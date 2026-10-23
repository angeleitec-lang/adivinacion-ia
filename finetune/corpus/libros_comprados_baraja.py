"""Procesado determinista de dos libros comprados de baraja española (T129).

Libros comprados por el usuario (copyright, uso interno):

* ``libro_salas_baraja``: «El arte de echar las cartas» (Salas), 25 pp.
* ``libro_tiradas_baraja_espanola``: «Tiradas de cartas españolas», 20 pp.

El PDF nunca se copia al repo: se extrae con ``pdftotext -layout`` en un
work-dir aparte (``/Users/angelgonzalez/fase0/libros_comprados_baraja``).

Los dos libros describen 12 naipes por palo (incluyen Ocho y Nueve), pero la KB
solo tiene 40 naipes (10 por palo): As..Siete, Sota, Caballo y Rey. El mapeo se
hace por (rango, palo) contra ``cartas.NAIPES_ESPANOLES``; Ocho y Nueve quedan
sin entidad y se guardan aparte.

Cada seccion es UNA carta en UNA orientacion (derecho/reves). Las tiradas y las
posiciones son metodo, no significado de carta, y se guardan en ficheros
aparte. Este modulo NO llama al LLM: extrae, limpia, segmenta, mapea, genera
evidencias y afirmaciones deterministas con puerta anti-copia (maximo 25
palabras consecutivas iguales al libro). Los comandos LLM para una fase
posterior quedan documentados en ``finetune/knowledge/libros_comprados_baraja.md``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from urllib.parse import urlparse

import afirmaciones_libros
import cartas
import cobertura

PDFTOTEXT = "/opt/homebrew/bin/pdftotext"

WORK_DIR_REAL = "/Users/angelgonzalez/fase0/libros"
WORK_DIR_DEFECTO = "/Users/angelgonzalez/fase0/libros_comprados_baraja"
CARPETA_PDFS = "/Users/angelgonzalez/fase0/libros_comprados"

LIBROS = {
    "libro_salas_baraja": {
        "id": "libro_salas_baraja",
        "titulo": "El arte de echar las cartas",
        "autor": "Salas",
        "anio": None,
        "idioma": "es",
        "archivo": "Salas - El arte de echar las cartas.pdf",
        "corto": "salas",
    },
    "libro_tiradas_baraja_espanola": {
        "id": "libro_tiradas_baraja_espanola",
        "titulo": "Tiradas de cartas españolas",
        "autor": "Anónimo",
        "anio": None,
        "idioma": "es",
        "archivo": "TiradasDeCartasEspanolas.pdf",
        "corto": "tiradas",
    },
}

META_NOMBRE = "fuentes_libros_comprados_baraja.jsonl"
ORIGEN = "comprado_por_usuario"
LICENCIA_HINT = "libro con copyright, uso interno"
PROCEDENCIA = "comprado por el usuario, uso interno, libro con copyright"

NODO2_ENDPOINT = "http://10.0.0.4:8000/v1"
NODO1_RESERVADO = "10.0.0.3"
# Hosts locales permitidos para el LLM: nodo1 y nodo2 (autorizado por el usuario el 23/10).
HOSTS_LOCALES_PERMITIDOS = ("10.0.0.3", "10.0.0.4")
ENDPOINTS_POR_DEFECTO = "http://10.0.0.3:8000/v1,http://10.0.0.4:8000/v1"
TIMEOUT = 120.0
MAX_WORKERS = 2

MAX_CONSECUTIVAS_COPIA = 25
MAX_PALABRAS_CITA = 20
MAX_PALABRAS_NUCLEO = 14
CALIDAD = 3
PERIODO = "moderna"

PALOS = ("oros", "copas", "espadas", "bastos")
RANGOS = ("as", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
          "nueve", "sota", "caballo", "rey")
RANGOS_KB = ("as", "dos", "tres", "cuatro", "cinco", "seis", "siete", "sota",
             "caballo", "rey")

_PALO_RE = "|".join(PALOS)
_RANGO_RE = "|".join(RANGOS)
_ENCABEZADO_RE = re.compile(
    r"^(%s)\s+de\s+(%s)$" % (_RANGO_RE, _PALO_RE), re.IGNORECASE)
_ENCABEZADO_MAYUS_RE = re.compile(
    r"^(%s)\s+DE\s+(%s)$" % (_RANGO_RE.upper(), _PALO_RE.upper()))
_DERECHO_RE = re.compile(r"\b(al\s*derecho|alderecho)\b\s*[,:.]?", re.IGNORECASE)
_REVES_RE = re.compile(r"\b(?:al\s*rev[eé]s|alreves)\b\s*[,:.]?", re.IGNORECASE)
_PAGINA_RE = re.compile(r"^\s*\d{1,3}\s*$")


def sin_tildes(texto: str) -> str:
    """Quita tildes y diéresis conservando el resto de caracteres."""
    if not texto:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def norm(texto: str) -> str:
    """Minúsculas, sin tildes, sin signos y con espacios simples."""
    texto = sin_tildes(texto or "").lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_token(texto: str) -> str:
    return norm(texto)


def limpiar_texto(texto: str) -> str:
    """Colapsa espacios, quita ruido de paginación y basura de maquetación."""
    texto = (texto or "").replace("\u00ad", "")
    texto = texto.replace("\uf0b7", " ").replace("\uf0a7", " ")
    lineas = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        if _PAGINA_RE.match(linea):
            continue
        if linea.startswith("</"):
            continue
        if "Elige un tema y haz tu consulta" in linea:
            continue
        lineas.append(re.sub(r"\s+", " ", linea))
    return " ".join(lineas).strip()


def es_nota_metodo(texto: str) -> bool:
    """Las notas con asterisco son método (cómo saber si está del revés)."""
    t = norm(texto)
    return t.startswith("para saber si esta del reves") or \
        t.startswith("estara del reves cuando") or \
        t.startswith("si el palo") or t.startswith("las cartas se")


# ---------------------------------------------------------------------------
# Catálogo KB
# ---------------------------------------------------------------------------

def _indice_kb():
    indice = {}
    for naipe in cartas.NAIPES_ESPANOLES:
        rango = norm(naipe["nombre"].split(" de ")[0])
        palo = norm(naipe["palo"])
        indice[(rango, palo)] = naipe["id"]
    return indice


INDICE_KB = _indice_kb()


def entidad_de(rango: str, palo: str):
    """Devuelve (entidad_id, motivo). entidad_id None si no está en la KB."""
    rango_n = norm(rango)
    palo_n = norm(palo)
    entidad = INDICE_KB.get((rango_n, palo_n))
    if entidad:
        return entidad, None
    if rango_n in ("ocho", "nueve"):
        return None, "rango_%s_ausente_en_kb" % rango_n
    return None, "sin_mapeo_kb"


def nombre_carta(rango: str, palo: str) -> str:
    return "%s de %s" % (rango.capitalize(), palo.capitalize())


# ---------------------------------------------------------------------------
# Extracción y preparación
# ---------------------------------------------------------------------------

def validar_work_dir(work_dir: str) -> str:
    """Rechaza el work-dir real de la tubería y sus subdirectorios.

    Nuestro work-dir también cuelga de ``fase0`` pero es un directorio nuevo y
    apartado (``libros_comprados_baraja``), así que se permite.
    """
    if not work_dir:
        raise ValueError("work-dir vacío")
    ruta = os.path.abspath(os.path.expanduser(work_dir))
    real = os.path.abspath(WORK_DIR_REAL)
    if ruta == real or ruta.startswith(real + os.sep):
        raise ValueError("work-dir dentro de la tubería real: %r" % ruta)
    if ruta == "/Users/angelgonzalez/fase0":
        raise ValueError("work-dir es fase0 entero: %r" % ruta)
    return ruta


def ruta_crudo(work_dir: str, libro: dict) -> str:
    return os.path.join(work_dir, "crudo", libro["corto"] + ".txt")


def extraer_texto_pdf(pdf: str, destino: str) -> str:
    """Extrae texto con pdftotext -layout; reutiliza caché si es razonable."""
    if os.path.exists(destino) and os.path.getsize(destino) > 1024:
        return destino
    if not os.path.exists(pdf):
        raise FileNotFoundError(pdf)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".tmp"
    subprocess.run([PDFTOTEXT, "-layout", pdf, tmp], check=True)
    os.replace(tmp, destino)
    return destino


def preparar(work_dir: str = WORK_DIR_DEFECTO) -> str:
    work_dir = validar_work_dir(work_dir)
    for sub in ("crudo", "limpio", "secciones", "evidencias", "knowledge",
                "afirmaciones", "resumenes"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        for libro in LIBROS.values():
            fh.write(json.dumps({
                "id": libro["id"], "anio": libro["anio"],
                "idioma": libro["idioma"], "titulo": libro["titulo"],
                "autor": libro["autor"], "origen": ORIGEN,
                "licencia_hint": LICENCIA_HINT,
                "procedencia": PROCEDENCIA,
            }, ensure_ascii=False) + "\n")
    for libro in LIBROS.values():
        extraer_texto_pdf(os.path.join(CARPETA_PDFS, libro["archivo"]),
                          ruta_crudo(work_dir, libro))
    return work_dir


def _lineas_de(entrada: str):
    """Acepta una ruta o el propio texto (útil en tests)."""
    try:
        if os.path.exists(entrada):
            return _leer_lineas(entrada)
    except OSError:
        pass
    return [(1, linea) for linea in entrada.splitlines()]


def _leer_lineas(ruta: str):
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    pagina = 1
    salida = []
    for linea in texto.splitlines():
        if "\f" in linea:
            partes = linea.split("\f")
            for i, parte in enumerate(partes):
                if i:
                    pagina += 1
                salida.append((pagina, parte))
        else:
            salida.append((pagina, linea))
    return salida


# ---------------------------------------------------------------------------
# Parser Salas: 48 encabezados en mayúsculas + 96 orientaciones
# ---------------------------------------------------------------------------

def _encabezado_salas(texto: str):
    limpio = texto.strip()
    if not limpio or limpio != limpio.upper():
        return None
    m = _ENCABEZADO_MAYUS_RE.match(limpio)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).lower()


def segmentar_salas(texto: str, libro: dict = None):
    """Devuelve (secciones, metodo, incidencias) del libro de Salas."""
    libro = libro or LIBROS["libro_salas_baraja"]
    lineas = _lineas_de(texto)
    secciones, metodo, incidencias = [], [], []
    actual = None
    orientacion = None
    buffer = []

    def cerrar():
        nonlocal buffer
        if actual and orientacion and buffer:
            cuerpo = limpiar_texto(" ".join(buffer))
            if cuerpo:
                secciones.append(_seccion(libro, actual[0], actual[1],
                                          orientacion, cuerpo,
                                          len(secciones), actual[2],
                                          "encabezado_mayusculas", "alta"))
        buffer = []

    for pagina, linea in lineas:
        cab = _encabezado_salas(linea)
        if cab:
            cerrar()
            actual = (cab[0], cab[1], pagina)
            orientacion = None
            continue
        limpia = linea.lstrip().replace("ÁL", "AL", 1)
        m_der = (_DERECHO_RE.match(limpia)
                 if limpia.startswith("AL DERECHO") else None)
        m_rev = (_REVES_RE.match(limpia)
                 if limpia.startswith(("AL REVÉS", "AL REVES")) else None)
        if actual and (m_der or m_rev):
            cerrar()
            if m_der:
                orientacion = "derecho"
                resto = linea[m_der.end():]
            else:
                orientacion = "reves"
                resto = linea[m_rev.end():]
            buffer = [resto]
            continue
        if actual is None:
            if linea.strip():
                metodo.append({"id_libro": libro["id"], "pagina": pagina,
                               "texto": limpiar_texto(linea)})
            continue
        buffer.append(linea)
    cerrar()

    return secciones, metodo, incidencias


# ---------------------------------------------------------------------------
# Parser Tiradas: bloques «Al derecho ... / Al revés ...»
# ---------------------------------------------------------------------------

def _nombre_de_linea(texto: str):
    m = _ENCABEZADO_RE.search(texto.strip().strip(".,:;"))
    if not m:
        return None
    return m.group(1).lower(), m.group(2).lower()


def segmentar_tiradas(texto: str, libro: dict = None):
    """Devuelve (secciones, metodo, incidencias) del libro de tiradas.

    Los bloques de Copas no llevan encabezado: se asignan en orden ordinal
    As..Rey porque las ilustraciones impresas van numeradas 1..12 (verificado
    visualmente). Se documenta con ``metodo="ordinal_ilustracion"``.
    """
    libro = libro or LIBROS["libro_tiradas_baraja_espanola"]
    lineas = _lineas_de(texto)
    metodo, incidencias = [], []

    primer_encabezado = len(lineas)
    for i, (pagina, linea) in enumerate(lineas):
        if _nombre_de_linea(linea.strip()):
            primer_encabezado = i
            break
    inicios = []
    for i, (pagina, linea) in enumerate(lineas):
        if i < primer_encabezado:
            continue
        m = _DERECHO_RE.search(linea)
        if m:
            prefijo = linea[:m.start()].strip(" .,:;-")
            if prefijo and not _nombre_de_linea(prefijo):
                continue
            inicios.append((i, m.start(), m.end(), pagina))

    bloques = []
    for k, (i, ini, fin, pagina) in enumerate(inicios):
        fin_bloque = inicios[k + 1][0] if k + 1 < len(inicios) else len(lineas)
        prefijo = lineas[i][1][:ini].strip(" .,:;-")
        cab = _nombre_de_linea(prefijo) if prefijo else None
        if prefijo and not cab:
            continue
        cabecera_linea = None
        if not cab:
            for j in range(i - 1, max(-1, i - 4), -1):
                posible = lineas[j][1].strip()
                if not posible or _PAGINA_RE.match(posible):
                    continue
                cab = _nombre_de_linea(posible)
                if cab:
                    cabecera_linea = j
                break
        cuerpo = [lineas[i][1][fin:]]
        for j in range(i + 1, fin_bloque):
            texto_linea = lineas[j][1]
            if _nombre_de_linea(texto_linea.strip()):
                break
            cuerpo.append(texto_linea)
        crudo = "\n".join(cuerpo)
        partes = _REVES_RE.split(crudo, maxsplit=1)
        derecho = limpiar_texto(partes[0])
        reves = limpiar_texto(partes[1]) if len(partes) > 1 else ""
        if not derecho:
            incidencias.append("tiradas: bloque sin texto al derecho (pág. %d)"
                               % pagina)
            continue
        bloques.append({"cab": cab, "pagina": pagina, "derecho": derecho,
                        "reves": reves, "prefijo": prefijo})

    # Método: todo lo anterior al primer bloque y notas sueltas.
    primera = inicios[0][0] if inicios else len(lineas)
    for j in range(0, primera):
        t = limpiar_texto(lineas[j][1])
        if t:
            metodo.append({"id_libro": libro["id"], "pagina": lineas[j][0],
                           "texto": t})

    # Asignación de encabezados: las tandas sin encabezado pertenecen al palo
    # siguiente al último encabezado explícito (Oros -> Copas -> Bastos ->
    # Espadas) y van en orden ordinal As..Rey. En este libro las ilustraciones
    # de Copas van numeradas 1..12, lo que respalda el orden.
    indice_palo = {p: i for i, p in enumerate(PALOS)}
    siguiente = {p: 0 for p in PALOS}
    for b in bloques:
        if b["cab"]:
            palo, rango = b["cab"][1], b["cab"][0]
            if rango in RANGOS:
                siguiente[palo] = max(siguiente[palo],
                                      RANGOS.index(rango) + 1)
    ultimo = None
    i = 0
    while i < len(bloques):
        if bloques[i]["cab"]:
            ultimo = bloques[i]["cab"][1]
            i += 1
            continue
        j = i
        while j < len(bloques) and not bloques[j]["cab"]:
            j += 1
        if ultimo is not None:
            palo = PALOS[(indice_palo[ultimo] + 1) % len(PALOS)]
        else:
            palo = next((p for p in PALOS if siguiente[p] == 0), PALOS[0])
        for b in bloques[i:j]:
            k = siguiente[palo]
            if k < len(RANGOS):
                b["cab"] = (RANGOS[k], palo)
                b["metodo"] = "ordinal_ilustracion"
                b["confianza"] = "alta"
                siguiente[palo] = k + 1
        i = j

    secciones = []
    for b in bloques:
        if not b["cab"]:
            incidencias.append("tiradas: bloque sin encabezado asignable "
                               "(pág. %d)" % b["pagina"])
            continue
        rango, palo = b["cab"]
        for orientacion, cuerpo in (("derecho", b["derecho"]),
                                    ("reves", b["reves"])):
            if not cuerpo:
                continue
            secciones.append(_seccion(
                libro, rango, palo, orientacion, cuerpo, len(secciones),
                b["pagina"], b.get("metodo", "encabezado"), 
                b.get("confianza", "alta")))
    return secciones, metodo, incidencias


def _seccion(libro, rango, palo, orientacion, texto, posicion, pagina,
             metodo, confianza):
    entidad, motivo = entidad_de(rango, palo)
    return {
        "id_libro": libro["id"],
        "fuente_id": libro["id"],
        "seccion": "%s:%s:%s:%s" % (libro["id"], palo, rango, orientacion),
        "titulo": "%s (%s)" % (nombre_carta(rango, palo), orientacion),
        "texto": texto,
        "chars": len(texto),
        "posicion": posicion,
        "entidad_id": entidad,
        "motivo_sin_entidad": motivo,
        "rango": rango,
        "palo": palo,
        "orientacion": orientacion,
        "idioma": libro["idioma"],
        "metodo": metodo,
        "confianza": confianza,
        "pagina": pagina,
    }


def segmentar_libro(libro: dict, work_dir: str):
    ruta = ruta_crudo(work_dir, libro)
    if libro["id"] == "libro_salas_baraja":
        return segmentar_salas(ruta, libro)
    return segmentar_tiradas(ruta, libro)


# ---------------------------------------------------------------------------
# Escritura de secciones
# ---------------------------------------------------------------------------

def _escribir_jsonl(ruta: str, filas) -> int:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    n = 0
    with open(ruta, "w", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            n += 1
    return n


def segmentar_a_disco(work_dir: str, verboso=True):
    work_dir = validar_work_dir(work_dir)
    resumen = {}
    for libro in LIBROS.values():
        secciones, metodo, incidencias = segmentar_libro(libro, work_dir)
        con = [s for s in secciones if s["entidad_id"]]
        sin = [s for s in secciones if not s["entidad_id"]]
        _escribir_jsonl(os.path.join(work_dir, "secciones",
                                     libro["id"] + ".jsonl"), secciones)
        _escribir_jsonl(os.path.join(work_dir, "secciones",
                                     "sin_entidad_" + libro["id"] + ".jsonl"),
                        sin)
        _escribir_jsonl(os.path.join(work_dir, "secciones",
                                     "metodo_" + libro["id"] + ".jsonl"),
                        metodo)
        resumen[libro["id"]] = {
            "secciones": len(secciones), "con_entidad": len(con),
            "sin_entidad": len(sin), "metodo": len(metodo),
            "incidencias": incidencias,
            "cartas": sorted({(s["palo"], s["rango"]) for s in secciones}),
        }
        if verboso:
            print("%s: %d secciones (%d con entidad, %d sin entidad), "
                  "%d método, %d incidencias"
                  % (libro["id"], len(secciones), len(con), len(sin),
                     len(metodo), len(incidencias)))
            for inc in incidencias:
                print("  AVISO:", inc)
    with open(os.path.join(work_dir, "resumenes", "segmentacion.json"), "w",
              encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return resumen


# ---------------------------------------------------------------------------
# Anti-copia y afirmaciones deterministas
# ---------------------------------------------------------------------------

def construir_indice_copia(texto: str,
                           max_consecutivas: int = MAX_CONSECUTIVAS_COPIA):
    palabras = norm(texto).split()
    n = max_consecutivas + 1
    indice = set()
    for i in range(0, max(0, len(palabras) - n + 1)):
        indice.add(hash(tuple(palabras[i:i + n])))
    return indice


def es_copia_literal(afirmacion: str, texto_libro: str = None,
                     max_consecutivas: int = MAX_CONSECUTIVAS_COPIA,
                     indice=None) -> bool:
    if indice is None:
        if texto_libro is None:
            raise ValueError("falta texto_libro o indice")
        indice = construir_indice_copia(texto_libro, max_consecutivas)
    palabras = norm(afirmacion).split()
    n = max_consecutivas + 1
    for i in range(0, max(0, len(palabras) - n + 1)):
        if hash(tuple(palabras[i:i + n])) in indice:
            return True
    return False


def _nucleo(texto: str, max_palabras: int = MAX_PALABRAS_NUCLEO) -> str:
    palabras = limpiar_texto(texto).split()
    return " ".join(palabras[:max_palabras]).strip(" .,;:")


def _cita(texto: str, max_palabras: int = MAX_PALABRAS_CITA) -> str:
    palabras = limpiar_texto(texto).split()
    return " ".join(palabras[:max_palabras]).strip(" .,;:")


def facetas_de(seccion: dict):
    if seccion["orientacion"] == "derecho":
        return ["significado_general", "derecha_invertida"]
    return ["derecha_invertida", "luz_sombra"]


def evidencias_deterministas(secciones, meta):
    salida = []
    for s in secciones:
        if not s.get("entidad_id"):
            continue
        for faceta in facetas_de(s):
            salida.append({
                "entidad_id": s["entidad_id"],
                "faceta": faceta,
                "fuente_id": s["fuente_id"],
                "dominio": s["fuente_id"],
                "idioma": s["idioma"],
                "periodo": PERIODO,
                "calidad": CALIDAD,
                "tipo": "libro",
                "hash_seccion": juez_hash(s),
                "orientacion": s["orientacion"],
            })
    return salida


def juez_hash(seccion: dict) -> str:
    clave = "%s|%s|%s" % (seccion["id_libro"], seccion["seccion"],
                         seccion["texto"])
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


def afirmaciones_de(seccion: dict, indice, titulo: str):
    nucleo = _nucleo(seccion["texto"])
    if not nucleo:
        return []
    carta = nombre_carta(seccion["rango"], seccion["palo"])
    orientacion = "al derecho" if seccion["orientacion"] == "derecho" \
        else "al revés"
    frase = ("En «%s», %s %s se asocia con estas claves: %s."
             % (titulo, carta, orientacion, nucleo))
    cita = _cita(seccion["texto"])
    if es_copia_literal(frase, indice=indice):
        frase = ("%s %s: claves recogidas en «%s»." %
                 (carta, orientacion, titulo))
    salida = []
    for faceta in facetas_de(seccion):
        salida.append({
            "entidad_id": seccion["entidad_id"],
            "faceta": faceta,
            "fuente_id": seccion["fuente_id"],
            "dominio": seccion["fuente_id"],
            "periodo": PERIODO,
            "calidad": CALIDAD,
            "afirmacion": frase,
            "cita_original": cita,
            "contradice_kb": False,
            "orientacion": seccion["orientacion"],
        })
    return salida


def generar_determinista(work_dir: str, verboso=True):
    """Evidencias y afirmaciones sin LLM, con puerta anti-copia."""
    work_dir = validar_work_dir(work_dir)
    meta = {libro["id"]: libro for libro in LIBROS.values()}
    todas_ev, todas_af, informes = [], [], {}
    for libro in LIBROS.values():
        ruta_sec = os.path.join(work_dir, "secciones", libro["id"] + ".jsonl")
        if not os.path.exists(ruta_sec):
            raise FileNotFoundError(ruta_sec)
        secciones = _leer_jsonl(ruta_sec)
        texto_libro = open(ruta_crudo(work_dir, libro), encoding="utf-8",
                           errors="replace").read()
        indice = construir_indice_copia(texto_libro)
        ev = evidencias_deterministas(secciones, meta)
        af = []
        rechazadas = 0
        for s in secciones:
            if not s.get("entidad_id"):
                continue
            for item in afirmaciones_de(s, indice, libro["titulo"]):
                if es_copia_literal(item["afirmacion"], indice=indice) or \
                        len(item["afirmacion"].split()) > 40:
                    rechazadas += 1
                    continue
                af.append(item)
        todas_ev.extend(ev)
        todas_af.extend(af)
        informes[libro["id"]] = {
            "secciones": len(secciones),
            "con_entidad": sum(1 for s in secciones if s["entidad_id"]),
            "evidencias": len(ev),
            "afirmaciones": len(af),
            "afirmaciones_rechazadas": rechazadas,
        }
        if verboso:
            print("%s: %d evidencias, %d afirmaciones (%d rechazadas)"
                  % (libro["id"], len(ev), len(af), rechazadas))
    _escribir_jsonl(os.path.join(work_dir, "evidencias",
                                 "evidencias_baraja.jsonl"), todas_ev)
    _escribir_jsonl(os.path.join(work_dir, "afirmaciones",
                                 "afirmaciones_baraja.jsonl"), todas_af)
    with open(os.path.join(work_dir, "resumenes", "determinista.json"), "w",
              encoding="utf-8") as fh:
        json.dump(informes, fh, ensure_ascii=False, indent=2)
    return todas_ev, todas_af


def _leer_jsonl(ruta: str):
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


# ---------------------------------------------------------------------------
# Informe de cobertura y delta sobre v3
# ---------------------------------------------------------------------------

def informe_cobertura(evidencias, catalogo=None):
    catalogo = catalogo or cobertura.entidades()
    por_carta = {}
    for ent in sorted(catalogo, key=lambda e: e["entidad_id"]):
        if ent.get("familia") != "baraja_espanola":
            continue
        por_carta[ent["entidad_id"]] = {"nombre": ent.get("nombre"),
                                        "derecho": [], "reves": []}
    for ev in evidencias:
        eid = ev.get("entidad_id")
        if eid not in por_carta:
            continue
        orientacion = ev.get("orientacion")
        if orientacion in ("derecho", "reves"):
            fuente = ev.get("fuente_id")
            if fuente and fuente not in por_carta[eid][orientacion]:
                por_carta[eid][orientacion].append(fuente)
    faltan = []
    for eid, datos in por_carta.items():
        for orientacion in ("derecho", "reves"):
            if not datos[orientacion]:
                faltan.append("%s:%s" % (eid, orientacion))
    return {
        "cartas": len(por_carta),
        "celdas_orientacion": len(por_carta) * 2,
        "cubiertas_derecho": sum(1 for d in por_carta.values()
                                 if d["derecho"]),
        "cubiertas_reves": sum(1 for d in por_carta.values() if d["reves"]),
        "faltan": faltan,
        "detalle": por_carta,
    }


def delta_v3(evidencias_nuevas, rutas_v3=None):
    rutas_v3 = rutas_v3 or [
        "/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl",
        "/Users/angelgonzalez/fase0/libros_limpio/evidencias_limpias.jsonl",
    ]
    base = []
    for ruta in rutas_v3:
        if os.path.exists(ruta):
            base.extend(_leer_jsonl(ruta))
    antes = cobertura.calcular_cobertura(base)
    despues = cobertura.calcular_cobertura(base + evidencias_nuevas)
    return {
        "evidencias_base": len(base),
        "antes": _solo_baraja(antes),
        "despues": _solo_baraja(despues),
    }


def _solo_baraja(res):
    baraja = [c for c in res.get("celdas", [])
              if str(c.get("entidad_id", "")).startswith("naipe-")]
    return {"total": len(baraja),
            "completas": sum(1 for c in baraja if c.get("completa")),
            "celdas": baraja}


def medir(work_dir: str = WORK_DIR_DEFECTO):
    import juez
    work_dir = validar_work_dir(work_dir)
    resumen = {}
    for libro in LIBROS.values():
        secciones, metodo, incidencias = segmentar_libro(libro, work_dir)
        con = [s for s in secciones if s["entidad_id"]]
        resumen[libro["id"]] = {
            "secciones": len(secciones), "con_entidad": len(con),
            "cartas": len({(s["palo"], s["rango"]) for s in secciones}),
            "incidencias": incidencias,
            "llamadas_estimadas": sum(
                len(juez.candidatos_seccion(s)) * 1 for s in con),
        }
    return resumen


# ---------------------------------------------------------------------------
# Fase LLM (documentada, no ejecutada en T129)
# ---------------------------------------------------------------------------

def construir_cliente_endpoints(endpoints_csv, timeout=TIMEOUT, acotar=True):
    """Cliente round-robin sobre nodo1 y nodo2 (autorizado el 23/10); rechaza otros hosts."""
    import libros_pipeline
    import llm_client
    endpoints = [e.strip() for e in (endpoints_csv or "").split(",") if e.strip()]
    if not endpoints:
        endpoints = [e.strip() for e in ENDPOINTS_POR_DEFECTO.split(",")]
    for url in endpoints:
        if urlparse(url).hostname not in HOSTS_LOCALES_PERMITIDOS:
            raise ValueError("endpoint no permitido (solo nodo1 y nodo2): %r" % url)
    base = llm_client.LLMClient(endpoints=endpoints, timeout=timeout)
    return libros_pipeline._ClienteAcotado(base) if acotar else base


def _meta_juez(work_dir):
    ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    meta = {}
    for fila in _leer_jsonl(ruta):
        meta[fila["id"]] = fila
    return meta


def procesar_juez(work_dir, endpoints, workers=MAX_WORKERS, limite=None):
    import juez
    work_dir = validar_work_dir(work_dir)
    cliente = construir_cliente_endpoints(endpoints)
    meta = _meta_juez(work_dir)
    secciones = []
    for libro in LIBROS.values():
        secciones.extend(_leer_jsonl(os.path.join(
            work_dir, "secciones", libro["id"] + ".jsonl")))
    return juez.procesar_secciones(secciones, cliente,
                                   os.path.join(work_dir, "evidencias"),
                                   meta=meta, workers=workers,
                                   limite=limite)


def procesar_afirmaciones(work_dir, endpoints, workers=MAX_WORKERS,
                          limite=None):
    """Etapa LLM futura: evidencias del juez -> afirmaciones."""
    work_dir = validar_work_dir(work_dir)
    cliente = construir_cliente_endpoints(endpoints, acotar=False)
    indice = afirmaciones_libros.IndiceLibros(
        os.path.join(work_dir, "secciones"))
    evidencias = _leer_jsonl(os.path.join(work_dir, "evidencias",
                                          "evidencias.jsonl"))
    out = os.path.join(work_dir, "afirmaciones", "afirmaciones_llm.jsonl")
    hechos = set()
    if os.path.exists(out):
        for fila in _leer_jsonl(out):
            hechos.add((fila.get("hash_seccion"), fila.get("entidad_id"),
                        fila.get("faceta")))
    with open(out, "a", encoding="utf-8") as fh:
        for ev in evidencias[:limite] if limite else evidencias:
            clave = (ev.get("hash_seccion"), ev.get("entidad_id"),
                     ev.get("faceta"))
            if clave in hechos:
                continue
            seccion = indice.seccion(ev["fuente_id"], ev["hash_seccion"])
            if not seccion:
                continue
            import consenso_kb
            corr = consenso_kb.cargar_correspondencias()
            resultado = afirmaciones_libros.extraer_afirmaciones_libros(
                cliente, ev["entidad_id"], ev["faceta"], seccion["texto"],
                ev.get("idioma", "es"), corr)
            for item in resultado.get("afirmaciones", []):
                registro = afirmaciones_libros.registro_afirmacion_libros(
                    ev, item)
                fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default=WORK_DIR_DEFECTO)
    ap.add_argument("--preparar", action="store_true")
    ap.add_argument("--segmentar", action="store_true")
    ap.add_argument("--determinista", action="store_true",
                    help="evidencias y afirmaciones sin LLM")
    ap.add_argument("--cobertura", action="store_true",
                    help="informe de orientaciones y delta sobre v3")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--juez", action="store_true")
    ap.add_argument("--afirmaciones", action="store_true")
    ap.add_argument("--endpoints", default=ENDPOINTS_POR_DEFECTO)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args(argv)

    work_dir = validar_work_dir(args.work_dir)
    if args.preparar:
        preparar(work_dir)
    if args.segmentar:
        segmentar_a_disco(work_dir)
    if args.cobertura:
        ev = _leer_jsonl(os.path.join(work_dir, "evidencias",
                                      "evidencias_baraja.jsonl"))
        res = {"informe": informe_cobertura(ev), "delta": delta_v3(ev)}
        ruta = os.path.join(work_dir, "resumenes", "cobertura.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
        print(json.dumps(res["informe"], ensure_ascii=False, indent=2))
        print("delta:", res["delta"]["antes"], "->",
              res["delta"]["despues"])
        return 0
    if args.dry_run or (not args.juez and not args.afirmaciones
                        and not args.determinista):
        resumen = medir(work_dir)
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        return 0
    if args.determinista:
        generar_determinista(work_dir)
    if args.juez:
        print(procesar_juez(work_dir, args.endpoints, args.workers,
                            args.limite))
    if args.afirmaciones:
        print(procesar_afirmaciones(work_dir, args.endpoints, args.workers,
                                    args.limite))
    return 0


if __name__ == "__main__":
    sys.exit(main())
