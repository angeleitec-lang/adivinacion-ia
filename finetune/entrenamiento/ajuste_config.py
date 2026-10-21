#!/usr/bin/env python3
"""Ajuste de la configuración de entrenamiento a los datos reales (T111).

Herramienta de análisis de solo lectura: calcula la distribución de longitud en
tokens del dataset (estimación caracteres/3,5 si no hay tokenizador local), el
impacto de truncar a distintos ``max_seq_len``, la memoria aproximada de un
QLoRA 4-bit y las horas de entrenamiento. No entrena, no instala nada y no
usa la red.

Los coeficientes de memoria y los rangos de rendimiento son supuestos
documentados, no mediciones en nodo1/nodo2. Ver ``docs/PLAN_ENTRENAMIENTO.md``.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

CHAR_POR_TOKEN = 3.5
MEMORIA_NODO_GB = 128.0
BYTES_PESOS_4BIT = 0.56
BYTES_OPTIMIZADOR_POR_PARAM = 12.0
COEF_ACTIVACION = 0.00035
SOBRECARGA = 1.15
LIMITES_TRUNCAMIENTO = (2048, 4096, 6144, 8192)


def parse_yaml_simple(texto: str) -> dict:
    """Parsea el subconjunto de YAML usado por los ``qlora_*.yaml`` del repo.

    Admite mapas anidados por indentación, listas de escalares con ``- ``,
    comentarios de línea completa y escalares int/float/bool/string. No es un
    YAML completo: lanza ``ValueError`` ante sintaxis no soportada.
    """
    lineas = [
        l for l in texto.splitlines()
        if l.strip() and not l.lstrip().startswith("#")
    ]
    if not lineas:
        return {}

    def indent(linea: str) -> int:
        return len(linea) - len(linea.lstrip(" "))

    def escalar(texto: str):
        t = texto.strip()
        if t.lower() in ("true", "yes"):
            return True
        if t.lower() in ("false", "no"):
            return False
        try:
            return int(t)
        except ValueError:
            pass
        try:
            return float(t)
        except ValueError:
            pass
        return t.strip("\"'")

    def parse_bloque(i: int, nivel: int):
        if lineas[i].strip().startswith("- "):
            lista = []
            while (
                i < len(lineas)
                and indent(lineas[i]) == nivel
                and lineas[i].strip().startswith("- ")
            ):
                lista.append(escalar(lineas[i].strip()[2:]))
                i += 1
            return lista, i
        mapa: dict = {}
        while i < len(lineas):
            ind = indent(lineas[i])
            if ind < nivel:
                break
            if ind > nivel:
                raise ValueError(f"indentación inesperada en: {lineas[i]!r}")
            contenido = lineas[i].strip()
            if ":" not in contenido:
                raise ValueError(f"línea sin ':' en: {lineas[i]!r}")
            clave, _, resto = contenido.partition(":")
            resto = resto.strip()
            if resto:
                mapa[clave.strip()] = escalar(resto)
                i += 1
            elif i + 1 < len(lineas) and indent(lineas[i + 1]) > ind:
                hijo, i = parse_bloque(i + 1, indent(lineas[i + 1]))
                mapa[clave.strip()] = hijo
            else:
                mapa[clave.strip()] = None
                i += 1
        return mapa, i

    valor, _ = parse_bloque(0, indent(lineas[0]))
    return valor if isinstance(valor, dict) else {}


def cargar_config(ruta: Path) -> dict:
    """Lee y parsea un YAML de entrenamiento del repo."""
    return parse_yaml_simple(Path(ruta).read_text(encoding="utf-8"))


def _percentil(ordenados: list[int], p: float) -> int:
    if not ordenados:
        return 0
    idx = min(len(ordenados) - 1, math.ceil(len(ordenados) * p) - 1)
    return ordenados[max(0, idx)]


def resumen_longitudes(valores: list[int]) -> dict:
    """n, media, mediana (p50), p95, p99 y máximo de una lista de longitudes."""
    if not valores:
        return {"n": 0, "media": 0.0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
    ordenados = sorted(valores)
    return {
        "n": len(ordenados),
        "media": round(statistics.fmean(ordenados), 1),
        "p50": _percentil(ordenados, 0.50),
        "p95": _percentil(ordenados, 0.95),
        "p99": _percentil(ordenados, 0.99),
        "max": ordenados[-1],
    }


def impacto_truncamiento(tokens: list[int], limite: int) -> dict:
    """Filas y tokens que se perderían al recortar a ``limite``."""
    total = sum(tokens)
    over = [t for t in tokens if t > limite]
    perdidos = sum(t - limite for t in over)
    n = len(tokens)
    return {
        "limite": limite,
        "filas_over": len(over),
        "pct_filas": round(100.0 * len(over) / n, 2) if n else 0.0,
        "pct_tokens_perdidos": round(100.0 * perdidos / total, 3) if total else 0.0,
    }


def estimar_horas(
    tokens_por_epoca: int,
    epocas: float,
    tokens_por_segundo: float,
    sobrecarga: float = SOBRECARGA,
) -> float:
    """Horas = tokens totales / rendimiento * sobrecarga, redondeadas."""
    if tokens_por_segundo <= 0:
        raise ValueError("tokens_por_segundo debe ser positivo")
    horas = tokens_por_epoca * epocas / tokens_por_segundo * sobrecarga / 3600.0
    return round(horas, 1)


def estimar_memoria_qlora(
    param_billones: float,
    trainable_millones: float,
    max_seq_len: int,
    batch_size: int,
    coef_activacion: float = COEF_ACTIVACION,
    bytes_pesos: float = BYTES_PESOS_4BIT,
) -> dict:
    """Recuerdos GB de un QLoRA 4-bit con gradient checkpointing.

    Supuestos (no medidos en Strix Halo):
    - pesos 4-bit NF4 con doble cuantización: ~0,56 GB por mil millones de params;
    - optimizador AdamW fp32 + gradientes: ~12 bytes por parámetro entrenable;
    - activaciones con checkpointing: lineales en batch x seq_len x tamaño del
      modelo, coeficiente calibrado con cifras comunitarias (±40 % de error).
    """
    pesos = param_billones * bytes_pesos
    optimizador = trainable_millones * BYTES_OPTIMIZADOR_POR_PARAM / 1000.0
    activaciones = (
        batch_size * max_seq_len * param_billones * coef_activacion
    )
    total = pesos + optimizador + activaciones
    return {
        "pesos_gb": round(pesos, 1),
        "optimizador_gb": round(optimizador, 2),
        "activaciones_gb": round(activaciones, 1),
        "total_gb": round(total, 1),
        "cabe_en_128gb": total <= MEMORIA_NODO_GB,
        "margen_gb": round(MEMORIA_NODO_GB - total, 1),
    }


def _familia_de(fila: dict) -> str:
    for contenedor in (fila, fila.get("metadatos") or {}, fila.get("metadata") or {}):
        if not isinstance(contenedor, dict):
            continue
        for clave in ("familia", "bloque", "categoria", "categoría", "tipo"):
            valor = contenedor.get(clave)
            if isinstance(valor, str) and valor.strip():
                return valor.strip().lower()
    return "sin_etiqueta"


def tokens_de_fila(fila: dict, char_por_token: float = CHAR_POR_TOKEN) -> int:
    """Tokens estimados de una fila ShareGPT (todos los turnos concatenados)."""
    texto = "\n".join(
        str(t.get("value", ""))
        for t in fila.get("conversations", [])
        if isinstance(t, dict)
    )
    return int(round(len(texto) / char_por_token))


def analizar_dataset(ruta_jsonl: Path) -> dict:
    """Distribución global y por familia + impacto de truncar a varios límites.

    Con tokenizador real se contaría igual; aquí se estima por caracteres.
    """
    tokens_por_familia: dict[str, list[int]] = defaultdict(list)
    todos: list[int] = []
    with Path(ruta_jsonl).open(encoding="utf-8") as fh:
        for linea in fh:
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if not isinstance(fila, dict):
                continue
            tok = tokens_de_fila(fila)
            todos.append(tok)
            tokens_por_familia[_familia_de(fila)].append(tok)
    resultado = {
        "fichero": str(ruta_jsonl),
        "global": resumen_longitudes(todos),
        "total_tokens": sum(todos),
        "por_familia": {
            fam: resumen_longitudes(vals)
            for fam, vals in sorted(tokens_por_familia.items())
        },
        "truncamiento": {
            str(lim): impacto_truncamiento(todos, lim) for lim in LIMITES_TRUNCAMIENTO
        },
    }
    return resultado


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Analiza longitudes, truncamiento, memoria y horas para la fase 2."
    )
    parser.add_argument("--dataset", required=True,
                        help="Carpeta con train.jsonl (y val/test si existen)")
    args = parser.parse_args(argv)
    dataset = Path(args.dataset).expanduser().resolve()
    informe = {}
    for split in ("train", "val", "test"):
        ruta = dataset / f"{split}.jsonl"
        if ruta.exists():
            informe[split] = analizar_dataset(ruta)
    if not informe:
        print(f"No hay JSONL en {dataset}", file=sys.stderr)
        return 2
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
