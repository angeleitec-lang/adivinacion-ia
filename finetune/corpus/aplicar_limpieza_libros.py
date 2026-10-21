"""Aplica (en copia) la limpieza de evidencias de libros y mide su efecto.

T71. Toma las evidencias de libros ya juzgadas y aplica un filtro
determinista (sin LLM ni red) con tres motivos de retirada:

  1. ``sol_luna_astrologica``: evidencias de ``tarot-mayor-19`` (La Luna) o
     ``tarot-mayor-20`` (El Sol) procedentes de libros cuya familia declarada
     en el inventario es ``astrologia``. Esas secciones hablan del planeta, no
     de la carta del tarot: son contaminación cruzada entre sistemas.
  2. ``titulo_otra_carta``: regla de T53/T67 (reutilizada de
     ``limpiar_evidencias_libros``): mayor cuyo titulo de seccion identifica
     OTRA carta del tarot.
  3. ``mayor_sistema_ajeno``: evidencias de mayor-19/20 procedentes de libros
     de ``numerologia``, ``quiromancia`` o ``iching``: el nombre de la carta
     ahi es ambiguo y la seccion no trata del arcano.

Nunca toca el original: escribe copias en ``libros_limpio/`` (evidencias
limpias, retiradas con motivo, muestra de revision con semilla fija, informe
de recuentos y claves de afirmaciones a excluir del consenso). Mide celdas
entidad x faceta completas antes/despes usando ``cobertura.py`` sin
sobrescribir ``cobertura_total_v2.json``.

La decision de aplicar a produccion la toma un humano revisando el informe;
el comando exacto se documenta en docs/LIMPIEZA_LIBROS.md.
"""
import argparse
import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cobertura
import diagnostico_tarot_libros as diag
import limpiar_evidencias_libros as lim

BASE = "/Users/angelgonzalez/fase0"
RUTA_EVIDENCIAS = os.path.join(BASE, "libros", "evidencias", "evidencias.jsonl")
DIR_SECCIONES = os.path.join(BASE, "libros", "secciones")
DIR_AFIRMACIONES = os.path.join(BASE, "afirmaciones_libros")
RUTA_EVIDENCIAS_WEB = os.path.join(BASE, "evidencias_web", "evidencias.jsonl")
DIR_SALIDA = os.path.join(BASE, "libros_limpio")
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "knowledge")
INVENTARIOS = ["fuentes_libros.jsonl", "fuentes_libros_es.jsonl",
              "fuentes_clasicas_pd.jsonl", "fuentes_libros_tema.jsonl"]

# Mayores cuyo nombre colisiona con el planeta (Sol/Luna) o con otros sistemas.
MAYORES_SOL_LUNA = {"tarot-mayor-19", "tarot-mayor-20"}
FAMILIAS_AJENAS = {"numerologia", "quiromancia", "iching"}
SEMILLA_MUESTRA = 42
TAM_MUESTRA = 40


def _leer_jsonl(ruta):
    out = []
    if not os.path.exists(ruta):
        return out
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _escribir_jsonl(ruta, registros):
    with open(ruta, "w", encoding="utf-8") as fh:
        for r in registros:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def cargar_familias_libros(knowledge_dir=None):
    """fuente_id -> familia declarada en los inventarios de knowledge."""
    if knowledge_dir is None:
        knowledge_dir = KNOWLEDGE_DIR
    familias = {}
    for fn in INVENTARIOS:
        for d in _leer_jsonl(os.path.join(knowledge_dir, fn)):
            fid = d.get("id")
            fam = d.get("familia")
            if fid and fam:
                familias[fid] = fam
    return familias


def motivo_retirada(ev, familias, titulos):
    """Devuelve el motivo de retirada (prioridad fija) o None si se conserva.

    ``titulos``: hash_seccion -> titulo (secciones indexadas).
    """
    eid = ev.get("entidad_id")
    familia = familias.get(ev.get("fuente_id"))
    if eid in MAYORES_SOL_LUNA and familia == "astrologia":
        return "sol_luna_astrologica"
    if lim._es_mayor(eid):
        num = lim._numero_mayor(eid)
        esperado = lim.MAYOR_TOKEN.get(num) if num is not None else None
        titulo = titulos.get(ev.get("hash_seccion"), "")
        if esperado is not None:
            if not lim._nombra_propio(titulo, num):
                if diag.clasificar_titulo(titulo, esperado) == "otra":
                    return "titulo_otra_carta"
    if eid in MAYORES_SOL_LUNA and familia in FAMILIAS_AJENAS:
        return "mayor_sistema_ajeno"
    return None


