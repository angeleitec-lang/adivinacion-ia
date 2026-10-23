# ARMAR_DATASET_V1E — de v1d a v1e (T141)

Construcción determinista del dataset **v1e** a partir de **v1d**, aplicando los
arreglos de la auditoría T135 (`docs/AUDITORIA_V1D.md`). Sin LLM, sin nodos de
entrenamiento. Semilla fija **141**.

- Entrada: `/Users/angelgonzalez/fase0/dataset_fase1_v1d` (solo lectura;
  13290 filas: train 11986 / val 648 / test 656) y
  `/Users/angelgonzalez/fase0/auditoria_v1d/auditoria_v1d.json`.
- Salida: `/Users/angelgonzalez/fase0/dataset_fase1_v1e` (nuevo).
- Script: `finetune/corpus/armar_dataset_v1e.py` (tests:
  `finetune/corpus/tests/test_armar_dataset_v1e.py`, 19 casos adversos).
- Registro de ids afectados por paso: `/Users/angelgonzalez/fase0/dataset_fase1_v1e/_cambios/<paso>.jsonl`.
- Resumen machine-readable: `/Users/angelgonzalez/fase0/dataset_fase1_v1e/resumen.json`.

## Orden de ejecución de los pasos

El orden efectivo es **1 → 3 → 4 → 5 → 6 → 2** (paso 2 al final). Motivo: el
filtro de boilerplate del detector de similitud (`auditoria_v1d._pares_similares`)
se construye **solo desde val/test**; los pasos 4 y 6 cambian la composición de
val/test, así que las fugas deben detectarse sobre la composición definitiva. Con
el orden numérico antiguo se escapaba un par train↔val de similitud 0.996.

## Paso 1 — fuera_alcance (bloque corrupto)

Se retiran **las 398 filas** del bloque `fuera_alcance` de v1d (357 train /
20 val / 21 test): preguntas corruptas que arrancaban con prefijo numérico.
Detección con el propio detector de la auditoría (`check_fuera_alcance`), no a
mano: 398/398 coinciden.

**Paso 1b (pendiente, reanudable):** la intención original era sustituir el
bloque por `fuera_alcance_v2` (T136). T136 **no está completo**: no existe
`/Users/angelgonzalez/fase0/fuera_alcance_v2/fuera_alcance_v2.jsonl` (solo hay
un `aceptadas.jsonl` con 14 líneas). v1e se construye **sin** ese bloque. El
script acepta `--fuera-alcance-v2 <ruta>` y, si el fichero existe, integra las
aceptadas repartiendo 90/5/5 (train/val/test) con ids `fa2-*`. Al re-ejecutar
con el fichero ya presente, el paso 1b se activa solo.

## Paso 2 — fugas cross-split (train ↔ val/test)

Tres vías, todas retirando **solo el lado train** (val/test no se toca):

- **(a) Similitud de prompt** (`prompt_propio`, umbral `SIM_PROMPT_MIN=0.83`):
  pares train↔val/test casi idénticos.
- **(b) Similitud de respuesta** (`limpia_texto(respuesta)`, umbral
  `SIM_RESP_MIN=0.86`): incluye la extensión documentada del par por respuesta
  train#3780↔test#0 (corpus real, sim 0.87).
- **(c) Prompt exacto cross-split** (hash normalizado de `prompt_propio`,
  len ≥ 40): necesario porque el filtro de boilerplate del detector oculta un
  prompt exacto cuando se repite ≥ 3 veces en val/test.

Total retiradas paso 2: **77** filas train.

## Paso 3 — mismo prompt con varias respuestas en train

De los ~1696 grupos de la auditoría (tras pasos previos quedan menos), se
conserva **una fila por prompt propio exacto**: la que no tenga banderas de
expurgo (ver paso 4); si todas están limpias, la de id menor.
Total retiradas paso 3: **1075** filas train.

