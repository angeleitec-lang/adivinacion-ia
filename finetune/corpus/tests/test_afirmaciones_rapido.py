"""Tests de la pasada rápida de extracción de afirmaciones (T69)."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import afirmaciones_es as es  # noqa: E402
import afirmaciones_rapido as ar  # noqa: E402
import juez  # noqa: E402
from llm_client import LLMClient, RateLimitError  # noqa: E402

CUERPO_WEB = ("El dos de copas representa la unión y el afecto mutuo entre "
              "dos personas; habla de encuentros amorosos y de acuerdos del "
              "corazón.")

TEXTO_LIBRO_EN = ("The two of wands represents fire in its purest form. It "
                  "speaks of enterprise, bold ventures and the spark of "
                  "initiative.")

AFIRMACION_WEB = "El dos de copas representa el afecto mutuo entre dos personas."
AFIRMACION_LIBRO = "El dos de bastos expresa el fuego en su forma mas pura."
CITA_LIBRO = "fire in its purest form"


def _md(url, dominio, cuerpo):
    return "---\nurl: %s\ndominio: %s\n---\n%s" % (url, dominio, cuerpo)


def _seccion_web(url, cuerpo):
    return {"url": url, "texto": cuerpo}


def _seccion_libro(texto=TEXTO_LIBRO_EN, id_libro="librotest"):
    return {"seccion": 1, "titulo": "T", "texto": texto,
            "chars": len(texto), "id_libro": id_libro, "posicion": 1}


def _evidencia_web(url="https://example.com/dos-copas", cuerpo=CUERPO_WEB,
                   calidad=4, hash_seccion=None, entidad="tarot-copas-02"):
    if hash_seccion is None:
        hash_seccion = juez.hash_seccion(_seccion_web(url, cuerpo))
    return {"entidad_id": entidad, "faceta": "significado_general",
            "fuente_id": url, "dominio": "example.com", "idioma": "es",
            "periodo": "moderna", "calidad": calidad, "tipo": "web",
            "hash_seccion": hash_seccion}


def _evidencia_libro(texto=TEXTO_LIBRO_EN, id_libro="librotest", calidad=3,
                     hash_seccion=None):
    if hash_seccion is None:
        hash_seccion = juez.hash_seccion(_seccion_libro(texto, id_libro))
    return {"entidad_id": "naipe-bastos-02", "faceta": "significado_general",
            "fuente_id": id_libro, "dominio": id_libro, "idioma": "en",
            "periodo": "moderna", "calidad": calidad, "tipo": "libro",
            "hash_seccion": hash_seccion}


def _simulador(respuesta_web=None, respuesta_libros=None):
    respuesta_web = respuesta_web or '{"afirmaciones": []}'
    respuesta_libros = respuesta_libros or '{"afirmaciones": []}'

    def sim(sistema, usuario):
        if "extrae de libros" in sistema:
            return respuesta_libros
        return respuesta_web
    return sim


def _cliente_ok():
    respuesta_web = json.dumps({"afirmaciones": [AFIRMACION_WEB]},
                               ensure_ascii=False)
    respuesta_libros = json.dumps(
        {"afirmaciones": [{"afirmacion": AFIRMACION_LIBRO,
                           "cita_original": CITA_LIBRO}]},
        ensure_ascii=False)
    return LLMClient(simulado=_simulador(respuesta_web, respuesta_libros))


class SetupBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        self.web_dir = os.path.join(self.base, "web")
        dom = os.path.join(self.web_dir, "example.com")
        os.makedirs(dom)
        with open(os.path.join(dom, "dos-copas.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(_md("https://example.com/dos-copas", "example.com",
                         CUERPO_WEB))
        self.secciones_dir = os.path.join(self.base, "secciones")
        os.makedirs(self.secciones_dir)
        with open(os.path.join(self.secciones_dir, "librotest.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(_seccion_libro(), ensure_ascii=False) + "\n")
        self.ev_web = os.path.join(self.base, "evidencias_web.jsonl")
        self.ev_libros = os.path.join(self.base, "evidencias_libros.jsonl")
        self.proc_web = os.path.join(self.base, "procesados_web.jsonl")
        self.proc_libros = os.path.join(self.base, "procesados_libros.jsonl")
        self.cov = os.path.join(self.base, "cobertura_total_v2.json")
        self.out = os.path.join(self.base, "afirmaciones_rapido")
        for p in (self.proc_web, self.proc_libros):
            open(p, "w", encoding="utf-8").close()
        with open(self.cov, "w", encoding="utf-8") as fh:
            json.dump({"resumen": {}, "celdas": []}, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def escribir_evidencias(self, web=None, libros=None):
        with open(self.ev_web, "w", encoding="utf-8") as fh:
            for ev in (web or []):
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        with open(self.ev_libros, "w", encoding="utf-8") as fh:
            for ev in (libros or []):
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def run_main(self, extra=(), cliente=None):
        argv = [
            "--web-evidencias", self.ev_web,
            "--libros-evidencias", self.ev_libros,
            "--web-procesados", self.proc_web,
            "--libros-procesados", self.proc_libros,
            "--web-dir", self.web_dir,
            "--libros-secciones-dir", self.secciones_dir,
            "--cobertura", self.cov,
            "--out-root", self.out,
        ] + list(extra)
        return ar.main(argv, cliente=cliente)

    def lineas(self, rel):
        ruta = os.path.join(self.out, rel)
        if not os.path.exists(ruta):
            return []
        with open(ruta, encoding="utf-8") as fh:
            return [l for l in fh.read().splitlines() if l.strip()]


class SeleccionPendientes(unittest.TestCase):
    def test_excluye_procesadas_y_filtra_calidad(self):
        ev_web_ok = _evidencia_web(calidad=4)
        ev_web_baja = _evidencia_web(url="https://example.com/baja",
                                     cuerpo="otro texto diferente para hash",
                                     calidad=3)
        ev_web_proc = _evidencia_web(url="https://example.com/proc",
                                     cuerpo="texto para procesado ya hecho",
                                     calidad=5)
        ev_lib_ok = _evidencia_libro(calidad=3)
        ev_lib_baja = _evidencia_libro(id_libro="otro", calidad=2)
        procesados = {ar.clave(ev_web_proc)}
        pend = ar.seleccionar_pendientes(
            [ev_web_ok, ev_web_baja, ev_web_proc],
            [ev_lib_ok, ev_lib_baja],
            procesados, 4, 3)
        self.assertEqual([t for t, _ in pend], ["web", "libros"])
        self.assertEqual([ev["calidad"] for _, ev in pend], [4, 3])

    def test_filtra_min_calidad(self):
        evs = [_evidencia_web(calidad=5), _evidencia_web(calidad=3)]
        self.assertEqual(len(ar.filtrar_min_calidad(evs, 4)), 1)
        self.assertEqual(len(ar.filtrar_min_calidad(evs, 0)), 2)


class CargarProcesados(unittest.TestCase):
    def test_lee_claves(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "procesados.jsonl")
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"hash_seccion": "h", "entidad_id": "e",
                                     "faceta": "f", "estado": "ok"}) + "\n")
                fh.write("basura\n")
            claves = ar.cargar_procesados_claves(ruta)
            self.assertEqual(claves, {("h", "e", "f")})
            self.assertEqual(ar.cargar_procesados_claves(
                os.path.join(d, "noexiste")), set())


class PipelineCompleto(SetupBase):
    def test_procesa_web_y_libros_con_origen(self):
        self.escribir_evidencias(
            web=[_evidencia_web()],
            libros=[_evidencia_libro()])
        stats = self.run_main(extra=["--workers", "1"],
                              cliente=_cliente_ok())
        self.assertEqual(stats["procesadas"], 2)
        self.assertEqual(stats["sin_texto"], 0)
        self.assertEqual(stats["errores"], 0)
        self.assertGreaterEqual(stats["afirmaciones"], 2)

        web_af = self.lineas(os.path.join("web", "afirmaciones.jsonl"))
        self.assertEqual(len(web_af), 1)
        reg_web = json.loads(web_af[0])
        self.assertEqual(reg_web["origen"], ar.ORIGEN)
        self.assertEqual(reg_web["afirmacion"], AFIRMACION_WEB)

        libros_af = self.lineas(
            os.path.join("libros", "afirmaciones_libros.jsonl"))
        self.assertEqual(len(libros_af), 1)
        reg_lib = json.loads(libros_af[0])
        self.assertEqual(reg_lib["origen"], ar.ORIGEN)
        self.assertIn("cita_original", reg_lib)

        proc_web = self.lineas(os.path.join("web", "procesados.jsonl"))
        proc_lib = self.lineas(os.path.join("libros", "procesados.jsonl"))
        self.assertEqual(len(proc_web), 1)
        self.assertEqual(len(proc_lib), 1)
        self.assertEqual(json.loads(proc_web[0])["origen"], ar.ORIGEN)
        self.assertEqual(json.loads(proc_lib[0])["origen"], ar.ORIGEN)

        informe = os.path.join(self.out, "informe.md")
        self.assertTrue(os.path.exists(informe))
        with open(informe, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("mercury-3", texto)
        self.assertIn("afirmaciones", texto)


class Reanudacion(SetupBase):
    def test_segunda_pasada_no_reprocesa(self):
        self.escribir_evidencias(
            web=[_evidencia_web()],
            libros=[_evidencia_libro()])
        cliente = _cliente_ok()
        stats1 = self.run_main(extra=["--workers", "1"], cliente=cliente)
        self.assertEqual(stats1["procesadas"], 2)
        stats2 = self.run_main(extra=["--workers", "1"], cliente=cliente)
        self.assertEqual(stats2["procesadas"], 0)


class ParadaPorErrores(SetupBase):
    def _cliente_que_falla(self, excepcion):
        def sim(sistema, usuario):
            raise excepcion
        return LLMClient(simulado=sim)

    def _run_55_y_comprobar_aborte(self, cliente):
        ev = _evidencia_web()
        self.escribir_evidencias(web=[ev] * 55)
        stats = self.run_main(extra=["--workers", "1"], cliente=cliente)
        self.assertEqual(stats["procesadas"], ar.VENTANA_ERRORES)
        self.assertEqual(stats["errores"], ar.VENTANA_ERRORES)
        informe = os.path.join(self.out, "informe.md")
        with open(informe, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("La pasada se detuvo", texto)
        return stats

    def test_aborta_con_json_invalido(self):
        self._run_55_y_comprobar_aborte(
            self._cliente_que_falla(ValueError("no es json")))

    def test_aborta_con_429(self):
        self._run_55_y_comprobar_aborte(
            self._cliente_que_falla(RateLimitError("30")))


class CeldasQuePasanACinco(unittest.TestCase):
    def test_cruza_con_cobertura_v2(self):
        with tempfile.TemporaryDirectory() as d:
            ev_web = _evidencia_web()
            ev_web2 = _evidencia_web(
                url="https://otrodominio.com/x", cuerpo="texto distinto de "
                "otro dominio para hash", entidad="tarot-copas-02")
            ev_lib = _evidencia_libro()

            celdas = [
                {"entidad_id": "tarot-copas-02",
                 "faceta": "significado_general", "n_fuentes": 4},
                {"entidad_id": "naipe-bastos-02",
                 "faceta": "significado_general", "n_fuentes": 6},
                {"entidad_id": "tarot-mayor-01",
                 "faceta": "significado_general", "n_fuentes": 2},
            ]
            cov_path = os.path.join(d, "cobertura.json")
            with open(cov_path, "w", encoding="utf-8") as fh:
                json.dump({"celdas": celdas}, fh)
            celda_por_clave = {(c["entidad_id"], c["faceta"]): c
                               for c in celdas}

            fuentes_base = ar.construir_fuentes_base(
                [ev_web, ev_web2], [ev_lib], 4, 3,
                excluir={ar.clave(ev_web), ar.clave(ev_web2),
                         ar.clave(ev_lib)})
            exitosos = [("web", ev_web), ("web", ev_web2), ("libros", ev_lib)]
            pasan = ar.celdas_que_pasan_a_cinco(
                exitosos, cov_path, fuentes_base, celda_por_clave)
            self.assertEqual(len(pasan), 1)
            p = pasan[0]
            self.assertEqual(p["entidad_id"], "tarot-copas-02")
            self.assertEqual(p["n_antes"], 4)
            self.assertEqual(p["n_despues"], 5)

    def test_ya_completas_no_se_cuentan(self):
        with tempfile.TemporaryDirectory() as d:
            ev = _evidencia_web()
            celdas = [{"entidad_id": "tarot-copas-02",
                       "faceta": "significado_general", "n_fuentes": 7}]
            cov_path = os.path.join(d, "cobertura.json")
            with open(cov_path, "w", encoding="utf-8") as fh:
                json.dump({"celdas": celdas}, fh)
            celda_por_clave = {(c["entidad_id"], c["faceta"]): c
                               for c in celdas}
            fuentes_base = ar.construir_fuentes_base(
                [ev], [], 4, 3, excluir={ar.clave(ev)})
            pasan = ar.celdas_que_pasan_a_cinco(
                [("web", ev)], cov_path, fuentes_base, celda_por_clave)
            self.assertEqual(pasan, [])


class Estimacion(unittest.TestCase):
    def test_estima_tokens(self):
        pend = [("web", _evidencia_web()), ("libros", _evidencia_libro())]
        est = ar.estimar(pend)
        self.assertEqual(est["pendientes"], 2)
        self.assertEqual(est["tokens_estimados"], 2 * 1600)


class CeldasConFuentesNuevas(unittest.TestCase):
    def _reg(self, eid, faceta, fuente):
        return {"entidad_id": eid, "faceta": faceta, "fuente_id": fuente,
                "dominio": fuente}

    def test_gana_fuente_nueva(self):
        base = [self._reg("tarot-copas-02", "significado_general",
                          "https://a.com")]
        extra = [self._reg("tarot-copas-02", "significado_general",
                           "https://b.com")]
        res = ar.celdas_con_fuentes_nuevas(base, extra)
        self.assertIn(("tarot-copas-02", "significado_general"), res)
        self.assertEqual(res[("tarot-copas-02", "significado_general")]
                         ["fuentes_base"], 1)
        self.assertEqual(res[("tarot-copas-02", "significado_general")]
                         ["fuentes_nuevas"], 1)

    def test_misma_fuente_no_es_nueva(self):
        base = [self._reg("tarot-copas-02", "significado_general",
                          "https://a.com")]
        extra = [self._reg("tarot-copas-02", "significado_general",
                           "https://a.com")]
        self.assertFalse(ar.celdas_con_fuentes_nuevas(base, extra))

    def test_separa_por_celda(self):
        base = [self._reg("tarot-copas-02", "significado_general",
                          "https://a.com")]
        extra = [
            self._reg("tarot-copas-02", "significado_general",
                      "https://b.com"),
            self._reg("naipe-bastos-02", "significado_general",
                      "https://c.com"),
            self._reg("naipe-bastos-02", "significado_general",
                      "https://c.com"),
        ]
        res = ar.celdas_con_fuentes_nuevas(base, extra)
        self.assertEqual(len(res), 2)


class EscribirExtraFiltrado(unittest.TestCase):
    def _reg(self, eid, faceta, fuente):
        return {"entidad_id": eid, "faceta": faceta, "fuente_id": fuente,
                "dominio": fuente}

    def test_escribe_solo_celdas_ganadoras(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "extra.jsonl")
            extra = [
                self._reg("tarot-copas-02", "significado_general",
                          "https://b.com"),
                self._reg("naipe-bastos-02", "significado_general",
                          "https://c.com"),
            ]
            n = ar.escribir_extra_filtrado(
                ruta, extra, {("tarot-copas-02", "significado_general")})
            self.assertEqual(n, 1)
            with open(ruta, encoding="utf-8") as fh:
                lineas = [l for l in fh.read().splitlines() if l.strip()]
            self.assertEqual(len(lineas), 1)
            self.assertEqual(json.loads(lineas[0])["entidad_id"],
                             "tarot-copas-02")


if __name__ == "__main__":
    unittest.main()
