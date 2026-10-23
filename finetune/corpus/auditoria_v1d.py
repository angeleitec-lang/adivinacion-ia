#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auditoria_v1d.py — Auditoría adversaria independiente del dataset v1d (T135).

Solo lectura del dataset; sin LLM. Detecta defectos que qa_dataset.py no cubre:
fugas cross-split por n-gramas (prompts propios Y respuestas), duplicados y
casi duplicados, calidad del español (portugués/gallego/catalán, restos de
razonamiento, markdown, truncados, tildes), coherencia de datos calculados
(planetas/signos/casas/aspectos/porcentajes/números citados que no están en la
consulta), tiradas inválidas (carta fuera de la baraja correcta, repetidas,
mezcla tarot/española, Referencia vs tirada), fuera_alcance (prompts corruptos,
respuestas que sí responden la técnica prohibida o dan predicciones concretas),
longitudes por familia y secretos/PII.

Uso:
  python auditoria_v1d.py --dataset-dir DIR --kb-dir DIR_KB --salida DIR_SALIDA
                          [--semilla 135]
"""
import argparse
import difflib
import hashlib
import json
import os
import random
import re
import statistics
import unicodedata
from collections import Counter, defaultdict

SEMILLA_DEFAULT = 135
N_GRAM = 12
SIM_PROMPT_MIN = 0.83
SIM_RESP_MIN = 0.86
BOILER_DF_MINI = 3
MAX_HALLAZGOS = 5000
EJEMPLOS_MAX = 5

FIN_PUNTUACION = ('.', '!', '?', '…', '"', "'", '»')
TRUNC_ULTIMAS = {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'u',
                 'e', 'a', 'en', 'de', 'del', 'con', 'por', 'para', 'que', 'al', 'su',
                 'sus', 'lo', 'le', 'les', 'se', 'es', 'son', 'era', 'fue', 'muy', 'mas',
                 'como', 'pero', 'si', 'no', 'tu', 'tus', 'mi', 'mis', 'este', 'esta',
                 'esto', 'the', 'of', 'and', 'to', 'in'}

FAMILIA_POR_BLOQUE = {
    'tarot_1': 'tarot', 'tarot_2': 'tarot', 'tarot_3': 'tarot',
    'tarot_pregunta': 'tarot', 'cruz_celta': 'tarot', 'multiturno': 'multiturno',
    'espanola_1': 'espanola', 'espanola_3': 'espanola', 'espanola_5': 'espanola',
    'espanola_7': 'espanola',
    'astro_natal': 'astrologia', 'sinastria': 'astrologia',
    'revolucion_solar': 'astrologia', 'lectura_completa': 'lectura_completa',
    'numerologia': 'numerologia', 'biorritmos': 'numerologia',
    'transitos': 'transitos', 'fuera_alcance': 'fuera_alcance',
    'etica': 'etica', 'sin_bloque': 'real',
}

BLOQUES_TAROT = {'tarot_1', 'tarot_2', 'tarot_3', 'tarot_pregunta', 'cruz_celta', 'multiturno',
                 'lectura_completa'}
BLOQUES_ESPANOLA = {'espanola_1', 'espanola_3', 'espanola_5', 'espanola_7'}
BLOQUES_ASTRO = {'astro_natal', 'transitos', 'revolucion_solar', 'sinastria', 'lectura_completa'}

RE_TOKENS = re.compile(r'[0-9a-záéíóúüñ¿¡]+')
RE_PREGUNTA = re.compile(r'Pregunta del consultante:\s*"([^"\n]+)"')
RE_ORIENT = r'(?:al derecho|invertida|derecho|invertido)'

SIGNOS_F = ['aries', 'tauro', 'geminis', 'cancer', 'leo', 'virgo', 'libra', 'escorpio',
            'escorpion', 'sagitario', 'capricornio', 'acuario', 'piscis']
PLANETAS_F = ['sol', 'luna', 'mercurio', 'venus', 'marte', 'jupiter', 'saturno', 'urano',
              'neptuno', 'pluton', 'ascendente', 'medio cielo', 'mc', 'nodo', 'nodos']
ASPECTOS_F = ['conjuncion', 'oposicion', 'trigono', 'cuadratura', 'sextil', 'quincunx']

MARKERS_PROMPT = ('referencia (significados', 'esquema obligatorio', 'estilo de esta lectura',
                  'vetos de estilo', 'interpreta', 'responde con', 'explica con claridad',
                  'no inventes', 'estructura de la lectura', 'cierra la', 'ofrece una alternativa',
                  'baraja española de 40 naipes', 'no es tarot ni baraja francesa')

PT_PALABRAS = {'você', 'não', 'são', 'também', 'muito', 'leitura', 'então', 'pra você',
               'não é', 'está a', 'você pode', 'para você'}
GL_PALABRAS = {'despois', 'tamén', 'faise', 'nosas', 'moi', 'isto é', 'non é', 'para min'}
CA_PALABRAS = {'molt', 'també', 'doncs', 'llavors', 'puc', 'aquesta', 'aquell', 'no és'}
EN_COMMON = {'the', 'and', 'you', 'your', 'with', 'this', 'that', 'have', 'will', 'would',
             'about', 'there', 'their', 'what', 'when', 'which', 'while', 'they', 'them',
             'these', 'those', 'from', 'into', 'more', 'most', 'other', 'some', 'such',
             'than', 'then', 'well', 'also', 'just', 'like', 'make', 'made', 'much',
             'must', 'need', 'never', 'once', 'only', 'over', 'own', 'same', 'too',
             'very', 'cant', 'cannot', 'come', 'could', 'day', 'even', 'ever', 'find',
             'give', 'got', 'here', 'home', 'house', 'live', 'look', 'now', 'number',
             'people', 'say', 'see', 'she', 'take', 'think', 'want', 'way', 'who',
             'why', 'work', 'world', 'write', 'years'}
RAZON_PATRONES = ['thinking process', 'step by step', 'i need to', 'let me think']
PLANTILLA_IA_PATRONES = ['asistente de ia', 'as an ai', 'language model', 'i am an ai',
                         'como modelo de lenguaje', 'como ia', 'im an ai', "i'm an ai",
                         'as a language model', 'no tengo cuerpo', 'no puedo vestir',
                         'no puedo oler', 'no tengo manos', 'no puedo tocar',
                         'no puedo percibir']

SK_PATRON = re.compile(r'sk-[A-Za-z0-9_\-]{20,}')
AKIA_PATRON = re.compile(r'AKIA[0-9A-Z]{16}')
BEARER_PATRON = re.compile(r'bearer\s+[a-z0-9._\-]{25,}', re.IGNORECASE)
APIKEY_PATRON = re.compile(r'(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|contrase[ñn]a|password)\s*[:=]\s*\S{6,}')
HEX64_PATRON = re.compile(r'\b[0-9a-f]{64}\b')
JWT_PATRON = re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}')
EMAIL_PATRON = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
TEL_PATRON = re.compile(r'(?:tel[ée]fono|telefono|whatsapp|llamar? al|contactar)\s*[:.]?\s*[+\d][\d\s().+-]{8,}|\+\d{1,3}[\s.]?\d{8,11}')
IP_PATRON = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b')
URL_PATRON = re.compile(r'https?://\S+')

RE_TIRADA = None            # nombres de carta de la KB, con orientación opcional
RE_TIRADA_POSIBLE = None    # nombre genérico capitalizado tras «pos: » (carta inventada)
RE_REF_LINEA = None
DECK_TAROT_NORM = set()
DECK_ESP_NORM = set()
NOMBRES_CANON = {}


def fold(s):
    """minúsculas sin tildes, espacios colapsados (para cotejos deterministas)."""
    d = unicodedata.normalize('NFD', s or '')
    d = ''.join(c for c in d if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', d.lower().strip())


def norm(s):
    s = unicodedata.normalize('NFC', s or '').lower().strip()
    return re.sub(r'\s+', ' ', s)


def tokens_de(s):
    return RE_TOKENS.findall(fold(s))


def limpia_texto(resp):
    """Respuesta sin cabeceras de esquema ## (legítimas en cruz celta) ni negritas."""
    out = re.sub(r'^##\s*\d+\.[^\n]*$', '', resp or '', flags=re.MULTILINE)
    out = out.replace('**', '').replace('##', '')
    return fold(out)


