"""Tests del módulo recuperacion_dirigida: plan de recuperación de celdas bajo mínimo."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recuperacion_dirigida as rd


def celda(entidad_id, faceta, n_fuentes, n_clasicas, n_modernas, n_es):
    """Celda sintética bajo los mínimos de cobertura (o completa si sobra)."""
    completa = (n_fuentes >= 5 and n_clasicas >= 1 and n_modernas >= 2 and n_es >= 1)
    return {
        "entidad_id": entidad_id,
        "faceta": faceta,
        "n_fuentes": n_fuentes,
        "n_clasicas": n_clasicas,
        "n_modernas": n_modernas,
        "n_es": n_es,
        "completa": completa,
        "faltan": [] if completa else ["falta algo"],
    }


class FuentesNecesarias(unittest.TestCase):
    """Mínimo de fuentes nuevas que satisface todas las carencias a la vez."""

    def test_celda_completa_no_necesita_nada(self):
        self.assertEqual(rd.fuentes_necesarias(celda("x", "amor", 5, 1, 2, 1)), 0)

    def test_carencia_de_independientes(self):
        c = celda("x", "amor", 3, 1, 2, 1)
        self.assertEqual(rd.fuentes_necesarias(c), 2)

    def test_clasica_y_moderna_suman(self):
        # Falta 1 clásica y 1 moderna: una fuente no puede ser ambas a la vez.
        c = celda("x", "amor", 4, 0, 1, 1)
        self.assertEqual(rd.fuentes_necesarias(c), 2)

    def test_es_dominante(self):
        c = celda("x", "amor", 5, 1, 2, 0)
        self.assertEqual(rd.fuentes_necesarias(c), 1)

    def test_max_de_las_tres_restricciones(self):
        # indep=3, clas+mod=2, es=1 → 3
        c = celda("x", "amor", 2, 0, 1, 0)
        self.assertEqual(rd.fuentes_necesarias(c), 3)

    def test_minimos_personalizados(self):
        minimos = {"fuentes": 3, "clasicas": 0, "modernas": 1, "es": 0}
        self.assertEqual(rd.fuentes_necesarias(celda("x", "amor", 1, 0, 0, 0), minimos), 2)

    def test_tipos_faltantes(self):
        c = celda("x", "amor", 4, 0, 1, 0)
        tipos = rd.tipos_faltantes(c)
        self.assertEqual(tipos, {"independiente": True, "clasica": True,
                                 "moderna": True, "es": True})


class FamiliaDe(unittest.TestCase):
    """Derivación de la familia desde el entidad_id."""

    def test_tarot(self):
        self.assertEqual(rd.familia_de("tarot-mayor-01"), "tarot")
        self.assertEqual(rd.familia_de("tarot-copas-03"), "tarot")

    def test_baraja(self):
        self.assertEqual(rd.familia_de("naipe-oros-10"), "baraja_espanola")

    def test_astrologia(self):
        self.assertEqual(rd.familia_de("tauro|signo"), "astrologia")
        self.assertEqual(rd.familia_de("sol|tauro|planeta_en_signo"), "astrologia")
        self.assertEqual(rd.familia_de("sol|casa7|planeta_en_casa"), "astrologia")
        self.assertEqual(rd.familia_de("sol|conjuncion|luna|aspecto"), "astrologia")

    def test_numerologia(self):
        self.assertEqual(rd.familia_de("7|camino_de_vida"), "numerologia")
        self.assertEqual(rd.familia_de("11|anio_personal"), "numerologia")

    def test_desconocida(self):
        self.assertEqual(rd.familia_de("runa-fehu|significado"), "desconocida")


class NombreEn(unittest.TestCase):
    """Nombres en inglés para las consultas de búsqueda."""

    def test_arcana_mayor(self):
        self.assertEqual(rd.nombre_en("tarot-mayor-01", "El Loco"), "The Fool")
        self.assertEqual(rd.nombre_en("tarot-mayor-22", "El Mundo"), "The World")

    def test_arcana_menor(self):
        self.assertEqual(rd.nombre_en("tarot-copas-03", "Tres de Copas"),
                       "Three of Cups")
        self.assertEqual(rd.nombre_en("tarot-oros-12", "Caballero de Oros"),
                       "Knight of Pentacles")
        self.assertEqual(rd.nombre_en("tarot-espadas-11", "Sota de Espadas"),
                       "Page of Swords")

    def test_signo(self):
        self.assertEqual(rd.nombre_en("escorpio|signo", "Escorpio"), "Scorpio")
        self.assertEqual(rd.nombre_en("capricornio|signo", "Capricornio"), "Capricorn")

    def test_planeta_en_signo(self):
        self.assertEqual(rd.nombre_en("sol|tauro|planeta_en_signo", "Sol en Tauro"),
                       "Sun in Taurus")

    def test_planeta_en_casa(self):
        self.assertEqual(rd.nombre_en("sol|casa7|planeta_en_casa", "Sol en casa 7"),
                       "Sun in 7th House")
        self.assertEqual(rd.nombre_en("luna|casa1|planeta_en_casa", "Luna en casa 1"),
                       "Moon in 1st House")

    def test_aspecto(self):
        self.assertEqual(rd.nombre_en("sol|trigono|luna|aspecto", "Sol trigono Luna"),
                       "Sun trine Moon")
        self.assertEqual(rd.nombre_en("mercurio|cuadratura|saturno|aspecto",
                                     "Mercurio cuadratura Saturno"),
                       "Mercury square Saturn")

    def test_numero_posicion(self):
        self.assertEqual(rd.nombre_en("7|camino_de_vida", "Camino de vida 7"),
                        "Life Path 7")
        self.assertEqual(rd.nombre_en("11|destino", "Destino 11"),
                        "Destiny Number 11")

    def test_desconocido_devuelve_nombre(self):
        self.assertEqual(rd.nombre_en("runa-fehu|x", "Fehu"), "Fehu")


class ConstruirPlan(unittest.TestCase):
    """Agrupación por entidad, rentabilidad y orden."""

    def setUp(self):
        self.matriz = {
            "resumen": {},
            "celdas": [
                celda("tarot-mayor-01", "significado_general", 2, 0, 1, 0),
                celda("tarot-mayor-01", "amor", 3, 1, 1, 1),
                celda("tarot-mayor-01", "simbolismo", 5, 1, 2, 1),  # completa
                celda("7|camino_de_vida", "amor", 4, 1, 2, 0),
            ],
        }
        self.plan = rd.construir_plan(self.matriz)

    def test_agrupa_por_entidad(self):
        ids = [p["entidad_id"] for p in self.plan]
        self.assertEqual(ids, ["tarot-mayor-01", "7|camino_de_vida"])

    def test_rentabilidad_es_facetas_bajo_minimo(self):
        self.assertEqual(self.plan[0]["rentabilidad"], 2)
        self.assertEqual(self.plan[1]["rentabilidad"], 1)

    def test_facetas_excluyen_las_completas(self):
        facetas = [f["faceta"] for f in self.plan[0]["facetas"]]
        self.assertEqual(facetas, ["significado_general", "amor"])

    def test_fuentes_necesarias_por_faceta_y_total(self):
        f0 = self.plan[0]["facetas"][0]
        self.assertEqual(f0["fuentes_necesarias"], 3)
        self.assertEqual(self.plan[0]["fuentes_necesarias"], 3 + 2)

    def test_orden_rentabilidad_desc(self):
        matriz = {
            "resumen": {},
            "celdas": [
                celda("7|camino_de_vida", "amor", 4, 1, 2, 0),
                celda("tarot-mayor-01", "amor", 4, 1, 2, 0),
                celda("tarot-mayor-01", "dinero", 4, 1, 2, 0),
            ],
        }
        plan = rd.construir_plan(matriz)
        self.assertEqual(plan[0]["entidad_id"], "tarot-mayor-01")

    def test_desconocida_tambien_entra(self):
        matriz = {"resumen": {},
                  "celdas": [celda("runa-fehu|significado", "significado_general", 1, 0, 0, 0)]}
        plan = rd.construir_plan(matriz)
        self.assertEqual(plan[0]["familia"], "desconocida")


class Consultas(unittest.TestCase):
    """Consultas ES/EN por faceta, con cualificador clásico."""

    def setUp(self):
        self.matriz = {
            "resumen": {},
            "celdas": [
                celda("tarot-mayor-01", "amor", 2, 0, 1, 0),
                celda("sol|tauro|planeta_en_signo", "simbolismo", 4, 1, 2, 0),
            ],
        }
        self.plan = {p["entidad_id"]: p for p in rd.construir_plan(self.matriz)}

    def test_consulta_es_contiene_nombre_y_faceta(self):
        es = self.plan["tarot-mayor-01"]["consultas"]["es"]
        self.assertTrue(any("El Loco" in q and "amor" in q for q in es))

    def test_consulta_en_contiene_nombre_ingles(self):
        en = self.plan["tarot-mayor-01"]["consultas"]["en"]
        self.assertTrue(any("The Fool" in q for q in en))

    def test_sin_clasica_anade_cualificador_es(self):
        es = self.plan["tarot-mayor-01"]["consultas"]["es"]
        self.assertTrue(any("Waite" in q for q in es))

    def test_sin_clasica_anade_cualificador_en(self):
        en = self.plan["tarot-mayor-01"]["consultas"]["en"]
        self.assertTrue(any("classical" in q for q in en))

    def test_con_clasica_no_anade_cualificador(self):
        es = self.plan["sol|tauro|planeta_en_signo"]["consultas"]["es"]
        self.assertFalse(any("Lilly" in q for q in es))

    def test_consultas_duplicadas_se_eliminan(self):
        for p in self.plan.values():
            for idioma in ("es", "en"):
                qs = p["consultas"][idioma]
                self.assertEqual(len(qs), len(set(qs)))


class UrlsCandidatas(unittest.TestCase):
    """URLs de sitios validados, sin descargar nada."""

    def test_tarot_english_slugs(self):
        urls = [u["url"] for u in rd.urls_candidatas("tarot-copas-03", "tarot",
                                                    "Tres de Copas")]
        joined = " ".join(urls)
        self.assertIn("three-of-cups", joined)
        self.assertTrue(any("biddytarot.com" in u for u in urls))
        self.assertTrue(any("labyrinthos.co" in u for u in urls))

    def test_tarot_es_indice(self):
        urls = [u["url"] for u in rd.urls_candidatas("tarot-mayor-01", "tarot",
                                                    "El Loco")]
        self.assertTrue(any("tarotrossana.com" in u for u in urls))

    def test_astrologia_Indices_es(self):
        urls = rd.urls_candidatas("sol|tauro|planeta_en_signo", "astrologia",
                                 "Sol en Tauro")
        self.assertTrue(len(urls) >= 1)
        self.assertTrue(all(u["nota"] for u in urls))

    def test_numerologia_indices(self):
        urls = rd.urls_candidatas("7|camino_de_vida", "numerologia",
                                 "Camino de vida 7")
        self.assertTrue(len(urls) >= 1)

    def test_desconocida_sin_urls(self):
        self.assertEqual(rd.urls_candidatas("runa-fehu|x", "desconocida", "Fehu"), [])


class EstimarMeta(unittest.TestCase):
    """Fuentes nuevas para bajar del 10% de celdas bajo mínimo."""

    def test_meta_10_por_ciento(self):
        celdas = [celda("e", "f", 5, 1, 2, 1) for _ in range(85)]
        for i in range(1, 16):
            celdas.append(celda(f"e{i}", "f", 5 - min(i, 4), 1, 2, 1))
        est = rd.estimar_meta(celdas, meta=0.10)
        self.assertEqual(est["total_celdas"], 100)
        self.assertEqual(est["bajo_minimo"], 15)
        self.assertEqual(est["max_bajo_permitido"], 9)
        # Hay que arreglar 6 celdas baratas (necesarias 1,2,3,4,4,4) → 18 fuentes.
        self.assertEqual(est["fuentes_para_meta"], 18)
        self.assertGreater(est["fuentes_total"], est["fuentes_para_meta"])

    def test_ya_bajo_meta(self):
        celdas = [celda("e", "f", 5, 1, 2, 1) for _ in range(95)]
        celdas.append(celda("mala", "f", 0, 0, 0, 0))
        est = rd.estimar_meta(celdas, meta=0.10)
        self.assertEqual(est["fuentes_para_meta"], 0)


class Informe(unittest.TestCase):
    """Informe markdown."""

    def test_contiene_familias_y_top(self):
        matriz = {
            "resumen": {},
            "celdas": [
                celda("tarot-mayor-01", "amor", 2, 0, 1, 0),
                celda("7|camino_de_vida", "amor", 4, 1, 2, 0),
            ],
        }
        plan = rd.construir_plan(matriz)
        md = rd.generar_informe(matriz, plan, top=50)
        self.assertIn("Tarot", md)
        self.assertIn("Numerología", md)
        self.assertIn("bajo mínimo", md)
        self.assertIn("El Loco", md)
        self.assertIn("10%", md)


class Main(unittest.TestCase):
    """CLI end-to-end con matriz sintética."""

    def test_main_escribe_plan_e_informe(self):
        with tempfile.TemporaryDirectory() as tmp:
            matriz_path = os.path.join(tmp, "matriz.json")
            plan_path = os.path.join(tmp, "plan.jsonl")
            informe_path = os.path.join(tmp, "informe.md")
            with open(matriz_path, "w", encoding="utf-8") as fh:
                json.dump({
                    "resumen": {},
                    "celdas": [
                        celda("tarot-mayor-01", "amor", 2, 0, 1, 0),
                        celda("tarot-mayor-01", "simbolismo", 3, 1, 1, 1),
                        celda("7|camino_de_vida", "amor", 4, 1, 2, 0),
                    ],
                }, fh)
            rc = rd.main(["--matriz", matriz_path, "--out-plan", plan_path,
                        "--out-informe", informe_path])
            self.assertEqual(rc, 0)
            with open(plan_path, encoding="utf-8") as fh:
                lineas = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(len(lineas), 2)
            self.assertEqual(lineas[0]["entidad_id"], "tarot-mayor-01")
            self.assertEqual(lineas[0]["rentabilidad"], 2)
            self.assertIn("consultas", lineas[0])
            self.assertIn("urls_candidatas", lineas[0])
            with open(informe_path, encoding="utf-8") as fh:
                self.assertIn("bajo mínimo", fh.read())

    def test_dry_run_no_escribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            matriz_path = os.path.join(tmp, "matriz.json")
            with open(matriz_path, "w", encoding="utf-8") as fh:
                json.dump({"resumen": {},
                          "celdas": [celda("7|camino_de_vida", "amor", 4, 1, 2, 0)]},
                         fh)
            plan_path = os.path.join(tmp, "plan.jsonl")
            rc = rd.main(["--matriz", matriz_path, "--out-plan", plan_path,
                         "--out-informe", os.path.join(tmp, "informe.md"),
                         "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(plan_path))

    def test_matriz_inexistente_falla(self):
        rc = rd.main(["--matriz", "/nonexistent/matriz.json"])
        self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
