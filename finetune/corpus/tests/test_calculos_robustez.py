#!/usr/bin/env python3
"""Tests de robustez para calculos/ (T40): 29-feb, bisiestos, fechas inválidas, polos.

Cubre el defecto verificado en revolucion_solar con nacidos el 29-feb y la
validación de fechas realmente inválidas (30-feb, mes 13, 1900 no bisiesto),
más la degradación con aviso en latitudes polares donde Placidus falla.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import swisseph as swe
    SWISSEPH_AVAILABLE = True
except ImportError:
    SWISSEPH_AVAILABLE = False

from calculos.astro import (
    carta_natal,
    transitos,
    transitos_periodo,
    revolucion_solar,
    sinastria,
)
from calculos.biorritmos import biorritmos
from calculos.numerologia import camino_de_vida, anio_personal


@unittest.skipUnless(SWISSEPH_AVAILABLE, "swisseph no disponible")
class RevolucionSolarBisiestoTests(unittest.TestCase):
    """El retorno solar se busca por longitud del Sol, no por fecha de calendario."""

    def test_29_feb_2000_no_reventar_en_ano_no_bisiesto(self):
        """Nacido 2000-02-29: RS en 2026 (no bisiesto) no lanza y es exacta."""
        res = revolucion_solar("2000-02-29", "12:00", 40.4, -3.7, "Europe/Madrid", 2026)
        self.assertLess(abs(res["diferencia_arco"]), 0.001)

    def test_29_feb_retorno_cae_28feb_o_1mar_en_ano_no_bisiesto(self):
        """En 2026 el Sol vuelve al 29-feb-natal sobre el 28-feb o 1-mar."""
        res = revolucion_solar("2000-02-29", "12:00", 40.4, -3.7, "Europe/Madrid", 2026)
        fecha_ut = res["instante_ut"][:10]
        self.assertIn(fecha_ut, ["2026-02-27", "2026-02-28", "2026-03-01", "2026-03-02"])

    def test_29_feb_coherente_con_28feb_y_1mar(self):
        """RS de nacidos 28-feb, 29-feb, 1-mar: todas válidas y en ventana coherente."""
        res_28 = revolucion_solar("2000-02-28", "12:00", 40.4, -3.7, "Europe/Madrid", 2026)
        res_29 = revolucion_solar("2000-02-29", "12:00", 40.4, -3.7, "Europe/Madrid", 2026)
        res_01 = revolucion_solar("2000-03-01", "12:00", 40.4, -3.7, "Europe/Madrid", 2026)
        for res in (res_28, res_29, res_01):
            self.assertLess(abs(res["diferencia_arco"]), 0.001)
        # Los instantes son distintos (soles natales distintos) y ordenados:
        # 28-feb < 29-feb < 1-mar en día juliano del retorno.
        self.assertLess(res_28["instante_ut"], res_29["instante_ut"])
        self.assertLess(res_29["instante_ut"], res_01["instante_ut"])

    def test_29_feb_en_ano_bisiesto_cae_29feb(self):
        """RS en año bisiesto (2028) cae sobre 29-feb."""
        res = revolucion_solar("2000-02-29", "12:00", 40.4, -3.7, "Europe/Madrid", 2028)
        fecha_ut = res["instante_ut"][:10]
        self.assertIn(fecha_ut, ["2028-02-28", "2028-02-29", "2028-03-01"])
        self.assertLess(abs(res["diferencia_arco"]), 0.001)

    def test_29_feb_1996_y_1904_funcionan(self):
        """Otros 29-feb válidos (1996, 1904) calculan RS sin romperse."""
        for anio_nac, anio_rs in ((1996, 2026), (1904, 2026)):
            res = revolucion_solar(f"{anio_nac}-02-29", "12:00", 40.4, -3.7, "Europe/Madrid", anio_rs)
            self.assertLess(abs(res["diferencia_arco"]), 0.001)


@unittest.skipUnless(SWISSEPH_AVAILABLE, "swisseph no disponible")
class FechasInvalidasAstroTests(unittest.TestCase):
    """Fechas realmente inválidas dan ValueError con mensaje en español."""

    def _assert_error_es(self, fn, *args):
        with self.assertRaises(ValueError) as cm:
            fn(*args)
        msg = str(cm.exception)
        self.assertIn("inválida", msg)
        # No debe quedar el mensaje en inglés de strptime
        self.assertNotIn("out of range", msg)
        self.assertNotIn("does not match format", msg)

    def test_carta_natal_30_feb(self):
        self._assert_error_es(carta_natal, "2001-02-30", "12:00", 40.4, -3.7, "UTC")

    def test_carta_natal_mes_13(self):
        self._assert_error_es(carta_natal, "2000-13-01", "12:00", 40.4, -3.7, "UTC")

    def test_carta_natal_1900_no_bisiesto_rechazado(self):
        """1900 NO fue bisiesto: 29-feb-1900 debe rechazarse."""
        self._assert_error_es(carta_natal, "1900-02-29", "12:00", 40.4, -3.7, "UTC")

    def test_carta_natal_1904_bisiesto_valido(self):
        """1904 sí fue bisiesto: 29-feb-1904 es válido."""
        res = carta_natal("1904-02-29", "12:00", 40.4, -3.7, "UTC")
        self.assertEqual(len(res["planetas"]), 10)

    def test_transitos_fecha_invalida(self):
        natal = carta_natal("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        self._assert_error_es(transitos, natal, "2001-02-30")

    def test_transitos_periodo_desde_invalido(self):
        natal = carta_natal("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        self._assert_error_es(transitos_periodo, natal, "2025-02-30", "2025-12-31")

    def test_transitos_periodo_paso_cero_no_bucle_infinito(self):
        """paso_dias=0 debe rechazarse, no colgar en bucle infinito."""
        natal = carta_natal("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        with self.assertRaises(ValueError):
            transitos_periodo(natal, "2025-01-01", "2025-12-31", paso_dias=0)

    def test_revolucion_solar_fecha_natal_invalida(self):
        self._assert_error_es(
            revolucion_solar, "2001-02-30", "12:00", 40.4, -3.7, "UTC", 2026
        )


@unittest.skipUnless(SWISSEPH_AVAILABLE, "swisseph no disponible")
class PolosDegradanTests(unittest.TestCase):
    """En latitudes polares Placidus falla: se degrada a casas iguales con aviso."""

    def test_lat_78_no_rompe_con_aviso(self):
        res = carta_natal("2000-02-29", "12:00", 78.0, 15.0, "UTC")
        self.assertEqual(len(res["casas"]), 12)
        self.assertTrue(res.get("aviso_casas"), "debe avisar del fallback de casas")

    def test_lat_85_no_rompe_con_aviso(self):
        res = carta_natal("2000-06-21", "00:00", 85.0, 0.0, "UTC")
        self.assertEqual(len(res["casas"]), 12)
        self.assertTrue(res.get("aviso_casas"))

    def test_latitud_normal_sin_aviso(self):
        res = carta_natal("1990-06-15", "12:00", 40.4, -3.7, "UTC")
        self.assertFalse(res.get("aviso_casas"))


@unittest.skipUnless(SWISSEPH_AVAILABLE, "swisseph no disponible")
class HoraYzonaTests(unittest.TestCase):
    def test_hora_00_00_valida(self):
        res = carta_natal("2000-02-29", "00:00", 40.4, -3.7, "Europe/Madrid")
        self.assertEqual(len(res["planetas"]), 10)

    def test_hora_invalida_error_es(self):
        with self.assertRaises(ValueError) as cm:
            carta_natal("2000-02-29", "25:00", 40.4, -3.7, "Europe/Madrid")
        self.assertIn("válida", str(cm.exception))

    def test_zona_horaria_inexistente_error_es(self):
        with self.assertRaises(ValueError) as cm:
            carta_natal("2000-02-29", "12:00", 40.4, -3.7, "Marte/Olympus_Mons")
        self.assertIn("horaria", str(cm.exception))


class BiorritmosRobustezTests(unittest.TestCase):
    def test_29_feb_dias_correctos(self):
        from datetime import date
        esperado = (date(2026, 3, 1) - date(2000, 2, 29)).days
        res = biorritmos("2000-02-29", "2026-03-01")
        self.assertEqual(res["dias_desde_nacimiento"], esperado)

    def test_fecha_invalida_error_es(self):
        with self.assertRaises(ValueError) as cm:
            biorritmos("2001-02-30", "2026-03-01")
        self.assertIn("inválida", str(cm.exception))
        self.assertNotIn("out of range", str(cm.exception))

    def test_mes_13_error_es(self):
        with self.assertRaises(ValueError) as cm:
            biorritmos("2000-13-01", "2026-03-01")
        self.assertIn("inválida", str(cm.exception))

    def test_1900_29_feb_rechazado(self):
        with self.assertRaises(ValueError) as cm:
            biorritmos("1900-02-29", "2026-03-01")
        self.assertIn("inválida", str(cm.exception))


class NumerologiaRobustezTests(unittest.TestCase):
    def test_camino_vida_29_feb(self):
        self.assertIn(camino_de_vida("2000-02-29"), range(1, 10))

    def test_anio_personal_29_feb(self):
        self.assertIn(anio_personal("2000-02-29", 2026), range(1, 10))

    def test_fecha_invalida_error_es(self):
        with self.assertRaises(ValueError) as cm:
            camino_de_vida("2001-02-30")
        self.assertIn("inválida", str(cm.exception))
        self.assertNotIn("out of range", str(cm.exception))

    def test_1900_29_feb_rechazado(self):
        with self.assertRaises(ValueError) as cm:
            camino_de_vida("1900-02-29")
        self.assertIn("inválida", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
