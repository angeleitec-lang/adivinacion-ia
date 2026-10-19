"""Tests del extractor de afirmaciones en español (T29)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import afirmaciones_es as af
import juez


CUERPO = ("El dos de copas representa la unión y el afecto mutuo entre dos "
          "personas; habla de encuentros amorosos y de acuerdos del corazón.")


def _md(url, dominio, cuerpo):
    return "---\nurl: %s\ndominio: %s\n---\n%s" % (url, dominio, cuerpo)


def _seccion_web(url, cuerpo):
    """Sección como la construye juez para páginas web (hash compatible)."""
    return {"url": url, "texto": cuerpo}


def _evidencia(url="https://example.com/dos-copas", dominio="example.com",
              entidad_id="tarot-copas-02", faceta="significado_general",
              cuerpo=CUERPO, hash_seccion=None):
    if hash_seccion is None:
        hash_seccion = juez.hash_seccion(_seccion_web(url, cuerpo))
    return {
        "entidad_id": entidad_id,
        "faceta": faceta,
        "fuente_id": url,
        "dominio": dominio,
        "idioma": "es",
        "periodo": "moderna",
        "calidad": 4,
        "tipo": "web",
        "hash_seccion": hash_seccion,
    }


class LocalizadorTexto(unittest.TestCase):
    """T29.1: localizar el texto de la sección de una evidencia web."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = os.path.join(self.tmp.name, "web")
        dom = os.path.join(self.web, "example.com")
        os.makedirs(dom)
        with open(os.path.join(dom, "dos-copas.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(_md("https://example.com/dos-copas", "example.com",
                        CUERPO))
        self.indice = af.IndiceWeb(self.web)

    def tearDown(self):
        self.tmp.cleanup()

    def test_devuelve_texto_cuando_coincide(self):
        self.assertEqual(af.texto_seccion(_evidencia(), self.indice), CUERPO)

    def test_hash_distinto_devuelve_none(self):
        ev = _evidencia(hash_seccion="f" * 64)
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_dominio_inexistente_devuelve_none(self):
        ev = _evidencia(dominio="noexiste.com")
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_url_no_coincide_devuelve_none(self):
        ev = _evidencia(url="https://example.com/otra-pagina")
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_indice_reutilizable_entre_evidencias(self):
        ev = _evidencia()
        self.assertEqual(af.texto_seccion(ev, self.indice), CUERPO)
        self.assertEqual(af.texto_seccion(ev, self.indice), CUERPO)


if __name__ == "__main__":
    unittest.main()
