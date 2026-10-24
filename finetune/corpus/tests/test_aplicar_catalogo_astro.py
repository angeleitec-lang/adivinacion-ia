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


class TestGenerarEvidencias(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.destino = os.path.join(self.tmp.name, "ev.jsonl")

    def _claim(self, entidad_id, faceta="amor", fuente="sasportas_1985"):
        return {"entidad_id": entidad_id, "faceta": faceta,
                "fuente_id": fuente, "dominio": "astrologia",
                "periodo": "moderna", "idioma": "en", "calidad": 4}

    def test_escribe_evidencias_remapeadas(self):
        import aplicar_catalogo_astro as ac
        n = ac.generar_evidencias(
            [self._claim("sol|piscis|planeta_en_signo"),
             self._claim("sol|casa3|planeta_en_casa")], self.destino)
        self.assertEqual(n, 3)  # 2 (agua+variable) + 1 (casa3)
        with open(self.destino, encoding="utf-8") as f:
            lineas = [json.loads(l) for l in f]
        ids = {e["entidad_id"] for e in lineas}
        self.assertEqual(ids, {"agua|elemento", "variable|modalidad",
                              "casa3|casa"})

    def test_doble_aplicacion_idempotente(self):
        import aplicar_catalogo_astro as ac
        claims = [self._claim("sol|piscis|planeta_en_signo"),
                 self._claim("luna|casa7|planeta_en_casa")]
        ac.generar_evidencias(claims, self.destino)
        with open(self.destino, "rb") as f:
            primera = f.read()
        ac.generar_evidencias(list(reversed(claims)), self.destino)
        with open(self.destino, "rb") as f:
            segunda = f.read()
        self.assertEqual(primera, segunda)

    def test_adverso_casa_13_0_negativa_sin_evidencia(self):
        import aplicar_catalogo_astro as ac
        n = ac.generar_evidencias(
            [self._claim("sol|casa13|planeta_en_casa"),
             self._claim("sol|casa0|planeta_en_casa"),
             self._claim("sol|casa-1|planeta_en_casa")], self.destino)
        self.assertEqual(n, 0)
        with open(self.destino, encoding="utf-8") as f:
            self.assertEqual(f.read(), "")

    def test_adverso_id_inexistente_y_signo_ambiguo(self):
        import aplicar_catalogo_astro as ac
        n = ac.generar_evidencias(
            [self._claim("quiron|piscis|planeta_en_signo"),
             self._claim("sol|ascendente|planeta_en_signo"),
             self._claim("entidad|que|no|existe|en|el|catalogo")],
            self.destino)
        self.assertEqual(n, 0)

    def test_adverso_evidencia_sin_faceta(self):
        import aplicar_catalogo_astro as ac
        c = self._claim("aries|signo")
        c.pop("faceta")
        n = ac.generar_evidencias([c], self.destino)
        self.assertEqual(n, 0)


class TestProteccionRutasReales(unittest.TestCase):
    def test_destino_dentro_de_rutas_protegidas_se_rechaza(self):
        import aplicar_catalogo_astro as ac
        for protegida in (
                "/Users/angelgonzalez/fase0/cobertura_v3/salida",
                "/Users/angelgonzalez/fase0/libros_limpio/x.jsonl",
                "/Users/angelgonzalez/fase0/evidencias_web/x.jsonl",
                "/Users/angelgonzalez/fase0/libros_comprados_astro/x.jsonl"):
            with self.assertRaises(ValueError, msg=protegida):
                ac.generar_evidencias([], protegida)

    def test_rutas_oficiales_del_modulo_no_caen_en_protegidas(self):
        import aplicar_catalogo_astro as ac
        self.assertIsNone(ac._ruta_protegida(ac.DESTINO))
        self.assertIsNone(ac._ruta_protegida(ac.V3_NUEVA_DIR))
        self.assertIsNotNone(ac._ruta_protegida(ac.V3_OFICIAL))


if __name__ == "__main__":
    unittest.main()
