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

_PALABRAS_ES = frozenset("""
a al algo algunas algunos ante antes aunque cada como con contra cual cuando
de del desde donde dos durante e el ella ellas ellos en entre era eran es esa
esas ese eso esos esta estaba estado estas este esto estos fue fueron ha hace
hacen hasta hay la las le les lo los más me mientras mi mis mucho muchos muy
nada ni no nos nosotros o os otra otras otro otros para pero poco por porque
que qué quien quienes se sea según ser si sí sin sino sobre son su sus también
tanto te tiene tienen todo todos tu tus tú un una uno unos y ya yo
""".split())

_PALABRAS_EN = frozenset("""
a about all also an and any are as at be been before being between both but by
can could did do does doing down each few for from further had has have having
he her here hers him his how i if in into is it its itself just me more most my
no not now of off on once only or other our out over own same she should so
some such than that the their them then there these they this those through to
too under until up very was we were what when where which while who whom why
will with would you your yours
""".split())

_KEYWORDS_RUIDO = (
    "inicio", "menú", "menu", "contacto", "aviso legal", "aviso de cookies",
    "política de privacidad", "politica de privacidad", "política de cookies",
    "politica de cookies", "cookies", "compartir", "suscríbete", "suscribete",
    "newsletter", "síguenos", "siguenos", "todos los derechos", "copyright",
    "©", "iniciar sesión", "iniciar sesion", "registrarse", "buscar",
    "publicidad", "aceptar", "rechazar", "home", "blog", "quiénes somos",
    "quienes somos", "sobre nosotros", "términos", "terminos",
)

_VERBO_RE = re.compile(
    r"\b\w{3,}(?:ar|er|ir|ando|iendo|ado|ada|idos|idas|aba|aban|"
    r"ía|ían|ó|aron|ieron|é|aste|iste)\b",
    re.IGNORECASE,
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


def bandera_no_espanol(texto: str) -> bool:
    """Heurística: texto largo con pocas palabras funcionales españolas.

    Solo se pronuncia si hay al menos 40 palabras y presencia apreciable de
    palabras funcionales inglesas; así no marca textos sin función conocida.
    """
    palabras = re.findall(r"[a-záéíóúüñ]+", texto.lower())
    if len(palabras) < UMBRAL_NO_ESPANOL_PALABRAS:
        return False
    total = len(palabras)
    es = sum(1 for palabra in palabras if palabra in _PALABRAS_ES) / total
    en = sum(1 for palabra in palabras if palabra in _PALABRAS_EN) / total
    return es < 0.08 and en >= 0.05


def _linea_ruido(linea: str) -> bool:
    texto = linea.strip()
    if not texto or texto.startswith("#"):
        return False
    texto = re.sub(r"^(?:[-*+>]\s*)+", "", texto).strip()
    if not texto:
        return False
    minusculas = texto.lower()
    if any(clave in minusculas for clave in _KEYWORDS_RUIDO):
        return True
    if len(texto) > 60 or len(texto.split()) > 8:
        return False
    if re.search(r"[.!?;:…]$", texto):
        return False
    if _VERBO_RE.search(texto):
        return False
    return True


def bandera_ruido_navegacion(texto: str) -> bool:
    """Detecta tres o más líneas cortas consecutivas típicas de navegación."""
    consecutivas = 0
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        if _linea_ruido(linea):
            consecutivas += 1
            if consecutivas >= 3:
                return True
        else:
            consecutivas = 0
    return False


def _normalizar_parrafo(parrafo: str) -> str:
    parrafo = parrafo.strip().lower()
    parrafo = re.sub(r"[^\w\s]", " ", parrafo)
    return re.sub(r"\s+", " ", parrafo).strip()


def extraer_parrafos(texto: str) -> List[str]:
    """Extrae párrafos normalizados (sin encabezados ni líneas cortas)."""
    parrafos: List[str] = []
    for bloque in re.split(r"\n+", texto):
        bloque = bloque.strip()
        if not bloque or bloque.startswith("#"):
            continue
        bloque = re.sub(r"^(?:[-*+>]\s*)+", "", bloque)
        normalizado = _normalizar_parrafo(bloque)
        if len(normalizado) >= MIN_PARRAFO:
            parrafos.append(normalizado)
    return parrafos


def parrafos_repetidos(texto: str, minimo: int = 3) -> List[Tuple[str, int]]:
    """Devuelve los párrafos normalizados que aparecen ``minimo`` veces o más."""
    cuenta = Counter(extraer_parrafos(texto))
    repetidos = [(p, n) for p, n in cuenta.items() if n >= minimo]
    return sorted(repetidos, key=lambda par: (-par[1], par[0]))


def bandera_repeticion_interna(texto: str) -> bool:
    return bool(parrafos_repetidos(texto))


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
        if bandera_no_espanol(cuerpo):
            banderas.append("no_espanol")
        if bandera_ruido_navegacion(cuerpo):
            banderas.append("ruido_navegacion")
        if bandera_titulo_pobre(pagina["titulo"]):
            banderas.append("titulo_pobre")
        repetidos = parrafos_repetidos(cuerpo)
        if repetidos:
            banderas.append("repeticion_interna")

        resultado = dict(pagina)
        resultado["banderas"] = banderas
        resultado["detalles"] = {}
        if repetidos:
            resultado["detalles"]["repeticion_interna"] = [
                {"parrafo": parrafo[:160], "veces": veces}
                for parrafo, veces in repetidos
            ]
        resultados.append(resultado)
    return resultados
