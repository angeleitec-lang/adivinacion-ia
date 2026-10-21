#!/usr/bin/env python3
"""Tests de variedad de estilo de T108 en prompts y ejecutor."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import generate_tasks as gt  # noqa: E402

KB = {
    "tarot": gt.load_kb("tarot.json"),
    "astrologia": gt.load_kb("astrologia.json"),
    "numerologia": gt.load_kb("numerologia.json"),
    "baraja": gt.load_kb("baraja_espanola.json"),
}

UNIVERSO = [c["nombre"] for c in KB["tarot"]["mayores"] + KB["tarot"]["menores"]]
BUENA = "El Loco abre tu camino: es un comienzo lleno de posibilidad."
PAYLOAD_TAROT = json.dumps(
    {"carta": {"nombre": "El Loco", "invertida": False}, "contexto": "trabajo"},
    ensure_ascii=False,
)


def tarea_tarot(cartas=None, contexto="amor", familia="tarot_3"):
    return {
        "familia": familia,
        "contexto": contexto,
        "pregunta": "¿Qué energía hay en mi vida sentimental?",
        "cartas": cartas or [{"nombre": "El Loco", "invertida": False}],
        "universo_cartas": UNIVERSO,
    }


def prompt_base_esperado(tarea):
    calc = tarea.get("calculos") or {}
    f = tarea.get("familia", "")
    partes = (
        fp._cuerpo(tarea, calc),
        fp._esquema_texto(tarea),
        fp._referencia(tarea, KB, calc),
        fp.INSTRUCCIONES.get(f, "Interpreta la consulta con las técnicas indicadas."),
    )
    return {"system": fp.SYSTEM, "user": "\n\n".join(p for p in partes if p)}


class ClienteGuion:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def chat(self, sistema, usuario, **kwargs):
        self.llamadas.append((sistema, usuario))
        if len(self.respuestas) > 1:
            return self.respuestas.pop(0)
        return self.respuestas[0]


class TestCompatibilidad(unittest.TestCase):
    def test_estilo_none_es_identico_al_prompt_base(self):
        t = tarea_tarot()
        self.assertEqual(fp.construir_prompt(t, KB, {}), prompt_base_esperado(t))

    def test_base_y_vacio_son_identicos_al_prompt_base(self):
        t = tarea_tarot()
        esperado = prompt_base_esperado(t)
        for valor in ("base", "", None):
            self.assertEqual(fp.construir_prompt(t, KB, {}, estilo=valor), esperado)

    def test_estilo_auto_anade_bloque_sin_tocar_el_resto(self):
        t = tarea_tarot()
        base = fp.construir_prompt(t, KB, {})["user"]
        auto = fp.construir_prompt(t, KB, {}, estilo="auto", semilla=7)
        self.assertNotEqual(base, auto["user"])
        self.assertTrue(auto["user"].startswith(base))
        self.assertIn("ESTILO DE ESTA LECTURA", auto["user"])
        self.assertEqual(auto["system"], fp.SYSTEM)

    def test_estilo_invalido_lanza_valueerror(self):
        with self.assertRaises(ValueError):
            fp.construir_prompt(tarea_tarot(), KB, {}, estilo="inventado")

    def test_nombre_exacto_devuelve_su_bloque(self):
        p = fp.construir_prompt(tarea_tarot(), KB, {}, estilo="directo")
        self.assertIn(fp._ESTILOS_POR_NOMBRE["directo"]["apertura"], p["user"])


class TestDiversidad(unittest.TestCase):
    def test_doscientos_jobs_producen_los_doce_estilos(self):
        nombres = {fp.estilo_para_job(str(i))["nombre"] for i in range(200)}
        self.assertEqual(nombres, {e["nombre"] for e in fp.ESTILOS})

    def test_doscientos_jobs_producen_aperturas_diversas(self):
        aperturas = {fp.estilo_para_job(str(i))["apertura"] for i in range(200)}
        self.assertGreaterEqual(len(aperturas), 10)

    def test_mismo_id_mismo_estilo(self):
        self.assertEqual(fp.estilo_para_job("42"), fp.estilo_para_job("42"))


class TestPuntuarEstilo(unittest.TestCase):
    def test_texto_limpio_no_puntua(self):
        r = fp.puntuar_estilo(BUENA)
        self.assertEqual(r["puntos"], 0)
        self.assertFalse(r["apertura_vetada"])
        self.assertFalse(r["cierre_vetado"])

    def test_detecta_apertura_vetada(self):
        r = fp.puntuar_estilo("Claro, con gusto te acompaño en esta lectura. " + BUENA)
        self.assertTrue(r["apertura_vetada"])
        self.assertGreater(r["puntos"], 0)
        self.assertIn("apertura", " ".join(r["motivos"]).lower())

    def test_detecta_cierre_vetado(self):
        r = fp.puntuar_estilo(BUENA + " Estoy aquí para acompañarte.")
        self.assertTrue(r["cierre_vetado"])
        self.assertGreaterEqual(r["puntos"], 2)

    def test_detecta_muletilla(self):
        r = fp.puntuar_estilo(BUENA + " Recuerda que esto es una tendencia.")
        self.assertGreaterEqual(len(r["muletillas"]), 1)
        self.assertGreater(r["puntos"], 0)

    def test_no_rechaza_ni_rompe_con_texto_vacio(self):
        r = fp.puntuar_estilo("")
        self.assertEqual(r["puntos"], 0)


class TestReintentoEstilo(unittest.TestCase):
    def _fila(self):
        return {
            "id": 1,
            "bloque": "tarot_1",
            "payload": PAYLOAD_TAROT,
            "prompt": "Carta: El Loco.",
        }

    def test_reintenta_una_vez_si_abre_con_formula_vetada(self):
        cliente = ClienteGuion(
            ["Claro, con gusto te acompaño en esta lectura. " + BUENA, BUENA]
        )
        r = ef.procesar_una(
            self._fila(), cliente, KB, estilo="auto", estilo_reintento=True
        )
        self.assertTrue(r["ok"])
        self.assertEqual(len(cliente.llamadas), 2)
        self.assertIn("estilo:apertura_vetada", r["motivos_rechazo_previos"])

    def test_no_reintenta_si_el_texto_es_limpio(self):
        cliente = ClienteGuion([BUENA])
        r = ef.procesar_una(
            self._fila(), cliente, KB, estilo="auto", estilo_reintento=True
        )
        self.assertTrue(r["ok"])
        self.assertEqual(len(cliente.llamadas), 1)
        self.assertNotIn("estilo:apertura_vetada", r["motivos"])

    def test_sin_bandera_no_reintenta_por_estilo(self):
        cliente = ClienteGuion(
            ["Claro, con gusto te acompaño en esta lectura. " + BUENA, BUENA]
        )
        r = ef.procesar_una(
            self._fila(), cliente, KB, estilo="auto", estilo_reintento=False
        )
        self.assertTrue(r["ok"])
        self.assertEqual(len(cliente.llamadas), 1)


class TestVerificabilidad(unittest.TestCase):
    def test_prompt_con_estilo_sigue_siendo_verificable(self):
        tarea = tarea_tarot(
            [
                {"nombre": "El Loco", "invertida": False},
                {"nombre": "La Luna", "invertida": False},
            ]
        )
        p = fp.construir_prompt(tarea, KB, {}, estilo="auto", semilla=3)
        sim = ef.simulacion_fase1(p["system"], p["user"])
        ok, motivos = fp.verificar_lectura(tarea, sim)
        self.assertTrue(ok, motivos)


if __name__ == "__main__":
    unittest.main()
