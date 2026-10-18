#!/usr/bin/env python3
"""Tests para yt_classify.py (A4.4)."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_classify
import llm_client
import unittest


def _simulado_clasificacion_valida(sistema, usuario):
    return '```json\n{"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}\n```'


def _simulado_clasificacion_invalida_primero(sistema, usuario):
    # Primera llamada: inválida (calidad 10). Segunda: válida.
    if not hasattr(_simulado_clasificacion_invalida_primero, "llamadas"):
        _simulado_clasificacion_invalida_primero.llamadas = 0
    _simulado_clasificacion_invalida_primero.llamadas += 1
    if _simulado_clasificacion_invalida_primero.llamadas == 1:
        return '```json\n{"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 10, "motivo": "mal"}\n```'
    return '```json\n{"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}\n```'


class ValidarClasificacion(unittest.TestCase):
    def test_valida_correcta(self):
        d = {"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}
        yt_classify.validar_clasificacion(d)  # no debe lanzar

    def test_rechaza_tipo_invalido(self):
        d = {"tipo": "inventado", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}
        with self.assertRaises(ValueError):
            yt_classify.validar_clasificacion(d)

    def test_rechaza_familia_invalida(self):
        d = {"tipo": "lectura_individual", "familia": "inventada", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}
        with self.assertRaises(ValueError):
            yt_classify.validar_clasificacion(d)

    def test_rechaza_calidad_fuera_rango(self):
        d = {"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 10, "motivo": "ok"}
        with self.assertRaises(ValueError):
            yt_classify.validar_clasificacion(d)

    def test_rechaza_n_cartas_invalido(self):
        d = {"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 0, "calidad": 4, "motivo": "ok"}
        with self.assertRaises(ValueError):
            yt_classify.validar_clasificacion(d)


class MuestrearTexto(unittest.TestCase):
    def test_texto_corto_se_devuelve_completo(self):
        texto = "hola mundo"
        self.assertEqual(yt_classify.muestrear_texto(texto, n=100), texto)

    def test_texto_largo_toma_inicio_mitad_final(self):
        texto = "A" * 100 + "B" * 100 + "C" * 100  # 300 chars
        muestra = yt_classify.muestrear_texto(texto, n=60)
        # n=60 -> 20 por tercio + 2 separadores "..." = ~64 chars
        self.assertLessEqual(len(muestra), 70)
        self.assertIn("A", muestra)
        self.assertIn("B", muestra)
        self.assertIn("C", muestra)


class ClasificarVideo(unittest.TestCase):
    def test_clasificacion_exitosa(self):
        client = llm_client.LLMClient(simulado=_simulado_clasificacion_valida)
        res = yt_classify.clasificar_video("vid1", "Título", "Desc", "Muestra texto", client)
        self.assertEqual(res["tipo"], "lectura_individual")
        self.assertEqual(res["familia"], "tarot-lectura")
        self.assertEqual(res["tirada"], "3_cartas")
        self.assertEqual(res["calidad"], 4)

    def test_reintento_corrige_error(self):
        # Reset counter
        _simulado_clasificacion_invalida_primero.llamadas = 0
        client = llm_client.LLMClient(simulado=_simulado_clasificacion_invalida_primero)
        res = yt_classify.clasificar_video("vid1", "Título", "Desc", "Muestra", client)
        self.assertEqual(res["calidad"], 4)


class ProcesarClasificacion(unittest.TestCase):
    def test_reanudable_salta_clasificados(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text(json.dumps({"id": "a", "titulo": "A", "descripcion": ""}) + "\n"
                               + json.dumps({"id": "b", "titulo": "B", "descripcion": ""}) + "\n")
            fetch = tmp / "fetch.jsonl"
            fetch.write_text(json.dumps({"id": "a", "estado": "ok", "tipo": "manual"}) + "\n"
                           + json.dumps({"id": "b", "estado": "ok", "tipo": "manual"}) + "\n")
            out_dir = tmp / "out"
            out_dir.mkdir()

            # Pre-crear clasificacion.jsonl con 'a' ya clasificado
            (out_dir / "clasificacion.jsonl").write_text(
                json.dumps({"video_id": "a", "tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}) + "\n"
            )

            client = llm_client.LLMClient(simulado=_simulado_clasificacion_valida)
            stats = yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client)
            self.assertEqual(stats["saltados"], 1)
            self.assertEqual(stats["ok"], 1)

    def test_sin_subtitulo_se_salta(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text(json.dumps({"id": "a", "titulo": "A", "descripcion": ""}) + "\n")
            fetch = tmp / "fetch.jsonl"
            fetch.write_text(json.dumps({"id": "a", "estado": "sin_subtitulo"}) + "\n")
            out_dir = tmp / "out"
            out_dir.mkdir()

            client = llm_client.LLMClient(simulado=_simulado_clasificacion_valida)
            stats = yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client)
            self.assertEqual(stats["sin_subtitulo"], 1)
            self.assertEqual(stats["ok"], 0)


if __name__ == "__main__":
    unittest.main()
