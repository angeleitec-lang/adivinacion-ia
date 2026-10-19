# Tests de libros_segmentar: capítulos, entidades y troceado de secciones.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest

from libros_segmentar import segmentar


def cuerpo(veces=20):
    return ("Este párrafo de relleno sirve para superar el mínimo de "
            "caracteres de una sección. " * veces).strip()


class Capitulos(unittest.TestCase):
    def test_detecta_markdown_y_capitulos(self):
        texto = ("Introducción general del libro.\n\n"
                 "# CAPÍTULO I\n\n" + cuerpo() + "\n\n"
                 "# CAPÍTULO II\n\n" + cuerpo())
        secciones = segmentar(texto, "tarot", id_libro="libro-1")
        titulos = [s["titulo"] for s in secciones]
        self.assertEqual(titulos, ["Sección 1 — Introducción general del libro",
                                  "CAPÍTULO I", "CAPÍTULO II"])
        self.assertEqual([s["seccion"] for s in secciones], [1, 2, 3])
        self.assertEqual([s["posicion"] for s in secciones], [0, 1, 2])
        self.assertEqual(secciones[0]["id_libro"], "libro-1")
        for seccion in secciones:
            self.assertEqual(seccion["chars"], len(seccion["texto"]))

    def test_detecta_titulo_en_mayusculas(self):
        texto = "Pórtico breve.\n\nEL VIAJE DEL HÉROE\n\n" + cuerpo()
        secciones = segmentar(texto, "general")
        self.assertIn("EL VIAJE DEL HÉROE", [s["titulo"] for s in secciones])

    def test_detecta_romano_con_titulo(self):
        texto = "Nota inicial.\n\nXII. LA MUERTE Y EL RENACER\n\n" + cuerpo()
        secciones = segmentar(texto, "general")
        self.assertIn("XII. LA MUERTE Y EL RENACER",
                      [s["titulo"] for s in secciones])


class Entidades(unittest.TestCase):
    def test_arcanos_mayores_en_tarot(self):
        texto = ("Prólogo del libro.\n\nEl Loco\n\n" + cuerpo() +
                 "\n\nEl Mago\n\n" + cuerpo())
        secciones = segmentar(texto, "tarot")
        titulos = [s["titulo"] for s in secciones]
        self.assertIn("El Loco", titulos)
        self.assertIn("El Mago", titulos)

    def test_signos_y_planetas_en_astrologia(self):
        texto = ("Presentación.\n\nAries\n\n" + cuerpo() +
                 "\n\nMarte\n\n" + cuerpo())
        secciones = segmentar(texto, "astrología")
        titulos = [s["titulo"] for s in secciones]
        self.assertIn("Aries", titulos)
        self.assertIn("Marte", titulos)

    def test_numeros_en_numerologia(self):
        texto = ("Prólogo.\n\n1\n\n" + cuerpo() +
                 "\n\n2\n\n" + cuerpo())
        secciones = segmentar(texto, "numerologia")
        titulos = [s["titulo"] for s in secciones]
        self.assertIn("1", titulos)
        self.assertIn("2", titulos)

    def test_no_detecta_entidades_en_otra_familia(self):
        texto = "Prólogo.\n\nAries\n\n" + cuerpo()
        secciones = segmentar(texto, "general")
        self.assertNotIn("Aries", [s["titulo"] for s in secciones])


class FusionYTroceado(unittest.TestCase):
    def test_funde_seccion_menor_de_400(self):
        texto = ("# Larga\n\n" + cuerpo() +
                 "\n\n# Corta\n\nApenas unas líneas.\n\n"
                 "# Otra\n\n" + cuerpo(30))
        secciones = segmentar(texto, "general")
        titulos = [s["titulo"] for s in secciones]
        self.assertNotIn("Corta", titulos)
        self.assertIn("Apenas unas líneas.", secciones[0]["texto"])

    def test_parte_secciones_mayores_de_12000_con_solape(self):
        parrafo = ("Texto de relleno para forzar el troceado. " * 80).strip()
        texto = "# Larga\n\n" + "\n\n".join([parrafo] * 6)
        secciones = segmentar(texto, "general")
        self.assertGreaterEqual(len(secciones), 2)
        self.assertTrue(secciones[1]["texto"].startswith(
            secciones[0]["texto"][-300:]))
        for seccion in secciones:
            self.assertGreater(seccion["chars"], 400)


