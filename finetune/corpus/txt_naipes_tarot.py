# -*- coding: utf-8 -*-
"""T132: TXT de naipes y tarot (apuntes OCR del usuario) a afirmaciones.

Tres TXT ya extraídos (OCR de djvu, archive.org) en ``_txt/``:

- ``naipes_secre_altaya_djvu.txt``: «Los naipes y sus secretos» (Altaya).
  Capítulos de figuras (ases, reyes, reinas, jotas, reyes/caballos/sotas,
  numerales) que mezclan barajas latinas y francesas, más 22 arcanos
  mayores (orden Rider-Waite, El Loco al final).
- ``compendium_tarot_mexicanus_djvu.txt``: «Compendium Tarot Mexicanus»
  (2025), cinco ensayos académicos sobre tarot.
- ``relacion_baraja_miguel_ricart_1838_djvu.txt``: romance en verso de
  1838 con OCR muy degradado. Excluido de extracción (ver knowledge md).

Etapas (reanudables, patrón libros_comprados_en/baraja):

1. ``--limpiar``: quita hifenación de fin de línea, números de página y
   running headers por fuente; mide calidad antes/después.
2. ``--segmentar``: secciones por capítulo/arcano con mapeo determinista a
   ids de la KB (tarot 78). Los capítulos mixtos de naipes NO se mapean a
   baraja española de forma determinista: el juez los evalúa por cuerpo.
3. ``--cobertura``: informe carta x faceta y llamadas LLM esperadas
   (determinista, sin LLM).
4. ``--juez`` / ``--afirmaciones``: LLM solo en nodo2 (una etapa a la vez,
   <= 2 workers), reutilizando ``juez.procesar_secciones`` y
   ``afirmaciones_libros.main`` sin modificarlos.
5. ``--auditar``: puerta anti-copia (>25 palabras consecutivas iguales al
   libro) con ``libros_comprados_en.es_copia``.
6. ``--fusionar``: ``afirmaciones/afirmaciones_txt_naipes.jsonl`` con
   procedencia.

Nunca se copia el texto fuente al repositorio: los TXT viven en el work-dir
fuera del repo (``/Users/angelgonzalez/fase0/txt_naipes_tarot``).
"""

import datetime
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import afirmaciones_libros
import cartas
import juez
import libros_comprados_en

TXT_DIR = "/Users/angelgonzalez/adivinacion-ia/_txt"
WORK_DIR = "/Users/angelgonzalez/fase0/txt_naipes_tarot"
NODO2_ENDPOINT = "http://10.0.0.4:8000/v1"
NODO1_RESERVADO = "10.0.0.3"
MAX_CONSECUTIVAS_COPIA = 25
MAX_CHARS_SECCION = 5500
WORKERS_MAX = 2
META_NOMBRE = "fuentes_txt_naipes.jsonl"
AFIRMACIONES_FUSION = "afirmaciones_txt_naipes.jsonl"
PROCEDENCIA = ("apuntes TXT del usuario (OCR de archive.org), "
              "uso interno, derechos por revisar")

FUENTES = [
    {
        "id": "altaya_naipes",
        "archivo": "naipes_secre_altaya_djvu.txt",
        "titulo": "Los naipes y sus secretos",
        "autor": "Anónimo (edición Altaya)",
        "anio": 1985,
        "idioma": "es",
        "incluido": True,
    },
    {
        "id": "compendium_tarot_mexicanus",
        "archivo": "comendium_placeholder",
        "titulo": "Compendium Tarot Mexicanus",
        "autor": "Varios autores",
        "anio": 2025,
        "idioma": "es",
        "incluido": True,
    },
    {
        "id": "ricart_1838",
        "archivo": "relacion_baraja_miguel_ricart_1838_djvu.txt",
        "titulo": "Relacion de la baraja (Miguel Ricart, 1838)",
        "autor": "Miguel Ricart",
        "anio": 1838,
        "idioma": "es",
        "incluido": False,
        "motivo_exclusion": ("OCR no recuperable: densidad de palabras reales "
                            "máxima 0.58 en ventanas de 40 líneas; es un "
                            "romance en verso, no un manual cartomántico"),
    },
]
FUENTES[1]["archivo"] = "compendium_tarot_mexicanus_djvu.txt"

