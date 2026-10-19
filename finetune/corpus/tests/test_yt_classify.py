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


_VTT_MANUAL = (
    "WEBVTT\n\n"
    "00:00:01.000 --> 00:00:05.000\n"
    "ahora vamos a cortar la baraja del consultante\n\n"
    "00:00:06.000 --> 00:00:10.000\n"
    "y desplegaremos la cruz celta sobre la mesa\n"
)

_VTT_AUTO = (
    "WEBVTT\nKind: captions\nLanguage: es\n\n"
    "00:00:01.000 --> 00:00:05.000\n"
    "transcrito automatico original del video\n"
)


def _simulado_que_captura(capturas):
    def sim(sistema, usuario):
        capturas.append((sistema, usuario))
        return _simulado_clasificacion_valida(sistema, usuario)
    return sim


def _escribir_vtt(vtt_dir: Path, canal_id: str, video_id: str, nombre: str, contenido: str):
    d = vtt_dir / canal_id
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{video_id}.{nombre}.vtt").write_text(contenido, encoding="utf-8")


class TranscriptVtt(unittest.TestCase):
    def _setup(self, tmp: Path):
        catalogo = tmp / "catalogo.jsonl"
        catalogo.write_text(json.dumps({"id": "v1", "titulo": "TITULO UNICO", "descripcion": "desc"}) + "\n")
        fetch = tmp / "fetch.jsonl"
        fetch.write_text(json.dumps({"id": "v1", "estado": "ok", "tipo": "manual"}) + "\n")
        return catalogo, fetch

    def _ultima_clasificacion(self, out_dir: Path):
        lineas = (out_dir / "clasificacion.jsonl").read_text(encoding="utf-8").strip().splitlines()
        return json.loads(lineas[-1])

    def test_vtt_manual_se_envia_al_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            vtt_dir = tmp / "raw_vtt"
            _escribir_vtt(vtt_dir, "UC111", "v1", "es", _VTT_MANUAL)
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            stats = yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client, vtt_dir=vtt_dir)
            self.assertEqual(stats["ok"], 1)
            self.assertIn("cortar la baraja del consultante", capturas[0][1])
            self.assertNotIn("TITULO UNICO", capturas[0][1].split("MUESTRA DE TEXTO")[1])
            reg = self._ultima_clasificacion(out_dir)
            self.assertEqual(reg["texto_fuente"], "transcript")

    def test_es_orig_cuando_no_hay_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            vtt_dir = tmp / "raw_vtt"
            _escribir_vtt(vtt_dir, "UC111", "v1", "es-orig", _VTT_AUTO)
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client, vtt_dir=vtt_dir)
            self.assertIn("transcrito automatico original", capturas[0][1])
            self.assertEqual(self._ultima_clasificacion(out_dir)["texto_fuente"], "transcript")

    def test_manual_prioritario_sobre_es_orig(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            vtt_dir = tmp / "raw_vtt"
            _escribir_vtt(vtt_dir, "UC111", "v1", "es-orig", _VTT_AUTO)
            _escribir_vtt(vtt_dir, "UC111", "v1", "es", _VTT_MANUAL)
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client, vtt_dir=vtt_dir)
            self.assertIn("cortar la baraja", capturas[0][1])
            self.assertNotIn("transcrito automatico", capturas[0][1])

    def test_sin_vtt_cae_a_titulo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client,
                                              vtt_dir=tmp / "no_existe")
            self.assertIn("TITULO UNICO", capturas[0][1])
            self.assertEqual(self._ultima_clasificacion(out_dir)["texto_fuente"], "titulo")

    def test_vtt_vacio_cae_a_titulo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            vtt_dir = tmp / "raw_vtt"
            _escribir_vtt(vtt_dir, "UC111", "v1", "es", "WEBVTT\n\n")
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client, vtt_dir=vtt_dir)
            self.assertIn("TITULO UNICO", capturas[0][1])
            self.assertEqual(self._ultima_clasificacion(out_dir)["texto_fuente"], "titulo")

    def test_vtt_dir_por_defecto_bajo_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            _escribir_vtt(fetch.parent / "raw_vtt", "UC111", "v1", "es", _VTT_MANUAL)
            out_dir = tmp / "out"
            capturas = []
            client = llm_client.LLMClient(simulado=_simulado_que_captura(capturas))
            yt_classify.procesar_clasificacion(catalogo, fetch, out_dir, client)
            self.assertIn("cortar la baraja del consultante", capturas[0][1])
            self.assertEqual(self._ultima_clasificacion(out_dir)["texto_fuente"], "transcript")

    def test_cli_acepta_vtt_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo, fetch = self._setup(tmp)
            vtt_dir = tmp / "vtt_custom"
            _escribir_vtt(vtt_dir, "UC111", "v1", "es", _VTT_MANUAL)
            out_dir = tmp / "out"
            argv = ["yt_classify", "--catalogo", str(catalogo), "--fetch", str(fetch),
                   "--out-dir", str(out_dir), "--vtt-dir", str(vtt_dir), "--simulado"]
            viejo = sys.argv
            sys.argv = argv
            try:
                rc = yt_classify.main()
            finally:
                sys.argv = viejo
            self.assertEqual(rc, 0)
            reg = self._ultima_clasificacion(out_dir)
            self.assertEqual(reg["texto_fuente"], "transcript")


if __name__ == "__main__":
    unittest.main()
