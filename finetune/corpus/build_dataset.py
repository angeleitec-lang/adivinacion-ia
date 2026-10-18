#!/usr/bin/env python3
"""Convierte el corpus markdown extraído con Firecrawl a JSONL ShareGPT.

Lee `corpus/raw/**/*.md`, trocea cada página por sus encabezados markdown
(cada encabezado se convierte en el *tema* de una instrucción y su cuerpo en
la *respuesta*), filtra ruido y escribe `train.jsonl` y `val.jsonl` con el
formato que consume Soup para SFT:

    {"conversations": [
        {"from": "system", "value": "..."},
        {"from": "human",  "value": "..."},
        {"from": "gpt",    "value": "..."}
    ]}

La división train/val se hace a nivel de documento (nunca se parte una misma
página entre ambos), para evitar fuga de información entre conjuntos.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

SYSTEM = (
    "Eres una experta en adivinación: tarot, astrología, numerología y "
    "quiromancia. Respondes con rigor, claridad y empatía, siempre en "
    "español."
)

INSTRUCTION_TEMPLATES = [
    "Explica en detalle: {topic}.",
    "¿Qué significa {topic}?",
    "Como experta en adivinación, desarróllame {topic}.",
    "Explícame {topic} de forma clara y completa.",
]

BOILERPLATE_HEADINGS = {
    "menú", "menu", "inicio", "home", "contacto", "contact",
    "política de privacidad", "politica de privacidad", "aviso legal",
    "cookies", "política de cookies", "registrarse", "iniciar sesión",
    "login", "publicidad", "anuncios", "quienes somos", "acerca de",
    "footer", "pie de página", "pie de pagina", "categorías", "categorias",
    "buscar", "search", "navegación", "navegacion", "compartir",
    "comentarios", "deja un comentario", "noticias",
    "artículos relacionados", "articulos relacionados", "suscríbete",
    "suscribete", "newsletter", "índice", "indice", "tabla de contenidos",
    "lo que aprenderás", "lo que aprenderas", "curso", "inmersivo",
    "reserva", "precio", "comprar", "descarga gratis", "preguntas frecuentes",
    "reseñas", "resenas", "testimonios", "sobre la autora", "sobre el autor",
}

JUNK_BODY_MARKERS = (
    "sacred-texts", "j.b. hare", "press the reload button",
    "botón recargar", "please enable javascript",
    "javascript enabled", "javascript habilitado",
    "for entertainment purposes only",
    "solo con fines de entretenimiento",
)
STRONG_JUNK_MARKERS = (
    "sacred-texts", "j.b. hare", "press the reload button", "botón recargar",
)


def is_junk_body(body: str) -> bool:
    """Descarta cuerpos que son navegación/copyright de una web."""
    low = body.lower()
    if any(marker in low for marker in STRONG_JUNK_MARKERS):
        return True
    return sum(1 for marker in JUNK_BODY_MARKERS if marker in low) >= 2


BAD_TOPIC_RE = re.compile(
    r"^(secci[oó]n\s*\d+|§\s*\d+|parte\s*\d+|cap[ií]tulo\s*\d+)\b"
    r"|^(referencias?|v[eé]ase tambi[eé]n|enlaces? externos?|bibliograf[ií]a"
    r"|notas?|categor[ií]as?|lecturas? adicionales|fuentes?|galer[ií]a"
    r"|men[uú]|televisi[oó]n|radio|internet|libros?|revistas?"
    r"|pel[ií]culas?|series?|videojuegos?)\b"
    r"|^(lo que aprender[aá]s|curso|inmersi[oó]n|inmersivo|reserva|precio"
    r"|comprar|descarga gratis|preguntas frecuentes|rese[ñn]as|testimonios"
    r"|sobre la autor[ae]|tu propia tirada)\b",
    re.IGNORECASE,
)

# Términos propios del dominio: su sola aparición ya ancla la pregunta.
STRONG_TERMS = (
    "tarot", "tarotista", "arcano", "arcanos", "baraja del tarot",
    "tirada", "tiradas", "cartomancia", "cartomántica",
    "astrología", "astrologia", "astrólogo", "carta astral", "carta natal",
    "horóscopo", "horoscopo", "zodiaco", "zodíaco", "ascendente",
    "descendente", "trígono", "trigono", "sextil", "cuadratura",
    "conjunción", "oposición", "numerología", "numerologia", "numerólogo",
    "camino de vida", "quiromancia", "quiromántica", "palmistry",
    "línea de la vida", "línea del corazón", "línea de la cabeza",
    "monte de venus", "runa", "runas", "futhark", "iching", "i ching",
    "hexagrama", "lenormand", "kipper", "sibila", "adivinación",
    "adivinacion", "oráculo", "oraculo", "esoterismo", "ocultismo",
    "videncia", "vidente",
)
# Términos cotidianos que solo cobran sentido con anclaje fuerte.
WEAK_TERMS = (
    "carta", "cartas", "baraja", "mazo", "astral", "signo", "signos",
    "planeta", "planetas", "casa", "casas", "aspecto", "sol", "luna",
    "mercurio", "venus", "marte", "júpiter", "jupiter", "saturno",
    "urano", "neptuno", "plutón", "pluton", "aries", "tauro", "géminis",
    "geminis", "cáncer", "cancer", "leo", "virgo", "libra", "escorpio",
    "sagitario", "capricornio", "acuario", "piscis", "palma", "mano",
    "manos", "adivino", "adivina", "esotérico", "esoterico", "mística",
    "mistica", "destino",
)
DOMAIN_TERMS = STRONG_TERMS + WEAK_TERMS

DOMAIN_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in DOMAIN_TERMS) + r")\b",
    re.IGNORECASE,
)
STRONG_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in STRONG_TERMS) + r")\b",
    re.IGNORECASE,
)
WEAK_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in WEAK_TERMS) + r")\b",
    re.IGNORECASE,
)


def _strong_raw(text: str) -> set[str]:
    return {m.group(1).lower() for m in STRONG_RE.finditer(text or "")}


def _weak_set(text: str) -> set[str]:
    return {m.group(1).lower() for m in WEAK_RE.finditer(text or "")}


def _strong_set(text: str) -> set[str]:
    """Fuertes de un texto; «oposición» sola no cuenta como fuerte."""
    s = _strong_raw(text)
    return set() if s == {"oposición"} else s


def domain_hits(text: str) -> set[str]:
    """Términos del dominio distintos presentes en un texto."""
    return {m.group(1).lower() for m in DOMAIN_RE.finditer(text or "")}


def domain_score(text: str) -> tuple[int, int]:
    """(fuertes, débiles) del dominio en un texto."""
    return (len(_strong_set(text)), len(_weak_set(text)))


def is_relevant(topic: str, body: str, doc: str, min_terms: int = 2) -> bool:
    """Relevante si fuertes >= min_terms, o fuertes >= 1 y débiles >= min_terms.
    Los débiles solos nunca bastan; min_terms <= 0 desactiva el filtro."""
    if min_terms <= 0:
        return True
    fuertes_set = _strong_raw(body) | _strong_raw(topic)
    if fuertes_set == {"oposición"}:
        fuertes_set = set()
    fuertes = len(fuertes_set)
    debiles = len(_weak_set(body) | _weak_set(topic))
    return fuertes >= min_terms or (fuertes >= 1 and debiles >= min_terms)


PT_MARKERS = ("ção", "ções", " não ", " você ", " também ", " são ",
              " uma ", " pelo ", " pela ", "ê", " muito ", " mais ")
IT_MARKERS = (" gli ", " della ", " dei ", " sono ", " perché ", " che ",
              " è ", " il ", "zione")
ES_MARKERS = (" el ", " los ", " las ", " del ", " que ", "ción", "ñ",
              " está ", " pero ")


def es_puro(texto: str) -> bool:
    """False si los marcadores portugueses/italianos superan el 40 % de los
    marcadores idiomáticos en las primeras 3.000 palabras (stdlib, sin red)."""
    ventana = " ".join((texto or "").split()[:3000]).lower()
    pt = sum(ventana.count(m) for m in PT_MARKERS)
    it = sum(ventana.count(m) for m in IT_MARKERS)
    es = sum(ventana.count(m) for m in ES_MARKERS)
    total = pt + it + es
    if total == 0:
        return True
    return (pt + it) <= 0.4 * total


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
EMPTY_LINK_RE = re.compile(r"\[\]\([^)]*\)")
# Diana de un enlace markdown que tolera paréntesis anidados en la URL y un
# título entre comillas (p. ej. «...Oros_(naipe)&action=edit "Editar...").»
_LINK_TARGET = r'(?:[^()\s]|\([^)]*\))*(?:\s+"[^"]*")?'
# Centinelas para los corchetes escapados de markdown (\[ \]) y tratarlos luego.
_ESC_OPEN, _ESC_CLOSE = "\uE000", "\uE001"
CITA_LINK_RE = re.compile(r"\[(?:\uE000\d+\uE001|\d+)\]\(" + _LINK_TARGET + r"\)")
CITA_BARE_RE = re.compile(r"\[(?:\uE000\d+\uE001|\d+)\]|\uE000\d+\uE001")
EDIT_LINK_RE = re.compile(
    r"\[(?:\uE000?editar\uE001?|editar)\]\(" + _LINK_TARGET + r"\)", re.IGNORECASE)
EDIT_BARE_RE = re.compile(
    r"\[\uE000?editar\uE001?\]|\uE000editar\uE001", re.IGNORECASE)
LINK_RE = re.compile(r"\[([^\]]+)\]\(" + _LINK_TARGET + r"\)")
# Rabo que queda cuando un enlace de edición no cierra bien: «&action=edit...")».
EDIT_RESIDUE_RE = re.compile(r'&action=edit(?:&section=\d+)?(?:\s*"[^"]*")?\)?')
# Líneas que tras limpiar solo contienen _ * > sueltos.
JUNK_LINE_RE = re.compile(r"[_*> \t]+")
# Botones de tienda, con o sin _/* alrededor y con o sin flecha →/».
BUTTON_RE = re.compile(
    r"[_*]*\s*(?:ver\s+productos|ver\s+m[áa]s|comprar\s+ahora|"
    r"a[nñ]adir\s+al\s+carrito|suscr[ií]bete|leer\s+m[áa]s)"
    r"\s*(?:→|»)?\s*[_*]*",
    re.IGNORECASE,
)
# Resto de enlace «](http…)» sin corchete de apertura.
STRAY_LINK_RE = re.compile(r"\]\((?:https?://|www\.|/)[^)]*\)")


def clean_inline(text: str) -> str:
    """Elimina enlaces, énfasis y backticks de un encabezado."""
    text = LINK_RE.sub(r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    return text.strip()


def clean_body(text: str) -> str:
    """Limpia el cuerpo: quita imágenes, enlaces de cita y de edición
    (también con corchetes escapados y paréntesis en la URL), convierte los
    enlaces restantes a texto plano, borra restos de «action=edit» y las
    líneas que quedan solo con _ * > sueltos, y colapsa líneas en blanco."""
    text = IMAGE_RE.sub("", text)
    text = text.replace("\\[", _ESC_OPEN).replace("\\]", _ESC_CLOSE)
    text = CITA_LINK_RE.sub("", text)
    text = EDIT_LINK_RE.sub("", text)
    text = EMPTY_LINK_RE.sub("", text)
    text = CITA_BARE_RE.sub("", text)
    text = EDIT_BARE_RE.sub("", text)
    text = LINK_RE.sub(r"\1", text)
    text = EDIT_RESIDUE_RE.sub("", text)
    text = BUTTON_RE.sub("", text)
    text = STRAY_LINK_RE.sub("", text)
    text = text.replace(_ESC_OPEN, "").replace(_ESC_CLOSE, "")
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = []
    blank = 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        if ln.strip() and JUNK_LINE_RE.fullmatch(ln):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def humanize(slug: str) -> str:
    """Convierte un nombre de fichero en un tema legible."""
    slug = Path(slug).stem
    slug = slug.replace("-", " ").replace("_", " ")
    slug = re.sub(r"\s+", " ", slug).strip()
    return slug or "este tema"


def split_sections(md: str) -> list[tuple[str, str]]:
    """Trocea markdown en (tema, cuerpo) usando los encabezados ATX."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    current_topic: str | None = None
    current: list[str] = []
    saw_heading = False

    for line in md.splitlines():
        match = HEADING_RE.match(line)
        if match:
            saw_heading = True
            if current_topic is not None:
                body = clean_body("\n".join(current))
                sections.append((" > ".join(t for _, t in stack), body))
            level = len(match.group(1))
            title = clean_inline(match.group(2))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_topic = title
            current = []
        elif current_topic is not None:
            current.append(line)

    if current_topic is not None:
        body = clean_body("\n".join(current))
        sections.append((" > ".join(t for _, t in stack), body))

    if not saw_heading:
        body = clean_body(md)
        if body:
            sections.append(("", body))

    return sections


