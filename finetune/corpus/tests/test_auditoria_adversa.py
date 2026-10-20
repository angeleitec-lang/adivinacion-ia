"""Casos adversos de la auditoría T50 (entradas reales o casi reales)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import afirmaciones_es
import fase1_prompts
import muestras
import recuperacion_dirigida
from calculos import biorritmos, numerologia

try:
    import swisseph  # noqa: F401
    SWISSEPH_AVAILABLE = True
except ImportError:
    SWISSEPH_AVAILABLE = False


class _ResolvedorVacio:
    def texto(self, nivel, registro):
        return ""

    def seccion_libro(self, registro):
        return None


class TestFase1Adversa(unittest.TestCase):

    def test_tarea_none_no_rompe(self):
        ok, motivos = fase1_prompts.verificar_lectura(None, "texto")
        self.assertFalse(ok)
        self.assertTrue(motivos)

    def test_texto_entero_no_rompe(self):
        tarea = {"cartas": [{"nombre": "El Loco"}]}
        ok, motivos = fase1_prompts.verificar_lectura(tarea, 123)
        self.assertFalse(ok)
        self.assertIn("Falta la carta de la tirada: El Loco", motivos)

    def test_palo_en_singular_no_es_falta(self):
        tarea = {"cartas": [{"nombre": "Sota de Espadas"}],
                 "universo_cartas": [{"nombre": "Sota de Espadas"}]}
        ok, motivos = fase1_prompts.verificar_lectura(
            tarea, "La sota de espada al derecho.")
        self.assertTrue(ok, motivos)

    def test_carta_del_mago_se_detecta_como_ajena(self):
        tarea = {"cartas": [{"nombre": "El Loco"}],
                 "universo_cartas": [{"nombre": "El Loco"},
                                     {"nombre": "El Mago"}]}
        ok, motivos = fase1_prompts.verificar_lectura(
            tarea, "La carta del Mago habla de inicio.")
        self.assertFalse(ok)
        self.assertTrue(any("El Mago" in m for m in motivos), motivos)

    def test_carta_none_no_rompe(self):
        tarea = {"cartas": [None]}
        ok, motivos = fase1_prompts.verificar_lectura(tarea, "texto")
        self.assertFalse(ok)
        self.assertTrue(any("no válida" in m for m in motivos), motivos)

    def test_baraja_espanola_con_universo_propio(self):
        tarea = {"cartas": [{"nombre": "As de Oros"}],
                 "universo_cartas": [{"nombre": "As de Oros"}]}
        ok, motivos = fase1_prompts.verificar_lectura(
            tarea, "El as de oros al derecho.")
        self.assertTrue(ok, motivos)


class TestMuestrasAdversa(unittest.TestCase):

    def _jsonl(self, contenido, modo="w", encoding="utf-8"):
        fd, ruta = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(ruta, modo, encoding=encoding) as fh:
            fh.write(contenido)
        self.addCleanup(os.unlink, ruta)
        return ruta

    def test_bom_en_primera_linea(self):
        ruta = self._jsonl('\ufeff{"id": "a"}\n{"id": "b"}\n')
        self.assertEqual([r["id"] for r in muestras._leer_jsonl(ruta)],
                         ["a", "b"])

    def test_linea_json_que_no_es_objeto(self):
        ruta = self._jsonl('{"id": "a"}\n[1, 2]\n"texto"\n')
        self.assertEqual([r["id"] for r in muestras._leer_jsonl(ruta)],
                         ["a"])

    def test_procedencia_web_con_fuente_id_entero(self):
        linea = muestras.procedencia_de(
            "web", {"fuente_id": 5, "dominio": "x"}, _ResolvedorVacio())
        self.assertIn("5", linea)

    def test_ficha_sin_id_y_cartas_no_lista(self):
        registro = {"cartas": 5, "entidad_id": "tarot-mayor-00",
                    "calidad": 3}
        ficha = muestras.ficha_markdown("lecturas", registro,
                                        _ResolvedorVacio())
        self.assertIn("- id: `", ficha)


class TestAfirmacionesAdversa(unittest.TestCase):

    def test_construir_prompt_con_texto_none(self):
        sistema, usuario = afirmaciones_es.construir_prompt("e", "f", None)
        self.assertTrue(sistema)
        self.assertIn("Entidad: e", usuario)

    def test_filtrar_min_calidad_con_texto_no_numerico(self):
        salida = afirmaciones_es.filtrar_min_calidad(
            [{"calidad": "alta"}, {"calidad": 3}], 2)
        self.assertEqual(salida, [{"calidad": 3}])

    def test_ordenar_evidencias_con_calidad_texto(self):
        salida = afirmaciones_es.ordenar_evidencias(
            [{"calidad": "alta"}, {"calidad": 3}], orden="calidad")
        self.assertEqual(salida[0], {"calidad": 3})

    def test_filtrar_utilidad_salta_linea_rota(self):
        fd, ruta = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"afirmacion":
                                 "La luna rige las emociones internas"},
                                ensure_ascii=False) + "\n")
            fh.write('{"afirmacion": "cortada\n')
            fh.write("[1, 2]\n")
        out_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(out_dir))
        stats = afirmaciones_es.filtrar_utilidad(ruta, out_dir)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["utiles"], 1)


class TestRecuperacionAdversa(unittest.TestCase):

    def test_celdas_sin_campos_lanzan_value_error(self):
        for matriz in (
            {"celdas": [{"faceta": "x"}]},
            {"celdas": [{"entidad_id": "tarot-mayor-00"}]},
            {"celdas": [5]},
        ):
            with self.assertRaises(ValueError):
                recuperacion_dirigida.construir_plan(matriz)

    def test_matriz_none_lanza_value_error(self):
        with self.assertRaises(ValueError):
            recuperacion_dirigida.construir_plan(None)

    def test_carencias_con_valores_nulos(self):
        celda = {"n_fuentes": None, "n_clasicas": None,
                 "n_modernas": None, "n_es": None}
        self.assertEqual(
            recuperacion_dirigida._carencias(
                celda, recuperacion_dirigida.MINIMOS),
            {"independiente": 5, "clasica": 1, "moderna": 2, "es": 1})

    def test_familia_de_entradas_no_texto(self):
        self.assertEqual(recuperacion_dirigida.familia_de(None),
                         "desconocida")
        self.assertEqual(recuperacion_dirigida.familia_de(5),
                         "desconocida")


class TestNumerologiaAdversa(unittest.TestCase):

    def test_reducir_rechaza_no_enteros(self):
        for valor in ("12", 10.5, True):
            with self.assertRaises(TypeError):
                numerologia.reducir(valor)

    def test_expresion_rechaza_nombre_no_texto(self):
        with self.assertRaises(TypeError):
            numerologia.expresion(123)

    def test_anio_personal_valida_anio(self):
        for valor in (None, 0, -5, 10000, "2026", True):
            with self.assertRaises((TypeError, ValueError)):
                numerologia.anio_personal("2000-01-01", valor)


class TestBiorritmosAdversa(unittest.TestCase):

    def test_dias_no_entero_rechazado(self):
        for valor in (None, 1.5, "3", True):
            with self.assertRaises(TypeError):
                biorritmos.biorritmos("1990-01-01", "1990-01-02", valor)

    def test_dias_negativos_rechazados(self):
        with self.assertRaises(ValueError):
            biorritmos.biorritmos("1990-01-01", "1990-01-02", -3)


@unittest.skipUnless(SWISSEPH_AVAILABLE, "swisseph no disponible")
class TestAstroAdversa(unittest.TestCase):

    def test_latitud_fuera_de_rango(self):
        from calculos.astro import carta_natal
        for lat in (91, -91):
            with self.assertRaises(ValueError):
                carta_natal("2000-01-01", "12:00", lat, 0, "UTC")

    def test_coordenadas_no_finitas(self):
        from calculos.astro import carta_natal
        for lat, lon in ((float("nan"), 0), (0, float("nan")),
                         (0, float("inf"))):
            with self.assertRaises(ValueError):
                carta_natal("2000-01-01", "12:00", lat, lon, "UTC")

    def test_longitud_200_se_normaliza(self):
        from calculos.astro import carta_natal
        carta = carta_natal("2000-01-01", "12:00", 0, 200, "UTC")
        self.assertIn("ascendente", carta)


if __name__ == "__main__":
    unittest.main()
