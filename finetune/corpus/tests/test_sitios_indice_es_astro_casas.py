"""Tests de estructura de sitios_indice_es_astro_casas.json (T42): sitios en español
con página por combinación astrológica (planeta en signo, planeta en casa, aspectos y
ascendente)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

RUTA = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge",
    "sitios_indice_es_astro_casas.json")
RUTA_GENERAL = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json")
RUTA_TAROT = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_tarot.json")
RUTA_FUENTES = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge",
    "fuentes_web_es_astro_casas.jsonl")

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

with open(RUTA_TAROT, encoding="utf-8") as _f:
    DATOS_TAROT = json.load(_f)

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
        self.assertGreaterEqual(len(SITIOS), 15)

    def test_campos_obligatorios(self):
        for s in SITIOS:
            faltan = CAMPOS_OBLIGATORIOS - set(s)
            self.assertFalse(faltan, f"{s.get('dominio')} sin campos: {faltan}")

    def test_regex_compilan_y_estan_ancladas(self):
        for s in SITIOS:
            try:
                re.compile(s["regex"])
            except re.error as exc:
                self.fail(f"regex inválida en {s['dominio']}: {exc}")
            self.assertTrue(s["regex"].startswith("^"), s["dominio"])
            self.assertTrue(s["regex"].endswith("$"), s["dominio"])

    def test_familia_astrologia(self):
        for s in SITIOS:
            self.assertEqual(s["familia"], "astrologia", s["dominio"])

    def test_prioridad_valida(self):
        for s in SITIOS:
            self.assertIn(s["prioridad"], PRIORIDADES_VALIDAS, s["dominio"])

    def test_indice_no_vacio_y_https(self):
        for s in SITIOS:
            self.assertTrue(s["indice"], f"{s['dominio']} sin índice")
            for u in s["indice"]:
                self.assertTrue(u.startswith("https://"),
                                f"{s['dominio']}: {u} no es https")

    def test_sin_dominios_duplicados(self):
        dominios = [s["dominio"] for s in SITIOS]
        self.assertEqual(len(dominios), len(set(dominios)))

    def test_sin_solape_con_indices_previos(self):
        previos = {s["dominio"] for s in DATOS_GENERAL["sitios"]}
        previos |= {s["dominio"] for s in DATOS_TAROT["sitios"]}
        nuevos = {s["dominio"] for s in SITIOS}
        self.assertFalse(nuevos & previos,
                         f"duplicados con índices previos: {nuevos & previos}")

    def test_dominio_coincide_con_nombre(self):
        for s in SITIOS:
            self.assertEqual(s["nombre"], s["dominio"])


CASOS = {
    "enastrologico.com": (
        ["https://enastrologico.com/astroblog/luna-en-casa-4/",
         "https://enastrologico.com/astroblog/sol-en-aries/",
         "https://enastrologico.com/astroblog/marte-cuadratura-saturno/"],
        ["https://enastrologico.com/astroblog/",
         "https://enastrologico.com/astroblog/jupiter-en-tauro-2026/"]),
    "astrochart.co": (
        ["https://astrochart.co/es/mars-in-aries",
         "https://astrochart.co/es/sun-in-4th-house"],
        ["https://astrochart.co/es/venus-in-taurus/",
         "https://astrochart.co/es/mars-in-house"]),
    "fernandoangelcoronado.es": (
        ["https://fernandoangelcoronado.es/luna-en-casa-4/",
         "https://fernandoangelcoronado.es/ascendente-libra/",
         "https://fernandoangelcoronado.es/nodo-norte-en-tauro/"],
        ["https://fernandoangelcoronado.es/sobre-mi/",
         "https://fernandoangelcoronado.es/luna-en-la-casa-4/"]),
    "aprendeastrologia.com": (
        ["https://aprendeastrologia.com/blog/sol-conjuncion-luna/",
         "https://aprendeastrologia.com/blog/sol-en-geminis/"],
        ["https://aprendeastrologia.com/blog/",
         "https://aprendeastrologia.com/blog/sol-en-geminis-2026/"]),
    "astroworld.es": (
        ["https://astroworld.es/el-sol-en-acuario/",
         "https://astroworld.es/ascendente-en-aries/"],
        ["https://astroworld.es/contacto/",
         "https://astroworld.es/sol-en-acuario-2026/"]),
    "astralisis.com": (
        ["https://astralisis.com/articulos/sol-en-aries"],
        ["https://astralisis.com/articulos/",
         "https://astralisis.com/articulos/sol-en-aries-2026"]),
    "ruthmontenegro.com": (
        ["https://ruthmontenegro.com/astrologia/sol-en-los-signos/el-sol-en-aries/"],
        ["https://ruthmontenegro.com/astrologia/sol-en-los-signos/el-sol-en-aries",
         "https://ruthmontenegro.com/astrologia/"]),
    "astrologica.es": (
        ["https://astrologica.es/escrito/luna-en-capricornio/"],
        ["https://astrologica.es/escrito/luna-en-capricornio",
         "https://astrologica.es/escrito/"]),
    "soyespiritual.top": (
        ["https://soyespiritual.top/saturno-en-la-casa-1/",
         "https://soyespiritual.top/ascendente-aries/"],
        ["https://soyespiritual.top/saturno-en-casa-1/",
         "https://soyespiritual.top/"]),
    "leandroliptak.com": (
        ["https://leandroliptak.com/luna-en-aries/",
         "https://leandroliptak.com/que-significa-el-ascendente-en-aries/"],
        ["https://leandroliptak.com/sobre-mi/",
         "https://leandroliptak.com/que-significa-el-ascendente-en-aries-y-mas/"]),
    "tailoredmoon.com": (
        ["https://tailoredmoon.com/es/aprender/transitos/sol-en-aries"],
        ["https://tailoredmoon.com/es/aprender/transitos/",
         "https://tailoredmoon.com/es/aprender/transitos/sol-en-aries/"]),
    "simbologia.net": (
        ["https://simbologia.net/pluton-en-la-casa-12-al-borde-de-quedarse-sin-hogar-ayuda/"],
        ["https://simbologia.net/pluton-en-casa-12/",
         "https://simbologia.net/"]),
    "ritmolunar.com": (
        ["https://ritmolunar.com/astrologia/luna-en-casa-4/",
         "https://ritmolunar.com/astrologia/sol-cuadratura-marte/",
         "https://ritmolunar.com/astrologia/ascendente-leo/"],
        ["https://ritmolunar.com/astrologia/",
         "https://ritmolunar.com/astrologia/luna-en-casa-4-2026/"]),
    "www.astrocosmo.cl": (
        ["https://www.astrocosmo.cl/sol-en-geminis/",
         "https://www.astrocosmo.cl/marte-en-geminis/",
         "https://www.astrocosmo.cl/ascendente-en-aries/"],
        ["https://www.astrocosmo.cl/sobre-nosotros/",
         "https://www.astrocosmo.cl/sol-en-geminis"]),
    "caminosdeconocimiento.com": (
        ["https://www.caminosdeconocimiento.com/post/sol-en-leo-2026-temporada-leonina",
         "https://www.caminosdeconocimiento.com/post/marte-cuadratura-saturno-2026"],
        ["https://www.caminosdeconocimiento.com/post/",
         "https://www.caminosdeconocimiento.com/post/sol-en-2026"]),
}


class TestRegexCapturanEntidades(unittest.TestCase):
    """Cada regex debe capturar páginas reales de combinación y no ruido."""

    def test_casos_positivos_y_negativos(self):
        self.assertEqual(set(CASOS), {s["dominio"] for s in SITIOS})
        for dominio, (positivos, negativos) in CASOS.items():
            rx = re.compile(_sitio(dominio)["regex"])
            for url in positivos:
                with self.subTest(sitio=dominio, url=url):
                    self.assertIsNotNone(rx.match(url))
            for url in negativos:
                with self.subTest(sitio=dominio, url=url):
                    self.assertIsNone(rx.match(url))


class TestFuentesWebAstroCasas(unittest.TestCase):
    def test_campos_de_fuente(self):
        for f in FUENTES:
            faltan = CAMPOS_FUENTE - set(f)
            self.assertFalse(faltan, f"{f.get('dominio')} sin campos: {faltan}")

    def test_licencia_hint_consultar(self):
        for f in FUENTES:
            self.assertEqual(f["licencia_hint"], "consultar", f["dominio"])

    def test_familias_e_idioma(self):
        for f in FUENTES:
            self.assertIn("astrologia", f["familias"], f["dominio"])
            self.assertEqual(f["idioma"], "es", f["dominio"])

    def test_dominios_coherentes_con_indice(self):
        self.assertEqual({f["dominio"] for f in FUENTES},
                         {s["dominio"] for s in SITIOS})

    def test_urls_https(self):
        for f in FUENTES:
            self.assertTrue(f["url_ejemplo"].startswith("https://"), f["dominio"])
            for u in f["urls_muestra"]:
                self.assertTrue(u.startswith("https://"), f["dominio"])

    def test_al_menos_quince_fuentes(self):
        self.assertGreaterEqual(len(FUENTES), 15)


if __name__ == "__main__":
    unittest.main()
