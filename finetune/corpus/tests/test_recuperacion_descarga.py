#!/usr/bin/env python3
"""Tests de la recuperación dirigida 2.ª iteración (T64), todo offline.

Cliente HTTP simulado: saltado por URL ya descargada, robots prohibido, 404,
reanudación, tope por dominio, duplicado por hash, idempotencia y orden de
prioridad de familias.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recuperacion_descarga as rd
from web_extraer import extraer


def _html_largo():
    return ("<html><head><title>Página de prueba</title></head><body>"
            + ("contenido util sobre naipes y numeros " * 120)
            + "</body></html>")


def _ok(html):
    return {"estado": "ok", "status": 200, "html": html, "bytes": len(html)}


class ClienteFalso:
    """Cliente simulado: respuestas por URL y registro de llamadas."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def get(self, url):
        self.llamadas.append(url)
        return self.respuestas.get(
            url, {"estado": "error", "status": 404, "html": None, "bytes": 0})


class BaseT64(unittest.TestCase):
    """Escenario común: plan, config de índices y cliente simulado."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_dir = os.path.join(self.tmp.name, "web_recup2")
        self.old_web = os.path.join(self.tmp.name, "web")
        os.makedirs(self.old_web)

        self.pagina = _html_largo()
        self.respuestas = {
            "https://barajademo.com/indice": {
                "estado": "ok", "status": 200, "bytes": 10,
                "html": '<html><body>'
                        '<a href="/naipe-as">As</a>'
                        '<a href="/naipe-rey">Rey</a>'
                        '<a href="/naipe-sota">Sota</a>'
                        '</body></html>'},
            "https://numerodemo.com/indice": {
                "estado": "ok", "status": 200, "bytes": 10,
                "html": '<html><body>'
                        '<a href="/numero-1">Uno</a>'
                        '<a href="/numero-2">Dos</a>'
                        '</body></html>'},
            "https://barajademo.com/naipe-as": _ok(self.pagina),
            "https://barajademo.com/naipe-rey": _ok(self.pagina),
            "https://barajademo.com/naipe-sota": _ok(self.pagina),
            "https://numerodemo.com/numero-1": _ok(self.pagina),
            "https://numerodemo.com/numero-2": _ok(self.pagina),
        }
        self.config = {"sitios": [
            {"nombre": "barajademo.com", "tipo": "blog",
             "indice": "https://barajademo.com/indice",
             "regex": "/naipe-", "dominio": "barajademo.com",
             "familia": "baraja_espanola", "prioridad": "alta"},
            {"nombre": "numerodemo.com", "tipo": "blog",
             "indice": "https://numerodemo.com/indice",
             "regex": "/numero-", "dominio": "numerodemo.com",
             "familia": "numerologia", "prioridad": "alta"},
        ]}
        self.plan = [
            {"entidad_id": "11|camino_de_vida", "familia": "numerologia",
             "nombre": "Camino de vida 11",
             "urls_candidatas": [{"url": "https://numerodemo.com/indice"}]},
            {"entidad_id": "naipe-oros-01", "familia": "baraja_espanola",
             "nombre": "As de Oros",
             "urls_candidatas": [{"url": "https://barajademo.com/indice"}]},
        ]
        self.ruta_plan = self._jsonl("plan.jsonl", self.plan)
        self.ruta_config = self._json("config.json", self.config)
        self.manifest_previo = os.path.join(self.tmp.name, "manifest_previo.jsonl")

    def _json(self, nombre, obj):
        ruta = os.path.join(self.tmp.name, nombre)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        return ruta

    def _jsonl(self, nombre, filas):
        ruta = os.path.join(self.tmp.name, nombre)
        with open(ruta, "w", encoding="utf-8") as fh:
            for f in filas:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        return ruta

    def _ejecutar(self, cliente, **kw):
        kw.setdefault("tope_por_dominio", 40)
        kw.setdefault("max_total", 150)
        return rd.descargar_todo(
            self.ruta_plan, self.ruta_config, self.out_dir,
            self.manifest_previo, self.old_web,
            fabrica_clientes=lambda intervalo: cliente, **kw)

    def _registros(self):
        ruta = os.path.join(self.out_dir, "manifest.jsonl")
        if not os.path.exists(ruta):
            return []
        with open(ruta, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def _md_files(self):
        found = []
        for raiz, _d, archivos in os.walk(self.out_dir):
            found += [os.path.join(raiz, a) for a in archivos
                      if a.endswith(".md")]
        return found


class CandidatasTests(BaseT64):
    def test_agrupacion_y_orden_de_aparicion(self):
        candidatas = rd.candidatas_por_familia(self.plan)
        self.assertEqual(candidatas["baraja_espanola"],
                         ["https://barajademo.com/indice"])
        self.assertEqual(candidatas["numerologia"],
                         ["https://numerodemo.com/indice"])

    def test_prioridad_de_familias(self):
        orden = rd.orden_familias(["numerologia", "astrologia",
                                  "baraja_espanola"])
        self.assertEqual(orden[:2], ["baraja_espanola", "numerologia"])
        self.assertEqual(orden[2:], ["astrologia"])

    def test_dominio_sin_config_se_descarta(self):
        candidatas = {"baraja_espanola": ["https://desconocido.com/x/"]}
        sitios = rd.construir_sitios(candidatas, rd.config_por_dominio(self.config))
        self.assertEqual(sitios, [])

    def test_dominio_bloqueado_no_se_descubre(self):
        config = {"sitios": [
            {"nombre": "astro.com", "tipo": "guia",
             "indice": "https://astro.com/horoscopo",
             "regex": "/horoscopo", "dominio": "astro.com",
             "familia": "astrologia", "prioridad": "alta"}]}
        candidatas = {"astrologia": ["https://astro.com/horoscopo"]}
        sitios = rd.construir_sitios(candidatas, rd.config_por_dominio(config))
        self.assertEqual(sitios, [])


class FiltrosPreviosTests(BaseT64):
    def test_cargar_urls_previas_solo_estados_terminales(self):
        with open(self.manifest_previo, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"url": "https://x.com/a?utm=1",
                                "estado": "ok"}) + "\n")
            fh.write(json.dumps({"url": "https://x.com/b",
                                "estado": "cortas"}) + "\n")
            fh.write(json.dumps({"url": "https://x.com/c",
                                "estado": "error"}) + "\n")
        urls = rd.cargar_urls_previas(self.manifest_previo)
        self.assertEqual(urls, {"https://x.com/a", "https://x.com/b"})

    def test_cargar_hashes_previos_del_front_matter(self):
        os.makedirs(os.path.join(self.old_web, "barajademo.com"))
        with open(os.path.join(self.old_web, "barajademo.com", "p.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("---\nurl: \"x\"\nsha256: " + "a" * 64 + "\n---\ncuerpo\n")
        with open(os.path.join(self.old_web, "barajademo.com", "q.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("---\nurl: \"y\"\n---\ncuerpo\n")
        hashes = rd.cargar_hashes_previos(self.old_web)
        self.assertEqual(hashes, {"a" * 64})


class DescargaTests(BaseT64):
    def test_url_ya_descargada_se_salta(self):
        with open(self.manifest_previo, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"url": "https://barajademo.com/naipe-as",
                                "estado": "ok"}) + "\n")
        cliente = ClienteFalso(self.respuestas)
        resumen = self._ejecutar(cliente)
        self.assertNotIn("https://barajademo.com/naipe-as", cliente.llamadas)
        self.assertEqual(resumen["omitidas_ya"], 1)
        urls_reg = [r["url"] for r in self._registros()]
        self.assertNotIn("https://barajademo.com/naipe-as", urls_reg)

    def test_robots_bloqueada(self):
        self.respuestas["https://barajademo.com/naipe-rey"] = {
            "estado": "bloqueada_robots", "status": None, "html": None,
            "bytes": 0}
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        regs = {r["url"]: r for r in self._registros()}
        self.assertEqual(regs["https://barajademo.com/naipe-rey"]["estado"],
                         "bloqueada_robots")
        self.assertIsNone(regs["https://barajademo.com/naipe-rey"]["archivo"])

    def test_404(self):
        del self.respuestas["https://numerodemo.com/numero-2"]
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        regs = {r["url"]: r for r in self._registros()}
        self.assertEqual(regs["https://numerodemo.com/numero-2"]["estado"],
                         "error")

    def test_tope_por_dominio(self):
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente, tope_por_dominio=2)
        baraja = [r for r in self._registros()
                  if r["dominio"] == "barajademo.com"]
        self.assertEqual(len(baraja), 2)

    def test_reanudacion_no_repite_lo_terminado(self):
        c1 = ClienteFalso(self.respuestas)
        r1 = self._ejecutar(c1, max_total=1)
        self.assertEqual(r1["intentos"], 1)
        primera = self._registros()[0]["url"]

        c2 = ClienteFalso(self.respuestas)
        r2 = self._ejecutar(c2, max_total=1)
        self.assertEqual(r2["intentos"], 1)
        segunda = self._registros()[1]["url"]
        self.assertNotEqual(primera, segunda)
        self.assertNotIn(primera, c2.llamadas)

    def test_idempotencia_segunda_pasada_no_baja_nada(self):
        c1 = ClienteFalso(self.respuestas)
        r1 = self._ejecutar(c1)
        self.assertEqual(r1["intentos"], 5)
        archivos1 = sorted(self._md_files())
        lineas1 = len(self._registros())

        c2 = ClienteFalso(self.respuestas)
        r2 = self._ejecutar(c2)
        self.assertEqual(r2["intentos"], 0)
        self.assertEqual(sorted(self._md_files()), archivos1)
        self.assertEqual(len(self._registros()), lineas1)

    def test_duplicada_por_hash_contra_web_previa(self):
        extraccion = extraer(self.pagina, "https://barajademo.com/x")
        self.assertIsNotNone(extraccion)
        hash_pagina = extraccion["hash"]
        os.makedirs(os.path.join(self.old_web, "previo.com"))
        with open(os.path.join(self.old_web, "previo.com", "copia.md"),
                  "w", encoding="utf-8") as fh:
            fh.write("---\nurl: \"x\"\nsha256: " + hash_pagina + "\n---\nbody\n")
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        regs = {r["url"]: r for r in self._registros()}
        self.assertEqual(regs["https://barajademo.com/naipe-as"]["estado"],
                         "duplicada_hash")
        self.assertEqual(regs["https://barajademo.com/naipe-as"]["hash"],
                         hash_pagina)
        self.assertIsNone(regs["https://barajademo.com/naipe-as"]["archivo"])

    def test_duplicada_por_hash_dentro_de_la_tanda(self):
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        regs = {r["url"]: r for r in self._registros()}
        self.assertEqual(regs["https://barajademo.com/naipe-as"]["estado"], "ok")
        self.assertEqual(regs["https://barajademo.com/naipe-rey"]["estado"],
                         "duplicada_hash")

    def test_prioridad_baraja_antes_que_numerologia(self):
        cliente = ClienteFalso(self.respuestas)
        resumen = self._ejecutar(cliente, max_total=2)
        dominios = [r["dominio"] for r in self._registros()]
        self.assertEqual(dominios, ["barajademo.com", "barajademo.com"])
        self.assertEqual(resumen["intentos"], 2)


class ForoTests(BaseT64):
    def test_rutas_no_publicas_de_foro_se_descartan(self):
        self.config["sitios"].append(
            {"nombre": "forodemo.net", "tipo": "foro",
             "indice": "https://forodemo.net/foro",
             "regex": "/(tema|user)-", "dominio": "forodemo.net",
             "familia": "baraja_espanola", "prioridad": "media"})
        self.plan.append(
            {"entidad_id": "naipe-copas-02", "familia": "baraja_espanola",
             "nombre": "Dos de Copas",
             "urls_candidatas": [{"url": "https://forodemo.net/foro"}]})
        self._json("config.json", self.config)
        self._jsonl("plan.jsonl", self.plan)
        self.respuestas["https://forodemo.net/foro"] = {
            "estado": "ok", "status": 200, "bytes": 10,
            "html": '<html><body>'
                    '<a href="/tema-combinaciones">Hilo</a>'
                    '<a href="/user/5">Perfil</a>'
                    '</body></html>'}
        self.respuestas["https://forodemo.net/tema-combinaciones"] = _ok(self.pagina)
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        dominios = {r["dominio"] for r in self._registros()}
        self.assertIn("forodemo.net", dominios)
        urls = [r["url"] for r in self._registros()]
        self.assertNotIn("https://forodemo.net/user/5", urls)


class DirectaTests(BaseT64):
    """Candidatas de página directa: dominios sin config de índice."""

    def _anadir_directa(self, url, html=None):
        self.plan.append(
            {"entidad_id": "tarot-el-loco", "familia": "tarot",
             "nombre": "El Loco",
             "urls_candidatas": [{"url": url}]})
        self._jsonl("plan.jsonl", self.plan)
        if html is None:
            unico = ("<html><head><title>Ficha " + url +
                    "</title></head><body>"
                    + ("significado unico de la carta " + url + " ") * 120
                    + "</body></html>")
            html = _ok(unico)
        self.respuestas[url] = html

    def test_candidata_directa_se_descarga(self):
        self._anadir_directa("https://fichatarot.com/carta/el-loco")
        cliente = ClienteFalso(self.respuestas)
        resumen = self._ejecutar(cliente)
        regs = {r["url"]: r for r in self._registros()}
        self.assertIn("https://fichatarot.com/carta/el-loco", regs)
        self.assertEqual(regs["https://fichatarot.com/carta/el-loco"]["estado"],
                         "ok")
        self.assertEqual(resumen["por_dominio"]["tarot|fichatarot.com"]["ok"], 1)
        self.assertTrue(any("fichatarot.com" in f for f in self._md_files()))

    def test_directa_ya_descargada_se_salta(self):
        self._anadir_directa("https://fichatarot.com/carta/el-loco")
        with open(self.manifest_previo, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"url": "https://fichatarot.com/carta/el-loco",
                 "estado": "ok"}) + "\n")
        cliente = ClienteFalso(self.respuestas)
        resumen = self._ejecutar(cliente)
        self.assertNotIn("https://fichatarot.com/carta/el-loco", cliente.llamadas)
        self.assertGreaterEqual(resumen["omitidas_ya"], 1)

    def test_directa_respeta_tope_por_dominio(self):
        self._anadir_directa("https://fichatarot.com/carta/el-loco")
        self._anadir_directa("https://fichatarot.com/carta/la-luna")
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente, tope_por_dominio=1)
        fichas = [r for r in self._registros()
                  if r["dominio"] == "fichatarot.com"]
        self.assertEqual(len(fichas), 1)

    def test_indice_antes_que_directa_en_la_familia(self):
        self._anadir_directa("https://fichatarot.com/carta/el-loco")
        # baraja (prioritaria) tiene índice (barajademo) y, en otra entrada,
        # una directa de tarot no: el índice de baraja se atiende primero.
        self.plan.append(
            {"entidad_id": "naipe-copas-03", "familia": "baraja_espanola",
             "nombre": "Tres de Copas",
             "urls_candidatas": [{"url": "https://fichatarot.com/carta/la-luna"}]})
        self._jsonl("plan.jsonl", self.plan)
        self.respuestas["https://fichatarot.com/carta/la-luna"] = _ok(self.pagina)
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente, max_total=1)
        self.assertEqual(self._registros()[0]["dominio"], "barajademo.com")

    def test_directa_bloqueada_no_se_baja(self):
        self._anadir_directa("https://reddit.com/r/tarot")
        cliente = ClienteFalso(self.respuestas)
        self._ejecutar(cliente)
        self.assertNotIn("https://reddit.com/r/tarot", cliente.llamadas)
        dominios = {r["dominio"] for r in self._registros()}
        self.assertNotIn("reddit.com", dominios)


class InformeTests(BaseT64):
    def test_informe_dom_flojo_y_potencial(self):
        cliente = ClienteFalso(self.respuestas)
        resumen = self._ejecutar(cliente, max_total=1)
        matriz = {"celdas": [
            {"entidad_id": "naipe-oros-01", "faceta": "amor",
             "completa": False},
            {"entidad_id": "naipe-oros-02", "faceta": "amor",
             "completa": True},
            {"entidad_id": "11|camino_de_vida", "faceta": "amor",
             "completa": False},
        ]}
        informe = rd.generar_informe(resumen, matriz)
        self.assertIn("barajademo.com", informe)
        self.assertIn("menos de 3 páginas útiles", informe)
        self.assertIn("Potencial de mejora por familia", informe)
        bajo = rd.celdas_bajo_minimo_por_familia(matriz)
        self.assertEqual(bajo["baraja_espanola"], 1)
        self.assertEqual(bajo["numerologia"], 1)


if __name__ == "__main__":
    unittest.main()
