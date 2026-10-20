import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cartas
import diagnostico_tarot_libros as diag


def _ev(entidad, periodo, fuente="libroX", h="h1"):
    return {
        "entidad_id": entidad,
        "faceta": "significado_general",
        "fuente_id": fuente,
        "dominio": fuente,
        "idioma": "en",
        "periodo": periodo,
        "calidad": 3,
        "tipo": "libro",
        "hash_seccion": h,
    }


class TestRecuento(unittest.TestCase):
    def test_recuento_por_carta(self):
        evs = [
            _ev("tarot-mayor-20", "clasica", h="a"),
            _ev("tarot-mayor-20", "clasica", h="b"),
            _ev("tarot-mayor-20", "moderna", h="c"),
            _ev("tarot-mayor-19", "moderna", h="d"),
        ]
        r = diag.recuento_por_carta(evs)
        self.assertEqual(r["tarot-mayor-20"]["total"], 3)
        self.assertEqual(r["tarot-mayor-20"]["clasica"], 2)
        self.assertEqual(r["tarot-mayor-20"]["moderna"], 1)
        self.assertEqual(r["tarot-mayor-19"]["clasica"], 0)

    def test_cartas_sin_clasica_usa_catalogo_completo(self):
        evs = [_ev("tarot-mayor-20", "clasica")]
        faltan = diag.cartas_sin_clasica(evs)
        self.assertIn("tarot-espadas-04", faltan)
        self.assertNotIn("tarot-mayor-20", faltan)
        # las 56 menores deben estar entre las que faltan si no tienen clasica
        self.assertGreaterEqual(len(faltan), 56)


class TestAuditoriaTitulo(unittest.TestCase):
    def test_titulo_real_otra_neutro(self):
        self.assertEqual(diag.clasificar_titulo("The Sun", "sun"), "real")
        self.assertEqual(diag.clasificar_titulo("THE MOON", "moon"), "real")
        self.assertEqual(diag.clasificar_titulo("The Moon", "sun"), "otra")
        self.assertEqual(diag.clasificar_titulo("Ace of Cups", "sun"), "otra")
        self.assertEqual(diag.clasificar_titulo("LESSON THREE", "sun"), "neutro")
        self.assertEqual(diag.clasificar_titulo("MORE ABOUT LIFE", "sun"), "neutro")

    def test_auditar_mayor_clasifica_y_muestra(self):
        secciones = [
            {"seccion": "1", "titulo": "The Sun", "texto": "x", "id_libro": "L"},
            {"seccion": "2", "titulo": "The Moon", "texto": "y", "id_libro": "L"},
            {"seccion": "3", "titulo": "LESSON FIVE", "texto": "z", "id_libro": "L"},
        ]
        idx = diag.indexar_secciones(secciones)
        evs = [
            _ev("tarot-mayor-20", "clasica", h=diag.hash_seccion("L", "1", "x")),
            _ev("tarot-mayor-20", "clasica", h=diag.hash_seccion("L", "2", "y")),
            _ev("tarot-mayor-20", "clasica", h=diag.hash_seccion("L", "3", "z")),
        ]
        res = diag.auditar_mayor(evs, idx, "tarot-mayor-20", "sun")
        self.assertEqual(res["real"], 1)
        self.assertEqual(res["otra"], 1)
        self.assertEqual(res["neutro"], 1)
        self.assertEqual(res["total_clasica"], 3)
        self.assertLessEqual(len(res["muestra"]), 15)


class TestGapMapeoIngles(unittest.TestCase):
    def test_menores_ingles_mapean_tras_arreglo_t53(self):
        # T53 arreglo A: cartas.py YA reconoce menores en ingles.
        self.assertIsNotNone(cartas.normalizar_carta("Two of Swords"))
        self.assertEqual(
            (cartas.normalizar_carta("King of Wands") or {}).get("nombre"),
            "Rey de Bastos")
        self.assertTrue(cartas.extraer_cartas("the King of Wands is here"))
        # En espanol sigue funcionando (control).
        self.assertIsNotNone(cartas.normalizar_carta("Dos de Espadas"))
        self.assertIsNotNone(cartas.normalizar_carta("Rey de Bastos"))

    def test_diagnostico_ya_no_detecta_gap(self):
        gap = diag.gap_mapeo_ingles()
        # Gap cerrado por el arreglo A: el ingles se reconoce.
        self.assertFalse(gap["no_reconoce_ingles"])
        self.assertEqual(gap["ejemplos_no_reconocidos"], [])
        self.assertTrue(gap["reconoce_espanol"])


class TestSeccionesMenoresWaite(unittest.TestCase):
    def test_detecta_titulos_de_menores_ingles(self):
        secciones = [
            {"seccion": "1", "titulo": "Two of Swords", "texto": "a", "id_libro": "W"},
            {"seccion": "2", "titulo": "Page of Wands", "texto": "b", "id_libro": "W"},
            {"seccion": "3", "titulo": "The Fool", "texto": "c", "id_libro": "W"},
            {"seccion": "4", "titulo": "Introduction", "texto": "d", "id_libro": "W"},
        ]
        men = diag.secciones_menores_ingles(secciones)
        titulos = [s["titulo"] for s in men]
        self.assertIn("Two of Swords", titulos)
        self.assertIn("Page of Wands", titulos)
        self.assertNotIn("The Fool", titulos)
        self.assertNotIn("Introduction", titulos)


if __name__ == "__main__":
    unittest.main()