FACETAS_TAROT = [
    "significado_general", "luz_sombra", "derecha_invertida", "amor",
    "trabajo", "dinero", "salud", "espiritual", "simbolismo",
    "correspondencias", "consejo_practico", "ejemplo_de_uso",
]

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def validar_work_dir(work_dir):
    """Rechaza el work-dir de la tuberia de libros comprados y fase0 entero."""
    ruta = os.path.abspath(work_dir)
    prohibidas = ["/Users/angelgonzalez/fase0/libros"]
    if ruta == "/Users/angelgonzalez/fase0":
        raise ValueError("work-dir prohibido: fase0 entero")
    for pref in prohibidas:
        if ruta == pref or ruta.startswith(pref + os.sep):
            raise ValueError("work-dir prohibido: %s" % pref)
    return ruta


def fuente_por_id(fuente_id):
    for f in FUENTES:
        if f["id"] == fuente_id:
            return f
    raise KeyError("fuente desconocida: %s" % fuente_id)


def leer_txt_fuente(fuente, txt_dir=TXT_DIR):
    ruta = os.path.join(txt_dir, fuente["archivo"])
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def norm_letras(texto):
    """Minusculas sin tildes, solo letras [a-z]."""
    base = unicodedata.normalize("NFKD", (texto or "").lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", base)


def norm_linea(texto):
    """Mayusculas sin tildes ni signos: para comparar cabeceras OCR."""
    base = unicodedata.normalize("NFKD", (texto or "").upper())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^A-Z]", "", base)


def cabecera_coincide(linea, objetivo):
    """La linea es la cabecera (con ruido OCR: digitos de pagina pegados)."""
    n = norm_linea(linea).strip("0123456789")
    return n == objetivo


def medir_calidad(texto):
    """Metricas de calidad OCR: proporcion de tokens que son palabras reales."""
    tokens = re.findall(r"\S+", texto or "")
    reales = 0
    for t in tokens:
        limpio = unicodedata.normalize("NFKD", t.lower())
        limpio = "".join(c for c in limpio if not unicodedata.combining(c))
        limpio = re.sub(r"[^a-z]", "", limpio)
        if len(limpio) >= 3:
            reales += 1
    total = len(tokens) or 1
    return {
        "chars": len(texto or ""),
        "lineas": len((texto or "").splitlines()),
        "tokens": len(tokens),
        "palabras_reales": reales,
        "real_word_ratio": round(reales / total, 4),
    }


# ---------------------------------------------------------------------------
# Limpieza
# ---------------------------------------------------------------------------

RE_PAGINA = re.compile(r"^\s*\d+\s*$")
RE_ALTAYA_HEADER = re.compile(
    r"^[|\[\]\s0-9lI]*L[O0]S?\s*NAIPES.*SECRE[T1][O0S]", re.IGNORECASE)
RE_COMPENDIUM_HEADER = re.compile(
    r"^\s*\d*\s*\|?\s*COMPENDIUM\s+TAROT\s+MEXICANUS\s*$", re.IGNORECASE)

COMPENDIUM_CABECERAS = {
    "LAMIRADADEFRIEDAHARRIS",
    "TIRADASSAGRADAS",
    "LAIMAGENEDELTETRAMORFOSYELMERKABA",
    "ELTAROTENNUESTROSDIAS",
    "CARTOMANCIANASYCARTOMANTES",
    "ALEJANDRAMAYTEIBANEZ",
    "JIMENAAULLET",
    "NAHUMMARTINEZORTIZ",
    "VERONICAHERNANDEZZAMORA",
    "LUISANGELHERNANDEZCUEVAS",
}


def es_linea_basura(linea, fuente_id):
    if RE_PAGINA.match(linea):
        return True
    desnuda = linea.strip()
    if not desnuda:
        return False
    if fuente_id == "altaya_naipes":
        if RE_ALTAYA_HEADER.match(desnuda):
            return True
        n = norm_linea(desnuda)
        if n in ("NAIPES", "LOSNAIPES", "YSUSSECRETOS"):
            return True
        if "NAIPES" in n and "SECRE" in n and len(desnuda) <= 45:
            return True
    elif fuente_id == "compendium_tarot_mexicanus":
        if RE_COMPENDIUM_HEADER.match(desnuda):
            return True
        if norm_linea(desnuda) in COMPENDIUM_CABECERAS:
            return True
    return False


