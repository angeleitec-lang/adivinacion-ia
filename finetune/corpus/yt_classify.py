#!/usr/bin/env python3
"""Clasificación de vídeos de YouTube para track A4 (A4.4)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import llm_client


# ---------------------------------------------------------------------------
# Prompt de clasificación (cargado desde archivo)
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent / "prompts" / "yt_clasificar.md"


def _cargar_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    # Fallback mínimo
    return """Clasifica el vídeo. Responde SOLO con JSON:
{"tipo": "lectura_individual|lectura_ejemplo|lectura_general_elige_carta|curso_conocimiento|mixto|otro",
 "familia": "tarot-lectura|tarot-conocimiento|baraja-lectura|astro-lectura|numerologia",
 "tirada": "1_carta|3_cartas|cruz_celta|herradura|relacion|si_no|carta_natal|otras",
 "n_cartas": 1,
 "calidad": 1-5,
 "motivo": "breve justificación"}"""


# ---------------------------------------------------------------------------
# Valores válidos (según diseño S5)
# ---------------------------------------------------------------------------

_TIPOS_VALIDOS = {
    "lectura_individual",
    "lectura_ejemplo",
    "lectura_general_elige_carta",
    "curso_conocimiento",
    "mixto",
    "otro",
}

_FAMILIAS_VALIDAS = {
    "tarot-lectura",
    "tarot-conocimiento",
    "baraja-lectura",
    "astro-lectura",
    "numerologia",
}

_TIRADAS_VALIDAS = {
    "1_carta",
    "3_cartas",
    "cruz_celta",
    "herradura",
    "relacion",
    "si_no",
    "carta_natal",
    "otras",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def muestrear_texto(texto: str, n: int = 2500) -> str:
    """Toma inicio, mitad y final del texto (máx n caracteres total)."""
    if len(texto) <= n:
        return texto
    tercio = n // 3
    inicio = texto[:tercio]
    mitad_inicio = max(0, len(texto) // 2 - tercio // 2)
    mitad = texto[mitad_inicio:mitad_inicio + tercio]
    final = texto[-tercio:]
    return inicio + "\n...\n" + mitad + "\n...\n" + final


def validar_clasificacion(d: Dict[str, Any]) -> None:
    """Valida estrictamente el dict de clasificación. Lanza ValueError si falla."""
    if not isinstance(d, dict):
        raise ValueError("La respuesta no es un objeto JSON")

    # tipo
    tipo = d.get("tipo")
    if tipo not in _TIPOS_VALIDOS:
        raise ValueError(f"tipo inválido: {tipo}. Valores: {sorted(_TIPOS_VALIDOS)}")

    # familia
    familia = d.get("familia")
    if familia not in _FAMILIAS_VALIDAS:
        raise ValueError(f"familia inválida: {familia}. Valores: {sorted(_FAMILIAS_VALIDAS)}")

    # tirada
    tirada = d.get("tirada")
    if tirada not in _TIRADAS_VALIDAS:
        raise ValueError(f"tirada inválida: {tirada}. Valores: {sorted(_TIRADAS_VALIDAS)}")

    # n_cartas
    n_cartas = d.get("n_cartas")
    if not isinstance(n_cartas, int) or n_cartas < 1:
        raise ValueError(f"n_cartas debe ser entero >= 1: {n_cartas}")

    # calidad
    calidad = d.get("calidad")
    if not isinstance(calidad, int) or not (1 <= calidad <= 5):
        raise ValueError(f"calidad debe ser entero 1-5: {calidad}")

    # motivo
    motivo = d.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("motivo debe ser string no vacío")


# ---------------------------------------------------------------------------
# Clasificación de un vídeo
# ---------------------------------------------------------------------------

def clasificar_video(
    video_id: str,
    titulo: str,
    descripcion: str,
    texto_muestra: str,
    client: llm_client.LLMClient,
) -> Dict[str, Any]:
    """Clasifica un vídeo usando el LLM."""
    prompt = _cargar_prompt()
    sistema = prompt
    usuario = (
        f"VIDEO_ID: {video_id}\n"
        f"TÍTULO: {titulo}\n"
        f"DESCRIPCIÓN: {descripcion[:500]}\n"
        f"MUESTRA DE TEXTO (inicio/mitad/final):\n{texto_muestra}\n\n"
        f"Clasifica según el esquema. Responde SOLO con el JSON."
    )
    return client.chat_json(sistema, usuario, validar_clasificacion)


# ---------------------------------------------------------------------------
# Procesamiento por lotes (reanudable)
# ---------------------------------------------------------------------------

def procesar_clasificacion(
    catalogo_path: Path,
    fetch_path: Path,
    out_dir: Path,
    client: llm_client.LLMClient,
    limite: Optional[int] = None,
) -> Dict[str, int]:
    """Procesa el catálogo clasificando vídeos con subtítulos descargados.

    Escribe `clasificacion.jsonl` con una línea por vídeo.
    Reanudable: salta IDs ya presentes en clasificacion.jsonl.
    """
    out_path = out_dir / "clasificacion.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Cargar IDs ya clasificados
    clasificados = set()
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            for linea in f:
                try:
                    reg = json.loads(linea)
                    if "video_id" in reg:
                        clasificados.add(reg["video_id"])
                except Exception:
                    pass

    # Cargar catálogo y fetch
    with open(catalogo_path, encoding="utf-8") as f:
        catalogo = [json.loads(l) for l in f if l.strip()]

    fetch_estados = {}
    if fetch_path.exists():
        with open(fetch_path, encoding="utf-8") as f:
            for linea in f:
                try:
                    reg = json.loads(linea)
                    if reg.get("estado") == "ok":
                        fetch_estados[reg["id"]] = reg.get("tipo")
                except Exception:
                    pass

    stats = {"ok": 0, "saltados": 0, "sin_subtitulo": 0, "error": 0}

    with open(out_path, "a", encoding="utf-8") as f_out:
        for i, entrada in enumerate(catalogo):
            if limite and i >= limite:
                break

            video_id = entrada["id"]

            if video_id in clasificados:
                stats["saltados"] += 1
                continue

            if video_id not in fetch_estados:
                stats["sin_subtitulo"] += 1
                continue

            # Leer texto del VTT (simplificado: usamos título+descripción si no hay VTT)
            # En producción real se leería el VTT limpio
            texto_muestra = muestrear_texto(f"{entrada.get('titulo', '')} {entrada.get('descripcion', '')}")

            try:
                clasif = clasificar_video(
                    video_id=video_id,
                    titulo=entrada.get("titulo", ""),
                    descripcion=entrada.get("descripcion", ""),
                    texto_muestra=texto_muestra,
                    client=client,
                )
                clasif["video_id"] = video_id
                f_out.write(json.dumps(clasif, ensure_ascii=False) + "\n")
                f_out.flush()
                stats["ok"] += 1
            except Exception as e:
                stats["error"] += 1
                # Escribir error para depuración
                f_out.write(json.dumps({
                    "video_id": video_id,
                    "error": str(e)[:200],
                }, ensure_ascii=False) + "\n")
                f_out.flush()

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Clasifica vídeos de YouTube (A4.4)")
    parser.add_argument("--catalogo", required=True, help="Ruta a catalogo.jsonl")
    parser.add_argument("--fetch", required=True, help="Ruta a fetch.jsonl")
    parser.add_argument("--out-dir", required=True, help="Directorio de salida")
    parser.add_argument("--limite", type=int, help="Máximo de vídeos a clasificar")
    parser.add_argument("--simulado", action="store_true", help="Usar cliente simulado")
    args = parser.parse_args()

    # Cliente simulado para tests
    if args.simulado:
        def simulado_ok(sistema, usuario):
            return '```json\n{"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "tres_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}\n```'
        client = llm_client.LLMClient(simulado=simulado_ok)
    else:
        client = llm_client.LLMClient()

    stats = procesar_clasificacion(
        catalogo_path=Path(args.catalogo),
        fetch_path=Path(args.fetch),
        out_dir=Path(args.out_dir),
        client=client,
        limite=args.limite,
    )

    print(f"OK: {stats['ok']} | Saltados: {stats['saltados']} | Sin subtítulo: {stats['sin_subtitulo']} | Errores: {stats['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