def aplicar_limpieza(evidencias, secciones, familias):
    """Clasifica evidencias en conservadas/retiradas. No muta las entradas.

    Devuelve {"kept": [...], "retiradas": [{"evidencia", "motivo", "titulo",
    "familia_libro"}], "recuento": {...}}.
    """
    idx = diag.indexar_secciones(secciones)
    titulos = {h: s.get("titulo", "") for h, s in idx.items()}
    kept = []
    retiradas = []
    for ev in evidencias:
        motivo = motivo_retirada(ev, familias, titulos)
        if motivo is None:
            kept.append(ev)
        else:
            retiradas.append({
                "evidencia": ev,
                "motivo": motivo,
                "titulo": titulos.get(ev.get("hash_seccion"), ""),
                "familia_libro": familias.get(ev.get("fuente_id"), "SIN_META"),
            })
    recuento = {
        "total": len(evidencias),
        "conservadas": len(kept),
        "retiradas": len(retiradas),
        "por_motivo": _conteo(retiradas, "motivo"),
        "por_motivo_y_libro": _conteo_doble(retiradas, "motivo",
                                           "evidencia", "fuente_id"),
        "por_motivo_y_entidad": _conteo_doble(retiradas, "motivo",
                                             "evidencia", "entidad_id"),
    }
    return {"kept": kept, "retiradas": retiradas, "recuento": recuento}


def _conteo(retiradas, campo):
    c = {}
    for r in retiradas:
        c[r[campo]] = c.get(r[campo], 0) + 1
    return dict(sorted(c.items()))


def _conteo_doble(retiradas, campo_primario, dict_evidencia, campo_ev):
    c = {}
    for r in retiradas:
        clave = (r[campo_primario], r[dict_evidencia].get(campo_ev) or "SIN_ID")
        c[clave] = c.get(clave, 0) + 1
    return {"|".join(k): v for k, v in sorted(c.items())}


def muestra_revision(retiradas, n=TAM_MUESTRA, semilla=SEMILLA_MUESTRA):
    """Muestra determinista de retiradas para revision humana."""
    ordenadas = sorted(
        retiradas,
        key=lambda r: (r["evidencia"].get("hash_seccion") or "",
                      r["evidencia"].get("entidad_id") or "",
                      r["evidencia"].get("faceta") or ""),
    )
    if n >= len(ordenadas):
        return list(ordenadas)
    rng = random.Random(semilla)
    return sorted(rng.sample(ordenadas, n),
                  key=lambda r: (r["evidencia"].get("hash_seccion") or "",
                                r["evidencia"].get("entidad_id") or "",
                                r["evidencia"].get("faceta") or ""))


def claves_excluir_consenso(retiradas, procesados):
    """Claves (hash_seccion, entidad_id, faceta) de afirmaciones a excluir.

    ``procesados``: registros de afirmaciones_libros/procesados.jsonl con
    hash_seccion, entidad_id, faceta y n_afirmaciones. Solo se listan las
    claves retiradas que efectivamente produjeron afirmaciones.
    """
    n_por_clave = {}
    for p in procesados:
        clave = (p.get("hash_seccion"), p.get("entidad_id"), p.get("faceta"))
        try:
            n = int(p.get("n_afirmaciones", 0))
        except (TypeError, ValueError):
            n = 0
        if all(clave):
            n_por_clave[clave] = n_por_clave.get(clave, 0) + n
    claves = []
    vistos = set()
    for r in retiradas:
        ev = r["evidencia"]
        clave = (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))
        if not all(clave) or clave in vistos:
            continue
        vistos.add(clave)
        n = n_por_clave.get(clave, 0)
        if n > 0:
            claves.append({
                "hash_seccion": clave[0],
                "entidad_id": clave[1],
                "faceta": clave[2],
                "n_afirmaciones": n,
                "motivo": r["motivo"],
            })
    claves.sort(key=lambda c: (c["entidad_id"], c["faceta"], c["hash_seccion"]))
    return claves


