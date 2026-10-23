# -*- coding: utf-8 -*-
"""T141: construir dataset v1e a partir de v1d aplicando los arreglos de la auditoría T135.

Determinista, semilla fija 141, sin LLM y sin nodos. Entrada: dataset v1d (solo lectura)
y los hallazgos de auditoria_v1d (recalculados aquí con las mismas funciones, porque el
JSON de la auditoría solo guarda hasta 5 ejemplos por categoría).

Pasos (cada uno deja registro de ids afectados en <salida>/_cambios/<paso>.jsonl):
  1  fuera_alcance: se retira todo el bloque fuera_alcance (filas corruptas, T135).
  1b fuera_alcance_v2: si existe el fichero de aceptadas de T136, se integra 90/5/5.
  2  fugas cross-split: se retira de train el lado duplicado (prompt o respuesta).
  3  dedupe train: mismo prompt propio con varias respuestas -> se conserva una
     (sin banderas de expurgo; si todas limpias, id menor).
  4  alucinaciones de calculos: se retiran signo_no_calculado,
     numero_numerologia_incorrecto y aspecto_no_calculado en todos los splits;
     casa_no_calculada y fase_biorritmo_incorrecta se conservan pero se listan.
  5  multiturno: no se borra; se reetiqueta a 'consulta_con_contexto' guardando
     el bloque original en 'bloque_origen' (no hay multiturno real, T135).
  6  numerologia sin test: se mueven filas de train a test y a val sin crear fugas.
  7  markdown: no se cambia nada; solo se informa el recuento por bloque.
"""
import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auditoria_v1d as aud  # noqa: E402

SEMILLA = 141
V1D_DEFAULT = '/Users/angelgonzalez/fase0/dataset_fase1_v1d'
OUT_DEFAULT = '/Users/angelgonzalez/fase0/dataset_fase1_v1e'
FUERA_V2_DEFAULT = '/Users/angelgonzalez/fase0/fuera_alcance_v2/fuera_alcance_v2.jsonl'

REMOVER_CATS = ('signo_no_calculado', 'numero_numerologia_incorrecto', 'aspecto_no_calculado')
CONSERVAR_LISTADAS = ('casa_no_calculada', 'fase_biorritmo_incorrecta')
BANDERAS_EXPURGO = set(REMOVER_CATS) | {'pregunta_corrupta'}

BLOQUE_FUERA = 'fuera_alcance'
BLOQUE_MULTI = 'multiturno'
BLOQUE_CONTEXTO = 'consulta_con_contexto'
N_TEST_NUMEROLOGIA = 20
N_VAL_NUMEROLOGIA = 15


def cargar_filas_raw(dataset_dir):
    """Como aud.cargar_filas pero conservando el dict original de cada fila en 'raw'."""
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
                             'familiar': aud.FAMILIA_POR_BLOQUE.get(bloque, 'otros'),
                             'calculos': d.get('calculos'),
                             'humano': hum, 'respuesta': gpt, 'raw': d})
    return filas


def _capturar(fn, *args, **kwargs):
    """Envuelve aud._add en runtime para capturar TODOS los (categoria, bloque, sid)."""
    capturado = []
    original = aud._add

    def wrapper(res, categoria, fila, detalle):
        capturado.append((categoria, fila.get('bloque'), fila['sid'], str(detalle)[:160]))
        return original(res, categoria, fila, detalle)

    aud._add = wrapper
    try:
        resultado = fn(*args, **kwargs)
    finally:
        aud._add = original
    return resultado, capturado


def capturar_flags(filas):
    """sid -> set(categorias de incoherencia) y set de sids de pregunta_corrupta."""
    _, cap_coh = _capturar(aud.check_coherencia_calculos, filas)
    _, cap_fa = _capturar(aud.check_fuera_alcance, filas)
    flags = defaultdict(set)
    for cat, _bloque, sid, _det in cap_coh:
        flags[sid].add(cat)
    corruptas = {sid for cat, _b, sid, _d in cap_fa if cat == 'pregunta_corrupta'}
    return flags, corruptas


