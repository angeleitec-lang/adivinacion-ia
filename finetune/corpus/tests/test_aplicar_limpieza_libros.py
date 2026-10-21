"""Tests de la limpieza de evidencias de libros (T71).

Cubre: retirada por Sol/Luna desde libros de astrologia, retirada por titulo
de otra carta (regla T53 reutilizada), retirada de mayores ambiguas desde
sistemas ajenos, conservacion de evidencias correctas, determinismo,
integridad del original y claves de exclusion del consenso.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import aplicar_limpieza_libros as al


def _sec(id_libro, seccion, titulo, texto="cuerpo de la seccion"):
    return {"id_libro": id_libro, "seccion": seccion, "titulo": titulo,
            "texto": texto}


def _hash(sec):
    return hashlib.sha256(
        ("%s|%s|%s" % (sec["id_libro"], sec["seccion"], sec["texto"]))
        .encode("utf-8")).hexdigest()


def _ev(entidad, sec, fuente, faceta="significado_general", calidad=4):
    return {"entidad_id": entidad, "faceta": faceta, "fuente_id": fuente,
            "periodo": "clasica", "idioma": "es", "calidad": calidad,
            "tipo": "libro", "hash_seccion": _hash(sec)}


FAMILIAS = {
    "libro_astro": "astrologia",
    "libro_tarot": "tarot",
    "libro_nume": "numerologia",
    "libro_quiro": "quiromancia",
}


class SolLunaAstrologica(unittest.TestCase):
    def setUp(self):
        self.s = _sec("libro_astro", 1, "THE SUN IN ARIES")
        self.ev_sol = _ev("tarot-mayor-20", self.s, "libro_astro")
        self.ev_luna = _ev("tarot-mayor-19", self.s, "libro_astro")

    def test_retirada_por_sol_desde_astrologia(self):
        res = al.aplicar_limpieza([self.ev_sol], [self.s], FAMILIAS)
        self.assertEqual(len(res["retiradas"]), 1)
        self.assertEqual(res["retiradas"][0]["motivo"], "sol_luna_astrologica")
        self.assertEqual(res["recuento"]["conservadas"], 0)

    def test_retirada_por_luna_desde_astrologia(self):
        res = al.aplicar_limpieza([self.ev_luna], [self.s], FAMILIAS)
        self.assertEqual(res["retiradas"][0]["motivo"], "sol_luna_astrologica")

    def test_otra_carta_desde_astrologia_no_la_regla_sol_luna(self):
        s = _sec("libro_astro", 2, "JUPITER IN LEO")
        ev = _ev("tarot-mayor-01", s, "libro_astro")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        motivos = [r["motivo"] for r in res["retiradas"]]
        self.assertNotIn("sol_luna_astrologica", motivos)


class TituloOtraCarta(unittest.TestCase):
    def test_mayor_con_titulo_de_otra_carta_se_retira(self):
        s = _sec("libro_tarot", 1, "The World")
        ev = _ev("tarot-mayor-01", s, "libro_tarot")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["retiradas"][0]["motivo"], "titulo_otra_carta")

    def test_mayor_con_titulo_propio_se_conserva(self):
        s = _sec("libro_tarot", 2, "La Luna")
        ev = _ev("tarot-mayor-19", s, "libro_tarot")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["recuento"]["retiradas"], 0)
        self.assertEqual(res["kept"], [ev])

    def test_sol_en_libro_tarot_se_conserva(self):
        s = _sec("libro_tarot", 3, "El Sol")
        ev = _ev("tarot-mayor-20", s, "libro_tarot")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["recuento"]["retiradas"], 0)


class MayorSistemaAjeno(unittest.TestCase):
    def test_mayor_19_desde_numerologia(self):
        s = _sec("libro_nume", 1, "CHAPTER XV THE LAW OF VALUES")
        ev = _ev("tarot-mayor-19", s, "libro_nume")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["retiradas"][0]["motivo"], "mayor_sistema_ajeno")

    def test_mayor_20_desde_quiromancia(self):
        s = _sec("libro_quiro", 1, "LA MONTICULO DE JUPITER")
        ev = _ev("tarot-mayor-20", s, "libro_quiro")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["retiradas"][0]["motivo"], "mayor_sistema_ajeno")

    def test_prioridad_sol_luna_sobre_sistema_ajeno(self):
        s = _sec("libro_astro", 4, "MISC")
        ev = _ev("tarot-mayor-19", s, "libro_astro")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        self.assertEqual(res["retiradas"][0]["motivo"], "sol_luna_astrologica")


class Determinismo(unittest.TestCase):
    def setUp(self):
        self.secs = [
            _sec("libro_astro", 1, "THE MOON IN LIBRA"),
            _sec("libro_tarot", 2, "The Sun"),
            _sec("libro_nume", 3, "NUMEROS Y LETRAS"),
        ]
        self.evs = [
            _ev("tarot-mayor-19", self.secs[0], "libro_astro"),
            _ev("tarot-mayor-20", self.secs[1], "libro_tarot"),
            _ev("tarot-mayor-19", self.secs[2], "libro_nume"),
            _ev("tarot-mayor-01", self.secs[1], "libro_tarot"),
        ]

    def _run(self):
        return al.aplicar_limpieza(self.evs, self.secs, FAMILIAS)

    def test_misma_clasificacion_en_dos_pasadas(self):
        a, b = self._run(), self._run()
        self.assertEqual(
            [json.dumps(r, sort_keys=True) for r in a["retiradas"]],
            [json.dumps(r, sort_keys=True) for r in b["retiradas"]])
        self.assertEqual(a["recuento"], b["recuento"])

    def test_muestra_revision_determinista(self):
        res = self._run()
        m1 = al.muestra_revision(res["retiradas"], n=2, semilla=42)
        m2 = al.muestra_revision(res["retiradas"], n=2, semilla=42)
        self.assertEqual(m1, m2)
        m3 = al.muestra_revision(res["retiradas"], n=2, semilla=7)
        self.assertNotEqual(m1, m3)


class ClavesExclusionConsenso(unittest.TestCase):
    def test_claves_de_retiradas_con_afirmaciones(self):
        s = _sec("libro_astro", 1, "THE SUN IN ARIES")
        ev1 = _ev("tarot-mayor-20", s, "libro_astro",
                  faceta="significado_general")
        ev2 = _ev("tarot-mayor-20", s, "libro_astro", faceta="amor")
        res = al.aplicar_limpieza([ev1, ev2], [s], FAMILIAS)
        self.assertEqual(res["recuento"]["retiradas"], 2)
        procesados = [
            {"hash_seccion": _hash(s), "entidad_id": "tarot-mayor-20",
             "faceta": "significado_general", "n_afirmaciones": 3},
            {"hash_seccion": _hash(s), "entidad_id": "tarot-mayor-20",
             "faceta": "amor", "n_afirmaciones": 2},
            {"hash_seccion": "otro_hash", "entidad_id": "tarot-mayor-01",
             "faceta": "amor", "n_afirmaciones": 9},
        ]
        claves = al.claves_excluir_consenso(res["retiradas"], procesados)
        self.assertEqual(len(claves), 2)
        self.assertEqual(sum(c["n_afirmaciones"] for c in claves), 5)
        for c in claves:
            self.assertEqual(c["motivo"], "sol_luna_astrologica")
            self.assertNotEqual(c["entidad_id"], "tarot-mayor-01")

    def test_faceta_no_retirada_no_se_excluye(self):
        s = _sec("libro_tarot", 1, "El Sol")
        ev_sol = _ev("tarot-mayor-20", s, "libro_tarot", faceta="amor")
        res = al.aplicar_limpieza([ev_sol], [s], FAMILIAS)
        procesados = [
            {"hash_seccion": _hash(s), "entidad_id": "tarot-mayor-20",
             "faceta": "amor", "n_afirmaciones": 7},
        ]
        claves = al.claves_excluir_consenso(res["retiradas"], procesados)
        self.assertEqual(claves, [])

    def test_retirada_sin_afirmaciones_no_genera_clave(self):
        s = _sec("libro_astro", 1, "THE SUN IN ARIES")
        ev = _ev("tarot-mayor-20", s, "libro_astro")
        res = al.aplicar_limpieza([ev], [s], FAMILIAS)
        claves = al.claves_excluir_consenso(res["retiradas"], [])
        self.assertEqual(claves, [])


class OriginalIntacto(unittest.TestCase):
    def setUp(self):
        if shutil.which("true") is None:
            self.skipTest("entorno minimo")
        self.tmp = tempfile.mkdtemp()
        self.dir_ev = os.path.join(self.tmp, "evidencias")
        os.makedirs(self.dir_ev)
        self.ruta_ev = os.path.join(self.dir_ev, "evidencias.jsonl")
        secs = [
            _sec("libro_astro", 1, "THE SUN IN ARIES"),
            _sec("libro_tarot", 2, "La Luna"),
        ]
        evs = [
            _ev("tarot-mayor-20", secs[0], "libro_astro"),
            _ev("tarot-mayor-19", secs[1], "libro_tarot"),
        ]
        with open(self.ruta_ev, "w", encoding="utf-8") as fh:
            for e in evs:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        self.dir_secs = os.path.join(self.tmp, "secciones")
        os.makedirs(self.dir_secs)
        with open(os.path.join(self.dir_secs, "secs.jsonl"), "w",
                 encoding="utf-8") as fh:
            for s in secs:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
        self.dir_af = os.path.join(self.tmp, "afirmaciones")
        os.makedirs(self.dir_af)
        with open(os.path.join(self.dir_af, "procesados.jsonl"), "w",
                 encoding="utf-8") as fh:
            fh.write(json.dumps({
                "hash_seccion": _hash(secs[0]), "entidad_id": "tarot-mayor-20",
                "faceta": "significado_general", "n_afirmaciones": 4},
                ensure_ascii=False) + "\n")
        self.dir_out = os.path.join(self.tmp, "libros_limpio")
        self.ruta_fam = os.path.join(self.tmp, "familias.json")
        with open(self.ruta_fam, "w", encoding="utf-8") as fh:
            json.dump(FAMILIAS, fh)
        self.md5_antes = hashlib.md5(
            open(self.ruta_ev, "rb").read()).hexdigest()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_main_no_toca_el_original_y_escribe_salidas(self):
        rc = al.main([
            "--evidencias", self.ruta_ev,
            "--secciones-dir", self.dir_secs,
            "--afirmaciones-dir", self.dir_af,
            "--evidencias-web", os.path.join(self.tmp, "sin_web.jsonl"),
            "--out-dir", self.dir_out,
            "--familias-json", self.ruta_fam,
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(self.md5_antes, hashlib.md5(
            open(self.ruta_ev, "rb").read()).hexdigest())
        for fn in ("evidencias_limpias.jsonl", "evidencias_retiradas.jsonl",
                   "muestra_revision.jsonl", "claves_excluir_consenso.jsonl",
                   "informe_limpieza.json"):
            self.assertTrue(os.path.exists(os.path.join(self.dir_out, fn)),
                            fn)
        limpias = [json.loads(l) for l in open(
            os.path.join(self.dir_out, "evidencias_limpias.jsonl"),
            encoding="utf-8")]
        retiradas = [json.loads(l) for l in open(
            os.path.join(self.dir_out, "evidencias_retiradas.jsonl"),
            encoding="utf-8")]
        self.assertEqual(len(limpias), 1)
        self.assertEqual(len(retiradas), 1)
        self.assertEqual(retiradas[0]["motivo"], "sol_luna_astrologica")
        claves = [json.loads(l) for l in open(
            os.path.join(self.dir_out, "claves_excluir_consenso.jsonl"),
            encoding="utf-8")]
        self.assertEqual(len(claves), 1)
        self.assertEqual(claves[0]["n_afirmaciones"], 4)


if __name__ == "__main__":
    unittest.main()
