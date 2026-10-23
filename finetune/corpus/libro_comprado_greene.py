"""Procesado del libro comprado «Saturn: A New Look at an Old Devil» (Liz Greene).

T130. Libro comprado por el usuario (copyright, uso interno), en ingles. El
escaneo (202 paginas, 396x612 pt, una pagina por hoja) NO tiene capa de texto
util: solo los preliminares traen texto real; el resto son marcas de imprenta.
Se extrae por OCR con tesseract (300 dpi), reutilizando las funciones de
limpieza de T118 (``libros_comprados_prep``) y el mecanismo de
juez/afirmaciones/puerta anti-copia de T119 (``libros_comprados_astro``), que
este modulo solo importa (no los modifica).

Alcance: se extraen UNICAMENTE celdas que YA existen en
``cobertura.entidades()``: ``saturno|<signo>|planeta_en_signo``,
``saturno|casaN|planeta_en_casa`` y aspectos ``p1|<asp>|p2|aspecto`` con
saturno. NO se crean entidades nuevas ni se toca el catalogo compartido.

La segmentacion es por CABECERA: Greene escribe una seccion por signo con su
casa («Saturn in Cancer and the fourth house»: 12 secciones que cubren los 12
signos y las 12 casas) y, en el capitulo 5, «Saturn in aspect to the Sun/Moon/
...». El contexto de cabecera asigna celdas a cada trozo (el texto de la
seccion versa sobre esa celda); ademas se detectan menciones explicitas de
Saturno en otras celdas dentro del trozo.

HUECOS (documentados, sin celda destino): el libro NO tiene capitulo de
tramites ni de retornos de Saturno (indice: Foreword, Introduction, caps. 1-4
signos y casas por elemento, cap. 5 aspectos, cap. 6 sinastria, cap. 7
conclusion). Prologo/introduccion/conclusion y sinastria son holisticos; los
trozos sin celda se contabilizan en el informe.

NUNCA se copia el PDF ni texto del libro al repositorio: todo el trabajo de
datos vive en ``/Users/angelgonzalez/fase0/libros_comprados_greene/``. El LLM
va fijado a nodo2 (nodo1 reservado). Las etapas ``--juez``/``--afirmaciones``
se lanzan por CLI (T121 las desbloquea): comando exacto en
``finetune/knowledge/libros_comprados_greene.md``.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import afirmaciones_libros
import juez
import libros_pipeline
import llm_client
import libros_comprados_astro as astro
import libros_comprados_prep as prep

# --- Identidad del libro y rutas --------------------------------------------
ID_LIBRO = "greene_saturn_1976"
LIBRO = {
    "id": ID_LIBRO,
    "titulo": "Saturn: A New Look at an Old Devil",
    "autor": "Liz Greene",
    "anio": 1976,
    "idioma": "en",
    "corto": "Greene",
}
PDF_FUENTE = ("/Users/angelgonzalez/fase0/libros_comprados/"
              "Greene - Saturn A New Look at an Old Devil.pdf")
WORK_DIR = "/Users/angelgonzalez/fase0/libros_comprados_greene"
META_NOMBRE = "fuentes_libros_comprados.jsonl"
CRUDO_TXT = "greene_saturn_capa_texto.txt"
LIMPIO_TXT = "greene_saturn.txt"

NODO2_ENDPOINT = astro.NODO2_ENDPOINT
NODO1_RESERVADO = astro.NODO1_RESERVADO
TIMEOUT = astro.TIMEOUT_ASTRO
MAX_WORKERS = astro.MAX_WORKERS
MIN_SECCION = astro.MIN_SECCION
MAX_SECCION = astro.MAX_SECCION
MAX_ENTIDADES_PARRAFO = astro.MAX_ENTIDADES_PARRAFO

# OCR: CPU local (iMac), sin LLM. Reanudable por pagina.
PSM_OCR = 3
MAX_WORKERS_OCR = 3
CHUNK_TARGET = 2500
CHUNK_MIN = 400
CHUNK_MAX = 6000

# Basura de imprenta del escaneo (marcas de imposicion y pie de pagina).
RE_IMPRENTA = re.compile(
    r"(?i)(45173|txt\s*\d+|indd|continental|\bnda\b|11-06|11-0603"
    r"|1[0-9]:[0-5][0-9]|\bpm\b|\bblack\b|17[0-9]{1,2}\s*[°º]"
    r"|pages_\d|layout|\bdg.49|4f49|4f;49|1f446)")
_JUNK_TOKENS = {"txt", "indd", "nda", "black", "continental",
                "inscontinental", "nscontinental", "layout", "pages"}

# --- Regex de cabeceras (sobre linea normalizada minuscula sin tildes) ------
_Alt_SIGNO = astro._alternancia(astro.SIGNOS_EN2ES)
_Alt_PLANETA = astro._alternancia(astro.PLANETAS_EN2ES)
_Alt_ORD = astro._alternancia(astro.CASAS_ORD)

RE_CAB_SIGNO = re.compile(
    r"^\W*saturn in (" + _Alt_SIGNO + r")"
    r"(?:\s+(?:and\s+)?(?:the\s+)?(" + _Alt_ORD + r")\s+house)?"
    r"(?:\s+(?:and|&))?\W*$")
RE_CAB_CASA = re.compile(
    r"^\W*(?:and\s+)?(?:the\s+)?(" + _Alt_ORD + r")\s+house"
    r"(?:\s+(?:and|&))?\W*$")
RE_CAB_ASPECTO = re.compile(
    r"^\W*(?:\d+\s+)?saturn in aspect"
    r"(?:\s+to\s+the\s+(" + _Alt_PLANETA + r"))?(?:\s+to)?\W*$")
RE_CAB_TO_PLANETA = re.compile(
    r"^\W*(?:to\s+)?the\s+(" + _Alt_PLANETA + r")(?:\s+chart)?\W*$")
RE_CAPITULO = re.compile(
    r"^\W*(?:\d+\s+)?(?:[a-z]\s+)?"
    r"(foreword|introduction|conclusion"
    r"|in the (?:watery|earthy|airy|fiery)(?:\s+signs)?(?:\s+and\s+houses)?"
    r"|signs\s+and\s+houses"
    r"|aspects\s+(?:on|in)\s+the(?:\s+birth)?(?:\s+chart)?"
    r"|birth\s+chart"
    r"|in\s+synastry)\W*(?:\d{1,4}\W*)?$")

# Variantes de aspecto mayores para el capitulo 5 (texto en ingles).
RE_ASPECTO_TIPO = {
    "conjuncion": re.compile(r"\bconjun(?:ct|ction|cts|cting|cted)\b"),
    "cuadratura": re.compile(r"\bsquare(?:s|d)?\b"),
    "trigono": re.compile(r"\btrine(?:s)?\b"),
    "sextil": re.compile(r"\bsextile(?:s)?\b"),
    "oposicion": re.compile(r"\bopposit(?:e|ion)(?:s)?\b"),
}

# El OCR suele fundir la cabecera «Saturn in aspect» con el cuerpo y perder la
# linea «to the X»: se infiere el planeta por frecuencia en el trozo.
RE_PLANETA_WORD = re.compile(
    r"\b(" + astro._alternancia(astro.PLANETAS_EN2ES) + r")\b")

# Los capitulos 6 (sinastria) y 7 (conclusion) no dejan cabecera OCR
# superviviente: se abren por marcador de primera frase. En ellos NO se
# admiten celdas de aspecto (el lenguaje es natal/sinastrico mixto y las
# cabeceras interiores («Pluto-Saturn contacts») no son secciones de Greene).
MARCADORES_CAPITULO = (
    ("having made a closer observation", "sinastria"),
    ("the science of psychology is a relatively new one", "conclusion"),
)
HUECOS_SIN_ASPECTO = {"sinastria", "conclusion"}


def _clave_capitulo(g1):
    """Clave normalizada de capitulo a partir del grupo capturado."""
    g1 = " ".join(g1.split())
    if g1.startswith("in the watery"):
        return "watery"
    if g1.startswith("in the earthy"):
        return "earthy"
    if g1.startswith("in the airy"):
        return "airy"
    if g1.startswith("in the fiery"):
        return "fiery"
    if g1.startswith("aspects"):
        return "aspectos"
    if g1 == "signs and houses" or g1 == "birth chart":
        return None
    if g1 == "in synastry":
        return "sinastria"
    if g1 == "foreword":
        return "prologo"
    if g1 == "introduction":
        return "introduccion"
    if g1 == "conclusion":
        return "conclusion"
    return None


def _eids_validos():
    return astro._validos()


def eids_signo_casa(signo=None, casa=None):
    """Celdas del catalogo para la cabecera Saturno en <signo> [y casa N]."""
    validos = _eids_validos()
    ids = []
    if signo:
        s = astro.SIGNOS_EN2ES.get(signo)
        if s:
            eid = "saturno|%s|planeta_en_signo" % s
            if eid in validos:
                ids.append(eid)
    if casa and casa in astro.CASAS_ORD:
        eid = "saturno|casa%d|planeta_en_casa" % astro.CASAS_ORD[casa]
        if eid in validos and eid not in ids:
            ids.append(eid)
    return ids


def detectar_aspectos(chunk_norm):
    """Nombres ES de aspectos mayores mencionados en un trozo."""
    return [es for es, rx in RE_ASPECTO_TIPO.items() if rx.search(chunk_norm)]


def eids_aspecto_planeta(planeta_es, aspectos):
    """Celdas canonicas <otro>|<asp>|saturno|aspecto para el planeta dado."""
    validos = _eids_validos()
    ids = []
    a, b = astro._canon_planetas(planeta_es, "saturno")
    for asp in aspectos:
        eid = "%s|%s|%s|aspecto" % (a, asp, b)
        if eid in validos and eid not in ids:
            ids.append(eid)
    return ids


def extras_saturn(texto):
    """Menciones explicitas de Saturno (astro.detectar_entidades filtradas)."""
    out = []
    for eid in astro.detectar_entidades(texto):
        if "saturno" in eid.split("|") and eid not in out:
            out.append(eid)
    return out


def detectar_cabecera(linea):
    """Clasifica una linea corta como cabecera del libro. None si no lo es."""
    s = linea.strip()
    if not s or len(s) > 60:
        return None
    n = astro.norm(s)
    m = RE_CAB_SIGNO.match(n)
    if m:
        return ("signo", m.group(1), m.group(2))
    m = RE_CAB_CASA.match(n)
    if m:
        return ("casa", m.group(1), None)
    m = RE_CAB_ASPECTO.match(n)
    if m:
        return ("aspecto", m.group(1), None)
    m = RE_CAB_TO_PLANETA.match(n)
    if m:
        return ("toplaneta", m.group(1), None)
    m = RE_CAPITULO.match(n)
    if m:
        return ("capitulo", m.group(1), None)
    return None


def trocear(texto, target=CHUNK_TARGET, chunk_min=CHUNK_MIN):
    """Divide un bloque largo en trozos por limites de oracion."""
    texto = " ".join(texto.split())
    if len(texto) <= target:
        return [texto] if texto else []
    frases = re.split(r"(?<=[.!?])\s+", texto)
    trozos = []
    cur = ""
    for f in frases:
        if len(f) > CHUNK_MAX:
            if cur:
                trozos.append(cur)
                cur = ""
            while len(f) > CHUNK_MAX:
                cut = f.rfind(" ", 0, CHUNK_MAX)
                cut = cut if cut > 0 else CHUNK_MAX
                trozos.append(f[:cut])
                f = f[cut:].lstrip()
            cur = f
            continue
        if cur and len(cur) + len(f) + 1 > target:
            trozos.append(cur)
            cur = f
        else:
            cur = (cur + " " + f).strip()
    if cur:
        trozos.append(cur)
    if len(trozos) >= 2 and len(trozos[-1]) < chunk_min:
        trozos[-2] = trozos[-2] + " " + trozos[-1]
        trozos.pop()
    return trozos


def inferir_planeta(texto):
    """Planeta (clave EN) mas mencionado en un trozo, excluido saturn."""
    conteo = {}
    orden = []
    for m in RE_PLANETA_WORD.finditer(astro.norm(texto)):
        p = m.group(1)
        if p == "saturn":
            continue
        if p not in conteo:
            conteo[p] = 0
            orden.append(p)
        conteo[p] += 1
    if not conteo:
        return None
    return max(orden, key=lambda p: conteo[p])


def _nuevo_contexto(capitulo="inicio"):
    return {"capitulo": capitulo, "tipo": None, "eids": [], "planeta": None}


def eids_para_trozo(trozo, contexto):
    """Celdas del trozo: contexto de cabecera + menciones explicitas."""
    ids = []

    def _add(eid):
        if eid not in ids:
            ids.append(eid)

    if contexto["tipo"] == "signo_casa":
        for eid in contexto["eids"]:
            _add(eid)
    elif contexto["tipo"] == "aspecto" and contexto["planeta"]:
        p = astro.PLANETAS_EN2ES.get(contexto["planeta"])
        if p:
            for eid in eids_aspecto_planeta(
                    p, detectar_aspectos(astro.norm(trozo))):
                _add(eid)
    for eid in extras_saturn(trozo):
        _add(eid)
    return ids[:MAX_ENTIDADES_PARRAFO]


def segmentar(texto_limpio):
    """Segmenta el texto limpio de Greene en secciones por cabecera.

    Devuelve (secciones, informe). Cada seccion lleva entidad_id explicito
    (formato T119); los trozos sin celda se contabilizan como hueco.
    """
    validos = _eids_validos()
    secciones = []
    contexto = _nuevo_contexto()
    buffer = []
    informe = {
        "secciones": 0, "trozos": 0, "trozos_sin_celda": 0,
        "sin_celda_por_capitulo": {}, "por_tipo": {},
        "celdas": {}, "secciones_por_capitulo": {},
    }
    estado = {"corte_corto": ""}
    posicion = [0]

    def registrar(trozo):
        informe["trozos"] += 1
        if contexto["tipo"] == "aspecto" and not contexto["planeta"]:
            p = inferir_planeta(trozo)
            if p:
                contexto["planeta"] = p
                contexto["capitulo"] = "aspectos:%s" % p
        ids = [e for e in eids_para_trozo(trozo, contexto) if e in validos]
        if contexto["capitulo"] in HUECOS_SIN_ASPECTO:
            ids = [e for e in ids if not e.endswith("|aspecto")]
        if not ids:
            informe["trozos_sin_celda"] += 1
            clave = contexto["capitulo"]
            informe["sin_celda_por_capitulo"][clave] = (
                informe["sin_celda_por_capitulo"].get(clave, 0) + 1)
            return
        for eid in ids:
            texto_sec = trozo[:MAX_SECCION]
            secciones.append({
                "seccion": eid,
                "titulo": "%s: %s" % (LIBRO["corto"], eid),
                "texto": texto_sec,
                "chars": len(texto_sec),
                "id_libro": ID_LIBRO,
                "posicion": posicion[0],
                "entidad_id": eid,
            })
            subtipo = eid.rsplit("|", 1)[-1]
            informe["por_tipo"][subtipo] = informe["por_tipo"].get(
                subtipo, 0) + 1
            informe["celdas"][eid] = informe["celdas"].get(eid, 0) + 1
            informe["secciones_por_capitulo"][contexto["capitulo"]] = (
                informe["secciones_por_capitulo"].get(
                    contexto["capitulo"], 0) + 1)
        posicion[0] += 1

    def vaciar():
        texto = "\n".join(buffer).strip()
        del buffer[:]
        if texto:
            texto = estado["corte_corto"] + " " + texto if (
                estado["corte_corto"]) else texto
            estado["corte_corto"] = ""
        if not texto:
            return
        if len(texto) < MIN_SECCION:
            estado["corte_corto"] = texto
            return
        for trozo in trocear(texto):
            registrar(trozo)

    for linea in texto_limpio.splitlines():
        if not linea.strip():
            vaciar()
            continue
        s = linea.strip()
        nl = astro.norm(s)
        marcador = None
        for pref, clave_m in MARCADORES_CAPITULO:
            if nl.startswith(pref):
                marcador = clave_m
                break
        if marcador is not None:
            if contexto["capitulo"] != marcador:
                vaciar()
                contexto = _nuevo_contexto(marcador)
            buffer.append(s)
            continue
        cab = detectar_cabecera(linea)
        if cab is None:
            buffer.append(s)
            continue
        if cab[0] != "capitulo" and contexto["capitulo"] in HUECOS_SIN_ASPECTO:
            buffer.append(s)
            continue
        tipo, g1, g2 = cab
        if tipo == "signo":
            vaciar()
            contexto = _nuevo_contexto("signos_casas:%s" % g1)
            contexto["tipo"] = "signo_casa"
            contexto["eids"] = eids_signo_casa(g1, g2)
        elif tipo == "casa":
            if contexto["tipo"] == "signo_casa":
                for eid in eids_signo_casa(None, g1):
                    if eid not in contexto["eids"]:
                        contexto["eids"].append(eid)
                if contexto["capitulo"].startswith("signos_casas:"):
                    contexto["capitulo"] = "signos_casas:%s_casa%s" % (
                        contexto["capitulo"].split(":", 1)[1], g1)
            else:
                buffer.append(linea.strip())
        elif tipo == "aspecto":
            vaciar()
            contexto = _nuevo_contexto(
                "aspectos:%s" % (g1 or "intro"))
            contexto["tipo"] = "aspecto"
            contexto["planeta"] = g1
        elif tipo == "toplaneta":
            if contexto["tipo"] == "aspecto" and not contexto["planeta"]:
                contexto["planeta"] = g1
                contexto["capitulo"] = "aspectos:%s" % g1
            else:
                buffer.append(linea.strip())
        elif tipo == "capitulo":
            clave = _clave_capitulo(g1)
            if clave is None:
                continue
            if (contexto["tipo"] is None
                    and contexto["capitulo"] in ("watery", "earthy", "airy",
                                                 "fiery", "aspectos",
                                                 "sinastria", "prologo",
                                                 "introduccion",
                                                 "conclusion", "inicio")):
                vaciar()
            contexto = _nuevo_contexto(clave)
            if clave == "aspectos":
                contexto["tipo"] = "capitulo_aspectos"
    vaciar()
    informe["secciones"] = len(secciones)
    informe["n_celdas_distintas"] = len(informe["celdas"])
    return secciones, informe


# --- Etapas sin LLM ----------------------------------------------------------
def preparar(work_dir=WORK_DIR):
    """Crea la estructura del work-dir y escribe el meta del juez."""
    work_dir = astro.validar_work_dir(work_dir)
    for sub in ("crudo", "limpio", "ocr", "secciones", "evidencias",
                "knowledge", "afirmaciones"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "id": LIBRO["id"], "anio": LIBRO["anio"],
            "idioma": LIBRO["idioma"], "titulo": LIBRO["titulo"],
            "autor": LIBRO["autor"], "origen": "comprado_por_usuario",
            "licencia_hint": "libro con copyright, uso interno",
        }, ensure_ascii=False) + "\n")
    return work_dir


def _no_imprenta(linea):
    """False si la linea es marcas de imposicion/pie de imprenta."""
    s = linea.strip()
    if len(s) < 5:
        return False
    if RE_IMPRENTA.search(s):
        return False
    reales = [t for t in prep.tokenize(s)
              if len(t) >= 3 and t.lower() not in _JUNK_TOKENS]
    return len(reales) >= 2


def extraer_capa_texto(work_dir=WORK_DIR):
    """Extrae la capa de texto del PDF (crudo) y emite informe por paginas."""
    work_dir = astro.validar_work_dir(work_dir)
    destino = os.path.join(work_dir, "crudo", CRUDO_TXT)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    if not os.path.isfile(destino):
        subprocess.run(["pdftotext", "-layout", PDF_FUENTE, destino],
                       check=True)
    with open(destino, encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    paginas = [p for p in texto.split("\f") if p.strip()]
    reales = []
    for i, pag in enumerate(paginas, 1):
        fichas = [t for t in prep.tokenize(pag)
                  if len(t) >= 3 and t.lower() not in _JUNK_TOKENS]
        if len(fichas) >= 30:
            reales.append(i)
    informe = {
        "paginas_total": len(paginas),
        "paginas_con_texto_real": len(reales),
        "paginas_reales": reales,
        "conclusion": ("capa de texto insuficiente: hace falta OCR"
                       if len(reales) < len(paginas) * 0.5
                       else "capa de texto suficiente"),
    }
    ruta_inf = os.path.join(work_dir, "limpio", "capa_texto_informe.json")
    os.makedirs(os.path.dirname(ruta_inf), exist_ok=True)
    with open(ruta_inf, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=1)
    return informe


def etapa_ocr(work_dir=WORK_DIR, psm=PSM_OCR, workers=MAX_WORKERS_OCR):
    """OCR reanudable por pagina (cache ocr/pNNN.txt). CPU local, sin LLM."""
    from concurrent.futures import ThreadPoolExecutor
    work_dir = astro.validar_work_dir(work_dir)
    ocr_dir = os.path.join(work_dir, "ocr")
    os.makedirs(ocr_dir, exist_ok=True)
    n = prep.pdfinfo_pages(PDF_FUENTE)

    def ruta_pag(p):
        return os.path.join(ocr_dir, "p%03d.txt" % p)

    def ocr_pagina(p):
        destino = ruta_pag(p)
        pgm = prep.rasterize_sheet(PDF_FUENTE, p)
        if prep.dark_fraction(pgm) < prep.BLANK_DARK_FRAC:
            txt = "@@BLANK\n"
        else:
            tmp = destino + ".pgm"
            with open(tmp, "wb") as fh:
                fh.write(pgm)
            try:
                txt = prep.tesseract_ocr(tmp, psm)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        with open(destino, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return p

    pendientes = [p for p in range(1, n + 1)
                  if not os.path.isfile(ruta_pag(p))]
    cache = n - len(pendientes)
    if pendientes:
        workers = max(1, min(workers, MAX_WORKERS_OCR))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, _ in enumerate(ex.map(ocr_pagina, pendientes), 1):
                if i % 20 == 0:
                    print("ocr: %d/%d paginas" % (i, len(pendientes)),
                          flush=True)
    blanks = 0
    for p in range(1, n + 1):
        try:
            with open(ruta_pag(p), encoding="utf-8") as fh:
                if fh.read(9) == "@@BLANK":
                    blanks += 1
        except OSError:
            pass
    return {"paginas": n, "cache": cache, "nuevas": len(pendientes),
            "blank": blanks, "psm": psm}


def etapa_limpieza(work_dir=WORK_DIR):
    """Limpia las paginas OCR (rubricas, imprenta, guiones) y ensambla."""
    work_dir = astro.validar_work_dir(work_dir)
    ocr_dir = os.path.join(work_dir, "ocr")
    n = prep.pdfinfo_pages(PDF_FUENTE)
    vocab = prep.load_vocab()
    pages_raw = []
    faltan = []
    for p in range(1, n + 1):
        ruta = os.path.join(ocr_dir, "p%03d.txt" % p)
        if not os.path.isfile(ruta):
            faltan.append(p)
            pages_raw.append([])
            continue
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            pages_raw.append(fh.read().splitlines())
    if faltan:
        raise FileNotFoundError(
            "faltan %d paginas por OCR (ejecuta --ocr); ejemplo: %s"
            % (len(faltan), faltan[:5]))
    heads = prep.collect_running_heads(
        [l for l in pages_raw if l], min_pages=4)
    pages_clean = []
    imprenta_drops = 0
    hyp = {"joined": 0, "kept_hyphen": 0, "forced": 0}
    blank = 0
    for p, lines in enumerate(pages_raw, 1):
        if len(lines) == 1 and lines[0].strip() == "@@BLANK":
            blank += 1
            continue
        cp = prep.clean_page(lines, heads)
        keep = []
        for l in cp.lines:
            if _no_imprenta(l):
                keep.append(l)
            elif l.strip():
                imprenta_drops += 1
        joined, info = prep.join_hyphens(keep, vocab)
        for k in hyp:
            hyp[k] += info[k]
        marked = prep.mark_headings(joined, heads, cp.title_page)
        pages_clean.append({"sheet": p, "side": "F", "lines": marked,
                            "label": cp.label})
    texto, records = prep.build_document(pages_clean)
    crudo = "\n".join(" ".join(l) for l in pages_raw)
    antes = prep.quality_metrics(crudo, vocab)
    despues = prep.quality_metrics(texto, vocab)
    ruta_txt = os.path.join(work_dir, "limpio", LIMPIO_TXT)
    os.makedirs(os.path.dirname(ruta_txt), exist_ok=True)
    with open(ruta_txt, "w", encoding="utf-8") as fh:
        fh.write(texto)
    informe = {
        "id_libro": ID_LIBRO,
        "paginas_pdf": n,
        "paginas_con_texto": len(pages_clean),
        "paginas_blank": blank,
        "rubricas_detectadas": len(heads),
        "lineas_imprenta_quitadas": imprenta_drops,
        "guiones": hyp,
        "calidad_antes": {"tokens": antes.tokens,
                          "vocab_pct": round(antes.vocab_pct, 2),
                          "glued": antes.glued},
        "calidad_despues": {"tokens": despues.tokens,
                            "vocab_pct": round(despues.vocab_pct, 2),
                            "glued": despues.glued},
        "chars": len(texto),
    }
    ruta_inf = os.path.join(work_dir, "limpio", ID_LIBRO + "_informe.json")
    with open(ruta_inf, "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=1)
    return informe


def ruta_limpio(work_dir=WORK_DIR):
    return os.path.join(work_dir, "limpio", LIMPIO_TXT)


def segmentar_a_disco(work_dir=WORK_DIR):
    with open(ruta_limpio(work_dir), encoding="utf-8",
              errors="replace") as fh:
        texto = fh.read()
    secciones, informe = segmentar(texto)
    destino = os.path.join(work_dir, "secciones", ID_LIBRO + ".jsonl")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as fh:
        for sec in secciones:
            fh.write(json.dumps(sec, ensure_ascii=False) + "\n")
    return secciones, informe


def _leer_secciones(work_dir):
    ruta = os.path.join(work_dir, "secciones", ID_LIBRO + ".jsonl")
    secciones = []
    if not os.path.isfile(ruta):
        return secciones
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                secciones.append(json.loads(linea))
    return secciones


def medir(work_dir=WORK_DIR):
    """Dry-run sin LLM: segmenta en memoria y estima llamadas y celdas."""
    with open(ruta_limpio(work_dir), encoding="utf-8",
              errors="replace") as fh:
        texto = fh.read()
    secciones, informe = segmentar(texto)
    con_cand = sum(1 for s in secciones if juez.candidatos_seccion(s))
    n = len(secciones)
    informe.update({
        "con_candidatos": con_cand,
        "llamadas_juez_estimadas": n,
        "llamadas_afirmaciones_estimadas": {
            "formula": ("evidencias x facetas (se sabra tras el juez); "
                        "estimacion 0.4-0.8 x secciones"),
            "rango": [int(n * 0.4), max(1, int(n * 0.8))],
        },
        "celdas_saturno_objetivo": sorted(informe["celdas"]),
    })
    return informe


# --- Etapas LLM (no lanzadas en T130 por presupuesto) -----------------------
def _simulado_juez_greene(sistema, usuario):
    return json.dumps({"tipo": "relleno", "calidad": 1, "idioma": "en",
                       "entidades": []}, ensure_ascii=False)


def procesar_juez_greene(work_dir=WORK_DIR, workers=1, max_llamadas=0,
                         cliente=None, simulado=False):
    secciones = _leer_secciones(work_dir)
    if not secciones:
        print("sin secciones que juzgar", file=sys.stderr)
        return {"juzgadas": 0, "llamadas": 0, "evidencias": 0,
                "reaprovechadas": 0, "sin_candidatos": 0, "error": 0}
    purgados = astro.purgar_errores_juez(work_dir)
    if purgados:
        print("%d juicios-error purgados para reintentar" % purgados,
              flush=True)
    if cliente is None:
        if not simulado:
            raise ValueError("hace falta cliente o --simulado")
        cliente = libros_pipeline._ClienteAcotado(
            llm_client.LLMClient(simulado=_simulado_juez_greene))
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if max_llamadas and max_llamadas > 0:
        hechos = astro._hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                      if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:max_llamadas]
    return juez.procesar_secciones(a_procesar, cliente,
                                   os.path.join(work_dir, "evidencias"),
                                   meta=meta, workers=workers)


def procesar_afirmaciones_greene(work_dir=WORK_DIR, workers=1, limite=0,
                                 cliente=None, simulado=False):
    import threading
    from collections import Counter
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
    corr = afirmaciones_libros.cargar_correspondencias()
    if cliente is None:
        if not simulado:
            raise ValueError("hace falta cliente o --simulado")
        cliente = llm_client.LLMClient(
            simulado=afirmaciones_libros._simulado_libros)
    out_dir = os.path.join(work_dir, "afirmaciones")
    os.makedirs(out_dir, exist_ok=True)
    ruta_af = os.path.join(out_dir, "afirmaciones_greene.jsonl")
    ruta_pr = os.path.join(out_dir, "procesados.jsonl")
    procesados = astro._cargar_procesados(ruta_pr)
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
            res = {"estado": "sin_texto", "afirmaciones": [],
                   "descartadas": []}
        else:
            texto = sec["texto"]
            indice = astro.construir_indice_copia(texto)
            res = astro.extraer_afirmaciones_astro(
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Procesa el Greene «Saturn» comprado (T130).")
    parser.add_argument("--work-dir", default=WORK_DIR)
    parser.add_argument("--endpoints", default=astro.ENDPOINTS_POR_DEFECTO,
                        help="URLs del LLM separadas por comas (solo nodo2).")
    parser.add_argument("--workers", type=int, default=1,
                        help="hilos del LLM (max %d)" % MAX_WORKERS)
    parser.add_argument("--timeout", type=float, default=TIMEOUT)
    parser.add_argument("--max-llamadas", type=int, default=0)
    parser.add_argument("--simulado", action="store_true")
    parser.add_argument("--psm", type=int, default=PSM_OCR,
                        help="page segmentation mode de tesseract")
    parser.add_argument("--preparar", action="store_true")
    parser.add_argument("--calidad", action="store_true",
                        help="informe de la capa de texto del PDF")
    parser.add_argument("--ocr", action="store_true",
                        help="OCR reanudable por pagina (CPU local)")
    parser.add_argument("--limpiar", action="store_true",
                        help="limpia el OCR y escribe el texto limpio")
    parser.add_argument("--segmentar", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="mide secciones, celdas y llamadas sin LLM")
    parser.add_argument("--juez", action="store_true")
    parser.add_argument("--afirmaciones", action="store_true")
    args = parser.parse_args(argv)

    try:
        work_dir = astro.validar_work_dir(args.work_dir)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.workers > MAX_WORKERS:
        print("error: workers <= %d (nodo2 saturable)" % MAX_WORKERS,
              file=sys.stderr)
        return 2

    if args.preparar:
        print("work-dir preparado en %s" % preparar(work_dir))
        return 0
    if args.calidad:
        print(json.dumps(extraer_capa_texto(work_dir), ensure_ascii=False))
        return 0
    if args.ocr:
        print(json.dumps(etapa_ocr(work_dir, psm=args.psm),
                         ensure_ascii=False))
        return 0
    if args.limpiar:
        print(json.dumps(etapa_limpieza(work_dir), ensure_ascii=False))
        return 0
    if args.dry_run:
        informe = medir(work_dir)
        resumen = {k: v for k, v in informe.items() if k != "celdas"}
        resumen["secciones_por_celda"] = informe["celdas"]
        print(json.dumps(resumen, ensure_ascii=False, indent=1))
        return 0
    if args.segmentar:
        _, informe = segmentar_a_disco(work_dir)
        resumen = {k: v for k, v in informe.items() if k != "celdas"}
        resumen["secciones_por_celda"] = informe["celdas"]
        print(json.dumps(resumen, ensure_ascii=False, indent=1))
        return 0

    if args.juez:
        cliente = None
        if not args.simulado:
            cliente = astro.construir_cliente_endpoints(args.endpoints,
                                                      timeout=args.timeout)
        stats = procesar_juez_greene(work_dir, workers=args.workers,
                                    max_llamadas=args.max_llamadas,
                                    cliente=cliente, simulado=args.simulado)
        print("juez: %s" % json.dumps(stats, ensure_ascii=False))
        return 0

    if args.afirmaciones:
        cliente = None
        if not args.simulado:
            cliente = astro.construir_cliente_endpoints(args.endpoints,
                                                      timeout=args.timeout,
                                                      acotar=False)
        stats = procesar_afirmaciones_greene(work_dir, workers=args.workers,
                                            limite=args.max_llamadas,
                                            cliente=cliente,
                                            simulado=args.simulado)
        print("afirmaciones: %s" % json.dumps(
            {k: v for k, v in stats.items() if k != "descartadas"},
            ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
