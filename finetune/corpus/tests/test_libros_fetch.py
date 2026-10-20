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


class _RespuestaFalsa:
    def __init__(self, datos, url):
        self._datos = datos
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._datos

    def geturl(self):
        return self._url


class _OpenerFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def open(self, url, timeout=None):
        self.llamadas.append(url)
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def _redireccion(url, destino):
    return urllib.error.HTTPError(url, 302, "Found",
                                  {"Location": destino}, None)


class RedireccionesSeguras(unittest.TestCase):
    def _con_opener(self, respuestas):
        opener = _OpenerFalso(respuestas)
        parche = mock.patch.object(libros_fetch.urllib.request,
                                   "build_opener", return_value=opener)
        parche.start()
        self.addCleanup(parche.stop)
        return opener

    def test_acepta_dominios_de_la_lista_blanca(self):
        for url in ("https://archive.org/download/x/y.txt",
                    "https://www.gutenberg.org/files/1/1.txt",
                    "http://es.wikisource.org/wiki/x",
                    "https://datos.bne.es/x",
                    "https://www.cervantesvirtual.com/x"):
            self.assertEqual(libros_fetch.validar_url(url), url)

    def test_rechaza_dominio_externo(self):
        with self.assertRaises(libros_fetch.DescargaInsegura):
            libros_fetch.validar_url("https://evil.com/x.txt")

    def test_rechaza_sufijo_enganoso(self):
        for url in ("https://archive.org.evil.com/x.txt",
                    "https://evilarchive.org/x.txt",
                    "https://archive.org@evil.com/x.txt"):
            with self.assertRaises(libros_fetch.DescargaInsegura):
                libros_fetch.validar_url(url)

    def test_rechaza_credenciales(self):
        for url in ("https://user:pass@archive.org/x.txt",
                    "https://user@archive.org/x.txt"):
            with self.assertRaises(libros_fetch.DescargaInsegura):
                libros_fetch.validar_url(url)

    def test_rechaza_esquema_file(self):
        for url in ("file:///etc/passwd", "ftp://archive.org/x.txt",
                    "javascript:alert(1)"):
            with self.assertRaises(libros_fetch.DescargaInsegura):
                libros_fetch.validar_url(url)

    def test_sigue_redireccion_interna(self):
        self._con_opener([
            _redireccion("https://archive.org/a", "https://archive.org/b"),
            _RespuestaFalsa(b"datos", "https://archive.org/b"),
        ])
        self.assertEqual(libros_fetch._obtener("https://archive.org/a"),
                         b"datos")

    def test_rechaza_redireccion_a_dominio_externo(self):
        self._con_opener([
            _redireccion("https://archive.org/a", "https://evil.com/b"),
        ])
        with self.assertRaises(libros_fetch.DescargaInsegura):
            libros_fetch._obtener("https://archive.org/a")

    def test_rechaza_bucle_de_redirecciones(self):
        opener = self._con_opener([
            _redireccion("https://archive.org/a", "https://archive.org/a"),
        ] * 10)
        with self.assertRaises(libros_fetch.DescargaInsegura):
            libros_fetch._obtener("https://archive.org/a")
        self.assertLessEqual(len(opener.llamadas),
                             libros_fetch.MAX_REDIRECCIONES + 1)

    def test_limita_el_numero_de_saltos(self):
        saltos = [_redireccion("https://archive.org/%d" % i,
                               "https://archive.org/%d" % (i + 1))
                  for i in range(libros_fetch.MAX_REDIRECCIONES + 5)]
        self._con_opener(saltos)
        with self.assertRaises(libros_fetch.DescargaInsegura):
            libros_fetch._obtener("https://archive.org/0")

    def test_valida_la_url_final(self):
        self._con_opener([
            _RespuestaFalsa(b"datos", "https://evil.com/b"),
        ])
        with self.assertRaises(libros_fetch.DescargaInsegura):
            libros_fetch._obtener("https://archive.org/a")

    def test_redireccion_bloqueada_no_se_reintenta(self):
        with mock.patch.object(
                libros_fetch, "_obtener",
                side_effect=libros_fetch.DescargaInsegura("host externo")), \
             mock.patch.object(libros_fetch.time, "sleep") as dormir:
            res = libros_fetch.descargar_libro(LIBRO, self.crudo)
        self.assertEqual(res["estado"], "bloqueado")
        self.assertEqual(res["intentos"], 1)
        dormir.assert_not_called()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.crudo = os.path.join(self.tmp.name, "crudo")


if __name__ == "__main__":
    unittest.main()
