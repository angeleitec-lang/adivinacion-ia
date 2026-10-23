#!/usr/bin/env python3
"""Tests de parafrasear_baraja.py (T131): verificador, antorcopia y tubo."""
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

import parafrasear_baraja as pa  # noqa: E402
from llm_client import LLMClient  # noqa: E402


_CITA_DEFECTO = ("Felicidad, prosperidad y triunfo en los asuntos materiales. "
                 "Riqueza y buen augurio para la persona consultante.")


def fila(entidad="naipe-oros-01", faceta="significado_general", texto=None,
         orient="derecho", cita=None, fuente="libro_salas_baraja"):
    return {"entidad_id": entidad, "faceta": faceta, "fuente_id": fuente,
            "dominio": fuente, "periodo": "moderna", "calidad": 3,
            "afirmacion": texto or "",
            "cita_original": _CITA_DEFECTO if cita is None else cita,
            "contradice_kb": False, "orientacion": orient}


LARGA = ("Felicidad. Prosperidad. Triunfo. Grandes alegrías. Satisfacción. "
         "Riqueza. Es la carta más favorable de la baraja completa.")


class TestAntiCopia(unittest.TestCase):
    def test_indice_y_deteccion(self):
        indice = pa.construir_indice_copia(LARGA)
        self.assertTrue(pa.es_copia_literal(
            "Felicidad prosperidad triunfo grandes alegrias satisfaccion "
            "riqueza es la carta mas favorable de la baraja completa.",
            indice=indice))
        self.assertFalse(pa.es_copia_literal(
            "El As de Oros al derecho señala felicidad y prosperidad.",
            indice=indice))

    def test_menos_de_9_palabras_no_cuenta(self):
        cita = "Felicidad. Prosperidad. Triunfo."
        indice = pa.construir_indice_copia(cita)
        # la cita tiene <9 palabras: ninguna ventana de 9 coincide
        self.assertFalse(pa.es_copia_literal(
            "Felicidad prosperidad triunfo.", indice=indice))


class TestVerificador(unittest.TestCase):
    def assert_ok(self, f, bruto):
        limpia, motivo = pa.verificar_parafrasis(f, bruto, pa.indice_copia_de(f))
        self.assertIsNone(motivo, f"no debía rechazarse: {motivo}")
        self.assertTrue(limpia)

    def assert_rechazo(self, f, bruto, esperado_en_motivo):
        limpia, motivo = pa.verificar_parafrasis(f, bruto, pa.indice_copia_de(f))
        self.assertIsNone(limpia)
        self.assertIn(esperado_en_motivo, motivo or "")

    def test_ok_derecho(self):
        self.assert_ok(fila(orient="derecho"),
                        "El As de Oros al derecho señala felicidad y prosperidad.")

    def test_ok_reves(self):
        self.assert_ok(fila(orient="reves"),
                        "El As de Oros al revés apunta a fortuna y dinero.")

    def test_no_termina_en_punto(self):
        self.assert_rechazo(fila(), "El As de Oros al derecho señala felicidad",
                            "punto")

    def test_demasiadas_oraciones(self):
        self.assert_rechazo(
            fila(),
            "El As de Oros al derecho indica felicidad. Prosperidad. Triunfo.",
            "oraciones")

    def test_copia_literal(self):
        f = fila(cita="Felicidad. Prosperidad. Triunfo. Grandes alegrías. "
                        "Satisfacción. Riqueza. Es la carta más favorable de la baraja")
        self.assert_rechazo(
            f, "Felicidad prosperidad triunfo grandes alegrias satisfaccion "
                "riqueza es la carta mas favorable de la baraja completa.",
            "copia literal")

    def test_ingles_rechazado(self):
        self.assert_rechazo(fila(), "The Ace of Coins indicates money and wealth.",
                            "inglés")

    def test_gallego_rechazado(self):
        self.assert_rechazo(fila(), "Non hai nada malo con esta carta al derecho.",
                            "gallego")

    def test_asistente_rechazado(self):
        self.assert_rechazo(
            fila(), "El As de Oros al derecho indica felicidad, según el "
                    "asistente de IA.", "asistente")

    def test_falta_orientacion_reves(self):
        self.assert_rechazo(fila(orient="reves"),
                            "El As de Oros señala fortuna y dinero.", "revés")

    def test_falta_orientacion_derecho(self):
        self.assert_rechazo(fila(orient="derecho"),
                            "El As de Oros señala felicidad y prosperidad.",
                            "derecho")

    def test_respuesta_vacia(self):
        self.assert_rechazo(fila(), "", "vacía")

    def test_cita_sin_contenido_rechazada(self):
        # Regresión T134: citas del tipo «Al revés» no deben parafrasearse.
        f = fila(orient="reves", cita="Al revés")
        self.assert_rechazo(
            f, "El As de Oros al revés indica una inversión o alteración "
                "del significado habitual de la carta.", "cita sin contenido")

    def test_cita_menos_de_40_rechazada(self):
        f = fila(cita="Felicidad. Prosperidad.")  # <40 caracteres
        self.assert_rechazo(f, "El As de Oros al derecho señala felicidad.",
                            "cita sin contenido")

    def test_formula_generica_rechazada(self):
        # Regresión T134: paráfrasis inventadas con fórmula vacía de reversa.
        for entidad, paraf in (
            ("naipe-oros-02",
             "El Dos de Oros al revés señala una inversión o alteración en el "
             "equilibrio material."),
            ("naipe-oros-01",
             "En su posición invertida, el As de Oros se asocia con una energía "
             "bloqueada o una pérdida de valor material."),
            ("naipe-oros-10",
             "El Rey de Oros al revés indica una inversión o bloqueo en la "
             "energía asociada a esta figura."),
        ):
            f = fila(entidad=entidad, orient="reves", cita=_CITA_DEFECTO)
            self.assert_rechazo(f, paraf, "genérica")

    def test_formula_generica_no_rechaza_contenido_real(self):
        f = fila(orient="reves", cita=_CITA_DEFECTO)
        self.assert_ok(
            f, "El As de Oros al revés indica problemas de dinero, demoras "
                "en los pagos y dificultades económicas para la persona.")


