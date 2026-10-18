#!/usr/bin/env python3
"""Normalización a pares ShareGPT con fidelidad comprobada (A4.6)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import local
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cartas
import llm_client


# ---------------------------------------------------------------------------
# Carga de prompt
# ---------------------------------------------------------------------------

_PROMPT_NORMALIZAR = Path(__file__).parent / "prompts" / "yt_normalizar.md"


def _cargar_prompt() -> str:
    if _PROMPT_NORMALIZAR.exists():
        return _PROMPT_NORMALIZAR.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Construcción de prompt humano
# ---------------------------------------------------------------------------

def _construir_prompt_human(lectura: Dict[str, Any]) -> str:
    """Construye el prompt 'human' estructurado desde la lectura validada."""
    lineas = [f"Tirada: {lectura.get('tirada', '')}"]
    lineas.append("Cartas y posiciones:")
    for c in lectura.get("cartas", []):
        lineas.append(f"- {c.get('nombre')} ({c.get('orientacion')}) en {c.get('posicion')}")
    lineas.append(f"Pregunta/Tema: {lectura.get('pregunta_o_tema', '')}")
    lineas.append("Interpretaciones por carta (referencia):")
    for interp in lectura.get("interpretaciones", []):
        lineas.append(f"- {interp.get('carta')}: {interp.get('texto')}")
    if lectura.get("sintesis"):
        lineas.append(f"Síntesis original: {lectura.get('sintesis')}")
    if lectura.get("consejo"):
        lineas.append(f"Consejo original: {lectura.get('consejo')}")
    return "\n".join(lineas)


def _texto_util_original(lectura: Dict[str, Any]) -> str:
    """Texto útil original = suma de interpretaciones + síntesis + consejo."""
    partes = []
    for interp in lectura.get("interpretaciones", []):
        partes.append(interp.get("texto", ""))
    if lectura.get("sintesis"):
        partes.append(lectura.get("sintesis", ""))
    if lectura.get("consejo"):
        partes.append(lectura.get("consejo", ""))
    return " ".join(partes).strip()


# ---------------------------------------------------------------------------
# Validaciones de fidelidad (post-reescritura)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_TELEFONO_RE = re.compile(r"\+?\d[\d\s\-]{8,}\d")
_PROMESAS_ABSOLUTAS = [
    "seguro que", "te garantizo", "vas a ", "definitivamente",
    "sin duda", "te aseguro", "garantizado", "100% seguro",
]
_DIAGNOSTICOS_MEDICOS = [
    "estás embarazada", "estás embarazado", "tienes cáncer",
    "vas a morir", "enfermedad grave", "terminal", "morirás",
]
_PALABRAS_PROMOCION = [
    "suscríbete", "suscribete", "like", "comparte", "canal",
    "vídeo", "video", "activar la campana", "campanita",
]


def _extraer_nombres_propio(texto: str) -> List[str]:
    """Extrae palabras que parecen nombres propios (inicial mayúscula, no inicio de frase).
    Excluye nombres de cartas del catálogo (canónicos y sinónimos)."""
    # Palabras con mayúscula inicial
    palabras = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b", texto)
    # Filtrar cartas conocidas (nombres canónicos + sinónimos con title case)
    cartas_conocidas = set()
    for c in cartas.CARTAS_TAROT:
        cartas_conocidas.add(c["nombre"])
        for s in c["sinonimos"]:
            # Title case de cada palabra del sinónimo
            for w in s.split():
                cartas_conocidas.add(w.title())
    # También excluir palabras comunes del prompt (Tirada, Cartas, Posiciones, Pregunta, Tema, etc.)
    excluir_comunes = {
        "Tirada", "Cartas", "Posiciones", "Pregunta", "Tema", "Interpretaciones",
        "Carta", "Síntesis", "Consejo", "Original", "En", "El", "La", "Los", "Las",
        "Y", "De", "Del", "En", "Con", "Por", "Para", "Una", "Uno", "Sobre",
    }
    return [p for p in palabras if p not in cartas_conocidas and p not in excluir_comunes and len(p) > 2]


def validar_normalizacion(
    respuesta: str,
    lectura_original: Dict[str, Any],
    prompt_human: str,
) -> Tuple[bool, List[str]]:
    """Valida la respuesta normalizada (GPT) contra reglas de fidelidad.

    Returns:
        (es_valida, lista_motivos_fallo)
    """
    motivos = []
    resp_lower = respuesta.lower()

    # 1. Todas las cartas y posiciones del prompt aparecen en la respuesta
    for c in lectura_original.get("cartas", []):
        nombre_norm = cartas.norm(c.get("nombre", ""))
        pos_norm = cartas.norm(c.get("posicion", ""))
        resp_norm = cartas.norm(respuesta)
        if nombre_norm not in resp_norm:
            motivos.append(f"Carta '{c.get('nombre')}' no aparece en la respuesta")
        if pos_norm and pos_norm not in resp_norm:
            motivos.append(f"Posición '{c.get('posicion')}' no aparece en la respuesta")

    # 2. Longitud entre 0.3x y 1.2x del texto útil original
    texto_util = _texto_util_original(lectura_original)
    len_orig = len(texto_util)
    len_resp = len(respuesta)
    if len_orig > 0:
        ratio = len_resp / len_orig
        if ratio < 0.3:
            motivos.append(f"Respuesta demasiado corta: {ratio:.2f}x del original (mín 0.3x)")
        elif ratio > 2.0:
            motivos.append(f"Respuesta demasiado larga: {ratio:.2f}x del original (máx 2.0x)")

    # 3. Sin teléfonos/URLs
    if _URL_RE.search(respuesta):
        motivos.append("Contiene URL")
    if _TELEFONO_RE.search(respuesta):
        motivos.append("Contiene teléfono")

    # 4. Sin palabras de promoción
    for pal in _PALABRAS_PROMOCION:
        if pal in resp_lower:
            motivos.append(f"Contiene palabra promocional: {pal}")

    # 5. Sin nombres propios ajenos a cartas
    nombres_extra = _extraer_nombres_propio(respuesta)
    if nombres_extra:
        motivos.append(f"Nombres propios no permitidos: {', '.join(nombres_extra[:5])}")

    # 6. Sin promesas absolutas
    for frase in _PROMESAS_ABSOLUTAS:
        if frase in resp_lower:
            motivos.append(f"Promesa absoluta detectada: '{frase}'")

    # 7. Sin diagnósticos médicos
    for frase in _DIAGNOSTICOS_MEDICOS:
        if frase in resp_lower:
            motivos.append(f"Diagnóstico médico detectado: '{frase}'")

    es_valida = len(motivos) == 0
    return es_valida, motivos


# ---------------------------------------------------------------------------
# Normalización principal
# ---------------------------------------------------------------------------

def normalizar_lectura(
    lectura: Dict[str, Any],
    client: llm_client.LLMClient,
    video_id: str = "",
    canal: str = "",
) -> Optional[Dict[str, Any]]:
    """Convierte una lectura validada en par ShareGPT con validación de fidelidad.

    Returns:
        Dict ShareGPT o None si falla la validación.
    """
    prompt_sistema = (
        "Eres un lector experto de tarot/baraja/astrología. "
        "Respondes en español neutro, 2ª persona, sin saludos ni publicidad, "
        "con estructura: apertura → interpretación por posición → síntesis → consejo."
    )
    prompt_human = _construir_prompt_human(lectura)

    # Llamada al LLM (usamos chat porque el prompt pide texto plano, no JSON)
    try:
        texto_gpt = client.chat(
            prompt_sistema,
            prompt_human,
            max_tokens=2048,
            temperature=0.3,
            max_reintentos=3,
        )
    except Exception as e:
        return None

    # Validación de fidelidad
    valida, motivos = validar_normalizacion(texto_gpt, lectura, prompt_human)
    if not valida:
        return None

    # Construir par ShareGPT
    system_msg = (
        "Eres un lector experto de tarot/baraja/astrología. "
        "Respondes en español neutro, 2ª persona, sin saludos ni publicidad, "
        "con estructura: apertura → interpretación por posición → síntesis → consejo."
    )

    return {
        "conversations": [
            {"from": "system", "value": system_msg},
            {"from": "human", "value": prompt_human},
            {"from": "gpt", "value": texto_gpt},
        ],
        "meta": {
            "video_id": video_id,
            "canal": canal,
            "tipo": "lectura",
            "tirada": lectura.get("tirada", ""),
        },
    }


# ---------------------------------------------------------------------------
# Procesamiento por lotes (reanudable)
# ---------------------------------------------------------------------------

def procesar_normalizacion(
    lecturas_path: Path,
    out_dir: Path,
    client: llm_client.LLMClient,
    limite: Optional[int] = None,
) -> Dict[str, int]:
    """Procesa lecturas validadas y genera pares ShareGPT.

    Escribe `dataset.jsonl` (pares válidos) y `descartados.jsonl` (con motivo).
    Reanudable: salta IDs ya presentes.
    """
    out_path = out_dir / "dataset.jsonl"
    descartados_path = out_dir / "descartados.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Cargar IDs ya procesados
    procesados = set()
    for path in (out_path, descartados_path):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for linea in f:
                    try:
                        reg = json.loads(linea)
                        vid = reg.get("meta", {}).get("video_id") or reg.get("video_id")
                        if vid:
                            procesados.add(vid)
                    except Exception:
                        pass

    with open(lecturas_path, encoding="utf-8") as f:
        lecturas = [json.loads(l) for l in f if l.strip()]

    stats = {"ok": 0, "descartados": 0, "saltados": 0}

    with open(out_path, "a", encoding="utf-8") as f_ok, \
         open(descartados_path, "a", encoding="utf-8") as f_bad:

        for i, lect in enumerate(lecturas):
            if limite and i >= limite:
                break

            video_id = lect.get("video_id") or lect.get("meta", {}).get("video_id", f"idx_{i}")
            if video_id in procesados:
                stats["saltados"] += 1
                continue

            par = normalizar_lectura(lect, client, video_id=video_id, canal=lect.get("canal", ""))

            if par:
                f_ok.write(json.dumps(par, ensure_ascii=False) + "\n")
                f_ok.flush()
                stats["ok"] += 1
            else:
                f_bad.write(json.dumps({
                    "video_id": video_id,
                    "motivo": "validación fidelidad fallida",
                }, ensure_ascii=False) + "\n")
                f_bad.flush()
                stats["descartados"] += 1

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Normaliza lecturas a pares ShareGPT (A4.6)")
    parser.add_argument("--lecturas", required=True, help="Archivo JSONL con lecturas validadas")
    parser.add_argument("--out-dir", required=True, help="Directorio de salida")
    parser.add_argument("--limite", type=int, help="Máximo a procesar")
    parser.add_argument("--simulado", action="store_true", help="Cliente LLM simulado")
    args = parser.parse_args()

    if args.simulado:
        # Simulado que devuelve una respuesta válida
        def simulado(sistema, usuario):
            return '''{
  "conversations": [
    {"from": "system", "value": "Eres un lector experto..."},
    {"from": "human", "value": "Tirada: 3_cartas\\nCartas y posiciones:\\n- Los Enamorados (derecha) en presente\\n- La Emperatriz (invertida) en pasado\\n- El Sol (derecha) en futuro\\nPregunta/Tema: amor"},
    {"from": "gpt", "value": "En esta tirada de tres cartas sobre el amor, Los Enamorados en posición presente te hablan de una elección importante que tienes delante. La Emperatriz invertida en el pasado sugiere que has sentido un bloqueo creativo o emocional. El Sol en el futuro te trae claridad y optimismo. En síntesis, la lectura muestra una evolución desde el bloqueo hacia la luz. Consejo: confía en tu intuición y toma la decisión que tu corazón te indica."}
  ],
  "meta": {"video_id": "test", "canal": "test", "tipo": "lectura", "tirada": "3_cartas"}
}'''
        client = llm_client.LLMClient(simulado=simulado)
    else:
        client = llm_client.LLMClient()

    stats = procesar_normalizacion(Path(args.lecturas), Path(args.out_dir), client, limite=args.limite)
    print(f"OK: {stats['ok']} | Descartados: {stats['descartados']} | Saltados: {stats['saltados']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
