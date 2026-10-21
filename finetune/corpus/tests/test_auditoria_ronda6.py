"""Auditoría ronda 6 (T96): generación de fase 1 con Mercury y cierre.

Casos adversos sobre el ejecutor de fase 1, `llm_client`, `generate_tasks`,
el verificador de `fase1_prompts`, `merge_final`, `cierre_recopilacion` y
`consenso_kb`. Nada de red ni de LLM real: clientes y `requests.post`
simulados, BD y JSONL temporales.

Los defectos confirmados por ejecución se afirman aquí con el comportamiento
CORRECTO y se marcan `expectedFailure` (para que check.sh siga en CHECK OK).
Ver docs/AUDITORIA_RONDA6.md.
"""

import json
import os
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cierre_recopilacion as cierre  # noqa: E402
import consenso_kb  # noqa: E402
import ejecutor_fase1 as ef  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import generate_tasks as gt  # noqa: E402
import llm_client  # noqa: E402
import merge_final  # noqa: E402
import validate_synthetic as vs  # noqa: E402
from cartas import NAIPES_ESPANOLES  # noqa: E402

BUENA = "El Loco abre tu camino: es un comienzo lleno de posibilidad."
PROMPT_TAROT = (
    "Tirada de una carta de tarot.\n\n"
    "Carta: El Loco (al derecho).\nContexto: trabajo.\n"
    'Pregunta del consultante: "¿Cómo va mi proyecto?"'
)
PAYLOAD_TAROT = json.dumps(
    {"carta": {"nombre": "El Loco", "invertida": False}, "contexto": "trabajo"},
    ensure_ascii=False,
)

KB_MIN = {
    "tarot": {
        "mayores": [
            {"nombre": "El Sol"},
            {"nombre": "La Luna"},
            {"nombre": "La Torre"},
        ],
        "menores": [],
    }
}


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


