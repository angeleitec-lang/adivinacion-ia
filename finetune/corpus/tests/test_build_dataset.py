"""Tests de limpieza y filtros de build_dataset (track T3)."""
import json
import os
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_dataset as bd
import build_scrapy_dataset as bsd


class LimpiezaResiduosWikipedia(unittest.TestCase):
    """T3.1: clean_body elimina residuos de citas y edición de Wikipedia."""

    def test_cita_escapada_con_url(self):
        texto = ("dura 25\xa0776 años[\\[1\\]]"
                 "(https://es.wikipedia.org/wiki/A%C3%B1o_plat%C3%B3nico#cite_note-grados-1)")
        limpio = bd.clean_body(texto)
        self.assertNotIn("cite_note", limpio)
        self.assertNotIn("[1]", limpio)
        self.assertIn("dura 25", limpio)

    def test_cita_escapada_punteada(self):
        texto = ". [\\[2\\]](https://es.wikipedia.org/wiki/A%C3%B1o_plat%C3%B3nico#cite_note-2)"
        limpio = bd.clean_body(texto)
        self.assertNotIn("cite_note", limpio)
        self.assertNotIn("[2]", limpio)

    def test_editar_con_parentesis_en_url(self):
        texto = ('[editar](https://es.wikipedia.org/w/index.php?title=Bastos_(naipe)'
                 '&action=edit&section=3 "Editar sección: Baraja española")')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)
        self.assertNotIn("Editar sección", limpio)

    def test_editar_con_corchetes_externos(self):
        texto = ('\\[[editar](https://es.wikipedia.org/w/index.php?title=Oros_(naipe)'
                 '&action=edit&section=3 "Editar sección: Baraja española")\\')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)
        self.assertNotIn("editar", limpio.lower())

    def test_crea_el_articulo_residuo(self):
        texto = ('**[Crea el artículo](https://es.wikipedia.org/w/index.php'
                '?title=Aspecto_(astrolog%C3%ADa)&action=edit)')
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)

    def test_residuo_sueltos_action_edit(self):
        texto = '&action=edit&section=4 "Editar sección: Baraja italiana")'
        limpio = bd.clean_body(texto)
        self.assertNotIn("action=edit", limpio)

    def test_enlace_normal_se_convierte_a_texto(self):
        texto = ("válido con [un enlace](https://example.com/pagina) y "
                "[\\[3\\]](http://x#cite_note-3) fin.")
        limpio = bd.clean_body(texto)
        self.assertIn("un enlace", limpio)
        self.assertNotIn("http", limpio)
        self.assertNotIn("cite_note", limpio)

    def test_lineas_solo_simbolos_se_eliminan(self):
        self.assertEqual(bd.clean_body("*    **"), "")
        self.assertEqual(bd.clean_body("_ _ _"), "")
        self.assertEqual(bd.clean_body("> >"), "")

    def test_texto_legitimo_se_conserva(self):
        texto = "Frase normal que se conserva intacta."
        self.assertEqual(bd.clean_body(texto), texto)

    def test_cita_numerica_suelta(self):
        texto = "Cita suelta [5] y [\\[7\\]] aquí."
        limpio = bd.clean_body(texto)
        self.assertNotIn("[5]", limpio)
        self.assertNotIn("[7]", limpio)
        self.assertIn("Cita suelta", limpio)
        self.assertIn("aquí", limpio)


