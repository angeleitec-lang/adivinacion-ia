# -*- coding: utf-8 -*-
"""Arma el dataset v1g (T146) limpiando v1f.

Cambios respecto a v1f (los demas bytes se conservan identicos):

1. Voseo: se retiran las filas cuya respuesta contiene voseo real. El
   detector es determinista y contextual: parte de la lista cerrada
   ``VOSEO_FORMS`` de ``regenerar_fuera_alcance`` y descarta los falsos
   positivos conocidos:
   * formas ambiguas con vosotros peninsular (``sentís``, ``seguís``,
     ``venís``...) se conservan si la fila lleva marcador de vosotros
     (``os``, ``vosotros``, ``estáis``, ``tenéis``, ``ambos/ambas``,
     ``dais``);
   * ``elegí``/``escribí`` (preterito 1.a persona) nunca disparan solas;
   * ``Tomás`` seguido de `` de `` se trata como nombre propio.
   Las filas retiradas se listan en ``_cambios/voseo_retiradas.jsonl``
   con split, id, bloque y fragmento. No se reesponde a mano ninguna
   respuesta: o se conserva o se retira la fila entera.

2. Sin bloque: se informa en ``_cambios/sin_bloque_informe.json``. Son
   filas de corpus real (web) integradas en v1d que nunca tuvieron bloque;
   sus prompts son explicadores genericos multi-tema (muchos de runas,
   quiromancia o I Ching, fuera del alcance del producto), por lo que NO
   se puede inferir un bloque existente de forma segura. Se conservan
   sin bloque y se documentan.

3. Tokens > 4096: recuento por split y bloque con la misma estimacion
   del piloto (chars/3.5, config qlora_14b). No se recorta nada: no hay
   una forma segura de recortar sin degradar la lectura, y quitar filas
   largas enteras reduciria familias ya minoritarias. Se documenta.

Determinista e idempotente: misma entrada -> mismos bytes de salida.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
if str(CORPUS_DIR) not in sys.path:
    sys.path.insert(0, str(CORPUS_DIR))

import armar_dataset_v1e as v1e  # noqa: E402
import armar_dataset_v1f as v1f  # noqa: E402
import comprobar_piloto as cp  # noqa: E402
from regenerar_fuera_alcance import RE_VOSEO  # noqa: E402

FASE0 = '/Users/angelgonzalez/fase0'
V1F_DEFAULT = os.path.join(FASE0, 'dataset_fase1_v1f')
OUT_DEFAULT = os.path.join(FASE0, 'dataset_fase1_v1g')
CONFIG_PILOTO = 'qlora_14b.yaml'

# Formas de VOSEO_FORMS que tambien existen en vosotros peninsular
# (2.a plural). Solo son voseo si la fila NO lleva marcador de vosotros.
AMB_VOSONOS = frozenset((
    'sentis', 'vivis', 'seguis', 'venis', 'pedis', 'dormis', 'abris',
    'escribis', 'compartis', 'recibis', 'preferis',
))
# Formas que casan con preterito indefinido de 1.a persona: nunca voseo.
AMB_PRETERITO = frozenset(('elegi', 'escribi'))

RE_VOSONOS_MARK = re.compile(
    r'\b(os|vosotros|est[aá]is|ten[eé]is|ambos|ambas|dais)\b', re.IGNORECASE)
RE_TOMAS_NOMBRE = re.compile(r'\bTom[aá]s de\b')


def _ascii_forma(forma):
    return (forma.replace('á', 'a').replace('é', 'e').replace('í', 'i')
            .replace('ó', 'o').replace('ú', 'u'))


def formas_voseo(texto):
    """Formas voseantes reales de un texto (dictadas por la regla
    determinista contextual). Devuelve lista de coincidencias crudas."""
    if not texto:
        return []
    marcado = bool(RE_VOSONOS_MARK.search(texto))
    nombre_tomas = bool(RE_TOMAS_NOMBRE.search(texto))
    halladas = []
    for m in RE_VOSEO.finditer(texto):
        forma = m.group(1)
        base = _ascii_forma(forma.lower())
        if base in AMB_PRETERITO:
            continue
        if base == 'tomas' and nombre_tomas:
            continue
        if base in AMB_VOSONOS and marcado:
            continue
        halladas.append(forma)
    return halladas


def es_voseo(texto):
    """True si el texto contiene voseo real bajo la regla determinista."""
    return bool(formas_voseo(texto))


def fragmento_voseo(texto, ancho=80):
    """Fragmento con contexto de la primera forma voseante del texto."""
    formas = formas_voseo(texto)
    if not formas:
        return None
    forma = formas[0]
    pos = texto.lower().find(forma.lower())
    ini = max(0, pos - ancho // 2)
    fin = min(len(texto), pos + len(forma) + ancho // 2)
    prefijo = '...' if ini > 0 else ''
    sufijo = '...' if fin < len(texto) else ''
    return {'forma': forma, 'formas': sorted(set(formas)),
            'fragmento': prefijo + texto[ini:fin] + sufijo}


def _tokens_fila(raw):
    texto = '\n'.join(str(t.get('value', ''))
                      for t in raw.get('conversations', [])
                      if isinstance(t, dict))
    return cp.estimar_tokens(texto)


def clasificar_voseo(filas):
    """Divide las filas en (conservadas, retiradas)."""
    ok, retiradas = [], []
    for f in filas:
        det = fragmento_voseo(f['respuesta'])
        if det:
            retiradas.append({'split': f['split'], 'id': f['id'],
                            'bloque': f['bloque'], 'sid': f['sid'],
                            'forma': det['forma'],
                            'formas': det['formas'],
                            'fragmento': det['fragmento']})
        else:
            ok.append(f)
    return ok, retiradas


def informe_sin_bloque(filas, max_ejemplos=12):
    """Informe determinista de las filas sin bloque."""
    sin_bloque = [f for f in filas if f['bloque'] == 'sin_bloque']
    por_split = collections.Counter(f['split'] for f in sin_bloque)
    ejemplos = []
    for f in sorted(sin_bloque, key=lambda f: f['sid'])[:max_ejemplos]:
        ejemplos.append({'split': f['split'], 'sid': f['sid'],
                        'humano': f['humano'][:160]})
    return {
        'total': len(sin_bloque),
        'por_split': {s: por_split.get(s, 0)
                     for s in ('train', 'val', 'test')},
        'origen': ('Filas de corpus real (web) integradas en v1d '
                  '(docs/ARMAR_DATASET_V1D.md: real-corpus 488); nunca '
                  'tuvieron bloque. System generico comun y prompts '
                  'explicadores multi-tema.'),
        'decision': ('NO se infiere un bloque existente: los temas son '
                     'dispares y muchos (runas, quiromancia, I Ching) '
                     'estan fuera del alcance del producto. Se conservan '
                     'sin bloque y se documentan aqui.'),
        'ejemplos': ejemplos,
    }


def informe_tokens(filas, max_length):
    """Recuento de filas que exceden la ventana de contexto."""
    por_split = {}
    for split in ('train', 'val', 'test'):
        del_split = [f for f in filas if f['split'] == split]
        exceden = [f for f in del_split
                   if _tokens_fila(f['raw']) > max_length]
        por_bloque = collections.Counter(f['bloque'] for f in exceden)
        por_split[split] = {
            'n': len(del_split),
            'exceden': len(exceden),
            'pct': round(100.0 * len(exceden) / len(del_split), 2)
            if del_split else 0.0,
            'bloques': dict(sorted(por_bloque.items())),
        }
    return {
        'max_length': max_length,
        'estimacion': 'chars/3.5 (comprobar_piloto.estimar_tokens)',
        'por_split': por_split,
        'decision': ('No se recorta ninguna fila: no existe un recorte '
                     'seguro que preserve el sentido de la lectura, y '
                     'quitar filas enteras reduciria familias ya '
                     'minoritarias. Queda documentado para decidir la '
                     'politica de truncamiento en el piloto.'),
    }


def _bloque_total(conteo_bloque_split, bloque):
    prefijo = bloque + '|'
    return sum(v for k, v in conteo_bloque_split.items()
              if k.startswith(prefijo))


def construir(v1f_dir=V1F_DEFAULT, out_dir=OUT_DEFAULT):
    """Construye v1g a partir de v1f. Devuelve el resumen."""
    filas_v1f = v1e.cargar_filas_raw(v1f_dir)
    antes = v1e._conteos(filas_v1f)

    conservadas, retiradas_voseo = clasificar_voseo(filas_v1f)
    informe_sb = informe_sin_bloque(conservadas)
    max_length = int(cp.cargar_config_piloto(CONFIG_PILOTO).get(
        'max_length', 4096))
    informe_tok = informe_tokens(conservadas, max_length)

    os.makedirs(out_dir, exist_ok=True)
    cambios = os.path.join(out_dir, '_cambios')
    os.makedirs(cambios, exist_ok=True)

    for split in ('train', 'val', 'test'):
        v1e._escribir_jsonl(
            os.path.join(out_dir, split + '.jsonl'),
            [f['raw'] for f in conservadas if f['split'] == split])

    despues = v1e._conteos(conservadas)
    retiradas_cs = collections.Counter(
        '%s|%s' % (r['bloque'], r['split']) for r in retiradas_voseo)

    bloques = sorted(set(k.split('|')[0] for k in antes['por_bloque_split'])
                    | set(k.split('|')[0] for k in despues['por_bloque_split']))
    comparacion = {b: {'v1f': _bloque_total(antes['por_bloque_split'], b),
                      'v1g': _bloque_total(despues['por_bloque_split'], b)}
                  for b in bloques}

    semaforo, errores, avisos = v1f._semforo_v1e_logica(conservadas)

    sha_splits = {}
    for split in ('train', 'val', 'test'):
        ruta = os.path.join(out_dir, split + '.jsonl')
        with open(ruta, 'rb') as fh:
            sha_splits[split] = hashlib.sha256(fh.read()).hexdigest()

    resumen = {
        'version': 'v1g',
        'rutas': {'v1f': str(v1f_dir), 'salida': str(out_dir)},
        'antes': antes,
        'despues': despues,
        'comparacion_v1f': comparacion,
        'retiradas_voseo': dict(sorted(retiradas_cs.items())),
        'sin_bloque': informe_sb['por_split'],
        'tokens_exceden': {s: informe_tok['por_split'][s]['exceden']
                          for s in ('train', 'val', 'test')},
        'sha256_splits': sha_splits,
        'semforo': semaforo,
        'semforo_detalle': {'errores': errores, 'avisos': avisos},
    }
    with open(os.path.join(out_dir, 'resumen.json'), 'w',
             encoding='utf-8') as fh:
        json.dump(resumen, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write('\n')

    v1e._escribir_jsonl(os.path.join(cambios, 'voseo_retiradas.jsonl'),
                        retiradas_voseo)
    with open(os.path.join(cambios, 'sin_bloque_informe.json'), 'w',
             encoding='utf-8') as fh:
        json.dump(informe_sb, fh, ensure_ascii=False, sort_keys=True,
                  indent=2)
        fh.write('\n')
    with open(os.path.join(cambios, 'tokens_exceden_informe.json'), 'w',
             encoding='utf-8') as fh:
        json.dump(informe_tok, fh, ensure_ascii=False, sort_keys=True,
                  indent=2)
        fh.write('\n')
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--v1f', default=V1F_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    resumen = construir(args.v1f, args.out)
    print('v1g construido en %s' % args.out)
    print('antes: %d filas | despues: %d filas'
          % (resumen['antes']['total'], resumen['despues']['total']))
    print('retiradas por voseo: %s'
          % json.dumps(resumen['retiradas_voseo'], ensure_ascii=False))
    print('sin bloque: %s' % json.dumps(resumen['sin_bloque'],
                                       ensure_ascii=False))
    print('tokens >%d: %s' % (4096, json.dumps(resumen['tokens_exceden'],
                                               ensure_ascii=False)))
    print('semaforo (logica v1e): %s' % resumen['semforo'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
