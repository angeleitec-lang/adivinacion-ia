#!/usr/bin/env python3
"""Construye la base de conocimiento estructurada (KB) para la generación sintética.

Genera tres ficheros JSON en corpus/kb/:
- tarot.json      : 22 arcanos mayores + 56 menores (compuestos de palo x rango)
- astrologia.json : signos, planetas, casas y aspectos
- numerologia.json: números 1-9 y maestros 11/22/33

Solo usa la stdlib. Ejecutar: .venv/bin/python corpus/build_kb.py [--validate]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "corpus" / "kb"

# ---------------------------------------------------------------------------
# Numerología (determinista)
# ---------------------------------------------------------------------------
NUMEROS = [
    {"numero": 1, "tipo": "simple", "nombre": "El Uno",
     "palabras_clave": ["liderazgo", "iniciativa", "independencia", "individualidad"],
     "positivo": ["pionero", "decidido", "original"],
     "sombra": ["egoísmo", "terquedad", "aislamiento"],
     "areas": {"amor": "quiere iniciativa y sinceridad", "trabajo": "destaca liderando y empezando proyectos",
               "dinero": "gana por cuenta propia o siendo el primero", "salud": "cuidar la cabeza y el estrés"}},
    {"numero": 2, "tipo": "simple", "nombre": "El Dos",
     "palabras_clave": ["cooperación", "diplomacia", "sensibilidad", "equilibrio"],
     "positivo": ["paciente", "empático", "mediador"],
     "sombra": ["dependencia", "indecisión", "hipersensibilidad"],
     "areas": {"amor": "busca unión y compañía", "trabajo": "destaca en equipo y apoyando",
               "dinero": "mejor en alianza que en solitario", "salud": "cuidar sistema digestivo y emociones"}},
    {"numero": 3, "tipo": "simple", "nombre": "El Tres",
     "palabras_clave": ["creatividad", "comunicación", "expresión", "alegría"],
     "positivo": ["expresivo", "optimista", "versátil"],
     "sombra": ["dispersión", "superficialidad", "drama"],
     "areas": {"amor": "juguetón y expresivo", "trabajo": "destaca creando y comunicando",
               "dinero": "fluye con la creatividad", "salud": "cuidar garganta y pulmones"}},
    {"numero": 4, "tipo": "simple", "nombre": "El Cuatro",
     "palabras_clave": ["orden", "estabilidad", "trabajo", "estructura"],
     "positivo": ["constante", "fiable", "práctico"],
     "sombra": ["rigidez", "monotonía", "terquedad"],
     "areas": {"amor": "valora compromiso y seguridad", "trabajo": "construye con método",
               "dinero": "ahorra y planifica", "salud": "cuidar huesos y estructura"}},
    {"numero": 5, "tipo": "simple", "nombre": "El Cinco",
     "palabras_clave": ["cambio", "libertad", "aventura", "versatilidad"],
     "positivo": ["adaptable", "curioso", "enérgico"],
     "sombra": ["inconstancia", "exceso", "impaciencia"],
     "areas": {"amor": "necesita libertad y variedad", "trabajo": "destaca en lo cambiante y viajes",
               "dinero": "altibajos, evita la rutina", "salud": "cuidar sistema nervioso"}},
    {"numero": 6, "tipo": "simple", "nombre": "El Seis",
     "palabras_clave": ["armonía", "familia", "responsabilidad", "cuidado"],
     "positivo": ["protector", "equilibrado", "leal"],
     "sombra": ["sacrificio", "interferencia", "perfeccionismo"],
     "areas": {"amor": "hogar y vínculos profundos", "trabajo": "destaca cuidando y armonizando equipos",
               "dinero": "estable y orientado al hogar", "salud": "cuidar corazón y equilibrio"}},
    {"numero": 7, "tipo": "simple", "nombre": "El Siete",
     "palabras_clave": ["introspección", "espiritualidad", "análisis", "sabiduría"],
     "positivo": ["profundo", "observador", "sabio"],
     "sombra": ["aislamiento", "desconfianza", "frialdad"],
     "areas": {"amor": "necesita confianza y profundidad", "trabajo": "destaca investigando y analizando",
               "dinero": "prudente y reservado", "salud": "cuidar la mente y el descanso"}},
    {"numero": 8, "tipo": "simple", "nombre": "El Ocho",
     "palabras_clave": ["poder", "ambición", "materialidad", "ejecución"],
     "positivo": ["eficiente", "ambicioso", "autoridad"],
     "sombra": ["autoritarismo", "avaricia", "materialismo"],
     "areas": {"amor": "busca solidez y respeto", "trabajo": "destaca dirigiendo y gestionando",
               "dinero": "gran capacidad de logro", "salud": "cuidar estrés y circulación"}},
    {"numero": 9, "tipo": "simple", "nombre": "El Nueve",
     "palabras_clave": ["altruismo", "cierre", "sabiduría", "humanitarismo"],
     "positivo": ["generoso", "compasivo", "idealista"],
     "sombra": ["frustración", "control", "resentimiento"],
     "areas": {"amor": "entrega profunda y desprendida", "trabajo": "destaca sirviendo a otros",
               "dinero": "menos interés, más propósito", "salud": "cuidar sistema inmunitario"}},
    {"numero": 11, "tipo": "maestro", "nombre": "Maestro Once",
     "palabras_clave": ["intuición", "iluminación", "idealismo", "inspiración"],
     "positivo": ["visionario", "inspirador", "sensible"],
     "sombra": ["nerviosismo", "mesianismo", "autoengaño"],
     "areas": {"amor": "unión espiritual y mental", "trabajo": "destaca inspirando y canalizando ideas",
               "dinero": "canal de ideas, no de rutina", "salud": "cuidar sistema nervioso"}},
    {"numero": 22, "tipo": "maestro", "nombre": "Maestro Veintidós",
     "palabras_clave": ["constructor", "visión", "servicio", "realización"],
     "positivo": ["constructor", "práctico", "ambicioso con causa"],
     "sombra": ["grandiosidad", "sobrecarga", "frustración"],
     "areas": {"amor": "construye vínculos con visión de futuro", "trabajo": "edifica proyectos grandes",
               "dinero": "logro material con propósito", "salud": "cuidar agotamiento"}},
    {"numero": 33, "tipo": "maestro", "nombre": "Maestro Treinta y Tres",
     "palabras_clave": ["maestría", "compasión", "guía", "entrega"],
     "positivo": ["maestro", "compasivo", "protector"],
     "sombra": ["autoexigencia", "mártir", "sobreimplicación"],
     "areas": {"amor": "amor incondicional y guía", "trabajo": "enseña y eleva a otros",
               "dinero": "abundancia al servicio de otros", "salud": "cuidar la sobrecarga emocional"}},
]

# ---------------------------------------------------------------------------
# Astrología
# ---------------------------------------------------------------------------
SIGNOS = [
    {"nombre": "Aries", "elemento": "fuego", "regente": "Marte",
     "palabras_clave": ["impulso", "valentía", "inicio", "independencia"],
     "rasgos": "impulsivo, pionero, directo; arranca con energía y sin miedo."},
    {"nombre": "Tauro", "elemento": "tierra", "regente": "Venus",
     "palabras_clave": ["estabilidad", "sensualidad", "persistencia", "posesión"],
     "rasgos": "constante, paciente, amante del placer y la seguridad."},
    {"nombre": "Géminis", "elemento": "aire", "regente": "Mercurio",
     "palabras_clave": ["comunicación", "curiosidad", "dualidad", "adaptación"],
     "rasgos": "versátil, mental, sociable; procesa el mundo con palabras."},
    {"nombre": "Cáncer", "elemento": "agua", "regente": "Luna",
     "palabras_clave": ["emoción", "hogar", "protección", "intuición"],
     "rasgos": "sensible, protector, apegado a las raíces y a la familia."},
    {"nombre": "Leo", "elemento": "fuego", "regente": "Sol",
     "palabras_clave": ["creatividad", "liderazgo", "orgullo", "generosidad"],
     "rasgos": "expresivo, magnánimo, busca brillar y ser reconocido."},
    {"nombre": "Virgo", "elemento": "tierra", "regente": "Mercurio",
     "palabras_clave": ["análisis", "servicio", "perfección", "detalle"],
     "rasgos": "metódico, crítico, orientado a mejorar y servir."},
    {"nombre": "Libra", "elemento": "aire", "regente": "Venus",
     "palabras_clave": ["equilibrio", "relación", "justicia", "armonía"],
     "rasgos": "diplomático, esteta, busca pareja y armonía en todo."},
    {"nombre": "Escorpio", "elemento": "agua", "regente": "Plutón",
     "palabras_clave": ["intensidad", "transformación", "control", "poder"],
     "rasgos": "profundo, magnético, vive las emociones con intensidad."},
    {"nombre": "Sagitario", "elemento": "fuego", "regente": "Júpiter",
     "palabras_clave": ["expansión", "optimismo", "búsqueda", "libertad"],
     "rasgos": "aventurero, filosófico, busca sentido y horizontes amplios."},
    {"nombre": "Capricornio", "elemento": "tierra", "regente": "Saturno",
     "palabras_clave": ["ambición", "disciplina", "estructura", "responsabilidad"],
     "rasgos": "tenaz, realista, escala con paciencia hacia la meta."},
    {"nombre": "Acuario", "elemento": "aire", "regente": "Urano",
     "palabras_clave": ["innovación", "libertad", "colectivo", "originalidad"],
     "rasgos": "independiente, visionario, piensa en el grupo y el futuro."},
    {"nombre": "Piscis", "elemento": "agua", "regente": "Neptuno",
     "palabras_clave": ["sensibilidad", "intuición", "disolución", "compasión"],
     "rasgos": "empático, soñador, permeable a las emociones del entorno."},
]

PLANETAS = [
    {"nombre": "Sol", "simboliza": "identidad, vitalidad, propósito",
     "palabras_clave": ["yo", "voluntad", "vitalidad", "identidad"]},
    {"nombre": "Luna", "simboliza": "emociones, instinto, memoria",
     "palabras_clave": ["emoción", "intuición", "hogar", "inconsciente"]},
    {"nombre": "Mercurio", "simboliza": "mente, comunicación, comercio",
     "palabras_clave": ["comunicación", "razón", "intercambio", "aprendizaje"]},
    {"nombre": "Venus", "simboliza": "amor, belleza, valores",
     "palabras_clave": ["amor", "placer", "estética", "dinero"]},
    {"nombre": "Marte", "simboliza": "acción, deseo, conflicto",
     "palabras_clave": ["acción", "pasión", "energía", "agresividad"]},
    {"nombre": "Júpiter", "simboliza": "expansión, suerte, sentido",
     "palabras_clave": ["crecimiento", "optimismo", "sabiduría", "abundancia"]},
    {"nombre": "Saturno", "simboliza": "límites, disciplina, tiempo",
     "palabras_clave": ["estructura", "responsabilidad", "restricción", "madurez"]},
    {"nombre": "Urano", "simboliza": "cambio, libertad, innovación",
     "palabras_clave": ["ruptura", "libertad", "originalidad", "revolución"]},
    {"nombre": "Neptuno", "simboliza": "sueños, ilusión, espiritualidad",
     "palabras_clave": ["inspiración", "ilusión", "disolución", "misticismo"]},
    {"nombre": "Plutón", "simboliza": "transformación, poder, regeneración",
     "palabras_clave": ["transformación", "poder", "crisis", "renacimiento"]},
]

CASAS = [
    {"numero": 1, "area": "Identidad y apariencia", "significado": "cómo te presentas y cómo inicias las cosas."},
    {"numero": 2, "area": "Recursos y valores", "significado": "dinero, posesiones y autoestima material."},
    {"numero": 3, "area": "Comunicación y entorno", "significado": "habla, estudio, hermanos y entorno cercano."},
    {"numero": 4, "area": "Hogar y raíces", "significado": "familia, base emocional y vida privada."},
    {"numero": 5, "area": "Creatividad y placer", "significado": "expresión, romance, hijos y diversión."},
    {"numero": 6, "area": "Trabajo y salud", "significado": "rutina, servicio, hábitos y bienestar."},
    {"numero": 7, "area": "Pareja y asociaciones", "significado": "relaciones íntimas, socios y contratos."},
    {"numero": 8, "area": "Transformación y poder compartido", "significado": "herencias, sexo, crisis y regeneración."},
    {"numero": 9, "area": "Filosofía y viajes", "significado": "creencias, estudios superiores y horizontes."},
    {"numero": 10, "area": "Carrera y estatus", "significado": "vocación, reputación y metas públicas."},
    {"numero": 11, "area": "Amistades e ideales", "significado": "grupos, comunidad y proyectos colectivos."},
    {"numero": 12, "area": "Subconsciente y karma", "significado": "lo oculto, el retiro y las pruebas internas."},
]

ASPECTOS = [
    {"nombre": "Conjunción", "simbolo": "0°", "orbe": 8,
     "significado": "los dos planetas funden su energía; intensidad y enfoque."},
    {"nombre": "Sextil", "simbolo": "60°", "orbe": 6,
     "significado": "oportunidad y apoyo; se activa con esfuerzo."},
    {"nombre": "Cuadratura", "simbolo": "90°", "orbe": 7,
     "significado": "tensión y fricción; exige ajuste y crecimiento."},
    {"nombre": "Trígono", "simbolo": "120°", "orbe": 8,
     "significado": "fluidez y talento natural; armonía entre energías."},
    {"nombre": "Oposición", "simbolo": "180°", "orbe": 8,
     "significado": "polaridad y confrontación; invita a integrar opuestos."},
]

# ---------------------------------------------------------------------------
# Tarot
# ---------------------------------------------------------------------------
MAYORES = [
    {"numero": 0, "nombre": "El Loco", "palabras_clave": ["inicio", "espontaneidad", "libertad", "salto de fe"],
     "significado": "Nuevos comienzos, soltar el control y confiar en el camino.",
     "invertida": "Imprudencia, bloqueo o miedo a dar el paso."},
    {"numero": 1, "nombre": "El Mago", "palabras_clave": ["voluntad", "recursos", "manifestación", "destreza"],
     "significado": "Tienes las herramientas y el poder para materializar tus deseos.",
     "invertida": "Manipulación, dispersión o talento desaprovechado."},
    {"numero": 2, "nombre": "La Sacerdotisa", "palabras_clave": ["intuición", "misterio", "inconsciente", "silencio"],
     "significado": "Escucha tu voz interior; hay sabiduría más allá de lo visible.",
     "invertida": "Secretos, desconexión de la intuición o información oculta."},
    {"numero": 3, "nombre": "La Emperatriz", "palabras_clave": ["fertilidad", "abundancia", "cuidado", "creatividad"],
     "significado": "Abundancia, crecimiento y nutrición de proyectos y relaciones.",
     "invertida": "Dependencia, bloqueo creativo o exceso de control."},
    {"numero": 4, "nombre": "El Emperador", "palabras_clave": ["autoridad", "estructura", "protección", "orden"],
     "significado": "Firmeza, liderazgo y construcción de bases sólidas.",
     "invertida": "Rigidez, abuso de poder o falta de estructura."},
    {"numero": 5, "nombre": "El Hierofante", "palabras_clave": ["tradición", "enseñanza", "creencias", "institución"],
     "significado": "Aprende de la tradición y busca guía en estructuras establecidas.",
     "invertida": "Dogmatismo, rebeldía o rechazo de las normas."},
    {"numero": 6, "nombre": "Los Enamorados", "palabras_clave": ["amor", "elección", "unión", "valores"],
     "significado": "Unión profunda y una elección importante alineada con tus valores.",
     "invertida": "Desarmonía, indecisión o conflicto de valores."},
    {"numero": 7, "nombre": "El Carro", "palabras_clave": ["voluntad", "victoria", "dirección", "control"],
     "significado": "Avanza con determinación y mantén las riendas de tu rumbo.",
     "invertida": "Pérdida de control, estancamiento o dirección dispersa."},
    {"numero": 8, "nombre": "La Fuerza", "palabras_clave": ["coraje", "autocontrol", "compasión", "resistencia"],
     "significado": "La fuerza suave domina: domina el impulso con paciencia.",
     "invertida": "Debilidad, desgaste o dominio por la ira."},
    {"numero": 9, "nombre": "El Ermitaño", "palabras_clave": ["introspección", "sabiduría", "soledad", "búsqueda"],
     "significado": "Retírate a reflexionar; la respuesta llega en el silencio.",
     "invertida": "Aislamiento, rechazo o encierro excesivo."},
    {"numero": 10, "nombre": "La Rueda de la Fortuna", "palabras_clave": ["ciclos", "destino", "cambio", "oportunidad"],
     "significado": "Gira la rueda; los ciclos traen cambios y nuevas oportunidades.",
     "invertida": "Mala racha, resistencia al cambio o retraso."},
    {"numero": 11, "nombre": "La Justicia", "palabras_clave": ["equidad", "verdad", "consecuencia", "ley"],
     "significado": "Actúa con integridad; cada acción tiene su consecuencia.",
     "invertida": "Injusticia, deshonestidad o cuentas pendientes."},
    {"numero": 12, "nombre": "El Colgado", "palabras_clave": ["pausa", "sacrificio", "perspectiva", "entrega"],
     "significado": "Una pausa necesaria; cambiar de perspectiva ilumina el camino.",
     "invertida": "Estancamiento, sacrificio inútil o resistencia."},
    {"numero": 13, "nombre": "La Muerte", "palabras_clave": ["fin", "transformación", "renacimiento", "cierre"],
     "significado": "Un ciclo termina para que otro nazca; soltar es transformar.",
     "invertida": "Resistencia al cambio, estancamiento o miedo a soltar."},
    {"numero": 14, "nombre": "La Templanza", "palabras_clave": ["equilibrio", "paciencia", "alquimia", "moderación"],
     "significado": "Integra los opuestos y avanza con calma y mesura.",
     "invertida": "Exceso, desequilibrio o impaciencia."},
    {"numero": 15, "nombre": "El Diablo", "palabras_clave": ["ataduras", "deseo", "sombra", "tentación"],
     "significado": "Reconoce tus cadenas y los apegos que te limitan.",
     "invertida": "Liberación, recuperación o despertar de la sombra."},
    {"numero": 16, "nombre": "La Torre", "palabras_clave": ["ruptura", "revelación", "caída", "liberación"],
     "significado": "Se derrumba lo falso; tras la crisis queda la verdad.",
     "invertida": "Crisis evitada, miedo al cambio o ruina postergada."},
    {"numero": 17, "nombre": "La Estrella", "palabras_clave": ["esperanza", "inspiración", "sanación", "fe"],
     "significado": "Renace la esperanza; la inspiración guía tu sanación.",
     "invertida": "Desaliento, pesimismo o pérdida de fe."},
    {"numero": 18, "nombre": "La Luna", "palabras_clave": ["ilusión", "intuición", "inconsciente", "sueños"],
     "significado": "No todo es lo que parece; confía en la intuición en la niebla.",
     "invertida": "Claridad, confusión disipada o engaño revelado."},
    {"numero": 19, "nombre": "El Sol", "palabras_clave": ["alegría", "éxito", "vitalidad", "claridad"],
     "significado": "Éxito, vitalidad y claridad; todo sale a la luz con alegría.",
     "invertida": "Felicidad empañada, exceso o falta de entusiasmo."},
    {"numero": 20, "nombre": "El Juicio", "palabras_clave": ["despertar", "evaluación", "renacimiento", "llamada"],
     "significado": "Una llamada a renacer y asumir una nueva etapa de la vida.",
     "invertida": "Autocrítica, duda o negarse a la llamada."},
    {"numero": 21, "nombre": "El Mundo", "palabras_clave": ["plenitud", "cierre", "integración", "realización"],
     "significado": "Culminación y logro; integras lo aprendido en un todo.",
     "invertida": "Incompletitud, retraso o falta de cierre."},
]

PALOS = [
    {"nombre": "Bastos", "elemento": "fuego", "dominio": "la acción, la pasión, el trabajo y la iniciativa"},
    {"nombre": "Copas", "elemento": "agua", "dominio": "las emociones, el amor y las relaciones"},
    {"nombre": "Espadas", "elemento": "aire", "dominio": "la mente, el conflicto y la verdad"},
    {"nombre": "Oros", "elemento": "tierra", "dominio": "el dinero, el cuerpo y lo material"},
]

RANGOS = [
    {"nombre": "As", "significado": "Un comienzo y una semilla de potencial"},
    {"nombre": "Dos", "significado": "La dualidad y una elección a tomar"},
    {"nombre": "Tres", "significado": "El crecimiento y la colaboración"},
    {"nombre": "Cuatro", "significado": "La estabilidad y una pausa para consolidar"},
    {"nombre": "Cinco", "significado": "El conflicto y un cambio necesario"},
    {"nombre": "Seis", "significado": "La armonía y el equilibrio recuperado"},
    {"nombre": "Siete", "significado": "La evaluación y un desafío que pide estrategia"},
    {"nombre": "Ocho", "significado": "El movimiento y la maestría en la acción"},
    {"nombre": "Nueve", "significado": "La culminación y la independencia"},
    {"nombre": "Diez", "significado": "La plenitud y el cierre de un ciclo"},
    {"nombre": "Sota", "significado": "Un mensaje y el aprendizaje de algo nuevo"},
    {"nombre": "Caballo", "significado": "La acción impetuosa y el impulso en marcha"},
    {"nombre": "Reina", "significado": "La madurez emocional y el cuidado"},
    {"nombre": "Rey", "significado": "La autoridad y el dominio consolidado"},
]


# ---------------------------------------------------------------------------
# Arcanos menores escritos a mano (tradición Rider-Waite-Smith)
# ---------------------------------------------------------------------------
MENORES_BASTOS = [
    {"nombre": "As de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "As", "numero": 1,
     "palabras_clave": ["inspiración", "impulso", "creatividad", "potencial"],
     "significado": "Una chispa de inspiración y energía creativa: el arranque de un proyecto apasionante.",
     "invertida": "La chispa se dispersa: retrasos, falta de dirección o energía sin cauce.",
     "contextos": {"amor": "Atracción nueva que enciende la ilusión.",
                   "trabajo": "Proyecto naciente que pide acción.",
                   "dinero": "Oportunidad de inversión en ciernes.",
                   "salud": "Energía desbordada que necesita descarga."}},
    {"nombre": "Dos de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Dos", "numero": 2,
     "palabras_clave": ["planificación", "visión", "decisión", "coraje"],
     "significado": "Sostienes el mundo en tus manos y decides hasta dónde llegar; tus planes se hacen más grandes.",
     "invertida": "Miedo a lo desconocido: te encierras en lo seguro y recortas tus planes.",
     "contextos": {"amor": "Decidir hacia dónde dirigir la relación.",
                   "trabajo": "Sopesar una expansión o un cambio de rumbo.",
                   "dinero": "Valorar riesgos antes de invertir.",
                   "salud": "Marcarte metas de bienestar con ambición."}},
    {"nombre": "Tres de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Tres", "numero": 3,
     "palabras_clave": ["expansión", "colaboración", "previsión", "crecimiento"],
     "significado": "Tus primeros frutos asoman en el horizonte y el trabajo en equipo abre nuevos caminos.",
     "invertida": "La expansión se frena: falta de visión, de coordinación o resultados lentos.",
     "contextos": {"amor": "La relación crece y se proyecta al futuro.",
                   "trabajo": "Colaboraciones que amplían tu alcance.",
                   "dinero": "Primeros beneficios de una buena siembra.",
                   "salud": "Progreso constante si mantienes la disciplina."}},
    {"nombre": "Cuatro de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Cuatro", "numero": 4,
     "palabras_clave": ["celebración", "hogar", "comunidad", "armonía"],
     "significado": "Se celebra un logro en familia o comunidad: estabilidad, acogida y alegría compartida.",
     "invertida": "La celebración se pospone o falta el apoyo del entorno en tu logro.",
     "contextos": {"amor": "Compromiso y convivencia feliz.",
                   "trabajo": "Equipo unido que celebra resultados.",
                   "dinero": "Hogar estable y gastos en comunidad.",
                   "salud": "Bienestar emocional y sentido de pertenencia."}},
    {"nombre": "Cinco de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Cinco", "numero": 5,
     "palabras_clave": ["conflicto", "competencia", "rivalidad", "tensión"],
     "significado": "Varias varas se cruzan: desacuerdos y competencia que ponen a prueba tu postura.",
     "invertida": "La disputa termina o la evitas: alivio del choque o conflicto reprimido.",
     "contextos": {"amor": "Riñas y celos que tensionan el vínculo.",
                   "trabajo": "Competencia sana o luchas de poder internas.",
                   "dinero": "Gastos por disputas o competencia de precios.",
                   "salud": "Irritabilidad y tensión muscular acumulada."}},
    {"nombre": "Seis de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Seis", "numero": 6,
     "palabras_clave": ["victoria", "reconocimiento", "triunfo", "orgullo"],
     "significado": "Vuelves vencedor y la multitud te aclama: reconocimiento público a tu esfuerzo.",
     "invertida": "El reconocimiento no llega, el orgullo se hiere o triunfas con vanidad.",
     "contextos": {"amor": "La pareja te admira y te apoya.",
                   "trabajo": "Ascenso, premio o elogio público.",
                   "dinero": "Ganancias ligadas a tu reputación.",
                   "salud": "Vitalidad alta y confianza en ti mismo."}},
    {"nombre": "Siete de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Siete", "numero": 7,
     "palabras_clave": ["defensa", "persistencia", "valentía", "resistencia"],
     "significado": "Desde tu altura defiendes lo conseguido ante quien te cuestiona: mantén la posición.",
     "invertida": "Te sientes superado y dudas: cedes terreno por agotamiento o inseguridad.",
     "contextos": {"amor": "Defender la relación frente a críticas externas.",
                   "trabajo": "Sostener tu proyecto ante la competencia.",
                   "dinero": "Proteger tus recursos de amenazas externas.",
                   "salud": "Resistencia física a prueba; no bajes la guardia."}},
    {"nombre": "Ocho de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Ocho", "numero": 8,
     "palabras_clave": ["rapidez", "noticias", "movimiento", "fluidez"],
     "significado": "Ocho varas cruzan el cielo veloz: noticias, viajes y cambios que se suceden sin pausa.",
     "invertida": "El ritmo se atasca: retrasos, malentendidos o energía que pierde dirección.",
     "contextos": {"amor": "Un mensaje o encuentro que acelera el romance.",
                   "trabajo": "Trámites y proyectos que avanzan rápido.",
                   "dinero": "Movimientos económicos veloces e imprevistos.",
                   "salud": "Nervios acelerados; conviene bajar el ritmo."}},
    {"nombre": "Nueve de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Nueve", "numero": 9,
     "palabras_clave": ["resiliencia", "cautela", "fortaleza", "experiencia"],
     "significado": "Herido pero en pie, aguantas la última embestida: la experiencia se vuelve escudo.",
     "invertida": "El cansancio puede más: desconfianza excesiva o rendirse justo antes del final.",
     "contextos": {"amor": "Vínculo tocado que resiste con cicatrices.",
                   "trabajo": "Proyecto superviviente que exige vigilancia.",
                   "dinero": "Ahorro de reserva para imprevistos.",
                   "salud": "Convalecencia: cuidado con las recaídas."}},
    {"nombre": "Diez de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Diez", "numero": 10,
     "palabras_clave": ["carga", "responsabilidad", "esfuerzo", "meta"],
     "significado": "Cargas diez varas hacia la meta: demasiada responsabilidad sobre tus hombros.",
     "invertida": "Aprendes a soltar y delegar, o simplemente colapsas bajo el peso.",
     "contextos": {"amor": "Sientes la relación como una carga pesada.",
                   "trabajo": "Sobrecarga de tareas y plazos ajustados.",
                   "dinero": "Gastos que superan tus fuerzas; pide ayuda.",
                   "salud": "Cansancio físico y dolor de espalda."}},
    {"nombre": "Sota de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Sota", "numero": 11,
     "palabras_clave": ["entusiasmo", "exploración", "descubrimiento", "mensaje"],
     "significado": "Un joven entusiasta otea el horizonte: llega un mensaje ilusionante y ganas de explorar.",
     "invertida": "Impulsividad inmadura: dispersión, malas noticias o ilusiones sin fundamento.",
     "contextos": {"amor": "Coqueteo nuevo y emoción incipiente.",
                   "trabajo": "Idea o aprendizaje que ilusiona empezar.",
                   "dinero": "Pequeña oportunidad que explorar con cautela.",
                   "salud": "Ganas de moverte; cuidado con la impaciencia."}},
    {"nombre": "Caballero de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Caballero", "numero": 12,
     "palabras_clave": ["aventura", "ímpetu", "carisma", "acción"],
     "significado": "Un jinete apasionado carga hacia sus metas con carisma y prisa aventurera.",
     "invertida": "El ímpetu se desboca: impaciencia, arrebatos y promesas que se apagan.",
     "contextos": {"amor": "Pretendente intenso pero poco constante.",
                   "trabajo": "Alguien que impulsa proyectos con fuego.",
                   "dinero": "Gasto impulsivo tras una corazonada.",
                   "salud": "Energía explosiva que agota si no se dosifica."}},
    {"nombre": "Reina de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Reina", "numero": 13,
     "palabras_clave": ["confianza", "calidez", "independencia", "determinación"],
     "significado": "Mujer segura y magnética que lidera con calidez y no teme brillar.",
     "invertida": "Los celos y la exigencia desbordan su carisma; necesita admiración constante.",
     "contextos": {"amor": "Pareja apasionada, protectora y celosa.",
                   "trabajo": "Liderazgo carismático que inspira al equipo.",
                   "dinero": "Buen hacer para generar y administrar ingresos.",
                   "salud": "Vitalidad y autoestima altas."}},
    {"nombre": "Rey de Bastos", "palo": "Bastos", "elemento": "fuego", "rango": "Rey", "numero": 14,
     "palabras_clave": ["liderazgo", "visión", "emprendimiento", "honor"],
     "significado": "Líder carismático y emprendedor que domina su terreno con visión y honor.",
     "invertida": "El liderazgo se tuerce: autoritarismo, impulsividad o poder vacío.",
     "contextos": {"amor": "Pareja protectora de voluntad fuerte.",
                   "trabajo": "Emprendedor que ve lejos y decide rápido.",
                   "dinero": "Negocios prósperos bien dirigidos.",
                   "salud": "Buena constitución; vigilar el exceso de estrés."}},
]

MENORES = list(MENORES_BASTOS)


def _compose_minores() -> list[dict]:
    out = []
    for palo in PALOS:
        for rango in RANGOS:
            nombre = f"{rango['nombre']} de {palo['nombre']}"
            out.append({
                "nombre": nombre,
                "palo": palo["nombre"],
                "elemento": palo["elemento"],
                "rango": rango["nombre"],
                "palabras_clave": [palo["dominio"].split(", ")[0], rango["significado"].split(" y ")[0]],
                "significado": f"{rango['significado']} en el ámbito de {palo['dominio']}.",
                "invertida": "Energía bloqueada o en exceso dentro de su ámbito.",
            })
    return out


def build() -> dict:
    menores = _compose_minores()
    return {
        "tarot": {"mayores": MAYORES, "menores": menores},
        "astrologia": {"signos": SIGNOS, "planetas": PLANETAS, "casas": CASAS, "aspectos": ASPECTOS},
        "numerologia": NUMEROS,
    }


def validate(data: dict) -> list[str]:
    errs = []
    t = data["tarot"]
    if len(t["mayores"]) != 22:
        errs.append(f"mayores: {len(t['mayores'])} != 22")
    if len(t["menores"]) != 56:
        errs.append(f"menores: {len(t['menores'])} != 56")
    if len(t["mayores"]) + len(t["menores"]) != 78:
        errs.append("total tarot != 78")
    for c in t["mayores"] + t["menores"]:
        for k in ("nombre", "significado", "invertida"):
            if not c.get(k):
                errs.append(f"tarot {c.get('nombre')}: falta {k}")
    a = data["astrologia"]
    for key, n in (("signos", 12), ("planetas", 10), ("casas", 12), ("aspectos", 5)):
        if len(a[key]) != n:
            errs.append(f"astrologia.{key}: {len(a[key])} != {n}")
    if len(data["numerologia"]) != 12:
        errs.append(f"numerologia: {len(data['numerologia'])} != 12")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true", help="solo valida, no escribe")
    ap.add_argument("--out", default=str(KB_DIR), help="directorio de salida")
    args = ap.parse_args()

    data = build()
    errs = validate(data)
    for e in errs:
        print(f"[!] {e}")
    if errs:
        return 1

    print("KB válida:")
    print(f"  tarot: {len(data['tarot']['mayores'])} mayores + {len(data['tarot']['menores'])} menores = "
          f"{len(data['tarot']['mayores']) + len(data['tarot']['menores'])} cartas")
    print(f"  astrologia: {len(SIGNOS)} signos, {len(PLANETAS)} planetas, {len(CASAS)} casas, {len(ASPECTOS)} aspectos")
    print(f"  numerologia: {len(NUMEROS)} números")

    if args.validate:
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tarot.json").write_text(json.dumps(data["tarot"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "astrologia.json").write_text(json.dumps(data["astrologia"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "numerologia.json").write_text(json.dumps(data["numerologia"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Escritos en {out}/: tarot.json, astrologia.json, numerologia.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
