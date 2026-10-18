import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hashlib
import tempfile
import unittest
from pathlib import Path

import collect_corpus


def _esperado(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:4]


class TestSavePageDeterminista(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_pagina_vacia_devuelve_none(self):
        self.assertIsNone(collect_corpus.save_page("   ", "https://ejemplo.com/x", self.raw))

    def test_misma_url_mismo_contenido_no_duplica(self):
        url = "https://ejemplo.com/guia"
        md = "# Guía\n\nContenido estable."
        r1 = collect_corpus.save_page(md, url, self.raw)
        r2 = collect_corpus.save_page(md, url, self.raw)
        self.assertEqual(r1, r2)
        archivos = sorted(p.name for p in (self.raw / "ejemplo.com").iterdir())
        self.assertEqual(archivos, ["guia.md"])

    def test_url_distinta_mismo_slug_nombre_estable(self):
        url1 = "https://ejemplo.com/guia"
        url2 = "https://ejemplo.com/guia?utm=1"
        collect_corpus.save_page("# Guía\n\nPrimera.", url1, self.raw)
        r2 = collect_corpus.save_page("# Guía\n\nSegunda.", url2, self.raw)
        esperado = f"guia_{_esperado(url2)}.md"
        self.assertEqual(r2, f"ejemplo.com/{esperado}")
        archivos = sorted(p.name for p in (self.raw / "ejemplo.com").iterdir())
        self.assertEqual(archivos, ["guia.md", esperado])

    def test_sufijo_no_depende_del_hash_de_python(self):
        url = "https://ejemplo.com/articulo-unico"
        r = collect_corpus.save_page("# Único\n\nTexto.", url, self.raw)
        self.assertEqual(r, f"ejemplo.com/articulo_unico.md")
        url2 = "https://ejemplo.com/articulo-unico?ref=2"
        r2 = collect_corpus.save_page("# Único\n\nOtro texto.", url2, self.raw)
        self.assertTrue(r2.endswith(f"_{_esperado(url2)}.md"))


if __name__ == "__main__":
    unittest.main()
