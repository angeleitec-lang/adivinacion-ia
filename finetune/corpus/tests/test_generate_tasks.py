import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import random
import unittest

import generate_tasks as gt
import fase1_prompts as fp


def kb_tarot_minima():
    """KB de tarot pequena para tests (alternativa si no existe la del repo)."""
    nombres = ["El Loco", "El Mago", "La Sacerdotisa", "La Emperatriz", "El Emperador",
               "El Hierofante", "Los Enamorados", "El Carro", "La Fuerza", "El Ermitano",
               "La Rueda de la Fortuna", "La Justicia"]
    return {
        "mayores": [
            {"nombre": n, "palabras_clave": ["clave"], "significado": "s", "invertida": "i"}
            for n in nombres
        ],
        "menores": [],
    }


def kbs_para_test():
    try:
        return gt.load_kb("tarot.json"), gt.load_kb("astrologia.json"), gt.load_kb("numerologia.json")
    except (OSError, ValueError):
        return kb_tarot_minima(), {"signos": [], "planetas": [], "casas": [], "aspectos": []}, []


class TestZonaHoraria(unittest.TestCase):
    def test_lima_ascendente_virgo(self):
        # 12:00 hora local de Lima = 17:00 UT; el Ascendente correcto es Virgo 20°01'.
        c = gt.calcular_carta("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        self.assertEqual(c["ascendente"]["signo"], "Virgo")
        self.assertTrue(c["ascendente"]["grados"].startswith("20°"),
                       f"grados inesperados: {c['ascendente']['grados']}")
        # La salida debe seguir mostrando la hora local original.
        self.assertEqual(c["hora"], "12:00")

    def test_madrid_verano_equivale_a_10ut(self):
        a = gt.calcular_carta("1988-07-01", "12:00", 40.4168, -3.7038, "Europe/Madrid")
        b = gt.calcular_carta("1988-07-01", "10:00", 40.4168, -3.7038, "UTC")
        self.assertEqual(a["planetas"], b["planetas"])
        self.assertEqual(a["ascendente"], b["ascendente"])


class TestOrtografia(unittest.TestCase):
    PROHIBIDAS = ["espanol", "Que energia", "Cual es", "proposito", "Geminis",
                 "Jupiter", "Pluton", "conjuncion", "trigono", "oposicion",
                 "Anio", "Mexico", "Espana"]

    def _todos_los_textos(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(1), kb_tarot, kb_astro, kb_num,
                       gt.load_kb("baraja_espanola.json"))
        lotes = [
            b.tarot_1(), b.tarot_2(5), b.tarot_3(5), b.cruz_celta(2),
            b.tarot_pregunta(5), b.astro_natal(5), b.sinastria(3),
            b.numerologia(5), b.lectura_completa(3), b.multiturno(5), b.etica(20),
            b.espanola_1(5), b.espanola_3(5), b.espanola_5(2), b.espanola_7(2),
            b.transitos(5), b.revolucion_solar(5), b.biorritmos(5), b.fuera_alcance(5),
        ]
        for lote in lotes:
            for _bloque, system, prompt, _payload, _mt in lote:
                yield system
                yield prompt

    def test_sin_subcadenas_sin_tilde(self):
        for texto in self._todos_los_textos():
            for mala in self.PROHIBIDAS:
                self.assertNotIn(mala, texto, f"subcadena sin tilde encontrada: {mala!r}")


class TestReferenciaKB(unittest.TestCase):
    def test_tarot_1_contiene_significado_de_la_kb(self):
        import json
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(9), kb_tarot, kb_astro, kb_num)
        job = b.tarot_1()[0]
        prompt = job[2]
        carta = json.loads(job[3])["carta"]
        kb_c = next(c for c in b.cartas if c["nombre"] == carta["nombre"])
        self.assertIn("Referencia (significados de la tradición", prompt)
        esperado = kb_c["invertida"] if carta["invertida"] else kb_c["significado"]
        self.assertIn(esperado, prompt)

    def test_kb_sin_contextos_no_rompe(self):
        b = gt.Builder(random.Random(2), kb_tarot_minima(),
                      {"signos": [], "planetas": [], "casas": []}, [])
        lotes = [b.tarot_1(), b.tarot_2(3), b.tarot_3(3), b.cruz_celta(1),
                 b.tarot_pregunta(3), b.multiturno(3)]
        for lote in lotes:
            for _bl, _sys, prompt, _pl, _mt in lote:
                self.assertIsInstance(prompt, str)

    def test_astro_natal_contiene_regente_del_signo_solar(self):
        import json
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(4), kb_tarot, kb_astro, kb_num)
        job = b.astro_natal(1)[0]
        prompt = job[2]
        carta = json.loads(job[3])["carta"]
        signo_sol = carta["planetas"]["Sol"]["signo"]
        regente = next(s for s in kb_astro["signos"] if s["nombre"] == signo_sol)["regente"]
        self.assertIn(regente, prompt)

    def test_numerologia_contiene_claves_del_camino_de_vida(self):
        import json
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        if not kb_num:
            self.skipTest("sin KB de numerología")
        b = gt.Builder(random.Random(6), kb_tarot, kb_astro, kb_num)
        job = b.numerologia(1)[0]
        prompt = job[2]
        payload = json.loads(job[3])
        cv = gt.camino_de_vida(payload["fecha"])
        entrada = next(e for e in kb_num if e.get("numero") == cv)
        clave = entrada["palabras_clave"][0]
        self.assertIn(clave, prompt)


