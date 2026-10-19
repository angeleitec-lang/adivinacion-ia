#!/usr/bin/env python3
"""Tests para yt_pipeline.py (T21.3): orquestador del pipeline YouTube A4."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import llm_client
import yt_pipeline


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
        {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica decision importante en el amor"},
        {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
        {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y exito"},
    ],
    "sintesis": "La lectura muestra evolucion de bloqueo a claridad",
    "consejo": "Confia en tu intuicion",
}

RESPUESTA_NORM = (
    "En esta tirada de tres cartas sobre el amor, Los Enamorados en posición presente "
    "te hablan de una elección importante que tienes delante. La Emperatriz invertida "
    "en el pasado sugiere que has sentido un bloqueo creativo o emocional. El Sol en el "
    "futuro te trae claridad y optimismo. En síntesis, la lectura muestra una evolución "
    "desde el bloqueo hacia la luz. Consejo: confía en tu intuición y toma la decisión "
    "que tu corazón te indica."
)

LINEAS_LECTURA = [
    "hola bienvenidos hoy en esta tirada",
    "la carta los enamorados sale en presente",
    "la carta la emperatriz invertida en pasado y la carta el sol sale en futuro",
    "los enamorados significa decision importante en el amor",
    "la emperatriz invertida representa bloqueo creativo",
    "el sol representa claridad y exito",
    "sintesis la lectura muestra evolucion de bloqueo a claridad",
    "consejo confia en tu intuicion",
]

LINEAS_CURSO = [
    "bienvenidos a este curso de tarot",
    "vamos a aprender el significado de las cartas",
    "la loca representa nuevos comienzos",
    "el mago representa la accion y la voluntad",
]


def _vtt(lineas):
    partes = ["WEBVTT"]
    for i, linea in enumerate(lineas):
        t0 = i * 5
        partes.append(
            f"\n00:00:{t0:02d}.000 --> 00:00:{t0 + 4:02d}.000\n{linea}"
        )
    return "\n".join(partes) + "\n"


def _simulado(sistema, usuario):
    if "Clasifica según el esquema" in usuario:
        if "CURSO" in usuario:
            return json.dumps({
                "tipo": "curso_conocimiento", "familia": "tarot-conocimiento",
                "tirada": "otras", "n_cartas": 1, "calidad": 3, "motivo": "curso",
            }, ensure_ascii=False)
        return json.dumps({
            "tipo": "lectura_individual", "familia": "tarot-lectura",
            "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok",
        }, ensure_ascii=False)
    if "Extrae la lectura según el esquema" in usuario:
        return "```json\n" + json.dumps(LECTURA_BUENA, ensure_ascii=False) + "\n```"
    if "Extrae afirmaciones de conocimiento" in usuario:
        return json.dumps({
            "tipo": "conocimiento", "familia": "tarot-conocimiento",
            "afirmaciones": [
                {"entidad": "La Loca", "faceta": "significado",
                 "texto": "La Loca representa nuevos comienzos"},
            ],
        }, ensure_ascii=False)
    return RESPUESTA_NORM


class _YDLFake:
    def __init__(self, opts, respuestas):
        self.opts = opts
        self.respuestas = respuestas

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        vid = url.rsplit("v=", 1)[1]
        modo = self.respuestas.get(vid, "none")
        if modo == "rate":
            raise Exception("ERROR: HTTP Error 429: Too Many Requests")
        destino = Path(self.opts["outtmpl"]).parent
        if modo == "manual":
            (destino / f"{vid}.es.vtt").write_text(_vtt(LINEAS_LECTURA), encoding="utf-8")
            return {"subtitles": {"es": [{"ext": "vtt"}]}, "automatic_captions": {}}
        if modo == "auto":
            (destino / f"{vid}.es-orig.vtt").write_text(_vtt(LINEAS_CURSO), encoding="utf-8")
            return {"subtitles": {}, "automatic_captions": {"es": [{"ext": "vtt"}]}}
        return {"subtitles": {}, "automatic_captions": {}}


def _clase_ydl(respuestas):
    return lambda opts: _YDLFake(opts, respuestas)


RESPUESTAS_OK = {"vid_lectura": "manual", "vid_curso": "auto", "vid_nosub": "none"}


def _escribir_catalogo(path: Path):
    filas = [
        {"id": "vid_lectura", "titulo": "TIRADA DE TAROT PARA HOY",
         "descripcion": "", "canal": "Tarot con María", "canal_id": "UC_ES1"},
        {"id": "vid_curso", "titulo": "CURSO DE TAROT LAS 3 TIRADAS BASICAS",
         "descripcion": "", "canal": "Escuela de Tarot", "canal_id": "UC_ES2"},
        {"id": "vid_nosub", "titulo": "VIDEO SIN SUBTITULOS",
         "descripcion": "", "canal": "Otro Canal", "canal_id": "UC_ES3"},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n")


def _leer_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class PipelineCompleto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name) / "work"
        self.catalogo = self.work / "catalogo.jsonl"
        _escribir_catalogo(self.catalogo)
        self.addCleanup(self._tmp.cleanup)

    def _ejecutar(self, **kw):
        args = dict(catalogo=str(self.catalogo), pausa=0.0,
                   client=llm_client.LLMClient(simulado=_simulado),
                   clase_ydl=_clase_ydl(RESPUESTAS_OK))
        args.update(kw)
        return yt_pipeline.procesar_pipeline(str(self.work), **args)

    def test_pipeline_llena_todos_los_ficheros(self):
        res = self._ejecutar()
        fetch = _leer_jsonl(self.work / "fetch.jsonl")
        self.assertEqual(len(fetch), 3)
        por_id = {r["id"]: r for r in fetch}
        self.assertEqual(por_id["vid_lectura"]["tipo"], "manual")
        self.assertEqual(por_id["vid_curso"]["tipo"], "auto_original")
        self.assertEqual(por_id["vid_nosub"]["estado"], "sin_subtitulo")

        limpio = self.work / "limpio" / "vid_lectura.txt"
        self.assertTrue(limpio.exists())
        self.assertIn("los enamorados", limpio.read_text(encoding="utf-8"))
        self.assertFalse((self.work / "limpio" / "vid_nosub.txt").exists())

        clasif = _leer_jsonl(self.work / "clasificacion.jsonl")
        self.assertEqual(len(clasif), 2)

        lecturas = _leer_jsonl(self.work / "lecturas_validadas.jsonl")
        self.assertEqual(len(lecturas), 1)
        self.assertEqual(lecturas[0]["video_id"], "vid_lectura")
        self.assertEqual(lecturas[0]["canal"], "Tarot con María")

        conocimiento = _leer_jsonl(self.work / "conocimiento.jsonl")
        self.assertEqual(len(conocimiento), 1)
        self.assertEqual(conocimiento[0]["video_id"], "vid_curso")

        dataset = _leer_jsonl(self.work / "dataset.jsonl")
        self.assertEqual(len(dataset), 1)
        self.assertEqual(dataset[0]["meta"]["video_id"], "vid_lectura")
        self.assertFalse(res.get("rate_limit"))

    def test_reanudar_no_repite(self):
        self._ejecutar()
        antes = {
            "fetch": len(_leer_jsonl(self.work / "fetch.jsonl")),
            "clasif": len(_leer_jsonl(self.work / "clasificacion.jsonl")),
            "lecturas": len(_leer_jsonl(self.work / "lecturas_validadas.jsonl")),
            "conoc": len(_leer_jsonl(self.work / "conocimiento.jsonl")),
            "dataset": len(_leer_jsonl(self.work / "dataset.jsonl")),
        }
        res2 = self._ejecutar()
        despues = {
            "fetch": len(_leer_jsonl(self.work / "fetch.jsonl")),
            "clasif": len(_leer_jsonl(self.work / "clasificacion.jsonl")),
            "lecturas": len(_leer_jsonl(self.work / "lecturas_validadas.jsonl")),
            "conoc": len(_leer_jsonl(self.work / "conocimiento.jsonl")),
            "dataset": len(_leer_jsonl(self.work / "dataset.jsonl")),
        }
        self.assertEqual(antes, despues)
        self.assertEqual(res2["fetch"]["saltados"], 3)
        self.assertEqual(res2["clasificar"]["saltados"], 2)
        self.assertEqual(res2["normalizar"]["saltados"], 1)

    def test_hasta_clean_no_clasifica(self):
        self._ejecutar(hasta="clean")
        self.assertTrue((self.work / "limpio" / "vid_lectura.txt").exists())
        self.assertFalse((self.work / "clasificacion.jsonl").exists())
        self.assertFalse((self.work / "dataset.jsonl").exists())

    def test_rate_limit_para_y_marca(self):
        respuestas = {"vid_lectura": "manual", "vid_curso": "rate", "vid_nosub": "none"}
        res = self._ejecutar(clase_ydl=_clase_ydl(respuestas))
        self.assertTrue(res.get("rate_limit"))
        self.assertFalse((self.work / "dataset.jsonl").exists())

    def test_main_devuelve_3_con_rate_limit(self):
        argv = ["--work-dir", str(self.work), "--catalogo", str(self.catalogo),
               "--pausa", "0", "--simulado"]
        respuestas = {"vid_lectura": "manual", "vid_curso": "rate", "vid_nosub": "none"}
        rc = yt_pipeline.main(argv=argv, clase_ydl=_clase_ydl(respuestas))
        self.assertEqual(rc, 3)

    def test_main_devuelve_0_ok(self):
        argv = ["--work-dir", str(self.work), "--catalogo", str(self.catalogo),
               "--pausa", "0", "--simulado"]
        rc = yt_pipeline.main(argv=argv, clase_ydl=_clase_ydl(RESPUESTAS_OK))
        self.assertEqual(rc, 0)
        self.assertTrue((self.work / "dataset.jsonl").exists())


class TodasLasLecturasDescartadas(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name) / "work"
        self.catalogo = self.work / "catalogo.jsonl"
        _escribir_catalogo(self.catalogo)
        self.addCleanup(self._tmp.cleanup)

    def _simulado_invalido(self, sistema, usuario):
        if "Clasifica según el esquema" in usuario:
            return json.dumps({
                "tipo": "lectura_individual", "familia": "tarot-lectura",
                "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok",
            }, ensure_ascii=False)
        if "Extrae la lectura según el esquema" in usuario:
            return json.dumps({
                "tipo": "lectura", "tirada": "3_cartas",
                "pregunta_o_tema": "amor",
                "cartas": [{"nombre": "Carta Inexistente", "orientacion": "derecha",
                           "posicion": "pasado"}],
                "interpretaciones": [], "sintesis": "", "consejo": "",
            }, ensure_ascii=False)
        return "respuesta irrelevante"

    def test_normalizar_no_revienta_sin_lecturas_validas(self):
        res = yt_pipeline.procesar_pipeline(
            str(self.work), catalogo=str(self.catalogo), pausa=0.0,
            client=llm_client.LLMClient(simulado=self._simulado_invalido),
            clase_ydl=_clase_ydl(RESPUESTAS_OK))
        self.assertFalse((self.work / "lecturas_validadas.jsonl").exists())
        self.assertGreaterEqual(len(_leer_jsonl(self.work / "lecturas_descartadas.jsonl")), 1)
        self.assertEqual(res["normalizar"]["ok"], 0)
        self.assertFalse((self.work / "dataset.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
