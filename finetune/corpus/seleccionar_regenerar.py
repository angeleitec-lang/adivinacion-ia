#!/usr/bin/env python3
"""Selecciona lecturas aceptadas que conviene regenerar con el prompt de T108.

Lee una copia congelada de aceptadas.jsonl (solo lectura), reutiliza las
comprobaciones de calidad de T105 y escribe un JSONL priorizado. No llama a
ningún nodo, no modifica el corpus y no excluye lecturas del dataset.
"""

import argparse
import json
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calidad_lecturas as cl  # noqa: E402

PESOS = {
    "apertura_formula": 2,
    "frase_plantilla": 2,
    "esquema_incumplido": 2,
    "genero_asumido": 1,
}
TOKENS_SALIDA = 1300
SEGUNDOS_POR_LECTURA = 4.0
FRACCION_PROPUESTA = 0.30


def puntuar_lectura(hallazgos):
    """Devuelve (puntuación, motivos) a partir de los hallazgos de una lectura."""
    motivos = sorted({h["codigo"] for h in hallazgos if h["codigo"] in PESOS})
    puntos = sum(PESOS[codigo] for codigo in motivos)
    return puntos, motivos


def construir_seleccion(lecturas, detalle, umbral=2):
    """Filtra por umbral; añade bloque, puntuación y motivos; ordena estable."""
    seleccion = []
    for lectura in lecturas:
        puntos, motivos = puntuar_lectura(detalle.get(lectura["id"], []))
        if puntos >= umbral:
            seleccion.append({
                "id": lectura["id"],
                "bloque": lectura["bloque"],
                "puntuacion": puntos,
                "motivos": motivos,
            })
    seleccion.sort(key=lambda s: (-s["puntuacion"], s["id"]))
    return seleccion


def marcar_propuesta(seleccion, totales_por_bloque, fraccion=FRACCION_PROPUESTA):
    """Marca el mejor porcentaje de cada bloque (mínimo una lectura por bloque)."""
    cupos = {}
    for bloque, total in totales_por_bloque.items():
        cupos[bloque] = max(1, int(math.ceil(total * fraccion)))
    vistos = Counter()
    for fila in seleccion:
        bloque = fila["bloque"]
        if vistos[bloque] < cupos.get(bloque, 0):
            fila["propuesta"] = True
            vistos[bloque] += 1
        else:
            fila["propuesta"] = False
    return seleccion


def resumen_por_bloque(lecturas, seleccion):
    totales = Counter(l["bloque"] for l in lecturas)
    seleccionadas = Counter(s["bloque"] for s in seleccion)
    propuestas = Counter(s["bloque"] for s in seleccion if s["propuesta"])
    filas = {}
    for bloque in sorted(totales):
        filas[bloque] = {
            "lecturas": totales[bloque],
            "seleccionadas": seleccionadas.get(bloque, 0),
            "propuestas": propuestas.get(bloque, 0),
        }
    return filas


def estimar(seleccion, tokens=TOKENS_SALIDA, segundos=SEGUNDOS_POR_LECTURA):
    n = len(seleccion)
    total_segundos = n * segundos
    return {
        "lecturas": n,
        "tokens_salida": n * tokens,
        "segundos": round(total_segundos, 1),
        "horas": round(total_segundos / 3600.0, 2),
        "supuestos": {"tokens_salida_por_lectura": tokens, "segundos_por_lectura": segundos},
    }


def seleccionar(lecturas, kb=None, umbral=2, fraccion=FRACCION_PROPUESTA):
    """Pipeline completo sobre lecturas ya cargadas."""
    informe = cl.analizar_lecturas(lecturas, kb)
    seleccion = construir_seleccion(lecturas, informe["detalle"], umbral=umbral)
    totales = Counter(l["bloque"] for l in lecturas)
    marcar_propuesta(seleccion, totales, fraccion=fraccion)
    propuestas = [s for s in seleccion if s["propuesta"]]
    return {
        "umbral": umbral,
        "fraccion": fraccion,
        "lecturas": len(lecturas),
        "seleccionadas": seleccion,
        "propuestas": propuestas,
        "resumen": resumen_por_bloque(lecturas, seleccion),
        "estimacion_total": estimar(seleccion),
        "estimacion_propuesta": estimar(propuestas),
    }


def escribir_jsonl(seleccion, ruta):
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        for fila in seleccion:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def escribir_resumen(resultado, ruta):
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Selecciona lecturas aceptadas que conviene regenerar (solo lectura)")
    ap.add_argument("--in", dest="entrada", required=True,
                    help="JSONL de lecturas aceptadas congeladas")
    ap.add_argument("--out-dir", default=".",
                    help="directorio de salida (JSONL y resumen JSON)")
    ap.add_argument("--umbral", type=int, default=2,
                    help="puntuación mínima para entrar en la selección (por defecto 2)")
    ap.add_argument("--fraccion", type=float, default=FRACCION_PROPUESTA,
                    help="fracción por bloque que se propone regenerar (por defecto 0,30)")
    args = ap.parse_args(argv)

    lecturas = cl.cargar_lecturas(args.entrada)
    resultado = seleccionar(lecturas, umbral=args.umbral, fraccion=args.fraccion)
    ruta_jsonl = os.path.join(args.out_dir, "seleccion_regenerar.jsonl")
    ruta_resumen = os.path.join(args.out_dir, "seleccion_regenerar_resumen.json")
    escribir_jsonl(resultado["seleccionadas"], ruta_jsonl)
    escribir_resumen({
        "umbral": resultado["umbral"],
        "fraccion": resultado["fraccion"],
        "lecturas": resultado["lecturas"],
        "resumen": resultado["resumen"],
        "estimacion_total": resultado["estimacion_total"],
        "estimacion_propuesta": resultado["estimacion_propuesta"],
    }, ruta_resumen)

    for bloque, datos in resultado["resumen"].items():
        print(f"{bloque:20s} {datos['seleccionadas']:5d}/{datos['lecturas']:5d} "
              f"propuestas {datos['propuestas']:5d}")
    est = resultado["estimacion_propuesta"]
    print(f"propuesta: {est['lecturas']} lecturas, {est['tokens_salida']} tokens, "
          f"{est['horas']} h")
    print(f"escrito {ruta_jsonl} y {ruta_resumen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