def unir_hifenacion(lineas):
    """Une «pal-\\nabra» cuando la siguiente linea empieza en minuscula."""
    out = []
    i = 0
    n = len(lineas)
    while i < n:
        linea = lineas[i]
        if (linea.rstrip().endswith("-") and i + 1 < n):
            siguiente = lineas[i + 1].lstrip()
            if siguiente and siguiente[0].islower():
                out.append(linea.rstrip()[:-1] + siguiente)
                i += 2
                continue
        out.append(linea)
        i += 1
    return out


def limpiar(texto, fuente_id):
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lineas = unir_hifenacion(lineas)
    limpias = []
    for linea in lineas:
        if es_linea_basura(linea, fuente_id):
            continue
        limpias.append(linea.rstrip())
    return "\n".join(limpias)


def etapa_limpieza(fuente_id, work_dir):
    fuente = fuente_por_id(fuente_id)
    crudo = leer_txt_fuente(fuente)
    limpio = limpiar(crudo, fuente_id)
    ruta_limpio = os.path.join(work_dir, "limpio", fuente_id + ".txt")
    with open(ruta_limpio, "w", encoding="utf-8") as fh:
        fh.write(limpio)
    informe = {
        "fuente_id": fuente_id,
        "antes": medir_calidad(crudo),
        "despues": medir_calidad(limpio),
    }
    ruta_inf = os.path.join(work_dir, "limpio", fuente_id + "_calidad.json")
    with open(ruta_inf, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)
    return informe


# ---------------------------------------------------------------------------
# Segmentacion: Altaya
# ---------------------------------------------------------------------------

# (clave, titulo, objetivo_de_cabecera, tipo)
#   tipo: 'frase' (arranca por frase), 'simple', 'partida' (2 lineas)
ALTAYA_CAPITULOS = [
    ("los_ases", "Los ases", None, "frase"),
    ("los_reyes", "Los reyes de la baraja",
     ("LOSREYES", "DELABARAJA"), "partida"),
    ("reinas_damas", "Reinas y damas", ("REINASYDAMAS", None), "simple"),
    ("jotas_valets", "Jotas, valets y bubes",
     ("JOTASVALETS", "YBUBES"), "partida"),
    ("reyes_caballos_sotas", "Reyes, caballos y sotas",
     ("REYESCABALLOS", "YSOTAS"), "partida"),
    ("cartas_numerales", "Las cartas numerales",
     ("LASCARTAS", "NUMERALES"), "partida"),
    ("intro_arcanos", "Introducción a los arcanos mayores",
     ("OSARCANOS", "MAYORES"), "partida"),
]

# (nombre_canonico_tarot, objetivo_cabecera) — orden del libro (Loco al final)
ALTAYA_ARCANOS = [
    ("El Mago", "ELMAGO"),
    ("La Sacerdotisa", "LAPAPISA"),
    ("La Emperatriz", "LAEMPERATRIZ"),
    ("El Emperador", "ELEMPERADOR"),
    ("El Papa", "ELPAPA"),
    ("Los Enamorados", "LOSENAMORADOS"),
    ("El Carro", "ELCARRO"),
    ("La Justicia", "LAJUSTICIA"),
    ("El Ermitaño", "ELERMITANO"),
    ("La Rueda de la Fortuna", "LARUEDA"),
    ("La Fuerza", "LAFUERZA"),
    ("El Colgado", "ELCOLGADO"),
    ("La Muerte", "LAMUERTE"),
    ("La Templanza", "LATEMPLANZA"),
    ("El Diablo", "ELDIABLO"),
    ("La Torre", "LATORRE"),
    ("La Estrella", "LAESTRELLA"),
    ("La Luna", "LALUNA"),
    ("El Sol", "ELSOL"),
    ("El Juicio", "ELJUICIO"),
    ("El Mundo", "ELMUNDO"),
    ("El Loco", "ELLOCO"),
]