**Hallazgo (decisión abierta, ver abajo):** en bloques muy plantillados el
dedupe colapsa muchas filas: `etica` train 281 filas = solo 7 prompts propios
únicos (máx. 44 repeticiones); `espanola_1` train 343 = 76 prompts únicos
(máx. 10 repeticiones). La carta sorteada **sí** forma parte del prompt propio
en `espanola_1` («carta: caballo de espadas (al derecho)»), así que la
diversidad de tiradas se conserva por prompt único, pero el volumen final cae
fuerte en esos bloques.

## Paso 4 — alucinaciones de datos calculados

Se retiran en **todos los splits** las filas con estas categorías de
`check_coherencia_calculos`:

| Categoría | Retiradas |
|---|---|
| `signo_no_calculado` | 41 |
| `numero_numerologia_incorrecto` | 25 |
| `aspecto_no_calculado` | 194 |
| **Total paso 4** | **260** |

**Conservadas y listadas** (no se retiran, decisión del encargo):
`casa_no_calculada` (78 en v1d; **65** sobreviven en v1e) y
`fase_biorritmo_incorrecta` (5 en v1d; **5** en v1e). Listado en
`_cambios/paso4_conservadas.jsonl` (38 filas con alguna de estas banderas que
permanecen en el dataset).

Nota: los conteos por categoría difieren de los de la auditoría v1d porque los
pasos 1 y 3 ya retiraron filas que también los tenían.

## Paso 5 — multiturno falso

Las 728 filas del bloque `multiturno` de v1d son en realidad **monoturno** (el
"contexto" va dentro del mismo mensaje). **No se borran**: se reetiquetan a
`consulta_con_contexto`, conservando id, y el bloque original queda guardado en
el campo `bloque_origen` de cada fila. Reetiquetadas: **472** (el resto ya había
sido retirado por pasos anteriores).

**Pendiente:** generar multiturno real (varios turnos de consultor/consultante)
para el bloque; no existe en v1e.

## Paso 6 — numerología sin test

v1d tenía numerología con test = 0 (train 321 / val 14 / test 0). Se mueven
**20 a test** y **15 a val** desde train, con bucle de reparación: si una fila
movida forma par similar con train (o con el otro split destino), se retira y se
rellena con el siguiente candidato, hasta 0 fugas. Resultado final:
numerología **269 train / 28 val / 20 test**.

Descubrimiento: los 321 prompts de numerología train comparten plantilla (todos
similares entre sí), pero el detector con boiler permite mover 20+15 sin crear
fuga cross-split.

## Paso 7 — markdown (no se cambia)

**Decisión: NO se limpia el markdown** de las respuestas. Solo se informa:
**5823 filas** de v1e contienen markdown en la respuesta (`##`, `**`, listas).
Queda pendiente la decisión de usuario sobre si limpiarlo o conservarlo como
estilo de salida.

## Tabla v1d → v1e por bloque y split (train / val / test)

| Bloque | v1d | v1e |
|---|---|---|
| astro_natal | 1332 / 69 / 73 | 1235 / 63 / 67 |
| biorritmos | 342 / 20 / 20 | 341 / 20 / 20 |
| consulta_con_contexto | 0 / 0 / 0 | 387 / 37 / 37 |
| cruz_celta | 442 / 25 / 26 | 442 / 25 / 26 |
| espanola_1 | 343 / 20 / 20 | 46 / 20 / 20 |
| espanola_3 | 799 / 45 / 45 | 797 / 45 / 45 |
| espanola_5 | 358 / 19 / 21 | 358 / 19 / 21 |
| espanola_7 | 177 / 10 / 11 | 177 / 10 / 11 |
| etica | 281 / 3 / 14 | 5 / 3 / 14 |
| fuera_alcance | 357 / 20 / 21 | 0 / 0 / 0 |
| lectura_completa | 1765 / 99 / 100 | 1758 / 98 / 99 |
| multiturno | 654 / 37 / 37 | 0 / 0 / 0 |
| numerologia | 321 / 14 / 0 | 269 / 28 / 20 |
| revolucion_solar | 357 / 20 / 21 | 334 / 19 / 19 |
| sin_bloque | 447 / 25 / 16 | 446 / 25 / 16 |
| sinastria | 518 / 29 / 30 | 465 / 29 / 28 |
| tarot_1 | 820 / 45 / 47 | 745 / 45 / 47 |
| tarot_2 | 353 / 20 / 22 | 353 / 20 / 22 |
| tarot_3 | 1240 / 68 / 70 | 1240 / 68 / 70 |
| tarot_pregunta | 673 / 37 / 38 | 445 / 37 / 38 |
| transitos | 407 / 23 / 24 | 364 / 21 / 21 |
| **TOTAL** | **11986 / 648 / 656** | **10207 / 632 / 641** |

