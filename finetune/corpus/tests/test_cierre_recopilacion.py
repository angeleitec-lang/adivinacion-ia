import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cierre_recopilacion as cierre
import diagnostico_tarot_libros as diag
import juez

TEXTO_SECCION_EXCLUIDA = ("El Sol ilumina todo lo que toca y da vitalidad "
                         "al consultante.")
CITA_EXCLUIDA = "El Sol ilumina todo lo que toca"
AFIRMACION_WEB_SOL = ("El Sol representa el exito, la vitalidad y el "
                      "reconocimiento.")


def _escribir_jsonl(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _leer_jsonl(ruta):
    with open(ruta, "r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


class TestDedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.consenso = os.path.join(self.tmp, "consenso.jsonl")
        self.log = os.path.join(self.tmp, "cierre_log.jsonl")

    def _escribir(self, filas):
        _escribir_jsonl(self.consenso, filas)

    def _ctx(self):
        return {"consenso": self.consenso, "log": self.log}

    def test_conserva_ultima_version(self):
        self._escribir([
            {"entidad_id": "a", "faceta": "f", "marca": 1},
            {"entidad_id": "b", "faceta": "f", "marca": 2},
            {"entidad_id": "a", "faceta": "f", "marca": 3},
        ])
        res = cierre.paso1_dedupe_consenso(self._ctx(), [])
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["duplicadas"], 1)
        filas = _leer_jsonl(self.consenso)
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[0]["entidad_id"], "a")
        self.assertEqual(filas[0]["marca"], 3)
        self.assertEqual(filas[1]["entidad_id"], "b")

    def test_copia_previa_existe(self):
        self._escribir([{"entidad_id": "a", "faceta": "f", "marca": 1},
                       {"entidad_id": "a", "faceta": "f", "marca": 2}])
        res = cierre.paso1_dedupe_consenso(self._ctx(), [])
        self.assertTrue(os.path.exists(res["backup"]))
        self.assertIn("pre-cierre", res["backup"])
        previas = _leer_jsonl(res["backup"])
        self.assertEqual(len(previas), 2)

    def test_idempotencia_sin_duplicados(self):
        self._escribir([{"entidad_id": "a", "faceta": "f"},
                       {"entidad_id": "b", "faceta": "f"}])
        antes = cierre._md5(self.consenso)
        res = cierre.paso1_dedupe_consenso(self._ctx(), [])
        self.assertEqual(res["estado"], "sin_cambio")
        self.assertEqual(cierre._md5(self.consenso), antes)
        copias = [f for f in os.listdir(self.tmp) if "pre-cierre" in f]
        self.assertEqual(copias, [])


class TestProcesosVivos(unittest.TestCase):
    def test_se_excluye_a_si_mismo(self):
        vivos = cierre.procesos_vivos()
        pids = {v["pid"] for v in vivos}
        self.assertNotIn(os.getpid(), pids)


class TestDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self._crear_entradas()

    def _crear_entradas(self):
        b = self.tmp
        for sub in ["consenso_kb", "libros/evidencias", "libros/secciones",
                    "afirmaciones_libros", "afirmaciones_full", "evidencias_web",
                    "libros_limpio"]:
            os.makedirs(os.path.join(b, sub), exist_ok=True)
        _escribir_jsonl(os.path.join(b, "consenso_kb", "consenso.jsonl"),
                       [{"entidad_id": "a", "faceta": "f"}])
        _escribir_jsonl(os.path.join(b, "libros/evidencias/evidencias.jsonl"),
                        [{"hash_seccion": "h1"}])
        _escribir_jsonl(os.path.join(b, "libros/secciones/x.jsonl"),
                        [{"seccion": "s", "texto": "t", "id_libro": "l1"}])
        _escribir_jsonl(os.path.join(b, "afirmaciones_libros/afirmaciones_libros.jsonl"),
                        [{"entidad_id": "a", "afirmacion": "x"}])
        _escribir_jsonl(os.path.join(b, "afirmaciones_full/afirmaciones.jsonl"),
                        [{"entidad_id": "a", "afirmacion": "y"}])
        _escribir_jsonl(os.path.join(b, "evidencias_web/evidencias.jsonl"),
                        [{"hash_seccion": "w1"}])
        _escribir_jsonl(os.path.join(b, "libros_limpio/claves_excluir_consenso.jsonl"),
                        [{"hash_seccion": "h1", "entidad_id": "a", "faceta": "f"}])

    def _argv(self):
        b = self.tmp
        return ["--dry-run", "--base-dir", b,
                "--consenso", os.path.join(b, "consenso_kb", "consenso.jsonl")]

    def test_dry_run_no_escribe_nada(self):
        antes = sorted(os.listdir(self.tmp))
        rc = cierre.main(self._argv(), procesos_fn=lambda: [])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(os.listdir(self.tmp)), antes)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "cierre_log.jsonl")))

    def test_aborta_con_proceso_vivo(self):
        rc = cierre.main(self._argv(),
                        procesos_fn=lambda: [{"pid": 4242, "cmd": "consenso_kb.py"}])
        self.assertEqual(rc, 1)

    def test_faltan_entradas_aborta(self):
        os.remove(os.path.join(self.tmp, "libros/evidencias/evidencias.jsonl"))
        rc = cierre.main(self._argv(), procesos_fn=lambda: [])
        self.assertEqual(rc, 1)


class TestFalloDetieneEncadenado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.orden = []
        self.orig = dict(cierre.PASOS)
        self.addCleanup(cierre.PASOS.update, self.orig)

        def stub(n):
            def fn(ctx, comandos):
                self.orden.append(n)
                if n == 2:
                    raise cierre.PasoFallido("fallo simulado")
                return {"estado": "ok"}
            return fn

        for n in cierre.PASOS:
            cierre.PASOS[n] = stub(n)

    def test_parada_en_el_primer_fallo(self):
        rc = cierre.main(["--todo", "--work-dir", self.tmp],
                        procesos_fn=lambda: [])
        self.assertEqual(rc, 1)
        self.assertEqual(self.orden, [1, 2])
        log = _leer_jsonl(os.path.join(self.tmp, "cierre_log.jsonl"))
        self.assertEqual([e["paso"] for e in log], [1, 2])
        self.assertEqual(log[1]["estado"], "fallido")


class TestOrdenTodo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.orden = []
        self.orig = dict(cierre.PASOS)
        self.addCleanup(cierre.PASOS.update, self.orig)
        for n in cierre.PASOS:
            def fn(ctx, comandos, n=n):
                self.orden.append(n)
                return {"estado": "ok"}
            cierre.PASOS[n] = fn

    def test_todo_ejecuta_los_siete_en_orden(self):
        rc = cierre.main(["--todo", "--work-dir", self.tmp],
                        procesos_fn=lambda: [])
        self.assertEqual(rc, 0)
        self.assertEqual(self.orden, [1, 2, 3, 4, 5, 6, 7])

    def test_paso_unico(self):
        rc = cierre.main(["--paso", "4", "--work-dir", self.tmp],
                        procesos_fn=lambda: [])
        self.assertEqual(rc, 0)
        self.assertEqual(self.orden, [4])


