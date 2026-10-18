import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import expand_wikipedia


class TestPriorizar(unittest.TestCase):
    def test_raices_antes_que_subcategorias(self):
        datos = {
            "Runas": {"raiz": False, "paginas": ["Fehu", "Uruz"]},
            "Tarot": {"raiz": True, "paginas": ["Zodiaco y tarot", "Arcanos"]},
        }
        self.assertEqual(
            expand_wikipedia.priorizar(datos, 10),
            ["Arcanos", "Zodiaco y tarot", "Fehu", "Uruz"],
        )

    def test_orden_de_categorias_raiz_es_el_de_insercion(self):
        datos = {
            "Tarot": {"raiz": True, "paginas": ["Tarot de Marsella"]},
            "Astrología": {"raiz": True, "paginas": ["Signos"]},
        }
        self.assertEqual(
            expand_wikipedia.priorizar(datos, 10),
            ["Tarot de Marsella", "Signos"],
        )

    def test_dedupe_preserva_prioridad(self):
        datos = {
            "Tarot": {"raiz": True, "paginas": ["Loco"]},
            "Sub": {"raiz": False, "paginas": ["Loco", "Fehu"]},
        }
        self.assertEqual(expand_wikipedia.priorizar(datos, 10), ["Loco", "Fehu"])

    def test_max_recorta_la_seleccion(self):
        datos = {
            "A": {"raiz": True, "paginas": ["a1", "a2"]},
            "B": {"raiz": True, "paginas": ["b1"]},
        }
        self.assertEqual(expand_wikipedia.priorizar(datos, 2), ["a1", "a2"])


if __name__ == "__main__":
    unittest.main()