def prompt_propio(texto):
    t = fold(texto)
    cut = len(t)
    for m in MARKERS_PROMPT:
        i = t.find(m)
        if 0 <= i < cut:
            cut = i
    return t[:cut].strip()


def _normcut(texto):
    """Texto normalizado (con tildes) solo hasta el primer marcador de plantilla."""
    t = norm(texto)
    cut = len(t)
    for m in MARKERS_PROMPT:
        i = t.find(m)
        if 0 <= i < cut:
            cut = i
    return t[:cut].strip()


def ngrams(texto, n=N_GRAM):
    toks = tokens_de(texto)
    if len(toks) < n:
        return set()
    return {hashlib.blake2b(' '.join(toks[i:i + n]).encode('utf-8'), digest_size=16).digest()
            for i in range(len(toks) - n + 1)}


def _q(name):
    return re.escape(fold(name)).replace(r'\ ', r'[\s\-]+')


def build_decks(kb_dir):
    """Carga mazos desde la KB y compila las regex de cartas. Devuelve tamaños."""
    global RE_TIRADA, RE_TIRADA_POSIBLE, RE_REF_LINEA
    global DECK_TAROT_NORM, DECK_ESP_NORM, NOMBRES_CANON
    with open(os.path.join(kb_dir, 'tarot.json'), encoding='utf-8') as fh:
        tarot = json.load(fh)
    with open(os.path.join(kb_dir, 'baraja_espanola.json'), encoding='utf-8') as fh:
        esp = json.load(fh)
    t_names = [x['nombre'] for x in tarot['mayores']] + [x['nombre'] for x in tarot['menores']]
    e_names = [x['nombre'] for x in esp['naipes']]
    DECK_TAROT_NORM = {fold(x) for x in t_names}
    DECK_ESP_NORM = {fold(x) for x in e_names}
    for n in set(t_names) | set(e_names):
        NOMBRES_CANON.setdefault(fold(n), n)
    alt = '(?:' + '|'.join(sorted({_q(n) for n in set(t_names) | set(e_names)},
                                  key=len, reverse=True)) + ')'
    pos = r'(?:[^\n:*]{1,30}(?::|\u2014)\s*)?'
    RE_TIRADA = re.compile(
        r'^[ \t]*' + pos + r'\*{0,2}(?P<carta>' + alt + r')\*{0,2}\s*(?:\((?P<orient>' + RE_ORIENT + r')\))?[\.\s]*$',
        re.MULTILINE | re.IGNORECASE)
    RE_TIRADA_POSIBLE = re.compile(
        r'^[ \t]*(?P<pos>[^\n:*]{1,30}(?::|\u2014)\s*)\*{0,2}(?P<carta>[A-ZÁÉÍÓÚ][\wáéíóúñ]+(?:\s+(?:de|del|la|el)\s+[A-ZÁÉÍÓÚ][\wáéíóúñ]+)*)\*{0,2}\s*(?:\((?P<orient>' + RE_ORIENT + r')\))?[\.\s]*$',
        re.MULTILINE)
    RE_REF_LINEA = re.compile(
        r'^[ \t]*[-*]\s*\*{0,2}(?P<carta>' + alt + r')\*{0,2}\s*\((?P<orient>' + RE_ORIENT + r')\)\s*:',
        re.MULTILINE | re.IGNORECASE)
    return {'tarot': len(DECK_TAROT_NORM), 'espanola': len(DECK_ESP_NORM)}


def muestreo_estratificado(filas, semilla=SEMILLA_DEFAULT, tam_por_celda=400):
    """Muestra determinista por (familia, split) para reportar cobertura."""
    celdas = defaultdict(list)
    for f in filas:
        celdas['%s|%s' % (f.get('familiar', 'otros'), f['split'])].append(f)
    muestra = {}
    for k in sorted(celdas):
        rng = random.Random('%s|%d' % (k, semilla))
        items = sorted(celdas[k], key=lambda f: (f['split'], f['idx']))
        muestra[k] = items if len(items) <= tam_por_celda else sorted(
            rng.sample(items, tam_por_celda), key=lambda f: (f['split'], f['idx']))
    return muestra


def _res():
    return {'total': 0, 'conteo': {}, 'ejemplos': []}


