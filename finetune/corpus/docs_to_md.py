#!/usr/bin/env python3
"""Extrae texto de los PDF/EPUB de corpus/docs con book-to-skill y lo deja
como markdown en corpus/raw/docs/<familia>/<slug>.md, listo para
`build_dataset.py`.

Por cada carpeta <familia>/<id>/ elige el mejor fichero (EPUB antes que PDF),
ejecuta el extractor en un workdir temporal, limpia el banner/SOURCE y, si el
documento tiene pocos encabezados ATX, inyecta secciones para que
build_dataset.py no descarte bloques demasiado largos.

Uso:
    .venv/bin/python corpus/docs_to_md.py
    .venv/bin/python corpus/docs_to_md.py --force --skip-large-mb 100
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DOC_EXTS = (".epub", ".pdf")
BANNER_RE = re.compile(r"(?m)^\s*={3,}\s*$")
SOURCE_RE = re.compile(r"(?m)^SOURCE:.*$")
HEADING_RE = re.compile(r"(?m)^#{1,6}\s+\S")


def pick_file(folder: Path, skip_large_mb: float) -> Path | None:
    candidates = [p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in DOC_EXTS]
    if not candidates:
        return None
    # EPUB primero (texto más limpio), luego el PDF más pequeño.
    candidates.sort(key=lambda p: (p.suffix.lower() != ".epub", p.stat().st_size))
    for path in candidates:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > skip_large_mb:
            print(f"    (omitido por tamaño: {path.name}, {size_mb:.0f} MB)")
            continue
        return path
    return None


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^0-9a-záéíóúñü]+", "_", text)
    return text.strip("_")[:80] or "documento"


def clean_text(raw: str) -> str:
    text = BANNER_RE.sub("", raw)
    text = SOURCE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def inject_sections(text: str, target: int = 2500) -> tuple[str, int]:
    blocks = re.split(r"\n\s*\n", text)
    out: list[str] = []
    buf: list[str] = []
    size = 0
    count = 0
    for block in blocks:
        buf.append(block)
        size += len(block) + 2
        if size >= target:
            count += 1
            out.append(f"## Sección {count}\n\n" + "\n\n".join(buf))
            buf, size = [], 0
    if buf:
        count += 1
        out.append(f"## Sección {count}\n\n" + "\n\n".join(buf))
    return "\n\n".join(out), count


def extract(path: Path, workdir: Path, timeout: int) -> str:
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["BOOK_SKILL_WORKDIR"] = str(workdir)
    cmd = [sys.executable, "-m", "book_to_skill", str(path),
           "--mode", "text", "--install-missing", "no"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True,
                            timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"extractor falló (rc={result.returncode}): "
            f"{(result.stderr or result.stdout)[-800:]}"
        )
    text_file = workdir / "full_text.txt"
    if not text_file.exists():
        raise RuntimeError("no se generó full_text.txt")
    return text_file.read_text(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", default="corpus/docs",
                        help="Raíz con <familia>/<id>/<fichero>.")
    parser.add_argument("--out", default="corpus/raw/docs",
                        help="Destino de los .md generados.")
    parser.add_argument("--skip-large-mb", type=float, default=100.0,
                        help="Omite ficheros mayores de N MB (manuscrito 1700).")
    parser.add_argument("--timeout", type=int, default=900,
                        help="Timeout por documento en segundos.")
    parser.add_argument("--force", action="store_true",
                        help="Re-extrae aunque el .md ya exista.")
    parser.add_argument("--only", default=None,
                        help="Procesa solo una familia (p.ej. tarot).")
    args = parser.parse_args(argv)

    docs_root = Path(args.docs)
    out_root = Path(args.out)
    if not docs_root.is_dir():
        print(f"ERROR: no existe {docs_root}")
        return 2

    ok = skipped = failed = 0
    families = sorted(p for p in docs_root.iterdir() if p.is_dir())
    for family_dir in families:
        family = family_dir.name
        if args.only and family != args.only:
            continue
        for item_dir in sorted(p for p in family_dir.iterdir() if p.is_dir()):
            item_id = item_dir.name
            slug = slugify(item_id)
            dest = out_root / family / f"{slug}.md"
            if dest.exists() and not args.force:
                print(f"  - {family}/{item_id}: ya existe, omitido")
                skipped += 1
                continue
            source = pick_file(item_dir, args.skip_large_mb)
            if source is None:
                print(f"  - {family}/{item_id}: sin documento utilizable")
                skipped += 1
                continue
            print(f"  + {family}/{item_id}: {source.name}")
            workdir = Path(tempfile.gettempdir()) / f"btk-{family}-{slug}"
            started = time.time()
            try:
                raw = extract(source, workdir, args.timeout)
            except Exception as exc:  # noqa: BLE001
                print(f"    ! fallo: {exc}")
                failed += 1
                continue
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

            text = clean_text(raw)
            headings = len(HEADING_RE.findall(text))
            threshold = max(5, len(text) // 8000)
            injected = 0
            if headings < threshold:
                text, injected = inject_sections(text)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text + "\n", encoding="utf-8")
            elapsed = time.time() - started
            print(
                f"    -> {dest} | {len(text):,} chars | "
                f"{headings} encabezados"
                + (f" | +{injected} inyectados" if injected else "")
                + f" | {elapsed:.1f}s"
            )
            ok += 1

    print(f"\nResumen: {ok} ok, {skipped} omitidos, {failed} fallos")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
