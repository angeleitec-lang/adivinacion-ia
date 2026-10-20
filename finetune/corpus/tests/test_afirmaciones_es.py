"""Tests del extractor de afirmaciones en español (T29)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import afirmaciones_es as af
import juez


CUERPO = ("El dos de copas representa la unión y el afecto mutuo entre dos "
          "personas; habla de encuentros amorosos y de acuerdos del corazón.")


def _md(url, dominio, cuerpo):
    return "---\nurl: %s\ndominio: %s\n---\n%s" % (url, dominio, cuerpo)


def _seccion_web(url, cuerpo):
    """Sección como la construye juez para páginas web (hash compatible)."""
    return {"url": url, "texto": cuerpo}


def _evidencia(url="https://example.com/dos-copas", dominio="example.com",
              entidad_id="tarot-copas-02", faceta="significado_general",
              cuerpo=CUERPO, hash_seccion=None):
    if hash_seccion is None:
        hash_seccion = juez.hash_seccion(_seccion_web(url, cuerpo))
    return {
        "entidad_id": entidad_id,
        "faceta": faceta,
        "fuente_id": url,
        "dominio": dominio,
        "idioma": "es",
        "periodo": "moderna",
        "calidad": 4,
        "tipo": "web",
        "hash_seccion": hash_seccion,
    }


class LocalizadorTexto(unittest.TestCase):
    """T29.1: localizar el texto de la sección de una evidencia web."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = os.path.join(self.tmp.name, "web")
        dom = os.path.join(self.web, "example.com")
        os.makedirs(dom)
        with open(os.path.join(dom, "dos-copas.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(_md("https://example.com/dos-copas", "example.com",
                        CUERPO))
        self.indice = af.IndiceWeb(self.web)

    def tearDown(self):
        self.tmp.cleanup()

    def test_devuelve_texto_cuando_coincide(self):
        self.assertEqual(af.texto_seccion(_evidencia(), self.indice), CUERPO)

    def test_hash_distinto_devuelve_none(self):
        ev = _evidencia(hash_seccion="f" * 64)
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_dominio_inexistente_devuelve_none(self):
        ev = _evidencia(dominio="noexiste.com")
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_url_no_coincide_devuelve_none(self):
        ev = _evidencia(url="https://example.com/otra-pagina")
        self.assertIsNone(af.texto_seccion(ev, self.indice))

    def test_indice_reutilizable_entre_evidencias(self):
        ev = _evidencia()
        self.assertEqual(af.texto_seccion(ev, self.indice), CUERPO)
        self.assertEqual(af.texto_seccion(ev, self.indice), CUERPO)


CUERPO_COMB = ("El dos de copas y la estrella forman una union luminosa: la "
               "carta de la estrella aporta esperanza y el dos de copas trae "
               "afecto mutuo entre las personas.")


def _simulador(respuesta):
    def sim(sistema, usuario):
        return respuesta
    return sim


def _cliente_simulado(respuesta):
    from llm_client import LLMClient
    return LLMClient(simulado=_simulador(respuesta))


def _json_afs(afs):
    return json.dumps({"afirmaciones": afs}, ensure_ascii=False)


