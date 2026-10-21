#!/usr/bin/env python3
"""Tests del backend Mercury del ejecutor de fase 1 (T95), sin red real."""

import io
import json
import os
import sqlite3
import sys
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ejecutor_fase1 as ef  # noqa: E402
import generate_tasks as gt  # noqa: E402
import llm_client  # noqa: E402

PROMPT_TAROT = (
    "Tirada de una carta de tarot.\n\n"
    "Carta: El Loco (al derecho).\nContexto: trabajo.\n"
    'Pregunta del consultante: "¿Cómo va mi proyecto?"'
)
PAYLOAD_TAROT = json.dumps(
    {"carta": {"nombre": "El Loco", "invertida": False}, "contexto": "trabajo"},
    ensure_ascii=False,
)
PAYLOAD_CRUZ = json.dumps(
    {
        "cartas": [{"nombre": "El Loco", "invertida": False}],
        "contexto": "trabajo",
        "posiciones": ["situación"],
    },
    ensure_ascii=False,
)
PROMPT_CRUZ = (
    "Tirada de la Cruz Celta (diez cartas).\n\n"
    "Posición situación: El Loco (al derecho).\n"
    'Pregunta del consultante: "¿Cómo va mi proyecto?"'
)


class FakeResp:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


class ClienteRegistro:
    """Registra los kwargs de cada llamada y devuelve una respuesta fija."""

    def __init__(self, respuesta="Texto de prueba."):
        self.respuesta = respuesta
        self.kwargs = []

    def chat(self, sistema, usuario, **kwargs):
        self.kwargs.append(dict(kwargs))
        return self.respuesta


class ClienteError(ClienteRegistro):
    def __init__(self, errores=999):
        super().__init__()
        self.errores = errores
        self.llamadas = 0

    def chat(self, sistema, usuario, **kwargs):
        self.llamadas += 1
        if self.llamadas <= self.errores:
            raise ConnectionError("nodos caídos")
        return ef.simulacion_fase1(sistema, usuario)


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


