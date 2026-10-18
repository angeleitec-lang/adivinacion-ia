#!/usr/bin/env python3
"""Tests para yt_fetch.py (A4.3)."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_fetch
import unittest


def _doble_fetch(respuestas):
    """Factory para inyectar como clase_ydl en tests de fetch."""
    class YDLFalso:
        def __init__(self, opts, respuestas):
            self.opts = opts
            self.respuestas = respuestas
            self.descargados = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            vid = url.split("v=")[-1] if "v=" in url else url
            # Simular escritura de archivo VTT si hay respuesta
            if vid in self.respuestas:
                resp = self.respuestas[vid]
                if resp.get("tipo") == "manual":
                    path = self.opts["outtmpl"] % {"language": "es", "ext": "vtt"}
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text(resp.get("vtt", "WEBVTT\n00:00:01.000 --> 00:00:02.000\nhola"))
                elif resp.get("tipo") == "auto":
                    path = self.opts["outtmpl"] % {"language": "es-orig", "ext": "vtt"}
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text(resp.get("vtt", "WEBVTT\n00:00:01.000 --> 00:00:02.000\nhola"))
            return {"id": vid}

    from pathlib import Path
    return lambda opts=None: YDLFalso(opts, respuestas)


class DescargarSubtitulos(unittest.TestCase):
    def test_manual_prioritario_sobre_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            respuestas = {
                "vid1": {"tipo": "manual", "vtt": "WEBVTT\n00:00:01.000 --> 00:00:02.000\nmanual"},
            }
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=_doble_fetch(respuestas)
            )
            self.assertEqual(res["estado"], "ok")
            self.assertEqual(res["tipo"], "manual")

    def test_auto_original_si_no_hay_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            respuestas = {
                "vid1": {"tipo": "auto", "vtt": "WEBVTT\n00:00:01.000 --> 00:00:02.000\nauto"},
            }
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=_doble_fetch(respuestas)
            )
            self.assertEqual(res["estado"], "ok")
            self.assertEqual(res["tipo"], "auto_original")

    def test_sin_subtitulo(self):
        with tempfile.TemporaryDirectory() as tmp:
            respuestas = {}
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=_doble_fetch(respuestas)
            )
            self.assertEqual(res["estado"], "sin_subtitulo")

    def test_reintento_y_fallo(self):
        # Simular fallo persistente
        class YDLFallo:
            def __init__(self, opts):
                self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def extract_info(self, url, download=False):
                raise Exception("Error persistente")

        with tempfile.TemporaryDirectory() as tmp:
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test",
                clase_ydl=lambda opts: YDLFallo(opts),
                reintentos=2, pausa=0.01
            )
            self.assertEqual(res["estado"], "error")

    def test_rate_limit_parada_limpia(self):
        class YDLRatio:
            def __init__(self, opts): self.opts = opts
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def extract_info(self, url, download=False):
                raise Exception("429 Too Many Requests")

        with tempfile.TemporaryDirectory() as tmp:
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test",
                clase_ydl=lambda opts: YDLRatio(opts),
                reintentos=0
            )
            self.assertEqual(res["estado"], "error")
            self.assertEqual(res.get("error"), "rate_limit")


class ProcesarCatalogo(unittest.TestCase):
    def test_reanudable_salta_procesados(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text(json.dumps({"id": "a", "canal_id": "UC1"}) + "\n"
                               + json.dumps({"id": "b", "canal_id": "UC2"}) + "\n")
            fetch = tmp / "fetch.jsonl"
            fetch.write_text(json.dumps({"id": "a", "estado": "ok", "tipo": "manual"}) + "\n")

            respuestas = {
                "a": {"tipo": "manual"},
                "b": {"tipo": "manual"},
            }

            stats = yt_fetch.procesar_catalogo(
                catalogo, tmp, clase_ydl=_doble_fetch(respuestas), pausa=0
            )
            self.assertEqual(stats["saltados"], 1)
            self.assertEqual(stats["ok"], 1)

    def test_limite_procesa_solo_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text("\n".join(json.dumps({"id": f"v{i}", "canal_id": "UC1"})
                                        for i in range(5)))

            respuestas = {f"v{i}": {"tipo": "manual"} for i in range(5)}

            stats = yt_fetch.procesar_catalogo(
                catalogo, tmp, clase_ydl=_doble_fetch(respuestas),
                pausa=0, limite=2
            )
            self.assertEqual(stats["ok"], 2)


if __name__ == "__main__":
    unittest.main()
