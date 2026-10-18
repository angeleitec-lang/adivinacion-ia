#!/usr/bin/env python3
"""Descarga libros clásicos (PDF/EPUB) de archive.org para el corpus.

Lista curada a mano: dominio público (Papus, Waite, Cheiro, Sanger, Lévi,
Mathers, Alan Leo...) y algunos de licencia dudosa marcados como
'consultar' (no usar en el producto monetizado sin revisar).

Uso:
    .venv/bin/python corpus/fetch_documents.py --dry-run
    .venv/bin/python corpus/fetch_documents.py
    .venv/bin/python corpus/fetch_documents.py --only tarot
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

METADATA = "https://archive.org/metadata/"
DOWNLOAD = "https://archive.org/download/"
UA = "adivinacion-ia-corpus/1.0 (uso local de investigación)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# id, familia, licencia, nota
CURATED: list[tuple[str, str, str, str]] = [
    # --- Tarot ---
    ("tarotofbohemians00papu_0", "tarot",
     "dominio público (1896)",
     "Papus, The Tarot of the Bohemians"),
    ("a.-e.-waite-the-pictorial-key-to-the-tarot", "tarot",
     "dominio público (1911)",
     "A. E. Waite, The Pictorial Key to the Tarot"),
    ("the-symbolism-of-the-tarot-ouspensky_202503", "tarot",
     "dominio público",
     "P. D. Ouspensky, The Symbolism of the Tarot"),
    ("the-book-t-the-tarot", "tarot",
     "dominio público (verificar)",
     "S. L. MacGregor Mathers, The Book T"),
    # --- Ocultismo / magia ---
    ("transcendental-magic-eliphas-levi", "ocultismo",
     "dominio público (1896)",
     "Éliphas Lévi, Transcendental Magic"),
    ("diccionario-de-ciencias-ocultas", "ocultismo",
     "consultar (sin licencia registrada)",
     "Diccionario de ciencias ocultas"),
    ("libro-primero-historia-de-las-ciencias-ocultas", "ocultismo",
     "consultar (sin licencia registrada)",
     "Historia de las ciencias ocultas"),
    # --- Quiromancia ---
    ("practicepalmist01saingoog", "quiromancia",
     "dominio público (1897)",
     "Sanger, The Practice of Palmistry"),
    ("descriptivement01mertgoog", "quiromancia",
     "dominio público (1899)",
     "Descriptive Mentality (head, face and hand)"),
    ("palmistryforall00cheigoog", "quiromancia",
     "dominio público (1910)",
     "Cheiro, Palmistry for All"),
    ("cheiroslanguageo00hamo", "quiromancia",
     "dominio público (1900)",
     "Cheiro, The Language of the Hand"),
    # --- Astrología ---
    ("bub_gb_8CwSAAAAYAAJ", "astrologia",
     "dominio público (1899)",
     "Alan Leo, Astrology for All"),
    ("tratados-varios-manuscrito-recopilados-y-copiados-por-"
     "macario-farinas-del-corral", "astrologia",
     "Public Domain Mark (manuscrito 1700)",
     "Tratados varios (astrología, s. XVIII)"),
    ("montero-s.-diccionario-de-adivinos-magos-y-astrologos-de-la-"
     "antiguedad-ocr-1997", "astrologia",
     "CC BY-ND (consultar)",
     "Montero, Diccionario de adivinos, magos y astrólogos"),
    # --- Numerología ---
    ("numerologia-portal-del-destino-helyn-hitchcock", "numerologia",
     "Public Domain Mark (verificar)",
     "Numerología, portal del destino"),
]

# Preferencia de formatos: texto extraíble primero.
FORMAT_PRIORITY = ("text pdf", "additional text pdf", "epub",
                   "image container pdf", "djvu.txt")


def _get_json(url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception:  # noqa: BLE001
            time.sleep(2 ** attempt)
    raise RuntimeError(f"no se pudo leer {url}")


def _rank_files(files: list[dict]) -> list[dict]:
    """Devuelve los ficheros candidatos ordenados por preferencia.

    Se devuelven todos (no solo el mejor) para poder probar el siguiente
    formato si la descarga del primero falla en el servidor.
    """
    candidates: list[tuple[int, dict]] = []
    for f in files:
        name = f.get("name", "")
        fmt = (f.get("format") or "").lower()
        if not name:
            continue
        if "lcp" in name.lower() or "encrypted" in fmt:
            continue
        for rank, want in enumerate(FORMAT_PRIORITY):
            if want in fmt:
                candidates.append((rank, f))
                break
    candidates.sort(key=lambda pair: pair[0])
    return [f for _, f in candidates]


def download(item_id: str, dest: Path, max_bytes: int) -> tuple[str, int]:
    meta = _get_json(METADATA + urllib.parse.quote(item_id))
    info = meta.get("metadata", {}) or {}
    if str(info.get("access-restricted-item", "")).lower() == "true":
        raise RuntimeError("préstamo restringido (no descargable)")

    candidates = _rank_files(meta.get("files", []) or [])
    if not candidates:
        raise RuntimeError("sin PDF/EPUB descargable")

    dest.mkdir(parents=True, exist_ok=True)
    last_error = "sin candidatos válidos"
    for chosen in candidates:
        name = chosen["name"]
        size = int(chosen.get("size") or 0)
        if size and size > max_bytes:
            last_error = f"demasiado grande ({size / 1e6:.0f} MB)"
            continue
        target = dest / Path(name).name.replace("/", "_")
        enc_name = urllib.parse.quote(name, safe="")
        urls = [f"{DOWNLOAD}{urllib.parse.quote(item_id)}/{enc_name}"]
        dir_ = (meta.get("dir") or "").rstrip("/")
        for host_key in ("server", "d1", "d2"):
            host = meta.get(host_key)
            if host and dir_:
                urls.append(f"https://{host}{dir_}/{enc_name}")

        downloaded = False
        for url in urls:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": BROWSER_UA})
                with urllib.request.urlopen(req, timeout=180) as resp, \
                        open(target, "wb") as out:
                    while True:
                        chunk = resp.read(1 << 16)
                        if not chunk:
                            break
                        out.write(chunk)
                if target.stat().st_size == 0:
                    raise RuntimeError("fichero vacío")
                downloaded = True
                break
            except Exception as exc:  # noqa: BLE001
                last_error = (
                    f"{chosen.get('format')} / {name} / {url}: {exc}")
                target.unlink(missing_ok=True)
        if downloaded:
            return target.name, target.stat().st_size
        continue
    raise RuntimeError(last_error)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Descarga libros de archive.org para el corpus."
    )
    parser.add_argument("--out", default="corpus/docs")
    parser.add_argument("--manifest", default="corpus/docs/manifest.json")
    parser.add_argument("--max-size-mb", type=int, default=300)
    parser.add_argument("--only", default=None,
                        help="Filtra por familia (tarot, quiromancia, ...).")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    max_bytes = args.max_size_mb * 1024 * 1024
    out_root = Path(args.out)
    manifest_path = Path(args.manifest)
    manifest: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}

    items = [c for c in CURATED if not args.only or c[1] == args.only]
    print(f"{len(items)} documentos candidatos")

    for item_id, familia, licencia, nota in items:
        dest = out_root / familia / item_id
        print(f"\n[{familia}] {nota}\n  id={item_id}\n  licencia={licencia}")
        try:
            if args.dry_run:
                meta = _get_json(METADATA + urllib.parse.quote(item_id))
                info = meta.get("metadata", {}) or {}
                restricted = str(
                    info.get("access-restricted-item", "")
                ).lower() == "true"
                ranked = _rank_files(meta.get("files", []) or [])
                chosen = ranked[0] if ranked else None
                if restricted:
                    print("  -> RESTRINGIDO (se saltaría)")
                elif not chosen:
                    print("  -> sin PDF/EPUB")
                else:
                    size = int(chosen.get("size") or 0)
                    print(f"  -> {chosen.get('format')}: {chosen['name']} "
                          f"({size / 1e6:.1f} MB)")
                continue

            name, size = download(item_id, dest, max_bytes)
            manifest[item_id] = {
                "id": item_id,
                "familia": familia,
                "licencia": licencia,
                "nota": nota,
                "fuente": f"https://archive.org/details/{item_id}",
                "fichero": str((dest / name).relative_to(out_root)),
                "bytes": size,
                "estado": "ok",
            }
            print(f"  -> OK {name} ({size / 1e6:.1f} MB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  -> FALLO: {exc}")
            manifest[item_id] = {
                "id": item_id, "familia": familia, "licencia": licencia,
                "nota": nota, "fuente":
                    f"https://archive.org/details/{item_id}",
                "estado": "fallo", "error": str(exc),
            }
        finally:
            if not args.dry_run:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                time.sleep(args.delay)

    ok = sum(1 for v in manifest.values() if v.get("estado") == "ok")
    print(f"\nDocumentos descargados: {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
