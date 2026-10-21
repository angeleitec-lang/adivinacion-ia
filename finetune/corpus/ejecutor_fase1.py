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

Backends (T95): `--backend local` (por defecto) usa el cliente local de
`llm_client`; `--backend mercury` usa el backend en la nube Mercury 3
(`INCEPTION_API_KEY`, `reasoning_effort=instant`, presupuesto por familia de
`RECOMENDACION_MAX_TOKENS`, concurrencia y tasa configurables, backoff ante
429). Cada fila aceptada lleva `generador: "local"` o `"mercury-3"` para poder
auditar el origen. La clave se lee solo de la variable de entorno y nunca se
escribe en logs ni en las salidas.

Seguridad de ejecución (T95): una ventana de las últimas
`--ventana-errores` (50) tareas detiene la pasada si la proporción de errores
de red supera `--umbral-error` (0,20); las tareas no reclamadas quedan
`pending`. `--solo-estimar` cuenta pendientes por familia y estima tokens y
horas para local y Mercury sin tocar la BD ni crear copias.

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
import collections
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
LATENCIA_MERCURY_S = 4.1
PISO_MAX_TOKENS = 4096
BACKEND_URL_MERCURY = "https://api.inceptionlabs.ai/v1"
BACKEND_MODEL_MERCURY = "mercury-3"
API_KEY_ENV_MERCURY = "INCEPTION_API_KEY"
REASONING_EFFORT_MERCURY = "instant"
TEMPERATURE_MERCURY = 0.5
TIMEOUT_MERCURY_S = 180.0
TASA_MAX_POR_MINUTO_MERCURY = 60
MAX_COMPLETION_TOKENS_DEFECTO = 6144
MAX_WORKERS_MERCURY = 3
REINTENTOS_RED_MERCURY = 3
ENDPOINT_LOCAL_DEFECTO = "http://10.0.0.4:8000/v1"
GENERADOR_LOCAL = "local"
GENERADOR_MERCURY = "mercury-3"
UMBRAL_ERROR_DEFECTO = 0.20
VENTANA_ERRORES_DEFECTO = 50
TOKENS_PROMPT_MEDIA = 840
TOKENS_COMPLETION_MEDIA = 1282
PRECIO_MERCURY_INPUT_USD_MILLON = 0.10
PRECIO_MERCURY_OUTPUT_USD_MILLON = 0.35
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


def _campo_payload(payload, clave, bloque):
    """Campo obligatorio del payload con error claro si falta."""
    if clave not in payload or payload[clave] in (None, ""):
        raise ValueError(f"payload incompleto para bloque {bloque}: falta '{clave}'")
    return payload[clave]


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
            "numerologia": num_desde_payload(
                _campo_payload(payload, "fecha", bloque),
                _campo_payload(payload, "nombre", bloque),
            )
        }
    elif bloque == "lectura_completa":
        tarea["cartas"] = [dict(c) for c in payload.get("cartas", [])]
        tarea["contexto"] = payload.get("contexto", "")
        tarea["universo_cartas"] = universo_tarot(kb)
        tarea["nombre"] = payload.get("nombre", "")
        tarea["ciudad"] = payload.get("ciudad", "")
        tarea["calculos"] = {
            "carta_natal": payload.get("carta") or {},
            "numerologia": num_desde_payload(
                _campo_payload(payload, "fecha", bloque),
                _campo_payload(payload, "nombre", bloque),
            ),
        }
    elif bloque == "etica":
        tarea["calculos"] = {}
    elif bloque == "transitos":
        tarea["foco"] = payload.get("foco", "")
        tarea["ciudad"] = payload.get("ciudad", "")
        tarea["pais"] = payload.get("pais", "")
        tarea["calculos"] = {
            "carta_natal": payload.get("carta") or {},
            "transitos": payload.get("transitos") or {},
        }
    elif bloque == "revolucion_solar":
        tarea["ciudad"] = payload.get("ciudad", "")
        tarea["pais"] = payload.get("pais", "")
        tarea["calculos"] = {
            "carta_natal": payload.get("carta") or {},
            "revolucion_solar": payload.get("revolucion_solar") or {},
        }
    elif bloque == "biorritmos":
        tarea["fecha_nacimiento"] = _campo_payload(payload, "fecha_nacimiento", bloque)
        tarea["hora"] = payload.get("hora", "")
        tarea["calculos"] = {"biorritmos": payload.get("biorritmos") or {}}
    elif bloque == "fuera_alcance":
        tarea["tecnica"] = payload.get("tecnica", "")
        tarea["calculos"] = {}
    else:
        raise ValueError(f"bloque desconocido: {bloque}")
    if "universo_cartas" not in tarea:
        # Lecturas sin tirada: cualquier carta de tarot mencionada es ajena.
        tarea["universo_cartas"] = universo_tarot(kb)
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


