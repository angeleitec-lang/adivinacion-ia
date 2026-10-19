#!/usr/bin/env python3
"""Tests del pipeline web T25: config de sitios en español y orquestador offline."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from urllib.parse import urlparse

RUTA_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "knowledge", "sitios_indice_es.json"
)

CAMPOS_REQUERIDOS = ("nombre", "indice", "regex", "dominio", "familia", "prioridad")
FAMILIAS_PERMITIDAS = {"baraja_espanola", "tarot", "astrologia", "numerologia"}
PRIORIDADES = {"alta", "media", "baja"}


def _dominio_normal(netloc: str) -> str:
    return netloc[4:] if netloc.startswith("www.") else netloc


class ConfigSitiosEspanolTests(unittest.TestCase):
    """T25.1: sitios_indice_es.json cumple los requisitos del track."""

    @classmethod
    def setUpClass(cls):
        with open(RUTA_CONFIG, encoding="utf-8") as fh:
            cls.config = json.load(fh)
        cls.sitios = cls.config["sitios"]

    def test_minimo_diez_sitios(self):
        self.assertGreaterEqual(len(self.sitios), 10)

    def test_minimo_seis_baraja_espanola(self):
        baraja = [s for s in self.sitios if s["familia"] == "baraja_espanola"]
        self.assertGreaterEqual(len(baraja), 6)

    def test_campos_requeridos(self):
        for sitio in self.sitios:
            for campo in CAMPOS_REQUERIDOS:
                self.assertIn(campo, sitio, f"{sitio.get('nombre')}: falta {campo}")
                self.assertIsInstance(sitio[campo], (str, list))

    def test_familias_y_prioridades_validas(self):
        for sitio in self.sitios:
            self.assertIn(sitio["familia"], FAMILIAS_PERMITIDAS, sitio["nombre"])
            self.assertIn(sitio["prioridad"], PRIORIDADES, sitio["nombre"])

    def test_sin_youtube_ni_libro_ni_biblioteca(self):
        for sitio in self.sitios:
            self.assertNotIn("youtube", sitio["dominio"])
            self.assertNotIn("youtube", sitio["nombre"])
            self.assertNotIn(sitio["familia"], {"libro", "biblioteca"})
            indices = sitio["indice"] if isinstance(sitio["indice"], list) else [sitio["indice"]]
            for url in indices:
                self.assertNotIn("youtube.", url)

    def test_regex_compila(self):
        for sitio in self.sitios:
            try:
                re.compile(sitio["regex"])
            except re.error as exc:
                self.fail(f"{sitio['nombre']}: regex no compila: {exc}")

    def test_indice_str_o_lista_no_vacia(self):
        for sitio in self.sitios:
            idx = sitio["indice"]
            self.assertIsInstance(idx, (str, list), sitio["nombre"])
            urls = idx if isinstance(idx, list) else [idx]
            self.assertGreater(len(urls), 0, sitio["nombre"])
            for url in urls:
                self.assertIsInstance(url, str)
                self.assertTrue(url.startswith("http"), f"{sitio['nombre']}: {url}")

    def test_dominio_coherente_con_indice(self):
        for sitio in self.sitios:
            idx = sitio["indice"]
            urls = idx if isinstance(idx, list) else [idx]
            esperado = _dominio_normal(sitio["dominio"])
            for url in urls:
                netloc = _dominio_normal(urlparse(url).netloc)
                self.assertEqual(
                    netloc,
                    esperado,
                    f"{sitio['nombre']}: indice {url} no pertenece a {esperado}",
                )

    def test_nombres_unicos(self):
        nombres = [s["nombre"] for s in self.sitios]
        self.assertEqual(len(nombres), len(set(nombres)))


class UtilidadesPipelineTests(unittest.TestCase):
    """T25.2: utilidades del orquestador."""

    def test_normalizar_url_quita_query_y_fragmento(self):
        from web_pipeline import normalizar_url

        self.assertEqual(
            normalizar_url("https://x.com/a/b?query=1#frag"), "https://x.com/a/b"
        )
        self.assertEqual(normalizar_url("https://x.com/a/b"), "https://x.com/a/b")

    def test_hilo_publico(self):
        from web_pipeline import es_hilo_publico

        self.assertTrue(es_hilo_publico("https://foro.net/tema-algo"))
        self.assertFalse(es_hilo_publico("https://foro.net/user/5"))
        self.assertFalse(es_hilo_publico("https://foro.net/perfil/ana"))
        self.assertFalse(es_hilo_publico("https://foro.net/search?q=x"))
        self.assertFalse(es_hilo_publico("https://foro.net/busqueda"))
        self.assertFalse(es_hilo_publico("https://foro.net/login"))
        self.assertFalse(es_hilo_publico("https://foro.net/admin/panel"))

    def test_intervalo_por_tipo_sitio(self):
        from web_pipeline import intervalo_para_sitio

        self.assertEqual(intervalo_para_sitio({"tipo": "foro"}), 2.5)
        self.assertEqual(intervalo_para_sitio({"tipo": "blog"}), 1.2)
        self.assertEqual(intervalo_para_sitio({}), 1.2)

    def test_slug_desde_url(self):
        from web_pipeline import slug_desde_url

        slug = slug_desde_url("https://x.com/baraja-espanola/as-de-copas/")
        self.assertTrue(re.fullmatch(r"[a-z0-9_-]+", slug))
        self.assertIn("as-de-copas", slug)


def _html_largo():
    return "<html><head><title>Página de prueba</title></head><body>" + ("contenido util " * 200) + "</body></html>"


class ClienteFalso:
    """Cliente HTTP simulado: respuestas por URL, registra llamadas e intervalos."""

    def __init__(self, respuestas, min_interval=1.2):
        self.respuestas = respuestas
        self.min_interval = min_interval
        self.llamadas = []

    def get(self, url):
        self.llamadas.append(url)
        return self.respuestas.get(
            url, {"estado": "error", "status": 404, "html": None, "bytes": 0}
        )


def _respuesta_ok(html):
    return {"estado": "ok", "status": 200, "html": html, "bytes": len(html)}


class OrquestadorTests(unittest.TestCase):
    """T25.2: descubrir → descargar → extraer → manifest → informe, todo offline."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.work_dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

        self.sitio_blog = {
            "nombre": "blogdemo.com",
            "tipo": "blog",
            "indice": "https://blogdemo.com/index.html",
            "regex": "/post-",
            "dominio": "blogdemo.com",
            "familia": "baraja_espanola",
            "prioridad": "alta",
        }
        self.indice_html = (
            "<html><body>"
            '<a href="/post-uno.html">Uno</a>'
            '<a href="/post-dos.html?utm=1">Dos</a>'
            "</body></html>"
        )

    def _escribir_config(self, sitios):
        import json
        import os

        ruta = os.path.join(self.work_dir, "config.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump({"sitios": sitios}, fh, ensure_ascii=False)
        return ruta

    def _ejecutar(self, ruta_config, cliente, **kw):
        from web_pipeline import ejecutar

        fabrica = lambda mi: cliente  # noqa: E731
        return ejecutar(
            ruta_config, self.work_dir, fabrica_clientes=fabrica, **kw
        )

    def test_flujo_completo_manifest_y_informe(self):
        import os

        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok(_html_largo()),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        resumen = self._ejecutar(ruta, cliente)
        manifest = os.path.join(self.work_dir, "manifest.jsonl")
        self.assertTrue(os.path.exists(manifest))
        with open(manifest, encoding="utf-8") as fh:
            regs = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(regs), 2)
        for reg in regs:
            self.assertEqual(reg["estado"], "ok")
            self.assertEqual(reg["dominio"], "blogdemo.com")
            self.assertEqual(reg["sitio"], "blogdemo.com")
            self.assertEqual(reg["familia"], "baraja_espanola")
            self.assertTrue(reg["archivo"])
        mds = [
            f
            for _, _, files in os.walk(self.work_dir)
            for f in files
            if f.endswith(".md") and "informe" not in f
        ]
        self.assertEqual(len(mds), 2)
        self.assertTrue(os.path.exists(os.path.join(self.work_dir, "informe.md")))
        self.assertEqual(resumen["total_ok"], 2)

    def test_relanzar_no_repite_descargas(self):
        import os

        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok(_html_largo()),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        self._ejecutar(ruta, cliente)
        cliente.llamadas.clear()
        self._ejecutar(ruta, cliente)
        contenido = [u for u in cliente.llamadas if "post-" in u]
        self.assertEqual(contenido, [])
        with open(os.path.join(self.work_dir, "manifest.jsonl"), encoding="utf-8") as fh:
            regs = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(regs), 2)

    def test_sitio_fallido_no_aborta(self):
        import os

        otro = dict(self.sitio_blog)
        otro["nombre"] = "otrodemo.com"
        otro["dominio"] = "otrodemo.com"
        otro["indice"] = "https://otrodemo.com/index.html"
        ruta = self._escribir_config([self.sitio_blog, otro])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok(_html_largo()),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        resumen = self._ejecutar(ruta, cliente)
        self.assertEqual(resumen["total_ok"], 2)
        self.assertIn("otrodemo.com", resumen["sitios_con_error"] + resumen.get("sitios_sin_paginas", []))

    def test_429_se_registra_y_continua(self):
        import os

        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": {
                    "estado": "pausado_429",
                    "status": 429,
                    "html": None,
                    "bytes": 0,
                },
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        self._ejecutar(ruta, cliente)
        with open(os.path.join(self.work_dir, "manifest.jsonl"), encoding="utf-8") as fh:
            regs = {json.loads(l)["url"]: json.loads(l)["estado"] for l in fh if l.strip()}
        self.assertEqual(regs["https://blogdemo.com/post-uno.html"], "pausado_429")
        self.assertEqual(regs["https://blogdemo.com/post-dos.html"], "ok")

    def test_pagina_corta_se_registra_como_corta(self):
        import os

        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok("<html><body>corto</body></html>"),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        self._ejecutar(ruta, cliente)
        with open(os.path.join(self.work_dir, "manifest.jsonl"), encoding="utf-8") as fh:
            regs = {json.loads(l)["url"]: json.loads(l)["estado"] for l in fh if l.strip()}
        self.assertEqual(regs["https://blogdemo.com/post-uno.html"], "cortas")

    def test_foro_tope_40_hilos(self):
        from web_pipeline import procesar_sitio

        foro = {
            "nombre": "forodemo.net",
            "tipo": "foro",
            "indice": "https://forodemo.net/foro-1",
            "regex": "/tema-",
            "dominio": "forodemo.net",
            "familia": "baraja_espanola",
            "prioridad": "alta",
        }
        enlaces = "".join(f'<a href="/tema-{i}">t{i}</a>' for i in range(60))
        cliente = ClienteFalso(
            {"https://forodemo.net/foro-1": _respuesta_ok("<html><body>" + enlaces + "</body></html>")}
        )
        for i in range(60):
            cliente.respuestas[f"https://forodemo.net/tema-{i}"] = _respuesta_ok(_html_largo())
        regs = procesar_sitio(foro, cliente, self.work_dir, limite=50, procesadas=set())
        self.assertEqual(len(regs), 40)

    def test_foro_solo_hilos_publicos(self):
        from web_pipeline import procesar_sitio

        foro = {
            "nombre": "forodemo.net",
            "tipo": "foro",
            "indice": "https://forodemo.net/foro-1",
            "regex": "(?:tema|user)",
            "dominio": "forodemo.net",
            "familia": "baraja_espanola",
            "prioridad": "alta",
        }
        html = (
            "<html><body>"
            '<a href="/tema-publico">p</a>'
            '<a href="/user/5">perfil</a>'
            "</body></html>"
        )
        cliente = ClienteFalso(
            {
                "https://forodemo.net/foro-1": _respuesta_ok(html),
                "https://forodemo.net/tema-publico": _respuesta_ok(_html_largo()),
            }
        )
        regs = procesar_sitio(foro, cliente, self.work_dir, limite=50, procesadas=set())
        urls = [r["url"] for r in regs]
        self.assertIn("https://forodemo.net/tema-publico", urls)
        self.assertNotIn("https://forodemo.net/user/5", urls)

    def test_dry_run_no_descarga(self):
        import os

        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok(_html_largo()),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        resumen = self._ejecutar(ruta, cliente, dry_run=True)
        contenido = [u for u in cliente.llamadas if "post-" in u]
        self.assertEqual(contenido, [])
        self.assertEqual(resumen["total_descubiertas"], 2)
        self.assertFalse(os.path.exists(os.path.join(self.work_dir, "manifest.jsonl")))

    def test_solo_filtra_sitios(self):
        ruta = self._escribir_config([self.sitio_blog])
        cliente = ClienteFalso(
            {
                "https://blogdemo.com/index.html": _respuesta_ok(self.indice_html),
                "https://blogdemo.com/post-uno.html": _respuesta_ok(_html_largo()),
                "https://blogdemo.com/post-dos.html": _respuesta_ok(_html_largo()),
            }
        )
        resumen = self._ejecutar(ruta, cliente, solo=["inexistente.com"])
        self.assertEqual(resumen["total_descubiertas"], 0)
        self.assertEqual(cliente.llamadas, [])


if __name__ == "__main__":
    unittest.main()
