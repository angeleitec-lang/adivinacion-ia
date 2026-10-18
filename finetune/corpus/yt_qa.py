#!/usr/bin/env python3
"""Informe de calidad y cobertura (A4.7)."""

from __future__ import annotations

import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import local
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cartas


# ---------------------------------------------------------------------------
# Utilidades de análisis
# ---------------------------------------------------------------------------

def _cargar_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _contar_por_canal(pares: List[Dict]) -> Dict[str, int]:
    """Cuenta pares por canal (desde meta.canal o meta.video_id -> catalogo)."""
    # Para simplificar, usamos meta.canal si está disponible
    c = Counter()
    for p in pares:
        canal = p.get("meta", {}).get("canal", "desconocido")
        c[canal] += 1
    return dict(c)


def _contar_por_familia(pares: List[Dict]) -> Dict[str, int]:
    c = Counter()
    for p in pares:
        fam = p.get("meta", {}).get("familia") or p.get("meta", {}).get("tirada", "desconocida")
        c[fam] += 1
    return dict(c)


def _contar_por_tirada(pares: List[Dict]) -> Dict[str, int]:
    c = Counter()
    for p in pares:
        tirada = p.get("meta", {}).get("tirada", "desconocida")
        c[tirada] += 1
    return dict(c)


def _cobertura_cartas(pares: List[Dict]) -> Dict[str, int]:
    """Cuántas lecturas tocan cada una de las 78 cartas."""
    # Mapa nombre canónico -> índice
    nombre_a_idx = {c["nombre"]: i for i, c in enumerate(cartas.CARTAS_TAROT)}
    cobertura = {c["nombre"]: 0 for c in cartas.CARTAS_TAROT}

    for p in pares:
        for conv in p.get("conversations", []):
            if conv.get("from") == "gpt":
                texto = conv.get("value", "")
                # Buscar menciones de cartas en el texto
                for nombre, idx in nombre_a_idx.items():
                    if cartas.norm(nombre) in cartas.norm(texto):
                        cobertura[nombre] += 1
    return cobertura


def _reparto_embudo(catalogo: List, fetch: List, clasificacion: List, extraccion: List, normalizacion: List) -> Dict:
    """Estadísticas de embudo."""
    return {
        "catalogo_total": len(catalogo),
        "con_subtitulos_ok": sum(1 for f in fetch if f.get("estado") == "ok"),
        "clasificados_lectura": sum(1 for c in clasificacion if c.get("tipo") in ("lectura_individual", "lectura_ejemplo", "lectura_general_elige_carta")),
        "clasificados_conocimiento": sum(1 for c in clasificacion if c.get("tipo") == "curso_conocimiento"),
        "extraidos_validos": len(extraccion),
        "normalizados_ok": len(normalizacion),
    }


def _muestras_aleatorias(pares: List[Dict], n: int = 30) -> List[Dict]:
    """Selecciona n pares aleatorios para revisión humana."""
    if len(pares) <= n:
        return pares
    return random.sample(pares, n)


# ---------------------------------------------------------------------------
# Generación de informe
# ---------------------------------------------------------------------------

