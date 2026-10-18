# Tests de libros_fuentes: inventario unificado de los cuatro ficheros.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import tempfile
import unittest

from libros_fuentes import cargar_inventario, normalizar_titulo

ESQUEMA = {"id", "titulo", "autor", "anio", "idioma", "familia", "prioridad",
           "origen", "url", "ruta_local", "calidad", "nota"}


def _escribir(dirk, nombre, filas):
    with open(os.path.join(dirk, nombre), "w", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


class CargarInventario(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dirk = self.tmp.name
        _escribir(self.dirk, "fuentes_libros.jsonl", [
            {"id": "waite-pkt", "titulo": "The Pictorial Key to the Tarot",
             "autor": "A. E. Waite", "anio": 1911, "idioma": "en",
             "familia": "tarot", "texto_ocr": "Pictorial Key_djvu.txt",
             "texto_kb": 229, "estado": "texto_verificado"},
            {"id": "prestamo", "titulo": "Solo Prestamo", "autor": "X",
             "anio": 1990, "idioma": "en", "familia": "astrologia",
             "estado": "solo_prestamo_o_sin_texto"},
        ])
        _escribir(self.dirk, "fuentes_libros_es.jsonl", [
            {"id": "arcanos-es", "titulo": "Los Arcanos Mayores del Tarot",
             "autor": "anónimo", "anio": 1987, "idioma": "es",
             "familia": "tarot", "prioridad": "alta",
             "texto_ocr": "Arcanos [ocr]_djvu.txt", "texto_kb": 180,
             "estado": "texto_verificado"},
        ])
        _escribir(self.dirk, "fuentes_libros_tema.jsonl", [
            {"id": "manual-carto", "titulo": "A Manual of Cartomancy",
             "autor": "Grand Orient", "anio": 1909, "idioma": "en",
             "familia": "baraja", "prioridad": "alta",
             "texto_ocr": "manual.pdf_djvu.txt", "texto_kb": 400,
             "estado": "texto_verificado"},
        ])
        _escribir(self.dirk, "epubs_locales.jsonl", [
            {"id": "waite-epub", "titulo": "The Pictorial Key to the Tarot",
             "autor": "A. E. Waite", "anio": 1911, "idioma": "en",
             "tema": "tarot", "chars": 50000,
             "fichero": "corpus/docs_epub/tarot/waite.epub",
             "decision": "usar"},
            {"id": "case-fund", "titulo": "Tarot Fundamentals",
             "autor": "Paul Foster Case", "anio": 1936, "idioma": "en",
             "tema": "tarot", "chars": 300000,
             "fichero": "corpus/docs_epub/tarot/case.epub",
             "decision": "usar_con_limpieza"},
            {"id": "descartado", "titulo": "Basura", "autor": "Y",
             "anio": 2000, "idioma": "en", "tema": "tarot", "chars": 10,
             "fichero": "corpus/docs_epub/tarot/basura.epub",
             "decision": "descartar"},
        ])

    def test_descarta_lo_no_verificado(self):
        inv = cargar_inventario(self.dirk)
        ids = {r["id"] for r in inv}
        self.assertNotIn("prestamo", ids)
        self.assertNotIn("descartado", ids)

    def test_esquema_comun(self):
        for r in cargar_inventario(self.dirk):
            self.assertEqual(set(r.keys()), ESQUEMA)

    def test_origen_y_calidad_archive(self):
        r = next(r for r in cargar_inventario(self.dirk) if r["id"] == "arcanos-es")
        self.assertEqual(r["origen"], "archive")
        self.assertEqual(r["calidad"], "con_limpieza")
        self.assertEqual(r["prioridad"], "alta")

    def test_url_archive_url_codificada(self):
        r = next(r for r in cargar_inventario(self.dirk) if r["id"] == "arcanos-es")
        self.assertTrue(r["url"].startswith("https://archive.org/download/arcanos-es/"))
        self.assertIn("%5Bocr%5D", r["url"])
        self.assertNotIn(" ", r["url"])

    def test_epub_origen_ruta_y_calidad(self):
        r = next(r for r in cargar_inventario(self.dirk) if r["id"] == "case-fund")
        self.assertEqual(r["origen"], "epub_local")
        self.assertEqual(r["calidad"], "con_limpieza")
        esperado = os.path.abspath(os.path.join(self.dirk, "..",
                                              "corpus/docs_epub/tarot/case.epub"))
        self.assertEqual(r["ruta_local"], esperado)
        self.assertIsNone(r["url"])
        self.assertEqual(r["familia"], "tarot")

    def test_epub_usar_es_limpio(self):
        inv = {r["id"]: r for r in cargar_inventario(self.dirk)}
        # Waite EPUB es 'usar' pero pierde en dedup por tamaño; usamos otro caso:
        # si el EPUB es mayor, gana y queda limpio.
        self.assertEqual(inv["waite-pkt"]["origen"], "archive")

    def test_dedup_por_titulo_conserva_mayor_tamano(self):
        inv = {r["id"]: r for r in cargar_inventario(self.dirk)}
        # archive 229 KB = 234496 chars > epub 50000 → gana archive
        self.assertNotIn("waite-epub", inv)
        self.assertIn("waite-pkt", inv)

    def test_prioridad_por_defecto(self):
        inv = {r["id"]: r for r in cargar_inventario(self.dirk)}
        self.assertEqual(inv["waite-pkt"]["prioridad"], "media")
        self.assertEqual(inv["case-fund"]["prioridad"], "media")

    def test_normalizar_titulo(self):
        self.assertEqual(normalizar_titulo("  El Tarot: ¡Místico! "),
                         normalizar_titulo("el tarot mistico"))


if __name__ == "__main__":
    unittest.main()
