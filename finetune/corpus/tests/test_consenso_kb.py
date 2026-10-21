"""Tests de las comprobaciones KB y el consenso por celda (T38 / A6)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import consenso_kb as ck
from llm_client import LLMClient


CORR = ck.cargar_correspondencias()


class TestCorrespondencias(unittest.TestCase):
    def test_signos_y_palos(self):
        self.assertEqual(CORR["signo_elemento"]["aries"], "fuego")
        self.assertEqual(CORR["signo_elemento"]["cancer"], "agua")
        self.assertIn("marte", CORR["signo_regentes"]["aries"])
        self.assertEqual(CORR["palo_elemento"]["bastos"], "fuego")
        self.assertEqual(CORR["palo_elemento"]["copas"], "agua")

    def test_signo_de_entidad(self):
        self.assertEqual(ck.signo_de_entidad("aries|signo"), "aries")
        self.assertEqual(
            ck.signo_de_entidad("jupiter|aries|planeta_en_signo"), "aries")
        self.assertIsNone(ck.signo_de_entidad("tarot-mayor-00"))
        self.assertIsNone(ck.signo_de_entidad("sol|casa1|planeta_en_casa"))

    def test_elemento_de_entidad(self):
        self.assertEqual(
            ck.elemento_de_entidad("aries|signo", CORR), "fuego")
        self.assertEqual(
            ck.elemento_de_entidad("jupiter|cancer|planeta_en_signo", CORR),
            "agua")
        self.assertEqual(
            ck.elemento_de_entidad("naipe-bastos-02", CORR), "fuego")
        self.assertEqual(
            ck.elemento_de_entidad("tarot-espadas-05", CORR), "aire")
        self.assertIsNone(ck.elemento_de_entidad("tarot-mayor-00", CORR))
        self.assertIsNone(ck.elemento_de_entidad("11|alma", CORR))


class TestContradiccionKB(unittest.TestCase):
    def test_gnomos_con_aries_es_error(self):
        vale, motivo = ck.contradiccion_kb(
            "Aries se asocia tradicionalmente con los gnomos.",
            "aries|signo", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "ser_elemental")

    def test_gnomos_con_dos_bastos_es_error(self):
        vale, motivo = ck.contradiccion_kb(
            "El dos de bastos esta regido por los gnomos del fuego.",
            "naipe-bastos-02", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "ser_elemental")

    def test_salamandras_con_bastos_ok(self):
        vale, _ = ck.contradiccion_kb(
            "Los bastos se relacionan con las salamandras del fuego.",
            "naipe-bastos-02", CORR)
        self.assertFalse(vale)

    def test_ondinas_con_copas_ok(self):
        vale, _ = ck.contradiccion_kb(
            "Las copas estan gobernadas por las ondinas del agua.",
            "naipe-copas-03", CORR)
        self.assertFalse(vale)

    def test_elemento_explicito_incorrecto(self):
        vale, motivo = ck.contradiccion_kb(
            "Aries es un signo de agua.", "aries|signo", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "elemento")

    def test_elemento_explicito_correcto(self):
        vale, _ = ck.contradiccion_kb(
            "Aries es un signo de fuego.", "aries|signo", CORR)
        self.assertFalse(vale)

    def test_regente_incorrecto(self):
        vale, motivo = ck.contradiccion_kb(
            "Aries esta regido por Venus.", "aries|signo", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "regente")

    def test_regente_correcto(self):
        vale, _ = ck.contradiccion_kb(
            "Aries esta regido por Marte.", "aries|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_signo(self):
        vale, motivo = ck.contradiccion_kb(
            "Aries se relaciona con los signos Aries, Leo y Sagitario.",
            "aries|signo", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "tautologia")

    def test_relacion_sin_tautologia(self):
        vale, _ = ck.contradiccion_kb(
            "Aries se relaciona con Leo y Sagitario.", "aries|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_carta(self):
        vale, motivo = ck.contradiccion_kb(
            "El dos de bastos se combina con el dos de bastos.",
            "naipe-bastos-02", CORR)
        self.assertTrue(vale)
        self.assertEqual(motivo, "tautologia")

    def test_tautologia_contexto_lejano_no_cuenta(self):
        vale, _ = ck.contradiccion_kb(
            "El color azul se asocia con el agua y con la letra Mem "
            "dentro del simbolismo de Cancer.",
            "cancer|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_negada_antes_del_verbo(self):
        vale, _ = ck.contradiccion_kb(
            "El Cancer no se asocia con el agua.", "cancer|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_negada_en_cola(self):
        vale, _ = ck.contradiccion_kb(
            "La verdad corresponde a la carta diecisiete, no al Cancer.",
            "cancer|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_sujeto_distinto_no_cuenta(self):
        vale, _ = ck.contradiccion_kb(
            "El 2 de Bastos corresponde al tercer decanato de Aries "
            "y rige del 10 al 19 de abril.",
            "aries|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_sujeto_simbolo_no_cuenta(self):
        vale, _ = ck.contradiccion_kb(
            "El leon se asocia al querube del Fuego y al signo Leo.",
            "leo|signo", CORR)
        self.assertFalse(vale)

    def test_tautologia_carta_sujeto_distinto_no_cuenta(self):
        vale, _ = ck.contradiccion_kb(
            "El Emperador se relaciona con el dos de bastos y su fuego.",
            "naipe-bastos-02", CORR)
        self.assertFalse(vale)

    def test_sin_elemento_no_aplica(self):
        vale, _ = ck.contradiccion_kb(
            "El numero 11 se relaciona con el 11.", "11|alma", CORR)
        self.assertFalse(vale)

    def test_vacia(self):
        self.assertEqual(ck.contradiccion_kb("", "aries|signo", CORR),
                         (False, None))


class TestTradicion(unittest.TestCase):
    def test_tradiciones(self):
        self.assertEqual(ck.tradicion_de_fuente("waite-smith-rws"), "RWS")
        self.assertEqual(ck.tradicion_de_fuente("tarot-marsella-1930"),
                         "Marsella")
        self.assertEqual(ck.tradicion_de_fuente("algun-libro", "clasica"),
                         "clasica")
        self.assertEqual(ck.tradicion_de_fuente("algun-libro", "moderna"),
                         "moderna")
        self.assertEqual(ck.tradicion_de_fuente("otro"), "sin_periodo")


class TestValidarParticion(unittest.TestCase):
    def test_valida(self):
        ck.validar_particion(4)(
            {"grupos": [[0, 2], [1], [3]], "contradicciones": [[0, 3]]})

    def test_indice_faltante(self):
        with self.assertRaises(ValueError):
            ck.validar_particion(4)({"grupos": [[0, 1], [2]]})

    def test_indice_repetido(self):
        with self.assertRaises(ValueError):
            ck.validar_particion(3)(
                {"grupos": [[0, 1], [1, 2]]})

    def test_indice_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            ck.validar_particion(2)({"grupos": [[0, 5]]})

    def test_contradiction_mismo_grupo_se_descarta(self):
        # Un par contradictorio dentro del mismo grupo de equivalencia es ruido:
        # se descarta el par y se conserva la particion valida (no se falla).
        res = ck.validar_particion(2)(
            {"grupos": [[0, 1]], "contradicciones": [[0, 1]]})
        self.assertEqual(res["grupos"], [[0, 1]])
        self.assertEqual(res["contradicciones"], [])

    def test_contradiction_mismo_grupo_parcial(self):
        # Se conservan los pares entre grupos distintos y se quitan los intra-grupo.
        res = ck.validar_particion(4)(
            {"grupos": [[0, 1], [2, 3]],
             "contradicciones": [[0, 1], [0, 2], [2, 3]]})
        self.assertEqual(res["contradicciones"], [[0, 2]])

    def test_par_malformado_si_falla(self):
        with self.assertRaises(ValueError):
            ck.validar_particion(2)(
                {"grupos": [[0], [1]], "contradicciones": [[0, 9]]})

    def test_sin_grupos(self):
        with self.assertRaises(ValueError):
            ck.validar_particion(2)({"grupos": []})


class TestCacheEquivalencia(unittest.TestCase):
    def test_persistencia(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "cache.jsonl")
            c1 = ck.CacheEquivalencia(ruta)
            clave = ck.CacheEquivalencia.clave("e", "f", ["a", "b"])
            self.assertIsNone(c1.get(clave))
            c1.put(clave, {"grupos": [[0], [1]], "contradicciones": []})
            c2 = ck.CacheEquivalencia(ruta)
            self.assertEqual(c2.get(clave),
                            {"grupos": [[0], [1]], "contradicciones": []})

    def test_clave_estable(self):
        k1 = ck.CacheEquivalencia.clave("e", "f", ["a", "b"])
        k2 = ck.CacheEquivalencia.clave("e", "f", ["a", "b"])
        k3 = ck.CacheEquivalencia.clave("e", "f", ["a", "c"])
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)


def _cliente_json(respuesta):
    return LLMClient(simulado=lambda s, u: json.dumps(respuesta))


class TestAgruparCelda(unittest.TestCase):
    def test_una_sola_afirmacion_sin_llamada(self):
        llamadas = []

        def sim(s, u):
            llamadas.append(u)
            return "{}"
        cliente = LLMClient(simulado=sim)
        res = ck.agrupar_celda(cliente, "e", "f", [{"afirmacion": "unica"}])
        self.assertEqual(res, {"grupos": [[0]], "contradicciones": []})
        self.assertEqual(llamadas, [])

    def test_agrupacion_y_cache(self):
        llamadas = []

        def sim(s, u):
            llamadas.append(u)
            return json.dumps({"grupos": [[0, 1], [2]], "contradicciones": []})
        cliente = LLMClient(simulado=sim)
        with tempfile.TemporaryDirectory() as d:
            cache = ck.CacheEquivalencia(os.path.join(d, "c.jsonl"))
            afs = [{"afirmacion": "a"}, {"afirmacion": "b"},
                   {"afirmacion": "c"}]
            r1 = ck.agrupar_celda(cliente, "e", "f", afs, cache)
            self.assertEqual(r1["grupos"], [[0, 1], [2]])
            r2 = ck.agrupar_celda(cliente, "e", "f", afs, cache)
            self.assertEqual(r1, r2)

    def test_fallback_singletons_si_llm_invalido(self):
        # El LLM devuelve una particion incompleta tras todos los reintentos:
        # la celda no debe tumbar el run; cae a singletons con fallback=True.
        def sim(s, u):
            return json.dumps({"grupos": [[0]]})  # faltan indices 1 y 2
        cliente = LLMClient(simulado=sim)
        afs = [{"afirmacion": "a"}, {"afirmacion": "b"}, {"afirmacion": "c"}]
        res = ck.agrupar_celda(cliente, "e", "f", afs)
        self.assertEqual(res["grupos"], [[0], [1], [2]])
        self.assertEqual(res["contradicciones"], [])
        self.assertTrue(res.get("fallback"))

    def test_fallback_no_rompe_construir_consensos(self):
        # Una celda en fallback se registra igual (unica_fuente por singletons)
        # y no lanza; el resto del run continua.
        def sim(s, u):
            return json.dumps({"grupos": [[0]]})
        cliente = LLMClient(simulado=sim)
        celdas = {("e", "f"): [
            {"entidad_id": "e", "faceta": "f", "afirmacion": "a",
             "fuente_id": "s1"},
            {"entidad_id": "e", "faceta": "f", "afirmacion": "b",
             "fuente_id": "s2"},
        ]}
        res = ck.construir_consensos(cliente, celdas)
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["fallback"])
        self.assertEqual(len(res[0]["unica_fuente"]), 2)


class TestConstruirConsensos(unittest.TestCase):
    def _celdas(self):
        return {
            ("aries|signo", "personalidad"): [
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "web1", "periodo": "moderna",
                 "afirmacion": "Aries es un signo de fuego."},
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "libro1", "periodo": "clasica",
                 "afirmacion": "Aries pertenece al elemento fuego."},
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "web2", "periodo": "moderna",
                 "afirmacion": "Aries es impulsivo y directo."},
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "libro2", "periodo": "moderna",
                 "afirmacion": "Aries se asocia con los gnomos.",
                 "contradice_kb": True, "motivo_contradice": "ser_elemental"},
            ],
        }

    def test_mayoritaria_unica_fuente_alerta(self):
        cliente = _cliente_json(
            {"grupos": [[0, 1], [2]], "contradicciones": []})
        res = ck.construir_consensos(cliente, self._celdas())[0]
        self.assertEqual(len(res["mayoritarias"]), 1)
        self.assertEqual(res["mayoritarias"][0]["n_fuentes"], 2)
        self.assertEqual(len(res["unica_fuente"]), 1)
        self.assertEqual(len(res["alertas_factuales"]), 1)
        self.assertEqual(res["alertas_factuales"][0]["motivo"], "ser_elemental")
        self.assertEqual(res["n_afirmaciones"], 4)

    def test_discrepancia_entre_tradiciones(self):
        cliente = _cliente_json(
            {"grupos": [[0], [1], [2]],
             "contradicciones": [[0, 1]]})
        res = ck.construir_consensos(cliente, self._celdas())[0]
        self.assertEqual(len(res["discrepancias"]), 1)
        lado_a = res["discrepancias"][0]["a"]
        lado_b = res["discrepancias"][0]["b"]
        self.assertIn("clasica", lado_a["tradiciones"] + lado_b["tradiciones"])
        self.assertNotEqual(lado_a["afirmacion"], lado_b["afirmacion"])

    def test_unica_fuente_no_duplica_discrepancia(self):
        cliente = _cliente_json(
            {"grupos": [[0], [1], [2]],
             "contradicciones": [[0, 1]]})
        res = ck.construir_consensos(cliente, self._celdas())[0]
        unicas = {u["afirmacion"] for u in res["unica_fuente"]}
        disp = {res["discrepancias"][0]["a"]["afirmacion"],
                res["discrepancias"][0]["b"]["afirmacion"]}
        self.assertTrue(unicas.isdisjoint(disp))
        self.assertEqual(len(res["unica_fuente"]), 1)


class TestCLIConsenso(unittest.TestCase):
    def _escribir(self, ruta, regs):
        with open(ruta, "w", encoding="utf-8") as f:
            for r in regs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def test_simulado_y_reanudacion(self):
        with tempfile.TemporaryDirectory() as d:
            web = os.path.join(d, "web.jsonl")
            libros = os.path.join(d, "libros.jsonl")
            self._escribir(web, [
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "web1", "periodo": "moderna",
                 "afirmacion": "Aries se caracteriza por la iniciativa y el coraje."},
            ])
            self._escribir(libros, [
                {"entidad_id": "aries|signo", "faceta": "personalidad",
                 "fuente_id": "libro1", "periodo": "clasica",
                 "afirmacion": "Aries impulsa a tomar la delantera en situaciones nuevas."},
                {"entidad_id": "tauro|signo", "faceta": "personalidad",
                 "fuente_id": "libro1", "periodo": "moderna",
                 "afirmacion": "Tauro valora la estabilidad y los placeres sensoriales."},
            ])
            out = os.path.join(d, "out")
            stats = ck.main([
                "--web-afirmaciones", web,
                "--libros-afirmaciones", libros,
                "--out-dir", out, "--workers", "1", "--simulado"])
            self.assertEqual(stats["celdas"], 2)
            self.assertEqual(stats["afirmaciones"], 3)
            ruta = os.path.join(out, "consenso.jsonl")
            self.assertTrue(os.path.exists(ruta))
            self.assertTrue(os.path.exists(
                os.path.join(out, "consenso_informe.md")))
            # Reanudacion: no hay celdas pendientes
            stats2 = ck.main([
                "--web-afirmaciones", web,
                "--libros-afirmaciones", libros,
                "--out-dir", out, "--workers", "1", "--simulado"])
            self.assertEqual(stats2["celdas"], 0)
            self.assertEqual(stats2["omitidas_existentes"], 2)

    def test_web_normalizada_detecta_contradiction(self):
        with tempfile.TemporaryDirectory() as d:
            web = os.path.join(d, "web.jsonl")
            self._escribir(web, [
                {"entidad_id": "aries|signo", "faceta": "simbolismo",
                 "fuente_id": "web1", "periodo": "moderna",
                 "afirmacion": "Aries se asocia con los gnomos."},
            ])
            out = os.path.join(d, "out")
            stats = ck.main([
                "--web-afirmaciones", web,
                "--libros-afirmaciones", os.path.join(d, "nada.jsonl"),
                "--out-dir", out, "--workers", "1", "--simulado"])
            self.assertEqual(stats["alertas"], 1)
            self.assertEqual(stats["motivos_alertas"].get("ser_elemental"), 1)


if __name__ == "__main__":
    unittest.main()
