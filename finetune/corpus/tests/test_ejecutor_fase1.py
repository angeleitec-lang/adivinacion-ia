#!/usr/bin/env python3
"""Tests del ejecutor de fase 1 (T62) con clientes simulados deterministas."""

import datetime
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import generate_tasks as gt  # noqa: E402
from calculos import numerologia as calc_num  # noqa: E402
from cartas import NAIPES_ESPANOLES  # noqa: E402
from llm_client import LLMClient  # noqa: E402

BUENA = "El Loco abre tu camino: es un comienzo lleno de posibilidad."
MALA = "La Torre lo destruye todo y El Diablo se cierne sobre tu proyecto."
TRUNCA = "El Loco abre tu camino"

PROMPT_TAROT = (
    "Tirada de una carta de tarot.\n\n"
    "Carta: El Loco (al derecho).\nContexto: trabajo.\n"
    'Pregunta del consultante: "¿Cómo va mi proyecto?"'
)
PAYLOAD_TAROT = json.dumps(
    {"carta": {"nombre": "El Loco", "invertida": False}, "contexto": "trabajo"},
    ensure_ascii=False,
)

CARTA_NATAL = {
    "fecha": "1990-01-01",
    "hora": "12:00",
    "planetas": {
        "Sol": {"signo": "Capricornio", "grados": "10°00'"},
        "Luna": {"signo": "Acuario", "grados": "20°00'"},
    },
    "ascendente": {"signo": "Piscis", "grados": "15°00'"},
}


def naipe(nombre, invertida=False):
    """Carta de baraja española como la deja generate_tasks en el payload."""
    for c in NAIPES_ESPANOLES:
        if c["nombre"] == nombre:
            return {
                "nombre": c["nombre"],
                "invertida": invertida,
                "sinonimos": list(c.get("sinonimos", [])),
            }
    raise KeyError(nombre)


def pasada_sim(kb, bloque, payload, pregunta="¿Cómo va todo?"):
    """tarea -> prompt -> lector simulado -> verificador. Devuelve todo."""
    tarea = ef.tarea_desde_job(bloque, payload, pregunta, kb)
    prompt = fp.construir_prompt(tarea, kb)
    sim = ef.simulacion_fase1(prompt["system"], prompt["user"])
    ok, motivos = fp.verificar_lectura(tarea, sim)
    return tarea, prompt, sim, ok, motivos


