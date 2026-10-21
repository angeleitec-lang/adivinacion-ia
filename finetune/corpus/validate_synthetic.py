#!/usr/bin/env python3
"""Valida y deduplica los pares sintéticos generados (formato ShareGPT).

Puertas: idioma español, longitud, boilerplate, repetición, eco de la pregunta,
coherencia con los datos del prompt y duplicados exactos/casi exactos.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from translate_dataset import detect_language

JUNK = (
    "sacred-texts", "j.b. hare", "press the reload button", "botón recargar",
    "please enable javascript", "javascript enabled", "javascript habilitado",
    "for entertainment purposes only", "solo con fines de entretenimiento",
    "lorem ipsum", "cookie policy", "política de cookies",
)

CARD_RE = re.compile(r"Carta[s]?:\s*([^(\n]+?)\s*(?:\(|\.|$)", re.I)
SIGN_RE = re.compile(r"(?:Signo solar|Ascendente|Luna|Sol)\s*:?\s*(?:en\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", re.I)
NUM_RE = re.compile(
    r"(?:Camino de vida|Número|Destino|Alma|Personalidad|Año personal)"
    r"(?:\s*\([^)]*\))?\s*:?\s*(\d{1,2})",
    re.I,
)
QUESTION_RE = re.compile(r'Pregunta del consultante:\s*"([^"]+)"', re.I)
# Marcas del generador antiguo (texto sin tildes): si aparecen, la fila se descarta.
SIN_TILDES_MARCAS = (
    "espanol", "que energia", "cual es el tema", "proposito", "astrologa ",
    "numerologa", "interpretacion", "anio personal", "empatia",
)
# Reconoce «Carta: X (o)», «Carta N: X (o)» y líneas de tirada «- posición: X (o)».
CARTA_LINEA_RE = re.compile(
    r"(?:Carta(?:\s*\d+)?\s*:|[-•]\s*[^\n:]+?:)\s*([^(\n]+?)\s*\((invertid[ao]|al derecho)\)",
    re.I,
)
ARTICULOS = ("el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas ")


def norm(texto: str) -> str:
    """Minúsculas, sin tildes (NFKD) y sin signos: base de toda comparación."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texto).split())


def _sin_articulo(nombre_norm: str) -> str:
    for art in ARTICULOS:
        if nombre_norm.startswith(art):
            return nombre_norm[len(art):]
    return nombre_norm


def extraer_cartas(prompt: str) -> list:
    """[(nombre, orientacion)] con orientacion en {"derecho", "invertida"}."""
    cartas = []
    for m in CARTA_LINEA_RE.finditer(prompt):
        nombre = m.group(1).strip().strip(".").strip()
        orient = "invertida" if m.group(2).lower().startswith("invertid") else "derecho"
        if nombre and len(nombre) > 2:
            cartas.append((nombre, orient))
    return cartas


def words(text: str) -> list[str]:
    text = re.sub(r"[^\wáéíóúñü]+", " ", text.lower())
    return text.split()


def normalize(text: str) -> str:
    return " ".join(words(text))


