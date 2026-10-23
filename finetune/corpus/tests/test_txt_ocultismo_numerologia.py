# -*- coding: utf-8 -*-
"""Tests del módulo txt_ocultismo_numerologia (T133)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cobertura
import txt_ocultismo_numerologia as mod

FASE0 = "/Users/angelgonzalez/fase0/txt_ocultismo_numerologia"
DICC_REAL = "/Users/angelgonzalez/adivinacion-ia/_txt/diccionario_ciencias_ocultas_djvu.txt"
NUM_REAL = "/Users/angelgonzalez/adivinacion-ia/_txt/numerologia_facil_djvu.txt"


class TestLimpieza(unittest.TestCase):
    def test_unir_hyphen_y_ruido(self):
        lineas = [
            (1, "Esto es cui-"),
            (2, "dado que se une."),
            (3, "Otro ejemplo¬"),
            (4, "pegado."),
            (5, "42"),
            (6, "CAF"),
            (7, "Texto normal."),
        ]
        bloques = [t for _, t in mod._unir_hyphen(lineas, skip_re=mod._RUNNING_HEADER_RE)]
        self.assertIn("Esto es cuidado que se une.", bloques)
        self.assertIn("Otro ejemplopegado.", bloques)
        self.assertNotIn("42", bloques)
        self.assertNotIn("CAF", bloques)
        self.assertIn("Texto normal.", bloques)

    def test_calidad_ocr(self):
        self.assertEqual(mod.calidad_ocr("muy corta"), (False, "corta"))
        self.assertEqual(
            mod.calidad_ocr("1234 5678 90!! ?? @@ 1234 5678 90!! ?? @@"),
            (False, "ilegible"))
        bueno = "Esta entrada tiene letras suficientes para considerarse legible y pasa."
        self.assertEqual(mod.calidad_ocr(bueno), (True, None))


class TestFamilias(unittest.TestCase):
    def test_deteccion(self):
        self.assertEqual(mod.familias_de("El tarot y sus arcanos"), ["tarot"])
        self.assertIn("numerologia", mod.familias_de("la numerología pitagórica y la cábala"))
        self.assertIn("astrologia", mod.familias_de("Marte en Aries, planeta del zodíaco"))
        self.assertIn("naipes", mod.familias_de("los oros y las copas de la baraja"))
        self.assertIn("adivinacion", mod.familias_de("la piromancia y el oráculo"))
        self.assertEqual(mod.familias_de("texto sin tema"), [])

    def test_prioridad_orden(self):
        familias = mod.familias_de("tarot y numerologia y astrologia")
        self.assertEqual(familias[0], "tarot")
        self.assertEqual(familias[1], "numerologia")


class TestSegmentarDiccionario(unittest.TestCase):
    def setUp(self):
        self.lineas = [
            "Portada del libro",
            "indice vario",
            "que no es entrada",
            "porque no lleva raya",
            "",
            "CABET — Limaduras de hierro.",
            "CAF",
            "CABALA — Doctrina secreta que asocia el número 7 con el camino de",
            "vida y el año personal, según la cábala hebrea de los números.",
            "MAG",
            "SILLAS — Muebles para sentarse, sin relación adivinatoria alguna.",
            "Acultomancia — Por las agujas.",
            "ANDROMEDA — Constelación boreal asociada a un planeta del zodíaco en",
            "la lectura astral de los cielos antiguos y sus mitos.",
        ]

    def test_entradas_y_exclusiones(self):
        original = mod._FRONT_MATTER_HASTA
        mod._FRONT_MATTER_HASTA = 0
        try:
            entradas = mod.segmentar_diccionario("\n".join(self.lineas))
        finally:
            mod._FRONT_MATTER_HASTA = original
        heads = [e["head"] for e in entradas]
        self.assertIn("CABET", heads)
        self.assertIn("CABALA", heads)
        self.assertIn("ANDROMEDA", heads)
        self.assertNotIn("CAF", heads)
        self.assertNotIn("MAG", heads)
        self.assertNotIn("Acultomancia", heads)
        self.assertNotIn("Portada del libro", heads)

    def test_completo_clasifica(self):
        import tempfile as _tf
        with _tf.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                   encoding="utf-8") as fh:
            fh.write("\n" * mod._FRONT_MATTER_HASTA)
            fh.write("\n".join(self.lineas[5:]))
            ruta = fh.name
        try:
            con_cand, rechazos, sin_ent, informe = (
                mod.segmentar_diccionario_completo(ruta))
        finally:
            os.unlink(ruta)
        self.assertEqual(informe["entradas"], 4)
        rechazos_by = {r["head"]: r["motivo"] for r in rechazos}
        self.assertEqual(rechazos_by.get("CABET"), "corta")
        cand_ids = {x["titulo"] for x in con_cand}
        self.assertIn("CABALA", cand_ids)
        self.assertNotIn("ANDROMEDA", cand_ids)
        sin_ids = {r["head"] for r in sin_ent}
        self.assertIn("ANDROMEDA", sin_ids)
        self.assertNotIn("SILLAS", cand_ids | sin_ids | set(rechazos_by))


class TestSegmentarNumerologia(unittest.TestCase):
    def setUp(self):
        self.lineas = [
            "Prefacio del libro",
            "1  (UM):  O  QUE  LIDERA",
            "Palavras-chave:  lider,  iniciativa.",
            "El número uno habla de comienzos y liderazgo personal.",
            "Características  positivas:  corajoso,  decidido.",
            "Características  negativas:  arrogante,  egoísta.",
            "Missão  a  cumprir:  aprender  a  liderar  com  humildade.",
            "2  (DOIS):  O  QUE  COLABORA",
            "Palavras-chave:  parceria,  diplomacia.",
            "El dos coopera y equilibra las relaciones.",
            "Características  positivas:  sensível,  justo.",
            "Características  negativas:  dependente,  indeciso.",
            "Missão  a  cumprir:  cooperar  sem  perder  a  identidade.",
            "Através dessas definições, Fernando entendeu seu caminho.",
            "Os Números Mestres",
            "Introducción a los números maestros 11 y 22.",
            "11  -  A  FORÇA",
            "Palavras-chave:  força,  inspiração.",
            "El once canaliza la fuerza espiritual.",
            "Através dessas definições, o onze inspira.",
            "Suas virtudes:  coraje  espiritual.",
            "Seus desafios:  nerviosismo.",
            "22  ou  0  -  O  LOUCO",
            "Palavras-chave:  liberdade,  sabedoria.",
            "El veintidós es el loco que confía.",
            "Através dessas definições, o vinte e dois realiza.",
            "Suas virtudes:  vision  ampla.",
            "Seus desafios:  imprudencia.",
            "Assim como os números mestres, todos somos únicos.",
            "Fazendo Previsões",
            "Capítulo de predicciones que no procesamos.",
        ]

    def test_bloques(self):
        bloques = mod.segmentar_numerologia("\n".join(self.lineas))
        claves = {(b["numero"], b["bloque"]) for b in bloques}
        self.assertEqual(claves, {
            (1, "general"), (1, "sombra"),
            (2, "general"), (2, "sombra"),
            (11, "general"), (11, "sombra"),
            (22, "general"), (22, "sombra"),
        })
        for b in bloques:
            self.assertTrue(b["texto"].strip())

    def test_evidencias_ids_validos(self):
        bloques = mod.segmentar_numerologia("\n".join(self.lineas))
        evs = mod.evidencias_numerologia(bloques)
        self.assertEqual(len(evs), 8 * 6)
        entidades = {e["entidad_id"] for e in cobertura.entidades()}
        for ev in evs:
            self.assertIn(ev["entidad_id"], entidades)
            self.assertEqual(ev["periodo"], "moderna")
            self.assertEqual(ev["idioma"], "pt")
            self.assertIn(ev["faceta"], {"significado_general", "luz_sombra"})
        hashes = {ev["hash_seccion"] for ev in evs}
        self.assertEqual(len(hashes), 8)


class _ClienteStub(object):
    def __init__(self, respuestas):
        self._r = respuestas
        self.llamadas = 0

    def chat_json(self, system, user, max_tokens=1500):
        self.llamadas += 1
        return self._r


class TestAfirmaciones(unittest.TestCase):
    def setUp(self):
        if not os.path.isdir("/Users/angelgonzalez/fase0"):
            self.skipTest("fase0 no disponible")
        self.wd = tempfile.mkdtemp(prefix="t133_test_", dir="/Users/angelgonzalez/fase0")
        os.makedirs(os.path.join(self.wd, "secciones"))
        os.makedirs(os.path.join(self.wd, "rechazos"))
        os.makedirs(os.path.join(self.wd, "resumenes"))
        os.makedirs(os.path.join(self.wd, "evidencias"))
        os.makedirs(os.path.join(self.wd, "afirmaciones"))
        texto = ("El numero uno representa el liderazgo y el inicio de todo ciclo "
                "personal en la numerologia pitagorica moderna que estudia los "
                "caminos del alma y el destino de las personas a lo largo de la "
                "vida entera.")
        seccion = {"id_libro": mod.ID_NUMEROLOGIA, "seccion": 11,
                   "titulo": "1 general", "texto": texto}
        with open(os.path.join(self.wd, "secciones", mod.ID_NUMEROLOGIA + ".jsonl"),
                 "w", encoding="utf-8") as fh:
            fh.write(json.dumps(seccion) + "\n")
        ev = {
            "entidad_id": "1|alma", "faceta": "significado_general",
            "fuente_id": mod.ID_NUMEROLOGIA, "dominio": mod.ID_NUMEROLOGIA,
            "idioma": "pt", "periodo": "moderna", "calidad": 4, "tipo": "libro",
            "hash_seccion": mod.juez.hash_seccion(seccion),
        }
        with open(os.path.join(self.wd, "evidencias", "evidencias.jsonl"),
                 "w", encoding="utf-8") as fh:
            fh.write(json.dumps(ev) + "\n")

    def tearDown(self):
        shutil.rmtree(self.wd, ignore_errors=True)

    def test_afirmacion_valida_y_anti_copia(self):
        copia = ("El numero uno representa el liderazgo y el inicio de todo ciclo "
                "personal en la numerologia pitagorica moderna que estudia los "
                "caminos del alma y el")
        buena = "El 1 simboliza el arranque y la iniciativa personal."
        cita = "liderazgo y el inicio de todo ciclo"
        cliente = _ClienteStub({
            "afirmaciones": [
                {"afirmacion": buena, "cita_original": cita, "contradice_kb": False},
                {"afirmacion": copia, "cita_original": cita, "contradice_kb": False},
            ]
        })
        stats = mod.procesar_afirmaciones(self.wd, cliente=cliente)
        self.assertEqual(stats["afirmaciones"], 1)
        self.assertEqual(stats["descartadas_copia"], 1)
        salida = os.path.join(self.wd, "afirmaciones", "afirmaciones_txt_ocultismo.jsonl")
        with open(salida, encoding="utf-8") as fh:
            regs = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(regs), 1)
        self.assertEqual(regs[0]["entidad_id"], "1|alma")
        self.assertIn("apuntes TXT del usuario", regs[0]["procedencia"])

    def test_reanudacion_por_diario(self):
        cliente = _ClienteStub({"afirmaciones": []})
        mod.procesar_afirmaciones(self.wd, cliente=cliente)
        self.assertEqual(cliente.llamadas, 1)
        mod.procesar_afirmaciones(self.wd, cliente=cliente)
        self.assertEqual(cliente.llamadas, 1)


@unittest.skipUnless(os.path.isfile(DICC_REAL) and os.path.isfile(NUM_REAL),
                    "fuentes reales no disponibles")
class TestFuentesReales(unittest.TestCase):
    def test_dry_run_estima_llamadas(self):
        tmp = tempfile.mkdtemp(prefix="t133_dry_", dir="/Users/angelgonzalez/fase0")
        try:
            mod.preparar_segmentacion(tmp, DICC_REAL, NUM_REAL)
            mod.procesar_determinista(tmp)
            informe = mod.medir_dry(tmp)
            self.assertGreater(informe["llamadas_juez_pendientes"], 0)
            self.assertGreater(informe["llamadas_extraccion_pendientes"], 0)
            self.assertGreaterEqual(informe["llamadas_totales_estimadas"],
                                  informe["llamadas_juez_pendientes"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ids_diccionario_en_cobertura(self):
        import juez
        secciones = mod._leer_jsonl(os.path.join(FASE0, "secciones",
                                                mod.ID_DICCIONARIO + ".jsonl"))
        entidades = {e["entidad_id"] for e in cobertura.entidades()}
        self.assertTrue(secciones)
        for s in secciones:
            candidatos = juez.candidatos_seccion(s)
            self.assertTrue(candidatos, s["titulo"])
            for c in candidatos:
                self.assertIn(c["entidad_id"], entidades)


if __name__ == "__main__":
    unittest.main()