class ClienteGuion:
    """Devuelve respuestas por orden; al agotarlas repite la última."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []
        self._lock = threading.Lock()

    def chat(self, sistema, usuario, **kwargs):
        with self._lock:
            self.llamadas.append((sistema, usuario))
            if len(self._respuestas) > 1:
                return self._respuestas.pop(0)
            return self._respuestas[0]


class ClienteError:
    def chat(self, *args, **kwargs):
        raise ConnectionError("nodos caídos")


def crear_db(ruta, filas):
    con = sqlite3.connect(ruta)
    gt.crear_tabla(con)
    for f in filas:
        con.execute(
            "INSERT INTO jobs (bloque, system, prompt, payload, max_tokens, status, "
            "updated_at) VALUES (?,?,?,?,?,?,?)",
            f,
        )
    con.commit()
    con.close()


def estado_fila(ruta, job_id=1):
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    con.close()
    return dict(r)


def lineas_jsonl(ruta):
    p = Path(ruta)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def iso_ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TestUnidades(unittest.TestCase):
    def test_truncado_sin_puntuacion_final(self):
        self.assertTrue(ef.respuesta_truncada("texto a medias"))
        self.assertTrue(ef.respuesta_truncada(""))
        self.assertTrue(ef.respuesta_truncada(None))
        self.assertFalse(ef.respuesta_truncada("Lectura completa."))
        self.assertFalse(ef.respuesta_truncada("¿Y ahora qué?"))
        self.assertFalse(ef.respuesta_truncada("Cierre con comillas: «sí»."))

    def test_extraer_pregunta(self):
        self.assertEqual(ef.extraer_pregunta(PROMPT_TAROT), "¿Cómo va mi proyecto?")
        self.assertEqual(ef.extraer_pregunta('Pregunta: "otro"'), "otro")
        self.assertEqual(ef.extraer_pregunta("sin pregunta"), "")

    def test_max_tokens_piso_y_pesados(self):
        self.assertEqual(ef.max_tokens_efectivo({"bloque": "tarot_1", "max_tokens": 1024}, 4096), 4096)
        self.assertEqual(ef.max_tokens_efectivo({"bloque": "cruz_celta", "max_tokens": 1600}, 4096), 6144)
        self.assertEqual(ef.max_tokens_efectivo({"bloque": "tarot_1", "max_tokens": 5000}, 4096), 5000)


class TestTareaDesdeJob(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def test_tarot_1(self):
        t = ef.tarea_desde_job("tarot_1", json.loads(PAYLOAD_TAROT), "¿Cómo va?", self.kb)
        self.assertEqual(t["cartas"], [{"nombre": "El Loco", "invertida": False}])
        self.assertEqual(t["contexto"], "trabajo")
        self.assertIn("El Loco", t["universo_cartas"])
        self.assertEqual(t["pregunta"], "¿Cómo va?")

    def test_multiturno_es_lectura_de_una_carta(self):
        payload = {
            "fase2": {"seguimiento": "¿Y en el trabajo?", "instruccion": "sigue"},
            "carta": {"nombre": "La Estrella", "invertida": True},
            "contexto": "amor",
        }
        t = ef.tarea_desde_job("multiturno", payload, "pregunta", self.kb)
        self.assertEqual(t["cartas"], [{"nombre": "La Estrella", "invertida": True}])

    def test_astro_natal(self):
        carta = {"fecha": "1990-01-01", "planetas": {"Sol": {"signo": "capricornio"}}}
        t = ef.tarea_desde_job("astro_natal", {"carta": carta, "ciudad": "Madrid"}, "p", self.kb)
        self.assertEqual(t["calculos"]["carta_natal"], carta)
        self.assertEqual(t["ciudad"], "Madrid")

    def test_sinastria(self):
        t = ef.tarea_desde_job("sinastria", {"a": {"x": 1}, "b": {"y": 2}}, "p", self.kb)
        self.assertEqual(t["calculos"]["carta_a"], {"x": 1})
        self.assertEqual(t["calculos"]["carta_b"], {"y": 2})

    def test_numerologia_calcula(self):
        t = ef.tarea_desde_job(
            "numerologia",
            {"fecha": "1990-05-04", "nombre": "Ana Lopez", "foco": "x"},
            "p", self.kb,
        )
        num = t["calculos"]["numerologia"]
        self.assertEqual(num["camino_de_vida"], calc_num.camino_de_vida("1990-05-04"))
        self.assertEqual(num["expresion"], calc_num.expresion("Ana Lopez"))

    def test_bloque_desconocido_explota(self):
        with self.assertRaises(ValueError):
            ef.tarea_desde_job("runas", {}, "p", self.kb)


class TestSimulacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _ok_con_sim(self, bloque, payload, pregunta="¿Cómo va todo?"):
        tarea = ef.tarea_desde_job(bloque, payload, pregunta, self.kb)
        prompt = fp.construir_prompt(tarea, self.kb)
        sim = ef.simulacion_fase1(prompt["system"], prompt["user"])
        ok, motivos = fp.verificar_lectura(tarea, sim)
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))

    def test_sim_pasa_verificador_tarot(self):
        self._ok_con_sim("tarot_1", json.loads(PAYLOAD_TAROT))

    def test_sim_pasa_verificador_con_invertida(self):
        payload = {"cartas": [{"nombre": "La Torre", "invertida": True}], "contexto": "trabajo"}
        self._ok_con_sim("tarot_2", payload)

    def test_sim_pasa_verificador_numerologia(self):
        payload = {"fecha": "1988-11-02", "nombre": "Marta Ruiz", "foco": "año personal"}
        self._ok_con_sim("numerologia", payload)

    def test_sim_pasa_verificador_etica(self):
        self._ok_con_sim("etica", {"tema": "salud"})


class TestEjecucion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "jobs.db")
        self.out = str(Path(self.tmp.name) / "salida")

    def tearDown(self):
        self.tmp.cleanup()

    def _ejecutar(self, cliente, **kw):
        kw.setdefault("workers", 1)
        return ef.ejecutar(self.db, cliente, self.kb, out_dir=self.out, **kw)

    def test_aceptacion(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        res = self._ejecutar(ClienteGuion([BUENA]))
        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(estado_fila(self.db)["status"], "done")
        ace = lineas_jsonl(Path(self.out) / "aceptadas.jsonl")
        self.assertEqual(len(ace), 1)
        self.assertEqual(ace[0]["respuesta"], BUENA)
        self.assertEqual(ace[0]["intentos"], 1)
        self.assertEqual(ace[0]["motivos"], [])
        self.assertEqual(ace[0]["prompt_user"], fp.construir_prompt(
            ef.tarea_desde_job("tarot_1", json.loads(PAYLOAD_TAROT), "¿Cómo va mi proyecto?", self.kb),
            self.kb,
        )["user"])

    def test_rechazo_reintento_con_causa_en_el_prompt(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        c = ClienteGuion([MALA, BUENA])
        res = self._ejecutar(c)
        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(len(c.llamadas), 2)
        self.assertIn("Tu respuesta anterior fue rechazada", c.llamadas[1][1])
        self.assertIn("Falta la carta de la tirada: El Loco", c.llamadas[1][1])
        ace = lineas_jsonl(Path(self.out) / "aceptadas.jsonl")
        self.assertEqual(ace[0]["intentos"], 2)
        self.assertTrue(ace[0]["motivos_rechazo_previos"])

    def test_truncado_reintenta_y_acepta(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        c = ClienteGuion([TRUNCA, BUENA])
        res = self._ejecutar(c)
        self.assertEqual(res["aceptadas"], 1)
        self.assertIn("cortada", c.llamadas[1][1])

    def test_truncado_agotado_rechazado(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        c = ClienteGuion([TRUNCA])
        res = self._ejecutar(c, max_reintentos=2)
        self.assertEqual(res["rechazadas"], 1)
        self.assertEqual(len(c.llamadas), 3)
        self.assertEqual(estado_fila(self.db)["status"], "failed")
        rech = lineas_jsonl(Path(self.out) / "rechazadas.jsonl")
        self.assertEqual(len(rech), 1)
        self.assertIn("respuesta_truncada", rech[0]["motivos"][0])

    def test_error_red_vuelve_a_pending(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        res = self._ejecutar(ClienteError())
        self.assertEqual(res["errores_red"], 1)
        fila = estado_fila(self.db)
        self.assertEqual(fila["status"], "pending")
        self.assertEqual(fila["attempts"], 1)
        self.assertIn("error_red", fila["error"])
        self.assertEqual(lineas_jsonl(Path(self.out) / "aceptadas.jsonl"), [])
        self.assertEqual(lineas_jsonl(Path(self.out) / "rechazadas.jsonl"), [])

    def test_reanudacion_huerfanas(self):
        vieja = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        crear_db(self.db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "running", vieja),
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "running", iso_ahora()),
        ])
        con = sqlite3.connect(self.db)
        con.execute("UPDATE jobs SET worker='otro-worker' WHERE id=2")
        con.commit()
        con.close()
        res = self._ejecutar(ClienteGuion([BUENA]), huerfano_minutos=30)
        self.assertEqual(res["huerfanas_recuperadas"], 1)
        self.assertEqual(estado_fila(self.db, 1)["status"], "done")
        self.assertEqual(estado_fila(self.db, 2)["status"], "running")

    def test_idempotencia_segunda_pasada_cero_trabajo(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        self._ejecutar(ClienteGuion([BUENA]))
        res2 = self._ejecutar(ClienteError())
        self.assertEqual(res2["pendientes"], 0)
        self.assertEqual(res2["procesadas"], 0)
        self.assertEqual(res2["errores_red"], 0)

    def test_copia_de_bd_creada(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        res = self._ejecutar(ClienteGuion([BUENA]))
        copias = list(Path(self.tmp.name).glob("jobs.db.copia-*"))
        self.assertEqual(len(copias), 1)
        self.assertEqual(res["copia"], str(copias[0]))

    def test_bd_vacia(self):
        crear_db(self.db, [])
        res = self._ejecutar(ClienteGuion([BUENA]))
        self.assertEqual(res["pendientes"], 0)
        self.assertEqual(res["procesadas"], 0)

    def test_concurrencia_cuatro_workers_sin_duplicados(self):
        filas = [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)
            for _ in range(24)
        ]
        crear_db(self.db, filas)
        contador = {"n": 0}
        lock = threading.Lock()

        def sim(sistema, usuario):
            with lock:
                contador["n"] += 1
            return ef.simulacion_fase1(sistema, usuario)

        cliente = LLMClient(simulado=sim)
        res = self._ejecutar(cliente, workers=4)
        self.assertEqual(res["aceptadas"], 24)
        self.assertEqual(contador["n"], 24)
        ace = lineas_jsonl(Path(self.out) / "aceptadas.jsonl")
        ids = [r["id"] for r in ace]
        self.assertEqual(len(ids), 24)
        self.assertEqual(len(set(ids)), 24)
        con = sqlite3.connect(self.db)
        n_done = con.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0]
        con.close()
        self.assertEqual(n_done, 24)

    def test_limite_de_tareas(self):
        filas = [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)
            for _ in range(5)
        ]
        crear_db(self.db, filas)
        res = self._ejecutar(ClienteGuion([BUENA]), limite=2)
        self.assertEqual(res["procesadas"], 2)
        con = sqlite3.connect(self.db)
        n_pending = con.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
        con.close()
        self.assertEqual(n_pending, 3)

    def test_bloque_desconocido_failed(self):
        crear_db(self.db, [("runas", "sys", "Pregunta: \"x\"", "{}", 1024, "pending", None)])
        res = self._ejecutar(ClienteGuion([BUENA]))
        self.assertEqual(res["rechazadas"], 1)
        fila = estado_fila(self.db)
        self.assertEqual(fila["status"], "failed")
        self.assertIn("bloque desconocido", fila["error"])

    def test_nunca_escribe_en_final(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        prohibido = str(Path(self.tmp.name) / "final" / "salida")
        with self.assertRaises(ValueError):
            ef.ejecutar(self.db, ClienteGuion([BUENA]), self.kb, out_dir=prohibido)

    def test_liberacion_al_interrumpir_no_toca_otros_workers(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "running", iso_ahora())])
        con = sqlite3.connect(self.db)
        con.execute("UPDATE jobs SET worker='otro-worker' WHERE id=1")
        con.commit()
        con.close()
        res = self._ejecutar(ClienteGuion([BUENA]), huerfano_minutos=9999)
        self.assertEqual(res["liberadas_al_interrumpir"], 0)
        self.assertEqual(estado_fila(self.db)["status"], "running")


class TestDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "jobs.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_no_escribe_ni_copia(self):
        crear_db(self.db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None),
            ("numerologia", "sys", "Pregunta: \"x\"", "{}", 1024, "done", None),
        ])
        res = ef.estimar_dry_run(self.db, workers=4)
        self.assertEqual(res["pendientes"], 1)
        self.assertGreater(res["horas_estimadas"], 0)
        self.assertEqual(list(Path(self.tmp.name).glob("jobs.db.copia-*")), [])
        self.assertEqual(estado_fila(self.db)["status"], "pending")

    def test_estimacion_usa_latencia_piloto(self):
        crear_db(self.db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)
            for _ in range(100)
        ])
        res = ef.estimar_dry_run(self.db, workers=2)
        esperado = 100 * ef.LATENCIA_PILOTO_S / 3600.0 / 2
        self.assertAlmostEqual(res["horas_estimadas"], esperado, places=6)


class TestFormatoShareGPT(unittest.TestCase):
    """D1 (T75): el ejecutor puede emitir ShareGPT consumible por validate_synthetic."""

    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "jobs.db")
        self.out = str(Path(self.tmp.name) / "salida")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_sharegpt_roles_y_nfc(self):
        fila = {
            "id": 7,
            "bloque": "tarot_1",
            "prompt_system": unicodedata.normalize("NFD", "Sistema de lectura áéíóú"),
            "prompt_user": unicodedata.normalize("NFD", "Carta: El Loco (al derecho)."),
            "respuesta": unicodedata.normalize("NFD", "El Loco abre tu camino."),
        }
        out = ef.a_sharegpt(fila)
        self.assertEqual([c["from"] for c in out["conversations"]], ["system", "human", "gpt"])
        for c in out["conversations"]:
            self.assertEqual(c["value"], unicodedata.normalize("NFC", c["value"]))
        self.assertEqual(out["id"], 7)
        self.assertEqual(out["bloque"], "tarot_1")
        self.assertNotIn("respuesta", out)

    def test_a_sharegpt_sin_system(self):
        out = ef.a_sharegpt(
            {"id": 1, "bloque": "etica", "prompt_user": "¿Qué hago?", "respuesta": "Con calma."}
        )
        self.assertEqual([c["from"] for c in out["conversations"]], ["human", "gpt"])

    def test_a_sharegpt_conserva_calculos(self):
        calculos = {"numerologia": {"camino_de_vida": 7}}
        out = ef.a_sharegpt(
            {"id": 2, "bloque": "numerologia", "prompt_user": "p", "respuesta": "r", "calculos": calculos}
        )
        self.assertEqual(out["calculos"], calculos)

    def test_ejecutar_formato_sharegpt(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        res = ef.ejecutar(
            self.db, ClienteGuion([BUENA]), self.kb, workers=1, out_dir=self.out, formato="sharegpt"
        )
        self.assertEqual(res["aceptadas"], 1)
        ace = lineas_jsonl(Path(self.out) / "aceptadas.jsonl")
        self.assertEqual(len(ace), 1)
        self.assertEqual([c["from"] for c in ace[0]["conversations"]], ["system", "human", "gpt"])
        self.assertEqual(ace[0]["bloque"], "tarot_1")
        self.assertNotIn("respuesta", ace[0])

    def test_ejecutar_default_sigue_plano(self):
        crear_db(self.db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)])
        ef.ejecutar(self.db, ClienteGuion([BUENA]), self.kb, workers=1, out_dir=self.out)
        ace = lineas_jsonl(Path(self.out) / "aceptadas.jsonl")
        self.assertIn("respuesta", ace[0])
        self.assertNotIn("conversations", ace[0])


class TestSimEjesAstrales(unittest.TestCase):
    """T75 (apoya D7): el lector simulado menciona los ejes astrales del prompt."""

    CARTA = {
        "fecha": "1990-01-01",
        "hora": "12:00",
        "planetas": {
            "Sol": {"signo": "Capricornio", "grados": "10°00'"},
            "Luna": {"signo": "Acuario", "grados": "20°00'"},
        },
        "ascendente": {"signo": "Piscis", "grados": "15°00'"},
    }

    def test_sim_menciona_ejes_y_pasa_verificador(self):
        kb = ef.cargar_kb()
        tarea = ef.tarea_desde_job(
            "astro_natal", {"carta": self.CARTA, "ciudad": "Madrid"}, "¿Quién soy?", kb
        )
        pr = fp.construir_prompt(tarea, kb)
        texto = ef.simulacion_fase1(pr["system"], pr["user"])
        self.assertIn("Sol en Capricornio", texto)
        self.assertIn("Luna en Acuario", texto)
        self.assertIn("Ascendente en Piscis", texto)
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertTrue(ok, motivos)


CRUZ_POSICIONES = [
    "situación", "obstáculo", "raíz", "pasado", "meta",
    "futuro cercano", "actitud", "entorno", "esperanzas y miedos", "resultado",
]
CRUZ_CARTAS = [
    ("El Loco", False), ("El Mago", False), ("La Sacerdotisa", True),
    ("La Emperatriz", False), ("El Emperador", False), ("El Hierofante", True),
    ("Los Enamorados", False), ("El Carro", False), ("La Fuerza", False),
    ("El Ermitaño", False),
]


class TestBarajaEspanola(unittest.TestCase):
    """T89: bloques espanola_1/3/5/7 con mazo, posiciones y universo de naipes."""

    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def test_kb_carga_baraja(self):
        self.assertIn("baraja", self.kb)
        self.assertEqual(len(self.kb["baraja"]["naipes"]), 40)

    def test_universo_baraja_se_cachea(self):
        u1 = ef.universo_baraja(self.kb)
        u2 = ef.universo_baraja(self.kb)
        self.assertIs(u1, u2)
        self.assertGreaterEqual(len(u1), 40)
        naipes = {u["nombre"] for u in u1 if isinstance(u, dict)}
        self.assertIn("As de Oros", naipes)
        extras = [u for u in u1 if isinstance(u, str)]
        self.assertIn("El Colgado", extras)

    def test_tarea_espanola_3(self):
        payload = {
            "cartas": [
                naipe("As de Oros"),
                naipe("Tres de Copas", True),
                naipe("Siete de Espadas"),
            ],
            "contexto": "trabajo",
            "mazo": "espanol",
            "posiciones": list(fp.POSICIONES_ESPAÑOLA["espanola_3"]),
        }
        tarea = ef.tarea_desde_job("espanola_3", payload, "¿Cómo va?", self.kb)
        self.assertEqual(tarea["familia"], "espanola_3")
        self.assertEqual(tarea["mazo"], "espanol")
        self.assertEqual(tarea["posiciones"], ["pasado", "presente", "futuro"])
        self.assertEqual(len(tarea["cartas"]), 3)
        self.assertTrue(tarea["cartas"][0]["sinonimos"])
        self.assertEqual(tarea["calculos"], {})
        self.assertTrue(tarea["universo_cartas"])

    def test_tarea_espanola_1_sin_posiciones(self):
        payload = {
            "cartas": [naipe("As de Espadas", True)],
            "contexto": "dinero",
            "mazo": "espanol",
        }
        tarea = ef.tarea_desde_job("espanola_1", payload, "¿Cómo va?", self.kb)
        self.assertNotIn("posiciones", tarea)
        self.assertTrue(tarea["cartas"][0]["invertida"])

    def test_sim_espanola_1_pasa_verificador(self):
        payload = {
            "cartas": [naipe("As de Espadas", True)],
            "contexto": "dinero",
            "mazo": "espanol",
        }
        _, _, sim, ok, motivos = pasada_sim(self.kb, "espanola_1", payload)
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))

    def test_sim_espanola_3_pasa_verificador(self):
        payload = {
            "cartas": [
                naipe("As de Oros"),
                naipe("Tres de Copas", True),
                naipe("Siete de Espadas"),
            ],
            "contexto": "trabajo",
            "mazo": "espanol",
            "posiciones": list(fp.POSICIONES_ESPAÑOLA["espanola_3"]),
        }
        _, _, sim, ok, motivos = pasada_sim(self.kb, "espanola_3", payload)
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))

    def test_sim_espanola_5_con_esquema(self):
        cartas = [
            naipe("Rey de Copas"),
            naipe("Caballo de Espadas", True),
            naipe("Cuatro de Bastos"),
            naipe("Sota de Oros"),
            naipe("Siete de Copas", True),
        ]
        payload = {
            "cartas": cartas,
            "contexto": "salud",
            "mazo": "espanol",
            "posiciones": list(fp.POSICIONES_ESPAÑOLA["espanola_5"]),
        }
        _, prompt, sim, ok, motivos = pasada_sim(self.kb, "espanola_5", payload)
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))
        self.assertIn("## Síntesis", sim)
        self.assertIn("## 1. situación — Rey de Copas (al derecho)", sim)
        self.assertIn("## 2. obstáculo — Caballo de Espadas (invertida)", sim)
        for num in range(1, 6):
            self.assertIn(f"## {num}. ", sim)

    def test_sim_espanola_7_con_esquema(self):
        nombres = ["As de Bastos", "Dos de Copas", "Tres de Espadas",
                   "Cuatro de Oros", "Sota de Bastos", "Caballo de Copas",
                   "Rey de Espadas"]
        cartas = [naipe(n, invertida=(i == 3)) for i, n in enumerate(nombres)]
        payload = {
            "cartas": cartas,
            "contexto": "trabajo",
            "mazo": "espanol",
            "posiciones": list(fp.POSICIONES_ESPAÑOLA["espanola_7"]),
        }
        _, _, sim, ok, motivos = pasada_sim(self.kb, "espanola_7", payload)
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))
        self.assertIn("## 1. base — As de Bastos (al derecho)", sim)
        self.assertIn("## 4. futuro — Cuatro de Oros (invertida)", sim)
        self.assertIn("## Síntesis", sim)


class TestSimulacionTiradasLargas(unittest.TestCase):
    """T89: el lector simulado respeta el esquema obligatorio en tiradas largas."""

    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def _payload_cruz(self, todas_derechas=False):
        return {
            "cartas": [
                {"nombre": n, "invertida": (False if todas_derechas else inv)}
                for n, inv in CRUZ_CARTAS
            ],
            "contexto": "trabajo",
            "posiciones": list(CRUZ_POSICIONES),
        }

    def test_cruz_celta_con_esquema(self):
        _, prompt, sim, ok, motivos = pasada_sim(
            self.kb, "cruz_celta", self._payload_cruz()
        )
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))
        self.assertIn("ESQUEMA OBLIGATORIO", prompt["user"])
        self.assertIn("## 1. situación — El Loco (al derecho)", sim)
        self.assertIn("## 3. raíz — La Sacerdotisa (invertida)", sim)
        self.assertIn("## 10. resultado — El Ermitaño (al derecho)", sim)
        self.assertIn("## Síntesis", sim)

    def test_cruz_celta_sin_invertidas_no_menciona_reves(self):
        _, _, sim, ok, motivos = pasada_sim(
            self.kb, "cruz_celta", self._payload_cruz(todas_derechas=True)
        )
        self.assertTrue(ok, motivos)
        self.assertNotIn("invertida", sim)
        self.assertNotIn("inversión", sim)

    def test_cruz_celta_acepta_posiciones_del_payload(self):
        payload = self._payload_cruz()
        tarea = ef.tarea_desde_job("cruz_celta", payload, "¿Cómo va?", self.kb)
        self.assertEqual(tarea["posiciones"], CRUZ_POSICIONES)

    def test_lectura_completa_cuatro_secciones_en_orden(self):
        payload = {
            "carta": CARTA_NATAL,
            "cartas": [
                {"nombre": "El Loco", "invertida": False},
                {"nombre": "La Estrella", "invertida": True},
                {"nombre": "La Luna", "invertida": False},
            ],
            "fecha": "1990-01-01",
            "nombre": "Marta Ruiz",
            "contexto": "trabajo",
            "ciudad": "Madrid",
        }
        _, _, sim, ok, motivos = pasada_sim(
            self.kb, "lectura_completa", payload, "¿Qué camino tomo?"
        )
        self.assertTrue(ok, motivos)
        self.assertFalse(ef.respuesta_truncada(sim))
        posiciones = ["## Carta natal", "## Tirada de tres cartas",
                      "## Numerología", "## Síntesis"]
        indices = [sim.find(p) for p in posiciones]
        self.assertTrue(all(i >= 0 for i in indices), sim)
        self.assertEqual(indices, sorted(indices))


class TestMaxTokensTabla(unittest.TestCase):
    """T89: el máximo efectivo sale de RECOMENDACION_MAX_TOKENS sobre el piso."""

    def test_espanola_7_sube_a_5120(self):
        fila = {"bloque": "espanola_7", "max_tokens": 1024}
        self.assertEqual(ef.max_tokens_efectivo(fila, ef.PISO_MAX_TOKENS), 5120)

    def test_espanola_1_respeta_piso(self):
        fila = {"bloque": "espanola_1", "max_tokens": 1024}
        self.assertEqual(ef.max_tokens_efectivo(fila, ef.PISO_MAX_TOKENS), 4096)

    def test_espanola_5_piso_e_igual(self):
        fila = {"bloque": "espanola_5", "max_tokens": 1024}
        self.assertEqual(ef.max_tokens_efectivo(fila, ef.PISO_MAX_TOKENS), 4096)

    def test_bloque_sin_tabla_usa_piso(self):
        fila = {"bloque": "runas", "max_tokens": 1024}
        self.assertEqual(ef.max_tokens_efectivo(fila, ef.PISO_MAX_TOKENS), 4096)

    def test_lectura_completa_6144(self):
        fila = {"bloque": "lectura_completa", "max_tokens": 1024}
        self.assertEqual(ef.max_tokens_efectivo(fila, ef.PISO_MAX_TOKENS), 6144)


if __name__ == "__main__":
    unittest.main()
