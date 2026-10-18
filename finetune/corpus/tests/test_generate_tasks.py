import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import unittest

import generate_tasks as gt


def kb_tarot_minima():
    """KB de tarot pequena para tests (alternativa si no existe la del repo)."""
    nombres = ["El Loco", "El Mago", "La Sacerdotisa", "La Emperatriz", "El Emperador",
               "El Hierofante", "Los Enamorados", "El Carro", "La Fuerza", "El Ermitano",
               "La Rueda de la Fortuna", "La Justicia"]
    return {
        "mayores": [
            {"nombre": n, "palabras_clave": ["clave"], "significado": "s", "invertida": "i"}
            for n in nombres
        ],
        "menores": [],
    }


def kbs_para_test():
    try:
        return gt.load_kb("tarot.json"), gt.load_kb("astrologia.json"), gt.load_kb("numerologia.json")
    except (OSError, ValueError):
        return kb_tarot_minima(), {"signos": [], "planetas": [], "casas": [], "aspectos": []}, []


class TestZonaHoraria(unittest.TestCase):
    def test_lima_ascendente_virgo(self):
        # 12:00 hora local de Lima = 17:00 UT; el Ascendente correcto es Virgo 20°01'.
        c = gt.calcular_carta("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        self.assertEqual(c["ascendente"]["signo"], "Virgo")
        self.assertTrue(c["ascendente"]["grados"].startswith("20°"),
                       f"grados inesperados: {c['ascendente']['grados']}")
        # La salida debe seguir mostrando la hora local original.
        self.assertEqual(c["hora"], "12:00")

    def test_madrid_verano_equivale_a_10ut(self):
        a = gt.calcular_carta("1988-07-01", "12:00", 40.4168, -3.7038, "Europe/Madrid")
        b = gt.calcular_carta("1988-07-01", "10:00", 40.4168, -3.7038, "UTC")
        self.assertEqual(a["planetas"], b["planetas"])
        self.assertEqual(a["ascendente"], b["ascendente"])


class TestOrtografia(unittest.TestCase):
    PROHIBIDAS = ["espanol", "Que energia", "Cual es", "proposito", "Geminis",
                 "Jupiter", "Pluton", "conjuncion", "trigono", "oposicion",
                 "Anio", "Mexico", "Espana"]

    def _todos_los_textos(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(1), kb_tarot, kb_astro, kb_num)
        lotes = [
            b.tarot_1(), b.tarot_2(5), b.tarot_3(5), b.cruz_celta(2),
            b.tarot_pregunta(5), b.astro_natal(5), b.sinastria(3),
            b.numerologia(5), b.lectura_completa(3), b.multiturno(5), b.etica(20),
        ]
        for lote in lotes:
            for _bloque, system, prompt, _payload, _mt in lote:
                yield system
                yield prompt

    def test_sin_subcadenas_sin_tilde(self):
        for texto in self._todos_los_textos():
            for mala in self.PROHIBIDAS:
                self.assertNotIn(mala, texto, f"subcadena sin tilde encontrada: {mala!r}")


class TestMultiturno(unittest.TestCase):
    def test_sin_te_preguntaste(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(5), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.multiturno(50):
            self.assertNotIn("Te preguntaste", prompt)

    def test_previo_honesto(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(5), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.multiturno(10):
            self.assertIn("En la consulta anterior salió", prompt)
            self.assertIn("el consultante preguntó: «", prompt)


class TestEtica(unittest.TestCase):
    def test_variedad_de_prompts(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(7), kb_tarot, kb_astro, kb_num)
        prompts = [p for _bloque, _system, p, _payload, _mt in b.etica(300)]
        self.assertGreaterEqual(len(set(prompts)), 200,
                               "los 300 prompts de ética deben tener variedad real")

    def test_todos_empiezan_igual(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(11), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.etica(300):
            self.assertTrue(prompt.startswith("Consulta delicada."))

    def test_no_repite_par_hasta_agotar(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(3), kb_tarot, kb_astro, kb_num)
        prompts = [p for _bloque, _system, p, _payload, _mt in b.etica(300)]
        # Con >= 40 casos x >= 6 arranques hay >= 240 pares: los 240 primeros son únicos.
        primeros = prompts[:240]
        self.assertEqual(len(set(primeros)), len(primeros))


if __name__ == "__main__":
    unittest.main()
