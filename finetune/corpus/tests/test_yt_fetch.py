#!/usr/bin/env python3
"""Tests para yt_fetch.py (A4.3).

El simulador reproduce el comportamiento real de yt-dlp 2026.08.19:
- solo escribe ficheros de subtítulos cuando extract_info recibe
  download=True (con download=False la carpeta queda vacía);
- nombra los ficheros a partir del outtmpl que recibe, insertando el
  código de idioma del subtítulo antes de la extensión;
- distingue manuales (info["subtitles"]) de automáticos
  (info["automatic_captions"]).
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_fetch


WEBVTT = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhola\n"


def _ruta_vtt(outtmpl: str, video_id: str, idioma: str) -> Path:
    """Nombre del fichero de subtítulo que generaría yt-dlp con este outtmpl.

    Sustituye %(id)s, %(language)s y %(ext)s y a continuación inserta el
    código de idioma del subtítulo antes de la extensión final.
    """
    base = (outtmpl.replace("%(id)s", video_id)
                    .replace("%(language)s", "es-US")
                    .replace("%(ext)s", "vtt"))
    if base.endswith(".vtt"):
        base = base[: -len(".vtt")] + "." + idioma + ".vtt"
    else:
        base = base + "." + idioma + ".vtt"
    return Path(base)


def _simulador(videos):
    """Fábrica de clase_ydl que simula a yt-dlp real.

    videos: {id: {"manuales": [idioma...], "autos": [idioma...],
                 "error": texto}}.
    Expone .estado con: escritos (id -> lista de Path escritos, solo si
    download=True) y llamadas (valor de download en cada extract_info).
    """
    estado = {"escritos": {}, "llamadas": []}

    class YDLSimulado:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            vid = url.split("v=")[-1] if "v=" in url else url
            estado["llamadas"].append(bool(download))
            cfg = videos.get(vid, {})
            if cfg.get("error"):
                raise Exception(cfg["error"])
            info = {
                "id": vid,
                "subtitles": {l: [{}] for l in cfg.get("manuales", [])},
                "automatic_captions": {l: [{}] for l in cfg.get("autos", [])},
            }
            if download:
                langs = sorted(set(cfg.get("manuales", [])) | set(cfg.get("autos", [])))
                escritos = []
                for lang in langs:
                    ruta = _ruta_vtt(self.opts["outtmpl"], vid, lang)
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    ruta.write_text(WEBVTT, encoding="utf-8")
                    escritos.append(ruta)
                estado["escritos"][vid] = escritos
            return info

    class Fabrica:
        def __init__(self, estado):
            self.estado = estado

        def __call__(self, opts):
            return YDLSimulado(opts)

    return Fabrica(estado)


class DescargarSubtitulos(unittest.TestCase):
    def test_solo_auto_original_ok(self):
        # (a) original automático es-orig -> ok / auto_original
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador({"vid1": {"autos": ["es-orig"]}})
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=fabrica, reintentos=0
            )
            self.assertEqual(res["estado"], "ok")
            self.assertEqual(res["tipo"], "auto_original")
            ruta = Path(tmp) / "raw_vtt" / "UC_test" / "vid1.es-orig.vtt"
            self.assertTrue(ruta.exists())
            self.assertEqual(res["bytes"], ruta.stat().st_size)

    def test_manual_es_ok(self):
        # (b) es manual en info["subtitles"] -> ok / manual
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador({"vid1": {"manuales": ["es"], "autos": ["es", "es-orig"]}})
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=fabrica, reintentos=0
            )
            self.assertEqual(res["estado"], "ok")
            self.assertEqual(res["tipo"], "manual")
            ruta = Path(tmp) / "raw_vtt" / "UC_test" / "vid1.es.vtt"
            self.assertTrue(ruta.exists())

    def test_es_automatico_traducido_se_descarta(self):
        # (c) es solo automático (no en subtitles) y sin es-orig -> sin_subtitulo
        # y el .es.vtt traducido se borra
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador({"vid1": {"autos": ["es"]}})
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=fabrica, reintentos=0
            )
            self.assertEqual(res["estado"], "sin_subtitulo")
            self.assertIsNone(res["tipo"])
            ruta = Path(tmp) / "raw_vtt" / "UC_test" / "vid1.es.vtt"
            escribidos = fabrica.estado["escritos"].get("vid1", [])
            self.assertTrue(any(p.name == "vid1.es.vtt" for p in escribidos),
                            "el simulador debía haber escrito el .es.vtt traducido")
            self.assertFalse(ruta.exists(), "el .es.vtt traducido debe borrarse")

    def test_sin_subtitulos(self):
        # (d) ni manuales ni autos -> sin_subtitulo
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador({"vid1": {}})
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=fabrica, reintentos=0
            )
            self.assertEqual(res["estado"], "sin_subtitulo")
            self.assertEqual(res["bytes"], 0)

    def test_rate_limit_429(self):
        # (e) 429 -> parada limpia (error=rate_limit, sin reintentos)
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador(
                {"vid1": {"error": "ERROR: HTTP Error 429: Too Many Requests"}}
            )
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test", clase_ydl=fabrica, reintentos=3
            )
            self.assertEqual(res["estado"], "error")
            self.assertEqual(res.get("error"), "rate_limit")
            self.assertEqual(len(fabrica.estado["llamadas"]), 1)

    def test_error_generico_reintenta(self):
        with tempfile.TemporaryDirectory() as tmp:
            fabrica = _simulador({"vid1": {"error": "Error persistente"}})
            res = yt_fetch.descargar_subtitulos(
                "vid1", Path(tmp), "UC_test",
                clase_ydl=fabrica, reintentos=2, pausa=0.01
            )
            self.assertEqual(res["estado"], "error")
            self.assertEqual(res.get("error") != "rate_limit", True)
            self.assertEqual(len(fabrica.estado["llamadas"]), 3)


class ProcesarCatalogo(unittest.TestCase):
    def _catalogo(self, tmp, ids):
        catalogo = tmp / "catalogo.jsonl"
        catalogo.write_text(
            "".join(json.dumps({"id": i, "canal_id": "UC1"}) + "\n" for i in ids),
            encoding="utf-8",
        )
        return catalogo

    def test_reanudable_salta_procesados(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = self._catalogo(tmp, ["a", "b"])
            fetch = tmp / "fetch.jsonl"
            fetch.write_text(json.dumps({"id": "a", "estado": "ok", "tipo": "manual"}) + "\n")
            fabrica = _simulador({"a": {"manuales": ["es"]}, "b": {"manuales": ["es"]}})
            stats = yt_fetch.procesar_catalogo(
                catalogo, tmp, clase_ydl=fabrica, pausa=0
            )
            self.assertEqual(stats["saltados"], 1)
            self.assertEqual(stats["ok"], 1)

    def test_limite_procesa_solo_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = self._catalogo(tmp, [f"v{i}" for i in range(5)])
            fabrica = _simulador({f"v{i}": {"manuales": ["es"]} for i in range(5)})
            stats = yt_fetch.procesar_catalogo(
                catalogo, tmp, clase_ydl=fabrica, pausa=0, limite=2
            )
            self.assertEqual(stats["ok"], 2)

    def test_fetch_jsonl_registra_id_estado_tipo_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = self._catalogo(tmp, ["vid1"])
            fabrica = _simulador({"vid1": {"autos": ["es-orig"]}})
            yt_fetch.procesar_catalogo(catalogo, tmp, clase_ydl=fabrica, pausa=0)
            regs = [json.loads(l) for l in (tmp / "fetch.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(regs), 1)
            self.assertEqual(set(regs[0]), {"id", "estado", "tipo", "bytes"})
            self.assertEqual(regs[0]["estado"], "ok")
            self.assertEqual(regs[0]["tipo"], "auto_original")
            self.assertGreater(regs[0]["bytes"], 0)

    def test_rate_limit_para_el_lote(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = self._catalogo(tmp, ["a", "b", "c"])
            fabrica = _simulador({
                "a": {"manuales": ["es"]},
                "b": {"error": "HTTP Error 429: Too Many Requests"},
                "c": {"manuales": ["es"]},
            })
            stats = yt_fetch.procesar_catalogo(
                catalogo, tmp, clase_ydl=fabrica, pausa=0, reintentos=0
            )
            self.assertEqual(stats["ok"], 1)
            self.assertEqual(stats["error"], 1)
            lineas = (tmp / "fetch.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lineas), 2)
            self.assertEqual(json.loads(lineas[1]).get("error"), "rate_limit")


if __name__ == "__main__":
    unittest.main()
