"""Tests de web_rejillas: expansión de las rejillas de astrología en tareas de descarga."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import unittest

from web_rejillas import cargar_rejillas, expandir, tareas_todas

DATOS = cargar_rejillas()
SLUGS = DATOS["slugs"]


def _rejilla(sitio, faceta):
    for r in DATOS["rejillas"]:
        if r["sitio"] == sitio and r["faceta"] == faceta:
            return r
    raise AssertionError(f"rejilla no encontrada: {sitio}/{faceta}")


class TestExpandir(unittest.TestCase):
    def test_planeta_en_signo_son_120(self):
        tareas = expandir(_rejilla("astrolink.com", "planeta_en_signo"), SLUGS)
        self.assertEqual(len(tareas), 120)

    def test_url_exacta_astrolink_sol_en_aries(self):
        tareas = expandir(_rejilla("astrolink.com", "planeta_en_signo"), SLUGS)
        urls = {t["url"] for t in tareas}
        self.assertIn("https://www.astrolink.com/es/interpretacion/sol-en-aries", urls)

    def test_planeta_en_casa_son_120(self):
        tareas = expandir(_rejilla("mercurioretrogrado.com", "planeta_en_casa"), SLUGS)
        self.assertEqual(len(tareas), 120)

    def test_url_exacta_mercurio_sol_casa_10(self):
        tareas = expandir(_rejilla("mercurioretrogrado.com", "planeta_en_casa"), SLUGS)
        urls = {t["url"] for t in tareas}
        self.assertIn(
            "https://www.mercurioretrogrado.com/planeta-en-casa/sol-en-casa-10", urls)

    def test_aspectos_son_225(self):
        tareas = expandir(_rejilla("yourastrallife.com", "aspecto"), SLUGS)
        self.assertEqual(len(tareas), 225)

    def test_entidad_id_planeta_en_signo(self):
        tareas = expandir(_rejilla("astrolink.com", "planeta_en_signo"), SLUGS)
        ids = {t["entidad_id"] for t in tareas}
        self.assertIn("sol|aries|planeta_en_signo", ids)

    def test_entidad_id_casa_normalizada(self):
        tareas = expandir(_rejilla("astrolink.com", "planeta_en_casa"), SLUGS)
        ids = {t["entidad_id"] for t in tareas}
        self.assertIn("luna|casa4|planeta_en_casa", ids)

    def test_entidad_id_aspecto(self):
        tareas = expandir(_rejilla("yourastrallife.com", "aspecto"), SLUGS)
        ids = {t["entidad_id"] for t in tareas}
        self.assertIn("sol|trigono|luna|aspecto", ids)

    def test_slugs_en_con_entidad_canonica_es(self):
        tareas = expandir(_rejilla("my-zodiac-ai.com", "planeta_en_casa"), SLUGS)
        por_url = {t["url"]: t for t in tareas}
        t = por_url["https://my-zodiac-ai.com/es/house/moon-in-4th-house"]
        self.assertEqual(t["entidad_id"], "luna|casa4|planeta_en_casa")
        self.assertEqual(t["entidad"]["planeta"], "luna")
        self.assertEqual(t["entidad"]["casa"], 4)

    def test_entidad_contiene_campos_segun_faceta(self):
        t_signo = expandir(_rejilla("astrolink.com", "planeta_en_signo"), SLUGS)[0]
        self.assertEqual(set(t_signo["entidad"]), {"planeta", "signo"})
        t_casa = expandir(_rejilla("astrolink.com", "planeta_en_casa"), SLUGS)[0]
        self.assertEqual(set(t_casa["entidad"]), {"planeta", "casa"})
        t_asp = expandir(_rejilla("yourastrallife.com", "aspecto"), SLUGS)[0]
        self.assertEqual(set(t_asp["entidad"]), {"planeta", "planeta2", "aspecto"})


class TestTareasTodas(unittest.TestCase):
    def test_totales_por_faceta(self):
        tareas = tareas_todas(DATOS)
        por_faceta = {}
        for t in tareas:
            por_faceta[t["faceta"]] = por_faceta.get(t["faceta"], 0) + 1
        self.assertEqual(por_faceta["planeta_en_signo"], 5 * 120)
        self.assertEqual(por_faceta["planeta_en_casa"], 7 * 120)
        self.assertEqual(por_faceta["aspecto"], 5 * 225)

    def test_solo_sitios_filtra(self):
        tareas = tareas_todas(DATOS, solo_sitios=["astrolink.com"])
        self.assertTrue(tareas)
        self.assertTrue(all(t["sitio"] == "astrolink.com" for t in tareas))

    def test_excluir_ia_quita_my_zodiac(self):
        tareas = tareas_todas(DATOS, excluir_ia=True)
        self.assertTrue(all(t["sitio"] != "my-zodiac-ai.com" for t in tareas))

    def test_limite_recorta(self):
        tareas = tareas_todas(DATOS, limite=10)
        self.assertEqual(len(tareas), 10)

    def test_todas_llevan_prioridad(self):
        tareas = tareas_todas(DATOS, limite=50)
        for t in tareas:
            self.assertIn(t["prioridad"], ("alta", "media", "baja", "sin_evaluar"))


if __name__ == "__main__":
    unittest.main()
