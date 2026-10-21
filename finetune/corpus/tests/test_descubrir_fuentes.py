#!/usr/bin/env python3
"""Tests de descubrir_fuentes (T74) con cliente HTTP simulado."""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import descubrir_fuentes as df  # noqa: E402


class ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def get(self, url):
        self.llamadas.append(url)
        return self.respuestas.get(
            url, {"estado": "error", "status": 404, "html": "", "bytes": 0}
        )


def _sitemap(urls):
    locs = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'


def _index(subs):
    locs = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in subs)
    return f'<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</sitemapindex>'


class TestUtilidades(unittest.TestCase):
    def test_norm_dominio(self):
        self.assertEqual(df.norm_dominio("WWW.Example.COM"), "example.com")
        self.assertEqual(df.norm_dominio("example.com:8080"), "example.com")
        self.assertEqual(df.norm_dominio("sub.example.com"), "sub.example.com")

    def test_extraer_locs(self):
        self.assertEqual(df.extraer_locs(_sitemap(["http://a.com/1", "http://a.com/2"])),
                         ["http://a.com/1", "http://a.com/2"])

    def test_extraer_locs_desenvuelve_cdata(self):
        xml = ("<urlset><url><loc><![CDATA[https://a.com/x]]></loc></url>"
               "<url><loc>  https://a.com/y  </loc></url>"
               "<url><loc><![CDATA[https://a.com/z?u=1]]></loc></url></urlset>")
        self.assertEqual(df.extraer_locs(xml),
                         ["https://a.com/x", "https://a.com/y", "https://a.com/z?u=1"])

    def test_indice_cdata_recurse(self):
        idx = "https://ej.com/sitemap.xml"
        xml_idx = ('<sitemapindex><sitemap><loc><![CDATA[https://ej.com/s-1.xml]]></loc></sitemap>'
                   '</sitemapindex>')
        cli = ClienteFalso({
            idx: {"estado": "ok", "html": xml_idx},
            "https://ej.com/s-1.xml": {"estado": "ok", "html": _sitemap([
                "https://ej.com/natal/pag"])},
        })
        urls = df.descubrir_desde_sitemap(cli, idx, r"natal", limite=10,
                                         sleep=lambda s: None)
        self.assertEqual(urls, ["https://ej.com/natal/pag"])

    def test_es_sitemap_index(self):
        self.assertTrue(df.es_sitemap_index(_index(["http://a.com/s1.xml"])))
        self.assertFalse(df.es_sitemap_index(_sitemap(["http://a.com/1"])))


class TestDescubrirSitemap(unittest.TestCase):
    def test_filtra_por_patron_y_dominio(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({
            sm: {"estado": "ok", "html": _sitemap([
                "https://ej.com/baraja/as-de-oro",
                "https://ej.com/baraja/dos-de-copas",
                "https://ej.com/horoscopo/aries",
                "https://otro.com/baraja/as-de-oro",
            ])},
        })
        urls = df.descubrir_desde_sitemap(cli, sm, r"ej\.com/baraja/", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(urls, [
            "https://ej.com/baraja/as-de-oro",
            "https://ej.com/baraja/dos-de-copas",
        ])

    def test_recursion_en_indice(self):
        idx = "https://ej.com/sitemap_index.xml"
        cli = ClienteFalso({
            idx: {"estado": "ok", "html": _index([
                "https://ej.com/sitemap-1.xml",
                "https://ej.com/sitemap-2.xml",
            ])},
            "https://ej.com/sitemap-1.xml": {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/1",
            ])},
            "https://ej.com/sitemap-2.xml": {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/2",
            ])},
        })
        urls = df.descubrir_desde_sitemap(cli, idx, r"numerolog", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(sorted(urls), [
            "https://ej.com/numerologia/1",
            "https://ej.com/numerologia/2",
        ])

    def test_robots_prohibido_se_excluye(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({
            sm: {"estado": "ok", "html": _sitemap([
                "https://ej.com/numerologia/permitido",
                "https://ej.com/numerologia/prohibido",
            ])},
        })
        robots = lambda u: "prohibido" not in u
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                         robots=robots, sleep=lambda s: None)
        self.assertEqual(urls, ["https://ej.com/numerologia/permitido"])

    def test_sitemap_404_devuelve_vacio(self):
        cli = ClienteFalso({})
        urls = df.descubrir_desde_sitemap(cli, "https://ej.com/sitemap.xml",
                                         r".", limite=50, sleep=lambda s: None)
        self.assertEqual(urls, [])

    def test_limite_se_respeta(self):
        sm = "https://ej.com/sitemap.xml"
        muchas = [f"https://ej.com/numerologia/{i}" for i in range(100)]
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap(muchas)}})
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=10,
                                         sleep=lambda s: None)
        self.assertEqual(len(urls), 10)

    def test_tasa_sleep_entre_peticiones(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1"])}})
        llamadas_sleep = []
        df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                   sleep=lambda s: llamadas_sleep.append(s))
        # una petición al sitemap → al menos un sleep de cortesía
        self.assertGreaterEqual(len(llamadas_sleep), 1)
        self.assertIn(1.2, llamadas_sleep)

    def test_deduplicado(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/x",
            "https://ej.com/numerologia/x",
        ])}})
        urls = df.descubrir_desde_sitemap(cli, sm, r"numerolog", limite=50,
                                         sleep=lambda s: None)
        self.assertEqual(urls, ["https://ej.com/numerologia/x"])


