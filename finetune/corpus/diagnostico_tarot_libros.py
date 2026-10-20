"""Diagnostico (solo lectura) de la evidencia clasica de tarot en libros.

No relanza el juez ni modifica datos: analiza evidencias.jsonl y secciones/*.jsonl
ya producidos, y reproduce con pruebas el defecto de mapeo de nombres ingleses
en cartas.py. Ver ESTADO.md para el informe y el parche propuesto.
"""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cartas

_RANGOS_EN = [
    "ace", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "page", "knight", "queen", "king",
]
_PALOS_EN = ["swords", "cups", "wands", "pentacles"]

_MAYORES_EN = [
    "the fool", "the magician", "the high priestess", "the empress",
    "the emperor", "the hierofante", "the hierophant", "the lovers",
    "the chariot", "strength", "the hermit", "wheel of fortune",
    "justice", "the hanged man", "death", "temperance", "the devil",
    "the tower", "the star", "the moon", "the sun", "judgement",
    "judgment", "the world",
]

_MENORES_EN = ["%s of %s" % (r, s) for r in _RANGOS_EN for s in _PALOS_EN]

_MENOR_EN_RE = re.compile(
    r"\b(" + "|".join(_RANGOS_EN) + r")\s+of\s+(" + "|".join(_PALOS_EN) + r")\b"
)


def hash_seccion(id_libro, seccion, texto):
    """Misma formula que juez.hash_seccion: sha256(id|seccion|texto)."""
    return hashlib.sha256(
        ("%s|%s|%s" % (id_libro, seccion, texto)).encode("utf-8")
    ).hexdigest()


def indexar_secciones(secciones):
    """hash_seccion -> seccion (dict con id_libro, seccion, titulo, texto)."""
    idx = {}
    for s in secciones:
        h = hash_seccion(s["id_libro"], s["seccion"], s["texto"])
        idx[h] = s
    return idx


def recuento_por_carta(evidencias):
    """entidad_id -> {total, clasica, moderna}."""
    rec = {}
    for ev in evidencias:
        eid = ev.get("entidad_id")
        if not eid:
            continue
        d = rec.setdefault(eid, {"total": 0, "clasica": 0, "moderna": 0})
        d["total"] += 1
        p = ev.get("periodo")
        if p == "clasica":
            d["clasica"] += 1
        elif p == "moderna":
            d["moderna"] += 1
    return rec


def cartas_sin_clasica(evidencias):
    """Ids del catalogo tarot (78) sin ninguna evidencia de periodo clasica."""
    rec = recuento_por_carta(evidencias)
    faltan = []
    for entrada in cartas.CARTAS_TAROT:
        eid = entrada["id"]
        if rec.get(eid, {}).get("clasica", 0) == 0:
            faltan.append(eid)
    return sorted(faltan)


def clasificar_titulo(titulo, esperado):
    """'real' si el titulo nombra la carta esperada; 'otra' si nombra otra carta
    del tarot; 'neutro' si no nombra ninguna (OCR, leccion, genericos).

    `esperado` es un token en minusculas sin acentos (p. ej. 'sun', 'moon').
    """
    t = cartas.norm(titulo or "")
    if esperado and re.search(r"(?<![a-z])" + re.escape(esperado) + r"(?![a-z])", t):
        return "real"
    for otra in _MAYORES_EN:
        if otra == esperado:
            continue
        if re.search(r"(?<![a-z])" + re.escape(otra) + r"(?![a-z])", t):
            return "otra"
    for otra in _MENORES_EN:
        if re.search(r"(?<![a-z])" + re.escape(otra) + r"(?![a-z])", t):
            return "otra"
    return "neutro"


def auditar_mayor(evidencias, idx, entidad_id, esperado, muestra_max=15):
    """Clasifica las evidencias classicas de un arcano mayor por el titulo de su
    seccion y devuelve conteos + una muestra de hasta `muestra_max` casos."""
    real = otra = neutro = 0
    muestra = []
    for ev in evidencias:
        if ev.get("entidad_id") != entidad_id or ev.get("periodo") != "clasica":
            continue
        sec = idx.get(ev.get("hash_seccion"))
        titulo = sec["titulo"] if sec else "(seccion no indexada)"
        cat = clasificar_titulo(titulo, esperado)
        if cat == "real":
            real += 1
        elif cat == "otra":
            otra += 1
        else:
            neutro += 1
        if len(muestra) < muestra_max:
            muestra.append({"titulo": titulo, "clasificacion": cat})
    return {
        "entidad_id": entidad_id,
        "esperado": esperado,
        "total_clasica": real + otra + neutro,
        "real": real,
        "otra": otra,
        "neutro": neutro,
        "muestra": muestra,
    }


