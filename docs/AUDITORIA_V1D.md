# Auditoría adversaria del dataset v1d (T135)

Fecha: 2026-10-23. Autor: opencode (track `t135-auditoria-v1d`).

## Alcance y método

- Dataset auditado: `/Users/angelgonzalez/fase0/dataset_fase1_v1d` (train 11.986 / val 648 / test 656 = 13.290 filas). **Solo lectura: no se modificó ninguna fila.**
- Auditoría determinista, sin LLM y sin nodos GPU. Código: `finetune/corpus/auditoria_v1d.py`; tests: `finetune/corpus/tests/test_auditoria_v1d.py` (38 casos adversos sintéticos, `unittest`).
- Muestreo estratificado reproducible: semilla fija 135, por familia × split (400 por celda) para los checks que no son de paso completo. Fugas, duplicados, longitudes, tiradas, fuera_alcance, secretos y coherencia se calculan sobre **todas** las filas.
- Objetivo: defectos que `qa_dataset.py` no detecta (fuga por n-gramas en respuestas, lenguas PT/GL/CA, restos de razonamiento, citación de datos no calculados, tiradas vs baraja correcta, secretos).
- Salidas del run: `/Users/angelgonzalez/fase0/auditoria_v1d/auditoria_v1d.json` y `resumen.md`.
- Reproducir: `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/auditoria_v1d.py --dataset-dir /Users/angelgonzalez/fase0/dataset_fase1_v1d --kb-dir finetune/corpus/kb --salida /Users/angelgonzalez/fase0/auditoria_v1d --semilla 135` (≈100 s).

## Tabla de hallazgos por gravedad

| # | Hallazgo | Grav. | Filas | Ejemplos (id) |
|---|---|---|---|---|
| 1 | Bloque `fuera_alcance`: 398/398 prompts corruptos («Pregunta del consultante: "131 Vengo a preguntarte:"») | **BLOQUEANTE** | 398 | 36905, 37084 |
| 2 | Fuga train↔val/test: prompts casi idénticos (similitud ≈1,00 sobre n-gramas) | **BLOQUEANTE** | 274 pares | 21437↔3063, 21474↔21649↔3068 |
| 3 | Mismo prompt con 2 respuestas distintas (redundancia del generador) | GRAVE | 1.696 | 14627↔14474 |
| 4 | Familia `multiturno` (728 filas) es monoturno real: un solo turno sin historial | GRAVE | 728 | 20293 |
| 5 | `markdown_en_respuesta`: `**`/`##` en 6.652 respuestas (fuera de los bloques con esquema obligatorio) | GRAVE (decisión) | 6.652 | 14627, 13327 |
| 6 | Aspectos citados y no calculados (defecto estructural en sinastria y revolución solar) | GRAVE | 219 | 29160, 29130 |
| 7 | Signos no calculados (p. ej. «Medio Cielo en Virgo» con MC calculado en Leo) | GRAVE | 41 | 36196 |
| 8 | Números de numerología contradictorios con el cálculo del prompt (incl. intercambio alma/personalidad interno) | GRAVE | 25 | 17012 |
| 9 | Casas mencionadas sin evidencia calculada (mezcla temática: «la Casa 2», «eje casa 6 y 10») | MENOR-GRAVE | 78 | 15787, 14863 |
| 10 | Respuesta casi idéntica cross-split (corpus real, 316 n-gramas compartidos) | MENOR | 1 par | train#3780↔test#0 |
| 11 | `acaba_truncado` (última palabra función gramatical) | MENOR | 33 | 14653, 36336 |
| 12 | `sin_puntuacion_final` (≥80 chars sin punto final) | MENOR | 4 | — |
| 13 | `sin_tildes` (≥160 chars propios sin ningún acento) | MENOR | 3 | 2920 |
| 14 | `fase_biorritmo_incorrecta` (ambigüedad fase=pendiente vs nivel; muestreo: casi todos dudosos) | MENOR | 5 | 36627 |
| — | Duplicados exactos (prompt+respuesta) | OK | 0 | — |
| — | Tiradas inválidas (carta fuera de baraja, repetida, mezcla española/francesa, Referencia≔tirada) | OK | 0 | — |
| — | Secretos/PII (API keys, JWT, AWS, emails, teléfonos, IPs) | OK | 0 | — |
| — | Longitudes anómalas (outliers por familia, z-score) | OK | 0 | — |
| — | Mezcla de lenguas PT/GL/CA, restos `asistente de IA`, `<thinking>` | OK | 0 | — |