class FiltroDeDominio(unittest.TestCase):
    """T3.2: términos fuertes y débiles; los débiles solos no bastan."""

    def test_domain_hits_sigue_devolviendo_set(self):
        self.assertIsInstance(bd.domain_hits("tarot y sol"), set)

    def test_domain_score_devuelve_tupla(self):
        fuertes, debiles = bd.domain_score("tarot y sol")
        self.assertEqual((fuertes, debiles), (1, 1))

    def test_abuela_no_relevante(self):
        frase = ("El sol sale por la casa de mi abuela; leo una carta "
                "mientras mi mano toca la luna del espejo.")
        self.assertFalse(bd.is_relevant("", frase, "", 2))

    def test_debiles_solos_no_bastan(self):
        self.assertFalse(bd.is_relevant("", "sol luna casa mano leo", "", 2))

    def test_tarot_relevante(self):
        frag = ("La Torre invertida es un arcano mayor que, en esta tirada "
               "del tarot, anuncia un cambio brusco tras el cinco de copas.")
        self.assertTrue(bd.is_relevant("", frag, "", 2))

    def test_carta_astral_relevante(self):
        frag = "Sol en Aries en casa 7, trígono a Júpiter."
        self.assertTrue(bd.is_relevant("", frag, "", 2))

    def test_psicometria_serie_tv_no_relevante(self):
        frag = ("Psico es una serie de televisión estadounidense de suspense "
               "estrenada en 2009, protagonizada por una detective que "
               "resuelve crímenes en una pequeña ciudad.")
        self.assertFalse(bd.is_relevant("", frag, "", 2))

    def test_min_terms_cero_desactiva(self):
        self.assertTrue(bd.is_relevant("", "texto sin nada del dominio", "", 0))

    def test_oposicion_sola_no_es_fuerte(self):
        self.assertEqual(bd.domain_score("oposición"), (0, 0))
        self.assertFalse(bd.is_relevant("", "oposición", "", 2))

    def test_oposicion_con_otro_fuerte_si_cuenta(self):
        self.assertEqual(bd.domain_score("oposición y trígono"), (2, 0))


