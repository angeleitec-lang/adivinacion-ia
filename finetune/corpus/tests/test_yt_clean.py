#!/usr/bin/env python3
"""Tests para yt_clean.py (A4.3)."""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
import yt_clean
import cartas


def _fixture_path() -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", "boBobcR3xiw.es-orig.vtt")


class VttAFrases(unittest.TestCase):
    def test_parsea_cabeceras_y_cues(self):
        vtt = """WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:02.000
hola mundo

00:00:02.000 --> 00:00:03.000
segunda frase
"""
        frases = yt_clean.vtt_a_frases(vtt)
        self.assertEqual(len(frases), 2)
        self.assertAlmostEqual(frases[0]["t0"], 1.0)
        self.assertEqual(frases[0]["texto"], "hola mundo")
        self.assertAlmostEqual(frases[1]["t0"], 2.0)
        self.assertEqual(frases[1]["texto"], "segunda frase")

    def test_ignora_etiquetas_inline(self):
        vtt = """WEBVTT
00:00:01.000 --> 00:00:02.000
hola<00:00:01.500><c> mundo</c>
"""
        frases = yt_clean.vtt_a_frases(vtt)
        self.assertEqual(frases[0]["texto"], "hola mundo")

    def test_elimina_tags_c(self):
        vtt = """WEBVTT
00:00:01.000 --> 00:00:02.000
<c>hola</c> <c>mundo</c>
"""
        frases = yt_clean.vtt_a_frases(vtt)
        self.assertEqual(frases[0]["texto"], "hola mundo")


class Limpiar(unittest.TestCase):
    def test_elimina_musica_y_aplausos(self):
        vtt = """WEBVTT
00:00:01.000 --> 00:00:02.000
[Música]
00:00:02.000 --> 00:00:03.000
hola
00:00:03.000 --> 00:00:04.000
[Aplausos]
"""
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        self.assertNotIn("[Música]", limpio)
        self.assertNotIn("[Aplausos]", limpio)
        self.assertIn("hola", limpio)

    def test_elimina_urls(self):
        vtt = """WEBVTT
00:00:01.000 --> 00:00:02.000
visita https://ejemplo.com para más
"""
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        self.assertNotIn("https://ejemplo.com", limpio)

    def test_sin_duplicados_consecutivos(self):
        vtt = """WEBVTT
00:00:01.000 --> 00:00:02.000
hola mundo
00:00:02.000 --> 00:00:03.000
hola mundo
00:00:03.000 --> 00:00:04.000
hola mundo extra
"""
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        # No debe haber "hola mundo hola mundo" consecutivo
        self.assertNotIn("hola mundo hola mundo", limpio)
        self.assertIn("hola mundo extra", limpio)

    def test_fixture_real_sin_musica(self):
        if not os.path.exists(_fixture_path()):
            self.skipTest("Fixture no disponible")
        with open(_fixture_path(), encoding="utf-8") as f:
            vtt = f.read()
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        self.assertNotIn("[Música]", limpio)
        self.assertNotIn("[música]", limpio)

    def test_fixture_real_palabras_minimas(self):
        if not os.path.exists(_fixture_path()):
            self.skipTest("Fixture no disponible")
        with open(_fixture_path(), encoding="utf-8") as f:
            vtt = f.read()
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        self.assertGreaterEqual(len(limpio.split()), 2000)

    def test_fixture_real_cartas_por_mil(self):
        if not os.path.exists(_fixture_path()):
            self.skipTest("Fixture no disponible")
        with open(_fixture_path(), encoding="utf-8") as f:
            vtt = f.read()
        frases = yt_clean.vtt_a_frases(vtt)
        limpio = yt_clean.limpiar(frases)
        m = yt_clean.metricas(limpio, duracion_s=1200)
        self.assertGreater(m["cartas_por_1000"], 5.0)


class Metricas(unittest.TestCase):
    def test_calculo_basico(self):
        texto = "hola mundo " * 100  # 200 palabras
        m = yt_clean.metricas(texto, duracion_s=60)
        self.assertEqual(m["palabras"], 200)
        self.assertAlmostEqual(m["palabras_por_min"], 200.0)

    def test_cartas_por_mil_con_cartas(self):
        # Texto con varias cartas conocidas + contexto para evitar filtrado
        texto = ("carta el loco carta la muerte carta el sol carta la luna " * 10)
        m = yt_clean.metricas(texto, duracion_s=60)
        self.assertGreater(m["cartas_por_1000"], 100)


if __name__ == "__main__":
    import unittest
    unittest.main()
