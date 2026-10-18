#!/usr/bin/env python3
"""Limpieza y métricas de subtítulos VTT de YouTube (A4.3)."""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Expresiones regulares
# ---------------------------------------------------------------------------

# Línea de tiempo: 00:00:01.380 --> 00:00:16.680
_TIMELINE_RE = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}"
)

# Etiquetas de tiempo dentro del texto: <00:00:17.320><c>
_INLINE_TIME_RE = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")

# Etiquetas <c>...</c> y otras etiquetas HTML-like
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")

# Ruido típico: [Música], [Aplausos], [Risas], etc.
_NOISE_RE = re.compile(r"\[(?:m[uú]sica|aplausos|risas|ruido|silencio|música)\]", re.IGNORECASE)

# URLs
_URL_RE = re.compile(r"https?://\S+|www\.\S+")


# ---------------------------------------------------------------------------
# vtt_a_frases: VTT -> lista de frases con tiempo de inicio
# ---------------------------------------------------------------------------

def vtt_a_frases(vtt_texto: str) -> List[Dict[str, Any]]:
    """Convierte el contenido VTT en lista de {"t0": float, "texto": str}.

    Cada línea de tiempo (cue) genera una entrada con el tiempo de inicio
    en segundos y el texto visible (sin etiquetas de tiempo ni <c>).
    """
    frases: List[Dict[str, Any]] = []
    lineas = vtt_texto.splitlines()

    t0_actual = 0.0
    texto_actual = ""

    for linea in lineas:
        # Detectar línea de tiempo
        m = _TIMELINE_RE.match(linea)
        if m:
            # Guardar frase anterior si tiene texto
            if texto_actual.strip():
                frases.append({"t0": t0_actual, "texto": texto_actual.strip()})
            # Nuevo cue: parsear t0
            t_str = m.group(1)
            h, m_min, s = t_str.split(":")
            t0_actual = int(h) * 3600 + int(m_min) * 60 + float(s)
            texto_actual = ""
            continue

        # Saltar cabeceras WEBVTT, Kind, Language, líneas vacías
        if not linea.strip() or linea.startswith("WEBVTT") or linea.startswith("Kind:") or linea.startswith("Language:"):
            continue

        # Acumular texto visible (sin etiquetas de tiempo)
        limpio = _INLINE_TIME_RE.sub("", linea)
        limpio = _TAG_RE.sub("", limpio)
        if limpio.strip():
            texto_actual += (" " if texto_actual else "") + limpio.strip()

    # Última frase
    if texto_actual.strip():
        frases.append({"t0": t0_actual, "texto": texto_actual.strip()})

    return frases


# ---------------------------------------------------------------------------
# Limpieza determinista
# ---------------------------------------------------------------------------

def _quitar_ruido_y_urls(texto: str) -> str:
    """Elimina [Música], [Aplausos], URLs y normaliza espacios."""
    # Eliminar etiquetas de ruido en cualquier posición
    t = _NOISE_RE.sub("", texto)
    t = _URL_RE.sub("", t)
    # Colapsar espacios múltiples
    t = re.sub(r"\s+", " ", t).strip()
    return t


