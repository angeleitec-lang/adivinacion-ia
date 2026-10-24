# -*- coding: utf-8 -*-
"""Arma el dataset v1f (T144).

Parte del dataset v1e y sustituye los bloques fuera_alcance / etica /
espanola_1 por los datos v2, repartidos ~80/10/10 por bloque con semilla
fija. Reglas heredadas de v1e: system canonico unico por bloque, sin
duplicados de prompt entre splits, sin fuga train->val/test (mismos
umbrales de la auditoria), 0 voseo y sin chino/cirileo.

Determinista e idempotente: misma entrada -> mismos bytes de salida.
"""
import argparse
import collections
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
if str(CORPUS_DIR) not in sys.path:
    sys.path.insert(0, str(CORPUS_DIR))

import auditoria_v1d as aud  # noqa: E402
import armar_dataset_v1e as v1e  # noqa: E402
import preparar_entrenamiento as prep  # noqa: E402
from regenerar_fuera_alcance import contiene_voseo  # noqa: E402

SEMILLA = 144
BLOQUES_SWAP = ('fuera_alcance', 'etica', 'espanola_1')
FRACCIONES = (0.8, 0.1)
ROLES_VALIDOS = ('system', 'human', 'gpt')

FASE0 = '/Users/angelgonzalez/fase0'
V1E_DEFAULT = os.path.join(FASE0, 'dataset_fase1_v1e')
FA_V2_DEFAULT = os.path.join(FASE0, 'fuera_alcance_v2', 'fuera_alcance_v2.jsonl')
EE_V2_DEFAULT = os.path.join(FASE0, 'etica_espanola1_v2', 'etica_espanola1_v2.jsonl')
OUT_DEFAULT = os.path.join(FASE0, 'dataset_fase1_v1f')

