#!/usr/bin/env python3
"""Juez LLM de evidencias (pista A5).

Toma secciones de libros (JSONL de `libros_segmentar.segmentar`) y páginas
web (Markdown con front-matter YAML de `web_extraer.guardar_markdown`) y
produce evidencias en el esquema de `cobertura.py`:
`{"entidad_id","faceta","fuente_id","dominio","idioma","periodo","calidad",
"tipo"}`.

Diseño en dos pasos:
  1. Determinista (`candidatos_seccion`): entidades plausibles de la sección
     usando `cartas.extraer_cartas` (tarot y baraja española), mapas de
     nombres ingleses de arcanos mayores, regex de signos/planetas/casas y
     números de numerología en contexto. Sin candidatos y sin entidad en el
     título, la sección se descarta sin llamar al LLM.
  2. LLM (`juzgar_seccion`): clasifica tipo/calidad/idioma y elige facetas
     SOLO entre los candidatos del paso 1 (anti-alucinación); JSON inválido
     admite un reintento y después queda como `error`.

Las facetas aceptadas deben superar la verificación de anclaje
(`PALABRAS_CLAVE_FACETA`): el texto de la sección debe contener alguna
palabra clave razonable de la faceta. `significado_general` y `simbolismo`
no exigen palabra clave.
"""

from __future__ import annotations

import hashlib
import json
import re

import cartas
import cobertura
import cobertura_dataset

# ---------------------------------------------------------------------------
# Normalización y mapas de nombres ingleses de arcanos mayores
# ---------------------------------------------------------------------------


def _norm(texto):
    """Minúsculas, sin tildes y con espacios simples (igual que cartas.norm)."""
    return cartas.norm(texto)


# Nombres ingleses corrientes de los 22 arcanos mayores → número. Los libros
# en inglés (Waite, Papus traducido) titular las secciones así; el catálogo
# de `cartas` solo cubre las formas españolas.
_MAYORES_EN = {
    "the fool": 1, "the magician": 2, "the magus": 2,
    "the high priestess": 3, "the priestess": 3, "the papess": 3,
    "the empress": 4, "the emperor": 5,
    "the hierophant": 6, "the pope": 6, "the high priest": 6,
    "the lovers": 7,
    "the chariot": 8, "strength": 9, "fortitude": 9,
    "the hermit": 10, "wheel of fortune": 11, "the wheel": 11,
    "justice": 12, "the hanged man": 13, "the hanging man": 13,
    "death": 14, "temperance": 15, "the devil": 16,
    "the tower": 17, "the house of god": 17,
    "the star": 18, "the moon": 19, "the sun": 20,
    "judgement": 21, "the resurrection": 21, "the world": 22,
}

# Títulos muy genéricos: estas palabras sueltas son nombres de carta ambiguos
# («Death», «Justice») y solo cuentan si aparecen en el título de la sección
# o con artículo/contexto tarot cerca (a cargo de `cartas.extraer_cartas`).
_MAYORES_EN_TITULO = dict(_MAYORES_EN)
_MAYORES_EN_CUERPO = {
    k: v for k, v in _MAYORES_EN.items()
    if k.startswith("the ") or k in ("wheel of fortune", "temperance",
                                     "strength", "judgement")}


def _mayor_en_ids(texto_norm):
    """Ids `tarot-mayor-NN` de nombres ingleses presentes en el texto."""
    ids = set()
    for nombre, numero in _MAYORES_EN.items():
        if re.search(r"(?<![a-z])" + re.escape(nombre) + r"(?![a-z])",
                     texto_norm):
            ids.add("tarot-mayor-%02d" % numero)
    return ids


# ---------------------------------------------------------------------------
# Paso 1: candidatos de entidad por sección
# ---------------------------------------------------------------------------

_POSICIONES_NUMERO = {
    "camino_de_vida": r"camino de vida",
    "destino": r"destino",
    "alma": r"numero del alma|alma\b",
    "personalidad": r"personalidad",
    "anio_personal": r"ano personal",
    "mes_personal": r"mes personal",
}

# Venus en casa 7 / Mercurio en la casa 3
_CASA_EN_RE = re.compile(
    r"\b(" + "|".join(cobertura.PLANETAS) + r")\b[^.]{0,40}?\bcasa\s+"
    r"(1[0-2]|[1-9])(?![0-9])")

# Sol en Leo; regex por planeta con cualquier signo a menos de 20 caracteres.
def _planeta_en_signo_ids(texto_norm):
    ids = set()
    for planeta in cobertura.PLANETAS:
        for signo in cobertura.SIGNOS:
            patron = (r"\b%s\b[^.]{0,20}?\b%s\b" % (planeta, signo))
            if re.search(patron, texto_norm):
                ids.add("%s|%s|planeta_en_signo" % (planeta, signo))
    return ids