class TestAspectos(unittest.TestCase):
    def test_mejores_aspectos_orden_y_corte(self):
        orbes = [5.5, 0.3, 2.2, 4.1, 1.0, 3.3, 0.7, 6.0, 2.8, 1.5, 4.9, 0.1, 3.9, 2.0, 5.0, 0.5]
        aspectos = [{"a": f"P{i}", "b": "Q", "aspecto": "trígono", "orbe": o}
                   for i, o in enumerate(orbes)]
        top = gt.mejores_aspectos(aspectos, k=14)
        self.assertEqual(len(top), 14)
        obtenidos = [x["orbe"] for x in top]
        self.assertEqual(obtenidos, sorted(obtenidos))
        self.assertEqual(max(obtenidos), 5.0)
        self.assertNotIn(5.5, obtenidos)
        self.assertNotIn(6.0, obtenidos)

    def test_carta_devuelve_aspectos_ordenados_por_orbe(self):
        c = gt.calcular_carta("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
        orbes = [a["orbe"] for a in c["aspectos"]]
        self.assertLessEqual(len(orbes), 14)
        self.assertEqual(orbes, sorted(orbes))


class TestInsercionIdempotente(unittest.TestCase):
    def _filas(self):
        return [
            ("alfa", "sys", "p1", "{}", 100),
            ("alfa", "sys", "p2", "{}", 100),
            ("beta", "sys", "p3", "{}", 200),
        ]

    def _con(self):
        import sqlite3
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        con = sqlite3.connect(tmp.name)
        gt.crear_tabla(con)
        return con

    def test_segunda_ejecucion_sin_flag_no_duplica(self):
        import io
        import contextlib
        con = self._con()
        gt.insertar_jobs(con, self._filas(), replace_pending=False)
        n1 = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gt.insertar_jobs(con, self._filas(), replace_pending=False)
        n2 = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        self.assertEqual((n1, n2), (3, 3))
        self.assertIn("bloque alfa: ya existe (2 filas), omitido", buf.getvalue())
        self.assertIn("bloque beta: ya existe (1 filas), omitido", buf.getvalue())

    def test_flag_sustituye_solo_pending(self):
        con = self._con()
        gt.insertar_jobs(con, self._filas(), replace_pending=False)
        con.execute("UPDATE jobs SET status='done' WHERE prompt='p1'")
        con.commit()
        gt.insertar_jobs(con, [("alfa", "sys", "nuevo1", "{}", 100)], replace_pending=True)
        alfa = con.execute("SELECT prompt, status FROM jobs WHERE bloque='alfa' ORDER BY id").fetchall()
        self.assertIn(("p1", "done"), alfa)
        self.assertIn(("nuevo1", "pending"), alfa)
        self.assertNotIn(("p2", "pending"), alfa)

    def test_done_y_otros_bloques_sobreviven(self):
        con = self._con()
        gt.insertar_jobs(con, self._filas(), replace_pending=False)
        con.execute("UPDATE jobs SET status='done' WHERE bloque='alfa'")
        con.execute("UPDATE jobs SET status='running' WHERE bloque='beta'")
        con.commit()
        gt.insertar_jobs(con, self._filas(), replace_pending=True)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0], 2)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM jobs WHERE bloque='beta' AND status='pending'").fetchone()[0], 1)


