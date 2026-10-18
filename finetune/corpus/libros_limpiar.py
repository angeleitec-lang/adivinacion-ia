"""Limpieza de textos OCR y EPUB de la pista de libros (F0.2).

`limpiar(texto, idioma)` descarta páginas con OCR poco fiable, quita cabeceras
y números de página, des-guiona palabras partidas, une líneas de margen, elimina
ruido de OCR y recorta portada e índice. Devuelve el texto limpio y un informe
con las métricas del proceso. No traduce ni reescribe el contenido.
"""
import re
import unicodedata

# Aviso de OCR que archive.org inserta por página. Acepta «Page N» opcional,
# coma decimal y mayúsculas variables.
AVISO_RE = re.compile(
    r"(?:Page\s+\d+\s*)?The text on this page is estimated to be only\s*"
    r"(\d+(?:[.,]\d+)?)\s*%\s*accurate",
    re.IGNORECASE)

NUMERO_PAGINA_RE = re.compile(r"^\s*(?:\d{1,4}|Page\s+\d+)\s*$", re.IGNORECASE)

MARCAS_PORTADA = ("all rights reserved", "isbn", "copyright",
                  "library of congress")

TERMINALES = ".?!:»\"”’')"

# Palabras funcionales (unas 60 por idioma) para medir la calidad del texto.
# Se comparan sin tildes ni mayúsculas, así que se escriben sin acentos.
PALABRAS_COMUNES = {
    "es": set(
        "a al algo algunas algunos ante antes como con contra cual cuando de "
        "del desde donde durante e el ella ellas ellos en entre era erais eran "
        "eras eres es esa esas ese eso esos esta estaba estado estan estar "
        "estas este esto estos fue fueron ha habia han has hasta hay la las le "
        "les lo los mas me mi mis mucho muy nada ni no nos nosotros o os otra "
        "otro para pero poco por porque que quien se sea segun ser si sin sobre "
        "son su sus tambien tan tanto te tenemos tener tu tus un una uno unos y "
        "ya yo".split()),
    "en": set(
        "the of and a to in is you that it he was for on are as with his they i "
        "at be this have from or one had by word but not what all were we when "
        "your can said there use an each which she do how their if will up "
        "other about out many then them these so some her would make like him "
        "into time has look two more write go see number no way could people my "
        "than first water been call who oil its now find long down day did get "
        "come made may part".split()),
    "pt": set(
        "de a o que e do da em um para e com nao uma os no se na por mais as dos "
        "como mas foi ao ele das tem a seu sua ou ser quando muito ha nos ja "
        "esta eu tambem so pelo pela ate isso ela entre era depois sem mesmo aos "
        "ter seus quem nas me esse eles estao voce tinha foram essa num nem "
        "suas meu as minha tem numa pelos elas havia seja qual sera nos tenho "
        "lhe deles essas esses pelas este fosse dele tu te voces vos lhes meus "
        "minhas teu tua teus tuas nosso nossa nossos nossas dela delas".split()),
    "fr": set(
        "de la le et les des en un une du que est pour qui dans a par plus pas "
        "au sur ne se ce il sont avec ou son elle comme mais tout nous vous "
        "leur sa ses cette deux aussi bien ou sans peut etre fait avoir je tu "
        "on y a ete tres si mes ton tes mon ma ta nos vos leurs quel quelle "
        "quand tres lui ils elles nous vous eux".split()),
}


def _idioma_corto(idioma):
    return (idioma or "")[:2].lower()