class TestFabricaRobots(unittest.TestCase):
    def test_permite_cuando_no_robots(self):
        cli = ClienteFalso({})  # robots.txt 404
        robots = df.fabrica_robots(cli, "ej.com", sleep=lambda s: None)
        self.assertTrue(robots("https://ej.com/cualquier/cosa"))

    def test_respeta_disallow(self):
        robots_txt = "User-agent: *\nDisallow: /privado/\n"
        cli = ClienteFalso({
            "https://ej.com/robots.txt": {"estado": "ok", "html": robots_txt},
        })
        robots = df.fabrica_robots(cli, "ej.com", sleep=lambda s: None)
        self.assertFalse(robots("https://ej.com/privado/secreto"))
        self.assertTrue(robots("https://ej.com/numerologia/1"))


class TestConstruirPlan(unittest.TestCase):
    def test_dominio_bloqueado_se_omite(self):
        fuentes = [{
            "dominio": "reddit.com",
            "sitemap": "https://reddit.com/sitemap.xml",
            "patron": r".",
            "familia": "numerologia",
        }]
        cli = ClienteFalso({})
        por = df.construir_plan(fuentes, cli, sleep=lambda s: None)
        self.assertEqual(por, {})
        self.assertNotIn("https://reddit.com/sitemap.xml", cli.llamadas)

    def test_agrupa_por_familia(self):
        sm = "https://ej.com/sitemap.xml"
        fuentes = [{
            "dominio": "ej.com",
            "sitemap": sm,
            "patron": r"ej\.com/(numerologia|baraja)/",
            "familia": "numerologia",
        }]
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1",
            "https://ej.com/baraja/2",
        ])}})
        por = df.construir_plan(fuentes, cli, sleep=lambda s: None)
        self.assertEqual(por["numerologia"], [
            "https://ej.com/numerologia/1",
            "https://ej.com/baraja/2",
        ])


