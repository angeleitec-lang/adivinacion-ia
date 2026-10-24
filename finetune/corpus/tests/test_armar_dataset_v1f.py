# -*- coding: utf-8 -*-
"""Tests adversos de armar_dataset_v1f (T144). Solo unittest, casos sinteticos."""
import hashlib
import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import armar_dataset_v1f as v1f  # noqa: E402

CANON = (
    'Eres un oraculo experto en tarot, baraja espanola, astrologia y numerologia. '
    'Responde siempre en espanol estandar con tuteo, con calidez y prudencia, '
    'sin prometer hechos futuros concretos ni dar consejo medico, legal o financiero.'
)
BASE_SYS = 'Sistema base de tarot canonico para las demas familias del dataset.'

PALABRAS = [
    'amor', 'trabajo', 'dinero', 'salud', 'viaje', 'familia', 'amistad',
    'estudios', 'arte', 'fe', 'miedo', 'esperanza', 'cambio', 'hogar',
    'camino', 'decision', 'sueno', 'tiempo', 'fuerza', 'calma',
]


def prompt_unico(i):
    rnd = random.Random(9000 + i)
    cuerpo = ' '.join(rnd.choice(PALABRAS) for _ in range(14))
    return (
        'Consulta numero %d: quiero una lectura detallada sobre %s '
        'con consejo practico y honesto para mi vida diaria.' % (i, cuerpo)
    )


def fila_raw(system, human, gpt, idn, bloque):
    return {
        'conversations': [
            {'from': 'system', 'value': system},
            {'from': 'human', 'value': human},
            {'from': 'gpt', 'value': gpt},
        ],
        'id': idn,
        'bloque': bloque,
        'generador': 'sintetico',
    }


def fila_int(split, sid, idn, bloque, human, gpt):
    return {'split': split, 'idx': 0, 'sid': sid, 'id': idn, 'bloque': bloque,
            'familiar': 'otros', 'calculos': None, 'humano': human,
            'respuesta': gpt, 'raw': {}, 'origen': 'test'}


def escribir_jsonl(path, filas):
    with open(path, 'w', encoding='utf-8') as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + '\n')


def leer_jsonl(path):
    out = []
    with open(path, encoding='utf-8') as fh:
        for linea in fh:
            if linea.strip():
                out.append(json.loads(linea))
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        h.update(fh.read())
    return h.hexdigest()


def mini_v1e(dirpath):
    """v1e mini: base tarot_1 + viejas etica/espanola_1 (deben desaparecer)."""
    os.makedirs(dirpath, exist_ok=True)
    train = [fila_raw(BASE_SYS, prompt_unico(100 + i), 'Respuesta base %d.' % i,
                     900 + i, 'tarot_1') for i in range(3)]
    train.append(fila_raw(CANON, prompt_unico(200), 'Etica vieja train.', 11, 'etica'))
    train.append(fila_raw(CANON, prompt_unico(201), 'Espanola vieja train.', 12, 'espanola_1'))
    val = [fila_raw(BASE_SYS, prompt_unico(110), 'Resp val base.', 910, 'tarot_1'),
           fila_raw(CANON, prompt_unico(202), 'Etica vieja val.', 13, 'etica'),
           fila_raw(CANON, prompt_unico(203), 'Espanola vieja val.', 14, 'espanola_1')]
    test = [fila_raw(BASE_SYS, prompt_unico(120), 'Resp test base.', 920, 'tarot_1'),
            fila_raw(CANON, prompt_unico(204), 'Etica vieja test.', 15, 'etica')]
    escribir_jsonl(os.path.join(dirpath, 'train.jsonl'), train)
    escribir_jsonl(os.path.join(dirpath, 'val.jsonl'), val)
    escribir_jsonl(os.path.join(dirpath, 'test.jsonl'), test)
    return dirpath


def nuevas_fa(n, start=1, system=CANON, bloque='fuera_alcance'):
    return [fila_raw(system, prompt_unico(300 + i),
                    'No puedo ayudarte con eso, consulta a un profesional.',
                    start + i, bloque) for i in range(n)]


def nuevas_ee(n_etica, n_esp, start=1, system=CANON):
    filas = []
    for i in range(n_etica):
        filas.append(fila_raw(system, prompt_unico(400 + i),
                             'Respuesta etica %d con prudencia y limite claro.' % i,
                             start + i, 'etica'))
    for i in range(n_esp):
        filas.append(fila_raw(system, prompt_unico(500 + i),
                             'Lectura con oros y copas %d, consejo templado.' % i,
                             start + 100 + i, 'espanola_1'))
    return filas


