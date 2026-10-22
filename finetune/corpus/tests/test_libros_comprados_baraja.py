# Tests de libros_comprados_baraja (T129): parseo de los dos libros, mapeo a la
# KB de 40 naipes, puerta anti-copia, work-dir, preparación y generación
# determinista de evidencias/afirmaciones. Sin red, sin LLM y sin PDFs reales.
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import shutil
import tempfile
import unittest
from unittest import mock

import libros_comprados_baraja as mod


SALAS = """AS DE OROS
AL DERECHO: Felicidad. Prosperidad. Triunfo.
AL REVÉS: Fortuna. Riquezas. Dinero.

DOS DE OROS
ÁL DERECHO: Obstáculos. Turbación.
AL REVÉS: Cartas. Libros. Documentos.
"""

TIRADAS = """OROS: trabajo y dinero.

As de Oros
Al derecho, siempre es positiva, triunfo y éxito.
Al revés, problemas de dinero o de trabajo.

Rey de Oros
Al derecho, hombre maduro y poderoso.
Al revés, alguien corrupto.

         Al derecho, representa el hogar y la familia.
         Al revés, es mudanza y mal ambiente en el hogar.

Al derecho, anuncia embarazo y creatividad.
Al revés, obstáculos en una relación.

As de Bastos
Al derecho, símbolo fálico y nacimiento.
Al revés, reaparece alguien del pasado.
"""


class TestNormalizacion(unittest.TestCase):
    def test_sin_tildes(self):
        self.assertEqual(mod.sin_tildes("Canción"), "Cancion")

    def test_norm(self):
        self.assertEqual(mod.norm("AL REVÉS:  Dinero."), "al reves dinero")


class TestMapeoKb(unittest.TestCase):
    def test_mapeo_por_rango_y_palo(self):
        self.assertEqual(mod.entidad_de("As", "Oros")[0], "naipe-oros-01")
        self.assertEqual(mod.entidad_de("Sota", "Copas")[0], "naipe-copas-08")
        self.assertEqual(mod.entidad_de("Caballo", "Espadas")[0],
                         "naipe-espadas-09")
        self.assertEqual(mod.entidad_de("Rey", "Bastos")[0], "naipe-bastos-10")

    def test_ocho_y_nueve_fuera_de_kb(self):
        eid, motivo = mod.entidad_de("Ocho", "Oros")
        self.assertIsNone(eid)
        self.assertEqual(motivo, "rango_ocho_ausente_en_kb")
        self.assertIsNone(mod.entidad_de("Nueve", "Copas")[0])


class TestSalas(unittest.TestCase):
    def test_parseo_y_orientaciones(self):
        secciones, metodo, inc = mod.segmentar_salas(SALAS)
        self.assertEqual(len(secciones), 4)
        self.assertEqual(inc, [])
        self.assertEqual(metodo, [])
        self.assertEqual([s["orientacion"] for s in secciones],
                         ["derecho", "reves", "derecho", "reves"])
        self.assertEqual(secciones[0]["entidad_id"], "naipe-oros-01")
        self.assertEqual(secciones[2]["entidad_id"], "naipe-oros-02")

    def test_no_confunde_prosa_en_minusculas(self):
        texto = SALAS + "\nla carta al revés, pronostica infamia.\n"
        secciones, _, _ = mod.segmentar_salas(texto)
        self.assertEqual(len(secciones), 4)
        self.assertIn("infamia", secciones[-1]["texto"])


class TestTiradas(unittest.TestCase):
    def test_bloques_explicitos_y_ordinales(self):
        secciones, metodo, inc = mod.segmentar_tiradas(TIRADAS)
        self.assertEqual(len(secciones), 10)
        self.assertEqual(inc, [])
        self.assertTrue(metodo)
        copas = [s for s in secciones if s["palo"] == "copas"]
        self.assertEqual([s["rango"] for s in copas],
                         ["as", "as", "dos", "dos"])
        self.assertTrue(all(s["metodo"] == "ordinal_ilustracion"
                            for s in copas))

    def test_ignora_al_derecho_en_prosa(self):
        texto = TIRADAS.replace(
            "Al revés, problemas de dinero o de trabajo.",
            "Al revés, problemas de dinero. Las citadas “al derecho” no "
            "cuentan. * Para saber si está del revés, mira el palo.")
        secciones, _, _ = mod.segmentar_tiradas(texto)
        self.assertEqual(len(secciones), 10)


