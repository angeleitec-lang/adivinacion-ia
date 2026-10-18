"""Tests de merge_datasets: filtrado por idioma también en la base."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from merge_datasets import merge


def fila(human: str, gpt: str) -> dict:
    return {"conversations": [
        {"from": "human", "value": human},
        {"from": "gpt", "value": gpt},
    ]}


ES = "El tarot de Marsella tiene 78 cartas y 22 arcanos mayores."
EN = "The Fool card represents new beginnings and spontaneous potential."


class TestFiltroIdiomaBase(unittest.TestCase):
    def test_base_espanol_se_conserva(self):
        out, stats = merge([fila("Háblame del tarot.", ES)], [], False)
        self.assertEqual(stats["base"], 1)
        self.assertEqual(len(out), 1)

    def test_base_inglesa_se_descarta_por_defecto(self):
        out, stats = merge([fila("Tell me about tarot.", EN)], [], False)
        self.assertEqual(stats["base"], 0)
        self.assertEqual(stats["base_lang"], 1)
        self.assertEqual(len(out), 0)

    def test_keep_base_en_conserva_ingles(self):
        out, stats = merge([fila("Tell me about tarot.", EN)], [], False, keep_base_en=True)
        self.assertEqual(stats["base"], 1)
        self.assertEqual(stats.get("base_lang", 0), 0)
        self.assertEqual(len(out), 1)

    def test_include_en_no_filtra_la_base(self):
        out, stats = merge([fila("Tell me about tarot.", EN)], [], True)
        self.assertEqual(stats["base"], 1)
        self.assertEqual(len(out), 1)

    def test_con_keep_base_en_los_nuevos_siguen_filtrados(self):
        out, stats = merge([fila("Háblame del tarot.", ES)],
                          [fila("Tell me about tarot.", EN)], False, keep_base_en=True)
        self.assertEqual(stats["new_lang"], 1)
        self.assertEqual(stats["new_added"], 0)
        self.assertEqual(len(out), 1)

    def test_deduplicado_de_base_sigue_igual(self):
        out, stats = merge([fila("a", ES), fila("b", ES + " ")], [], False)
        self.assertEqual(stats["base"], 1)
        self.assertEqual(stats["base_dup"], 1)


if __name__ == "__main__":
    unittest.main()
