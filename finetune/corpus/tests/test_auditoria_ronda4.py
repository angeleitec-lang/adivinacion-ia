"""Auditoría ronda 4 (T63): casos adversos sobre la tubería de fase 0/1.

Los defectos confirmados por ejecución se documentan como expectedFailure
(el test afirma el comportamiento CORRECTO, que aún no ocurre); los
comportamientos verificados como sanos se afirman directamente.
Nada de esto toca red ni LLM. Ver docs/AUDITORIA_RONDA4.md.
"""
import datetime
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cartas
import clasicos_pd_a_evidencias
import cobertura
import diagnostico_tarot_libros
import juez
import limpiar_evidencias_libros
import salud_datos


class TestEvaluarNumerologia(unittest.TestCase):
    """evaluar_modelo: mínima de 3 etiquetas numerales."""

    def test_doble_cuenta_ano_personal(self):
        """B1 (T63) arreglado en T67: cada etiqueta distintiva cuenta una vez."""
        import evaluar_modelo
        fallos = []
        evaluar_modelo._check_numerologia(
            {"calculos": {}},
            "El camino de vida revela cosas y el año personal también.",
            fallos)
        menos = [f for f in fallos if f["motivo"].startswith("Menciona menos")]
        self.assertEqual(len(menos), 1,
                         "solo hay 2 etiquetas reales: debe exigir 3")

    def test_una_sola_etiqueta_si_falla(self):
        import evaluar_modelo
        fallos = []
        evaluar_modelo._check_numerologia(
            {"calculos": {}}, "Solo el año personal importa.", fallos)
        menos = [f for f in fallos if f["motivo"].startswith("Menciona menos")]
        self.assertEqual(len(menos), 1)


class TestLimpiarEvidenciasTitulosES(unittest.TestCase):
    """limpiar_evidencias_libros/diagnostico: títulos de mayores en español.

    Arreglado en T67 (A2): `clasificar_titulo` y `MAYOR_PROPIO` reconocen
    también los nombres españoles (norm, sin tildes), no solo los ingleses.
    """

    def _filtro(self, titulo):
        seccion = {"id_libro": "l1", "seccion": 1, "titulo": titulo,
                   "texto": "x" * 60}
        evidencia = {"entidad_id": "tarot-mayor-18",
                     "hash_seccion": juez.hash_seccion(seccion),
                     "faceta": "significado_general"}
        return limpiar_evidencias_libros.propuesta_filtro(
            [evidencia], [seccion])

    def test_titulo_ingles_si_quita(self):
        resultado = self._filtro("Death")
        self.assertEqual(resultado["n_quitadas"], 1)

    def test_titulo_espanol_debe_quitar(self):
        resultado = self._filtro("La Muerte")
        self.assertEqual(
            resultado["n_quitadas"], 1,
            "el filtro debe retirar evidencias de La Estrella en una sección "
            "titulada La Muerte también cuando el título está en español")

    def test_titulo_propio_en_espanol_se_conserva(self):
        resultado = self._filtro("La Estrella")
        self.assertEqual(resultado["n_quitadas"], 0)

    def test_clasificar_titulo_es_otra(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("La Muerte", "moon"),
            "otra")

    def test_clasificar_titulo_es_real(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("La Luna", "moon"),
            "real")

    def test_clasificar_titulo_es_real_variante_token(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("La Estrella", "star"),
            "real")

    def test_clasificar_titulo_menor_espanol_otra(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("Rey de Copas", "sun"),
            "otra")

    def test_clasificar_titulo_regresion_ingles(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("The Moon", "sun"),
            "otra")

    def test_clasificar_titulo_neutro_sigue_neutro(self):
        self.assertEqual(
            diagnostico_tarot_libros.clasificar_titulo("LESSON THREE", "sun"),
            "neutro")