class TestLimpiezaLibros(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        b = self.tmp
        os.makedirs(os.path.join(b, "secciones"))
        os.makedirs(os.path.join(b, "afir"))
        os.makedirs(os.path.join(b, "limpio"))
        self.texto_astro = "THE SUN IN ARIES brings light."
        self.texto_tarot = "The High Priestess holds the veil."
        self.hash_astro = diag.hash_seccion("libro-astro", "THE SUN IN ARIES",
                                          self.texto_astro)
        self.hash_tarot = diag.hash_seccion("libro-tarot", "The High Priestess",
                                          self.texto_tarot)
        _escribir_jsonl(os.path.join(b, "secciones", "libro-astro.jsonl"),
                       [{"id_libro": "libro-astro", "seccion": "THE SUN IN ARIES",
                         "texto": self.texto_astro}])
        _escribir_jsonl(os.path.join(b, "secciones", "libro-tarot.jsonl"),
                       [{"id_libro": "libro-tarot", "seccion": "The High Priestess",
                         "texto": self.texto_tarot}])
        _escribir_jsonl(os.path.join(b, "afir", "procesados.jsonl"),
                       [{"hash_seccion": self.hash_astro,
                         "entidad_id": "tarot-mayor-20",
                         "faceta": "significado_general", "n_afirmaciones": 3}])
        self.evidencias = os.path.join(b, "evidencias.jsonl")
        _escribir_jsonl(self.evidencias, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "hash_seccion": self.hash_astro, "tipo": "libro",
             "fuente_id": "libro-astro"},
            {"entidad_id": "tarot-mayor-02", "faceta": "significado_general",
             "hash_seccion": self.hash_tarot, "tipo": "libro",
             "fuente_id": "libro-tarot"},
        ])
        _escribir_jsonl(os.path.join(b, "web.jsonl"), [])
        self.familias = os.path.join(b, "familias.json")
        with open(self.familias, "w") as fh:
            json.dump({"libro-astro": "astrologia", "libro-tarot": "tarot"}, fh)
        self.ctx = {
            "evidencias_libros": self.evidencias,
            "secciones_dir": os.path.join(b, "secciones"),
            "afirmaciones_libros_dir": os.path.join(b, "afir"),
            "evidencias_web": os.path.join(b, "web.jsonl"),
            "libros_limpio": os.path.join(b, "limpio"),
            "familias_json": self.familias,
        }

    def test_aplica_limpieza_con_backup(self):
        res = cierre.paso2_limpieza_libros(self.ctx, [])
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["retiradas"], 1)
        vigentes = _leer_jsonl(self.evidencias)
        self.assertEqual([e["entidad_id"] for e in vigentes], ["tarot-mayor-02"])
        self.assertTrue(os.path.exists(res["backup"]))

    def test_idempotencia_ya_aplicada(self):
        cierre.paso2_limpieza_libros(self.ctx, [])
        res = cierre.paso2_limpieza_libros(self.ctx, [])
        self.assertEqual(res["estado"], "ya_aplicada")


class TestConsensoExclusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        b = self.tmp
        os.makedirs(os.path.join(b, "secciones"))
        os.makedirs(os.path.join(b, "consenso"))
        self.hash_excl = diag.hash_seccion("libro-astro", "EL SOL EN ARIES",
                                          TEXTO_SECCION_EXCLUIDA)
        _escribir_jsonl(os.path.join(b, "secciones", "libro-astro.jsonl"),
                       [{"id_libro": "libro-astro", "seccion": "EL SOL EN ARIES",
                         "texto": TEXTO_SECCION_EXCLUIDA}])
        self.claves = os.path.join(b, "claves.jsonl")
        _escribir_jsonl(self.claves, [
            {"hash_seccion": self.hash_excl, "entidad_id": "tarot-mayor-20",
             "faceta": "significado_general", "n_afirmaciones": 1}])
        self.afir_libros = os.path.join(b, "afir_libros.jsonl")
        _escribir_jsonl(self.afir_libros, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "fuente_id": "libro-astro", "afirmacion": CITA_EXCLUIDA,
             "cita_original": CITA_EXCLUIDA}])
        self.afir_web = os.path.join(b, "afir_web.jsonl")
        _escribir_jsonl(self.afir_web, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "fuente_id": "web-1", "afirmacion": AFIRMACION_WEB_SOL}])
        self.consenso = os.path.join(b, "consenso", "consenso.jsonl")
        self.ctx = {
            "consenso": self.consenso,
            "consenso_dir": os.path.join(b, "consenso"),
            "afirmaciones_web_file": self.afir_web,
            "afirmaciones_libros_file": self.afir_libros,
            "claves_excluir": self.claves,
            "secciones_dir": os.path.join(b, "secciones"),
            "workers": 1,
            "simulado": True,
        }

    def test_afirmacion_excluida_no_llega_al_consenso(self):
        res = cierre.paso4_consenso_exclusion(self.ctx, [])
        self.assertEqual(res["estado"], "ok")
        self.assertGreaterEqual(res["afirmaciones_excluidas"], 1)
        celdas = _leer_jsonl(self.consenso)
        textos = set()
        for c in celdas:
            for k in ("mayoritarias", "discrepancias", "unica_fuente"):
                for item in c.get(k) or []:
                    textos.add(item["afirmacion"])
        self.assertNotIn(CITA_EXCLUIDA, textos)
        self.assertIn(AFIRMACION_WEB_SOL, textos)


