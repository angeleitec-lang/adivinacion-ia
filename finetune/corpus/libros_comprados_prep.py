#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preparación de los libros de astrología comprados (T118): Arroyo y Sasportas.

Los PDF están en formato apaisado: cada hoja del PDF contiene DOS páginas del
libro (izquierda = verso, derecha = recto). Este script:

  * Arroyo (buena capa de texto): extrae cada media hoja con recorte
    (pdftotext -layout -x/-y/-W/-H), quita cabeceras/pies y números de página,
    une palabras cortadas por guion y marca títulos de capítulo (``#``) y
    subtítulos (``##``) cuando se detectan con fiabilidad.
  * Sasportas (capa de texto inservible): re-hace el OCR a 300 dpi
    (pdftoppm -gray + tesseract -l eng), separando las dos medias hojas antes
    de OCR. Prueba varias configuraciones de segmentación (psm) sobre 10
    páginas y elige con una métrica objetiva (% de palabras en un vocabulario
    inglés y nº de palabras pegadas). Reanudable por media hoja con caché.

Salidas (fuera del repo, datos con copyright, uso interno):
  <base>/limpio/{arroyo,sasportas}.txt            texto limpio
  <base>/limpio/{arroyo,sasportas}.paginas.jsonl  hoja del PDF → offsets
  <base>/informe_calidad.md                       informe antes/después y cobertura

Procedencia: libros comprados por el usuario, uso interno, con copyright. No
copiar los textos al repo. Sin LLM: solo CPU del iMac (nice -n 10, ≤3 procesos
en paralelo).

Uso:
  python libros_comprados_prep.py arroyo     [--pdf ...] [--base ...]
  python libros_comprados_prep.py sasportas  [--base ...] [--fuerza-psm N]
  python libros_comprados_prep.py ambos
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Constantes de entorno / rutas por defecto
# --------------------------------------------------------------------------
ARROYO_PDF = "/Users/angelgonzalez/fase0/libros_comprados/Arroyo - Astrology Psychology and the Four Elements (1982).pdf"
SASPORTAS_PDF = "/Users/angelgonzalez/fase0/libros_comprados/Sasportas - The Twelve Houses (1985).pdf"
BASE_DIR = "/Users/angelgonzalez/fase0/libros_comprados_astro"
VOCAB_PATH = "/usr/share/dict/words"

MAX_WORKERS = 3           # ≤3 procesos en paralelo (el usuario trabaja en el iMac)
NICE_PREFIX = ["nice", "-n", "10"]
OCR_DPI = 300
BLANK_DARK_FRAC = 0.0004  # fracción de píxeles oscuros por debajo de la cual la media hoja es «en blanco»
SHORT_PAGE_WORDS = 110    # páginas de menos palabras se consideran cortas (apertura de capítulo)
TOP_ZONE = 6              # líneas de contenido superiores que pueden ser cabecera
BOTTOM_ZONE = 4           # líneas de contenido inferiores que pueden ser pie

ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth",
}

# --------------------------------------------------------------------------
# Utilidades de subprocess (todo con nice -n 10)
# --------------------------------------------------------------------------

def run_cmd(cmd: list, timeout: int = 1200) -> subprocess.CompletedProcess:
    """Ejecuta un comando bajo nice -n 10 y captura stdout/stderr."""
    return subprocess.run(NICE_PREFIX + cmd, capture_output=True, timeout=timeout)


def pdfinfo_pages(pdf: str) -> int:
    out = run_cmd(["pdfinfo", pdf]).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise ValueError(f"pdfinfo no devolvió número de páginas para {pdf}")


def pdfinfo_page_size(pdf: str) -> tuple:
    """Tamaño (ancho, alto) en puntos de la primera página."""
    out = run_cmd(["pdfinfo", "-f", "1", "-l", "1", pdf]).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        m = re.match(r"Page\s+1 size:\s+(\d+(?:\.\d+)?) x (\d+(?:\.\d+)?)", line)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))
    raise ValueError(f"no se pudo leer el tamaño de página de {pdf}")

# --------------------------------------------------------------------------
# Vocabulario inglés y métricas de calidad
# --------------------------------------------------------------------------

def ascii_fold(text: str) -> str:
    """Minúsculas ascii sin acentos: solo letras (para comparar con el diccionario)."""
    norm = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in norm if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", stripped.lower())


def load_vocab(path: str = VOCAB_PATH) -> frozenset:
    """Vocabulario inglés normalizado desde /usr/share/dict/words."""
    words = set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            w = ascii_fold(line.strip().lower())
            if 1 < len(w) <= 24 and w.isalpha():
                words.add(w)
    return frozenset(words)


WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019-]*")


def tokenize(text: str) -> list:
    return WORD_RE.findall(text)


@dataclass
class QualityStats:
    tokens: int = 0
    in_vocab: int = 0
    glued: int = 0

    @property
    def vocab_pct(self) -> float:
        return 100.0 * self.in_vocab / self.tokens if self.tokens else 0.0