class TestCachJuezEvaluacion(unittest.TestCase):
    """evaluar_modelo: la clave de caché del juez debe depender del caso."""

    class _Cliente:
        def __init__(self):
            self.llamadas = 0

        def chat(self, system, user, **kwargs):
            self.llamadas += 1
            return "4"

    def setUp(self):
        import evaluar_modelo
        self.mod = evaluar_modelo
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.ruta_cache = os.path.join(self.dir, "cache.jsonl")

    def _caso(self, user="pregunta original"):
        return {"id": "ev-tarot-01", "system": "situa", "user": user,
                "familia": "tarot"}

    def _resultado(self):
        return {"id": "ev-tarot-01", "respuesta": "la respuesta del modelo"}

    def test_segunda_pasada_usa_cache(self):
        cliente = self._Cliente()
        self.mod.aplicar_juez([self._caso()], [self._resultado()],
                              cliente=cliente, cache_path=self.ruta_cache)
        self.assertEqual(cliente.llamadas, 1)
        cliente2 = self._Cliente()
        self.mod.aplicar_juez([self._caso()], [self._resultado()],
                              cliente=cliente2, cache_path=self.ruta_cache)
        self.assertEqual(cliente2.llamadas, 0)

    def test_misma_respuesta_otro_caso_no_reutiliza_cache(self):
        cliente = self._Cliente()
        self.mod.aplicar_juez([self._caso()], [self._resultado()],
                              cliente=cliente, cache_path=self.ruta_cache)
        cliente2 = self._Cliente()
        res2 = self._resultado()
        self.mod.aplicar_juez([self._caso(user="otra pregunta"), ], [res2],
                              cliente=cliente2, cache_path=self.ruta_cache)
        self.assertEqual(
            cliente2.llamadas, 1,
            "A4 (T63): cambiar el caso sin cambiar la respuesta no debe "
            "revalidar la puntuacion cacheada")


class TestJuezValidadores(unittest.TestCase):
    """juez.parsear_respuesta: `calidad` entera 1-5 obligatoria.

    B2 (T63) arreglado en T67: cadenas y flotantes no enteros se rechazan.
    """

    def setUp(self):
        self.familia = "tarot"
        self.faceta = cobertura.FACETAS_POR_FAMILIA[self.familia][0]
        self.crudo = {"entidad_id": "tarot-mayor-18", "faceta": self.faceta,
                      "familia": self.familia,
                      "texto": "brilla la luna plateada en la carta"}

    def _responder(self, calidad):
        texto = json.dumps({
            "tipo": "conocimiento",
            "entidades": [{"entidad_id": self.crudo["entidad_id"],
                           "limpias": [{"faceta": self.faceta,
                                        "texto_paraphrase":
                                            "resplandece la luna"}]}],
            "calidad": calidad})
        return juez.parsear_respuesta(texto, [self.crudo])

    def _calidad(self, salida):
        juicio = salida["juicio"] if isinstance(salida, dict) and "juicio" in salida else salida
        return juicio["calidad"]

    def test_calidad_cadena_se_rechaza(self):
        self.assertRaises(ValueError, self._responder, "4")

    def test_calidad_flotante_no_entera_se_rechaza(self):
        self.assertRaises(ValueError, self._responder, 3.7)

    def test_calidad_entera_valida_se_acepta(self):
        self.assertEqual(self._calidad(self._responder(4)), 4)

    def test_calidad_flotante_entero_4_0_se_acepta(self):
        self.assertEqual(self._calidad(self._responder(4.0)), 4)

    def test_calidad_bool_se_rechaza(self):
        self.assertRaises(ValueError, self._responder, True)

    def test_fuera_de_rango_si_rechaza(self):
        self.assertRaises(ValueError, self._responder, 7)


