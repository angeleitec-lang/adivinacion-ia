#!/usr/bin/env python3
"""Descarga de subtítulos de YouTube (A4.3).

Solo subtítulos: manual `es` si existe; si no, automático original `es-orig`.
Nunca el `es` automático traducido.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yt_dlp  # type: ignore
except Exception:  # pragma: no cover
    yt_dlp = None  # type: ignore


# ---------------------------------------------------------------------------
# Constantes y utilidades
# ---------------------------------------------------------------------------

_ESTADOS_VALIDOS = {"ok", "sin_subtitulo", "error"}
_TIPOS_VALIDOS = {"manual", "auto_original"}

# Códigos de salida
EXIT_OK = 0
EXIT_ERROR_GENERAL = 1
EXIT_ERROR_YT_LIMIT = 3  # 429 o "Sign in to confirm"


def _es_codigo_limite(exc: Exception) -> bool:
    """Detecta si la excepción indica límite de YouTube (429 o login)."""
    msg = str(exc).lower()
    return "429" in msg or "sign in to confirm" in msg or "too many requests" in msg


def _extraer_id(url_o_id: str) -> str:
    """Extrae el video ID de una URL o devuelve el ID si ya lo es."""
    # yt-dlp devuelve el ID directo en extract_info con extract_flat
    return url_o_id


# ---------------------------------------------------------------------------
# Descarga de subtítulos para un vídeo
# ---------------------------------------------------------------------------

def descargar_subtitulos(
    video_id: str,
    out_dir: Path,
    canal_id: str,
    clase_ydl: Optional[Callable] = None,
    pausa: float = 1.5,
    reintentos: int = 3,
) -> Dict[str, Any]:
    """Descarga subtítulos de un vídeo.

    Returns:
        dict con: id, estado (ok|sin_subtitulo|error), tipo (manual|auto_original),
        bytes (tamaño del archivo VTT), error (opcional)
    """
    # Preparar directorio de salida
    vtt_dir = out_dir / "raw_vtt" / canal_id
    vtt_dir.mkdir(parents=True, exist_ok=True)

    # Opciones yt-dlp: solo subtítulos, sin descargar vídeo
    # Prioridad: manual `es` > automático original `es-orig`
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["es", "es-orig"],
        "subtitlesformat": "vtt",
        "outtmpl": str(vtt_dir / f"{video_id}.%(language)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": False,  # queremos capturar errores
    }

    YDL = clase_ydl or (lambda opts: yt_dlp.YoutubeDL(opts))

    # Reintentos con espera exponencial
    espera = pausa
    for intento in range(reintentos + 1):
        try:
            with YDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            # yt-dlp guarda los archivos automáticamente según outtmpl
            # Verificar qué se descargó
            manual_path = vtt_dir / f"{video_id}.es.vtt"
            auto_path = vtt_dir / f"{video_id}.es-orig.vtt"

            if manual_path.exists():
                return {
                    "id": video_id,
                    "estado": "ok",
                    "tipo": "manual",
                    "bytes": manual_path.stat().st_size,
                }
            elif auto_path.exists():
                return {
                    "id": video_id,
                    "estado": "ok",
                    "tipo": "auto_original",
                    "bytes": auto_path.stat().st_size,
                }
            else:
                return {
                    "id": video_id,
                    "estado": "sin_subtitulo",
                    "tipo": None,
                    "bytes": 0,
                }

        except Exception as e:
            if _es_codigo_limite(e):
                # Límite de YouTube: parar limpio con código 3
                return {
                    "id": video_id,
                    "estado": "error",
                    "tipo": None,
                    "bytes": 0,
                    "error": "rate_limit",
                }
            if intento < reintentos:
                time.sleep(espera)
                espera *= 2  # backoff exponencial
                continue
            # Último intento fallido
            return {
                "id": video_id,
                "estado": "error",
                "tipo": None,
                "bytes": 0,
                "error": str(e)[:200],
            }

    return {
        "id": video_id,
        "estado": "error",
        "tipo": None,
        "bytes": 0,
        "error": "max_retries",
    }


# ---------------------------------------------------------------------------
# Procesamiento por lotes (reanudable)
# ---------------------------------------------------------------------------

def procesar_catalogo(
    catalogo_path: Path,
    out_dir: Path,
    clase_ydl: Optional[Callable] = None,
    pausa: float = 1.5,
    reintentos: int = 3,
    limite: Optional[int] = None,
) -> Dict[str, int]:
    """Procesa el catálogo descargando subtítulos.

    Escribe `fetch.jsonl` con una línea por vídeo.
    Reanudable: salta los IDs ya presentes en fetch.jsonl.
    """
    fetch_path = out_dir / "fetch.jsonl"
    fetch_path.parent.mkdir(parents=True, exist_ok=True)

    # Cargar IDs ya procesados
    procesados = set()
    if fetch_path.exists():
        with open(fetch_path, encoding="utf-8") as f:
            for linea in f:
                try:
                    reg = json.loads(linea)
                    if reg.get("estado") in ("ok", "sin_subtitulo"):
                        procesados.add(reg["id"])
                except Exception:
                    pass

    # Leer catálogo
    with open(catalogo_path, encoding="utf-8") as f:
        lineas = [json.loads(l) for l in f if l.strip()]

    stats = {"ok": 0, "sin_subtitulo": 0, "error": 0, "saltados": 0}

    with open(fetch_path, "a", encoding="utf-8") as f_out:
        for i, entrada in enumerate(lineas):
            if limite and i >= limite:
                break

            video_id = entrada["id"]
            canal_id = entrada.get("canal_id", "desconocido")

            if video_id in procesados:
                stats["saltados"] += 1
                continue

            res = descargar_subtitulos(
                video_id=video_id,
                out_dir=out_dir,
                canal_id=canal_id,
                clase_ydl=clase_ydl,
                pausa=pausa,
                reintentos=reintentos,
            )

            # Si es rate_limit, parar todo y devolver código 3
            if res.get("error") == "rate_limit":
                f_out.write(json.dumps(res, ensure_ascii=False) + "\n")
                stats["error"] += 1
                return stats  # El llamador debe salir con código 3

            f_out.write(json.dumps(res, ensure_ascii=False) + "\n")
            f_out.flush()

            stats[res["estado"]] = stats.get(res["estado"], 0) + 1

            if pausa > 0:
                time.sleep(pausa)

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Descarga subtítulos de YouTube (A4.3)")
    parser.add_argument("--catalogo", required=True, help="Ruta a catalogo.jsonl")
    parser.add_argument("--out-dir", required=True, help="Directorio de salida")
    parser.add_argument("--pausa", type=float, default=1.5, help="Pausa entre peticiones (s)")
    parser.add_argument("--reintentos", type=int, default=3, help="Reintentos por vídeo")
    parser.add_argument("--limite", type=int, help="Máximo de vídeos a procesar")
    parser.add_argument("--dry-run", action="store_true", help="Solo simula, no descarga")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY-RUN] Simulación, no se descarga nada")
        return EXIT_OK

    stats = procesar_catalogo(
        catalogo_path=Path(args.catalogo),
        out_dir=Path(args.out_dir),
        pausa=args.pausa,
        reintentos=args.reintentos,
        limite=args.limite,
    )

    print(f"OK: {stats['ok']} | Sin subtítulo: {stats['sin_subtitulo']} | Errores: {stats['error']} | Saltados: {stats['saltados']}")

    # Si hubo rate_limit, salir con código 3
    if stats["error"] > 0:
        # Verificar si fue rate_limit leyendo fetch.jsonl
        fetch_path = Path(args.out_dir) / "fetch.jsonl"
        if fetch_path.exists():
            with open(fetch_path, encoding="utf-8") as f:
                for linea in f:
                    try:
                        if json.loads(linea).get("error") == "rate_limit":
                            return EXIT_ERROR_YT_LIMIT
                    except Exception:
                        pass
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
