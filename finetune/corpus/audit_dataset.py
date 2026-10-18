#!/usr/bin/env python3
"""Auditoría de calidad del dataset ShareGPT: puntúa cada par y escribe ficheros nuevos.

Nunca modifica los ficheros de entrada. Autónomo: solo stdlib (no depende de la API
interna de build_dataset, translate_dataset ni validate_synthetic).

Uso:
  .venv/bin/python corpus/audit_dataset.py --in train.jsonl [--in val.jsonl] \
      --out-dir /tmp/t8/ [--min-score 0.6] [--license strict]

Salidas en --out-dir:
  <nombre>.clean.jsonl    pares con puntuación >= umbral (formato ShareGPT intacto)
  <nombre>.rejected.jsonl filas rechazadas con _score y _reasons
  report.json / report.md informe en español (bloques, cobertura, longitudes, ejemplos)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

# Pesos de cada criterio: score = 1 - suma(pesos de motivos) + bonus lectura (topes 0..1)
PESOS = {
    "prompt_generico": 0.35,
    "residuos": 0.45,
    "dominio": 0.45,
    "idioma": 0.35,
    "longitud": 0.25,
    "repeticion": 0.30,
    "duplicado": 1.00,
    "licencia": 0.50,
    "bonus_lectura": 0.15,
}

LONG_MIN = 200
LONG_MAX = 4000

ARCANOS_MAYORES = [
    "El Loco", "El Mago", "La Sacerdotisa", "La Emperatriz", "El Emperador",
    "El Hierofante", "Los Enamorados", "El Carro", "La Fuerza", "El Ermitaño",
    "La Rueda de la Fortuna", "La Justicia", "El Colgado", "La Muerte",
    "La Templanza", "El Diablo", "La Torre", "La Estrella", "La Luna", "El Sol",
    "El Juicio", "El Mundo",
]

SIGNOS = [
    "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra", "Escorpio",
    "Sagitario", "Capricornio", "Acuario", "Piscis",
]

NUMEROS = {str(n): w for n, w in zip(
    range(1, 10), ["uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"])}

# Términos fuertes: dominio claro de la adivinación
FUERTES = [
    "tarot", "tarotista", "arcano", "arcana", "arcanos", "arcanas",
    "astrología", "astrólogo", "astróloga", "astral", "numerología",
    "quiromancia", "quiromante", "hexagrama", "hexagramas", "runa", "runas",
    "rúnico", "rúnicos", "ascendente", "zodiaco", "carta astral", "camino de vida",
    "i ching", "iching", "oráculo chino",
    "aries", "tauro", "géminis", "cáncer", "virgo", "escorpio", "escorpión",
    "sagitario", "capricornio", "acuario", "piscis",
]

# Términos débiles cotidianos: solos no demuestran dominio
DEBILES = [
    "sol", "luna", "casa", "mano", "carta", "leo", "libra", "destino",
    "estrella", "rueda", "muerte", "diablo", "fuerza", "torre", "mundo",
    "juicio", "justicia", "emperador", "emperatriz", "loco", "mago",
    "sacerdotisa", "ermitaño",
]

# Nombres de arcanos ambiguos NO entran aquí (el sol/la luna son cotidianos);
# solo los inequívocos precedidos de artículo cuentan como fuertes
_ARCANOS_ART = re.compile(
    r"\b(?:el|la|los|las)\s+(?:loco|mago|sacerdotisa|emperatriz|emperador|hierofante|"
    r"enamorados|carro|ermitaño|rueda de la fortuna|colgado|templanza)\b", re.IGNORECASE)

RE_SECCION = re.compile(r"\bsecci[oó]n\s*\d+", re.IGNORECASE)
RE_CAPITULO = re.compile(r"\bcap[ií]tulo\s*\d+", re.IGNORECASE)
RE_PROMO = re.compile(
    r"\b(curso|precio|reserva|compra|oferta|descuento|matr[ií]cula)\b", re.IGNORECASE)

# Residuos de scraping/wiki/newsletter: cada patrón es un motivo de descarte
RESIDUOS = [
    re.compile(r"&action=edit"),
    re.compile(r"cite_(?:note|ref)", re.IGNORECASE),
    re.compile(r"\[\s*\d+\s*\]\s*\(|\[\[\d+\]\]"),
    re.compile(r"\[[^\]]*\]\([^)\n]*$|\[[^\]]*\]\(\s*\)", re.MULTILINE),
    re.compile(r"^\s*\|.*-{3,}", re.MULTILINE),
    re.compile(r"please\s+enable\s+javascript|activa\s+(?:el\s+)?javascript", re.IGNORECASE),
    re.compile(r"suscr[ií]bete|newsletter|bolet[ií]n\s+(?:informativo|semanal|diario)", re.IGNORECASE),
    re.compile(r"\bcookies?\b|usamos\s+cookies", re.IGNORECASE),
    re.compile(r"reserva\s+ahora|compra\s+ahora|curso\s+gratis|precio\s+especial|oferta\s+especial", re.IGNORECASE),
]

# Palabras funcionales españolas (ojo: «no» es español, no inglés)
ES_FUNC = set("""de la que el en y a los del se las por un con no una su para es lo como más
pero sus le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde
quien desde todo nos durante todos uno les ni contra otros ese eso antes él mí ti conmigo
contigo nuestro nuestra mío tuya cada cual cómo aquí allí allá luego entonces así aunque
sino mientras según tras hacia demás tanto cuanto mucha mucho otras mismo misma mismos mismas""".split())

# Extranjerismos distintivos (evitan solapamientos con el español)
EN_DIST = set("the and is was of this that with you your not but have had from they will are "
              "it his her our we can would there their what which when who how why about into "
              "over just like get do does did him she its them these those here then than "
              "because for all any some most now new one two three been".split())
PT_DIST = set("não são você vocês isso essa nosso nossa meus minhas estão muito muita foi foram "
              "temos vou ela ele eles elas".split())
IT_DIST = set("non sono questo questa questi queste degli delle dei molto ancora sempre gli è "
              "per come ma più anche senza tutto ogni".split())

BLOQUES_PALABRAS = [
    ("tarot", ["tarot", "arcano", "tirada", "arcanos"]),
    ("astrología", ["astrolog", "astral", "signo", "zodiaco", "ascendente", "planeta"]),
    ("numerología", ["numerolog", "camino de vida", "número del alma", "vibración"]),
    ("quiromancia", ["quiromanc", "líneas de la mano", "montes de la mano"]),
    ("i ching", ["i ching", "iching", "hexagrama", "oráculo chino"]),
    ("runas", ["runa", "futhark", "rúnico"]),
    ("ocultismo", ["ocultismo", "ritual", "hechizo", "magia", "amuleto"]),
]


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñ]+", texto.lower())


def extraer(fila: dict) -> tuple[str, str]:
    """Devuelve (prompt, respuesta) de una fila ShareGPT."""
    prompt = respuesta = ""
    for c in fila.get("conversations", []):
        if c.get("from") == "human":
            prompt = c.get("value", "")
        elif c.get("from") == "gpt":
            respuesta = c.get("value", "")
    return prompt, respuesta


def _tema(prompt: str) -> str:
    """Desnuda el prompt de fórmulas de pregunta para quedarse con el tema."""
    t = prompt.strip().strip("?¡!«»\"' ")
    t = re.sub(r"(?i)^(?:¿)?\s*(?:qué|que)\s+(?:significa|significan|es|son|son\s+)?\s*", "", t)
    t = re.sub(r"(?i)^(?:explica|cu[eé]ntame|h[aá]blame\s+de|dime|describe)\s+(?:en\s+detalle:?\s*)?", "", t)
    return t.strip(" ?:.\"'»")


def _contiene_fuerte(texto: str) -> bool:
    palabras = set(_palabras(texto))
    if _ARCANOS_ART.search(texto):
        return True
    for f in FUERTES:
        if " " in f:
            if f in texto.lower():
                return True
        elif f in palabras:
            return True
    return False


def criterio_prompt_generico(prompt: str) -> bool:
    if RE_SECCION.search(prompt) or RE_CAPITULO.search(prompt):
        return True
    if RE_PROMO.search(prompt):
        return True
    tema = _tema(prompt)
    if not tema:
        return True
    if len(_palabras(tema)) <= 1 and not _contiene_fuerte(tema):
        return True
    return False


def criterio_residuos(texto: str) -> bool:
    return any(rx.search(texto) for rx in RESIDUOS)


def criterio_dominio(texto: str) -> bool:
    """True si hay términos fuertes; los débiles solos no cuentan."""
    return _contiene_fuerte(texto)


def criterio_idioma(texto: str) -> bool:
    """True si parece mezcla con inglés/italiano/portugués (penaliza)."""
    palabras = _palabras(texto)
    es = sum(1 for w in palabras if w in ES_FUNC)
    extranjero = sum(1 for w in palabras if w in EN_DIST or w in PT_DIST or w in IT_DIST)
    if es == 0 and extranjero >= 2:
        return True
    return extranjero >= 3 and extranjero > 0.4 * es


def criterio_longitud(respuesta: str) -> bool:
    """True si la respuesta está fuera del rango 200-4000 caracteres."""
    return len(respuesta) < LONG_MIN or len(respuesta) > LONG_MAX


def _shingles(texto: str, k: int = 5) -> set:
    ws = _palabras(texto)
    return {tuple(ws[i:i + k]) for i in range(len(ws) - k + 1)}


def criterio_repeticion(texto: str) -> bool:
    """n-gramas (5 palabras) repetidos en exceso dentro del propio texto."""
    ws = _palabras(texto)
    if len(ws) < 15:
        return False
    sh = Counter(tuple(ws[i:i + 5]) for i in range(len(ws) - 4))
    max_rep = max(sh.values())
    repetidas = sum(c for c in sh.values() if c >= 2)
    return max_rep >= 3 or repetidas / len(sh) > 0.5


def clasificar_tipo(prompt: str, respuesta: str, fila: dict) -> str:
    """lectura (habla al consultante o es sintética), enciclopedico u otros."""
    if fila.get("bloque"):
        return "lectura"
    segunda = len(re.findall(r"\b(?:te|tu|tú|ti)\b", respuesta))
    if segunda >= 2:
        return "lectura"
    if _contiene_fuerte(prompt + " " + respuesta):
        return "enciclopedico"
    return "otros"


def inferir_bloque(fila: dict, texto: str) -> str:
    if fila.get("bloque"):
        return str(fila["bloque"]).split("_")[0].lower()
    t = texto.lower()
    for nombre, kws in BLOQUES_PALABRAS:
        if any(k in t for k in kws):
            return nombre
    return "otros"


def _licencia_permitida(fila: dict) -> bool | None:
    """None si no aplica; False si license_filter la rechaza."""
    if not fila.get("source"):
        return None
    try:
        import license_filter
    except ImportError:
        return None
    return license_filter.is_allowed(fila["source"])


def puntuar(fila: dict, licencia: str | None = None) -> tuple[float, list[str], str]:
    """Puntúa un par: (score 0-1, motivos de penalización, tipo)."""
    prompt, respuesta = extraer(fila)
    motivos: list[str] = []
    if criterio_prompt_generico(prompt):
        motivos.append("prompt_generico")
    if criterio_residuos(prompt + "\n" + respuesta):
        motivos.append("residuos")
    if not criterio_dominio(prompt + " " + respuesta):
        motivos.append("dominio")
    if criterio_idioma(respuesta):
        motivos.append("idioma")
    if criterio_longitud(respuesta):
        motivos.append("longitud")
    if criterio_repeticion(respuesta):
        motivos.append("repeticion")
    if licencia == "strict" and _licencia_permitida(fila) is False:
        motivos.append("licencia")
    tipo = clasificar_tipo(prompt, respuesta, fila)
    score = 1.0 - sum(PESOS[m] for m in motivos)
    if tipo == "lectura":
        score += PESOS["bonus_lectura"]
    return max(0.0, min(1.0, score)), motivos, tipo


def _minhash(shingles: set, n: int = 64) -> list[int]:
    return [min((hash((s, sh)) for sh in shingles), default=0) for s in range(n)]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def auditar_pares(filas: list[dict], min_score: float = 0.6,
                 licencia: str | None = None) -> list[dict]:
    """Puntúa todas las filas juntas (los duplicados se detectan entre TODAS)."""
    resultados: list[dict] = []
    vistos: set[str] = set()
    shingles: list[set] = []
    for fila in filas:
        prompt, respuesta = extraer(fila)
        score, motivos, tipo = puntuar(fila, licencia)
        texto_norm = " ".join(_palabras(prompt + "\n" + respuesta))
        exacto = hashlib.sha1(texto_norm.encode("utf-8")).hexdigest()
        if exacto in vistos:
            motivos = motivos + ["duplicado"]
            score = 0.0
        vistos.add(exacto)
        shingles.append(_shingles(prompt + "\n" + respuesta))
        resultados.append({
            "fila": fila,
            "score": score,
            "motivos": motivos,
            "tipo": tipo,
            "bloque": inferir_bloque(fila, prompt + " " + respuesta),
            "aceptado": score >= min_score,
        })

    # Casi-duplicados: MinHash con bandas + verificación Jaccard >= 0.9
    n_bandas, filas_banda = 8, 8
    firmas = [_minhash(s) for s in shingles]
    cubos: dict[tuple[int, int], list[int]] = {}
    for i, f in enumerate(firmas):
        for b in range(n_bandas):
            cubos.setdefault((b, hash(tuple(f[b * filas_banda:(b + 1) * filas_banda]))), []).append(i)
    for idxs in cubos.values():
        if len(idxs) < 2:
            continue
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                i, j = idxs[a_pos], idxs[b_pos]
                if _jaccard(shingles[i], shingles[j]) >= 0.9:
                    r = resultados[j]
                    if "duplicado" not in r["motivos"]:
                        r["motivos"] = r["motivos"] + ["duplicado"]
                        r["score"] = 0.0
                        r["aceptado"] = False
    return resultados


def _percentil(vals: list[int], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))
    return float(s[k])


def construir_informe(resultados: list[dict], min_score: float, seed: int = 42) -> dict:
    """Informe global en español: bloques, cobertura, longitudes y ejemplos."""
    aceptados = [r for r in resultados if r["aceptado"]]
    rechazados = [r for r in resultados if not r["aceptado"]]

    bloques: dict[str, dict] = {}
    for r in resultados:
        b = bloques.setdefault(r["bloque"], {
            "total": 0, "supervivientes": 0, "motivos": Counter(), "tipos": Counter()})
        b["total"] += 1
        b["tipos"][r["tipo"]] += 1
        if r["aceptado"]:
            b["supervivientes"] += 1
        else:
            for m in r["motivos"]:
                b["motivos"][m] += 1
    for b in bloques.values():
        b["pct"] = round(100.0 * b["supervivientes"] / b["total"], 1) if b["total"] else 0.0
        b["motivos"] = dict(b["motivos"].most_common())
        b["tipos"] = dict(b["tipos"])

    cobertura: dict[str, dict[str, int]] = {"arcanos": {}, "signos": {}, "numeros": {}}
    for r in aceptados:
        prompt, respuesta = extraer(r["fila"])
        t = (prompt + " " + respuesta).lower()
        for a in ARCANOS_MAYORES:
            cobertura["arcanos"][a] = cobertura["arcanos"].get(a, 0) + (1 if a.lower() in t else 0)
        for s in SIGNOS:
            cobertura["signos"][s] = cobertura["signos"].get(s, 0) + (1 if s.lower() in t else 0)
        for d, palabra in NUMEROS.items():
            cobertura["numeros"][d] = cobertura["numeros"].get(d, 0) + (
                1 if (d in t or palabra in t) else 0)
    huecos = {k: sorted(n for n, c in v.items() if c < 10) for k, v in cobertura.items()}

    longitudes = [len(extraer(r["fila"])[1]) for r in aceptados]
    rnd = random.Random(seed)
    ej_ok = rnd.sample(aceptados, min(10, len(aceptados)))
    ej_no = rnd.sample(rechazados, min(10, len(rechazados)))

    return {
        "umbral": min_score,
        "total": len(resultados),
        "aceptados": len(aceptados),
        "rechazados": len(rechazados),
        "pct_supervivencia": round(100.0 * len(aceptados) / len(resultados), 1) if resultados else 0.0,
        "bloques": bloques,
        "cobertura": cobertura,
        "huecos": huecos,
        "longitudes": {
            "min": min(longitudes) if longitudes else 0,
            "p10": _percentil(longitudes, 10),
            "mediana": _percentil(longitudes, 50),
            "media": round(sum(longitudes) / len(longitudes), 1) if longitudes else 0.0,
            "p90": _percentil(longitudes, 90),
            "max": max(longitudes) if longitudes else 0,
        },
        "ejemplos_aceptados": [
            {"prompt": extraer(r["fila"])[0][:160], "score": round(r["score"], 3),
             "bloque": r["bloque"], "tipo": r["tipo"]} for r in ej_ok
        ],
        "ejemplos_rechazados": [
            {"prompt": extraer(r["fila"])[0][:160], "score": round(r["score"], 3),
             "motivos": r["motivos"], "bloque": r["bloque"]} for r in ej_no
        ],
    }


def informe_md(informe: dict) -> str:
    """Versión markdown del informe, en español."""
    lineas = [
        "# Informe de auditoría del dataset",
        "",
        f"- **Total de pares:** {informe['total']}",
        f"- **Supervivientes (score ≥ {informe['umbral']}):** {informe['aceptados']} "
        f"({informe['pct_supervivencia']} %)",
        f"- **Rechazados:** {informe['rechazados']}",
        "",
        "## Reparto por bloque",
        "",
        "| Bloque | Total | Supervivientes | % | Motivos más frecuentes |",
        "|---|---|---|---|---|",
    ]
    for nombre, b in sorted(informe["bloques"].items(), key=lambda kv: -kv[1]["total"]):
        motivos = ", ".join(f"{m} ({c})" for m, c in list(b["motivos"].items())[:5]) or "—"
        lineas.append(f"| {nombre} | {b['total']} | {b['supervivientes']} | {b['pct']} % | {motivos} |")
    tipos = Counter()
    for b in informe["bloques"].values():
        tipos.update(b["tipos"])
    lineas += [
        "",
        "## Tipo de par (objetivo del modelo: hacer lecturas)",
        "",
        "| Tipo | Pares |",
        "|---|---|",
    ]
    for t in ("lectura", "enciclopedico", "otros"):
        lineas.append(f"| {t} | {tipos.get(t, 0)} |")
    lineas += ["", "## Cobertura de supervivientes", ""]
    for grupo, etiqueta in (("arcanos", "22 arcanos mayores"), ("signos", "12 signos"),
                          ("numeros", "números 1-9")):
        counts = informe["cobertura"][grupo]
        faltan = informe["huecos"].get(grupo, [])
        resumen = ", ".join(f"{n}: {c}" for n, c in counts.items())
        lineas.append(f"### {etiqueta}")
        lineas.append("")
        lineas.append(resumen)
        lineas.append("")
        if faltan:
            lineas.append(f"**Huecos (< 10 pares):** {', '.join(faltan)}")
        else:
            lineas.append("Sin huecos: todos cubiertos con 10 o más pares.")
        lineas.append("")
    lg = informe["longitudes"]
    lineas += [
        "## Distribución de longitudes de respuesta (aceptados)",
        "",
        f"min {lg['min']} · p10 {lg['p10']:.0f} · mediana {lg['mediana']:.0f} · "
        f"media {lg['media']} · p90 {lg['p90']:.0f} · max {lg['max']}",
        "",
        "## 10 ejemplos aceptados",
        "",
    ]
    for e in informe["ejemplos_aceptados"]:
        lineas.append(f"- [{e['score']}] ({e['bloque']}/{e['tipo']}) {e['prompt']}")
    lineas += ["", "## 10 ejemplos rechazados", ""]
    for e in informe["ejemplos_rechazados"]:
        lineas.append(f"- [{e['score']}] ({e['bloque']}) {', '.join(e['motivos'])} — {e['prompt']}")
    lineas.append("")
    return "\n".join(lineas)


def leer_jsonl(ruta: Path) -> list[dict]:
    filas = []
    with ruta.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                filas.append(json.loads(linea))
    return filas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Auditoría de calidad del dataset ShareGPT.")
    ap.add_argument("--in", dest="ins", action="append", required=True, type=Path,
                   help="fichero .jsonl de entrada (repetible)")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--min-score", type=float, default=0.6)
    ap.add_argument("--license", default="", choices=["", "strict"],
                   help="strict: aplica license_filter.is_allowed si el módulo existe")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    todas: list[dict] = []
    origenes: list[str] = []
    for inp in args.ins:
        filas = leer_jsonl(inp)
        todas.extend(filas)
        origenes.extend([inp.stem] * len(filas))

    resultados = auditar_pares(todas, args.min_score, args.license or None)

    limpias: dict[str, list[dict]] = {}
    rechazadas: dict[str, list[dict]] = {}
    for origen, r in zip(origenes, resultados):
        if r["aceptado"]:
            limpias.setdefault(origen, []).append(r["fila"])
        else:
            copia = dict(r["fila"])
            copia["_score"] = round(r["score"], 3)
            copia["_reasons"] = r["motivos"]
            rechazadas.setdefault(origen, []).append(copia)
    escritos = set()
    for origen in origenes:
        if origen in escritos:
            continue
        escritos.add(origen)
        with (args.out_dir / f"{origen}.clean.jsonl").open("w", encoding="utf-8") as f:
            for fila in limpias.get(origen, []):
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        with (args.out_dir / f"{origen}.rejected.jsonl").open("w", encoding="utf-8") as f:
            for fila in rechazadas.get(origen, []):
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")

    informe = construir_informe(resultados, args.min_score, args.seed)
    (args.out_dir / "report.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "report.md").write_text(informe_md(informe), encoding="utf-8")
    print(f"[ok] {informe['aceptados']}/{informe['total']} pares superviven "
          f"({informe['pct_supervivencia']} %) -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
