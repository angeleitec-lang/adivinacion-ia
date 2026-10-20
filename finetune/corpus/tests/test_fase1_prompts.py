import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import random
import unittest

import fase1_prompts as fp
import generate_tasks as gt
from calculos import numerologia as calc_num

KB = {
    "tarot": gt.load_kb("tarot.json"),
    "astrologia": gt.load_kb("astrologia.json"),
    "numerologia": gt.load_kb("numerologia.json"),
}

UNIVERSO = [c["nombre"] for c in KB["tarot"]["mayores"] + KB["tarot"]["menores"]]


def tarea_tarot(cartas, contexto="amor", familia="tarot_3"):
    return {
        "familia": familia,
        "contexto": contexto,
        "pregunta": "¿Qué energía hay en mi vida sentimental?",
        "cartas": cartas,
        "universo_cartas": UNIVERSO,
    }


class TestConstruirPrompt(unittest.TestCase):
    def test_devuelve_system_y_user(self):
        t = tarea_tarot([{"nombre": "El Loco", "invertida": False}])
        p = fp.construir_prompt(t, KB, {})
        self.assertIsInstance(p, dict)
        self.assertIn("system", p)
        self.assertIn("user", p)
        self.assertTrue(p["system"].strip())
        self.assertTrue(p["user"].strip())

    def test_system_incluye_reglas_de_estilo(self):
        t = tarea_tarot([{"nombre": "El Loco", "invertida": False}])
        s = fp.construir_prompt(t, KB, {})["system"]
        self.assertIn("español", s)
        self.assertIn("tendencia", s)
        self.assertIn("diagnóstic", s)
        self.assertIn("garant", s)
        self.assertIn("deriv", s)

    def test_referencia_contiene_cartas_y_significado(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": False},
        ], familia="tarot_2")
        u = fp.construir_prompt(t, KB, {})["user"]
        self.assertIn("Referencia", u)
        self.assertIn("El Loco", u)
        self.assertIn("La Luna", u)
        kb_loco = next(c for c in KB["tarot"]["mayores"] if c["nombre"] == "El Loco")
        self.assertIn(kb_loco["significado"], u)

    def test_referencia_marca_orientacion_invertida(self):
        t = tarea_tarot([{"nombre": "La Luna", "invertida": True}], familia="tarot_1")
        u = fp.construir_prompt(t, KB, {})["user"]
        self.assertIn("invertida", u)
        kb_luna = next(c for c in KB["tarot"]["mayores"] if c["nombre"] == "La Luna")
        self.assertIn(kb_luna["invertida"], u)

    def test_referencia_marca_discrepancia_entre_tradiciones(self):
        # Escorpio: regente moderno Plutón != regente tradicional Marte.
        carta = {
            "planetas": {"Sol": {"signo": "Escorpio", "grados": "15°20", "casa": 3}},
            "ascendente": {"signo": "Libra", "grados": "10°00"},
            "mc": {"signo": "Cáncer", "grados": "0°00"},
            "aspectos": [],
        }
        t = {
            "familia": "astro_natal",
            "pregunta": "¿Qué dice mi carta sobre mi vocación?",
            "foco": "vocación profesional",
            "ciudad": "Madrid",
            "pais": "España",
        }
        calculos = {"carta_natal": carta}
        u = fp.construir_prompt(t, KB, calculos)["user"]
        self.assertIn("Escorpio", u)
        self.assertIn("tradicional", u)
        self.assertIn("Marte", u)

    def test_incluye_datos_calculados_numerologia(self):
        fecha, nombre = "1990-05-15", "María López"
        cv = calc_num.camino_de_vida(fecha)
        ap = calc_num.anio_personal(fecha, 2026)
        t = {
            "familia": "numerologia",
            "pregunta": "¿Qué me dice la numerología sobre mi camino?",
            "nombre": nombre,
            "calculos": {
                "numerologia": {
                    "camino_de_vida": cv,
                    "expresion": calc_num.expresion(nombre),
                    "alma": calc_num.reducir(calc_num.alma(nombre)),
                    "personalidad": calc_num.reducir(calc_num.personalidad(nombre)),
                    "anio_personal": ap,
                }
            },
        }
        u = fp.construir_prompt(t, KB, t["calculos"])["user"]
        self.assertIn("camino de vida", u)
        self.assertIn(str(cv), u)
        self.assertIn("año personal", u)
        self.assertIn(str(ap), u)

    def test_incluye_carta_natal_datos(self):
        carta = {
            "fecha": "1990-05-15", "hora": "08:30",
            "planetas": {"Sol": {"signo": "Tauro", "grados": "24°10", "casa": 8}},
            "ascendente": {"signo": "Libra", "grados": "12°05"},
            "mc": {"signo": "Cáncer", "grados": "2°00"},
            "aspectos": [],
        }
        t = {
            "familia": "astro_natal",
            "pregunta": "¿Qué dice mi carta sobre mi salud?",
            "foco": "salud y energía",
            "ciudad": "Sevilla", "pais": "España",
        }
        u = fp.construir_prompt(t, KB, {"carta_natal": carta})["user"]
        self.assertIn("Ascendente", u)
        self.assertIn("Tauro", u)
        self.assertIn("24°10", u)


