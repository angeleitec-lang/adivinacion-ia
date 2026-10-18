#!/usr/bin/env python3
"""Fusiona pares reales y sintéticos, deduplica y genera split estratificado.

Salida: corpus/final/{train,val,test}.jsonl + report.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from translate_dataset import detect_language
from validate_synthetic import answer_of, sha
from build_dataset import BAD_TOPIC_RE, domain_hits


def is_junk_pair(row: dict, min_terms: int = 2) -> bool:
    """Descarta prompts genéricos de secciones inyectadas o sin anclaje."""
    human = ""
    for t in row.get("conversations", []):
        if t.get("from") == "human":
            human = t.get("value", "")
            break
    answer = answer_of(row)
    if re.search(r"secci[oó]n\s*\d+|§\s*\d+", human, re.IGNORECASE):
        return True
    if BAD_TOPIC_RE.search(human):
        return True
    if min_terms > 0 and len(domain_hits(human) | domain_hits(answer)) < min_terms:
        return True
    return False


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def load_meta(path: Path) -> list[dict]:
    return load_jsonl(path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def split_block(rows: list[dict], block: str, seed: int, r_train: float, r_val: float):
    rng = random.Random(f"{seed}:{block}")
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    n = len(idx)
    n_train = int(n * r_train)
    n_val = int(n * r_val)
    train = [rows[i] for i in idx[:n_train]]
    val = [rows[i] for i in idx[n_train:n_train + n_val]]
    test = [rows[i] for i in idx[n_train + n_val:]]
    return train, val, test


def lang_counts(rows: list[dict]) -> dict[str, int]:
    c = Counter()
    for r in rows:
        c[detect_language(answer_of(r))] += 1
    return dict(c)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fusiona real + sintético y genera splits.")
    ap.add_argument("--real-train", default="corpus/train_final.jsonl")
    ap.add_argument("--real-val", default="corpus/val_final.jsonl")
    ap.add_argument("--synth", default="corpus/synthetic_clean.jsonl")
    ap.add_argument("--synth-meta", default="corpus/synthetic_clean.meta.jsonl")
    ap.add_argument("--out-dir", default="corpus/final")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train-ratio", type=float, default=0.8)
    ap.add_argument("--val-ratio", type=float, default=0.1)
    args = ap.parse_args(argv)

    real_train = load_jsonl(Path(args.real_train))
    real_val = load_jsonl(Path(args.real_val))
    synth = load_jsonl(Path(args.synth))
    meta = load_meta(Path(args.synth_meta))
    if len(meta) != len(synth):
        print(f"[merge] aviso: meta={len(meta)} synth={len(synth)}; se usa el mínimo")
        n = min(len(meta), len(synth))
        synth, meta = synth[:n], meta[:n]

    real_train = [r for r in real_train if not is_junk_pair(r)]
    real_val = [r for r in real_val if not is_junk_pair(r)]

    seen: set[str] = set()
    dedup_real_train, dedup_real_val = [], []
    for r in real_train:
        h = sha(answer_of(r))
        if h not in seen:
            seen.add(h)
            dedup_real_train.append(r)
    for r in real_val:
        h = sha(answer_of(r))
        if h not in seen:
            seen.add(h)
            dedup_real_val.append(r)

    by_block: dict[str, list[dict]] = defaultdict(list)
    dup_synth = 0
    for r, m in zip(synth, meta):
        h = sha(answer_of(r))
        if h in seen:
            dup_synth += 1
            continue
        seen.add(h)
        by_block[m.get("block", "sintetico")].append(r)

    st, sv, ste = [], [], []
    for block, rows in sorted(by_block.items()):
        a, b, c = split_block(rows, block, args.seed, args.train_ratio, args.val_ratio)
        st += a
        sv += b
        ste += c

    train = dedup_real_train + st
    val = dedup_real_val + sv
    test = ste
    random.Random(args.seed).shuffle(train)

    out = Path(args.out_dir)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "val.jsonl", val)
    write_jsonl(out / "test.jsonl", test)

    report = {
        "real_train_in": len(real_train),
        "real_val_in": len(real_val),
        "real_train_kept": len(dedup_real_train),
        "real_val_kept": len(dedup_real_val),
        "synth_in": len(synth),
        "synth_dups_vs_real": dup_synth,
        "synth_kept": sum(len(v) for v in by_block.values()),
        "split": {"train": len(train), "val": len(val), "test": len(test)},
        "blocks": {k: len(v) for k, v in sorted(by_block.items())},
        "langs": {
            "train": lang_counts(train),
            "val": lang_counts(val),
            "test": lang_counts(test),
        },
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[merge] real train {len(real_train)}→{len(dedup_real_train)} · val {len(real_val)}→{len(dedup_real_val)}")
    print(f"[merge] sintético {len(synth)} · dup con real {dup_synth} · útil {report['synth_kept']}")
    print(f"[merge] split train={len(train)} val={len(val)} test={len(test)}")
    for k, v in sorted(by_block.items()):
        print(f"  {k:18s} {len(v)}")
    print(f"[merge] idiomas train: {report['langs']['train']}")
    print(f"[merge] salida: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
