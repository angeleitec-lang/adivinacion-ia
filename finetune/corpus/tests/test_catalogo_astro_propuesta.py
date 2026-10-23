"""Tests de catalogo_astro_propuesta (T137): remapeo determinista y cobertura
hipotetica. Hermeticos: datos sinteticos y tempdir, sin red ni LLM. Incluyen
casos adversos: id inexistente, casa 13, signo ambiguo."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import catalogo_astro_propuesta as cap


def claim(entidad_id, faceta="significado_general", fuente="arroyo_1982",
         calidad=4, periodo="moderna"):
    return {
        "entidad_id": entidad_id,
        "faceta": faceta,
        "fuente_id": fuente,
        "dominio": fuente,
        "periodo": periodo,
        "calidad": calidad,
        "afirmacion": "texto de ejemplo",
    }


class TestParsearEntidadId(unittest.TestCase):
    def test_signo(self):
        tipo, partes = cap.parsear_entidad_id("aries|signo")
        self.assertEqual(tipo, "signo")
        self.assertEqual(partes, ["aries", "signo"])

    def test_planeta_en_signo(self):
        tipo, partes = cap.parsear_entidad_id("sol|piscis|planeta_en_signo")
        self.assertEqual(tipo, "planeta_en_signo")
        self.assertEqual(partes, ["sol", "piscis", "planeta_en_signo"])

    def test_planeta_en_casa_numero(self):
        tipo, partes = cap.parsear_entidad_id("saturno|casa5|planeta_en_casa")
        self.assertEqual(tipo, "planeta_en_casa")
        self.assertEqual(partes, ["saturno", 5])

    def test_aspecto(self):
        tipo, _ = cap.parsear_entidad_id("luna|cuadratura|venus|aspecto")
        self.assertEqual(tipo, "aspecto")

    def test_adverso_casa_token_malo(self):
        tipo, _ = cap.parsear_entidad_id("saturno|casaX|planeta_en_casa")
        self.assertEqual(tipo, "desconocido")

    def test_adverso_vacio_y_none(self):
        self.assertEqual(cap.parsear_entidad_id(""), ("desconocido", []))
        self.assertEqual(cap.parsear_entidad_id(None), ("desconocido", []))
        self.assertEqual(cap.parsear_entidad_id(42), ("desconocido", []))

    def test_adverso_partes_de_mas(self):
        tipo, _ = cap.parsear_entidad_id("a|b|c|d|e")
        self.assertEqual(tipo, "desconocido")


class TestRemapeoCasas(unittest.TestCase):
    def test_planeta_en_casa_remapea_a_casa(self):
        got = cap.remapear_afirmacion(claim("saturno|casa5|planeta_en_casa"))
        self.assertEqual([g["entidad_id"] for g in got], ["casa5|casa"])
        self.assertEqual(got[0]["regla"], "casa_desde_planeta_en_casa")

    def test_adverso_casa_13_no_remapea(self):
        self.assertEqual(
            cap.remapear_afirmacion(claim("saturno|casa13|planeta_en_casa")),
            [])

    def test_adverso_casa_0_no_remapea(self):
        self.assertEqual(
            cap.remapear_afirmacion(claim("sol|casa0|planeta_en_casa")), [])

    def test_adverso_casa_negativa_no_remapea(self):
        self.assertEqual(
            cap.remapear_afirmacion(claim("sol|casa-1|planeta_en_casa")), [])

    def test_casa_1_y_12_validas(self):
        self.assertEqual(
            [g["entidad_id"] for g in
             cap.remapear_afirmacion(claim("sol|casa1|planeta_en_casa"))],
            ["casa1|casa"])
        self.assertEqual(
            [g["entidad_id"] for g in
             cap.remapear_afirmacion(claim("neptuno|casa12|planeta_en_casa"))],
            ["casa12|casa"])


class TestRemapeoSignos(unittest.TestCase):
    def test_signo_remapea_elemento_y_modalidad(self):
        got = cap.remapear_afirmacion(claim("aries|signo"))
        self.assertEqual(
            sorted(g["entidad_id"] for g in got),
            ["cardinal|modalidad", "fuego|elemento"])

    def test_planeta_en_signo_remapea_elemento_y_modalidad(self):
        got = cap.remapear_afirmacion(claim("sol|piscis|planeta_en_signo"))
        self.assertEqual(
            sorted(g["entidad_id"] for g in got),
            ["agua|elemento", "variable|modalidad"])

    def test_adverso_id_inexistente_no_remapea(self):
        self.assertEqual(cap.remapear_afirmacion(claim("quiron|signo")), [])
        self.assertEqual(
            cap.remapear_afirmacion(claim("quiron|piscis|planeta_en_signo")),
            [])
        self.assertEqual(
            cap.remapear_afirmacion(
                claim("quiron|casa5|planeta_en_casa")), [])

    def test_adverso_signo_ambiguo_no_remapea(self):
        self.assertEqual(
            cap.remapear_afirmacion(claim("cancer leo|signo")), [])
        self.assertEqual(
            cap.remapear_afirmacion(claim("ascendente|signo")), [])
        self.assertEqual(
            cap.remapear_afirmacion(claim("|signo")), [])

    def test_adverso_signo_ambiguo_en_planeta_en_signo(self):
        self.assertEqual(
            cap.remapear_afirmacion(
                claim("sol|ascendente|planeta_en_signo")), [])

    def test_aspecto_no_remapea(self):
        self.assertEqual(
            cap.remapear_afirmacion(claim("luna|cuadratura|venus|aspecto")),
            [])

    def test_adverso_claim_no_dict(self):
        self.assertEqual(cap.remapear_afirmacion(None), [])
        self.assertEqual(cap.remapear_afirmacion("sol|signo"), [])


class TestCoherenciaConKB(unittest.TestCase):
    def test_signo_elemento_coincide_con_kb(self):
        kb_ruta = os.path.join(os.path.dirname(__file__), "..",
                               "kb", "astrologia.json")
        with open(kb_ruta, encoding="utf-8") as fh:
            kb = json.load(fh)
        for signo in kb["signos"]:
            slug = cap._norm(signo["nombre"])
            self.assertIn(slug, cap.SIGNO_ELEMENTO, slug)
            self.assertEqual(cap.SIGNO_ELEMENTO[slug], signo["elemento"],
                             slug)

    def test_modalidad_canonica(self):
        self.assertEqual(cap.SIGNO_MODALIDAD["aries"], "cardinal")
        self.assertEqual(cap.SIGNO_MODALIDAD["leo"], "fijo")
        self.assertEqual(cap.SIGNO_MODALIDAD["geminis"], "variable")
        self.assertEqual(len(cap.SIGNO_MODALIDAD), 12)

    def test_ids_propuestos_no_colisionan_con_catalogo(self):
        existentes = {e["entidad_id"] for e in __import__(
            "cobertura").entidades()}
        nuevos = cap.ids_propuestos()
        self.assertEqual(len(nuevos), 19)
        self.assertEqual(nuevos & existentes, set())


class TestEvidenciasRemapeadas(unittest.TestCase):
    def test_preserva_faceta_y_fuente_idioma_en(self):
        evs = cap.evidencias_remapeadas([
            claim("sol|piscis|planeta_en_signo", faceta="amor",
                 fuente="sasportas_1985")])
        self.assertEqual(len(evs), 2)
        for e in evs:
            self.assertEqual(e["faceta"], "amor")
            self.assertEqual(e["fuente_id"], "sasportas_1985")
            self.assertEqual(e["idioma"], "en")
            self.assertEqual(e["periodo"], "moderna")

    def test_sin_faceta_no_genera_evidencia(self):
        c = claim("aries|signo")
        c.pop("faceta")
        self.assertEqual(cap.evidencias_remapeadas([c]), [])


class TestCoberturaHipotetica(unittest.TestCase):
    def test_celdas_nuevas_son_209(self):
        res = cap.cobertura_hipotetica([])
        self.assertEqual(res["resumen"]["celdas_nuevas"], 209)
        self.assertEqual(res["resumen"]["completas"], 0)

    def test_sin_evidencias_ninguna_celda_con_fuente(self):
        res = cap.cobertura_hipotetica([])
        self.assertEqual(res["resumen"]["con_fuente"], 0)

    def test_dos_fuentes_no_alcanzan_para_completa(self):
        claims = [
            claim("saturno|casa5|planeta_en_casa", fuente="arroyo_1982"),
            claim("neptuno|casa5|planeta_en_casa", fuente="sasportas_1985"),
        ]
        res = cap.cobertura_hipotetica(claims)
        casa5 = [c for c in res["celdas_nuevas"]
                 if c["entidad_id"] == "casa5|casa"
                 and c["faceta"] == "significado_general"]
        self.assertEqual(len(casa5), 1)
        self.assertEqual(casa5[0]["n_fuentes"], 2)
        self.assertFalse(casa5[0]["completa"])

    def test_calidad_min_excluye_bajas(self):
        res = cap.cobertura_hipotetica(
            [claim("aries|signo", calidad=2)], calidad_min=3)
        self.assertEqual(res["resumen"]["con_fuente"], 0)

    def test_adverso_claims_basura_no_rompen(self):
        res = cap.cobertura_hipotetica([
            None, "texto", claim("casa13|signo"),
            claim("saturno|casa13|planeta_en_casa"),
        ])
        self.assertEqual(res["resumen"]["con_fuente"], 0)


class TestEstadisticasRemapeo(unittest.TestCase):
    def test_cuentas_por_regla(self):
        stats = cap.estadisticas_remapeo([
            claim("aries|signo"),
            claim("sol|piscis|planeta_en_signo"),
            claim("saturno|casa5|planeta_en_casa"),
            claim("luna|cuadratura|venus|aspecto"),
        ])
        self.assertEqual(stats["total_afirmaciones"], 4)
        self.assertEqual(stats["por_regla"]["elemento_desde_signo"], 2)
        self.assertEqual(stats["por_regla"]["modalidad_desde_signo"], 2)
        self.assertEqual(stats["por_regla"]["casa_desde_planeta_en_casa"], 1)
        self.assertEqual(stats["sin_remapeo"], 1)
        self.assertEqual(stats["sin_remapeo_por_origen"].get("aspecto"), 1)


class TestEjecutar(unittest.TestCase):
    def test_escribe_artefactos_en_copia(self):
        with tempfile.TemporaryDirectory() as tmp:
            afirm = os.path.join(tmp, "afirmaciones.jsonl")
            with open(afirm, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(claim("saturno|casa5|planeta_en_casa"))
                         + "\n")
                fh.write(json.dumps(claim("aries|signo")) + "\n")
            work = os.path.join(tmp, "copia")
            res = cap.ejecutar(work_dir=work, ruta_afirmaciones=afirm,
                              ruta_v3=os.path.join(tmp, "no_existe.json"))
            for nombre in ("afirmaciones_origen.jsonl", "remapeo.jsonl",
                          "cobertura_hipotetica.json",
                          "inventario_y_remapeo.json", "informe.md"):
                self.assertTrue(os.path.exists(os.path.join(work, nombre)),
                                nombre)
            self.assertEqual(res["hipotetica"]["celdas_nuevas"], 209)
            with open(os.path.join(work, "remapeo.jsonl"),
                      encoding="utf-8") as fh:
                registro = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(registro[0]["nuevos"], ["casa5|casa"])
            self.assertEqual(sorted(registro[1]["nuevos"]),
                             ["cardinal|modalidad", "fuego|elemento"])

    def test_adverso_work_dir_protegido_se_rechaza(self):
        with self.assertRaises(ValueError):
            cap.ejecutar(work_dir="/Users/angelgonzalez/fase0/libros")
        with self.assertRaises(ValueError):
            cap.ejecutar(
                work_dir="/Users/angelgonzalez/fase0/cobertura_v3/subdir")

    def test_adverso_afirmaciones_inexistentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                cap.ejecutar(work_dir=os.path.join(tmp, "c"),
                            ruta_afirmaciones=os.path.join(tmp, "no.jsonl"),
                            ruta_v3=os.path.join(tmp, "no_v3.json"))


class TestNorm(unittest.TestCase):
    def test_sin_tildes_minusculas(self):
        self.assertEqual(cap._norm("Piscis"), "piscis")
        self.assertEqual(cap._norm("CAPRICORNIO"), "capricornio")
        self.assertEqual(cap._norm("Corazón"), "corazon")


if __name__ == "__main__":
    unittest.main()