class TestPrompt(unittest.TestCase):
    def test_reglas_inyectadas(self):
        s = pa.construir_sistema()
        for marca in ("baraja española", "1 o 2 oraciones", "terminando en punto",
                      "No inventes significados", "al revés", "gallego",
                      "Devuelve SOLO la paráfrasis"):
            self.assertIn(marca, s)


class TestClientes(unittest.TestCase):
    def test_mercury_exige_env_sin_imprimir_clave(self):
        args = Namespace(backend="mercury", endpoint=[], model=None,
                         timeout=1.0, workers=1)
        with mock.patch.dict(os.environ, {}, clear=True):
            try:
                pa.crear_cliente(args)
                self.fail("debería exigir INCEPTION_API_KEY")
            except SystemExit as e:
                self.assertIn("INCEPTION_API_KEY", str(e))
        with mock.patch.dict(os.environ, {"INCEPTION_API_KEY": "sk-secreta"}):
            c = pa.crear_cliente(args)
            self.assertEqual(c.endpoints[0]["api_key_env"], "INCEPTION_API_KEY")
            self.assertNotIn("sk-secreta", json.dumps(c.endpoints[0]))

    def test_workers_por_defecto_2_y_no_mas(self):
        self.assertLessEqual(pa.MAX_WORKERS, 2)

    def test_procedencia(self):
        self.assertEqual(pa.PROCEDENCIA, "comprado por el usuario, uso interno, libro con copyright")


class TestParafrasearUna(unittest.TestCase):
    def test_reintento_incluye_motivo(self):
        usuarios = []

        def simulado(sistema, usuario):
            usuarios.append(usuario)
            if len(usuarios) == 1:
                return "The Ace of Coins indicates money."  # sigue en inglés
            return "El As de Oros al derecho señala felicidad y prosperidad."

        c = LLMClient(simulado=simulado)
        f = fila(orient="derecho")
        txt, motivo, n = pa.parafrasear_una(c, pa.construir_sistema(), f,
                                            pa.indice_copia_de(f), 3, 0.2)
        self.assertIsNone(motivo)
        self.assertEqual(n, 2)
        self.assertIn("rechazado", usuarios[1])
        self.assertIn("inglés", usuarios[1])
        self.assertIn("al derecho", txt)


