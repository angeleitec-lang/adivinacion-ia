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


if __name__ == "__main__":
    unittest.main()
