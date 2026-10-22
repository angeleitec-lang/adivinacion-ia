#!/usr/bin/env python3
"""Prompts de fase 1 con «Referencia» de la KB de consenso y datos calculados.

Fase 1 = regenerar el dataset sintético con prompts que incluyen:
  (a) una «Referencia» con significados contrastados de la KB (solo hechos; se
      marcan las discrepancias entre tradiciones cuando la KB las trae), y
  (b) los datos calculados por código (calculos/).

Expone:
  - construir_prompt(tarea, kb, calculos) -> {"system", "user"}
  - verificar_lectura(tarea, texto) -> (ok: bool, motivos: list[str])
  - generar_ejemplos(ruta, n=10, seed=42)  (solo prompts, no llama a los nodos)

La `tarea` es el objeto canónico del trabajo: lleva la familia, la pregunta, el
contexto/foco, las cartas dibujadas y, en `calculos`, los datos deterministas.
`verificar_lectura` se apoya en `tarea` (cartas, universo_cartas y calculos).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAMILIAS = (
    "tarot_1", "tarot_2", "tarot_3", "cruz_celta", "tarot_pregunta",
    "astro_natal", "sinastria", "numerologia", "lectura_completa",
    "multiturno", "etica",
    "espanola_1", "espanola_3", "espanola_5", "espanola_7",
    "transitos", "revolucion_solar", "biorritmos", "fuera_alcance",
)

FAMILIAS_ESPAÑOLA = ("espanola_1", "espanola_3", "espanola_5", "espanola_7")

# Familias de tirada: si la reconstrucción no recupera las cartas, al menos se
# revisan las cartas inventadas (cruz_celta y lectura_completa largas).
FAMILIAS_TIRADA = ("tarot_1", "tarot_2", "tarot_3", "cruz_celta",
                   "tarot_pregunta", "lectura_completa", "multiturno") \
    + FAMILIAS_ESPAÑOLA

# Familias sin tirada en las que Sol/Luna pueden ser astros, no cartas.
FAMILIAS_ASTRO = ("astro_natal", "sinastria", "transitos", "revolucion_solar")
FAMILIAS_SIN_CARTAS = ("astro_natal", "sinastria", "numerologia",
                       "transitos", "revolucion_solar", "biorritmos")

# Familias de tirada larga con esquema duro por posiciones (diagnóstico T72:
# sin límite por sección el modelo se extendía en las primeras posiciones y
# truncaba antes de cubrir la tirada; el esquema acota y obliga a cerrar).
FAMILIAS_ESQUEMA = ("cruz_celta", "espanola_5", "espanola_7")

POSICIONES_ESPAÑOLA = {
    "espanola_3": ["pasado", "presente", "futuro"],
    "espanola_5": ["situación", "obstáculo", "pasado", "futuro", "resultado"],
    "espanola_7": ["base", "pasado", "presente", "futuro", "entorno", "consejo", "resultado"],
}

LIMITE_POSICION_CHARS = 1200
LIMITE_SINTESIS_CHARS = 800

# max_tokens recomendado por familia, calculado desde longitudes reales del
# piloto: 2,05 chars/token de media en español (cortes observados a 4.173-4.428
# chars con 2.048 tokens). Presupuesto = secciones × ~300 chars + cabeceras +
# síntesis, con margen ×1,6 y redondeado. Ver docs/FASE1_TIRADAS_LARGAS.md.
RECOMENDACION_MAX_TOKENS = {
    "tarot_1": 1536,
    "tarot_pregunta": 1536,
    "etica": 1536,
    "tarot_2": 2048,
    "multiturno": 2048,
    "numerologia": 2048,
    "espanola_1": 1536,
    "tarot_3": 2560,
    "espanola_3": 2560,
    "astro_natal": 3072,
    "espanola_5": 4096,
    "sinastria": 4096,
    "espanola_7": 5120,
    "cruz_celta": 6144,
    "lectura_completa": 6144,
    "transitos": 3072,
    "revolucion_solar": 3072,
    "biorritmos": 2048,
    "fuera_alcance": 1536,
}

ZODIACO = {
    "aries", "tauro", "gemini", "geminis", "cancer", "leo", "virgo", "libra",
    "escorpio", "sagitario", "capricornio", "acuario", "piscis",
}

CABECERA_REFERENCIA = (
    "Referencia (significados de la tradición; úsalos como base y no inventes otros):"
)

SYSTEM = (
    "Eres una tarotista, astróloga y numeróloga profesional con más de veinte años de "
    "experiencia. Escribes en español estándar, con un tono cercano y empático. "
    "Interpretas a partir de la Referencia y de los datos calculados que se te dan, sin "
    "inventar cartas, signos, casas ni números: solo existen los que aparecen en la "
    "consulta, con la orientación indicada. Hablas de tendencias y posibilidades, nunca "
    "de certezas absolutas. No haces diagnósticos médicos, legales ni financieros ni "
    "prometes resultados ni garantías; cuando algo excede la lectura, derivas con cuidado "
    "a un profesional. Si la Referencia señala discrepancias entre tradiciones, las "
    "mencionas con honestidad en lugar de ocultarlas."
)

APERTURAS_VETADAS = (
    "Claro, con gusto te acompaño en esta lectura",
    "Claro, te acompaño en esta lectura",
    "Querido consultante, gracias por compartir tu pregunta conmigo",
    "Querido/a consultante, gracias por compartir tu pregunta conmigo",
    "Querido consultante, gracias por compartir tu carta conmigo",
    "Querido consultante, gracias por compartir tu carta natal conmigo",
    "Qué hermosa carta tienes, y qué pregunta tan profunda",
    "Qué hermosa carta y qué pregunta tan profunda",
    "Qué hermosa consulta me traes hoy",
    "Hola, gracias por compartir tu consulta",
    "Hola, querido consultante",
)

CIERRES_VETADOS = (
    "Estoy aquí para acompañarte",
    "Estoy aquí para lo que necesites",
    "Un abrazo cálido",
    "¿Hay algo más que quieras explorar sobre esta lectura?",
    "Con cariño y respeto, tu tarotista y astróloga",
    "Con cariño y luz, tu tarotista y astróloga",
    "Con cariño, tu tarotista",
)

MULETILLAS_VETADAS = (
    "estoy aquí para acompañarte",
    "es importante que",
    "recuerda que esto es una tendencia",
    "no es una sentencia",
    "en el fondo",
    "desde el corazón",
    "vamos a mirar con calma",
    "luz al final",
    "como quien hojea",
    "hilo dorado",
    "respira hondo",
    "el universo no te abandona",
    "confía en el proceso",
    "todo sucede por una razón",
)

ESTILOS = (
    {
        "nombre": "directo",
        "apertura": "entra en la interpretación sin saludo ni fórmula de cortesía",
        "desarrollo": "frases claras y concretas, con pocos rodeos",
        "cierre": "termina con una idea útil, sin pregunta retórica ni firma",
    },
    {
        "nombre": "narrativo",
        "apertura": "abre con un pequeño relato sobre la situación que describe la tirada",
        "desarrollo": "encadena las cartas como momentos de una historia",
        "cierre": "cierra la historia con una imagen sobria, sin moraleja",
    },
    {
        "nombre": "imagen_simbolica",
        "apertura": "abre con una imagen simbólica propia de la carta o del naipe",
        "desarrollo": "traduce cada símbolo a la vida cotidiana del consultante",
        "cierre": "cierra con una imagen breve que resuma la lectura",
    },
    {
        "nombre": "pregunta_abierta",
        "apertura": "abre con una pregunta abierta que nazca de la tirada",
        "desarrollo": "responde esa pregunta con lo que muestran las cartas",
        "cierre": "cierra con una invitación a observar, sin interrogatorio final",
    },
    {
        "nombre": "consejo_primero",
        "apertura": "empieza por el consejo principal que se desprende de la tirada",
        "desarrollo": "justifica ese consejo con las cartas y el contexto",
        "cierre": "cierra con una condición práctica para llevarlo a cabo",
    },
    {
        "nombre": "conversacional",
        "apertura": "habla como en una conversación tranquila, sin fórmulas de recepción",
        "desarrollo": "alterna observación e interpretación con un tono cercano",
        "cierre": "cierra de forma natural, sin despedida protocolaria",
    },
    {
        "nombre": "sobrio",
        "apertura": "entra con una observación sobria y precisa sobre la tirada",
        "desarrollo": "prioriza claridad y contención, sin adornos",
        "cierre": "cierra con una síntesis breve y seca",
    },
    {
        "nombre": "sensorial",
        "apertura": "abre con una sensación concreta que evoque la carta",
        "desarrollo": "usa detalles sensoriales sin caer en tópicos",
        "cierre": "cierra con una sensación que deje poso, sin promesas",
    },
    {
        "nombre": "contraste",
        "apertura": "abre contrastando dos fuerzas que aparecen en la tirada",
        "desarrollo": "muestra cómo se equilibran o chocan esas fuerzas",
        "cierre": "cierra con el punto de equilibrio posible",
    },
    {
        "nombre": "escena_cotidiana",
        "apertura": "sitúa la lectura en una escena cotidiana reconocible",
        "desarrollo": "interpreta las cartas desde esa escena, sin alegorías huecas",
        "cierre": "cierra volviendo a la escena con una idea práctica",
    },
    {
        "nombre": "carta_central",
        "apertura": "abre por la carta que consideras central y explica por qué",
        "desarrollo": "ordena el resto de la tirada alrededor de esa carta",
        "cierre": "cierra con lo que esa carta central deja como tarea",
    },
    {
        "nombre": "practico",
        "apertura": "abre con lo que la persona puede hacer ya, según la tirada",
        "desarrollo": "conecta cada carta con un paso concreto y realista",
        "cierre": "cierra con el paso más pequeño y útil, sin garantías",
    },
)

_ESTILOS_POR_NOMBRE = {e["nombre"]: e for e in ESTILOS}

INSTRUCCION_ESTILO = (
    "VETOS DE ESTILO (obligatorios en esta lectura):\n"
    "- No empieces con ninguna de estas fórmulas: "
    + "; ".join(f"«{a}»" for a in APERTURAS_VETADAS)
    + ".\n- No cierres con ninguna de estas fórmulas ni con una firma: "
    + "; ".join(f"«{c}»" for c in CIERRES_VETADOS)
    + ".\n- No uses estas muletillas: "
    + "; ".join(f"«{m}»" for m in MULETILLAS_VETADAS)
    + ".\n- No atribuyas género al consultante si el prompt no lo indica; evita "
    "«Querido/a» y usa fórmulas neutras.\n"
    "- No dejes paréntesis vacíos ni copies la ficha técnica del prompt "
    "(«Datos de nacimiento: ...», «Posiciones:», «Aspectos:»).\n"
    "- No conviertas la lectura en una lista de viñetas si el esquema pide prosa."
)

INSTRUCCIONES = {
    "tarot_1": "Interpreta la carta para esta persona, en el contexto indicado.",
    "tarot_2": "Interpreta la combinación de las dos cartas.",
    "tarot_3": "Interpreta la tirada completa, relacionando las tres posiciones.",
    "cruz_celta": "Interpreta la tirada completa de la Cruz Celta.",
    "tarot_pregunta": "Responde a la pregunta a partir de la carta.",
    "astro_natal": "Interpreta la carta natal centrándote en el ámbito preguntado.",
    "sinastria": "Compara ambas cartas e interpreta la relación.",
    "numerologia": "Interpreta los números calculados.",
    "lectura_completa": "Integra las tres técnicas en una lectura coherente y personalizada.",
    "multiturno": "Interpreta la carta para esta persona, en el contexto indicado.",
    "etica": (
        "Responde con honestidad y empatía, marcando los límites de la lectura y "
        "derivando a un profesional cuando corresponda."
    ),
    "espanola_1": "Interpreta el naipe para esta persona, en el contexto indicado.",
    "espanola_3": "Interpreta la tirada completa, relacionando las tres posiciones.",
    "espanola_5": "Interpreta la tirada en cruz completa, relacionando las cinco posiciones.",
    "espanola_7": "Interpreta la tirada completa, relacionando las siete posiciones.",
    "transitos": "Interpreta los tránsitos indicados, relacionándolos con la carta natal.",
    "revolucion_solar": "Interpreta la revolución solar a partir de los datos indicados.",
    "biorritmos": "Interpreta los tres ciclos con los porcentajes indicados, sin inventar cifras.",
    "fuera_alcance": (
        "Explica con claridad que esa técnica no forma parte de tu alcance (tarot, "
        "baraja española, astrología y numerología), no inventes datos y ofrece una "
        "alternativa dentro de esas técnicas si tiene sentido."
    ),
}

# Esquema duro de lectura_completa: el piloto mostraba que la carta natal se
# desbordaba listando aspectos y la lectura no llegaba a cubrir el tarot.
_ESQUEMA_COMPLETA = """ESQUEMA OBLIGATORIO (cuatro secciones, en este orden y con estas cabeceras):
## Carta natal
## Tirada de tres cartas
## Numerología
## Síntesis