RE_ASES_INICIO = re.compile(r"^\s*Al estudiar los ases", re.IGNORECASE)


def _buscar_indice(lineas_norm, objetivo, cursor, partida=False):
    """Primera ocurrencia de la cabecera (o par de lineas) desde cursor."""
    n = len(lineas_norm)
    if partida:
        prim, seg = objetivo
        for i in range(cursor, n - 1):
            if lineas_norm[i] == prim and lineas_norm[i + 1] == seg:
                return i
        return -1
    for i in range(cursor, n):
        if lineas_norm[i] == objetivo:
            return i
    return -1


def _trocear_por_parrafos(texto, max_chars=MAX_CHARS_SECCION):
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    partes = []
    actual = []
    largo = 0
    for p in parrafos:
        anadido = len(p) + (2 if actual else 0)
        if actual and largo + anadido > max_chars:
            partes.append("\n\n".join(actual))
            actual = [p]
            largo = len(p)
        else:
            if len(p) > max_chars:
                if actual:
                    partes.append("\n\n".join(actual))
                    actual = []
                    largo = 0
                for j in range(0, len(p), max_chars):
                    partes.append(p[j:j + max_chars])
            else:
                actual.append(p)
                largo += anadido
    if actual:
        partes.append("\n\n".join(actual))
    return [p for p in partes if p.strip()]


def _seccion(fuente_id, clave, titulo, texto, posicion, entidad_id,
             motivo_sin_entidad, sistema, metodo, confianza, pagina=None):
    return {
        "id_libro": fuente_id,
        "fuente_id": fuente_id,
        "seccion": "%s:%s" % (fuente_id, clave),
        "titulo": titulo,
        "texto": texto,
        "chars": len(texto),
        "posicion": posicion,
        "entidad_id": entidad_id,
        "motivo_sin_entidad": motivo_sin_entidad,
        "sistema": sistema,
        "idioma": "es",
        "metodo": metodo,
        "confianza": confianza,
        "pagina": pagina,
    }


def _emitir_partes(fuente_id, clave_base, titulo_base, texto, posicion,
                  entidad_id, motivo_sin_entidad, sistema, metodo, confianza):
    partes = _trocear_por_parrafos(texto)
    secciones = []
    for idx, parte in enumerate(partes, start=1):
        sufijo = "" if len(partes) == 1 else " (parte %d)" % idx
        secciones.append(_seccion(
            fuente_id, "%s:%d" % (clave_base, idx), titulo_base + sufijo,
            parte, posicion, entidad_id, motivo_sin_entidad, sistema,
            metodo, confianza))
    return secciones


