#!/usr/bin/env python3
"""Línea base de modelos sin entrenar sobre el conjunto de evaluación T56 (T99).

Genera la respuesta de uno o varios modelos para cada uno de los 240 casos
fijos de ``evaluacion_casos.py`` (prompt del caso tal cual: ``system`` y
``user`` ya incorporan el system prompt mínimo del producto de
``fase1_prompts.py``), con temperatura 0,7, reanudación y caché por id de
caso, y escribe ``respuestas.jsonl`` en el formato que consume
``evaluar_modelo.py`` (líneas con ``id`` y ``respuesta``; el resto de campos
es informativo).

Después evalúa cada modelo con ``evaluar_modelo.py`` (sin ``--juez-llm``) y
guarda los informes JSON/MD en el directorio de salida
(``/Users/angelgonzalez/fase0/linea_base/`` por defecto). La comparación se
hace con ``python evaluar_modelo.py --comparar A.json B.json``.

Modelos disponibles (registro ``MODELOS``):

- ``flash-next``: halogen-qwen3.8-flash-next en el nodo2
  (http://10.0.0.4:8000/v1). El nodo1 está reservado: no se usa. Máximo 2
  peticiones en paralelo porque otras IAs comparten el nodo.
- ``mercury-3``: Inception Mercury 3 (reasoning_effort=instant). SOLO si la
  clave está en la variable de entorno ``INCEPTION_API_KEY``: nunca se lee
  de ficheros ni se imprime. Sin clave, el modelo se omite con un aviso.

Reanudación: cada fila escrita en ``<modelo>/respuestas.jsonl`` es la caché;
una segunda pasada solo pide los ids que faltan. Los errores de red NO se
cachéan: el caso queda pendiente para la próxima pasada.

Uso:
    python linea_base.py --modelo flash-next
    python linea_base.py --modelo flash-next --limitar 4 --simulado
    python linea_base.py --modelo mercury-3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import evaluar_modelo  # noqa: E402
import evaluacion_casos as ec  # noqa: E402
from llm_client import LLMClient  # noqa: E402

DEFAULT_SALIDA = "/Users/angelgonzalez/fase0/linea_base"
TEMPERATURA = 0.7

# Presupuesto de salida por familia de evaluación, alineado con
# fase1_prompts.RECOMENDACION_MAX_TOKENS (tarot_10 = cruz_celta,
# baraja_3 = espanola_3; el resto, lecturas cortas o medias).
MAX_TOKENS_POR_FAMILIA = {
    "tarot_1": 1536,
    "tarot_3": 2560,
    "tarot_10": 6144,
    "baraja_3": 2560,
    "astro_natal": 3072,
    "transitos": 3072,
    "revolucion_solar": 3072,
    "sinastria": 4096,
    "numerologia": 2048,
    "biorritmos": 1536,
    "fuera_alcance": 1536,
    "etica": 1536,
}

MODELOS = {
    "flash-next": {
        "slug": "flash_next_nodo2",
        "url": "http://10.0.0.4:8000/v1",
        "model": "halogen-qwen3.8-flash-next",
        "concurrencia_max": 2,
        "api_key_env": None,
        "reasoning_effort": None,
        "timeout": 180.0,
    },
    "mercury-3": {
        "slug": "mercury_3",
        "url": "https://api.inceptionlabs.ai/v1",
        "model": "mercury-3",
        "concurrencia_max": 2,
        "api_key_env": "INCEPTION_API_KEY",
        "reasoning_effort": "instant",
        "timeout": 180.0,
    },
}


class ClaveFaltanteError(RuntimeError):
    """No hay clave en el entorno para un backend de nube."""


def max_tokens_familia(familia: str) -> int:
    return MAX_TOKENS_POR_FAMILIA.get(familia, 1536)


def crear_cliente(nombre: str, paralelo: int, simulado=None,
                  metricas=None) -> LLMClient:
    """Construye el LLMClient del modelo indicado (registro ``MODELOS``).

    La clave de los backends de nube se lee solo del entorno en el momento
    de la petición (``api_key_env``); si la variable no existe, se aborta
    con ``ClaveFaltanteError`` que nombra la variable pero nunca su valor.
    """
    if nombre not in MODELOS:
        raise ValueError(
            f"Modelo desconocido {nombre!r}; opciones: {sorted(MODELOS)}")
    cfg = MODELOS[nombre]
    if paralelo < 1 or paralelo > cfg["concurrencia_max"]:
        raise ValueError(
            f"Paralelismo {paralelo} fuera de límites para {nombre} "
            f"(1..{cfg['concurrencia_max']})")
    if cfg["api_key_env"] and simulado is None:
        if not os.environ.get(cfg["api_key_env"]):
            raise ClaveFaltanteError(
                f"No hay clave en la variable de entorno "
                f"{cfg['api_key_env']!r} para {nombre}; se omite este modelo.")
    return LLMClient(
        endpoints=[{
            "url": cfg["url"],
            "model": cfg["model"],
            "api_key_env": cfg["api_key_env"],
        }],
        model=cfg["model"],
        max_concurrencia=paralelo,
        reasoning_effort=cfg["reasoning_effort"],
        timeout=cfg["timeout"],
        max_tokens_default=1536,
        metricas=metricas,
        simulado=simulado,
    )


def cargar_cache(destino: Path) -> dict[str, str]:
    """Ids ya respondidos en ``respuestas.jsonl`` (id -> respuesta).

    Una pasada interrumpida puede dejar líneas duplicadas o corruptas: se
    conserva la primera respuesta válida por id y se ignoran el resto.
    """
    cache: dict[str, str] = {}
    if not destino.exists():
        return cache
    for linea in destino.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if not isinstance(fila, dict) or "id" not in fila:
            continue
        rid = str(fila["id"])
        if rid not in cache:
            resp = fila.get("respuesta")
            cache[rid] = "" if resp is None else str(resp)
    return cache


def generar(casos: list[dict], cliente: LLMClient, destino: Path,
            nombre_modelo: str, temperatura: float = TEMPERATURA,
            paralelo: int = 1) -> dict:
    """Pide a ``cliente`` la respuesta de cada caso sin caché y va escribiendo
    ``respuestas.jsonl`` (append, un flush por fila: reanudable a la segunda).

    Devuelve un resumen con ``casos``, ``en_cache``, ``pedidas``,
    ``escritas``, ``erroneas`` y ``errores``. Los errores de red no se
    escriben: quedan para la próxima pasada.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    cache = cargar_cache(destino)
    pendientes = [c for c in casos if c["id"] not in cache]
    resumen = {
        "casos": len(casos),
        "en_cache": len(casos) - len(pendientes),
        "pedidas": 0,
        "escritas": 0,
        "erroneas": 0,
        "errores": [],
    }
    if not pendientes:
        return resumen

    lock = threading.Lock()


    def _uno(caso: dict) -> dict:
        respuesta = cliente.chat(
            caso["system"], caso["user"],
            max_tokens=max_tokens_familia(caso["familia"]),
            temperature=temperatura,
        )
        fila = {
            "id": caso["id"],
            "familia": caso["familia"],
            "modelo": nombre_modelo,
            "temperatura": temperatura,
            "generada": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "respuesta": respuesta,
        }
        with lock:
            with destino.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
                fh.flush()
        return fila

    with ThreadPoolExecutor(max_workers=max(1, paralelo)) as ex:
        futures = []
        for caso in pendientes:
            futures.append(ex.submit(_uno, caso))
        for futuro in as_completed(futures):
            resumen["pedidas"] += 1
            try:
                futuro.result()
                resumen["escritas"] += 1
            except Exception as e:
                resumen["erroneas"] += 1
                resumen["errores"].append(
                    {"tipo": type(e).__name__,
                     "mensaje": str(e)[:200]})
    return resumen


