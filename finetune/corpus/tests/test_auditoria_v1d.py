# -*- coding: utf-8 -*-
"""Tests adversos de auditoria_v1d (T135). Solo unittest, casos sintéticos."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import auditoria_v1d as aud  # noqa: E402

KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'kb')


def setUpModule():
    aud.build_decks(KB_DIR)


def fila(bloque, human, gpt, calculos=None, sid=None, split='train', idx=0, idn=1):
    conv = [{'from': 'system', 'value': 'S'},
            {'from': 'human', 'value': human},
            {'from': 'gpt', 'value': gpt}]
    return {'split': split, 'idx': idx, 'sid': sid or '%s:%d' % (split, idx),
            'id': idn, 'bloque': bloque, 'calculos': calculos,
            'humano': human, 'respuesta': gpt, 'conversations': conv,
            'familiar': aud.FAMILIA_POR_BLOQUE.get(bloque, 'otros')}


class TestTaridas(unittest.TestCase):
    def test_carta_inexistente_espanola(self):
        f = fila('espanola_3', 'Tirada de tres cartas de la baraja española.\nOros: Rey de Oros\nCopas: Siete de Copas\nEspadas: Once de Espadas', 'x')
        res = aud.check_tiradas([f])
        self.assertEqual(res['total'], 1)
        self.assertIn('Once de Espadas', res['ejemplos'][0]['detalle'])

    def test_mezcla_tarot_en_espanola(self):
        f = fila('espanola_1', 'Tirada de una carta de la baraja española.\n- naipe: La Luna (al derecho)', 'x')
        res = aud.check_tiradas([f])
        self.assertEqual(res['total'], 1)

    def test_repetida(self):
        f = fila('tarot_3', 'Carta 1: El Loco (al derecho)\nCarta 2: El Loco (invertida)', 'x')
        res = aud.check_tiradas([f])
        self.assertEqual(res['total'], 1)

    def test_limpia_no_flag(self):
        f = fila('tarot_3', 'pasado: As de Bastos (al derecho)\npresente: Reina de Copas (invertida)\nfuturo: Siete de Espadas (derecho)', 'x')
        res = aud.check_tiradas([f])
        self.assertEqual(res['total'], 0)

    def test_referencia_sin_tirada(self):
        f = fila('tarot_1', 'Carta: El Sol (al derecho)', '- As de Oros (al derecho): brillo raro. Palabras clave: x')
        res = aud.check_tiradas([f])
        self.assertEqual(res['total'], 1)
        self.assertIn('As de Oros', res['ejemplos'][0]['detalle'])


class TestCoherenciaCalculos(unittest.TestCase):
    CALC_NATAL = {'carta_natal': {
        'planetas': {
            'Sol': {'signo': 'Virgo', 'casa': 10},
            'Luna': {'signo': 'Piscis', 'casa': 4},
            'Ascendente': {'signo': 'Géminis'},
        },
        'aspectos': ['Mercurio conjunción Júpiter'],
    }}

    PROMPT_ASTRO = ('Datos de nacimiento: 1990-01-01, 10:00.\n'
                    'Posiciones:\n- Sol: Virgo 15°00\' (casa 10)\n- Luna: Piscis 3°00\' (casa 4)\n'
                    '- Ascendente: Géminis 1°00\'\nAspectos: Mercurio conjunción Júpiter')

    def test_planeta_signo_inventado(self):
        f = fila('astro_natal', self.PROMPT_ASTRO, 'Venus en Escorpio te pide soltar el control profundo.', self.CALC_NATAL)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)

    def test_planeta_no_en_prompt(self):
        f = fila('astro_natal', self.PROMPT_ASTRO, 'Saturno en Capricornio marca tu madurez.', self.CALC_NATAL)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)

    def test_casa_inventada(self):
        f = fila('astro_natal', self.PROMPT_ASTRO, 'Mercurio rige la casa 9 de tu carta.', self.CALC_NATAL)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)

    def test_aspecto_inventado(self):
        f = fila('astro_natal', self.PROMPT_ASTRO, 'Tu Sol forma una oposición con Plutón que transforma.', self.CALC_NATAL)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)

    def test_cadena_mismo_sujeto(self):
        calc = {'carta_natal': {'planetas': [], 'aspectos': [
            {'a': 'Luna', 'b': 'Saturno', 'aspecto': 'sextil'},
            {'a': 'Luna', 'b': 'Júpiter', 'aspecto': 'cuadratura'}]}}
        f = fila('astro_natal', 'x', 'La Luna en sextil a Saturno y en cuadratura con Júpiter exige ritmo.', calc)
        self.assertEqual(aud.check_coherencia_calculos([f])['total'], 0)

    def test_cadena_nuevo_sujeto(self):
        calc = {'carta_natal': {'planetas': [], 'aspectos': [
            {'a': 'Luna', 'b': 'Saturno', 'aspecto': 'oposicion'},
            {'a': 'Mercurio', 'b': 'Urano', 'aspecto': 'cuadratura'}]}}
        f = fila('astro_natal', 'Aspectos: Luna oposicion a Saturno; Mercurio cuadratura con Urano.',
                 'La Luna en oposicion a Saturno y Mercurio en cuadratura con Urano marcan el tono.', calc)
        self.assertEqual(aud.check_coherencia_calculos([f])['total'], 0)

    def test_par_post_sujeto_omitido(self):
        calc = {'carta_a': {'planetas': [], 'aspectos': [
            {'a': 'Venus', 'b': 'Plutón', 'aspecto': 'oposicion'}]},
            'carta_b': {'planetas': [], 'aspectos': []}}
        f = fila('sinastria', 'Aspectos: Venus oposicion a Pluton de A.',
                 'La cuadratura de Venus a Urano de B desborda lo calculado.', calc)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)
        self.assertEqual(res['ejemplos'][0]['categoria'], 'aspecto_no_calculado')

    def test_limpia(self):
        f = fila('astro_natal', self.PROMPT_ASTRO, 'El Sol en Virgo en casa 10 ordena tu rutina, con la conjunción de Mercurio y Júpiter.', self.CALC_NATAL)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 0)

    def test_biorritmos_porcentaje(self):
        calc = {'biorritmos': {'ciclos': {'fisico': {'valor': 0.2698, 'porcentaje': 27, 'fase': 'ascendente'},
                                          'emocional': {'valor': 0.9, 'porcentaje': 90, 'fase': 'descendente'},
                                          'intelectual': {'valor': -0.87, 'porcentaje': -87, 'fase': 'descendente'}}}}
        f = fila('biorritmos', 'Biorritmos para el 2026-10-15:\n- Físico: 27% (ascendente)', 'Tu ciclo físico está al 81% hoy.', calc)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)
        f2 = fila('biorritmos', 'x', 'Tu ciclo físico ronda el 26% y el emocional el 91%.', calc)
        res2 = aud.check_coherencia_calculos([f2])
        self.assertEqual(res2['total'], 0)

    def test_numerologia(self):
        calc = {'numerologia': {'camino_de_vida': 7, 'expresion': 7, 'expresion_es': 'La Torre',
                                'alma': 4, 'personalidad': 9, 'anio_personal': 4}}
        f = fila('numerologia', 'Camino de vida: 7', 'Tu camino de vida es el 7, y tu expresión 3 te da voz.', calc)
        res = aud.check_coherencia_calculos([f])
        self.assertEqual(res['total'], 1)
        self.assertIn('expresion', res['ejemplos'][0]['detalle'])
        f2 = fila('numerologia', 'x', 'Tu camino de vida 7 y tu año personal 4 piden calma.', calc)
        self.assertEqual(aud.check_coherencia_calculos([f2])['total'], 0)


class TestFueraAlcance(unittest.TestCase):
    def test_prompt_corrupto(self):
        f = fila('fuera_alcance', 'Consulta fuera de alcance.\nPregunta del consultante: "131 Vengo a preguntarte:"', 'No es mi alcance.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 1)

    def test_responde_tecnica_prohibida(self):
        f = fila('fuera_alcance', 'Pregunta del consultante: "¿Me lees la mano?"',
                 'En tu mano, la línea de la vida es larga y la del corazón indica amor profundo. Esta runa Kenaz ilumina tu camino.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 1)

    def test_prediccion_concreta(self):
        f = fila('fuera_alcance', 'Pregunta del consultante: "¿Qué números jugar en la lotería?"',
                 'Juega el 7, el 23 y el 45, porque las cartas lo confirman este martes.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 1)

    def test_negacion_no_cuenta(self):
        f = fila('fuera_alcance', 'Pregunta del consultante: "¿Me dices la lotería?"',
                 'No voy a decirte números ni a jugar la lotería, eso no es parte de mi alcance.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 0)

    def test_rechazo_menciona_tecnica_no_cuenta(self):
        f = fila('fuera_alcance', 'Pregunta del consultante: "¿Me lees la mano?"',
                 'Si lo que buscas es otra técnica, como la quiromancia o la lectura del café, te recomiendo acudir a un profesional.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 0)

    def test_rechazo_prediccion_no_cuenta(self):
        f = fila('fuera_alcance', 'Pregunta del consultante: "¿Voy a ganar la lotería?"',
                 'No puedo decir si vas a ganar la lotería; para tus finanzas te recomiendo acudir a un asesor.')
        res = aud.check_fuera_alcance([f])
        self.assertEqual(res['total'], 0)


class TestIdioma(unittest.TestCase):
    def test_portugues(self):
        f = fila('tarot_1', 'Carta: El Sol (al derecho)',
                 'Esta es una leitura muito importante para você, porque o momento é de mudanças grandes, não tema o futuro incierto aquí.')
        res = aud.check_idioma([f])
        self.assertEqual(res['total'], 1)

    def test_razonamiento(self):
        f = fila('tarot_1', 'x', 'Thinking Process:\n1. Analyze the card. El Sol ilumina tu camino hoy.')
        res = aud.check_idioma([f])
        self.assertEqual(res['total'], 1)

    def test_markdown(self):
        f = fila('tarot_1', 'x', 'La carta **El Sol** indica éxito.\n```\ncódigo raro\n``` y sigue la lectura normal aquí.')
        res = aud.check_idioma([f])
        self.assertEqual(res['total'], 1)

    def test_truncado(self):
        f = fila('tarot_1', 'x', 'Hoy es un día para mirar dentro de ti misma y conectar con esa energía que te sostiene en los momentos de mayor')
        res = aud.check_idioma([f])
        self.assertEqual(res['total'], 1)

    def test_tildes_ausentes(self):
        base = ('La lectura de hoy muestra que el momento es de cambio, y es necesario que tu alma encuentre calma. '
                'El camino que sigues puede darte exito y armonia si mantienes la paciencia. No es facil, pero tu '
                'energia interior puede transformar cada dia en una oportunidad real de crecimiento personal.')
        f = fila('tarot_1', 'x', base)
        res = aud.check_idioma([f])
        self.assertEqual(res['total'], 1)
        clean = base.replace('exito', 'éxito').replace('armonia', 'armonía').replace('facil', 'fácil') \
                     .replace('energia', 'energía').replace('dia', 'día')
        f2 = fila('tarot_1', 'x', clean)
        self.assertEqual(aud.check_idioma([f2])['total'], 0)


class TestSecretos(unittest.TestCase):
    def test_clave(self):
        f = fila('tarot_1', 'Carta: El Sol (al derecho)', 'Mi api_key: sk-proj-AbCdEf1234567890XYZ abcd, sigue la lectura.')
        f['humano'] = f['human'] if 'human' in f else f['humano']
        res = aud.check_secretos([f])
        self.assertEqual(res['total'], 1)

    def test_bearer(self):
        f = fila('tarot_1', 'x', 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc', 'ok')
        res = aud.check_secretos([f])
        self.assertEqual(res['total'], 1)

    def test_limpia(self):
        f = fila('tarot_1', 'x', 'El 2 es 2345678901 y la casa 9 no es un secreto, nada de claves aqui vale.', 'ok')
        res = aud.check_secretos([f])
        self.assertEqual(res['total'], 0)


class TestLimpiaTexto(unittest.TestCase):
    def test_sin_esquema(self):
        r = '## 1. situación — Cuatro de Oros\ntexto\n## 2. desafıo — El Loco\nmás\n## 3. pasado — X'
        out = aud.limpia_texto(r)
        self.assertNotIn('## 1', out)
        self.assertIn('texto', out)

    def test_no_toca_normal(self):
        r = 'El Sol ilumina tu camino hoy.'
        self.assertEqual(aud.limpia_texto(r), r.lower())


class TestFugas(unittest.TestCase):
    def _par(self):
        t = fila('tarot_1',
                 'Carta: El Loco (al derecho)\nPregunta del consultante: "¿Qué me espera en el amor hoy, considerando todo lo que hemos hablado antes y lo mucho que me ilusiona pensar en el futuro juntos?"',
                 'El Loco te invita a dar un salto de fe en el amor, con espontaneidad total y sin miedo a equivocarte mientras caminas ligera hacia una nueva etapa plena.',
                 split='train', idx=0, idn=10)
        v = fila('tarot_1',
                 'Carta: El Loco (al derecho)\nPregunta del consultante: "¿Qué me espera en el amor hoy, considerando todo lo que hemos hablado antes y lo mucho que me ilusiona pensar en el futuro juntos?"',
                 'El Loco te invita a dar un salto de fe en el amor, con espontaneidad total y sin miedo a equivocarte mientras caminas ligera hacia una nueva etapa plena.',
                 split='test', idx=3, idn=11)
        return [t, v]

    def test_fuga_prompts(self):
        fs = self._par()
        res = aud.check_fugas(fs, semilla=135)
        self.assertGreaterEqual(res['fugas_prompt']['total'], 1)
        self.assertEqual(res['fugas_respuesta']['total'], 1)

    def test_duplicados(self):
        fs = self._par()
        fs.append(fila('tarot_1', fs[0]['humano'], fs[0]['respuesta'], split='train', idx=9, idn=12))
        res = aud.check_duplicados(fs, semilla=135)
        self.assertGreaterEqual(res['duplicados_exactos']['total'], 2)
        self.assertGreaterEqual(res['respuesta_en_varias_filas']['total'], 1)


class TestLongitudes(unittest.TestCase):
    def test_outliers(self):
        fs = []
        for i in range(12):
            fs.append(fila('tarot_3', 'x' * 100, ('palabra ' * 400)[:4000], split='train', idx=i, idn=i))
        fs.append(fila('tarot_3', 'x' * 100, 'corta.', split='train', idx=99, idn=99))
        res = aud.check_longitudes(fs)
        self.assertTrue(any(e['categoria'] == 'gpt_corta' for e in res['ejemplos']))

    def test_distribucion(self):
        fs = [fila('tarot_1', 'x', 'lectura normal de la carta del sol para hoy.', split='train', idx=i, idn=i) for i in range(6)]
        res = aud.check_longitudes(fs)
        self.assertIn('tarot', res['distribucion'])


class TestMuestreo(unittest.TestCase):
    def test_reproducible(self):
        filas = [{'split': 'train', 'idx': i, 'familiar': 'tarot', 'id': i} for i in range(1000)]
        a = aud.muestreo_estratificado(filas, semilla=135, tam_por_celda=50)
        b = aud.muestreo_estratificado(filas, semilla=135, tam_por_celda=50)
        self.assertEqual(a['tarot|train'], b['tarot|train'])
        self.assertLessEqual(len(a['tarot|train']), 50)
        c = aud.muestreo_estratificado(filas, semilla=136, tam_por_celda=50)
        self.assertNotEqual(a['tarot|train'], c['tarot|train'])


class TestEnd2End(unittest.TestCase):
    def test_todo_ok(self):
        fs = [fila('tarot_1',
                   'Carta: El Sol (al derecho)\nPregunta del consultante: "¿Cómo va mi día?"',
                   'El Sol al derecho ilumina tu día con energía clara y positiva; es un buen momento para actuar con confianza y mostrar lo mejor de ti misma.')]
        informe = aud.auditar(fs, semilla=135)
        for k in ['fugas_prompt', 'fugas_respuesta', 'duplicados_exactos', 'tiradas_invalidas',
                  'datos_incoherentes', 'idioma_anomalo', 'fuera_alcance_ndefectos',
                  'secretos', 'longitudes_anomalas']:
            self.assertIn(k, informe)

    def test_resumen_formatea(self):
        fs = [fila('fuera_alcance', 'Pregunta del consultante: "99 Vengo a preguntarte:"', 'No es mi alcance.')]
        informe = aud.auditar(fs, semilla=135)
        txt = aud.resumen_md(informe)
        self.assertIn('fuera_alcance_ndefectos', txt)


if __name__ == '__main__':
    unittest.main()