class TestNumerologiaCalculo(unittest.TestCase):
    def test_anio_personal_manual(self):
        self.assertEqual(gt.anio_personal("1963-11-06"), 9)   # 6+11+10=27→9
        self.assertEqual(gt.anio_personal("1990-03-15"), 1)   # 6+3+1=10→1
        self.assertEqual(gt.anio_personal("2000-12-31"), 8)   # 4+3+1=8
        self.assertEqual(gt.anio_personal("1985-07-04"), 3)   # 4+7+1=12→3

    def test_camino_de_vida_manual(self):
        self.assertEqual(gt.camino_de_vida("1963-11-06"), 9)  # 11+6+1=18→9
        self.assertEqual(gt.camino_de_vida("1960-02-29"), 2)  # 2+11+7=20→2
        self.assertEqual(gt.camino_de_vida("1992-11-29"), 7)  # 11+11+3=25→7

    def test_rangos_200_fechas(self):
        rng = random.Random(42)
        for _ in range(200):
            f = f"{rng.randint(1950, 2005)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            ap = gt.anio_personal(f)
            self.assertIn(ap, range(1, 10), f"anio_personal fuera de 1..9 en {f}: {ap}")
            cv = gt.camino_de_vida(f)
            self.assertIn(cv, list(range(1, 10)) + [11, 22, 33],
                          f"camino_de_vida inválido en {f}: {cv}")

    def test_fmt_muestra_valor_corregido(self):
        texto = gt.fmt_numerologia("1963-11-06", "María López")
        self.assertIn("Año personal 2026: 9", texto)
        self.assertIn("Camino de vida: 9", texto)


