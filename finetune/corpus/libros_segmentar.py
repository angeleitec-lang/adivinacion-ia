"""Segmentación de libros limpios en capítulos y secciones con sentido.

`segmentar(texto_limpio, familia, id_libro="")` detecta encabezados (markdown,
CHAPTER/CAPÍTULO, numeración seguida de título en mayúsculas y líneas cortas en
mayúsculas) y, en tarot/baraja/astrología/numerología, también entidades (arcanos
mayores, signos, planetas y números del 1 al 9). Las secciones de menos de 400
caracteres se funden con la anterior y las de más de 12.000 se parten por
párrafos con 300 caracteres de solape.
"""
import re
import unicodedata

MIN_SECCION = 400
MAX_SECCION = 12000
SOLAPE = 300

try:
    from cartas import normalizar_carta
except ImportError:  # el módulo cartas aún no existe en esta rama
    normalizar_carta = None

ARCANOS_MAYORES = (
    "El Loco", "El Mago", "La Sacerdotisa", "La Emperatriz", "El Emperador",
    "El Hierofante", "El Sumo Sacerdote", "El Papa", "Los Enamorados",
    "El Carro", "La Fuerza", "La Justicia", "El Ermitaño",
    "La Rueda de la Fortuna", "El Colgado", "La Muerte", "La Templanza",
    "El Diablo", "La Torre", "La Estrella", "La Luna", "El Sol", "El Juicio",
    "El Mundo",
)

SIGNOS = (
    "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra",
    "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis",
)

PLANETAS = (
    "Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno",
    "Urano", "Neptuno", "Plutón",
)

FAMILIAS_ENTIDADES = {"tarot", "baraja", "astrologia", "numerologia"}

CAPITULO_RE = re.compile(r"^(?:cap[ií]tulo|chapter)\b", re.IGNORECASE)
NUMERADO_RE = re.compile(r"^(?:[IVXLCDM]+|\d{1,3})[.)-]?\s+(.+)$")
NUMERO_SUELTO_RE = re.compile(r"^[1-9]$")


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
            if isinstance(valor, str) and valor:
                return _clave(valor)
        except Exception:
            pass
    return _clave(nombre)


ENTIDADES = {
    "tarot": {_clave(n) for n in ARCANOS_MAYORES},
    "astrologia": {_clave(n) for n in SIGNOS + PLANETAS},
}


def _quitar_markdown(linea):
    return re.sub(r"^#+\s*", "", linea).strip()


def _es_mayusculas(texto):
    letras = [c for c in texto if c.isalpha()]
    if len(letras) < 3:
        return False
    return sum(1 for c in letras if c.isupper()) / len(letras) >= 0.80


def _titulo_de_linea(linea, familia):
    """Título si la línea es un encabezado; None en caso contrario."""
    texto = linea.strip()
    if not texto:
        return None
    if texto.startswith("#"):
        titulo = _quitar_markdown(texto)
        if titulo:
            return titulo

    sin_marca = _quitar_markdown(texto)
    if CAPITULO_RE.match(sin_marca):
        return sin_marca

    if _familia_norm(familia) in FAMILIAS_ENTIDADES:
        if _familia_norm(familia) in ENTIDADES:
            if _clave_entidad(sin_marca) in ENTIDADES[_familia_norm(familia)]:
                return sin_marca
        if (_familia_norm(familia) == "numerologia"
                and NUMERO_SUELTO_RE.match(sin_marca)):
            return sin_marca

    numerado = NUMERADO_RE.match(sin_marca)
    if numerado and _es_mayusculas(numerado.group(1)):
        return sin_marca

    if len(sin_marca) <= 80 and _es_mayusculas(sin_marca):
        return sin_marca
    return None


def _secciones_crudas(texto, familia):
    secciones = []
    actual = []
    titulo = "Introducción"
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


def _fundir_cortas(secciones):
    resultado = []
    for seccion in secciones:
        if resultado and len(seccion["texto"]) < MIN_SECCION:
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


def segmentar(texto_limpio, familia, id_libro=""):
    """Devuelve las secciones de un libro limpio, en orden.

    Cada sección es un dict con `seccion` (ordinal desde 1), `titulo`, `texto`,
    `chars`, `id_libro` y `posicion` (índice desde 0).
    """
    if not texto_limpio or not texto_limpio.strip():
        return []
    crudas = _fundir_cortas(_secciones_crudas(texto_limpio, familia))
    secciones = []
    for cruda in crudas:
        for parte in _partir_largo(cruda["texto"]):
            if not parte.strip():
                continue
            secciones.append({
                "titulo": cruda["titulo"],
                "texto": parte,
                "chars": len(parte),
            })
    for posicion, seccion in enumerate(secciones):
        seccion["seccion"] = posicion + 1
        seccion["posicion"] = posicion
        seccion["id_libro"] = id_libro
    orden = ("seccion", "titulo", "texto", "chars", "id_libro", "posicion")
    return [{clave: seccion[clave] for clave in orden} for seccion in secciones]
