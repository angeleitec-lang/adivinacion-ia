"""Tests del juez de evidencias (T22): candidatos, validación, anclaje y salida."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest


import juez


def _seccion(titulo, texto, id_libro="libro-demo"):
    return {
        "seccion": 1,
        "titulo": titulo,
        "texto": texto,
        "chars": len(texto),
        "id_libro": id_libro,
        "posicion": 0,
    }


class CandidatosTarot(unittest.TestCase):
    """Paso 1 determinista: candidatos de entidad en secciones de naipes."""

    def _ids(self, seccion):
        return {c["entidad_id"] for c in juez.candidatos_seccion(seccion)}

    def test_the_fool_con_interpretacion(self):
        seccion = _seccion(
            "The Fool",
            "The Fool stands at the edge of the cliff and teaches new "
            "beginnings. The number of The Fool is often read as zero, a "
            "journey that starts in innocence and spontaneity.")
        self.assertIn("tarot-mayor-01", self._ids(seccion))

    def test_seccion_sin_entidades_no_da_candidatos(self):
        seccion = _seccion(
            "Nota del editor",
            "Esta impresión de la corte se realizó con planchas de cobre "
            "durante el siglo XVIII y sobrevive en un único ejemplar "
            "conservado en una biblioteca municipal de provincia.")
        self.assertEqual(self._ids(seccion), set())

    def test_baraja_espanola_as_de_oros(self):
        seccion = _seccion(
            "El as de oros",
            "En la baraja española el as de oros anuncia comienzos "
            "prósperos en el plano material y se asocia con la riqueza.")
        ids = self._ids(seccion)
        self.assertIn("naipe-oros-01", ids)

    def test_tarot_en_espanol(self):
        seccion = _seccion(
            "La Emperatriz",
            "La Emperatriz representa la fertilidad y la abundancia; "
            "invertida puede señalar dependencia afectiva.")
        self.assertIn("tarot-mayor-04", self._ids(seccion))


class CandidatosAstroNumerologia(unittest.TestCase):
    """Paso 1 para astrología y numerología."""

    def _ids(self, seccion):
        return {c["entidad_id"] for c in juez.candidatos_seccion(seccion)}

    def test_sol_en_leo_da_planeta_y_signo(self):
        seccion = _seccion(
            "El Sol en el zodiaco",
            "Con el Sol en Leo la vitalidad se expresa con teatralidad; "
            "es un signo de fuego regido por el Sol.")
        ids = self._ids(seccion)
        self.assertIn("leo|signo", ids)
        self.assertIn("sol|leo|planeta_en_signo", ids)

    def test_camino_de_vida_siete(self):
        seccion = _seccion(
            "El número siete",
            "Si tu camino de vida es el 7, la introspección y el estudio "
            "marcan tu manera de estar en el mundo.")
        self.assertIn("7|camino_de_vida", self._ids(seccion))

    def test_planeta_en_casa(self):
        seccion = _seccion(
            "Venus en la carta",
            "Venus en casa 7 trae el vínculo de pareja al centro del mapa "
            "natal y suaviza los tratos.")
        self.assertIn("venus|casa7|planeta_en_casa", self._ids(seccion))

    def test_titulo_apunta_a_entidad(self):
        seccion = _seccion(
            "The High Priestess",
            "This figure keeps the veil between the seen and the unseen, "
            "guarding intuition and silent knowledge.")
        self.assertIn("tarot-mayor-03", self._ids(seccion))


if __name__ == "__main__":
    unittest.main()


import json as _json

import cobertura
import llm_client


_CANDIDATOS = [
    {"entidad_id": "tarot-mayor-01", "familia": "tarot", "nombre": "El Loco"},
    {"entidad_id": "tarot-mayor-20", "familia": "tarot", "nombre": "El Sol"},
]


class ParsearRespuesta(unittest.TestCase):
    """T22.2: parser y validador estricto de la respuesta del juez."""

    def _juicio(self, texto):
        return juez.parsear_respuesta(texto, _CANDIDATOS)

    def test_json_en_bloque_de_codigo(self):
        texto = ('Aquí está mi juicio:\n```json\n'
                 '{"tipo": "conocimiento", "calidad": 4, "idioma": "es", '
                 '"entidades": [{"entidad_id": "tarot-mayor-01", '
                 '"facetas": ["significado_general", "amor"]}]}'
                 '\n```')
        juicio = self._juicio(texto)
        self.assertEqual(juicio["tipo"], "conocimiento")
        self.assertEqual(juicio["calidad"], 4)
        self.assertEqual(juicio["entidades"][0]["facetas"],
                         ["significado_general", "amor"])

    def test_json_sin_bloque(self):
        texto = _json.dumps({
            "tipo": "lectura_trabajada", "calidad": 3, "idioma": "en",
            "entidades": [{"entidad_id": "tarot-mayor-20",
                           "facetas": ["simbolismo"]}]})
        juicio = self._juicio(texto)
        self.assertEqual(juicio["tipo"], "lectura_trabajada")
        self.assertEqual(juicio["idioma"], "en")

    def test_faltan_campos_obligatorios(self):
        with self.assertRaises(ValueError):
            self._juicio('{"calidad": 4, "idioma": "es", "entidades": []}')

    def test_tipo_invalido(self):
        with self.assertRaises(ValueError):
            self._juicio('{"tipo": "chorrada", "calidad": 4, "idioma": "es",'
                         ' "entidades": []}')

    def test_calidad_fuera_de_rango(self):
        for calidad in (0, 6, "alta"):
            with self.subTest(calidad=calidad):
                with self.assertRaises(ValueError):
                    self._juicio(_json.dumps({
                        "tipo": "conocimiento", "calidad": calidad,
                        "idioma": "es", "entidades": []}))

    def test_entidades_fuera_de_candidatos_se_descartan(self):
        texto = _json.dumps({
            "tipo": "conocimiento", "calidad": 4, "idioma": "es",
            "entidades": [{"entidad_id": "tarot-mayor-01",
                           "facetas": ["amor"]},
                          {"entidad_id": "venus|leo|planeta_en_signo",
                           "facetas": ["significado_general"]}]})
        juicio = self._juicio(texto)
        self.assertEqual([e["entidad_id"] for e in juicio["entidades"]],
                         ["tarot-mayor-01"])

    def test_facetas_invalidas_se_descartan(self):
        texto = _json.dumps({
            "tipo": "conocimiento", "calidad": 4, "idioma": "es",
            "entidades": [{"entidad_id": "tarot-mayor-01",
                           "facetas": ["amor", "faceta_inventada",
                                       "significado_general"]}]})
        juicio = self._juicio(texto)
        self.assertEqual(juicio["entidades"][0]["facetas"],
                         ["amor", "significado_general"])

    def test_idioma_desconocido_pasa_a_otro(self):
        texto = _json.dumps({
            "tipo": "conocimiento", "calidad": 4, "idioma": "de",
            "entidades": []})
        self.assertEqual(self._juicio(texto)["idioma"], "otro")

    def test_json_roto_lanza_valor_error(self):
        with self.assertRaises(ValueError):
            self._juicio("no hay ningún json aquí")

    def test_entidades_no_lista(self):
        with self.assertRaises(ValueError):
            self._juicio('{"tipo": "conocimiento", "calidad": 4,'
                         ' "idioma": "es", "entidades": "tarot-mayor-01"}')


class JuzgarSeccion(unittest.TestCase):
    """T22.2: la llamada al LLM admite un reintento y si no, `error`."""

    def test_reintento_tras_json_invalido(self):
        respuestas = ["pura paja sin json",
                      _json.dumps({"tipo": "conocimiento", "calidad": 4,
                                   "idioma": "es",
                                   "entidades": [{"entidad_id":
                                                   "tarot-mayor-01",
                                                   "facetas": ["amor"]}]})]
        llamadas = []

        def simulado(sistema, usuario):
            llamadas.append(usuario)
            return respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]

        cliente = llm_client.LLMClient(simulado=simulado)
        juicio = juez.juzgar_seccion(cliente, _seccion("The Fool", "texto"),
                                    _CANDIDATOS)
        self.assertEqual(juicio["tipo"], "conocimiento")
        self.assertEqual(len(llamadas), 2)

    def test_error_tras_dos_fallos(self):
        def simulado(sistema, usuario):
            return "sin json"

        cliente = llm_client.LLMClient(simulado=simulado)
        juicio = juez.juzgar_seccion(cliente, _seccion("The Fool", "texto"),
                                    _CANDIDATOS)
        self.assertEqual(juicio["tipo"], "error")

    def test_prompt_trunca_seccion_y_lista_candidatos(self):
        capturado = {}

        def simulado(sistema, usuario):
            capturado["sistema"] = sistema
            capturado["usuario"] = usuario
            return _json.dumps({"tipo": "relleno", "calidad": 1,
                                "idioma": "es", "entidades": []})

        cliente = llm_client.LLMClient(simulado=simulado)
        largo = "palabra " * 2000
        juez.juzgar_seccion(cliente, _seccion("The Fool", largo),
                            _CANDIDATOS)
        self.assertLessEqual(len(capturado["usuario"]), 9000)
        self.assertIn("tarot-mayor-01", capturado["usuario"])
        self.assertIn("El Loco", capturado["usuario"])


class AnclajeFacetas(unittest.TestCase):
    """T22.3: una faceta solo se acepta si el texto contiene alguna de sus
    palabras clave (significado_general y simbolismo están exentos)."""

    def test_amor_aceptada_con_pareja(self):
        texto = "El dos de copas señala un encuentro de pareja feliz."
        self.assertEqual(juez.facetas_ancladas(["amor"], texto), ["amor"])

    def test_amor_descartada_sin_palabra_clave(self):
        texto = "Esta lámina muestra una figura alegórica con un manto azul."
        self.assertEqual(juez.facetas_ancladas(["amor"], texto), [])

    def test_trabajo_dinero_salud(self):
        texto = ("El cuatro de bastos promete éxito en el empleo y "
                 "estabilidad financiera, aunque conviene cuidar el cuerpo.")
        aceptadas = juez.facetas_ancladas(["trabajo", "dinero", "salud"],
                                          texto)
        self.assertEqual(aceptadas, ["trabajo", "dinero", "salud"])

    def test_derecha_invertida_con_al_reves(self):
        for frase in ("aceptada invertida", "saca la carta al revés"):
            with self.subTest(frase=frase):
                self.assertEqual(
                    juez.facetas_ancladas(["derecha_invertida"], frase),
                    ["derecha_invertida"])

    def test_exentas_de_palabra_clave(self):
        texto = "párrafo sin ninguna palabra útil"
        self.assertEqual(
            juez.facetas_ancladas(["significado_general", "simbolismo"],
                                  texto),
            ["significado_general", "simbolismo"])

    def test_acentos_y_mayusculas(self):
        texto = "HABLAMOS DE SU RELACIÓN y de la ESPIRITUALIDAD del naipe."
        aceptadas = juez.facetas_ancladas(["amor", "espiritual"], texto)
        self.assertEqual(aceptadas, ["amor", "espiritual"])

    def test_constante_cubre_todas_las_facetas(self):
        todas = set()
        for facetas in cobertura.FACETAS_POR_FAMILIA.values():
            todas.update(facetas)
        self.assertTrue(todas <= set(juez.PALABRAS_CLAVE_FACETA))
        for faceta in ("significado_general", "simbolismo"):
            self.assertIsNone(juez.PALABRAS_CLAVE_FACETA[faceta])


import tempfile


class ConversiónEvidencias(unittest.TestCase):
    """T22.4: conversión de juicios a evidencias del esquema de cobertura."""

    def _fuente_libro(self):
        return {"tipo": "libro", "fuente_id": "waite-pktt",
                "dominio": "waite-pktt", "periodo": "clasica", "idioma": "en"}

    def test_evidencias_de_juicio_conocimiento(self):
        seccion = _seccion("The Fool",
                           "The Fool speaks of new starts and of a couple "
                           "in love; pareja y amor.")
        juicio = {"tipo": "conocimiento", "calidad": 4, "idioma": "en",
                  "entidades": [{"entidad_id": "tarot-mayor-01",
                                 "facetas": ["significado_general", "amor",
                                             "dinero"]}]}
        evs = juez.evidencias_de_seccion(seccion, juicio, self._fuente_libro())
        self.assertEqual({e["faceta"] for e in evs},
                         {"significado_general", "amor"})
        e = evs[0]
        self.assertEqual(e["entidad_id"], "tarot-mayor-01")
        self.assertEqual(e["tipo"], "libro")
        self.assertEqual(e["fuente_id"], "waite-pktt")
        self.assertEqual(e["periodo"], "clasica")
        self.assertEqual(e["idioma"], "en")
        self.assertEqual(e["calidad"], 4)
        self.assertNotIn("tipo_evidencia", e)

    def test_lectura_trabajada_marca_tipo_evidencia(self):
        seccion = _seccion("Tirada", "El consultante habla de su pareja.")
        juicio = {"tipo": "lectura_trabajada", "calidad": 5, "idioma": "es",
                  "entidades": [{"entidad_id": "tarot-mayor-01",
                                 "facetas": ["amor"]}]}
        evs = juez.evidencias_de_seccion(seccion, juicio, self._fuente_libro())
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["tipo_evidencia"], "lectura")

    def test_tipos_no_knowledge_no_dejan_evidencia(self):
        for tipo in ("publicidad", "relleno", "ficcion", "otro", "error"):
            juicio = {"tipo": tipo, "calidad": 4, "idioma": "es",
                      "entidades": [{"entidad_id": "tarot-mayor-01",
                                     "facetas": ["significado_general"]}]}
            evs = juez.evidencias_de_seccion(_seccion("x", "y"), juicio,
                                             self._fuente_libro())
            self.assertEqual(evs, [], tipo)

    def test_idioma_del_juicio_si_la_fuente_no_lo_sabe(self):
        fuente = {"tipo": "libro", "fuente_id": "anon", "dominio": "anon",
                  "periodo": "moderna", "idioma": None}
        juicio = {"tipo": "conocimiento", "calidad": 3, "idioma": "es",
                  "entidades": [{"entidad_id": "tarot-mayor-01",
                                 "facetas": ["significado_general"]}]}
        evs = juez.evidencias_de_seccion(_seccion("t", "x"), juicio, fuente)
        self.assertEqual(evs[0]["idioma"], "es")

    def test_fuente_desconocida_es_moderna(self):
        meta = juez.cargar_meta_libros([])
        fuente = juez.fuente_de_seccion(
            _seccion("t", "x", id_libro="no-existe"), meta)
        self.assertEqual(fuente["periodo"], "moderna")


class EscrituraReanudable(unittest.TestCase):
    """T22.4: relanzar el procesamiento no repite llamadas al LLM."""

    def _simulado(self, llamadas):
        def simulado(sistema, usuario):
            llamadas.append(usuario)
            id_m = "tarot-mayor-01"
            return ("```json\n%s\n```" % _json.dumps({
                "tipo": "conocimiento", "calidad": 4, "idioma": "es",
                "entidades": [{"entidad_id": id_m,
                               "facetas": ["significado_general"]}]}))
        return simulado

    def _secciones(self):
        return [
            _seccion("The Fool", "texto primero sobre la pareja"),
            _seccion("The Fool", "texto segundo distinto"),
            _seccion("Nota", "sin entidades en absoluto: planchas de cobre "
                     "del siglo XVIII conservadas en vitrina."),
        ]

    def test_relanzamiento_no_repite_llamadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            llamadas = []
            cliente = llm_client.LLMClient(simulado=self._simulado(llamadas))
            stats1 = juez.procesar_secciones(self._secciones(), cliente, tmp,
                                             workers=1)
            n1 = len(llamadas)
            self.assertEqual(n1, 2)  # la sección sin candidatos no llama
            self.assertGreater(stats1["evidencias"], 0)
            stats2 = juez.procesar_secciones(self._secciones(), cliente, tmp,
                                             workers=1)
            self.assertEqual(len(llamadas), n1)  # ninguna llamada nueva
            self.assertEqual(stats2["reaprovechadas"], 2)
            with open(os.path.join(tmp, "evidencias.jsonl"),
                      encoding="utf-8") as fh:
                lineas = [l for l in fh if l.strip()]
            self.assertEqual(len(lineas), stats1["evidencias"])

    def test_evidencias_se_regeneran_desde_juicios_sin_llamada(self):
        with tempfile.TemporaryDirectory() as tmp:
            llamadas = []
            cliente = llm_client.LLMClient(simulado=self._simulado(llamadas))
            juez.procesar_secciones(self._secciones(), cliente, tmp,
                                    workers=1)
            # Se borra el fichero de evidencias: debe regenerarse de juicios.
            os.remove(os.path.join(tmp, "evidencias.jsonl"))
            n = len(llamadas)
            stats = juez.procesar_secciones(self._secciones(), cliente, tmp,
                                            workers=1)
            self.assertEqual(len(llamadas), n)
            self.assertGreaterEqual(stats["evidencias"], 1)

    def test_limite_de_secciones(self):
        with tempfile.TemporaryDirectory() as tmp:
            llamadas = []
            cliente = llm_client.LLMClient(simulado=self._simulado(llamadas))
            juez.procesar_secciones(self._secciones(), cliente, tmp,
                                    workers=1, limite=1)
            self.assertEqual(len(llamadas), 1)

    def test_juicios_quedan_en_fichero(self):
        with tempfile.TemporaryDirectory() as tmp:
            llamadas = []
            cliente = llm_client.LLMClient(simulado=self._simulado(llamadas))
            juez.procesar_secciones(self._secciones(), cliente, tmp,
                                    workers=1)
            with open(os.path.join(tmp, "juicios.jsonl"),
                      encoding="utf-8") as fh:
                registros = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(len(registros), 2)
            self.assertEqual({r["juicio"]["tipo"] for r in registros},
                             {"conocimiento"})