class ValidacionDeterminista(unittest.TestCase):
    """T29.2: reglas duras que no dependen del modelo."""

    def test_afirmacion_valida(self):
        vale, motivo = af.validar_afirmacion(
            "Representa la union y el afecto mutuo.", CUERPO,
            "tarot-copas-02", "significado_general")
        self.assertTrue(vale)
        self.assertIsNone(motivo)

    def test_vacia(self):
        vale, motivo = af.validar_afirmacion("   ", CUERPO,
                                           "tarot-copas-02", "amor")
        self.assertFalse(vale)
        self.assertEqual(motivo, "vacia")

    def test_mas_de_cuarenta_palabras(self):
        larga = ("El dos de copas representa la union y el afecto mutuo "
                "entre dos personas que comparten encuentros amorosos y "
                "acuerdos del corazon con sinceridad y con alegria "
                "desbordante cada dia de su vida juntos, y tambien promesas "
                "de un futuro compartido durante muchos anos mas")
        self.assertGreater(len(larga.split()), 40)
        vale, motivo = af.validar_afirmacion(larga, CUERPO,
                                            "tarot-copas-02", "amor")
        self.assertFalse(vale)
        self.assertEqual(motivo, "longitud")

    def test_sin_vocabulario_compartido(self):
        vale, motivo = af.validar_afirmacion(
            "Predice una herencia millonaria e inmediata.", CUERPO,
            "tarot-copas-02", "dinero")
        self.assertFalse(vale)
        self.assertEqual(motivo, "vocabulario")

    def test_otra_carta_en_faceta_simple(self):
        vale, motivo = af.validar_afirmacion(
            "La carta de la estrella aporta esperanza.", CUERPO_COMB,
            "tarot-copas-02", "significado_general")
        self.assertFalse(vale)
        self.assertEqual(motivo, "otra_carta")

    def test_otra_carta_sin_palabra_contexto_tambien_se_descarta(self):
        vale, motivo = af.validar_afirmacion(
            "La estrella aporta esperanza y luz.", CUERPO_COMB,
            "tarot-copas-02", "significado_general")
        self.assertFalse(vale)
        self.assertEqual(motivo, "otra_carta")

    def test_faceta_combinacion_permite_otra_carta(self):
        vale, motivo = af.validar_afirmacion(
            "La carta de la estrella aporta esperanza.", CUERPO_COMB,
            "tarot-copas-02", "combinaciones")
        self.assertTrue(vale)

    def test_entidad_compuesta_permite_otra_carta(self):
        vale, motivo = af.validar_afirmacion(
            "La carta de la estrella aporta esperanza.", CUERPO_COMB,
            "tarot-copas-02|tarot-mayor-18", "significado_general")
        self.assertTrue(vale)

    def test_entidad_no_carta_no_aplica_otra_carta(self):
        vale, motivo = af.validar_afirmacion(
            "La carta de la estrella aporta esperanza.", CUERPO_COMB,
            "marte|cuadratura|pluton|aspecto", "amor")
        self.assertTrue(vale)


class ExtraccionConModelo(unittest.TestCase):
    """T29.2: prompt, parseo y recuento con modelo simulado."""

    def test_extrae_afirmaciones_validas(self):
        cliente = _cliente_simulado(_json_afs([
            "Representa la union y el afecto mutuo.",
            "Habla de encuentros amorosos y acuerdos del corazon.",
        ]))
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "significado_general", CUERPO)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(len(res["afirmaciones"]), 2)
        self.assertEqual(res["descartadas"], [])

    def test_json_roto_estado_error(self):
        cliente = _cliente_simulado("esto no es json")
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "amor", CUERPO)
        self.assertEqual(res["estado"], "error")
        self.assertEqual(res["afirmaciones"], [])

    def test_lista_vacia_es_ok(self):
        cliente = _cliente_simulado(_json_afs([]))
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "salud", CUERPO)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["afirmaciones"], [])

    def test_inventada_se_descarta_por_vocabulario(self):
        cliente = _cliente_simulado(_json_afs([
            "Representa la union y el afecto mutuo.",
            "Predice una herencia millonaria e inmediata.",
        ]))
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "dinero", CUERPO)
        self.assertEqual(len(res["afirmaciones"]), 1)
        self.assertEqual(res["descartadas"][0][1], "vocabulario")

    def test_otra_carta_se_descarta(self):
        cliente = _cliente_simulado(_json_afs([
            "La carta de la estrella aporta esperanza.",
        ]))
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "significado_general", CUERPO_COMB)
        self.assertEqual(res["afirmaciones"], [])
        self.assertEqual(res["descartadas"][0][1], "otra_carta")

    def test_mas_de_doce_sobran_por_exceso(self):
        afs = ["Afecto mutuo numero %d." % i for i in range(14)]
        cliente = _cliente_simulado(_json_afs(afs))
        res = af.extraer_afirmaciones(cliente, "tarot-copas-02",
                                     "amor", CUERPO)
        self.assertEqual(len(res["afirmaciones"]), 12)
        exceso = [m for _, m in res["descartadas"] if m == "exceso"]
        self.assertEqual(len(exceso), 2)

    def test_registro_afirmacion_tiene_campos_de_evidencia(self):
        ev = _evidencia()
        reg = af.registro_afirmacion(ev, "Representa la union afectiva.")
        self.assertEqual(reg["entidad_id"], "tarot-copas-02")
        self.assertEqual(reg["faceta"], "significado_general")
        self.assertEqual(reg["fuente_id"], ev["fuente_id"])
        self.assertEqual(reg["dominio"], "example.com")
        self.assertEqual(reg["periodo"], "moderna")
        self.assertEqual(reg["calidad"], 4)
        self.assertEqual(reg["afirmacion"], "Representa la union afectiva.")


