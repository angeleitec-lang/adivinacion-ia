#!/usr/bin/env python3
"""Genera la matriz de trabajos sintéticos en corpus/jobs.db."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sqlite3
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "corpus" / "kb"

SYSTEM = (
    "Eres una tarotista, astróloga y numeróloga profesional con más de veinte años de "
    "experiencia. Lees para personas reales con respeto, empatía y lenguaje claro. "
    "Interpretas los símbolos combinando las técnicas que se te dan, sin inventar datos: "
    "las cartas, posiciones planetarias, casas y números que aparecen en la consulta son "
    "los únicos válidos. Escribes en español neutro, con estructura natural (apertura, "
    "interpretación, consejo), sin listas rígidas salvo que aporten claridad. No haces "
    "diagnósticos médicos, legales ni financieros: orientas y derivas cuando corresponde. "
    "No prometes resultados ni predicciones absolutas; hablas de tendencias y posibilidades."
)

CIUDADES = [
    ("Madrid", "España", 40.4168, -3.7038, "Europe/Madrid"),
    ("Barcelona", "España", 41.3874, 2.1686, "Europe/Madrid"),
    ("Sevilla", "España", 37.3891, -5.9845, "Europe/Madrid"),
    ("Valencia", "España", 39.4699, -0.3763, "Europe/Madrid"),
    ("Bilbao", "España", 43.2630, -2.9350, "Europe/Madrid"),
    ("Ciudad de México", "México", 19.4326, -99.1332, "America/Mexico_City"),
    ("Guadalajara", "México", 20.6597, -103.3496, "America/Mexico_City"),
    ("Buenos Aires", "Argentina", -34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
    ("Córdoba", "Argentina", -31.4201, -64.1888, "America/Argentina/Cordoba"),
    ("Bogotá", "Colombia", 4.7110, -74.0721, "America/Bogota"),
    ("Medellín", "Colombia", 6.2442, -75.5812, "America/Bogota"),
    ("Lima", "Perú", -12.0464, -77.0428, "America/Lima"),
    ("Santiago", "Chile", -33.4489, -70.6693, "America/Santiago"),
    ("Caracas", "Venezuela", 10.4806, -66.9036, "America/Caracas"),
    ("Montevideo", "Uruguay", -34.9011, -56.1645, "America/Montevideo"),
    ("La Habana", "Cuba", 23.1136, -82.3666, "America/Havana"),
    ("San Juan", "Puerto Rico", 18.4655, -66.1057, "America/Puerto_Rico"),
    ("Quito", "Ecuador", -0.1807, -78.4678, "America/Guayaquil"),
    ("Panamá", "Panamá", 8.9824, -79.5199, "America/Panama"),
    ("Asunción", "Paraguay", -25.2637, -57.5759, "America/Asuncion"),
]

NOMBRES = [
    "María López", "Ana García", "Lucía Fernández", "Carmen Ruiz", "Sofía Martínez",
    "Laura Sánchez", "Paula Gómez", "Marta Díaz", "Elena Torres", "Claudia Ramos",
    "Valeria Ortiz", "Daniela Castro", "Patricia Vega", "Rosa Méndez", "Irene Navarro",
    "Javier Pérez", "Carlos Rodríguez", "Daniel Álvarez", "Pablo Moreno", "Diego Romero",
    "Andrés Gil", "Miguel Serrano", "Sergio Blanco", "Álvaro Molina", "Adrián Ortega",
    "Hugo Delgado", "Iván Marín", "Raúl Iglesias", "Óscar Rubio", "Manuel Herrera",
    "Beatriz Cano", "Silvia Prieto", "Natalia Cortés", "Andrea Rivas", "Eva Campos",
    "Verónica Suárez", "Julia Reyes", "Cristina Vidal", "Alicia León", "Teresa Fuentes",
]

CONTEXTOS = ["amor", "trabajo", "dinero", "salud", "espiritual", "general"]

PREGUNTAS = {
    "amor": [
        "¿Qué energía hay en mi vida sentimental ahora mismo?",
        "Tengo una relación que me tiene confundida, ¿qué me dice esta carta?",
        "¿Voy a encontrar pareja en los próximos meses?",
        "¿Cómo puedo mejorar la comunicación con mi pareja?",
    ],
    "trabajo": [
        "¿Qué me espera en el trabajo en los próximos meses?",
        "¿Me conviene aceptar la oferta que me han hecho?",
        "¿Cómo puedo desbloquear mi carrera profesional?",
        "¿Hay cambios laborales cerca para mí?",
    ],
    "dinero": [
        "¿Qué dice esta carta sobre mis finanzas actuales?",
        "¿Es buen momento para una inversión o un cambio económico?",
        "¿Cómo puedo salir de esta situación económica?",
        "¿Voy a mejorar mis ingresos este año?",
    ],
    "salud": [
        "¿Qué energía rodea mi bienestar físico y emocional?",
        "¿Qué necesito atender de mi salud en esta etapa?",
        "¿Por qué me siento tan agotada últimamente?",
        "¿Qué debería cambiar en mis hábitos?",
    ],
    "espiritual": [
        "¿Qué aprendizaje espiritual me trae esta etapa?",
        "¿Qué debo soltar para avanzar?",
        "¿Qué me quiere decir el universo con esta situación?",
        "¿Cómo conecto con mi propósito?",
    ],
    "general": [
        "¿Qué necesito saber en este momento?",
        "¿Cuál es el tema central de mi vida ahora?",
        "¿Qué me conviene priorizar este mes?",
        "¿Qué bloqueo me está frenando?",
    ],
}

FOCOS_ASTRO = [
    "vocación profesional", "vida amorosa", "familia y raíces", "dinero y recursos",
    "salud y energía", "propósito espiritual", "estudios y formación",
    "mudanza o viaje", "próximo año", "talentos y creatividad",
]

FOCOS_SIN = ["compatibilidad amorosa", "sociedad laboral", "amistad", "vínculo familiar", "proyecto en común"]

SIGNOS = ["Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra", "Escorpio",
          "Sagitario", "Capricornio", "Acuario", "Piscis"]

PLANETAS = [
    (swe.SUN, "Sol"), (swe.MOON, "Luna"), (swe.MERCURY, "Mercurio"),
    (swe.VENUS, "Venus"), (swe.MARS, "Marte"), (swe.JUPITER, "Júpiter"),
    (swe.SATURN, "Saturno"), (swe.URANUS, "Urano"), (swe.NEPTUNE, "Neptuno"),
    (swe.PLUTO, "Plutón"),
]

ASPECTOS = [(0, "conjunción", 6.0), (60, "sextil", 5.0), (90, "cuadratura", 6.0),
            (120, "trígono", 6.0), (180, "oposición", 7.0)]


def load_kb(nombre):
    p = KB_DIR / nombre
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def fmt_grados(lon):
    g = int(lon % 30)
    m = int((lon % 1) * 60)
    return f"{g}°{m:02d}'"


def signo_de(lon):
    return SIGNOS[int(lon // 30) % 12]


def casa_de(lon, cuspides):
    for i in range(12):
        a = cuspides[i]
        b = cuspides[(i + 1) % 12]
        if a <= b:
            if a <= lon < b:
                return i + 1
        else:
            if lon >= a or lon < b:
                return i + 1
    return 1


def calcular_carta(fecha, hora, lat, lon, tz):
    d = dt.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    # La hora de nacimiento es local: se convierte a UT antes del cálculo juliano.
    d = d.replace(tzinfo=ZoneInfo(tz)).astimezone(dt.timezone.utc)
    jd = swe.julday(d.year, d.month, d.day, d.hour + d.minute / 60.0)
    cuspides, ascmc = swe.houses(jd, lat, lon, b"P")
    cusp = list(cuspides[1:13]) if len(cuspides) >= 13 else list(cuspides[:12])
    planetas = {}
    for pid, nombre in PLANETAS:
        xx, _ = swe.calc_ut(jd, pid, swe.FLG_SWIEPH | swe.FLG_SPEED)
        l = xx[0]
        planetas[nombre] = {
            "signo": signo_de(l),
            "grados": fmt_grados(l),
            "lon": l,
            "casa": casa_de(l, cusp),
        }
    aspectos = []
    nombres = [n for _, n in PLANETAS]
    for i in range(len(nombres)):
        for j in range(i + 1, len(nombres)):
            a = planetas[nombres[i]]["lon"]
            b = planetas[nombres[j]]["lon"]
            diff = abs((a - b + 180) % 360 - 180)
            for ang, nom, orbe in ASPECTOS:
                if abs(diff - ang) <= orbe:
                    aspectos.append({
                        "a": nombres[i], "b": nombres[j], "aspecto": nom,
                        "orbe": round(abs(diff - ang), 1),
                    })
                    break
    return {
        "fecha": fecha, "hora": hora,
        "planetas": planetas,
        "ascendente": {"signo": signo_de(ascmc[0]), "grados": fmt_grados(ascmc[0])},
        "mc": {"signo": signo_de(ascmc[1]), "grados": fmt_grados(ascmc[1])},
        "aspectos": mejores_aspectos(aspectos),
    }


def mejores_aspectos(aspectos, k=14):
    """Los k aspectos más exactos: ordenados por orbe ascendente."""
    return sorted(aspectos, key=lambda x: x["orbe"])[:k]


def fmt_carta(c, ciudad, pais):
    lineas = [f"Datos de nacimiento: {c['fecha']}, {c['hora']}, {ciudad} ({pais}).", "Posiciones:"]
    for nombre, p in c["planetas"].items():
        lineas.append(f"- {nombre}: {p['signo']} {p['grados']} (casa {p['casa']})")
    lineas.append(f"- Ascendente: {c['ascendente']['signo']} {c['ascendente']['grados']}")
    lineas.append(f"- Medio Cielo: {c['mc']['signo']} {c['mc']['grados']}")
    if c["aspectos"]:
        asp = "; ".join(
            f"{a['a']} {a['aspecto']} {a['b']} (orbe {a['orbe']}°)" for a in c["aspectos"]
        )
        lineas.append(f"Aspectos: {asp}.")
    return "\n".join(lineas)


def reducir(n):
    while n > 9 and n not in (11, 22, 33):
        n = sum(int(d) for d in str(n))
    return n


def digitos(fecha):
    return sum(int(ch) for ch in fecha if ch.isdigit())


def camino_de_vida(fecha):
    """Reduce por componentes conservando maestros (11, 22, 33) en cada uno."""
    _a, m, d = fecha.split("-")
    return reducir(reducir(int(d)) + reducir(int(m)) + reducir(digitos(_a)))


def letras_valor(nombre):
    n = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    total = 0
    for ch in n:
        if "A" <= ch <= "Z":
            total += (ord(ch) - 65) % 9 + 1
    return total


def vocales_consonantes(nombre):
    n = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    voc = sum(((ord(ch) - 65) % 9 + 1) for ch in n if ch in "AEIOU")
    con = sum(((ord(ch) - 65) % 9 + 1) for ch in n if "A" <= ch <= "Z" and ch not in "AEIOU")
    return reducir(voc), reducir(con)


def anio_personal(fecha, anio=2026):
    """Año personal: el resultado se reduce siempre a 1-9 (no conserva maestros)."""
    _a, m, d = fecha.split("-")
    total = reducir(int(d)) + reducir(int(m)) + reducir(digitos(str(anio)))
    while total > 9:
        total = sum(int(ch) for ch in str(total))
    return total


def fmt_numerologia(fecha, nombre):
    voc, con = vocales_consonantes(nombre)
    return (
        f"Fecha de nacimiento: {fecha}. Nombre completo: {nombre}.\n"
        f"- Camino de vida: {camino_de_vida(fecha)}\n"
        f"- Destino/expresión: {reducir(letras_valor(nombre))}\n"
        f"- Alma (vocales): {voc}\n"
        f"- Personalidad (consonantes): {con}\n"
        f"- Año personal 2026: {anio_personal(fecha)}"
    )


def carta_txt(c):
    orient = "invertida" if c.get("invertida") else "al derecho"
    return f"{c['nombre']} ({orient})"


def datos_carta(c):
    return c


ARRANQUES_ETICA = [
    "Estoy muy angustiada.",
    "Es urgente, no sé qué hacer.",
    "Llevo días sin dormir pensando en esto.",
    "Me tiembla la voz al preguntar.",
    "Vengo con mucho miedo.",
    "Estoy desesperada y sin saber a quién acudir.",
    "Acabo de enterarme y estoy en shock.",
]

CASOS_ETICA = [
    # Salud
    ("salud", "Tengo un bulto en el pecho y he soñado que es malo. Dime si tengo cáncer."),
    ("salud", "Estoy embarazada y quiero saber si el bebé estará sano, aunque no he ido al médico."),
    ("salud", "Mi médico me recetó una medicación larga. ¿Me dice la carta si puedo dejarla?"),
    ("salud", "Llevo meses con ataques de ansiedad y depresión. ¿La carta dice si voy a curarme?"),
    ("salud", "A veces pienso en hacerme daño. ¿Me lee la carta para saber si todo pasará?"),
    ("salud", "¿Tengo la misma enfermedad hereditaria que mi madre? Quiero saberlo antes de las pruebas."),
    # Legal
    ("legal", "Mi ex me quiere quitar la custodia. Dime qué decide el juez."),
    ("legal", "Voy a divorciarme. ¿La carta dice quién se quedará con la casa?"),
    ("legal", "Ha muerto mi tío y hay pelea por la herencia. ¿Qué me tocará?"),
    ("legal", "He puesto una denuncia. ¿La carta dice si ganaré el juicio?"),
    ("legal", "Me despidieron injustamente. ¿Recuperaré mi puesto según las cartas?"),
    # Dinero
    ("dinero", "¿Debería pedir un crédito para invertir en criptomonedas? Dime cuánto voy a ganar."),
    ("dinero", "Quiero poner un negocio. ¿La carta me garantiza que no perderé el dinero?"),
    ("dinero", "¿Me van a embargar la casa? Quiero saberlo hoy, no puedo esperar al banco."),
    ("dinero", "He comprado lotería. Dime los números ganadores de la semana."),
    ("dinero", "Me han ofrecido una inversión que promete el triple. ¿Es estafa o la carta dice que es buena?"),
    ("dinero", "Perdí todos mis ahorros en trading. ¿Me dice el tarot cómo recuperarlos rápido?"),
    # Terceros
    ("terceros", "Quiero saber si mi pareja me engaña. Lee su energía sin que esté presente."),
    ("terceros", "Sospecho que mi hijo adolescente consume drogas. Espíale con las cartas."),
    ("terceros", "¿Mi socio me está robando? Quiero leer su mente sin que lo sepa."),
    ("terceros", "Quiero saber qué piensa realmente mi jefa de mí, aunque ella no lo sepa."),
    # Menores
    ("menores", "Mi hija de 14 años quiere que le lea el futuro, ¿qué le digo?"),
    ("menores", "Mi niño de 8 años tiene miedo por las noches. Léele el tarot para tranquilizarlo."),
    # Muerte y duelo
    ("muerte", "Dime la fecha en que voy a morir."),
    ("muerte", "Mi marido falleció hace un año. Pregúntale a las cartas cómo está y si me perdona."),
    ("muerte", "Mi madre está en la UCI. ¿Cuánto tiempo de vida le queda según la carta?"),
    # Adicciones
    ("adicción", "Mi hermano es adicto. ¿La carta dice que va a dejarlo solo, verdad?"),
    ("adicción", "Yo mismo no puedo dejar el juego. ¿El tarot me confirma que puedo parar cuando quiera?"),
    ("adicción", "Mi hija bebe demasiado. ¿Las cartas dicen que no es para tanto?"),
    # Garantías
    ("garantía", "Si pago la lectura premium, ¿me garantizas que vuelve conmigo?"),
    ("garantía", "¿Me garantizas que acertarás? Si no, exijo la devolución."),
    ("garantía", "Quiero una garantía por escrito de que mi pareja me será fiel."),
    # Manipulación y dependencia
    ("dependencia", "¿Puedo consultarte cada día para decidir qué hacer? Sin tus cartas no vivo."),
    ("dependencia", "No tomo ninguna decisión sin preguntarte antes. ¿Es normal?"),
    ("manipulación", "Quiero usar la lectura para que mi pareja no me deje. Dime qué decirle para retenerla."),
    # Exigencia de certezas
    ("certeza", "Exijo una respuesta segura: sí o no, sin matices. ¿Me caso con él?"),
    ("certeza", "Dime algo 100% seguro sobre mi futuro, no quiero interpretaciones."),
    # Magia y maldiciones
    ("magia", "¿Me han hecho un trabajo de brujería? Quiero que lo confirmes y me quites la maldición."),
    ("magia", "Pagaré lo que sea por un amarre para que esa persona me ame. Hazlo con las cartas."),
    ("magia", "Creo que una maldición familiar arruina mi vida. ¿La carta lo confirma?"),
    # Cobros y estafas recibidas
    ("cobros", "Otra vidente me cobró una fortuna por una lectura falsa. ¿Me devuelve el dinero las cartas?"),
    ("cobros", "No tengo para comer, pero quiero una lectura urgente: ¿me la haces gratis y me dices si cobraré el paro?"),
]


class Builder:
    def __init__(self, rng, kb_tarot, kb_astro, kb_num):
        self.rng = rng
        self.cartas = kb_tarot["mayores"] + kb_tarot["menores"]
        self.astro = kb_astro
        self.num = kb_num

    def nacimiento(self):
        ciudad, pais, lat, lon, tz = self.rng.choice(CIUDADES)
        anio = self.rng.randint(1950, 2005)
        mes = self.rng.randint(1, 12)
        dia = self.rng.randint(1, 28)
        hora = f"{self.rng.randint(0, 23):02d}:{self.rng.choice([0, 15, 30, 45]):02d}"
        fecha = f"{anio:04d}-{mes:02d}-{dia:02d}"
        return fecha, hora, ciudad, pais, lat, lon, tz

    def tirada(self, n, unicas=True):
        elegidas = self.rng.sample(self.cartas, n) if unicas else self.rng.choices(self.cartas, k=n)
        return [{"nombre": c["nombre"], "invertida": self.rng.random() < 0.35} for c in elegidas]

    def job(self, bloque, prompt, payload, max_tokens=1024):
        return (bloque, SYSTEM, prompt, json.dumps(payload, ensure_ascii=False), max_tokens)

    def tarot_1(self):
        out = []
        for c in self.cartas:
            for ctx in CONTEXTOS:
                for inv in (False, True):
                    carta = {"nombre": c["nombre"], "invertida": inv}
                    preg = self.rng.choice(PREGUNTAS[ctx])
                    prompt = (
                        f"Tirada de una carta de tarot.\n\n"
                        f"Carta: {carta_txt(carta)}.\nContexto: {ctx}.\n"
                        f'Pregunta del consultante: "{preg}"\n\n'
                        f"Interpreta la carta para esta persona, en el contexto indicado."
                    )
                    out.append(self.job("tarot_1", prompt, {"carta": carta, "contexto": ctx}))
        return out

    def tarot_2(self, n=400):
        out = []
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            cartas = self.tirada(2)
            preg = self.rng.choice(PREGUNTAS[ctx])
            prompt = (
                f"Tirada de dos cartas de tarot.\n\n"
                f"Carta 1: {carta_txt(cartas[0])}.\nCarta 2: {carta_txt(cartas[1])}.\n"
                f"Contexto: {ctx}.\nPregunta del consultante: \"{preg}\"\n\n"
                f"Interpreta la combinación de las dos cartas."
            )
            out.append(self.job("tarot_2", prompt, {"cartas": cartas, "contexto": ctx}))
        return out

    def tarot_3(self, n=1400):
        out = []
        pos = ["pasado", "presente", "futuro"]
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            cartas = self.tirada(3)
            preg = self.rng.choice(PREGUNTAS[ctx])
            lineas = "\n".join(f"- {p}: {carta_txt(c)}" for p, c in zip(pos, cartas))
            prompt = (
                f"Tirada de tres cartas (pasado, presente y futuro).\n\n{lineas}\n"
                f"Contexto: {ctx}.\nPregunta del consultante: \"{preg}\"\n\n"
                f"Interpreta la tirada completa, relacionando las tres posiciones."
            )
            out.append(self.job("tarot_3", prompt, {"cartas": cartas, "contexto": ctx}))
        return out

    def cruz_celta(self, n=500):
        out = []
        pos = ["situacion", "obstaculo", "raiz", "pasado", "meta", "futuro cercano",
               "actitud", "entorno", "esperanzas y miedos", "resultado"]
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            cartas = self.tirada(10)
            preg = self.rng.choice(PREGUNTAS[ctx])
            lineas = "\n".join(f"- {p}: {carta_txt(c)}" for p, c in zip(pos, cartas))
            prompt = (
                f"Tirada de la Cruz Celta (diez cartas).\n\n{lineas}\n"
                f"Contexto: {ctx}.\nPregunta del consultante: \"{preg}\"\n\n"
                f"Interpreta la tirada completa."
            )
            out.append(self.job("cruz_celta", prompt, {"cartas": cartas, "contexto": ctx}, 1600))
        return out

    def tarot_pregunta(self, n=800):
        out = []
        for _ in range(n):
            carta = self.tirada(1)[0]
            ctx = self.rng.choice(CONTEXTOS)
            preg = self.rng.choice(PREGUNTAS[ctx])
            prompt = (
                f"Consulta de tarot con una carta.\n\n"
                f"Carta: {carta_txt(carta)}.\n"
                f'Pregunta del consultante: "{preg}"\n\n'
                f"Responde a la pregunta a partir de la carta."
            )
            out.append(self.job("tarot_pregunta", prompt, {"carta": carta, "contexto": ctx}))
        return out

    def astro_natal(self, n=1500):
        out = []
        for _ in range(n):
            fecha, hora, ciudad, pais, lat, lon, tz = self.nacimiento()
            c = calcular_carta(fecha, hora, lat, lon, tz)
            foco = self.rng.choice(FOCOS_ASTRO)
            prompt = (
                f"Lectura de carta natal.\n\n{fmt_carta(c, ciudad, pais)}\n\n"
                f'Pregunta del consultante: "¿Qué dice mi carta sobre mi {foco}?"\n\n'
                f"Interpreta la carta natal centrándote en ese ámbito."
            )
            out.append(self.job("astro_natal", prompt, {"carta": c, "foco": foco, "ciudad": ciudad}, 1400))
        return out

    def sinastria(self, n=600):
        out = []
        for _ in range(n):
            f1, h1, c1, p1, la1, lo1, tz1 = self.nacimiento()
            f2, h2, c2, p2, la2, lo2, tz2 = self.nacimiento()
            a = calcular_carta(f1, h1, la1, lo1, tz1)
            b = calcular_carta(f2, h2, la2, lo2, tz2)
            foco = self.rng.choice(FOCOS_SIN)
            prompt = (
                f"Estudio de sinastria entre dos cartas natales.\n\n"
                f"Persona A: {fmt_carta(a, c1, p1)}\n\nPersona B: {fmt_carta(b, c2, p2)}\n\n"
                f'Pregunta: "¿Qué nos dice la sinastria sobre nuestra {foco}?"\n\n'
                f"Compara ambas cartas e interpreta la relación."
            )
            out.append(self.job("sinastria", prompt, {"a": a, "b": b, "foco": foco}, 1600))
        return out

    def numerologia(self, n=400):
        out = []
        for _ in range(n):
            fecha, _, _, _, _, _, _ = self.nacimiento()
            nombre = self.rng.choice(NOMBRES)
            foco = self.rng.choice(["camino de vida", "propósito", "año personal", "talentos", "relaciones"])
            prompt = (
                f"Lectura numerológica.\n\n{fmt_numerologia(fecha, nombre)}\n\n"
                f'Pregunta del consultante: "¿Qué me dice la numerología sobre mi {foco}?"\n\n'
                f"Interpreta los números calculados."
            )
            out.append(self.job("numerologia", prompt, {"fecha": fecha, "nombre": nombre, "foco": foco}))
        return out

    def lectura_completa(self, n=3000):
        out = []
        for _ in range(n):
            fecha, hora, ciudad, pais, lat, lon, tz = self.nacimiento()
            c = calcular_carta(fecha, hora, lat, lon, tz)
            cartas = self.tirada(3)
            nombre = self.rng.choice(NOMBRES)
            ctx = self.rng.choice(CONTEXTOS)
            preg = self.rng.choice(PREGUNTAS[ctx])
            lineas = "\n".join(
                f"- {p}: {carta_txt(card)}" for p, card in zip(["pasado", "presente", "futuro"], cartas)
            )
            prompt = (
                f"Lectura completa: carta natal, tarot y numerología.\n\n"
                f"Consultante: {nombre}.\n{fmt_carta(c, ciudad, pais)}\n\n"
                f"Tirada de tres cartas:\n{lineas}\n\n"
                f"{fmt_numerologia(fecha, nombre)}\n\n"
                f'Pregunta del consultante: "{preg}"\n\n'
                f"Integra las tres técnicas en una lectura coherente y personalizada."
            )
            out.append(self.job("lectura_completa", prompt, {
                "carta": c, "cartas": cartas, "fecha": fecha, "nombre": nombre,
                "contexto": ctx, "ciudad": ciudad,
            }, 1800))
        return out

    def multiturno(self, n=800):
        """Simula la continuación en un solo turno; un multi-turno real requiere
        generación en dos fases (pendiente)."""
        out = []
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            carta = self.tirada(1)[0]
            preg1 = self.rng.choice(PREGUNTAS[ctx])
            seguimiento = self.rng.choice([
                "¿Y qué debería hacer yo al respecto?",
                "¿Y si la situación no cambia en un mes?",
                "¿Qué parte de esto depende de mí?",
                "¿Cómo afecta esto a mi entorno cercano?",
                "¿Qué señal debería observar para saber si voy bien?",
            ])
            previo = (
                f"En la consulta anterior salió {carta_txt(carta)} en contexto de {ctx}; "
                f"el consultante preguntó: «{preg1}»"
            )
            prompt = (
                f"Continuación de una consulta de tarot.\n\n{previo}\n\n"
                f'Nueva pregunta del consultante: "{seguimiento}"\n\n'
                f"Responde solo a la nueva pregunta, manteniendo el hilo de la lectura."
            )
            out.append(self.job("multiturno", prompt, {"carta": carta, "contexto": ctx}, 900))
        return out

    def _pares_etica(self):
        """Recorre todos los pares (caso, arranque) barajados sin repetir hasta agotarlos."""
        pares = [(c, a) for c in CASOS_ETICA for a in ARRANQUES_ETICA]
        while True:
            self.rng.shuffle(pares)
            yield from pares

    def etica(self, n=300):
        out = []
        for (tema, pregunta), arranque in zip(self._pares_etica(), range(n)):
            prompt = (
                f"Consulta delicada.\n\n{arranque} Pregunta del consultante: \"{pregunta}\"\n\n"
                f"Responde con honestidad, marcando los límites de la lectura y derivando a un profesional cuando corresponda."
            )
            out.append(self.job("etica", prompt, {"tema": tema}, 700))
        return out


TARGETS = {
    "tarot_1": 936, "tarot_2": 400, "tarot_3": 1400, "cruz_celta": 500,
    "tarot_pregunta": 800, "astro_natal": 1500, "sinastria": 600,
    "numerologia": 400, "lectura_completa": 3000, "multiturno": 800, "etica": 300,
}


def build_all(builder, only=None, scale=1.0):
    metodos = {
        "tarot_1": lambda: builder.tarot_1(),
        "tarot_2": lambda: builder.tarot_2(TARGETS["tarot_2"]),
        "tarot_3": lambda: builder.tarot_3(TARGETS["tarot_3"]),
        "cruz_celta": lambda: builder.cruz_celta(TARGETS["cruz_celta"]),
        "tarot_pregunta": lambda: builder.tarot_pregunta(TARGETS["tarot_pregunta"]),
        "astro_natal": lambda: builder.astro_natal(TARGETS["astro_natal"]),
        "sinastria": lambda: builder.sinastria(TARGETS["sinastria"]),
        "numerologia": lambda: builder.numerologia(TARGETS["numerologia"]),
        "lectura_completa": lambda: builder.lectura_completa(TARGETS["lectura_completa"]),
        "multiturno": lambda: builder.multiturno(TARGETS["multiturno"]),
        "etica": lambda: builder.etica(TARGETS["etica"]),
    }
    filas = []
    for nombre, fn in metodos.items():
        if only and nombre != only:
            continue
        lote = fn()
        if scale != 1.0:
            lote = lote[: max(1, int(len(lote) * scale))]
        filas.extend(lote)
        print(f"{nombre}: {len(lote)}")
    return filas


def crear_tabla(con):
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bloque TEXT NOT NULL,
            system TEXT NOT NULL,
            prompt TEXT NOT NULL,
            payload TEXT NOT NULL,
            max_tokens INTEGER NOT NULL DEFAULT 1024,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            worker TEXT,
            error TEXT,
            updated_at TEXT
        )"""
    )


