# Calidad de las lecturas reales de Mercury

Auditoría de las lecturas que ya han pasado el verificador de fase 1. El
objetivo no es excluir datos, sino medir los defectos de fondo que el
verificador actual no mira: fórmulas repetidas, incumplimiento del esquema,
muletillas, listas donde se pide prosa, género inventado, contradicciones
astrológicas y preguntas que el prompt no puede responder con los datos que
trae.

Fecha de la auditoría: 21 de octubre de 2026.

## 1. Alcance y método

- Fuente: `/Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl`, en
  producción mientras se hizo el trabajo.
- Copia congelada de solo lectura:
  `/Users/angelgonzalez/fase0/calidad_lecturas/aceptadas_snapshot.jsonl`.
- SHA256 de la copia:
  `feac15787dd4833df7f459e049ee836923dfb166898f4d90a939c959270978be`.
- 6.557 lecturas, 8 bloques. No hay `sinastria`, `multiturno`, `etica` ni
  `espanola_1/3/5/7` en las aceptadas; las comprobaciones para esas familias
  quedan preparadas pero no se han podido medir.
- Muestra estratificada reproducible: 12 lecturas por bloque, 96 en total,
  semilla `20261021`. Se leyeron completas para contrastar lo que detectan
  las comprobaciones automáticas.
- El análisis es de solo lectura: no modifica el fichero de entrada, no
  escribe en `fase1_mercury/`, no usa red ni claves y no reentrena nada.
- Herramienta: `finetune/corpus/calidad_lecturas.py` (solo biblioteca
  estándar). Tests: `finetune/corpus/tests/test_calidad_lecturas.py`.

Reproducción:

```sh
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  finetune/corpus/calidad_lecturas.py \
  --in /Users/angelgonzalez/fase0/calidad_lecturas/aceptadas_snapshot.jsonl \
  --out-dir /Users/angelgonzalez/fase0/calidad_lecturas/informe \
  --muestra 12 --semilla 20261021
```

Genera `informe.json`, `informe.md` y `muestra_12.jsonl` en el directorio de
salida. La ejecución completa tarda unos 38 segundos.

## 2. Volumen y longitudes

| Bloque | N | Mín. | p10 | Mediana | p90 | Máx. |
|---|---:|---:|---:|---:|---:|---:|
| astro_natal | 1434 | 3875 | 5976 | 8298 | 10948 | 12804 |
| cruz_celta | 500 | 2631 | 3183 | 3674 | 4928 | 10343 |
| lectura_completa | 687 | 1855 | 2424 | 2705 | 3108 | 4464 |
| numerologia | 399 | 2389 | 3350 | 4450 | 5808 | 7193 |
| tarot_1 | 939 | 1132 | 1700 | 2348 | 3152 | 4333 |
| tarot_2 | 399 | 1746 | 2455 | 3154 | 3937 | 5700 |
| tarot_3 | 1399 | 2155 | 3146 | 3870 | 4741 | 7076 |
| tarot_pregunta | 800 | 988 | 1465 | 1994 | 2760 | 4099 |

Longitudes en caracteres del texto generado. `lectura_completa` es corta
para la cantidad de técnicas que debe cubrir (mediana de 2.705 caracteres
para carta natal, tirada y numerología), mientras que `astro_natal` tiene
una mediana de 8.298 y una cola de hasta 12.804.

## 3. Resultado global

| Código | Lecturas | % del corpus |
|---|---:|---:|
| `frase_plantilla` | 3689 | 56,3 % |
| `apertura_formula` | 2765 | 42,2 % |
| `lista_en_prosa` | 2452 | 37,4 % |
| `cierre_repetido` | 2449 | 37,3 % |
| `apertura_repetida` | 2355 | 35,9 % |
| `muletilla` | 2302 | 35,1 % |
| `placeholder_prompt` | 2121 | 32,3 % |
| `cierre_formula` | 1546 | 23,6 % |
| `esquema_incumplido` | 1056 | 16,1 % |
| `pregunta_sin_datos` | 133 | 2,0 % |
| `genero_asumido` | 87 | 1,3 % |
| `longitud_atipica` | 14 | 0,2 % |
| `astro_signo_contradicho` | 11 | 0,2 % |
| `genero_inconsistente` | 9 | 0,1 % |
| `astro_ascendente_contradicho` | 4 | 0,1 % |
| `repeticion_interna` | 3 | 0,0 % |
| `ficha_tecnica` | 1 | 0,0 % |
| `referencia_ausente` | 1 | 0,0 % |

`astro_casa_contradicha`, `elemento_contradicho` y `regente_contradicho` no
aparecen con los patrones estrictos actuales. Se mantienen como red de
seguridad y para cuando el corpus incluya más familias.

Uniones de lecturas afectadas, útiles para priorizar:

