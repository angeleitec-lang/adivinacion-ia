# Tests de libros_pipeline: orquestador reanudable de la fase 0 de libros.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import io
import json
import contextlib
import tempfile
import unittest
import urllib.error
from unittest import mock

import cobertura
import juez
import libros_pipeline


def _parrafo(relleno, veces):
    lineas = ["EL LOCO " + relleno]
    lineas += [relleno] * veces
    return "\n".join(lineas)


RELLENO_EN = ("the fool of the sun and the moon is a journey of the soul "
              "and he walks the long road with the light of the stars and "
              "the wheel turns once more for every one who dares to see")
RELLENO_ES = ("el loco del sol y de la luna es un viaje del alma y el anda "
              "con la luz de las estrellas y la rueda gira una vez mas para "
              "cada uno que se atreve a mirar y asi es como vemos el camino")

CRUDO_EN = "\n\n".join([_parrafo(RELLENO_EN, 15)] * 4)
CRUDO_ES = "\n\n".join([_parrafo(RELLENO_ES, 15)] * 4)


def _obtener_que_falla(code, mensaje="limitado"):
    """_obtener de recambio que lanza HTTPError con ese código."""
    def _obtener(url, timeout=120):
        raise urllib.error.HTTPError(url, code, mensaje, None, None)
    return _obtener


def _escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(texto)


def _leer_jsonl(ruta):
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.work = os.path.join(self.base, "libros")
        self.knowledge = os.path.join(self.base, "knowledge")
        filas = [
            {"id": "loco-es", "titulo": "El loco esoterico", "idioma": "es",
             "familia": "tarot", "prioridad": "alta", "anio": 1910,
             "texto_ocr": "loco-es_djvu.txt", "texto_kb": 40,
             "estado": "texto_verificado"},
            {"id": "the-fool-en", "titulo": "The Fool Abroad", "idioma": "en",
             "familia": "tarot", "prioridad": "alta", "anio": 1920,
             "texto_ocr": "fool_djvu.txt", "texto_kb": 40,
             "estado": "texto_verificado"},
            {"id": "epub-demo", "titulo": "Libro EPUB", "idioma": "es",
             "tema": "tarot", "prioridad": "media", "anio": 2005,
             "fichero": "epubs/epub-demo.epub", "chars": 10000,
             "decision": "usar"},
        ]
        _escribir(os.path.join(self.knowledge, "fuentes_libros.jsonl"),
                  "\n".join(json.dumps(f, ensure_ascii=False) for f in filas))

    def run_pipeline(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = libros_pipeline.ejecutar(**kw)
        return code, buf.getvalue()


class Sequia(Base):
    """T24.1: estructura del orquestador, --dry-run y reanudación."""

    def test_dry_run_no_toca_nada(self):
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 3 libros", salida)
        self.assertIn("pendientes de descarga: 2", salida)
        self.assertFalse(os.path.exists(self.work))

    def test_dry_run_con_max_y_solo_ids(self):
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True, max=1)
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 1 libros", salida)
        code, salida = self.run_pipeline(
            work_dir=self.work, knowledge_dir=self.knowledge,
            hasta="informe", dry_run=True, solo_ids="epub-demo")
        self.assertIn("Inventario: 1 libros", salida)

    def test_etapa_descarga_escribe_crudo_y_registro(self):
        crud = CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               return_value=crud):
            code, _ = self.run_pipeline(
                work_dir=self.work, knowledge_dir=self.knowledge,
                hasta="descarga", pausa=0)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.work, "crudo",
                                                    "the-fool-en.txt")))
        registro = _leer_jsonl(os.path.join(self.work, "fetch.jsonl"))
        self.assertEqual([r["estado"] for r in registro], ["ok"])
        self.assertFalse(os.path.isdir(os.path.join(self.work, "limpio")))

    def test_reanudacion_no_redescarga(self):
        crud = CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               return_value=crud):
            self.run_pipeline(work_dir=self.work,
                              knowledge_dir=self.knowledge,
                              hasta="descarga", pausa=0)
        obtener = mock.patch.object(libros_pipeline.libros_fetch, "_obtener")
        with obtener as mock_obt:
            code, _ = self.run_pipeline(
                work_dir=self.work, knowledge_dir=self.knowledge,
                hasta="descarga", pausa=0)
        mock_obt.assert_not_called()
        self.assertEqual(code, 0)
        registro = _leer_jsonl(os.path.join(self.work, "fetch.jsonl"))
        self.assertEqual(registro[-1]["estado"], "ya_existe")

    def test_etapa_desconocida_devuelve_2(self):
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="teletransporte")
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.work))

    def test_inventario_vacio(self):
        vacio = os.path.join(self.base, "knowledge-vacio")
        os.makedirs(vacio)
        code, salida = self.run_pipeline(work_dir=self.work,
                                         knowledge_dir=vacio,
                                         hasta="informe")
        self.assertEqual(code, 0)
        self.assertIn("Inventario: 0 libros", salida)


