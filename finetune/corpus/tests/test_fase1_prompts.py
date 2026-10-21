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
    "baraja": gt.load_kb("baraja_espanola.json"),
}

UNIVERSO = [c["nombre"] for c in KB["tarot"]["mayores"] + KB["tarot"]["menores"]]
UNIVERSO_ESP = fp.universo_baraja(KB["baraja"], KB["tarot"])


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

    def test_loteria_vedada(self):
        t = tarea_tarot([{"nombre": "La Emperatriz", "invertida": False}], familia="tarot_1")
        texto = "La Emperatriz al derecho; juega el número 23 de lotería."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("juego" in m or "apuest" in m or "loter" in m for m in motivos))

    def test_variantes_juego_vedadas(self):
        t = tarea_tarot([{"nombre": "La Emperatriz", "invertida": False}], familia="tarot_1")
        for frase in [
            "La Emperatriz al derecho; compra un décimo para la primitiva.",
            "La Emperatriz al derecho; rellena una quiniela esta semana.",
            "La Emperatriz al derecho; haz una apuesta segura.",
            "La Emperatriz al derecho; juega loteria sin miedo.",
        ]:
            with self.subTest(frase=frase):
                ok, motivos = fp.verificar_lectura(t, frase)
                self.assertFalse(ok, motivos)

    def test_sol_minuscula_no_es_carta_ajena(self):
        t = tarea_tarot([{"nombre": "La Emperatriz", "invertida": False}], familia="tarot_1")
        texto = "La Emperatriz al derecho brilla como el sol de la mañana."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_luna_torre_minusculas_no_ajenas(self):
        t = tarea_tarot([{"nombre": "La Emperatriz", "invertida": False}], familia="tarot_1")
        texto = (
            "La Emperatriz al derecho aporta abundancia; la luna llena y la torre "
            "del reloj son solo imágenes de tu día a día, no naipes de esta tirada."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_mayusculas_si_cuentan_como_carta_ajena(self):
        t = tarea_tarot([{"nombre": "La Emperatriz", "invertida": False}], familia="tarot_1")
        texto = "LA EMPERATRIZ AL DERECHO BRILLA. EL SOL ANUNCIA UNA NUEVA ETAPA."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("ajena" in m for m in motivos))

    def test_carta_ajena_mayuscula_inicial(self):
        t = tarea_tarot([
            {"nombre": "La Luna", "invertida": False},
            {"nombre": "La Emperatriz", "invertida": False},
        ], familia="tarot_2")
        texto = (
            "La Luna aporta intuición y La Emperatriz fertilidad. Además El Sol "
            "viene a reforzar el brillo de la tirada."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("ajena" in m and "Sol" in m for m in motivos))


from cartas import NAIPES_ESPANOLES  # noqa: E402

NAIPE = {c["nombre"]: c for c in NAIPES_ESPANOLES}


def naipe_carta(nombre, invertida=False):
    return {"nombre": nombre, "invertida": invertida,
            "sinonimos": list(NAIPE[nombre].get("sinonimos") or [])}


def tarea_baraja(cartas, familia="espanola_3"):
    t = {"familia": familia, "mazo": "espanol", "contexto": "amor",
         "pregunta": "¿Cómo va mi relación?",
         "cartas": cartas, "universo_cartas": UNIVERSO_ESP}
    if familia in fp.POSICIONES_ESPAÑOLA:
        t["posiciones"] = list(fp.POSICIONES_ESPAÑOLA[familia])
    return t


MAYORES = [c["nombre"] for c in KB["tarot"]["mayores"]]


def tarea_cruz():
    cartas = [{"nombre": n, "invertida": False} for n in MAYORES[:10]]
    pos = ["situacion", "obstaculo", "raiz", "pasado", "meta", "futuro cercano",
           "actitud", "entorno", "esperanzas y miedos", "resultado"]
    return {"familia": "cruz_celta", "contexto": "amor",
            "pregunta": "¿Qué camino me conviene?", "cartas": cartas,
            "posiciones": pos, "universo_cartas": UNIVERSO}


def texto_cruz(tarea, omitir=None, desorden=False, largo=False, sintesis=True,
               sin_carta_en=None):
    lineas = []
    for i, c in enumerate(tarea["cartas"]):
        k = i + 1
        if omitir == k:
            continue
        num = k
        if desorden and k == 3:
            num = 4
        elif desorden and k == 4:
            num = 3
        cuerpo = (
            f"Esta posición habla de una tendencia que puedes cuidar con calma y "
            f"presencia en tu día a día, sin apresurar los acontecimientos ni forzar "
            f"salidas."
        )
        if sin_carta_en != k:
            cuerpo = f"{c['nombre']} señala esto: " + cuerpo
        if largo and k == 5:
            cuerpo = cuerpo + (" Y además conviene matizar mucho cada palabra. " * 40)
        nombre_cab = c["nombre"] if sin_carta_en != k else ""
        linea_cab = f"## {num}. {tarea['posiciones'][i]} — {nombre_cab} (al derecho)"
        lineas.append(f"{linea_cab}\n{cuerpo}")
    if sintesis:
        lineas.append("## Síntesis\nAtando todo, avanza con pasos pequeños y medidos. Buen cierre.")
    return "\n\n".join(lineas)


