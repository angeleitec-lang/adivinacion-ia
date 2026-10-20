"""Auditoría adversa ronda 3 (T58): casos de regresión de fallos silenciosos.

Un test por hallazgo confirmado. Los discutibles se anotan en ESTADO.md y no
se convierten en cambios de comportamiento.
"""

import argparse
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import descarga_clasicos_pd as dc
import evaluacion_casos as ec
import evaluar_modelo as ev
import multiturno as mt

CASOS = ec.generar_casos()


def _caso(familia):
    return next(c for c in CASOS if c["familia"] == familia)


def _args(**kw):
    d = {"min_chars": 40, "max_chars": 12000, "max_repetition": 0.12}
    d.update(kw)
    return argparse.Namespace(**d)


def _fila(cartas, humanos, respuestas, bloque="multiturno"):
    conv = [{"from": "system", "value": "Sistema de prueba"}]
    for h, g in zip(humanos, respuestas):
        conv.append({"from": "human", "value": h})
        conv.append({"from": "gpt", "value": g})
    return {
        "conversations": conv,
        "turnos": len(respuestas),
        "metadatos": {
            "bloque": bloque,
            "sistema": "Sistema de prueba",
            "cartas": cartas,
            "contexto": "amor",
            "referencia": "",
            "semilla": 1,
            "tipos": ["pregunta_inicial"] + ["seguimiento"] * (len(respuestas) - 1),
        },
    }


class TestEvaluadorCartas(unittest.TestCase):
    def test_carta_ambigua_esperada_sin_contexto_no_falta(self):
        caso = next(c for c in CASOS if c["id"] == "eval-tarot_3-08")
        texto = (
            "El Loco en el pasado habla de un inicio impulsivo. "
            "La Sota de Copas al derecho aporta una mirada sensible. "
            "El Caballero de Copas al derecho invita a escuchar lo que sientes."
        )
        resultado = ev.analizar_respuesta(caso, texto)
        motivos = [f["motivo"] for f in resultado["fallos"]]
        self.assertFalse(
            any(m == "Falta el naipe o carta: El Loco" for m in motivos),
            motivos,
        )
        self.assertFalse(
            any("carta ajena" in f["check"] and "El Loco" in f["motivo"]
                for f in resultado["fallos"]),
            motivos,
        )


class TestEvaluadorPromesas(unittest.TestCase):
    def test_promesa_tras_no_te_preocupes_se_marca(self):
        caso = _caso("etica")
        texto = (
            "No puedo diagnosticar ni sustituir a un médico. "
            "No te preocupes, te vas a curar."
        )
        resultado = ev.analizar_respuesta(caso, texto)
        promesas = [f for f in resultado["fallos"] if f["check"] == "promesas"]
        self.assertTrue(promesas, resultado["fallos"])
        self.assertIn("vas a curar", promesas[0]["motivo"].lower())

    def test_promesa_tras_dos_puntos_se_marca(self):
        caso = _caso("etica")
        texto = (
            "No puedo diagnosticar ni sustituir a un médico. "
            "Tranquila, esto no es grave: te vas a curar."
        )
        resultado = ev.analizar_respuesta(caso, texto)
        self.assertTrue(
            any(f["check"] == "promesas" for f in resultado["fallos"]),
            resultado["fallos"],
        )

    def test_negacion_real_de_la_promesa_no_se_marca(self):
        caso = _caso("etica")
        texto = (
            "No puedo diagnosticar ni sustituir a un médico. "
            "No puedo decirte que te vas a curar ni garantizar resultados."
        )
        resultado = ev.analizar_respuesta(caso, texto)
        self.assertFalse(
            any(f["check"] == "promesas" for f in resultado["fallos"]),
            resultado["fallos"],
        )


class TestEvaluadorCarga(unittest.TestCase):
    def test_respuestas_con_bom_se_cargan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "respuestas.jsonl"
            ruta.write_bytes(
                b"\xef\xbb\xbf" + b'{"id": "a", "respuesta": "texto"}\n'
            )
            self.assertEqual(ev.cargar_respuestas(ruta), {"a": "texto"})

    def test_casos_con_bom_se_cargan(self):
        caso = CASOS[0]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "casos.jsonl"
            ruta.write_bytes(
                b"\xef\xbb\xbf"
                + (json.dumps(caso, ensure_ascii=False) + "\n").encode("utf-8")
            )
            self.assertEqual(ev.cargar_casos(ruta)[0]["id"], caso["id"])


class TestMultiturno(unittest.TestCase):
    def test_respuesta_que_copia_la_pregunta_se_rechaza(self):
        cartas = [{"nombre": "El Loco", "invertida": False}]
        g1 = ("La carta El Loco sale al derecho y me habla de un inicio con calma "
              "y de mirar el camino con atencion.")
        g2 = ("Sobre ese mismo camino, El Loco al derecho sigue invitando a dar un "
              "paso prudente y a escuchar tus tiempos.")
        fila = _fila(cartas, [g1, "¿Y que mas ves en ese camino?"], [g1, g2])
        ok, motivo = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok, motivo)
        self.assertEqual(motivo, "copia_pregunta")

    def test_cartas_none_no_lanza_typeerror(self):
        g1 = ("La carta El Loco sale al derecho y me habla de un inicio con calma "
              "y de mirar el camino con atencion.")
        g2 = ("Sobre ese mismo camino, El Loco al derecho sigue invitando a dar un "
              "paso prudente y a escuchar tus tiempos.")
        fila = _fila(None, ["Consulta inicial", "Consulta de seguimiento"], [g1, g2])
        resultado = mt.verificar_conversacion(fila, _args())
        self.assertIsInstance(resultado, tuple)
        self.assertEqual(len(resultado), 2)

    def test_construir_fila_con_longitudes_distintas_falla(self):
        tarea = {"sistema": "s", "cartas": [], "contexto": "", "semilla": 1}
        guion = [{"texto": "uno", "tipo": "pregunta_inicial"},
                 {"texto": "dos", "tipo": "seguimiento"}]
        with self.assertRaises(ValueError):
            mt.construir_fila(guion, ["solo una"], tarea)


class TestDescargaResumen(unittest.TestCase):
    def test_id_con_traversal_no_escribe_fuera(self):
        fila = {
            "id": "../fuera",
            "url_texto": "https://www.gutenberg.org/files/1/1.txt",
            "prioridad": "alta",
        }
        with tempfile.TemporaryDirectory() as tmp:
            crudo = Path(tmp) / "crudo"
            with self.assertRaises(ValueError):
                dc.descargar_candidata(fila, str(crudo))
            self.assertFalse((Path(tmp) / "fuera.txt").exists())

    def test_todos_fallidos_no_se_resume_como_ya_existe(self):
        fila = {
            "id": "prueba-fallo",
            "url_texto": "https://www.gutenberg.org/files/1/1.txt",
            "prioridad": "alta",
        }
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(dc, "MAX_INTENTOS", 1), \
                    mock.patch.object(
                        dc, "_obtener_datos",
                        side_effect=urllib.error.URLError("sin red")):
                dc.descargar_todas([fila], tmp, pausa=0)
            resumen = json.loads(
                (Path(tmp) / "fetch.jsonl").read_text(encoding="utf-8").strip()
            )
        self.assertEqual(resumen["estado"], "fallida")
        self.assertEqual(resumen["fallidos"], 1)
        self.assertEqual(resumen["nuevos"], 0)


if __name__ == "__main__":
    unittest.main()
