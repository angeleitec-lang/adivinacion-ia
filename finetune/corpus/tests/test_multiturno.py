"""Tests del generador multi-turno en dos fases (T45).

Cubre: esquema compatible, generacion con cliente simulado, reanudacion por semilla,
reproducibilidad y el verificador con casos adversos (giro de carta, copia, falta
de hilo, longitud, idioma, ia_meta, boilerplate).
"""
import argparse
import json
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import multiturno as mt
import validate_synthetic as vs
from llm_client import LLMClient
from generate_tasks import SYSTEM, Builder
from tests.test_generate_tasks import kbs_para_test


def _args(**kw):
    d = {"min_chars": 40, "max_chars": 12000, "max_repetition": 0.12}
    d.update(kw)
    return argparse.Namespace(**d)


def _tarea_real(seed=7, n_cartas=1):
    kb_tarot, kb_astro, kb_num = kbs_para_test()
    builder = Builder(random.Random(seed), kb_tarot, kb_astro, kb_num)
    return mt.construir_tarea(builder, semilla=seed, n_cartas=n_cartas)


def _fila_happy(seed=7):
    tarea = _tarea_real(seed)
    cliente = LLMClient(simulado=mt.simulacion)
    fila, ok, motivo = mt.generar_conversacion(tarea, cliente, _args(), n_turnos=4)
    return fila, tarea, ok, motivo


def _fila_manual(cartas, respuestas, humanos=None, contexto="amor", bloque="multiturno"):
    humanos = humanos or [f"Consulta numero {i + 1} sobre el asunto" for i in range(len(respuestas))]
    conv = [{"from": "system", "value": SYSTEM}]
    for h, g in zip(humanos, respuestas):
        conv.append({"from": "human", "value": h})
        conv.append({"from": "gpt", "value": g})
    return {
        "conversations": conv,
        "turnos": len(respuestas),
        "metadatos": {
            "bloque": bloque,
            "sistema": SYSTEM,
            "cartas": cartas,
            "contexto": contexto,
            "referencia": "",
            "semilla": 1,
            "tipos": ["pregunta_inicial"] + ["seguimiento"] * (len(respuestas) - 1),
        },
    }


class TestEsquema(unittest.TestCase):
    def test_forma_sharegpt_y_claves(self):
        fila, _tarea, ok, _m = _fila_happy()
        self.assertTrue(ok)
        self.assertEqual(fila["turnos"], 4)
        conv = fila["conversations"]
        self.assertEqual(len(conv), 1 + 2 * 4)
        self.assertEqual(conv[0]["from"], "system")
        origenes = [c["from"] for c in conv[1:]]
        self.assertEqual(origenes, ["human", "gpt"] * 4)
        for c in conv:
            self.assertIn("value", c)
            self.assertTrue(str(c["value"]).strip())

    def test_helpers_validador_y_merge_funcionan(self):
        fila, _tarea, _ok, _m = _fila_happy()
        pares = vs.turnos_de(fila)
        self.assertEqual(len(pares), 4)
        self.assertTrue(vs.human_of(fila))
        self.assertTrue(vs.answer_of(fila))
        self.assertTrue(vs.system_of(fila))
        # round-trip JSON conserva claves extra
        recargada = json.loads(json.dumps(fila, ensure_ascii=False))
        self.assertEqual(recargada["turnos"], 4)
        self.assertIn("metadatos", recargada)
        self.assertIn("cartas", recargada["metadatos"])

    def test_compatible_con_validate_synthetic(self):
        fila, _tarea, ok, _m = _fila_happy()
        ok_v, why = vs.validate(fila, _args(), bloque="multiturno")
        self.assertTrue(ok_v, why)