def _idkey(i):
    """Clave de ordenación estable para ids que pueden ser int, str o None."""
    if isinstance(i, int):
        return (0, i, '')
    if i is None:
        return (2, 0, '')
    return (1, 0, str(i))


def _registro(f, accion, motivo):
    return {'sid': f['sid'], 'id': f['id'], 'split': f['split'],
            'bloque': f['bloque'], 'accion': accion, 'motivo': motivo}


def _retirar(filas, retirar):
    nuevas = [f for f in filas if f['sid'] not in retirar]
    reg = [_registro(f, 'retirada', retirar[f['sid']])
           for f in filas if f['sid'] in retirar]
    return nuevas, reg


# --------------------------------------------------------------- paso 1

def paso1_fuera_alcance(filas):
    retirar = {f['sid']: 'bloque fuera_alcance corrupto (T135/T141 paso 1)'
               for f in filas if f['bloque'] == BLOQUE_FUERA}
    return _retirar(filas, retirar)


def paso1b_fuera_alcance_v2(filas, ruta, semilla=SEMILLA):
    """Integra las aceptadas de T136 repartiendo 90/5/5 train/val/test."""
    crudos = []
    with open(ruta, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                crudos.append(json.loads(line))
    orden = list(range(len(crudos)))
    random.Random(semilla).shuffle(orden)
    n = len(crudos)
    n_train = int(round(n * 0.90))
    n_val = int(round(n * 0.05))
    nuevas = []
    reg = []
    for pos, i in enumerate(orden):
        d = crudos[i]
        split = 'train' if pos < n_train else ('val' if pos < n_train + n_val else 'test')
        conv = d.get('conversations', [])
        hum = ' '.join(m.get('value', '') for m in conv if m.get('from') == 'human')
        gpt = ' '.join(m.get('value', '') for m in conv if m.get('from') == 'gpt')
        bloque = d.get('bloque') or BLOQUE_FUERA
        f = {'split': split, 'idx': -1, 'sid': 'v2#%d id=%s' % (i, d.get('id')),
             'id': d.get('id'), 'bloque': bloque,
             'familiar': aud.FAMILIA_POR_BLOQUE.get(bloque, 'otros'),
             'calculos': d.get('calculos'), 'humano': hum, 'respuesta': gpt, 'raw': d}
        nuevas.append(f)
        reg.append(_registro(f, 'integrada_v2', 'aceptada T136, reparto 90/5/5'))
    return filas + nuevas, reg


# --------------------------------------------------------------- paso 2

def paso2_fugas(filas):
    """Retira de train el lado duplicado de cada fuga cross-split.

    Tres vias: (a) prompt casi identico por similitud del detector de la
    auditoria; (b) respuesta casi identica por similitud; (c) prompt propio
    EXACTO compartido con val/test (el filtro boiler del detector puede
    ocultar estas coincidencias cuando el prompt se repite >=3 veces en
    val/test; se tratan como fuga igualmente).
    """
    retirar = {}
    for i, j, cnt, sim in aud._pares_similares(
            filas, lambda f: aud.prompt_propio(f['humano']), aud.SIM_PROMPT_MIN):
        a, b = filas[i], filas[j]
        for t, o in ((a, b), (b, a)):
            if t['split'] == 'train' and o['split'] in ('val', 'test'):
                retirar.setdefault(t['sid'], 'fuga_prompt cross-split con %s (sim %.2f)' % (o['sid'], sim))
    for i, j, cnt, sim in aud._pares_similares(
            filas, lambda f: aud.limpia_texto(f['respuesta']), aud.SIM_RESP_MIN):
        a, b = filas[i], filas[j]
        for t, o in ((a, b), (b, a)):
            if t['split'] == 'train' and o['split'] in ('val', 'test'):
                retirar.setdefault(t['sid'], 'fuga_respuesta cross-split con %s (sim %.2f)' % (o['sid'], sim))
    hashes_valtest = set()
    for f in filas:
        if f['split'] in ('val', 'test'):
            pp = aud.prompt_propio(f['humano'])
            if len(pp) >= 40:
                hashes_valtest.add(aud._hash_norm(pp))
    for f in filas:
        if f['split'] != 'train':
            continue
        pp = aud.prompt_propio(f['humano'])
        if len(pp) >= 40 and aud._hash_norm(pp) in hashes_valtest:
            retirar.setdefault(f['sid'], 'prompt propio exacto compartido con val/test')
    return _retirar(filas, retirar)


# --------------------------------------------------------------- paso 3

def paso3_dedupe_prompts(filas, flags):
    """En train, mismo prompt propio con >=2 respuestas distintas: se conserva una."""
    grupos = defaultdict(list)
    for f in filas:
        if f['split'] != 'train':
            continue
        pp = aud.prompt_propio(f['humano'])
        if len(pp) >= 40:
            grupos[aud._hash_norm(pp)].append(f)
    retirar = {}
    for h in sorted(grupos):
        fs = grupos[h]
        if len(fs) < 2 or len({aud.fold(x['respuesta']) for x in fs}) < 2:
            continue

        def clave(f):
            banderas = 1 if (flags.get(f['sid'], set()) & BANDERAS_EXPURGO) else 0
            return (banderas, _idkey(f['id']), f['sid'])

        fs_orden = sorted(fs, key=clave)
        conserva = fs_orden[0]
        for f in fs_orden[1:]:
            retirar[f['sid']] = 'prompt duplicado en train (se conserva %s)' % conserva['sid']
    return _retirar(filas, retirar)


# --------------------------------------------------------------- paso 4

def paso4_alucinaciones(filas, flags):
    retirar = {}
    conservadas = []
    for f in filas:
        cats = flags.get(f['sid'], set())
        hit = [c for c in REMOVER_CATS if c in cats]
        if hit:
            retirar[f['sid']] = 'alucinacion de datos calculados: ' + ','.join(hit)
        else:
            for c in CONSERVAR_LISTADAS:
                if c in cats:
                    conservadas.append({'sid': f['sid'], 'id': f['id'], 'split': f['split'],
                                      'bloque': f['bloque'], 'categoria': c,
                                      'accion': 'conservada_listada'})
    nuevas, reg = _retirar(filas, retirar)
    return nuevas, reg, conservadas


# --------------------------------------------------------------- paso 5

def paso5_multiturno(filas):
    reg = []
    for f in filas:
        if f['bloque'] != BLOQUE_MULTI:
            continue
        f['raw']['bloque_origen'] = BLOQUE_MULTI
        f['raw']['bloque'] = BLOQUE_CONTEXTO
        f['bloque'] = BLOQUE_CONTEXTO
        reg.append(_registro(f, 'reetiquetado', 'multiturno no es tal -> consulta_con_contexto'))
    return filas, reg


# --------------------------------------------------------------- paso 6

def _prompt_key(f):
    return aud.prompt_propio(f['humano'])


def paso6_numerologia(filas, n_test=N_TEST_NUMEROLOGIA, n_val=N_VAL_NUMEROLOGIA):
    """Mueve numerologia de train a test/val sin crear fugas cross-split.

    Los prompts de numerologia comparten plantilla: el detector de la auditoria
    (filtro boiler de n-gramas) decide que filas pueden convivir en splits
    distintos. Se asignan los primeros candidatos y se repara en bucle: toda
    fila movida que fugue con train o entre val/test se retira y se rellena
    con el siguiente candidato hasta que no queden fugas.
    """
    train_num = sorted((f for f in filas if f['split'] == 'train' and f['bloque'] == 'numerologia'),
                      key=lambda f: (_idkey(f['id']), f['sid']))
    snap = [dict(f) for f in filas]
    prohibidos = set()
    for i, j, _cnt, _sim in aud._pares_similares(snap, _prompt_key, aud.SIM_PROMPT_MIN):
        a, b = snap[i], snap[j]
        t = a if a['split'] == 'train' else (b if b['split'] == 'train' else None)
        if t is not None:
            prohibidos.add(t['sid'])
    candidatos = [f for f in train_num if f['sid'] not in prohibidos]
    mov_test = candidatos[:n_test]
    mov_val = candidatos[n_test:n_test + n_val]
    usados = {f['sid'] for f in mov_test} | {f['sid'] for f in mov_val}

    def aplicar():
        for f in train_num:
            f['split'] = 'train'
        for f in mov_test:
            f['split'] = 'test'
        for f in mov_val:
            f['split'] = 'val'

    def detectar_leak():
        pares = aud._pares_similares(filas, _prompt_key, aud.SIM_PROMPT_MIN)
        mov = {f['sid'] for f in mov_test} | {f['sid'] for f in mov_val}
        leak = set()
        for i, j, _cnt, _sim in pares:
            a, b = filas[i], filas[j]
            if a['split'] == b['split']:
                continue
            if a['sid'] in mov and b['split'] == 'train':
                leak.add(a['sid'])
            if b['sid'] in mov and a['split'] == 'train':
                leak.add(b['sid'])
            if {a['split'], b['split']} == {'val', 'test'} and (a['sid'] in mov or b['sid'] in mov):
                leak.add(a['sid'] if a['sid'] in mov else b['sid'])
        return leak

    for _ in range(len(candidatos) + 1):
        aplicar()
        leak = detectar_leak()
        if not leak:
            break
        mov_test = [f for f in mov_test if f['sid'] not in leak]
        mov_val = [f for f in mov_val if f['sid'] not in leak]
        relleno = False
        for f in candidatos:
            if len(mov_test) >= n_test and len(mov_val) >= n_val:
                break
            if f['sid'] in usados or f['sid'] in leak:
                continue
            if len(mov_test) < n_test:
                mov_test.append(f)
            else:
                mov_val.append(f)
            usados.add(f['sid'])
            relleno = True
        if not relleno:
            aplicar()
            break
    aplicar()
    reg = []
    for f in mov_test:
        reg.append(_registro(f, 'movido_test', 'train -> test (numerologia sin test)'))
    for f in mov_val:
        reg.append(_registro(f, 'movido_val', 'train -> val (numerologia sin test)'))
    return filas, reg


# --------------------------------------------------------------- paso 7

def paso7_markdown(filas):
    _res, cap = _capturar(aud.check_idioma, filas)
    por_bloque = Counter(b for cat, b, _sid, _det in cap if cat == 'markdown_en_respuesta')
    return [{'bloque': b, 'filas_con_markdown': c} for b, c in sorted(por_bloque.items())]


# --------------------------------------------------------------- orquestación

def _escribir_jsonl(path, registros):
    with open(path, 'w', encoding='utf-8') as fh:
        for r in registros:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')


def _conteos(filas):
    c = Counter(f['split'] for f in filas)
    por_split = {s: c.get(s, 0) for s in ('train', 'val', 'test')}
    por_bloque_split = {'%s|%s' % k: v for k, v in sorted(
        Counter((f['bloque'], f['split']) for f in filas).items())}
    return {'total': len(filas), 'por_split': por_split, 'por_bloque_split': por_bloque_split}


def construir(v1d_dir=V1D_DEFAULT, out_dir=OUT_DEFAULT, fuera_v2=FUERA_V2_DEFAULT,
              semilla=SEMILLA, n_test_num=N_TEST_NUMEROLOGIA, n_val_num=N_VAL_NUMEROLOGIA):
    filas = cargar_filas_raw(v1d_dir)
    antes = _conteos(filas)
    cambios = os.path.join(out_dir, '_cambios')
    os.makedirs(cambios, exist_ok=True)

    flags, corruptas = capturar_flags(filas)

    filas, reg1 = paso1_fuera_alcance(filas)
    _escribir_jsonl(os.path.join(cambios, 'paso1_fuera_alcance.jsonl'), reg1)

    if fuera_v2 and os.path.exists(fuera_v2):
        filas, reg1b = paso1b_fuera_alcance_v2(filas, fuera_v2, semilla)
        estado1b = 'integradas %d filas desde %s' % (len(reg1b), fuera_v2)
        _escribir_jsonl(os.path.join(cambios, 'paso1b_fuera_alcance_v2.jsonl'), reg1b)
    else:
        reg1b = []
        estado1b = 'omitido: %s no existe (T136 pendiente); paso reanudable con --fuera-alcance-v2' % fuera_v2

    # El paso 2 (fugas) se ejecuta AL FINAL, sobre la composicion definitiva de
    # val/test: el filtro boiler del detector depende de que filas quedan en
    # val/test, y los pasos 4 y 6 cambian esa composicion.
    filas, reg3 = paso3_dedupe_prompts(filas, flags)
    _escribir_jsonl(os.path.join(cambios, 'paso3_dedupe_train.jsonl'), reg3)

    filas, reg4, cons4 = paso4_alucinaciones(filas, flags)
    _escribir_jsonl(os.path.join(cambios, 'paso4_alucinaciones.jsonl'), reg4)
    _escribir_jsonl(os.path.join(cambios, 'paso4_conservadas_listadas.jsonl'), cons4)

    filas, reg5 = paso5_multiturno(filas)
    _escribir_jsonl(os.path.join(cambios, 'paso5_multiturno.jsonl'), reg5)

    filas, reg6 = paso6_numerologia(filas, n_test_num, n_val_num)
    _escribir_jsonl(os.path.join(cambios, 'paso6_numerologia.jsonl'), reg6)

    filas, reg2 = paso2_fugas(filas)
    _escribir_jsonl(os.path.join(cambios, 'paso2_fugas.jsonl'), reg2)

    reg7 = paso7_markdown(filas)
    _escribir_jsonl(os.path.join(cambios, 'paso7_markdown.jsonl'), reg7)

    for split in ('train', 'val', 'test'):
        with open(os.path.join(out_dir, split + '.jsonl'), 'w', encoding='utf-8') as fh:
            for f in filas:
                if f['split'] == split:
                    fh.write(json.dumps(f['raw'], ensure_ascii=False) + '\n')

    despues = _conteos(filas)
    resumen = {
        'semilla': semilla,
        'v1d_dir': v1d_dir,
        'antes': antes,
        'despues': despues,
        'paso1_retiradas': len(reg1),
        'paso1b': estado1b,
        'paso2_retiradas': len(reg2),
        'paso3_retiradas': len(reg3),
        'paso4_retiradas': len(reg4),
        'paso4_conservadas_listadas': len(cons4),
        'paso5_reetiquetadas': len(reg5),
        'paso6_movidos_test': sum(1 for r in reg6 if r['accion'] == 'movido_test'),
        'paso6_movidos_val': sum(1 for r in reg6 if r['accion'] == 'movido_val'),
        'paso7_markdown': reg7,
        'corruptas_detectadas': len(corruptas),
    }
    with open(os.path.join(out_dir, 'resumen.json'), 'w', encoding='utf-8') as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description='Construir dataset v1e desde v1d (T141)')
    ap.add_argument('--v1d', default=V1D_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--fuera-alcance-v2', default=FUERA_V2_DEFAULT)
    ap.add_argument('--semilla', type=int, default=SEMILLA)
    ap.add_argument('--n-test-numerologia', type=int, default=N_TEST_NUMEROLOGIA)
    ap.add_argument('--n-val-numerologia', type=int, default=N_VAL_NUMEROLOGIA)
    args = ap.parse_args(argv)
    resumen = construir(args.v1d, args.out, args.fuera_alcance_v2, args.semilla,
                       args.n_test_numerologia, args.n_val_numerologia)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
