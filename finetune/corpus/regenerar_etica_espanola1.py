#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenera los bloques `etica` y `espanola_1` colapsados por dedupe v1e (T142).

Contexto
--------
En v1d `etica` solo tenía 7 preguntas únicas (281 filas) y `espanola_1`
76 combinaciones de carta+orientación con 24 preguntas: tras el dedupe
quedaron 5 filas de `etica` y 46 de `espanola_1` para entrenar. La causa
es el pool diminuto del generador (`CASOS_ETICA`) y la plantilla v1d:
`auditoria_v1d.prompt_propio` corta el prompt en la línea «Baraja española
de 40 naipes», que iba ANTES de la pregunta, de modo que el contexto y la
pregunta no contaban para la unicidad.

Este script construye jobs nuevos con variabilidad real:

- `etica`: 12 categorías de situaciones éticas reales (crisis emocional,
  salud, menores, legal, dependencia de la consulta, presión para predecir
  muerte/embarazo/infidelidad, manipulación de terceros, dinero, duelo,
  adicciones), ~24 preguntas únicas por categoría. Las respuestas acogen,
  no sentencian ni predicen; en riesgo vital remiten a la línea 024
  (España) y SOLO en esos casos.
- `espanola_1`: carta × orientación × contexto × pregunta (40 naipes × 2
  orientaciones × 6 contextos × 14 preguntas). La plantilla coloca el
  boilerplate («Baraja española de 40 naipes...») DESPUÉS de la pregunta,
  de modo que `prompt_propio` incluye carta, orientación, contexto y
  pregunta: la unicidad queda garantizada por construcción. Los significados
  salen de la KB (`kb/baraja_espanola.json`) vía `fase1_prompts._referencia`;
  no se mezcla tarot ni baraja francesa.

No toca `generate_tasks.py` ni `fase1_prompts.py`: los importa y los
parchea en runtime de forma ACOTADA (solo las familias `etica` y
`espanola_1`, que son las únicas de esta BD). La salida va a
`/Users/angelgonzalez/fase0/etica_espanola1_v2/`; el dataset v1e no se
toca.

Verificación extra por fila (además de la canónica `verificar_lectura`):
- tuteo estándar: se rechaza el voseo;
- 024: obligatorio en consultas de riesgo vital, prohibido en las demás;
- punto final; sin autodenominarse IA; sin inglés;
- anti-copia entre filas (Jaccard de 12-gramas plegados >= 0.83) post-export;
- fuga de evaluación (casos T56) vía `qa.fugas_eval` post-export.

Objetivo: >= 250 filas válidas por bloque con >= 90% de prompts únicos.

Encendido del LLM: SOLO nodo2 (`http://10.0.0.4:8000/v1`), 1 worker.
Nunca Mercury, nunca nodo1 para generación de datos.

Subcomandos
-----------
  --dry-run    Construye los jobs en memoria: cifras, unicidad, fuga eval y
               estimación de llamadas/tokens. Sin efectos en disco ni red.
  --prepare    Crea la BD de trabajo e inserta los jobs como `pending`
               (idempotente: no duplica los ya `done`).
  --run        Ejecuta la generación contra nodo2 (1 worker), reanudable.
  --report     Informe de cifras, rechazos por motivo y export final.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import auditoria_v1d as aud  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import generate_tasks as gt  # noqa: E402
import qa_dataset as qa  # noqa: E402

WORK_DIR_DEFECTO = "/Users/angelgonzalez/fase0/etica_espanola1_v2"
DB_NOMBRE = "jobs_etica_esp1_v2.db"
JSONL_FINAL = "etica_espanola1_v2.jsonl"
ENDPOINT_NODO2 = "http://10.0.0.4:8000/v1"
MODELO_DEFECTO = "halogen-qwen3.8-flash-next"
EVAL_DIR_DEFECTO = "/Users/angelgonzalez/fase0/dataset_fase1_v1d/_etapas/eval"

N_ETICA = 280
N_ESPANOLA = 280
MIN_VALIDAS = 250
UMBRAL_UNICIDAD = 0.90
SIM_COPIA = 0.83
N_GRAM_COPIA = 12
CHARS_POR_TOKEN = 4.0
REINTENTOS_ESTIMADOS = 0.3

FAMILIAS_T142 = ("etica", "espanola_1")

BOILER_ESP1 = ("Baraja española de 40 naipes: no es tarot ni baraja "
               "francesa; no la mezcles.")

INSTRUCCION_TUTEO = (
    " Responde siempre en español estándar con tuteo (tú); nunca uses voseo "
    "(ni «vos», «querés», «podés», «tenés», «contame», «decime», «mirá»)."
)

INSTRUCCION_024 = (
    " Si la persona está en riesgo vital inmediato, indícale claramente que "
    "llame ahora al 024, la línea de atención a la conducta suicida en "
    "España, y que no está sola."
)

# Formas voseantes explícitas (lista cerrada, sin patrón genérico -ás/-és/-ís
# para evitar falsos positivos en español estándar con tildes).
VOSEO_FORMS = (
    "querés", "podés", "tenés", "hacés", "decís", "sabés", "querés",
    "vendés", "comés", "vivís", "escribís", "venís", "irás vos",
    "contame", "decime", "mirá vos", "andá", "sentate", "acordate",
    "fijate", "pensá", "jugá", "buscá", "llamá", "llamame", "contame",
    "vos tenés", "vos podés", "vos querés", "vos sabés", "vos hacés",
    "vos",
)
RE_VOSEO = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in sorted(set(VOSEO_FORMS))) + r")\b",
    re.IGNORECASE,
)

RE_INGLES = re.compile(
    r"\b(the|and|you|your|they|them|with|what|where|when|that|this)\b",
    re.IGNORECASE,
)

AUTODENOMINACIONES_IA = (
    "asistente de ia", "como ia", "modelo de lenguaje", "no soy humano",
    "inteligencia artificial", "soy una ia",
)

PUNTOS_FINALES = tuple('.!?…»"\'')

# --------------------------------------------------------------------------- #
# Bancos de preguntas (T142): variabilidad real, español estándar con tildes
# --------------------------------------------------------------------------- #

