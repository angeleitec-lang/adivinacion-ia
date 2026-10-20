"""Tests del extractor de lecturas trabajadas (T37)."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import lecturas_extraer


def _seccion(titulo, texto, id_libro="libro-demo"):
    return {
        "seccion": 1,
        "titulo": titulo,
        "texto": texto,
        "chars": len(texto),
        "id_libro": id_libro,
        "posicion": 0,
    }


TIRADA_TAROT = (
    "Ejemplo de tirada de cartas: para una consultante que quiere saber "
    "sobre su trabajo, salio El Mago, salio La Sacerdotisa y salio El "
    "Loco invertido. La carta del Mago significa que tiene las "
    "herramientas necesarias; la carta de la Sacerdotisa aconseja "
    "escuchar su intuicion; la carta del Loco invertido advierte contra "
    "los impulsos precipitados. El consejo final es planificar con calma."
)

NATAL_ASTRO = (
    "Carta natal de Maria, nacida el 3 de marzo de 1980. Su Sol en Piscis "
    "y su Luna en Cancer la hacen muy intuitiva y protectora. El ascendente "
    "en Libra suaviza su caracter. La casa 7 esta ocupada por Venus: su "
    "pareja sera alguien del arte. Esta lectura de su carta natal indica "
    "una vida volcada a los demas."
)

TEORIA_SUELTA = (
    "El Mago representa el arquetipo del beginnings y la manifestacion. "
    "En la historia del tarot, esta carta se asocia con Hermes y con el "
    "numero uno. Los autores clasicos lo describen como el punto de "
    "partida del viaje del loco por los arcanos mayores."
)


class DetectorCandidatas(unittest.TestCase):
    """Paso 1 determinista: deteccion de candidatas a lectura trabajada."""

    def test_tirada_con_ejemplo_es_candidata(self):
        det = lecturas_extraer.candidata_lectura(
            _seccion("Ejemplo", TIRADA_TAROT))
        self.assertIsNotNone(det)
        self.assertIn("tirada", det["motivos"])
        self.assertGreaterEqual(det["n_cartas_tarot"], 3)

    def test_carta_natal_con_interpretacion_es_candidata(self):
        det = lecturas_extraer.candidata_lectura(
            _seccion("Carta natal", NATAL_ASTRO))
        self.assertIsNotNone(det)
        self.assertIn("natal", det["motivos"])

    def test_teoria_suelta_sin_ejemplo_no_es_candidata(self):
        det = lecturas_extraer.candidata_lectura(
            _seccion("El Mago", TEORIA_SUELTA))
        self.assertIsNone(det)

    def test_juicio_ruido_excluye_aunque_haya_tirada(self):
        det = lecturas_extraer.candidata_lectura(
            _seccion("Basura", TIRADA_TAROT),
            juicio={"tipo": "publicidad"})
        self.assertIsNone(det)

    def test_juicio_lectura_trabajada_es_candidata_segura(self):
        texto = ("Una senora pregunto por su hijo y saque unas cartas. "
                 "Las cartas mostraron que todo ira bien pronto. " +
                 "x" * 250)
        det = lecturas_extraer.candidata_lectura(
            _seccion("Consulta", texto),
            juicio={"tipo": "lectura_trabajada"})
        self.assertIsNotNone(det)
        self.assertIn("juicio_lectura", det["motivos"])

    def test_seccion_corta_no_es_candidata(self):
        det = lecturas_extraer.candidata_lectura(
            _seccion("Corta", "Ejemplo: El Mago, La Luna y El Sol."))
        self.assertIsNone(det)

    def test_ingles_reading_for_querent_es_candidata(self):
        texto = (
            "Example reading for a querent who wants to know about her "
            "marriage. The cards drawn were The Empress, The Tower and "
            "The Star. The Empress means abundance in the home; The Tower "
            "warns of sudden change; The Star promises hope after the "
            "storm. This reading suggests patience and trust.")
        det = lecturas_extraer.candidata_lectura(_seccion("Reading", texto))
        self.assertIsNotNone(det)
        self.assertIn("consulta", det["motivos"])

    def test_numerologia_con_ejemplo_es_candidata(self):
        texto = (
            "Ejemplo de numerologia: el camino de vida de Juan es 7. "
            "El 7 indica introspeccion y analisis. Su numero del destino "
            "es 3, que sugiere creatividad y comunicacion. La lectura "
            "numerologica aconseja combinar reflexion y expresion.")
        det = lecturas_extraer.candidata_lectura(_seccion("Numero", texto))
        self.assertIsNotNone(det)
        self.assertIn("numerologia", det["motivos"])

    def test_consulta_sin_senal_de_sistema_no_es_candidata(self):
        texto = ("En este capitulo encontramos un ejemplo teorico. "
                 "? La palabra significa muchas cosas y el consejo es "
                 "generico. " + "y" * 250)
        det = lecturas_extraer.candidata_lectura(_seccion("Teoria", texto))
        self.assertIsNone(det)

    def test_senales_lectura_cuentan_cartas(self):
        s = lecturas_extraer.senales_lectura(TIRADA_TAROT)
        self.assertGreaterEqual(s["n_cartas_tarot"], 3)
        self.assertTrue(s["ejemplo"])
        self.assertTrue(s["interpretacion"])


class ValidacionClasificador(unittest.TestCase):
    """Paso 2: validacion de la respuesta del LLM."""

    def _ok(self):
        return {
            "es_lectura": True,
            "sistema": "tarot",
            "cartas": ["El Mago"],
            "elementos": [],
            "pregunta": "?",
            "calidad": 4,
            "idioma": "es",
            "motivo": "ok",
        }

    def test_respuesta_valida_pasa(self):
        lecturas_extraer.validar_clasificacion(self._ok())

    def test_sistema_invalido_falla(self):
        d = self._ok()
        d["sistema"] = "runas"
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_calidad_fuera_rango_falla(self):
        d = self._ok()
        d["calidad"] = 7
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_calidad_no_entera_falla(self):
        d = self._ok()
        d["calidad"] = "alta"
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_es_lectura_no_booleano_falla(self):
        d = self._ok()
        d["es_lectura"] = "si"
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_cartas_no_lista_falla(self):
        d = self._ok()
        d["cartas"] = "El Mago"
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_idioma_invalido_falla(self):
        d = self._ok()
        d["idioma"] = "gl"
        with self.assertRaises(ValueError):
            lecturas_extraer.validar_clasificacion(d)

    def test_clasificar_con_simulado(self):
        from llm_client import LLMClient
        cliente = LLMClient(simulado=lecturas_extraer._simulado_clasificador)
        res = lecturas_extraer.clasificar_lectura(
            cliente, _seccion("Ejemplo", TIRADA_TAROT))
        self.assertTrue(res["es_lectura"])
        self.assertEqual(res["sistema"], "tarot")
        self.assertEqual(res["calidad"], 4)


class RegistroLectura(unittest.TestCase):
    """Registro con procedencia (libro, seccion, periodo)."""

    def test_registro_incluye_procedencia(self):
        clasif = {
            "es_lectura": True, "sistema": "tarot",
            "cartas": ["El Mago"], "elementos": [],
            "pregunta": "trabajo", "calidad": 5, "idioma": "es",
            "motivo": "completa",
        }
        meta = {"libro-demo": {"anio": 1920, "idioma": "es",
                              "titulo": "Tarot clasico", "autor": "Anonimo",
                              "periodo": "clasica"}}
        reg = lecturas_extraer.registro_lectura(
            _seccion("Ejemplo", TIRADA_TAROT), clasif, meta)
        self.assertEqual(reg["fuente"], "libro")
        self.assertEqual(reg["libro_id"], "libro-demo")
        self.assertEqual(reg["titulo_libro"], "Tarot clasico")
        self.assertEqual(reg["periodo"], "clasica")
        self.assertEqual(reg["sistema"], "tarot")
        self.assertEqual(reg["calidad"], 5)
        self.assertIn("id", reg)

    def test_registro_sin_meta_no_falla(self):
        clasif = {"es_lectura": True, "sistema": "astrologia",
                 "cartas": [], "elementos": ["Sol en Piscis"],
                 "pregunta": None, "calidad": 3, "idioma": "es",
                 "motivo": "parcial"}
        reg = lecturas_extraer.registro_lectura(
            _seccion("Natal", NATAL_ASTRO), clasif, {})
        self.assertEqual(reg["titulo_libro"], "")
        self.assertIsNone(reg["periodo"])


class PipelineSimulado(unittest.TestCase):
    """main() con simulado: salida, reanudabilidad e informe."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir_sec = os.path.join(self.tmp, "secciones")
        os.makedirs(self.dir_sec)
        secciones = [
            _seccion("Ejemplo", TIRADA_TAROT, "libro-a"),
            _seccion("Natal", NATAL_ASTRO, "libro-b"),
            _seccion("Teoria", TEORIA_SUELTA, "libro-c"),
        ]
        with open(os.path.join(self.dir_sec, "a.jsonl"), "w",
                 encoding="utf-8") as fh:
            for s in secciones:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
        self.ruta_lect = os.path.join(self.tmp, "lecturas.jsonl")
        self.ruta_pr = os.path.join(self.tmp, "procesados.jsonl")
        self.ruta_in = os.path.join(self.tmp, "lecturas_informe.md")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _run(self, extra=None):
        argv = ["--secciones-dir", self.dir_sec,
               "--juicios", os.path.join(self.tmp, "noexiste.jsonl"),
               "--out-dir", self.tmp, "--simulado"]
        argv += extra or []
        return lecturas_extraer.main(argv)

    def test_acepta_candidatas_y_rechaza_teoria(self):
        stats = self._run()
        self.assertEqual(stats["secciones"], 3)
        self.assertEqual(stats["candidatas"], 2)
        self.assertEqual(stats["aceptadas"], 2)
        self.assertEqual(stats["errores"], 0)
        with open(self.ruta_lect, encoding="utf-8") as fh:
            regs = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(regs), 2)
        for reg in regs:
            self.assertEqual(reg["fuente"], "libro")
            self.assertIn("texto", reg)

    def test_reanudable_no_duplica(self):
        self._run()
        stats2 = self._run()
        self.assertEqual(stats2["clasificadas"], 0)
        with open(self.ruta_lect, encoding="utf-8") as fh:
            regs = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(regs), 2)

    def test_solo_detector_escribe_candidatas_sin_llm(self):
        stats = self._run(["--solo-detector"])
        self.assertEqual(stats["candidatas"], 2)
        self.assertEqual(stats["clasificadas"], 0)
        self.assertFalse(os.path.exists(self.ruta_lect))
        with open(os.path.join(self.tmp, "candidatas.jsonl"),
                 encoding="utf-8") as fh:
            cands = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(cands), 2)
        for c in cands:
            self.assertIn("motivos", c)

    def test_informe_tiene_recuentos(self):
        self._run()
        with open(self.ruta_in, encoding="utf-8") as fh:
            informe = fh.read()
        self.assertIn("Lecturas aceptadas: 2", informe)
        self.assertIn("tarot", informe)
        self.assertIn("Ejemplos", informe)

    def test_error_llm_no_rompe_y_no_se_registra_procesada(self):
        from llm_client import LLMClient

        def malo(sistema, usuario):
            return "no hay json aqui"

        cliente = LLMClient(simulado=malo)
        stats = lecturas_extraer.main(
            ["--secciones-dir", self.dir_sec,
             "--juicios", os.path.join(self.tmp, "noexiste.jsonl"),
             "--out-dir", self.tmp, "--workers", "1"],
            cliente=cliente)
        self.assertEqual(stats["errores"], 2)
        self.assertEqual(stats["aceptadas"], 0)
        self.assertFalse(os.path.exists(self.ruta_pr))


if __name__ == "__main__":
    unittest.main()
