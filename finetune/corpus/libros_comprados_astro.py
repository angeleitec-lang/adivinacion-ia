"""Procesado de los libros comprados de astrologia (Arroyo, Sasportas) a evidencias.

T119. Dos libros comprados por el usuario (copyright, uso interno), en ingles:

- Stephen Arroyo, «Astrology, Psychology and the Four Elements» (1982): capa de
  texto buena y completa. Trata signos por elemento, planetas, casas y aspectos.
- Howard Sasportas, «The Twelve Houses» (1985): escaneo incompleto. Contiene las
  doce casas (caps. 3-14) y el inicio del cap. 15 (agrupaciones). Falta todo lo
  posterior a la pagina impresa 131 (apendices, glosario, bibliografia, indice).

Decis de alcance (usuario, 2026-10-22): se extraen UNICAMENTE celdas que YA
existen en el catalogo de ``cobertura.entidades()``: ``signo``,
``planeta_en_signo``, ``planeta_en_casa`` y ``aspecto``. NO se crean entidades
``casa-N``, ``elemento`` ni ``modalidad`` (no existen en el catalogo y tocarlo
seria un cambio transversal fuera de esta pista). El contenido holistico de casas
y de elementos que no cabe en esas celdas se documenta como HUECO en el
``knowledge/libros_comprados_astro_evidencias.md`` y se propone como pista aparte.

Los libros estan en ingles y la detencion automatica del juez esta en espanol,
asi que este modulo resuelve EN->ES en su propia segmentacion y fija un
``entidad_id`` explicito por seccion (una seccion por entidad detectada). El juez
reconoce ese id explicito como candidato (``juez.candidatos_seccion``) y decide
tipo/calidad/facetas. Las afirmaciones reutilizan ``afirmaciones_libros`` y anaden
la puerta anti-copia de T114: una afirmacion que repita mas de 25 palabras
consecutivas del libro se rechaza (debe ser parafasis breve, no cita literal).

El LLM va fijado a nodo2 (nodo1 reservado), con reintentos bajos y corrida
reanudable. El texto limpio lo aporta T118 en
``/Users/angelgonzalez/fase0/libros_comprados_astro/limpio/``; nunca se toca el
work-dir real de la tuberia (``/Users/angelgonzalez/fase0/libros``).
"""
import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

import afirmaciones_libros
import cobertura
import juez
import libros_pipeline
import llm_client

# --- Endpoints y limites -----------------------------------------------------
NODO2_ENDPOINT = "http://10.0.0.4:8000/v1"
NODO1_RESERVADO = "10.0.0.3"
TIMEOUT_ASTRO = 120.0
MAX_WORKERS = 2

MAX_CONSECUTIVAS_COPIA = 25
MIN_SECCION = 120
MAX_SECCION = 12000
MAX_ENTIDADES_PARRAFO = 5

WORK_DIR = "/Users/angelgonzalez/fase0/libros_comprados_astro"
WORK_DIR_REAL = "/Users/angelgonzalez/fase0/libros"
LIMPIO_DIR = os.path.join(WORK_DIR, "limpio")
META_NOMBRE = "fuentes_libros_comprados.jsonl"

# --- Libros ----------------------------------------------------------------
LIBROS = (
    {
        "id": "arroyo_astrologia_psicologia_1982",
        "titulo": "Astrology, Psychology and the Four Elements",
        "autor": "Stephen Arroyo",
        "anio": 1982,
        "idioma": "en",
        "archivo": "arroyo.txt",
        "corto": "Arroyo",
    },
    {
        "id": "sasportas_twelve_houses_1985",
        "titulo": "The Twelve Houses",
        "autor": "Howard Sasportas",
        "anio": 1985,
        "idioma": "en",
        "archivo": "sasportas.txt",
        "corto": "Sasportas",
    },
)
LIBROS_POR_ID = {lib["id"]: lib for lib in LIBROS}