ETICA_BANCO = {
    "crisis_emocional": {
        "riesgo": True,
        "preguntas": [
            "Llevo semanas pensando que sería mejor desaparecer, no quiero seguir así. ¿Qué me dicen las cartas?",
            "He vuelto a cortarme cuando la ansiedad me desborda y no sé qué hacer conmigo.",
            "Esta mañana no quería levantarme de la cama y he pensado en no volver a hacerlo nunca.",
            "Siento que nadie me quiere y que el mundo iría mejor sin mí. ¿Lo ve así la baraja?",
            "Estoy aguantando un dolor que no puedo contar a nadie y a veces pienso en hacerme daño.",
            "He perdido a mi mejor amiga y quiero seguir su camino, no sé vivir sin ella.",
            "Cada noche lloro hasta quedarme dormida y por la mañana quiero que no amanezca.",
            "Tengo pensamientos de hacerme daño cuando bebo, y esta noche he bebido.",
            "Mi pareja me ha dejado y siento que no tiene sentido seguir viva.",
            "Llevo meses con una angustia que no me deja respirar y pienso en acabar con todo.",
            "He planificado cómo irme de este mundo y he venido a consultarte antes de hacerlo.",
            "No duermo, no como, solo pienso en desaparecer. Dime algo que me dé una razón.",
            "Siento que soy una carga para mi familia y que estarían mejor sin mí.",
            "Me he hecho daño otra vez esta semana y no puedo parar, ayúdame con la lectura.",
            "Quiero morir, no es una llamada de atención, lo digo muy en serio.",
            "Después del diagnóstico de mi padre no quiero seguir, pienso en irme yo también.",
            "Estoy sola en otra ciudad, sin amigos ni familia, y la soledad me mata.",
            "He dejado de creer que las cosas puedan mejorar y ya no quiero intentarlo más.",
            "Cada día es una lucha y esta noche estoy más cansada que nunca de luchar.",
            "Tengo miedo de estar pensando en el suicidio demasiado a menudo, ¿qué hago?",
            "Mi hijo pequeño es lo único que me ata a la vida, pero ya no puedo más.",
            "He escrito una carta de despedida y dudo, por eso vengo a consultarte.",
            "Nadie me toma en serio cuando digo que estoy mal, ¿la carta al menos me escucha?",
            "Siento un vacío enorme desde que perdí el trabajo y pienso en no despertar.",
        ],
    },
    "salud": {
        "riesgo": False,
        "preguntas": [
            "Me han dado un diagnóstico grave y no sé si contarlo a mi familia, ¿qué hago?",
            "¿La carta me confirma que la operación saldrá bien y me curaré?",
            "Estoy dudando entre seguir el tratamiento médico o probar una terapia natural, ¿qué elijo?",
            "Mi médico dice que debo operarme pero tengo mucho miedo, ¿qué me recomienda la baraja?",
            "¿Tengo algún problema de salud que las cartas puedan ver antes de las pruebas?",
            "Llevo meses con dolores y las pruebas salen normales, ¿qué me está diciendo mi cuerpo?",
            "¿Debo dejar la medicación que me tienen recetada desde hace años?",
            "Mi madre está muy grave en la UCI, ¿va a salir de esta?",
            "¿El tratamiento de quimioterapia va a funcionar en mi caso?",
            "Tengo miedo de tener una enfermedad grave, ¿la carta lo ve?",
            "Me han dicho que mi corazón está mal, ¿debo operarme ya o esperar?",
            "¿La ansiedad que siento es física o mental? No sé a quién acudir.",
            "Quiero saber si mi hijo tiene TDAH o si solo es travieso, ¿la carta lo aclara?",
            "¿Me voy a quedar calva con este tratamiento? Es mi mayor miedo.",
            "El médico me ha dado pocas esperanzas, ¿la baraja ve una recuperación?",
            "¿Debo hacerme la prueba genética que me ofrecen o es mejor no saberlo?",
            "Duermo fatal desde hace meses, ¿la carta ve la causa de mi insomnio?",
            "Me duele todo el cuerpo y nadie me cree, ¿qué hago?",
            "¿Es seguro el anticonceptivo nuevo que me han puesto? Tengo miedo de los efectos.",
            "Mi abuela tiene Alzheimer y no me reconoce, ¿queda algo de ella dentro?",
            "¿Debo donar un riñón a mi hermano aunque mi médico me diga que es arriesgado?",
            "Tengo un bulto y me da miedo ir al médico, ¿la carta me dice si es grave?",
            "¿Volveré a correr algún día después de esta lesión de rodilla?",
            "Mi psiquiatra me cambió la medicación y estoy peor, ¿fue un error?",
        ],
    },
    "menores": {
        "riesgo": False,
        "preguntas": [
            "Mi hija de doce años quiere que le lea las cartas sobre sus amigas, ¿es apropiado?",
            "Mi hijo de diez años me pregunta si su abuelo ha muerto, ¿qué le respondo?",
            "Mi adolescente no habla conmigo y quiero usar la baraja para entenderlo.",
            "Mi niña tiene miedo de que sus padres se divorcien, ¿la carta me dice qué decirle?",
            "¿Le hago una lectura a mi hijo sobre los exámenes o le estoy metiendo ideas raras?",
            "Mi hija de trece años me pide una lectura sobre si le gusta un chico de clase.",
            "Los abuelos de mi hijo le leen el tarot constantemente y yo no sé si prohibirlo.",
            "Mi niño se orina en la cama y su padre quiere consultar la carta, ¿yo qué hago?",
            "¿Es bueno que mi hija crea en las cartas o la estoy confundiendo?",
            "Mi hijo pequeño pregunta si su gato muerto está bien, ¿le digo algo del más allá?",
            "Quiero leerle a mi hija adoptiva sobre su madre biológica, ¿es sano?",
            "Mi hija de once años tiene ansiedad por los estudios, ¿la carta me da una respuesta para ella?",
            "¿Consulto la baraja sobre el futuro profesional de mi hijo de quince años?",
            "Mi hijo me ha visto leer las cartas y ahora quiere que le diga el futuro de sus amigos.",
            "¿Le hago una tirada a mi bebé para ver cómo será de mayor?",
            "Mi hija adolescente quiere una lectura sobre si su novio la engaña, ¿se lo hago?",
            "Los amigos de mi hijo le han metido miedo con una carta maldita, ¿cómo lo arreglo?",
            "Mi niño pregunta por qué su hermana no puede tener hijos, ¿cómo se lo explico?",
            "¿Es ético leer a menores sin permiso de ambos padres?",
            "Mi hija sueña con ser famosa y me pide una lectura sobre su futuro artístico.",
            "Mi hijo de nueve años tiene miedo de la muerte desde que murió su abuelo, ¿qué le digo?",
            "Quiero usar las cartas para que mi hija estudie más, ¿funciona o es un error?",
            "Mi adolescente me pide una lectura sobre drogas, sus amigos le ofrecen cosas.",
            "¿Le leo a mi hija sobre si va a entrar en el instituto que quiere?",
        ],
    },
    "legal": {
        "riesgo": False,
        "preguntas": [
            "Tengo un juicio de custodia la semana que viene, ¿el naipe me dice si voy a ganar?",
            "Me han demandado por una deuda, ¿la carta me dice si debo pagar o pelear?",
            "¿Voy a conseguir el divorcio rápido o mi abogado me está mintiendo sobre los plazos?",
            "La carta debe decirme si el juez me dará la razón en el caso de herencia.",
            "Me ofrecen un acuerdo económico y no sé si aceptarlo, decide tú con la baraja.",
            "¿Mi ex va a intentar quitarme a los niños en el juicio?",
            "Estoy pensando en denunciar a mi jefe, ¿la carta me dice si saldré ganando?",
            "¿Me van a echar del trabajo y no me corresponde indemnización?",
            "Tengo un problema con hacienda y quiero saber si tendré problemas legales.",
            "¿La baraja ve si mi vecino va a retirar la denuncia?",
            "Mi hermano está detenido, ¿va a entrar en prisión o saldrá?",
            "¿Debo fiarme del abogado nuevo que me han recomendado?",
            "Quiero saber si el testigo dirá la verdad en el juicio.",
            "¿La carta me dice si me devolverán el dinero que me deben?",
            "Estoy tramitando una adopción y temo que la rechacen, ¿qué ve el naipe?",
            "Me han robado y la policía no avanza, ¿la carta sabe quién fue?",
            "¿Voy a perder la casa por la hipoteca?",
            "Mi socio me quiere expulsar, ¿la baraja me dice si tengo razón legal?",
            "¿Debo declarar todo en el juicio o hay cosas que me perjudican?",
            "Tengo un litigio por una finca, ¿la carta me dice quién ganará?",
            "¿Me van a conceder la pensión que pido?",
            "Quiero denunciar a mi expareja por control, ¿la carta me dice si es delito?",
            "¿La lectura puede decirme si mi abogado me está robando?",
            "Me han puesto una multa injusta, ¿recurro o pago? Decide la carta.",
        ],
    },
    "dependencia": {
        "riesgo": False,
        "preguntas": [
            "Le pregunto a la baraja diez veces al día si él me llama, no puedo evitarlo.",
            "Sin consultar la carta no puedo decidir ni qué ropa ponerme, ¿es normal?",
            "Cada decisión que tomo pasa primero por las cartas y ya no pienso por mí misma.",
            "Gasto todo mi dinero en consultas y no puedo parar, ¿me estoy arruinando?",
            "Si no saco una carta buena, no salgo de casa ese día.",
            "Mi pareja dice que las cartas me controlan más que yo a ellas, ¿es cierto?",
            "Consulto la baraja para todo: trabajo, amor, salud, dinero. No sé vivir sin ello.",
            "Llevo tres cartas hoy porque las primeras no me gustaron, ¿cuál es el límite?",
            "Siento ansiedad si no consulto, y ansiedad con la consulta, ¿qué hago?",
            "Quiero que la carta me diga si debo dejar de consultar tanto, ¿se puede?",
            "No duermo si antes no hago una tirada sobre el día de mañana.",
            "He consultado a cinco tarotistas distintos el mismo asunto porque ninguno me convence.",
            "Mi familia me ha prohibido las cartas y yo sigo a escondidas.",
            "Cada mensaje que recibo lo consulto con la baraja antes de contestar.",
            "Siento que sin las cartas no tengo protección, ¿es sano depender así?",
            "Consulto hasta para tirar la basura, ¿dónde pongo el freno?",
            "Gasto dos horas diarias en lecturas y he dejado de hacer mi trabajo.",
            "Si la carta sale mal, repito hasta que salga bien, ¿eso es trampa?",
            "Tengo miedo de que dejes de atenderme y no sé qué haré sin tus lecturas.",
            "Las cartas deciden si hablo o no con mi madre desde hace años.",
            "Cada noche hago una tirada para saber si él me piensa, aunque no hablemos.",
            "Siento que me estoy volviendo loca por consultar tanto, ¿me ayudas?",
            "Antes consultaba una vez al mes y ahora es cada hora, ¿cómo lo paro?",
            "Quiero dejar de consultar pero siento que si no lo hago pasará algo malo.",
        ],
    },
    "presion_muerte": {
        "riesgo": False,
        "preguntas": [
            "Dime con la baraja cuánto tiempo de vida me queda, necesito saberlo.",
            "Mi madre está muy grave, ¿va a morir esta noche? Contesta con la carta.",
            "¿Cuándo voy a morir? Quiero la fecha exacta que vea la baraja.",
            "Tira una carta y dime si mi marido va a morir pronto.",
            "¿Voy a morir de la misma enfermedad que mi padre? Dímelo ya.",
            "La carta debe decirme si mi hijo corre peligro de muerte.",
            "¿Me quedan cinco años de vida o veinte? Necesito un número.",
            "Sueño con mi abuela muerta, ¿la carta me dice cuándo me tocará a mí?",
            "¿Voy a morir sola o acompañada? Quiero saberlo ahora.",
            "Dime si moriré en un accidente, lo soñé y necesito confirmarlo.",
            "¿Mi pareja me sobrevivirá o morimos el mismo año?",
            "La baraja tiene que decirme si este año es el último de mi vida.",
            "¿Voy a morir joven como mi tía? Contesta sin rodeos.",
            "Quiero saber la causa de mi muerte según las cartas.",
            "¿Mi médico se equivoca y me queda menos de lo que dice?",
            "Dime si mi enemigo va a morir pronto, lo necesito para estar tranquila.",
            "¿La carta ve mi fecha de defunción? Sé que los tarotistas la ven.",
            "Si no me dices cuándo muero, consultaré a otro que sí lo haga.",
            "¿Moriré en esta casa o en otra? Quiero detalles.",
            "Tira la carta y dime si me quedan menos de diez años.",
            "¿Voy a sufrir mucho al morir o será tranquilo?",
            "Mi marido dice que la carta no puede decir cuándo se muere, ¿tú qué dices?",
            "¿Puedes ver en el naipe si mi hijo mayor morirá antes que yo?",
            "Necesito que la baraja me confirme que no voy a morir este año.",
        ],
    },
    "presion_embarazo": {
        "riesgo": False,
        "preguntas": [
            "¿Estoy embarazada? Tira una carta y dime la verdad, llevo dos semanas de retraso.",
            "Mi novio y yo buscamos bebé, ¿la carta dice si llegará este año?",
            "¿El test me ha salido negativo por error? La carta debe decirme si estoy encinta.",
            "Quiero saber si será niño o niña antes de la ecografía, dime con la baraja.",
            "¿Puedo quedarme embarazada o mi médico tiene razón y es difícil?",
            "La carta debe confirmarme que estoy embarazada de dos meses.",
            "Mi marido no quiere hijos y yo sí, ¿la carta dice si cederá?",
            "¿Voy a tener gemelos? Lo soñé y quiero confirmación en el naipe.",
            "Llevo un año buscando el embarazo, ¿la baraja me dice si lo conseguiré?",
            "¿Debo abortar o seguir adelante? Decide tú con la carta.",
            "Quiero una carta que me diga si mi hija está embarazada sin preguntarle.",
            "¿El bebé que busco vendrá antes de los cuarenta? Dímelo claro.",
            "La baraja tiene que decirme si este mes he concebid.",
            "¿Estoy embarazada de mi ex? No quiero otra prueba, dime con la carta.",
            "¿Será niño? Apuesto con mi cuñada y necesito la carta.",
            "Si la carta dice que sí, dejo las pastillas anticonceptivas hoy mismo.",
            "¿Puedo tener un embarazo sano a mi edad? Contesta con el naipe.",
            "Quiero saber si mi hija adolescente está embarazada, ¿la carta lo ve?",
            "¿El tratamiento de fertilidad funcionará a la primera?",
            "Dime si vendrán dos embarazos en mi vida o solo uno.",
            "¿La carta confirma que no estoy embarazada y puedo respirar tranquila?",
            "Mi pareja insiste en preguntar el sexo del bebé con las cartas, ¿se puede?",
            "¿Quedé embarazada la noche de la fiesta? Necesito saberlo hoy.",
            "La baraja debe decirme si debo seguir buscando o rendirme.",
        ],
    },
    "presion_infidelidad": {
        "riesgo": False,
        "preguntas": [
            "¿Mi pareja me engaña? Necesito que la carta me lo confirme, tengo pruebas a medias.",
            "Sospecho de mi mujer con su compañero de trabajo, ¿qué ve el naipe?",
            "Dime con la baraja si él me es infiel, no me vale un depende.",
            "Encontré mensajes en su móvil, ¿la carta me dice si fue solo una vez?",
            "¿Mi novio me pone los cuernos con mi amiga? Contesta con la carta.",
            "Quiero que la baraja me diga el nombre de su amante.",
            "¿Volverá a engañarme si le perdono? La carta debe ser clara.",
            "Mi marido viaja mucho, ¿la carta ve a otra mujer en sus viajes?",
            "¿Me engaña o estoy loca de celos? Dime la verdad con el naipe.",
            "La carta tiene que decirme si él esta noche está con otra.",
            "¿Mi mujer me fue infiel en el pasado y nunca lo supe?",
            "Quiero una carta que confirme mis sospechas para plantarle cara.",
            "¿El padre del bebé de mi ex es otro? La baraja debe resolverlo.",
            "Mi pareja jura que no hay nadie, ¿la carta le cree?",
            "¿Me engaña con mi propio hermano? Es lo que temo, dime.",
            "La baraja debe decirme si sus salidas de viernes son con amigos o con ella.",
            "¿Dejo a mi pareja por infiel según lo que veas en la carta?",
            "Quiero saber si mi marido me engaña desde antes de casarnos.",
            "¿La carta ve mensajes prohibidos en su teléfono?",
            "Si la carta dice que sí, mañana mismo le pido el divorcio.",
            "¿Mi novia me engaña con su ex que ha vuelto a aparecer?",
            "Dime si los celos que tengo están justificados según el naipe.",
            "¿Hay una tercera persona en mi matrimonio? Contesta con la carta.",
            "La baraja me tiene que decir si él me engañó en el viaje a Madrid.",
        ],
    },
    "manipulacion": {
        "riesgo": False,
        "preguntas": [
            "Un amigo me paga para que le lea a su novia y la convenza de volver con él, ¿lo hago?",
            "Quiero usar la lectura para que mi ex me perdone, aunque él no quiera consultarte.",
            "Dime qué carta debo sacar para que mi jefa me suba el sueldo, yo la dirijo.",
            "Mi madre quiere una lectura amañada para que mi hermano deje las drogas, ¿le ayudo?",
            "Quiero que leas a mi rival y me digas sus puntos débiles para ganarle.",
            "Puedo pagar más si la lectura que le haces a mi pareja sale a mi favor.",
            "Necesito que la carta demuestre que mi hijo se equivoca, ya tengo la respuesta.",
            "Quiero usar tus lecturas para controlar a mi novio, ¿me enseñas cómo?",
            "Le miento a mi clienta diciéndole que las cartas mandan, ¿sigo engañándola?",
            "Quiero una lectura falsa para asustar a mi vecino y que venda la casa.",
            "Mi socio quiere que le lea y salirme con la mía, ¿me dejas?",
            "¿Puedo orientar la carta para que mi hija crea en mí otra vez?",
            "Quiero que leas a mi ex marido y le digas que volverá conmigo sí o sí.",
            "Uso las cartas para que mi pareja no se separe de mí, ¿es manipulación?",
            "Quiero que confirmes lo que yo ya decidí para que mi familia no discuta.",
            "Le pido a la carta lo que yo quiero oír y lo vendo como verdad, ¿está mal?",
            "Quiero una lectura que asuste a mi hija para que no viaje con sus amigos.",
            "Mi amiga me paga para que le diga a su novio que le sea fiel, ¿acepto?",
            "Quiero usar el miedo de mi madre a las cartas para que firme los papeles.",
            "¿Le hago una lectura a mi jefe para que no me despida, aunque no crea?",
            "Quiero que la carta diga lo que mi pareja necesita oír para no dejarme.",
            "Puedo dirigir el sorteo para que salga lo que yo quiero, ¿es trampa?",
            "Quiero convencer a mi hermano de que vote lo que yo con una lectura.",
            "Uso las cartas para que mi novio no se vaya con su ex, ¿me ayudas?",
        ],
    },
    "dinero": {
        "riesgo": False,
        "preguntas": [
            "He perdido los ahorros en apuestas, ¿la carta me dice cómo recuperarlos?",
            "¿Debo invertir mis ahorros en el negocio de mi cuñado? Decide la baraja.",
            "La carta debe decirme qué número jugar en la lotería del sábado.",
            "¿Me tocará la primitiva este año? Juega tú la carta por mí.",
            "Quiero saber si debo comprar esta casa o esperar a que baje el precio.",
            "¿El negocio que abro va a funcionar o perderé todo?",
            "La baraja tiene que decirme si vendo mis acciones hoy.",
            "¿Debo prestar dinero a mi amigo o me lo perderé?",
            "Quiero que la carta me diga dónde está el dinero que me robaron.",
            "¿Voy a quedar en la ruina con esta crisis o me salvaré?",
            "Dime con la baraja si acepto la oferta de trabajo con menos sueldo.",
            "¿Mi socio me está robando de la caja? La carta debe resolverlo.",
            "Quiero una carta que me diga si pedir un préstamo para el coche.",
            "¿Invierto en criptomonedas según lo que vea el naipe?",
            "La carta debe decirme si mi casero me subirá la renta.",
            "¿Recuperaré el dinero que invertí en el chiringuito de mi primo?",
            "Quiero saber si debo disputar la casa de mi tía en la herencia.",
            "¿Me conviene cambiar de banco o da igual? Decide la carta.",
            "La baraja debe decirme si pido aumento o busco otro trabajo.",
            "¿Debo cerrar mi tienda o resistir un año más? Tú decides con la carta.",
            "Quiero que la carta me diga en qué apostar para salir de deudas.",
            "¿Mi pareja me dejará sin nada en el divorcio? La carta lo sabe.",
            "Dime si compro el local de al lado para mi negocio.",
            "¿La carta ve abundancia o miseria en mis finanzas este año?",
        ],
    },
    "duelo": {
        "riesgo": False,
        "preguntas": [
            "Mi marido murió hace un año, quiero una carta suya para hablar con él, ¿puedes canalizarle?",
            "¿Mi madre fallecida está en paz? Dime qué mensaje me manda con la baraja.",
            "Quiero que las cartas me digan si mi hijo muerto me perdona.",
            "¿Mi abuelo me ve desde el más allá? Contesta con una carta.",
            "Necesito una lectura de mi hermana muerta para saber que está bien.",
            "La carta debe traerme las palabras de mi padre antes de morir.",
            "¿Volveré a ver a mi esposa? Dime si hay reencuentro tras la muerte.",
            "Quiero consultar por mi mascota muerta, ¿está bien donde esté?",
            "¿Mi hijo no nacido está en un lugar bueno? Dime con la baraja.",
            "La baraja tiene que decirme si mi madre me guarda desde el cielo.",
            "¿Mi marido me perdonó antes de morir? Necesito saberlo.",
            "Quiero una carta que me una a mi gemela fallecida.",
            "¿Los muertos pueden hablar contigo? Demuéstramelo con mi padre.",
            "La carta debe decirme si mi abuela está orgullosa de mí desde el más allá.",
            "¿Mi hermano muerto quiere que venda la casa familiar? Pregúntale.",
            "Necesito cerrar el duelo de mi hija y solo las cartas pueden ayudarme.",
            "¿Mi pareja muerta está esperando a que yo llegue? Dímelo.",
            "Quiero saber si hice todo lo posible por mi madre antes de que muriera.",
            "La baraja debe decirme si mi padre está en paz o sufriendo.",
            "¿Puedes preguntar a mi difunto si me quiere todavía?",
            "Quiero una lectura donde hable mi hija mayor que falleció.",
            "¿Mi abuelo me protege desde el más allá según las cartas?",
            "La carta debe confirmarme que volveré a ver a mi perro.",
            "Necesito que las cartas me den una señal de mi marido en el aniversario de su muerte.",
        ],
    },
    "adicciones": {
        "riesgo": False,
        "preguntas": [
            "Mi hermano no puede dejar el alcohol, ¿la carta me dice cómo sacarlo de ahí?",
            "Llevo tres días sin beber y pienso en recaer, ¿tengo fuerza para seguir?",
            "¿La baraja ve si mi marido volverá a beber después de dos años limpio?",
            "Quiero dejar el tabaco, ¿la carta me dice si lo conseguiré?",
            "Mi hijo está enganchado al juego online, ¿cómo lo saco? Decide la carta.",
            "¿Debo internar a mi padre o darle otra oportunidad? Tú con la baraja.",
            "La carta debe decirme si mi pareja recaerá en la cocaína.",
            "Bebo cada noche para dormir y no puedo parar, ¿qué hago?",
            "¿Mi adicción al juego se va a curar con las cartas?",
            "Quiero saber si mi hermano morirá por el alcohol si no hace caso.",
            "La baraja debe decirme si debo perdonar a mi madre alcohólica otra vez.",
            "¿Puedo controlar un solo trago o estoy perdida? Dime con la carta.",
            "Mi novio fuma porros y quiere dejarlo, ¿la carta dice si podrá?",
            "¿Dejo a mi pareja si vuelve a beber? Contesta con el naipe.",
            "La carta debe decirme si mi hijo tocará fondo pronto.",
            "Estoy en recuperación y necesito una carta que me dé ánimo hoy.",
            "¿Mi marido dejará el juego si le quito las tarjetas? Decide la baraja.",
            "Quiero saber si mi hija está usando drogas por lo que veas en la carta.",
            "¿La baraja ve una recaída en mi futuro cercano?",
            "Mi padre alcohólico promete dejarlo, ¿la carta cree que cumplirá?",
            "¿Debo ir a una reunión de AA o basto yo sola? Dime con la carta.",
            "Quiero que la carta me diga si mi hermano superará la heroína.",
            "¿El alcohol va a acabar conmigo o podré parar a tiempo?",
            "La baraja debe decirme si mi pareja me miente sobre su adicción.",
        ],
    },
}