def split_vocab_pieces(word: str, vocab: frozenset, min_part: int = 2, max_part: int = 24):
    """Trocea `word` (ascii_fold ya aplicado) en el MENOR nº de piezas del
    vocabulario (cada una de longitud >= min_part). Devuelve la lista de
    piezas o None si no es descomponible. DP O(n·max_part)."""
    n = len(word)
    INF = float("inf")
    best = [INF] * (n + 1)
    cut_at = [-1] * (n + 1)
    best[0] = 0
    for i in range(1, n + 1):
        lo = max(0, i - max_part)
        for j in range(lo, i):
            if best[j] == INF:
                continue
            piece = word[j:i]
            if len(piece) < min_part or piece not in vocab:
                continue
            if best[j] + 1 < best[i]:
                best[i] = best[j] + 1
                cut_at[i] = j
    if best[n] == INF:
        return None
    pieces = []
    i = n
    while i > 0:
        j = cut_at[i]
        pieces.append(word[j:i])
        i = j
    return pieces[::-1]


def is_glued(token: str, vocab: frozenset) -> bool:
    """Palabra «pegada» (típico de OCR sin espacios): no está en el
    vocabulario pero se descompone en >= 2 palabras reales, con al menos una
    de ellas larga (>= 3). Ejemplos de la capa vieja: 'houseis', 'wayof'."""
    w = ascii_fold(token)
    if len(w) < 5 or not w.isalpha() or w in vocab:
        return False
    pieces = split_vocab_pieces(w, vocab, min_part=2)
    if not pieces or len(pieces) < 2:
        return False
    return any(len(p) >= 3 for p in pieces)


def quality_metrics(text: str, vocab: frozenset, count_glued: bool = True) -> QualityStats:
    st = QualityStats()
    for tok in tokenize(text):
        w = ascii_fold(tok)
        if not w:
            continue
        st.tokens += 1
        if w in vocab:
            st.in_vocab += 1
        elif count_glued and is_glued(tok, vocab):
            st.glued += 1
    return st

# --------------------------------------------------------------------------
# PGM (grayscale P5): parseo, división en mitades, detección de página en blanco
# --------------------------------------------------------------------------

def parse_pgm(data: bytes) -> tuple:
    """Parsea PGM binario (P5). Devuelve (width, height, maxval, offset)."""
    if not data.startswith(b"P5"):
        raise ValueError("no es un PGM binario (P5)")
    i = 2
    tokens = []
    while len(tokens) < 3:
        while i < len(data) and data[i:i + 1] in (b" ", b"\t", b"\n", b"\r"):
            i += 1
        if i < len(data) and data[i:i + 1] == b"#":
            while i < len(data) and data[i:i + 1] not in (b"\n", b"\r"):
                i += 1
            continue
        j = i
        while j < len(data) and data[j:j + 1] not in (b" ", b"\t", b"\n", b"\r"):
            j += 1
        tokens.append(int(data[i:j]))
        i = j
    while i < len(data) and data[i:i + 1] in (b" ", b"\t", b"\n", b"\r"):
        i += 1
    return tokens[0], tokens[1], tokens[2], i


def build_pgm(pixels: bytes, w: int, h: int, maxv: int = 255) -> bytes:
    """Construye un PGM P5 mínimo (útil en tests)."""
    return f"P5\n{w} {h}\n{maxv}\n".encode() + pixels


def split_pgm_halves(data: bytes) -> tuple:
    """Divide un PGM en dos PGM (mitad izquierda y mitad derecha)."""
    w, h, maxv, off = parse_pgm(data)
    mid = w // 2
    px = data[off:]
    left = bytearray()
    right = bytearray()
    for y in range(h):
        base = y * w
        left += px[base:base + mid]
        right += px[base + mid:base + w]
    return build_pgm(bytes(left), mid, h, maxv), build_pgm(bytes(right), w - mid, h, maxv)


