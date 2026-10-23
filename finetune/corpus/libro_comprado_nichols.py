"""Procesado del libro comprado Nichols, «Jung y el Tarot» (1988), hacia evidencias.

T114. Libro comprado por el usuario (copyright, uso interno): solo arcanos
mayores, enfoque junguiano. El PDF nunca se copia al repo; se trabaja sobre el
texto extraido con ``pdftotext -layout`` en un work-dir NUEVO, apartado de la
tuberia real (``/Users/angelgonzalez/fase0/libros``).

El OCR de esta edicion llega muy defectuoso (vocales acentuadas sustituidas por
``ä/ö/ü/£``, guion silabico ``¬`` a fin de linea, ``^`` ambiguo, cabeceras de
pagina repetidas y numeros de pagina sueltos). La limpieza aplica una tabla
SEGURA de sustituciones y deja a proposito los tokens ambiguos sin «corregir» a
ciegas: se listan como dudosos en el informe.

La segmentacion va por arcano mayor (capitulos numerados en mayusculas, p. ej.
``13. LA RUEDA DE LA FORTUNA:``), mapeando por NOMBRE de carta a los ids de la
KB (el orden del libro no coincide con el del tarot: cap. 11 = Justicia =
tarot-mayor-12). Las cabeceras de pagina en title-case (``La Rueda de la
Fortuna: jSocorro!``) se detectan por repeticion y se eliminan para que no se
confundan con contenido ni con titulos de otra carta.

El juez y las evidencias reutilizan ``juez``/``libros_pipeline`` igual que
``clasicos_pd_a_evidencias.py``, con el LLM fijado a nodo2 (nodo1 reservado) y
reanudable. Las afirmaciones reutilizan ``afirmaciones_libros`` y anaden una
puerta anti-copia: una afirmacion que repita mas de 25 palabras consecutivas del
libro se marca y se rechaza (debe ser parafasis breve, no cita literal larga).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata

import afirmaciones_libros
import juez
import libros_pipeline
import libros_segmentar
import llm_client
from urllib.parse import urlparse

ID_LIBRO = "nichols_jung_tarot_1988"
TITULO_LIBRO = "Jung y el Tarot"
AUTOR_LIBRO = "Sallie Nichols"
ANIO_LIBRO = 1988
IDIOMA_LIBRO = "es"

WORK_DIR_REAL = "/Users/angelgonzalez/fase0/libros"
WORK_DIR_NICHOLS = "/Users/angelgonzalez/fase0/libros_comprados_nichols"
PDF_FUENTE = ("/Users/angelgonzalez/fase0/libros_comprados/"
              "Nichols - Jung y el Tarot (1988).pdf")
META_NOMBRE = "fuentes_libros_comprados.jsonl"

NODO2_ENDPOINT = "http://10.0.0.4:8000/v1"
NODO1_RESERVADO = "10.0.0.3"
# Hosts locales permitidos para el LLM: nodo1 y nodo2 (autorizado por el usuario el 23/10).
HOSTS_LOCALES_PERMITIDOS = ("10.0.0.3", "10.0.0.4")
ENDPOINTS_POR_DEFECTO = "http://10.0.0.3:8000/v1,http://10.0.0.4:8000/v1"
TIMEOUT_NICHOLS = 120.0
MAX_WORKERS = 2

MAX_CONSECUTIVAS_COPIA = 25
MAX_SECCION = 12000

# Cartas: token normalizado (sin espacios ni tildes, en mayusculas) -> (nombre
# canonico para el titulo de seccion, entidad_id de la KB). El orden del libro no
# es el del tarot; se mapea por nombre de carta.
CARTAS = (
    ("LOCO", "El Loco", "tarot-mayor-01"),
    ("MAGO", "El Mago", "tarot-mayor-02"),
    ("PAPISA", "La Papisa", "tarot-mayor-03"),
    ("EMPERATRIZ", "La Emperatriz", "tarot-mayor-04"),
    ("EMPERADOR", "El Emperador", "tarot-mayor-05"),
    ("PAPA", "El Papa", "tarot-mayor-06"),
    ("ENAMORADO", "El Enamorado", "tarot-mayor-07"),
    ("CARRO", "El Carro", "tarot-mayor-08"),
    ("FUERZA", "La Fuerza", "tarot-mayor-09"),
    ("ERMITANO", "El Ermitano", "tarot-mayor-10"),
    ("RUEDA", "La Rueda de la Fortuna", "tarot-mayor-11"),
    ("JUSTICIA", "La Justicia", "tarot-mayor-12"),
    ("COLGADO", "El Colgado", "tarot-mayor-13"),
    ("MUERTE", "La Muerte", "tarot-mayor-14"),
    ("TEMPLANZA", "La Templanza", "tarot-mayor-15"),
    ("DIABLO", "El Diablo", "tarot-mayor-16"),
    ("TORRE", "La Torre", "tarot-mayor-17"),
    ("ESTRELLA", "La Estrella", "tarot-mayor-18"),
    ("LUNA", "La Luna", "tarot-mayor-19"),
    ("SOL", "El Sol", "tarot-mayor-20"),
    ("JUICIO", "El Juicio", "tarot-mayor-21"),
    ("MUNDO", "El Mundo", "tarot-mayor-22"),
)
# Tokens ordenados por longitud descendente: PAPISA debe probarse antes que PAPA.
TOKENS_ORDENADOS = tuple(sorted(CARTAS, key=lambda c: -len(c[0])))

# Tabla segura de sustitucion de caracteres OCR (siempre validos en este libro).
SUSTITUCIONES_CAR = (("ä", "á"), ("ö", "ó"), ("ü", "ú"), ("£", "é"))

# Tokens OCR inequivocos (se reemplazan tal cual, en este orden).
SUSTITUCIONES_TOKEN = (
    ("6sta", "ésta"),
    ("6stas", "éstas"),
    ("tambi^n", "también"),
    ("Tambi^n", "También"),
    ("Ile-", "lle-"),
    ("mateniendo", "manteniendo"),
    ("t^cnica", "técnica"),
    ("t^cnicas", "técnicas"),
    ("t^rmino", "término"),
    ("t^rminos", "términos"),
    ("despues^", "después"),
    ("Despu^s", "Después"),
    ("franc^s", "francés"),
)

_RE_CRUDO = re.compile(r"\x0c")
_RE_GUION_LINEA = re.compile(r"[ \t]*¬[ \t]*\n?[ \t]*")
_RE_PAGINA_SUELTA = re.compile(r"(?m)^[ \t]*\d{1,3}[ \t]*$")
_RE_ENCABEZADO = re.compile(r"^\s*(\d{1,2})\.\s+(\S.*)$")
_RE_CABECERA_HEAD = re.compile(r"^(El|La|Los|Las)\s+\S.*?:\s*\S")
_RE_TOKEN_AMBIGUO = re.compile(r"\S*\^\S*")
# «^» a inicio de palabra (no precedida de letra/digito, seguida de letra) es el
# signo de apertura de interrogacion «¿» mal reconocido por el OCR. Alto confianza:
# todos los casos observados son interrogativas. No toca la «^» intra-palabra.
_RE_INICIO_INTERROGACION = re.compile(
    r"(?<![0-9A-Za-z\u00C0-\u00FF])\^(?=[A-Za-z\u00C0-\u00FF])"
)


def sin_tildes(texto):
    """Minusculas sin marcas diacriticas (para comparar tokens de carta)."""
    descomp = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in descomp if not unicodedata.combining(ch))


def normalizar_token(texto):
    """Solo letras en mayusculas sin tildes ni espacios: base para el token."""
    limpio = re.sub(r"[^A-Za-zÀ-ÿ]", "", texto)
    return sin_tildes(limpio).upper()


def medir_defectos(texto):
    """Cuenta los defectos OCR presentes en un texto (para el informe)."""
    conteo = {
        "chars": len(texto),
        "a_diaeresis": texto.count("ä"),
        "o_diaeresis": texto.count("ö"),
        "u_diaeresis": texto.count("ü"),
        "libra": texto.count("£"),
        "circunflejo": texto.count("^"),
        "guion_silabico": texto.count("¬"),
        "6sta": texto.count("6sta"),
        "tambi^n": texto.count("tambi^n"),
    }
    return conteo


def _aplicar_tabla(texto):
    for viejo, nuevo in SUSTITUCIONES_CAR:
        texto = texto.replace(viejo, nuevo)
    for viejo, nuevo in SUSTITUCIONES_TOKEN:
        texto = texto.replace(viejo, nuevo)
    return texto


def _es_mayusculado(resto):
    """El resto del encabezado va en mayusculas (>=80% de sus letras)."""
    letras = [ch for ch in resto if ch.isalpha()]
    if len(letras) < 4:
        return False
    mayus = sum(1 for ch in letras if ch.isupper())
    return mayus / len(letras) >= 0.8


def _encabezados_numericos(lineas):
    """Encabezados numerados en mayusculas (arcanos y no arcanos).

    Devuelve dicts {linea, numero, token, titulo, entidad_id}; token/titulo/
    entidad_id son None si la linea no corresponde a una carta. Sirven como
    limites de corte: el cuerpo de un arcano termina en el siguiente encabezado
    numerado, sea o no de arcano (asi el cap. 25 «Sobre como echar» acota al
    Mundo y no se lo traga).
    """
    hallados = []
    for idx, linea in enumerate(lineas):
        m = _RE_ENCABEZADO.match(linea)
        if not m:
            continue
        resto = m.group(2)
        if not _es_mayusculado(resto):
            continue
        norm = normalizar_token(resto)
        token = titulo = entidad = None
        for tok, nom, eid in TOKENS_ORDENADOS:
            if tok in norm:
                token, titulo, entidad = tok, nom, eid
                break
        hallados.append({
            "linea": idx,
            "numero": int(m.group(1)),
            "token": token,
            "titulo": titulo,
            "entidad_id": entidad,
        })
    return hallados


def detectar_encabezados(lineas):
    """Encabezados de capitulo de arcano: numerados, en mayusculas, con token.

    Solo los que mapean a una carta. No confunde las cabeceras de pagina
    (title-case) ni las menciones sueltas de carta en el cuerpo.
    """
    return [h for h in _encabezados_numericos(lineas) if h["token"]]


def _candidatas_cabecera(lineas):
    """Lineas title-case «El/La ...:» que contienen una carta: cabeceras de pag.

    Se cuentan por forma normalizada; solo las repetidas (>= MIN_REPETICIONES)
    son cabeceras de pagina y se eliminan. Una frase del cuerpo que coincida una
    sola vez no se toca.
    """
    MIN_REPETICIONES = 3
    candidatos = {}
    for idx, linea in enumerate(lineas):
        recortada = linea.strip()
        if len(recortada) >= 60:
            continue
        if not _RE_CABECERA_HEAD.match(recortada):
            continue
        if re.match(r"^\s*\d", recortada):
            continue
        norm = sin_tildes(recortada.lower())
        if not any(tok.lower() in norm for tok, _, _ in CARTAS):
            continue
        candidatos.setdefault(norm, []).append(idx)
    return {norm: idxs for norm, idxs in candidatos.items()
            if len(idxs) >= MIN_REPETICIONES}


def limpiar_ocr(texto):
    """Limpieza OCR segura del crudo de Nichols.

    Devuelve ``(texto_limpio, informe)``. No «corrige» a ciegas los tokens
    ambiguos: los cuenta en ``informe['dudosos']`` para revision.
    """
    antes = medir_defectos(texto)
    texto = _RE_CRUDO.sub("", texto)
    unidos = len(_RE_GUION_LINEA.findall(texto))
    texto = _RE_GUION_LINEA.sub("", texto)
    texto = _aplicar_tabla(texto)
    interrogaciones = len(_RE_INICIO_INTERROGACION.findall(texto))
    texto = _RE_INICIO_INTERROGACION.sub("¿", texto)
    lineas = texto.split("\n")
    paginas = sum(1 for l in lineas if _RE_PAGINA_SUELTA.match(l))
    lineas = [l for l in lineas if not _RE_PAGINA_SUELTA.match(l)]
    cabeceras = _candidatas_cabecera(lineas)
    indices_a_quitar = set()
    for idxs in cabeceras.values():
        indices_a_quitar.update(idxs)
    lineas = [l for i, l in enumerate(lineas) if i not in indices_a_quitar]
    limpio = "\n".join(lineas)
    despues = medir_defectos(limpio)
    dudosos = {}
    for tok in _RE_TOKEN_AMBIGUO.findall(limpio):
        dudosos[tok] = dudosos.get(tok, 0) + 1
    informe = {
        "antes": antes,
        "despues": despues,
        "guiones_unidos": unidos,
        "paginas_eliminadas": paginas,
        "cabeceras_pagina_eliminadas": len(indices_a_quitar),
        "interrogaciones_reparadas": interrogaciones,
        "dudosos": dudosos,
    }
    return limpio, informe


def segmentar_arcanos(texto_limpio, id_libro=ID_LIBRO):
    """Segmenta el libro limpio en secciones por arcano mayor.

    Cada seccion tiene el formato de ``libros_segmentar`` (``seccion``,
    ``titulo``, ``texto``, ``chars``, ``id_libro``, ``posicion``) mas
    ``entidad_id`` para trazabilidad. Las secciones de mas de 12.000 caracteres
    se parten con el solape de ``libros_segmentar._partir_largo``.
    """
    lineas = texto_limpio.split("\n")
    todos = _encabezados_numericos(lineas)
    arcanos = [h for h in todos if h["token"]]
    if not arcanos:
        return []
    secciones = []
    posicion = 0
    for enc in arcanos:
        i = todos.index(enc)
        inicio = enc["linea"] + 1
        fin = todos[i + 1]["linea"] if i + 1 < len(todos) else len(lineas)
        cuerpo = "\n".join(lineas[inicio:fin]).strip()
        if not cuerpo:
            continue
        partes = libros_segmentar._partir_largo(cuerpo) if len(cuerpo) > MAX_SECCION else [cuerpo]
        for parte in partes:
            parte = parte.strip()
            if not parte:
                continue
            secciones.append({
                "seccion": posicion + 1,
                "titulo": enc["titulo"],
                "texto": parte,
                "chars": len(parte),
                "id_libro": id_libro,
                "posicion": posicion,
                "entidad_id": enc["entidad_id"],
            })
            posicion += 1
    return secciones


def _normalizar_palabras(texto):
    """Palabras en minuscula sin tildes ni signos: base de la puerta anti-copia."""
    bajo = sin_tildes(texto.lower())
    bajo = re.sub(r"[^a-z0-9 ]+", " ", bajo)
    return bajo.split()


def construir_indice_copia(texto_libro, max_consecutivas=MAX_CONSECUTIVAS_COPIA):
    """Indice de n-gramas (n = max_consecutivas + 1) del libro, por hash.

    Se construye una sola vez por corrida y se reusa para todas las afirmaciones.
    """
    n = max_consecutivas + 1
    palabras = _normalizar_palabras(texto_libro)
    indice = set()
    for i in range(len(palabras) - n + 1):
        indice.add(hash(tuple(palabras[i:i + n])))
    return indice


def es_copia_literal(afirmacion, texto_libro=None, max_consecutivas=MAX_CONSECUTIVAS_COPIA,
                     indice=None):
    """True si la afirmacion repite mas de ``max_consecutivas`` palabras seguidas.

    Se pasa ``indice`` (de ``construir_indice_copia``) para no reconstruirlo por
    cada afirmacion. Una afirmacion de ``max_consecutivas`` o menos palabras no
    puede superar el umbral y devuelve False.
    """
    n = max_consecutivas + 1
    palabras = _normalizar_palabras(afirmacion)
    if len(palabras) < n:
        return False
    if indice is None:
        if texto_libro is None:
            raise ValueError("hace falta texto_libro o indice")
        indice = construir_indice_copia(texto_libro, max_consecutivas)
    for i in range(len(palabras) - n + 1):
        if hash(tuple(palabras[i:i + n])) in indice:
            return True
    return False


def extraer_afirmaciones_nichols(cliente, entidad_id, faceta, texto, idioma, corr,
                                indice=None):
    """Extraccion de T38 mas la puerta anti-copia sobre la afirmacion.

    Reutiliza ``afirmaciones_libros.extraer_afirmaciones_libros`` y descarta
    las afirmaciones aceptadas que resulten copia literal del libro.
    """
    resultado = afirmaciones_libros.extraer_afirmaciones_libros(
        cliente, entidad_id, faceta, texto, idioma, corr)
    if indice is None:
        indice = construir_indice_copia(texto)
    filtradas = []
    for item in resultado["afirmaciones"]:
        if es_copia_literal(item["afirmacion"], indice=indice):
            resultado["descartadas"].append(
                (item["afirmacion"], "copia_literal"))
        else:
            filtradas.append(item)
    resultado["afirmaciones"] = filtradas
    return resultado


def validar_work_dir(work_dir):
    """Rechaza el work-dir real: aqui nunca se escribe en la tuberia madre."""
    real = os.path.realpath(work_dir)
    raiz_real = os.path.realpath(WORK_DIR_REAL)
    if real == raiz_real or real.startswith(raiz_real + os.sep):
        raise ValueError(
            "work-dir %r apunta al directorio real de la tuberia; usa uno "
            "aparte (por defecto: %s)" % (work_dir, WORK_DIR_NICHOLS))
    return real


def extraer_texto_pdf(pdf=PDF_FUENTE, destino=None):
    """Extrae el crudo con ``pdftotext -layout`` si aun no existe en destino."""
    if destino and os.path.isfile(destino) and os.path.getsize(destino) > 1024:
        return destino
    if not os.path.isfile(pdf):
        raise FileNotFoundError("no existe el PDF: %s" % pdf)
    if not destino:
        raise ValueError("hace falta un destino para el crudo")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    subprocess.run(["pdftotext", "-layout", pdf, destino], check=True)
    return destino


def ruta_crudo(work_dir):
    return os.path.join(work_dir, "crudo", ID_LIBRO + ".txt")


def preparar(work_dir=WORK_DIR_NICHOLS):
    """Crea la estructura, extrae el crudo y escribe el meta del juez."""
    work_dir = validar_work_dir(work_dir)
    for sub in ("crudo", "limpio", "secciones", "evidencias", "knowledge",
               "resumenes"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    extraer_texto_pdf(PDF_FUENTE, ruta_crudo(work_dir))
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "id": ID_LIBRO, "anio": ANIO_LIBRO, "idioma": IDIOMA_LIBRO,
            "titulo": TITULO_LIBRO, "autor": AUTOR_LIBRO,
            "origen": "comprado_por_usuario",
            "licencia_hint": "libro con copyright, uso interno",
        }, ensure_ascii=False) + "\n")
    return work_dir


def construir_cliente_endpoints(endpoints_csv, timeout=TIMEOUT_NICHOLS,
                               acotar=True):
    """Cliente fijado a los endpoints indicados.

    Rechaza el nodo1 reservado (10.0.0.3). Iguales garantias que en
    ``clasicos_pd_a_evidencias``. Con ``acotar=True`` (juez) envuelve en
    ``_ClienteAcotado`` para reintentos bajos; con ``acotar=False``
    (afirmaciones) devuelve el ``LLMClient`` crudo, que expone ``chat_json``.
    """
    endpoints = [e.strip() for e in (endpoints_csv or "").split(",") if e.strip()]
    if not endpoints:
        endpoints = [e.strip() for e in ENDPOINTS_POR_DEFECTO.split(",")]
    for url in endpoints:
        if urlparse(url).hostname not in HOSTS_LOCALES_PERMITIDOS:
            raise ValueError(
                "endpoint no permitido (solo nodo1 y nodo2): %r" % url)
    base = llm_client.LLMClient(endpoints=endpoints, timeout=timeout)
    if acotar:
        return libros_pipeline._ClienteAcotado(base)
    return base


def _hashes_juzgados(work_dir):
    ruta = os.path.join(work_dir, "evidencias", "juicios.jsonl")
    hechos = set()
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    registro = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if registro.get("hash"):
                    hechos.add(registro["hash"])
    return hechos


def purgar_errores_juez(work_dir):
    """Quita los juicios ``tipo=error`` para que la reanudacion los reintente."""
    import datetime
    import shutil
    ruta = os.path.join(work_dir, "evidencias", "juicios.jsonl")
    if not os.path.exists(ruta):
        return 0
    buenos = []
    errores = 0
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            stripped = linea.strip()
            if not stripped:
                continue
            try:
                registro = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if registro.get("juicio", {}).get("tipo") == "error":
                errores += 1
            else:
                buenos.append(stripped)
    if errores:
        sello = datetime.datetime.now().strftime("%Y%m%d")
        respaldo = "%s.bak-%s" % (ruta, sello)
        if not os.path.exists(respaldo):
            shutil.copy2(ruta, respaldo)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            for linea in buenos:
                fh.write(linea + "\n")
        os.replace(tmp, ruta)
    return errores


def etapa_limpieza_y_segmentacion(work_dir):
    """Limpia el crudo, escribe el informe y segmenta por arcanos a disco."""
    with open(ruta_crudo(work_dir), encoding="utf-8", errors="replace") as fh:
        crudo = fh.read()
    limpio, informe = limpiar_ocr(crudo)
    ruta_limpio = os.path.join(work_dir, "limpio", ID_LIBRO + ".txt")
    with open(ruta_limpio, "w", encoding="utf-8") as fh:
        fh.write(limpio)
    secciones = segmentar_arcanos(limpio, ID_LIBRO)
    ruta_secciones = os.path.join(work_dir, "secciones", ID_LIBRO + ".jsonl")
    with open(ruta_secciones, "w", encoding="utf-8") as fh:
        for sec in secciones:
            fh.write(json.dumps(sec, ensure_ascii=False) + "\n")
    ruta_informe = os.path.join(work_dir, "limpio", ID_LIBRO + "_informe.json")
    with open(ruta_informe, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)
    return secciones, informe


def medir(work_dir=WORK_DIR_NICHOLS):
    """Dry-run: segmenta en memoria y cuenta secciones y llamadas estimadas."""
    with open(ruta_crudo(work_dir), encoding="utf-8", errors="replace") as fh:
        crudo = fh.read()
    limpio, informe = limpiar_ocr(crudo)
    secciones = segmentar_arcanos(limpio, ID_LIBRO)
    con_candidatos = sum(1 for s in secciones if juez.candidatos_seccion(s))
    por_entidad = {}
    for s in secciones:
        por_entidad[s["entidad_id"]] = por_entidad.get(s["entidad_id"], 0) + 1
    return {
        "secciones": len(secciones),
        "con_candidatos": con_candidatos,
        "llamadas_estimadas": con_candidatos,
        "arcanos_cubiertos": len(por_entidad),
        "dudosos_restantes": sum(informe["dudosos"].values()),
        "por_entidad": por_entidad,
    }


def procesar_juez(work_dir=WORK_DIR_NICHOLS, workers=1, max_llamadas=0,
                 cliente=None, simulado=False):
    """Corre el juez sobre las secciones segmentadas (reanudable)."""
    ruta_secciones = os.path.join(work_dir, "secciones", ID_LIBRO + ".jsonl")
    secciones = []
    with open(ruta_secciones, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                secciones.append(json.loads(linea))
    if not secciones:
        print("%s: sin secciones que juzgar" % ID_LIBRO, file=sys.stderr)
        return {"juzgadas": 0, "llamadas": 0, "evidencias": 0,
                "reaprovechadas": 0, "sin_candidatos": 0, "error": 0}
    purgados = purgar_errores_juez(work_dir)
    if purgados:
        print("%s: %d juicios-error purgados para reintentar"
              % (ID_LIBRO, purgados), flush=True)
    if cliente is None:
        if not simulado:
            raise ValueError("hace falta cliente o --simulado")
        cliente = libros_pipeline._ClienteAcotado(
            llm_client.LLMClient(simulado=_simulado_juez_nichols))
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if max_llamadas and max_llamadas > 0:
        hechos = _hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                     if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:max_llamadas]
    stats = juez.procesar_secciones(a_procesar, cliente,
                                    os.path.join(work_dir, "evidencias"),
                                    meta=meta, workers=workers)
    return stats


def _simulado_juez_nichols(sistema, usuario):
    """Cliente simulado del juez: sin candidatos reales, para pruebas offline."""
    return json.dumps({"tipo": "sin_interes", "razon": "simulado"},
                     ensure_ascii=False)


def procesar_afirmaciones(work_dir=WORK_DIR_NICHOLS, workers=1, limite=0,
                         cliente=None, simulado=False):
    """Extrae afirmaciones con la puerta anti-copia sobre las evidencias del libro."""
    import threading
    from collections import Counter
    import afirmaciones_es as es

    ruta_ev = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    evidencias = []
    if os.path.exists(ruta_ev):
        with open(ruta_ev, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if linea:
                    ev = json.loads(linea)
                    if ev.get("fuente_id") == ID_LIBRO:
                        evidencias.append(ev)
    if limite:
        evidencias = evidencias[:limite]

    indice_sec = afirmaciones_libros.IndiceLibros(
        os.path.join(work_dir, "secciones"))
    catalogo = es._catalogo_familias()
    corr = afirmaciones_libros.cargar_correspondencias()
    if cliente is None:
        if not simulado:
            raise ValueError("hace falta cliente o --simulado")
        cliente = llm_client.LLMClient(
            simulado=afirmaciones_libros._simulado_libros)

    out_dir = os.path.join(work_dir, "afirmaciones")
    os.makedirs(out_dir, exist_ok=True)
    ruta_af = os.path.join(out_dir, "afirmaciones_nichols.jsonl")
    ruta_pr = os.path.join(out_dir, "procesados.jsonl")

    procesados = _cargar_procesados(ruta_pr)
    stats = {"procesadas": 0, "afirmaciones": 0, "copia_rechazada": 0,
             "errores": 0, "descartadas": Counter()}
    lock = threading.Lock()

    pendientes = [
        ev for ev in evidencias
        if (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))
        not in procesados
    ]

    def trabajar(ev):
        sec = indice_sec.seccion(ev.get("fuente_id"), ev.get("hash_seccion"))
        if sec is None or not (sec.get("texto") or "").strip():
            res = {"estado": "sin_texto", "afirmaciones": [], "descartadas": []}
        else:
            texto = sec["texto"]
            indice = construir_indice_copia(texto)
            res = extraer_afirmaciones_nichols(
                cliente, ev.get("entidad_id"), ev.get("faceta"), texto,
                ev.get("idioma"), corr, indice=indice)
        with lock:
            for item in res["afirmaciones"]:
                fa.write(json.dumps(
                    afirmaciones_libros.registro_afirmacion_libros(ev, item),
                    ensure_ascii=False) + "\n")
            for txt, motivo in res["descartadas"]:
                stats["descartadas"][motivo] += 1
                if motivo == "copia_literal":
                    stats["copia_rechazada"] += 1
            fp.write(json.dumps({
                "hash_seccion": ev.get("hash_seccion"),
                "entidad_id": ev.get("entidad_id"),
                "faceta": ev.get("faceta"),
                "estado": res["estado"],
                "n_afirmaciones": len(res["afirmaciones"]),
            }, ensure_ascii=False) + "\n")
            fa.flush()
            fp.flush()
            stats["procesadas"] += 1
            if res["estado"] == "error":
                stats["errores"] += 1
            else:
                stats["afirmaciones"] += len(res["afirmaciones"])

    with open(ruta_pr, "a", encoding="utf-8") as fp, \
            open(ruta_af, "a", encoding="utf-8") as fa:
        if workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=workers) as ex:
                list(ex.map(trabajar, pendientes))
        else:
            for ev in pendientes:
                trabajar(ev)
    return stats


def _cargar_procesados(ruta):
    claves = set()
    if not os.path.exists(ruta):
        return claves
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                d = json.loads(linea)
            except ValueError:
                continue
            claves.add((d.get("hash_seccion"), d.get("entidad_id"),
                        d.get("faceta")))
    return claves


def ejemplos_parrafos(crudo, n=10):
    """Pares (antes, despues) de parrafos representativos para el ESTADO.md."""
    limpio, _ = limpiar_ocr(crudo)
    crudo_parrafos = [p.strip() for p in re.split(r"\n\s*\n", crudo) if len(p.strip()) > 120]
    limpio_parrafos = [p.strip() for p in re.split(r"\n\s*\n", limpio) if len(p.strip()) > 120]
    pares = []
    paso_c = max(1, len(crudo_parrafos) // max(n, 1))
    for i in range(0, min(len(crudo_parrafos), len(limpio_parrafos)), paso_c):
        if len(pares) >= n:
            break
        pares.append((crudo_parrafos[i], limpio_parrafos[i]))
    return pares


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Procesa el libro comprado Nichols hacia evidencias (T114).")
    parser.add_argument("--work-dir", default=WORK_DIR_NICHOLS)
    parser.add_argument("--endpoints", default=NODO2_ENDPOINT,
                       help="URLs del LLM del juez separadas por comas "
                            "(solo nodo2; nunca 10.0.0.3).")
    parser.add_argument("--workers", type=int, default=1,
                       help="hilos de llamada al LLM (max %d)" % MAX_WORKERS)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_NICHOLS)
    parser.add_argument("--max-llamadas", type=int, default=0)
    parser.add_argument("--simulado", action="store_true")
    parser.add_argument("--preparar", action="store_true",
                       help="crea el work-dir, extrae el crudo y el meta")
    parser.add_argument("--dry-run", action="store_true",
                       help="mide secciones y llamadas sin LLM")
    parser.add_argument("--juez", action="store_true",
                       help="corre el juez sobre las secciones")
    parser.add_argument("--afirmaciones", action="store_true",
                       help="extrae afirmaciones con puerta anti-copia")
    parser.add_argument("--ejemplos", type=int, default=0,
                       help="imprime N pares de parrafos antes/despues")
    args = parser.parse_args(argv)

    try:
        work_dir = validar_work_dir(args.work_dir)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.workers > MAX_WORKERS:
        print("error: workers <= %d (nodo2 saturable)" % MAX_WORKERS,
              file=sys.stderr)
        return 2

    if args.preparar:
        preparar(work_dir)
        print("work-dir preparado en %s" % work_dir)
        return 0

    if args.ejemplos:
        with open(ruta_crudo(work_dir), encoding="utf-8", errors="replace") as fh:
            crudo = fh.read()
        for antes, despues in ejemplos_parrafos(crudo, args.ejemplos):
            print("=== ANTES ===")
            print(antes[:600])
            print("=== DESPUES ===")
            print(despues[:600])
            print()
        return 0

    if args.dry_run:
        if not os.path.isfile(ruta_crudo(work_dir)):
            preparar(work_dir)
        medida = medir(work_dir)
        print("%s: %d secciones, %d con candidatos (~%d llamadas), "
              "%d arcanos cubiertos, %d tokens dudosos restantes"
              % (ID_LIBRO, medida["secciones"], medida["con_candidatos"],
                 medida["llamadas_estimadas"], medida["arcanos_cubiertos"],
                 medida["dudosos_restantes"]))
        return 0

    if args.juez:
        if not os.path.isfile(
                os.path.join(work_dir, "secciones", ID_LIBRO + ".jsonl")):
            etapa_limpieza_y_segmentacion(work_dir)
        cliente = None
        if not args.simulado:
            cliente = construir_cliente_endpoints(args.endpoints,
                                                timeout=args.timeout)
        stats = procesar_juez(work_dir, workers=args.workers,
                             max_llamadas=args.max_llamadas, cliente=cliente,
                             simulado=args.simulado)
        print("%s juez: %s" % (ID_LIBRO, json.dumps(stats, ensure_ascii=False)))
        return 0

    if args.afirmaciones:
        cliente = None
        if not args.simulado:
            cliente = construir_cliente_endpoints(args.endpoints,
                                                timeout=args.timeout,
                                                acotar=False)
        stats = procesar_afirmaciones(work_dir, workers=args.workers,
                                     limite=args.max_llamadas, cliente=cliente,
                                     simulado=args.simulado)
        print("%s afirmaciones: %s" % (ID_LIBRO, json.dumps(
            {k: v for k, v in stats.items() if k != "descartadas"},
            ensure_ascii=False)))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