class TestKbV2SinMezcla(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.consenso = os.path.join(self.tmp, "consenso.jsonl")
        _escribir_jsonl(self.consenso, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "n_afirmaciones": 1, "mayoritarias": [], "discrepancias": [],
             "unica_fuente": [{"afirmacion": "El sol ilumina.",
                               "fuente_id": "w1", "tradicion": "moderna"}]},
            {"entidad_id": "naipe-bastos-01", "faceta": "significado_general",
             "n_afirmaciones": 1, "mayoritarias": [], "discrepancias": [],
             "unica_fuente": [{"afirmacion": "El as de bastos inicia.",
                              "fuente_id": "w2", "tradicion": "moderna"}]},
        ])
        self.kb_out = os.path.join(self.tmp, "kb")

    def test_familias_no_se_mezclan(self):
        res = cierre.paso5_kb_v2(
            {"consenso": self.consenso, "kb_out": self.kb_out}, [])
        self.assertEqual(res["estado"], "ok")
        tarot = json.load(open(os.path.join(self.kb_out, "tarot.json")))
        baraja = json.load(open(os.path.join(self.kb_out, "baraja_espanola.json")))
        self.assertIn("tarot-mayor-20", tarot["entidades"])
        self.assertNotIn("naipe-bastos-01", tarot["entidades"])
        self.assertIn("naipe-bastos-01", baraja["entidades"])
        self.assertNotIn("tarot-mayor-20", baraja["entidades"])


class TestPaso2ClaveCompleta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.limpio = os.path.join(self.tmp, "limpio")
        os.makedirs(self.limpio)
        self.evidencias = os.path.join(self.tmp, "evidencias.jsonl")
        self.ctx = {"evidencias_libros": self.evidencias,
                   "libros_limpio": self.limpio}

    def _retirada(self, h, eid, faceta):
        return {"evidencia": {"entidad_id": eid, "faceta": faceta,
                              "hash_seccion": h}}

    def test_misma_seccion_retirada_para_otra_celda_no_falla(self):
        _escribir_jsonl(os.path.join(self.limpio, "evidencias_retiradas.jsonl"),
                       [self._retirada("h1", "tarot-mayor-20",
                                      "significado_general")])
        _escribir_jsonl(self.evidencias, [
            {"entidad_id": "tarot-mayor-19", "faceta": "significado_general",
             "hash_seccion": "h1"}])
        res = cierre._verificacion_limpieza(self.ctx)
        self.assertEqual(res["retiradas"], 1)
        self.assertEqual(res["vigentes"], 1)

    def test_retirada_realmente_vigente_si_falla(self):
        _escribir_jsonl(os.path.join(self.limpio, "evidencias_retiradas.jsonl"),
                       [self._retirada("h1", "tarot-mayor-20",
                                      "significado_general")])
        _escribir_jsonl(self.evidencias, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "hash_seccion": "h1"}])
        with self.assertRaises(cierre.PasoFallido):
            cierre._verificacion_limpieza(self.ctx)

    def test_falta_fichero_retiradas_falla(self):
        _escribir_jsonl(self.evidencias, [{"hash_seccion": "h1"}])
        with self.assertRaises(cierre.PasoFallido):
            cierre._verificacion_limpieza(self.ctx)


