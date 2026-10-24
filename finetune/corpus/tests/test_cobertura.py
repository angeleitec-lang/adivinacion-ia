"""Tests del módulo cobertura: matriz de entidades × facetas y fuentes que las respaldan."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura


class CatalogoEntidades(unittest.TestCase):
    """Catálogo de entidades de la ola activa: recuentos, ids y facetas."""

    def setUp(self):
        self.entidades = cobertura.entidades()

    def _por_familia(self):
        cuenta = {}
        for e in self.entidades:
            cuenta[e["familia"]] = cuenta.get(e["familia"], 0) + 1
        return cuenta

    def _por_subtipo(self):
        cuenta = {}
        for e in self.entidades:
            cuenta[e["subtipo"]] = cuenta.get(e["subtipo"], 0) + 1
        return cuenta

    def test_recuento_por_familia(self):
        self.assertEqual(self._por_familia(), {
            "tarot": 78,
            "baraja_espanola": 40,
            "astrologia": 496,
            "numerologia": 72,
        })

    def test_recuento_por_subtipo(self):
        self.assertEqual(self._por_subtipo(), {
            "carta_tarot": 78,
            "naipe_espanol": 40,
            "signo": 12,
            "planeta_en_signo": 120,
            "planeta_en_casa": 120,
            "aspecto": 225,
            "casa": 12,
            "elemento": 4,
            "modalidad": 3,
            "numero_posicion": 72,
        })

    def test_ids_unicos_y_no_vacios(self):
        ids = [e["entidad_id"] for e in self.entidades]
        self.assertEqual(len(ids), len(set(ids)), "hay entidad_id duplicados")
        self.assertTrue(all(i and i.strip() for i in ids), "hay entidad_id vacíos")

    def test_convencion_de_ids(self):
        ids = {e["entidad_id"] for e in self.entidades}
        esperados = {
            "tarot-mayor-01", "tarot-copas-10",
            "naipe-oros-05", "naipe-espadas-10",
            "aries|signo", "piscis|signo",
            "sol|aries|planeta_en_signo", "pluton|piscis|planeta_en_signo",
            "sol|casa3|planeta_en_casa", "luna|casa12|planeta_en_casa",
            "sol|conjuncion|luna|aspecto", "saturno|oposicion|neptuno|aspecto",
            "7|camino_de_vida", "11|destino", "22|anio_personal", "33|mes_personal",
        }
        faltan = esperados - ids
        self.assertEqual(faltan, set(), f"faltan entidad_id esperados: {faltan}")

    def test_facetas_por_familia_no_vacias(self):
        for familia in ("tarot", "baraja_espanola", "astrologia", "numerologia"):
            facetas = cobertura.FACETAS_POR_FAMILIA[familia]
            self.assertTrue(facetas, f"facetas vacías para {familia}")
            self.assertIn("significado_general", facetas)

    def test_derecha_invertida_solo_en_naipes(self):
        self.assertIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["tarot"])
        self.assertIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["baraja_espanola"])
        self.assertNotIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["astrologia"])
        self.assertNotIn("derecha_invertida", cobertura.FACETAS_POR_FAMILIA["numerologia"])

    def test_nombre_legible_presente(self):
        for e in self.entidades:
            self.assertTrue(e.get("nombre"), f"sin nombre legible: {e['entidad_id']}")

    def test_facetas_sin_duplicados(self):
        for familia, facetas in cobertura.FACETAS_POR_FAMILIA.items():
            self.assertEqual(len(facetas), len(set(facetas)), f"facetas duplicadas en {familia}")


def _ev(entidad="tarot-mayor-01", faceta="significado_general", fuente="f1",
        dominio="d.com", idioma="en", periodo="moderna", calidad=4, tipo="web"):
    return {"entidad_id": entidad, "faceta": faceta, "fuente_id": fuente,
            "dominio": dominio, "idioma": idioma, "periodo": periodo,
            "calidad": calidad, "tipo": tipo}


def _celda(resultado, entidad, faceta):
    for c in resultado["celdas"]:
        if c["entidad_id"] == entidad and c["faceta"] == faceta:
            return c
    raise AssertionError(f"celda no encontrada: {entidad} × {faceta}")


class CalculoDeCeldas(unittest.TestCase):
    """Cálculo por celda: independencia, descartes y carencias."""

    def test_celda_completa(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica",
                calidad=5, tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com", periodo="moderna",
                calidad=4, tipo="libro"),
            _ev(fuente="biddy", dominio="biddytarot.com", periodo="moderna",
                calidad=4, tipo="web"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es",
                periodo="moderna", calidad=3, tipo="web"),
            _ev(fuente="jodorowsky", dominio="google.com", idioma="es",
                periodo="moderna", calidad=4, tipo="libro"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 5)
        self.assertEqual(c["n_clasicas"], 1)
        self.assertEqual(c["n_modernas"], 4)
        self.assertEqual(c["n_es"], 2)
        self.assertTrue(c["completa"])
        self.assertEqual(c["faltan"], [])

    def test_independencia_por_fuente_id(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com"),
            _ev(fuente="biddy", dominio="biddytarot.com"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es"),
            _ev(fuente="jodorowsky", dominio="google.com", idioma="es"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 5, "la misma fuente cuenta una vez")

    def test_independencia_por_dominio_web(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com", periodo="moderna", tipo="libro"),
            _ev(fuente="biddy", dominio="biddytarot.com"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es"),
            # Dos fuentes web distintas del mismo dominio cuentan una vez:
            _ev(fuente="otro_blog", dominio="biddytarot.com"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 4)

    def test_descarte_por_calidad(self):
        evidencias = [
            _ev(fuente="mala", calidad=2),
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com"),
            _ev(fuente="biddy", dominio="biddytarot.com"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 4)
        self.assertFalse(c["completa"])

    def test_calidad_min_configurable(self):
        evidencias = [_ev(fuente="f1", dominio="a.com", calidad=2),
                     _ev(fuente="f2", dominio="b.com", calidad=3)]
        res = cobertura.calcular_cobertura(evidencias, calidad_min=2)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 2)
        res3 = cobertura.calcular_cobertura(evidencias)
        c3 = _celda(res3, "tarot-mayor-01", "significado_general")
        self.assertEqual(c3["n_fuentes"], 1)

    def test_falta_una_fuente_en_espanol(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com"),
            _ev(fuente="biddy", dominio="biddytarot.com"),
            _ev(fuente="jodorowsky", dominio="google.com"),
            _ev(fuente="hand", dominio="hand.com"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["faltan"], ["falta 1 fuente en español"])

    def test_faltan_dos_fuentes_modernas(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="papus", dominio="wikisource.org", idioma="es",
                periodo="clasica", tipo="libro"),
            _ev(fuente="mathers", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="case", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="wirth", dominio="archive.org", periodo="clasica", tipo="libro"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["faltan"], ["faltan 2 fuentes modernas"])

    def test_faltan_tres_fuentes_independientes(self):
        evidencias = [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica", tipo="libro"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["faltan"], [
            "faltan 3 fuentes independientes",
            "falta 1 fuente moderna",
        ])

    def test_carencias_multiple_orden(self):
        evidencias = [_ev(fuente="f1", dominio="d1.com", idioma="en",
                         periodo="clasica", tipo="libro")]
        res = cobertura.calcular_cobertura(evidencias)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["faltan"], [
            "faltan 4 fuentes independientes",
            "faltan 2 fuentes modernas",
            "falta 1 fuente en español",
        ])

    def test_entidad_o_faceta_desconocida_se_ignora(self):
        evidencias = [
            _ev(entidad="noexiste|signo"),
            _ev(faceta="faceta_fantasma"),
            _ev(entidad="otro_falso|xyz", faceta="tampoco"),
            _ev(fuente="buena", dominio="d.net", periodo="clasica", tipo="libro"),
        ]
        res = cobertura.calcular_cobertura(evidencias)
        self.assertEqual(res["ignoradas"], 3)
        c = _celda(res, "tarot-mayor-01", "significado_general")
        self.assertEqual(c["n_fuentes"], 1)

    def test_sin_evidencias_todas_las_celdas_bajo_minimo(self):
        res = cobertura.calcular_cobertura([])
        total = sum(
            len(cobertura.FACETAS_POR_FAMILIA[e["familia"]])
            for e in cobertura.entidades()
        )
        self.assertEqual(len(res["celdas"]), total)
        self.assertEqual(res["completas"], 0)
        self.assertEqual(res["ignoradas"], 0)


class SalidaYCLI(unittest.TestCase):
    """Escritura de cobertura.json / cobertura.md y comportamiento del CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_json = os.path.join(self.tmp.name, "cobertura.json")
        self.ruta_md = os.path.join(self.tmp.name, "cobertura.md")

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir_evidencias(self, nombre, lineas):
        ruta = os.path.join(self.tmp.name, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            for linea in lineas:
                f.write(json.dumps(linea, ensure_ascii=False) + "\n")
        return ruta

    def test_integracion_tres_evidencias(self):
        ruta = self._escribir_evidencias("ev.jsonl", [
            _ev(fuente="waite", dominio="archive.org", periodo="clasica",
                tipo="libro"),
            _ev(fuente="pollack", dominio="pollack.com", faceta="luz_sombra"),
            _ev(fuente="tarotes_es", dominio="tarotes.es", idioma="es",
                entidad="aries|signo"),
        ])
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = cobertura.main([
                "--evidencias", ruta,
                "--out-json", self.ruta_json,
                "--out-md", self.ruta_md,
            ])
        self.assertEqual(codigo, 0)
        with open(self.ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["resumen"]["ignoradas"], 0)
        self.assertEqual(datos["resumen"]["total_celdas"], 7664)
        self.assertEqual(datos["resumen"]["completas"], 0)
        self.assertIn("Tarot", datos["resumen"]["por_familia"])
        with open(self.ruta_md, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("Matriz de cobertura", md)
        self.assertIn("Numerología", md)
        self.assertIn("falta 1 fuente en español", md)

    def test_dry_run_no_escribe(self):
        ruta = self._escribir_evidencias("ev.jsonl", [_ev()])
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = cobertura.main([
                "--evidencias", ruta,
                "--out-json", self.ruta_json,
                "--out-md", self.ruta_md,
                "--dry-run",
            ])
        self.assertEqual(codigo, 0)
        self.assertFalse(os.path.exists(self.ruta_json))
        self.assertFalse(os.path.exists(self.ruta_md))
        self.assertIn("cobertura", salida.getvalue().lower())

    def test_fichero_inexistente_sin_fallo(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            codigo = cobertura.main([
                "--evidencias", os.path.join(self.tmp.name, "no-existe.jsonl"),
                "--out-json", self.ruta_json,
                "--out-md", self.ruta_md,
            ])
        self.assertEqual(codigo, 0)
        with open(self.ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["resumen"]["completas"], 0)

    def test_lineas_malformadas_se_ignoran(self):
        ruta = os.path.join(self.tmp.name, "rota.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("{esto no es json}\n")
            f.write("\n")
            f.write(json.dumps(_ev(fuente="buena", dominio="d.net",
                                  periodo="clasica", tipo="libro"),
                             ensure_ascii=False) + "\n")
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            cobertura.main([
                "--evidencias", ruta,
                "--out-json", self.ruta_json,
                "--out-md", self.ruta_md,
            ])
        with open(self.ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["resumen"]["ignoradas"], 1)

    def test_max_huecos_limita_listado(self):
        resultado = cobertura.calcular_cobertura([])
        cobertura.escribir_md(resultado, self.ruta_md, max_huecos=5)
        with open(self.ruta_md, encoding="utf-8") as f:
            md = f.read()
        self.assertIn("Y 7659 celdas más bajo el mínimo", md)

    def test_ordenacion_por_carencia(self):
        celdas = [
            {"entidad_id": "c4", "faceta": "f", "n_fuentes": 5,
             "n_clasicas": 1, "n_modernas": 2, "n_es": 1},
            {"entidad_id": "c1", "faceta": "f", "n_fuentes": 0,
             "n_clasicas": 0, "n_modernas": 0, "n_es": 0},
            {"entidad_id": "c3", "faceta": "f", "n_fuentes": 3,
             "n_clasicas": 1, "n_modernas": 2, "n_es": 1},
            {"entidad_id": "c2", "faceta": "f", "n_fuentes": 1,
             "n_clasicas": 1, "n_modernas": 0, "n_es": 1},
        ]
        orden = cobertura.ordenar_por_carencia(celdas)
        self.assertEqual([c["entidad_id"] for c in orden],
                         ["c1", "c2", "c3", "c4"])


class HuecosParaRastreo(unittest.TestCase):
    """Utilidad para que las pistas de rastreo sepan qué buscar."""

    def test_solo_huecos_ordenados_por_carencia(self):
        resultado = {"celdas": [
            {"entidad_id": "poco", "faceta": "f", "n_fuentes": 4,
             "n_clasicas": 1, "n_modernas": 2, "n_es": 1, "completa": False,
             "faltan": ["falta 1 fuente independiente"]},
            {"entidad_id": "llena", "faceta": "f", "n_fuentes": 5,
             "n_clasicas": 1, "n_modernas": 2, "n_es": 1, "completa": True,
             "faltan": []},
            {"entidad_id": "vacia", "faceta": "f", "n_fuentes": 0,
             "n_clasicas": 0, "n_modernas": 0, "n_es": 0, "completa": False,
             "faltan": ["faltan 5 fuentes independientes",
                       "falta 1 fuente clásica",
                       "faltan 2 fuentes modernas",
                       "falta 1 fuente en español"]},
        ], "completas": 1, "ignoradas": 0}
        huecos = cobertura.huecos_para_rastreo(resultado)
        self.assertEqual([h["entidad_id"] for h in huecos], ["vacia", "poco"])
        for h in huecos:
            self.assertEqual(set(h.keys()), {"entidad_id", "faceta", "faltan"})
            self.assertTrue(h["faltan"], "todo hueco debe listar sus carencias")

    def test_coherencia_con_matriz_completa(self):
        evidencias = [_ev(fuente="w", dominio="a.org", periodo="clasica",
                         tipo="libro")]
        resultado = cobertura.calcular_cobertura(evidencias)
        huecos = cobertura.huecos_para_rastreo(resultado)
        self.assertEqual(len(huecos),
                         len(resultado["celdas"]) - resultado["completas"])

        def carencia(h):
            celda = next(c for c in resultado["celdas"]
                        if c["entidad_id"] == h["entidad_id"]
                        and c["faceta"] == h["faceta"])
            return (max(0, 5 - celda["n_fuentes"])
                    + max(0, 1 - celda["n_clasicas"])
                    + max(0, 2 - celda["n_modernas"])
                    + max(0, 1 - celda["n_es"]))

        valores = [carencia(h) for h in huecos]
        self.assertEqual(valores, sorted(valores, reverse=True),
                        "los huecos deben ir de mayor a menor carencia")

    def test_vacio_sin_huecos(self):
        resultado = {"celdas": [
            {"entidad_id": "e", "faceta": "f", "n_fuentes": 5, "n_clasicas": 1,
             "n_modernas": 2, "n_es": 1, "completa": True, "faltan": []},
        ], "completas": 1, "ignoradas": 0}
        self.assertEqual(cobertura.huecos_para_rastreo(resultado), [])


if __name__ == "__main__":
    unittest.main()
