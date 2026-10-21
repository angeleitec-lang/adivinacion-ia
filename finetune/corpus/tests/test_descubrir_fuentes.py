#!/usr/bin/env python3
"""Tests de descubrir_fuentes (T74) con cliente HTTP simulado."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import descubrir_fuentes as df  # noqa: E402


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def get(self, url):
        self.llamadas.append(url)
        return self.respuestas.get(
            url, {"estado": "error", "status": 404, "html": "", "bytes": 0}
        )


def _sitemap(urls):
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


def _index(subs):
    locs = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in subs)
    return f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</sitemapindex>'


class TestUtilidades(unittest.TestCase):
    def test_norm_dominio(self):
        self.assertEqual(df.norm_dominio("WWW.Example.COM"), "example.com")
        self.assertEqual(df.norm_dominio("example.com:8080"), "example.com")
        self.assertEqual(df.norm_dominio("sub.example.com"), "sub.example.com")

    def test_extraer_locs(self):
        self.assertEqual(df.extraer_locs(_sitemap(["http://a.com/1", "http://a.com/2"])),
                         ["http://a.com/1", "http://a.com/2"])

    def test_es_sitemap_index(self):
        self.assertTrue(df.es_sitemap_index(_index(["http://a.com/s1.xml"])))
        self.assertFalse(df.es_sitemap_index(_sitemap(["http://a.com/1"])))


class TestDescubrirSitemap(unittest.TestCase):
    def test_filtra_por_patron_y_dominio(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({
            sm: {"estado": "ok", "html": _sitemap([
                "https://ej.com/baraja/as-de-oro",
                "https://ej.com/baraja/dos-de-copas",
                "https://ej.com/horoscopo/aries",
                "https://otro.com/baraja/as-de-oro",
            ])},
        })
        urls = df.descubrir_desde_sitemap(cli, sm, r"ej\.com/baraja/", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(urls, [
            "https://ej.com/baraja/as-de-oro",
            "https://ej.com/baraja/dos-de-copas",
        ])

    def test_recursion_en_indice(self):
        idx = "https://ej.com/sitemap_index.xml"
        cli = ClienteFalso({
            idx: {"estado": "ok", "html": _index([
                "https://ej.com/sitemap-1.xml",
                "https://ej.com/sitemap-2.xml",
            ])},
            "https://ej.com/sitemap-1.xml": {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/1",
            ])},
            "https://ej.com/sitemap-2.xml": {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/2",
            ])},
        })
        urls = df.descubrir_desde_sitemap(cli, idx, r"numerolog", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(sorted(urls), [
            "https://ej.com/numerologia/1",
            "https://ej.com/numerologia/2",
        ])

    def test_robots_prohibido_se_excluye(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({
            sm: {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/permitido",
                "https://ej.com/numerologia/prohibido",
            ])},
        })
        robots = lambda u: "prohibido" not in u
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                         robots=robots, sleep=lambda s: None)
        self.assertEqual(urls, ["https://ej.com/numerologia/permitido"])

    def test_sitemap_404_devuelve_vacio(self):
        cli = ClienteFalso({})
        urls = df.descubrir_desde_sitemap(cli, "https://ej.com/sitemap.xml",
                                         r".", limite=50, sleep=lambda s: None)
        self.assertEqual(urls, [])

    def test_limite_se_respeta(self):
        sm = "https://ej.com/sitemap.xml"
        muchas = [f"https://ej.com/numerologia/{i}" for i in range(100)]
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap(muchas)}})
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=10,
                                         sleep=lambda s: None)
        self.assertEqual(len(urls), 10)

    def test_tasa_sleep_entre_peticiones(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1"])}})
        llamadas_sleep = []
        df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                   sleep=lambda s: llamadas_sleep.append(s))
        # una petición al sitemap → al menos un sleep de cortesía
        self.assertGreaterEqual(len(llamadas_sleep), 1)
        self.assertIn(1.2, llamadas_sleep)

    def test_deduplicado(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/x",
            "https://ej.com/numerologia/x",
        ])}})
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(urls, ["https://ej.com/numerologia/x"])


class TestFabricaRobots(unittest.TestCase):
    def test_permite_cuando_no_robots(self):
        cli = ClienteFalso({})  # robots.txt 404
        robots = df.fabrica_robots(cli, "ej.com", sleep=lambda s: None)
        self.assertTrue(robots("https://ej.com/cualquier/cosa"))

    def test_respeta_disallow(self):
        robots_txt = "User-agent: *\nDisallow: /privado/\n"
        cli = ClienteFalso({
            "https://ej.com/robots.txt": {"estado": "ok", "html": robots_txt},
        })
        robots = df.fabrica_robots(cli, "ej.com", sleep=lambda s: None)
        self.assertFalse(robots("https://ej.com/privado/secreto"))
        self.assertTrue(robots("https://ej.com/numerologia/1"))


class TestConstruirPlan(unittest.TestCase):
    def test_dominio_bloqueado_se_omite(self):
        fuentes = [{
            "dominio": "reddit.com",
            "sitemap": "https://reddit.com/sitemap.xml",
            "patron": r".",
            "familia": "numerologia",
        }]
        cli = ClienteFalso({})
        por = df.construir_plan(fuentes, cli, sleep=lambda s: None)
        self.assertEqual(por, {})
        self.assertNotIn("https://reddit.com/sitemap.xml", cli.llamadas)

    def test_agrupa_por_familia(self):
        sm = "https://ej.com/sitemap.xml"
        fuentes = [{
            "dominio": "ej.com",
            "sitemap": sm,
            "patron": r"ej\.com/(numerologia|baraja)/",
            "familia": "numerologia",
        }]
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1",
            "https://ej.com/baraja/2",
        ])}})
        por = df.construir_plan(fuentes, cli, sleep=lambda s: None)
        self.assertEqual(por["numerologia"], [
            "https://ej.com/numerologia/1",
            "https://ej.com/baraja/2",
        ])


class TestEscribirPlan(unittest.TestCase):
    def test_formato_compatible(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            total = df.escribir_plan(
                {"numerologia": ["https://a.com/1", "https://a.com/2"],
                 "baraja_espanola": ["https://b.com/3"]},
                ruta,
            )
            self.assertEqual(total, 3)
            with open(ruta, encoding="utf-8") as fh:
                lineas = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(len(lineas), 2)
            for entrada in lineas:
                self.assertIn("entidad_id", entrada)
                self.assertIn("familia", entrada)
                self.assertIn("nombre", entrada)
                self.assertIsInstance(entrada["urls_candidatas"], list)
                for c in entrada["urls_candidatas"]:
                    self.assertIn("url", c)
            familias = sorted(e["familia"] for e in lineas)
            self.assertEqual(familias, ["baraja_espanola", "numerologia"])

    def test_familia_vacia_no_se_escribe(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            total = df.escribir_plan({"numerologia": []}, ruta)
            self.assertEqual(total, 0)
            with open(ruta, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "")


if __name__ == "__main__":
    unittest.main()