class DensidadDeTerminosFuertes(unittest.TestCase):
    """T12.2: min_density exige fuertes por 1.000 palabras de cuerpo."""

    def test_sin_palabras_no_divide_por_cero(self):
        self.assertEqual(bd.density_fuertes(""), 0.0)
        self.assertEqual(bd.density_fuertes("   \n\t "), 0.0)
        self.assertFalse(bd.is_relevant("", "", "", 2, 1.0))

    def test_oposicion_sola_no_aporta_densidad(self):
        self.assertEqual(bd.density_fuertes("oposición tras oposición siempre"), 0.0)

    def test_texto_largo_con_dos_menciones_sueeltas_rechazado(self):
        cuerpo = ("El tarot aparece una sola vez aqui. "
                 + "palabras de relleno neutro para alargar el texto " * 1000
                 + " Y numerologia al final del documento.")
        self.assertTrue(bd.is_relevant("", cuerpo, "", 2))
        self.assertLess(bd.density_fuertes(cuerpo), 2.0)
        self.assertFalse(bd.is_relevant("", cuerpo, "", 2, 2.0))

    def test_texto_corto_denso_aceptado(self):
        cuerpo = ("El tarot, el arcano mayor y la tirada del oraculo: "
                 "numerologia y astrologia en una lectura completa.")
        self.assertGreaterEqual(bd.density_fuertes(cuerpo), 2.0)
        self.assertTrue(bd.is_relevant("", cuerpo, "", 2, 2.0))

    def test_por_defecto_no_cambia_el_comportamiento(self):
        casos = [
            ("", "El tarot y la numerologia guian la tirada.", "", 2),
            ("", "sol luna casa mano leo", "", 2),
            ("", "", "", 0),
        ]
        for topic, cuerpo, doc, mt in casos:
            with self.subTest(cuerpo=cuerpo[:20]):
                self.assertEqual(bd.is_relevant(topic, cuerpo, doc, mt),
                                 bd.is_relevant(topic, cuerpo, doc, mt, 0.0))

    def test_build_pairs_propaga_min_density(self):
        md_denso = ("## El tarot de Marsella\nEl tarot de Marsella usa "
                   "veintidos arcanos mayores y una tirada clasica del "
                   "oraculo para leer el destino con claridad y rigor.")
        relleno = ("bajo el sol y la luna, cada signo y cada planeta marcaba "
                   "el ritmo de la casa y del pueblo de la region ")
        md_disperso = ("## Historia del cielo\n" + relleno * 35
                      + "Solo de paso se menciona la astrologia.")
        rng = __import__("random").Random(3)
        self.assertGreaterEqual(
            len(bd.build_pairs("a.md", md_denso, rng, 10, 4000, 2)), 1)
        self.assertGreaterEqual(
            len(bd.build_pairs("b.md", md_disperso, rng, 10, 4000, 2)), 1)
        self.assertGreaterEqual(
            len(bd.build_pairs("a.md", md_denso, rng, 10, 4000, 2, 2.0)), 1)
        self.assertEqual(
            len(bd.build_pairs("b.md", md_disperso, rng, 10, 4000, 2, 2.0)), 0)

    def _raw_disperso(self, tmp):
        raw = bd.Path(tmp) / "raw"
        raw.mkdir()
        relleno = ("bajo el sol y la luna, cada signo y cada planeta marcaba "
                   "el ritmo de la casa y del pueblo de la region ")
        (raw / "mundo-musulman-astrologia.md").write_text(
            "# Mundo musulman\n\n" + relleno * 35
            + "Solo de paso se menciona la astrologia.",
            encoding="utf-8")
        return str(raw)

    def test_cli_min_density_en_build_dataset(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            raw = self._raw_disperso(tmp)
            buf_sin = io.StringIO()
            with contextlib.redirect_stdout(buf_sin):
                rc_sin = bd.main(["--raw", raw, "--out", tmp, "--dry-run"])
            buf_con = io.StringIO()
            with contextlib.redirect_stdout(buf_con):
                rc_con = bd.main(["--raw", raw, "--out", tmp, "--dry-run",
                                 "--min-density", "2"])
        self.assertEqual(rc_sin, 0)
        self.assertEqual(rc_con, 0)
        self.assertIn("Documentos con pares: 1", buf_sin.getvalue())
        self.assertIn("Documentos con pares: 0", buf_con.getvalue())

    def test_cli_min_density_en_build_scrapy_dataset(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            raw = self._raw_disperso(tmp)
            buf_sin = io.StringIO()
            with contextlib.redirect_stdout(buf_sin):
                rc_sin = bsd.main(["--raw", raw, "--out", tmp, "--dry-run"])
            buf_con = io.StringIO()
            with contextlib.redirect_stdout(buf_con):
                rc_con = bsd.main(["--raw", raw, "--out", tmp, "--dry-run",
                                  "--min-density", "2"])
        self.assertEqual(rc_sin, 0)
        self.assertEqual(rc_con, 0)
        self.assertIn("pares nuevos: 1", buf_sin.getvalue())
        self.assertIn("pares nuevos: 0", buf_con.getvalue())


class EncabezadosMalos(unittest.TestCase):
    """T3.3: se comprueba cada segmento de la ruta, no solo el inicio."""

    def test_libro_referencias_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Libro > Referencias"))

    def test_segmento_malo_al_final_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Baraja española > Referencias"))

    def test_vase_tambien_al_final_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Tarot > Véase también"))

    def test_arcanos_loco_aceptado(self):
        self.assertFalse(bd.is_bad_topic("Los arcanos mayores > El Loco"))

    def test_curso_inmersivo_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Curso inmersivo"))

    def test_preguntas_frecuentes_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Preguntas frecuentes"))

    def test_sobre_la_autora_rechazado(self):
        self.assertTrue(bd.is_bad_topic("Sobre la autora"))

    def test_buen_tema_unico_aceptado(self):
        self.assertFalse(bd.is_bad_topic("El Mago"))


class Idioma(unittest.TestCase):
    """T3.8: es_puro descarta portugués e italiano."""

    def test_espanol_normal_es_puro(self):
        texto = ("El tarot es una herramienta de autoconocimiento que usamos "
                 "para reflexionar sobre el pasado, el presente y el futuro, "
                 "pero sin perder de vista las decisiones que tomamos cada día.")
        self.assertTrue(bd.es_puro(texto))

    def test_portugues_fliptarot_no_es_puro(self):
        texto = ("Perguntas mais indicadas para esta tiragem. Uma situação "
                "complexa que precisa de um mapa completo de influências. Cada "
                "carta deve ser lida pela função da posição em que caiu. A "
                "mesma carta muda de foco e nuance conforme a casa que ocupa, "
                "porque a atmosfera geral, a condição central o punto de "
                "partida que atualmente cobre a pergunta.")
        self.assertFalse(bd.es_puro(texto))

    def test_italiano_no_es_puro(self):
        texto = ("I pianeti sono i verbi del cielo e le case sono i "
                "sostantivi. La carta astrale è una mappa della vita "
                "quotidiana, dove ogni aspetto racconta una storia.")
        self.assertFalse(bd.es_puro(texto))

    def test_espanol_con_cita_ingles_latin_es_puro(self):
        texto = ("El oráculo es un espejo del alma. Como decía el viejo adagio "
                "«carpe diem», y nosotros añadimos que el momento presente "
                "guarda la clave de lo que vendrá, pero sin obsesionarse.")
        self.assertTrue(bd.es_puro(texto))


class BotonesComerciales(unittest.TestCase):
    """T3.9: clean_body elimina botones de tienda y restos de enlace."""

    def test_boton_ver_productos_bindi(self):
        texto = ("Amuletos, velas y minerales que cierran el paso a la mala "
                 "energía_Ver productos →_](https://bindi-online.com/"
                 "etiqueta-producto/proteccion/)")
        limpio = bd.clean_body(texto)
        self.assertNotIn("Ver productos", limpio)
        self.assertNotIn("bindi-online", limpio)
        self.assertNotIn("](", limpio)
        self.assertIn("energía", limpio)

    def test_ver_mas_con_flecha(self):
        limpio = bd.clean_body("Texto útil Ver más → resto")
        self.assertNotIn("Ver más", limpio)
        self.assertNotIn("→", limpio)

    def test_comprar_ahora(self):
        limpio = bd.clean_body("Un amuleto Comprar ahora mismo")
        self.assertNotIn("Comprar ahora", limpio)

    def test_leer_mas_guillemet(self):
        limpio = bd.clean_body("Resumen breve Leer más » y seguimos")
        self.assertNotIn("Leer más", limpio)
        self.assertNotIn("»", limpio)

    def test_suscribete(self):
        limpio = bd.clean_body("*Suscríbete* para recibir más tiradas")
        self.assertNotIn("Suscríbete", limpio)

    def test_asteriscos_alrededor(self):
        limpio = bd.clean_body("**Ver productos** y nada más")
        self.assertNotIn("Ver productos", limpio)

    def test_texto_normal_no_se_toca(self):
        texto = "La verde luna ilumina el tarot."
        self.assertEqual(bd.clean_body(texto), texto)

    def test_elimina_frases_comerciales_completas(self):
        texto = ("Esta carta habla de transformación y renacimiento. "
                 "_Ver productos →_](https://bindi-online.com/"
                 "etiqueta-producto/despertar) Añadir al carrito. "
                 "Suscríbete a nuestra newsletter. Leer más »")
        self.assertEqual(
            bd.clean_body(texto),
            "Esta carta habla de transformación y renacimiento.")

    def test_frase_sin_reclamos_no_cambia(self):
        texto = "La carta del Sol anuncia claridad y éxito."
        self.assertEqual(bd.clean_body(texto), texto)

    def test_elimina_oferta_con_posesivo(self):
        texto = ("El arcano invita a mirar dentro. Compra nuestro pack de tarot "
                 "por solo 19,99 euros hoy.")
        self.assertEqual(
            bd.clean_body(texto),
            "El arcano invita a mirar dentro.")

    def test_elimina_oferta_con_precio(self):
        casos = [
            "Compra tu mazo de Rider-Waite por 12 €.",
            "Adquiere un amuleto por 9,95 euros.",
            "Consigue tu vela por 8 USD.",
            "Pide tu tirada por 5 $.",
        ]
        for texto in casos:
            with self.subTest(texto=texto):
                self.assertEqual(bd.clean_body(texto), "")

    def test_elimina_titular_lee_tambien(self):
        texto = "Texto útil sobre la tirada. Lee también: Cómo leer el tarot en pareja."
        self.assertEqual(bd.clean_body(texto), "Texto útil sobre la tirada.")

    def test_elimina_titulares_enlazados(self):
        for titular in ("Lee más", "Te puede interesar", "Artículos relacionados"):
            with self.subTest(titular=titular):
                texto = "Texto útil. " + titular + ": Otra lectura recomendada."
                self.assertEqual(bd.clean_body(texto), "Texto útil.")

    def test_conserva_compra_y_venta(self):
        texto = "Compra y venta de bienes: la casa 2 rige las posesiones."
        self.assertEqual(bd.clean_body(texto), texto)

    def test_conserva_comprar_con_prudencia(self):
        texto = ("Comprar con prudencia es un consejo de Saturno. "
                 "La carta pide paciencia.")
        self.assertEqual(bd.clean_body(texto), texto)

    def test_conserva_precio_sin_verbo_de_compra(self):
        texto = ("La carta del Diablo cuesta 5 euros de tributo en la leyenda. "
                 "Es un símbolo de apego.")
        self.assertEqual(bd.clean_body(texto), texto)

    def test_conserva_lee_tambien_sin_dos_puntos(self):
        texto = "Lee también sin dos puntos ni texto detrás."
        self.assertEqual(bd.clean_body(texto), texto)


class Introduccion(unittest.TestCase):
    """T3.4: se conserva el texto previo al primer encabezado."""

    def test_intro_mas_seccion_dos_secciones(self):
        md = ("Introducción al tarot con suficiente longitud para contar algo.\n\n"
              "## Sección real\nContenido de la sección real aquí.")
        secs = bd.split_sections(md, "tarot_guia")
        self.assertEqual(len(secs), 2)
        self.assertEqual(secs[0][0], bd.humanize("tarot_guia"))
        self.assertIn("Introducción", secs[0][1])

    def test_sin_intro_solo_secciones(self):
        md = "## Una\ncuerpo uno\n\n## Dos\ncuerpo dos"
        secs = bd.split_sections(md, "x")
        self.assertEqual(len(secs), 2)
        self.assertEqual(secs[0][0], "Una")

    def test_sin_encabezados(self):
        secs = bd.split_sections("solo texto sin encabezados", "doc")
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0][0], "")

    def test_intro_vacia_no_anade_seccion(self):
        md = "# Título\ncuerpo bajo el título"
        secs = bd.split_sections(md, "doc")
        self.assertEqual(len(secs), 1)


