#!/usr/bin/env python3
"""Tests de la segunda comparativa de backends (T68).

Cubren: (1) reintento ante `content=None` en `llm_client.LLMClient` con
`requests` simulado; (2) la métrica de similitud de tokens (Jaccard sobre
raíces truncadas) y la cobertura bilateral de `comparar_backends.py`.
Sin red.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_client  # noqa: E402
import comparar_backends as cb  # noqa: E402


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


def _resp_content_nulo():
    return FakeResp(payload={
        "choices": [{"message": {"content": None}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })


class ReintentoContenidoVacioTests(unittest.TestCase):
    def test_content_null_reintenta_y_devuelve_segundo(self):
        with patch("llm_client.requests.post") as post:
            post.side_effect = [_resp_content_nulo(), FakeResp()]
            cliente = llm_client.LLMClient(endpoints=["http://a:8000/v1"])
            resp = cliente.chat("sys", "user")
        self.assertEqual(resp, '{"ok": true}')
        self.assertEqual(post.call_count, 2)

    def test_content_null_agota_reintentos_y_lanza(self):
        with patch("llm_client.requests.post") as post, \
                patch("llm_client.time.sleep"):
            post.side_effect = [_resp_content_nulo()] * 4
            cliente = llm_client.LLMClient(endpoints=["http://a:8000/v1"])
            with self.assertRaises(llm_client.ContenidoVacioError):
                cliente.chat("sys", "user", max_reintentos=3)

    def test_reasoning_effort_y_max_completion_envio(self):
        with patch("llm_client.requests.post") as post:
            post.return_value = FakeResp()
            cliente = llm_client.LLMClient(
                endpoints=[("http://nube/v1", "mercury-3")],
                api_key_env="LLM_API_KEY",
                reasoning_effort="instant",
                max_completion_tokens=8192,
                max_tokens_default=4096)
            with patch.dict(os.environ, {"LLM_API_KEY": "k"}):
                cliente.chat("s", "u")
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["reasoning_effort"], "instant")
            self.assertEqual(payload["max_completion_tokens"], 8192)
            self.assertEqual(payload["max_tokens"], 4096)


class SimilitudTests(unittest.TestCase):
    def test_jaccard_conjuntos(self):
        a = {"el", "sol"}
        b = {"el", "sol", "luna"}
        self.assertAlmostEqual(cb._jaccard(a, b), 2 / 3)
        self.assertEqual(cb._jaccard(set(), {"x"}), 0.0)
        self.assertEqual(cb._jaccard(set(), set()), 0.0)

    def test_tokens_raiz_elimina_stopwords_y_acentos(self):
        raices = cb._tokens_raiz(
            "El Sol de la justicia ilumina la noche")
        self.assertNotIn("el", raices)
        self.assertNotIn("de", raices)
        self.assertNotIn("la", raices)
        self.assertIn("ilumin", raices)
        self.assertIn("noche", raices)

    def test_cobertura_porafrasis_mismo_concepto(self):
        local = ["El Sol representa el éxito, la claridad y la voluntad"]
        fast = ["La carta del Sol representa éxito y claridad, e indica "
                "voluntad"]
        # Misma afirmación con redacción distinta: comparten raíces, cobertura
        # mínima esperada >0.
        self.assertGreater(cb._cobertura(local, fast), 0.0)

    def test_cobertura_cero_sin_relacion(self):
        local = ["El Sol representa el éxito"]
        fast = ["La Muerte anuncia un cambio radical"]
        self.assertEqual(cb._cobertura(local, fast), 0.0)

    def test_cobertura_direccional(self):
        local = ["El Sol representa éxito y claridad",
                 "La Luna rige las emociones",
                 "El Mago indica acción y poder"]
        fast = ["el Sol representa éxito y claridad",
                "la Luna rige emociones"]
        self.assertAlmostEqual(cb._cobertura(fast, local), 1.0)
        self.assertAlmostEqual(cb._cobertura(local, fast), 2 / 3)


if __name__ == "__main__":
    unittest.main()
