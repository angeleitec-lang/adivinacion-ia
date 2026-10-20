"""Recuperación dirigida de celdas bajo mínimo de cobertura.

Lee la matriz de cobertura (cobertura_total.json) y produce:

- ``plan_recuperacion.jsonl``: una línea por entidad con facetas bajo mínimo,
  fuentes nuevas necesarias por faceta, consultas de búsqueda (ES/EN) y URLs
  candidatas de sitios validados. Ordenado por rentabilidad (facetas que se
  arreglan con una sola búsqueda por entidad).
- ``informe_recuperacion.md``: resumen por familia, top de entidades por
  carencia y estimación de fuentes nuevas para bajar del 10% de celdas
  bajo mínimo.

No descarga nada: solo planifica. Las búsquedas las ejecuta una persona o un
pipeline aparte, con las precauciones de rate limit del proyecto.
"""
import argparse
import datetime
import json
import math
import os
import sys
import unicodedata

MINIMOS = {"fuentes": 5, "clasicas": 1, "modernas": 2, "es": 1}

FAMILIA_LABEL = {
    "tarot": "Tarot",
    "baraja_espanola": "Baraja española",
    "astrologia": "Astrología",
    "numerologia": "Numerología",
    "desconocida": "Desconocida",
}

# ---------------------------------------------------------------------------
# Nombres en inglés (para consultas de búsqueda)
# ---------------------------------------------------------------------------

_MAYORES_EN = [
    "The Fool", "The Magician", "The High Priestess", "The Empress",
    "The Emperor", "The Hierophant", "The Lovers", "The Chariot",
    "Strength", "The Hermit", "Wheel of Fortune", "Justice",
    "The Hanged Man", "Death", "Temperance", "The Devil", "The Tower",
    "The Star", "The Moon", "The Sun", "Judgement", "The World",
]

_RANK_EN = {
    1: "Ace", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six",
    7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Page",
    12: "Knight", 13: "Queen", 14: "King",
}

_PALO_EN = {"bastos": "Wands", "copas": "Cups", "espadas": "Swords",
            "oros": "Pentacles"}

_SIGNOS_EN = {
    "aries": "Aries", "tauro": "Taurus", "geminis": "Gemini",
    "cancer": "Cancer", "leo": "Leo", "virgo": "Virgo", "libra": "Libra",
    "escorpio": "Scorpio", "sagitario": "Sagittarius",
    "capricornio": "Capricorn", "acuario": "Aquarius", "piscis": "Pisces",
}

_PLANETAS_EN = {
    "sol": "Sun", "luna": "Moon", "mercurio": "Mercury", "venus": "Venus",
    "marte": "Mars", "jupiter": "Jupiter", "saturno": "Saturn",
    "urano": "Uranus", "neptuno": "Neptune", "pluton": "Pluto",
}

_ASPECTOS_EN = {
    "conjuncion": "conjunct", "sextil": "sextile", "cuadratura": "square",
    "trigono": "trine", "oposicion": "opposition",
}

_POSICIONES_EN = {
    "camino_de_vida": "Life Path", "destino": "Destiny Number",
    "alma": "Soul Number", "personalidad": "Personality Number",
    "anio_personal": "Personal Year", "mes_personal": "Personal Month",
}

_ORDINAL_EN = {1: "1st", 2: "2nd", 3: "3rd"}

_TERMO_FACETA_ES = {
    "significado_general": "significado",
    "luz_sombra": "luz y sombra",
    "derecha_invertida": "al derecho y al revés",
    "amor": "amor",
    "trabajo": "trabajo",
    "dinero": "dinero",
    "salud": "salud",
    "espiritual": "espiritual",
    "simbolismo": "simbolismo",
    "correspondencias": "correspondencias",
    "consejo_practico": "consejo práctico",
    "ejemplo_de_uso": "ejemplo de lectura",
}

_TERMO_FACETA_EN = {
    "significado_general": "meaning",
    "luz_sombra": "light and shadow",
    "derecha_invertida": "upright and reversed",
    "amor": "love",
    "trabajo": "work",
    "dinero": "money",
    "salud": "health",
    "espiritual": "spiritual",
    "simbolismo": "symbolism",
    "correspondencias": "correspondences",
    "consejo_practico": "practical advice",
    "ejemplo_de_uso": "example reading",
}

# Autor clásico de referencia por familia (cualificador de búsqueda).
_AUTOR_CLASICO = {"tarot": "Waite", "astrologia": "Lilly",
                  "numerologia": "Pitágoras"}

_POSICIONES_CONOCIDAS = set(_POSICIONES_EN)