class TestVerificarLectura(unittest.TestCase):
    def test_lectura_valida_pasa(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": True},
            {"nombre": "El Sol", "invertida": False},
        ])
        texto = (
            "En esta tirada, El Loco abre el camino con ganas de lanzarte sin red. "
            "La Luna aparece invertida, invitándote a aclarar ilusiones y no confundir "
            "el miedo con la intuición. El Sol cierra con calidez y vitalidad compartida. "
            "Con honestidad puedes disfrutar de esta etapa."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_carta_ausente(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": True},
            {"nombre": "El Sol", "invertida": False},
        ])
        texto = (
            "El Loco abre el camino y El Sol cierra con calidez. "
            "La Luna invertida pide aclarar ilusiones. Todo fluye."
        )
        # Quitamos por completo la mención a una carta:
        texto = "El Loco abre el camino con ganas. El Sol cierra con calidez y vitalidad. Es un buen momento."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("La Luna" in m for m in motivos))

    def test_carta_ajena(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": True},
        ], familia="tarot_2")
        texto = (
            "El Loco inicia y La Luna invertida aclara ilusiones. "
            "Además, la Torre anuncia un cambio brusco que lo cambia todo."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("ajena" in m for m in motivos))

    def test_orientacion_invertida_no_mencionada(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": True},
        ], familia="tarot_2")
        texto = (
            "El Loco abre con espontaneidad y La Luna habla de intuición profunda "
            "en tu vínculo. Es un momento de escucha interior."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("invertid" in m or "orientación" in m for m in motivos))

    def test_orientacion_inventada(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "El Sol", "invertida": False},
        ], familia="tarot_2")
        texto = (
            "El Loco abre el camino y El Sol, invertido, trae un optimismo que "
            "conviene revisar con calma."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("invertid" in m or "orientación" in m for m in motivos))

    def test_ano_personal_erroneo(self):
        fecha = "1990-05-15"
        ap = calc_num.anio_personal(fecha, 2026)
        malo = ap + 1 if ap < 9 else 1
        t = {
            "familia": "numerologia",
            "pregunta": "¿Qué me depara este año?",
            "nombre": "María López",
            "calculos": {"numerologia": {"anio_personal": ap}},
        }
        texto = (
            f"Tu año personal {malo} te pide abrir ciclos nuevos con confianza y "
            "tomara la iniciativa en lo que te ilusiona."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("año personal" in m for m in motivos))

    def test_ano_personal_correcto_no_falla(self):
        fecha = "1990-05-15"
        ap = calc_num.anio_personal(fecha, 2026)
        t = {
            "familia": "numerologia",
            "pregunta": "¿Qué me depara este año?",
            "nombre": "María López",
            "calculos": {"numerologia": {"anio_personal": ap}},
        }
        texto = (
            f"Tu año personal {ap} te acompaña hacia una etapa de apertura y "
            "nuevos comienzos si te atreves a dar el paso."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_camino_de_vida_erroneo(self):
        fecha = "1990-05-15"
        cv = calc_num.camino_de_vida(fecha)
        malo = cv + 1 if cv < 9 else 1
        t = {
            "familia": "numerologia",
            "pregunta": "¿Cuál es mi camino?",
            "nombre": "María López",
            "calculos": {"numerologia": {"camino_de_vida": cv}},
        }
        texto = (
            f"Tu camino de vida {malo} habla de liderazgo e iniciativa propia."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("camino de vida" in m for m in motivos))

    def test_sol_en_signo_erroneo(self):
        t = {
            "familia": "astro_natal",
            "pregunta": "¿Qué dice mi carta?",
            "foco": "general",
            "calculos": {"carta_natal": {"planetas": {"Sol": {"signo": "Aries"}}}},
        }
        texto = "Con tu Sol en Leo buscas brillo y reconocimiento en todo lo que haces."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("Sol" in m for m in motivos))

    def test_promesa_medica(self):
        t = tarea_tarot([{"nombre": "El Sol", "invertida": False}], familia="tarot_1")
        texto = (
            "El Sol ilumina tu salud: vas a curarte del cáncer por completo, "
            "así que puedes dejar la medicación sin problema."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("médic" in m or "promesa" in m or "diagnóstic" in m for m in motivos))

    def test_derivacion_medica_no_es_promesa(self):
        t = tarea_tarot([{"nombre": "El Sol", "invertida": False}], familia="tarot_1")
        texto = (
            "El Sol habla de vitalidad, pero no puedo decirte si tienes esa "
            "enfermedad: consulta con tu médico, que es quien puede ayudarte de verdad."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_etica_sin_promesas_pasa(self):
        t = {"familia": "etica", "pregunta": "Dime la fecha en que voy a morir."}
        texto = (
            "Entiendo tu angustia, pero nadie puede darte una fecha de muerte; "
            "eso no está en las cartas. Lo que sí puedo ofrecerte es acompañamiento "
            "y, si lo necesitas, derivarte a un profesional."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_etica_con_promesa_falla(self):
        t = {"familia": "etica", "pregunta": "¿Me garantizas que vuelve conmigo?"}
        texto = "Te garantizo que tu pareja volverá contigo este mes, sin ninguna duda."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
