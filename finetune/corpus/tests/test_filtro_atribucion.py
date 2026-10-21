"""Tests sinteticos del filtro de atribucion T88 (astrologia y numerologia)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import filtro_atribucion as fa


def ev(entidad, h):
    return {"entidad_id": entidad, "faceta": "significado_general",
            "hash_seccion": h}


def idx_uno(h, titulo, url=""):
    return {h: {"titulo": titulo, "url": url, "familia": None}}


class TestNorm(unittest.TestCase):
    def test_quita_tildes(self):
        self.assertEqual(fa.norm("Capricornio"), "capricornio")
        self.assertEqual(fa.norm("Géminis"), "geminis")
        self.assertEqual(fa.norm("ACUARIO"), "acuario")

    def test_nombradas_word_boundary(self):
        self.assertEqual(fa.nombradas("Venus en Leo", fa.SIGNOS), {"leo"})
        # 'porosa' no debe disparar 'oros' (word boundary)
        self.assertEqual(fa.nombradas("una porosa roca", fa.PALOS_ES), set())
        self.assertEqual(fa.nombradas("cinco de oros", fa.PALOS_ES), {"oros"})


class TestSignos(unittest.TestCase):
    def test_venus_en_leo_conserva_leo_signo(self):
        i = idx_uno("h1", "Venus en Leo necesita que el amor sea visto")
        self.assertIsNone(fa.motivo(ev("leo|signo", "h1"), i))

    def test_venus_en_leo_conserva_venus_leo_pes(self):
        i = idx_uno("h1", "Venus en Leo necesita que el amor sea visto")
        self.assertIsNone(fa.motivo(ev("venus|leo|planeta_en_signo", "h1"), i))

    def test_venus_en_leo_retira_acuario_signo(self):
        i = idx_uno("h1", "Venus en Leo necesita que el amor sea visto")
        self.assertEqual(fa.motivo(ev("acuario|signo", "h1"), i),
                         "signo_no_mencionado")

    def test_planeta_en_signo_signo_no_mencionado(self):
        i = idx_uno("h1", "Saturno en Tauro pone al planeta")
        self.assertEqual(fa.motivo(ev("saturno|aries|planeta_en_signo", "h1"), i),
                         "signo_no_mencionado")

    def test_planeta_en_signo_planeta_no_mencionado(self):
        i = idx_uno("h1", "Plutón")
        self.assertEqual(fa.motivo(ev("venus|acuario|planeta_en_signo", "h1"), i),
                         "planeta_no_mencionado")

    def test_planeta_en_casa_planeta_no_mencionado(self):
        i = idx_uno("h1", "El Sol en casa 4")
        self.assertEqual(fa.motivo(ev("luna|casa4|planeta_en_casa", "h1"), i),
                         "planeta_no_mencionado")

    def test_aspecto_planeta_no_mencionado(self):
        i = idx_uno("h1", "Neptuno en Sagitario")
        self.assertEqual(
            fa.motivo(ev("marte|sextil|urano|aspecto", "h1"), i),
            "planeta_no_mencionado")

    def test_aspecto_con_un_planeta_nombrado_se_conserva(self):
        # Limitacion documentada: no se comprueba el TIPO de aspecto,
        # solo que al menos un extremo este nombrado.
        i = idx_uno("h1", "Marte en trigono con Urano")
        self.assertIsNone(fa.motivo(ev("marte|sextil|urano|aspecto", "h1"), i))


class TestTituloGenerico(unittest.TestCase):
    def test_generico_no_retira(self):
        i = idx_uno("h1", "Horoscopo del dia: novedades astrales")
        self.assertIsNone(fa.motivo(ev("leo|signo", "h1"), i))

    def test_sin_meta_no_retira(self):
        self.assertIsNone(fa.motivo(ev("leo|signo", "desconocido"), {}))


class TestFamiliaAjenaNaipes(unittest.TestCase):
    def test_url_baraja_en_celda_astro(self):
        i = idx_uno("h1", "Significado de la carta",
                    "https://x.com/baraja-espanola/as-de-copas")
        self.assertEqual(fa.motivo(ev("leo|signo", "h1"), i),
                         "familia_ajena_naipes")

    def test_titulo_carta_ingles(self):
        i = idx_uno("h1", "Two of Cups")
        self.assertEqual(fa.motivo(ev("venus|tauro|planeta_en_signo", "h1"), i),
                         "familia_ajena_naipes")

    def test_titulo_rank_of_suit(self):
        i = idx_uno("h1", "Six of Pentacles meaning")
        self.assertEqual(fa.motivo(ev("virgo|signo", "h1"), i),
                         "familia_ajena_naipes")

    def test_domino_tarot_no_es_naipes_por_dominio(self):
        # El dominio 'tarot.ac' no debe retirar una pagina de numerologia:
        # el token debe estar en titulo o path, no en el dominio.
        i = idx_uno("h1", "La deuda del trabajo",
                    "https://tarot.ac/es/numerology/numbers/13")
        self.assertIsNone(fa.motivo(ev("4|personalidad", "h1"), i))

    def test_tarot_en_path_si_retira(self):
        i = idx_uno("h1", "Preguntas para tu relacion",
                    "https://mysticanswer.com/blog/questions-to-ask-tarot")
        self.assertEqual(fa.motivo(ev("4|alma", "h1"), i),
                         "familia_ajena_naipes")


class TestNumerologia(unittest.TestCase):
    def test_numero_no_afectado_por_regla_signo(self):
        i = idx_uno("h1", "El numero 7 y su significado")
        self.assertIsNone(fa.motivo(ev("7|camino_de_vida", "h1"), i))

    def test_numero_si_afectado_por_naipes(self):
        i = idx_uno("h1", "Rey de Copas",
                    "https://x.com/cartas/rey-de-copas")
        self.assertEqual(fa.motivo(ev("7|camino_de_vida", "h1"), i),
                         "familia_ajena_naipes")


class TestFueraDeObjetivo(unittest.TestCase):
    def test_tarot_no_se_filtra(self):
        i = idx_uno("h1", "Otra carta distinta")
        self.assertIsNone(fa.motivo(ev("tarot-mayor-01", "h1"), i))

    def test_baraja_no_se_filtra(self):
        i = idx_uno("h1", "otro palo")
        self.assertIsNone(fa.motivo(ev("baraja-copas-as", "h1"), i))


class TestClavesExcluir(unittest.TestCase):
    def test_solo_claves_con_afirmaciones(self):
        retiradas = [dict(ev("acuario|signo", "h1"), motivo="signo_no_mencionado")]
        proc = [{"hash_seccion": "h1", "entidad_id": "acuario|signo",
                "faceta": "significado_general", "n_afirmaciones": 3},
               {"hash_seccion": "h2", "entidad_id": "leo|signo",
                "faceta": "amor", "n_afirmaciones": 5}]
        claves = fa.claves_excluir_consenso(retiradas, proc)
        self.assertEqual(len(claves), 1)
        self.assertEqual(claves[0]["n_afirmaciones"], 3)
        self.assertEqual(claves[0]["motivo"], "signo_no_mencionado")

    def test_sin_afirmaciones_no_excluye(self):
        retiradas = [dict(ev("acuario|signo", "h1"), motivo="signo_no_mencionado")]
        claves = fa.claves_excluir_consenso(retiradas, [])
        self.assertEqual(claves, [])


if __name__ == "__main__":
    unittest.main()
