"""Tests de estructura de sitios_indice_es_numerologia.json (T36): sitios en español con páginas por número."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

RUTA = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_numerologia.json")
RUTA_GENERAL = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json")
RUTA_LECTURAS = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_lecturas.json")
RUTA_TAROT = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_tarot.json")
RUTA_FUENTES = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "fuentes_web_es_numerologia.jsonl")

PRIORIDADES_VALIDAS = {"alta", "media", "baja"}
CAMPOS_OBLIGATORIOS = {
    "nombre", "tipo", "indice", "regex", "dominio", "familia", "prioridad", "nota"}
CAMPOS_FUENTE = {
    "dominio", "url_ejemplo", "tipo", "familias", "idioma", "periodo",
    "licencia", "licencia_hint", "paginas_estimadas", "calidad_estimada",
    "evidencia", "urls_muestra", "nota"}
NUMEROS_VALIDOS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 22, 33}

with open(RUTA, encoding="utf-8") as _f:
    DATOS = json.load(_f)

with open(RUTA_GENERAL, encoding="utf-8") as _f:
    DATOS_GENERAL = json.load(_f)

with open(RUTA_LECTURAS, encoding="utf-8") as _f:
    DATOS_LECTURAS = json.load(_f)

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

    def test_familia_numerologia(self):
        for s in SITIOS:
            self.assertEqual(s["familia"], "numerologia", s["dominio"])

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

    def test_sin_solape_con_otros_indices(self):
        nuevos = {s["dominio"] for s in SITIOS}
        for otros, nombre in (
                (DATOS_GENERAL, "sitios_indice_es.json"),
                (DATOS_LECTURAS, "sitios_indice_es_lecturas.json"),
                (DATOS_TAROT, "sitios_indice_es_tarot.json")):
            previos = {s["dominio"] for s in otros["sitios"]}
            self.assertFalse(nuevos & previos, f"duplicados con {nombre}: {nuevos & previos}")

    def test_dominio_coincide_con_nombre(self):
        for s in SITIOS:
            self.assertEqual(s["nombre"], s["dominio"])


class TestRegexCapturanNumeros(unittest.TestCase):
    """Cada regex debe capturar URLs reales por número y no ruido."""

    def test_yourastrallife(self):
        rx = re.compile(_sitio("www.yourastrallife.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.yourastrallife.com/es/numerologia/guia/numero-del-alma-1"))
        self.assertIsNotNone(rx.match(
            "https://www.yourastrallife.com/es/numerologia/guia/camino-de-vida-22"))
        self.assertIsNone(rx.match(
            "https://www.yourastrallife.com/es/numerologia/guia/numero-del-alma-13"))
        self.assertIsNone(rx.match("https://www.yourastrallife.com/es/numerologia/"))

    def test_cartaceleste(self):
        rx = re.compile(_sitio("www.cartaceleste.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.cartaceleste.com/numerologia/camino-de-vida/1/"))
        self.assertIsNotNone(rx.match(
            "https://www.cartaceleste.com/numerologia/camino-de-vida/33/"))
        self.assertIsNone(rx.match(
            "https://www.cartaceleste.com/numerologia/camino-de-vida/10/"))
        self.assertIsNone(rx.match("https://www.cartaceleste.com/numerologia/"))

    def test_mybornday(self):
        rx = re.compile(_sitio("mybornday.com")["regex"])
        self.assertIsNotNone(rx.match("https://mybornday.com/es/numerologia/camino-1/"))
        self.assertIsNotNone(rx.match("https://mybornday.com/es/numerologia/camino-11/"))
        self.assertIsNone(rx.match("https://mybornday.com/es/numerologia/camino-10/"))
        self.assertIsNone(rx.match("https://mybornday.com/es/numerologia/"))

    def test_datemyst(self):
        rx = re.compile(_sitio("datemyst.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://datemyst.com/es/conocimiento/numerologia/numerologia-1-significado-del-numero-1"))
        self.assertIsNotNone(rx.match(
            "https://datemyst.com/es/conocimiento/numerologia/numerologia-11-numero-maestro-11"))
        self.assertIsNone(rx.match(
            "https://datemyst.com/es/conocimiento/numerologia/numerologia-10-significado"))
        self.assertIsNone(rx.match("https://datemyst.com/es/conocimiento/tarot/"))

    def test_velotit(self):
        rx = re.compile(_sitio("www.velotit.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.velotit.com/es/blog/numero-1-significado-numerologia"))
        self.assertIsNotNone(rx.match(
            "https://www.velotit.com/es/blog/numero-maestro-22-significado-numerologia"))
        self.assertIsNone(rx.match(
            "https://www.velotit.com/es/blog/numero-44-significado-numerologia"))
        self.assertIsNone(rx.match("https://www.velotit.com/es/blog/horoscopo"))

    def test_mon_oracle(self):
        rx = re.compile(_sitio("www.mon-oracle.org")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.mon-oracle.org/es/numerologia/camino-de-vida-1"))
        self.assertIsNotNone(rx.match(
            "https://www.mon-oracle.org/es/numerologia/camino-de-vida-9"))
        self.assertIsNone(rx.match(
            "https://www.mon-oracle.org/es/numerologia/numeros-maestros-11-22-33"))
        self.assertIsNone(rx.match("https://www.mon-oracle.org/es/tarot/"))

    def test_freenumerology(self):
        rx = re.compile(_sitio("freenumerology.net")["regex"])
        self.assertIsNotNone(rx.match("https://freenumerology.net/es/guides/life-path-1"))
        self.assertIsNotNone(rx.match("https://freenumerology.net/es/guides/personal-year-7"))
        self.assertIsNone(rx.match("https://freenumerology.net/es/guides/life-path-10"))
        self.assertIsNone(rx.match("https://freenumerology.net/es/guides/"))

    def test_skywhisper(self):
        rx = re.compile(_sitio("www.skywhisper.app")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.skywhisper.app/es/numerology/life-path/1"))
        self.assertIsNotNone(rx.match(
            "https://www.skywhisper.app/es/numerology/life-path/9"))
        self.assertIsNone(rx.match(
            "https://www.skywhisper.app/es/numerology/life-path/10"))
        self.assertIsNone(rx.match("https://www.skywhisper.app/es/numerology/"))

    def test_numerologia_cotidiana(self):
        rx = re.compile(_sitio("numerologia-cotidiana.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://numerologia-cotidiana.com/significado-1-numeropersonal/"))
        self.assertIsNotNone(rx.match(
            "https://numerologia-cotidiana.com/significado-22-numeropersonal/"))
        self.assertIsNone(rx.match(
            "https://numerologia-cotidiana.com/significado-10-numeropersonal/"))
        self.assertIsNone(rx.match(
            "https://numerologia-cotidiana.com/significado-1-numerokarma/"))

    def test_numerologos(self):
        rx = re.compile(_sitio("numerologos.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://numerologos.com/interpretaciones-y-significados/numero-de-vida-1-explicado-guia-completa-numerologia/"))
        self.assertIsNotNone(rx.match(
            "https://numerologos.com/interpretaciones-y-significados/numero-de-vida-3/"))
        self.assertIsNone(rx.match("https://numerologos.com/numeros-maestros/"))
        self.assertIsNone(rx.match(
            "https://numerologos.com/interpretaciones-y-significados/tarot-1/"))

    def test_aurimundi(self):
        rx = re.compile(_sitio("www.aurimundi.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.aurimundi.com/numerologia/camino-de-vida-1/"))
        self.assertIsNotNone(rx.match(
            "https://www.aurimundi.com/numerologia/numero-maestro-33/"))
        self.assertIsNone(rx.match(
            "https://www.aurimundi.com/numerologia/numero-del-alma-numerologia/"))
        self.assertIsNone(rx.match("https://www.aurimundi.com/tarot/"))

    def test_numerovya(self):
        rx = re.compile(_sitio("www.numerovya.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.numerovya.com/es/camino-de-vida-1-numerologia"))
        self.assertIsNotNone(rx.match(
            "https://www.numerovya.com/es/camino-de-vida-11-numerologia"))
        self.assertIsNone(rx.match(
            "https://www.numerovya.com/es/camino-de-vida-10-numerologia"))
        self.assertIsNone(rx.match(
            "https://www.numerovya.com/es/los-numeros-maestros-en-numerologia"))


class TestCoberturaNumeros(unittest.TestCase):
    """La unión de las regex de los 12 sitios debe cubrir los 12 números de la matriz."""

    PLANTILLAS = {
        "www.yourastrallife.com": "https://www.yourastrallife.com/es/numerologia/guia/camino-de-vida-{n}",
        "www.cartaceleste.com": "https://www.cartaceleste.com/numerologia/camino-de-vida/{n}/",
        "mybornday.com": "https://mybornday.com/es/numerologia/camino-{n}/",
        "datemyst.com": "https://datemyst.com/es/conocimiento/numerologia/numerologia-{n}-significado",
        "www.velotit.com": "https://www.velotit.com/es/blog/numero-{n}-significado-numerologia",
        "www.mon-oracle.org": "https://www.mon-oracle.org/es/numerologia/camino-de-vida-{n}",
        "freenumerology.net": "https://freenumerology.net/es/guides/life-path-{n}",
        "www.skywhisper.app": "https://www.skywhisper.app/es/numerology/life-path/{n}",
        "numerologia-cotidiana.com": "https://numerologia-cotidiana.com/significado-{n}-numeropersonal/",
        "numerologos.com": "https://numerologos.com/interpretaciones-y-significados/numero-de-vida-{n}/",
        "www.aurimundi.com": "https://www.aurimundi.com/numerologia/camino-de-vida-{n}/",
        "www.numerovya.com": "https://www.numerovya.com/es/camino-de-vida-{n}-numerologia",
    }

    def test_union_cubre_12_numeros(self):
        cubiertos = set()
        for s in SITIOS:
            rx = re.compile(s["regex"])
            for n in NUMEROS_VALIDOS:
                url = self.PLANTILLAS[s["dominio"]].format(n=n)
                if rx.match(url):
                    cubiertos.add(n)
        faltan = NUMEROS_VALIDOS - cubiertos
        self.assertFalse(faltan, f"números sin cubrir por ningún sitio: {sorted(faltan)}")

    def test_regex_no_capturan_numeros_invalidos(self):
        invalidos = (10, 12, 13, 44, 111)
        for s in SITIOS:
            rx = re.compile(s["regex"])
            for n in invalidos:
                url = self.PLANTILLAS[s["dominio"]].format(n=n)
                self.assertIsNone(rx.match(url),
                                f"{s['dominio']}: regex captura número inválido {n}: {url}")


class TestFuentesWebNumerologia(unittest.TestCase):
    def test_campos_de_fuente(self):
        for f in FUENTES:
            faltan = CAMPOS_FUENTE - set(f)
            self.assertFalse(faltan, f"{f.get('dominio')} sin campos: {faltan}")

    def test_licencia_hint_consultar(self):
        for f in FUENTES:
            self.assertEqual(f["licencia_hint"], "consultar", f["dominio"])

    def test_familias_e_idioma(self):
        for f in FUENTES:
            self.assertIn("numerologia", f["familias"], f["dominio"])
            self.assertEqual(f["idioma"], "es", f["dominio"])

    def test_dominios_coherentes_con_indice(self):
        self.assertEqual({f["dominio"] for f in FUENTES},
                         {s["dominio"] for s in SITIOS})

    def test_url_ejemplo_https(self):
        for f in FUENTES:
            self.assertTrue(f["url_ejemplo"].startswith("https://"), f["dominio"])
            for u in f["urls_muestra"]:
                self.assertTrue(u.startswith("https://"), f"{f['dominio']}: {u}")

    def test_url_ejemplo_match_con_regex(self):
        for f in FUENTES:
            rx = re.compile(_sitio(f["dominio"])["regex"])
            self.assertIsNotNone(rx.match(f["url_ejemplo"]),
                                f"{f['dominio']}: url_ejemplo no matchea la regex")

    def test_al_menos_12_fuentes(self):
        self.assertGreaterEqual(len(FUENTES), 12)


if __name__ == "__main__":
    unittest.main()
