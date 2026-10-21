"""Tests de la exclusion por claves en el consenso (T78).

Cubre --excluir-claves y --rehacer-celdas-con-exclusion de consenso_kb.py
con cliente simulado y tempdirs: nunca se toca el consenso en vivo.
"""

import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import consenso_kb as ck  # noqa: E402
import diagnostico_tarot_libros as diag  # noqa: E402
from llm_client import LLMClient  # noqa: E402

CELDA_SOL = ("tarot-mayor-20", "significado_general")
CELDA_LUNA = ("tarot-mayor-19", "consejo_practico")
TEXTO_SOL = "El Sol representa el exito, la vitalidad y el reconocimiento."
TEXTO_LUNA = "Confia en tu intuicion antes de decidir."

SEC_EXCLUIDA = ("EL SOL EN ARIES",
               "El Sol ilumina todo lo que toca y da vitalidad al consultante.")
SEC_OK = ("LA LUNA EN CANCER",
          "La intuicion fluye en la noche y guia los suenos.")
CITA_EXCLUIDA = "El Sol ilumina todo lo que toca"


def _escribir_jsonl(ruta, regs):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in regs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _leer_jsonl(ruta):
    out = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            s = linea.strip()
            if s:
                out.append(json.loads(s))
    return out


def _seccion(id_libro, titulo, texto):
    return {"id_libro": id_libro, "seccion": titulo, "titulo": titulo,
            "texto": texto, "chars": len(texto), "posicion": 0,
            "front_matter": False}


def _hash_sec(sec):
    return diag.hash_seccion(sec["id_libro"], sec["seccion"], sec["texto"])


def _afirmacion(eid, faceta, fuente, texto, cita):
    return {"entidad_id": eid, "faceta": faceta, "fuente_id": fuente,
            "dominio": "tarot", "periodo": "rws", "calidad": "alta",
            "afirmacion": texto, "cita_original": cita}


def _cliente():
    return LLMClient(simulado=ck._simulado_consenso)


class BaseExclusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.sec_excluida = _seccion("libro-astro", SEC_EXCLUIDA[0],
                                    SEC_EXCLUIDA[1])
        self.sec_ok = _seccion("libro-astro", SEC_OK[0], SEC_OK[1])
        self.sec_rapida = _seccion("libro-rapido", SEC_EXCLUIDA[0],
                                  SEC_EXCLUIDA[1])
        self.dir_sec = os.path.join(self.dir, "secciones")
        os.makedirs(self.dir_sec)
        _escribir_jsonl(os.path.join(self.dir_sec, "libro-astro.jsonl"),
                        [self.sec_excluida, self.sec_ok])
        _escribir_jsonl(os.path.join(self.dir_sec, "libro-rapido.jsonl"),
                        [self.sec_rapida])
        self.ruta_claves = os.path.join(self.dir, "claves.jsonl")
        _escribir_jsonl(self.ruta_claves, [
            {"hash_seccion": _hash_sec(self.sec_excluida),
             "entidad_id": CELDA_SOL[0],
             "faceta": CELDA_SOL[1],
             "n_afirmaciones": 1,
             "motivo": "sol_luna_astrologica"},
            {"hash_seccion": _hash_sec(self.sec_rapida),
             "entidad_id": CELDA_SOL[0],
             "faceta": CELDA_SOL[1],
             "n_afirmaciones": 1,
             "motivo": "sol_luna_astrologica"},
        ])
        self.ruta_afirms = os.path.join(self.dir, "afirms.jsonl")
        self.ruta_web = os.path.join(self.dir, "web.jsonl")
        self.ruta_out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, extra_argv=()):
        argv = ["--libros-afirmaciones", self.ruta_afirms,
               "--web-afirmaciones", self.ruta_web,
               "--out-dir", self.ruta_out,
               "--secciones-dir", self.dir_sec]
        argv.extend(extra_argv)
        return ck.main(argv=argv, cliente=_cliente())

    def _consenso(self):
        return _leer_jsonl(os.path.join(self.ruta_out, "consenso.jsonl"))

    def _linea_celda(self, celda):
        for linea in open(os.path.join(self.ruta_out, "consenso.jsonl"),
                         encoding="utf-8"):
            s = linea.strip()
            if not s:
                continue
            reg = json.loads(s)
            if (reg["entidad_id"], reg["faceta"]) == celda:
                return s
        return None


