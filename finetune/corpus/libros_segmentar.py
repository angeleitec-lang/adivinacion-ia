"""Segmentación de libros limpios en capítulos y secciones con sentido.

`segmentar(texto_limpio, familia, id_libro="")` detecta encabezados (markdown,
CHAPTER/CAPÍTULO, numeración seguida de título en mayúsculas y líneas cortas en
mayúsculas) y, en tarot/baraja/astrología/numerología, también entidades: las 78
cartas, signos, planetas y los números 1-9/11/22/33. Las secciones de menos de
400 caracteres sin encabezado se funden con la anterior; las de más de 12.000 se
parten por párrafos con 300 caracteres de solape. Los títulos nunca superan 80
caracteres ni acaban en preposición o artículo.
"""
import re
import unicodedata

MIN_SECCION = 400
MAX_SECCION = 12000
SOLAPE = 300

try:
    from cartas import normalizar_carta
except ImportError:  # si el catálogo no está disponible, se usa la lista propia
    normalizar_carta = None

MAYORES_ES = (
    ("El Loco", 1), ("El Necio", 1), ("El Mago", 2), ("La Sacerdotisa", 3),
    ("La Papisa", 3), ("La Emperatriz", 4), ("El Emperador", 5),
    ("El Hierofante", 6), ("El Papa", 6), ("El Sumo Sacerdote", 6),
    ("Los Enamorados", 7), ("El Enamorado", 7), ("Los Amantes", 7),
    ("El Carro", 8), ("La Fuerza", 9), ("La Fortaleza", 9), ("El Ermitaño", 10),
    ("El Eremita", 10), ("La Rueda de la Fortuna", 11), ("La Rueda", 11),
    ("La Justicia", 12), ("El Colgado", 13), ("El Ahorcado", 13),
    ("La Muerte", 14), ("La Templanza", 15), ("El Diablo", 16),
    ("La Torre", 17), ("La Estrella", 18), ("La Luna", 19), ("El Sol", 20),
    ("El Juicio", 21), ("El Juicio Final", 21), ("El Mundo", 22),
)

MAYORES_EN = (
    ("The Fool", 1), ("The Magician", 2), ("The High Priestess", 3),
    ("The Empress", 4), ("The Emperor", 5), ("The Hierophant", 6),
    ("The Lovers", 7), ("The Chariot", 8), ("Strength", 9), ("Fortitude", 9),
    ("The Hermit", 10), ("Wheel of Fortune", 11), ("Justice", 12),
    ("The Hanged Man", 13), ("Death", 14), ("Temperance", 15),
    ("The Devil", 16), ("The Tower", 17), ("The Star", 18), ("The Moon", 19),
    ("The Sun", 20), ("Judgement", 21), ("Judgment", 21), ("The World", 22),
)

NOMBRES_MAYORES_EN = (
    "The Fool", "The Magician", "The High Priestess", "The Empress",
    "The Emperor", "The Hierophant", "The Lovers", "The Chariot", "Strength",
    "The Hermit", "Wheel of Fortune", "Justice", "The Hanged Man", "Death",
    "Temperance", "The Devil", "The Tower", "The Star", "The Moon", "The Sun",
    "Judgement", "The World",
)

RANGOS_EN = {"Ace": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6,
             "Seven": 7, "Eight": 8, "Nine": 9, "Ten": 10, "Page": 11,
             "Knight": 12, "Queen": 13, "King": 14}
RANGOS_ES = {"As": 1, "Dos": 2, "Tres": 3, "Cuatro": 4, "Cinco": 5,
             "Seis": 6, "Siete": 7, "Ocho": 8, "Nueve": 9, "Diez": 10,
             "Sota": 11, "Caballero": 12, "Reina": 13, "Rey": 14}
PALOS_EN = {"Wands": ("bastos", "Wands"), "Cups": ("copas", "Cups"),
            "Swords": ("espadas", "Swords"),
            "Pentacles": ("oros", "Pentacles"), "Coins": ("oros", "Coins")}
PALOS_ES = {"Bastos": ("bastos", "Bastos"), "Copas": ("copas", "Copas"),
            "Espadas": ("espadas", "Espadas"), "Oros": ("oros", "Oros")}

SIGNOS = ("Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra",
          "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis",
          "Taurus", "Gemini", "Cancer", "Scorpio", "Sagittarius",
          "Capricorn", "Aquarius", "Pisces")
