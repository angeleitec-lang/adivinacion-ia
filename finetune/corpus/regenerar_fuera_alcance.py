#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenera el bloque `fuera_alcance` corrupto del dataset v1d (T136).

Contexto
--------
Las ~400 filas `fuera_alcance` del dataset v1d salieron con el prompt
mutilado: la pregunta del consultante quedó como `"<n> <arranque>:"` en vez
de la pregunta real (patrón `Pregunta del consultante: "0 Tengo curiosidad:"`).
El generador (`generate_tasks.Builder.fuera_alcance`) ya está corregido (T127),
de modo que volver a construir las tareas produce prompts válidos con la
pregunta completa.

Este script NO toca `generate_tasks.py` ni `fase1_prompts.py`: los importa y
orquesta la regeneración en un conjunto NUEVO bajo
`/Users/angelgonzalez/fase0/fuera_alcance_v2/`, sin sobrescribir v1d.

Reutiliza el ejecutor canónico de fase 1 (`ejecutor_fase1`), que ya es
reanudable (pending/running/done), reintenta ante rechazos del verificador y
corta por tasa de error. Las respuestas aceptadas se exportan en el esquema
ShareGPT exacto de las filas `fuera_alcance` de v1d
(`{conversations:[system,human,gpt], id, bloque, generador}`).

Encendido del LLM: SOLO nodo2 (`http://10.0.0.4:8000/v1`), 1 worker.
Nodo1 no se usa para generación de datos. Nunca Mercury.

Subcomandos
-----------
  --dry-run    Construye las tareas en memoria, imprime muestra y estimación
               de llamadas/tokens. Sin efectos en disco ni red.
  --prepare    Crea la BD de trabajo e inserta los jobs como `pending`
               (idempotente: no duplica los ya `done`).
  --run        Prepara si hace falta y ejecuta la generación contra nodo2
               (1 worker). Escribe aceptadas/rechazadas y el jsonl final.
  --report     Vuelve a leer los resultados y emite el informe de cifras y
               rechazos por motivo (sin tocar el LLM).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import generate_tasks as gt  # noqa: E402
import fase1_prompts as fp  # noqa: E402

WORK_DIR_DEFECTO = "/Users/angelgonzalez/fase0/fuera_alcance_v2"
DB_NOMBRE = "jobs_fuera_v2.db"
JSONL_FINAL = "fuera_alcance_v2.jsonl"
ENDPOINT_NODO2 = "http://10.0.0.4:8000/v1"
MODELO_DEFECTO = "halogen-qwen3.8-flash-next"
BLOQUE = "fuera_alcance"

# Estimación conservadora para el dry-run (chars/token ~4, reintentos medios).
CHARS_POR_TOKEN = 4.0
REINTENTOS_ESTIMADOS = 0.3


def _nfc(texto):
    return unicodedata.normalize("NFC", texto or "")


def construir_jobs(n, seed=42):
    """Construye `n` jobs `fuera_alcance` con el generador ya corregido.

    Devuelve la lista de tuplas `(bloque, system, prompt, payload_json,
    max_tokens)` que produce `generate_tasks.Builder`, lista para insertar.
    """
    if n <= 0:
        raise ValueError(f"n debe ser > 0 (recibido {n!r})")
    builder = gt.Builder(
        random.Random(seed),
        gt.load_kb("tarot.json"),
        gt.load_kb("astrologia.json"),
        gt.load_kb("numerologia.json"),
        gt.load_kb("baraja_espanola.json"),
    )
    return builder.fuera_alcance(n)


def validar_jobs(filas):
    """Comprueba invariantes de cada job regenerado. Devuelve lista de errores.

    Un job es válido si: es del bloque correcto, el payload trae `tecnica` y
    `pregunta` no vacías, el prompt arranca con el encabezado de consulta
    fuera de alcance, contiene la pregunta real entre comillas y NO presenta
    el patrón de corrupción (`"数字 arranque:"`).
    """
    import re

    corrupto = re.compile(r'Pregunta del consultante:\s*"\d+\s+[^"]*"\s*$')
    errores = []
    for i, fila in enumerate(filas):
        bloque, system, prompt, payload_json, _mt = fila
        if bloque != BLOQUE:
            errores.append(f"[{i}] bloque inesperado: {bloque!r}")
            continue
        try:
            payload = json.loads(payload_json)
        except (TypeError, ValueError) as exc:
            errores.append(f"[{i}] payload no es JSON: {exc}")
            continue
        tecnica = payload.get("tecnica") or ""
        pregunta = payload.get("pregunta") or ""
        if not tecnica:
            errores.append(f"[{i}] payload sin 'tecnica'")
        if not pregunta.strip():
            errores.append(f"[{i}] payload sin 'pregunta'")
        if not prompt or not prompt.startswith("Consulta fuera de alcance."):
            errores.append(f"[{i}] prompt sin encabezado de fuera de alcance")
        if pregunta and f'"{pregunta}"' not in prompt:
            errores.append(f"[{i}] la pregunta real no aparece en el prompt")
        if corrupto.search(prompt or ""):
            errores.append(f"[{i}] patrón de corrupción presente en el prompt")
    return errores


