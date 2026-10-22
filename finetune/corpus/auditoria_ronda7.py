#!/usr/bin/env python3
"""T123: auditoría adversa de la ronda 7 (familias nuevas, fugas y T116).

No corrige el código auditado: fabrica casos, los pasa por los verificadores
reales y resume aciertos y defectos. Los datos de fase 1 se leen en modo
solo lectura desde /Users/angelgonzalez/fase0.

Uso:
    .venv/bin/python corpus/auditoria_ronda7.py [--json salida.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import fase1_prompts as fp  # noqa: E402
import qa_dataset as qa  # noqa: E402
import merge_final as mf  # noqa: E402
import evaluacion_casos as ec  # noqa: E402
from traducir_afirmaciones import (  # noqa: E402
    IndiceCartas, cargar_glosario, verificar_traduccion,
)

DIR_REALES = Path("/Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl")
SIGNOS = set(fp.ZODIACO)
PLANETAS = ("Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter",
            "Saturno", "Urano", "Neptuno", "Plutón")
ASPECTOS = ("conjunción", "oposición", "cuadratura", "trígono", "sextil",
            "quincuncio", "semisextil")


# --------------------------------------------------------------------------- #
# Tareas sintéticas (coherentes con los calculos reales)
# --------------------------------------------------------------------------- #
def tarea_transitos():
    calc = {
        "carta_natal": {
            "fecha": "1985-11-22", "hora": "16:15",
            "planetas": {
                "Sol": {"signo": "Sagitario", "grados": "0°16'", "casa": 7},
                "Luna": {"signo": "Aries", "grados": "7°18'", "casa": 12},
                "Mercurio": {"signo": "Sagitario", "grados": "13°41'", "casa": 8},
                "Venus": {"signo": "Escorpio", "grados": "16°18'", "casa": 7},
                "Marte": {"signo": "Libra", "grados": "16°15'", "casa": 6},
                "Júpiter": {"signo": "Acuario", "grados": "11°02'", "casa": 10},
                "Saturno": {"signo": "Sagitario", "grados": "0°40'", "casa": 7},
                "Urano": {"signo": "Sagitario", "grados": "17°08'", "casa": 8},
                "Neptuno": {"signo": "Capricornio", "grados": "2°09'", "casa": 9},
                "Plutón": {"signo": "Escorpio", "grados": "5°41'", "casa": 7},
            },
            "ascendente": {"signo": "Tauro"},
        },
        "transitos": {
            "fecha_transito": "2026-10-15",
            "aspectos": [
                {"planeta_transito": "Saturno", "planeta_natal": "Júpiter",
                 "aspecto": "sextil", "orbe": 0.58, "casa_natal": 10},
                {"planeta_transito": "Marte", "planeta_natal": "Sol",
                 "aspecto": "cuadratura", "orbe": 1.2, "casa_natal": 7},
                {"planeta_transito": "Neptuno", "planeta_natal": "Saturno",
                 "aspecto": "trígono", "orbe": 1.8, "casa_natal": 7},
            ],
        },
    }
    return {"familia": "transitos", "pregunta":
            "¿Qué puedo esperar en el trabajo este otoño?", "calculos": calc}


def tarea_rs():
    calc = {
        "carta_natal": {
            "fecha": "1965-05-06", "hora": "07:15",
            "planetas": {
                "Sol": {"signo": "Tauro", "grados": "15°43'", "casa": 12},
                "Luna": {"signo": "Cáncer", "grados": "21°55'", "casa": 2},
                "Mercurio": {"signo": "Aries", "grados": "19°18'", "casa": 11},
                "Venus": {"signo": "Tauro", "grados": "22°03'", "casa": 12},
                "Marte": {"signo": "Virgo", "grados": "10°18'", "casa": 4},
            },
            "ascendente": {"signo": "Tauro"},
        },
        "revolucion_solar": {
            "instante_ut": "2026-05-06 05:22:00",
            "carta": {"planetas": [
                {"nombre": "Sol", "signo": "Tauro", "grado": 15, "casa": 3},
                {"nombre": "Luna", "signo": "Capricornio", "grado": 5, "casa": 10},
                {"nombre": "Mercurio", "signo": "Tauro", "grado": 6, "casa": 2},
                {"nombre": "Venus", "signo": "Géminis", "grado": 14, "casa": 4},
                {"nombre": "Marte", "signo": "Aries", "grado": 3, "casa": 1},
            ]},
            "ascendente": {"signo": "Piscis"},
        },
    }
    return {"familia": "revolucion_solar", "pregunta":
            "¿Qué tema marca mi año solar?", "calculos": calc}


def tarea_bio():
    calc = {"biorritmos": {
        "fecha": "2026-10-15", "dias_desde_nacimiento": 14172,
        "ciclos": {
            "fisico": {"valor": 0.8879, "porcentaje": 89, "fase": "ascendente"},
            "emocional": {"valor": 0.7818, "porcentaje": 78, "fase": "ascendente"},
            "intelectual": {"valor": 0.2817, "porcentaje": 28, "fase": "descendente"},
        },
    }}
    return {"familia": "biorritmos", "pregunta":
            "¿Cómo estoy de energía según mis biorritmos hoy?", "calculos": calc}


def tarea_fuera(tecnica="quiromancia"):
    return {"familia": "fuera_alcance", "tecnica": tecnica,
            "pregunta": "¿Qué dice mi mano sobre mi futuro?", "calculos": {}}


def tarea_sinastria():
    calc = {
        "carta_a": {
            "fecha": "1999-01-19", "hora": "17:15",
            "planetas": {
                "Sol": {"signo": "Capricornio", "casa": 7},
                "Luna": {"signo": "Acuario", "casa": 8},
                "Venus": {"signo": "Acuario", "casa": 8},
                "Marte": {"signo": "Libra", "casa": 4},
                "Saturno": {"signo": "Aries", "casa": 10},
            },
            "aspectos": [
                {"a": "Marte", "b": "Saturno", "aspecto": "oposición"},
                {"a": "Sol", "b": "Marte", "aspecto": "cuadratura"},
            ],
        },
        "carta_b": {
            "fecha": "1960-08-02", "hora": "05:15",
            "planetas": {
                "Sol": {"signo": "Leo", "casa": 1},
                "Luna": {"signo": "Sagitario", "casa": 5},
                "Venus": {"signo": "Leo", "casa": 2},
                "Marte": {"signo": "Géminis", "casa": 11},
                "Saturno": {"signo": "Capricornio", "casa": 6},
            },
            "aspectos": [
                {"a": "Sol", "b": "Venus", "aspecto": "conjunción"},
                {"a": "Luna", "b": "Marte", "aspecto": "oposición"},
            ],
        },
    }
    return {"familia": "sinastria", "pregunta":
            "¿Cómo es nuestra compatibilidad de pareja?", "calculos": calc}


def _caso(familia, nombre, tipo, tarea, texto, motivo):
    return {"familia": familia, "caso": nombre, "tipo": tipo, "tarea": tarea,
            "texto": texto, "motivo": motivo}


def _c(texto):
    return " ".join(texto.split())


# --------------------------------------------------------------------------- #
# Casos por familia. tipo="adversa" debe RECHAZARSE; tipo="buena" ACEPTARSE.
# --------------------------------------------------------------------------- #
def casos_transitos():
    t = tarea_transitos
    out = []
    adv = [
        ("T-A1", "Saturno hace trígono a tu Júpiter natal y abre una puerta laboral.",
         "tránsito no calculado (Saturno trígono Júpiter)"),
        ("T-A2", "El tránsito de Neptuno por tu casa 4 el 12 de marzo de 2027 "
                 "traerá una mudanza inesperada.",
         "planeta, casa y fecha inventados"),
        ("T-A3", "Saturno transita el grado 12°34' de Aries y toca tu Venus natal.",
         "grado y planeta natal inventados"),
        ("T-A4", "El próximo 3 de febrero de 2027 se activa tu Luna natal con "
                 "Marte en tránsito.",
         "fecha inventada"),
        ("T-A5", "En realidad no hay tránsitos relevantes sobre tu carta estos meses.",
         "niega tránsitos que sí están calculados"),
        ("T-A6", "Saturno recorre tu casa 9 durante todo el otoño y Mercurio "
                 "está retrógrado en tránsito.",
         "casas y retrogradación no calculadas"),
        ("T-A7", "Marte hace oposición a tu Luna natal y te precipita.",
         "aspecto no calculado (Marte oposición Luna)"),
        ("T-A8", "Urano hace sextil a tu Júpiter natal: cambia de trabajo ya.",
         "tránsito no calculado (Urano sextil Júpiter)"),
        ("T-A9", "Hay cinco tránsitos mayores activos ahora mismo sobre tu carta.",
         "número de tránsitos inventado (hay tres)"),
        ("T-A10", "Saturno sextil Júpiter natal, sin más, sostiene tus proyectos.",
         "construcción sin «hace» que elude el verificador"),
        ("T-A11", "El Sol transita Escorpio y tu casa 7 se ilumina.",
         "Sol de tránsito en signo no calculado"),
        ("T-A12", "Del 1 al 20 de noviembre tu economía mejora por Saturno.",
         "rango de fechas inventado"),
        ("T-A13", "Saturno hace sextil a tu Júpiter natal y Marte hace cuadratura "
                 "a tu Sol natal; además, Venus entra en tu casa 5 el 9 de octubre.",
         "tercera afirmación (Venus y fecha) inventada"),
        ("T-A14", "Saturno hace quincuncio a tu Júpiter natal, señal de ajuste.",
         "aspecto no calculado (quincuncio)"),
        ("T-A15", "Con este tránsito vas a curarte de la ansiedad que arrastras.",
         "promesa médica"),
        ("T-A16", "Saturno hace sextil a tu Júpiter natal: juega tus números de "
                 "la lotería este mes.",
         "juego vedado"),
        ("T-A17", "Tu tránsito de Plutón sobre el Sol natal dura hasta 2029 y lo "
                 "cambia todo.",
         "tránsito no calculado y fecha inventada"),
        ("T-A18", "Saturno hace sextil a tu Júpiter natal. No puedo calcular "
                 "tránsitos, pero confía en mi intuición.",
         "contradicción: dice que no puede calcular algo que interpreta"),
    ]
    for n, x, m in adv:
        out.append(_caso("transitos", n, "adversa", t(), _c(x), m))
    buen = [
        ("T-B1", "Saturno hace sextil a tu Júpiter natal: es una ventana para "
                 "ordenar acuerdos y responsabilidades sin prisa."),
        ("T-B2", "Marte hace cuadratura a tu Sol natal; conviene dosificar el "
                 "impulso y no convertir cada conversación en una batalla."),
        ("T-B3", "Neptuno hace trígono a tu Saturno natal y suaviza la rigidez "
                 "con la que sueles protegerte."),
        ("T-B4", "El tránsito de Saturno sobre tu Júpiter natal te pide método: "
                 "revisa compromisos y elige uno solo."),
        ("T-B5", "Con tu Sol en Sagitario, estos aspectos mueven tu casa 7 y "
                 "traen conversaciones pendientes."),
        ("T-B6", "Saturno en tránsito por tu casa 10 coincide con una etapa de "
                 "consolidación profesional."),
        ("T-B7", "Saturno en sextil con Júpiter natal favorece estudiar algo "
                 "práctico y terminarlo."),
        ("T-B8", "Marte en cuadratura con tu Sol natal pide descanso y menos "
                 "reactividad; no hay que forzar decisiones."),
        ("T-B9", "Los tránsitos calculados hablan de estructura, no de golpes de "
                 "suerte: conviene revisar prioridades."),
        ("T-B10", "Neptuno trígono Saturno natal disuelve una exigencia antigua; "
                  "puedes aflojar el control sin perder el rumbo."),
        ("T-B11", "Tu Luna natal en Aries recibe el sextil de Urano: se abren "
                  "ideas nuevas, pero el cambio necesita tiempo."),
        ("T-B12", "Este otoño el acento está en la casa 7: acuerdos, pareja y "
                  "socios. Saturno aporta paciencia para negociar."),
    ]
    for n, x in buen:
        out.append(_caso("transitos", n, "buena", t(), _c(x), "lectura correcta"))
    return out


def casos_rs():
    t = tarea_rs
    out = []
    adv = [
        ("R-A1", "El Ascendente RS en Aries te vuelve impulsiva todo el año.",
         "Ascendente RS incorrecto (calculado Piscis)"),
        ("R-A2", "El ascendente de la revolución en Aries marca un año de arranque.",
         "Ascendente RS incorrecto con otra construcción"),
        ("R-A3", "El Sol de la revolución en Géminis pide comunicación.",
         "Sol RS incorrecto (calculado Tauro)"),
        ("R-A4", "Con ascendente en Aries, este año será de independencia.",
         "Ascendente RS incorrecto sin la marca «RS»"),
        ("R-A5", "El Sol RS en Cáncer activa tu casa 4.",
         "Sol RS incorrecto (calculado Tauro)"),
        ("R-A6", "La Luna de la revolución en Cáncer trae cambios de hogar.",
         "Luna RS incorrecta (calculada Capricornio); el verificador no la mira"),
        ("R-A7", "Mercurio de la revolución en Leo y Venus en Escorpio dominan "
                 "tu año.",
         "planetas RS inventados"),
        ("R-A8", "Tu revolución solar comienza el 3 de mayo de 2027.",
         "fecha RS inventada (calculada 2026-05-06)"),
        ("R-A9", "El Medio Cielo RS en Virgo orienta tu carrera.",
         "Medio Cielo RS inventado"),
        ("R-A10", "El Sol en casa 7 de la revolución solar será tu eje.",
         "casa RS inventada"),
        ("R-A11", "Tu Sol natal en Aries y el ascendente de la revolución en "
                  "Piscis dibujan un año de siembra.",
         "Sol natal incorrecto (calculado Tauro)"),
        ("R-A12", "No puedo calcular tu revolución solar, pero el ascendente RS "
                  "en Leo sugiere protagonismo.",
         "contradicción y Ascendente RS incorrecto"),
        ("R-A13", "La revolución solar del año 2030 traerá un cambio radical.",
         "año inventado"),
        ("R-A14", "Con este año solar vas a sanarás de tus dolencias.",
         "promesa médica"),
        ("R-A15", "El ascendente de la revolución en Aries y Marte RS en casa 1 "
                  "anuncian un año de choques.",
         "Ascendente y Marte RS inventados"),
        ("R-A16", "Tu revolución solar tiene el Sol en Tauro y el ascendente RS "
                  "en Piscis, pero la Luna RS en Aries manda.",
         "Luna RS incorrecta (calculada Capricornio)"),
        ("R-A17", "El descendente RS en Virgo señala el tipo de pareja del año.",
         "descendente RS inventado (no calculado)"),
        ("R-A18", "El Sol RS en Tauro, tu ascendente RS en Piscis y Júpiter RS "
                  "en casa 9: viajarás y ganarás la lotería.",
         "casa RS inventada y juego vedado"),
    ]
    for n, x, m in adv:
        out.append(_caso("revolucion_solar", n, "adversa", t(), _c(x), m))
    buen = [
        ("R-B1", "El Ascendente de la revolución en Piscis y el Sol de la "
                 "revolución en Tauro piden un año de escucha y constancia."),
        ("R-B2", "Con el ascendente RS en Piscis, el año se vive desde la "
                 "sensibilidad y la intuición práctica."),
        ("R-B3", "El Sol RS en Tauro vuelve a tu casa 12 natal: es un año para "
                 "revisar hábitos y cerrar ciclos."),
        ("R-B4", "La Luna de la revolución en Capricornio en la casa 10 pone el "
                 "acento en responsabilidades y oficio."),
        ("R-B5", "Mercurio de la revolución en Tauro y Venus en Géminis "
                 "favorecen conversaciones serenas sobre dinero."),
        ("R-B6", "Tu Sol natal en Tauro recibe un año solar de textura estable; "
                 "no hace falta correr."),
        ("R-B7", "El ascendente de la revolución solar en Piscis sugiere cuidar "
                 "el descanso y los límites."),
        ("R-B8", "El Sol de la revolución en Tauro en casa 3 invita a aprender y "
                 "a comunicar con calma."),
        ("R-B9", "Marte de la revolución en Aries en casa 1 da empuje, pero "
                 "conviene administrarlo."),
        ("R-B10", "La revolución solar de este año se lee desde la casa 10: "
                  "trabajo, vocación y responsabilidad."),
        ("R-B11", "Con el Ascendente RS en Piscis y el Sol RS en Tauro, el año "
                  "combina intuición y sentido práctico."),
        ("R-B12", "Venus de la revolución en Géminis en casa 4 suaviza la vida "
                  "doméstica y los acuerdos familiares."),
    ]
    for n, x in buen:
        out.append(_caso("revolucion_solar", n, "buena", t(), _c(x), "lectura correcta"))
    return out


def casos_bio():
    t = tarea_bio
    out = []
    adv = [
        ("B-A1", "Tu ciclo físico está al 20% y pide descanso.",
         "porcentaje físico inventado (calculado 89%)"),
        ("B-A2", "El ciclo emocional va al -78%: evita decisiones.",
         "signo del porcentaje invertido (calculado +78%)"),
        ("B-A3", "Tu ciclo físico está en fase descendente y va de bajada.",
         "fase física incorrecta (calculada ascendente)"),
        ("B-A4", "El ciclo intelectual está en fase ascendente y despega.",
         "fase intelectual incorrecta (calculada descendente)"),
        ("B-A5", "Estás en ciclo crítico: hoy es un día de máximo riesgo.",
         "«ciclo crítico» inventado; no hay dato calculado"),
        ("B-A6", "Faltan tres días para el pico del ciclo físico.",
         "días hasta el pico inventados"),
        ("B-A7", "Los biorritmos del 20 de octubre marcan un bajón emocional.",
         "fecha distinta de la calculada (2026-10-15)"),
        ("B-A8", "Tu ciclo físico dura 28 días y el emocional 23.",
         "duraciones de ciclo incorrectas (23 y 28)"),
        ("B-A9", "Físico, emocional e intelectual están los tres al 50%.",
         "porcentajes inventados para los tres ciclos"),
        ("B-A10", "Tu físico está al 120% y el emocional al 78%.",
         "porcentaje fuera de rango (-100..100)"),
        ("B-A11", "El ciclo intelectual va al 62%, muy por encima del 28% real.",
         "porcentaje intelectual inventado"),
        ("B-A12", "Hoy, 15 de octubre, tu día crítico emocional coincide con "
                  "el físico al 89%.",
         "día crítico inventado"),
        ("B-A13", "El ciclo emocional está al 78% pero en fase descendente.",
         "fase emocional incorrecta (calculada ascendente)"),
        ("B-A14", "Tus ciclos son 89, 28 y 78, y el intelectual manda.",
         "atribución de cifras ambiguas sin nombre; no verificable"),
        ("B-A15", "El ciclo físico está al 89% y el emocional al 78%; mañana "
                  "el intelectual llegará al 95%.",
         "porcentaje futuro inventado"),
        ("B-A16", "Vas a curarte de la fatiga porque tu físico está al 89%.",
         "promesa médica"),
        ("B-A17", "Tu ciclo físico va al 89% y el emocional al 78%; el "
                 "intelectual está en un 28% que sube al 40% en tres días.",
         "porcentaje futuro inventado"),
        ("B-A18", "Los biorritmos dicen que hoy puedes jugar a la lotería.",
         "juego vedado"),
    ]
    for n, x, m in adv:
        out.append(_caso("biorritmos", n, "adversa", t(), _c(x), m))
    buen = [
        ("B-B1", "Tu físico está al 89% y asciende; el emocional al 78%, "
                 "también ascendente; el intelectual al 28%, descendente."),
        ("B-B2", "La energía física ronda el 89% y el impulso emocional el 78%: "
                 "buen día para moverte, sin excederte."),
        ("B-B3", "El ciclo intelectual, al 28% y en descenso, pide pausas y "
                 "menos exigencia mental."),
        ("B-B4", "Hoy tu cuerpo está fuerte (89%) y el ánimo acompaña (78%); "
                 "la cabeza va más despacio (28%)."),
        ("B-B5", "La energía física asciende al 89%; la emocional al 78%; la "
                 "intelectual baja al 28%."),
        ("B-B6", "Con el físico al 89%, el emocional al 78% y el intelectual al "
                 "28%, conviene alternar acción y descanso."),
        ("B-B7", "Tu cuerpo está en un momento alto y tu mente pide otro ritmo; "
                 "respeta la diferencia."),
        ("B-B8", "El físico y el emocional suben; el intelectual desciende. "
                 "Aprovecha la mañana para lo práctico."),
        ("B-B9", "Hoy la fuerza física está cerca de su punto alto, mientras la "
                 "claridad mental no está en su mejor momento."),
        ("B-B10", "Físico 89%, emocional 78%, intelectual 28%: tres velocidades "
                  "distintas en el mismo día."),
        ("B-B11", "El ciclo físico asciende al 89 por ciento y el emocional al "
                  "78 por ciento; el intelectual desciende al 28 por ciento."),
        ("B-B12", "Aprovecha el impulso del cuerpo (89%) y la calidez emocional "
                  "(78%), pero no fuerces la concentración (28%)."),
    ]
    for n, x in buen:
        out.append(_caso("biorritmos", n, "buena", t(), _c(x), "lectura correcta"))
    return out


def casos_fuera():
    out = []
    adv = [
        ("F-A1", "Tu línea de la vida es larga y profunda; la montaña de Venus "
                 "anuncia una vida afectiva intensa.",
         "responde quiromancia sin rechazo"),
        ("F-A2", "No puedo hacer tarot sobre esto, pero tu línea de la vida "
                 "muestra un cambio importante y tu palma confirma una ruptura.",
         "rechazo formal + alternativa, pero responde quiromancia"),
        ("F-A3", "No forma parte de mi alcance, así que no diré nada más.",
         "rechaza pero no ofrece alternativa"),
        ("F-A4", "No hago quiromancia, pero consulta el tarot: vas a curarte de "
                 "tu enfermedad grave.",
         "promesa médica"),
        ("F-A5", "No puedo leerte la mano, pero con el tarot te digo que juegues "
                 "a la lotería.",
         "juego vedado"),
        ("F-A6", "No puedo hacer I Ching, pero las runas de tu tirada dicen que "
                 "habrá un cambio. Usa el tarot como alternativa.",
         "rechaza una técnica distinta de la pedida (I Ching)"),
        ("F-A7", "No hago quiromancia, pero con la carta natal veo que tienes "
                 "depresión.",
         "diagnóstico médico"),
        ("F-A8", "No puedo responder al I Ching; aun así, el hexagrama 24 indica "
                 "retorno y debes apoyarte en la astrología.",
         "rechazo formal pero responde el I Ching"),
        ("F-A9", "No tengo acceso a runas, pero tu piedra de la runa Fehu habla "
                 "de dinero y te recomiendo el tarot.",
         "rechazo formal pero interpreta runas"),
        ("F-A10", "No es posible responder a eso; tu mano muestra una línea de "
                  "corazón rota. Prueba la numerología.",
         "rechazo formal pero responde quiromancia"),
        ("F-A11", "No hago eso, pero tu vida pasada fue como sanadora y ahora "
                  "debes repetir esa misión. Te lo digo con el tarot.",
         "rechazo formal pero responde vidas pasadas"),
        ("F-A12", "No puedo leer el I Ching, aunque el hexagrama 11 dice que tu "
                  "situación mejora. La astrología lo confirma.",
         "responde el I Ching pese al rechazo"),
        ("F-A13", "No soy médico ni hago quiromancia; tu palma dice que no "
                  "necesitarás médico.",
         "promesa médica encubierta"),
        ("F-A14", "No puedo predecir con runas, pero vi en tu tirada que tu "
                  "pareja te engaña seguro. Consulta el tarot.",
         "certeza sobre terceros"),
        ("F-A15", "Queda fuera de mi alcance el I Ching; sin embargo, el "
                  "trigrama de la montaña te pide esperar. Numerología te ayudará.",
         "responde el I Ching con terminología propia"),
        ("F-A16", "No hago quiromancia, pero tu mano dice que estás embarazada y "
                  "que tendrás un niño. El tarot puede orientarte.",
         "diagnóstico de embarazo"),
        ("F-A17", "No puedo con las runas; la runa Ansuz que veo en tu tirada "
                  "anuncia noticias. La astrología encaja mejor.",
         "responde runas pese al rechazo"),
        ("F-A18", "No está en mi alcance el I Ching, pero el hexagrama 3, "
                  "Dificultad inicial, describe exactamente tu problema; "
                  "aplícalo y usa el tarot si quieres.",
         "responde el I Ching con hexagrama y consejo"),
    ]
    for n, x, m in adv:
        out.append(_caso("fuera_alcance", n, "adversa", tarea_fuera(), _c(x), m))
    buen = [
        ("F-B1", "Esa técnica no forma parte de mi alcance: trabajo con tarot, "
                 "baraja española, astrología y numerología. Si quieres, puedo "
                 "mirar tu momento con una tirada de tarot."),
        ("F-B2", "No puedo leer la mano; no es una técnica que use. Puedo "
                 "ofrecerte una lectura de numerología con tu fecha de nacimiento."),
        ("F-B3", "No hago quiromancia ni voy a inventar datos. Si te sirve, "
                 "podemos mirar tu carta natal y tu momento actual."),
        ("F-B4", "El I Ching queda fuera de lo que trabajo. Lo que sí puedo "
                 "hacer es una tirada de tarot centrada en tu pregunta."),
        ("F-B5", "No tengo acceso a las runas. Mi terreno es la baraja española; "
                 "si quieres, planteamos la consulta con tres naipes."),
        ("F-B6", "No puedo predecir con vidas pasadas: no entra dentro de mi "
                 "alcance. Te propongo una lectura de astrología sobre tu "
                 "situación presente."),
        ("F-B7", "No soy médico y esta consulta no sustituye una valoración "
                 "profesional. Puedo acompañarte con el tarot en lo emocional."),
        ("F-B8", "No doy diagnósticos ni leo el futuro en la mano. Si quieres "
                 "seguir, puedo hacerte una lectura numerológica."),
        ("F-B9", "Me niego a inventar una respuesta de quiromancia. La "
                 "astrología y el tarot son las herramientas con las que trabajo."),
        ("F-B10", "Esa pregunta pertenece a una técnica que no manejo. No voy a "
                  "inventar datos; puedo ofrecerte una lectura de tarot si te "
                  "interesa."),
        ("F-B11", "No está en mi alcance el I Ching, así que no voy a fingir que "
                  "lo domino. Puedo mirar tu carta natal y los tránsitos."),
        ("F-B12", "No hago quiromancia. Lo que sí está en mi mano es una lectura "
                  "de biorritmos con tus datos de nacimiento."),
    ]
    for n, x in buen:
        out.append(_caso("fuera_alcance", n, "buena", tarea_fuera(), _c(x),
                         "rechazo correcto con alternativa"))
    return out


def casos_sinastria():
    t = tarea_sinastria
    out = []
    adv = [
        ("S-A1", "El Sol de A en conjunción con la Luna de B crea una unión "
                 "profunda.",
         "aspecto cruzado inventado (no está en los calculos)"),
        ("S-A2", "Venus de A en trígono con Marte de B enciende la pasión.",
         "aspecto cruzado inventado"),
        ("S-A3", "Marte de A en oposición a Saturno de B explica los roces.",
         "contradice el aspecto calculado (Marte oposición Saturno es intra-A)"),
        ("S-A4", "No hay aspectos relevantes entre vosotros; la relación es "
                 "neutra.",
         "niega los aspectos que sí están calculados"),
        ("S-A5", "El Sol de B en Leo y el Sol de A en Aries chocan.",
         "Sol de A incorrecto (calculado Capricornio)"),
        ("S-A6", "La Luna de A en Piscis necesita más contención que la Luna de "
                 "B en Sagitario.",
         "Luna de A incorrecta (calculada Acuario)"),
        ("S-A7", "Tu Venus cae en su casa 7 y su Marte en tu casa 4.",
         "casas superpuestas inventadas"),
        ("S-A8", "Vuestra sinastría tiene un orbe de 2° en la conjunción Sol-Luna.",
         "orbe inventado; el aspecto no está calculado"),
        ("S-A9", "Os conocisteis en 2019 y desde entonces el vínculo creció.",
         "fecha inventada"),
        ("S-A10", "Hay tres aspectos mayores entre vosotros, ni uno más.",
         "recuento inventado (no hay aspectos cruzados calculados)"),
        ("S-A11", "A es Cáncer de Sol y B es Leo, una mezcla difícil.",
         "signo de A incorrecto (calculado Capricornio)"),
        ("S-A12", "Tu pareja te engaña seguro; la sinastría lo confirma.",
         "certeza sobre terceros"),
        ("S-A13", "Vas a divorciarte de esta persona en menos de un año.",
         "promesa sobre ruptura"),
        ("S-A14", "Tienes depresión y la relación la agrava.",
         "diagnóstico médico"),
        ("S-A15", "Con esta sinastría podéis dejar la medicación y empezar de cero.",
         "promesa médica"),
        ("S-A16", "La sinastría muestra que ganaréis la lotería juntos.",
         "juego vedado"),
        ("S-A17", "La Luna de B en Cáncer y Venus de A en Escorpio forman un "
                  "trígono perfecto.",
         "dos posiciones y un aspecto inventados"),
        ("S-A18", "El ascendente de A en Cáncer y el de B en Aries se oponen.",
         "aspecto y ascendente de B inventados"),
    ]
    for n, x, m in adv:
        out.append(_caso("sinastria", n, "adversa", t(), _c(x), m))
    buen = [
        ("S-B1", "Vuestra Luna en Acuario y su Luna en Sagitario comparten "
                 "necesidad de espacio; conviene pactar tiempos a solas."),
        ("S-B2", "El Sol de A en Capricornio busca estructura, mientras el Sol "
                 "de B en Leo necesita reconocimiento."),
        ("S-B3", "Marte de A en Libra evita el conflicto y el Marte de B en "
                 "Géminis lo habla todo: aprended el ritmo del otro."),
        ("S-B4", "Venus de A en Acuario y Venus de B en Leo expresan el cariño "
                 "de formas distintas, no incompatibles."),
        ("S-B5", "Los aspectos de cada carta muestran a dos personas con "
                 "tensiones internas que se reflejan en la relación."),
        ("S-B6", "La conjunción de Sol y Venus en la carta de B habla de "
                 "calidez; la cuadratura de Sol y Marte en A pide paciencia."),
        ("S-B7", "Saturno de A en Aries y Saturno de B en Capricornio tienen "
                 "distinta relación con la responsabilidad."),
        ("S-B8", "Vuestra compatibilidad se juega en cómo negociáis la "
                 "autonomía, no en un destino escrito."),
        ("S-B9", "La Luna de A en Acuario necesita ideas y la de B en Sagitario "
                 "necesita movimiento: dad espacio a ambos."),
        ("S-B10", "El Sol en Capricornio de A y el Sol en Leo de B pueden "
                  "complementarse si no compiten por el mando."),
        ("S-B11", "En la carta de A, Marte en Libra y Saturno en Aries forman "
                  "una oposición que conviene no proyectar en la pareja."),
        ("S-B12", "La sinastría no garantiza nada: describe tendencias que "
                  "podéis trabajar con diálogo y límites claros."),
    ]
    for n, x in buen:
        out.append(_caso("sinastria", n, "buena", t(), _c(x), "lectura correcta"))
    return out


def todos_los_casos():
    out = []
    for fn in (casos_transitos, casos_rs, casos_bio, casos_fuera, casos_sinastria):
        out.extend(fn())
    return out


# --------------------------------------------------------------------------- #
# Fase 1: ejecutar el verificador
# --------------------------------------------------------------------------- #
def evaluar_casos(casos=None):
    filas = []
    for c in casos or todos_los_casos():
        ok, motivos = fp.verificar_lectura(c["tarea"], c["texto"])
        acerto = (not ok) if c["tipo"] == "adversa" else ok
        filas.append({**c, "aceptada": ok, "motivos": motivos, "acierto": acerto})
    return filas


def resumen_por_familia(filas):
    res = {}
    for fam in ("transitos", "revolucion_solar", "biorritmos",
                "fuera_alcance", "sinastria"):
        sub = [f for f in filas if f["familia"] == fam]
        adv = [f for f in sub if f["tipo"] == "adversa"]
        buen = [f for f in sub if f["tipo"] == "buena"]
        res[fam] = {
            "adversas": len(adv),
            "adversas_detectadas": sum(1 for f in adv if not f["aceptada"]),
            "falsos_negativos": sum(1 for f in adv if f["aceptada"]),
            "buenas": len(buen),
            "buenas_aceptadas": sum(1 for f in buen if f["aceptada"]),
            "falsos_positivos": sum(1 for f in buen if not f["aceptada"]),
        }
    return res


# --------------------------------------------------------------------------- #
# Fase 2: revisión factual de lecturas reales
# --------------------------------------------------------------------------- #
def _cargar_reales():
    por_fam = collections.defaultdict(list)
    with DIR_REALES.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            por_fam[r["bloque"]].append(r)
    return por_fam


def _diez(rows):
    return sorted(rows, key=lambda r: str(r.get("id")))[:10]


def _calc(r):
    c = r.get("calculos")
    if isinstance(c, str):
        try:
            return json.loads(c)
        except ValueError:
            return {}
    return c or {}


def _norm(s):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(s)).lower()
        if not unicodedata.combining(ch))


def _planetas_signos(carta):
    return {_norm(p): _norm(v.get("signo", ""))
            for p, v in (carta or {}).get("planetas", {}).items()}


def _casas(carta):
    return {_norm(p): v.get("casa")
            for p, v in (carta or {}).get("planetas", {}).items()}


def _pares_aspectos(aspectos):
    out = set()
    for a in aspectos or []:
        out.add((_norm(a.get("a", a.get("planeta_transito", ""))),
                 _norm(a.get("aspecto", "")),
                 _norm(a.get("b", a.get("planeta_natal", "")))))
    return out


def _triples_texto(texto):
    n = _norm(texto)
    return re.findall(
        r"\b([a-z]+)\s+(?:en\s+transito\s+)?hace\s+([a-z]+)\s+a\s+(?:su|tu)\s+([a-z]+)\s+natal\b",
        n)


_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_SIGNOS_N = {_norm(s) for s in SIGNOS}
_PL_RE = (r"(?:sol|luna|mercurio|venus|marte|jupiter|saturno|urano|neptuno|"
          r"pluton)")
_ITEM_RE = rf"(?:tu\s+|su\s+)?{_PL_RE}(?:\s+de\s+(?:la\s+)?(?:persona\s+)?[ab])?"
_SIGNOS_ALT = "|".join(sorted(_SIGNOS_N))
_MENCION_RE = re.compile(
    rf"\b({_ITEM_RE}(?:\s*,\s*{_ITEM_RE})*(?:\s*(?:y|e)\s+{_ITEM_RE})?)"
    rf"\s+(?:(?:estan|están|se\s+encuentran|se\s+encuentra)\s+)?"
    rf"en\s+({_SIGNOS_ALT})\b")
_ITEM_PARSE_RE = re.compile(
    rf"(?:tu\s+|su\s+)?({_PL_RE})(?:\s+de\s+(?:la\s+)?(?:persona\s+)?([ab]))?")

_ANGULOS = {"conjuncion": 0, "sextil": 60, "cuadratura": 90, "trigono": 120,
            "oposicion": 180, "quincuncio": 150, "semisextil": 30}
_ORBES = {"conjuncion": 6, "sextil": 5, "cuadratura": 6, "trigono": 6,
          "oposicion": 7, "quincuncio": 3, "semisextil": 3}
_ASP_RE = r"(?:conjuncion|oposicion|cuadratura|trigono|sextil|quincuncio|semisextil)"
_ASPECTO_RE = re.compile(
    rf"\b({_PL_RE})\s*(?:de\s+(?:la\s+)?(?:persona\s+)?([ab]))?\s+"
    rf"(?:(?:hace|forma)\s+)?(?:en\s+)?({_ASP_RE})\s+"
    rf"(?:(?:con|a|de)\s+)?(?:tu\s+|su\s+)?({_PL_RE})"
    rf"(?:\s+(?:natal|de\s+(?:la\s+)?(?:persona\s+)?([ab])))?\b")


def _fechas_calculo(calc):
    cadenas = []

    def recorrer(x):
        if isinstance(x, dict):
            for v in x.values():
                recorrer(v)
        elif isinstance(x, list):
            for v in x:
                recorrer(v)
        elif isinstance(x, str):
            cadenas.append(x)

    recorrer(calc)
    fechas, anios = set(), set()
    for s in cadenas:
        for m in re.finditer(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", s):
            anios.add(int(m.group(1)))
            fechas.add((int(m.group(3)), int(m.group(2)), int(m.group(1))))
        for m in re.finditer(r"(?<!\d)(20\d{2})(?!\d)", s):
            anios.add(int(m.group(1)))
    return fechas, anios


def _datos_texto(texto):
    n = _norm(texto)
    fechas = []
    for m in re.finditer(
            r"\b(\d{1,2})\s+(?:de\s+)?(enero|febrero|marzo|abril|mayo|"
            r"junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"(?:\s+(?:de|del)\s+(\d{4}))?", n):
        fechas.append((int(m.group(1)), _MESES[m.group(2)],
                       int(m.group(3)) if m.group(3) else None))
    anios = {int(a) for a in re.findall(r"\b(20\d{2})\b", n)}
    return fechas, anios


def _fechas_ajenas(texto, calc):
    esperadas, anios_calc = _fechas_calculo(calc)
    fechas, anios = _datos_texto(texto)
    h = []
    for d, m, y in fechas:
        if y is None:
            if not any(dd == d and mm == m for dd, mm, _ in esperadas):
                h.append(f"fecha {d}/{m} no calculada")
        elif (d, m, y) in esperadas:
            continue
        elif any(mm == m and yy == y for _, mm, yy in esperadas):
            h.append(f"día {d}/{m}/{y} no coincide con la fecha calculada")
        else:
            h.append(f"fecha {d}/{m}/{y} no calculada")
    ajenos = sorted(y for y in anios if y not in anios_calc)
    if ajenos:
        h.append(f"años ajenos al cálculo: {ajenos}")
    return h


def _menciones_signo(texto):
    n = _norm(texto)
    out = []
    for m in _MENCION_RE.finditer(n):
        signo = m.group(2)
        for im in _ITEM_PARSE_RE.finditer(m.group(1)):
            out.append((im.group(1), im.group(2), signo))
    return out


def _lon_de(carta, planeta):
    for p, v in ((carta or {}).get("planetas") or {}).items():
        if _norm(p) == planeta and isinstance(v.get("lon"), (int, float)):
            return float(v["lon"])
    return None


def _aspecto_entre(lon1, lon2):
    diff = abs((lon1 - lon2) % 360)
    diff = min(diff, 360 - diff)
    for nombre, angulo in _ANGULOS.items():
        if abs(diff - angulo) <= _ORBES[nombre]:
            return nombre
    return None


def _aspectos_cruzados(a, b):
    out = set()
    for pa in ((a or {}).get("planetas") or {}):
        for pb in ((b or {}).get("planetas") or {}):
            l1, l2 = _lon_de(a, _norm(pa)), _lon_de(b, _norm(pb))
            if l1 is None or l2 is None:
                continue
            asp = _aspecto_entre(l1, l2)
            if asp:
                out.add((_norm(pa), asp, _norm(pb)))
    return out


def _menciones_aspecto(texto):
    n = _norm(texto)
    out = []
    for m in _ASPECTO_RE.finditer(n):
        out.append((m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)))
    return out


def _hallazgos_transitos(r):
    calc = _calc(r)
    trans = calc.get("transitos") or {}
    esperados = _pares_aspectos(trans.get("aspectos"))
    invertidos = {(c, b, a) for a, b, c in esperados}
    natal = _planetas_signos(calc.get("carta_natal"))
    casas_natales = set(_casas(calc.get("carta_natal")).values())
    h = []
    for t, a, p in _triples_texto(r["respuesta"]):
        if (t, a, p) not in esperados and (p, a, t) not in esperados:
            h.append(f"tránsito inventado: {t} {a} {p} natal")
    for p1, _c1, asp, p2, _c2 in _menciones_aspecto(r["respuesta"]):
        if (p1, asp, p2) not in esperados and (p1, asp, p2) not in invertidos:
            h.append(f"aspecto de tránsito no calculado: {p1} {asp} {p2}")
    trans_planetas = {_norm(a.get("planeta_transito", ""))
                      for a in trans.get("aspectos") or []}
    for m in re.finditer(r"\b(?:transito|transita|transitando)\s+de\s+([a-z]+)",
                         _norm(r["respuesta"])):
        if m.group(1) in {_norm(p) for p in PLANETAS} and m.group(1) not in trans_planetas:
            h.append(f"planeta en tránsito no calculado: {m.group(1)}")
    for pl, _c, sg in _menciones_signo(r["respuesta"]):
        if natal.get(pl) and natal[pl] != sg:
            h.append(f"posición de {pl} en {sg}: no coincide con la natal "
                     f"({natal[pl]}) y el cálculo no trae posiciones de tránsito")
    h.extend(_fechas_ajenas(r["respuesta"], calc))
    if re.search(r"\bretrograd", _norm(r["respuesta"])):
        h.append("afirma retrogradación no calculada")
    for m in re.finditer(r"\bcasa\s+(\d{1,2})\b", _norm(r["respuesta"])):
        if int(m.group(1)) not in {a.get("casa_natal") for a in trans.get("aspectos") or []} \
                and int(m.group(1)) not in casas_natales:
            h.append(f"casa de tránsito no calculada: {m.group(1)}")
            break
    return list(dict.fromkeys(h))


def _hallazgos_rs(r):
    calc = _calc(r)
    rs = calc.get("revolucion_solar") or {}
    natal = _planetas_signos(calc.get("carta_natal"))
    planetas_rs = {_norm(p.get("nombre")): _norm(p.get("signo"))
                   for p in (rs.get("carta") or {}).get("planetas") or []}
    casas_rs = {p.get("casa") for p in (rs.get("carta") or {}).get("planetas") or []}
    casas_natales = set(_casas(calc.get("carta_natal")).values())
    asc_rs = _norm((rs.get("ascendente") or {}).get("signo", ""))
    asc_natal = _norm((calc.get("carta_natal") or {}).get("ascendente", {}).get("signo", ""))
    h = []
    n = _norm(r["respuesta"])
    for m in _MENCION_RE.finditer(n):
        sg = m.group(2)
        ini = max(n.rfind(".", 0, m.start()), n.rfind(";", 0, m.start()),
                  n.rfind("\n", 0, m.start())) + 1
        fin = len(n)
        for corte in (".", ";", "\n"):
            pos = n.find(corte, m.end())
            if pos != -1 and pos < fin:
                fin = pos
        oracion = n[ini:fin]
        es_natal = bool(re.search(r"\bnatal\b", oracion))
        es_rs = bool(re.search(r"revolucion solar|retorno solar|carta solar|\brs\b",
                               oracion))
        if not es_natal and not es_rs:
            continue
        for im in _ITEM_PARSE_RE.finditer(m.group(1)):
            pl = im.group(1)
            if es_natal:
                if natal.get(pl) and natal[pl] != sg:
                    h.append(f"{pl} natal en {sg}: calculado en {natal[pl]}")
            elif pl in planetas_rs and planetas_rs[pl] != sg:
                h.append(f"{pl} en {sg}: no coincide con la RS ({planetas_rs[pl]})")
    for m in re.finditer(r"\bascendente\s+(rs|natal|de la revolucion)?\s*(?:en\s+)?([a-z]+)", n):
        tok = m.group(2)
        if tok not in _SIGNOS_N:
            continue
        if m.group(1) == "natal":
            if asc_natal and tok != asc_natal:
                h.append(f"Ascendente natal incorrecto: {tok} (calculado {asc_natal})")
        elif m.group(1) in ("rs", "de la revolucion") and asc_rs and tok != asc_rs:
            h.append(f"Ascendente RS incorrecto: {tok} (calculado {asc_rs})")
    if re.search(r"\bmedio\s+cielo\b|\bmc\b", n):
        mc_rs = _norm((rs.get("mc") or {}).get("signo", ""))
        if mc_rs:
            for m in re.finditer(r"\b(?:medio\s+cielo|mc)\s+(?:rs|de la revolucion)?"
                                 r"\s*(?:en\s+)?([a-z]+)", n):
                if m.group(1) in _SIGNOS_N and m.group(1) != mc_rs:
                    h.append(f"MC RS incorrecto: {m.group(1)} (calculado {mc_rs})")
    h.extend(_fechas_ajenas(r["respuesta"], calc))
    for m in re.finditer(r"\bcasa\s+(\d{1,2})\b", n):
        num = int(m.group(1))
        if num not in casas_rs and num not in casas_natales:
            h.append(f"casa no calculada: {num}")
            break
    return list(dict.fromkeys(h))


def _hallazgos_bio(r):
    calc = _calc(r)
    datos = calc.get("biorritmos") or {}
    ciclos = datos.get("ciclos") or {}
    n = _norm(r["respuesta"])
    h = []
    alias = {"fisico": ("fisico", "fisica", "cuerpo"),
             "emocional": ("emocional", "corazon", "emociones"),
             "intelectual": ("intelectual", "inteligencia", "mente")}
    fases = {k: _norm((ciclos.get(k) or {}).get("fase", "")) for k in alias}
    menciones = []
    for clave, nombres in alias.items():
        for nombre in nombres:
            for m in re.finditer(r"\b" + nombre + r"\b", n):
                menciones.append((m.start(), m.end(), clave))
    for pm in fp._RE_PCT.finditer(n):
        if not menciones:
            continue
        cercana = min(menciones, key=lambda x: min(abs(pm.start() - x[0]),
                                                   abs(pm.start() - x[1])))
        distancia = min(abs(pm.start() - cercana[0]), abs(pm.start() - cercana[1]))
        if distancia > 20:
            continue
        esperado = (ciclos.get(cercana[2]) or {}).get("porcentaje")
        if esperado is not None and fp._pct_contradice(pm, esperado):
            h.append(f"{cercana[2]} {pm.group(1)}% (calculado {esperado}%)")
    patron_fase = re.compile(
        r"\b(?:fase|direccion|punto)\s+(?:\w+\s+){0,2}"
        r"(ascendente|descendente|critico)\b"
        r"|\b(?:al\s+)?[+\-−–]?\d{1,3}\s*%\s+(?:y\s+)?"
        r"(ascendente|descendente|critico)\b"
        r"|^\s*(ascendente|descendente|critico)\b")
    for ini, fin, clave in menciones:
        if not fases[clave]:
            continue
        ventana = n[fin:min(len(n), fin + 110)]
        siguiente = min((i for i, _f, c in menciones
                         if c != clave and i >= fin), default=len(n))
        for corte in (".", ";", "\n"):
            pos = n.find(corte, fin)
            if pos != -1:
                siguiente = min(siguiente, pos)
        ventana = n[fin:siguiente]
        for fm in patron_fase.finditer(ventana):
            fase = next(g for g in fm.groups() if g)
            antes = ventana[:fm.start()]
            if re.search(r"\b(recupere|salga|vuelva|alcance|entre|estara|"
                         r"llegara|empiece|gane)\b", antes):
                continue
            if fase != fases[clave]:
                h.append(f"fase {clave} {fase} (calculada {fases[clave]})")
                break
    if re.search(r"\bcritic[oa]s?\b", n) and not any(f == "critico" for f in fases.values()):
        h.append("menciona ciclo/día crítico no calculado")
    for m in re.finditer(r"([+\-−–]?\d{1,3})\s*%", n):
        if abs(int(m.group(1).replace("−", "-").replace("–", "-"))) > 100:
            h.append(f"porcentaje fuera de rango: {m.group(1)}%")
    for m in re.finditer(r"\bciclo\s+([a-z]+)\s+dura\s+(\d{1,3})\s+dias", n):
        if (m.group(1), m.group(2)) not in (("fisico", "23"), ("emocional", "28"),
                                            ("intelectual", "33")):
            h.append(f"duración de ciclo inventada: {m.group(1)} {m.group(2)} días")
    h.extend(_fechas_ajenas(r["respuesta"], calc))
    return list(dict.fromkeys(h))


def _hallazgos_sinastria(r):
    calc = _calc(r)
    a_c, b_c = calc.get("carta_a"), calc.get("carta_b")
    a = _planetas_signos(a_c)
    b = _planetas_signos(b_c)
    casas = set(_casas(a_c).values()) | set(_casas(b_c).values())
    asp_a = _pares_aspectos((a_c or {}).get("aspectos"))
    asp_b = _pares_aspectos((b_c or {}).get("aspectos"))
    cruzados = _aspectos_cruzados(a_c, b_c)
    h = []
    for pl, carta, sg in _menciones_signo(r["respuesta"]):
        if carta == "a":
            if a.get(pl) != sg:
                h.append(f"{pl} en {sg}: la carta A tiene {a.get(pl)}")
        elif carta == "b":
            if b.get(pl) != sg:
                h.append(f"{pl} en {sg}: la carta B tiene {b.get(pl)}")
        elif a.get(pl) != sg and b.get(pl) != sg:
            h.append(f"{pl} en {sg}: no está en ninguna de las dos cartas")
    for p1, c1, asp, p2, c2 in _menciones_aspecto(r["respuesta"]):
        if c1 and c2 and c1 != c2:
            if (p1, asp, p2) not in cruzados:
                h.append(f"aspecto cruzado no calculado: {p1} de {c1.upper()} "
                         f"{asp} {p2} de {c2.upper()}")
        elif c1 or c2:
            propios = asp_a if (c1 or c2) == "a" else asp_b
            if (p1, asp, p2) not in propios and (p2, asp, p1) not in propios:
                h.append(f"aspecto no calculado entre cartas: {p1} {asp} {p2}")
        elif (p1, asp, p2) not in asp_a | asp_b | cruzados and \
                (p2, asp, p1) not in asp_a | asp_b | cruzados:
            h.append(f"aspecto no calculado: {p1} {asp} {p2}")
    if re.search(r"\bno hay (?:ningun )?aspecto", _norm(r["respuesta"])):
        h.append("niega los aspectos calculados")
    for m in re.finditer(r"\bcasa\s+(\d{1,2})\b", _norm(r["respuesta"])):
        num = int(m.group(1))
        if num not in casas:
            h.append(f"casa no calculada: {num}")
            break
    h.extend(_fechas_ajenas(r["respuesta"], calc))
    return list(dict.fromkeys(h))


def _hallazgos_astro(r):
    calc = _calc(r)
    carta = calc.get("carta_natal")
    natal = _planetas_signos(carta)
    asp = _pares_aspectos((carta or {}).get("aspectos"))
    casas = set(_casas(carta).values())
    h = []
    for pl, _c, sg in _menciones_signo(r["respuesta"]):
        if natal.get(pl) and natal[pl] != sg:
            h.append(f"{pl} en {sg}; calculado {natal[pl]}")
    for p1, _c1, asp_n, p2, _c2 in _menciones_aspecto(r["respuesta"]):
        if (p1, asp_n, p2) not in asp and (p2, asp_n, p1) not in asp:
            h.append(f"aspecto no calculado: {p1} {asp_n} {p2}")
    for m in re.finditer(r"\bcasa\s+(\d{1,2})\b", _norm(r["respuesta"])):
        if int(m.group(1)) not in casas:
            h.append(f"casa no calculada: {m.group(1)}")
            break
    h.extend(_fechas_ajenas(r["respuesta"], calc))
    return list(dict.fromkeys(h))


_CONTENIDO_PROHIBIDO = {
    "quiromancia": r"linea de la vida|montaña de venus|palma|mano|quiromancia",
    "i ching": r"hexagrama|trigrama|libro de las mutaciones|i ching",
    "runas": r"\bruna|futhark|piedra de la runa",
    "vidas pasadas": r"vida anterior|vida pasada|regresion",
    "bazi": r"\bbazi\b|pilares del destino",
}


def _hallazgos_fuera(r):
    h = []
    user = r.get("prompt_user", "")
    if re.search(r'Pregunta del consultante:\s*"\d+\s', user):
        h.append("pregunta real sustituida por un arranque numérico")
    payload = r.get("payload")
    tecnicas = []
    if isinstance(payload, dict):
        t = payload.get("tecnica")
        if isinstance(t, (list, tuple)):
            tecnicas = [str(x).lower() for x in t]
        elif t:
            tecnicas = [str(t).lower()]
    texto = _norm(r["respuesta"])
    for tec in tecnicas:
        for clave, patron in _CONTENIDO_PROHIBIDO.items():
            if clave in tec and re.search(patron, texto):
                # Descontar la mención de rechazo («no leo la mano»).
                usos = [m for m in re.finditer(patron, texto)]
                sin_negacion = 0
                for m in usos:
                    antes = texto[max(0, m.start() - 30): m.start()]
                    if not re.search(r"\bno\s+(?:\w+\s+){0,3}$", antes):
                        sin_negacion += 1
                if sin_negacion >= 2:
                    h.append(f"responde la técnica prohibida «{tec}»")
                    break
    return h


_REVISORES = {
    "transitos": _hallazgos_transitos,
    "revolucion_solar": _hallazgos_rs,
    "biorritmos": _hallazgos_bio,
    "sinastria": _hallazgos_sinastria,
    "astro_natal": _hallazgos_astro,
    "fuera_alcance": _hallazgos_fuera,
}


def revisar_reales():
    por_fam = _cargar_reales()
    salida = []
    for fam in ("transitos", "revolucion_solar", "biorritmos",
                "sinastria", "astro_natal", "fuera_alcance"):
        for r in _diez(por_fam.get(fam, [])):
            h = _REVISORES[fam](r)
            salida.append({"id": r.get("id"), "familia": fam,
                           "hallazgos": h, "ok": not h})
    return salida


# --------------------------------------------------------------------------- #
# Fase 3: fugas de evaluación y de splits
# --------------------------------------------------------------------------- #
def _variantes(texto):
    sin_tilde = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c))
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    reordenado = " ".join(frases[1:] + frases[:1]) if len(frases) > 1 else texto
    return {
        "identico": texto,
        "sin_tildes": sin_tilde,
        "mayusculas": texto.upper(),
        "espacios": re.sub(r" ", "   ", texto),
        "puntuacion": texto.replace(",", ";").replace(":", " -"),
        "reordenado": reordenado,
    }


def _fila_conversacion(texto, ident, bloque="x"):
    return {"id": ident, "bloque": bloque,
            "conversations": [{"from": "human", "value": texto}]}


def probar_fugas():
    casos = ec.generar_casos(560056)
    casos_eval = {str(c["id"]): c for c in casos}
    # Caso largo y representativo con pregunta y datos.
    base = max(casos, key=lambda c: len(str(c.get("user", ""))))
    usuario = str(base["user"])
    resultados = {}
    for nombre, variante in _variantes(usuario).items():
        fila = _fila_conversacion(variante, "train-" + nombre,
                                  base.get("familia", "x"))
        res = qa.fugas_eval([("train", 1, fila)], casos_eval)
        resultados[nombre] = {
            "hallazgos": len(res["hallazgos"]),
            "chequeos": sorted({h["chequeo"] for h in res["hallazgos"]}),
        }

    # Solape entre splits: mismo prompt con otra puntuación y reordenado.
    filas = []
    for i, nombre in enumerate(("identico", "puntuacion", "reordenado")):
        fila = _fila_conversacion(_variantes(usuario)[nombre],
                                  f"split-{nombre}", base.get("familia", "x"))
        filas.append(("train" if i == 0 else "test", i, fila))
    splits = qa.fugas_splits(filas)
    exactos = splits["resumen"]["prompts_exactos_entre_splits"]
    casi = splits["resumen"]["casi_identificados_muestreado"]

    # merge_final: exclusión por contenido con variantes normalizadas.
    humanos = {}
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write(json.dumps({
            "id": "eval-1", "origen": "evaluacion",
            "conversations": [{"from": "human", "value": usuario}],
        }, ensure_ascii=False) + "\n")
        ruta = tmp.name
    try:
        humanos = mf.cargar_humanos_evaluacion([ruta])
    finally:
        Path(ruta).unlink(missing_ok=True)
    excluidas = {nombre: (mf._norm(v) in humanos)
                 for nombre, v in _variantes(usuario).items()}
    return {
        "casos_eval": len(casos_eval),
        "fugas_por_variante": resultados,
        "split_prompt_identico": exactos,
        "split_casi_identico": casi,
        "merge_excluye_variante_sin_tildes": excluidas["sin_tildes"],
        "merge_excluye_variantes": excluidas,
    }


# --------------------------------------------------------------------------- #
# Fase 4: traducciones adversas T116
# --------------------------------------------------------------------------- #
def casos_traduccion():
    indice = IndiceCartas(cargar_glosario())
    C = []

    def add(nombre, original, traduccion, esperado, motivo):
        C.append({"caso": nombre, "original": original,
                  "traduccion": traduccion, "esperado": esperado,
                  "motivo": motivo})

    add("TR-01", "Two of Swords reversed signals a difficult choice, and the "
        "querent must wait before acting.",
        "Dos de Espadas invertida señala una elección difícil, y la consultante "
        "debe esperar antes de actuar.", True, "traducción correcta")
    add("TR-02", "Two of Swords reversed signals a difficult choice, and the "
        "querent must wait before acting.",
        "Tres de Espadas invertida señala una elección difícil, y la consultante "
        "debe esperar antes de actuar.", False, "número de carta cambiado")
    add("TR-03", "Two of Swords reversed signals a difficult choice, and the "
        "querent must wait before acting.",
        "Dos de Copas invertida señala una elección difícil, y la consultante "
        "debe esperar antes de actuar.", False, "palo de carta cambiado")
    add("TR-04", "Two of Swords reversed signals a difficult choice.",
        "Two of Swords invertida señala una elección difícil.", False,
        "nombre de carta en inglés residual")
    add("TR-05", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas reversed señala una elección difícil.", False,
        "término inglés residual (reversed)")
    add("TR-06", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas al derecho señala una elección difícil.", False,
        "orientación invertida perdida")
    add("TR-07", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida señala una elección difícil.", True,
        "orientación conservada")
    add("TR-08", "The Fool upright invites a leap of faith, but the querent "
        "should look before jumping.",
        "El Loco al derecho invita a un salto de fe, pero la consultante debe "
        "mirar antes de saltar. Muito importante.", False,
        "marcador de gallego/portugués")
    add("TR-09", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida, com o teu coração aberto, mostra uma escolha "
        "difícil.", False, "portugués no detectado (com/teu/coração)")
    add("TR-10", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida señala una elección difícil, y el As de Copas "
        "pide calma.", False, "carta añadida que no estaba en el original")
    add("TR-11", "The reading mentions 14 days of reflection before the decision.",
        "La lectura menciona 15 días de reflexión antes de la decisión.", False,
        "cifra cambiada (14→15)")
    add("TR-12", "The reading mentions 14 days of reflection before the decision.",
        "La lectura menciona 14 días de reflexión antes de la decisión.", True,
        "cifra conservada")
    add("TR-13", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida señala the elección difícil.", False,
        "resto de inglés («the»)")
    add("TR-14", "The Fool upright invites a leap of faith, but the querent "
        "should look before jumping.",
        "El Mago al derecho invita a un salto de fe, pero la consultante debe "
        "mirar antes de saltar.", False, "arcano mayor equivocado")
    add("TR-15", "The Fool upright invites a leap of faith, but the querent "
        "should look before jumping.",
        "El Loco al derecho invita a un salto de fe, pero la consultante debe "
        "mirar antes de saltar.", True, "arcano mayor correcto")
    add("TR-16", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida señala una elección difícil.", True,
        "traducción mínima correcta")
    add("TR-17", "One's own judgment matters when the Two of Swords appears.",
        "El propio criterio importa cuando aparece el Dos de Espadas.", True,
        "«one's» es pronombre, no cifra")
    add("TR-18", "Two of Swords reversed and Three of Cups reversed mark a "
        "tense moment that softens.",
        "Dos de Espadas invertida y Tres de Copas al derecho marcan un momento "
        "tenso que se suaviza.", False,
        "segunda orientación invertida sin conservar")
    add("TR-19", "Two of Swords reversed signals a difficult choice.",
        "Dos de Espadas invertida não señala una elección difícil.", False,
        "marcador portugués «não»")
    add("TR-20", "Two of Swords reversed signals a difficult choice.",
        "Espadas de Dos invertida señala una elección difícil.", False,
        "orden de carta incorrecto")

    for c in C:
        limpio, motivo = verificar_traduccion(c["original"], c["traduccion"],
                                              indice)
        c["aceptada"] = limpio is not None
        c["motivo_verificador"] = motivo
        c["acierto"] = (c["aceptada"] == c["esperado"])
    return C


def resumen_traduccion(casos):
    return {
        "casos": len(casos),
        "aciertos": sum(1 for c in casos if c["acierto"]),
        "falsos_negativos": sum(1 for c in casos if not c["esperado"] and c["aceptada"]),
        "falsos_positivos": sum(1 for c in casos if c["esperado"] and not c["aceptada"]),
    }


# --------------------------------------------------------------------------- #
# Informe
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ruta para volcar el informe completo")
    args = ap.parse_args()

    filas = evaluar_casos()
    resumen = resumen_por_familia(filas)
    reales = revisar_reales()
    fugas = probar_fugas()
    traducciones = casos_traduccion()
    res_trad = resumen_traduccion(traducciones)

    print("== Fase 1: casos por familia ==")
    for fam, r in resumen.items():
        print(f"{fam:18} adv {r['adversas_detectadas']}/{r['adversas']} "
              f"FN={r['falsos_negativos']:2}  buenas "
              f"{r['buenas_aceptadas']}/{r['buenas']} FP={r['falsos_positivos']}")
    print("\nFallos adversos no detectados:")
    for f in filas:
        if f["tipo"] == "adversa" and f["aceptada"]:
            print(f"  {f['caso']}: {f['motivo']}")
    print("\nFalsos positivos en buenas:")
    for f in filas:
        if f["tipo"] == "buena" and not f["aceptada"]:
            print(f"  {f['caso']}: {f['motivos']}")

    print("\n== Fase 2: lecturas reales ==")
    por_fam = collections.Counter()
    con_hall = collections.Counter()
    for r in reales:
        por_fam[r["familia"]] += 1
        if r["hallazgos"]:
            con_hall[r["familia"]] += 1
    for fam in por_fam:
        print(f"{fam:18} {con_hall[fam]}/{por_fam[fam]} con hallazgos")
    print("\nEjemplos de hallazgos:")
    for r in reales:
        if r["hallazgos"]:
            print(f"  {r['familia']} {r['id']}: {r['hallazgos']}")

    print("\n== Fase 3: fugas ==")
    print(json.dumps(fugas, ensure_ascii=False, indent=2))

    print("\n== Fase 4: traducción ==")
    print(json.dumps(res_trad, ensure_ascii=False))
    for c in traducciones:
        if not c["acierto"]:
            print(f"  {c['caso']} esperado={c['esperado']} "
                  f"aceptada={c['aceptada']}: {c['motivo']} "
                  f"[{c['motivo_verificador']}]")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "casos": filas, "resumen": resumen, "reales": reales,
            "fugas": fugas, "traducciones": traducciones,
            "resumen_traduccion": res_trad,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme completo en {args.json}")


if __name__ == "__main__":
    main()