def copiar_bd(db_path, con=None, maximo=5):
    """Copia la BD solo si quedan pendientes y rota las últimas `maximo` copias."""
    propia = con is None
    if propia:
        con = sqlite3.connect(str(db_path))
    try:
        pendientes = con.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    finally:
        if propia:
            con.close()
    if not pendientes:
        return None
    destino = Path(f"{db_path}.copia-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(db_path, destino)
    copias = sorted(Path(db_path).parent.glob(Path(db_path).name + ".copia-*"))
    for vieja in copias[:-max(int(maximo), 1)]:
        try:
            vieja.unlink()
        except OSError:
            pass
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


def validar_clave_mercury():
    """Comprueba que la clave de Mercury exista en el entorno.

    Nunca devuelve ni imprime el valor; solo nombra la variable que falta.
    """
    if not os.environ.get(API_KEY_ENV_MERCURY):
        raise RuntimeError(
            "Falta la variable de entorno %s para usar --backend mercury; "
            "defínela antes de ejecutar (la clave no se lee de ficheros)."
            % API_KEY_ENV_MERCURY)


def crear_cliente_mercury(simulado=None, max_concurrencia=MAX_WORKERS_MERCURY,
                          tasa_max_por_minuto=TASA_MAX_POR_MINUTO_MERCURY,
                          timeout=TIMEOUT_MERCURY_S, model=BACKEND_MODEL_MERCURY,
                          metricas=None):
    """Construye el LLMClient del backend Mercury 3 (T95).

    La clave se toma exclusivamente de `INCEPTION_API_KEY` (sin caer a
    `auth.json`) y solo se comprueba aquí; con `simulado` no hace falta clave.
    """
    if simulado is None:
        validar_clave_mercury()
    return LLMClient(
        endpoints=[{
            "url": BACKEND_URL_MERCURY,
            "model": model,
            "api_key_env": API_KEY_ENV_MERCURY,
        }],
        timeout=timeout,
        simulado=simulado,
        max_concurrencia=max(int(max_concurrencia), 1),
        tasa_max_por_minuto=tasa_max_por_minuto,
        metricas=metricas,
        reasoning_effort=REASONING_EFFORT_MERCURY,
        max_completion_tokens=None,
    )


def max_tokens_mercury(bloque):
    """Presupuesto de completion por familia para Mercury (tabla T89)."""
    return int(fp.RECOMENDACION_MAX_TOKENS.get(bloque, MAX_COMPLETION_TOKENS_DEFECTO))


def procesar_una(fila, cliente, kb, max_reintentos=2, max_tokens_piso=PISO_MAX_TOKENS,
                temperature=0.2, backend=GENERADOR_LOCAL, reintentos_red=None,
                generador=None):
    """Una fila -> registro con lectura, veredicto e intentos.

    `error` distinto de None significa fallo de transporte (red/salida vacía):
    no es un rechazo del verificador. En Mercury se envía el presupuesto por
    familia en `max_completion_tokens`; en local se mantiene el cálculo
    histórico de `max_tokens` con piso.
    """
    payload = json.loads(fila["payload"]) if isinstance(fila["payload"], str) else fila["payload"]
    pregunta = extraer_pregunta(fila.get("prompt", ""))
    tarea = tarea_desde_job(fila["bloque"], payload, pregunta, kb)
    prompt = fp.construir_prompt(tarea, kb)
    es_mercury = backend == GENERADOR_MERCURY
    if es_mercury:
        max_tokens = max_tokens_mercury(fila["bloque"])
        tope_completion = max_tokens
        if reintentos_red is None:
            reintentos_red = REINTENTOS_RED_MERCURY
    else:
        max_tokens = max_tokens_efectivo(fila, max_tokens_piso)
        tope_completion = None
        if reintentos_red is None:
            reintentos_red = 0
    if generador is None:
        generador = GENERADOR_MERCURY if es_mercury else GENERADOR_LOCAL
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
            kwargs = {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "max_reintentos": reintentos_red,
            }
            if tope_completion is not None:
                kwargs["max_completion_tokens"] = tope_completion
            raw = cliente.chat(prompt["system"], usuario, **kwargs)
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
        "generador": generador,
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
    - conserva `generador` (T95) para auditar si la lectura vino de local o
      de Mercury.
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
    fila_out["generador"] = fila.get("generador") or GENERADOR_LOCAL
    return fila_out


# --------------------------------------------------------------------------- #
# Ejecución
# --------------------------------------------------------------------------- #
def proteger_final(ruta):
    partes = {p.lower() for p in Path(ruta).resolve().parts}
    if "final" in partes:
        raise ValueError("el ejecutor no escribe dentro de corpus/final")


def _escribir_jsonl(ruta, registro):
    """Añade una línea y fuerza su persistencia (append + fsync)."""
    with Path(ruta).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def ejecutar(db_path, cliente, kb, workers=4, max_reintentos=2,
            max_tokens_piso=PISO_MAX_TOKENS, temperature=0.2, limite=0,
            huerfano_minutos=30.0, out_dir=None, stop_event=None,
            formato="plano", backend=GENERADOR_LOCAL, reintentos_red=None,
            ventana_errores=VENTANA_ERRORES_DEFECTO,
            umbral_error=UMBRAL_ERROR_DEFECTO):
    if backend not in (GENERADOR_LOCAL, GENERADOR_MERCURY):
        raise ValueError(
            f"backend no válido: {backend!r}; usa {GENERADOR_LOCAL!r} o "
            f"{GENERADOR_MERCURY!r}")
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"no existe la BD: {db_path}")
    out_dir = Path(out_dir) if out_dir else db_path.parent / "salida_ejecutor_fase1"
    proteger_final(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    aceptadas_path = out_dir / "aceptadas.jsonl"
    rechazadas_path = out_dir / "rechazadas.jsonl"

    con = conectar(db_path)
    if not tabla_existe(con):
        con.close()
        raise ValueError(f"la BD no tiene la tabla jobs: {db_path}")
    copia = copiar_bd(db_path, con)
    lock = threading.Lock()
    wid = f"{socket.gethostname()}:{os.getpid()}"
    resumen = {
        "copia": str(copia) if copia else None,
        "huerfanas_recuperadas": 0,
        "pendientes": 0,
        "procesadas": 0,
        "aceptadas": 0,
        "rechazadas": 0,
        "errores_red": 0,
        "omitidas": 0,
        "interrumpida": False,
        "backend": backend,
        "parada": None,
        "no_procesadas_por_parada": 0,
    }
    ventana_max = max(int(ventana_errores), 1)
    ventana = collections.deque(maxlen=ventana_max)
    parada = threading.Event()

    def detenido():
        return parada.is_set() or (stop_event is not None and stop_event.is_set())

    def anotar_resultado(fallo, red=False):
        """Ventana móvil de fallos (red o verificador) frente al umbral.

        Con menos tareas que `ventana_errores` la muestra efectiva baja al
        total de pendientes (si no, nunca se evaluaría). Los rechazos del
        verificador se reportan en `parada` pero no abortan la pasada en
        curso; los errores de red sí (el nodo puede estar caído).
        """
        ventana.append(2 if red else (1 if fallo else 0))
        objetivo = min(ventana_max, max(1, resumen["pendientes"]))
        if len(ventana) < objetivo:
            return
        fallos = sum(1 for x in ventana if x)
        proporcion = fallos / len(ventana)
        if proporcion > umbral_error and resumen["parada"] is None:
            resumen["parada"] = (
                f"fallos {fallos}/{len(ventana)} "
                f"({proporcion:.0%}) > {umbral_error:.0%}"
            )
            if any(x == 2 for x in ventana):
                parada.set()
                if stop_event is not None:
                    stop_event.set()

    ids = []
    try:
        with lock:
            resumen["huerfanas_recuperadas"] = recuperar_huerfanas(con, huerfano_minutos)
            sql = "SELECT id FROM jobs WHERE status='pending' ORDER BY id"
            if limite and limite > 0:
                sql += f" LIMIT {int(limite)}"
            ids = [r["id"] for r in con.execute(sql)]
        resumen["pendientes"] = len(ids)

        def uno(job_id):
            if detenido():
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
                    backend=backend,
                    reintentos_red=reintentos_red,
                    generador=(GENERADOR_MERCURY if backend == GENERADOR_MERCURY
                               else GENERADOR_LOCAL),
                )
            except (ValueError, KeyError, TypeError) as exc:
                with lock:
                    marcar(con, job_id, "failed", f"bloque_invalido: {exc}")
                    _escribir_jsonl(rechazadas_path, {
                        "id": job_id, "bloque": fila.get("bloque"),
                        "motivos": [str(exc)],
                    })
                    resumen["procesadas"] += 1
                    resumen["rechazadas"] += 1
                    anotar_resultado(True, red=False)
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
                fallo = bool(registro.get("error")) or not registro.get("ok")
                anotar_resultado(fallo, red=bool(registro.get("error")))

        if workers <= 1:
            for jid in ids:
                if detenido():
                    break
                uno(jid)
        else:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                pendientes = iter(ids)
                futuros = {}

                def enviar():
                    while len(futuros) < workers and not detenido():
                        try:
                            jid = next(pendientes)
                        except StopIteration:
                            break
                        futuros[ex.submit(uno, jid)] = jid

                enviar()
                while futuros:
                    for f in as_completed(list(futuros)):
                        jid = futuros.pop(f)
                        try:
                            f.result()
                        except Exception as exc:
                            with lock:
                                marcar(con, jid, "failed",
                                       f"excepcion:{type(exc).__name__}: {exc}")
                                resumen["procesadas"] += 1
                                resumen["rechazadas"] += 1
                                anotar_resultado(True, red=False)
                        enviar()
                        break
    except KeyboardInterrupt:
        resumen["interrumpida"] = True
        if stop_event is not None:
            stop_event.set()
        raise
    finally:
        with lock:
            resumen["liberadas_al_interrumpir"] = liberar_vuelo(con, wid)
            if resumen["parada"] or resumen["interrumpida"]:
                resumen["no_procesadas_por_parada"] = max(
                    0, len(ids) - resumen["procesadas"])
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