def _add(res, categoria, fila, detalle):
    res['total'] += 1
    res['conteo'][categoria] = res['conteo'].get(categoria, 0) + 1
    por_cat = Counter(e['categoria'] for e in res['ejemplos'])
    if len(res['ejemplos']) < EJEMPLOS_MAX and por_cat[categoria] < 2:
        res['ejemplos'].append({'id': fila.get('sid', fila['idx']), 'split': fila['split'],
                                'bloque': fila.get('bloque'), 'categoria': categoria,
                                'detalle': str(detalle)[:240]})


# ---------------------------------------------------------------- 1 fugas

def _pares_similares(filas, key_fn, sim_min):
    """Pares entre splits distintos que comparten muchos n-gramas y son casi idénticos."""
    grams = {}
    for i, f in enumerate(filas):
        if f['split'] in ('val', 'test'):
            grams[i] = ngrams(key_fn(f))
    df_mini = Counter()
    for g in grams.values():
        df_mini.update(g)
    boiler = {g for g, c in df_mini.items() if c >= BOILER_DF_MINI}
    index = defaultdict(list)
    for i, gs in grams.items():
        for g in gs - boiler:
            index[g].append(i)
    out = []
    vistos = set()
    for r, f in enumerate(filas):
        gr = ngrams(key_fn(f)) if r not in grams else grams[r]
        if not gr:
            continue
        grf = gr - boiler
        cand = Counter()
        for g in grf:
            for j in index.get(g, ()):
                if j != r:
                    cand[j] += 1
        for j, cnt in cand.items():
            par = (min(r, j), max(r, j))
            if par in vistos:
                continue
            gj = grams[j] - boiler
            umbral = max(6, min(N_GRAM + 2, int(0.6 * min(len(grf) or 1, len(gj) or 1))))
            if cnt < umbral:
                continue
            ta, tb = key_fn(filas[par[0]]), key_fn(filas[par[1]])
            sm = difflib.SequenceMatcher(None, ta[:4000], tb[:4000])
            if sm.quick_ratio() < sim_min:
                continue
            if sm.ratio() >= sim_min:
                vistos.add(par)
                out.append((par[0], par[1], cnt, round(sm.ratio(), 3)))
                if len(out) >= MAX_HALLAZGOS // 10:
                    return out
    return out


def check_fugas(filas, semilla=SEMILLA_DEFAULT):
    res_p, res_r = _res(), _res()
    for i, j, n, sim in _pares_similares(filas, lambda f: prompt_propio(f['humano']), SIM_PROMPT_MIN):
        a, b = filas[i], filas[j]
        _add(res_p, 'prompt_casi_identico_cross_split', a,
             '%d n-gramas compartidos, similitud %.2f con %s' % (n, sim, b['sid']))
    for i, j, n, sim in _pares_similares(filas, lambda f: limpia_texto(f['respuesta']), SIM_RESP_MIN):
        a, b = filas[i], filas[j]
        _add(res_r, 'respuesta_casi_identica_cross_split', a,
             '%d n-gramas compartidos, similitud %.2f con %s' % (n, sim, b['sid']))
    return {'fugas_prompt': res_p, 'fugas_respuesta': res_r}


# ---------------------------------------------------------------- 2 duplicados

def _hash_norm(t):
    return hashlib.blake2b(fold(t).encode('utf-8'), digest_size=16).digest()


def check_duplicados(filas, semilla=SEMILLA_DEFAULT):
    res_exacto, res_resp, res_par = _res(), _res(), _res()
    grupos = defaultdict(list)
    for f in filas:
        grupos[_hash_norm(f['humano'] + '\x00' + f['respuesta'])].append(f)
    for h in sorted(grupos, key=lambda x: -len(grupos[x])):
        fs = grupos[h]
        if len(fs) > 1:
            splits = ','.join(sorted({x['split'] for x in fs}))
            for x in fs:
                _add(res_exacto, 'fila_duplicada_exacta', x,
                     'fila repetida %d veces (splits %s); primera %s' % (len(fs), splits, fs[0]['sid']))
    g_resp = defaultdict(list)
    for f in filas:
        if len(norm(f['respuesta'])) >= 40:
            g_resp[_hash_norm(f['respuesta'])].append(f)
    for h, fs in g_resp.items():
        if len(fs) > 1:
            _add(res_resp, 'respuesta_en_varias_filas', fs[0],
                 'misma respuesta en %d filas: %s' % (len(fs), ', '.join(x['sid'] for x in fs[:4])))
    g_prom = defaultdict(list)
    for f in filas:
        pp = prompt_propio(f['humano'])
        if len(pp) >= 40:
            g_prom[_hash_norm(pp)].append(f)
    vistos = set()
    for h, fs in g_prom.items():
        if len(fs) < 2 or len({fold(x['respuesta']) for x in fs}) < 2:
            continue
        for x in fs:
            if x['sid'] in vistos:
                continue
            vistos.add(x['sid'])
            _add(res_par, 'misma_pregunta_distintas_respuestas', x,
                 'prompt propio idéntico con %d respuestas: %s' %
                 (len(fs), ', '.join(y['sid'] for y in fs[:4])))
    return {'duplicados_exactos': res_exacto,
            'respuesta_en_varias_filas': res_resp,
            'par_pregunta_respuesta_incoherente': res_par}


# ---------------------------------------------------------------- 3 idioma

def _marcadores_lengua(texto):
    tl = fold(texto)
    def ct(w):
        return len(re.findall(r'(?<![a-z])' + re.escape(fold(w)) + r'(?![a-z])', tl))
    pt = sum(1 for w in PT_PALABRAS if fold(w) in tl)
    gl = sum(1 for w in GL_PALABRAS if fold(w) in tl)
    ca = sum(1 for w in CA_PALABRAS if fold(w) in tl)
    es_m = ct('la') + ct('el') + ct('que') + ct('de') + ct('tu') + ct('es')
    en = sum(ct(w) for w in EN_COMMON)
    return pt, gl, ca, es_m, en


