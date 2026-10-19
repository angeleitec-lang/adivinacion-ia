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


# ---------------------------------------------------------------------------
# Paso 2: respuesta del LLM (parser, validador y llamada con un reintento)
# ---------------------------------------------------------------------------

TIPOS_VALIDOS = {"conocimiento", "lectura_trabajada", "publicidad",
                 "relleno", "ficcion", "otro"}

IDIOMAS_VALIDOS = {"es", "en", "otro"}

MAX_TEXTO_PROMPT = 6000

SISTEMA_PROMPT = (
    "Eres un juez documental de textos sobre tarot, baraja española, "
    "astrología y numerología. Clasifica el fragmento que recibes y "
    "etiqueta qué entidades y facetas documenta. Responde SOLO con un "
    "objeto JSON válido, sin texto adicional."
)


def _extraer_json(texto):
    """Primer objeto JSON del texto: bloque ```json, bloque ``` o llaves."""
    for marca in ("```json", "```"):
        inicio = texto.find(marca)
        if inicio != -1:
            desde = inicio + len(marca)
            fin = texto.find("```", desde)
            if fin != -1:
                try:
                    return json.loads(texto[desde:fin].strip())
                except json.JSONDecodeError:
                    pass
    inicio = texto.find("{")
    if inicio != -1:
        nivel = 0
        for i in range(inicio, len(texto)):
            if texto[i] == "{":
                nivel += 1
            elif texto[i] == "}":
                nivel -= 1
                if nivel == 0:
                    try:
                        return json.loads(texto[inicio:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("No se encontró JSON válido en la respuesta")


def parsear_respuesta(texto, candidatos):
    """Extrae y valida el juicio del LLM contra la lista de candidatos.

    Devuelve un dict normalizado con `tipo` (en TIPOS_VALIDOS), `calidad`
    (entero 1-5), `idioma` (es|en|otro) y `entidades` con solo ids de
    `candidatos` y facetas de `FACETAS_POR_FAMILIA` de su familia. Las
    entidades o facetas inventadas se descartan sin error; un JSON ilegible
    o campos obligatorios ausentes/inválidos lanzan ValueError.
    """
    datos = _extraer_json(texto)
    if not isinstance(datos, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    tipo = datos.get("tipo")
    if tipo not in TIPOS_VALIDOS:
        raise ValueError("Campo «tipo» ausente o inválido: %r" % (tipo,))
    calidad = datos.get("calidad")
    if isinstance(calidad, bool) or not isinstance(calidad, (int, float)) \
            or not 1 <= int(calidad) <= 5:
        raise ValueError("Campo «calidad» fuera de 1-5: %r" % (calidad,))
    calidad = int(calidad)
    idioma = datos.get("idioma")
    if idioma not in IDIOMAS_VALIDOS:
        idioma = "otro"
    crudo = datos.get("entidades")
    if not isinstance(crudo, list):
        raise ValueError("Campo «entidades» ausente o no es lista")
    familias = {c["entidad_id"]: c["familia"] for c in candidatos}
    entidades = []
    for ent in crudo:
        if not isinstance(ent, dict):
            continue
        entidad_id = ent.get("entidad_id")
        if entidad_id not in familias:
            continue
        permitidas = cobertura.FACETAS_POR_FAMILIA[familias[entidad_id]]
        facetas = ent.get("facetas")
        limpias = []
        if isinstance(facetas, list):
            for faceta in facetas:
                if faceta in permitidas and faceta not in limpias:
                    limpias.append(faceta)
        entidades.append({"entidad_id": entidad_id, "facetas": limpias})
    return {"tipo": tipo, "calidad": calidad, "idioma": idioma,
            "entidades": entidades}


def construir_prompt(seccion, candidatos):
    """(sistema, usuario) para juzgar una sección con sus candidatos."""
    lineas = []
    for c in candidatos:
        facetas = ", ".join(cobertura.FACETAS_POR_FAMILIA[c["familia"]])
        lineas.append('- %s (%s, familia %s). Facetas permitidas: %s'
                      % (c["entidad_id"], c["nombre"], c["familia"], facetas))
    texto = (seccion.get("texto") or "")[:MAX_TEXTO_PROMPT]
    usuario = (
        "FRAGMENTO (título: %s):\n%s\n\n"
        "CANDIDATOS (elige SOLO entre estos ids y sus facetas permitidas):\n%s\n\n"
        'Responde con JSON: {"tipo":"conocimiento|lectura_trabajada|'
        'publicidad|relleno|ficcion|otro","calidad":1-5,"idioma":"es|en|otro",'
        '"entidades":[{"entidad_id":"...","facetas":["..."]}]}'
        % (seccion.get("titulo") or "(sin título)", texto, "\n".join(lineas)))
    return SISTEMA_PROMPT, usuario


def juzgar_seccion(cliente, seccion, candidatos, reintentos=1):
    """Juzga una sección con el LLM. Un JSON inválido admite `reintentos`
    llamadas más; si persiste el fallo, devuelve `{"tipo": "error", ...}`.
    """
    sistema, usuario = construir_prompt(seccion, candidatos)
    motivo = None
    llamadas = 0
    for intento in range(reintentos + 1):
        try:
            respuesta = cliente.chat(sistema, usuario)
            llamadas += 1
            juicio = parsear_respuesta(respuesta, candidatos)
            juicio["llamadas"] = llamadas
            return juicio
        except ValueError as exc:
            motivo = str(exc)
            if intento < reintentos:
                usuario = (usuario + "\n\n[INTENTO %d FALLÓ: %s]\n"
                           "Responde SOLO con el JSON corregido."
                           % (intento + 1, exc))
        except Exception as exc:  # fallo de red u otro del endpoint
            llamadas += 1
            motivo = "fallo de llamada: %s" % exc
            break
    return {"tipo": "error", "calidad": 0, "idioma": "otro",
            "entidades": [], "motivo": motivo, "llamadas": llamadas}


# ---------------------------------------------------------------------------
# Verificación de anclaje por faceta
# ---------------------------------------------------------------------------

# Palabras clave (en forma normalizada por cartas.norm: minúsculas y sin
# tildes) que deben aparecer en el texto de la sección para aceptar la faceta.
# `None` significa exenta: no exige palabra clave (lo son `significado_general`
# y `simbolismo`, que todo texto de entidad documenta de facto).
PALABRAS_CLAVE_FACETA = {
    "significado_general": None,
    "simbolismo": None,
    "luz_sombra": ["luz", "sombra", "positiv", "negativ", "buen lado",
                   "mal lado"],
    "derecha_invertida": ["invertid", "al reves", "reves"],
    "amor": ["amor", "pareja", "relacion", "sentimental", "corazon",
             "matrimonio", "afectiv"],
    "trabajo": ["trabajo", "empleo", "carrera", "profesion", "laboral",
                "negocio", "oficio"],
    "dinero": ["dinero", "finanzas", "financier", "economic", "riqueza",
               "ingresos", "abundancia", "patrimonio"],
    "salud": ["salud", "enfermedad", "cuerpo", "bienestar", "fisico",
              "vitalidad"],
    "espiritual": ["espiritual", "espiritu", "meditacion", "karma",
                   "divino", "sagrado", "trascendencia"],
    "correspondencias": ["correspondencia", "regencia", "regido",
                         "elemento", "arbol de la vida", "hebreo",
                         "astrolog", "planeta gobernante"],
    "consejo_practico": ["consejo", "recomendacion", "sugiere", "practico",
                         "que hacer", "conviene", "procura"],
    "ejemplo_de_uso": ["ejemplo", "tirada", "ejercicio", "caso practico",
                       "en la practica", "consulta real"],
}


def facetas_ancladas(facetas, texto):
    """Subconjunto de `facetas` cuyo anclaje léxico supera el texto.

    Las facetas sin entrada o con lista vacía se consideran exentas. El texto
    se normaliza con `cartas.norm` (minúsculas, sin tildes), igual que las
    palabras clave de la constante.
    """
    tn = _norm(texto)
    aceptadas = []
    for faceta in facetas:
        claves = PALABRAS_CLAVE_FACETA.get(faceta)
        if not claves or any(clave in tn for clave in claves):
            if faceta not in aceptadas:
                aceptadas.append(faceta)
    return aceptadas