def estimar_backends(db_path, workers_local=4, workers_mercury=MAX_WORKERS_MERCURY,
                     latencia_local=LATENCIA_PILOTO_S,
                     latencia_mercury=LATENCIA_MERCURY_S):
    """`--solo-estimar`: pendientes por familia, tokens y horas por backend.

    No escribe en la BD ni crea copias: abre la BD en modo lectura. Los tokens
    de entrada/salida son la media observada en el piloto T83 (840 / 1282 por
    lectura) y el «techo» de salida usa el presupuesto por familia. El coste de
    Mercury es una estimación con los precios de lanzamiento de T83.
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    if not tabla_existe(con):
        con.close()
        raise ValueError(f"la BD no tiene la tabla jobs: {db_path}")
    filas = list(con.execute(
        "SELECT bloque, COUNT(*) FROM jobs WHERE status='pending' "
        "GROUP BY bloque ORDER BY bloque"
    ))
    conteos = {r[0]: r[1] for r in con.execute(
        "SELECT status, COUNT(*) FROM jobs GROUP BY status"
    )}
    con.close()
    total = sum(c for _, c in filas)
    por_bloque = {}
    techo_salida = 0
    print(f"Pendientes: {total} (por estado: {conteos})")
    print(f"{'familia':<20} {'pendientes':>10} {'max_completion':>15} "
          f"{'techo salida':>14}")
    for bloque, c in filas:
        tope = max_tokens_mercury(bloque)
        techo = c * tope
        techo_salida += techo
        por_bloque[bloque] = {
            "pendientes": c,
            "max_completion": tope,
            "techo_tokens_salida": techo,
        }
        print(f"{bloque:<20} {c:>10} {tope:>15} {techo:>14}")

    entrada = total * TOKENS_PROMPT_MEDIA
    salida_media = total * TOKENS_COMPLETION_MEDIA
    resumen = {
        "pendientes": total,
        "conteos": conteos,
        "por_bloque": por_bloque,
        "tokens_entrada_estimados": entrada,
        "tokens_salida_estimados": salida_media,
        "tokens_salida_techo": techo_salida,
    }
    for clave, nombre, workers, latencia in (
        ("local", GENERADOR_LOCAL, workers_local, latencia_local),
        ("mercury", GENERADOR_MERCURY, workers_mercury, latencia_mercury),
    ):
        horas = total * latencia / 3600.0 / max(1, workers)
        datos = {
            "workers": workers,
            "latencia_s": latencia,
            "horas": horas,
        }
        if clave == "mercury":
            datos["coste_usd"] = (
                entrada / 1_000_000 * PRECIO_MERCURY_INPUT_USD_MILLON
                + salida_media / 1_000_000 * PRECIO_MERCURY_OUTPUT_USD_MILLON
            )
        resumen[clave] = datos
        extra = (f", coste ~${datos['coste_usd']:.2f}"
                 if "coste_usd" in datos else "")
        print(
            f"{nombre}: {total} lecturas x {latencia} s / {workers} workers "
            f"= ~{horas:.1f} h{extra}"
        )
    print(
        f"Tokens estimados: entrada ~{entrada:,} + salida media ~{salida_media:,} "
        f"(techo de salida {techo_salida:,})."
    )
    print(
        "Supuestos: latencias del piloto (local 169,9 s/lectura T49; Mercury "
        "4,1 s/lectura T83) y 840/1282 tokens por lectura (T83)."
    )
    return resumen


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


def _sim_transitos(usuario):
    triples = re.findall(
        r"- (\w+) en tránsito hace (\w+) a su (\w+) natal", usuario or "")
    frases = []
    if triples:
        eco = "; ".join(
            f"{t} en tránsito hace {a} a su {n} natal" for t, a, n in triples[:4])
        frases.append(f"Los tránsitos del día marcan el clima actual: {eco}.")
    ejes = _sim_ejes(usuario)
    if ejes:
        frases.append(
            "En tu carta natal, " + ", ".join(ejes) + " reciben ese clima.")
    frases.append(_SIM_SINTESIS_CIERRE)
    return " ".join(frases)


def _sim_revolucion(usuario):
    sol = re.search(r"Sol RS en (\w+)", usuario or "")
    asc = re.search(r"Ascendente RS (\w+)", usuario or "")
    frases = []
    if sol:
        frases.append(
            f"En tu revolución solar, el Sol RS en {sol.group(1)} da el tono "
            "del año que empieza.")
    if asc:
        frases.append(
            f"El Ascendente RS {asc.group(1)} pinta el escenario en el que te mueves.")
    ejes = _sim_ejes(usuario)
    if ejes:
        frases.append(
            "Todo ello cae sobre tu carta natal, donde " + ", ".join(ejes)
            + " marcan el fondo.")
    frases.append(_SIM_SINTESIS_CIERRE)
    return " ".join(frases)


def _sim_biorritmos(usuario):
    ciclos = re.findall(
        r"- (F[íi]sico|Emocional|Intelectual): (\d+)% \(([^)]+)\)", usuario or "")
    frases = []
    if ciclos:
        eco = "; ".join(f"{n} al {p}% ({f})" for n, p, f in ciclos)
        frases.append(f"Tus ciclos hoy: {eco}.")
    frases.append(
        "Con esta foto de tus biorritmos, coloca las tareas que exijan más "
        "energía cuando el ciclo correspondente te acompañe.")
    frases.append(_SIM_SINTESIS_CIERRE)
    return " ".join(frases)


def _sim_fuera_alcance(usuario):
    return (
        "Esa técnica no forma parte de mi alcance, así que no voy a inventar "
        "datos sobre ella. Sí puedo acompañarte con tarot, baraja española, "
        "astrología o numerología: si te apetece, pregúntame por una de esas "
        "técnicas y lo miramos con calma. " + _SIM_SINTESIS_CIERRE
    )


def simulacion_fase1(sistema, usuario):
    if "cuatro secciones" in (usuario or ""):
        return _sim_lectura_completa(usuario)
    if "ESQUEMA OBLIGATORIO" in (usuario or ""):
        cabeceras = _sim_esquema_cabeceras(usuario)
        if cabeceras:
            return _sim_tirada_esquema(cabeceras)
    if "Lectura de tránsitos" in (usuario or ""):
        return _sim_transitos(usuario)
    if "Lectura de revolución solar" in (usuario or ""):
        return _sim_revolucion(usuario)
    if "Lectura de biorritmos" in (usuario or ""):
        return _sim_biorritmos(usuario)
    if "fuera de alcance" in (usuario or ""):
        return _sim_fuera_alcance(usuario)
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
                    help="directorio de salida (por defecto "
                         "<carpeta_de_la_bd>/salida_ejecutor_fase1)")
    ap.add_argument("--backend", choices=("local", "mercury"),
                    default="local",
                    help="local (por defecto) o mercury (API en la nube)")
    ap.add_argument("--workers", type=int, default=None,
                    help="hilos concurrentes (local 4, mercury 3 por defecto)")
    ap.add_argument("--max-reintentos", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=None,
                    help="timeout por petición (s); local 300, mercury 180")
    ap.add_argument("--max-tokens-piso", type=int, default=PISO_MAX_TOKENS,
                    help="piso global de max_tokens; el suelo por bloque sale de la "
                         "tabla fase1_prompts.RECOMENDACION_MAX_TOKENS (cruz_celta/"
                         "lectura_completa 6144, espanola_7 5120, etc.)")
    ap.add_argument("--temperature", type=float, default=None,
                    help="temperatura (local 0.2, mercury 0.5)")
    ap.add_argument("--limite", type=int, default=0,
                    help="máximo de tareas a procesar en esta pasada (0 = sin límite)")
    ap.add_argument("--huerfano-minutos", type=float, default=30.0,
                    help="running más antiguas que esto vuelven a pending; "
                         "0 recupera todas al reanudar (útil si ningún worker "
                         "antiguo sigue vivo)")
    ap.add_argument("--simulado", action="store_true",
                    help="lector simulado determinista (sin red, no consume LLM)")
    ap.add_argument("--formato", choices=("plano", "sharegpt"), default="plano",
                    help="formato de aceptadas.jsonl: registro plano historico "
                         "(por defecto) o ShareGPT canonico con bloque, id y "
                         "calculos (D1, T75)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo cuenta pendientes y estima horas; no escribe nada")
    ap.add_argument("--solo-estimar", action="store_true",
                    help="pendientes por familia, tokens y horas de local y "
                         "mercury; no escribe ni copia la BD")
    ap.add_argument("--ventana-errores", type=int,
                    default=VENTANA_ERRORES_DEFECTO,
                    help="tamaño de la ventana móvil de errores (50)")
    ap.add_argument("--umbral-error", type=float, default=UMBRAL_ERROR_DEFECTO,
                    help="proporción de errores que detiene la pasada (0.20)")
    ap.add_argument("--tasa-max-por-minuto", type=int,
                    default=TASA_MAX_POR_MINUTO_MERCURY,
                    help="límite de peticiones/minuto en mercury (60)")
    ap.add_argument("--reintentos-red", type=int, default=None,
                    help="reintentos de red por tarea (mercury 3, local 0)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoints", default=None,
                    help="URLs locales separadas por coma (por defecto solo "
                         "el nodo2: %s)" % ENDPOINT_LOCAL_DEFECTO)
    args = ap.parse_args(argv)

    es_mercury = args.backend == "mercury"
    backend = GENERADOR_MERCURY if es_mercury else GENERADOR_LOCAL
    workers = args.workers if args.workers is not None else (
        MAX_WORKERS_MERCURY if es_mercury else 4)
    temperature = args.temperature if args.temperature is not None else (
        TEMPERATURE_MERCURY if es_mercury else 0.2)
    timeout = args.timeout if args.timeout is not None else (
        TIMEOUT_MERCURY_S if es_mercury else 300.0)

    if args.solo_estimar:
        trabajadores_mercury = (args.workers if args.workers is not None
                                else MAX_WORKERS_MERCURY)
        trabajadores_local = args.workers if args.workers is not None else 4
        estimar_backends(args.db, workers_local=trabajadores_local,
                         workers_mercury=trabajadores_mercury)
        return 0
    if args.dry_run:
        estimar_dry_run(args.db, workers=workers)
        return 0

    kb = cargar_kb()
    try:
        if es_mercury:
            cliente = crear_cliente_mercury(
                simulado=simulacion_fase1 if args.simulado else None,
                max_concurrencia=workers,
                tasa_max_por_minuto=args.tasa_max_por_minuto,
                timeout=timeout,
                model=args.model or BACKEND_MODEL_MERCURY,
            )
        elif args.simulado:
            cliente = LLMClient(simulado=simulacion_fase1)
        else:
            endpoints = (args.endpoints.split(",") if args.endpoints
                         else [ENDPOINT_LOCAL_DEFECTO])
            cliente = LLMClient(endpoints=endpoints, timeout=timeout)
            if args.model:
                cliente.model = args.model
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    stop_event = threading.Event()
    try:
        resumen = ejecutar(
            args.db, cliente, kb,
            workers=workers,
            max_reintentos=args.max_reintentos,
            max_tokens_piso=args.max_tokens_piso,
            temperature=temperature,
            limite=args.limite,
            huerfano_minutos=args.huerfano_minutos,
            out_dir=args.out_dir,
            stop_event=stop_event,
            formato=args.formato,
            backend=backend,
            reintentos_red=args.reintentos_red,
            ventana_errores=args.ventana_errores,
            umbral_error=args.umbral_error,
        )
    except KeyboardInterrupt:
        print("Interrumpido: las tareas en vuelo de este worker han vuelto a "
              "pending (BD consistente).", flush=True)
        return 130
    print(
        f"Backend: {resumen['backend']}\n"
        f"Copia de BD: {resumen['copia']}\n"
        f"Huérfanas recuperadas: {resumen['huerfanas_recuperadas']}\n"
        f"Pendientes al inicio: {resumen['pendientes']}\n"
        f"Procesadas: {resumen['procesadas']} | Aceptadas: {resumen['aceptadas']} | "
        f"Rechazadas: {resumen['rechazadas']} | Errores de red: {resumen['errores_red']} | "
        f"Omitidas: {resumen['omitidas']}"
    )
    if resumen["parada"]:
        print(
            f"PARADA DE SEGURIDAD: {resumen['parada']}. "
            f"Quedaron {resumen['no_procesadas_por_parada']} tareas sin procesar "
            f"(siguen pending)."
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
