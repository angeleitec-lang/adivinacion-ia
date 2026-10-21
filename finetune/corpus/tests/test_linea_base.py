#!/usr/bin/env python3
"""Tests de la línea base de modelos sin entrenar (T99).

Cubren ``linea_base.py`` sin red: presupuesto de tokens por familia,
validaciones de ``crear_cliente`` (paralelismo y clave de entorno para
Mercury), caché tolerante a líneas corruptas/duplicadas, reanudación de la
generación con cliente simulado, formato compatible con
``evaluar_modelo.cargar_respuestas``, no-caché de errores de red y
``evaluar_y_guardar`` (informe JSON/MD).
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import evaluar_modelo  # noqa: E402
import evaluacion_casos as ec  # noqa: E402
import linea_base as lb  # noqa: E402


RESPUESTA_OK = (
    "Las cartas sugieren un momento de cambio y de reflexion; tomalo como "
    "una orientacion posible junto a otras personas de confianza, no como "
    "un hecho fijo, y recuerda que la lectura no sustituye el consejo de "
    "un profesional si lo necesitas para tu salud o tus decisiones."
)


def caso_sintetico(rid: str, familia: str = "tarot_1") -> dict:
    return {
        "id": rid,
        "familia": familia,
        "system": "Eres un lector prudente.",
        "user": f"Caso {rid}: saca una carta sobre mi momento actual "
                "y explicamela.",
        "tarea": {},
        "calculos": {},
        "cartas": [],
        "orientaciones": {},
        "datos_esperados": {},
        "comprobaciones": ["no_vacia", "idioma", "longitud"],
        "longitud_minima": 5,
    }


class ClienteContador:
    """Cliente simulado que cuenta llamadas y devuelve texto fijo."""

    def __init__(self, texto=RESPUESTA_OK):
        self.texto = texto
        self.llamadas = []

    def chat(self, sistema, usuario, max_tokens=None, temperature=None,
             **kwargs):
        self.llamadas.append({"sistema": sistema, "usuario": usuario,
                              "max_tokens": max_tokens,
                              "temperature": temperature})
        return self.texto


class TestPresupuestoFamilias(unittest.TestCase):
    def test_cubre_las_doce_familias_de_evaluacion(self):
        self.assertEqual(set(lb.MAX_TOKENS_POR_FAMILIA),
                         set(ec.FAMILIAS_EVALUACION))

    def test_max_tokens_familia_desconocida_usa_por_defecto(self):
        self.assertEqual(lb.max_tokens_familia("nada_de_nada"), 1536)
        self.assertEqual(lb.max_tokens_familia("tarot_10"), 6144)


class TestCrearCliente(unittest.TestCase):
    def test_paralelismo_fuera_de_limites_se_rechaza(self):
        for paralelo in (0, 3):
            with self.subTest(paralelo=paralelo):
                with self.assertRaises(ValueError):
                    lb.crear_cliente("flash-next", paralelo)

    def test_modelo_desconocido_se_rechaza(self):
        with self.assertRaises(ValueError):
            lb.crear_cliente("gpt-9000", 1)

    def test_mercury_sin_clave_aborta_nombrando_el_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(lb.ClaveFaltanteError) as ctx:
                lb.crear_cliente("mercury-3", 1)
        self.assertIn("INCEPTION_API_KEY", str(ctx.exception))
        # El mensaje no puede contener valor de clave alguno: solo el nombre.
        self.assertNotIn("sk-", str(ctx.exception))

    def test_mercury_con_clave_en_el_entorno_crea_cliente(self):
        with patch.dict(os.environ, {"INCEPTION_API_KEY": "clave-falsa"}):
            cliente = lb.crear_cliente("mercury-3", 1)
        self.assertEqual(cliente.model, "mercury-3")
        self.assertEqual(cliente.reasoning_effort, "instant")

    def test_mercury_simulado_no_exige_clave(self):
        with patch.dict(os.environ, {}, clear=True):
            cliente = lb.crear_cliente(
                "mercury-3", 1, simulado=lambda s, u: "hola")
        self.assertIsNotNone(cliente)

    def test_flash_next_usa_solo_nodo2(self):
        self.assertIn("10.0.0.4", lb.MODELOS["flash-next"]["url"])
        self.assertNotIn("10.0.0.3", json.dumps(lb.MODELOS))


class TestCargarCache(unittest.TestCase):
    def test_tolera_corruptas_y_duplicadas_conservando_la_primera(self):
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "respuestas.jsonl"
            filas = [
                '{"id": "a", "respuesta": "primera"}',
                "línea que no es json {{{",
                '{"sin_id": true}',
                '{"id": "a", "respuesta": "segunda"}',
                '{"id": "b", "respuesta": "otra"}',
            ]
            destino.write_text("\n".join(filas) + "\n", encoding="utf-8")
            cache = lb.cargar_cache(destino)
        self.assertEqual(cache, {"a": "primera", "b": "otra"})

    def test_fichero_inexistente_cache_vacia(self):
        self.assertEqual(lb.cargar_cache(Path("/no/existe.jsonl")), {})


class TestGenerar(unittest.TestCase):
    def test_reanuda_y_escribe_formato_compatible(self):
        casos = [caso_sintetico("eval-a-01"), caso_sintetico("eval-a-02")]
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "respuestas.jsonl"
            primera = {"id": "eval-a-01", "respuesta": RESPUESTA_OK,
                       "extra": 1}
            destino.write_text(json.dumps(primera, ensure_ascii=False) + "\n",
                               encoding="utf-8")
            cliente = ClienteContador()
            resumen = lb.generar(casos, cliente, destino, "flash-next",
                                 temperatura=0.7, paralelo=2)
            self.assertEqual(resumen["en_cache"], 1)
            self.assertEqual(resumen["pedidas"], 1)
            self.assertEqual(resumen["escritas"], 1)
            self.assertEqual(resumen["erroneas"], 0)
            self.assertEqual(len(cliente.llamadas), 1)
            self.assertEqual(cliente.llamadas[0]["temperature"], 0.7)
            self.assertEqual(cliente.llamadas[0]["max_tokens"],
                             lb.max_tokens_familia("tarot_1"))
            respuestas = evaluar_modelo.cargar_respuestas(destino)
            self.assertEqual(set(respuestas), {"eval-a-01", "eval-a-02"})
            self.assertTrue(respuestas["eval-a-02"].strip())

    def test_todo_en_cache_no_hace_ninguna_peticion(self):
        casos = [caso_sintetico("eval-a-01")]
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "respuestas.jsonl"
            destino.write_text(
                json.dumps({"id": "eval-a-01", "respuesta": RESPUESTA_OK})
                + "\n", encoding="utf-8")
            cliente = ClienteContador()
            resumen = lb.generar(casos, cliente, destino, "flash-next")
            self.assertEqual(resumen["pedidas"], 0)
            self.assertEqual(cliente.llamadas, [])

    def test_errores_no_se_cachean_y_quedan_pendientes(self):
        casos = [caso_sintetico("eval-a-01"), caso_sintetico("eval-a-02")]
        with tempfile.TemporaryDirectory() as td:
            destino = Path(td) / "respuestas.jsonl"

            class ClienteMixto:
                def chat(self, sistema, usuario, max_tokens=None,
                         temperature=None, **kwargs):
                    if "eval-a-01" in usuario:
                        raise ConnectionError("sin conexion")
                    return RESPUESTA_OK

            resumen = lb.generar(casos, ClienteMixto(), destino, "flash-next",
                                 paralelo=2)
            self.assertEqual(resumen["escritas"], 1)
            self.assertEqual(resumen["erroneas"], 1)
            self.assertEqual(len(resumen["errores"]), 1)
            self.assertEqual(resumen["errores"][0]["tipo"], "ConnectionError")
            cache = lb.cargar_cache(destino)
            self.assertEqual(set(cache), {"eval-a-02"})
            # Segunda pasada reintenta solo el fallido.
            cliente = ClienteContador()
            resumen2 = lb.generar(casos, cliente, destino, "flash-next",
                                  paralelo=2)
            self.assertEqual(resumen2["pedidas"], 1)
            self.assertEqual(len(cliente.llamadas), 1)


class TestEvaluarYGuardar(unittest.TestCase):
    def test_produce_informe_json_y_md(self):
        casos = [caso_sintetico("eval-a-01"), caso_sintetico("eval-a-02")]
        with tempfile.TemporaryDirectory() as td:
            respuestas = Path(td) / "respuestas.jsonl"
            respuestas.write_text(
                "\n".join(json.dumps({"id": c["id"], "respuesta": RESPUESTA_OK},
                                     ensure_ascii=False) for c in casos)
                + "\n", encoding="utf-8")
            base = Path(td) / "informe"
            ruta_json, ruta_md = lb.evaluar_y_guardar(casos, respuestas, base)
            self.assertTrue(ruta_json.exists())
            self.assertTrue(ruta_md.exists())
            informe = json.loads(ruta_json.read_text(encoding="utf-8"))
            self.assertEqual(informe["global"]["casos"], 2)
            self.assertIn("tarot_1", informe["por_familia"])
            self.assertEqual(informe["por_familia"]["tarot_1"]["casos"], 2)


if __name__ == "__main__":
    unittest.main()
