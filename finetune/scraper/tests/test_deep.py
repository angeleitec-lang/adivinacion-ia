import tempfile
import unittest

import scrapy
from scrapy.http import HtmlResponse

from scraper.spiders import deep

PARRAFOS_ES = (
    "El tarot es una baraja de setenta y ocho cartas dividida en arcanos "
    "mayores y menores que se usa para la introspección y la lectura del futuro.",
    "Cada carta simboliza una situación vital y se interpreta según su "
    "posición en la tirada y su relación con las cartas vecinas del tapete.",
    "Los arcanos mayores representan arquetipos universales como El Loco, "
    "La Sacerdotisa o La Rueda de la Fortuna, base de toda la baraja moderna.",
)

PARRAFOS_IT = (
    "Il tarocco è un mazzo di settantotto carte diviso in arcani maggiori e "
    "minori che si usa per l'introspezione e la lettura del futuro.",
    "Ogni carta simboleggia una situazione vitale e si interpreta secondo la "
    "sua posizione nella stesa e il suo rapporto con le carte vicine del tavolo.",
    "Gli arcani maggiori rappresentano archetipi universali come Il Matto, "
    "La Papessa o La Ruota della Fortuna, base di tutta la moderna.",
)


def _pagina(lang, titulo, parrafos):
    atributo = f' lang="{lang}"' if lang else ""
    cuerpo = "".join(f"<p>{p}</p>" for p in parrafos)
    return (
        f"<html{atributo}><head><title>{titulo}</title></head>"
        f"<body><article><h1>{titulo}</h1>{cuerpo}</article></body></html>"
    )


def _spider():
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write("https://ejemplo.com/\n")
    return deep.DeepSpider(seeds=fh.name, prior="")


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


class TestMarcadoresComercialesAfinados(unittest.TestCase):
    def test_titulos_legitimos_con_palabras_ambiguas_no_se_descartan(self):
        for titulo in (
            "Glosario de términos astrológicos",
            "Astrological terms and definitions",
            "La política y las cartas astrales",
            "Cartomancia y tarot legal en España",
        ):
            self.assertFalse(deep.titulo_descartable(titulo), titulo)

    def test_frases_comerciales_completas_se_descartan(self):
        for titulo in (
            "Términos y condiciones",
            "Política de privacidad",
            "Terms of Service",
            "Aviso legal",
            "Carrito de compra",
        ):
            self.assertTrue(deep.titulo_descartable(titulo), titulo)

    def test_contacto_solo_si_el_titulo_completo_es_la_palabra(self):
        self.assertTrue(deep.titulo_descartable("Contacto"))
        self.assertTrue(deep.titulo_descartable("Contacto | Tarot Mágico"))
        self.assertFalse(deep.titulo_descartable("Contacto con las cartas del tarot"))

    def test_extensiones_de_ruta_comercial_se_saltan(self):
        self.assertFalse(deep.ruta_crawleable("https://ejemplo.com/cart.html"))
        self.assertFalse(deep.ruta_crawleable("https://ejemplo.com/checkout/"))
        self.assertTrue(deep.ruta_crawleable("https://ejemplo.com/carta-astral.html"))


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


class TestIdiomaDePagina(unittest.TestCase):
    def setUp(self):
        self.spider = _spider()

    def _parse(self, body, url):
        request = scrapy.Request(url, meta={"depth": 0})
        resp = HtmlResponse(
            url=url,
            request=request,
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=body.encode("utf-8"),
            encoding="utf-8",
        )
        return [i for i in self.spider.parse(resp) if isinstance(i, dict)]

    def test_italiana_descartada(self):
        body = _pagina("it", "Il tarocco e i suoi significati", PARRAFOS_IT)
        self.assertEqual(self._parse(body, "https://ejemplo.com/pagina"), [])

    def test_control_sin_lang_si_extrae(self):
        body = _pagina(None, "El tarot y sus significados", PARRAFOS_ES)
        self.assertEqual(len(self._parse(body, "https://ejemplo.com/control")), 1)

    def test_es_mx_aceptada_con_lang_normalizado(self):
        body = _pagina("es-MX", "El tarot y sus significados", PARRAFOS_ES)
        items = self._parse(body, "https://ejemplo.com/guia")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["lang"], "es")

    def test_sin_lang_aceptada(self):
        body = _pagina(None, "El tarot y sus significados", PARRAFOS_ES)
        items = self._parse(body, "https://ejemplo.com/otro")
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["lang"])


if __name__ == "__main__":
    unittest.main()
