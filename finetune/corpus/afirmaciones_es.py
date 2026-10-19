#!/usr/bin/env python3
"""Extractor de afirmaciones atómicas en español (pista A6, track T29).

Convierte cada evidencia de `evidencias.jsonl` (esquema de `cobertura.py`)
en afirmaciones atómicas en español (una idea por afirmación, fiel al
texto, sin inventar), para construir luego la base de conocimiento por
consenso.

Diseño en tres pasos:
  1. Determinista (`texto_seccion`): localiza el texto de la sección de la
     evidencia en las páginas Markdown de `web_dir` (`<web_dir>/<dominio>/*.md`),
     verificando URL y `hash_seccion` con el mismo algoritmo de `juez.py`.
     Si no se puede localizar, devuelve `None` (se cuenta como `sin_texto`).
  2. LLM (`extraer_afirmaciones`): pide al modelo una lista JSON de
     afirmaciones cortas extraídas ÚNICAMENTE del texto.
  3. Validación determinista (`validar_afirmacion`): descarta lo que no
     comparte vocabulario con la sección, lo que excede límites de tamaño y
     lo que menciona otra carta cuando la faceta no es de combinación.
"""

from __future__ import annotations

import glob
import json
import os

import cartas
import juez

MAX_AFIRMACIONES = 12
MAX_PALABRAS = 40

# Palabras funcionales en español (sin tildes, como las deja `cartas.norm`).
_STOPWORDS = frozenset("""
de la que el en y a los del se las por un para con no su al lo como mas pero
sus le ya o este esta si porque entre cuando muy sin sobre tambien me mi mis
hasta donde desde todo todos toda todas nos durante uno una les ni contra otros
otras ese eso esos esas ante esto estos estas alguno alguna algunos algunas
otro otra yo ti tu tus te tanto tanta tantos tantas cual cuales cuanto cuanta
cuantos cuantas nada alguien nadie cada cierto cierta ciertos ciertas mismo
misma mismos mismas nuestro nuestra nuestros nuestras vuestro vuestra
mio mia mios mias tuyo tuya tuyos tuyas suyo suya suyos suyas son fue era
han has hay ha sido estar estan estaba tiene tienen tengo tienes somos sois
eres sera eran siendo tenido toda via
""".split())


# ---------------------------------------------------------------------------
# T29.1: localización del texto de la sección
# ---------------------------------------------------------------------------


class IndiceWeb:
    """Índice de secciones web por dominio: url -> lista de (hash, texto).

    Las páginas Markdown viven en `<web_dir>/<dominio>/*.md` con
    front-matter YAML (`url`, `dominio`). Cada fichero es una sección, y su
    hash se calcula con `juez.hash_seccion` para que coincida con el
    `hash_seccion` de las evidencias. El índice por dominio se construye la
    primera vez que se necesita y se reutiliza.
    """

    def __init__(self, web_dir):
        self.web_dir = web_dir
        self._cache = {}

    def _por_dominio(self, dominio):
        if dominio in self._cache:
            return self._cache[dominio]
        indice = {}
        patron = os.path.join(self.web_dir, dominio, "*.md")
        for ruta in sorted(glob.glob(patron)):
            try:
                with open(ruta, encoding="utf-8", errors="replace") as fh:
                    contenido = fh.read()
            except OSError:
                continue
            datos, cuerpo = juez._front_matter(contenido)
            seccion = dict(datos)
            seccion["texto"] = cuerpo
            if not seccion.get("url"):
                seccion["url"] = os.path.abspath(ruta)
            indice.setdefault(seccion["url"], []).append(
                (juez.hash_seccion(seccion), cuerpo))
        self._cache[dominio] = indice
        return indice

    def texto_por_hash(self, dominio, fuente_id, hash_seccion):
        """Texto de la sección cuyo hash coincide; None si no la hay."""
        for h, texto in self._por_dominio(dominio).get(fuente_id, []):
            if h == hash_seccion:
                return texto
        return None


def texto_seccion(evidencia, indice):
    """Texto de la sección de una evidencia, o `None` si no se localiza.

    `None` debe contarse como `sin_texto` en el informe.
    """
    dominio = evidencia.get("dominio")
    fuente_id = evidencia.get("fuente_id")
    hash_seccion = evidencia.get("hash_seccion")
    if not dominio or not fuente_id or not hash_seccion:
        return None
    return indice.texto_por_hash(dominio, fuente_id, hash_seccion)


# ---------------------------------------------------------------------------
# T29.2: extracción con LLM y validación determinista
# ---------------------------------------------------------------------------


def _mazo_de_entidad(entidad_id):
    """Mazo de una entidad de naipes; None si no es una carta."""
    if (entidad_id or "").startswith("tarot-"):
        return "tarot"
    if (entidad_id or "").startswith("naipe-"):
        return "espanol"
    return None


def es_combinacion(entidad_id, faceta):
    """Combinación: entidad compuesta (contiene `|`) o faceta de combinaciones."""
    return "|" in (entidad_id or "") or "combinacion" in (faceta or "")


def _tokens_clave(texto):
    """Tokens de contenido (>= 4 letras, sin stopwords) de un texto normalizado."""
    return [w for w in cartas.norm(texto).split()
            if len(w) >= 4 and w not in _STOPWORDS]


