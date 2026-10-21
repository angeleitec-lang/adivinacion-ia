"""Tests de la comparativa consenso local vs Mercury 3 (T76)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import comparar_consenso as cc
import consenso_kb as ck


class ClienteSimulado:
    """Cliente que devuelve una particion fija, aplica el validador y cuenta."""

    def __init__(self, respuesta=None, exc=None):
        self.respuesta = respuesta
        self.exc = exc
        self.llamadas = 0

    def chat_json(self, sistema, prompt, validador, **kwargs):
        self.llamadas += 1
        if self.exc is not None:
            raise self.exc
        validador(self.respuesta)
        return self.respuesta


def _particion_bloques(n, tam=2):
    """[[0,1],[2,3],...] con singleton final si n es impar."""
    grupos = []
    i = 0
    while i < n:
        g = list(range(i, min(i + tam, n)))
        grupos.append(g)
        i += tam
    return grupos


def _particion_singleton(n):
    return [[i] for i in range(n)]


class TestAri(unittest.TestCase):
    def test_identico(self):
        self.assertAlmostEqual(
            cc.ari([[0, 1], [2, 3]], [[0, 1], [2, 3]]), 1.0)

    def test_cruzado_valor_conocido(self):
        # n=4, dos bisecciones cruzadas: ARI = -0.5
        self.assertAlmostEqual(
            cc.ari([[0, 1], [2, 3]], [[0, 2], [1, 3]]), -0.5)

    def test_singleton_vs_grupo_completo(self):
        self.assertAlmostEqual(
            cc.ari([[0], [1], [2]], [[0, 1, 2]]), 0.0)

    def test_insuficientes(self):
        self.assertIsNone(cc.ari([[0]], [[0]]))
        self.assertIsNone(cc.ari([], []))


class TestParesCocluster(unittest.TestCase):
    def test_grupo_y_singleton(self):
        self.assertEqual(
            cc.pares_cocluster([[0, 1, 2], [3]]),
            {(0, 1), (0, 2), (1, 2)})

    def test_todo_singleton(self):
        self.assertEqual(cc.pares_cocluster([[0], [1], [2]]), set())

    def test_orden_invariante(self):
        self.assertEqual(
            cc.pares_cocluster([[2, 0], [1]]), {(0, 2)})


class TestContarDerivados(unittest.TestCase):
    def setUp(self):
        self.regs = [
            {"fuente_id": "f1"},
            {"fuente_id": "f1"},
            {"fuente_id": "f2"},
            {"fuente_id": "f3"},
        ]

    def test_mayoritaria_por_dos_fuentes(self):
        d = cc.contar_derivados([[0, 2], [1], [3]], [], self.regs)
        self.assertEqual(d["mayoritarias"], 1)
        self.assertEqual(d["unicas"], 2)
        self.assertEqual(d["discrepancias"], 0)

    def test_discrepancia_excluye_unicas(self):
        d = cc.contar_derivados([[0, 2], [1], [3]], [[1, 3]], self.regs)
        self.assertEqual(d["mayoritarias"], 1)
        self.assertEqual(d["unicas"], 0)
        self.assertEqual(d["discrepancias"], 1)

    def test_discrepancia_intragrupo_ignorada(self):
        d = cc.contar_derivados([[0, 2], [1], [3]], [[0, 2]], self.regs)
        self.assertEqual(d["discrepancias"], 0)
        self.assertEqual(d["unicas"], 2)

    def test_mayoritaria_puede_estar_en_discrepancia(self):
        d = cc.contar_derivados([[0, 2], [1], [3]], [[0, 1]], self.regs)
        self.assertEqual(d["mayoritarias"], 1)
        self.assertEqual(d["unicas"], 1)
        self.assertEqual(d["discrepancias"], 1)

    def test_pares_duplicados_cuentan_una(self):
        d = cc.contar_derivados([[0, 2], [1], [3]],
                               [[1, 3], [3, 1]], self.regs)
        self.assertEqual(d["discrepancias"], 1)


class TestCompararCelda(unittest.TestCase):
    def _sel(self):
        textos = [
            "Aries muestra una iniciativa firme cuando afronta desafios nuevos.",
            "Aries se caracteriza por la iniciativa y el coraje.",
            "En aries predominan la impulsividad y el deseo de liderar.",
            "Aries prefiere actuar primero y reflexionar despues.",
        ]
        regs = [
            {"fuente_id": "f1", "afirmacion": textos[0]},
            {"fuente_id": "f2", "afirmacion": textos[1]},
            {"fuente_id": "f1", "afirmacion": textos[2]},
            {"fuente_id": "f2", "afirmacion": textos[3]},
        ]
        return {
            "clave": ("aries|signo", "personalidad"),
            "familia": "signo",
            "regs": regs,
            "textos": textos,
            "local": {"grupos": [[0, 1], [2, 3]], "contradicciones": []},
        }

    def test_misma_particion_ari_uno(self):
        cliente = ClienteSimulado(
            {"grupos": [[0, 1], [2, 3]], "contradicciones": []})
        r = cc.comparar_celda(self._sel(), cliente)
        self.assertAlmostEqual(r["ari"], 1.0)
        self.assertFalse(r["fallback_mercury"])
        self.assertIsNone(r["error"])
        self.assertEqual(r["ejemplos"], [])
        self.assertEqual(r["pares_fusion_local_no_mercury"], 0)
        self.assertEqual(r["pares_fusion_mercury_no_local"], 0)

    def test_diferente_particion_ejemplos_y_recuentos(self):
        cliente = ClienteSimulado(
            {"grupos": [[0], [1], [2, 3]], "contradicciones": []})
        r = cc.comparar_celda(self._sel(), cliente)
        self.assertIsNotNone(r["ari"])
        self.assertLess(r["ari"], 1.0)
        self.assertEqual(r["pares_fusion_local_no_mercury"], 1)
        self.assertEqual(r["pares_fusion_mercury_no_local"], 0)
        tipos = {e["tipo"] for e in r["ejemplos"]}
        self.assertEqual(tipos, {"fusion_local_no_mercury"})
        ej = r["ejemplos"][0]
        self.assertEqual((ej["i"], ej["j"]), (0, 1))
        self.assertEqual(
            ej["texto_i"],
            "Aries muestra una iniciativa firme cuando afronta desafios nuevos.")
        self.assertEqual(
            ej["texto_j"],
            "Aries se caracteriza por la iniciativa y el coraje.")

    def test_fallback_por_valueerror(self):
        cliente = ClienteSimulado(exc=ValueError("json invalido"))
        r = cc.comparar_celda(self._sel(), cliente)
        self.assertTrue(r["fallback_mercury"])
        self.assertIsNone(r["ari"])
        self.assertIsNone(r["error"])

    def test_error_de_red_no_tumba(self):
        cliente = ClienteSimulado(exc=ConnectionError("sin conexion"))
        r = cc.comparar_celda(self._sel(), cliente)
        self.assertIsNone(r["ari"])
        self.assertFalse(r["fallback_mercury"])
        self.assertIn("ConnectionError", r["error"])
        self.assertIn("sin conexion", r["error"])

    def test_latencia_registrada(self):
        cliente = ClienteSimulado(
            {"grupos": [[0, 1], [2, 3]], "contradicciones": []})
        r = cc.comparar_celda(self._sel(), cliente)
        self.assertIsInstance(r["latencia_s"], float)
        self.assertGreaterEqual(r["latencia_s"], 0.0)


class TestSeleccionarCeldas(unittest.TestCase):
    def _datos(self, n_afs=10, fuentes=("f1", "f2")):
        claves = [
            ("aries|signo", "personalidad"),
            ("tauro|signo", "caracter"),
            ("naipe-oros-1", "significado"),
            ("12|camino_de_vida", "descripcion"),
        ]
        consenso, celdas, cache = {}, {}, {}
        for eid, faceta in claves:
            regs = []
            for k in range(n_afs):
                regs.append({
                    "entidad_id": eid,
                    "faceta": faceta,
                    "fuente_id": fuentes[k % len(fuentes)],
                    "afirmacion": "%s afirmacion numero %d con texto suficiente."
                                 % (eid, k),
                })
            textos = [r["afirmacion"] for r in regs][:ck.MAX_POR_CELDA]
            clave_cache = ck.CacheEquivalencia.clave(eid, faceta, textos)
            consenso[(eid, faceta)] = {"n_afirmaciones": n_afs}
            celdas[(eid, faceta)] = regs
            cache[clave_cache] = {
                "grupos": _particion_singleton(len(textos)),
                "contradicciones": [],
            }
        return consenso, celdas, cache

    def test_determinismo_misma_semilla(self):
        consenso, celdas, cache = self._datos()
        s1 = cc.seleccionar_celdas(consenso, celdas, cache, n=3, semilla=76)
        s2 = cc.seleccionar_celdas(consenso, celdas, cache, n=3, semilla=76)
        self.assertEqual([s["clave"] for s in s1], [s["clave"] for s in s2])

    def test_mecla_familias(self):
        consenso, celdas, cache = self._datos()
        sel = cc.seleccionar_celdas(consenso, celdas, cache, n=4, semilla=76)
        familias = {s["familia"] for s in sel}
        self.assertGreaterEqual(len(familias), 2)

    def test_excluye_pocas_afirmaciones(self):
        consenso, celdas, cache = self._datos(n_afs=cc.MIN_AFIRMACIONES - 1)
        sel = cc.seleccionar_celdas(consenso, celdas, cache, n=4, semilla=1)
        self.assertEqual(sel, [])

    def test_excluye_una_sola_fuente(self):
        consenso, celdas, cache = self._datos(fuentes=("f1",))
        sel = cc.seleccionar_celdas(consenso, celdas, cache, n=4, semilla=1)
        self.assertEqual(sel, [])

    def test_excluye_sin_cache(self):
        consenso, celdas, cache = self._datos()
        sel = cc.seleccionar_celdas(consenso, celdas, {}, n=4, semilla=1)
        self.assertEqual(sel, [])

    def test_campos_del_seleccionado(self):
        consenso, celdas, cache = self._datos()
        sel = cc.seleccionar_celdas(consenso, celdas, cache, n=1, semilla=7)
        self.assertEqual(len(sel), 1)
        s = sel[0]
        for campo in ("clave", "familia", "regs", "textos", "local"):
            self.assertIn(campo, s)
        self.assertIn("grupos", s["local"])


class TestResumir(unittest.TestCase):
    def _res(self, ari=None, error=None, fallback=False, lat=2.0):
        return {
            "ari": ari,
            "error": error,
            "fallback_mercury": fallback,
            "latencia_s": lat,
            "local_derivados": {"mayoritarias": 1, "unicas": 2,
                               "discrepancias": 0},
            "mercury_derivados": {"mayoritarias": 1, "unicas": 1,
                                 "discrepancias": 1},
        }

    def test_delegable_por_encima_del_umbral(self):
        r = cc.resumir([self._res(ari=0.9), self._res(ari=0.88)])
        self.assertAlmostEqual(r["ari_medio"], 0.89)
        self.assertTrue(r["delegable"])
        self.assertEqual(r["comparables"], 2)

    def test_no_delegable_por_debajo(self):
        r = cc.resumir([self._res(ari=0.9), self._res(ari=0.9),
                        self._res(ari=0.5)])
        self.assertLess(r["ari_medio"], cc.UMBRAL_ACUERDO)
        self.assertFalse(r["delegable"])
        self.assertEqual(r["celdas_ari_85"], 2)

    def test_errores_y_fallbacks_no_cuentan_como_ari(self):
        r = cc.resumir([self._res(ari=0.9),
                        self._res(error="boom"),
                        self._res(fallback=True)])
        self.assertEqual(r["total"], 3)
        self.assertEqual(r["comparables"], 1)
        self.assertEqual(r["errores"], 1)
        self.assertEqual(r["fallbacks"], 1)

    def test_recuentos_acumulados(self):
        r = cc.resumir([self._res(ari=0.9), self._res(ari=0.95)])
        self.assertEqual(r["mayoritarias_local"], 2)
        self.assertEqual(r["unicas_mercury"], 2)
        self.assertEqual(r["discrepancias_mercury"], 2)

    def test_horas_ahorradas(self):
        r = cc.resumir([self._res(ari=0.9, lat=2.0)], pendientes_locales=360)
        self.assertAlmostEqual(r["horas_locales_restantes"], 6.0)
        self.assertAlmostEqual(r["horas_mercury"], 0.2)
        self.assertAlmostEqual(r["horas_ahorradas"], 5.8)

    def test_sin_aris_no_hay_delegable(self):
        r = cc.resumir([self._res(error="boom")], pendientes_locales=100)
        self.assertIsNone(r["ari_medio"])
        self.assertNotIn("delegable", r)
        self.assertNotIn("horas_ahorradas", r)


class TestInforme(unittest.TestCase):
    def _resumen(self, **extra):
        base = {
            "total": 3, "comparables": 3, "errores": 0, "fallbacks": 0,
            "ari_medio": 0.9, "ari_mediana": 0.9,
            "celdas_ari_85": 3, "pct_celdas_85": 100.0,
            "latencia_media_s": 2.0, "latencia_mediana_s": 2.0,
            "mayoritarias_local": 5, "mayoritarias_mercury": 5,
            "unicas_local": 4, "unicas_mercury": 3,
            "discrepancias_local": 1, "discrepancias_mercury": 2,
            "pendientes": 360, "delegable": True,
            "horas_locales_restantes": 6.0, "horas_mercury": 0.2,
            "horas_ahorradas": 5.8,
        }
        base.update(extra)
        return base

    def _resultados_con_ejemplo(self):
        return [{
            "entidad_id": "aries|signo", "faceta": "personalidad",
            "familia": "signo", "n_textos": 4, "latencia_s": 2.0,
            "error": None, "fallback_mercury": False, "ari": 0.5,
            "pares_fusion_local_no_mercury": 1,
            "pares_fusion_mercury_no_local": 0,
            "ejemplos": [{
                "tipo": "fusion_local_no_mercury", "i": 0, "j": 1,
                "texto_i": "Texto primero.", "texto_j": "Texto segundo.",
            }],
        }]

    def _leer(self, ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            return f.read()

    def test_conclusion_delegable(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "inf.md")
            cc.escribir_informe(ruta, self._resumen(), [])
            texto = self._leer(ruta)
            self.assertIn("## Conclusión", texto)
            self.assertIn("**Sí**", texto)
            self.assertIn("Horas ahorradas", texto)
            self.assertIn("mercury-3", texto)

    def test_conclusion_no_delegable(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "inf.md")
            cc.escribir_informe(
                ruta,
                self._resumen(ari_medio=0.4, ari_mediana=0.4,
                             celdas_ari_85=0, pct_celdas_85=0.0,
                             delegable=False),
                [])
            texto = self._leer(ruta)
            self.assertIn("**No**", texto)
            self.assertNotIn("Horas ahorradas", texto)

    def test_sin_datos_comparables(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "inf.md")
            resumen = self._resumen(ari_medio=None, ari_mediana=None,
                                   celdas_ari_85=0, pct_celdas_85=None,
                                   comparables=0)
            resumen.pop("delegable")
            cc.escribir_informe(ruta, resumen, [])
            self.assertIn("Sin datos comparables", self._leer(ruta))

    def test_ejemplos_incluidos(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "inf.md")
            cc.escribir_informe(ruta, self._resumen(),
                                self._resultados_con_ejemplo())
            texto = self._leer(ruta)
            self.assertIn("El nodo local fusionó y Mercury no", texto)
            self.assertIn("Texto primero.", texto)
            self.assertIn("aries|signo", texto)


class TestMainEndToEnd(unittest.TestCase):
    """Main con ficheros temporales, caché reconstruida y cliente simulado."""

    TEXTOS = [
        "Aries muestra una iniciativa firme cuando afronta desafios nuevos.",
        "Aries se caracteriza por la iniciativa y el coraje ante el peligro.",
        "En aries predominan la impulsividad y el deseo de liderar el grupo.",
        "Aries prefiere actuar primero y reflexionar despues de cada decision.",
        "El signo de aries valora la competencia y la victoria rapida.",
        "Aries aborda los conflictos con energia y poca paciencia esperando.",
        "Las personas de aries buscan metas claras y las persiguen sin dudarlo.",
        "Aries necesita desafios constantes para no aburrirse de la rutina.",
        "En el caracter de aries destaca el coraje y la franqueza directa.",
        "Aries tiende a iniciar proyectos con entusiasmo pero le cuesta acabar.",
    ]

    def _escribir_web(self, ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            for k, texto in enumerate(self.TEXTOS):
                f.write(json.dumps({
                    "entidad_id": "aries|signo",
                    "faceta": "personalidad",
                    "fuente_id": "f%d" % (k % 2 + 1),
                    "afirmacion": texto,
                }, ensure_ascii=False) + "\n")

    def test_main_con_cliente_simulado(self):
        with tempfile.TemporaryDirectory() as d:
            web = os.path.join(d, "web.jsonl")
            libros = os.path.join(d, "libros.jsonl")
            open(libros, "w").close()
            self._escribir_web(web)

            celdas = cc.reconstruir_celdas(web, libros)
            clave = ("aries|signo", "personalidad")
            self.assertIn(clave, celdas)
            textos = [r["afirmacion"] for r in celdas[clave]]
            n = len(textos)
            self.assertEqual(n, len(self.TEXTOS))

            clave_cache = ck.CacheEquivalencia.clave("aries|signo",
                                                   "personalidad", textos)
            cache = os.path.join(d, "cache.jsonl")
            with open(cache, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "clave": clave_cache,
                    "respuesta": {
                        "grupos": _particion_bloques(n, 2),
                        "contradicciones": [],
                    },
                }, ensure_ascii=False) + "\n")

            consenso = os.path.join(d, "consenso.jsonl")
            with open(consenso, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "entidad_id": "aries|signo",
                    "faceta": "personalidad",
                    "n_afirmaciones": n,
                }) + "\n")

            informe = os.path.join(d, "inf.md")
            cliente = ClienteSimulado(
                {"grupos": _particion_singleton(n), "contradicciones": []})
            resumen = cc.main([
                "--consenso", consenso, "--cache", cache,
                "--web", web, "--libros", libros,
                "--informe", informe, "--n-celdas", "1",
            ], cliente=cliente)
            self.assertEqual(resumen["comparables"], 1)
            self.assertAlmostEqual(resumen["ari_medio"], 0.0)
            self.assertFalse(resumen["delegable"])
            self.assertTrue(os.path.exists(informe))
            self.assertEqual(cliente.llamadas, 1)

    def test_main_sin_elegibles(self):
        with tempfile.TemporaryDirectory() as d:
            web = os.path.join(d, "web.jsonl")
            open(web, "w").close()
            libros = os.path.join(d, "libros.jsonl")
            open(libros, "w").close()
            consenso = os.path.join(d, "consenso.jsonl")
            open(consenso, "w").close()
            cache = os.path.join(d, "cache.jsonl")
            open(cache, "w").close()
            informe = os.path.join(d, "inf.md")
            resultado = cc.main([
                "--consenso", consenso, "--cache", cache,
                "--web", web, "--libros", libros,
                "--informe", informe,
            ], cliente=ClienteSimulado({"grupos": [[0]], "contradicciones":
                                      []}))
            self.assertEqual(resultado["total"], 0)
            self.assertFalse(os.path.exists(informe))


if __name__ == "__main__":
    unittest.main()
