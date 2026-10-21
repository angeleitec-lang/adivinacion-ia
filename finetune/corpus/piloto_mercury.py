#!/usr/bin/env python3
"""Piloto de fase 1 con Mercury 3 (T83): medir si sus lecturas pasan el
verificador con la calidad exigida, frente a la línea base local (T49/T72).

Genera 3 tareas por familia (todas las de fase1_prompts.FAMILIAS, incluidas
las de baraja española y las tiradas largas) con semilla fija, las envía a
Inception Mercury 3 (reasoning_effort=instant, max_completion_tokens según la
tabla RECOMENDACION_MAX_TOKENS, concurrencia <= 3), las pasa por
verificar_lectura con reintento por causa (igual que el ejecutor de fase 1) y
guarda lecturas y motivos de rechazo. No toca jobs.db ni corpus/final: trabaja
con salidas en /Users/angelgonzalez/fase0/piloto_mercury/. La clave de la API
se lee de INCEPTION_API_KEY o del auth.json de opencode, nunca se escribe en
repo/logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fase1_prompts as fp  # noqa: E402
from ejecutor_fase1 import MOTIVO_TRUNCADO, respuesta_truncada  # noqa: E402
from fase1_piloto import cargar_tareas, limpiar_lectura, prompt_reintento  # noqa: E402
from llm_client import LLMClient  # noqa: E402

BACKEND_URL = "https://api.inceptionlabs.ai/v1"
BACKEND_MODEL = "mercury-3"
API_KEY_ENV = "INCEPTION_API_KEY"
AUTH_FILE = os.path.expanduser("~/.local/share/opencode/auth.json")
AUTH_ENTRY = "inception"

REASONING_EFFORT = "instant"
TEMPERATURE = 0.5
TASA_MAX_POR_MINUTO = 60
TIMEOUT_S = 180.0
MAX_COMPLETION_TOKENS_DEFECTO = 6144

FASE0_PILOTO = "/Users/angelgonzalez/fase0/piloto_mercury"
LOCAL_PILOTO_JSONL = "/Users/angelgonzalez/fase0/piloto_fase1/piloto.jsonl"
MIN_MUESTRAS = 5
UMBRAL_ERROR = 0.30


def cargar_clave_inception():
    """Devuelve la clave de Inception sin exponerla: env primero, auth.json después."""
    clave = os.environ.get(API_KEY_ENV)
    if clave:
        return clave
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth = json.load(f)
        entrada = auth.get(AUTH_ENTRY) or {}
        clave = entrada.get("key")
    except (OSError, json.JSONDecodeError):
        clave = None
    if not clave:
        raise RuntimeError(
            "No hay clave para %s: define %s o la entrada %r en %s"
            % (BACKEND_MODEL, API_KEY_ENV, AUTH_ENTRY, AUTH_FILE))
    os.environ[API_KEY_ENV] = clave
    return clave


def crear_cliente(familia, metricas=None, simulado=None):
    """LLMClient apuntando a Mercury 3 con los parámetros de T83."""
    cargar_clave_inception()
    max_tokens = fp.RECOMENDACION_MAX_TOKENS.get(
        familia, MAX_COMPLETION_TOKENS_DEFECTO)
    return LLMClient(
        endpoints=[{
            "url": BACKEND_URL,
            "model": BACKEND_MODEL,
            "api_key_env": API_KEY_ENV,
        }],
        reasoning_effort=REASONING_EFFORT,
        max_completion_tokens=max_tokens,
        max_concurrencia=1,
        tasa_max_por_minuto=TASA_MAX_POR_MINUTO,
        timeout=TIMEOUT_S,
        metricas=metricas,
        simulado=simulado,
    )


def _huella(tarea):
    base = "\n".join([tarea.get("prompt_system", ""), tarea.get("prompt_user", "")])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def _ids_existente(destino):
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


def ejecutar_una(tarea, cliente, max_reintentos=1):
    """Una tarea -> registro con lectura, veredicto, reintento por causa y tokens.

    Añade la detección de truncamiento (igual que el ejecutor de fase 1) a los
    motivos del verificador. El presupuesto de tokens es el recomendado para la
    familia.
    """
    t0 = time.monotonic()
    familia = tarea["familia"]
    max_tokens = fp.RECOMENDACION_MAX_TOKENS.get(
        familia, MAX_COMPLETION_TOKENS_DEFECTO)
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
                temperature=TEMPERATURE,
                max_reintentos=0,
            )
        except Exception as exc:
            error = f"error_red:{type(exc).__name__}"
            break
        lectura = limpiar_lectura(raw)
        if not lectura:
            error = "salida_vacia"
            break
        motivos = []
        if respuesta_truncada(lectura):
            motivos.append(MOTIVO_TRUNCADO)
        ver_ok, ver_motivos = fp.verificar_lectura(tarea["tarea"], lectura)
        motivos.extend(ver_motivos)
        ok = not motivos
        if ok or intentos > max_reintentos:
            break
        usuario = prompt_reintento(tarea["prompt_user"], motivos)
    return {
        "id": tarea["id"],
        "familia": familia,
        "huella": _huella(tarea),
        "prompt_system": tarea["prompt_system"],
        "prompt_user": tarea["prompt_user"],
        "lectura": lectura,
        "ok": bool(ok),
        "motivos": list(motivos),
        "intentos": intentos,
        "chars": len(lectura),
        "truncada": bool(motivos and motivos[0] == MOTIVO_TRUNCADO),
        "max_completion_tokens": max_tokens,
        "segundos": round(time.monotonic() - t0, 3),
        "error": error,
    }


def ejecutar_piloto(tareas, worker=None, max_reintentos=1, out_dir=None,
                    umbral_error=UMBRAL_ERROR, min_muestras=MIN_MUESTRAS,
                    cliente_factory=None):
    """Escribe piloto.jsonl de forma incremental y reanudable, con workers <= 3.

    Cada tarea usa un cliente propio (clave por familia); la concurrencia se
    limita a `workers` con ThreadPoolExecutor. Devuelve resumen.
    """
    out_dir = Path(out_dir) if out_dir else Path(FASE0_PILOTO)
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / "piloto.jsonl"
    if cliente_factory is None:
        cliente_factory = crear_cliente
    workers = 3 if worker is None else worker

    hechos = _ids_existente(destino)
    pendientes = [t for t in tareas if t["id"] not in hechos]
    omitidos = len(tareas) - len(pendientes)
    distintos = [
        t["id"] for t in tareas
        if t["id"] in hechos and hechos[t["id"]] is not None
        and hechos[t["id"]] != _huella(t)
    ]
    if distintos:
        print(f"AVISO: {len(distintos)} ids omitidos corresponden a otra tarea "
              f"(cambió la semilla o el n-por-familia): {distintos[:5]}. Usa "
              "--out-dir nuevo o retira piloto.jsonl.", flush=True)

    lock = threading.Lock()
    metricas = {"peticiones": 0, "latencia_total": 0.0, "max_latencia": 0.0,
                "prompt_tokens": 0, "completion_tokens": 0}
    estado = {"errores": 0, "procesadas": 0, "escritas": 0}
    parada = []
    errores_destino = out_dir / "piloto_errores.jsonl"

    def uno(tarea):
        with lock:
            if parada:
                return
        cliente = cliente_factory(tarea["familia"], metricas=metricas)
        registro = ejecutar_una(tarea, cliente, max_reintentos=max_reintentos)
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
                    f"{estado['errores']}/{estado['procesadas']} peticiones "
                    f"fallaron por red o salida vacía (umbral {umbral_error:.0%})"
                )

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as ex:
        futuros = [ex.submit(uno, t) for t in pendientes]
        for f in as_completed(futuros):
            f.result()

    resumen = {
        "escritas": estado["escritas"],
        "procesadas": estado["procesadas"],
        "errores": estado["errores"],
        "pendientes": len(pendientes),
        "omitidos": omitidos,
        "omitidos_contenido_distinto": len(distintos),
        "parada": parada[0] if parada else None,
        "metricas": metricas,
        "piloto": str(destino),
    }
    if parada:
        print(f"PARADA: {parada[0]}. Revisar el estado de la API de Inception.",
              flush=True)
    return resumen


def _media(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _leer_jsonl(ruta):
    if not Path(ruta).exists():
        return []
    registros = []
    with Path(ruta).open(encoding="utf-8") as fh:
        for linea in fh:
            if linea.strip():
                try:
                    registros.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
    return registros


def _estadisticas_local():
    """Carga la línea base local del piloto phase 1 (informe T49) por familia."""
    registros = _leer_jsonl(LOCAL_PILOTO_JSONL)
    por = {}
    for r in registros:
        familia = r.get("familia") or "(sin familia)"
        por.setdefault(familia, []).append(r)
    return por


def generar_informe(out_dir, meta=None):
    """Redacta docs/PILOTO_MERCURY.md a partir de piloto.jsonl."""
    out_dir = Path(out_dir)
    registros = _leer_jsonl(out_dir / "piloto.jsonl")
    meta = meta or {}

    lineas = ["# Piloto Mercury 3 — fase 1 (T83)", ""]
    lineas += [
        f"- Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
        f"- Backend: {BACKEND_MODEL} (reasoning_effort={REASONING_EFFORT}, "
        f"temperature={TEMPERATURE}, concurrencia <= 3)",
        f"- Tareas valoradas en piloto.jsonl: {len(registros)}",
    ]
    if meta.get("parada"):
        lineas.append(f"- **PARADA ANTICIPADA**: {meta['parada']}")
    lineas.append("")

    if not registros:
        lineas.append("Sin lecturas registradas: no se puede calcular aprobación.")
        (out_dir / "PILOTO_MERCURY.md").write_text(
            "\n".join(lineas) + "\n", encoding="utf-8")
        return "\n".join(lineas)

    lineas += [
        "El verificador es determinista (fase1_prompts.verificar_lectura). El",
        "veredicto humano de calidad se revisa aparte sobre 6 lecturas completas.",
        "",
        "## Aprobación por familia (Mercury vs local)",
        "",
        "| familia | n | ok | tasa | tasa 1er intento | local (ok/tasa) |",
        "|---|---|---|---|---|---|",
    ]
    local_por = _estadisticas_local()
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
        lrs = local_por.get(familia, [])
        lok = sum(1 for r in lrs if r.get("ok"))
        ltasa = f"{lok / len(lrs):.0%}" if lrs else "—"
        lineas.append(
            f"| {familia} | {len(rs)} | {ok} | {ok / len(rs):.0%} | "
            f"{primera / len(rs):.0%} | {lok}/{len(lrs) if lrs else '—'} ({ltasa}) |"
        )
    lineas.append(
        f"| **GLOBAL** | {total} | {ok_total} | {ok_total / total:.0%} | "
        f"{primera_total / total:.0%} | |"
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
    truncadas = sum(1 for r in registros if r.get("truncada"))
    m = meta.get("metricas", {})
    prompt_toks = m.get("prompt_tokens", 0)
    compl_toks = m.get("completion_tokens", 0)
    lineas += [
        "",
        "## Longitud, truncamiento y tokens",
        "",
        f"- Longitud (chars): media {_media(chars):.0f}, mín {min(chars)}, máx {max(chars)}",
        f"- Tiempo medio por lectura: {_media(segs):.1f} s (incluye reintentos)",
        f"- Lecturas truncadas: {truncadas} ({truncadas / total:.0%})",
        f"- Tokens (acumulados): prompt {prompt_toks}, completion {compl_toks}",
        "",
        "## Estimación para 10.270 lecturas",
        "",
        f"- Fórmula: 10.270 × tiempo medio / segundos por hora / workers.",
    ]
    seg_media = _media(segs)
    if seg_media > 0:
        for w in (3, 6):
            horas = 10270 * seg_media / 3600.0 / w
            dias = horas / 24.0
            lineas.append(f"- {w} workers: {horas:.1f} h ({dias:.1f} días) "
                          f"a {seg_media:.1f} s/lectura")
    else:
        lineas.append("- Sin datos de tiempo: no calculable.")
    texto = "\n".join(lineas) + "\n"
    (out_dir / "PILOTO_MERCURY.md").write_text(texto, encoding="utf-8")
    return texto


def main(argv=None):
    ap = argparse.ArgumentParser(description="Piloto de fase 1 con Mercury 3 (T83).")
    ap.add_argument("--n-por-familia", type=int, default=3)
    ap.add_argument("--semilla", type=int, default=83)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max-reintentos", type=int, default=1)
    ap.add_argument("--out-dir", default=FASE0_PILOTO)
    ap.add_argument("--simulado", action="store_true",
                    help="cliente simulado determinista (sin red, para tests)")
    args = ap.parse_args(argv)

    tareas = cargar_tareas(args.n_por_familia, args.semilla)
    print(f"Tareas piloto Mercury: {len(tareas)} ({args.n_por_familia} por "
          f"familia, semilla {args.semilla})", flush=True)

    cliente_factory = crear_cliente
    if args.simulado:
        from ejecutor_fase1 import simulacion_fase1

        def cliente_factory(familia, metricas=None, simulado=None):
            return crear_cliente(familia, metricas=metricas,
                                 simulado=simulacion_fase1)

    resumen = ejecutar_piloto(
        tareas, args.workers, max_reintentos=args.max_reintentos,
        out_dir=args.out_dir, cliente_factory=cliente_factory,
    )
    informe = generar_informe(args.out_dir, meta=resumen)
    print(f"\nResumen: {resumen['escritas']} escritas, "
          f"{resumen['procesadas']} procesadas, {resumen['errores']} errores, "
          f"{resumen['omitidos']} omitidas ya hechas.", flush=True)
    print(f"Piloto: {resumen['piloto']}\nInforme: "
          f"{Path(args.out_dir) / 'PILOTO_MERCURY.md'}", flush=True)
    if resumen["parada"]:
        print("AVISO: el piloto se detuvo por exceso de errores de red; "
              "revisar la API de Inception antes de reanudar.", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
