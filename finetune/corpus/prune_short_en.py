#!/usr/bin/env python3
"""Purga pares y documentos en inglés cortos para no acumular basura.

- En datasets JSONL: descarta filas cuya respuesta no sea española y tenga
  menos de --min-pair-chars caracteres.
- En ficheros .md crudos: borra los documentos no españoles de menos de
  --min-raw-chars caracteres (los que build_scrapy_dataset descartaría igual).

NO toca train.jsonl/val.jsonl por defecto (la traducción en curso reanuda por
índice sobre ellos); usar --datasets para indicar los ficheros a podar.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from translate_dataset import detect_language

FRONT_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)


def strip_front(text: str) -> str:
    return FRONT_RE.sub("", text, count=1)


def answer_of(row: dict) -> str:
    for turn in row.get("conversations", []):
        if turn.get("from") == "gpt":
            return turn.get("value", "")
    return ""


def prune_dataset(path: Path, min_chars: int, dry: bool) -> tuple[int, int]:
    if not path.exists():
        print(f"[aviso] no existe {path}")
        return 0, 0
    rows = []
    dropped = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            answer = answer_of(row)
            if detect_language(answer) != "es" and len(answer) < min_chars:
                dropped += 1
                continue
            rows.append(row)
    if dropped and not dry:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        with path.open("w", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
    action = "dry" if dry else "ok"
    print(f"[{action}] {path.name}: {len(rows)} quedan, {dropped} EN cortos borrados")
    return len(rows), dropped


def prune_raw(root: Path, min_chars: int, dry: bool) -> tuple[int, int, int]:
    removed = 0
    freed = 0
    kept = 0
    for path in sorted(root.rglob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        md = strip_front(raw)
        if detect_language(md) != "es" and len(md) < min_chars:
            size = path.stat().st_size
            if not dry:
                path.unlink()
            removed += 1
            freed += size
        else:
            kept += 1
    action = "dry" if dry else "ok"
    print(
        f"[{action}] raw {root}: {kept} quedan, {removed} borrados "
        f"({freed / 1_000_000:.2f} MB)"
    )
    return kept, removed, freed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=str(HERE / "raw_scrapy"))
    parser.add_argument("--min-raw-chars", type=int, default=6000)
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=[str(HERE / "train_scrapy.jsonl"), str(HERE / "val_scrapy.jsonl")],
    )
    parser.add_argument("--min-pair-chars", type=int, default=1200)
    parser.add_argument("--skip-raw", action="store_true")
    parser.add_argument("--skip-datasets", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.skip_datasets:
        for path in args.datasets:
            prune_dataset(Path(path), args.min_pair_chars, args.dry_run)

    if not args.skip_raw:
        prune_raw(Path(args.raw), args.min_raw_chars, args.dry_run)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