def _normalizar_palabra(palabra):
    base = unicodedata.normalize("NFKD", palabra.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def _marcas_de_pagina(texto):
    """Marcas de página: avisos de OCR (con su precisión) y líneas «Page N».

    Devuelve [(posición, precisión)] ordenado; la precisión es None cuando la
    marca solo delimita la página y no informa de la calidad.
    """
    marcas = []
    for match in AVISO_RE.finditer(texto):
        try:
            precision = float(match.group(1).replace(",", "."))
        except ValueError:
            precision = None
        marcas.append((match.start(), match.end(), precision))
    for match in re.finditer(r"^[ \t]*Page\s+\d+[ \t]*$", texto,
                             re.IGNORECASE | re.MULTILINE):
        marcas.append((match.start(), match.end(), None))
    marcas.sort()
    return marcas


def _quitar_paginas(texto):
    """Elimina las páginas con OCR por debajo del 60 % de fiabilidad.

    Una página es el bloque entre dos marcas consecutivas (avisos de OCR o
    líneas «Page N»). Si el libro no tiene marcas, se cuentan bloques de unos
    3.000 caracteres, pero no se descarta ninguno. Devuelve
    (texto_restante, paginas_total, paginas_descartadas).
    """
    marcas = _marcas_de_pagina(texto)
    if not marcas:
        if not texto.strip():
            return texto, 0, 0
        total = (len(texto.strip()) + 2999) // 3000
        return texto, max(1, total), 0

    total = len(marcas) + (1 if texto[:marcas[0][0]].strip() else 0)
    rangos = []
    for i, (inicio, fin_marca, precision) in enumerate(marcas):
        if precision is None or precision >= 60:
            continue
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(texto)
        rangos.append((inicio, fin))

    descartadas = len(rangos)
    # Fusiona rangos solapados antes de recortar.
    rangos.sort()
    fusionados = []
    for inicio, fin in rangos:
        if fusionados and inicio <= fusionados[-1][1]:
            fusionados[-1] = (fusionados[-1][0], max(fusionados[-1][1], fin))
        else:
            fusionados.append((inicio, fin))

    partes = []
    cursor = 0
    for inicio, fin in fusionados:
        partes.append(texto[cursor:inicio])
        partes.append("\n\n")
        cursor = fin
    partes.append(texto[cursor:])
    return "".join(partes), total, descartadas


def _quitar_control(texto):
    texto = "".join(c for c in texto
                    if c in "\n\t" or not unicodedata.category(c).startswith("C"))
    return re.sub(r"(?:[~^\\|_]\s*){3,}", " ", texto)


def _linea_ruidosa(linea):
    """True si más del 40 % de los caracteres visibles no son alfanuméricos."""
    visibles = [c for c in linea if not c.isspace()]
    if not visibles:
        return False
    no_alnum = sum(1 for c in visibles if not c.isalnum())
    return no_alnum / len(visibles) > 0.40


def _quitar_cabeceras(lineas):
    """Quita avisos, números de página y líneas cortas muy repetidas."""
    lineas = [AVISO_RE.sub("", linea) for linea in lineas]
    cuenta = {}
    for linea in lineas:
        texto = linea.strip()
        if (not texto or len(texto) > 80 or not any(c.isalpha() for c in texto)
                or NUMERO_PAGINA_RE.match(texto)):
            continue
        cuenta[texto] = cuenta.get(texto, 0) + 1
    repetidas = {texto for texto, n in cuenta.items() if n >= 8}
    salida = []
    quitadas = 0
    for linea in lineas:
        texto = linea.strip()
        if not texto:
            salida.append("")
        elif NUMERO_PAGINA_RE.match(texto) or texto in repetidas:
            quitadas += 1
        elif _linea_ruidosa(texto):
            continue
        else:
            salida.append(linea.rstrip())
    return salida, quitadas


def _diccionario(texto):
    cuenta = {}
    for match in re.finditer(r"[^\W\d_]+(?!-\n)", texto, re.UNICODE):
        palabra = match.group(0).lower()
        if len(palabra) >= 2:
            cuenta[palabra] = cuenta.get(palabra, 0) + 1
    return {palabra for palabra, n in cuenta.items() if n >= 3}


def _desguionar(texto):
    diccionario = _diccionario(texto)
    unidos = [0]

    def unir(match):
        palabra = match.group(1) + match.group(2)
        if palabra.lower() in diccionario:
            unidos[0] += 1
            return palabra
        return match.group(0)

    return re.sub(r"([^\W\d_]+)-\n([^\W\d_]+)", unir, texto), unidos[0]


def _quitar_letras_aisladas(texto):
    # Series de tres o más letras sueltas («r a s g o s»): ruido de OCR.
    return re.sub(r"(?<!\w)(?:[^\W\d_]\s+){2,}[^\W\d_](?!\w)", " ", texto)


def _recortar_portada(lineas):
    limite = min(150, len(lineas))
    ultimo = -1
    for i in range(limite):
        bajo = lineas[i].lower()
        if any(marca in bajo for marca in MARCAS_PORTADA):
            ultimo = i
    if ultimo < 0:
        return lineas
    inicio = ultimo + 1
    while inicio < len(lineas) and not lineas[inicio].strip():
        inicio += 1
    return lineas[inicio:]


def _recortar_indice(lineas):
    """Corta un índice alfabético final de 40 o más líneas cortas con número."""
    i = len(lineas) - 1
    while i >= 0 and not lineas[i].strip():
        i -= 1
    fin = i
    seguidas = 0
    while i >= 0:
        texto = lineas[i].strip()
        if (not texto or len(texto) > 70 or not any(c.isalpha() for c in texto)
                or not re.match(r"^.{0,60}?\d{1,4}$", texto)):
            break
        seguidas += 1
        i -= 1
    if seguidas >= 40:
        return lineas[:i + 1]
    return lineas


def _unir_parrafos(lineas):
    parrafos = []
    actual = ""
    for linea in lineas:
        texto = linea.strip()
        if not texto:
            if actual:
                parrafos.append(actual)
                actual = ""
            continue
        if not actual:
            actual = texto
        elif actual.endswith("-"):
            # Guion no resuelto: se conserva el salto de línea.
            actual += "\n" + texto
        elif actual[-1] not in TERMINALES and texto[0].islower():
            actual += " " + texto
        else:
            parrafos.append(actual)
            actual = texto
    if actual:
        parrafos.append(actual)
    return "\n\n".join(parrafos)


def _ratio_comunes(texto, idioma):
    palabras = [_normalizar_palabra(p)
                for p in re.findall(r"[^\W\d_]+", texto, re.UNICODE)]
    if not palabras:
        return 0.0
    comunes = PALABRAS_COMUNES.get(_idioma_corto(idioma))
    if not comunes:
        comunes = set().union(*PALABRAS_COMUNES.values())
    return sum(1 for p in palabras if p in comunes) / len(palabras)


def limpiar(texto, idioma):
    """Limpia un texto OCR/EPUB y devuelve (texto_limpio, informe)."""
    chars_antes = len(texto)
    texto, paginas_total, paginas_descartadas = _quitar_paginas(texto)
    texto = _quitar_control(texto)
    lineas, lineas_cabecera_quitadas = _quitar_cabeceras(texto.splitlines())
    texto = "\n".join(lineas)
    texto, guiones_unidos = _desguionar(texto)
    texto = _quitar_letras_aisladas(texto)

    lineas = _recortar_portada(texto.splitlines())
    lineas = _recortar_indice(lineas)
    limpio = _unir_parrafos(lineas)
    limpio = re.sub(r"[ \t]+", " ", limpio)
    limpio = re.sub(r" *\n *", "\n", limpio)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio).strip()

    ratio = _ratio_comunes(limpio, idioma)
    informe = {
        "paginas_total": paginas_total,
        "paginas_descartadas": paginas_descartadas,
        "lineas_cabecera_quitadas": lineas_cabecera_quitadas,
        "guiones_unidos": guiones_unidos,
        "ratio_comunes": round(ratio, 4),
        "calidad_baja": ratio < 0.30,
        "chars_antes": chars_antes,
        "chars_despues": len(limpio),
    }
    return limpio, informe
