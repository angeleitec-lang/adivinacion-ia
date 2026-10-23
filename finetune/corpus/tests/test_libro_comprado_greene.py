"""Tests del procesado del Greene «Saturn» comprado (T130).

Sin red y sin LLM real: solo mapeo de cabeceras, deteccion de aspectos,
troceo, filtro de imprenta, segmentacion sobre texto sintetico, puerta
anti-copia (astro), validaciones de work-dir/endpoints y el dry-run.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import libro_comprado_greene as greene  # noqa: E402
import libros_comprados_astro as astro  # noqa: E402


class TestMapeoCabeceras(unittest.TestCase):
    def test_signo_mas_casa_una_linea(self):
        cab = greene.detectar_cabecera("Saturn in Cancer and the fourth house")
        self.assertEqual(cab[0], "signo")
        eids = greene.eids_signo_casa(cab[1], cab[2])
        self.assertIn("saturno|cancer|planeta_en_signo", eids)
        self.assertIn("saturno|casa4|planeta_en_casa", eids)

    def test_signo_y_casa_en_dos_lineas(self):
        cab1 = greene.detectar_cabecera("Saturn in Scorpio and")
        self.assertEqual(cab1[0], "signo")
        self.assertIsNone(cab1[2])
        cab2 = greene.detectar_cabecera("the eighth house")
        self.assertEqual(cab2[0], "casa")
        eids = greene.eids_signo_casa(cab1[1]) + greene.eids_signo_casa(
            None, cab2[1])
        self.assertIn("saturno|escorpio|planeta_en_signo", eids)
        self.assertIn("saturno|casa8|planeta_en_casa", eids)

    def test_prefijo_basura_portadilla(self):
        cab = greene.detectar_cabecera("l in the watery")
        self.assertEqual(cab[0], "capitulo")
        self.assertEqual(greene._clave_capitulo(cab[1]), "watery")

    def test_capitulo_aspectos(self):
        cab = greene.detectar_cabecera("5 aspects on the")
        self.assertEqual(cab[0], "capitulo")
        self.assertEqual(greene._clave_capitulo(cab[1]), "aspectos")

    def test_cabecera_aspecto_sin_planeta(self):
        cab = greene.detectar_cabecera("Saturn in aspect")
        self.assertEqual(cab[0], "aspecto")
        self.assertIsNone(cab[1])

    def test_to_planeta_continuacion(self):
        cab = greene.detectar_cabecera("to the Moon")
        self.assertEqual(cab[0], "toplaneta")
        self.assertEqual(cab[1], "moon")

    def test_linea_larga_no_es_cabecera(self):
        self.assertIsNone(greene.detectar_cabecera(
            "The presence of Saturn in Cancer and the fourth house colors "
            "the whole character of the person who is born under it."))


class TestAspectos(unittest.TestCase):
    def test_detecta_variantes(self):
        norm = astro.norm("Saturn is conjunct the moon, in square to the "
                          "sun, and trine venus; several sextiles and an "
                          "opposition.")
        asp = set(greene.detectar_aspectos(norm))
        self.assertEqual(asp, {"conjuncion", "cuadratura", "trigono",
                               "sextil", "oposicion"})

    def test_eids_canonicos(self):
        ids = greene.eids_aspecto_planeta(
            "luna", ["conjuncion", "cuadratura"])
        self.assertIn("luna|conjuncion|saturno|aspecto", ids)
        self.assertIn("luna|cuadratura|saturno|aspecto", ids)

    def test_orden_canonico_tras_saturno(self):
        ids = greene.eids_aspecto_planeta("urano", ["trigono"])
        self.assertIn("saturno|trigono|urano|aspecto", ids)


class TestTrocear(unittest.TestCase):
    def test_por_oraciones(self):
        frases = ["Esta es una frase de prueba bastante larga. "] * 120
        trozos = greene.trocear("".join(frases))
        self.assertGreater(len(trozos), 1)
        for t in trozos[:-1]:
            self.assertLessEqual(len(t), greene.CHUNK_MAX)

    def test_bloque_corto_no_se_divide(self):
        texto = "Una frase corta."
        self.assertEqual(greene.trocear(texto), ["Una frase corta."])


class TestImprenta(unittest.TestCase):
    def test_rechaza_marcas(self):
        for linea in ("45173", "TXT49", "45173_TXT.indd 49",
                      "* . ", "11-06-03 12:01"):
            self.assertFalse(greene._no_imprenta(linea), linea)

    def test_conserva_texto_real(self):
        self.assertTrue(greene._no_imprenta(
            "Saturn in Cancer and the fourth house"))
        self.assertTrue(greene._no_imprenta(
            "The quality of endurance belongs to Saturn here."))


class TestSegmentar(unittest.TestCase):
    def _texto(self):
        parrafo = ("Saturn here conditions the deepest waters of the soul. "
                   "The native learns patience through long hardship and "
                   "finds security only after many trials of the family "
                   "root. ") * 12
        return "\n".join([
            "l in the watery",
            "signs and houses",
            "",
            "Saturn in Cancer",
            "and the fourth house",
            "",
            parrafo,
            "",
            "Saturn in aspect",
            "to the Moon",
            "",
            ("When Saturn is conjunct the Moon the inner mood becomes "
             "serious and the person fears joy; the square to the Sun "
             "brings discipline through conflict. ") * 8,
        ])

    def test_signo_y_casa_mapeadas(self):
        secciones, informe = greene.segmentar(self._texto())
        eids = {s["entidad_id"] for s in secciones}
        self.assertIn("saturno|cancer|planeta_en_signo", eids)
        self.assertIn("saturno|casa4|planeta_en_casa", eids)
        self.assertGreaterEqual(informe["secciones"], 1)

    def test_aspectos_desde_contexto(self):
        secciones, _ = greene.segmentar(self._texto())
        eids = {s["entidad_id"] for s in secciones}
        self.assertIn("luna|conjuncion|saturno|aspecto", eids)

    def test_formato_seccion_t119(self):
        secciones, _ = greene.segmentar(self._texto())
        for s in secciones:
            self.assertEqual(s["id_libro"], greene.ID_LIBRO)
            self.assertEqual(s["seccion"], s["entidad_id"])
            self.assertTrue(s["titulo"].startswith("Greene: "))
            self.assertIn("texto", s)
            self.assertLessEqual(s["chars"], greene.MAX_SECCION)

    def test_celdas_existing(self):
        validos = astro._validos()
        secciones, _ = greene.segmentar(self._texto())
        for s in secciones:
            self.assertIn(s["entidad_id"], validos)

    def test_hueco_capitulo_sin_celda(self):
        texto = ("Prologue text. " + "This introduction discusses archetypes "
                 "at length. " * 40)
        secciones, informe = greene.segmentar(texto)
        self.assertEqual(secciones, [])
        self.assertGreaterEqual(informe["trozos_sin_celda"], 1)


class TestInferir(unittest.TestCase):
    def test_planeta_por_frecuencia(self):
        t = ("Saturn meets Mars in a hard angle; Mars drives the square; the "
             "Venus note appears once only.")
        self.assertEqual(greene.inferir_planeta(t), "mars")

    def test_sin_planetas_devuelve_none(self):
        self.assertIsNone(greene.inferir_planeta("nothing of the sort here"))

    def test_aspecto_sin_to_the_infiere(self):
        texto = "\n".join([
            "5 aspects on the",
            "birth chart",
            "",
            "Saturn in aspect",
            "",
            ("Saturn-Mars contacts cut the appetite for ease; the Mars-Saturn "
             "square forces endurance, and every Mars encounter with Saturn "
             "demands long discipline before any reward arrives. ") * 8,
        ])
        secciones, _ = greene.segmentar(texto)
        eids = {s["entidad_id"] for s in secciones}
        self.assertIn("marte|cuadratura|saturno|aspecto", eids)
        self.assertNotIn("luna|conjuncion|saturno|aspecto", eids)


class TestMarcadoresHueco(unittest.TestCase):
    def test_sinastria_filtra_aspectos(self):
        p1 = ("Having made a closer observation of Saturn on the individual "
              "chart we now watch it between two people: Saturn conjunct his "
              "Moon in the partner makes duty feel like love, and Saturn "
              "square her Sun binds them through fear. ") * 8
        p2 = ("Saturn in Aries between the charts keeps the spark under "
              "control and teaches both partners patience over the years. ") * 3
        secciones, informe = greene.segmentar(p1 + "\n\n" + p2)
        eids = {s["entidad_id"] for s in secciones}
        self.assertFalse([e for e in eids if e.endswith("|aspecto")])
        self.assertIn("saturno|aries|planeta_en_signo", eids)
        self.assertGreaterEqual(informe["trozos_sin_celda"], 1)

    def test_conclusion_filtra_aspectos(self):
        parrafo = ("The science of psychology is a relatively new one, and "
                   "astrology older still; Saturn square the Sun in this "
                   "final chapter summarizes the discipline of time and "
                   "patience. ") * 8
        secciones, informe = greene.segmentar(parrafo)
        self.assertEqual(secciones, [])
        self.assertGreaterEqual(informe["trozos_sin_celda"], 1)
        self.assertIn("conclusion", informe["sin_celda_por_capitulo"])


class TestAntiCopia(unittest.TestCase):
    def test_afirmacion_literal_rechazada(self):
        indice = astro.construir_indice_copia(
            "Saturn in the watery signs demands that the soul descend "
            "into the depths of feeling before it can ever rise again "
            "into the light of day.")
        self.assertTrue(astro.es_copia_literal(
            "Saturn in the watery signs demands that the soul descend into "
            "the depths of feeling before it can ever rise again into the "
            "light of day and stay there",
            indice=indice))

    def test_parafeo_aceptado(self):
        indice = astro.construir_indice_copia(
            "Saturn in the watery signs demands that the soul descend "
            "into the depths of feeling before it can rise again.")
        self.assertFalse(astro.es_copia_literal(
            "Saturno en signos de agua pide un descenso emocional largo.",
            indice=indice))


class TestRutas(unittest.TestCase):
    def test_work_dir_real_rechazado(self):
        with self.assertRaises(ValueError):
            astro.validar_work_dir("/Users/angelgonzalez/fase0/libros/x")

    def test_acepta_nodo1_y_nodo2(self):
        cli1 = astro.construir_cliente_endpoints(
            "http://10.0.0.3:8000/v1", timeout=5.0)
        self.assertEqual(cli1._cliente.endpoints, ["http://10.0.0.3:8000/v1"])
        cli2 = astro.construir_cliente_endpoints(
            "http://10.0.0.4:8000/v1", timeout=5.0)
        self.assertEqual(cli2._cliente.endpoints, ["http://10.0.0.4:8000/v1"])

    def test_rechaza_host_ajeno(self):
        with self.assertRaises(ValueError):
            astro.construir_cliente_endpoints(
                "http://example.com/v1", timeout=5.0)


class TestEtapasLocales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="greene_t130_")
        self.old_dir = greene.WORK_DIR
        greene.WORK_DIR = self.tmp

    def tearDown(self):
        greene.WORK_DIR = self.old_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preparar_crea_estructura(self):
        greene.preparar(self.tmp)
        for sub in ("crudo", "limpio", "ocr", "secciones", "evidencias",
                    "knowledge", "afirmaciones"):
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, sub)))
        with open(os.path.join(self.tmp, "knowledge",
                               greene.META_NOMBRE)) as fh:
            meta = json.loads(fh.readline())
        self.assertEqual(meta["id"], greene.ID_LIBRO)
        self.assertEqual(meta["origen"], "comprado_por_usuario")

    def test_limpieza_exige_ocr_completo(self):
        greene.preparar(self.tmp)
        with self.assertRaises(FileNotFoundError):
            greene.etapa_limpieza(self.tmp)

    def test_medir_y_dry_run(self):
        greene.preparar(self.tmp)
        os.makedirs(os.path.join(self.tmp, "limpio"), exist_ok=True)
        parrafo = ("Saturn binds the water signs with patience. "
                   "The fourth house tests early security deeply. ") * 10
        texto = "\n".join([
            "Saturn in Cancer",
            "and the fourth house",
            "",
            parrafo,
        ])
        with open(greene.ruta_limpio(self.tmp), "w", encoding="utf-8") as fh:
            fh.write(texto)
        informe = greene.medir(self.tmp)
        self.assertGreaterEqual(informe["secciones"], 1)
        self.assertEqual(informe["llamadas_juez_estimadas"],
                         informe["secciones"])
        self.assertIn("saturno|cancer|planeta_en_signo",
                      informe["celdas_saturno_objetivo"])
        rc = greene.main(["--dry-run", "--work-dir", self.tmp])
        self.assertEqual(rc, 0)

    def test_main_despacha_etapas_llm(self):
        greene.preparar(self.tmp)
        with mock.patch.object(greene.astro, "construir_cliente_endpoints",
                             return_value=object()) as cli, \
             mock.patch.object(greene, "procesar_juez_greene",
                             return_value={"juzgadas": 1}) as pj:
            rc = greene.main(["--juez", "--work-dir", self.tmp,
                             "--endpoints", "http://10.0.0.4:8000/v1"])
            self.assertEqual(rc, 0)
            pj.assert_called_once()
            cli.assert_called_once()
        with mock.patch.object(greene.astro, "construir_cliente_endpoints",
                             return_value=object()) as cli, \
             mock.patch.object(greene, "procesar_afirmaciones_greene",
                             return_value={"procesadas": 1}) as pa:
            rc = greene.main(["--afirmaciones", "--work-dir", self.tmp,
                             "--endpoints", "http://10.0.0.4:8000/v1"])
            self.assertEqual(rc, 0)
            pa.assert_called_once()
            cli.assert_called_once()

    def test_main_rechaza_work_dir_real(self):
        self.assertEqual(
            greene.main(["--preparar", "--work-dir",
                         "/Users/angelgonzalez/fase0/libros/x"]), 2)


if __name__ == "__main__":
    unittest.main()