def check_idioma(filas):
    res = _res()
    for f in filas:
        r = f['respuesta'] or ''
        rn = fold(r)
        categorias = []
        if re.search(r'<(think|thinking|antml|redacted)', rn):
            categorias.append(('tags_razonamiento', rn[:120]))
        elif any(p in rn[:1500] for p in RAZON_PATRONES):
            categorias.append(('resto_razonamiento', rn[:120]))
        for p in PLANTILLA_IA_PATRONES:
            if p in rn:
                categorias.append(('restos_asistente_ia', p))
                break
        pt, gl, ca, es_m, en = _marcadores_lengua(r)
        if pt >= 3 and es_m < pt:
            categorias.append(('portugues_detectado', 'pt=%d es=%d' % (pt, es_m)))
        if gl >= 2 and es_m < 10:
            categorias.append(('gallego_detectado', 'gl=%d' % gl))
        if ca >= 2 and es_m < 10:
            categorias.append(('catalan_detectado', 'ca=%d' % ca))
        if en >= 30 and es_m < 20:
            categorias.append(('ingles_detectado', 'en=%d' % en))
        if re.search(r'\*\*|```|<p>|</p>', r):
            categorias.append(('markdown_en_respuesta', 'marcas de formato'))
        rstrip = r.strip()
        if len(rstrip) >= 80 and (not rstrip.endswith(FIN_PUNTUACION) or rstrip[-1] in ',;:'):
            categorias.append(('sin_puntuacion_final', rstrip[-60:]))
        else:
            limpios = re.sub(r'[.»"\')\s]+$', '', rstrip).lower().split()
            if limpios and limpios[-1] in TRUNC_ULTIMAS:
                categorias.append(('acaba_truncado', ' '.join(limpios[-6:])))
        propios = []
        if f.get('humano'):
            propios.append(_normcut(f['humano']))
        propios.append(_normcut(r))
        todo = ' '.join(p for p in propios if p)
        if len(todo) >= 160:
            acentos = sum(todo.count(c) for c in 'áéíóúüñ')
            letras = sum(1 for c in todo if c.isalpha())
            if acentos == 0 and letras >= 150:
                categorias.append(('sin_tildes', 'texto propio %d letras sin un solo acento' % letras))
            elif letras >= 1500 and acentos / letras < 0.004:
                categorias.append(('tildes_escasas', 'acentos=%d/%d letras' % (acentos, letras)))
        for cat, det in categorias:
            _add(res, cat, f, det)
    return res


# ---------------------------------------------------------------- 4 coherencia cálculos

RE_PLANETA_SIGNO_F = re.compile(r'\b(' + '|'.join(PLANETAS_F) + r')\s+(?:esta\s+|qued[oa]\s+)?(?:en|de)\s+(' + '|'.join(SIGNOS_F) + r')\b')
RE_CASA_MENCION_F = re.compile(r'\bcasa\s+(\d{1,2})\b')
RE_PCT_F = re.compile(r'(\d{1,3})\s*%')
RE_NUM_NOMBRADO = re.compile(r'\b(camino de vida|expresion|alma|personalidad|anio personal|numero maestro)\s*[^\d\n]{0,14}(\d{1,2})\b')
RE_BIOR_CICLO = re.compile(r'\b(fisico|emocional|intelectual)\b(?:(?!fisico|emocional|intelectual)[^\d%]){0,30}?(-?\d{1,3})\s*%')


_RX_ASPECTO_ALL = re.compile(r'\b(?:' + '|'.join(sorted(ASPECTOS_F, key=len, reverse=True)) + r')\b')
_RX_PLANETA_ALL = re.compile(r'\b(?:' + '|'.join(sorted(PLANETAS_F, key=len, reverse=True)) + r')\b')
_CHAIN_SEG = re.compile(r'^(?:a|al|con|del|de|en|y|e|la|las|el|los)\b')
_NEG_CASA_RE = re.compile(r'\b(?:no|ni|nunca|jamas)\b[^\n,.:;]{0,16}$')


def _aspect_claims(texto_f):
    """Reclamos (planetaA, planetaB) de aspectos en texto plegado.

    Dentro de la frase del nombre de aspecto: sujeto = planeta previo cuyo hueco
    hasta el nombre no lleva «y», otro aspecto ni separador y es corto; si no, se
    reutiliza el sujeto del aspecto anterior en cadena («sextil a X y en
    cuadratura con Y» = mismo sujeto; «oposicion a X y mercurio en cuadratura
    con Y» = sujeto nuevo por hueco estricto). Objeto = primer planeta posterior.
    «entre X y Y» reclama el par directamente.
    """
    claims = set()
    seps = '.;:!?\n'
    sujeto_res = {}
    for m in _RX_ASPECTO_ALL.finditer(texto_f):
        i0 = max((texto_f.rfind(ch, 0, m.start()) for ch in seps), default=-1)
        ant_start = max(i0 + 1, m.start() - 45)
        ant = texto_f[ant_start:m.start()]
        futuros = [k for ch in seps for k in [texto_f.find(ch, m.end(), m.end() + 45)] if k >= 0]
        j1 = min(futuros) if futuros else -1
        des = texto_f[m.end():(j1 if j1 >= 0 else m.end() + 45)]
        dm = re.match(r'^\s*(?:entre\s+)(.+)$', des)
        if dm:
            pls = [p.group(0) for p in _RX_PLANETA_ALL.finditer(dm.group(1))]
            if len(pls) >= 2 and pls[0] != pls[1]:
                claims.add(frozenset(pls[:2]))
            continue
        sujeto = None
        cands = list(_RX_PLANETA_ALL.finditer(ant))
        par_y = False
        if len(cands) >= 2 and not _RX_ASPECTO_ALL.search(ant) \
                and re.fullmatch(r'\s*(?:y|e)\s*', ant[cands[-2].end():cands[-1].start()]):
            par = frozenset((cands[-2].group(0), cands[-1].group(0)))
            if len(par) == 2:
                claims.add(par)
                sujeto_res[m.start()] = cands[-1].group(0)
                par_y = True
        if not par_y and sujeto is None:
            for p in reversed(cands):
                gap = ant[p.end():]
                if len(gap) <= 35 and not re.search(r'\by\b', gap) \
                        and not _RX_ASPECTO_ALL.search(gap) \
                        and not any(ch in gap for ch in seps):
                    sujeto = p.group(0)
                    break
        if sujeto is None:
            prev = [a for a in _RX_ASPECTO_ALL.finditer(ant)
                    if a.start() in sujeto_res]
            if prev:
                a = prev[-1]
                seg = ant[a.end():]
                if _CHAIN_SEG.match(seg.strip()) \
                        and len(_RX_PLANETA_ALL.findall(seg)) <= 1:
                    sujeto = sujeto_res[a.start()]
        if par_y:
            continue
        bnd = re.search(r',\s*(?:y|que)\b|\by\s+(?:por|tambien|ademas|nuevamente|el|la|un|una|de nuevo)\b', des)
        des_o = des[:bnd.start()] if bnd else des
        md = _RX_PLANETA_ALL.search(des_o)
        if sujeto is None and md:
            mo = re.match(r'^\s*(?:de|del|a|al|con)\s+', des_o)
            if mo and not re.search(r'\s+y\s+(?:a|al|con|de|del|en)\s+', des_o):
                pls = list(_RX_PLANETA_ALL.finditer(des_o))
                if len(pls) >= 2 and pls[0].group(0) != pls[1].group(0):
                    claims.add(frozenset((pls[0].group(0), pls[1].group(0))))
                continue
        if sujeto:
            sujeto_res[m.start()] = sujeto
            if md and sujeto != md.group(0):
                claims.add(frozenset((sujeto, md.group(0))))
    return claims