class TestCartas(unittest.TestCase):
    """cartas: normalización unicode y filtrado contextual de ambiguos."""

    def test_norm_iguala_nfc_y_nfd(self):
        nfc = unicodedata.normalize("NFC", "El Niño de La Muerte")
        nfd = unicodedata.normalize("NFD", "El Niño de La Muerte")
        self.assertEqual(cartas.norm(nfc), cartas.norm(nfd))

    def test_prosa_sin_contexto_no_extrae(self):
        prosa = ("En el mundo todo cambia; la fuerza de la naturaleza gana, "
                 "y la muerte llega para todos bajo el sol.")
        self.assertEqual(cartas.extraer_cartas(prosa, mazo="tarot"), [])

    def test_prosa_sin_contextual_saca_todo(self):
        prosa = ("En el mundo todo cambia; la fuerza de la naturaleza gana, "
                 "y la muerte llega para todos bajo el sol.")
        menciones = cartas.extraer_cartas(prosa, mazo="tarot",
                                          contextual=False)
        self.assertGreaterEqual(len(menciones), 4)

    def test_orientacion_hace_aceptable(self):
        menciones = cartas.extraer_cartas("La Muerte invertida",
                                          mazo="tarot")
        self.assertEqual(len(menciones), 1)
        self.assertEqual(menciones[0]["carta"]["id"], "tarot-mayor-14")
        self.assertEqual(menciones[0]["orientacion"], "invertida")


