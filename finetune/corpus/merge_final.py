#!/usr/bin/env python3
"""Fusiona pares reales y sintéticos, deduplica y genera split estratificado.

Salida: corpus/final/{train,val,test}.jsonl + report.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from translate_dataset import detect_language
from validate_synthetic import answer_of, human_of, sha, turnos_de
from build_dataset import BAD_TOPIC_RE, domain_hits


def extraer_tema(human: str) -> str:
    """Extrae el tema real del prompt, tolerando las plantillas de INSTRUCTION_TEMPLATES.

    Si hay «:» toma lo posterior; si coincide con una plantilla conocida
    («¿Qué significa X?», «Háblame de X.», «Explícame X de forma…», «…desarróllame X.»)
    toma X; si no puede extraer, devuelve la frase completa.
    """
    t = (human or "").strip()
    if ":" in t:
        t = t.split(":", 1)[1].strip()
    else:
        patrones = (
            r"^¿?Qu[eé]\s+significa\s+(.+?)\??$",
            r"^H[áa]blame\s+(?:del\s+|de\s+)(.+?)[.?]?$",
            r"^Expl[íi]came\s+(.+?)\s+de\s+forma\s+.+$",
            r"^.*desarr[oó]llame\s+(.+?)[.?]?$",
        )
        for pat in patrones:
            m = re.match(pat, t, re.IGNORECASE)
            if m:
                t = m.group(1)
                break
    return t.strip().rstrip(".?").strip()


def _pares_o_fallback(row: dict) -> list:
    """Todos los pares (human, gpt) de la fila; fallback al primer par si no hay turnos."""
    pares = turnos_de(row)
    if not pares:
        return [(human_of(row), answer_of(row))]
    return pares


def concat_respuestas(row: dict) -> str:
    """Concatenacion de todas las respuestas gpt, en orden."""
    return "\n".join(g for _, g in _pares_o_fallback(row))


def _par_es_junk(human: str, answer: str, min_terms: int) -> bool:
    if re.search(r"secci[oó]n\s*\d+|§\s*\d+", human, re.IGNORECASE):
        return True
    tema = extraer_tema(human)
    if len(tema) <= 2:
        return True
    for segmento in tema.split(" > "):
        if BAD_TOPIC_RE.search(segmento.strip()):
            return True
    if min_terms > 0 and len(domain_hits(human) | domain_hits(answer)) < min_terms:
        return True
    return False


def is_junk_pair(row: dict, min_terms: int = 2) -> bool:
    """Descarta prompts genericos: si CUALQUIER par de la fila es basura.

    Exencion D3 (T75): las filas del bloque `etica` no se juzgan por terminos
    de dominio. Su materia (duelo, menores, urgencias, salud) puede no citar
    tarot, astrologia ni numerologia y aun asi ser dato valido: el filtro de
    dominio esta pensado para el corpus tematico, no para los casos eticos,
    que ya se controlan en `validate_synthetic` (skips de eco/ia_meta) y en
    el verificador del ejecutor (promesas y juego vedados).
    """
    if str(row.get("bloque", "")) == "etica":
        min_terms = 0
    return any(_par_es_junk(h, a, min_terms) for h, a in _pares_o_fallback(row))


def load_jsonl(path: Path, estricto: bool = False, estadisticas=None) -> list[dict]:
    """Lee JSONL; por defecto descarta líneas corruptas, pero puede contarlas.

    `estricto=True` lanza ValueError al primer JSON inválido. Si se pasa
    `estadisticas`, se anotan las claves lineas/validas/descartadas.
    """
    if not path.exists():
        return []
    stats = estadisticas if estadisticas is not None else {}
    stats.setdefault("lineas", 0)
    stats.setdefault("validas", 0)
    stats.setdefault("descartadas", 0)
    rows = []
    with path.open(encoding="utf-8") as f:
        for num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            stats["lineas"] += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                stats["descartadas"] += 1
                if estricto:
                    raise ValueError(
                        f"{path}:{num}: JSON inválido ({exc.msg})") from exc
                continue
            if isinstance(row, dict):
                rows.append(row)
                stats["validas"] += 1
            else:
                stats["descartadas"] += 1
    return rows


def load_meta(path: Path) -> list[dict]:
    return load_jsonl(path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Escribe JSONL de forma atomica: un crash no trunca el destino."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def write_text_atomico(path: Path, texto: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, path)


def split_block(rows: list[dict], block: str, seed: int, r_train: float, r_val: float):
    """Reparte por GRUPOS del primer human: variantes de una misma pregunta no se separan.

    Cada grupo (mismo sha del primer human) va entero a un unico split, evitando
    fuga train/val/test entre follow-ups de una misma pregunta.
    """
    rng = random.Random(f"{seed}:{block}")
    grupos: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grupos[sha(human_of(r))].append(r)
    claves = sorted(grupos)
    rng.shuffle(claves)
    n = len(rows)
    n_train = int(n * r_train)
    n_val = int(n * r_val)
    train, val, test = [], [], []
    for k in claves:
        g = grupos[k]
        if len(train) < n_train:
            train += g
        elif len(train) + len(val) < n_train + n_val:
            val += g
        else:
            test += g
    return train, val, test


def lang_counts(rows: list[dict]) -> dict[str, int]:
    """Cuenta TODAS las respuestas gpt de cada fila, no solo la primera."""
    c = Counter()
    for r in rows:
        for _, g in _pares_o_fallback(r):
            c[detect_language(g)] += 1
    return dict(c)


def _norm(text: str) -> str:
    return unicodedata.normalize(
        "NFC", re.sub(r"\s+", " ", text or "").strip().lower())


def _clave_respuestas(row: dict) -> str:
    """sha de las respuestas con Unicode normalizado (NFC)."""
    return sha(unicodedata.normalize("NFC", concat_respuestas(row)))


def es_caso_de_evaluacion(fila: dict) -> bool:
    """True si la fila pertenece al conjunto reservado de evaluación (T56)."""
    if not isinstance(fila, dict):
        return False
    if fila.get("origen") == "evaluacion":
        return True
    return str(fila.get("id", "")).startswith("eval-")


def cargar_humanos_evaluacion(rutas) -> set[str]:
    """Humanos normalizados de los casos de evaluación, para excluirlos por contenido."""
    if isinstance(rutas, (str, Path)):
        rutas = [rutas]
    humanos: set[str] = set()
    for ruta in rutas or ():
        if not ruta:
            continue
        for fila in load_jsonl(Path(ruta)):
            if es_caso_de_evaluacion(fila):
                humanos.add(_norm(human_of(fila)))
    return humanos


def fusionar(real_train: list[dict], real_val: list[dict], synth: list[dict],
            meta: list[dict], cfg: dict) -> dict:
    """Fusiona reales y sintéticos: filtros, splits 50/50 del val real, dedupes y reporte.

    cfg: seed, train_ratio, val_ratio, include_en.
    Devuelve {"train", "val", "test", "report"}.
    """
    seed = cfg.get("seed", 42)
    r_train = cfg.get("train_ratio", 0.8)
    r_val = cfg.get("val_ratio", 0.1)
    include_en = cfg.get("include_en", False)
    descartes = {"junk": 0, "duplicado_exacto": 0, "duplicado_prefijo": 0,
                 "idioma": 0}

    humanos_eval = {_norm(h) for h in (cfg.get("eval_humanos") or ())}
    for r in list(real_train) + list(real_val) + list(synth):
        if es_caso_de_evaluacion(r):
            humanos_eval.add(_norm(human_of(r)))

    rt, rv = [], []
    for src, dst in ((real_train, rt), (real_val, rv)):
        for r in src:
            if es_caso_de_evaluacion(r) or _norm(human_of(r)) in humanos_eval:
                descartes["duplicado_exacto"] += 1
                continue
            if is_junk_pair(r):
                descartes["junk"] += 1
                continue
            if not include_en and any(
                    detect_language(g) != "es" for _, g in _pares_o_fallback(r)):
                descartes["idioma"] += 1
                continue
            dst.append(r)

    seen_real: set[str] = set()
    train_real, val_cands = [], []
    for r in rt:
        h = _clave_respuestas(r)
        if h in seen_real:
            descartes["duplicado_exacto"] += 1
            continue
        seen_real.add(h)
        train_real.append(r)
    humanos_train = {sha(human_of(r)) for r in train_real}
    for r in rv:
        h = _clave_respuestas(r)
        if h in seen_real:
            descartes["duplicado_exacto"] += 1
            continue
        if sha(human_of(r)) in humanos_train:
            descartes["duplicado_exacto"] += 1
            continue
        seen_real.add(h)
        val_cands.append(r)

    humanos_val = {sha(human_of(r)) for r in val_cands}
    by_block: dict[str, list[dict]] = defaultdict(list)
    dup_vs_real = 0
    seen_synth: set[str] = set()
    for r, m in zip(synth, meta):
        if es_caso_de_evaluacion(r) or _norm(human_of(r)) in humanos_eval:
            descartes["evaluacion"] += 1
            continue
        if sha(human_of(r)) in humanos_val:
            descartes["duplicado_exacto"] += 1
            continue
        h = _clave_respuestas(r)
        if h in seen_real:
            dup_vs_real += 1
            descartes["duplicado_exacto"] += 1
            continue
        if h in seen_synth:
            descartes["duplicado_exacto"] += 1
            continue
        seen_synth.add(h)
        by_block[m.get("block", "sintetico")].append(r)

    st, sv, ste = [], [], []
    for block, rows in sorted(by_block.items()):
        a, b, c = split_block(rows, block, seed, r_train, r_val)
        st += [(r, block) for r in a]
        sv += [(r, block) for r in b]
        ste += [(r, block) for r in c]

    val_real, test_real = [], []
    for r in val_cands:
        h = sha(human_of(r))
        (val_real if int(h, 16) % 2 == 0 else test_real).append(r)

    prefijos = {_norm(concat_respuestas(r))[:200] for r in train_real}
    prefijos.update(_norm(concat_respuestas(r))[:200] for r, _ in st)

    def sin_prefijo(rows: list[dict]) -> list[dict]:
        out = []
        for r in rows:
            if _norm(concat_respuestas(r))[:200] in prefijos:
                descartes["duplicado_prefijo"] += 1
                continue
            out.append(r)
        return out

    def sin_prefijo_tup(items: list[tuple]) -> list[tuple]:
        out = []
        for row, block in items:
            if _norm(concat_respuestas(row))[:200] in prefijos:
                descartes["duplicado_prefijo"] += 1
                continue
            out.append((row, block))
        return out

    val_real = sin_prefijo(val_real)
    test_real = sin_prefijo(test_real)
    sv = sin_prefijo_tup(sv)
    ste = sin_prefijo_tup(ste)

    train = train_real + [r for r, _ in st]
    val = val_real + [r for r, _ in sv]
    test = test_real + [r for r, _ in ste]
    random.Random(seed).shuffle(train)

    bps: dict[str, Counter] = {"train": Counter(), "val": Counter(), "test": Counter()}
    for r in train_real:
        bps["train"]["real"] += 1
    for _, b in st:
        bps["train"][b] += 1
    for r in val_real:
        bps["val"]["real"] += 1
    for _, b in sv:
        bps["val"][b] += 1
    for r in test_real:
        bps["test"]["real"] += 1
    for _, b in ste:
        bps["test"][b] += 1

    report = {
        "real_train_in": len(real_train),
        "real_val_in": len(real_val),
        "real_train_kept": len(train_real),
        "real_val_kept": len(val_real) + len(test_real),
        "synth_in": len(synth),
        "synth_dups_vs_real": dup_vs_real,
        "synth_kept": sum(len(v) for v in by_block.values()),
        "split": {"train": len(train), "val": len(val), "test": len(test)},
        "blocks": {k: len(v) for k, v in sorted(by_block.items())},
        "blocks_por_split": {k: dict(sorted(v.items())) for k, v in bps.items()},
        "descartes": descartes,
        "langs": {
            "train": lang_counts(train),
            "val": lang_counts(val),
            "test": lang_counts(test),
        },
    }
    return {"train": train, "val": val, "test": test, "report": report}


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
    ap.add_argument("--include-en", action="store_true",
                    help="conserva respuestas no españolas en los datos reales")
    ap.add_argument("--eval-casos", default=None,
                    help="JSONL del conjunto de evaluación (T56) a excluir por contenido")
    ap.add_argument("--strict", action="store_true",
                    help="aborta si alguna línea JSONL es inválida")
    args = ap.parse_args(argv)

    stats = {}
    real_train = load_jsonl(Path(args.real_train), args.strict, stats)
    real_val = load_jsonl(Path(args.real_val), args.strict, stats)
    synth = load_jsonl(Path(args.synth), args.strict, stats)
    meta = load_jsonl(Path(args.synth_meta), args.strict, stats)
    if stats.get("descartadas"):
        print(f"[merge] aviso: {stats['descartadas']} líneas JSONL descartadas")
    if len(meta) != len(synth):
        print(f"[merge] aviso: meta={len(meta)} synth={len(synth)}; se usa el mínimo")
        n = min(len(meta), len(synth))
        synth, meta = synth[:n], meta[:n]

    cfg = {
        "seed": args.seed,
        "train_ratio": args.train_ratio,
        "val_ratio": args.val_ratio,
        "include_en": args.include_en,
        "eval_humanos": cargar_humanos_evaluacion(args.eval_casos),
    }
    res = fusionar(real_train, real_val, synth, meta, cfg)
    train, val, test, report = res["train"], res["val"], res["test"], res["report"]

    out = Path(args.out_dir)
    write_jsonl(out / "train.jsonl", train)
    write_jsonl(out / "val.jsonl", val)
    write_jsonl(out / "test.jsonl", test)
    write_text_atomico(out / "report.json",
                       json.dumps(report, ensure_ascii=False, indent=2))

    d = report["descartes"]
    print(f"[merge] real train {report['real_train_in']}→{report['real_train_kept']} · "
          f"val {report['real_val_in']}→{report['real_val_kept']}")
    print(f"[merge] sintético {report['synth_in']} · dup con real {report['synth_dups_vs_real']} · "
          f"útil {report['synth_kept']}")
    print(f"[merge] descartes: junk={d['junk']} exacto={d['duplicado_exacto']} "
          f"prefijo={d['duplicado_prefijo']} idioma={d['idioma']}")
    print(f"[merge] split train={len(train)} val={len(val)} test={len(test)}")
    for k, v in sorted(report["blocks"].items()):
        print(f"  {k:18s} {v}")
    print(f"[merge] idiomas train: {report['langs']['train']}")
    print(f"[merge] salida: {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
