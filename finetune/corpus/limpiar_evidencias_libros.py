"""Post-filtro determinista (PROPUESTA, no aplica a produccion).

Dadas las evidencias ya juzgadas (`evidencias.jsonl`) y las secciones de origen,
propone quitar las evidencias de ARCANOS MAYORES cuyo titulo de seccion ya
identifica OTRA carta del tarot. Es determinista y barato: no llama al LLM ni
relanza el juez; solo clasifica por titulo reutilizando la logica del
diagnostico (`diagnostico_tarot_libros.clasificar_titulo`).

Nunca toca el fichero original: escribe `evidencias_filtradas.jsonl` (lo que se
conservaria) y `informe_filtro.md` (cuantas se quitarian por carta) en un
directorio nuevo. La decision de aplicar o no la toma un humano revisando el
informe.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cartas
import diagnostico_tarot_libros as diag

# Tokens (normalizados, minusculas, sin tildes) que identifican la propia carta
# mayor por su numero. Si el titulo contiene alguno, la evidencia es coherente y
# se conserva, aunque el titulo nombre tambien otra carta. Cubre variantes reales
# de los libros (judgement/judgment, hanged/hanging, priestess/papess...).
MAYOR_PROPIO = {
    1: ["fool"],
    2: ["magician", "magus", "mage"],
    3: ["priestess", "papess"],
    4: ["empress"],
    5: ["emperor"],
    6: ["hierophant", "pope"],
    7: ["lovers"],
    8: ["chariot"],
    9: ["strength", "fortitude"],
    10: ["hermit"],
    11: ["wheel"],
    12: ["justice"],
    13: ["hanged", "hanging"],
    14: ["death"],
    15: ["temperance"],
    16: ["devil"],
    17: ["tower"],
    18: ["star"],
    19: ["moon"],
    20: ["sun"],
    21: ["judgement", "judgment", "resurrection"],
    22: ["world"],
}

# Token primario que se pasa a `clasificar_titulo` para detectar otra carta.
MAYOR_TOKEN = {n: toks[0] for n, toks in MAYOR_PROPIO.items()}


def _nombra_propio(titulo, num):
    """True si el titulo nombra la propia carta mayor `num`."""
    t = cartas.norm(titulo or "")
    for tok in MAYOR_PROPIO.get(num, []):
        if re.search(r"(?<![a-z])" + re.escape(tok) + r"(?![a-z])", t):
            return True
    return False


def _es_mayor(entidad_id):
    return bool(entidad_id) and entidad_id.startswith("tarot-mayor-")


def _numero_mayor(entidad_id):
    try:
        return int(entidad_id.rsplit("-", 1)[-1])
    except (ValueError, AttributeError):
        return None


def propuesta_filtro(evidencias, secciones):
    """Clasifica evidencias y propone quitar mayores con titulo de otra carta.

    Devuelve un dict con:
      - kept: evidencias que se conservarian (todo lo no quitado).
      - removed: lista de {"evidencia", "titulo"} de las propuestas a quitar.
      - por_carta: entidad_id -> {"total_mayor", "quitadas", "muestra"}.
      - total, n_quitadas.
    No muta las listas de entrada.
    """
    idx = diag.indexar_secciones(secciones)
    kept = []
    removed = []
    total_mayor = {}
    quitadas = {}
    muestra = {}

    for ev in evidencias:
        eid = ev.get("entidad_id")
        if not _es_mayor(eid):
            kept.append(ev)
            continue
        num = _numero_mayor(eid)
        total_mayor[eid] = total_mayor.get(eid, 0) + 1
        esperado = MAYOR_TOKEN.get(num) if num is not None else None
        if num is None or esperado is None:
            kept.append(ev)
            continue
        sec = idx.get(ev.get("hash_seccion"))
        if sec is None:
            kept.append(ev)
            continue
        titulo = sec.get("titulo", "")
        if _nombra_propio(titulo, num):
            kept.append(ev)
            continue
        if diag.clasificar_titulo(titulo, esperado) == "otra":
            removed.append({"evidencia": ev, "titulo": titulo})
            quitadas[eid] = quitadas.get(eid, 0) + 1
            muestra.setdefault(eid, []).append(titulo)
        else:
            kept.append(ev)

    por_carta = {}
    for eid, q in sorted(quitadas.items()):
        por_carta[eid] = {
            "total_mayor": total_mayor.get(eid, 0),
            "quitadas": q,
            "muestra": muestra.get(eid, [])[:15],
        }
    return {
        "kept": kept,
        "removed": removed,
        "por_carta": por_carta,
        "total": len(evidencias),
        "n_quitadas": len(removed),
    }


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
                out.append(json.loads(linea))
            except Exception:
                continue
    return out


def _escribir_jsonl(ruta, registros):
    with open(ruta, "w", encoding="utf-8") as fh:
        for r in registros:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def informe_markdown(res):
    lineas = [
        "# Propuesta de post-filtro de evidencias de mayores",
        "",
        "Total evidencias analizadas: %d" % res["total"],
        "Propuestas a quitar (mayor con titulo de otra carta): %d"
        % res["n_quitadas"],
        "A conservar: %d" % len(res["kept"]),
        "",
        "## Quitadas por carta",
        "",
        "| entidad_id | total mayor | quitadas |",
        "|---|---|---|",
    ]
    for eid, d in res["por_carta"].items():
        lineas.append("| %s | %d | %d |"
                     % (eid, d["total_mayor"], d["quitadas"]))
    lineas.append("")
    lineas.append("## Muestra de titulos retirados")
    lineas.append("")
    for eid, d in res["por_carta"].items():
        lineas.append("### %s (%d)" % (eid, d["quitadas"]))
        for t in d["muestra"]:
            lineas.append("- %r" % t)
        lineas.append("")
    return "\n".join(lineas)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Propone quitar evidencias de mayores cuyo titulo de "
                    "seccion identifica otra carta (no aplica a produccion).")
    ap.add_argument("--evidencias",
                    default="/Users/angelgonzalez/fase0/libros/evidencias/"
                            "evidencias.jsonl")
    ap.add_argument("--secciones-dir",
                    default="/Users/angelgonzalez/fase0/libros/secciones")
    ap.add_argument("--out-dir",
                    default="/Users/angelgonzalez/fase0/filtro_evidencias")
    args = ap.parse_args(argv)

    evidencias = _leer_jsonl(args.evidencias)
    secciones = []
    if os.path.isdir(args.secciones_dir):
        for fn in sorted(os.listdir(args.secciones_dir)):
            if fn.endswith(".jsonl"):
                secciones.extend(_leer_jsonl(os.path.join(args.secciones_dir, fn)))

    res = propuesta_filtro(evidencias, secciones)
    os.makedirs(args.out_dir, exist_ok=True)
    _escribir_jsonl(os.path.join(args.out_dir, "evidencias_filtradas.jsonl"),
                    res["kept"])
    with open(os.path.join(args.out_dir, "informe_filtro.md"), "w",
              encoding="utf-8") as fh:
        fh.write(informe_markdown(res))

    print("Analizadas: %d | propuestas a quitar: %d | a conservar: %d"
          % (res["total"], res["n_quitadas"], len(res["kept"])))
    print("Salida (NO toca el original): %s" % args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