PLANETAS = ("Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno",
            "Urano", "Neptuno", "Plutón", "Sun", "Moon", "Mercury", "Mars",
            "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
NUMEROS_NUMEROLOGIA = {str(n) for n in range(1, 10)} | {"11", "22", "33"}

FAMILIAS_ENTIDADES = {"tarot", "baraja", "astrologia", "numerologia"}
FAMILIAS_CARTAS = {"tarot", "baraja"}

CAPITULO_RE = re.compile(r"^(?:cap[ií]tulo|chapter)\b", re.IGNORECASE)
NUMERADO_RE = re.compile(r"^(?:[IVXLCDM]+|\d{1,3})[.)-]?\s+(.+)$")
NUMERO_CARD_RE = re.compile(r"^\s*(?:\d{1,2}|[IVXLCDM]+)[.)\-:]?\s+")
RANGO_UP_RE = re.compile(
    r"(?<!\w)(%s)(?=\s+[A-ZÁÉÍÓÚÑ¿¡(])"
    % "|".join(sorted([r.upper() for r in list(RANGOS_EN) + list(RANGOS_ES)],
                      key=len, reverse=True)))
KEY_RE = re.compile(r"\bKey\s+(\d{1,2}|[IVXL]+)\b", re.IGNORECASE)
SUIT_CAP_RE = re.compile(
    r"\b(?:chapter|cap[ií]tulo)\s+\d+\W{0,6}"
    r"(wands|cups|s\s*words|pentacles|bastos|copas|espadas|oros)\b",
    re.IGNORECASE)
SUIT_LINEA_RE = re.compile(
    r"^\s*(wands|cups|s\s*words|pentacles|bastos|copas|espadas|oros)\b",
    re.IGNORECASE)

_STOPWORDS_FINAL = set(
    "de del la el los las un una unos unas y o u en con por para a al que su "
    "sus the of and a an in on with for to at by from or as but is are".split())


def _sin_tildes(texto):
    base = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in base if not unicodedata.combining(c))


def _clave(texto):
    limpio = "".join(c if c.isalnum() else " " for c in _sin_tildes(texto))
    return " ".join(limpio.lower().split())


def _familia_norm(familia):
    return _clave(familia or "")


def _clave_entidad(nombre):
    if normalizar_carta is not None:
        try:
            valor = normalizar_carta(nombre)
            if isinstance(valor, dict) and valor.get("nombre"):
                return _clave(valor["nombre"])
        except Exception:
            pass
    return _clave(nombre)


def _registrar(alias, clave, display, alias_originales, alias_carta):
    alias_carta.setdefault(_clave(alias), (clave, display))
    alias_originales.append(alias)


def _construir_alias():
    originales = []
    alias = {}
    for nombre, numero in MAYORES_ES + MAYORES_EN:
        _registrar(nombre, "tarot-mayor-%02d" % numero, nombre, originales,
                   alias)
    for rango, numero in RANGOS_EN.items():
        for palo, (clave_palo, display_palo) in PALOS_EN.items():
            _registrar("%s of %s" % (rango, palo),
                       "tarot-%s-%02d" % (clave_palo, numero),
                       "%s of %s" % (rango, display_palo),
                       originales, alias)
    for rango, numero in RANGOS_ES.items():
        for palo, (clave_palo, display_palo) in PALOS_ES.items():
            _registrar("%s de %s" % (rango, palo),
                       "tarot-%s-%02d" % (clave_palo, numero),
                       "%s de %s" % (rango, display_palo),
                       originales, alias)
    return alias, originales


ALIAS_CARTA, _ALIAS_ORIGINALES = _construir_alias()
_ALIAS_UP = {a.upper(): datos for a, datos in
             ((a, ALIAS_CARTA[_clave(a)]) for a in _ALIAS_ORIGINALES)}
_RE_ALIAS_UP = re.compile(
    r"(?<!\w)(%s)(?!\w)"
    % "|".join(sorted([re.escape(a) for a in _ALIAS_UP], key=len, reverse=True)))
_RE_ALIAS = re.compile(
    r"(?<!\w)(%s)(?!\w)"
    % "|".join(sorted([re.escape(a) for a in _ALIAS_ORIGINALES],
                      key=len, reverse=True)),
    re.IGNORECASE)
