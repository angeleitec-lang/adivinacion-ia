# Tests de libros_comprados_astro (T119): detector EN->ES, segmentacion,
# puerta anti-copia, validacion de work-dir y preparacion. Sin red ni LLM real:
# se usa el modo simulado del juez y del extractor.
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import shutil
import tempfile
import unittest

import libros_comprados_astro as mod


class TestNormalizacion(unittest.TestCase):
    def test_sin_tildes(self):
        self.assertEqual(mod.sin_tildes("Canción"), "Cancion")
        self.assertEqual(mod.sin_tildes("Capricornio"), "Capricornio")

    def test_norm_minusculas_sin_tildes(self):
        self.assertEqual(mod.norm("Mars IN Pisces"), "mars in pisces")


class TestCanonPlanetas(unittest.TestCase):
    def test_orden_canonico(self):
        self.assertEqual(mod._canon_planetas("marte", "sol"), ("sol", "marte"))
        self.assertEqual(mod._canon_planetas("sol", "luna"), ("sol", "luna"))
        self.assertEqual(mod._canon_planetas("pluton", "venus"), ("venus", "pluton"))

    def test_igualdad(self):
        self.assertEqual(mod._canon_planetas("venus", "venus"), ("venus", "venus"))


class TestDetectarEntidades(unittest.TestCase):
    def test_planeta_en_signo(self):
        self.assertEqual(mod.detectar_entidades("Sun was in Pisces"),
                         ["sol|piscis|planeta_en_signo"])
        self.assertEqual(mod.detectar_entidades("Venus in Cancer"),
                         ["venus|cancer|planeta_en_signo"])

    def test_planeta_en_casa_palabra(self):
        self.assertEqual(mod.detectar_entidades("Saturn in his natal fifth house"),
                         ["saturno|casa5|planeta_en_casa"])

    def test_planeta_en_casa_digito(self):
        self.assertEqual(mod.detectar_entidades("Sun in the 2nd house"),
                         ["sol|casa2|planeta_en_casa"])

    def test_aspecto_orden_canonico(self):
        self.assertEqual(mod.detectar_entidades("Venus square Moon"),
                         ["luna|cuadratura|venus|aspecto"])
        self.assertEqual(mod.detectar_entidades("Mars is trine his Sun"),
                         ["sol|trigono|marte|aspecto"])

    def test_signo_por_frase(self):
        self.assertEqual(mod.detectar_entidades("the sign of Aries"),
                         ["aries|signo"])

    def test_luna_no_es_signo(self):
        # 'Moon' es planeta, no signo: no debe dar falso positivo de signo.
        self.assertEqual(mod.detectar_entidades("the Moon is a water sign"), [])

    def test_sin_ruido(self):
        self.assertEqual(mod.detectar_entidades("no astrology here at all"), [])

    def test_dedup_y_validos(self):
        ids = mod.detectar_entidades(
            "Sun in Pisces and the Sun in Pisces again")
        self.assertEqual(ids.count("sol|piscis|planeta_en_signo"), 1)


class TestSegmentar(unittest.TestCase):
    def test_emite_secciones_con_entidad(self):
        texto = ("Sun was in Pisces in his chart. " * 6)
        secs = mod.segmentar(texto, "arroyo_astrologia_psicologia_1982")
        self.assertTrue(len(secs) >= 1)
        for s in secs:
            self.assertIn("entidad_id", s)
            self.assertIn("texto", s)
            self.assertIn("chars", s)
            self.assertEqual(s["id_libro"], "arroyo_astrologia_psicologia_1982")
            self.assertIn("posicion", s)
            self.assertTrue(s["entidad_id"].endswith(
                ("|signo", "|planeta_en_signo", "|planeta_en_casa", "|aspecto")))

    def test_parrafo_sin_entidad_no_emite(self):
        texto = "This paragraph talks about cooking pasta and has no astrology. " * 6
        secs = mod.segmentar(texto, "arroyo_astrologia_psicologia_1982")
        self.assertEqual(secs, [])

    def test_max_entidades_por_parrafo(self):
        # Un parrafo con muchas entidades no debe exceder MAX_ENTIDADES_PARRAFO.
        partes = []
        for i, (p, s) in enumerate([
                ("Sun", "Pisces"), ("Moon", "Aries"), ("Mars", "Taurus"),
                ("Venus", "Cancer"), ("Jupiter", "Leo"), ("Saturn", "Virgo")]):
            partes.append("%s in %s sign here for example number %d" % (p, s, i))
        texto = " ".join(partes)
        secs = mod.segmentar(texto, "arroyo_astrologia_psicologia_1982")
        self.assertTrue(all(len(s["entidad_id"]) > 0 for s in secs))
        self.assertTrue(len(secs) <= mod.MAX_ENTIDADES_PARRAFO)


