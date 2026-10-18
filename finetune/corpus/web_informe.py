#!/usr/bin/env python3
"""Informe de cobertura por sitio y entidad (A3.5).

Lee manifest.jsonl y archivos .md por dominio y produce informe.md:
- Por sitio: descargadas, bloqueadas por robots/antibot, pausadas, cortas, chars medios
- Por faceta de la matriz: nº de entidades cubiertas y por cuántos sitios
- Entidades con < 3 sitios
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# YAML simple loader (evita dependencia PyYAML)
def _yaml_loader(text: str) -> Dict[str, Any]:
    """Carga YAML simple (solo key: value simples)."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ": " in line:
            k, v = line.split(": ", 1)
            k = k.strip()
            v = v.strip()
            # Quitar comillas
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'"):
                v = v[1:-1]
            # Convertir tipos
            if v.lower() == "null":
                v = None
            elif v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            elif v.isdigit():
                v = int(v)
            else:
                try:
                    v = float(v)
                except ValueError:
                    pass
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _cargar_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """Carga manifest.jsonl y devuelve lista de registros."""
    if not manifest_path.exists():
        return []
    registros = []
    with open(manifest_path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
                registros.append(reg)
            except json.JSONDecodeError:
                pass
    return registros


def _cargar_md_files(out_dir: Path) -> List[Dict[str, Any]]:
    """Carga todos los archivos .md de los subdirectorios de dominio."""
    md_files = []
    for md_path in out_dir.rglob("*.md"):
        try:
            contenido = md_path.read_text(encoding="utf-8")
            # Parsear front-matter YAML
            if contenido.startswith("---"):
                partes = contenido.split("---", 2)
                if len(partes) >= 3:
                    fm_text = partes[1]
                    fm = _yaml_loader(fm_text) or {}
                    fm["_archivo"] = str(md_path)
                    md_files.append(fm)
        except Exception:
            pass
    return md_files


def _entidad_id_de_fm(fm: Dict[str, Any]) -> Optional[str]:
    """Extrae entidad_id del front-matter."""
    return fm.get("entidad_id")


def _faceta_de_fm(fm: Dict[str, Any]) -> Optional[str]:
    """Extrae faceta del front-matter."""
    return fm.get("faceta")


def _familia_de_fm(fm: Dict[str, Any]) -> Optional[str]:
    """Extrae familia del front-matter."""
    return fm.get("familia")


def _dominio_de_fm(fm: Dict[str, Any]) -> Optional[str]:
    """Extrae dominio del front-matter."""
    return fm.get("dominio")


# ---------------------------------------------------------------------------
# Generación de informe
# ---------------------------------------------------------------------------

def generar_informe(
    manifest_path: Path,
    out_dir: Path,
    out_path: Path,
) -> Dict[str, Any]:
    """Genera informe.md y devuelve dict con estadísticas."""
    manifest = _cargar_manifest(manifest_path)
    md_files = _cargar_md_files(out_dir)

    # Estadísticas por sitio (desde manifest)
    stats_sitio = defaultdict(lambda: {
        "descargadas": 0, "bloqueadas_robots": 0, "bloqueadas_antibot": 0,
        "pausadas_429": 0, "error": 0, "cortas": 0, "chars_totales": 0,
        "archivos": 0,
    })

    for reg in manifest:
        estado = reg.get("estado", "error")
        sitio = reg.get("dominio", "desconocido")
        bytes_ = reg.get("bytes", 0)

        if estado == "ok":
            stats_sitio[sitio]["descargadas"] += 1
            stats_sitio[sitio]["chars_totales"] += bytes_
            stats_sitio[sitio]["archivos"] += 1
        elif estado == "bloqueada_robots":
            stats_sitio[sitio]["bloqueadas_robots"] += 1
        elif estado == "bloqueada_antibot":
            stats_sitio[sitio]["bloqueadas_antibot"] += 1
        elif estado == "pausado_429":
            stats_sitio[sitio]["pausadas_429"] += 1
        elif estado == "cortas" or (estado == "ok" and bytes_ > 0 and bytes_ < 1000):
            stats_sitio[sitio]["cortas"] += 1
        else:
            stats_sitio[sitio]["error"] += 1

    # Calcular chars medios por sitio
    for sitio, stats in stats_sitio.items():
        if stats["descargadas"] > 0:
            stats["chars_medios"] = round(stats["chars_totales"] / stats["descargadas"])
        else:
            stats["chars_medios"] = 0

    # Estadísticas por faceta y entidad (desde MD files)
    entidades_por_faceta = defaultdict(lambda: defaultdict(set))  # faceta -> entidad_id -> set(sitios)
    sitios_por_entidad = defaultdict(set)  # entidad_id -> set(sitios)
    faceta_de_entidad = {}  # entidad_id -> faceta
    familia_de_entidad = {}  # entidad_id -> familia

    for fm in md_files:
        entidad_id = _entidad_id_de_fm(fm)
        faceta = _faceta_de_fm(fm)
        familia = _familia_de_fm(fm)
        dominio = _dominio_de_fm(fm)

        if entidad_id:
            if faceta:
                entidades_por_faceta[faceta][entidad_id].add(dominio)
            sitios_por_entidad[entidad_id].add(dominio)
            if faceta:
                faceta_de_entidad[entidad_id] = faceta
            if familia:
                familia_de_entidad[entidad_id] = familia

    # Entidades con < 3 sitios
    entidades_pocas = [
        {"entidad_id": eid, "faceta": faceta_de_entidad.get(eid), "familia": familia_de_entidad.get(eid), "sitios": list(sitios)}
        for eid, sitios in sitios_por_entidad.items()
        if len(sitios) < 3
    ]

    # Cobertura por faceta
    cobertura_faceta = {}
    for faceta, entidades in entidades_por_faceta.items():
        total = len(entidades)
        con_multiples = sum(1 for sitios in entidades.values() if len(sitios) >= 3)
        cobertura_faceta[faceta] = {
            "entidades_totales": total,
            "con_3_o_mas_sitios": con_multiples,
            "cobertura_pct": round(con_multiples / total * 100, 1) if total > 0 else 0,
        }

    # Generar Markdown
    md_lines = [
        "# Informe de Cobertura Web (A3.5)",
        "",
        "## Resumen General",
        f"- Total sitios: {len(stats_sitio)}",
        f"- Total archivos MD: {len(md_files)}",
        f"- Total entidades únicas: {len(sitios_por_entidad)}",
        f"- Entidades con < 3 sitios: {len(entidades_pocas)}",
        "",
        "## Por Sitio",
    ]

    for sitio, stats in sorted(stats_sitio.items()):
        md_lines.append(f"### {sitio}")
        md_lines.append(f"- Descargadas OK: {stats['descargadas']}")
        md_lines.append(f"- Bloqueadas por robots.txt: {stats['bloqueadas_robots']}")
        md_lines.append(f"- Bloqueadas por antibot: {stats['bloqueadas_antibot']}")
        md_lines.append(f"- Pausadas (429): {stats['pausadas_429']}")
        md_lines.append(f"- Errores: {stats['error']}")
        md_lines.append(f"- Cortas (<1000 chars): {stats['cortas']}")
        md_lines.append(f"- Chars medios: {stats['chars_medios']}")
        md_lines.append(f"- Archivos: {stats['archivos']}")
        md_lines.append("")

    md_lines += [
        "## Cobertura por Faceta",
    ]

    for faceta, stats in sorted(cobertura_faceta.items()):
        md_lines.append(f"### {faceta}")
        md_lines.append(f"- Entidades totales: {stats['entidades_totales']}")
        md_lines.append(f"- Con ≥3 sitios: {stats['con_3_o_mas_sitios']}")
        md_lines.append(f"- Cobertura: {stats['cobertura_pct']}%")
        md_lines.append("")

    md_lines += [
        "## Entidades con < 3 sitios (requieren más fuentes)",
    ]

    if entidades_pocas:
        for e in sorted(entidades_pocas, key=lambda x: (x["faceta"] or "", x["entidad_id"])):
            md_lines.append(
                f"- **{e['entidad_id']}** ({e['faceta'] or '?'}, {e['familia'] or '?'}) "
                f"→ {len(e['sitios'])} sitios: {', '.join(sorted(e['sitios']))}"
            )
    else:
        md_lines.append("- (ninguna)")

    md_lines += [
        "",
        "## 5 Muestras Aleatorias para Revisión",
    ]

    # Seleccionar 5 muestras aleatorias de los MD files
    import random
    random.seed(42)
    muestras = random.sample(md_files, min(5, len(md_files))) if md_files else []
    for i, fm in enumerate(muestras, 1):
        md_lines.append(f"### {i}. {fm.get('entidad_id', '?')} ({fm.get('dominio', '?')})")
        md_lines.append(f"**Faceta:** {fm.get('faceta', '?')}")
        md_lines.append(f"**Familia:** {fm.get('familia', '?')}")
        md_lines.append(f"**Chars:** {fm.get('chars', 0)}")
        md_lines.append("")

    # Escribir archivo
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md_lines), encoding="utf-8")

    # JSON de salida para automatización
    resultado = {
        "stats_sitio": dict(stats_sitio),
        "cobertura_faceta": cobertura_faceta,
        "entidades_pocas": entidades_pocas,
        "total_md": len(md_files),
        "total_entidades": len(sitios_por_entidad),
    }
    return resultado


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Genera informe de cobertura (A3.5)")
    parser.add_argument("--manifest", required=True, help="Ruta a manifest.jsonl")
    parser.add_argument("--out-dir", required=True, help="Directorio con archivos .md por dominio")
    parser.add_argument("--out", required=True, help="Archivo de salida informe.md")
    args = parser.parse_args()

    res = generar_informe(Path(args.manifest), Path(args.out_dir), Path(args.out))
    print(f"Informe generado en {args.out}")
    print(f"Sitios: {len(res['stats_sitio'])} | MDs: {res['total_md']} | Entidades: {res['total_entidades']}")
    print(f"Entidades <3 sitios: {len(res['entidades_pocas'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