class TestSoloVerificar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.limpio = os.path.join(self.tmp, "limpio")
        os.makedirs(self.limpio)
        self.evidencias = os.path.join(self.tmp, "evidencias.jsonl")
        self.work = os.path.join(self.tmp, "cierre")
        self.llamadas = []
        self.orig = cierre._ejecutar

        def spy(cmd, log):
            self.llamadas.append(cmd)
            return self.orig(cmd, log)

        cierre._ejecutar = spy
        self.addCleanup(setattr, cierre, "_ejecutar", self.orig)

    def _argv(self):
        return ["--paso", "2", "--solo-verificar",
                "--evidencias-libros", self.evidencias,
                "--libros-limpio", self.limpio,
                "--work-dir", self.work]

    def test_solo_verificar_no_reaplica_y_no_loquea_proceso_vivo(self):
        _escribir_jsonl(os.path.join(self.limpio, "evidencias_retiradas.jsonl"),
                        [{"evidencia": {"entidad_id": "tarot-mayor-20",
                                       "faceta": "significado_general",
                                       "hash_seccion": "h1"}}])
        _escribir_jsonl(self.evidencias, [
            {"entidad_id": "tarot-mayor-19", "faceta": "significado_general",
             "hash_seccion": "h1"}])
        rc = cierre.main(self._argv(),
                       procesos_fn=lambda: [{"pid": 4242, "cmd": "consenso"}])
        self.assertEqual(rc, 0)
        self.assertEqual(self.llamadas, [])
        log = _leer_jsonl(os.path.join(self.work, "cierre_log.jsonl"))
        self.assertEqual(log[-1]["estado"], "verificada")

    def test_solo_verificar_detecta_retirada_vigente(self):
        _escribir_jsonl(os.path.join(self.limpio, "evidencias_retiradas.jsonl"),
                        [{"evidencia": {"entidad_id": "tarot-mayor-20",
                                       "faceta": "significado_general",
                                       "hash_seccion": "h1"}}])
        _escribir_jsonl(self.evidencias, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "hash_seccion": "h1"}])
        rc = cierre.main(self._argv(), procesos_fn=lambda: [])
        self.assertEqual(rc, 1)
        self.assertEqual(self.llamadas, [])
        log = _leer_jsonl(os.path.join(self.work, "cierre_log.jsonl"))
        self.assertEqual(log[-1]["estado"], "fallido")

    def test_solo_verificar_requiere_paso2_o_3(self):
        # Paso 4 (consenso) no admite --solo-verificar -> SystemExit.
        with self.assertRaises(SystemExit):
            cierre.main(["--paso", "4", "--solo-verificar",
                        "--work-dir", self.work], procesos_fn=lambda: [])


class TestConsensoTextoWebNoEsFiltracion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        b = self.tmp
        os.makedirs(os.path.join(b, "secciones"))
        self.hash_excl = diag.hash_seccion("libro-astro", "EL SOL EN ARIES",
                                          TEXTO_SECCION_EXCLUIDA)
        _escribir_jsonl(os.path.join(b, "secciones", "libro-astro.jsonl"),
                       [{"id_libro": "libro-astro", "seccion": "EL SOL EN ARIES",
                         "texto": TEXTO_SECCION_EXCLUIDA}])
        self.claves = os.path.join(b, "claves.jsonl")
        _escribir_jsonl(self.claves, [
            {"hash_seccion": self.hash_excl, "entidad_id": "tarot-mayor-20",
             "faceta": "significado_general", "n_afirmaciones": 1}])
        self.afir_libros = os.path.join(b, "afir_libros.jsonl")
        _escribir_jsonl(self.afir_libros, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "fuente_id": "libro-astro", "afirmacion": CITA_EXCLUIDA,
             "cita_original": CITA_EXCLUIDA}])
        self.afir_web = os.path.join(b, "afir_web.jsonl")
        self.consenso = os.path.join(b, "consenso.jsonl")
        _escribir_jsonl(self.consenso, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "n_afirmaciones": 1, "mayoritarias": [], "discrepancias": [],
             "unica_fuente": [{"afirmacion": CITA_EXCLUIDA,
                               "fuente_id": "web-1", "tradicion": "moderna"}]}])
        self.ctx = {
            "consenso": self.consenso,
            "afirmaciones_web_file": self.afir_web,
            "afirmaciones_libros_file": self.afir_libros,
            "claves_excluir": self.claves,
            "secciones_dir": os.path.join(b, "secciones"),
        }

    def test_texto_igual_desde_web_no_es_filtracion(self):
        _escribir_jsonl(self.afir_web, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "fuente_id": "web-1", "afirmacion": CITA_EXCLUIDA}])
        cierre._comprobar_retiradas_fuera_de_consenso(self.ctx)

    def test_texto_excluido_sin_origen_web_si_falla(self):
        _escribir_jsonl(self.afir_web, [
            {"entidad_id": "tarot-mayor-20", "faceta": "significado_general",
             "fuente_id": "web-1", "afirmacion": AFIRMACION_WEB_SOL}])
        with self.assertRaises(cierre.PasoFallido):
            cierre._comprobar_retiradas_fuera_de_consenso(self.ctx)