class LoadBlocked(unittest.TestCase):
    """T3.5: load_blocked devuelve rutas reales y filtra por colisión."""

    def _manifest(self, entries):
        fh = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(entries, fh)
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        return bd.Path(fh.name)

    def test_bloqueada_se_convierte_en_ruta(self):
        path = self._manifest([
            {"url": "https://es.wikipedia.org/wiki/Bastos_(naipe)",
             "estado": "bloqueado"},
            {"url": "https://ok.com/guia", "estado": "ok"},
        ])
        blocked = bd.load_blocked(path)
        self.assertIn("es.wikipedia.org/wiki_Bastos_naipe.md", blocked)
        self.assertNotIn("ok.com/guia.md", blocked)

    def test_is_blocked_rel_coincide(self):
        blocked = {"es.wikipedia.org/wiki_Bastos_naipe.md"}
        self.assertTrue(bd.is_blocked_rel(
            "es.wikipedia.org/wiki_Bastos_naipe.md", blocked))

    def test_is_blocked_rel_con_colision(self):
        blocked = {"es.wikipedia.org/wiki_Bastos_naipe.md"}
        self.assertTrue(bd.is_blocked_rel(
            "es.wikipedia.org/wiki_Bastos_naipe_ab12.md", blocked))

    def test_is_blocked_rel_no_coincide(self):
        blocked = {"es.wikipedia.org/wiki_Bastos_naipe.md"}
        self.assertFalse(bd.is_blocked_rel("ok.com/guia.md", blocked))

    def test_estado_fallo_tambien_bloquea(self):
        path = self._manifest([
            {"url": "https://x.com/pagina", "estado": "fallo"},
        ])
        blocked = bd.load_blocked(path)
        self.assertIn("x.com/pagina.md", blocked)

    def test_license_filter_strict_sin_modulo_devuelve_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            with unittest.mock.patch.dict(sys.modules, {"license_filter": None}):
                rc = bd.main(["--raw", tmp, "--dry-run",
                             "--license-filter", "strict"])
        self.assertEqual(rc, 2)


