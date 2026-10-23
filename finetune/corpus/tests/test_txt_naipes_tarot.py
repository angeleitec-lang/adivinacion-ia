# -*- coding: utf-8 -*-
"""Tests de T132: txt_naipes_tarot (limpieza, segmentacion, cobertura, puertas)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import txt_naipes_tarot as mod


class TestValidarWorkDir(unittest.TestCase):
    def test_rechaza_libros_comprados(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0/libros")
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0/libros/x")

    def test_rechaza_fase0_entero(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir("/Users/angelgonzalez/fase0")

    def test_acepta_tmp(self):
        tmp = tempfile.mkdtemp()
        try:
            self.assertEqual(mod.validar_work_dir(tmp), os.path.abspath(tmp))
        finally:
            shutil.rmtree(tmp)


class TestNormas(unittest.TestCase):
    def test_norm_linea_sin_tildes(self):
        self.assertEqual(mod.norm_linea("La Justicia"), "LAJUSTICIA")
        self.assertEqual(mod.norm_linea("EL ERMITAÑO"), "ELERMITANO")

    def test_cabecera_con_digitos_de_pagina(self):
        self.assertTrue(mod.cabecera_coincide("12 EL MAGO 34", "ELMAGO"))
        self.assertFalse(mod.cabecera_coincide("EL MAGO DE LA BRUJA", "ELMAGO"))


class TestCalidad(unittest.TestCase):
    def test_texto_limpio_vs_basura(self):
        bueno = mod.medir_calidad("La carta del loco simboliza el inicio del viaje")
        malo = mod.medir_calidad("MEA A E E ||| 3 nn MEA")
        self.assertGreater(bueno["real_word_ratio"], 0.7)
        self.assertLess(malo["real_word_ratio"], 0.3)


class TestLimpieza(unittest.TestCase):
    def test_hifenacion_se_ue(self):
        out = mod.unir_hifenacion(["en-", "tre las barajas"])
        self.assertEqual(out, ["entre las barajas"])

    def test_hifenacion_no_ue_mayuscula(self):
        out = mod.unir_hifenacion(["En-", "Las barajas"])
        self.assertEqual(out, ["En-", "Las barajas"])

    def test_quita_paginas_y_headers_altaya(self):
        texto = ("12\n"
                "LOS NAIPES Y SUS SECRETOS\n"
                "10S NAIPES Y SUS SECRE1OS\n"
                "NAIPES\n"
                "Y SUS SECRETOS\n"
                "Texto legitimo sobre los ases.\n")
        limpio = mod.limpiar(texto, "altaya_naipes")
        self.assertNotIn("SECRETOS", limpio)
        self.assertNotIn("NAIPES", limpio)
        self.assertIn("Texto legitimo", limpio)

    def test_quita_headers_compendium(self):
        texto = ("7 | COMPENDIUM TAROT MEXICANUS\n"
                "LA MIRADA DE FRIEDA HARRIS\n"
                "ALEJANDRA MAYTÉ IBÁÑEZ\n"
                "El Loco representa el aire.\n")
        limpio = mod.limpiar(texto, "compendium_tarot_mexicanus")
        self.assertNotIn("COMPENDIUM", limpio)
        self.assertNotIn("FRIEDA", limpio)
        self.assertIn("El Loco representa", limpio)

    def test_no_toca_cabeceras_de_arcano(self):
        texto = "EL MAGO\nContenido del mago.\n"
        limpio = mod.limpiar(texto, "altaya_naipes")
        self.assertIn("EL MAGO", limpio)


class TestTroceo(unittest.TestCase):
    def test_max_chars(self):
        parrafos = ["p" * 2000] * 5
        partes = mod._trocear_por_parrafos("\n\n".join(parrafos), 5500)
        for p in partes:
            self.assertLessEqual(len(p), 5500)
        self.assertEqual(sum(len(p) for p in partes),
                         sum(len(x) for x in parrafos) + 2 * (len(partes) - 1))

    def test_parrafo_gigante_se_corta(self):
        partes = mod._trocear_por_parrafos("x" * 12000, 5500)
        self.assertTrue(all(len(p) <= 5500 for p in partes))
        self.assertEqual("".join(partes), "x" * 12000)


MINI_ALTAYA = """Indice
Los naipes y sus secretos
12
Los naipes y su diseño han sufrido escasas variaciones.
Al estudiar los ases de las barajas de juego puede observarse
una clara diferenciacion entre las barajas latinas.
LOS REYES
DE LA BARAJA
Reyes de corazones y demas figuras.
REINAS Y DAMAS
Las reinas solo aparecen en las barajas francesas.
JOTAS, VALETS
Y BUBES
Valets y jotas de la baraja.
REYES, CABALLOS
Y SOTAS
Sotas y caballos latinos.
LAS CARTAS
NUMERALES
Las cartas numerales.
OS ARCANOS
MAYORES
Introduccion a los arcanos mayores del tarot.
EL MAGO
Contenido del mago.
LA PAPISA
Contenido de la papisa.
LA EMPERATRIZ
Contenido de la emperatriz.
EL EMPERADOR
Contenido del emperador.
EL PAPA
Contenido del papa.
LOS ENAMORADOS
Contenido de los enamorados.
EL CARRO
Contenido del carro.
LA JUSTICIA
Contenido de la justicia.
EL ERMITAÑO
Contenido del ermitano.
LA RUEDA
DE LA FORTUNA
Contenido de la rueda.
LA FUERZA
Contenido de la fuerza.
EL COLGADO
Contenido del colgado.
LA MUERTE
Contenido de la muerte.
LA TEMPLANZA
Contenido de la templanza.
EL DIABLO
Contenido del diablo.
LA TORRE
Contenido de la torre.
LA ESTRELLA
Contenido de la estrella.
LA LUNA
Contenido de la luna.
EL SOL
Contenido del sol.
EL JUICIO
Contenido del juicio.
EL MUNDO
Contenido del mundo.
EL Loco
Contenido del loco.
"""


class TestSegmentarAltaya(unittest.TestCase):
    def setUp(self):
        limpio = mod.limpiar(MINI_ALTAYA, "altaya_naipes")
        self.secs = mod.segmentar_altaya(limpio)

    def test_arcanos_mapeados(self):
        por_entidad = {s["entidad_id"]: s for s in self.secs if s["entidad_id"]}
        self.assertEqual(len(por_entidad), 22)
        self.assertEqual(por_entidad["tarot-mayor-01"]["titulo"], "El Loco")
        self.assertEqual(por_entidad["tarot-mayor-02"]["titulo"], "El Mago")
        self.assertEqual(por_entidad["tarot-mayor-12"]["titulo"], "La Justicia")
        self.assertEqual(por_entidad["tarot-mayor-10"]["titulo"], "El Ermitaño")

    def test_justicia_no_es_la_intro(self):
        just = [s for s in self.secs if s.get("entidad_id") == "tarot-mayor-12"]
        self.assertEqual(len(just), 1)
        self.assertIn("Contenido de la justicia", just[0]["texto"])

    def test_mixtos_sin_entidad(self):
        mixtas = [s for s in self.secs if not s.get("entidad_id")]
        claves = [s["seccion"] for s in mixtas]
        self.assertTrue(any("los_ases" in c for c in claves))
        self.assertTrue(any("reyes_caballos_sotas" in c for c in claves))
        for s in mixtas:
            if "introduccion" in s["seccion"]:
                self.assertEqual(s["motivo_sin_entidad"],
                                 "capitulo_general_no_carta")
            else:
                self.assertEqual(s["motivo_sin_entidad"],
                                 "capitulo_mixto_no_carta")

    def test_texto_arranca_en_intro(self):
        intro = [s for s in self.secs if "introduccion" in s["seccion"]][0]
        self.assertTrue(intro["texto"].startswith("Los naipes y su diseño"))


MINI_COMPENDIUM = "\n".join(
    ["Indice de capitulos"] * 5 + ["linea corta"] * 400 + [
        "Capítulo I. La mirada de Frieda Harris",
        "El Loco de Thoth representa el aire puro.",
        "Mas contenido util sobre simbolismo.",
        "BIBLIOGRAFIA",
        "Libro citado uno.",
        "Capítulo II. Tiradas Sagradas",
        "Correspondencias entre hebreo y arcanos.",
    ])


class TestSegmentarCompendium(unittest.TestCase):
    def setUp(self):
        self.secs = mod.segmentar_compendium(MINI_COMPENDIUM)

    def test_descarta_toc_y_bibliografia(self):
        for s in self.secs:
            self.assertNotIn("Indice", s["texto"])
            self.assertNotIn("Libro citado", s["texto"])

    def test_capitulos_presentes(self):
        titulos = " ".join(s["titulo"] for s in self.secs)
        self.assertIn("La mirada de Frieda Harris", titulos)
        self.assertIn("Tiradas Sagradas", titulos)
        self.assertTrue(all(s["sistema"] == "tarot" for s in self.secs))


class TestPuertaCopia(unittest.TestCase):
    def setUp(self):
        self.wd = tempfile.mkdtemp()
        mod.validar_work_dir(self.wd)
        os.makedirs(os.path.join(self.wd, "limpio"))
        os.makedirs(os.path.join(self.wd, "afirmaciones"))
        referencia = " ".join("palabra%d" % i for i in range(40))
        with open(os.path.join(self.wd, "limpio", "altaya_naipes.txt"),
                 "w", encoding="utf-8") as fh:
            fh.write(referencia)
        copia = {"entidad_id": "tarot-mayor-01", "fuente_id": "altaya_naipes",
                "afirmacion": "El loco dice " + referencia[:len(referencia)],
                "cita_original": "x"}
        legitima = {"entidad_id": "tarot-mayor-01",
                   "fuente_id": "altaya_naipes",
                   "afirmacion": "El loco simboliza un comienzo sin ataduras.",
                   "cita_original": "El loco simboliza un comienzo."}
        with open(os.path.join(self.wd, "afirmaciones",
                              "afirmaciones_libros.jsonl"),
                 "w", encoding="utf-8") as fh:
            fh.write(json.dumps(copia, ensure_ascii=False) + "\n")
            fh.write(json.dumps(legitima, ensure_ascii=False) + "\n")

    def tearDown(self):
        shutil.rmtree(self.wd)

    def test_rechaza_copia_larga(self):
        ok, rech = mod.auditar_copias(self.wd)
        self.assertEqual((ok, rech), (1, 1))
        ruta_rech = os.path.join(self.wd, "afirmaciones",
                                "rechazadas_copia.jsonl")
        self.assertTrue(os.path.isfile(ruta_rech))

    def test_fusion_anade_procedencia(self):
        mod.auditar_copias(self.wd)
        n = mod.fusionar(self.wd)
        self.assertEqual(n, 1)
        ruta = os.path.join(self.wd, "afirmaciones", mod.AFIRMACIONES_FUSION)
        regs = [json.loads(l) for l in open(ruta, encoding="utf-8")]
        self.assertEqual(regs[0]["procedencia"], mod.PROCEDENCIA)
        self.assertNotIn("motivo_rechazo", regs[0])


class TestEndpoints(unittest.TestCase):
    def test_rechaza_nodo1(self):
        with self.assertRaises(ValueError):
            mod.construir_cliente("http://10.0.0.3:8000/v1")

    def test_workers_maximos(self):
        with self.assertRaises(SystemExit):
            mod.main(["--work-dir", tempfile.mkdtemp(), "--workers", "3",
                     "--cobertura"])


class TestFuentes(unittest.TestCase):
    def test_ricart_excluido(self):
        ricart = mod.fuente_por_id("ricart_1838")
        self.assertFalse(ricart["incluido"])
        with self.assertRaises(ValueError):
            mod.fuentes_incluidas("ricart_1838")

    def test_incluidas_son_dos(self):
        self.assertEqual(len(mod.fuentes_incluidas()), 2)


if __name__ == "__main__":
    unittest.main()
