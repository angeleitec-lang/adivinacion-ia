"""Tests de web_fetch: cliente HTTP educado con robots.txt, reintentos, antibot y reanudación."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import http.server
import json
import tempfile
import threading
import time
import unittest

from web_fetch import Cliente, USER_AGENT


class _Servidor:
    """Servidor HTTP en un hilo con puerto libre y respuestas programables."""

    def __init__(self, respuestas, robots=None):
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.peticiones.append(self.path)
                if self.path == "/robots.txt":
                    estado, cuerpo, cabeceras = 200, (
                        outer.robots if outer.robots is not None
                        else "User-agent: *\nAllow: /\n").encode("utf-8"), {}
                else:
                    estado, cuerpo, cabeceras = outer.respuestas.get(
                        self.path, (404, b"no existe", {}))
                self.send_response(estado)
                for k, v in cabeceras.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *args):
                pass

        self.peticiones = []
        self.respuestas = respuestas
        self.robots = robots
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.puerto = self.srv.server_address[1]
        self.hilo = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.hilo.start()

    def url(self, ruta):
        return f"http://127.0.0.1:{self.puerto}{ruta}"

    def detener(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestRobots(unittest.TestCase):
    def test_url_prohibida_no_se_descarga(self):
        srv = _Servidor({}, robots="User-agent: *\nDisallow: /privado\n")
        try:
            c = Cliente(min_interval=0.0)
            r = c.get(srv.url("/privado/pagina"))
            self.assertEqual(r["estado"], "bloqueada_robots")
            self.assertNotIn("/privado/pagina", srv.peticiones)
        finally:
            srv.detener()

    def test_url_permitida_se_descarga(self):
        srv = _Servidor({"/publica": (200, "<html><body>hola</body></html>".encode(), {})})
        try:
            c = Cliente(min_interval=0.0)
            r = c.get(srv.url("/publica"))
            self.assertEqual(r["estado"], "ok")
            self.assertIn("hola", r["html"])
        finally:
            srv.detener()


class TestRateLimit(unittest.TestCase):
    def test_429_reintenta_y_luego_pausa_el_dominio(self):
        srv = _Servidor({"/x": (429, b"", {})})
        try:
            c = Cliente(min_interval=0.0, backoff=(0.01, 0.02, 0.03))
            r = c.get(srv.url("/x"))
            self.assertEqual(r["estado"], "pausado_429")
            self.assertEqual(r["intentos"], 4)
            n = len(srv.peticiones)
            r2 = c.get(srv.url("/y"))
            self.assertEqual(r2["estado"], "pausado_429")
            self.assertEqual(len(srv.peticiones), n)
        finally:
            srv.detener()


class TestAntibot(unittest.TestCase):
    def test_checking_browser_no_reintenta(self):
        srv = _Servidor({"/b": (403, b"<html>Checking your browser</html>", {})})
        try:
            c = Cliente(min_interval=0.0)
            r = c.get(srv.url("/b"))
            self.assertEqual(r["estado"], "bloqueado_antibot")
            self.assertEqual(r["intentos"], 1)
        finally:
            srv.detener()

    def test_cabecera_cf_en_503_es_antibot(self):
        srv = _Servidor({"/c": (503, b"", {"cf-mitigated": "challenge"})})
        try:
            c = Cliente(min_interval=0.0)
            r = c.get(srv.url("/c"))
            self.assertEqual(r["estado"], "bloqueado_antibot")
        finally:
            srv.detener()


class TestReanudacion(unittest.TestCase):
    def test_url_ok_no_se_repite(self):
        with tempfile.TemporaryDirectory() as td:
            man = os.path.join(td, "manifest.jsonl")
            srv = _Servidor({"/p": (200, "<html>ok</html>".encode(), {})})
            try:
                c1 = Cliente(min_interval=0.0, manifest_path=man)
                r1 = c1.get(srv.url("/p"))
                self.assertEqual(r1["estado"], "ok")
                c2 = Cliente(min_interval=0.0, manifest_path=man)
                r2 = c2.get(srv.url("/p"))
                self.assertEqual(r2["estado"], "ya_descargada")
                self.assertEqual(srv.peticiones.count("/p"), 1)
                with open(man, encoding="utf-8") as f:
                    fila = json.loads(f.readline())
                self.assertEqual(fila["url"], srv.url("/p"))
                self.assertEqual(fila["estado"], "ok")
            finally:
                srv.detener()


class TestCortesia(unittest.TestCase):
    def test_respeta_el_intervalo_por_dominio(self):
        srv = _Servidor({"/a": (200, b"<html>a</html>", {}),
                        "/b": (200, b"<html>b</html>", {})})
        try:
            c = Cliente(min_interval=0.3)
            t0 = time.monotonic()
            c.get(srv.url("/a"))
            c.get(srv.url("/b"))
            self.assertGreaterEqual(time.monotonic() - t0, 0.3)
        finally:
            srv.detener()

    def test_user_agent_honesto(self):
        self.assertIn("adivinacion-ia-corpus", USER_AGENT)


class TestCharset(unittest.TestCase):
    def test_decodifica_utf8_de_la_cabecera(self):
        cuerpo = "<html><body>tarot y arcanos: corazón</body></html>".encode("utf-8")
        srv = _Servidor({"/u": (200, cuerpo, {"Content-Type": "text/html; charset=utf-8"})})
        try:
            c = Cliente(min_interval=0.0)
            r = c.get(srv.url("/u"))
            self.assertEqual(r["estado"], "ok")
            self.assertIn("corazón", r["html"])
            self.assertEqual(r["bytes"], len(cuerpo))
        finally:
            srv.detener()


if __name__ == "__main__":
    unittest.main()