if __name__ == "__main__":
    unittest.main()


class TitulosUtiles(unittest.TestCase):
    def test_sin_encabezados_usa_titulos_sinteticos_unicos(self):
        relleno = ("Párrafo de relleno para forzar el troceado. " * 80).strip()
        texto = "\n\n".join([relleno] * 6)
        secciones = segmentar(texto, "general")
        titulos = [s["titulo"] for s in secciones]
        self.assertGreaterEqual(len(titulos), 2)
        self.assertTrue(all(t.startswith("Sección ") for t in titulos))
        self.assertEqual(len(titulos), len(set(titulos)))
        self.assertNotIn("Introducción", titulos)

    def test_introduccion_solo_si_el_texto_lo_dice(self):
        texto = "Introducción\n\n" + cuerpo(30)
        secciones = segmentar(texto, "general")
        self.assertEqual(secciones[0]["titulo"], "Introducción")

    def test_titulo_no_acaba_en_preposicion(self):
        texto = ("CAPÍTULO 1 UNA FRASE MUY LARGA QUE TERMINA EN DE\n\n"
                 + cuerpo(30))
        secciones = segmentar(texto, "general")
        titulo = secciones[0]["titulo"]
        self.assertLessEqual(len(titulo), 80)
        self.assertFalse(titulo.lower().endswith(" de"))


class Cartas(unittest.TestCase):
    def _titulos(self, texto, familia="tarot"):
        return [s["titulo"] for s in segmentar(texto, familia)]

    def test_mayor_en_ingles_con_articulo(self):
        self.assertIn("The Fool", self._titulos("THE FOOL\n\n" + cuerpo(30)))

    def test_mayor_numerado(self):
        self.assertIn("The Fool", self._titulos("0 THE FOOL\n\n" + cuerpo(30)))
        self.assertIn("La Muerte",
                      self._titulos("XIII. La Muerte\n\n" + cuerpo(30), "tarot"))

    def test_menor_en_ingles_y_espanol(self):
        self.assertIn("Ace of Cups",
                      self._titulos("Ace of Cups\n\n" + cuerpo(30)))
        self.assertIn("As de Copas",
                      self._titulos("As de Copas\n\n" + cuerpo(30), "tarot"))

    def test_carta_en_linea_con_cabecera(self):
        texto = ("Chapter 1. Wands\n\n" + cuerpo(30) +
                 "\n\nFigure 5 QUEEN The Queen represents the receptive "
                 "quality. " + cuerpo(30) + "\n\nFigure 6 KING The King "
                 "represents authority. " + cuerpo(30))
        titulos = self._titulos(texto)
        self.assertIn("Queen of Wands", titulos)
        self.assertIn("King of Wands", titulos)

    def test_clave_numerada(self):
        self.assertIn("The Fool",
                      self._titulos("Key 0 represents the beginning. "
                                    + cuerpo(30)))

    def test_familia_astrologia_en_ingles(self):
        titulos = self._titulos("Taurus\n\n" + cuerpo(30), "astrologia")
        self.assertIn("Taurus", titulos)

    def test_numerologia_11_22_33(self):
        texto = ("11\n\n" + cuerpo(30) + "\n\n22\n\n" + cuerpo(30) +
                 "\n\n33\n\n" + cuerpo(30))
        titulos = self._titulos(texto, "numerologia")
        for numero in ("11", "22", "33"):
            self.assertIn(numero, titulos)


