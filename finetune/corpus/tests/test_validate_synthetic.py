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


REFERENCIA = (
    "Referencia (tarot): La Torre simboliza rupturas necesarias, el fin de "
    "estructuras agrietadas y la liberación de lo que ya no sostiene en la "
    "vida del consultante y de sus apegos más antiguos."
)
COPIA_25 = (
    "La Torre simboliza rupturas necesarias, el fin de estructuras agrietadas "
    "y la liberación de lo que ya no sostiene en la vida del consultante y de "
    "sus apegos más antiguos."
)


class TestEcoPrompt(unittest.TestCase):
    def test_copia_larga_rechazada(self):
        row = _fila(human=REFERENCIA, gpt=COPIA_25 + " Por eso conviene pausar y observar.")
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "eco_prompt")

    def test_copia_corta_pasa(self):
        row = _fila(
            human=REFERENCIA,
            gpt="La Torre simboliza rupturas necesarias, pero tu caso pide otro enfoque "
                "más sereno y personal.",
        )
        ok, why = vs.validate(row, _args())
        self.assertTrue(ok, why)

    def test_etica_no_aplica_eco(self):
        row = _fila(human=REFERENCIA, gpt=COPIA_25)
        ok, why = vs.validate(row, _args(), bloque="etica")
        self.assertNotEqual(why, "eco_prompt")

    def test_prompt_corto_no_aplica_eco(self):
        row = _fila(
            human="Carta: La Torre.",
            gpt="La Torre. La Torre. La Torre anuncia un final necesario que deja espacio "
                "para empezar de nuevo con calma y claridad.",
        )
        ok, why = vs.validate(row, _args())
        self.assertNotEqual(why, "eco_prompt")


