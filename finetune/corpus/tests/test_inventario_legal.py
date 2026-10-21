"""Tests del inventario legal: manifiestos sintéticos y clasificación de riesgo."""
import csv
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura
import inventario_legal


def escribir_jsonl(ruta, filas):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


class InventarioSintetico(unittest.TestCase):
    """Construye una fase 0 mínima con un caso de cada tipo de fuente."""

    @classmethod
    def setUpClass(cls):
        cls.entidad = cobertura.entidades()[0]["entidad_id"]
        cls.faceta = "significado_general"

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.raiz = self.temporal.name
        self.fase0 = os.path.join(self.raiz, "fase0")
        self.knowledge = os.path.join(self.raiz, "knowledge")
        os.makedirs(self.knowledge)
        self._escribir_fuentes()
        self.inventario = inventario_legal.construir_inventario(
            self.fase0, self.knowledge)
        self.por_id = {f["id"]: f for f in self.inventario["fuentes"]}

    def tearDown(self):
        self.temporal.cleanup()

    def _evidencia(self, tipo, fuente, dominio="", periodo="moderna",
                   idioma="es", calidad=3, hash_seccion=""):
        fila = {
            "entidad_id": self.entidad,
            "faceta": self.faceta,
            "fuente_id": fuente,
            "dominio": dominio,
            "periodo": periodo,
            "idioma": idioma,
            "calidad": calidad,
            "tipo": tipo,
        }
        if hash_seccion:
            fila["hash_seccion"] = hash_seccion
        return fila

    def _afirmacion(self, fuente, dominio="", entidad=None, faceta=None):
        return {
            "entidad_id": entidad or self.entidad,
            "faceta": faceta or self.faceta,
            "fuente_id": fuente,
            "dominio": dominio,
            "periodo": "moderna",
            "calidad": 3,
            "afirmacion": "texto sintético",
        }

    def _escribir_fuentes(self):
        escribir_jsonl(os.path.join(self.fase0, "web", "manifest.jsonl"), [
            {"url": "https://blogmoderno.example/uno",
             "dominio": "blogmoderno.example", "familia": "tarot",
             "estado": "ok", "chars": 1200},
            {"url": "https://blogmoderno.example/dos",
             "dominio": "blogmoderno.example", "familia": "tarot",
             "estado": "ok", "chars": 800},
            {"url": "https://blogmoderno.example/rota",
             "dominio": "blogmoderno.example", "familia": "tarot",
             "estado": "error", "chars": 0},
        ])

        evidencias_web = [
            self._evidencia("web", "https://blogmoderno.example/uno",
                            "blogmoderno.example"),
            self._evidencia("web", "https://sinmeta.example/a",
                            "sinmeta.example"),
            self._evidencia("web", "https://web-libre.example/a",
                            "web-libre.example"),
            self._evidencia("web", "https://premium.example/a",
                            "premium.example"),
            self._evidencia("libro", "libro_pd", periodo="clasica",
                            hash_seccion="s1"),
            self._evidencia("libro", "libro_pd", periodo="clasica",
                            hash_seccion="s2"),
            self._evidencia("libro", "libro_moderno"),
        ]
        escribir_jsonl(
            os.path.join(self.fase0, "evidencias_web", "evidencias.jsonl"),
            [e for e in evidencias_web if e["tipo"] == "web"])
        escribir_jsonl(
            os.path.join(self.fase0, "libros", "evidencias", "evidencias.jsonl"),
            [e for e in evidencias_web if e["tipo"] == "libro"])

        escribir_jsonl(
            os.path.join(self.fase0, "afirmaciones_full", "afirmaciones.jsonl"),
            [self._afirmacion("https://blogmoderno.example/uno",
                              "blogmoderno.example"),
             self._afirmacion("https://sinmeta.example/a", "sinmeta.example"),
             self._afirmacion("https://sinmeta.example/b", "sinmeta.example")])
        escribir_jsonl(
            os.path.join(self.fase0, "afirmaciones_libros",
                         "afirmaciones_libros.jsonl"),
            [self._afirmacion("libro_moderno"),
             self._afirmacion("libro_moderno"),
             self._afirmacion("libro_moderno")])

        escribir_jsonl(
            os.path.join(self.fase0, "libros", "manifiesto_clasicos_pd.jsonl"),
            [{"id": "libro_pd", "estado": "ok",
              "url_texto": "https://archive.org/download/x/libro_pd.txt",
              "familia": "tarot", "licencia_hint": "dominio_publico"}])
        escribir_jsonl(
            os.path.join(self.fase0, "libros", "secciones", "libro_pd.jsonl"),
            [{"seccion": 1}, {"seccion": 2}, {"seccion": 3}])
        escribir_jsonl(
            os.path.join(self.fase0, "libros", "secciones",
                         "libro_moderno.jsonl"),
            [{"seccion": i} for i in range(5)])

        escribir_jsonl(os.path.join(self.knowledge, "fuentes_libros.jsonl"), [
            {"id": "libro_pd", "titulo": "Obra clásica",
             "autor": "Autora, 1850-1910", "anio": 1900, "idioma": "es",
             "familia": "tarot"},
            {"id": "libro_moderno", "titulo": "Manual reciente",
             "autor": "Autor vivo", "anio": 2015, "idioma": "es",
             "familia": "tarot", "licencia_hint": "copyright"},
        ])
        escribir_jsonl(os.path.join(self.knowledge, "fuentes_web_es.jsonl"), [
            {"dominio": "blogmoderno.example", "tipo": "blog",
             "familias": ["tarot"], "idioma": "es", "periodo": "moderna",
             "licencia": "desconocida"},
            {"dominio": "premium.example", "tipo": "sitio",
             "familias": ["tarot"], "idioma": "es", "periodo": "moderna",
             "licencia": "reservada"},
        ])

        os.makedirs(os.path.join(self.fase0, "youtube", "raw_vtt"), exist_ok=True)
        with open(os.path.join(self.fase0, "youtube", "raw_vtt",
                               "VID1.es.vtt"), "w", encoding="utf-8") as f:
            f.write("WEBVTT\n")
        escribir_jsonl(
            os.path.join(self.fase0, "youtube", "catalogo.jsonl"),
            [{"id": "VID1", "canal": "Canal", "familia": "tarot"},
             {"id": "VID2", "canal": "Canal", "familia": "tarot"}])

    def test_libro_dominio_publico_libre(self):
        libro = self.por_id["libro_pd"]
        self.assertEqual(libro["riesgo"], "libre")
        self.assertTrue(libro["indicios_dominio_publico"])
        self.assertEqual(libro["n_paginas"], 3)
        self.assertEqual(libro["n_evidencias"], 2)
        self.assertEqual(libro["periodo"], "clasica")

    def test_blog_sin_licencia_consultar(self):
        blog = self.por_id["blogmoderno.example"]
        self.assertEqual(blog["riesgo"], "consultar")
        self.assertEqual(blog["n_paginas"], 2)
        self.assertEqual(blog["n_evidencias"], 1)
        self.assertEqual(blog["n_afirmaciones"], 1)
        self.assertEqual(blog["licencia_hint"], "desconocida")

    def test_libro_moderno_riesgo_alto(self):
        libro = self.por_id["libro_moderno"]
        self.assertEqual(libro["riesgo"], "riesgo_alto")
        self.assertEqual(libro["n_paginas"], 5)
        self.assertEqual(libro["n_evidencias"], 1)
        self.assertEqual(libro["n_afirmaciones"], 3)

    def test_fuente_sin_metadatos(self):
        sinmeta = self.por_id["sinmeta.example"]
        self.assertEqual(sinmeta["riesgo"], "consultar")
        self.assertEqual(sinmeta["licencia_hint"], "desconocida")
        self.assertEqual(sinmeta["n_evidencias"], 1)
        self.assertEqual(sinmeta["n_afirmaciones"], 2)

    def test_video_solo_con_subtitulos(self):
        videos = [f for f in self.inventario["fuentes"] if f["tipo"] == "video"]
        self.assertEqual([v["id"] for v in videos], ["VID1"])
        self.assertEqual(videos[0]["riesgo"], "riesgo_alto")
        self.assertEqual(videos[0]["n_paginas"], 1)

    def test_impacto_exclusion_riesgo_alto(self):
        impacto = inventario_legal.impacto_exclusion(
            self.inventario["evidencias"], self.inventario["fuentes"])
        self.assertEqual(impacto["perdidas"], 1)
        self.assertEqual(impacto["completas_despues"],
                         impacto["completas_antes"] - 1)
        self.assertEqual(impacto["detalle"][0]["entidad_id"], self.entidad)

    def test_salidas_csv_y_json(self):
        salida = os.path.join(self.raiz, "salida")
        os.makedirs(salida)
        ruta_csv = os.path.join(salida, "inventario_legal.csv")
        ruta_json = os.path.join(salida, "inventario_legal.json")
        inventario_legal.escribir_csv(self.inventario["fuentes"], ruta_csv)
        inventario_legal.escribir_json(self.inventario["fuentes"], ruta_json)
        with open(ruta_csv, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        self.assertEqual(len(filas), len(self.inventario["fuentes"]))
        self.assertEqual(filas[0]["indicios_dominio_publico"],
                         " | ".join(self.inventario["fuentes"][0]
                                    ["indicios_dominio_publico"]))
        with open(ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(len(datos["fuentes"]), len(self.inventario["fuentes"]))


class ClasificacionRiesgo(unittest.TestCase):
    """Reglas deterministas de riesgo y lectura de fechas de autor."""

    def test_anio_fallecimiento(self):
        self.assertEqual(
            inventario_legal.anio_fallecimiento("Encausse, Gérard, 1865-1916"),
            1916)
        self.assertIsNone(inventario_legal.anio_fallecimiento("Anónimo"))

    def test_dominio_publico_por_autor(self):
        indicios = inventario_legal.indicios_dominio_publico(
            "libro", "Autora, 1850-1900", 1890, "", "", anio_actual=2026)
        self.assertTrue(any("fallecido" in i for i in indicios))
        self.assertEqual(inventario_legal.clasificar_riesgo(
            "libro", "desconocida", indicios, 1890), "libre")

    def test_cc_nc_no_es_libre(self):
        self.assertEqual(inventario_legal.clasificar_riesgo(
            "web", "CC BY-NC", [], None), "consultar")

    def test_cc_by_es_libre(self):
        self.assertEqual(inventario_legal.clasificar_riesgo(
            "web", "CC BY-SA", [], None), "libre")

    def test_anio_en_id(self):
        self.assertEqual(inventario_legal._anio_en_id("RobertWang-1983"), 1983)
        self.assertIsNone(
            inventario_legal._anio_en_id("in.ernet.dli.2015.128064"))
        self.assertIsNone(inventario_legal._anio_en_id("sin-anio"))

    def test_libro_moderno_sin_anio_queda_consultar(self):
        self.assertEqual(inventario_legal.clasificar_riesgo(
            "libro", "desconocida", [], None), "consultar")
        self.assertEqual(inventario_legal.clasificar_riesgo(
            "libro", "desconocida", [], 1950), "riesgo_alto")

    def test_normalizar_dominio(self):
        self.assertEqual(
            inventario_legal.normalizar_dominio("https://www.Ejemplo.com:8080/x"),
            "ejemplo.com")


if __name__ == "__main__":
    unittest.main()
