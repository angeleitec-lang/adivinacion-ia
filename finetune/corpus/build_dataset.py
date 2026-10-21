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
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

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
    "Háblame de {topic}.",
    "¿Puedes contarme más sobre {topic}?",
    "¿Qué hay que saber sobre {topic}?",
    "Dame una explicación completa de {topic}.",
    "Quiero entender mejor {topic}, ¿me lo explicas?",
    "¿Qué es {topic} y por qué importa?",
    "Profundiza en {topic} para mí.",
    "Cuéntame todo lo posible sobre {topic}.",
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


def density_fuertes(text: str) -> float:
    """Ocurrencias de términos fuertes por cada 1.000 palabras del texto.

    Devuelve 0.0 si el texto no tiene palabras (nunca divide por cero) o si su
    único término fuerte distinto es «oposición», que no ancla el dominio."""
    palabras = len((text or "").split())
    if palabras == 0:
        return 0.0
    ocurrencias = [m.group(1).lower() for m in STRONG_RE.finditer(text or "")]
    if set(ocurrencias) == {"oposición"}:
        return 0.0
    return len(ocurrencias) * 1000.0 / palabras


def is_relevant(topic: str, body: str, doc: str, min_terms: int = 2,
                min_density: float = 0.0) -> bool:
    """Relevante si fuertes >= min_terms, o fuertes >= 1 y débiles >= min_terms.
    Los débiles solos nunca bastan; min_terms <= 0 desactiva ese filtro.
    min_density exige fuertes por 1.000 palabras de cuerpo (se aplica sobre
    `body`, no sobre el tema); 0 lo desactiva."""
    if min_density > 0 and density_fuertes(body) < min_density:
        return False
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
# Reclamos comerciales: se elimina la frase entera que los contiene.
COMMERCIAL_RE = re.compile(
    r"(?:ver\s+productos|ver\s+m[áa]s|comprar\s+ahora|"
    r"a[nñ]adir\s+al\s+carrito|suscr[ií]bete|leer\s+m[áa]s|"
    r"descarga(?:r)?\s+gratis|"
    r"(?:compra|compre|comprar|adquiere|consigue|pide)\b"
    r"(?=[^.!?»\n]*(?:(?:nuestro|nuestra|nuestros|nuestras|tu|tus)\b|"
    r"\d+(?:[.,]\d+)?\s*(?:€|euros?|\$|USD)\b))|"
    r"(?:lee\s+tambi[ée]n|lee\s+m[áa]s|te\s+puede\s+interesar|"
    r"art[ií]culos\s+relacionados)\s*:)",
    re.IGNORECASE,
)
COMMERCIAL_END_RE = re.compile(r"[.!?](?=\s|$)|»")
COMMERCIAL_START_RE = re.compile(r"([.!?»]\s+)|([_*])")
# Resto de enlace «](http…)» sin corchete de apertura.
STRAY_LINK_RE = re.compile(r"\]\((?:https?://|www\.|/)[^)]*\)")


def _sin_frases_comerciales(text: str) -> str:
    """Elimina cada frase que contenga un reclamo comercial, desde su inicio
    hasta el punto, el salto de línea o el cierre de cita."""
    lineas = []
    for linea in text.splitlines():
        piezas = []
        inicio = 0
        while True:
            reclamo = COMMERCIAL_RE.search(linea, inicio)
            if not reclamo:
                piezas.append(linea[inicio:])
                break
            previo = linea[inicio:reclamo.start()]
            cortes = list(COMMERCIAL_START_RE.finditer(previo))
            if cortes:
                corte = cortes[-1]
                principio = inicio + (corte.end() if corte.group(1) else corte.start())
            else:
                principio = inicio
            final = COMMERCIAL_END_RE.search(linea, reclamo.end())
            fin = final.end() if final else len(linea)
            piezas.append(linea[inicio:principio])
            inicio = fin
        lineas.append("".join(piezas))
    return "\n".join(lineas)


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
    text = _sin_frases_comerciales(text)
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


GENERIC_TOPICS = {
    "inicio", "home", "pagina", "página", "introduccion", "introducción",
    "tema", "seccion", "sección", "indice", "índice", "otros", "otras",
    "general", "generales", "informacion", "información", "varios",
}


