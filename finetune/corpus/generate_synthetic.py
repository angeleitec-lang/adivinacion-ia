#!/usr/bin/env python3
"""Worker de generacion sintetica: reclama jobs de corpus/jobs.db y llama al LLM."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STOP = threading.Event()
ES_WORDS = {"que", "de", "la", "el", "en", "y", "los", "las", "un", "una", "para", "con",
            "por", "del", "al", "es", "su", "tu", "como", "más", "pero", "sin", "sobre"}


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def es_score(text):
    words = text.lower().replace(".", " ").replace(",", " ").split()
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in ES_WORDS)
    return hits / len(words)


def call_llm(base, model, system, user, max_tokens, timeout, retries=2):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.8,
        "top_p": 0.95,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload).encode("utf-8")
    last = None
    for intento in range(retries + 1):
        try:
            req = urllib.request.Request(
                base.rstrip("/") + "/chat/completions",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last = exc
            time.sleep(2 * (intento + 1))
    raise RuntimeError(f"fallo tras {retries + 1} intentos: {last}")


def resetear_stale(con, tag):
    """Reabre solo los running de este tag o los abandonados hace >2 horas.

    Así un worker nuevo no resetea los trabajos en curso de otros nodos.
    """
    con.execute(
        "UPDATE jobs SET status='pending' "
        "WHERE status='running' "
        "AND (worker LIKE ? OR updated_at < datetime('now','localtime','-2 hours'))",
        (tag + "%",),
    )
    con.commit()


def claim(con, worker, only=None):
    for intento in range(5):
        try:
            con.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError:
            if intento == 4:
                raise
            time.sleep(1)
    if only:
        row = con.execute(
            "SELECT id, bloque, system, prompt, max_tokens FROM jobs "
            "WHERE status='pending' AND bloque=? ORDER BY id LIMIT 1",
            (only,),
        ).fetchone()
    else:
        row = con.execute(
            "SELECT id, bloque, system, prompt, max_tokens FROM jobs "
            "WHERE status='pending' ORDER BY id LIMIT 1"
        ).fetchone()
    if row:
        con.execute(
            "UPDATE jobs SET status='running', worker=?, updated_at=? WHERE id=?",
            (worker, now(), row[0]),
        )
    con.commit()
    return row


def finish(con, job_id, ok, error=None):
    if ok:
        con.execute("UPDATE jobs SET status='done', updated_at=? WHERE id=?", (now(), job_id))
    else:
        con.execute(
            "UPDATE jobs SET status='pending', attempts=attempts+1, error=?, updated_at=? "
            "WHERE id=? AND attempts < 2",
            (error, now(), job_id),
        )
        con.execute(
            "UPDATE jobs SET status='failed', attempts=attempts+1, error=?, updated_at=? "
            "WHERE id=? AND status='running'",
            (error, now(), job_id),
        )
    con.commit()


def worker_loop(args, tag, stats, lock):
    con = sqlite3.connect(args.db, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    vacios = 0
    while not STOP.is_set():
        if args.limit:
            with lock:
                if stats["started"] >= args.limit:
                    break
        row = claim(con, tag, args.only)
        if not row:
            vacios += 1
            if vacios >= 3:
                break
            time.sleep(2)
            continue
        if args.limit:
            with lock:
                stats["started"] += 1
        vacios = 0
        job_id, bloque, system, prompt, max_tokens = row
        try:
            texto = call_llm(args.endpoint, args.model, system, prompt, max_tokens, args.timeout)
            if len(texto) < args.min_chars:
                raise RuntimeError(f"respuesta corta ({len(texto)} chars)")
            if es_score(texto) < 0.10:
                raise RuntimeError("respuesta no parece espanol")
            fila = {
                "job_id": job_id,
                "bloque": bloque,
                "endpoint": args.endpoint,
                "generated_at": now(),
                "conversations": [
                    {"from": "system", "value": system},
                    {"from": "human", "value": prompt},
                    {"from": "gpt", "value": texto},
                ],
            }
            dst = args.out / f"{bloque}.{tag}.jsonl"
            with open(dst, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            finish(con, job_id, True)
            with lock:
                stats["done"] += 1
                n = stats["done"] + stats["failed"]
                if n % 20 == 0:
                    el = time.time() - stats["t0"]
                    rate = n / el if el else 0
                    print(f"[{tag}] {n} ok={stats['done']} fail={stats['failed']} "
                          f"{rate:.2f} jobs/s", flush=True)
        except Exception as exc:
            finish(con, job_id, False, str(exc)[:300])
            with lock:
                stats["failed"] += 1
            print(f"[{tag}] job {job_id} ({bloque}) ERROR: {exc}", flush=True)
    con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera el dataset sintetico desde jobs.db.")
    ap.add_argument("--db", default=str(ROOT / "corpus" / "jobs.db"))
    ap.add_argument("--out", default=str(ROOT / "corpus" / "synthetic"))
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--model", default="halogen-qwen3.8-flash-next")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--min-chars", type=int, default=150)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    args.out = Path(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    tag = args.tag or f"w{os.getpid()}"

    con = sqlite3.connect(args.db, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    resetear_stale(con, tag)
    if args.only:
        total = con.execute("SELECT COUNT(*) FROM jobs WHERE status='pending' AND bloque=?", (args.only,)).fetchone()[0]
    else:
        total = con.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    con.commit()
    con.close()
    print(f"[{tag}] pendientes: {total} | endpoint {args.endpoint} | {args.workers} workers", flush=True)

    def on_sigint(signum, frame):
        print(f"[{tag}] deteniendo...", flush=True)
        STOP.set()

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    stats = {"done": 0, "failed": 0, "started": 0, "t0": time.time()}
    lock = threading.Lock()
    hilos = [threading.Thread(target=worker_loop, args=(args, tag, stats, lock), daemon=True)
             for _ in range(args.workers)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    print(f"[{tag}] fin: ok={stats['done']} fail={stats['failed']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
