"""Libros comprados en inglés (Pollack, Greer) hacia evidencias (T115).

Reutiliza las etapas de `libros_pipeline`/`juez` sobre un work-dir NUEVO
(`/Users/angelgonzalez/fase0/libros_comprados_en`), nunca sobre el real
(`/Users/angelgonzalez/fase0/libros`). Los dos libros son compras del usuario
para uso interno (con copyright); los PDF no se copian al repo y las
evidencias conservan el idioma original (`en`).

Segmentación propia (los libros no siguen el formato de los clásicos PD):

- Pollack, *Seventy-Eight Degrees of Wisdom* (1980): los 22 arcanos mayores
  por capítulo (título en línea suelta, en orden Rider) y 4 capítulos de
  palos del arcana menor. Los menores no traen título por carta: se segmenta
  por capítulo de palo y la detección de candidatos del juez trabaja sobre
  el cuerpo. El prelio, el índice, la introducción y la parte de lecturas
  no se segmentan como conocimiento de cartas.
- Greer, *Tarot for Your Self* (1984): prefacio + introducción, 12
  capítulos (cortados por encabezados de técnica/tirada, prefijados
  «Técnica: » para que el juez no los confunda con significado de carta)
  y el apéndice de 78 cartas, una sección por carta con nombre canónico.

El juez apunta SIEMPRE a nodo2 (`http://10.0.0.4:8000/v1`); nodo1
(10.0.0.3) está reservado por el usuario. Con T114 vivo se usa 1 worker.
Reanudable por hash de sección, como `clasicos_pd_a_evidencias`.

Tras las afirmaciones (T38) se aplica la puerta anti-copia: cualquier
afirmación o cita que comparta más de `MAX_RUN_COPIA` (25) palabras
consecutivas con el libro se rechaza a
`afirmaciones/rechazadas_copia.jsonl`.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter

import afirmaciones_libros
import cobertura
import juez
import libros_limpiar
import libros_pipeline
import libros_segmentar
import llm_client
from urllib.parse import urlparse

WORK_DIR_REAL = "/Users/angelgonzalez/fase0/libros"
WORK_DIR_DEFAULT = "/Users/angelgonzalez/fase0/libros_comprados_en"
PDF_DIR = "/Users/angelgonzalez/fase0/libros_comprados"
META_NOMBRE = "fuentes_libros_comprados_en.jsonl"
PROCEDENCIA = "comprado por el usuario, uso interno, copyright"
NODO1_RESERVADO = "10.0.0.3"
ENDPOINT_NODO2 = "http://10.0.0.4:8000/v1"
# Hosts locales permitidos para el LLM: nodo1 y nodo2 (autorizado por el usuario el 23/10).
HOSTS_LOCALES_PERMITIDOS = ("10.0.0.3", "10.0.0.4")
ENDPOINTS_POR_DEFECTO = "http://10.0.0.3:8000/v1,http://10.0.0.4:8000/v1"
TIMEOUT_LIBRO = 90.0
MIN_CRUDO_BYTES = 1024
MIN_SECCION = 400
MAX_SECCION = 12000
SOLAPE_CHARS = 300
MAX_RUN_COPIA = 25
PDFTOTEXT = "/opt/homebrew/bin/pdftotext"

LIBROS = (
    {"id": "pollack-78-degrees",
     "titulo": "Seventy-Eight Degrees of Wisdom",
     "autor": "Rachel Pollack", "anio": 1980, "idioma": "en",
     "familia": "tarot",
     "pdf": "Pollack - 78 Degrees of Wisdom (1980).pdf",
     "crudo": "pollack_78_degrees.txt"},
    {"id": "greer-tarot-your-self",
     "titulo": "Tarot for Your Self",
     "autor": "Mary K. Greer", "anio": 1984, "idioma": "en",
     "familia": "tarot",
     "pdf": "Greer - Tarot for Your Self (1984).pdf",
     "crudo": "greer_tarot_your_self.txt"},
)

# Nombres canónicos en inglés de los mayores (indice = numero Rider - 1).
MAYORES_EN = libros_segmentar.NOMBRES_MAYORES_EN

# Titulos de palo para los capitulos menores de Pollack (orden en el libro).
PALOS_POLLACK = ("Wands", "Cups", "Swords", "Pentacles")

# Palabras que parecen cabecera corrida pero son estructura util del libro.
POLLACK_KEEP = frozenset(
    {"THE MINOR ARCANA", "REVERSED", "READINGS"}
    | {t.upper() for t in MAYORES_EN}
)

# Encabezados de tecnica/tirada de Greer (caja alta obligatoria en la clave).
TECH_RE = re.compile(
    r"\b(Spread|Permutation|Mandala|Exercise|Ritual|Visualization|"
    r"Meditation|Wards?|Pendulum|Purification|Infusing|Cross|Journal)\b")

TERMINALES = ".?!:»\"”’')"


class LibroSinFuenteError(Exception):
    """Falta el PDF de origen o el crudo no se pudo extraer."""


def validar_work_dir(work_dir):
    """Rechaza el work-dir real: aqui nunca se escribe en la tuberia madre."""
    real = os.path.realpath(work_dir)
    raiz_real = os.path.realpath(WORK_DIR_REAL)
    if real == raiz_real or real.startswith(raiz_real + os.sep):
        raise ValueError(
            "work-dir %r apunta al directorio real de la tuberia; usa uno "
            "aparte (por defecto: %s)" % (work_dir, WORK_DIR_DEFAULT))
    return real


def construir_cliente_endpoints(endpoints_csv, timeout=TIMEOUT_LIBRO):
    """Cliente del juez fijado a los endpoints indicados, con reintentos bajos.

    Rechaza nodo1 (10.0.0.3), reservado por el usuario: el LLM de esta
    pista solo puede correr contra nodo2.
    """
    endpoints = [e.strip() for e in (endpoints_csv or "").split(",") if e.strip()]
    if not endpoints:
        endpoints = [e.strip() for e in ENDPOINTS_POR_DEFECTO.split(",")]
    for url in endpoints:
        if urlparse(url).hostname not in HOSTS_LOCALES_PERMITIDOS:
            raise ValueError(
                "endpoint no permitido (solo nodo1 y nodo2): %r" % url)
    base = llm_client.LLMClient(endpoints=endpoints, timeout=timeout)
    return libros_pipeline._ClienteAcotado(base)


class _ClienteAfirmaciones:
    """Adaptador que reenvia ``chat`` y ``chat_json`` con reintentos bajos.

    ``libros_pipeline._ClienteAcotado`` solo define ``chat``; el extractor de
    afirmaciones (T38) llama a ``chat_json``, que no existia en el envoltorio
    y hacia fallar todas las evidencias con ``estado=error``. Aqui se
    reenvian ambos metodos acotando los reintentos: ``max_reintentos`` en
    ``chat`` e ``intentos`` en ``chat_json``.
    """

    def __init__(self, cliente, reintentos=2):
        self._cliente = cliente
        self._reintentos = reintentos

    def chat(self, sistema, usuario, **kwargs):
        kwargs.setdefault("max_reintentos", self._reintentos)
        return self._cliente.chat(sistema, usuario, **kwargs)

    def chat_json(self, sistema, usuario, validar, **kwargs):
        kwargs.setdefault("intentos", self._reintentos)
        return self._cliente.chat_json(sistema, usuario, validar, **kwargs)


def ruta_crudo(work_dir, libro):
    return os.path.join(work_dir, "crudo", libro["crudo"])


def extraer_crudo(libro, work_dir, forzar=False):
    """Extrae el crudo con pdftotext -layout si aun no existe (idempotente)."""
    destino = ruta_crudo(work_dir, libro)
    if (not forzar and os.path.isfile(destino)
            and os.path.getsize(destino) >= MIN_CRUDO_BYTES):
        return destino
    origen = os.path.join(PDF_DIR, libro["pdf"])
    if not os.path.isfile(origen):
        raise LibroSinFuenteError(
            "falta el PDF de %s (esperado en %s)" % (libro["id"], origen))
    if not os.path.isfile(PDFTOTEXT):
        raise LibroSinFuenteError("pdftotext no esta en %s" % PDFTOTEXT)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    subprocess.run([PDFTOTEXT, "-layout", origen, destino], check=True)
    if (not os.path.isfile(destino)
            or os.path.getsize(destino) < MIN_CRUDO_BYTES):
        raise LibroSinFuenteError(
            "la extraccion de %s no produjo texto util" % libro["id"])
    return destino


def preparar_work_dir(work_dir, libros):
    """Crea la estructura, extrae los crudos y escribe el meta del juez."""
    for sub in ("crudo", "limpio", "secciones", "evidencias", "knowledge",
               "resumenes", "afirmaciones"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    for libro in libros:
        extraer_crudo(libro, work_dir)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        for c in LIBROS:
            fh.write(json.dumps({"id": c["id"], "anio": c["anio"],
                                "idioma": c["idioma"], "titulo": c["titulo"],
                                "autor": c["autor"],
                                "procedencia": PROCEDENCIA},
                               ensure_ascii=False) + "\n")


def _sin_ff(linea):
    return linea.replace("\x0c", "").strip()


def _unir_inicial(texto):
    """Recompone titulos OCR partidos: 'G    etting' -> 'Getting'."""
    return re.sub(r"^(\w)\s{2,}(\w.*)$", r"\1\2", texto)


def _canonico_mayor(titulo):
    bajo = re.sub(r"^the\s+", "", titulo.lower().strip())
    for nombre in MAYORES_EN:
        if re.sub(r"^the\s+", "", nombre.lower()) == bajo:
            return nombre
    return None


def _nombre_canonico(entidad_id):
    """Nombre en ingles canónico a partir del id de carta del KB."""
    if entidad_id.startswith("tarot-mayor-"):
        num = int(entidad_id.rsplit("-", 1)[1])
        return MAYORES_EN[num - 1]
    partes = entidad_id.split("-")
    if len(partes) == 3 and partes[0] == "tarot":
        palo_clave, num = partes[1], int(partes[2])
        display = None
        for _, (clave, disp) in libros_segmentar.PALOS_EN.items():
            if clave == palo_clave:
                display = disp
                break
        rango = None
        for nombre, n in libros_segmentar.RANGOS_EN.items():
            if n == num:
                rango = nombre
                break
        if display and rango:
            return "%s of %s" % (rango, display)
    return None


def _mapa_titulo_greer(titulo):
    """id de carta desde un titulo de apendice (con dobles formas Thoth)."""
    cands = [titulo]
    if "/" in titulo:
        for parte in titulo.split("/"):
            parte = parte.strip()
            cands += [parte, "The " + parte.lower(), parte.lower(),
                      re.sub(r"^THE\s+", "", parte)]
    cands += ["The " + titulo.lower(), titulo.lower(),
              re.sub(r"^THE\s+", "", titulo)]
    for c in cands:
        cid = libros_segmentar.carta_de_titulo(c, "tarot")
        if cid:
            return cid
    return None


# --------------------------------------------------------------------------
# Pollack
# --------------------------------------------------------------------------

def _es_cabecera_pollack(texto):
    """Cabecera corrida de Pollack: todo mayusculas (con numero de pagina)."""
    if not texto or texto in POLLACK_KEEP:
        return False
    alfa = re.sub(r"[^A-Za-z]", "", texto)
    if len(alfa) < 2:
        return False
    return alfa == alfa.upper()


def _quitar_cabeceras_pollack(lineas):
    salida = []
    for linea in lineas:
        t = _sin_ff(linea)
        if t and _es_cabecera_pollack(t):
            salida.append("")
        else:
            salida.append(linea)
    return salida


def _indices_pollack(lineas):
    """Localiza titulos de mayores, ancla de menores y fin de capitulos."""
    norm = lambda s: re.sub(r"^the\s+", "", s.lower().strip())
    mayores = []
    prev = 0
    for titulo in MAYORES_EN:
        tnorm = norm(titulo)
        idx = None
        for i in range(prev, len(lineas)):
            if norm(_sin_ff(lineas[i])) == tnorm:
                idx = i
                break
        if idx is None:
            raise LibroSinFuenteError(
                "no se encontro el titulo de %r en Pollack" % titulo)
        mayores.append((titulo, idx))
        prev = idx + 1
    ancla = None
    for i in range(mayores[-1][1], len(lineas)):
        if _sin_ff(lineas[i]) == "THE MINOR ARCANA":
            ancla = i
            break
    if ancla is None:
        raise LibroSinFuenteError("no se encontro THE MINOR ARCANA en Pollack")
    # Wands no trae linea de titulo: arranca tras THE MINOR ARCANA. Los demas
    # palos si: 'Cups', 'Swords', 'Pentacles' en linea suelta.
    palos = {"Wands": ancla + 1}
    cursor = ancla + 1
    for palo in ("Cups", "Swords", "Pentacles"):
        idx = None
        for i in range(cursor, len(lineas)):
            if _sin_ff(lineas[i]) == palo:
                idx = i
                break
        if idx is None:
            raise LibroSinFuenteError(
                "no se encontro el capitulo de %s en Pollack" % palo)
        palos[palo] = idx
        cursor = idx + 1
    lecturas = None
    for i in range(palos["Pentacles"] + 1, len(lineas)):
        if _sin_ff(lineas[i]) == "READINGS":
            lecturas = i
            break
    if lecturas is None:
        raise LibroSinFuenteError("no se encontro READINGS tras Pentacles")
    colofon = None
    fin_patron = re.compile(
        r"^(WISDOM$|A BOOK OF TAROT|First published|©|British Library)")
    for i in range(mayores[-1][1] + 1, ancla):
        if fin_patron.match(_sin_ff(lineas[i])):
            colofon = i
            break
    if colofon is None:
        raise LibroSinFuenteError("no se encontro el colofon tras The World")
    return mayores, ancla, palos, lecturas, colofon


def trozos_pollack(texto):
    """Trozos crudos (titulo, lineas) de Pollack, sin limpiar aun."""
    lineas = texto.splitlines()
    mayores, ancla, palos, lecturas, colofon = _indices_pollack(lineas)
    trozos = []
    for k, (titulo, idx) in enumerate(mayores):
        fin = mayores[k + 1][1] if k + 1 < len(mayores) else colofon
        trozos.append((titulo, lineas[idx:fin]))
    orden = ["Wands", "Cups", "Swords", "Pentacles"]
    for palo in orden:
        inicio = ancla + 1 if palo == "Wands" else palos[palo]
        if palo == "Wands":
            fin = palos["Cups"]
        elif palo == "Cups":
            fin = palos["Swords"]
        elif palo == "Swords":
            fin = palos["Pentacles"]
        else:
            fin = lecturas
        titulo = "%s (Arcana Menor)" % palo
        trozos.append((titulo, lineas[inicio:fin]))
    return trozos


# --------------------------------------------------------------------------
# Greer
# --------------------------------------------------------------------------

def _es_cabecera_greer(texto):
    if not texto:
        return False
    if re.match(r"^[^\[\]]{1,70}\]\s*\d{1,3}\s*\[?$", texto):
        return True
    if re.match(r"^\]?\s*\d{1,3}\s*\[$", texto):
        return True
    if texto in ("]", "[", "] ["):
        return True
    return False


def _quitar_cabeceras_greer(lineas):
    salida = []
    for linea in lineas:
        t = _sin_ff(linea)
        if t and _es_cabecera_greer(t):
            salida.append("")
        else:
            salida.append(linea)
    return salida


def _titulo_capitulo(lineas, marker_idx):
    j = marker_idx + 1
    while j < len(lineas) and not _sin_ff(lineas[j]):
        j += 1
    if j >= len(lineas):
        return ""
    return re.sub(r"\s+", " ", _unir_inicial(_sin_ff(lineas[j])))


def _es_encabezado_tecnica(lineas, i):
    t = _sin_ff(lineas[i])
    if not (4 <= len(t) <= 70):
        return False
    if t.isupper():
        return False
    if not (t[0].isupper() or t[0] == "#"):
        return False
    if re.search(r"\d{1,4}\s*$", t):
        return False
    if not TECH_RE.search(t):
        return False
    prev = lineas[i - 1] if i > 0 else ""
    prev_t = _sin_ff(prev)
    if prev_t and not prev_t.endswith(TERMINALES):
        return False
    nxt = None
    for k in range(i + 1, min(i + 4, len(lineas))):
        if _sin_ff(lineas[k]):
            nxt = _sin_ff(lineas[k])
            break
    if nxt is not None and not (nxt[0].isupper() or nxt[0] == "#"):
        return False
    return True


def trozos_greer(texto):
    """Trozos crudos (titulo, lineas) de Greer, sin limpiar aun."""
    lineas = texto.splitlines()
    markers = []
    for i, linea in enumerate(lineas):
        m = re.match(r"^\s*\]\s*Chapter\s+(\d+)\s*\[", linea)
        if m:
            markers.append((i, int(m.group(1))))
    if len(markers) < 12:
        raise LibroSinFuenteError(
            "se esperaban 12 marcadores de capitulo en Greer, hay %d"
            % len(markers))
    apendice = None
    for i in range(markers[-1][0], len(lineas)):
        if _sin_ff(lineas[i]) == "THE FOOL":
            apendice = i
            break
    if apendice is None:
        raise LibroSinFuenteError("no se encontro el apendice (THE FOOL)")
    tabla = None
    for i in range(apendice + 1, len(lineas)):
        if "TABLE OF CORRESPONDENCES" in lineas[i]:
            tabla = i
            break
    if tabla is None:
        tabla = len(lineas)
    trozos = []
    # Prefacio + introduccion: desde 'P reface' hasta el capitulo 1.
    prefacio = None
    for i in range(markers[0][0]):
        t = _sin_ff(lineas[i])
        if re.match(r"^[Pp]\s*reface$", t):
            prefacio = i
            break
    if prefacio is not None:
        trozos.append(("Prefacio e introduccion", lineas[prefacio:markers[0][0]]))
    # Capitulos 1..12, cortados por encabezados de tecnica.
    for k, (idx, num) in enumerate(markers):
        fin = markers[k + 1][0] if k + 1 < len(markers) else apendice
        cap_lines = lineas[idx:fin]
        titulo_cap = "Capitulo %d: %s" % (num, _titulo_capitulo(lineas, idx))
        partes = []
        actual_titulo = titulo_cap
        buffer = []
        no_blank = 0
        for j, linea in enumerate(cap_lines):
            t = _sin_ff(linea)
            if t:
                no_blank += 1
            if no_blank > 3 and _es_encabezado_tecnica(cap_lines, j):
                if buffer and "".join(buffer).strip():
                    partes.append((actual_titulo, list(buffer)))
                actual_titulo = "Tecnica: %s" % t
                buffer = [linea]
            else:
                buffer.append(linea)
        if buffer and "".join(buffer).strip():
            partes.append((actual_titulo, buffer))
        trozos.extend(partes)
    # Apendice: una seccion por carta con nombre canonico.
    card_idx = []
    for i in range(apendice, tabla):
        t = _sin_ff(lineas[i])
        if not t or len(t) > 40 or not t.isupper():
            continue
        cid = _mapa_titulo_greer(t)
        if cid:
            card_idx.append((i, cid))
    for k, (idx, cid) in enumerate(card_idx):
        fin = card_idx[k + 1][0] if k + 1 < len(card_idx) else tabla
        nombre = _nombre_canonico(cid) or _sin_ff(lineas[idx])
        trozos.append((nombre, lineas[idx:fin]))
    return trozos


# --------------------------------------------------------------------------
# Etapas comunes
# --------------------------------------------------------------------------

def _trocear(texto, max_chars=MAX_SECCION, solape=SOLAPE_CHARS):
    """Corta por fronteras de linea con solape en caracteres."""
    if len(texto) <= max_chars:
        return [texto]
    trozos = []
    lineas = texto.splitlines()
    inicio = 0
    while inicio < len(lineas):
        acumulado = 0
        fin = inicio
        while fin < len(lineas) and acumulado + len(lineas[fin]) + 1 <= max_chars:
            acumulado += len(lineas[fin]) + 1
            fin += 1
        if fin == inicio:
            # Una sola linea mas larga que el max: se incluye entera.
            fin += 1
        trozo = "\n".join(lineas[inicio:fin])
        trozos.append(trozo)
        if fin >= len(lineas):
            break
        # nuevo inicio: retroceder el solape desde fin
        nuevo = fin
        retro_acum = 0
        while nuevo > inicio + 1 and retro_acum < solape:
            nuevo -= 1
            retro_acum += len(lineas[nuevo]) + 1
        inicio = nuevo
    return trozos


def limpiar_trozo(texto, idioma, cabecera_quita):
    """Quita cabeceras propias y pasa por libros_limpiar."""
    lineas = cabecera_quita(texto.splitlines())
    pre = "\n".join(lineas)
    limpio, informe = libros_limpiar.limpiar(pre, idioma)
    return limpio, informe


def segmentar_libro(libro, texto_crudo):
    """Devuelve las secciones (dicts listos para el jsonl) de un libro."""
    if libro["id"] == "pollack-78-degrees":
        trozos = trozos_pollack(texto_crudo)
        quitar = _quitar_cabeceras_pollack
    elif libro["id"] == "greer-tarot-your-self":
        trozos = trozos_greer(texto_crudo)
        quitar = _quitar_cabeceras_greer
    else:
        raise LibroSinFuenteError("libro desconocido: %s" % libro["id"])
    secciones = []
    n = 0
    for titulo, lineas in trozos:
        crudo = "\n".join(lineas)
        limpio, _informe = limpiar_trozo(crudo, libro["idioma"], quitar)
        if len(limpio) < MIN_SECCION:
            continue
        partes = _trocear(limpio)
        for k, parte in enumerate(partes):
            n += 1
            titulo_sec = titulo if len(partes) == 1 else "%s (parte %d)" % (
                titulo, k + 1)
            secciones.append({
                "seccion": n,
                "titulo": titulo_sec,
                "texto": parte,
                "chars": len(parte),
                "id_libro": libro["id"],
                "posicion": k + 1,
            })
    return secciones


def ruta_limpio(work_dir, libro):
    return os.path.join(work_dir, "limpio", libro["id"] + ".txt")


def etapa_limpieza_segmentacion(libro, work_dir, forzar=False):
    """Escribe limpio/<id>.txt y secciones/<id>.jsonl (idempotente)."""
    crudo = ruta_crudo(work_dir, libro)
    with open(crudo, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    if libro["id"] == "pollack-78-degrees":
        quitar = _quitar_cabeceras_pollack
    else:
        quitar = _quitar_cabeceras_greer
    ruta_limp = ruta_limpio(work_dir, libro)
    if forzar or not os.path.isfile(ruta_limp):
        limpio, informe = limpiar_trozo(texto, libro["idioma"], quitar)
        with open(ruta_limp, "w", encoding="utf-8") as fh:
            fh.write(limpio)
    secciones = segmentar_libro(libro, texto)
    ruta_sec = os.path.join(work_dir, "secciones", libro["id"] + ".jsonl")
    with open(ruta_sec, "w", encoding="utf-8") as fh:
        for s in secciones:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    return len(secciones)


def medir_libro(libro, work_dir):
    """Segmenta en memoria y cuenta secciones y llamadas (sin LLM ni disco)."""
    ruta = ruta_crudo(work_dir, libro)
    if not os.path.isfile(ruta) or os.path.getsize(ruta) < MIN_CRUDO_BYTES:
        raise LibroSinFuenteError("falta el crudo de %s" % libro["id"])
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    secciones = segmentar_libro(libro, texto)
    con_candidatos = sum(1 for s in secciones if juez.candidatos_seccion(s))
    return {"secciones": len(secciones), "con_candidatos": con_candidatos,
            "llamadas_estimadas": con_candidatos}


def resumen_de_evidencias(work_dir, libro_id):
    """Cuenta evidencias del libro: total, calidad >= 3, por familia/entidad."""
    ruta = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    familias = {e["entidad_id"]: e["familia"] for e in cobertura.entidades()}
    total = aceptadas = 0
    por_familia = {}
    por_entidad = {}
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    ev = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if ev.get("fuente_id") != libro_id:
                    continue
                total += 1
                if (ev.get("calidad") or 0) >= 3:
                    aceptadas += 1
                fam = familias.get(ev.get("entidad_id"), "desconocida")
                por_familia[fam] = por_familia.get(fam, 0) + 1
                ent = ev.get("entidad_id") or "?"
                por_entidad[ent] = por_entidad.get(ent, 0) + 1
    return {"evidencias": total, "aceptadas_calidad_ge_3": aceptadas,
            "evidencias_por_familia": por_familia,
            "evidencias_por_entidad": por_entidad}


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
    """Quita de juicios.jsonl los juicios tipo=error para que se reintenten."""
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


def etapa_juez(libro, work_dir, max_llamadas=0, workers=1,
              timeout=TIMEOUT_LIBRO, simulado=False, cliente=None):
    """Juzga las secciones del libro (reanudable por hash)."""
    ctx = {"pausa": 0.0, "workers": workers, "simulado": simulado,
           "cliente": cliente,
           "knowledge_dir": os.path.join(work_dir, "knowledge"),
           "timeout": timeout, "lote_juez": None}
    secciones = libros_pipeline.secciones_de_libros([libro], work_dir)
    if not secciones:
        print("%s: sin secciones que juzgar" % libro["id"], file=sys.stderr)
        return {"id": libro["id"], "secciones": 0, "juzgadas": 0,
                "llamadas": 0, "evidencias": 0, "reaprovechadas": 0,
                "sin_candidatos": 0, "error": 0}
    purgados = purgar_errores_juez(work_dir)
    if purgados:
        print("%s: %d juicios-error purgados para reintentar"
              % (libro["id"], purgados), flush=True)
    cliente_juez = libros_pipeline._cliente_juez(ctx)
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if max_llamadas and max_llamadas > 0:
        hechos = _hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                     if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:max_llamadas]
    stats = juez.procesar_secciones(a_procesar, cliente_juez,
                                    os.path.join(work_dir, "evidencias"),
                                    meta=meta, workers=workers)
    resumen = {"id": libro["id"], "secciones": len(secciones),
               "procesadas_esta_pasada": len(a_procesar)}
    resumen.update(stats)
    resumen.update(resumen_de_evidencias(work_dir, libro["id"]))
    ruta_resumen = os.path.join(work_dir, "resumenes", libro["id"] + ".json")
    with open(ruta_resumen, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return resumen


# --------------------------------------------------------------------------
# Afirmaciones y puerta anti-copia
# --------------------------------------------------------------------------

def _palabras(texto):
    base = unicodedata.normalize("NFKD", (texto or "").lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", base).split()


def es_copia(texto, referencia, max_run=MAX_RUN_COPIA):
    """True si `texto` comparte mas de `max_run` palabras consecutivas con
    el libro de referencia (normalizado: minusculas, sin tildes, sin
    puntuacion)."""
    w = _palabras(texto)
    r = _palabras(referencia)
    n = max_run + 1
    if len(w) < n or len(r) < n:
        return False
    grams = set()
    for i in range(len(r) - n + 1):
        grams.add(" ".join(r[i:i + n]))
    for i in range(len(w) - n + 1):
        if " ".join(w[i:i + n]) in grams:
            return True
    return False


def etapa_afirmaciones(work_dir, workers=1, simulado=False, cliente=None):
    """Afirmaciones T38 sobre las evidencias de este work-dir."""
    argv = ["--evidencias",
            os.path.join(work_dir, "evidencias", "evidencias.jsonl"),
            "--secciones-dir", os.path.join(work_dir, "secciones"),
            "--out-dir", os.path.join(work_dir, "afirmaciones"),
            "--workers", str(workers)]
    if simulado:
        argv.append("--simulado")
    if cliente is not None:
        base = getattr(cliente, "_cliente", cliente)
        cliente = _ClienteAfirmaciones(base)
    return afirmaciones_libros.main(argv, cliente=cliente)


def auditar_copias(work_dir):
    """Puerta anti-copia: descarta afirmaciones/citas con >25 palabras
    consecutivas identicas al libro. Devuelve (aceptadas, rechazadas)."""
    ruta_af = os.path.join(work_dir, "afirmaciones",
                          "afirmaciones_libros.jsonl")
    if not os.path.exists(ruta_af):
        return 0, 0
    libros_texto = {}
    for libro in LIBROS:
        ruta_limp = ruta_limpio(work_dir, libro)
        if os.path.isfile(ruta_limp):
            with open(ruta_limp, encoding="utf-8", errors="replace") as fh:
                libros_texto[libro["id"]] = fh.read()
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
            fuente = reg.get("fuente_id")
            referencia = libros_texto.get(fuente, "")
            copia_en = None
            for campo in ("afirmacion", "cita_original"):
                if es_copia(reg.get(campo, ""), referencia):
                    copia_en = campo
                    break
            if copia_en:
                reg["motivo_rechazo"] = "copia>%d (%s)" % (MAX_RUN_COPIA,
                                                           copia_en)
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


# --------------------------------------------------------------------------
# Medicion de mejora sobre la matriz v3
# --------------------------------------------------------------------------

def medir_mejora(work_dir, out_dir=None):
    """Corre cobertura_v3 con las evidencias nuevas y mide celdas de tarot
    que pasan a completas. No toca el directorio v3 original."""
    import cobertura_v3
    evidencias = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    if not os.path.isfile(evidencias):
        raise LibroSinFuenteError("no hay evidencias que medir en %s"
                                 % work_dir)
    if out_dir is None:
        out_dir = "/Users/angelgonzalez/fase0/cobertura_v3_t115"
    rc = cobertura_v3.main(["--extra", evidencias, "--out-dir", out_dir])
    if rc not in (0, None):
        return rc
    ruta_v3 = "/Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.json"
    ruta_new = os.path.join(out_dir, "cobertura_total_v3.json")
    def tarot_completas(ruta):
        with open(ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
        celdas = [c for c in datos.get("celdas", [])
                  if (c.get("entidad_id") or "").startswith("tarot-")]
        return {c["entidad_id"] + "|" + c["faceta"] for c in celdas
                if c.get("completa")}
    base = tarot_completas(ruta_v3)
    nuevo = tarot_completas(ruta_new)
    ganadas = sorted(nuevo - base)
    perdidas = sorted(base - nuevo)
    resumen = {"tarot_completas_base": len(base),
               "tarot_completas_con_t115": len(nuevo),
               "ganadas": len(ganadas), "perdidas": len(perdidas),
               "ejemplos_ganadas": ganadas[:40],
               "out_dir": out_dir}
    ruta_res = os.path.join(work_dir, "resumenes", "mejora_cobertura.json")
    with open(ruta_res, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return resumen


# --------------------------------------------------------------------------
# Orquestacion y CLI
# --------------------------------------------------------------------------

def libros_en_orden(solo_ids=None):
    conocidos = {c["id"] for c in LIBROS}
    if solo_ids:
        faltan = sorted(set(solo_ids) - conocidos)
        if faltan:
            raise LibroSinFuenteError(
                "ids fuera del listado de comprados EN: %s" % ", ".join(faltan))
    libros = []
    for c in LIBROS:
        if solo_ids and c["id"] not in solo_ids:
            continue
        libros.append(dict(c))
    return libros


def ejecutar(work_dir=WORK_DIR_DEFAULT, solo_ids=None, hasta="juez",
            max_llamadas=0, workers=1, timeout=TIMEOUT_LIBRO,
            simulado=False, dry_run=False, cliente=None, extraer=False):
    try:
        work_dir = validar_work_dir(work_dir)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    try:
        libros = libros_en_orden(solo_ids)
    except LibroSinFuenteError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not libros:
        print("No hay libros que procesar.")
        return 0
    if dry_run:
        for libro in libros:
            try:
                preparar_work_dir(work_dir, [libro])
                medida = medir_libro(libro, work_dir)
            except (LibroSinFuenteError, Exception) as exc:
                print("%s: %s" % (libro["id"], exc), file=sys.stderr)
                continue
            print("%s: %d secciones, %d con candidatos (~%d llamadas al LLM)"
                  % (libro["id"], medida["secciones"], medida["con_candidatos"],
                     medida["llamadas_estimadas"]))
        return 0
    preparar_work_dir(work_dir, libros)
    if extraer:
        for libro in libros:
            extraer_crudo(libro, work_dir, forzar=True)
    if hasta == "preparacion":
        print("Preparacion completa en %s" % work_dir)
        return 0
    for libro in libros:
        n_sec = etapa_limpieza_segmentacion(libro, work_dir)
        print("%s: %d secciones escritas" % (libro["id"], n_sec), flush=True)
    if hasta == "limpieza" or hasta == "segmentacion":
        return 0
    for libro in libros:
        resumen = etapa_juez(libro, work_dir, max_llamadas=max_llamadas,
                            workers=workers, timeout=timeout,
                            simulado=simulado, cliente=cliente)
        print("%s: %d/%d secciones, %d llamadas, %d reaprovechadas, "
              "%d sin candidatos, %d errores, %d evidencias "
              "(%d con calidad >= 3)"
              % (libro["id"], resumen.get("juzgadas", 0),
                 resumen.get("secciones", 0), resumen.get("llamadas", 0),
                 resumen.get("reaprovechadas", 0),
                 resumen.get("sin_candidatos", 0),
                 resumen.get("error", 0), resumen.get("evidencias", 0),
                 resumen.get("aceptadas_calidad_ge_3", 0)), flush=True)
    if hasta == "juez":
        return 0
    stats = etapa_afirmaciones(work_dir, workers=workers, simulado=simulado,
                               cliente=cliente)
    aceptadas, rechazadas = auditar_copias(work_dir)
    print("afirmaciones: %d aceptadas, %d rechazadas por anti-copia "
          "(stats: %s)" % (aceptadas, rechazadas,
                          json.dumps({k: v for k, v in (stats or {}).items()
                                      if not isinstance(v, Counter)},
                                     ensure_ascii=False)), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pasa los libros comprados en ingles (Pollack, Greer) por "
                    "la tuberia de libros hacia evidencias (work-dir aparte "
                    "del real).")
    parser.add_argument("--work-dir", default=WORK_DIR_DEFAULT)
    parser.add_argument("--solo-ids", default="",
                      help="ids separados por comas")
    parser.add_argument("--hasta", default="juez",
                       choices=("preparacion", "limpieza", "segmentacion",
                               "juez", "afirmaciones"))
    parser.add_argument("--max-llamadas", type=int, default=0,
                       help="maximo de secciones pendientes por pasada "
                            "(0 = sin limite)")
    parser.add_argument("--workers", type=int, default=1,
                       help="hilos de llamada al LLM (con T114 vivo: 1)")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_LIBRO)
    parser.add_argument("--endpoints", default=ENDPOINTS_POR_DEFECTO,
                       help="URLs del LLM del juez separadas por comas. "
                            "Nunca 10.0.0.3 (reservado).")
    parser.add_argument("--simulado", action="store_true",
                       help="cliente LLM simulado para el juez")
    parser.add_argument("--dry-run", action="store_true",
                       help="mide secciones y llamadas sin tocar LLM")
    parser.add_argument("--extraer", action="store_true",
                       help="fuerza la re-extraccion de los crudos")
    parser.add_argument("--list", action="store_true", dest="lista")
    parser.add_argument("--medir", action="store_true",
                       help="mide celdas de tarot que pasan a completas con "
                            "estas evidencias (no toca la v3 original)")
    args = parser.parse_args(argv)
    solo = {s.strip() for s in args.solo_ids.split(",") if s.strip()} or None
    if args.lista:
        for libro in libros_en_orden(solo):
            print("%s (%s, %s, %d)" % (libro["id"], libro["familia"],
                                      libro["idioma"], libro["anio"]))
        return 0
    if args.medir:
        try:
            resumen = medir_mejora(args.work_dir)
        except (LibroSinFuenteError, Exception) as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        return 0
    cliente = None
    if args.endpoints and not args.simulado:
        try:
            cliente = construir_cliente_endpoints(args.endpoints,
                                                timeout=args.timeout)
        except ValueError as exc:
            print("error: %s" % exc, file=sys.stderr)
            return 2
    return ejecutar(work_dir=args.work_dir, solo_ids=solo, hasta=args.hasta,
                   max_llamadas=args.max_llamadas, workers=args.workers,
                   timeout=args.timeout, simulado=args.simulado,
                   dry_run=args.dry_run, cliente=cliente,
                   extraer=args.extraer)


if __name__ == "__main__":
    sys.exit(main())