ESPANOLA_BANCO = {
    "salud": [
        "¿Cómo estará mi energía durante las próximas semanas?",
        "¿Me recuperaré bien de la operación que me han programado?",
        "¿Qué debo cuidar más este mes para no enfermar?",
        "¿El estrés actual pasará factura a mi cuerpo?",
        "¿Volveré a dormir bien pronto?",
        "¿Qué me aconseja el naipe para manejar la ansiedad?",
        "¿Mi cuerpo está pidiendo un cambio de ritmo?",
        "¿Tendré una recuperación rápida de la lesión?",
        "¿Cómo afectará a mi salud el cambio de vida que estoy haciendo?",
        "¿Debo parar y descansar o puedo seguir con este ritmo?",
        "¿Qué fortaleza oculta mi cuerpo que no estoy aprovechando?",
        "¿La primavera me sentará bien o tendré recaídas?",
        "¿Cómo llevo el duelo en el cuerpo y qué me dice el naipe?",
        "¿Qué hábito nuevo me vendría mejor según la carta?",
    ],
    "amor": [
        "¿Qué me espera en el amor este mes?",
        "¿Debo dar el paso y declarar mis sentimientos?",
        "¿Él piensa en mí como yo en él?",
        "¿Esta relación tiene futuro o es un callejón?",
        "¿Cómo sano la herida de mi última ruptura?",
        "¿Volverá alguien de mi pasado o debo mirar adelante?",
        "¿Qué me impide abrirme al amor?",
        "¿Es el momento de comprometerme o de ir despacio?",
        "¿Qué necesita mi pareja de mí que no estoy viendo?",
        "¿El amor que siento es correspondido o me lo invento?",
        "¿Cómo superar los celos que me están comiendo?",
        "¿Debo perdonar la última discusión o cerrar la puerta?",
        "¿Qué aprendizaje me deja esta etapa sentimental?",
        "¿Estaré sola mucho tiempo o hay alguien cerca?",
    ],
    "trabajo": [
        "¿Cómo va mi carrera profesional este trimestre?",
        "¿Debo aceptar el ascenso que me ofrecen?",
        "¿Mi jefe valora lo que hago o me tiene olvidado?",
        "¿Busco otro trabajo o aguanto donde estoy?",
        "¿El proyecto que empiezo saldrá adelante?",
        "¿Qué habilidad debo desarrollar para crecer?",
        "¿Hay un rival interno que me esté saboteando?",
        "¿Debo emprender o me conviene la estabilidad?",
        "¿Cómo llevar la relación con mi equipo?",
        "¿Se reconocerá mi esfuerzo este año?",
        "¿El despido es inminente o es mi miedo?",
        "¿Qué decisión laboral me dará más satisfacción?",
        "¿Debo negociar el sueldo o callar?",
        "¿Mi vocación está donde estoy o me llama otra cosa?",
    ],
    "dinero": [
        "¿Cómo se estabilizarán mis finanzas este año?",
        "¿Debo ahorrar ya o puedo permitirme el gasto?",
        "¿El dinero que espero llegará finalmente?",
        "¿Qué bloqueo tengo con el dinero?",
        "¿Conviene hacer ahora la inversión que estoy mirando?",
        "¿Saldré de deudas antes de lo que temo?",
        "¿Debo fiarme de la oferta económica que me han hecho?",
        "¿Qué relación tengo con el dinero que me perjudica?",
        "¿El gasto imprevisto llegará o es solo mi preocupación?",
        "¿Cómo protejo lo que he ganado?",
        "¿Es buen momento para pedir un préstamo?",
        "¿La abundancia está cerca o debo apretarme el cinturón?",
        "¿Qué decisión económica tomaré con miedo y no con cabeza?",
        "¿El negocio familiar dará beneficios este año?",
    ],
    "espiritual": [
        "¿En qué punto de mi camino espiritual estoy?",
        "¿Qué me está enseñando esta etapa de mi vida?",
        "¿Tengo alguna misión que deba reconocer?",
        "¿Cómo profundizo mi práctica de meditación?",
        "¿Qué me frena para conectar conmigo misma?",
        "¿El silencio que busco llegará pronto?",
        "¿Qué símbolo del naipe me acompaña este año?",
        "¿Debo confiar más en mi intuición?",
        "¿Qué creencia antigua debo soltar?",
        "¿Cómo encuentro paz interior en medio del caos?",
        "¿Qué me pide el alma que no estoy escuchando?",
        "¿Estoy alineada con mi propósito?",
        "¿Qué práctica espiritual me conviene empezar?",
        "¿Cómo trabajo la gratitud en mi día a día?",
    ],
    "general": [
        "¿Qué me depara el mes que viene?",
        "¿En qué debo centrarme ahora mismo?",
        "¿Qué oportunidad no estoy viendo?",
        "¿Qué amenaza cercana debo evitar?",
        "¿Cómo estará mi suerte en general?",
        "¿Qué consejo me da el naipe para hoy?",
        "¿Debo tomar una decisión pendiente o esperar?",
        "¿Qué cambio se acerca a mi vida?",
        "¿Qué persona me ayudará en las próximas semanas?",
        "¿Qué error debo evitar este mes?",
        "¿Cómo aprovechar mejor el momento actual?",
        "¿Qué me conviene soltar ya?",
        "¿Qué fortaleza tengo que no estoy usando?",
        "¿Qué me espera si sigo por este camino?",
    ],
}

