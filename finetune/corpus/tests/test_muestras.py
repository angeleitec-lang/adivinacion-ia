"""Tests del muestreador de fichas para revisión humana (T48)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import muestras


def _ev(entidad, faceta, calidad, hash_seccion):
    return {"entidad_id": entidad, "faceta": faceta,
            "fuente_id": "https://ejemplo.com/pagina", "dominio":
            "ejemplo.com", "idioma": "es", "periodo": "moderna",
            "calidad": calidad, "tipo": "web", "hash_seccion": hash_seccion}


def _registros_web():
    regs = []
    for i in range(60):
        regs.append(_ev("tarot-mayor-%02d" % (i % 22), "significado_general",
                        5, "h%02d" % i))
    for i in range(10):
        regs.append(_ev("naipe-oros-%02d" % i, "significado_general", 3,
                        "o%02d" % i))
    return regs


class TestMuestrear(unittest.TestCase):

    def test_reproducibilidad_misma_semilla(self):
        a, ta = muestras.muestrear(_registros_web(), 0.03,
                                   estratos=lambda r: (r["entidad_id"].split("-")[0], r["calidad"]),
                                   semilla=42)
        b, tb = muestras.muestrear(_registros_web(), 0.03,
                                   estratos=lambda r: (r["entidad_id"].split("-")[0], r["calidad"]),
                                   semilla=42)
        self.assertEqual([muestras.id_registro(r) for r in a],
                         [muestras.id_registro(r) for r in b])
        self.assertEqual(ta, tb)

    def test_independiente_del_orden_de_entrada(self):
        regs = _registros_web()
        a, _ = muestras.muestrear(regs, 0.1, estratos=lambda r: ("x",),
                                  semilla=7)
        b, _ = muestras.muestrear(list(reversed(regs)), 0.1,
                                  estratos=lambda r: ("x",), semilla=7)
        self.assertEqual([muestras.id_registro(r) for r in a],
                         [muestras.id_registro(r) for r in b])

    def test_minimo_uno_por_estrato(self):
        seleccion, tamanos = muestras.muestrear(
            _registros_web(), fraccion=0.0,
            estratos=lambda r: (muestras.familia_de(r["entidad_id"]),
                                 r["calidad"]), semilla=1)
        self.assertGreaterEqual(len(tamanos), 2)
        for k in tamanos.values():
            self.assertGreaterEqual(k, 1)
        estratos_sel = {(muestras.familia_de(r["entidad_id"]), r["calidad"])
                        for r in seleccion}
        self.assertEqual(estratos_sel, set(tamanos))

    def test_tamano_y_tope(self):
        regs = [_ev("tarot-mayor-01", "f", 5, "x%d" % i) for i in range(100)]
        seleccion, tamanos = muestras.muestrear(regs, 0.1,
                                                estratos=lambda r: ("t",), semilla=3)
        self.assertEqual(len(seleccion), 10)
        self.assertEqual(tamanos[("t",)], 10)
        pocos = [_ev("tarot-mayor-01", "f", 5, "y%d" % i) for i in range(3)]
        seleccion, tamanos = muestras.muestrear(pocos, 0.9,
                                                estratos=lambda r: ("t",), semilla=3)
        self.assertEqual(len(seleccion), 3)
        self.assertEqual(tamanos[("t",)], 3)

    def test_entradas_vacias(self):
        seleccion, tamanos = muestras.muestrear([])
        self.assertEqual(seleccion, [])
        self.assertEqual(tamanos, {})

    def test_nunca_repite(self):
        regs = _registros_web()
        regs.append(dict(regs[0]))
        regs.append(dict(regs[1]))
        seleccion, _ = muestras.muestrear(regs, 0.5,
                                          estratos=lambda r: (r["entidad_id"],), semilla=9)
        ids = [muestras.id_registro(r) for r in seleccion]
        self.assertEqual(len(ids), len(set(ids)))

    def test_id_determinista_y_con_id_nativo(self):
        r1 = _ev("tarot-mayor-01", "f", 5, "z")
        self.assertEqual(muestras.id_registro(r1), muestras.id_registro(dict(r1)))
        self.assertEqual(muestras.id_registro({"id": "abc123"}), "abc123")
        self.assertNotEqual(muestras.id_registro(r1),
                            muestras.id_registro({**r1, "calidad": 4}))

    def test_unicode_en_hash_de_id(self):
        a = muestras.id_registro({"afirmacion": "El naïpe óro — ¿significa?"})
        b = muestras.id_registro({"afirmacion": "El na\u00efpe \u00f3ro \u2014 \u00bfsignifica?"})
        self.assertEqual(a, b)


class TestEstratos(unittest.TestCase):

    def test_familias(self):
        self.assertEqual(muestras.familia_de("tarot-copas-02"), "tarot-copas")
        self.assertEqual(muestras.familia_de("naipe-espadas-10"), "naipe-espadas")
        self.assertEqual(muestras.familia_de("tarot-mayor-01|tarot-loco"),
                         "combinaciones")
        self.assertEqual(muestras.familia_de("astrologia"), "astrologia")
        self.assertEqual(muestras.familia_de(None), "sin-entidad")

    def test_estrato_por_nivel(self):
        ev = _ev("tarot-copas-02", "f", 4, "h")
        self.assertEqual(muestras.estrato_de("web", ev),
                         ("tarot-copas", "4"))
        self.assertEqual(muestras.estrato_de("libros", ev),
                         ("tarot-copas", "4"))
        self.assertEqual(muestras.estrato_de("afirmaciones", ev, "libros"),
                         ("libros", "tarot-copas", "4"))
        lec = {"sistema": "astrologia", "calidad": 5}
        self.assertEqual(muestras.estrato_de("lecturas", lec),
                         ("astrologia", "5"))
        self.assertEqual(muestras.estrato_de("web", {}),
                         ("sin-entidad", "s/d"))


class TestFichas(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        for d in ("evidencias_web", "libros/evidencias", "libros/secciones",
                  "afirmaciones_full", "lecturas", "web/ejemplo.com"):
            os.makedirs(os.path.join(self.base, d), exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _escribir(self, rel, lineas):
        with open(os.path.join(self.base, rel), "w",
                  encoding="utf-8") as fh:
            for l in lineas:
                fh.write(json.dumps(l, ensure_ascii=False) + "\n")

    def test_ficha_sin_texto(self):
        ev = _ev("tarot-mayor-01", "significado_general", 5, "noexiste")
        resolvedor = muestras.Resolvedor(self.base)
        ficha = muestras.ficha_markdown("web", {**ev, "id": "x",
                                                "estrato": ("tarot-mayor", "5")},
                                        resolvedor)
        self.assertIn("(sin texto)", ficha)
        self.assertIn("[ ] correcto", ficha)
        self.assertIn("[ ] dudoso", ficha)
        self.assertIn("[ ] incorrecto", ficha)
        self.assertIn("Nota: ___", ficha)

    def test_recortar(self):
        self.assertIsNone(muestras.recortar(None))
        self.assertIsNone(muestras.recortar("   "))
        largo = muestras.recortar("a " * 500, 60)
        self.assertLessEqual(len(largo), 75)
        self.assertTrue(largo.endswith("[…]"))
        self.assertEqual(muestras.recortar(" hola   mundo ", 100),
                         "hola mundo")

    def test_escribir_muestras_afirmaciones(self):
        afs = [{"entidad_id": "tarot-mayor-%02d" % i,
                "faceta": "significado_general",
                "fuente_id": "https://ejemplo.com/a%d" % i,
                "dominio": "ejemplo.com", "periodo": "moderna",
                "calidad": 4,
                "afirmacion": "El emperador nº %d — maternidad y ácción." % i}
               for i in range(50)]
        self._escribir("afirmaciones_full/afirmaciones.jsonl", afs)
        out = os.path.join(self.base, "salida")
        resumen = muestras.escribir_muestras(self.base, ("afirmaciones",),
                                             0.1, 42, out)
        self.assertEqual(resumen["niveles"]["afirmaciones"]["muestra"], 5)
        md = open(os.path.join(out, "muestras.md"),
                  encoding="utf-8").read()
        jl = [json.loads(l) for l in open(os.path.join(out, "muestras.jsonl"),
                                          encoding="utf-8")]
        self.assertEqual(len(jl), 5)
        for fila in jl:
            self.assertIn(fila["id"], md)
        # unicode intacto y sin escape ascii
        self.assertIn("—", md)
        self.assertIn("nº", md)
        self.assertNotIn("\\u", open(os.path.join(out, "muestras.jsonl"),
                                     encoding="utf-8").read())
        # las fichas salen ordenadas por estrato dentro del nivel
        posiciones = [md.index(fila["id"]) for fila in jl]
        self.assertEqual(posiciones, sorted(posiciones))

    def test_deduplicacion_entre_ficheros_del_nivel(self):
        a = {"entidad_id": "tarot-mayor-01", "faceta": "f",
             "fuente_id": "https://x/a", "dominio": "x", "periodo": "m",
             "calidad": 4, "afirmacion": "una"}
        self._escribir("afirmaciones_full/afirmaciones.jsonl", [a, dict(a)])
        out = os.path.join(self.base, "salida")
        resumen = muestras.escribir_muestras(self.base, ("afirmaciones",), 1.0,
                                             1, out)
        self.assertEqual(resumen["niveles"]["afirmaciones"]["total"], 1)


class TestOro(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        muestras_filas = [
            {"id": "a1", "nivel": "web", "estrato": ["tarot-mayor", "5"]},
            {"id": "a2", "nivel": "web", "estrato": ["tarot-mayor", "5"]},
            {"id": "a3", "nivel": "libros", "estrato": ["tarot-copas", "4"]},
            {"id": "a4", "nivel": "libros", "estrato": ["tarot-copas", "4"]},
            {"id": "a5", "nivel": "lecturas", "estrato": ["astrologia", "5"]},
        ]
        self.ruta_muestras = os.path.join(self.dir, "muestras.jsonl")
        with open(self.ruta_muestras, "w", encoding="utf-8") as fh:
            for m in muestras_filas:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _revisar(self, filas):
        ruta = os.path.join(self.dir, "muestras_revisadas.jsonl")
        with open(ruta, "w", encoding="utf-8") as fh:
            for f in filas:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        return ruta

    def test_oro_rechazados_informe(self):
        ruta = self._revisar([
            {"id": "a1", "veredicto": "correcto", "nota": "bien"},
            {"id": "a2", "veredicto": "incorrecto", "nota": "inventa"},
            {"id": "a3", "veredicto": "correcto"},
            {"id": "a4", "veredicto": "dudoso", "nota": "revisar URL"},
            {"id": "a5", "veredicto": "correcto"},
        ])
        informe = muestras.generar_oro(self.ruta_muestras, ruta, self.dir)
        oro = [json.loads(l) for l in open(informe["oro"],
                                           encoding="utf-8")]
        rech = [json.loads(l) for l in open(informe["rechazados"],
                                            encoding="utf-8")]
        self.assertEqual({o["id"] for o in oro}, {"a1", "a3", "a5"})
        self.assertEqual({r["id"] for r in rech}, {"a2"})
        self.assertEqual(oro[0]["nota"], "bien")
        texto = open(informe["informe"], encoding="utf-8").read()
        self.assertIn("web", texto)
        self.assertIn("50.0 %", texto)   # a1,a2: 1 de 2
        self.assertIn("NO ALCANZA", texto)
        # dudoso penaliza: libros 1 correcto de 2 -> 50 %
        self.assertAlmostEqual(informe["por_nivel"]["libros"]["tasa"], 0.5)

    def test_ids_desconocidos_error_claro(self):
        ruta = self._revisar([{"id": "zz9", "veredicto": "correcto"},
                              {"id": "a1", "veredicto": "correcto"}])
        with self.assertRaises(ValueError) as ctx:
            muestras.generar_oro(self.ruta_muestras, ruta, self.dir)
        self.assertIn("1 ids", str(ctx.exception))
        self.assertIn("zz9", str(ctx.exception))

    def test_veredicto_invalido_error(self):
        ruta = self._revisar([{"id": "a1", "veredicto": "maso bueno"}])
        with self.assertRaises(ValueError):
            muestras.generar_oro(self.ruta_muestras, ruta, self.dir)

    def test_muestras_vacias_error(self):
        vacia = os.path.join(self.dir, "vacia.jsonl")
        open(vacia, "w").close()
        ruta = self._revisar([{"id": "a1", "veredicto": "correcto"}])
        with self.assertRaises(ValueError):
            muestras.generar_oro(vacia, ruta, self.dir)


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        for d in ("lecturas",):
            os.makedirs(os.path.join(self.base, d), exist_ok=True)
        with open(os.path.join(self.base, "lecturas", "lecturas.jsonl"),
                  "w", encoding="utf-8") as fh:
            for i in range(40):
                fh.write(json.dumps({
                    "id": "l%02d" % i, "fuente": "libro",
                    "titulo_libro": "Guía de ádivinación", "autor": "N.",
                    "sistema": "astrologia" if i % 2 else "tarot",
                    "calidad": 4, "cartas": ["El sol"],
                    "pregunta": "¿Me irá bien?",
                    "texto": "Texto %d con tildes: ú í ó." % i},
                    ensure_ascii=False) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cli_muestrear_y_oro(self):
        out = os.path.join(self.base, "salida")
        rc = muestras.main(["--accion", "muestrear", "--nivel", "lecturas",
                            "--fraccion", "0.25", "--semilla", "5",
                            "--base", self.base, "--out-dir", out])
        self.assertEqual(rc, 0)
        jl = [json.loads(l) for l in
              open(os.path.join(out, "muestras.jsonl"), encoding="utf-8")]
        self.assertEqual(len(jl), 10)  # 5 por cada estrato (sistema, calidad)
        sistemas = {tuple(f["estrato"]) for f in jl}
        self.assertTrue(any(s[0] in ("tarot", "astrologia")
                            for s in sistemas))
        md = open(os.path.join(out, "muestras.md"), encoding="utf-8").read()
        self.assertIn("¿Me irá bien?", md)
        self.assertIn("Muestras para revisión humana", md)
        self.assertIn("Recuentos", md)
        with open(os.path.join(out, "muestras_revisadas.jsonl"),
                  "w", encoding="utf-8") as fh:
            for f in jl:
                fh.write(json.dumps({"id": f["id"],
                                     "veredicto": "correcto"}) + "\n")
        rc = muestras.main(["--accion", "oro", "--base", self.base,
                            "--out-dir", out])
        self.assertEqual(rc, 0)
        oro = [json.loads(l) for l in
               open(os.path.join(out, "oro.jsonl"), encoding="utf-8")]
        self.assertEqual(len(oro), 10)
        informe = open(os.path.join(out, "oro_informe.md"),
                       encoding="utf-8").read()
        self.assertIn("100.0 %", informe)
        self.assertIn("supera", informe)


class TestConsensoYCanalesRapidos(unittest.TestCase):
    """Celdas de consenso/KB v2 y canales rápido (mercury-3) — T93."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name
        for d in ("consenso_kb", "kb_v2", "afirmaciones_rapido/web",
                  "afirmaciones_rapido/libros"):
            os.makedirs(os.path.join(self.base, d), exist_ok=True)
        self.celda = {
            "entidad_id": "tarot-copas-02", "faceta": "significado_general",
            "n_afirmaciones": 4,
            "mayoritarias": [{"afirmacion": "El cuatro de copas invita al "
                               "recogimiento.", "n_fuentes": 2,
                               "fuentes": ["fuente-a", "fuente-b"],
                               "tradiciones": ["RWS"]}],
            "discrepancias": [{"a": {"afirmacion": "Trae suerte",
                                     "fuentes": ["fuente-a"]},
                               "b": {"afirmacion": "Aporta calma",
                                     "fuentes": ["fuente-b"]}}],
            "unica_fuente": [{"afirmacion": "Aportación única de repaso.",
                              "fuente_id": "fuente-c",
                              "tradicion": "Marsella"}],
            "alertas_factuales": [{"afirmacion": "Atribuye fuego a copas.",
                                   "fuente_id": "fuente-c",
                                   "motivo": "elemento"}],
        }
        with open(os.path.join(self.base, "consenso_kb", "consenso.jsonl"),
                  "w", encoding="utf-8") as fh:
            fh.write(json.dumps(self.celda, ensure_ascii=False) + "\n")
        kb = {"version": 2, "familia": "tarot",
              "entidades": {"tarot-copas-02": {
                  "significado_general": {"confianza": "alta"}}}}
        with open(os.path.join(self.base, "kb_v2", "tarot.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(kb, fh, ensure_ascii=False)
        rapida = {"entidad_id": "tarot-copas-02",
                  "faceta": "significado_general",
                  "fuente_id": "https://rapido.example/x",
                  "dominio": "rapido.example", "periodo": "moderna",
                  "calidad": 5, "origen": "mercury-3",
                  "afirmacion": "El cuatro de copas sugiere una pausa breve."}
        for rel in ("afirmaciones_rapido/web/afirmaciones.jsonl",):
            with open(os.path.join(self.base, rel), "w",
                      encoding="utf-8") as fh:
                fh.write(json.dumps(rapida, ensure_ascii=False) + "\n")
        rapida_l = dict(rapida)
        rapida_l["fuente_id"] = "waite1909"
        rapida_l["cita_original"] = "The Four of Cups..."
        with open(os.path.join(self.base,
                               "afirmaciones_rapido/libros/"
                               "afirmaciones_libros.jsonl"),
                  "w", encoding="utf-8") as fh:
            fh.write(json.dumps(rapida_l, ensure_ascii=False) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_forma_celda(self):
        self.assertEqual("M+D+U", muestras.forma_celda(self.celda))
        self.assertEqual("M", muestras.forma_celda(
            {"mayoritarias": [{"afirmacion": "a"}]}))
        self.assertEqual("D+U", muestras.forma_celda(
            {"discrepancias": [{"a": {"afirmacion": "x"},
                                "b": {"afirmacion": "y"}}],
             "unica_fuente": [{"afirmacion": "u", "fuente_id": "f"}]}))
        self.assertEqual("vacia", muestras.forma_celda({}))

    def test_rutas_consensso_y_canal_rapido(self):
        rutas = muestras.rutas_entradas(self.base, "consenso")
        self.assertEqual(1, len(rutas))
        self.assertEqual("consenso", rutas[0][1])
        origenes = [origen for _, origen in
                    muestras.rutas_entradas(self.base, "afirmaciones")]
        self.assertEqual(["rapido-web", "rapido-libros"], origenes)

    def test_indice_confianza(self):
        indice = muestras.indice_confianza(self.base)
        self.assertEqual(("tarot", "alta"),
                         indice[("tarot-copas-02", "significado_general")])

    def test_cargar_registros_anota_consenso(self):
        regs = list(muestras.cargar_registros(self.base, "consenso"))
        self.assertEqual(1, len(regs))
        fila = regs[0]
        self.assertEqual("M+D+U", fila["forma"])
        self.assertEqual("tarot", fila["familia_kb"])
        self.assertEqual("alta", fila["confianza"])
        self.assertEqual("alta", fila["calidad"])
        self.assertEqual("tarot", fila["sistema"])
        self.assertEqual(("tarot", "alta", "M+D+U"), fila["estrato"])

    def test_resolvedor_texto_y_procedencia_consenso(self):
        fila = next(iter(muestras.cargar_registros(self.base, "consenso")))
        resolvedor = muestras.Resolvedor(self.base)
        texto = resolvedor.texto("consenso", fila)
        self.assertIn("Afirmaciones mayoritarias:", texto)
        self.assertIn("(2 fuentes; fuentes: fuente-a, fuente-b; "
                      "tradiciones: RWS)", texto)
        self.assertIn("Discrepancias:", texto)
        self.assertIn("1) A: Trae suerte [fuente-a] — B: Aporta calma "
                      "[fuente-b]", texto)
        self.assertIn("Aportaciones de una sola fuente:", texto)
        self.assertIn("(fuente: fuente-c; tradición: Marsella)", texto)
        self.assertIn("Alertas fácticas:", texto)
        self.assertIn("! Atribuye fuego a copas. (motivo: elemento; "
                      "fuente: fuente-c)", texto)
        proc = muestras.procedencia_de("consenso", fila, resolvedor)
        self.assertIn("consenso_kb/consenso.jsonl", proc)
        self.assertIn("kb_v2 · tarot", proc)
        self.assertIn("confianza alta", proc)
        self.assertIn("4 afirmaciones", proc)

    def test_ficha_consenso_muestra_n_afirmaciones(self):
        fila = next(iter(muestras.cargar_registros(self.base, "consenso")))
        resolvedor = muestras.Resolvedor(self.base)
        ficha = muestras.ficha_markdown("consenso", fila, resolvedor)
        self.assertIn("4 afirmaciones en la celda", ficha)
        self.assertIn("forma M+D+U", ficha)

    def test_escribir_muestras_consenso_y_rapido(self):
        out = os.path.join(self.base, "salida")
        resumen = muestras.escribir_muestras(
            self.base, ("afirmaciones", "consenso"), 1.0, 42, out)
        self.assertEqual(resumen["niveles"]["afirmaciones"]["total"], 2)
        self.assertEqual(resumen["niveles"]["consenso"]["total"], 1)
        jl = [json.loads(l) for l in open(os.path.join(out, "muestras.jsonl"),
                                          encoding="utf-8")]
        por_origen = {fila["origen"]: fila for fila in jl}
        self.assertEqual("alta", por_origen["consenso"]["calidad"])
        self.assertEqual(["tarot", "alta", "M+D+U"],
                         por_origen["consenso"]["estrato"])
        self.assertIn("rapido-web", por_origen)
        self.assertIn("rapido-libros", por_origen)
        md = open(os.path.join(out, "muestras.md"), encoding="utf-8").read()
        self.assertIn("rapido-web", md)


if __name__ == "__main__":
    unittest.main()
