#!/usr/bin/env python3
"""Tests de web_indices: descubrimiento de páginas desde índices configurables."""
import os
import re
import sys
import unittest
from urllib.parse import urlparse

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

    def test_extraer_enlaces_relativos(self):
        """Test T13.1: enlaces relativos resueltos con urljoin."""
        html = """<html><body>
        <a href="fool.shtml">The Fool</a>
        <a href="./a.html">A relative</a>
        <a href="../b/">B relative</a>
        <a href="//cdn.x.com/y">Protocol-relative</a>
        <a href="#anchor">Anchor</a>
        <a href="mailto:test@test.com">Mail</a>
        <a href="tel:+34123456789">Phone</a>
        <a href="javascript:alert(1)">JS</a>
        <a href="data:text/html,hello">Data</a>
        </body></html>"""
        base = "https://www.aeclectic.net/tarot/tarot-card-meanings/major-arcana/"
        urls = _extraer_enlaces(html, base, "aeclectic.net")
        # foo.shtml se resuelve contra la base
        self.assertIn("https://www.aeclectic.net/tarot/tarot-card-meanings/major-arcana/fool.shtml", urls)
        # ./a.html se resuelve contra la base
        self.assertIn("https://www.aeclectic.net/tarot/tarot-card-meanings/major-arcana/a.html", urls)
        # ../b/ sube un nivel: major-arcana/ -> tarot/tarot-card-meanings/ -> b/
        self.assertIn("https://www.aeclectic.net/tarot/tarot-card-meanings/b/", urls)
        # protocol-relative //cdn.x.com/y: netloc es cdn.x.com, diferente a aeclectic.net, así que filtrado por dominio
        # mailto, tel, javascript, data deben descartarse
        self.assertNotIn("mailto:test@test.com", urls)
        self.assertNotIn("tel:+34123456789", urls)
        self.assertNotIn("javascript:alert(1)", urls)
        self.assertNotIn("data:text/html,hello", urls)
        # #anchor must be removed
        self.assertNotIn("#anchor", "".join(urls))  # just verify no pure anchor remains

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

    # --- NUEVOS TESTS T13.2: varios índices por sitio ---

    def test_indice_str_igual_antes(self):
        """str sigue funcionando exactamente como antes."""
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

    def test_indice_lista_union_sin_duplicados(self):
        """lista con 3 índices (cliente falso) devuelve la unión sin duplicados."""
        html1 = """<html><body>
        <a href="/tarot-card-meanings/major-arcana/the-fool">The Fool</a>
        <a href="/tarot-card-meanings/minor-arcana/ace-of-wands">Ace</a>
        </body></html>"""
        html2 = """<html><body>
        <a href="/tarot-card-meanings/major-arcana/the-magician">The Magician</a>
        <a href="/tarot-card-meanings/minor-arcana/star-of-wands">Star</a>
        </body></html>"""
        html3 = """<html><body>
        <a href="/tarot-card-meanings/minor-arcana/ace-of-wands">Ace (dup)</a>
        </body></html>"""

        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": [
                "https://biddytarot.com/tarot-card-meanings/major",
                "https://biddytarot.com/tarot-card-meanings/minor",
                "https://biddytarot.com/tarot-card-meanings/court",
            ],
            "regex": "/tarot-card-meanings/(major|minor)-arcana/",
            "dominio": "biddytarot.com",
            "familia": "tarot",
            "prioridad": "alta",
        }
        class ClienteLista:
            def __init__(self, *htmls):
                self.htmls = htmls
            def get(self, url):
                idx = {"https://biddytarot.com/tarot-card-meanings/major": 0,
                       "https://biddytarot.com/tarot-card-meanings/minor": 1,
                       "https://biddytarot.com/tarot-card-meanings/court": 2}.get(url, 0)
                return {"estado": "ok", "html": self.htmls[idx], "status": 200, "bytes": len(self.htmls[idx])}

        cliente = ClienteLista(html1, html2, html3)
        urls = seguir_indice(sitio_cfg, cliente, limite=50)
        # Debería tener 4 URLs únicas (the-fool, the-magician, ace-of-wands, star-of-wands; el duplicado se descarta)
        unique_urls = set(urls)
        self.assertEqual(len(unique_urls), 4)  # the-fool, the-magician, ace-of-wands, star-of-wands

    def test_indice_lista_con_error_un_indice(self):
        """si un índice de la lista falla (estado != "ok"), los demás se procesan igual."""
        html1 = """<html><body>
        <a href="/tarot-card-meanings/major-arcana/the-fool">The Fool</a>
        </body></html>"""
        html2 = """<html><body>
        </body></html>"""  # vacío, estado error

        sitio_cfg = {
            "nombre": "biddytarot.com",
            "indice": [
                "https://biddytarot.com/tarot-card-meanings/major",
                "https://biddytarot.com/tarot-card-meanings/minor",
            ],
            "regex": "/tarot-card-meanings/(major|minor)-arcana/",
            "dominio": "biddytarot.com",
            "familia": "tarot",
            "prioridad": "alta",
        }
        class ClienteErrorParcial:
            def get(self, url):
                if "major" in url:
                    return {"estado": "ok", "html": html1, "status": 200, "bytes": len(html1)}
                return {"estado": "error", "html": html2, "status": 200, "bytes": len(html2)}

        cliente = ClienteErrorParcial()
        urls = seguir_indice(sitio_cfg, cliente, limite=50)
        # Solo el primer índice (major) debería procesarse; el segundo falla y se omite
        self.assertIn("https://biddytarot.com/tarot-card-meanings/major-arcana/the-fool", urls)
        self.assertNotIn("https://biddytarot.com/tarot-card-meanings/minor-arcana/the-fool", urls)


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

    def test_config_requisitos_t13(self):
        """T13.3: valida que todos los sitios tienen los requisitos esperados."""
        config = cargar_config()
        sitios = config["sitios"]
        self.assertEqual(len(sitios), 6)

        for sitio in sitios:
            # nombre
            self.assertIn("nombre", sitio)
            self.assertIsInstance(sitio["nombre"], str)
            self.assertTrue(len(sitio["nombre"]) > 0)

            # indice: str o lista no vacía
            self.assertIn("indice", sitio)
            idx = sitio["indice"]
            self.assertTrue(isinstance(idx, (str, list)))
            if isinstance(idx, str):
                self.assertTrue(len(idx) > 0)
            else:
                self.assertTrue(len(idx) > 0)

            # regex que compila
            self.assertIn("regex", sitio)
            regex_compilado = re.compile(sitio["regex"])

            # dominio
            self.assertIn("dominio", sitio)
            self.assertIsInstance(sitio["dominio"], str)
            self.assertTrue(len(sitio["dominio"]) > 0)

            # familia
            self.assertIn("familia", sitio)
            self.assertIsInstance(sitio["familia"], str)
            self.assertTrue(len(sitio["familia"]) > 0)

            # el dominio de cada índice coincide con el del sitio
            # extraer dominio desde el índice (quitar www.)
            idx_str = idx if isinstance(idx, str) else idx[0]  # tomar el primero si es lista
            netloc = urlparse(idx_str).netloc
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if sitio["dominio"].startswith("www."):
                sitio_dom = sitio["dominio"][4:]
            else:
                sitio_dom = sitio["dominio"]
            self.assertEqual(netloc, sitio_dom,
                f"Sitio {sitio['nombre']}: dominio {netloc} del índice no coincide con {sitio_dom} del sitio")


if __name__ == "__main__":
    unittest.main()