## Detalle de los hallazgos

### 1. `fuera_alcance` corrupto (BLOQUEANTE)

Confirmado en v1d: **las 398 filas** del bloque tienen la pregunta truncada por el bug de `generate_tasks.py:977-986` identificado en la Ronda 7 (`docs/AUDITORIA_RONDA7.md`), que nunca se regeneró. Patrón: `Pregunta del consultante: "131 Vengo a preguntarte:"` — el texto de la pregunta real se perdió. Las respuestas literizan los restos («Esa fórmula, con ese número al inicio…»), así que el bloque entreno enseña a responder preguntas rotas. Ronda 7 ya dictaminó su invalidez.

Nota positiva: con los filtros de negación/rechazo aplicados, **ninguna** respuesta de este bloque hace predicción médica/legal/financiera concreta ni enumera técnica prohibida como servicio: los 6 «técnicos» que marcaba la primera pasada eran rechazos legítimos («como la quiromancia… te recomiendo otro profesional»). El defecto es solo el prompt corrupto.

### 2. Fuga entre splits (BLOQUEANTE)

274 pares train↔val/test con prompts casi idénticos: similitud ≈1,00 sobre 12-gramas con 6-7 n-gramas compartidos, mayoritariamente en bloques `espanola_1`/`tarot_*` donde la variabilidad del generador es baja (misma tirada + misma pregunta parafraseada igual). `qa_dataset.py` solo comparaba prompts **exactos** y pares dentro del mismo bucket con difflib muestreado; esta auditoría usa un índice invertido de n-gramas sobre el lado mini (val+test), con umbral adaptativo (`max(6, min(14, 0.6·|más corto|))`) y descarte de boiler (df≥3 en val/test). Con 274 fugas, val/test miden memorización, no generalización. Ejemplos: train id 21437 ↔ val id 3063; train id 21474 ↔ val id 21649 y test id 3068.

### 3. Misma pregunta, distintas respuestas (GRAVE)

1.696 filas train comparten prompt propio (≥40 chars normalizado, sin cabeceras de esquema/referencia) con otra respuesta distinta: el generador repite prompts y produce lecturas alternativas. No son duplicados exactos, pero combinado con §2 sesga la evaluación y sobrepondera ciertas tiradas/preguntas en la distribución de train.

### 4. `multiturno` no es multiturno (GRAVE)

Las 728 filas de la familia `multiturno` tienen `conversations` de 3 roles (system/human/gpt) exactamente como un turno simple: no hay historial de consultas anteriores en el humano ni marcas tipo «Consultas anteriores». El dataset **no contiene una sola conversación multiturno real**, pese a que la cobertura prometida incluía multiturno. (Verificado además: el resto de filas tienen todas roles system/human/gpt.)

### 5. Markdown en respuestas (decisión de diseño)

6.652 respuestas contienen `**negritas**` o `##` fuera de los bloques cuyo prompt exige esquema (`cruz_celta`, `lectura_completa`, que lo piden explícitamente con «ESQUEMA OBLIGATORIO»). El uso se extendió a todos los bloques por imitación del estilo del generador. No es un error de limpieza como los de Ronda 7 (`<p>`, `{{`): es una decisión de formato de salida de la app. Si la app no renderiza markdown, hay que limpiar o reescribir.

### 6-8. Datos calculados citados que no están en el prompt (GRAVE)

Coherencia respuestas↔`calculos`↔prompt (tras depurar falsos positivos de sintaxis — cadena «en sextil a X y en cuadratura con Y», «entre X y Y», aposiciones):

- **aspecto_no_calculado: 219** flags (astro_natal 149, sinastria 63, transitos 25, revolucion_solar 24). Muestreo manual de 10: ~4-6 reales. El defecto es **estructural en sinastria** (verificador ausente en Ronda 7): las respuestas afirman aspectos cruzados A↔B que el prompt nunca calculó. Ejemplos reales: id 29160 «sol venus», id 29130 sextil Venus↔Plutón entre cartas.
- **signo_no_calculado: 41**: en su mayoría alucinaciones verdaderas. Ejemplo: id 36196 «Medio Cielo en Virgo» cuando la revolución calcula MC en Leo y la natal en Géminis.
- **numero_numerologia_incorrecto: 25**: números sin relación con el calculado (se aceptan reducciones maestras 11→2, 22→4, 33→6). Ejemplo: id 17012 contradice sus propios valores (alma=22 y alma=11 en la misma respuesta).
- **casa_no_calculada: 78**: mezcla de casas temáticas legítimas en prosa («es eje profesional: casa 6 y casa 10») con afirmaciones de posición sin evidencia; gravedad menor, patrón difuso.
- **fase_biorritmo_incorrecta: 5**: semántica — `fase` del cálculo es la pendiente del ciclo, no el nivel; los 5 casos revisados son ambiguos o falsos positivos (deseos modales: «recupere dirección ascendente»). Se reporta como MENOR.