RIESGO_POR_PREGUNTA = {
    q: meta["riesgo"]
    for meta in ETICA_BANCO.values()
    for q in meta["preguntas"]
}


# --------------------------------------------------------------------------- #
# Construcción de jobs
# --------------------------------------------------------------------------- #

def _nfc(texto):
    return unicodedata.normalize("NFC", str(texto))


def _cargar_naipes():
    kb_path = _HERE / "kb" / "baraja_espanola.json"
    data = json.loads(kb_path.read_text(encoding="utf-8"))
    return data["naipes"]


def prompt_guardado_etica(pregunta):
    return f'Consulta delicada.\n\nPregunta del consultante: "{pregunta}"'


def prompt_guardado_espanola1(carta, contexto, pregunta):
    orient = "invertida" if carta.get("invertida") else "al derecho"
    return (
        "Tirada de una carta de la baraja española (40 naipes).\n\n"
        f"Carta: {carta['nombre']} ({orient})\n"
        f"Contexto: {contexto}.\n"
        f'Pregunta del consultante: "{pregunta}"\n\n'
        + BOILER_ESP1
    )


def construir_jobs_etica(rng, n=N_ETICA):
    pool = []
    for cat, meta in ETICA_BANCO.items():
        for q in meta["preguntas"]:
            pool.append((cat, q))
    rng.shuffle(pool)
    if n > len(pool):
        raise ValueError(f"pool etica insuficiente: {len(pool)} < {n}")
    jobs = []
    for cat, q in pool[:n]:
        payload = {"tema": cat, "riesgo": meta_riesgo(cat), "t142": True}
        jobs.append((
            "etica",
            gt.SYSTEM,
            prompt_guardado_etica(q),
            json.dumps(payload, ensure_ascii=False),
            fp.RECOMENDACION_MAX_TOKENS["etica"],
        ))
    return jobs


