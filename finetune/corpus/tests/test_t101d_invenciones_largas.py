"""T101d: cartas inventadas en lecturas largas (cruz_celta, lectura_completa, astro)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402


class TestInvencionesLecturasLargas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _tarea(self, familia, payload=None):
        return ef.tarea_desde_job(familia, self._payload(familia, payload),
                                  "¿Qué me depara?", self.kb)

    def _payload(self, familia, payload=None):
        if familia == "lectura_completa":
            return {"fecha": "1992-11-29", "nombre": "Ana", "carta": {},
                    "cartas": [], **(payload or {})}
        return payload or {}

    def _motivos(self, familia, texto, payload=None):
        _ok, motivos = fp.verificar_lectura(
            self._tarea(familia, payload), texto)
        return motivos

    def _inventadas(self, familia, texto):
        return [m for m in self._motivos(familia, texto)
                if "inexistente" in m]

    # ----- cruz_celta y lectura_completa (sin cartas reconstruidas) -----

    def test_cruz_celta_rechaza_nueve_de_estrellas_con_articulo(self):
        motivos = self._inventadas(
            "cruz_celta",
            "Sale también el Nueve de Estrellas, que anuncia cambios.")
        self.assertTrue(any("Nueve de Estrellas" in m for m in motivos), motivos)

    def test_cruz_celta_rechaza_invencion_sin_articulo(self):
        motivos = self._inventadas(
            "cruz_celta", "Ocho de Estrellas anuncia un cambio importante.")
        self.assertTrue(any("Ocho de Estrellas" in m for m in motivos), motivos)

    def test_cruz_celta_rechaza_rey_de_treboles(self):
        motivos = self._inventadas(
            "cruz_celta", "El Rey de Tréboles aparece como consejero.")
        self.assertTrue(any("Rey de Tréboles" in m for m in motivos), motivos)

    def test_cruz_celta_rechaza_mayusculas(self):
        motivos = self._inventadas(
            "cruz_celta", "NUEVE DE ESTRELLAS anuncia un cambio.")
        self.assertTrue(any("ESTRELLAS" in m for m in motivos), motivos)

    def test_cruz_celta_rechaza_numero_fuera_de_rango(self):
        motivos = self._inventadas(
            "cruz_celta", "Quince de Oros marca el final del ciclo.")
        self.assertTrue(any("Quince de Oros" in m for m in motivos), motivos)

    def test_cruz_celta_rechaza_palo_extranjero(self):
        motivos = self._inventadas(
            "cruz_celta", "Swords of Stars anuncia un giro inesperado.")
        self.assertTrue(any("Swords of Stars" in m for m in motivos), motivos)

    def test_cruz_celta_no_marca_nombres_narrativos(self):
        motivos = self._inventadas(
            "cruz_celta",
            "La Cruz de la tirada habla de La Mente, Los Sueños, El Impulso "
            "y La Transformación como procesos internos.")
        self.assertEqual(motivos, [])

    def test_lectura_completa_rechaza_invencion_con_palo(self):
        texto = (
            "## Carta natal\nTu Sol en Piscis pide calma.\n"
            "## Tirada de tres cartas\nAparece el Nueve de Estrellas.\n"
            "## Numerología\nTu camino de vida es el 7.\n"
            "## Síntesis\nUn ciclo que se cierra con claridad.")
        motivos = self._inventadas("lectura_completa", texto)
        self.assertTrue(any("Nueve de Estrellas" in m for m in motivos), motivos)

    def test_lectura_completa_acepta_cartas_validas(self):
        texto = (
            "## Carta natal\nTu Sol en Piscis pide calma.\n"
            "## Tirada de tres cartas\nEl Sol ilumina y La Luna acompaña.\n"
            "## Numerología\nTu camino de vida es el 7.\n"
            "## Síntesis\nUn ciclo que se abre con claridad.")
        ok, motivos = fp.verificar_lectura(
            self._tarea("lectura_completa"), texto)
        self.assertTrue(ok, motivos)

    # ----- astro_natal -----

    def test_astro_rechaza_invencion_de_palo(self):
        motivos = self._inventadas(
            "astro_natal", "El Rey de Tréboles aparece como consejero.")
        self.assertTrue(any("Rey de Tréboles" in m for m in motivos), motivos)

    def test_astro_permite_astros_y_conceptos(self):
        texto = (
            "El Sol en Piscis y la Luna en Leo describen tu energía. "
            "La Fuerza es tu gran virtud y el impulso de tu carta natal.")
        ok, motivos = fp.verificar_lectura(self._tarea("astro_natal"), texto)
        self.assertTrue(ok, motivos)

    def test_astro_permite_analogia_con_carta_de_tarot(self):
        texto = ("En el tarot, la carta que mejor representa tu energía es "
                 "El Colgado.")
        ok, motivos = fp.verificar_lectura(self._tarea("astro_natal"), texto)
        self.assertTrue(ok, motivos)

    def test_astro_no_marca_nombres_propios_largos(self):
        motivos = self._inventadas(
            "astro_natal",
            "La Mente racional y Los Sueños profundos conviven con "
            "La Transformación y El Impulso de tu carta.")
        self.assertEqual(motivos, [])

    # ----- cartas válidas y formas conocidas -----

    def test_tarot_acepta_carta_valida_de_otro_palo(self):
        tarea = self._tarea("tarot_1", {"cartas": [
            {"nombre": "Tres de Oros", "invertida": False}]})
        ok, motivos = fp.verificar_lectura(
            tarea, "El Tres de Oros abre la lectura con trabajo constante.")
        self.assertTrue(ok, motivos)

    def test_tarot_sigue_rechazando_carta_inventada(self):
        tarea = self._tarea("tarot_1", {"cartas": [
            {"nombre": "El Sol", "invertida": False}]})
        ok, motivos = fp.verificar_lectura(
            tarea, "El Sol ilumina. El Arquitecto abre tu camino.")
        self.assertFalse(ok)
        self.assertTrue(any("Arquitecto" in m for m in motivos), motivos)


if __name__ == "__main__":
    unittest.main()