def fila(bloque="tarot_1", prompt=PROMPT_TAROT, payload=PAYLOAD_TAROT):
    return (
        bloque, "system", prompt, payload, 1024, "pending",
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


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


class BaseMercury(unittest.TestCase):
    def setUp(self):
        self._tmp = __import__("tempfile").TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.db = self.dir / "jobs.db"
        self.salida = self.dir / "salida"
        self.kb = ef.cargar_kb()
        self._entorno = os.environ.copy()
        os.environ.pop("INCEPTION_API_KEY", None)
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        os.environ.clear()
        os.environ.update(self._entorno)
        self._tmp.cleanup()

    def aceptadas(self):
        return lineas_jsonl(self.salida / "aceptadas.jsonl")

    def rechazadas(self):
        return lineas_jsonl(self.salida / "rechazadas.jsonl")


class TestClienteMercury(BaseMercury):
    def test_clave_ausente_menciona_variable_y_no_filtra(self):
        with self.assertRaises(RuntimeError) as ctx:
            ef.crear_cliente_mercury()
        mensaje = str(ctx.exception)
        self.assertIn("INCEPTION_API_KEY", mensaje)
        self.assertNotIn("sk-", mensaje)

    def test_clave_presente_se_usa_sin_imprimirla(self):
        os.environ["INCEPTION_API_KEY"] = "clave-de-prueba-123"
        cliente = ef.crear_cliente_mercury()
        self.assertEqual(cliente._specs[0]["model"], "mercury-3")
        self.assertEqual(cliente.reasoning_effort, "instant")
        self.assertEqual(cliente._specs[0]["api_key_env"], "INCEPTION_API_KEY")
        self.assertNotIn("clave-de-prueba-123", repr(cliente.__dict__))

    def test_simulado_no_exige_clave(self):
        cliente = ef.crear_cliente_mercury(simulado=ef.simulacion_fase1)
        self.assertIs(cliente.simulado, ef.simulacion_fase1)

    def test_main_sin_clave_sale_2_sin_copiar_bd(self):
        crear_db(self.db, [fila()])
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            rc = ef.main(["--db", str(self.db), "--backend", "mercury", "--out-dir", str(self.salida)])
        self.assertEqual(rc, 2)
        self.assertIn("INCEPTION_API_KEY", err.getvalue())
        self.assertEqual(list(self.db.parent.glob(self.db.name + ".copia-*")), [])


class TestTokensPorFamilia(BaseMercury):
    def test_tabla_y_techo(self):
        self.assertEqual(ef.max_tokens_mercury("tarot_1"), 1536)
        self.assertEqual(ef.max_tokens_mercury("cruz_celta"), 6144)
        self.assertEqual(ef.max_tokens_mercury("desconocida"), 6144)

    def test_procesar_una_mercury_pasa_tope_por_familia(self):
        for bloque, prompt, payload, esperado in (
            ("tarot_1", PROMPT_TAROT, PAYLOAD_TAROT, 1536),
            ("cruz_celta", PROMPT_CRUZ, PAYLOAD_CRUZ, 6144),
        ):
            cliente = ClienteRegistro()
            f = {
                "id": 1,
                "bloque": bloque,
                "prompt": prompt,
                "payload": payload,
                "max_tokens": 1024,
            }
            reg = ef.procesar_una(f, cliente, self.kb, max_reintentos=0, backend=ef.GENERADOR_MERCURY)
            self.assertEqual(reg["generador"], "mercury-3")
            self.assertEqual(len(cliente.kwargs), 1)
            self.assertEqual(cliente.kwargs[0]["max_completion_tokens"], esperado)
            self.assertEqual(cliente.kwargs[0]["max_tokens"], esperado)


class TestEjecucionMercury(BaseMercury):
    def test_marca_generador_en_aceptadas(self):
        crear_db(self.db, [fila()])
        res = ef.ejecutar(
            self.db,
            ef.crear_cliente_mercury(simulado=ef.simulacion_fase1),
            self.kb,
            workers=1,
            backend=ef.GENERADOR_MERCURY,
            out_dir=self.salida,
            formato="sharegpt",
        )
        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(res["backend"], "mercury-3")
        registros = self.aceptadas()
        self.assertEqual(registros[0]["generador"], "mercury-3")
        self.assertEqual(estado_fila(self.db)["status"], "done")

    def test_local_marca_generador_local(self):
        crear_db(self.db, [fila()])
        res = ef.ejecutar(
            self.db,
            llm_client.LLMClient(simulado=ef.simulacion_fase1),
            self.kb,
            workers=1,
            out_dir=self.salida,
            formato="sharegpt",
        )
        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(self.aceptadas()[0]["generador"], "local")

    def test_reanudar_no_duplica(self):
        crear_db(self.db, [fila(), fila()])
        cliente = ef.crear_cliente_mercury(simulado=ef.simulacion_fase1)
        primero = ef.ejecutar(
            self.db, cliente, self.kb, workers=1, limite=1,
            backend=ef.GENERADOR_MERCURY, out_dir=self.salida,
        )
        segundo = ef.ejecutar(
            self.db, cliente, self.kb, workers=1, limite=1,
            backend=ef.GENERADOR_MERCURY, out_dir=self.salida,
        )
        registros = self.aceptadas()
        self.assertEqual(primero["aceptadas"], 1)
        self.assertEqual(segundo["aceptadas"], 1)
        self.assertEqual(len(registros), 2)
        self.assertEqual(len({r["id"] for r in registros}), 2)

    def test_parada_por_errores_en_ventana(self):
        crear_db(self.db, [fila() for _ in range(60)])
        cliente = ClienteError(errores=11)
        res = ef.ejecutar(
            self.db, cliente, self.kb, workers=1,
            backend=ef.GENERADOR_MERCURY, out_dir=self.salida,
            ventana_errores=50, umbral_error=0.20,
        )
        self.assertTrue(res["parada"])
        self.assertEqual(res["procesadas"], 50)
        self.assertEqual(res["errores_red"], 11)
        self.assertEqual(res["no_procesadas_por_parada"], 10)
        self.assertEqual(res["aceptadas"], 39)

    def test_rechazo_tras_reintentos_no_entra_en_aceptadas(self):
        crear_db(self.db, [fila()])
        cliente = ClienteRegistro("La Torre lo destruye todo")
        res = ef.ejecutar(
            self.db, cliente, self.kb, workers=1, max_reintentos=2,
            backend=ef.GENERADOR_MERCURY, out_dir=self.salida,
        )
        self.assertEqual(res["aceptadas"], 0)
        self.assertEqual(res["rechazadas"], 1)
        self.assertEqual(self.aceptadas(), [])
        registros = self.rechazadas()
        self.assertTrue(registros[0]["motivos"])
        self.assertEqual(registros[0]["generador"], "mercury-3")
        self.assertEqual(len(cliente.kwargs), 3)
        self.assertEqual(estado_fila(self.db)["status"], "failed")

    def test_429_reintenta_y_acepta(self):
        crear_db(self.db, [fila()])
        os.environ["INCEPTION_API_KEY"] = "clave-de-prueba"
        posts = []

        def fake_post(url, **kwargs):
            posts.append((url, kwargs))
            if len(posts) == 1:
                return FakeResp(429, {}, {"Retry-After": "0"})
            payload = kwargs["json"]
            contenido = ef.simulacion_fase1(
                payload["messages"][0]["content"], payload["messages"][1]["content"]
            )
            return FakeResp(200, {"choices": [{"message": {"content": contenido}}]})

        cliente = ef.crear_cliente_mercury(max_concurrencia=1, tasa_max_por_minuto=0)
        with mock.patch.object(llm_client.requests, "post", side_effect=fake_post), \
                mock.patch.object(llm_client.time, "sleep"):
            res = ef.ejecutar(
                self.db, cliente, self.kb, workers=1,
                backend=ef.GENERADOR_MERCURY, out_dir=self.salida, formato="sharegpt",
            )

        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(res["errores_red"], 0)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0][0], ef.BACKEND_URL_MERCURY + "/chat/completions")
        payload = posts[0][1]["json"]
        self.assertEqual(payload["model"], "mercury-3")
        self.assertEqual(payload["reasoning_effort"], "instant")
        self.assertEqual(payload["max_completion_tokens"], 1536)
        self.assertEqual(posts[0][1]["headers"]["Authorization"], "Bearer clave-de-prueba")
        self.assertEqual(self.aceptadas()[0]["generador"], "mercury-3")