def medir_cobertura(evidencias_libros, evidencias_web=None):
    """Celdas completas antes/despues sobre una copia en memoria de la matriz.

    No escribe cobertura_total_v2.json: solo calcula y devuelve resumenes.
    """
    catalogo = cobertura.entidades()
    res = {}
    for nombre, evs in evidencias_libros.items():
        r = cobertura.calcular_cobertura(evs, catalogo=catalogo)
        res[nombre] = {
            "completas": r["completas"],
            "total_celdas": len(r["celdas"]),
            "por_familia": cobertura.resumen_por_familia(r, catalogo),
        }
    if evidencias_web is not None:
        for nombre, evs in evidencias_libros.items():
            combinadas = list(evs) + list(evidencias_web)
            r = cobertura.calcular_cobertura(combinadas, catalogo=catalogo)
            res[nombre + "_con_web"] = {
                "completas": r["completas"],
                "total_celdas": len(r["celdas"]),
                "por_familia": cobertura.resumen_por_familia(r, catalogo),
            }
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Aplica en copia la limpieza de evidencias de libros y "
                    "mide su efecto (no toca el original).")
    ap.add_argument("--evidencias", default=RUTA_EVIDENCIAS)
    ap.add_argument("--secciones-dir", default=DIR_SECCIONES)
    ap.add_argument("--afirmaciones-dir", default=DIR_AFIRMACIONES)
    ap.add_argument("--evidencias-web", default=RUTA_EVIDENCIAS_WEB)
    ap.add_argument("--out-dir", default=DIR_SALIDA)
    ap.add_argument("--semilla", type=int, default=SEMILLA_MUESTRA)
    ap.add_argument("--familias-json", default=None,
                    help="JSON dict fuente_id->familia (por defecto, los "
                         "inventarios de knowledge)")
    args = ap.parse_args(argv)

    evidencias = _leer_jsonl(args.evidencias)
    secciones = []
    if os.path.isdir(args.secciones_dir):
        for fn in sorted(os.listdir(args.secciones_dir)):
            if fn.endswith(".jsonl"):
                secciones.extend(
                    _leer_jsonl(os.path.join(args.secciones_dir, fn)))
    if args.familias_json:
        with open(args.familias_json, "r", encoding="utf-8") as fh:
            familias = json.load(fh)
    else:
        familias = cargar_familias_libros()

    res = aplicar_limpieza(evidencias, secciones, familias)
    procesados = _leer_jsonl(
        os.path.join(args.afirmaciones_dir, "procesados.jsonl"))
    claves = claves_excluir_consenso(res["retiradas"], procesados)
    n_afirmaciones_excluidas = sum(c["n_afirmaciones"] for c in claves)

    web = _leer_jsonl(args.evidencias_web)
    medicion = medir_cobertura(
        {"antes": evidencias, "despues": res["kept"]},
        evidencias_web=web)

    os.makedirs(args.out_dir, exist_ok=True)
    _escribir_jsonl(os.path.join(args.out_dir, "evidencias_limpias.jsonl"),
                    res["kept"])
    _escribir_jsonl(os.path.join(args.out_dir, "evidencias_retiradas.jsonl"),
                    res["retiradas"])
    _escribir_jsonl(os.path.join(args.out_dir, "muestra_revision.jsonl"),
                    muestra_revision(res["retiradas"], semilla=args.semilla))
    _escribir_jsonl(
        os.path.join(args.out_dir, "claves_excluir_consenso.jsonl"), claves)

    informe = {
        "recuento": res["recuento"],
        "afirmaciones": {
            "claves_excluidas": len(claves),
            "afirmaciones_afectadas": n_afirmaciones_excluidas,
        },
        "cobertura": medicion,
    }
    with open(os.path.join(args.out_dir, "informe_limpieza.json"), "w",
              encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print("Total evidencias: %d | conservadas: %d | retiradas: %d"
          % (res["recuento"]["total"], res["recuento"]["conservadas"],
             res["recuento"]["retiradas"]))
    for m, n in res["recuento"]["por_motivo"].items():
        print("  %s: %d" % (m, n))
    print("Afirmaciones a excluir del consenso: %d claves, %d afirmaciones"
          % (len(claves), n_afirmaciones_excluidas))
    for k in ("antes", "despues", "antes_con_web", "despues_con_web"):
        d = medicion.get(k)
        if d:
            print("Cobertura %s: %d/%d celdas completas"
                  % (k, d["completas"], d["total_celdas"]))
    print("Salida (original intacto): %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
