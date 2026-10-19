#!/usr/bin/env python3
"""Orquestador del pipeline web en español (T25).

Descubre páginas desde los índices de ``knowledge/sitios_indice_es.json``,
las descarga con cortesía por dominio, extrae el contenido a Markdown,
registra cada URL en un manifest propio y genera el informe de cobertura.

Reanudable por URL: las entradas ya procesadas (ok/cortas) no se repiten.
Un sitio que falla no aborta el resto. Los foros tienen pausa mayor y tope
de hilos, y solo se visitan hilos públicos (nunca perfiles ni búsquedas).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from web_fetch import Cliente, USER_AGENT
from web_indices import cargar_config, seguir_indice
from web_extraer import extraer, guardar_markdown
from web_informe import generar_informe

CORTESIA_GENERAL = 1.2
CORTESIA_FORO = 2.5
MAX_HILOS_FORO = 40

RUTA_CONFIG_DEF = os.path.join(
    os.path.dirname(__file__), os.pardir, "knowledge", "sitios_indice_es.json"
)

_RUTA_PROHIBIDA = {
    "user", "users", "member", "members", "memberlist", "perfil", "profile",
    "search", "busqueda", "login", "logout", "admin", "modcp", "usercp",
    "private",
}


def normalizar_url(url: str) -> str:
    """Quita query y fragmento para deduplicar y descargar."""
    return url.split("?")[0].split("#")[0]


def es_hilo_publico(url: str) -> bool:
    """Descarta rutas de usuario, perfil, búsqueda o administración."""
    path = urlparse(url).path.lower()
    segmentos = [s for s in path.split("/") if s]
    return not any(s in _RUTA_PROHIBIDA for s in segmentos)


def intervalo_para_sitio(sitio_cfg: Dict[str, Any]) -> float:
    """Cortesía por dominio: los foros piden más pausa que los blogs."""
    return CORTESIA_FORO if sitio_cfg.get("tipo") == "foro" else CORTESIA_GENERAL


def slug_desde_url(url: str) -> str:
    """Slug seguro derivado del último segmento del path."""
    path = urlparse(url).path
    segmentos = [s for s in path.split("/") if s]
    ultimo = segmentos[-1] if segmentos else "pagina"
    ultimo = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", ultimo)
    slug = re.sub(r"[^a-z0-9_-]+", "-", ultimo.lower()).strip("-")
    return slug or "pagina"


def _cargar_procesadas(manifest_path: Path) -> Set[str]:
    """URLs ya terminadas (ok/cortas) para no repetir en relanzamientos."""
    procesadas: Set[str] = set()
    if not manifest_path.exists():
        return procesadas
    with open(manifest_path, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if reg.get("estado") in ("ok", "cortas"):
                procesadas.add(reg.get("url"))
    return procesadas


def procesar_sitio(
    sitio_cfg: Dict[str, Any],
    cliente,
    work_dir: str,
    limite: int,
    procesadas: Set[str],
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Descubre y (salvo dry-run) descarga/extrae las páginas de un sitio."""
    es_foro = sitio_cfg.get("tipo") == "foro"
    limite_efectivo = min(limite, MAX_HILOS_FORO) if es_foro else limite

    descubiertas = seguir_indice(sitio_cfg, cliente, limite=limite_efectivo)

    vistas: Set[str] = set()
    urls: List[str] = []
    for url in descubiertas:
        u = normalizar_url(url)
        if es_foro and not es_hilo_publico(u):
            continue
        if u not in vistas:
            vistas.add(u)
            urls.append(u)

    if dry_run:
        return [
            {"url": u, "sitio": sitio_cfg.get("nombre"), "dominio": sitio_cfg.get("dominio"),
             "familia": sitio_cfg.get("familia"), "estado": "descubierta",
             "chars": 0, "bytes": 0, "archivo": None}
            for u in urls
        ]

    registros: List[Dict[str, Any]] = []
    for url in urls:
        if url in procesadas:
            continue
        base = {
            "url": url,
            "sitio": sitio_cfg.get("nombre"),
            "dominio": sitio_cfg.get("dominio"),
            "familia": sitio_cfg.get("familia"),
        }
        try:
            resp = cliente.get(url)
        except Exception:  # noqa: BLE001 - un fallo de red no aborta el sitio
            registros.append({**base, "estado": "error", "chars": 0, "bytes": 0, "archivo": None})
            continue
        estado = resp.get("estado", "error")
        if estado != "ok":
            registros.append({**base, "estado": estado, "chars": 0,
                             "bytes": resp.get("bytes", 0), "archivo": None})
            continue
        try:
            extraccion = extraer(resp.get("html") or "", url, familia=sitio_cfg.get("familia"))
        except Exception:  # noqa: BLE001
            registros.append({**base, "estado": "error", "chars": 0,
                             "bytes": resp.get("bytes", 0), "archivo": None})
            continue
        if extraccion is None:
            registros.append({**base, "estado": "cortas", "chars": 0,
                             "bytes": resp.get("bytes", 0), "archivo": None})
            continue
        archivo = guardar_markdown(extraccion, Path(work_dir), slug_desde_url(url))
        registros.append({**base, "estado": "ok", "chars": extraccion.get("chars", 0),
                         "bytes": resp.get("bytes", 0), "archivo": str(archivo)})
    return registros


