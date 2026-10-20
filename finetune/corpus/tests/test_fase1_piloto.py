#!/usr/bin/env python3
"""Tests del piloto de fase 1 (T49) con cliente simulado determinista."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fase1_piloto as fp  # noqa: E402
from llm_client import LLMClient  # noqa: E402


def tarea_tarot():
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
        "prompt_user": "Tirada: El Loco (derecho). Lee el tarot.",
    }
    return t


BUENA = "El Loco abre tu proyecto: es un comienzo, no un final."
MALA = "La Torre destruye tu proyecto."


class TestLimpiar(unittest.TestCase):
    def test_quita_bloque_de_pensamiento(self):
        raw = "<think>Voy a razonar largo.</think>\n\nEsta es la lectura final."
        self.assertEqual(fp.limpiar_lectura(raw), "Esta es la lectura final.")

    def test_bloque_abierto_se_descarta(self):
        raw = "Lectura buena.\n<thinking>razonamiento truncado"
        self.assertEqual(fp.limpiar_lectura(raw), "Lectura buena.")

    def test_texto_plano_intacto(self):
        self.assertEqual(fp.limpiar_lectura("  texto normal  "), "texto normal")

    def test_vacio(self):
        self.assertEqual(fp.limpiar_lectura(None), "")
        self.assertEqual(fp.limpiar_lectura("   "), "")

    def test_ignora_mayusculas(self):
        raw = "<THINK>abc</THINK>final"
        self.assertEqual(fp.limpiar_lectura(raw), "final")


class TestPromptReintento(unittest.TestCase):
    def test_incluye_motivos(self):
        p = fp.prompt_reintento("PROMPT", ["falta la carta El Loco", "menciona La Torre"])
        self.assertIn("PROMPT", p)
        self.assertIn("falta la carta El Loco", p)
        self.assertIn("menciona La Torre", p)


class TestEjecutarUna(unittest.TestCase):
    def test_aprobacion_a_la_primera(self):
        cliente = LLMClient(simulado=lambda s, u: "<think>pienso</think>" + BUENA)
        r = fp.ejecutar_una(tarea_tarot(), cliente)
        self.assertTrue(r["ok"])
        self.assertEqual(r["intentos"], 1)
        self.assertEqual(r["motivos"], [])
        self.assertIsNone(r["error"])
        self.assertEqual(r["lectura"], BUENA)
        self.assertEqual(r["chars"], len(BUENA))

    def test_fallo_y_reintento_exitoso(self):
        llamadas = []

        def sim(s, u):
            llamadas.append(u)
            return MALA if len(llamadas) == 1 else BUENA

        r = fp.ejecutar_una(tarea_tarot(), LLMClient(simulado=sim), max_reintentos=1)
        self.assertTrue(r["ok"])
        self.assertEqual(r["intentos"], 2)
        self.assertEqual(len(llamadas), 2)
        self.assertIn("rechazada", llamadas[1])

    def test_fallo_definitivo(self):
        r = fp.ejecutar_una(tarea_tarot(), LLMClient(simulado=lambda s, u: MALA))
        self.assertFalse(r["ok"])
        self.assertEqual(r["intentos"], 2)
        self.assertTrue(r["motivos"])

    def test_sin_reintentos(self):
        r = fp.ejecutar_una(tarea_tarot(), LLMClient(simulado=lambda s, u: MALA),
                            max_reintentos=0)
        self.assertFalse(r["ok"])
        self.assertEqual(r["intentos"], 1)

    def test_salida_vacia_del_modelo(self):
        r = fp.ejecutar_una(tarea_tarot(), LLMClient(simulado=lambda s, u: "  "))
        self.assertEqual(r["error"], "salida_vacia")
        self.assertFalse(r["ok"])

    def test_error_de_red_se_registra(self):
        def sim(s, u):
            raise ConnectionError("boom")

        r = fp.ejecutar_una(tarea_tarot(), LLMClient(simulado=sim))
        self.assertEqual(r["error"], "error_red:ConnectionError")
        self.assertFalse(r["ok"])


class TestEjecutarPiloto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "salida"
        self.addCleanup(self.tmp.cleanup)

    def _lineas(self):
        p = self.out / "piloto.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def test_escribe_y_es_reanudable(self):
        tareas = [tarea_tarot(), {**tarea_tarot(), "id": "tarot_1-02"}]
        cliente = LLMClient(simulado=lambda s, u: BUENA)
        res = fp.ejecutar_piloto(tareas, cliente, out_dir=self.out)
        self.assertEqual(res["escritas"], 2)
        self.assertEqual(len(self._lineas()), 2)
        res2 = fp.ejecutar_piloto(tareas, cliente, out_dir=self.out)
        self.assertEqual(res2["escritas"], 0)
        self.assertEqual(res2["omitidos"], 2)
        ids = [r["id"] for r in self._lineas()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_registro_contiene_campos(self):
        fp.ejecutar_piloto([tarea_tarot()], LLMClient(simulado=lambda s, u: BUENA),
                           out_dir=self.out)
        r = self._lineas()[0]
        for campo in ("id", "familia", "prompt_system", "prompt_user", "lectura",
                      "ok", "motivos", "intentos", "chars", "segundos"):
            self.assertIn(campo, r)

    def test_parada_por_exceso_de_errores(self):
        def sim(s, u):
            raise ConnectionError("caído")

        tareas = [{**tarea_tarot(), "id": f"tarot_1-{i:02d}"} for i in range(1, 6)]
        res = fp.ejecutar_piloto(tareas, LLMClient(simulado=sim), out_dir=self.out)
        self.assertIsNotNone(res["parada"])
        self.assertGreater(res["errores"], 0)
        self.assertEqual(self._lineas(), [])

    def test_errores_por_debajo_del_umbral_no_parada(self):
        llamadas = {"n": 0}

        def sim(s, u):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise ConnectionError("uno falló")
            return BUENA

        tareas = [{**tarea_tarot(), "id": f"tarot_1-{i:02d}"} for i in range(1, 6)]
        res = fp.ejecutar_piloto(tareas, LLMClient(simulado=sim), out_dir=self.out,
                                 umbral_error=0.40, min_muestras=3)
        self.assertIsNone(res["parada"])
        self.assertEqual(res["escritas"], 4)
        self.assertEqual(res["errores"], 1)

    def test_no_escribe_errores_para_reanudar(self):
        estado = {"n": 0}

        def sim(s, u):
            estado["n"] += 1
            if estado["n"] == 1:
                return ""
            return BUENA

        tareas = [tarea_tarot(), {**tarea_tarot(), "id": "tarot_1-02"}]
        res1 = fp.ejecutar_piloto(tareas, LLMClient(simulado=sim), out_dir=self.out,
                                  umbral_error=0.99)
        self.assertEqual(res1["escritas"], 1)
        res2 = fp.ejecutar_piloto(tareas, LLMClient(simulado=lambda s, u: BUENA),
                                  out_dir=self.out)
        self.assertEqual(res2["escritas"], 1)
        self.assertEqual(res2["omitidos"], 1)


class TestCargarTareas(unittest.TestCase):
    def test_todas_las_familias_ids_unicos(self):
        tareas = fp.cargar_tareas(n_por_familia=2, semilla=42)
        self.assertEqual(len(tareas), 2 * len(fp.FAMILIAS))
        ids = [t["id"] for t in tareas]
        self.assertEqual(len(ids), len(set(ids)))
        familias = {t["familia"] for t in tareas}
        self.assertEqual(familias, set(fp.FAMILIAS))
        for t in tareas:
            self.assertIn("calculos", t["tarea"])
            self.assertTrue(t["prompt_system"])
            self.assertTrue(t["prompt_user"])

    def test_determinista_con_semilla(self):
        a = [t["prompt_user"] for t in fp.cargar_tareas(1, 7)]
        b = [t["prompt_user"] for t in fp.cargar_tareas(1, 7)]
        self.assertEqual(a, b)


class TestInforme(unittest.TestCase):
    def test_contiene_secciones_y_estimacion(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        fp.ejecutar_piloto([tarea_tarot()], LLMClient(simulado=lambda s, u: MALA),
                           out_dir=out)
        texto = fp.generar_informe(out, meta={"procesadas": 1, "errores": 0})
        self.assertIn("Aprobación por familia", texto)
        self.assertIn("GLOBAL", texto)
        self.assertIn("Motivos de rechazo", texto)
        self.assertIn("sin reintento", texto)
        self.assertIn("Estimación para 10.000 lecturas", texto)
        informe = out / "informe_piloto.md"
        self.assertTrue(informe.exists())
        self.assertIn("tarot_1", informe.read_text(encoding="utf-8"))

    def test_estimacion_con_tiempos_reales(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name)
        registro = {**tarea_tarot(), "tarea": None, "lectura": BUENA, "ok": True,
                    "motivos": [], "intentos": 1, "chars": len(BUENA), "segundos": 7.2,
                    "error": None}
        (out / "piloto.jsonl").write_text(
            json.dumps(registro, ensure_ascii=False) + "\n", encoding="utf-8")
        texto = fp.generar_informe(out, meta={"procesadas": 1, "errores": 0})
        self.assertIn("3 workers", texto)
        self.assertIn("6 workers", texto)

    def test_sin_registros_no_explota(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        texto = fp.generar_informe(Path(tmp.name), meta={})
        self.assertIn("Sin lecturas", texto)


if __name__ == "__main__":
    unittest.main()