class TemasLegibles(unittest.TestCase):
    """T3.6: tema_legible y plantillas de pregunta."""

    def test_usa_ultimo_segmento(self):
        t = bd.tema_legible("Tarot > Cartas del tarot de Marsella", "x")
        self.assertNotIn(" > ", t)
        self.assertEqual(t, "Cartas del tarot de Marsella")

    def test_corto_anade_primero(self):
        t = bd.tema_legible("Tarot > Sí", "x")
        self.assertEqual(t, "Sí (Tarot)")

    def test_generico_anade_primero(self):
        t = bd.tema_legible("Numerología > Inicio", "x")
        self.assertEqual(t, "Inicio (Numerología)")

    def test_igualmente_primo_y_ultimo_no_repite(self):
        t = bd.tema_legible("Tarot > Tarot", "x")
        self.assertEqual(t, "Tarot")

    def test_sin_puntuacion_final(self):
        t = bd.tema_legible("Guía > ¿Qué es el tarot?", "x")
        self.assertNotIn("?", t)
        self.assertEqual(t, "Qué es el tarot")

    def test_al_menos_doce_plantillas(self):
        self.assertGreaterEqual(len(bd.INSTRUCTION_TEMPLATES), 12)

    def test_todas_las_plantillas_tienen_topic(self):
        for tpl in bd.INSTRUCTION_TEMPLATES:
            self.assertIn("{topic}", tpl)

    def test_prompt_final_sin_ruta_ni_doble_puntuacion(self):
        md = ("# Tarot\n\n## Los arcanos mayores\n"
              "El tarot de Marsella contiene veintidos arcanos mayores que se "
              "usan en la adivinacion y la lectura del futuro con las cartas.")
        rng = __import__("random").Random(7)
        pairs = bd.build_pairs("guia_tarot", md, rng, 10, 4000, 0)
        self.assertGreaterEqual(len(pairs), 1)
        for p in pairs:
            human = p["conversations"][1]["value"]
            self.assertNotIn(" > ", human)
            self.assertNotIn("..", human)
            self.assertNotIn("?.", human)

    def test_reproducible_con_semilla(self):
        tpl_a = [__import__("random").Random(1).choice(bd.INSTRUCTION_TEMPLATES)
                for _ in range(3)]
        tpl_b = [__import__("random").Random(1).choice(bd.INSTRUCTION_TEMPLATES)
                for _ in range(3)]
        self.assertEqual(tpl_a, tpl_b)