class TestAntiCopia(unittest.TestCase):
    def test_detecta_26_palabras(self):
        libro = " ".join(["palabra%d" % i for i in range(60)])
        copia = " ".join(["palabra%d" % i for i in range(5, 32)])
        self.assertTrue(mod.es_copia_literal(copia, libro))

    def test_permite_20_palabras(self):
        libro = " ".join(["palabra%d" % i for i in range(60)])
        corta = " ".join(["palabra%d" % i for i in range(5, 25)])
        self.assertFalse(mod.es_copia_literal(corta, libro))

    def test_parafrasis_no_es_copia(self):
        libro = "El as de oros anuncia felicidad, prosperidad y triunfo."
        self.assertFalse(mod.es_copia_literal(
            "El as de oros se vincula con alegría y éxito.", libro))


class TestWorkDir(unittest.TestCase):
    def test_rechaza_tuberia_real(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0/libros")
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0/libros/sub")
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0")

    def test_acepta_work_dir_nuevo(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mod.validar_work_dir(tmp), os.path.abspath(tmp))


class TestPreparar(unittest.TestCase):
    def test_crea_estructura_y_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mod, "extraer_texto_pdf") as extraer:
                mod.preparar(tmp)
            self.assertEqual(extraer.call_count, 2)
            for sub in ("crudo", "limpio", "secciones", "evidencias",
                        "knowledge", "afirmaciones", "resumenes"):
                self.assertTrue(os.path.isdir(os.path.join(tmp, sub)))
            ruta = os.path.join(tmp, "knowledge", mod.META_NOMBRE)
            with open(ruta, encoding="utf-8") as fh:
                filas = [json.loads(l) for l in fh]
            self.assertEqual(len(filas), 2)
            self.assertEqual(filas[0]["origen"], "comprado_por_usuario")
            self.assertIn("copyright", filas[0]["licencia_hint"])
            self.assertIn("comprado por el usuario", filas[0]["procedencia"])


class TestDeterminista(unittest.TestCase):
    def _seccion(self, orientacion="derecho"):
        return {
            "id_libro": "libro_salas_baraja", "fuente_id": "libro_salas_baraja",
            "seccion": "libro_salas_baraja:oros:as:" + orientacion,
            "titulo": "As de Oros", "texto": "Felicidad. Prosperidad. Triunfo.",
            "entidad_id": "naipe-oros-01", "rango": "as", "palo": "oros",
            "orientacion": orientacion, "idioma": "es", "metodo": "test",
            "confianza": "alta", "pagina": 1, "chars": 34,
        }

    def test_evidencias_por_orientacion(self):
        ev = mod.evidencias_deterministas([self._seccion()], {})
        facetas = [e["faceta"] for e in ev]
        self.assertEqual(facetas, ["significado_general", "derecha_invertida"])
        self.assertEqual(ev[0]["entidad_id"], "naipe-oros-01")
        self.assertEqual(ev[0]["tipo"], "libro")
        reves = mod.evidencias_deterministas([self._seccion("reves")], {})
        self.assertEqual([e["faceta"] for e in reves],
                         ["derecha_invertida", "luz_sombra"])

    def test_afirmaciones_parafraseadas(self):
        texto = " ".join("clave%d" % i for i in range(40))
        seccion = self._seccion()
        seccion["texto"] = texto
        indice = mod.construir_indice_copia(texto)
        af = mod.afirmaciones_de(seccion, indice, "El arte de echar las cartas")
        self.assertEqual(len(af), 2)
        for item in af:
            self.assertLessEqual(len(item["cita_original"].split()), 20)
            self.assertFalse(mod.es_copia_literal(item["afirmacion"],
                                                  indice=indice))


class TestCobertura(unittest.TestCase):
    def test_informe_40_naipes(self):
        secciones = []
        for eid in mod.INDICE_KB.values():
            for orientacion in ("derecho", "reves"):
                secciones.append({
                    "entidad_id": eid, "fuente_id": "libro_salas_baraja",
                    "orientacion": orientacion,
                })
        inf = mod.informe_cobertura(secciones)
        self.assertEqual(inf["cartas"], 40)
        self.assertEqual(inf["cubiertas_derecho"], 40)
        self.assertEqual(inf["cubiertas_reves"], 40)
        self.assertEqual(inf["faltan"], [])

    def test_detecta_faltantes(self):
        inf = mod.informe_cobertura([])
        self.assertEqual(len(inf["faltan"]), 80)


if __name__ == "__main__":
    unittest.main()