def _carta_pairs(carta, _prof=0):
    """(planeta-signo, casas, pares de aspecto) extraídos de una carta, lista o dict,
    cubriendo también diccionarios anidados como revolucion_solar.carta."""
    pairs, casas, asp = set(), set(), set()
    if _prof > 3 or carta is None:
        return pairs, casas, asp
    if isinstance(carta, list):
        for x in carta:
            p, c, a = _carta_pairs(x, _prof + 1)
            pairs |= p
            casas |= c
            asp |= a
        return pairs, casas, asp
    if not isinstance(carta, dict):
        return pairs, casas, asp
    planetas = carta.get('planetas')
    if isinstance(planetas, dict):
        items = [(p, v) for p, v in planetas.items() if isinstance(v, dict)]
    elif isinstance(planetas, list):
        items = [(p.get('nombre', ''), p) for p in planetas if isinstance(p, dict)]
    else:
        items = []
    for p, v in items:
        pf = fold(p)
        if v.get('signo'):
            pairs.add((pf, fold(v['signo'])))
        if v.get('casa') is not None:
            try:
                casas.add(int(v['casa']))
            except (TypeError, ValueError):
                pass
    for ang, alias in (('ascendente', 'ascendente'), ('mc', 'mc'), ('medio_cielo', 'medio cielo')):
        v = carta.get(ang)
        if isinstance(v, dict) and v.get('signo'):
            pairs.add((alias, fold(v['signo'])))
        elif isinstance(v, str) and v:
            for s in SIGNOS_F:
                if s in fold(v):
                    pairs.add((alias, s))
                    break
    casas_l = carta.get('casas')
    if isinstance(casas_l, list):
        for x in casas_l:
            n = x.get('casa', x.get('numero', x.get('cuspide'))) if isinstance(x, dict) else x
            if n is None:
                continue
            try:
                casas.add(int(n))
            except (TypeError, ValueError):
                continue
    for a in carta.get('aspectos') or []:
        if isinstance(a, dict) and a.get('a') and a.get('b'):
            asp.add(frozenset((fold(a['a']), fold(a['b']))))
        else:
            s = fold(json.dumps(a, ensure_ascii=False) if not isinstance(a, str) else a)
            pls = [p for p in PLANETAS_F if re.search(r'\b%s\b' % p, s)]
            if len(pls) >= 2:
                asp.add(frozenset(pls[:2]))
    for k in ('carta', 'cartas'):
        if k in carta and isinstance(carta[k], (dict, list)):
            p, c, a = _carta_pairs(carta[k], _prof + 1)
            pairs |= p
            casas |= c
            asp |= a
    return pairs, casas, asp


def _prompt_planetas(texto):
    pairs, casas = set(), set()
    tf = fold(texto)
    for p, s in re.findall(r'[-*]\s*(' + '|'.join(PLANETAS_F) + r'):\s*(' + '|'.join(SIGNOS_F) + r')', tf):
        pairs.add((p, s))
    for casa in re.findall(r'[-*]\s*(?:' + '|'.join(PLANETAS_F) + r'):[^\n(]*\((?:casa\s+)?(\d{1,2})\)', tf):
        casas.add(int(casa))
    for casa in re.findall(r'\(casa\s+(\d{1,2})\)', tf):
        casas.add(int(casa))
    return pairs, casas