def segmentar_altaya(texto_limpio):
    lineas = texto_limpio.split("\n")
    lineas_norm = [norm_linea(l) for l in lineas]
    secciones = []

    # Inicio de «Los ases» por frase caracteristica.
    ases_idx = -1
    for i, l in enumerate(lineas):
        if RE_ASES_INICIO.match(l):
            ases_idx = i
            break
    if ases_idx < 0:
        raise ValueError("Altaya: no se encontro el inicio de Los ases")

    # Introducción: primera línea de cuerpo (>=25 chars) tras el índice.
    intro_inicio = 0
    for i in range(0, ases_idx):
        if len(lineas[i].strip()) >= 25:
            intro_inicio = i
            break
    intro_texto = "\n".join(lineas[intro_inicio:ases_idx]).strip()
    if intro_texto:
        secciones.extend(_emitir_partes(
            "altaya_naipes", "introduccion", "Introducción", intro_texto,
            intro_inicio, None, "capitulo_general_no_carta", "mixto",
            "posicion", "media"))

    # Cabeceras de capitulos no-arcano, en orden.
    limites = []  # (indice_cabecera, fin) para cada capitulo no-arcano
    cursor = ases_idx
    for clave, titulo, objetivo, tipo in ALTAYA_CAPITULOS:
        if tipo == "frase":
            inicio = ases_idx
            cuerpo_desde = ases_idx
        elif tipo == "simple":
            inicio = _buscar_indice(lineas_norm, objetivo[0], cursor)
            cuerpo_desde = inicio + 1
        else:
            inicio = _buscar_indice(lineas_norm, objetivo, cursor, partida=True)
            cuerpo_desde = inicio + 2
        if inicio < 0:
            raise ValueError("Altaya: no se encontro cabecera %s" % clave)
        limites.append((clave, titulo, inicio, cuerpo_desde))
        cursor = inicio + 1

    # Primera cabecera de arcano tras la intro de arcanos.
    cursor_arcanos = limites[-1][3]
    arcano_indices = []
    for nombre, objetivo in ALTAYA_ARCANOS:
        idx = _buscar_indice(lineas_norm, objetivo, cursor_arcanos)
        if idx < 0:
            raise ValueError("Altaya: no se encontro cabecera de %s" % nombre)
        arcano_indices.append(idx)
        cursor_arcanos = idx + 1

    # Cuerpos de capitulos no-arcano: hasta la siguiente cabecera.
    for j, (clave, titulo, inicio, cuerpo_desde) in enumerate(limites):
        fin = limites[j + 1][2] if j + 1 < len(limites) else arcano_indices[0]
        cuerpo = "\n".join(lineas[cuerpo_desde:fin]).strip()
        if not cuerpo:
            continue
        secciones.extend(_emitir_partes(
            "altaya_naipes", clave, titulo, cuerpo, inicio,
            None, "capitulo_mixto_no_carta", "mixto", "cabecera", "media"))

    # Capitulo de introduccion a los arcanos: ya incluido como ultimo no-arcano
    # (su cuerpo termina en el primer arcano). Los arcanos:
    for j, (nombre, objetivo) in enumerate(ALTAYA_ARCANOS):
        inicio = arcano_indices[j]
        fin = (arcano_indices[j + 1] if j + 1 < len(arcano_indices)
              else len(lineas))
        cuerpo = "\n".join(lineas[inicio + 1:fin]).strip()
        if not cuerpo:
            continue
        info = cartas.normalizar_carta(nombre, mazo="tarot")
        entidad_id = info["id"] if info else None
        if not entidad_id:
            raise ValueError("Altaya: sin id KB para %s" % nombre)
        secciones.extend(_emitir_partes(
            "altaya_naipes", "arcano:" + objetivo.lower(), nombre, cuerpo,
            inicio, entidad_id, None, "tarot", "cabecera", "alta"))
    return secciones


# ---------------------------------------------------------------------------
# Segmentacion: Compendium Tarot Mexicanus
# ---------------------------------------------------------------------------

COMPENDIUM_TITULOS = {
    "I": "La mirada de Frieda Harris",
    "II": "Tiradas Sagradas",
    "III": "Tetramorfos y Merkaba",
    "IV": "El tarot en nuestros días 2020-2024",
    "V": "Cartomancianas y Cartomantes",
}

RE_CAPITULO = re.compile(
    r"^\s*(?:CAP[IÍ]TULO|Cap[ií]tulo|CAPITULO)\s+"
    r"(I{1,3}|IV|V|VI|[1-6])\b")

ROMANIZAR = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}

COMPENDIUM_DESCARTES = {
    "BIBLIOGRAFIA", "REFERENCIAS", "REFERENCIASBIBLIOGRAFICAS",
    "OBRASCONSULTADAS", "AGRADECIMIENTOS", "NOTABIOGRAFICA",
    "NOTASBIOGRAFICAS", "INDICE",
}


