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
)

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
}

# Promesas y afirmaciones vedadas (diagnóstico/promesa médica, muerte, garantías,
# lotería). Se descartan cuando van negadas inmediatamente antes.
_PROMESAS_VEDADAS = [
    r"vas a curar",
    r"\bcurar[aá]s\b",
    r"\bsanar[aá]s\b",
    r"quedar[aá]s?\s+curad",
    r"(puedes|puede)\s+dejar\s+(la|tu)\s+medicaci[oó]n",
    r"\bdeja\s+(la|tu)\s+medicaci[oó]n",
    r"no\s+necesitas\s+(el\s+)?(m[eé]dico|ir\s+al\s+m[eé]dico)",
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

_VERIF_NUM = [
    ("año personal", r"año\s*personal\s*(\d+)", "anio_personal"),
    ("camino de vida", r"camino\s*de\s*vida\s*(\d+)", "camino_de_vida"),
    ("expresión", r"expresi[oó]n\s*(\d+)", "expresion"),
    ("alma", r"alma\s*(\d+)", "alma"),
    ("personalidad", r"personalidad\s*(\d+)", "personalidad"),
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

    return f'Consulta.\n\nPregunta del consultante: "{q}"'


def _referencia(tarea, kb, calc):
    f = tarea.get("familia", "")
    kb_tarot = kb.get("tarot", {})
    kb_astro = kb.get("astrologia", {})
    kb_num = kb.get("numerologia", [])
    ctx = tarea.get("contexto")

    if f in ("tarot_1", "tarot_2", "tarot_3", "cruz_celta", "tarot_pregunta", "multiturno"):
        return _ref_tarot(tarea.get("cartas"), kb_tarot, ctx)
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
    return ""


def construir_prompt(tarea, kb, calculos=None):
    """Devuelve {"system", "user"} con estilo, Referencia de la KB y datos calculados."""
    calc = calculos if calculos is not None else (tarea.get("calculos") or {})
    f = tarea.get("familia", "")
    cuerpo = _cuerpo(tarea, calc)
    referencia = _referencia(tarea, kb, calc)
    instruccion = INSTRUCCIONES.get(f, "Interpreta la consulta con las técnicas indicadas.")
    user = "\n\n".join(p for p in (cuerpo, referencia, instruccion) if p)
    return {"system": SYSTEM, "user": user}


# --------------------------------------------------------------------------- #
# Verificador determinista de la lectura
# --------------------------------------------------------------------------- #
def _tiene_inversion(texto):
    n = _norm(texto)
    return ("invertid" in n) or ("al reves" in n)


def _negado(texto, inicio):
    pre = texto[max(0, inicio - 6):inicio]
    return bool(re.search(r"\bno\s+$", pre, re.IGNORECASE))


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
    forma = (
        r"(?:cartas?|arcanos?)\s+(?:mayor\s+|menor\s+)?de\s+" + re.escape(nombre)
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


def _verif_cartas(cartas, universo, texto, motivos):
    norm = _norm(texto)
    drawn = {_norm(c.get("nombre")) for c in cartas}
    for c in cartas:
        if _norm(c.get("nombre")) not in norm:
            motivos.append(f"Falta la carta de la tirada: {c.get('nombre')}")
    for nombre in universo:
        nn = _norm(nombre)
        if nn in drawn:
            continue
        if nn and _mencion_carta(nombre, texto):
            motivos.append(f"Menciona carta ajena a la tirada: {nombre}")
    hay_inv = any(c.get("invertida") for c in cartas)
    inv = _tiene_inversion(texto)
    if hay_inv and not inv:
        nombres = ", ".join(c.get("nombre") for c in cartas if c.get("invertida"))
        motivos.append(f"No indica la orientación invertida de: {nombres}")
    if (not hay_inv) and inv:
        motivos.append(
            "Menciona una orientación invertida sin que haya cartas invertidas en la tirada"
        )


def _verif_numeros(calc, texto, motivos):
    num = (calc or {}).get("numerologia") or {}
    for etiqueta, pat, key in _VERIF_NUM:
        esperado = num.get(key)
        if esperado is None:
            continue
        for m in re.finditer(pat, texto, re.IGNORECASE):
            val = int(m.group(1))
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


def verificar_lectura(tarea, texto):
    """Comprueba presencia, no invención, coherencia con lo calculado y vedados."""
    motivos = []
    texto = texto or ""
    calc = tarea.get("calculos") or {}
    cartas = tarea.get("cartas") or []
    if cartas:
        _verif_cartas(cartas, tarea.get("universo_cartas") or [], texto, motivos)
    _verif_numeros(calc, texto, motivos)
    _verif_sol(calc, texto, motivos)
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
    }


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
