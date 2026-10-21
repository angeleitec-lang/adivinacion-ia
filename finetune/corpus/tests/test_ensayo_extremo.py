#!/usr/bin/env python3
"""Tests del ensayo extremo de la fase 1 (T70).

Cubren: ensayo completo sobre una muestra pequena que termina con el semaforo
esperado, deteccion de una etapa rota (simulada) y aislamiento (no escribe fuera
del directorio temporal ni toca la BD real ni corpus/final).
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ensayo_extremo as ee  # noqa: E402


def lector_roto(sistema, usuario):
    """Lector simulado que viola los vedados: promesas y juego."""
    return "Te prometo que ganaras la loteria: es seguro y garantizado."


class AdaptadorShareGPTTest(unittest.TestCase):
    def test_adapta_registro_del_ejecutor(self):
        fila = {
            "id": 7,
            "bloque": "tarot_1",
            "prompt_system": "Eres un lector de tarot.",
            "prompt_user": "Carta: El Loco",
            "respuesta": "El Loco abre un camino nuevo.",
        }
        out = ee.adaptar_a_sharegpt(fila)
        roles = [c["from"] for c in out["conversations"]]
        self.assertEqual(roles, ["system", "human", "gpt"])
        self.assertEqual(out["bloque"], "tarot_1")
        self.assertEqual(out["id"], 7)

    def test_normaliza_nfc(self):
        nfd = "cafe\u0301"  # 'café' descompuesto
        fila = {
            "id": 1,
            "bloque": "etica",
            "prompt_system": "",
            "prompt_user": nfd,
            "respuesta": nfd,
        }
        out = ee.adaptar_a_sharegpt(fila)
        for turno in out["conversations"]:
            self.assertEqual(turno["value"], "caf\u00e9")
        roles = [c["from"] for c in out["conversations"]]
        self.assertEqual(roles, ["human", "gpt"])


class EnsayoCompletoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="t70_test_")
        self.base = Path(self._tmp.name) / "ensayo"

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensayo_20_tareas_termina_con_semaforo_esperado(self):
        resumen = ee.ejecutar_ensayo(self.base, n_tareas=20)
        self.assertEqual(resumen["seleccion"]["total"], 20)
        self.assertGreaterEqual(len(resumen["seleccion"]["por_bloque"]), 10)
        self.assertGreater(resumen["fusion"]["train"], 0)
        self.assertGreater(resumen["fusion"]["val"], 0)
        self.assertIn(
            resumen["preparacion"]["semaforo"], ("amarillo", "verde")
        )
        self.assertEqual(resumen["fallos"], [])
        for d in resumen["desajustes"]:
            self.assertIn("reproduccion", d)
            self.assertIn("parche", d)

    def test_detecta_etapa_rota(self):
        resumen = ee.ejecutar_ensayo(self.base, n_tareas=8, lector=lector_roto)
        self.assertEqual(resumen["ejecutor"]["aceptadas"], 0)
        self.assertTrue(resumen["fallos"])
        self.assertTrue(
            any("ejecutor" in f for f in resumen["fallos"]),
            f"se esperaba un fallo de ejecutor en {resumen['fallos']}",
        )

    def test_no_escribe_fuera_del_temporal(self):
        db_real = ee.DB_REAL
        stat_antes = db_real.stat()
        final_dir = db_real.parent / "final"
        antes = (
            sorted(p.name for p in final_dir.iterdir())
            if final_dir.exists()
            else None
        )
        ee.ejecutar_ensayo(self.base, n_tareas=10)
        stat_despues = db_real.stat()
        self.assertEqual(stat_despues.st_size, stat_antes.st_size)
        self.assertEqual(stat_despues.st_mtime, stat_antes.st_mtime)
        despues = (
            sorted(p.name for p in final_dir.iterdir())
            if final_dir.exists()
            else None
        )
        self.assertEqual(despues, antes)
        for sub in ("jobs_ensayo.db", "ejecutor", "validacion",
                   "dataset_ensayo", "preparado"):
            self.assertTrue((self.base / sub).exists(), sub)


if __name__ == "__main__":
    unittest.main()
