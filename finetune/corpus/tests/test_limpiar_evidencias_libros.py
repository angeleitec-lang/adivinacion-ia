"""Tests del post-filtro determinista de evidencias de mayores por titulo.

El post-filtro PROPONE quitar evidencias de arcanos mayores cuyo titulo de
seccion ya identifica OTRA carta del tarot. No toca la produccion: solo
clasifica y propone. Reutiliza la clasificacion de titulos del diagnostico.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import diagnostico_tarot_libros as diag
import limpiar_evidencias_libros as lim


def _sec(id_libro, seccion, titulo, texto="cuerpo"):
    return {"id_libro": id_libro, "seccion": seccion, "titulo": titulo,
            "texto": texto}


def _ev(entidad, h, periodo="clasica"):
    return {"entidad_id": entidad, "periodo": periodo, "hash_seccion": h,
            "faceta": "significado_general"}


class IdentificaOtraCarta(unittest.TestCase):
    def setUp(self):
        self.s_sol = _sec("L", 1, "The Sun")
        self.s_luna = _sec("L", 2, "The Moon")
        self.s_as_copas = _sec("L", 3, "Ace of Cups")
        self.s_neutro = _sec("L", 4, "Chapter on symbolism")
        self.secs = [self.s_sol, self.s_luna, self.s_as_copas, self.s_neutro]
        self.h_sol = diag.hash_seccion("L", 1, "cuerpo")
        self.h_luna = diag.hash_seccion("L", 2, "cuerpo")
        self.h_as = diag.hash_seccion("L", 3, "cuerpo")
        self.h_neutro = diag.hash_seccion("L", 4, "cuerpo")

    def test_mayor_cuyo_titulo_es_otra_mayor_se_propone_quitar(self):
        res = lim.propuesta_filtro([_ev("tarot-mayor-20", self.h_luna)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 1)
        self.assertEqual(res["removed"][0]["evidencia"]["entidad_id"],
                         "tarot-mayor-20")
        self.assertEqual(res["removed"][0]["titulo"], "The Moon")
        self.assertEqual(len(res["kept"]), 0)

    def test_mayor_cuyo_titulo_es_otra_menor_se_propone_quitar(self):
        res = lim.propuesta_filtro([_ev("tarot-mayor-20", self.h_as)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 1)
        self.assertEqual(res["removed"][0]["titulo"], "Ace of Cups")

    def test_mayor_cuyo_titulo_es_el_propio_se_conserva(self):
        res = lim.propuesta_filtro([_ev("tarot-mayor-20", self.h_sol)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 0)
        self.assertEqual(len(res["kept"]), 1)

    def test_mayor_titulo_neutro_se_conserva(self):
        res = lim.propuesta_filtro([_ev("tarot-mayor-20", self.h_neutro)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 0)
        self.assertEqual(len(res["kept"]), 1)

    def test_mayor_seccion_no_indexada_se_conserva(self):
        res = lim.propuesta_filtro([_ev("tarot-mayor-20", "f" * 64)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 0)
        self.assertEqual(len(res["kept"]), 1)

    def test_menor_no_se_filtra_aunque_titulo_otra_carta(self):
        # Una menor etiquetada As de Copas con titulo 'The Sun' NO se quita:
        # el post-filtro solo actua sobre mayores.
        res = lim.propuesta_filtro([_ev("tarot-copas-1", self.h_sol)],
                                  self.secs)
        self.assertEqual(len(res["removed"]), 0)
        self.assertEqual(len(res["kept"]), 1)

    def test_no_astro_logico_num_se_filtran(self):
        res = lim.propuesta_filtro(
            [_ev("astro-sol-aries", self.h_luna),
             _ev("numerologia-5", self.h_as)], self.secs)
        self.assertEqual(len(res["removed"]), 0)
        self.assertEqual(len(res["kept"]), 2)


class RecuentoPorCarta(unittest.TestCase):
    def setUp(self):
        self.secs = [
            _sec("L", 1, "The Sun"),
            _sec("L", 2, "The Moon"),
            _sec("L", 3, "Ace of Cups"),
        ]
        self.h_sol = diag.hash_seccion("L", 1, "cuerpo")
        self.h_luna = diag.hash_seccion("L", 2, "cuerpo")
        self.h_as = diag.hash_seccion("L", 3, "cuerpo")

    def test_por_carta_cuenta_quitadas_por_entidad(self):
        evidencias = [
            _ev("tarot-mayor-20", self.h_sol),    # real, se queda
            _ev("tarot-mayor-20", self.h_luna),   # otra, se quita
            _ev("tarot-mayor-20", self.h_as),     # otra, se quita
            _ev("tarot-mayor-19", self.h_luna),   # real, se queda
            _ev("tarot-mayor-19", self.h_sol),    # otra, se quita
        ]
        res = lim.propuesta_filtro(evidencias, self.secs)
        por = res["por_carta"]
        self.assertEqual(por["tarot-mayor-20"]["quitadas"], 2)
        self.assertEqual(por["tarot-mayor-20"]["total_mayor"], 3)
        self.assertEqual(por["tarot-mayor-19"]["quitadas"], 1)
        self.assertEqual(por["tarot-mayor-19"]["total_mayor"], 2)

    def test_totales_cuadran(self):
        evidencias = [
            _ev("tarot-mayor-20", self.h_sol),
            _ev("tarot-mayor-20", self.h_luna),
            _ev("tarot-copas-1", self.h_luna),
        ]
        res = lim.propuesta_filtro(evidencias, self.secs)
        self.assertEqual(res["total"], 3)
        self.assertEqual(res["n_quitadas"], 1)
        self.assertEqual(len(res["kept"]) + len(res["removed"]), 3)


class Pureza(unittest.TestCase):
    def test_no_mutar_entrada(self):
        secs = [_sec("L", 1, "The Moon")]
        h = diag.hash_seccion("L", 1, "cuerpo")
        evs = [_ev("tarot-mayor-20", h)]
        import copy
        antes = copy.deepcopy(evs)
        lim.propuesta_filtro(evs, secs)
        self.assertEqual(evs, antes)


if __name__ == "__main__":
    unittest.main()