class TestEscribirPlan(unittest.TestCase):
    def test_formato_compatible(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            total = df.escribir_plan(
                {"numerologia": ["https://a.com/1", "https://a.com/2"],
                 "baraja_espanola": ["https://b.com/3"]},
                ruta,
            )
            self.assertEqual(total, 3)
            with open(ruta, encoding="utf-8") as fh:
                lineas = [json.loads(l) for l in fh if l.strip()]
            self.assertEqual(len(lineas), 2)
            for entrada in lineas:
                self.assertIn("entidad_id", entrada)
                self.assertIn("familia", entrada)
                self.assertIn("nombre", entrada)
                self.assertIsInstance(entrada["urls_candidatas"], list)
                for c in entrada["urls_candidatas"]:
                    self.assertIn("url", c)
            familias = sorted(e["familia"] for e in lineas)
            self.assertEqual(familias, ["baraja_espanola", "numerologia"])

    def test_familia_vacia_no_se_escribe(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            total = df.escribir_plan({"numerologia": []}, ruta)
            self.assertEqual(total, 0)
            with open(ruta, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "")

    def test_prefijo_t79_en_entidad_id(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            df.escribir_plan({"tarot": ["https://a.com/1"]}, ruta, prefijo="t79")
            with open(ruta, encoding="utf-8") as fh:
                entrada = json.loads(fh.readline())
            self.assertEqual(entrada["entidad_id"], "t79_tarot")
            self.assertIn("T79", entrada["nombre"])

    def test_prefijo_por_defecto_es_t74(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan.jsonl")
            df.escribir_plan({"tarot": ["https://a.com/1"]}, ruta)
            with open(ruta, encoding="utf-8") as fh:
                entrada = json.loads(fh.readline())
            self.assertEqual(entrada["entidad_id"], "t74_tarot")


class TestNormUrl(unittest.TestCase):
    def test_quita_query_y_fragmento(self):
        self.assertEqual(df.norm_url("https://a.com/x?v=1#frag"), "https://a.com/x")
        self.assertEqual(df.norm_url("https://a.com/x#f"), "https://a.com/x")
        self.assertEqual(df.norm_url("https://a.com/x"), "https://a.com/x")


class TestExcluir(unittest.TestCase):
    def test_excluir_salta_urls_ya_descargadas(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1",
            "https://ej.com/numerologia/2",
        ])}})
        urls = df.descubrir_desde_sitemap(
            cli, sm, r"numerolog", limite=50, sleep=lambda s: None,
            excluir={"https://ej.com/numerologia/1"},
        )
        self.assertEqual(urls, ["https://ej.com/numerologia/2"])

    def test_excluir_compara_normalizada(self):
        sm = "https://ej.com/sitemap.xml"
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1?utm=x#top",
            "https://ej.com/numerologia/2",
        ])}})
        urls = df.descubrir_desde_sitemap(
            cli, sm, r"numerolog", limite=50, sleep=lambda s: None,
            excluir={"https://ej.com/numerologia/1"},
        )
        self.assertEqual(urls, ["https://ej.com/numerologia/2"])

    def test_construir_plan_pasa_excluir(self):
        sm = "https://ej.com/sitemap.xml"
        fuentes = [{
            "dominio": "ej.com", "sitemap": sm,
            "patron": r"numerolog", "familia": "numerologia",
        }]
        cli = ClienteFalso({sm: {"estado": "ok", "html": _sitemap([
            "https://ej.com/numerologia/1",
            "https://ej.com/numerologia/2",
        ])}})
        por = df.construir_plan(fuentes, cli, sleep=lambda s: None,
                               excluir={"https://ej.com/numerologia/2"})
        self.assertEqual(por["numerologia"], ["https://ej.com/numerologia/1"])


class TestCargarExclusiones(unittest.TestCase):
    def test_lee_manifest_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "manifest.jsonl")
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"url": "https://a.com/x?u=1"}) + "\n")
                fh.write(json.dumps({"url": "https://b.com/y#f"}) + "\n")
                fh.write(json.dumps({"otra": "cosa"}) + "\n")
                fh.write("\n")
            ex = df.cargar_exclusiones_de_manifest(ruta)
            self.assertEqual(ex, {"https://a.com/x", "https://b.com/y"})

    def test_manifest_inexistente_devuelve_vacio(self):
        ex = df.cargar_exclusiones_de_manifest("/nonexistent/manifest.jsonl")
        self.assertEqual(ex, set())