def segmentar_compendium(texto_limpio):
    lineas = texto_limpio.split("\n")
    inicios = []
    for i, l in enumerate(lineas):
        if i < 400:  # el indice (TOC) no es capitulo
            continue
        m = RE_CAPITULO.match(l)
        if m:
            numeral = ROMANIZAR.get(m.group(1), m.group(1).upper())
            inicios.append((i, numeral))
    if not inicios:
        raise ValueError("Compendium: no se encontro ninguna cabecera de capitulo")
    secciones = []
    for j, (inicio, numeral) in enumerate(inicios):
        fin = inicios[j + 1][0] if j + 1 < len(inicios) else len(lineas)
        titulo = COMPENDIUM_TITULOS.get(numeral, "Capítulo %s" % numeral)
        cuerpo_lineas = lineas[inicio:fin]
        # descartar bloques finales de bibliografia/agradecimientos
        corte = len(cuerpo_lineas)
        for k, l in enumerate(cuerpo_lineas):
            if norm_linea(l) in COMPENDIUM_DESCARTES:
                corte = k
                break
        cuerpo = "\n".join(cuerpo_lineas[:corte]).strip()
        if not cuerpo:
            continue
        partes = _trocear_por_parrafos(cuerpo)
        for idx, parte in enumerate(partes, start=1):
            sufijo = "" if len(partes) == 1 else " (parte %d)" % idx
            secciones.append(_seccion(
                "compendium_tarot_mexicanus",
                "cap%s:%d" % (numeral.lower(), idx),
                "Capítulo %s: %s%s" % (numeral, titulo, sufijo),
                parte, inicio + 1, None, "ensayo_sin_carta_determinista",
                "tarot", "chunk_parrafos", "media"))
    return secciones


# ---------------------------------------------------------------------------
# Preparacion y escritura de secciones
# ---------------------------------------------------------------------------

SUBDIRS = ["crudo", "limpio", "secciones", "evidencias", "knowledge",
           "afirmaciones", "resumenes"]


def preparar(work_dir):
    work_dir = validar_work_dir(work_dir)
    for d in SUBDIRS:
        os.makedirs(os.path.join(work_dir, d), exist_ok=True)
    for fuente in FUENTES:
        src = os.path.join(TXT_DIR, fuente["archivo"])
        dst = os.path.join(work_dir, "crudo", fuente["archivo"])
        if os.path.isfile(src) and not os.path.exists(dst):
            with open(src, encoding="utf-8", errors="replace") as fh:
                contenido = fh.read()
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(contenido)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        for fuente in FUENTES:
            registro = {
                "id": fuente["id"],
                "anio": fuente["anio"],
                "idioma": fuente["idioma"],
                "titulo": fuente["titulo"],
                "autor": fuente["autor"],
                "origen": "apuntes TXT del usuario (OCR de archive.org)",
                "licencia_hint": "derechos por revisar",
                "procedencia": PROCEDENCIA,
                "incluido": fuente["incluido"],
            }
            if fuente.get("motivo_exclusion"):
                registro["motivo_exclusion"] = fuente["motivo_exclusion"]
            fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return work_dir


def fuentes_incluidas(fuente=None):
    if fuente:
        f = fuente_por_id(fuente)
        if not f["incluido"]:
            raise ValueError("fuente excluida: %s (%s)"
                            % (fuente, f.get("motivo_exclusion", "")))
        return [f]
    return [f for f in FUENTES if f["incluido"]]


def segmentar_fuente(fuente_id, work_dir):
    ruta_limpio = os.path.join(work_dir, "limpio", fuente_id + ".txt")
    with open(ruta_limpio, encoding="utf-8") as fh:
        texto = fh.read()
    if fuente_id == "altaya_naipes":
        secciones = segmentar_altaya(texto)
    elif fuente_id == "compendium_tarot_mexicanus":
        secciones = segmentar_compendium(texto)
    else:
        raise ValueError("sin segmentador para %s" % fuente_id)
    ruta_out = os.path.join(work_dir, "secciones", fuente_id + ".jsonl")
    with open(ruta_out, "w", encoding="utf-8") as fh:
        for s in secciones:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    return secciones


def leer_secciones(work_dir, fuente=None):
    secciones = []
    for f in fuentes_incluidas(fuente):
        ruta = os.path.join(work_dir, "secciones", f["id"] + ".jsonl")
        if os.path.isfile(ruta):
            secciones.extend(juez.leer_secciones(ruta))
    return secciones


# ---------------------------------------------------------------------------
# Cobertura (determinista, sin LLM)
# ---------------------------------------------------------------------------


