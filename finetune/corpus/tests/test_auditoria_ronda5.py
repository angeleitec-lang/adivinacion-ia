"""Auditoría ronda 5 (T81): casos adversos sobre consenso, KB v2, descarga,
ejecutor de fase 1, prompts y KB de la baraja.

Los defectos confirmados por ejecución se documentan como expectedFailure
(el test afirma el comportamiento CORRECTO, que aún no ocurre); los
comportamientos verificados como sanos se afirman directamente.
Nada de esto toca red ni LLM real. Ver docs/AUDITORIA_RONDA5.md.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_kb_baraja
import consenso_kb
import descubrir_fuentes as df
import ejecutor_fase1
import ensayo_extremo
import fase1_prompts as fp
import kb_v2
import llm_client
import recuperacion_descarga as rd


class ClienteFalsoConsenso:
    """Cliente que siempre devuelve la partición pedida (sin LLM)."""

    def __init__(self, grupos, contradicciones=None, falla=False):
        self.grupos = grupos
        self.contradicciones = contradicciones or []
        self.falla = falla

    def chat_json(self, sistema, prompt, validador=None, **kw):
        if self.falla:
            raise ValueError("respuesta invalida")
        return {"grupos": self.grupos, "contradicciones": self.contradicciones}


class TestConsensoFuentes(unittest.TestCase):
    """consenso_kb: independencia de fuentes y ordenación de ids."""

    def test_mayoritaria_con_fuente_id_none_no_crashea(self):
        """fuente_id=None (web sin id) conviviendo con str no debe tumbar el run.

        Reproduccion: celda con dos afirmaciones equivalentes, una de una web
        sin fuente_id (solo dominio) y otra de 'waite'. construir_consensos
        hace sorted({None, 'waite'}) -> TypeError.
        """
        celdas = {
            ("tarot|loco", "significado"): [
                {"afirmacion": "A", "fuente_id": None, "dominio": "a.com"},
                {"afirmacion": "B", "fuente_id": "waite"},
            ],
        }
        cliente = ClienteFalsoConsenso([[0, 1]])
        res = consenso_kb.construir_consensos(cliente, celdas)
        self.assertEqual(len(res), 1)

    def test_dominios_distintos_sin_fuente_id_deben_sumar_mayoria(self):
        """Dos webs de dominios distintos (sin fuente_id) son fuentes
        independientes y deberian formar mayoria; hoy fuentes={None} y nunca
        la forman (subconteo de independencia)."""
        celdas = {
            ("tarot|loco", "significado"): [
                {"afirmacion": "A", "fuente_id": None, "dominio": "a.com"},
                {"afirmacion": "B", "fuente_id": None, "dominio": "b.com"},
            ],
        }
        cliente = ClienteFalsoConsenso([[0, 1]])
        res = consenso_kb.construir_consensos(cliente, celdas)
        self.assertEqual(len(res[0]["mayoritarias"]), 1)

    def test_truncamiento_max_por_celda_es_silencioso(self):
        """Confirmado: agrupar_celda recorta a MAX_POR_CELDA sin avisar;
        n_afirmaciones reporta todas pero las demas nunca se agrupan."""
        afirmaciones = [{"afirmacion": "afirmacion %d" % i}
                       for i in range(consenso_kb.MAX_POR_CELDA + 1)]
        capturado = []

        def fake_prompt(eid, faceta, textos):
            capturado.append(len(textos))
            return "prompt"

        n = consenso_kb.MAX_POR_CELDA
        cliente = ClienteFalsoConsenso([[i] for i in range(n)])
        with mock.patch.object(consenso_kb, "construir_prompt_consenso",
                             side_effect=fake_prompt):
            consenso_kb.agrupar_celda(cliente, "tarot|loco", "significado",
                                     afirmaciones)
        self.assertEqual(capturado, [consenso_kb.MAX_POR_CELDA])

    def test_truncamiento_max_por_celda_se_reporta(self):
        """Las afirmaciones que no se agrupan deben quedar contadas, no
        desaparecer en silencio del resultado de la celda."""
        n = consenso_kb.MAX_POR_CELDA
        celdas = {
            ("tarot|loco", "significado"): [
                {"afirmacion": "afirmacion %d" % i, "fuente_id": "s%d" % i}
                for i in range(n + 1)
            ],
        }
        cliente = ClienteFalsoConsenso([[i] for i in range(n)])
        with mock.patch.object(consenso_kb, "construir_prompt_consenso",
                               side_effect=lambda e, f, t: "prompt"):
            res = consenso_kb.construir_consensos(cliente, celdas)
        self.assertEqual(res[0]["n_afirmaciones"], n + 1)
        self.assertEqual(res[0]["n_no_agrupadas"], 1)

    def test_fallback_no_debe_contarse_como_procesada_definitiva(self):
        """El docstring promete reintentar las celdas fallback mas adelante,
        pero _cargar_celdas_procesadas las excluye por igual al reanudar."""
        tmp = tempfile.mkdtemp()
        try:
            ruta = os.path.join(tmp, "consenso.jsonl")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "entidad_id": "tarot|loco", "faceta": "significado",
                    "fallback": True, "mayoritarias": [],
                    "discrepancias": [], "unica_fuente": [],
                }, ensure_ascii=False) + "\n")
            procesadas = consenso_kb._cargar_celdas_procesadas(ruta)
            self.assertNotIn(("tarot|loco", "significado"), procesadas)
        finally:
            shutil.rmtree(tmp)


class TestKbV2Confianza(unittest.TestCase):
    """kb_v2: confianza y reanudacion."""

    def test_unica_fuente_repetida_no_debe_dar_media(self):
        """Dos entradas de la MISMA fuente no son respaldo cruzado; el
        criterio documentado exige fuentes DISTINTAS para subir a media."""
        celda = {
            "nucleo": [],
            "discrepancias": [],
            "unica_fuente": [{"fuente_id": "waite"}, {"fuente_id": "waite"}],
            "fallback": False,
        }
        self.assertEqual(kb_v2._confianza(celda), "baja")

    def _consenso_duplicado(self, tmp):
        ruta = os.path.join(tmp, "consenso.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "entidad_id": "aries|signo", "faceta": "general",
                "mayoritarias": [],
                "unica_fuente": [{"afirmacion": "vieja", "fuente_id": "x"}],
                "fallback": False,
            }, ensure_ascii=False) + "\n")
            f.write(json.dumps({
                "entidad_id": "aries|signo", "faceta": "general",
                "mayoritarias": [{"afirmacion": "nueva",
                                 "fuentes": ["a", "b"]}],
                "unica_fuente": [], "fallback": False,
            }, ensure_ascii=False) + "\n")
        kb_v1 = os.path.join(tmp, "kb_v1")
        os.makedirs(kb_v1)
        with open(os.path.join(kb_v1, "astrologia.json"), "w",
                 encoding="utf-8") as f:
            json.dump({"signos": []}, f)
        return ruta, kb_v1

    def test_celda_duplicada_gana_la_ultima_no_la_primera(self):
        """consenso_kb._cargar_consenso_existente es last-wins; kb_v2 es
        first-wins (vistas). Con una correccion appended en consenso.jsonl,
        kb_v2 conserva la version ANTIGUA (inconsistente)."""
        tmp = tempfile.mkdtemp()
        try:
            ruta, kb_v1 = self._consenso_duplicado(tmp)
            stats = kb_v2.construir_kb_v2(ruta, os.path.join(tmp, "out"),
                                         kb_v1_dir=kb_v1)
            self.assertEqual(stats["por_familia"]["astrologia"]["con_nucleo"], 1)
        finally:
            shutil.rmtree(tmp)

    def test_stats_deben_ser_serializables(self):
        """stats['v1_con_nucleo'] es un set: json.dumps(stats) revienta si
        alguien intenta serializar el resultado de construir_kb_v2."""
        tmp = tempfile.mkdtemp()
        try:
            ruta, kb_v1 = self._consenso_duplicado(tmp)
            stats = kb_v2.construir_kb_v2(ruta, os.path.join(tmp, "out"),
                                         kb_v1_dir=kb_v1)
            json.dumps(stats)
            self.assertIsInstance(stats["v1_con_nucleo"], list)
        finally:
            shutil.rmtree(tmp)

    def test_celda_duplicada_se_cuenta(self):
        """La sustitución last-wins no debe contar dos veces la celda."""
        tmp = tempfile.mkdtemp()
        try:
            ruta, kb_v1 = self._consenso_duplicado(tmp)
            stats = kb_v2.construir_kb_v2(ruta, os.path.join(tmp, "out"),
                                         kb_v1_dir=kb_v1)
            self.assertEqual(stats["celdas"], 1)
            self.assertEqual(stats["celdas_duplicadas"], 1)
        finally:
            shutil.rmtree(tmp)


class TestRecuperacionDescarga(unittest.TestCase):
    """recuperacion_descarga: orden de familias, bloqueos, plan."""

    def test_orden_familias_tolera_familia_none(self):
        """Una entrada del plan sin 'familia' y entidad no reconocida produce
        clave None; orden_familias hace sorted con None -> TypeError."""
        rd.orden_familias([None, "astrologia"])
        self.assertEqual(rd.orden_familias([None, "astrologia"]),
                         ["astrologia"])

    def test_orden_familias_pone_prioritarias_primero(self):
        self.assertEqual(
            rd.orden_familias([None, "tarot", "numerologia"]),
            ["numerologia", "tarot"],
        )

    def test_bloqueo_debe_cubrir_subdominios(self):
        """DOMINIOS_BLOQUEADOS coincide solo exacto: old.reddit.com y
        es.astro.com evaden el bloqueo declarado por cortesía."""
        candidatas = {"numerologia": [
            "https://old.reddit.com/r/tarot",
            "https://es.astro.com/x",
        ]}
        tareas = rd.construir_tareas(candidatas, {})
        self.assertEqual(tareas, [])

    def test_cargar_plan_debe_tolerar_linea_corrupta(self):
        """Una linea corrupta en el plan tumba todo el run; otros loaders de
        la tuberia toleran y cuentan. Debe saltarse la linea invalida."""
        tmp = tempfile.mkdtemp()
        try:
            ruta = os.path.join(tmp, "plan.jsonl")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write('{"entidad_id": "x"}\n')
                f.write('esto-no-es-json\n')
                f.write('{"entidad_id": "y"}\n')
            plan = rd.cargar_plan(ruta)
            self.assertEqual(len(plan), 2)
        finally:
            shutil.rmtree(tmp)


class TestEjecutorFase1(unittest.TestCase):
    """ejecutor_fase1: errores de payload dentro del pool."""

    def test_payload_sin_fecha_no_aborta_el_pool(self):
        """bloque='numerologia' con payload={} lanza KeyError('fecha') desde
        tarea_desde_job; uno() solo captura ValueError, asi que el hilo muere,
        la fila queda 'running' y f.result() aborta todo el run. Lo correcto:
        ValueError (o registro de error) para que se marque failed."""
        fila = {"id": 1, "bloque": "numerologia", "payload": "{}",
               "prompt": "Que me espera?"}
        with self.assertRaises(ValueError):
            ejecutor_fase1.procesar_una(fila, None, {})

    def test_payload_sin_nombre_no_aborta_el_pool(self):
        fila = {"id": 1, "bloque": "numerologia",
                "payload": '{"fecha": "1990-05-15"}',
                "prompt": "Que me espera?"}
        with self.assertRaises(ValueError) as cm:
            ejecutor_fase1.procesar_una(fila, None, {})
        self.assertIn("nombre", str(cm.exception))


class TestFase1Prompts(unittest.TestCase):
    """fase1_prompts: verificacion numerologica."""

    def test_etiqueta_con_ano_no_contradice_anio_personal(self):
        """Si la respuesta repite la etiqueta del prompt («Año personal
        2026: 5»), el patron captura 2026 != 5 y rechaza la lectura como
        contradictoria. El numero verificado es el valor, no el ano."""
        tarea = {
            "familia": "numerologia",
            "calculos": {"numerologia": {"anio_personal": 5}},
        }
        ok, motivos = fp.verificar_lectura(
            tarea, "Tu Año personal 2026: 5 trae cambios de ciclo.")
        self.assertTrue(ok, motivos)

    def test_etiqueta_sin_valor_no_es_contradiccion(self):
        """«Año personal 2026» a secas es la etiqueta, no una afirmación del
        valor; no debe compararse 2026 con el año personal calculado."""
        tarea = {
            "familia": "numerologia",
            "calculos": {"numerologia": {"anio_personal": 5}},
        }
        ok, motivos = fp.verificar_lectura(
            tarea, "Tu Año personal 2026 llega con cambios de ciclo.")
        self.assertTrue(ok, motivos)


class TestKbBaraja(unittest.TestCase):
    """build_kb_baraja: sinonimos y consistencia de los 40 naipes."""

    def test_naipes_deben_incluir_sinonimos(self):
        """construir() calcula la lista `sinonimos` (paje/jota, caballero,
        'N de palo', 'uno de palo') pero nunca la mete en el dict del naipe:
        la KB commitada no tiene el campo."""
        data = build_kb_baraja.construir()
        sota = [n for n in data["naipes"] if n["rango"] == "Sota"][0]
        self.assertIn("sinonimos", sota)
        self.assertIn("paje de Oros", sota["sinonimos"])
        self.assertIn("jota de Oros", sota["sinonimos"])
        self.assertIn("8 de Oros", sota["sinonimos"])

    def test_baraja_cuarenta_naipes_sana(self):
        """Confirmado sano: 40 naipes, nombres unicos, 10 por palo."""
        data = build_kb_baraja.construir()
        naipes = data["naipes"]
        self.assertEqual(len(naipes), 40)
        self.assertEqual(len({n["nombre"] for n in naipes}), 40)
        por_palo = {}
        for n in naipes:
            por_palo[n["palo"]] = por_palo.get(n["palo"], 0) + 1
        self.assertEqual(sorted(por_palo.values()), [10, 10, 10, 10])


class TestEnsayoYDescubrir(unittest.TestCase):
    """ensayo_extremo y descubrir_fuentes: tolerancia y bloqueos."""

    def test_leer_jsonl_tolera_linea_corrupta(self):
        tmp = tempfile.mkdtemp()
        try:
            ruta = os.path.join(tmp, "aceptadas.jsonl")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write('{"a": 1}\n')
                f.write('{"a": 2, "texto": "cortad\n')
                f.write('{"a": 3}\n')
            filas = ensayo_extremo._leer_jsonl(ruta)
            self.assertEqual([f["a"] for f in filas], [1, 3])
        finally:
            shutil.rmtree(tmp)

    def test_bloqueo_de_subdominios_en_descubrir(self):
        self.assertTrue(df.esta_bloqueado("old.reddit.com"))
        self.assertTrue(df.esta_bloqueado("es.astro.com"))
        self.assertFalse(df.esta_bloqueado("astro.com.ejemplo.net"))

    def test_construir_plan_descarta_subdominio_bloqueado(self):
        fuentes = [{
            "dominio": "old.reddit.com",
            "sitemap": "https://old.reddit.com/sitemap.xml",
            "patron": r"reddit\.com/",
            "familia": "tarot",
        }]
        llamadas = []
        por = df.construir_plan(
            fuentes, None, sleep=lambda s: None,
            robots_fn=lambda c, d, sleep=None: llamadas.append(d) or (lambda u: True),
        )
        self.assertEqual(por, {})
        self.assertEqual(llamadas, [])


class TestLlmClientFuga(unittest.TestCase):
    """llm_client: la clave de API no se filtra en errores."""

    def test_error_de_env_nombra_variable_sin_valor(self):
        """Confirmado sano: si falta la variable, el RuntimeError nombra la
        variable de entorno pero nunca un valor secreto."""
        os.environ.pop("T81_CLAVE_AUSENTE", None)
        spec = {"api_key_env": "T81_CLAVE_AUSENTE", "url": "http://x"}
        cliente = llm_client.LLMClient(endpoints=[spec])
        with self.assertRaises(RuntimeError) as cm:
            cliente._headers_de_endpoint(spec)
        self.assertIn("T81_CLAVE_AUSENTE", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
