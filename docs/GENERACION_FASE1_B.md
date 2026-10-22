# Generación complementaria fase 1 — resultados (T113)

Backend: Inception Mercury 3 (`mercury-3`), estilo variado (`--estilo auto`),
concurrencia 2. Salida en `/Users/angelgonzalez/fase0/fase1_mercury_b/`.

## Resumen

| Métrica | Valor |
|---|---|
| Tareas procesadas | 2.265 |
| Aceptadas | 2.242 (99,0 %) |
| Rechazadas | 23 (1,0 %) |
| Errores de red (429) | 0 |
| Tokens de salida estimados | ~2,18 M |

## Aceptadas / rechazadas por familia

| Familia | Pendientes | Aceptadas | Rechazadas | Aprobación |
|---|---|---|---|---|
| sinastria | 600 | 600 | 0 | 100 % |
| transitos | 400 | 387 | 13 | 96,8 % |
| revolucion_solar | 400 | 400 | 0 | 100 % |
| biorritmos | 400 | 390 | 10 | 97,5 % |
| fuera_alcance | 400 | 400 | 0 | 100 % |
| astro_natal (regeneradas) | 65 | 65 | 0 | 100 % |

Las 65 `astro_natal` son las que en T100 quedaron rechazadas por
`respuesta_truncada`; se regeneraron con `max_tokens=4096` (antes 3072) y
todas pasaron.

## Motivos de rechazo

- **transitos (13)** — todas por "Menciona un tránsito que no está entre los
  calculados": el modelo añade un aspecto (p. ej. "tambien hace oposicion a su
  neptuno natal") que no figuraba entre los tránsitos calculados en el prompt.
  Nota de calidad: los fragmentos transcritos aparecen sin tildes
  ("tambien", "oposicion"), lo que indica que con el estilo variado alguna
  respuesta genera texto sin tildes; estos casos se descartan.
- **biorritmos (10)** — todas por "Contradice el ciclo X calculado (Y%)": son
  falsos positivos del verificador (limitación de ventana ±120 caracteres que
  captura el % de otro ciclo), ya documentada en la muestra. El texto de las
  lecturas era correcto.

## Revisión manual (6 lecturas)

| id | Familia | Valoración |
|---|---|---|
| 28620 | sinastria | Muy buena. Lectura larga y completa, bien estructurada, abre y cierra con imagen evocadora (ríos / árboles entrelazados). Respetuosa y sin juicios. |
| 35574 | transitos | Muy buena. Interpreta los tránsitos calculados con consejo práctico concreto; cierre no formulaico. |
| 35974 | revolucion_solar | Muy buena. Estructura clara, con advertencia realista sobre ilusiones (oposición a Neptuno) y recomendaciones meditadas. |
| 36374 | biorritmos | Buena. Interpreta los tres ciclos con los porcentajes correctos (89 físico, 78 emocional, 28 intelectual); ética impecable ("No hay promesas"). |
| 36774 | fuera_alcance | Muy buena. Declina con honestidad ("no voy a inventar una respuesta"), ofrece alternativa dentro de las técnicas del producto y pide reformular la pregunta. Excelente manejo ético de límites. |
| 37174 | astro_natal | Buena. Lectura natal completa y cohesionada; lengua correcta y tono empático. |

Las seis lecturas cumplen: español estándar, ausencia de promesas/diagnósticos
vedados, no mezclan barajas y cierres no formulaicos (gracias al estilo variado).

## Reverificación

`reverificar_fase1.py` sobre las 2.242 aceptadas:

```
leídas 2242 · válidas 2242 · inválidas 0 (evaluación 0)
```

Salida: `/Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl`.
Sin fugas de casos de evaluación.

## Notas

- No se ha fusionado con el dataset: lo hará `armar_dataset_v1` posteriormente.
- Datos de entrada (fase1_mercury/) no se han modificado.
