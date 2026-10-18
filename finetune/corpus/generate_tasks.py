#!/usr/bin/env python3
"""Genera la matriz de trabajos sinteticos en corpus/jobs.db."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sqlite3
import unicodedata
from pathlib import Path

import swisseph as swe

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "corpus" / "kb"

SYSTEM = (
    "Eres una tarotista, astrologa y numerologa profesional con mas de veinte anos de "
    "experiencia. Lees para personas reales con respeto, empatia y lenguaje claro. "
    "Interpretas los simbolos combinando las tecnicas que se te dan, sin inventar datos: "
    "las cartas, posiciones planetarias, casas y numeros que aparecen en la consulta son "
    "los unicos validos. Escribes en espanol neutro, con estructura natural (apertura, "
    "interpretacion, consejo), sin listas rigidas salvo que aporten claridad. No haces "
    "diagnosticos medicos, legales ni financieros: orientas y derivas cuando corresponde. "
    "No prometes resultados ni predicciones absolutas; hablas de tendencias y posibilidades."
)

CIUDADES = [
    ("Madrid", "Espana", 40.4168, -3.7038),
    ("Barcelona", "Espana", 41.3874, 2.1686),
    ("Sevilla", "Espana", 37.3891, -5.9845),
    ("Valencia", "Espana", 39.4699, -0.3763),
    ("Bilbao", "Espana", 43.2630, -2.9350),
    ("Ciudad de Mexico", "Mexico", 19.4326, -99.1332),
    ("Guadalajara", "Mexico", 20.6597, -103.3496),
    ("Buenos Aires", "Argentina", -34.6037, -58.3816),
    ("Cordoba", "Argentina", -31.4201, -64.1888),
    ("Bogota", "Colombia", 4.7110, -74.0721),
    ("Medellin", "Colombia", 6.2442, -75.5812),
    ("Lima", "Peru", -12.0464, -77.0428),
    ("Santiago", "Chile", -33.4489, -70.6693),
    ("Caracas", "Venezuela", 10.4806, -66.9036),
    ("Montevideo", "Uruguay", -34.9011, -56.1645),
    ("La Habana", "Cuba", 23.1136, -82.3666),
    ("San Juan", "Puerto Rico", 18.4655, -66.1057),
    ("Quito", "Ecuador", -0.1807, -78.4678),
    ("Panama", "Panama", 8.9824, -79.5199),
    ("Asuncion", "Paraguay", -25.2637, -57.5759),
]

NOMBRES = [
    "Maria Lopez", "Ana Garcia", "Lucia Fernandez", "Carmen Ruiz", "Sofia Martinez",
    "Laura Sanchez", "Paula Gomez", "Marta Diaz", "Elena Torres", "Claudia Ramos",
    "Valeria Ortiz", "Daniela Castro", "Patricia Vega", "Rosa Mendez", "Irene Navarro",
    "Javier Perez", "Carlos Rodriguez", "Daniel Alvarez", "Pablo Moreno", "Diego Romero",
    "Andres Gil", "Miguel Serrano", "Sergio Blanco", "Alvaro Molina", "Adrian Ortega",
    "Hugo Delgado", "Ivan Marin", "Raul Iglesias", "Oscar Rubio", "Manuel Herrera",
    "Beatriz Cano", "Silvia Prieto", "Natalia Cortes", "Andrea Rivas", "Eva Campos",
    "Veronica Suarez", "Julia Reyes", "Cristina Vidal", "Alicia Leon", "Teresa Fuentes",
]

CONTEXTOS = ["amor", "trabajo", "dinero", "salud", "espiritual", "general"]

PREGUNTAS = {
    "amor": [
        "Que energia hay en mi vida sentimental ahora mismo?",
        "Tengo una relacion que me tiene confundida, que me dice esta carta?",
        "Voy a encontrar pareja en los proximos meses?",
        "Como puedo mejorar la comunicacion con mi pareja?",
    ],
    "trabajo": [
        "Que me espera en el trabajo en los proximos meses?",
        "Me conviene aceptar la oferta que me han hecho?",
        "Como puedo desbloquear mi carrera profesional?",
        "Hay cambios laborales cerca para mi?",
    ],
    "dinero": [
        "Que dice esta carta sobre mis finanzas actuales?",
        "Es buen momento para una inversion o un cambio economico?",
        "Como puedo salir de esta situacion economica?",
        "Voy a mejorar mis ingresos este ano?",
    ],
    "salud": [
        "Que energia rodea mi bienestar fisico y emocional?",
        "Que necesito atender de mi salud en esta etapa?",
        "Por que me siento tan agotada ultimamente?",
        "Que deberia cambiar en mis habitos?",
    ],
    "espiritual": [
        "Que aprendizaje espiritual me trae esta etapa?",
        "Que debo soltar para avanzar?",
        "Que me quiere decir el universo con esta situacion?",
        "Como conecto con mi proposito?",
    ],
    "general": [
        "Que necesito saber en este momento?",
        "Cual es el tema central de mi vida ahora?",
        "Que me conviene priorizar este mes?",
        "Que bloqueo me esta frenando?",
    ],
}

FOCOS_ASTRO = [
    "vocacion profesional", "vida amorosa", "familia y raices", "dinero y recursos",
    "salud y energia", "proposito espiritual", "estudios y formacion",
    "mudanza o viaje", "proximo ano", "talentos y creatividad",
]

FOCOS_SIN = ["compatibilidad amorosa", "sociedad laboral", "amistad", "vinculo familiar", "proyecto en comun"]

SIGNOS = ["Aries", "Tauro", "Geminis", "Cancer", "Leo", "Virgo", "Libra", "Escorpio",
          "Sagitario", "Capricornio", "Acuario", "Piscis"]

PLANETAS = [
    (swe.SUN, "Sol"), (swe.MOON, "Luna"), (swe.MERCURY, "Mercurio"),
    (swe.VENUS, "Venus"), (swe.MARS, "Marte"), (swe.JUPITER, "Jupiter"),
    (swe.SATURN, "Saturno"), (swe.URANUS, "Urano"), (swe.NEPTUNE, "Neptuno"),
    (swe.PLUTO, "Pluton"),
]

ASPECTOS = [(0, "conjuncion", 6.0), (60, "sextil", 5.0), (90, "cuadratura", 6.0),
            (120, "trigono", 6.0), (180, "oposicion", 7.0)]


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


def calcular_carta(fecha, hora, lat, lon):
    d = dt.datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
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
        "aspectos": aspectos[:14],
    }


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
    return reducir(digitos(fecha))


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
    d, m, _ = fecha.split("-")
    return reducir(int(d) + int(m) + digitos(str(anio)))


def fmt_numerologia(fecha, nombre):
    voc, con = vocales_consonantes(nombre)
    return (
        f"Fecha de nacimiento: {fecha}. Nombre completo: {nombre}.\n"
        f"- Camino de vida: {camino_de_vida(fecha)}\n"
        f"- Destino/expresion: {reducir(letras_valor(nombre))}\n"
        f"- Alma (vocales): {voc}\n"
        f"- Personalidad (consonantes): {con}\n"
        f"- Anio personal 2026: {anio_personal(fecha)}"
    )


def carta_txt(c):
    orient = "invertida" if c.get("invertida") else "al derecho"
    return f"{c['nombre']} ({orient})"


def datos_carta(c):
    return c


class Builder:
    def __init__(self, rng, kb_tarot, kb_astro, kb_num):
        self.rng = rng
        self.cartas = kb_tarot["mayores"] + kb_tarot["menores"]
        self.astro = kb_astro
        self.num = kb_num

    def nacimiento(self):
        ciudad, pais, lat, lon = self.rng.choice(CIUDADES)
        anio = self.rng.randint(1950, 2005)
        mes = self.rng.randint(1, 12)
        dia = self.rng.randint(1, 28)
        hora = f"{self.rng.randint(0, 23):02d}:{self.rng.choice([0, 15, 30, 45]):02d}"
        fecha = f"{anio:04d}-{mes:02d}-{dia:02d}"
        return fecha, hora, ciudad, pais, lat, lon

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
                f"Interpreta la combinacion de las dos cartas."
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
            fecha, hora, ciudad, pais, lat, lon = self.nacimiento()
            c = calcular_carta(fecha, hora, lat, lon)
            foco = self.rng.choice(FOCOS_ASTRO)
            prompt = (
                f"Lectura de carta natal.\n\n{fmt_carta(c, ciudad, pais)}\n\n"
                f'Pregunta del consultante: "Que dice mi carta sobre mi {foco}?"\n\n'
                f"Interpreta la carta natal centrandote en ese ambito."
            )
            out.append(self.job("astro_natal", prompt, {"carta": c, "foco": foco, "ciudad": ciudad}, 1400))
        return out

    def sinastria(self, n=600):
        out = []
        for _ in range(n):
            f1, h1, c1, p1, la1, lo1 = self.nacimiento()
            f2, h2, c2, p2, la2, lo2 = self.nacimiento()
            a = calcular_carta(f1, h1, la1, lo1)
            b = calcular_carta(f2, h2, la2, lo2)
            foco = self.rng.choice(FOCOS_SIN)
            prompt = (
                f"Estudio de sinastria entre dos cartas natales.\n\n"
                f"Persona A: {fmt_carta(a, c1, p1)}\n\nPersona B: {fmt_carta(b, c2, p2)}\n\n"
                f'Pregunta: "Que nos dice la sinastria sobre nuestra {foco}?"\n\n'
                f"Compara ambas cartas e interpreta la relacion."
            )
            out.append(self.job("sinastria", prompt, {"a": a, "b": b, "foco": foco}, 1600))
        return out

    def numerologia(self, n=400):
        out = []
        for _ in range(n):
            fecha, _, _, _, _, _ = self.nacimiento()
            nombre = self.rng.choice(NOMBRES)
            foco = self.rng.choice(["camino de vida", "proposito", "anio personal", "talentos", "relaciones"])
            prompt = (
                f"Lectura numerologica.\n\n{fmt_numerologia(fecha, nombre)}\n\n"
                f'Pregunta del consultante: "Que me dice la numerologia sobre mi {foco}?"\n\n'
                f"Interpreta los numeros calculados."
            )
            out.append(self.job("numerologia", prompt, {"fecha": fecha, "nombre": nombre, "foco": foco}))
        return out

    def lectura_completa(self, n=3000):
        out = []
        for _ in range(n):
            fecha, hora, ciudad, pais, lat, lon = self.nacimiento()
            c = calcular_carta(fecha, hora, lat, lon)
            cartas = self.tirada(3)
            nombre = self.rng.choice(NOMBRES)
            ctx = self.rng.choice(CONTEXTOS)
            preg = self.rng.choice(PREGUNTAS[ctx])
            lineas = "\n".join(
                f"- {p}: {carta_txt(card)}" for p, card in zip(["pasado", "presente", "futuro"], cartas)
            )
            prompt = (
                f"Lectura completa: carta natal, tarot y numerologia.\n\n"
                f"Consultante: {nombre}.\n{fmt_carta(c, ciudad, pais)}\n\n"
                f"Tirada de tres cartas:\n{lineas}\n\n"
                f"{fmt_numerologia(fecha, nombre)}\n\n"
                f'Pregunta del consultante: "{preg}"\n\n'
                f"Integra las tres tecnicas en una lectura coherente y personalizada."
            )
            out.append(self.job("lectura_completa", prompt, {
                "carta": c, "cartas": cartas, "fecha": fecha, "nombre": nombre,
                "contexto": ctx, "ciudad": ciudad,
            }, 1800))
        return out

    def multiturno(self, n=800):
        out = []
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            carta = self.tirada(1)[0]
            preg1 = self.rng.choice(PREGUNTAS[ctx])
            seguimiento = self.rng.choice([
                "Y que deberia hacer yo al respecto?",
                "Y si la situacion no cambia en un mes?",
                "Que parte de esto depende de mi?",
                "Como afecta esto a mi entorno cercano?",
                "Que senal deberia observar para saber si voy bien?",
            ])
            previo = (
                f"En la lectura anterior salio {carta_txt(carta)} en contexto de {ctx}. "
                f"Te preguntaste: \"{preg1}\"."
            )
            prompt = (
                f"Continuacion de una consulta de tarot.\n\n{previo}\n\n"
                f'Nueva pregunta del consultante: "{seguimiento}"\n\n'
                f"Responde solo a la nueva pregunta, manteniendo el hilo de la lectura."
            )
            out.append(self.job("multiturno", prompt, {"carta": carta, "contexto": ctx}, 900))
        return out

    def etica(self, n=300):
        casos = [
            ("salud", "Tengo un bulto en el pecho y he sonado que es malo. Dime si tengo cancer."),
            ("legal", "Mi ex me quiere quitar la custodia. Dime que decide el juez."),
            ("dinero", "Deberia pedir un credito para invertir en criptomonedas? Dime cuanto voy a ganar."),
            ("terceros", "Quiero saber si mi pareja me engana. Lee su energia sin que este presente."),
            ("menores", "Mi hija de 14 anos quiere que le lea el futuro, que le digo?"),
            ("muerte", "Dime la fecha en que voy a morir."),
            ("adiccion", "Mi hermano es adicto. La carta dice que va a dejarlo solo, verdad?"),
            ("garantia", "Si pago la lectura premium, me garantizas que vuelve conmigo?"),
        ]
        out = []
        for i in range(n):
            tema, pregunta = casos[i % len(casos)]
            prompt = (
                f"Consulta delicada.\n\nPregunta del consultante: \"{pregunta}\"\n\n"
                f"Responde con honestidad, marcando los limites de la lectura y derivando a un profesional cuando corresponda."
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera la matriz de jobs sinteticos.")
    ap.add_argument("--db", default=str(ROOT / "corpus" / "jobs.db"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--only", default=None)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    builder = Builder(rng, load_kb("tarot.json"), load_kb("astrologia.json"), load_kb("numerologia.json"))
    filas = build_all(builder, args.only, args.scale)
    print(f"TOTAL jobs: {len(filas)}")
    if args.dry_run:
        return 0

    con = sqlite3.connect(args.db)
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
    con.executemany(
        "INSERT INTO jobs (bloque, system, prompt, payload, max_tokens) VALUES (?,?,?,?,?)",
        filas,
    )
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print(f"Insertados {len(filas)} jobs. Total en DB: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
