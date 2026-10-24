# -*- coding: utf-8 -*-
"""Tests de armar_dataset_v1g (T146). Solo unittest, casos sinteticos.

Cubre: detector determinista de voseo (falsos positivos y vosotros
peninsular), exclusion con registro en _cambios, informe de filas sin
bloque, recuento de tokens >4096, determinismo byte a byte y ausencia de
fuga train->val/test tras retirar filas.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import armar_dataset_v1g as g  # noqa: E402

SYS_GENERICO = ('Eres una experta en adivinacion: tarot, astrologia, '
               'numerologia y quiromancia.')


def fila(ident, bloque, humano, gpt, system=None):
    conv = []
    if system is not None:
        conv.append({'from': 'system', 'value': system})
    conv.append({'from': 'human', 'value': humano})
    conv.append({'from': 'gpt', 'value': gpt})
    d = {'conversations': conv}
    if ident is not None:
        d['id'] = ident
    if bloque is not None:
        d['bloque'] = bloque
    return d


def escribir_split(d_dir, split, filas):
    with open(os.path.join(d_dir, split + '.jsonl'), 'w',
             encoding='utf-8') as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + '\n')


def leer_jsonl(ruta):
    out = []
    with open(ruta, encoding='utf-8') as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                out.append(json.loads(linea))
    return out


def sha256_de(ruta):
    h = hashlib.sha256()
    with open(ruta, 'rb') as fh:
        h.update(fh.read())
    return h.hexdigest()


class TestDetectorVoseo(unittest.TestCase):
    def test_falsos_positivos_tuteo(self):
        for texto in ('mas alla de lo que ves', 'ademas todo esta bien',
                     'estas listo?', 'detrás de ti', 'interes puro',
                     'a traves del espejo'.replace('través', 'través'),
                     'despues vendra la calma', 'quizas sea mejor',
                     'viviras momentos intensos', 'casaras pronto'):
            self.assertFalse(g.es_voseo(texto), texto)

    def test_falso_positivo_pretérito_elegi(self):
        self.assertFalse(g.es_voseo('porque la elegi yo misma'))
        self.assertFalse(g.es_voseo('la carta que elegí representa el cambio'))

    def test_falso_positivo_tomas_nombre_propio(self):
        self.assertFalse(g.es_voseo('Como decia Tomas de Aquino, el todo es mayor'))
        self.assertFalse(g.es_voseo('Tomás de Aquino escribió sumas enteras'))

    def test_voseo_inequivoco(self):
        for texto in ('necesitás un cambio', 'usá esta carta',
                     'vos misma lo sabes', 'contame que ves',
                     'no podés ignorarlo', 'hacés lo que querés'):
            self.assertTrue(g.es_voseo(texto), texto)

    def test_ambigua_sin_marcador_es_voseo(self):
        self.assertTrue(g.es_voseo('te sentís cansada ultimamente'))
        self.assertTrue(g.es_voseo('si seguís asi el bloqueo crece'))
        self.assertTrue(g.es_voseo('lo que revelan de vos tus cartas'))

    def test_ambigua_con_marcador_es_vosotros(self):
        self.assertFalse(g.es_voseo('ambos os sentís identicos'))
        self.assertFalse(g.es_voseo('venís como estáis los dos'))
        self.assertFalse(g.es_voseo('vosotros lo vivís cada dia'))
        self.assertFalse(g.es_voseo('os entiendo y lo recibís bien'))
        self.assertFalse(g.es_voseo('ambas compartís el mismo miedo'))
        self.assertFalse(g.es_voseo('¿os sentís? sí, lo estáis'))

    def test_voseo_pese_a_otra_persona_en_texto(self):
        # «vos» inequivoco manda aunque haya tercera persona
        self.assertTrue(g.es_voseo('el consultante dice que vos no escuchás'))


class TestConstruirSintetico(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='v1g_test_')
        self.in_dir = os.path.join(self.tmp, 'v1f')
        self.out_dir = os.path.join(self.tmp, 'v1g')
        os.makedirs(self.in_dir)
        self.train = [
            fila(101, 'transitos', '¿Cómo va mi año?',
                 'Necesitás paciencia, el tránsito es lento.'),
            fila(102, 'lectura_completa', 'Léeme todo',
                 'vos misma tenés la respuesta dentro.'),
            fila(103, 'sinastria', '¿Cómo nos vemos?',
                 'ambos os sentís atraidos de forma mutua.'),
            fila(104, 'tarot_3', 'Tres cartas',
                 'más allá del miedo, estás a tiempo; la elegí por ti.'),
            fila(105, 'tarot_1', 'Una carta',
                 'Como decía Tomás de Aquino, la luz ilumina el camino.'),
            fila(None, None, 'Háblame de las runas nórdicas',
                 'Las runas son símbolos del futhark antiguo.',
                 system=SYS_GENERICO),
            fila(106, 'tarot_2', 'Dos cartas',
                 'El dos habla de equilibrio. ' + 'x' * 20000),
        ]
        self.val = [
            fila(201, 'transitos', '¿Qué siento?',
                 'te sentís perdida pero el camino se aclara.'),
            fila(202, 'numerologia', 'Mi número',
                 'Tu número es el 7, introspección y análisis.'),
        ]
        self.test = [
            fila(301, 'espanola_3', 'Tres de la española',
                 'El tres de copas celebra encuentros y alegrías.'),
        ]
        escribir_split(self.in_dir, 'train', self.train)
        escribir_split(self.in_dir, 'val', self.val)
        escribir_split(self.in_dir, 'test', self.test)
        self.resumen = g.construir(self.in_dir, self.out_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_retira_voseo_y_conserva_resto(self):
        ids_train = {f.get('id') for f in leer_jsonl(
            os.path.join(self.out_dir, 'train.jsonl'))}
        self.assertNotIn(101, ids_train)
        self.assertNotIn(102, ids_train)
        self.assertIn(103, ids_train)
        self.assertIn(104, ids_train)
        self.assertIn(105, ids_train)
        self.assertIn(106, ids_train)
        ids_val = {f.get('id') for f in leer_jsonl(
            os.path.join(self.out_dir, 'val.jsonl'))}
        self.assertNotIn(201, ids_val)
        self.assertIn(202, ids_val)

    def test_registro_voseo_retiradas(self):
        retiradas = leer_jsonl(os.path.join(
            self.out_dir, '_cambios', 'voseo_retiradas.jsonl'))
        self.assertEqual({r['id'] for r in retiradas}, {101, 102, 201})
        for r in retiradas:
            self.assertIn('split', r)
            self.assertIn('bloque', r)
            self.assertIn('fragmento', r)
            self.assertTrue(r['fragmento'])
        por_id = {r['id']: r for r in retiradas}
        self.assertEqual(por_id[101]['bloque'], 'transitos')
        self.assertEqual(por_id[101]['split'], 'train')
        self.assertEqual(por_id[201]['split'], 'val')

    def test_informe_sin_bloque(self):
        informe = json.loads(open(os.path.join(
            self.out_dir, '_cambios', 'sin_bloque_informe.json'),
            encoding='utf-8').read())
        self.assertEqual(informe['total'], 1)
        self.assertEqual(informe['por_split']['train'], 1)
        self.assertTrue(informe['ejemplos'])
        self.assertIn('decision', informe)

    def test_informe_tokens_exceden(self):
        informe = json.loads(open(os.path.join(
            self.out_dir, '_cambios', 'tokens_exceden_informe.json'),
            encoding='utf-8').read())
        self.assertEqual(informe['max_length'], 4096)
        self.assertEqual(informe['por_split']['train']['exceden'], 1)
        self.assertEqual(informe['por_split']['train']['bloques']['tarot_2'], 1)
        self.assertEqual(informe['por_split']['val']['exceden'], 0)
        self.assertIn('decision', informe)

    def test_resumen_y_semaforo(self):
        self.assertEqual(self.resumen['version'], 'v1g')
        self.assertEqual(self.resumen['antes']['total'], 10)
        self.assertEqual(self.resumen['despues']['total'], 7)
        self.assertIn('comparacion_v1f', self.resumen)
        self.assertIn(str(self.resumen['semforo']).lower(),
                      ('verde', 'amarillo', 'rojo'))

    def test_determinismo_dos_ejecuciones(self):
        out2 = os.path.join(self.tmp, 'v1g_bis')
        g.construir(self.in_dir, out2)
        for nombre in ('train.jsonl', 'val.jsonl', 'test.jsonl'):
            self.assertEqual(
                sha256_de(os.path.join(self.out_dir, nombre)),
                sha256_de(os.path.join(out2, nombre)), nombre)
        for nombre in ('voseo_retiradas.jsonl', 'sin_bloque_informe.json',
                      'tokens_exceden_informe.json'):
            self.assertEqual(
                sha256_de(os.path.join(self.out_dir, '_cambios', nombre)),
                sha256_de(os.path.join(out2, '_cambios', nombre)), nombre)
        # El resumen difiere solo en 'rutas' (ruta de salida); el resto
        # debe ser identico byte a byte.
        res_a = json.loads(open(os.path.join(self.out_dir, 'resumen.json'),
                               encoding='utf-8').read())
        res_b = json.loads(open(os.path.join(out2, 'resumen.json'),
                               encoding='utf-8').read())
        res_a.pop('rutas', None)
        res_b.pop('rutas', None)
        self.assertEqual(
            json.dumps(res_a, sort_keys=True, ensure_ascii=False),
            json.dumps(res_b, sort_keys=True, ensure_ascii=False))

    def test_sin_fuga_train_val_test(self):
        import auditoria_v1d as aud
        hashes_train = set()
        for f in leer_jsonl(os.path.join(self.out_dir, 'train.jsonl')):
            pp = aud.prompt_propio(f['conversations'][0]['value']
                                  if f['conversations'][0]['from'] == 'human'
                                  else next(t['value'] for t in f['conversations']
                                          if t['from'] == 'human'))
            if len(pp) >= 40:
                hashes_train.add(aud._hash_norm(pp))
        for split in ('val', 'test'):
            for f in leer_jsonl(os.path.join(self.out_dir, split + '.jsonl')):
                pp = next(t['value'] for t in f['conversations']
                         if t['from'] == 'human')
                if len(pp) >= 40:
                    self.assertNotIn(aud._hash_norm(pp), hashes_train,
                                    'fuga en %s: %s' % (split, pp[:40]))


V1F_REAL = '/Users/angelgonzalez/fase0/dataset_fase1_v1f'


@unittest.skipUnless(os.path.isdir(V1F_REAL), 'v1f no disponible')
class TestSobreV1FReal(unittest.TestCase):
    """Verificacion sobre el dataset real (clasificacion contextual
    verificada a mano el 2026-10-24, por sid: los ids de v1f son mixtos
    y hay 693 duplicados, asi que se compara por hash del JSON de la
    fila). 15 filas de voseo real fuera; 16 conservadas (13 vosotros
    peninsulares + 2 falsos positivos + 1 mixto con marcadores validos)."""

    RETIRADAS_SIDS = {
        'train#242 id=19246', 'train#1487 id=2201', 'train#3299 id=35587',
        'train#3438 id=1442', 'train#4977 id=892', 'train#5427 id=13048',
        'train#5556 id=2353', 'train#6637 id=36322', 'train#7415 id=18190',
        'train#8590 id=3558', 'train#8653 id=35809', 'train#8924 id=12632',
        'train#9441 id=None', 'train#9874 id=286', 'val#189 id=35697',
    }
    CONSERVADAS_SIDS = {
        'train#2419 id=29087', 'train#2786 id=21709', 'train#2911 id=28895',
        'train#3418 id=12533', 'train#3706 id=11657', 'train#4918 id=432',
        'train#5012 id=13183', 'train#6330 id=1001', 'train#6363 id=22419',
        'train#6892 id=13117', 'train#7522 id=None', 'train#9107 id=10673',
        'train#9213 id=981', 'train#9405 id=28724', 'val#170 id=28952',
        'test#254 id=28699',
    }

    @classmethod
    def setUpClass(cls):
        import armar_dataset_v1e as v1e
        cls.hash_por_sid = {}
        for f in v1e.cargar_filas_raw(V1F_REAL):
            h = hashlib.sha256(
                json.dumps(f['raw'], sort_keys=True,
                         ensure_ascii=False).encode('utf-8')).hexdigest()
            cls.hash_por_sid[f['sid']] = h

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='v1g_real_')
        self.out_dir = os.path.join(self.tmp, 'v1g')
        self.resumen = g.construir(V1F_REAL, self.out_dir)
        self.hash_salida = set()
        for split in ('train', 'val', 'test'):
            for f in leer_jsonl(os.path.join(self.out_dir, split + '.jsonl')):
                self.hash_salida.add(hashlib.sha256(
                    json.dumps(f, sort_keys=True,
                             ensure_ascii=False).encode('utf-8')).hexdigest())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_retiradas_no_presentes(self):
        for sid in self.RETIRADAS_SIDS:
            self.assertNotIn(self.hash_por_sid[sid], self.hash_salida,
                           'sigue presente: %s' % sid)

    def test_conservadas_presentes(self):
        for sid in self.CONSERVADAS_SIDS:
            self.assertIn(self.hash_por_sid[sid], self.hash_salida,
                         'falta: %s' % sid)

    def test_recuentos_reales(self):
        self.assertEqual(self.resumen['antes']['total'], 12330)
        self.assertEqual(self.resumen['despues']['total'], 12330 - 15)
        self.assertEqual(self.resumen['despues']['por_split']['train'], 10909)
        self.assertEqual(self.resumen['despues']['por_split']['val'], 704)
        self.assertEqual(self.resumen['despues']['por_split']['test'], 702)
        retiradas = leer_jsonl(os.path.join(
            self.out_dir, '_cambios', 'voseo_retiradas.jsonl'))
        self.assertEqual(len(retiradas), 15)


if __name__ == '__main__':
    unittest.main()
