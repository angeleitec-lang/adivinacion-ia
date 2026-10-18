#!/usr/bin/env python3
"""Tests para calculos/biorritmos.py (C1.6)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from calculos.biorritmos import biorritmos


class BiorritmosTests(unittest.TestCase):
    def test_t0_todos_cero(self):
        """t=0 ⇒ los tres 0%."""
        res = biorritmos("1990-01-01", "1990-01-01")
        for ciclo in ["fisico", "emocional", "intelectual"]:
            self.assertEqual(res["ciclos"][ciclo]["porcentaje"], 0)
            self.assertEqual(res["ciclos"][ciclo]["fase"], "crítico")

    def test_t_p4_fisico_100(self):
        """t = P/4 para físico (23/4 = 5.75 → redondeo, usamos t=6 para aprox 100%)."""
        # El ciclo físico es 23 días, P/4 = 5.75 → t=6 da ~sin(2π*6/23) ≈ 0.99 ≈ 100%
        res = biorritmos("1990-01-01", "1990-01-07")
        self.assertGreaterEqual(abs(res["ciclos"]["fisico"]["porcentaje"]), 90)

    def test_t_p4_emocional_100(self):
        """t = 7 para emocional (28/4 = 7) ⇒ 100%."""
        res = biorritmos("1990-01-01", "1990-01-08")
        self.assertEqual(res["ciclos"]["emocional"]["porcentaje"], 100)

    def test_t_p2_emocional_critico(self):
        """t = 14 para emocional (28/2 = 14) ⇒ crítico."""
        res = biorritmos("1990-01-01", "1990-01-15")
        self.assertEqual(res["ciclos"]["emocional"]["porcentaje"], 0)
        self.assertEqual(res["ciclos"]["emocional"]["fase"], "crítico")

    def test_fecha_anterior_error(self):
        """Fecha anterior al nacimiento ⇒ ValueError."""
        with self.assertRaises(ValueError):
            biorritmos("1990-01-01", "1989-12-31")

    def test_ventana_dias(self):
        """Opción dias=N devuelve ventana de N días."""
        res = biorritmos("1990-01-01", "1990-01-01", dias=3)
        self.assertIn("ventana", res)
        self.assertEqual(len(res["ventana"]), 3)
        for dia in res["ventana"]:
            self.assertIn("fecha", dia)
            # Los ciclos están directamente en el día, no bajo "ciclos"
            self.assertIn("fisico", dia)
            self.assertIn("emocional", dia)
            self.assertIn("intelectual", dia)
            self.assertIn("dias_desde_nacimiento", dia)


if __name__ == "__main__":
    unittest.main()
