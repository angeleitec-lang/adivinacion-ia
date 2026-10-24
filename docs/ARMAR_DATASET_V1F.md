# ARMAR DATASET v1f (T144)

`finetune/corpus/armar_dataset_v1f.py` construye
`/Users/angelgonzalez/fase0/dataset_fase1_v1f/` a partir de
`dataset_fase1_v1e` sustituyendo los bloques `fuera_alcance`, `etica` y
`espanola_1` por los datos v2 (`fuera_alcance_v2.jsonl` 400 filas,
`etica_espanola1_v2.jsonl` 560 filas), con semilla fija 144.

## Recuentos (antes → después)

| Bloque | v1e | v1f | Detalle v1f (train/val/test) |
|---|---|---|---|
| fuera_alcance | 0 | 400 | 320 / 40 / 40 |
| etica | 22 | 280 | 224 / 28 / 28 |
| espanola_1 | 86 | 278 | 223 / 28 / 27 |
| Total | 11 480 | 12 330 | train 10 923 / val 705 / test 702 |

- Retiradas de v1e: etica 22 (5/3/14), espanola_1 86 (46/20/20),
  fuera_alcance 0 (el paso 1b original nunca se aplicó al construir v1e).
- Reparto 80/10/10 por bloque con `random.Random(144)`; `espanola_1`
  pierde 2 filas por descarte (abajo), de ahí 278 y el 223/28/27.

## Reglas heredadas aplicadas a las filas nuevas

- **System canónico**: único en v1e para los bloques swap
  (sha256 `0970d34db83083acb4c4129f16886444d575ffa581f89b88d4b09a7b6e4a0f0a`).
  Las 960 filas nuevas ya coincidían: 0 normalizadas.
- **Voseo**: 0 descartes (detector `contiene_voseo` de T142).
- **Chino/cirílico**: 0 descartes (rangos Unicode CJK y cirílico).
- **Esquema**: 0 descartes (todas las filas v2 válidas).
- **Fugas/duplicados** (umbrales de `auditoria_v1d`: prompt 0.83,
  respuesta 0.86, hash exacto de prompt propio ≥ 40 chars): 2 descartes,
  ambos nuevo↔nuevo cross-split dentro del fichero etica_espanola1_v2:
  - id 1023 vs 1017 (sim 0.946): misma pregunta de duelo, solo cambia la carta.
  - id 974 vs 1025 (sim 0.837): mismo cinco de espadas, pregunta distinta.
  Se retira siempre la fila nueva de sid mayor, nunca la base de v1e.
  Son prompts de plantilla que inflan la similitud; la regla se aplica tal
  cual la define v1e (mismo detector y umbral), por coherencia.

## Piloto (comprobar_piloto.py, T139) sobre v1f

```
Piloto base=Qwen/Qwen2.5-14B-Instruct max_len=4096 lote=2x8 epocas=3.0
  train: n=10923 invalidas=0 tokens(media/p95/max)=1927.0/3334/5148 exceden=74 (0.68%)
  val: n=705 invalidas=0 tokens(media/p95/max)=1807.5/3273/4446 exceden=4 (0.57%)
  test: n=702 invalidas=0 tokens(media/p95/max)=1835.9/3383/4870 exceden=1 (0.14%)
  pasos: 683/época (lote 16) total=2049
  SEMAFORO: ROJO
    [DEGRADA] 74 filas de train superan max_length=4096
    [DEGRADA] 4 filas de val superan max_length=4096
    [BLOQUEANTE] familias sin ejemplos en test: multiturno
    [DEGRADA] 2 system prompts distintos en train
    [DEGRADA] 446 filas de train sin 'bloque' (sin familia)
```

### Condiciones ROJO

- `multiturno` sin test: **condición conocida, no regresión de v1f**. En
  T141 las filas multiturno se reetiquetaron a `consulta_con_contexto`;
  el piloto sigue esperando la familia `multiturno` en test. Para
  desbloquear hace falta reetiquetar el piloto o generar test multiturno.

### Condiciones ÁMBAR (DEGRADA)

- 74 train / 4 val / 1 test > 4096 tokens: idénticas en v1e (las filas
  nuevas no añaden excedentes). Política de truncamiento pendiente.
- 2 system prompts distintos en train: preexistente en v1e (base tarot vs
  canónico de los bloques swap); v1f no lo introduce.
- 446 filas de train sin `bloque`: preexistente en v1e.

### Mejoras frente al piloto de v1e

- v1e estaba ROJO por **dos** familias sin test (`fuera_alcance` y
  `multiturno`); v1f solo por `multiturno`.
- `etica` en val pasa de 3 a 28 (se va el aviso `val < 10`).

## Semáforo de resumen.json (lógica de v1e)

Con la lógica de `preparar_entrenamiento._problemas_y_semaforo` (la que
dio VERDE a v1e): **verde** (0 errores, 0 avisos). El ROJO del piloto es
una capa distinta (evaluación por familia), no inconsistencia.

## Idempotencia y determinismo

Dos ejecuciones de `construir()` con la misma semilla producen sha256
idénticos de train/val/test y del resumen (verificado en
`tests/test_armar_dataset_v1f.py`, 19 tests).

## Ficheros generados

`train.jsonl`, `val.jsonl`, `test.jsonl`, `resumen.json` y
`_cambios/` (paso1_retirada_bloques_viejos.jsonl,
paso2_integracion_nuevas.jsonl, paso3_descartes.jsonl).
