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


if __name__ == "__main__":
    unittest.main()
