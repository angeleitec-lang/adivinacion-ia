import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import random
import unittest

import generate_tasks as gt
import fase1_prompts as fp
import ejecutor_fase1 as ef
import evaluacion_casos as ec

NUEVAS = ("transitos", "revolucion_solar", "biorritmos", "fuera_alcance")
TILDES = "áéíóúñ¿¡"


def _kbs():
    return gt.load_kb("tarot.json"), gt.load_kb("astrologia.json"), gt.load_kb("numerologia.json"), gt.load_kb("baraja_espanola.json")


def _builder(seed=11):
    kb_tarot, kb_astro, kb_num, kb_baraja = _kbs()
    return gt.Builder(random.Random(seed), kb_tarot, kb_astro, kb_num, kb_baraja)


def _kb_fp():
    return {"tarot": None, "astrologia": None, "numerologia": None, "baraja": None}


class TestTargets(unittest.TestCase):
    def test_targets_nuevas(self):
        for f in NUEVAS:
            self.assertEqual(gt.TARGETS[f], 400, f)
        self.assertEqual(sum(gt.TARGETS.values()), 14136)

    def test_familias_registradas(self):
        for f in NUEVAS:
            self.assertIn(f, fp.FAMILIAS)
            self.assertIn(f, fp.RECOMENDACION_MAX_TOKENS)
            self.assertIn(f, fp.INSTRUCCIONES)


class TestRoundTrip(unittest.TestCase):
    """El prompt guardado debe reconstruirse igual desde el payload (ejecutor)."""

    def setUp(self):
        self.kb = fp._cargar_kb_real()

    def _check(self, familia, n=5):
        b = _builder(seed=hash(familia) % 10000)
        jobs = getattr(b, familia)(n)
        for bloque, system, prompt, payload, mt in jobs:
            self.assertEqual(bloque, familia)
            self.assertEqual(system, gt.SYSTEM)
            self.assertEqual(mt, fp.RECOMENDACION_MAX_TOKENS[familia])
            pregunta = ef.extraer_pregunta(prompt)
            tarea = ef.tarea_desde_job(bloque, json.loads(payload), pregunta, self.kb)
            self.assertEqual(tarea["familia"], familia)
            recon = fp.construir_prompt(tarea, self.kb)["user"]
            self.assertEqual(recon, prompt, f"round-trip roto en {familia}")

    def test_transitos_round_trip(self):
        self._check("transitos")

    def test_revolucion_solar_round_trip(self):
        self._check("revolucion_solar")

    def test_biorritmos_round_trip(self):
        self._check("biorritmos")

    def test_fuera_alcance_round_trip(self):
        self._check("fuera_alcance")


class TestDisjuncionEvaluacion(unittest.TestCase):
    """Los jobs nuevos no coinciden con los 240 casos de evaluación (semillas 560056-560058)."""

    def setUp(self):
        self.casos = ec.generar_casos(semilla=560056)
        self.assertEqual(len(self.casos), 240)

    def test_ids_disjuntos(self):
        b = _builder()
        ids_jobs = set()
        for f in NUEVAS:
            for _b, _s, _p, _pl, _m in getattr(b, f)(50):
                ids_jobs.add(_pl)
        ids_eval = {c["id"] for c in self.casos}
        self.assertTrue(all(i.startswith("eval-") for i in ids_eval))

    def test_prompts_disjuntos(self):
        b = _builder()
        prompts_norm = set()
        for f in NUEVAS:
            for _b, _s, prompt, _pl, _m in getattr(b, f)(50):
                prompts_norm.add(fp._norm(prompt))
        eval_norm = {fp._norm(c["user"]) for c in self.casos}
        self.assertEqual(prompts_norm & eval_norm, set())

    def test_preguntas_fuera_alcance_distintas(self):
        preguntas_eval = {fp._norm(c["tarea"]["pregunta"]) for c in self.casos
                        if c["familia"] == "fuera_alcance"}
        preguntas_ent = {fp._norm(p) for _t, p in gt.FUERA_ALCANCE_ENTRENAMIENTO}
        self.assertEqual(preguntas_ent & preguntas_eval, set())


class TestSimulacionVerifica(unittest.TestCase):
    """La lectura simulada del ejecutor pasa verificar_lectura para las familias nuevas."""

    def setUp(self):
        self.kb = fp._cargar_kb_real()

    def _check(self, familia, n=10):
        b = _builder(seed=7)
        for bloque, system, prompt, payload, _mt in getattr(b, familia)(n):
            pregunta = ef.extraer_pregunta(prompt)
            tarea = ef.tarea_desde_job(bloque, json.loads(payload), pregunta, self.kb)
            lectura = ef.simulacion_fase1(system, prompt)
            ok, motivos = fp.verificar_lectura(tarea, lectura)
            self.assertTrue(ok, f"{familia}: {motivos} :: {lectura[:200]}")

    def test_transitos_simulada_ok(self):
        self._check("transitos")

    def test_revolucion_solar_simulada_ok(self):
        self._check("revolucion_solar")

    def test_biorritmos_simulada_ok(self):
        self._check("biorritmos")

    def test_fuera_alcance_simulada_ok(self):
        self._check("fuera_alcance")

    def test_fuera_alcance_negativa_y_alternativa(self):
        b = _builder()
        for _b, system, prompt, _pl, _m in b.fuera_alcance(5):
            lectura = ef.simulacion_fase1(system, prompt)
            self.assertTrue(fp._RECHAZO_ALCANCE.search(lectura), lectura[:120])
            self.assertTrue(fp._ALTERNATIVA_TECNICAS.search(lectura), lectura[:120])


class TestTildes(unittest.TestCase):
    def test_prompts_con_tildes(self):
        b = _builder()
        for f in NUEVAS:
            for _b, _s, prompt, _pl, _m in getattr(b, f)(10):
                self.assertTrue(any(c in prompt for c in TILDES),
                              f"prompt sin tildes en {f}: {prompt[:120]}")


class TestFabricarTarea(unittest.TestCase):
    def test_smoke_cuatro_familias(self):
        kb = fp._cargar_kb_real()
        for f in NUEVAS:
            rng = random.Random(3)
            tarea, calc = fp._fabricar_tarea(f, rng, kb)
            self.assertEqual(tarea["familia"], f)
            prompt = fp.construir_prompt(tarea, kb, calc)["user"]
            self.assertTrue(any(c in prompt for c in TILDES), f)
            lectura = ef.simulacion_fase1(fp.SYSTEM, prompt)
            ok, motivos = fp.verificar_lectura(tarea, lectura)
            self.assertTrue(ok, f"{f}: {motivos}")


if __name__ == "__main__":
    unittest.main()