# ---------------------------------------------------------------------------
# Carencias por celda
# ---------------------------------------------------------------------------

def _carencias(celda, minimos):
    """Déficit por cada restricción de la celda."""
    return {
        "independiente": max(0, minimos["fuentes"] - int(celda.get("n_fuentes") or 0)),
        "clasica": max(0, minimos["clasicas"] - int(celda.get("n_clasicas") or 0)),
        "moderna": max(0, minimos["modernas"] - int(celda.get("n_modernas") or 0)),
        "es": max(0, minimos["es"] - int(celda.get("n_es") or 0)),
    }


def fuentes_necesarias(celda, minimos=None):
    """Mínimo de fuentes nuevas que satisface todas las carencias a la vez.

    Cada fuente nueva cuenta como una independiente; si es clásica cubre la
    cuota de clásicas, si es moderna la de modernas, si está en español la de
    español. Una fuente no puede ser clásica y moderna a la vez, por eso las
    carencias de clásica+moderna se suman.
    """
    m = minimos or MINIMOS
    if celda.get("completa"):
        return 0
    d = _carencias(celda, m)
    return max(d["independiente"], d["clasica"] + d["moderna"], d["es"], 0)


def tipos_faltantes(celda, minimos=None):
    """Qué restricciones de la celda están por debajo del mínimo."""
    d = _carencias(celda, minimos or MINIMOS)
    return {k: v > 0 for k, v in d.items()}


# ---------------------------------------------------------------------------
# Identificación de entidades
# ---------------------------------------------------------------------------

def familia_de(entidad_id):
    """Familia (clave interna) derivada del entidad_id."""
    entidad_id = str(entidad_id or "")
    if entidad_id.startswith("tarot-"):
        return "tarot"
    if entidad_id.startswith("naipe-"):
        return "baraja_espanola"
    partes = entidad_id.split("|")
    if len(partes) == 2 and partes[1] == "signo":
        return "astrologia"
    if len(partes) == 3 and partes[2] in ("planeta_en_signo", "planeta_en_casa"):
        return "astrologia"
    if len(partes) == 4 and partes[3] == "aspecto":
        return "astrologia"
    if len(partes) == 2 and partes[1] in _POSICIONES_CONOCIDAS:
        return "numerologia"
    return "desconocida"


def _ordinal_en(n):
    if n in _ORDINAL_EN:
        return _ORDINAL_EN[n]
    return f"{n}th"


def nombre_en(entidad_id, nombre):
    """Nombre en inglés para consultas; fallback al nombre en español."""
    if entidad_id.startswith("tarot-mayor-"):
        try:
            idx = int(entidad_id.rsplit("-", 1)[1]) - 1
        except ValueError:
            return nombre
        if 0 <= idx < len(_MAYORES_EN):
            return _MAYORES_EN[idx]
        return nombre
    if entidad_id.startswith("tarot-"):
        trozos = entidad_id.split("-")
        if len(trozos) == 3:
            palo, nn = trozos[1], trozos[2]
            try:
                n = int(nn)
            except ValueError:
                return nombre
            if palo in _PALO_EN and n in _RANK_EN:
                return f"{_RANK_EN[n]} of {_PALO_EN[palo]}"
        return nombre
    partes = entidad_id.split("|")
    if len(partes) == 2 and partes[1] == "signo":
        return _SIGNOS_EN.get(partes[0], nombre)
    if len(partes) == 3 and partes[2] == "planeta_en_signo":
        p, s = partes[0], partes[1]
        if p in _PLANETAS_EN and s in _SIGNOS_EN:
            return f"{_PLANETAS_EN[p]} in {_SIGNOS_EN[s]}"
        return nombre
    if len(partes) == 3 and partes[2] == "planeta_en_casa":
        p = partes[0]
        casa = partes[1]
        if casa.startswith("casa"):
            try:
                n = int(casa[4:])
            except ValueError:
                return nombre
            if p in _PLANETAS_EN:
                return f"{_PLANETAS_EN[p]} in {_ordinal_en(n)} House"
        return nombre
    if len(partes) == 4 and partes[3] == "aspecto":
        p1, a, p2 = partes[0], partes[1], partes[2]
        if p1 in _PLANETAS_EN and p2 in _PLANETAS_EN and a in _ASPECTOS_EN:
            return f"{_PLANETAS_EN[p1]} {_ASPECTOS_EN[a]} {_PLANETAS_EN[p2]}"
        return nombre
    if len(partes) == 2 and partes[1] in _POSICIONES_EN:
        return f"{_POSICIONES_EN[partes[1]]} {partes[0]}"
    return nombre


