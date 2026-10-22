#!/usr/bin/env python3
"""Tests de traducir_afirmaciones.py (T116): glosario, verificador y tubo."""
import io
import json
import os
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cartas  # noqa: E402
import traducir_afirmaciones as ta  # noqa: E402
from llm_client import LLMClient  # noqa: E402

GLOSARIO = ta.cargar_glosario()
INDICE = ta.IndiceCartas(GLOSARIO)


def fila(entidad, faceta, texto):
    return {"entidad_id": entidad, "faceta": faceta, "dominio": "tarot",
            "afirmacion": texto, "cita_original": texto, "contradice_kb": False}


class TestGlosarioContraKB(unittest.TestCase):
    def test_mayores_coinciden_con_kb_tarot(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "kb",
                               "tarot.json"), encoding="utf-8") as f:
            kb = json.load(f)
        nombres_kb = {e["nombre"] for e in kb["mayores"]}
        valores = set(GLOSARIO["mayores"].values())
        self.assertEqual(valores, nombres_kb)
        self.assertEqual(len(valores), 22)

    def test_menores_derivan_de_cartas(self):
        nombres = {e["nombre"] for e in cartas.CARTAS_TAROT}
        for r_es in set(GLOSARIO["rangos"].values()):
            for p_es in set(GLOSARIO["palos"].values()):
                self.assertIn(f"{r_es} de {p_es}", nombres)

    def test_palos_y_cortes(self):
        self.assertEqual(GLOSARIO["palos"]["wands"], "Bastos")
        self.assertEqual(GLOSARIO["palos"]["cups"], "Copas")
        self.assertEqual(GLOSARIO["palos"]["swords"], "Espadas")
        self.assertEqual(GLOSARIO["palos"]["pentacles"], "Oros")
        self.assertEqual(GLOSARIO["palos"]["coins"], "Oros")
        self.assertEqual(GLOSARIO["rangos"]["page"], "Sota")
        self.assertEqual(GLOSARIO["rangos"]["knight"], "Caballero")
        self.assertEqual(GLOSARIO["rangos"]["queen"], "Reina")
        self.assertEqual(GLOSARIO["rangos"]["king"], "Rey")

    def test_terminos_clave(self):
        t = GLOSARIO["terminos"]
        self.assertEqual(t["reversed"], "invertida")
        self.assertEqual(t["spread"], "tirada")
        self.assertEqual(t["querent"], "consultante")
        self.assertEqual(t["significator"], "significador")

    def test_astros_coinciden_con_kb(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "kb",
                               "astrologia.json"), encoding="utf-8") as f:
            kb = json.load(f)
        nombres = ({e["nombre"] for e in kb["signos"]}
                   | {e["nombre"] for e in kb["planetas"]}
                   | {e["nombre"] for e in kb["aspectos"]})
        for seccion in ("signos", "planetas", "aspectos"):
            for es in GLOSARIO["astrologia"][seccion].values():
                self.assertIn(es, nombres)