def is_boilerplate(topic: str) -> bool:
    """Descarta encabezados de navegación/pie/suscríbete."""
    norm = topic.strip().lower().strip(".:")
    if norm in BOILERPLATE_HEADINGS:
        return True
    parts = [p.strip().lower().strip(".:") for p in topic.split(">")]
    return any(p in BOILERPLATE_HEADINGS for p in parts)


def is_bad_topic(topic: str) -> bool:
    """Rechaza si ALGÚN segmento de la ruta «A > B > C» es una cabecera mala
    (navegación, referencias o promoción), no solo el inicio."""
    for part in topic.split(">"):
        norm = part.strip().lower().strip(".:")
        if not norm:
            continue
        if norm in BOILERPLATE_HEADINGS or BAD_TOPIC_RE.search(norm):
            return True
    return False


def load_blocked(manifest_path: Path) -> set[str]:
    """Devuelve el conjunto de URLs marcadas como bloqueadas/incompatibles."""
    if not manifest_path.exists():
        return set()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    blocked = set()
    for entry in data:
        estado = str(entry.get("estado", "")).lower()
        if estado in {"bloqueado", "incompatible", "excluido"}:
            blocked.add(str(entry.get("url", "")))
    return blocked


def iter_markdown(raw_dir: Path) -> list[tuple[str, str]]:
    """Recorre `raw_dir` y devuelve [(ruta_relativa, texto)]."""
    files = []
    for path in sorted(raw_dir.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(raw_dir))
        files.append((rel, text))
    return files