class TestMultiturno(unittest.TestCase):
    def setUp(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        self.b = gt.Builder(random.Random(5), kb_tarot, kb_astro, kb_num)

    def test_sin_te_preguntaste(self):
        for _bloque, _system, prompt, _payload, _mt in self.b.multiturno(50):
            self.assertNotIn("Te preguntaste", prompt)

    def test_sin_simulacion_de_historial(self):
        # El multi-turno real no simula el historial dentro del prompt de fase 1.
        for _bloque, _system, prompt, _payload, _mt in self.b.multiturno(50):
            self.assertNotIn("En la consulta anterior salió", prompt)
            self.assertNotIn("Nueva pregunta del consultante", prompt)

    def test_fase1_es_lectura_normal(self):
        # El prompt de la fila es una lectura normal de una carta con su Referencia.
        for _bloque, _system, prompt, payload, _mt in self.b.multiturno(10):
            self.assertIn("Tirada de una carta de tarot.", prompt)
            self.assertIn("Referencia (significados de la tradición", prompt)
            datos = json.loads(payload)
            self.assertIn("Carta: " + datos["carta"]["nombre"], prompt)
            self.assertIn("Contexto: " + datos["contexto"], prompt)
            self.assertIn('Pregunta del consultante: "', prompt)

    def test_payload_con_fase2(self):
        for _bloque, _system, _prompt, payload, _mt in self.b.multiturno(20):
            datos = json.loads(payload)
            fase2 = datos["fase2"]
            seg = fase2["seguimiento"]
            ctx = datos["contexto"]
            self.assertIn(seg, gt.SEGUIMIENTOS[ctx])
            self.assertIn("sin repetirla", fase2["instruccion"])

    def test_seguimientos_con_tildes(self):
        for lista in gt.SEGUIMIENTOS.values():
            for seg in lista:
                inicio = seg.lstrip("¿¡")
                self.assertTrue(seg and inicio[0].isupper())
        plano = "".join(seg for lista in gt.SEGUIMIENTOS.values() for seg in lista)
        self.assertTrue(any(c in plano for c in "áéíóúñ¿¡"))

    def test_variedad_seguimientos(self):
        # En 200 trabajos, al menos 25 seguimientos distintos.
        segs = {json.loads(p)["fase2"]["seguimiento"]
                for _b, _s, _p, p, _m in self.b.multiturno(200)}
        self.assertGreaterEqual(len(segs), 25)

    def test_lista_amplia(self):
        total = sum(len(v) for v in gt.SEGUIMIENTOS.values())
        self.assertGreaterEqual(total, 40)
        for ctx in ("amor", "trabajo", "dinero", "salud", "espiritual"):
            self.assertIn(ctx, gt.SEGUIMIENTOS)

    def test_targets_multiturno(self):
        self.assertEqual(gt.TARGETS["multiturno"], 800)
        self.assertEqual(sum(gt.TARGETS.values()), 14136)

    def test_targets_baraja_espanola(self):
        self.assertEqual(gt.TARGETS["espanola_1"], 400)
        self.assertEqual(gt.TARGETS["espanola_3"], 900)
        self.assertEqual(gt.TARGETS["espanola_5"], 400)
        self.assertEqual(gt.TARGETS["espanola_7"], 200)


class TestEtica(unittest.TestCase):
    def test_variedad_de_prompts(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(7), kb_tarot, kb_astro, kb_num)
        prompts = [p for _bloque, _system, p, _payload, _mt in b.etica(300)]
        self.assertGreaterEqual(len(set(prompts)), 200,
                               "los 300 prompts de ética deben tener variedad real")

    def test_todos_empiezan_igual(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(11), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.etica(300):
            self.assertTrue(prompt.startswith("Consulta delicada."))

    def test_no_repite_par_hasta_agotar(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(3), kb_tarot, kb_astro, kb_num)
        prompts = [p for _bloque, _system, p, _payload, _mt in b.etica(300)]
        # Con >= 40 casos x >= 6 arranques hay >= 240 pares: los 240 primeros son únicos.
        primeros = prompts[:240]
        self.assertEqual(len(set(primeros)), len(primeros))


class TestFueraAlcance(unittest.TestCase):
    def _jobs(self, n=10, semilla=5):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(semilla), kb_tarot, kb_astro, kb_num)
        return b.fuera_alcance(n)

    def test_payload_incluye_tecnica_y_pregunta(self):
        for _bloque, _system, prompt, payload, _mt in self._jobs():
            datos = json.loads(payload)
            self.assertIn("tecnica", datos)
            self.assertIn("pregunta", datos)
            self.assertTrue(datos["pregunta"])
            self.assertIn(datos["pregunta"], prompt)

    def test_arranque_es_texto_y_no_indice(self):
        # Regresión: zip(..., range(n)) metía el índice como arranque y la
        # pregunta empezaba por un número.
        for _bloque, _system, _prompt, payload, _mt in self._jobs():
            datos = json.loads(payload)
            self.assertFalse(datos["pregunta"][0].isdigit(), datos["pregunta"])

    def test_pares_distintos_sin_repetir(self):
        preguntas = [json.loads(payload)["pregunta"]
                     for _bloque, _system, _prompt, payload, _mt in self._jobs(10)]
        self.assertEqual(len(set(preguntas)), len(preguntas))


class TestReferenciaSinDoblePunto(unittest.TestCase):
    def _lineas_referencia(self, prompt):
        en_referencia = False
        for linea in prompt.splitlines():
            if linea.startswith("Referencia ("):
                en_referencia = True
                continue
            if en_referencia:
                if not linea.strip():
                    en_referencia = False
                elif linea.startswith("- "):
                    yield linea

    def test_ninguna_linea_de_referencia_con_doble_punto_en_los_15_bloques(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(12), kb_tarot, kb_astro, kb_num,
                       gt.load_kb("baraja_espanola.json"))
        lotes = [
            ("tarot_1", lambda: b.tarot_1()[:20]),
            ("tarot_2", lambda: b.tarot_2(20)),
            ("tarot_3", lambda: b.tarot_3(20)),
            ("cruz_celta", lambda: b.cruz_celta(20)),
            ("tarot_pregunta", lambda: b.tarot_pregunta(20)),
            ("astro_natal", lambda: b.astro_natal(20)),
            ("sinastria", lambda: b.sinastria(20)),
            ("numerologia", lambda: b.numerologia(20)),
            ("lectura_completa", lambda: b.lectura_completa(20)),
            ("multiturno", lambda: b.multiturno(20)),
            ("etica", lambda: b.etica(20)),
            ("espanola_1", lambda: b.espanola_1(20)),
            ("espanola_3", lambda: b.espanola_3(20)),
            ("espanola_5", lambda: b.espanola_5(20)),
            ("espanola_7", lambda: b.espanola_7(20)),
        ]
        bloques = set()
        total = 0
        for nombre, generar in lotes:
            lote = generar()
            self.assertTrue(lote, f"el bloque {nombre} no generó trabajos")
            for job in lote:
                bloques.add(job[0])
                total += 1
                for linea in self._lineas_referencia(job[2]):
                    self.assertNotIn("..", linea, f"{nombre}: {linea}")
        self.assertEqual(bloques, {
            "tarot_1", "tarot_2", "tarot_3", "cruz_celta", "tarot_pregunta",
            "astro_natal", "sinastria", "numerologia", "lectura_completa",
            "multiturno", "etica",
            "espanola_1", "espanola_3", "espanola_5", "espanola_7",
        })
        self.assertGreaterEqual(total, 200)


class TestProyeccion(unittest.TestCase):
    """Tránsitos del día y revolución solar en lecturas con foco 'próximo año' (T35)."""

    MADRID = ("1988-07-01", "12:00", 40.4168, -3.7038, "Europe/Madrid")

    def setUp(self):
        self.trans, self.rs = gt.datos_proyeccion(*self.MADRID)

    def test_transitos_valores_de_referencia(self):
        self.assertEqual(self.trans["fecha_transito"], gt.FECHA_CONSULTA)
        aspectos = self.trans["aspectos"]
        self.assertEqual(len(aspectos), 5)
        top = aspectos[0]
        self.assertEqual(top["planeta_transito"], "Saturno")
        self.assertEqual(top["aspecto"], "cuadratura")
        self.assertEqual(top["planeta_natal"], "Sol")
        self.assertEqual(top["casa_natal"], 10)
        self.assertAlmostEqual(top["orbe"], 0.6781, delta=0.01)
        orbs = [a["orbe"] for a in aspectos]
        self.assertEqual(orbs, sorted(orbs))

    def test_revolucion_solar_valores_de_referencia(self):
        self.assertEqual(self.rs["instante_ut"], "2026-07-01 14:25:00")
        self.assertEqual(self.rs["instante_local"], "2026-07-01 16:25:00")
        self.assertLess(self.rs["diferencia_arco"], 1.0 / 60.0)
        sol_rs = next(p for p in self.rs["carta"]["planetas"] if p["nombre"] == "Sol")
        self.assertEqual((sol_rs["signo"], sol_rs["grado"], sol_rs["minuto"]), ("Cáncer", 9, 47))
        asc = self.rs["ascendente"]
        self.assertEqual((asc["signo"], asc["grado"], asc["minuto"]), ("Escorpio", 3, 27))

    def test_fmt_transitos_texto_exacto(self):
        texto = gt.fmt_transitos(self.trans)
        lineas = texto.split("\n")
        self.assertEqual(lineas[0], "Tránsitos del día 2026-10-15:")
        self.assertEqual(
            lineas[1],
            "- Saturno en tránsito hace cuadratura a su Sol natal (casa 10, orbe 0.7°)",
        )
        self.assertEqual(len(lineas), 1 + len(self.trans["aspectos"]))

    def test_fmt_revolucion_solar_texto_exacto(self):
        self.assertEqual(
            gt.fmt_revolucion_solar(self.rs),
            "Revolución solar del año 2026: instante 2026-07-01 14:25:00 UT "
            "(local 2026-07-01 16:25:00); Sol RS en Cáncer 9°47'; "
            "Ascendente RS Escorpio 3°27'.",
        )

    def test_astro_natal_con_proyeccion_incluye_transitos_y_rs(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(1), kb_tarot, kb_astro, kb_num)
        jobs = [j for j in b.astro_natal(60)
                if json.loads(j[3])["foco"] == gt.FOCO_PROYECCION]
        self.assertTrue(jobs, "ningún job con foco de proyección")
        for job in jobs:
            prompt = job[2]
            payload = json.loads(job[3])
            self.assertIn("Lectura de carta natal con proyección.", prompt)
            self.assertIn("Tránsitos del día 2026-10-15", prompt)
            self.assertIn("Revolución solar del año 2026", prompt)
            self.assertIn("próximo año", prompt)
            self.assertIn("transitos", payload)
            self.assertIn("revolucion_solar", payload)

    def test_astro_natal_sin_proyeccion_no_incluye_transitos(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(1), kb_tarot, kb_astro, kb_num)
        jobs = [j for j in b.astro_natal(60)
                if json.loads(j[3])["foco"] != gt.FOCO_PROYECCION]
        self.assertTrue(jobs)
        for job in jobs:
            prompt = job[2]
            payload = json.loads(job[3])
            self.assertNotIn("Tránsitos del día", prompt)
            self.assertNotIn("Revolución solar", prompt)
            self.assertNotIn("transitos", payload)
            self.assertNotIn("revolucion_solar", payload)


def _builder_baraja(seed):
    kb_tarot, kb_astro, kb_num = kbs_para_test()
    return gt.Builder(random.Random(seed), kb_tarot, kb_astro, kb_num,
                      gt.load_kb("baraja_espanola.json"))


NOMBRES_NAIPE = {c["nombre"] for c in gt.NAIPES_ESPANOLES}


class TestBarajaEspanola(unittest.TestCase):
    def test_solo_40_naipes_y_sin_repetir(self):
        b = _builder_baraja(21)
        for fn, n in ((b.espanola_1, 1), (b.espanola_3, 3), (b.espanola_5, 5), (b.espanola_7, 7)):
            for _ in range(30):
                job = fn(1)[0]
                cartas = json.loads(job[3])["cartas"]
                nombres = [c["nombre"] for c in cartas]
                self.assertEqual(len(nombres), len(set(nombres)), "carta repetida en la tirada")
                self.assertEqual(len(nombres), n)
                for nombre in nombres:
                    self.assertIn(nombre, NOMBRES_NAIPE, "naipe fuera de la baraja de 40")

    def test_payload_y_frase_obligatoria(self):
        b = _builder_baraja(22)
        for job in b.espanola_3(10):
            bloque, _system, prompt, payload, mt = job
            self.assertEqual(bloque, "espanola_3")
            pl = json.loads(payload)
            self.assertEqual(pl["mazo"], "espanol")
            self.assertIn("contexto", pl)
            self.assertIn('Pregunta del consultante: "', prompt)
            self.assertIn("Baraja española de 40 naipes: no es tarot ni baraja francesa", prompt)
            self.assertIn("española", prompt)
            self.assertNotIn("espanol", prompt.replace("española", ""))
            self.assertEqual(mt, fp.RECOMENDACION_MAX_TOKENS["espanola_3"])

    def test_posiciones_y_esquema(self):
        b = _builder_baraja(23)
        pl3 = json.loads(b.espanola_3(1)[0][3])
        self.assertEqual(pl3["posiciones"], ["pasado", "presente", "futuro"])
        self.assertNotIn("posiciones", json.loads(b.espanola_1(1)[0][3]))
        job5 = b.espanola_5(1)[0]
        pl5 = json.loads(job5[3])
        self.assertEqual(pl5["posiciones"],
                         ["situación", "obstáculo", "pasado", "futuro", "resultado"])
        for cab in ("## 1. situación —", "## 5. resultado —", "## Síntesis",
                    "ESQUEMA OBLIGATORIO"):
            self.assertIn(cab, job5[2])
        job7 = b.espanola_7(1)[0]
        self.assertEqual(len(json.loads(job7[3])["posiciones"]), 7)
        self.assertIn("## 7. resultado —", job7[2])

    def test_referencia_baraja_en_prompt(self):
        b = _builder_baraja(24)
        for job in b.espanola_5(5):
            prompt = job[2]
            self.assertIn("Referencia (", prompt)
            for c in json.loads(job[3])["cartas"]:
                self.assertIn(c["nombre"], prompt)

    def test_max_tokens_por_familia(self):
        b = _builder_baraja(25)
        esperados = {
            "espanola_1": 1536, "espanola_3": 2560,
            "espanola_5": 4096, "espanola_7": 5120,
        }
        for familia, mt in esperados.items():
            job = getattr(b, familia)(1)[0]
            self.assertEqual(job[0], familia)
            self.assertEqual(job[4], mt)


class TestTiradasLargasDelegadas(unittest.TestCase):
    def test_cruz_celta_esquema_y_presupuesto(self):
        b = _builder_baraja(31)
        for job in b.cruz_celta(5):
            bloque, _system, prompt, payload, mt = job
            self.assertEqual(bloque, "cruz_celta")
            self.assertEqual(mt, 6144)
            self.assertIn("ESQUEMA OBLIGATORIO", prompt)
            self.assertIn("## 1. situación —", prompt)
            self.assertIn("## 10. resultado —", prompt)
            self.assertIn("## Síntesis", prompt)
            self.assertIn('Pregunta del consultante: "', prompt)
            pl = json.loads(payload)
            self.assertEqual(pl["posiciones"][0], "situación")
            self.assertEqual(len(pl["cartas"]), 10)

    def test_lectura_completa_secciones_y_presupuesto(self):
        b = _builder_baraja(32)
        for job in b.lectura_completa(3):
            _bloque, _system, prompt, payload, mt = job
            self.assertEqual(mt, 6144)
            for cab in ("## Carta natal", "## Tirada de tres cartas",
                        "## Numerología", "## Síntesis"):
                self.assertIn(cab, prompt)
            pl = json.loads(payload)
            self.assertEqual(
                sorted(pl),
                ["carta", "cartas", "ciudad", "contexto", "fecha", "nombre"],
            )
            self.assertIn('Pregunta del consultante: "', prompt)

    def test_lectura_completa_prompt_igual_que_ejecutor(self):
        import ejecutor_fase1 as ex
        import fase1_prompts as fp
        kb = ex.cargar_kb()
        b = gt.Builder(random.Random(33), kb["tarot"], kb["astrologia"], kb["numerologia"],
                       gt.load_kb("baraja_espanola.json"))
        for job in b.lectura_completa(2):
            _b, _s, prompt, payload, _mt = job
            pl = json.loads(payload)
            t = ex.tarea_desde_job("lectura_completa", pl, ex.extraer_pregunta(prompt), kb)
            self.assertEqual(fp.construir_prompt(t, kb)["user"], prompt)

    def test_compatibilidad_tarot_sin_esquema(self):
        b = _builder_baraja(34)
        for job in b.tarot_1()[:10] + b.tarot_2(5) + b.tarot_3(5) + b.multiturno(5):
            self.assertNotIn("ESQUEMA", job[2])
        for job in b.tarot_1()[:5]:
            self.assertEqual(job[4], 1024)


class TestIdempotenciaBaraja(unittest.TestCase):
    def _db_tmp(self):
        import sqlite3
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        return tmp.name, sqlite3.connect(tmp.name)

    def test_replace_pending_solo_toca_pendientes(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        db, con = self._db_tmp()
        try:
            gt.crear_tabla(con)
            b = gt.Builder(random.Random(41), kb_tarot, kb_astro, kb_num,
                           gt.load_kb("baraja_espanola.json"))
            filas = b.espanola_1(10) + b.cruz_celta(5)
            gt.insertar_jobs(con, filas)
            con.execute("UPDATE jobs SET status='done' WHERE bloque='espanola_1' AND id<=3")
            con.commit()
            filas2 = b.espanola_1(10) + b.cruz_celta(5)
            gt.insertar_jobs(con, filas2, replace_pending=True)
            done = con.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0]
            total1 = con.execute("SELECT COUNT(*) FROM jobs WHERE bloque='espanola_1'").fetchone()[0]
            total2 = con.execute("SELECT COUNT(*) FROM jobs WHERE bloque='cruz_celta'").fetchone()[0]
            self.assertEqual(done, 3)
            self.assertEqual(total1, 13)  # 3 done conservados + 10 nuevos pending
            self.assertEqual(total2, 5)
        finally:
            con.close()
            os.remove(db)

    def test_bloques_nuevos_se_insertan(self):
        db, con = self._db_tmp()
        try:
            gt.crear_tabla(con)
            gt.main(["--db", db, "--seed", "42", "--only", "espanola_5", "--scale", "0.01"])
            n = con.execute("SELECT COUNT(*) FROM jobs WHERE bloque='espanola_5'").fetchone()[0]
            self.assertGreaterEqual(n, 1)
        finally:
            con.close()
            os.remove(db)


if __name__ == "__main__":
    unittest.main()