class TestIaMeta(unittest.TestCase):
    def test_como_modelo_de_lenguaje(self):
        row = _fila(
            human="Háblame del amor.",
            gpt="Lo siento, pero como modelo de lenguaje no tengo opiniones propias.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_no_tengo_acceso(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="No tengo acceso a datos en tiempo real, pero interpreto lo que me das.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_etiquetas_think(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="<|im_start|> pienso <|im_end|> La Torre anuncia un cambio profundo y necesario.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_bloque_think_previo_rechazado(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="<think>pienso</think> La Torre anuncia un cambio profundo y necesario.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_cierre_think_suelto_rechazado(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="</think> La Torre anuncia un cambio profundo y necesario.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_thinking_en_mayusculas_rechazado(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="<THINKING> La Torre anuncia un cambio profundo y necesario.",
        )
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_respuesta_sin_marcas_pasa(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="La Torre anuncia un cambio profundo y necesario.",
        )
        ok, why = vs.validate(row, _args())
        self.assertTrue(ok, why)

    def test_palabra_think_sin_marcas_pasa(self):
        row = _fila(
            human="¿Qué cartas salieron?",
            gpt="La Torre invita a pensar el cambio con calma. Think in images, no en etiquetas.",
        )
        ok, why = vs.validate(row, _args())
        self.assertTrue(ok, why)

    def test_etica_no_aplica_ia_meta(self):
        row = _fila(
            human="¿Puedes predecir mi muerte?",
            gpt="Como modelo de lenguaje no puedo ayudarte con eso: consulta a un profesional.",
        )
        ok, why = vs.validate(row, _args(), bloque="etica")
        self.assertTrue(ok, why)


G1_MT = ("La luna nueva te invita a soltar viejas heridas y abrir un ciclo de "
         "calma interior; hoy el tarot sugiere paciencia y escucha atenta.")
G2_MT = ("Sobre esa misma calma, la carta recomienda dar el primer paso sin "
         "ruido: escribe hoy una nota breve y clara para ti.")


def _fila_mt(system="SYS", h1="Pregunta uno", g1=G1_MT, h2="Pregunta dos", g2=G2_MT):
    return {
        "turnos": 2,
        "conversations": [
            {"from": "system", "value": system},
            {"from": "human", "value": h1},
            {"from": "gpt", "value": g1},
            {"from": "human", "value": h2},
            {"from": "gpt", "value": g2},
        ],
    }


class TestTurnosDe(unittest.TestCase):
    def test_empareja_humano_gpt(self):
        pares = vs.turnos_de(_fila_mt())
        self.assertEqual(len(pares), 2)
        self.assertEqual(pares[0][0], "Pregunta uno")
        self.assertEqual(pares[1][1], G2_MT)

    def test_un_turno(self):
        pares = vs.turnos_de(_fila(human="h", gpt="g"))
        self.assertEqual(pares, [("h", "g")])

    def test_human_final_sin_gpt_se_ignora(self):
        row = _fila_mt()
        row["conversations"].append({"from": "human", "value": "colgando"})
        self.assertEqual(len(vs.turnos_de(row)), 2)


class TestValidarMultiturno(unittest.TestCase):
    def test_bueno_pasa(self):
        ok, why = vs.validate(_fila_mt(), _args())
        self.assertTrue(ok, why)

    def test_turno2_copia_total(self):
        row = _fila_mt(g2=G1_MT)
        ok, why = vs.validate(row, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "turno2_copia_turno1")

    def test_turno2_copia_por_frases(self):
        g1 = ("La luna nueva trae calma interior. El tarot sugiere paciencia "
              "hoy. Suelta las viejas heridas poco a poco. Escucha tu voz "
              "interior cada mañana. Descansa sin culpa esta semana.")
        g2 = ("La luna nueva trae calma interior. El tarot sugiere paciencia "
              "hoy. Suelta las viejas heridas poco a poco. En marzo escribe "
              "una nota breve y clara para ti.")
        ok, why = vs.validate(_fila_mt(g1=g1, g2=g2), _args())
        self.assertFalse(ok)
        self.assertEqual(why, "turno2_copia_turno1")

    def test_turno2_sin_hilo(self):
        g2 = ("El reloj marca las tres de la madrugada y fuera llueve con "
              "fuerza sobre los tejados de la ciudad dormida, ajena a todo.")
        ok, why = vs.validate(_fila_mt(g2=g2), _args())
        self.assertFalse(ok)
        self.assertEqual(why, "turno2_sin_hilo")

    def test_turno2_corto(self):
        ok, why = vs.validate(_fila_mt(g2="Vale, gracias."), _args())
        self.assertFalse(ok)
        self.assertEqual(why, "turno2_corto")

    def test_primer_par_corto_usa_corto(self):
        ok, why = vs.validate(_fila_mt(g1="Corta."), _args())
        self.assertFalse(ok)
        self.assertEqual(why, "corto")

    def test_idioma_en_segundo_turno(self):
        g2 = ("The moon brings you calm and the cards suggest patience and "
             "inner listening today, my dear friend, rest well and breathe.")
        ok, why = vs.validate(_fila_mt(g2=g2), _args())
        self.assertFalse(ok)
        self.assertTrue(why.startswith("idioma_"))

    def test_boilerplate_en_segundo_turno(self):
        g2 = ("Sobre esa calma, la carta recomienda lo mismo: for entertainment "
             "purposes only, nothing more to add here about your reading today.")
        ok, why = vs.validate(_fila_mt(g2=g2), _args())
        self.assertFalse(ok)
        self.assertEqual(why, "boilerplate")

    def test_un_turno_no_aplica_reglas_mt(self):
        fila = _fila(human="¿Qué sale hoy?",
                    gpt=G1_MT + " " + G2_MT)
        ok, why = vs.validate(fila, _args())
        self.assertTrue(ok, why)


CALCULOS_ASTRO = {
    "carta_natal": {
        "planetas": {
            "Sol": {"signo": "Capricornio"},
            "Luna": {"signo": "Acuario"},
        },
        "ascendente": {"signo": "Piscis"},
    }
}

PROMPT_ASTRO = (
    "Lectura de carta natal.\n\n"
    "- Sol: Capricornio 10°00' (casa 1)\n"
    "- Luna: Acuario 20°00' (casa 2)\n"
    "- Ascendente: Piscis 15°00'\n"
    'Pregunta: "¿Quién soy?"'
)


class TestGroundingConCalculos(unittest.TestCase):
    """D7 (T75): el grounding usa los calculos de la fila en vez del texto del prompt."""

    def test_signos_de_calculos_incluye_ascendente_de_clave_propia(self):
        self.assertEqual(
            vs.signos_de_calculos(CALCULOS_ASTRO),
            ["capricornio", "acuario", "piscis"],
        )

    def test_signos_de_calculos_dedup_entre_cartas(self):
        calc = {
            "carta_a": {"planetas": {"Sol": {"signo": "Aries"}}, "ascendente": {"signo": "Libra"}},
            "carta_b": {"planetas": {"Sol": {"signo": "Aries"}, "Luna": {"signo": "Cáncer"}}},
        }
        self.assertEqual(vs.signos_de_calculos(calc), ["aries", "libra", "cancer"])

    def test_numeros_de_calculos_solo_claves_conocidas_enteras(self):
        calc = {"numerologia": {
            "camino_de_vida": 7, "expresion": 3, "alma": 5,
            "anio_personal": "no-entero", "extra": 9,
        }}
        self.assertEqual(vs.numeros_de_calculos(calc), ["7", "3", "5"])

    def test_grounding_astro_menciona_dos_de_tres_signos(self):
        ans = "Con el Sol en Capricornio y la Luna en Acuario, avanzas con paso firme."
        self.assertTrue(vs.grounding(PROMPT_ASTRO, ans, calculos=CALCULOS_ASTRO))

    def test_grounding_astro_sin_signos_falla(self):
        ans = "Tu carta muestra una estructura estable y un ritmo pausado para hoy."
        self.assertFalse(vs.grounding(PROMPT_ASTRO, ans, calculos=CALCULOS_ASTRO))

    def test_grounding_numerologia_usa_valores_reales_no_el_anio_del_texto(self):
        calc = {"numerologia": {"camino_de_vida": 7, "expresion": 3, "alma": 5}}
        prompt = "Numerología del año personal 2026 según tu nombre."
        ans_ok = "El 7 rige tu camino, el 3 tu expresión y el 5 tu alma."
        ans_mal = "El 2026 trae cambios bajo el número 20."
        self.assertTrue(vs.grounding(prompt, ans_ok, calculos=calc))
        self.assertFalse(vs.grounding(prompt, ans_mal, calculos=calc))

    def test_fallback_sin_calculos_es_el_comportamiento_heredado(self):
        prompt = "Tu Sol en Aries y tu Luna en Géminis piden acción."
        self.assertTrue(vs.grounding(prompt, "Aries empuja y Géminis comunica tus ideas."))
        self.assertFalse(vs.grounding(prompt, "Hoy toca descansar y observar sin prisa."))

    def test_validate_usa_calculos_de_la_fila(self):
        args = _args(min_chars=10)
        base = {
            "system": "Eres una astróloga profesional y empática.",
            "human": PROMPT_ASTRO,
        }
        con_signos = _fila(**base, gpt="El Sol en Capricornio y el Ascendente en Piscis te marcan constancia.")
        ok, why = vs.validate({**con_signos, "calculos": CALCULOS_ASTRO}, args, "astro_natal")
        self.assertNotEqual(why, "sin_datos_del_prompt")
        sin_signos = _fila(**base, gpt="Tu carta revela una personalidad tranquila y constante.")
        ok2, why2 = vs.validate({**sin_signos, "calculos": CALCULOS_ASTRO}, args, "astro_natal")
        self.assertFalse(ok2)
        self.assertEqual(why2, "sin_datos_del_prompt")


class TestBloqueDeFila(unittest.TestCase):
    """D1 (T75): main toma el bloque de la fila, no solo del nombre del fichero."""

    def test_main_usa_bloque_de_la_fila(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            fila_etica = {
                "conversations": [
                    {"from": "system", "value": "Eres una consejera ética y prudente."},
                    {"from": "human", "value": "Mi hija de 14 años quiere una lectura, ¿qué le digo?"},
                    {"from": "gpt", "value": "Acompaña su curiosidad con calma y evita pronósticos que la asusten."},
                ],
                "bloque": "etica",
            }
            fila_tarot = {
                "conversations": [
                    {"from": "system", "value": "Eres una tarotista profesional."},
                    {"from": "human", "value": "Carta: El Loco (al derecho). Contexto: trabajo."},
                    {"from": "gpt", "value": "El Loco inicia un camino nuevo e ilusionante en tu trabajo."},
                ],
                "bloque": "tarot_1",
            }
            (d / "aceptadas.jsonl").write_text(
                "\n".join(json.dumps(f, ensure_ascii=False) for f in (fila_etica, fila_tarot)) + "\n",
                encoding="utf-8",
            )
            rc = vs.main([
                "--dir", td,
                "--out", str(d / "clean.jsonl"),
                "--meta-out", str(d / "meta.jsonl"),
                "--report", str(d / "report.json"),
                "--min-chars", "10",
            ])
            self.assertEqual(rc, 0)
            report = json.loads((d / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(set(report["per_block"].keys()), {"etica", "tarot_1"})


if __name__ == "__main__":
    unittest.main()
