import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from scraper.pipelines import MarkdownPipeline

TEXTO = (
    "El tarot de Marsella es la baraja clásica del tarot europeo, con "
    "setenta y ocho cartas divididas en arcanos mayores y menores. Cada "
    "carta se interpreta según su simbología, su posición en la tirada y "
    "las cartas que la rodean en el tapete del consultante. "
) * 3


def _item(url="https://ejemplo.com/guia", title="Guía de tarot", texto=TEXTO, lang=None):
    item = {
        "url": url,
        "domain": urlparse(url).netloc,
        "title": title,
        "depth": 0,
        "text": texto,
    }
    if lang is not None:
        item["lang"] = lang
    return item


def _md_files(out_dir):
    return sorted(p for p in Path(out_dir).rglob("*.md"))


def _manifest_records(out_dir):
    manifest = Path(out_dir) / "pages.jsonl"
    if not manifest.exists():
        return []
    return [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestDedupePersistente(unittest.TestCase):
    def test_mismo_texto_un_solo_fichero(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item(url="https://a.com/guia-1"))
            pipe.process_item(_item(url="https://b.com/guia-2"))
            self.assertEqual(len(_md_files(d)), 1)
            self.assertEqual(len(_manifest_records(d)), 1)

    def test_reabrir_no_reguarda(self):
        with tempfile.TemporaryDirectory() as d:
            primero = MarkdownPipeline(d)
            primero.open_spider()
            primero.process_item(_item())
            segundo = MarkdownPipeline(d)
            segundo.open_spider()
            segundo.process_item(_item())
            self.assertEqual(len(_md_files(d)), 1)
            self.assertEqual(len(_manifest_records(d)), 1)

    def test_textos_distintos_si_se_guardan(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item(url="https://a.com/uno", texto=TEXTO))
            pipe.process_item(_item(url="https://a.com/dos", texto=TEXTO + "Y más contenido único para el segundo artículo de tarot que lo diferencia."))
            self.assertEqual(len(_md_files(d)), 2)


class TestLicenciaYIdioma(unittest.TestCase):
    def test_license_hint_wikipedia(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item(url="https://es.wikipedia.org/wiki/Tarot", title="Tarot - Wikipedia"))
            rec = _manifest_records(d)[0]
            self.assertEqual(rec["license_hint"], "cc-by-sa")
            md = _md_files(d)[0].read_text(encoding="utf-8")
            self.assertIn("license_hint: cc-by-sa", md)

    def test_license_hint_otro_dominio(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item(url="https://tarot.example.org/cartas"))
            rec = _manifest_records(d)[0]
            self.assertEqual(rec["license_hint"], "consultar")

    def test_lang_en_manifiesto_y_front_matter(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item(lang="es"))
            rec = _manifest_records(d)[0]
            self.assertEqual(rec["lang"], "es")
            md = _md_files(d)[0].read_text(encoding="utf-8")
            self.assertIn("lang: es", md)

    def test_sin_lang_no_esta_en_el_fichero(self):
        with tempfile.TemporaryDirectory() as d:
            pipe = MarkdownPipeline(d)
            pipe.open_spider()
            pipe.process_item(_item())
            rec = _manifest_records(d)[0]
            self.assertNotIn("lang", rec)
            md = _md_files(d)[0].read_text(encoding="utf-8")
            self.assertNotIn("lang:", md)


if __name__ == "__main__":
    unittest.main()
