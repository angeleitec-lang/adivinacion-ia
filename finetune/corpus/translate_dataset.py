#!/usr/bin/env python3
"""Traduce al español las respuestas en inglés de train.jsonl / val.jsonl.

Usa la API OpenAI-compatible del nodo1 (halogen). Detecta el idioma de la
respuesta con una heurística de palabras funcionales y solo traduce las que
están en inglés (o mixtas con predominio inglés). Conserva el prompt humano
(ya está en español) y el formato Markdown.

Ejemplos:
    .venv/bin/python corpus/translate_dataset.py --dry-run
    .venv/bin/python corpus/translate_dataset.py --limit 5
    .venv/bin/python corpus/translate_dataset.py --workers 4
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_BASE_URL = "http://10.0.0.3:8000/v1"
DEFAULT_MODEL = "halogen-qwen3.8-flash-next"

ES_WORDS = {
    "el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una",
    "es", "por", "con", "para", "se", "su", "al", "como", "más", "pero",
    "sus", "le", "ya", "o", "fue", "este", "ha", "si", "porque", "esta",
    "son", "entre", "cuando", "muy", "sin", "sobre", "también", "me",
    "hasta", "hay", "donde", "quien", "desde", "todo", "nos", "durante",
    "todos", "uno", "les", "ni", "contra", "otros", "ese", "eso", "ante",
    "ellos", "esto", "antes", "algunos", "qué", "unos", "yo", "otro",
    "otras", "otra", "él", "tanto", "esa", "estos", "mucho", "quienes",
    "nada", "muchos", "cual", "poco", "ella", "estar", "estas", "algunas",
    "algo", "nosotros", "tiene", "tienen", "hace", "ser", "cada", "solo",
    "no",
}

EN_WORDS = {
    "the", "and", "of", "to", "in", "is", "that", "for", "it", "with",
    "as", "was", "on", "are", "be", "this", "have", "from", "or", "one",
    "had", "by", "but", "not", "what", "all", "were", "we", "when", "your",
    "can", "said", "there", "use", "an", "each", "which", "she", "do",
    "how", "their", "if", "will", "up", "other", "about", "out", "many",
    "then", "them", "these", "some", "her", "would", "make", "like",
    "him", "into", "time", "has", "look", "two", "more", "write", "go",
    "see", "number", "way", "could", "people", "my", "than", "first",
    "been", "call", "who", "its", "now", "find", "long", "down", "day",
    "did", "get", "come", "made", "may", "part", "should", "upon", "must",
    "such", "through", "only", "own", "same", "those", "which", "while",
}

SYSTEM_PROMPT = (
    "Eres un traductor profesional. Traduce el texto del inglés al español "
    "neutro. Conserva el formato Markdown (encabezados #, listas, tablas, "
    "cursivas) y los nombres propios. No añadas comentarios, notas ni "
    "explicaciones. Devuelve únicamente la traducción."
)

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def detect_language(text: str) -> str:
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if not words:
        return "unknown"
    es = sum(1 for w in words if w in ES_WORDS)
    en = sum(1 for w in words if w in EN_WORDS)
    total = max(1, es + en)
    if en > es and en / total >= 0.5:
        return "en"
    if es > en and es / total >= 0.5:
        return "es"
    return "mixed"


def _translate(text: str, base_url: str, model: str, retries: int = 4, timeout: int = 300) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    body = json.dumps(payload).encode("utf-8")
    url = base_url.rstrip("/") + "/chat/completions"
    last_error = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            last_error = str(exc)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"traducción fallida tras {retries} intentos: {last_error}")


def _load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _answer_of(row: dict) -> str:
    for turn in row.get("conversations", []):
        if turn.get("from") == "gpt":
            return turn.get("value", "")
    return ""


def _set_answer(row: dict, value: str) -> None:
    for turn in row.get("conversations", []):
        if turn.get("from") == "gpt":
            turn["value"] = value
            return


def _write_progress(path: Path, n: int) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(str(n), encoding="utf-8")
    tmp.replace(path)


def translate_file(src: Path, dst: Path, args) -> dict:
    rows = _load(src)
    if args.limit:
        rows = rows[: args.limit]

    progress = Path(str(dst) + ".progress")
    mode = "w"
    done = 0
    if args.resume and dst.exists():
        if progress.exists():
            try:
                done = int(progress.read_text(encoding="utf-8").strip() or 0)
            except ValueError:
                done = 0
        if not done:
            done = sum(1 for ln in dst.open(encoding="utf-8") if ln.strip())
        done = min(done, len(rows))
        rows = rows[done:]
        mode = "a"

    endpoints = getattr(args, "endpoints", None) or [
        (args.base_url, args.model)
    ]

    min_en = getattr(args, "min_en_chars", 0) or 0
    drop_short = getattr(args, "drop_short_en", False)

    def work(item) -> dict:
        idx, row, (ep_url, ep_model) = item
        answer = _answer_of(row)
        lang = detect_language(answer)
        if lang in ("en", "mixed"):
            if min_en and len(answer) < min_en:
                if drop_short:
                    return {"row": None, "lang": lang, "skipped": True,
                            "idx": idx}
                return {"row": row, "lang": lang, "translated": False,
                        "idx": idx}
            try:
                translated = _translate(answer, ep_url, ep_model, timeout=args.timeout)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! error traduciendo: {exc}", file=sys.stderr,
                      flush=True)
                return {"row": row, "lang": lang, "translated": False,
                        "error": True, "idx": idx}
            _set_answer(row, translated)
            return {"row": row, "lang": lang, "translated": True, "idx": idx}
        return {"row": row, "lang": lang, "translated": False, "idx": idx}

    pairs = [(done + i, row, endpoints[(done + i) % len(endpoints)])
             for i, row in enumerate(rows)]

    stats = {"total": 0, "translated": 0, "kept": 0, "error": 0, "dropped": 0}
    start = time.time()
    with dst.open(mode, encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, result in enumerate(pool.map(work, pairs), 1):
            stats["total"] += 1
            if result.get("skipped"):
                stats["dropped"] += 1
            else:
                if result.get("error"):
                    stats["error"] += 1
                elif result["translated"]:
                    stats["translated"] += 1
                else:
                    stats["kept"] += 1
                out.write(json.dumps(result["row"], ensure_ascii=False) + "\n")
                out.flush()
            _write_progress(progress, result["idx"] + 1)
            if i % 20 == 0 or i == len(rows):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed else 0
                eta = (len(rows) - i) / rate if rate else 0
                print(f"  {i}/{len(rows)}  trad={stats['translated']} "
                      f"keep={stats['kept']} drop={stats['dropped']} "
                      f"err={stats['error']}  "
                      f"{rate:.2f} filas/s  ETA {eta/60:.1f} min", flush=True)
    return stats


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Traduce respuestas EN→ES.")
    parser.add_argument("--train", default="corpus/train.jsonl")
    parser.add_argument("--val", default="corpus/val.jsonl")
    parser.add_argument("--out-train", default="corpus/train_es.jsonl")
    parser.add_argument("--out-val", default="corpus/val_es.jsonl")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", action="append", default=None,
                        help="url=model (repetible); reparte round-robin.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--min-en-chars", type=int, default=0,
                        help="No traduce respuestas EN/mixed mas cortas que esto.")
    parser.add_argument("--drop-short-en", action="store_true",
                        help="Descarta (en vez de conservar) los pares EN cortos.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo cuenta idiomas, sin traducir.")
    parser.add_argument("--only", choices=["train", "val"], default=None)
    args = parser.parse_args(argv)

    endpoints = []
    for spec in (args.endpoint or []):
        if "=" in spec:
            url, model = spec.split("=", 1)
        elif "|" in spec:
            url, model = spec.split("|", 1)
        else:
            url, model = spec, args.model
        endpoints.append((url.strip(), model.strip()))
    args.endpoints = endpoints or [(args.base_url, args.model)]

    targets = []
    if args.only != "val":
        targets.append((Path(args.train), Path(args.out_train)))
    if args.only != "train":
        targets.append((Path(args.val), Path(args.out_val)))

    if args.dry_run:
        for src, _ in targets:
            rows = _load(src)
            counts = {"es": 0, "en": 0, "mixed": 0, "unknown": 0}
            for row in rows:
                counts[detect_language(_answer_of(row))] += 1
            print(f"{src}: {len(rows)} pares  {counts}")
        return 0

    for src, dst in targets:
        if not src.exists():
            print(f"! no existe {src}", file=sys.stderr)
            continue
        print(f"\n== {src} -> {dst}")
        stats = translate_file(src, dst, args)
        print(f"   total={stats['total']} trad={stats['translated']} "
              f"keep={stats['kept']} err={stats['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