def gap_mapeo_ingles():
    """Demuestra que cartas.py no reconoce las menores en ingles pero si en
    espanol (causa raiz de 0 evidencia clasica en las 56 menores)."""
    ejemplos_en = [
        "Two of Swords", "King of Wands", "Page of Cups", "Ten of Pentacles",
    ]
    ejemplos_es = [
        "Dos de Espadas", "Rey de Bastos", "Sota de Copas", "Diez de Oros",
    ]
    no_rec = [e for e in ejemplos_en if cartas.normalizar_carta(e) is None]
    es_ok = all(cartas.normalizar_carta(e) for e in ejemplos_es)
    return {
        "no_reconoce_ingles": len(no_rec) == len(ejemplos_en),
        "ejemplos_no_reconocidos": no_rec,
        "reconoce_espanol": es_ok,
    }


def secciones_menores_ingles(secciones):
    """Secciones cuyo titulo nombra una menor en ingles (rank of suit)."""
    out = []
    for s in secciones:
        if _MENOR_EN_RE.search(cartas.norm(s.get("titulo", ""))):
            out.append(s)
    return out


# ---------------------------------------------------------------------------
# Runner de solo lectura sobre los datos reales de fase0/libros
# ---------------------------------------------------------------------------

BASE_LIBROS = "/Users/angelgonzalez/fase0/libros"
WAITE_ID = "A.EWaiteThePictorialKeyToTheTarot"


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
                import json
                out.append(json.loads(linea))
            except Exception:
                continue
    return out


def cargar_todo(base=BASE_LIBROS):
    evidencias = _leer_jsonl(os.path.join(base, "evidencias", "evidencias.jsonl"))
    secciones = []
    sec_dir = os.path.join(base, "secciones")
    if os.path.isdir(sec_dir):
        for fn in sorted(os.listdir(sec_dir)):
            if fn.endswith(".jsonl"):
                secciones.extend(_leer_jsonl(os.path.join(sec_dir, fn)))
    return evidencias, secciones


def informe(base=BASE_LIBROS):
    evidencias, secciones = cargar_todo(base)
    idx = indexar_secciones(secciones)
    rec = recuento_por_carta(evidencias)
    tarot = {k: v for k, v in rec.items() if k.startswith("tarot-")}
    sin_clasica = cartas_sin_clasica(evidencias)
    top = sorted(tarot.items(), key=lambda kv: kv[1]["total"], reverse=True)[:10]
    aud20 = auditar_mayor(evidencias, idx, "tarot-mayor-20", "sun")
    aud19 = auditar_mayor(evidencias, idx, "tarot-mayor-19", "moon")
    waite = [s for s in secciones if s.get("id_libro") == WAITE_ID]
    waite_menores = secciones_menores_ingles(waite)
    gap = gap_mapeo_ingles()
    return {
        "total_evidencias": len(evidencias),
        "total_tarot": sum(v["total"] for v in tarot.values()),
        "clasica_tarot": sum(v["clasica"] for v in tarot.values()),
        "moderna_tarot": sum(v["moderna"] for v in tarot.values()),
        "top_cartas": top,
        "n_sin_clasica": len(sin_clasica),
        "sin_clasica_menores": sum(1 for c in sin_clasica if not c.endswith(
            tuple("%02d" % i for i in range(1, 23)))),
        "auditoria_20": aud20,
        "auditoria_19": aud19,
        "waite_secciones": len(waite),
        "waite_menores_titulo": len(waite_menores),
        "waite_menores_titulos": [s["titulo"] for s in waite_menores][:50],
        "gap": gap,
    }


def main():
    inf = informe()
    print("Total evidencias: %d (tarot %d | clasica %d | moderna %d)" % (
        inf["total_evidencias"], inf["total_tarot"],
        inf["clasica_tarot"], inf["moderna_tarot"]))
    print("Cartas tarot sin evidencia clasica: %d" % inf["n_sin_clasica"])
    print("Top 10 cartas por total:")
    for eid, v in inf["top_cartas"]:
        print("  %s total=%d clasica=%d moderna=%d" % (
            eid, v["total"], v["clasica"], v["moderna"]))
    for tag, aud in (("mayor-20 (Sol)", inf["auditoria_20"]),
                    ("mayor-19 (Luna)", inf["auditoria_19"])):
        print("Auditoria %s: total_clasica=%d real=%d otra=%d neutro=%d" % (
            tag, aud["total_clasica"], aud["real"], aud["otra"], aud["neutro"]))
    print("Waite: %d secciones, %d con titulo de menor en ingles" % (
        inf["waite_secciones"], inf["waite_menores_titulo"]))
    print("Gap mapeo ingles: no_reconoce=%s reconoce_es=%s no_rec=%s" % (
        inf["gap"]["no_reconoce_ingles"], inf["gap"]["reconoce_espanol"],
        inf["gap"]["ejemplos_no_reconocidos"]))


if __name__ == "__main__":
    main()
