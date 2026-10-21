"""Casos límite de los arreglos T101 (ronda 6) y de ``reverificar_fase1``."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_dataset as bd  # noqa: E402
import consenso_kb  # noqa: E402
import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import generate_tasks as gt  # noqa: E402
import merge_final  # noqa: E402
import reverificar_fase1 as rev  # noqa: E402

BUENA = "El Loco abre tu camino: es un comienzo lleno de posibilidad."
PROMPT = (
    "Tirada de una carta de tarot.\n\n"
    "Carta: El Loco (al derecho).\nContexto: trabajo.\n"
    'Pregunta del consultante: "¿Cómo va mi proyecto?"'
)
PAYLOAD = {"carta": {"nombre": "El Loco", "invertida": False},
           "contexto": "trabajo"}


def escribir_jsonl(ruta, filas):
    Path(ruta).write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
        encoding="utf-8")


def leer_jsonl(ruta):
    p = Path(ruta)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


class TestReverificarFase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.entrada = Path(self.tmp.name) / "aceptadas.jsonl"
        self.salida = Path(self.tmp.name) / "validas.jsonl"

    def _fila(self, i=1, respuesta=BUENA, **extra):
        fila = {"id": i, "bloque": "tarot_1", "payload": PAYLOAD,
                "prompt_user": PROMPT, "respuesta": respuesta}
        fila.update(extra)
        return fila

    def test_separa_validas_y_rechazadas_sin_tocar_la_entrada(self):
        escribir_jsonl(self.entrada, [
            self._fila(1, BUENA),
            self._fila(2, "El Loco abre tu camino. El Arquitecto lo cierra."),
        ])
        antes = self.entrada.read_bytes()
        res = rev.reverificar(self.entrada, self.salida, kb=self.kb)
        self.assertEqual(antes, self.entrada.read_bytes())
        self.assertEqual(res["validas"], 1)
        self.assertEqual(res["invalidas"], 1)
        self.assertEqual(len(leer_jsonl(self.salida)), 1)
        rechazadas = leer_jsonl(res["rechazadas"])
        self.assertTrue(any("inexistente" in m for m in rechazadas[0]["motivos"]))

    def test_filtra_evaluacion_por_origen_y_por_contenido(self):
        eval_casos = Path(self.tmp.name) / "evaluacion.jsonl"
        escribir_jsonl(eval_casos, [{
            "id": "eval-tarot_1-01", "origen": "evaluacion",
            "conversations": [{"from": "human", "value": PROMPT},
                              {"from": "gpt", "value": BUENA}],
        }])
        escribir_jsonl(self.entrada, [
            self._fila(1, BUENA, origen="evaluacion"),
            self._fila(2, BUENA),
        ])
        res = rev.reverificar(self.entrada, self.salida,
                              eval_casos=eval_casos, kb=self.kb)
        self.assertEqual(res["validas"], 0)
        self.assertEqual(res["evaluacion"], 2)

    def test_acepta_sharegpt_sin_payload(self):
        fila = {"id": 7, "bloque": "tarot_1", "conversations": [
            {"from": "human", "value": PROMPT},
            {"from": "gpt", "value": BUENA},
        ]}
        escribir_jsonl(self.entrada, [fila])
        res = rev.reverificar(self.entrada, self.salida, kb=self.kb)
        self.assertEqual(res["validas"], 1, res)

    def test_no_permite_sobrescribir_la_entrada(self):
        escribir_jsonl(self.entrada, [self._fila()])
        with self.assertRaises(ValueError):
            rev.reverificar(self.entrada, self.entrada, kb=self.kb)


class TestCasosLimiteVerificador(unittest.TestCase):
    def _tarea(self, payload):
        return ef.tarea_desde_job("tarot_1", payload, "¿Qué me depara el trabajo?",
                                  ef.cargar_kb())

    def test_numero_correcto_en_frase_natural_pasa(self):
        tarea = ef.tarea_desde_job(
            "numerologia", {"fecha": "1992-11-29", "nombre": "Ana"}, "¿x?",
            ef.cargar_kb())
        ok, motivos = fp.verificar_lectura(tarea, "Tu camino de vida es el 7.")
        self.assertTrue(ok, motivos)

    def test_anio_de_cuatro_cifras_no_es_el_valor(self):
        tarea = ef.tarea_desde_job(
            "numerologia", {"fecha": "1992-11-29", "nombre": "Ana"}, "¿x?",
            ef.cargar_kb())
        ok, motivos = fp.verificar_lectura(
            tarea, "Tu año personal 2026 llega con cambios.")
        self.assertTrue(ok, motivos)

    def test_orientacion_correcta_por_carta_pasa(self):
        tarea = self._tarea({"cartas": [
            {"nombre": "El Sol", "invertida": True},
            {"nombre": "La Luna", "invertida": False},
        ]})
        texto = ("El Sol aparece invertida y te invita a la pausa. La Luna "
                 "ilumina tus emociones.")
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertTrue(ok, motivos)

    def test_perifrasis_plural_tambien_es_promesa(self):
        tarea = self._tarea({"cartas": [{"nombre": "El Sol", "invertida": False}]})
        texto = "El Sol te acompaña. Podéis dejar de tomar la medicación."
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertFalse(ok, motivos)

    def test_lectura_completa_respeta_limites_de_seccion(self):
        tarea = {"familia": "lectura_completa", "cartas": [],
                 "universo_cartas": [], "calculos": {}}
        texto = (
            "## Carta natal\n" + ("x" * (fp.LIMITE_POSICION_CHARS + 1)) + "\n"
            "## Tirada de tres cartas\nbreve\n"
            "## Numerología\nbreve\n"
            "## Síntesis\nbreve")
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertFalse(ok)
        self.assertTrue(any("excede" in m for m in motivos), motivos)


class TestCasosLimitePipeline(unittest.TestCase):
    def test_replace_pending_reintenta_failed_sin_duplicar(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        con = sqlite3.connect(str(Path(tmp.name) / "jobs.db"))
        gt.crear_tabla(con)
        filas = [("alfa", "sys", "p1", "{}", 100),
                 ("alfa", "sys", "p2", "{}", 100)]
        gt.insertar_jobs(con, filas)
        con.execute("UPDATE jobs SET status='done' WHERE prompt='p1'")
        con.execute("UPDATE jobs SET status='failed' WHERE prompt='p2'")
        con.commit()
        gt.insertar_jobs(con, filas, replace_pending=True)
        estados = dict(con.execute(
            "SELECT prompt, status FROM jobs WHERE bloque='alfa'").fetchall())
        self.assertEqual(estados, {"p1": "done", "p2": "pending"})
        con.close()

    def test_merge_excluye_caso_de_evaluacion_por_id(self):
        fila = {"id": "eval-tarot_1-01", "origen": "evaluacion",
                "conversations": [{"from": "human", "value": "¿pregunta?"},
                                  {"from": "gpt", "value": "respuesta de prueba"}]}
        res = merge_final.fusionar([fila], [], [], [],
                                   {"seed": 42, "train_ratio": 0.8,
                                    "val_ratio": 0.1})
        self.assertEqual(res["train"] + res["val"] + res["test"], [])

    def test_merge_excluye_contenido_de_evaluacion_por_human(self):
        fila = {"id": 10, "conversations": [
            {"from": "human", "value": "¿Pregunta reservada?"},
            {"from": "gpt", "value": "Respuesta suficientemente larga."}]}
        res = merge_final.fusionar(
            [fila], [], [], [],
            {"seed": 42, "train_ratio": 0.8, "val_ratio": 0.1,
             "eval_humanos": {"¿pregunta reservada?"}})
        self.assertEqual(res["train"], [])

    def test_build_dataset_filtra_preguntas_de_evaluacion(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ruta = Path(tmp.name) / "eval.jsonl"
        escribir_jsonl(ruta, [{
            "id": "eval-tarot_1-01", "origen": "evaluacion",
            "conversations": [{"from": "human", "value": "¿Pregunta reservada?"},
                              {"from": "gpt", "value": "x"}]}])
        humanos = bd.humanos_evaluacion(ruta)
        pares = [{"conversations": [
            {"from": "system", "value": "sys"},
            {"from": "human", "value": "¿Pregunta reservada?"},
            {"from": "gpt", "value": "respuesta"}]}]
        self.assertEqual(bd.filtrar_evaluacion(pares, humanos), [])

    def test_load_jsonl_estricto_falla(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ruta = Path(tmp.name) / "x.jsonl"
        ruta.write_text('{"a": 1}\n{roto', encoding="utf-8")
        with self.assertRaises(ValueError):
            merge_final.load_jsonl(ruta, estricto=True)

    def test_claves_de_exclusion_cuentan_descartes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ruta = Path(tmp.name) / "claves.jsonl"
        escribir_jsonl(ruta, [
            {"entidad_id": "e", "faceta": "f", "hash_seccion": "abc"},
            {"entidad_id": "e", "faceta": "f", "hash_seccion": "  "},
            {"entidad_id": "e"},
        ])
        stats = {}
        claves = consenso_kb.cargar_claves_exclusion(ruta, stats)
        self.assertEqual(claves, {("e", "f"): {"abc"}})
        self.assertEqual(stats, {"lineas": 3, "validas": 1, "descartadas": 2})

    def test_backend_invalido_falla(self):
        with self.assertRaises(ValueError):
            ef.ejecutar("no-existe.db", None, {}, backend="mercury")

    def test_sharegpt_sin_generador_escribe_local(self):
        fila = ef.a_sharegpt({"prompt_user": "hola", "respuesta": "mundo"})
        self.assertEqual(fila["generador"], ef.GENERADOR_LOCAL)


if __name__ == "__main__":
    unittest.main()
