"""Tests de estructura de sitios_indice_es_tarot.json (T27): sitios en español con página por carta de tarot."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

RUTA = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_tarot.json")
RUTA_GENERAL = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json")
RUTA_FUENTES = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "fuentes_web_es_tarot.jsonl")

PRIORIDADES_VALIDAS = {"alta", "media", "baja"}
CAMPOS_OBLIGATORIOS = {
    "nombre", "tipo", "indice", "regex", "dominio", "familia", "prioridad", "nota"}
CAMPOS_FUENTE = {
    "dominio", "url_ejemplo", "tipo", "familias", "idioma", "periodo",
    "licencia", "licencia_hint", "paginas_estimadas", "calidad_estimada",
    "evidencia", "urls_muestra", "nota"}

with open(RUTA, encoding="utf-8") as _f:
    DATOS = json.load(_f)

with open(RUTA_GENERAL, encoding="utf-8") as _f:
    DATOS_GENERAL = json.load(_f)

with open(RUTA_FUENTES, encoding="utf-8") as _f:
    FUENTES = [json.loads(linea) for linea in _f if linea.strip()]

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
        self.assertGreaterEqual(len(SITIOS), 12)

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

    def test_familia_tarot(self):
        for s in SITIOS:
            self.assertEqual(s["familia"], "tarot", s["dominio"])

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

    def test_sin_solape_con_sitios_indice_es(self):
        previos = {s["dominio"] for s in DATOS_GENERAL["sitios"]}
        nuevos = {s["dominio"] for s in SITIOS}
        self.assertFalse(nuevos & previos, f"duplicados con sitios_indice_es.json: {nuevos & previos}")

    def test_dominio_coincide_con_nombre(self):
        for s in SITIOS:
            self.assertEqual(s["nombre"], s["dominio"])


class TestRegexCapturanCartas(unittest.TestCase):
    """Cada regex debe capturar URLs reales de carta y no ruido."""

    def test_cartastarotsagrado(self):
        rx = re.compile(_sitio("cartastarotsagrado.com")["regex"])
        self.assertIsNotNone(rx.match("https://cartastarotsagrado.com/el-loco/"))
        self.assertIsNotNone(rx.match("https://cartastarotsagrado.com/la-rueda-fortuna/"))
        self.assertIsNotNone(rx.match("https://cartastarotsagrado.com/rey-de-oros/"))
        self.assertIsNone(rx.match("https://cartastarotsagrado.com/tiradas/"))
        self.assertIsNone(rx.match("https://cartastarotsagrado.com/arcanos-mayores/"))

    def test_tarotveraluna(self):
        rx = re.compile(_sitio("tarotveraluna.com")["regex"])
        self.assertIsNotNone(rx.match("https://tarotveraluna.com/cartas/as-de-copas/"))
        self.assertIsNotNone(rx.match("https://tarotveraluna.com/cartas/caballero-de-copas/"))
        self.assertIsNone(rx.match("https://tarotveraluna.com/cartas/"))
        self.assertIsNone(rx.match("https://tarotveraluna.com/sobre-mi/"))

    def test_tarot_secret(self):
        rx = re.compile(_sitio("tarot-secret.com")["regex"])
        self.assertIsNotNone(rx.match("https://tarot-secret.com/es/as-de-copas/"))
        self.assertIsNotNone(rx.match("https://www.tarot-secret.com/es/la-templanza/"))
        self.assertIsNone(rx.match("https://tarot-secret.com/es/aprender-tarot/"))
        self.assertIsNone(rx.match("https://tarot-secret.com/en/as-de-copas/"))

    def test_tarotbrisatalis(self):
        rx = re.compile(_sitio("tarotbrisatalis.com")["regex"])
        self.assertIsNotNone(rx.match("https://tarotbrisatalis.com/as-de-copas/"))
        self.assertIsNotNone(rx.match("https://tarotbrisatalis.com/3-de-espadas/"))
        self.assertIsNotNone(rx.match("https://tarotbrisatalis.com/el-emperador-en-el-tarot/"))
        self.assertIsNone(rx.match("https://tarotbrisatalis.com/adivinacion/"))
        self.assertIsNone(rx.match("https://tarotbrisatalis.com/amor-para-solteros/"))

    def test_tuastral(self):
        rx = re.compile(_sitio("tuastral.com")["regex"])
        self.assertIsNotNone(rx.match("https://tuastral.com/tarot/cartas/as-de-copas"))
        self.assertIsNotNone(rx.match("https://tuastral.com/tarot/cartas/el-loco"))
        self.assertIsNone(rx.match("https://tuastral.com/tarot/tiradas"))
        self.assertIsNone(rx.match("https://tuastral.com/api/cartas"))

    def test_tarotjunguiano(self):
        rx = re.compile(_sitio("tarotjunguiano.com")["regex"])
        self.assertIsNotNone(rx.match("https://www.tarotjunguiano.com/arcano-mayor-el-carro-arquetipo/"))
        self.assertIsNotNone(rx.match("https://www.tarotjunguiano.com/arcano-menor-as-de-copas/"))
        self.assertIsNotNone(rx.match("https://www.tarotjunguiano.com/9-de-copas/"))
        self.assertIsNone(rx.match("https://www.tarotjunguiano.com/como-limpiar-las-cartas-del-tarot/"))
        self.assertIsNone(rx.match("https://www.tarotjunguiano.com/cartas-de-tarot/"))

    def test_tarotnova(self):
        rx = re.compile(_sitio("tarotnova.app")["regex"])
        self.assertIsNotNone(rx.match("https://www.tarotnova.app/es/tarot/marsella/majors/el-loco"))
        self.assertIsNotNone(rx.match("https://www.tarotnova.app/es/tarot/rider-waite/majors/los-enamorados"))
        self.assertIsNone(rx.match("https://www.tarotnova.app/pt/tarot/marselha/majors/o-mago"))
        self.assertIsNone(rx.match("https://www.tarotnova.app/es/tarot/marsella/minors/as-de-copas"))

    def test_eltarot(self):
        rx = re.compile(_sitio("eltarot.es")["regex"])
        self.assertIsNotNone(rx.match("https://eltarot.es/cartas/as-de-bastos"))
        self.assertIsNotNone(rx.match("https://eltarot.es/cartas/el-loco"))
        self.assertIsNone(rx.match("https://eltarot.es/cartas"))
        self.assertIsNone(rx.match("https://eltarot.es/sobre"))

    def test_tarotgratuito(self):
        rx = re.compile(_sitio("tarotgratuito.net")["regex"])
        self.assertIsNotNone(rx.match("https://www.tarotgratuito.net/el-as-de-copas-tarot"))
        self.assertIsNotNone(rx.match("https://www.tarotgratuito.net/la-templanza-tarot"))
        self.assertIsNotNone(rx.match("https://www.tarotgratuito.net/los-amantes-tarot"))
        self.assertIsNone(rx.match("https://www.tarotgratuito.net/horoscopo"))
        self.assertIsNone(rx.match("https://www.tarotgratuito.net/tirada-tres-cartas-tarot"))

    def test_tarotfiable(self):
        rx = re.compile(_sitio("tarotfiable.es")["regex"])
        self.assertIsNotNone(rx.match("https://tarotfiable.es/arcano-el-loco/"))
        self.assertIsNotNone(rx.match("https://tarotfiable.es/arcano-los-amantes/"))
        self.assertIsNone(rx.match("https://tarotfiable.es/arcano-de-copas/"))
        self.assertIsNone(rx.match("https://tarotfiable.es/curso-tarot/"))

    def test_zodiatarot(self):
        rx = re.compile(_sitio("zodiatarot.com")["regex"])
        self.assertIsNotNone(rx.match("https://zodiatarot.com/es/significado-cartas-tarot/as-de-copas/"))
        self.assertIsNotNone(rx.match("https://zodiatarot.com/es/significado-cartas-tarot/la-luna/"))
        self.assertIsNone(rx.match("https://zodiatarot.com/es/significado-cartas-tarot/"))
        self.assertIsNone(rx.match("https://zodiatarot.com/es/horoscopo/"))

    def test_tarotdetiziana(self):
        rx = re.compile(_sitio("tarotdetiziana.com")["regex"])
        self.assertIsNotNone(rx.match("https://tarotdetiziana.com/el-as-de-copas-y-su-significado-en-el-tarot/"))
        self.assertIsNotNone(rx.match("https://tarotdetiziana.com/el-2-de-bastos-y-sus-simbolos-explicados-en-el-tarot/"))
        self.assertIsNone(rx.match("https://tarotdetiziana.com/4379-2/"))
        self.assertIsNone(rx.match("https://tarotdetiziana.com/72-nombres-una-original-cubierta-cabalistica/"))


class TestFuentesWebTarot(unittest.TestCase):
    def test_campos_de_fuente(self):
        for f in FUENTES:
            faltan = CAMPOS_FUENTE - set(f)
            self.assertFalse(faltan, f"{f.get('dominio')} sin campos: {faltan}")

    def test_licencia_hint_consultar(self):
        for f in FUENTES:
            self.assertEqual(f["licencia_hint"], "consultar", f["dominio"])

    def test_familias_e_idioma(self):
        for f in FUENTES:
            self.assertIn("tarot", f["familias"], f["dominio"])
            self.assertEqual(f["idioma"], "es", f["dominio"])

    def test_dominios_coherentes_con_indice(self):
        self.assertEqual({f["dominio"] for f in FUENTES},
                         {s["dominio"] for s in SITIOS})

    def test_url_ejemplo_https(self):
        for f in FUENTES:
            self.assertTrue(f["url_ejemplo"].startswith("https://"), f["dominio"])
            for u in f["urls_muestra"]:
                self.assertTrue(u.startswith("https://"), f"{f['dominio']}: {u}")

    def test_al_menos_12_fuentes(self):
        self.assertGreaterEqual(len(FUENTES), 12)


if __name__ == "__main__":
    unittest.main()
