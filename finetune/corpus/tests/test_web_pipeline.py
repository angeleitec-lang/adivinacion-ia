#!/usr/bin/env python3
"""Tests del pipeline web T25: config de sitios en español y orquestador offline."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from urllib.parse import urlparse

RUTA_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json"
)

CAMPOS_REQUERIDOS = ("nombre", "indice", "regex", "dominio", "familia", "prioridad")
FAMILIAS_PERMITIDAS = {"baraja_espanola", "tarot", "astrologia", "numerologia"}
PRIORIDADES = {"alta", "media", "baja"}


def _dominio_normal(netloc: str) -> str:
    return netloc[4:] if netloc.startswith("www.") else netloc


class ConfigSitiosEspanolTests(unittest.TestCase):
    """T25.1: sitios_indice_es.json cumple los requisitos del track."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_CONFIG, encoding="utf-8") as fh:
            cls.config = json.load(fh)
        cls.sitios = cls.config["sitios"]

    def test_minimo_diez_sitios(self):
        self.assertGreaterEqual(len(self.sitios), 10)

    def test_minimo_seis_baraja_espanola(self):
        baraja = [s for s in self.sitios if s["familia"] == "baraja_espanola"]
        self.assertGreaterEqual(len(baraja), 6)

    def test_campos_requeridos(self):
        for sitio in self.sitios:
            for campo in CAMPOS_REQUERIDOS:
                self.assertIn(campo, sitio, f"{sitio.get('nombre')}: falta {campo}")
                self.assertIsInstance(sitio[campo], (str, list))

    def test_familias_y_prioridades_validas(self):
        for sitio in self.sitios:
            self.assertIn(sitio["familia"], FAMILIAS_PERMITIDAS, sitio["nombre"])
            self.assertIn(sitio["prioridad"], PRIORIDADES, sitio["nombre"])

    def test_sin_youtube_ni_libro_ni_biblioteca(self):
        for sitio in self.sitios:
            self.assertNotIn("youtube", sitio["dominio"])
            self.assertNotIn("youtube", sitio["nombre"])
            self.assertNotIn(sitio["familia"], {"libro", "biblioteca"})
            indices = sitio["indice"] if isinstance(sitio["indice"], list) else [sitio["indice"]]
            for url in indices:
                self.assertNotIn("youtube.", url)

    def test_regex_compila(self):
        for sitio in self.sitios:
            try:
                re.compile(sitio["regex"])
            except re.error as exc:
                self.fail(f"{sitio['nombre']}: regex no compila: {exc}")

    def test_indice_str_o_lista_no_vacia(self):
        for sitio in self.sitios:
            idx = sitio["indice"]
            self.assertIsInstance(idx, (str, list), sitio["nombre"])
            urls = idx if isinstance(idx, list) else [idx]
            self.assertGreater(len(urls), 0, sitio["nombre"])
            for url in urls:
                self.assertIsInstance(url, str)
                self.assertTrue(url.startswith("http"), f"{sitio['nombre']}: {url}")

    def test_dominio_coherente_con_indice(self):
        for sitio in self.sitios:
            idx = sitio["indice"]
            urls = idx if isinstance(idx, list) else [idx]
            esperado = _dominio_normal(sitio["dominio"])
            for url in urls:
                netloc = _dominio_normal(urlparse(url).netloc)
                self.assertEqual(
                    netloc,
                    esperado,
                    f"{sitio['nombre']}: indice {url} no pertenece a {esperado}",
                )

    def test_nombres_unicos(self):
        nombres = [s["nombre"] for s in self.sitios]
        self.assertEqual(len(nombres), len(set(nombres)))


if __name__ == "__main__":
    unittest.main()
