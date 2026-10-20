import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import unittest

import generate_tasks as gt
from calculos import numerologia as calc_num
from calculos.astro import carta_natal

# Literales congelados del código viejo de generate_tasks.py (truncado de minutos),
# generados antes de la unificación. Son la referencia de no-regresión.
CONGELADO_VIEJO = {
    "lima_1990": {
        "planetas": {
            "Sol": {"signo": "Géminis", "grados": "24°19'", "casa": 10},
            "Luna": {"signo": "Piscis", "grados": "18°08'", "casa": 6},
            "Mercurio": {"signo": "Géminis", "grados": "6°02'", "casa": 9},
            "Venus": {"signo": "Tauro", "grados": "19°01'", "casa": 8},
            "Marte": {"signo": "Aries", "grados": "11°11'", "casa": 7},
            "Júpiter": {"signo": "Cáncer", "grados": "15°56'", "casa": 10},
            "Saturno": {"signo": "Capricornio", "grados": "24°01'", "casa": 5},
            "Urano": {"signo": "Capricornio", "grados": "8°09'", "casa": 4},
            "Neptuno": {"signo": "Capricornio", "grados": "13°42'", "casa": 4},
            "Plutón": {"signo": "Escorpio", "grados": "15°23'", "casa": 2},
        },
        "ascendente": {"signo": "Virgo", "grados": "20°01'"},
        "mc": {"signo": "Géminis", "grados": "22°21'"},
        "aspectos": [("Júpiter", "Plutón", "trígono"), ("Luna", "Venus", "sextil"), ("Neptuno", "Plutón", "sextil"), ("Luna", "Júpiter", "trígono"), ("Júpiter", "Neptuno", "oposición"), ("Marte", "Neptuno", "cuadratura"), ("Luna", "Plutón", "trígono"), ("Marte", "Urano", "cuadratura"), ("Venus", "Júpiter", "sextil"), ("Venus", "Plutón", "oposición"), ("Luna", "Neptuno", "sextil"), ("Marte", "Júpiter", "cuadratura"), ("Venus", "Saturno", "trígono"), ("Venus", "Neptuno", "trígono")],
    },
    "madrid_dst": {
        "planetas": {
            "Sol": {"signo": "Cáncer", "grados": "9°46'", "casa": 10},
            "Luna": {"signo": "Acuario", "grados": "1°32'", "casa": 5},
            "Mercurio": {"signo": "Géminis", "grados": "19°49'", "casa": 10},
            "Venus": {"signo": "Géminis", "grados": "14°07'", "casa": 10},
            "Marte": {"signo": "Piscis", "grados": "23°49'", "casa": 7},
            "Júpiter": {"signo": "Tauro", "grados": "26°08'", "casa": 9},
            "Saturno": {"signo": "Sagitario", "grados": "28°26'", "casa": 4},
            "Urano": {"signo": "Sagitario", "grados": "28°36'", "casa": 4},
            "Neptuno": {"signo": "Capricornio", "grados": "8°47'", "casa": 4},
            "Plutón": {"signo": "Escorpio", "grados": "9°51'", "casa": 3},
        },
        "ascendente": {"signo": "Virgo", "grados": "10°54'"},
        "mc": {"signo": "Géminis", "grados": "7°45'"},
        "aspectos": [("Sol", "Plutón", "trígono"), ("Saturno", "Urano", "conjunción"), ("Sol", "Neptuno", "oposición"), ("Neptuno", "Plutón", "sextil"), ("Marte", "Júpiter", "sextil"), ("Mercurio", "Marte", "cuadratura"), ("Marte", "Saturno", "cuadratura"), ("Marte", "Urano", "cuadratura"), ("Luna", "Júpiter", "trígono"), ("Mercurio", "Venus", "conjunción")],
    },
    "reykjavik_alta_lat": {
        "planetas": {
            "Sol": {"signo": "Aries", "grados": "0°00'", "casa": 1},
            "Luna": {"signo": "Cáncer", "grados": "5°11'", "casa": 7},
            "Mercurio": {"signo": "Piscis", "grados": "6°42'", "casa": 1},
            "Venus": {"signo": "Tauro", "grados": "1°37'", "casa": 2},
            "Marte": {"signo": "Acuario", "grados": "13°36'", "casa": 1},
            "Júpiter": {"signo": "Aries", "grados": "0°37'", "casa": 1},
            "Saturno": {"signo": "Cáncer", "grados": "11°59'", "casa": 7},
            "Urano": {"signo": "Escorpio", "grados": "1°40'", "casa": 8},
            "Neptuno": {"signo": "Sagitario", "grados": "11°46'", "casa": 10},
            "Plutón": {"signo": "Libra", "grados": "8°06'", "casa": 7},
        },
        "ascendente": {"signo": "Capricornio", "grados": "2°37'"},
        "mc": {"signo": "Sagitario", "grados": "7°57'"},
        "aspectos": [("Venus", "Urano", "oposición"), ("Sol", "Júpiter", "conjunción"), ("Luna", "Mercurio", "trígono"), ("Marte", "Neptuno", "sextil"), ("Luna", "Plutón", "cuadratura"), ("Luna", "Urano", "trígono"), ("Luna", "Venus", "sextil"), ("Neptuno", "Plutón", "sextil"), ("Saturno", "Plutón", "cuadratura"), ("Luna", "Júpiter", "cuadratura"), ("Mercurio", "Urano", "trígono"), ("Mercurio", "Neptuno", "cuadratura"), ("Sol", "Luna", "cuadratura"), ("Mercurio", "Saturno", "trígono")],
    },
    "buenos_aires_1962": {
        "planetas": {
            "Sol": {"signo": "Leo", "grados": "22°38'", "casa": 6},
            "Luna": {"signo": "Acuario", "grados": "24°33'", "casa": 12},
            "Mercurio": {"signo": "Virgo", "grados": "9°04'", "casa": 6},
            "Venus": {"signo": "Libra", "grados": "7°47'", "casa": 7},
            "Marte": {"signo": "Géminis", "grados": "25°46'", "casa": 4},
            "Júpiter": {"signo": "Piscis", "grados": "9°42'", "casa": 12},
            "Saturno": {"signo": "Acuario", "grados": "6°57'", "casa": 11},
            "Urano": {"signo": "Virgo", "grados": "0°21'", "casa": 6},
            "Neptuno": {"signo": "Escorpio", "grados": "10°52'", "casa": 8},
            "Plutón": {"signo": "Virgo", "grados": "9°15'", "casa": 6},
        },
        "ascendente": {"signo": "Piscis", "grados": "19°56'"},
        "mc": {"signo": "Sagitario", "grados": "18°58'"},
        "aspectos": [("Mercurio", "Plutón", "conjunción"), ("Júpiter", "Plutón", "oposición"), ("Mercurio", "Júpiter", "oposición"), ("Venus", "Saturno", "trígono"), ("Luna", "Marte", "trígono"), ("Júpiter", "Neptuno", "trígono"), ("Neptuno", "Plutón", "sextil"), ("Mercurio", "Neptuno", "sextil"), ("Sol", "Luna", "oposición"), ("Sol", "Marte", "sextil"), ("Saturno", "Neptuno", "cuadratura"), ("Marte", "Urano", "sextil"), ("Luna", "Urano", "oposición")],
    },
    "sidney_1955": {
        "planetas": {
            "Sol": {"signo": "Sagitario", "grados": "7°44'", "casa": 1},
            "Luna": {"signo": "Géminis", "grados": "22°25'", "casa": 8},
            "Mercurio": {"signo": "Sagitario", "grados": "5°35'", "casa": 1},
            "Venus": {"signo": "Capricornio", "grados": "0°43'", "casa": 2},
            "Marte": {"signo": "Escorpio", "grados": "1°05'", "casa": 12},
            "Júpiter": {"signo": "Virgo", "grados": "1°01'", "casa": 10},
            "Saturno": {"signo": "Escorpio", "grados": "25°26'", "casa": 1},
            "Urano": {"signo": "Leo", "grados": "2°06'", "casa": 9},
            "Neptuno": {"signo": "Libra", "grados": "29°22'", "casa": 12},
            "Plutón": {"signo": "Leo", "grados": "28°36'", "casa": 10},
        },
        "ascendente": {"signo": "Escorpio", "grados": "21°23'"},
        "mc": {"signo": "Leo", "grados": "3°57'"},
        "aspectos": [("Marte", "Júpiter", "sextil"), ("Venus", "Júpiter", "trígono"), ("Venus", "Marte", "sextil"), ("Neptuno", "Plutón", "sextil"), ("Marte", "Urano", "cuadratura"), ("Venus", "Neptuno", "sextil"), ("Júpiter", "Neptuno", "sextil"), ("Marte", "Neptuno", "conjunción"), ("Sol", "Mercurio", "conjunción"), ("Venus", "Plutón", "trígono"), ("Júpiter", "Plutón", "conjunción"), ("Marte", "Plutón", "sextil"), ("Urano", "Neptuno", "cuadratura"), ("Saturno", "Plutón", "cuadratura")],
    },
}

