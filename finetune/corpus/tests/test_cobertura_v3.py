"""Tests de cobertura_v3: reunión de evidencias vigentes, comparación v2->v3 e
informe de huecos. Hermeticos: evidencias sinteticas y tempdir, sin red ni LLM."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura
import cobertura_v3


def ev(entidad, faceta, fuente, periodo, idioma, calidad=4, tipo="web",
       dominio=None, hash_seccion=None):
    d = {
        "entidad_id": entidad,
        "faceta": faceta,
        "fuente_id": fuente,
        "dominio": dominio or fuente,
        "idioma": idioma,
        "periodo": periodo,
        "calidad": str(calidad),
        "tipo": tipo,
    }
    if hash_seccion:
        d["hash_seccion"] = hash_seccion
    return d


def cinco_fuentes_completas(entidad, faceta, prefijo="f"):
    """5 fuentes independientes: 2 clasicas, 3 modernas, 1 en espanol."""
    return [
        ev(entidad, faceta, f"{prefijo}1", "clasica", "en"),
        ev(entidad, faceta, f"{prefijo}2", "moderna", "en"),
        ev(entidad, faceta, f"{prefijo}3", "moderna", "es"),
        ev(entidad, faceta, f"{prefijo}4", "clasica", "en"),
        ev(entidad, faceta, f"{prefijo}5", "moderna", "en"),
    ]


class CeldaCompleta(unittest.TestCase):
    def test_cinco_fuentes_es_completa(self):
        evidencias = cinco_fuentes_completas("tarot-mayor-01",
                                           "significado_general")
        resultado = cobertura.calcular_cobertura(evidencias)
        celda = next(c for c in resultado["celdas"]
                    if c["entidad_id"] == "tarot-mayor-01"
                    and c["faceta"] == "significado_general")
        self.assertTrue(celda["completa"])
        self.assertEqual(celda["n_fuentes"], 5)
        self.assertEqual(celda["n_clasicas"], 2)
        self.assertEqual(celda["n_modernas"], 3)
        self.assertEqual(celda["n_es"], 1)


class FaltaClasica(unittest.TestCase):
    def test_sin_clasica_no_es_completa(self):
        evidencias = [
            ev("tarot-mayor-02", "amor", "a", "moderna", "en"),
            ev("tarot-mayor-02", "amor", "b", "moderna", "en"),
            ev("tarot-mayor-02", "amor", "c", "moderna", "es"),
            ev("tarot-mayor-02", "amor", "d", "moderna", "en"),
            ev("tarot-mayor-02", "amor", "e", "moderna", "en"),
        ]
        resultado = cobertura.calcular_cobertura(evidencias)
        celda = next(c for c in resultado["celdas"]
                    if c["entidad_id"] == "tarot-mayor-02"
                    and c["faceta"] == "amor")
        self.assertFalse(celda["completa"])
        self.assertIn("falta 1 fuente clasica".replace("clasica", "clásica"),
                      celda["faltan"])


class FaltaEspanol(unittest.TestCase):
    def test_sin_espanol_no_es_completa(self):
        evidencias = [
            ev("tarot-mayor-03", "dinero", "a", "clasica", "en"),
            ev("tarot-mayor-03", "dinero", "b", "moderna", "en"),
            ev("tarot-mayor-03", "dinero", "c", "moderna", "en"),
            ev("tarot-mayor-03", "dinero", "d", "clasica", "en"),
            ev("tarot-mayor-03", "dinero", "e", "moderna", "en"),
        ]
        resultado = cobertura.calcular_cobertura(evidencias)
        celda = next(c for c in resultado["celdas"]
                    if c["entidad_id"] == "tarot-mayor-03"
                    and c["faceta"] == "dinero")
        self.assertFalse(celda["completa"])
        self.assertIn("falta 1 fuente en español", celda["faltan"])


class ExclusionDeClaves(unittest.TestCase):
    def test_evidencia_con_clave_coincidente_se_excluye(self):
        evidencias = [
            ev("tarot-mayor-01", "amor", "x1", "clasica", "en",
               hash_seccion="H1"),
            ev("tarot-mayor-01", "amor", "x2", "moderna", "es",
               hash_seccion="H2"),
        ]
        claves = {("H1", "tarot-mayor-01", "amor")}
        conservadas, excluidas = cobertura_v3.excluir_por_claves(evidencias,
                                                               claves)
        self.assertEqual(excluidas, 1)
        self.assertEqual(len(conservadas), 1)
        self.assertEqual(conservadas[0]["fuente_id"], "x2")

    def test_misma_hash_otra_entidad_se_conserva(self):
        evidencias = [
            ev("tarot-mayor-05", "amor", "x1", "clasica", "en",
               hash_seccion="H1"),
        ]
        claves = {("H1", "tarot-mayor-01", "amor")}
        conservadas, excluidas = cobertura_v3.excluir_por_claves(evidencias,
                                                               claves)
        self.assertEqual(excluidas, 0)
        self.assertEqual(len(conservadas), 1)

    def test_sin_hash_se_conserva(self):
        evidencias = [ev("tarot-mayor-01", "amor", "x1", "clasica", "en")]
        claves = {("H1", "tarot-mayor-01", "amor")}
        conservadas, excluidas = cobertura_v3.excluir_por_claves(evidencias,
                                                               claves)
        self.assertEqual(excluidas, 0)
        self.assertEqual(len(conservadas), 1)

    def test_cargar_claves_de_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "claves.jsonl")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(json.dumps({"hash_seccion": "H1",
                                   "entidad_id": "tarot-mayor-01",
                                   "faceta": "amor",
                                   "n_afirmaciones": "3"}) + "\n")
                f.write("linea invalida\n")
                f.write("\n")
            claves = cobertura_v3.cargar_claves_exclusion(ruta)
            self.assertEqual(claves,
                             {("H1", "tarot-mayor-01", "amor")})

    def test_claves_inexistente_vacio(self):
        self.assertEqual(
            cobertura_v3.cargar_claves_exclusion("/ruta/que/no/existe.jsonl"),
            set())

    def test_exclusion_degrada_celda(self):
        """Quitar una fuente clave puede dejar la celda sin clasica."""
        evidencias = cinco_fuentes_completas("tarot-mayor-04", "salud")
        evidencias[0]["hash_seccion"] = "HC"
        claves = {("HC", "tarot-mayor-04", "salud")}
        filtradas, excluidas = cobertura_v3.excluir_por_claves(evidencias,
                                                             claves)
        self.assertEqual(excluidas, 1)
        resultado = cobertura.calcular_cobertura(filtradas)
        celda = next(c for c in resultado["celdas"]
                    if c["entidad_id"] == "tarot-mayor-04"
                    and c["faceta"] == "salud")
        self.assertFalse(celda["completa"])
        self.assertEqual(celda["n_clasicas"], 1)


class ComparacionV2V3(unittest.TestCase):
    def _escribir_v2(self, tmp, celdas, completas):
        ruta = os.path.join(tmp, "v2.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"resumen": {"completas": completas}, "celdas": celdas},
                      f)
        return ruta

    def test_pasan_y_dejan_de_serlo(self):
        with tempfile.TemporaryDirectory() as tmp:
            v2_celdas = [
                {"entidad_id": "tarot-mayor-01", "faceta": "amor",
                 "n_fuentes": 4, "n_clasicas": 1, "n_modernas": 2,
                 "n_es": 1, "completa": False},
                {"entidad_id": "tarot-mayor-02", "faceta": "dinero",
                 "n_fuentes": 6, "n_clasicas": 2, "n_modernas": 3,
                 "n_es": 2, "completa": True},
            ]
            ruta_v2 = self._escribir_v2(tmp, v2_celdas, 1)
            v3_celdas = [
                {"entidad_id": "tarot-mayor-01", "faceta": "amor",
                 "n_fuentes": 5, "n_clasicas": 1, "n_modernas": 3,
                 "n_es": 1, "completa": True},
                {"entidad_id": "tarot-mayor-02", "faceta": "dinero",
                 "n_fuentes": 6, "n_clasicas": 0, "n_modernas": 5,
                 "n_es": 2, "completa": False},
            ]
            comp = cobertura_v3.comparar_v2_v3(v3_celdas, ruta_v2)
            self.assertTrue(comp["disponible"])
            self.assertEqual(len(comp["pasan_a_completas"]), 1)
            self.assertEqual(comp["pasan_a_completas"][0]["entidad_id"],
                             "tarot-mayor-01")
            self.assertEqual(len(comp["dejan_de_serlo"]), 1)
            caida = comp["dejan_de_serlo"][0]
            self.assertEqual(caida["entidad_id"], "tarot-mayor-02")
            self.assertTrue(any("clasica" in m for m in caida["motivo"]))

    def test_v2_inexistente_sin_comparacion(self):
        comp = cobertura_v3.comparar_v2_v3([], "/ruta/que/no/existe.json")
        self.assertFalse(comp["disponible"])

    def test_motivo_caida_lista_varios_criterios(self):
        c2 = {"n_fuentes": 5, "n_clasicas": 1, "n_modernas": 2, "n_es": 1}
        c3 = {"n_fuentes": 3, "n_clasicas": 0, "n_modernas": 2, "n_es": 0}
        motivo = cobertura_v3._motivo_caida(c2, c3)
        self.assertEqual(len(motivo), 3)
        self.assertTrue(any("fuentes" in m for m in motivo))
        self.assertTrue(any("clasica" in m for m in motivo))
        self.assertTrue(any("es" in m for m in motivo))


class ReunionEvidencias(unittest.TestCase):
    def test_reune_web_y_libros_con_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = os.path.join(tmp, "web.jsonl")
            libros = os.path.join(tmp, "libros.jsonl")
            claves = os.path.join(tmp, "claves.jsonl")
            with open(web, "w", encoding="utf-8") as f:
                f.write(json.dumps(ev("tarot-mayor-01", "amor", "w1",
                                     "moderna", "es")) + "\n")
            with open(libros, "w", encoding="utf-8") as f:
                f.write(json.dumps(ev("tarot-mayor-01", "amor", "L1",
                                     "clasica", "en", tipo="libro",
                                     hash_seccion="HX")) + "\n")
            with open(claves, "w", encoding="utf-8") as f:
                f.write(json.dumps({"hash_seccion": "HX",
                                   "entidad_id": "tarot-mayor-01",
                                   "faceta": "amor"}) + "\n")
            claves_set = cobertura_v3.cargar_claves_exclusion(claves)
            evidencias, info = cobertura_v3.reunir_evidencias(
                web, libros, claves=claves_set)
            self.assertEqual(len(evidencias), 1)
            self.assertEqual(info["origenes"]["web"]["leidas"], 1)
            self.assertEqual(info["origenes"]["libros"]["leidas"], 1)
            self.assertEqual(info["excluidas"], 1)
            self.assertEqual(info["claves_cargadas"], 1)

    def test_ficheros_ausentes_no_rompen(self):
        evidencias, info = cobertura_v3.reunir_evidencias(
            "/no/existe/web.jsonl", "/no/existe/libros.jsonl")
        self.assertEqual(evidencias, [])
        self.assertEqual(info["origenes"]["web"]["leidas"], 0)


class InformeHuecos(unittest.TestCase):
    def setUp(self):
        self.catalogo = [
            {"entidad_id": "1|camino_de_vida", "familia": "numerologia",
             "subtipo": "numero_posicion", "nombre": "Camino de vida 1"},
            {"entidad_id": "2|destino", "familia": "numerologia",
             "subtipo": "numero_posicion", "nombre": "Destino 2"},
        ]
        self.facetas = cobertura.FACETAS_POR_FAMILIA["numerologia"]

    def _celda(self, ent, faceta, n, cl=0, mo=0, es=0):
        completa = (n >= 5 and cl >= 1 and mo >= 2 and es >= 1)
        return {"entidad_id": ent, "faceta": faceta, "n_fuentes": n,
                "n_clasicas": cl, "n_modernas": mo, "n_es": es,
                "completa": completa, "faltan": []}

    def test_top_entidades_orden_y_carencias(self):
        celdas = []
        for faceta in self.facetas:
            celdas.append(self._celda("1|camino_de_vida", faceta, 0))
        celdas.append(self._celda("2|destino", self.facetas[0], 1))
        top = cobertura_v3.top_entidades_incompletas(celdas, self.catalogo,
                                                    top_n=30)
        self.assertIn("numerologia", top)
        self.assertEqual(top["numerologia"][0]["entidad_id"],
                        "1|camino_de_vida")
        self.assertEqual(top["numerologia"][0]["celdas_incompletas"],
                         len(self.facetas))
        self.assertEqual(top["numerologia"][0]["falta_independientes"],
                         5 * len(self.facetas))
        self.assertEqual(top["numerologia"][1]["falta_independientes"], 4)

    def test_dominios_top_por_familia(self):
        evidencias = [
            ev("1|camino_de_vida", "amor", "a.com/x", "moderna", "es",
               dominio="a.com"),
            ev("1|camino_de_vida", "dinero", "a.com/y", "moderna", "es",
               dominio="a.com"),
            ev("2|destino", "amor", "b.com/z", "moderna", "en",
               dominio="b.com"),
            ev("2|destino", "amor", "c.com/w", "moderna", "en",
               dominio="c.com", calidad=2),
        ]
        top = cobertura_v3.dominios_top_por_familia(evidencias, self.catalogo,
                                                   top_n=10)
        self.assertEqual(top["numerologia"][0]["dominio"], "a.com")
        self.assertEqual(top["numerologia"][0]["n_entidades"], 1)
        self.assertEqual(top["numerologia"][0]["n_evidencias"], 2)
        dominios = {d["dominio"] for d in top["numerologia"]}
        self.assertNotIn("c.com", dominios)

    def test_estimacion_meta_10pct(self):
        celdas = []
        for faceta in self.facetas:
            celdas.append(self._celda("1|camino_de_vida", faceta, 0))
        celdas.append(self._celda("2|destino", self.facetas[0], 5, 1, 2, 1))
        for faceta in self.facetas[1:]:
            celdas.append(self._celda("2|destino", faceta, 4, 1, 2, 1))
        est = cobertura_v3.estimacion_meta_por_familia(celdas, self.catalogo,
                                                      meta=0.10)
        datos = est["numerologia"]
        total = 2 * len(self.facetas)
        self.assertEqual(datos["celdas"], total)
        self.assertEqual(datos["completas"], 1)
        self.assertEqual(datos["meta_completas"], -(-total // 10))
        self.assertEqual(datos["celdas_faltantes"], -(-total // 10) - 1)
        self.assertGreater(datos["fuentes_ideales"], 0)
        self.assertGreaterEqual(datos["fuentes_total_arreglar"],
                               datos["fuentes_ideales"])

    def test_ritmo_observado(self):
        evidencias = [
            ev("1|camino_de_vida", "amor", "s1", "moderna", "es"),
            ev("1|camino_de_vida", "dinero", "s1", "moderna", "es"),
            ev("2|destino", "amor", "s2", "moderna", "en"),
            ev("2|destino", "amor", "s3", "moderna", "en", calidad=1),
        ]
        ritmo = cobertura_v3.ritmo_observado_por_familia(evidencias,
                                                        self.catalogo)
        self.assertEqual(ritmo["numerologia"], 2)


class PipelineCompleto(unittest.TestCase):
    def test_construir_v3_y_escritura(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = os.path.join(tmp, "web.jsonl")
            libros = os.path.join(tmp, "libros.jsonl")
            v2 = os.path.join(tmp, "v2.json")
            with open(web, "w", encoding="utf-8") as f:
                for e in cinco_fuentes_completas("tarot-mayor-01",
                                                "significado_general"):
                    f.write(json.dumps(e) + "\n")
            with open(libros, "w", encoding="utf-8") as f:
                f.write(json.dumps(ev("tarot-mayor-01", "significado_general",
                                     "libroA", "clasica", "en", tipo="libro",
                                     hash_seccion="HZ")) + "\n")
            with open(v2, "w", encoding="utf-8") as f:
                json.dump({"resumen": {"completas": 0}, "celdas": [
                    {"entidad_id": "tarot-mayor-01",
                     "faceta": "significado_general",
                     "n_fuentes": 4, "n_clasicas": 1, "n_modernas": 2,
                     "n_es": 1, "completa": False}]}, f)
            datos = cobertura_v3.construir_v3(web, libros, claves=None,
                                             ruta_v2=v2)
            self.assertEqual(datos["resumen"]["completas"], 1)
            comp = datos["comparacion_v2"]
            self.assertEqual(len(comp["pasan_a_completas"]), 1)
            cobertura_v3.escribir_json(datos, os.path.join(tmp, "v3.json"))
            cobertura_v3.escribir_md(datos, os.path.join(tmp, "v3.md"))
            with open(os.path.join(tmp, "v3.json"), encoding="utf-8") as f:
                leido = json.load(f)
            self.assertEqual(leido["resumen"]["total_celdas"],
                             datos["resumen"]["total_celdas"])
            with open(os.path.join(tmp, "v3.md"), encoding="utf-8") as f:
                md = f.read()
            self.assertIn("Comparación con la v2", md)
            self.assertIn("Informe de huecos por familia", md)
            self.assertIn("Estimación para el 10 %", md)


class Cli(unittest.TestCase):
    def test_dry_run_no_escribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = os.path.join(tmp, "web.jsonl")
            libros = os.path.join(tmp, "libros.jsonl")
            with open(web, "w", encoding="utf-8") as f:
                for e in cinco_fuentes_completas("tarot-mayor-01", "amor"):
                    f.write(json.dumps(e) + "\n")
            open(libros, "w").close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cobertura_v3.main([
                    "--web", web, "--libros-crudo", libros,
                    "--sin-excluir-claves", "--v2",
                    os.path.join(tmp, "noexiste.json"),
                    "--out-dir", os.path.join(tmp, "salida"),
                    "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertIn("simulación", out.getvalue())
            self.assertFalse(os.path.exists(os.path.join(tmp, "salida")))

    def test_run_real_escribe_v3(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = os.path.join(tmp, "web.jsonl")
            libros = os.path.join(tmp, "libros.jsonl")
            with open(web, "w", encoding="utf-8") as f:
                for e in cinco_fuentes_completas("naipe-oros-01",
                                                "significado_general"):
                    f.write(json.dumps(e) + "\n")
            open(libros, "w").close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cobertura_v3.main([
                    "--web", web, "--libros-crudo", libros,
                    "--sin-excluir-claves", "--v2",
                    os.path.join(tmp, "noexiste.json"),
                    "--out-dir", tmp])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "cobertura_total_v3.json")))
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "cobertura_total_v3.md")))

    def test_seleccion_libros_crudo_vs_limpio(self):
        with tempfile.TemporaryDirectory() as tmp:
            web = os.path.join(tmp, "web.jsonl")
            limpio = os.path.join(tmp, "limpio.jsonl")
            crudo = os.path.join(tmp, "crudo.jsonl")
            open(web, "w").close()
            with open(limpio, "w", encoding="utf-8") as f:
                for e in cinco_fuentes_completas("tarot-mayor-02", "amor",
                                                prefijo="l"):
                    f.write(json.dumps(e) + "\n")
            open(crudo, "w").close()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cobertura_v3.main(["--web", web, "--libros-limpio", limpio,
                                  "--libros-crudo", crudo,
                                  "--sin-excluir-claves", "--v2",
                                  os.path.join(tmp, "noexiste.json"),
                                  "--out-dir", tmp, "--dry-run"])
            self.assertIn("Tarot: 1/936", out.getvalue())
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                cobertura_v3.main(["--web", web, "--libros", "crudo",
                                  "--libros-limpio", limpio,
                                  "--libros-crudo", crudo,
                                  "--sin-excluir-claves", "--v2",
                                  os.path.join(tmp, "noexiste.json"),
                                  "--out-dir", tmp, "--dry-run"])
            self.assertIn("Tarot: 0/936", out2.getvalue())


if __name__ == "__main__":
    unittest.main()
