"""Tests de translate_dataset: detección, validación y gestión de fallos."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import translate_dataset as td

EN_ANSWER = ("The tower card means that the end of a cycle is coming "
             "soon and you should look inside yourself for answers.")


def _fila(respuesta):
    return {"conversations": [
        {"from": "human", "value": "Explica en detalle: La Torre."},
        {"from": "gpt", "value": respuesta},
    ]}


class DetectLanguage(unittest.TestCase):
    def test_listas_sin_solapamiento(self):
        self.assertEqual(set(td.ES_WORDS) & set(td.EN_WORDS), set())

    def test_no_espanol_no_es_ingles(self):
        texto = "No es lo que parece. No sabes que no puedes. No."
        self.assertEqual(td.detect_language(texto), "es")

    def test_no_acumulado_sigue_espanol(self):
        texto = "Esto no es ni sí ni no, no, no, no y no."
        self.assertEqual(td.detect_language(texto), "es")

    def test_ingles_autentico(self):
        texto = ("The card means that you have to look at what is "
                 "in front of you.")
        self.assertEqual(td.detect_language(texto), "en")

    def test_vacio_unknown(self):
        self.assertEqual(td.detect_language(""), "unknown")


class ValidarTraduccion(unittest.TestCase):
    def test_vacio(self):
        texto, motivo = td.validar_traduccion("Some english source text.", "   ", "stop")
        self.assertIsNone(texto)
        self.assertIn("vacío", motivo)

    def test_bloque_think_se_quita(self):
        original = "The moon is beautiful tonight."
        traducida = "<think>voy a pensar</think>La luna es hermosa esta noche."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "La luna es hermosa esta noche.")

    def test_truncada_se_rechaza(self):
        original = "The moon is beautiful tonight."
        texto, motivo = td.validar_traduccion(original, "La luna es hermosa", "length")
        self.assertIsNone(texto)
        self.assertIn("truncada", motivo)

    def test_sigue_en_ingles(self):
        original = "The card means change and transformation ahead."
        texto, motivo = td.validar_traduccion(
            original, "The card is the tower of change.", "stop")
        self.assertIsNone(texto)
        self.assertIn("inglés", motivo)

    def test_ratio_fuera_de_rango(self):
        original = "word " * 400
        texto, motivo = td.validar_traduccion(original, "Poco texto.", "stop")
        self.assertIsNone(texto)
        self.assertIn("ratio", motivo)

    def test_prefijo_traduccion_recortado(self):
        original = "Good morning, friend."
        traducida = "Aquí está la traducción:\n\nBuenos días, amigo."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "Buenos días, amigo.")

    def test_prefijo_corto_recortado(self):
        original = "Good morning, friend."
        traducida = "Traducción: Buenos días, amigo."
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, "Buenos días, amigo.")

    def test_caso_bueno(self):
        original = "The card means that you have to look at what is in front of you."
        traducida = ("La carta significa que tienes que mirar lo que "
                    "tienes delante.")
        texto, motivo = td.validar_traduccion(original, traducida, "stop")
        self.assertIsNone(motivo)
        self.assertEqual(texto, traducida)


class FallosYReintento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.src = root / "train.jsonl"
        self.dst = root / "train_es.jsonl"
        self.failed = Path(str(self.dst) + ".failed.jsonl")
        self.progress = Path(str(self.dst) + ".progress")

    def _argv(self, *extra):
        return ["--train", str(self.src), "--out-train", str(self.dst),
                "--only", "train", "--workers", "1", *extra]

    def test_fallo_no_escribe_destino_y_registra(self):
        self.src.write_text(json.dumps(_fila(EN_ANSWER)) + "\n", encoding="utf-8")
        with mock.patch.object(td, "_translate",
                             side_effect=RuntimeError("simulado")):
            rc = td.main(self._argv())
        self.assertEqual(rc, 0)
        self.assertEqual(self.dst.read_text(encoding="utf-8"), "")
        self.assertTrue(self.failed.exists())
        entry = json.loads(self.failed.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["idx"], 0)
        self.assertIn("simulado", entry["motivo"])
        self.assertEqual(entry["row"], _fila(EN_ANSWER))
        self.assertEqual(self.progress.read_text(encoding="utf-8"), "1")

    def test_retry_failed_recupera(self):
        self.src.write_text(json.dumps(_fila(EN_ANSWER)) + "\n", encoding="utf-8")
        with mock.patch.object(td, "_translate",
                             side_effect=RuntimeError("simulado")):
            td.main(self._argv())
        self.assertEqual(self.dst.read_text(encoding="utf-8"), "")
        trad = ("La carta de la torre significa que el final de un ciclo "
               "llega pronto y debes mirar dentro de ti.")
        with mock.patch.object(td, "_translate", return_value=trad):
            td.main(self._argv("--retry-failed"))
        lineas = [ln for ln in self.dst.read_text(encoding="utf-8").splitlines()
                 if ln.strip()]
        self.assertEqual(len(lineas), 1)
        self.assertEqual(
            json.loads(lineas[0])["conversations"][-1]["value"], trad)
        restante = (self.failed.read_text(encoding="utf-8")
                    if self.failed.exists() else "")
        self.assertEqual(restante, "")

    def test_retry_failed_sin_fallos_previos(self):
        self.src.write_text(json.dumps(_fila(EN_ANSWER)) + "\n", encoding="utf-8")
        rc = td.main(self._argv("--retry-failed"))
        self.assertEqual(rc, 0)


class ExtraerTema(unittest.TestCase):
    def test_cuatro_plantillas(self):
        casos = [
            ("Explica en detalle: la luna llena.",
             "Explica en detalle: ", "la luna llena", "."),
            ("¿Qué significa el tres?",
             "¿Qué significa ", "el tres", "?"),
            ("Como experta en adivinación, desarróllame los sueños.",
             "Como experta en adivinación, desarróllame ", "los sueños", "."),
            ("Explícame el tarot de forma clara y completa.",
             "Explícame ", "el tarot", " de forma clara y completa."),
        ]
        for prompt, pref, tema, suf in casos:
            self.assertEqual(td.extraer_tema(prompt), (pref, tema, suf))

    def test_prompt_desconocido(self):
        self.assertIsNone(td.extraer_tema("Háblame de lo que quieras."))


class TraducirPrompts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.src = root / "train.jsonl"
        self.dst = root / "train_es.jsonl"

    def _argv(self, *extra):
        return ["--train", str(self.src), "--out-train", str(self.dst),
                "--only", "train", "--workers", "1", *extra]

    def test_recompone_prompt_con_tema_ingles(self):
        fila = {"conversations": [
            {"from": "human",
             "value": "Explica en detalle: The Lily Meaning and Combinations."},
            {"from": "gpt", "value": EN_ANSWER},
        ]}
        self.src.write_text(json.dumps(fila) + "\n", encoding="utf-8")
        trad_tema = "El significado y las combinaciones del Lilio"
        trad_resp = ("La carta de la torre significa que el final de un ciclo "
                    "llega pronto y debes mirar dentro de ti mismo ahora.")

        def fake(t, *a, **k):
            if "Lily" in t:
                return trad_tema
            return trad_resp

        with mock.patch.object(td, "_translate", side_effect=fake):
            td.main(self._argv("--translate-prompts"))
        fila_out = json.loads(
            self.dst.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(
            fila_out["conversations"][0]["value"],
            "Explica en detalle: " + trad_tema + ".")
        self.assertEqual(fila_out["conversations"][1]["value"], trad_resp)

    def test_tema_espanol_no_se_traduce(self):
        fila = {"conversations": [
            {"from": "human", "value": "¿Qué significa la luna?"},
            {"from": "gpt", "value": EN_ANSWER},
        ]}
        self.src.write_text(json.dumps(fila) + "\n", encoding="utf-8")
        trad_resp = ("La carta de la torre significa que el final de un ciclo "
                    "llega pronto y debes mirar dentro de ti mismo ahora.")
        with mock.patch.object(td, "_translate",
                             return_value=trad_resp) as m:
            td.main(self._argv("--translate-prompts"))
        self.assertEqual(m.call_count, 1)
        fila_out = json.loads(
            self.dst.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(fila_out["conversations"][0]["value"],
                        "¿Qué significa la luna?")

    def test_sin_flag_no_toca_el_prompt(self):
        fila = {"conversations": [
            {"from": "human",
             "value": "Explica en detalle: The Lily Meaning and Combinations."},
            {"from": "gpt", "value": EN_ANSWER},
        ]}
        self.src.write_text(json.dumps(fila) + "\n", encoding="utf-8")
        trad_resp = ("La carta de la torre significa que el final de un ciclo "
                    "llega pronto y debes mirar dentro de ti mismo ahora.")
        with mock.patch.object(td, "_translate",
                             return_value=trad_resp) as m:
            td.main(self._argv())
        self.assertEqual(m.call_count, 1)
        fila_out = json.loads(
            self.dst.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(fila_out["conversations"][0]["value"],
                        "Explica en detalle: The Lily Meaning and Combinations.")


if __name__ == "__main__":
    unittest.main()
