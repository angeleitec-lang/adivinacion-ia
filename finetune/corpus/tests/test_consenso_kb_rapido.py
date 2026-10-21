"""Tests de la ampliacion T73: extras de pasada rapida, dedup por fuente y
reproceso selectivo de celdas. Cliente simulado, sin LLM real ni red."""
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cartas
import consenso_kb as ck
from llm_client import LLMClient


def _cliente_json(respuesta):
    return LLMClient(simulado=lambda s, u: json.dumps(respuesta))


def _cliente_agrupa_por_texto():
    """Simula un LLM que agrupa afirmaciones de texto normalizado igual."""
    def sim(sistema, usuario):
        grupos = {}
        for m in re.finditer(r"^\[(\d+)\] (.*)$", usuario, flags=re.MULTILINE):
            grupos.setdefault(cartas.norm(m.group(2)), []).append(int(m.group(1)))
        return json.dumps({"grupos": list(grupos.values()),
                          "contradicciones": []})
    return LLMClient(simulado=sim)


def _escribir(ruta, regs):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _leer(ruta):
    out = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if linea:
                out.append(json.loads(linea))
    return out


def _backups(out):
    ruta = os.path.join(out, "consenso.jsonl")
    return sorted(n for n in os.listdir(out)
                 if n.startswith(os.path.basename(ruta) + ".pre-extra"))


def _reg(eid, faceta, fuente, texto, **kw):
    r = {"entidad_id": eid, "faceta": faceta, "fuente_id": fuente,
         "afirmacion": texto}
    r.update(kw)
    return r


class TestDeduplicarPorFuente(unittest.TestCase):
    def test_misma_fuente_mismo_texto_se_fusiona(self):
        base = _reg("e", "f", "s1", "Aries es un signo cardinal de fuego.")
        extra = _reg("e", "f", "s1", "Aries es un signo cardinal de fuego.",
                     origen="mercury-3")
        regs, fus = ck.deduplicar_por_fuente([base, extra])
        self.assertEqual(len(regs), 1)
        self.assertEqual(fus, 1)
        self.assertEqual(regs[0]["extractores"], ["base", "mercury-3"])

    def test_tildes_y_mayusculas_son_equivalentes(self):
        a = _reg("e", "f", "s1", "Júpiter rige el trueno y el viento.")
        b = _reg("e", "f", "s1", "jupiter rige el trueno y el viento",
                 origen="mercury-3")
        regs, fus = ck.deduplicar_por_fuente([a, b])
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["extractores"], ["base", "mercury-3"])

    def test_distinta_fuente_mismo_texto_no_deduplica(self):
        a = _reg("e", "f", "s1", "Texto comun de dos fuentes.")
        b = _reg("e", "f", "s2", "Texto comun de dos fuentes.",
                 origen="mercury-3")
        regs, fus = ck.deduplicar_por_fuente([a, b])
        self.assertEqual(len(regs), 2)
        self.assertEqual(fus, 0)

    def test_misma_fuente_distinto_texto_no_deduplica(self):
        a = _reg("e", "f", "s1", "Aries inicia con energia.")
        b = _reg("e", "f", "s1", "Aries impulsa la delantera.",
                 origen="mercury-3")
        regs, fus = ck.deduplicar_por_fuente([a, b])
        self.assertEqual(len(regs), 2)
        self.assertEqual(fus, 0)

    def test_dominio_identifica_fuente_sin_fuente_id(self):
        a = {"entidad_id": "e", "faceta": "f", "dominio": "d1.es",
             "afirmacion": "Mismo texto de dominio."}
        b = {"entidad_id": "e", "faceta": "f", "dominio": "d1.es",
             "afirmacion": "Mismo texto de dominio.", "origen": "mercury-3"}
        regs, fus = ck.deduplicar_por_fuente([a, b])
        self.assertEqual(len(regs), 1)
        self.assertEqual(fus, 1)

    def test_duplicado_completa_campos_faltantes(self):
        a = _reg("e", "f", "s1", "Aries inicia proyectos con energia y decision.")
        b = _reg("e", "f", "s1", "Aries inicia proyectos con energia y decision.",
                 origen="mercury-3", periodo="moderna")
        regs, _ = ck.deduplicar_por_fuente([a, b])
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0].get("periodo"), "moderna")

    def test_extractores_ordenados_y_unicos(self):
        regs_in = [
            _reg("e", "f", "s1", "Texto.", origen="mercury-3"),
            _reg("e", "f", "s1", "Texto."),
            _reg("e", "f", "s1", "Texto.", origen="mercury-3"),
        ]
        regs, fus = ck.deduplicar_por_fuente(regs_in)
        self.assertEqual(len(regs), 1)
        self.assertEqual(fus, 2)
        self.assertEqual(regs[0]["extractores"], ["base", "mercury-3"])