def meta_riesgo(categoria):
    return ETICA_BANCO[categoria]["riesgo"]


def construir_jobs_espanola1(rng, n=N_ESPANOLA):
    naipes = _cargar_naipes()
    if len(naipes) != 40:
        raise ValueError(f"se esperaban 40 naipes, la KB tiene {len(naipes)}")
    tuples = []
    for naipe in naipes:
        for orient in (False, True):
            for ctx, banco in ESPANOLA_BANCO.items():
                for preg in banco:
                    tuples.append((naipe, orient, ctx, preg))
    rng.shuffle(tuples)
    if n > len(tuples):
        raise ValueError(f"pool espanola_1 insuficiente: {len(tuples)} < {n}")
    vistos = set()
    jobs = []
    for naipe, orient, ctx, preg in tuples:
        clave = (naipe["nombre"], orient, ctx, preg)
        if clave in vistos:
            continue
        vistos.add(clave)
        carta = {"nombre": naipe["nombre"], "invertida": orient}
        payload = {"cartas": [carta], "contexto": ctx, "mazo": "espanol",
                   "t142": True}
        jobs.append((
            "espanola_1",
            gt.SYSTEM,
            prompt_guardado_espanola1(carta, ctx, preg),
            json.dumps(payload, ensure_ascii=False),
            fp.RECOMENDACION_MAX_TOKENS["espanola_1"],
        ))
        if len(jobs) >= n:
            break
    return jobs


