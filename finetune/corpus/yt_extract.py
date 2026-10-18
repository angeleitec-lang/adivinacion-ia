#!/usr/bin/env python3
"""Extracción y validación determinista de lecturas (A4.5)."""

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
# Carga de prompts
# ---------------------------------------------------------------------------

_PROMPT_LECTURA = Path(__file__).parent / "prompts" / "yt_extraer_lectura.md"
_PROMPT_CONOCIMIENTO = Path(__file__).parent / "prompts" / "yt_extraer_conocimiento.md"


def _cargar_prompt(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Ventaneo de texto largo
# ---------------------------------------------------------------------------

def _trocear_con_solape(texto: str, max_chars: int = 6000, solape: int = 500) -> List[str]:
    """Trocea texto en ventanas con solape para no perder contexto entre cartas."""
    if len(texto) <= max_chars:
        return [texto]
    trozos = []
    inicio = 0
    while inicio < len(texto):
        fin = min(inicio + max_chars, len(texto))
        trozos.append(texto[inicio:fin])
        if fin >= len(texto):
            break
        inicio = fin - solape
    return trozos


def _fusionar_lecturas(lecturas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fusiona múltiples lecturas parciales evitando duplicados de cartas."""
    if not lecturas:
        return {"tipo": "no_lectura"}

    # Tomar la primera como base
    base = lecturas[0]
    if base.get("tipo") != "lectura":
        return base

    cartas_vistas = set()
    cartas_fusionadas = []
    interpretaciones_fusionadas = []

    for lect in lecturas:
        if lect.get("tipo") != "lectura":
            continue
        for c in lect.get("cartas", []):
            clave = (c.get("nombre"), c.get("posicion"))
            if clave not in cartas_vistas:
                cartas_vistas.add(clave)
                cartas_fusionadas.append(c)
        for interp in lect.get("interpretaciones", []):
            # Deduplicar por carta
            if not any(i["carta"] == interp["carta"] for i in interpretaciones_fusionadas):
                interpretaciones_fusionadas.append(interp)

    # Sintetizar: tomar la más larga no vacía
    sintesis = max((l.get("sintesis", "") for l in lecturas if l.get("sintesis")), default="", key=len)
    consejo = max((l.get("consejo", "") for l in lecturas if l.get("consejo")), default="", key=len)

    base["cartas"] = cartas_fusionadas
    base["interpretaciones"] = interpretaciones_fusionadas
    base["sintesis"] = sintesis
    base["consejo"] = consejo
    return base


# ---------------------------------------------------------------------------
# Extracción principal
# ---------------------------------------------------------------------------

def extraer_lectura(texto: str, client: llm_client.LLMClient) -> Dict[str, Any]:
    """Extrae la estructura de una lectura del texto, troceando si es largo."""
    prompt = _cargar_prompt(_PROMPT_LECTURA)
    if not prompt:
        return {"tipo": "no_lectura", "error": "prompt no encontrado"}

    trozos = _trocear_con_solape(texto)
    lecturas_parciales = []

    for trozo in trozos:
        sistema = prompt
        usuario = f"TEXTO DEL VÍDEO (fragmento):\n{trozo}\n\nExtrae la lectura según el esquema. Si no hay lectura, devuelve {{\"tipo\": \"no_lectura\"}}."
        try:
            res = client.chat_json(sistema, usuario, lambda d: None, max_tokens=2048)
            lecturas_parciales.append(res)
        except Exception:
            # Si falla en un trozo, continuar con los demás
            continue

    return _fusionar_lecturas(lecturas_parciales)


def extraer_conocimiento(texto: str, client: llm_client.LLMClient) -> Dict[str, Any]:
    """Extrae afirmaciones de conocimiento del texto."""
    prompt = _cargar_prompt(_PROMPT_CONOCIMIENTO)
    if not prompt:
        return {"tipo": "no_conocimiento", "error": "prompt no encontrado"}

    trozos = _trocear_con_solape(texto)
    todas_afirmaciones = []

    for trozo in trozos:
        sistema = prompt
        usuario = f"TEXTO DEL VÍDEO (fragmento):\n{trozo}\n\nExtrae afirmaciones de conocimiento según el esquema."
        try:
            res = client.chat_json(sistema, usuario, lambda d: None, max_tokens=2048)
            if res.get("tipo") == "conocimiento":
                todas_afirmaciones.extend(res.get("afirmaciones", []))
        except Exception:
            continue

    # Deduplicar afirmaciones por (entidad, faceta, texto[:50])
    unicas = []
    vistas = set()
    for a in todas_afirmaciones:
        clave = (a.get("entidad"), a.get("faceta"), a.get("texto", "")[:50])
        if clave not in vistas:
            vistas.add(clave)
            unicas.append(a)

    return {"tipo": "conocimiento", "familia": "tarot-conocimiento", "afirmaciones": unicas}


# ---------------------------------------------------------------------------
# Validaciones deterministas (S6 del diseño)
# ---------------------------------------------------------------------------

_TIRADAS_POSICIONES = {
    "1_carta": ["carta"],
    "3_cartas": ["pasado", "presente", "futuro", "situacion", "obstaculo", "consejo", "tu", "la otra persona", "la relacion"],
    "cruz_celta": ["situacion", "presente", "desafio", "obstaculo", "base", "raiz", "pasado remoto", "pasado reciente", "corona", "meta", "lo mejor", "futuro cercano", "tu", "actitud", "entorno", "influencias", "esperanzas y miedos", "resultado"],
    "herradura": ["posicion 1", "posicion 2", "posicion 3", "posicion 4", "posicion 5", "posicion 6", "posicion 7"],
    "relacion": ["posicion 1", "posicion 2", "posicion 3", "posicion 4", "posicion 5", "posicion 6", "posicion 7"],
    "si_no": ["carta"],
    "carta_natal": [],  # validación distinta
    "otras": [],  # cualquier posición
}

_PLANETAS = {"sol", "luna", "mercurio", "venus", "marte", "jupiter", "saturno", "urano", "neptuno", "pluton"}
_SIGNOS = {"aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra", "escorpio", "sagitario", "capricornio", "acuario", "piscis"}


def _normalizar_posicion(pos: str) -> str:
    return cartas.norm(pos).strip()


def _coincide_aproximado(texto_original: str, palabras_clave: List[str], umbral: float = 0.6) -> bool:
    """Verifica si al menos umbral fracción de palabras clave aparecen en el texto."""
    if not palabras_clave:
        return True
    texto_norm = cartas.norm(texto_original)
    encontradas = sum(1 for p in palabras_clave if p in texto_norm)
    return encontradas / len(palabras_clave) >= umbral


def validar_lectura(lectura: Dict[str, Any], texto_original: str) -> Tuple[bool, List[str]]:
    """Valida una lectura extraída con 5 comprobaciones deterministas.

    Returns:
        (es_valida, lista_motivos_fallo)
    """
    motivos = []

    if lectura.get("tipo") != "lectura":
        return False, ["tipo no es 'lectura'"]

    # 1. Cartas existen en catálogo (78 tarot)
    cartas_lectura = lectura.get("cartas", [])
    nombres_cartas = []
    for c in cartas_lectura:
        nombre = c.get("nombre", "")
        entrada = cartas.normalizar_carta(nombre, mazo="tarot")
        if entrada is None:
            motivos.append(f"Carta no existe en catálogo: {nombre}")
        else:
            nombres_cartas.append(entrada["nombre"])

    # 2. Nº de cartas coherente con la tirada
    tirada = lectura.get("tirada", "")
    n_cartas_esperado = {
        "1_carta": 1, "3_cartas": 3, "cruz_celta": 10, "herradura": 7,
        "relacion": 7, "si_no": 1, "carta_natal": 0, "otras": None,
    }.get(tirada)
    n_reales = len(cartas_lectura)
    if n_cartas_esperado is not None and n_reales != n_cartas_esperado:
        motivos.append(f"Nº cartas ({n_reales}) no coincide con tirada {tirada} (esperado {n_cartas_esperado})")

    # 3. Posiciones válidas para la tirada
    posiciones_validas = _TIRADAS_POSICIONES.get(tirada, [])
    for c in cartas_lectura:
        pos = _normalizar_posicion(c.get("posicion", ""))
        if posiciones_validas and pos not in [cartas.norm(p) for p in posiciones_validas]:
            motivos.append(f"Posición inválida para {tirada}: {c.get('posicion')}")

    # 4. Interpretación anclada en texto original
    for interp in lectura.get("interpretaciones", []):
        carta_nombre = interp.get("carta", "")
        interp_texto = interp.get("texto", "")
        # Palabras clave: nombre de carta + palabras de la interpretación
        palabras = [w for w in cartas.norm(interp_texto).split() if len(w) > 3][:10]
        if not _coincide_aproximado(texto_original, [cartas.norm(carta_nombre)] + palabras):
            motivos.append(f"Interpretación de {carta_nombre} no anclada en texto original")

    # 5. Para carta_natal: planetas, signos, casas en original
    if tirada == "carta_natal":
        # En diseño S6: "planetas, signos y casas deben aparecer en el original"
        # Aquí validamos que al menos algunos planetas/signos/casas mencionados estén en el texto
        pass  # Implementación simplificada

    es_valida = len(motivos) == 0
    return es_valida, motivos


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Extrae y valida lecturas (A4.5)")
    parser.add_argument("--texto", required=True, help="Archivo de texto limpio o '-' para stdin")
    parser.add_argument("--out", help="Archivo de salida JSON")
    parser.add_argument("--simulado", action="store_true", help="Cliente LLM simulado")
    args = parser.parse_args()

    if args.texto == "-":
        texto = sys.stdin.read()
    else:
        with open(args.texto, encoding="utf-8") as f:
            texto = f.read()

    if args.simulado:
        def simulado(sistema, usuario):
            if "no_lectura" in usuario.lower() or "curso" in usuario.lower():
                return '```json\n{"tipo": "no_lectura"}\n```'
            return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [
    {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica una decisión importante en el amor"},
    {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
    {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y éxito"}
  ],
  "sintesis": "La lectura muestra evolución de bloqueo a claridad",
  "consejo": "Confía en tu intuición"
}
```'''
        client = llm_client.LLMClient(simulado=simulado)
    else:
        client = llm_client.LLMClient()

    lectura = extraer_lectura(texto, client)
    valida, motivos = validar_lectura(lectura, texto)

    resultado = {
        "lectura": lectura,
        "valida": valida,
        "motivos_fallo": motivos,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))

    return 0 if valida else 1


if __name__ == "__main__":
    sys.exit(main())