def tema_legible(topic: str, doc: str) -> str:
    """Devuelve un tema legible sin la ruta ``A > B > C`` ni puntuación duplicada."""
    segs = [s.strip() for s in topic.split(">")] if ">" in topic else [topic.strip()]
    segs = [s for s in segs if s]
    if not segs:
        return humanize(doc)
    ultimo = re.sub(r"[?.:]+$", "", re.sub(r"^[¿¡]+", "", segs[-1])).strip()
    primero = re.sub(r"[?.:]+$", "", re.sub(r"^[¿¡]+", "", segs[0])).strip()
    if not ultimo:
        return primero or humanize(doc)
    if len(ultimo) < 12 or ultimo.lower() in GENERIC_TOPICS:
        if primero and primero.lower() != ultimo.lower():
            return f"{ultimo} ({primero})"
    return ultimo


def split_sections(md: str, doc: str = "") -> list[tuple[str, str]]:
    """Trocea markdown en (tema, cuerpo) usando los encabezados ATX.
    El texto previo al primer encabezado se conserva como sección con título
    humanize(doc) en lugar de descartarse."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    current_topic: str | None = None
    current: list[str] = []
    intro: list[str] = []
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
        else:
            intro.append(line)

    if current_topic is not None:
        body = clean_body("\n".join(current))
        sections.append((" > ".join(t for _, t in stack), body))

    if saw_heading:
        intro_body = clean_body("\n".join(intro))
        if intro_body:
            sections.insert(0, (humanize(doc), intro_body))
    else:
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


def domain_of(url: str) -> str:
    """Nombre de dominio saneado para usar como carpeta."""
    netloc = urlparse(url).netloc
    return re.sub(r"[^A-Za-z0-9.\-]", "_", netloc) or "desconocido"


def slug_of(url: str) -> str:
    """Slug del path de la URL, apto para nombre de fichero."""
    path = unquote(urlparse(url).path).strip("/")
    if not path:
        return "index"
    parts = []
    for seg in path.split("/"):
        seg = re.sub(r"[^A-Za-z0-9]+", "_", seg).strip("_")
        if seg:
            parts.append(seg)
    return "_".join(parts)[-80:] or "index"


def _strip_collision(stem: str) -> str:
    """Quita el sufijo de colisión ``_ab12`` si lo hay."""
    m = re.match(r"^(?P<base>.+?)_[0-9a-f]{4}$", stem)
    return m.group("base") if m else stem


def is_blocked_rel(rel: str, blocked: set[str]) -> bool:
    """True si la ruta relativa coincide con una bloqueada (con o sin colisión)."""
    parts = rel.split("/")
    fn = parts[-1]
    stem = fn[:-3] if fn.endswith(".md") else fn
    base = _strip_collision(stem)
    norm = "/".join(parts[:-1] + [base + ".md"])
    return norm in blocked


def load_blocked(manifest_path: Path) -> set[str]:
    """Devuelve las rutas relativas esperadas de los documentos bloqueados."""
    if not manifest_path.exists():
        return set()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    if isinstance(data, dict):
        data = data.get("pages") or []
    if not isinstance(data, list):
        return set()
    blocked = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        estado = str(entry.get("estado", "")).lower()
        if estado in {"bloqueado", "incompatible", "excluido", "fallo"}:
            url = str(entry.get("url", ""))
            if not url:
                continue
            blocked.add(f"{domain_of(url)}/{slug_of(url)}.md")
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
                min_domain_terms: int = 2,
                min_density: float = 0.0) -> list[dict]:
    """Convierte un documento markdown en pares ShareGPT.

    min_density exige términos fuertes por 1.000 palabras de cuerpo (0 = no
    se aplica), para descartar secciones que solo rozan el dominio."""
    pairs = []
    for topic, body in split_sections(md, doc):
        topic = clean_inline(topic or humanize(doc))
        if not topic or is_boilerplate(topic) or is_bad_topic(topic):
            continue
        if len(body) < min_chars or len(body) > max_chars:
            continue
        if is_junk_body(body):
            continue
        if not is_relevant(topic, body, doc, min_domain_terms, min_density):
            continue
        if not es_puro(body):
            continue
        template = rng.choice(INSTRUCTION_TEMPLATES)
        human = template.format(topic=tema_legible(topic, doc))
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
        charla = pair.get("conversations") if isinstance(pair, dict) else None
        if not isinstance(charla, list) or len(charla) < 3:
            continue
        try:
            key = (unicodedata.normalize("NFC", charla[1]["value"]),
                   unicodedata.normalize("NFC", charla[2]["value"]))
        except (KeyError, TypeError):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(pair)
    return out


def _norm_humano(texto: str) -> str:
    return unicodedata.normalize(
        "NFC", re.sub(r"\s+", " ", texto or "").strip().lower())


def humanos_evaluacion(rutas) -> set[str]:
    """Humanos normalizados de los casos reservados de evaluación (T56, A3/C1)."""
    if isinstance(rutas, (str, Path)):
        rutas = [rutas]
    humanos: set[str] = set()
    for ruta in rutas or ():
        if not ruta or not Path(ruta).exists():
            continue
        with Path(ruta).open("r", encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    fila = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if not isinstance(fila, dict):
                    continue
                reservada = (fila.get("origen") == "evaluacion"
                             or str(fila.get("id", "")).startswith("eval-"))
                if not reservada:
                    continue
                for turno in fila.get("conversations") or []:
                    if isinstance(turno, dict) and turno.get("from") == "human":
                        humanos.add(_norm_humano(turno.get("value", "")))
    return humanos


def filtrar_evaluacion(pairs: list[dict], humanos: set[str]) -> list[dict]:
    """Descarta pares cuya pregunta coincida con un caso de evaluación."""
    if not humanos:
        return pairs
    out = []
    for pair in pairs:
        charla = pair.get("conversations") if isinstance(pair, dict) else None
        if isinstance(charla, list) and len(charla) > 1:
            human = _norm_humano((charla[1] or {}).get("value", ""))
            if human in humanos:
                continue
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
    parser.add_argument("--min-density", type=float, default=0.0,
                        help="Términos fuertes por 1.000 palabras de cuerpo "
                             "exigidos para aceptar un par (0 desactiva; "
                             "default: 0)")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe ficheros, solo informa de los conteos")
    parser.add_argument("--eval-casos", default=None,
                        help="JSONL del conjunto de evaluación (T56) a excluir")
    parser.add_argument("--license-filter", choices=["off", "strict"],
                        default="off",
                        help="strict exige license_filter.py (track T5) para "
                             "descartar licencias no compatibles (default: off)")
    args = parser.parse_args(argv)

    is_allowed = None
    if args.license_filter == "strict":
        try:
            from license_filter import is_allowed  # type: ignore
        except ImportError:
            print("license_filter.py no disponible (track T5)")
            return 2

    raw_dir = Path(args.raw)
    out_dir = Path(args.out)
    manifest_path = Path(args.manifest)

    if not raw_dir.is_dir():
        print(f"ERROR: no existe el directorio {raw_dir}")
        return 1

    blocked = load_blocked(manifest_path)
    rng = random.Random(args.seed)

    docs = iter_markdown(raw_dir)
    if is_allowed is not None:
        docs = [(rel, text) for rel, text in docs if is_allowed(rel)]
    if blocked:
        docs = [(rel, text) for rel, text in docs
                if not is_blocked_rel(rel, blocked)]

    by_doc: dict[str, list[dict]] = {}
    for rel, text in docs:
        pairs = build_pairs(rel, text, rng, args.min_chars, args.max_chars,
                            args.min_domain_terms, args.min_density)
        if pairs:
            by_doc[rel] = pairs

    doc_names = sorted(by_doc)
    rng.shuffle(doc_names)

    cutoff = max(1, int(len(doc_names) * args.ratio))
    train_docs = doc_names[:cutoff]
    val_docs = doc_names[cutoff:]

    train = dedupe([p for d in train_docs for p in by_doc[d]])
    val = dedupe([p for d in val_docs for p in by_doc[d]])

    reservados = humanos_evaluacion(args.eval_casos)
    if reservados:
        antes = len(train) + len(val)
        train = filtrar_evaluacion(train, reservados)
        val = filtrar_evaluacion(val, reservados)
        print(f"Pares de evaluación excluidos: {antes - len(train) - len(val)}")

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