def insertar_jobs(con, filas, replace_pending=False):
    """Inserta jobs por bloque de forma idempotente dentro de una transacción.

    Sin replace_pending: si el bloque ya tiene filas en la BD, se omite entero.
    Con replace_pending: se borran solo las filas 'pending' de ese bloque y se
    insertan las nuevas; done/running/failed no se tocan.
    """
    bloques = []
    for f in filas:
        if f[0] not in bloques:
            bloques.append(f[0])
    con.execute("BEGIN IMMEDIATE")
    try:
        insertadas = 0
        for bloque in bloques:
            existentes = con.execute(
                "SELECT COUNT(*) FROM jobs WHERE bloque=?", (bloque,)
            ).fetchone()[0]
            if existentes and not replace_pending:
                print(f"bloque {bloque}: ya existe ({existentes} filas), omitido")
                continue
            if replace_pending:
                con.execute("DELETE FROM jobs WHERE bloque=? AND status='pending'", (bloque,))
            grupo = [f for f in filas if f[0] == bloque]
            con.executemany(
                "INSERT INTO jobs (bloque, system, prompt, payload, max_tokens) VALUES (?,?,?,?,?)",
                grupo,
            )
            insertadas += len(grupo)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return insertadas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera la matriz de jobs sintéticos.")
    ap.add_argument("--db", default=str(ROOT / "corpus" / "jobs.db"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--only", default=None)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace-pending", action="store_true",
                   help="sustituye solo los jobs pendientes del bloque al regenerar")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    builder = Builder(rng, load_kb("tarot.json"), load_kb("astrologia.json"), load_kb("numerologia.json"))
    filas = build_all(builder, args.only, args.scale)
    print(f"TOTAL jobs: {len(filas)}")
    if args.dry_run:
        return 0

    con = sqlite3.connect(args.db)
    crear_tabla(con)
    insertadas = insertar_jobs(con, filas, replace_pending=args.replace_pending)
    n = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"Insertados {insertadas} jobs. Total en DB: {n}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
