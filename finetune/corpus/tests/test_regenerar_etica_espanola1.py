import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import unittest

import auditoria_v1d as aud
import fase1_prompts as fp
import regenerar_etica_espanola1 as re142


def tarea_etica(pregunta):
    return {"familia": "etica", "pregunta": pregunta, "calculos": {}}


def tarea_esp(nombre="As de Oros", invertida=False, contexto="amor",
              pregunta="¿Qué me espera en el amor este mes?"):
    return {
        "familia": "espanola_1",
        "pregunta": pregunta,
        "contexto": contexto,
        "mazo": "espanol",
        "cartas": [{"nombre": nombre, "invertida": invertida}],
        "universo_cartas": [nombre],
        "calculos": {},
    }


PREG_RIESGO = "Quiero morir, no es una llamada de atención, lo digo muy en serio."
PREG_NO_RIESGO = "¿Me van a conceder la pensión que pido?"


class TestConstruirJobs(unittest.TestCase):
    def test_cuentas(self):
        filas = re142.construir_jobs(semilla=142)
        etica = [f for f in filas if f[0] == "etica"]
        esp = [f for f in filas if f[0] == "espanola_1"]
        self.assertEqual(len(etica), re142.N_ETICA)
        self.assertEqual(len(esp), re142.N_ESPANOLA)

    def test_validacion_limpia(self):
        filas = re142.construir_jobs(semilla=7)
        self.assertTrue(re142.validar_jobs(filas))

    def test_max_tokens(self):
        filas = re142.construir_jobs(semilla=3)
        for f in filas:
            esperado = fp.RECOMENDACION_MAX_TOKENS[f[0]]
            self.assertEqual(f[4], esperado)

    def test_payload_marca_t142(self):
        for f in re142.construir_jobs(semilla=5):
            payload = json.loads(f[3])
            self.assertTrue(payload.get("t142"))

    def test_unicidad_prompts_guardados(self):
        filas = re142.construir_jobs(semilla=11)
        for bloque in ("etica", "espanola_1"):
            prompts = [f[2] for f in filas if f[0] == bloque]
            propios = {aud.prompt_propio(p) for p in prompts}
            self.assertGreaterEqual(len(propios) / len(prompts),
                                  re142.UMBRAL_UNICIDAD)

    def test_esp1_boilerplate_tras_pregunta(self):
        for f in re142.construir_jobs(semilla=9):
            if f[0] != "espanola_1":
                continue
            self.assertLess(f[2].index("Pregunta del consultante:"),
                           f[2].index(re142.BOILER_ESP1))
            propio = aud.prompt_propio(f[2])
            self.assertIn("pregunta del consultante", propio)

    def test_esp1_cartas_validas_kb(self):
        naipes = {n["nombre"] for n in re142._cargar_naipes()}
        self.assertEqual(len(naipes), 40)
        for f in re142.construir_jobs(semilla=4):
            if f[0] != "espanola_1":
                continue
            payload = json.loads(f[3])
            carta = payload["cartas"][0]
            self.assertIn(carta["nombre"], naipes)
            self.assertIn(carta["invertida"], (True, False))

    def test_etica_cubre_categorias(self):
        filas = re142.construir_jobs(semilla=13)
        temas = {json.loads(f[3])["tema"]
                for f in filas if f[0] == "etica"}
        self.assertEqual(temas, set(re142.ETICA_BANCO))


class TestVerificadorExtra(unittest.TestCase):
    def test_voseo_rechazado(self):
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO),
            "Contame qué te pasa, no podés seguir así.")
        self.assertTrue(any("voseo" in m for m in motivos))

    def test_024_obligatorio_en_riesgo(self):
        t = tarea_etica(PREG_RIESGO)
        motivos = re142.verificar_fila_extra(
            "etica", t, "Siento mucho tu dolor. Llama ahora al 024.")
        self.assertFalse(any("024" in m for m in motivos))
        motivos = re142.verificar_fila_extra(
            "etica", t, "Siento mucho tu dolor. Busca ayuda profesional.")
        self.assertTrue(any("024" in m for m in motivos))

    def test_024_prohibido_sin_riesgo(self):
        t = tarea_etica(PREG_NO_RIESGO)
        motivos = re142.verificar_fila_extra(
            "etica", t, "Puedes llamar al 024 si te sirve.")
        self.assertTrue(any("024" in m for m in motivos))

    def test_punto_final(self):
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO),
            "Esta respuesta no termina bien")
        self.assertTrue(any("punto" in m for m in motivos))

    def test_autodenominacion_ia(self):
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO),
            "Como asistente de IA no puedo predecir el futuro.")
        self.assertTrue(any("IA" in m for m in motivos))

    def test_ingles_rechazado(self):
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO),
            "The cards show a difficult moment for you.")
        self.assertTrue(any("inglés" in m for m in motivos))

    def test_respuesta_valida_sin_motivos(self):
        texto = ("Te escucho y tu dolor es real. La carta habla de un momento "
                "duro, pero también de recursos que ya tienes dentro. Te "
                "aconsejo apoyarte en tu médico de cabecera y en las personas "
                "que te quieren. Un abrazo fuerte.")
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO), texto)
        self.assertEqual(motivos, [])

    def test_vacio(self):
        motivos = re142.verificar_fila_extra(
            "etica", tarea_etica(PREG_NO_RIESGO), "   ")
        self.assertTrue(motivos)


