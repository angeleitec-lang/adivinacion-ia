#!/usr/bin/env python3
"""Busca y descarga EPUBs de archive.org sobre las disciplinas del proyecto.

Consulta advancedsearch por subject (inglés + español), se queda con los items
que tienen un EPUB libre (sin access-restricted ni LCP), lo descarga a
corpus/docs_epub/<tema>/ y registra licencia/fuente en un manifest.

Solo stdlib. Ejemplos:
    .venv/bin/python corpus/harvest_epubs.py --dry-run
    .venv/bin/python corpus/harvest_epubs.py --topics tarot astrologia
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/"
DOWNLOAD = "https://archive.org/download/"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SUBJECTS = {
    "tarot": ["tarot", "tarot cards", "cartomancia"],
    "astrologia": ["astrology", "astrología", "astrologia"],
    "numerologia": ["numerology", "numerología"],
    "quiromancia": ["palmistry", "chiromancy", "quiromancia"],
    "iching": ["i ching", "iching", "libro de los cambios"],
    "runas": ["runes", "runic", "runas"],
    "lenormand": ["lenormand"],
    "baraja-espanola": ["spanish playing cards", "baraja española", "naipes"],
    "astrologia-china": ["chinese astrology", "astrología china"],
    "astrologia-vedica": ["vedic astrology", "jyotish", "astrología védica"],
    "ocultismo": ["occultism", "occult", "esotericism", "ocultismo", "esoterismo"],
}


def _get_json(url: str, retries: int = 4):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(1.5 * (attempt + 1))
    return None


def search_docs(terms: list[str], rows: int) -> list[dict]:
    clauses = " OR ".join(f'subject:"{t}"' for t in terms)
    query = f"({clauses}) AND format:\"EPUB\" AND mediatype:texts"
    params = {
        "q": query,
        "fl[]": ["identifier", "title", "creator", "year", "licenseurl",
                 "collection", "downloads"],
        "rows": str(rows),
        "page": "1",
        "output": "json",
        "sort[]": "downloads desc",
    }
    url = SEARCH + "?" + urllib.parse.urlencode(params, doseq=True)
    data = _get_json(url) or {}
    return data.get("response", {}).get("docs", [])


def classify_license(meta: dict, doc: dict) -> str:
    lic = str(doc.get("licenseurl") or meta.get("licenseurl") or "").lower()
    rights = str(meta.get("rights") or "").lower()
    if "publicdomain" in lic or "public domain" in rights:
        return "dominio público"
    if "creativecommons.org/licenses/" in lic:
        try:
            seg = lic.split("/licenses/", 1)[1].split("/")[0]
            return f"CC {seg.upper()}"
        except IndexError:
            return "CC (verificar)"
    return "consultar"


def _is_restricted(meta: dict) -> bool:
    if str(meta.get("access-restricted-item", "")).lower() == "true":
        return True
    inner = meta.get("metadata", {}) or {}
    return str(inner.get("access-restricted-item", "")).lower() == "true"


def _epub_files(meta: dict) -> list[dict]:
    out = []
    for f in meta.get("files", []) or []:
        name = f.get("name", "")
        low = name.lower()
        if not low.endswith(".epub"):
            continue
        if "lcp" in low or "encrypted" in low:
            continue
        out.append(f)
    return out


def _size_of(f: dict) -> int:
    try:
        return int(f.get("size", 0) or 0)
    except (TypeError, ValueError):
        return 0


def download(meta: dict, item_id: str, filename: str, target: Path,
             max_bytes: int) -> int | None:
    enc = urllib.parse.quote(filename, safe="")
    urls = [f"{DOWNLOAD}{urllib.parse.quote(item_id)}/{enc}"]
    directory = meta.get("dir")
    for host in (meta.get("server"), meta.get("d1"), meta.get("d2")):
        if host and directory:
            urls.append(f"https://{host}{directory}/{enc}")
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            if not data or len(data) > max_bytes:
                continue
            target.write_bytes(data)
            return len(data)
        except Exception:  # noqa: BLE001 - probar siguiente URL
            if target.exists():
                target.unlink()
    return None


def harvest_topic(topic: str, terms: list[str], args, manifest: dict) -> int:
    docs = search_docs(terms, args.rows)
    taken = 0
    for doc in docs:
        if taken >= args.max_per_topic:
            break
        item_id = doc.get("identifier")
        if not item_id:
            continue
        meta = _get_json(META + urllib.parse.quote(item_id))
        if not meta or _is_restricted(meta):
            continue
        epubs = _epub_files(meta)
        if not epubs:
            continue
        f = epubs[0]
        if _size_of(f) > args.max_size_mb * 1024 * 1024:
            continue
        license_ = classify_license(meta, doc)
        title = doc.get("title") or meta.get("metadata", {}).get("title") or item_id
        entry = {
            "id": item_id,
            "tema": topic,
            "titulo": title,
            "autor": doc.get("creator") or meta.get("metadata", {}).get("creator"),
            "anio": doc.get("year"),
            "licencia": license_,
            "fuente": f"https://archive.org/details/{item_id}",
            "fichero": f["name"],
            "estado": "candidato",
        }
        if args.dry_run:
            print(f"  [{topic}] {title}  ({license_})  {f['name']}")
            manifest[item_id] = entry
            taken += 1
            continue
        target_dir = Path(args.out) / topic
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f["name"]
        n = download(meta, item_id, f["name"], target,
                     args.max_size_mb * 1024 * 1024)
        if n is None:
            entry["estado"] = "fallo"
            print(f"  ! fallo {item_id}")
        else:
            entry["estado"] = "ok"
            entry["bytes"] = n
            print(f"  ok [{topic}] {title[:70]}  {n // 1024} KB  ({license_})")
        manifest[item_id] = entry
        write_manifest(args.manifest, manifest)
        taken += 1
        time.sleep(args.delay)
    return taken


def write_manifest(path: str, manifest: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Recolector de EPUBs de archive.org por tema.")
    parser.add_argument("--topics", nargs="+", choices=sorted(SUBJECTS),
                        default=None, help="Temas a recolectar (default: todos).")
    parser.add_argument("--rows", type=int, default=200,
                        help="Resultados a pedir por tema a advancedsearch.")
    parser.add_argument("--max-per-topic", type=int, default=20,
                        help="EPUBs descargados por tema.")
    parser.add_argument("--max-size-mb", type=int, default=200)
    parser.add_argument("--out", default="corpus/docs_epub")
    parser.add_argument("--manifest", default="corpus/docs_epub/manifest.json")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    manifest = {}
    if Path(args.manifest).exists():
        try:
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    topics = args.topics or list(SUBJECTS)
    total = 0
    for topic in topics:
        print(f"\n== {topic}")
        total += harvest_topic(topic, SUBJECTS[topic], args, manifest)
        if not args.dry_run:
            write_manifest(args.manifest, manifest)
    print(f"\nTotal: {total} EPUBs. Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