class PipelineCLI(unittest.TestCase):
    """T29.3: CLI reanudable con sidecar de procesados e informe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.web = os.path.join(self.tmp.name, "web")
        dom = os.path.join(self.web, "example.com")
        os.makedirs(dom)
        with open(os.path.join(dom, "dos-copas.md"), "w",
                  encoding="utf-8") as fh:
            fh.write(_md("https://example.com/dos-copas", "example.com",
                        CUERPO))
        self.ev_path = os.path.join(self.tmp.name, "evidencias.jsonl")
        with open(self.ev_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(_evidencia(), ensure_ascii=False) + "\n")
            ev_sin = _evidencia(url="https://example.com/absente")
            fh.write(json.dumps(ev_sin, ensure_ascii=False) + "\n")
        self.out = os.path.join(self.tmp.name, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, extra=(), cliente=None):
        argv = ["--evidencias", self.ev_path, "--web-dir", self.web,
                "--out-dir", self.out] + list(extra)
        return af.main(argv, cliente=cliente)

    def _lineas(self, nombre):
        ruta = os.path.join(self.out, nombre)
        if not os.path.exists(ruta):
            return []
        with open(ruta, encoding="utf-8") as fh:
            return [l for l in fh.read().splitlines() if l.strip()]

    def test_procesa_y_escribe_archivos(self):
        cliente = _cliente_simulado(_json_afs([
            "Representa la union y el afecto mutuo.",
        ]))
        stats = self._run(cliente=cliente)
        self.assertEqual(stats["procesadas"], 2)
        self.assertEqual(stats["sin_texto"], 1)
        self.assertEqual(stats["errores"], 0)
        self.assertEqual(stats["afirmaciones"], 1)
        self.assertEqual(len(self._lineas("afirmaciones.jsonl")), 1)
        self.assertEqual(len(self._lineas("procesados.jsonl")), 2)
        informe = os.path.join(self.out, "afirmaciones_informe.md")
        self.assertTrue(os.path.exists(informe))
        with open(informe, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("sin_texto", texto)
        self.assertIn("tarot", texto)

    def test_reanudable_no_reprocesa(self):
        cliente = _cliente_simulado(_json_afs([
            "Representa la union y el afecto mutuo.",
        ]))
        self._run(cliente=cliente)
        stats2 = self._run(cliente=cliente)
        self.assertEqual(stats2["procesadas"], 0)
        self.assertEqual(len(self._lineas("afirmaciones.jsonl")), 1)
        self.assertEqual(len(self._lineas("procesados.jsonl")), 2)

    def test_limite_de_evidencias(self):
        cliente = _cliente_simulado(_json_afs([]))
        stats = self._run(extra=["--limite", "1"], cliente=cliente)
        self.assertEqual(stats["procesadas"], 1)

    def test_descartadas_se_cuentan_por_motivo(self):
        cliente = _cliente_simulado(_json_afs([
            "Predice una herencia millonaria e inmediata.",
        ]))
        stats = self._run(cliente=cliente)
        self.assertEqual(stats["descartadas"].get("vocabulario"), 1)
        self.assertEqual(stats["afirmaciones"], 0)


class EvaluarUtilidad(unittest.TestCase):
    """T34.1: filtro determinista de utilidad de una afirmación."""

    def _ok(self, a, eid="naipe-oros-03", faceta="significado_general"):
        vale, motivo = af.evaluar_utilidad(a, eid, faceta)
        self.assertTrue(vale, msg="descartada por %s: %s" % (motivo, a))
        self.assertIsNone(motivo)

    def _mal(self, a, esperado, eid="naipe-oros-03",
             faceta="significado_general"):
        vale, motivo = af.evaluar_utilidad(a, eid, faceta)
        self.assertFalse(vale)
        self.assertEqual(motivo, esperado)

    def test_afirmacion_con_sustancia_pasa(self):
        self._ok("El dos de copas habla de reciprocidad y de un vínculo "
                "donde ambas partes dan y reciben a partes iguales.")

    def test_vacia(self):
        self._mal("   ", "vacia")

    def test_identificador_guion(self):
        self._mal("El naipe bastos-05 se vincula con los signos zodiacales "
                "Aries, Leo y Sagitario.", "identificador")

    def test_identificador_numero_suelto(self):
        self._mal("El naipe oros 05 augura prosperidad en los negocios.",
                 "identificador")

    def test_identificador_sin_naipe(self):
        self._mal("La energía de copas-02 favorece los reencuentros.",
                 "identificador")

    def test_deictica_consultante(self):
        self._mal("El consultante quiere comenzar una relación estable.",
                 "deictica", eid="tarot-copas-02")

    def test_deictica_estas_cartas(self):
        self._mal("Juntas, estas cartas describen un encuentro que cura.",
                 "deictica", eid="tarot-copas-02")

    def test_deictica_tirada(self):
        self._mal("En una tirada, esta combinación habla de revelación.",
                 "deictica", eid="tarot-mayor-16")

    def test_deictica_acompanen(self):
        self._mal("La interpretación para solteros depende de las cartas "
                "que acompañen al cinco de espadas.", "deictica",
                eid="naipe-espadas-05")

    def test_corta_sin_sustancia(self):
        self._mal("Tiene polaridad masculina.", "corta")

    def test_repite_nombre_elemento(self):
        self._mal("El 3 de Oros está ligado al elemento tierra.",
                 "repite_nombre")

    def test_repite_nombre_signo(self):
        self._mal("Aries es un signo de fuego.", "repite_nombre",
                 eid="aries|signo")

    def test_signo_con_sustancia_pasa(self):
        self._ok("Los nativos de Aries destacan por su ambición y su "
                "liderazgo natural en equipo.", eid="aries|signo")

    def test_elemento_con_sustancia_pasa(self):
        self._ok("El fuego de bastos da fuerza para actuar y comenzar "
                "nuevos proyectos con decisión.", eid="naipe-bastos-02")


class FiltroUtilidadCLI(unittest.TestCase):
    """T34.2: modo --filtrar-utilidad del CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.entrada = os.path.join(self.tmp.name, "afirmaciones.jsonl")
        self.out = os.path.join(self.tmp.name, "out")
        regs = [
            {"entidad_id": "naipe-oros-03", "faceta": "significado_general",
             "fuente_id": "u1", "dominio": "d", "periodo": "p",
             "calidad": 4,
             "afirmacion": "El tres de oros enseña a administrar con "
                          "paciencia los frutos del trabajo diario."},
            {"entidad_id": "naipe-oros-03", "faceta": "correspondencias",
             "fuente_id": "u2", "dominio": "d", "periodo": "p",
             "calidad": 4,
             "afirmacion": "El 3 de Oros está ligado al elemento tierra."},
            {"entidad_id": "tarot-copas-02", "faceta": "amor",
             "fuente_id": "u3", "dominio": "d", "periodo": "p",
             "calidad": 4,
             "afirmacion": "El consultante quiere comenzar una relación."},
        ]
        with open(self.entrada, "w", encoding="utf-8") as fh:
            for r in regs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _lineas(self, nombre):
        ruta = os.path.join(self.out, nombre)
        if not os.path.exists(ruta):
            return []
        with open(ruta, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh.read().splitlines()
                    if l.strip()]

    def test_separa_utiles_y_descartadas(self):
        stats = af.main(["--filtrar-utilidad", "--in", self.entrada,
                        "--out-dir", self.out])
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["utiles"], 1)
        utiles = self._lineas("afirmaciones_utiles.jsonl")
        descartadas = self._lineas("descartadas_utilidad.jsonl")
        self.assertEqual(len(utiles), 1)
        self.assertIn("administrar", utiles[0]["afirmacion"])
        self.assertEqual(len(descartadas), 2)
        motivos = sorted(d["motivo"] for d in descartadas)
        self.assertEqual(motivos, ["deictica", "repite_nombre"])

    def test_original_no_se_toca(self):
        with open(self.entrada, encoding="utf-8") as fh:
            antes = fh.read()
        af.main(["--filtrar-utilidad", "--in", self.entrada,
                "--out-dir", self.out])
        with open(self.entrada, encoding="utf-8") as fh:
            despues = fh.read()
        self.assertEqual(antes, despues)


if __name__ == "__main__":
    unittest.main()
