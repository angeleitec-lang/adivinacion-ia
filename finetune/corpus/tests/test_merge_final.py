"""Tests de merge_final: extracción del tema del prompt y descarte de pares basura."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from merge_final import extraer_tema, is_junk_pair


def fila(human: str, gpt: str) -> dict:
    return {"conversations": [
        {"from": "human", "value": human},
        {"from": "gpt", "value": gpt},
    ]}


RESPUESTA_VALIDA = ("El tarot es una baraja de 78 cartas; el arcano mayor "
                   "representa arquetipos del camino del alma.")


class TestExtraerTema(unittest.TestCase):
    def test_plantilla_dos_puntos(self):
        self.assertEqual(extraer_tema("Explica en detalle: Sección 3."), "Sección 3")

    def test_plantilla_que_significa(self):
        self.assertEqual(extraer_tema("¿Qué significa Referencias?"), "Referencias")

    def test_plantilla_expliname_de_forma(self):
        self.assertEqual(
            extraer_tema("Explícame El Loco de forma clara y completa."), "El Loco")

    def test_plantilla_habla_de(self):
        self.assertEqual(extraer_tema("Háblame del Tarot de Marsella."), "Tarot de Marsella")

    def test_plantilla_desarrollame(self):
        self.assertEqual(
            extraer_tema("Como experta en adivinación, desarróllame la carta El Colgado."),
            "la carta El Colgado")

    def test_sin_plantilla_frase_completa(self):
        self.assertEqual(extraer_tema("el tarot de marsella"), "el tarot de marsella")

    def test_tema_con_separador_mayor(self):
        self.assertEqual(
            extraer_tema("Explica en detalle: Arcanos > El Loco."), "Arcanos > El Loco")


class TestIsJunkPair(unittest.TestCase):
    def test_seccion_es_junk(self):
        self.assertTrue(is_junk_pair(fila("Explica en detalle: Sección 3.", RESPUESTA_VALIDA)))

    def test_referencias_es_junk(self):
        self.assertTrue(is_junk_pair(fila("¿Qué significa Referencias?", RESPUESTA_VALIDA)))

    def test_segmento_malo_en_jerarquia_es_junk(self):
        self.assertTrue(is_junk_pair(
            fila("Explica en detalle: El Loco > Referencias.", RESPUESTA_VALIDA)))

    def test_tema_valido_no_es_junk(self):
        self.assertFalse(is_junk_pair(
            fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA)))

    def test_tema_corto_es_junk(self):
        self.assertTrue(is_junk_pair(fila("¿Qué significa X?", RESPUESTA_VALIDA)))

    def test_tema_vacio_es_junk(self):
        self.assertTrue(is_junk_pair(fila("", RESPUESTA_VALIDA)))

    def test_sin_terminos_de_dominio_es_junk(self):
        self.assertTrue(is_junk_pair(
            fila("Explícame El Loco de forma clara y completa.", "Texto sin anclaje alguno.")))

    def test_seccion_numerada_en_texto_humano_sigue_descartando(self):
        self.assertTrue(is_junk_pair(
            fila("Háblame de la Sección 12 del manual.", RESPUESTA_VALIDA)))


if __name__ == "__main__":
    unittest.main()
