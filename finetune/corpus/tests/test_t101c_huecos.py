"""T101c: huecos del verificador tras T101b (cartas inventadas y vedados)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import reverificar_fase1 as rv  # noqa: E402


class TestHuecosCartas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _tarea(self, bloque="tarot_1", cartas=None, **extra):
        payload = dict(extra)
        if cartas is not None:
            payload["cartas"] = cartas
        if bloque in ("tarot_1", "tarot_pregunta") and cartas is None:
            payload["carta"] = {"nombre": "El Loco", "invertida": False}
        return ef.tarea_desde_job(bloque, payload, "¿Qué me depara?", self.kb)

    def test_carta_inventada_con_articulo_en_minuscula(self):
        t = self._tarea()
        ok, motivos = fp.verificar_lectura(
            t, "El Loco abre tu camino. También aparece el Ocho de Estrellas, "
               "que anuncia un cambio importante.")
        self.assertFalse(ok)
        self.assertTrue(any("inexistente" in m for m in motivos), motivos)

    def test_otras_cartas_con_palo_inventado(self):
        for frase in ("el Seis de Estrellas", "el Rey de Tréboles"):
            with self.subTest(frase=frase):
                ok, motivos = fp.verificar_lectura(
                    self._tarea(), f"El Loco abre. Aparece {frase} en la mesa.")
                self.assertFalse(ok, motivos)
                self.assertTrue(any("inexistente" in m for m in motivos), motivos)

    def test_carta_real_con_palo_sigue_pasando(self):
        ok, motivos = fp.verificar_lectura(
            self._tarea(), "El Loco abre. El Rey de Oros espera en la mesa.")
        self.assertFalse(ok, motivos)  # ajena a la tirada, no inventada
        self.assertFalse(any("inexistente" in m for m in motivos), motivos)

    def test_astro_rechaza_cartas_presentadas_como_sacadas(self):
        t = self._tarea("astro_natal", carta={})
        ok, motivos = fp.verificar_lectura(
            t, "La carta de La Torre y el Tres de Oros también estaban en la mesa.")
        self.assertFalse(ok)
        self.assertTrue(any("La Torre" in m for m in motivos), motivos)
        self.assertTrue(any("Tres de Oros" in m for m in motivos), motivos)

    def test_astro_permite_analogias_de_tarot(self):
        t = self._tarea("astro_natal", carta={})
        ok, motivos = fp.verificar_lectura(
            t, "En el tarot, la carta que mejor representa tu energía es El "
               "Colgado. Otro arcano relevante es La Rueda de la Fortuna.")
        self.assertTrue(ok, motivos)

    def test_astro_permite_sol_y_luna_como_astros(self):
        t = self._tarea("astro_natal", carta={})
        ok, motivos = fp.verificar_lectura(
            t, "El Sol en Leo ilumina tu energía y la Luna en Cáncer acompaña.")
        self.assertTrue(ok, motivos)

    def test_reverificar_construye_universo_en_astro(self):
        campos = {"human": "Carta natal.", "respuesta": "", "calculos": {},
                  "bloque": "astro_natal"}
        t = rv._construir_tarea("astro_natal", campos, {"carta": {}}, self.kb)
        self.assertTrue(t.get("universo_cartas"))
        ok, motivos = fp.verificar_lectura(
            t, "La carta de La Torre estaba en la mesa.")
        self.assertFalse(ok, motivos)


class TestHuecosVedados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _texto(self, frase):
        t = ef.tarea_desde_job(
            "tarot_1", {"carta": {"nombre": "El Loco", "invertida": False}},
            "¿Qué me depara?", self.kb)
        return fp.verificar_lectura(t, "El Loco abre tu camino. " + frase)

    def test_diagnostico_y_abandono_de_medicacion(self):
        ok, motivos = self._texto(
            "Tienes depresión clínica y deberías dejar la medicación.")
        self.assertFalse(ok)
        self.assertTrue(any("depresión" in m.lower() for m in motivos), motivos)
        self.assertTrue(any("dejar la medicación" in m.lower() for m in motivos),
                        motivos)

    def test_deja_el_tratamiento(self):
        ok, motivos = self._texto("Deja el tratamiento cuanto antes.")
        self.assertFalse(ok, motivos)

    def test_tienes_cancer(self):
        ok, motivos = self._texto("Tienes cáncer de pulmón.")
        self.assertFalse(ok, motivos)

    def test_estas_embarazada(self):
        ok, motivos = self._texto("Estás embarazada y será niña.")
        self.assertFalse(ok, motivos)

    def test_pareja_engana_seguro(self):
        ok, motivos = self._texto("Tu pareja te engaña seguro.")
        self.assertFalse(ok, motivos)

    def test_vas_a_divorciarte(self):
        ok, motivos = self._texto("Vas a divorciarte este año.")
        self.assertFalse(ok, motivos)

    def test_negaciones_siguen_exentas(self):
        ok, motivos = self._texto(
            "No tienes cáncer ni estás embarazada; no debes dejar la medicación.")
        self.assertTrue(ok, motivos)


if __name__ == "__main__":
    unittest.main()
