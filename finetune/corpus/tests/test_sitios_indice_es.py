"""Tests de estructura de sitios_indice_es.json (T26): índices de sitios en español."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

RUTA = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json")

FAMILIAS_VALIDAS = {"baraja_espanola", "tarot", "astrologia", "numerologia"}
PRIORIDADES_VALIDAS = {"alta", "media", "baja"}
CAMPOS_OBLIGATORIOS = {
    "nombre", "tipo", "indice", "regex", "dominio", "familia", "prioridad", "nota"}

with open(RUTA, encoding="utf-8") as _f:
    DATOS = json.load(_f)

SITIOS = DATOS["sitios"]


def _sitio(dominio):
    for s in SITIOS:
        if s["dominio"] == dominio:
            return s
    raise AssertionError(f"sitio no encontrado: {dominio}")


class TestEstructura(unittest.TestCase):
    def test_tiene_descripcion_y_sitios(self):
        self.assertIn("descripcion", DATOS)
        self.assertIsInstance(DATOS["sitios"], list)
        self.assertGreaterEqual(len(SITIOS), 26)

    def test_campos_obligatorios(self):
        for s in SITIOS:
            faltan = CAMPOS_OBLIGATORIOS - set(s)
            self.assertFalse(faltan, f"{s.get('dominio')} sin campos: {faltan}")

    def test_regex_compilan(self):
        for s in SITIOS:
            try:
                re.compile(s["regex"])
            except re.error as exc:
                self.fail(f"regex inválida en {s['dominio']}: {exc}")

    def test_familia_valida(self):
        for s in SITIOS:
            self.assertIn(s["familia"], FAMILIAS_VALIDAS, s["dominio"])

    def test_prioridad_valida(self):
        for s in SITIOS:
            self.assertIn(s["prioridad"], PRIORIDADES_VALIDAS, s["dominio"])

    def test_indice_no_vacio_y_https(self):
        for s in SITIOS:
            self.assertTrue(s["indice"], f"{s['dominio']} sin índice")
            for u in s["indice"]:
                self.assertTrue(u.startswith("https://"), f"{s['dominio']}: {u} no es https")

    def test_sin_dominios_duplicados(self):
        dominios = [s["dominio"] for s in SITIOS]
        self.assertEqual(len(dominios), len(set(dominios)))

    def test_dominio_coincide_con_nombre(self):
        for s in SITIOS:
            self.assertEqual(s["nombre"], s["dominio"])


class TestCoberturaT26(unittest.TestCase):
    def test_al_menos_12_astrologia_o_numerologia(self):
        nuevos = [s for s in SITIOS if s["familia"] in ("astrologia", "numerologia")]
        self.assertGreaterEqual(len(nuevos), 12)

    def test_los_12_sitios_t26_presentes(self):
        esperados = {
            "grancosmos.com", "mercurioretrogrado.com", "astrolink.com",
            "escuelamaia.com", "mundivia.es", "es.astrologyk.com",
            "eight-leaves.de", "moonoscope.com", "tarot.ac", "loveplay.io",
            "horoscopelogic.com", "es.astro-seek.com"}
        presentes = {s["dominio"] for s in SITIOS}
        self.assertTrue(esperados.issubset(presentes),
                       esperados - presentes)


class TestRegexForotarot(unittest.TestCase):
    def setUp(self):
        self.rx = re.compile(_sitio("forotarot.net")["regex"])

    def test_excluye_meta_hilos(self):
        meta = [
            "/tema-Sistema-de-puntos",
            "/tema-Normas-para-recibir-interpretaciones-%C2%A1Leer-antes-de-publicar",
            "/tema-minimo-de-puntos-parar-recibir-interpretaciones",
            "/tema-normas-para-recibir-interpretaciones-leer-antes-de-publicar",
        ]
        for m in meta:
            self.assertIsNone(self.rx.search(m), m)

    def test_incluye_hilos_de_lectura(self):
        lectura = [
            "/tema-interpretacion-de-mi-tirada",
            "/tema-combinacion-de-oros",
            "/tema-tirada-de-amor",
        ]
        for x in lectura:
            self.assertIsNotNone(self.rx.search(x), x)


class TestRegexDescubrenMuestras(unittest.TestCase):
    def test_grancosmos_match(self):
        rx = re.compile(_sitio("grancosmos.com")["regex"])
        self.assertIsNotNone(rx.search("https://grancosmos.com/guia/sol-en-aries"))

    def test_astrolink_match(self):
        rx = re.compile(_sitio("astrolink.com")["regex"])
        self.assertIsNotNone(
            rx.search("https://www.astrolink.com/es/interpretacion/jupiter-en-acuario"))

    def test_horoscopelogic_match(self):
        rx = re.compile(_sitio("horoscopelogic.com")["regex"])
        self.assertIsNotNone(
            rx.search("https://horoscopelogic.com/es/expression-number-11"))

    def test_escuelamaia_excluye_hub(self):
        rx = re.compile(_sitio("escuelamaia.com")["regex"])
        self.assertIsNotNone(rx.search("https://escuelamaia.com/jupiter-en-aries/"))
        self.assertIsNone(rx.search("https://escuelamaia.com/jupiter-en-astrologia/"))


if __name__ == "__main__":
    unittest.main()
