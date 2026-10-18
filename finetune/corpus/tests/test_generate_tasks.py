import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import random
import unittest

import generate_tasks as gt


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
        b = gt.Builder(random.Random(1), kb_tarot, kb_astro, kb_num)
        lotes = [
            b.tarot_1(), b.tarot_2(5), b.tarot_3(5), b.cruz_celta(2),
            b.tarot_pregunta(5), b.astro_natal(5), b.sinastria(3),
            b.numerologia(5), b.lectura_completa(3), b.multiturno(5), b.etica(20),
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
    def test_sin_te_preguntaste(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(5), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.multiturno(50):
            self.assertNotIn("Te preguntaste", prompt)

    def test_previo_honesto(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(5), kb_tarot, kb_astro, kb_num)
        for _bloque, _system, prompt, _payload, _mt in b.multiturno(10):
            self.assertIn("En la consulta anterior salió", prompt)
            self.assertIn("el consultante preguntó: «", prompt)


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

    def test_ninguna_linea_de_referencia_con_doble_punto_en_los_11_bloques(self):
        kb_tarot, kb_astro, kb_num = kbs_para_test()
        b = gt.Builder(random.Random(12), kb_tarot, kb_astro, kb_num)
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
        })
        self.assertGreaterEqual(total, 200)


if __name__ == "__main__":
    unittest.main()