class FrenteMateria(unittest.TestCase):
    def test_preambulo_de_creditos_no_da_titulo_sintetico_basura(self):
        portada = ("Tarot para principiantes\n\nÁngel González\n\n"
                   "Copyright © 2020 Ángel González\n"
                   "Todos los derechos reservados\n"
                   "ISBN 978-84-1234-567-8\n\n"
                   "Índice\nIntroducción ....... 3\nCapítulo 1 ..... 7\n\n")
        texto = portada + "# Capítulo 1\n\n" + cuerpo(30)
        secciones = segmentar(texto, "tarot")
        primera = secciones[0]
        self.assertTrue(primera.get("front_matter"))
        self.assertNotIn("Sección", primera["titulo"])
        self.assertNotIn("Copyright", primera["titulo"])
        self.assertNotIn("ISBN", primera["titulo"])
        self.assertNotIn("González", primera["titulo"])
        titulos = [s["titulo"] for s in secciones]
        self.assertIn("Capítulo 1", titulos)

    def test_texto_genuino_sin_cabeceras_conserva_titulo_sintetico(self):
        texto = cuerpo(40)
        secciones = segmentar(texto, "general")
        self.assertTrue(secciones[0]["titulo"].startswith("Sección "))
        self.assertFalse(secciones[0].get("front_matter", False))

    def test_introduccion_real_conserva_su_titulo(self):
        texto = "Introducción\n\n" + cuerpo(30)
        secciones = segmentar(texto, "general")
        self.assertEqual(secciones[0]["titulo"], "Introducción")
        self.assertFalse(secciones[0].get("front_matter", False))

    def test_prologo_real_conserva_su_titulo(self):
        texto = "Prólogo\n\n" + cuerpo(30)
        secciones = segmentar(texto, "general")
        self.assertEqual(secciones[0]["titulo"], "Prólogo")
        self.assertFalse(secciones[0].get("front_matter", False))

    def test_mencion_aislada_de_copyright_no_es_front_matter(self):
        texto = ("El tarot y el copyright en la edición moderna de mazos. "
                 * 30).strip()
        secciones = segmentar(texto, "general")
        self.assertTrue(secciones[0]["titulo"].startswith("Sección "))
        self.assertFalse(secciones[0].get("front_matter", False))

    def test_frase_con_contents_no_es_front_matter(self):
        texto = ("Contents of the cup are poured out by the figure in the "
                 "card, which signals emotional release. " + cuerpo(30))
        secciones = segmentar(texto, "tarot")
        self.assertFalse(secciones[0].get("front_matter", False))
        self.assertTrue(secciones[0]["titulo"].startswith("Sección "))

    def test_frase_con_indice_no_es_front_matter(self):
        texto = ("Indice de masa corporal no tiene relación con el tarot, "
                "pero el Ermitaño sugiere introspección. " + cuerpo(30))
        secciones = segmentar(texto, "tarot")
        self.assertFalse(secciones[0].get("front_matter", False))
        self.assertTrue(secciones[0]["titulo"].startswith("Sección "))

    def test_marcas_ambiguas_sin_marca_legal_no_es_front_matter(self):
        texto = ("La baraja Rider-Waite fue publicada por Rider (published "
                 "by Rider) en 1909; la first edition incluía la Rueda de "
                 "la Fortuna. " + cuerpo(30))
        secciones = segmentar(texto, "tarot")
        self.assertFalse(secciones[0].get("front_matter", False))
        self.assertTrue(secciones[0]["titulo"].startswith("Sección "))

    def test_indice_toc_con_index_si_es_front_matter(self):
        texto = ("Contents Introduction Page 7 THE MINOR ARCANA 23 Chapter "
                 "1. Wands 25 2. Cups 48 3. Swords 71 4. Pentacles 94 "
                 "Index 207")
        secciones = segmentar(texto, "general")
        self.assertTrue(secciones[0].get("front_matter"))
        self.assertNotIn("Sección", secciones[0]["titulo"])

    def test_aviso_internet_archive_si_es_front_matter(self):
        texto = ("This book was produced in EPUB format by the Internet "
                 "Archive. " + cuerpo(20))
        secciones = segmentar(texto, "general")
        self.assertTrue(secciones[0].get("front_matter"))

    def test_intro_en_frase_no_es_titulo_de_introduccion(self):
        from libros_segmentar import _titulo_intro
        self.assertIsNone(_titulo_intro(
            "Introduction of a new cycle: the Fool begins his journey "
            "with trust."))
        self.assertIsNone(_titulo_intro(
            "Introducción general del libro y sus usos."))

    def test_titulo_intro_acepta_numero_y_signos(self):
        from libros_segmentar import _titulo_intro
        self.assertEqual(_titulo_intro("Introducción\n\n" + cuerpo(10)),
                         "Introducción")
        self.assertEqual(_titulo_intro("INTRODUCTION.\n\n" + cuerpo(10)),
                         "Introducción")
        self.assertEqual(_titulo_intro("1. Introduction\n\n" + cuerpo(10)),
                         "Introducción")
        self.assertEqual(_titulo_intro("Prólogo\n\n" + cuerpo(10)), "Prólogo")