RE_CJK = re.compile('[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
RE_CIRILICO = re.compile('[\u0400-\u04ff]')


def validar_esquema(raw):
    """Errores de esquema de una fila nueva; lista vacia si es valida."""
    errores = []
    if not isinstance(raw, dict):
        return ['no_es_dict']
    conv = raw.get('conversations')
    if not isinstance(conv, list) or not conv:
        errores.append('sin_conversations')
        return errores
    roles = [t.get('from') for t in conv if isinstance(t, dict)]
    if any(r not in ROLES_VALIDOS for r in roles):
        errores.append('rol_invalido')
    if 'human' not in roles:
        errores.append('sin_human')
    if 'gpt' not in roles:
        errores.append('sin_gpt')
    if raw.get('bloque') not in BLOQUES_SWAP:
        errores.append('bloque_inesperado')
    if raw.get('id') is None:
        errores.append('sin_id')
    for t in conv:
        if not isinstance(t, dict) or not isinstance(t.get('value'), str):
            errores.append('valor_no_texto')
            break
    return errores


def _sistema_de(raw):
    for t in raw.get('conversations', []):
        if isinstance(t, dict) and t.get('from') == 'system':
            return t.get('value')
    return None


def _textos_no_system(raw):
    return [t.get('value', '') for t in raw.get('conversations', [])
            if isinstance(t, dict) and t.get('from') != 'system']


def cargar_nuevas(rutas):
    """Carga las filas nuevas de los jsonl v2. Devuelve (filas, descartes)."""
    filas = []
    descartes = []
    for ruta in rutas:
        origen = os.path.basename(ruta)
        with open(ruta, encoding='utf-8') as fh:
            for linea, texto in enumerate(fh):
                texto = texto.strip()
                if not texto:
                    continue
                try:
                    raw = json.loads(texto)
                except json.JSONDecodeError:
                    descartes.append({'motivo': 'esquema_roto', 'origen': origen,
                                    'linea': linea, 'error': 'json_invalido'})
                    continue
                errs = validar_esquema(raw)
                if errs:
                    descartes.append({'motivo': 'esquema_roto', 'origen': origen,
                                     'linea': linea, 'id': raw.get('id'),
                                     'errores': errs})
                    continue
                humanos = [t['value'] for t in raw['conversations']
                          if t.get('from') == 'human']
                gpts = [t['value'] for t in raw['conversations']
                        if t.get('from') == 'gpt']
                bloque = raw['bloque']
                sid = 'nuevo:%s#%d id=%s' % (origen, linea, raw['id'])
                filas.append({
                    'split': None, 'idx': linea, 'sid': sid, 'id': raw['id'],
                    'bloque': bloque,
                    'familiar': aud.FAMILIA_POR_BLOQUE.get(bloque, 'otros'),
                    'calculos': raw.get('calculos'),
                    'humano': humanos[0], 'respuesta': gpts[-1],
                    'raw': raw, 'origen': origen,
                })
    return filas, descartes


def canon_system_desde_v1e(filas_v1e):
    """System canonico de los bloques swap en v1e (mayoritario)."""
    sistemas = collections.Counter(
        _sistema_de(f['raw']) for f in filas_v1e if f['bloque'] in BLOQUES_SWAP)
    sistemas.pop(None, None)
    if not sistemas:
        return None, {'fuente': 'v1e_sin_filas', 'distintos': 0}
    canon, _ = sistemas.most_common(1)[0]
    return canon, {'fuente': 'v1e', 'distintos': len(sistemas)}


def aplicar_canon_system(nuevas, canon):
    """Normaliza el system de las nuevas al canonico. Devuelve normalizadas."""
    if canon is None:
        sistemas = collections.Counter(_sistema_de(f['raw']) for f in nuevas)
        sistemas.pop(None, None)
        if not sistemas:
            return 0
        canon = sistemas.most_common(1)[0][0]
    n = 0
    for f in nuevas:
        if _sistema_de(f['raw']) != canon:
            for t in f['raw']['conversations']:
                if t.get('from') == 'system':
                    t['value'] = canon
            n += 1
    return n


def checar_voseo(filas):
    ok, descartes = [], []
    for f in filas:
        if contiene_voseo(f['respuesta']):
            descartes.append({'motivo': 'voseo', 'origen': f.get('origen'),
                            'id': f['id'], 'sid': f['sid']})
        else:
            ok.append(f)
    return ok, descartes


def checar_idioma(filas):
    ok, descartes = [], []
    for f in filas:
        texto = ' '.join(_textos_no_system(f['raw']))
        if RE_CJK.search(texto) or RE_CIRILICO.search(texto):
            descartes.append({'motivo': 'idioma_no_es', 'origen': f.get('origen'),
                            'id': f['id'], 'sid': f['sid']})
        else:
            ok.append(f)
    return ok, descartes


def repartir(filas, semilla):
    """Asigna split ~80/10/10 por bloque, determinista con semilla."""
    por_bloque = collections.defaultdict(list)
    for f in filas:
        por_bloque[f['bloque']].append(f)
    for bloque in sorted(por_bloque):
        orden = sorted(por_bloque[bloque], key=lambda f: f['sid'])
        random.Random(semilla).shuffle(orden)
        n = len(orden)
        n_train = int(round(n * FRACCIONES[0]))
        n_val = int(round(n * FRACCIONES[1]))
        for i, f in enumerate(orden):
            if i < n_train:
                f['split'] = 'train'
            elif i < n_train + n_val:
                f['split'] = 'val'
            else:
                f['split'] = 'test'
    return filas


def filtrar_fugas_y_dupes(base, nuevas):
    """Descarta filas nuevas que duplican o fugar prompts/respuestas.

    Reglas (umbrales de la auditoria v1d, como v1e):
    (a) prompt propio EXACTO (len>=40) compartido con otra fila de otro
        split, o con otra fila nueva (aunque sea del mismo split);
    (b) prompt casi identico cross-split (SIM_PROMPT_MIN);
    (c) respuesta casi identica cross-split (SIM_RESP_MIN).
    En todo caso se retira la fila NUEVA, nunca la base de v1e.
    """
    descartes = []
    vivas = list(nuevas)
    nuevas_sids = {f['sid'] for f in vivas}

    def quitar(f, motivo, pareja):
        vivas.remove(f)
        descartes.append({'motivo': motivo, 'origen': f.get('origen'),
                        'id': f['id'], 'sid': f['sid'],
                        'pareja': pareja['sid']})

    # (a) duplicado exacto de prompt propio
    por_hash = collections.defaultdict(list)
    for f in list(base) + vivas:
        pp = aud.prompt_propio(f['humano'])
        if len(pp) >= 40:
            por_hash[aud._hash_norm(pp)].append(f)
    for h in sorted(por_hash):
        grupo = por_hash[h]
        nuevas_g = sorted((f for f in grupo if f['sid'] in nuevas_sids),
                         key=lambda f: f['sid'])
        if not nuevas_g:
            continue
        bases_g = [f for f in grupo if f['sid'] not in nuevas_sids]
        for n in nuevas_g:
            if any(b['split'] != n['split'] for b in bases_g):
                pareja = next(b for b in bases_g if b['split'] != n['split'])
                quitar(n, 'prompt_duplicado', pareja)
            elif any(m['sid'] < n['sid'] for m in nuevas_g if m is not n):
                pareja = min((m for m in nuevas_g if m is not n),
                            key=lambda m: m['sid'])
                quitar(n, 'prompt_duplicado', pareja)

    # (b) fuga por similitud de prompt
    combinadas = list(base) + vivas
    for i, j, _cnt, _sim in aud._pares_similares(
            combinadas, lambda f: aud.prompt_propio(f['humano']),
            aud.SIM_PROMPT_MIN):
        a, b = combinadas[i], combinadas[j]
        a_nueva = a['sid'] in nuevas_sids and a in vivas
        b_nueva = b['sid'] in nuevas_sids and b in vivas
        if not (a_nueva or b_nueva):
            continue
        if a_nueva and b_nueva:
            victima, pareja = (a, b) if a['sid'] > b['sid'] else (b, a)
        else:
            victima, pareja = (a, b) if a_nueva else (b, a)
        if victima in vivas:
            quitar(victima, 'fuga_prompt', pareja)

    # (c) fuga por similitud de respuesta
    combinadas = list(base) + vivas
    for i, j, _cnt, _sim in aud._pares_similares(
            combinadas, lambda f: aud.limpia_texto(f['respuesta']),
            aud.SIM_RESP_MIN):
        a, b = combinadas[i], combinadas[j]
        a_nueva = a['sid'] in nuevas_sids and a in vivas
        b_nueva = b['sid'] in nuevas_sids and b in vivas
        if not (a_nueva or b_nueva):
            continue
        if a_nueva and b_nueva:
            victima, pareja = (a, b) if a['sid'] > b['sid'] else (b, a)
        else:
            victima, pareja = (a, b) if a_nueva else (b, a)
        if victima in vivas:
            quitar(victima, 'fuga_respuesta', pareja)

    return vivas, descartes


def _bloque_total(conteo_bloque_split, bloque):
    prefijo = bloque + '|'
    return sum(v for k, v in conteo_bloque_split.items() if k.startswith(prefijo))


def _semforo_v1e_logica(finales):
    filas_por_split = {'train': [], 'val': [], 'test': []}
    contadores = {'train': 0, 'val': 0, 'test': 0}
    for f in finales:
        contadores[f['split']] += 1
        filas_por_split[f['split']].append(
            {'linea': contadores[f['split']], 'fila': f['raw']})
    leidas = {s: len(v) for s, v in filas_por_split.items()}
    invalidas = {s: 0 for s in filas_por_split}
    estadisticas = prep.calcular_estadisticas(filas_por_split, leidas, invalidas)
    semaforo, errores, avisos = prep._problemas_y_semaforo(
        estadisticas, [],
        {'train': True, 'val': True, 'test': True})
    return semaforo, errores, avisos


def construir(v1e_dir=V1E_DEFAULT, fa_ruta=FA_V2_DEFAULT,
              ee_ruta=EE_V2_DEFAULT, out_dir=OUT_DEFAULT, semilla=SEMILLA):
    """Construye v1f a partir de v1e + los dos jsonl v2. Devuelve el resumen."""
    filas_v1e = v1e.cargar_filas_raw(v1e_dir)
    antes = v1e._conteos(filas_v1e)
    base = [f for f in filas_v1e if f['bloque'] not in BLOQUES_SWAP]
    viejas = [f for f in filas_v1e if f['bloque'] in BLOQUES_SWAP]

    canon, canon_info = canon_system_desde_v1e(filas_v1e)
    nuevas, descartes_esquema = cargar_nuevas([fa_ruta, ee_ruta])
    coincidentes = sum(1 for f in nuevas if _sistema_de(f['raw']) == canon)
    normalizadas = aplicar_canon_system(nuevas, canon)

    sin_voseo, descartes_voseo = checar_voseo(nuevas)
    sin_idioma, descartes_idioma = checar_idioma(sin_voseo)
    repartidas = repartir(sin_idioma, semilla)
    integradas, descartes_fugas = filtrar_fugas_y_dupes(base, repartidas)

    finales = base + integradas
    os.makedirs(out_dir, exist_ok=True)
    cambios = os.path.join(out_dir, '_cambios')
    os.makedirs(cambios, exist_ok=True)

    for split in ('train', 'val', 'test'):
        filas_split = ([f for f in base if f['split'] == split]
                      + [f for f in integradas if f['split'] == split])
        v1e._escribir_jsonl(os.path.join(out_dir, split + '.jsonl'),
                            [f['raw'] for f in filas_split])

    despues = v1e._conteos(finales)
    retiradas = collections.Counter()
    for b in BLOQUES_SWAP:
        for s in ('train', 'val', 'test'):
            retiradas['%s|%s' % (b, s)] = 0
    retiradas.update(
        '%s|%s' % (f['bloque'], f['split']) for f in viejas)
    integradas_cs = collections.Counter(
        '%s|%s' % (f['bloque'], f['split']) for f in integradas)

    descartes = descartes_esquema + descartes_voseo + descartes_idioma \
        + descartes_fugas
    conteo_descartes = collections.Counter(d['motivo'] for d in descartes)

    bloques = sorted(set(
        k.split('|')[0] for k in antes['por_bloque_split'])
        | set(k.split('|')[0] for k in despues['por_bloque_split']))
    comparacion = {b: {'v1e': _bloque_total(antes['por_bloque_split'], b),
                      'v1f': _bloque_total(despues['por_bloque_split'], b)}
                  for b in bloques}

    semaforo, errores, avisos = _semforo_v1e_logica(finales)

    resumen = {
        'version': 'v1f',
        'semilla': semilla,
        'rutas': {'v1e': str(v1e_dir), 'fuera_alcance_v2': str(fa_ruta),
                 'etica_espanola1_v2': str(ee_ruta), 'salida': str(out_dir)},
        'system_canonico': {
            'sha256': hashlib.sha256(
                (canon or '').encode('utf-8')).hexdigest(),
            'fuente': canon_info['fuente'],
            'distintos_en_v1e': canon_info.get('distintos', 0),
            'coincidentes_nuevas': coincidentes,
            'normalizadas_nuevas': normalizadas,
        },
        'antes': antes,
        'despues': despues,
        'comparacion_v1e': comparacion,
        'retiradas_viejas': dict(sorted(retiradas.items())),
        'integradas': dict(sorted(integradas_cs.items())),
        'descartes': dict(sorted(conteo_descartes.items())),
        'semforo': semaforo,
        'semforo_detalle': {'errores': errores, 'avisos': avisos},
    }
    with open(os.path.join(out_dir, 'resumen.json'), 'w', encoding='utf-8') as fh:
        json.dump(resumen, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write('\n')

    v1e._escribir_jsonl(
        os.path.join(cambios, 'paso1_retirada_bloques_viejos.jsonl'),
        [{'accion': 'retirada', 'split': f['split'], 'id': f['id'],
          'bloque': f['bloque'], 'sid': f['sid']} for f in viejas])
    v1e._escribir_jsonl(
        os.path.join(cambios, 'paso2_integracion_nuevas.jsonl'),
        [{'accion': 'integrada', 'split': f['split'], 'id': f['id'],
          'bloque': f['bloque'], 'sid': f['sid'], 'origen': f.get('origen')}
         for f in integradas])
    v1e._escribir_jsonl(
        os.path.join(cambios, 'paso3_descartes.jsonl'), descartes)
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--v1e', default=V1E_DEFAULT)
    ap.add_argument('--fuera-alcance', default=FA_V2_DEFAULT)
    ap.add_argument('--etica-espanola', default=EE_V2_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--semilla', type=int, default=SEMILLA)
    args = ap.parse_args(argv)
    resumen = construir(args.v1e, args.fuera_alcance, args.etica_espanola,
                       args.out, args.semilla)
    print('v1f construido en %s' % args.out)
    print('antes: %d filas | despues: %d filas'
          % (resumen['antes']['total'], resumen['despues']['total']))
    print('integradas: %s' % json.dumps(resumen['integradas'],
                                       ensure_ascii=False))
    print('descartes: %s' % json.dumps(resumen['descartes'],
                                      ensure_ascii=False))
    print('semaforo (logica v1e): %s' % resumen['semforo'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
