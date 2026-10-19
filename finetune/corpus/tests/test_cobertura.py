"""Tests del módulo cobertura: matriz de entidades × facetas y fuentes que las respaldan."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura


class CatalogoEntidades(unittest.TestCase):
    """Catálogo de entidades de la ola activa: recuentos, ids y facetas."""

    def setUp(self):
        self.entidades = cobertura.entidades()

    def _por_familia(self):
        cuenta = {}
        for e in self.entidades:
            cuenta[e["familia"]] = cuenta.get(e["familia"], 0) + 1
        return cuenta

    def _por_subtipo(self):
        cuenta = {}
        for e in self.entidades:
            cuenta[e["subtipo"]] = cuenta.get(e["subtipo"], 0) + 1
        return cuenta

    def test_recuento_por_familia(self):
        self.assertEqual(self._por_familia(), {
            "tarot": 78,
            "baraja_espanola": 40,
            "astrologia": 477,
            "numerologia": 72,
        })

    def test_recuento_por_subtipo(self):
        self.assertEqual(self._por_subtipo(), {
            "carta_tarot": 78,
            "naipe_espanol": 40,
            "signo": 12,
            "planeta_en_signo": 120,
            "planeta_en_casa": 120,
            "aspecto": 225,
            "numero_posicion": 72,
        })

    def test_ids_unicos_y_no_vacios(self):
        ids = [e["entidad_id"] for e in self.entidades]
        self.assertEqual(len(ids), len(set(ids)), "hay entidad_id duplicados")
        self.assertTrue(all(i and i.strip() for i in ids), "hay entidad_id vacíos")

    def test_convencion_de_ids(self):
        ids = {e["entidad_id"] for e in self.entidades}
        esperados = {
            "tarot-mayor-01", "tarot-copas-10",
            "naipe-oros-05", "naipe-espadas-10",
            "aries|signo", "piscis|signo",
            "sol|aries|planeta_en_signo", "pluton|piscis|planeta_en_signo",
            "sol|casa3|planeta_en_casa", "luna|casa12|planeta_en_casa",
            "sol|conjuncion|luna|aspecto", "saturno|oposicion|neptuno|aspecto",
            "7|camino_de_vida", "11|destino", "22|anio_personal", "33|mes_personal",
        }
        faltan = esperados - ids
        self.assertEqual(faltan, set(), f"faltan entidad_id esperados: {faltan}")

    def test_facetas_por_familia_no_vacias(self):
        for familia in ("tarot", "baraja_espanola", "astrologia", "numerologia"):
            facetas = cobertura.FACETAS_POR_FAMILIA[familia]
            self.assertTrue(facetas, f"facetas vacías para {familia}")
            self.assertIn("significado_general", facetas)

    def test_derecha_invertida_solo_en_naipes(self):
        self.assertIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["tarot"])
        self.assertIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["baraja_espanola"])
        self.assertNotIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["astrologia"])
        self.assertNotIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["numerologia"])

    def test_nombre_legible_presente(self):
        for e in self.entidades:
            self.assertTrue(e.get("nombre"), f"sin nombre legible: {e['entidad_id']}")

    def test_facetas_sin_duplicados(self):
        for familia, facetas in cobertura.FACETAS_POR_FAMILIA.items():
            self.assertEqual(len(facetas), len(set(facetas)), f"facetas duplicadas en {familia}")


if __name__ == "__main__":
    unittest.main()