def check_coherencia_calculos(filas):
    res = _res()
    for f in filas:
        b = f.get('bloque')
        c = f.get('calculos') or {}
        rf = limpia_texto(f['respuesta'])
        categorias = []
        if b in BLOQUES_ASTRO and c:
            allowed, casas_ok, asp = set(), set(), set()
            for key in ('carta_natal', 'carta_a', 'carta_b', 'revolucion_solar', 'revolucion'):
                pr, cs, ap = _carta_pairs(c.get(key))
                allowed |= pr
                casas_ok |= cs
                asp |= ap
            tr = c.get('transitos')
            if tr is not None:
                entries = tr if isinstance(tr, list) else [tr]
                for entry in entries:
                    if isinstance(entry, dict):
                        if entry.get('planeta_transito') and entry.get('planeta_natal'):
                            asp.add(frozenset((fold(entry['planeta_transito']),
                                               fold(entry['planeta_natal']))))
                        if entry.get('casa_natal') is not None:
                            try:
                                casas_ok.add(int(entry['casa_natal']))
                            except (TypeError, ValueError):
                                pass
                    s = fold(json.dumps(entry, ensure_ascii=False) if not isinstance(entry, str) else entry)
                    pls = [p for p in PLANETAS_F if re.search(r'\b%s\b' % p, s)]
                    if len(pls) >= 2:
                        asp.add(frozenset(pls[:2]))
            pr_p, cs_p = _prompt_planetas(f.get('humano', ''))
            allowed |= pr_p
            casas_ok |= cs_p
            h_f = fold(f.get('humano', ''))
            asp |= _aspect_claims(h_f)
            casas_ok |= {int(x) for x in re.findall(r'casas?\s+(\d{1,2})\b', h_f)}
            allowed_planetas = {p for p, _ in allowed}
            if allowed:
                for p, s in RE_PLANETA_SIGNO_F.findall(rf):
                    if (p, s) not in allowed:
                        cat = 'signo_no_calculado' if p in allowed_planetas else 'planeta_no_en_consulta'
                        categorias.append((cat, '%s en %s' % (p, s)))
            if casas_ok:
                for m in re.finditer(r'(?<![a-záéíóúñ])casas?\s+(\d{1,2})(?![\d%])', rf):
                    if _NEG_CASA_RE.search(rf[max(0, m.start() - 22):m.start()]):
                        continue
                    casa = int(m.group(1))
                    if casa not in casas_ok:
                        categorias.append(('casa_no_calculada', 'casa %d' % casa))
            if asp:
                for claim in _aspect_claims(rf):
                    if claim not in asp:
                        categorias.append(('aspecto_no_calculado', ' '.join(sorted(claim))))
            for pct in RE_PCT_F.findall(rf):
                if int(pct) > 100:
                    categorias.append(('porcentaje_inventado', pct + '%'))
        if isinstance(c.get('numerologia'), dict):
            calc_clave = {fold(k): v for k, v in c['numerologia'].items()
                          if isinstance(v, int) and not isinstance(v, bool)}
            for nom, num in RE_NUM_NOMBRADO.findall(rf):
                if nom in calc_clave:
                    esperado = calc_clave[nom]
                    reducido = sum(int(d) for d in str(esperado))
                    if int(num) not in (esperado, reducido):
                        categorias.append(('numero_numerologia_incorrecto',
                                           '%s=%s (calculado %s)' % (nom, num, esperado)))
        if isinstance(c.get('biorritmos'), dict):
            ciclos = (c['biorritmos'] or {}).get('ciclos') or {}
            for ciclo, num in RE_BIOR_CICLO.findall(rf):
                if ciclo in ciclos:
                    esperado = round(abs(ciclos[ciclo].get('porcentaje') or 0))
                    if abs(abs(int(num)) - esperado) > 2:
                        categorias.append(('porcentaje_biorritmo_incorrecto',
                                           '%s: %s%% (calculado %d%%)' % (ciclo, num, esperado)))
            up = {'ascendente', 'ascenso', 'subiendo', 'creciente'}
            down = {'descendente', 'descenso', 'bajando', 'decreciente'}
            for m in re.finditer(r'\b(ascendente|descendente|ascenso|descenso|subiendo|bajando|creciente|decreciente)\b', rf):
                ant = rf[max(0, m.start() - 40):m.start()]
                dicho = m.group(1)
                for ck in ('fisico', 'emocional', 'intelectual'):
                    if ck not in ciclos:
                        continue
                    if not re.search(r'\b%s\b[^\n]{0,30}$' % ck, ant):
                        continue
                    fase = fold(str(ciclos[ck].get('fase') or ''))
                    if fase in up and dicho in down:
                        categorias.append(('fase_biorritmo_incorrecta', '%s: %s (calculado %s)' % (ck, dicho, fase)))
                    elif fase in down and dicho in up:
                        categorias.append(('fase_biorritmo_incorrecta', '%s: %s (calculado %s)' % (ck, dicho, fase)))
        for cat, det in categorias:
            _add(res, cat, f, det)
    return res


# ---------------------------------------------------------------- 5 tiradas

def _deck_for(bloque):
    if bloque in BLOQUES_ESPANOLA:
        return DECK_ESP_NORM
    if bloque in BLOQUES_TAROT:
        return DECK_TAROT_NORM
    return None


def _parece_carta(nombre_fold):
    if nombre_fold in DECK_TAROT_NORM or nombre_fold in DECK_ESP_NORM:
        return True
    if re.match(r'^(?:el|la|los|las)\s+\w', nombre_fold):
        return True
    if re.search(r'\b(?:de|del)\s+\w+$', nombre_fold):
        return True
    return nombre_fold.split()[0] in {'sota', 'caballero', 'caballo', 'reina', 'rey', 'as',
                                      'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete',
                                      'ocho', 'nueve', 'diez'}


def _parsear_tiradas(texto, rx_t, rx_p):
    """Cartas citadas en el texto que papeleean de línea de tirada."""
    drawn = []
    vistos_spans = set()
    for m in rx_t.finditer(texto or ''):
        esq = texto.rfind('\n', 0, m.start())
        esq = (texto[esq + 1:esq + 3] == '##')
        drawn.append((fold(m.group('carta')), m.group('carta'), m.start(), m.end(), 'main', esq))
        vistos_spans.add((m.start(), m.end()))
    for m in rx_p.finditer(texto or ''):
        if any(a <= m.start() < b or a < m.end() <= b for a, b in vistos_spans):
            continue
        if not _parece_carta(fold(m.group('carta'))):
            continue
        esq = texto.rfind('\n', 0, m.start())
        esq = (texto[esq + 1:esq + 3] == '##')
        drawn.append((fold(m.group('carta')), m.group('carta'), m.start(), m.end(), 'posible', esq))
    return drawn


def check_tiradas(filas):
    res = _res()
    rx_t, rx_p = RE_TIRADA, RE_TIRADA_POSIBLE
    rx_ref = RE_REF_LINEA
    if rx_t is None or rx_p is None or rx_ref is None:
        raise RuntimeError('build_decks() debe llamarse antes de check_tiradas()')
    for f in filas:
        b = f.get('bloque')
        deck = _deck_for(b)
        if deck is None:
            continue
        categorias = []
        drawn = _parsear_tiradas(f.get('humano', ''), rx_t, rx_p)
        refs = [(fold(m.group('carta')), m.group('orient'))
                for m in rx_ref.finditer(f.get('humano', '') or '')]
        refs += [(fold(m.group('carta')), m.group('orient'))
                 for m in rx_ref.finditer(f.get('respuesta', '') or '')]
        vistos = set()
        for name, raw, _s, _e, _fu, esq in drawn:
            if name not in vistos:
                rep = sum(1 for x, _, _, _, _, e2 in drawn if x == name and not e2)
                if rep > 1:
                    categorias.append(('carta_repetida_en_tirada', NOMBRES_CANON.get(name, raw)))
            vistos.add(name)
            if name not in deck:
                otras = DECK_ESP_NORM if deck is DECK_TAROT_NORM else DECK_TAROT_NORM
                cat = 'baraja_mezclada' if name in otras else 'carta_inventada'
                categorias.append((cat, NOMBRES_CANON.get(name, raw) + ' (' + str(b) + ')'))
        for name, _o in refs:
            if name not in deck:
                categorias.append(('referencia_carta_inventada', NOMBRES_CANON.get(name, name)))
        if drawn and refs:
            dn, rn2 = {x[0] for x in drawn}, {x for x, _ in refs}
            if dn != rn2:
                categorias.append(('referencia_no_coincide_con_tirada',
                                   'sin referencia %s | referidas sin tirar %s' %
                                   (', '.join(sorted(NOMBRES_CANON.get(x, x) for x in dn - rn2)) or '-',
                                    ', '.join(sorted(NOMBRES_CANON.get(x, x) for x in rn2 - dn)) or '-')))
        for cat, det in categorias:
            _add(res, cat, f, det)
    return res