class TestFuentesT79(unittest.TestCase):
    def test_shape_valido(self):
        self.assertGreaterEqual(len(df.FUENTES_T79), 8)
        for f in df.FUENTES_T79:
            for clave in ("dominio", "sitemap", "patron", "familia"):
                self.assertIn(clave, f)
            re.compile(f["patron"])

    def test_sin_dominios_bloqueados(self):
        bloqueados = df.dominios_bloqueados()
        for f in df.FUENTES_T79:
            self.assertNotIn(df.norm_dominio(f["dominio"]), bloqueados)

    def test_familias_conocidas(self):
        conocidas = {"baraja_espanola", "numerologia", "astrologia", "tarot"}
        for f in df.FUENTES_T79:
            self.assertIn(f["familia"], conocidas)

    def test_cubre_familias_exigidas(self):
        familias = {f["familia"] for f in df.FUENTES_T79}
        for exigida in ("baraja_espanola", "numerologia", "astrologia"):
            self.assertIn(exigida, familias)

    def test_patrones_coinciden_con_slugs_reales(self):
        esperadas = {
            "https://astralsagehub.com/es-es/sol-ascendente/ascendente-en-aries": "astralsagehub.com",
            "https://biddytarot.com/tarot-card-meanings/major-arcana/fool/": "biddytarot.com",
            "https://annacasas.es/tres-de-oros-baraja-espanola/": "annacasas.es",
            "https://annacasas.es/el-3-de-copas-en-una-lectura/": "annacasas.es",
            "https://annacasas.es/la-sota-de-espadas-en-el-tarot/": "annacasas.es",
            "https://annacasas.es/tirada-de-cartas-gratis-baraja-espanola-significado-40-y-48-cartas/": "annacasas.es",
            "https://campus-astrologia.es/urano-en-libra-en-casa-7/": "campus-astrologia.es",
            "https://campus-astrologia.es/luna-oposicion-neptuno/": "campus-astrologia.es",
            "https://campus-astrologia.es/nodo-norte-en-capricornio-en-casa-10/": "campus-astrologia.es",
            "https://campus-astrologia.es/quiron-en-aries-significado/": "campus-astrologia.es",
            "https://elreydecopas.com/baraja-espanola/as-de-copas/": "elreydecopas.com",
            "https://astrologuias.com/baraja-espanola/7-de-copas/": "astrologuias.com",
            "https://astro-cours.com/es/planetas/marte/": "astro-cours.com",
            "https://www.numerologist.com/numerology/master-numbers/master-number-11": "numerologist.com",
            "https://www.numerologist.com/numerology/chaldean-numerology": "numerologist.com",
            "https://labyrinthos.co/blogs/learn-tarot-with-labyrinthos-academy/ace-of-cups-meaning": "labyrinthos.co",
            "https://tiradadetarot.com/tirada-del-tiempo/": "tiradadetarot.com",
            "https://tiradadetarot.com/lectura-de-vida/": "tiradadetarot.com",
        }
        for url, dominio in esperadas.items():
            regexes = [re.compile(f["patron"]) for f in df.FUENTES_T79
                      if df.norm_dominio(f["dominio"]) == dominio]
            self.assertTrue(regexes, f"sin fuente para {dominio}")
            self.assertTrue(any(r.search(url) for r in regexes),
                          f"ningún patrón de {dominio} casa con {url}")

    def test_patrones_annacasas_no_casan_ruido(self):
        ruido = [
            "https://annacasas.es/que-significa-sonar-con-monedas-de-oro/",
            "https://annacasas.es/colgantes-de-oro/",
            "https://annacasas.es/caballo-de-troya/",
        ]
        regexes = [re.compile(f["patron"]) for f in df.FUENTES_T79
                   if df.norm_dominio(f["dominio"]) == "annacasas.es"]
        for url in ruido:
            self.assertFalse(any(r.search(url) for r in regexes),
                           f"patrón casa con ruido: {url}")