class TestConstruirPromptTiradasLargas(unittest.TestCase):
    def test_recomendacion_cubre_todas_las_familias(self):
        for f in fp.FAMILIAS:
            self.assertIn(f, fp.RECOMENDACION_MAX_TOKENS)
        self.assertGreaterEqual(fp.RECOMENDACION_MAX_TOKENS["cruz_celta"], 6144)
        self.assertGreaterEqual(fp.RECOMENDACION_MAX_TOKENS["lectura_completa"], 6144)

    def test_cruz_celta_prompt_incluye_esquema_con_cabeceras(self):
        t = tarea_cruz()
        u = fp.construir_prompt(t, KB, {})["user"]
        self.assertIn("ESQUEMA OBLIGATORIO", u)
        for i, c in enumerate(t["cartas"], start=1):
            self.assertIn(f"## {i}. {t['posiciones'][i - 1]} — {c['nombre']} (al derecho)", u)
        self.assertIn("## Síntesis", u)
        self.assertIn("Solo existen las 10 cartas", u)

    def test_lectura_completa_prompt_incluye_cuatro_secciones(self):
        t = {"familia": "lectura_completa", "nombre": "María", "contexto": "amor",
             "pregunta": "¿Cómo va el año?",
             "cartas": [{"nombre": "El Loco", "invertida": False}],
             "universo_cartas": UNIVERSO}
        u = fp.construir_prompt(t, KB, {})["user"]
        for cab in ("## Carta natal", "## Tirada de tres cartas", "## Numerología", "## Síntesis"):
            self.assertIn(cab, u)

    def test_espanola_1_prompt_usa_kb_baraja(self):
        t = tarea_baraja([naipe_carta("As de Copas")], familia="espanola_1")
        u = fp.construir_prompt(t, KB, {})["user"]
        self.assertIn("baraja española (40 naipes)", u)
        self.assertIn("no es tarot ni baraja francesa", u)
        self.assertIn("Referencia", u)
        kb_as = next(c for c in KB["baraja"]["naipes"] if c["nombre"] == "As de Copas")
        self.assertIn(kb_as["significado"], u)

    def test_espanola_5_prompt_esquema_y_posiciones(self):
        cartas = [naipe_carta(n) for n in ("As de Oros", "Tres de Copas", "Siete de Espadas",
                                           "Sota de Bastos", "Rey de Oros")]
        t = tarea_baraja(cartas, familia="espanola_5")
        u = fp.construir_prompt(t, KB, {})["user"]
        self.assertIn("ESQUEMA OBLIGATORIO", u)
        self.assertIn("## 1. situación — As de Oros (al derecho)", u)
        self.assertIn("## 5. resultado — Rey de Oros (al derecho)", u)


