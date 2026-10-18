"""Tests del módulo license_filter: clases de licencia y permisos por origen."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import license_filter


def _escribir(ruta, texto=""):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")


class RaizLicencias(unittest.TestCase):
    """Raiz temporal con manifests ficticios para cada origen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "corpus")
        os.makedirs(self.root)
        # manifest de raw/ (Firecrawl): lista de {url, dominio, licencia, estado}
        manifest_raw = [
            {"url": "https://es.wikipedia.org/wiki/Tarot", "dominio": "es.wikipedia.org",
             "licencia": "CC BY-SA (Wikipedia)", "estado": "ok"},
            {"url": "https://example.com/guia", "dominio": "example.com",
             "licencia": "consultar", "estado": "ok"},
            {"url": "https://gutenberg.org/ebooks/123", "dominio": "gutenberg.org",
             "licencia": "dominio público (Project Gutenberg)", "estado": "ok"},
        ]
        _escribir(self._p("manifest.json"), json.dumps(manifest_raw, ensure_ascii=False))
        # docs/manifest.json: dict id -> {familia, licencia, ...}
        manifest_docs = {
            "El Tarot de Marsella": {"id": "El Tarot de Marsella", "familia": "tarot",
                                    "licencia": "dominio público (1911)"},
            "Libro Prohibido": {"id": "Libro Prohibido", "familia": "ocultismo",
                               "licencia": "CC BY-NC-ND"},
        }
        _escribir(self._p("docs", "manifest.json"), json.dumps(manifest_docs, ensure_ascii=False))
        # docs_epub/manifest.json: dict id -> {tema, licencia, fichero}
        manifest_epub = {
            "meditaciones": {"id": "meditaciones", "tema": "tarot",
                            "licencia": "consultar", "fichero": "Meditaciones.epub"},
            "dominios": {"id": "dominios", "tema": "astrologia",
                        "licencia": "dominio público", "fichero": "Dominios.epub"},
        }
        _escribir(self._p("docs_epub", "manifest.json"), json.dumps(manifest_epub, ensure_ascii=False))
        # raw_scrapy con front-matter
        _escribir(self._p("raw_scrapy", "es-wikipedia-org", "tarot.md"),
                  "---\nurl: https://es.wikipedia.org/wiki/Tarot\ndomain: es.wikipedia.org\n---\nTexto.\n")
        _escribir(self._p("raw_scrapy", "example-com", "guia.md"),
                  "---\nurl: https://example.com/guia\ndomain: example.com\n---\nTexto.\n")
        license_filter.configure(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _p(self, *partes):
        return Path(self.root).joinpath(*partes)


class TestParseoLicencia(RaizLicencias):
    def test_dominio_publico_con_ano(self):
        self.assertEqual(license_filter.classify_license_text("dominio público (1896)"), "publico")

    def test_public_domain_mark_manuscrito(self):
        self.assertEqual(
            license_filter.classify_license_text("Public Domain Mark (manuscrito 1700)"), "publico")

    def test_cc_by(self):
        self.assertEqual(license_filter.classify_license_text("CC BY"), "cc-by")

    def test_cc_by_sa_wikipedia(self):
        self.assertEqual(
            license_filter.classify_license_text("CC BY-SA (Wikipedia)"), "cc-by-sa")

    def test_nc_manda_sobre_nd(self):
        self.assertEqual(license_filter.classify_license_text("CC BY-NC-ND"), "cc-nc")

    def test_cc_by_nd_con_consultar(self):
        self.assertEqual(
            license_filter.classify_license_text("CC BY-ND (consultar)"), "cc-nd")

    def test_consultar_sin_licencia_registrada(self):
        self.assertEqual(
            license_filter.classify_license_text("consultar (sin licencia registrada)"), "desconocida")

    def test_dominio_publico_verificar_es_desconocida(self):
        self.assertEqual(
            license_filter.classify_license_text("dominio público (verificar)"), "desconocida")

    def test_dominio_publico_varia_por_obra_es_desconocida(self):
        self.assertEqual(
            license_filter.classify_license_text("dominio público (varía por obra)"), "desconocida")

    def test_dominio_publico_cc_by_sa_es_la_mas_restrictiva(self):
        self.assertEqual(
            license_filter.classify_license_text("dominio público / CC BY-SA"), "cc-by-sa")

    def test_texto_vacio_es_desconocida(self):
        self.assertEqual(license_filter.classify_license_text(""), "desconocida")


class TestRutasOrigen(RaizLicencias):
    def test_raw_manifest_por_ruta_relativa(self):
        self.assertEqual(
            license_filter.license_of("raw/es.wikipedia.org/wiki_Tarot.md"), "cc-by-sa")

    def test_raw_manifest_sin_licencia_conocida(self):
        self.assertEqual(license_filter.license_of("raw/example.com/guia.md"), "desconocida")

    def test_raw_gutenberg_es_publico(self):
        self.assertEqual(
            license_filter.license_of("raw/gutenberg.org/ebooks_123.md"), "publico")

    def test_colision_sufijo_hex_resuelve_a_la_base(self):
        self.assertEqual(
            license_filter.license_of("raw/es.wikipedia.org/wiki_Tarot_1a2b.md"), "cc-by-sa")

    def test_docs_libro_por_slugify(self):
        self.assertEqual(
            license_filter.license_of("raw/docs/tarot/el_tarot_de_marsella.md"), "publico")

    def test_docs_libro_nc(self):
        self.assertEqual(
            license_filter.license_of("raw/docs/ocultismo/libro_prohibido.md"), "cc-nc")

    def test_raw_scrapy_wikipedia_es_cc_by_sa(self):
        self.assertEqual(
            license_filter.license_of("raw_scrapy/es-wikipedia-org/tarot.md"), "cc-by-sa")

    def test_raw_scrapy_otro_dominio_es_desconocida(self):
        self.assertEqual(
            license_filter.license_of("raw_scrapy/example-com/guia.md"), "desconocida")

    def test_epub_consultar_es_desconocida(self):
        self.assertEqual(
            license_filter.license_of("docs_epub/tarot/Meditaciones.epub"), "desconocida")

    def test_epub_dominio_publico(self):
        self.assertEqual(
            license_filter.license_of("docs_epub/astrologia/Dominios.epub"), "publico")

    def test_ruta_absoluta_bajo_la_raiz(self):
        abs_path = self._p("raw", "es.wikipedia.org", "wiki_Tarot.md")
        self.assertEqual(license_filter.license_of(abs_path), "cc-by-sa")

    def test_ruta_desconocida_es_desconocida(self):
        self.assertEqual(
            license_filter.license_of("raw/ningun-sitio.io/nada.md"), "desconocida")

    def test_path_relativo_a_raw_sin_prefijo(self):
        self.assertEqual(
            license_filter.license_of("es.wikipedia.org/wiki_Tarot.md"), "cc-by-sa")


class TestPermisos(RaizLicencias):
    def test_es_permitido_por_defecto(self):
        self.assertTrue(license_filter.is_allowed("raw/es.wikipedia.org/wiki_Tarot.md"))
        self.assertTrue(license_filter.is_allowed("raw/gutenberg.org/ebooks_123.md"))

    def test_no_permitido_nc(self):
        self.assertFalse(license_filter.is_allowed("raw/docs/ocultismo/libro_prohibido.md"))

    def test_no_permitido_desconocida(self):
        self.assertFalse(license_filter.is_allowed("raw/example.com/guia.md"))

    def test_lista_permitida_personalizada(self):
        self.assertTrue(
            license_filter.is_allowed("raw/example.com/guia.md", allowed=("desconocida",)))
        self.assertFalse(
            license_filter.is_allowed("raw/es.wikipedia.org/wiki_Tarot.md", allowed=("publico",)))


class TestManifiestosAusentes(RaizLicencias):
    def test_sin_manifests_no_explode(self):
        vacio = tempfile.TemporaryDirectory()
        try:
            license_filter.configure(vacio.name)
            self.assertEqual(
                license_filter.license_of("raw/algo/donde.md"), "desconocida")
            self.assertFalse(license_filter.is_allowed("raw/algo/donde.md"))
        finally:
            vacio.cleanup()

    def test_configure_cambia_de_raiz(self):
        self.assertEqual(
            license_filter.license_of("raw/es.wikipedia.org/wiki_Tarot.md"), "cc-by-sa")
        otro = tempfile.TemporaryDirectory()
        try:
            license_filter.configure(otro.name)
            self.assertEqual(
                license_filter.license_of("raw/es.wikipedia.org/wiki_Tarot.md"), "desconocida")
        finally:
            otro.cleanup()


if __name__ == "__main__":
    unittest.main()