| Grupo | Lecturas | % |
|---|---:|---:|
| Cualquier defecto detectado | 6104 | 93,1 % |
| Fórmulas de apertura o cierre | 4269 | 65,1 % |
| Frases plantilla | 3689 | 56,3 % |
| Listas donde se pide prosa | 2452 | 37,4 % |
| Muletillas | 2302 | 35,1 % |
| Placeholder de país o ficha técnica | 2121 | 32,3 % |
| Esquema incumplido | 1056 | 16,1 % |
| Pregunta de futuro sin datos | 133 | 2,0 % |
| Género asumido o inconsistente | 96 | 1,5 % |
| Contradicciones astrológicas | 15 | 0,2 % |
| Truncamiento, referencia ausente, repetición interna o longitud atípica | 18 | 0,3 % |

El 93,1 % no significa que el 93,1 % de las lecturas sea inservible: son
marcadores heurísticos, muchos de forma y no de contenido. Lo relevante es
que los defectos de estilo están extendidos y son sistemáticos, no casos
aislados.

## 4. Hallazgos por familia

### tarot_1, tarot_2, tarot_3 y tarot_pregunta

Calidad de fondo buena en la muestra: usan la Referencia de la KB, no
inventan cartas, responden a la pregunta y derivan a profesionales cuando
aparecen salud o dinero. Los defectos son de forma y de voz:

- Aperturas formulaicas: «Claro, con gusto te acompaño en esta lectura»
  (106 lecturas), «Querido consultante, gracias por compartir tu pregunta
  conmigo» (87), «Qué hermosa carta tienes, y qué pregunta tan profunda»
  (73), «Hola, gracias por compartir tu consulta» (59).
- Cierres casi idénticos: «Estoy aquí para acompañarte» (693), «Un abrazo
  cálido» (72), «¿Hay algo más que quieras explorar sobre esta lectura?»
  (66). Las firmas «Tu tarotista y astróloga» y variantes suman cientos de
  casos.
- Frases plantilla de 50 caracteres o más repetidas en tres o más lecturas:
  750 tipos. «Recuerda que esto es una tendencia, no una sentencia» aparece
  en 310 lecturas; «Tú tienes el libre albedrío para escribir tu propia
  historia», en 78.
- Clichés y relleno: «luz al final del camino» o «del túnel», «el universo
  no te abandona», «desde el corazón», «en el fondo».
- Preguntas retóricas finales y listas de consejos numeradas, incluso
  cuando la respuesta se lee mejor en prosa.
- `tarot_pregunta` a veces evade las preguntas de sí/no con «no es un sí
  rotundo ni un no definitivo», sin dar una orientación clara.
- Género asumido sin dato: «te sientes agotada» (10656, 10692, 10704),
  «te sientes atrapada» (10698).
- `tarot_3` usa listas en el 38,9 % y acumula 544 casos; `tarot_2` en el
  41,1 %.

Ejemplo de lista donde se pedía Lectura en prosa (id 362, tarot_1, 7
líneas):

> - **Resiliencia:** Has demostrado una capacidad enorme para levantarte y
>   seguir. No es poca cosa.

### cruz_celta

Es la familia con mejor estructura formal: las 500 lecturas tienen las 10
secciones numeradas y la Síntesis. La narrativa es coherente y usa la
Referencia. Los problemas son de límites y de reutilización:

- 1.723 secciones superan los 300 caracteres que pide el esquema; 287
  síntesis superan los 400. En total, 373 de 500 lecturas (74,6 %)
  incumplen al menos un límite.
- Se reutilizan frases enteras para la misma carta en lecturas distintas.
  Ejemplo: la sección de La Sacerdotisa de los ids 13837 y 13380 empieza
  igual («En el pasado escuchaste tu voz interior y accediste a una
  sabiduría que iba más allá de lo visible...»).
- La síntesis a veces repite literalmente fragmentos de las secciones.
- Fórmula de cierre «Consejo práctico: ...» y frases sentenciosas entre
  comillas; algunas secciones usan un tono más determinista del permitido
  («El resultado apunta a...»).

Ejemplos de límites (ids 13373, 13374, 13376):

> 5. Meta — La Sacerdotisa (invertida): 312 caracteres (máximo 300).

> 1. Situación — Sota de Copas (invertida): 345 caracteres (máximo 300).

### lectura_completa

La estructura de cuatro secciones está presente en todas las lecturas, pero
el contenido es desigual:

- El 99,4 % (683 de 687) incumple algún límite: 679 síntesis de más de 400
  caracteres, 640 bloques de numerología de más de 400, 609 tiradas fuera
  del rango total de 450 a 900 y 198 cartas natales de más de 600.
- La astrología es superficial: en la muestra se comentan Sol, Luna,
  Ascendente y algún aspecto, y se omiten planetas y aspectos que el prompt
  entrega. La mediana de 2.705 caracteres es corta para tres técnicas.
