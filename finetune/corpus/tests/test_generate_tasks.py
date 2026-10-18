import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import generate_tasks as gt


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


if __name__ == "__main__":
    unittest.main()