class TestIndependenciaPorFuente(unittest.TestCase):
    def test_misma_fuente_dos_extractores_no_forma_mayoria(self):
        celdas = {("aries|signo", "personalidad"): [
            _reg("aries|signo", "personalidad", "web1",
                 "Aries se caracteriza por la iniciativa y el coraje.",
                 extractores=["base"]),
            _reg("aries|signo", "personalidad", "web1",
                 "Aries impulsa a tomar la delantera en situaciones nuevas.",
                 extractores=["mercury-3"]),
        ]}
        cliente = _cliente_json({"grupos": [[0, 1]], "contradicciones": []})
        res = ck.construir_consensos(cliente, celdas)[0]
        self.assertEqual(res["mayoritarias"], [])
        self.assertEqual(len(res["unica_fuente"]), 1)
        self.assertEqual(res["unica_fuente"][0]["extractores"],
                         ["base", "mercury-3"])

    def test_dos_fuentes_distintas_si_forman_mayoria(self):
        celdas = {("aries|signo", "personalidad"): [
            _reg("aries|signo", "personalidad", "web1",
                 "Aries se caracteriza por la iniciativa y el coraje.",
                 extractores=["base"]),
            _reg("aries|signo", "personalidad", "libro1",
                 "Aries impulsa a tomar la delantera en situaciones nuevas.",
                 extractores=["mercury-3"]),
        ]}
        cliente = _cliente_json({"grupos": [[0, 1]], "contradicciones": []})
        res = ck.construir_consensos(cliente, celdas)[0]
        self.assertEqual(len(res["mayoritarias"]), 1)
        self.assertEqual(res["mayoritarias"][0]["n_fuentes"], 2)
        self.assertEqual(res["mayoritarias"][0]["extractores"],
                         ["base", "mercury-3"])

    def test_discrepancia_lleva_extractores(self):
        celdas = {("aries|signo", "personalidad"): [
            _reg("aries|signo", "personalidad", "web1",
                 "Aries se caracteriza por la iniciativa y el coraje.",
                 extractores=["base"]),
            _reg("aries|signo", "personalidad", "libro1",
                 "Tauro valora la estabilidad y los placeres sensoriales.",
                 extractores=["mercury-3"]),
        ]}
        cliente = _cliente_json({"grupos": [[0], [1]],
                                "contradicciones": [[0, 1]]})
        res = ck.construir_consensos(cliente, celdas)[0]
        self.assertEqual(len(res["discrepancias"]), 1)
        self.assertEqual(res["discrepancias"][0]["a"]["extractores"], ["base"])
        self.assertEqual(res["discrepancias"][0]["b"]["extractores"],
                         ["mercury-3"])