class TestGeneracion(unittest.TestCase):
    def test_guion_simulado_devuelve_tipos(self):
        tarea = _tarea_real(seed=11)
        cliente = LLMClient(simulado=mt.simulacion)
        guion = mt.generar_guion(tarea, cliente, n_turnos=4)
        self.assertEqual(len(guion), 4)
        for t in guion:
            self.assertIn("tipo", t)
            self.assertTrue(str(t["texto"]).strip())

    def test_respuestas_alineadas_con_guion(self):
        tarea = _tarea_real(seed=12)
        cliente = LLMClient(simulado=mt.simulacion)
        guion = mt.generar_guion(tarea, cliente, n_turnos=4)
        respuestas = mt.generar_respuestas(guion, tarea, cliente)
        self.assertEqual(len(respuestas), len(guion))
        for r in respuestas:
            self.assertGreaterEqual(len(r), 40)

    def test_reanudacion_no_llama_cliente(self):
        def _boom(sistema, usuario):
            raise AssertionError("el cliente no debe llamarse al reanudar")

        tarea = _tarea_real(seed=13)
        pre = [
            {"tipo": "pregunta_inicial", "texto": "Primera pregunta valida"},
            {"tipo": "seguimiento", "texto": "Segunda pregunta valida"},
        ]
        tarea["guion"] = pre
        cliente = LLMClient(simulado=_boom)
        guion = mt.generar_guion(tarea, cliente)
        self.assertEqual(guion, pre)

    def test_reproducibilidad_por_semilla(self):
        tarea = _tarea_real(seed=14)
        cliente = LLMClient(simulado=mt.simulacion)
        g1 = mt.generar_guion(tarea, cliente, n_turnos=4)
        g2 = mt.generar_guion(tarea, cliente, n_turnos=4)
        self.assertEqual(g1, g2)

    def test_guion_invalido_agota_intentos(self):
        cliente = LLMClient(simulado=lambda s, u: "esto no es json")
        tarea = _tarea_real(seed=15)
        with self.assertRaises(ValueError):
            mt.generar_guion(tarea, cliente, n_turnos=4)


