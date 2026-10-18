#!/usr/bin/env python3
"""Descubre URLs sobre adivinación usando Exa (MCP vía mcporter).

No usa LLM ni genera informes: solo lanza búsquedas, extrae las URLs de los
resultados y las deduplica. La salida alimenta `collect_corpus.py` (Firecrawl).

Uso:
    .venv/bin/python corpus/discover_urls.py
    .venv/bin/python corpus/discover_urls.py --topics tarot astrologia --num 10
    .venv/bin/python corpus/discover_urls.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

MCPORTER = "/Users/angelgonzalez/.local/bin/mcporter"

TOPICS: dict[str, list[str]] = {
    "tarot": [
        "significado de los 22 arcanos mayores del tarot uno por uno",
        "significado de los arcanos menores del tarot copas oros espadas bastos",
        "tiradas de tarot cruz celta posiciones e interpretación",
        "tirada de tres cartas pasado presente futuro tarot",
        "diferencias tarot de Marsella Rider Waite Smith Thoth",
        "cómo interpretar cartas invertidas en el tarot",
    ],
    "astrologia": [
        "carta natal interpretación planetas signos casas ascendente",
        "significado de las 12 casas astrológicas",
        "aspectos astrológicos conjunción sextil cuadratura trígono oposición",
        "significado de los planetas en astrología Sol Luna Mercurio Venus Marte",
        "tránsitos astrológicos y revolución solar",
        "sinastría compatibilidad de cartas natales",
    ],
    "numerologia": [
        "numerología significado de los números del 1 al 9",
        "cómo calcular el camino de vida numerología",
        "número del destino y número del alma numerología",
        "números maestros 11 22 33 numerología",
        "año personal numerología cálculo",
        "compatibilidad numerológica entre personas",
    ],
    "quiromancia": [
        "quiromancia líneas de la mano corazón cabeza vida destino",
        "significado de los montes de la mano quiromancia",
        "formas de la mano tierra aire fuego agua quiromancia",
        "líneas menores de la mano quiromancia sol mercurio",
        "cómo leer la palma de la mano paso a paso",
        "dedos y falanges quiromancia significado",
    ],
    "iching": [
        "I Ching 64 hexagramas significado",
        "cómo consultar el I Ching con monedas",
        "hexagrama 1 y 2 I Ching interpretación",
        "I Ching trigramas cielo tierra agua fuego",
        "método de las varillas I Ching",
    ],
    "runas": [
        "runas del Futhark antiguo 24 runas significado",
        "cómo hacer una tirada de runas",
        "significado de las runas Fehu Uruz Thurisaz Ansuz",
        "runas nórdicas adivinación interpretación",
        "Futhark joven y anglosajón diferencias",
    ],
    "lenormand": [
        "tarot Lenormand 36 cartas significado",
        "combinaciones de cartas Lenormand",
        "tiradas Lenormand Grand Tableau",
    ],
    "baraja-espanola": [
        "baraja española adivinación significado de las cartas",
        "oros copas espadas bastos significado adivinación",
        "tiradas con baraja española",
    ],
    "astrologia-china": [
        "astrología china 12 animales significado",
        "cinco elementos astrología china ciclo",
        "BaZi cuatro pilares cálculo",
    ],
    "astrologia-vedica": [
        "astrología védica Jyotish signos siderales",
        "nakshatras astrología védica significado",
        "casas y dashas Jyotish",
    ],
}

RECORD_RE = re.compile(
    r"Title:\s*(?P<title>.+?)\s*\n"
    r"URL:\s*(?P<url>\S+)\s*\n"
    r"(?:Published:\s*(?P<published>[^\n]*)\n)?"
    r"(?:Author:\s*(?P<author>[^\n]*)\n)?"
    r"Highlights:\s*\n(?P<highlights>.*?)"
    r"(?=\nTitle:|\Z)",
    re.DOTALL,
)


def _call_exa(query: str, num: int, objective: str) -> list[dict]:
    payload = json.dumps({
        "query": query,
        "numResults": num,
        "objective": objective,
    }, ensure_ascii=False)
    try:
        proc = subprocess.run(
            [MCPORTER, "call", "exa.web_search_exa",
             "--args", payload, "--output", "json"],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"  ! {query}: {exc}", file=sys.stderr)
        return []
    if proc.returncode != 0:
        print(f"  ! {query}: exit {proc.returncode} {proc.stderr[:200]}",
              file=sys.stderr)
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"  ! {query}: JSON inválido", file=sys.stderr)
        return []
    text = "\n".join(
        item.get("text", "") for item in data.get("content", [])
        if item.get("type") == "text"
    )
    records = []
    for match in RECORD_RE.finditer(text):
        url = match.group("url").strip()
        if not url.startswith("http"):
            continue
        records.append({
            "title": match.group("title").strip(),
            "url": url,
            "published": (match.group("published") or "").strip(),
            "author": (match.group("author") or "").strip(),
            "snippet": match.group("highlights").strip()[:600],
        })
    return records


def _normalize(url: str) -> str:
    url = url.split("#", 1)[0].rstrip("/")
    return url.lower()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Descubre URLs con Exa (sin LLM ni informes).")
    parser.add_argument("--topics", nargs="+", choices=sorted(TOPICS),
                        default=sorted(TOPICS))
    parser.add_argument("--num", type=int, default=15,
                        help="Resultados por query.")
    parser.add_argument("--out-urls", default="corpus/urls_research.txt")
    parser.add_argument("--out-sources", default="corpus/research_sources.jsonl")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Segundos entre queries.")
    parser.add_argument("--max-queries", type=int, default=0,
                        help="Tope global de queries (0 = sin tope).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    seen: set[str] = set()
    rows: list[dict] = []
    queries = 0
    for topic in args.topics:
        for query in TOPICS[topic]:
            if args.max_queries and queries >= args.max_queries:
                break
            queries += 1
            objective = (
                f"Encontrar páginas web en español con información detallada "
                f"y autoritativa sobre {topic}, para construir un corpus de "
                f"entrenamiento sobre adivinación."
            )
            print(f"[{queries}] {topic}: {query}", flush=True)
            if args.dry_run:
                continue
            records = _call_exa(query, args.num, objective)
            new = 0
            for record in records:
                key = _normalize(record["url"])
                if key in seen:
                    continue
                seen.add(key)
                record["topic"] = topic
                record["query"] = query
                rows.append(record)
                new += 1
            print(f"    +{new} nuevas ({len(rows)} total)", flush=True)
            time.sleep(args.delay)
        if args.max_queries and queries >= args.max_queries:
            break

    print(f"\nQueries: {queries}  URLs únicas: {len(rows)}")
    if args.dry_run:
        return 0

    urls_path = Path(args.out_urls)
    urls_path.parent.mkdir(parents=True, exist_ok=True)
    by_topic: dict[str, list[str]] = {}
    for row in rows:
        by_topic.setdefault(row["topic"], []).append(row["url"])
    lines = ["# URLs descubiertas con Exa (búsqueda web)",
             f"# total: {len(rows)}"]
    for topic in sorted(by_topic):
        lines.append(f"\n# {topic}")
        lines.extend(sorted(by_topic[topic]))
    urls_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sources_path = Path(args.out_sources)
    with sources_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Escrito: {urls_path}")
    print(f"Escrito: {sources_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
