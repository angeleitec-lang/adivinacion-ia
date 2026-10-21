# QA dataset v1 (fase 1, parcial) — pista T110

Fecha: 2026-10-21. Script: `finetune/corpus/qa_dataset.py` (solo lectura, sin red, sin
modificar el pipeline). Entrada: `/Users/angelgonzalez/fase0/dataset_fase1_v1/`
(train 5205 / val 578 / test 582 = 6365 filas). Casos de evaluación:
`_etapas/eval/evaluacion_560056/560057/560058.jsonl` (240 casos, sin respuestas
guardadas). Salidas: `/Users/angelgonzalez/fase0/qa_dataset/` (`qa_report.json`,
`findings.tsv` —índices de fila en 0—, `resumen.txt`). Muestreo de sanidad:
semilla fija 42, 15 filas por bloque.

Reproducción:

```
finetune/.venv/bin/python finetune/corpus/qa_dataset.py \
  --dataset /Users/angelgonzalez/fase0/dataset_fase1_v1 \
  --out /Users/angelgonzalez/fase0/qa_dataset
```

## Recuentos

- Generador `mercury-3`: 5431 filas (9 bloques: tarot_1 837, tarot_2 294, tarot_3
  1077, tarot_pregunta 718, astro_natal 819, numerologia 339, lectura_completa
  1110, cruz_celta 237).
- Generador `real-corpus` (sin `id`/`bloque`): 934 filas (informe T103: 860 train,
  42 val, 32 test). System corto de `build_dataset.py` = variante autorizada.

## 1. Formato por fila

Limpio en todo el dataset sintético: 0 no-NFC, 0 caracteres de control, 0 mojibake,
0 ids repetidos, 0 ids colisionando con eval, 0 esquemas de roles rotos, 0 systems
no autorizados, 0 human sin tilde en prompts largos, 0 respuestas sin ESQUEMA
OBLIGATORIO en cruz_celta.

**Los 344 hallazgos de formato son todos de las 934 filas `real-corpus`
(sin_bloque):**

| Chequeo | n | Ejemplo |
|---|---|---|
| respuesta_truncada | 327 | id sin, train:1 → termina en `'---------'`; train:24 → `'…íos, húmedos, suaves'` |
| sin_tildes | 5 | train:612 turno gpt (1739 chars) sin una sola tilde |
| longitud_extrema | 7 | gpt de 42–73 chars |
| restos_plantilla | 3 | gpt contiene `'asistente de ia'`, llaves `{}` |
| ingles_largo | 2 | gpt con ≥20 palabras comunes en inglés |

## 2. Fugas

### 2.1 Dataset vs 240 casos de eval

- **3 fugas reales de prompt** (`fuga_eval_prompt_identico`, propio igual tras
  quitar la plantilla): id 14170 (train) = `eval-tarot_1-16`; id 14508 (train) =
  `eval-tarot_1-13`; id 14203 (**val**) = `eval-tarot_1-02`. Misma carta, mismo
  contexto, misma pregunta que el caso con el que se medirá el modelo. El filtro
  anti-fugas de T103 las dejó pasar.
- 1281 coincidencias de n-gramas de 12 palabras (`fuga_eval_fragmento`) en los 8
  bloques sintéticos: astro_natal 253, numerologia 214, lectura_completa 223,
  tarot_1 192, tarot_pregunta 156, tarot_3 142, cruz_celta 55, tarot_2 46.
  **Se matiza**: eval se genera con la misma plantilla y el mismo banco de
  preguntas que el dataset (los n-gramas compartidos son cabeceras + datos +
  pregunta del mismo generador, no respuestas). Con el filtro de boilerplate
  (≥20 filas) quedan 197 hallazgos con ≥5 n-gramas compartidos, que en la
  práctica repiten la entrada completa de un caso eval con otros valores. El
  riesgo real y accionable son los 3 prompts idénticos de arriba; el resto es un
  diseño de banco compartido que devalúa la medición (el eval no puede sorprender
  al modelo con preguntas que ya están en entrenamiento).

