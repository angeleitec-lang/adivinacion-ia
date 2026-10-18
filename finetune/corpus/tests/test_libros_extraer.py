# Tests de libros_extraer: extracción de texto de EPUB con zipfile + lxml.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import io
import tempfile
import unittest
import zipfile

from libros_extraer import epub_a_texto

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0"?>
<package xmlns="http://www/idpf.org/opf/" unique-identifier="uid" version="3.0">
  <manifest>
    <item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="cap2.xhtml" media-type="application/xhtml+xml"/>
    <item id="c1" href="cap1.xhtml" media-type="application/xhtml+xml"/>
    <item id="g" href="gordo.html" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="t"/><itemref idref="c2"/><itemref idref="c1"/></spine>
</package>"""

TITLE = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head>
<body><h1>Mi Libro</h1><p>Portada con <img src="a.png"/> imagen.</p></body></html>"""

CAP2 = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>2</title>
<style>.x{color:red}</style></head>
<body><h2>Capitulo Dos</h2><p>Texto del dos, va el segundo.</p>
<nav>INDICE FALSO</nav><script>var malicioso=1;</script></body></html>"""

CAP1 = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>1</title></head>
<body><h3>Capitulo Uno</h3><p>Texto del uno, va el primero.</p>
<p>Segundo parrafo del uno.</p></body></html>"""


def _epub_bytes(extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", OPF)
        zf.writestr("OEBPS/title.xhtml", TITLE)
        zf.writestr("OEBPS/cap2.xhtml", CAP2)
        zf.writestr("OEBPS/cap1.xhtml", CAP1)
        for nombre, contenido in (extra or {}).items():
            zf.writestr(nombre, contenido)
    return buf.getvalue()


class EpubATexto(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = os.path.join(self.tmp.name, "libro.epub")

    def _escribir(self, extra=None):
        with open(self.ruta, "wb") as fh:
            fh.write(_epub_bytes(extra))

    def test_respeta_el_orden_del_spine(self):
        self._escribir()
        texto, _ = epub_a_texto(self.ruta)
        self.assertLess(texto.index("Mi Libro"), texto.index("Capitulo Dos"))
        self.assertLess(texto.index("Capitulo Dos"), texto.index("Capitulo Uno"))

    def test_encabezados_con_metas(self):
        self._escribir()
        texto, _ = epub_a_texto(self.ruta)
        self.assertIn("# Mi Libro", texto)
        self.assertIn("## Capitulo Dos", texto)
        self.assertIn("### Capitulo Uno", texto)

    def test_ignora_script_style_y_nav(self):
        self._escribir()
        texto, _ = epub_a_texto(self.ruta)
        self.assertNotIn("malicioso", texto)
        self.assertNotIn("color:red", texto)
        self.assertNotIn("INDICE FALSO", texto)

    def test_marca_una_pagina_por_fichero(self):
        self._escribir()
        texto, m = epub_a_texto(self.ruta)
        for numero in range(1, m["n_html"] + 1):
            self.assertIn("Page %d" % numero, texto)
        self.assertEqual(m["n_html"], 3)

    def test_metricas_basicas(self):
        self._escribir()
        texto, m = epub_a_texto(self.ruta)
        self.assertEqual(m["n_html"], 3)
        self.assertEqual(m["n_imagenes"], 1)
        self.assertGreater(m["chars"], 100)
        self.assertFalse(m["drm"])

    def test_drm_detectado_por_encryption(self):
        self._escribir({"META-INF/encryption.xml":
                        "<encryption xmlns='urn:oasis:names:tc:opendocument:xmlns:container'/>"})
        _, m = epub_a_texto(self.ruta)
        self.assertTrue(m["drm"])

    def test_salta_ficheros_mayores_de_6mb(self):
        gordo = "<html><body><p>" + ("relleno largo " * 500000) + "</p></body></html>"
        self._escribir()
        # Reescribir añadiendo el gordo dentro del zip ya escrito no aplica:
        # se incluye en el spine via extra bajo el nombre del item g.
        with zipfile.ZipFile(self.ruta, "a") as zf:
            zf.writestr("OEBPS/gordo.html", gordo)
        _, m = epub_a_texto(self.ruta)
        self.assertEqual(m["n_html"], 3)  # gordo.html supera 6 MB y se omite

    def test_sin_opf_orden_alfabetico(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("zeta.xhtml", "<html><body><p>ZZZ</p></body></html>")
            zf.writestr("alfa.xhtml", "<html><body><p>AAA</p></body></html>")
        ruta = os.path.join(self.tmp.name, "sinf.opf.epub")
        with open(ruta, "wb") as fh:
            fh.write(buf.getvalue())
        texto, m = epub_a_texto(ruta)
        self.assertLess(texto.index("AAA"), texto.index("ZZZ"))
        self.assertEqual(m["n_html"], 2)


if __name__ == "__main__":
    unittest.main()


class AvisosOcr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _extraer(self, cuerpo):
        html = ('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>P</title>'
                '</head><body>%s</body></html>' % cuerpo)
        ruta = os.path.join(self.tmp.name, "pagina.epub")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("page_1.xhtml", html)
        with open(ruta, "wb") as fh:
            fh.write(buf.getvalue())
        texto, _ = epub_a_texto(ruta)
        return texto

    def test_aviso_en_bajo_body_conserva_su_linea(self):
        aviso = ("The text on this page is estimated to be only 20.89% "
                 "accurate")
        texto = self._extraer("<b>%s</b><p>Texto real.</p>" % aviso)
        self.assertIn(aviso, texto)
        self.assertTrue(any(linea.strip() == aviso
                            for linea in texto.splitlines()))
        self.assertIn("Texto real.", texto)

    def test_conserva_span_font_y_texto_suelto(self):
        texto = self._extraer(
            'Texto suelto. <span>Con span.</span>'
            '<font>Y font.</font><p>Párrafo.</p>')
        self.assertIn("Texto suelto.", texto)
        self.assertIn("Con span.", texto)
        self.assertIn("Y font.", texto)
        self.assertIn("Párrafo.", texto)
        self.assertEqual(texto.count("Con span."), 1)
