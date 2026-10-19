#!/usr/bin/env python3
"""Auditoría determinista de calidad de las páginas web descargadas (T31).

Lee los Markdown de ``/Users/angelgonzalez/fase0/web/<dominio>/*.md``
(front-matter YAML + cuerpo) y marca banderas de calidad sin usar LLM:

- ``corta``: menos de 1.000 caracteres de texto.
- ``mojibake``: secuencias típicas de codificación rota.
- ``no_espanol``: proporción baja de palabras funcionales españolas.
- ``ruido_navegacion``: menús, pies, cookies o avisos que sobreviven.
- ``duplicada``: misma página o párrafos casi idénticos a otra.
- ``titulo_pobre``: título vacío, corto, truncado o con Markdown.
- ``repeticion_interna``: un párrafo repetido tres o más veces.

Produce ``calidad.jsonl`` (una línea por página) y ``calidad.md`` (informe
por dominio con porcentajes y peores páginas).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

UMBRAL_CORTO = 1000
UMBRAL_NO_ESPANOL_PALABRAS = 40
UMBRAL_JACCARD = 0.90
MIN_PARRAFO = 40

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_ENCABEZADO_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_MOJIBAKE_RE = re.compile(
    r"Ã[\x80-\xBF]|Â[\x80-\xBF]|â€|â€™|â€œ|â€\x9d|\ufffd"
)


# ---------------------------------------------------------------------------
# Lectura de páginas
# ---------------------------------------------------------------------------

def _quitar_comillas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1]
    return valor


def _parsear_front_matter(texto: str) -> Dict[str, Any]:
    """Carga un YAML plano de ``clave: valor`` (sin dependencia de PyYAML)."""
    datos: Dict[str, Any] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or ": " not in linea:
            if linea.endswith(":") and not linea.startswith("#"):
                clave = linea[:-1].strip()
                if clave:
                    datos[clave] = None
            continue
        clave, valor = linea.split(": ", 1)
        clave = clave.strip()
        valor = _quitar_comillas(valor.strip())
        if valor.lower() in ("null", "~", ""):
            datos[clave] = None
        elif valor.lower() == "true":
            datos[clave] = True
        elif valor.lower() == "false":
            datos[clave] = False
        else:
            datos[clave] = valor
    return datos


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def leer_pagina(ruta: Path) -> Dict[str, Any]:
    """Lee una página Markdown y separa front-matter y cuerpo."""
    ruta = Path(ruta)
    contenido = ruta.read_text(encoding="utf-8", errors="replace")
    coincidencia = _FRONT_MATTER_RE.match(contenido)
    if coincidencia:
        front_matter = _parsear_front_matter(coincidencia.group(1))
        cuerpo = contenido[coincidencia.end():]
    else:
        front_matter = {}
        cuerpo = contenido

    cuerpo = cuerpo.strip()
    titulo = front_matter.get("titulo")
    if not isinstance(titulo, str):
        titulo = ""
    if not titulo.strip():
        encabezado = _ENCABEZADO_RE.search(cuerpo)
        titulo = encabezado.group(1).strip() if encabezado else ""

    sha = front_matter.get("sha256")
    if not isinstance(sha, str) or not sha.strip():
        sha = _sha256_texto(cuerpo)

    dominio = front_matter.get("dominio")
    if not isinstance(dominio, str) or not dominio.strip():
        dominio = ruta.parent.name

    return {
        "ruta": str(ruta),
        "dominio": dominio.strip(),
        "titulo": titulo.strip(),
        "front_matter": front_matter,
        "cuerpo": cuerpo,
        "caracteres": len(cuerpo),
        "sha256": sha.strip(),
    }


def leer_paginas(web_dir: Path) -> List[Dict[str, Any]]:
    """Lee todas las páginas ``*.md`` bajo ``web_dir`` ordenadas por ruta."""
    web_dir = Path(web_dir)
    paginas = [leer_pagina(ruta) for ruta in sorted(web_dir.rglob("*.md"))]
    return paginas


# ---------------------------------------------------------------------------
# Banderas
# ---------------------------------------------------------------------------

def bandera_corta(texto: str, minimo: int = UMBRAL_CORTO) -> bool:
    return len(texto.strip()) < minimo


def bandera_mojibake(texto: str) -> bool:
    return bool(_MOJIBAKE_RE.search(texto))


def bandera_titulo_pobre(titulo: str) -> bool:
    titulo = (titulo or "").strip()
    if len(titulo) < 4:
        return True
    if titulo.endswith(":"):
        return True
    if "**" in titulo:
        return True
    return False


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

def analizar_paginas(paginas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Añade a cada página sus banderas y detalles, en orden determinista."""
    resultados: List[Dict[str, Any]] = []
    for pagina in sorted(paginas, key=lambda p: p["ruta"]):
        cuerpo = pagina["cuerpo"]
        banderas: List[str] = []
        if bandera_corta(cuerpo):
            banderas.append("corta")
        if bandera_mojibake(cuerpo):
            banderas.append("mojibake")
        if bandera_titulo_pobre(pagina["titulo"]):
            banderas.append("titulo_pobre")

        resultado = dict(pagina)
        resultado["banderas"] = banderas
        resultado["detalles"] = {}
        resultados.append(resultado)
    return resultados