class TestAntiCopia(unittest.TestCase):
    def setUp(self):
        self.libro = ("the sun represents the core self and the vital life force "
                     "of a person and it is the center of the solar system around "
                     "which all the other planets revolve in their orbits")

    def test_copia_literal_rechazada(self):
        copia = ("the core self and the vital life force of a person and it is "
                "the center of the solar system around which all the other "
                "planets revolve")
        self.assertTrue(mod.es_copia_literal(copia, texto_libro=self.libro))

    def test_paraphrase_no_rechazada(self):
        parafraseo = "el Sol simboliza la identidad central y la energia vital"
        self.assertFalse(mod.es_copia_literal(parafraseo, texto_libro=self.libro))

    def test_indice_reutilizable(self):
        indice = mod.construir_indice_copia(self.libro)
        copia = ("the core self and the vital life force of a person and it is "
                "the center of the solar system around which all the other "
                "planets revolve")
        self.assertTrue(mod.es_copia_literal(copia, indice=indice))
        self.assertFalse(mod.es_copia_literal("nada que ver con el libro aqui",
                                            indice=indice))


class TestValidarWorkDir(unittest.TestCase):
    def test_rechaza_work_dir_real(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir(mod.WORK_DIR_REAL)

    def test_rechaza_subdir_del_real(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir(os.path.join(mod.WORK_DIR_REAL, "subida"))

    def test_acepta_work_dir_astro(self):
        # El work-dir de astro NO es el real -> debe aceptarse.
        real = mod.validar_work_dir(mod.WORK_DIR)
        self.assertTrue(real.endswith("libros_comprados_astro"))


class TestPreparar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t119_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_crea_subdirs_y_meta(self):
        mod.preparar(self.tmp)
        for sub in ("secciones", "evidencias", "knowledge", "afirmaciones"):
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, sub)))
        meta = os.path.join(self.tmp, "knowledge", mod.META_NOMBRE)
        with open(meta, encoding="utf-8") as fh:
            lineas = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(lineas), 2)
        for d in lineas:
            self.assertEqual(d["origen"], "comprado_por_usuario")
            self.assertEqual(d["idioma"], "en")
            self.assertIn("copyright", d["licencia_hint"])
        ids = {d["id"] for d in lineas}
        self.assertIn("arroyo_astrologia_psicologia_1982", ids)
        self.assertIn("sasportas_twelve_houses_1985", ids)

    def test_rechaza_real(self):
        with self.assertRaises(ValueError):
            mod.preparar(mod.WORK_DIR_REAL)


class TestSimuladoSinRed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t119_sim_")
        mod.preparar(self.tmp)
        # Sembrar secciones con entidad explicita para el juez simulado.
        secc = {
            "seccion": "sol|piscis|planeta_en_signo",
            "titulo": "Arroyo: sol|piscis|planeta_en_signo",
            "texto": "Sun was in Pisces and this gave him strong psychic abilities "
                    "near water throughout his life and work. " * 4,
            "chars": 300,
            "id_libro": "arroyo_astrologia_psicologia_1982",
            "posicion": 0,
            "entidad_id": "sol|piscis|planeta_en_signo",
        }
        with open(os.path.join(self.tmp, "secciones",
                              "arroyo_astrologia_psicologia_1982.jsonl"),
                  "w", encoding="utf-8") as fh:
            fh.write(json.dumps(secc, ensure_ascii=False) + "\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_juez_simulado_no_toca_red(self):
        res = mod.procesar_juez(self.tmp, workers=1, simulado=True)
        self.assertEqual(res["juzgadas"], 1)
        self.assertEqual(res["error"], 0)
        # simulado devuelve sin_interes -> sin evidencias
        self.assertEqual(res["evidencias"], 0)

    def test_simulado_juez_json(self):
        j = json.loads(mod._simulado_juez_astro("s", "u"))
        self.assertEqual(j["tipo"], "relleno")
        self.assertEqual(j["entidades"], [])


class TestConstruirClienteEndpoints(unittest.TestCase):
    """T143: nodo1 y nodo2 permitidos (autorizado el 23/10); solo esos dos hosts."""

    def test_acepta_nodo1(self):
        cli = mod.construir_cliente_endpoints("http://10.0.0.3:8000/v1")
        self.assertEqual(cli._cliente.endpoints, ["http://10.0.0.3:8000/v1"])

    def test_acepta_nodo2(self):
        cli = mod.construir_cliente_endpoints("http://10.0.0.4:8000/v1")
        self.assertEqual(cli._cliente.endpoints, ["http://10.0.0.4:8000/v1"])

    def test_acepta_ambos_round_robin(self):
        cli = mod.construir_cliente_endpoints(
            "http://10.0.0.3:8000/v1,http://10.0.0.4:8000/v1")
        self.assertEqual(
            cli._cliente.endpoints,
            ["http://10.0.0.3:8000/v1", "http://10.0.0.4:8000/v1"])

    def test_vacio_reparte_ambos(self):
        cli = mod.construir_cliente_endpoints("")
        self.assertEqual(
            set(cli._cliente.endpoints),
            {"http://10.0.0.3:8000/v1", "http://10.0.0.4:8000/v1"})

    def test_rechaza_host_ajeno(self):
        with self.assertRaises(ValueError):
            mod.construir_cliente_endpoints("http://example.com/v1")


if __name__ == "__main__":
    unittest.main()