class TestVerificador(unittest.TestCase):
    def assert_ok(self, orig, trad):
        limpia, motivo = ta.verificar_traduccion(orig, trad, INDICE)
        self.assertIsNone(motivo, f"no debía rechazarse: {motivo}")
        self.assertTrue(limpia)

    def assert_rechazo(self, orig, trad, esperado_en_motivo):
        limpia, motivo = ta.verificar_traduccion(orig, trad, INDICE)
        self.assertIsNone(limpia)
        self.assertIn(esperado_en_motivo, motivo or "")

    def test_colgado_invertido(self):
        self.assert_ok(
            "The Hanged Man reversed suggests a pause.",
            "El Colgado invertido sugiere una pausa.")

    def test_hombre_colgado_reversed_rechazado(self):
        self.assert_rechazo(
            "The Hanged Man reversed suggests a pause.",
            "El Hombre Colgado Reversed sugiere una pausa.", "reversed")

    def test_strength_como_carta(self):
        self.assert_ok("Strength suggests inner control.",
                       "La Fuerza sugiere autocontrol interior.")
        # Si no traduce el nombre de la carta, rechazo.
        self.assert_rechazo("Strength suggests inner control.",
                            "La Fortalece sugiere autocontrol.", "La Fuerza")

    def test_strength_como_palabra_comun(self):
        # En minúsculas no es nombre de carta: no exige "La Fuerza".
        self.assert_ok("She found strength in difficult times.",
                       "Encontró fuerza en los momentos difíciles.")

    def test_pentacles_consistente_con_oros(self):
        self.assert_ok("Two of Pentacles shows balance.",
                       "El Dos de Oros muestra equilibrio.")
        self.assert_ok("Two of Pentacles shows balance.",
                       "El Dos de Pentáculos muestra equilibrio.")
        self.assert_rechazo("Two of Pentacles shows balance.",
                            "El Dos de Pentacles muestra equilibrio.",
                            "pentacles")

    def test_resto_en_ingles_rechazado(self):
        self.assert_rechazo("The Tower brings sudden change.",
                            "The Tower brings sudden change.", "inglés")

    def test_cifras_conservadas(self):
        self.assert_ok("There were 21 cards on the table.",
                       "Había 21 cartas sobre la mesa.")
        self.assert_rechazo("There were 21 cards on the table.",
                            "Había cartas sobre la mesa.", "21")

    def test_numero_en_palabras(self):
        self.assert_ok("It takes three cards in this spread.",
                       "Se necesitan tres cartas en esta tirada.")
        self.assert_rechazo("It takes three cards in this spread.",
                            "Se necesitan cartas en esta tirada.", "three")

    def test_upright_conservado(self):
        self.assert_ok("The Sun upright brings clarity.",
                       "El Sol al derecho aporta claridad.")
        self.assert_rechazo("The Sun upright brings clarity.",
                            "El Sol aporta claridad.", "derecha")

    def test_longitud_maxima(self):
        self.assert_rechazo(
            "The Star heals.",
            "La Estrella aporta un proceso profundo de sanación que "
            "reconforta el ánimo del consultante durante mucho tiempo.",
            "ratio")

    def test_gallego_rechazado(self):
        self.assert_rechazo("Nothing bad happens here.",
                            "Non hai nada malo.", "gallego")

    def test_portugues_rechazado(self):
        self.assert_rechazo("The Star is a card of healing.",
                            "La Estrella é muito boa.", "gallego")

    def test_prefijo_traduccion_limpiado(self):
        limpia, motivo = ta.verificar_traduccion(
            "The Fool means new beginnings.",
            "Traducción: El Loco significa nuevos comienzos.", INDICE)
        self.assertIsNone(motivo)
        self.assertEqual(limpia, "El Loco significa nuevos comienzos.")

    def test_as_de_copas_no_es_ingles_residual(self):
        # "as" está en EN_WORDS pero "As de Copas" es español válido.
        self.assert_ok("The Ace of Cups appears first.",
                       "El As de Copas aparece primero.")

    def test_debe_traducirse(self):
        self.assertEqual(ta.debe_traducirse("Buenas cartas para ti.", INDICE),
                         (False, "es"))
        self.assertEqual(ta.debe_traducirse("The cup runneth over.", INDICE),
                         (True, "en"))
        self.assertEqual(ta.debe_traducirse("2 of Cups", INDICE), (True, "en"))
        self.assertEqual(ta.debe_traducirse("¡Buena suerte!", INDICE),
                         (False, "unknown"))


class TestPrompt(unittest.TestCase):
    def test_glosario_inyectado(self):
        s = ta.construir_sistema(GLOSARIO)
        for marca in ("wands → Bastos", "pentacles → Oros",
                      "judgement → El Juicio", "reversed → invertida",
                      "life path → camino de vida", "taurus → Tauro",
                      "Devuelve SOLO la traducción", "gallego"):
            self.assertIn(marca, s)


class TestClientes(unittest.TestCase):
    def test_local_default_es_nodo2_y_nunca_nodo1(self):
        args = Namespace(backend="local", endpoint=[], model=None,
                         timeout=120.0, workers=1)
        c = ta.crear_cliente(args)
        self.assertIn("10.0.0.4", json.dumps([str(e) for e in c.endpoints]))
        self.assertNotIn("10.0.0.3", json.dumps([str(e) for e in c.endpoints]))

    def test_mercury_exige_env_sin_imprimir_clave(self):
        args = Namespace(backend="mercury", endpoint=[], model=None,
                         timeout=1.0, workers=1)
        with mock.patch.dict(os.environ, {}, clear=True):
            try:
                ta.crear_cliente(args)
                self.fail("debería exigir INCEPTION_API_KEY")
            except SystemExit as e:
                self.assertIn("INCEPTION_API_KEY", str(e))
        with mock.patch.dict(os.environ, {"INCEPTION_API_KEY": "sk-secreta"}):
            c = ta.crear_cliente(args)
            self.assertEqual(c.endpoints[0]["api_key_env"], "INCEPTION_API_KEY")
            self.assertNotIn("sk-secreta", json.dumps(c.endpoints[0]))


class TestTraducirUna(unittest.TestCase):
    def test_reintento_incluye_motivo(self):
        usuarios = []

        def simulado(sistema, usuario):
            usuarios.append(usuario)
            if len(usuarios) == 1:
                return "The Tower means sudden change."  # sigue en inglés
            return "La Torre supone un cambio súbito."

        c = LLMClient(simulado=simulado)
        args = Namespace(backend="local", endpoint=[], model=None,
                         timeout=1.0, workers=1)
        trad, motivo, n = ta.traducir_una(c, ta.construir_sistema(GLOSARIO),
                                          "The Tower means sudden change.",
                                          INDICE, 3, 0.2)
        self.assertEqual(motivo, None)
        self.assertEqual(n, 2)
        self.assertIn("rechazado", usuarios[1])
        self.assertIn("sigue en inglés", usuarios[1])


