#!/usr/bin/env python3
"""Extracción de páginas HTML a Markdown con procedencia (A3.3).

Usa trafilatura para extraer el contenido principal, descarta páginas cortas,
elimina frases de navegación/comercial y guarda Markdown con front-matter YAML.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import trafilatura


# ---------------------------------------------------------------------------
# Frases de navegación/comercial a eliminar (insensible a mayúsculas)
# ---------------------------------------------------------------------------

FRASES_RUIDO = [
    "suscríbete", "suscribete", "subscribe",
    "compra", "comprar", "buy", "añadir al carrito", "añadir al carrito",
    "agregar al carrito", "add to cart", "ver productos", "ver productos relacionados",
    "lee también", "leer también", "read also", "continúa leyendo", "continuar leyendo",
    "regístrate", "registrate", "sign up", "iniciar sesión", "iniciar sesion",
    "cookie", "política de privacidad", "privacy policy", "términos de uso",
    "terms of service", "aceptar cookies", "accept cookies",
    "publicidad", "advertisement", "anuncio", "sponsored",
    "newsletter", "boletín", "boletin", "no te pierdas",
    "síguenos", "siguenos", "follow us", "compártelo", "compartelo",
    "share", "whatsapp", "telegram", "facebook", "twitter", "instagram",
]


# ---------------------------------------------------------------------------
# YAML simple para front-matter (evita dependencia PyYAML)
# ---------------------------------------------------------------------------

def _yaml_dumper(data: Dict[str, Any]) -> str:
    """Dumper YAML simple para front-matter (solo tipos básicos)."""
    lines = []
    for k, v in data.items():
        if v is None:
            lines.append(f"{k}: null")
        elif isinstance(v, bool):
            lines.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, str):
            # Escapar comillas y caracteres especiales
            escaped = v.replace('"', '\\"').replace("'", "\\'")
            if "\n" in v or ":" in v or '"' in v or "'" in v:
                lines.append(f'{k}: "{escaped}"')
            else:
                lines.append(f"{k}: {escaped}")
        else:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Frases de navegación/comercial a eliminar (insensible a mayúsculas)
# ---------------------------------------------------------------------------

FRASES_RUIDO = [
    "suscríbete", "suscribete", "subscribe",
    "compra", "comprar", "buy", "añadir al carrito", "añadir al carrito",
    "agregar al carrito", "add to cart", "ver productos", "ver productos relacionados",
    "lee también", "leer también", "read also", "continúa leyendo", "continuar leyendo",
    "regístrate", "registrate", "sign up", "iniciar sesión", "iniciar sesion",
    "cookie", "política de privacidad", "privacy policy", "términos de uso",
    "terms of service", "aceptar cookies", "accept cookies",
    "publicidad", "advertisement", "anuncio", "sponsored",
    "newsletter", "boletín", "boletin", "no te pierdas",
    "síguenos", "siguenos", "follow us", "compártelo", "compartelo",
    "share", "whatsapp", "telegram", "facebook", "twitter", "instagram",
]


# ---------------------------------------------------------------------------
# Funciones de limpieza
# ---------------------------------------------------------------------------

# Coincidencia con límite de palabra: «compra» no casa dentro de «comprador»
_PATRONES_RUIDO = [re.compile(r"\b" + re.escape(frase) + r"\b", re.IGNORECASE)
                   for frase in FRASES_RUIDO]

# Una línea que contenga ruido solo se borra si es corta (navegación/comercial)
MAX_PALABRAS_RUIDO = 12


def _contiene_ruido(linea_lower: str) -> bool:
    """True si la línea contiene alguna frase de ruido como palabra completa."""
    return any(p.search(linea_lower) for p in _PATRONES_RUIDO)


def _es_solo_ruido(linea_lower: str) -> bool:
    """True si, quitadas las frases de ruido, no queda nada alfanumérico."""
    resto = linea_lower
    for p in _PATRONES_RUIDO:
        resto = p.sub(" ", resto)
    return not re.search(r"\w", resto)


def _limpiar_ruido(texto: str) -> str:
    """Borra líneas cortas de navegación/comercial o que son solo ruido.

    Respeta la prosa larga (> MAX_PALABRAS_RUIDO palabras) aunque contenga
    palabras de la lista, y la prosa corta sin ruido. La coincidencia es con
    límite de palabra, así «comprador» o «anuncia» no se confunden con
    «compra» o «anuncio».
    """
    lineas = texto.splitlines()
    limpias = []
    for linea in lineas:
        stripped = linea.strip()
        # Saltar líneas muy cortas que parecen ruido
        if len(stripped) <= 2:
            continue
        lower = stripped.lower()
        if not _contiene_ruido(lower):
            limpias.append(linea)
            continue
        # Línea que es solo ruido: fuera sea cual sea su longitud
        if _es_solo_ruido(lower):
            continue
        # Ruido en línea corta (navegación/comercial): fuera
        if len(lower.split()) <= MAX_PALABRAS_RUIDO:
            continue
        # Prosa larga: se conserva
        limpias.append(linea)
    return "\n".join(limpias)


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Extracción principal
# ---------------------------------------------------------------------------

def extraer(
    html: str,
    url: str,
    *,
    entidad_id: Optional[str] = None,
    faceta: Optional[str] = None,
    familia: Optional[str] = None,
    min_chars: int = 1000,
) -> Optional[Dict[str, Any]]:
    """Extrae el contenido principal de una página HTML a Markdown con metadatos.

    Args:
        html: HTML crudo de la página
        url: URL de origen
        entidad_id: ID de la entidad (opcional)
        faceta: tipo de faceta (opcional)
        familia: familia de la entidad (opcional)
        min_chars: mínimo de caracteres para considerar válida (default 1000)

    Returns:
        dict con: titulo, texto_md, idioma, chars, hash, front_matter (dict)
        o None si la página es demasiado corta
    """
    # Extraer con trafilatura (precisión alta, markdown, sin enlaces, con tablas)
    md = trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_tables=True,
        favor_precision=True,
        include_comments=False,
        include_formatting=True,
    )

    if not md or len(md.strip()) < min_chars:
        return None

    # Limpiar ruido
    md = _limpiar_ruido(md)

    # Detectar idioma (simple, basado en trafilatura o heurística)
    idioma = "es"  # default para nuestro corpus

    # Título: primera línea que parece título (heurística simple)
    lineas = md.splitlines()
    titulo = ""
    for l in lineas:
        l_strip = l.strip()
        if l_strip and not l_strip.startswith("#") and len(l_strip) > 5:
            titulo = l_strip[:200]
            break

    chars = len(md)
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()

    # Dominio para front-matter
    from urllib.parse import urlparse
    dominio = urlparse(url).netloc

    # Front-matter YAML
    front_matter = {
        "url": url,
        "dominio": dominio,
        "titulo": titulo,
        "entidad_id": entidad_id,
        "faceta": faceta,
        "familia": familia,
        "idioma": idioma,
        "fecha": None,  # se puede rellenar luego
        "sha256": sha,
        "licencia_hint": "consultar",
    }

    return {
        "titulo": titulo,
        "texto_md": md,
        "idioma": idioma,
        "chars": chars,
        "hash": sha,
        "front_matter": front_matter,
    }


def guardar_markdown(
    extraccion: Dict[str, Any],
    out_dir: Path,
    slug: str,
) -> Path:
    """Guarda el Markdown con front-matter YAML en <dominio>/<slug>.md."""
    fm = extraccion["front_matter"]
    dominio = fm["dominio"]
    out_path = out_dir / dominio / f"{slug}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Construir YAML front-matter + contenido
    fm_yaml = _yaml_dumper(fm)
    contenido = f"---\n{fm_yaml}\n---\n\n{extraccion['texto_md']}\n"
    out_path.write_text(contenido, encoding="utf-8")
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extrae HTML a Markdown con metadatos")
    parser.add_argument("--html", required=True, help="Archivo HTML de entrada")
    parser.add_argument("--url", required=True, help="URL de origen")
    parser.add_argument("--out-dir", required=True, help="Directorio de salida")
    parser.add_argument("--slug", required=True, help="Slug para el archivo de salida")
    parser.add_argument("--entidad-id", help="ID de la entidad")
    parser.add_argument("--faceta", help="Faceta")
    parser.add_argument("--familia", help="Familia")
    args = parser.parse_args()

    with open(args.html, encoding="utf-8") as f:
        html = f.read()

    res = extraer(html, args.url, entidad_id=args.entidad_id,
                  faceta=args.faceta, familia=args.familia)
    if res:
        out_path = Path(args.out_dir)
        guardar_markdown(res, out_path, args.slug)
        print(f"OK: {res['chars']} chars -> {out_path}")
    else:
        print("DESCARTADA: menos de 1000 caracteres")
