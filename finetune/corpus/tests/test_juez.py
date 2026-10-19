"""Tests del juez de evidencias (T22): candidatos, validación, anclaje y salida."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest


import juez


def _seccion(titulo, texto, id_libro="libro-demo"):
    return {
        "seccion": 1,
        "titulo": titulo,
        "texto": texto,
        "chars": len(texto),
        "id_libro": id_libro,
        "posicion": 0,
    }


class CandidatosTarot(unittest.TestCase):
    """Paso 1 determinista: candidatos de entidad en secciones de naipes."""

    def _ids(self, seccion):
        return {c["entidad_id"] for c in juez.candidatos_seccion(seccion)}

    def test_the_fool_con_interpretacion(self):
        seccion = _seccion(
            "The Fool",
            "The Fool stands at the edge of the cliff and teaches new "
            "beginnings. The number of The Fool is often read as zero, a "
            "journey that starts in innocence and spontaneity.")
        self.assertIn("tarot-mayor-01", self._ids(seccion))

    def test_seccion_sin_entidades_no_da_candidatos(self):
        seccion = _seccion(
            "Nota del editor",
            "Esta impresión de la corte se realizó con planchas de cobre "
            "durante el siglo XVIII y sobrevive en un único ejemplar "
            "conservado en una biblioteca municipal de provincia.")
        self.assertEqual(self._ids(seccion), set())

    def test_baraja_espanola_as_de_oros(self):
        seccion = _seccion(
            "El as de oros",
            "En la baraja española el as de oros anuncia comienzos "
            "prósperos en el plano material y se asocia con la riqueza.")
        ids = self._ids(seccion)
        self.assertIn("naipe-oros-01", ids)

    def test_tarot_en_espanol(self):
        seccion = _seccion(
            "La Emperatriz",
            "La Emperatriz representa la fertilidad y la abundancia; "
            "invertida puede señalar dependencia afectiva.")
        self.assertIn("tarot-mayor-04", self._ids(seccion))


class CandidatosAstroNumerologia(unittest.TestCase):
    """Paso 1 para astrología y numerología."""

    def _ids(self, seccion):
        return {c["entidad_id"] for c in juez.candidatos_seccion(seccion)}

    def test_sol_en_leo_da_planeta_y_signo(self):
        seccion = _seccion(
            "El Sol en el zodiaco",
            "Con el Sol en Leo la vitalidad se expresa con teatralidad; "
            "es un signo de fuego regido por el Sol.")
        ids = self._ids(seccion)
        self.assertIn("leo|signo", ids)
        self.assertIn("sol|leo|planeta_en_signo", ids)

    def test_camino_de_vida_siete(self):
        seccion = _seccion(
            "El número siete",
            "Si tu camino de vida es el 7, la introspección y el estudio "
            "marcan tu manera de estar en el mundo.")
        self.assertIn("7|camino_de_vida", self._ids(seccion))

    def test_planeta_en_casa(self):
        seccion = _seccion(
            "Venus en la carta",
            "Venus en casa 7 trae el vínculo de pareja al centro del mapa "
            "natal y suaviza los tratos.")
        self.assertIn("venus|casa7|planeta_en_casa", self._ids(seccion))

    def test_titulo_apunta_a_entidad(self):
        seccion = _seccion(
            "The High Priestess",
            "This figure keeps the veil between the seen and the unseen, "
            "guarding intuition and silent knowledge.")
        self.assertIn("tarot-mayor-03", self._ids(seccion))


if __name__ == "__main__":
    unittest.main()
