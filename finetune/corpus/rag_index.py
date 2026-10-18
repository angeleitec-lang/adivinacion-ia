#!/usr/bin/env python3
"""Índice RAG sobre el corpus: chunk + embeddings (nomic-embed-text) + búsqueda por coseno.

Salida:
- corpus/rag/chunks.jsonl   (una línea por chunk: id, source, domain, text)
- corpus/rag/embeddings.npy (float32, L2-normalizados, una fila por chunk)

Uso:
  .venv/bin/python corpus/rag_index.py                 # construye el índice completo
  .venv/bin/python corpus/rag_index.py --limit 200     # índice reducido (prueba)
  .venv/bin/python corpus/rag_index.py --query "significado del Sol en la carta astral" --k 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAG_DIR = ROOT / "rag"
DEFAULT_DIRS = ["corpus/raw", "corpus/raw_scrapy"]

BOILERPLATE = (
    "whitelist", "enable javascript", "cookies", "suscríbete",
    "política de privacidad", "all rights reserved", "just a moment",
    "verifying you are human", "acceso denegado", "introduce tu email",
)
_LINK_RE = re.compile(r"https?://\S+|\[[^\]]*\]\([^)]*\)|[|#*_~^<>&=]")
DEFAULT_URL = "http://10.0.0.1:11434"
DEFAULT_MODEL = "nomic-embed-text"


def iter_md_files(dirs: list[str]) -> list[Path]:
    files: list[Path] = []
    for d in dirs:
        p = ROOT / d if not Path(d).is_absolute() else Path(d)
        if not p.exists():
            print(f"[!] directorio no encontrado: {p}")
            continue
        files.extend(sorted(p.rglob("*.md")))
    return files


def split_chunks(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    paras = [t.strip() for t in text.split("\n\n") if t.strip()]
    # une párrafos cortos para evitar trozos diminutos
    units: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 2 <= chunk_size:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            if buf:
                units.append(buf)
            buf = para
    if buf:
        units.append(buf)

    chunks: list[str] = []
    for u in units:
        if len(u) <= chunk_size:
            chunks.append(u)
        else:
            # partir unidades largas en ventanas solapadas
            start = 0
            while start < len(u):
                chunks.append(u[start:start + chunk_size])
                if start + chunk_size >= len(u):
                    break
                start += chunk_size - overlap
    return [c for c in chunks if len(c.strip()) >= 40]


def chunk_util(texto: str) -> bool:
    """Devuelve True si el chunk es útil; rechaza boilerplate, símbolos y texto insuficiente."""
    t = texto.strip()
    if len(t) < 80:
        return False
    bajo = t.lower()
    for frase in BOILERPLATE:
        if frase in bajo:
            return False
    letras = sum(1 for ch in t if ch.isalpha())
    if letras < 40:
        return False
    basura = sum(m.end() - m.start() for m in _LINK_RE.finditer(t))
    if basura > 0.6 * len(t):
        return False
    return True


def embed_uno(texto: str, url: str, model: str, reintentos: int = 3) -> list[float]:
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(
                f"{url.rstrip('/')}/api/embeddings",
                data=json.dumps({"model": model, "prompt": texto}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["embedding"]
        except Exception:
            if intento == reintentos - 1:
                raise
            time.sleep(0.5 * (2 ** intento))
    raise RuntimeError("no se debería llegar aquí")


def embed_paralelo(texts: list[str], fn, workers: int = 4) -> list[list[float]]:
    """Aplica fn (texto -> vector) a todos los textos conservando el orden de entrada."""
    if workers <= 1:
        return [fn(t) for t in texts]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, texts))


def embed_con_reudo(items: list[dict], fn, workers: int = 4,
                    partial_path: "Path | None" = None, resume: bool = False) -> dict:
    """Embebe items [{id, text}] en paralelo y los guarda en un fichero parcial reanudable."""
    hecho: dict = {}
    if resume and partial_path is not None and Path(partial_path).exists():
        for linea in Path(partial_path).read_text(encoding="utf-8").splitlines():
            if linea.strip():
                obj = json.loads(linea)
                hecho[obj["id"]] = obj["vec"]
    pendientes = [x for x in items if x["id"] not in hecho]
    if pendientes and partial_path is not None:
        Path(partial_path).parent.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futuros = {ex.submit(fn, x["text"]): x["id"] for x in pendientes}
            with open(partial_path, "a", encoding="utf-8") as fh:
                for fut in as_completed(futuros):
                    vec = fut.result()
                    cid = futuros[fut]
                    hecho[cid] = vec
                    fh.write(json.dumps({"id": cid, "vec": vec}) + "\n")
    return hecho


def embed(texts: list[str], url: str, model: str, workers: int = 4) -> list[list[float]]:
    return embed_paralelo(texts, lambda t: embed_uno(t, url, model), workers)


def _norm(mat: "np.ndarray") -> "np.ndarray":
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def build(args) -> int:
    files = iter_md_files(args.dirs)
    print(f"[i] {len(files)} ficheros .md")

    chunks: list[dict] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        domain = f.parent.name if f.parent.name != "docs" else f"docs/{f.parent.parent.name}"
        for c in split_chunks(text, args.chunk, args.overlap):
            cid = hashlib.sha256(c.encode("utf-8")).hexdigest()[:16]
            chunks.append({"id": cid, "source": str(f), "domain": domain, "text": c})
        if args.limit and len(chunks) >= args.limit:
            break

    # dedupe por hash de texto
    seen: set[str] = set()
    deduped: list[dict] = []
    for c in chunks:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        deduped.append(c)
    print(f"[i] {len(deduped)} chunks tras dedupe")

    # filtro de boilerplate antes de embeber
    utiles = [c for c in deduped if chunk_util(c["text"])]
    print(f"[i] {len(deduped) - len(utiles)} chunks descartados por boilerplate; "
          f"{len(utiles)} útiles")
    if not utiles:
        print("[!] ningún chunk útil; nada que indexar")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    partial = args.out / "embeddings.partial.jsonl"
    hecho = embed_con_reudo(utiles, lambda t: embed_uno(t, args.url, args.model),
                           workers=args.workers, partial_path=partial, resume=args.resume)
    vecs = [hecho[c["id"]] for c in utiles]
    mat = _norm(np.asarray(vecs, dtype=np.float32))

    (args.out / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in utiles) + "\n", encoding="utf-8")
    np.save(args.out / "embeddings.npy", mat)
    if partial.exists():
        partial.unlink()
    print(f"[ok] índice: {len(utiles)} chunks, {mat.shape[1]} dims -> {args.out}")
    return 0


def search(args) -> int:
    chunks_file = args.out / "chunks.jsonl"
    emb_file = args.out / "embeddings.npy"
    if not (chunks_file.exists() and emb_file.exists()):
        print("[!] no existe el índice; ejecuta sin --query primero")
        return 1
    chunks = [json.loads(l) for l in chunks_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    mat = np.load(emb_file)
    q = embed([args.query], args.url, args.model)[0]
    qv = np.asarray(q, dtype=np.float32)
    qv = qv / (np.linalg.norm(qv) or 1.0)
    scores = mat @ qv
    top = np.argsort(-scores)[: args.k]
    for i in top:
        print(f"--- {scores[i]:.3f} | {chunks[i]['domain']} | {chunks[i]['source']}")
        print(chunks[i]["text"][:400].replace("\n", " "))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", nargs="+", default=DEFAULT_DIRS)
    ap.add_argument("--out", type=Path, default=RAG_DIR)
    ap.add_argument("--chunk", type=int, default=900)
    ap.add_argument("--overlap", type=int, default=150)
    ap.add_argument("--limit", type=int, default=0, help="número máximo de chunks (prueba)")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--query", help="modo búsqueda (requiere índice existente)")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4, help="hilos de embeddings en paralelo")
    ap.add_argument("--resume", action="store_true", help="reanude desde el fichero parcial")
    args = ap.parse_args()
    return search(args) if args.query else build(args)


if __name__ == "__main__":
    raise SystemExit(main())