def dark_fraction(pgm: bytes) -> float:
    """Fracción de píxeles oscuros (<128) sobre el total."""
    w, h, maxv, off = parse_pgm(pgm)
    px = pgm[off:off + w * h]
    if not px:
        return 0.0
    if maxv != 255:
        px = bytes((b * 255) // maxv for b in px)
    table = b"\x01" * 128 + b"\x00" * 128
    dark = px.translate(table).count(1)
    return dark / (w * h)

# --------------------------------------------------------------------------
# Extracción Arroyo: media hoja con recorte (pdftotext -layout)
# --------------------------------------------------------------------------

def arroyo_half_text(pdf: str, sheet: int, x: int, width: int, height: int) -> str:
    """Texto (con layout) de la franja [x, x+width] de la hoja `sheet`."""
    out = run_cmd([
        "pdftotext", "-f", str(sheet), "-l", str(sheet),
        "-layout", "-x", str(x), "-y", "0", "-W", str(width), "-H", str(height),
        pdf, "-",
    ]).stdout.decode("utf-8", "replace")
    return out.replace("\f", "")

# --------------------------------------------------------------------------
# Limpieza común: cabeceras/pies, guiones, títulos
# --------------------------------------------------------------------------

_NUM = r"\d{1,4}|[ivxlcdmIVXLCDM]{1,8}"
NUM_ONLY_RE = re.compile(rf"^\s*({_NUM})\s*$")
NUM_HEAD_RE = re.compile(rf"^\s*({_NUM})\s+(\S.{{1,58}}?)\s*$")
HEAD_NUM_RE = re.compile(rf"^\s*(\S.{{1,58}}?)\s+({_NUM})\s*$")
PART_RE = re.compile(r"^\s*part\s+[ivxlcdm0-9]{1,7}\s*$", re.IGNORECASE)


def norm_head(line: str) -> str:
    """Normaliza una línea para compararla como rúbrica recurrente."""
    s = re.sub(r"\s+", " ", line).strip()
    s = s.strip(".·: ").strip("—–- ")
    return s.lower()


def norm_keep_case(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def looks_page_number_line(line: str):
    """Etiqueta si la línea es solo un número de página; None en caso contrario."""
    m = NUM_ONLY_RE.match(line)
    return m.group(1) if m else None


def collect_running_heads(pages: list, min_pages: int = 4, top_zone: int = TOP_ZONE,
                          bottom_zone: int = BOTTOM_ZONE) -> frozenset:
    """Rúbricas recurrentes: líneas cortas del borde superior/inferior que se
    repiten idénticas en >= min_pages páginas (título del capítulo en curso,
    título del libro en cabecera...)."""
    counts = {}
    for lines in pages:
        content = [l for l in lines if l.strip()]
        zone = content[:top_zone] + content[-bottom_zone:]
        seen = set()
        for line in zone:
            if NUM_ONLY_RE.match(line):
                continue
            m = NUM_HEAD_RE.match(line)
            if m:
                s = norm_head(m.group(2))
            else:
                m = HEAD_NUM_RE.match(line)
                s = norm_head(m.group(1)) if m else norm_head(line)
            if not s or len(s) > 60 or len(tokenize(line)) > 10:
                continue
            if s not in seen:
                counts[s] = counts.get(s, 0) + 1
                seen.add(s)
    return frozenset(s for s, c in counts.items() if c >= min_pages)


@dataclass
class CleanPage:
    lines: list = field(default_factory=list)     # líneas limpias (sin cabeceras/pies)
    label: "str | None" = None                    # nº de página impreso visto
    dropped: list = field(default_factory=list)   # líneas eliminadas
    title_page: bool = False                      # apertura de capítulo (línea 1 es título recurrente y página corta)


def clean_page(lines: list, running_heads: frozenset) -> CleanPage:
    """Quita cabeceras/pies y números de página y detecta aperturas de capítulo.

    Apertura: página corta (<= SHORT_PAGE_WORDS palabras) cuyo primer texto
    tras eventuales números sueltos es una rúbrica recurrente o «Part N». En
    ese caso el título SE CONSERVA (luego se marcará con #) y no se anota
    etiqueta: el número suelto de la apertura es el nº de capítulo, ambiguo.
    """
    content = [l for l in lines if l.strip()]
    clean = CleanPage()
    n_words = len(tokenize(" ".join(content)))

    first_idx = None
    for i, line in enumerate(content[:4]):
        if looks_page_number_line(line):
            continue
        s = norm_head(line)
        if s in running_heads or PART_RE.match(line):
            first_idx = i
        break
    clean.title_page = first_idx is not None and n_words <= SHORT_PAGE_WORDS

    body = list(lines)
    idx = 0
    for i, line in enumerate(body):
        if not line.strip():
            continue
        if idx >= TOP_ZONE:
            break
        idx += 1
        s = norm_head(line)
        lbl = looks_page_number_line(line)
        if lbl is not None:
            if not clean.title_page:
                clean.label = clean.label or lbl
            clean.dropped.append(line)
            body[i] = None
            continue
        if s in running_heads:
            if clean.title_page and first_idx is not None and idx == first_idx + 1:
                break  # es el título de apertura: se conserva
            clean.dropped.append(line)
            body[i] = None
            continue
        if idx <= 2:
            m = NUM_HEAD_RE.match(line)
            if m and norm_head(m.group(2)) in running_heads:
                if not clean.title_page:
                    clean.label = clean.label or m.group(1)
                clean.dropped.append(line)
                body[i] = None
                continue
            m = HEAD_NUM_RE.match(line)
            if m and norm_head(m.group(1)) in running_heads:
                if not clean.title_page:
                    clean.label = clean.label or m.group(2)
                clean.dropped.append(line)
                body[i] = None
                continue
        break

    tail = 0
    for i in range(len(body) - 1, -1, -1):
        line = body[i]
        if line is None or not line.strip():
            continue
        if tail >= BOTTOM_ZONE:
            break
        tail += 1
        lbl = looks_page_number_line(line)
        if lbl is not None:
            clean.label = clean.label or lbl
            clean.dropped.append(line)
            body[i] = None
            continue
        if norm_head(line) in running_heads:
            clean.dropped.append(line)
            body[i] = None
            continue
        break

    clean.lines = [l for l in body if l is not None]
    return clean


def join_hyphens(lines: list, vocab: frozenset) -> tuple:
    """Une palabras cortadas por guion a final de línea.

    - Unión = palabra del vocabulario → se une sin guion («ar- / chetypes» → «archetypes»).
    - Ambas partes son palabras reales → se conserva el guion en la misma línea («fortune- / teller» → «fortune-teller»).
    - Segunda pieza en minúscula y caso desconocido → se une sin guion (evita dejar «re-» colgando); se cuenta como forzada.
    Devuelve (nuevas líneas, conteos).
    """
    info = {"joined": 0, "kept_hyphen": 0, "forced": 0}
    out = list(lines)
    i = 0
    while i + 1 < len(out):
        nxt = out[i + 1]
        if not nxt.strip():
            i += 1
            continue
        stripped = out[i].rstrip()
        if stripped.endswith("-") and not NUM_ONLY_RE.match(stripped):
            before = stripped[:-1]
            m_a = re.search(r"([A-Za-z'\u2019]+)$", before)
            m_b = re.match(r"\s*([A-Za-z'\u2019]+)", nxt)
            if m_a and m_b:
                a, b = m_a.group(1), m_b.group(1)
                cand = ascii_fold(a) + ascii_fold(b)
                prefix = before[:m_a.start(1)]
                rest = nxt[m_b.end(1):]
                if cand in vocab:
                    out[i] = prefix + a + b + rest
                    info["joined"] += 1
                elif ascii_fold(a) in vocab and ascii_fold(b) in vocab:
                    out[i] = prefix + a + "-" + b + rest
                    info["kept_hyphen"] += 1
                elif b[0].islower():
                    out[i] = prefix + a + b + rest
                    info["forced"] += 1
                else:
                    i += 1
                    continue
                out.pop(i + 1)
                continue
        i += 1
    return out, info


HEADING_MAX_WORDS = 8
HEADING_MAX_CHARS = 46
_BAD_END = tuple(".!?,;:—–-'\"\u201c\u201d\u2018\u2019")
_SMALL_WORDS = {"a", "an", "and", "the", "of", "in", "on", "to", "as", "or", "for", "&"}


def heading_candidate(line: str, running_heads: frozenset) -> bool:
    """Subtítulo probable: línea corta (2-8 palabras, <=46 caracteres), sin
    puntuación final ni dígitos, no rúbrica recurrente, con las palabras en
    mayúscula inicial (permitiendo artículos/preposiciones en minúscula) o
    todo en mayúsculas."""
    s = line.strip()
    if not s or len(s) > HEADING_MAX_CHARS or s.endswith(_BAD_END):
        return False
    toks = tokenize(s)
    if not 2 <= len(toks) <= HEADING_MAX_WORDS:
        return False
    if s[0] in "\"'\u201c\u2018—–-([":
        return False
    if NUM_ONLY_RE.match(s) or re.search(r"\d", s):
        return False
    if norm_head(s) in running_heads:
        return False
    if s.upper() == s:
        return True
    for t in toks:
        if t[0].isalpha() and not t[0].isupper() and ascii_fold(t) not in _SMALL_WORDS:
            return False
    return True


def mark_headings(page_lines: list, running_heads: frozenset, title_page: bool) -> list:
    """Marca la primera línea de las aperturas con ``#`` y los subtítulos
    sueltos (línea entre dos líneas en blanco) con ``##``."""
    out = []
    n = len(page_lines)
    pending_title = title_page
    for k, line in enumerate(page_lines):
        if not line.strip():
            out.append("")
            continue
        if pending_title:
            out.append("# " + norm_keep_case(line))
            pending_title = False
            continue
        prev_blank = k == 0 or not page_lines[k - 1].strip()
        next_blank = k + 1 >= n or not page_lines[k + 1].strip()
        if prev_blank and next_blank and heading_candidate(line, running_heads):
            out.append("## " + norm_keep_case(line))
        else:
            out.append(line)
    return out

# --------------------------------------------------------------------------
# Ensamblado de documento + offsets por página
# --------------------------------------------------------------------------

def build_document(pages: list) -> tuple:
    """Une las páginas (dicts con sheet/side/lines/label) en un texto.

    Devuelve (texto, registros con offsets en caracteres [start,end))."""
    chunks = []
    records = []
    pos = 0
    for p in pages:
        chunk = "\n".join(p["lines"]).strip("\n")
        if not chunk.strip():
            continue
        if chunks:
            chunks.append("\n\n")
            pos += 2
        start = pos
        chunks.append(chunk)
        pos += len(chunk)
        records.append({
            "page_idx": len(records) + 1,
            "label": p.get("label"),
            "sheet": p["sheet"],
            "side": p["side"],
            "start": start,
            "end": pos,
        })
    text = "".join(chunks) + "\n"
    return text, records

# --------------------------------------------------------------------------
# Cobertura (AJUSTE Sasportas): casas 1-12 y partes del libro presentes
# --------------------------------------------------------------------------

def detect_house_presence(text: str) -> dict:
    """Para cada casa 1..12: nº de menciones del patrón «The <ordinal> House»,
    primera/última línea y si aparece como título marcado (#/##)."""
    lines = text.splitlines()
    res = {}
    for num, word in ORDINALS.items():
        pat = re.compile(rf"\bthe\s+{word}\s+houses?\b", re.IGNORECASE)
        head_pat = re.compile(rf"^#{{1,2}}\s+the\s+{word}\s+house\b", re.IGNORECASE)
        hits = [i + 1 for i, l in enumerate(lines) if pat.search(l)]
        heads = [i + 1 for i, l in enumerate(lines) if head_pat.match(l)]
        res[num] = {"word": word, "mentions": len(hits),
                    "first_line": hits[0] if hits else None,
                    "last_line": hits[-1] if hits else None,
                    "as_heading": bool(heads)}
    return res


PART_MARKERS = {
    "introducción/prefacio": r"\b(?:introduction|preface|foreword)\b",
    "capítulo Space, Time and Boundaries": r"space,?\s+time\s+and\s+boundaries",
    "los planetas": r"\bthe\s+planets\b",
    "los signos": r"\bthe\s+signs\b",
    "luminaries (Sol/Luna)": r"\bluminar(?:y|ies)\b",
    "aspectos": r"\baspects\b",
    "casas como concepto general": r"\bthe\s+houses\b",
    "apéndice/glosario": r"\bappendix\b|\bglossary\b",
    "bibliografía": r"\bbibliography\b",
    "índice": r"\bindex\b",
}


def detect_part_presence(text: str) -> dict:
    low = text.lower()
    return {name: bool(re.search(pat, low)) for name, pat in PART_MARKERS.items()}

# --------------------------------------------------------------------------
# Pipeline Arroyo
# --------------------------------------------------------------------------

def prepare_arroyo(pdf: str, vocab: frozenset) -> dict:
    n = pdfinfo_pages(pdf)
    w_pt, h_pt = pdfinfo_page_size(pdf)
    mid = w_pt // 2
    raw_pages = []
    for sheet in range(1, n + 1):
        for side, x, width in (("L", 0, mid), ("R", mid, w_pt - mid)):
            txt = arroyo_half_text(pdf, sheet, x, width, h_pt)
            if not "".join(txt.split()):
                continue
            lines = [norm_keep_case(l) for l in txt.splitlines()]
            raw_pages.append({"sheet": sheet, "side": side, "lines": lines})
    heads = collect_running_heads([p["lines"] for p in raw_pages])
    out_pages = []
    hy = {"joined": 0, "kept_hyphen": 0, "forced": 0}
    dropped = 0
    for p in raw_pages:
        cp = clean_page(p["lines"], heads)
        joined, hinfo = join_hyphens(cp.lines, vocab)
        for k in hy:
            hy[k] += hinfo[k]
        dropped += len(cp.dropped)
        marked = mark_headings(joined, heads, cp.title_page)
        out_pages.append({"sheet": p["sheet"], "side": p["side"], "lines": marked,
                          "label": cp.label, "title_page": cp.title_page})
    text, records = build_document(out_pages)
    before = "\n".join("\n".join(p["lines"]) for p in raw_pages)
    return {"text": text, "records": records, "heads": sorted(heads), "hyphens": hy,
            "dropped": dropped, "n_raw_pages": len(raw_pages), "before_text": before}

# --------------------------------------------------------------------------
# Pipeline Sasportas (OCR)
# --------------------------------------------------------------------------

BLANK_MARK = "@@BLANK"
PSM_CANDIDATOS = (3, 4, 6)


def rasterize_sheet(pdf: str, sheet: int, dpi: int = OCR_DPI) -> bytes:
    """PGM (grayscale) de la hoja completa a `dpi`."""
    with tempfile.TemporaryDirectory(prefix=f"t118r{sheet}_") as td:
        prefix = str(Path(td) / "pg")
        run_cmd(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(sheet), "-l", str(sheet), pdf, prefix])
        files = sorted(Path(td).glob("pg*.pgm"))
        if not files:
            raise RuntimeError(f"pdftoppm no generó PGM para la hoja {sheet}")
        return files[0].read_bytes()


def tesseract_ocr(pgm_path: str, psm: int) -> str:
    res = run_cmd(["tesseract", pgm_path, "stdout", "-l", "eng", "--psm", str(psm)], timeout=1800)
    return res.stdout.decode("utf-8", "replace")


def sas_dirs(work: Path) -> dict:
    dirs = {"sample": work / "ocr_sample", "full": work / "ocr", "raster": work / "raster"}
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def sasportas_sample(pdf: str, work: Path, vocab: frozenset, sheets: list, psms=None) -> dict:
    """Prueba las configuraciones de tesseract sobre `sheets` (cada hoja = 2 páginas
    del libro; en total ~10 páginas con 5 hojas). Elige el psm con mayor
    % vocabulario; empate → menos palabras pegadas. Guarda caché y un json."""
    psms = tuple(psms or PSM_CANDIDATOS)
    dirs = sas_dirs(work)
    per_psm = {p: [] for p in psms}
    n_pages = 0
    for sheet in sheets:
        pgm = rasterize_sheet(pdf, sheet)
        halves = dict(zip(("L", "R"), split_pgm_halves(pgm)))
        for side in ("L", "R"):
            data = halves[side]
            if dark_fraction(data) < BLANK_DARK_FRAC:
                continue
            fp = dirs["sample"] / f"{sheet:03d}_{side}.pgm"
            fp.write_bytes(data)
            n_pages += 1
            for psm in psms:
                cache = dirs["sample"] / f"{sheet:03d}_{side}_psm{psm}.txt"
                if cache.exists():
                    txt = cache.read_text(encoding="utf-8", errors="replace")
                else:
                    txt = tesseract_ocr(str(fp), psm)
                    cache.write_text(txt, encoding="utf-8")
                per_psm[psm].append(txt)
    table = []
    for psm in psms:
        st = quality_metrics("\n".join(per_psm[psm]), vocab)
        table.append({"psm": psm, "pages": len(per_psm[psm]), "tokens": st.tokens,
                      "vocab_pct": round(st.vocab_pct, 2), "glued": st.glued})
    chosen = sorted(table, key=lambda r: (-r["vocab_pct"], r["glued"]))[0]["psm"]
    result = {"table": table, "chosen_psm": chosen, "sheets": sheets, "pages": n_pages}
    (work / "config_sasportas.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    return result


def sasportas_page_text(pdf: str, work: Path, sheet: int, psm: int) -> dict:
    """OCR reanudable de una hoja: usa la caché por media hoja si existe."""
    dirs = sas_dirs(work)
    cache = {}
    for side in ("L", "R"):
        cp = dirs["full"] / f"{sheet:03d}_{side}.txt"
        if cp.exists():
            cache[side] = cp.read_text(encoding="utf-8", errors="replace")
    if len(cache) == 2:
        return {"sheet": sheet, "halves": cache}
    pgm = rasterize_sheet(pdf, sheet)
    halves = dict(zip(("L", "R"), split_pgm_halves(pgm)))
    del pgm
    for side in ("L", "R"):
        if side in cache:
            continue
        data = halves[side]
        df = dark_fraction(data)
        cp = dirs["full"] / f"{sheet:03d}_{side}.txt"
        if df < BLANK_DARK_FRAC:
            cache[side] = f"{BLANK_MARK} dark={df:.5f}\n"
        else:
            fp = dirs["raster"] / f"{sheet:03d}_{side}.pgm"
            fp.write_bytes(data)
            try:
                txt = tesseract_ocr(str(fp), psm)
            finally:
                fp.unlink(missing_ok=True)
            if not "".join(txt.split()):
                cache[side] = f"{BLANK_MARK} dark={df:.5f} ocr-nulo\n"
            else:
                cache[side] = txt
        cp.write_text(cache[side], encoding="utf-8")
    return {"sheet": sheet, "halves": cache}


def prepare_sasportas(pdf: str, vocab: frozenset, work: Path, psm: int) -> dict:
    n = pdfinfo_pages(pdf)
    halves_by_sheet = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(sasportas_page_text, pdf, work, s, psm) for s in range(1, n + 1)]
        for f in futs:
            r = f.result()
            halves_by_sheet.append(r["halves"])
    infos = []
    raw_pages = []
    for sheet, halves in enumerate(halves_by_sheet, start=1):
        for side in ("L", "R"):
            txt = halves.get(side, "")
            if txt.startswith(BLANK_MARK):
                infos.append({"sheet": sheet, "side": side, "kind": "en blanco", "note": txt.strip()})
                continue
            toks = len(tokenize(txt))
            kind = "texto" if toks >= 30 else "figura/sin texto"
            infos.append({"sheet": sheet, "side": side, "kind": kind, "tokens": toks})
            if toks:
                lines = [l.rstrip() for l in txt.splitlines()]
                raw_pages.append({"sheet": sheet, "side": side, "lines": lines})
    heads = collect_running_heads([p["lines"] for p in raw_pages])
    out_pages = []
    hy = {"joined": 0, "kept_hyphen": 0, "forced": 0}
    dropped = 0
    for p in raw_pages:
        cp = clean_page(p["lines"], heads)
        joined, hinfo = join_hyphens(cp.lines, vocab)
        for k in hy:
            hy[k] += hinfo[k]
        dropped += len(cp.dropped)
        marked = mark_headings(joined, heads, cp.title_page)
        out_pages.append({"sheet": p["sheet"], "side": p["side"], "lines": marked,
                          "label": cp.label, "title_page": cp.title_page})
    text, records = build_document(out_pages)
    before = run_cmd(["pdftotext", pdf, "-"], timeout=1800).stdout.decode("utf-8", "replace")
    return {"text": text, "records": records, "heads": sorted(heads), "hyphens": hy,
            "dropped": dropped, "sheet_infos": infos, "before_text": before,
            "n_raw_pages": len(raw_pages)}

# --------------------------------------------------------------------------
# Salidas e informe
# --------------------------------------------------------------------------

def sample_paragraphs(text: str, k: int = 5) -> list:
    """K párrafos de muestra (40-220 palabras) repartidos por el documento."""
    paras = [norm_keep_case(p) for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if 40 <= len(p.split()) <= 220 and not p.startswith("#")]
    if not paras:
        return []
    step = max(1, len(paras) // k)
    picks = []
    idx = 0
    while len(picks) < k and idx < len(paras):
        picks.append(paras[min(idx, len(paras) - 1)])
        idx += step
    return picks


def write_outputs(base: Path, book: str, data: dict) -> Path:
    limpi = base / "limpio"
    limpi.mkdir(parents=True, exist_ok=True)
    (limpi / f"{book}.txt").write_text(data["text"], encoding="utf-8")
    with open(limpi / f"{book}.paginas.jsonl", "w", encoding="utf-8") as fh:
        for rec in data["records"]:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return limpi


def make_report(arroyo, sas, vocab: frozenset, psm_chosen, sample_table) -> str:
    out = ["# Informe de calidad T118 — preparación de los libros de astrología", "",
           "Procedencia: PDF comprados por el usuario, uso interno, con copyright. "
           "Los textos extraídos viven en `fase0/libros_comprados_astro/`, nunca en el repo.", ""]
    if arroyo:
        before = quality_metrics(arroyo["before_text"], vocab)
        after = quality_metrics(arroyo["text"], vocab)
        out += [
            "## Arroyo — Stephen Arroyo, Astrology, Psychology and the Four Elements (1982)",
            "",
            f"- Medias páginas con texto: {arroyo['n_raw_pages']}; páginas al documento final: {len(arroyo['records'])}",
            f"- Líneas de cabecera/pie eliminadas: {arroyo['dropped']}",
            f"- Guiones: {arroyo['hyphens']['joined']} unidos, "
            f"{arroyo['hyphens']['kept_hyphen']} compuestos conservados con guion, "
            f"{arroyo['hyphens']['forced']} uniones forzadas",
            "",
            "| métrica | antes (capa cruda de la media hoja) | después (limpio) |",
            "|---|---|---|",
            f"| tokens alfabéticos | {before.tokens} | {after.tokens} |",
            f"| % en vocabulario inglés | {before.vocab_pct:.2f} % | {after.vocab_pct:.2f} % |",
            f"| palabras pegadas detectadas | {before.glued} | {after.glued} |",
            "",
            "Rúbricas recurrentes eliminadas (muestra): "
            + "; ".join(arroyo["heads"][:14]) + ("…" if len(arroyo["heads"]) > 14 else ""),
            "",
            "### 5 párrafos de muestra (texto limpio)",
            "",
        ]
        for j, p in enumerate(sample_paragraphs(arroyo["text"]), 1):
            out.append(f"{j}. «{p[:400]}»")
        out += ["", "### Marcas de estructura detectadas", ""]
        for rec, line in _heading_lines(arroyo["text"])[:40]:
            out.append(f"- hoja {rec['sheet']} {rec['side']} (pág. {rec['label']}): {line[:80]}")
        out.append("")
    if sas:
        before = quality_metrics(sas["before_text"], vocab)
        after = quality_metrics(sas["text"], vocab)
        out += [
            "## Sasportas — Liz Greene & Howard Sasportas (?) — The Twelve Houses (1985)",
            "",
            f"- OCR re-hecho a {OCR_DPI} dpi, tesseract `-l eng --psm {psm_chosen}` (separando las dos medias hojas).",
            f"- Medias páginas con texto: {sas['n_raw_pages']}; páginas al documento final: {len(sas['records'])}",
            f"- Líneas de cabecera/pie eliminadas: {sas['dropped']}",
            f"- Guiones: {sas['hyphens']['joined']} unidos, {sas['hyphens']['kept_hyphen']} conservados, "
            f"{sas['hyphens']['forced']} forzados",
            "",
        ]
        if sample_table:
            out += ["### Muestra de configuraciones OCR (10 páginas)", "",
                    "| --psm | páginas | tokens | % vocabulario | palabras pegadas |",
                    "|---|---|---|---|---|"]
            for r in sample_table:
                mark = " ← elegido" if r["psm"] == psm_chosen else ""
                out.append(f"| {r['psm']}{mark} | {r['pages']} | {r['tokens']} | {r['vocab_pct']} % | {r['glued']} |")
            out.append("")
        out += [
            "| métrica | antes (capa de texto del PDF) | después (OCR nuevo limpio) |",
            "|---|---|---|",
            f"| tokens alfabéticos | {before.tokens} | {after.tokens} |",
            f"| % en vocabulario inglés | {before.vocab_pct:.2f} % | {after.vocab_pct:.2f} % |",
            f"| palabras pegadas detectadas | {before.glued} | {after.glued} |",
            "",
            "### Cobertura real del escaneo (AJUSTE: el PDF está incompleto)",
            "",
            "| hoja | lado L | lado R |",
            "|---|---|---|",
        ]
        by_sheet = {}
        for info in sas["sheet_infos"]:
            by_sheet.setdefault(info["sheet"], {})[info["side"]] = info
        for sheet in sorted(by_sheet):
            cells = []
            for side in ("L", "R"):
                info = by_sheet[sheet].get(side, {})
                kind = info.get("kind", "?")
                tok = info.get("tokens")
                cells.append(f"{kind}" + (f" ({tok})" if tok else ""))
            out.append(f"| {sheet} | {cells[0]} | {cells[1]} |")
        houses = detect_house_presence(sas["text"])
        out += ["", "### Casas 1-12 en la parte escaneada", "",
                "| casa | patrón «The <ordinal> House» | ¿presente? |",
                "|---|---|---|"]
        for num, d in houses.items():
            estado = "SÍ" if (d["mentions"] or d["as_heading"]) else "NO"
            det = f"{d['mentions']} apariciones" + (
                f", última línea {d['last_line']}" if d["mentions"] else "")
            if d["as_heading"]:
                det += ", como título #"
            out.append(f"| {num} ({d['word']}) | {det} | {estado} |")
        parts = detect_part_presence(sas["text"])
        out += ["", "### Partes del libro detectadas", ""]
        for name, ok in parts.items():
            out.append(f"- {'SÍ' if ok else 'NO'}: {name}")
        out += ["", "### Marcas de estructura detectadas", ""]
        for rec, line in _heading_lines(sas["text"])[:40]:
            out.append(f"- hoja {rec['sheet']} {rec['side']} (pág. {rec['label']}): {line[:80]}")
        out += ["", "### 5 párrafos de muestra (texto limpio)", ""]
        for j, p in enumerate(sample_paragraphs(sas["text"]), 1):
            out.append(f"{j}. «{p[:400]}»")
        out.append("")
    out += [
        "## Problemas que quedan",
        "",
        "- Arroyo: la tipografía decorativa de las portadillas («Astro logy & P syc ho [ogy») llega "
        "con espacios dentro de las palabras desde la capa de texto del PDF; no es recuperable sin OCR.",
        "- Arroyo: el sumario (tabla de contenido) se conserva tal cual, con líneas de puntos y números "
        "sustos que la limpieza general no distingue de texto normal.",
        "- Sasportas: fracciones del tipo «2½ days» salen como «2% days»; no se han corregido para no "
        "introducir cambios de texto no verificables.",
        "- Sasportas: las figuras/diagramas quedan como líneas sueltas sin texto alternativo.",
        "- Las marcas `#`/`##` son heurísticas (frecuencia de rúbricas + líneas cortas sueltas); T119 debe "
        "revisarlas antes de usarlas como segmentación.",
        "- El PDF de Sasportas está INCOMPLETO (63 de ~150 hojas): ver la tabla de cobertura; T119 solo "
        "podrá atribuir evidencias a lo presente.",
    ]
    return "\n".join(out) + "\n"


def _heading_lines(data: dict) -> list:
    """[(registro de página, línea marcada)] a partir de los offsets de cada página."""
    text = data["text"]
    res = []
    for rec in data["records"]:
        chunk = text[rec["start"]:rec["end"]]
        for line in chunk.splitlines():
            if line.startswith("#"):
                res.append((rec, line))
    return res


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Preparación T118 de libros de astrología (Arroyo/Sasportas).")
    ap.add_argument("libro", choices=["arroyo", "sasportas", "ambos"])
    ap.add_argument("--arroyo-pdf", default=ARROYO_PDF)
    ap.add_argument("--sasportas-pdf", default=SASPORTAS_PDF)
    ap.add_argument("--base", default=BASE_DIR, help="directorio de salidas (fuera del repo)")
    ap.add_argument("--work", default=None, help="directorio de caché (por defecto <base>/work)")
    ap.add_argument("--fuerza-psm", type=int, default=None, help="forzar psm de tesseract sin muestreo")
    ap.add_argument("--sheets-muestra", default="8,15,24,33,42", help="hojas del muestreo de configs")
    ap.add_argument("--psms", default="3,4,6", help="psm candidatos (separados por comas)")
    args = ap.parse_args(argv)

    base = Path(args.base)
    work = Path(args.work) if args.work else base / "work"
    work.mkdir(parents=True, exist_ok=True)
    vocab = load_vocab()

    arroyo = sas = None
    psm_chosen = None
    sample_table = None

    if args.libro in ("arroyo", "ambos"):
        print("[t118] Arroyo: extrayendo medias hojas con recorte...", file=sys.stderr)
        arroyo = prepare_arroyo(args.arroyo_pdf, vocab)
        write_outputs(base, "arroyo", arroyo)
        print(f"[t118] Arroyo: {len(arroyo['records'])} páginas, {len(arroyo['text'])} caracteres",
              file=sys.stderr)

    if args.libro in ("sasportas", "ambos"):
        if args.fuerza_psm:
            psm_chosen = args.fuerza_psm
        else:
            sheets = [int(x) for x in args.sheets_muestra.split(",")]
            psms = [int(x) for x in args.psms.split(",")]
            print(f"[t118] Sasportas: muestreo OCR en hojas {sheets} (psm {psms})...", file=sys.stderr)
            sel = sasportas_sample(args.sasportas_pdf, work, vocab, sheets, psms)
            sample_table = sel["table"]
            psm_chosen = sel["chosen_psm"]
            print(f"[t118] Sasportas: elegido psm {psm_chosen} (tabla: {sample_table})", file=sys.stderr)
        print("[t118] Sasportas: OCR de todas las hojas (reanudable, ≤3 procesos, nice)...", file=sys.stderr)
        sas = prepare_sasportas(args.sasportas_pdf, vocab, work, psm_chosen)
        write_outputs(base, "sasportas", sas)
        print(f"[t118] Sasportas: {len(sas['records'])} páginas, {len(sas['text'])} caracteres",
              file=sys.stderr)

    report = make_report(arroyo, sas, vocab, psm_chosen, sample_table)
    (base / "informe_calidad.md").write_text(report, encoding="utf-8")
    print("[t118] informe de calidad:", base / "informe_calidad.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
