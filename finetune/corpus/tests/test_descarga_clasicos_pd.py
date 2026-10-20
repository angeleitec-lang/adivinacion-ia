# Tests de descarga_clasicos_pd: lista blanca, reanudacion y hash (sin red).
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hashlib
import json
import tempfile
import unittest
import urllib.error
from unittest import mock

import descarga_clasicos_pd as descarga

TEXTO_OK = ("Texto clasico de dominio publico con letras suficientes para "
            "superar el umbral minimo. " * 60).encode("utf-8")
FILA = {
    "id": "demo_clasico",
    "titulo": "Demo",
    "familia": "astrologia",
    "prioridad": "alta",
    "licencia_hint": "dominio_publico",
    "verificada": True,
    "formato": "txt",
    "url_texto": "https://archive.org/download/demo/demo_djvu.txt",
    "celdas_que_cubre": ["astrologia"],
}
INVENTARIO = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge",
                          "fuentes_clasicas_pd.jsonl")


def _http_error(codigo):
    return urllib.error.HTTPError("u", codigo, "err", {}, None)


class ListaBlanca(unittest.TestCase):
    def test_dominios_permitidos(self):
        for url in ("https://www.gutenberg.org/cache/epub/1/pg1.txt",
                    "https://archive.org/download/x/y.txt",
                    "https://es.wikisource.org/wiki/X",
                    "https://datos.bne.es/x",
                    "https://hemerotecadigital.bne.es/x",
                    "https://www.cervantesvirtual.com/x"):
            self.assertTrue(descarga.url_permitida(url), url)

    def test_dominios_rechazados(self):
        for url in ("https://example.com/x.txt",
                    "https://archive.org.evil.com/x.txt",
                    "ftp://archive.org/x.txt",
                    "javascript:alert(1)",
                    "https://archive.org@evil.com/x.txt"):
            self.assertFalse(descarga.url_permitida(url), url)


class Descarga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.crudo = os.path.join(self.tmp.name, "crudo")

    def test_descarga_valida_y_hash(self):
        with mock.patch.object(descarga, "_obtener", return_value=TEXTO_OK):
            res = descarga.descargar_candidata(FILA, self.crudo)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["bytes"], len(TEXTO_OK))
        self.assertEqual(res["sha256"], hashlib.sha256(TEXTO_OK).hexdigest())
        with open(os.path.join(self.crudo, "demo_clasico.txt"), "rb") as fh:
            self.assertEqual(fh.read(), TEXTO_OK)

    def test_url_fuera_de_lista_blanca(self):
        fila = dict(FILA, url_texto="https://example.com/robado.txt")
        with mock.patch.object(descarga, "_obtener") as obtener:
            with self.assertRaises(ValueError):
                descarga.descargar_candidata(fila, self.crudo)
        obtener.assert_not_called()

    def test_reanudacion_no_vuelve_a_descargar(self):
        with mock.patch.object(descarga, "_obtener", return_value=TEXTO_OK):
            descarga.descargar_candidata(FILA, self.crudo)
        with mock.patch.object(descarga, "_obtener",
                              side_effect=AssertionError("no debe llamarse")):
            res = descarga.descargar_candidata(FILA, self.crudo)
        self.assertEqual(res["estado"], "ya_existe")
        self.assertEqual(res["intentos"], 0)

    def test_archivo_existente_invalido_no_se_pisa(self):
        os.makedirs(self.crudo)
        ruta = os.path.join(self.crudo, "demo_clasico.txt")
        with open(ruta, "wb") as fh:
            fh.write(b"<html>error</html>")
        with mock.patch.object(descarga, "_obtener") as obtener:
            res = descarga.descargar_candidata(FILA, self.crudo)
        self.assertEqual(res["estado"], "ya_existe_invalido")
        obtener.assert_not_called()
        with open(ruta, "rb") as fh:
            self.assertEqual(fh.read(), b"<html>error</html>")

    def test_429_repetido_para_la_pasada(self):
        with mock.patch.object(descarga, "_obtener",
                              side_effect=[_http_error(429),
                                           _http_error(429)]):
            with mock.patch.object(descarga.time, "sleep"):
                with self.assertRaises(descarga.ParadaLimitada):
                    descarga.descargar_candidata(FILA, self.crudo)

    def test_html_se_convierte_a_texto(self):
        cuerpo = b"<p>Uno &amp; dos</p><p>Otra linea</p>" * 80
        pagina = (b"<html><head><title>t</title><style>x{}</style></head>"
                  b"<body><script>malo()</script>" + cuerpo + b"</body></html>")
        fila = dict(FILA, formato="html",
                    url_texto="https://es.wikisource.org/wiki/X")
        with mock.patch.object(descarga, "_obtener", return_value=pagina):
            res = descarga.descargar_candidata(fila, self.crudo)
        self.assertEqual(res["estado"], "ok")
        with open(os.path.join(self.crudo, "demo_clasico.txt"), "rb") as fh:
            texto = fh.read().decode("utf-8")
        self.assertIn("Uno & dos", texto)
        self.assertNotIn("<p>", texto)
        self.assertNotIn("malo()", texto)


class Seleccion(unittest.TestCase):
    def test_prioriza_alta_y_respeta_maximo(self):
        filas = [
            dict(FILA, id="baja", prioridad="baja"),
            dict(FILA, id="alta1", prioridad="alta"),
            dict(FILA, id="media", prioridad="media"),
            dict(FILA, id="alta2", prioridad="alta"),
        ]
        elegidas = descarga.seleccionar(filas, maximo=2)
        self.assertEqual([f["id"] for f in elegidas], ["alta1", "alta2"])

    def test_descarta_no_verificadas(self):
        filas = [dict(FILA, id="mala", verificada=False)]
        self.assertEqual(descarga.seleccionar(filas), [])


class InventarioReal(unittest.TestCase):
    def test_esquema_y_minimo_de_fuentes(self):
        filas = descarga.cargar_candidatas(INVENTARIO)
        self.assertGreaterEqual(len(filas), 25)
        ids = set()
        for fila in filas:
            for campo in ("id", "titulo", "autor", "anio", "idioma", "familia",
                          "url_texto", "formato", "licencia_hint", "prioridad",
                          "celdas_que_cubre", "nota"):
                self.assertIn(campo, fila, fila.get("id"))
            self.assertIn(fila["familia"], ("astrologia", "numerologia", "baraja"))
            self.assertIn(fila["prioridad"], ("alta", "media", "baja"))
            self.assertEqual(fila["licencia_hint"], "dominio_publico")
            self.assertIsInstance(fila["celdas_que_cubre"], list)
            self.assertNotIn(fila["id"], ids)
            ids.add(fila["id"])
            self.assertTrue(descarga.url_permitida(fila["url_texto"]),
                            fila["url_texto"])
            if fila.get("estado") == "texto_verificado":
                self.assertTrue(fila["verificada"])
                self.assertIn(fila["http"], (200, 206))
        altas = [f for f in filas if f["prioridad"] == "alta"]
        self.assertGreaterEqual(len(altas), 10)


if __name__ == "__main__":
    unittest.main()
