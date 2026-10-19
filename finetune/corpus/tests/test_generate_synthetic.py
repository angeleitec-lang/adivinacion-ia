"""Tests de generate_synthetic: reset de trabajos, contadores y multi-turno."""
import argparse
import json
import os
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


def _inserta(con, status, worker, updated_at):
    con.execute(
        "INSERT INTO jobs (bloque, system, prompt, payload, status, worker, "
        "updated_at) VALUES ('tarot', 'sys', 'prompt', '{}', ?, ?, ?)",
        (status, worker, updated_at),
    )


class ResetStale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "jobs.db"
        self.con = sqlite3.connect(self.db)
        self.con.executescript(ESQUEMA)
        self.addCleanup(self.con.close)

    def _estado(self):
        return {w: s for w, s in self.con.execute(
            "SELECT worker, status FROM jobs")}

    def test_no_reinicia_running_de_otro_tag(self):
        ahora = time.strftime("%Y-%m-%d %H:%M:%S")
        _inserta(self.con, "running", "nodo2-w1", ahora)
        self.con.commit()
        gs.resetear_stale(self.con, "nodo1")
        self.assertEqual(self._estado()["nodo2-w1"], "running")

    def test_reinicia_running_del_mismo_tag(self):
        ahora = time.strftime("%Y-%m-%d %H:%M:%S")
        _inserta(self.con, "running", "nodo1", ahora)
        self.con.commit()
        gs.resetear_stale(self.con, "nodo1")
        self.assertEqual(self._estado()["nodo1"], "pending")

    def test_reinicia_anticuos(self):
        viejo = time.strftime("%Y-%m-%d %H:%M:%S",
                             time.localtime(time.time() - 3 * 3600))
        _inserta(self.con, "running", "nodo2-w1", viejo)
        self.con.commit()
        gs.resetear_stale(self.con, "nodo1")
        self.assertEqual(self._estado()["nodo2-w1"], "pending")

    def test_no_toca_los_pending(self):
        ahora = time.strftime("%Y-%m-%d %H:%M:%S")
        _inserta(self.con, "pending", None, ahora)
        self.con.commit()
        gs.resetear_stale(self.con, "nodo1")
        self.assertEqual(self._estado()[None], "pending")


class ContadorStarted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "jobs.db"
        con = sqlite3.connect(self.db)
        con.executescript(ESQUEMA)
        con.commit()
        con.close()
        self.args = argparse.Namespace(
            db=str(self.db), only=None, limit=1, min_chars=10,
            endpoint="http://mock/v1", model="m", timeout=5,
            out=Path(self.tmp.name) / "synthetic",
        )
        (Path(self.tmp.name) / "synthetic").mkdir()
        gs.STOP.clear()

    def _stats(self):
        return {"done": 0, "failed": 0, "started": 0, "t0": time.time()}

    def test_started_no_cuenta_reclamos_vacios(self):
        stats = self._stats()
        with mock.patch.object(gs.time, "sleep"):
            gs.worker_loop(self.args, "t1", stats, threading.Lock())
        self.assertEqual(stats["started"], 0)
        self.assertEqual(stats["done"], 0)

    def test_started_cuenta_reclamo_real(self):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO jobs (bloque, system, prompt, payload) "
            "VALUES ('tarot', 'sys', 'prompt', '{}')")
        con.commit()
        con.close()
        texto = ("La luna llena ilumina el camino y las cartas hablan de un "
                "cambio interior profundo para ti en este momento.")
        stats = self._stats()
        with mock.patch.object(gs.time, "sleep"), \
                mock.patch.object(gs, "call_llm", return_value=texto):
            gs.worker_loop(self.args, "t1", stats, threading.Lock())
        self.assertEqual(stats["started"], 1)
        self.assertEqual(stats["done"], 1)
        con = sqlite3.connect(self.db)
        self.assertEqual(
            con.execute("SELECT status FROM jobs").fetchone()[0], "done")
        con.close()


PAYLOAD_MT = json.dumps({
    "fase2": {
        "seguimiento": "¿Y qué me dices del trabajo que mencionaste?",
        "instruccion": ("Responde solo a la nueva pregunta, manteniendo el hilo "
                       "de la lectura anterior y sin repetirla."),
    },
    "carta": "El Loco",
    "contexto": "trabajo",
})

GPT1 = ("El Loco abre un ciclo nuevo en tu vida laboral: incertidumbre fértil, "
        "un paso al vacío que la carta recomienda dar con confianza y humildad.")
