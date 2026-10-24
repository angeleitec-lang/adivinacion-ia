"""Tests de la aplicacion del catalogo astro ampliado (T145).

Cubre la seccion `entidades_ampliadas` de kb/astrologia.json y el modulo
aplicar_catalogo_astro. Los casos adversos de remapeo puro viven en
test_catalogo_astro_propuesta.py; aqui se prueba la aplicacion real.
"""

import hashlib
import json
import os
import unittest

import catalogo_astro_propuesta as cap
import cobertura

RUTA_KB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "kb", "astrologia.json")

# Hash canonico (json sort_keys) de las secciones antiguas del KB tal y
# como estaban antes de T145. Si cambia, las entradas antiguas se tocaron.
SHA_ANTIGUAS = "ecc474d8947e71e0a73c2db74ae3f326907fd8d4e1ca6eb71220028366fbe35f"

SIGNOS_ORDEN = list(cobertura.SIGNOS)


class TestKbAstroAmpliado(unittest.TestCase):
    def setUp(self):
        with open(RUTA_KB, encoding="utf-8") as f:
            self.kb = json.load(f)
        self.ampliadas = {e["entidad_id"]: e
                         for e in self.kb["entidades_ampliadas"]}

    def test_kb_carga_y_secciones_antiguas_identicas(self):
        antiguas = {k: self.kb[k] for k in
                    ("signos", "planetas", "casas", "aspectos")}
        canon = json.dumps(antiguas, ensure_ascii=False, sort_keys=True)
        self.assertEqual(
            hashlib.sha256(canon.encode("utf-8")).hexdigest(), SHA_ANTIGUAS)

    def test_diecinueve_entradas_nuevas(self):
        esperados = {f"casa{n}|casa" for n in range(1, 13)}
        esperados |= {f"{x}|elemento"
                     for x in ("fuego", "tierra", "aire", "agua")}
        esperados |= {f"{m}|modalidad"
                     for m in ("cardinal", "fijo", "variable")}
        self.assertEqual(set(self.ampliadas), esperados)

    def test_casas_atributos_deterministas(self):
        angulares = {1, 4, 7, 10}
        sucedentes = {2, 5, 8, 11}
        for n in range(1, 13):
            e = self.ampliadas[f"casa{n}|casa"]
            self.assertEqual(e["tipo"], "casa")
            self.assertEqual(e["numero"], n)
            esperado = ("angular" if n in angulares
                       else "sucedente" if n in sucedentes else "cadente")
            self.assertEqual(e["ciclo"], esperado)
            self.assertEqual(e["signo_natural"], SIGNOS_ORDEN[n - 1])
            self.assertIsNone(e["significado"])
            self.assertIn("pendiente", e)
            self.assertTrue(e["pendiente"])

    def test_elementos_coherentes_con_mapeo_canonico(self):
        for x in ("fuego", "tierra", "aire", "agua"):
            e = self.ampliadas[f"{x}|elemento"]
            self.assertEqual(e["tipo"], "elemento")
            esperados = sorted(s for s in SIGNOS_ORDEN
                              if cap.SIGNO_ELEMENTO[s] == x)
            self.assertEqual(sorted(e["signos"]), esperados)
            self.assertEqual(len(e["signos"]), 3)
            self.assertIsNone(e["significado"])
            self.assertIn("pendiente", e)

    def test_modalidades_coherentes_con_mapeo_canonico(self):
        for m in ("cardinal", "fijo", "variable"):
            e = self.ampliadas[f"{m}|modalidad"]
            self.assertEqual(e["tipo"], "modalidad")
            esperados = sorted(s for s in SIGNOS_ORDEN
                              if cap.SIGNO_MODALIDAD[s] == m)
            self.assertEqual(sorted(e["signos"]), esperados)
            self.assertEqual(len(e["signos"]), 4)
            self.assertIsNone(e["significado"])
            self.assertIn("pendiente", e)

    def test_ids_ampliados_existen_en_catalogo(self):
        catalogo = {e["entidad_id"] for e in cobertura.entidades()}
        for ent_id in self.ampliadas:
            self.assertIn(ent_id, catalogo)

    def test_nombres_no_vacios(self):
        for ent_id, e in self.ampliadas.items():
            self.assertTrue(e.get("nombre"), ent_id)


if __name__ == "__main__":
    unittest.main()
