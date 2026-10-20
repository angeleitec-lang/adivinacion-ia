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

import argparse
import glob
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import cartas
import juez
import cobertura
from llm_client import LLMClient

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
    """True si la afirmación menciona una carta distinta de `entidad_id`.

    Se usa `contextual=False` a propósito: en un corpus de adivinación un
    nombre de naipe («la estrella», «el sol») casi siempre alude a la carta,
    y aquí prima no contaminar la entidad con afirmaciones de otra carta.
    """
    mazo = _mazo_de_entidad(entidad_id)
    if mazo is None:
        return False
    for m in cartas.extraer_cartas(afirmacion, mazo=mazo, contextual=False):
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


def _calidad_num(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def construir_prompt(entidad_id, faceta, texto, max_chars=6000):
    """(sistema, usuario) para pedir afirmaciones atómicas de una sección."""
    texto = "" if texto is None else str(texto)
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


def _chat_json_reintento(cliente, sistema, usuario, validar, reintentos=1):
    """Chat + parseo + validacion con un maximo de `reintentos` reintentos.

    Cada intento hace UNA peticion de red (sin los reintentos internos de
    `chat`, para que una peticion atascada no multiplique el tiempo: el
    `timeout` del cliente acota cada intento). En el reintento se anade el
    error al prompt, como hace `chat_json`. Lanza la ultima excepcion si se
    agotan los intentos.
    """
    ultima_exc = None
    for intento in range(reintentos + 1):
        try:
            texto = cliente.chat(sistema, usuario, max_reintentos=0)
            data = cliente._extraer_json(texto)
            validar(data)
            return data
        except Exception as e:
            ultima_exc = e
            if intento < reintentos:
                usuario = (
                    "%s\n\n[INTENTO %d FALLO: %s]\n"
                    "Responde SOLO con el JSON corregido."
                    % (usuario, intento + 1, e)
                )
    raise ValueError("JSON invalido tras %d intentos: %s"
                     % (reintentos + 1, ultima_exc))


def extraer_afirmaciones(cliente, entidad_id, faceta, texto):
    """Extrae y valida afirmaciones de una sección con el modelo dado.

    Devuelve `{"estado": "ok"|"error", "afirmaciones": [...],
    "descartadas": [(texto, motivo), ...]}`.
    """
    resultado = {"estado": "ok", "afirmaciones": [], "descartadas": []}
    sistema, usuario = construir_prompt(entidad_id, faceta, texto)
    try:
        data = _chat_json_reintento(cliente, sistema, usuario,
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


# ---------------------------------------------------------------------------
# T29.3: CLI reanudable e informe
# ---------------------------------------------------------------------------

DEFAULT_EVIDENCIAS = "/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl"
DEFAULT_WEB_DIR = "/Users/angelgonzalez/fase0/web"
DEFAULT_OUT_DIR = "/Users/angelgonzalez/fase0/afirmaciones"


def _catalogo_familias():
    """entidad_id -> familia según `cobertura.entidades()`."""
    return {e["entidad_id"]: e.get("familia")
            for e in cobertura.entidades() if e.get("entidad_id")}


def familia_de_entidad(entidad_id, catalogo=None):
    """Familia de una entidad, con reserva por sufijo si no está en el catálogo."""
    if catalogo is None:
        catalogo = _catalogo_familias()
    if entidad_id in catalogo:
        return catalogo[entidad_id]
    eid = entidad_id or ""
    if eid.startswith("tarot-"):
        return "tarot"
    if eid.startswith("naipe-"):
        return "baraja_espanola"
    if eid.endswith("|signo") or eid.endswith("|aspecto"):
        return "astrologia"
    if "|destino" in eid or "|alma" in eid or "|personalidad" in eid:
        return "numerologia"
    return "otra"


def _cargar_procesados(ruta):
    """Claves (hash_seccion, entidad_id, faceta) ya procesadas antes."""
    claves = set()
    if not os.path.exists(ruta):
        return claves
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            claves.add((d.get("hash_seccion"), d.get("entidad_id"),
                        d.get("faceta")))
    return claves


def _simulado_vacio(sistema, usuario):
    return '{"afirmaciones": []}'


def procesar_evidencia(evidencia, indice, cliente):
    """Procesa una evidencia: localiza texto y extrae afirmaciones."""
    texto = texto_seccion(evidencia, indice)
    if texto is None:
        return {"estado": "sin_texto", "afirmaciones": [], "descartadas": []}
    return extraer_afirmaciones(cliente, evidencia.get("entidad_id"),
                               evidencia.get("faceta"), texto)


def escribir_informe(ruta, stats):
    """Informe Markdown del estado de la extracción."""
    lineas = [
        "# Informe de afirmaciones (T29)",
        "",
        "- Evidencias procesadas: %d" % stats["procesadas"],
        "- Sin texto localizable (`sin_texto`): %d" % stats["sin_texto"],
        "- Errores del modelo: %d" % stats["errores"],
        "- Afirmaciones aceptadas: %d" % stats["afirmaciones"],
        "",
        "## Descartadas por motivo",
        "",
    ]
    if stats["descartadas"]:
        for motivo, n in sorted(stats["descartadas"].items(),
                               key=lambda kv: -kv[1]):
            lineas.append("- %s: %d" % (motivo, n))
    else:
        lineas.append("- (ninguna)")
    lineas += ["", "## Afirmaciones por familia", "",
               "| Familia | Afirmaciones |", "|---|---|"]
    if stats["por_familia"]:
        for familia, n in sorted(stats["por_familia"].items(),
                                key=lambda kv: -kv[1]):
            lineas.append("| %s | %d |" % (familia, n))
    else:
        lineas.append("| (ninguna) | 0 |")
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


def filtrar_min_calidad(evidencias, min_calidad):
    """Deja fuera las evidencias con calidad por debajo de `min_calidad`.

    Con `min_calidad` <= 0 no filtra nada. Una evidencia sin calidad cuenta
    como 0.
    """
    if not min_calidad or min_calidad <= 0:
        return list(evidencias)
    return [e for e in evidencias if _calidad_num(e.get("calidad")) >= min_calidad]


def ordenar_evidencias(evidencias, orden=None, familias=None, catalogo=None):
    """Ordena las evidencias para procesar primero lo mas valioso.

    - `orden="calidad"`: calidad descendente (5 antes que 4 y 3).
    - `familias=[...]`: las familias listadas van primero, en el orden dado;
      las demas despues.
    - Combinados: primero la prioridad de familia, luego la calidad.
    Sin ninguno de los dos, conserva el orden de entrada. El orden es estable.
    """
    if catalogo is None:
        catalogo = _catalogo_familias()
    if not orden and not familias:
        return list(evidencias)
    fam_list = list(familias) if familias else None

    def clave(i):
        ev = evidencias[i]
        partes = []
        if fam_list is not None:
            f = familia_de_entidad(ev.get("entidad_id"), catalogo)
            partes.append(fam_list.index(f) if f in fam_list else len(fam_list))
        if orden == "calidad":
            partes.append(-_calidad_num(ev.get("calidad")))
        partes.append(i)
        return tuple(partes)

    return [evidencias[i] for i in sorted(range(len(evidencias)), key=clave)]


def _log_progreso(stream, hechas, total, stats, inicio):
    """Linea de progreso a `stream`: ritmo, aceptadas, descartes y ETA."""
    transcurrido = time.time() - inicio
    ritmo = hechas / (transcurrido / 60.0) if transcurrido > 0 else 0.0
    restantes = max(total - hechas, 0)
    eta = restantes / ritmo if ritmo > 0 else 0.0
    descartas = sum(stats["descartadas"].values())
    detalle = ", ".join("%s:%d" % (m, n)
                       for m, n in sorted(stats["descartadas"].items()))
    linea = ("[afirmaciones] %d/%d evidencias | aceptadas=%d descartadas=%d"
             " (%s) | %.1f ev/min | ETA %.1f min"
             % (hechas, total, stats["afirmaciones"], descartas,
                detalle or "-", ritmo, eta))
    print(linea, file=stream, flush=True)


def main(argv=None, cliente=None):
    """Punto de entrada del extractor de afirmaciones (T29.3)."""
    parser = argparse.ArgumentParser(
        description="Extrae afirmaciones atomicas en espanol de las "
                    "evidencias web (T29).")
    parser.add_argument("--evidencias", default=DEFAULT_EVIDENCIAS)
    parser.add_argument("--web-dir", default=DEFAULT_WEB_DIR)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--limite", type=int, default=0,
                       help="Maximo de evidencias a procesar (0 = todas).")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--simulado", action="store_true",
                       help="Usa un cliente simulado (sin nodos GPU).")
    parser.add_argument("--filtrar-utilidad", action="store_true",
                       help="Filtra por utilidad un afirmaciones.jsonl "
                            "existente (T34) sin tocarlo.")
    parser.add_argument("--in", dest="in_", default=DEFAULT_AFIRMACIONES,
                       help="Fichero de entrada para --filtrar-utilidad.")
    parser.add_argument("--orden", choices=["calidad"], default=None,
                       help="Ordena por calidad descendente (5 antes que 4 y 3).")
    parser.add_argument("--familias", default=None,
                       help="Lista separada por comas de familias a procesar "
                            "primero (p. ej. tarot,baraja_espanola).")
    parser.add_argument("--min-calidad", type=int, default=0,
                       help="Deja fuera las evidencias con calidad menor.")
    parser.add_argument("--timeout", type=float, default=60.0,
                       help="Timeout por peticion al nodo, en segundos.")
    args = parser.parse_args(argv)

    if args.filtrar_utilidad:
        return filtrar_utilidad(args.in_, args.out_dir)

    evidencias = []
    with open(args.evidencias, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                evidencia = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(evidencia, dict):
                evidencias.append(evidencia)

    familias = None
    if args.familias:
        familias = [f.strip() for f in args.familias.split(",") if f.strip()]
    evidencias = filtrar_min_calidad(evidencias, args.min_calidad)
    evidencias = ordenar_evidencias(evidencias, orden=args.orden,
                                   familias=familias)
    if args.limite:
        evidencias = evidencias[:args.limite]

    os.makedirs(args.out_dir, exist_ok=True)
    ruta_af = os.path.join(args.out_dir, "afirmaciones.jsonl")
    ruta_pr = os.path.join(args.out_dir, "procesados.jsonl")
    ruta_in = os.path.join(args.out_dir, "afirmaciones_informe.md")

    procesados = _cargar_procesados(ruta_pr)
    indice = IndiceWeb(args.web_dir)
    catalogo = _catalogo_familias()
    if cliente is None:
        cliente = LLMClient(simulado=_simulado_vacio, timeout=args.timeout) \
            if args.simulado else LLMClient(timeout=args.timeout)

    stats = {
        "procesadas": 0,
        "sin_texto": 0,
        "errores": 0,
        "afirmaciones": 0,
        "descartadas": Counter(),
        "por_familia": Counter(),
    }
    lock = threading.Lock()
    inicio = time.time()
    total = len(evidencias)
    hechas = 0

    def trabajar(ev):
        clave = (ev.get("hash_seccion"), ev.get("entidad_id"),
                ev.get("faceta"))
        if clave in procesados:
            return None
        return ev, procesar_evidencia(ev, indice, cliente)

    def registrar(fp, fa, ev, res):
        """Escribe el resultado en cuanto llega y actualiza el contador.

        Serializado con `lock` y con flush por linea: si el proceso se corta,
        lo ya escrito queda en disco y la reanudacion no lo repite.
        """
        nonlocal hechas
        with lock:
            for a in res["afirmaciones"]:
                fa.write(json.dumps(registro_afirmacion(ev, a),
                                   ensure_ascii=False) + "\n")
                fa.flush()
                stats["por_familia"][
                    familia_de_entidad(ev.get("entidad_id"), catalogo)] += 1
            for _, motivo in res["descartadas"]:
                stats["descartadas"][motivo] += 1
            fp.write(json.dumps({
                "hash_seccion": ev.get("hash_seccion"),
                "entidad_id": ev.get("entidad_id"),
                "faceta": ev.get("faceta"),
                "estado": res["estado"],
                "n_afirmaciones": len(res["afirmaciones"]),
            }, ensure_ascii=False) + "\n")
            fp.flush()
            stats["procesadas"] += 1
            hechas += 1
            if res["estado"] == "sin_texto":
                stats["sin_texto"] += 1
            elif res["estado"] == "error":
                stats["errores"] += 1
            else:
                stats["afirmaciones"] += len(res["afirmaciones"])
            if hechas % 25 == 0:
                _log_progreso(sys.stderr, hechas, total, stats, inicio)

    with open(ruta_pr, "a", encoding="utf-8") as fp, \
            open(ruta_af, "a", encoding="utf-8") as fa:
        if args.workers > 1:
            ex = ThreadPoolExecutor(max_workers=args.workers)
            try:
                futuros = [ex.submit(trabajar, ev) for ev in evidencias]
                for fut in as_completed(futuros):
                    r = fut.result()
                    if r is None:
                        continue
                    registrar(fp, fa, r[0], r[1])
            except BaseException:
                ex.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                ex.shutdown(wait=True)
        else:
            for ev in evidencias:
                r = trabajar(ev)
                if r is None:
                    continue
                registrar(fp, fa, r[0], r[1])

    escribir_informe(ruta_in, stats)
    return stats


# ---------------------------------------------------------------------------
# T34: filtro de utilidad de afirmaciones
# ---------------------------------------------------------------------------

DEFAULT_AFIRMACIONES = "/Users/angelgonzalez/fase0/afirmaciones/afirmaciones.jsonl"

MIN_PALABRAS_UTIL = 5

# Identificadores internos: «bastos-05», «naipe …», «oros 05».
_RE_IDENTIFICADOR = re.compile(
    r"[a-z]+-\d{2}"
    r"|\bnaipe\b"
    r"|\b(?:oros|copas|espadas|bastos)\s+\d{1,2}\b",
)

# Referencias deícticas al contexto de la consulta o de la tirada.
_RE_DEICTICO = re.compile(
    r"consultante"
    r"|\best[oa]s?\s+(?:cartas?|naipes?|barajas?)\b"
    r"|\bjunt[oa]s?\b"
    r"|\btirada\b"
    r"|\bacompa"
    r"|\bdepende\b"
    r"|\binterpretaci[oó]n\s+para\b",
    re.IGNORECASE,
)

# Palabras de relleno: correspondencias y fórmulas que no aportan
# interpretación por sí solas (en español normalizado, sin tildes).
_BOILERPLATE_UTIL = frozenset("""
elemento tierra fuego agua aire polaridad masculino masculina femenino
femenina liga ligado ligada ligados ligadas asociado asociada asociados
asociadas asocia relaciona relacionado relacionada relacionados
relacionadas vincula vinculado vinculada vinculados vinculadas seres
elementales elemental signo signos zodiacal zodiacales carta cartas naipe
naipes oros copas espadas bastos representa
""".split())


def _tokens_entidad(entidad_id):
    """Tokens del identificador de entidad (sin prefijos estructurales)."""
    partes = re.split(r"[-|]", entidad_id or "")
    return {cartas.norm(p) for p in partes
            if p and not p.isdigit() and p not in ("tarot", "naipe")}


def _tokens_sustancia(afirmacion, entidad_id):
    """Tokens de contenido: ni vacíos funcionales, ni relleno, ni nombre."""
    entidad = _tokens_entidad(entidad_id)
    sustancia = []
    for w in cartas.norm(afirmacion).split():
        if len(w) < 4 or w in _STOPWORDS or w in _BOILERPLATE_UTIL:
            continue
        if w.isdigit() or w in entidad:
            continue
        sustancia.append(w)
    return sustancia


def evaluar_utilidad(afirmacion, entidad_id, faceta):
    """(True, None) si la afirmación aporta contenido interpretativo.

    Motivos de descarte: `vacia`, `identificador`, `deictica`, `corta`,
    `repite_nombre` (solo nombre de la carta/entidad y correspondencias).
    """
    if not afirmacion or not afirmacion.strip():
        return False, "vacia"
    if _RE_IDENTIFICADOR.search(afirmacion):
        return False, "identificador"
    if _RE_DEICTICO.search(afirmacion):
        return False, "deictica"
    if len(afirmacion.split()) < MIN_PALABRAS_UTIL:
        return False, "corta"
    if not _tokens_sustancia(afirmacion, entidad_id):
        return False, "repite_nombre"
    return True, None


def filtrar_utilidad(ruta_entrada, out_dir):
    """Separa un `afirmaciones.jsonl` en útiles y descartadas (con motivo).

    No modifica el fichero de entrada.
    """
    os.makedirs(out_dir, exist_ok=True)
    ruta_u = os.path.join(out_dir, "afirmaciones_utiles.jsonl")
    ruta_d = os.path.join(out_dir, "descartadas_utilidad.jsonl")
    stats = {"total": 0, "utiles": 0, "descartadas": Counter()}
    with open(ruta_entrada, encoding="utf-8") as fin, \
            open(ruta_u, "w", encoding="utf-8") as fu, \
            open(ruta_d, "w", encoding="utf-8") as fd:
        for linea in fin:
            linea = linea.strip()
            if not linea:
                continue
            try:
                rec = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            ok, motivo = evaluar_utilidad(rec.get("afirmacion"),
                                         rec.get("entidad_id"),
                                         rec.get("faceta"))
            stats["total"] += 1
            if ok:
                stats["utiles"] += 1
                fu.write(json.dumps(rec, ensure_ascii=False) + "\n")
            else:
                stats["descartadas"][motivo] += 1
                d = dict(rec)
                d["motivo"] = motivo
                fd.write(json.dumps(d, ensure_ascii=False) + "\n")
    return stats


if __name__ == "__main__":
    main()
