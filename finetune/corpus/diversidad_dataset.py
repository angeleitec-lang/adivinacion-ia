#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T106 — Diversidad y balance del dataset de fase 1 (solo lectura; sin red).

Lee un JSONL de lecturas aceptadas (campos: id, bloque, generador,
conversations con roles system/human/gpt y, opcionalmente, calculos) y, si se
indica --jobs-db (por defecto finetune/corpus/jobs.db, abierta en modo
solo-lectura), enriquece cada lectura con el payload estructurado de la tarea
unido por id. Cuando el payload no está disponible, se analiza el texto del
prompt (fallback por regex sobre las líneas de cartas y de contexto).

Mide:
1. Por bloque y global: número de lecturas, longitud (chars y tokens
   estimados: media, p5, p95), proporción multiturno, diversidad léxica
   (type-token ratio; n-gramas de 4 y 6 palabras únicos frente a totales;
   muletillas = n-gramas que aparecen en >5 % de las lecturas del bloque),
   repetición de aperturas y cierres (primeras/últimas 8 palabras, ranking
   top-N), y similitud aproximada entre lecturas del mismo bloque
   (Jaccard sobre shingles de 5 palabras con firma MinHash determinista y
   bandas LSH) con pares casi duplicados y recuento de lecturas que se
   perderían al filtrar con umbrales 0.80 / 0.90 / 0.95.
2. Balance de contenido: frecuencia de las 78 cartas del tarot y de los 40
   naipes de la baraja española (y porcentaje de invertidas), signos solares
   y ascendentes, números de camino de vida, contextos de consulta, tipos de
   pregunta (plantilla fija de generate_tasks.py o libre), casos éticos o
   fuera de alcance por palabras clave, y huecos (cartas o números ausentes,
   bloques del jobs.db sin lecturas aceptadas).

No modifica ningún fichero de entrada. Los tests usan datos sintéticos.

Uso:
    python finetune/corpus/diversidad_dataset.py \
        --jsonl /ruta/aceptadas_snapshot.jsonl \
        --out /ruta/informe_diversidad.json \
        --md /ruta/informe_diversidad.md