class TestVerificadorAdverso(unittest.TestCase):
    def test_invertida_llamada_al_derecho(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        g2 = ("En realidad El Loco esta al derecho y todo fluye sin bloqueos, "
              "asi que avanza sin miedo por el mismo camino de antes.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "carta_cambiada")

    def test_derecha_llamada_invertida(self):
        cartas = [{"nombre": "La Estrella", "invertida": False}]
        g1 = ("La Estrella sale al derecho y trae esperanza y calma en tu vida "
              "sentimental, con una ilusion renovada que acompana el momento.")
        g2 = ("Ahora veo La Estrella invertida, lo que bloquea esa esperanza "
              "que comentabamos antes sobre el mismo asunto.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "carta_cambiada")

    def test_turno_copia_del_anterior(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        fila = _fila_manual(cartas, [g1, g1])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "copia")

    def test_turno_sin_hilo(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        g2 = ("Manana llovera mucho yuire al mercado a comprar manzanas verdes, "
              "pan fresco y tomates maduros para la cena de toda la familia.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "sin_hilo")

    def test_turno_demasiado_corto(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        fila = _fila_manual(cartas, [g1, "Si."])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "corto")

    def test_ia_meta_rechazada(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        g2 = ("Como modelo de lenguaje no puedo ayudarte con eso, pero manteniendo "
              "el hilo de la carta invertida te suguyo observar tu calma interior.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "ia_meta")

    def test_boilerplate_rechazado(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        g2 = ("Lorem ipsum dolor sit amet, manteniendo el hilo de la carta invertida "
             "y la calma interior que ya comentabamos sobre el mismo asunto aqui.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "boilerplate")

    def test_idioma_no_espanol_rechazado(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        g2 = ("This is clearly english text about the weather and it is not spanish "
              "at all, keeping the thread of the card and the calm we discussed.")
        fila = _fila_manual(cartas, [g1, g2])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertTrue(why.startswith("idioma_"))

    def test_un_solo_turno_falla(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y pide calma interior y paciencia "
              "en el amor, mirando hacia dentro con atencion y sin prisa.")
        fila = _fila_manual(cartas, [g1])
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "sin_turnos")

    def test_etica_permite_ia_meta(self):
        cartas = [{"nombre": "El Loco", "invertida": True}]
        g1 = ("La carta El Loco aparece invertida y marca un limite: no doy "
              "diagnostico, te oriento y derivo a un profesional con calma y respeto.")
        g2 = ("Manteniendo ese limite, como modelo de lenguaje no diagnostico, pero "
              "insisto en que busques ayuda profesional para el mismo asunto de antes.")
        fila = _fila_manual(cartas, [g1, g2], bloque="etica")
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertTrue(ok, why)


class TestPromptLectura(unittest.TestCase):
    def test_una_carta_reconocible(self):
        tarea = {"cartas": [{"nombre": "El Loco", "invertida": True}], "contexto": "amor"}
        p = mt.prompt_lectura(tarea)
        self.assertIn("Carta: El Loco (invertida)", p)
        self.assertEqual(vs.extraer_cartas(p), [("El Loco", "invertida")])

    def test_varias_cartas_reconocibles(self):
        tarea = {
            "cartas": [
                {"nombre": "El Loco", "invertida": False},
                {"nombre": "La Estrella", "invertida": True},
            ],
            "contexto": "trabajo",
        }
        p = mt.prompt_lectura(tarea)
        self.assertEqual(
            vs.extraer_cartas(p),
            [("El Loco", "derecho"), ("La Estrella", "invertida")],
        )


class TestVedadosFase1(unittest.TestCase):
    """AJUSTE coordinadora: promesas, diagnosticos, juego, carta ajena y
    orientacion contraria en un turno de seguimiento deben rechazarse usando
    fase1_prompts.verificar_lectura. Base autocontenida (no depende de /tmp)."""

    CARTAS = [{"nombre": "Cinco de Copas", "invertida": False}]

    def _base(self):
        g1 = ("El Cinco de Copas sale al derecho y habla de una perdida reciente "
              "en el amor; duele, pero quedan recursos afectivos que aun sostienen "
              "tu momento presente con calma.")
        g2 = ("Entiendo ese dolor por la perdida que trae el Cinco de Copas; "
              "conviene no decidir desde la tristeza y mirar lo que aun permanece "
              "en pie a tu alrededor.")
        g3 = ("Esa misma carta te pide atravesar la pena con calma, sin negarla, "
              "y reconocer el afecto que todavia te acompana en el dia a dia.")
        g4 = ("Por eso te sugiero dar tiempo a la emocion, nombrar lo que duele "
              "y abrirte poco a poco a lo que el Cinco de Copas aun deja en pie.")
        return _fila_manual([dict(c) for c in self.CARTAS], [g1, g2, g3, g4])

    def _mod_ultimo(self, mod):
        fila = self._base()
        idx = len(fila["conversations"]) - 1
        self.assertEqual(fila["conversations"][idx]["from"], "gpt")
        fila["conversations"][idx]["value"] = mod(fila["conversations"][idx]["value"])
        return fila

    def test_base_es_valida(self):
        ok, why = mt.verificar_conversacion(self._base(), _args())
        self.assertTrue(ok, why)

    def test_promesa_vedada(self):
        fila = self._mod_ultimo(
            lambda t: t + " Te garantizo que esa persona volvera en un mes.")
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "promesa")

    def test_diagnostico_vedado(self):
        fila = self._mod_ultimo(
            lambda t: t + " Tienes depresion; deja la medicacion.")
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "diagnostico")

    def test_juego_vedado(self):
        fila = self._mod_ultimo(
            lambda t: t + " Juega el 23 en la loteria.")
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "juego")

    def test_carta_ajena_vedada(self):
        fila = self._mod_ultimo(
            lambda t: t.replace("Cinco de Copas", "Tres de Espadas"))
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "carta_ajena")

    def test_orientacion_contraria_vedada(self):
        # Turno de seguimiento que afirma inversion sin nombrar la carta
        # (escenario real del AJUSTE): lo pilla fase1, no _orientacion_turno.
        fila = self._mod_ultimo(
            lambda t: ("Entiendo lo que sientes; como esta invertida, cambia todo "
                      "y conviene mirar esa pena que aun duele con calma."))
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "orientacion")

    def test_orientacion_contraria_con_carta_nombrada(self):
        # Variante: carta derecho nombrada junto a "invertida" -> ya la pilla
        # el check propio de multiturno como carta_cambiada.
        fila = self._mod_ultimo(
            lambda t: t + " El Cinco de Copas esta invertida y lo cambia todo.")
        ok, why = mt.verificar_conversacion(fila, _args())
        self.assertFalse(ok)
        self.assertEqual(why, "carta_cambiada")


if __name__ == "__main__":
    unittest.main()