# ---------------------------------------------------------------- 6 fuera_alcance

RE_CORRUPTO = re.compile(r'^\d+\s+\S')
TECNICA_PROHIBIDA = [
    r'lineas?\s+de\s+la\s+mano', r'l[ií]neas\s+de\s+la\s+vida', r'quiromanc',
    r'mont[aí]nas?\s+de\s+la\s+fortuna', r'p[eé]ndulo', r'bola\s+de\s+cristal',
    r'posos?\s+(?:de\s+)?(?:caf[eé]|t[eé])', r'hexagramas?', r'runa', r'nakshatra',
    r'\bbazi\b', r'jyotish', r'sue[ñn]os?\s+(?:me\s+)?(?:dicen|revelan|anuncian)',
    r'vidas\s+pasadas', r'or[aá]culo', r'tarot\s+de\s+los\s+muertos',
]
PREDICCION = [
    r'\b(?:jueg\w*|jugar\w*|apost\w*)\b.{0,40}\b\d{1,3}\b', r'la loter[ií]a', r'n[uú]mero\s+(?:de la suerte|premiado|ganador)\s*[^\d\n]{0,8}\d',
    r'primitiva', r'quiniela', r'\bonza\b', r'apuesta\s+ganadora',
    r'va\s+a\s+ganar', r'vas\s+a\s+ganar', r'cobrar[áa]s', r'heredar[áa]s',
    r'te\s+receto', r'demanda?\s+(?:judicial|contra)', r'compra\s+(?:esta|esas|esos)\s+acciones',
    r'vende\s+(?:tus|las)\s+acciones', r'invertir[e]?\s+en\s+(?:bitcoin|acciones|cripto)',
    r'firma\s+(?:el|este|esa)\s+(?:contrato|papeles)',
]
NEG_WINDOW = 45
_RECHAZO_CERCANO = re.compile(
    r'\b(?:no (?:puedo|hago|realizo|ofrezco|suelo|haria)|no es posible|me (?:paso|escapo)|'
    r'fuera de (?:mi )?alcance|no practico|no soy|recomiendo|acudir|otro profesional|'
    r'otra t[eé]cnica|otro m[eé]todo|m[eé]todo[^.]{0,30}?(?:diferente|distinto|alternativ)'
    r'|(?:diferente|distinto|alternativ)[^.]{0,30}?m[eé]todo|sistema distinto|ouija)', re.I)


def _match_sin_negacion(r_low, pat):
    for m in re.finditer(pat, r_low):
        ant = r_low[max(0, m.start() - NEG_WINDOW):m.start()]
        if re.search(r'\b(?:no|nunca|jam[aá]s|tampoco|ni)\b', ant):
            continue
        return m
    return None


def _contexto(r_low, m, radio=30):
    return r_low[max(0, m.start() - radio):m.end() + radio]


def check_fuera_alcance(filas):
    res = _res()
    for f in filas:
        if f.get('bloque') != 'fuera_alcance':
            continue
        m = RE_PREGUNTA.search(f.get('humano', ''))
        q = m.group(1) if m else ''
        categorias = []
        if not q:
            categorias.append(('pregunta_no_extraida', f.get('humano', '')[:80]))
        elif RE_CORRUPTO.match(q) and (q.rstrip().endswith(':') or len(q) < 30):
            categorias.append(('pregunta_corrupta', q[:100]))
        rl = fold(f.get('respuesta', '') or '')
        rl_ac = re.sub(r'[^a-z0-9áéíóúüñ%\s.,¡!¿?;:-]', '', unicodedata.normalize('NFC', f.get('respuesta', '') or '').lower())
        for pat in TECNICA_PROHIBIDA:
            m = _match_sin_negacion(rl_ac, pat)
            if m:
                ventana = rl_ac[max(0, m.start() - 60):m.end() + 60]
                if _RECHAZO_CERCANO.search(ventana):
                    continue
                categorias.append(('responde_tecnica_prohibida', _contexto(rl_ac, m)))
                break
        for pat in PREDICCION:
            m = _match_sin_negacion(rl_ac, pat)
            if m:
                ventana = rl_ac[max(0, m.start() - 60):m.end() + 60]
                if _RECHAZO_CERCANO.search(ventana):
                    continue
                categorias.append(('prediccion_concreta', _contexto(rl_ac, m)))
                break
        for cat, det in categorias:
            _add(res, cat, f, det)
    return res


# ---------------------------------------------------------------- 7 longitudes

