"""Tests del extractor de afirmaciones desde libros (T38)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import afirmaciones_libros as al
import juez
from llm_client import LLMClient

from consenso_kb import cargar_correspondencias

CORR = cargar_correspondencias()

TEXTO_EN = ("The two of wands represents fire in its purest form. It speaks "
            "of enterprise, bold ventures and the spark of initiative that "
            "drives the seeker forward into new plans.")

TEXTO_ES = ("El dos de bastos representa el fuego en su forma mas pura. "
            "Habla de empresa, de proyectos audaces y del impulso que "
            "mueve al consultante hacia nuevos planes.")


def _item(afirmacion, cita):
    return {"afirmacion": afirmacion, "cita_original": cita}


class TestCitaVerbatim(unittest.TestCase):
    def test_exacta(self):
        self.assertTrue(al.cita_verbatim("fire in its purest form", TEXTO_EN))

    def test_tildes_y_signos(self):
        self.assertTrue(al.cita_verbatim("fuego en su forma más pura.",
                                        TEXTO_ES))

    def test_no_presente(self):
        self.assertFalse(al.cita_verbatim("fire of the deep ocean", TEXTO_EN))

    def test_vacia(self):
        self.assertFalse(al.cita_verbatim("", TEXTO_EN))
        self.assertFalse(al.cita_verbatim("algo", ""))


class TestValidarAfirmacionLibros(unittest.TestCase):
    def test_valida_ingles(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El dos de bastos expresa el fuego en su forma mas pura.",
                 "fire in its purest form"),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertTrue(vale)
        self.assertIsNone(motivo)

    def test_vacia(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("  ", "fire"), TEXTO_EN, "naipe-bastos-02",
            "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "vacia"))

    def test_longitud(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("palabra " * 41, "fire"), TEXTO_EN, "naipe-bastos-02",
            "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "longitud"))

    def test_sin_cita(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El dos de bastos habla de empresa.", "   "),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "sin_cita"))

    def test_exceso_cita(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El dos de bastos habla de empresa.",
                 " ".join(["word"] * 26)),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "exceso_cita"))

    def test_cita_no_textual(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El dos de bastos habla de empresa.",
                 "the green dragon flies away"),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "cita_no_textual"))

    def test_otra_carta(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El tres de copas habla de fiesta y celebracion.",
                 "fire in its purest form"),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertEqual((vale, motivo), (False, "otra_carta"))

    def test_vocabulario_solo_si_es(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("La luna rige las mareas del oceano nocturno.",
                 "fuego en su forma más pura"),
            TEXTO_ES, "naipe-bastos-02", "significado_general", "es")
        self.assertEqual((vale, motivo), (False, "vocabulario"))
        # En ingles no se exige vocabulario comun (la cita ancla el grounding)
        vale2, _ = al.validar_afirmacion_libros(
            _item("La luna rige las mareas del oceano nocturno.",
                 "fire in its purest form"),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertTrue(vale2)

    def test_inutil_repite_nombre(self):
        vale, motivo = al.validar_afirmacion_libros(
            _item("El dos de bastos es el dos de bastos.",
                 "fire in its purest form"),
            TEXTO_EN, "naipe-bastos-02", "significado_general", "en")
        self.assertFalse(vale)


class TestExtraerAfirmacionesLibros(unittest.TestCase):
    def _cliente(self, respuesta):
        return LLMClient(simulado=lambda s, u: json.dumps(respuesta,
                                                         ensure_ascii=False))

    def test_acepta_y_marca_contradiction(self):
        cliente = self._cliente({"afirmaciones": [
            _item("El dos de bastos expresa el fuego en su forma mas pura.",
                 "fire in its purest form"),
            _item("El dos de bastos se asocia con los gnomos.",
                 "enterprise, bold ventures"),
        ]})
        res = al.extraer_afirmaciones_libros(
            cliente, "naipe-bastos-02", "significado_general", TEXTO_EN,
            "en", CORR)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(len(res["afirmaciones"]), 2)
        self.assertFalse(res["afirmaciones"][0]["contradice_kb"])
        self.assertTrue(res["afirmaciones"][1]["contradice_kb"])
        self.assertEqual(res["afirmaciones"][1]["motivo_contradice"],
                         "ser_elemental")

    def test_descarta_cita_no_textual(self):
        cliente = self._cliente({"afirmaciones": [
            _item("Algo inventado sobre el tema.", "this phrase is not there"),
        ]})
        res = al.extraer_afirmaciones_libros(
            cliente, "naipe-bastos-02", "significado_general", TEXTO_EN,
            "en", CORR)
        self.assertEqual(res["afirmaciones"], [])
        self.assertEqual(res["descartadas"][0][1], "cita_no_textual")

    def test_error_del_modelo(self):
        def falla(s, u):
            raise RuntimeError("sin nodo")
        cliente = LLMClient(simulado=falla)
        res = al.extraer_afirmaciones_libros(
            cliente, "naipe-bastos-02", "significado_general", TEXTO_EN,
            "en", CORR)
        self.assertEqual(res["estado"], "error")

    def test_tope_maximo(self):
        items = [_item("El dos de bastos habla de empresa numero %d." % i,
                      "fire in its purest form")
                 for i in range(15)]
        cliente = self._cliente({"afirmaciones": items})
        res = al.extraer_afirmaciones_libros(
            cliente, "naipe-bastos-02", "significado_general", TEXTO_EN,
            "en", CORR)
        self.assertEqual(len(res["afirmaciones"]), 12)
        self.assertIn(("El dos de bastos habla de empresa numero 12.",
                      "exceso"), res["descartadas"])


class TestRegistro(unittest.TestCase):
    def test_esquema(self):
        ev = {"entidad_id": "aries|signo", "faceta": "personalidad",
             "fuente_id": "1899minetta", "dominio": "1899minetta",
             "periodo": "clasica", "calidad": 4}
        item = {"afirmacion": "Aries es un signo de fuego.",
               "cita_original": "Aries is a sign of fire",
               "contradice_kb": True, "motivo_contradice": "elemento"}
        reg = al.registro_afirmacion_libros(ev, item)
        self.assertEqual(reg["entidad_id"], "aries|signo")
        self.assertEqual(reg["cita_original"], "Aries is a sign of fire")
        self.assertTrue(reg["contradice_kb"])
        self.assertEqual(reg["motivo_contradice"], "elemento")
        self.assertNotIn("hash_seccion", reg)


class TestIndiceLibros(unittest.TestCase):
    def test_busqueda_por_hash(self):
        sec = {"seccion": 3, "titulo": "T", "texto": TEXTO_EN,
               "chars": len(TEXTO_EN), "id_libro": "testlibro",
               "posicion": 3}
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "testlibro.jsonl"), "w",
                     encoding="utf-8") as f:
                f.write(json.dumps(sec, ensure_ascii=False) + "\n")
            idx = al.IndiceLibros(d)
            h = juez.hash_seccion(sec)
            encontrada = idx.seccion("testlibro", h)
            self.assertIsNotNone(encontrada)
            self.assertEqual(encontrada["texto"], TEXTO_EN)
            self.assertIsNone(idx.seccion("testlibro", "sinhash"))
            self.assertIsNone(idx.seccion("otro", h))


def _prep(d):
    """Crea secciones y evidencias de prueba; devuelve rutas."""
    sec = {"seccion": 1, "titulo": "Wands", "texto": TEXTO_EN,
           "chars": len(TEXTO_EN), "id_libro": "testlibro", "posicion": 1}
    secc_dir = os.path.join(d, "secciones")
    os.makedirs(secc_dir)
    with open(os.path.join(secc_dir, "testlibro.jsonl"), "w",
              encoding="utf-8") as f:
        f.write(json.dumps(sec, ensure_ascii=False) + "\n")
    evs = [
        {"entidad_id": "naipe-bastos-02", "faceta": "significado_general",
         "fuente_id": "testlibro", "dominio": "testlibro", "idioma": "en",
         "periodo": "moderna", "calidad": 4,
         "hash_seccion": juez.hash_seccion(sec)},
        {"entidad_id": "aries|signo", "faceta": "personalidad",
         "fuente_id": "testlibro", "dominio": "testlibro", "idioma": "en",
         "periodo": "moderna", "calidad": 3,
         "hash_seccion": "hash_inexistente"},
    ]
    ruta_ev = os.path.join(d, "evidencias.jsonl")
    with open(ruta_ev, "w", encoding="utf-8") as f:
        for e in evs:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return ruta_ev, secc_dir


class TestCLI(unittest.TestCase):
    def test_simulado_y_reanudacion(self):
        with tempfile.TemporaryDirectory() as d:
            ruta_ev, secc_dir = _prep(d)
            out = os.path.join(d, "out")
            stats = al.main([
                "--evidencias", ruta_ev, "--secciones-dir", secc_dir,
                "--out-dir", out, "--workers", "1", "--simulado"])
            self.assertEqual(stats["procesadas"], 2)
            self.assertEqual(stats["sin_texto"], 1)
            self.assertEqual(stats["afirmaciones"], 1)
            ruta_af = os.path.join(out, "afirmaciones_libros.jsonl")
            with open(ruta_af, encoding="utf-8") as f:
                regs = [json.loads(x) for x in f if x.strip()]
            self.assertEqual(len(regs), 1)
            self.assertIn("cita_original", regs[0])
            self.assertIn("contradice_kb", regs[0])
            self.assertTrue(os.path.exists(
                os.path.join(out, "afirmaciones_libros_informe.md")))
            # Reanudacion: todo ya procesado
            stats2 = al.main([
                "--evidencias", ruta_ev, "--secciones-dir", secc_dir,
                "--out-dir", out, "--workers", "1", "--simulado"])
            self.assertEqual(stats2["procesadas"], 0)

    def test_limite(self):
        with tempfile.TemporaryDirectory() as d:
            ruta_ev, secc_dir = _prep(d)
            out = os.path.join(d, "out")
            stats = al.main([
                "--evidencias", ruta_ev, "--secciones-dir", secc_dir,
                "--out-dir", out, "--workers", "1", "--limite", "1",
                "--simulado"])
            self.assertEqual(stats["procesadas"], 1)


if __name__ == "__main__":
    unittest.main()
