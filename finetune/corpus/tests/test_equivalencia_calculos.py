import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import unittest

import generate_tasks as gt
from calculos import numerologia as calc_num

# 208 fechas 1940-2010: aleatorias + todos los 29 de febrero del rango +
# componentes maestros (día 11/22/29, mes 11, años con suma 11/22 como 1993 y 2009).
_RNG = random.Random(7)
FECHAS_EQUIVALENCIA = [
    f"{_RNG.randint(1940, 2010):04d}-{_RNG.randint(1, 12):02d}-{_RNG.randint(1, 28):02d}"
    for _ in range(190)
] + [
    "1940-02-29", "1944-02-29", "1948-02-29", "1952-02-29", "1956-02-29",
    "1960-02-29", "1964-02-29", "1968-02-29", "1972-02-29", "1976-02-29",
    "1980-02-29", "1984-02-29", "1988-02-29", "1992-02-29", "1996-02-29",
    "2000-02-29", "2004-02-29", "2008-02-29",
    "1990-11-11", "1990-11-22", "1990-11-29", "1999-11-11", "1999-11-22",
    "2000-11-22", "2000-11-29", "1993-05-17", "2009-05-17", "1993-11-11",
    "2009-11-22", "1990-02-22",
]

NOMBRES_EQUIVALENCIA = [
    "María López", "Ángel González", "Iñaki Etxeberria", "José Núñez",
    "Müller Hans", "François Übeda", "Zoë Martín", "Björk Guðmundsdóttir",
    "Concepción Rodríguez-Prieto", "Ñu", "Álvaro de Torres y Villarroel",
    "Íñigo López de Mendoza", "Úrsula Peréz", "Ernesto Nogueira",
    "Aarón Méndez", "Compunción Álvarez", "Sancho Sánchez", "Dña. Elvira",
    "María del Carmen Fernández de la Vega", "Jesús Navas", "Àlex Costa",
    "Rúben Dos Santos", "Güendi Ortega", "Ísabel de Borbón", "Nuño Álvarez",
]


class TestEquivalenciaNumerologia(unittest.TestCase):
    def setUp(self):
        self.assertGreaterEqual(len(FECHAS_EQUIVALENCIA), 200)
        self.assertGreaterEqual(len(NOMBRES_EQUIVALENCIA), 20)

    def test_camino_de_vida_igual(self):
        for fecha in FECHAS_EQUIVALENCIA:
            with self.subTest(fecha=fecha):
                self.assertEqual(gt.camino_de_vida(fecha), calc_num.camino_de_vida(fecha))

    def test_anio_personal_igual(self):
        for fecha in FECHAS_EQUIVALENCIA:
            with self.subTest(fecha=fecha):
                self.assertEqual(
                    gt.anio_personal(fecha, 2026), calc_num.anio_personal(fecha, 2026)
                )

    def test_expresion_igual(self):
        for nombre in NOMBRES_EQUIVALENCIA:
            with self.subTest(nombre=nombre):
                self.assertEqual(
                    gt.reducir(gt.letras_valor(nombre)), calc_num.expresion(nombre)
                )

    def test_alma_y_personalidad_iguales(self):
        for nombre in NOMBRES_EQUIVALENCIA:
            with self.subTest(nombre=nombre):
                self.assertEqual(
                    gt.vocales_consonantes(nombre),
                    (calc_num.alma(nombre), calc_num.personalidad(nombre)),
                )


if __name__ == "__main__":
    unittest.main()
