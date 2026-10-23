import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import unittest

import fase1_prompts as fp
import ejecutor_fase1 as ex
import regenerar_fuera_alcance as rf


def tarea_fuera(tecnica="quiromancia", pregunta="¿Qué me dice la línea de mi vida?"):
    return {
        "familia": "fuera_alcance",
        "tecnica": tecnica,
        "pregunta": pregunta,
        "calculos": {},
        "universo_cartas": ["El Loco", "El Mago"],
    }


class TestConstruirJobs(unittest.TestCase):
    def test_n_y_bloque(self):
        filas = rf.construir_jobs(12, seed=7)
        self.assertEqual(len(filas), 12)
        for f in filas:
            self.assertEqual(f[0], "fuera_alcance")

    def test_validacion_limpia(self):
        filas = rf.construir_jobs(20, seed=1)
        self.assertEqual(rf.validar_jobs(filas), [])

    def test_n_invalido(self):
        with self.assertRaises(ValueError):
            rf.construir_jobs(0)
        with self.assertRaises(ValueError):
            rf.construir_jobs(-3)

    def test_max_tokens_coincide(self):
        filas = rf.construir_jobs(3, seed=2)
        esperado = fp.RECOMENDACION_MAX_TOKENS["fuera_alcance"]
        for f in filas:
            self.assertEqual(f[4], esperado)


class TestValidarDetectaCorrupcion(unittest.TestCase):
    def test_prompt_mutilado(self):
        # Réplica del patrón corrupto de v1d: pregunta sustituida por "<n> arranque:".
        fila = (
            "fuera_alcance",
            "SYS",
            'Consulta fuera de alcance.\n\nPregunta del consultante: "0 Tengo curiosidad:"',
            json.dumps({"tecnica": "vidas pasadas", "pregunta": ""}),
            1536,
        )
        errores = rf.validar_jobs([fila])
        self.assertTrue(errores)
        self.assertTrue(any("corrupción" in e for e in errores))

    def test_sin_tecnica(self):
        fila = (
            "fuera_alcance", "SYS",
            'Consulta fuera de alcance.\n\nPregunta del consultante: "x"',
            json.dumps({"pregunta": "x"}), 1536,
        )
        errores = rf.validar_jobs([fila])
        self.assertTrue(any("tecnica" in e for e in errores))

    def test_sin_encabezado(self):
        fila = (
            "fuera_alcance", "SYS",
            'Algo raro.\n\nPregunta del consultante: "hola"',
            json.dumps({"tecnica": "runas", "pregunta": "hola"}), 1536,
        )
        errores = rf.validar_jobs([fila])
        self.assertTrue(any("encabezado" in e for e in errores))

    def test_bloque_inesperado(self):
        fila = ("tarot_1", "SYS", "x", "{}", 1024)
        errores = rf.validar_jobs([fila])
        self.assertTrue(any("bloque" in e for e in errores))


class TestVerificadorAdverso(unittest.TestCase):
    def test_respuesta_diagnostico_muerte_rechazada(self):
        ok, motivos = fp.verificar_lectura(
            tarea_fuera(),
            "Tu línea de la vida es corta: morirás antes de los sesenta. "
            "La palma de tu mano lo confirma.",
        )
        self.assertFalse(ok)
        self.assertTrue(any("muerte" in m or "diagnóstico" in m or "Promesa" in m
                           for m in motivos))

    def test_respuesta_sin_rechazo_rechazada(self):
        ok, motivos = fp.verificar_lectura(
            tarea_fuera(),
            "Claro, la quiromancia revela tu destino a través de la palma de tu mano.",
        )
        self.assertFalse(ok)
        self.assertTrue(any("rechaza" in m for m in motivos))

    def test_respuesta_sin_alternativa_rechazada(self):
        ok, motivos = fp.verificar_lectura(
            tarea_fuera(),
            "No puedo leer la quiromancia, eso no es lo mío. Lo siento mucho.",
        )
        self.assertFalse(ok)
        self.assertTrue(any("alternativa" in m for m in motivos))

    def test_respuesta_buena_aceptada(self):
        texto = (
            "Entiendo tu curiosidad, pero la quiromancia no forma parte de lo que "
            "ofrezco: trabajo tarot, baraja española, astrología y numerología. "
            "Lo que sí puedo hacer es una lectura simbólica con el tarot para "
            "reflexionar sobre tu momento. No sustituyo el consejo de un profesional."
        )
        ok, motivos = fp.verificar_lectura(tarea_fuera(), texto)
        self.assertTrue(ok, motivos)

    def test_otra_lengua_rechazada(self):
        # Declinación en inglés: no casa con el regex español de rechazo.
        ok, motivos = fp.verificar_lectura(
            tarea_fuera(),
            "I cannot read your palm, that is not something I do. Sorry about that.",
        )
        self.assertFalse(ok)
        self.assertTrue(any("rechaza" in m for m in motivos))

    def test_truncada_detectada(self):
        # El ejecutor marca truncado si no cierra con puntuación.
        self.assertTrue(ex.respuesta_truncada(
            "No puedo leer la quiromancia pero puedo ofrecerte tarot"))
        self.assertFalse(ex.respuesta_truncada(
            "No puedo leer la quiromancia, pero ofrezco tarot."))


