"""Orquestador de los clásicos de dominio público hacia evidencias (T57).

Reutiliza las etapas de `libros_pipeline` (limpieza, segmentación y juez)
sobre un directorio de trabajo NUEVO, separado del real
(`/Users/angelgonzalez/fase0/libros`), para que los diez clásicos PD que
descargó T55 puedan cubrir las celdas que exigen fuente clásica sin
mezclarse con las evidencias ya existentes.

Prioridad: baraja española primero (`libro_negro_1886`), luego el resto de
baraja, numerología y astrología. Cada pasada es reanudable: el juez no
vuelve a llamar al LLM por secciones cuyo hash ya está en `juicios.jsonl`.

El `--dry-run` mide en memoria secciones y llamadas estimadas por libro sin
tocar disco ni red; si un libro supera `UMBRAL_LLAMADAS` se recomienda
procesarlo por tramos con `--max-llamadas`.
"""
import argparse
import json
import os
import shutil
import sys

import cobertura
import juez
import libros_limpiar
import libros_pipeline
import libros_segmentar

WORK_DIR_REAL = "/Users/angelgonzalez/fase0/libros"
WORK_DIR_CLASICOS = "/Users/angelgonzalez/fase0/libros_clasicos_pd"
CRUDO_ORIGEN = os.path.join(WORK_DIR_REAL, "crudo")
META_NOMBRE = "fuentes_libros_clasicos_pd.jsonl"
UMBRAL_LLAMADAS = 600
PASO_LLAMADAS = 300
TIMEOUT_CLASICO = 90.0
MIN_CRUDO_BYTES = 1024


class LibroAusenteError(Exception):
    """El crudo de un clásico no está en el origen ni en el work-dir."""


# Orden de prioridad: baraja española primero (la mayor laguna de la
# matriz), luego numerología y astrología. `familia` es la del segmentador
# ("baraja" cubre la baraja española del KB, `baraja_espanola`).
CLASICOS = (
    {"id": "libro_negro_1886",
     "titulo": "El libro negro o la magia",
     "autor": "anónimo", "anio": 1886, "idioma": "es", "familia": "baraja"},
    {"id": "richmond_mystic_test_1919",
     "titulo": "The Mystic Test Book",
     "autor": "W. F. B. Richmond", "anio": 1919, "idioma": "en",
     "familia": "baraja"},
    {"id": "westcott_numbers_1911",
     "titulo": "Numbers: Their Occult Power and Mystic Virtues",
     "autor": "W. W. Westcott", "anio": 1911, "idioma": "en",
     "familia": "numerologia"},
    {"id": "balliett_philosophy_numbers_1908",
     "titulo": "The Philosophy of Numbers",
     "autor": "L. Dow Balliett", "anio": 1908, "idioma": "en",
     "familia": "numerologia"},
    {"id": "sepharial_manual_occultism_1914",
     "titulo": "A Manual of Occultism",
     "autor": "Sepharial", "anio": 1914, "idioma": "en",
     "familia": "astrologia"},
    {"id": "agrippa_three_books_1898",
     "titulo": "Three Books of Occult Philosophy",
     "autor": "Heinrich Cornelius Agrippa", "anio": 1898, "idioma": "en",
     "familia": "astrologia"},
    {"id": "firmicus_mathescos_1897",
     "titulo": "Matheseos Libri VIII",
     "autor": "Firmicus Maternus", "anio": 1897, "idioma": "en",
     "familia": "astrologia"},
    {"id": "manilius_housman_1903",
     "titulo": "Astronomica",
     "autor": "Manilio (ed. Housman)", "anio": 1903, "idioma": "en",
     "familia": "astrologia"},
    {"id": "zadkiel_grammar_1833",
     "titulo": "The Grammar of Astrology",
     "autor": "Zadkiel (Alan Leo)", "anio": 1833, "idioma": "en",
     "familia": "astrologia"},
    {"id": "sepharial_horoscope_1920",
     "titulo": "Astrology: How to Make and Read Your Own Horoscope",
     "autor": "Sepharial", "anio": 1920, "idioma": "en",
     "familia": "astrologia"},
)


