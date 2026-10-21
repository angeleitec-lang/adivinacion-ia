#!/usr/bin/env python3
"""Tests del piloto de fase 1 con Mercury 3 (T83) con cliente simulado."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import piloto_mercury as pm  # noqa: E402
from llm_client import LLMClient  # noqa: E402


def tarea_fake():
    t = {
        "id": "tarot_1-01",
        "familia": "tarot_1",
        "tarea": {
            "familia": "tarot_1",
            "contexto": "trabajo",
            "pregunta": "¿Cómo va mi proyecto?",
            "cartas": [{"nombre": "El Loco", "invertida": False}],
            "universo_cartas": ["El Loco", "La Torre", "La Estrella"],
            "calculos": {},
        },
        "prompt_system": "Sistema de prueba.",
        "prompt_user": "Tirada: El Loco (al derecho). Lee el tarot.",
    }
    return t


BUENA = "El Loco abre tu proyecto: es un comienzo, no un final."
MALA = "La Torre destruye tu proyecto."


class TestCrearCliente(unittest.TestCase):
    def setUp(self):
        import unittest.mock
        patcher = unittest.mock.patch.object(pm, "cargar_clave_inception",
                                             return_value="clave-de-prueba")
        self._patch_clave = patcher
        self._patch_clave.start()
        self.addCleanup(self._patch_clave.stop)

    def test_configura_mercury_por_familia(self):
        cliente = pm.crear_cliente("tarot_1")
        spec = cliente._specs[0]
        self.assertEqual(spec["model"], "mercury-3")
        self.assertEqual(spec["url"], "https://api.inceptionlabs.ai/v1")
        self.assertEqual(cliente.reasoning_effort, "instant")
        self.assertEqual(cliente.max_completion_tokens,
                         1536)  # RECOMENDACION_MAX_TOKENS["tarot_1"]

    def test_max_completion_tokens_largas(self):
        self.assertEqual(pm.crear_cliente("cruz_celta").max_completion_tokens, 6144)
        self.assertEqual(pm.crear_cliente("lectura_completa").max_completion_tokens, 6144)


class TestEjecutarUna(unittest.TestCase):
    def test_aprobacion_a_la_primera(self):
        cliente = LLMClient(simulado=lambda s, u: "<think>pienso</think>" + BUENA)
        r = pm.ejecutar_una(tarea_fake(), cliente)
        self.assertTrue(r["ok"])
        self.assertEqual(r["intentos"], 1)
        self.assertEqual(r["motivos"], [])
        self.assertIsNone(r["error"])
        self.assertEqual(r["lectura"], BUENA)
        self.assertFalse(r["truncada"])

    def test_fallo_y_reintento_exitoso(self):
        llamadas = []

        def sim(s, u):
            llamadas.append(u)
            return MALA if len(llamadas) == 1 else BUENA

        r = pm.ejecutar_una(tarea_fake(), LLMClient(simulado=sim), max_reintentos=1)
        self.assertTrue(r["ok"])
        self.assertEqual(r["intentos"], 2)
        self.assertIn("rechazada", llamadas[1])

    def test_fallo_definitivo(self):
        r = pm.ejecutar_una(tarea_fake(), LLMClient(simulado=lambda s, u: MALA))
        self.assertFalse(r["ok"])
        self.assertEqual(r["intentos"], 2)
        self.assertTrue(r["motivos"])

    def test_salida_vacia(self):
        r = pm.ejecutar_una(tarea_fake(), LLMClient(simulado=lambda s, u: "  "))
        self.assertEqual(r["error"], "salida_vacia")
        self.assertFalse(r["ok"])

    def test_error_de_red_se_registra(self):
        def sim(s, u):
            raise ConnectionError("boom")

        r = pm.ejecutar_una(tarea_fake(), LLMClient(simulado=sim))
        self.assertEqual(r["error"], "error_red:ConnectionError")
        self.assertFalse(r["ok"])

    def test_truncamiento_se_detecta(self):
        texto_truncado = "El Loco abre tu proyecto: es un comienzo"
        r = pm.ejecutar_una(
            tarea_fake(), LLMClient(simulado=lambda s, u: texto_truncado))
        self.assertFalse(r["ok"])
        self.assertTrue(r["truncada"])


class TestEjecutarPiloto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "salida"
        self.addCleanup(self.tmp.cleanup)

    def _lineas(self):
        p = self.out / "piloto.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def _factory(self, simulado):
        def make(familia, metricas=None, simulado=simulado):
            return LLMClient(simulado=simulado)
        return make

    def test_escribe_y_es_reanudable(self):
        tareas = [tarea_fake(), {**tarea_fake(), "id": "tarot_1-02"}]
        res = pm.ejecutar_piloto(
            tareas, worker=2, out_dir=self.out,
            cliente_factory=self._factory(lambda s, u: BUENA))
        self.assertEqual(res["escritas"], 2)
        self.assertEqual(len(self._lineas()), 2)
        res2 = pm.ejecutar_piloto(
            tareas, worker=2, out_dir=self.out,
            cliente_factory=self._factory(lambda s, u: BUENA))
        self.assertEqual(res2["escritas"], 0)
        self.assertEqual(res2["omitidos"], 2)

    def test_registro_contiene_campos(self):
        pm.ejecutar_piloto(
            [tarea_fake()], worker=1, out_dir=self.out,
            cliente_factory=self._factory(lambda s, u: BUENA))
        r = self._lineas()[0]
        for campo in ("id", "familia", "prompt_system", "prompt_user", "lectura",
                      "ok", "motivos", "intentos", "chars", "truncada",
                      "max_completion_tokens", "segundos"):
            self.assertIn(campo, r)

    def test_errores_se_registran_y_no_paran_debajo_umbral(self):
        llamadas = {"n": 0}

        def sim(s, u):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise ConnectionError("uno falló")
            return BUENA

        tareas = [{**tarea_fake(), "id": f"tarot_1-{i:02d}"} for i in range(1, 6)]
        res = pm.ejecutar_piloto(
            tareas, worker=2, out_dir=self.out,
            cliente_factory=self._factory(sim), umbral_error=0.40,
            min_muestras=3)
        self.assertIsNone(res["parada"])
        self.assertEqual(res["escritas"], 4)
        self.assertEqual(res["errores"], 1)
        self.assertEqual(len(list(self.out.glob("piloto_errores.jsonl"))), 1)


class TestInforme(unittest.TestCase):
    def test_contiene_secciones(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        out = Path(self.tmp.name)
        pm.ejecutar_piloto(
            [tarea_fake()], worker=1, out_dir=out,
            cliente_factory=lambda f, metricas=None, simulado=None:
            LLMClient(simulado=lambda s, u: MALA))
        texto = pm.generar_informe(out, meta={"metricas": {
            "prompt_tokens": 100, "completion_tokens": 50}})
        self.assertIn("Aprobación por familia", texto)
        self.assertIn("GLOBAL", texto)
        self.assertIn("Motivos de rechazo", texto)
        self.assertIn("Estimación para 10.270 lecturas", texto)
        informe = out / "PILOTO_MERCURY.md"
        self.assertTrue(informe.exists())
        self.assertIn("tarot_1", informe.read_text(encoding="utf-8"))

    def test_sin_registros_no_explota(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        texto = pm.generar_informe(Path(self.tmp.name), meta={})
        self.assertIn("Sin lecturas", texto)


if __name__ == "__main__":
    unittest.main()