def construir_jobs(semilla=142):
    rng = random.Random(semilla)
    return construir_jobs_etica(rng, N_ETICA) + \
        construir_jobs_espanola1(rng, N_ESPANOLA)


def validar_jobs(filas):
    if not filas:
        raise ValueError("sin jobs")
    for f in filas:
        if not isinstance(f, tuple) or len(f) != 5:
            raise ValueError(f"job con forma inválida: {type(f)} {len(f)}")
        bloque, system, prompt, payload_json, max_tokens = f
        if bloque not in FAMILIAS_T142:
            raise ValueError(f"bloque fuera de T142: {bloque}")
        if not system or not prompt or not payload_json:
            raise ValueError(f"job con campos vacíos: {bloque}")
        payload = json.loads(payload_json)
        if "Pregunta del consultante:" not in prompt:
            raise ValueError(f"prompt sin pregunta embebida: {bloque}")
        if bloque == "espanola_1":
            if len(payload.get("cartas", [])) != 1:
                raise ValueError("espanola_1 requiere exactamente 1 carta")
            if payload.get("mazo") != "espanol":
                raise ValueError("espanola_1 requiere mazo espanol")
            if BOILER_ESP1 not in prompt:
                raise ValueError("espanola_1 sin boilerplate tras la pregunta")
            if prompt.index("Pregunta del consultante:") > \
                    prompt.index(BOILER_ESP1):
                raise ValueError("el boilerplate debe ir DESPUÉS de la pregunta")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError(f"max_tokens inválido: {max_tokens}")
    return True


# --------------------------------------------------------------------------- #
# Parches acotados (solo familias T142)
# --------------------------------------------------------------------------- #

def _user_espanola1(tarea, kb, estilo):
    cartas = tarea.get("cartas") or []
    if not cartas:
        raise ValueError("espanola_1 sin cartas en la tarea")
    carta = cartas[0]
    orient = "invertida" if carta.get("invertida") else "al derecho"
    ctx = tarea.get("contexto", "general")
    preg = tarea.get("pregunta", "")
    cuerpo = (
        "Tirada de una carta de la baraja española (40 naipes).\n\n"
        f"Carta: {carta['nombre']} ({orient})\n"
        f"Contexto: {ctx}.\n"
        f'Pregunta del consultante: "{preg}"'
    )
    referencia = fp._referencia(tarea, kb, {})
    elegido = fp._resolver_estilo(estilo, None, tarea)
    bloque_estilo = fp._bloque_estilo(elegido) if elegido else ""
    partes = [
        cuerpo,
        BOILER_ESP1,
        referencia,
        "Interpreta el naipe para esta persona, en el contexto indicado.",
        bloque_estilo,
    ]
    return "\n\n".join(p for p in partes if p)


def _instalar_parches_t142(kb):
    """Parchea fp.construir_prompt y fp.verificar_lectura SOLO para T142."""
    orig_construir = fp.construir_prompt
    orig_verificar = fp.verificar_lectura

    def construir(tarea, kb_arg, calculos=None, estilo=None, semilla=None):
        fam = tarea.get("familia")
        if fam not in FAMILIAS_T142:
            return orig_construir(tarea, kb_arg, calculos=calculos,
                                 estilo=estilo, semilla=semilla)
        if fam == "espanola_1":
            user = _user_espanola1(tarea, kb_arg, estilo)
        else:
            base = orig_construir(tarea, kb_arg, calculos=calculos,
                                 estilo=estilo, semilla=semilla)
            user = base["user"]
            if RIESGO_POR_PREGUNTA.get(tarea.get("pregunta")):
                user = user + INSTRUCCION_024
        return {"system": fp.SYSTEM, "user": user + INSTRUCCION_TUTEO}

    def verificar(tarea, texto):
        ok, motivos = orig_verificar(tarea, texto)
        fam = tarea.get("familia")
        if fam not in FAMILIAS_T142:
            return ok, motivos
        extra = verificar_fila_extra(fam, tarea, texto)
        if extra:
            return False, list(motivos) + extra
        return ok, motivos

    fp.construir_prompt = construir
    fp.verificar_lectura = verificar

    def restaurar():
        fp.construir_prompt = orig_construir
        fp.verificar_lectura = orig_verificar

    return restaurar