class CadenaLimpieza(Base):
    """T24.2: limpieza → segmentación → informe sobre textos sintéticos."""

    def _sembrar_crudos(self):
        _escribir(os.path.join(self.work, "crudo", "loco-es.txt"), CRUDO_ES)
        _escribir(os.path.join(self.work, "crudo", "the-fool-en.txt"), CRUDO_EN)

    def test_cadena_hasta_informe(self):
        self._sembrar_crudos()
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="informe", pausa=0, solo_ids="loco-es,the-fool-en")
        self.assertEqual(code, 0)
        for libro_id in ("loco-es", "the-fool-en"):
            self.assertTrue(os.path.exists(os.path.join(self.work, "limpio",
                                                        libro_id + ".txt")),
                            "falta limpio de %s" % libro_id)
            secciones = _leer_jsonl(os.path.join(self.work, "secciones",
                                                 libro_id + ".jsonl"))
            self.assertGreaterEqual(len(secciones), 1)
            for seccion in secciones:
                for campo in ("seccion", "titulo", "texto", "chars",
                              "id_libro", "posicion"):
                    self.assertIn(campo, seccion)
                self.assertEqual(seccion["id_libro"], libro_id)
        informe = os.path.join(self.work, "informe.md")
        self.assertTrue(os.path.exists(informe))
        with open(informe, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("# Informe de calidad de libros", texto)
        self.assertIn("El loco esoterico", texto)

    def test_reanudacion_no_reprocesa_limpieza(self):
        self._sembrar_crudos()
        self.run_pipeline(work_dir=self.work, knowledge_dir=self.knowledge,
                          hasta="informe", pausa=0, solo_ids="loco-es,the-fool-en")
        ruta_limpio = os.path.join(self.work, "limpio", "loco-es.txt")
        ruta_secciones = os.path.join(self.work, "secciones", "loco-es.jsonl")
        with open(ruta_limpio, "a", encoding="utf-8") as fh:
            fh.write("\n#MARCA#")
        with open(ruta_secciones, encoding="utf-8") as fh:
            antes = fh.read()
        self.run_pipeline(work_dir=self.work, knowledge_dir=self.knowledge,
                          hasta="informe", pausa=0, solo_ids="loco-es,the-fool-en")
        with open(ruta_limpio, encoding="utf-8") as fh:
            self.assertIn("#MARCA#", fh.read())
        with open(ruta_secciones, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), antes)

    def test_epub_se_extrae_en_descarga(self):
        import zipfile
        capitulo = ("<html xmlns=\"http://www.w3.org/1999/xhtml\"><head>"
                    "<title>Libro EPUB</title></head><body>"
                    + "".join("<p>%s</p>" % _parrafo(RELLENO_ES, 10) for _ in range(8))
                    + "</body></html>")
        epub = os.path.join(self.base, "epubs", "epub-demo.epub")
        os.makedirs(os.path.dirname(epub), exist_ok=True)
        with zipfile.ZipFile(epub, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("OEBPS/capitulo.xhtml", capitulo)
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="limpieza", pausa=0, solo_ids="epub-demo")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.work, "crudo",
                                                    "epub-demo.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.work, "limpio",
                                                    "epub-demo.txt")))