CARTAS_EQUIVALENCIA = {
    "lima_1990": ("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima"),
    "madrid_dst": ("1988-07-01", "12:00", 40.4168, -3.7038, "Europe/Madrid"),
    "reykjavik_alta_lat": ("1975-03-21", "06:00", 64.1466, -21.9426, "Atlantic/Reykjavik"),
    "buenos_aires_1962": ("1962-08-15", "20:30", -34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
    "sidney_1955": ("1955-12-01", "03:45", -33.8688, 151.2093, "Australia/Sydney"),
}


def _minutos(grados):
    """'24°19'' -> 1459 (minutos de arco)."""
    g, m = grados.split("°")
    return int(g) * 60 + int(m.rstrip("'"))


def _adaptar(carta):
    """carta_natal() -> formato viejo de calcular_carta (sin fecha/hora)."""
    planetas = {}
    for p in carta["planetas"]:
        planetas[p["nombre"]] = {
            "signo": p["signo"],
            "grados": f"{p['grado']}°{p['minuto']:02d}'",
            "lon": p["lon"],
            "casa": p["casa"],
        }
    asc = carta["ascendente"]
    mc = carta["medio_cielo"]
    aspectos = [
        {"a": a["planeta_a"], "b": a["planeta_b"], "aspecto": a["aspecto"],
         "orbe": round(a["orbe"], 1)}
        for a in carta["aspectos"]
    ]
    return {
        "planetas": planetas,
        "ascendente": {"signo": asc["signo"], "grados": f"{asc['grado']}°{asc['minuto']:02d}'"},
        "mc": {"signo": mc["signo"], "grados": f"{mc['grado']}°{mc['minuto']:02d}'"},
        "aspectos": aspectos,
    }




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
    "2009-11-22", "1990-02-22", "2009-11-29",
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

    def test_maestros_11_22_33_cubiertos(self):
        caminos = {gt.camino_de_vida(f) for f in FECHAS_EQUIVALENCIA}
        for maestro in (11, 22, 33):
            with self.subTest(maestro=maestro):
                self.assertIn(maestro, caminos)
                self.assertIn(maestro, {calc_num.camino_de_vida(f) for f in FECHAS_EQUIVALENCIA})

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


class TestEquivalenciaCartaNatal(unittest.TestCase):
    def _comparar_con_congelado(self, carta, congelado):
        for nombre, esperado in congelado["planetas"].items():
            obtenido = carta["planetas"][nombre]
            self.assertEqual(obtenido["signo"], esperado["signo"], f"{nombre} signo")
            self.assertEqual(obtenido["casa"], esperado["casa"], f"{nombre} casa")
            self.assertLessEqual(
                abs(_minutos(obtenido["grados"]) - _minutos(esperado["grados"])), 1,
                f"{nombre} grados",
            )
        for clave in ("ascendente", "mc"):
            self.assertEqual(carta[clave]["signo"], congelado[clave]["signo"], clave)
            self.assertLessEqual(
                abs(_minutos(carta[clave]["grados"]) - _minutos(congelado[clave]["grados"])), 1,
                clave,
            )
        self.assertEqual(
            {(a["a"], a["b"], a["aspecto"]) for a in carta["aspectos"]},
            set(congelado["aspectos"]),
        )

    def test_carta_natal_vs_congelado(self):
        for nombre, params in CARTAS_EQUIVALENCIA.items():
            with self.subTest(carta=nombre):
                adaptada = _adaptar(carta_natal(*params))
                self._comparar_con_congelado(adaptada, CONGELADO_VIEJO[nombre])

    def test_calcular_carta_vs_congelado(self):
        for nombre, params in CARTAS_EQUIVALENCIA.items():
            with self.subTest(carta=nombre):
                carta = gt.calcular_carta(*params)
                self._comparar_con_congelado(carta, CONGELADO_VIEJO[nombre])


if __name__ == "__main__":
    unittest.main()