def _mk_pair(prompt, answer):
    return {"conversations": [
        {"from": "system", "value": "s"},
        {"from": "human", "value": prompt},
        {"from": "gpt", "value": answer},
    ]}


class ScrapyDedupe(unittest.TestCase):
    """T3.7: dedupe por prompt ademas de respuesta y pares extranjeros cortos."""

    def test_duplicado_por_prompt(self):
        pairs = [_mk_pair("Háblame del tarot.", "respuesta uno"),
                _mk_pair("Háblame del tarot.", "respuesta dos distinta")]
        kept, dup = bsd.dedupe_new(pairs, set())
        self.assertEqual(len(kept), 1)
        self.assertEqual(dup, 1)

    def test_mismo_prompt_normalizado(self):
        pairs = [_mk_pair("Háblame   del tarot", "a"),
                _mk_pair("háblame del TAROT", "b")]
        kept, dup = bsd.dedupe_new(pairs, set())
        self.assertEqual(len(kept), 1)
        self.assertEqual(dup, 1)

    def test_respuesta_ya_integrada_se_descarta(self):
        p = _mk_pair("pregunta nueva", "respuesta ya usada")
        existing = {bsd.text_hash("respuesta ya usada")}
        kept, dup = bsd.dedupe_new([p], existing)
        self.assertEqual(kept, [])
        self.assertEqual(dup, 1)

    def test_pares_distintos_se_conservan(self):
        pairs = [_mk_pair("uno", "resp a"), _mk_pair("dos", "resp b")]
        kept, dup = bsd.dedupe_new(pairs, set())
        self.assertEqual(len(kept), 2)
        self.assertEqual(dup, 0)

    def test_extranjero_corto(self):
        self.assertTrue(bsd.is_foreign_short("en", "x" * 100))
        self.assertFalse(bsd.is_foreign_short("es", "x" * 100))
        self.assertFalse(bsd.is_foreign_short("en", "x" * 2000))


if __name__ == "__main__":
    unittest.main()
