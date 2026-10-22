"""Tests de T126: reemplazo de originales por lecturas regeneradas (v1d).

Cubren: (1) el snapshot de Tuberia elimina de las fuentes los originales que
sustituyen las regeneradas de una fuente posterior (conserva solo la nueva);
(2) el reemplazo busca el original en cualquier fuente, respeta el orden y
falla si un original o una nueva no aparecen (mapa incoherente con las
fuentes); (3) la huella del snapshot cambia al cambiar el mapa; (4)
mapear_reemplazos une la fuente nueva con la BD de tareas de la pasada y la
BD maestra por (bloque, prompt) exacto, admite varios ids maestros por prompt
y trata como «solo nuevas» las tareas sin original (p. ej. transitos 2026);
(5) el modo CLI --mapear-regeneradas escribe el mapa.
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import armar_dataset_v1 as ad
import merge_final as mf


def _conv(humano, respuesta, system="Eres un lector experto."):
    return [{"from": "system", "value": system},
            {"from": "human", "value": humano},
            {"from": "gpt", "value": respuesta}]


def fila(humano, respuesta, bloque="tarot_1", id_=None):
    return {"conversations": _conv(humano, respuesta),
            "id": id_ or f"{bloque}-x", "bloque": bloque,
            "generador": "mercury-3"}


def fila_plana(prompt, respuesta, bloque="tarot_1", id_=1):
    return {"prompt_user": prompt, "respuesta": respuesta,
            "bloque": bloque, "id": id_, "generador": "mercury-3"}


RESP_OK = ("La carta mostrada habla de un ciclo que se cierra con prudencia; "
           "conviene observar los silencios del consultante antes de actuar, "
           "porque la prisa nubla el juicio y la duda se disipa cuando el "
           "mapa interior esta claro y sin prisa alguna por responder.")


def crear_jobs_db(ruta: Path, filas):
    con = sqlite3.connect(ruta)
    con.execute("create table jobs (id integer primary key, bloque text, "
                "system text, prompt text, payload text, max_tokens integer, "
                "status text)")
    con.executemany("insert into jobs (id, bloque, prompt) values (?,?,?)",
                    filas)
    con.commit()
    con.close()


class TestAplicarReemplazos(unittest.TestCase):
    def _run(self, fuentes, mapa):
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            rutas = []
            for i, filas in enumerate(fuentes, 1):
                r = tp / f"f{i}.jsonl"
                mf.write_jsonl(r, filas)
                rutas.append(r)
            mr = tp / "mapa.jsonl"
            mf.write_jsonl(mr, mapa)
            tub = ad.Tuberia(salida_dir=tp / "out", fuentes=rutas,
                             reemplazos=mr)
            stats = tub.etapa_snapshot()
            snap = mf.load_jsonl(tub._p("00_snapshot", "aceptadas.jsonl"))
            return snap, stats

    def test_reemplaza_original_conserva_solo_la_nueva(self):
        f1 = [fila("p1 vieja", RESP_OK, "tarot_1", 1),
              fila("p2 vieja", RESP_OK, "tarot_1", 2)]
        f2 = [fila_plana("p1 nueva", RESP_OK, "tarot_1", 10)]
        mapa = [{"nuevo": {"id": 10, "bloque": "tarot_1"},
                 "originales": [{"id": 1, "bloque": "tarot_1"}]}]
        snap, stats = self._run([f1, f2], mapa)
        self.assertEqual([(f["bloque"], str(f["id"])) for f in snap],
                         [("tarot_1", "2"), ("tarot_1", "10")])
        self.assertEqual(stats["reemplazos"]["originales_eliminados"], 1)
        self.assertEqual(stats["reemplazos"]["nuevos"], 1)
        self.assertEqual(stats["filas"], 2)

    def test_original_puede_estar_en_cualquier_fuente(self):
        f1 = [fila("p1", RESP_OK, "tarot_1", 1)]
        f2 = [fila("p9", RESP_OK, "astro_natal", 9)]
        f3 = [fila_plana("p9 nueva", RESP_OK, "astro_natal", 99)]
        mapa = [{"nuevo": {"id": 99, "bloque": "astro_natal"},
                 "originales": [{"id": 9, "bloque": "astro_natal"}]}]
        snap, stats = self._run([f1, f2, f3], mapa)
        self.assertEqual({(f["bloque"], str(f["id"])) for f in snap},
                         {("tarot_1", "1"), ("astro_natal", "99")})
        self.assertEqual(stats["reemplazos"]["originales_eliminados"], 1)

    def test_multi_originales_del_mismo_prompt(self):
        f1 = [fila("pA", RESP_OK, "tarot_3", 1),
              fila("pA", RESP_OK, "tarot_3", 2),
              fila("pB", RESP_OK, "tarot_3", 3)]
        f2 = [fila_plana("pA nueva", RESP_OK, "tarot_3", 7)]
        mapa = [{"nuevo": {"id": 7, "bloque": "tarot_3"},
                 "originales": [{"id": 1, "bloque": "tarot_3"},
                                {"id": 2, "bloque": "tarot_3"}]}]
        snap, stats = self._run([f1, f2], mapa)
        self.assertEqual({str(f["id"]) for f in snap}, {"3", "7"})
        self.assertEqual(stats["reemplazos"]["originales_eliminados"], 2)

    def test_id_compartido_no_colisiona_entre_bloques(self):
        f1 = [fila("x", RESP_OK, "tarot_1", 5)]
        f2 = [fila("y", RESP_OK, "tarot_2", 5)]
        f3 = [fila_plana("z", RESP_OK, "tarot_2", 55)]
        mapa = [{"nuevo": {"id": 55, "bloque": "tarot_2"},
                 "originales": [{"id": 5, "bloque": "tarot_2"}]}]
        snap, _ = self._run([f1, f2, f3], mapa)
        self.assertIn(("tarot_1", "5"),
                      [(f["bloque"], str(f["id"])) for f in snap])
        self.assertNotIn(("tarot_2", "5"),
                         [(f["bloque"], str(f["id"])) for f in snap])

    def test_original_inexistente_falla(self):
        f1 = [fila("p1", RESP_OK, "tarot_1", 1)]
        f2 = [fila_plana("p10", RESP_OK, "tarot_1", 10)]
        mapa = [{"nuevo": {"id": 10, "bloque": "tarot_1"},
                 "originales": [{"id": 999, "bloque": "tarot_1"}]}]
        with self.assertRaises(ValueError):
            self._run([f1, f2], mapa)

    def test_nueva_inexistente_falla(self):
        f1 = [fila("p1", RESP_OK, "tarot_1", 1)]
        mapa = [{"nuevo": {"id": 10, "bloque": "tarot_1"},
                 "originales": [{"id": 1, "bloque": "tarot_1"}]}]
        with self.assertRaises(ValueError):
            self._run([f1], mapa)

    def test_sin_mapa_snapshot_igual_que_antes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            f1 = tp / "f1.jsonl"
            mf.write_jsonl(f1, [fila("p1", RESP_OK, "tarot_1", 1)])
            tub = ad.Tuberia(salida_dir=tp / "out", fuentes=[f1])
            stats = tub.etapa_snapshot()
            self.assertNotIn("reemplazos", stats)

    def test_huella_snapshot_cambia_con_el_mapa(self):
        with tempfile.TemporaryDirectory() as tmp:
            tp = Path(tmp)
            f1 = tp / "f1.jsonl"
            mf.write_jsonl(f1, [fila("p1", RESP_OK, "tarot_1", 1)])
            mr = tp / "mapa.jsonl"
            mf.write_jsonl(mr, [])
            t1 = ad.Tuberia(salida_dir=tp / "o1", fuentes=[f1])
            t2 = ad.Tuberia(salida_dir=tp / "o2", fuentes=[f1], reemplazos=mr)
            h1 = t1._definicion_etapas()[0][1]()
            h2 = t2._definicion_etapas()[0][1]()
            self.assertNotEqual(h1, h2)
            mr2 = tp / "mapa2.jsonl"
            mf.write_jsonl(mr2, [{"nuevo": {"id": 2, "bloque": "tarot_1"},
                                  "originales": []}])
            t3 = ad.Tuberia(salida_dir=tp / "o3", fuentes=[f1], reemplazos=mr2)
            h3 = t3._definicion_etapas()[0][1]()
            self.assertNotEqual(h2, h3)


class TestMapearReemplazos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tp = Path(self.tmp.name)
        self.tp = tp
        crear_jobs_db(tp / "maestra.db", [
            (1, "tarot_1", "PROMPT A"),
            (2, "tarot_1", "PROMPT A"),   # prompt duplicado en maestro
            (3, "tarot_1", "PROMPT B"),
            (4, "transitos", "PROMPT VIEJO"),
        ])
        crear_jobs_db(tp / "tareas.db", [
            (7, "tarot_1", "PROMPT A"),
            (8, "tarot_1", "PROMPT B"),
            (9, "transitos", "PROMPT NUEVO SIN ORIGINAL"),
        ])
        self.nueva = tp / "nueva.jsonl"
        mf.write_jsonl(self.nueva, [
            fila_plana("reg A", RESP_OK, "tarot_1", 7),
            fila_plana("reg B", RESP_OK, "tarot_1", 8),
            fila_plana("reg transito", RESP_OK, "transitos", 9),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_mapeo_por_prompt_exacto(self):
        entries, resumen = ad.mapear_reemplazos(
            self.nueva, self.tp / "tareas.db", self.tp / "maestra.db")
        self.assertEqual(len(entries), 2)
        e7 = next(e for e in entries if e["nuevo"]["id"] == 7)
        self.assertEqual(sorted(o["id"] for o in e7["originales"]), [1, 2])
        self.assertEqual(resumen["reemplazos"], 2)
        self.assertEqual(resumen["originales"], 3)
        self.assertEqual(resumen["solo_nuevas"], 1)
        self.assertEqual(resumen["sin_job"], 0)

    def test_bloque_incoherente_cuenta_sin_job(self):
        mf.write_jsonl(self.nueva, [
            fila_plana("reg", RESP_OK, "astro_natal", 7)])
        entries, resumen = ad.mapear_reemplazos(
            self.nueva, self.tp / "tareas.db", self.tp / "maestra.db")
        self.assertEqual(entries, [])
        self.assertEqual(resumen["sin_job"], 1)

    def test_mapa_roundtrip_con_snapshot(self):
        entries, _ = ad.mapear_reemplazos(
            self.nueva, self.tp / "tareas.db", self.tp / "maestra.db")
        mr = self.tp / "mapa.jsonl"
        mf.write_jsonl(mr, entries)
        viejas = self.tp / "viejas.jsonl"
        mf.write_jsonl(viejas, [
            fila("PROMPT A", RESP_OK, "tarot_1", 1),
            fila("PROMPT A", RESP_OK, "tarot_1", 2),
            fila("PROMPT B", RESP_OK, "tarot_1", 3),
        ])
        tub = ad.Tuberia(salida_dir=self.tp / "out",
                        fuentes=[viejas, self.nueva], reemplazos=mr)
        tub.etapa_snapshot()
        snap = mf.load_jsonl(tub._p("00_snapshot", "aceptadas.jsonl"))
        self.assertEqual({(f["bloque"], str(f["id"])) for f in snap},
                         {("tarot_1", "7"), ("tarot_1", "8"),
                          ("transitos", "9")})

    def test_cli_mapear_regeneradas(self):
        salida = self.tp / "mapa_cli.jsonl"
        rc = ad.main([
            "--mapear-regeneradas",
            "--fuente-nueva", str(self.nueva),
            "--db-tareas", str(self.tp / "tareas.db"),
            "--db-maestra", str(self.tp / "maestra.db"),
            "--mapa-salida", str(salida),
        ])
        self.assertEqual(rc, 0)
        entries = mf.load_jsonl(salida)
        self.assertEqual(len(entries), 2)


if __name__ == "__main__":
    unittest.main()
