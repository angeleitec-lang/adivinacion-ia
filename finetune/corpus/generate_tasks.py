#!/usr/bin/env python3
"""Genera la matriz de trabajos sintéticos en corpus/jobs.db."""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import unicodedata
from pathlib import Path

from calculos import numerologia as calc_num
from calculos.astro import carta_natal, revolucion_solar, transitos

import fase1_prompts as fp
from cartas import NAIPES_ESPANOLES

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

# Referencias temporales de las lecturas de proyección (T35): los tránsitos se
# calculan para esta fecha y la revolución solar para este año, de forma
# determinista (igual que el año personal 2026 de numerología).
FECHA_CONSULTA = "2026-10-15"
ANIO_PROYECCION = 2026
FOCO_PROYECCION = "próximo año"

# Seguimientos del consultante para la fase 2 del multi-turno real (T16). Elegidos
# por contexto; algunos arrancan refiriéndose a lo dicho en la lectura anterior.
SEGUIMIENTOS = {
    "amor": [
        "Dijiste que hay confusión entre nosotros, ¿cómo la despejo?",
        "No me convence eso de que deba esperar, ¿qué más puedo hacer?",
        "¿Y si hago lo contrario de lo que me sugieres?",
        "Lo que me has dicho de la carta, ¿se aplica también a su lado de la relación?",
        "¿Esto significa que debo dar el paso o dejar que llegue solo?",
        "¿Y si él no siente lo mismo que yo?",
        "¿Cuánto tiempo puede durar esta situación?",
        "¿Qué error estoy cometiendo con mi pareja?",
    ],
    "trabajo": [
        "Dijiste que conviene esperar, ¿hasta cuándo debo aguantar en el empleo?",
        "No me convence eso de que no mueva ficha, ¿doy el paso?",
        "¿Y si pido el cambio que llevo tiempo pensando?",
        "Lo de la carta, ¿se refiere a mi jefe o a la empresa?",
        "¿Me conviene más la seguridad o el riesgo en este momento?",
        "¿Cómo sé si la oferta que me han hecho es buena para mí?",
        "¿Debería hablar con mi jefe o buscar fuera?",
        "¿Qué habilidad me falta para desbloquear mi carrera?",
    ],
    "dinero": [
        "Dijiste que hay que ordenar las cuentas, ¿por dónde empiezo?",
        "No me convence eso de no invertir, ¿y si pierdo la oportunidad?",
        "¿Y si hago lo contrario y pido el préstamo?",
        "Lo de la carta, ¿significa que el dinero llegará o que debo buscarlo?",
        "¿Es momento de gastar o de ahorrar?",
        "¿Cómo salgo del agujero económico en el que estoy?",
        "¿Me fío de esa oportunidad que me han ofrecido?",
        "¿Qué estoy haciendo mal con el dinero?",
    ],
    "salud": [
        "Dijiste que debo descansar, ¿cómo lo hago si no puedo parar?",
        "No me convence eso de que sea estrés, ¿y si es algo más serio?",
        "¿Y si hago caso omiso y sigo al ritmo de siempre?",
        "Lo de la carta, ¿se refiere a mi cuerpo o a mis emociones?",
        "¿Qué hábito debería cambiar primero?",
        "¿Voy a recuperarme si pongo de mi parte?",
        "¿Cuándo notaré mejoría?",
        "¿Debo preocuparme o mantener la calma?",
    ],
    "espiritual": [
        "Dijiste que suelte algo, ¿cómo sé qué es exactamente?",
        "No me convence eso de que todo tiene un propósito, ¿y el dolor?",
        "¿Y si hago lo contrario de lo que la carta me pide?",
        "Lo de la carta, ¿es una advertencia o una guía?",
        "¿Qué práctica me ayuda a conectar con esto?",
        "¿Cómo sé si estoy en el camino correcto?",
        "¿Debo meditar o actuar en el mundo?",
        "¿Qué aprendizaje me llevo de esta etapa?",
    ],
    "general": [
        "Dijiste que hay un bloqueo, ¿cómo lo identifico?",
        "No me convence eso de priorizar, ¿y si todo es urgente?",
        "¿Y si hago lo contrario de lo que me recomiendas?",
        "Lo de la carta, ¿se refiere a hoy o a las próximas semanas?",
        "¿Qué es lo primero que debo hacer mañana?",
        "¿Cómo sé si la decisión que pienso es la buena?",
        "¿Debo actuar ya o esperar una señal?",
        "¿Qué me estoy perdiendo de esta situación?",
    ],
}

