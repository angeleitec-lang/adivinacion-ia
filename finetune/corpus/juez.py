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
import llm_client

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


import argparse
import glob
import os
import sys

# ---------------------------------------------------------------------------
# Fuentes, evidencias y procesamiento reanudable
# ---------------------------------------------------------------------------

_PERIODO_CORTE_ANIO = 1950

_RUTAS_META_POR_DEFECTO = (
    "fuentes_libros*.jsonl", "epubs_locales.jsonl")


def hash_seccion(seccion):
    """Identificador estable de la sección: hash del texto más su id."""
    id_parte = seccion.get("id_libro") or seccion.get("url") or ""
    numero = seccion.get("seccion", seccion.get("posicion", 0))
    base = "%s|%s|%s" % (id_parte, numero, seccion.get("texto") or "")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def cargar_meta_libros(rutas=None):
    """Metadatos de libros por id, desde los inventarios JSONL de knowledge.

    Cada entrada: {"anio","idioma","titulo","autor","periodo"}. Con `rutas`
    None se leen los inventarios por defecto (`fuentes_libros*.jsonl` y
    `epubs_locales.jsonl` en `finetune/knowledge`, junto a este fichero).
    """
    if rutas is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "knowledge")
        rutas = []
        for patron in _RUTAS_META_POR_DEFECTO:
            rutas.extend(sorted(glob.glob(os.path.join(base, patron))))
    meta = {}
    for ruta in rutas:
        try:
            fh = open(ruta, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    dato = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if not isinstance(dato, dict) or "id" not in dato:
                    continue
                anio = dato.get("anio")
                periodo = None
                if isinstance(anio, int):
                    periodo = ("clasica" if anio < _PERIODO_CORTE_ANIO
                               else "moderna")
                meta[dato["id"]] = {
                    "anio": anio,
                    "idioma": dato.get("idioma"),
                    "titulo": dato.get("titulo"),
                    "autor": dato.get("autor"),
                    "periodo": periodo,
                }
    return meta


def _idioma_corto(valor):
    return valor if valor in IDIOMAS_VALIDOS else None


def fuente_de_seccion(seccion, meta=None):
    """Datos de fuente de una sección: páginas web (con `url`) o libros."""
    meta = meta or {}
    if seccion.get("url"):
        return {
            "tipo": "web",
            "fuente_id": seccion["url"],
            "dominio": seccion.get("dominio") or "",
            "periodo": "moderna",
            "idioma": _idioma_corto(seccion.get("idioma")),
        }
    id_libro = seccion.get("id_libro") or ""
    datos = meta.get(id_libro, {})
    return {
        "tipo": "libro",
        "fuente_id": id_libro,
        "dominio": id_libro,
        "periodo": datos.get("periodo") or "moderna",
        "idioma": _idioma_corto(datos.get("idioma")),
    }


TIPOS_CON_EVIDENCIA = {"conocimiento", "lectura_trabajada"}


def evidencias_de_seccion(seccion, juicio, fuente):
    """Líneas de evidencias.jsonl para el juicio de una sección.

    Solo los tipos conocimiento y lectura_trabajada generan evidencias, y
    solo para las facetas que superan el anclaje léxico sobre el texto. Las
    lecturas trabajadas añaden `tipo_evidencia: "lectura"` para A6.
    """
    if juicio.get("tipo") not in TIPOS_CON_EVIDENCIA:
        return []
    idioma = fuente.get("idioma") or juicio.get("idioma") or "otro"
    tn = seccion.get("texto") or ""
    evidencia_hash = hash_seccion(seccion)
    lineas = []
    for ent in juicio.get("entidades", []):
        for faceta in facetas_ancladas(ent.get("facetas", []), tn):
            linea = {
                "entidad_id": ent["entidad_id"],
                "faceta": faceta,
                "fuente_id": fuente["fuente_id"],
                "dominio": fuente["dominio"],
                "idioma": idioma,
                "periodo": fuente["periodo"],
                "calidad": juicio.get("calidad", 0),
                "tipo": fuente["tipo"],
                "hash_seccion": evidencia_hash,
            }
            if juicio["tipo"] == "lectura_trabajada":
                linea["tipo_evidencia"] = "lectura"
            lineas.append(linea)
    return lineas


def _leer_jsonl(ruta):
    registros = []
    if not os.path.exists(ruta):
        return registros
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                registros.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return registros


def procesar_secciones(secciones, cliente, out_dir, meta=None, workers=1,
                       limite=None):
    """Juzga secciones y escribe `juicios.jsonl` y `evidencias.jsonl`.

    Reanudable: las secciones cuyo hash ya está en juicios.jsonl no vuelven
    a llamarse; si sus evidencias faltan, se regeneran del juicio guardado.
    `limite` recorta el número de secciones procesadas en esta pasada.
    Devuelve estadísticas {"juzgadas","llamadas","evidencias",
    "reaprovechadas","sin_candidatos","error"}.
    """
    if limite is not None:
        secciones = secciones[:limite]
    os.makedirs(out_dir, exist_ok=True)
    ruta_juicios = os.path.join(out_dir, "juicios.jsonl")
    ruta_evidencias = os.path.join(out_dir, "evidencias.jsonl")
    hechos = {}
    for registro in _leer_jsonl(ruta_juicios):
        if registro.get("hash"):
            hechos[registro["hash"]] = registro
    hashes_ev = {e.get("hash_seccion")
                 for e in _leer_jsonl(ruta_evidencias)}

    stats = {"juzgadas": 0, "llamadas": 0, "evidencias": 0,
             "reaprovechadas": 0, "sin_candidatos": 0, "error": 0}
    fh_juicios = open(ruta_juicios, "a", encoding="utf-8")
    fh_ev = open(ruta_evidencias, "a", encoding="utf-8")

    def _escribir_ev(lineas):
        for linea in lineas:
            fh_ev.write(json.dumps(linea, ensure_ascii=False) + "\n")
        if lineas:
            fh_ev.flush()

    try:
        pendientes = []
        for seccion in secciones:
            h = hash_seccion(seccion)
            if h in hechos:
                stats["reaprovechadas"] += 1
                if h not in hashes_ev:
                    lineas = evidencias_de_seccion(
                        seccion, hechos[h]["juicio"],
                        fuente_de_seccion(seccion, meta))
                    _escribir_ev(lineas)
                    stats["evidencias"] += len(lineas)
                continue
            candidatos = candidatos_seccion(seccion)
            if not candidatos:
                stats["sin_candidatos"] += 1
                continue
            pendientes.append((h, seccion, candidatos))

        def _trabajo(item):
            h, seccion, candidatos = item
            return h, seccion, candidatos, juzgar_seccion(cliente, seccion,
                                                          candidatos)

        resultados = []
        if pendientes:
            if workers and workers > 1 and len(pendientes) > 1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    resultados = list(pool.map(_trabajo, pendientes))
            else:
                resultados = [_trabajo(item) for item in pendientes]

        for h, seccion, candidatos, juicio in resultados:
            if juicio.get("tipo") == "error":
                stats["error"] += 1
            stats["juzgadas"] += 1
            stats["llamadas"] += juicio.get("llamadas", 0)
            registro = {
                "hash": h,
                "fuente_id": fuente_de_seccion(seccion, meta)["fuente_id"],
                "titulo": seccion.get("titulo"),
                "candidatos": [c["entidad_id"] for c in candidatos],
                "juicio": juicio,
            }
            fh_juicios.write(json.dumps(registro, ensure_ascii=False) + "\n")
            fh_juicios.flush()
            lineas = evidencias_de_seccion(
                seccion, juicio, fuente_de_seccion(seccion, meta))
            _escribir_ev(lineas)
            stats["evidencias"] += len(lineas)
            hashes_ev.add(h)
    finally:
        fh_juicios.close()
        fh_ev.close()
    return stats


# ---------------------------------------------------------------------------
# Lectura de secciones (autodetección libro/web), informe y CLI
# ---------------------------------------------------------------------------

_NOMBRE_FAMILIA = {
    "tarot": "Tarot",
    "baraja_espanola": "Baraja española",
    "astrologia": "Astrología",
    "numerologia": "Numerología",
}

_FAMILIA_DE = None


def _familia_de(entidad_id):
    """Familia de una entidad por id (catálogo de `cobertura.entidades`)."""
    global _FAMILIA_DE
    if _FAMILIA_DE is None:
        _FAMILIA_DE = {e["entidad_id"]: e["familia"]
                       for e in cobertura.entidades()}
    return _FAMILIA_DE.get(entidad_id, "desconocida")


def _front_matter(texto):
    """Separa el front-matter YAML simple (`clase: valor`) del cuerpo."""
    if not texto.startswith("---"):
        return {}, texto
    fin = texto.find("\n---", 3)
    if fin == -1:
        return {}, texto
    bloque = texto[3:fin].strip()
    cuerpo = texto[fin + 4:].lstrip("\n")
    datos = {}
    for linea in bloque.splitlines():
        if ":" not in linea:
            continue
        clave, valor = linea.split(":", 1)
        valor = valor.strip().strip('"').strip("'")
        datos[clave.strip()] = None if valor in ("", "None") else valor
    return datos, cuerpo


def _secciones_de_fichero(ruta):
    """Lee un fichero de entrada y devuelve sus secciones normalizadas."""
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        contenido = fh.read()
    if ruta.endswith(".jsonl"):
        secciones = []
        for linea in contenido.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                dato = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if (isinstance(dato, dict) and dato.get("texto")
                    and not dato.get("front_matter")):
                secciones.append(dato)
        return secciones
    if ruta.endswith((".md", ".markdown")):
        datos, cuerpo = _front_matter(contenido)
        seccion = dict(datos)
        seccion["texto"] = cuerpo
        seccion["chars"] = len(cuerpo)
        if not seccion.get("url"):
            seccion["url"] = os.path.abspath(ruta)
        if not seccion.get("dominio"):
            seccion["dominio"] = os.path.basename(
                os.path.dirname(os.path.abspath(ruta)))
        return [seccion]
    return []


def leer_secciones(ruta):
    """Todas las secciones de un fichero o directorio (recursivo, ordenado).

    JSONL: secciones de libro (se omiten las `front_matter: true`).
    Markdown con front-matter YAML: páginas web. Otros ficheros se ignoran.
    """
    rutas = []
    if os.path.isdir(ruta):
        for raiz, _, ficheros in os.walk(ruta):
            for nombre in sorted(ficheros):
                if nombre.endswith((".jsonl", ".md", ".markdown")):
                    rutas.append(os.path.join(raiz, nombre))
    else:
        rutas.append(ruta)
    secciones = []
    for r in sorted(rutas):
        secciones.extend(_secciones_de_fichero(r))
    return secciones


def _porcentaje(n, total):
    return (100.0 * n / total) if total else 0.0


def construir_informe(estadisticas, juicios, evidencias):
    """Texto Markdown del informe del juez (en español)."""
    juzgadas = len(juicios)
    tipos = {}
    llamadas = sum(r.get("juicio", {}).get("llamadas", 0) for r in juicios)
    for r in juicios:
        tipo = r.get("juicio", {}).get("tipo", "sin_juicio")
        tipos[tipo] = tipos.get(tipo, 0) + 1
    por_familia = {}
    calidades = []
    for ev in evidencias:
        familia = _NOMBRE_FAMILIA.get(_familia_de(ev.get("entidad_id")),
                                      "Otras")
        por_familia[familia] = por_familia.get(familia, 0) + 1
        if isinstance(ev.get("calidad"), (int, float)) and ev["calidad"]:
            calidades.append(ev["calidad"])
    calidad_media = (sum(calidades) / len(calidades)) if calidades else 0.0
    lineas = [
        "# Informe del juez de evidencias",
        "",
        "- Secciones juzgadas (histórico): %d" % juzgadas,
        "- Sin candidatos (descartadas sin llamada en esta pasada): %d"
        % estadisticas.get("sin_candidatos", 0),
        "- Juicios con error: %d" % estadisticas.get("error", 0),
        "- Llamadas al LLM: %d (media %.2f por sección juzgada)"
        % (llamadas, _porcentaje(llamadas, juzgadas) / 100.0
           if juzgadas else 0.0),
        "",
        "## Distribución de tipo",
        "",
    ]
    for tipo in sorted(tipos, key=lambda t: -tipos[t]):
        lineas.append("- %s: %d (%.1f %%)"
                      % (tipo, tipos[tipo],
                         round(_porcentaje(tipos[tipo], juzgadas), 1)))
    lineas += [
        "",
        "## Evidencias",
        "",
        "- Total de evidencias: %d" % len(evidencias),
        "- Calidad media de las evidencias: %.2f" % calidad_media,
        "",
        "| Familia | Evidencias |",
        "|---|---|",
    ]
    for familia in sorted(por_familia, key=lambda f: -por_familia[f]):
        lineas.append("| %s | %d |" % (familia, por_familia[familia]))
    return "\n".join(lineas) + "\n"


def escribir_informe(out_dir, estadisticas, ruta_informe=None):
    """Genera `juez_informe.md` a partir de los ficheros ya escritos."""
    if ruta_informe is None:
        ruta_informe = os.path.join(out_dir, "juez_informe.md")
    juicios = _leer_jsonl(os.path.join(out_dir, "juicios.jsonl"))
    evidencias = _leer_jsonl(os.path.join(out_dir, "evidencias.jsonl"))
    with open(ruta_informe, "w", encoding="utf-8") as fh:
        fh.write(construir_informe(estadisticas, juicios, evidencias))
    return ruta_informe


def _simular(sistema, usuario):
    """Cliente determinista para `--simulado`: primer candidato, sin facetas
    que exijan anclaje."""
    entidad = None
    for linea in usuario.splitlines():
        if linea.startswith("- ") and "(" in linea:
            entidad = linea[2:linea.index("(")].strip()
            break
    respuesta = {"tipo": "conocimiento", "calidad": 4, "idioma": "es",
                 "entidades": ([{"entidad_id": entidad,
                                 "facetas": ["significado_general"]}]
                                if entidad else [])}
    return "```json\n%s\n```" % json.dumps(respuesta, ensure_ascii=False)


def main(argv=None):
    """CLI del juez: `python corpus/juez.py --secciones DIR --out-dir DIR`."""
    parser = argparse.ArgumentParser(
        description="Jueza secciones de libros y páginas web y produce "
                    "evidencias para la matriz de cobertura.")
    parser.add_argument("--secciones", required=True,
                        help="directorio o fichero de secciones "
                             "(JSONL de libros o Markdown web)")
    parser.add_argument("--out-dir", required=True,
                        help="directorio de salida (evidencias.jsonl, "
                             "juicios.jsonl, juez_informe.md)")
    parser.add_argument("--limite", type=int, default=None,
                        help="máximo de secciones procesadas en esta pasada")
    parser.add_argument("--simulado", action="store_true",
                        help="usa un cliente determinista (pruebas, sin red)")
    parser.add_argument("--workers", type=int, default=4,
                        help="hilos de llamada al LLM (por defecto: 4)")
    parser.add_argument("--knowledge-dir", default=None,
                        help="directorio de inventarios de libros "
                             "(por defecto: finetune/knowledge)")
    args = parser.parse_args(argv)

    cliente = llm_client.LLMClient() if not args.simulado else \
        llm_client.LLMClient(simulado=_simular)
    rutas_meta = None
    if args.knowledge_dir:
        rutas_meta = []
        for patron in _RUTAS_META_POR_DEFECTO:
            rutas_meta.extend(sorted(glob.glob(
                os.path.join(args.knowledge_dir, patron))))
    meta = cargar_meta_libros(rutas_meta)
    secciones = leer_secciones(args.secciones)
    stats = procesar_secciones(secciones, cliente, args.out_dir, meta=meta,
                               workers=args.workers, limite=args.limite)
    ruta_informe = escribir_informe(args.out_dir, stats)
    print("Secciones: %d juzgadas, %d reaprovechadas, %d sin candidatos; "
          "%d evidencias nuevas, %d llamadas; informe en %s"
          % (stats["juzgadas"], stats["reaprovechadas"],
             stats["sin_candidatos"], stats["evidencias"],
             stats["llamadas"], ruta_informe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
