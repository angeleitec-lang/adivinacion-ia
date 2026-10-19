"""Tests de estructura de sitios_indice_es_lecturas.json (T28): fuentes ES de lecturas resueltas."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
RUTA = os.path.join(BASE, "sitios_indice_es_lecturas.json")
RUTA_JSONL = os.path.join(BASE, "fuentes_web_es_lecturas.jsonl")
RUTA_ES = os.path.join(BASE, "sitios_indice_es.json")

FAMILIAS_VALIDAS = {"baraja_espanola", "tarot"}
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
        self.assertGreaterEqual(len(SITIOS), 10)

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

    def test_sin_duplicados_con_sitios_indice_es(self):
        with open(RUTA_ES, encoding="utf-8") as f:
            otros = json.load(f)
        dominios_otros = {s["dominio"] for s in otros["sitios"]}
        dominios_nuevos = {s["dominio"] for s in SITIOS}
        self.assertFalse(dominios_nuevos & dominios_otros,
                        f"duplicados con sitios_indice_es.json: {dominios_nuevos & dominios_otros}")


class TestRegexAtraparanMuestras(unittest.TestCase):
    """Cada regex debe atrapar las URLs de ejemplo verificadas en el sondeo T28."""

    EJEMPLOS = {
        "cartastarotsagrado.com": [
            "https://cartastarotsagrado.com/tiradas/cruz-celta/",
            "https://cartastarotsagrado.com/tiradas/amor/"],
        "tarotveraluna.com": [
            "https://tarotveraluna.com/tirada-de-la-herradura/",
            "https://tarotveraluna.com/cruz-celta-tarot-posiciones/",
            "https://tarotveraluna.com/tarot-volvera/",
            "https://tarotveraluna.com/tarot-del-trabajo/"],
        "elvitarot.com": [
            "https://elvitarot.com/es/blog/cruz-celta-tirada-tarot",
            "https://elvitarot.com/es/blog/guia-tirada-tres-cartas"],
        "astroideal.com": [
            "https://astroideal.com/blog/caso-real-reconciliacion-pareja-tarot",
            "https://astroideal.com/blog/combinaciones-arcanos-menores-ejemplos"],
        "mi.astrocentro.com": [
            "https://mi.astrocentro.com/tarot/articulo/cruz-celta-amor",
            "https://mi.astrocentro.com/tarot/tarot-espanol/metodos-de-tirada"],
        "tiradadecartas.com.ar": [
            "https://tiradadecartas.com.ar/tirada-de-cartas-espanolas/amor",
            "https://tiradadecartas.com.ar/tirada-de-tarot/amor"],
        "tarotnova.app": [
            "https://tarotnova.app/es/tiradas/12-casas",
            "https://tarotnova.app/es/blog/tarot-amor-interpretar-tirada"],
        "mysticanswer.com": [
            "https://mysticanswer.com/es/blog/tirada-de-3-cartas-tarot-guia",
            "https://mysticanswer.com/mx/blog/pareja-pide-espacio-tirada-tarot"],
        "tarotysalud.com": [
            "https://tarotysalud.com/como-interpretar-una-tirada-de-tarot/",
            "https://tarotysalud.com/interpretacion-tiradas-saber-si-volvera/"],
        "tarotdetiziana.com": [
            "https://tarotdetiziana.com/lecturas-de-tarot-con-3-cartas/",
            "https://tarotdetiziana.com/combinaciones-de-cartas-en-el-tarot/"],
    }

    def test_regex_atrapan_ejemplos(self):
        for dominio, urls in self.EJEMPLOS.items():
            rx = re.compile(_sitio(dominio)["regex"])
            for u in urls:
                self.assertIsNotNone(rx.search(u), f"{dominio}: regex no atrapa {u}")

    def test_regex_excluyen_rutas_no_lectura(self):
        exclusiones = {
            "tarotveraluna.com": ["https://tarotveraluna.com/cartas/el-loco/"],
            "tiradadecartas.com.ar": [
                "https://tiradadecartas.com.ar/_next/static/chunks/app.js",
                "https://tiradadecartas.com.ar/arcano/loco"],
            "tarotysalud.com": [
                "https://tarotysalud.com/tag/interpretacion/",
                "https://tarotysalud.com/category/tarot-gitano-y-su-interpretacion/"],
            "tarotdetiziana.com": [
                "https://tarotdetiziana.com/producto/101-lecturas-para-hacer-e-book/",
                "https://tarotdetiziana.com/mi-cuenta/?redirect_to=https%3A%2F%2Ftarotdetiziana.com%2Flecturas-de-tarot-con-3-cartas%2F"],
        }
        for dominio, urls in exclusiones.items():
            rx = re.compile(_sitio(dominio)["regex"])
            for u in urls:
                self.assertIsNone(rx.search(u), f"{dominio}: regex no debería atrapar {u}")


class TestProcedencia(unittest.TestCase):
    def setUp(self):
        with open(RUTA_JSONL, encoding="utf-8") as f:
            self.registros = [json.loads(line) for line in f if line.strip()]

    def test_un_registro_por_sitio(self):
        self.assertEqual(len(self.registros), len(SITIOS))
        self.assertEqual({r["dominio"] for r in self.registros},
                        {s["dominio"] for s in SITIOS})

    def test_campos_procedencia(self):
        for r in self.registros:
            for campo in ("dominio", "url_ejemplo", "tipo", "familias", "idioma",
                         "periodo", "licencia", "licencia_hint", "paginas_estimadas",
                         "calidad_estimada", "evidencia", "urls_muestra", "nota"):
                self.assertIn(campo, r, f"{r.get('dominio')} sin {campo}")
            self.assertEqual(r["idioma"], "es", r["dominio"])
            self.assertEqual(r["licencia_hint"], "consultar", r["dominio"])
            self.assertIsInstance(r["familias"], list)
            self.assertTrue(r["familias"], r["dominio"])
            self.assertTrue(r["url_ejemplo"].startswith("https://"), r["dominio"])

    def test_baraja_espanola_presente(self):
        con_baraja = [r for r in self.registros if "baraja_espanola" in r["familias"]]
        self.assertGreaterEqual(len(con_baraja), 1)


if __name__ == "__main__":
    unittest.main()