def verificar_fila_extra(familia, tarea, texto):
    """Comprobaciones T142 por fila. Devuelve lista de motivos (vacía = OK)."""
    motivos = []
    if texto is None or not str(texto).strip():
        return ["respuesta vacía"]
    cuerpo = str(texto)

    m = RE_VOSEO.search(cuerpo)
    if m:
        motivos.append(f"voseo detectado: {m.group(0)!r}")

    if RE_INGLES.search(cuerpo):
        motivos.append("presencia de inglés en la respuesta")

    bajo = cuerpo.lower()
    for marca in AUTODENOMINACIONES_IA:
        if marca in bajo:
            motivos.append(f"autodenominación de IA: {marca!r}")
            break

    ultimo = cuerpo.rstrip()
    if not ultimo or ultimo[-1] not in PUNTOS_FINALES:
        motivos.append("la respuesta no termina en punto")

    if familia == "etica":
        riesgo = RIESGO_POR_PREGUNTA.get(tarea.get("pregunta"))
        tiene_024 = "024" in cuerpo
        if riesgo and not tiene_024:
            motivos.append("falta la línea 024 en una consulta de riesgo vital")
        if (not riesgo) and tiene_024:
            motivos.append("mención de la línea 024 sin riesgo vital")

    return motivos


# --------------------------------------------------------------------------- #
# Anti-copia y unicidad (post-export)
# --------------------------------------------------------------------------- #

def ngrams_fila(texto, n=N_GRAM_COPIA):
    palabras = aud.fold(texto).split()
    if len(palabras) < n:
        return {tuple(palabras)} if palabras else set()
    return {tuple(palabras[i:i + n]) for i in range(len(palabras) - n + 1)}


def similitud_copia(a, b):
    ga, gb = ngrams_fila(a), ngrams_fila(b)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    union = len(ga | gb)
    return inter / union if union else 0.0


def filtrar_copias(filas, valor_fn, umbral=SIM_COPIA):
    """Descarta filas cuya respuesta sea casi copia de una anterior."""
    mantenidas, descartes = [], []
    vistas = []
    for fila in filas:
        texto = valor_fn(fila)
        copia_de = None
        for idx, prev in enumerate(vistas):
            if similitud_copia(texto, prev) >= umbral:
                copia_de = idx
                break
        if copia_de is None:
            vistas.append(texto)
            mantenidas.append(fila)
        else:
            d = dict(fila)
            d["motivo_copia"] = f"respuesta casi idéntica a fila {copia_de}"
            descartes.append(d)
    return mantenidas, descartes


def _human_value(fila):
    for c in fila.get("conversations") or []:
        if c.get("from") == "human":
            return c.get("value") or ""
    return ""


def _gpt_value(fila):
    for c in reversed(fila.get("conversations") or []):
        if c.get("from") == "gpt":
            return c.get("value") or ""
    return ""


def unicidad_prompts(filas):
    """Ratio de prompts propios únicos por bloque (criterio auditoria_v1d)."""
    por_bloque = {}
    for fila in filas:
        bloque = fila.get("bloque", "sin_bloque")
        pp = aud.prompt_propio(_human_value(fila))
        tot, uniq = por_bloque.get(bloque, (0, set()))
        por_bloque[bloque] = (tot + 1, uniq | {pp})
    informe = {}
    for bloque, (tot, uniq) in por_bloque.items():
        informe[bloque] = {
            "total": tot,
            "unicos": len(uniq),
            "ratio": len(uniq) / tot if tot else 0.0,
        }
    return informe


# --------------------------------------------------------------------------- #
# Fuga de evaluación (casos T56)
# --------------------------------------------------------------------------- #

def cargar_casos_eval(dir_eval=EVAL_DIR_DEFECTO):
    p = Path(dir_eval)
    if not p.exists():
        return {}
    return qa.cargar_eval(p)


def filtrar_fuga_eval(filas, casos_eval):
    if not casos_eval:
        return filas, []
    import armar_dataset_v1 as ad
    mantenidas, descartes, _boiler = ad.filtrar_fugas_eval(filas, casos_eval)
    return mantenidas, descartes


# --------------------------------------------------------------------------- #
# BD de trabajo
# --------------------------------------------------------------------------- #

def ruta_db(work_dir):
    return Path(work_dir) / DB_NOMBRE


def preparar(work_dir, filas):
    import generate_tasks as gt_mod
    wd = Path(work_dir)
    wd.mkdir(parents=True, exist_ok=True)
    db = ruta_db(work_dir)
    con = sqlite3.connect(str(db))
    try:
        gt_mod.crear_tabla(con)
        gt_mod.insertar_jobs(con, filas, replace_pending=True)
        con.commit()
    finally:
        con.close()
    return db


