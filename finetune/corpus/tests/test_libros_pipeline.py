# Tests de libros_pipeline: orquestador reanudable de la fase 0 de libros.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import io
import json
import contextlib
import tempfile
import unittest
from unittest import mock

import libros_pipeline


def _parrafo(relleno, veces):
    lineas = ["EL LOCO " + relleno]
    lineas += [relleno] * veces
    return "\n".join(lineas)


RELLENO_EN = ("the fool of the sun and the moon is a journey of the soul "
              "and he walks the long road with the light of the stars and "
              "the wheel turns once more for every one who dares to see")
RELLENO_ES = ("el loco del sol y de la luna es un viaje del alma y el anda "
              "con la luz de las estrellas y la rueda gira una vez mas para "
              "cada uno que se atreve a mirar y asi es como vemos el camino")

CRUDO_EN = "\n\n".join([_parrafo(RELLENO_EN, 15)] * 4)
CRUDO_ES = "\n\n".join([_parrafo(RELLENO_ES, 15)] * 4)


def _escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


def _leer_jsonl(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.work = os.path.join(self.base, "libros")
        self.knowledge = os.path.join(self.base, "knowledge")
        filas = [
            {"id": "loco-es", "titulo": "El loco esoterico", "idioma": "es",
             "familia": "tarot", "prioridad": "alta", "anio": 1910,
             "texto_ocr": "loco-es_djvu.txt", "texto_kb": 40,
             "estado": "texto_verificado"},
            {"id": "the-fool-en", "titulo": "The Fool Abroad", "idioma": "en",
             "familia": "tarot", "prioridad": "alta", "anio": 1920,
             "texto_ocr": "fool_djvu.txt", "texto_kb": 40,
             "estado": "texto_verificado"},
            {"id": "epub-demo", "titulo": "Libro EPUB", "idioma": "es",
             "tema": "tarot", "prioridad": "media", "anio": 2005,
             "fichero": "epubs/epub-demo.epub", "chars": 10000,
             "decision": "usar"},
        ]
        _escribir(os.path.join(self.knowledge, "fuentes_libros.jsonl"),
                  "\n".join(json.dumps(f, ensure_ascii=False) for f in filas))

    def run_pipeline(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = libros_pipeline.ejecutar(**kw)
        return code, buf.getvalue()


class Sequia(Base):
    """T24.1: estructura del orquestador, --dry-run y reanudación."""

    def test_dry_run_no_toca_nada(self):
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 3 libros", salida)
        self.assertIn("pendientes de descarga: 2", salida)
        self.assertFalse(os.path.exists(self.work))

    def test_dry_run_con_max_y_solo_ids(self):
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True, max=1)
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 1 libros", salida)
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True, solo_ids="epub-demo")
        self.assertIn("Inventario: 1 libros", salida)

    def test_etapa_descarga_escribe_crudo_y_registro(self):
        crud = CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               return_value=crud):
            code, _ = self.run_pipeline(
                work_dir=self.work, knowledge_dir=self.knowledge,
                hasta="descarga", pausa=0)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.work, "crudo",
                                                    "the-fool-en.txt")))
        registro = _leer_jsonl(os.path.join(self.work, "fetch.jsonl"))
        self.assertEqual([r["estado"] for r in registro], ["ok"])
        self.assertFalse(os.path.isdir(os.path.join(self.work, "limpio")))

    def test_reanudacion_no_redescarga(self):
        crud = CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               return_value=crud):
            self.run_pipeline(work_dir=self.work,
                              knowledge_dir=self.knowledge,
                              hasta="descarga", pausa=0)
        obtener = mock.patch.object(libros_pipeline.libros_fetch, "_obtener")
        with obtener as mock_obt:
            code, _ = self.run_pipeline(
                work_dir=self.work, knowledge_dir=self.knowledge,
                hasta="descarga", pausa=0)
        mock_obt.assert_not_called()
        self.assertEqual(code, 0)
        registro = _leer_jsonl(os.path.join(self.work, "fetch.jsonl"))
        self.assertEqual(registro[-1]["estado"], "ya_existe")

    def test_etapa_desconocida_devuelve_2(self):
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="teletransporte")
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.work))

    def test_inventario_vacio(self):
        vacio = os.path.join(self.base, "knowledge-vacio")
        os.makedirs(vacio)
        code, salida = self.run_pipeline(work_dir=self.work,
                                         knowledge_dir=vacio,
                                         hasta="informe")
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 0 libros", salida)


if __name__ == "__main__":
    unittest.main()