def _slug(texto):
    """Slug en minúsculas con guiones, sin acentos."""
    norm = unicodedata.normalize("NFD", texto)
    sin_acentos = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    out = []
    for ch in sin_acentos.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def _nombre_fallback(entidad_id):
    base = entidad_id.split("|")[0]
    return base.replace("-", " ").strip().title()


# ---------------------------------------------------------------------------
# Catálogo (nombre legible y familia canónica)
# ---------------------------------------------------------------------------

_CATALOGO_CACHE = None


def _catalogo():
    global _CATALOGO_CACHE
    if _CATALOGO_CACHE is None:
        try:
            import cobertura
            _CATALOGO_CACHE = {e["entidad_id"]: e for e in cobertura.entidades()}
        except Exception:
            _CATALOGO_CACHE = {}
    return _CATALOGO_CACHE


# ---------------------------------------------------------------------------
# Consultas y URLs candidatas
# ---------------------------------------------------------------------------

def _uniq(seq):
    vistos = set()
    out = []
    for x in seq:
        if x not in vistos:
            vistos.add(x)
            out.append(x)
    return out


def _consultas(entidad_id, familia, nombre, facetas):
    es = []
    en = []
    nom_en = nombre_en(entidad_id, nombre)
    for f in facetas:
        fac = f["faceta"]
        t_es = _TERMO_FACETA_ES.get(fac, fac.replace("_", " "))
        t_en = _TERMO_FACETA_EN.get(fac, fac.replace("_", " "))
        es.append(f"{nombre} {t_es}")
        en.append(f"{nom_en} {t_en}")
        if "clasica" in f["tipos"]:
            autor = _AUTOR_CLASICO.get(familia)
            if autor:
                es.append(f"{nombre} {t_es} {autor}")
            else:
                es.append(f"{nombre} {t_es} clásico")
            en.append(f"{nom_en} {t_en} classical")
    return {"es": _uniq(es), "en": _uniq(en)}


def _urls_tarot(entidad_id, nombre):
    urls = []
    if entidad_id.startswith("tarot-mayor-"):
        try:
            idx = int(entidad_id.rsplit("-", 1)[1]) - 1
        except ValueError:
            idx = -1
        if 0 <= idx < len(_MAYORES_EN):
            slug = _slug(_MAYORES_EN[idx])
            urls.append({"url": f"https://biddytarot.com/tarot-card-meanings/major-arcana/{slug}/",
                       "sitio": "biddytarot.com", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.labyrinthos.co/blogs/tarot-card-meanings-list/{slug}-tarot-card-meaning",
                       "sitio": "labyrinthos.co", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.tarot.com/tarot/cards/{slug}",
                       "sitio": "tarot.com", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.aeclectic.net/tarot/tarot-card-meanings/major-arcana/{slug}.shtml",
                       "sitio": "aeclectic.net", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://tarotrossana.com/guia/tarot/arcanos-mayores/{_slug(nombre)}-tarot/",
                       "sitio": "tarotrossana.com", "nota": "ficha ES de la carta"})
        return urls
    trozos = entidad_id.split("-")
    if len(trozos) == 3:
        palo, nn = trozos[1], trozos[2]
        try:
            n = int(nn)
        except ValueError:
            return urls
        if palo in _PALO_EN and n in _RANK_EN:
            slug = _slug(f"{_RANK_EN[n]} of {_PALO_EN[palo]}")
            corte = 11 <= n <= 14
            aec_path = "court-cards" if corte else "minor-arcana"
            urls.append({"url": f"https://biddytarot.com/tarot-card-meanings/minor-arcana/{slug}/",
                       "sitio": "biddytarot.com", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.labyrinthos.co/blogs/tarot-card-meanings-list/{slug}-tarot-card-meaning",
                       "sitio": "labyrinthos.co", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.tarot.com/tarot/cards/{slug}",
                       "sitio": "tarot.com", "nota": "ficha EN de la carta"})
            urls.append({"url": f"https://www.aeclectic.net/tarot/tarot-card-meanings/{aec_path}/{slug}.shtml",
                       "sitio": "aeclectic.net", "nota": "ficha EN de la carta"})
    return urls


_SITIOS_INDICE_CACHE = None


def _sitios_indice():
    global _SITIOS_INDICE_CACHE
    if _SITIOS_INDICE_CACHE is None:
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "knowledge", "sitios_indice_es.json")
        try:
            with open(ruta, encoding="utf-8") as fh:
                _SITIOS_INDICE_CACHE = json.load(fh).get("sitios", [])
        except Exception:
            _SITIOS_INDICE_CACHE = []
    return _SITIOS_INDICE_CACHE


