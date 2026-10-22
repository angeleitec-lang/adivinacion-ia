"""Tests de libros_comprados_en (T115): segmentacion Pollack/Greer y puerta anti-copia."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import libros_comprados_en as lce

CRUDO_POLLACK = "/Users/angelgonzalez/fase0/libros_comprados_en/crudo/pollack_78_degrees.txt"
CRUDO_GREER = "/Users/angelgonzalez/fase0/libros_comprados_en/crudo/greer_tarot_your_self.txt"

LIBRO_POLLACK = next(l for l in lce.LIBROS if l["id"] == "pollack-78-degrees")
LIBRO_GREER = next(l for l in lce.LIBROS if l["id"] == "greer-tarot-your-self")


def _relleno(n_chars, marca="filler"):
    parrafo = ("%s sentence about the card and its symbolism in the book. " % marca)
    out = []
    total = 0
    i = 0
    while total < n_chars:
        p = parrafo.replace("filler", "%s%d" % (marca, i))
        out.append(p)
        total += len(p)
        i += 1
    return "\n\n".join(out)


def _pollack_sintetico():
    lineas = ["8            SEVENTY-EIGHT DEGREES OF WISDOM"]
    for nombre in lce.MAYORES_EN:
        lineas.append(nombre)
        lineas.append(_relleno(600, marca="the meaning of %s" % nombre.lower()))
        if nombre == "The Fool":
            # Trampa: 'the tower' suelto dentro de otro capitulo no debe
            # crear una seccion falsa (la busqueda es secuencial).
            lineas.append("the tower")
        if nombre == "The Moon":
            lineas.append("REVERSED")
            lineas.append(_relleno(450, marca="reversed moon"))
    lineas.append("First published 1980 by Weiser.")
    lineas.append("THE MINOR ARCANA")
    lineas.append(_relleno(700, marca="wands chapter body"))
    for palo in ("Cups", "Swords", "Pentacles"):
        lineas.append(palo)
        lineas.append(_relleno(700, marca="%s chapter body" % palo.lower()))
    lineas.append("READINGS")
    lineas.append(_relleno(500, marca="readings part"))
    return "\n".join(lineas)


def _greer_sintetico():
    lineas = ["Preface", _relleno(500, marca="prefacio")]
    titulos = ["Getting Acquainted with the Cards", "The Tarot Journal",
              "Reading the Cards", "The Celtic Cross Spread",
              "The Court Card Personalities", "Permutations Reading in Depth",
              "Dealing with Moods", "Prosperity and Planning",
              "Becoming Conscious", "Healing", "Crystals and Tarot",
              "Design and Creativity"]
    for num, tit in enumerate(titulos, 1):
        lineas.append("] Chapter %d [" % num)
        lineas.append(tit)
        lineas.append(_relleno(500, marca="capitulo %d body" % num))
        if num == 4:
            lineas.append("")
            lineas.append("The Celtic Cross Spread")
            lineas.append("Lay the cards out in ten positions and read them.")
            lineas.append(_relleno(500, marca="spread body"))
        lineas.append("SUGGESTED READING FOR CHAPTER %d" % num)
    lineas.append("THE FOOL")
    lineas.append("Air. Non-stupidity. A beginning of the journey.")
    lineas.append(_relleno(500, marca="fool appendix"))
    lineas.append("QUESTIONS TO ANSWER:")
    lineas.append("Where am I beginning fresh?")
    lineas.append("SAMPLE AFFIRMATION:")
    lineas.append("I trust new beginnings.")
    for titulo_ap, canon in (
            ("HIGH PRIESTESS", "The High Priestess"),
            ("THE WHEEL OF FORTUNE", "Wheel of Fortune"),
            ("MOON", "The Moon"),
            ("ACE OF WANDS", "Ace of Wands"),
            ("KING OF CUPS", "King of Cups"),
            ("PAGE OF PENTACLES", "Page of Pentacles")):
        lineas.append(titulo_ap)
        lineas.append(_relleno(500, marca="appendix %s" % canon))
        lineas.append("QUESTIONS TO ANSWER:")
        lineas.append("What does this card ask of me?")
    lineas.append("TABLE OF CORRESPONDENCES")
    lineas.append(_relleno(300, marca="tabla"))
    return "\n".join(lineas)


class TestCabeceras(unittest.TestCase):
    def test_cabecera_pollack(self):
        self.assertTrue(lce._es_cabecera_pollack(
            "8            SEVENTY-EIGHT DEGREES OF WISDOM"))
        self.assertTrue(lce._es_cabecera_pollack("WANDS                              27"))
        self.assertFalse(lce._es_cabecera_pollack("THE MINOR ARCANA"))
        self.assertFalse(lce._es_cabecera_pollack("REVERSED"))
        self.assertFalse(lce._es_cabecera_pollack("READINGS"))
        self.assertFalse(lce._es_cabecera_pollack("The Fool"))
        self.assertFalse(lce._es_cabecera_pollack("THE MOON"))

    def test_cabecera_greer(self):
        self.assertTrue(lce._es_cabecera_greer(
            "Getting Acquainted with the Cards ] 29"))
        self.assertTrue(lce._es_cabecera_greer("] 26 ["))
        self.assertFalse(lce._es_cabecera_greer("] Chapter 3 ["))
        self.assertFalse(lce._es_cabecera_greer("THE FOOL"))


class TestPollack(unittest.TestCase):
    def setUp(self):
        self.trozos = lce.trozos_pollack(_pollack_sintetico())

    def test_22_mayores_y_4_palos(self):
        titulos = [t for t, _ in self.trozos]
        self.assertEqual(len(self.trozos), 26)
        self.assertEqual(titulos[:22], list(lce.MAYORES_EN))
        self.assertEqual(titulos[22:],
                         ["Wands (Arcana Menor)", "Cups (Arcana Menor)",
                          "Swords (Arcana Menor)", "Pentacles (Arcana Menor)"])

    def test_trampa_the_tower_no_falsa_seccion(self):
        torres = [t for t, _ in self.trozos if t == "The Tower"]
        self.assertEqual(len(torres), 1)
        texto_fool = dict(self.trozos)["The Fool"]
        self.assertIn("the tower", texto_fool)

    def test_segmentar_forma_secciones(self):
        secs = lce.segmentar_libro(LIBRO_POLLACK, _pollack_sintetico())
        self.assertTrue(secs)
        for s in secs:
            self.assertEqual(
                sorted(s.keys()),
                ["chars", "id_libro", "posicion", "seccion", "texto", "titulo"])
            self.assertGreaterEqual(s["chars"], lce.MIN_SECCION)
            self.assertEqual(s["id_libro"], "pollack-78-degrees")
            self.assertNotIn("SEVENTY-EIGHT DEGREES OF WISDOM", s["texto"])
        numerados = [s["seccion"] for s in secs]
        self.assertEqual(numerados, list(range(1, len(secs) + 1)))

    def test_reversed_se_conserva(self):
        secs = lce.segmentar_libro(LIBRO_POLLACK, _pollack_sintetico())
        luna = [s for s in secs if s["titulo"].startswith("The Moon")]
        self.assertTrue(any("REVERSED" in s["texto"] for s in luna))


class TestGreer(unittest.TestCase):
    def setUp(self):
        self.trozos = lce.trozos_greer(_greer_sintetico())

    def test_prefacio_capitulos_tecnica_y_apendice(self):
        titulos = [t for t, _ in self.trozos]
        self.assertEqual(titulos[0], "Prefacio e introduccion")
        self.assertIn("Capitulo 1: Getting Acquainted with the Cards", titulos)
        self.assertIn("Capitulo 12: Design and Creativity", titulos)
        self.assertIn("Tecnica: The Celtic Cross Spread", titulos)
        for canon in ("The Fool", "The High Priestess", "Wheel of Fortune",
                     "The Moon", "Ace of Wands", "King of Cups",
                     "Page of Pentacles"):
            self.assertIn(canon, titulos)

    def test_apendice_no_incluye_tabla(self):
        titulos = [t for t, _ in self.trozos]
        self.assertFalse(any("TABLE" in t for t in titulos))

    def test_mapa_titulo_greer_dobles_formas(self):
        casos = {
            "HIGH PRIESTESS": "tarot-mayor-03",
            "MOON": "tarot-mayor-19",
            "THE WHEEL OF FORTUNE": "tarot-mayor-11",
            "STRENGTH/LUST": "tarot-mayor-09",
            "JUSTICE/ADJUSTMENT": "tarot-mayor-12",
            "TEMPERANCE/ART": "tarot-mayor-15",
            "JUDGMENT/AEON": "tarot-mayor-21",
            "THE WORLD/UNIVERSE": "tarot-mayor-22",
            "ACE OF WANDS": "tarot-bastos-01",
            "KING OF CUPS": "tarot-copas-14",
            "PAGE OF PENTACLES": "tarot-oros-11",
        }
        for titulo, esperado in casos.items():
            self.assertEqual(lce._mapa_titulo_greer(titulo), esperado, titulo)


class TestAntiCopia(unittest.TestCase):
    def setUp(self):
        self.libro = " ".join("palabra%d" % i for i in range(60))

    def test_mas_de_25_consecutivas_rechaza(self):
        texto = "inicio " + " ".join("palabra%d" % i for i in range(26))
        self.assertTrue(lce.es_copia(texto, self.libro))

    def test_exactamente_25_consecutivas_ok(self):
        texto = "inicio " + " ".join("palabra%d" % i for i in range(25)) + " final"
        self.assertFalse(lce.es_copia(texto, self.libro))

    def test_ignora_mayusculas_y_tildes(self):
        base = " ".join(["caf\u00e9", "na\u00efve", "r\u00e9sum\u00e9",
                        "pi\u00f1ata", "coraz\u00f3n"] * 7)
        copia = base.upper()
        self.assertTrue(lce.es_copia(copia, base))

    def test_no_consecutivas_ok(self):
        barajado = " ".join(
            ["palabra%d" % i for i in range(0, 30, 2)]
            + ["palabra%d" % i for i in range(1, 30, 2)])
        self.assertFalse(lce.es_copia(barajado, self.libro))

    def test_max_run_configurable(self):
        texto = " ".join("palabra%d" % i for i in range(5))
        self.assertTrue(lce.es_copia(texto, self.libro, max_run=4))
        self.assertFalse(lce.es_copia(texto, self.libro, max_run=5))


class TestWorkDirYEndpoints(unittest.TestCase):
    def test_rechaza_work_dir_real(self):
        with self.assertRaises(ValueError):
            lce.validar_work_dir(lce.WORK_DIR_REAL)
        with self.assertRaises(ValueError):
            lce.validar_work_dir(lce.WORK_DIR_REAL + "/subida")

    def test_acepta_work_dir_aparte(self):
        self.assertTrue(lce.validar_work_dir(lce.WORK_DIR_DEFAULT))

    def test_rechaza_nodo1(self):
        with self.assertRaises(ValueError):
            lce.construir_cliente_endpoints("http://10.0.0.3:8000/v1")
        with self.assertRaises(ValueError):
            lce.construir_cliente_endpoints(
                "http://10.0.0.4:8000/v1,http://10.0.0.3:8000/v1")

    def test_acepta_nodo2(self):
        cliente = lce.construir_cliente_endpoints(lce.ENDPOINT_NODO2)
        self.assertIsNotNone(cliente)

    def test_endpoints_vacios(self):
        with self.assertRaises(ValueError):
            lce.construir_cliente_endpoints("")


class TestClienteAfirmaciones(unittest.TestCase):
    """El adaptador debe reenviar chat y chat_json (bug T115: _ClienteAcotado
    solo define chat y el extractor T38 usa chat_json)."""

    class _Base:
        def __init__(self):
            self.chat_calls = []
            self.json_calls = []

        def chat(self, sistema, usuario, **kw):
            self.chat_calls.append(kw)
            return "ok"

        def chat_json(self, sistema, usuario, validar, **kw):
            self.json_calls.append(kw)
            return {"afirmaciones": []}

    def test_reenvia_chat_json(self):
        base = self._Base()
        adapt = lce._ClienteAfirmaciones(base, reintentos=2)
        out = adapt.chat_json("s", "u", lambda d: None)
        self.assertEqual(out, {"afirmaciones": []})
        self.assertEqual(base.json_calls[0]["intentos"], 2)

    def test_reenvia_chat(self):
        base = self._Base()
        adapt = lce._ClienteAfirmaciones(base, reintentos=2)
        self.assertEqual(adapt.chat("s", "u"), "ok")
        self.assertEqual(base.chat_calls[0]["max_reintentos"], 2)

    def test_no_pisa_kwargs_explicitos(self):
        base = self._Base()
        adapt = lce._ClienteAfirmaciones(base, reintentos=2)
        adapt.chat_json("s", "u", lambda d: None, intentos=5)
        self.assertEqual(base.json_calls[0]["intentos"], 5)


@unittest.skipUnless(os.path.isfile(CRUDO_POLLACK), "crudo Pollack no disponible")
class TestPollackReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CRUDO_POLLACK, encoding="utf-8") as fh:
            cls.texto = fh.read()

    def test_estructura_real(self):
        trozos = lce.trozos_pollack(self.texto)
        titulos = [t for t, _ in trozos]
        self.assertEqual(titulos[:22], list(lce.MAYORES_EN))
        self.assertEqual(len(titulos), 26)
        self.assertEqual(titulos.count("The Tower"), 1)
        self.assertEqual(titulos.count("The Star"), 1)
        self.assertEqual(titulos.count("The Moon"), 1)

    def test_sin_cabeceras_en_secciones(self):
        secs = lce.segmentar_libro(LIBRO_POLLACK, self.texto)
        self.assertGreater(len(secs), 26)
        for s in secs:
            self.assertNotIn("SEVENTY-EIGHT DEGREES OF WISDOM", s["texto"])
            self.assertLessEqual(s["chars"], lce.MAX_SECCION + 500)


@unittest.skipUnless(os.path.isfile(CRUDO_GREER), "crudo Greer no disponible")
class TestGreerReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CRUDO_GREER, encoding="utf-8") as fh:
            cls.texto = fh.read()

    def test_78_cartas_apendice(self):
        trozos = lce.trozos_greer(self.texto)
        nombres_mayores = set(lce.MAYORES_EN)
        menores = set()
        for palo in ("Wands", "Cups", "Swords", "Pentacles"):
            for rango in ("Ace", "Two", "Three", "Four", "Five", "Six",
                         "Seven", "Eight", "Nine", "Ten", "Page", "Knight",
                         "Queen", "King"):
                menores.add("%s of %s" % (rango, palo))
        deck = nombres_mayores | menores
        cartas = [t for t, _ in trozos if t in deck]
        self.assertEqual(len(cartas), 78)
        self.assertEqual(len(set(cartas)), 78)

    def test_capitulos_y_tecnicas(self):
        trozos = lce.trozos_greer(self.texto)
        titulos = [t for t, _ in trozos]
        caps = [t for t in titulos if t.startswith("Capitulo ")]
        self.assertGreaterEqual(len(caps), 12)
        tecnicas = [t for t in titulos if t.startswith("Tecnica: ")]
        self.assertGreater(len(tecnicas), 5)
        self.assertEqual(titulos[0], "Prefacio e introduccion")


if __name__ == "__main__":
    unittest.main()
