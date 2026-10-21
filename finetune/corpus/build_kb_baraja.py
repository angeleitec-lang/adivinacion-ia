#!/usr/bin/env python3
"""Genera kb/baraja_espanola.json (40 naipes) con la tradición clásica de la
cartomancia española.

PROVISIONAL: los significados resumen la tradición transmitida en manuales
clásicos (Oros=materia/dinero, Copas=emoción/amor, Espadas=prueba/conflicto,
Bastos=acción/trabajo) y NO proceden aún del consenso de fuentes de fase 0.
Deben contrastarse con `afirmaciones_full` (8.604 afirmaciones de naipe) y las
rejillas de fuentes web de baraja (`finetune/knowledge/fuentes_web_es_baraja.md`)
antes de usar esta KB para el dataset final. Cada entrada lleva
`estado: "provisional"` para que el pipeline pueda filtrarla.

Uso: /Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/build_kb_baraja.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "kb" / "baraja_espanola.json"

PALOS = {
    "Oros": {
        "tema": "lo material: dinero, trabajo remunerado, recursos, salud",
        "elemento": "tierra",
    },
    "Copas": {
        "tema": "lo emocional: amor, familia, amistad, sentimientos",
        "elemento": "agua",
    },
    "Espadas": {
        "tema": "la prueba: conflicto, enfermedad, pérdida, pensamiento",
        "elemento": "aire",
    },
    "Bastos": {
        "tema": "la acción: trabajo, creatividad, energía, proyectos",
        "elemento": "fuego",
    },
}

# nombre: (significado, invertida, [palabras_clave], amor, trabajo)
NAIPES = {
    "As de Oros": (
        "Comienzo material sólido: oportunidad económica, estabilidad que se abre paso.",
        "La oportunidad llega tardía o se dispersa en gastos sin rumbo.",
        ["prosperidad", "inicio", "estabilidad"],
        "Un vínculo que ofrece seguridad y proyectos en común.",
        "Puerta de trabajo o ingresos nuevos que conviene aprovechar.",
    ),
    "Dos de Oros": (
        "Equilibrio entre dos asuntos materiales: cambio de manos, intercambio justo.",
        "Desequilibrio: cuentas que no cuadran o promesas que se esquivan.",
        ["equilibrio", "cambio", "intercambio"],
        "Ida y vuelta en la relación; hace falta conversar para cuadrar.",
        "Alternar tareas o dos fuentes de ingreso con agilidad.",
    ),
    "Tres de Oros": (
        "Trabajo bien hecho que rinde sus primeros frutos visibles.",
        "Frutos que se retrasan por descuidos o falta de coordinación.",
        ["obra", "equipo", "reconocimiento"],
        "Relación que se construye a base de esfuerzo compartido.",
        "Colaboración profesional con resultados concretos.",
    ),
    "Cuatro de Oros": (
        "Lo ganado se protege: prudencia con el dinero y con el propio terreno.",
        "Avaricia o miedo a perder que deja pasar oportunidades.",
        ["prudencia", "reserva", "seguridad"],
        "Apego y celos: cuesta abrirse de más.",
        "Mantener lo conquistado antes de expandirse.",
    ),
    "Cinco de Oros": (
        "Estrechez temporal: carencia que se puede sobrellevar con apoyo.",
        "Se toca fondo y aparece la ayuda que no se quería ver.",
        ["pérdida", "solidaridad", "recurso"],
        "Sentirse fuera del vínculo; conviene pedir claro lo que se necesita.",
        "Aprieto económico pasajero; no aísles a nadie por ello.",
    ),
    "Seis de Oros": (
        "Dar y recibir en justa medida: ayuda, don, beneficio compartido.",
        "Cuentas desiguales: dar de más o cobrar de menos.",
        ["generosidad", "equidad", "gratitud"],
        "Un reparto afectivo equilibrado cura viejas deudas.",
        "Mejoras materiales gracias a quien tiende la mano.",
    ),
    "Siete de Oros": (
        "Paciencia activa: esperar la cosecha sin dejar de cuidar el campo.",
        "Cosecha anticipada o rendirse antes de tiempo.",
        ["paciencia", "inversión", "espera"],
        "Dejar madurar lo sembrado sin agobiar.",
        "Proyecto a largo plazo; hoy toca regar, no recoger.",
    ),
    "Sota de Oros": (
        "Mensajero práctico y estudioso: noticia concreta sobre dinero o trabajo.",
        "Juventud insegura o promesas materiales sin fundamento.",
        ["mensaje", "estudio", "oportunidad"],
        "Alguien leal y discreto que se gana tu confianza despacio.",
        "Aprendizaje, curso o propuesta laboral sensata.",
    ),
    "Caballo de Oros": (
        "Noticia o cambio material que llega seguro, sin prisa pero sin pausa.",
        "Estancamiento: lo esperado se retrasa por exceso de cautela.",
        ["llegada", "estabilidad", "noticia"],
        "Pretendiente constante y de hecho, no de palabra.",
        "Movimientos firmes en el terreno profesional.",
    ),
    "Rey de Oros": (
        "Adulto responsable y próspero: consejo sensato, respaldo material.",
        "Rigidez, control o poder usado para imponer.",
        ["protección", "experiencia", "administración"],
        "Pareja madura que da seguridad más que fuegos artificiales.",
        "Jefe, cliente o asesor que maneja bien los recursos.",
    ),
    "As de Copas": (
        "El corazón se abre: amor naciente, emoción nueva, sanación afectiva.",
        "Sentimiento que no encuentra cauce o se ofrece tarde.",
        ["amor", "emoción", "comienzo"],
        "Chispa verdadera; cuídala sin idealizarla.",
        "Ambiente agradable que da ganas de quedarse.",
    ),
    "Dos de Copas": (
        "Unión y acuerdo: dos que se eligen con claridad.",
        "Desavenencia pasajera o promesa incumplida por una parte.",
        ["vínculo", "acuerdo", "encuentro"],
        "La carta del pareja: entendimiento y atracción mutua.",
        "Sociadad afectuosa con la que se puede contar.",
    ),
    "Tres de Copas": (
        "Celebración compartida: amistad, festejo, logro que se brinda juntos.",
        "Alegría dispersa en excesos o habladurías.",
        ["celebración", "amistad", "gratitud"],
        "Relación ligera y feliz; cuidado con los triángulos.",
        "Éxito de equipo que merece celebrarse.",
    ),
    "Cuatro de Copas": (
        "Cansancio afectivo: lo ofrecido no se ve por estar mirando otra cosa.",
        "Se recupera el interés; la propuesta que se desdeñaba vuelve a tiempo.",
        ["apatía", "oferta", "introspección"],
        "Dar por hecho el cariño de quien está al lado.",
        "Desmotivación: revisar qué falta de verdad.",
    ),
    "Cinco de Copas": (
        "Duelo: pérdida sentida; quedan copas en pie todavía.",
        "El duelo empieza a cerrarse: se vuelve a mirar adelante.",
        ["pérdida", "duelo", "consuelo"],
        "Echar de menos lo que fue y no ver lo que queda.",
        "Decepción en un proyecto; no todo se perdió.",
    ),
    "Seis de Copas": (
        "Recuerdo y reencuentro: lo de antes vuelve con dulzura.",
        "Anclarse en el pasado e impedir el presente.",
        ["nostalgia", "regalo", "reencuentro"],
        "Viejo amor o amistad que reaparece.",
        "Volver a algo conocido con cariño.",
    ),
    "Siete de Copas": (
        "Ilusiones múltiples: fantasía que promete más de lo que sostiene.",
        "Se aclara la niebla y se elige una opción real.",
        ["fantasía", "opciones", "ilusión"],
        "Idealización: distinguir deseo de realidad.",
        "Muchas ideas y poca ejecución; concretar una.",
    ),
    "Ocho de Copas": (
        "Retirada consciente: dejar atrás lo que ya no llena.",
        "Volver sobre lo propio cuando ya estaba cerrado.",
        ["retirada", "búsqueda", "valentía"],
        "Alejarse duele pero es necesario.",
        "Cerrar un ciclo para buscar algo más coherente.",
    ),
    "Nueve de Copas": (
        "Deseo cumplido: satisfacción emocional y buena estrella.",
        "Contentarse de menos o prometer lo que no se puede dar.",
        ["deseo", "satisfacción", "abundancia"],
        "Plenitud afectiva; disfrutar sin volvverse caprichoso.",
        "Lo que se quería se consigue; agradecerlo.",
    ),
    "Diez de Copas": (
        "Felicidad doméstica: familia, casa y afecto en armonía.",
        "Riñas en el círculo íntimo que deslucen la convivencia.",
        ["hogar", "familia", "plenitud"],
        "Compromiso estable y afecto compartido.",
        "Buen clima de equipo y conciliación.",
    ),
    "Sota de Copas": (
        "Mensajero del afecto: atención sincera, invitación, confidencia.",
        "Inmadurez emocional o halago con intención.",
        ["atención", "mensaje", "sensibilidad"],
        "Declaración tímida pero verdadera.",
        "Compañero joven o aprendiz sensible al ambiente.",
    ),
    "Caballo de Copas": (
        "Llega una propuesta emocional: noticia del corazón, gesto romántico.",
        "Palabras bonitas que no se sostienen.",
        ["propuesta", "romance", "llegada"],
        "El pretendiente encantador; mirar los hechos.",
        "Oportunidad que ilusiona; verificar el detalle.",
    ),
    "Rey de Copas": (
        "Adulto de buen corazón: comprensión, tacto, madurez afectiva.",
        "Manipulación sentimental o dependencia emocional.",
        ["comprensión", "tacto", "madurez"],
        "Pareja empática que escucha de verdad.",
        "Liderazgo humano; mediador eficaz.",
    ),
    "As de Espadas": (
        "Verdad que corta: claridad mental, decisión firme, comienzo difícil pero limpio.",
        "Confusión: la espada no encuentra su filo.",
        ["claridad", "verdad", "decisión"],
        "Hablar claro evita más daño que el silencio.",
        "Un corte necesario (contrato, rumbo) que libera.",
    ),
    "Dos de Espadas": (
        "Encrucijada: elegir con la información que hay, no con la que falta.",
        "La decisión tomada disipa la tensión.",
        ["duda", "equilibrio", "elección"],
        "Impasse afectivo; no dejar que otros elijan por ti.",
        "Dos opciones que obligan a priorizar.",
    ),
    "Tres de Espadas": (
        "Dolor claro: traición, despedida o palabra que hiere.",
        "La herida empieza a cicatrizar; se agradece la verdad.",
        ["herida", "duelo", "verdad"],
        "Ruptura o decepción que hay que llorar a solas y luego soltar.",
        "Crítica dura; separar el fondo de la forma.",
    ),
    "Cuatro de Espadas": (
        "Tregua necesaria: reposo tras el esfuerzo, pausa que restaura.",
        "Descanso que no llega o parón que se vuelve aislamiento.",
        ["reposo", "recuperación", "silencio"],
        "Distancia sana para no decir lo que no se piensa.",
        "Baja activa: recuperarse antes de volver.",
    ),
    "Cinco de Espadas": (
        "Conflicto: victoria que deja sabor amargo; conviene elegir la paz.",
        "Se deponen las armas: reconciliación o perdón.",
        ["disputa", "orgullo", "reconciliación"],
        "Ganar la discusión puede costar la relación.",
        "Rivalidad y zancadillas; no escalar.",
    ),
    "Seis de Espadas": (
        "Travesía: alejarse de aguas revueltas hacia algo más sereno.",
        "Volver a la orilla dejada cuando el viaje era lo correcto.",
        ["cambio", "transición", "viaje"],
        "Alejarse juntos o separarse con cariño.",
        "Cambio de aires, de equipo o de ciudad.",
    ),
    "Siete de Espadas": (
        "Astucia: algo se oculta o se negocia a medias; revisar el detalle.",
        "La trampa se descubre; lo recuperado vuelve.",
        ["engaño", "estratega", "cautela"],
        "Medias verdades: preguntar sin acusar.",
        "Pacto con letra pequeña; leer antes de firmar.",
    ),
    "Ocho de Espadas": (
        "Atadura mental: el miedo ata más que la situación real.",
        "Las ataduras caen: se recupera la movilidad.",
        ["limitación", "miedo", "salida"],
        "Sentirse atrapado en un vínculo; la salida está en hablar.",
        "Bloqueo autoimpuesto: pedir ayuda lo deshace.",
    ),
    "Nueve de Espadas": (
        "Angustia nocturna: preocupación que crece sin dormir; pedir apoyo.",
        "La peor pesadilla se disipa; alivio tras la tormenta.",
        ["angustia", "insomnio", "apoyo"],
        "Rumiar heridas viejas en soledad.",
        "Estrés alto; priorizar y delegar.",
    ),
    "Diez de Espadas": (
        "Final doloroso pero necesario: tocar fondo permite el relevo.",
        "Se levanta lo que parecía enterrado.",
        ["cierre", "fondo", "renovación"],
        "Ruptura definitiva que abre aire.",
        "Proyecto que termina; no reanimarlo a la fuerza.",
    ),
    "Sota de Espadas": (
        "Mente alerta: noticia dura o joven observador que no se deja engañar.",
        "Desconfianza que sabotea; oír sin acusar.",
        ["vigilancia", "noticia", "astucia"],
        "Vigilancia y celos; la duda no es prueba.",
        "Contrato o persona que exige leer la letra pequeña.",
    ),
    "Caballo de Espadas": (
        "Impulso veloz: llegada repentina, franqueza que atropella.",
        "La prisa se frena; hay que pensar antes de cargar.",
        ["prontitud", "franco", "embate"],
        "Declaración directa, sin rodeos.",
        "Cambios rápidos y decisiones tajantes.",
    ),
    "Rey de Espadas": (
        "Autoridad serena: criterio, ley y distancia para juzgar bien.",
        "Dureza sin compasión: autoridad que hiere.",
        ["justicia", "criterio", "distancia"],
        "Alguien que pone límites sanos.",
        "Asesor, juez o jefe de palabra firme.",
    ),
    "As de Bastos": (
        "Chispa de arranque: energía creativa, inspiración, iniciativa.",
        "La chispa se dispersa: comenzar sin rumbo.",
        ["impulso", "creatividad", "iniciativa"],
        "Atracción nueva; encender sin quemar.",
        "Proyecto apasionante que pide el primer paso.",
    ),
    "Dos de Bastos": (
        "Plan de futuro: elegir rumbo con el mundo delante.",
        "Dudar del mapa o aferrarse a un plan que ya no sirve.",
        ["plan", "decisión", "visión"],
        "Decidir hacia dónde crecer juntos.",
        "Dos frentes abiertos; repartir bien la energía.",
    ),
    "Tres de Bastos": (
        "Expansión: lo sembrado sale bien y se abren caminos.",
        "El barco no llega: expectativa sobreestimada.",
        ["expansión", "logro", "horizonte"],
        "Relación que mira lejos sin perder el puerto.",
        "Primeros frutos de un proyecto que crece.",
    ),
    "Cuatro de Bastos": (
        "Base firme: hogar, comunidad y celebración de lo conseguido.",
        "La celebración se pospone o el refugio se siente rígido.",
        ["refugio", "armonía", "hito"],
        "Convivencia alegre; presentar a la familia.",
        "Equipo consolidado; momento para agasajar.",
    ),
    "Cinco de Bastos": (
        "Rivalidad sana o no: choques de energía que enseñan a sostenerse.",
        "Se sueltan las armas y aparece la colaboración.",
        ["conflicto", "competencia", "esfuerzo"],
        "Discutir por tonterías; elegir la batalla.",
        "Equipo con roces: ordenar roles.",
    ),
    "Seis de Bastos": (
        "Reconocimiento: el esfuerzo se ve y se aplaude.",
        "Triunfo que se desinfla por vanidad o descuido.",
        ["victoria", "prestigio", "avance"],
        "Ser elegido y celebrarlo juntos.",
        "Promoción, premio o logro público.",
    ),
    "Siete de Bastos": (
        "Defender la posición: resistencia activa ante quien cuestiona.",
        "Dejar la defensa cuando ya estaba ganada.",
        ["defensa", "perseverancia", "terreno"],
        "Poner límites sin agresividad.",
        "Sostener lo logrado contra competidores.",
    ),
    "Ocho de Bastos": (
        "Velocidad: muchos sucesos a la vez, noticias que llueven.",
        "Dispersión: demasiadas flechas y ningún blanco.",
        ["rapidez", "abundancia", "movimiento"],
        "Intensidad y prisas; hablar claro.",
        "Racha de actividad; organizarse.",
    ),
    "Siete de Bastos": (
        "Defender la posición: resistencia activa ante quien cuestiona.",
        "Dejar la defensa cuando ya estaba ganada.",
        ["defensa", "perseverancia", "terreno"],
        "Poner límites sin agresividad.",
        "Sostener lo logrado contra competidores.",
    ),
    "Nueve de Bastos": (
        "Experiencia que ya superó la prueba: fuerza con cicatrices y recelo prudente.",
        "Bajar la guardia demasiado pronto o no pedir refuerzos.",
        ["resiliencia", "vigilancia", "maestría"],
        "Desconfianza que protege de más; abrir una rendija.",
        "Saber hacer probado; cuidar la salud.",
    ),
    "Diez de Bastos": (
        "Carga pesada: demasiadas responsabilidades sobre una sola espalda.",
        "Soltar lastre: delegar libera y termina el ciclo.",
        ["carga", "esfuerzo", "delegar"],
        "Aguantar por costumbre; repartir el peso.",
        "Sobrecarga: priorizar o decir que no.",
    ),
    "Sota de Bastos": (
        "Mensajero entusiasta: noticia, invitación o aprendizaje ilusionante.",
        "Entusiasmo sin método: quedarse en el amago.",
        ["entusiasmo", "mensaje", "aprendiz"],
        "Alguien simpático que trae aire nuevo.",
        "Curso, idea o propuesta que ilusiona.",
    ),
    "Caballo de Bastos": (
        "Aventura en marcha: viaje, impulso emprendedor, energía que llega.",
        "Impulsividad: arrancar sin frenos ni mapa.",
        ["viaje", "ímpetu", "empresa"],
        "Pretendiente apasionado e inquieto.",
        "Proyecto viajero o cambio de aires laboral.",
    ),
    "Rey de Bastos": (
        "Emprendedor maduro: liderazgo creativo, visión y hechos.",
        "Autoritarismo o empresas que desbordan a su dueño.",
        ["liderazgo", "visión", "emprendimiento"],
        "Pareja segura, cálida y con iniciativa.",
        "Mentor o jefe con ideas y mano firme.",
    ),
}


SINONIMOS = {
    "Sota": ["paje", "jota"],
    "Caballo": ["caballero"],
}


def construir():
    naipes = []
    for palo, info in PALOS.items():
        rangos = ["As", "Dos", "Tres", "Cuatro", "Cinco", "Seis", "Siete",
                  "Sota", "Caballo", "Rey"]
        for numero, rango in enumerate(rangos, start=1):
            nombre = f"{rango} de {palo}"
            significado, invertida, claves, amor, trabajo = NAIPES[nombre]
            sinonimos = []
            if rango in SINONIMOS:
                for sin in SINONIMOS[rango]:
                    sinonimos.append(f"{sin} de {palo}")
            sinonimos.append(f"{numero} de {palo}" if rango != "As" else "uno de " + palo)
            naipes.append({
                "id": f"naipe-{palo.lower()}-{numero:02d}",
                "nombre": nombre,
                "palo": palo,
                "rango": rango,
                "numero": numero,
                "elemento": info["elemento"],
                "tema": info["tema"],
                "palabras_clave": claves,
                "significado": significado,
                "invertida": invertida,
                "contextos": {"amor": amor, "trabajo": trabajo},
                "estado": "provisional",
            })
    return {
        "aviso": (
            "Significados provisionales de la tradición clásica de cartomancia española, "
            "escritos sin consenso de fuentes; validar contra las afirmaciones de fase 0 "
            "(naipe-*) antes del dataset final."
        ),
        "naipes": naipes,
    }


def main():
    data = construir()
    assert len(data["naipes"]) == 40, len(data["naipes"])
    nombres = {n["nombre"] for n in data["naipes"]}
    assert len(nombres) == 40, len(nombres)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {OUT}: {len(data['naipes'])} naipes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
