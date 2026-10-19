#!/usr/bin/env python3
"""Tests de web_extraer: extracción HTML a Markdown con trafilatura."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from web_extraer import extraer, guardar_markdown, _limpiar_ruido


class LimpiarRuidoTests(unittest.TestCase):
    def test_elimina_suscribete(self):
        texto = "hola\nSuscríbete a nuestro boletín\nadiós"
        res = _limpiar_ruido(texto)
        self.assertNotIn("Suscríbete", res)
        self.assertIn("hola", res)
        self.assertIn("adiós", res)

    def test_elimina_compra(self):
        texto = "compra ahora\ncontenido real\nver productos"
        res = _limpiar_ruido(texto)
        self.assertNotIn("compra", res.lower())
        self.assertNotIn("ver productos", res.lower())
        self.assertIn("contenido real", res)

    def test_elimina_lee_tambien(self):
        texto = "artículo\nLee también: otro artículo\nfin"
        res = _limpiar_ruido(texto)
        self.assertNotIn("Lee también", res)
        self.assertIn("artículo", res)
        self.assertIn("fin", res)

    def test_case_insensitive(self):
        texto = "SUSCRÍBETE\nsubscribe\nSuscribete"
        res = _limpiar_ruido(texto)
        self.assertEqual(res.strip(), "")

    def test_conserva_prosa_legitima_corta(self):
        lineas = [
            "La carta anuncia un cambio importante",
            "Es momento de compartir lo vivido",
            "El comprador debe firmar el contrato con calma",
        ]
        res = _limpiar_ruido("\n".join(lineas))
        for linea in lineas:
            self.assertIn(linea, res)

    def test_conserva_prosa_larga_con_palabras_de_ruido(self):
        prosa = ("La compra del mazo nuevo de tarot de Marsella fue una decision "
                 "acertada que trajo muchas horas de lectura compartida entre amigos")
        res = _limpiar_ruido(prosa)
        self.assertIn("compra", res)
        self.assertIn("compartida", res)

    def test_elimina_linea_comercial_corta(self):
        res = _limpiar_ruido("texto bueno\nCompra ahora y ahorra un veinte por ciento\nmás texto")
        self.assertNotIn("Compra ahora", res)
        self.assertIn("texto bueno", res)

    def test_elimina_linea_solo_ruido_aunque_sea_larga(self):
        ruido = ("Suscríbete Compártelo Facebook Twitter Instagram WhatsApp "
                 "Newsletter Boletín Síguenos Suscríbete Compártelo Facebook")
        res = _limpiar_ruido(ruido)
        self.assertEqual(res.strip(), "")

    def test_conserva_prosa_sin_ruido(self):
        res = _limpiar_ruido("El tarot de Marsella tiene setenta y ocho cartas")
        self.assertIn("setenta y ocho", res)


class ExtraerTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "pagina_ok.html"), encoding="utf-8") as f:
            self.html_ok = f.read()
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "pagina_corta.html"), encoding="utf-8") as f:
            self.html_corta = f.read()

    def test_extraccion_ok(self):
        url = "https://ejemplo.com/el-loco"
        res = extraer(self.html_ok, url, entidad_id="sol|aries|planeta_en_signo",
                      faceta="planeta_en_signo", familia="astrologia")
        self.assertIsNotNone(res)
        self.assertGreaterEqual(res["chars"], 1000)
        self.assertIn("El Loco", res["texto_md"])
        self.assertEqual(res["idioma"], "es")
        self.assertEqual(res["front_matter"]["entidad_id"], "sol|aries|planeta_en_signo")
        self.assertEqual(res["front_matter"]["faceta"], "planeta_en_signo")
        self.assertEqual(res["front_matter"]["familia"], "astrologia")
        self.assertEqual(res["front_matter"]["url"], url)

    def test_descarta_corta(self):
        url = "https://ejemplo.com/corta"
        res = extraer(self.html_corta, url)
        self.assertIsNone(res)

    def test_elimina_frases_comerciales(self):
        html = """<html><body><article>
        Contenido principal sobre El Loco. El Loco es la carta número cero del tarot de Marsella y representa el comienzo del viaje del alma. Su número cero indica que aún no está sujeta a las leyes de la secuencia y que guarda en su interior todas las posibilidades del camino. En las lecturas de tarot, esta carta de los arcanos mayores habla de espontaneidad, inocencia y de un salto al vacío que se da con confianza.
        En el plano del amor, El Loco anuncia una relación nueva que nace sin planes previos, con una energía libre e ilusionante. En el trabajo sugiere iniciar un proyecto desde cero, cambiar de rumbo profesional o emprender una actividad que no estaba en los planes. En el dinero invita a no aferrarse a lo material y a confiar en que los recursos llegarán cuando sean necesarios. En la salud señala conviene cuidar la impulsividad y practicar el descanso.
        <p>Suscríbete a nuestro boletín</p>
        <p>Añadir al carrito</p>
        <p>Más contenido sobre el tarot.</p>
        """ + " Contenido adicional para alcanzar el mínimo de caracteres. " * 20 + """
        </article></body></html>"""
        url = "https://ejemplo.com/test"
        res = extraer(html, url)
        self.assertIsNotNone(res)
        self.assertNotIn("Suscríbete", res["texto_md"])
        self.assertNotIn("carrito", res["texto_md"].lower())
        self.assertIn("El Loco", res["texto_md"])
        self.assertIn("tarot", res["texto_md"])

    def test_front_matter_campos(self):
        url = "https://ejemplo.com/el-loco"
        res = extraer(self.html_ok, url, entidad_id="loco|aries|planeta_en_signo",
                      faceta="planeta_en_signo", familia="tarot")
        fm = res["front_matter"]
        self.assertIn("url", fm)
        self.assertIn("dominio", fm)
        self.assertIn("titulo", fm)
        self.assertIn("entidad_id", fm)
        self.assertIn("faceta", fm)
        self.assertIn("familia", fm)
        self.assertIn("idioma", fm)
        self.assertIn("fecha", fm)
        self.assertIn("sha256", fm)
        self.assertIn("licencia_hint", fm)
        self.assertEqual(fm["licencia_hint"], "consultar")
        self.assertEqual(fm["dominio"], "ejemplo.com")
        self.assertEqual(fm["idioma"], "es")


class GuardarMarkdownTests(unittest.TestCase):
    def test_guarda_con_front_matter_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            # Simular extracción (estructura completa como devuelve extraer)
            extraccion = {
                "texto_md": "# Título\n\nContenido de prueba. " * 10,
                "front_matter": {
                    "url": "https://ejemplo.com/test",
                    "dominio": "ejemplo.com",
                    "titulo": "Test",
                    "entidad_id": "test|test|test",
                    "faceta": "test",
                    "familia": "test",
                    "idioma": "es",
                    "fecha": None,
                    "sha256": "abc123",
                    "licencia_hint": "consultar",
                }
            }
            slug = "test-slug"
            path = guardar_markdown(extraccion, out_dir, slug)
            self.assertTrue(path.exists())
            contenido = path.read_text(encoding="utf-8")
            self.assertTrue(contenido.startswith("---"))
            self.assertIn('url: "https://ejemplo.com/test"', contenido)
            self.assertIn("titulo: Test", contenido)
            self.assertIn("sha256: abc123", contenido)
            self.assertIn("licencia_hint: consultar", contenido)
            # Verificar que el contenido está después del segundo ---
            partes = contenido.split("---")
            self.assertEqual(len(partes), 3)
            self.assertIn("Contenido de prueba.", partes[2])


if __name__ == "__main__":
    unittest.main()