RANGO_UP_EN = {r.upper(): (r, n) for r, n in RANGOS_EN.items()}
RANGO_UP_ES = {r.upper(): (r, n) for r, n in RANGOS_ES.items()}
_SUIT_CANON = {
    "wands": ("bastos", "Wands"), "cups": ("copas", "Cups"),
    "swords": ("espadas", "Swords"), "pentacles": ("oros", "Pentacles"),
    "coins": ("oros", "Coins"), "bastos": ("bastos", "Bastos"),
    "copas": ("copas", "Copas"), "espadas": ("espadas", "Espadas"),
    "oros": ("oros", "Oros"),
}


def _quitar_markdown(linea):
    return re.sub(r"^#+\s*", "", linea).strip()


def _limpiar_titulo(titulo):
    texto = " ".join((titulo or "").split())
    if len(texto) > 80:
        texto = texto[:80].rsplit(" ", 1)[0]
    palabras = texto.split()
    while palabras and _clave(palabras[-1]) in _STOPWORDS_FINAL:
        palabras.pop()
    texto = " ".join(palabras).strip(" .,;:-—")
    return texto or None


def _es_mayusculas(texto):
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 3:
        return False
    return sum(1 for c in letras if c.isupper()) / len(letras) >= 0.80


def _parece_cabecera(prefijo):
    texto = prefijo.strip()
    if not texto:
        return True
    if len(texto) > 70:
        return False
    letras = [c for c in texto if c.isalpha()]
    mayusculas = sum(1 for c in letras if c.isupper())
    return (bool(re.search(r"\d", texto)) or "Figure" in texto
            or "Fig." in texto
            or (letras and mayusculas / len(letras) >= 0.60))


def _suit_de_linea(linea):
    match = SUIT_CAP_RE.search(linea) or SUIT_LINEA_RE.match(linea)
    if not match:
        return None
    clave = re.sub(r"\s+", "", match.group(1).lower())
    return _SUIT_CANON.get(clave)


def _numero_romano(texto):
    if texto.isdigit():
        return int(texto)
    valores = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    total = 0
    previo = 0
    for caracter in reversed(texto.upper()):
        valor = valores.get(caracter, 0)
        total = total - valor if valor < previo else total + valor
        previo = max(previo, valor)
    return total


def _eventos_de_linea(linea, familia, suit):
    if _familia_norm(familia) not in FAMILIAS_CARTAS:
        return []
    eventos = []

    for match in _RE_ALIAS_UP.finditer(linea):
        clave, display = _ALIAS_UP[match.group(1).upper()]
        eventos.append((match.start(), match.end(), clave, display))

    if suit:
        for match in RANGO_UP_RE.finditer(linea):
            token = match.group(1).upper()
            if token in RANGO_UP_EN:
                rango, numero = RANGO_UP_EN[token]
                display = "%s of %s" % (rango, suit[1])
            else:
                rango, numero = RANGO_UP_ES[token]
                display = "%s de %s" % (rango, suit[0].capitalize())
            eventos.append((match.start(), match.end(),
                            "tarot-%s-%02d" % (suit[0], numero), display))

    for match in _RE_ALIAS.finditer(linea):
        prefijo = linea[:match.start()]
        if not _parece_cabecera(prefijo):
            continue
        clave, display = ALIAS_CARTA[_clave(match.group(1))]
        eventos.append((match.start(), match.end(), clave, display))

    for match in KEY_RE.finditer(linea):
        numero = _numero_romano(match.group(1))
        if 0 <= numero <= 21:
            eventos.append((match.start(), match.end(),
                            "tarot-mayor-%02d" % (numero + 1),
                            NOMBRES_MAYORES_EN[numero]))

    eventos.sort(key=lambda e: (e[0], -(e[1] - e[0])))
    return eventos


def _preprocesar_cartas(texto, familia):
    """Marca con «# » los encabezados de carta que van dentro de una línea."""
    salida = []
    vistos = set()
    suit = None
    for linea in texto.splitlines():
        suit_linea = _suit_de_linea(linea)
        if suit_linea:
            suit = suit_linea
        eventos = _eventos_de_linea(linea, familia, suit)
        if not eventos:
            salida.append(linea)
            continue
        cursor = 0
        hubo = False
        for inicio, fin, clave, display in eventos:
            if clave in vistos or inicio < cursor:
                continue
            prefijo = linea[cursor:inicio]
            if prefijo.strip() and not _parece_cabecera(prefijo):
                salida.append(prefijo.strip())
            salida.append("# " + display)
            vistos.add(clave)
            cursor = fin
            hubo = True
        resto = linea[cursor:]
        if resto.strip():
            salida.append(resto.strip())
        elif not hubo:
            salida.append(linea)
    return "\n".join(salida)


