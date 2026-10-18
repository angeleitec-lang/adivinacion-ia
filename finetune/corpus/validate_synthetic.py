#!/usr/bin/env python3
"""Valida y deduplica los pares sintéticos generados (formato ShareGPT).

Puertas: idioma español, longitud, boilerplate, repetición, eco de la pregunta,
coherencia con los datos del prompt y duplicados exactos/casi exactos.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from translate_dataset import detect_language

JUNK = (
    "sacred-texts", "j.b. hare", "press the reload button", "botón recargar",
    "please enable javascript", "javascript enabled", "javascript habilitado",
    "for entertainment purposes only", "solo con fines de entretenimiento",
    "lorem ipsum", "cookie policy", "política de cookies",
)

CARD_RE = re.compile(r"Carta[s]?:\s*([^(\n]+?)\s*(?:\(|\.|$)", re.I)
SIGN_RE = re.compile(r"(?:Signo solar|Ascendente|Luna|Sol)\s*:?\s*(?:en\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", re.I)
NUM_RE = re.compile(r"(?:Camino de vida|Número|Destino|Alma|Personalidad|Año personal)\s*:?\s*(\d{1,2})", re.I)
QUESTION_RE = re.compile(r'Pregunta del consultante:\s*"([^"]+)"', re.I)


def words(text: str) -> list[str]:
    text = re.sub(r"[^\wáéíóúñü]+", " ", text.lower())
    return text.split()


def normalize(text: str) -> str:
    return " ".join(words(text))


def sha(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def near_key(text: str) -> tuple:
    w = words(text)
    if len(w) < 8:
        return tuple(w)
    picks = [w[int(len(w) * f)] for f in (0.1, 0.5, 0.9)]
    mids = [w[min(len(w) - 1, int(len(w) * f) + 1)] for f in (0.1, 0.5, 0.9)]
    return tuple(picks + mids)


def repetition_ratio(text: str, n: int = 12) -> float:
    w = words(text)
    if len(w) < n * 3:
        return 0.0
    grams = Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    top = grams.most_common(1)[0][1] if grams else 0
    return top / max(1, len(w) - n + 1)


def answer_of(row: dict) -> str:
    for c in row.get("conversations", []):
        if c.get("from") == "gpt":
            return c.get("value", "")
    return ""


def human_of(row: dict) -> str:
    for c in row.get("conversations", []):
        if c.get("from") == "human":
            return c.get("value", "")
    return ""


def grounding(prompt: str, answer: str) -> bool:
    low = answer.lower()
    checks = []
    for m in CARD_RE.finditer(prompt):
        name = m.group(1).strip().strip(".")
        if name and len(name) > 2:
            checks.append(name.lower())
    for m in SIGN_RE.finditer(prompt):
        checks.append(m.group(1).lower())
    for m in NUM_RE.finditer(prompt):
        checks.append(m.group(1))
    if not checks:
        return True
    return any(c in low for c in checks)


def validate(row: dict, args) -> tuple[bool, str]:
    answer = answer_of(row)
    prompt = human_of(row)
    if not answer or not prompt:
        return False, "sin_turnos"
    if len(answer) < args.min_chars:
        return False, "corto"
    if len(answer) > args.max_chars:
        return False, "largo"
    low = answer.lower()
    if any(m in low for m in JUNK):
        return False, "boilerplate"
    lang = detect_language(answer)
    if lang not in ("es", "mixed"):
        return False, f"idioma_{lang}"
    if repetition_ratio(answer) > args.max_repetition:
        return False, "repeticion"
    m = QUESTION_RE.search(prompt)
    if m:
        q = normalize(m.group(1))
        if len(q) > 25 and normalize(answer[:120]).startswith(q[:40]):
            return False, "eco_pregunta"
    if not grounding(prompt, answer):
        return False, "sin_datos_del_prompt"
    return True, "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Valida y deduplica pares sintéticos.")
    ap.add_argument("--dir", default="corpus/synthetic")
    ap.add_argument("--out", default="corpus/synthetic_clean.jsonl")
    ap.add_argument("--meta-out", default="corpus/synthetic_clean.meta.jsonl")
    ap.add_argument("--report", default="corpus/synthetic_report.json")
    ap.add_argument("--min-chars", type=int, default=400)
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--max-repetition", type=float, default=0.12)
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(str(Path(args.dir) / "*.jsonl")))
    if not paths:
        print(f"[validate] no hay ficheros en {args.dir}")
        return 1

    seen_hash: set[str] = set()
    seen_near: set[tuple] = set()
    meta: list[dict] = []
    reasons: Counter = Counter()
    per_block: dict[str, dict[str, int]] = {}
    kept = 0
    total = 0
    pairs_dup = 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for path in paths:
            block = Path(path).name.split(".")[0]
            stats = per_block.setdefault(block, {"total": 0, "ok": 0, "dup": 0, "bad": 0})
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    stats["total"] += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        stats["bad"] += 1
                        reasons["json_invalido"] += 1
                        continue
                    ok, why = validate(row, args)
                    if not ok:
                        stats["bad"] += 1
                        reasons[why] += 1
                        continue
                    answer = answer_of(row)
                    h = sha(answer)
                    if h in seen_hash:
                        stats["dup"] += 1
                        reasons["duplicado_exacto"] += 1
                        continue
                    k = near_key(answer)
                    if k in seen_near:
                        stats["dup"] += 1
                        pairs_dup += 1
                        reasons["duplicado_cercano"] += 1
                        continue
                    seen_hash.add(h)
                    seen_near.add(k)
                    stats["ok"] += 1
                    kept += 1
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    meta.append({"i": kept - 1, "block": block})

    Path(args.meta_out).write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in meta), encoding="utf-8"
    )
    report = {
        "total": total,
        "kept": kept,
        "rejected": total - kept,
        "near_duplicates": pairs_dup,
        "reasons": dict(reasons),
        "per_block": per_block,
        "output": str(out),
    }
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[validate] leídos {total} · válidos {kept} · descartados {total - kept}")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  - {k}: {v}")
    print(f"[validate] salida: {out}")
    for b, s in sorted(per_block.items()):
        print(f"  {b:18s} total={s['total']:5d} ok={s['ok']:5d} dup={s['dup']:4d} bad={s['bad']:4d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
