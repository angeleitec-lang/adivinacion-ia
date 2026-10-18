#!/usr/bin/env python3
"""Lanza Firecrawl para extraer el corpus de adivinación.

Tres modos:

- `scrape` (por defecto): lee `corpus/urls.txt` y extrae CADA URL concreta
  (una página por URL) guardándola en `corpus/raw/<dominio>/<slug>.md`.
  Es el modo correcto para URLs hoja (artículos, guías), ya que el endpoint
  `crawl` solo sigue sub-enlaces bajo la misma ruta.
- `crawl`: rastrea un dominio siguiendo sub-enlaces de la misma ruta
  (útil solo para secciones/índices como un dominio raíz o una carpeta).
- `agent`: usa el endpoint agent de Firecrawl con el prompt de
  `corpus/INSTRUCCIONES_FIRECRAWL.md` para recolección autónoma.

Todo el trabajo queda registrado en `corpus/manifest.json`
(url, dominio, licencia estimada, estado, nº de páginas y fecha), de modo
que `build_dataset.py` puede saltarse las URLs bloqueadas o incompatibles.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

try:
    from firecrawl import Firecrawl
    from firecrawl.types import ScrapeOptions
except ImportError:  # pragma: no cover - firecrawl es opcional hasta lanzar
    Firecrawl = None
    ScrapeOptions = None

PUBLIC_DOMAINS = {
    "wikipedia.org": "CC BY-SA (Wikipedia)",
    "wikisource.org": "dominio público / CC BY-SA",
    "gutenberg.org": "dominio público (Project Gutenberg)",
    "archive.org": "dominio público (varía por obra)",
}


def read_urls(path: Path) -> list[str]:
    """Lee `urls.txt` y devuelve las URLs sin comentarios ni vacías."""
    if not path.exists():
        return []
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc
    return re.sub(r"[^A-Za-z0-9.\-]", "_", netloc) or "desconocido"


def slug_of(url: str) -> str:
    path = unquote(urlparse(url).path).strip("/")
    if not path:
        return "index"
    parts = []
    for seg in path.split("/"):
        seg = re.sub(r"[^A-Za-z0-9]+", "_", seg).strip("_")
        if seg:
            parts.append(seg)
    return "_".join(parts)[-80:] or "index"


def estimate_license(url: str) -> str:
    host = urlparse(url).netloc
    for dom, lic in PUBLIC_DOMAINS.items():
        if host.endswith(dom):
            return lic
    return "consultar"


def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(e.get("url", "")): e for e in data}


def write_manifest(entries: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries.values(), key=lambda e: (e.get("dominio", ""), e.get("url", "")))
    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _markdown_of(doc) -> str:
    if isinstance(doc, dict):
        return doc.get("markdown", "") or ""
    return getattr(doc, "markdown", "") or ""


def _url_of(doc) -> str:
    if isinstance(doc, dict):
        meta = doc.get("metadata", {}) or {}
        return str(meta.get("url") or meta.get("sourceURL") or "")
    meta = getattr(doc, "metadata", None)
    if isinstance(meta, dict):
        return str(meta.get("url") or meta.get("sourceURL") or "")
    return str(getattr(meta, "url", "") or getattr(meta, "sourceURL", "") or "")


def save_page(markdown: str, source_url: str, raw_dir: Path) -> str | None:
    """Guarda una página y devuelve la ruta relativa, o None si está vacía."""
    markdown = (markdown or "").strip()
    if not markdown:
        return None
    domain = domain_of(source_url or "desconocido")
    slug = slug_of(source_url or "")
    target = raw_dir / domain / f"{slug}.md"
    if target.exists():
        short = abs(hash(source_url)) % 0xFFFF
        target = raw_dir / domain / f"{slug}_{short:04x}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return str(target.relative_to(raw_dir))


def crawl_domain(app, url: str, limit: int, raw_dir: Path) -> dict:
    """Rastrea una URL semilla y devuelve la entrada del manifest."""
    entry = {
        "url": url,
        "dominio": domain_of(url),
        "licencia": estimate_license(url),
        "fecha": now_iso(),
        "paginas": 0,
    }
    try:
        if ScrapeOptions is not None:
            res = app.crawl(
                url,
                limit=limit,
                scrape_options=ScrapeOptions(formats=["markdown"]),
            )
        else:  # pragma: no cover
            res = app.crawl(url, limit=limit, formats=["markdown"])
    except Exception as exc:
        msg = str(exc).lower()
        entry["estado"] = "bloqueado" if "robot" in msg else "fallo"
        entry["error"] = str(exc)[:300]
        return entry

    docs = getattr(res, "data", None) or []
    if not docs:
        entry["estado"] = "sin_paginas"
        return entry

    written = 0
    for doc in docs:
        markdown = _markdown_of(doc)
        source = _url_of(doc) or url
        rel = save_page(markdown, source, raw_dir)
        if rel:
            written += 1

    entry["estado"] = "ok"
    entry["paginas"] = written
    return entry


def scrape_domain(app, url: str, raw_dir: Path) -> dict:
    """Extrae una URL concreta (una página) y devuelve la entrada del manifest."""
    entry = {
        "url": url,
        "dominio": domain_of(url),
        "licencia": estimate_license(url),
        "fecha": now_iso(),
        "paginas": 0,
    }
    try:
        doc = app.scrape(url, formats=["markdown"])
    except Exception as exc:
        msg = str(exc).lower()
        entry["estado"] = "bloqueado" if "robot" in msg else "fallo"
        entry["error"] = str(exc)[:300]
        return entry

    markdown = _markdown_of(doc)
    source = _url_of(doc) or url
    rel = save_page(markdown, source, raw_dir)
    entry["estado"] = "ok" if rel else "sin_contenido"
    entry["paginas"] = 1 if rel else 0
    return entry


def run_crawl(app, args, manifest: dict[str, dict]) -> dict[str, dict]:
    urls = read_urls(Path(args.urls))
    if not urls:
        print(f"ERROR: no hay URLs en {args.urls}")
        return manifest

    print(f"URLs semilla a rastrear: {len(urls)}")
    for idx, url in enumerate(urls, 1):
        if args.dry_run:
            print(f"[dry-run] ({idx}/{len(urls)}) {url}")
            continue
        print(f"({idx}/{len(urls)}) {url} ... ", end="", flush=True)
        entry = crawl_domain(app, url, args.limit, Path(args.raw))
        print(f"{entry['estado']} ({entry['paginas']} páginas)")
        manifest[url] = entry
        write_manifest(manifest, Path(args.manifest))
        time.sleep(args.delay)

    return manifest


def run_scrape(app, args, manifest: dict[str, dict]) -> dict[str, dict]:
    urls = read_urls(Path(args.urls))
    if not urls:
        print(f"ERROR: no hay URLs en {args.urls}")
        return manifest

    print(f"URLs a extraer (una página cada una): {len(urls)}")
    for idx, url in enumerate(urls, 1):
        print(f"({idx}/{len(urls)}) {url} ... ", end="", flush=True)
        entry = scrape_domain(app, url, Path(args.raw))
        print(f"{entry['estado']} ({entry['paginas']} páginas)")
        manifest[url] = entry
        write_manifest(manifest, Path(args.manifest))
        time.sleep(args.delay)

    return manifest


def run_agent(app, args, manifest: dict[str, dict]) -> dict[str, dict]:
    prompt_path = Path(args.prompt)
    prompt = prompt_path.read_text(encoding="utf-8")

    agent_urls = None
    if args.agent_urls:
        agent_urls = read_urls(Path(args.agent_urls)) or None

    print("Lanzando agente Firecrawl ...", flush=True)
    if agent_urls:
        res = app.agent(prompt=prompt, urls=agent_urls)
    else:
        res = app.agent(prompt=prompt)

    data = getattr(res, "data", None)
    out_dir = Path(args.raw) / "agent"
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(data, str):
        (out_dir / "agent_output.md").write_text(data, encoding="utf-8")
    else:
        (out_dir / "agent_output.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"Salida del agente guardada en {out_dir}")

    manifest["__agent__"] = {
        "url": "__agent__",
        "dominio": "agent",
        "licencia": "consultar",
        "estado": "ok",
        "fecha": now_iso(),
        "paginas": 1,
    }
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrae el corpus de adivinación con Firecrawl."
    )
    parser.add_argument("--mode", choices=["scrape", "crawl", "agent"], default="scrape",
                        help="Modo de extracción (default: scrape)")
    parser.add_argument("--urls", default="corpus/urls.txt",
                        help="Lista de URLs semilla (default: corpus/urls.txt)")
    parser.add_argument("--prompt", default="corpus/INSTRUCCIONES_FIRECRAWL.md",
                        help="Documento/prompt para el modo agent")
    parser.add_argument("--agent-urls", default="",
                        help="URLs opcionales para acotar el agente (separadas por coma)")
    parser.add_argument("--raw", default="corpus/raw",
                        help="Directorio de salida del markdown (default: corpus/raw)")
    parser.add_argument("--manifest", default="corpus/manifest.json",
                        help="Manifest de resultados (default: corpus/manifest.json)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Máx. páginas por dominio (default: 50)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Segundos entre dominios (default: 1.0)")
    parser.add_argument("--api-key", default=os.environ.get("FIRECRAWL_API_KEY", ""),
                        help="Clave de Firecrawl (o var FIRECRAWL_API_KEY). Vacía en self-host.")
    parser.add_argument("--api-url", default=os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002"),
                        help="URL base de la API Firecrawl (default: http://localhost:3002, self-host)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo lista lo que se haría, sin llamar a Firecrawl")
    args = parser.parse_args(argv)

    if args.mode == "agent" and not args.dry_run and Firecrawl is None:
        print("ERROR: instala firecrawl-py: pip install firecrawl-py")
        return 1

    manifest = load_manifest(Path(args.manifest))

    if args.dry_run:
        urls = read_urls(Path(args.urls))
        print(f"[dry-run] modo={args.mode}, URLs={len(urls)}")
        return 0

    if Firecrawl is None:
        print("ERROR: instala firecrawl-py: pip install firecrawl-py")
        return 1
    es_nube = "api.firecrawl.dev" in args.api_url
    if es_nube and not args.api_key:
        print("ERROR: define FIRECRAWL_API_KEY o pasa --api-key (cloud de Firecrawl)")
        return 1

    app = Firecrawl(api_key=args.api_key, api_url=args.api_url)

    if args.mode == "agent":
        manifest = run_agent(app, args, manifest)
    elif args.mode == "crawl":
        manifest = run_crawl(app, args, manifest)
    else:
        manifest = run_scrape(app, args, manifest)

    write_manifest(manifest, Path(args.manifest))
    print("Manifest actualizado:", args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
