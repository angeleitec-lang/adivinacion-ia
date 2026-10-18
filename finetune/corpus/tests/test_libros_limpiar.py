# Tests de libros_limpiar: reglas de limpieza de textos OCR y EPUB.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import unittest

from libros_limpiar import limpiar


class PaginasOcrPocoFiable(unittest.TestCase):
    def test_descarta_pagina_bajo_60(self):
        texto = ("Introduccion valida del libro.\n\n"
                 "Page 3 The text on this page is estimated to be only 27.46% accurate\n"
                 "Texto ilegible de esa pagina OCR.\n\n"
                 "Page 4 The text on this page is estimated to be only 95% accurate\n"
                 "Texto bueno de la pagina cuatro.")
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("ilegible", limpio)
        self.assertIn("Texto bueno de la pagina cuatro", limpio)
        self.assertIn("Introduccion valida", limpio)
        self.assertEqual(inf["paginas_descartadas"], 1)
        self.assertEqual(inf["paginas_total"], 3)

    def test_variante_sin_numero_de_pagina(self):
        texto = ("Antes del aviso.\n"
                 "The text on this page is estimated to be only 45% accurate\n"
                 "Mala calidad, fuera.\n"
                 "Despues del bloque descartado.")
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("Mala calidad", limpio)
        self.assertIn("Despues del bloque", limpio)
        self.assertEqual(inf["paginas_descartadas"], 1)

    def test_coma_decimal(self):
        texto = ("Inicio.\nThe text on this page is estimated to be only 33,2% accurate\n"
                 "Basura OCR.\nFin del libro.")
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("Basura", limpio)
        self.assertEqual(inf["paginas_descartadas"], 1)

    def test_umbral_exacto_se_conserva(self):
        texto = ("Inicio.\nPage 2 The text on this page is estimated to be only 60% accurate\n"
                 "Pagina justa pero util.")
        limpio, inf = limpiar(texto, "es")
        self.assertIn("Pagina justa pero util", limpio)
        self.assertEqual(inf["paginas_descartadas"], 0)


class CabecerasYPies(unittest.TestCase):
    def test_quita_cabecera_repetida(self):
        cabecera = "Cabecera repetida del libro"
        partes = []
        for i in range(8):
            partes.append(cabecera)
            partes.append("Texto con contenido distinto %d." % i)
        limpio, inf = limpiar("\n\n".join(partes), "es")
        self.assertNotIn(cabecera, limpio)
        self.assertEqual(inf["lineas_cabecera_quitadas"], 8)

    def test_quita_numeros_de_pagina(self):
        texto = "Inicio del libro.\n\n    42\n\nPage 43\n\nFinal del texto."
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("42", limpio)
        self.assertNotIn("Page 43", limpio)
        self.assertIn("Final del texto", limpio)
        self.assertGreaterEqual(inf["lineas_cabecera_quitadas"], 2)


class Desguionado(unittest.TestCase):
    def test_une_si_la_palabra_existe(self):
        texto = ("La extraordinaria-\nmente buena noticia. "
                 "extraordinariamente extraordinariamente extraordinariamente.")
        limpio, inf = limpiar(texto, "es")
        self.assertIn("extraordinariamente buena", limpio)
        self.assertEqual(inf["guiones_unidos"], 1)

    def test_conserva_guion_si_la_union_no_existe(self):
        texto = "El color casa-\nverde del jardín."
        limpio, inf = limpiar(texto, "es")
        self.assertIn("casa-\nverde", limpio)
        self.assertEqual(inf["guiones_unidos"], 0)


class Parrafos(unittest.TestCase):
    def test_une_linea_de_margen(self):
        texto = ("Esta frase continúa\ncon el resto de la idea.\n\n"
                 "Párrafo nuevo aquí.\nOtra línea empieza en mayúscula.")
        limpio, inf = limpiar(texto, "es")
        self.assertIn("Esta frase continúa con el resto de la idea.", limpio)
        self.assertIn("Párrafo nuevo aquí.", limpio)
        self.assertIn("Otra línea empieza en mayúscula.", limpio)
        self.assertNotIn("aquí. Otra línea", limpio)


class RuidoOcr(unittest.TestCase):
    def test_quita_control_simbolos_y_letras_aisladas(self):
        texto = ("Título \x07 del ~~~ libro.\n\n"
                 "r a s g o s basura.\n\nTexto final válido.")
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("\x07", limpio)
        self.assertNotIn("~~~", limpio)
        self.assertNotIn("r a s g o s", limpio)
        self.assertIn("Texto final válido", limpio)

    def test_elimina_linea_con_mucho_ruido(self):
        texto = "Texto normal.\n~~~~ |||| 1234 ^^^^\nSigue el texto."
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("||||", limpio)
        self.assertIn("Sigue el texto", limpio)

    def test_ratio_de_palabras_comunes(self):
        texto = ("de la que el en y a los se del las un por con no una su para "
                 "es al lo como más pero sus le ya o este sí porque esta entre "
                 "cuando muy")
        limpio, inf = limpiar(texto, "es")
        self.assertGreaterEqual(inf["ratio_comunes"], 0.30)
        self.assertFalse(inf["calidad_baja"])
        _, inf2 = limpiar("zzz qqq xxx", "es")
        self.assertTrue(inf2["calidad_baja"])


class PortadaEIndice(unittest.TestCase):
    def test_recorta_portada_copyright(self):
        texto = ("All rights reserved.\nISBN 978-1-2345.\n\n"
                 "Capítulo primero con contenido real.\n\nMás texto del capítulo.")
        limpio, inf = limpiar(texto, "es")
        self.assertNotIn("All rights reserved", limpio)
        self.assertIn("Capítulo primero", limpio)

    def test_recorta_indice_final(self):
        cuerpo = "Capítulo con texto real y suficiente.\n\n"
        indice = "\n".join("Entrada%d 12" % i for i in range(40))
        limpio, inf = limpiar(cuerpo + indice, "es")
        self.assertNotIn("Entrada39", limpio)
        self.assertIn("Capítulo con texto real", limpio)


if __name__ == "__main__":
    unittest.main()