def estimar(filas):
    """Estimación del coste de la pasada (sin llamar al LLM)."""
    n = len(filas)
    if n == 0:
        return {"jobs": 0, "llamadas_estimadas": 0,
                "tokens_prompt_estimados": 0, "tokens_salida_presupuesto": 0}
    chars_prompt = sum(len(f[2]) for f in filas)
    presupuesto_salida = sum(int(f[4]) for f in filas)
    tokens_prompt = int(chars_prompt / CHARS_POR_TOKEN)
    llamadas = int(round(n * (1.0 + REINTENTOS_ESTIMADOS)))
    return {
        "jobs": n,
        "llamadas_estimadas": llamadas,
        "tokens_prompt_estimados": tokens_prompt,
        "tokens_salida_presupuesto": presupuesto_salida,
    }


def ruta_db(work_dir):
    return Path(work_dir) / DB_NOMBRE


def preparar(work_dir, filas, replace_pending=True):
    """Crea la BD de trabajo e inserta los jobs pendientes (idempotente)."""
    import sqlite3

    wd = Path(work_dir)
    wd.mkdir(parents=True, exist_ok=True)
    db = ruta_db(wd)
    con = sqlite3.connect(str(db))
    try:
        gt.crear_tabla(con)
        insertadas = gt.insertar_jobs(con, filas, replace_pending=replace_pending)
        total = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE bloque=?", (BLOQUE,)
        ).fetchone()[0]
        pendientes = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE bloque=? AND status='pending'",
            (BLOQUE,),
        ).fetchone()[0]
    finally:
        con.close()
    return {"db": str(db), "insertadas": insertadas,
            "total_bloque": total, "pendientes": pendientes}


def crear_cliente(endpoint=ENDPOINT_NODO2, model=MODELO_DEFECTO):
    """Cliente LLM apuntando SOLO a nodo2, 1 de concurrencia, ~1 req/s."""
    from llm_client import LLMClient

    if "10.0.0.3" in endpoint:
        raise ValueError(
            "esta pista no usa nodo1 para generación de datos; "
            f"endpoint prohibido: {endpoint}")
    return LLMClient(
        endpoints=[endpoint],
        model=model,
        max_concurrencia=1,
        tasa_max_por_minuto=60,
        timeout=180.0,
    )


def ejecutar_generacion(work_dir, endpoint=ENDPOINT_NODO2, model=MODELO_DEFECTO,
                       workers=1, limite=0):
    """Ejecuta la pasada reanudable sobre la BD de trabajo (nodo2, 1 worker)."""
    import ejecutor_fase1 as ex

    db = ruta_db(work_dir)
    if not db.exists():
        raise FileNotFoundError(
            f"no hay BD de trabajo en {db}; ejecuta --prepare primero")
    kb = ex.cargar_kb()
    cliente = crear_cliente(endpoint=endpoint, model=model)
    out_dir = Path(work_dir)
    resumen = ex.ejecutar(
        str(db), cliente, kb,
        workers=workers,
        limite=limite,
        out_dir=str(out_dir),
        formato="sharegpt",
        backend=ex.GENERADOR_LOCAL,
    )
    return resumen


