"""Tests del revisor local HTML (T54)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import revisor_local

VEREDICTOS = {"correcto", "dudoso", "incorrecto"}


def _fila(rid, nivel="web", estrato=("tarot-mayor", "5"), **extra):
    fila = {
        "id": rid,
        "nivel": nivel,
        "origen": "web",
        "estrato": list(estrato),
        "entidad_id": "tarot-mayor-01",
        "sistema": None,
        "faceta": "amor",
        "calidad": 4,
    }
    fila.update(extra)
    return fila


def _datos(html):
    coincide = re.search(
        r'<script id="datos-revisor" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not coincide:
        raise AssertionError("no se encontró el bloque de datos")
    return json.loads(coincide.group(1))


def _js_app(html):
    coincide = re.search(r"<script>\n(.*?)\n</script>", html, re.S)
    if not coincide:
        raise AssertionError("no se encontró el script de la aplicación")
    return coincide.group(1)


def _js_export(html):
    coincide = re.search(
        r"/\* INICIO_EXPORT \*/(.*?)/\* FIN_EXPORT \*/", html, re.S
    )
    if not coincide:
        raise AssertionError("no se encontró el bloque de exportación")
    return coincide.group(1)


class TestGeneracion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _generar(self, filas, pre=(), textos=None, procedencias=None,
                 max_texto=6000):
        textos = textos or {}
        procedencias = procedencias or {}

        def resolver(fila):
            return (
                textos.get(fila["id"], "texto de %s" % fila["id"]),
                procedencias.get(fila["id"], "proc de %s" % fila["id"]),
            )

        fichas = revisor_local.construir_fichas(
            filas, pre, resolver=resolver, max_texto=max_texto
        )
        return fichas, revisor_local.generar_html(fichas)

    def test_html_autocontenido_con_datos(self):
        pre = [{
            "id": "a1",
            "nivel": "web",
            "banderas": [{"codigo": "texto_corto", "motivo": "muy corto",
                          "peso": 4}],
            "puntuacion": 4,
        }]
        fichas, html = self._generar(
            [_fila("a1"), _fila("a2", nivel="libros")], pre
        )
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("Revisor de muestras", html)
        self.assertIn("prefers-color-scheme", html)
        self.assertIn("localStorage", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        datos = _datos(html)
        self.assertEqual(datos["version"], 1)
        self.assertEqual([f["id"] for f in datos["fichas"]], ["a1", "a2"])
        a1 = datos["fichas"][0]
        self.assertEqual(a1["texto"], "texto de a1")
        self.assertEqual(a1["procedencia"], "proc de a1")
        self.assertEqual(a1["banderas"][0]["codigo"], "texto_corto")
        self.assertEqual(a1["puntuacion"], 4)
        self.assertEqual(a1["estrato"], "tarot-mayor · 5")
        a2 = datos["fichas"][1]
        self.assertEqual(a2["banderas"], [])
        self.assertEqual(a2["puntuacion"], 0)

    def test_escapa_script_comillas_y_separadores_unicode(self):
        peligro = (
            '</script><img src=x onerror=alert(1)> '
            '"comillas" & <b>negrita</b>\u2028\u2029<script>alert(2)</script>'
        )
        fichas, html = self._generar(
            [_fila("a1")], textos={"a1": peligro},
            procedencias={"a1": "</script><svg onload=alert(3)>"},
        )
        self.assertNotIn("<img", html)
        self.assertNotIn("<svg", html)
        self.assertNotIn("\u2028", html)
        self.assertNotIn("\u2029", html)
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertIn("\\u2028", html)
        self.assertIn("\\u2029", html)
        datos = _datos(html)
        self.assertEqual(datos["fichas"][0]["texto"], peligro)
        self.assertEqual(
            datos["fichas"][0]["procedencia"],
            "</script><svg onload=alert(3)>",
        )

    def test_ficha_sin_texto(self):
        fichas, html = self._generar(
            [_fila("a1")], textos={"a1": ""},
            procedencias={"a1": "sin fuente"},
        )
        self.assertEqual(fichas[0]["texto"], "")
        self.assertFalse(fichas[0]["truncado"])
        datos = _datos(html)
        self.assertEqual(datos["fichas"][0]["texto"], "")

    def test_ficha_sin_prerevision(self):
        fichas, _ = self._generar([_fila("a1")])
        self.assertEqual(fichas[0]["banderas"], [])
        self.assertEqual(fichas[0]["puntuacion"], 0)

    def test_prerevision_con_datos_raros(self):
        pre = [{
            "id": "a1",
            "banderas": [
                {"codigo": "x", "motivo": "<b>malo</b>", "peso": "7"},
                {"codigo": "y"},
                "bandera inválida",
            ],
            "puntuacion": 99,
        }]
        fichas, html = self._generar([_fila("a1")], pre)
        self.assertEqual(fichas[0]["puntuacion"], 10)
        self.assertEqual(len(fichas[0]["banderas"]), 2)
        self.assertEqual(fichas[0]["banderas"][0]["peso"], 7)
        self.assertNotIn("<b>malo</b>", html)

    def test_entrada_vacia(self):
        fichas, html = self._generar([], [])
        self.assertEqual(fichas, [])
        datos = _datos(html)
        self.assertEqual(datos["fichas"], [])
        self.assertEqual(datos["total"], 0)
        self.assertIn("0 fichas", html)

    def test_texto_largo_se_recorta_y_marca(self):
        largo = "a" * 100
        fichas, _ = self._generar(
            [_fila("a1")], textos={"a1": largo}, max_texto=40
        )
        self.assertEqual(fichas[0]["texto"], "a" * 40)
        self.assertTrue(fichas[0]["truncado"])
        self.assertEqual(fichas[0]["largo_original"], 100)

    def test_ids_duplicados_no_revientan(self):
        fichas, _ = self._generar([_fila("a1"), _fila("a1")])
        self.assertEqual(len(fichas), 1)

    def test_fila_sin_id_se_omite(self):
        fichas, _ = self._generar([{"nivel": "web"}, _fila("a1")])
        self.assertEqual([f["id"] for f in fichas], ["a1"])


class TestExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.fichas = [
            {"id": "a1", "nivel": "web"},
            {"id": "a2", "nivel": "libros"},
            {"id": "a3", "nivel": "web"},
            {"id": "a4", "nivel": "lecturas"},
        ]
        self.veredictos = {"a1": "correcto", "a2": "incorrecto",
                           "a3": "dudoso"}
        self.notas = {"a1": "bien", "a2": "", "a4": "no revisada"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_esquema_python(self):
        lineas = revisor_local.construir_lineas_export(
            self.fichas, self.veredictos, self.notas
        )
        self.assertEqual([ln["id"] for ln in lineas], ["a1", "a2", "a3"])
        for linea in lineas:
            self.assertEqual(
                set(linea), {"id", "veredicto", "nota", "nivel"}
            )
            self.assertIn(linea["veredicto"], VEREDICTOS)
            self.assertIsInstance(linea["nota"], str)
        self.assertEqual(lineas[0]["nota"], "bien")
        self.assertEqual(lineas[1]["nota"], "")
        texto = revisor_local.texto_export(lineas)
        self.assertTrue(texto.endswith("\n"))
        self.assertEqual(len(texto.strip().splitlines()), 3)
        for fila in texto.strip().splitlines():
            self.assertEqual(
                set(json.loads(fila)),
                {"id", "veredicto", "nota", "nivel"},
            )

    def test_veredictos_invalidos_se_ignoran(self):
        lineas = revisor_local.construir_lineas_export(
            self.fichas, {"a1": "regular", "a2": "correcto"},
            {"a2": "ok"},
        )
        self.assertEqual([ln["id"] for ln in lineas], ["a2"])

    def test_js_export_coincide_con_python(self):
        if not shutil.which("node"):
            self.skipTest("node no instalado")
        fichas, html = self._construir_html()
        bloque = _js_export(html)
        programa = (
            bloque
            + "\nconst fichas = %s;\nconst veredictos = %s;\n"
            "const notas = %s;\n"
            "console.log(JSON.stringify(construirLineasExport("
            "fichas, veredictos, notas)));\n"
        ) % (
            json.dumps(fichas, ensure_ascii=False),
            json.dumps(self.veredictos, ensure_ascii=False),
            json.dumps(self.notas, ensure_ascii=False),
        )
        resultado = subprocess.run(
            ["node", "-e", programa], capture_output=True, text=True,
            timeout=30,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        js = json.loads(resultado.stdout)
        py = revisor_local.construir_lineas_export(
            fichas, self.veredictos, self.notas
        )
        self.assertEqual(js, py)

    def _construir_html(self):
        filas = [_fila(f["id"], nivel=f["nivel"]) for f in self.fichas]
        fichas = revisor_local.construir_fichas(
            filas, [], resolver=lambda f: ("texto", "proc")
        )
        return fichas, revisor_local.generar_html(fichas)


class TestJS(unittest.TestCase):
    def test_sintaxis_js_si_hay_node(self):
        if not shutil.which("node"):
            self.skipTest("node no instalado")
        fichas = revisor_local.construir_fichas(
            [_fila("a1")], [], resolver=lambda f: ("texto", "proc")
        )
        html = revisor_local.generar_html(fichas)
        js = _js_app(html)
        ruta = os.path.join(tempfile.mkdtemp(), "app.js")
        try:
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(js)
            resultado = subprocess.run(
                ["node", "--check", ruta], capture_output=True, text=True,
                timeout=30,
            )
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
        finally:
            shutil.rmtree(os.path.dirname(ruta), ignore_errors=True)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir(self, nombre, filas):
        ruta = os.path.join(self.dir, nombre)
        with open(ruta, "w", encoding="utf-8") as fh:
            for fila in filas:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        return ruta

    def test_cli_genera_html(self):
        muestras = self._escribir(
            "muestras.jsonl",
            [_fila("a1"), _fila("a2", nivel="libros")],
        )
        pre = self._escribir("prerevision.jsonl", [{
            "id": "a1", "banderas": [], "puntuacion": 0,
        }])
        salida = os.path.join(self.dir, "revisor.html")
        rc = revisor_local.main([
            "--muestras", muestras,
            "--prerevision", pre,
            "--out", salida,
            "--base", os.path.join(self.dir, "base-vacia"),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(salida))
        with open(salida, encoding="utf-8") as fh:
            datos = _datos(fh.read())
        self.assertEqual(len(datos["fichas"]), 2)
        self.assertEqual(datos["fichas"][0]["procedencia"],
                         "procedencia desconocida")

    def test_cli_entrada_vacia(self):
        muestras = self._escribir("muestras.jsonl", [])
        pre = self._escribir("prerevision.jsonl", [])
        salida = os.path.join(self.dir, "revisor.html")
        rc = revisor_local.main([
            "--muestras", muestras,
            "--prerevision", pre,
            "--out", salida,
            "--base", os.path.join(self.dir, "base-vacia"),
        ])
        self.assertEqual(rc, 0)
        with open(salida, encoding="utf-8") as fh:
            datos = _datos(fh.read())
        self.assertEqual(datos["total"], 0)


if __name__ == "__main__":
    unittest.main()