def limpiar(frases: List[Dict[str, Any]]) -> str:
    """Une frases eliminando duplicados consecutivos (subtítulos rodantes)
    y ruido. Devuelve texto continuo limpio.

    Los subtítulos automáticos de YouTube son "rodantes": cada cue repite
    el texto anterior y añade una palabra. Se detecta y elimina el
    prefijo duplicado manteniendo solo la parte nueva.
    """
    if not frases:
        return ""

    # 1) Limpiar cada frase individualmente
    limpias = []
    for f in frases:
        t = _quitar_ruido_y_urls(f["texto"])
        if t:
            limpias.append(t)

    # 2) Eliminar subtítulos rodantes: YouTube repite el texto acumulado
    # en cada cue. Patrón típico: cada cue añade una palabra al anterior
    # (rolling forward) y a veces muestra solo la cola (rolling backward).
    # Algoritmo: mantener último texto guardado. Para cada nuevo texto:
    # - Si nuevo empieza por último guardado -> rolling forward, reemplazar
    # - Si último guardado empieza por nuevo -> rolling backward (cola), saltar
    # - Si último guardado TERMINA en nuevo -> rolling backward (cola al final), saltar
    # - Si nuevo EMPIEZA por un sufijo de último -> solapamiento, recortar
    # - Si no -> texto nuevo, guardar
    resultado = []
    ultimo = ""
    for t in limpias:
        if not ultimo:
            resultado.append(t)
            ultimo = t
            continue
        t_norm = t
        u_norm = ultimo
        if t_norm.startswith(u_norm):
            # Rolling forward: el nuevo contiene al anterior y más
            resultado[-1] = t
            ultimo = t
        elif u_norm.startswith(t_norm) or u_norm.endswith(t_norm):
            # Rolling backward: YouTube muestra solo la cola (prefijo o sufijo)
            # Saltar este, mantener el más largo (ultimo)
            continue
        else:
            # Detectar solapamiento: nuevo empieza por sufijo de ultimo
            # Buscar el sufijo más largo de ultimo que sea prefijo de t
            overlap = 0
            max_check = min(len(u_norm), len(t_norm))
            for L in range(max_check, 0, -1):
                if u_norm[-L:] == t_norm[:L]:
                    overlap = L
                    break
            if overlap > 10:  # solapamiento significativo (>10 chars)
                # Añadir solo la parte no solapada
                resultado.append(t[overlap:])
                ultimo = t
            else:
                # Texto nuevo, no relacionado con rolling anterior
                resultado.append(t)
                ultimo = t

    return " ".join(resultado)

    return " ".join(resultado)


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

def metricas(texto: str, duracion_s: float) -> Dict[str, float]:
    """Calcula métricas de calidad del texto.

    Returns:
        dict con: palabras, palabras_por_min, cartas_por_1000, terminos_astro_por_1000
    """
    if not texto or duracion_s <= 0:
        return {"palabras": 0, "palabras_por_min": 0.0,
                "cartas_por_1000": 0.0, "terminos_astro_por_1000": 0.0}

    palabras = len(texto.split())
    ppm = (palabras / duracion_s) * 60.0

    # Cartas: usar cartas.extraer_cartas (import perezoso para evitar ciclo)
    try:
        import cartas
        menciones = cartas.extraer_cartas(texto, mazo="tarot", contextual=True)
        cartas_por_mil = (len(menciones) / palabras) * 1000 if palabras > 0 else 0.0
    except Exception:
        cartas_por_mil = 0.0

    # Términos astrológicos/numerológicos básicos
    terminos_astro = [
        "sol", "luna", "mercurio", "venus", "marte", "jupiter", "saturno",
        "urano", "neptuno", "pluton", "nodo", "ascendente", "mc", "casa",
        "signo", "aries", "tauro", "geminis", "cancer", "leo", "virgo",
        "libra", "escorpio", "sagitario", "capricornio", "acuario", "piscis",
        "tránsito", "transito", "progresión", "progresion", "revolución",
        "revolucion", "solar", "sinastría", "sinastria", "carta natal",
        "camino de vida", "numero", "número", "destino", "maestro",
    ]
    texto_lower = texto.lower()
    count_astro = sum(1 for t in terminos_astro if t in texto_lower)
    astro_por_mil = (count_astro / palabras) * 1000 if palabras > 0 else 0.0

    return {
        "palabras": palabras,
        "palabras_por_min": round(ppm, 2),
        "cartas_por_1000": round(cartas_por_mil, 2),
        "terminos_astro_por_1000": round(astro_por_mil, 2),
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Limpieza de VTT y métricas")
    parser.add_argument("vtt", help="Archivo VTT a procesar")
    parser.add_argument("--duracion", type=float, default=0,
                        help="Duración en segundos para métricas")
    args = parser.parse_args()

    with open(args.vtt, encoding="utf-8") as f:
        vtt = f.read()

    frases = vtt_a_frases(vtt)
    limpio = limpiar(frases)
    m = metricas(limpio, args.duracion)

    print(f"Frases originales: {len(frases)}")
    print(f"Texto limpio ({len(limpio)} chars): {limpio[:200]}...")
    print(json.dumps(m, ensure_ascii=False, indent=2))
