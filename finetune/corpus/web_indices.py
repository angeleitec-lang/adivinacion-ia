#!/usr/bin/env python3
"""Descubrimiento de páginas desde índices configurables (A3.4).

Para sitios con una página por carta/número pero sin patrón de URL fijo,
separte de una página índice y se siguen los enlaces que cumplan una
regex configurable.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests


RUTA_CONFIG = os.path.join(os.path.dirname(__file__), os.pardir,
                           "knowledge", "sitios_indice.json")


def cargar_config(ruta: Optional[str] = None) -> Dict[str, Any]:
    """Carga la configuración de sitios índice."""
    with open(ruta or RUTA_CONFIG, encoding="utf-8") as f:
        return json.load(f)


def _normalizar_url(base: str, href: str) -> str:
    """Normaliza y resuelve URL relativa."""
    return urljoin(base, href)


def _mismo_dominio(url: str, dominio: str) -> bool:
    """Verifica que la URL pertenezca al mismo dominio (incluye www)."""
    netloc = urlparse(url).netloc
    # Normalizar: quitar www. si el dominio no lo tiene
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if dominio.startswith("www."):
        dominio = dominio[4:]
    return netloc == dominio


def _extraer_enlaces(html: str, base_url: str, dominio: Optional[str] = None) -> List[str]:
    """Extrae todos los enlaces <a href> del HTML, opcionalmente filtrando por dominio.

    Resuelve URLs relativas con urljoin; descarta #ancla, mailto:, tel:, javascript:, data:.
    Quita el fragmento #… de las URLs resultantes. Si tras quitar el fragmento la URL
    es igual a `base_url`, también se descarta.
    """
    patron = re.compile(r'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    enlaces = []
    for match in patron.finditer(html):
        href = match.group(1)
        # Descartar hrefs que empiecen por #
        if href.startswith("#"):
            continue
        url_norm = _normalizar_url(base_url, href)
        # Descartar si tras quitar fragmento la URL es la misma que base_url
        base_sin_fragmento = base_url.split("#")[0]
        if url_norm == base_sin_fragmento:
            continue
        # Filtrar esquemas no deseados
        if url_norm.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        # Quita el fragmento #… de las URLs resultantes
        if "#" in url_norm.split("?")[0]:
            url_norm = url_norm.split("#")[0]
        if dominio is None or _mismo_dominio(url_norm, dominio):
            enlaces.append(url_norm)
    return enlaces


def _filtrar_por_regex(urls: List[str], regex: str, dominio: str) -> List[str]:
    """Filtra URLs por regex y mismo dominio."""
    patron = re.compile(regex)
    filtradas = []
    for url in urls:
        if _mismo_dominio(url, dominio) and patron.search(url):
            filtradas.append(url)
    return filtradas


def _deduplicar_urls(urls: List[str]) -> List[str]:
    """Elimina duplicados preservando orden."""
    vistos = set()
    unicas = []
    for url in urls:
        if url not in vistos:
            vistos.add(url)
            unicas.append(url)
    return unicas


def _seguir_indice_unico(
    indice_url: str,
    cliente,
    regex: str,
    dominio: str,
    limite: int,
    timeout: float,
) -> List[str]:
    """Secuencia interna de `seguir_indice` para un solo URL de índice."""
    resp = cliente.get(indice_url)
    if resp["estado"] != "ok" or not resp.get("html"):
        return []

    # Extraer enlaces
    enlaces = _extraer_enlaces(resp["html"], indice_url, dominio)

    # Filtrar por regex y dominio
    filtradas = _filtrar_por_regex(enlaces, regex, dominio)

    # Deduplicar
    unicas = _deduplicar_urls(filtradas)

    # Aplicar límite
    return unicas[:limite]


def seguir_indice(
    sitio_cfg: Dict[str, Any],
    cliente,
    limite: int = 50,
    timeout: float = 30.0,
) -> List[str]:
    """Descarga el índice, extrae enlaces, filtra por regex y dominio.

    Args:
        sitio_cfg: dict con keys: nombre, indice, regex, dominio, familia, prioridad
        cliente: instancia de web_fetch.Cliente (o compatible con .get(url))
        limite: máximo de URLs a devolver
        timeout: timeout por petición

    Returns:
        Lista de URLs únicas, filtradas y desduplicadas (máx. `limite`)
    """
    indice = sitio_cfg["indice"]
    regex = sitio_cfg["regex"]
    dominio = sitio_cfg["dominio"]

    if isinstance(indice, list):
        # Varios índices: descarga todas, junta los enlaces antes de filtrar
        todas_enlaces: List[str] = []
        for idx_url in indice:
            resp = cliente.get(idx_url)
            if resp["estado"] != "ok" or not resp.get("html"):
                # Si falla este índice, se continúa con los demás
                continue
            enlaces = _extraer_enlaces(resp["html"], idx_url, dominio)
            todas_enlaces.extend(enlaces)
        # Filtrar por regex y dominio sobre la unión
        filtradas = _filtrar_por_regex(todas_enlaces, regex, dominio)
        # Deduplicar preservando orden
        unicas = _deduplicar_urls(filtradas)
        # Aplicar límite
        return unicas[:limite]
    else:
        # Un solo índice (retrocompatible)
        return _seguir_indice_unico(indice, cliente, regex, dominio, limite, timeout)


def seguir_indice_multiples(
    config_path: Optional[str] = None,
    cliente=None,
    limite_por_sitio: int = 50,
    timeout: float = 30.0,
    solo_sitios: Optional[List[str]] = None,
) -> List[str]:
    """Ejecuta seguir_indice para todos los sitios de la config (o filtrados).

    Args:
        config_path: ruta al JSON de config (default: RUTA_CONFIG)
        cliente: instancia de Cliente (si None, crea uno default)
        limite_por_sitio: límite por sitio
        timeout: timeout por petición
        solo_sitios: lista de nombres de sitios a procesar (None = todos)

    Returns:
        Lista combinada de URLs de todos los sitios procesados.
    """
    from web_fetch import Cliente
    config = cargar_config(config_path)
    if cliente is None:
        cliente = Cliente()

    sitios = config["sitios"]
    if solo_sitios:
        sitios = [s for s in sitios if s["nombre"] in solo_sitios]

    todas_urls = []
    for sitio in sitios:
        urls = seguir_indice(sitio, cliente, limite=limite_por_sitio, timeout=timeout)
        todas_urls.extend(urls)

    return _deduplicar_urls(todas_urls)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Descubre URLs desde índices configurables")
    parser.add_argument("--config", help="Ruta al JSON de config")
    parser.add_argument("--limite", type=int, default=50, help="Límite por sitio")
    parser.add_argument("--solo", help="Lista de sitios separados por coma")
    parser.add_argument("--out", help="Archivo de salida JSONL")
    args = parser.parse_args()

    solo = args.solo.split(",") if args.solo else None
    urls = seguir_indice_multiples(args.config, limite_por_sitio=args.limite,
                                   solo_sitios=solo)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for url in urls:
                f.write(json.dumps({"url": url}, ensure_ascii=False) + "\n")
    else:
        for url in urls:
            print(url)
