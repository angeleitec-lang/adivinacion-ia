"""Tests del validador de datos sintéticos (track T4)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import validate_synthetic as vs


TIRADA3 = (
    "Tirada de tres cartas (pasado, presente y futuro).\n\n"
    "- pasado: El Loco (al derecho)\n"
    "- presente: La Torre (invertida)\n"
    "- futuro: El Sol (al derecho)\n"
    "Contexto: amor."
)

CRUZ_CELTA = (
    "Tirada de la Cruz Celta.\n\n"
    "- situación: El Mago (al derecho)\n"
    "- obstáculo: La Luna (invertida)\n"
    "- pasado: El Carro (al derecho)\n"
    "- futuro: La Justicia (al derecho)\n"
    "- corona: El Sol (al derecho)\n"
    "- base: El Diablo (invertido)\n"
    "- yo: La Fuerza (al derecho)\n"
    "- entorno: El Ermitaño (al derecho)\n"
    "- esperanzas: La Templanza (al derecho)\n"
    "- resultado: El Mundo (al derecho)\n"
    "Contexto: trabajo."
)

DOS_CARTAS = (
    "Tirada de dos cartas.\n\n"
    "Carta 1: La Emperatriz (al derecho).\n"
    "Carta 2: El Ermitaño (invertida).\n"
    "Contexto: dinero."
)

ASTRO = (
    "Carta astral.\n\n"
    "- Sol: Aries 12°30' (casa 7)\n"
    "- Luna: Cáncer 5°12' (casa 10)\n"
    "- Ascendente: Virgo 20°01'\n"
    "Contexto: amor."
)

NUMEROLOGIA = (
    "Lectura numerológica.\n\n"
    "- Camino de vida: 7\n"
    "- Alma (vocales): 3\n"
    "- Personalidad: 5\n"
    "Contexto: trabajo."
)


class TestNorm(unittest.TestCase):
    def test_quita_tildes_y_mayusculas(self):
        self.assertEqual(vs.norm("La Torre INVERTIDA"), "la torre invertida")
        self.assertEqual(vs.norm("Cáncer"), "cancer")

    def test_quita_signos(self):
        self.assertEqual(vs.norm("¡Qué energía! 12°30'"), "que energia 12 30")


class TestExtraerCartas(unittest.TestCase):
    def test_tirada_tres_cartas(self):
        cartas = vs.extraer_cartas(TIRADA3)
        self.assertEqual(len(cartas), 3)
        nombres = [n for n, _ in cartas]
        self.assertIn("El Loco", nombres)
        self.assertIn("La Torre", nombres)
        self.assertIn("El Sol", nombres)
        orient = dict((n, o) for n, o in cartas)
        self.assertEqual(orient["La Torre"], "invertida")
        self.assertEqual(orient["El Loco"], "derecho")

    def test_cruz_celta_diez_cartas(self):
        cartas = vs.extraer_cartas(CRUZ_CELTA)
        self.assertEqual(len(cartas), 10)
        self.assertEqual(dict(cartas)["El Diablo"], "invertida")

    def test_carta_uno_dos(self):
        cartas = vs.extraer_cartas(DOS_CARTAS)
        self.assertEqual(len(cartas), 2)
        self.assertEqual(dict(cartas)["La Emperatriz"], "derecho")
        self.assertEqual(dict(cartas)["El Ermitaño"], "invertida")

    def test_una_carta(self):
        prompt = 'Carta: La Torre (invertida).\nContexto: amor.'
        cartas = vs.extraer_cartas(prompt)
        self.assertEqual(cartas, [("La Torre", "invertida")])

    def test_sin_cartas(self):
        self.assertEqual(vs.extraer_cartas("Háblame del amor en general."), [])


class TestGrounding(unittest.TestCase):
    def test_tres_cartas_todas_mencionadas(self):
        respuesta = ("El Loco abre el camino con ingenuidad, La Torre marca el quiebre "
                     "necesario y El Sol ilumina el final del recorrido.")
        self.assertTrue(vs.grounding(TIRADA3, respuesta))

    def test_tres_cartas_una_ausente(self):
        respuesta = ("El Loco abre el camino con ingenuidad y La Torre marca el quiebre "
                     "necesario en tu vida.")
        self.assertFalse(vs.grounding(TIRADA3, respuesta))

    def test_cruz_celta_con_una_ausente(self):
        respuesta = ("El Mago inicia, la Luna oculta, el Carro avanza, la Justicia ordena, "
                     "el Sol corona, el Diablo ata, la Fuerza sostiene, el Ermitaño guía y "
                     "la Templanza equilibra este momento.")
        self.assertFalse(vs.grounding(CRUZ_CELTA, respuesta))

    def test_cruz_celta_completa(self):
        respuesta = ("El Mago inicia, la Luna oculta, el Carro avanza, la Justicia ordena, "
                     "el Sol corona, el Diablo ata, la Fuerza sostiene, el Ermitaño guía, "
                     "la Templanza equilibra y El Mundo cierra el ciclo.")
        self.assertTrue(vs.grounding(CRUZ_CELTA, respuesta))

    def test_carta_uno_dos_grounding(self):
        respuesta = ("La Emperatriz aporta fertilidad y el Ermitaño pide introspección "
                     "en tus finanzas.")
        self.assertTrue(vs.grounding(DOS_CARTAS, respuesta))
        self.assertFalse(vs.grounding(DOS_CARTAS, "Solo la Emperatriz habla de abundancia aquí."))

    def test_prompt_sin_cartas_devuelve_true(self):
        self.assertTrue(vs.grounding("Háblame del amor en general.", "El amor es complejo."))

    def test_tildes_ignoradas(self):
        prompt = "Carta: La Torre (invertida).\nContexto: amor."
        respuesta = "la torre anuncia un derrumbe necesario en tu vida sentimental."
        self.assertTrue(vs.grounding(prompt, respuesta))

    def test_articulo_inicial_puede_faltar(self):
        prompt = "Carta: La Torre (invertida).\nContexto: amor."
        respuesta = "Torre invertida: toca soltar lo que se sostiene con grietas."
        self.assertTrue(vs.grounding(prompt, respuesta))

    def test_numerologia_dos_tercios(self):
        respuesta = "El 7 marca tu camino de vida y el 3 tu alma creativa."
        self.assertTrue(vs.grounding(NUMEROLOGIA, respuesta))
        self.assertFalse(vs.grounding(NUMEROLOGIA, "Solo el 7 rige tu sendero vital."))

    def test_astrologia_dos_tercios(self):
        respuesta = "Aries impulsa tu Sol y Cáncer moja tus emociones de Virgo ascendente."
        self.assertTrue(vs.grounding(ASTRO, respuesta))
        self.assertFalse(vs.grounding(ASTRO, "Aries marca el ritmo de esta consulta."))


class TestOrientacion(unittest.TestCase):
    def test_invertida_reconocida(self):
        prompt = "Carta: La Torre (invertida).\nContexto: amor."
        respuesta = "La Torre aparece invertida y bloquea tu progreso sentimental."
        self.assertTrue(vs.orientacion_ok(prompt, respuesta))

    def test_invertida_sin_mencion(self):
        prompt = "Carta: La Torre (invertida).\nContexto: amor."
        respuesta = "La Torre anuncia cambios profundos y necesarios en tu vida."
        self.assertFalse(vs.orientacion_ok(prompt, respuesta))

    def test_invertida_con_al_reves(self):
        prompt = "Carta: La Torre (invertida).\nContexto: amor."
        respuesta = "La Torre, al revés, te pide soltar lo que se agrieta."
        self.assertTrue(vs.orientacion_ok(prompt, respuesta))

    def test_al_derecho_llamada_invertida(self):
        prompt = "Carta: El Sol (al derecho).\nContexto: trabajo."
        respuesta = "El Sol invertido oscurece tu camino profesional."
        self.assertFalse(vs.orientacion_ok(prompt, respuesta))

    def test_al_derecho_sin_afirmar_inversion(self):
        prompt = "Carta: El Sol (al derecho).\nContexto: trabajo."
        respuesta = "El Sol al derecho ilumina tu etapa profesional con claridad."
        self.assertTrue(vs.orientacion_ok(prompt, respuesta))

    def test_mixta_orientaciones(self):
        respuesta = ("El Sol brilla con fuerza en tu presente, mientras La Torre "
                     "invertida anuncia el quiebre necesario.")
        self.assertTrue(vs.orientacion_ok(TIRADA3, respuesta))

    def test_prompt_sin_cartas(self):
        self.assertTrue(vs.orientacion_ok("Háblame del amor.", "El amor es complejo."))


BASE_LARGA = (
    "La Torre invertida anuncia un derrumbe necesario en tu vida sentimental. "
    "Durante semanas has sostenido una estructura agrietada por silencios, dudas y "
    "promesas que nadie terminó de cumplir. Esa construcción temblaba desde adentro "
    "y ahora toca mirar los escombros sin miedo, porque cada bloque caído deja "
    "ver el cielo que tapaba. No es un castigo, es una liberación tardía. "
) * 2

CASI_IGUAL = BASE_LARGA + " Consejo final: respira hondo."

DISTINTA_MISMA_CARTA = (
    "El Sol ilumina esta tirada con una energía de madurez y claridad mental. "
    "Lejos de los fuegos impulsivos de otras cartas, aquí manda la serenidad de "
    "quien ya atravesó la crisis y aprendió a nombrar lo que siente. En el amor "
    "propuesto, conviene hablar pronto y sin dramatismos, porque la honestidad "
    "abre puertas que la timidez cerró durante meses. "
) * 2


class TestCasiDuplicados(unittest.TestCase):
    def test_shingles_estables(self):
        s1 = vs.shingles("texto de prueba con varias palabras normalizadas")
        s2 = vs.shingles("TEXTO de prueba, con varias palabras normalizadas!")
        self.assertEqual(s1, s2)
        self.assertTrue(all(isinstance(x, int) for x in s1))

    def test_minhash_determinista(self):
        sh = vs.shingles(BASE_LARGA)
        self.assertEqual(vs.minhash(sh), vs.minhash(sh))
        self.assertEqual(len(vs.minhash(sh)), 64)

    def test_casi_igual_es_duplicado(self):
        idx = vs.IndiceCasiDuplicados()
        idx.add("a", BASE_LARGA)
        self.assertTrue(idx.buscar(CASI_IGUAL))

    def test_distintas_sobre_misma_carta_no_duplicado(self):
        idx = vs.IndiceCasiDuplicados()
        idx.add("a", BASE_LARGA)
        self.assertFalse(idx.buscar(DISTINTA_MISMA_CARTA))

    def test_texto_corto_no_revienta(self):
        idx = vs.IndiceCasiDuplicados()
        idx.add("c", "hola")
        self.assertTrue(idx.buscar("hola"))
        self.assertFalse(idx.buscar("adios"))
        self.assertFalse(idx.buscar(""))

    def test_determinismo_entre_indices(self):
        i1 = vs.IndiceCasiDuplicados()
        i2 = vs.IndiceCasiDuplicados()
        i1.add("x", BASE_LARGA)
        i2.add("y", BASE_LARGA)
        self.assertEqual(i1.buscar(CASI_IGUAL), i2.buscar(CASI_IGUAL))
        self.assertTrue(i1.buscar(CASI_IGUAL))


import argparse


def _args(**kw):
    d = {"min_chars": 40, "max_chars": 12000, "max_repetition": 0.12}
    d.update(kw)
    return argparse.Namespace(**d)


def _fila(system="", human="", gpt="La Torre invertida anuncia un derrumbe necesario en tu vida sentimental."):
    conv = []
    if system:
        conv.append({"from": "system", "value": system})
    if human:
        conv.append({"from": "human", "value": human})
    conv.append({"from": "gpt", "value": gpt})
    return {"conversations": conv}


class TestPromptSinTildes(unittest.TestCase):
    def test_system_antiguo_rechazado(self):
        row = _fila(
            system="Eres una tarotista, astrologa y numerologa profesional con empatia.",
            human="Tirada de una carta.\n\nCarta: La Torre (invertida).",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "prompt_sin_tildes")

    def test_human_antiguo_rechazado(self):
        row = _fila(
            system="Eres una tarotista con experiencia.",
            human='Carta: La Torre (invertida).\nPregunta: "Que energia hay hoy?"',
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "prompt_sin_tildes")

    def test_fila_nueva_con_tildes_pasa(self):
        row = _fila(
            system="Eres una tarotista, astróloga y numeróloga profesional con empatía.",
            human=(
                "Tirada de una carta.\n\nCarta: La Torre (invertida).\nContexto: amor.\n"
                'Pregunta del consultante: "¿Qué energía hay en mi vida sentimental ahora mismo?"'
            ),
        )
        ok, why = vs.validate(row, _args())
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