class TestCoberturaOmitida(unittest.TestCase):
    def test_omite_si_no_esta_integrado(self):
        script = os.path.join(cierre.CORPUS, "cobertura_v3.py")
        if os.path.exists(script):
            self.skipTest("cobertura_v3 ya integrado; nada que omitir")
        res = cierre.paso6_cobertura_v3({"cobertura_out": "/tmp"}, [])
        self.assertEqual(res["estado"], "omitido")
        self.assertIn("T82", res["aviso"])


def _montar_filtro(tmp):
    """Fixture del paso 3: web .md 'Venus en Leo' + libro 'CAPRICORNIO'.

    Devuelve (ctx, hashes). La pagina web nombra Leo (retira acuario|signo,
    conserva leo|signo); la seccion de libro nombra Capricornio (retira
    aries|signo, conserva capricornio|signo).
    """
    b = tmp
    os.makedirs(os.path.join(b, "webpaginas"), exist_ok=True)
    os.makedirs(os.path.join(b, "libros", "secciones"), exist_ok=True)
    os.makedirs(os.path.join(b, "evidencias_web"), exist_ok=True)
    os.makedirs(os.path.join(b, "libros", "evidencias"), exist_ok=True)
    os.makedirs(os.path.join(b, "afirmaciones_full"), exist_ok=True)
    os.makedirs(os.path.join(b, "afirmaciones_libros"), exist_ok=True)
    os.makedirs(os.path.join(b, "filtro"), exist_ok=True)

    url = "http://escuelamaia.com/venus-en-leo"
    md = os.path.join(b, "webpaginas", "venus-leo.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("---\nurl: %s\ntitulo: Venus en Leo necesita amor visto\n"
                 "dominio: escuelamaia.com\n---\n"
                 "Cuerpo de la pagina sobre venus en leo.\n" % url)
    h_web = juez.hash_seccion(juez._secciones_de_fichero(md)[0])

    libro_sec = {"id_libro": "libro-x", "seccion": 1, "posicion": 1,
                 "titulo": "CAPRICORNIO", "texto": "Texto sobre capricornio."}
    h_lib = juez.hash_seccion(libro_sec)
    _escribir_jsonl(os.path.join(b, "libros", "secciones", "libro-x.jsonl"),
                    [libro_sec])

    ev_web = os.path.join(b, "evidencias_web", "evidencias.jsonl")
    _escribir_jsonl(ev_web, [
        {"entidad_id": "acuario|signo", "faceta": "significado_general",
         "hash_seccion": h_web, "fuente_id": url, "tipo": "web"},
        {"entidad_id": "leo|signo", "faceta": "significado_general",
         "hash_seccion": h_web, "fuente_id": url, "tipo": "web"},
    ])
    ev_lib = os.path.join(b, "libros", "evidencias", "evidencias.jsonl")
    _escribir_jsonl(ev_lib, [
        {"entidad_id": "aries|signo", "faceta": "significado_general",
         "hash_seccion": h_lib, "fuente_id": "libro-x", "tipo": "libro"},
        {"entidad_id": "capricornio|signo", "faceta": "significado_general",
         "hash_seccion": h_lib, "fuente_id": "libro-x", "tipo": "libro"},
    ])
    _escribir_jsonl(os.path.join(b, "afirmaciones_full", "procesados.jsonl"),
                    [{"hash_seccion": h_web, "entidad_id": "acuario|signo",
                      "faceta": "significado_general", "n_afirmaciones": 2}])
    _escribir_jsonl(os.path.join(b, "afirmaciones_libros", "procesados.jsonl"),
                    [{"hash_seccion": h_lib, "entidad_id": "aries|signo",
                      "faceta": "significado_general", "n_afirmaciones": 3}])

    ctx = {
        "base_dir": b,
        "evidencias_web": ev_web,
        "evidencias_libros": ev_lib,
        "secciones_dir": os.path.join(b, "libros", "secciones"),
        "procesados_web": os.path.join(b, "afirmaciones_full", "procesados.jsonl"),
        "procesados_libros": os.path.join(b, "afirmaciones_libros", "procesados.jsonl"),
        "filtro_atribucion_out": os.path.join(b, "filtro"),
    }
    return ctx, {"h_web": h_web, "h_lib": h_lib}


