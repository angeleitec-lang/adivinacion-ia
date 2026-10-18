"""Tests de limpieza y filtros de build_dataset (track T3)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_dataset as bd


class LimpiezaResiduosWikipedia(unittest.TestCase):
    """T3.1: clean_body elimina residuos de citas y edición de Wikipedia."""

    def test_cita_escapada_con_url(self):
        texto = ("dura 25\xa0776 años[\\[1\\]]"
                 "(https://es.wikipedia.org/wiki/A%C3%B1o_plat%C3%B3nico#cite_note-grados-1)")
        limpio = bd.clean_body(texto)
        self.assertNotIn("cite_note", limpio)
        self.assertNotIn("[1]", limpio)
        self.assertIn("dura 25", limpio)

    def test_cita_escapada_punteada(self):
        texto = ". [\\[2\\]](https://es.wikipedia.org/wiki/A%C3%B1o_plat%C3%B3nico#cite_note-2)"
        limpio = bd.clean_body(texto)
        self.assertNotIn("cite_note", limpio)
        self.assertNotIn("[2]", limpio)

    def test_editar_con_parentesis_en_url(self):
        texto = ('[editar](https://es.wikipedia.org/w/index.php?title=Bastos_(naipe)'
                 '&action=edit&section=3 "Editar sección: Baraja española")')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)
        self.assertNotIn("Editar sección", limpio)

    def test_editar_con_corchetes_externos(self):
        texto = ('\\[[editar](https://es.wikipedia.org/w/index.php?title=Oros_(naipe)'
                 '&action=edit&section=3 "Editar sección: Baraja española")\\')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)
        self.assertNotIn("editar", limpio.lower())

    def test_crea_el_articulo_residuo(self):
        texto = ('**[Crea el artículo](https://es.wikipedia.org/w/index.php'
                '?title=Aspecto_(astrolog%C3%ADa)&action=edit)')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)

    def test_residuo_sueltos_action_edit(self):
        texto = '&action=edit&section=4 "Editar sección: Baraja italiana")'
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)

    def test_enlace_normal_se_convierte_a_texto(self):
        texto = ("válido con [un enlace](https://example.com/pagina) y "
                "[\\[3\\]](http://x#cite_note-3) fin.")
        limpio = bd.clean_body(texto)
        self.assertIn("un enlace", limpio)
        self.assertNotIn("http", limpio)
        self.assertNotIn("cite_note", limpio)

    def test_lineas_solo_simbolos_se_eliminan(self):
        self.assertEqual(bd.clean_body("*    **"), "")
        self.assertEqual(bd.clean_body("_ _ _"), "")
        self.assertEqual(bd.clean_body("> >"), "")

    def test_texto_legitimo_se_conserva(self):
        texto = "Frase normal que se conserva intacta."
        self.assertEqual(bd.clean_body(texto), texto)

    def test_cita_numerica_suelta(self):
        texto = "Cita suelta [5] y [\\[7\\]] aquí."
        limpio = bd.clean_body(texto)
        self.assertNotIn("[5]", limpio)
        self.assertNotIn("[7]", limpio)
        self.assertIn("Cita suelta", limpio)
        self.assertIn("aquí", limpio)


class FiltroDeDominio(unittest.TestCase):
    """T3.2: términos fuertes y débiles; los débiles solos no bastan."""

    def test_domain_hits_sigue_devolviendo_set(self):
        self.assertIsInstance(bd.domain_hits("tarot y sol"), set)

    def test_domain_score_devuelve_tupla(self):
        fuertes, debiles = bd.domain_score("tarot y sol")
        self.assertEqual((fuertes, debiles), (1, 1))

    def test_abuela_no_relevante(self):
        frase = ("El sol sale por la casa de mi abuela; leo una carta "
                "mientras mi mano toca la luna del espejo.")
        self.assertFalse(bd.is_relevant("", frase, "", 2))

    def test_debiles_solos_no_bastan(self):
        self.assertFalse(bd.is_relevant("", "sol luna casa mano leo", "", 2))

    def test_tarot_relevante(self):
        frag = ("La Torre invertida es un arcano mayor que, en esta tirada "
               "del tarot, anuncia un cambio brusco tras el cinco de copas.")
        self.assertTrue(bd.is_relevant("", frag, "", 2))

    def test_carta_astral_relevante(self):
        frag = "Sol en Aries en casa 7, trígono a Júpiter."
        self.assertTrue(bd.is_relevant("", frag, "", 2))

    def test_psicometria_serie_tv_no_relevante(self):
        frag = ("Psico es una serie de televisión estadounidense de suspense "
               "estrenada en 2009, protagonizada por una detective que "
               "resuelve crímenes en una pequeña ciudad.")
        self.assertFalse(bd.is_relevant("", frag, "", 2))

    def test_min_terms_cero_desactiva(self):
        self.assertTrue(bd.is_relevant("", "texto sin nada del dominio", "", 0))

    def test_oposicion_sola_no_es_fuerte(self):
        self.assertEqual(bd.domain_score("oposición"), (0, 0))
        self.assertFalse(bd.is_relevant("", "oposición", "", 2))

    def test_oposicion_con_otro_fuerte_si_cuenta(self):
        self.assertEqual(bd.domain_score("oposición y trígono"), (2, 0))


class EncabezadosMalos(unittest.TestCase):
    """T3.3: se comprueba cada segmento de la ruta, no solo el inicio."""

    def test_libro_referencias_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Libro > Referencias"))

    def test_segmento_malo_al_final_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Baraja española > Referencias"))

    def test_vase_tambien_al_final_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Tarot > Véase también"))

    def test_arcanos_loco_aceptado(self):
        self.assertFalse(bd.is_bad_topic("Los arcanos mayores > El Loco"))

    def test_curso_inmersivo_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Curso inmersivo"))

    def test_preguntas_frecuentes_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Preguntas frecuentes"))

    def test_sobre_la_autora_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Sobre la autora"))

    def test_buen_tema_unico_aceptado(self):
        self.assertFalse(bd.is_bad_topic("El Mago"))


class Idioma(unittest.TestCase):
    """T3.8: es_puro descarta portugués e italiano."""

    def test_espanol_normal_es_puro(self):
        texto = ("El tarot es una herramienta de autoconocimiento que usamos "
                 "para reflexionar sobre el pasado, el presente y el futuro, "
                 "pero sin perder de vista las decisiones que tomamos cada día.")
        self.assertTrue(bd.es_puro(texto))

    def test_portugues_fliptarot_no_es_puro(self):
        texto = ("Perguntas mais indicadas para esta tiragem. Uma situação "
                "complexa que precisa de um mapa completo de influências. Cada "
                "carta deve ser lida pela função da posição em que caiu. A "
                "mesma carta muda de foco e nuance conforme a casa que ocupa, "
                "porque a atmosfera geral, a condição central o punto de "
                "partida que atualmente cobre a pergunta.")
        self.assertFalse(bd.es_puro(texto))

    def test_italiano_no_es_puro(self):
        texto = ("I pianeti sono i verbi del cielo e le case sono i "
                "sostantivi. La carta astrale è una mappa della vita "
                "quotidiana, dove ogni aspetto racconta una storia.")
        self.assertFalse(bd.es_puro(texto))

    def test_espanol_con_cita_ingles_latin_es_puro(self):
        texto = ("El oráculo es un espejo del alma. Como decía el viejo adagio "
                "«carpe diem», y nosotros añadimos que el momento presente "
                "guarda la clave de lo que vendrá, pero sin obsesionarse.")
        self.assertTrue(bd.es_puro(texto))


if __name__ == "__main__":
    unittest.main()
