# Tests de libro_comprado_nichols: limpieza OCR, segmentacion por arcanos y
# puerta anti-copia (T114). Sin red ni LLM: clientes falsos y mocks.
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import tempfile
import unittest
from unittest import mock

import libro_comprado_nichols as mod


class TestNormalizacion(unittest.TestCase):
    def test_sin_tildes(self):
        self.assertEqual(mod.sin_tildes("Destrucción"), "Destruccion")
        self.assertEqual(mod.sin_tildes("Ermitaño"), "Ermitano")

    def test_normalizar_token(self):
        self.assertEqual(mod.normalizar_token("La Rueda de la Fortuna"),
                         "LARUEDADELAFORTUNA")
        self.assertEqual(mod.normalizar_token("EL COLGADO:"), "ELCOLGADO")


class TestMedida(unittest.TestCase):
    def test_medir_defectos(self):
        texto = "nümero ä £sta civilización técnica^ y ¬fin"
        m = mod.medir_defectos(texto)
        self.assertEqual(m["u_diaeresis"], 1)
        self.assertEqual(m["libra"], 1)
        self.assertEqual(m["a_diaeresis"], 1)
        self.assertEqual(m["circunflejo"], 1)
        self.assertEqual(m["guion_silabico"], 1)


class TestLimpieza(unittest.TestCase):
    def test_tabla_vocales(self):
        limpio, _ = mod.limpiar_ocr("nümero civilización destrucciön")
        self.assertIn("número", limpio)
        self.assertIn("civilización", limpio)
        self.assertIn("destrucción", limpio)
        self.assertNotIn("ü", limpio)
        self.assertNotIn("ö", limpio)

    def test_guion_silabico_unido(self):
        crudo = "comen¬\nzando la obra"
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertIn("comenzando", limpio)
        self.assertNotIn("¬", limpio)
        self.assertGreaterEqual(informe["guiones_unidos"], 1)

    def test_numeros_pagina_fuera(self):
        crudo = "parrafo uno\n\n47\n\nparrafo dos"
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertNotIn("\n47\n", limpio)
        self.assertGreaterEqual(informe["paginas_eliminadas"], 1)

    def test_cabeceras_pagina_repetidas_fuera(self):
        head = "La Rueda de la Fortuna: jSocorro!"
        crudo = (head + "\n\nparrafo de contenido real aqui.\n\n"
                + head + "\n\notro parrafo de contenido.\n\n"
                + head + "\n\ny un tercer parrafo.")
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertNotIn("jSocorro", limpio)
        self.assertGreaterEqual(informe["cabeceras_pagina_eliminadas"], 3)

    def test_frase_cuerpo_no_se_quita(self):
        # Una frase del cuerpo que menciona una carta una sola vez NO es cabecera.
        crudo = ("El mago representa la voluntad consciente del consultante "
                "en la lectura de hoy.\n\nOtro parrafo sin repeticion.")
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertIn("El mago representa", limpio)

    def test_whitelist_circunflejo(self):
        crudo = "la t^cnica y el t^rmino y tambi^n franc^s"
        limpio, _ = mod.limpiar_ocr(crudo)
        self.assertIn("técnica", limpio)
        self.assertIn("término", limpio)
        self.assertIn("también", limpio)
        self.assertIn("francés", limpio)

    def test_interrogacion_inicial(self):
        # «^» a inicio de palabra es «¿»; no toca la intra-palabra ambigua.
        crudo = "^Como ^cual ^no y «^por que» —^Sabes? t^cnica la^cuenta"
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertIn("¿Como", limpio)
        self.assertIn("¿cual", limpio)
        self.assertIn("¿no", limpio)
        self.assertIn("«¿por", limpio)
        self.assertIn("—¿Sabes", limpio)
        self.assertIn("técnica", limpio)
        self.assertNotIn("¿t", limpio)
        self.assertIn("la^cuenta", informe["dudosos"])
        self.assertEqual(informe["interrogaciones_reparadas"], 5)

    def test_dudosos_se_listan_no_se_corrigem(self):
        # Un ^ ambiguo intra-palabra fuera de la whitelist queda y se reporta.
        crudo = "texto con TTl^THX basura y la^cuenta suelta"
        limpio, informe = mod.limpiar_ocr(crudo)
        self.assertIn("^", limpio)
        self.assertGreaterEqual(sum(informe["dudosos"].values()), 1)


