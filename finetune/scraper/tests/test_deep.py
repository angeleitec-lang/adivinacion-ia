import unittest

from scraper.spiders import deep


class TestTituloDescartable(unittest.TestCase):
    def test_titulos_de_adivinacion_no_se_descartan(self):
        for titulo in (
            "Significado de las cartas del tarot",
            "Carta astral gratis",
            "Carta natal: cómo interpretarla",
            "Cartomancia práctica",
            "El tarot, ¿es ilegal?",
        ):
            self.assertFalse(deep.titulo_descartable(titulo), titulo)

    def test_titulos_comerciales_se_descartan(self):
        for titulo in (
            "Carrito de compra",
            "Política de cookies",
            "Aviso legal",
            "Login de usuario",
            "Checkout seguro",
            "Contacto",
            "Términos y condiciones",
        ):
            self.assertTrue(deep.titulo_descartable(titulo), titulo)

    def test_titulo_vacio_no_se_descarta(self):
        self.assertFalse(deep.titulo_descartable(""))


class TestRutaCrawleable(unittest.TestCase):
    def test_rutas_de_contenido_son_crawleables(self):
        for url in (
            "https://ejemplo.com/carta-astral/",
            "https://ejemplo.com/cartomancia/",
            "https://ejemplo.com/cartas-del-tarot/",
            "https://ejemplo.com/arcanos-mayores/",
        ):
            self.assertTrue(deep.ruta_crawleable(url), url)

    def test_rutas_comerciales_se_saltan(self):
        for url in (
            "https://ejemplo.com/cart/",
            "https://ejemplo.com/carrito",
            "https://ejemplo.com/checkout",
            "https://ejemplo.com/login",
            "https://ejemplo.com/faq/",
        ):
            self.assertFalse(deep.ruta_crawleable(url), url)

    def test_extensiones_binarias_se_saltan(self):
        self.assertFalse(deep.ruta_crawleable("https://ejemplo.com/guia.pdf"))

    def test_is_crawlable_es_alias_de_ruta_crawleable(self):
        self.assertTrue(deep.is_crawlable("https://ejemplo.com/carta-astral/"))
        self.assertFalse(deep.is_crawlable("https://ejemplo.com/cart/"))


if __name__ == "__main__":
    unittest.main()
