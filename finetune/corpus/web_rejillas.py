"""Expansión de las rejillas de astrología en tareas de descarga (track A3).

Cada tarea apunta a la página de una entidad concreta (planeta en signo, planeta en
casa o aspecto) y lleva una `entidad_id` normalizada en español canónico para
poder cruzar fuentes entre sitios, aunque el slug de la URL esté en inglés.
"""
import argparse
import json
import os
import sys

from urllib.parse import urlparse

RUTA_REJILLAS = os.path.join(os.path.dirname(__file__), os.pardir,
                             "knowledge", "rejillas_astrologia.json")
RUTA_FUENTES = os.path.join(os.path.dirname(__file__), os.pardir,
                            "knowledge", "fuentes_sitios.jsonl")
SITIOS_IA = {"my-zodiac-ai.com"}


def _dominio_base(dominio):
    return dominio[4:] if dominio.startswith("www.") else dominio


def cargar_rejillas(ruta=None):
    with open(ruta or RUTA_REJILLAS, encoding="utf-8") as f:
        return json.load(f)


def _prioridades(ruta=None):
    mapa = {}
    try:
        with open(ruta or RUTA_FUENTES, encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    reg = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                mapa[_dominio_base(reg.get("dominio", ""))] = reg.get(
                    "prioridad", "sin_evaluar")
    except FileNotFoundError:
        pass
    return mapa


def _mapa_canonico(slugs):
    """Slug en → slug es (listas paralelas) y casa en → número."""
    planetas = {}
    for i, p_en in enumerate(slugs["en"]["planetas"]):
        planetas[p_en] = slugs["es"]["planetas"][i]
    casas = {}
    for i, h_en in enumerate(slugs["en"]["casas"]):
        casas[h_en] = slugs["es"]["casas"][i]
    return planetas, casas


def expandir(rejilla, slugs):
    """Genera las tareas de una rejilla a partir de sus slugs (es o en)."""
    idioma = rejilla.get("slugs", "es")
    canon_p, canon_h = _mapa_canonico(slugs)
    prior = _prioridades().get(_dominio_base(rejilla["sitio"]), "sin_evaluar")
    faceta = rejilla["faceta"]
    tareas = []
    if faceta == "planeta_en_signo":
        for p in slugs[idioma]["planetas"]:
            for s in slugs[idioma]["signos"]:
                cp = canon_p.get(p, p)
                cs = slugs["es"]["signos"][slugs[idioma]["signos"].index(s)]
                tareas.append({
                    "sitio": rejilla["sitio"], "faceta": faceta,
                    "entidad": {"planeta": cp, "signo": cs},
                    "entidad_id": f"{cp}|{cs}|planeta_en_signo",
                    "url": rejilla["patron"].format(p=p, s=s),
                    "prioridad": prior,
                })
    elif faceta == "planeta_en_casa":
        for p in slugs[idioma]["planetas"]:
            for h in slugs[idioma]["casas"]:
                cp = canon_p.get(p, p)
                ch = canon_h.get(h, h)
                tareas.append({
                    "sitio": rejilla["sitio"], "faceta": faceta,
                    "entidad": {"planeta": cp, "casa": int(ch)},
                    "entidad_id": f"{cp}|casa{int(ch)}|planeta_en_casa",
                    "url": rejilla["patron"].format(p=p, h=h),
                    "prioridad": prior,
                })
    elif faceta == "aspecto":
        planetas = slugs[idioma]["planetas"]
        aspectos = slugs["es"]["aspectos"]
        for i in range(len(planetas)):
            for j in range(i + 1, len(planetas)):
                p1, p2 = planetas[i], planetas[j]
                c1, c2 = canon_p.get(p1, p1), canon_p.get(p2, p2)
                for x in aspectos:
                    tareas.append({
                        "sitio": rejilla["sitio"], "faceta": faceta,
                        "entidad": {"planeta": c1, "planeta2": c2, "aspecto": x},
                        "entidad_id": f"{c1}|{x}|{c2}|aspecto",
                        "url": rejilla["patron"].format(p1=p1, p2=p2, x=x),
                        "prioridad": prior,
                    })
    else:
        raise ValueError(f"faceta desconocida: {faceta}")
    return tareas


def tareas_todas(datos, solo_sitios=None, facetas=None, excluir_ia=False,
                 limite=None):
    """Expande todas las rejillas aplicando filtros de sitio, faceta e IA."""
    tareas = []
    for rejilla in datos["rejillas"]:
        if solo_sitios and rejilla["sitio"] not in solo_sitios:
            continue
        if facetas and rejilla["faceta"] not in facetas:
            continue
        if excluir_ia and rejilla["sitio"] in SITIOS_IA:
            continue
        tareas.extend(expandir(rejilla, datos["slugs"]))
        if limite is not None and len(tareas) >= limite:
            return tareas[:limite]
    return tareas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Expande las rejillas en tareas de descarga")
    ap.add_argument("--solo-sitios", help="lista separada por comas")
    ap.add_argument("--facetas", help="lista separada por comas")
    ap.add_argument("--excluir-ia", action="store_true",
                    help="excluye my-zodiac-ai.com")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--out", help="fichero JSONL de salida (por defecto stdout)")
    args = ap.parse_args(argv)
    datos = cargar_rejillas()
    tareas = tareas_todas(
        datos,
        solo_sitios=args.solo_sitios.split(",") if args.solo_sitios else None,
        facetas=args.facetas.split(",") if args.facetas else None,
        excluir_ia=args.excluir_ia,
        limite=args.limite,
    )
    salida = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        for t in tareas:
            salida.write(json.dumps(t, ensure_ascii=False) + "\n")
    finally:
        if args.out:
            salida.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