class TestEncabezados(unittest.TestCase):
    def test_detecta_arcana_mayusculas(self):
        lineas = ["preludio", "13. LA RUEDA DE LA FORTUNA:", "cuerpo"]
        encs = mod.detectar_encabezados(lineas)
        self.assertEqual(len(encs), 1)
        self.assertEqual(encs[0]["entidad_id"], "tarot-mayor-11")
        self.assertEqual(encs[0]["numero"], 13)

    def test_papisa_antes_que_papa(self):
        lineas = ["5. LA PAPISA:"]
        encs = mod.detectar_encabezados(lineas)
        self.assertEqual(encs[0]["entidad_id"], "tarot-mayor-03")

    def test_title_case_no_es_encabezado(self):
        lineas = ["La Justicia: Existe?", "el carro nos lleva"]
        self.assertEqual(mod.detectar_encabezados(lineas), [])

    def test_mencion_cuerpo_no_es_encabezado(self):
        lineas = ["la fuerza es comun en el lenguaje diario"]
        self.assertEqual(mod.detectar_encabezados(lineas), [])


class TestSegmentacion(unittest.TestCase):
    def _mini_libro(self):
        # Orden del libro != orden del tarot: Justicia (cap 11) = tarot-12.
        partes = []
        partes.append("intro sin numero")
        partes.append("11. LA JUSTICIA:")
        partes.append("Texto sobre la justicia y el arquetipo. " * 10)
        partes.append("12. EL ERMITANO:")
        partes.append("Texto sobre el ermitano y la introspeccion. " * 10)
        partes.append("25. SOBRE COMO ECHAR LAS CARTAS:")
        partes.append("Esto no es un arcano y queda fuera.")
        return "\n".join(partes)

    def test_mapeo_por_nombre_no_por_numero(self):
        secs = mod.segmentar_arcanos(self._mini_libro())
        titulos = [s["titulo"] for s in secs]
        self.assertIn("La Justicia", titulos)
        self.assertIn("El Ermitano", titulos)
        just = [s for s in secs if s["titulo"] == "La Justicia"][0]
        self.assertEqual(just["entidad_id"], "tarot-mayor-12")
        erm = [s for s in secs if s["titulo"] == "El Ermitano"][0]
        self.assertEqual(erm["entidad_id"], "tarot-mayor-10")

    def test_no_arcana_fuera(self):
        secs = mod.segmentar_arcanos(self._mini_libro())
        titulos = [s["titulo"] for s in secs]
        self.assertNotIn("Sobre como echar las cartas", titulos)
        for s in secs:
            self.assertNotIn("no es un arcano", s["texto"])

    def test_formato_seccion(self):
        secs = mod.segmentar_arcanos(self._mini_libro())
        for s in secs:
            for clave in ("seccion", "titulo", "texto", "chars", "id_libro",
                         "posicion", "entidad_id"):
                self.assertIn(clave, s)
            self.assertEqual(s["chars"], len(s["texto"]))
            self.assertEqual(s["id_libro"], mod.ID_LIBRO)

    def test_seccion_larga_se_parte(self):
        largo = "palabra " * 4000  # > 12000 chars
        libro = "3. EL LOCO:\n" + largo
        secs = mod.segmentar_arcanos(libro)
        self.assertGreater(len(secs), 1)
        for s in secs:
            self.assertLessEqual(s["chars"], mod.MAX_SECCION + 500)

    def test_sin_encabezados_vacio(self):
        self.assertEqual(mod.segmentar_arcanos("solo texto sin capitulos"), [])


class TestPuertaAntiCopia(unittest.TestCase):
    def setUp(self):
        self.libro = " ".join("palabra%d" % i for i in range(1, 31))
        self.indice = mod.construir_indice_copia(self.libro)

    def test_copia_mas_de_25_rechazada(self):
        copia = " ".join("palabra%d" % i for i in range(1, 27))  # 26 palabras
        self.assertTrue(mod.es_copia_literal(copia, indice=self.indice))

    def test_25_consecutivas_permitida(self):
        run25 = " ".join("palabra%d" % i for i in range(1, 26))  # 25 palabras
        self.assertFalse(mod.es_copia_literal(run25, indice=self.indice))

    def test_parafasis_permitida(self):
        par = run = " ".join("palabra%d" % i for i in range(1, 26))
        par = par + " y ademas una idea propia redactada"
        self.assertFalse(mod.es_copia_literal(par, indice=self.indice))

    def test_sin_texto_e_indice_error(self):
        larga = " ".join("palabra%d" % i for i in range(1, 30))  # > 26 palabras
        with self.assertRaises(ValueError):
            mod.es_copia_literal(larga)

    def test_max_consecutivas_configurable(self):
        libro = " ".join("w%d" % i for i in range(1, 11))
        indice = mod.construir_indice_copia(libro, max_consecutivas=5)
        copia6 = " ".join("w%d" % i for i in range(1, 7))  # 6 consecutivas
        self.assertTrue(mod.es_copia_literal(copia6, indice=indice,
                                           max_consecutivas=5))
        copia5 = " ".join("w%d" % i for i in range(1, 6))  # 5 = no > 5
        self.assertFalse(mod.es_copia_literal(copia5, indice=indice,
                                            max_consecutivas=5))


