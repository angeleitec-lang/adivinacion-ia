#!/usr/bin/env python3
"""Cierre de la recopilación (T85): orquestador del encadenado final.

Cuando terminan las pasadas en vivo, ejecuta en orden y sin olvidos:

  1. dedupe de consenso.jsonl (dos procesos escribieron el mismo fichero:
     conservar la ULTIMA version de cada (entidad_id, faceta); copia previa).
  2. limpieza de libros aplicada a las evidencias (aplicar_limpieza_libros.py,
     T71: generar en copia y sustituir el original con copia de seguridad).
  3. consenso con --excluir-claves y --rehacer-celdas-con-exclusion (T78).
  4. kb_v2.py (T66).
  5. cobertura v3 (T82) si el script esta integrado; si no, se omite con aviso.
  6. informe de cierre (agrega el log JSONL).

Garantias: cada paso hace copia previa con marca de tiempo, es idempotente y
reanudable, registra comando/entrada/salida/recuentos en un log JSONL, escribe
de forma atomica y el encadenado se detiene en el primer fallo.

--dry-run solo lee: comprueba entradas, procesos vivos que escriban esos ficheros
(aborta con aviso), espacio en disco y que haria cada paso. No escribe nada.

--paso 2 --solo-verificar: re-verifica una limpieza ya aplicada sin
reaplicarla (solo lectura; no loquean los procesos vivos).

Sin LLM propio ni red (el paso 3 puede pasarse --simulado para pruebas).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

CORPUS = os.path.dirname(os.path.abspath(__file__))
if CORPUS not in sys.path:
    sys.path.insert(0, CORPUS)

FASE0 = "/Users/angelgonzalez/fase0"
ESPACIO_MINIMO_BYTES = 2 * 1024 ** 3
PATRON_PROCESOS = r"consenso_kb\.py|afirmaciones_(rapido|libros|es)\.py|evidencias_incremental\.py"

NOMBRES_PASOS = {
    1: "dedupe_consenso",
    2: "limpieza_libros",
    3: "consenso_exclusion",
    4: "kb_v2",
    5: "cobertura_v3",
    6: "informe_cierre",
}


class PasoFallido(Exception):
    """Un paso del cierre fallo; el encadenado debe detenerse."""


def _ts():
    return time.strftime("%Y%m%d-%H%M%S")


def _leer_jsonl(ruta):
    filas = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def _escribir_jsonl_atomico(ruta, filas):
    tmp = ruta + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)


def _md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _copia_previa(ruta, sufijo="pre-cierre"):
    destino = "%s.%s-%s" % (ruta, sufijo, _ts())
    shutil.copy2(ruta, destino)
    return destino


def procesos_vivos(excluir_pids=None):
    """PIDs vivos que escriben los ficheros del cierre (consenso/afirmaciones)."""
    excluir = set(excluir_pids or [])
    excluir.add(os.getpid())
    excluir.add(os.getppid())
    try:
        proc = subprocess.run(
            ["pgrep", "-fl", PATRON_PROCESOS],
            capture_output=True, text=True, check=False)
    except OSError:
        return []
    vivos = []
    for linea in proc.stdout.splitlines():
        parts = linea.strip().split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid in excluir:
            continue
        vivos.append({"pid": pid, "cmd": (parts[1] if len(parts) > 1 else "")[:160]})
    return vivos


def _ejecutar(cmd, log_comandos):
    log_comandos.append(cmd)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise PasoFallido("comando fallo (rc=%d): %s\n%s" % (
            proc.returncode, " ".join(cmd), (proc.stderr or proc.stdout)[-800:]))
    return proc.stdout


# ---------------------------------------------------------------------------
# Paso 1: dedupe del consenso
# ---------------------------------------------------------------------------

def paso1_dedupe_consenso(ctx, log_comandos):
    ruta = ctx["consenso"]
    filas = _leer_jsonl(ruta)
    orden = []
    ultima = {}
    for fila in filas:
        clave = (fila.get("entidad_id"), fila.get("faceta"))
        if clave not in ultima:
            orden.append(clave)
        ultima[clave] = fila
    duplicadas = len(filas) - len(orden)
    if duplicadas == 0:
        return {"estado": "sin_cambio", "filas": len(filas), "unicas": len(orden),
                "duplicadas": 0}
    backup = _copia_previa(ruta)
    dedup = [ultima[c] for c in orden]
    _escribir_jsonl_atomico(ruta, dedup)
    # Comprobacion posterior: las unicas no bajan y ninguna clave se pierde.
    despues = _leer_jsonl(ruta)
    claves_despues = {(f.get("entidad_id"), f.get("faceta")) for f in despues}
    if len(despues) != len(orden) or claves_despues != set(orden):
        raise PasoFallido("dedupe: las celdas unicas no cuadran tras escribir")
    return {"estado": "ok", "filas_antes": len(filas), "filas_despues": len(despues),
            "unicas": len(orden), "duplicadas": duplicadas, "backup": backup}


# ---------------------------------------------------------------------------
# Paso 2: limpieza de libros (generar en copia + aplicar con backup)
# ---------------------------------------------------------------------------

def _verificacion_limpieza(ctx, estado="verificada"):
    """Verificacion del paso 2 con la clave COMPLETA.

    Una misma seccion puede estar retirada para una (entidad_id, faceta) y
    conservada legitimamente para otra; comparar solo hash_seccion daba falsos
    positivos (produccion 2026-10-21: 318 'vigentes' que no lo eran).
    """
    ruta_retiradas = os.path.join(ctx["libros_limpio"],
                                 "evidencias_retiradas.jsonl")
    if not os.path.exists(ruta_retiradas):
        raise PasoFallido("limpieza: no hay %s para verificar" % ruta_retiradas)
    retiradas = _leer_jsonl(ruta_retiradas)
    claves_retiradas = {
        (r["evidencia"].get("hash_seccion"),
         r["evidencia"].get("entidad_id"),
         r["evidencia"].get("faceta"))
        for r in retiradas}
    vigentes = {
        (e.get("hash_seccion"), e.get("entidad_id"), e.get("faceta"))
        for e in _leer_jsonl(ctx["evidencias_libros"])}
    filtradas = claves_retiradas & vigentes
    if filtradas:
        ejemplo = sorted(filtradas)[0]
        raise PasoFallido(
            "limpieza: %d evidencias retiradas siguen vigentes "
            "(ejemplo: hash=%s... entidad=%s faceta=%s)"
            % (len(filtradas), (ejemplo[0] or "")[:12], ejemplo[1], ejemplo[2]))
    return {"estado": estado, "retiradas": len(retiradas),
            "claves_retiradas": len(claves_retiradas),
            "vigentes": len(vigentes)}


def paso2_limpieza_libros(ctx, log_comandos):
    if ctx.get("solo_verificar"):
        return _verificacion_limpieza(ctx, "verificada")
    script = os.path.join(CORPUS, "aplicar_limpieza_libros.py")
    cmd = [sys.executable, script,
           "--evidencias", ctx["evidencias_libros"],
           "--secciones-dir", ctx["secciones_dir"],
           "--afirmaciones-dir", ctx["afirmaciones_libros_dir"],
           "--evidencias-web", ctx["evidencias_web"],
           "--out-dir", ctx["libros_limpio"]]
    if ctx.get("familias_json"):
        cmd += ["--familias-json", ctx["familias_json"]]
    _ejecutar(cmd, log_comandos)
    informe_ruta = os.path.join(ctx["libros_limpio"], "informe_limpieza.json")
    with open(informe_ruta, encoding="utf-8") as fh:
        informe = json.load(fh)
    recuento = informe.get("recuento", {})
    limpias = os.path.join(ctx["libros_limpio"], "evidencias_limpias.jsonl")
    if _md5(ctx["evidencias_libros"]) == _md5(limpias):
        return dict(_verificacion_limpieza(ctx, "ya_aplicada"),
                   recuento=recuento)
    backup = _copia_previa(ctx["evidencias_libros"])
    tmp = ctx["evidencias_libros"] + ".tmp-%d" % os.getpid()
    shutil.copy2(limpias, tmp)
    os.replace(tmp, ctx["evidencias_libros"])
    return dict(_verificacion_limpieza(ctx, "ok"),
                recuento=recuento, backup=backup)


# ---------------------------------------------------------------------------
# Paso 3: consenso con exclusion (T78)
# ---------------------------------------------------------------------------

def paso3_consenso_exclusion(ctx, log_comandos):
    script = os.path.join(CORPUS, "consenso_kb.py")
    cmd = [sys.executable, script,
           "--web-afirmaciones", ctx["afirmaciones_web_file"],
           "--libros-afirmaciones", ctx["afirmaciones_libros_file"],
           "--excluir-claves", ctx["claves_excluir"],
           "--secciones-dir", ctx["secciones_dir"],
           "--rehacer-celdas-con-exclusion",
           "--out-dir", ctx["consenso_dir"],
           "--workers", str(ctx["workers"])]
    if ctx.get("simulado"):
        cmd.append("--simulado")
    _ejecutar(cmd, log_comandos)
    exclusion_ruta = os.path.join(ctx["consenso_dir"], "exclusion_por_celda.jsonl")
    excluidas_por_celda = _leer_jsonl(exclusion_ruta) if os.path.exists(exclusion_ruta) else []
    n_excluidas = sum(e.get("n_excluidas", 0) for e in excluidas_por_celda)
    _comprobar_retiradas_fuera_de_consenso(ctx)
    return {"estado": "ok", "celdas_afectadas": len(excluidas_por_celda),
            "afirmaciones_excluidas": n_excluidas}


def _comprobar_retiradas_fuera_de_consenso(ctx):
    """Las afirmaciones de secciones excluidas no deben aparecer en el consenso."""
    import cartas
    import consenso_kb as ck
    claves = ck.cargar_claves_exclusion(ctx["claves_excluir"])
    secciones = ck.indexar_secciones_por_libro(ctx["secciones_dir"])
    afirmaciones = _leer_jsonl(ctx["afirmaciones_libros_file"])
    conservadas, excluidas_por_celda, _ = ck.excluir_claves_por_cita(
        afirmaciones, claves, secciones)
    cons_norm = {(a.get("entidad_id"), a.get("faceta"),
                 cartas.norm(a.get("afirmacion", ""))) for a in conservadas}
    # El mismo texto procedente de la web no es una filtracion de la limpieza
    # de libros: la exclusion solo atane a las secciones de libros.
    web_norm = set()
    if os.path.exists(ctx.get("afirmaciones_web_file", "")):
        web_norm = {(a.get("entidad_id"), a.get("faceta"),
                    cartas.norm(a.get("afirmacion", "")))
                   for a in _leer_jsonl(ctx["afirmaciones_web_file"])}
    textos_por_celda = {}
    for a in afirmaciones:
        clave = (a.get("entidad_id"), a.get("faceta"))
        if clave not in excluidas_por_celda:
            continue
        texto_norm = cartas.norm(a.get("afirmacion", ""))
        if (clave[0], clave[1], texto_norm) in cons_norm:
            continue
        if (clave[0], clave[1], texto_norm) in web_norm:
            continue
        textos_por_celda.setdefault(clave, set()).add(texto_norm)
    consenso = _leer_jsonl(ctx["consenso"])
    for celda in consenso:
        clave = (celda.get("entidad_id"), celda.get("faceta"))
        prohibidos = textos_por_celda.get(clave)
        if not prohibidos:
            continue
        for grupo_key in ("mayoritarias", "discrepancias", "unica_fuente"):
            for item in celda.get(grupo_key) or []:
                if cartas.norm(item.get("afirmacion", "")) in prohibidos:
                    raise PasoFallido(
                        "consenso: afirmacion excluida (%s / %s) presente en %s"
                        % (clave[0], clave[1], grupo_key))


# ---------------------------------------------------------------------------
# Paso 4: KB v2
# ---------------------------------------------------------------------------

def paso4_kb_v2(ctx, log_comandos):
    script = os.path.join(CORPUS, "kb_v2.py")
    cmd = [sys.executable, script,
           "--consenso", ctx["consenso"],
           "--out-dir", ctx["kb_out"]]
    _ejecutar(cmd, log_comandos)
    # Comprobacion: cada fichero de familia solo contiene entidades de su familia.
    import kb_v2
    por_familia = {}
    for familia in kb_v2.FAMILIAS:
        ruta = os.path.join(ctx["kb_out"], familia + ".json")
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as fh:
            doc = json.load(fh)
        mezclas = [eid for eid in doc.get("entidades", {})
                   if kb_v2.familia_de_entidad(eid) != familia]
        if mezclas:
            raise PasoFallido("kb_v2: familia %s contiene %d entidades ajenas "
                             "(ejemplo: %s)" % (familia, len(mezclas), mezclas[0]))
        por_familia[familia] = len(doc.get("entidades", {}))
    return {"estado": "ok", "entidades_por_familia": por_familia}


# ---------------------------------------------------------------------------
# Paso 5: cobertura v3 (omitir con aviso si T82 no esta integrado)
# ---------------------------------------------------------------------------

def paso5_cobertura_v3(ctx, log_comandos):
    script = os.path.join(CORPUS, "cobertura_v3.py")
    if not os.path.exists(script):
        return {"estado": "omitido",
                "aviso": "cobertura_v3.py no esta integrado en esta rama (T82); "
                        "ejecutar el paso cuando se integre track/t82-cobertura-v3"}
    cmd = [sys.executable, script,
           "--libros", "limpio",
           "--libros-limpio", ctx["libros_limpio"],
           "--excluir-claves", ctx["claves_excluir"],
           "--out-dir", ctx["cobertura_out"]]
    _ejecutar(cmd, log_comandos)
    salida = os.path.join(ctx["cobertura_out"], "cobertura_total_v3.json")
    doc = json.load(open(salida, encoding="utf-8"))
    resumen = doc.get("resumen", {})
    return {"estado": "ok", "resumen": resumen}


# ---------------------------------------------------------------------------
# Paso 6: informe de cierre
# ---------------------------------------------------------------------------

def paso6_informe(ctx, log_comandos):
    entradas = _leer_jsonl(ctx["log"]) if os.path.exists(ctx["log"]) else []
    informe = {"ts": _ts(), "pasos": entradas}
    ruta_json = os.path.join(ctx["work_dir"], "informe_cierre.json")
    tmp = ruta_json + ".tmp-%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta_json)
    lineas = ["# Informe de cierre de la recopilacion", "",
              "Generado: %s" % informe["ts"], "",
              "| Paso | Nombre | Estado | Recuentos |",
              "|---|---|---|---|"]
    for e in entradas:
        rec = json.dumps({k: v for k, v in e.get("recuentos", {}).items()
                         if k != "comandos"}, ensure_ascii=False)
        lineas.append("| %s | %s | %s | %s |" % (
            e.get("paso"), e.get("nombre"), e.get("estado"), rec[:200]))
    ruta_md = os.path.join(ctx["work_dir"], "informe_cierre.md")
    tmp_md = ruta_md + ".tmp-%d" % os.getpid()
    with open(tmp_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_md, ruta_md)
    return {"estado": "ok", "informe": ruta_json, "entradas_log": len(entradas)}


PASOS = {
    1: paso1_dedupe_consenso,
    2: paso2_limpieza_libros,
    3: paso3_consenso_exclusion,
    4: paso4_kb_v2,
    5: paso5_cobertura_v3,
    6: paso6_informe,
}


def _registrar(ctx, paso, estado, recuentos, comandos):
    entrada = {"ts": _ts(), "paso": paso, "nombre": NOMBRES_PASOS[paso],
               "estado": estado, "recuentos": recuentos, "comandos": comandos}
    with open(ctx["log"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entrada, ensure_ascii=False) + "\n")
        fh.flush()
    return entrada


def ejecutar_paso(ctx, paso):
    comandos = []
    try:
        resultado = PASOS[paso](ctx, comandos)
    except PasoFallido as exc:
        _registrar(ctx, paso, "fallido", {"error": str(exc)[:500]}, comandos)
        raise
    _registrar(ctx, paso, resultado.get("estado", "ok"), resultado, comandos)
    return resultado


def _validar_entradas_paso(ctx, paso):
    """Rutas que el paso necesita; devuelve lista de (ruta, existe)."""
    mapa = {
        1: [ctx["consenso"]],
        2: [ctx["evidencias_libros"], ctx["secciones_dir"],
            ctx["afirmaciones_libros_dir"], ctx["evidencias_web"]],
        3: [ctx["afirmaciones_web_file"], ctx["afirmaciones_libros_file"],
            ctx["claves_excluir"], ctx["secciones_dir"], ctx["consenso"]],
        4: [ctx["consenso"]],
        5: [ctx["claves_excluir"], ctx["libros_limpio"]],
        6: [],
    }
    return [(r, os.path.exists(r)) for r in mapa.get(paso, [])]


def dry_run(ctx, procesos_fn):
    print("== DRY RUN: no se escribe nada ==")
    faltan = []
    for paso in sorted(PASOS):
        for ruta, existe in _validar_entradas_paso(ctx, paso):
            marca = "OK " if existe else "FALTA"
            print("  [%s] paso %d: %s" % (marca, paso, ruta))
            if not existe:
                faltan.append(ruta)
    vivos = procesos_fn()
    if vivos:
        print("AVISO: procesos vivos que escriben los ficheros del cierre:")
        for v in vivos:
            print("  PID %s: %s" % (v["pid"], v["cmd"]))
        print("Abortar el cierre hasta que terminen.")
        return 1
    uso = shutil.disk_usage(ctx["base_dir"])
    libre_gb = uso.free / (1024 ** 3)
    print("Espacio libre en %s: %.1f GB" % (ctx["base_dir"], libre_gb))
    if uso.free < ESPACIO_MINIMO_BYTES:
        print("AVISO: espacio libre por debajo de 2 GB")
    if faltan:
        print("Faltan %d entradas; el cierre no podra completarse." % len(faltan))
        return 1
    for paso in sorted(PASOS):
        print("  paso %d (%s): %s" % (paso, NOMBRES_PASOS[paso],
                                      _descripcion_paso(ctx, paso)))
    return 0


def _descripcion_paso(ctx, paso):
    if paso == 1:
        try:
            filas = _leer_jsonl(ctx["consenso"])
            unicas = len({(f.get("entidad_id"), f.get("faceta")) for f in filas})
            dup = len(filas) - unicas
            return ("dedupe: %d filas, %d unicas, %d duplicadas -> %s"
                    % (len(filas), unicas, dup,
                       "sin cambio" if dup == 0 else "reescribir con backup"))
        except OSError:
            return "sin leer"
    if paso == 2:
        return ("generar limpieza en %s y sustituir %s con backup"
                % (ctx["libros_limpio"], ctx["evidencias_libros"]))
    if paso == 3:
        return ("consenso --excluir-claves %s --rehacer-celdas-con-exclusion "
                "en %s" % (ctx["claves_excluir"], ctx["consenso_dir"]))
    if paso == 4:
        return "kb_v2 desde %s hacia %s" % (ctx["consenso"], ctx["kb_out"])
    if paso == 5:
        if os.path.exists(os.path.join(CORPUS, "cobertura_v3.py")):
            return "cobertura v3 en %s" % ctx["cobertura_out"]
        return "OMITIDO: cobertura_v3.py no integrado (T82)"
    return "informe de cierre en %s" % ctx["work_dir"]


def construir_ctx(args):
    base = args.base_dir
    consenso_dir = args.consenso_dir or os.path.join(base, "consenso_kb")
    return {
        "base_dir": base,
        "consenso": args.consenso or os.path.join(consenso_dir, "consenso.jsonl"),
        "consenso_dir": consenso_dir,
        "evidencias_libros": args.evidencias_libros or os.path.join(
            base, "libros", "evidencias", "evidencias.jsonl"),
        "secciones_dir": args.secciones_dir or os.path.join(base, "libros", "secciones"),
        "afirmaciones_libros_dir": args.afirmaciones_libros_dir or os.path.join(
            base, "afirmaciones_libros"),
        "afirmaciones_libros_file": args.afirmaciones_libros_file or os.path.join(
            base, "afirmaciones_libros", "afirmaciones_libros.jsonl"),
        "afirmaciones_web_file": args.afirmaciones_web_file or os.path.join(
            base, "afirmaciones_full", "afirmaciones.jsonl"),
        "evidencias_web": args.evidencias_web or os.path.join(
            base, "evidencias_web", "evidencias.jsonl"),
        "claves_excluir": args.claves_excluir or os.path.join(
            base, "libros_limpio", "claves_excluir_consenso.jsonl"),
        "libros_limpio": args.libros_limpio or os.path.join(base, "libros_limpio"),
        "kb_out": args.kb_out or os.path.join(base, "kb_v2"),
        "cobertura_out": args.cobertura_out or os.path.join(base, "cobertura_v3"),
        "work_dir": args.work_dir or os.path.join(base, "cierre"),
        "familias_json": args.familias_json,
        "simulado": args.simulado,
        "workers": args.workers,
    }


def main(argv=None, procesos_fn=None):
    parser = argparse.ArgumentParser(
        description="Cierre de la recopilacion: dedupe, limpieza, consenso con "
                    "exclusion, KB v2, cobertura v3 e informe (T85).")
    parser.add_argument("--base-dir", default=FASE0)
    parser.add_argument("--dry-run", action="store_true",
                       help="solo lectura: entradas, procesos vivos, disco y plan")
    parser.add_argument("--paso", type=int, choices=sorted(PASOS),
                       help="ejecutar un unico paso")
    parser.add_argument("--solo-verificar", action="store_true",
                       help="solo con --paso 2: re-verificar una limpieza ya "
                            "aplicada sin reaplicarla (solo lectura; no loquean "
                            "los procesos vivos)")
    parser.add_argument("--todo", action="store_true",
                       help="ejecutar todos los pasos en orden")
    parser.add_argument("--simulado", action="store_true",
                       help="cliente simulado para el paso de consenso (pruebas)")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--consenso")
    parser.add_argument("--consenso-dir")
    parser.add_argument("--evidencias-libros")
    parser.add_argument("--secciones-dir")
    parser.add_argument("--afirmaciones-libros-dir")
    parser.add_argument("--afirmaciones-libros-file")
    parser.add_argument("--afirmaciones-web-file")
    parser.add_argument("--evidencias-web")
    parser.add_argument("--claves-excluir")
    parser.add_argument("--libros-limpio")
    parser.add_argument("--kb-out")
    parser.add_argument("--cobertura-out")
    parser.add_argument("--work-dir")
    parser.add_argument("--familias-json")
    args = parser.parse_args(argv)

    ctx = construir_ctx(args)
    procesos_fn = procesos_fn or procesos_vivos

    if args.solo_verificar and args.paso != 2:
        parser.error("--solo-verificar solo aplica a --paso 2")
    ctx["solo_verificar"] = args.solo_verificar

    if args.dry_run:
        return dry_run(ctx, procesos_fn)
    if not args.paso and not args.todo:
        parser.error("indicar --dry-run, --paso N o --todo")

    os.makedirs(ctx["work_dir"], exist_ok=True)
    ctx["log"] = os.path.join(ctx["work_dir"], "cierre_log.jsonl")
    # --solo-verificar es solo lectura: no loquean los procesos vivos.
    vivos = [] if args.solo_verificar else procesos_fn()
    if vivos:
        print("AVISO: procesos vivos que escriben los ficheros del cierre:")
        for v in vivos:
            print("  PID %s: %s" % (v["pid"], v["cmd"]))
        print("Cierre abortado; esperar a que terminen las pasadas.")
        return 1

    pasos = [args.paso] if args.paso else sorted(PASOS)
    for paso in pasos:
        print("== Paso %d: %s ==" % (paso, NOMBRES_PASOS[paso]))
        try:
            resultado = ejecutar_paso(ctx, paso)
        except PasoFallido as exc:
            print("FALLO en paso %d (%s): %s" % (paso, NOMBRES_PASOS[paso], exc))
            print("Encadenado detenido; los pasos posteriores no se ejecutan.")
            return 1
        print("   -> %s" % json.dumps(resultado, ensure_ascii=False)[:300])
    print("CIERRE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