class TestAntiCopia(unittest.TestCase):
    def test_copia_descartada(self):
        a = {"id": 1, "conversations": [
            {"from": "gpt", "value": "Texto largo y único de la primera fila "
                                     "que se repite después."}]}
        b = {"id": 2, "conversations": [
            {"from": "gpt", "value": "Texto largo y único de la primera fila "
                                     "que se repite después."}]}
        c = {"id": 3, "conversations": [
            {"from": "gpt", "value": "Otra lectura completamente distinta "
                                     "sobre el mismo naipe y su contexto."}]}
        mantenidas, descartes = re142.filtrar_copias(
            [a, b, c], re142._gpt_value)
        self.assertEqual([f["id"] for f in mantenidas], [1, 3])
        self.assertEqual(len(descartes), 1)

    def test_similitud_umbral(self):
        base = ("La carta muestra un momento de incertidumbre pero también de "
               "esperanza para ti en los proximos dias.")
        self.assertGreaterEqual(re142.similitud_copia(base, base),
                               re142.SIM_COPIA)
        otro = ("El naipe señala cambios en el trabajo y la necesidad de "
               "reposar y cuidar tu salud con calma y paciencia.")
        self.assertLess(re142.similitud_copia(base, otro), re142.SIM_COPIA)


class TestParchesAcotados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ejecutor_fase1 as ex
        cls.kb = ex.cargar_kb()

    def setUp(self):
        self.orig_construir = fp.construir_prompt
        self.orig_verificar = fp.verificar_lectura

    def tearDown(self):
        fp.construir_prompt = self.orig_construir
        fp.verificar_lectura = self.orig_verificar

    def test_etica_riesgo_incluye_024_y_tuteo(self):
        restaurar = re142._instalar_parches_t142(self.kb)
        try:
            d = fp.construir_prompt(tarea_etica(PREG_RIESGO), self.kb)
            self.assertIn("024", d["user"])
            self.assertIn("tuteo", d["user"])
        finally:
            restaurar()

    def test_etica_sin_riesgo_sin_024(self):
        restaurar = re142._instalar_parches_t142(self.kb)
        try:
            d = fp.construir_prompt(tarea_etica(PREG_NO_RIESGO), self.kb)
            self.assertNotIn("024", d["user"])
            self.assertIn("tuteo", d["user"])
        finally:
            restaurar()

    def test_esp1_plantilla_custom(self):
        restaurar = re142._instalar_parches_t142(self.kb)
        try:
            t = tarea_esp()
            d = fp.construir_prompt(t, self.kb)
            self.assertIn("Tirada de una carta de la baraja española",
                         d["user"])
            self.assertLess(d["user"].index("Pregunta del consultante:"),
                           d["user"].index(re142.BOILER_ESP1))
            self.assertIn("As de Oros", d["user"])
            self.assertIn("tuteo", d["user"])
            propio = aud.prompt_propio(d["user"])
            self.assertIn("pregunta del consultante", propio)
            self.assertIn("as de oros", propio)
        finally:
            restaurar()

    def test_parche_no_toca_otras_familias(self):
        t = {"familia": "tarot_1", "pregunta": "¿Qué me espera?",
             "cartas": [{"nombre": "El Loco", "invertida": False}],
             "contexto": "general", "calculos": {},
             "universo_cartas": ["El Loco"]}
        antes = fp.construir_prompt(t, self.kb)
        restaurar = re142._instalar_parches_t142(self.kb)
        try:
            despues = fp.construir_prompt(t, self.kb)
        finally:
            restaurar()
        self.assertEqual(antes["user"], despues["user"])

    def test_parche_restaura_originales(self):
        restaurar = re142._instalar_parches_t142(self.kb)
        self.assertNotEqual(fp.construir_prompt, self.orig_construir)
        restaurar()
        self.assertEqual(fp.construir_prompt, self.orig_construir)
        self.assertEqual(fp.verificar_lectura, self.orig_verificar)

    def test_verificar_parcheado_rechaza_voseo(self):
        restaurar = re142._instalar_parches_t142(self.kb)
        try:
            ok, motivos = fp.verificar_lectura(
                tarea_etica(PREG_NO_RIESGO),
                "Contame tu problema y la carta te escucha.")
            self.assertFalse(ok)
            self.assertTrue(any("voseo" in m for m in motivos))
        finally:
            restaurar()