def informe_cobertura(work_dir, fuente=None):
    secciones = leer_secciones(work_dir, fuente)
    informes = {}
    for f in fuentes_incluidas(fuente):
        informes[f["id"]] = {
            "secciones": 0, "con_entidad": 0, "con_candidatos": 0,
            "est_juez": 0, "est_afirmaciones_max": 0,
            "cartas": {},
        }
    for s in secciones:
        inf = informes[s["fuente_id"]]
        inf["secciones"] += 1
        if s.get("entidad_id"):
            inf["con_entidad"] += 1
            inf["cartas"].setdefault(s["entidad_id"], set())
            for faceta in FACETAS_TAROT:
                inf["cartas"][s["entidad_id"]].add(faceta)
            inf["est_afirmaciones_max"] += len(FACETAS_TAROT)
        candidatos = juez.candidatos_seccion(s)
        if candidatos:
            inf["con_candidatos"] += 1
            inf["est_juez"] += 1
            for c in candidatos:
                if not s.get("entidad_id"):
                    inf["cartas"].setdefault(c["entidad_id"], set())
    for inf in informes.values():
        inf["cartas"] = {k: sorted(v) for k, v in inf["cartas"].items()}
    return informes


# ---------------------------------------------------------------------------
# Etapas LLM (nodo2, reanudables)
# ---------------------------------------------------------------------------


def construir_cliente(endpoints, timeout=90.0):
    return libros_comprados_en.construir_cliente_endpoints(endpoints, timeout)


def etapa_juez(fuente_id, work_dir, cliente, workers=1, limite=0):
    if workers > WORKERS_MAX:
        raise ValueError("workers maximo %d en nodo2" % WORKERS_MAX)
    secciones = leer_secciones(work_dir, fuente_id)
    libros_comprados_en.purgar_errores_juez(work_dir)
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if limite and limite > 0:
        hechos = libros_comprados_en._hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                     if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:limite]
    stats = juez.procesar_secciones(
        a_procesar, cliente, os.path.join(work_dir, "evidencias"),
        meta=meta, workers=workers)
    return stats


def etapa_afirmaciones(work_dir, cliente, workers=1, limite=0):
    if workers > WORKERS_MAX:
        raise ValueError("workers maximo %d en nodo2" % WORKERS_MAX)
    argv = ["--evidencias",
           os.path.join(work_dir, "evidencias", "evidencias.jsonl"),
           "--secciones-dir", os.path.join(work_dir, "secciones"),
           "--out-dir", os.path.join(work_dir, "afirmaciones"),
           "--workers", str(workers)]
    if limite and limite > 0:
        argv += ["--limite", str(limite)]
    base = getattr(cliente, "_cliente", cliente)
    return afirmaciones_libros.main(argv, cliente=base)