GPT2 = ("En cuanto al trabajo, el hilo sigue ahí: esa incertidumbre se resuelve "
        "cuando dejas de pedir permiso y empiezas el proyecto pequeño que ya imaginas.")


class LlamadasFalsas:
    """Simula call_llm registrando los messages de cada llamada."""

    def __init__(self, respuestas, falla_en=None):
        self.respuestas = list(respuestas)
        self.calls = []
        self.falla_en = falla_en

    def __call__(self, base, model, system, user, max_tokens, timeout,
                 retries=2, messages=None):
        idx = len(self.calls)
        msgs = messages if messages is not None else [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        self.calls.append(msgs)
        if self.falla_en == idx:
            raise RuntimeError("caida simulada")
        return self.respuestas[idx]


class WorkerMultiturno(unittest.TestCase):
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
        self.args = argparse.Namespace(
            db=str(self.db), only=None, limit=1, min_chars=10,
            endpoint="http://mock/v1", model="m", timeout=5, out=self.out,
        )
        gs.STOP.clear()

    def _inserta(self, payload, attempts=0):
        con = sqlite3.connect(self.db)
        con.execute(
            "INSERT INTO jobs (bloque, system, prompt, payload, attempts) "
            "VALUES ('multiturno', 'SYS', 'PROMPT1', ?, ?)",
            (payload, attempts),
        )
        con.commit()
        con.close()

    def _corre(self, fake):
        stats = {"done": 0, "failed": 0, "started": 0, "t0": time.time()}
        with mock.patch.object(gs.time, "sleep"), \
                mock.patch.object(gs, "call_llm", fake):
            gs.worker_loop(self.args, "t1", stats, threading.Lock())
        return stats

    def _filas(self):
        filas = []
        for f in sorted(self.out.glob("*.jsonl")):
            with open(f, encoding="utf-8") as fh:
                filas.extend(json.loads(line) for line in fh if line.strip())
        return filas

    def _status(self):
        con = sqlite3.connect(self.db)
        s = con.execute("SELECT status FROM jobs").fetchone()[0]
        con.close()
        return s

    def test_claim_devuelve_payload_al_final(self):
        self._inserta(PAYLOAD_MT)
        con = sqlite3.connect(self.db)
        row = gs.claim(con, "w1")
        con.close()
        self.assertEqual(len(row), 6)
        self.assertEqual(json.loads(row[5])["fase2"]["seguimiento"],
                         "¿Y qué me dices del trabajo que mencionaste?")

    def test_multiturno_dos_llamadas_con_historial(self):
        self._inserta(PAYLOAD_MT)
        fake = LlamadasFalsas([GPT1, GPT2])
        stats = self._corre(fake)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[1], [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "PROMPT1"},
            {"role": "assistant", "content": GPT1},
            {"role": "user", "content": fake.calls[1][3]["content"]},
        ])
        h2 = fake.calls[1][3]["content"]
        self.assertIn("¿Y qué me dices del trabajo", h2)
        self.assertIn("sin repetirla", h2)
        self.assertEqual(stats["done"], 1)

    def test_multiturno_escribe_cinco_mensajes_y_turnos(self):
        self._inserta(PAYLOAD_MT)
        self._corre(LlamadasFalsas([GPT1, GPT2]))
        filas = self._filas()
        self.assertEqual(len(filas), 1)
        convs = filas[0]["conversations"]
        self.assertEqual([c["from"] for c in convs],
                         ["system", "human", "gpt", "human", "gpt"])
        self.assertEqual(convs[4]["value"], GPT2)
        self.assertEqual(filas[0]["turnos"], 2)
        self.assertEqual(self._status(), "done")

    def test_sin_fase2_como_hoy(self):
        self._inserta("{}")
        fake = LlamadasFalsas([GPT1])
        stats = self._corre(fake)
        self.assertEqual(len(fake.calls), 1)
        filas = self._filas()
        self.assertEqual(len(filas[0]["conversations"]), 3)
        self.assertNotIn("turnos", filas[0])
        self.assertEqual(stats["done"], 1)

    def test_fallo_fase2_no_escribe_nada(self):
        self._inserta(PAYLOAD_MT, attempts=2)
        fake = LlamadasFalsas([GPT1], falla_en=1)
        stats = self._corre(fake)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(self._filas(), [])
        self.assertEqual(self._status(), "failed")

    def test_fase1_corta_no_dispara_fase2(self):
        self._inserta(PAYLOAD_MT)
        fake = LlamadasFalsas(["corto"])
        stats = self._corre(fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(stats["failed"], 1)
        self.assertEqual(self._filas(), [])


if __name__ == "__main__":
    unittest.main()