def libros_en_orden(solo_ids=None):
    """Registros formato-pipeline de los clásicos, en orden de prioridad."""
    conocidos = {c["id"] for c in CLASICOS}
    if solo_ids:
        faltan = sorted(set(solo_ids) - conocidos)
        if faltan:
            raise LibroAusenteError(
                "ids fuera del listado de clásicos PD: %s" % ", ".join(faltan))
    libros = []
    for c in CLASICOS:
        if solo_ids and c["id"] not in solo_ids:
            continue
        libros.append({
            "id": c["id"], "titulo": c["titulo"], "autor": c["autor"],
            "anio": c["anio"], "idioma": c["idioma"], "familia": c["familia"],
            "prioridad": "alta", "origen": "local_pd", "url": None,
            "ruta_local": None, "calidad": "con_limpieza", "nota": "clasico_pd",
        })
    return libros


def validar_work_dir(work_dir):
    """Rechaza el work-dir real: aquí nunca se escribe en la tubería madre."""
    real = os.path.realpath(work_dir)
    raiz_real = os.path.realpath(WORK_DIR_REAL)
    if real == raiz_real or real.startswith(raiz_real + os.sep):
        raise ValueError(
            "work-dir %r apunta al directorio real de la tubería; usa uno "
            "aparte (por defecto: %s)" % (work_dir, WORK_DIR_CLASICOS))
    return real


def ruta_crudo(work_dir, libro_id):
    return os.path.join(work_dir, "crudo", libro_id + ".txt")


def crudo_disponible(work_dir, libro_id):
    """Ruta del crudo usable: primero el del work-dir, luego el del origen."""
    for ruta in (ruta_crudo(work_dir, libro_id),
                os.path.join(CRUDO_ORIGEN, libro_id + ".txt")):
        if os.path.isfile(ruta) and os.path.getsize(ruta) >= MIN_CRUDO_BYTES:
            return ruta
    return None