def _aspecto_ids(texto_norm):
    """Aspectos cuando el texto nombra aspecto y dos planetas próximos."""
    ids = set()
    for aspecto in cobertura.ASPECTOS:
        for m in re.finditer(
                r"\b%s\b(?!\w)" % aspecto, texto_norm):
            ventana = texto_norm[max(0, m.start() - 40):m.end() + 40]
            nombrados = [p for p in cobertura.PLANETAS
                         if re.search(r"\b%s\b(?!\w)" % p, ventana)]
            if len(nombrados) >= 2:
                p1, p2 = sorted(nombrados[:2])
                ids.add("%s|%s|%s|aspecto" % (p1, aspecto, p2))
    return ids


def _numero_posicion_ids(texto_norm):
    """Números de numerología junto a una posición canónica."""
    ids = set()
    for posicion, patron in _POSICIONES_NUMERO.items():
        for m in re.finditer(patron, texto_norm):
            ventana = texto_norm[max(0, m.start() - 40):m.end() + 40]
            for nm in re.finditer(
                    r"(?<![0-9a-z])(1[0-9]|2[0-9]|3[0-9]|[1-9])(?![0-9a-z])",
                    ventana):
                n = int(nm.group(1))
                if n in cobertura.NUMEROS:
                    ids.add("%d|%s" % (n, posicion))
    return ids


def candidatos_seccion(seccion):
    """Candidatos de entidad para una sección, determinista y sin LLM.

    Devuelve una lista ordenada de `{"entidad_id","familia","nombre"}` sin
    duplicados. Se aceptan los campos `entidad_id`/`familia` que la página
    web ya traiga etiquetados en su front-matter.
    """
    titulo = _norm(seccion.get("titulo") or "")
    texto = _norm(seccion.get("texto") or "")
    cuerpo = texto if not titulo else titulo + "\n" + texto

    candidatos = {}

    def _alta(entidad_id, familia, nombre):
        candidatos[entidad_id] = {
            "entidad_id": entidad_id, "familia": familia, "nombre": nombre}

    catalogo = {e["entidad_id"]: e for e in cobertura.entidades()}
    etiquetado = seccion.get("entidad_id")
    if etiquetado in catalogo:
        e = catalogo[etiquetado]
        _alta(e["entidad_id"], e["familia"], e["nombre"])

    # Naipes (tarot y baraja española) en el cuerpo.
    for mazo, familia in (("tarot", "tarot"), ("espanol", "baraja_espanola")):
        for m in cartas.extraer_cartas(seccion.get("texto") or "",
                                       mazo=mazo):
            _alta(m["carta"]["id"], familia, m["carta"]["nombre"])
        entrada = cartas.normalizar_carta(seccion.get("titulo") or "",
                                          mazo=mazo)
        if entrada is not None:
            _alta(entrada["id"], familia, entrada["nombre"])

    # Arcanos mayores por nombre inglés: todos valen en el título; en el
    # cuerpo solo los inequívocos (con «the» o formas poco comunes).
    for entidad_id in _mayor_en_ids(titulo):
        _alta(entidad_id, "tarot", catalogo[entidad_id]["nombre"])
    numerados_cuerpo = {"tarot-mayor-%02d" % n
                        for n in _MAYORES_EN_CUERPO.values()}
    for entidad_id in _mayor_en_ids(texto):
        if entidad_id in numerados_cuerpo:
            _alta(entidad_id, "tarot", catalogo[entidad_id]["nombre"])

    # Astrología: signos, planetas en signo, planetas en casa y aspectos.
    hallazgos = cobertura_dataset._menciones_astro(seccion.get("texto") or "")
    for clave, dato in hallazgos.items():
        tipo, _, sid = clave.partition(":")
        if tipo == "signo":
            _alta("%s|signo" % sid, "astrologia", dato["nombre"])
    tn = cuerpo
    for entidad_id in _planeta_en_signo_ids(tn):
        _alta(entidad_id, "astrologia",
              catalogo.get(entidad_id, {}).get("nombre", entidad_id))
    for m in _CASA_EN_RE.finditer(tn):
        entidad_id = "%s|casa%d|planeta_en_casa" % (m.group(1),
                                                   int(m.group(2)))
        _alta(entidad_id, "astrologia",
              catalogo.get(entidad_id, {}).get("nombre", entidad_id))
    for entidad_id in _aspecto_ids(tn):
        _alta(entidad_id, "astrologia",
              catalogo.get(entidad_id, {}).get("nombre", entidad_id))

    # Numerología: número junto a una posición canónica.
    for entidad_id in _numero_posicion_ids(tn):
        _alta(entidad_id, "numerologia",
              catalogo.get(entidad_id, {}).get("nombre", entidad_id))

    return [candidatos[k] for k in sorted(candidatos)]