class ClienteGuion:
    """Devuelve respuestas por orden; al agotarlas repite la última."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []
        self._lock = threading.Lock()

    def chat(self, sistema, usuario, **kwargs):
        with self._lock:
            self.llamadas.append((sistema, usuario, kwargs))
            if len(self._respuestas) > 1:
                return self._respuestas.pop(0)
            return self._respuestas[0]


class ClienteError:
    def chat(self, *args, **kwargs):
        raise ConnectionError("nodos caídos")


# --------------------------------------------------------------------------- #
# GRADO 1: duplicación de tareas y clave enviada al endpoint equivocado
# --------------------------------------------------------------------------- #
class TestGeneracionIdempotente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = sqlite3.connect(str(Path(self.tmp.name) / "jobs.db"))
        gt.crear_tabla(self.con)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def _filas(self):
        return [
            ("alfa", "sys", "p1", "{}", 100),
            ("alfa", "sys", "p2", "{}", 100),
            ("alfa", "sys", "p3", "{}", 100),
        ]

    @unittest.expectedFailure
    def test_replace_pending_no_duplica_tareas_ya_hechas(self):
        """Regenerar con la misma semilla reinserta lo que ya estaba `done`.

        `insertar_jobs(..., replace_pending=True)` borra solo las pendientes y
        vuelve a insertar TODAS las filas del bloque. Si el bloque ya se había
        procesado (done) y la generación es determinista (misma `--seed`), las
        mismas tareas quedan duplicadas: una hecha y otra pendiente.

        Reproduccion: test_replace_pending_no_duplica_tareas_ya_hechas.
        """
        filas = self._filas()
        gt.insertar_jobs(self.con, filas, replace_pending=False)
        self.con.execute("UPDATE jobs SET status='done' WHERE bloque='alfa'")
        self.con.commit()
        gt.insertar_jobs(self.con, filas, replace_pending=True)
        total = self.con.execute(
            "SELECT COUNT(*) FROM jobs WHERE bloque='alfa'").fetchone()[0]
        self.assertEqual(total, len(filas))


class TestEndpointYClave(unittest.TestCase):
    def test_la_clave_no_viaja_al_endpoint_equivocado(self):
        """Sano: URL, modelo y clave salen siempre del mismo `spec`.

        `_chat_real` lee `_idx` y construye `spec`/`url`/`headers` de ese mismo
        índice; el endpoint devuelto por `_siguiente_endpoint()` no se usa para
        la petición. Aun con dos hilos intercalados, no se cruzan credenciales.
        (La variable `endpoint` es código muerto; ver BAJOS en la auditoría.)
        """
        registros = []

        def post_falso(url, **kwargs):
            registros.append({
                "url": url,
                "model": kwargs["json"]["model"],
                "auth": (kwargs.get("headers") or {}).get("Authorization"),
            })
            resp = mock.Mock()
            resp.status_code = 200
            resp.headers = {}
            resp.raise_for_status.return_value = None
            resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
            return resp

        cliente = llm_client.LLMClient(
            endpoints=[
                {"url": "http://nodo-a/v1", "model": "modelo-a",
                 "api_key_env": "T96_CLAVE_A"},
                {"url": "http://nodo-b/v1", "model": "modelo-b",
                 "api_key_env": "T96_CLAVE_B"},
            ],
            max_concurrencia=2,
            tasa_max_por_minuto=0,
        )
        original = llm_client.LLMClient._siguiente_endpoint
        barrera = threading.Barrier(2)

        def siguiente_con_barrera(self):
            # Fuerza el interleaving: ambas peticiones leen `_idx` antes de
            # que ninguna consuma su turno del round-robin.
            barrera.wait(timeout=5)
            return original(self)

        cliente._siguiente_endpoint = types.MethodType(siguiente_con_barrera, cliente)
        errores = []

        def trabajar():
            try:
                cliente.chat("sistema", "usuario", max_tokens=8)
            except Exception as exc:  # pragma: no cover - diagnóstico
                errores.append(exc)

        with mock.patch.dict(os.environ, {
                "T96_CLAVE_A": "clave-a", "T96_CLAVE_B": "clave-b"}):
            with mock.patch.object(llm_client.requests, "post", side_effect=post_falso):
                hilos = [threading.Thread(target=trabajar) for _ in range(2)]
                for h in hilos:
                    h.start()
                for h in hilos:
                    h.join(timeout=10)

        self.assertEqual(errores, [])
        self.assertEqual(len(registros), 2)
        for reg in registros:
            if reg["url"].startswith("http://nodo-a"):
                self.assertEqual(reg["model"], "modelo-a")
                self.assertEqual(reg["auth"], "Bearer clave-a")
            else:
                self.assertEqual(reg["model"], "modelo-b")
                self.assertEqual(reg["auth"], "Bearer clave-b")


# --------------------------------------------------------------------------- #
# GRADO 2: parada por errores, fugas de evaluación, verificador y cierre
# --------------------------------------------------------------------------- #
class TestParadaPorErrores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = ef.cargar_kb()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "jobs.db")
        self.out = str(Path(self.tmp.name) / "salida")

    def tearDown(self):
        self.tmp.cleanup()

    def _cuatro_rechazos(self):
        crear_db(self.db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)
            for _ in range(4)
        ])

    @unittest.expectedFailure
    def test_los_rechazos_del_verificador_cuentan_para_la_parada(self):
        """La ventana de errores solo mira `error_red`, no los rechazos.

        Con `ventana_errores=2` y `umbral_error=0.2`, cuatro lecturas
        rechazadas por el verificador (100 % de fallos) deberían disparar la
        parada; hoy la ventana queda a cero y el run sigue.

        Reproduccion: test_los_rechazos_del_verificador_cuentan_para_la_parada.
        """
        self._cuatro_rechazos()
        res = ef.ejecutar(self.db, ClienteGuion(["Hola."]), self.kb,
                          workers=1, out_dir=self.out,
                          ventana_errores=2, umbral_error=0.2)
        self.assertEqual(res["rechazadas"], 4)
        self.assertIsNotNone(res["parada"])

    def test_los_errores_de_red_si_disparan_la_parada(self):
        """Comportamiento actual (sano): los fallos de transporte paran el run."""
        crear_db(self.db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None)
            for _ in range(3)
        ])
        res = ef.ejecutar(self.db, ClienteError(), self.kb, workers=1,
                          out_dir=self.out, ventana_errores=2, umbral_error=0.2)
        self.assertIsNotNone(res["parada"])
        self.assertEqual(res["procesadas"], 2)
        self.assertEqual(res["no_procesadas_por_parada"], 1)


class TestFugaEvaluacion(unittest.TestCase):
    @staticmethod
    def _fila(i, pregunta, respuesta):
        return {
            "conversations": [
                {"from": "human", "value": pregunta},
                {"from": "gpt", "value": respuesta},
            ],
            "id": i,
        }

    @unittest.expectedFailure
    def test_el_prompt_de_evaluacion_no_aparece_en_train(self):
        """El dedupe compara respuestas, no preguntas: el mismo prompt se cuela.

        Una pregunta real reservada para val/test puede volver a train vía una
        fila sintética con OTRA respuesta (el par no es duplicado exacto). Se
        espera que ningún human de train esté en val/test.

        Reproduccion: test_el_prompt_de_evaluacion_no_aparece_en_train.
        """
        pregunta = "¿Qué significa la carta El Sol en la tirada %d del tarot?"
        reales = [
            self._fila(1000 + i, pregunta % i,
                       "La carta del Sol representa la claridad y la energía "
                       "vital en la tirada número %d." % i)
            for i in range(20)
        ]
        sinteticos = [
            self._fila(2000 + i, pregunta % i,
                       "El Sol anuncia un camino luminoso y favorable para el "
                       "consultante en la tirada número %d." % i)
            for i in range(20)
        ]
        meta = [{"block": "tarot_1"} for _ in sinteticos]
        res = merge_final.fusionar([], reales, sinteticos, meta,
                                   {"seed": 42, "train_ratio": 0.8, "val_ratio": 0.1})
        humanos_train = {merge_final.human_of(r) for r in res["train"]}
        humanos_eval = {merge_final.human_of(r) for r in res["val"] + res["test"]}
        self.assertTrue(humanos_eval)
        self.assertEqual(humanos_train & humanos_eval, set())


class TestVerificador(unittest.TestCase):
    def _tarea(self, payload):
        return ef.tarea_desde_job(
            "tarot_1", payload, "¿Qué me depara el trabajo?", KB_MIN)

    @unittest.expectedFailure
    def test_rechaza_carta_inventada_fuera_del_universo(self):
        """Solo compara contra el universo conocido: un arcano inventado pasa.

        Reproduccion: test_rechaza_carta_inventada_fuera_del_universo.
        """
        tarea = self._tarea({"cartas": [{"nombre": "El Sol", "invertida": False}]})
        texto = "El Sol trae claridad. El Arquitecto abre tu camino."
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertFalse(ok, motivos)

    @unittest.expectedFailure
    def test_la_orientacion_se_comprueba_por_carta(self):
        """Basta una marca global de inversión: El Sol invertida queda sin marcar.

        Reproduccion: test_la_orientacion_se_comprueba_por_carta.
        """
        tarea = self._tarea({"cartas": [
            {"nombre": "El Sol", "invertida": True},
            {"nombre": "La Luna", "invertida": False},
        ]})
        texto = ("El Sol ilumina tu camino. La Luna aparece invertida y te "
                 "invita al recogimiento.")
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertFalse(ok, motivos)

    @unittest.expectedFailure
    def test_numero_contradicho_en_frase_natural(self):
        """`_verif_numeros` exige la etiqueta pegada al dígito.

        «Tu camino de vida es el 8» no se detecta contra el 7 calculado.

        Reproduccion: test_numero_contradicho_en_frase_natural.
        """
        tarea = ef.tarea_desde_job(
            "numerologia", {"fecha": "1992-11-29", "nombre": "Ana"},
            "¿Qué me depara el trabajo?", KB_MIN)
        self.assertEqual(tarea["calculos"]["numerologia"]["camino_de_vida"], 7)
        ok, motivos = fp.verificar_lectura(
            tarea, "Tu camino de vida es el 8 y marca tu año.")
        self.assertFalse(ok, motivos)

    @unittest.expectedFailure
    def test_promesa_vedada_con_perifrasis(self):
        """«Puedes dejar de tomar la medicación» no coincide con el patrón.

        Reproduccion: test_promesa_vedada_con_perifrasis.
        """
        tarea = self._tarea({"cartas": [{"nombre": "El Sol", "invertida": False}]})
        texto = ("El Sol te acompaña. Puedes dejar de tomar la medicación sin "
                 "problema.")
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertFalse(ok, motivos)

    @unittest.expectedFailure
    def test_una_negativa_expresa_no_es_promesa_vedada(self):
        """«No puedo darte números de la lotería» se rechaza como si prometiera.

        `_negado` solo mira 6 caracteres antes del patrón y aquí la negación
        queda más lejos.

        Reproduccion: test_una_negativa_expresa_no_es_promesa_vedada.
        """
        tarea = self._tarea({"cartas": [{"nombre": "El Sol", "invertida": False}]})
        texto = "El Sol te acompaña. No puedo darte números de la lotería."
        ok, motivos = fp.verificar_lectura(tarea, texto)
        self.assertTrue(ok, motivos)

    # ----- comportamientos sanos -----

    def test_carta_repetida_en_la_tirada_se_rechaza(self):
        tarea = self._tarea({"cartas": [
            {"nombre": "El Sol", "invertida": False},
            {"nombre": "El Sol", "invertida": False},
        ]})
        ok, motivos = fp.verificar_lectura(
            tarea, "El Sol trae claridad. El Sol abre tu camino.")
        self.assertFalse(ok)
        self.assertTrue(any("repetida" in m for m in motivos), motivos)

    def test_baraja_espanola_rechaza_arcano_de_tarot(self):
        """El universo de la baraja incluye el tarot como control de ajenas."""
        kb = ef.cargar_kb()
        tarea = ef.tarea_desde_job(
            "espanola_1", {"cartas": [NAIPES_ESPANOLES[0]]}, "¿x?", kb)
        ok, motivos = fp.verificar_lectura(
            tarea, "El As de Bastos abre el camino. La Torre aparece al fondo.")
        self.assertFalse(ok)
        self.assertTrue(any("La Torre" in m for m in motivos), motivos)

    def test_aceptadas_llevan_el_generador_de_mercury(self):
        """La etiqueta de origen llega al dataset y el presupuesto es el de T89."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "jobs.db")
        crear_db(db, [("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024,
                       "pending", None)])
        cliente = ClienteGuion([BUENA])
        res = ef.ejecutar(db, cliente, ef.cargar_kb(), workers=1,
                          out_dir=str(Path(tmp.name) / "salida"),
                          backend=ef.GENERADOR_MERCURY, formato="sharegpt")
        self.assertEqual(res["aceptadas"], 1)
        self.assertEqual(cliente.llamadas[0][2]["max_completion_tokens"],
                         fp.RECOMENDACION_MAX_TOKENS["tarot_1"])
        fila = lineas_jsonl(Path(tmp.name) / "salida" / "aceptadas.jsonl")[0]
        self.assertEqual(fila["generador"], ef.GENERADOR_MERCURY)