### 10-14. Menores

- 1 par de respuestas casi idénticas cross-split (filas del corpus real, `id=None`): train#3780 ↔ test#0, 316 n-gramas compartidos (sim 0,87).
- 33 respuestas terminan en palabra funcional («…no la negación de este»), 4 sin puntuación final, 3 sin ningún acento en ≥160 chars propios (ej. id 2920, bloque `etica`).
- Los checks de restos de razonamiento (`<think>`, «Thinking:»), restos de asistente de IA, inglés/portugués/gallego/catalán, y secretos (claves API, JWT, AWS, correos, teléfonos, IPs) dieron **cero**.
- `longitudes_anomalas` dio cero: sin outliers extremos ni por familia (p50/p95 por familia en rango).
- `tiradas_invalidas` cero: todas las cartas citadas en prompts de naipes existen en la baraja correcta (tarot 78 / española 40, KB validada), sin repetidas dentro de la tirada, y la sección Referencia coincide con lo tirado. (Nota: este check generaba 21.249 falsos positivos en la primera pasada por una regex que capturaba palabras comunes; quedó restringido a nombres capitalizados que parecen carta. Los tests sintéticos cubren ambos modos.)

## Qué añade esta auditoría frente a `qa_dataset.py`

`qa_dataset.py` (693 líneas) ya cubría: formato de roles, ids únicos, mojibake, sin-tildes, truncado por puntuación, restos de plantilla, inglés largo, fuga contra los 240 casos de eval, fuga de prompts exactos cross-split y sanidad por muestreo (15/bloque). Esta auditoría añade: fuga por n-gramas de **respuestas** y de prompts casi-idénticos sin bucket, duplicados globales y pares pregunta↔respuesta, lenguas PT/GL/CA y restos de razonamiento, verificación de tiradas contra la baraja correcta (KB), citación de planetas/signos/casas/aspectos/porcentajes/números no calculados, predicciones concretas y prompts corruptos en `fuera_alcance`, distribución de longitudes por familia y búsqueda de secretos/PII.

## DECISIONES pendientes para el usuario

1. **`fuera_alcance` (398)**: regenerar el bloque con el bug de `generate_tasks.py` corregido, o eliminarlo del v1d. (BLOQUEANTE mientras no se decida.)
2. **Fugas cross-split (274 pares)**: expulsar de train el lado duplicado (o del split mini el duplicado) y reconstruir splits; decidir umbral definitivo. Val/test actuales no son fiables para medir generalización.
3. **Pares misma-pregunta-distinta-respuesta (1.696)**: ¿deduplicar a una fila por prompt, o aceptarlos como aumento de datos? Afecta a la distribución y a la evaluación.
4. **`multiturno` (728)**: ¿re-etiquetar como turnos simples o generar conversaciones multiturno reales antes del entrenamiento definitivo?
5. **Markdown (6.652)**: ¿formato objetivo de la app? Si no, limpiar `**`/`##` o ajustar prompts del generador.
6. **Alucinaciones de datos calculados (~285 filas claras: aspectos 219 con muestreo mixto, signos 41, numerología 25)**: ¿expurgar las filas afectadas, o regenerar los bloques `sinastria`/`revolucion_solar`/`astro_natal` con verificadores fuertes (la corrección de Ronda 7 no llegó al v1d)?
7. **Puerta de calidad**: ¿añadir `auditoria_v1d.py` al pipeline de armado de dataset (como gate, con salidas != 0 en BLOQUEANTE) para las versiones v1e+?

## Limitaciones del método

- La detección de aspectos/signos/casas depende de análisis sintáctico heurístico; el muestreo manual (10+5+5 banderas) estima un 40-50% de falsos positivos residuales en `aspecto_no_calculado` y menos en signos/numerosología (los ejemplos revisados eran reales). Las cifras son techo, no suelo exacto.
- Similitud de prompts con 12-gramas y umbral adaptativo puede dejar fuera fugas parafraseadas por debajo de 6 n-gramas compartidos.
- El check de tiradas valida contra la KB (`tarot.json`, `baraja_espanola.json`); una carta mal escrita en la KB pasaría desapercibida.
