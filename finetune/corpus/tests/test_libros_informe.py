# Tests de libros_informe: tabla por libro y resumen global.
import json
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tempfile
import unittest

from libros_informe import generar_informe, main

TEXTO_ES = ("de la que el en y a los se del las un por con no una su para es "
            "al lo como más pero sus le ya o este sí porque esta entre cuando "
            "muy")
TEXTO_EN = ("the of and a to in is you that it he was for on are as with his "
            "they i at be this have from or one had by word but not what all")


def _escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


class Informe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.libros = os.path.join(self.base, "libros")
        self.knowledge = os.path.join(self.base, "knowledge")
        os.makedirs(self.knowledge)

        filas = [
            {"id": "libro-es", "familia": "tarot", "nivel": "A",
             "prioridad": "alta", "titulo": "Libro de prueba",
             "idioma": "es", "texto_ocr": "x_djvu.txt", "texto_kb": 10,
             "estado": "texto_verificado"},
            {"id": "libro-en", "familia": "tarot", "nivel": "A",
             "prioridad": "alta", "titulo": "Libro mal etiquetado",
             "idioma": "en", "texto_ocr": "y_djvu.txt", "texto_kb": 10,
             "estado": "texto_verificado"},
        ]
        _escribir(os.path.join(self.knowledge, "fuentes_libros_es.jsonl"),
                  "\n".join(json.dumps(f, ensure_ascii=False) for f in filas))

        crudo = (TEXTO_ES + "\nPage 2 The text on this page is estimated to be "
                 "only 10% accurate\nbasura OCR")
        _escribir(os.path.join(self.libros, "crudo", "libro-es.txt"), crudo)
        _escribir(os.path.join(self.libros, "limpio", "libro-es.txt"), TEXTO_ES)
        _escribir(os.path.join(self.libros, "secciones", "libro-es.jsonl"),
                  '{"seccion": 1}\n{"seccion": 2}\n')

        _escribir(os.path.join(self.libros, "crudo", "libro-en.txt"), TEXTO_ES)
        _escribir(os.path.join(self.libros, "limpio", "libro-en.txt"), TEXTO_ES)
        _escribir(os.path.join(self.libros, "secciones", "libro-en.jsonl"),
                  '{"seccion": 1}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_genera_tabla_y_resumen(self):
        salida = os.path.join(self.base, "informe.md")
        texto = generar_informe(self.libros, salida, self.knowledge)
        self.assertTrue(os.path.exists(salida))
        with open(salida, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), texto)
        self.assertIn("Libro de prueba", texto)
        self.assertIn("Páginas", texto)
        self.assertIn("Ratio", texto)
        self.assertIn("Calidad", texto)
        self.assertIn("Resumen global", texto)
        # El primer libro tiene una página OCR descartada y dos secciones.
        self.assertIn("| 1 |", texto)
        self.assertIn("| 2 |", texto)

    def test_marca_idioma_que_no_coincide(self):
        salida = os.path.join(self.base, "informe.md")
        texto = generar_informe(self.libros, salida, self.knowledge)
        self.assertIn("no coincide", texto)
        self.assertIn("Libro mal etiquetado", texto)

    def test_cli(self):
        salida = os.path.join(self.base, "informe-cli.md")
        codigo = main(["--in-dir", self.libros, "--out", salida,
                       "--knowledge-dir", self.knowledge])
        self.assertEqual(codigo, 0)
        self.assertTrue(os.path.exists(salida))


if __name__ == "__main__":
    unittest.main()
