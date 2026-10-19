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

import juez


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