def check_longitudes(filas):
    res = _res()
    por_fam = defaultdict(list)
    gpt_lens = []
    for f in filas:
        lg = len(f.get('respuesta', ''))
        gpt_lens.append(lg)
        por_fam[f.get('familiar', 'otros')].append(lg)
    mu = statistics.mean(gpt_lens)
    sd = statistics.pstdev(gpt_lens) or 1.0
    p95g = statistics.quantiles(gpt_lens, n=20)[18] if len(gpt_lens) > 20 else float(max(gpt_lens))
    distribucion = {}
    for fam, lens in sorted(por_fam.items()):
        fp95 = statistics.quantiles(lens, n=20)[18] if len(lens) >= 20 else float(max(lens))
        distribucion[fam] = {'n': len(lens), 'p50': int(statistics.median(lens)),
                             'p95': int(fp95), 'max': int(max(lens)),
                             'mean': int(statistics.mean(lens))}
    for f in filas:
        lg = len(f.get('respuesta', ''))
        lh = len(f.get('humano', ''))
        tipo = None
        if lg < 60:
            tipo = 'gpt_corta'
        elif lg > 24000:
            tipo = 'gpt_muy_larga'
        elif lh > 12000:
            tipo = 'humano_muy_larga'
        elif lg > 4000 and lg > 2.5 * p95g:
            tipo = 'gpt_outlier_p95'
        elif abs(lg - mu) > 5 * sd:
            tipo = 'gpt_zscore'
        if tipo:
            res['total'] += 1
            res['conteo'][tipo] = res['conteo'].get(tipo, 0) + 1
            if len(res['ejemplos']) < EJEMPLOS_MAX:
                res['ejemplos'].append({'id': f['sid'], 'split': f['split'],
                                        'bloque': f.get('bloque'), 'categoria': tipo,
                                        'detalle': 'gpt=%d human=%d' % (lg, lh)})
    return {'total': res['total'], 'conteo': res['conteo'], 'ejemplos': res['ejemplos'],
            'distribucion': distribucion}


# ---------------------------------------------------------------- 8 secretos

def check_secretos(filas):
    res = _res()
    pats = [('api_key', APIKEY_PATRON), ('sk_key', SK_PATRON), ('aws', AKIA_PATRON),
            ('bearer', BEARER_PATRON), ('jwt', JWT_PATRON), ('hex64', HEX64_PATRON),
            ('email', EMAIL_PATRON), ('telefono', TEL_PATRON), ('ip', IP_PATRON)]
    for f in filas:
        texto = (f.get('humano', '') or '') + '\n' + (f.get('respuesta', '') or '')
        for nombre, pat in pats:
            m = pat.search(texto)
            if m:
                _add(res, 'posible_secreto_' + nombre, f, m.group(0)[:60])
                break
    return res


# ---------------------------------------------------------------- orquestación

def cargar_filas(dataset_dir):
    filas = []
    for split in ('train', 'val', 'test'):
        path = os.path.join(dataset_dir, split + '.jsonl')
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as fh:
            for idx, line in enumerate(fh):
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                conv = d.get('conversations', [])
                hum = ' '.join(m.get('value', '') for m in conv if m.get('from') == 'human')
                gpt = ' '.join(m.get('value', '') for m in conv if m.get('from') == 'gpt')
                bloque = d.get('bloque') or 'sin_bloque'
                filas.append({'split': split, 'idx': idx,
                              'sid': '%s#%d id=%s' % (split, idx, d.get('id')),
                              'id': d.get('id'), 'bloque': bloque,
                              'familiar': FAMILIA_POR_BLOQUE.get(bloque, 'otros'),
                              'calculos': d.get('calculos'),
                              'humano': hum, 'respuesta': gpt})
    return filas


def auditar(filas, semilla=SEMILLA_DEFAULT):
    informe = {}
    informe.update(check_fugas(filas, semilla))
    informe.update(check_duplicados(filas, semilla))
    informe['idioma_anomalo'] = check_idioma(filas)
    informe['datos_incoherentes'] = check_coherencia_calculos(filas)
    informe['tiradas_invalidas'] = check_tiradas(filas)
    informe['fuera_alcance_ndefectos'] = check_fuera_alcance(filas)
    informe['longitudes_anomalas'] = check_longitudes(filas)
    informe['secretos'] = check_secretos(filas)
    muestra = muestreo_estratificado(filas, semilla=semilla)
    informe['_muestra'] = {k: [f['sid'] for f in v] for k, v in muestra.items()}
    informe['_meta'] = {'semilla': semilla, 'n_filas': len(filas),
                        'por_split': dict(Counter(f['split'] for f in filas)),
                        'por_familia_split': {'%s|%s' % k: v for k, v in sorted(
                            Counter((f['familiar'], f['split']) for f in filas).items())}}
    return informe


ORDEN_SECCIONES = ['fugas_prompt', 'fugas_respuesta', 'duplicados_exactos',
                   'respuesta_en_varias_filas', 'par_pregunta_respuesta_incoherente',
                   'idioma_anomalo', 'datos_incoherentes', 'tiradas_invalidas',
                   'fuera_alcance_ndefectos', 'longitudes_anomalas', 'secretos']


def resumen_md(informe):
    lineas = ['# Resumen auditoría v1d', '']
    meta = informe.get('_meta', {})
    lineas.append('Filas: %s · semilla %s · por split %s' %
                  (meta.get('n_filas'), meta.get('semilla'), meta.get('por_split')))
    lineas.append('')
    for k in ORDEN_SECCIONES:
        r = informe.get(k)
        if not r:
            continue
        lineas.append('## %s — %d' % (k, r['total']))
        for cat, n in sorted(r.get('conteo', {}).items(), key=lambda x: -x[1]):
            lineas.append('- %s: %d' % (cat, n))
        for e in r.get('ejemplos', [])[:3]:
            lineas.append('  - ej %s [%s] %s' % (e['id'], e.get('categoria'), e['detalle'][:110]))
        lineas.append('')
    return '\n'.join(lineas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset-dir', required=True)
    ap.add_argument('--kb-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb'))
    ap.add_argument('--salida', required=True, help='directorio de trabajo (JSON + resumen)')
    ap.add_argument('--semilla', type=int, default=SEMILLA_DEFAULT)
    ap.add_argument('--tam-muestra', type=int, default=400)
    args = ap.parse_args(argv)
    os.makedirs(args.salida, exist_ok=True)
    deck_info = build_decks(args.kb_dir)
    filas = cargar_filas(args.dataset_dir)
    informe = auditar(filas, semilla=args.semilla)
    informe['_meta']['decks'] = deck_info
    informe['_meta']['tam_muestra'] = args.tam_muestra
    jp = os.path.join(args.salida, 'auditoria_v1d.json')
    with open(jp, 'w', encoding='utf-8') as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=1)
    mp = os.path.join(args.salida, 'resumen.md')
    with open(mp, 'w', encoding='utf-8') as fh:
        fh.write(resumen_md(informe))
    print(resumen_md(informe))
    print('[ok] informe JSON: %s' % jp)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
