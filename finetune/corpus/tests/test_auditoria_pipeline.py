"""Casos adversos de la auditoría T51: tubería de adquisición y generación.

Entradas reales o casi reales; cada caso que falló en la auditoría queda aquí
como test de regresión.
"""
import json
import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_dataset
import cobertura
import generate_tasks
import juez
import llm_client
import merge_final
import web_calidad
import web_extraer
import web_pipeline

CANDIDATOS = [{"entidad_id": "tarot-mayor-01", "nombre": "El Loco",
               "familia": "tarot"}]


def _fila(human, gpt):
    return {"conversations": [
        {"from": "system", "value": "sistema"},
        {"from": "human", "value": human},
        {"from": "gpt", "value": gpt},
    ]}


class TestWebPipelineAdversa(unittest.TestCase):

    def test_manifest_con_linea_lista_no_aborta(self):
        with tempfile.TemporaryDirectory() as tmp:
            man = Path(tmp) / "manifest.jsonl"
            man.write_text(
                '{"url": "https://x.com/a", "estado": "ok"}\n'
                "[1, 2]\n"
                '{"url": "https://x.com/b", "estado": "ok"}\n',
                encoding="utf-8")
            procesadas = web_pipeline._cargar_procesadas(man)
        self.assertEqual(procesadas, {"https://x.com/a", "https://x.com/b"})

    def test_urls_distintas_con_mismo_slug_no_se_pisan(self):
        html_a = ("<html><body><article><h1>Tarot</h1><p>"
                  "La guía del tarot explica el simbolismo de cada arcano "
                  "y su lectura tradicional en la tirada. " * 10 +
                  "</p></article></body></html>")
        html_b = ("<html><body><article><h1>Baraja</h1><p>"
                  "La guía de la baraja española describe los palos, las "
                  "figuras y el valor de cada naipe en la lectura. " * 10 +
                  "</p></article></body></html>")

        class Cliente:
            def get(self, url):
                return {"estado": "ok", "bytes": 100,
                        "html": html_a if "/tarot/" in url else html_b}

        sitio = {"nombre": "x", "dominio": "x.com", "familia": "tarot"}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(web_pipeline, "seguir_indice",
                                  return_value=["https://x.com/tarot/guia",
                                                "https://x.com/baraja/guia"]):
            regs = web_pipeline.procesar_sitio(
                sitio, Cliente(), tmp, limite=10, procesadas=set(),
                min_chars=50)
            archivos = [Path(r["archivo"]) for r in regs]
            self.assertEqual(len(set(archivos)), 2)
            textos = [p.read_text(encoding="utf-8") for p in archivos]
            self.assertNotEqual(textos[0], textos[1])

    def test_normalizar_url_quita_query_y_fragmento(self):
        self.assertEqual(
            web_pipeline.normalizar_url("https://x.com/a?utm=1#frag"),
            "https://x.com/a")


class TestWebExtraerAdversa(unittest.TestCase):

    def test_pagina_solo_navegacion_no_pasa_el_umbral(self):
        nav = "\n".join(
            ["[%s](https://x.com/%d)" % ("Sección de la web " * 3, i)
             for i in range(20)])
        with mock.patch.object(web_extraer.trafilatura, "extract",
                               return_value=nav):
            self.assertIsNone(
                web_extraer.extraer("<html></html>", "https://x.com/a",
                                    min_chars=500))

    def test_chars_refleja_el_texto_tras_limpiar(self):
        prosa = ("La carta del Loco representa el inicio del camino y la "
                 "confianza en lo desconocido. " * 5)
        ruido = "\n".join(["[Suscríbete](https://x.com/n)"] * 30)
        md = prosa + "\n" + ruido
        with mock.patch.object(web_extraer.trafilatura, "extract",
                               return_value=md):
            res = web_extraer.extraer("<html></html>", "https://x.com/a",
                                      min_chars=100)
        self.assertIsNotNone(res)
        self.assertEqual(res["chars"], len(res["texto_md"]))
        self.assertLess(res["chars"], len(md))

    def test_html_vacio_y_truncado_no_rompen(self):
        self.assertIsNone(web_extraer.extraer("", "https://x.com/a"))
        self.assertIsNone(web_extraer.extraer(
            "<html><body><p>corto", "https://x.com/a", min_chars=1000))


