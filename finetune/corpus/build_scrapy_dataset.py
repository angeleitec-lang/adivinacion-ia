#!/usr/bin/env python3
"""Construye pares ShareGPT desde corpus/raw_scrapy sin duplicar lo ya integrado.

Reutiliza la lógica de build_dataset.py (limpieza, split por encabezados,
plantillas y filtros) y descarta cualquier respuesta cuya huella ya exista en
train.jsonl, val.jsonl o train_es.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_dataset as bd
from translate_dataset import detect_language

FRONT_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)
HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.M)


def strip_front_matter(text: str) -> str:
    return FRONT_RE.sub("", text, count=1)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def pair_prompt(pair: dict) -> str:
    return next((t.get("value", "") for t in pair["conversations"]
                if t.get("from") == "human"), "")


def pair_answer(pair: dict) -> str:
    return next((t.get("value", "") for t in pair["conversations"]
                if t.get("from") == "gpt"), "")


def is_foreign_short(doc_lang: str, answer: str, min_len: int = 1200) -> bool:
    """Un par de documento no español con respuesta corta no aporta valor."""
    return doc_lang != "es" and len(answer) < min_len


def dedupe_new(pairs: list[dict], existing: set[str]) -> tuple[list[dict], int]:
    """Descarta pares por huella de respuesta o de prompt ya vistos."""
    kept: list[dict] = []
    seen_answers: set[str] = set()
    seen_prompts: set[str] = set()
    dup = 0
    for pair in pairs:
        ah = text_hash(pair_answer(pair))
        ph = text_hash(pair_prompt(pair))
        if ah in existing or ah in seen_answers or ph in seen_prompts:
            dup += 1
            continue
        seen_answers.add(ah)
        seen_prompts.add(ph)
        kept.append(pair)
    return kept, dup


def load_hashes(paths) -> set[str]:
    hashes: set[str] = set()
    for path in paths:
        path = Path(path)
        if not path.exists():
            print(f"[aviso] no existe {path}; se ignora")
            continue
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for turn in row.get("conversations", []):
                    if turn.get("from") == "gpt":
                        hashes.add(text_hash(turn.get("value", "")))
    return hashes


def needs_sections(md: str) -> bool:
    return len(HEADING_RE.findall(md)) < max(3, len(md) // 8000)


def inject_sections(text: str, target_chars: int = 2500) -> str:
    """Añade encabezados ATX cada ~target_chars si el documento no los tiene."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current, size = [], [], 0
    for para in paragraphs:
        current.append(para)
        size += len(para)
        if size >= target_chars:
            chunks.append("\n\n".join(current))
            current, size = [], 0
    if current:
        chunks.append("\n\n".join(current))
    if len(chunks) <= 1:
        return text
    return "\n\n".join(f"## Sección {i}\n\n{chunk}" for i, chunk in enumerate(chunks, 1))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default=str(HERE / "raw_scrapy"))
    parser.add_argument("--out", default=str(HERE))
    parser.add_argument(
        "--existing",
        nargs="*",
        default=[
            str(HERE / "train.jsonl"),
            str(HERE / "val.jsonl"),
            str(HERE / "train_es.jsonl"),
        ],
    )
    parser.add_argument("--ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--inject-chars", type=int, default=0,
                        help="Chars por sección inyectada (0 = no inyectar; "
                             "las secciones 'Sección N' generan pares basura)")
    parser.add_argument("--min-chars", type=int, default=200)
    parser.add_argument("--min-domain-terms", type=int, default=2,
                        help="Términos del dominio exigidos por par (0 desactiva)")
    parser.add_argument("--max-chars", type=int, default=4000)
    parser.add_argument(
        "--min-en-doc-chars",
        type=int,
        default=6000,
        help="descarta documentos no españoles mas cortos que esto (paginas web flojas)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    existing = load_hashes(args.existing)
    print(f"[info] huellas ya integradas: {len(existing)}")

    files = sorted(Path(args.raw).rglob("*.md"))
    print(f"[info] documentos en {args.raw}: {len(files)}")

    docs = []
    existing_all = set(existing)
    stats = {
        "docs_con_pares": 0,
        "pares": 0,
        "duplicados": 0,
        "inyectados": 0,
        "docs_en_cortos": 0,
        "pares_extranjeros_cortos": 0,
    }
    for path in files:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        md = strip_front_matter(raw)
        doc_lang = detect_language(md)
        if doc_lang != "es" and len(md) < args.min_en_doc_chars:
            stats["docs_en_cortos"] += 1
            continue
        if args.inject_chars > 0 and needs_sections(md):
            md = inject_sections(md, args.inject_chars)
            stats["inyectados"] += 1
        candidates = []
        for pair in bd.build_pairs(path.stem, md, rng, args.min_chars,
                                   args.max_chars, args.min_domain_terms):
            if is_foreign_short(doc_lang, pair_answer(pair)):
                stats["pares_extranjeros_cortos"] += 1
                continue
            candidates.append(pair)
        kept, dup = dedupe_new(candidates, existing_all)
        stats["duplicados"] += dup
        for pair in kept:
            existing_all.add(text_hash(pair_answer(pair)))
            existing_all.add(text_hash(pair_prompt(pair)))
        if kept:
            stats["docs_con_pares"] += 1
            stats["pares"] += len(kept)
            docs.append(kept)

    print(f"[info] documentos con pares: {stats['docs_con_pares']}")
    print(
        f"[info] pares nuevos: {stats['pares']} "
        f"(duplicados descartados: {stats['duplicados']}, "
        f"pares extranjeros cortos: {stats['pares_extranjeros_cortos']}, "
        f"docs con secciones inyectadas: {stats['inyectados']}, "
        f"docs no-ES cortos descartados: {stats['docs_en_cortos']})"
    )
    if not docs or args.dry_run:
        return 0

    rng.shuffle(docs)
    cutoff = max(1, int(len(docs) * args.ratio))
    train = [pair for group in docs[:cutoff] for pair in group]
    val = [pair for group in docs[cutoff:] for pair in group]

    langs: dict[str, int] = {}
    for pair in train + val:
        answer = next(
            (t["value"] for t in pair["conversations"] if t["from"] == "gpt"), ""
        )
        lang = detect_language(answer)
        langs[lang] = langs.get(lang, 0) + 1
    print(f"[info] idiomas de los pares nuevos: {langs}")

    out = Path(args.out)
    bd.write_jsonl(out / "train_scrapy.jsonl", train)
    bd.write_jsonl(out / "val_scrapy.jsonl", val)
    print(f"[ok] {len(train)} train + {len(val)} val -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