- Confusión casa/signo: id 17593 dice «tu Luna en Aries en el ascendente»
  cuando la Luna está en Aries en casa 1 y el Ascendente es Piscis.
- Identidad colisionada en el generador de prompts: «Andrés Gil» aparece en
  17317 y 17229 con fechas y preguntas distintas.
- Placeholder de país sin rellenar en todos los registros: «Valencia ()»,
  «La Habana ()».
- Repetición translectura: «las tres técnicas coinciden/convergen», «Cierra
  la lectura...», «Recuerda: ...».
- La numerología recita los números del prompt sin explicar el cálculo ni
  contrastarlos.
- Firma «Tu tarotista y astróloga» también en lecturas de carta natal.

### numerologia

Usa los números calculados del prompt y no los contradice; responde a la
pregunta. Los defectos son de estilo y de estructura:

- Aperturas formulaicas en el 76,7 % (306 de 399): «Qué hermosa
  pregunta/consulta».
- Estructura idéntica número por número, con las mismas áreas y el mismo
  orden, lo que produce lecturas intercambiables.
- Muletillas: «como quien hojea un libro antiguo», «hilo dorado», «desde el
  corazón», «respira hondo».
- Género inconsistente: masculino genérico («constructor nato», «compañero»)
  junto a formas «Querido/a» o «juguetón/a». Nueve casos detectados en todo
  el corpus, cuatro en esta familia.
- Cuando el mismo número aparece en dos posiciones se repiten las mismas
  áreas sin integrarlas.

### astro_natal

Es la familia más voluminosa y la que concentra los defectos de datos:

- 133 de 1.434 preguntas (9,3 %) piden «¿Qué dice mi carta sobre mi próximo
  año?» y el prompt no trae tránsitos, revolución solar ni fechas. El modelo
  responde como si la carta natal predijera el año; el id 15496 dedica una
  sección a «Lo que tu Carta Dice sobre tu Próximo Año».
- Profundidad irregular: el id 15847 tiene 4.331 caracteres y omite
  Mercurio, Júpiter, Saturno y los planetas exteriores; el id 15916 tiene
  12.463 y cubre casi todo.
- Formato inconsistente: el id 15491 no usa encabezados; el 14696 empieza
  directamente en `###`; otros usan H1.
- Contradicciones con las posiciones del prompt: 11 de signo y 1 de
  ascendente. Ejemplos reales: 14933 dice «Saturno en Capricornio» cuando el
  prompt da Piscis; 14958 dice «Urano en Capricornio» con Urano en Acuario;
  15298 dice «Júpiter en Acuario en el ascendente» con Ascendente
  Capricornio.
- Fuga de la ficha técnica: el id 15100 copia «Datos de nacimiento: 22 de
  enero de 1950, 15:00, Panamá» dentro de la respuesta.
- Referencia casi ausente: el id 15414 solo menciona el Sol.
- Firma «Tu tarotista y astróloga», impropia de una lectura natal.
- Listas en el 73,6 % (1.055 de 1.434), a menudo para enumerar planetas o
  casas, lo que convierte la interpretación en un inventario.

## 5. Las diez mejoras de mayor impacto

Porcentajes sobre las 6.557 lecturas y medidos con el detector actual. Una
misma lectura puede estar en varias filas.

| # | Mejora | Afectadas | % | Cómo |
|---|---|---:|---:|---|
| 1 | Prohibir aperturas, cierres y firmas fijas | 4269 | 65,1 % | Instrucción explícita de entrar en materia sin saludo ni firma; filtro que rechace la primera o última frase si ya aparece en 3 lecturas del lote. |
| 2 | Eliminar frases plantilla y cierres retóricos | 3689 | 56,3 % | Lista negra de frases de 50 caracteres o más vistas en 3 o más lecturas; prohibir «¿Hay algo más...?» y «Recuerda que esto es una tendencia...». |
| 3 | Hacer cumplir los límites del esquema | 1056 | 16,1 % | Validar en el verificador los límites que ya pide el prompt: 150-300 por sección de cruz_celta, 400 de síntesis, 600/400/400 de lectura_completa. Hoy el verificador usa 1.200 y 800 y por eso acepta estos textos. |
| 4 | Prohibir listas donde se pide prosa | 2452 | 37,4 % | Regla de estilo por familia; cero listas en lectura_completa y cruz_celta, y prosa por defecto en tarot y astro salvo que el esquema pida pasos. |
| 5 | Quitar muletillas y clichés | 2302 | 35,1 % | Lista negra de 10-15 fórmulas («estoy aquí para acompañarte», «desde el corazón», «luz al final», «vamos a mirar con calma», «como quien hojea», «hilo dorado»). |
| 6 | Corregir placeholders y fugas de ficha técnica | 2121 | 32,3 % | Rellenar el país en el generador de prompts, no imprimir paréntesis vacíos, impedir que la ficha se copie en la respuesta y revisar identidades duplicadas antes de generar. |
| 7 | No responder preguntas de tránsitos sin tránsitos | 133 | 2,0 % | O se añaden tránsitos y fechas al prompt, o se instruye a decir que la carta natal no permite fechar el próximo año y a ofrecer una lectura de tendencias sin inventar plazos. |
| 8 | Neutralizar el género | 96 | 1,5 % | Instrucción de lenguaje neutro cuando el prompt no declare género; prohibir «Querido/a», «agotada», «constructor nato» y mezclas de marcadores. |
| 9 | Verificar las posiciones astrológicas contra el prompt | 15 | 0,2 % | Comprobación determinista de signo, casa y ascendente antes de aceptar; es poco frecuente pero grave, porque una lectura con Saturno en el signo equivocado es factualmente falsa. |
| 10 | Fijar profundidad y formato de astro_natal | No medida | — | Cobertura mínima de planetas y aspectos relevantes, secciones con H1/H2 estables, sin listas de inventario y sin firma de tarotista. Requiere un medidor nuevo; la muestra manual basta para justificarlo. |