INSTRUCCION_FASE2 = ("Responde solo a la nueva pregunta, manteniendo el hilo "
                     "de la lectura anterior y sin repetirla.")

def load_kb(nombre):
    p = KB_DIR / nombre
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def calcular_carta(fecha, hora, lat, lon, tz):
    """Carta natal delegada en calculos.astro, adaptada al formato de siempre.

    calculos.astro redondea los minutos (el código viejo los truncaba): la
    tolerancia de no-regresión de 1 minuto queda fijada en
    tests/test_equivalencia_calculos.py contra valores congelados.
    """
    carta = carta_natal(fecha, hora, lat, lon, tz)
    planetas = {}
    for p in carta["planetas"]:
        planetas[p["nombre"]] = {
            "signo": p["signo"],
            "grados": f"{p['grado']}°{p['minuto']:02d}'",
            "lon": p["lon"],
            "casa": p["casa"],
        }
    asc = carta["ascendente"]
    mc = carta["medio_cielo"]
    aspectos = [
        {
            "a": a["planeta_a"],
            "b": a["planeta_b"],
            "aspecto": a["aspecto"],
            "orbe": round(a["orbe"], 1),
        }
        for a in carta["aspectos"]
    ]
    return {
        "fecha": fecha, "hora": hora,
        "planetas": planetas,
        "ascendente": {"signo": asc["signo"], "grados": f"{asc['grado']}°{asc['minuto']:02d}'"},
        "mc": {"signo": mc["signo"], "grados": f"{mc['grado']}°{mc['minuto']:02d}'"},
        "aspectos": aspectos,
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


def fmt_transitos(trans, max_aspectos=12):
    """Tránsitos de calculos.astro en líneas legibles para el prompt."""
    lineas = [f"Tránsitos del día {trans['fecha_transito']}:"]
    for a in trans["aspectos"][:max_aspectos]:
        lineas.append(
            f"- {a['planeta_transito']} en tránsito hace {a['aspecto']} a su "
            f"{a['planeta_natal']} natal (casa {a['casa_natal']}, orbe {round(a['orbe'], 1)}°)"
        )
    return "\n".join(lineas)


def fmt_revolucion_solar(rs):
    """Revolución solar de calculos.astro en una línea legible para el prompt."""
    sol_rs = next((p for p in rs["carta"]["planetas"]
                   if p["nombre"] == "Sol"), None)
    if sol_rs is None:
        raise ValueError("La carta de revolución solar no contiene el Sol")
    asc = rs["ascendente"]
    return (
        f"Revolución solar del año {rs['instante_ut'][:4]}: instante {rs['instante_ut']} UT "
        f"(local {rs['instante_local']}); Sol RS en {sol_rs['signo']} "
        f"{sol_rs['grado']}°{sol_rs['minuto']:02d}'; Ascendente RS {asc['signo']} "
        f"{asc['grado']}°{asc['minuto']:02d}'."
    )


def datos_proyeccion(fecha, hora, lat, lon, tz):
    """Tránsitos del día y revolución solar del año de proyección (calculos.astro)."""
    natal = carta_natal(fecha, hora, lat, lon, tz)
    trans = transitos(natal, FECHA_CONSULTA, hora="12:00", tz=tz)
    rs = revolucion_solar(fecha, hora, lat, lon, tz, ANIO_PROYECCION)
    return trans, rs


def reducir(n):
    """Reducción pitagórica conservando maestros (delegada en calculos.numerologia)."""
    return calc_num.reducir(n)


def camino_de_vida(fecha):
    """Camino de vida (delegado en calculos.numerologia)."""
    return calc_num.camino_de_vida(fecha)


def letras_valor(nombre):
    """Suma pitagórica de las letras, con la normalización de calculos (fuente de verdad)."""
    return sum(calc_num.PITAGORICA.get(c, 0) for c in calc_num._normalizar_texto(nombre))


def vocales_consonantes(nombre):
    """(Alma, personalidad) reducidos conservando maestros (delegado en calculos)."""
    return calc_num.alma(nombre), calc_num.personalidad(nombre)


def anio_personal(fecha, anio=2026):
    """Año personal: el resultado se reduce siempre a 1-9 (delegado en calculos)."""
    return calc_num.anio_personal(fecha, anio)


def fmt_numerologia(fecha, nombre):
    voc, con = vocales_consonantes(nombre)
    return (
        f"Fecha de nacimiento: {fecha}. Nombre completo: {nombre}.\n"
        f"- Camino de vida: {camino_de_vida(fecha)}\n"
        f"- Destino/expresión: {calc_num.expresion(nombre)}\n"
        f"- Alma (vocales): {voc}\n"
        f"- Personalidad (consonantes): {con}\n"
        f"- Año personal 2026: {anio_personal(fecha)}"
    )


def carta_txt(c):
    orient = "invertida" if c.get("invertida") else "al derecho"
    return f"{c['nombre']} ({orient})"


CABECERA_REFERENCIA = ("Referencia (significados de la tradición; "
                      "úsalos como base y no inventes otros):")


def _norm(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def unir(frases):
    """Une fragmentos con '. ' y un único punto final."""
    limpias = [str(f).strip().rstrip(".").strip() for f in frases]
    limpias = [f for f in limpias if f]
    if not limpias:
        return ""
    return ". ".join(limpias) + "."


def referencia_tarot(cartas, kb_cartas, contexto=None):
    """Bloque de referencia con significados reales de la KB (funciona sin 'contextos')."""
    por_nombre = {_norm(c["nombre"]): c for c in kb_cartas}
    lineas = []
    for c in cartas:
        kb = por_nombre.get(_norm(c["nombre"]))
        if not kb:
            continue
        if c.get("invertida"):
            texto = kb.get("invertida") or kb.get("significado", "")
            orient = "invertida"
        else:
            texto = kb.get("significado", "")
            orient = "al derecho"
        frases = [f"- {c['nombre']} ({orient}): {texto}"]
        if contexto:
            ctx_txt = (kb.get("contextos") or {}).get(contexto)
            if ctx_txt:
                frases.append(f"En {contexto}: {ctx_txt}")
        claves = ", ".join(kb.get("palabras_clave", []))
        if claves:
            frases.append(f"Palabras clave: {claves}")
        lineas.append(unir(frases))
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def referencia_astro(carta, kb_astro):
    """Referencia de signos (elemento, regente, claves), simbolismo planetario y casas."""
    signos = {_norm(s["nombre"]): s for s in kb_astro.get("signos", [])}
    planetas_kb = {_norm(p["nombre"]): p for p in kb_astro.get("planetas", [])}
    casas = {str(h.get("numero")): h for h in kb_astro.get("casas", [])}
    lineas = []
    for etiqueta, signo in (
        ("Sol", carta["planetas"].get("Sol", {}).get("signo")),
        ("Luna", carta["planetas"].get("Luna", {}).get("signo")),
        ("Ascendente", carta.get("ascendente", {}).get("signo")),
    ):
        s = signos.get(_norm(signo)) if signo else None
        if s:
            claves = ", ".join(s.get("palabras_clave", []))
            lineas.append(
                f"- {etiqueta} en {signo}: elemento {s.get('elemento', 'sin dato')}, "
                f"regente {s.get('regente', 'sin dato')}, palabras clave: {claves}."
            )
    for nombre, datos in carta["planetas"].items():
        p = planetas_kb.get(_norm(nombre))
        if p and p.get("simboliza"):
            lineas.append(f"- {nombre}: {p['simboliza']}.")
    for nombre in ("Sol", "Luna", "Venus"):
        datos = carta["planetas"].get(nombre)
        if datos:
            h = casas.get(str(datos.get("casa")))
            if h and h.get("area"):
                lineas.append(f"- Casa {datos['casa']} de {nombre}: {h['area']}.")
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def referencia_numerologia(fecha, nombre, kb_num):
    """Referencia de palabras clave y áreas de cada número calculado."""
    por_numero = {e.get("numero"): e for e in kb_num}
    voc, con = vocales_consonantes(nombre)
    valores = [
        ("camino de vida", camino_de_vida(fecha)),
        ("destino/expresión", calc_num.expresion(nombre)),
        ("alma (vocales)", reducir(voc)),
        ("personalidad (consonantes)", reducir(con)),
        ("año personal", anio_personal(fecha)),
    ]
    lineas = []
    for etiqueta, n in valores:
        e = por_numero.get(n)
        if not e:
            continue
        claves = ", ".join(e.get("palabras_clave", []))
        areas = e.get("areas") or {}
        area_txt = "; ".join(f"{k}: {v}" for k, v in areas.items())
        linea = f"- {n} en {etiqueta}: {claves}."
        if area_txt:
            linea += f" Áreas: {area_txt}."
        lineas.append(linea)
    if not lineas:
        return ""
    return CABECERA_REFERENCIA + "\n" + "\n".join(lineas)


def unir_con_referencia(cuerpo, referencia, instruccion):
    partes = [cuerpo]
    if referencia:
        partes.append(referencia)
    partes.append(instruccion)
    return "\n\n".join(partes)


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
    def __init__(self, rng, kb_tarot, kb_astro, kb_num, kb_baraja=None):
        self.rng = rng
        self.kb_tarot = kb_tarot
        self.cartas = kb_tarot["mayores"] + kb_tarot["menores"]
        self.astro = kb_astro
        self.num = kb_num
        self._baraja = kb_baraja
        self._kb_fp = None
        self._universo_esp = None

    @property
    def baraja(self):
        if self._baraja is None:
            self._baraja = load_kb("baraja_espanola.json")
        return self._baraja

    def kb_fp(self):
        """Base de conocimiento con el formato que espera fase1_prompts."""
        if self._kb_fp is None:
            self._kb_fp = {
                "tarot": self.kb_tarot,
                "astrologia": self.astro,
                "numerologia": self.num,
                "baraja": self.baraja,
            }
        return self._kb_fp

    def universo_esp(self):
        if self._universo_esp is None:
            self._universo_esp = fp.universo_baraja(self.baraja, self.kb_tarot)
        return self._universo_esp

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

    def tirada_baraja(self, n):
        """Tirada sin reemplazo de la baraja española (40 naipes)."""
        elegidas = self.rng.sample(NAIPES_ESPANOLES, n)
        return [
            {
                "nombre": c["nombre"],
                "invertida": self.rng.random() < 0.35,
                "sinonimos": list(c.get("sinonimos", [])),
            }
            for c in elegidas
        ]

    def job(self, bloque, prompt, payload, max_tokens=1024):
        return (bloque, SYSTEM, prompt, json.dumps(payload, ensure_ascii=False), max_tokens)

    def tarot_1(self):
        out = []
        for c in self.cartas:
            for ctx in CONTEXTOS:
                for inv in (False, True):
                    carta = {"nombre": c["nombre"], "invertida": inv}
                    preg = self.rng.choice(PREGUNTAS[ctx])
                    prompt = unir_con_referencia(
                        f"Tirada de una carta de tarot.\n\n"
                        f"Carta: {carta_txt(carta)}.\nContexto: {ctx}.\n"
                        f'Pregunta del consultante: "{preg}"',
                        referencia_tarot([carta], self.cartas, ctx),
                        "Interpreta la carta para esta persona, en el contexto indicado.",
                    )
                    out.append(self.job("tarot_1", prompt, {"carta": carta, "contexto": ctx}))
        return out

    def tarot_2(self, n=400):
        out = []
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            cartas = self.tirada(2)
            preg = self.rng.choice(PREGUNTAS[ctx])
            prompt = unir_con_referencia(
                f"Tirada de dos cartas de tarot.\n\n"
                f"Carta 1: {carta_txt(cartas[0])}.\nCarta 2: {carta_txt(cartas[1])}.\n"
                f"Contexto: {ctx}.\nPregunta del consultante: \"{preg}\"",
                referencia_tarot(cartas, self.cartas, ctx),
                "Interpreta la combinación de las dos cartas.",
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
            prompt = unir_con_referencia(
                f"Tirada de tres cartas (pasado, presente y futuro).\n\n{lineas}\n"
                f"Contexto: {ctx}.\nPregunta del consultante: \"{preg}\"",
                referencia_tarot(cartas, self.cartas, ctx),
                "Interpreta la tirada completa, relacionando las tres posiciones.",
            )
            out.append(self.job("tarot_3", prompt, {"cartas": cartas, "contexto": ctx}))
        return out

    def cruz_celta(self, n=500):
        out = []
        pos = ["situación", "obstáculo", "raíz", "pasado", "meta", "futuro cercano",
               "actitud", "entorno", "esperanzas y miedos", "resultado"]
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            cartas = self.tirada(10)
            preg = self.rng.choice(PREGUNTAS[ctx])
            tarea = {
                "familia": "cruz_celta", "contexto": ctx, "pregunta": preg,
                "cartas": cartas, "posiciones": pos,
                "universo_cartas": [c["nombre"] for c in self.cartas],
                "calculos": {},
            }
            prompt = fp.construir_prompt(tarea, self.kb_fp())["user"]
            out.append(self.job(
                "cruz_celta", prompt,
                {"cartas": cartas, "contexto": ctx, "posiciones": pos},
                fp.RECOMENDACION_MAX_TOKENS["cruz_celta"],
            ))
        return out

    def tarot_pregunta(self, n=800):
        out = []
        for _ in range(n):
            carta = self.tirada(1)[0]
            ctx = self.rng.choice(CONTEXTOS)
            preg = self.rng.choice(PREGUNTAS[ctx])
            prompt = unir_con_referencia(
                f"Consulta de tarot con una carta.\n\n"
                f"Carta: {carta_txt(carta)}.\n"
                f'Pregunta del consultante: "{preg}"',
                referencia_tarot([carta], self.cartas, ctx),
                "Responde a la pregunta a partir de la carta.",
            )
            out.append(self.job("tarot_pregunta", prompt, {"carta": carta, "contexto": ctx}))
        return out

    def astro_natal(self, n=1500):
        out = []
        for _ in range(n):
            fecha, hora, ciudad, pais, lat, lon, tz = self.nacimiento()
            c = calcular_carta(fecha, hora, lat, lon, tz)
            foco = self.rng.choice(FOCOS_ASTRO)
            payload = {"carta": c, "foco": foco, "ciudad": ciudad}
            if foco == FOCO_PROYECCION:
                trans, rs = datos_proyeccion(fecha, hora, lat, lon, tz)
                cuerpo = (
                    f"Lectura de carta natal con proyección.\n\n"
                    f"{fmt_carta(c, ciudad, pais)}\n\n"
                    f"{fmt_transitos(trans)}\n{fmt_revolucion_solar(rs)}\n\n"
                )
                payload["transitos"] = trans
                payload["revolucion_solar"] = rs
            else:
                cuerpo = f"Lectura de carta natal.\n\n{fmt_carta(c, ciudad, pais)}\n\n"
            prompt = unir_con_referencia(
                cuerpo + f'Pregunta del consultante: "¿Qué dice mi carta sobre mi {foco}?"',
                referencia_astro(c, self.astro),
                "Interpreta la carta natal centrándote en ese ámbito.",
            )
            out.append(self.job("astro_natal", prompt, payload, 1400))
        return out

    def sinastria(self, n=600):
        out = []
        for _ in range(n):
            f1, h1, c1, p1, la1, lo1, tz1 = self.nacimiento()
            f2, h2, c2, p2, la2, lo2, tz2 = self.nacimiento()
            a = calcular_carta(f1, h1, la1, lo1, tz1)
            b = calcular_carta(f2, h2, la2, lo2, tz2)
            foco = self.rng.choice(FOCOS_SIN)
            refs = []
            ref_a = referencia_astro(a, self.astro)
            ref_b = referencia_astro(b, self.astro)
            if ref_a:
                refs.append("Referencia de la persona A:\n" + ref_a)
            if ref_b:
                refs.append("Referencia de la persona B:\n" + ref_b)
            prompt = unir_con_referencia(
                f"Estudio de sinastria entre dos cartas natales.\n\n"
                f"Persona A: {fmt_carta(a, c1, p1)}\n\nPersona B: {fmt_carta(b, c2, p2)}\n\n"
                f'Pregunta: "¿Qué nos dice la sinastria sobre nuestra {foco}?"',
                "\n\n".join(refs),
                "Compara ambas cartas e interpreta la relación.",
            )
            out.append(self.job("sinastria", prompt, {"a": a, "b": b, "foco": foco}, 1600))
        return out

    def numerologia(self, n=400):
        out = []
        for _ in range(n):
            fecha, _, _, _, _, _, _ = self.nacimiento()
            nombre = self.rng.choice(NOMBRES)
            foco = self.rng.choice(["camino de vida", "propósito", "año personal", "talentos", "relaciones"])
            prompt = unir_con_referencia(
                f"Lectura numerológica.\n\n{fmt_numerologia(fecha, nombre)}\n\n"
                f'Pregunta del consultante: "¿Qué me dice la numerología sobre mi {foco}?"',
                referencia_numerologia(fecha, nombre, self.num),
                "Interpreta los números calculados.",
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
            num = {
                "camino_de_vida": calc_num.camino_de_vida(fecha),
                "expresion": calc_num.expresion(nombre),
                "alma": calc_num.reducir(calc_num.alma(nombre)),
                "personalidad": calc_num.reducir(calc_num.personalidad(nombre)),
                "anio_personal": calc_num.anio_personal(fecha, 2026),
            }
            tarea = {
                "familia": "lectura_completa", "pregunta": preg, "contexto": ctx,
                "cartas": cartas, "nombre": nombre, "ciudad": ciudad,
                "universo_cartas": [c2["nombre"] for c2 in self.cartas],
            }
            calc = {"carta_natal": c, "numerologia": num}
            prompt = fp.construir_prompt(tarea, self.kb_fp(), calc)["user"]
            out.append(self.job("lectura_completa", prompt, {
                "carta": c, "cartas": cartas, "fecha": fecha, "nombre": nombre,
                "contexto": ctx, "ciudad": ciudad,
            }, fp.RECOMENDACION_MAX_TOKENS["lectura_completa"]))
        return out

    def multiturno(self, n=800):
        """Multi-turno real en dos fases: el prompt es la lectura de fase 1 y el
        payload lleva el seguimiento y la instrucción de la fase 2 (T16)."""
        out = []
        for _ in range(n):
            ctx = self.rng.choice(CONTEXTOS)
            carta = self.tirada(1)[0]
            preg1 = self.rng.choice(PREGUNTAS[ctx])
            seguimiento = self.rng.choice(SEGUIMIENTOS[ctx])
            prompt = unir_con_referencia(
                f"Tirada de una carta de tarot.\n\n"
                f"Carta: {carta_txt(carta)}.\nContexto: {ctx}.\n"
                f'Pregunta del consultante: "{preg1}"',
                referencia_tarot([carta], self.cartas, ctx),
                "Interpreta la carta para esta persona, en el contexto indicado.",
            )
            payload = {
                "fase2": {"seguimiento": seguimiento, "instruccion": INSTRUCCION_FASE2},
                "carta": carta,
                "contexto": ctx,
            }
            out.append(self.job("multiturno", prompt, payload, 900))
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


    def _job_baraja(self, familia, n):
        ctx = self.rng.choice(CONTEXTOS)
        cartas = self.tirada_baraja(n)
        preg = self.rng.choice(PREGUNTAS[ctx])
        posiciones = list(fp.POSICIONES_ESPAÑOLA.get(familia, []))
        tarea = {
            "familia": familia, "mazo": "espanol", "contexto": ctx, "pregunta": preg,
            "cartas": cartas, "universo_cartas": self.universo_esp(),
            "calculos": {},
        }
        if posiciones:
            tarea["posiciones"] = posiciones
        prompt = fp.construir_prompt(tarea, self.kb_fp())["user"]
        payload = {"cartas": cartas, "contexto": ctx, "mazo": "espanol"}
        if posiciones:
            payload["posiciones"] = posiciones
        return self.job(familia, prompt, payload, fp.RECOMENDACION_MAX_TOKENS[familia])

    def espanola_1(self, n=400):
        return [self._job_baraja("espanola_1", 1) for _ in range(n)]

    def espanola_3(self, n=900):
        return [self._job_baraja("espanola_3", 3) for _ in range(n)]

    def espanola_5(self, n=400):
        return [self._job_baraja("espanola_5", 5) for _ in range(n)]

    def espanola_7(self, n=200):
        return [self._job_baraja("espanola_7", 7) for _ in range(n)]


TARGETS = {
    "tarot_1": 936, "tarot_2": 400, "tarot_3": 1400, "cruz_celta": 500,
    "tarot_pregunta": 800, "astro_natal": 1500, "sinastria": 600,
    "numerologia": 400, "lectura_completa": 3000, "multiturno": 800, "etica": 300,
    "espanola_1": 400, "espanola_3": 900, "espanola_5": 400, "espanola_7": 200,
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
        "espanola_1": lambda: builder.espanola_1(TARGETS["espanola_1"]),
        "espanola_3": lambda: builder.espanola_3(TARGETS["espanola_3"]),
        "espanola_5": lambda: builder.espanola_5(TARGETS["espanola_5"]),
        "espanola_7": lambda: builder.espanola_7(TARGETS["espanola_7"]),
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
    builder = Builder(rng, load_kb("tarot.json"), load_kb("astrologia.json"),
                      load_kb("numerologia.json"), load_kb("baraja_espanola.json"))
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