def build_pairs(doc: str, md: str, rng: random.Random,
                min_chars: int, max_chars: int,
                min_domain_terms: int = 2) -> list[dict]:
    """Convierte un documento markdown en pares ShareGPT."""
    pairs = []
    for topic, body in split_sections(md):
        topic = clean_inline(topic or humanize(doc))
        if not topic or is_boilerplate(topic) or is_bad_topic(topic):
            continue
        if len(body) < min_chars or len(body) > max_chars:
            continue
        if is_junk_body(body):
            continue
        if not is_relevant(topic, body, doc, min_domain_terms):
            continue
        if not es_puro(body):
            continue
        template = rng.choice(INSTRUCTION_TEMPLATES)
        human = template.format(topic=topic)
        pairs.append({
            "conversations": [
                {"from": "system", "value": SYSTEM},
                {"from": "human", "value": human},
                {"from": "gpt", "value": body},
            ]
        })
    return pairs


def dedupe(pairs: list[dict]) -> list[dict]:
    """Elimina pares (instrucción, respuesta) exactamente duplicados."""
    seen = set()
    out = []
    for pair in pairs:
        key = (pair["conversations"][1]["value"],
               pair["conversations"][2]["value"])
        if key in seen:
            continue
        seen.add(key)
        out.append(pair)
    return out