# --- Mapeos EN -> ES (catalogo) --------------------------------------------
SIGNOS_EN2ES = {
    "aries": "aries",
    "taurus": "tauro",
    "gemini": "geminis",
    "cancer": "cancer",
    "leo": "leo",
    "virgo": "virgo",
    "libra": "libra",
    "scorpio": "escorpio",
    "sagittarius": "sagitario",
    "capricorn": "capricornio",
    "capricornus": "capricornio",
    "aquarius": "acuario",
    "pisces": "piscis",
}
PLANETAS_EN2ES = {
    "sun": "sol",
    "moon": "luna",
    "mercury": "mercurio",
    "venus": "venus",
    "mars": "marte",
    "jupiter": "jupiter",
    "saturn": "saturno",
    "uranus": "urano",
    "neptune": "neptuno",
    "pluto": "pluton",
}
ASPECTOS_EN2ES = {
    "conjunction": "conjuncion",
    "sextile": "sextil",
    "square": "cuadratura",
    "trine": "trigono",
    "opposition": "oposicion",
}
# Orden canonico de planetas para normalizar el aspecto (p1 antes que p2).
PLANETA_ORDEN = [
    "sol", "luna", "mercurio", "venus", "marte",
    "jupiter", "saturno", "urano", "neptuno", "pluton",
]
# Ordinales en palabra para casas (1..12).
CASAS_ORD = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12,
}


