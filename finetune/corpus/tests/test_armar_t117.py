"""Tests de T117: múltiples fuentes y cierre de residuos v1b.

Cubren: (1) el snapshot de Tuberia fusiona varias fuentes y mantiene la huella
de todas; (2) el split agrupado junta dos filas con prompt humano idéntico
aunque sus claves de situación difieran (residuo a); (3) la puerta de calidad
detecta «asistente de IA» en mayúscula (residuo b); (4) el contador de
preguntas basura no elimina nada y cuenta en fuera_alcance (residuo c).
"""
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import armar_dataset_v1 as ad
import merge_final as mf
import qa_dataset as qa


def _conv(humano, respuesta, system="Eres un lector experto."):
    return [{"from": "system", "value": system},
            {"from": "human", "value": humano},
            {"from": "gpt", "value": respuesta}]


def fila(humano, respuesta, bloque="tarot_1", id_=None):
    return {"conversations": _conv(humano, respuesta),
            "id": id_ or f"{bloque}-x", "bloque": bloque,
            "generador": "mercury-3"}


RESP_OK = ("La carta mostrada habla de un ciclo que se cierra con prudencia; "
           "convien\u00e9 observar los silencios del consultante antes de "
           "actuar, porque la prisa nubla el juicio y la duda se disipa "
           "cuando el mapa interior est\u00e1 claro.")


class TestMultiFuente(unittest.TestCase):
    def test_snapshot_fusiona_varias_fuentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            f1 = tp / "f1.jsonl"
            f2 = tp / "f2.jsonl"
            mf.write_jsonl(f1, [fila("a", RESP_OK, "tarot_1", "x1")])
            mf.write_jsonl(f2, [fila("b", RESP_OK, "tarot_2", "x2")])
            tub = ad.Tuberia(salida_dir=tp / "out", fuentes=[f1, f2])
            report = tub.etapa_snapshot()
            self.assertEqual(len(tub.fuentes), 2)
            self.assertEqual(report["filas"], 2)
            self.assertEqual(sum(report["por_fuente"].values()), 2)
            snap = tub._p("00_snapshot", "aceptadas.jsonl")
            self.assertTrue(snap.exists())
            filas = mf.load_jsonl(snap)
            self.assertEqual(len(filas), 2)
            self.assertEqual({f["id"] for f in filas}, {"x1", "x2"})

    def test_main_resuelve_fuentes(self):
        # --fuente repetible debe llegar al constructor (sin ejecutar cadena)
        import armar_dataset_v1 as ad_mod
        captured = {}

        class StubTuberia:
            def __init__(self, **kw):
                captured.update(kw)
                self.salida = Path(kw["salida_dir"]) / "out"
            def ejecutar(self):
                return 0

        original = ad_mod.Tuberia
        ad_mod.Tuberia = StubTuberia
        try:
            rc = ad_mod.main(["--fuente", "a.jsonl", "--fuente", "b.jsonl",
                              "--salida", "/tmp/outx"])
            self.assertEqual(rc, 0)
            self.assertEqual(captured.get("fuentes"), ["a.jsonl", "b.jsonl"])
        finally:
            ad_mod.Tuberia = original
        # Sin --fuente ni --entrada usa la ruta por defecto
        captured.clear()
        ad_mod.Tuberia = StubTuberia
        try:
            ad_mod.main(["--salida", "/tmp/outy"])
            self.assertEqual(captured.get("fuentes"), [ad.ENTRADA_POR_DEFECTO])
        finally:
            ad_mod.Tuberia = original


class TestSplitPromptIdentico(unittest.TestCase):
    def test_prompt_identico_mismo_split(self):
        # Dos filas con humano exactamente idéntico van al mismo split aunque sus
        # claves de situación difieran (residuo a: tarot_1 en train y test).
        h = situacion_texto(1)
        a = fila(h, RESP_OK, "tarot_1", "id1")
        b = fila(h, RESP_OK, "tarot_1", "id2")
        items = [(a, "tarot_1"), (b, "tarot_1")]
        train, val, test = mf.split_agrupado(items, 42, 0.9, 0.05)
        # Si fueran a splits distintos, queo. Deben ir juntas.
        splits = []
        for s, grupo in (("train", train), ("val", val), ("test", test)):
            splits.extend([s] * len(grupo))
        self.assertEqual(len(set(splits)), 1)


def situacion_texto(i):
    return (f"Cartas: \u2014\ndata (no)\n"
            f"Carta 1: La Sombra {i} (al derecho)\n"
            f"Pregunta del consultante: \"\u00bfcomo evolucionara mi trabajo?\"")


class TestPuertaAsistenteIA(unittest.TestCase):
    def test_asistente_ia_mayuscula_fallido(self):
        f = {"conversations": _conv(
            "Pregunta del consultante: \"\u00bfque me depara el mes?\"",
            "La lectura se enfoca en la evolución del consultante y en una "
            "aplicación como el asistente de IA de MysticLog que ordena las "
            "cartas; conviene observar los silencios antes de actuar, porque "
            "la prisa nubla el juicio. Es un ciclo que se cierra con prudencia."),
            "id": "r1", "bloque": None}
        fallos = mf.fallos_puerta_calidad(f)
        self.assertTrue(any(str(x).startswith("restos_plantilla") for x in fallos),
                        fallos)


class TestPreguntasBasura(unittest.TestCase):
    def test_contar_no_elimina(self):
        filas = [
            fila("Pregunta del consultante: \"124 A ver,\"", RESP_OK,
                 "fuera_alcance", "b1"),
            fila("Pregunta del consultante: \"\u00bfque me depara?\"", RESP_OK,
                 "fuera_alcance", "b2"),
        ]
        report = qa.contar_preguntas_basura(filas)
        self.assertEqual(report["total"], 1)
        self.assertEqual(report["por_bloque"].get("fuera_alcance"), 1)
        # No elimina: falt 2 filas en la entrada
        self.assertEqual(len(filas), 2)

    def test_es_pregunta_basura(self):
        self.assertTrue(qa.es_pregunta_basura("124 A ver,"))
        self.assertTrue(qa.es_pregunta_basura("2 A ver"))
        self.assertFalse(qa.es_pregunta_basura("¿cómo evolucionará mi trabajo?"))


if __name__ == "__main__":
    unittest.main()