class TestFiltroAtribucionPaso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ctx, self.h = _montar_filtro(self.tmp)

    def test_aplica_retira_y_conserva_por_origen(self):
        res = cierre.paso3_filtro_atribucion(self.ctx, [])
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["retiradas"], 2)
        self.assertEqual(res["cambios"], {"web": "aplicada", "libros": "aplicada"})
        web = _leer_jsonl(self.ctx["evidencias_web"])
        self.assertEqual([e["entidad_id"] for e in web], ["leo|signo"])
        lib = _leer_jsonl(self.ctx["evidencias_libros"])
        self.assertEqual([e["entidad_id"] for e in lib], ["capricornio|signo"])
        self.assertIn("web", res["backups"])
        self.assertIn("libros", res["backups"])
        self.assertTrue(os.path.exists(res["backups"]["web"]))

    def test_claves_excluir_tienen_afirmaciones(self):
        cierre.paso3_filtro_atribucion(self.ctx, [])
        claves = _leer_jsonl(os.path.join(self.ctx["filtro_atribucion_out"],
                                         "claves_excluir_consenso.jsonl"))
        por_entidad = {c["entidad_id"]: c["n_afirmaciones"] for c in claves}
        self.assertEqual(por_entidad, {"acuario|signo": 2, "aries|signo": 3})

    def test_idempotente_ya_aplicada(self):
        cierre.paso3_filtro_atribucion(self.ctx, [])
        antes_web = cierre._md5(self.ctx["evidencias_web"])
        antes_lib = cierre._md5(self.ctx["evidencias_libros"])
        res = cierre.paso3_filtro_atribucion(self.ctx, [])
        self.assertEqual(res["estado"], "ya_aplicada")
        self.assertEqual(cierre._md5(self.ctx["evidencias_web"]), antes_web)
        self.assertEqual(cierre._md5(self.ctx["evidencias_libros"]), antes_lib)

    def test_solo_verificar_ok_no_reaplica(self):
        cierre.paso3_filtro_atribucion(self.ctx, [])
        antes_web = cierre._md5(self.ctx["evidencias_web"])
        self.llamadas = []
        orig = cierre._ejecutar

        def spy(cmd, log):
            self.llamadas.append(cmd)
            return orig(cmd, log)

        cierre._ejecutar = spy
        self.addCleanup(setattr, cierre, "_ejecutar", orig)
        self.ctx["solo_verificar"] = True
        res = cierre.paso3_filtro_atribucion(self.ctx, [])
        self.assertEqual(res["estado"], "verificada")
        self.assertEqual(self.llamadas, [])
        self.assertEqual(cierre._md5(self.ctx["evidencias_web"]), antes_web)

    def test_solo_verificar_detecta_retirada_vigente(self):
        # Retirada que sigue vigente en las evidencias -> debe fallar.
        out = self.ctx["filtro_atribucion_out"]
        _escribir_jsonl(os.path.join(out, "evidencias_retiradas_web.jsonl"),
                        [{"entidad_id": "leo|signo", "faceta": "significado_general",
                          "hash_seccion": self.h["h_web"], "motivo": "x"}])
        _escribir_jsonl(os.path.join(out, "evidencias_retiradas_libros.jsonl"), [])
        self.ctx["solo_verificar"] = True
        with self.assertRaises(cierre.PasoFallido):
            cierre.paso3_filtro_atribucion(self.ctx, [])


class TestDosListasExclusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_lista_devuelve_ambas(self):
        f71 = os.path.join(self.tmp, "t71.jsonl")
        f88 = os.path.join(self.tmp, "t88.jsonl")
        _escribir_jsonl(f71, [])
        _escribir_jsonl(f88, [])
        ctx = {"claves_excluir": f71, "claves_atribucion": f88}
        self.assertEqual(cierre._listas_claves_exclusion(ctx), [f71, f88])

    def test_omite_la_que_no_existe(self):
        f71 = os.path.join(self.tmp, "t71.jsonl")
        _escribir_jsonl(f71, [])
        ctx = {"claves_excluir": f71,
               "claves_atribucion": os.path.join(self.tmp, "noexiste.jsonl")}
        self.assertEqual(cierre._listas_claves_exclusion(ctx), [f71])

    def test_clave_compartida_se_une_en_una_sola(self):
        import consenso_kb as ck
        f71 = os.path.join(self.tmp, "t71.jsonl")
        f88 = os.path.join(self.tmp, "t88.jsonl")
        _escribir_jsonl(f71, [{"hash_seccion": "hA", "entidad_id": "X|signo",
                               "faceta": "amor"}])
        _escribir_jsonl(f88, [{"hash_seccion": "hA", "entidad_id": "X|signo",
                               "faceta": "amor"},
                              {"hash_seccion": "hB", "entidad_id": "X|signo",
                               "faceta": "amor"}])
        claves = ck.cargar_claves_exclusion([f71, f88])
        # Una sola celda (X|signo, amor) con los hashes unidos -> se rehace 1 vez.
        self.assertEqual(list(claves.keys()), [("X|signo", "amor")])
        self.assertEqual(claves[("X|signo", "amor")], {"hA", "hB"})

    def test_paso4_pasa_ambas_listas_al_comando(self):
        b = self.tmp
        os.makedirs(os.path.join(b, "secciones"))
        os.makedirs(os.path.join(b, "consenso"))
        f71 = os.path.join(b, "t71.jsonl")
        f88 = os.path.join(b, "t88.jsonl")
        _escribir_jsonl(f71, [])
        _escribir_jsonl(f88, [])
        _escribir_jsonl(os.path.join(b, "afir_web.jsonl"), [])
        _escribir_jsonl(os.path.join(b, "afir_lib.jsonl"), [])
        ctx = {
            "consenso": os.path.join(b, "consenso", "consenso.jsonl"),
            "consenso_dir": os.path.join(b, "consenso"),
            "afirmaciones_web_file": os.path.join(b, "afir_web.jsonl"),
            "afirmaciones_libros_file": os.path.join(b, "afir_lib.jsonl"),
            "claves_excluir": f71,
            "claves_atribucion": f88,
            "secciones_dir": os.path.join(b, "secciones"),
            "workers": 1,
            "simulado": True,
        }
        self.llamadas = []
        orig = cierre._ejecutar

        def spy(cmd, log):
            self.llamadas.append(cmd)
            return orig(cmd, log)

        cierre._ejecutar = spy
        self.addCleanup(setattr, cierre, "_ejecutar", orig)
        res = cierre.paso4_consenso_exclusion(ctx, [])
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["listas_claves"], 2)
        cmd = self.llamadas[0]
        excl = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--excluir-claves"]
        self.assertEqual(sorted(excl), sorted([f71, f88]))


if __name__ == "__main__":
    unittest.main()
