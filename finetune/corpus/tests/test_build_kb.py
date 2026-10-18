#!/usr/bin/env python3
"""Tests de la KB: arcanos menores escritos a mano (T7.1)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import build_kb

FRASE_GENERICA = "Energía bloqueada o en exceso dentro de su ámbito."
CLAVES_CONTEXTO = ("amor", "trabajo", "dinero", "salud")
ELEMENTO_PALO = {"Bastos": "fuego", "Copas": "agua", "Espadas": "aire", "Oros": "tierra"}


class TestMenoresEscritos(unittest.TestCase):
    def setUp(self):
        self.menores = build_kb.MENORES

    def test_cincuenta_y_seis_menores(self):
        self.assertEqual(len(self.menores), 56)

    def test_nombres_unicos(self):
        nombres = [c["nombre"] for c in self.menores]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_usa_caballero_no_caballo(self):
        for c in self.menores:
            self.assertNotIn("Caballo", c["nombre"])
            self.assertNotIn("Caballo", c["rango"])

    def test_invertidas_unicas_y_no_genericas(self):
        invertidas = [c["invertida"] for c in self.menores]
        self.assertEqual(len(invertidas), len(set(invertidas)))
        for c in self.menores:
            self.assertNotEqual(c["invertida"], FRASE_GENERICA)

    def test_palabras_clave_cuatro_especificas(self):
        for c in self.menores:
            self.assertEqual(len(c["palabras_clave"]), 4, c["nombre"])

    def test_significado_sin_plantilla(self):
        for c in self.menores:
            self.assertNotIn("en el ámbito de", c["significado"])

    def test_contextos_completos(self):
        for c in self.menores:
            ctx = c.get("contextos", {})
            for k in CLAVES_CONTEXTO:
                self.assertTrue(ctx.get(k), f"{c['nombre']}: falta contexto {k}")

    def test_numero_y_palo_coherentes(self):
        self.assertEqual(sorted(c["numero"] for c in self.menores), list(range(1, 15)) * 4)
        for c in self.menores:
            self.assertEqual(c["elemento"], ELEMENTO_PALO[c["palo"]])


if __name__ == "__main__":
    unittest.main()