_PRIORIDAD_ORDEN = {"alta": 0, "media": 1, "baja": 2}


def _urls_indice(familia, maximo=4):
    sitios = [s for s in _sitios_indice() if s.get("familia") == familia]
    sitios.sort(key=lambda s: _PRIORIDAD_ORDEN.get(s.get("prioridad"), 9))
    urls = []
    for s in sitios[:maximo]:
        indice = s.get("indice")
        if isinstance(indice, list):
            indice = indice[0] if indice else None
        if not indice:
            continue
        urls.append({"url": indice, "sitio": s.get("dominio", s.get("nombre", "")),
                    "nota": "empezar por el índice validado y buscar la entidad dentro"})
    return urls


def urls_candidatas(entidad_id, familia, nombre):
    """URLs de sitios validados para la entidad (sin descargar)."""
    if familia == "tarot":
        return _urls_tarot(entidad_id, nombre)
    if familia in ("baraja_espanola", "astrologia", "numerologia"):
        return _urls_indice(familia)
    return []


# ---------------------------------------------------------------------------
# Plan de recuperación
# ---------------------------------------------------------------------------

def construir_plan(matriz, minimos=None):
    """Una entrada por entidad con facetas bajo mínimo, ordenada por rentabilidad."""
    m = minimos or MINIMOS
    if not isinstance(matriz, dict):
        raise ValueError("La matriz debe ser un objeto JSON")
    catalogo = _catalogo()
    grupos = {}
    for indice, celda in enumerate(matriz.get("celdas", [])):
        if not isinstance(celda, dict):
            raise ValueError(f"La celda {indice} no es un objeto JSON")
        for campo in ("entidad_id", "faceta"):
            if not celda.get(campo):
                raise ValueError(f"La celda {indice} no tiene el campo {campo}")
        if celda.get("completa"):
            continue
        neces = fuentes_necesarias(celda, m)
        if neces <= 0:
            continue
        grupos.setdefault(celda["entidad_id"], []).append((celda, neces))
    plan = []
    for eid, items in grupos.items():
        info = catalogo.get(eid)
        familia = info["familia"] if info else familia_de(eid)
        nombre = info["nombre"] if info else _nombre_fallback(eid)
        facetas = []
        total = 0
        tipos_agg = {"independiente": False, "clasica": False,
                     "moderna": False, "es": False}
        for c, neces in items:
            caren = _carencias(c, m)
            tipos = [k for k, v in caren.items() if v > 0]
            facetas.append({
                "faceta": c["faceta"],
                "n_fuentes": c.get("n_fuentes", 0),
                "n_clasicas": c.get("n_clasicas", 0),
                "n_modernas": c.get("n_modernas", 0),
                "n_es": c.get("n_es", 0),
                "fuentes_necesarias": neces,
                "tipos": tipos,
            })
            total += neces
            for k in tipos:
                tipos_agg[k] = True
        plan.append({
            "entidad_id": eid,
            "familia": familia,
            "nombre": nombre,
            "rentabilidad": len(facetas),
            "facetas": facetas,
            "fuentes_necesarias": total,
            "tipos_faltantes": tipos_agg,
            "consultas": _consultas(eid, familia, nombre, facetas),
            "urls_candidatas": urls_candidatas(eid, familia, nombre),
        })
    plan.sort(key=lambda p: (-p["rentabilidad"], p["fuentes_necesarias"],
                            p["entidad_id"]))
    return plan


def estimar_meta(celdas, meta=0.10, minimos=None):
    """Fuentes nuevas para que las celdas bajo mínimo queden por debajo de `meta`."""
    m = minimos or MINIMOS
    total = len(celdas)
    bajo = [c for c in celdas if not c.get("completa")]
    max_bajo = max(0, math.ceil(total * meta) - 1)
    necesidades = sorted(fuentes_necesarias(c, m) for c in bajo)
    a_arreglar = max(0, len(bajo) - max_bajo)
    return {
        "total_celdas": total,
        "bajo_minimo": len(bajo),
        "max_bajo_permitido": max_bajo,
        "celdas_a_arreglar": a_arreglar,
        "fuentes_para_meta": sum(necesidades[:a_arreglar]),
        "fuentes_total": sum(necesidades),
    }