class JuezCobertura(CadenaLimpieza):
    """T24.3: juez simulado sobre las secciones y cobertura con `calcular_cobertura`."""

    def _hasta_secciones(self):
        self._sembrar_crudos()
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="segmentacion", pausa=0,
                                    solo_ids="loco-es,the-fool-en")
        self.assertEqual(code, 0)

    def test_juez_simulado_produce_evidencias(self):
        self._hasta_secciones()
        code, salida = self.run_pipeline(work_dir=self.work,
                                         knowledge_dir=self.knowledge,
                                         hasta="juez", pausa=0, simulado=True,
                                         solo_ids="loco-es,the-fool-en")
        self.assertEqual(code, 0)
        self.assertIn("juez:", salida)
        self.assertIn("cobertura:", salida)
        ruta_ev = os.path.join(self.work, "evidencias", "evidencias.jsonl")
        self.assertTrue(os.path.exists(ruta_ev))
        evidencias = _leer_jsonl(ruta_ev)
        self.assertGreaterEqual(len(evidencias), 1)
        for ev in evidencias:
            self.assertIn("entidad_id", ev)
            self.assertIn("faceta", ev)
            self.assertIn(ev["fuente_id"], ("loco-es", "the-fool-en"))
        rutas, ignoradas = cobertura.leer_evidencias([ruta_ev])
        self.assertEqual(ignoradas, 0)
        self.assertEqual(len(rutas), len(evidencias))
        resumen = cobertura.calcular_cobertura(rutas)
        self.assertGreaterEqual(resumen["completas"], 0)
        self.assertGreater(len(resumen["celdas"]), 0)

    def test_juez_reanuda_sin_repetir_llamadas(self):
        self._hasta_secciones()
        self.run_pipeline(work_dir=self.work, knowledge_dir=self.knowledge,
                          hasta="juez", pausa=0, simulado=True,
                          solo_ids="loco-es,the-fool-en")
        ruta_ev = os.path.join(self.work, "evidencias", "evidencias.jsonl")
        with open(ruta_ev, encoding="utf-8") as fh:
            primeras = fh.read()
        code, salida = self.run_pipeline(work_dir=self.work,
                                         knowledge_dir=self.knowledge,
                                         hasta="juez", pausa=0, simulado=True,
                                         solo_ids="loco-es,the-fool-en")
        self.assertEqual(code, 0)
        with open(ruta_ev, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), primeras)
        self.assertIn("reaprovechadas", salida)

    def test_juez_sin_secciones_no_crashea(self):
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               _obtener_que_falla(503, "Servicio no disponible")):
            code, _ = self.run_pipeline(work_dir=self.work,
                                             knowledge_dir=self.knowledge,
                                             hasta="juez", pausa=0,
                                             simulado=True, solo_ids="loco-es")
        self.assertEqual(code, 0)


class JuezLotes(Base):
    """T32: el juez solo mira los libros pedidos, escribe por lotes con
    timeout acotado y deja progreso en el log."""

    def _hasta_secciones(self, solo_ids="loco-es,the-fool-en"):
        self._sembrar_crudos()
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="segmentacion", pausa=0,
                                    solo_ids=solo_ids)
        self.assertEqual(code, 0)

    def _sembrar_crudos(self):
        _escribir(os.path.join(self.work, "crudo", "loco-es.txt"), CRUDO_ES)
        _escribir(os.path.join(self.work, "crudo", "the-fool-en.txt"), CRUDO_EN)

    def test_juez_solo_juzga_los_libros_pedidos(self):
        self._hasta_secciones()
        ajeno = os.path.join(self.work, "secciones", "libro-ajeno.jsonl")
        seccion = {"seccion": 1, "titulo": "El loco", "texto": CRUDO_ES,
                   "chars": len(CRUDO_ES), "id_libro": "libro-ajeno",
                   "posicion": 0}
        _escribir(ajeno, json.dumps(seccion, ensure_ascii=False) + "\n")
        code, salida = self.run_pipeline(work_dir=self.work,
                                         knowledge_dir=self.knowledge,
                                         hasta="juez", pausa=0, simulado=True,
                                         solo_ids="loco-es")
        self.assertEqual(code, 0)
        ruta_ev = os.path.join(self.work, "evidencias", "evidencias.jsonl")
        evidencias = _leer_jsonl(ruta_ev)
        self.assertGreaterEqual(len(evidencias), 1)
        self.assertEqual({ev["fuente_id"] for ev in evidencias}, {"loco-es"})
        # El log anuncia el total real de secciones a juzgar.
        self.assertIn("lotes de", salida)

    def test_juez_escribe_cada_lote_sin_esperar_al_final(self):
        """Reproduce el cuelgue: antes no había ni una línea en juicios.jsonl
        hasta acabar TODAS las secciones; con lotes, la siguiente llamada ya
        ve escrito el lote anterior."""
        self._hasta_secciones(solo_ids="loco-es")
        ruta_sec = os.path.join(self.work, "secciones", "loco-es.jsonl")
        secciones = _leer_jsonl(ruta_sec)
        if len(secciones) < 2:
            # El crudo sintético solo segmenta una sección; se añade una
            # segunda distinta (otro número y texto con naipes, para que
            # tenga candidatos) y poder observar el avance entre lotes.
            segunda = {"seccion": 2, "posicion": 2,
                       "titulo": "El Loco",
                       "texto": "el loco del sol y de la luna es un viaje del alma",
                       "chars": 48, "id_libro": "loco-es"}
            with open(ruta_sec, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(segunda, ensure_ascii=False) + "\n")
            secciones = _leer_jsonl(ruta_sec)
        self.assertGreaterEqual(len(secciones), 2)
        ruta_juicios = os.path.join(self.work, "evidencias", "juicios.jsonl")

        class ClienteEspia:
            def __init__(self):
                self.vistos = []

            def chat(self, sistema, usuario):
                self.vistos.append(len(_leer_jsonl(ruta_juicios)))
                return juez._simular(sistema, usuario)

        espia = ClienteEspia()
        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="juez", pausa=0, cliente=espia,
                                    solo_ids="loco-es", lote_juez=1)
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(espia.vistos), 2)
        self.assertEqual(espia.vistos[0], 0)
        self.assertGreaterEqual(espia.vistos[1], 1,
                                "el lote anterior no se escribió antes de "
                                "empezar el siguiente")

    def test_cliente_juez_acota_timeout_y_reintentos(self):
        base = mock.Mock()
        with mock.patch.object(libros_pipeline.llm_client, "LLMClient",
                               return_value=base) as constructor:
            cliente = libros_pipeline._cliente_juez({"timeout": 12})
        constructor.assert_called_once_with(timeout=12)
        base.chat.return_value = "{}"
        cliente.chat("sistema", "usuario")
        self.assertEqual(base.chat.call_args.kwargs["max_reintentos"],
                         libros_pipeline.REINTENTOS_JUEZ)

    def test_cliente_explicito_no_se_envuelve(self):
        propio = object()
        self.assertIs(libros_pipeline._cliente_juez({"cliente": propio}), propio)

    def test_lote_fallido_no_aborta_la_pasada(self):
        self._hasta_secciones(solo_ids="loco-es")

        class ClienteQueFalla:
            def chat(self, sistema, usuario):
                raise TimeoutError("endpoint mudo")

        code, _ = self.run_pipeline(work_dir=self.work,
                                    knowledge_dir=self.knowledge,
                                    hasta="juez", pausa=0,
                                    cliente=ClienteQueFalla(),
                                    solo_ids="loco-es", lote_juez=1)
        self.assertEqual(code, 0)
        errores = _leer_jsonl(os.path.join(self.work, "errores.jsonl"))
        self.assertTrue(any(e["etapa"] == "juez" for e in errores))


