# Plan de entrenamiento (fase 2) — T111

Plan de ejecución del fine-tune con los datos reales del dataset v1 parcial.
Complementa `finetune/GUIA_REENTRENAMIENTO.md` (cómo) y
`docs/LINEA_BASE_MODELOS.md` (umbrales). Ninguna cifra de rendimiento está
medida en nodo1/nodo2: son estimaciones documentadas. Recalcular con:

```
python finetune/entrenamiento/ajuste_config.py --dataset <carpeta-dataset>
```

## 1. Datos reales del dataset v1 (parcial)

Estimación caracteres/3,5 (sin tokenizador local en el iMac). TRAIN 5.205
filas, VAL 578, TEST 582.

| Split | p50 | p95 | p99 | máx | media |
|---|---|---|---|---|---|
| train | 1.510 | 3.233 | 3.869 | 4.166 | 1.611 |
| val | 1.634 | 3.154 | 3.912 | 4.111 | — |
| test | 1.626 | 3.098 | 3.832 | 4.107 | — |

- Total ~8,38 M tokens por época (8.384.298 recortado a 4096).
- Familia más larga: `astro_natal` (p99 4.131, máx 4.166).
- Truncando a 4096: 10 filas afectadas (0,19 %) y <0,01 % de tokens
  perdidos. A 2048 (valor anterior) se truncaría ~15 % de las filas.
  6144/8192 no aportan: ninguna fila los alcanza.

**Decisión T111: `max_seq_len = 4096`** (cubre ≥99,8 % sin truncar, con
margen para el solape ChatML de ~15 tokens por fila).

## 2. Configuración de entrenamiento

| Parámetro | 7B (iteración) | 14B (modelo final) |
|---|---|---|
| max_length | 4096 | 4096 |
| batch × accum (efectivo) | 4 × 4 = 16 | 2 × 8 = 16 |
| LoRA r / alpha | 16 / 32 | 32 / 64 |
| lr | 2e-4 | 1e-4 |
| Memoria est. (QLoRA 4-bit, checkpointing) | ~44 GB (±40 %) | ~48 GB (±40 %) |
| Margen en 128 GB unificados | ≥66 GB | ≥60 GB |
| Horas 1 época @550/250 tps | ~5 h | ~11 h |
| Horas 3 épocas (rango 400-750 / 180-350 tps) | ~10,7-20,1 h | ~23,0-44,6 h |

La pérdida debe calcularse **solo sobre los turnos del asistente** (mask de
system y human). En Soup la clave exacta NO está verificada: comprobar con
`soup --help` antes de la primera tanda (ver comentario en los YAML).

## 3. Orden de ejecución (nodo1, cuando quede libre)

0. **Prerrequisitos**: revisión humana del 3 % del dataset cerrada;
   `preparar_entrenamiento.py` en verde; `soup --help` verificado en la
   versión instalada (claves de este repo y máscara de pérdida).
1. **Humo (7B, ~50 pasos)**: validar pipeline completo — carga de datos,
   máscara de pérdida en el log, uso de memoria real, tps real, sin NaN.
   Con el tps medido aquí se recalculan las horas de los pasos 2-4.
2. **7B, 1 época (~5 h)**: evaluar con `finetune/corpus/evaluar_modelo.py`
   contra la línea base (`docs/LINEA_BASE_MODELOS.md`). Criterio para
   seguir: mejora sin regresión en familias de seguridad.
3. **7B, 3 épocas (~10-20 h)**: solo si el paso 2 cumple. Evaluar de
   nuevo; comparar 1 vs 3 épocas (sobreajuste: val loss sube).
4. **14B, tanda final (~23-45 h)**: solo si el 7B demuestra que receta y
   datos funcionan (regla de MODELO.md). Evaluar y decidir despliegue.

## 4. Criterios de aceptación (de LINEA_BASE_MODELOS.md)

| Familia | Umbral | Familia | Umbral |
|---|---|---|---|
| baraja_3 | 1,00 | tarot_10 | 0,95 |
| fuera_alcance | 1,00 | revolucion_solar | 0,90 |
| etica | 1,00 | sinastria | 0,90 |
| tarot_1 | 0,95 | astro_natal | 0,85 |
| tarot_3 | 0,95 | transitos | 0,75 |
| numerologia | 0,95 | biorritmos | 0,90 |

**Compuerta global**: ≥ 0,92 de media ponderada y ninguna familia de
seguridad (`fuera_alcance`, `etica`, `baraja`) por debajo de su umbral.
Si `transitos`/`astro_natal` no alcanzan su umbral, el fine-tune se revisa
antes de desplegar aunque el global pase. Medir a temperatura 0,7.

## 5. Riesgos conocidos

- **Fuente única generadora**: gran parte del dataset sintético sale de los
  mismos prompts; riesgo de estilo repetitivo y de aprender fraseos del
  generador en lugar de conocimiento (ver `docs/CALIDAD_LECTURAS.md` y
  `docs/DIVERSIDAD_DATASET.md`).
- **Familias aún sin generar o incompletas**: multiturno, sinastría, ética,
  baraja española y las 4 técnicas nuevas de T107. Sin ellas no se pueden
  medir sus umbrales; la compuerta de seguridad queda coja.
- **Rendimiento ROCm gfx1151 no medido**: los rangos de tps (400-750 /
  180-350) son supuestos comunitarios; el paso 1 (humo) es obligatorio
  antes de comprometer tandas largas.
- **Claves de Soup sin verificar contra la versión instalada**: si alguna
  clave de los YAML no existe, Soup debe fallar en voz alta; no eliminarla
  a ciegas.
- **Coeficientes de memoria ±40 %**: el margen en 128 GB es amplio, pero
  el humo debe confirmar el pico real antes de subir batch.

## 6. Qué falta antes de entrenar

1. Cerrar la revisión humana del 3 % del dataset v1.
2. Generar las familias que faltan (multiturno, sinastría, ética, baraja
   española, técnicas T107) y pasar el validador + semáforo de
   `preparar_entrenamiento.py`.
3. Verificar `soup --help` en nodo1: claves de datos, máscara de pérdida,
   cuantización NF4 y checkpointing.
4. Recalcular longitudes con el tokenizador real (Qwen2.5) sobre el
   dataset final: confirmar que 4096 sigue cubriendo ≥99,8 %.
5. Paso de humo de 50 pasos y medición de tps/memoria reales.
