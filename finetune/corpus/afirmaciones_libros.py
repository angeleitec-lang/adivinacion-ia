#!/usr/bin/env python3
"""Extraccion de afirmaciones desde libros (T38).

Mismo esquema de salida que ``afirmaciones_es.py`` mas el campo
``cita_original``: la afirmacion se redacta en espanol y la cita se copia
verbatim del texto original (ingles o clasico). Reutiliza la validacion
determinista y el filtro de utilidad de ``afirmaciones_es.py`` y las
comprobaciones de contradiccion contra la KB de ``consenso_kb.py``.

Cada registro lleva ``contradice_kb`` (bool) y, si es true,
``motivo_contradice`` (ser_elemental | elemento | regente | tautologia).

Reanudable por (hash_seccion, entidad_id, faceta); workers por defecto 3.
No modifica ``afirmaciones_es.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import cartas
import juez
from llm_client import LLMClient

import afirmaciones_es as es
from consenso_kb import cargar_correspondencias, contradiccion_kb

MAX_CITA_PALABRAS = 25

DEFAULT_EVIDENCIAS = "/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl"
DEFAULT_SECCIONES_DIR = "/Users/angelgonzalez/fase0/libros/secciones"
DEFAULT_OUT_DIR = "/Users/angelgonzalez/fase0/afirmaciones_libros"

SISTEMA_AFIRMACIONES_LIBROS = (
    "Eres un asistente que extrae de libros de adivinacion (tarot, baraja "
    "espanola, astrologia, numerologia) afirmaciones claras y utiles. "
    "La afirmacion se redacta en espanol estandar con tildes, aunque el "
    "texto original este en otro idioma, y va acompanada de una cita textual "
    "breve del original que la respalda. "
    "Responde SOLO con un objeto JSON valido."
)


class IndiceLibros:
    """Localizador de secciones de libros: hash_seccion -> seccion (cahce por libro)."""

    def __init__(self, secciones_dir):
        self.secciones_dir = secciones_dir
        self._cache = {}
        self._lock = threading.Lock()

    def _cargar_libro(self, fuente_id):
        ruta = os.path.join(self.secciones_dir, "%s.jsonl" % fuente_id)
        mapa = {}
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as fh:
                for linea in fh:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        sec = json.loads(linea)
                    except ValueError:
                        continue
                    mapa[juez.hash_seccion(sec)] = sec
        return mapa

    def seccion(self, fuente_id, hash_seccion):
        with self._lock:
            mapa = self._cache.get(fuente_id)
            if mapa is None:
                mapa = self._cargar_libro(fuente_id)
                self._cache[fuente_id] = mapa
        return mapa.get(hash_seccion)


def cita_verbatim(cita, texto):
    """True si la cita aparece textualmente en el texto (ignorando tildes/signos)."""
    if not cita or not texto:
        return False
    return cartas.norm(cita) in cartas.norm(texto)


def construir_prompt_libros(entidad_id, faceta, texto, max_chars=6000):
    """(sistema, usuario) para pedir afirmaciones + cita verbatim de una seccion."""
    cuerpo = texto if len(texto) <= max_chars else texto[:max_chars] + " [...]"
    usuario = (
        "Entidad: {e}\nFaceta: {f}\n\n"
        "Texto de la fuente (idioma original):\n\"\"\"\n{t}\n\"\"\"\n\n"
        "Extrae del texto una lista de afirmaciones utiles sobre la entidad "
        "en la faceta indicada. Para cada afirmacion incluye una cita "
        "textual del original que la respalde.\n"
        "Reglas:\n"
        "1. La afirmacion se redacta en espanol estandar con tildes, "
        "expresa una sola idea y es autonoma (se entiende sin ver el texto).\n"
        "2. Maximo 40 palabras por afirmacion.\n"
        "3. La cita (\"cita_original\") se copia EXACTAMENTE del texto, en "
        "su idioma original, con un maximo de 25 palabras.\n"
        "4. Usa unicamente informacion presente en el texto; no inventes ni "
        "anadas conocimiento externo.\n"
        "5. Evita afirmaciones que solo repitan el nombre de la entidad o "
        "que no aporten nada.\n"
        "6. Si el texto no aporta nada sobre esa faceta, devuelve la lista "
        "vacia.\n\n"
        "Responde SOLO con JSON valido de la forma "
        '{{"afirmaciones": [{{"afirmacion": "...", '
        '"cita_original": "..."}}, ...]}}'
    ).format(e=entidad_id, f=faceta, t=cuerpo)
    return SISTEMA_AFIRMACIONES_LIBROS, usuario


def validar_respuesta_afirmaciones_libros(data):
    """Valida la forma de la respuesta; lanza ValueError si no."""
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    afirmaciones = data.get("afirmaciones")
    if not isinstance(afirmaciones, list):
        raise ValueError('Falta la lista "afirmaciones"')
    for a in afirmaciones:
        if not isinstance(a, dict):
            raise ValueError("Elemento de afirmaciones no es un objeto")
        if not isinstance(a.get("afirmacion"), str) or not a["afirmacion"].strip():
            raise ValueError("Afirmacion no textual o vacia")
        if not isinstance(a.get("cita_original"), str) or not a["cita_original"].strip():
            raise ValueError("cita_original no textual o vacia")


def validar_afirmacion_libros(item, texto, entidad_id, faceta, idioma):
    """Validacion determinista de una afirmacion de libro.

    Devuelve (bool, motivo). Motivos: vacia, longitud, sin_cita,
    cita_no_textual, otra_carta, vocabulario, exceso_cita y los del filtro
    de utilidad de T34, ademas de marcar contradiccion KB (no descarta).
    """
    afirmacion = (item.get("afirmacion") or "").strip()
    cita = (item.get("cita_original") or "").strip()
    if not afirmacion:
        return (False, "vacia")
    if len(afirmacion.split()) > es.MAX_PALABRAS:
        return (False, "longitud")
    if not cita:
        return (False, "sin_cita")
    if len(cita.split()) > MAX_CITA_PALABRAS:
        return (False, "exceso_cita")
    if not cita_verbatim(cita, texto):
        return (False, "cita_no_textual")
    if not es.es_combinacion(entidad_id, faceta) and \
            es.menciona_otra_carta(afirmacion, entidad_id):
        return (False, "otra_carta")
    if idioma == "es" and not es.compartir_vocabulario(afirmacion, texto):
        return (False, "vocabulario")
    vale, motivo = es.evaluar_utilidad(afirmacion, entidad_id, faceta)
    if not vale:
        return (False, motivo)
    return (True, None)


def extraer_afirmaciones_libros(cliente, entidad_id, faceta, texto, idioma, corr):
    """Extrae y valida afirmaciones de una seccion de libro.

    Devuelve {"estado", "afirmaciones": [dict...], "descartadas": [(txt, motivo)]}.
    Cada afirmacion aceptada: {"afirmacion", "cita_original",
    "contradice_kb", "motivo_contradice"?}.
    """
    resultado = {"estado": "ok", "afirmaciones": [], "descartadas": []}
    sistema, usuario = construir_prompt_libros(entidad_id, faceta, texto)
    try:
        data = cliente.chat_json(sistema, usuario,
                               validar_respuesta_afirmaciones_libros)
    except Exception:
        resultado["estado"] = "error"
        return resultado
    crudas = data.get("afirmaciones") or []
    aceptadas = []
    for item in crudas:
        vale, motivo = validar_afirmacion_libros(
            item, texto, entidad_id, faceta, idioma)
        if not vale:
            resultado["descartadas"].append(
                ((item.get("afirmacion") or "").strip(), motivo))
            continue
        contradice, motivo_kb = contradiccion_kb(
            item["afirmacion"].strip(), entidad_id, corr)
        registro = {
            "afirmacion": item["afirmacion"].strip(),
            "cita_original": item["cita_original"].strip(),
            "contradice_kb": contradice,
        }
        if contradice:
            registro["motivo_contradice"] = motivo_kb
        if len(aceptadas) < es.MAX_AFIRMACIONES:
            aceptadas.append(registro)
        else:
            resultado["descartadas"].append((registro["afirmacion"], "exceso"))
    resultado["afirmaciones"] = aceptadas
    return resultado


def registro_afirmacion_libros(evidencia, item):
    """Registro de salida: esquema de T29 + cita_original + contradiccion KB."""
    reg = {
        "entidad_id": evidencia.get("entidad_id"),
        "faceta": evidencia.get("faceta"),
        "fuente_id": evidencia.get("fuente_id"),
        "dominio": evidencia.get("dominio"),
        "periodo": evidencia.get("periodo"),
        "calidad": evidencia.get("calidad"),
        "afirmacion": item["afirmacion"],
        "cita_original": item["cita_original"],
        "contradice_kb": bool(item.get("contradice_kb")),
    }
    if item.get("motivo_contradice"):
        reg["motivo_contradice"] = item["motivo_contradice"]
    return reg


def procesar_evidencia(evidencia, indice, cliente, corr):
    """Procesa una evidencia: localiza la seccion y extrae afirmaciones."""
    sec = indice.seccion(evidencia.get("fuente_id"),
                        evidencia.get("hash_seccion"))
    if sec is None or not (sec.get("texto") or "").strip():
        return {"estado": "sin_texto", "afirmaciones": [], "descartadas": []}
    return extraer_afirmaciones_libros(
        cliente, evidencia.get("entidad_id"), evidencia.get("faceta"),
        sec.get("texto", ""), evidencia.get("idioma"), corr)


def _simulado_libros(sistema, usuario):
    """Respuesta simulada: una afirmacion con cita = primeras palabras del texto."""
    m = re.search(r'"""\n(.*)\n"""', usuario, flags=re.DOTALL)
    texto = m.group(1) if m else ""
    cita = " ".join(texto.split()[:10])
    if not cita:
        return '{"afirmaciones": []}'
    return json.dumps({
        "afirmaciones": [{
            "afirmacion": "Contenido simulado de prueba: %s" % cita[:80],
            "cita_original": cita,
        }],
    }, ensure_ascii=False)


def _cargar_procesados(ruta):
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


def escribir_informe(ruta, stats):
    lineas = [
        "# Informe de afirmaciones de libros (T38)",
        "",
        "- Evidencias procesadas: %d" % stats["procesadas"],
        "- Sin texto localizable (`sin_texto`): %d" % stats["sin_texto"],
        "- Errores del modelo: %d" % stats["errores"],
        "- Afirmaciones aceptadas: %d" % stats["afirmaciones"],
        "- Afirmaciones marcadas `contradice_kb`: %d" % stats["contradicciones"],
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


def main(argv=None, cliente=None):
    """Punto de entrada del extractor de afirmaciones de libros (T38)."""
    parser = argparse.ArgumentParser(
        description="Extrae afirmaciones en espanol con cita verbatim de "
                    "los libros (T38).")
    parser.add_argument("--evidencias", default=DEFAULT_EVIDENCIAS)
    parser.add_argument("--secciones-dir", default=DEFAULT_SECCIONES_DIR)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--limite", type=int, default=0,
                       help="Maximo de evidencias a procesar (0 = todas).")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--simulado", action="store_true",
                       help="Usa un cliente simulado (sin nodos GPU).")
    args = parser.parse_args(argv)

    evidencias = []
    with open(args.evidencias, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                evidencias.append(json.loads(linea))
    if args.limite:
        evidencias = evidencias[:args.limite]

    os.makedirs(args.out_dir, exist_ok=True)
    ruta_af = os.path.join(args.out_dir, "afirmaciones_libros.jsonl")
    ruta_pr = os.path.join(args.out_dir, "procesados.jsonl")
    ruta_in = os.path.join(args.out_dir, "afirmaciones_libros_informe.md")

    procesados = _cargar_procesados(ruta_pr)
    indice = IndiceLibros(args.secciones_dir)
    catalogo = es._catalogo_familias()
    corr = cargar_correspondencias()
    if cliente is None:
        cliente = LLMClient(simulado=_simulado_libros) if args.simulado \
            else LLMClient()

    stats = {
        "procesadas": 0,
        "sin_texto": 0,
        "errores": 0,
        "afirmaciones": 0,
        "contradicciones": 0,
        "descartadas": Counter(),
        "por_familia": Counter(),
    }

    lock = threading.Lock()
    pendientes = [
        ev for ev in evidencias
        if (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))
        not in procesados
    ]
    total = len(pendientes)
    print("Evidencias pendientes: %d" % total, flush=True)

    def registrar(ev, res):
        with lock:
            for item in res["afirmaciones"]:
                fa.write(json.dumps(registro_afirmacion_libros(ev, item),
                                   ensure_ascii=False) + "\n")
                stats["por_familia"][
                    es.familia_de_entidad(ev.get("entidad_id"), catalogo)] += 1
                if item.get("contradice_kb"):
                    stats["contradicciones"] += 1
            for _, motivo in res["descartadas"]:
                stats["descartadas"][motivo] += 1
            fp.write(json.dumps({
                "hash_seccion": ev.get("hash_seccion"),
                "entidad_id": ev.get("entidad_id"),
                "faceta": ev.get("faceta"),
                "estado": res["estado"],
                "n_afirmaciones": len(res["afirmaciones"]),
            }, ensure_ascii=False) + "\n")
            fa.flush()
            fp.flush()
            stats["procesadas"] += 1
            if res["estado"] == "sin_texto":
                stats["sin_texto"] += 1
            elif res["estado"] == "error":
                stats["errores"] += 1
            else:
                stats["afirmaciones"] += len(res["afirmaciones"])
            hecha = stats["procesadas"]
            if hecha % 25 == 0 or hecha == total:
                print("Progresadas %d/%d (afirmaciones=%d, errores=%d)"
                      % (hecha, total, stats["afirmaciones"],
                         stats["errores"]), flush=True)

    def trabajar(ev):
        registrar(ev, procesar_evidencia(ev, indice, cliente, corr))

    with open(ruta_pr, "a", encoding="utf-8") as fp, \
            open(ruta_af, "a", encoding="utf-8") as fa:
        if args.workers > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                list(ex.map(trabajar, pendientes))
        else:
            for ev in pendientes:
                trabajar(ev)

    escribir_informe(ruta_in, stats)
    return stats


if __name__ == "__main__":
    main()