def sin_tildes(texto):
    """Quita marcas diacriticas combinantes (para normalizar comparaciones)."""
    nfkd = unicodedata.normalize("NFD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm(texto):
    """Minusculas sin tildes: base de las comparaciones del detector."""
    return sin_tildes(texto.lower())


def _alternancia(claves):
    """Alternancia regex ordenada por longitud descendente (evita prefijos)."""
    ordenadas = sorted(claves, key=len, reverse=True)
    return "|".join(re.escape(k) for k in ordenadas)


_ALT_PLANETAS = _alternancia(PLANETAS_EN2ES)
_ALT_SIGNOS = _alternancia(SIGNOS_EN2ES)
_ALT_ASPECTOS = _alternancia(ASPECTOS_EN2ES)
_RE_PLANETA = r"(?P<planeta>" + _ALT_PLANETAS + r")"
_RE_SIGNO = r"(?P<signo>" + _ALT_SIGNOS + r")"
_RE_ASPECTO = r"(?P<aspecto>" + _ALT_ASPECTOS + r")"

# Planeta ... in ... signo  (y espejo signo ... in ... planeta).
RE_PIS = re.compile(
    _RE_PLANETA + r"\b[^.]{0,40}?\bin\b[^.]{0,15}?\b" + _RE_SIGNO + r"\b")
RE_SPIN = re.compile(
    _RE_SIGNO + r"\b[^.]{0,40}?\bin\b[^.]{0,15}?\b" + _RE_PLANETA + r"\b")

# Planeta ... in ... <ordinal> house  (ordinal en palabra o digito-ordinal).
_RE_CASA_ORD = r"(?:(?P<casa_palabra>" + _alternancia(CASAS_ORD) + r")" \
    r"|(?P<casa_num>\d{1,2})(?:st|nd|rd|th))"
RE_PIH = re.compile(
    _RE_PLANETA + r"\b[^.]{0,40}?\bin\b[^.]{0,15}?" + _RE_CASA_ORD + r"\s+house")

# «the sign of X» y «X is a fire/earth/air/water sign».
RE_SIGNOF = re.compile(r"\bthe sign of\s+" + _RE_SIGNO + r"\b")
RE_SIGNEL = re.compile(
    r"\b" + _RE_SIGNO + r"\b\s+(?:is|represents)\s+a\s+"
    r"(?:fire|earth|air|water)\s+sign")

# Aspectos: «p1 square p2» y «square between p1 and p2».
RE_ASPECTO1 = re.compile(
    r"(?P<p1>" + _ALT_PLANETAS + r")\b[^.]{0,20}?" + _RE_ASPECTO
    + r"[^.]{0,20}?\b(?P<p2>" + _ALT_PLANETAS + r")\b")
RE_ASPECTO2 = re.compile(
    r"\b" + _RE_ASPECTO + r"\s+(?:between|to)\s+(?P<p1>" + _ALT_PLANETAS
    + r")\s+and\s+(?P<p2>" + _ALT_PLANETAS + r")\b")


def _validos():
    """Conjunto de entidad_id validos del catalogo activo."""
    return {e["entidad_id"] for e in cobertura.entidades()}


def _canon_planetas(a, b):
    """Ordena dos planetas (es) segun PLANETA_ORDEN; devuelve (p1, p2)."""
    ia = PLANETA_ORDEN.index(a) if a in PLANETA_ORDEN else 99
    ib = PLANETA_ORDEN.index(b) if b in PLANETA_ORDEN else 99
    return (a, b) if ia <= ib else (b, a)


def _casa_de(m):
    """Numero de casa (1..12) desde un match con casa_palabra o casa_num."""
    if m.groupdict().get("casa_palabra"):
        return CASAS_ORD[m.group("casa_palabra")]
    if m.groupdict().get("casa_num"):
        n = int(m.group("casa_num"))
        return n if 1 <= n <= 12 else None
    return None


def detectar_entidades(parrafo):
    """Detecta entidad_ids existentes (astro) mencionados en un parrafo.

    Devuelve una lista ordenada y sin duplicados. Solo se incluyen ids que
    existen en el catalogo (``_validos()``). No se crean casas/elementos sueltos.
    """
    texto = norm(parrafo)
    validos = _validos()
    ids = []

    def _add(eid):
        if eid in validos and eid not in ids:
            ids.append(eid)

    for m in RE_PIS.finditer(texto):
        p = PLANETAS_EN2ES.get(m.group("planeta"))
        s = SIGNOS_EN2ES.get(m.group("signo"))
        if p and s:
            _add("%s|%s|planeta_en_signo" % (p, s))
    for m in RE_SPIN.finditer(texto):
        p = PLANETAS_EN2ES.get(m.group("planeta"))
        s = SIGNOS_EN2ES.get(m.group("signo"))
        if p and s:
            _add("%s|%s|planeta_en_signo" % (p, s))
    for m in RE_PIH.finditer(texto):
        p = PLANETAS_EN2ES.get(m.group("planeta"))
        casa = _casa_de(m)
        if p and casa:
            _add("%s|casa%d|planeta_en_casa" % (p, casa))
    for m in RE_SIGNOF.finditer(texto):
        s = SIGNOS_EN2ES.get(m.group("signo"))
        if s:
            _add("%s|signo" % s)
    for m in RE_SIGNEL.finditer(texto):
        s = SIGNOS_EN2ES.get(m.group("signo"))
        if s:
            _add("%s|signo" % s)
    for m in RE_ASPECTO1.finditer(texto):
        p1 = PLANETAS_EN2ES.get(m.group("p1"))
        asp = ASPECTOS_EN2ES.get(m.group("aspecto"))
        p2 = PLANETAS_EN2ES.get(m.group("p2"))
        if p1 and asp and p2 and p1 != p2:
            a, b = _canon_planetas(p1, p2)
            _add("%s|%s|%s|aspecto" % (a, asp, b))
    for m in RE_ASPECTO2.finditer(texto):
        asp = ASPECTOS_EN2ES.get(m.group("aspecto"))
        p1 = PLANETAS_EN2ES.get(m.group("p1"))
        p2 = PLANETAS_EN2ES.get(m.group("p2"))
        if p1 and asp and p2 and p1 != p2:
            a, b = _canon_planetas(p1, p2)
            _add("%s|%s|%s|aspecto" % (a, asp, b))
    return ids


def _dividir_parrafos(texto):
    """Parrafos por linea en blanco, descartando cabeceras (# / ##) y cortos."""
    parrafos = []
    for bloque in re.split(r"\n\s*\n", texto):
        lineas = [ln for ln in bloque.splitlines()
                  if not ln.lstrip().startswith("#")]
        p = "\n".join(lineas).strip()
        if len(p) >= MIN_SECCION:
            parrafos.append(p)
    return parrafos


def segmentar(texto_libro, id_libro):
    """Segmenta un libro en secciones (una por entidad detectada por parrafo)."""
    secciones = []
    for idx, parrafo in enumerate(_dividir_parrafos(texto_libro)):
        if len(parrafo) > MAX_SECCION:
            parrafo = parrafo[:MAX_SECCION]
        for eid in detectar_entidades(parrafo)[:MAX_ENTIDADES_PARRAFO]:
            secciones.append({
                "seccion": eid,
                "titulo": "%s: %s" % (LIBROS_POR_ID[id_libro]["corto"], eid),
                "texto": parrafo,
                "chars": len(parrafo),
                "id_libro": id_libro,
                "posicion": idx,
                "entidad_id": eid,
            })
    return secciones


# --- Puerta anti-copia (igual que T114) ------------------------------------
def _normalizar_palabras(texto):
    bajo = sin_tildes(texto.lower())
    bajo = re.sub(r"[^a-z0-9 ]+", " ", bajo)
    return bajo.split()


def construir_indice_copia(texto_libro, max_consecutivas=MAX_CONSECUTIVAS_COPIA):
    n = max_consecutivas + 1
    palabras = _normalizar_palabras(texto_libro)
    indice = set()
    for i in range(len(palabras) - n + 1):
        indice.add(hash(tuple(palabras[i:i + n])))
    return indice


def es_copia_literal(afirmacion, texto_libro=None,
                    max_consecutivas=MAX_CONSECUTIVAS_COPIA, indice=None):
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


def extraer_afirmaciones_astro(cliente, entidad_id, faceta, texto, idioma, corr,
                              indice=None):
    """Extraccion de T38 mas la puerta anti-copia sobre la afirmacion."""
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


# --- Work-dir y cliente ----------------------------------------------------
def validar_work_dir(work_dir):
    real = os.path.realpath(work_dir)
    raiz_real = os.path.realpath(WORK_DIR_REAL)
    if real == raiz_real or real.startswith(raiz_real + os.sep):
        raise ValueError(
            "work-dir %r apunta al directorio real de la tuberia; usa uno "
            "aparte (por defecto: %s)" % (work_dir, WORK_DIR))
    return real


def ruta_limpio(libro):
    return os.path.join(LIMPIO_DIR, libro["archivo"])


def preparar(work_dir=WORK_DIR):
    """Crea la estructura y escribe el meta del juez para ambos libros."""
    work_dir = validar_work_dir(work_dir)
    for sub in ("secciones", "evidencias", "knowledge", "afirmaciones"):
        os.makedirs(os.path.join(work_dir, sub), exist_ok=True)
    meta_ruta = os.path.join(work_dir, "knowledge", META_NOMBRE)
    with open(meta_ruta, "w", encoding="utf-8") as fh:
        for lib in LIBROS:
            fh.write(json.dumps({
                "id": lib["id"], "anio": lib["anio"], "idioma": lib["idioma"],
                "titulo": lib["titulo"], "autor": lib["autor"],
                "origen": "comprado_por_usuario",
                "licencia_hint": "libro con copyright, uso interno",
            }, ensure_ascii=False) + "\n")
    return work_dir


def construir_cliente_endpoints(endpoints_csv, timeout=TIMEOUT_ASTRO, acotar=True):
    endpoints = [e.strip() for e in (endpoints_csv or "").split(",") if e.strip()]
    if not endpoints:
        raise ValueError("--endpoints vacio")
    for url in endpoints:
        if NODO1_RESERVADO in url:
            raise ValueError(
                "nodo1 (%s) esta reservado por el usuario; no puede usarse: %r"
                % (NODO1_RESERVADO, url))
    base = llm_client.LLMClient(endpoints=endpoints, timeout=timeout)
    if acotar:
        return libros_pipeline._ClienteAcotado(base)
    return base


# --- Segmentacion a disco --------------------------------------------------
def segmentar_a_disco(work_dir):
    """Segmenta ambos libros y escribe secciones/<id>.jsonl."""
    total = {}
    for lib in LIBROS:
        ruta_txt = ruta_limpio(lib)
        if not os.path.isfile(ruta_txt):
            raise FileNotFoundError("falta texto limpio: %s" % ruta_txt)
        with open(ruta_txt, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
        secciones = segmentar(texto, lib["id"])
        destino = os.path.join(work_dir, "secciones", lib["id"] + ".jsonl")
        with open(destino, "w", encoding="utf-8") as fh:
            for sec in secciones:
                fh.write(json.dumps(sec, ensure_ascii=False) + "\n")
        total[lib["id"]] = len(secciones)
    return total


def _leer_secciones(work_dir):
    secciones = []
    for lib in LIBROS:
        ruta = os.path.join(work_dir, "secciones", lib["id"] + ".jsonl")
        if not os.path.isfile(ruta):
            continue
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if linea:
                    secciones.append(json.loads(linea))
    return secciones


def medir(work_dir=WORK_DIR):
    """Dry-run: segmenta en memoria y cuenta secciones y candidatos."""
    informe = {}
    for lib in LIBROS:
        with open(ruta_limpio(lib), encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
        secciones = segmentar(texto, lib["id"])
        con_cand = sum(1 for s in secciones if juez.candidatos_seccion(s))
        por_tipo = {}
        for s in secciones:
            subtipo = s["entidad_id"].rsplit("|", 1)[-1]
            por_tipo[subtipo] = por_tipo.get(subtipo, 0) + 1
        informe[lib["id"]] = {
            "secciones": len(secciones),
            "con_candidatos": con_cand,
            "por_tipo": por_tipo,
        }
    return informe


# --- Juez (reanudable) -----------------------------------------------------
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


def procesar_juez(work_dir=WORK_DIR, workers=1, max_llamadas=0,
                 cliente=None, simulado=False):
    secciones = _leer_secciones(work_dir)
    if not secciones:
        print("sin secciones que juzgar", file=sys.stderr)
        return {"juzgadas": 0, "llamadas": 0, "evidencias": 0,
                "reaprovechadas": 0, "sin_candidatos": 0, "error": 0}
    purgados = purgar_errores_juez(work_dir)
    if purgados:
        print("%d juicios-error purgados para reintentar" % purgados, flush=True)
    if cliente is None:
        if not simulado:
            raise ValueError("hace falta cliente o --simulado")
        cliente = libros_pipeline._ClienteAcotado(
            llm_client.LLMClient(simulado=_simulado_juez_astro))
    meta = juez.cargar_meta_libros(
        [os.path.join(work_dir, "knowledge", META_NOMBRE)])
    a_procesar = secciones
    if max_llamadas and max_llamadas > 0:
        hechos = _hashes_juzgados(work_dir)
        pendientes = [s for s in secciones
                     if juez.hash_seccion(s) not in hechos]
        a_procesar = pendientes[:max_llamadas]
    return juez.procesar_secciones(a_procesar, cliente,
                                   os.path.join(work_dir, "evidencias"),
                                   meta=meta, workers=workers)


def _simulado_juez_astro(sistema, usuario):
    # Tipo valido para el juez pero que no genera evidencia (solo conocimiento y
    # lectura_trabajada producen evidencias). Evita error de parse en modo simulado.
    return json.dumps({"tipo": "relleno", "calidad": 1, "idioma": "en",
                      "entidades": []}, ensure_ascii=False)


# --- Afirmaciones (anti-copia) ---------------------------------------------
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


def procesar_afirmaciones(work_dir=WORK_DIR, workers=1, limite=0,
                         cliente=None, simulado=False):
    import threading
    from collections import Counter
    import afirmaciones_es as es

    ruta_ev = os.path.join(work_dir, "evidencias", "evidencias.jsonl")
    ids_libros = set(LIBROS_POR_ID)
    evidencias = []
    if os.path.exists(ruta_ev):
        with open(ruta_ev, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if linea:
                    ev = json.loads(linea)
                    if ev.get("fuente_id") in ids_libros:
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
    ruta_af = os.path.join(out_dir, "afirmaciones_astro.jsonl")
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
            res = extraer_afirmaciones_astro(
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
        description="Procesa los libros comprados de astrologia (T119).")
    parser.add_argument("--work-dir", default=WORK_DIR)
    parser.add_argument("--endpoints", default=NODO2_ENDPOINT,
                       help="URLs del LLM separadas por comas (solo nodo2).")
    parser.add_argument("--workers", type=int, default=1,
                       help="hilos de llamada al LLM (max %d)" % MAX_WORKERS)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_ASTRO)
    parser.add_argument("--max-llamadas", type=int, default=0)
    parser.add_argument("--simulado", action="store_true")
    parser.add_argument("--preparar", action="store_true",
                       help="crea el work-dir y el meta de ambos libros")
    parser.add_argument("--dry-run", action="store_true",
                       help="mide secciones y candidatos sin LLM")
    parser.add_argument("--segmentar", action="store_true",
                       help="escribe las secciones a disco")
    parser.add_argument("--juez", action="store_true",
                       help="corre el juez sobre las secciones")
    parser.add_argument("--afirmaciones", action="store_true",
                       help="extrae afirmaciones con puerta anti-copia")
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

    if args.dry_run:
        informe = medir(work_dir)
        for lid, d in informe.items():
            print("%s: %d secciones, %d con candidatos, por tipo: %s"
                  % (lid, d["secciones"], d["con_candidatos"],
                     json.dumps(d["por_tipo"], ensure_ascii=False)))
        return 0

    if args.segmentar:
        total = segmentar_a_disco(work_dir)
        print("secciones escritas: %s" % json.dumps(total, ensure_ascii=False))
        return 0

    if args.juez:
        if not _leer_secciones(work_dir):
            segmentar_a_disco(work_dir)
        cliente = None
        if not args.simulado:
            cliente = construir_cliente_endpoints(args.endpoints,
                                                 timeout=args.timeout)
        stats = procesar_juez(work_dir, workers=args.workers,
                             max_llamadas=args.max_llamadas, cliente=cliente,
                             simulado=args.simulado)
        print("juez: %s" % json.dumps(stats, ensure_ascii=False))
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
        print("afirmaciones: %s" % json.dumps(
            {k: v for k, v in stats.items() if k != "descartadas"},
            ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