Reglas:
- En «Carta natal» (máximo 600 caracteres) interpreta solo Sol, Luna, Ascendente y el foco de la pregunta; NO hagas listas de aspectos ni de posiciones planetarias.
- En «Tirada de tres cartas» dedica un párrafo de 150 a 300 caracteres a cada carta con su posición (pasado, presente, futuro), nombrándola cada vez con su nombre exacto y su orientación.
- En «Numerología» (máximo 400 caracteres) usa los números calculados que se dan, sin contradecirlos.
- En «Síntesis» (máximo 400 caracteres) ata las tres técnicas, da un consejo y cierra la lectura con una frase final.
- No menciones naipes ni arcanos distintos de los tres dibujados, ni otros signos o números que no estén en los datos."""

# Promesas y afirmaciones vedadas (diagnóstico/promesa médica, muerte, garantías,
# lotería). Se descartan cuando van negadas inmediatamente antes.
_PROMESAS_VEDADAS = [
    r"vas a curar",
    r"\bcurar[aá]s\b",
    r"\bsanar[aá]s\b",
    r"quedar[aá]s?\s+curad",
    r"(puedes|puede)\s+dejar\s+(la|tu)\s+medicaci[oó]n",
    r"\bdeja\s+(la|tu)\s+medicaci[oó]n",
    r"(?:puedes|puede|pod[eé]is|pueden|podr[aá]s|podr[eé]is)\s+"
    r"dejar(?:[aá]s|eis|éis)?\s+de\s+(?:tomar|llevar)",
    r"\b(?:dejar[aá]s?|dejar[eé]is|abandonar[aá]s?|abandonar[eé]is|"
    r"suspender[aá]s?|suspender[eé]is)\s+(?:el|la|tu|su)?\s*"
    r"(?:tratamiento|medicaci[oó]n|medicamentos?)",
    r"\bno\s+necesitar[aá]s\s+(?:el\s+)?"
    r"(?:m[eé]dico|tratamiento|medicaci[oó]n|ir\s+al\s+m[eé]dico)",
    r"\bno\s+necesitas\s+(el\s+)?(m[eé]dico|ir\s+al\s+m[eé]dico)",
    r"\b(?:deber[ií]as|tienes\s+que|debes|deber[ií]ais|ten[eé]is\s+que)\s+"
    r"(?:dejar|abandonar|suspender)\s+(?:el|la|tu|su)?\s*"
    r"(?:tratamiento|medicaci[oó]n|medicamentos?)",
    r"\bdeja\s+(?:el|tu)\s+tratamiento\b",
    # Diagnósticos médicos y certezas sobre terceros.
    r"\btienes\s+(?:una\s+)?(?:depresi[oó]n|ansiedad|c[aá]ncer|diabetes|"
    r"trastorno\s+\w+|enfermedad\s+(?:grave|terminal))",
    r"\b(?:padeces|sufres)\s+(?:de\s+)?(?:depresi[oó]n|ansiedad|c[aá]ncer|"
    r"diabetes|trastorno\s+\w+)",
    r"\best[aá]s\s+embarazada\b",
    r"\b(?:tu|su)\s+pareja\s+(?:te|le)\s+enga[ñn]a\s+"
    r"(?:seguro|fijo|con\s+seguridad)\b",
    r"\b(?:seguro|sin\s+duda|con\s+seguridad)\s+que\s+(?:tu|su)\s+pareja\s+"
    r"(?:te|le)\s+enga[ñn]a\b",
    r"\bvas\s+a\s+divorciarte\b",
    r"\b(?:os\s+vais|se\s+van)\s+a\s+divorciar\b",
    r"vas\s+a\s+morir",
    r"\bmorir[aá]s\b",
    r"fecha\s+de\s+(tu|su)\s+muerte",
    r"tiempo\s+de\s+vida\s+(le|te)\s+queda",
    r"(te\s+)?garantizo",
    r"garant[ií]a\s+(de\s+)?(que|por\s+escrito)",
    r"100\s*%\s+seguro",
    r"n[uú]meros\s+ganadores",
    r"n[uú]meros\s+de\s+la\s+loter[ií]a",
]

# Juego y apuestas: queda vedado prometer o recomendar cualquier variante.
_JUEGO_VEDADO = [
    r"\bloter[ií]a\b",
    r"\bquinielas?\b",
    r"\bapuestas?\b",
    r"\bprimitiva\b",
    r"\bd[eé]cimos?\b",
]

# Artículos y preposiciones: no cuentan como nombre propio de una carta.
_ARTICULOS = {"el", "la", "los", "las", "un", "una", "unos", "unas"}
_PREPOS = {"de", "del", "a", "al", "en", "con", "y", "e", "u"}
_LETRAS = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"

# El valor puede venir pegado a la etiqueta («camino de vida 7») o en frase
# natural («tu camino de vida es el 8»). `\d{1,2}` evita capturar un año de
# cuatro cifras como si fuera el número calculado.
_NEXO_NUM = (
    r"(?:(?:es|ser[aá]|corresponde\s+al|marca\s+el|da(?:r[aá])?|arroja|"
    r"indica|resulta\s+en|equivale\s+a)\s+(?:el\s+)?)?"
)
_VERIF_NUM = [
    ("año personal",
     r"año\s*personal\s*(?:(?:\d{4})\s*[:\-–]\s*|[:\-–]\s*)?"
     + _NEXO_NUM + r"(\d{1,2})(?!\d)",
     "anio_personal"),
    ("camino de vida", r"camino\s*de\s*vida\s*" + _NEXO_NUM + r"(\d{1,2})(?!\d)",
     "camino_de_vida"),
    ("expresión", r"expresi[oó]n\s*" + _NEXO_NUM + r"(\d{1,2})(?!\d)", "expresion"),
    ("alma", r"alma\s*" + _NEXO_NUM + r"(\d{1,2})(?!\d)", "alma"),
    ("personalidad", r"personalidad\s*" + _NEXO_NUM + r"(\d{1,2})(?!\d)",
     "personalidad"),
]


def _norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def _unir(frases):
    limpias = [str(f).strip().rstrip(".").strip() for f in frases]
    limpias = [f for f in limpias if f]
    return ". ".join(limpias) + "." if limpias else ""


def _nota_discrepancia(entry):
    """Nota de discrepancia entre tradiciones si la KB la trae (lista o dict)."""
    if not isinstance(entry, dict):
        return ""
    disc = entry.get("discrepancias")
    if isinstance(disc, (list, tuple)) and disc:
        return "Discrepancia entre tradiciones: " + "; ".join(str(d) for d in disc)
    trad = entry.get("tradiciones")
    if isinstance(trad, dict) and len(trad) > 1:
        partes = [f"{k}: {v}" for k, v in trad.items()]
        return "Según las tradiciones (" + "; ".join(partes) + ")."
    return ""


# --------------------------------------------------------------------------- #
# Formateo de datos calculados
# --------------------------------------------------------------------------- #
def _fmt_cartas(cartas, posiciones=None):
    lineas = []
    for i, c in enumerate(cartas or []):
        orient = "invertida" if c.get("invertida") else "al derecho"
        if posiciones and i < len(posiciones):
            etiqueta = f"{posiciones[i]}: "
        elif len(cartas) > 1:
            etiqueta = f"Carta {i + 1}: "
        else:
            etiqueta = "Carta: "
        lineas.append(f"{etiqueta}{c.get('nombre', '?')} ({orient})")
    return "\n".join(lineas)


def _fmt_carta_natal(carta, ciudad="", pais=""):
    carta = carta or {}
    lugar = f", {ciudad} ({pais})" if ciudad else ""
    lineas = [f"Datos de nacimiento: {carta.get('fecha', '?')}, {carta.get('hora', '?')}{lugar}."]
    lineas.append("Posiciones:")
    for nombre, p in (carta.get("planetas") or {}).items():
        casa = p.get("casa")
        extra = f" (casa {casa})" if casa else ""
        lineas.append(f"- {nombre}: {p.get('signo', '?')} {p.get('grados', '')}{extra}")
    asc = carta.get("ascendente") or {}
    lineas.append(f"- Ascendente: {asc.get('signo', '?')} {asc.get('grados', '')}")
    mc = carta.get("mc") or {}
    if mc:
        lineas.append(f"- Medio Cielo: {mc.get('signo', '?')} {mc.get('grados', '')}")
    asp = carta.get("aspectos") or []
    if asp:
        lineas.append(
            "Aspectos: "
            + "; ".join(f"{a.get('a')} {a.get('aspecto')} {a.get('b')}" for a in asp)
            + "."
        )
    return "\n".join(lineas)


def _fmt_numerologia(num):
    num = num or {}
    etiquetas = [
        ("Camino de vida", "camino_de_vida"),
        ("Destino/expresión", "expresion"),
        ("Alma (vocales)", "alma"),
        ("Personalidad (consonantes)", "personalidad"),
        ("Año personal 2026", "anio_personal"),
    ]
    lineas = ["Datos numerológicos calculados:"]
    for etiqueta, key in etiquetas:
        v = num.get(key)
        if v is not None:
            lineas.append(f"- {etiqueta}: {v}")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- #
# Referencia desde la KB
# --------------------------------------------------------------------------- #
def _ref_tarot(cartas, kb_tarot, contexto=None):
    por = {
        _norm(c["nombre"]): c
        for c in (kb_tarot.get("mayores", []) + kb_tarot.get("menores", []))
    }
    lineas = []
    for c in cartas or []:
        kb = por.get(_norm(c.get("nombre")))
        if not kb:
            continue
        if c.get("invertida"):
            texto = kb.get("invertida") or kb.get("significado", "")
            orient = "invertida"
        else:
            texto = kb.get("significado", "")
            orient = "al derecho"
        frases = [f"- {c.get('nombre')} ({orient}): {texto}"]
        if contexto:
            ctx = (kb.get("contextos") or {}).get(contexto)
            if ctx:
                frases.append(f"En {contexto}: {ctx}")
        claves = ", ".join(kb.get("palabras_clave", []))
        if claves:
            frases.append(f"Palabras clave: {claves}")
        disc = _nota_discrepancia(kb)
        if disc:
            frases.append(disc)
        lineas.append(_unir(frases))
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def _ref_baraja(cartas, kb_baraja, contexto=None):
    naipes = kb_baraja.get("naipes", []) if isinstance(kb_baraja, dict) else list(kb_baraja or [])
    por = {_norm(c["nombre"]): c for c in naipes}
    lineas = []
    for c in cartas or []:
        kb = por.get(_norm(c.get("nombre")))
        if not kb:
            continue
        if c.get("invertida"):
            texto = kb.get("invertida") or kb.get("significado", "")
            orient = "invertida"
        else:
            texto = kb.get("significado", "")
            orient = "al derecho"
        frases = [f"- {c.get('nombre')} ({orient}): {texto}"]
        if contexto:
            ctx = (kb.get("contextos") or {}).get(contexto)
            if ctx:
                frases.append(f"En {contexto}: {ctx}")
        claves = ", ".join(kb.get("palabras_clave", []))
        if claves:
            frases.append(f"Palabras clave: {claves}")
        disc = _nota_discrepancia(kb)
        if disc:
            frases.append(disc)
        lineas.append(_unir(frases))
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def _ref_astro(carta, kb_astro):
    carta = carta or {}
    signos = {_norm(s["nombre"]): s for s in kb_astro.get("signos", [])}
    planetas = {_norm(p["nombre"]): p for p in kb_astro.get("planetas", [])}
    casas = {str(h.get("numero")): h for h in kb_astro.get("casas", [])}
    lineas = []
    for etiqueta, signo in (
        ("Sol", (carta.get("planetas", {}).get("Sol") or {}).get("signo")),
        ("Luna", (carta.get("planetas", {}).get("Luna") or {}).get("signo")),
        ("Ascendente", (carta.get("ascendente") or {}).get("signo")),
    ):
        s = signos.get(_norm(signo)) if signo else None
        if not s:
            continue
        frases = [
            f"- {etiqueta} en {signo}: elemento {s.get('elemento', 'sin dato')}, "
            f"regente {s.get('regente', 'sin dato')}"
        ]
        rt = s.get("regente_tradicional")
        if rt and rt != s.get("regente"):
            frases.append(f"regencia tradicional: {rt} (moderna: {s.get('regente')})")
        claves = ", ".join(s.get("palabras_clave", []))
        if claves:
            frases.append(f"palabras clave: {claves}")
        lineas.append(_unir(frases))
    for nombre, datos in (carta.get("planetas") or {}).items():
        pk = planetas.get(_norm(nombre))
        if pk and pk.get("simboliza"):
            lineas.append(f"- {nombre}: {pk['simboliza']}.")
    for nombre in ("Sol", "Luna", "Venus"):
        datos = carta.get("planetas", {}).get(nombre)
        if datos:
            h = casas.get(str(datos.get("casa")))
            if h and h.get("area"):
                lineas.append(f"- Casa {datos.get('casa')} de {nombre}: {h['area']}.")
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def _ref_numerologia(num, kb_num):
    num = num or {}
    por = {e.get("numero"): e for e in kb_num}
    etiquetas = [
        ("camino de vida", "camino_de_vida"),
        ("destino/expresión", "expresion"),
        ("alma (vocales)", "alma"),
        ("personalidad (consonantes)", "personalidad"),
        ("año personal", "anio_personal"),
    ]
    lineas = []
    for etiqueta, key in etiquetas:
        n = num.get(key)
        if n is None:
            continue
        e = por.get(n)
        if not e:
            continue
        claves = ", ".join(e.get("palabras_clave", []))
        areas = e.get("areas") or {}
        area_txt = "; ".join(f"{k}: {v}" for k, v in areas.items())
        linea = f"- {n} en {etiqueta}: {claves}."
        if area_txt:
            linea += f" Áreas: {area_txt}."
        disc = _nota_discrepancia(e)
        if disc:
            linea += f" {disc}"
        lineas.append(linea)
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


# --------------------------------------------------------------------------- #
# Cuerpo del prompt (petición + datos calculados)
# --------------------------------------------------------------------------- #
def _cuerpo(tarea, calc):
    f = tarea.get("familia", "")
    q = tarea.get("pregunta", "")
    ctx = tarea.get("contexto")

    if f in ("tarot_1", "tarot_pregunta", "multiturno"):
        cuerpo = f"Tirada de una carta de tarot.\n\n{_fmt_cartas(tarea.get('cartas'))}"
        if ctx:
            cuerpo += f"\nContexto: {ctx}."
        return cuerpo + f'\nPregunta del consultante: "{q}"'

    if f in ("tarot_2", "tarot_3", "cruz_celta"):
        titulos = {
            "tarot_2": "Tirada de dos cartas de tarot.",
            "tarot_3": "Tirada de tres cartas (pasado, presente y futuro).",
            "cruz_celta": "Tirada de la Cruz Celta (diez cartas).",
        }
        cuerpo = f"{titulos[f]}\n\n{_fmt_cartas(tarea.get('cartas'), tarea.get('posiciones'))}"
        if ctx:
            cuerpo += f"\nContexto: {ctx}."
        return cuerpo + f'\nPregunta del consultante: "{q}"'

    if f in FAMILIAS_ESPAÑOLA:
        titulos = {
            "espanola_1": "Tirada de una carta de la baraja española (40 naipes).",
            "espanola_3": "Tirada de tres cartas de la baraja española (pasado, presente y futuro).",
            "espanola_5": "Tirada en cruz de cinco cartas de la baraja española.",
            "espanola_7": "Tirada de siete cartas de la baraja española.",
        }
        cuerpo = f"{titulos[f]}\n\n{_fmt_cartas(tarea.get('cartas'), tarea.get('posiciones'))}"
        cuerpo += "\nBaraja española de 40 naipes: no es tarot ni baraja francesa; no la mezcles."
        if ctx:
            cuerpo += f"\nContexto: {ctx}."
        return cuerpo + f'\nPregunta del consultante: "{q}"'

    if f == "astro_natal":
        cuerpo = (
            "Lectura de carta natal.\n\n"
            + _fmt_carta_natal(calc.get("carta_natal"), tarea.get("ciudad", ""), tarea.get("pais", ""))
            + f'\nPregunta del consultante: "{q}"'
        )
        return cuerpo

    if f == "sinastria":
        return (
            "Estudio de sinastria entre dos cartas natales.\n\n"
            "Persona A:\n"
            + _fmt_carta_natal(calc.get("carta_a"), tarea.get("ciudad_a", ""), tarea.get("pais_a", ""))
            + "\n\nPersona B:\n"
            + _fmt_carta_natal(calc.get("carta_b"), tarea.get("ciudad_b", ""), tarea.get("pais_b", ""))
            + f'\n\nPregunta: "{q}"'
        )

    if f == "numerologia":
        return (
            "Lectura numerológica.\n\n"
            + _fmt_numerologia(calc.get("numerologia"))
            + f'\nPregunta del consultante: "{q}"'
        )

    if f == "lectura_completa":
        partes = ["Lectura completa: carta natal, tarot y numerología."]
        if tarea.get("nombre"):
            partes.append(f"Consultante: {tarea['nombre']}.")
        partes.append(_fmt_carta_natal(calc.get("carta_natal"), tarea.get("ciudad", ""), tarea.get("pais", "")))
        partes.append(
            "Tirada de tres cartas:\n"
            + _fmt_cartas(tarea.get("cartas"), ["pasado", "presente", "futuro"])
        )
        partes.append(_fmt_numerologia(calc.get("numerologia")))
        return "\n\n".join(partes) + f'\n\nPregunta del consultante: "{q}"'

    if f == "etica":
        return f"Consulta delicada.\n\nPregunta del consultante: \"{q}\""

    if f == "transitos":
        import generate_tasks as gt
        return (
            "Lectura de tránsitos sobre una carta natal.\n\n"
            + _fmt_carta_natal(calc.get("carta_natal"), tarea.get("ciudad", ""), tarea.get("pais", ""))
            + "\n\n" + gt.fmt_transitos(calc.get("transitos") or {})
            + f'\n\nPregunta del consultante: "{q}"'
        )

    if f == "revolucion_solar":
        import generate_tasks as gt
        return (
            "Lectura de revolución solar.\n\n"
            + _fmt_carta_natal(calc.get("carta_natal"), tarea.get("ciudad", ""), tarea.get("pais", ""))
            + "\n\n" + gt.fmt_revolucion_solar(calc.get("revolucion_solar") or {})
            + f'\n\nPregunta del consultante: "{q}"'
        )

    if f == "biorritmos":
        datos = calc.get("biorritmos") or {}
        ciclos = datos.get("ciclos") or {}
        etiquetas = (("fisico", "Físico"), ("emocional", "Emocional"), ("intelectual", "Intelectual"))
        lineas = [
            f"- {etiq}: {ciclos[clave].get('porcentaje')}% ({ciclos[clave].get('fase')})"
            for clave, etiq in etiquetas if clave in ciclos
        ]
        return (
            "Lectura de biorritmos.\n\n"
            + f"Datos de nacimiento: {tarea.get('fecha_nacimiento', '')}, {tarea.get('hora', '')}.\n"
            + f"Biorritmos para el {datos.get('fecha', '')}:\n"
            + "\n".join(lineas)
            + f'\n\nPregunta del consultante: "{q}"'
        )

    if f == "fuera_alcance":
        return f"Consulta fuera de alcance.\n\nPregunta del consultante: \"{q}\""

    return f'Consulta.\n\nPregunta del consultante: "{q}"'


def _referencia(tarea, kb, calc):
    f = tarea.get("familia", "")
    kb_tarot = kb.get("tarot", {})
    kb_astro = kb.get("astrologia", {})
    kb_num = kb.get("numerologia", [])
    ctx = tarea.get("contexto")

    if f in ("tarot_1", "tarot_2", "tarot_3", "cruz_celta", "tarot_pregunta", "multiturno"):
        return _ref_tarot(tarea.get("cartas"), kb_tarot, ctx)
    if f in FAMILIAS_ESPAÑOLA:
        return _ref_baraja(tarea.get("cartas"), kb.get("baraja", {}), ctx)
    if f == "astro_natal":
        return _ref_astro(calc.get("carta_natal"), kb_astro)
    if f == "sinastria":
        refs = []
        ra = _ref_astro(calc.get("carta_a"), kb_astro)
        rb = _ref_astro(calc.get("carta_b"), kb_astro)
        if ra:
            refs.append("Referencia de la persona A:\n" + ra)
        if rb:
            refs.append("Referencia de la persona B:\n" + rb)
        return "\n\n".join(refs)
    if f == "numerologia":
        return _ref_numerologia(calc.get("numerologia"), kb_num)
    if f == "lectura_completa":
        refs = [r for r in (
            _ref_astro(calc.get("carta_natal"), kb_astro),
            _ref_tarot(tarea.get("cartas"), kb_tarot, ctx),
            _ref_numerologia(calc.get("numerologia"), kb_num),
        ) if r]
        return "\n\n".join(refs)
    if f in ("transitos", "revolucion_solar"):
        return _ref_astro(calc.get("carta_natal"), kb_astro)
    return ""


def _esquema_texto(tarea):
    """Esquema obligatorio para tiradas largas y lectura completa (o '' si no aplica)."""
    f = tarea.get("familia", "")
    if f == "lectura_completa":
        return _ESQUEMA_COMPLETA
    if f not in FAMILIAS_ESQUEMA:
        return ""
    cartas = tarea.get("cartas") or []
    posiciones = tarea.get("posiciones") or []
    n = len(cartas)
    lineas = [
        f"ESQUEMA OBLIGATORIO ({n} secciones numeradas y una síntesis final). "
        "Copia cada cabecera en su propia línea, en este orden exacto:",
    ]
    for i, c in enumerate(cartas):
        orient = "invertida" if c.get("invertida") else "al derecho"
        pos = posiciones[i] if i < len(posiciones) else f"posición {i + 1}"
        lineas.append(f"## {i + 1}. {pos} — {c.get('nombre', '?')} ({orient})")
    lineas.append("## Síntesis")
    lineas += [
        "",
        "Reglas:",
        f"- Después de cada cabecera, escribe entre 150 y 300 caracteres de interpretación "
        f"dedicados SOLO a esa posición. No te extiendas más: el lector debe poder recorrer "
        f"las {n} posiciones sin que se agote el espacio.",
        f"- Solo existen las {n} cartas dibujadas, con la orientación indicada. No menciones "
        "ninguna otra carta, ni siquiera como comparación o ejemplo.",
        "- En «Síntesis» (máximo 400 caracteres) ata las posiciones en una idea central, "
        "da un consejo práctico y cierra la lectura con una frase final.",
    ]
    return "\n".join(lineas)


def _indice_estilo(valor):
    clave = "0" if valor is None else str(valor)
    digest = hashlib.sha256(clave.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(ESTILOS)


def estilo_para_job(job_id):
    """Devuelve el estilo determinista que corresponde a un id de job."""
    return ESTILOS[_indice_estilo(job_id)]


def _resolver_estilo(estilo, semilla, tarea):
    if estilo is None:
        return None
    if isinstance(estilo, dict):
        nombre = estilo.get("nombre")
        if nombre not in _ESTILOS_POR_NOMBRE:
            raise ValueError(f"Estilo no válido: {nombre!r}")
        return _ESTILOS_POR_NOMBRE[nombre]
    nombre = str(estilo).strip().lower()
    if nombre in ("", "base", "none"):
        return None
    if nombre in ("auto", "variedad"):
        if semilla is None:
            return estilo_para_job(tarea.get("id"))
        if isinstance(semilla, int):
            return ESTILOS[semilla % len(ESTILOS)]
        return estilo_para_job(semilla)
    if nombre not in _ESTILOS_POR_NOMBRE:
        raise ValueError(f"Estilo no válido: {estilo!r}")
    return _ESTILOS_POR_NOMBRE[nombre]


def _bloque_estilo(estilo):
    return (
        "ESTILO DE ESTA LECTURA (no cambia el esquema, la Referencia ni los datos):\n"
        f"- Apertura: {estilo['apertura']}.\n"
        f"- Desarrollo: {estilo['desarrollo']}.\n"
        f"- Cierre: {estilo['cierre']}.\n\n"
        + INSTRUCCION_ESTILO
    )


def puntuar_estilo(respuesta, bloque=None):
    """Puntúa fórmulas de estilo sin rechazar la lectura."""
    texto = "" if respuesta is None else str(respuesta)
    n = _norm(texto)
    inicio = n[:400].lstrip(" #*-_\t\n")
    final = n[-350:]
    aperturas = [frase for frase in APERTURAS_VETADAS
                 if inicio.startswith(_norm(frase))]
    cierres = [frase for frase in CIERRES_VETADOS
               if _norm(frase) in final]
    muletillas = [frase for frase in MULETILLAS_VETADAS
                  if _norm(frase) in n]
    motivos = []
    if aperturas:
        motivos.append("apertura_vetada:" + aperturas[0])
    if cierres:
        motivos.append("cierre_vetado:" + cierres[0])
    motivos.extend("muletilla:" + m for m in muletillas)
    puntos = 3 * len(aperturas) + 2 * len(cierres) + len(muletillas)
    return {
        "puntos": puntos,
        "motivos": motivos,
        "apertura_vetada": bool(aperturas),
        "cierre_vetado": bool(cierres),
        "muletillas": muletillas,
        "bloque": bloque,
    }


def construir_prompt(tarea, kb, calculos=None, estilo=None, semilla=None):
    """Devuelve {"system", "user"} con estilo, Referencia de la KB y datos calculados."""
    calc = calculos if calculos is not None else (tarea.get("calculos") or {})
    f = tarea.get("familia", "")
    cuerpo = _cuerpo(tarea, calc)
    esquema = _esquema_texto(tarea)
    referencia = _referencia(tarea, kb, calc)
    instruccion = INSTRUCCIONES.get(f, "Interpreta la consulta con las técnicas indicadas.")
    elegido = _resolver_estilo(estilo, semilla, tarea)
    bloque_estilo = _bloque_estilo(elegido) if elegido else ""
    user = "\n\n".join(
        p for p in (cuerpo, esquema, referencia, instruccion, bloque_estilo) if p)
    return {"system": SYSTEM, "user": user}


# --------------------------------------------------------------------------- #
# Verificador determinista de la lectura
# --------------------------------------------------------------------------- #
def _tiene_inversion(texto):
    n = _norm(texto)
    return ("invertid" in n) or ("al reves" in n)


def _negado(texto, inicio):
    """True si el match cae bajo una negación de la misma cláusula.

    Mira hasta 40 caracteres atrás, cortando en el último signo de puntuación
    fuerte o coma: cubre «No puedo darte números de la lotería» y
    «La Luna no está invertida», sin arrastrar negaciones de otra cláusula.
    """
    pre = texto[max(0, inicio - 40):inicio]
    pre = re.split(r"[.;,:!?¡¿\n]", pre)[-1]
    return bool(re.search(r"\bno\b(?:\s+\w+){0,6}\s*$", pre, re.IGNORECASE))


# Nombre propio con artículo en mayúscula. Las cartas con rango y palo
# («el Ocho de Estrellas») las cubre `_RANGO_CARTA_RE` sin depender del artículo.
_CARTA_NOMBRE_RE = re.compile(
    r"(?<![" + _LETRAS + r"])"
    r"((?:El|La|Los|Las)\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+"
    r"(?:\s+(?:de|del)\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+)?)"
    r"(?![" + _LETRAS + r"])"
)

_RANGO_CARTA_RE = re.compile(
    r"(?<![" + _LETRAS + r"])("
    r"(?i:As|Dos|Tres|Cuatro|Cinco|Seis|Siete|Ocho|Nueve|Diez|"
    r"Sota|Caballero|Reina|Rey|Paje)\s+(?i:de)\s+"
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúñ]+)"
    r"(?![" + _LETRAS + r"])"
)

# Números fuera de los dos mazos (tarot llega a Diez; baraja, a Nueve).
_NUMERO_FUERA_RE = re.compile(
    r"(?<![" + _LETRAS + r"])("
    r"(?i:Once|Doce|Trece|Catorce|Quince|Diecis[eé]is|Diecisiete|"
    r"Dieciocho|Diecinueve|Veinte|Veintiuno|Veintid[oó]s|Treinta)"
    r"\s+(?i:de)\s+[A-Za-zÁÉÍÓÚÜÑáéíóúñ]+)"
    r"(?![" + _LETRAS + r"])"
)

_PALOS_CARTA = {
    "oros", "copas", "espadas", "bastos", "estrellas", "treboles",
    "corazones", "diamantes", "picas",
}

# Palos plausibles en otros idiomas: una construcción de carta con ellos
# («Swords of Stars», «Nine of Cups») nunca pertenece a estos mazos.
_PALOS_OTROS = {
    "swords", "cups", "wands", "pentacles", "coins", "hearts", "diamonds",
    "clubs", "spades", "stars", "chalices", "rods",
}
_RANGO_OTRO_RE = re.compile(
    r"(?<![" + _LETRAS + r"])("
    r"(?i:As|Dos|Tres|Cuatro|Cinco|Seis|Siete|Ocho|Nueve|Diez|Sota|"
    r"Caballero|Reina|Rey|Paje|Ace|Two|Three|Four|Five|Six|Seven|Eight|"
    r"Nine|Ten|Page|Knight|Queen|King|Jack)\s+(?i:de|of|di|von)\s+"
    r"[A-Za-zÁÉÍÓÚÜÑáéíóúñ]+)"
    r"(?![" + _LETRAS + r"])"
)
_PALO_DE_PALO_RE = re.compile(
    r"(?<![" + _LETRAS + r"])("
    r"(?i:Swords|Cups|Wands|Pentacles|Coins|Hearts|Diamonds|Clubs|Spades|"
    r"Stars|Chalices|Rods)\s+(?i:of|de)\s+"
    r"(?i:Swords|Cups|Wands|Pentacles|Coins|Hearts|Diamonds|Clubs|Spades|"
    r"Stars|Chalices|Rods))"
    r"(?![" + _LETRAS + r"])"
)

_GENERICOS_CARTA = {
    "carta", "cartas", "arcano", "arcanos", "tirada", "tiradas", "lectura",
    "sintesis", "consultante", "posicion", "posiciones", "signo", "signos",
    "planeta", "planetas", "casa", "casas", "ascendente", "descendente",
    "medio", "cielo", "fondo", "nodo", "nodos", "pregunta", "contexto",
    # Nombres narrativos que no son cartas (lecturas reales de fase 1).
    "tarot", "mensaje", "hilo", "tema", "historia", "respuesta", "combinacion",
    "panorama", "aprendizaje", "referencia", "orientacion", "interpretacion",
    "cuidado", "invitacion", "miedo", "energia", "fuego", "niebla", "riesgo",
    "cierre", "semilla", "espiritu", "duelo", "expansion", "puente", "ancla",
    "mascara", "descanso", "claridad", "gestion", "viaje", "bloqueo",
    "comunicacion", "retiro", "autosuficiencia", "estructura", "reconstruccion",
    "campo", "batalla", "artesano", "labrador", "maestra", "conexion",
    "universo",
}

# Posiciones de las tiradas (tarot y baraja): nunca son cartas.
_POSICIONES_CARTA = {
    "pasado", "presente", "futuro", "situacion", "obstaculo", "raiz", "meta",
    "actitud", "entorno", "esperanzas", "miedos", "resultado", "base",
    "consejo", "cercano", "posicion", "posiciones",
}


def _sin_articulo(texto):
    return re.sub(r"^(?:el|la|los|las|un|una|unos|unas)\s+", "",
                  str(texto).strip(), flags=re.IGNORECASE)


def _formas_de(elemento):
    """Nombre y sinónimos de una carta del universo (dict o cadena)."""
    if isinstance(elemento, dict):
        nombre = elemento.get("nombre")
        return [x for x in [nombre] + list(elemento.get("sinonimos") or []) if x]
    return [elemento] if elemento else []


def _nombres_conocidos(universo, drawn_todo):
    """Formas normalizadas (con y sin artículo) de las cartas del sistema."""
    conocidos = set(drawn_todo)
    for elemento in universo:
        for forma in _formas_de(elemento):
            conocidos.add(_norm(forma))
            conocidos.add(_norm(_sin_articulo(forma)))
    return conocidos


def _es_posicion(base):
    tokens = [t for t in base.split()
              if t not in _ARTICULOS and t not in _PREPOS]
    return bool(tokens) and all(t in _POSICIONES_CARTA for t in tokens)


def _cartas_inventadas(texto, conocidos, incluir_nombres=True):
    """Nombres propios con artículo que no pertenecen al universo del sistema.

    Se aceptan las posiciones de la tirada («El Pasado», «El Futuro»), las
    formas cortas y cargos de la corte («La Rueda» → La Rueda de la Fortuna,
    «La Sota», «El Rey») y los nombres narrativos («El Mensaje»). Un nombre
    con palo que no exista («El Ocho de Estrellas») sigue rechazándose.

    En lecturas largas sin cartas reconstruidas (cruz_celta, astro_natal) solo
    se revisan las construcciones de carta (rango + palo, número + palo, palos
    extranjeros): escanear nombres propios sueltos produce cientos de falsos
    positivos («La Mente», «Los Sueños», «La Cruz»).
    """
    tokens_conocidos = {
        t for nombre in conocidos for t in nombre.split()
        if t not in _ARTICULOS and t not in _PREPOS
    }
    inventadas = []
    vistas = set()

    def revisar(nombre):
        base = _norm(_sin_articulo(nombre))
        if not base or base in vistas:
            return
        if base in conocidos:
            return
        if base.split()[0] in _GENERICOS_CARTA or _es_posicion(base):
            return
        # Forma corta de una carta conocida: «La Rueda», «La Sota», «El Rey».
        if len(base.split()) == 1 and base in tokens_conocidos:
            return
        if any(k.startswith(base + " ") for k in conocidos):
            return
        vistas.add(base)
        inventadas.append(nombre)

    texto = texto or ""
    if incluir_nombres:
        for m in _CARTA_NOMBRE_RE.finditer(texto):
            revisar(m.group(1))
    for m in _RANGO_CARTA_RE.finditer(texto):
        nombre = m.group(1)
        palo = _norm(nombre).split()[-1]
        if palo in _PALOS_CARTA:
            revisar(nombre)
    for m in _NUMERO_FUERA_RE.finditer(texto):
        nombre = m.group(1)
        if _norm(nombre).split()[-1] in _PALOS_CARTA:
            revisar(nombre)
    for m in _RANGO_OTRO_RE.finditer(texto):
        nombre = m.group(1)
        if _norm(nombre).split()[-1] in _PALOS_CARTA | _PALOS_OTROS:
            revisar(nombre)
    for m in _PALO_DE_PALO_RE.finditer(texto):
        revisar(m.group(1))
    return inventadas


def _verif_cartas_inventadas(universo, texto, motivos, drawn_todo=None,
                             incluir_nombres=True):
    """Añade un motivo por cada carta que no existe en el sistema."""
    conocidos = _nombres_conocidos(universo, drawn_todo or set())
    for nombre in _cartas_inventadas(texto, conocidos, incluir_nombres):
        motivos.append(f"Menciona una carta inexistente en el sistema: {nombre}")


def _tokens_propios(nombre):
    """Tokens del nombre de la carta que son nombre propio (no artículo/preposición)."""
    props = []
    for t in str(nombre).split():
        base = _norm(t)
        if base in _ARTICULOS or base in _PREPOS:
            continue
        if t[:1].isupper():
            props.append(t)
    return props


def _mencion_carta(nombre, texto):
    """True si el texto nombra la carta como propio (no como uso común en minúscula).

    Cuenta: mayúscula inicial en el nombre propio («El Sol», «la Torre»), la forma
    «carta/arcano de X», o una lectura escrita toda en mayúsculas. No cuenta el uso
    común en minúscula («el sol», «la luna», «la torre»).
    """
    if not _tokens_propios(nombre):
        return False
    solo_mayus = not any(ch.islower() for ch in texto if ch.isalpha())
    nombre_sin_articulo = re.sub(
        r"^(?:el|la|los|las)\s+", "", str(nombre), flags=re.IGNORECASE
    )
    forma = (
        r"(?:cartas?|arcanos?)\s+(?:mayor\s+|menor\s+)?"
        r"(?:de\s+l[ao]s?\s+|de\s*l\s+|de\s+)?" + re.escape(nombre_sin_articulo)
    )
    if re.search(forma, texto, re.IGNORECASE):
        return True
    pat = (
        r"(?<![" + _LETRAS + r"])" + re.escape(nombre) + r"(?![" + _LETRAS + r"])"
    )
    nom_toks = str(nombre).split()
    for m in re.finditer(pat, texto, re.IGNORECASE):
        if solo_mayus:
            return True
        seg_toks = m.group(0).split()
        for i, nt in enumerate(nom_toks):
            base = _norm(nt)
            if base in _ARTICULOS or base in _PREPOS:
                continue
            if i < len(seg_toks) and seg_toks[i][:1].isupper():
                return True
    return False


def _presente_carta(nombre, norm):
    """True si el nombre está en el texto, tolerando el palo en singular."""
    base = _norm(nombre)
    if base and base in norm:
        return True
    partes = base.rsplit(" ", 1)
    if len(partes) == 2 and partes[1].endswith("s"):
        return (partes[0] + " " + partes[1][:-1]) in norm
    return False


def _presente_carta_any(carta, norm):
    """_presente_carta sobre el nombre y sus sinónimos (baraja española)."""
    if isinstance(carta, dict):
        candidatos = [carta.get("nombre")] + list(carta.get("sinonimos") or [])
    else:
        candidatos = [carta]
    return any(_presente_carta(x, norm) for x in candidatos if x)


_SIGNOS_ZODIACO = (
    r"aries|tauro|g[ée]minis|c[áa]ncer|leo|virgo|libra|escorpio(?:n)?|"
    r"sagitario|capricornio|acuario|piscis"
)
_RE_ASTRO_LUMINAR = re.compile(
    r"(?i)\b(?:el\s+sol|la\s+luna)\s+en\s+(?:" + _SIGNOS_ZODIACO + r")(?![" + _LETRAS + r"])"
)


def _mascara_astros(texto):
    """Blanquea las menciones astrológicas «el sol / la luna en <signo>».

    En lecturas con carta natal, El Sol y La Luna nombran astros, no arcanos:
    sin este filtro el verificador los marcaría como cartas ajenas.
    """
    return _RE_ASTRO_LUMINAR.sub(lambda m: " " * len(m.group(0)), texto)


def _inversiones_afirmadas(texto):
    """Marcas de inversión no negadas («invertida», «al revés»)."""
    return [m for m in re.finditer(r"invertid\w*|al\s+rev[eé]s", texto,
                                   re.IGNORECASE)
            if not _negado(texto, m.start())]


def _tokens_distintivos(nombre):
    return [t for t in str(nombre).split()
            if _norm(t) not in _ARTICULOS and _norm(t) not in _PREPOS
            and len(_norm(t)) >= 2]


def _marca_es_orientacion(texto, marca):
    """Descarta participios verbales y metáforas que no describen la carta."""
    antes = texto[max(0, marca.start() - 30):marca.start()]
    if re.search(
            r"\b(?:he|has|ha|hemos|hab[eé]is|han|haya|hayas|hayan|"
            r"hab[ií]a|hab[ií]as|hab[ií]amos|hab[ií]an|haber|habr[ií]a)"
            r"\s+(?:\w+\s+){0,2}$", antes, re.IGNORECASE):
        return False
    # Sustantivos comunes en minúscula («perspectiva invertida»); «El Mundo»
    # con mayúscula es la carta y no debe caer en esta lista.
    if re.search(
            r"\b(?:perspectiva|mirada|visi[oó]n|mundo|papel|rol|orden|"
            r"valores|situaci[oó]n|energ[ií]a|esfuerzo|tiempo|dinero|"
            r"recursos)\s+$", antes):
        return False
    return True


def _marcas_orientacion(cartas, texto):
    """Asigna cada marca de inversión a la última carta mencionada antes de ella.

    - Las formas cortas («la Reina», «Mundo», «el caballero») solo cuentan si no
      forman parte del nombre completo de otra carta.
    - La marca debe ir pegada a la carta («La Torre invertida», «El Sol
      (invertida)», «X en posición invertida»). Así no cuentan usos verbales
      («has invertido energía») ni metáforas («perspectiva invertida»).
    - Las anáforas («la carta invertida») no se asignan a ninguna carta.
    Devuelve {nombre_normalizado: marcada_invertida}.
    """
    solo_mayus = not any(ch.islower() for ch in texto if ch.isalpha())
    spans_full = []
    menciones = []
    for carta in cartas:
        nn = _norm(carta.get("nombre"))
        for forma in _formas_de(carta):
            pat = re.compile(
                r"(?<![" + _LETRAS + r"])" + re.escape(str(forma))
                + r"(?![" + _LETRAS + r"])", re.IGNORECASE)
            for m in pat.finditer(texto):
                if not solo_mayus:
                    props = [t for t in m.group(0).split()
                             if _norm(t) not in _ARTICULOS
                             and _norm(t) not in _PREPOS]
                    if not any(t[:1].isupper() for t in props):
                        continue
                spans_full.append((m.start(), m.end()))
                menciones.append((m.start(), m.end(), nn))
    for carta in cartas:
        nn = _norm(carta.get("nombre"))
        for token in _tokens_distintivos(carta.get("nombre")):
            pat = re.compile(
                r"(?<![" + _LETRAS + r"])" + re.escape(token)
                + r"(?![" + _LETRAS + r"])", re.IGNORECASE)
            for m in pat.finditer(texto):
                if any(a <= m.start() < b for a, b in spans_full):
                    continue
                previo = texto[max(0, m.start() - 8):m.start()]
                if (solo_mayus or m.group(0)[:1].isupper()
                        or re.search(r"(?:^|\W)(?:el|la|los|las)\s+$",
                                     previo, re.IGNORECASE)):
                    menciones.append((m.start(), m.end(), nn))
    menciones.sort(key=lambda x: x[0])
    marcas = {_norm(c.get("nombre")): False for c in cartas}
    for marca in _inversiones_afirmadas(texto):
        if not _marca_es_orientacion(texto, marca):
            continue
        if len(cartas) == 1:
            marcas[_norm(cartas[0].get("nombre"))] = True
            continue
        previas = [x for x in menciones if x[0] < marca.start()]
        if not previas:
            continue
        _ini, fin_previo, nn = previas[-1]
        entre = texto[fin_previo:marca.start()]
        pegado = bool(re.fullmatch(
            r"\s*(?:\*\*|__)?\s*"
            r"(?:(?:aparece|aparecen|aparezca|aparezcan|sale|salen|salir|"
            r"sali[oó]|est[aá]|est[aá]n|queda|quedan|incluso|tambi[eé]n|"
            r"a[uú]n|como|cuando|ahora)\s+){0,3}"
            r"(?:en\s+posici[oó]n\s+)?(?:,|:)?\s*",
            entre, re.IGNORECASE))
        parentesis = bool(re.search(r"\(\s*$", entre))
        if pegado or parentesis:
            marcas[nn] = True
    return marcas


def _verif_cartas(cartas, universo, texto, motivos, texto_ajenas=None):
    """Presencia, repetición, orientación y cartas ajenas.

    texto_ajenas: si se aporta, se usa solo para buscar menciones ajenas
    (permite ocultar los astros homónimos en lecturas con carta natal).
    """
    norm = _norm(texto)
    drawn = set()
    drawn_todo = set()
    validas = []
    for c in cartas:
        if not isinstance(c, dict) or not c.get("nombre"):
            motivos.append(f"Carta de la tirada no válida: {c!r}")
            continue
        validas.append(c)
        nn = _norm(c.get("nombre"))
        if nn in drawn:
            motivos.append(f"Carta repetida en la tirada: {c.get('nombre')}")
        drawn.add(nn)
        drawn_todo.add(nn)
        for s in c.get("sinonimos") or []:
            drawn_todo.add(_norm(s))
    for c in validas:
        if not _presente_carta_any(c, norm):
            motivos.append(f"Falta la carta de la tirada: {c.get('nombre')}")
    for_ajenas = texto if texto_ajenas is None else texto_ajenas
    for elemento in universo:
        nombre = elemento.get("nombre") if isinstance(elemento, dict) else elemento
        if not nombre:
            continue
        nn = _norm(nombre)
        if nn in drawn_todo:
            continue
        sinon = (elemento.get("sinonimos") or []) if isinstance(elemento, dict) else []
        if any(_norm(s) in drawn_todo for s in sinon):
            continue
        if nn and _mencion_carta(nombre, for_ajenas):
            motivos.append(f"Menciona carta ajena a la tirada: {nombre}")
    _verif_cartas_inventadas(universo, for_ajenas, motivos, drawn_todo)
    hay_inv = any(c.get("invertida") for c in validas)
    marcas = _marcas_orientacion(validas, texto)
    inv = any(marcas.values())
    if (not hay_inv) and inv:
        motivos.append(
            "Menciona una orientación invertida sin que haya cartas invertidas en la tirada"
        )
    for c in validas:
        marcada = marcas.get(_norm(c.get("nombre")), False)
        if c.get("invertida") and not marcada:
            motivos.append(
                f"No indica la orientación invertida de: {c.get('nombre')}")
        if (not c.get("invertida")) and marcada:
            motivos.append(
                f"Marca como invertida una carta que está al derecho: {c.get('nombre')}")


def _verif_numeros(calc, texto, motivos):
    num = (calc or {}).get("numerologia") or {}
    for etiqueta, pat, key in _VERIF_NUM:
        esperado = num.get(key)
        if esperado is None:
            continue
        for m in re.finditer(pat, texto, re.IGNORECASE):
            val = int(m.group(1))
            if key == "anio_personal" and 1000 <= val <= 2999:
                # Un año de cuatro cifras es la etiqueta («Año personal 2026»),
                # no el valor del año personal.
                continue
            if val != esperado:
                motivos.append(
                    f"Contradice el {etiqueta} calculado ({esperado}): el texto dice {val}"
                )


def _verif_sol(calc, texto, motivos):
    carta = (calc or {}).get("carta_natal") or {}
    sol = (carta.get("planetas", {}).get("Sol") or {}).get("signo")
    if not sol:
        return
    for m in re.finditer(r"\bsol\s+en\s+([a-záéíóúñ]+)", texto, re.IGNORECASE):
        tok = _norm(m.group(1))
        if tok in ZODIACO and tok != _norm(sol):
            motivos.append(
                f"Contradice el signo del Sol calculado ({sol}): el texto dice {m.group(1)}"
            )


def _verif_promesas(texto, motivos):
    for pat in _PROMESAS_VEDADAS:
        for m in re.finditer(pat, texto, re.IGNORECASE):
            if _negado(texto, m.start()):
                continue
            motivos.append(f"Promesa o diagnóstico vedado: «{m.group(0)}»")


def _verif_juego(texto, motivos):
    for pat in _JUEGO_VEDADO:
        for m in re.finditer(pat, texto, re.IGNORECASE):
            if _negado(texto, m.start()):
                continue
            motivos.append(f"Promesa vedada de juego o apuestas: «{m.group(0)}»")


_CAB_NUM = re.compile(r"(?m)^[ \t>*#-]*(\d+)[.)][ \t]+(.*)$")
_CAB_SINTESIS = re.compile(r"(?m)^[ \t>*#-]*S[ií]ntesis[ \t:.—-]*(.*)$")


def _verif_esquema(tarea, texto, motivos):
    """Exige orden, presencia de la carta y límites por sección en tiradas largas."""
    f = tarea.get("familia", "")
    if f == "lectura_completa":
        esperado = ["carta natal", "tirada de tres cartas", "numerolog", "sintesis"]
        patrones = ["carta natal", "tirada de tres cartas", "numerolog",
                    r"s[ií]ntesis"]
        posiciones = []
        for etiqueta, patron in zip(esperado, patrones):
            m = re.search(patron, texto, re.IGNORECASE)
            if not m:
                motivos.append(f"Falta la sección: {etiqueta}")
                posiciones.append(None)
            else:
                posiciones.append(m.start())
        presentes = [i for i in posiciones if i is not None]
        if presentes != sorted(presentes):
            motivos.append("Las secciones no siguen el orden esperado")
        for j, (etiqueta, inicio) in enumerate(zip(esperado, posiciones)):
            if inicio is None:
                continue
            siguientes = [p for p in posiciones[j + 1:]
                          if p is not None and p > inicio]
            fin = min(siguientes) if siguientes else len(texto)
            limite = (LIMITE_SINTESIS_CHARS if etiqueta == "sintesis"
                      else LIMITE_POSICION_CHARS)
            largo = fin - inicio
            if largo > limite:
                motivos.append(
                    f"La sección «{etiqueta}» excede el máximo de "
                    f"{limite} caracteres ({largo})"
                )
        return
    cartas = tarea.get("cartas") or []
    posiciones = tarea.get("posiciones") or []
    n = len(cartas)
    if not n:
        return
    heads = []
    for m in _CAB_NUM.finditer(texto):
        heads.append((int(m.group(1)), m.start(), m.end()))
    fin_posiciones = max((s for _num, s, _e in heads), default=0)
    msin = None
    for m in _CAB_SINTESIS.finditer(texto):
        if m.start() >= fin_posiciones:
            msin = m
            break
    vistos = {}
    for num, start, end in heads:
        if num in vistos:
            motivos.append(f"Sección {num} duplicada")
            continue
        vistos[num] = (start, end)
    primera_aparicion = []
    for num, _start, _end in heads:
        if num not in primera_aparicion:
            primera_aparicion.append(num)
    if primera_aparicion != sorted(primera_aparicion):
        motivos.append("Las secciones numeradas no siguen el orden 1 a " + str(n))
    for k in range(1, n + 1):
        etiqueta = posiciones[k - 1] if k - 1 < len(posiciones) else f"posición {k}"
        if k not in vistos:
            motivos.append(f"Falta la sección {k} ({etiqueta})")
            continue
        start, _end = vistos[k]
        siguiente = min((st for _num, st, _e in heads if st > start), default=len(texto))
        if msin and start < msin.start() < siguiente:
            siguiente = msin.start()
        segmento = texto[start:siguiente]
        c = cartas[k - 1]
        if not _presente_carta_any(c, _norm(segmento)):
            motivos.append(
                f"La sección {k} ({etiqueta}) no nombra a la carta {c.get('nombre')}"
            )
        if len(segmento) > LIMITE_POSICION_CHARS:
            motivos.append(
                f"La sección {k} ({etiqueta}) excede el máximo de "
                f"{LIMITE_POSICION_CHARS} caracteres ({len(segmento)})"
            )
    if not msin:
        motivos.append("Falta la sección de Síntesis")
    else:
        cola = texto[msin.end():]
        if len(cola) > LIMITE_SINTESIS_CHARS:
            motivos.append(
                f"La síntesis excede el máximo de {LIMITE_SINTESIS_CHARS} caracteres "
                f"({len(cola)})"
            )


_RE_PRESENCIA_TIRADA = re.compile(
    r"(?:sali[oó]|salieron|ha[n]?\s+salido|te\s+ha[n]?\s+salido|"
    r"en\s+la\s+mesa|en\s+(?:tu\s+)?tirada)",
    re.IGNORECASE)


def _mencion_explicita_carta(nombre, texto):
    """True si el texto dice «carta/arcano de X» (frente a un astro homónimo)."""
    base = re.escape(_sin_articulo(nombre))
    return bool(re.search(
        r"(?:cartas?|arcanos?)\s+(?:mayor\s+|menor\s+)?"
        r"(?:de\s+(?:la|el|los|las)\s+|del\s+|de\s+)?" + base, texto,
        re.IGNORECASE))


def _tiene_presencia_tirada(nombre, texto):
    """True si hay una marca de «carta sacada» cerca del nombre."""
    pat = re.compile(
        r"(?<![" + _LETRAS + r"])" + re.escape(str(nombre))
        + r"(?![" + _LETRAS + r"])", re.IGNORECASE)
    for m in pat.finditer(texto):
        if _RE_PRESENCIA_TIRADA.search(texto[max(0, m.start() - 40):m.end() + 80]):
            return True
    return False


def _mencion_como_tirada(nombre, texto):
    """True si la carta se presenta como sacada («carta de X», «estaba en la mesa»)."""
    return (_mencion_explicita_carta(nombre, texto)
            or _tiene_presencia_tirada(nombre, texto))


def _verif_cartas_sin_tirada(universo, texto, motivos, astro):
    """Una lectura sin tirada no debe colar cartas ajenas presentadas como sacadas.

    En astro/sinastría, «El Sol» y «La Luna» se permiten como astros salvo que
    el texto las presente explícitamente como carta. Las analogías («en el
    tarot, la carta que representa tu energía es El Colgado») no se rechazan:
    el dataset real las usa y no afirman que la carta esté en la lectura.
    """
    _verif_cartas_inventadas(universo, texto, motivos, incluir_nombres=False)
    for elemento in universo:
        nombre = elemento.get("nombre") if isinstance(elemento, dict) else elemento
        if not nombre:
            continue
        if astro and _norm(nombre) in {"el sol", "la luna"} \
                and not _tiene_presencia_tirada(nombre, texto):
            continue
        if _mencion_como_tirada(nombre, texto):
            motivos.append(
                f"Menciona carta de tarot en una lectura sin tirada: {nombre}")


_RE_TRIPLE_TRANSITO = re.compile(
    r"\b([a-z]+)\s+(?:en\s+transito\s+)?hace\s+([a-z]+)\s+a\s+(?:su|tu)\s+([a-z]+)\s+natal\b")

_RE_SOL_RS = re.compile(r"\bsol\s+(?:rs|de la revolucion)\s+(?:en\s+)?([a-z]+)\b")

_RE_ASC_RS = re.compile(r"\bascendente\s+(?:rs|de la revolucion)\s+(?:en\s+)?([a-z]+)\b")

_RE_PCT = re.compile(r"([+\-−–]?\d{1,3})\s*%")


def _pct_con_signo(m):
    """Devuelve (valor:int, tiene_signo:bool) del match de _RE_PCT."""
    s = m.group(1)
    if s[0] in "+-−–":
        return int(s[1:]) * (-1 if s[0] in "-−–" else 1), True
    return int(s), False


def _pct_contradice(c, esperado):
    """True si el % citado contradice el calculado (>5 de diferencia).

    Si el texto trae signo se compara con signo; si no lo trae, se compara la
    magnitud (p.ej. "-63%" contra -63 no contradice, y "63%" contra -63 tampoco).
    """
    valor, con_signo = _pct_con_signo(c)
    if con_signo:
        return abs(valor - int(esperado)) > 5
    return abs(valor - abs(int(esperado))) > 5

_RECHAZO_ALCANCE = re.compile(
    r"no puedo|no voy a|no es posible|no estoy (para|en condiciones)|no forma parte|"
    r"no entra dentro|queda fuera de mi alcance|no sustituye|no reemplaza|"
    r"no soy (?:m[ée]dico|profesional|sanador)|no doy|no hago|me niego|"
    r"no está en mi (?:alcance|mano)|no tengo (?:acceso|datos|forma)|no dispongo|"
    r"no es mi cometido|no corresponde|no puedo (?:garantizar|predecir|diagnosticar|asegurar|darte)",
    re.IGNORECASE)

_ALTERNATIVA_TECNICAS = re.compile(
    r"tarot|baraja|astrolog|numerolog|carta\s+natal|tr[aá]nsito|"
    r"revoluci[oó]n\s+solar|biorritmo", re.IGNORECASE)


_PLANETAS_ASTRO = ("sol", "luna", "mercurio", "venus", "marte", "jupiter",
                   "saturno", "urano", "neptuno", "pluton")
_RE_PLANETA = r"(?:" + "|".join(_PLANETAS_ASTRO) + r")"

_ANGULOS_ASPECTO = (
    (0, "conjuncion", 6), (30, "semisextil", 3), (60, "sextil", 5),
    (90, "cuadratura", 6), (120, "trigono", 6), (150, "quincuncio", 3),
    (180, "oposicion", 7),
)
_NOMBRES_ASPECTO = {
    "conjuncion": "conjuncion", "conjunto": "conjuncion",
    "semisextil": "semisextil", "sextil": "sextil",
    "cuadratura": "cuadratura", "cuadro": "cuadratura",
    "trigono": "trigono", "quincuncio": "quincuncio", "quincunce": "quincuncio",
    "oposicion": "oposicion", "opuesto": "oposicion", "opuesta": "oposicion",
}

_MESES_NUM = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _planetas_mapa(carta):
    """Mapa nombre normalizado -> datos, acepte planetas en dict o en lista."""
    planetas = (carta or {}).get("planetas") or {}
    mapa = {}
    if isinstance(planetas, dict):
        for nombre, datos in planetas.items():
            if isinstance(datos, dict):
                mapa[_norm(nombre)] = datos
        return mapa
    for datos in planetas:
        if isinstance(datos, dict):
            mapa[_norm(datos.get("nombre", ""))] = datos
    return mapa


def _lon_de(datos):
    """Longitud eclíptica de un planeta, o None si no está calculada."""
    if not isinstance(datos, dict):
        return None
    lon = datos.get("lon")
    if isinstance(lon, (int, float)):
        return float(lon) % 360
    signo = _norm(datos.get("signo", ""))
    if signo in ZODIACO:
        grados = datos.get("grados", datos.get("grado", 0)) or 0
        try:
            return (_signo_base(signo) + float(grados)) % 360
        except (TypeError, ValueError):
            return None
    return None


def _signo_base(signo):
    orden = ("aries", "tauro", "gemini", "cancer", "leo", "virgo", "libra",
             "escorpio", "sagitario", "capricornio", "acuario", "piscis")
    signo = "gemini" if signo == "geminis" else signo
    return orden.index(signo) * 30 if signo in orden else 0


def _aspecto_entre(lon_a, lon_b):
    """Aspecto que forma el par de longitudes (con orbe), o None."""
    if lon_a is None or lon_b is None:
        return None
    diferencia = abs((lon_a - lon_b) % 360)
    diferencia = min(diferencia, 360 - diferencia)
    for angulo, nombre, orbe in _ANGULOS_ASPECTO:
        if abs(diferencia - angulo) <= orbe:
            return nombre
    return None


def _fechas_texto(texto):
    """Fechas ISO y años de 4 cifras mencionados en el texto."""
    n = _norm(texto)
    fechas, anios = set(), set()
    for m in re.finditer(
            r"\b(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+|del\s+)?(\d{4})\b", n):
        mes = _MESES_NUM.get(m.group(2))
        if mes and 1 <= int(m.group(1)) <= 31:
            fechas.add(f"{int(m.group(3)):04d}-{mes:02d}-{int(m.group(1)):02d}")
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", n):
        fechas.add(m.group(0))
    for m in re.finditer(r"\b(?:19|20)\d{2}\b", n):
        anios.add(int(m.group(0)))
    return fechas, anios


def _fechas_calculo(calc):
    """Fechas ISO y años presentes en cualquier cadena del cálculo."""
    fechas, anios = set(), set()

    def recorrer(valor):
        if isinstance(valor, dict):
            for hijo in valor.values():
                recorrer(hijo)
        elif isinstance(valor, (list, tuple)):
            for hijo in valor:
                recorrer(hijo)
        elif isinstance(valor, str):
            for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", valor):
                fechas.add(m.group(0))
                anios.add(int(m.group(0)[:4]))
            for m in re.finditer(r"\b(?:19|20)\d{2}\b", valor):
                anios.add(int(m.group(0)))

    recorrer(calc)
    return fechas, anios


def _fechas_inventadas(calc, texto):
    """Fechas o años citados que no constan en el cálculo (no verificables)."""
    fechas, anios = _fechas_texto(texto)
    fechas_calc, anios_calc = _fechas_calculo(calc)
    malas = []
    for fecha in sorted(fechas):
        if fechas_calc:
            if fecha not in fechas_calc:
                malas.append(fecha)
        elif anios_calc:
            if int(fecha[:4]) not in anios_calc:
                malas.append(fecha)
        else:
            malas.append(fecha)
    for anio in sorted(anios):
        if anios_calc and anio not in anios_calc:
            malas.append(str(anio))
        elif not anios_calc:
            malas.append(str(anio))
    return malas


_RE_SIN_ASTRO_DE = re.compile(
    r"\b(" + _RE_PLANETA + r")\s+de\s+([ab])\s+"
    r"(?:hace|forma)\s+([a-z]+)\s+(?:con|a|de)\s+"
    r"(" + _RE_PLANETA + r")\s+de\s+([ab])\b")
_RE_SIN_POSICION = re.compile(
    r"\b(" + _RE_PLANETA + r")\s+de\s+([ab])\s+"
    r"(?:esta\s+en|transita\s+por|en|por)\s+([a-z]+)\b")


def _verif_sinastria(calc, texto, motivos):
    """Sinastría: aspectos cruzados y posiciones deben salir del cálculo."""
    calc = calc or {}
    carta_a, carta_b = calc.get("carta_a"), calc.get("carta_b")
    if not carta_a or not carta_b:
        return
    mapas = {"a": _planetas_mapa(carta_a), "b": _planetas_mapa(carta_b)}
    n = _norm(texto)
    for pl_a, lado_a, aspecto, pl_b, lado_b in _RE_SIN_ASTRO_DE.findall(n):
        if lado_a == lado_b:
            continue
        datos_a = mapas[lado_a].get(pl_a)
        datos_b = mapas[lado_b].get(pl_b)
        if datos_a is None or datos_b is None:
            motivos.append(
                f"Menciona un aspecto cruzado con un planeta no calculado: "
                f"{pl_a} de {lado_a.upper()} con {pl_b} de {lado_b.upper()}")
            continue
        esperado = _aspecto_entre(_lon_de(datos_a), _lon_de(datos_b))
        pedido = _NOMBRES_ASPECTO.get(aspecto, aspecto)
        if esperado is None:
            motivos.append(
                f"No se puede verificar el aspecto cruzado "
                f"{pl_a} de {lado_a.upper()} con {pl_b} de {lado_b.upper()}: "
                f"faltan longitudes calculadas")
        elif pedido != esperado:
            motivos.append(
                f"Atribuye un aspecto cruzado que no se calcula: "
                f"{pl_a} de {lado_a.upper()} {aspecto} {pl_b} de "
                f"{lado_b.upper()} (el cálculo da {esperado})")
    for pl, lado, signo in _RE_SIN_POSICION.findall(n):
        if signo not in ZODIACO:
            continue
        datos = mapas[lado].get(pl)
        if datos is None or not datos.get("signo"):
            motivos.append(
                f"Atribuye una posición no calculada: {pl} de {lado.upper()} "
                f"en {signo}")
            continue
        if _norm(datos.get("signo")) != signo:
            motivos.append(
                f"Contradice la posición calculada de {pl} de "
                f"{lado.upper()} ({datos.get('signo')}): el texto dice {signo}")
    for fecha in _fechas_inventadas(calc, texto):
        motivos.append(f"Menciona una fecha o año no calculado: {fecha}")


def _verif_transitos(calc, texto, motivos):
    """Solo contradicciones: triples 'X hace Y a su Z natal' no calculados."""
    trans = (calc or {}).get("transitos") or {}
    aspectos = trans.get("aspectos") or []
    if not aspectos:
        return
    esperados = {
        (_norm(a.get("planeta_transito", "")), _norm(a.get("aspecto", "")),
         _norm(a.get("planeta_natal", "")))
        for a in aspectos
    }
    n = _norm(texto)
    for t, a, npl in _RE_TRIPLE_TRANSITO.findall(n):
        if (t, a, npl) not in esperados:
            motivos.append(
                f"Menciona un tránsito que no está entre los calculados: "
                f"{t} hace {a} a su {npl} natal")


_RE_PLANETA_RS = re.compile(
    r"\b(" + _RE_PLANETA + r")\s+"
    r"(?:rs|de\s+la\s+revolucion(?:\s+solar)?)\s+"
    r"(?:esta\s+en|transita\s+por|en|por)\s+([a-z]+)\b")
_RE_MC_RS = re.compile(
    r"\b(?:medio\s+cielo|mc)\s+"
    r"(?:rs|de\s+la\s+revolucion(?:\s+solar)?)\s+"
    r"(?:esta\s+en|en)\s+([a-z]+)\b")


def _verif_revolucion(calc, texto, motivos):
    """Contradicciones de todos los planetas, Ascendente y Medio Cielo RS."""
    rs = (calc or {}).get("revolucion_solar") or {}
    if not rs:
        return
    carta = rs.get("carta") or {}
    planetas = _planetas_mapa(carta)
    asc_rs = (rs.get("ascendente") or carta.get("ascendente") or {}).get("signo")
    mc_rs = (rs.get("medio_cielo") or carta.get("medio_cielo") or {}).get("signo")
    n = _norm(texto)
    for planeta, tok in _RE_PLANETA_RS.findall(n):
        if tok not in ZODIACO:
            continue
        datos = planetas.get(planeta)
        if not datos or not datos.get("signo"):
            motivos.append(
                f"Menciona un planeta de la revolución solar no calculado: "
                f"{planeta} en {tok}")
        elif _norm(datos.get("signo")) != tok:
            motivos.append(
                f"Contradice {planeta} de la revolución solar calculado "
                f"({datos.get('signo')}): el texto dice {tok}")
    if asc_rs:
        for tok in _RE_ASC_RS.findall(n):
            if tok in ZODIACO and tok != _norm(asc_rs):
                motivos.append(
                    f"Contradice el Ascendente de la revolución solar calculado "
                    f"({asc_rs}): el texto dice {tok}")
    for tok in _RE_MC_RS.findall(n):
        if tok not in ZODIACO:
            continue
        if not mc_rs:
            motivos.append(
                f"Menciona el Medio Cielo de la revolución solar no calculado: "
                f"en {tok}")
        elif _norm(mc_rs) != tok:
            motivos.append(
                f"Contradice el Medio Cielo de la revolución solar calculado "
                f"({mc_rs}): el texto dice {tok}")
    for fecha in _fechas_inventadas(calc, texto):
        motivos.append(f"Menciona una fecha o año no calculado: {fecha}")


def _verif_biorritmos(calc, texto, motivos):
    """Solo contradicciones: porcentajes citados fuera de ±5 de los calculados."""
    datos = (calc or {}).get("biorritmos") or {}
    ciclos = datos.get("ciclos") or {}
    if not ciclos:
        return
    n = _norm(texto)
    alias = {
        "fisico": ("fisico", "fisica"),
        "emocional": ("emocional",),
        "intelectual": ("intelectual",),
    }
    for clave, nombres in alias.items():
        ciclo = ciclos.get(clave)
        if not ciclo:
            continue
        esperado = ciclo.get("porcentaje")
        if esperado is None:
            continue
        for nombre in nombres:
            for m in re.finditer(r"\b" + nombre + r"\b", n):
                inicio = max(0, m.start() - 60)
                ventana = n[inicio: m.end() + 120]
                candidatos = list(_RE_PCT.finditer(ventana))
                if not candidatos:
                    continue
                # El porcentaje propio del ciclo va justo después del nombre
                # ("intelectual al 87%"); se prefiere ese y solo se falla si
                # todas las lecturas razonables contradicen lo calculado.
                cercano = min(candidatos,
                             key=lambda c: abs((inicio + c.start()) - m.start()))
                despues = [c for c in candidatos
                          if inicio + c.start() >= m.end()]
                elegidos = [despues[0], cercano] if despues else [cercano]
                if all(_pct_contradice(c, esperado) for c in elegidos):
                    motivos.append(
                        f"Contradice el ciclo {clave} calculado "
                        f"({esperado}%): el texto dice {cercano.group(1)}%")


def _es_negativa_alcance(tarea):
    """Casos que deben rechazar una técnica: familia propia o ética del alcance."""
    familia = tarea.get("familia")
    if familia == "fuera_alcance":
        return True
    return (familia == "etica"
            and _norm(tarea.get("tema", "")) == "fuera_alcance")


_CONTENIDO_FUERA_ALCANCE = (
    (r"\b(?:linea\s+de\s+la\s+vida|monte\s+de\s+venus|montana\s+de\s+venus|"
     r"palma|palmas|mano|manos|quiromancia|quiromantica)\b", "quiromancia"),
    (r"\b(?:runas?|futhark|fehu|ansuz|thurisaz|raidho)\b", "runas"),
    (r"\b(?:i\s+ching|hexagrama|trigrama|libro\s+de\s+las\s+mutaciones)\b",
     "i ching"),
    (r"\b(?:vida\s+pasada|vida\s+anterior|vidas\s+pasadas|regresion)\b",
     "vidas pasadas"),
    (r"\b(?:bazi|nakshatra|dasha|jyotish|astrologia\s+vedica|vedico)\b",
     "jyotish o bazi"),
    (r"\b(?:pendulo|bola\s+de\s+cristal|posos|borra\s+de\s+cafe|aura|"
     r"mediumnidad|tarot\s+egipcio|lenormand)\b", "otras técnicas"),
)


def _verif_negativa_alcance(tarea, texto, motivos):
    """Rechaza la técnica fuera de alcance y no la responde de tapadillo.

    Además de exigir rechazo explícito y alternativa dentro del producto, se
    ignoran las oraciones que contienen el rechazo (nombrar la técnica al
    rechazarla es legítimo) y se busca contenido propio de la técnica vedada
    en el resto del texto.
    """
    if not _es_negativa_alcance(tarea):
        return
    if not _RECHAZO_ALCANCE.search(texto):
        motivos.append("No rechaza la técnica fuera de alcance")
    if not _ALTERNATIVA_TECNICAS.search(texto):
        motivos.append("No ofrece alternativa dentro de las técnicas del producto")
    for oracion in re.split(r"(?<=[.!?;])\s+|\n+", texto):
        if not oracion.strip() or _RECHAZO_ALCANCE.search(oracion):
            continue
        normalizada = _norm(oracion)
        for patron, etiqueta in _CONTENIDO_FUERA_ALCANCE:
            m = re.search(patron, normalizada)
            if m:
                motivos.append(
                    f"Responde contenido de una técnica fuera de alcance "
                    f"({etiqueta}): «{m.group(0)}»")
                break


def verificar_lectura(tarea, texto):
    """Comprueba presencia, no invención, coherencia con lo calculado y vedados."""
    motivos = []
    if not isinstance(tarea, dict):
        return False, [f"Tarea no válida: {tarea!r}"]
    texto = "" if texto is None else texto if isinstance(texto, str) else str(texto)
    calc = tarea.get("calculos") or {}
    cartas = tarea.get("cartas") or []
    f = tarea.get("familia", "")
    if cartas:
        texto_ajenas = _mascara_astros(texto) if "carta_natal" in calc else None
        _verif_cartas(cartas, tarea.get("universo_cartas") or [], texto, motivos,
                      texto_ajenas=texto_ajenas)
    elif f in FAMILIAS_SIN_CARTAS and tarea.get("universo_cartas"):
        _verif_cartas_sin_tirada(tarea["universo_cartas"], texto, motivos,
                                 astro=f in FAMILIAS_ASTRO)
    elif f in FAMILIAS_TIRADA and tarea.get("universo_cartas"):
        # Sin cartas reconstruidas no se puede exigir presencia ni orientación,
        # pero sí rechazar rangos y palos que no existen en el mazo.
        _verif_cartas_inventadas(tarea["universo_cartas"], texto, motivos,
                                 incluir_nombres=False)
    if f in FAMILIAS_ESQUEMA or f == "lectura_completa":
        _verif_esquema(tarea, texto, motivos)
    _verif_numeros(calc, texto, motivos)
    _verif_sol(calc, texto, motivos)
    _verif_transitos(calc, texto, motivos)
    _verif_sinastria(calc, texto, motivos)
    _verif_revolucion(calc, texto, motivos)
    _verif_biorritmos(calc, texto, motivos)
    _verif_negativa_alcance(tarea, texto, motivos)
    _verif_promesas(texto, motivos)
    _verif_juego(texto, motivos)
    return (len(motivos) == 0, motivos)


# --------------------------------------------------------------------------- #
# Ejemplos (solo prompts; no llama a los nodos)
# --------------------------------------------------------------------------- #
def _cargar_kb_real():
    import generate_tasks as gt
    return {
        "tarot": gt.load_kb("tarot.json"),
        "astrologia": gt.load_kb("astrologia.json"),
        "numerologia": gt.load_kb("numerologia.json"),
        "baraja": gt.load_kb("baraja_espanola.json"),
    }


def universo_baraja(kb_baraja, kb_tarot):
    """Universo de la baraja: los 40 naipes (con sinónimos) más los nombres del
    tarot que NO son naipe (mayores, reinas, ochos/nueves/dieces), para que el
    verificador detecte como ajenas las cartas de la 41 en adelante y las
    mezclas con tarot. Caballero/Sota/Caballo y As-Siete compartidos no se listan
    como ajenos porque son variantes o naipes legítimos."""
    from cartas import NAIPES_ESPANOLES
    aceptadas = set()
    for c in NAIPES_ESPANOLES:
        aceptadas.add(_norm(c["nombre"]))
        for s in c.get("sinonimos") or []:
            aceptadas.add(_norm(s))
    extras = []
    for c in (kb_tarot.get("mayores", []) + kb_tarot.get("menores", [])):
        nn = _norm(c.get("nombre", ""))
        if nn and nn not in aceptadas:
            extras.append(c["nombre"])
    return list(NAIPES_ESPANOLES) + extras


def _fabricar_tarea(familia, rng, kb):
    """Construye (tarea, calculos) realistas para una familia."""
    import generate_tasks as gt
    from calculos import numerologia as calc_num

    universo = [c["nombre"] for c in kb["tarot"]["mayores"] + kb["tarot"]["menores"]]
    contexto = rng.choice(gt.CONTEXTOS)
    pregunta = rng.choice(gt.PREGUNTAS[contexto])

    def dibujar(n):
        elegidas = rng.sample(kb["tarot"]["mayores"] + kb["tarot"]["menores"], n)
        return [{"nombre": c["nombre"], "invertida": rng.random() < 0.35} for c in elegidas]

    def nacimiento():
        ciudad, pais, lat, lon, tz = rng.choice(gt.CIUDADES)
        anio = rng.randint(1950, 2005)
        mes = rng.randint(1, 12)
        dia = rng.randint(1, 28)
        hora = f"{rng.randint(0, 23):02d}:{rng.choice([0, 15, 30, 45]):02d}"
        return f"{anio:04d}-{mes:02d}-{dia:02d}", hora, ciudad, pais, lat, lon, tz

    def num_calc(fecha, nombre):
        return {
            "camino_de_vida": calc_num.camino_de_vida(fecha),
            "expresion": calc_num.expresion(nombre),
            "alma": calc_num.reducir(calc_num.alma(nombre)),
            "personalidad": calc_num.reducir(calc_num.personalidad(nombre)),
            "anio_personal": calc_num.anio_personal(fecha, 2026),
        }

    if familia in ("tarot_1", "tarot_pregunta", "multiturno"):
        t = {"familia": familia, "contexto": contexto, "pregunta": pregunta,
             "cartas": dibujar(1), "universo_cartas": universo}
        return t, {}

    if familia == "tarot_2":
        t = {"familia": familia, "contexto": contexto, "pregunta": pregunta,
             "cartas": dibujar(2), "universo_cartas": universo}
        return t, {}

    if familia == "tarot_3":
        t = {"familia": familia, "contexto": contexto, "pregunta": pregunta,
             "cartas": dibujar(3), "posiciones": ["pasado", "presente", "futuro"],
             "universo_cartas": universo}
        return t, {}

    if familia == "cruz_celta":
        pos = ["situacion", "obstaculo", "raiz", "pasado", "meta", "futuro cercano",
               "actitud", "entorno", "esperanzas y miedos", "resultado"]
        t = {"familia": familia, "contexto": contexto, "pregunta": pregunta,
             "cartas": dibujar(10), "posiciones": pos, "universo_cartas": universo}
        return t, {}

    if familia in FAMILIAS_ESPAÑOLA:
        from cartas import NAIPES_ESPANOLES
        n = {"espanola_1": 1, "espanola_3": 3, "espanola_5": 5, "espanola_7": 7}[familia]
        elegidas = rng.sample(NAIPES_ESPANOLES, n)
        cartas_e = [{"nombre": c["nombre"], "invertida": rng.random() < 0.35,
                     "sinonimos": list(c.get("sinonimos") or [])} for c in elegidas]
        t = {"familia": familia, "mazo": "espanol", "contexto": contexto,
             "pregunta": pregunta, "cartas": cartas_e,
             "universo_cartas": universo_baraja(kb.get("baraja", {}), kb["tarot"])}
        if familia in POSICIONES_ESPAÑOLA:
            t["posiciones"] = list(POSICIONES_ESPAÑOLA[familia])
        return t, {}

    if familia == "astro_natal":
        fecha, hora, ciudad, pais, lat, lon, tz = nacimiento()
        carta = gt.calcular_carta(fecha, hora, lat, lon, tz)
        foco = rng.choice(gt.FOCOS_ASTRO)
        t = {"familia": familia, "foco": foco, "ciudad": ciudad, "pais": pais,
             "pregunta": f"¿Qué dice mi carta sobre mi {foco}?"}
        return t, {"carta_natal": carta}

    if familia == "sinastria":
        f1, h1, c1, p1, la1, lo1, tz1 = nacimiento()
        f2, h2, c2, p2, la2, lo2, tz2 = nacimiento()
        foco = rng.choice(gt.FOCOS_SIN)
        t = {"familia": familia, "foco": foco, "ciudad_a": c1, "pais_a": p1,
             "ciudad_b": c2, "pais_b": p2,
             "pregunta": f"¿Qué nos dice la sinastria sobre nuestra {foco}?"}
        return t, {"carta_a": gt.calcular_carta(f1, h1, la1, lo1, tz1),
                   "carta_b": gt.calcular_carta(f2, h2, la2, lo2, tz2)}

    if familia == "numerologia":
        fecha, _, _, _, _, _, _ = nacimiento()
        nombre = rng.choice(gt.NOMBRES)
        foco = rng.choice(["camino de vida", "propósito", "año personal", "talentos", "relaciones"])
        t = {"familia": familia, "nombre": nombre,
             "pregunta": f"¿Qué me dice la numerología sobre mi {foco}?"}
        return t, {"numerologia": num_calc(fecha, nombre)}

    if familia == "lectura_completa":
        fecha, hora, ciudad, pais, lat, lon, tz = nacimiento()
        nombre = rng.choice(gt.NOMBRES)
        t = {"familia": familia, "nombre": nombre, "contexto": contexto,
             "ciudad": ciudad, "pais": pais, "pregunta": pregunta,
             "cartas": dibujar(3), "universo_cartas": universo}
        return t, {"carta_natal": gt.calcular_carta(fecha, hora, lat, lon, tz),
                   "numerologia": num_calc(fecha, nombre)}

    if familia == "etica":
        tema, pregunta_e = rng.choice(gt.CASOS_ETICA)
        arranque = rng.choice(gt.ARRANQUES_ETICA)
        t = {"familia": familia, "tema": tema,
             "pregunta": f"{arranque} {pregunta_e}"}
        return t, {}

    if familia == "transitos":
        fecha, hora, ciudad, pais, lat, lon, tz = nacimiento()
        carta = gt.calcular_carta(fecha, hora, lat, lon, tz)
        trans, _rs = gt.datos_proyeccion(fecha, hora, lat, lon, tz)
        foco = rng.choice(gt.FOCOS_ASTRO)
        t = {"familia": familia, "foco": foco, "ciudad": ciudad, "pais": pais,
             "pregunta": rng.choice(gt.PREGUNTAS_TRANSITOS).format(foco=foco)}
        return t, {"carta_natal": carta, "transitos": trans}

    if familia == "revolucion_solar":
        fecha, hora, ciudad, pais, lat, lon, tz = nacimiento()
        carta = gt.calcular_carta(fecha, hora, lat, lon, tz)
        _trans, rs = gt.datos_proyeccion(fecha, hora, lat, lon, tz)
        t = {"familia": familia, "ciudad": ciudad, "pais": pais,
             "pregunta": rng.choice(gt.PREGUNTAS_RS)}
        return t, {"carta_natal": carta, "revolucion_solar": rs}

    if familia == "biorritmos":
        from calculos import biorritmos as calc_bio
        fecha, hora, _ciudad, _pais, _lat, _lon, _tz = nacimiento()
        datos = calc_bio.biorritmos(fecha, gt.FECHA_CONSULTA)
        t = {"familia": familia, "fecha_nacimiento": fecha, "hora": hora,
             "pregunta": rng.choice(gt.PREGUNTAS_BIORRITMOS)}
        return t, {"biorritmos": datos}

    if familia == "fuera_alcance":
        tecnica, pregunta_f = rng.choice(gt.FUERA_ALCANCE_ENTRENAMIENTO)
        arranque = rng.choice(gt.ARRANQUES_FUERA)
        t = {"familia": familia, "tecnica": tecnica,
             "pregunta": f"{arranque} {pregunta_f}"}
        return t, {}

    raise ValueError(f"familia desconocida: {familia}")


def generar_ejemplos(ruta, n=10, seed=42):
    """Escribe n tareas por familia (solo prompts) en JSONL. No llama a los nodos."""
    rng = random.Random(seed)
    kb = _cargar_kb_real()
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with ruta.open("w", encoding="utf-8") as fh:
        for familia in FAMILIAS:
            for _ in range(n):
                tarea, calc = _fabricar_tarea(familia, rng, kb)
                prompt = construir_prompt(tarea, kb, calc)
                fila = {
                    "familia": familia,
                    "system": prompt["system"],
                    "user": prompt["user"],
                    "tarea": tarea,
                    "calculos": calc,
                }
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
                total += 1
    return total


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Genera ejemplos de prompts de fase 1.")
    ap.add_argument("--out", default="/tmp/t44/ejemplos.jsonl")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    total = generar_ejemplos(args.out, n=args.n, seed=args.seed)
    print(f"Ejemplos escritos en {args.out}: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
