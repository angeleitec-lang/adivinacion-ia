# ARMAR_DATASET_V1C — Dataset de fase 1 v1c

Track **T117**. Construye `fase0/dataset_fase1_v1c/` a partir de **dos fuentes**:
`fase1_mercury` (aceptadas.jsonl, 11851 filas, T100) y `fase1_mercury_b`
(aceptadas.reverificadas.jsonl, 2242 filas, T113). Misma cadena de armado que
v1b (reverificar → filtrar fugas evaluación → sharegpt → validate_synthetic →
build_dataset → merge_final → preparar_entrenamiento → QA gate), con la
adición del soporte multi-fuente y el cierre de los residuos (a)/(b)/(c).

## 1. Filas por bloque y split

Total: **12796** filas (train 11563 / val 609 / test 624).

| bloque | train | val | test | total |
|---|---:|---:|---:|---:|
| lectura_completa | 1481 | 83 | 84 | 1648 |
| astro_natal | 1327 | 69 | 71 | 1467 |
| tarot_3 | 1238 | 69 | 71 | 1378 |
| tarot_1 | 814 | 46 | 47 | 907 |
| espanola_3 | 796 | 45 | 46 | 887 |
| tarot_pregunta | 696 | 39 | 41 | 776 |
| multiturno | 687 | 39 | 40 | 766 |
| sinastria | 517 | 29 | 31 | 577 |
| sin_bloque (real) | 447 | 25 | 16 | 488 |
| cruz_celta | 441 | 25 | 27 | 493 |
| espanola_1 | 359 | 21 | 20 | 400 |
| espanola_5 | 358 | 19 | 21 | 398 |
| fuera_alcance | 356 | 20 | 22 | 398 |
| revolucion_solar | 356 | 20 | 22 | 398 |
| tarot_2 | 353 | 20 | 22 | 395 |
| biorritmos | 341 | 20 | 21 | 382 |
| numerologia | 332 | 0 | 0 | 332 |
| etica | 300 | 0 | 0 | 300 |
| transitos | 187 | 10 | 11 | 208 |
| espanola_7 | 177 | 10 | 11 | 198 |

Generador: mercury-3 11608 · real-corpus 488 · (sin dato 0).

### Proporción vs objetivo (generate_tasks.TARGETS)

| familia | objetivo | final | % |
|---|---:|---:|---:|
| tarot_1 | 936 | 907 | 97% |
| tarot_2 | 400 | 395 | 99% |
| tarot_3 | 1400 | 1378 | 98% |
| cruz_celta | 500 | 493 | 99% |
| tarot_pregunta | 800 | 776 | 97% |
| astro_natal | 1500 | 1467 | 98% |
| sinastria | 600 | 577 | 96% |
| numerologia | 400 | 332 | 83% |
| lectura_completa | 3000 | 1648 | 55% |
| multiturno | 800 | 766 | 96% |
| etica | 300 | 300 | 100% |
| espanola_1 | 400 | 400 | 100% |
| espanola_3 | 900 | 887 | 99% |
| espanola_5 | 400 | 398 | 100% |
| espanola_7 | 200 | 198 | 99% |
| transitos | 400 | 208 | 52% |
| revolucion_solar | 400 | 398 | 100% |
| biorritmos | 400 | 382 | 96% |
| fuera_alcance | 400 | 398 | 100% |

## 2. Comparación v1b → v1c

| | v1b | v1c | Δ |
|---|---:|---:|---:|
| train | 8131 | 11563 | +3432 |
| val | 425 | 609 | +184 |
| test | 430 | 624 | +194 |
| **total** | 8986 | 12796 | +3810 |
| bloques | 15 | 20 | +5 |

v1c incorpora los 5 bloques de T113 que v1b no tenía (sinastria, transitos,
revolucion_solar, biorritmos, fuera_alcance) y amplía astro_natal con las 65
filas regeneradas. lectura_completa y transitos quedan por debajo del objetivo
porque la mayoría de sus candidatas son descartadas en reverificar por exceder
los máximos de sección (1200/800 caracteres), no por pérdida de calidad.

## 3. Puerta QA

QA v1c: **0 fugas con conjunto de evaluación** · **0 solapes exactos entre
splits** (prefijo 0, completo 0) · **0 casi idénticos** · **0 buckets
solapados**. Hallazgos de formato: 2 (`restos_plantilla`, en astro_natal, turno
2 gpt «lenguaje natural» — preexistentes, ajenos a los residuos de T117).
Sanidad por muestreo: lectura_completa 1/15 falla (fila 1101); resto 0 fallos.
**semáforo QA: verde**.

`preparar_entrenamiento`: **semáforo verde** (errores [], avisos [], fugas 0).

## 4. Diversidad (diversidad_dataset.py sobre train)

- TTR global: 0.004; únicas 4g 0.74 / 6g 0.90 (media ponderada por bloque).
- Cartas tarot: 78/78 vistas, 0 huecos; españolas: 40/40, 0/40 ausentes.
- Preguntas distintas: 461 de 10599 (69.8% coinciden con plantillas
  generate_tasks). Pregunta más repetida: «¿Qué bloqueo me está frenando?» (341).
- Duplicados MinHash (Jaccard ≥0.95): 0 en todos los bloques.
- Bloques con menor TTR (más repetitivos): lectura_completa 0.015, sinastria
  0.015, tarot_3 0.016. Mayor: sin_bloque 0.128.

## 5. Calidad (calidad_lecturas.py sobre train)

Defectos dominantes (esperables en síntesis con plantilla): frase_plantilla
42.1%, apertura_formula 30.6%, apertura_repetida 27.3%, lista_en_prosa 27.0%,
cierre_repetido 26.9%, muletilla 25.3%, placeholder_prompt 24.3% (lectura_completa
casi 100%), esquema_incumplido 15.6%. Graves y acotados: astro_signo_contradicho
3.9% (sinastria 443), pregunta_sin_datos 1.1% (astro_natal 122), genero_asumido
0.9%, referencia_ausente 0.4% (transitos 42). Truncamiento/ficha_tecnica: 1.

## 6. Residuos T117 cerrados

- (a) prompt idéntico / misma situación → mismo split (union-find en
  `split_agrupado`): QA 0 solapes ban 0 casi idénticos entre splits.
- (b) fila train «asistente de IA»: descartada — `grep -ic "asistente de ia"`
  en train.jsonl = 0 (puerta real case-insensitive).
- (c) preguntas basura en fuera_alcance: contadas, no eliminadas (120/400 en la
  fuente; herramienta `contar_preguntas_basura` en qa_dataset.py).
- Soporte multi-fuente (`--fuente` repetible): corregido bug de formato plano vs
  ShareGPT en `humano_completo`/`respuesta_completa` que descartaba mercury_b
  como duplicados falsos.

## 7. Comando de construcción

```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/armar_dataset_v1.py \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl \
  --salida /Users/angelgonzalez/fase0/dataset_fase1_v1c \
  --train-ratio 0.9 --val-ratio 0.05 \
  --real-raw /Users/angelgonzalez/adivinacion-ia/finetune/corpus/raw \
  --manifest /Users/angelgonzalez/adivinacion-ia/finetune/corpus/manifest.json
```