def ejecutar(
    config_path: str,
    work_dir: str,
    solo: Optional[List[str]] = None,
    limite_por_sitio: int = 50,
    dry_run: bool = False,
    fabrica_clientes: Optional[Callable[[float], Any]] = None,
) -> Dict[str, Any]:
    """Ejecuta el pipeline completo y devuelve un resumen."""
    if fabrica_clientes is None:
        fabrica_clientes = lambda mi: Cliente(user_agent=USER_AGENT, min_interval=mi)  # noqa: E731

    config = cargar_config(config_path)
    sitios = config.get("sitios", [])
    if solo:
        sitios = [s for s in sitios if s.get("nombre") in solo]

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    manifest_path = work / "manifest.jsonl"
    procesadas = _cargar_procesadas(manifest_path)

    resumen: Dict[str, Any] = {
        "total_descubiertas": 0,
        "total_ok": 0,
        "sitios_con_error": [],
        "sitios_sin_paginas": [],
    }

    for sitio in sitios:
        nombre = sitio.get("nombre", "?")
        try:
            cliente = fabrica_clientes(intervalo_para_sitio(sitio))
            registros = procesar_sitio(
                sitio, cliente, work_dir, limite_por_sitio, procesadas, dry_run
            )
        except Exception:  # noqa: BLE001 - un sitio caído no aborta los demás
            resumen["sitios_con_error"].append(nombre)
            continue
        if not registros:
            resumen["sitios_sin_paginas"].append(nombre)
        resumen["total_descubiertas"] += len(registros)
        resumen["total_ok"] += sum(1 for r in registros if r["estado"] == "ok")
        if registros and not dry_run:
            with open(manifest_path, "a", encoding="utf-8") as fh:
                for reg in registros:
                    fh.write(json.dumps(reg, ensure_ascii=False) + "\n")

    if not dry_run:
        resumen["informe"] = generar_informe(manifest_path, work, work / "informe.md")

    return resumen


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline web en español (T25)")
    parser.add_argument("--work-dir", required=True, help="Directorio de trabajo (manifest, md, informe)")
    parser.add_argument("--config", default=RUTA_CONFIG_DEF, help="Config de sitios índice (JSON)")
    parser.add_argument("--solo", default=None, help="Lista de nombres de sitio separados por comas")
    parser.add_argument("--limite-por-sitio", type=int, default=50, help="Máximo de páginas por sitio")
    parser.add_argument("--dry-run", action="store_true", help="Solo descubre, no descarga")
    args = parser.parse_args(argv)

    solo = [s.strip() for s in args.solo.split(",")] if args.solo else None
    resumen = ejecutar(
        args.config,
        args.work_dir,
        solo=solo,
        limite_por_sitio=args.limite_por_sitio,
        dry_run=args.dry_run,
    )
    print(f"Descubiertas: {resumen['total_descubiertas']} | OK: {resumen['total_ok']}")
    if resumen["sitios_con_error"]:
        print(f"Sitios con error: {', '.join(resumen['sitios_con_error'])}")
    if resumen["sitios_sin_paginas"]:
        print(f"Sitios sin páginas: {', '.join(resumen['sitios_sin_paginas'])}")
    if not args.dry_run:
        print(f"Informe: {Path(args.work_dir) / 'informe.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