class LimitacionTest(Base):
    """T24.4: los 429 seguidos cortan la pasada con código 3 y no cortan
    otros errores por libro."""

    def test_429_seguidos_parada_limpia(self):
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener",
                               _obtener_que_falla(429)):
            code, _ = self.run_pipeline(work_dir=self.work,
                                        knowledge_dir=self.knowledge,
                                        hasta="descarga", pausa=0)
        self.assertEqual(code, 3)
        # no se crean etapas posteriores
        self.assertFalse(os.path.exists(os.path.join(self.work, "limpio")))
        errores = _leer_jsonl(os.path.join(self.work, "errores.jsonl"))
        self.assertEqual([e["motivo"] for e in errores], ["http_429", "http_429"])
        registro = _leer_jsonl(os.path.join(self.work, "fetch.jsonl"))
        self.assertEqual(registro[-1]["estado"], "limitada")

    def test_un_429_no_corta_la_pasada(self):
        llamadas = []

        def _obtener(url, timeout=120):
            llamadas.append(url)
            if len(llamadas) == 1:
                raise urllib.error.HTTPError(url, 429, "limitado", None, None)
            return CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener", _obtener):
            code, _ = self.run_pipeline(work_dir=self.work,
                                        knowledge_dir=self.knowledge,
                                        hasta="descarga", pausa=0)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.work, "crudo",
                                                    "the-fool-en.txt")))
        errores = _leer_jsonl(os.path.join(self.work, "errores.jsonl"))
        self.assertEqual(errores[0]["id"], "loco-es")
        self.assertEqual(errores[0]["motivo"], "http_429")

    def test_error_por_libro_no_detiene_el_resto(self):
        def _obtener(url, timeout=120):
            if "loco" in url:
                raise urllib.error.HTTPError(url, 500, "fallback", None, None)
            return CRUDO_EN.encode("utf-8")
        with mock.patch.object(libros_pipeline.libros_fetch, "_obtener", _obtener):
            code, _ = self.run_pipeline(work_dir=self.work,
                                        knowledge_dir=self.knowledge,
                                        hasta="limpieza", pausa=0)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.work, "crudo",
                                                     "loco-es.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.work, "limpio",
                                                    "the-fool-en.txt")))
        errores = _leer_jsonl(os.path.join(self.work, "errores.jsonl"))
        self.assertEqual(errores[0]["motivo"], "http_500")


if __name__ == "__main__":
    unittest.main()
