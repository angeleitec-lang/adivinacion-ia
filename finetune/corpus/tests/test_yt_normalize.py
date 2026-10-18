#!/usr/bin/env python3
"""Tests para yt_normalize.py (A4.6)."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_normalize
import llm_client
import unittest


LECTURA_BUENA = {
    "tipo": "lectura",
    "tirada": "3_cartas",
    "pregunta_o_tema": "amor",
    "cartas": [
        {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
        {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
        {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
    ],
    "interpretaciones": [
        {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica una decision importante en el amor"},
        {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
        {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y exito"},
    ],
    "sintesis": "La lectura muestra evolucion de bloqueo a claridad",
    "consejo": "Confia en tu intuicion",
}


def _simulado_respuesta_valida(sistema, usuario):
    # Devuelve directamente el texto GPT (no JSON completo)
    return '''En esta tirada de tres cartas sobre el amor, Los Enamorados en posición presente te hablan de una elección importante que tienes delante. La Emperatriz invertida en el pasado sugiere que has sentido un bloqueo creativo o emocional. El Sol en el futuro te trae claridad y optimismo. En síntesis, la lectura muestra una evolución desde el bloqueo hacia la luz. Consejo: confía en tu intuición y toma la decisión que tu corazón te indica.'''


def _simulado_omite_carta(sistema, usuario):
    # Omite "El Sol"
    return '''En esta tirada, Los Enamorados en presente te hablan de una elección. La Emperatriz invertida en pasado sugiere bloqueo. En síntesis, hay evolución. Consejo: confía.'''


def _simulado_con_url(sistema, usuario):
    return '''Los Enamorados en presente indican elección. La Emperatriz invertida en pasado. El Sol en futuro. Visita https://miweb.com para más. Consejo: confía.'''


def _simulado_demasiado_corto(sistema, usuario):
    return '''Los Enamorados en presente. Consejo: confía.'''


def _simulado_con_promesa(sistema, usuario):
    return '''Los Enamorados en presente te garantizan el amor. La Emperatriz invertida. El Sol. Consejo: seguro que vas a ser feliz.'''


def _simulado_con_nombre_proprio(sistema, usuario):
    return '''Los Enamorados en presente hablan de Juan. La Emperatriz invertida. El Sol en futuro. Consejo: confía.'''


class ValidarNormalizacion(unittest.TestCase):
    def test_respuesta_valida_pasa(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_respuesta_valida("", ""), LECTURA_BUENA, ""
        )
        self.assertTrue(valida, f"Fallos: {motivos}")

    def test_omite_carta_falla(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_omite_carta("", ""), LECTURA_BUENA, ""
        )
        self.assertFalse(valida)
        self.assertTrue(any("El Sol" in m for m in motivos))

    def test_con_url_falla(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_con_url("", ""), LECTURA_BUENA, ""
        )
        self.assertFalse(valida)
        self.assertTrue(any("URL" in m for m in motivos))

    def test_demasiado_corto_falla(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_demasiado_corto("", ""), LECTURA_BUENA, ""
        )
        self.assertFalse(valida)
        self.assertTrue(any("demasiado corta" in m for m in motivos))

    def test_promesa_absoluta_falla(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_con_promesa("", ""), LECTURA_BUENA, ""
        )
        self.assertFalse(valida)
        self.assertTrue(any("Promesa absoluta" in m for m in motivos))

    def test_nombre_proprio_falla(self):
        valida, motivos = yt_normalize.validar_normalizacion(
            _simulado_con_nombre_proprio("", ""), LECTURA_BUENA, ""
        )
        self.assertFalse(valida)
        self.assertTrue(any("Nombres propios" in m for m in motivos))


class NormalizarLectura(unittest.TestCase):
    def test_normalizacion_exitosa(self):
        client = llm_client.LLMClient(simulado=lambda s, u: _simulado_respuesta_valida(s, u))
        par = yt_normalize.normalizar_lectura(LECTURA_BUENA, client, video_id="vid1", canal="Canal Test")
        self.assertIsNotNone(par)
        self.assertEqual(par["meta"]["video_id"], "vid1")
        self.assertEqual(par["meta"]["tirada"], "3_cartas")
        self.assertEqual(len(par["conversations"]), 3)
        self.assertEqual(par["conversations"][0]["from"], "system")
        self.assertEqual(par["conversations"][1]["from"], "human")
        self.assertEqual(par["conversations"][2]["from"], "gpt")

    def test_normalizacion_falla_si_invalida(self):
        client = llm_client.LLMClient(simulado=lambda s, u: _simulado_omite_carta(s, u))
        par = yt_normalize.normalizar_lectura(LECTURA_BUENA, client, video_id="vid1")
        self.assertIsNone(par)


class ProcesarNormalizacion(unittest.TestCase):
    def test_reanudable_salta_procesados(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            lecturas_path = tmp / "lecturas.jsonl"
            lecturas_path.write_text(json.dumps(LECTURA_BUENA | {"video_id": "a"}) + "\n"
                                   + json.dumps(LECTURA_BUENA | {"video_id": "b"}) + "\n")
            out_dir = tmp / "out"
            out_dir.mkdir()

            # Pre-crear dataset.jsonl con 'a' ya procesado
            par_existente = {
                "conversations": [{"from": "system", "value": "s"}, {"from": "human", "value": "h"}, {"from": "gpt", "value": "g"}],
                "meta": {"video_id": "a", "canal": "", "tipo": "lectura", "tirada": "3_cartas"}
            }
            (out_dir / "dataset.jsonl").write_text(json.dumps(par_existente) + "\n")

            client = llm_client.LLMClient(simulado=lambda s, u: _simulado_respuesta_valida(s, u))
            stats = yt_normalize.procesar_normalizacion(lecturas_path, out_dir, client)
            self.assertEqual(stats["saltados"], 1)
            self.assertEqual(stats["ok"], 1)


if __name__ == "__main__":
    unittest.main()