def preparar_work_dir(work_dir, libros):
    """Crea la estructura y enlaza los crudos; escribe el meta para el juez."""
    for sub in ("crudo", "limpio", "secciones", "evidencias", "knowledge",
               "resumenes"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    for libro in libros:
        destino = ruta_crudo(work_dir, libro["id"])
        if os.path.exists(destino):
            continue
        origen = os.path.join(CRUDO_ORIGEN, libro["id"] + ".txt")
        if not os.path.isfile(origen):
            raise LibroAusenteError(
                "falta el crudo de %s (esperado en %s)" % (libro["id"], origen))
        try:
            os.symlink(origen, destino)
        except OSError:
            shutil.copyfile(origen, destino)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        for c in CLASICOS:
            fh.write(json.dumps({"id": c["id"], "anio": c["anio"],
                                "idioma": c["idioma"], "titulo": c["titulo"],
                                "autor": c["autor"]},
                               ensure_ascii=False) + "\n")


def medir_libro(libro, work_dir):
    """Segmenta en memoria y cuenta secciones y llamadas (sin LLM ni disco)."""
    ruta = crudo_disponible(work_dir, libro["id"])
    if not ruta:
        raise LibroAusenteError(
            "falta el crudo de %s (esperado en %s)"
            % (libro["id"], os.path.join(CRUDO_ORIGEN, libro["id"] + ".txt")))
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    limpio, informe = libros_limpiar.limpiar(texto, libro["idioma"])
    secciones = libros_segmentar.segmentar(limpio, libro["familia"],
                                          libro["id"])
    con_candidatos = sum(1 for s in secciones if juez.candidatos_seccion(s))
    return {"secciones": len(secciones), "con_candidatos": con_candidatos,
            "llamadas_estimadas": con_candidatos,
            "calidad_baja": bool(informe.get("calidad_baja"))}


def resumen_de_evidencias(work_dir, libro_id):
    """Cuenta las evidencias del libro: totales, calidad >= 3, familia/entidad."""
    ruta = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    familias = {e["entidad_id"]: e["familia"] for e in cobertura.entidades()}
    total = aceptadas = 0
    por_familia = {}
    por_entidad = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    ev = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if ev.get("fuente_id") != libro_id:
                    continue
                total += 1
                calidad = ev.get("calidad") or 0
                if calidad >= 3:
                    aceptadas += 1
                fam = familias.get(ev.get("entidad_id"), "desconocida")
                por_familia[fam] = por_familia.get(fam, 0) + 1
                ent = ev.get("entidad_id") or "?"
                por_entidad[ent] = por_entidad.get(ent, 0) + 1
    return {"evidencias": total, "aceptadas_calidad_ge_3": aceptadas,
            "evidencias_por_familia": por_familia,
            "evidencias_por_entidad": por_entidad}


def _hashes_juzgados(work_dir):
    ruta = os.path.join(work_dir, "evidencias", "juicios.jsonl")
    hechos = set()
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    registro = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if registro.get("hash"):
                    hechos.add(registro["hash"])
    return hechos


def purgar_errores_juez(work_dir):
    """Quita de `juicios.jsonl` los juicios `tipo=error` (timeouts del nodo).

    Sin esto, un juicio-error queda guardado como hecho y la reanudación no
    lo reintenta: los timeouts de un nodo saturado envenenarian el work-dir.
    Devuelve el número de registros eliminados.
    """
    ruta = os.path.join(work_dir, "evidencias", "juicios.jsonl")
    if not os.path.exists(ruta):
        return 0
    buenos = []
    errores = 0
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            stripped = linea.strip()
            if not stripped:
                continue
            try:
                registro = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if registro.get("juicio", {}).get("tipo") == "error":
                errores += 1
            else:
                buenos.append(stripped)
    if errores:
        with open(ruta, "w", encoding="utf-8") as fh:
            for linea in buenos:
                fh.write(linea + "\n")
    return errores


def procesar_libro(libro, work_dir, hasta="juez", max_llamadas=0, workers=1,
                  timeout=TIMEOUT_CLASICO, simulado=False, cliente=None):
    """Corre limpieza, segmentación y juez para un libro; devuelve el resumen."""
    ctx = {"pausa": 0.0, "workers": workers, "simulado": simulado,
           "cliente": cliente,
           "knowledge_dir": os.path.join(work_dir, "knowledge"),
           "timeout": timeout, "lote_juez": None}
    libros_pipeline._etapa_limpieza([libro], work_dir, ctx)
    if hasta == "limpieza":
        return {"id": libro["id"], "hasta": hasta}
    libros_pipeline._etapa_segmentacion([libro], work_dir, ctx)
    if hasta == "segmentacion":
        return {"id": libro["id"], "hasta": hasta}
    secciones = libros_pipeline.secciones_de_libros([libro], work_dir)
    if not secciones:
        print("%s: sin secciones que juzgar" % libro["id"], file=sys.stderr)
        return {"id": libro["id"], "hasta": hasta, "secciones": 0,
                "juzgadas": 0, "llamadas": 0, "evidencias": 0,
                "reaprovechadas": 0, "sin_candidatos": 0, "error": 0}
    purgados = purgar_errores_juez(work_dir)
    if purgados:
        print("%s: %d juicios-error purgados para reintentar"
              % (libro["id"], purgados), flush=True)
    cliente_juez = libros_pipeline._cliente_juez(ctx)
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if max_llamadas and max_llamadas > 0:
        hechos = _hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                     if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:max_llamadas]
    stats = juez.procesar_secciones(a_procesar, cliente_juez,
                                    os.path.join(work_dir, "evidencias"),
                                    meta=meta, workers=workers)
    resumen = {"id": libro["id"], "hasta": hasta, "secciones": len(secciones),
               "procesadas_esta_pasada": len(a_procesar)}
    resumen.update(stats)
    resumen.update(resumen_de_evidencias(work_dir, libro["id"]))
    ruta_resumen = os.path.join(work_dir, "resumenes", libro["id"] + ".json")
    with open(ruta_resumen, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return resumen


def ejecutar(work_dir=WORK_DIR_CLASICOS, solo_ids=None, hasta="juez",
            max_llamadas=0, workers=1, timeout=TIMEOUT_CLASICO,
            simulado=False, dry_run=False, cliente=None):
    """Orquesta los clásicos por orden de prioridad. Devuelve código de salida."""
    try:
        work_dir = validar_work_dir(work_dir)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    try:
        libros = libros_en_orden(solo_ids)
    except LibroAusenteError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not libros:
        print("No hay libros que procesar.")
        return 0
    if dry_run:
        for libro in libros:
            try:
                medida = medir_libro(libro, work_dir)
            except LibroAusenteError as exc:
                print("%s: %s" % (libro["id"], exc), file=sys.stderr)
                continue
            print("%s: %d secciones, %d con candidatos (~%d llamadas al LLM)%s"
                  % (libro["id"], medida["secciones"], medida["con_candidatos"],
                     medida["llamadas_estimadas"],
                     " [calidad de limpieza baja]"
                     if medida["calidad_baja"] else ""))
            if medida["llamadas_estimadas"] > UMBRAL_LLAMADAS:
                print("  supera %d llamadas: procesa con --max-llamadas %d y "
                      "repite la orden para continuar"
                      % (UMBRAL_LLAMADAS, PASO_LLAMADAS))
        return 0
    for libro in libros:
        try:
            preparar_work_dir(work_dir, [libro])
        except LibroAusenteError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        resumen = procesar_libro(libro, work_dir, hasta=hasta,
                                max_llamadas=max_llamadas, workers=workers,
                                timeout=timeout, simulado=simulado,
                                cliente=cliente)
        if hasta == "juez":
            print("%s: %d/%d secciones, %d llamadas, %d reaprovechadas, "
                  "%d sin candidatos, %d errores, %d evidencias "
                  "(%d con calidad >= 3)"
                  % (libro["id"], resumen.get("juzgadas", 0),
                     resumen.get("secciones", 0), resumen.get("llamadas", 0),
                     resumen.get("reaprovechadas", 0),
                     resumen.get("sin_candidatos", 0),
                     resumen.get("error", 0), resumen.get("evidencias", 0),
                     resumen.get("aceptadas_calidad_ge_3", 0)), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pasa los clásicos PD por la tubería de libros hacia "
                    "evidencias (work-dir aparte del real).")
    parser.add_argument("--work-dir", default=WORK_DIR_CLASICOS)
    parser.add_argument("--solo-ids", default="",
                      help="ids separados por comas (orden de prioridad fijo)")
    parser.add_argument("--hasta", default="juez",
                       choices=("limpieza", "segmentacion", "juez"))
    parser.add_argument("--max-llamadas", type=int, default=0,
                      help="máximo de secciones pendientes por libro en esta "
                           "pasada (0 = sin límite)")
    parser.add_argument("--workers", type=int, default=1,
                       help="hilos de llamada al LLM (nodos saturados: 1)")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_CLASICO,
                       help="timeout por petición al LLM en segundos")
    parser.add_argument("--simulado", action="store_true",
                       help="cliente LLM simulado para el juez")
    parser.add_argument("--dry-run", action="store_true",
                       help="mide secciones y llamadas sin tocar disco ni LLM")
    parser.add_argument("--list", action="store_true", dest="lista",
                       help="muestra el orden de prioridad y sale")
    args = parser.parse_args(argv)
    solo = {s.strip() for s in args.solo_ids.split(",") if s.strip()} or None
    if args.lista:
        try:
            for libro in libros_en_orden(solo):
                print("%s (%s, %s, %d)" % (libro["id"], libro["familia"],
                                          libro["idioma"], libro["anio"]))
        except LibroAusenteError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        return 0
    return ejecutar(work_dir=args.work_dir, solo_ids=solo, hasta=args.hasta,
                   max_llamadas=args.max_llamadas, workers=args.workers,
                   timeout=args.timeout, simulado=args.simulado,
                   dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