def _leer_jsonl(ruta):
    p = Path(ruta)
    if not p.exists():
        return []
    filas = []
    with p.open("r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def exportar_final(work_dir):
    """Copia las aceptadas (ShareGPT) al jsonl final del conjunto v2."""
    aceptadas = _leer_jsonl(Path(work_dir) / "aceptadas.jsonl")
    final = Path(work_dir) / JSONL_FINAL
    with final.open("w", encoding="utf-8") as fh:
        for fila in aceptadas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return {"final": str(final), "aceptadas": len(aceptadas)}


def rechazos_por_motivo(work_dir):
    """Agrupa los rechazos por motivo (primer motivo normalizado)."""
    rechazadas = _leer_jsonl(Path(work_dir) / "rechazadas.jsonl")
    conteo = {}
    for fila in rechazadas:
        motivos = fila.get("motivos") or ["sin_motivo"]
        clave = motivos[0] if isinstance(motivos, list) else str(motivos)
        clave = _nfc(clave).strip() or "sin_motivo"
        conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


def informe(work_dir):
    """Cifras del estado actual del conjunto v2 (sin LLM)."""
    import sqlite3

    db = ruta_db(work_dir)
    datos: dict = {"work_dir": str(work_dir)}
    if db.exists():
        con = sqlite3.connect(str(db))
        try:
            for estado in ("pending", "running", "done", "failed"):
                datos[estado] = con.execute(
                    "SELECT COUNT(*) FROM jobs WHERE bloque=? AND status=?",
                    (BLOQUE, estado),
                ).fetchone()[0]
        finally:
            con.close()
    aceptadas = _leer_jsonl(Path(work_dir) / "aceptadas.jsonl")
    datos["aceptadas_jsonl"] = len(aceptadas)
    datos["rechazos_por_motivo"] = rechazos_por_motivo(work_dir)
    return datos


def imprimir_informe(datos):
    print("=== INFORME fuera_alcance_v2 ===")
    print(f"directorio: {datos.get('work_dir')}")
    for k in ("pending", "running", "done", "failed"):
        if k in datos:
            print(f"  {k:>8}: {datos[k]}")
    print(f"  aceptadas jsonl: {datos.get('aceptadas_jsonl', 0)}")
    rechazos = datos.get("rechazos_por_motivo") or {}
    if rechazos:
        print("  rechazos por motivo:")
        for motivo, n in sorted(rechazos.items(), key=lambda x: -x[1]):
            print(f"    {n:>4}  {motivo}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Regenera el bloque fuera_alcance (T136) en un conjunto nuevo.")
    ap.add_argument("--n", type=int, default=400, help="número de tareas (defecto 400)")
    ap.add_argument("--seed", type=int, default=42, help="semilla del generador")
    ap.add_argument("--work-dir", default=WORK_DIR_DEFECTO,
                    help=f"directorio del conjunto v2 (defecto {WORK_DIR_DEFECTO})")
    ap.add_argument("--endpoint", default=ENDPOINT_NODO2,
                    help=f"endpoint LLM (defecto {ENDPOINT_NODO2})")
    ap.add_argument("--model", default=MODELO_DEFECTO, help="modelo del endpoint")
    ap.add_argument("--workers", type=int, default=1, help="workers (defecto 1)")
    ap.add_argument("--limite", type=int, default=0,
                    help="máx. jobs por pasada (0 = todos)")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--dry-run", action="store_true",
                      help="solo estimación y muestra, sin disco ni red")
    modo.add_argument("--prepare", action="store_true",
                      help="crea la BD e inserta jobs pendientes")
    modo.add_argument("--run", action="store_true",
                      help="prepara y ejecuta la generación (nodo2, 1 worker)")
    modo.add_argument("--report", action="store_true",
                      help="informe de cifras y rechazos (sin LLM)")
    args = ap.parse_args(argv)

    if args.report:
        imprimir_informe(informe(args.work_dir))
        return 0

    filas = construir_jobs(args.n, seed=args.seed)
    errores = validar_jobs(filas)
    if errores:
        print(f"ERRORES de validación en {len(errores)} jobs (se aborta):")
        for e in errores[:20]:
            print("  -", e)
        return 2

    if args.dry_run:
        est = estimar(filas)
        print("=== DRY-RUN fuera_alcance_v2 ===")
        print(f"jobs construidos: {est['jobs']} (todos validados)")
        print(f"llamadas estimadas (con {REINTENTOS_ESTIMADOS:.0%} reintentos): "
              f"{est['llamadas_estimadas']}")
        print(f"tokens de prompt estimados (~{CHARS_POR_TOKEN:.0f} char/token): "
              f"{est['tokens_prompt_estimados']}")
        print(f"presupuesto de salida (suma max_tokens): "
              f"{est['tokens_salida_presupuesto']}")
        print(f"endpoint previsto: {args.endpoint} (modelo {args.model}, "
              f"{args.workers} worker)")
        print("muestra de prompts:")
        for fila in filas[:5]:
            payload = json.loads(fila[3])
            print(f"  - [{payload['tecnica']}] {payload['pregunta']}")
        return 0

    prep = preparar(args.work_dir, filas)
    print(f"PREPARE: {prep['insertadas']} insertadas, "
          f"{prep['pendientes']} pendientes en {prep['db']}")

    if not args.run:
        return 0

    resumen = ejecutar_generacion(
        args.work_dir, endpoint=args.endpoint, model=args.model,
        workers=args.workers, limite=args.limite)
    print("=== EJECUCIÓN fuera_alcance_v2 ===")
    for k in ("procesadas", "aceptadas", "rechazadas", "errores_red",
              "huerfanas_recuperadas", "parada"):
        if k in resumen:
            print(f"  {k}: {resumen[k]}")
    exp = exportar_final(args.work_dir)
    print(f"  exportado: {exp['final']} ({exp['aceptadas']} filas)")
    imprimir_informe(informe(args.work_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
