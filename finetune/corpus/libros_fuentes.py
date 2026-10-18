"""Inventario unificado de libros fuente para la pista de libros (F0.2).

Lee los cuatro ficheros de `knowledge/` (fuentes_libros.jsonl, fuentes_libros_es.jsonl,
fuentes_libros_tema.jsonl, epubs_locales.jsonl), normaliza a un esquema común,
descarta lo que no esté aprobado y desduplica por título normalizado.
"""
import json
import os
import unicodedata
import urllib.parse

ARCHIVE_FILES = ("fuentes_libros.jsonl", "fuentes_libros_es.jsonl",
                "fuentes_libros_tema.jsonl")
EPUB_FILE = "epubs_locales.jsonl"
ESTADOS_OK = {"texto_verificado"}
DECISIONES_OK = {"usar", "usar_con_limpieza"}


def normalizar_titulo(titulo):
    """Título en minúsculas, sin acentos ni signos, espacios colapsados."""
    s = unicodedata.normalize("NFKD", titulo or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if c.isalnum() else " " for c in s)
    return " ".join(s.lower().split())


def _leer_jsonl(ruta):
    filas = []
    if not os.path.exists(ruta):
        return filas
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def _tamano_kb_a_chars(kb):
    try:
        return int(float(kb) * 1024)
    except (TypeError, ValueError):
        return 0


def _normalizar_archive(fila):
    texto_ocr = fila.get("texto_ocr") or ""
    url = None
    if texto_ocr:
        url = ("https://archive.org/download/%s/%s"
               % (urllib.parse.quote(fila["id"]), urllib.parse.quote(texto_ocr)))
    return {
        "id": fila["id"],
        "titulo": fila.get("titulo", ""),
        "autor": fila.get("autor", ""),
        "anio": fila.get("anio"),
        "idioma": fila.get("idioma", ""),
        "familia": fila.get("familia", ""),
        "prioridad": fila.get("prioridad", "media"),
        "origen": "archive",
        "url": url,
        "ruta_local": None,
        # El texto de archive.org es OCR: siempre pasa por la limpieza.
        "calidad": "con_limpieza",
        "nota": fila.get("nota", ""),
    }, _tamano_kb_a_chars(fila.get("texto_kb"))


def _normalizar_epub(fila, dir_knowledge):
    decision = fila.get("decision")
    calidad = "limpio" if decision == "usar" else "con_limpieza"
    fichero = fila.get("fichero", "")
    ruta_local = os.path.abspath(os.path.join(dir_knowledge, "..", fichero))
    return {
        "id": fila["id"],
        "titulo": fila.get("titulo", ""),
        "autor": fila.get("autor", ""),
        "anio": fila.get("anio"),
        "idioma": fila.get("idioma", ""),
        "familia": fila.get("tema", ""),
        "prioridad": fila.get("prioridad", "media"),
        "origen": "epub_local",
        "url": None,
        "ruta_local": ruta_local,
        "calidad": calidad,
        "nota": fila.get("nota", ""),
    }, int(fila.get("chars") or 0)


def cargar_inventario(dir_knowledge):
    """Devuelve la lista normalizada y desduplicada de libros aprobados."""
    candidatos = []
    for nombre in ARCHIVE_FILES:
        for fila in _leer_jsonl(os.path.join(dir_knowledge, nombre)):
            if fila.get("estado") in ESTADOS_OK:
                candidatos.append(_normalizar_archive(fila))
    for fila in _leer_jsonl(os.path.join(dir_knowledge, EPUB_FILE)):
        if fila.get("decision") in DECISIONES_OK:
            candidatos.append(_normalizar_epub(fila, dir_knowledge))
    # Desduplicar por título normalizado: conserva el de mayor tamaño.
    mejores = {}
    orden = []
    for registro, tamano in candidatos:
        clave = normalizar_titulo(registro["titulo"])
        if clave not in mejores or tamano > mejores[clave][1]:
            if clave not in mejores:
                orden.append(clave)
            mejores[clave] = (registro, tamano)
    return [mejores[clave][0] for clave in orden]