class TestTuberia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = lambda n: os.path.join(self.tmp.name, n)

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, **kw):
        base = dict(backend="local", endpoint=[], model=None, timeout=1.0,
                    workers=2, max_intentos=3, temperatura=0.2)
        base.update(kw)
        return Namespace(**base)

    def _simulada(self, sistema, usuario):
        # Traducciones correctas de prueba, en español.
        if "Hanged Man" in usuario:
            return "El Colgado invertido sugiere una pausa."
        if "2 of Cups" in usuario:
            return "El Dos de Copas trae un vínculo nuevo."
        if "bad" in usuario:
            return "bad translation stays in English"
        return "La Torre supone un cambio súbito."

    def test_fin_a_fin_con_simulado(self):
        entrada = self.ruta("in.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila("tarot-mayor-12", "significado_general",
                                     "The Hanged Man reversed suggests a pause."),
                               ensure_ascii=False) + "\n")
            f.write(json.dumps(fila("tarot-copas-02", "significado_general",
                                     "The 2 of Cups appears here."),
                               ensure_ascii=False) + "\n")
            f.write(json.dumps(fila("tarot-mayor-16", "significado_general",
                                     "La Torre ya está en español."),
                               ensure_ascii=False) + "\n")
            f.write(json.dumps(fila("tarot-mayor-16b", "otro",
                                     "The bad thing stays bad."),
                               ensure_ascii=False) + "\n")
        salida, rech = self.ruta("out.jsonl"), self.ruta("rej.jsonl")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(ta, "crear_cliente", lambda args: c):
            argv = ["--entrada", entrada, "--salida", salida,
                    "--rechazadas", rech]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ta.main(argv), 0)
            self.assertIn("rechazos=1", out.getvalue())
        con = {json.loads(l)["entidad_id"]: json.loads(l)
               for l in open(salida, encoding="utf-8")}
        self.assertEqual(len(con), 3)
        e1 = con["tarot-mayor-12"]
        self.assertEqual(e1["afirmacion"],
                         "El Colgado invertido sugiere una pausa.")
        self.assertEqual(e1["idioma_origen"], "en")
        self.assertIn("local:", e1["traductor"])
        self.assertTrue(e1["fid"])
        e3 = con["tarot-mayor-16"]
        self.assertEqual(e3["afirmacion"], "La Torre ya está en español.")
        self.assertNotIn("traductor", e3)
        rechazos = [json.loads(l) for l in open(rech, encoding="utf-8")]
        self.assertEqual(len(rechazos), 1)
        self.assertIn("inglés", rechazos[0]["motivo"])
        # fid estable: misma fila, mismo fid
        self.assertEqual(rechazos[0]["fid"], ta.fid_de(
            fila("tarot-mayor-16b", "otro", "The bad thing stays bad.")))

    def test_resume_omite_completadas(self):
        entrada = self.ruta("in.jsonl")
        salida = self.ruta("out.jsonl")
        fila1 = fila("tarot-mayor-12", "significado_general",
                     "The Tower means sudden change.")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila1, ensure_ascii=False) + "\n")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(ta, "crear_cliente", lambda args: c):
            with redirect_stdout(io.StringIO()):
                ta.main(["--entrada", entrada, "--salida", salida,
                         "--rechazadas", self.ruta("rej.jsonl")])
            # segunda pasada con una fila nueva: --resume no rehace la primera
            with open(entrada, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila("tarot-copas-02", "significado_general",
                                         "The 2 of Cups appears here."),
                                   ensure_ascii=False) + "\n")
            with redirect_stdout(io.StringIO()) as out:
                ta.main(["--entrada", entrada, "--salida", salida,
                         "--rechazadas", self.ruta("rej.jsonl"), "--resume"])
            txt = out.getvalue()
            self.assertIn("omitidas=1", txt)
        filas = [json.loads(l) for l in open(salida, encoding="utf-8")]
        self.assertEqual(len(filas), 2)
        self.assertEqual({f["entidad_id"] for f in filas},
                         {"tarot-mayor-12", "tarot-copas-02"})

    def test_dry_run_no_escribe(self):
        entrada = self.ruta("in.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila("x", "y", "The Tower means change."),
                               ensure_ascii=False) + "\n")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ta.main(["--entrada", entrada, "--dry-run"]), 0)
        self.assertIn("a traducir: 1", out.getvalue())
        self.assertFalse(os.path.exists(self.ruta("out.jsonl")))

    def test_limite(self):
        entrada = self.ruta("in.jsonl")
        salida = self.ruta("out.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps(fila(f"e{i}", "s",
                                         "The Tower means sudden change."),
                                   ensure_ascii=False) + "\n")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(ta, "crear_cliente", lambda args: c):
            with redirect_stdout(io.StringIO()) as out:
                ta.main(["--entrada", entrada, "--salida", salida,
                         "--limite", "2", "--rechazadas", self.ruta("r.jsonl")])
            self.assertIn("filas: 2", out.getvalue())
        self.assertEqual(sum(1 for _ in open(salida, encoding="utf-8")), 2)


if __name__ == "__main__":
    unittest.main()