def auditar_copias(work_dir):
    """Puerta anti-copia: >25 palabras consecutivas iguales al libro limpio."""
    ruta_af = os.path.join(work_dir, "afirmaciones",
                          "afirmaciones_libros.jsonl")
    if not os.path.exists(ruta_af):
        return 0, 0
    textos = {}
    for f in fuentes_incluidas():
        ruta_limp = os.path.join(work_dir, "limpio", f["id"] + ".txt")
        if os.path.isfile(ruta_limp):
            with open(ruta_limp, encoding="utf-8", errors="replace") as fh:
                textos[f["id"]] = fh.read()
    aceptadas = []
    rechazadas = []
    with open(ruta_af, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            referencia = textos.get(reg.get("fuente_id"), "")
            copia_en = None
            for campo in ("afirmacion", "cita_original"):
                if libros_comprados_en.es_copia(
                        reg.get(campo, ""), referencia,
                        max_run=MAX_CONSECUTIVAS_COPIA):
                    copia_en = campo
                    break
            if copia_en:
                reg["motivo_rechazo"] = "copia>%d (%s)" % (
                    MAX_CONSECUTIVAS_COPIA, copia_en)
                rechazadas.append(reg)
            else:
                aceptadas.append(reg)
    if rechazadas:
        tmp = ruta_af + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for reg in aceptadas:
                fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
        os.replace(tmp, ruta_af)
        ruta_rech = os.path.join(work_dir, "afirmaciones",
                                "rechazadas_copia.jsonl")
        with open(ruta_rech, "w", encoding="utf-8") as fh:
            for reg in rechazadas:
                fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return len(aceptadas), len(rechazadas)


def fusionar(work_dir):
    """Afirmaciones auditadas -> afirmaciones_txt_naipes.jsonl con procedencia."""
    ruta_af = os.path.join(work_dir, "afirmaciones",
                          "afirmaciones_libros.jsonl")
    if not os.path.exists(ruta_af):
        return 0
    ruta_out = os.path.join(work_dir, "afirmaciones", AFIRMACIONES_FUSION)
    total = 0
    with open(ruta_af, encoding="utf-8") as fh, \
            open(ruta_out, "w", encoding="utf-8") as out:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if reg.get("motivo_rechazo"):
                continue
            reg["procedencia"] = PROCEDENCIA
            out.write(json.dumps(reg, ensure_ascii=False) + "\n")
            total += 1
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="T132 TXT naipes y tarot")
    parser.add_argument("--work-dir", default=WORK_DIR)
    parser.add_argument("--fuente", default=None)
    parser.add_argument("--preparar", action="store_true")
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--segmentar", action="store_true")
    parser.add_argument("--cobertura", action="store_true")
    parser.add_argument("--juez", action="store_true")
    parser.add_argument("--afirmaciones", action="store_true")
    parser.add_argument("--auditar", action="store_true")
    parser.add_argument("--fusionar", action="store_true")
    parser.add_argument("--endpoints", default=libros_comprados_en.ENDPOINTS_POR_DEFECTO)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--simulado", action="store_true")
    args = parser.parse_args(argv)

    work_dir = validar_work_dir(args.work_dir)
    if args.workers > WORKERS_MAX:
        parser.error("workers maximo %d" % WORKERS_MAX)

    if args.preparar:
        preparar(work_dir)
        print("preparado: %s" % work_dir)
    if args.limpiar:
        for f in fuentes_incluidas(args.fuente):
            inf = etapa_limpieza(f["id"], work_dir)
            print("%s: ratio antes %.3f -> despues %.3f (%d lineas)" % (
                f["id"], inf["antes"]["real_word_ratio"],
                inf["despues"]["real_word_ratio"],
                inf["despues"]["lineas"]))
    if args.segmentar:
        for f in fuentes_incluidas(args.fuente):
            secs = segmentar_fuente(f["id"], work_dir)
            con_ent = sum(1 for s in secs if s.get("entidad_id"))
            print("%s: %d secciones (%d con entidad)" % (
                f["id"], len(secs), con_ent))
    if args.cobertura:
        informes = informe_cobertura(work_dir, args.fuente)
        for fid, inf in informes.items():
            print("%s: %d secciones | %d con entidad | %d con candidatos | "
                  "est_juez=%d | est_afirmaciones_max=%d | cartas=%d" % (
                      fid, inf["secciones"], inf["con_entidad"],
                      inf["con_candidatos"], inf["est_juez"],
                      inf["est_afirmaciones_max"], len(inf["cartas"])))
        ruta_inf = os.path.join(work_dir, "resumenes", "cobertura.json")
        with open(ruta_inf, "w", encoding="utf-8") as fh:
            json.dump(informes, fh, ensure_ascii=False, indent=2,
                      default=list)
        print("informe: %s" % ruta_inf)
    if args.juez:
        cliente = None
        if not args.simulado:
            cliente = construir_cliente(args.endpoints, args.timeout)
        for f in fuentes_incluidas(args.fuente):
            stats = etapa_juez(f["id"], work_dir, cliente,
                              workers=args.workers, limite=args.limite)
            print("%s juez: %s" % (f["id"], json.dumps(stats)))
    if args.afirmaciones:
        cliente = None
        if not args.simulado:
            cliente = construir_cliente(args.endpoints, args.timeout)
        res = etapa_afirmaciones(work_dir, cliente, workers=args.workers,
                                limite=args.limite)
        print("afirmaciones: %s" % json.dumps(res, default=str))
    if args.auditar:
        ok, rech = auditar_copias(work_dir)
        print("auditoria copia: %d aceptadas, %d rechazadas" % (ok, rech))
    if args.fusionar:
        n = fusionar(work_dir)
        print("fusionado: %d afirmaciones en %s" % (n, AFIRMACIONES_FUSION))
    return 0


if __name__ == "__main__":
    sys.exit(main())