def generar_informe_qa(
    catalogo_path: Path,
    fetch_path: Path,
    clasificacion_path: Path,
    extraccion_path: Path,
    normalizacion_path: Path,
    out_dir: Path,
) -> Dict[str, Any]:
    """Genera qa.md y qa.json con el informe completo."""
    out_dir.mkdir(parents=True, exist_ok=True)

    catalogo = _cargar_jsonl(catalogo_path)
    fetch = _cargar_jsonl(fetch_path)
    clasificacion = _cargar_jsonl(clasificacion_path)
    extraccion = _cargar_jsonl(extraccion_path)
    normalizacion = _cargar_jsonl(normalizacion_path)

    # Métricas
    embudo = _reparto_embudo(catalogo, fetch, clasificacion, extraccion, normalizacion)
    por_canal = _contar_por_canal(normalizacion)
    por_familia = _contar_por_familia(normalizacion)
    por_tirada = _contar_por_tirada(normalizacion)
    cobertura = _cobertura_cartas(normalizacion)
    muestras = _muestras_aleatorias(normalizacion, n=30)

    # Alertas
    alertas = []
    total_pares = len(normalizacion)
    for canal, count in por_canal.items():
        if total_pares > 0 and count / total_pares > 0.03:
            alertas.append(f"Canal '{canal}' supera el 3% ({count}/{total_pares} = {count/total_pares*100:.1f}%)")

    cartas_bajas = [nombre for nombre, count in cobertura.items() if count < 10]
    if cartas_bajas:
        alertas.append(f"Cartas con <10 lecturas: {len(cartas_bajas)} ({', '.join(cartas_bajas[:10])}...)")

    # JSON de salida
    qa_json = {
        "embudo": embudo,
        "por_canal": por_canal,
        "por_familia": por_familia,
        "por_tirada": por_tirada,
        "cobertura_cartas": cobertura,
        "alertas": alertas,
        "muestras_revision": [
            {
                "video_id": p.get("meta", {}).get("video_id"),
                "canal": p.get("meta", {}).get("canal"),
                "tirada": p.get("meta", {}).get("tirada"),
                "prompt": next((c["value"] for c in p["conversations"] if c["from"] == "human"), "")[:200],
                "respuesta": next((c["value"] for c in p["conversations"] if c["from"] == "gpt"), "")[:300],
            }
            for p in muestras
        ],
    }

    # Markdown legible
    md_lines = [
        "# Informe de Calidad A4 (YouTube Subtítulos)",
        "",
        "## Embudo",
        f"- Catálogo total: {embudo['catalogo_total']}",
        f"- Con subtítulos OK: {embudo['con_subtitulos_ok']}",
        f"- Clasificados como lectura: {embudo['clasificados_lectura']}",
        f"- Clasificados como conocimiento: {embudo['clasificados_conocimiento']}",
        f"- Extracciones válidas: {embudo['extraidos_validos']}",
        f"- **Pares finales (OK): {embudo['normalizados_ok']}**",
        "",
        "## Reparto por canal (top 10)",
    ]
    for canal, count in sorted(por_canal.items(), key=lambda x: -x[1])[:10]:
        pct = count / total_pares * 100 if total_pares else 0
        md_lines.append(f"- {canal}: {count} ({pct:.1f}%)")

    md_lines += [
        "",
        "## Reparto por familia",
    ]
    for fam, count in sorted(por_familia.items(), key=lambda x: -x[1]):
        md_lines.append(f"- {fam}: {count}")

    md_lines += [
        "",
        "## Reparto por tirada",
    ]
    for tirada, count in sorted(por_tirada.items(), key=lambda x: -x[1]):
        md_lines.append(f"- {tirada}: {count}")

    md_lines += [
        "",
        "## Cobertura de cartas (78 tarot)",
    ]
    for nombre, count in sorted(cobertura.items(), key=lambda x: x[1]):
        flag = " ⚠️" if count < 10 else ""
        md_lines.append(f"- {nombre}: {count}{flag}")

    md_lines += [
        "",
        "## Alertas",
    ]
    if alertas:
        for a in alertas:
            md_lines.append(f"- ⚠️ {a}")
    else:
        md_lines.append("- Sin alertas")

    md_lines += [
        "",
        "## 30 Muestras para revisión humana",
    ]
    for i, m in enumerate(muestras, 1):
        md_lines.append(f"### {i}. {m.get('meta',{}).get('video_id','?')} ({m.get('meta',{}).get('canal','?')})")
        md_lines.append(f"**Tirada:** {m.get('meta',{}).get('tirada','?')}")
        md_lines.append(f"**Prompt:** {next((c['value'] for c in m['conversations'] if c['from']=='human'), '')[:200]}...")
        md_lines.append(f"**Respuesta:** {next((c['value'] for c in m['conversations'] if c['from']=='gpt'), '')[:300]}...")
        md_lines.append("")

    # Escribir archivos
    (out_dir / "qa.json").write_text(json.dumps(qa_json, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "qa.md").write_text("\n".join(md_lines), encoding="utf-8")

    return qa_json


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Genera informe QA (A4.7)")
    parser.add_argument("--catalogo", required=True)
    parser.add_argument("--fetch", required=True)
    parser.add_argument("--clasificacion", required=True)
    parser.add_argument("--extraccion", required=True)
    parser.add_argument("--normalizacion", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    qa = generar_informe_qa(
        Path(args.catalogo), Path(args.fetch), Path(args.clasificacion),
        Path(args.extraccion), Path(args.normalizacion), Path(args.out_dir)
    )

    print(f"Informe generado en {args.out_dir}/qa.md y qa.json")
    print(f"Pares totales: {qa['embudo']['normalizados_ok']}")
    print(f"Alertas: {len(qa['alertas'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
