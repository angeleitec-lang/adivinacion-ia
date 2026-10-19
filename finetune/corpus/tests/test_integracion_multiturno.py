"""Integración e2e del multi-turno: generador → worker simulado → validador (T16)."""
import argparse
import json
import os
import random
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import generate_synthetic as gs
import generate_tasks as gt
import validate_synthetic as vs
from tests.test_generate_tasks import kbs_para_test

ESQUEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bloque TEXT NOT NULL,
    system TEXT NOT NULL,
    prompt TEXT NOT NULL,
    payload TEXT NOT NULL,
    max_tokens INTEGER NOT NULL DEFAULT 1024,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    worker TEXT,
    error TEXT,
    updated_at TEXT
)
"""


def _fake_llamada(base, model, system, user, max_tokens, timeout,
                  retries=2, messages=None):
    if messages is None:
        cartas = vs.extraer_cartas(user)
        nombre = cartas[0][0] if cartas else "la carta"
        return (f"La carta {nombre} ilumina tu momento presente: es tiempo de "
                "calma interior, paciencia y escucha atenta; te pide avanzar con "
                "confianza y humildad ante lo que empieza.")
    cartas = vs.extraer_cartas(messages[1]["content"])
    nombre = cartas[0][0] if cartas else "la carta"
    return (f"Siguiendo con la calma de antes, {nombre} recomienda dar hoy el "
            "primer paso: una nota breve y clara sobre el mismo asunto que ya "
            "tratamos, sin dar vueltas ni repetirme.")


def _args_val(**kw):
    d = {"min_chars": 40, "max_chars": 12000, "max_repetition": 0.12}
    d.update(kw)
    return argparse.Namespace(**d)


def _builder(seed=7):
    kb_tarot, kb_astro, kb_num = kbs_para_test()
    return gt.Builder(random.Random(seed), kb_tarot, kb_astro, kb_num)


class IntegracionMultiturno(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "jobs.db"
        con = sqlite3.connect(self.db)
        con.executescript(ESQUEMA)
        con.commit()
        con.close()
        self.out = Path(self.tmp.name) / "synthetic"
        self.out.mkdir()
        gs.STOP.clear()

    def _genera_y_procesa(self, n):
        jobs = _builder().multiturno(n)
        con = sqlite3.connect(self.db)
        for bloque, system, prompt, payload, max_tokens in jobs:
            con.execute(
                "INSERT INTO jobs (bloque, system, prompt, payload, max_tokens) "
                "VALUES (?, ?, ?, ?, ?)",
                (bloque, system, prompt, payload, max_tokens),
            )
        con.commit()
        con.close()
        args = argparse.Namespace(
            db=str(self.db), only=None, limit=n, min_chars=40,
            endpoint="http://mock/v1", model="m", timeout=5, out=self.out,
        )
        stats = {"done": 0, "failed": 0, "started": 0, "t0": time.time()}
        with mock.patch.object(gs.time, "sleep"), \
                mock.patch.object(gs, "call_llm", _fake_llamada):
            gs.worker_loop(args, "t1", stats, threading.Lock())
        filas = []
        for f in sorted(self.out.glob("*.jsonl")):
            with open(f, encoding="utf-8") as fh:
                filas.extend(json.loads(line) for line in fh if line.strip())
        return jobs, stats, filas

    def test_ciclo_completo_multiturno(self):
        jobs, stats, filas = self._genera_y_procesa(5)
        self.assertEqual(len(jobs), 5)
        self.assertEqual(stats["done"], 5)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(len(filas), 5)
        for fila in filas:
            self.assertEqual(fila["turnos"], 2)
            self.assertEqual(len(fila["conversations"]), 5)
            ok, why = vs.validate(fila, _args_val(), bloque="multiturno")
            self.assertTrue(ok, why)

    def test_copia_a_mano_falla_validacion(self):
        _b, system, prompt, _payload, _mt = _builder().multiturno(1)[0]
        g1 = _fake_llamada("b", "m", system, prompt, 900, 5)
        fila = {
            "turnos": 2,
            "conversations": [
                {"from": "system", "value": system},
                {"from": "human", "value": prompt},
                {"from": "gpt", "value": g1},
                {"from": "human", "value": "¿Y el trabajo?"},
                {"from": "gpt", "value": g1},
            ],
        }
        ok, why = vs.validate(fila, _args_val(), bloque="multiturno")
        self.assertFalse(ok)
        self.assertEqual(why, "turno2_copia_turno1")

    def test_fila_monoturno_no_afectada(self):
        _b, system, prompt, _payload, _mt = _builder().multiturno(1)[0]
        g1 = _fake_llamada("b", "m", system, prompt, 900, 5)
        fila = {
            "conversations": [
                {"from": "system", "value": system},
                {"from": "human", "value": prompt},
                {"from": "gpt", "value": g1},
            ]
        }
        ok, why = vs.validate(fila, _args_val(), bloque="multiturno")
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
