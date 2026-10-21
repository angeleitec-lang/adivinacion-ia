#!/usr/bin/env python3
"""Re-verifica un ``aceptadas.jsonl`` de fase 1 con el verificador corregido (T101).

Lee el fichero de entrada en SOLO LECTURA, reconstruye la tarea de cada lectura
(plano o ShareGPT), la pasa por ``fase1_prompts.verificar_lectura`` y separa:

  - válidas: filas que superan el verificador (se copian sin cambios);
  - rechazadas: filas con motivos (id, bloque y motivos), incluida la fuga de
    casos de evaluación (T56) por id/origen o por contenido normalizado.

Nunca sobrescribe la entrada: la salida es un fichero nuevo.

Uso:
    python reverificar_fase1.py --aceptadas ruta/aceptadas.jsonl \
        --salida ruta/aceptadas.reverificadas.jsonl \
        [--rechazadas ruta/rechazadas.jsonl] [--eval-casos ruta/evaluacion_casos.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import merge_final  # noqa: E402
import validate_synthetic as vs  # noqa: E402


def _norm(texto: str) -> str:
    return unicodedata.normalize(
        "NFC", " ".join(str(texto or "").split()).strip().lower())


def _campos(fila: dict) -> dict:
    """Normaliza una fila plana o ShareGPT a los campos que necesita el verificador."""
    conversaciones = fila.get("conversations")
    if isinstance(conversaciones, list):
        human = ""
        respuestas = []
        for turno in conversaciones:
            if not isinstance(turno, dict):
                continue
            if turno.get("from") == "human" and not human:
                human = turno.get("value", "")
            elif turno.get("from") == "gpt":
                respuestas.append(turno.get("value", ""))
        respuesta = "\n".join(respuestas)
    else:
        human = fila.get("prompt_user", fila.get("prompt", ""))
        respuesta = fila.get("respuesta", "")
    calculos = fila.get("calculos") or {}
    if isinstance(calculos, str):
        try:
            calculos = json.loads(calculos)
        except json.JSONDecodeError:
            calculos = {}
    return {
        "human": human or "",
        "respuesta": respuesta or "",
        "calculos": calculos if isinstance(calculos, dict) else {},
        "bloque": fila.get("bloque"),
    }


def _payload(fila: dict):
    payload = fila.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _construir_tarea(bloque: str, campos: dict, payload, kb) -> dict:
    pregunta = ef.extraer_pregunta(campos["human"])
    tarea = None
    if payload is not None:
        try:
            tarea = ef.tarea_desde_job(bloque, payload, pregunta, kb)
        except (ValueError, KeyError, TypeError):
            tarea = None
    if tarea is None:
        tarea = {"familia": bloque, "pregunta": pregunta, "calculos": {}}
        cartas = [
            {"nombre": nombre,
             "invertida": str(orient).lower().startswith("invertid")}
            for nombre, orient in vs.extraer_cartas(campos["human"])
        ]
        if cartas:
            tarea["cartas"] = cartas
            if bloque in getattr(fp, "FAMILIAS_ESPAÑOLA", ()):
                tarea["universo_cartas"] = ef.universo_baraja(kb)
            else:
                tarea["universo_cartas"] = ef.universo_tarot(kb)
    if campos["calculos"]:
        tarea["calculos"] = campos["calculos"]
    return tarea


def _humanos_reservados(filas: list, eval_casos) -> set[str]:
    reservados = merge_final.cargar_humanos_evaluacion(eval_casos)
    for fila in filas:
        if merge_final.es_caso_de_evaluacion(fila):
            reservados.add(_norm(_campos(fila)["human"]))
    return reservados


def reverificar(entrada, salida, rechazadas=None, eval_casos=None, kb=None) -> dict:
    entrada = Path(entrada)
    salida = Path(salida)
    rechazadas = (Path(rechazadas) if rechazadas
                  else salida.with_name(salida.name + ".rechazadas.jsonl"))
    if not entrada.exists():
        raise FileNotFoundError(entrada)
    if entrada.resolve() == salida.resolve():
        raise ValueError("la salida no puede ser el fichero de entrada")
    filas = merge_final.load_jsonl(entrada)
    kb = kb if kb is not None else ef.cargar_kb()
    reservados = _humanos_reservados(filas, eval_casos)

    validas, invalidas = [], []
    motivos_conteo: Counter = Counter()
    for fila in filas:
        if not isinstance(fila, dict):
            continue
        campos = _campos(fila)
        base = {"id": fila.get("id"), "bloque": campos["bloque"]}
        if merge_final.es_caso_de_evaluacion(fila) \
                or _norm(campos["human"]) in reservados:
            motivos = ["caso_de_evaluacion"]
        elif not campos["bloque"]:
            motivos = ["sin_bloque"]
        else:
            tarea = _construir_tarea(campos["bloque"], campos, _payload(fila), kb)
            ok, motivos = fp.verificar_lectura(tarea, campos["respuesta"])
            motivos = list(motivos)
            if not ok and ef.respuesta_truncada(campos["respuesta"]):
                motivos.insert(0, ef.MOTIVO_TRUNCADO)
        if motivos:
            invalidas.append({**base, "motivos": motivos})
            motivos_conteo.update(m.split(":")[0] for m in motivos)
        else:
            validas.append(fila)

    merge_final.write_jsonl(salida, validas)
    merge_final.write_jsonl(rechazadas, invalidas)
    return {
        "entrada": str(entrada),
        "salida": str(salida),
        "rechazadas": str(rechazadas),
        "total": len(filas),
        "validas": len(validas),
        "invalidas": len(invalidas),
        "evaluacion": motivos_conteo.get("caso_de_evaluacion", 0),
        "motivos": dict(motivos_conteo),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-verifica aceptadas.jsonl con el verificador corregido.")
    ap.add_argument("--aceptadas", required=True,
                    help="JSONL de entrada (solo lectura)")
    ap.add_argument("--salida", required=True,
                    help="JSONL de salida con las lecturas válidas")
    ap.add_argument("--rechazadas", default=None,
                    help="JSONL de salidas inválidas (por defecto <salida>.rechazadas)")
    ap.add_argument("--eval-casos", default=None,
                    help="JSONL del conjunto de evaluación (T56) a excluir")
    args = ap.parse_args(argv)
    try:
        resumen = reverificar(args.aceptadas, args.salida, args.rechazadas,
                              args.eval_casos)
    except FileNotFoundError:
        print(f"ERROR: no existe la entrada {args.aceptadas}", file=sys.stderr)
        return 1
    print(f"leídas {resumen['total']} · válidas {resumen['validas']} · "
          f"inválidas {resumen['invalidas']} "
          f"(evaluación {resumen['evaluacion']})")
    print(f"válidas:    {resumen['salida']}")
    print(f"rechazadas: {resumen['rechazadas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