class TestPurgarErroresJuez(unittest.TestCase):
    """clasicos_pd: purgar_errores_juez reescribe sin copia de seguridad."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        ev_dir = os.path.join(self.dir, "evidencias")
        os.makedirs(ev_dir)
        bueno = {"hash": "h1", "fuente_id": "f1", "titulo": "t",
                 "candidatos": [], "juicio": {"tipo": "conocimiento"}}
        malo = {"hash": "h2", "fuente_id": "f1", "titulo": "t",
                "candidatos": [], "juicio": {"tipo": "error"}}
        with open(os.path.join(ev_dir, "juicios.jsonl"), "w",
                  encoding="utf-8") as fh:
            for registro in (bueno, malo):
                fh.write(json.dumps(registro) + "\n")

    def test_quita_error_deja_bueno(self):
        quitados = clasicos_pd_a_evidencias.purgar_errores_juez(self.dir)
        self.assertEqual(quitados, 1)
        with open(os.path.join(self.dir, "evidencias", "juicios.jsonl"),
                  encoding="utf-8") as fh:
            lineas = [l for l in fh if l.strip()]
        self.assertEqual(len(lineas), 1)

    def test_deja_copia_previa(self):
        clasicos_pd_a_evidencias.purgar_errores_juez(self.dir)
        respaldo = [n for n in os.listdir(self.dir) +
                    os.listdir(os.path.join(self.dir, "evidencias"))
                    if ".bak" in n]
        self.assertTrue(
            respaldo,
            "A1 (T63): la purga debe dejar copia .bak antes de reescribir")

    def test_sin_errores_no_deja_copia(self):
        bueno = {"hash": "h1", "fuente_id": "f1", "titulo": "t",
                 "candidatos": [], "juicio": {"tipo": "conocimiento"}}
        with open(os.path.join(self.dir, "evidencias", "juicios.jsonl"),
                  "w", encoding="utf-8") as fh:
            fh.write(json.dumps(bueno) + "\n")
        ruta_respaldo = os.path.join(
            self.dir, "evidencias", "juicios.jsonl.bak-" +
            datetime.datetime.now().strftime("%Y%m%d"))
        self.assertEqual(
            clasicos_pd_a_evidencias.purgar_errores_juez(self.dir), 0)
        self.assertFalse(os.path.exists(ruta_respaldo))

    def test_copia_no_se_sobrescribe_el_mismo_dia(self):
        purga = clasicos_pd_a_evidencias.purgar_errores_juez
        ruta = os.path.join(self.dir, "evidencias", "juicios.jsonl")
        self.assertEqual(purga(self.dir), 1)
        baks = [n for n in os.listdir(os.path.join(self.dir, "evidencias"))
                if ".bak" in n]
        self.assertEqual(len(baks), 1)
        with open(os.path.join(self.dir, "evidencias", baks[0]),
                  encoding="utf-8") as fh:
            self.assertEqual(len([l for l in fh if l.strip()]), 2)
        malo = {"hash": "h3", "fuente_id": "f1", "titulo": "t",
                "candidatos": [], "juicio": {"tipo": "error"}}
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(malo) + "\n")
        self.assertEqual(purga(self.dir), 1)
        self.assertEqual(len([n for n in
                              os.listdir(os.path.join(self.dir, "evidencias"))
                              if ".bak" in n]), 1)
        with open(os.path.join(self.dir, "evidencias", baks[0]),
                  encoding="utf-8") as fh:
            self.assertEqual(len([l for l in fh if l.strip()]), 2)


class TestSaludDatosExclusiones(unittest.TestCase):
    """salud_datos: el patrón de exclusión .bak es demasiado amplio."""

    def test_excluye_residuos_reales(self):
        self.assertTrue(salud_datos._es_excluido("evidencias.jsonl.bak-1"))
        self.assertTrue(salud_datos._es_excluido("x.truncada-20261001"))

    @unittest.expectedFailure
    def test_no_deberia_excluir_nombres_con_bak(self):
        self.assertFalse(
            salud_datos._es_excluido("naipes.bakery-ventas.jsonl"),
            "DEFECTO B6: cualquier nombre que contenga '.bak' se oculta al "
            "descubrimiento, aunque no sea una copia de seguridad")

    def test_repara_tras_copia(self):
        dir_ = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dir_)
        ruta = os.path.join(dir_, "afirmaciones.jsonl")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"entidad_id": "e", "faceta": "f",
                                 "fuente_id": "s", "dominio": "d",
                                 "periodo": "p", "calidad": 4,
                                 "afirmacion": "a"}) + "\n")
            fh.write('{"entidad_id": "e", "faceta": "f", "fuente')
        acciones = salud_datos.reparar_ficheros([ruta], si=True,
                                                intervalo=0,
                                                comprobar_lsof=False)
        self.assertEqual(acciones[0]["estado"], "reparado")
        with open(ruta, encoding="utf-8") as fh:
            self.assertEqual(len([l for l in fh if l.strip()]), 1)


class TestJuezReanudacionFacetas(unittest.TestCase):
    """juez.procesar_secciones: reanudar completa facetas parcial-escritas.

    Arreglado en T67 (A3): el estado de evidencias se lleva por par
    (entidad, faceta), no solo por hash de sección.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.seccion = {"id_libro": "l1", "seccion": 1, "titulo": "t",
                        "texto": "x" * 60}
        self.h = juez.hash_seccion(self.seccion)
        self.juicio = {"tipo": "conocimiento", "idioma": "es", "calidad": 4,
                       "entidades": [{"entidad_id": "tarot-mayor-18",
                                      "facetas": ["faceta_uno",
                                                  "faceta_dos"]}]}
        self.esperadas = juez.evidencias_de_seccion(
            self.seccion, self.juicio,
            juez.fuente_de_seccion(self.seccion, {}))
        self.assertEqual(len(self.esperadas), 2)
        registro = {"hash": self.h, "fuente_id": "l1", "titulo": "t",
                    "candidatos": ["tarot-mayor-18"], "juicio": self.juicio}
        with open(os.path.join(self.dir, "juicios.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(registro) + "\n")

    def _escribir_ev_parcial(self, hasta):
        with open(os.path.join(self.dir, "evidencias.jsonl"), "w",
                  encoding="utf-8") as fh:
            for linea in self.esperadas[:hasta]:
                fh.write(json.dumps(linea) + "\n")

    def _lineas_ev(self):
        with open(os.path.join(self.dir, "evidencias.jsonl"),
                  encoding="utf-8") as fh:
            return [l for l in fh if l.strip()]

    def _relanzar(self):
        return juez.procesar_secciones([self.seccion], object(), self.dir)

    def test_completa_la_faceta_que_falta(self):
        self._escribir_ev_parcial(1)
        stats = self._relanzar()
        self.assertEqual(stats["reaprovechadas"], 1)
        self.assertEqual(stats["evidencias"], 1)
        self.assertEqual(len(self._lineas_ev()), 2)

    def test_relanzamiento_no_duplica(self):
        self._escribir_ev_parcial(1)
        self._relanzar()
        stats = self._relanzar()
        self.assertEqual(stats["evidencias"], 0)
        self.assertEqual(len(self._lineas_ev()), 2)

    def test_sin_evidencias_genera_todas(self):
        with open(os.path.join(self.dir, "evidencias.jsonl"), "w",
                  encoding="utf-8") as fh:
            fh.write("")
        stats = self._relanzar()
        self.assertEqual(stats["evidencias"], 2)
        self.assertEqual(len(self._lineas_ev()), 2)

    def test_juicio_error_se_reintenta(self):
        """B5 (T63) arreglado en T67: tipo=error no es sección terminada."""
        import llm_client
        seccion = {"id_libro": "l1", "seccion": 2, "titulo": "The Fool",
                   "texto": "the fool card opens the journey of the trump"}
        h = juez.hash_seccion(seccion)
        registro = {"hash": h, "fuente_id": "l1", "titulo": "The Fool",
                    "candidatos": ["tarot-mayor-01"],
                    "juicio": {"tipo": "error", "error": "respuesta_no_parseable"}}
        with open(os.path.join(self.dir, "juicios.jsonl"), "a",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(registro) + "\n")
        llamadas = []

        def simulado(sistema, usuario):
            llamadas.append(usuario)
            return ("```json\n%s\n```" % json.dumps({
                "tipo": "conocimiento", "calidad": 4, "idioma": "en",
                "entidades": [{"entidad_id": "tarot-mayor-01",
                               "facetas": ["significado_general"]}]}))
        cliente = llm_client.LLMClient(simulado=simulado)
        stats = juez.procesar_secciones([seccion], cliente, self.dir,
                                        workers=1)
        self.assertEqual(stats["reaprovechadas"], 0)
        self.assertEqual(stats["juzgadas"], 1)
        self.assertEqual(len(llamadas), 1)
        # Segunda pasada: ya hay juicio bueno, no se vuelve a llamar.
        stats2 = juez.procesar_secciones([seccion], cliente, self.dir,
                                         workers=1)
        self.assertEqual(stats2["reaprovechadas"], 1)
        self.assertEqual(len(llamadas), 1)


class TestEscribirCasosCopia(unittest.TestCase):
    """B3 (T63) arreglado en T67: el conjunto congelado no se destruye."""

    def _caso(self, usuario="pregunta"):
        return {"id": "eval-tarot_1-01", "system": "s", "user": usuario,
                "familia": "tarot_1", "origen": "evaluacion"}

    def test_primera_escritura_sin_copia(self):
        import evaluacion_casos as ec
        with tempfile.TemporaryDirectory() as dir:
            ruta = pathlib.Path(dir) / "casos.jsonl"
            ec.escribir_casos(ruta, [self._caso()])
            residuos = [p.name for p in pathlib.Path(dir).iterdir()
                        if ".bak" in p.name]
            self.assertEqual(residuos, [])

    def test_reescritura_identica_deja_copia(self):
        import evaluacion_casos as ec
        with tempfile.TemporaryDirectory() as dir:
            ruta = pathlib.Path(dir) / "casos.jsonl"
            casos = [self._caso()]
            ec.escribir_casos(ruta, casos)
            ec.escribir_casos(ruta, casos)
            sello = datetime.datetime.now().strftime("%Y%m%d")
            respaldo = pathlib.Path(f"{ruta}.bak-{sello}")
            self.assertTrue(respaldo.exists())
            self.assertEqual(ruta.read_text(encoding="utf-8"),
                             respaldo.read_text(encoding="utf-8"))

    def test_id_con_otro_contenido_aborta_sin_tocar_disco(self):
        import evaluacion_casos as ec
        with tempfile.TemporaryDirectory() as dir:
            ruta = pathlib.Path(dir) / "casos.jsonl"
            ec.escribir_casos(ruta, [self._caso("original")])
            antes = ruta.read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                ec.escribir_casos(ruta, [self._caso("otra semilla")])
            self.assertEqual(ruta.read_text(encoding="utf-8"), antes)


class _ClienteFallo:
    def chat(self, *args, **kwargs):
        raise ConnectionError("sin nodos en el test")


class TestPilotoHuella(unittest.TestCase):
    """B4 (T63) arreglado en T67: reanudación consciente del contenido."""

    def setUp(self):
        import fase1_piloto as fp
        self.fp = fp

    def _tarea(self, ident="tarot-01", usuario="u1"):
        return {"id": ident, "familia": "tarot",
                "prompt_system": "s", "prompt_user": usuario}

    def _piloto_con(self, dir, fila):
        ruta = pathlib.Path(dir) / "piloto.jsonl"
        ruta.write_text(json.dumps(fila, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        return ruta

    def test_misma_tarea_se_omite_sin_aviso(self):
        with tempfile.TemporaryDirectory() as dir:
            t = self._tarea()
            self._piloto_con(dir, {"id": t["id"], "familia": "tarot",
                                   "huella": self.fp._huella(t), "ok": True})
            resumen = self.fp.ejecutar_piloto([t], object(), out_dir=dir)
            self.assertEqual(resumen["omitidos"], 1)
            self.assertEqual(resumen["omitidos_contenido_distinto"], 0)

    def test_id_con_otra_tarea_avisa(self):
        with tempfile.TemporaryDirectory() as dir:
            self._piloto_con(dir, {"id": "tarot-01", "familia": "tarot",
                                   "huella": "0" * 16, "ok": True})
            resumen = self.fp.ejecutar_piloto([self._tarea()], object(),
                                              out_dir=dir)
            self.assertEqual(resumen["omitidos"], 1)
            self.assertEqual(resumen["omitidos_contenido_distinto"], 1)

    def test_registros_viejos_sin_huella_no_avisan(self):
        with tempfile.TemporaryDirectory() as dir:
            self._piloto_con(dir, {"id": "tarot-01", "familia": "tarot",
                                   "ok": True})
            resumen = self.fp.ejecutar_piloto([self._tarea()], object(),
                                              out_dir=dir)
            self.assertEqual(resumen["omitidos_contenido_distinto"], 0)

    def test_errores_no_acumulan_duplicados(self):
        with tempfile.TemporaryDirectory() as dir:
            ruta = pathlib.Path(dir) / "piloto_errores.jsonl"
            lineas = [{"id": "tarot-01", "error": "viejo1"},
                      {"id": "tarot-02", "error": "otro"},
                      {"id": "tarot-01", "error": "viejo2"}]
            ruta.write_text("".join(json.dumps(f) + "\n" for f in lineas),
                            encoding="utf-8")
            self.fp.ejecutar_piloto([self._tarea()], _ClienteFallo(),
                                    out_dir=dir)
            restantes = [json.loads(l) for l in
                         ruta.read_text(encoding="utf-8").splitlines() if l]
            ids = [f["id"] for f in restantes]
            self.assertEqual(sorted(ids), ["tarot-01", "tarot-02"])
            nuevo = [f for f in restantes if f["id"] == "tarot-01"][0]
            self.assertTrue(nuevo["error"].startswith("error_red"))
            copias = [p.name for p in pathlib.Path(dir).iterdir()
                      if "piloto_errores.jsonl.bak-" in p.name]
            self.assertEqual(len(copias), 1)


if __name__ == "__main__":
    unittest.main()
