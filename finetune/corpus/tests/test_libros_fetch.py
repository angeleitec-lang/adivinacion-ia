# Tests de libros_fetch: descarga reanudable y educada de archive.org (offline).
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import tempfile
import unittest
import urllib.error
from unittest import mock

import libros_fetch

LIBRO = {"id": "libro-demo", "url": "https://archive.org/download/libro-demo/x.txt"}
TEXTO_OK = ("Esto es un texto valido en espanol con letras suficientes. "
            * 1200).encode("utf-8")  # > 30 KB


def _http_error(codigo):
    return urllib.error.HTTPError("u", codigo, "err", {}, None)


class Descarga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.crudo = os.path.join(self.tmp.name, "crudo")

    def test_descarga_valida(self):
        with mock.patch.object(libros_fetch, "_obtener", return_value=TEXTO_OK):
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["intentos"], 1)
        self.assertGreater(res["bytes"], 30 * 1024)
        self.assertTrue(os.path.exists(os.path.join(self.crudo, "libro-demo.txt")))

    def test_no_redescarga_lo_existente_valido(self):
        os.makedirs(self.crudo)
        with open(os.path.join(self.crudo, "libro-demo.txt"), "wb") as fh:
            fh.write(TEXTO_OK)
        with mock.patch.object(libros_fetch, "_obtener") as obt:
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        obt.assert_not_called()
        self.assertEqual(res["estado"], "ya_existe")

    def test_invalido_por_tamano(self):
        with mock.patch.object(libros_fetch, "_obtener", return_value=b"corto"), \
             mock.patch.object(libros_fetch.time, "sleep"):
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        self.assertEqual(res["estado"], "invalido")
        self.assertFalse(os.path.exists(os.path.join(self.crudo, "libro-demo.txt")))

    def test_invalido_por_html_de_error(self):
        html = (b"<html><head><title>Error</title></head><body>"
                + b"Request failed badly. " * 3000 + b"</body></html>")
        with mock.patch.object(libros_fetch, "_obtener", return_value=html), \
             mock.patch.object(libros_fetch.time, "sleep"):
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        self.assertEqual(res["estado"], "invalido")

    def test_reintentos_con_espera_exponencial(self):
        llamadas = []

        def fake(url):
            llamadas.append(url)
            if len(llamadas) < 3:
                raise urllib.error.URLError("caida")
            return TEXTO_OK

        dormidas = []
        with mock.patch.object(libros_fetch, "_obtener", side_effect=fake), \
             mock.patch.object(libros_fetch.time, "sleep", side_effect=dormidas.append):
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["intentos"], 3)
        self.assertGreater(len(dormidas), 1)
        self.assertLess(dormidas[0], dormidas[1])

    def test_parada_limite_429(self):
        with mock.patch.object(libros_fetch, "_obtener",
                              side_effect=lambda u: (_ for _ in ()).throw(
                                  _http_error(429))), \
             mock.patch.object(libros_fetch.time, "sleep"):
            with self.assertRaises(libros_fetch.ParadaLimitada):
                libros_fetch.descargar_libro(LIBRO, self.crudo)

    def test_fetch_todos_registra_y_pausa(self):
        libros = [LIBRO,
                 {"id": "otro", "url": "https://archive.org/download/otro/y.txt"}]
        dormidas = []
        with mock.patch.object(libros_fetch, "_obtener", return_value=TEXTO_OK), \
             mock.patch.object(libros_fetch.time, "sleep", side_effect=dormidas.append):
            rc = libros_fetch.fetch_todos(libros, self.tmp.name, pausa=2.5)
        self.assertEqual(rc, 0)
        self.assertIn(2.5, dormidas)
        registro = [json.loads(l) for l in
                   open(os.path.join(self.tmp.name, "fetch.jsonl"), encoding="utf-8")]
        self.assertEqual(len(registro), 2)
        for fila in registro:
            self.assertEqual(set(fila.keys()), {"id", "estado", "bytes", "intentos"})
            self.assertEqual(fila["estado"], "ok")

    def test_fetch_todos_devuelve_3_con_429(self):
        with mock.patch.object(libros_fetch, "_obtener",
                              side_effect=lambda u: (_ for _ in ()).throw(
                                  _http_error(429))), \
             mock.patch.object(libros_fetch.time, "sleep"):
            rc = libros_fetch.fetch_todos([LIBRO], self.tmp.name)
        self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main()
