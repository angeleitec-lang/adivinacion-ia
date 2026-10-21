#!/usr/bin/env python3
"""Recuperación dirigida 2.ª iteración: descarga de URLs candidatas del plan (T64).

Toma las URLs candidatas de ``plan_recuperacion.jsonl`` (patrones de sitios ya
validados en ``knowledge/sitios_indice_es.json``), las filtra contra lo ya
descargado (manifest y hashes de contenido de ``web/``), prioriza baraja
española y numerología y descarga las páginas con la tubería existente
(robots.txt, cortesía por dominio, extracción a Markdown) hacia un directorio
NUEVO ``web_recup2/``. No fusiona nada con ``web/`` ni con las evidencias y
no consume LLM.

Reanudable: las URLs ya terminadas (ok/cortas/duplicada_hash) no se repiten.
Cada intento queda registrado en ``web_recup2/manifest.jsonl`` con su estado
(ok, cortas, duplicada_hash, error, bloqueada_robots, bloqueado_antibot,
pausado_429). El tope de páginas por dominio y el total de la tanda son
configurables.

Los dominios con bloqueo conocido (astro.com, nymero.org, Reddit) no se
intentan ni descubrir: nunca se salta un bloqueo.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from web_fetch import Cliente, USER_AGENT
from web_indices import cargar_config, seguir_indice
from web_extraer import extraer, guardar_markdown
from web_pipeline import (
    es_hilo_publico,
    intervalo_para_sitio,
    normalizar_url,
    slug_desde_url,
)
from recuperacion_dirigida import familia_de

RUTA_PLAN_DEF = "/Users/angelgonzalez/fase0/plan_recuperacion.jsonl"
RUTA_MANIFEST_PREVIO_DEF = "/Users/angelgonzalez/fase0/web/manifest.jsonl"
RUTA_WEB_PREVIA_DEF = "/Users/angelgonzalez/fase0/web"
RUTA_CONFIG_INDICES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, "knowledge", "sitios_indice_es.json",
)
RUTA_OUT_DEF = "/Users/angelgonzalez/fase0/web_recup2"
RUTA_MATRIZ_DEF = "/Users/angelgonzalez/fase0/cobertura_total_v2.json"

PRIORIDAD_FAMILIAS = ("baraja_espanola", "numerologia")

# Dominios con bloqueo declarado en el proyecto: no se descubren ni descargan.
DOMINIOS_BLOQUEADOS = frozenset({"astro.com", "nymero.org", "reddit.com"})

# Estados que dan una URL por terminada (no se reintenta al reanudar).
ESTADOS_TERMINALES = ("ok", "cortas", "duplicada_hash")

_SHA_FRONT_RE = re.compile(r"^sha256:\s*([0-9a-f]{64})\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Carga de entradas
# ---------------------------------------------------------------------------

def cargar_plan(ruta: str) -> list:
    """Lee el plan JSONL de recuperación (una entrada por entidad).

    Las líneas corruptas o truncadas se saltan para no tumbar el run por una
    escritura interrumpida.
    """
    plan = []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                plan.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return plan


def _norm_dominio(netloc: str) -> str:
    return netloc[4:] if netloc.startswith("www.") else netloc


def esta_bloqueado(dominio: str, bloqueados=DOMINIOS_BLOQUEADOS) -> bool:
    """True si el dominio (o un subdominio suyo) está en la lista bloqueada."""
    return any(dominio == b or dominio.endswith("." + b) for b in bloqueados)


def candidatas_por_familia(plan: list) -> dict:
    """URLs candidatas del plan agrupadas por familia, en orden de aparición."""
    out: dict = {}
    for entrada in plan:
        familia = entrada.get("familia") or familia_de(entrada.get("entidad_id"))
        for c in entrada.get("urls_candidatas", []):
            url = c.get("url") if isinstance(c, dict) else c
            if not url:
                continue
            lista = out.setdefault(familia, [])
            if url not in lista:
                lista.append(url)
    return out


def orden_familias(familias, prioritarias=PRIORIDAD_FAMILIAS) -> list:
    """Familias prioritarias primero; el resto, ordenadas alfabéticamente."""
    prim = [f for f in prioritarias if f in familias]
    resto = sorted(f for f in familias if f is not None and f not in prioritarias)
    return prim + resto


def config_por_dominio(config: dict) -> dict:
    """Mapa dominio_normal -> sitio de la config de índices validados."""
    mapa = {}
    for sitio in config.get("sitios", []):
        dominio = _norm_dominio(str(sitio.get("dominio", "")))
        if dominio and dominio not in mapa:
            mapa[dominio] = sitio
    return mapa


def construir_sitios(candidatas: dict, configs: dict,
                     bloqueados=DOMINIOS_BLOQUEADOS,
                     prioritarias=PRIORIDAD_FAMILIAS) -> list:
    """Sitios sintéticos de descarga: un dominio agrupa sus URLs candidatas.

    Se descartan las candidatas cuyo dominio no está en la config validada o
    está en la lista de bloqueados. El orden respeta la prioridad de familias
    y, dentro de cada familia, el orden de aparición en el plan.
    """
    grupos: dict = {}
    orden: list = []
    for familia in orden_familias(candidatas.keys(), prioritarias):
        for url in candidatas[familia]:
            dominio = _norm_dominio(urlparse(url).netloc)
            if esta_bloqueado(dominio, bloqueados):
                continue
            cfg = configs.get(dominio)
            if cfg is None:
                continue
            clave = (familia, dominio)
            if clave not in grupos:
                grupos[clave] = []
                orden.append(clave)
            if url not in grupos[clave]:
                grupos[clave].append(url)
    sitios = []
    for (familia, dominio) in orden:
        cfg = configs[dominio]
        sitios.append({
            "nombre": cfg.get("nombre", dominio),
            "dominio": cfg.get("dominio", dominio),
            "indice": grupos[(familia, dominio)],
            "regex": cfg["regex"],
            "tipo": cfg.get("tipo", "blog"),
            "familia": familia,
        })
    return sitios


def construir_tareas(candidatas: dict, configs: dict,
                    bloqueados=DOMINIOS_BLOQUEADOS,
                    prioritarias=PRIORIDAD_FAMILIAS) -> list:
    """Tareas de descarga ordenadas por familia prioritaria.

    Dentro de cada familia, primero los sitios de índice validados (se descubre
    con ``seguir_indice`` usando el índice completo del config) y después las
    candidatas de página directa (dominios que no están en la config de índices,
    p. ej. las fichas de tarot en inglés del plan: se descarga la URL tal cual).
    """
    tareas: list = []
    vistos_indice: set = set()
    vistos_directa: set = set()
    for familia in orden_familias(candidatas.keys(), prioritarias):
        directas: list = []
        for url in candidatas[familia]:
            dominio = _norm_dominio(urlparse(url).netloc)
            if esta_bloqueado(dominio, bloqueados):
                continue
            cfg = configs.get(dominio)
            if cfg is not None:
                clave = (familia, dominio)
                if clave in vistos_indice:
                    continue
                vistos_indice.add(clave)
                tareas.append({"tipo": "indice", "familia": familia,
                             "dominio": dominio, "sitio_cfg": cfg})
            else:
                if url in vistos_directa:
                    continue
                vistos_directa.add(url)
                directas.append((url, dominio))
        for url, dominio in directas:
            tareas.append({"tipo": "directa", "familia": familia,
                         "dominio": dominio, "url": url})
    return tareas


# ---------------------------------------------------------------------------
# Filtros contra lo ya descargado
# ---------------------------------------------------------------------------

def cargar_urls_previas(manifest_path: str, estados=ESTADOS_TERMINALES) -> set:
    """URLs normalizadas ya terminadas en un manifest (para no repetir)."""
    urls: set = set()
    if not manifest_path or not os.path.exists(manifest_path):
        return urls
    with open(manifest_path, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if not isinstance(reg, dict):
                continue
            if reg.get("estado") in estados and reg.get("url"):
                urls.add(normalizar_url(reg["url"]))
    return urls


def cargar_hashes_previos(web_dir: str) -> set:
    """sha256 del front-matter de los Markdown ya guardados en ``web_dir``."""
    hashes: set = set()
    if not web_dir or not os.path.isdir(web_dir):
        return hashes
    for raiz, _dirs, archivos in os.walk(web_dir):
        for nombre in archivos:
            if not nombre.endswith(".md"):
                continue
            try:
                with open(os.path.join(raiz, nombre), encoding="utf-8",
                         errors="replace") as fh:
                    cabecera = fh.read(2048)
            except OSError:
                continue
            m = _SHA_FRONT_RE.search(cabecera)
            if m:
                hashes.add(m.group(1))
    return hashes


def hashes_del_manifest(manifest_path: str) -> set:
    """sha256 registrados como ok en un manifest propio."""
    hashes: set = set()
    if not manifest_path or not os.path.exists(manifest_path):
        return hashes
    with open(manifest_path, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(reg, dict) and reg.get("estado") == "ok" and reg.get("hash"):
                hashes.add(reg["hash"])
    return hashes


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------

def _append_registro(manifest_path: str, reg: dict) -> None:
    with open(manifest_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(reg, ensure_ascii=False) + "\n")


def _fabrica_clientes_def(intervalo: float) -> Cliente:
    return Cliente(user_agent=USER_AGENT, min_interval=intervalo)


def _detalle_de(resumen: dict, familia: str, dominio: str, sitio_nombre: str) -> dict:
    clave = f"{familia}|{dominio}"
    return resumen["por_dominio"].setdefault(
        clave, {"familia": familia, "dominio": dominio, "sitio": sitio_nombre,
               "intentos": 0, "ok": 0, "cortas": 0,
               "duplicada_hash": 0, "error": 0})


def _acumular(resumen: dict, detalle: dict, reg: dict) -> None:
    resumen["intentos"] += 1
    detalle["intentos"] += 1
    resumen["estados"][reg["estado"]] = \
        resumen["estados"].get(reg["estado"], 0) + 1
    bucket = reg["estado"] if reg["estado"] in detalle else "error"
    detalle[bucket] = detalle.get(bucket, 0) + 1
    fam = resumen["familias"].setdefault(reg["familia"],
                                        {"intentos": 0, "ok": 0})
    fam["intentos"] += 1
    if reg["estado"] == "ok":
        fam["ok"] += 1


def _descargar_pagina(cliente, url: str, familia: str, dominio: str,
                     sitio_nombre: str, out: Path, manifest_path: str,
                     known_hashes: set, usados: set, min_chars: int) -> dict:
    """Descarga, extrae y persiste una página; devuelve su registro."""
    base = {"url": url, "dominio": dominio, "familia": familia,
            "sitio": sitio_nombre}
    try:
        resp = cliente.get(url)
    except Exception:  # noqa: BLE001 - una caída no aborta la tanda
        resp = {"estado": "error", "status": None, "html": None, "bytes": 0}
    estado = resp.get("estado", "error")
    reg = {**base, "estado": estado, "chars": 0,
           "bytes": resp.get("bytes", 0), "hash": None, "archivo": None}
    if estado == "ok":
        try:
            extraccion = extraer(resp.get("html") or "", url,
                                familia=familia, min_chars=min_chars)
        except Exception:  # noqa: BLE001
            extraccion = None
        if extraccion is None:
            reg["estado"] = "cortas"
        elif extraccion.get("hash") in known_hashes:
            reg["estado"] = "duplicada_hash"
            reg["hash"] = extraccion.get("hash")
        else:
            slug = slug_desde_url(url)
            destino = out / dominio / f"{slug}.md"
            if (dominio, slug) in usados or destino.exists():
                import hashlib
                slug = (f"{slug}_"
                       + hashlib.sha1(url.encode("utf-8")).hexdigest()[:4])
            usados.add((dominio, slug))
            archivo = guardar_markdown(extraccion, out, slug)
            known_hashes.add(extraccion["hash"])
            reg["estado"] = "ok"
            reg["chars"] = extraccion.get("chars", 0)
            reg["hash"] = extraccion.get("hash")
            reg["archivo"] = str(archivo)
    _append_registro(manifest_path, reg)
    return reg


def descargar_todo(
    plan_path: str,
    config_path: str,
    out_dir: str,
    manifest_previo: str,
    web_previa: str,
    tope_por_dominio: int = 40,
    max_total: int = 150,
    min_chars: int = 1000,
    prioritarias=PRIORIDAD_FAMILIAS,
    bloqueados=DOMINIOS_BLOQUEADOS,
    dry_run: bool = False,
    fabrica_clientes=None,
) -> dict:
    """Descubre, filtra y descarga las candidatas del plan hacia ``out_dir``.

    Combina dos corrientes: sitios de índice validados (descubrimiento con
    ``seguir_indice``) y páginas directas (candidatas de dominios sin config de
    índice). El tope por dominio se comparte entre ambas. Devuelve un resumen
    con intentos, conteos por estado y desglose por familia y dominio. No
    escribe fuera de ``out_dir``.
    """
    if fabrica_clientes is None:
        fabrica_clientes = _fabrica_clientes_def

    plan = cargar_plan(plan_path)
    candidatas = candidatas_por_familia(plan)
    configs = config_por_dominio(cargar_config(config_path))
    tareas = construir_tareas(candidatas, configs, bloqueados, prioritarias)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = str(out / "manifest.jsonl")

    ya = cargar_urls_previas(manifest_previo)
    ya |= cargar_urls_previas(manifest_path)
    known_hashes = cargar_hashes_previos(web_previa)
    known_hashes |= hashes_del_manifest(manifest_path)

    resumen: dict = {
        "intentos": 0,
        "estados": {},
        "por_dominio": {},
        "familias": {},
        "omitidas_ya": 0,
    }
    restantes = max_total
    dominio_usado: dict = {}
    usados: set = set()
    clientes: dict = {}

    def cliente_para(dominio: str, cfg=None):
        if dominio not in clientes:
            clientes[dominio] = fabrica_clientes(
                intervalo_para_sitio(cfg if cfg is not None else {"tipo": "blog"}))
        return clientes[dominio]

    def bajar(url: str, familia: str, dominio: str, sitio_nombre: str, cliente):
        nonlocal restantes
        detalle = _detalle_de(resumen, familia, dominio, sitio_nombre)
        reg = _descargar_pagina(cliente, url, familia, dominio, sitio_nombre,
                               out, manifest_path, known_hashes, usados,
                               min_chars)
        _acumular(resumen, detalle, reg)
        dominio_usado[dominio] = dominio_usado.get(dominio, 0) + 1
        if reg["estado"] in ESTADOS_TERMINALES:
            ya.add(url)
        restantes -= 1

    for tarea in tareas:
        if restantes <= 0:
            break
        familia = tarea["familia"]
        dominio = tarea["dominio"]
        if tarea["tipo"] == "indice":
            cfg = tarea["sitio_cfg"]
            es_foro = cfg.get("tipo") == "foro"
            sitio_nombre = cfg.get("nombre", dominio)
            limite = tope_por_dominio + len(ya) + 10
            try:
                cliente = cliente_para(dominio, cfg)
                descubiertas = seguir_indice(cfg, cliente, limite=limite)
            except Exception:  # noqa: BLE001 - un dominio caído no aborta la tanda
                continue
            vistas: set = set()
            for url in descubiertas:
                if restantes <= 0:
                    break
                if dominio_usado.get(dominio, 0) >= tope_por_dominio:
                    break
                u = normalizar_url(url)
                if u in vistas:
                    continue
                vistas.add(u)
                if u in ya:
                    resumen["omitidas_ya"] += 1
                    continue
                if es_foro and not es_hilo_publico(u):
                    continue
                if dry_run:
                    detalle = _detalle_de(resumen, familia, dominio, sitio_nombre)
                    detalle["intentos"] += 1
                    resumen["intentos"] += 1
                    dominio_usado[dominio] = dominio_usado.get(dominio, 0) + 1
                    continue
                bajar(u, familia, dominio, sitio_nombre, cliente)
        else:
            u = normalizar_url(tarea["url"])
            if u in ya:
                resumen["omitidas_ya"] += 1
                continue
            if dominio_usado.get(dominio, 0) >= tope_por_dominio:
                continue
            if dry_run:
                detalle = _detalle_de(resumen, familia, dominio, dominio)
                detalle["intentos"] += 1
                resumen["intentos"] += 1
                dominio_usado[dominio] = dominio_usado.get(dominio, 0) + 1
                continue
            bajar(u, familia, dominio, dominio, cliente_para(dominio))

    return resumen


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def celdas_bajo_minimo_por_familia(matriz: dict) -> dict:
    """Celdas no completas de la matriz agrupadas por familia."""
    conteo: dict = {}
    for celda in matriz.get("celdas", []):
        if not isinstance(celda, dict) or celda.get("completa"):
            continue
        f = familia_de(celda.get("entidad_id"))
        conteo[f] = conteo.get(f, 0) + 1
    return conteo


def generar_informe(resumen: dict, matriz: dict, umbral_util: int = 3) -> str:
    """Markdown: válidas por dominio/familia, potencial de mejora y flojos."""
    hoy = datetime.date.today().isoformat()
    lineas = [
        "# Informe de recuperación web 2.ª iteración (T64)",
        "",
        f"Generado el {hoy}. Tanda de {resumen.get('intentos', 0)} URLs "
        "intentadas hacia `web_recup2/`. No se ha fusionado nada con `web/` "
        "ni con las evidencias.",
        "",
        f"- URLs omitidas por estar ya descargadas en `web/`: "
        f"**{resumen.get('omitidas_ya', 0)}**",
        "",
        "## Páginas por familia y dominio",
        "",
        "| Familia | Dominio | Intentos | Válidas | Cortas | Duplicadas | Errores/bloqueos |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    flojos = []
    for clave in sorted(resumen.get("por_dominio", {}).keys()):
        d = resumen["por_dominio"][clave]
        errores = d.get("error", 0)
        lineas.append(
            f"| {d['familia']} | {d['dominio']} | {d.get('intentos', 0)} | "
            f"{d.get('ok', 0)} | {d.get('cortas', 0)} | "
            f"{d.get('duplicada_hash', 0)} | {errores} |")
        if d.get("ok", 0) < umbral_util:
            flojos.append(d)
    lineas += [
        "",
        "## Potencial de mejora por familia (matriz v2)",
        "",
        "| Familia | Celdas bajo mínimo | Páginas nuevas válidas | Celdas que podrían mejorar (cota) |",
        "|---|---:|---:|---:|",
    ]
    bajo = celdas_bajo_minimo_por_familia(matriz)
    familias = sorted(set(list(bajo.keys()) + list(resumen.get("familias", {}).keys())))
    for f in familias:
        n_ok = resumen.get("familias", {}).get(f, {}).get("ok", 0)
        n_bajo = bajo.get(f, 0)
        lineas.append(f"| {f} | {n_bajo} | {n_ok} | {min(n_ok, n_bajo)} |")
    lineas += [
        "",
        "> La cota supone una página nueva útil por celda bajo mínimo; la "
        "mejora real exige emparejar cada página con su entidad en la "
        "tubería de cobertura.",
        "",
        f"## Dominios con menos de {umbral_util} páginas útiles",
        "",
    ]
    if flojos:
        for d in sorted(flojos, key=lambda x: (x["familia"], x["dominio"])):
            lineas.append(f"- {d['dominio']} ({d['familia']}): "
                         f"{d.get('ok', 0)} válidas de {d.get('intentos', 0)} "
                         f"intentadas")
    else:
        lineas.append("- Ninguno: todos los dominios aportan al menos "
                     f"{umbral_util} páginas útiles.")
    lineas.append("")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Descarga de URLs candidatas del plan de recuperación "
                    "(2.ª iteración, sin LLM).")
    parser.add_argument("--plan", default=RUTA_PLAN_DEF)
    parser.add_argument("--config", default=RUTA_CONFIG_INDICES)
    parser.add_argument("--out-dir", default=RUTA_OUT_DEF)
    parser.add_argument("--manifest-previo", default=RUTA_MANIFEST_PREVIO_DEF)
    parser.add_argument("--web-previa", default=RUTA_WEB_PREVIA_DEF)
    parser.add_argument("--tope-por-dominio", type=int, default=40)
    parser.add_argument("--max-total", type=int, default=150)
    parser.add_argument("--min-chars", type=int, default=1000)
    parser.add_argument("--matriz", default=RUTA_MATRIZ_DEF,
                       help="Matriz de cobertura v2 para el informe.")
    parser.add_argument("--dry-run", action="store_true",
                       help="Solo descubre y filtra; no descarga ni escribe.")
    args = parser.parse_args(argv)

    resumen = descargar_todo(
        args.plan, args.config, args.out_dir,
        args.manifest_previo, args.web_previa,
        tope_por_dominio=args.tope_por_dominio,
        max_total=args.max_total,
        min_chars=args.min_chars,
        dry_run=args.dry_run,
    )

    estados = ", ".join(f"{k}={v}" for k, v in sorted(resumen["estados"].items()))
    print(f"Intentos: {resumen['intentos']} | {estados or 'ninguno'}")
    print(f"Omitidas ya descargadas: {resumen['omitidas_ya']}")
    if args.dry_run:
        print("[dry-run] no se ha descargado nada.")
        return 0

    with open(args.matriz, encoding="utf-8") as fh:
        matriz = json.load(fh)
    informe = generar_informe(resumen, matriz)
    ruta_informe = os.path.join(args.out_dir, "informe.md")
    with open(ruta_informe, "w", encoding="utf-8") as fh:
        fh.write(informe)
    with open(os.path.join(args.out_dir, "resumen.json"), "w",
             encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    print(f"Informe: {ruta_informe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