class RuidoDeTitulo(unittest.TestCase):
    def test_criterios_de_ruido_ocr(self):
        from libros_segmentar import _titulo_es_ruido
        ruidos = ("CNN", "IMI", "XDI", "VII", "III", "DDD", "RET",
                  "270 THE, TAROT", "308 • THE TAROT", "HAROLD a L££ 1",
                  "sab DDPDDDDDDPDDDDDDIDDD HHH", "¢ PHO", "VPZ 2, Ta")
        for t in ruidos:
            self.assertTrue(_titulo_es_ruido(t), t)

    def test_titulos_legitimos_no_son_ruido(self):
        from libros_segmentar import _titulo_es_ruido
        legitimos = ("THE FOOL", "EL LOCO", "PREFACE", "Chapter 1",
                    "ACE OF CUPS", "XIII", "The High Priestess",
                    "Introducción", "LA MUERTE", "WHEEL OF FORTUNE",
                    "MYSTICISM", "LA TORRE")
        for t in legitimos:
            self.assertFalse(_titulo_es_ruido(t), t)

    def test_linea_ruidosa_no_genera_seccion(self):
        for ruido in ("CNN", "270 THE, TAROT", "HAROLD a L££ 1", "VII"):
            texto = ("Introducción breve del libro.\n\n" + ruido + "\n\n"
                     + cuerpo(30))
            secciones = segmentar(texto, "tarot")
            titulos = [s["titulo"] for s in secciones]
            self.assertNotIn(ruido, titulos)
            self.assertEqual(len(secciones), 1)


class CabecerasRepetidas(unittest.TestCase):
    def test_titulo_repetido_con_cuerpos_minimos_se_demuele(self):
        partes = ["LA MUERTE\n\n" + (cuerpo(2) if i < 2 else cuerpo(30))
                  for i in range(3)]
        texto = "Introducción inicial.\n\n" + "\n\n".join(partes)
        secciones = segmentar(texto, "tarot")
        titulos = [s["titulo"] for s in secciones]
        self.assertNotIn("La Muerte", titulos)
        self.assertEqual(len(secciones), 1)

    def test_repetido_con_cuerpos_grandes_se_conserva(self):
        partes = ["LA TORRE\n\n" + cuerpo(30) for _ in range(3)]
        texto = "Prólogo.\n\n" + "\n\n".join(partes)
        secciones = segmentar(texto, "tarot")
        self.assertIn("La Torre", [s["titulo"] for s in secciones])
        self.assertEqual(len(secciones), 4)

    def test_demolido_se_funde_con_la_anterior(self):
        partes = ["EL DIABLO\n\n" + cuerpo(2) for _ in range(3)]
        texto = "Texto único del capítulo, sin cabecera.\n\n" + "\n\n".join(partes)
        secciones = segmentar(texto, "tarot")
        self.assertEqual(len(secciones), 1)
        self.assertNotIn("El Diablo", [s["titulo"] for s in secciones])
        self.assertIn("relleno", secciones[0]["texto"])