Recuento global: 13290 → **11480** filas.

## Auditoría de v1e (verificación)

Ejecutada con el script de la propia auditoría
(`auditoria_v1d.py --dataset-dir .../dataset_fase1_v1e --salida .../auditoria_v1e --semilla 141`):

| Métrica | v1d | v1e |
|---|---|---|
| Fugas prompt train↔val/test | 274 pares | **0** |
| Fugas respuesta train↔val/test | 1 par | **0** |
| Preguntas corruptas (fuera_alcance) | 398 | **0** |
| Alucinaciones de cálculo (removidas) | 285 | **0** (conservadas: casa 65 + fase 5) |
| Fugas within-split (no bloqueantes) | — | 24 (val↔val 13, test↔test 8, val↔test 3) |
| Par pregunta-respuesta incoherente within-split | — | 67 (0 cruzan train↔val/test) |

QA (`qa_dataset.py --dataset .../v1e --out .../qa_dataset/v1e --semilla 141`):
11480 filas, fuga_eval = 0, fuga_splits = 0; avisos menores de formato
(restos_plantilla 2, id_repetido 2).

Semáforo de entrenamiento (`preparar_entrenamiento.py --dataset .../v1e`):
**VERDE**. Informe: `/Users/angelgonzalez/fase0/dataset_fase1_v1e/preparado/informe_entrenamiento.md`.

**Objetivo cumplido: 0 hallazgos bloqueantes cross-split.**

## Decisiones abiertas (para el usuario / coordinadora)

1. **Markdown (5823 filas):** no se limpió. Decidir si conservar como estilo de
   salida o normalizar a texto plano antes de una futura v1f.
2. **Multiturno real:** el bloque `multiturno` de v1d era falso; reetiquetado a
   `consulta_con_contexto`. Hace falta generar multiturno real si se quiere ese
   formato en el dataset.
3. **Calidad del dedupe (paso 3):** el dedupe por prompt propio exacto es
   agresivo en bloques plantillados: `etica` 281→5 train, `espanola_1` 343→46
   train. La diversidad por prompt único se conserva (la carta sorteada está en
   el prompt), pero si se desea más volumen habría que dedupear por
   (prompt, respuesta) o relajar el criterio. Revisar antes de entrenar.
4. **Paso 1b (fuera_alcance_v2):** pendiente de T136. Cuando exista
   `fuera_alcance_v2.jsonl`, re-ejecutar el script (o pasar
   `--fuera-alcance-v2 <ruta>`) para integrar las aceptadas con reparto 90/5/5.

## Reproducción

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t141-dataset-v1e/finetune/corpus
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python armar_dataset_v1e.py
# defaults: --v1d /Users/angelgonzalez/fase0/dataset_fase1_v1d
#           --out  /Users/angelgonzalez/fase0/dataset_fase1_v1e
#           --fuera-alcance-v2 /Users/angelgonzalez/fase0/fuera_alcance_v2/fuera_alcance_v2.jsonl (opcional)
#           --semilla 141 --n-test 20 --n-val 15

# Regenerar auditoría y QA:
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python auditoria_v1d.py \
  --dataset-dir /Users/angelgonzalez/fase0/dataset_fase1_v1e \
  --salida /Users/angelgonzalez/fase0/auditoria_v1e --semilla 141
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python qa_dataset.py \
  --dataset /Users/angelgonzalez/fase0/dataset_fase1_v1e \
  --out /Users/angelgonzalez/fase0/qa_dataset/v1e --semilla 141
```

Determinismo verificado: dos ejecuciones producen los mismos ficheros (mismo
`resumen.json`, mismos ids en `_cambios/`).
