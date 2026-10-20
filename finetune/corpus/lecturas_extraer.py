#!/usr/bin/env python3
"""Extractor de lecturas trabajadas de libros segmentados (T37, F0.5).

Una LECTURA TRABAJADA es una consulta resuelta: cartas (o carta natal, o
numeros) con pregunta o consultante explicitos y una interpretacion
desarrollada. Es la pieza mas escasa del corpus.

Paso 1: detector determinista de candidatas sobre las secciones de libros,
        excluyendo las ya juzgadas ruido (relleno, publicidad, ficcion).
Paso 2: clasificador LLM (reanudable, pocos workers porque los nodos se
        comparten) que confirma si es lectura resuelta y extrae sistema,
        cartas/elementos, pregunta, calidad 1-5 e idioma.

Salida: /Users/angelgonzalez/fase0/lecturas/lecturas.jsonl con procedencia
(libro, seccion, periodo) e informe con recuento por sistema y ejemplos.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import cartas as cartas_mod
import juez
from llm_client import LLMClient

DEFAULT_SECCIONES_DIR = "/Users/angelgonzalez/fase0/libros/secciones"
DEFAULT_JUICIOS = "/Users/angelgonzalez/fase0/libros/evidencias/juicios.jsonl"
DEFAULT_OUT_DIR = "/Users/angelgonzalez/fase0/lecturas"

TIPOS_RUIDO = frozenset({"relleno", "publicidad", "ficcion", "error"})
SISTEMAS_VALIDOS = ("tarot", "baraja_espanola", "astrologia", "numerologia",
                    "otro")
IDIOMAS_VALIDOS = ("es", "en", "otro")

MIN_CHARS_SECCION = 200
MAX_TEXTO_PROMPT = 6000

# ---------------------------------------------------------------------------
# Paso 1: detector determinista de candidatas
# ---------------------------------------------------------------------------

_PATRON_EJEMPLO = re.compile(
    r"\bejemplo\b|\blectura de\b|\blectura para\b|\bconsulta\b|"
    r"\bsupongamos\b|\bimaginemos\b|\bfijemonos\b|\bcaso practico\b|"
    r"\bcaso real\b|\bexample\b|\breading for\b|\ba querent\b|"
    r"\bthe querent\b|\binquirer\b|\blet(?:'?s| us) say\b|\bsuppose\b|"
    r"\bconsultante\b",
    re.IGNORECASE,
)

_PATRON_NATAL = re.compile(
    r"\b(carta natal|carta astral|natal chart|birth chart|tema natal)\b",
    re.IGNORECASE,
)

_PATRON_ASTRO_TERMS = re.compile(
    r"\bascendente\b|\bsol en\b|\bluna en\b|\bcasa \d|\bcasas \d|"
    r"\bascendant\b|\bsun in\b|\bmoon in\b|\bhouse \d",
    re.IGNORECASE,
)

_PATRON_NUMEROLOGIA = re.compile(
    r"\bcamino de vida\b|\blife path\b|\bnumero del (?:destino|expresion|alma)\b|"
    r"\bn[uú]mero del (?:destino|expresi[oó]n|alma)\b|\bnumerolog\w*\b",
    re.IGNORECASE,
)

_PATRON_PREGUNTA = re.compile(
    r"\bpregunta\b|\bquiere saber\b|\bwants to know\b|\basked\b|\?",
    re.IGNORECASE,
)

_PATRON_INTERPRETACION = re.compile(
    r"\bsignifica\b|\bindica\b|\bsugiere\b|\bapunta a\b|\bconsejo\b|"
    r"\badvice\b|\bmeans\b|\bthis reading\b|\bla lectura\b|\bel consejo\b",
    re.IGNORECASE,
)

_PATRON_QUERENT = re.compile(
    r"\breading for\b|\bquerent\b|\binquirant\b",
    re.IGNORECASE,
)


def senales_lectura(texto):
    """Senales deterministas de que el texto podria contener una lectura."""
    texto = texto or ""
    ids_tarot = {c["carta"]["id"]
                 for c in cartas_mod.extraer_cartas(texto, mazo="tarot")}
    ids_baraja = {c["carta"]["id"]
                 for c in cartas_mod.extraer_cartas(texto, mazo="espanol")}
    return {
        "n_cartas_tarot": len(ids_tarot),
        "n_cartas_baraja": len(ids_baraja),
        "ejemplo": bool(_PATRON_EJEMPLO.search(texto)),
        "natal": bool(_PATRON_NATAL.search(texto)),
        "astro_terms": len(_PATRON_ASTRO_TERMS.findall(texto)),
        "numerologia": bool(_PATRON_NUMEROLOGIA.search(texto)),
        "pregunta": bool(_PATRON_PREGUNTA.search(texto)),
        "interpretacion": bool(_PATRON_INTERPRETACION.search(texto)),
        "querent": bool(_PATRON_QUERENT.search(texto)),
    }


def candidata_lectura(seccion, juicio=None):
    """Devuelve dict de motivos si la seccion es candidata, None si no.

    Se excluyen las secciones cuyo juicio es ruido. Una seccion es candidata
    si tiene tirada de 3+ cartas con contexto de ejemplo/consulta, o carta
    natal con interpretacion, o numerologia con ejemplo e interpretacion,
    o si el juez ya la marco como lectura_trabajada.
    """
    if juicio and (juicio.get("tipo") in TIPOS_RUIDO):
        return None
    texto = seccion.get("texto") or ""
    if len(texto) < MIN_CHARS_SECCION:
        return None
    s = senales_lectura(texto)
    motivos = []
    if juicio and juicio.get("tipo") == "lectura_trabajada":
        motivos.append("juicio_lectura")
    if ((s["n_cartas_tarot"] >= 3 or s["n_cartas_baraja"] >= 3)
            and (s["ejemplo"] or s["pregunta"] or s["interpretacion"])):
        motivos.append("tirada")
    if s["natal"] and s["interpretacion"]:
        motivos.append("natal")
    if (not s["natal"] and s["astro_terms"] >= 2 and s["interpretacion"]
            and s["ejemplo"]):
        motivos.append("natal")
    if s["numerologia"] and s["interpretacion"] and (s["ejemplo"] or s["pregunta"]):
        motivos.append("numerologia")
    senal_sistema = (s["n_cartas_tarot"] >= 1 or s["n_cartas_baraja"] >= 1
                     or s["natal"] or s["numerologia"] or s["astro_terms"] >= 2)
    if (s["ejemplo"] and s["pregunta"] and s["interpretacion"]
            and (senal_sistema or s["querent"])):
        motivos.append("consulta")
    if not motivos:
        return None
    resultado = dict(s)
    resultado["motivos"] = motivos
    return resultado


# ---------------------------------------------------------------------------
# Paso 2: clasificador LLM
# ---------------------------------------------------------------------------

SISTEMA_CLASIFICADOR = (
    "Eres un analista de textos de adivinacion (tarot, baraja espanola, "
    "astrologia y numerologia). Analiza el fragmento de libro que se te da y "
    "decide si contiene una LECTURA TRABAJADA: una consulta resuelta con "
    "cartas, carta natal o numeros, con pregunta o consultante explicito y "
    "una interpretacion desarrollada (no solo teoria suelta ni lista de "
    "significados). "
    "Valora la calidad: 5 = lectura completa con pregunta, elementos y "
    "interpretacion rica; 4 = lectura clara algo breve; 3 = lectura parcial; "
    "2 = esbozo; 1 = no es lectura. "
    "Responde SOLO con un objeto JSON valido, sin texto adicional, con estas "
    'claves exactas: {"es_lectura": true o false, "sistema": '
    '"tarot" o "baraja_espanola" o "astrologia" o "numerologia" o "otro", '
    '"cartas": ["nombre de cada carta mencionada en la lectura"], '
    '"elementos": ["elementos astrales o numerologicos de la lectura"], '
    '"pregunta": "resumen de la pregunta o del consultante, o null", '
    '"calidad": entero de 1 a 5, "idioma": "es" o "en" o "otro", '
    '"motivo": "justificacion breve"}'
)


def construir_prompt_lectura(seccion, max_chars=MAX_TEXTO_PROMPT):
    """Prompt de usuario para clasificar una seccion como lectura."""
    titulo = seccion.get("titulo") or "(sin titulo)"
    texto = (seccion.get("texto") or "")[:max_chars]
    return "Titulo de la seccion: %s\n\nTexto:\n%s" % (titulo, texto)


def validar_clasificacion(data):
    """Lanza ValueError si la respuesta del modelo no tiene el formato esperado."""
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    if not isinstance(data.get("es_lectura"), bool):
        raise ValueError("falta 'es_lectura' booleano")
    if data.get("sistema") not in SISTEMAS_VALIDOS:
        raise ValueError("sistema invalido: %r" % (data.get("sistema"),))
    calidad = data.get("calidad")
    if not isinstance(calidad, int) or isinstance(calidad, bool) \
            or calidad < 1 or calidad > 5:
        raise ValueError("calidad debe ser entero 1-5")
    if data.get("idioma") not in IDIOMAS_VALIDOS:
        raise ValueError("idioma invalido: %r" % (data.get("idioma"),))
    for clave in ("cartas", "elementos"):
        if not isinstance(data.get(clave), list):
            raise ValueError("'%s' debe ser una lista" % clave)


def clasificar_lectura(cliente, seccion):
    """Clasifica una seccion con el LLM. Devuelve el dict validado."""
    usuario = construir_prompt_lectura(seccion)
    return cliente.chat_json(SISTEMA_CLASIFICADOR, usuario,
                            validar_clasificacion, max_tokens=1024,
                            intentos=2)


# ---------------------------------------------------------------------------
# Registro y carga de datos
# ---------------------------------------------------------------------------

def registro_lectura(seccion, clasif, meta=None):
    """Fila de lecturas.jsonl con procedencia completa."""
    meta = meta or {}
    id_libro = seccion.get("id_libro") or ""
    datos = meta.get(id_libro, {})
    return {
        "id": juez.hash_seccion(seccion),
        "fuente": "libro",
        "libro_id": id_libro,
        "titulo_libro": datos.get("titulo") or "",
        "autor": datos.get("autor"),
        "periodo": datos.get("periodo"),
        "seccion": seccion.get("seccion"),
        "posicion": seccion.get("posicion"),
        "sistema": clasif["sistema"],
        "cartas": clasif.get("cartas") or [],
        "elementos": clasif.get("elementos") or [],
        "pregunta": clasif.get("pregunta"),
        "calidad": clasif["calidad"],
        "idioma": clasif["idioma"],
        "motivo": clasif.get("motivo", ""),
        "texto": seccion.get("texto") or "",
    }


def cargar_secciones(secciones_dir):
    """Todas las secciones de los *.jsonl del directorio."""
    secciones = []
    for ruta in sorted(glob.glob(os.path.join(secciones_dir, "*.jsonl"))):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    dato = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(dato, dict):
                    secciones.append(dato)
    return secciones


def cargar_juicios(ruta):
    """Dict hash_seccion -> juicio (dict con tipo, calidad, ...)."""
    juicios = {}
    if not os.path.exists(ruta):
        return juicios
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                dato = json.loads(linea)
            except ValueError:
                continue
            if isinstance(dato, dict) and dato.get("hash"):
                juicios[dato["hash"]] = dato.get("juicio") or {}
    return juicios


def _cargar_procesados(ruta):
    """Hashes de secciones ya clasificadas (solo las validas: no se repiten)."""
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
            if d.get("estado") in ("aceptada", "rechazada"):
                claves.add(d.get("hash_seccion"))
    return claves


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def escribir_informe(ruta, stats, ejemplos=None):
    """Informe Markdown del recuento de lecturas."""
    ejemplos = ejemplos or []
    lineas = [
        "# Informe de lecturas trabajadas (T37)",
        "",
        "- Secciones analizadas: %d" % stats["secciones"],
        "- Candidatas del detector: %d" % stats["candidatas"],
        "- Excluidas por juicio de ruido: %d" % stats["ruido"],
        "- Clasificadas por el LLM: %d" % stats["clasificadas"],
        "- Lecturas aceptadas: %d" % stats["aceptadas"],
        "- Rechazadas por el LLM: %d" % stats["rechazadas"],
        "- Errores del modelo: %d" % stats["errores"],
        "",
        "## Lecturas por sistema",
        "",
        "| Sistema | Lecturas | >= 4/5 |",
        "|---|---|---|",
    ]
    for sistema in SISTEMAS_VALIDOS:
        n = stats["por_sistema"].get(sistema, 0)
        n4 = stats["por_sistema_calidad4"].get(sistema, 0)
        if n or n4:
            lineas.append("| %s | %d | %d |" % (sistema, n, n4))
    if not stats["por_sistema"]:
        lineas.append("| (ninguna) | 0 | 0 |")
    lineas += ["", "## Lecturas por calidad", "",
               "| Calidad | Lecturas |", "|---|---|"]
    for q in (5, 4, 3, 2, 1):
        lineas.append("| %d | %d |" % (q, stats["por_calidad"].get(q, 0)))
    lineas += ["", "## Ejemplos", ""]
    if ejemplos:
        for ej in ejemplos:
            lineas.append("- [%s] %s (calidad %d, %s): %s" % (
                ej.get("sistema", "?"),
                (ej.get("titulo_libro") or ej.get("libro_id") or "?")[:60],
                ej.get("calidad", 0),
                ej.get("periodo") or "?",
                (ej.get("pregunta") or "sin pregunta")[:120],
            ))
    else:
        lineas.append("- (ninguno)")
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _simulado_clasificador(sistema, usuario):
    return ('{"es_lectura": true, "sistema": "tarot", '
            '"cartas": ["El Mago", "La Sacerdotisa", "El Loco"], '
            '"elementos": [], "pregunta": "?", '
            '"calidad": 4, "idioma": "es", "motivo": "simulado"}')


def main(argv=None, cliente=None):
    """Punto de entrada del extractor de lecturas trabajadas (T37)."""
    parser = argparse.ArgumentParser(
        description="Extrae lecturas trabajadas de los libros segmentados (T37).")
    parser.add_argument("--secciones-dir", default=DEFAULT_SECCIONES_DIR)
    parser.add_argument("--juicios", default=DEFAULT_JUICIOS)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--limite", type=int, default=0,
                       help="Maximo de candidatas a procesar (0 = todas).")
    parser.add_argument("--workers", type=int, default=2,
                        help="Hilos de clasificacion (nodos compartidos).")
    parser.add_argument("--simulado", action="store_true",
                       help="Usa un cliente simulado (sin nodos GPU).")
    parser.add_argument("--solo-detector", action="store_true",
                       help="Solo escribe candidatas.jsonl, sin LLM.")
    args = parser.parse_args(argv)

    secciones = cargar_secciones(args.secciones_dir)
    juicios = cargar_juicios(args.juicios)
    meta = juez.cargar_meta_libros()

    os.makedirs(args.out_dir, exist_ok=True)
    ruta_cand = os.path.join(args.out_dir, "candidatas.jsonl")
    ruta_lect = os.path.join(args.out_dir, "lecturas.jsonl")
    ruta_pr = os.path.join(args.out_dir, "procesados.jsonl")
    ruta_in = os.path.join(args.out_dir, "lecturas_informe.md")

    stats = {
        "secciones": len(secciones),
        "candidatas": 0,
        "ruido": 0,
        "clasificadas": 0,
        "aceptadas": 0,
        "rechazadas": 0,
        "errores": 0,
        "por_sistema": Counter(),
        "por_sistema_calidad4": Counter(),
        "por_calidad": Counter(),
    }

    candidatas = []
    for seccion in secciones:
        h = juez.hash_seccion(seccion)
        juicio = juicios.get(h)
        det = candidata_lectura(seccion, juicio)
        if juicio and juicio.get("tipo") in TIPOS_RUIDO:
            stats["ruido"] += 1
        if det is None:
            continue
        stats["candidatas"] += 1
        candidatas.append((seccion, h, det))
    if args.limite:
        candidatas = candidatas[:args.limite]

    with open(ruta_cand, "w", encoding="utf-8") as fc:
        for seccion, h, det in candidatas:
            fc.write(json.dumps({
                "hash_seccion": h,
                "id_libro": seccion.get("id_libro"),
                "seccion": seccion.get("seccion"),
                "titulo": seccion.get("titulo"),
                "motivos": det["motivos"],
                "n_cartas_tarot": det["n_cartas_tarot"],
                "n_cartas_baraja": det["n_cartas_baraja"],
            }, ensure_ascii=False) + "\n")

    if args.solo_detector:
        escribir_informe(ruta_in, stats)
        return stats

    procesados = _cargar_procesados(ruta_pr)
    if cliente is None:
        cliente = LLMClient(simulado=_simulado_clasificador) if args.simulado \
            else LLMClient()

    lock = threading.Lock()
    ejemplos = []

    def trabajar(item):
        seccion, h, det = item
        if h in procesados:
            return
        try:
            clasif = clasificar_lectura(cliente, seccion)
        except Exception as exc:
            with lock:
                stats["errores"] += 1
                print("ERROR %s: %s" % (h[:12], exc))
            return
        aceptada = bool(clasif.get("es_lectura"))
        with lock:
            stats["clasificadas"] += 1
            if aceptada:
                stats["aceptadas"] += 1
                stats["por_sistema"][clasif["sistema"]] += 1
                stats["por_calidad"][clasif["calidad"]] += 1
                if clasif["calidad"] >= 4:
                    stats["por_sistema_calidad4"][clasif["sistema"]] += 1
                if len(ejemplos) < 10:
                    ejemplos.append(registro_lectura(seccion, clasif, meta))
            else:
                stats["rechazadas"] += 1
            with open(ruta_lect, "a", encoding="utf-8") as fl:
                if aceptada:
                    fl.write(json.dumps(
                        registro_lectura(seccion, clasif, meta),
                        ensure_ascii=False) + "\n")
                    fl.flush()
            with open(ruta_pr, "a", encoding="utf-8") as fp:
                fp.write(json.dumps({
                    "hash_seccion": h,
                    "estado": "aceptada" if aceptada else "rechazada",
                    "sistema": clasif["sistema"],
                    "calidad": clasif["calidad"],
                }, ensure_ascii=False) + "\n")
                fp.flush()

    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(trabajar, candidatas))
    else:
        for item in candidatas:
            trabajar(item)

    escribir_informe(ruta_in, stats, ejemplos)
    return stats


if __name__ == "__main__":
    main()