def evaluar_y_guardar(casos: list[dict], respuestas_path: Path,
                      informe_base: Path) -> tuple[Path, Path]:
    """Evalúa las respuestas con ``evaluar_modelo`` (sin juez LLM) y guarda
    el informe JSON/MD. Devuelve las dos rutas."""
    respuestas = evaluar_modelo.cargar_respuestas(respuestas_path)
    informe = evaluar_modelo.evaluar(casos, respuestas)
    return evaluar_modelo.escribir_informe(informe, informe_base)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Línea base de modelos sin entrenar sobre el conjunto T56 (T99).")
    parser.add_argument("--modelo", default="flash-next",
                        choices=sorted(MODELOS))
    parser.add_argument("--semilla", type=int,
                        default=ec.SEMILLA_POR_DEFECTO,
                        choices=ec.SEMILLAS_RESERVADAS)
    parser.add_argument("--dir", default=DEFAULT_SALIDA,
                        help="directorio de salidas (respuestas e informes)")
    parser.add_argument("--paralelo", type=int, default=2,
                        help="peticiones simultáneas (máx. 2 en nodo2)")
    parser.add_argument("--temperatura", type=float, default=TEMPERATURA)
    parser.add_argument("--limitar", type=int, default=0,
                        help="solo los N primeros casos (prueba de humo)")
    parser.add_argument("--simulado", action="store_true",
                        help="cliente simulado determinista (sin red, pruebas)")
    parser.add_argument("--sin-evaluar", action="store_true",
                        help="solo genera respuestas; no evalúa")
    args = parser.parse_args(argv)

    cfg = MODELOS[args.modelo]
    dir_base = Path(args.dir)
    dir_modelo = dir_base / cfg["slug"]
    dir_modelo.mkdir(parents=True, exist_ok=True)

    casos = ec.generar_casos(args.semilla)
    if args.limitar > 0:
        casos = casos[:args.limitar]
    else:
        ruta_casos = dir_base / f"casos-semilla{args.semilla}.jsonl"
        if not ruta_casos.exists():
            ec.escribir_casos(ruta_casos, casos)

    def lector_simulado(sistema, usuario):
        return ("Lectura de prueba simulada. Las cartas indican una "
                "tendencia de cambio; recuerda que no sustituye a un "
                "profesional. " + usuario[:80])

    metricas: dict[str, float] = {}
    try:
        cliente = crear_cliente(args.modelo, args.paralelo,
                                simulado=lector_simulado if args.simulado
                                else None,
                                metricas=metricas)
    except ClaveFaltanteError as e:
        print(f"AVISO: {e}")
        return 2

    destino = dir_modelo / "respuestas.jsonl"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {args.modelo}: "
          f"generando {len(casos)} casos -> {destino}", flush=True)
    resumen = generar(casos, cliente, destino, args.modelo,
                      temperatura=args.temperatura, paralelo=args.paralelo)
    print(json.dumps({k: v for k, v in resumen.items() if k != "errores"},
                     ensure_ascii=False), flush=True)
    if resumen["errores"]:
        rutas = dir_modelo / "errores.log"
        with rutas.open("a", encoding="utf-8") as fh:
            for err in resumen["errores"]:
                fh.write(json.dumps(err, ensure_ascii=False) + "\n")
        print(f"{resumen['erroneas']} errores de red anotados en {rutas}; "
              "re-ejecuta para reintentarlos.", flush=True)

    if not args.sin_evaluar:
        ruta_informes = dir_modelo / "informe"
        completos = evaluar_modelo.cargar_respuestas(destino)
        if len(completos) < len(casos):
            print("Quedan respuestas pendientes; la evaluación exige el "
                  "conjunto completo. Vuelve a lanzar la misma orden.",
                  flush=True)
            return 3
        json_ruta, md_ruta = evaluar_y_guardar(
            casos, destino, ruta_informes)
        print(f"Informe: {md_ruta} y {json_ruta}", flush=True)
    if metricas:
        (dir_modelo / "metricas.json").write_text(
            json.dumps(metricas, ensure_ascii=False, indent=2),
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