class TestCLIConExtras(unittest.TestCase):
    def _run(self, d, extra=None, rehacer=False, cliente=None, web_extra=None):
        argv = [
            "--web-afirmaciones", os.path.join(d, "web.jsonl"),
            "--libros-afirmaciones", os.path.join(d, "nada.jsonl"),
            "--out-dir", os.path.join(d, "out"),
            "--workers", "1",
        ]
        if extra:
            argv += ["--extra-afirmaciones"] + extra
        if rehacer:
            argv.append("--rehacer-celdas-con-extra")
        return ck.main(argv, cliente=cliente)

    def test_compatibilidad_sin_extras_ni_flag(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            stats = self._run(d)
            self.assertEqual(stats["celdas"], 1)
            self.assertEqual(stats["extra_entrada"], 0)
            self.assertEqual(stats["rehacer_afectadas"], 0)
            self.assertEqual(_backups(os.path.join(d, "out")), [])

    def test_extra_misma_fuente_no_crea_mayoria(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            extra = os.path.join(d, "extra.jsonl")
            _escribir(extra, [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje.",
                     origen="mercury-3"),
            ])
            stats = self._run(d, extra=[extra])
            self.assertEqual(stats["afirmaciones"], 1)
            self.assertEqual(stats["duplicadas_por_fuente"], 1)
            recs = _leer(os.path.join(d, "out", "consenso.jsonl"))
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["mayoritarias"], [])
            self.assertEqual(len(recs[0]["unica_fuente"]), 1)
            self.assertEqual(recs[0]["unica_fuente"][0]["extractores"],
                             ["base", "mercury-3"])

    def test_extra_de_otra_fuente_si_crea_mayoria(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            extra = os.path.join(d, "extra.jsonl")
            _escribir(extra, [
                _reg("aries|signo", "personalidad", "libro_nuevo",
                     "Aries se caracteriza por la iniciativa y el coraje.",
                     origen="mercury-3"),
            ])
            stats = self._run(d, extra=[extra],
                             cliente=_cliente_agrupa_por_texto())
            recs = _leer(os.path.join(d, "out", "consenso.jsonl"))
            self.assertEqual(len(recs[0]["mayoritarias"]), 1)
            self.assertEqual(recs[0]["mayoritarias"][0]["n_fuentes"], 2)

    def test_celda_sin_cambios_no_se_rehace(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            extra = os.path.join(d, "extra.jsonl")
            _escribir(extra, [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje.",
                     origen="mercury-3"),
            ])
            self._run(d)
            ruta = os.path.join(d, "out", "consenso.jsonl")
            antes = _leer(ruta)
            stats = self._run(d, extra=[extra], rehacer=True)
            self.assertEqual(stats["rehacer_afectadas"], 0)
            self.assertEqual(stats["celdas"], 0)
            self.assertEqual(_backups(os.path.join(d, "out")), [])
            self.assertEqual(_leer(ruta), antes)

    def test_rehacer_sin_extra_no_reprocesa(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            self._run(d)
            stats = self._run(d, rehacer=True)
            self.assertEqual(stats["celdas"], 0)
            self.assertEqual(_backups(os.path.join(d, "out")), [])

    def test_sin_flag_no_se_rehace_celda_que_gana_extra(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
            ])
            extra = os.path.join(d, "extra.jsonl")
            _escribir(extra, [
                _reg("aries|signo", "personalidad", "web2",
                     "Aries inicia proyectos con energia y decision.",
                     origen="mercury-3"),
            ])
            self._run(d)
            ruta = os.path.join(d, "out", "consenso.jsonl")
            antes = _leer(ruta)
            stats = self._run(d, extra=[extra])
            self.assertEqual(stats["celdas"], 0)
            self.assertEqual(stats["rehacer_afectadas"], 0)
            self.assertEqual(_leer(ruta), antes)

    def test_rehacer_solo_toca_celdas_afectadas(self):
        with tempfile.TemporaryDirectory() as d:
            _escribir(os.path.join(d, "web.jsonl"), [
                _reg("aries|signo", "personalidad", "web1",
                     "Aries se caracteriza por la iniciativa y el coraje."),
                _reg("tauro|signo", "personalidad", "web2",
                     "Tauro valora la estabilidad y los placeres sensoriales."),
            ])
            extra = os.path.join(d, "extra.jsonl")
            _escribir(extra, [
                _reg("aries|signo", "personalidad", "web3",
                     "Aries inicia proyectos con energia y decision.",
                     origen="mercury-3"),
            ])
            self._run(d)
            ruta = os.path.join(d, "out", "consenso.jsonl")
            originales = {(r["entidad_id"], r["faceta"]): r
                         for r in _leer(ruta)}
            self.assertEqual(len(originales), 2)

            llamadas = []

            def sim(sistema, usuario):
                llamadas.append(usuario)
                return json.dumps({"grupos": [[0], [1]],
                                  "contradicciones": []})

            stats = self._run(d, extra=[extra], rehacer=True,
                             cliente=LLMClient(simulado=sim))
            self.assertEqual(stats["rehacer_afectadas"], 1)
            self.assertEqual(stats["celdas"], 1)
            self.assertEqual(len(llamadas), 1)
            self.assertIn("aries|signo", llamadas[0])
            self.assertNotIn("tauro|signo", llamadas[0])

            finales = {(r["entidad_id"], r["faceta"]): r for r in _leer(ruta)}
            self.assertEqual(len(finales), 2)
            self.assertEqual(finales["tauro|signo", "personalidad"],
                             originales["tauro|signo", "personalidad"])
            self.assertEqual(
                finales["aries|signo", "personalidad"]["n_afirmaciones"], 2)

            backups = _backups(os.path.join(d, "out"))
            self.assertEqual(len(backups), 1)
            copia = _leer(os.path.join(d, "out", backups[0]))
            self.assertEqual(len(copia), 2)
            self.assertEqual(
                copia[0]["n_afirmaciones"],
                originales["aries|signo", "personalidad"]["n_afirmaciones"])


if __name__ == "__main__":
    unittest.main()
