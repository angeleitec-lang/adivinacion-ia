#!/usr/bin/env python3
"""Tests de web_indices: descubrimiento de páginas desde índices configurables."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
from web_indices import (
    cargar_config,
    seguir_indice,
    _extraer_enlaces,
    _filtrar_por_regex,
    _deduplicar_urls,
    _mismo_dominio,
)


class UtilidadesTests(unittest.TestCase):
    def test_mismo_dominio(self):
        self.assertTrue(_mismo_dominio("https://biddytarot.com/page", "biddytarot.com"))
        self.assertTrue(_mismo_dominio("https://www.biddytarot.com/page", "biddytarot.com"))
        self.assertFalse(_mismo_dominio("https://otro.com/page", "biddytarot.com"))

    def test_extraer_enlaces(self):
        html = """<html><body>
        <a href="/tarot-card-meanings/the-fool">The Fool</a>
        <a href="https://biddytarot.com/tarot-card-meanings/the-magician">The Magician</a>
        <a href="https://otro.com/page">Externo</a>
        <a href="#anchor">Anchor</a>
        </body></html>"""
        base = "https://biddytarot.com/tarot-card-meanings/"
        urls = _extraer_enlaces(html, base, "biddytarot.com")
        self.assertIn("https://biddytarot.com/tarot-card-meanings/the-fool", urls)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/the-magician", urls)
        self.assertNotIn("https://otro.com/page", urls)

    def test_filtrar_por_regex(self):
        urls = [
            "https://biddytarot.com/tarot-card-meanings/major-arcana/the-fool",
            "https://biddytarot.com/tarot-card-meanings/minor-arcana/ace-of-wands",
            "https://biddytarot.com/blog/post",
            "https://otro.com/tarot-card-meanings/major-arcana",
        ]
        filtradas = _filtrar_por_regex(urls, "/tarot-card-meanings/(major|minor)-arcana/", "biddytarot.com")
        self.assertEqual(len(filtradas), 2)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/major-arcana/the-fool", filtradas)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/minor-arcana/ace-of-wands", filtradas)

    def test_deduplicar_urls(self):
        urls = ["a", "b", "a", "c", "b"]
        self.assertEqual(_deduplicar_urls(urls), ["a", "b", "c"])


class SeguirIndiceTests(unittest.TestCase):
    def setUp(self):
        # HTML simulado de página índice
        self.html_indice = """<html><body>
        <a href="/tarot-card-meanings/major-arcana/the-fool">The Fool</a>
        <a href="/tarot-card-meanings/major-arcana/the-magician">The Magician</a>
        <a href="/tarot-card-meanings/minor-arcana/ace-of-wands">Ace of Wands</a>
        <a href="/blog/post">Blog Post</a>
        <a href="https://otro.com/page">Externo</a>
        </body></html>"""

    def _crear_cliente_simulado(self, html: str, estado: str = "ok"):
        class ClienteSimulado:
            def __init__(self, html, estado):
                self.html = html
                self.estado = estado
            def get(self, url):
                return {"estado": self.estado, "html": self.html, "status": 200, "bytes": len(self.html)}
        return ClienteSimulado(html, estado)

    def test_filtrado_regex_y_dominio(self):
        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": "https://biddytarot.com/tarot-card-meanings/",
            "regex": "/tarot-card-meanings/(major|minor)-arcana/",
            "dominio": "biddytarot.com",
            "familia": "tarot",
            "prioridad": "alta",
        }
        cliente = self._crear_cliente_simulado(self.html_indice)
        urls = seguir_indice(sitio_cfg, cliente, limite=50)
        self.assertEqual(len(urls), 3)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/major-arcana/the-fool", urls)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/major-arcana/the-magician", urls)
        self.assertIn("https://biddytarot.com/tarot-card-meanings/minor-arcana/ace-of-wands", urls)
        # No debe incluir /blog/post ni externos
        self.assertNotIn("https://biddytarot.com/blog/post", urls)

    def test_limite_recorta(self):
        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": "https://biddytarot.com/tarot-card-meanings/",
            "regex": "/tarot-card-meanings/",
            "dominio": "biddytarot.com",
        }
        # HTML con muchos enlaces
        html = "<html><body>" + "".join(f'<a href="/tarot-card-meanings/card-{i}">Card {i}</a>' for i in range(20)) + "</body></html>"
        cliente = self._crear_cliente_simulado(html)
        urls = seguir_indice(sitio_cfg, cliente, limite=5)
        self.assertEqual(len(urls), 5)

    def test_estado_no_ok_retorna_vacio(self):
        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": "https://biddytarot.com/tarot-card-meanings/",
            "regex": "/tarot-card-meanings/",
            "dominio": "biddytarot.com",
        }
        cliente = self._crear_cliente_simulado("", estado="error")
        urls = seguir_indice(sitio_cfg, cliente, limite=50)
        self.assertEqual(urls, [])

    def test_sin_html_retorna_vacio(self):
        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": "https://biddytarot.com/tarot-card-meanings/",
            "regex": "/tarot-card-meanings/",
            "dominio": "biddytarot.com",
        }
        class ClienteVacio:
            def get(self, url):
                return {"estado": "ok", "html": None, "status": 200, "bytes": 0}
        urls = seguir_indice(sitio_cfg, ClienteVacio(), limite=50)
        self.assertEqual(urls, [])


class CargarConfigTests(unittest.TestCase):
    def test_carga_config_valida(self):
        config = cargar_config()
        self.assertIn("sitios", config)
        self.assertEqual(len(config["sitios"]), 6)
        for sitio in config["sitios"]:
            self.assertIn("nombre", sitio)
            self.assertIn("indice", sitio)
            self.assertIn("regex", sitio)
            self.assertIn("dominio", sitio)
            self.assertIn("familia", sitio)
            self.assertIn("prioridad", sitio)


if __name__ == "__main__":
    unittest.main()