class TestFugaEval(unittest.TestCase):
    def test_fuga_detectada_con_caso_real(self):
        casos = re142.cargar_casos_eval()
        if not casos:
            self.skipTest("sin casos de evaluacion en disco")
        caso = next(iter(casos.values()))
        texto = str(caso.get("user", ""))
        self.assertTrue(texto)
        fila = {"id": "x1", "bloque": "etica", "conversations": [
            {"from": "human", "value": texto},
            {"from": "gpt", "value": "Respuesta inventada para la prueba."}]}
        mantenidas, descartes = re142.filtrar_fuga_eval([fila], casos)
        self.assertEqual(len(descartes), 1)
        self.assertEqual(mantenidas, [])

    def test_preguntas_t142_no_fugan(self):
        casos = re142.cargar_casos_eval()
        if not casos:
            self.skipTest("sin casos de evaluacion en disco")
        filas = []
        for i, f in enumerate(re142.construir_jobs(semilla=142)):
            filas.append({"id": f"t-{i}", "bloque": f[0], "conversations": [
                {"from": "human", "value": f[2]},
                {"from": "gpt", "value": ""}]})
        _mant, descartes = re142.filtrar_fuga_eval(filas, casos)
        self.assertEqual(descartes, [])


class TestCliente(unittest.TestCase):
    def test_nodo1_permitido(self):
        self.assertIsNotNone(
            re142.crear_cliente(endpoint="http://10.0.0.3:8000/v1"))

    def test_nodo2_permitido(self):
        self.assertIsNotNone(
            re142.crear_cliente(endpoint="http://10.0.0.4:8000/v1"))

    def test_endpoint_externo_prohibido(self):
        with self.assertRaises(ValueError):
            re142.crear_cliente(endpoint="https://api.openai.com/v1")


class TestRepartoNodos(unittest.TestCase):
    def _bd_mixta(self, tmp):
        import sqlite3
        import generate_tasks as gt
        db = os.path.join(tmp, "jobs_test.db")
        con = sqlite3.connect(db)
        gt.crear_tabla(con)
        gt.insertar_jobs(con, [
            ("etica", "sys",
             'Consulta delicada.\n\nPregunta del consultante: '
             '"¿Me van a conceder la pensión que pido?"',
             json.dumps({"tema": "legal", "riesgo": False, "t142": True}), 700),
            ("espanola_1", "sys",
             'Tirada de una carta.\n\nPregunta del consultante: '
             '"¿Qué me espera en el amor?"',
             json.dumps({"cartas": [{"nombre": "As de Oros",
                                    "invertida": False}],
                         "contexto": "amor", "mazo": "espanol",
                         "t142": True}), 700),
        ])
        con.commit()
        con.close()
        return db

    def test_filtro_bloques_deja_otra_familia_pending(self):
        import tempfile
        import sqlite3
        import ejecutor_fase1 as ex
        with tempfile.TemporaryDirectory() as tmp:
            db = self._bd_mixta(tmp)

            class StubCliente:
                def chat(self, *a, **k):
                    return "x"

            ex.ejecutar(db, StubCliente(), ex.cargar_kb(), workers=1,
                       limite=5, out_dir=os.path.join(tmp, "salida"),
                       formato="sharegpt", backend=ex.GENERADOR_LOCAL,
                       bloques=("espanola_1",))
            con = sqlite3.connect(db)
            estados = {b: s for b, s in
                       con.execute("SELECT bloque, status FROM jobs")}
            con.close()
            self.assertEqual(estados["etica"], "pending")
            self.assertEqual(estados["espanola_1"], "failed")

    def test_sin_filtro_reclama_todas(self):
        import tempfile
        import sqlite3
        import ejecutor_fase1 as ex
        with tempfile.TemporaryDirectory() as tmp:
            db = self._bd_mixta(tmp)

            class StubCliente:
                def chat(self, *a, **k):
                    return "x"

            ex.ejecutar(db, StubCliente(), ex.cargar_kb(), workers=1,
                       limite=5, out_dir=os.path.join(tmp, "salida"),
                       formato="sharegpt", backend=ex.GENERADOR_LOCAL)
            con = sqlite3.connect(db)
            estados = {b: s for b, s in
                       con.execute("SELECT bloque, status FROM jobs")}
            con.close()
            self.assertEqual(estados["etica"], "failed")
            self.assertEqual(estados["espanola_1"], "failed")


if __name__ == "__main__":
    unittest.main()
