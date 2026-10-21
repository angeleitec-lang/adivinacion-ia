#!/usr/bin/env python3
"""Piloto de fase 1 (T49): medir si los prompts producen lecturas aceptables.

Pide unas pocas lecturas a un LLM real, las pasa por el verificador
determinista de fase1_prompts y deja salida reanudable (piloto.jsonl) más un
informe (informe_piloto.md). No toca jobs.db ni los generadores suspendidos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fase1_prompts import FAMILIAS, generar_ejemplos, verificar_lectura  # noqa: E402,F401
from llm_client import LLMClient  # noqa: E402

_BLOQUE_PENSAMIENTO = re.compile(
    r"<(?:think|thinking)>.*?</(?:think|thinking)>", re.DOTALL | re.IGNORECASE
)
_ETIQUETA_PENSAMIENTO = re.compile(r"<(?:think|thinking)\b[^>]*>", re.IGNORECASE)


def limpiar_lectura(texto):
    """Devuelve solo la respuesta final: sin bloques de razonamiento visible."""
    if not texto:
        return ""
    t = _BLOQUE_PENSAMIENTO.sub("", texto)
    m = _ETIQUETA_PENSAMIENTO.search(t)
    if m:
        t = t[: m.start()]  # bloque abierto (respuesta cortada): se descarta
    return t.strip()


def prompt_reintento(prompt_user, motivos):
    """Prompt de segundo intento: añade los motivos de rechazo del verificador."""
    lista = "\n".join(f"- {m}" for m in motivos)
    return (
        prompt_user
        + "\n\n---\nTu respuesta anterior fue rechazada por el verificador por estos "
        "motivos:\n" + lista
        + "\nVuelve a redactar la lectura completa desde el principio, corrigiendo esos "
        "puntos y respetando todas las instrucciones anteriores."
    )


def cargar_tareas(n_por_familia=3, semilla=42, ruta=None):
    """Construye las tareas piloto vía fase1_prompts.generar_ejemplos (sin tocar nodos)."""
    propio = None
    if ruta is None:
        import tempfile

        fd, nombre = tempfile.mkstemp(prefix="t49_tareas_", suffix=".jsonl")
        os.close(fd)
        propio = Path(nombre)
        ruta = propio
    try:
        generar_ejemplos(ruta, n=n_por_familia, seed=semilla)
        tareas = []
        contador = Counter()
        with Path(ruta).open(encoding="utf-8") as fh:
            for linea in fh:
                if not linea.strip():
                    continue
                fila = json.loads(linea)
                familia = fila["familia"]
                contador[familia] += 1
                tarea = dict(fila["tarea"])
                tarea["calculos"] = fila["calculos"]
                tareas.append(
                    {
                        "id": f"{familia}-{contador[familia]:02d}",
                        "familia": familia,
                        "tarea": tarea,
                        "prompt_system": fila["system"],
                        "prompt_user": fila["user"],
                    }
                )
        return tareas
    finally:
        if propio is not None:
            try:
                propio.unlink()
            except OSError:
                pass


def ejecutar_una(tarea, cliente, max_reintentos=1, max_tokens=2048, temperature=0.2):
    """Una tarea -> registro con lectura, veredicto del verificador e intentos.

    Errores de red o salida vacía quedan en el campo `error` (no se dan por
    hechos: la reanudación los reintentará).
    """
    t0 = time.monotonic()
    usuario = tarea["prompt_user"]
    lectura = ""
    ok = False
    motivos = []
    intentos = 0
    error = None
    while True:
        intentos += 1
        try:
            raw = cliente.chat(
                tarea["prompt_system"],
                usuario,
                max_tokens=max_tokens,
                temperature=temperature,
                max_reintentos=0,
            )
        except Exception as exc:
            error = f"error_red:{type(exc).__name__}"
            break
        lectura = limpiar_lectura(raw)
        if not lectura:
            error = "salida_vacia"
            break
        ok, motivos = verificar_lectura(tarea["tarea"], lectura)
        if ok or intentos > max_reintentos:
            break
        usuario = prompt_reintento(tarea["prompt_user"], motivos)
    return {
        "id": tarea["id"],
        "familia": tarea["familia"],
        "huella": _huella(tarea),
        "prompt_system": tarea["prompt_system"],
        "prompt_user": tarea["prompt_user"],
        "lectura": lectura,
        "ok": bool(ok),
        "motivos": list(motivos),
        "intentos": intentos,
        "chars": len(lectura),
        "segundos": round(time.monotonic() - t0, 3),
        "error": error,
    }


def _huella(tarea):
    """Identidad de contenido de la tarea (T67, defecto B4).

    Los ids «{familia}-{NN}» no fijan el contenido: al reanudar con otra
    --semilla o --n-por-familia el mismo id puede corresponder a otra tarea.
    La huella permite detectarlo y avisar en vez de omitir en silencio.
    """
    base = "\n".join([tarea.get("prompt_system", ""), tarea.get("prompt_user", "")])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ids_existente(destino):
    """Devuelve {id: huella} de piloto.jsonl.

    huella es None en registros escritos antes de T67 (sin el campo) o sin
    prompts: esos casos no permiten afirmar cambio de contenido y no avisan.
    """
    hechos = {}
    if Path(destino).exists():
        with Path(destino).open(encoding="utf-8") as fh:
            for linea in fh:
                if not linea.strip():
                    continue
                try:
                    fila = json.loads(linea)
                    hechos[fila["id"]] = fila.get("huella")
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
    return hechos


def _compactar_errores(errores_destino):
    """Deja en piloto_errores.jsonl solo el último registro por id (T67, B4).

    Al reanudar, la misma tarea fallida se reapuntaba en cada pasada y el
    fichero acumulaba duplicados. Se reescribe de forma atómica previa copia
    diaria; devuelve cuántas líneas se retiraron (0 si no hizo falta).
    """
    errores_destino = Path(errores_destino)
    if not errores_destino.exists():
        return 0
    con_error = []
    corruptas = 0
    with errores_destino.open(encoding="utf-8") as fh:
        for linea in fh:
            if not linea.strip():
                continue
            try:
                con_error.append(json.loads(linea))
            except json.JSONDecodeError:
                corruptas += 1
    por_id = {}
    orden = []
    for fila in con_error:
        ident = fila.get("id")
        if ident not in por_id:
            orden.append(ident)
        por_id[ident] = fila
    if len(por_id) + corruptas == len(con_error):
        return 0  # ya sin duplicados: no se toca el fichero
    respaldo = errores_destino.with_name(
        errores_destino.name + ".bak-" + datetime.now().strftime("%Y%m%d")
    )
    if not respaldo.exists():
        shutil.copy2(errores_destino, respaldo)
    tmp = errores_destino.with_name(errores_destino.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for ident in orden:
            fh.write(json.dumps(por_id[ident], ensure_ascii=False) + "\n")
    os.replace(tmp, errores_destino)
    return len(con_error) - len(por_id)


def ejecutar_piloto(
    tareas,
    cliente,
    workers=1,
    max_reintentos=1,
    out_dir=None,
    umbral_error=0.30,
    min_muestras=5,
    max_tokens=2048,
    temperature=0.2,
):
    """Escribe `piloto.jsonl` de forma incremental (flush por línea), reanudable por id.

    Si más del `umbral_error` de las tareas procesadas acaban en error de red o
    salida vacía (con al menos `min_muestras` tareas), se para: los nodos pueden
    estar saturados. Devuelve resumen con contador de errores y motivo de parada.
    """
    out_dir = Path(out_dir) if out_dir else Path(__file__).resolve().parent / "salida" / "piloto"
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / "piloto.jsonl"

    hechos = _ids_existente(destino)
    pendientes = [t for t in tareas if t["id"] not in hechos]
    omitidos = len(tareas) - len(pendientes)
    # T67 (B4): omitir está bien si la tarea es la misma; si el id cambió de
    # contenido (otra --semilla / --n-por-familia) hay que decirlo, no callar.
    distintos = [
        t["id"] for t in tareas
        if t["id"] in hechos and hechos[t["id"]] is not None
        and hechos[t["id"]] != _huella(t)
    ]
    if distintos:
        print(f"AVISO: {len(distintos)} ids omitidos corresponden a otra tarea "
              f"(los prompts coinciden con registros previos de otra semilla o "
              f"otro --n-por-familia): {distintos[:5]}. Repite con --out-dir "
              "nuevo o retira piloto.jsonl.", flush=True)

    lock = threading.Lock()
    estado = {"errores": 0, "procesadas": 0, "escritas": 0}
    parada = []
    errores_destino = out_dir / "piloto_errores.jsonl"

    def uno(tarea):
        with lock:
            if parada:
                return
        registro = ejecutar_una(
            tarea, cliente, max_reintentos=max_reintentos,
            max_tokens=max_tokens, temperature=temperature,
        )
        with lock:
            estado["procesadas"] += 1
            if registro["error"]:
                estado["errores"] += 1
                con_error = dict(registro)
                con_error["tarea_pendiente"] = True
                with errores_destino.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(con_error, ensure_ascii=False) + "\n")
                    fh.flush()
                print(f"[error] {registro['id']}: {registro['error']} "
                      f"({registro['segundos']:.0f}s)", flush=True)
            else:
                with destino.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
                    fh.flush()
                estado["escritas"] += 1
            if (
                not parada
                and estado["procesadas"] >= min_muestras
                and estado["errores"] / estado["procesadas"] > umbral_error
            ):
                parada.append(
                    f"{estado['errores']}/{estado['procesadas']} peticiones fallaron "
                    f"por red o salida vacía (umbral {umbral_error:.0%})"
                )

    if workers <= 1:
        for tarea in pendientes:
            if parada:
                break
            uno(tarea)
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futuros = [ex.submit(uno, t) for t in pendientes]
            for f in as_completed(futuros):
                f.result()

    compactados = _compactar_errores(errores_destino) if estado["errores"] else 0
    resumen = {
        "escritas": estado["escritas"],
        "procesadas": estado["procesadas"],
        "errores": estado["errores"],
        "pendientes": len(pendientes),
        "omitidos": omitidos,
        "omitidos_contenido_distinto": len(distintos),
        "errores_compactados": compactados,
        "parada": parada[0] if parada else None,
        "piloto": str(destino),
    }
    if parada:
        print(f"PARADA: {parada[0]}. Avisar antes de continuar: revisando el "
              "estado de los nodos (10.0.0.3 / 10.0.0.4).", flush=True)
    return resumen


def _media(vals):
    return sum(vals) / len(vals) if vals else 0.0


def generar_informe(out_dir, meta=None):
    """Redacta informe_piloto.md a partir de piloto.jsonl (y la meta de esta ejecución)."""
    out_dir = Path(out_dir)
    registros = []
    destino = out_dir / "piloto.jsonl"
    if destino.exists():
        with destino.open(encoding="utf-8") as fh:
            for linea in fh:
                if linea.strip():
                    try:
                        registros.append(json.loads(linea))
                    except json.JSONDecodeError:
                        continue
    meta = meta or {}

    lineas = ["# Informe piloto — fase 1 (T49)", ""]
    lineas += [
        f"- Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- Tareas valoradas en piloto.jsonl: {len(registros)}",
        f"- Procesadas en la última ejecución: {meta.get('procesadas', 's/d')}",
        f"- Errores de red o salida vacía (última ejecución): {meta.get('errores', 's/d')}",
    ]
    if meta.get("parada"):
        lineas.append(f"- **PARADA ANTICIPADA**: {meta['parada']}")
    lineas.append("")

    if not registros:
        lineas.append("Sin lecturas registradas: no se puede calcular aprobación.")
        (out_dir / "informe_piloto.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
        return "\n".join(lineas)

    lineas += [
        "El verificador es determinista (fase1_prompts.verificar_lectura). El veredicto",
        "humano de calidad aún no existe: aquí solo se mide aprobación automática.",
        "",
        "## Aprobación por familia",
        "",
        "| familia | n | ok | ok a la primera | tasa | tasa 1er intento |",
        "|---|---|---|---|---|---|",
    ]
    familias = sorted({r.get("familia") or "(sin familia)" for r in registros})
    total = len(registros)
    ok_total = 0
    primera_total = 0
    for familia in familias:
        rs = [r for r in registros if (r.get("familia") or "(sin familia)") == familia]
        ok = sum(1 for r in rs if r.get("ok"))
        primera = sum(1 for r in rs if r.get("ok") and r.get("intentos", 1) <= 1)
        ok_total += ok
        primera_total += primera
        lineas.append(
            f"| {familia} | {len(rs)} | {ok} | {primera} | "
            f"{ok / len(rs):.0%} | {primera / len(rs):.0%} |"
        )
    lineas.append(
        f"| **GLOBAL** | {total} | {ok_total} | {primera_total} | "
        f"{ok_total / total:.0%} | {primera_total / total:.0%} |"
    )
    lineas += [
        "",
        f"- Aprobación **sin reintento** (1er intento): {primera_total / total:.0%}",
        f"- Aprobación **con reintento** permitido: {ok_total / total:.0%}",
        "",
        "## Motivos de rechazo más frecuentes",
        "",
    ]
    motivos = Counter()
    for r in registros:
        if not r.get("ok"):
            for m in r.get("motivos") or [r.get("error") or "sin motivo"]:
                motivos[m] += 1
    if motivos:
        for motivo, n in motivos.most_common(15):
            lineas.append(f"- {motivo}: {n}")
    else:
        lineas.append("- Ninguno: todas las lecturas registradas aprobaron el verificador.")

    chars = [r.get("chars", 0) for r in registros]
    segs = [r.get("segundos", 0.0) for r in registros]
    seg_media = _media(segs)
    lineas += [
        "",
        "## Longitud y tiempo",
        "",
        f"- Longitud (chars): media {_media(chars):.0f}, mín {min(chars)}, máx {max(chars)}",
        f"- Tiempo medio por lectura: {seg_media:.1f} s (incluye reintentos)",
        "",
        "## Estimación para 10.000 lecturas",
        "",
        f"- Fórmula: 10.000 × tiempo medio / segundos por hora / workers.",
    ]
    if seg_media > 0:
        for w in (3, 6):
            horas = 10000 * seg_media / 3600.0 / w
            dias = horas / 24.0
            lineas.append(f"- {w} workers: {horas:.1f} h ({dias:.1f} días) "
                          f"a {seg_media:.1f} s/lectura")
    else:
        lineas.append("- Sin datos de tiempo: no calculable.")
    texto = "\n".join(lineas) + "\n"
    (out_dir / "informe_piloto.md").write_text(texto, encoding="utf-8")
    return texto


def main(argv=None):
    ap = argparse.ArgumentParser(description="Piloto fase 1 con LLM real (T49).")
    ap.add_argument("--n-por-familia", type=int, default=3)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-reintentos", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--umbral-error", type=float, default=0.30)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoints", default=None,
                    help="URLs separadas por coma (por defecto las de llm_client)")
    ap.add_argument("--out-dir", default="/Users/angelgonzalez/fase0/piloto_fase1")
    args = ap.parse_args(argv)

    endpoints = args.endpoints.split(",") if args.endpoints else None
    cliente = LLMClient(endpoints=endpoints, timeout=args.timeout)
    if args.model:
        cliente.model = args.model

    tareas = cargar_tareas(args.n_por_familia, args.semilla)
    print(f"Tareas piloto: {len(tareas)} ({args.n_por_familia} por familia, "
          f"semilla {args.semilla})", flush=True)
    resumen = ejecutar_piloto(
        tareas, cliente, workers=args.workers, max_reintentos=args.max_reintentos,
        out_dir=args.out_dir, umbral_error=args.umbral_error,
        max_tokens=args.max_tokens, temperature=args.temperature,
    )
    informe = generar_informe(args.out_dir, meta=resumen)
    print(f"\nResumen: {resumen['escritas']} escritas, {resumen['procesadas']} procesadas, "
          f"{resumen['errores']} errores, {resumen['omitidos']} omitidas ya hechas.", flush=True)
    print(f"Piloto: {resumen['piloto']}\nInforme: {Path(args.out_dir) / 'informe_piloto.md'}",
          flush=True)
    if resumen["parada"]:
        print("AVISO: el piloto se detuvo por exceso de errores de red; revisar los "
              "nodos antes de reanudar.", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
