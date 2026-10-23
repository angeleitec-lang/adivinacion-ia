# -*- coding: utf-8 -*-
"""T133: apuntes TXT del usuario (OCR de archive.org).

Dos fuentes: el «Diccionario de ciencias ocultas» (español, época clásica,
atribuido a Papus/Encausse) y «Numerología fácil» (portugués, moderna).
Segmentación determinista, filtro estricto de familias, mapeo a ids de la KB y
etapas LLM (solo nodo2) de juez y extracción de afirmaciones, reanudables.
El texto fuente nunca se copia al repo: vive en ``/Users/angelgonzalez/fase0``.

Procedencia registrada en cada afirmación: «apuntes TXT del usuario (OCR de
archive.org), uso interno, derechos por revisar».
"""
import argparse
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cartas
import juez
import afirmaciones_libros
import consenso_kb
import libros_comprados_baraja as baraja

RUTA_DICCIONARIO = ("/Users/angelgonzalez/adivinacion-ia/_txt/"
                    "diccionario_ciencias_ocultas_djvu.txt")
RUTA_NUMEROLOGIA = ("/Users/angelgonzalez/adivinacion-ia/_txt/"
                    "numerologia_facil_djvu.txt")
WORK_DIR_DEFECTO = "/Users/angelgonzalez/fase0/txt_ocultismo_numerologia"

ID_DICCIONARIO = "diccionario_ciencias_ocultas"
ID_NUMEROLOGIA = "numerologia_facil_galves"
PERIODO_DICCIONARIO = "clasica"
PERIODO_NUMEROLOGIA = "moderna"
PROCEDENCIA = ("apuntes TXT del usuario (OCR de archive.org), "
               "uso interno, derechos por revisar")

MAX_ENTRADA_CHARS = 4000
MIN_CHARS_ENTRADA = 40
MIN_RATIO_LETRAS = 0.72
MAX_CONSECUTIVAS_COPIA = 25
MAX_WORKERS = 2
CALIDAD_NUMEROLOGIA = 4
IDIOMA_NUMEROLOGIA = "pt"

NODO2_ENDPOINT = baraja.NODO2_ENDPOINT

POSICIONES_NUMEROLOGIA = ("alma", "anio_personal", "camino_de_vida",
                         "destino", "mes_personal", "personalidad")

PRIORIDAD_FAMILIAS = ["tarot", "numerologia", "astrologia", "naipes",
                     "adivinacion"]

FAMILIAS_TERMS = {
    "tarot": r"\b(tarot|arcanos?)\b",
    "numerologia": r"\b(numerologia|cabala|guematria|gematria|pitagoras?)\b",
    "astrologia": (r"\b(aries|tauro|geminis|cancer|leo|virgo|libra|escorpio|"
                   r"sagitario|capricornio|acuario|piscis|mercurio|venus|marte|"
                   r"jupiter|saturno|urano|neptuno|pluton|zodiaco|planeta|"
                   r"horoscopo|astral)\b"),
    "naipes": (r"\b(naipe|baraja|cartomancia|oros|copas|espadas|bastos|"
               r"sota|caballo)\b"),
    "adivinacion": (r"\b(mancia|adivinacion|sortilegio|oraculo|augurio|"
                   r"presagio)\b"),
}

_PAGINA_RE = re.compile(r"^\d+\s*$")
_RUNNING_HEADER_RE = re.compile(r"^[A-Z]{2,4}\s*$")
_HEAD_RE = re.compile(
    r"^([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑÜíéáóúüñ']*"
    r"(?:\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑÜíéáóúüñ']*)*)\s*—\s*(.*)$")
_FRONT_MATTER_HASTA = 610