def compartir_vocabulario(afirmacion, texto_seccion):
    """True si la afirmación comparte vocabulario verificable con la sección.

    Con 1-2 tokens clave basta 1 coincidencia; con 3 o mas, al menos 2.
    Sin tokens clave no se puede verificar: False.
    """
    tokens = _tokens_clave(afirmacion)
    if not tokens:
        return False
    seccion = set(cartas.norm(texto_seccion).split())
    compartidas = sum(1 for t in tokens if t in seccion)
    necesario = 1 if len(tokens) <= 2 else 2
    return compartidas >= necesario


def menciona_otra_carta(afirmacion, entidad_id):
    """True si la afirmación menciona una carta distinta de `entidad_id`."""
    mazo = _mazo_de_entidad(entidad_id)
    if mazo is None:
        return False
    for m in cartas.extraer_cartas(afirmacion, mazo=mazo):
        if m["carta"]["id"] != entidad_id:
            return True
    return False


def validar_afirmacion(afirmacion, texto_seccion, entidad_id, faceta):
    """(True, None) si la afirmación pasa todas las reglas duras.

    Motivos de descarte: `vacia`, `longitud`, `vocabulario`, `otra_carta`.
    """
    if not afirmacion or not afirmacion.strip():
        return False, "vacia"
    if len(afirmacion.split()) > MAX_PALABRAS:
        return False, "longitud"
    if not compartir_vocabulario(afirmacion, texto_seccion):
        return False, "vocabulario"
    if not es_combinacion(entidad_id, faceta) and \
            menciona_otra_carta(afirmacion, entidad_id):
        return False, "otra_carta"
    return True, None


SISTEMA_AFIRMACIONES = (
    "Eres un extractor de conocimiento para un sistema de adivinación en "
    "español. Extraes afirmaciones atómicas fieles al texto de la fuente: "
    "cada afirmación debe poder verificarse en el texto dado y no contener "
    "información externa. Respondes solo en español estándar con tildes y "
    "solo con JSON válido."
)


def construir_prompt(entidad_id, faceta, texto, max_chars=6000):
    """(sistema, usuario) para pedir afirmaciones atómicas de una sección."""
    cuerpo = texto if len(texto) <= max_chars else texto[:max_chars] + " [...]"
    usuario = (
        "Entidad: {e}\nFaceta: {f}\n\n"
        "Texto de la fuente:\n\"\"\"\n{t}\n\"\"\"\n\n"
        "Extrae del texto una lista de afirmaciones atómicas sobre la "
        "entidad en la faceta indicada:\n"
        "1. Cada afirmación expresa una sola idea, en español estándar "
        "con tildes.\n"
        "2. Máximo 40 palabras por afirmación.\n"
        "3. Máximo 12 afirmaciones.\n"
        "4. Usa únicamente información presente en el texto; no inventes "
        "ni añadas conocimiento externo.\n"
        "5. Si el texto no aporta nada sobre esa faceta, devuelve la "
        "lista vacía.\n\n"
        'Responde SOLO con JSON válido de la forma '
        '{{"afirmaciones": ["...", "..."]}}'
    ).format(e=entidad_id, f=faceta, t=cuerpo)
    return SISTEMA_AFIRMACIONES, usuario


def validar_respuesta_afirmaciones(data):
    """Valida la forma de la respuesta del modelo; lanza ValueError si no."""
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    afirmaciones = data.get("afirmaciones")
    if not isinstance(afirmaciones, list):
        raise ValueError('Falta la lista "afirmaciones"')
    for a in afirmaciones:
        if not isinstance(a, str) or not a.strip():
            raise ValueError("Afirmación no textual o vacía")


def extraer_afirmaciones(cliente, entidad_id, faceta, texto):
    """Extrae y valida afirmaciones de una sección con el modelo dado.

    Devuelve `{"estado": "ok"|"error", "afirmaciones": [...],
    "descartadas": [(texto, motivo), ...]}`.
    """
    resultado = {"estado": "ok", "afirmaciones": [], "descartadas": []}
    sistema, usuario = construir_prompt(entidad_id, faceta, texto)
    try:
        data = cliente.chat_json(sistema, usuario,
                               validar_respuesta_afirmaciones)
    except Exception:
        resultado["estado"] = "error"
        return resultado
    crudas = data.get("afirmaciones") or []
    aceptadas = []
    for a in crudas:
        a = a.strip()
        vale, motivo = validar_afirmacion(a, texto, entidad_id, faceta)
        if not vale:
            resultado["descartadas"].append((a, motivo))
        elif len(aceptadas) < MAX_AFIRMACIONES:
            aceptadas.append(a)
        else:
            resultado["descartadas"].append((a, "exceso"))
    resultado["afirmaciones"] = aceptadas
    return resultado


def registro_afirmacion(evidencia, afirmacion):
    """Registro de una afirmación aceptada, con la procedencia de la evidencia."""
    return {
        "entidad_id": evidencia.get("entidad_id"),
        "faceta": evidencia.get("faceta"),
        "fuente_id": evidencia.get("fuente_id"),
        "dominio": evidencia.get("dominio"),
        "periodo": evidencia.get("periodo"),
        "calidad": evidencia.get("calidad"),
        "afirmacion": afirmacion,
    }