class TestExclusionBasica(BaseExclusion):
    def test_descarta_afirmacion_de_seccion_excluida(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves])
        self.assertEqual(stats["excluidas_por_clave"], 1)
        self.assertEqual(stats["exclusion_celdas"], 1)
        self.assertEqual(self._consenso(), [])

    def test_sin_flags_no_excluye(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run()
        self.assertEqual(stats.get("excluidas_por_clave", 0), 0)
        celdas = {(r["entidad_id"], r["faceta"]) for r in self._consenso()}
        self.assertIn(CELDA_SOL, celdas)

    def test_cita_ambigua_se_conserva(self):
        sec_eco = _seccion("libro-astro", "ECO DEL SOL",
                          "Recuerda: " + CITA_EXCLUIDA + " cada manana.")
        _escribir_jsonl(os.path.join(self.dir_sec, "libro-astro.jsonl"),
                        [self.sec_excluida, self.sec_ok, sec_eco])
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves])
        self.assertEqual(stats.get("excluidas_por_clave", 0), 0)
        celdas = {(r["entidad_id"], r["faceta"]) for r in self._consenso()}
        self.assertIn(CELDA_SOL, celdas)

    def test_sin_resolver_se_conserva_y_cuenta(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL,
                       "cita que no esta en ninguna seccion del libro"),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves])
        self.assertEqual(stats.get("excluidas_por_clave", 0), 0)
        self.assertEqual(stats["exclusion_sin_resolver"], 1)
        celdas = {(r["entidad_id"], r["faceta"]) for r in self._consenso()}
        self.assertIn(CELDA_SOL, celdas)

    def test_fuente_web_no_se_toca(self):
        _escribir_jsonl(self.ruta_web, [
            _afirmacion(*CELDA_SOL, "blog-ajeno", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves])
        self.assertEqual(stats.get("excluidas_por_clave", 0), 0)
        celdas = {(r["entidad_id"], r["faceta"]) for r in self._consenso()}
        self.assertIn(CELDA_SOL, celdas)

    def test_claves_inexistentes_no_rompe(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run(["--excluir-claves",
                          os.path.join(self.dir, "no-existe.jsonl")])
        self.assertEqual(stats.get("excluidas_por_clave", 0), 0)

    def test_exclusion_por_celda_jsonl(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL,
                       "da vitalidad al consultante"),
        ])
        self._run(["--excluir-claves", self.ruta_claves])
        filas = _leer_jsonl(os.path.join(self.ruta_out,
                                        "exclusion_por_celda.jsonl"))
        self.assertEqual(filas, [{"entidad_id": CELDA_SOL[0],
                                 "faceta": CELDA_SOL[1],
                                 "n_excluidas": 2}])


class TestRehacerConExclusion(BaseExclusion):
    def _baseline(self, regs_sol):
        _escribir_jsonl(self.ruta_afirms, regs_sol)
        _escribir_jsonl(self.ruta_web, [
            _afirmacion(*CELDA_LUNA, "blog-1", TEXTO_LUNA, ""),
        ])
        self._run()

    def test_rehacer_solo_celdas_afectadas(self):
        self._baseline([
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
            _afirmacion(*CELDA_SOL, "libro-ok", TEXTO_SOL,
                       "La intuicion fluye en la noche"),
        ])
        linea_b = self._linea_celda(CELDA_LUNA)
        self.assertIsNotNone(linea_b)
        stats = self._run(["--excluir-claves", self.ruta_claves,
                          "--rehacer-celdas-con-exclusion"])
        self.assertEqual(stats["excluidas_por_clave"], 1)
        self.assertEqual(stats["rehacer_por_exclusion"], 1)
        self.assertEqual(self._linea_celda(CELDA_LUNA), linea_b)
        sol = [r for r in self._consenso()
               if (r["entidad_id"], r["faceta"]) == CELDA_SOL]
        self.assertEqual(len(sol), 1)
        self.assertEqual(sol[0]["n_afirmaciones"], 1)

    def test_copia_previa_existe(self):
        self._baseline([
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        self._run(["--excluir-claves", self.ruta_claves,
                   "--rehacer-celdas-con-exclusion"])
        backups = glob.glob(os.path.join(self.ruta_out,
                                       "consenso.jsonl.pre-exclusion-*"))
        self.assertEqual(len(backups), 1)
        previas = _leer_jsonl(backups[0])
        celdas_prev = {(r["entidad_id"], r["faceta"]) for r in previas}
        self.assertIn(CELDA_SOL, celdas_prev)

    def test_celda_sin_afirmaciones_se_elimina(self):
        self._baseline([
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves,
                          "--rehacer-celdas-con-exclusion"])
        self.assertEqual(stats["exclusion_celdas_eliminadas"], 1)
        celdas = {(r["entidad_id"], r["faceta"]) for r in self._consenso()}
        self.assertNotIn(CELDA_SOL, celdas)
        self.assertIn(CELDA_LUNA, celdas)

    def test_sin_rehacer_la_celda_existente_no_se_toca(self):
        self._baseline([
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL, CITA_EXCLUIDA),
        ])
        linea_a = self._linea_celda(CELDA_SOL)
        stats = self._run(["--excluir-claves", self.ruta_claves])
        self.assertEqual(stats.get("rehacer_por_exclusion", 0), 0)
        self.assertEqual(self._linea_celda(CELDA_SOL), linea_a)


class TestCombinacionConExtra(BaseExclusion):
    def test_extra_de_seccion_excluida_cae_y_ok_dispara_rehacer(self):
        _escribir_jsonl(self.ruta_afirms, [
            _afirmacion(*CELDA_SOL, "libro-astro", TEXTO_SOL,
                        "La intuicion fluye en la noche"),
        ])
        _escribir_jsonl(self.ruta_web, [
            _afirmacion(*CELDA_LUNA, "blog-1", TEXTO_LUNA, ""),
        ])
        self._run()
        ruta_extra = os.path.join(self.dir, "extra.jsonl")
        _escribir_jsonl(ruta_extra, [
            _afirmacion(*CELDA_SOL, "libro-rapido", TEXTO_SOL, CITA_EXCLUIDA),
            _afirmacion(*CELDA_SOL, "libro-extra-ok", TEXTO_SOL,
                        "La intuicion fluye en la noche y guia"),
        ])
        stats = self._run(["--excluir-claves", self.ruta_claves,
                          "--extra-afirmaciones", ruta_extra,
                          "--rehacer-celdas-con-extra",
                          "--rehacer-celdas-con-exclusion"])
        self.assertEqual(stats["excluidas_por_clave"], 1)
        self.assertEqual(stats["rehacer_afectadas"], 1)
        sol = [r for r in self._consenso()
              if (r["entidad_id"], r["faceta"]) == CELDA_SOL]
        self.assertEqual(len(sol), 1)
        self.assertEqual(sol[0]["n_afirmaciones"], 2)


if __name__ == "__main__":
    unittest.main()
