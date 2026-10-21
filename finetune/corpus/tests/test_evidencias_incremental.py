"""Pruebas de evidencias_incremental: ejecución reanudable del tramo
calidad → juez → append de evidencias para dominios web pendientes."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import evidencias_incremental as ei
import juez


class ClienteStub:
    """Cliente que imita al simulado del juez y cuenta sus llamadas."""

    def __init__(self):
        self.llamadas = 0

    def chat(self, sistema, usuario):
        self.llamadas += 1
        entidad = None
        for linea in usuario.splitlines():
            if linea.startswith("- ") and "(" in linea:
                entidad = linea[2:linea.index("(")].strip()
                break
        respuesta = {"tipo": "conocimiento", "calidad": 4, "idioma": "es",
                     "entidades": ([{"entidad_id": entidad,
                                     "facetas": ["significado_general"]}]
                                    if entidad else [])}
        return "```json\n%s\n```" % json.dumps(respuesta, ensure_ascii=False)


def _relleno(semilla, n=30):
    frases = []
    for i in range(n):
        frases.append(
            "Observacion %s-%d sobre el naipe, su contexto historico y su "
            "lectura en la consulta diaria del tarotista." % (semilla, i))
    return " ".join(frases)


def _pagina(dominio, titulo, extra="", entidad="naipe-bastos-01"):
    return (
        "---\n"
        "dominio: %s\n"
        "titulo: %s\n"
        "entidad_id: %s\n"
        "fuente: web\n"
        "---\n\n"
        "%s\n" % (dominio, titulo, entidad, _relleno(titulo) + extra))


class BaseTemporal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.web_dir = os.path.join(self.tmp, "web")
        self.out_dir = os.path.join(self.tmp, "evidencias_web")
        os.makedirs(self.web_dir)
        os.makedirs(self.out_dir)
        self.ruta_ev = os.path.join(self.out_dir, "evidencias.jsonl")
        self.ruta_juicios = os.path.join(self.out_dir, "juicios.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escribir_pagina(self, dominio, nombre, contenido):
        d = os.path.join(self.web_dir, dominio)
        os.makedirs(d, exist_ok=True)
        ruta = os.path.join(d, nombre + ".md")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(contenido)
        return ruta

    def hash_de_pagina(self, ruta):
        return juez.hash_seccion(juez._secciones_de_fichero(ruta)[0])


class TestDeteccionPendientes(BaseTemporal):
    def test_dominios_pendientes_detectados(self):
        ruta_a = self.escribir_pagina("dominioa", "p1",
                                     _pagina("dominioa", "As de Bastos uno"))
        self.escribir_pagina("dominiob", "p1",
                            _pagina("dominiob", "As de Bastos dos"))
        with open(self.ruta_juicios, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"hash": self.hash_de_pagina(ruta_a)}) + "\n")
        pendientes = ei.dominios_pendientes(self.web_dir, self.ruta_ev)
        self.assertEqual(pendientes, ["dominiob"])

    def test_filtro_de_dominios(self):
        self.escribir_pagina("dominioa", "p1",
                            _pagina("dominioa", "As de Bastos uno"))
        self.escribir_pagina("dominiob", "p1",
                            _pagina("dominiob", "As de Bastos dos"))
        pendientes = ei.dominios_pendientes(self.web_dir, self.ruta_ev,
                                           filtro={"dominioa"})
        self.assertEqual(pendientes, ["dominioa"])

    def test_pagina_ya_en_evidencias_no_es_pendiente(self):
        ruta = self.escribir_pagina("dominioa", "p1",
                                   _pagina("dominioa", "As de Bastos uno"))
        with open(self.ruta_ev, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"hash_seccion": self.hash_de_pagina(ruta),
                                "entidad_id": "naipe-bastos-01",
                                "faceta": "significado_general"}) + "\n")
        pendientes = ei.dominios_pendientes(self.web_dir, self.ruta_ev)
        self.assertEqual(pendientes, [])


class TestEjecucionIncremento(BaseTemporal):
    def test_apende_evidencias_de_pagina_apt(self):
        self.escribir_pagina("dominioa", "p1",
                            _pagina("dominioa", "As de Bastos uno"))
        cliente = ClienteStub()
        stats = ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        self.assertEqual(cliente.llamadas, 1)
        with open(self.ruta_ev, encoding="utf-8") as fh:
            lineas = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(lineas), 1)
        self.assertEqual(lineas[0]["dominio"], "dominioa")
        self.assertEqual(lineas[0]["entidad_id"], "naipe-bastos-01")
        self.assertEqual(lineas[0]["tipo"], "web")
        self.assertGreaterEqual(lineas[0]["calidad"], 3)

    def test_idempotencia_segunda_pasada(self):
        self.escribir_pagina("dominioa", "p1",
                            _pagina("dominioa", "As de Bastos uno"))
        cliente = ClienteStub()
        ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        with open(self.ruta_ev, encoding="utf-8") as fh:
            n1 = sum(1 for l in fh if l.strip())
        stats2 = ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        with open(self.ruta_ev, encoding="utf-8") as fh:
            n2 = sum(1 for l in fh if l.strip())
        self.assertEqual(cliente.llamadas, 1)
        self.assertEqual(n1, n2)
        self.assertEqual(stats2["secciones"], 0)

    def test_backup_una_sola_vez(self):
        original = json.dumps({"entidad_id": "vieja", "hash_seccion": "h-vieja"})
        with open(self.ruta_ev, "w", encoding="utf-8") as fh:
            fh.write(original + "\n")
        self.escribir_pagina("dominioa", "p1",
                            _pagina("dominioa", "As de Bastos uno"))
        cliente = ClienteStub()
        ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        sufijo = date.today().strftime("%Y%m%d")
        ruta_bak = self.ruta_ev + ".bak-" + sufijo
        self.assertTrue(os.path.exists(ruta_bak))
        with open(ruta_bak, encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), original)
        ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        backups = [n for n in os.listdir(self.out_dir)
                   if n.startswith("evidencias.jsonl.bak-")]
        self.assertEqual(len(backups), 1)
        with open(ruta_bak, encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), original)

    def test_entrada_vacia_sin_backup(self):
        cliente = ClienteStub()
        stats = ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        self.assertEqual(cliente.llamadas, 0)
        self.assertEqual(stats["secciones"], 0)
        self.assertFalse(os.path.exists(self.ruta_ev + ".bak-"
                                       + date.today().strftime("%Y%m%d")))

    def test_ruido_navegacion_descartado(self):
        ruido = ("\nAviso legal\nPolítica de privacidad\n"
                 "Todos los derechos reservados\n")
        self.escribir_pagina("dominioruido", "p1",
                            _pagina("dominioruido", "Página con ruido",
                                   extra=ruido))
        cliente = ClienteStub()
        stats = ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente)
        self.assertEqual(cliente.llamadas, 0)
        self.assertEqual(stats["descartadas"], 1)
        self.assertEqual(stats["secciones"], 0)
        self.assertFalse(os.path.exists(self.ruta_ev))

    def test_cli_timeout_pasa_al_cliente(self):
        from unittest import mock
        with mock.patch.object(ei.llm_client, "LLMClient") as fab:
            ei.main(["--web-dir", self.web_dir, "--evidencias", self.ruta_ev,
                    "--dominios", "x", "--timeout", "240"])
        self.assertEqual(fab.call_args.kwargs.get("timeout"), 240.0)

    def test_dry_run_no_escribe_ni_llama(self):
        self.escribir_pagina("dominioa", "p1",
                            _pagina("dominioa", "As de Bastos uno"))
        cliente = ClienteStub()
        stats = ei.ejecutar_incremento(self.web_dir, self.ruta_ev, cliente,
                                      dry_run=True)
        self.assertEqual(cliente.llamadas, 0)
        self.assertEqual(stats["secciones"], 1)
        self.assertFalse(os.path.exists(self.ruta_ev))
        self.assertFalse(os.path.exists(self.ruta_juicios))


if __name__ == "__main__":
    unittest.main()