class TestWebCalidadAdversa(unittest.TestCase):

    def _pagina(self, tmp, titulo, url="https://x.com/a"):
        fm = {
            "url": url, "dominio": "x.com", "titulo": titulo,
            "entidad_id": None, "faceta": None, "familia": "tarot",
            "idioma": "es", "fecha": None, "sha256": None,
            "licencia_hint": None,
        }
        contenido = ("---\n" + web_extraer._yaml_dumper(fm) + "\n---\n\n"
                     "Cuerpo de la página sobre el tarot y sus arcanos. " * 3)
        ruta = Path(tmp) / "x.com" / "a.md"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    def test_bom_no_pierde_el_front_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._pagina(tmp, "El Loco")
            ruta.write_text("\ufeff" + ruta.read_text(encoding="utf-8"),
                            encoding="utf-8")
            pag = web_calidad.leer_pagina(ruta)
        self.assertEqual(pag["titulo"], "El Loco")
        self.assertEqual(pag["front_matter"].get("url"), "https://x.com/a")
        self.assertFalse(pag["cuerpo"].startswith("---"))

    def test_titulo_con_comillas_ida_y_vuelta(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = self._pagina(tmp, '¿Qué es "El Loco" del tarot?')
            pag = web_calidad.leer_pagina(ruta)
        self.assertEqual(pag["titulo"], '¿Qué es "El Loco" del tarot?')


class TestCoberturaAdversa(unittest.TestCase):

    def _ev(self, fuente, dominio, tipo="web", periodo="moderna", idioma="es",
            calidad=4, url=None):
        ev = {"entidad_id": "tarot-mayor-01", "faceta": "significado_general",
              "fuente_id": fuente, "dominio": dominio, "periodo": periodo,
              "idioma": idioma, "calidad": calidad, "tipo": tipo}
        if url:
            ev["url"] = url
        return ev

    def _celda(self, evidencias):
        res = cobertura.calcular_cobertura(evidencias, calidad_min=3,
                                          minimo_fuentes=1,
                                          minimo_clasicas=0,
                                          minimo_modernas=0, minimo_es=0)
        celda = next(c for c in res["celdas"]
                     if c["entidad_id"] == "tarot-mayor-01"
                     and c["faceta"] == "significado_general")
        return celda["n_fuentes"]

    def test_www_y_sin_www_cuentan_una_sola_fuente(self):
        evs = [self._ev("https://www.biddytarot.com/a", "www.biddytarot.com"),
               self._ev("https://biddytarot.com/b", "biddytarot.com")]
        self.assertEqual(self._celda(evs), 1)

    def test_mayusculas_y_puerto_no_duplican_la_fuente(self):
        evs = [self._ev("https://BiddyTarot.com/a", "BiddyTarot.com"),
               self._ev("https://biddytarot.com:443/b", "biddytarot.com:443")]
        self.assertEqual(self._celda(evs), 1)

    def test_dominio_ausente_se_deriva_de_la_url(self):
        evs = [self._ev("https://biddytarot.com/a", ""),
               self._ev("https://biddytarot.com/b", "")]
        self.assertEqual(self._celda(evs), 1)

    def test_calidad_none_o_cadena_no_rompe(self):
        evs = [self._ev("a", "a.com", calidad=None),
               self._ev("b", "b.com", calidad="4"),
               self._ev("c", "c.com", calidad=4)]
        self.assertGreaterEqual(self._celda(evs), 1)


class TestJuezAdversa(unittest.TestCase):

    def test_json_valido_despues_de_llaves_invalidas(self):
        texto = ('Aviso {no es json} y ahora el juicio: '
                 '{"tipo": "conocimiento", "calidad": 4, "entidades": []}')
        datos = juez.parsear_respuesta(texto, CANDIDATOS)
        self.assertEqual(datos["calidad"], 4)

    def test_calidad_como_cadena_numerica_se_rechaza(self):
        # T67 (B2): antes se aceptaba y convertía; ahora «calidad» debe ser
        # numérica entera 1-5, no cadena.
        texto = ('{"tipo": "conocimiento", "calidad": "4", '
                 '"entidades": []}')
        with self.assertRaises(ValueError):
            juez.parsear_respuesta(texto, CANDIDATOS)

    def test_idioma_en_mayusculas(self):
        texto = ('{"tipo": "conocimiento", "calidad": 3, "idioma": "ES", '
                 '"entidades": []}')
        self.assertEqual(juez.parsear_respuesta(texto, CANDIDATOS)["idioma"],
                         "es")

    def test_calidad_infinita_es_value_error(self):
        texto = ('{"tipo": "conocimiento", "calidad": 1e999, '
                 '"entidades": []}')
        with self.assertRaises(ValueError):
            juez.parsear_respuesta(texto, CANDIDATOS)

    def test_leer_jsonl_ignora_lineas_no_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "juicios.jsonl"
            ruta.write_text('{"hash": "a"}\n[1]\n"texto"\n{"hash": "b"}\n',
                            encoding="utf-8")
            regs = juez._leer_jsonl(str(ruta))
        self.assertEqual(regs, [{"hash": "a"}, {"hash": "b"}])

    def test_fuente_web_deriva_dominio_de_la_url(self):
        fuente = juez.fuente_de_seccion(
            {"url": "https://www.biddytarot.com/tarot", "idioma": "es"})
        self.assertEqual(fuente["dominio"], "www.biddytarot.com")


class TestLLMClientAdversa(unittest.TestCase):

    def test_json_valido_despues_de_llaves_invalidas(self):
        cliente = llm_client.LLMClient(simulado=lambda s, u: "")
        self.assertEqual(cliente._extraer_json('ruido {mal} {"a": 1}'),
                         {"a": 1})

    def test_respuesta_sin_choices_no_rompe_chat_json(self):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": []}

        cliente = llm_client.LLMClient(endpoints=["http://127.0.0.1:9/v1"])
        with mock.patch.object(llm_client.requests, "post", return_value=Resp()), \
                mock.patch.object(llm_client.time, "sleep"):
            with self.assertRaises(ValueError):
                cliente.chat_json("s", "u", lambda d: None, intentos=2)

    def test_timeout_agota_reintentos(self):
        cliente = llm_client.LLMClient(endpoints=["http://127.0.0.1:9/v1"])
        with mock.patch.object(
                llm_client.requests, "post",
                side_effect=llm_client.requests.Timeout("timeout")) as post, \
                mock.patch.object(llm_client.time, "sleep"):
            with self.assertRaises(llm_client.requests.Timeout):
                cliente.chat("s", "u", max_reintentos=2)
        self.assertEqual(post.call_count, 3)


class TestGenerateTasksT35(unittest.TestCase):

    def _proyeccion(self, fecha, hora):
        return generate_tasks.datos_proyeccion(fecha, hora, 40.4, -3.7,
                                               "Europe/Madrid")

    def test_29_febrero_ancla_en_28(self):
        trans, rs = self._proyeccion("2000-02-29", "12:00")
        self.assertTrue(rs["instante_ut"].startswith("2026-02-28"))
        self.assertTrue(generate_tasks.fmt_revolucion_solar(rs))

    def test_31_diciembre_y_1_enero(self):
        for fecha in ("1990-12-31", "1990-01-01"):
            trans, rs = self._proyeccion(fecha, "23:30")
            self.assertEqual(trans["fecha_transito"], "2026-10-15")
            self.assertIn("Revolución solar del año", 
                          generate_tasks.fmt_revolucion_solar(rs))

    def test_fecha_sin_ceros_a_la_izquierda(self):
        trans, rs = self._proyeccion("1990-2-3", "9:05")
        self.assertTrue(generate_tasks.fmt_transitos(trans))

    def test_revolucion_solar_sin_sol_da_error_claro(self):
        rs = self._proyeccion("1990-03-21", "18:00")[1]
        rs["carta"]["planetas"] = [p for p in rs["carta"]["planetas"]
                                  if p["nombre"] != "Sol"]
        with self.assertRaises(ValueError):
            generate_tasks.fmt_revolucion_solar(rs)


class TestBuildDatasetAdversa(unittest.TestCase):

    def test_manifest_con_pages_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            man = Path(tmp) / "manifest.json"
            man.write_text(json.dumps({"pages": [
                {"url": "https://x.com/a", "estado": "bloqueado"},
                {"url": "https://x.com/b", "estado": "ok"},
            ]}), encoding="utf-8")
            bloqueadas = build_dataset.load_blocked(man)
        self.assertEqual(bloqueadas, {"x.com/a.md"})

    def test_manifest_con_entrada_no_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            man = Path(tmp) / "manifest.json"
            man.write_text(json.dumps([
                "texto suelto",
                {"url": "https://x.com/a", "estado": "bloqueado"},
            ]), encoding="utf-8")
            self.assertEqual(build_dataset.load_blocked(man), {"x.com/a.md"})

    def test_dedupe_nfc_y_nfd_es_el_mismo_par(self):
        nfc = unicodedata.normalize("NFC", "corazón")
        nfd = unicodedata.normalize("NFD", "corazón")
        pares = [_fila("¿Qué significa " + x + "?", "cuerpo " + x)
                 for x in (nfc, nfd)]
        self.assertEqual(len(build_dataset.dedupe(pares)), 1)

    def test_dedupe_fila_sin_campos_no_rompe(self):
        pares = [{"conversations": [{"from": "human", "value": "a"}]},
                 _fila("¿Qué significa el Loco?", "El Loco inicia el camino.")]
        self.assertEqual(len(build_dataset.dedupe(pares)), 1)


class TestMergeFinalAdversa(unittest.TestCase):

    def test_load_jsonl_ignora_lineas_no_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "rows.jsonl"
            ruta.write_text('{"a": 1}\n[1]\n"texto"\n', encoding="utf-8")
            self.assertEqual(merge_final.load_jsonl(ruta), [{"a": 1}])

    def test_norm_iguala_nfc_y_nfd(self):
        nfc = unicodedata.normalize("NFC", "corazón del tarot")
        nfd = unicodedata.normalize("NFD", "corazón del tarot")
        self.assertEqual(merge_final._norm(nfc), merge_final._norm(nfd))

    def test_duplicado_exacto_nfc_contra_nfd(self):
        human = "Explícame el significado del Loco en el tarot."
        answer = unicodedata.normalize("NFC", "El Loco es el arcano del inicio.")
        sintetica = unicodedata.normalize("NFD", answer)
        real = [_fila(human, answer)]
        synth = [_fila(human, sintetica)]
        res = merge_final.fusionar(real, [], synth, [{"block": "proyeccion"}],
                                   {"seed": 1})
        self.assertEqual(res["report"]["synth_kept"], 0)


if __name__ == "__main__":
    unittest.main()