Las mejoras 1, 2, 4 y 5 son de prompt y de filtro, y se pueden aplicar sin
tocar el dataset ya generado. Las mejoras 3, 9 y 10 necesitan cambios en el
verificador o en el prompt y afectan a la siguiente generación. Las mejoras
6 y 7 son defectos de la entrada, no del modelo: mientras el prompt lleve
«Valencia ()» o pida el año sin tránsitos, el modelo no puede hacerlo bien.

## 6. Umbrales propuestos

- `apertura_repetida` y `cierre_repetido`: máximo 2 lecturas con la misma
  primera o última frase normalizada.
- `frase_plantilla`: ninguna frase de 50 caracteres o más en 3 o más
  lecturas.
- `muletilla`: máximo 1 por lectura y ninguna en más del 2 % del corpus.
- `lista_en_prosa`: 0 listas en lectura_completa y cruz_celta.
- `esquema_incumplido`: 0 incumplimientos de los límites que pide el prompt.
- `longitud_atipica`: fuera de [0,5 × mediana, 2 × mediana] de la familia.
- `genero_inconsistente` y `genero_asumido`: 0.
- `astro_signo_contradicho`, `astro_casa_contradicha`,
  `astro_ascendente_contradicho`: 0.
- `pregunta_sin_datos`: 0 preguntas de tránsitos sin tránsitos en el prompt.
- `truncamiento`: 0 lecturas sin puntuación terminal.
- `referencia_ausente`: cobertura de cartas dibujadas ≥ 0,8.
- `repeticion_interna`: 0 frases de 50 caracteres o más repetidas dentro de
  la misma lectura.

Estos umbrales son propuestas de filtro, no reglas aplicadas al corpus
actual. El módulo solo informa: no elimina ni reescribe ninguna lectura.

## 7. Limitaciones

- Los detectores son heurísticos. Los porcentajes sirven para ordenar
  problemas, no para decidir que una lectura es inservible.
- Se corrigieron falsos positivos antes de la pasada final: «Pregunta del
  consultante» ya no cuenta como fuga, las listas coordinadas de planetas no
  cuentan como contradicción y los sustantivos como «energía creadora» no
  cuentan como género asumido.
- La comprobación de contradicciones solo cubre construcciones explícitas
  («Saturno en Capricornio», «la Luna está en la casa 3»). Una contradicción
  expresada con rodeos puede pasar.
- El módulo no mide calidad literaria, adecuación fina al tono ni acierto
  interpretativo. Eso exige lectura humana, y por eso se leyeron 96
  lecturas completas además de las comprobaciones.
- No se han podido medir sinastria, multiturno, ética ni baraja española
  porque no hay registros de esas familias en las aceptadas.
- No se detectaron truncamientos reales, inglés residual, «como IA» ni
  disculpas. Los cortes que parecían truncamientos en la muestra eran
  límites de impresión del análisis, no del dato.

## 8. Conclusión

El dataset no tiene un problema grave de invención de cartas ni de
truncamiento. Tiene un problema de voz: las lecturas se parecen demasiado
entre sí por fórmulas, plantillas y muletillas, y en astro_natal hay además
fallos de datos y de profundidad. Antes de entrenar conviene aplicar las
mejoras 1 a 6, que cubren la mayor parte del estilo repetido, y arreglar en
el prompt los placeholders y las preguntas de tránsitos. Las mejoras 7 a 10
deberían entrar en el verificador de la siguiente generación, no en una
limpieza posterior del corpus.
