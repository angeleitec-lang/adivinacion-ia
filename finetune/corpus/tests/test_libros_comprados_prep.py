"""Tests de la preparación de libros de astrología comprados (T118).

Cubren las funciones puras de libros_comprados_prep.py: vocabulario y métricas
(% en vocabulario, palabras pegadas), parseo/división de PGM, detección de
páginas en blanco, rúbricas recurrentes, limpieza de cabeceras/pies, unión de
guiones, marcas de títulos, ensamblado con offsets y detección de cobertura
(casas 1-12 y partes). No ejecutan binarios (pdftotext/tesseract) ni leen los
PDF: las verificaciones de extremo a extremo se hacen al ejecutar la pista.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import libros_comprados_prep as lcp


VOCAB = frozenset({
    "archetypes", "serving", "universal", "principles", "house", "houses", "way",
    "of", "is", "fortune", "teller", "prologue", "division", "time", "space",
    "and", "boundaries", "modern", "science", "psychology", "today", "the",
    "earthly", "things", "must", "be", "known", "loved", "divine", "arche",
    "types", "as", "foo", "are", "energy", "language", "zodiacal", "signs",
})


class TestVocabulario(unittest.TestCase):
    def test_ascii_fold(self):
        self.assertEqual(lcp.ascii_fold("Astrología’s"), "astrologias")
        self.assertEqual(lcp.ascii_fold("naïve"), "naive")

    def test_split_pieces_minimo(self):
        self.assertEqual(lcp.split_vocab_pieces("houseis", VOCAB), ["house", "is"])
        self.assertEqual(lcp.split_vocab_pieces("xyzzy", VOCAB), None)

    def test_is_glued(self):
        self.assertTrue(lcp.is_glued("houseis", VOCAB))
        self.assertTrue(lcp.is_glued("wayof", VOCAB))
        self.assertFalse(lcp.is_glued("serving", VOCAB))   # palabra real
        self.assertFalse(lcp.is_glued("xyzzyq", VOCAB))    # indescomponible
        self.assertFalse(lcp.is_glued("the", VOCAB))       # corta

    def test_quality_metrics(self):
        text = "The house is a way of serving archetypes xyzzyq houseis"
        st = lcp.quality_metrics(text, VOCAB)
        self.assertEqual(st.tokens, 10)
        self.assertEqual(st.in_vocab, 7)  # "a" (1 letra) y "xyzzyq"/"houseis" no cuentan
        self.assertEqual(st.glued, 1)     # solo "houseis" es descomponible
        self.assertFalse(lcp.is_glued("xyzzyq", VOCAB))


class TestPgm(unittest.TestCase):
    def _pgm(self):
        # 4x2: columna 0 y 1 oscuras (0), columna 2-3 claras (255)
        pixels = bytes([0, 0, 255, 255, 0, 0, 255, 255])
        return lcp.build_pgm(pixels, 4, 2)

    def test_parse(self):
        w, h, maxv, off = lcp.parse_pgm(self._pgm())
        self.assertEqual((w, h, maxv), (4, 2, 255))

    def test_split_halves(self):
        left, right = lcp.split_pgm_halves(self._pgm())
        lw, lh, _, lo = lcp.parse_pgm(left)
        rw, rh, _, ro = lcp.parse_pgm(right)
        self.assertEqual((lw, lh), (2, 2))
        self.assertEqual((rw, rh), (2, 2))
        self.assertEqual(left[lo:], bytes([0, 0, 0, 0]))
        self.assertEqual(right[ro:], bytes([255, 255, 255, 255]))

    def test_dark_fraction(self):
        self.assertAlmostEqual(lcp.dark_fraction(self._pgm()), 0.5)
        blanco = lcp.build_pgm(b"\xff" * 8, 4, 2)
        self.assertEqual(lcp.dark_fraction(blanco), 0.0)

    def test_maxval_no_255(self):
        datos = lcp.build_pgm(bytes([0, 100, 200, 255]), 2, 2, maxv=255)
        self.assertAlmostEqual(lcp.dark_fraction(datos), 0.5)


class TestMetricasConfig(unittest.TestCase):
    def test_choice_por_vocab(self):
        table = [{"psm": 3, "pages": 10, "tokens": 100, "vocab_pct": 80.0, "glued": 5},
                 {"psm": 6, "pages": 10, "tokens": 100, "vocab_pct": 85.0, "glued": 2},
                 {"psm": 4, "pages": 10, "tokens": 100, "vocab_pct": 85.0, "glued": 1}]
        chosen = sorted(table, key=lambda r: (-r["vocab_pct"], r["glued"]))[0]["psm"]
        self.assertEqual(chosen, 4)


class TestRunningHeads(unittest.TestCase):
    def test_recurrentes_y_no(self):
        paginas = []
        for i in range(5):
            paginas.append(["26 THE TWELVE HOUSES", f"body unique text {i}", "",
                            f"ending unique {i}"])
        paginas.append(["unique header line", "more body"])
        heads = lcp.collect_running_heads(paginas, min_pages=4)
        self.assertIn("the twelve houses", heads)
        self.assertNotIn("unique header line", heads)
        self.assertNotIn("body unique text 0", heads)

    def test_no_cuenta_numeros_sueltos(self):
        paginas = [["12"], ["12"], ["12"], ["12"], ["12"]]
        self.assertEqual(lcp.collect_running_heads(paginas, min_pages=4), frozenset())


class TestCleanPage(unittest.TestCase):
    HEADS = frozenset({"the twelve houses", "space, time and boundaries",
                       "archetypes & universal principles"})

    def test_cabecera_verso_con_numero(self):
        lines = ["26 THE TWELVE HOUSES", "", "against these divisions of the ecliptic,",
                 "showing what sign each planet happens."]
        cp = lcp.clean_page(lines, self.HEADS)
        self.assertEqual(cp.label, "26")
        self.assertIn("THE TWELVE HOUSES", " ".join(cp.dropped))
        self.assertTrue(cp.lines[0].startswith("against") or cp.lines[0] == "")

    def test_cabecera_recto_numero_final(self):
        lines = ["SPACE, TIME AND BOUNDARIES 27", "", "nature of the sign in which it is placed."]
        cp = lcp.clean_page(lines, self.HEADS)
        self.assertEqual(cp.label, "27")
        self.assertNotIn("SPACE, TIME AND BOUNDARIES 27", cp.lines)

    def test_apertura_capitulo(self):
        lines = ["4", "", "Archetypes & Universal Principles", "",
                 "Earthly things must be known to be loved: divine",
                 "things must be loved to be known.", "", "— Pascal"]
        cp = lcp.clean_page(lines, self.HEADS)
        self.assertTrue(cp.title_page)
        self.assertIsNone(cp.label)
        self.assertIn("4", " ".join(cp.dropped))
        self.assertIn("Archetypes & Universal Principles", cp.lines)

    def test_pagina_larga_no_es_apertura(self):
        body = ["word " * 20 for _ in range(10)]  # >110 palabras
        lines = ["Archetypes & Universal Principles"] + body
        cp = lcp.clean_page(lines, self.HEADS)
        self.assertFalse(cp.title_page)
        self.assertNotIn("Archetypes & Universal Principles", cp.lines)

    def test_part_reconocido(self):
        lines = ["Part I", "", "Astrology and Psychology"]
        cp = lcp.clean_page(lines, frozenset())
        self.assertTrue(cp.title_page)

    def test_pie_numero(self):
        lines = ["primer renglón del cuerpo", "segundo renglón", "84"]
        cp = lcp.clean_page(lines, self.HEADS)
        self.assertEqual(cp.label, "84")
        self.assertNotIn("84", cp.lines)


class TestJoinHyphens(unittest.TestCase):
    def test_union_palabra_real(self):
        out, info = lcp.join_hyphens(["the ser-", "ving of archetypes"], VOCAB)
        self.assertEqual(out, ["the serving of archetypes"])
        self.assertEqual(info["joined"], 1)

    def test_compuesto_conserva_guion(self):
        out, info = lcp.join_hyphens(["a fortune-", "teller and the"], VOCAB)
        self.assertEqual(out, ["a fortune-teller and the"])
        self.assertEqual(info["kept_hyphen"], 1)

    def test_segunda_mayuscula_no_toca(self):
        out, info = lcp.join_hyphens(["algo re-", "Oriented line"], VOCAB)
        self.assertEqual(out, ["algo re-", "Oriented line"])
        self.assertEqual(info["joined"] + info["kept_hyphen"] + info["forced"], 0)

    def test_forzada_minuscula(self):
        out, info = lcp.join_hyphens(["el hiper-", "cal energy"], VOCAB)
        # "hipercal" no está en el VOCAB de prueba y "hiper" tampoco → unión forzada
        self.assertEqual(out, ["el hipercal energy"])
        self.assertEqual(info["forced"], 1)

    def test_no_cruza_párrafos(self):
        out, info = lcp.join_hyphens(["serv-", "", "ing"], VOCAB)
        self.assertEqual(out, ["serv-", "", "ing"])


class TestMarkHeadings(unittest.TestCase):
    HEADS = frozenset({"the twelve houses"})

    def test_apertura_marca_h1(self):
        lines = ["", "Archetypes & Universal Principles", "", "Earthly things"]
        marked = lcp.mark_headings(lines, self.HEADS, title_page=True)
        self.assertEqual(marked[1], "# Archetypes & Universal Principles")

    def test_subtitulo_marca_h2(self):
        lines = ["The planets, each at its own rate.", "", "The Division of Time", "",
                 "The word horoscope comes from the Greek."]
        marked = lcp.mark_headings(lines, self.HEADS, title_page=False)
        self.assertEqual(marked[2], "## The Division of Time")

    def test_linea_de_cuerpo_no_marca(self):
        lines = ["primer renglón largo del párrafo anterior",
                 "Modern Science and Energy patterns continue"]
        marked = lcp.mark_headings(lines, self.HEADS, title_page=False)
        self.assertEqual(marked, lines)

    def test_epigrafe_no_marca(self):
        lines = ["", "Earthly things must be known to be loved: divine",
                 "things must be loved to be known.", "", "— Pascal"]
        marked = lcp.mark_headings(lines, self.HEADS, title_page=False)
        self.assertTrue(all(not l.startswith("#") for l in marked))


class TestBuildDocument(unittest.TestCase):
    def test_offsets(self):
        pages = [{"sheet": 1, "side": "L", "label": "i", "lines": ["alfa", "beta"]},
                 {"sheet": 1, "side": "R", "label": "1", "lines": ["gamma"]}]
        text, records = lcp.build_document(pages)
        self.assertEqual(len(records), 2)
        for rec in records:
            esperado = "\n".join(pages[rec["page_idx"] - 1]["lines"])
            self.assertEqual(text[rec["start"]:rec["end"]], esperado)
        self.assertEqual(records[0]["end"] + 2, records[1]["start"])

    def test_pagina_vacia_se_omite(self):
        pages = [{"sheet": 2, "side": "L", "label": None, "lines": ["", "  "]}]
        text, records = lcp.build_document(pages)
        self.assertEqual(records, [])


class TestCobertura(unittest.TestCase):
    def test_casas(self):
        text = ("# The First House\n"
                "The first house rules self-image.\n"
                "Some prose about the Second House origins.\n")
        res = lcp.detect_house_presence(text)
        self.assertTrue(res[1]["mentions"] >= 1)
        self.assertTrue(res[1]["as_heading"])
        self.assertTrue(res[2]["mentions"] >= 1)
        self.assertEqual(res[12]["mentions"], 0)
        self.assertEqual(res[12]["first_line"], None)

    def test_partes(self):
        text = "See the appendix and the glossary. The Planets, the signs and aspects.\nBibliography follows the Index."
        partes = lcp.detect_part_presence(text)
        self.assertTrue(partes["apéndice/glosario"])
        self.assertTrue(partes["los planetas"])
        self.assertTrue(partes["bibliografía"])
        self.assertFalse(partes["luminaries (Sol/Luna)"])


class TestMuestras(unittest.TestCase):
    def test_sample_paragraphs_filtra(self):
        texto = "\n\n".join([f"word {i} " * 60 for i in range(12)] + ["short", "# Titulo"])
        picks = lcp.sample_paragraphs(texto, k=5)
        self.assertLessEqual(len(picks), 5)
        self.assertTrue(all(len(p.split()) >= 40 for p in picks))
        self.assertTrue(all(not p.startswith("#") for p in picks))


class TestHeadingCandidate(unittest.TestCase):
    def test_normal(self):
        self.assertTrue(lcp.heading_candidate("The Element Fire", frozenset()))
        self.assertTrue(lcp.heading_candidate("FIRE SIGNS KEY CONCEPT", frozenset()))

    def test_truncado_por_capa(self):
        # «...Their K»: último token de una letra → línea cortada por la capa de texto
        self.assertFalse(
            lcp.heading_candidate("The Elements of the Zodiacal Signs & Their K",
                                  frozenset()))

    def test_rubrica_recurrente_excluida(self):
        self.assertFalse(
            lcp.heading_candidate("Universal Principles",
                                  frozenset({"universal principles"})))


if __name__ == "__main__":
    unittest.main()
