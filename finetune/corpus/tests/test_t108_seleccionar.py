#!/usr/bin/env python3
"""Tests de seleccionar_regenerar (T108)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import seleccionar_regenerar as sr  # noqa: E402


def lecturas_sinteticas():
    return [
        {"id": 1, "bloque": "tarot_1", "gpt": "a"},
        {"id": 2, "bloque": "tarot_1", "gpt": "b"},
        {"id": 3, "bloque": "tarot_1", "gpt": "c"},
        {"id": 4, "bloque": "tarot_1", "gpt": "d"},
        {"id": 5, "bloque": "numerologia", "gpt": "e"},
        {"id": 6, "bloque": "numerologia", "gpt": "f"},
    ]


def hallazgo(codigo):
    return {"codigo": codigo, "detalle": "", "evidencia": "", "gravedad": "alta"}


class TestPuntuacion(unittest.TestCase):
    def test_suma_pesos(self):
        puntos, motivos = sr.puntuar_lectura([
            hallazgo("apertura_formula"), hallazgo("frase_plantilla"),
            hallazgo("genero_asumido")])
        self.assertEqual(puntos, 5)
        self.assertEqual(motivos, ["apertura_formula", "frase_plantilla", "genero_asumido"])

    def test_ignora_codigos_sin_peso_y_no_duplica(self):
        puntos, motivos = sr.puntuar_lectura([
            hallazgo("muletilla"), hallazgo("apertura_formula"),
            hallazgo("apertura_formula")])
        self.assertEqual(puntos, 2)
        self.assertEqual(motivos, ["apertura_formula"])

    def test_lectura_limpia_no_puntua(self):
        self.assertEqual(sr.puntuar_lectura([]), (0, []))


class TestConstruirSeleccion(unittest.TestCase):
    def test_umbral_y_orden(self):
        lecturas = lecturas_sinteticas()
        detalle = {
            1: [hallazgo("apertura_formula")],
            2: [hallazgo("apertura_formula"), hallazgo("esquema_incumplido")],
            3: [hallazgo("genero_asumido")],
            4: [],
            5: [hallazgo("frase_plantilla")],
            6: [],
        }
        sel = sr.construir_seleccion(lecturas, detalle, umbral=2)
        self.assertEqual([s["id"] for s in sel], [2, 1, 5])
        self.assertEqual(sel[0]["puntuacion"], 4)
        self.assertEqual(sel[0]["bloque"], "tarot_1")

    def test_umbral_alto_deja_lista_vacia(self):
        sel = sr.construir_seleccion(
            lecturas_sinteticas(), {1: [hallazgo("genero_asumido")]}, umbral=5)
        self.assertEqual(sel, [])


class TestPropuestaYResumen(unittest.TestCase):
    def test_marca_treinta_por_ciento_por_bloque(self):
        lecturas = lecturas_sinteticas()
        sel = [
            {"id": 1, "bloque": "tarot_1", "puntuacion": 6, "motivos": []},
            {"id": 2, "bloque": "tarot_1", "puntuacion": 4, "motivos": []},
            {"id": 3, "bloque": "tarot_1", "puntuacion": 2, "motivos": []},
            {"id": 5, "bloque": "numerologia", "puntuacion": 2, "motivos": []},
        ]
        sr.marcar_propuesta(sel, {"tarot_1": 4, "numerologia": 2}, fraccion=0.30)
        self.assertEqual([s["propuesta"] for s in sel], [True, True, False, True])

    def test_resumen_cuenta_por_bloque(self):
        lecturas = lecturas_sinteticas()
        sel = [
            {"id": 1, "bloque": "tarot_1", "puntuacion": 2, "propuesta": True},
            {"id": 5, "bloque": "numerologia", "puntuacion": 2, "propuesta": False},
        ]
        r = sr.resumen_por_bloque(lecturas, sel)
        self.assertEqual(r["tarot_1"], {"lecturas": 4, "seleccionadas": 1, "propuestas": 1})
        self.assertEqual(r["numerologia"], {"lecturas": 2, "seleccionadas": 1, "propuestas": 0})


class TestEstimacion(unittest.TestCase):
    def test_estima_tokens_y_horas(self):
        e = sr.estimar([{}, {}])
        self.assertEqual(e["lecturas"], 2)
        self.assertEqual(e["tokens_salida"], 2600)
        self.assertEqual(e["segundos"], 8.0)
        self.assertEqual(e["horas"], 0.0)

    def test_supuestos_configurables(self):
        e = sr.estimar([{}], tokens=100, segundos=3600)
        self.assertEqual(e["tokens_salida"], 100)
        self.assertEqual(e["horas"], 1.0)


class TestIntegracion(unittest.TestCase):
    def test_seleccionar_no_modifica_lecturas_y_devuelve_propuesta(self):
        lecturas = lecturas_sinteticas()
        detalle = {1: [hallazgo("apertura_formula")], 3: [hallazgo("genero_asumido")]}
        informe = {"detalle": detalle}
        with mock.patch.object(sr.cl, "analizar_lecturas", return_value=informe):
            r = sr.seleccionar(lecturas, kb={}, umbral=2)
        self.assertEqual(r["lecturas"], 6)
        self.assertEqual([s["id"] for s in r["seleccionadas"]], [1])
        self.assertEqual([s["id"] for s in r["propuestas"]], [1])
        self.assertEqual(lecturas, lecturas_sinteticas())
        self.assertEqual(r["estimacion_propuesta"]["lecturas"], 1)

    def test_escribir_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "salida.jsonl"
            sr.escribir_jsonl([{"id": 7, "bloque": "tarot_1", "propuesta": True}], ruta)
            filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(filas[0]["id"], 7)


if __name__ == "__main__":
    unittest.main()
