# -*- coding: utf-8 -*-
"""Tests de diversidad_dataset.py (T106) con datos sintéticos, sin red."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import diversidad_dataset as dd


def _fila(idx, bloque, respuesta, pregunta=None, contexto=None, calculos=None,
          humanos_extra=()):
    convs = [{"from": "system", "value": "Sistema"}]
    human = "Tirada de una carta de tarot.\n\n"
    if contexto:
        human += "Contexto: %s.\n" % contexto
    if pregunta:
        human += 'Pregunta del consultante: "%s"\n' % pregunta
    convs.append({"from": "human", "value": human})
    for extra in humanos_extra:
        convs.append({"from": "gpt", "value": respuesta + " base"})
        convs.append({"from": "human", "value": extra})
    convs.append({"from": "gpt", "value": respuesta})
    fila = {"id": idx, "bloque": bloque, "generador": "test",
            "conversations": convs}
    if calculos:
        fila["calculos"] = calculos
    return json.dumps(fila, ensure_ascii=False)


def _escribir(directorio, nombre, lineas):
    ruta = os.path.join(directorio, nombre)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    return ruta


class TestUtilidades(unittest.TestCase):
    def test_tokenize_sin_acentos(self):
        self.assertEqual(dd.tokenize("Cáncer, la MUERTE-2."),
                         ["cancer", "la", "muerte", "2"])

    def test_estimar_tokens(self):
        self.assertEqual(dd.estimar_tokens(""), 0)
        self.assertGreater(dd.estimar_tokens("una dos tres"),
                           dd.estimar_tokens("una"))

    def test_percentil(self):
        vals = list(range(1, 11))  # 1..10
        self.assertEqual(dd.percentil(vals, 0), 1.0)
        self.assertEqual(dd.percentil(vals, 1), 10.0)
        self.assertEqual(dd.percentil(vals, 0.5), 5.5)
        self.assertIsNone(dd.percentil([], 0.5))

    def test_resumen_longitud(self):
        r = dd.resumen_longitud([10, 20, 30, 40])
        self.assertEqual(r["n"], 4)
        self.assertEqual(r["media"], 25.0)
        self.assertEqual(r["min"], 10)
        self.assertEqual(r["max"], 40)
        self.assertEqual(dd.resumen_longitud([]), {"n": 0})


class TestNgrams(unittest.TestCase):
    def test_ngram_diversidad(self):
        toks = [["a", "b", "c", "d", "e"], ["a", "b", "c", "d", "e"],
                ["x", "y", "z", "w", "v"]]
        d = dd.ngram_diversidad(toks, 4)
        self.assertEqual(d["total"], 6)   # 2 apariciones por lectura
        self.assertEqual(d["unicos"], 4)  # abcd, bcde, xyzw, yzwv
        self.assertEqual(d["n"], 4)

    def test_muletillas(self):
        base = ["entre", "otras", "palabras", "muy", "distintas"]
        toks = []
        for i in range(20):
            fila = list(base) if i < 4 else ["palabra_%d" % i] * 5
            toks.append(fila + ["final%d" % i, "x", "y", "z"])
        found = dd.muletillas(toks, 4)
        grams = {" ".join(g) for g, c, f in found}
        self.assertIn("entre otras palabras muy", grams)
        for g, c, f in found:
            self.assertGreater(c / len(toks), dd.MULETILLA_MIN_FRAC)

    def test_extremos_y_ranking(self):
        t1 = " ".join("palabra%d" % i for i in range(12))
        textos = [t1, t1, "otras cinco palabras aqui siguen diez mas total"]
        ranking = dd.ranking_extremos(textos)
        apertura8 = " ".join("palabra%d" % i for i in range(8))
        self.assertEqual(ranking[apertura8], 2)
        # textos cortos (<8 palabras) no generan apertura
        self.assertIsNone(dd.extremos(dd.tokenize("una dos tres")))
        cierres = dd.ranking_extremos(textos, primera=False)
        cierre8 = " ".join("palabra%d" % i for i in range(4, 12))
        self.assertEqual(cierres[cierre8], 2)
        self.assertNotIn(apertura8, cierres)


class TestSimilitud(unittest.TestCase):
    def test_shingles_deterministas_y_cap(self):
        toks = ["w%d" % i for i in range(1000)]
        a = dd.shingle_hashes(toks)
        b = dd.shingle_hashes(toks)
        self.assertEqual(a, b)
        self.assertLessEqual(len(a), dd.SHINGLE_MAX)
        cortos = dd.shingle_hashes(["una", "dos"])
        self.assertEqual(cortos, set())

    def test_jaccard(self):
        self.assertEqual(dd.jaccard({1, 2, 3}, {1, 2, 3}), 1.0)
        self.assertEqual(dd.jaccard({1, 2}, {3, 4}), 0.0)
        self.assertAlmostEqual(dd.jaccard({1, 2}, {2, 3}), 1 / 3)
        self.assertEqual(dd.jaccard(set(), {1}), 0.0)

    def test_minhash_identico_y_vacio(self):
        s = dd.shingle_hashes(["palabra%d" % i for i in range(50)])
        self.assertEqual(dd.minhash_firma(s), dd.minhash_firma(s))
        firma0 = dd.minhash_firma(set())
        self.assertEqual(firma0, tuple([0] * dd.MINHASH_K))

    def test_lsh_detecta_duplicado(self):
        texto = " ".join("pal%d" % i for i in range(80))
        otros = [" ".join("otra%d_%d" % (j, i) for i in range(80))
                 for j in range(5)]
        textos = [texto, otros[0], "otro2", texto, otros[1]]
        sets = dd.firmas_por_lectura(textos)
        sigs = [dd.minhash_firma(s) for s in sets]
        pares = dd.lsh_pares_candidatos(sigs)
        self.assertIn((0, 3), pares)
        sim = dd.pares_similares(sets, sigs)
        self.assertTrue(any(s >= 0.99 for _i, _j, s in sim))

    def test_dedup_greedy(self):
        # 3 lecturas: 0 y 1 casi idénticas, 2 distinta
        sim = [(0, 1, 0.97)]
        perdidas, conservadas = dd.dedup_greedy(3, sim, 0.95)
        self.assertEqual(perdidas, 1)
        self.assertEqual(conservadas, 2)
        # por debajo del umbral no pierde nada
        self.assertEqual(dd.dedup_greedy(3, sim, 0.98)[0], 0)


class TestParseo(unittest.TestCase):
    def test_normalizar_nombre_carta(self):
        self.assertEqual(dd.normalizar_nombre_carta("5 de Copas", "tarot"),
                         "Cinco de Copas")
        self.assertEqual(dd.normalizar_nombre_carta("siete de oros", "espanol"),
                         "Siete de Oros")
        self.assertIsNone(dd.normalizar_nombre_carta("Carta Inexistente", "tarot"))

    def test_cartas_de_payload(self):
        p = {"cartas": [{"nombre": "Siete de Bastos", "invertida": True},
                        {"nombre": "El Loco"}],
             "contexto": "amor"}
        cs = dd.cartas_de_payload(p, "tarot")
        self.assertEqual(cs, [("Siete de Bastos", True), ("El Loco", False)])
        self.assertEqual(dd.cartas_de_payload(None, "tarot"), [])
        # carta natal (dict sin "nombre") no debe contar como naipe
        self.assertEqual(dd.cartas_de_payload(
            {"carta": {"fecha": "1990-01-01", "planetas": {}}}, "tarot"), [])

    def test_cartas_de_prompt_fallback(self):
        human = ("Tirada de dos cartas de tarot.\n\n"
                 "Carta 1: Ocho de Copas (al derecho)\n"
                 "Carta 2: La Templanza (invertida)\n"
                 "Contexto: general.\n\n"
                 "Referencia (significados):\n"
                 "- Ocho de Copas (al derecho): significado\n"
                 "- La Templanza (invertida): otro\n")
        cs = dd.cartas_de_prompt(human, "tarot")
        self.assertEqual(cs, [("Ocho de Copas", False),
                              ("La Templanza", True)])

    def test_cartas_de_prompt_cruz(self):
        human = ("Tirada de la Cruz Celta (diez cartas).\n\n"
                 "situación: Caballero de Copas (invertida)\n"
                 "esperanzas y miedos: Nueve de Oros (invertida)\n"
                 "Contexto: salud.\n"
                 "ESQUEMA OBLIGATORIO:\n"
                 "## 1. situación — Caballero de Copas (invertida)\n")
        cs = dd.cartas_de_prompt(human, "tarot")
        self.assertIn(("Caballero de Copas", True), cs)
        self.assertIn(("Nueve de Oros", True), cs)
        self.assertEqual(len(cs), 2)  # la del ESQUEMA no se repite

    def test_extraer_pregunta_y_contexto(self):
        human = 'Pregunta del consultante: "¿Cómo estoy?"\nContexto: trabajo.'
        self.assertEqual(dd.extraer_pregunta(human), "¿Cómo estoy?")
        self.assertEqual(dd.extraer_contexto(human, None), "trabajo")
        self.assertEqual(dd.extraer_contexto(human, {"contexto": "AMOR"}),
                         "amor")
        self.assertEqual(dd.extraer_contexto(human, {"tema": "salud"}),
                         "etica:salud")
        self.assertIsNone(dd.extraer_pregunta("sin pregunta aqui"))

    def test_clasificar_pregunta(self):
        casos = [
            ("¿Cómo puedo mejorar?", "cómo"),
            ("¿Qué me espera?", "qué"),
            ("¿Voy a encontrar pareja?", "si_no"),
            ("¿Por qué me siento sola?", "por_qué"),
            ("¿Cuál es mi camino?", "cuál"),
            ("Tengo dudas, ¿qué hago?", "qué"),
            ("Como conecto?", "cómo"),
            ("No sé nada", "otra"),
            (None, "sin_pregunta"),
        ]
        for q, esperado in casos:
            self.assertEqual(dd.clasificar_pregunta(q), esperado, q)

    def test_es_pregunta_fija(self):
        self.assertTrue(dd.es_pregunta_fija(
            "¿Cómo puedo desbloquear mi carrera profesional?"))
        # variante del consultante sin tildes ni signos de apertura
        self.assertTrue(dd.es_pregunta_fija(
            "Por que me siento tan agotada ultimamente?"))
        self.assertFalse(dd.es_pregunta_fija("Pregunta inventada por mí?"))

    def test_claves_etica(self):
        temas = dd.claves_etica_detectadas(
            "Tengo un bulto en el pecho. Dime si tengo cancer.")
        self.assertIn("salud_grave", temas)
        self.assertIn("muerte_duelo",
                      dd.claves_etica_detectadas("Mi padre va a morir pronto"))
        self.assertEqual(dd.claves_etica_detectadas("¿Cómo va mi amor?"), [])

    def test_signos_de_calculos(self):
        calc = {"carta_natal": {
            "planetas": {"Sol": {"signo": "Piscis"}},
            "ascendente": {"signo": "Géminis"}},
            "numerologia": {"camino_de_vida": 11}}
        signos, caminos = dd.signos_de_calculos(calc)
        self.assertIn(("sol", "Piscis"), signos)
        self.assertIn(("ascendente", "Géminis"), signos)
        self.assertEqual(caminos, [11])
        self.assertEqual(dd.signos_de_calculos({}), ([], []))

    def test_mazo_de_bloque(self):
        self.assertEqual(dd.mazo_de_bloque("espanola_3"), "espanol")
        self.assertEqual(dd.mazo_de_bloque("tarot_1"), "tarot")
        self.assertEqual(dd.mazo_de_bloque(None), "tarot")


class TestCargar(unittest.TestCase):
    def test_aplanar_multiturno(self):
        fila = json.loads(_fila(1, "multiturno", "respuesta larga",
                                humanos_extra=("¿Y ahora?",)))
        r = dd.aplanar(fila)
        self.assertTrue(r["multiturno"])
        self.assertEqual(r["n_human"], 2)
        self.assertIn("respuesta larga", r["respuesta"])

    def test_payloads_y_bloques_sin_db(self):
        self.assertEqual(dd.payloads_desde_jobs(None), {})
        self.assertEqual(dd.payloads_desde_jobs("/ruta/que/no/existe.db"), {})
        self.assertEqual(dd.bloques_en_jobs(""), [])

    def test_payloads_desde_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "jobs.db")
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY,"
                        " bloque TEXT, payload TEXT)")
            con.execute("INSERT INTO jobs VALUES (7, 'tarot_1', ?)",
                        (json.dumps({"carta": {"nombre": "El Loco"}}),))
            con.execute("INSERT INTO jobs VALUES (8, 'tarot_1', 'no-json')")
            con.commit()
            con.close()
            p = dd.payloads_desde_jobs(db)
            self.assertIn(7, p)
            self.assertNotIn(8, p)
            self.assertEqual([b for b, _n in dd.bloques_en_jobs(db)],
                             ["tarot_1"])


class TestAnalizar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        base = ("Entiendo tu pregunta y vamos a mirar. "
                + " ".join("palabra%d" % i for i in range(60)))
        otra = " ".join("distinta%d_%d" % (i, i % 3) for i in range(70))
        lineas = [
            _fila(1, "tarot_1", base, pregunta="¿Cómo mejoro?",
                  contexto="amor"),
            _fila(2, "tarot_1", base, pregunta="¿Cómo mejoro?",
                  contexto="amor"),  # duplicado exacto del 1
            _fila(3, "tarot_1", otra, pregunta="¿Me conviene?"),
            _fila(4, "numerologia", otra,
                  pregunta="¿Qué me dice la numerología?",
                  calculos={"numerologia": {"camino_de_vida": 7}}),
            _fila(5, "multiturno", base, humanos_extra=("¿Y ahora qué?",),
                  pregunta="¿Y ahora qué?"),
        ]
        self.ruta = _escribir(self.tmp, "acept.jsonl", lineas)
        self.db = os.path.join(self.tmp, "jobs.db")
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY,"
                    " bloque TEXT, payload TEXT)")
        con.executemany("INSERT INTO jobs VALUES (?,?,?)", [
            (1, "tarot_1", json.dumps(
                {"carta": {"nombre": "Siete de Bastos", "invertida": True},
                 "contexto": "amor"})),
            (2, "tarot_1", json.dumps(
                {"carta": {"nombre": "Siete de Bastos", "invertida": True}})),
            (3, "tarot_1", json.dumps(
                {"carta": {"nombre": "As de Copas"}})),
            (4, "numerologia", json.dumps({"fecha": "1990-01-01"})),
            (5, "multiturno", json.dumps(
                {"carta": {"nombre": "El Loco"}, "contexto": "salud"})),
            (99, "espanola_1", json.dumps(
                {"cartas": [{"nombre": "Siete de Oros",
                             "invertida": False}], "mazo": "espanol"})),
        ])
        con.commit()
        con.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_informe_completo(self):
        inf = dd.analizar(self.ruta, jobs_db=self.db, top=5)
        self.assertEqual(inf["meta"]["n_lecturas"], 5)
        self.assertEqual(inf["meta"]["n_con_payload"], 5)
        self.assertEqual(inf["meta"]["ids_repetidos"], 0)
        # bloques y multiturno
        self.assertEqual(set(inf["bloques"]),
                         {"tarot_1", "numerologia", "multiturno"})
        self.assertEqual(inf["bloques"]["multiturno"]["multiturno_frac"], 1.0)
        self.assertAlmostEqual(inf["global"]["multiturno_frac"], 0.2)
        # duplicados: el par (1,2) es idéntico
        dup = inf["bloques"]["tarot_1"]["duplicados"]
        self.assertGreaterEqual(dup["pares_por_bin"][">=0.95"], 1)
        self.assertGreaterEqual(dup["perdidas_dedup"]["0.95"], 1)
        # balance por payload
        tarot = inf["balance"]["tarot"]
        frec = {x["carta"]: x["n"] for x in tarot["tabla_completa"]}
        self.assertEqual(frec["Siete de Bastos"], 2)
        self.assertEqual(frec["As de Copas"], 1)
        self.assertEqual(frec["El Loco"], 1)
        self.assertEqual(tarot["invertidas"], 2)
        self.assertGreater(tarot["invertida_frac"], 0)
        # baraja española: ninguna lectura aceptada -> hueco
        self.assertEqual(inf["balance"]["espanol"]["n_ocurrencias"], 0)
        self.assertEqual(len(inf["huecos"]["naipes_espanoles_ausentes"]), 40)
        # hueco de bloques: espanola_1 está en jobs.db pero no en aceptadas
        self.assertIn("espanola_1", inf["huecos"]["bloques_sin_aceptadas"])
        # preguntas: 4 distintas, tipos
        self.assertEqual(inf["balance"]["preguntas"]["distintas"], 4)
        self.assertEqual(inf["balance"]["preguntas"]["totales"], 5)
        self.assertEqual(inf["balance"]["tipos_pregunta"]["cómo"], 2)
        # contextos y camino de vida
        self.assertGreaterEqual(inf["balance"]["contextos"]["amor"], 2)
        self.assertEqual(inf["balance"]["caminos_de_vida"], {"7": 1})
        self.assertIn("11", inf["huecos"]["caminos_de_vida_ausentes"])
        # markdown
        md = dd.render_markdown(inf)
        for cab in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(cab, md)

    def test_sin_jobs_db_usa_prompt(self):
        inf = dd.analizar(self.ruta, jobs_db=None, top=5)
        # sin payload, no hay cartas en el prompt sintético -> 0 ocurrencias
        self.assertEqual(inf["balance"]["tarot"]["n_ocurrencias"], 0)
        self.assertEqual(inf["meta"]["n_con_payload"], 0)
        self.assertEqual(inf["huecos"]["bloques_sin_aceptadas"], [])

    def test_main_cli(self):
        salida = os.path.join(self.tmp, "inf.json")
        md_ruta = os.path.join(self.tmp, "inf.md")
        rc = dd.main(["--jsonl", self.ruta, "--jobs-db", self.db,
                      "--out", salida, "--md", md_ruta, "--top", "3"])
        self.assertEqual(rc, 0)
        with open(salida, encoding="utf-8") as fh:
            inf = json.load(fh)
        self.assertEqual(inf["meta"]["n_lecturas"], 5)
        self.assertTrue(os.path.getsize(md_ruta) > 100)


if __name__ == "__main__":
    unittest.main()
