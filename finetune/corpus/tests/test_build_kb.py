#!/usr/bin/env python3
"""Tests de la KB: arcanos menores escritos a mano (T7.1)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

import build_kb

FRASE_GENERICA = "Energía bloqueada o en exceso dentro de su ámbito."
CLAVES_CONTEXTO = ("amor", "trabajo", "dinero", "salud")
ELEMENTO_PALO = {"Bastos": "fuego", "Copas": "agua", "Espadas": "aire", "Oros": "tierra"}


class TestMenoresEscritos(unittest.TestCase):
    def setUp(self):
        self.menores = build_kb.MENORES

    def test_cincuenta_y_seis_menores(self):
        self.assertEqual(len(self.menores), 56)

    def test_nombres_unicos(self):
        nombres = [c["nombre"] for c in self.menores]
        self.assertEqual(len(nombres), len(set(nombres)))

    def test_usa_caballero_no_caballo(self):
        for c in self.menores:
            self.assertNotIn("Caballo", c["nombre"])
            self.assertNotIn("Caballo", c["rango"])

    def test_invertidas_unicas_y_no_genericas(self):
        invertidas = [c["invertida"] for c in self.menores]
        self.assertEqual(len(invertidas), len(set(invertidas)))
        for c in self.menores:
            self.assertNotEqual(c["invertida"], FRASE_GENERICA)

    def test_palabras_clave_cuatro_especificas(self):
        for c in self.menores:
            self.assertEqual(len(c["palabras_clave"]), 4, c["nombre"])

    def test_significado_sin_plantilla(self):
        for c in self.menores:
            self.assertNotIn("en el ámbito de", c["significado"])

    def test_contextos_completos(self):
        for c in self.menores:
            ctx = c.get("contextos", {})
            for k in CLAVES_CONTEXTO:
                self.assertTrue(ctx.get(k), f"{c['nombre']}: falta contexto {k}")

    def test_numero_y_palo_coherentes(self):
        self.assertEqual(sorted(c["numero"] for c in self.menores), sorted(list(range(1, 15)) * 4))
        for c in self.menores:
            self.assertEqual(c["elemento"], ELEMENTO_PALO[c["palo"]])


class TestMayoresConContextos(unittest.TestCase):
    def setUp(self):
        self.mayores = build_kb.MAYORES

    def test_veintidos_mayores(self):
        self.assertEqual(len(self.mayores), 22)

    def test_contextos_completos(self):
        for c in self.mayores:
            ctx = c.get("contextos", {})
            for k in CLAVES_CONTEXTO:
                self.assertTrue(ctx.get(k), f"{c['nombre']}: falta contexto {k}")

    def test_invertidas_unicas_entre_mayores(self):
        invertidas = [c["invertida"] for c in self.mayores]
        self.assertEqual(len(invertidas), len(set(invertidas)))

    def test_la_fuerza_sin_repetición(self):
        fuerza = next(c for c in self.mayores if c["nombre"] == "La Fuerza")
        self.assertNotIn("domina: domina", fuerza["significado"])

    def test_numeracion_fuerza_y_justicia(self):
        fuerza = next(c for c in self.mayores if c["nombre"] == "La Fuerza")
        justicia = next(c for c in self.mayores if c["nombre"] == "La Justicia")
        self.assertEqual(fuerza["numero"], 8)
        self.assertEqual(justicia["numero"], 11)


class TestSotaDeEspadas(unittest.TestCase):
    def test_de_pie_y_alerta(self):
        sota = next(c for c in build_kb.MENORES if c["nombre"] == "Sota de Espadas")
        self.assertNotIn("agazapada", sota["significado"])
        self.assertIn("De pie y alerta", sota["significado"])


class TestAstroCoherencia(unittest.TestCase):
    def test_orbes_aspectos(self):
        esperado = {"Conjunción": 6, "Sextil": 5, "Cuadratura": 6, "Trígono": 6, "Oposición": 7}
        self.assertEqual(len(build_kb.ASPECTOS), 5)
        for a in build_kb.ASPECTOS:
            self.assertEqual(a["orbe"], esperado[a["nombre"]], a["nombre"])

    def test_regentes_tradicionales(self):
        for s in build_kb.SIGNOS:
            self.assertIn("regente_tradicional", s, s["nombre"])
        escorpio = next(s for s in build_kb.SIGNOS if s["nombre"] == "Escorpio")
        acuario = next(s for s in build_kb.SIGNOS if s["nombre"] == "Acuario")
        self.assertEqual(escorpio["regente_tradicional"], "Marte")
        self.assertEqual(acuario["regente_tradicional"], "Saturno")
        self.assertEqual(escorpio["regente"], "Plutón")
        self.assertEqual(acuario["regente"], "Urano")
        tradicional = {"Aries": "Marte", "Tauro": "Venus", "Géminis": "Mercurio",
                      "Cáncer": "Luna", "Leo": "Sol", "Virgo": "Mercurio",
                      "Libra": "Venus", "Escorpio": "Marte", "Sagitario": "Júpiter",
                      "Capricornio": "Saturno", "Acuario": "Saturno", "Piscis": "Júpiter"}
        for s in build_kb.SIGNOS:
            self.assertEqual(s["regente_tradicional"], tradicional[s["nombre"]], s["nombre"])

    def test_numerologia_doce_con_areas(self):
        self.assertEqual(len(build_kb.NUMEROS), 12)
        for n in build_kb.NUMEROS:
            areas = n.get("areas", {})
            for k in CLAVES_CONTEXTO:
                self.assertTrue(areas.get(k), f"{n['nombre']}: falta área {k}")


class TestValidateAmpliado(unittest.TestCase):
    def setUp(self):
        import copy
        self.data = build_kb.build()
        self.copy = copy.deepcopy

    def test_validate_sin_errores(self):
        self.assertEqual(build_kb.validate(self.data), [])

    def test_detecta_nombre_repetido(self):
        d = self.copy(self.data)
        d["tarot"]["menores"][0]["nombre"] = d["tarot"]["menores"][1]["nombre"]
        self.assertTrue(any("duplicado" in e for e in build_kb.validate(d)))

    def test_detecta_invertida_repetida(self):
        d = self.copy(self.data)
        d["tarot"]["menores"][0]["invertida"] = d["tarot"]["menores"][1]["invertida"]
        self.assertTrue(any("invertida" in e for e in build_kb.validate(d)))

    def test_detecta_falta_contextos(self):
        d = self.copy(self.data)
        del d["tarot"]["mayores"][0]["contextos"]
        self.assertTrue(any("contexto" in e for e in build_kb.validate(d)))


if __name__ == "__main__":
    unittest.main()