class TestEstimar(unittest.TestCase):
    def test_estimacion_positiva(self):
        filas = rf.construir_jobs(50, seed=3)
        est = rf.estimar(filas)
        self.assertEqual(est["jobs"], 50)
        self.assertGreater(est["llamadas_estimadas"], 50)
        self.assertGreater(est["tokens_prompt_estimados"], 0)
        self.assertGreater(est["tokens_salida_presupuesto"], 0)

    def test_vacio(self):
        est = rf.estimar([])
        self.assertEqual(est["jobs"], 0)
        self.assertEqual(est["llamadas_estimadas"], 0)


class TestEsquemaShareGPT(unittest.TestCase):
    def test_a_sharegpt_esquema_v1d(self):
        registro = {
            "id": 999,
            "bloque": "fuera_alcance",
            "prompt_system": "Eres tarotista...",
            "prompt_user": 'Consulta fuera de alcance.\n\nPregunta del consultante: "x"',
            "respuesta": "No puedo, pero ofrezco tarot.",
            "generador": "local",
        }
        fila = ex.a_sharegpt(registro)
        self.assertEqual(fila["bloque"], "fuera_alcance")
        self.assertEqual(fila["id"], 999)
        roles = [c["from"] for c in fila["conversations"]]
        self.assertEqual(roles, ["system", "human", "gpt"])
        self.assertEqual(fila["generador"], "local")


class TestClienteNodo2(unittest.TestCase):
    def test_nodo1_prohibido(self):
        with self.assertRaises(ValueError):
            rf.crear_cliente(endpoint="http://10.0.0.3:8000/v1")

    def test_nodo2_ok(self):
        c = rf.crear_cliente(endpoint="http://10.0.0.4:8000/v1")
        self.assertEqual(len(c.endpoints), 1)
        self.assertIn("10.0.0.4", c.endpoints[0])


class TestDetectorVoseo(unittest.TestCase):
    def test_contiene_voseo_true(self):
        for t in [
            "¿Qué querés saber?",
            "Podés contarme lo que te pasa.",
            "Decime qué necesitás.",
            "Vos tenés la última palabra.",
            "Mirá lo que encontraste.",
            "Si preferís, contame.",
        ]:
            self.assertTrue(rf.contiene_voseo(t), t)

    def test_contiene_voseo_false_falsos_positivos(self):
        for t in [
            "más o menos",
            "además de eso",
            "tú estás bien",
            "que estés tranquila",
            "detrás de ti",
            "por interés propio",
            "bajo estrés",
            "a través de las cartas",
            "después veremos",
            "quizás mañana",
            "vivirás tu proceso",
            "te casarás algún día",
            "Puedes contarme qué te preocupa; estoy aquí para escucharte.",
        ]:
            self.assertFalse(rf.contiene_voseo(t), t)

    def test_verificar_voseo_rechaza(self):
        ok, motivos = rf.verificar_voseo(
            tarea_fuera(), "¿Qué querés que te diga? Contame.")
        self.assertFalse(ok)
        self.assertTrue(any("voseo" in m for m in motivos))

    def test_verificar_voseo_acepta_tuteo(self):
        ok, motivos = rf.verificar_voseo(
            tarea_fuera(),
            "Puedes contarme qué te preocupa; estoy aquí para escucharte.")
        self.assertTrue(ok)
        self.assertEqual(motivos, [])


class TestParcheTuteo(unittest.TestCase):
    def setUp(self):
        self.kb = ex.cargar_kb()

    def test_construir_prompt_inyecta_tuteo_fuera_alcance(self):
        restaurar = rf._instalar_parches_tuteo()
        try:
            d = fp.construir_prompt(tarea_fuera(), self.kb)
            self.assertIn("tuteo", d["user"])
            self.assertIn("voseo", d["user"])
        finally:
            restaurar()

    def test_parche_no_toca_no_fuera_alcance(self):
        restaurar = rf._instalar_parches_tuteo()
        try:
            tarea = {"familia": "etica", "pregunta": "¿Me lees algo?", "calculos": {}}
            d = fp.construir_prompt(tarea, self.kb)
            self.assertNotIn("nunca uses voseo", d["user"])
        finally:
            restaurar()

    def test_verificar_lectura_rechaza_voseo_fuera_alcance(self):
        restaurar = rf._instalar_parches_tuteo()
        try:
            texto = (
                "No puedo leer la quiromancia, pero podés contar con el tarot "
                "para reflexionar; no sustituyo a un profesional."
            )
            ok, motivos = fp.verificar_lectura(tarea_fuera(), texto)
            self.assertFalse(ok)
            self.assertTrue(any("voseo" in m for m in motivos))
        finally:
            restaurar()

    def test_parche_restaura_originales(self):
        orig_c = fp.construir_prompt
        orig_v = fp.verificar_lectura
        restaurar = rf._instalar_parches_tuteo()
        self.assertNotEqual(fp.construir_prompt, orig_c)
        self.assertNotEqual(fp.verificar_lectura, orig_v)
        restaurar()
        self.assertIs(fp.construir_prompt, orig_c)
        self.assertIs(fp.verificar_lectura, orig_v)


if __name__ == "__main__":
    unittest.main()