_INTRO_TITULOS = {
    "introduccion": "Introducción", "introduction": "Introducción",
    "prologo": "Prólogo", "prologue": "Prólogo",
    "prefacio": "Prefacio", "preface": "Prefacio", "foreword": "Foreword",
}
_INTRO_RE = re.compile(r"^(%s)\b" % "|".join(_INTRO_TITULOS))


def _titulo_intro(texto):
    """Título de introducción si la primera línea lo dice; None en caso contrario."""
    for linea in texto.splitlines():
        if linea.strip():
            match = _INTRO_RE.match(_clave(linea))
            return _INTRO_TITULOS[match.group(1)] if match else None
    return False


# Aperturas típicas de portada, página legal o índice (sobre texto sin tildes).
_FRENTE_APERTURA_RE = re.compile(
    r"^(this book was produced|produced in epub format|internet archive|"
    r"contents|table of contents|indice|pagina legal|copyright|"
    r"all rights reserved|derechos reservados)\b")

# Marcas de créditos/portada en español e inglés (texto sin tildes, en minúsculas).
_MARCAS_CREDITO = (
    "copyright", "©", "all rights reserved", "derechos reservados",
    "reservados todos", "isbn", "978-", "979-", "library of congress",
    "primera edicion", "first edition", "reimpresion", "printed in",
    "impreso en", "published by", "publicado por", "distributed by",
    "distribuido por", "translated by", "traducido por", "ilustrado por",
    "cubierta", "portada", "produced in epub format",
    "optical character recognition",
)


def _es_frente_materia(texto):
    """True si el texto es portada, créditos o índice, no contenido genuino."""
    primera = ""
    for linea in (texto or "").splitlines():
        if linea.strip():
            primera = _sin_tildes(linea).lower()
            break
    if _FRENTE_APERTURA_RE.match(primera):
        return True
    crudo = _sin_tildes(texto or "").lower()[:2000]
    distintas = {m for m in _MARCAS_CREDITO if m in crudo}
    return len(distintas) >= 2


def _titulo_de_linea(linea, familia):
    """Título si la línea es un encabezado; None en caso contrario."""
    texto = linea.strip()
    if not texto:
        return None
    if texto.startswith("#"):
        return _limpiar_titulo(_quitar_markdown(texto))

    sin_marca = _quitar_markdown(texto)
    if CAPITULO_RE.match(sin_marca):
        return _limpiar_titulo(sin_marca)

    familia_norm = _familia_norm(familia)
    if familia_norm in FAMILIAS_ENTIDADES:
        limpio = NUMERO_CARD_RE.sub("", sin_marca)
        if familia_norm in FAMILIAS_CARTAS and _clave(limpio) in ALIAS_CARTA:
            return _limpiar_titulo(ALIAS_CARTA[_clave(limpio)][1])
        if familia_norm == "astrologia":
            if _clave_entidad(limpio) in {_clave(n)
                                          for n in SIGNOS + PLANETAS}:
                return _limpiar_titulo(limpio)
        if (familia_norm == "numerologia"
                and limpio in NUMEROS_NUMEROLOGIA):
            return limpio

    numerado = NUMERADO_RE.match(sin_marca)
    if numerado and _es_mayusculas(numerado.group(1)):
        return _limpiar_titulo(sin_marca)

    if len(sin_marca) <= 80 and _es_mayusculas(sin_marca):
        return _limpiar_titulo(sin_marca)
    return None


def _secciones_crudas(texto, familia):
    secciones = []
    actual = []
    titulo = None
    for linea in texto.splitlines():
        candidato = _titulo_de_linea(linea, familia)
        if candidato is not None:
            cuerpo = "\n".join(actual).strip()
            if cuerpo:
                secciones.append({"titulo": titulo, "texto": cuerpo})
            titulo = candidato
            actual = []
        else:
            actual.append(linea)
    cuerpo = "\n".join(actual).strip()
    if cuerpo:
        secciones.append({"titulo": titulo, "texto": cuerpo})
    return secciones


def _titulo_protegido(titulo, familia):
    """No se funde un encabezado de carta, signo, planeta o número."""
    if not titulo:
        return False
    familia_norm = _familia_norm(familia)
    if familia_norm in FAMILIAS_CARTAS and carta_de_titulo(titulo, familia):
        return True
    if familia_norm == "astrologia":
        return _clave(titulo) in {_clave(n) for n in SIGNOS + PLANETAS}
    if familia_norm == "numerologia":
        return titulo.strip() in NUMEROS_NUMEROLOGIA
    return False