def write_jsonl(path: Path, pairs: list[dict]) -> None:
    """Escribe una lista de pares como JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Convierte el corpus markdown de Firecrawl a JSONL ShareGPT."
    )
    parser.add_argument("--raw", default="corpus/raw",
                        help="Directorio con los .md extraídos (default: corpus/raw)")
    parser.add_argument("--out", default="corpus",
                        help="Directorio de salida de train/val (default: corpus)")
    parser.add_argument("--ratio", type=float, default=0.9,
                        help="Proporción de entrenamiento (default: 0.9)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Semilla para barajar (default: 42)")
    parser.add_argument("--min-chars", type=int, default=40,
                        help="Longitud mínima de un cuerpo (default: 40)")
    parser.add_argument("--max-chars", type=int, default=4000,
                        help="Longitud máxima de un cuerpo (default: 4000)")
    parser.add_argument("--manifest", default="corpus/manifest.json",
                        help="Manifest de Firecrawl para saltar URLs bloqueadas")
    parser.add_argument("--min-domain-terms", type=int, default=2,
                        help="Términos del dominio exigidos para aceptar un par "
                             "(0 desactiva el filtro; default: 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe ficheros, solo informa de los conteos")
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw)
    out_dir = Path(args.out)
    manifest_path = Path(args.manifest)

    if not raw_dir.is_dir():
        print(f"ERROR: no existe el directorio {raw_dir}")
        return 1

    blocked = load_blocked(manifest_path)
    rng = random.Random(args.seed)

    docs = iter_markdown(raw_dir)
    if blocked:
        docs = [(rel, text) for rel, text in docs if not any(
            b and b in rel for b in blocked)]

    by_doc: dict[str, list[dict]] = {}
    for rel, text in docs:
        pairs = build_pairs(rel, text, rng, args.min_chars, args.max_chars,
                            args.min_domain_terms)
        if pairs:
            by_doc[rel] = pairs

    doc_names = sorted(by_doc)
    rng.shuffle(doc_names)

    cutoff = max(1, int(len(doc_names) * args.ratio))
    train_docs = doc_names[:cutoff]
    val_docs = doc_names[cutoff:]

    train = dedupe([p for d in train_docs for p in by_doc[d]])
    val = dedupe([p for d in val_docs for p in by_doc[d]])

    print(f"Documentos escaneados: {len(docs)}")
    print(f"Documentos con pares: {len(doc_names)}")
    print(f"Pares en train: {len(train)}")
    print(f"Pares en val:   {len(val)}")

    if not args.dry_run:
        write_jsonl(out_dir / "train.jsonl", train)
        write_jsonl(out_dir / "val.jsonl", val)
        print(f"Escritos: {out_dir / 'train.jsonl'} y {out_dir / 'val.jsonl'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
