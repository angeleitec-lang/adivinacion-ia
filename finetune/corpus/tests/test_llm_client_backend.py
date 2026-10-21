#!/usr/bin/env python3
"""Tests del backend en la nube de llm_client.py (T65).

Cubren: cabecera Authorization Bearer desde variable de entorno, error claro
si la clave falta (sin filtrar nada), reintento con backoff ante 429 y
round-robin mixto con modelo propio por endpoint. Todo con `requests`
simulado (sin red).
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_client


class FakeResp:
    """Respuesta `requests` simulada."""

    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError("HTTP %d" % self.status_code)


class LLMClientBackendTests(unittest.TestCase):
    def test_cabecera_bearer_presente(self):
        with patch.dict(os.environ, {"INCEPTION_API_KEY": "clave-secreta"}):
            client = llm_client.LLMClient(endpoints=[{
                "url": "http://nube/v1",
                "model": "mercury-3",
                "api_key_env": "INCEPTION_API_KEY",
            }])
            with patch("llm_client.requests.post") as post:
                post.return_value = FakeResp()
                client.chat("sys", "user")
            args, kwargs = post.call_args
            self.assertEqual(args[0], "http://nube/v1/chat/completions")
            cabeceras = kwargs.get("headers", {})
            self.assertEqual(cabeceras["Authorization"], "Bearer clave-secreta")
            # La clave no debe filtrarse en el payload ni en la URL
            self.assertNotIn("clave-secreta", str(kwargs.get("json")))
            self.assertNotIn("clave-secreta", args[0])

    def test_clave_ausente_error_claro_sin_filtrar(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INCEPTION_API_KEY", None)
            client = llm_client.LLMClient(endpoints=[{
                "url": "http://nube/v1",
                "model": "mercury-3",
                "api_key_env": "INCEPTION_API_KEY",
            }])
            with patch("llm_client.requests.post") as post:
                with self.assertRaises(RuntimeError) as ctx:
                    client.chat("sys", "user")
            # No debe haberse hecho ninguna petición de red
            post.assert_not_called()
            msg = str(ctx.exception)
            self.assertIn("INCEPTION_API_KEY", msg)
            self.assertNotIn("clave-secreta", msg)

    def test_429_reintenta_con_backoff(self):
        with patch("llm_client.time.sleep") as sleep, \
                patch("llm_client.requests.post") as post:
            post.side_effect = [
                FakeResp(status=429, headers={"Retry-After": "0.01"}),
                FakeResp(),
            ]
            client = llm_client.LLMClient(endpoints=["http://a:8000/v1"])
            resp = client.chat("sys", "user")
            self.assertEqual(post.call_count, 2)
            self.assertEqual(resp, '{"ok": true}')
            # El backoff debe usar Retry-After (0.01 s)
            self.assertGreaterEqual(len(sleep.call_args_list), 1)
            self.assertAlmostEqual(sleep.call_args_list[0][0][0], 0.01,
                                   places=2)

    def test_429_se_agota_y_lanza(self):
        with patch("llm_client.requests.post") as post:
            post.side_effect = [
                FakeResp(status=429, headers={"Retry-After": "0.01"}),
                FakeResp(status=429, headers={"Retry-After": "0.01"}),
                FakeResp(status=429, headers={"Retry-After": "0.01"}),
                FakeResp(status=429, headers={"Retry-After": "0.01"}),
            ]
            client = llm_client.LLMClient(endpoints=["http://a:8000/v1"])
            with self.assertRaises(llm_client.RateLimitError):
                client.chat("sys", "user", max_reintentos=3)

    def test_round_robin_mixto(self):
        endpoints = [
            "http://local1:8000/v1",
            ("http://nube/v1", "mercury-3"),
            {"url": "http://local2:8000/v1",
             "model": "halogen-qwen3.8-flash-next"},
        ]
        client = llm_client.LLMClient(endpoints=endpoints,
                                       api_key_env="LLM_API_KEY")
        self.assertEqual(client._siguiente_endpoint(), endpoints[0])
        self.assertEqual(client._siguiente_endpoint(), endpoints[1])
        self.assertEqual(client._siguiente_endpoint(), endpoints[2])
        self.assertEqual(client._siguiente_endpoint(), endpoints[0])

    def test_modelo_por_endpoint(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}):
            client = llm_client.LLMClient(
                endpoints=[("http://nube/v1", "mercury-3"),
                           ("http://other/v1", "otro-modelo")],
                api_key_env="LLM_API_KEY")
            with patch("llm_client.requests.post") as post:
                post.return_value = FakeResp()
                client.chat("s", "u")
                client.chat("s", "u")
            modelos = [c.kwargs["json"]["model"] for c in post.call_args_list]
            self.assertEqual(modelos, ["mercury-3", "otro-modelo"])

    def test_endpoint_local_sin_autorizacion(self):
        # Sin variable de entorno ni api_key_env, no se manda cabecera auth
        client = llm_client.LLMClient(endpoints=["http://local:8000/v1"])
        with patch("llm_client.requests.post") as post:
            post.return_value = FakeResp()
            client.chat("s", "u")
        _, kwargs = post.call_args
        self.assertNotIn("Authorization", kwargs.get("headers", {}))


if __name__ == "__main__":
    unittest.main()