def construir_todo(tmp, fa=None, ee=None, semilla=144):
    v1e_dir = mini_v1e(os.path.join(tmp, 'v1e'))
    fa_ruta = os.path.join(tmp, 'fa.jsonl')
    ee_ruta = os.path.join(tmp, 'ee.jsonl')
    escribir_jsonl(fa_ruta, fa if fa is not None else nuevas_fa(10))
    escribir_jsonl(ee_ruta, ee if ee is not None else nuevas_ee(10, 10))
    out = os.path.join(tmp, 'v1f')
    resumen = v1f.construir(v1e_dir=v1e_dir, fa_ruta=fa_ruta, ee_ruta=ee_ruta,
                            out_dir=out, semilla=semilla)
    return out, resumen


class TestIntegridadBasica(unittest.TestCase):
    def test_desaparecen_las_viejas_de_v1e(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = construir_todo(tmp)
            ids_out = set()
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    ids_out.add(f['id'])
            for viejo in (11, 12, 13, 14, 15):
                self.assertNotIn(viejo, ids_out)

    def test_base_tarot_se_conserva(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = construir_todo(tmp)
            ids_out = set()
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    ids_out.add(f['id'])
            for base in (900, 901, 902, 910, 920):
                self.assertIn(base, ids_out)

    def test_reparto_80_10_10_por_bloque(self):
        with tempfile.TemporaryDirectory() as tmp:
            ee = nuevas_ee(40, 20)
            out, _ = construir_todo(tmp, fa=nuevas_fa(40), ee=ee)
            por_bloque_split = {}
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    if f['bloque'] in v1f.BLOQUES_SWAP:
                        clave = (f['bloque'], split)
                        por_bloque_split[clave] = por_bloque_split.get(clave, 0) + 1
            self.assertEqual(por_bloque_split[('fuera_alcance', 'train')], 32)
            self.assertEqual(por_bloque_split[('fuera_alcance', 'val')], 4)
            self.assertEqual(por_bloque_split[('fuera_alcance', 'test')], 4)
            self.assertEqual(por_bloque_split[('etica', 'train')], 32)
            self.assertEqual(por_bloque_split[('etica', 'val')], 4)
            self.assertEqual(por_bloque_split[('etica', 'test')], 4)
            self.assertEqual(por_bloque_split[('espanola_1', 'train')], 16)
            self.assertEqual(por_bloque_split[('espanola_1', 'val')], 2)
            self.assertEqual(por_bloque_split[('espanola_1', 'test')], 2)


class TestReglasHeredadas(unittest.TestCase):
    def test_prompt_duplicado_entre_nuevas_se_descarta(self):
        dup = fila_raw(CANON, prompt_unico(700), 'Respuesta uno.', 7001, 'etica')
        dup2 = fila_raw(CANON, prompt_unico(700), 'Respuesta dos distinta.',
                       7002, 'etica')
        ee = nuevas_ee(8, 8) + [dup, dup2]
        with tempfile.TemporaryDirectory() as tmp:
            out, resumen = construir_todo(tmp, ee=ee)
            supervivientes = 0
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    if f['id'] in (7001, 7002):
                        supervivientes += 1
            self.assertEqual(supervivientes, 1)
            self.assertGreaterEqual(resumen['descartes'].get('prompt_duplicado', 0), 1)

    def test_fuga_prompt_nuevo_train_vs_base_val(self):
        base = [fila_int('val', 'val#0 id=910', 910, 'tarot_1',
                        prompt_unico(110), 'Resp val base.')]
        nuevo = [fila_int('train', 'nuevo:fa#0 id=8001', 8001, 'fuera_alcance',
                         prompt_unico(110).replace('diaria', 'diurna'),
                         'Nuevo que copia un prompt de val.')]
        ok, descartes = v1f.filtrar_fugas_y_dupes(base, nuevo)
        self.assertEqual(ok, [])
        self.assertEqual(descartes[0]['motivo'], 'fuga_prompt')
        self.assertEqual(descartes[0]['pareja'], 'val#0 id=910')

    def test_fuga_prompt_nuevo_val_vs_base_train(self):
        base = [fila_int('train', 'train#0 id=900', 900, 'tarot_1',
                        prompt_unico(100), 'Resp base train.')]
        nuevo = [fila_int('val', 'nuevo:ee#0 id=8002', 8002, 'etica',
                         prompt_unico(100).replace('diaria', 'diurna'),
                         'Nueva etica que copia prompt de train.')]
        ok, descartes = v1f.filtrar_fugas_y_dupes(base, nuevo)
        self.assertEqual(ok, [])
        self.assertEqual(descartes[0]['motivo'], 'fuga_prompt')

    def test_similares_mismo_split_no_es_fuga(self):
        base = [fila_int('train', 'train#0 id=900', 900, 'tarot_1',
                        prompt_unico(100), 'Resp base train.')]
        nuevo = [fila_int('train', 'nuevo:ee#0 id=8003', 8003, 'etica',
                         prompt_unico(100).replace('diaria', 'diurna'),
                         'Nueva etica parecida pero mismo split.')]
        ok, descartes = v1f.filtrar_fugas_y_dupes(base, nuevo)
        self.assertEqual(len(ok), 1)
        self.assertEqual(descartes, [])

    def test_dup_exact_nuevo_vs_base_cross_split(self):
        base = [fila_int('val', 'val#0 id=910', 910, 'tarot_1',
                        prompt_unico(110), 'Resp val base.')]
        nuevo = [fila_int('train', 'nuevo:fa#0 id=8004', 8004, 'fuera_alcance',
                         prompt_unico(110), 'Nueva con prompt exacto de val.')]
        ok, descartes = v1f.filtrar_fugas_y_dupes(base, nuevo)
        self.assertEqual(ok, [])
        self.assertEqual(descartes[0]['motivo'], 'prompt_duplicado')

    def test_fuga_respuesta_nuevo_vs_base(self):
        resp = ('Esta lectura muestra un cambio importante en tu vida afectiva '
               'durante las proximas semanas con mucha prudencia y calma')
        base = [fila_int('test', 'test#0 id=920', 920, 'tarot_1',
                        prompt_unico(120), resp)]
        nuevo = [fila_int('train', 'nuevo:fa#0 id=8005', 8005, 'fuera_alcance',
                         prompt_unico(130), resp)]
        ok, descartes = v1f.filtrar_fugas_y_dupes(base, nuevo)
        self.assertEqual(ok, [])
        self.assertEqual(descartes[0]['motivo'], 'fuga_respuesta')

    def test_voseo_en_respuesta_se_descarta(self):
        voseo = fila_raw(CANON, prompt_unico(710),
                        'No quiero que te alteres, pero vos deberias consultar a un medico.',
                        8101, 'etica')
        ee = nuevas_ee(8, 8) + [voseo]
        with tempfile.TemporaryDirectory() as tmp:
            out, resumen = construir_todo(tmp, ee=ee)
            ids_out = set()
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    ids_out.add(f['id'])
            self.assertNotIn(8101, ids_out)
            self.assertGreaterEqual(resumen['descartes'].get('voseo', 0), 1)

    def test_chino_o_cirilico_se_descarta(self):
        con_chino = fila_raw(CANON, prompt_unico(720) + ' 你好',
                            'Respuesta limpia.', 8201, 'etica')
        con_cirilico = fila_raw(CANON, prompt_unico(721),
                               'Respuesta con Привет dentro.', 8202, 'espanola_1')
        ee = nuevas_ee(8, 8) + [con_chino, con_cirilico]
        with tempfile.TemporaryDirectory() as tmp:
            out, resumen = construir_todo(tmp, ee=ee)
            ids_out = set()
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    ids_out.add(f['id'])
            self.assertNotIn(8201, ids_out)
            self.assertNotIn(8202, ids_out)
            self.assertGreaterEqual(resumen['descartes'].get('idioma_no_es', 0), 2)

    def test_fila_sin_bloque_se_descarta(self):
        sin_bloque = fila_raw(CANON, prompt_unico(730), 'Respuesta.', 8301, None)
        ee = nuevas_ee(8, 8) + [sin_bloque]
        with tempfile.TemporaryDirectory() as tmp:
            _, resumen = construir_todo(tmp, ee=ee)
            self.assertGreaterEqual(resumen['descartes'].get('esquema_roto', 0), 1)

    def test_bloque_fuera_del_swap_se_descarta(self):
        intruso = fila_raw(CANON, prompt_unico(731), 'Respuesta.', 8302, 'tarot_1')
        ee = nuevas_ee(8, 8) + [intruso]
        with tempfile.TemporaryDirectory() as tmp:
            _, resumen = construir_todo(tmp, ee=ee)
            self.assertGreaterEqual(resumen['descartes'].get('esquema_roto', 0), 1)

    def test_esquema_roto_sin_conversations_o_sin_gpt(self):
        sin_conv = {'id': 8401, 'bloque': 'etica'}
        sin_gpt = {'conversations': [
            {'from': 'system', 'value': CANON},
            {'from': 'human', 'value': prompt_unico(740)},
        ], 'id': 8402, 'bloque': 'etica'}
        rol_invalido = {'conversations': [
            {'from': 'system', 'value': CANON},
            {'from': 'user', 'value': prompt_unico(741)},
            {'from': 'gpt', 'value': 'x'},
        ], 'id': 8403, 'bloque': 'etica'}
        ee = nuevas_ee(8, 8) + [sin_conv, sin_gpt, rol_invalido]
        with tempfile.TemporaryDirectory() as tmp:
            _, resumen = construir_todo(tmp, ee=ee)
            self.assertGreaterEqual(resumen['descartes'].get('esquema_roto', 0), 3)

    def test_system_no_canonico_se_normaliza(self):
        raro = fila_raw('Sistema raro que no es el canonico.', prompt_unico(750),
                       'Respuesta con system raro.', 8501, 'etica')
        ee = nuevas_ee(8, 8) + [raro]
        with tempfile.TemporaryDirectory() as tmp:
            out, resumen = construir_todo(tmp, ee=ee)
            encontrado = None
            for split in ('train', 'val', 'test'):
                for f in leer_jsonl(os.path.join(out, '%s.jsonl' % split)):
                    if f['id'] == 8501:
                        encontrado = f
            self.assertIsNotNone(encontrado)
            self.assertEqual(encontrado['conversations'][0]['value'], CANON)
            self.assertGreaterEqual(
                resumen['system_canonico']['normalizadas_nuevas'], 1)


class TestResumen(unittest.TestCase):
    def test_resumen_antes_despues_y_comparacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, resumen = construir_todo(tmp)
            self.assertEqual(resumen['semilla'], 144)
            self.assertEqual(resumen['antes']['por_bloque_split']['etica|train'], 1)
            self.assertEqual(resumen['antes']['por_bloque_split']['etica|val'], 1)
            self.assertEqual(resumen['antes']['por_bloque_split']['etica|test'], 1)
            self.assertEqual(resumen['retiradas_viejas']['etica|train'], 1)
            self.assertEqual(resumen['retiradas_viejas']['espanola_1|test'], 0)
            despues = resumen['despues']['por_bloque_split']
            self.assertEqual(despues['etica|train'] + despues['etica|val']
                             + despues['etica|test'], 10)
            self.assertIn('etica', resumen['comparacion_v1e'])
            self.assertEqual(resumen['comparacion_v1e']['etica']['v1e'], 3)
            self.assertEqual(resumen['comparacion_v1e']['fuera_alcance']['v1e'], 0)
            self.assertIn('semforo', resumen)
            self.assertIn(resumen['semforo'], ('verde', 'amarillo', 'rojo'))

    def test_cambios_escritos(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = construir_todo(tmp)
            cambios = os.path.join(out, '_cambios')
            for nombre in ('paso1_retirada_bloques_viejos.jsonl',
                          'paso2_integracion_nuevas.jsonl',
                          'paso3_descartes.jsonl'):
                self.assertTrue(os.path.exists(os.path.join(cambios, nombre)),
                                nombre)


class TestDeterminismo(unittest.TestCase):
    def test_dos_ejecuciones_mismo_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fa = nuevas_fa(20)
            ee = nuevas_ee(20, 20)
            out1, res1 = construir_todo(
                os.path.join(tmp, 'a'), fa=fa, ee=ee)
            out2, res2 = construir_todo(
                os.path.join(tmp, 'b'), fa=fa, ee=ee)
            for split in ('train', 'val', 'test'):
                self.assertEqual(
                    sha256(os.path.join(out1, '%s.jsonl' % split)),
                    sha256(os.path.join(out2, '%s.jsonl' % split)), split)
            res1.pop('rutas', None)
            res2.pop('rutas', None)
            self.assertEqual(json.dumps(res1, sort_keys=True, ensure_ascii=False),
                             json.dumps(res2, sort_keys=True, ensure_ascii=False))

    def test_idempotencia_mismo_directorio(self):
        with tempfile.TemporaryDirectory() as tmp:
            fa = nuevas_fa(20)
            ee = nuevas_ee(20, 20)
            out1, _ = construir_todo(tmp, fa=fa, ee=ee)
            h1 = {s: sha256(os.path.join(out1, '%s.jsonl' % s))
                  for s in ('train', 'val', 'test')}
            out2, _ = construir_todo(tmp, fa=fa, ee=ee)
            h2 = {s: sha256(os.path.join(out2, '%s.jsonl' % s))
                  for s in ('train', 'val', 'test')}
            self.assertEqual(h1, h2)


if __name__ == '__main__':
    unittest.main()