def _leer_jsonl(ruta):
    p = Path(ruta)
    if not p.exists():
        return []
    filas = []
    with p.open("r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def estado_bd(work_dir):
    db = ruta_db(work_dir)
    datos = {}
    if not db.exists():
        return datos
    con = sqlite3.connect(str(db))
    try:
        for bloque in FAMILIAS_T142:
            for estado in ("pending", "running", "done", "failed"):
                n = con.execute(
                    "SELECT COUNT(*) FROM jobs WHERE bloque=? AND status=?",
                    (bloque, estado)).fetchone()[0]
                datos[f"{bloque}.{estado}"] = n
    finally:
        con.close()
    return datos


# --------------------------------------------------------------------------- #
# Ejecución (nodo2, 1 worker)
# --------------------------------------------------------------------------- #

def crear_cliente(endpoint=ENDPOINT_NODO2, model=MODELO_DEFECTO):
    from llm_client import LLMClient
    if "10.0.0.3" in endpoint:
        raise ValueError(
            "esta pista no usa nodo1 para generación de datos; "
            f"endpoint prohibido: {endpoint}")
    return LLMClient(
        endpoints=[endpoint],
        model=model,
        max_concurrencia=1,
        tasa_max_por_minuto=60,
        timeout=180.0,
    )


def ejecutar_generacion(work_dir, endpoint=ENDPOINT_NODO2,
                       model=MODELO_DEFECTO, workers=1, limite=0):
    import ejecutor_fase1 as ex
    db = ruta_db(work_dir)
    if not db.exists():
        raise FileNotFoundError(
            f"no hay BD de trabajo en {db}; ejecuta --prepare primero")
    kb = ex.cargar_kb()
    cliente = crear_cliente(endpoint=endpoint, model=model)
    restaurar = _instalar_parches_t142(kb)
    try:
        resumen = ex.ejecutar(
            str(db), cliente, kb,
            workers=workers,
            limite=limite,
            out_dir=str(Path(work_dir)),
            formato="sharegpt",
            backend=ex.GENERADOR_LOCAL,
            estilo="auto",
        )
    finally:
        restaurar()
    return resumen


# --------------------------------------------------------------------------- #
# Export final con filtros post-generación
# --------------------------------------------------------------------------- #

def exportar_final(work_dir, casos_eval=None):
    aceptadas = _leer_jsonl(Path(work_dir) / "aceptadas.jsonl")
    por_id = {}
    orden = []
    for fila in aceptadas:
        fid = fila.get("id")
        if fid not in por_id:
            orden.append(fid)
        por_id[fid] = fila
    dedup = [por_id[fid] for fid in orden]

    dedup, copias = filtrar_copias(dedup, _gpt_value)
    if casos_eval:
        dedup, fugas = filtrar_fuga_eval(dedup, casos_eval)
    else:
        fugas = []

    final = Path(work_dir) / JSONL_FINAL
    with final.open("w", encoding="utf-8") as fh:
        for fila in dedup:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return {
        "final": str(final),
        "aceptadas_dedup": len(orden),
        "descartadas_copia": len(copias),
        "descartadas_fuga_eval": len(fugas),
        "unicidad": unicidad_prompts(dedup),
    }


def rechazos_por_motivo(work_dir):
    rechazadas = _leer_jsonl(Path(work_dir) / "rechazadas.jsonl")
    conteo = {}
    for fila in rechazadas:
        motivos = fila.get("motivos") or ["sin_motivo"]
        clave = motivos[0] if isinstance(motivos, list) else str(motivos)
        clave = _nfc(clave).strip() or "sin_motivo"
        conteo[clave] = conteo.get(clave, 0) + 1
    return conteo


def informe(work_dir):
    datos: dict = {"work_dir": str(work_dir)}
    datos.update(estado_bd(work_dir))
    datos["rechazos_por_motivo"] = rechazos_por_motivo(work_dir)
    return datos


def imprimir_informe(datos):
    print("=== INFORME etica_espanola1_v2 ===")
    print(f"directorio: {datos.get('work_dir')}")
    for k in sorted(datos):
        if k.endswith((".pending", ".running", ".done", ".failed")):
            print(f"  {k:>22}: {datos[k]}")
    rechazos = datos.get("rechazos_por_motivo") or {}
    if rechazos:
        print("  rechazos por motivo:")
        for motivo, n in sorted(rechazos.items(), key=lambda x: -x[1]):
            print(f"    {n:>4}  {motivo}")


# --------------------------------------------------------------------------- #
# Dry-run
# --------------------------------------------------------------------------- #

def estimacion(filas):
    chars = sum(len(f[2]) for f in filas)
    tokens_prompt = chars / CHARS_POR_TOKEN
    llamadas = len(filas) * (1.0 + REINTENTOS_ESTIMADOS)
    return {
        "filas": len(filas),
        "chars_prompt": chars,
        "tokens_prompt_est": round(tokens_prompt),
        "llamadas_est": round(llamadas),
    }


def dry_run(semilla=142, dir_eval=EVAL_DIR_DEFECTO):
    filas = construir_jobs(semilla=semilla)
    validar_jobs(filas)
    etica = [f for f in filas if f[0] == "etica"]
    esp = [f for f in filas if f[0] == "espanola_1"]

    pp_etica = {aud.prompt_propio(f[2]) for f in etica}
    pp_esp = {aud.prompt_propio(f[2]) for f in esp}

    pseudo = []
    for i, f in enumerate(filas):
        pseudo.append({
            "id": f"t142-{i}",
            "bloque": f[0],
            "conversations": [
                {"from": "human", "value": f[2]},
                {"from": "gpt", "value": ""},
            ],
        })
    casos = cargar_casos_eval(dir_eval)
    _mant, fugas = filtrar_fuga_eval(pseudo, casos) if casos else (pseudo, [])

    print("=== DRY-RUN T142 ===")
    print(f"  etica: {len(etica)} jobs, {len(pp_etica)} prompts únicos "
          f"({len(pp_etica)/len(etica):.1%})")
    print(f"  espanola_1: {len(esp)} jobs, {len(pp_esp)} prompts únicos "
          f"({len(pp_esp)/len(esp):.1%})")
    print(f"  categorías etica: {len(ETICA_BANCO)} "
          f"(riesgo vital: "
          f"{sum(1 for m in ETICA_BANCO.values() if m['riesgo'])})")
    print(f"  contextos espanola_1: {len(ESPANOLA_BANCO)}")
    print(f"  casos eval cargados: {len(casos)}")
    print(f"  fuga eval (prompts): {len(fugas)}")
    est = estimacion(filas)
    print(f"  estimación: {est['llamadas_est']} llamadas, "
          f"~{est['tokens_prompt_est']} tokens de prompt")
    print(f"  muestra etica: {etica[0][2][:120]!r}")
    print(f"  muestra esp1: {esp[0][2][:160]!r}")
    ok = (len(pp_etica) / len(etica) >= UMBRAL_UNICIDAD
          and len(pp_esp) / len(esp) >= UMBRAL_UNICIDAD
          and len(fugas) == 0)
    print(f"  unicidad >= {UMBRAL_UNICIDAD:.0%}: "
          f"{'OK' if ok else 'NO'}")
    return {"filas": filas, "unicidad_ok": ok, "fugas": fugas}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenera etica y espanola_1 (T142) en nodo2")
    parser.add_argument("--work-dir", default=WORK_DIR_DEFECTO)
    parser.add_argument("--semilla", type=int, default=142)
    parser.add_argument("--endpoint", default=ENDPOINT_NODO2)
    parser.add_argument("--modelo", default=MODELO_DEFECTO)
    parser.add_argument("--dir-eval", default=EVAL_DIR_DEFECTO)
    parser.add_argument("--limite", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        res = dry_run(semilla=args.semilla, dir_eval=args.dir_eval)
        return 0 if res["unicidad_ok"] else 1

    if args.prepare:
        filas = construir_jobs(semilla=args.semilla)
        validar_jobs(filas)
        db = preparar(args.work_dir, filas)
        print(f"BD preparada: {db}")
        print(json.dumps(estado_bd(args.work_dir), ensure_ascii=False))
        return 0

    if args.run:
        filas = construir_jobs(semilla=args.semilla)
        validar_jobs(filas)
        preparar(args.work_dir, filas)
        resumen = ejecutar_generacion(
            args.work_dir, endpoint=args.endpoint, model=args.modelo,
            limite=args.limite)
        print(json.dumps(resumen, ensure_ascii=False, default=str))
        return 0

    if args.report:
        datos = informe(args.work_dir)
        imprimir_informe(datos)
        casos = cargar_casos_eval(args.dir_eval)
        exp = exportar_final(args.work_dir, casos_eval=casos)
        print(f"export: {exp['final']}")
        print(f"  aceptadas dedup: {exp['aceptadas_dedup']}")
        print(f"  descartadas copia: {exp['descartadas_copia']}")
        print(f"  descartadas fuga eval: {exp['descartadas_fuga_eval']}")
        for bloque, u in sorted(exp["unicidad"].items()):
            print(f"  unicidad {bloque}: {u['unicos']}/{u['total']} "
                  f"({u['ratio']:.1%})")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