def _resumen_familias(celdas):
    acc = {}
    for c in celdas:
        if not isinstance(c, dict):
            continue
        f = familia_de(c.get("entidad_id"))
        d = acc.setdefault(f, {"celdas": 0, "completas": 0})
        d["celdas"] += 1
        if c.get("completa"):
            d["completas"] += 1
    return acc


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def generar_informe(matriz, plan, top=50, meta=0.10):
    """Markdown con resumen por familia, top de carencias y estimación de meta."""
    celdas = matriz.get("celdas", [])
    resumen = _resumen_familias(celdas)
    est = estimar_meta(celdas, meta=meta)
    hoy = datetime.date.today().isoformat()
    lineas = [
        "# Informe de recuperación dirigida",
        "",
        f"Generado el {hoy} a partir de la matriz de cobertura.",
        "",
        f"- Total de celdas: **{est['total_celdas']}**",
        f"- Celdas bajo mínimo: **{est['bajo_minimo']}**",
        "",
        "## Celdas bajo mínimo por familia",
        "",
        "| Familia | Celdas | Completas | Bajo mínimo | % bajo mínimo |",
        "|---|---:|---:|---:|---:|",
    ]
    orden = ["tarot", "baraja_espanola", "astrologia", "numerologia",
             "desconocida"]
    claves = [f for f in orden if f in resumen] + \
             [f for f in sorted(resumen) if f not in orden]
    for f in claves:
        d = resumen[f]
        bajo = d["celdas"] - d["completas"]
        pct = (100.0 * bajo / d["celdas"]) if d["celdas"] else 0.0
        lineas.append(f"| {FAMILIA_LABEL.get(f, f)} | {d['celdas']} | "
                     f"{d['completas']} | {bajo} | {pct:.1f}% |")
    lineas += [
        "",
        f"## Top {top} entidades por carencia",
        "",
        "| Entidad | Familia | Facetas bajo mínimo | Fuentes necesarias |",
        "|---|---|---:|---:|",
    ]
    for p in plan[:top]:
        lineas.append(f"| {p['nombre']} (`{p['entidad_id']}`) | "
                     f"{FAMILIA_LABEL.get(p['familia'], p['familia'])} | "
                     f"{p['rentabilidad']} | {p['fuentes_necesarias']} |")
    pct_meta = int(round(meta * 100))
    lineas += [
        "",
        f"## Estimación para bajar del {pct_meta}% de celdas bajo mínimo",
        "",
        f"- Máximo de celdas bajo mínimo permitido: **{est['max_bajo_permitido']}**",
        f"- Celdas a arreglar (las más baratas primero): **{est['celdas_a_arreglar']}**",
        f"- Fuentes nuevas estimadas para la meta: **{est['fuentes_para_meta']}**",
        f"- Fuentes nuevas para arreglar todas las celdas: **{est['fuentes_total']}**",
        "",
        "El plan completo (consultas ES/EN y URLs candidatas por entidad) está en "
        "`plan_recuperacion.jsonl`, ordenado por rentabilidad: una búsqueda por "
        "entidad cubre varias facetas a la vez.",
        "",
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Plan de recuperación dirigida de celdas bajo mínimo.")
    parser.add_argument("--matriz",
                      default="/Users/angelgonzalez/fase0/cobertura_total.json",
                      help="Ruta a la matriz de cobertura JSON.")
    parser.add_argument("--out-plan", default=None,
                      help="Salida del plan JSONL (por defecto, junto a la matriz).")
    parser.add_argument("--out-informe", default=None,
                      help="Salida del informe markdown (por defecto, junto a la matriz).")
    parser.add_argument("--top", type=int, default=50,
                      help="Número de entidades en el top del informe.")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe ficheros, solo informa.")
    args = parser.parse_args(argv)

    if not os.path.exists(args.matriz):
        print(f"[ERROR] matriz no encontrada: {args.matriz}", file=sys.stderr)
        return 1
    try:
        with open(args.matriz, encoding="utf-8") as fh:
            matriz = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[ERROR] no se pudo leer la matriz: {exc}", file=sys.stderr)
        return 1

    plan = construir_plan(matriz)
    informe = generar_informe(matriz, plan, top=args.top)
    base = os.path.dirname(os.path.abspath(args.matriz))
    out_plan = args.out_plan or os.path.join(base, "plan_recuperacion.jsonl")
    out_informe = args.out_informe or os.path.join(base, "informe_recuperacion.md")

    if args.dry_run:
        print(f"[dry-run] {len(plan)} entidades con facetas bajo mínimo.")
        print(f"[dry-run] plan: {out_plan}")
        print(f"[dry-run] informe: {out_informe}")
        return 0

    with open(out_plan, "w", encoding="utf-8") as fh:
        for p in plan:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(out_informe, "w", encoding="utf-8") as fh:
        fh.write(informe)
    print(f"Plan escrito en {out_plan} ({len(plan)} entidades).")
    print(f"Informe escrito en {out_informe}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
