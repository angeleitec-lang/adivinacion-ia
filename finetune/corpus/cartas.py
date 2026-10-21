#!/usr/bin/env python3
"""Catálogo de cartas (tarot y baraja española) y normalización de nombres.

Diseño A4 (track A4.1). Los subtítulos automáticos de YouTube escriben los
nombres con minúsculas, sin tildes, con artículos de más y con errores
típicos («la papisa», «paje de pentáculos», «la reina de copas invertido»);
este módulo identifica las cartas contra un catálogo cerrado para que las
etapas de extracción y validación no acepten cartas inventadas.

API:
    CARTAS_TAROT          78 entradas {"id","nombre","arcano","palo","numero","sinonimos"}
    NAIPES_ESPANOLES      40 entradas con el mismo esquema
    norm(texto)           minúsculas, sin tildes, sin signos, espacios simples
    normalizar_carta(texto, mazo="tarot")  -> entrada del catálogo o None
    extraer_cartas(texto, mazo="tarot")    -> menciones en orden de aparición
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Datos de referencia (los de SIGUIENTE.md; no inventar otros)
# ---------------------------------------------------------------------------

# (nombre canónico, sinónimos con artículo tal cual aparecen en subtítulos)
_MAYORES = [
    ("El Loco", ["el loco", "el necio"]),
    ("El Mago", ["el mago", "el mago de los bastos", "el bateleur",
                 "el prestidigitador"]),
    ("La Sacerdotisa", ["la sacerdotisa", "la alta sacerdotisa", "la papisa"]),
    ("La Emperatriz", ["la emperatriz"]),
    ("El Emperador", ["el emperador"]),
    ("El Hierofante", ["el hierofante", "el papa", "el sumo sacerdote"]),
    ("Los Enamorados", ["los enamorados", "el enamorado", "los amantes"]),
    ("El Carro", ["el carro", "el carruaje"]),
    ("La Fuerza", ["la fuerza", "la fortaleza"]),
    ("El Ermitaño", ["el ermitaño", "el eremita"]),
    ("La Rueda de la Fortuna", ["la rueda de la fortuna", "la rueda"]),
    ("La Justicia", ["la justicia"]),
    ("El Colgado", ["el colgado", "el ahorcado"]),
    ("La Muerte", ["la muerte", "el arcano sin nombre"]),
    ("La Templanza", ["la templanza", "la temperancia"]),
    ("El Diablo", ["el diablo"]),
    ("La Torre", ["la torre", "la casa de dios", "la torre herida"]),
    ("La Estrella", ["la estrella"]),
    ("La Luna", ["la luna"]),
    ("El Sol", ["el sol"]),
    ("El Juicio", ["el juicio", "el juicio final", "el angel"]),
    ("El Mundo", ["el mundo"]),
]

_PALOS = ["Bastos", "Copas", "Espadas", "Oros"]

_PALO_SINONIMOS = {
    "Bastos": ["palos", "varas"],
    "Copas": [],
    "Espadas": [],
    "Oros": ["pentaculos", "denarios", "monedas"],
}

# Rangos del tarot: 1-14 (As..Rey) con sus formas habituales en subtítulos
_RANGOS_TAROT = [
    ("As", 1, ["uno"]),
    ("Dos", 2, []),
    ("Tres", 3, []),
    ("Cuatro", 4, []),
    ("Cinco", 5, []),
    ("Seis", 6, []),
    ("Siete", 7, []),
    ("Ocho", 8, []),
    ("Nueve", 9, []),
    ("Diez", 10, []),
    ("Sota", 11, ["paje", "jota"]),
    ("Caballero", 12, ["caballo"]),
    ("Reina", 13, []),
    ("Rey", 14, []),
]

# Equivalencias inglesas de palo y rango para el tarot (los libros en inglés
# nombran las menores como «<Rank> of <Suit>»: King of Wands, Page of Cups).
# Solo se aplican al mazo tarot; los naipes franceses (hearts, diamonds,
# clubs, spades) NO son cartas de tarot y quedan fuera a propósito.
_EN_PALO = {
    "Bastos": ["wands"],
    "Copas": ["cups"],
    "Espadas": ["swords"],
    "Oros": ["pentacles", "coins", "disks", "discs"],
}

_EN_RANGO = {
    1: ["ace"],
    2: ["two"],
    3: ["three"],
    4: ["four"],
    5: ["five"],
    6: ["six"],
    7: ["seven"],
    8: ["eight"],
    9: ["nine"],
    10: ["ten"],
    11: ["page"],
    12: ["knight"],
    13: ["queen"],
    14: ["king"],
}

# Baraja española: 10 cartas por palo (As, 2-7, Sota, Caballo, Rey)
_RANGOS_NAIPE = [
    ("As", 1, ["uno"]),
    ("Dos", 2, []),
    ("Tres", 3, []),
    ("Cuatro", 4, []),
    ("Cinco", 5, []),
    ("Seis", 6, []),
    ("Siete", 7, []),
    ("Sota", 8, ["paje", "jota"]),
    ("Caballo", 9, ["caballero"]),
    ("Rey", 10, []),
]


def _mayores():
    entradas = []
    for numero, (nombre, sinonimos) in enumerate(_MAYORES, start=1):
        entradas.append({
            "id": f"tarot-mayor-{numero:02d}",
            "nombre": nombre,
            "arcano": "mayor",
            "palo": None,
            "numero": numero,
            "sinonimos": list(sinonimos),
        })
    return entradas


def _menores(rangos, prefijo_id, etiqueta, en_palo=None, en_rango=None):
    """Construye las cartas menores: «<Rango> de <Palo>» con sinónimos
    composicionales (rangos × palos) y numerales («2 de oros»).

    Si se pasan `en_palo` y `en_rango` (solo el tarot), añade además las
    formas inglesas «<rank> of <suit>» que usan los libros en inglés."""
    entradas = []
    for palo in _PALOS:
        for rango, numero, extras_rango in rangos:
            sinonimos = []
            variantes_rango = [rango] + extras_rango
            variantes_palo = [palo] + _PALO_SINONIMOS[palo]
            for vr in variantes_rango:
                for vp in variantes_palo:
                    forma = f"{vr} de {vp}"
                    if forma.lower() != f"{rango} de {palo}".lower():
                        sinonimos.append(forma)
            if numero >= 2 and numero <= 10:
                sinonimos.append(f"{numero} de {palo}")
            if en_palo is not None and en_rango is not None:
                for er in en_rango.get(numero, []):
                    for ep in en_palo[palo]:
                        sinonimos.append(f"{er} of {ep}")
            entradas.append({
                "id": f"{prefijo_id}-{palo.lower()}-{numero:02d}",
                "nombre": f"{rango} de {palo}",
                "arcano": etiqueta,
                "palo": palo,
                "numero": numero,
                "sinonimos": sinonimos,
            })
    return entradas


CARTAS_TAROT = _mayores() + _menores(
    _RANGOS_TAROT, "tarot", "menor", en_palo=_EN_PALO, en_rango=_EN_RANGO)
NAIPES_ESPANOLES = _menores(_RANGOS_NAIPE, "naipe", "menor")

_MAZOS = {
    "tarot": CARTAS_TAROT,
    "espanol": NAIPES_ESPANOLES,
}

# ---------------------------------------------------------------------------
# Normalización de texto
# ---------------------------------------------------------------------------

_SIGNOS_RE = re.compile(r"[^0-9a-z]+")


def norm(texto) -> str:
    """Minúsculas, sin tildes, sin signos y con espacios simples."""
    if not texto:
        return ""
    decompuesto = unicodedata.normalize("NFD", str(texto).lower())
    sin_tildes = "".join(ch for ch in decompuesto
                         if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", _SIGNOS_RE.sub(" ", sin_tildes)).strip()


def _catalogo(mazo):
    clave = norm(mazo or "tarot")
    if clave in ("espanol", "naipes", "baraja", "baraja espanola"):
        return NAIPES_ESPANOLES
    return CARTAS_TAROT


# ---------------------------------------------------------------------------
# Índice de variantes normalizadas (para normalizar_carta)
# ---------------------------------------------------------------------------

_ARTICULO_RE = re.compile(r"^(?:el|la|los|las|un|una)\s+")
_PARTITIVA_RE = re.compile(r"^(?:del|de la|de el|de los|de las|de)\s+")
_ORIENTACION_FINAL_RE = re.compile(
    r"\s+(?:inver\w*|(?:al|del)?\s+reves|derech\w*)$")


def _variantes_de(nombre, sinonimos):
    """Todas las formas de llamar a la carta ya normalizadas, incluidas las
    versiones sin artículo (los subtítulos a veces lo pierden)."""
    formas = [nombre] + list(sinonimos)
    variantes = set()
    for forma in formas:
        base = norm(forma)
        pendientes = [base]
        while pendientes:
            cand = pendientes.pop()
            if not cand:
                continue
            variantes.add(cand)
            sin_art = _ARTICULO_RE.sub("", cand)
            if sin_art != cand:
                pendientes.append(sin_art)
    return variantes


_INDICE_CACHE: dict = {}


def _indice(mazo):
    if mazo not in _INDICE_CACHE:
        indice = {}
        for entrada in _catalogo(mazo):
            for variante in _variantes_de(entrada["nombre"],
                                          entrada["sinonimos"]):
                indice.setdefault(variante, entrada)
        _INDICE_CACHE[mazo] = indice
    return _INDICE_CACHE[mazo]


def _candidatos(consulta):
    """Formas a probar contra el índice: tal cual, sin orientación final,
    sin artículo y con las partículas iniciales retiradas."""
    base = norm(consulta)
    candidatos = []
    pendientes = [base]
    while pendientes:
        cand = pendientes.pop()
        if not cand or cand in candidatos:
            continue
        candidatos.append(cand)
        sin_or = _ORIENTACION_FINAL_RE.sub("", cand)
        if sin_or != cand:
            pendientes.append(sin_or)
        sin_art = _ARTICULO_RE.sub("", cand)
        if sin_art != cand:
            pendientes.append(sin_art)
        sin_part = _PARTITIVA_RE.sub("", cand)
        if sin_part != cand:
            pendientes.append(sin_part)
        if cand.startswith("carta "):
            pendientes.append(cand[6:])
    return candidatos


def normalizar_carta(texto, mazo="tarot"):
    """Entrada del catálogo si `texto` identifica una carta; None si no.

    Admite artículo, mayúsculas, sinónimos y errores típicos del subtítulo
    automático (minúsculas, sin tildes, «invertido» colgado del nombre).
    """
    indice = _indice(mazo)
    for cand in _candidatos(texto):
        entrada = indice.get(cand)
        if entrada is not None:
            return entrada
    return None


# ---------------------------------------------------------------------------
# Extracción de menciones en un texto
# ---------------------------------------------------------------------------

# Nombres ambiguos (arcanos mayores cuyo nombre es palabra cotidiana)
# En modo contextual solo cuentan si tienen indicador de orientación,
# palabras de contexto tarot cerca, o están cerca de otra carta no ambigua.
_AMBIGUOS = {
    "el sol", "la luna", "el mundo", "la fuerza", "el juicio",
    "la muerte", "la justicia", "la estrella", "el carro", "la torre",
    "el diablo", "el loco", "el mago", "la templanza", "el colgado",
    "la emperatriz", "el emperador", "la sacerdotisa", "el ermitaño",
    "los enamorados", "la rueda de la fortuna", "el hierofante",
}

_PALABRAS_CONTEXTO = {
    "carta", "cartas", "arcano", "arcanos", "tarot", "salio",
    "saco", "aparece", "tirada", "posicion", "significa", "representa",
}

_MENCION_CACHE: dict = {}


def _regex_menciones(mazo):
    """Alternación de todas las variantes, de más larga a más corta, con
    bordes de palabra para no entrar en medio de otra («casas» no contiene
    «as»)."""
    if mazo in _MENCION_CACHE:
        return _MENCION_CACHE[mazo]
    variantes = set()
    for entrada in _catalogo(mazo):
        variantes |= _variantes_de(entrada["nombre"], entrada["sinonimos"])
    ordenadas = sorted(variantes, key=len, reverse=True)
    patron = "|".join(re.escape(v) for v in ordenadas)
    regex = re.compile(r"(?<![0-9a-z])(?:" + patron + r")(?![0-9a-z])")
    _MENCION_CACHE[mazo] = regex
    return regex


_INVERTIDA_RE = re.compile(r"\binver\w*|\b(?:al|del)?\s?reves\b")
_DERECHA_RE = re.compile(r"\bderech\w*\b")


def _orientacion(texto, fin, limite, indice_siguiente):
    """Orientación en las hasta 4 palabras posteriores al nombre, sin
    cruzarse con la mención siguiente."""
    ventana = texto[fin:limite] if limite > fin else ""
    palabras = ventana.split()[:4]
    if not palabras:
        return None
    muestra = " " + " ".join(palabras) + " "
    if _INVERTIDA_RE.search(muestra):
        return "invertida"
    if _DERECHA_RE.search(muestra):
        return "derecha"
    return None


def extraer_cartas(texto, mazo="tarot", contextual=True):
    """Menciones en orden de aparición.

    Cada elemento es {"carta": entrada del catálogo,
    "orientacion": "derecha"|"invertida"|None,
    "posicion_texto": índice de carácter en el texto normalizado}.
    «invertida/al revés» hasta 4 palabras después del nombre marca invertida.

    Si contextual=True (por defecto), los nombres ambiguos (El Sol, La Luna,
    El Mundo, La Fuerza, El Juicio, La Muerte, La Justicia, La Estrella,
    El Carro, La Torre, El Diablo, El Loco, El Mago, La Templanza,
    El Colgado, La Emperatriz, El Emperador, La Sacerdotisa, El Ermitaño,
    Los Enamorados, La Rueda de la Fortuna, El Hierofante) solo cuentan si
    cumplen al menos una condición: (a) van seguidos en ≤4 palabras de
    invertid*/al revés/al derecho/derecho; (b) hay en ±8 palabras alguna
    palabra de contexto tarot (carta, arcano, tarot, salió, sale, sacó,
    aparece, tirada, posición, significa, representa); (c) están a ≤12
    palabras de otra carta no ambigua ya aceptada.
    """
    consulta = norm(texto)
    if not consulta:
        return []
    regex = _regex_menciones(mazo)
    coincidencias = list(regex.finditer(consulta))
    indice = _indice(mazo)
    menciones = []
    # Para modo contextual: mantener conjunto de posiciones de cartas no ambiguas
    # aceptadas (índice de palabra en texto normalizado)
    pos_no_ambiguas = []
    palabras_texto = consulta.split()
    
    for i, coinc in enumerate(coincidencias):
        entrada = indice.get(coinc.group(0))
        if entrada is None:
            continue
        
        # Modo contextual: verificar si carta ambigua cumple condiciones
        if contextual:
            nombre_norm = norm(entrada["nombre"])
            if nombre_norm in _AMBIGUOS:
                # Calcular posición en palabras
                palabra_inicio = len(consulta[:coinc.start()].split())
                palabra_fin = len(consulta[:coinc.end()].split())
                
                # (a) orientación en ≤4 palabras después
                fin = coinc.end()
                if i + 1 < len(coincidencias):
                    limite_palabra = coincidencias[i + 1].start()
                else:
                    limite_palabra = min(fin + 60, len(consulta))
                orientacion = _orientacion(consulta, fin, limite_palabra, None)
                if orientacion is not None:
                    pass  # cumple condición (a)
                else:
                    # (b) palabras de contexto en ventana ±8 palabras
                    ini_ventana = max(0, palabra_inicio - 8)
                    fin_ventana = min(len(palabras_texto), palabra_fin + 8)
                    ventana_palabras = set(palabras_texto[ini_ventana:fin_ventana])
                    if not (ventana_palabras & _PALABRAS_CONTEXTO):
                        # (c) a ≤12 palabras de otra carta no ambigua ya aceptada
                        cerca_no_ambigua = any(
                            abs(palabra_inicio - p) <= 12 for p in pos_no_ambiguas)
                        if not cerca_no_ambigua:
                            continue  # rechazar esta mención ambigua
            else:
                # No ambigua: registrar posición para futuras referencias
                palabra_inicio = len(consulta[:coinc.start()].split())
                pos_no_ambiguas.append(palabra_inicio)
        
        fin = coinc.end()
        if i + 1 < len(coincidencias):
            limite_palabra = coincidencias[i + 1].start()
        else:
            limite_palabra = min(fin + 60, len(consulta))
        orientacion = _orientacion(consulta, fin, limite_palabra, None)
        menciones.append({
            "carta": entrada,
            "orientacion": orientacion,
            "posicion_texto": coinc.start(),
        })
    return menciones


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Prueba manual del catálogo de cartas.")
    parser.add_argument("texto", help="Texto a analizar")
    parser.add_argument("--mazo", default="tarot",
                        help="tarot (por defecto) o español")
    args = parser.parse_args()
    print(json.dumps(extraer_cartas(args.texto, mazo=args.mazo),
                     ensure_ascii=False, indent=2, default=str))
