#!/usr/bin/env python3
"""Tests para llm_client.py (A4.4)."""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_client
import unittest


class LLMClientTests(unittest.TestCase):
    def test_chat_con_simulado(self):
        def simulado(sistema, usuario):
            return "respuesta simulada"

        client = llm_client.LLMClient(simulado=simulado)
        resp = client.chat("sys", "user")
        self.assertEqual(resp, "respuesta simulada")

    def test_chat_json_exito_primer_intento(self):
        def simulado(sistema, usuario):
            return '```json\n{"clave": "valor"}\n```'

        client = llm_client.LLMClient(simulado=simulado)
        data = client.chat_json("sys", "user", lambda d: None)
        self.assertEqual(data, {"clave": "valor"})

    def test_chat_json_sin_bloque_markdown(self):
        def simulado(sistema, usuario):
            return '{"clave": "valor"}'

        client = llm_client.LLMClient(simulado=simulado)
        data = client.chat_json("sys", "user", lambda d: None)
        self.assertEqual(data, {"clave": "valor"})

    def test_chat_json_extrae_primer_objeto(self):
        def simulado(sistema, usuario):
            return 'texto antes {"a": 1} texto después {"b": 2}'

        client = llm_client.LLMClient(simulado=simulado)
        data = client.chat_json("sys", "user", lambda d: None)
        self.assertEqual(data, {"a": 1})

    def test_chat_json_reintento_con_error_en_prompt(self):
        intentos = [0]

        def simulado(sistema, usuario):
            intentos[0] += 1
            if intentos[0] == 1:
                return '```json\n{"calidad": 10}\n```'  # inválido
            return '```json\n{"calidad": 4}\n```'

        def validar(d):
            if not (1 <= d.get("calidad", 0) <= 5):
                raise ValueError("calidad fuera de rango")

        client = llm_client.LLMClient(simulado=simulado)
        data = client.chat_json("sys", "user", validar, intentos=3)
        self.assertEqual(data, {"calidad": 4})
        self.assertEqual(intentos[0], 2)

    def test_chat_json_falla_tras_intentos(self):
        def simulado(sistema, usuario):
            return 'no hay json aqui'

        client = llm_client.LLMClient(simulado=simulado)
        with self.assertRaises(ValueError):
            client.chat_json("sys", "user", lambda d: None, intentos=2)

    def test_round_robin_endpoints(self):
        endpoints = ["http://a:8000/v1", "http://b:8000/v1", "http://c:8000/v1"]
        client = llm_client.LLMClient(endpoints=endpoints, simulado=lambda s, u: "ok")
        # Verificar que el índice rota
        self.assertEqual(client._siguiente_endpoint(), endpoints[0])
        self.assertEqual(client._siguiente_endpoint(), endpoints[1])
        self.assertEqual(client._siguiente_endpoint(), endpoints[2])
        self.assertEqual(client._siguiente_endpoint(), endpoints[0])


if __name__ == "__main__":
    unittest.main()