def sha(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def near_key(text: str) -> tuple:
    w = words(text)
    if len(w) < 8:
        return tuple(w)
    picks = [w[int(len(w) * f)] for f in (0.1, 0.5, 0.9)]
    mids = [w[min(len(w) - 1, int(len(w) * f) + 1)] for f in (0.1, 0.5, 0.9)]
    return tuple(picks + mids)


# --- Casi-duplicados: MinHash + LSH (solo stdlib, determinista) ---
_MHASH_P = (1 << 61) - 1
_rng = random.Random(20261018)
_MHASH_A = [_rng.randrange(1, _MHASH_P) for _ in range(64)]
_MHASH_B = [_rng.randrange(0, _MHASH_P) for _ in range(64)]


def shingles(texto: str, k: int = 5) -> set:
    """Conjunto de hashes estables (hashlib) de k-gramas de palabras normalizadas."""
    w = norm(texto).split()
    if not w:
        return set()
    if len(w) < k:
        grams = [" ".join(w)]
    else:
        grams = [" ".join(w[i:i + k]) for i in range(len(w) - k + 1)]
    return {
        int.from_bytes(hashlib.blake2b(g.encode("utf-8"), digest_size=8).digest(), "big")
        for g in grams
    }


def minhash(sh: set, n: int = 64) -> tuple:
    """Firma MinHash con n funciones (a*x + b) % p de constantes fijas."""
    if not sh:
        return tuple()
    return tuple(
        min((_MHASH_A[i] * x + _MHASH_B[i]) % _MHASH_P for x in sh)
        for i in range(n)
    )


class IndiceCasiDuplicados:
    """LSH por bandas (16 bandas x 4 filas) sobre firmas MinHash.

    `buscar` devuelve True si algún candidato alcanza un Jaccard estimado >= 0,9.
    """

    def __init__(self, n: int = 64, bandas: int = 16, filas: int = 4, umbral: float = 0.9):
        self.n = n
        self.bandas = bandas
        self.filas = filas
        self.umbral = umbral
        self.sigs: dict = {}
        self.cubetas: dict = defaultdict(set)

    def _clave(self, banda: int, sig: tuple) -> bytes:
        crudo = "|".join(str(x) for x in sig[banda * self.filas:(banda + 1) * self.filas])
        return hashlib.blake2b(crudo.encode("utf-8"), digest_size=8).digest()

    def add(self, id_: str, texto: str) -> None:
        sig = minhash(shingles(texto), self.n)
        self.sigs[id_] = sig
        for b in range(self.bandas):
            self.cubetas[(b, self._clave(b, sig))].add(id_)

    def buscar(self, texto: str) -> bool:
        sig = minhash(shingles(texto), self.n)
        if not sig:
            return False
        candidatos: set = set()
        for b in range(self.bandas):
            candidatos |= self.cubetas.get((b, self._clave(b, sig)), set())
        for cid in candidatos:
            otra = self.sigs[cid]
            if len(otra) != len(sig):
                continue
            acuerdo = sum(1 for a, c in zip(sig, otra) if a == c) / len(sig)
            if acuerdo >= self.umbral:
                return True
        return False


def repetition_ratio(text: str, n: int = 12) -> float:
    w = words(text)
    if len(w) < n * 3:
        return 0.0
    grams = Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    top = grams.most_common(1)[0][1] if grams else 0
    return top / max(1, len(w) - n + 1)


def answer_of(row: dict) -> str:
    for c in row.get("conversations", []):
        if c.get("from") == "gpt":
            return c.get("value", "")
    return ""


def human_of(row: dict) -> str:
    for c in row.get("conversations", []):
        if c.get("from") == "human":
            return c.get("value", "")
    return ""


def system_of(row: dict) -> str:
    for c in row.get("conversations", []):
        if c.get("from") == "system":
            return c.get("value", "")
    return ""


def turnos_de(row: dict) -> list:
    """[(human, gpt), ...] siguiendo el orden de conversations."""
    pares = []
    humano = None
    for c in row.get("conversations", []):
        origen = c.get("from")
        if origen == "human":
            humano = c.get("value", "")
        elif origen == "gpt" and humano is not None:
            pares.append((humano, c.get("value", "")))
            humano = None
    return pares


# Funciones vacías españolas (normalizadas, sin tildes) para medir contenido.
STOP_CONTENIDO = frozenset("""
de la que el en y a los del se las un por con no una su para es al lo como
mas pero sus le ya o si porque esta entre cuando muy sin sobre tambien me hasta
hay donde quien desde todo nos durante todos uno les ni contra otros ese eso
ante ellos e esto mi antes algunos yo ha han has fue fueron ser sido estar esta
estan estaba este estos estas esa esos esas aquel aquella lo mismo puede pueden
hace hacer hizo hay dia cosa vez veces asi alla aqui alli
""".split())


def _contenido(texto: str) -> set:
    return {w for w in norm(texto).split()
            if w not in STOP_CONTENIDO and len(w) >= 3}


def _copia_turno1(g1: str, g2: str) -> bool:
    """True si g2 repite demasiado a g1 (Jaccard > 0,6 o > 50% de frases)."""
    w1 = set(norm(g1).split())
    w2 = set(norm(g2).split())
    if not w1 or not w2:
        return False
    if len(w1 & w2) / len(w1 | w2) > 0.6:
        return True
    frases = [norm(s) for s in re.split(r"[.!?]+", g2)]
    frases = [f for f in frases if len(f.split()) >= 4]
    if not frases:
        return False
    n1 = norm(g1)
    copiadas = sum(1 for f in frases if f in n1)
    return copiadas / len(frases) > 0.5


def _sin_hilo(g1: str, g2: str) -> bool:
    """True si g2 no comparte ninguna palabra de contenido con g1."""
    return len(_contenido(g1) & _contenido(g2)) < 1


# Marcas que reconocen una carta invertida en la respuesta (texto normalizado).
INVERT_RECONOC = (
    "invertid", "al reves", "bloque", "sombra", "resist", "retraso", "interior",
)
# Marcas que afirman inversión (para contradecir una carta al derecho).
INVERT_AFIRMA = ("invertid", "al reves")


def orientacion_ok(prompt: str, answer: str) -> bool:
    """Si el prompt dice (invertida) la respuesta debe reconocerlo; si dice
    (al derecho) no debe afirmar inversión junto al nombre de la carta."""
    cartas = extraer_cartas(prompt)
    if not cartas:
        return True
    na = norm(answer)
    for nombre, orient in cartas:
        token = _sin_articulo(norm(nombre))
        if not token:
            continue
        if orient == "invertida":
            if not any(marca in na for marca in INVERT_RECONOC):
                return False
        else:
            for m in re.finditer(r"\b" + re.escape(token) + r"\b", na):
                ventana = na[max(0, m.start() - 30): m.end() + 30]
                if any(f in ventana for f in INVERT_AFIRMA):
                    return False
    return True


IA_META_FRASES = (
    "como modelo de lenguaje",
    "como inteligencia artificial",
    "no tengo acceso a",
    "no puedo ayudarte con eso",
)


def eco_prompt(prompt: str, answer: str, min_run: int = 25) -> bool:
    """True si la respuesta copia >= min_run palabras consecutivas del prompt."""
    pw = norm(prompt).split()
    aw = norm(answer).split()
    if len(pw) < min_run or len(aw) < min_run:
        return False
    gramas = {tuple(pw[i:i + min_run]) for i in range(len(pw) - min_run + 1)}
    for i in range(len(aw) - min_run + 1):
        if tuple(aw[i:i + min_run]) in gramas:
            return True
    return False


def ia_meta(answer: str) -> bool:
    """True si la respuesta delata ser una IA (frases hechas o etiquetas de razonamiento)."""
    raw = answer.lower()
    if any(marca in raw for marca in ("<think>", "</think>", "<thinking>", "</thinking>")):
        return True
    if "<|im_start|>" in raw or "<|im_end|>" in raw:
        return True
    na = norm(answer)
    return any(f in na for f in IA_META_FRASES)


def _menciona(na: str, token_norm: str) -> bool:
    return bool(token_norm) and re.search(r"\b" + re.escape(token_norm) + r"\b", na) is not None


EJES_ASTRALES = ("Sol", "Luna", "Ascendente")
CALCULOS_NUM_CLAVES = (
    "camino_de_vida", "expresion", "alma", "personalidad", "anio_personal",
)


def signos_de_calculos(calculos: dict) -> list:
    """Signos de los ejes (Sol/Luna/Ascendente) de las cartas astrales en `calculos`.

    Misma fuente canónica que `fase1_prompts.verificar_lectura` (carta_natal,
    carta_a, carta_b), sin depender del texto del prompt (DESAJUSTE D7).
    El Ascendente puede venir en `planetas["Ascendente"]` o en la clave
    `ascendente` de la carta (estructura real de las cartas natales).
    """
    signos = []
    for clave in ("carta_natal", "carta_a", "carta_b"):
        carta = calculos.get(clave) or {}
        planetas = carta.get("planetas") or {}
        for eje in EJES_ASTRALES:
            dato = planetas.get(eje)
            if not dato and eje == "Ascendente":
                dato = carta.get("ascendente")
            signo = (dato or {}).get("signo")
            if signo:
                signos.append(norm(signo))
    return list(dict.fromkeys(signos))


def numeros_de_calculos(calculos: dict) -> list:
    """Números de la tabla de numerología en `calculos` (fuente canónica, D7)."""
    tabla = calculos.get("numerologia") or {}
    out = []
    for clave in CALCULOS_NUM_CLAVES:
        valor = tabla.get(clave)
        if isinstance(valor, int):
            out.append(str(valor))
    return list(dict.fromkeys(out))


def grounding(prompt: str, answer: str, calculos: dict | None = None) -> bool:
    """Exige que la respuesta mencione los datos de la tarea.

    Fuente de signos y números (DESAJUSTE D7, alineado en T75):
    - Si la fila trae `calculos` (los datos deterministas que consumió
      `fase1_prompts.verificar_lectura`), signos y números se leen de ahí,
      en vez de extraerse del texto del prompt, donde los regex pierden
      formatos (p. ej. «Año personal 2026: 5» extraía «20») y el verificador
      ni los mira.
    - Sin `calculos` se mantiene el comportamiento heredado: extracción del
      texto del prompt con SIGN_RE/NUM_RE.
    Criterio invariable: cartas del prompt, todas; signos y números, al menos
    2/3 mencionados. Las cartas se leen siempre del texto (la fila ShareGPT
    no las trae en `calculos`).
    """
    na = norm(answer)
    cartas = extraer_cartas(prompt)
    for nombre, _ in cartas:
        if not _menciona(na, _sin_articulo(norm(nombre))):
            return False
    # Una carta que no existe en ninguno de los dos sistemas invalida la lectura,
    # aunque la tirada se mencione correctamente (mismo control que el verificador).
    try:
        import cartas as _cartas
        import fase1_prompts as _fp
        universo = list(_cartas.CARTAS_TAROT) + list(_cartas.NAIPES_ESPANOLES)
        dibujadas = {_fp._norm(_fp._sin_articulo(n)) for n, _ in cartas}
        conocidos = _fp._nombres_conocidos(universo, dibujadas)
        if _fp._cartas_inventadas(answer, conocidos):
            return False
    except ImportError:
        pass
    if calculos:
        signos = signos_de_calculos(calculos)
        numeros = numeros_de_calculos(calculos)
    else:
        signos = list(dict.fromkeys(norm(m.group(1)) for m in SIGN_RE.finditer(prompt)))
        numeros = list(dict.fromkeys(m.group(1) for m in NUM_RE.finditer(prompt)))
    if signos:
        menc = sum(1 for s in signos if _menciona(na, s))
        if menc / len(signos) < 2 / 3:
            return False
    if numeros:
        menc = sum(1 for n in numeros if _menciona(na, n))
        if menc / len(numeros) < 2 / 3:
            return False
    return True


def _validar_multiturno(pares: list, args, bloque: str | None,
                       calculos: dict | None = None) -> tuple[bool, str]:
    for i, (humano, gpt) in enumerate(pares):
        if not humano or not gpt:
            return False, "sin_turnos"
        if len(gpt) < args.min_chars:
            return False, "turno2_corto" if i == 1 else "corto"
        if len(gpt) > args.max_chars:
            return False, "largo"
        low = gpt.lower()
        if any(m in low for m in JUNK):
            return False, "boilerplate"
        lang = detect_language(gpt)
        if lang not in ("es", "mixed"):
            return False, f"idioma_{lang}"
        if repetition_ratio(gpt) > args.max_repetition:
            return False, "repeticion"
        if bloque != "etica" and ia_meta(gpt):
            return False, "ia_meta"
    (h1, g1), (_, g2) = pares[0], pares[1]
    m = QUESTION_RE.search(h1)
    if m:
        q = normalize(m.group(1))
        if len(q) > 25 and normalize(g1[:120]).startswith(q[:40]):
            return False, "eco_pregunta"
    if not grounding(h1, g1, calculos):
        return False, "sin_datos_del_prompt"
    if not orientacion_ok(h1, g1):
        return False, "orientacion"
    if bloque != "etica":
        if eco_prompt(h1, g1):
            return False, "eco_prompt"
    if _copia_turno1(g1, g2):
        return False, "turno2_copia_turno1"
    if _sin_hilo(g1, g2):
        return False, "turno2_sin_hilo"
    return True, "ok"


def validate(row: dict, args, bloque: str | None = None) -> tuple[bool, str]:
    answer = answer_of(row)
    prompt = human_of(row)
    if not answer or not prompt:
        return False, "sin_turnos"
    texto_prompt = (system_of(row) + "\n" + prompt).lower()
    if any(marca in texto_prompt for marca in SIN_TILDES_MARCAS):
        return False, "prompt_sin_tildes"
    pares = turnos_de(row)
    calculos = row.get("calculos") if isinstance(row.get("calculos"), dict) else None
    if len(pares) >= 2:
        return _validar_multiturno(pares, args, bloque, calculos)
    if len(answer) < args.min_chars:
        return False, "corto"
    if len(answer) > args.max_chars:
        return False, "largo"
    low = answer.lower()
    if any(m in low for m in JUNK):
        return False, "boilerplate"
    lang = detect_language(answer)
    if lang not in ("es", "mixed"):
        return False, f"idioma_{lang}"
    if repetition_ratio(answer) > args.max_repetition:
        return False, "repeticion"
    m = QUESTION_RE.search(prompt)
    if m:
        q = normalize(m.group(1))
        if len(q) > 25 and normalize(answer[:120]).startswith(q[:40]):
            return False, "eco_pregunta"
    if not grounding(prompt, answer, calculos):
        return False, "sin_datos_del_prompt"
    if not orientacion_ok(prompt, answer):
        return False, "orientacion"
    if bloque != "etica":
        if eco_prompt(prompt, answer):
            return False, "eco_prompt"
        if ia_meta(answer):
            return False, "ia_meta"
    return True, "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Valida y deduplica pares sintéticos.")
    ap.add_argument("--dir", default="corpus/synthetic")
    ap.add_argument("--out", default="corpus/synthetic_clean.jsonl")
    ap.add_argument("--meta-out", default="corpus/synthetic_clean.meta.jsonl")
    ap.add_argument("--report", default="corpus/synthetic_report.json")
    ap.add_argument("--min-chars", type=int, default=400)
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--max-repetition", type=float, default=0.12)
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(str(Path(args.dir) / "*.jsonl")))
    if not paths:
        print(f"[validate] no hay ficheros en {args.dir}")
        return 1

    seen_hash: set[str] = set()
    indice = IndiceCasiDuplicados()
    meta: list[dict] = []
    reasons: Counter = Counter()
    per_block: dict[str, dict[str, int]] = {}
    kept = 0
    total = 0
    pairs_dup = 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for path in paths:
            file_block = Path(path).name.split(".")[0]
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        stats = per_block.setdefault(
                            file_block, {"total": 0, "ok": 0, "dup": 0, "bad": 0})
                        stats["total"] += 1
                        stats["bad"] += 1
                        reasons["json_invalido"] += 1
                        continue
                    # Bloque: el de la fila si lo trae (salida del ejecutor, D1),
                    # si no el del nombre de fichero (comportamiento heredado).
                    block = str(row.get("bloque") or file_block)
                    stats = per_block.setdefault(
                        block, {"total": 0, "ok": 0, "dup": 0, "bad": 0})
                    stats["total"] += 1
                    ok, why = validate(row, args, bloque=block)
                    if not ok:
                        stats["bad"] += 1
                        reasons[why] += 1
                        continue
                    answer = answer_of(row)
                    h = sha(answer)
                    if h in seen_hash:
                        stats["dup"] += 1
                        reasons["duplicado_exacto"] += 1
                        continue
                    if indice.buscar(answer):
                        stats["dup"] += 1
                        pairs_dup += 1
                        reasons["duplicado_cercano"] += 1
                        continue
                    seen_hash.add(h)
                    indice.add(str(kept), answer)
                    stats["ok"] += 1
                    kept += 1
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    meta.append({"i": kept - 1, "block": block})

    Path(args.meta_out).write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in meta), encoding="utf-8"
    )
    report = {
        "total": total,
        "kept": kept,
        "rejected": total - kept,
        "near_duplicates": pairs_dup,
        "reasons": dict(reasons),
        "per_block": per_block,
        "output": str(out),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[validate] leídos {total} · válidos {kept} · descartados {total - kept}")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  - {k}: {v}")
    print(f"[validate] salida: {out}")
    for b, s in sorted(per_block.items()):
        print(f"  {b:18s} total={s['total']:5d} ok={s['ok']:5d} dup={s['dup']:4d} bad={s['bad']:4d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
