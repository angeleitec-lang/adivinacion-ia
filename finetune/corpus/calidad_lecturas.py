#!/usr/bin/env python3
"""Auditoría de calidad de las lecturas ya aceptadas de la fase 1.

No modifica el fichero de entrada ni llama a la red. Detecta defectos de
contenido y de forma que el verificador de fase 1 no mide: fórmulas
repetidas entre lecturas, muletillas, incumplimiento del esquema, listas
donde se pide prosa, género asumido, contradicciones astrológicas, fugas de
la ficha técnica del prompt y respuestas a preguntas que el prompt no puede
responder con los datos que trae.

Uso:
  .venv/bin/python corpus/calidad_lecturas.py \
      --in /ruta/aceptadas.jsonl --out-dir /tmp/calidad \
      [--muestra 12] [--semilla 20261021] [--top 10]

Salidas:
  informe.json   contadores, ejemplos y umbrales propuestos
  informe.md     resumen legible para revisión
  muestra_N.jsonl muestra estratificada reproducible (si --muestra > 0)
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

CODIGOS = (
    "apertura_formula",
    "cierre_formula",
    "apertura_repetida",
    "cierre_repetido",
    "frase_plantilla",
    "muletilla",
    "lista_en_prosa",
    "esquema_incumplido",
    "longitud_atipica",
    "genero_inconsistente",
    "genero_asumido",
    "ficha_tecnica",
    "placeholder_prompt",
    "astro_signo_contradicho",
    "astro_casa_contradicha",
    "astro_ascendente_contradicho",
    "elemento_contradicho",
    "regente_contradicho",
    "pregunta_sin_datos",
    "truncamiento",
    "referencia_ausente",
    "repeticion_interna",
)

FAMILIAS_TAROT = (
    "tarot_1", "tarot_2", "tarot_3", "tarot_pregunta", "cruz_celta",
    "lectura_completa", "espanola_1", "espanola_3", "espanola_5",
    "espanola_7", "multiturno",
)
FAMILIAS_ASTRO = ("astro_natal", "sinastria", "transitos", "revolucion_solar")

PLANETAS = (
    "Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno",
    "Urano", "Neptuno", "Plutón",
)
SIGNOS = (
    "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra",
    "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis",
)

_PATRONES_APERTURA = (
    r"^(?:claro|por supuesto|desde luego)[,;:]",
    r"^(?:qué|que)\s+(?:hermosa|bonita|bella|preciosa|interesante|profunda|"
    r"valiosa|poderosa|bonito|hermoso)\s+(?:pregunta|carta|consulta|tirada|lectura)",
    r"^(?:hola|buenas|buenos días)[,;:]",
    r"^(?:querid[oa]s?\s+)?consultante[,;:]",
    r"^gracias por (?:compartir|confiar|tu confianza)",
    r"^entiendo (?:tu|su) (?:pregunta|consulta|situación|preocupación)",
    r"^vamos a (?:mirar|leer|explorar|analizar)",
    r"^(?:como|en calidad de) (?:tarotista|astróloga|astrólogo|numeróloga|numerólogo)",
    r"^aprecio (?:tu|su) (?:confianza|honestidad|pregunta)",
)

_PATRONES_CIERRE = (
    r"estoy aquí para (?:acompañarte|lo que necesites|ayudarte|apoyarte)",
    r"si (?:tienes|necesitas) (?:más|alguna|otra) (?:pregunta|duda|consulta)",
    r"¿hay algo más que (?:quieras|te gustaría|desees) (?:explorar|saber|preguntar)",
    r"un abrazo (?:cálido|grande|fuerte|enorme)",
    r"con cariño(?: y (?:luz|respeto))?[,;:]?\s*(?:tu|siempre tu)",
    r"que (?:la luz|el universo|las estrellas) te (?:acompañe|guíe|ilumine)",
    r"recuerda que (?:esto|esta lectura) es (?:una tendencia|solo una tendencia)",
)

_MULETILLAS = (
    "estoy aquí para acompañarte",
    "es importante que",
    "recuerda que esto es una tendencia",
    "no es una sentencia",
    "en el fondo",
    "desde el corazón",
    "vamos a mirar con calma",
    "por otro lado",
    "luz al final",
    "como quien hojea",
    "hilo dorado",
    "respira hondo",
    "el universo no te abandona",
    "confía en el proceso",
    "todo sucede por una razón",
)

_PALABRAS_FINALES = {
    "a", "al", "algo", "así", "con", "como", "de", "del", "donde", "el",
    "en", "es", "esta", "este", "está", "están", "fue", "ha", "hacia", "hasta",
    "la", "las", "le", "les", "lo", "los", "más", "mi", "muy", "no", "o",
    "para", "pero", "por", "que", "qué", "se", "ser", "si", "sin", "sobre",
    "son", "su", "sus", "te", "tu", "tus", "un", "una", "uno", "y", "ya",
}

_MASCULINO_GENERICO = (
    r"\b(?:constructor|compañero|buscador|juguetón|luchador|pionero|"
    r"trabajador|soñador|creador|protector|cuidador|solitario)\s+"
    r"(?:nato|de nacimiento|empedernido)\b",
    r"\bseguro de ti mismo\b",
    r"\b(?:estás|te sientes|te encuentras)\s+(?:muy\s+)?(?:cansado|agotado|"
    r"preparado|listo|invitado|llamado|conectado|enfocado)\b",
)
_FEMENINO_DIRIGIDO = (
    r"\b(?:estás|te sientes|te encuentras|quedas|sigues)\s+(?:muy\s+)?"
    r"(?:atrapada|esclava|agarrada|bendecida|preparada|invitada|llamada|"
    r"conectada|enfocada|cansada|agotada|lista)\b",
    r"\b(?:eres|estás|te sientes|te encuentras|quedas|sigues|siendo)\s+"
    r"(?:una\s+)?(?:dueña|buscadora|creadora|protectora|cuidadora|solitari[ao])\b",
)
_MARCADOR_GENERO = re.compile(r"\b\w+[oa]/a\b", re.I)

_FICHA_TECNICA = (
    re.compile(r"\bDatos de nacimiento\s*:", re.I),
    re.compile(r"\bDatos numerológicos calculados\s*:", re.I),
    re.compile(r"Referencia \(significados de la tradición", re.I),
    re.compile(r"^\s*(?:Posiciones|Aspectos)\s*:\s*$", re.M),
)

_STOP_TRANSITOS = re.compile(
    r"tr[aá]nsit|revoluci[oó]n solar|progresi[oó]n|carta de tr[aá]nsito", re.I
)
_PREGUNTA_FUTURO = re.compile(
    r"pr[oó]xim[oa] (?:año|mes|meses|semana)|año que viene|"
    r"(?:este|el) año|pr[oó]ximos? (?:d[ií]as|meses)|20(?:2[5-9]|3[0-9])",
    re.I,
)

_LINEA_CARTA = re.compile(
    r"^(?:Carta(?:\s+\d+)?|[^:\n]{2,40}):\s*(.+?)\s*\((al derecho|invertida)\)\s*$",
    re.I | re.M,
)
_CABECERA_CARTA = re.compile(
    r"^##\s*\d+\.\s*[^—\n]+—\s*(.+?)\s*\((al derecho|invertida)\)\s*$",
    re.I | re.M,
)
_POSICION_ASTRO = re.compile(
    r"^-\s*(" + "|".join(PLANETAS) + r"|Ascendente|Medio Cielo)\s*:\s*(" +
    "|".join(SIGNOS) + r")\s+\d+°\d+'[^()\n]*(?:\(casa\s+(\d+)\))?",
    re.M,
)
_NUMERO_PROMPT = re.compile(r"^-\s*[^:\n]+:\s*(\d{1,2})\s*$", re.M)


_ACENTOS = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
    "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u", "â": "a", "ê": "e",
    "î": "i", "ô": "o", "û": "u", "ä": "a", "ë": "e", "ï": "i", "ö": "o",
    "Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ü": "U", "Ñ": "N",
    "À": "A", "È": "E", "Ì": "I", "Ò": "O", "Ù": "U", "Â": "A", "Ê": "E",
    "Î": "I", "Ô": "O", "Û": "U", "Ä": "A", "Ë": "E", "Ï": "I", "Ö": "O",
})


def _sin_acentos(texto):
    return texto.translate(_ACENTOS)


@lru_cache(maxsize=8192)
def normalizar(texto):
    texto = _sin_acentos(texto or "").casefold()
    texto = re.sub(r"[*_`#>]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip(" \t\n.,;:!?¿¡\"'«»—-")


def _limpiar(texto):
    texto = re.sub(r"^\s*#{1,6}\s*", "", texto, flags=re.M)
    texto = re.sub(r"[*_`]+", "", texto)
    texto = re.sub(r"^\s*[-+]\s+", "", texto, flags=re.M)
    return re.sub(r"[ \t]+", " ", texto).strip()


def _oraciones(texto):
    limpio = _limpiar(texto)
    partes = re.split(r"(?<=[.!?…])\s+|\n{2,}", limpio)
    return [p.strip() for p in partes if len(normalizar(p)) >= 3]


def _primera_frase(texto):
    oraciones = _oraciones(texto)
    return oraciones[0] if oraciones else ""


def _ultima_frase(texto):
    oraciones = _oraciones(texto)
    return oraciones[-1] if oraciones else ""


def _hallazgo(codigo, detalle, evidencia="", gravedad="media"):
    return {
        "codigo": codigo,
        "detalle": detalle,
        "evidencia": re.sub(r"\s+", " ", evidencia)[:280],
        "gravedad": gravedad,
    }


def cargar_lecturas(ruta):
    lecturas = []
    with open(ruta, encoding="utf-8") as fh:
        for numero, linea in enumerate(fh, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido en la línea {numero}: {exc}") from exc
            mensajes = fila.get("conversations") or []
            system = human = gpt = ""
            for mensaje in mensajes:
                rol = mensaje.get("from") or mensaje.get("role") or ""
                valor = mensaje.get("value") or mensaje.get("content") or ""
                if rol == "system":
                    system = valor
                elif rol in ("human", "user"):
                    human = valor
                elif rol in ("gpt", "assistant"):
                    gpt = valor
            if not human or not gpt:
                continue
            lecturas.append({
                "id": str(fila.get("id", numero)),
                "bloque": fila.get("bloque") or fila.get("familia") or "desconocido",
                "system": system,
                "human": human,
                "gpt": gpt,
                "calculos": fila.get("calculos"),
            })
    return lecturas


def cargar_kb(ruta_kb=None):
    base = Path(ruta_kb) if ruta_kb else Path(__file__).resolve().parent / "kb"
    astro = json.loads((base / "astrologia.json").read_text(encoding="utf-8"))
    signos = {}
    for signo in astro.get("signos", []):
        signos[normalizar(signo["nombre"])] = signo
    return {"signos": signos}


def _cartas_prompt(human):
    nombres = []
    for patron in (_LINEA_CARTA, _CABECERA_CARTA):
        for m in patron.finditer(human):
            nombre = m.group(1).strip()
            if normalizar(nombre) not in {normalizar(n) for n in nombres}:
                nombres.append(nombre)
    return nombres


def _posiciones_astro(human):
    return {
        m.group(1): {"signo": m.group(2), "casa": m.group(3)}
        for m in _POSICION_ASTRO.finditer(human)
    }


def _numeros_prompt(human):
    return {int(n) for n in _NUMERO_PROMPT.findall(human)}


def _es_cabecera_esquema(frase):
    return normalizar(frase) in {
        "carta natal", "tirada de tres cartas", "numerologia", "sintesis",
    }


def _pregunta(human):
    m = re.search(r'Pregunta del consultante:\s*["“](.+?)["”]\s*$', human, re.M | re.S)
    return m.group(1).strip() if m else ""


def _menciona_carta(gpt, nombre):
    if normalizar(nombre) in normalizar(gpt):
        return True
    partes = [p for p in re.split(r"\s+(?:de|del|la|el)\s+", nombre) if len(p) > 2]
    return bool(partes) and all(normalizar(p) in normalizar(gpt) for p in partes)


def _comprobar_esquema(lectura):
    bloque = lectura["bloque"]
    gpt = lectura["gpt"]
    hallazgos = []
    if bloque not in ("lectura_completa", "cruz_celta"):
        return hallazgos

    cabeceras = list(re.finditer(r"^##\s+(.+?)\s*$", gpt, re.M))
    secciones = {}
    for i, m in enumerate(cabeceras):
        fin = cabeceras[i + 1].start() if i + 1 < len(cabeceras) else len(gpt)
        secciones[normalizar(m.group(1))] = gpt[m.end():fin].strip()

    def cuerpo(clave):
        for titulo, texto in secciones.items():
            if titulo == clave or titulo.startswith(clave):
                return texto
        return None

    if bloque == "lectura_completa":
        faltan = [s for s in ("carta natal", "tirada de tres cartas", "numerologia", "sintesis")
                  if cuerpo(s) is None]
        if faltan:
            hallazgos.append(_hallazgo(
                "esquema_incumplido", "faltan secciones: " + ", ".join(faltan),
                gpt[:160], "alta"))
        for nombre, limite in (("carta natal", 600), ("numerologia", 400), ("sintesis", 400)):
            texto = cuerpo(nombre)
            if texto is not None and len(texto) > limite:
                hallazgos.append(_hallazgo(
                    "esquema_incumplido",
                    f"{nombre}: {len(texto)} caracteres (máximo {limite})",
                    texto[:180], "alta" if nombre == "sintesis" else "media"))
        tirada = cuerpo("tirada de tres cartas")
        if tirada is not None:
            if len(tirada) < 450 or len(tirada) > 900:
                hallazgos.append(_hallazgo(
                    "esquema_incumplido",
                    f"tirada de tres cartas: {len(tirada)} caracteres (esperado 450-900)",
                    tirada[:180], "media"))
            for nombre in _cartas_prompt(lectura["human"]):
                if not _menciona_carta(tirada, nombre):
                    hallazgos.append(_hallazgo(
                        "esquema_incumplido", f"la tirada no nombra {nombre}",
                        tirada[:180], "alta"))
        return hallazgos

    numeradas = [t for t in secciones if re.match(r"^\d+\.", t)]
    if len(numeradas) != 10:
        hallazgos.append(_hallazgo(
            "esquema_incumplido",
            f"cruz celta con {len(numeradas)} secciones numeradas (esperadas 10)",
            gpt[:160], "alta"))
    for titulo, texto in secciones.items():
        if not re.match(r"^\d+\.", titulo):
            continue
        if len(texto) > 300:
            hallazgos.append(_hallazgo(
                "esquema_incumplido",
                f"{titulo}: {len(texto)} caracteres (máximo 300)",
                texto[:180], "media"))
        elif len(texto) < 150:
            hallazgos.append(_hallazgo(
                "esquema_incumplido",
                f"{titulo}: {len(texto)} caracteres (mínimo 150)",
                texto[:180], "media"))
    sintesis = cuerpo("sintesis")
    if sintesis is not None and len(sintesis) > 400:
        hallazgos.append(_hallazgo(
            "esquema_incumplido",
            f"síntesis: {len(sintesis)} caracteres (máximo 400)",
            sintesis[:180], "alta"))
    return hallazgos


def _comprobar_astro(lectura, kb):
    bloque = lectura["bloque"]
    if bloque not in FAMILIAS_ASTRO + ("lectura_completa",):
        return []
    human, gpt = lectura["human"], lectura["gpt"]
    posiciones = _posiciones_astro(human)
    if not posiciones:
        return []
    hallazgos = []
    patron_signo = re.compile(
        r"\b(" + "|".join(PLANETAS) + r")\s+en\s+(" + "|".join(SIGNOS) + r")\b")
    for m in patron_signo.finditer(gpt):
        planeta, signo = m.group(1), m.group(2)
        antes = gpt[max(0, m.start() - 45):m.start()]
        if re.search(r"(?:\by\b|,)\s*$", antes, re.I):
            continue
        esperado = posiciones.get(planeta, {}).get("signo")
        if esperado and normalizar(signo) != normalizar(esperado):
            contexto = gpt[max(0, m.start() - 70):m.end() + 70]
            hallazgos.append(_hallazgo(
                "astro_signo_contradicho",
                f"{planeta} en {signo}; el prompt dice {esperado}",
                contexto, "alta"))
    ascendente = posiciones.get("Ascendente", {}).get("signo")
    if ascendente:
        for planeta, signo in re.findall(
                r"\b(" + "|".join(PLANETAS) + r")\s+en\s+(" + "|".join(SIGNOS) +
                r")\s+en\s+el\s+ascendente\b", gpt, re.I):
            if normalizar(signo) != normalizar(ascendente):
                hallazgos.append(_hallazgo(
                    "astro_ascendente_contradicho",
                    f"{planeta} en {signo} «en el ascendente»; el Ascendente es {ascendente}",
                    "", "alta"))
    for planeta, casa in re.findall(
            r"\b(" + "|".join(PLANETAS) + r")(?:\s+en\s+(?:" + "|".join(SIGNOS) +
            r"))?\s+(?:está|se encuentra)\s+en\s+(?:la\s+)?casa\s+(\d+)\b", gpt):
        esperada = posiciones.get(planeta, {}).get("casa")
        if esperada and casa != esperada:
            hallazgos.append(_hallazgo(
                "astro_casa_contradicha",
                f"{planeta} en casa {casa}; el prompt dice casa {esperada}",
                "", "alta"))
    for signo in SIGNOS:
        if normalizar(signo) not in normalizar(human):
            continue
        datos = kb.get("signos", {}).get(normalizar(signo))
        if not datos:
            continue
        patron = (
            rf"\b{re.escape(signo)}\b\s*(?:,|es|:)?\s*(?:un\s+)?"
            r"(?:signo|elemento)\s+de\s+(fuego|tierra|aire|agua)\b"
        )
        for m in re.finditer(patron, gpt, re.I):
            elemento = m.group(1).lower()
            if elemento != normalizar(datos.get("elemento", "")):
                hallazgos.append(_hallazgo(
                    "elemento_contradicho",
                    f"{signo} es de {datos.get('elemento')}; la lectura dice {elemento}",
                    m.group(0), "alta"))
    for signo in SIGNOS:
        datos = kb.get("signos", {}).get(normalizar(signo))
        if not datos or normalizar(signo) not in normalizar(human):
            continue
        for m in re.finditer(
                rf"\b{re.escape(signo)}\b[^.\n]{{0,80}}\bregid[oa]\s+por\s+"
                rf"(" + "|".join(PLANETAS) + r")\b", gpt, re.I):
            regente = m.group(1)
            validos = {normalizar(datos.get("regente", "")),
                       normalizar(datos.get("regente_tradicional", ""))}
            if normalizar(regente) not in validos:
                hallazgos.append(_hallazgo(
                    "regente_contradicho",
                    f"{signo} regido por {regente}; la KB dice "
                    f"{datos.get('regente')} / {datos.get('regente_tradicional')}",
                    m.group(0), "alta"))
    return hallazgos


def analizar_lectura(lectura, kb=None):
    kb = kb or {"signos": {}}
    human, gpt, bloque = lectura["human"], lectura["gpt"], lectura["bloque"]
    hallazgos = []
    primera = _primera_frase(gpt)
    ultima = _ultima_frase(gpt)
    norm_primera = normalizar(primera)
    norm_ultima = normalizar(ultima)

    for patron in _PATRONES_APERTURA:
        if re.search(normalizar(patron), norm_primera):
            hallazgos.append(_hallazgo(
                "apertura_formula", "apertura formulaica", primera, "media"))
            break
    for patron in _PATRONES_CIERRE:
        if re.search(normalizar(patron), norm_ultima):
            hallazgos.append(_hallazgo(
                "cierre_formula", "cierre formulaico", ultima or gpt[-160:], "media"))
            break

    presentes = [f for f in _MULETILLAS if f in normalizar(gpt)]
    if presentes:
        hallazgos.append(_hallazgo(
            "muletilla", "muletillas: " + ", ".join(presentes[:6]),
            presentes[0], "baja" if len(presentes) == 1 else "media"))

    lineas = re.findall(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+\S", gpt, re.M)
    if len(lineas) >= 3:
        gravedad = "alta" if bloque == "lectura_completa" else "media"
        hallazgos.append(_hallazgo(
            "lista_en_prosa",
            f"{len(lineas)} líneas de lista donde se pide prosa",
            next((l for l in gpt.splitlines() if re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", l)), ""),
            gravedad))

    hallazgos.extend(_comprobar_esquema(lectura))
    hallazgos.extend(_comprobar_astro(lectura, kb))

    if any(p.search(gpt) for p in _FICHA_TECNICA):
        hallazgos.append(_hallazgo(
            "ficha_tecnica", "la respuesta copia la ficha técnica del prompt",
            gpt[:180], "alta"))
    if "( )" in human or re.search(r"\(\s*\)", human):
        linea = next((l for l in human.splitlines() if re.search(r"\(\s*\)", l)), "")
        hallazgos.append(_hallazgo(
            "placeholder_prompt", "placeholder de país vacío en el prompt",
            linea, "media"))

    marcador = _MARCADOR_GENERO.search(gpt)
    if marcador and any(re.search(p, normalizar(gpt)) for p in _MASCULINO_GENERICO):
        hallazgos.append(_hallazgo(
            "genero_inconsistente",
            "marcador /a junto a masculino genérico",
            marcador.group(0), "media"))
    if not re.search(
            r"\b(?:hombre|mujer|var[oó]n|chico|chica|ni[nñ]o|ni[nñ]a|"
            r"se[nñ]or|se[nñ]ora)\b|\bsoy\s+(?:hombre|mujer)\b",
            normalizar(human)):
        for patron in _FEMENINO_DIRIGIDO:
            m = re.search(patron, normalizar(gpt))
            if m:
                hallazgos.append(_hallazgo(
                    "genero_asumido", "atribuye género sin dato en el prompt",
                    m.group(0), "media"))
                break

    pregunta = _pregunta(human)
    if bloque in FAMILIAS_ASTRO and _PREGUNTA_FUTURO.search(pregunta or "") \
            and not _STOP_TRANSITOS.search(human):
        hallazgos.append(_hallazgo(
            "pregunta_sin_datos",
            "pregunta por el futuro sin tránsitos ni fechas en el prompt",
            pregunta, "alta"))

    limpio = gpt.rstrip()
    if limpio and not re.search(r"[.!?…)»\"]\s*$", limpio):
        hallazgos.append(_hallazgo(
            "truncamiento", "final sin puntuación terminal", limpio[-160:], "alta"))

    if bloque in FAMILIAS_TAROT:
        cartas = _cartas_prompt(human)
        if cartas:
            mencionadas = sum(1 for c in cartas if _menciona_carta(gpt, c))
            if mencionadas < max(1, len(cartas) // 2):
                hallazgos.append(_hallazgo(
                    "referencia_ausente",
                    f"solo menciona {mencionadas} de {len(cartas)} cartas dibujadas",
                    ", ".join(cartas[:6]), "alta"))
    elif bloque in FAMILIAS_ASTRO:
        presentes_astro = [p for p in ("Sol", "Luna", "Ascendente")
                           if normalizar(p) in normalizar(gpt)]
        if len(presentes_astro) < 2:
            hallazgos.append(_hallazgo(
                "referencia_ausente", "no interpreta Sol, Luna y Ascendente",
                ", ".join(presentes_astro), "alta"))
    elif bloque == "numerologia":
        numeros = _numeros_prompt(human)
        if numeros and not any(str(n) in gpt for n in numeros):
            hallazgos.append(_hallazgo(
                "referencia_ausente", "no menciona ningún número calculado",
                "", "alta"))

    vistas = Counter(normalizar(o) for o in _oraciones(gpt) if len(normalizar(o)) >= 50)
    repetidas = [o for o, n in vistas.items() if n >= 2]
    if repetidas:
        hallazgos.append(_hallazgo(
            "repeticion_interna", f"{len(repetidas)} frases repetidas dentro de la lectura",
            repetidas[0], "media"))

    return hallazgos


def _percentil(valores, p):
    if not valores:
        return 0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, max(0, round((len(ordenados) - 1) * p)))
    return ordenados[indice]


def analizar_lecturas(lecturas, kb=None):
    kb = kb or cargar_kb()
    por_id = {l["id"]: [] for l in lecturas}
    for lectura in lecturas:
        por_id[lectura["id"]] = analizar_lectura(lectura, kb)

    primeras = Counter(
        normalizar(_primera_frase(l["gpt"])) for l in lecturas
        if not _es_cabecera_esquema(_primera_frase(l["gpt"])))
    ultimas = Counter(normalizar(_ultima_frase(l["gpt"])) for l in lecturas)
    frases = defaultdict(set)
    for lectura in lecturas:
        for oracion in _oraciones(lectura["gpt"]):
            norm = normalizar(oracion)
            if len(norm) >= 50:
                frases[norm].add(lectura["id"])

    for lectura in lecturas:
        primera = normalizar(_primera_frase(lectura["gpt"]))
        ultima = normalizar(_ultima_frase(lectura["gpt"]))
        if primera and not _es_cabecera_esquema(primera) and primeras[primera] >= 3:
            por_id[lectura["id"]].append(_hallazgo(
                "apertura_repetida",
                f"misma apertura en {primeras[primera]} lecturas",
                _primera_frase(lectura["gpt"]), "alta"))
        if ultima and ultimas[ultima] >= 3:
            por_id[lectura["id"]].append(_hallazgo(
                "cierre_repetido",
                f"mismo cierre en {ultimas[ultima]} lecturas",
                _ultima_frase(lectura["gpt"]), "alta"))
        for oracion in _oraciones(lectura["gpt"]):
            norm = normalizar(oracion)
            if len(norm) >= 50 and len(frases[norm]) >= 3:
                por_id[lectura["id"]].append(_hallazgo(
                    "frase_plantilla",
                    f"frase idéntica en {len(frases[norm])} lecturas",
                    oracion, "alta"))
                break

    longitudes = defaultdict(list)
    for lectura in lecturas:
        longitudes[lectura["bloque"]].append(len(lectura["gpt"]))
    medianas = {b: statistics.median(v) for b, v in longitudes.items()}
    for lectura in lecturas:
        mediana = medianas[lectura["bloque"]]
        largo = len(lectura["gpt"])
        if mediana and (largo < 0.5 * mediana or largo > 2 * mediana):
            por_id[lectura["id"]].append(_hallazgo(
                "longitud_atipica",
                f"{largo} caracteres; mediana de {lectura['bloque']}: {mediana:.0f}",
                "", "media"))

    resumen = {}
    for codigo in CODIGOS:
        ejemplos = []
        total = 0
        casos = 0
        por_bloque = Counter()
        for lectura in lecturas:
            del_codigo = [h for h in por_id[lectura["id"]] if h["codigo"] == codigo]
            if not del_codigo:
                continue
            total += 1
            casos += len(del_codigo)
            por_bloque[lectura["bloque"]] += 1
            if len(ejemplos) < 5:
                ejemplos.append({
                    "id": lectura["id"], "bloque": lectura["bloque"],
                    "detalle": del_codigo[0]["detalle"],
                    "evidencia": del_codigo[0]["evidencia"],
                })
        if total:
            resumen[codigo] = {
                "total": total,
                "casos": casos,
                "porcentaje": round(100 * total / max(1, len(lecturas)), 1),
                "por_bloque": dict(sorted(por_bloque.items())),
                "ejemplos": ejemplos,
            }

    plantillas = [
        {"frase": frase, "lecturas": len(ids)}
        for frase, ids in frases.items() if len(ids) >= 3
    ]
    plantillas.sort(key=lambda x: (-x["lecturas"], x["frase"]))

    def top(counter, n=10):
        return [{"texto": t, "lecturas": c} for t, c in counter.most_common(n) if t]

    estadisticas = {}
    for bloque, valores in sorted(longitudes.items()):
        estadisticas[bloque] = {
            "lecturas": len(valores),
            "min": min(valores),
            "p10": _percentil(valores, 0.10),
            "mediana": int(statistics.median(valores)),
            "p90": _percentil(valores, 0.90),
            "max": max(valores),
        }

    return {
        "lecturas": len(lecturas),
        "por_bloque": dict(sorted(Counter(l["bloque"] for l in lecturas).items())),
        "longitudes": estadisticas,
        "aperturas_repetidas": top(primeras),
        "cierres_repetidos": top(ultimas),
        "plantillas": plantillas[:50],
        "plantillas_total": len(plantillas),
        "hallazgos": resumen,
        "detalle": {l["id"]: por_id[l["id"]] for l in lecturas},
        "umbrales_propuestos": {
            "apertura_repetida": "máximo 2 lecturas con la misma primera frase",
            "cierre_repetido": "máximo 2 lecturas con la misma última frase",
            "frase_plantilla": "ninguna frase de >=50 caracteres en >=3 lecturas",
            "muletilla": "máximo 1 muletilla por lectura, ninguna en >2% del corpus",
            "lista_en_prosa": "0 listas en lectura_completa y cruz_celta",
            "esquema_incumplido": "0 incumplimientos de límites del esquema",
            "longitud_atipica": "fuera de [0,5x mediana, 2x mediana] de la familia",
            "genero_inconsistente": "0 marcadores /a mezclados con masculino genérico",
            "genero_asumido": "0 adjetivos de género sin dato en el prompt",
            "astro_signo_contradicho": "0 contradicciones con las posiciones del prompt",
            "astro_casa_contradicha": "0 contradicciones de casa con el prompt",
            "astro_ascendente_contradicho": "0 confusiones de signo con el Ascendente",
            "pregunta_sin_datos": "0 preguntas de tránsitos sin tránsitos en el prompt",
            "truncamiento": "0 lecturas sin puntuación terminal",
            "referencia_ausente": "cobertura de cartas dibujadas >= 0,8",
            "repeticion_interna": "0 frases de >=50 caracteres repetidas en la lectura",
        },
    }


def exportar_muestra(lecturas, salida, n=12, semilla=20261021):
    grupos = defaultdict(list)
    for lectura in lecturas:
        grupos[lectura["bloque"]].append(lectura)
    rng = random.Random(semilla)
    muestra = []
    for bloque in sorted(grupos):
        candidatas = sorted(grupos[bloque], key=lambda l: l["id"])
        muestra.extend(rng.sample(candidatas, min(n, len(candidatas))))
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8") as fh:
        for lectura in muestra:
            fh.write(json.dumps({
                "id": lectura["id"],
                "bloque": lectura["bloque"],
                "human": lectura["human"],
                "gpt": lectura["gpt"],
                "calculos": lectura["calculos"],
            }, ensure_ascii=False) + "\n")
    return len(muestra)


def escribir_markdown(informe, ruta, top=10):
    lineas = [
        "# Informe de calidad de las lecturas de Mercury",
        "",
        f"Lecturas analizadas: **{informe['lecturas']}**.",
        "",
        "## Longitudes por familia",
        "",
        "| Bloque | N | Mín. | p10 | Mediana | p90 | Máx. |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for bloque, datos in informe["longitudes"].items():
        lineas.append(
            f"| {bloque} | {datos['lecturas']} | {datos['min']} | {datos['p10']} | "
            f"{datos['mediana']} | {datos['p90']} | {datos['max']} |")
    lineas += ["", "## Hallazgos", "",
               "| Código | Casos | % corpus | Familias principales |",
               "|---|---:|---:|---|"]
    for codigo, datos in sorted(
            informe["hallazgos"].items(), key=lambda kv: -kv[1]["total"]):
        familias = ", ".join(
            f"{b} ({n})" for b, n in sorted(
                datos["por_bloque"].items(), key=lambda kv: -kv[1])[:4])
        lineas.append(
            f"| `{codigo}` | {datos['total']} | {datos['porcentaje']}% | {familias} |")
    lineas += ["", "## Aperturas más repetidas", "",
               "| Apertura | Lecturas |", "|---|---:|"]
    for item in informe["aperturas_repetidas"][:top]:
        lineas.append(f"| {item['texto'][:150]} | {item['lecturas']} |")
    lineas += ["", "## Cierres más repetidos", "",
               "| Cierre | Lecturas |", "|---|---:|"]
    for item in informe["cierres_repetidos"][:top]:
        lineas.append(f"| {item['texto'][:150]} | {item['lecturas']} |")
    lineas += ["", "## Frases plantilla", "",
               f"Frases de 50 caracteres o más repetidas en 3 o más lecturas: "
               f"**{informe['plantillas_total']}** tipos.", ""]
    for item in informe["plantillas"][:top]:
        lineas.append(f"- {item['lecturas']} lecturas: «{item['frase'][:180]}»")
    lineas += ["", "## Umbrales propuestos", ""]
    for clave, valor in informe["umbrales_propuestos"].items():
        lineas.append(f"- `{clave}`: {valor}")
    lineas += ["", "## Ejemplos por código", ""]
    for codigo, datos in sorted(
            informe["hallazgos"].items(), key=lambda kv: -kv[1]["total"]):
        lineas.append(f"### `{codigo}` ({datos['total']})")
        for ejemplo in datos["ejemplos"][:3]:
            lineas.append(
                f"- id {ejemplo['id']} ({ejemplo['bloque']}): {ejemplo['detalle']}"
                + (f". «{ejemplo['evidencia']}»" if ejemplo["evidencia"] else ""))
        lineas.append("")
    Path(ruta).write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="entrada", required=True)
    parser.add_argument("--out-dir", dest="salida", required=True)
    parser.add_argument("--muestra", type=int, default=0)
    parser.add_argument("--semilla", type=int, default=20261021)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    lecturas = cargar_lecturas(args.entrada)
    informe = analizar_lecturas(lecturas)
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "informe.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    escribir_markdown(informe, salida / "informe.md", args.top)
    if args.muestra:
        hechas = exportar_muestra(
            lecturas, salida / f"muestra_{args.muestra}.jsonl",
            args.muestra, args.semilla)
        print(f"muestra: {hechas} lecturas en {salida / f'muestra_{args.muestra}.jsonl'}")
    print(f"lecturas: {informe['lecturas']} -> {salida / 'informe.json'}")
    for codigo, datos in sorted(
            informe["hallazgos"].items(), key=lambda kv: -kv[1]["total"]):
        print(f"{codigo:24s} {datos['total']:6d}  {datos['porcentaje']:5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