_NUM_HEAD_RE = re.compile(r"^(\d)\s+\([A-ZÀ-Ú]+\)[:\s]")
_MASTER_11_RE = re.compile(r"^11\s*-\s*A\s+FORÇA")
_MASTER_22_RE = re.compile(r"^22\s+ou\s+0\s*-\s*O\s+LOUCO")
_ARCANO_HEAD_RE = re.compile(r"^\d{1,2}\s*-\s*[A-ZÁÉÍÓÚÑ]")
_MESTRES_TITULO_RE = re.compile(r"^Os Números Mestres")
_PREVISIONES_RE = re.compile(r"^Fazendo Previsões")
_EJEMPLO_FIN_RE = re.compile(r"^Através dessas defini")
_ASSIM_COMO_RE = re.compile(r"^Assim como os números")
_POSITIVAS_RE = re.compile(r"^Caracter[íi]sticas\s+positivas\s*:")
_VIRTUDES_RE = re.compile(r"Suas virtudes\s*:")


def norm(s):
    return cartas.norm(s or "")


def _leer_jsonl(ruta):
    registros = []
    if not os.path.exists(ruta):
        return registros
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                registro = json.loads(linea)
            except ValueError:
                continue
            if isinstance(registro, dict):
                registros.append(registro)
    return registros


def validar_work_dir(work_dir):
    """El work dir debe estar bajo fase0 y fuera del repo."""
    ruta = os.path.abspath(work_dir)
    if not ruta.startswith("/Users/angelgonzalez/fase0"):
        raise ValueError("work-dir fuera de fase0: %r" % work_dir)
    return ruta


# ---------------------------------------------------------------------------
# Diccionario de ciencias ocultas
# ---------------------------------------------------------------------------

def _unir_hyphen(lineas, skip_re=None):
    """Une líneas (numero, texto) deshaciendo la partición OCR (`-`/`¬` final).

    Devuelve una lista de bloques ``(linea_inicio, texto)``. Se descartan las
    líneas vacías, los números de página sueltos y, si se indica, los cabeceras
    de página (``skip_re``).
    """
    bloques = []
    buf = None
    inicio = None
    for num, ln in lineas:
        ln = (ln or "").strip()
        if not ln or _PAGINA_RE.match(ln):
            continue
        if skip_re is not None and skip_re.match(ln):
            continue
        if buf is None:
            buf, inicio = ln, num
        elif buf.endswith("-") or buf.endswith("¬"):
            buf = buf[:-1] + ln
        else:
            bloques.append((inicio, buf))
            buf, inicio = ln, num
    if buf is not None:
        bloques.append((inicio, buf))
    return bloques


def segmentar_diccionario(texto):
    """Divide el diccionario en entradas ``CABECERA — definición``.

    Excluye el front matter (primeras ~610 líneas), los cabeceras de página
    de 2-4 letras y el cuadro sinóptico de -mancias (inicia en minúscula y
    no pasa la regex de cabecera). Devuelve ``[{head, linea, texto}]``.
    """
    lineas = enumerate(texto.split("\n"), start=1)
    entradas = []
    actual = None
    for num, ln in lineas:
        if num <= _FRONT_MATTER_HASTA:
            continue
        m = _HEAD_RE.match(ln)
        if m and len(m.group(1)) >= 2:
            if actual is not None:
                entradas.append(actual)
            actual = {"head": m.group(1), "linea": num,
                     "texto": [m.group(2)]}
        elif actual is not None:
            actual["texto"].append(ln)
    if actual is not None:
        entradas.append(actual)
    salida = []
    for e in entradas:
        unidas = _unir_hyphen(
            [(i, t) for i, t in enumerate(e["texto"])],
            skip_re=_RUNNING_HEADER_RE)
        cuerpo = " ".join(t for _, t in unidas).strip()
        if cuerpo:
            salida.append({"head": e["head"], "linea": e["linea"],
                         "texto": cuerpo})
    return salida


def calidad_ocr(texto):
    """(bool, motivo): rechaza entradas cortas o con exceso de ruido OCR."""
    if len(texto) < MIN_CHARS_ENTRADA:
        return (False, "corta")
    sin_espacios = re.sub(r"\s", "", texto)
    if not sin_espacios:
        return (False, "ilegible")
    letras = sum(1 for c in sin_espacios if c.isalpha())
    if letras / float(len(sin_espacios)) < MIN_RATIO_LETRAS:
        return (False, "ilegible")
    return (True, None)