class TestEstimacion(BaseMercury):
    def test_solo_estimar_no_copia_y_calcula_backends(self):
        crear_db(self.db, [fila(), fila(), fila("cruz_celta", PROMPT_CRUZ, PAYLOAD_CRUZ)])
        res = ef.estimar_backends(self.db, workers_local=2, workers_mercury=3)
        self.assertEqual(res["pendientes"], 3)
        self.assertEqual(res["por_bloque"]["tarot_1"]["pendientes"], 2)
        self.assertEqual(res["por_bloque"]["tarot_1"]["max_completion"], 1536)
        self.assertEqual(res["por_bloque"]["cruz_celta"]["max_completion"], 6144)
        self.assertAlmostEqual(res["local"]["horas"], 3 * ef.LATENCIA_PILOTO_S / 2 / 3600)
        self.assertAlmostEqual(res["mercury"]["horas"], 3 * ef.LATENCIA_MERCURY_S / 3 / 3600)
        self.assertGreater(res["mercury"]["coste_usd"], 0)
        self.assertEqual(list(self.db.parent.glob(self.db.name + ".copia-*")), [])

    def test_main_solo_estimar_no_toca_bd(self):
        crear_db(self.db, [fila()])
        salida = io.StringIO()
        with redirect_stdout(salida):
            rc = ef.main(["--db", str(self.db), "--solo-estimar"])
        self.assertEqual(rc, 0)
        self.assertIn("mercury", salida.getvalue().lower())
        self.assertEqual(estado_fila(self.db)["status"], "pending")
        self.assertEqual(list(self.db.parent.glob(self.db.name + ".copia-*")), [])

    def test_main_mercury_simulado_funciona(self):
        crear_db(self.db, [fila()])
        with redirect_stdout(io.StringIO()):
            rc = ef.main([
                "--db", str(self.db), "--backend", "mercury", "--simulado",
                "--workers", "1", "--limite", "1", "--out-dir", str(self.salida),
            ])
        self.assertEqual(rc, 0)
        self.assertEqual(self.aceptadas()[0]["generador"], "mercury-3")


if __name__ == "__main__":
    unittest.main()
