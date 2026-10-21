#!/usr/bin/env python3
"""T53 ARREGLO B: nombres ingleses ambiguos de arcanos mayores.

«the sun», «the moon», «the world», «death», «justice», «strength» son
palabras cotidianas. En el cuerpo de una sección solo deben contar como
carta si hay una palabra de contexto tarot cerca (card, tarot, trump,
arcanum, major arcana…). En el título siguen valiendo siempre.

Antes del arreglo, cualquier «the …» del cuerpo se aceptaba, así que
«the sun was setting» generaba evidencia falsa para El Sol.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import juez  # noqa: E402


def _seccion(titulo, texto, id_libro="libro-demo"):
    return {
        "seccion": 1,
        "titulo": titulo,
        "texto": texto,
        "chars": len(texto),
        "id_libro": id_libro,
        "posicion": 0,
    }


def _ids(seccion):
    return {c["entidad_id"] for c in juez.candidatos_seccion(seccion)}


class CuerpoCotidianoNoMapea(unittest.TestCase):
    def test_the_sun_was_setting(self):
        ids = _ids(_seccion("Notas", "the sun was setting over the hills"))
        self.assertNotIn("tarot-mayor-20", ids)

    def test_the_world_is_round(self):
        ids = _ids(_seccion("Notas", "the world is round and vast"))
        self.assertNotIn("tarot-mayor-22", ids)

    def test_the_moon_rose(self):
        ids = _ids(_seccion("Notas", "the moon rose late that night"))
        self.assertNotIn("tarot-mayor-19", ids)

    def test_death_came_suddenly(self):
        ids = _ids(_seccion("Cronica", "death came suddenly to the village"))
        self.assertNotIn("tarot-mayor-14", ids)

    def test_justice_prevailed(self):
        ids = _ids(_seccion("Tribunal", "justice prevailed in the court"))
        self.assertNotIn("tarot-mayor-12", ids)

    def test_strength_is_not_violence(self):
        ids = _ids(_seccion("Ensayo", "strength is not the same as violence"))
        self.assertNotIn("tarot-mayor-09", ids)


class CuerpoConContextoSiMapea(unittest.TestCase):
    def test_card_of_the_sun(self):
        ids = _ids(_seccion("Notas", "the card of the Sun brings joy"))
        self.assertIn("tarot-mayor-20", ids)

    def test_sun_trump_xix(self):
        ids = _ids(_seccion("Notas", "The Sun, trump XIX, radiates success"))
        self.assertIn("tarot-mayor-20", ids)

    def test_tarot_card_the_moon(self):
        ids = _ids(_seccion(
            "Notas", "this tarot card, the moon, governs dreams"))
        self.assertIn("tarot-mayor-19", ids)

    def test_arcanum_the_world(self):
        ids = _ids(_seccion(
            "Notas", "the arcanum known as the world crowns the journey"))
        self.assertIn("tarot-mayor-22", ids)

    def test_major_arcana_the_star(self):
        ids = _ids(_seccion(
            "Notas", "among the major arcana, the star brings hope"))
        self.assertIn("tarot-mayor-18", ids)


class TituloSiempreVale(unittest.TestCase):
    def test_titulo_the_sun_cuerpo_cotidiano(self):
        ids = _ids(_seccion("The Sun", "the sun was setting over the hills"))
        self.assertIn("tarot-mayor-20", ids)

    def test_titulo_death(self):
        ids = _ids(_seccion("Death", "death is a natural end of all things"))
        self.assertIn("tarot-mayor-14", ids)


class CuerpoNoAmbiguoSigueMapeando(unittest.TestCase):
    def test_the_hanged_man_sin_contexto(self):
        ids = _ids(_seccion(
            "Notas", "the hanged man suspends from a living tree"))
        self.assertIn("tarot-mayor-13", ids)

    def test_wheel_of_fortune_sin_contexto(self):
        ids = _ids(_seccion(
            "Notas", "wheel of fortune turns endlessly through the ages"))
        self.assertIn("tarot-mayor-11", ids)


if __name__ == "__main__":
    unittest.main()
