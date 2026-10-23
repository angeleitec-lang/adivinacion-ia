# -*- coding: utf-8 -*-
"""Tests adversos de armar_dataset_v1e (T141). Solo unittest, casos sintéticos."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import auditoria_v1d as aud  # noqa: E402
import armar_dataset_v1e as v1e  # noqa: E402

BASE_PROMPT = (
    'Pregunta del consultante: "Quiero una lectura detallada sobre mi situación sentimental '
    'actual y las perspectivas que se abren en los proximos meses, teniendo en cuenta lo que '
    'siento por esta persona y lo que ella podria sentir por mi, con consejo practico."'
)


def fila(split, idx, idn, bloque, human, gpt, calculos=None):
    conv = [{'from': 'system', 'value': 'S'},
            {'from': 'human', 'value': human},
            {'from': 'gpt', 'value': gpt}]
    raw = {'conversations': conv, 'id': idn, 'bloque': bloque,
           'calculos': calculos, 'generador': 'sintetico'}
    return {'split': split, 'idx': idx, 'sid': '%s#%d id=%s' % (split, idx, idn),
            'id': idn, 'bloque': bloque,
            'familiar': aud.FAMILIA_POR_BLOQUE.get(bloque, 'otros'),
            'calculos': calculos, 'humano': human, 'respuesta': gpt, 'raw': raw}


def variante(prompt, palabra):
    return prompt.replace('sentimental', palabra)


class TestPaso1FueraAlcance(unittest.TestCase):
    def test_retira_todo_el_bloque(self):
        filas = [fila('train', 0, 1, 'tarot_1', BASE_PROMPT, 'a'),
                 fila('train', 1, 2, 'fuera_alcance', 'x', 'y'),
                 fila('val', 0, 3, 'fuera_alcance', 'x', 'y'),
                 fila('test', 0, 4, 'numerologia', BASE_PROMPT, 'b')]
        nuevas, reg = v1e.paso1_fuera_alcance(filas)
        self.assertEqual(len(nuevas), 2)
        self.assertEqual({f['sid'] for f in nuevas}, {'train#0 id=1', 'test#0 id=4'})
        self.assertEqual(len(reg), 2)
        self.assertTrue(all(r['accion'] == 'retirada' for r in reg))

    def test_sin_bloque_no_retira_nada(self):
        filas = [fila('train', 0, 1, 'tarot_1', BASE_PROMPT, 'a')]
        nuevas, reg = v1e.paso1_fuera_alcance(filas)
        self.assertEqual(len(nuevas), 1)
        self.assertEqual(reg, [])


class TestPaso2Fugas(unittest.TestCase):
    def test_fuga_prompt_retira_solo_el_lado_train(self):
        filas = [fila('train', 0, 1, 'tarot_3', BASE_PROMPT, 'resp train'),
                 fila('val', 0, 2, 'tarot_3', variante(BASE_PROMPT, 'sentimental'), 'resp val'),
                 fila('test', 0, 3, 'tarot_1', 'Otra pregunta totalmente distinta sobre el trabajo y el dinero que entra y sale este mes largo', 'resp test')]
        nuevas, reg = v1e.paso2_fugas(filas)
        self.assertNotIn('train#0 id=1', {f['sid'] for f in nuevas})
        self.assertIn('val#0 id=2', {f['sid'] for f in nuevas})
        self.assertIn('test#0 id=3', {f['sid'] for f in nuevas})
        self.assertEqual(len(reg), 1)
        self.assertIn('fuga_prompt', reg[0]['motivo'])

    def test_fuga_respuesta_retira_train(self):
        resp_comun = ('Esta lectura muestra que las cartas indican un cambio importante en tu vida '
                     'afectiva durante las proximas semanas con mucha prudencia y calma')
        filas = [fila('train', 0, 1, 'tarot_1', 'Pregunta A distinta sobre el amor y el desamor que vivo', resp_comun),
                 fila('test', 0, 2, 'tarot_1', 'Pregunta B muy diferente sobre estudios y oposiciones este ano', resp_comun)]
        nuevas, reg = v1e.paso2_fugas(filas)
        self.assertNotIn('train#0 id=1', {f['sid'] for f in nuevas})
        self.assertIn('test#0 id=2', {f['sid'] for f in nuevas})
        self.assertIn('fuga_respuesta', reg[0]['motivo'])

    def test_par_val_test_no_se_toca(self):
        filas = [fila('val', 0, 1, 'tarot_1', BASE_PROMPT, 'a'),
                fila('test', 0, 2, 'tarot_1', variante(BASE_PROMPT, 'sentimental'), 'b')]
        nuevas, reg = v1e.paso2_fugas(filas)
        self.assertEqual(len(nuevas), 2)
        self.assertEqual(reg, [])


class TestPaso3Dedupe(unittest.TestCase):
    def test_conserva_la_sin_bandera_id_menor(self):
        filas = [
            fila('train', 0, 10, 'tarot_1', BASE_PROMPT, 'respuesta uno distinta'),
            fila('train', 1, 11, 'tarot_1', BASE_PROMPT, 'respuesta dos distinta'),
            fila('train', 2, 12, 'tarot_1', BASE_PROMPT, 'respuesta tres distinta'),
        ]
        flags = {'train#1 id=11': {'signo_no_calculado'}}
        nuevas, reg = v1e.paso3_dedupe_prompts(filas, flags)
        self.assertEqual([f['id'] for f in nuevas], [10])
        self.assertEqual(len(reg), 2)

    def test_todas_limpias_conserva_id_menor(self):
        filas = [
            fila('train', 0, 30, 'tarot_1', BASE_PROMPT, 'respuesta x distinta'),
            fila('train', 1, 20, 'tarot_1', BASE_PROMPT, 'respuesta y distinta'),
        ]
        nuevas, reg = v1e.paso3_dedupe_prompts(filas, {})
        self.assertEqual([f['id'] for f in nuevas], [20])

    def test_misma_respuesta_no_es_dedupe(self):
        filas = [fila('train', 0, 1, 'tarot_1', BASE_PROMPT, 'igual'),
                fila('train', 1, 2, 'tarot_1', BASE_PROMPT, 'igual')]
        nuevas, reg = v1e.paso3_dedupe_prompts(filas, {})
        self.assertEqual(len(nuevas), 2)
        self.assertEqual(reg, [])

    def test_val_no_se_dedupe(self):
        filas = [fila('val', 0, 1, 'tarot_1', BASE_PROMPT, 'a'),
                fila('val', 1, 2, 'tarot_1', BASE_PROMPT, 'b')]
        nuevas, reg = v1e.paso3_dedupe_prompts(filas, {})
        self.assertEqual(len(nuevas), 2)
        self.assertEqual(reg, [])


class TestPaso4Alucinaciones(unittest.TestCase):
    def test_retira_categorias_de_expurgo_en_todos_los_splits(self):
        filas = [fila('train', 0, 1, 'astro_natal', BASE_PROMPT, 'a'),
                fila('val', 0, 2, 'astro_natal', BASE_PROMPT + ' x', 'b'),
                fila('test', 0, 3, 'numerologia', BASE_PROMPT + ' y', 'c')]
        flags = {'train#0 id=1': {'signo_no_calculado'},
                 'val#0 id=2': {'numero_numerologia_incorrecto'},
                 'test#0 id=3': {'aspecto_no_calculado'}}
        nuevas, reg, cons = v1e.paso4_alucinaciones(filas, flags)
        self.assertEqual(nuevas, [])
        self.assertEqual(len(reg), 3)
        self.assertEqual(cons, [])

    def test_conserva_casa_y_fase_listadas(self):
        filas = [fila('train', 0, 1, 'astro_natal', BASE_PROMPT, 'a'),
                fila('train', 1, 2, 'biorritmos', BASE_PROMPT + ' z', 'b')]
        flags = {'train#0 id=1': {'casa_no_calculada'},
                 'train#1 id=2': {'fase_biorritmo_incorrecta'}}
        nuevas, reg, cons = v1e.paso4_alucinaciones(filas, flags)
        self.assertEqual(len(nuevas), 2)
        self.assertEqual(reg, [])
        self.assertEqual(len(cons), 2)
        self.assertEqual({c['categoria'] for c in cons},
                         {'casa_no_calculada', 'fase_biorritmo_incorrecta'})

    def test_bandera_no_expurgable_no_retira(self):
        filas = [fila('train', 0, 1, 'astro_natal', BASE_PROMPT, 'a')]
        flags = {'train#0 id=1': {'porcentaje_inventado'}}
        nuevas, reg, cons = v1e.paso4_alucinaciones(filas, flags)
        self.assertEqual(len(nuevas), 1)
        self.assertEqual(reg, [])


class TestPaso5Multiturno(unittest.TestCase):
    def test_reetiqueta_sin_borrar(self):
        filas = [fila('train', 0, 1, 'multiturno', BASE_PROMPT, 'a'),
                fila('val', 0, 2, 'tarot_1', BASE_PROMPT, 'b')]
        nuevas, reg = v1e.paso5_multiturno(filas)
        self.assertEqual(len(nuevas), 2)
        mt = [f for f in nuevas if f['id'] == 1][0]
        self.assertEqual(mt['bloque'], 'consulta_con_contexto')
        self.assertEqual(mt['raw']['bloque'], 'consulta_con_contexto')
        self.assertEqual(mt['raw']['bloque_origen'], 'multiturno')
        self.assertEqual(mt['id'], 1)
        no_mt = [f for f in nuevas if f['id'] == 2][0]
        self.assertEqual(no_mt['bloque'], 'tarot_1')
        self.assertNotIn('bloque_origen', no_mt['raw'])
        self.assertEqual(len(reg), 1)


class TestPaso6Numerologia(unittest.TestCase):
    def _base(self):
        textos = [
            'Que me dice el numero de camino de vida calculado de mi fecha de nacimiento sobre mi mision en la tierra?',
            'Como influye mi numero de expresion en la forma en que me comunico con los demas cada dia?',
            'Que significa el numero de alma que resulta de mis vocales y como se refleja en mis deseos profundos?',
            'Quiero entender mi ano personal segun la numerologia pitagorica y que oportunidades trae este ciclo?',
            'Explorame el numero de personalidad que forman las consonantes de mi nombre completo y sus rasgos?',
            'Que relacion hay entre mi numero de madurez y las etapas de mi vida segun la numerologia clasica?',
        ]
        train = [fila('train', i, 100 + i, 'numerologia', textos[i], 'resp %d' % i)
                 for i in range(6)]
        val = [fila('val', 0, 200, 'numerologia',
                   'Consulta numerologica sobre mi vibracion numerica y el significado oculto '
                   'de los numeros que veo repetidos ultimamente', 'resp val')]
        return train + val

    def test_mueve_a_test_y_val(self):
        filas = self._base()
        nuevas, reg = v1e.paso6_numerologia(filas, n_test=2, n_val=1)
        splits = {f['sid']: f['split'] for f in nuevas}
        movidos = [r for r in reg if r['accion'] in ('movido_test', 'movido_val')]
        self.assertEqual(len(movidos), 3)
        self.assertEqual(splits['train#0 id=100'], 'test')
        self.assertEqual(splits['train#1 id=101'], 'test')
        self.assertEqual(splits['train#2 id=102'], 'val')
        self.assertEqual(splits['train#3 id=103'], 'train')

    def test_no_mueve_si_fuga_con_val(self):
        filas = self._base()
        # train#0 copia el prompt de val -> prohibido moverlo
        filas[0]['humano'] = filas[-1]['humano']
        nuevas, reg = v1e.paso6_numerologia(filas, n_test=2, n_val=1)
        splits = {f['sid']: f['split'] for f in nuevas}
        self.assertEqual(splits['train#0 id=100'], 'train')
        movidos = {r['sid'] for r in reg if r['accion'] in ('movido_test', 'movido_val')}
        self.assertNotIn('train#0 id=100', movidos)

    def test_sin_candidatos_no_mueve(self):
        filas = [fila('train', 0, 1, 'tarot_1', BASE_PROMPT, 'a')]
        nuevas, reg = v1e.paso6_numerologia(filas, n_test=2, n_val=1)
        self.assertEqual(len(nuevas), 1)
        self.assertEqual([r for r in reg if r['accion'] in ('movido_test', 'movido_val')], [])


class TestPaso1bIntegracion(unittest.TestCase):
    def test_reparte_noventa_cinco_cinco(self):
        with tempfile.TemporaryDirectory() as td:
            ruta = os.path.join(td, 'fuera_alcance_v2.jsonl')
            with open(ruta, 'w', encoding='utf-8') as fh:
                for i in range(20):
                    d = {'conversations': [{'from': 'human', 'value': 'pregunta v2 %d' % i},
                                          {'from': 'gpt', 'value': 'no puedo hacer eso'}],
                         'id': 900 + i, 'bloque': 'fuera_alcance'}
                    fh.write(json.dumps(d, ensure_ascii=False) + '\n')
            filas, reg = v1e.paso1b_fuera_alcance_v2([], ruta, semilla=141)
            self.assertEqual(len(filas), 20)
            from collections import Counter
            c = Counter(f['split'] for f in filas)
            self.assertEqual(c['train'], 18)
            self.assertEqual(c['val'], 1)
            self.assertEqual(c['test'], 1)
            self.assertTrue(all(f['bloque'] == 'fuera_alcance' for f in filas))


class TestConstruirEndToEnd(unittest.TestCase):
    def test_ciclo_completo_en_directorio_temporal(self):
        with tempfile.TemporaryDirectory() as td:
            v1d = os.path.join(td, 'v1d')
            out = os.path.join(td, 'v1e')
            os.makedirs(v1d)
            filas_train = [
                fila('train', 0, 1, 'tarot_1', BASE_PROMPT, 'respuesta uno'),
                fila('train', 1, 2, 'tarot_1', BASE_PROMPT, 'respuesta dos'),
                fila('train', 2, 3, 'fuera_alcance', 'x', 'y'),
                fila('train', 3, 4, 'multiturno', 'hola de bloque multiturno largo para pasar filtros', 'adios'),
                fila('train', 4, 5, 'numerologia', 'Que me dice el numero de camino de vida calculado de mi fecha sobre mi mision en la tierra?', 'r5'),
                fila('train', 5, 6, 'numerologia', 'Como influye mi numero de expresion en la forma en que hablo con los demas cada dia?', 'r6'),
                fila('train', 6, 7, 'numerologia', 'Que significa el numero de alma que resulta de mis vocales y mis deseos profundos?', 'r7'),
            ]
            filas_val = [fila('val', 0, 8, 'tarot_3', 'Pregunta val unica sobre el tarot y las cartas esta semana', 'rv')]
            filas_test = [fila('test', 0, 9, 'fuera_alcance', 'x', 'y')]
            for split, fs in (('train', filas_train), ('val', filas_val), ('test', filas_test)):
                with open(os.path.join(v1d, split + '.jsonl'), 'w', encoding='utf-8') as fh:
                    for f in fs:
                        fh.write(json.dumps(f['raw'], ensure_ascii=False) + '\n')
            resumen = v1e.construir(v1d, out, fuera_v2=None, semilla=141,
                                   n_test_num=2, n_val_num=1)
            self.assertTrue(os.path.exists(os.path.join(out, 'train.jsonl')))
            self.assertTrue(os.path.exists(os.path.join(out, '_cambios', 'paso1_fuera_alcance.jsonl')))
            self.assertTrue(os.path.exists(os.path.join(out, 'resumen.json')))
            with open(os.path.join(out, 'train.jsonl'), encoding='utf-8') as fh:
                crudos = [json.loads(l) for l in fh if l.strip()]
            ids_train = {d['id'] for d in crudos}
            self.assertNotIn(3, ids_train)  # fuera_alcance fuera
            self.assertIn(1, ids_train)     # dedupe conserva id menor
            self.assertNotIn(2, ids_train)  # duplicada fuera
            mt = [d for d in crudos if d['id'] == 4][0]
            self.assertEqual(mt['bloque'], 'consulta_con_contexto')
            self.assertEqual(mt['bloque_origen'], 'multiturno')
            sp = resumen['despues']['por_split']
            self.assertEqual(sp['train'], 2)  # id1 + id4 (multiturno reetiquetado)
            self.assertEqual(sp['val'], 2)    # id8 + 1 movido
            self.assertEqual(sp['test'], 2)   # 2 movidos (el fuera_alcance original se fue en paso 1)
            bloques = {d['id']: d['bloque'] for d in crudos}
            self.assertNotIn('fuera_alcance', set(bloques.values()))


if __name__ == '__main__':
    unittest.main()