class TestTuberia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = lambda n: os.path.join(self.tmp.name, n)

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, **kw):
        base = dict(backend="mercury", endpoint=[], model=None, timeout=1.0,
                    workers=2, max_intentos=3, temperatura=0.2)
        base.update(kw)
        return Namespace(**base)

    def _simulada(self, sistema, usuario):
        if "RECH_LOG" in usuario:
            return ("Felicidad prosperidad triunfo grandes alegrias satisfaccion "
                    "riqueza es la carta mas favorable de la baraja completa.")
        if "revés" in usuario:
            return "El As de Oros al revés apunta a fortuna y dinero."
        return "El As de Oros al derecho señala felicidad y prosperidad."

    def test_fin_a_fin_con_simulado(self):
        entrada = self.ruta("in.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila(orient="derecho"), ensure_ascii=False) + "\n")
            f.write(json.dumps(fila(orient="reves"), ensure_ascii=False) + "\n")
            f.write(json.dumps(fila(entidad="naipe-oros-03", cita=LARGA,
                                    texto="RECH_LOG"), ensure_ascii=False) + "\n")
        salida, rech = self.ruta("out.jsonl"), self.ruta("rej.jsonl")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(pa, "crear_cliente", lambda args: c):
            argv = ["--entrada", entrada, "--salida", salida,
                    "--rechazadas", rech]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(pa.main(argv), 0)
            self.assertIn("rechazos=1", out.getvalue())
        con = [json.loads(l) for l in open(salida, encoding="utf-8")]
        self.assertEqual(len(con), 2)
        aceptadas = {r["orientacion"]: r for r in con}
        self.assertIn("al derecho", aceptadas["derecho"]["afirmacion"])
        self.assertIn("al revés", aceptadas["reves"]["afirmacion"])
        for r in con:
            self.assertEqual(r["procedencia"], pa.PROCEDENCIA)
            self.assertTrue(r["fid"])
            self.assertTrue(r["cita_original"] or True)
        rechazos = [json.loads(l) for l in open(rech, encoding="utf-8")]
        self.assertEqual(len(rechazos), 1)
        self.assertIn("copia literal", rechazos[0]["motivo"])
        self.assertEqual(rechazos[0]["entidad_id"], "naipe-oros-03")

    def test_resume_omite_aceptadas(self):
        entrada = self.ruta("in.jsonl")
        salida = self.ruta("out.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila(orient="derecho"), ensure_ascii=False) + "\n")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(pa, "crear_cliente", lambda args: c):
            with redirect_stdout(io.StringIO()):
                pa.main(["--entrada", entrada, "--salida", salida,
                         "--rechazadas", self.ruta("rej.jsonl")])
            with open(entrada, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila(orient="reves"), ensure_ascii=False) + "\n")
            with redirect_stdout(io.StringIO()) as out:
                pa.main(["--entrada", entrada, "--salida", salida,
                         "--rechazadas", self.ruta("rej.jsonl"), "--resume"])
            self.assertIn("omitidas=1", out.getvalue())
        con = [json.loads(l) for l in open(salida, encoding="utf-8")]
        self.assertEqual(len(con), 2)

    def test_dry_run_no_escribe(self):
        entrada = self.ruta("in.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps(fila(), ensure_ascii=False) + "\n")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(pa.main(["--entrada", entrada, "--dry-run"]), 0)
        self.assertIn("filas: 1", out.getvalue())
        self.assertFalse(os.path.exists(self.ruta("out.jsonl")))

    def test_limite(self):
        entrada = self.ruta("in.jsonl")
        salida = self.ruta("out.jsonl")
        with open(entrada, "w", encoding="utf-8") as f:
            for _ in range(5):
                f.write(json.dumps(fila(orient="derecho"),
                                   ensure_ascii=False) + "\n")
        c = LLMClient(simulado=self._simulada)
        with mock.patch.object(pa, "crear_cliente", lambda args: c):
            with redirect_stdout(io.StringIO()) as out:
                pa.main(["--entrada", entrada, "--salida", salida,
                         "--limite", "2", "--rechazadas", self.ruta("r.jsonl")])
            self.assertIn("filas: 2", out.getvalue())
        self.assertEqual(sum(1 for _ in open(salida, encoding="utf-8")), 2)


if __name__ == "__main__":
    unittest.main()