class TestWrapperAfirmaciones(unittest.TestCase):
    def test_rechaza_copia_acepta_parafasis(self):
        texto = " ".join("palabra%d" % i for i in range(1, 31))
        copia = " ".join("palabra%d" % i for i in range(1, 27))
        base_result = {
            "estado": "ok",
            "afirmaciones": [
                {"afirmacion": copia, "cita_original": "palabra1 palabra2"},
                {"afirmacion": "Idea propia parafraseada del capitulo",
                 "cita_original": "palabra3 palabra4"},
            ],
            "descartadas": [],
        }
        with mock.patch.object(mod.afirmaciones_libros,
                             "extraer_afirmaciones_libros",
                             return_value=base_result):
            res = mod.extraer_afirmaciones_nichols(
                None, "tarot-mayor-11", "simbolismo", texto, "es", None)
        self.assertEqual(len(res["afirmaciones"]), 1)
        self.assertEqual(res["afirmaciones"][0]["afirmacion"],
                         "Idea propia parafraseada del capitulo")
        motivos = [m for _, m in res["descartadas"]]
        self.assertIn("copia_literal", motivos)


class TestWorkDir(unittest.TestCase):
    def test_rechaza_work_dir_real(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir(mod.WORK_DIR_REAL)

    def test_acepta_work_dir_aparte(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mod.validar_work_dir(tmp), os.path.realpath(tmp))

    def test_acepta_nodo1(self):
        cliente = mod.construir_cliente_endpoints("http://10.0.0.3:8000/v1")
        self.assertIsNotNone(cliente)

    def test_acepta_nodo2(self):
        cliente = mod.construir_cliente_endpoints(mod.NODO2_ENDPOINT)
        self.assertIsNotNone(cliente)

    def test_vacio_reparte_ambos(self):
        cliente = mod.construir_cliente_endpoints("")
        base = getattr(cliente, "_cliente", cliente)
        self.assertEqual(
            set(base.endpoints),
            {"http://10.0.0.3:8000/v1", "http://10.0.0.4:8000/v1"})

    def test_rechaza_host_ajeno(self):
        with self.assertRaises(ValueError):
            mod.construir_cliente_endpoints("http://example.com/v1")


class TestIntegracionCrudo(unittest.TestCase):
    """Valida la segmentacion sobre el crudo real si esta disponible."""

    CRUDO_TMP = ("/var/folders/wf/n_gzv4090z77rh0jlq19y78r0000gn/T/opencode/"
                "nichols_crudo.txt")

    @unittest.skipUnless(os.path.isfile(CRUDO_TMP), "crudo real no disponible")
    def test_22_arcanos_reales(self):
        with open(self.CRUDO_TMP, encoding="utf-8", errors="replace") as fh:
            crudo = fh.read()
        limpio, informe = mod.limpiar_ocr(crudo)
        secs = mod.segmentar_arcanos(limpio)
        entidades = {s["entidad_id"] for s in secs}
        self.assertEqual(len(entidades), 22)
        # El orden del libro (Justicia cap.11) no altera el id: Justicia=12.
        just = [s for s in secs if s["entidad_id"] == "tarot-mayor-12"]
        self.assertTrue(just)
        # No debe entrar el capitulo 25 (no arcano).
        for s in secs:
            self.assertNotIn("SOBRE COMO ECHAR", s["titulo"])
        # Limpieza: no quedan vocales con dieresis.
        self.assertNotIn("ö", limpio)
        self.assertNotIn("ä", limpio)


if __name__ == "__main__":
    unittest.main()
