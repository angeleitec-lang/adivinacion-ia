#!/usr/bin/env python3
"""Fusiona el dataset ya traducido con los pares nuevos de Scrapy.

Reglas:
- `train_es.jsonl` es la version traducida de `train.jsonl` (mismas filas, en orden),
  asi que es la base autoritativa: NO se anade `train.jsonl` para no duplicar.
- Los pares nuevos salen de `train_scrapy.jsonl` / `val_scrapy.jsonl`.
- Se descarta cualquier par cuyo texto (turno gpt) ya exista en la base,
  comparando por hash del texto normalizado.
- Por defecto solo se conservan respuestas en espanol; usa --include-en para todo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from translate_dataset import detect_language


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def turn(row: dict, role: str) -> str:
    for t in row.get("conversations", []):
        if t.get("from") == role:
            return t.get("value", "")
    return ""


def answer(row: dict) -> str:
    return turn(row, "gpt")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def merge(base_rows: list[dict], new_rows: list[dict], include_en: bool) -> tuple[list[dict], dict]:
    seen: set[str] = set()
    out: list[dict] = []
    stats: dict = {"base": 0, "base_dup": 0, "new_added": 0, "new_dup": 0, "new_lang": 0, "new_empty": 0}
    langs = {"es": 0, "en": 0, "mixed": 0, "unknown": 0}

    for row in base_rows:
        text = answer(row)
        if not text:
            continue
        key = text_hash(text)
        if key in seen:
            stats["base_dup"] += 1
            continue
        seen.add(key)
        out.append(row)
        stats["base"] += 1
        langs[detect_language(text)] = langs.get(detect_language(text), 0) + 1

    for row in new_rows:
        text = answer(row)
        if not text:
            stats["new_empty"] += 1
            continue
        lang = detect_language(text)
        if not include_en and lang != "es":
            stats["new_lang"] += 1
            continue
        key = text_hash(text)
        if key in seen:
            stats["new_dup"] += 1
            continue
        seen.add(key)
        out.append(row)
        stats["new_added"] += 1
        langs[lang] = langs.get(lang, 0) + 1

    stats["total"] = len(out)
    stats["langs"] = langs
    return out, stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fusiona train_es.jsonl con los pares nuevos de Scrapy")
    parser.add_argument("--base", default="corpus/train_es.jsonl")
    parser.add_argument("--new", default="corpus/train_scrapy.jsonl")
    parser.add_argument("--out", default="corpus/train_final.jsonl")
    parser.add_argument("--val-base", default="corpus/val_es.jsonl")
    parser.add_argument("--val-new", default="corpus/val_scrapy.jsonl")
    parser.add_argument("--val-out", default="corpus/val_final.jsonl")
    parser.add_argument("--include-en", action="store_true", help="no filtrar por idioma")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    base = load_jsonl(Path(args.base))
    new = load_jsonl(Path(args.new))
    merged, stats = merge(base, new, args.include_en)
    print(f"base {args.base}: {len(base)} filas -> {stats['base']} utiles ({stats['base_dup']} duplicadas)")
    print(f"nuevos {args.new}: {len(new)} filas -> {stats['new_added']} anadidos, "
          f"{stats['new_dup']} duplicados, {stats['new_lang']} descartados por idioma, {stats['new_empty']} vacios")
    print(f"total fusionado: {stats['total']} pares; idiomas {stats['langs']}")
    if not args.dry_run:
        write_jsonl(Path(args.out), merged)
        print(f"escrito {args.out}")

    val_base = load_jsonl(Path(args.val_base))
    val_new = load_jsonl(Path(args.val_new))
    val_merged, val_stats = merge(val_base, val_new, args.include_en)
    print(f"val base {args.val_base}: {len(val_base)} -> {val_stats['base']} utiles")
    print(f"val nuevos {args.val_new}: {len(val_new)} -> {val_stats['new_added']} anadidos, "
          f"{val_stats['new_dup']} duplicados, {val_stats['new_lang']} descartados por idioma")
    print(f"val total: {val_stats['total']} pares; idiomas {val_stats['langs']}")
    if not args.dry_run:
        write_jsonl(Path(args.val_out), val_merged)
        print(f"escrito {args.val_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
