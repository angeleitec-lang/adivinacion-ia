#!/usr/bin/env python3
"""Ejecutor de la generación de fase 1 sobre jobs.db (T62).

Toma tareas `pending` de una jobs.db (ruta por argumento), reconstruye la
`tarea` canónica desde el payload, genera la lectura con
`fase1_prompts.construir_prompt`, la verifica con `verificar_lectura` y
reintenta (máx. N, con la causa del rechazo añadida al prompt). Las aceptadas
van a `aceptadas.jsonl` y las rechazadas a `rechazadas.jsonl` (una línea por
tarea, con id, prompt, respuesta, intentos y motivos de rechazo); en la BD se
marca `done`/`failed`. Los errores de red o salida vacía NO son rechazo: la
fila vuelve a `pending` (con `attempts` incrementada) para reintentarla en una
pasada posterior.

Reanudabilidad: al arrancar, las `running` más antiguas que
`--huerfano-minutos` vuelven a `pending`; una segunda pasada sobre una BD ya
procesada no hace nada (idempotencia). Un ctrl+c deja la BD consistente: las
tareas en vuelo de este worker vuelven a `pending`.

Seguridad: copia automática de la BD con marca de tiempo antes de la primera
escritura; `--dry-run` solo cuenta y estima horas; nunca escribe en
`corpus/final`.

max_tokens: el piloto (T49) usó 2048 y truncó las tiradas largas (cruz_celta
y lectura_completa al 0% de aprobación por respuestas cortadas). Este ejecutor
usa `max_tokens = max(job.max_tokens, --max-tokens-piso, tabla)`: el piso global
(--max-tokens-piso, 4096) se combina con el suelo por bloque de la tabla única
`fase1_prompts.RECOMENDACION_MAX_TOKENS` (T89: cruz_celta y lectura_completa
6144, espanola_7 5120, espanola_5 4096, espanola_3 2560, etc.). Ninguna fila
queda por debajo del piso y ninguna tirada larga se queda corta.

Latencia de referencia: 169,9 s/lectura (piloto T49, incluye reintentos, con
los nodos 10.0.0.3/10.0.0.4 saturados). La estimación del `--dry-run` usa ese
valor; el tiempo real variará según la carga de los nodos.

Modos: `--simulado` usa un lector simulado determinista (sin red): los nodos
están saturados y las pruebas de este track no consumen LLM real.

Formato de salida (D1, T75): por defecto se escribe el registro plano
histórico (`prompt_system`/`prompt_user`/`respuesta`). Con
`--formato sharegpt` las aceptadas se escriben ya en ShareGPT canónico
(`conversations` system/human/gpt en NFC, con `id`, `bloque` y `calculos`),
listas para consumir directamente por `validate_synthetic` sin adaptador
externo.

Validación recomendada en producción (D2, T75): el default de
`validate_synthetic` es `--min-chars 400`, adecuado para lecturas reales
completas; el lector simulado de este módulo genera respuestas breves, así
que el ensayo valida con `--min-chars 60`. En producción NO se baja el
umbral: validar con el default y, si una familia queda corta, subir la
verbosidad del prompt antes que relajar el filtro. Ejemplo:

    python validate_synthetic.py --dir <salida> --min-chars 400
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fase1_prompts as fp  # noqa: E402
from calculos import numerologia as calc_num  # noqa: E402
from fase1_piloto import limpiar_lectura, prompt_reintento  # noqa: E402
from llm_client import LLMClient  # noqa: E402

LATENCIA_PILOTO_S = 169.9
PISO_MAX_TOKENS = 4096
MOTIVO_TRUNCADO = (
    "respuesta_truncada: la lectura quedó cortada antes de cerrar; entrégala "
    "completa y terminada en puntuación."
)
CIERRE = set(".!?…»\"'")
TAROT_FAMILIAS = (
    "tarot_1", "tarot_2", "tarot_3", "cruz_celta", "tarot_pregunta", "multiturno",
)
_PREGUNTA_RE = re.compile(r'Pregunta(?:\s+del\s+consultante)?\s*:\s*"([^"]*)"')


# --------------------------------------------------------------------------- #
# Reconstrucción de la tarea desde la fila de jobs.db
# --------------------------------------------------------------------------- #
def extraer_pregunta(prompt):
    m = _PREGUNTA_RE.search(prompt or "")
    return m.group(1) if m else ""


def num_desde_payload(fecha, nombre):
    return {
        "camino_de_vida": calc_num.camino_de_vida(fecha),
        "expresion": calc_num.expresion(nombre),
        "alma": calc_num.reducir(calc_num.alma(nombre)),
        "personalidad": calc_num.reducir(calc_num.personalidad(nombre)),
        "anio_personal": calc_num.anio_personal(fecha, 2026),
    }


def universo_tarot(kb):
    return [c["nombre"] for c in kb["tarot"]["mayores"] + kb["tarot"]["menores"]]


def cargar_kb():
    import generate_tasks as gt

    return {
        "tarot": gt.load_kb("tarot.json"),
        "astrologia": gt.load_kb("astrologia.json"),
        "numerologia": gt.load_kb("numerologia.json"),
        "baraja": gt.load_kb("baraja_espanola.json"),
    }


def universo_baraja(kb):
    """Universo de la baraja española (40 naipes con sinónimos más los nombres del
    tarot como control de cartas ajenas); se cachea en la propia KB."""
    cache = kb.get("_universo_baraja")
    if cache is None:
        cache = fp.universo_baraja(kb["baraja"], kb["tarot"])
        kb["_universo_baraja"] = cache
    return cache


def tarea_desde_job(bloque, payload, pregunta, kb):
    """Convierte (bloque, payload, pregunta) en la `tarea` de fase1_prompts."""
    tarea = {"familia": bloque, "pregunta": pregunta}
    if bloque in TAROT_FAMILIAS:
        cartas = payload.get("cartas")
        if not cartas and payload.get("carta"):
            cartas = [payload["carta"]]
        tarea["cartas"] = [dict(c) for c in (cartas or [])]
        tarea["contexto"] = payload.get("contexto", "")
        tarea["universo_cartas"] = universo_tarot(kb)
        posiciones = list(payload.get("posiciones") or [])
        if posiciones:
            tarea["posiciones"] = posiciones
        tarea["calculos"] = {}
    elif bloque in fp.FAMILIAS_ESPAÑOLA:
        tarea["cartas"] = [dict(c) for c in payload.get("cartas", [])]
        tarea["mazo"] = payload.get("mazo", "espanol")
        tarea["contexto"] = payload.get("contexto", "")
        posiciones = list(payload.get("posiciones") or [])
        if posiciones:
            tarea["posiciones"] = posiciones
        tarea["universo_cartas"] = universo_baraja(kb)
        tarea["calculos"] = {}
    elif bloque == "astro_natal":
        tarea["ciudad"] = payload.get("ciudad", "")
        tarea["calculos"] = {"carta_natal": payload.get("carta") or {}}
    elif bloque == "sinastria":
        tarea["calculos"] = {
            "carta_a": payload.get("a") or {},
            "carta_b": payload.get("b") or {},
        }
    elif bloque == "numerologia":
        tarea["calculos"] = {
            "numerologia": num_desde_payload(payload["fecha"], payload["nombre"])
        }
    elif bloque == "lectura_completa":
        tarea["cartas"] = [dict(c) for c in payload.get("cartas", [])]
        tarea["contexto"] = payload.get("contexto", "")
        tarea["universo_cartas"] = universo_tarot(kb)
        tarea["nombre"] = payload.get("nombre", "")
        tarea["ciudad"] = payload.get("ciudad", "")
        tarea["calculos"] = {
            "carta_natal": payload.get("carta") or {},
            "numerologia": num_desde_payload(payload["fecha"], payload["nombre"]),
        }
    elif bloque == "etica":
        tarea["calculos"] = {}
    else:
        raise ValueError(f"bloque desconocido: {bloque}")
    return tarea


# --------------------------------------------------------------------------- #
# Detección de truncado
# --------------------------------------------------------------------------- #
def respuesta_truncada(texto):
    t = (texto or "").strip()
    if not t:
        return True
    return t[-1] not in CIERRE


# --------------------------------------------------------------------------- #
# Acceso a la BD (una conexión compartida con lock: workers en hilos)
# --------------------------------------------------------------------------- #
def _ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(db_path):
    con = sqlite3.connect(str(db_path), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def tabla_existe(con):
    r = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    return r is not None


def copiar_bd(db_path):
    destino = Path(f"{db_path}.copia-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(db_path, destino)
    return destino


def recuperar_huerfanas(con, minutos):
    corte = _iso(
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(minutes=minutos)
    )
    cur = con.execute(
        "UPDATE jobs SET status='pending', updated_at=? "
        "WHERE status='running' AND (updated_at IS NULL OR updated_at < ?)",
        (_ahora(), corte),
    )
    con.commit()
    return cur.rowcount


def reclamar(con, job_id, worker):
    cur = con.execute(
        "UPDATE jobs SET status='running', worker=?, attempts=attempts+1, updated_at=? "
        "WHERE id=? AND status='pending'",
        (worker, _ahora(), job_id),
    )
    con.commit()
    return cur.rowcount == 1


def marcar(con, job_id, status, error=None):
    con.execute(
        "UPDATE jobs SET status=?, error=?, updated_at=? WHERE id=?",
        (status, error, _ahora(), job_id),
    )
    con.commit()


def liberar_vuelo(con, worker):
    cur = con.execute(
        "UPDATE jobs SET status='pending', updated_at=? "
        "WHERE status='running' AND worker=?",
        (_ahora(), worker),
    )
    con.commit()
    return cur.rowcount


# --------------------------------------------------------------------------- #
# Procesamiento de una tarea
# --------------------------------------------------------------------------- #
def max_tokens_efectivo(fila, piso):
    bloque = fila.get("bloque", "")
    rec = fp.RECOMENDACION_MAX_TOKENS.get(bloque)
    efectivo = int(piso) if rec is None else max(int(piso), int(rec))
    return max(int(fila.get("max_tokens") or 1024), efectivo)


def procesar_una(fila, cliente, kb, max_reintentos=2, max_tokens_piso=PISO_MAX_TOKENS,
                temperature=0.2):
    """Una fila -> registro con lectura, veredicto e intentos.

    `error` distinto de None significa fallo de transporte (red/salida vacía):
    no es un rechazo del verificador.
    """
    payload = json.loads(fila["payload"]) if isinstance(fila["payload"], str) else fila["payload"]
    pregunta = extraer_pregunta(fila.get("prompt", ""))
    tarea = tarea_desde_job(fila["bloque"], payload, pregunta, kb)
    prompt = fp.construir_prompt(tarea, kb)
    max_tokens = max_tokens_efectivo(fila, max_tokens_piso)
    usuario = prompt["user"]
    intentos = 0
    previos = []
    t0 = time.monotonic()
    lectura = ""
    motivos = []
    ok = False
    error = None
    while True:
        intentos += 1
        try:
            raw = cliente.chat(
                prompt["system"], usuario,
                max_tokens=max_tokens, temperature=temperature, max_reintentos=0,
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
        ver_ok, ver_motivos = fp.verificar_lectura(tarea, lectura)
        motivos.extend(ver_motivos)
        ok = not motivos
        if ok or intentos > max_reintentos:
            break
        previos.extend(motivos)
        usuario = prompt_reintento(prompt["user"], motivos)
    return {
        "id": fila["id"],
        "bloque": fila["bloque"],
        "prompt_system": prompt["system"],
        "prompt_user": prompt["user"],
        "respuesta": lectura,
        "ok": bool(ok),
        "intentos": intentos,
        "motivos": list(motivos),
        "motivos_rechazo_previos": previos,
        "max_tokens": max_tokens,
        "segundos": round(time.monotonic() - t0, 3),
        "error": error,
        "payload": payload,
        "calculos": tarea.get("calculos") or {},
    }


def a_sharegpt(fila: dict) -> dict:
    """Convierte un registro plano del ejecutor a ShareGPT canónico (D1, T75).

    - `conversations`: system (si existe), human y gpt, con el texto en NFC.
    - conserva `id` y `bloque`: `merge_final` y `preparar_entrenamiento` leen
      `bloque` para la familia, y los ids numéricos no colisionan con 'eval-'.
    - conserva `calculos` si la fila los trae: `validate_synthetic` usa esa
      fuente canónica para el grounding (D7), igual que `verificar_lectura`.
    """
    def nfc(texto):
        return unicodedata.normalize("NFC", texto or "")

    conv = []
    if fila.get("prompt_system"):
        conv.append({"from": "system", "value": nfc(fila["prompt_system"])})
    conv.append({"from": "human", "value": nfc(fila.get("prompt_user", ""))})
    conv.append({"from": "gpt", "value": nfc(fila.get("respuesta", ""))})
    fila_out = {
        "conversations": conv,
        "id": fila.get("id"),
        "bloque": fila.get("bloque"),
    }
    if fila.get("calculos"):
        fila_out["calculos"] = fila["calculos"]
    return fila_out


# --------------------------------------------------------------------------- #
# Ejecución
# --------------------------------------------------------------------------- #
def proteger_final(ruta):
    partes = {p.lower() for p in Path(ruta).resolve().parts}
    if "final" in partes:
        raise ValueError("el ejecutor no escribe dentro de corpus/final")


def _escribir_jsonl(ruta, registro):
    with Path(ruta).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
        fh.flush()


def ejecutar(db_path, cliente, kb, workers=4, max_reintentos=2,
            max_tokens_piso=PISO_MAX_TOKENS, temperature=0.2, limite=0,
            huerfano_minutos=30.0, out_dir=None, stop_event=None,
            formato="plano"):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"no existe la BD: {db_path}")
    out_dir = Path(out_dir) if out_dir else db_path.parent / "salida_ejecutor_fase1"
    proteger_final(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aceptadas_path = out_dir / "aceptadas.jsonl"
    rechazadas_path = out_dir / "rechazadas.jsonl"

    copia = copiar_bd(db_path)
    con = conectar(db_path)
    if not tabla_existe(con):
        con.close()
        raise ValueError(f"la BD no tiene la tabla jobs: {db_path}")
    lock = threading.Lock()
    wid = f"{socket.gethostname()}:{os.getpid()}"
    resumen = {
        "copia": str(copia),
        "huerfanas_recuperadas": 0,
        "pendientes": 0,
        "procesadas": 0,
        "aceptadas": 0,
        "rechazadas": 0,
        "errores_red": 0,
        "omitidas": 0,
        "interrumpida": False,
    }
    try:
        with lock:
            resumen["huerfanas_recuperadas"] = recuperar_huerfanas(con, huerfano_minutos)
            sql = "SELECT id FROM jobs WHERE status='pending' ORDER BY id"
            if limite and limite > 0:
                sql += f" LIMIT {int(limite)}"
            ids = [r["id"] for r in con.execute(sql)]
        resumen["pendientes"] = len(ids)

        def uno(job_id):
            if stop_event is not None and stop_event.is_set():
                return
            with lock:
                reclamado = reclamar(con, job_id, wid)
            if not reclamado:
                with lock:
                    resumen["omitidas"] += 1
                return
            with lock:
                fila = dict(con.execute(
                    "SELECT * FROM jobs WHERE id=?", (job_id,)
                ).fetchone())
            try:
                registro = procesar_una(
                    fila, cliente, kb,
                    max_reintentos=max_reintentos,
                    max_tokens_piso=max_tokens_piso,
                    temperature=temperature,
                )
            except ValueError as exc:
                with lock:
                    marcar(con, job_id, "failed", f"bloque_invalido: {exc}")
                    _escribir_jsonl(rechazadas_path, {
                        "id": job_id, "bloque": fila.get("bloque"),
                        "motivos": [str(exc)],
                    })
                    resumen["procesadas"] += 1
                    resumen["rechazadas"] += 1
                return
            with lock:
                resumen["procesadas"] += 1
                if registro.get("error"):
                    con.execute(
                        "UPDATE jobs SET status='pending', error=?, updated_at=? "
                        "WHERE id=?",
                        (registro["error"], _ahora(), job_id),
                    )
                    con.commit()
                    resumen["errores_red"] += 1
                elif registro["ok"]:
                    marcar(con, job_id, "done")
                    fila_out = a_sharegpt(registro) if formato == "sharegpt" else registro
                    _escribir_jsonl(aceptadas_path, fila_out)
                    resumen["aceptadas"] += 1
                else:
                    marcar(con, job_id, "failed", "; ".join(registro["motivos"]))
                    _escribir_jsonl(rechazadas_path, registro)
                    resumen["rechazadas"] += 1

        if workers <= 1:
            for jid in ids:
                if stop_event is not None and stop_event.is_set():
                    break
                uno(jid)
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futuros = [ex.submit(uno, jid) for jid in ids]
                for f in as_completed(futuros):
                    f.result()
    except KeyboardInterrupt:
        resumen["interrumpida"] = True
        if stop_event is not None:
            stop_event.set()
        raise
    finally:
        with lock:
            resumen["liberadas_al_interrumpir"] = liberar_vuelo(con, wid)
        con.close()
    return resumen


# --------------------------------------------------------------------------- #
# Modo dry-run: solo cuenta y estima horas (sin tocar la BD)
# --------------------------------------------------------------------------- #
def estimar_dry_run(db_path, workers=4, latencia_s=LATENCIA_PILOTO_S):
    con = sqlite3.connect(str(db_path))
    if not tabla_existe(con):
        con.close()
        raise ValueError(f"la BD no tiene la tabla jobs: {db_path}")
    conteos = {r[0]: r[1] for r in con.execute(
        "SELECT status, COUNT(*) FROM jobs GROUP BY status"
    )}
    bloques = list(con.execute(
        "SELECT bloque, COUNT(*) FROM jobs WHERE status='pending' "
        "GROUP BY bloque ORDER BY bloque"
    ))
    con.close()
    n = conteos.get("pending", 0)
    horas = n * latencia_s / 3600.0 / max(1, workers)
    horas_por_bloque = {}
    print(f"Pendientes: {n} (por estado: {conteos})")
    for bloque, c in bloques:
        h = c * latencia_s / 3600.0 / max(1, workers)
        horas_por_bloque[bloque] = h
        print(f"  - {bloque}: {c} lecturas (~{h:.1f} h con {workers} workers)")
    print(
        f"Estimación: {n} lecturas x {latencia_s} s/lectura / {workers} workers "
        f"= {horas:.1f} h ({horas / 24:.1f} días)."
    )
    print(
        "Supuesto explícito: latencia de 169,9 s/lectura medida en el piloto T49 "
        "(incluye reintentos, nodos 10.0.0.3/10.0.0.4 saturados); el tiempo "
        "real variará con la carga de los nodos."
    )
    return {
        "pendientes": n,
        "conteos": conteos,
        "workers": workers,
        "latencia_s": latencia_s,
        "horas_estimadas": horas,
        "horas_por_bloque": horas_por_bloque,
    }


# --------------------------------------------------------------------------- #
# Lector simulado determinista (sin red): construye una lectura que pasa el
# verificador a partir de las cartas y los números que aparecen en el prompt.
# --------------------------------------------------------------------------- #
_SIM_CARTA_RE = re.compile(
    r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]*?)\s*\((al derecho|invertida)\)"
)
_SIM_NUM_RE = re.compile(
    r"(Camino de vida|Destino/expresión|Alma \(vocales\)|Personalidad \(consonantes\)"
    r"|Año personal 2026):\s*(\d+)"
)
_SIM_NUM_FRASES = {
    "Camino de vida": "camino de vida {}",
    "Destino/expresión": "expresión {}",
    "Alma (vocales)": "alma {}",
    "Personalidad (consonantes)": "personalidad {}",
    "Año personal 2026": "año personal {}",
}


def _sim_cartas(usuario):
    vistos = {}
    for m in _SIM_CARTA_RE.finditer(usuario or ""):
        nombre = m.group(1).strip()
        inv = m.group(2) == "invertida"
        clave = fp._norm(nombre)
        if clave and clave not in vistos:
            vistos[clave] = (nombre, inv)
    return list(vistos.values())


def _sim_numeros(usuario):
    frases = []
    for m in _SIM_NUM_RE.finditer(usuario or ""):
        plantilla = _SIM_NUM_FRASES.get(m.group(1))
        if plantilla:
            frases.append(plantilla.format(m.group(2)))
    return frases


_SIM_EJE_RE = re.compile(
    r"^\s*-\s*(Sol|Luna|Ascendente):\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)", re.M
)


def _sim_ejes(usuario):
    """Ejes astrales del prompt («- Sol: Aries ...») como «Sol en Aries».

    El lector simulado los menciona para que el grounding (por texto o por
    `calculos`, D7) encuentre los signos; al copiarlos del prompt generado
    desde la carta, nunca contradice a `_verif_sol`.
    """
    vistos = {}
    for m in _SIM_EJE_RE.finditer(usuario or ""):
        clave = (m.group(1), fp._norm(m.group(2)))
        if clave not in vistos:
            vistos[clave] = f"{m.group(1)} en {m.group(2)}"
    return list(vistos.values())


_SIM_ESQUEMA_RE = re.compile(
    r"(?m)^#{1,6}[ \t]*(\d+)[.)][ \t]+(.+?)[ \t]+—[ \t]+(.+?)[ \t]*\((al derecho|invertida)\)[ \t]*$"
)


def _sim_esquema_cabeceras(usuario):
    """Cabeceras del esquema obligatorio del prompt: [(n, posición, carta, invertida)]."""
    cabeceras = []
    for m in _SIM_ESQUEMA_RE.finditer(usuario or ""):
        cabeceras.append(
            (int(m.group(1)), m.group(2).strip(), m.group(3).strip(), m.group(4) == "invertida")
        )
    return cabeceras


def _sim_frase_carta(nombre, inv):
    if inv:
        return f"La carta {nombre} aparece invertida y pide mirar ese bloqueo con calma"
    return f"La carta {nombre} sale al derecho y acompaña tu momento con claridad"


_SIM_SINTESIS_CIERRE = "Esta lectura orienta, no sentencia: cuídate y decide con calma."


def _sim_posicion(nombre, inv):
    frase = _sim_frase_carta(nombre, inv)
    if inv:
        return (
            f"En esta posición, {frase}; no fuerces la salida, dale su tiempo a lo que "
            "trae y observa qué es lo que bloquea el paso."
        )
    return (
        f"En esta posición, {frase}; apóyate en lo que trae y dale forma a tu decisión "
        "con calma, sin adelantarte a los tiempos de los demás."
    )


def _sim_sintesis():
    return (
        "Sumadas, las cartas dibujadas forman un cuadro que puedes manejar con calma: "
        "quédate con lo que más te hable hoy y da el paso pequeño que te pida. "
        + _SIM_SINTESIS_CIERRE
    )


def _sim_tirada_esquema(cabeceras):
    """Lectura con las cabeceras `## n. posición — carta (orientación)` del esquema."""
    partes = [
        f"## {num}. {pos} — {nombre} ({'invertida' if inv else 'al derecho'})\n\n"
        + _sim_posicion(nombre, inv)
        for num, pos, nombre, inv in cabeceras
    ]
    partes.append("## Síntesis\n\n" + _sim_sintesis())
    return "\n\n".join(partes)


def _sim_lectura_completa(usuario):
    """Lectura de cuatro secciones: Carta natal / Tirada / Numerología / Síntesis."""
    ejes = _sim_ejes(usuario)
    cielo = (
        "En el cielo consultado, " + ", ".join(ejes) + " dan el marco de la lectura. "
        if ejes else ""
    )
    secciones = [
        "## Carta natal\n\n" + cielo +
        "Es el fondo estable sobre el que caen las cartas: tómalo como contexto, "
        "no como destino.",
    ]
    cartas = _sim_cartas(usuario)
    if cartas:
        tirada = "; ".join(_sim_frase_carta(nombre, inv) for nombre, inv in cartas) + "."
    else:
        tirada = "Las cartas acompañan tu momento con claridad y piden calma."
    secciones.append("## Tirada de tres cartas\n\n" + tirada)
    numeros = _sim_numeros(usuario)
    if numeros:
        num_txt = " ".join(
            f"En lo numérico, el {frase} marca el ritmo de esta etapa." for frase in numeros
        )
    else:
        num_txt = "En lo numérico, el ritmo de esta etapa se lee con calma."
    secciones.append("## Numerología\n\n" + num_txt)
    secciones.append("## Síntesis\n\n" + _sim_sintesis())
    return "\n\n".join(secciones)


def simulacion_fase1(sistema, usuario):
    if "cuatro secciones" in (usuario or ""):
        return _sim_lectura_completa(usuario)
    if "ESQUEMA OBLIGATORIO" in (usuario or ""):
        cabeceras = _sim_esquema_cabeceras(usuario)
        if cabeceras:
            return _sim_tirada_esquema(cabeceras)
    cartas = _sim_cartas(usuario)
    frases = []
    if cartas:
        partes = [_sim_frase_carta(nombre, inv) for nombre, inv in cartas]
        frases.append("; ".join(partes) + ".")
    ejes = _sim_ejes(usuario)
    if ejes:
        frases.append(
            "En el cielo consultado, " + ", ".join(ejes) + " dan el marco de la lectura."
        )
    for frase in _sim_numeros(usuario):
        frases.append(f"En lo numérico, el {frase} marca el ritmo de esta etapa.")
    if not frases:
        frases.append(
            "Te escucho con atención y acompaño tu consulta con honestidad."
        )
    frases.append(_SIM_SINTESIS_CIERRE)
    return " ".join(frases)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Ejecutor de fase 1 sobre jobs.db (T62, reanudable)."
    )
    ap.add_argument("--db", required=True, help="ruta a la jobs.db (copia de trabajo)")
    ap.add_argument("--out-dir", default=None,
                    help="directorio de salida (por defecto <db>_salida)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-reintentos", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="timeout por petición al nodo (s)")
    ap.add_argument("--max-tokens-piso", type=int, default=PISO_MAX_TOKENS,
                    help="piso global de max_tokens; el suelo por bloque sale de la "
                         "tabla fase1_prompts.RECOMENDACION_MAX_TOKENS (cruz_celta/"
                         "lectura_completa 6144, espanola_7 5120, etc.)")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--limite", type=int, default=0,
                    help="máximo de tareas a procesar en esta pasada (0 = sin límite)")
    ap.add_argument("--huerfano-minutos", type=float, default=30.0,
                    help="running más antiguas que esto vuelven a pending")
    ap.add_argument("--simulado", action="store_true",
                    help="lector simulado determinista (sin red, no consume LLM)")
    ap.add_argument("--formato", choices=("plano", "sharegpt"), default="plano",
                    help="formato de aceptadas.jsonl: registro plano historico "
                         "(por defecto) o ShareGPT canonico con bloque, id y "
                         "calculos (D1, T75)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo cuenta pendientes y estima horas; no escribe nada")
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoints", default=None,
                    help="URLs separadas por coma (por defecto las de llm_client)")
    args = ap.parse_args(argv)

    if args.dry_run:
        estimar_dry_run(args.db, workers=args.workers)
        return 0

    kb = cargar_kb()
    if args.simulado:
        cliente = LLMClient(simulado=simulacion_fase1)
    else:
        endpoints = args.endpoints.split(",") if args.endpoints else None
        cliente = LLMClient(endpoints=endpoints, timeout=args.timeout)
        if args.model:
            cliente.model = args.model

    stop_event = threading.Event()
    try:
        resumen = ejecutar(
            args.db, cliente, kb,
            workers=args.workers,
            max_reintentos=args.max_reintentos,
            max_tokens_piso=args.max_tokens_piso,
            temperature=args.temperature,
            limite=args.limite,
            huerfano_minutos=args.huerfano_minutos,
            out_dir=args.out_dir,
            stop_event=stop_event,
            formato=args.formato,
        )
    except KeyboardInterrupt:
        print("Interrumpido: las tareas en vuelo de este worker han vuelto a "
              "pending (BD consistente).", flush=True)
        return 130
    print(
        f"Copia de BD: {resumen['copia']}\n"
        f"Huérfanas recuperadas: {resumen['huerfanas_recuperadas']}\n"
        f"Pendientes al inicio: {resumen['pendientes']}\n"
        f"Procesadas: {resumen['procesadas']} | Aceptadas: {resumen['aceptadas']} | "
        f"Rechazadas: {resumen['rechazadas']} | Errores de red: {resumen['errores_red']} | "
        f"Omitidas: {resumen['omitidas']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
