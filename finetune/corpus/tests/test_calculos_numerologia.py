#!/usr/bin/env python3
"""Tests para calculos/numerologia.py (C1.5)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from calculos.numerologia import (
    reducir,
    camino_de_vida,
    expresion,
    alma,
    personalidad,
    anio_personal,
    mes_personal,
    dia_personal,
    compatibilidad,
    perfil_completo,
)


class ReducirTests(unittest.TestCase):
    def test_reduce_simple(self):
        self.assertEqual(reducir(10), 1)
        self.assertEqual(reducir(27), 9)
        self.assertEqual(reducir(99), 9)

    def test_maestros_conservados(self):
        self.assertEqual(reducir(11, maestros=True), 11)
        self.assertEqual(reducir(22, maestros=True), 22)
        self.assertEqual(reducir(33, maestros=True), 33)

    def test_maestros_no_conservados(self):
        self.assertEqual(reducir(11, maestros=False), 2)
        self.assertEqual(reducir(22, maestros=False), 4)
        self.assertEqual(reducir(33, maestros=False), 6)


class CaminoDeVidaTests(unittest.TestCase):
    def test_casos_referencia(self):
        # Por componentes: día, mes, año por separado conservando maestros en componentes
        self.assertEqual(camino_de_vida("1963-11-06"), 9)   # 6+11+10=27→9 (11 se conserva en mes)
        self.assertEqual(camino_de_vida("1960-02-29"), 2)   # 2+2+7=11→2 (11 se conserva en año? 1960=16→7, 2+2+7=11→2)
        self.assertEqual(camino_de_vida("1992-11-29"), 7)   # 11+11+3=25→7 (11 se conserva en día y mes)
        self.assertEqual(camino_de_vida("1985-07-04"), 7)   # 4+7+5=16→7


class ExpresionAlmaPersonalidadTests(unittest.TestCase):
    def test_ana(self):
        self.assertEqual(expresion("Ana"), 7)      # A=1, N=5, A=1 → 7
        self.assertEqual(alma("Ana"), 2)           # A, A → 1+1=2
        self.assertEqual(personalidad("Ana"), 5)   # N → 5

    def test_maria_lopez(self):
        # María López → MARIALOPEZ (sin tildes, sin espacios)
        # M=4, A=1, R=9, I=9, A=1, L=3, O=6, P=7, E=5, Z=8
        # Suma = 4+1+9+9+1+3+6+7+5+8 = 53 → 5+3=8
        self.assertEqual(expresion("María López"), 8)
        # Alma: A, I, A, O, E → 1+9+1+6+5 = 22 (maestro, se conserva)
        self.assertEqual(alma("María López"), 22)
        # Personalidad: M, R, L, P, Z → 4+9+3+7+8 = 31 → 4
        self.assertEqual(personalidad("María López"), 4)


class AnioMesDiaPersonalTests(unittest.TestCase):
    def test_anio_personal(self):
        # 1963-11-06, 2026 → día 6 + mes 11 + 2026(2+0+2+6=10→1) = 6+11+1=18→9
        self.assertEqual(anio_personal("1963-11-06", 2026), 9)

    def test_mes_personal(self):
        # anio_personal(1963-11-06, 2026)=9, mes 10→1, 9+1=10→1
        self.assertEqual(mes_personal("1963-11-06", 2026, 10), 1)

    def test_dia_personal(self):
        # mes_personal=1, día 15→6, 1+6=7
        self.assertEqual(dia_personal("1963-11-06", 2026, 10, 15), 7)


class CompatibilidadTests(unittest.TestCase):
    def test_tabla_simetrica(self):
        # La tabla es simétrica
        res1 = compatibilidad("1990-01-01", "1990-02-02")
        res2 = compatibilidad("1990-02-02", "1990-01-01")
        self.assertEqual(res1["nivel"], res2["nivel"])
        self.assertEqual(res1["camino_a"], res2["camino_b"])
        self.assertEqual(res1["camino_b"], res2["camino_a"])

    def test_niveles_validos(self):
        for _ in range(10):
            res = compatibilidad("1990-01-01", "1992-03-03")
            self.assertIn(res["nivel"], ["alta", "media", "baja"])


class PerfilCompletoTests(unittest.TestCase):
    def test_estructura_completa(self):
        perfil = perfil_completo("Ana", "1990-01-01", 2026)
        claves_esperadas = [
            "camino_de_vida", "expresion", "alma", "personalidad",
            "anio_personal", "mes_personal", "dia_personal"
        ]
        for k in claves_esperadas:
            self.assertIn(k, perfil)


if __name__ == "__main__":
    unittest.main()