class TestValidador(unittest.TestCase):
    @unittest.expectedFailure
    def test_el_validador_rechaza_una_carta_inventada(self):
        """`grounding` exige las cartas del prompt, pero no prohíbe las de más.

        Un texto que menciona El Sol (la carta de la tirada) y además «El
        Arquitecto» (arcano inexistente) pasa las puertas y llega a
        `synthetic_clean.jsonl`.

        Reproduccion: test_el_validador_rechaza_una_carta_inventada.
        """
        prompt = (
            "Tirada de una carta de tarot.\n\n"
            "Carta: El Sol (al derecho).\nContexto: trabajo.\n"
            'Pregunta del consultante: "¿Cómo va mi proyecto?"'
        )
        respuesta = (
            "La carta El Sol ilumina tu proyecto y muestra una etapa de "
            "claridad. Su energía te invita a presentar tu trabajo con "
            "confianza y a sostener el esfuerzo. El Arquitecto aparece como "
            "una figura inventada que no pertenece a la tirada, y aun así el "
            "texto sigue adelante. Conviene ordenar prioridades, hablar con tu "
            "equipo y reservar tiempo para revisar avances. La cosecha llegará "
            "si mantienes la constancia y cuidas los detalles del proceso. Tu "
            "pregunta encuentra una respuesta favorable, con espacio para "
            "crecer durante las próximas semanas. Evita dispersarte y confía "
            "en lo que ya has construido con paciencia y oficio."
        )
        row = {"conversations": [
            {"from": "human", "value": prompt},
            {"from": "gpt", "value": respuesta},
        ]}
        args = types.SimpleNamespace(
            min_chars=400, max_chars=12000, max_repetition=0.12)
        ok, motivo = vs.validate(row, args, "tarot_1")
        self.assertFalse(ok, motivo)


class TestCierreDedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = str(Path(self.tmp.name) / "consenso.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.expectedFailure
    def test_dedupe_no_se_queda_la_ultima_si_es_peor(self):
        """El dedupe conserva la ÚLTIMA fila de cada celda, sea fallback o no.

        Reproduccion: test_dedupe_no_se_queda_la_ultima_si_es_peor.
        """
        buena = {"entidad_id": "tarot|loco", "faceta": "significado",
                 "texto": "lectura buena", "fallback": False}
        mala = {"entidad_id": "tarot|loco", "faceta": "significado",
                "texto": "relleno de fallback", "fallback": True}
        Path(self.ruta).write_text(
            json.dumps(buena, ensure_ascii=False) + "\n" +
            json.dumps(mala, ensure_ascii=False) + "\n", encoding="utf-8")
        cierre.paso1_dedupe_consenso({"consenso": self.ruta}, lambda *a, **k: None)
        filas = [json.loads(l) for l in Path(self.ruta).read_text(
            encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["texto"], "lectura buena")
        self.assertFalse(filas[0].get("fallback"))


class TestPerdidasSilenciosas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "datos.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_jsonl_descarta_la_linea_corrupta_sin_aviso(self):
        """Documenta la pérdida silenciosa (BAJO en AUDITORIA_RONDA6).

        Hoy no hay contador ni aviso: una línea truncada de aceptadas
        desaparece del dataset sin rastro. El test fija el comportamiento
        actual para que un futuro arreglo lo cambie a propósito.
        """
        self.ruta.write_text(
            '{"a": 1}\n{"a": 2, "b": "cortada', encoding="utf-8")
        self.assertEqual(merge_final.load_jsonl(self.ruta), [{"a": 1}])

    @unittest.expectedFailure
    def test_claves_de_exclusion_con_hash_vacio_no_crean_celda(self):
        """Una clave de exclusión sin hash no excluye nada y pasa en silencio.

        Reproduccion: test_claves_de_exclusion_con_hash_vacio_no_crean_celda.
        """
        ruta = str(Path(self.tmp.name) / "claves.jsonl")
        Path(ruta).write_text("\n".join([
            json.dumps({"entidad_id": "e", "faceta": "f", "hash_seccion": "abc"}),
            json.dumps({"entidad_id": "e"}),  # sin faceta: se salta
            json.dumps({"entidad_id": "e", "faceta": "f", "hash_seccion": ""}),
        ]) + "\n", encoding="utf-8")
        self.assertEqual(consenso_kb.cargar_claves_exclusion(ruta),
                         {("e", "f"): {"abc"}})


class TestHuerfanas(unittest.TestCase):
    def test_un_running_reciente_no_se_recupera_al_reanudar(self):
        """Documenta el comportamiento (BAJO): solo se recupera por antigüedad.

        Un `running` de un worker muerto hace menos de `--huerfano-minutos`
        no vuelve a `pending`: la reanudación inmediata lo ignora en silencio.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "jobs.db")
        crear_db(db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "running", None),
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None),
        ])
        con = sqlite3.connect(db)
        con.execute("UPDATE jobs SET updated_at=? WHERE id=1", (ef._ahora(),))
        con.commit()
        con.close()
        res = ef.ejecutar(db, ClienteGuion([BUENA]), ef.cargar_kb(),
                          workers=1, out_dir=str(Path(tmp.name) / "salida"),
                          huerfano_minutos=30.0)
        self.assertEqual(res["huerfanas_recuperadas"], 0)
        self.assertEqual(res["procesadas"], 1)
        self.assertEqual(estado_fila(db, 1)["status"], "running")


class TestExcepcionNoControlada(unittest.TestCase):
    @unittest.expectedFailure
    def test_una_excepcion_en_un_job_no_aborta_todo_el_run(self):
        """`f.result()` no está protegido: un fallo no capturado tumba la pasada.

        Reproduccion: test_una_excepcion_en_un_job_no_aborta_todo_el_run.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = str(Path(tmp.name) / "jobs.db")
        crear_db(db, [
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None),
            ("tarot_1", "sys", PROMPT_TAROT, PAYLOAD_TAROT, 1024, "pending", None),
        ])
        original = ef.procesar_una

        def falla_en_el_segundo(fila, *args, **kwargs):
            if fila["id"] == 2:
                raise RuntimeError("fallo inesperado del procesador")
            return original(fila, *args, **kwargs)

        with mock.patch.object(ef, "procesar_una", side_effect=falla_en_el_segundo):
            res = ef.ejecutar(db, ClienteGuion([BUENA]), ef.cargar_kb(),
                              workers=2, out_dir=str(Path(tmp.name) / "salida"))
        self.assertEqual(res["procesadas"], 2)
        self.assertEqual(estado_fila(db, 2)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
