#!/usr/bin/env python3
"""T53 ARREGLO A: sinónimos ingleses de palos y rangos en el tarot.

Los libros en inglés (Waite y compañía) nombran las menores como
«<Rank> of <Suit>» (King of Wands, Page of Cups, Ace of Pentacles).
Hasta ahora el catálogo solo conocía las formas en español, así que esas
menciones no mapeaban y dejaban 50 menores sin evidencia clásica.

Regla dura: NO mezclar naipes franceses. «King of Hearts» no es una carta
de tarot y debe devolver None en el mazo tarot.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cartas  # noqa: E402


def _entrada(nombre_esperado):
    for e in cartas.CARTAS_TAROT:
        if e["nombre"] == nombre_esperado:
            return e
    raise AssertionError(f"no existe {nombre_esperado} en CARTAS_TAROT")


class NormalizarIngles(unittest.TestCase):
    def test_king_of_wands_es_rey_de_bastos(self):
        e = cartas.normalizar_carta("King of Wands", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Rey de Bastos")
        self.assertEqual(e["id"], "tarot-bastos-14")

    def test_page_of_cups_es_sota_de_copas(self):
        e = cartas.normalizar_carta("Page of Cups", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Sota de Copas")
        self.assertEqual(e["id"], "tarot-copas-11")

    def test_knight_of_swords_es_caballero_de_espadas(self):
        e = cartas.normalizar_carta("Knight of Swords", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Caballero de Espadas")
        self.assertEqual(e["id"], "tarot-espadas-12")

    def test_queen_of_pentacles_es_reina_de_oros(self):
        e = cartas.normalizar_carta("Queen of Pentacles", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Reina de Oros")
        self.assertEqual(e["id"], "tarot-oros-13")

    def test_ace_of_wands_es_as_de_bastos(self):
        e = cartas.normalizar_carta("Ace of Wands", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "As de Bastos")
        self.assertEqual(e["id"], "tarot-bastos-01")

    def test_ten_of_cups_es_diez_de_copas(self):
        e = cartas.normalizar_carta("Ten of Cups", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Diez de Copas")

    def test_two_of_swords_es_dos_de_espadas(self):
        e = cartas.normalizar_carta("Two of Swords", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Dos de Espadas")

    def test_coins_synonym_pentacles(self):
        e = cartas.normalizar_carta("Three of Coins", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Tres de Oros")

    def test_disks_synonym_pentacles(self):
        e = cartas.normalizar_carta("Four of Disks", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Cuatro de Oros")

    def test_mayusculas_minusculas(self):
        for texto in ("KING OF WANDS", "king of wands", "King Of Wands"):
            e = cartas.normalizar_carta(texto, mazo="tarot")
            self.assertIsNotNone(e, texto)
            self.assertEqual(e["nombre"], "Rey de Bastos", texto)

    def test_ocr_doble_espacio(self):
        e = cartas.normalizar_carta("King  of   Wands", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Rey de Bastos")


class NoMezclarNaipesFranceses(unittest.TestCase):
    def test_king_of_hearts_no_es_tarot(self):
        self.assertIsNone(cartas.normalizar_carta("King of Hearts", mazo="tarot"))

    def test_queen_of_diamonds_no_es_tarot(self):
        self.assertIsNone(cartas.normalizar_carta("Queen of Diamonds", mazo="tarot"))

    def test_jack_of_clubs_no_es_tarot(self):
        self.assertIsNone(cartas.normalizar_carta("Jack of Clubs", mazo="tarot"))

    def test_two_of_spades_no_es_tarot(self):
        self.assertIsNone(cartas.normalizar_carta("Two of Spades", mazo="tarot"))


class AdversariosSinMapeo(unittest.TestCase):
    def test_two_swords_sin_of_no_mapea(self):
        self.assertIsNone(cartas.normalizar_carta("two swords", mazo="tarot"))

    def test_two_swords_crossed_no_mapea(self):
        self.assertIsNone(cartas.normalizar_carta("two swords crossed", mazo="tarot"))

    def test_pages_plural_no_mapea(self):
        self.assertIsNone(cartas.normalizar_carta("Pages", mazo="tarot"))

    def test_the_wand_sin_rango_no_mapea(self):
        self.assertIsNone(cartas.normalizar_carta("the Wand", mazo="tarot"))


class ExtraccionIngles(unittest.TestCase):
    def test_extrae_dos_menores(self):
        menciones = cartas.extraer_cartas(
            "the King of Wands and the Queen of Cups", mazo="tarot")
        nombres = [m["carta"]["nombre"] for m in menciones]
        self.assertEqual(nombres, ["Rey de Bastos", "Reina de Copas"])

    def test_extrae_two_swords_crossed_no(self):
        menciones = cartas.extraer_cartas(
            "two swords crossed in the painting", mazo="tarot")
        self.assertEqual(menciones, [])

    def test_extrae_page_of_pentacles(self):
        menciones = cartas.extraer_cartas(
            "The Page of Pentacles signifies a new venture", mazo="tarot")
        nombres = [m["carta"]["nombre"] for m in menciones]
        self.assertEqual(nombres, ["Sota de Oros"])


class SeparacionMazos(unittest.TestCase):
    def test_ingles_no_aplica_a_baraja_espanola(self):
        self.assertIsNone(cartas.normalizar_carta("King of Wands", mazo="espanol"))

    def test_espanol_sigue_mapeando_en_tarot(self):
        e = cartas.normalizar_carta("rey de bastos", mazo="tarot")
        self.assertIsNotNone(e)
        self.assertEqual(e["nombre"], "Rey de Bastos")


if __name__ == "__main__":
    unittest.main()