"""
import argparse
import collections
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cartas  # noqa: E402  (índices canónicos de 78 tarot y 40 españoles)

# --------------------------------------------------------------------------
# Constantes de las medidas (documentadas en docs/DIVERSIDAD_DATASET.md)
# --------------------------------------------------------------------------
PALABRAS_EXTREMO = 8          # aperturas y cierres: primeras/últimas 8 palabras
NGRAMS = (4, 6)               # longitudes de n-grama para diversidad léxica
MULETILLA_MIN_FRAC = 0.05     # n-grama en >5 % de las lecturas = muletilla
MULETILLA_MIN_DOCS = 2        # y en al menos 2 lecturas
SHINGLE_PALABRAS = 5          # shingles de 5 palabras para Jaccard
SHINGLE_MAX = 240             # máximo de shingles por lectura (muestreo con paso)
MINHASH_K = 16                # permutaciones de la firma MinHash
LSH_BANDS = 8                 # bandas de la firma (LSH_BANDS x LSH_ROWS = MINHASH_K)
LSH_ROWS = 2
UMBRAL_CASI_DUP = 0.75        # pares "casi duplicados" reportados
UMBRALES_DEDUP = (0.80, 0.90, 0.95)  # umbrales del filtro de duplicados propuesto
TOKENS_POR_PALABRA = 1.35     # estimación determinista de tokens (español ~1.3-1.4)

SIGNOS_ESPERADOS = ["Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo",
                    "Libra", "Escorpio", "Sagitario", "Capricornio", "Acuario",
                    "Piscis"]
CAMINOS_ESPERADOS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 22, 33]
CONTEXTOS_ESPERADOS = ["amor", "trabajo", "dinero", "salud", "espiritual",
                       "general"]
# Plantillas fijas de generate_tasks.py (solo lectura; si cambia el generador,
# este conjunto es orientativo: las preguntas fuera de él se marcan como libres).
PREGUNTAS_FIJIAS = {
    "¿Qué energía hay en mi vida sentimental ahora mismo?",
    "Tengo una relación que me tiene confundida, ¿qué me dice esta carta?",
    "¿Voy a encontrar pareja en los próximos meses?",
    "¿Cómo puedo mejorar la comunicación con mi pareja?",
    "¿Qué me espera en el trabajo en los próximos meses?",
    "¿Me conviene aceptar la oferta que me han hecho?",
    "¿Cómo puedo desbloquear mi carrera profesional?",
    "¿Hay cambios laborales cerca para mí?",
    "¿Qué dice esta carta sobre mis finanzas actuales?",
    "¿Es buen momento para una inversión o un cambio económico?",
    "¿Cómo puedo salir de esta situación económica?",
    "¿Voy a mejorar mis ingresos este año?",
    "¿Qué energía rodea mi bienestar físico y emocional?",
    "¿Qué necesito atender de mi salud en esta etapa?",
    "¿Por qué me siento tan agotada últimamente?",
    "¿Qué debería cambiar en mis hábitos?",
    "¿Qué aprendizaje espiritual me trae esta etapa?",
    "¿Qué debo soltar para avanzar?",
    "¿Qué me quiere decir el universo con esta situación?",
    "¿Cómo conecto con mi propósito?",
    "¿Qué necesito saber en este momento?",
    "¿Cuál es el tema central de mi vida ahora?",
    "¿Qué me conviene priorizar este mes?",
    "¿Qué bloqueo me está frenando?",
}
# Pistas de casos éticos / fuera de alcance (búsqueda en la pregunta y en el
# prompt humano; los bloques "etica" se cuentan aparte).
CLAVES_ETICA = {
    "salud_grave": ["cáncer", "cancer", "tumor", "bulto", "biopsia", "quimio",
                    "metástasis", "metastasis", "sida", "vih", "diagnóstico",
                    "diagnostico", "va a morir", "se muere"],
    "muerte_duelo": ["morir", "muerte", "fallecer", "fallecimiento", "velorio",
                     "suicid", "matarse", "cadáver", "cadaver"],
    "salud_mental": ["depresión", "depresion", "deprimid", "trastorno",
                     "ansiedad", "medicación", "medicacion", "psiquiatra",
                     "psicólogo", "psicologo", "pánico", "panico"],
    "embarazo_reproduccion": ["embaraz", "abort", "fecundación", "fecundacion",
                              "óvulo", "ovulo", "gestación", "gestacion"],
    "violencia_legal": ["maltrat", "violencia", "abus", "agresión", "agresion",
                        "denuncia", "demanda", "juicio", "cárcel", "carcel",
                        "abogado", "custodia", "estafa", "ruina"],
    "adicciones": ["alcohol", "droga", "cocaína", "heroína", "juego "
                   "patológico", "apuesta", "apuestas", "adicción"],
    "muerte_terceros": ["mi padre va a morir", "mi madre va a morir",
                        "mi hijo va a morir", "mi hija va a morir"],
}

PALABRA_RE = re.compile(r"\w+", re.UNICODE)
# Pregunta entre comillas tras "Pregunta del consultante:" (no codicia: se
# detiene en la primera comilla de cierre; las plantillas no llevan comillas
# internas).
PREGUNTA_RE = re.compile(r'Pregunta del consultante:\s*"(.+?)"', re.S)
CONTEXTO_RE = re.compile(r"^Contexto:\s*([a-záéíóúñ]+)", re.M)
# Fallback de cartas en el prompt: líneas "Carta[ N]: Nombre (orientada)" o
# "posición: Nombre (orientada)" (etiqueta en minúsculas), fuera de Referencia
# y del ESQUEMA OBLIGATORIO.
CARTA_LINEA_RE = re.compile(
    r"^(?:Carta(?:\s*\d+)?|[a-záéíóúüñ]+(?:\s+[a-záéíóúüñ]+)*):\s*"
    r"([A-ZÁÉÍÓÚÜÑa-záéíóúüñ ]+)\s*\((invertida|al derecho)\)\s*$", re.M)


# --------------------------------------------------------------------------
# Utilidades deterministas
# --------------------------------------------------------------------------
def sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def tokenize(texto):
    """Palabras en minúscula sin acentos (útil para recuento estable de
    aperturas, n-gramas y shingles)."""
    return [sin_acentos(w.lower()) for w in PALABRA_RE.findall(texto)]


def estimar_tokens(texto):
    """Tokens ≈ 1.35 por palabra (aproximación determinista, sin tokenizador)."""
    n = len(PALABRA_RE.findall(texto))
    return max(1, int(round(n * TOKENS_POR_PALABRA))) if n else 0


def percentil(vals, q):
    """Percentil lineal determinista (interpolación entre ordenadas)."""
    if not vals:
        return None
    vs = sorted(vals)
    idx = (len(vs) - 1) * q
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return float(vs[lo])
    return vs[lo] + (vs[hi] - vs[lo]) * (idx - lo)


def resumen_longitud(vals):
    vals = list(vals)
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "media": round(sum(vals) / len(vals), 1),
        "p5": round(percentil(vals, 0.05), 1),
        "p95": round(percentil(vals, 0.95), 1),
        "min": min(vals),
        "max": max(vals),
    }


def _hash_shingle(palabras):
    return int.from_bytes(
        hashlib.sha256(" ".join(palabras).encode("utf-8")).digest()[:8], "big")


def shingle_hashes(tokens, ancho=SHINGLE_PALABRAS, maximo=SHINGLE_MAX):
    """Set de hashes de shingles de `ancho` palabras; si hay más de `maximo`,
    se muestrean con paso uniforme (determinista)."""
    n_sh = max(0, len(tokens) - ancho + 1)
    if n_sh == 0:
        return set()
    paso = 1 if n_sh <= maximo else math.ceil(n_sh / maximo)
    out = set()
    for i in range(0, n_sh, paso):
        out.add(_hash_shingle(tokens[i:i + ancho]))
    return out


def jaccard(sets_a, sets_b):
    if not sets_a or not sets_b:
        return 0.0
    inter = len(sets_a & sets_b)
    union = len(sets_a | sets_b)
    return inter / union if union else 0.0


# --- MinHash determinista --------------------------------------------------
def _coeficientes(k=MINHASH_K, seed=20261021):
    """(a, b) fijos derivados de sha256(seed): sin random, estable entre runs."""
    primos = (1 << 61) - 1
    coefs = []
    for i in range(k):
        h = hashlib.sha256(("t106-%d-%d" % (seed, i)).encode()).digest()
        a = int.from_bytes(h[:8], "big") % (primos - 1) + 1
        b = int.from_bytes(h[8:16], "big") % primos
        coefs.append((a, b))
    return coefs


COEFICIENTES = _coeficientes()
_PRIMO_61 = (1 << 61) - 1


def minhash_firma(sh_set, coefs=COEFICIENTES):
    if not sh_set:
        return tuple([0] * len(coefs))
    firma = []
    for a, b in coefs:
        firma.append(min((a * h + b) % _PRIMO_61 for h in sh_set))
    return tuple(firma)


def lsh_pares_candidatos(sigs, bands=LSH_BANDS, rows=LSH_ROWS):
    """Pares (i, j), i<j, que comparten al menos una banda."""
    cubos = collections.defaultdict(list)
    for i, sig in enumerate(sigs):
        for banda in range(bands):
            clave = (banda, sig[banda * rows:(banda + 1) * rows])
            cubos[clave].append(i)
    pares = set()
    for idxs in cubos.values():
        if len(idxs) < 2:
            continue
        idxs = sorted(idxs)
        if len(idxs) > 600:
            # Cúmulo gigante: las comparaciones exactas se harían igual, pero
            # acotamos el materializado (se avisa en el informe).
            idxs = idxs[:600]
        for x in range(len(idxs)):
            for y in range(x + 1, len(idxs)):
                pares.add((idxs[x], idxs[y]))
    return sorted(pares)


def dedup_greedy(n, sim_pares, umbral):
    """Conserva lecturas en orden de id; descarta la que supera el umbral con
    alguna ya conservada. Devuelve (perdidas, conservadas)."""
    vecinos = collections.defaultdict(list)
    for i, j, s in sim_pares:
        if s >= umbral:
            vecinos[i].append(j)
            vecinos[j].append(i)
    kept = set()
    perdidas = 0
    for idx in range(n):
        if any(k in kept for k in vecinos[idx]):
            perdidas += 1
        else:
            kept.add(idx)
    return perdidas, len(kept)


# --------------------------------------------------------------------------
# Lectura de datos
# --------------------------------------------------------------------------
def iter_lecturas(ruta):
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea, txt in enumerate(fh, 1):
            txt = txt.strip()
            if not txt:
                continue
            try:
                yield linea, json.loads(txt)
            except json.JSONDecodeError:
                continue


def aplanar(d):
    """Dict normalizado por lectura con texto human/gpt y banderas."""
    convs = d.get("conversations") or []
    humans = [c.get("value", "") for c in convs if c.get("from") == "human"]
    gpts = [c.get("value", "") for c in convs if c.get("from") == "gpt"]
    return {
        "id": d.get("id"),
        "bloque": d.get("bloque") or "sin_bloque",
        "generador": d.get("generador"),
        "human": humans[0] if humans else "",
        "humans_juntos": "\n".join(humans),
        "respuesta": "\n".join(gpts),
        "respuesta_final": gpts[-1] if gpts else "",
        "n_human": len(humans),
        "multiturno": len(humans) > 1,
        "calculos": d.get("calculos") or {},
    }


def payloads_desde_jobs(db_path):
    """{id: payload_dict} desde jobs.db en modo lectura; {} si no existe."""
    if not db_path or not os.path.exists(db_path):
        return {}
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
        cur = con.cursor()
        out = {}
        for jid, payload in cur.execute("SELECT id, payload FROM jobs"):
            if not payload:
                continue
            try:
                out[jid] = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                continue
        con.close()
        return out
    except sqlite3.Error:
        return {}


def bloques_en_jobs(db_path):
    if not db_path or not os.path.exists(db_path):
        return []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
        cur = con.cursor()
        filas = cur.execute("SELECT bloque, COUNT(*) FROM jobs GROUP BY bloque"
                            " ORDER BY 2 DESC").fetchall()
        con.close()
        return filas
    except sqlite3.Error:
        return []


# --------------------------------------------------------------------------
# Diversidad léxica
# --------------------------------------------------------------------------
def ttr(respuestas):
    tokens = []
    for r in respuestas:
        tokens.extend(tokenize(r))
    if not tokens:
        return {"tokens": 0, "tipos": 0, "ttr": None}
    tipos = len(set(tokens))
    return {"tokens": len(tokens), "tipos": tipos,
            "ttr": round(tipos / len(tokens), 4)}


def ngram_diversidad(tokens_por_lectura, n):
    """Únicos (tipos) frente a apariciones totales, por bloque."""
    total = 0
    counter = collections.Counter()
    for toks in tokens_por_lectura:
        for i in range(len(toks) - n + 1):
            total += 1
            counter[tuple(toks[i:i + n])] += 1
    unicos = len(counter)
    return {"n": n, "total": total, "unicos": unicos,
            "frac_unicos": round(unicos / total, 4) if total else None}


def muletillas(tokens_por_lectura, n, min_frac=MULETILLA_MIN_FRAC,
               min_docs=MULETILLA_MIN_DOCS):
    """N-gramas de n palabras que aparecen en más de min_frac de las lecturas."""
    ndocs = len(tokens_por_lectura)
    df = collections.Counter()
    for toks in tokens_por_lectura:
        vistos = set()
        for i in range(len(toks) - n + 1):
            vistos.add(tuple(toks[i:i + n]))
        df.update(vistos)
    if ndocs == 0:
        return []
    out = [(gram, cnt, cnt / ndocs) for gram, cnt in df.items()
           if cnt >= min_docs and cnt / ndocs > min_frac]
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def extremos(tokens, k=PALABRAS_EXTREMO, primera=True):
    if not tokens or len(tokens) < k:
        return None
    trozo = tokens[:k] if primera else tokens[-k:]
    return " ".join(trozo)


def ranking_extremos(textos, k=PALABRAS_EXTREMO, primera=True):
    counter = collections.Counter()
    for t in textos:
        e = extremos(tokenize(t), k, primera)
        if e:
            counter[e] += 1
    return counter


# --------------------------------------------------------------------------
# Similitud y duplicados
# --------------------------------------------------------------------------
def firmas_por_lectura(respuestas):
    return [shingle_hashes(tokenize(r)) for r in respuestas]


def pares_similares(sets_shingles, sigs=None):
    """Pares candidatos (LSH) con Jaccard exacto sobre los sets de shingles."""
    if sigs is None:
        sigs = [minhash_firma(s) for s in sets_shingles]
    out = []
    for i, j in lsh_pares_candidatos(sigs):
        s = jaccard(sets_shingles[i], sets_shingles[j])
        if s > 0:
            out.append((i, j, s))
    return out


def resumen_duplicados(pares, n_lecturas):
    bins = {">=0.95": 0, "0.90-0.95": 0, "0.80-0.90": 0, "0.75-0.80": 0}
    afectados = {">=0.90": set(), ">=0.75": set()}
    for _i, _j, s in pares:
        if s >= 0.95:
            bins[">=0.95"] += 1
        elif s >= 0.90:
            bins["0.90-0.95"] += 1
        elif s >= 0.80:
            bins["0.80-0.90"] += 1
        elif s >= UMBRAL_CASI_DUP:
            bins["0.75-0.80"] += 1
        if s >= 0.90:
            afectados[">=0.90"].update((_i, _j))
        if s >= UMBRAL_CASI_DUP:
            afectados[">=0.75"].update((_i, _j))
    perdidas = {("%.2f" % u): dedup_greedy(n_lecturas, pares, u)[0]
                for u in UMBRALES_DEDUP}
    return {
        "pares_por_bin": bins,
        "pares_casi_dup": sum(bins.values()),
        "lecturas_afectadas_090": len(afectados[">=0.90"]),
        "lecturas_afectadas_075": len(afectados[">=0.75"]),
        "perdidas_dedup": perdidas,
        "n_lecturas": n_lecturas,
    }


# --------------------------------------------------------------------------
# Balance de contenido
# --------------------------------------------------------------------------
def mazo_de_bloque(bloque):
    return "espanol" if (bloque or "").startswith("espanola") else "tarot"


def _indice_cartas(mazo):
    catalogo = cartas.CARTAS_TAROT if mazo == "tarot" else cartas.NAIPES_ESPANOLES
    por_nombre = {}
    for c in catalogo:
        claves = [c["nombre"]] + list(c.get("sinonimos") or [])
        for k in claves:
            por_nombre[sin_acentos(str(k)).lower()] = c
    return por_nombre


_INDICES = {"tarot": _indice_cartas("tarot"), "espanol": _indice_cartas("espanol")}


def normalizar_nombre_carta(nombre, mazo):
    c = _INDICES[mazo].get(sin_acentos(str(nombre)).lower().strip())
    return c["nombre"] if c else None


def cartas_de_payload(payload, mazo):
    """[(nombre_canonico, invertida)] desde el payload estructurado."""
    out = []
    if not payload:
        return out
    items = []
    if isinstance(payload.get("carta"), dict) and "nombre" in payload["carta"]:
        items.append(payload["carta"])
    for c in payload.get("cartas") or []:
        if isinstance(c, dict) and "nombre" in c:
            items.append(c)
    for c in items:
        nom = normalizar_nombre_carta(c["nombre"], mazo)
        if nom is None:
            nom = str(c["nombre"])
        out.append((nom, bool(c.get("invertida"))))
    return out


def _region_cartas_prompt(human):
    """Texto del prompt sin Referencia ni ESQUEMA OBLIGATORIO (evita contar
    las repeticiones de la plantilla)."""
    corte = human.find("Referencia (")
    if corte >= 0:
        human = human[:corte]
    corte = human.find("ESQUEMA OBLIGATORIO")
    if corte >= 0:
        human = human[:corte]
    return human


def cartas_de_prompt(human, mazo):
    out = []
    for m in CARTA_LINEA_RE.finditer(_region_cartas_prompt(human)):
        nom = normalizar_nombre_carta(m.group(1).strip(), mazo) or m.group(1).strip()
        out.append((nom, m.group(2) == "invertida"))
    return out


def extraer_pregunta(human):
    m = PREGUNTA_RE.search(human)
    if not m:
        return None
    q = m.group(1).strip().strip('"').strip()
    return q or None


def extraer_contexto(human, payload):
    if isinstance(payload, dict) and payload.get("contexto"):
        return str(payload["contexto"]).lower()
    if isinstance(payload, dict) and payload.get("tema"):
        return "etica:%s" % str(payload["tema"]).lower()
    m = CONTEXTO_RE.search(_region_cartas_prompt(human))
    return m.group(1).lower() if m else None


def clasificar_pregunta(q):
    """Tipo de pregunta por su primer interrogativo (sin acentos)."""
    if not q:
        return "sin_pregunta"
    texto = sin_acentos(q.strip().lower())
    interior = texto.split("¿", 1)[1] if "¿" in texto else texto
    primera = interior.strip().split()
    if not primera:
        return "otra"
    w0 = primera[0].strip(",.:;")
    mapa = {"como": "cómo", "que": "qué", "cual": "cuál", "cuales": "cuáles",
            "cuando": "cuándo", "donde": "dónde", "adonde": "adónde",
            "quien": "quién", "quienes": "quiénes"}
    if w0 == "por" and len(primera) > 1 and primera[1].strip(",.:;") == "que":
        return "por_qué"
    if w0 in mapa:
        return mapa[w0]
    if texto.lstrip("¡! ").startswith("¿") or "¿" in texto:
        return "si_no"
    return "otra"


def _norm_pregunta(q):
    return sin_acentos(q.strip().lower()).strip("¿?¡! ").strip()


PREGUNTAS_FIJIAS_NORM = {_norm_pregunta(p) for p in PREGUNTAS_FIJIAS}


def es_pregunta_fija(q):
    if not q:
        return False
    return _norm_pregunta(q) in PREGUNTAS_FIJIAS_NORM


def claves_etica_detectadas(*textos):
    plano = " ".join(sin_acentos(t.lower()) for t in textos if t)
    found = []
    for tema, claves in CLAVES_ETICA.items():
        for c in claves:
            cc = sin_acentos(c.lower())
            if cc in plano:
                found.append(tema)
                break
    return found


def signos_de_calculos(calculos):
    """([(fuente, signo)], [camino_de_vida]) desde el campo calculos."""
    signos, caminos = [], []
    if not isinstance(calculos, dict):
        return signos, caminos

    def una(cn):
        if not isinstance(cn, dict):
            return
        sol = (cn.get("planetas") or {}).get("Sol")
        if isinstance(sol, dict) and sol.get("signo"):
            signos.append(("sol", sol["signo"]))
        asc = cn.get("ascendente")
        if isinstance(asc, dict) and asc.get("signo"):
            signos.append(("ascendente", asc["signo"]))

    una(calculos.get("carta_natal"))
    for letra in ("a", "b"):
        if isinstance(calculos.get(letra), dict):
            una(calculos[letra])
    num = calculos.get("numerologia")
    if isinstance(num, dict) and num.get("camino_de_vida") is not None:
        caminos.append(num["camino_de_vida"])
    return signos, caminos


# --------------------------------------------------------------------------
# Análisis completo
# --------------------------------------------------------------------------
def analizar(jsonl_path, jobs_db=None, top=20):
    payloads = payloads_desde_jobs(jobs_db)
    lecturas = []
    ids_repetidos = 0
    vistos = set()
    for _linea, d in iter_lecturas(jsonl_path):
        rec = aplanar(d)
        if rec["id"] is not None and rec["id"] in vistos:
            ids_repetidos += 1
        vistos.add(rec["id"])
        rec["payload"] = payloads.get(rec["id"])
        rec["tiene_payload"] = rec["payload"] is not None
        lecturas.append(rec)

    por_bloque = collections.defaultdict(list)
    for r in lecturas:
        por_bloque[r["bloque"]].append(r)

    informe = {
        "meta": {
            "jsonl": os.path.abspath(jsonl_path),
            "jsonl_sha256": sha256_de(jsonl_path),
            "jobs_db": os.path.abspath(jobs_db) if jobs_db else None,
            "n_lecturas": len(lecturas),
            "n_con_payload": sum(1 for r in lecturas if r["tiene_payload"]),
            "ids_repetidos": ids_repetidos,
            "constantes": {
                "palabras_extremo": PALABRAS_EXTREMO, "ngrams": list(NGRAMS),
                "muletilla_min_frac": MULETILLA_MIN_FRAC,
                "shingle_palabras": SHINGLE_PALABRAS,
                "shingle_max": SHINGLE_MAX, "minhash_k": MINHASH_K,
                "lsh_bands": LSH_BANDS, "lsh_rows": LSH_ROWS,
                "tokens_por_palabra": TOKENS_POR_PALABRA,
            },
        },
        "global": {},
        "bloques": {},
        "balance": {},
        "huecos": {},
    }

    def medidas(resps, resps_final=None):
        tokens = [tokenize(r) for r in resps]
        chars = [len(r) for r in (resps_final or resps)]
        toks_est = [estimar_tokens(r) for r in (resps_final or resps)]
        m = {
            "n": len(resps),
            "longitud_chars": resumen_longitud(chars),
            "longitud_tokens_est": resumen_longitud(toks_est),
            "ttr": ttr(resps),
            "ngrams": [ngram_diversidad(tokens, n) for n in NGRAMS],
        }
        mults = {}
        for n in NGRAMS:
            lista = muletillas(tokens, n)
            m["n_muletillas_%d" % n] = len(lista)
            mults[n] = lista
        ap = ranking_extremos(resps)
        cie = ranking_extremos([r for r in (resps_final or resps)])
        m["top_aperturas"] = [{"apertura": a, "n": c,
                               "frac": round(c / len(resps), 4) if resps else 0}
                              for a, c in ap.most_common(top)]
        m["top_cierres"] = [{"cierre": a, "n": c,
                             "frac": round(c / len(resps), 4) if resps else 0}
                            for a, c in cie.most_common(top)]
        return m, mults

    # --- por bloque --------------------------------------------------------
    muletillas_globales = {n: collections.Counter() for n in NGRAMS}
    for bloque in sorted(por_bloque):
        rs = por_bloque[bloque]
        resps = [r["respuesta"] for r in rs]
        m, mults = medidas(resps, [r["respuesta_final"] for r in rs])
        m["multiturno_frac"] = round(
            sum(1 for r in rs if r["multiturno"]) / len(rs), 4) if rs else 0
        sh_sets = firmas_por_lectura(resps)
        pares = pares_similares(sh_sets)
        m["duplicados"] = resumen_duplicados(pares, len(rs))
        m["generadores"] = dict(collections.Counter(
            r["generador"] for r in rs))
        m["payload_frac"] = round(
            sum(1 for r in rs if r["tiene_payload"]) / len(rs), 4) if rs else 0
        informe["bloques"][bloque] = m
        for n in NGRAMS:
            for gram, cnt, frac in mults[n]:
                muletillas_globales[n][(bloque, gram)] = max(
                    muletillas_globales[n].get((bloque, gram), 0), cnt)

    # --- global ------------------------------------------------------------
    resps = [r["respuesta"] for r in lecturas]
    m, _mults = medidas(resps, [r["respuesta_final"] for r in lecturas])
    m["multiturno_frac"] = round(
        sum(1 for r in lecturas if r["multiturno"]) / len(lecturas), 4
    ) if lecturas else 0
    # Duplicados cruzando bloques (para el filtro global propuesto)
    sh_all = [s for b in sorted(por_bloque)
              for s in firmas_por_lectura(
                  [r["respuesta"] for r in por_bloque[b]])]
    bloque_all = [b for b in sorted(por_bloque) for _ in por_bloque[b]]
    sig_all = [minhash_firma(s) for s in sh_all]
    pares_glob = []
    for i, j in lsh_pares_candidatos(sig_all):
        s = jaccard(sh_all[i], sh_all[j])
        if s >= UMBRAL_CASI_DUP:
            pares_glob.append((i, j, s))
    m["duplicados_entre_bloques"] = {
        "pares_ge_075": len(pares_glob),
        "pares_mismo_bloque": sum(1 for _i, _j, _s in pares_glob
                                 if bloque_all[_i] == bloque_all[_j]),
    }
    informe["global"] = m
    informe["muletillas"] = {
        str(n): [{"bloque": b, "ngrama": " ".join(g), "n": c}
                 for (b, g), c in sorted(
                     muletillas_globales[n].items(),
                     key=lambda x: -x[1])[:top]]
        for n in NGRAMS}

    # --- balance -----------------------------------------------------------
    freq_tarot = collections.Counter()
    inv_tarot = collections.Counter()
    freq_espanol = collections.Counter()
    inv_espanol = collections.Counter()
    contextos = collections.Counter()
    contextos_bloque = collections.defaultdict(collections.Counter)
    tipos = collections.Counter()
    preguntas = collections.Counter()
    preguntas_fijas = 0
    preguntas_tot = 0
    signos_sol = collections.Counter()
    signos_asc = collections.Counter()
    caminos = collections.Counter()
    etica_bloque = 0
    etica_claves = collections.Counter()
    etica_ejemplos = []

    for r in lecturas:
        mazo = mazo_de_bloque(r["bloque"])
        cs = cartas_de_payload(r["payload"], mazo)
        origen = "payload"
        if not cs:
            cs = cartas_de_prompt(r["human"], mazo)
            origen = "prompt"
        freq = freq_tarot if mazo == "tarot" else freq_espanol
        inv = inv_tarot if mazo == "tarot" else inv_espanol
        for nom, invertida in cs:
            freq[nom] += 1
            if invertida:
                inv[nom] += 1
        ctx = extraer_contexto(r["human"], r["payload"])
        if ctx:
            contextos[ctx] += 1
            contextos_bloque[r["bloque"]][ctx] += 1
        preg = extraer_pregunta(r["human"])
        if preg:
            preguntas_tot += 1
            preguntas[preg] += 1
            tipos[clasificar_pregunta(preg)] += 1
            if es_pregunta_fija(preg):
                preguntas_fijas += 1
        sg, cms = signos_de_calculos(r["calculos"])
        for fuente, signo in sg:
            (signos_sol if fuente == "sol" else signos_asc)[signo] += 1
        for cval in cms:
            caminos[str(cval)] += 1
        if r["bloque"] == "etica":
            etica_bloque += 1
            temas = claves_etica_detectadas(r["human"])
        else:
            temas = claves_etica_detectadas(preg or "")
        for t in temas:
            etica_claves[t] += 1
        if temas and len(etica_ejemplos) < 15:
            etica_ejemplos.append({"id": r["id"], "bloque": r["bloque"],
                                   "temas": temas,
                                   "pregunta": (preg or "")[:160]})

    def tabla_cartas(freq, inv, catalogo):
        filas = []
        for c in catalogo:
            nom = c["nombre"]
            f_ = freq.get(nom, 0)
            filas.append({"carta": nom, "n": f_,
                          "invertidas": inv.get(nom, 0),
                          "frac": round(f_ / sum(freq.values()), 5)
                          if freq else 0.0})
        return filas

    n_ocurr_tarot = sum(freq_tarot.values())
    n_ocurr_espanol = sum(freq_espanol.values())
    informe["balance"] = {
        "tarot": {
            "n_ocurrencias": n_ocurr_tarot,
            "invertidas": sum(inv_tarot.values()),
            "invertida_frac": round(sum(inv_tarot.values()) / n_ocurr_tarot, 4)
            if n_ocurr_tarot else None,
            "cartas_vistas": len(freq_tarot),
            "mas_frecuentes": [{"carta": c, "n": k}
                               for c, k in freq_tarot.most_common(15)],
            "menos_frecuentes": [{"carta": c, "n": k} for c, k in
                                 sorted(freq_tarot.items(), key=lambda x: x[1])
                                 [:15]],
            "tabla_completa": tabla_cartas(freq_tarot, inv_tarot,
                                           cartas.CARTAS_TAROT),
            "origen": "payload+prompt",
        },
        "espanol": {
            "n_ocurrencias": n_ocurr_espanol,
            "invertidas": sum(inv_espanol.values()),
            "invertida_frac": round(sum(inv_espanol.values()) / n_ocurr_espanol, 4)
            if n_ocurr_espanol else None,
            "cartas_vistas": len(freq_espanol),
            "mas_frecuentes": [{"carta": c, "n": k}
                               for c, k in freq_espanol.most_common(15)],
            "tabla_completa": tabla_cartas(freq_espanol, inv_espanol,
                                           cartas.NAIPES_ESPANOLES),
        },
        "contextos": dict(contextos),
        "contextos_por_bloque": {b: dict(c)
                                 for b, c in contextos_bloque.items()},
        "tipos_pregunta": dict(tipos),
        "preguntas": {
            "distintas": len(preguntas),
            "totales": preguntas_tot,
            "fijas_frac": round(preguntas_fijas / preguntas_tot, 4)
            if preguntas_tot else None,
            "top": [{"pregunta": p, "n": k} for p, k in
                    preguntas.most_common(15)],
        },
        "signos_sol": dict(signos_sol),
        "signos_ascendente": dict(signos_asc),
        "caminos_de_vida": dict(caminos),
        "etica": {
            "bloque_etica_aceptado": etica_bloque,
            "claves_detectadas": dict(etica_claves),
            "ejemplos": etica_ejemplos,
        },
    }

    # --- huecos ------------------------------------------------------------
    ausentes_tarot = [c["nombre"] for c in cartas.CARTAS_TAROT
                      if freq_tarot.get(c["nombre"], 0) == 0]
    raras_tarot = sorted([(c, k) for c, k in freq_tarot.items() if k <= 2],
                         key=lambda x: x[1])
    ausentes_espanol = [c["nombre"] for c in cartas.NAIPES_ESPANOLES
                        if freq_espanol.get(c["nombre"], 0) == 0]
    caminos_obs = {int(k) for k in caminos if str(k).lstrip("-").isdigit()}
    hueco_bloques = [b for b, _c in bloques_en_jobs(jobs_db)
                     if b not in por_bloque] if jobs_db else []
    informe["huecos"] = {
        "bloques_sin_aceptadas": hueco_bloques,
        "cartas_tarot_ausentes": ausentes_tarot,
        "cartas_tarot_muy_raras": [{"carta": c, "n": k} for c, k in raras_tarot],
        "naipes_espanoles_ausentes": ausentes_espanol,
        "caminos_de_vida_ausentes": [str(c) for c in CAMINOS_ESPERADOS
                                     if c not in caminos_obs],
        "contextos_ausentes": [c for c in CONTEXTOS_ESPERADOS
                               if contextos.get(c, 0) == 0],
        "signos_sol_ausentes": [s for s in SIGNOS_ESPERADOS
                                if signos_sol.get(s, 0) == 0],
        "signos_asc_ausentes": [s for s in SIGNOS_ESPERADOS
                                if signos_asc.get(s, 0) == 0],
    }
    return informe


def sha256_de(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Render Markdown del informe
# --------------------------------------------------------------------------
def _tabla(cabeceras, filas):
    out = ["| " + " | ".join(cabeceras) + " |",
           "|" + "|".join(["---"] * len(cabeceras)) + "|"]
    for f in filas:
        out.append("| " + " | ".join(str(x) for x in f) + " |")
    return "\n".join(out)


def render_markdown(informe, top_listas=10):
    b = informe["balance"]
    h = informe["huecos"]
    g = informe["global"]
    md = []
    md.append("# Informe de diversidad y balance del dataset (T106)\n")
    md.append("- Fuente: `%s` (sha256 `%s…`)" % (
        informe["meta"]["jsonl"], informe["meta"]["jsonl_sha256"][:16]))
    md.append("- Lecturas: **%d**; con payload unido desde jobs.db: %d; ids "
              "repetidos: %d" % (informe["meta"]["n_lecturas"],
                                 informe["meta"]["n_con_payload"],
                                 informe["meta"]["ids_repetidos"]))
    md.append("- Multiturno global: **%.2f %%**\n" % (100 * g["multiturno_frac"]))

    md.append("## 1. Medidas por bloque\n")
    filas = []
    for bloque, m in sorted(informe["bloques"].items()):
        ng4 = next(x for x in m["ngrams"] if x["n"] == 4)
        ng6 = next(x for x in m["ngrams"] if x["n"] == 6)
        top_ap = m["top_aperturas"][0]["frac"] if m["top_aperturas"] else 0
        top_ci = m["top_cierres"][0]["frac"] if m["top_cierres"] else 0
        filas.append([bloque, m["n"], "%.0f" % m["longitud_chars"]["media"],
                      "%.0f" % m["longitud_tokens_est"]["media"],
                      "%.0f / %.0f" % (m["longitud_chars"]["p5"],
                                       m["longitud_chars"]["p95"]),
                      "%.3f" % (m["ttr"]["ttr"] or 0),
                      "%.3f" % (ng4["frac_unicos"] or 0),
                      "%.3f" % (ng6["frac_unicos"] or 0),
                      m["n_muletillas_4"], m["n_muletillas_6"],
                      "%.1f %%" % (100 * top_ap), "%.1f %%" % (100 * top_ci),
                      "%.2f %%" % (100 * m["multiturno_frac"])])
    md.append(_tabla(["bloque", "n", "chars⌀", "tok⌀", "chars p5/p95", "TTR",
                      "únicas 4g", "únicas 6g", "mulet4", "mulet6",
                      "apertura top", "cierre top", "multiturno"], filas))
    md.append("\n## 2. Duplicados por bloque (Jaccard sobre shingles de %d "
              "palabras, MinHash determinista K=%d)\n" % (
                  SHINGLE_PALABRAS, MINHASH_K))
    filas = []
    for bloque, m in sorted(informe["bloques"].items()):
        d = m["duplicados"]
        filas.append([bloque, d["n_lecturas"],
                      d["pares_por_bin"].get(">=0.95", 0),
                      d["pares_por_bin"].get("0.90-0.95", 0),
                      d["pares_por_bin"].get("0.80-0.90", 0),
                      d["pares_por_bin"].get("0.75-0.80", 0),
                      d["lecturas_afectadas_090"],
                      d["lecturas_afectadas_075"],
                      ", ".join("%s→%d" % (k, v) for k, v in
                                sorted(d["perdidas_dedup"].items()))])
    md.append(_tabla(["bloque", "n", "≥.95", ".90–.95", ".80–.90", ".75–.80",
                      "afd.≥.90", "afd.≥.75", "dedup (umbral→perdidas)"], filas))
    md.append("\nParejas casi duplicadas cruzando bloques (≥0.75): %d, de las "
              "cuales mismo bloque: %d.\n" % (
                  g["duplicados_entre_bloques"]["pares_ge_075"],
                  g["duplicados_entre_bloques"]["pares_mismo_bloque"]))

    md.append("## 3. Muletillas (n-gramas en >%d %% de las lecturas de su "
              "bloque)\n" % (100 * MULETILLA_MIN_FRAC))
    for n in (str(4), str(6)):
        filas = [[x["bloque"], "`%s`" % x["ngrama"], x["n"]]
                 for x in informe["muletillas"][n][:top_listas]]
        md.append("**4-gramas:**\n") if n == "4" else md.append("**6-gramas:**\n")
        md.append(_tabla(["bloque", "ngrama", "lecturas"], filas))
        md.append("")

    md.append("## 4. Aperturas y cierres más frecuentes (top %d global)\n" % top_listas)
    filas = [[ "`%s`" % x["apertura"], x["n"], "%.1f %%" % (100 * x["frac"])]
             for x in g["top_aperturas"][:top_listas]]
    md.append(_tabla(["apertura (8 primeras palabras)", "n", "frac"], filas))
    md.append("")
    filas = [["`%s`" % x["cierre"], x["n"], "%.1f %%" % (100 * x["frac"])]
             for x in g["top_cierres"][:top_listas]]
    md.append(_tabla(["cierre (8 últimas palabras)", "n", "frac"], filas))
    md.append("")

    md.append("## 5. Balance de contenido\n")
    t = b["tarot"]
    md.append("### Tarot (78 cartas)\n")
    md.append("- Ocurrencias totales: %d; vistas: %d/78; invertidas: %.1f %%" % (
        t["n_ocurrencias"], t["cartas_vistas"],
        100 * (t["invertida_frac"] or 0)))
    filas = [[x["carta"], x["n"]] for x in t["mas_frecuentes"]]
    md.append("\n**Más frecuentes:**\n")
    md.append(_tabla(["carta", "n"], filas))
    filas = [[x["carta"], x["n"]] for x in t["menos_frecuentes"]]
    md.append("\n**Menos frecuentes (dentro de las vistas):**\n")
    md.append(_tabla(["carta", "n"], filas))
    md.append("\n### Baraja española (40 naipes)\n")
    e = b["espanol"]
    md.append("- Ocurrencias: **%d** — lecturas aceptadas con naipes españoles:"
              " %s\n" % (e["n_ocurrencias"],
                         "ninguna" if e["n_ocurrencias"] == 0 else
                         "%d cartas vistas" % e["cartas_vistas"]))
    md.append("### Signos, caminos de vida y contextos\n")
    filas = [[s, b["signos_sol"].get(s, 0), b["signos_ascendente"].get(s, 0)]
             for s in SIGNOS_ESPERADOS]
    md.append(_tabla(["signo", "Sol", "Ascendente"], filas))
    filas = [[c, b["caminos_de_vida"].get(str(c), 0)] for c in CAMINOS_ESPERADOS]
    md.append("\n**Camino de vida (numerología):**\n")
    md.append(_tabla(["número", "lecturas"], filas))
    filas = [[c, b["contextos"].get(c, 0)] for c in
             sorted(b["contextos"], key=lambda k: -b["contextos"][k])]
    md.append("\n**Contextos de consulta:**\n")
    md.append(_tabla(["contexto", "lecturas"], filas))
    filas = [[tp, n] for tp, n in
             sorted(b["tipos_pregunta"].items(), key=lambda x: -x[1])]
    md.append("\n**Tipos de pregunta:**\n")
    md.append(_tabla(["tipo", "lecturas"], filas))
    md.append("\n- Preguntas distintas: %d de %d; coincidencia con plantillas "
              "fijas de generate_tasks.py: %s\n" % (
                  b["preguntas"]["distintas"], b["preguntas"]["totales"],
                  "%.1f %%" % (100 * (b["preguntas"]["fijas_frac"] or 0))))
    filas = [[p["pregunta"][:90], p["n"]] for p in b["preguntas"]["top"][:10]]
    md.append(_tabla(["pregunta", "n"], filas))
    md.append("\n### Casos éticos / fuera de alcance\n")
    et = b["etica"]
    md.append("- Bloque `etica` aceptado: %d lecturas." %
              et["bloque_etica_aceptado"])
    filas = [[k, v] for k, v in sorted(et["claves_detectadas"].items(),
                                       key=lambda x: -x[1])]
    md.append("\n")
    md.append(_tabla(["clave detectada", "lecturas"], filas) if filas
            else "_Sin coincidencias por palabras clave._")
    if et["ejemplos"]:
        md.append("\nEjemplos: " + "; ".join(
            "(%s: «%s» → %s)" % (x["id"], x["pregunta"][:60],
                                  ",".join(x["temas"]))
            for x in et["ejemplos"][:8]))
    md.append("")

    md.append("## 6. Huecos\n")
    if h["bloques_sin_aceptadas"]:
        md.append("- Bloques del jobs.db sin ninguna lectura aceptada: %s" %
                  ", ".join("`%s`" % x for x in h["bloques_sin_aceptadas"]))
    md.append("- Cartas del tarot ausentes (%d): %s" % (
        len(h["cartas_tarot_ausentes"]),
        ", ".join(h["cartas_tarot_ausentes"]) or "ninguna"))
    if h["cartas_tarot_muy_raras"]:
        md.append("- Cartas del tarot con ≤2 apariciones: %s" % ", ".join(
            "%s (%d)" % (x["carta"], x["n"]) for x in
            h["cartas_tarot_muy_raras"]))
    md.append("- Naipes españoles ausentes: %d/40" %
              len(h["naipes_espanoles_ausentes"]))
    md.append("- Caminos de vida ausentes: %s" % (", ".join(
        str(c) for c in h["caminos_de_vida_ausentes"]) or "ninguno"))
    md.append("- Signos solares ausentes: %s; ascendentes: %s" % (
        ", ".join(h["signos_sol_ausentes"]) or "ninguno",
        ", ".join(h["signos_asc_ausentes"]) or "ninguno"))
    md.append("- Contextos ausentes: %s" %
              (", ".join(h["contextos_ausentes"]) or "ninguno"))
    return "\n".join(md) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main(argv=None):
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jsonl", required=True, help="JSONL de lecturas aceptadas")
    ap.add_argument("--jobs-db", default=os.path.join(aqui, "jobs.db"),
                    help="jobs.db para unir payloads por id (lectura; "
                    "'' para desactivar)")
    ap.add_argument("--out", help="escribe el informe JSON en esta ruta")
    ap.add_argument("--md", help="escribe el informe Markdown en esta ruta")
    ap.add_argument("--top", type=int, default=20, help="longitud de rankings")
    args = ap.parse_args(argv)

    informe = analizar(args.jsonl, jobs_db=args.jobs_db or None, top=args.top)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(informe, fh, ensure_ascii=False, indent=1)
        print("JSON:", args.out)
    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(informe, top_listas=min(args.top, 10)))
        print("Markdown:", args.md)
    g = informe["global"]
    print("lecturas=%d multiturno=%.2f%% TTR=%.3f cartas_tarot_vistas=%d "
          "huecos_tarot=%d espanolas=%d" % (
              informe["meta"]["n_lecturas"], 100 * g["multiturno_frac"],
              g["ttr"]["ttr"] or 0, informe["balance"]["tarot"]["cartas_vistas"],
              len(informe["huecos"]["cartas_tarot_ausentes"]),
              informe["balance"]["espanol"]["n_ocurrencias"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
