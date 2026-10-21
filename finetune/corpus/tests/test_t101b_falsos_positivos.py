"""T101b: falsos positivos del detector de cartas y de orientación.

Frases tomadas de `aceptadas.jsonl` reales de fase 1 (Mercury): posiciones de
la tirada, formas cortas de cartas y comparaciones de dos cartas con distinta
orientación.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402


class TestFalsosPositivosT101b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _tarea(self, bloque, cartas=None, **extra):
        payload = dict(extra)
        if cartas is not None:
            payload["cartas"] = cartas
        return ef.tarea_desde_job(bloque, payload, "¿Qué me depara?", self.kb)

    def _verificar(self, bloque, cartas, texto, **extra):
        return fp.verificar_lectura(self._tarea(bloque, cartas, **extra), texto)

    def test_posiciones_de_la_tiada_no_son_cartas(self):
        cartas = [
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "El Sol", "invertida": False},
            {"nombre": "La Luna", "invertida": False},
        ]
        texto = ("El Pasado: El Loco abre el camino. El Presente: El Sol "
                 "ilumina. El Futuro: La Luna acompaña. El Mensaje es claro.")
        ok, motivos = self._verificar("tarot_3", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_formas_cortas_y_cargos_de_la_corte(self):
        cartas = [
            {"nombre": "La Rueda de la Fortuna", "invertida": False},
            {"nombre": "Sota de Copas", "invertida": False},
            {"nombre": "Rey de Oros", "invertida": False},
        ]
        texto = ("La Rueda de la Fortuna abre el ciclo. La Sota de Copas "
                 "acompaña con ternura y el Rey de Oros sostiene la mesa. La "
                 "Rueda vuelve a girar; la Sota sonríe; el Rey calla.")
        ok, motivos = self._verificar("tarot_3", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_el_as_y_los_palos_como_formas_cortas(self):
        cartas = [{"nombre": "As de Bastos", "invertida": False}]
        texto = ("El As de Bastos abre el camino. Las Espadas y los Bastos "
                 "acompañan la lectura.")
        ok, motivos = self._verificar("tarot_1", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_sigue_rechazando_una_carta_inexistente(self):
        cartas = [{"nombre": "As de Bastos", "invertida": False}]
        texto = "El As de Bastos abre el camino. El Ocho de Estrellas lo cierra."
        ok, motivos = self._verificar("tarot_1", cartas, texto)
        self.assertFalse(ok)
        self.assertTrue(any("inexistente" in m for m in motivos), motivos)

    def test_comparacion_de_dos_cartas_no_contagia_la_orientacion(self):
        cartas = [
            {"nombre": "El Emperador", "invertida": True},
            {"nombre": "Caballero de Copas", "invertida": False},
        ]
        texto = ("**La combinación: El Emperador invertido + Caballero de "
                 "Copas al derecho**\n\nEl Emperador invertido habla de reglas "
                 "confusas. El Caballero de Copas al derecho trae una propuesta.")
        ok, motivos = self._verificar("tarot_2", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_dos_cartas_del_mismo_palo_invertidas(self):
        cartas = [
            {"nombre": "Seis de Bastos", "invertida": True},
            {"nombre": "Ocho de Bastos", "invertida": True},
        ]
        texto = ("**El Seis de Bastos invertido** habla de un reconocimiento "
                 "que no llega. **El Ocho de Bastos invertido** trae prisas "
                 "que se atascan.")
        ok, motivos = self._verificar("tarot_2", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_has_invertido_es_un_verbo_no_una_orientacion(self):
        cartas = [
            {"nombre": "Siete de Oros", "invertida": False},
            {"nombre": "As de Copas", "invertida": True},
            {"nombre": "Ocho de Oros", "invertida": False},
        ]
        texto = ("El Siete de Oros mira la viña: has invertido esfuerzo y "
                 "paciencia. El As de Copas invertido muestra un bloqueo. El "
                 "Ocho de Oros invita a seguir trabajando.")
        ok, motivos = self._verificar("tarot_3", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_orientacion_lejana_en_tarot_de_una_carta(self):
        cartas = [{"nombre": "Los Enamorados", "invertida": True}]
        texto = ("Que Los Enamorados aparezcan **invertidos** como tema "
                 "central es una señal de encrucijada interna.")
        ok, motivos = self._verificar("tarot_1", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_el_mundo_invertida(self):
        cartas = [{"nombre": "El Mundo", "invertida": True}]
        texto = "El Mundo invertida te habla de un ciclo que aún no se cierra."
        ok, motivos = self._verificar("tarot_pregunta", cartas, texto)
        self.assertTrue(ok, motivos)

    def test_en_posicion_invertida(self):
        cartas = [{"nombre": "El Ermitaño", "invertida": True}]
        texto = ("El Ermitaño en posición invertida trae un mensaje de "
                 "aislamiento que ya no sostiene.")
        ok, motivos = self._verificar("tarot_1", cartas, texto)
        self.assertTrue(ok, motivos)


if __name__ == "__main__":
    unittest.main()
