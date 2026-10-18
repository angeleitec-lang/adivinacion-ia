#!/usr/bin/env python3
"""Descubre artículos de Wikipedia ES por categoría y escribe una lista de
URLs lista para `collect_corpus.py`.

Usa solo la API pública de Wikipedia (para descubrir títulos), con pausas y
reintentos con backoff para respetar el rate limit. La extracción del
contenido la sigue haciendo Firecrawl, igual que el resto del corpus.

Ejemplo:
    .venv/bin/python corpus/expand_wikipedia.py --depth 1
    .venv/bin/python corpus/expand_wikipedia.py --categories Tarot Astrología
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://es.wikipedia.org/w/api.php"
UA = "adivinacion-ia-corpus/1.0 (uso local de investigación)"

# Subcategorías que merecen rastrearse (evita ramas tangenciales enormes).
RELEVANT_SUBCAT_KEYWORDS = (
    "arcano", "tarot", "cartas", "cartomancia", "signos", "zodiaco",
    "casas", "planetas", "aspectos", "numerolog", "runa", "quiromancia",
    "adivinaci", "astrolog", "oráculo", "oraculo", "i ching", "geoman",
)


def _call(params: dict, retries: int = 5) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    url = f"{API}?{query}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    raise RuntimeError(f"fallo tras {retries} reintentos: {url}")


def _members(category: str, kind: str) -> list[str]:
    data = _call({
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Categoría:{category}",
        "cmlimit": "500",
        "cmtype": kind,
    })
    return [m["title"] for m in data.get("query", {}).get("categorymembers", [])]


def _relevant(subcat: str) -> bool:
    low = subcat.lower()
    return any(key in low for key in RELEVANT_SUBCAT_KEYWORDS)


def collect(category: str, depth: int, seen_cats: set[str],
            pages: set[str], sleep: float) -> None:
    if category in seen_cats or depth < 0:
        return
    seen_cats.add(category)
    time.sleep(sleep)
    try:
        for title in _members(category, "page"):
            pages.add(title)
    except Exception as exc:  # noqa: BLE001 - seguir con otras categorías
        print(f"  ! categoría {category}: {exc}")
        return
    if depth > 0:
        try:
            subcats = _members(category, "subcat")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! subcategorías {category}: {exc}")
            return
        for title in subcats:
            sub = title.split(":", 1)[-1]
            if _relevant(sub):
                collect(sub, depth - 1, seen_cats, pages, sleep)


def title_to_url(title: str) -> str:
    slug = title.replace(" ", "_")
    return "https://es.wikipedia.org/wiki/" + urllib.parse.quote(slug)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Descubre artículos de Wikipedia ES por categoría."
    )
    parser.add_argument(
        "--categories", nargs="+",
        default=["Tarot", "Cartomancia", "Astrología", "Numerología",
                 "Runas", "Adivinación"],
        help="Categorías raíz a rastrear.",
    )
    parser.add_argument("--depth", type=int, default=1,
                        help="Profundidad de recursión en subcategorías.")
    parser.add_argument("--out", default="corpus/urls_wikipedia.txt",
                        help="Fichero de salida con una URL por línea.")
    parser.add_argument("--sleep", type=float, default=1.5,
                        help="Segundos entre llamadas a la API.")
    parser.add_argument("--max", type=int, default=800,
                        help="Tope de URLs a generar.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo informa, no escribe el fichero.")
    args = parser.parse_args(argv)

    seen_cats: set[str] = set()
    pages: set[str] = set()
    for category in args.categories:
        before = len(pages)
        collect(category, args.depth, seen_cats, pages, args.sleep)
        print(f"  {category}: +{len(pages) - before} (total {len(pages)})")

    urls = sorted({title_to_url(t) for t in pages})[: args.max]
    print(f"Artículos únicos: {len(pages)}  URLs: {len(urls)}")

    if args.dry_run:
        for url in urls[:10]:
            print("  ", url)
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# URLs descubiertas en Wikipedia ES (CC BY-SA)\n"
        + "\n".join(urls) + "\n",
        encoding="utf-8",
    )
    print(f"Escrito: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