class TestVerificarBaraja(unittest.TestCase):
    def test_universo_baraja_tiene_40_naipes_y_ajenas(self):
        naipes = [e for e in UNIVERSO_ESP if isinstance(e, dict)]
        extras = [e for e in UNIVERSO_ESP if isinstance(e, str)]
        self.assertEqual(len(naipes), 40)
        self.assertIn("Reina de Copas", extras)
        self.assertIn("Ocho de Oros", extras)
        self.assertIn("El Sol", extras)
        self.assertNotIn("Caballero de Copas", extras)
        self.assertNotIn("Sota de Oros", extras)

    def test_baraja_lectura_valida_pasa(self):
        t = tarea_baraja([naipe_carta("As de Copas"),
                          naipe_carta("Tres de Oros", invertida=True),
                          naipe_carta("Sota de Bastos")])
        texto = (
            "El As de Copas abre la tirada con ilusiones nuevas. El Tres de Oros "
            "invertido avisa de descuidos que conviene revisar. La Sota de Bastos "
            "trae noticias prácticas para el día a día. Cierra con calma."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_baraja_detecta_carta_ajena_de_tarot(self):
        t = tarea_baraja([naipe_carta("As de Copas"),
                          naipe_carta("Tres de Oros"),
                          naipe_carta("Sota de Bastos")])
        texto = (
            "El As de Copas abre, el Tres de Oros sostiene y la Sota de Bastos "
            "concreta. Además, la Reina de Copas corona la lectura con madurez."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("ajena" in m and "Reina de Copas" in m for m in motivos))

    def test_baraja_detecta_41_carta_ocho_de_oros(self):
        t = tarea_baraja([naipe_carta("As de Copas"),
                          naipe_carta("Tres de Oros"),
                          naipe_carta("Sota de Bastos")])
        texto = (
            "El As de Copas abre, el Tres de Oros sostiene y la Sota de Bastos "
            "concreta. El Ocho de Oros añade un final de ciclo material."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("ajena" in m and "Ocho de Oros" in m for m in motivos))

    def test_baraja_sinonimo_caballero_no_es_ajena_ni_faltante(self):
        t = tarea_baraja([naipe_carta("Caballo de Copas"),
                          naipe_carta("Tres de Oros"),
                          naipe_carta("Sota de Bastos")])
        texto = (
            "El Caballero de Copas trae propuestas afectivas, el Tres de Oros las "
            "sostiene con esfuerzo y la Sota de Bastos las concreta en gestos pequeños."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_baraja_carta_repetida_en_tirada(self):
        t = tarea_baraja([naipe_carta("As de Copas"),
                          naipe_carta("As de Copas"),
                          naipe_carta("Sota de Bastos")])
        texto = (
            "El As de Copas abre y la Sota de Bastos concreta, con ganas de cuidar "
            "lo que empieza."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("repetida" in m for m in motivos))

    def test_espanola_5_exige_esquema(self):
        cartas = [naipe_carta(n) for n in ("As de Oros", "Tres de Copas", "Siete de Espadas",
                                           "Sota de Bastos", "Rey de Oros")]
        t = tarea_baraja(cartas, familia="espanola_5")
        libre = " ".join(c["nombre"] + " trae su mensaje; " for c in cartas)
        ok, motivos = fp.verificar_lectura(t, libre)
        self.assertFalse(ok)
        self.assertTrue(any("Falta la sección" in m for m in motivos))
        self.assertTrue(any("Síntesis" in m for m in motivos))


class TestVerificarEsquema(unittest.TestCase):
    def test_cruz_celta_esquema_correcto_pasa(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t))
        self.assertTrue(ok, motivos)

    def test_cruz_celta_sin_esquema_falla(self):
        t = tarea_cruz()
        libre = " ".join(c["nombre"] + " aporta su lectura en este momento; " for c in t["cartas"])
        ok, motivos = fp.verificar_lectura(t, libre)
        self.assertFalse(ok)
        self.assertTrue(any("Falta la sección" in m for m in motivos))
        self.assertTrue(any("Síntesis" in m for m in motivos))

    def test_cruz_celta_falta_sintesis(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t, sintesis=False))
        self.assertFalse(ok)
        self.assertTrue(any("Síntesis" in m for m in motivos))

    def test_cruz_celta_omite_posicion(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t, omitir=7))
        self.assertFalse(ok)
        self.assertTrue(any("Falta la sección 7" in m for m in motivos))

    def test_cruz_celta_seccion_sin_su_carta(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t, sin_carta_en=3))
        self.assertFalse(ok)
        self.assertTrue(any("no nombra a la carta" in m for m in motivos))

    def test_cruz_celta_fuera_de_orden(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t, desorden=True))
        self.assertFalse(ok)
        self.assertTrue(any("orden" in m for m in motivos))

    def test_cruz_celta_seccion_larga_excede(self):
        t = tarea_cruz()
        ok, motivos = fp.verificar_lectura(t, texto_cruz(t, largo=True))
        self.assertFalse(ok)
        self.assertTrue(any("excede el máximo" in m for m in motivos))

    def test_lectura_completa_secciones_en_orden_pasan(self):
        t = {"familia": "lectura_completa", "nombre": "María", "contexto": "amor",
             "pregunta": "¿Cómo va el año?",
             "cartas": [
                 {"nombre": "El Loco", "invertida": False},
                 {"nombre": "La Templanza", "invertida": False},
                 {"nombre": "La Estrella", "invertida": False},
             ],
             "universo_cartas": UNIVERSO}
        texto = (
            "## Carta natal\nTu Sol y tu Luna piden movimiento sereno; el Ascendente acompaña.\n\n"
            "## Tirada de tres cartas\nEl Loco abre, La Templanza sostiene y La Estrella ilusiona.\n\n"
            "## Numerología\nTus números calculados hablan de constancia en lo cotidiano.\n\n"
            "## Síntesis\nUn año de pasos serenos: cuídalo sin prisa y con presencia."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)

    def test_lectura_completa_sin_secciones_falla(self):
        t = {"familia": "lectura_completa", "nombre": "María", "contexto": "amor",
             "pregunta": "¿Cómo va el año?",
             "cartas": [
                 {"nombre": "El Loco", "invertida": False},
                 {"nombre": "La Templanza", "invertida": False},
                 {"nombre": "La Estrella", "invertida": False},
             ],
             "universo_cartas": UNIVERSO}
        texto = "El Loco abre, La Templanza sostiene y La Estrella ilusiona este año."
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertFalse(ok)
        self.assertTrue(any("Falta la sección" in m for m in motivos))

    def test_compatibilidad_tarot_3_sin_esquema(self):
        t = tarea_tarot([
            {"nombre": "El Loco", "invertida": False},
            {"nombre": "La Luna", "invertida": False},
            {"nombre": "El Sol", "invertida": False},
        ])
        texto = (
            "El Loco abre con ganas, La Luna pide escucha interior y El Sol cierra "
            "con calidez compartida."
        )
        ok, motivos = fp.verificar_lectura(t, texto)
        self.assertTrue(ok, motivos)


if __name__ == "__main__":
    unittest.main()
