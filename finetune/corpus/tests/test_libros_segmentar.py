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
        self.assertEqual(titulos, ["Introducción", "CAPÍTULO I", "CAPÍTULO II"])
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
