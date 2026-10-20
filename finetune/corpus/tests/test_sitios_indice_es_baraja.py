"""Tests de estructura de sitios_indice_es_baraja.json (T36): sitios en español con página por naipe de baraja española."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import re
import unittest

RUTA = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_baraja.json")
RUTA_GENERAL = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json")
RUTA_LECTURAS = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_lecturas.json")
RUTA_TAROT = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es_tarot.json")
RUTA_FUENTES = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "fuentes_web_es_baraja.jsonl")

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

    def test_familia_baraja(self):
        for s in SITIOS:
            self.assertEqual(s["familia"], "baraja", s["dominio"])

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


class TestRegexCapturanNaipes(unittest.TestCase):
    """Cada regex debe capturar URLs reales de naipe y no ruido."""

    def test_tiradadetarot(self):
        rx = re.compile(_sitio("tiradadetarot.com")["regex"])
        self.assertIsNotNone(rx.match("https://tiradadetarot.com/cartas-espanolas/as-de-oros"))
        self.assertIsNotNone(rx.match("https://tiradadetarot.com/cartas-espanolas/rey-de-espadas/"))
        self.assertIsNone(rx.match("https://tiradadetarot.com/en/cartas-espanolas/as-de-oros"))
        self.assertIsNone(rx.match("https://tiradadetarot.com/tiradas/"))

    def test_futooro(self):
        rx = re.compile(_sitio("futooro.net")["regex"])
        self.assertIsNotNone(rx.match("https://futooro.net/tarot/baraja-espanola/as-de-oros/"))
        self.assertIsNotNone(rx.match("https://futooro.net/tarot/baraja-espanola/caballo-de-bastos/"))
        self.assertIsNone(rx.match("https://futooro.net/tarot/baraja-espanola/"))
        self.assertIsNone(rx.match("https://futooro.net/tarot/arcanos-mayores/"))

    def test_tarotamigo(self):
        rx = re.compile(_sitio("www.tarotamigo.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.tarotamigo.com/tarot/significado-cartas/baraja-espanola/as-de-copas/"))
        self.assertIsNotNone(rx.match(
            "https://www.tarotamigo.com/tarot/significado-cartas/baraja-espanola/rey-de-bastos/"))
        self.assertIsNone(rx.match(
            "https://www.tarotamigo.com/tarot/significado-cartas/baraja-espanola/"))
        self.assertIsNone(rx.match("https://www.tarotamigo.com/tarot/tiradas/"))

    def test_jardindeltarot(self):
        rx = re.compile(_sitio("jardindeltarot.com")["regex"])
        self.assertIsNotNone(rx.match("https://jardindeltarot.com/cartas-espanolas/as-de-bastos/"))
        self.assertIsNotNone(rx.match("https://jardindeltarot.com/cartas-espanolas/rey-de-oros/"))
        self.assertIsNone(rx.match("https://jardindeltarot.com/cartas/as-de-bastos/"))
        self.assertIsNone(rx.match("https://jardindeltarot.com/cartas-espanolas/"))

    def test_oraculoseuropeos(self):
        rx = re.compile(_sitio("oraculoseuropeos.blogspot.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://oraculoseuropeos.blogspot.com/2011/07/baraja-espanola-rey-de-copas.html"))
        self.assertIsNotNone(rx.match(
            "https://oraculoseuropeos.blogspot.com/2011/07/baraja-espanola-sota-de-oros.html"))
        self.assertIsNone(rx.match(
            "https://oraculoseuropeos.blogspot.com/2011/07/rider-waite-as-de-copas.html"))
        self.assertIsNone(rx.match("https://oraculoseuropeos.blogspot.com/search?q=baraja"))

    def test_tarotdeabsalon(self):
        rx = re.compile(_sitio("tarotdeabsalon.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://tarotdeabsalon.com/significado-cartas/baraja-espanola/sota-de-copas/"))
        self.assertIsNotNone(rx.match(
            "https://tarotdeabsalon.com/significado-cartas/baraja-espanola/as-copas/"))
        self.assertIsNone(rx.match(
            "https://tarotdeabsalon.com/significado-cartas/baraja-espanola/"))
        self.assertIsNone(rx.match("https://tarotdeabsalon.com/significado-cartas/tarot/as-de-copas/"))

    def test_soyespiritual(self):
        rx = re.compile(_sitio("soyespiritual.top")["regex"])
        self.assertIsNotNone(rx.match(
            "https://soyespiritual.top/significado-cinco-de-bastos-tarot-baraja-espanola/"))
        self.assertIsNotNone(rx.match(
            "https://soyespiritual.top/significado-rey-de-oros-tarot-baraja-espanola/"))
        self.assertIsNone(rx.match("https://soyespiritual.top/significado-el-loco-tarot/"))
        self.assertIsNone(rx.match("https://soyespiritual.top/tarot/"))

    def test_tarotsolaguilar(self):
        rx = re.compile(_sitio("www.tarotsolaguilar.com")["regex"])
        self.assertIsNotNone(rx.match("https://www.tarotsolaguilar.com/baraja-espanola/rey-de-bastos/"))
        self.assertIsNotNone(rx.match("https://www.tarotsolaguilar.com/baraja-espanola/as-de-copas/"))
        self.assertIsNone(rx.match("https://www.tarotsolaguilar.com/baraja-espanola/ocho-de-oros/"))
        self.assertIsNone(rx.match("https://www.tarotsolaguilar.com/tarot/"))

    def test_consultacartas(self):
        rx = re.compile(_sitio("www.consultacartas.com")["regex"])
        self.assertIsNotNone(rx.match(
            "https://www.consultacartas.com/baraja_espanola_as_de_bastos.html"))
        self.assertIsNotNone(rx.match(
            "https://www.consultacartas.com/baraja_espanola_rey_de_oros.html"))
        self.assertIsNone(rx.match("https://www.consultacartas.com/tarot_as_de_oros.html"))
        self.assertIsNone(rx.match("https://www.consultacartas.com/baraja_espanola.html"))

    def test_elreydecopas(self):
        rx = re.compile(_sitio("elreydecopas.com")["regex"])
        self.assertIsNotNone(rx.match("https://elreydecopas.com/baraja-espanola/as-de-copas/"))
        self.assertIsNotNone(rx.match("https://elreydecopas.com/baraja-espanola/2-de-oros/"))
        self.assertIsNotNone(rx.match("https://elreydecopas.com/baraja-espanola/rey-de-bastos/"))
        self.assertIsNone(rx.match("https://elreydecopas.com/baraja-espanola/ocho-de-oros/"))
        self.assertIsNone(rx.match("https://elreydecopas.com/tarot/as-de-copas/"))

    def test_tarotgratis_club(self):
        rx = re.compile(_sitio("tarotgratis.club")["regex"])
        self.assertIsNotNone(rx.match(
            "https://tarotgratis.club/baraja-espanola/cartas/oros/caballo/"))
        self.assertIsNotNone(rx.match(
            "https://tarotgratis.club/baraja-espanola/cartas/espadas/rey/"))
        self.assertIsNone(rx.match("https://tarotgratis.club/baraja-espanola/cartas/oros/"))
        self.assertIsNone(rx.match("https://tarotgratis.club/tarot/cartas/oros/caballo/"))

    def test_tarotdeana(self):
        rx = re.compile(_sitio("tarotdeana.es")["regex"])
        self.assertIsNotNone(rx.match("https://tarotdeana.es/sota-de-oros-baraja-espanola/"))
        self.assertIsNotNone(rx.match("https://tarotdeana.es/3-de-copas-baraja-espanola/"))
        self.assertIsNone(rx.match("https://tarotdeana.es/as-de-copas-tarot/"))
        self.assertIsNone(rx.match("https://tarotdeana.es/baraja-espanola/"))


class TestCoberturaNaipes(unittest.TestCase):
    """La unión de las regex de los 12 sitios debe cubrir los 40 naipes de la matriz."""

    RANGOS = {
        "as": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
        "siete": 7, "sota": 8, "caballo": 9, "rey": 10}
    PALOS = ("oros", "copas", "espadas", "bastos")

    def _ejemplo_url(self, dominio, palo, rango):
        r = self.RANGOS[rango]
        plantillas = {
            "tiradadetarot.com": f"https://tiradadetarot.com/cartas-espanolas/{rango}-de-{palo}",
            "futooro.net": f"https://futooro.net/tarot/baraja-espanola/{rango}-de-{palo}/",
            "www.tarotamigo.com": f"https://www.tarotamigo.com/tarot/significado-cartas/baraja-espanola/{rango}-de-{palo}/",
            "jardindeltarot.com": f"https://jardindeltarot.com/cartas-espanolas/{rango}-de-{palo}/",
            "oraculoseuropeos.blogspot.com": f"https://oraculoseuropeos.blogspot.com/2011/07/baraja-espanola-{rango}-de-{palo}.html",
            "tarotdeabsalon.com": f"https://tarotdeabsalon.com/significado-cartas/baraja-espanola/{rango}-de-{palo}/",
            "soyespiritual.top": f"https://soyespiritual.top/significado-{rango}-de-{palo}-tarot-baraja-espanola/",
            "www.tarotsolaguilar.com": f"https://www.tarotsolaguilar.com/baraja-espanola/{rango}-de-{palo}/",
            "www.consultacartas.com": f"https://www.consultacartas.com/baraja_espanola_{rango}_de_{palo}.html",
            "elreydecopas.com": f"https://elreydecopas.com/baraja-espanola/{rango}-de-{palo}/",
            "tarotgratis.club": f"https://tarotgratis.club/baraja-espanola/cartas/{palo}/{rango}/",
            "tarotdeana.es": f"https://tarotdeana.es/{rango}-de-{palo}-baraja-espanola/",
        }
        return plantillas[dominio]

    def test_union_cubre_40_naipes(self):
        cubiertos = set()
        for s in SITIOS:
            rx = re.compile(s["regex"])
            for palo in self.PALOS:
                for rango in self.RANGOS:
                    url = self._ejemplo_url(s["dominio"], palo, rango)
                    if rx.match(url):
                        cubiertos.add((palo, self.RANGOS[rango]))
        self.assertEqual(len(cubiertos), 40, f"faltan naipes: {sorted(set((p, n) for p in self.PALOS for n in self.RANGOS.values()) - cubiertos)}")


class TestFuentesWebBaraja(unittest.TestCase):
    def test_campos_de_fuente(self):
        for f in FUENTES:
            faltan = CAMPOS_FUENTE - set(f)
            self.assertFalse(faltan, f"{f.get('dominio')} sin campos: {faltan}")

    def test_licencia_hint_consultar(self):
        for f in FUENTES:
            self.assertEqual(f["licencia_hint"], "consultar", f["dominio"])

    def test_familias_e_idioma(self):
        for f in FUENTES:
            self.assertIn("baraja", f["familias"], f["dominio"])
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