def _fundir_cortas(secciones, familia):
    """Funde las secciones cortas con la anterior salvo encabezados de entidad."""
    resultado = []
    for seccion in secciones:
        corta = len(seccion["texto"]) < MIN_SECCION
        if (resultado and corta
                and not _titulo_protegido(seccion["titulo"], familia)):
            previa = resultado[-1]
            if seccion["texto"]:
                previa["texto"] = (previa["texto"] + "\n\n"
                                   + seccion["texto"]).strip()
        elif seccion["texto"]:
            resultado.append({"titulo": seccion["titulo"],
                              "texto": seccion["texto"]})
    return resultado


def _partir_largo(texto):
    """Parte un texto largo por párrafos con solape de 300 caracteres."""
    if len(texto) <= MAX_SECCION:
        return [texto]
    partes = []
    actual = []
    tamano = 0
    for parrafo in texto.split("\n\n"):
        if len(parrafo) > MAX_SECCION:
            if actual:
                partes.append("\n\n".join(actual))
                actual = []
                tamano = 0
            inicio = 0
            while inicio < len(parrafo):
                fin = min(inicio + MAX_SECCION, len(parrafo))
                partes.append(parrafo[inicio:fin])
                if fin >= len(parrafo):
                    break
                inicio = fin - SOLAPE
            continue
        extra = len(parrafo) + (2 if actual else 0)
        if actual and tamano + extra > MAX_SECCION:
            partes.append("\n\n".join(actual))
            cola = partes[-1][-SOLAPE:]
            actual = [cola, parrafo] if cola else [parrafo]
            tamano = len(cola) + 2 + len(parrafo) if cola else len(parrafo)
        else:
            actual.append(parrafo)
            tamano += extra
    if actual:
        partes.append("\n\n".join(actual))
    return partes


def _titulo_sintetico(texto, posicion):
    primeras = re.findall(r"\S+", texto)[:8]
    base = " ".join(primeras)
    return (_limpiar_titulo("Sección %d — %s" % (posicion, base))
            or "Sección %d" % posicion)


def carta_de_titulo(titulo, familia="tarot"):
    """Clave de carta (p. ej. «tarot-mayor-01») si el título es una carta."""
    if not titulo or _familia_norm(familia) not in FAMILIAS_CARTAS:
        return None
    limpio = NUMERO_CARD_RE.sub("", _quitar_markdown(titulo))
    datos = ALIAS_CARTA.get(_clave(limpio))
    if datos:
        return datos[0]
    if normalizar_carta is not None:
        try:
            entrada = normalizar_carta(limpio)
            if entrada:
                return entrada["id"]
        except Exception:
            pass
    return None


def segmentar(texto_limpio, familia, id_libro=""):
    """Devuelve las secciones de un libro limpio, en orden.

    Cada sección es un dict con `seccion` (ordinal desde 1), `titulo`, `texto`,
    `chars`, `id_libro` y `posicion` (índice desde 0).
    """
    if not texto_limpio or not texto_limpio.strip():
        return []
    texto = _preprocesar_cartas(texto_limpio, familia)
    crudas = _fundir_cortas(_secciones_crudas(texto, familia), familia)
    partes = []
    for cruda in crudas:
        for parte in _partir_largo(cruda["texto"]):
            if parte.strip():
                partes.append({"titulo": cruda["titulo"], "texto": parte})
    secciones = []
    for posicion, parte in enumerate(partes):
        if parte["titulo"]:
            titulo = _limpiar_titulo(parte["titulo"])
        else:
            titulo = None
        frente_materia = False
        if titulo is None:
            intro = _titulo_intro(parte["texto"])
            if intro:
                titulo = intro
            elif _es_frente_materia(parte["texto"]):
                titulo = "Material preliminar"
                frente_materia = True
            else:
                titulo = _titulo_sintetico(parte["texto"], posicion + 1)
        seccion = {
            "seccion": posicion + 1,
            "titulo": titulo,
            "texto": parte["texto"],
            "chars": len(parte["texto"]),
            "id_libro": id_libro,
            "posicion": posicion,
        }
        if frente_materia:
            seccion["front_matter"] = True
        secciones.append(seccion)
    return secciones