def familias_de(texto):
    """Familias detectadas por términos estrictos (sin tildes, word-boundary)."""
    t = norm(texto)
    return [f for f, patron in FAMILIAS_TERMS.items()
            if re.search(patron, t)]


def _prioridad(familias):
    for f in PRIORIDAD_FAMILIAS:
        if f in familias:
            return PRIORIDAD_FAMILIAS.index(f)
    return len(PRIORIDAD_FAMILIAS)


def segmentar_diccionario_completo(ruta=None):
    """Segmenta, filtra por calidad/familia y separa por candidatos KB.

    Devuelve ``(secciones, rechazos_calidad, sin_entidad, informe)`` donde
    ``secciones`` son las entradas con candidatos deterministas de la KB
    (van al juez LLM), ordenadas por prioridad de familia.
    """
    ruta = ruta or RUTA_DICCIONARIO
    with open(ruta, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    entradas = segmentar_diccionario(texto)
    secciones = []
    rechazos_calidad = []
    sin_entidad = []
    informe = {"entradas": len(entradas),
               "rechazo_calidad": {}, "rechazo_longitud": 0,
               "pasan_familia": {}, "con_candidatos": {},
               "sin_candidatos": 0}
    for e in entradas:
        vale, motivo = calidad_ocr(e["texto"])
        if not vale:
            informe["rechazo_calidad"][motivo] = (
                informe["rechazo_calidad"].get(motivo, 0) + 1)
            rechazos_calidad.append({"head": e["head"], "linea": e["linea"],
                                   "motivo": motivo})
            continue
        if len(e["texto"]) > MAX_ENTRADA_CHARS:
            informe["rechazo_longitud"] += 1
            rechazos_calidad.append({"head": e["head"], "linea": e["linea"],
                                   "motivo": "exceso_longitud"})
            continue
        familias = familias_de(e["head"] + " " + e["texto"])
        if not familias:
            continue
        for f in familias:
            informe["pasan_familia"][f] = (
                informe["pasan_familia"].get(f, 0) + 1)
        seccion = {"id_libro": ID_DICCIONARIO, "seccion": e["linea"],
                   "titulo": e["head"],
                   "texto": (e["head"] + " — " + e["texto"])[:6000],
                   "_familias": familias}
        candidatos = juez.candidatos_seccion(seccion)
        if candidatos:
            informe["con_candidatos"].setdefault(
                familias[0], 0)
            informe["con_candidatos"][familias[0]] += 1
            secciones.append(seccion)
        else:
            informe["sin_candidatos"] += 1
            sin_entidad.append({"head": e["head"], "linea": e["linea"],
                               "motivo": "sin_candidatos_kb",
                               "familias": familias})
    secciones.sort(key=lambda s: (_prioridad(s["_familias"]), s["seccion"]))
    return secciones, rechazos_calidad, sin_entidad, informe


# ---------------------------------------------------------------------------
# Numerología fácil (portugués)
# ---------------------------------------------------------------------------

def _lineas_pt(texto):
    return [(i + 1, re.sub(r" {2,}", " ", ln).strip())
            for i, ln in enumerate(texto.split("\n"))]


def _buscar(bloques, regex, desde=0):
    for idx in range(desde, len(bloques)):
        if regex.match(bloques[idx][1]):
            return idx
    return -1


def segmentar_numerologia(texto):
    """Divide el libro en bloques por número (1-9) y maestros (11, 22).

    Cada número produce dos bloques: ``general`` (Palavras-chave + párrafo)
    y ``sombra`` (características positivas/negativas + missão). Los maestros
    11 y 22 se cortan en ``general`` (intro del arcano) y ``sombra``
    (Suas virtudes / fraquezas + remisión numerológica). El 33 no tiene
    sección propia en el libro y no se procesa.
    Devuelve ``[{numero, maestro, bloque, titulo, texto, seccion}]``.
    """
    crudos = _lineas_pt(texto)
    bloques = _unir_hyphen(crudos)
    salida = []

    def _anadir(numero, maestro, bloque, titulo, lineas_contenido, seccion):
        cuerpo = " ".join(t for _, t in lineas_contenido).strip()
        if cuerpo:
            salida.append({"numero": numero, "maestro": maestro,
                         "bloque": bloque, "titulo": titulo,
                         "texto": cuerpo, "seccion": seccion})

    # Números 1-9: desde el header del 1 hasta el ejemplo de «Fernando».
    i = _buscar(bloques, _NUM_HEAD_RE)
    fin_nums = _buscar(bloques, _EJEMPLO_FIN_RE, desde=max(i, 0))
    if fin_nums < 0:
        fin_nums = len(bloques)
    while i >= 0 and i < fin_nums:
        m = _NUM_HEAD_RE.match(bloques[i][1])
        if not m:
            i += 1
            continue
        numero = int(m.group(1))
        j = i + 1
        while j < fin_nums and not _NUM_HEAD_RE.match(bloques[j][1]):
            j += 1
        contenido = bloques[i + 1:j]
        k = -1
        for pos in range(len(contenido)):
            if _POSITIVAS_RE.match(contenido[pos][1]):
                k = pos
                break
        if k >= 0:
            _anadir(numero, False, "general", bloques[i][1],
                    contenido[:k], numero * 10 + 1)
            _anadir(numero, False, "sombra", bloques[i][1],
                    contenido[k:], numero * 10 + 2)
        else:
            _anadir(numero, False, "general", bloques[i][1],
                    contenido, numero * 10 + 1)
        i = j

    # Maestros: capítulo «Os Números Mestres» hasta «Fazendo Previsões».
    ini_m = _buscar(bloques, _MESTRES_TITULO_RE)
    fin_m = _buscar(bloques, _PREVISIONES_RE, desde=max(ini_m, 0))
    if fin_m < 0:
        fin_m = len(bloques)
    if ini_m >= 0:
        for regex, numero in ((_MASTER_11_RE, 11), (_MASTER_22_RE, 22)):
            h = _buscar(bloques, regex, desde=ini_m + 1)
            if h < 0 or h >= fin_m:
                continue
            j = h + 1
            if numero == 11:
                while j < fin_m and not _ARCANO_HEAD_RE.match(bloques[j][1]):
                    j += 1
            else:
                while j < fin_m and not _ASSIM_COMO_RE.match(bloques[j][1]):
                    j += 1
            contenido = bloques[h + 1:j]
            k = -1
            for pos in range(len(contenido)):
                if _VIRTUDES_RE.search(contenido[pos][1]):
                    k = pos
                    break
            if k >= 0:
                _anadir(numero, True, "general", bloques[h][1],
                        contenido[:k], numero * 10 + 1)
                _anadir(numero, True, "sombra", bloques[h][1],
                        contenido[k:], numero * 10 + 2)
            else:
                _anadir(numero, True, "general", bloques[h][1],
                        contenido, numero * 10 + 1)
    return salida


FACETA_POR_BLOQUE = {"general": "significado_general",
                     "sombra": "luz_sombra"}


def evidencias_numerologia(bloques):
    """Evidencias deterministas: cada bloque × 6 posiciones canónicas."""
    evs = []
    for b in bloques:
        faceta = FACETA_POR_BLOQUE[b["bloque"]]
        seccion = {"id_libro": ID_NUMEROLOGIA, "seccion": b["seccion"],
                   "titulo": b["titulo"], "texto": b["texto"]}
        h = juez.hash_seccion(seccion)
        for pos in POSICIONES_NUMEROLOGIA:
            evs.append({
                "entidad_id": "%d|%s" % (b["numero"], pos),
                "faceta": faceta,
                "fuente_id": ID_NUMEROLOGIA,
                "dominio": ID_NUMEROLOGIA,
                "idioma": IDIOMA_NUMEROLOGIA,
                "periodo": PERIODO_NUMEROLOGIA,
                "calidad": CALIDAD_NUMEROLOGIA,
                "tipo": "libro",
                "hash_seccion": h,
            })
    return evs


# ---------------------------------------------------------------------------
# Preparación en disco
# ---------------------------------------------------------------------------

def preparar_segmentacion(work_dir, ruta_dicc=None, ruta_num=None):
    work_dir = validar_work_dir(work_dir)
    for sub in ("secciones", "evidencias", "afirmaciones", "rechazos",
               "resumenes"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    secciones, rechazos_calidad, sin_entidad, informe = (
        segmentar_diccionario_completo(ruta_dicc))
    with open(os.path.join(work_dir, "secciones",
                          "%s.jsonl" % ID_DICCIONARIO), "w",
              encoding="utf-8") as fh:
        for s in secciones:
            fila = {"id_libro": s["id_libro"], "seccion": s["seccion"],
                    "titulo": s["titulo"], "texto": s["texto"]}
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    with open(os.path.join(work_dir, "rechazos", "calidad.jsonl"), "w",
              encoding="utf-8") as fh:
        for r in rechazos_calidad:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(work_dir, "rechazos", "sin_entidad.jsonl"), "w",
              encoding="utf-8") as fh:
        for r in sin_entidad:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(ruta_num or RUTA_NUMEROLOGIA, encoding="utf-8",
              errors="replace") as fh:
        texto_num = fh.read()
    bloques = segmentar_numerologia(texto_num)
    with open(os.path.join(work_dir, "secciones",
                          "%s.jsonl" % ID_NUMEROLOGIA), "w",
              encoding="utf-8") as fh:
        for b in bloques:
            fila = {"id_libro": ID_NUMEROLOGIA, "seccion": b["seccion"],
                    "titulo": b["titulo"], "texto": b["texto"]}
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    informe["numerologia"] = {
        "bloques": len(bloques),
        "numeros": sorted({b["numero"] for b in bloques}),
        "evidencias_esperadas": len(bloques) * len(POSICIONES_NUMEROLOGIA),
    }
    ruta_informe = os.path.join(work_dir, "resumenes",
                               "informe_segmentacion.json")
    with open(ruta_informe, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)
    return informe


def procesar_determinista(work_dir):
    """Escribe las evidencias de numerología (sin LLM), idempotente."""
    work_dir = validar_work_dir(work_dir)
    ruta_ev = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    existentes = set()
    for ev in _leer_jsonl(ruta_ev):
        if ev.get("fuente_id") == ID_NUMEROLOGIA:
            existentes.add((ev.get("hash_seccion"), ev.get("entidad_id"),
                           ev.get("faceta")))
    with open(os.path.join(work_dir, "secciones",
                          "%s.jsonl" % ID_NUMEROLOGIA),
             encoding="utf-8") as fh:
        secciones = [json.loads(l) for l in fh if l.strip()]
    bloques = []
    for s in secciones:
        bloques.append({"numero": s["seccion"] // 10,
                       "maestro": (s["seccion"] // 10) in (11, 22),
                       "bloque": "general" if s["seccion"] % 10 == 1
                       else "sombra",
                       "titulo": s["titulo"], "texto": s["texto"],
                       "seccion": s["seccion"]})
    nuevas = [ev for ev in evidencias_numerologia(bloques)
              if (ev["hash_seccion"], ev["entidad_id"], ev["faceta"])
              not in existentes]
    with open(ruta_ev, "a", encoding="utf-8") as fh:
        for ev in nuevas:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return {"nuevas": len(nuevas), "existentes": len(existentes)}


# ---------------------------------------------------------------------------
# Etapas LLM (solo nodo2)
# ---------------------------------------------------------------------------

def _clamp_workers(workers):
    return max(1, min(int(workers or 1), MAX_WORKERS))


def procesar_juez(work_dir, endpoints=None, workers=MAX_WORKERS, limite=None,
                  cliente=None):
    """Juez LLM sobre las secciones del diccionario (español, clásica)."""
    work_dir = validar_work_dir(work_dir)
    if cliente is None:
        cliente = baraja.construir_cliente_endpoints(endpoints)
    meta = {ID_DICCIONARIO: {
        "periodo": PERIODO_DICCIONARIO, "idioma": "es", "anio": 1889,
        "titulo": "Diccionario de las ciencias ocultas",
        "autor": "Papus (Gérard Encausse)"}}
    secciones = _leer_jsonl(os.path.join(work_dir, "secciones",
                                        "%s.jsonl" % ID_DICCIONARIO))
    return juez.procesar_secciones(secciones, cliente,
                                   os.path.join(work_dir, "evidencias"),
                                   meta=meta,
                                   workers=_clamp_workers(workers),
                                   limite=limite)


def procesar_afirmaciones(work_dir, endpoints=None, workers=MAX_WORKERS,
                         limite=None, cliente=None):
    """Extrae afirmaciones de todas las evidencias (numerología primero).

    Reanudable por ``(hash_seccion, entidad_id, faceta)`` vía fichero de
    salida y diario de procesados (las tareas sin afirmaciones no se
    repiten). Anti-copia: se descarta toda afirmación con más de
    ``MAX_CONSECUTIVAS_COPIA`` palabras consecutivas idénticas al texto.
    """
    work_dir = validar_work_dir(work_dir)
    if cliente is None:
        cliente = baraja.construir_cliente_endpoints(endpoints, acotar=False)
    indice = afirmaciones_libros.IndiceLibros(
        os.path.join(work_dir, "secciones"))
    corr = consenso_kb.cargar_correspondencias()
    evidencias = _leer_jsonl(os.path.join(work_dir, "evidencias",
                                         "evidencias.jsonl"))
    # Prioridad: numerología completa primero, luego diccionario.
    evidencias.sort(key=lambda e: (0 if e.get("fuente_id") == ID_NUMEROLOGIA
                                  else 1))
    out = os.path.join(work_dir, "afirmaciones",
                      "afirmaciones_txt_ocultismo.jsonl")
    diario = os.path.join(work_dir, "afirmaciones", "procesadas.jsonl")
    hechos = set()
    for fila in _leer_jsonl(out):
        hechos.add((fila.get("hash_seccion"), fila.get("entidad_id"),
                    fila.get("faceta")))
    for fila in _leer_jsonl(diario):
        hechos.add((fila.get("hash_seccion"), fila.get("entidad_id"),
                    fila.get("faceta")))
    pendientes = [ev for ev in evidencias
                 if (ev.get("hash_seccion"), ev.get("entidad_id"),
                     ev.get("faceta")) not in hechos]
    if limite is not None:
        pendientes = pendientes[:limite]
    lock = threading.Lock()
    stats = {"procesadas": 0, "afirmaciones": 0, "descartadas_copia": 0,
             "error": 0, "sin_texto": 0}

    def _trabajo(ev):
        sec = indice.seccion(ev["fuente_id"], ev["hash_seccion"])
        if sec is None or not (sec.get("texto") or "").strip():
            return (ev, None, "")
        texto = sec["texto"]
        resultado = afirmaciones_libros.extraer_afirmaciones_libros(
            cliente, ev["entidad_id"], ev["faceta"], texto,
            ev.get("idioma", "es"), corr)
        return (ev, resultado, texto)

    def _registrar(ev, resultado, texto):
        with lock:
            if resultado is None:
                stats["sin_texto"] += 1
                return
            if resultado.get("estado") == "error":
                stats["error"] += 1
                return
            n_ok = 0
            n_copia = 0
            with open(out, "a", encoding="utf-8") as fh:
                for item in resultado.get("afirmaciones", []):
                    if baraja.es_copia_literal(item["afirmacion"], texto,
                                              MAX_CONSECUTIVAS_COPIA):
                        n_copia += 1
                        continue
                    registro = afirmaciones_libros.registro_afirmacion_libros(
                        ev, item)
                    registro["procedencia"] = PROCEDENCIA
                    fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
                    n_ok += 1
            stats["procesadas"] += 1
            stats["afirmaciones"] += n_ok
            stats["descartadas_copia"] += n_copia
            with open(diario, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "hash_seccion": ev["hash_seccion"],
                    "entidad_id": ev["entidad_id"],
                    "faceta": ev["faceta"],
                    "estado": "ok", "n_afirmaciones": n_ok,
                    "copia": n_copia}, ensure_ascii=False) + "\n")

    if pendientes:
        w = _clamp_workers(workers)
        if w > 1 and len(pendientes) > 1:
            with ThreadPoolExecutor(max_workers=w) as pool:
                for ev, resultado, texto in pool.map(_trabajo, pendientes):
                    _registrar(ev, resultado, texto)
        else:
            for ev in pendientes:
                _registrar(*_trabajo(ev))
    return stats


