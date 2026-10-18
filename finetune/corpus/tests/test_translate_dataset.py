"""Tests de translate_dataset: detección de idioma y validación de traducción."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import translate_dataset as td


class DetectLanguage(unittest.TestCase):
    def test_listas_sin_solapamiento(self):
        self.assertEqual(set(td.ES_WORDS) & set(td.EN_WORDS), set())

    def test_no_espanol_no_es_ingles(self):
        texto = "No es lo que parece. No sabes que no puedes. No."
        self.assertEqual(td.detect_language(texto), "es")

    def test_no_acumulado_sigue_espanol(self):
        texto = "Esto no es ni sí ni no, no, no, no y no."
        self.assertEqual(td.detect_language(texto), "es")

    def test_ingles_autentico(self):
        texto = ("The card means that you have to look at what is "
                 "in front of you.")
        self.assertEqual(td.detect_language(texto), "en")

    def test_vacio_unknown(self):
        self.assertEqual(td.detect_language(""), "unknown")


class ValidarTraduccion(unittest.TestCase):
    def test_vacio(self):
        texto, motivo = td.validar_traduccion("Some english source text.", "   ", "stop")
        self.assertIsNone(texto)
        self.assertIn("vacío", motivo)

    def test_bloque_think_se_quita(self):
        original = "The moon is beautiful tonight."
        traducida = "<think>voy a pensar</think>La luna es hermosa esta noche."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "La luna es hermosa esta noche.")

    def test_truncada_se_rechaza(self):
        original = "The moon is beautiful tonight."
        texto, motivo = td.validar_traduccion(original, "La luna es hermosa", "length")
        self.assertIsNone(texto)
        self.assertIn("truncada", motivo)

    def test_sigue_en_ingles(self):
        original = "The card means change and transformation ahead."
        texto, motivo = td.validar_traduccion(
            original, "The card is the tower of change.", "stop")
        self.assertIsNone(texto)
        self.assertIn("inglés", motivo)

    def test_ratio_fuera_de_rango(self):
        original = "word " * 400
        texto, motivo = td.validar_traduccion(original, "Poco texto.", "stop")
        self.assertIsNone(texto)
        self.assertIn("ratio", motivo)

    def test_prefijo_traduccion_recortado(self):
        original = "Good morning, friend."
        traducida = "Aquí está la traducción:\n\nBuenos días, amigo."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "Buenos días, amigo.")

    def test_prefijo_corto_recortado(self):
        original = "Good morning, friend."
        traducida = "Traducción: Buenos días, amigo."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "Buenos días, amigo.")

    def test_caso_bueno(self):
        original = "The card means that you have to look at what is in front of you."
        traducida = ("La carta significa que tienes que mirar lo que "
                    "tienes delante.")
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, traducida)


if __name__ == "__main__":
    unittest.main()
