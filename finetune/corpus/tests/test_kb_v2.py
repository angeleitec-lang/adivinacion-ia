"""Tests del constructor de la KB v2 a partir del consenso (T66)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import kb_v2


def celda(eid, faceta, mayoritarias=None, discrepancias=None, unica=None,
         fallback=False, alertas=None):
    reg = {
        "entidad_id": eid,
        "faceta": faceta,
        "n_afirmaciones": 0,
        "mayoritarias": mayoritarias or [],
        "discrepancias": discrepancias or [],
        "unica_fuente": unica or [],
        "fallback": fallback,
        "alertas_factuales": alertas or [],
    }
    return reg


def may(texto, fuentes):
    return {
        "afirmacion": texto,
        "n_fuentes": len(fuentes),
        "fuentes": sorted(fuentes),
        "tradiciones": ["moderna"],
    }


def unica(texto, fuente, tradicion="moderna"):
    return {"afirmacion": texto, "fuente_id": fuente, "tradicion": tradicion}


def lado(texto, fuentes, tradiciones):
    return {"afirmacion": texto, "fuentes": sorted(fuentes),
            "tradiciones": sorted(tradiciones)}


class TestFamilia(unittest.TestCase):
    def test_familias_conocidas(self):
        self.assertEqual(kb_v2.familia_de_entidad("tarot-mayor-03"), "tarot")
        self.assertEqual(kb_v2.familia_de_entidad("tarot-bastos-11"), "tarot")
        self.assertEqual(kb_v2.familia_de_entidad("naipe-oros-01"),
                         "baraja_espanola")
        self.assertEqual(kb_v2.familia_de_entidad("aries|signo"), "astrologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("jupiter|aries|planeta_en_signo"),
            "astrologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("sol|casa3|planeta_en_casa"), "astrologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("luna|conjuncion|sol|aspecto"),
            "astrologia")
        self.assertEqual(kb_v2.familia_de_entidad("11|alma"), "numerologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("7|anio_personal"), "numerologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("3|camino_de_vida"), "numerologia")
        self.assertEqual(kb_v2.familia_de_entidad("5|destino"), "numerologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("9|personalidad"), "numerologia")
        self.assertEqual(
            kb_v2.familia_de_entidad("4|mes_personal"), "numerologia")

    def test_entidad_desconocida(self):
        self.assertIsNone(kb_v2.familia_de_entidad("runa-fehu|runa"))
        self.assertIsNone(kb_v2.familia_de_entidad("lenormand-1"))
        self.assertIsNone(kb_v2.familia_de_entidad(""))


class BaseKB(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t66_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.salida = os.path.join(self.dir, "kb_v2")

    def construir(self, regs, lineas_crudas=()):
        ruta = os.path.join(self.dir, "consenso.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            for reg in regs:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            for cruda in lineas_crudas:
                f.write(cruda + "\n")
        return kb_v2.construir_kb_v2(ruta, self.salida)


class TestCeldas(BaseKB):
    def test_mayoritarias_forman_nucleo_confianza_alta(self):
        regs = [celda("tarot-mayor-00", "significado_general",
                     mayoritarias=[may("inicio libre", ["a.com", "b.com"])])]
        stats = self.construir(regs)
        with open(os.path.join(self.salida, "tarot.json"), encoding="utf-8") as fh:
            kb = json.load(fh)
        c = kb["entidades"]["tarot-mayor-00"]["significado_general"]
        self.assertEqual(len(c["nucleo"]), 1)
        self.assertEqual(c["nucleo"][0]["afirmacion"], "inicio libre")
        self.assertEqual(c["confianza"], "alta")
        self.assertEqual(stats["celdas"], 1)

    def test_discrepancias_marcadas_sin_ganadora(self):
        disc = [{"a": lado("A es fuego", ["w1"], ["clasica"]),
                "b": lado("A es agua", ["w2"], ["moderna"])}]
        regs = [celda("aries|signo", "simbolismo",
                     mayoritarias=[may("base comun", ["x1", "x2"])],
                     discrepancias=disc)]
        self.construir(regs)
        with open(os.path.join(self.salida, "astrologia.json"), encoding="utf-8") as fh:
            kb = json.load(fh)
        c = kb["entidades"]["aries|signo"]["simbolismo"]
        self.assertEqual(len(c["discrepancias"]), 1)
        self.assertEqual(c["discrepancias"][0]["a"]["afirmacion"], "A es fuego")
        self.assertEqual(c["discrepancias"][0]["b"]["afirmacion"], "A es agua")
        self.assertNotIn("ganadora", c)
        self.assertEqual(c["confianza"], "media")

    def test_solo_unica_fuente_con_procedencia(self):
        regs = [celda("11|alma", "amor",
                     unica=[unica("mística", "moonoscope.com")])]
        self.construir(regs)
        with open(os.path.join(self.salida, "numerologia.json"), encoding="utf-8") as fh:
            kb = json.load(fh)
        c = kb["entidades"]["11|alma"]["amor"]
        self.assertEqual(c["nucleo"], [])
        self.assertEqual(c["unica_fuente"][0]["fuente_id"], "moonoscope.com")
        self.assertEqual(c["unica_fuente"][0]["tradicion"], "moderna")
        self.assertEqual(c["confianza"], "baja")

    def test_unica_fuente_dos_afirmaciones_media(self):
        regs = [celda("11|alma", "amor",
                     unica=[unica("una", "f1"), unica("dos", "f2")])]
        self.construir(regs)
        with open(os.path.join(self.salida, "numerologia.json"), encoding="utf-8") as fh:
            kb = json.load(fh)
        self.assertEqual(
            kb["entidades"]["11|alma"]["amor"]["confianza"], "media")

    def test_fallback_confianza_baja(self):
        regs = [celda("tarot-mayor-01", "amor",
                     unica=[unica("x", "f1")], fallback=True)]
        self.construir(regs)
        with open(os.path.join(self.salida, "tarot.json"), encoding="utf-8") as fh:
            kb = json.load(fh)
        c = kb["entidades"]["tarot-mayor-01"]["amor"]
        self.assertTrue(c["fallback"])
        self.assertEqual(c["confianza"], "baja")


class TestRobustez(BaseKB):
    def test_linea_corrupta_se_ignora_y_se_cuenta(self):
        regs = [celda("tarot-mayor-00", "amor",
                     mayoritarias=[may("ok", ["a", "b"])])]
        stats = self.construir(regs, lineas_crudas=["{no es json", "   {"])
        self.assertEqual(stats["corruptas"], 2)
        self.assertEqual(stats["celdas"], 1)

    def test_consenso_vacio(self):
        stats = self.construir([])
        self.assertEqual(stats["celdas"], 0)
        self.assertEqual(stats["corruptas"], 0)
        for fam in kb_v2.FAMILIAS:
            self.assertFalse(
                os.path.exists(os.path.join(self.salida, fam + ".json")))

    def test_entidad_desconocida_se_cuenta(self):
        regs = [celda("runa-fehu|runa", "amor",
                     mayoritarias=[may("x", ["a", "b"])])]
        stats = self.construir(regs)
        self.assertEqual(stats["desconocidas"], 1)
        self.assertEqual(stats["celdas"], 0)

    def test_no_modifica_la_entrada(self):
        ruta = os.path.join(self.dir, "consenso.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(json.dumps(celda(
                "tarot-mayor-00", "amor",
                mayoritarias=[may("x", ["a", "b"])]),
                ensure_ascii=False) + "\n")
        with open(ruta, "rb") as fh:
            antes = fh.read()
        kb_v2.construir_kb_v2(ruta, self.salida)
        with open(ruta, "rb") as fh:
            despues = fh.read()
        self.assertEqual(antes, despues)


class TestSeparacion(BaseKB):
    def test_baraja_y_tarot_nunca_se_mezclan(self):
        regs = [
            celda("naipe-oros-01", "amor",
                  mayoritarias=[may("naipe", ["a", "b"])]),
            celda("tarot-oros-1", "amor",
                  mayoritarias=[may("tarot", ["c", "d"])]),
        ]
        self.construir(regs)
        with open(os.path.join(self.salida, "baraja_espanola.json"),
                    encoding="utf-8") as fh:
            bar = json.load(fh)
        with open(os.path.join(self.salida, "tarot.json"),
                    encoding="utf-8") as fh:
            tar = json.load(fh)
        self.assertIn("naipe-oros-01", bar["entidades"])
        self.assertNotIn("naipe-oros-01", tar["entidades"])
        self.assertIn("tarot-oros-1", tar["entidades"])
        self.assertNotIn("tarot-oros-1", bar["entidades"])


class TestDeterminismo(BaseKB):
    def test_misma_entrada_misma_salida(self):
        regs = [
            celda("aries|signo", "amor",
                  mayoritarias=[may("x", ["a", "b"])],
                  discrepancias=[{"a": lado("p", ["f1"], ["clasica"]),
                                 "b": lado("q", ["f2"], ["moderna"])}]),
            celda("naipe-copas-02", "simbolismo",
                  unica=[unica("s", "f9")]),
            celda("3|destino", "significado_general",
                  mayoritarias=[may("d", ["u", "v", "w"])]),
        ]
        dir_b = os.path.join(self.dir, "b")
        ruta = os.path.join(self.dir, "consenso.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            for reg in regs:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        kb_v2.construir_kb_v2(ruta, self.salida)
        kb_v2.construir_kb_v2(ruta, dir_b)
        for fam in kb_v2.FAMILIAS:
            fa = os.path.join(self.salida, fam + ".json")
            fb = os.path.join(dir_b, fam + ".json")
            if os.path.exists(fa):
                with open(fa, "rb") as h1, open(fb, "rb") as h2:
                    self.assertEqual(h1.read(), h2.read())


class TestAtomico(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t66_atomico_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_escribe_y_renombra(self):
        destino = os.path.join(self.dir, "ok.json")
        kb_v2._escribir_atomico(destino, {"clave": "valor"})
        self.assertTrue(os.path.exists(destino))
        with open(destino, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"clave": "valor"})
        self.assertEqual(
            [f for f in os.listdir(self.dir) if f.endswith(".tmp")], [])

    def test_fallo_no_deja_fichero_parcial(self):
        destino = os.path.join(self.dir, "malo.json")
        with self.assertRaises(TypeError):
            kb_v2._escribir_atomico(destino, {"malo": {1, 2, 3}})
        self.assertFalse(os.path.exists(destino))
        self.assertEqual(
            [f for f in os.listdir(self.dir) if f.endswith(".tmp")], [])


class TestDiff(BaseKB):
    def setUp(self):
        super().setUp()
        self.kb_v1 = os.path.join(self.dir, "kb_v1")
        os.makedirs(self.kb_v1)
        astro = {"signos": [
            {"nombre": "Aries", "elemento": "fuego", "regente": "Marte",
             "regente_tradicional": "Marte", "palabras_clave": [],
             "rasgos": "impulsivo"},
            {"nombre": "Tauro", "elemento": "tierra", "regente": "Venus",
             "regente_tradicional": "Venus", "palabras_clave": [],
             "rasgos": "constante"},
        ], "planetas": [{"nombre": "Marte", "simboliza": "accion",
                        "palabras_clave": []}],
            "casas": [{"numero": 1, "area": "yo", "significado": "x"}],
            "aspectos": [{"nombre": "Conjuncion", "simbolo": "0",
                         "orbe": 6, "significado": "fusion"}]}
        with open(os.path.join(self.kb_v1, "astrologia.json"), "w",
                 encoding="utf-8") as fh:
            json.dump(astro, fh, ensure_ascii=False)
        num = {"1": {"numero": 1, "tipo": "simple", "nombre": "El Uno",
                    "palabras_clave": [], "positivo": "x", "sombra": "y",
                    "areas": {}}}
        with open(os.path.join(self.kb_v1, "numerologia.json"), "w",
                 encoding="utf-8") as fh:
            json.dump(num, fh, ensure_ascii=False)

    def construir_con_diff(self, regs):
        ruta = os.path.join(self.dir, "consenso.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            for reg in regs:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        informe = os.path.join(self.salida, "diff_vs_kb_v1.md")
        stats = kb_v2.construir_kb_v2(ruta, self.salida,
                                      kb_v1_dir=self.kb_v1,
                                      informe_diff=informe)
        return stats, informe

    def test_diff_contiene_las_cuatro_secciones(self):
        regs = [
            # aries tiene nucleo => respaldado; pero una unica fuente contradice
            celda("aries|signo", "amor",
                  mayoritarias=[may("impulso en el amor", ["a", "b"])]),
            celda("aries|signo", "simbolismo",
                  unica=[unica("Aries es un signo de agua", "malo.com")]),
            # tauro sin nucleo => v1 sin respaldo
            celda("tauro|signo", "amor", unica=[unica("suave", "f1")]),
            # numero 2 no esta en v1 => celda nueva
            celda("2|alma", "significado_general",
                  mayoritarias=[may("dualidad", ["p", "q"])]),
        ]
        stats, informe = self.construir_con_diff(regs)
        self.assertTrue(os.path.exists(informe))
        with open(informe, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("celdas nuevas", texto.lower())
        self.assertIn("contradicen", texto.lower())
        self.assertIn("sin respaldo", texto.lower())
        self.assertIn("cobertura", texto.lower())
        # (a) 2|alma es nueva (no esta en v1)
        self.assertTrue(any(c["entidad_id"] == "2|alma"
                           for c in stats["celdas_nuevas"]))
        # (b) la afirmacion de agua contradice la KB v1 (aries=fuego)
        self.assertTrue(any("agua" in c["afirmacion"]
                           for c in stats["contradicciones_v1"]))
        # (c) tauro sin respaldo
        respaldos = stats["v1_sin_respaldo"]
        self.assertTrue(any("tauro" in str(e).lower()
                           for e in respaldos.get("astrologia", [])))
        self.assertFalse(any("aries" in str(e).lower()
                            for e in respaldos.get("astrologia", [])))

    def test_alertas_del_consenso_entran_en_el_diff(self):
        regs = [celda("acuario|signo", "amor",
                     alertas=[{"afirmacion": "Acuario es de fuego",
                              "fuente_id": "f", "motivo": "elemento"}])]
        stats, _ = self.construir_con_diff(regs)
        self.assertTrue(any(a["motivo"] == "elemento"
                           for a in stats["contradicciones_v1"]))


if __name__ == "__main__":
    unittest.main()