def medir_dry(work_dir):
    """Estimación de llamadas LLM sin ejecutar nada."""
    work_dir = validar_work_dir(work_dir)
    secciones_dicc = _leer_jsonl(os.path.join(
        work_dir, "secciones", "%s.jsonl" % ID_DICCIONARIO))
    secciones_num = _leer_jsonl(os.path.join(
        work_dir, "secciones", "%s.jsonl" % ID_NUMEROLOGIA))
    evs = _leer_jsonl(os.path.join(work_dir, "evidencias",
                                   "evidencias.jsonl"))
    out = os.path.join(work_dir, "afirmaciones",
                      "afirmaciones_txt_ocultismo.jsonl")
    diario = os.path.join(work_dir, "afirmaciones", "procesadas.jsonl")
    hechos = set()
    for fila in _leer_jsonl(out) + _leer_jsonl(diario):
        hechos.add((fila.get("hash_seccion"), fila.get("entidad_id"),
                    fila.get("faceta")))
    pendientes_ev = [ev for ev in evs
                    if (ev.get("hash_seccion"), ev.get("entidad_id"),
                        ev.get("faceta")) not in hechos]
    juzgados = set()
    for fila in _leer_jsonl(os.path.join(work_dir, "evidencias",
                                        "juicios.jsonl")):
        if (fila.get("juicio") or {}).get("tipo") != "error":
            juzgados.add(fila.get("hash"))
    juez_pend = [s for s in secciones_dicc
                 if juez.hash_seccion(s) not in juzgados]
    return {
        "secciones_diccionario": len(secciones_dicc),
        "secciones_numerologia": len(secciones_num),
        "llamadas_juez_pendientes": len(juez_pend),
        "evidencias_totales": len(evs),
        "llamadas_extraccion_pendientes": len(pendientes_ev),
        "llamadas_totales_estimadas": (len(juez_pend)
                                      + len(pendientes_ev)),
        "endpoints": NODO2_ENDPOINT,
        "workers_max": MAX_WORKERS,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", default=WORK_DIR_DEFECTO)
    ap.add_argument("--segmentar", action="store_true")
    ap.add_argument("--determinista", action="store_true",
                    help="evidencias de numerología sin LLM")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--juez", action="store_true")
    ap.add_argument("--afirmaciones", action="store_true")
    ap.add_argument("--endpoints", default=NODO2_ENDPOINT)
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args(argv)

    work_dir = validar_work_dir(args.work_dir)
    if args.segmentar:
        informe = preparar_segmentacion(work_dir)
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0
    if args.dry_run:
        print(json.dumps(medir_dry(work_dir), ensure_ascii=False, indent=2))
        return 0
    if args.determinista:
        print(procesar_determinista(work_dir))
    if args.juez:
        print(procesar_juez(work_dir, args.endpoints, args.workers,
                            args.limite))
    if args.afirmaciones:
        print(procesar_afirmaciones(work_dir, args.endpoints, args.workers,
                                    args.limite))
    return 0


if __name__ == "__main__":
    sys.exit(main())
