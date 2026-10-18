"""Tests de generate_synthetic: reset de trabajos y contadores."""
import argparse
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


if __name__ == "__main__":
    unittest.main()