### 2.2 Entre splits

- **71 grupos con el propio-prompt idéntico entre train/val/test** (tarot_1 36,
  tarot_pregunta 35). El prompt completo no es idéntico (0 casos): difiere solo
  la instrucción final («Interpreta la carta…» vs «Responde a la pregunta…»), y
  las respuestas son otras generaciones. Ejemplo: ids 10850 (train) y 14015
  (val) comparten El Emperador/…/pregunta. La misma situación se repite entre
  splits → val/test miden memorización, no generalización.
- Muestreo de pares casi idénticos (similitud ≥0.9, cap 12/bucket): **150 pares**
  detectados, sobre todo en numerologia (5 buckets con solapes de mismo número
  y misma pregunta, p. ej. pregunta «qué me dice la numerología sobre mi
  relaciones» con 66/8/8 filas en train/val/test).
- 5 buckets solapados por clave (bloque, cartas/orientación, fecha, pregunta),
  todos numerologia; los bloques de tarot están cubiertos por el hallazgo de
  prompt idéntico.

## 3. Sanidad por muestreo (15 filas/bloque, semilla 42)

| Bloque | Fallan | Observación |
|---|---|---|
| tarot_1 / tarot_2 / tarot_3 / tarot_pregunta / cruz_celta | 0/15 | cartas citadas, orientación respetada |
| astro_natal / lectura_completa | 0/15 | signos citados |
| numerologia | 0/15 | números del prompt citados |
| sin_bloque (real-corpus) | 4/15 (26,7 %) | restos web en la respuesta (`suscr`, `página`, `visita`) |

## 4. Cobertura

El dataset tiene 9 bloques; eval tiene 12 familias. **No hay filas de tarot
español/baraja española, casos de alcance/ética (fuera de alcance, quiromancia,
medicina/legal), tiradas de 10 cartas (Rev. Sol y similar) ni biorritmos en el
train** —120 de los 240 casos eval miden comportamientos que el dataset no
enseña. El informe T103 ya lo reconocía (baraja 36/40 cartas, etica/fuera_alcance
0 filas), pero el semáforo VERDE se declaró igualmente.

## 5. Conclusión: ¿es fiable el VERDE de T103?

**No del todo.** Los bloques sintéticos mercury-3 pasan formato, sanidad y no
revelan fugas graves… salvo dos cosas que T103 no cazó:

1. 3 filas con el prompt idéntico a casos de eval (2 en train, 1 en **val**,
   donde val es precisamente el termómetro).
2. 71 grupos de situaciones repetidas entre splits + 150 pares casi idénticos:
   val/test están contaminados y sobreestiman el rendimiento.

Además, las 934 filas `real-corpus` incumplen el propio contrato de calidad que
el informe da por bueno (327 respuestas cortadas sin puntuación, restos de web,
respuestas en inglés) y 120 casos eval miden técnicas ausentes del train. El
dataset **es aprovechable**, pero no en este estado para medir ni para un
entrenamiento final limpio.

### Corregir antes de entrenar (propuestas, sin tocar el pipeline desde esta pista)

1. **Expulsar** del dataset las ids 14170, 14508, 14203 (fuga directa con eval).
2. **Deduplicar entre splits**: mantener una fila por grupo de prompt-igual
   (71 grupos) y, para los 150 pares casi idénticos, reasignar o regenerar las
   filas de val/test con cartas/contextos/preguntas distintos de train.
3. **Depurar o descartar las 934 filas `real-corpus`** (≥327 truncadas + restos
   web): o filtrarlas con el validador de la fase sintética, o reescritas con el
   system largo y formato de casa.
4. **Cerrar el hueco de cobertura** (baraja española, fuera-de-alcance/ética,
   tiradas de 10, biorritmos) o reducir eval a las familias entrenadas para el
   primer checkpoint.
5. **Integrar `qa_dataset.py` como puerta** en `armar_dataset.py`/`validate`
   (bloqueo si hay `fuga_eval_prompt_identico` > 0 o prompts idénticos entre
   splits).