class TestFuentesT86(unittest.TestCase):
    def test_shape_valido(self):
        self.assertGreaterEqual(len(df.FUENTES_T86), 8)
        for f in df.FUENTES_T86:
            for clave in ("dominio", "sitemap", "patron", "familia"):
                self.assertIn(clave, f)
            re.compile(f["patron"])

    def test_sin_dominios_bloqueados(self):
        bloqueados = df.dominios_bloqueados()
        for f in df.FUENTES_T86:
            self.assertNotIn(df.norm_dominio(f["dominio"]), bloqueados)

    def test_todas_de_astrologia(self):
        for f in df.FUENTES_T86:
            self.assertEqual(f["familia"], "astrologia")

    def test_no_repite_dominios_t74_t79_astrologia(self):
        previos = set()
        for f in list(df.FUENTES_DEF) + list(df.FUENTES_T79):
            if f["familia"] == "astrologia":
                previos.add(df.norm_dominio(f["dominio"]))
        for f in df.FUENTES_T86:
            self.assertNotIn(df.norm_dominio(f["dominio"]), previos)

    def test_patrones_coinciden_con_slugs_reales(self):
        esperadas = {
            "https://mundoastro.com/planetas/nodo-norte/": "mundoastro.com",
            "https://mundoastro.com/planetas/quiron/": "mundoastro.com",
            "https://astralisis.com/articulos/urano-en-aries": "astralisis.com",
            "https://astralisis.com/articulos/saturno-en-aries": "astralisis.com",
            "https://aspectados.com/guias/aspectos-astrologicos": "aspectados.com",
            "https://aspectados.com/blog/aspectos-aplicativos-separativos-orbes-astrologia": "aspectados.com",
            "https://astrocronos.com/blog/la-casa-1-y-el-ascendente": "astrocronos.com",
            "https://zodiacohoy.com/blog/ascendente-en-aries-personalidad-y-vida-diaria": "zodiacohoy.com",
            "https://aprendeastrologia.com/blog/sol-en-geminis/": "aprendeastrologia.com",
            "https://www.yourastrallife.com/es/blog/lectura-de-quiron-en-la-carta-astral": "yourastrallife.com",
            "https://miastrologa.com/es/aspects/chiron-semisextile-ascendant": "miastrologa.com",
            "https://cafeastrology.com/synastry/venus_mars_aspects.html": "cafeastrology.com",
            "https://cafeastrology.com/natal/venus-in-aries.html": "cafeastrology.com",
            "https://www.astrology.com/houses/eighth-house": "astrology.com",
            "https://www.astrology.com/planets/venus": "astrology.com",
        }
        for url, dominio in esperadas.items():
            regexes = [re.compile(f["patron"]) for f in df.FUENTES_T86
                       if df.norm_dominio(f["dominio"]) == dominio]
            self.assertTrue(regexes, f"sin fuente para {dominio}")
            self.assertTrue(any(r.search(url) for r in regexes),
                          f"ningún patrón de {dominio} casa con {url}")

    def test_patrones_no_casan_ruido(self):
        ruido = [
            "https://www.yourastrallife.com/pt/blog/compatibilidade-de-marte/",
            "https://www.yourastrallife.com/es/biblioteca",
            "https://www.yourastrallife.com/es/tarot/respuesta-inmediata",
            "https://miastrologa.com/es/chat",
            "https://miastrologa.com/es/pricing",
            "https://miastrologa.com/es/calendar",
            "https://cafeastrology.com/birthday/august-12.html",
            "https://www.astrology.com/tarot/card-meanings.html",
            "https://mundoastro.com/contacto/",
            "https://astralisis.com/servicios/consulta",
        ]
        regexes = [re.compile(f["patron"]) for f in df.FUENTES_T86]
        for url in ruido:
            self.assertFalse(any(r.search(url) for r in regexes),
                           f"patrón casa con ruido: {url}")


class TestConjunto(unittest.TestCase):
    def test_t74_es_la_defecto(self):
        self.assertIs(df.obtener_conjunto("t74"), df.FUENTES_DEF)

    def test_t79_devuelve_nueva(self):
        self.assertIs(df.obtener_conjunto("t79"), df.FUENTES_T79)

    def test_t86_devuelve_astrologia(self):
        self.assertIs(df.obtener_conjunto("t86"), df.FUENTES_T86)

    def test_conjunto_desconocido_error(self):
        with self.assertRaises(ValueError):
            df.obtener_conjunto("t99")


if __name__ == "__main__":
    unittest.main()
