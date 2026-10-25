# Lanzar el piloto 7B QLoRA (T148)

Runbook para poner en marcha el **piloto** del fine-tune QLoRA 4-bit sobre
`Qwen/Qwen2.5-7B-Instruct` con el dataset **v1g** ya preparado. Está escrito
para que lo ejecute alguien sin experiencia previa en el cluster: cada paso dice
**dónde** se ejecuta, **qué comando** se teclea y **qué salida** esperar.

> **Este documento NO entrena nada desde el iMac.** El entrenamiento se hace en
> **nodo1** (10.0.0.3). Desde el iMac solo se prepara el dataset (ya hecho) y
> se copia a nodo1. Nada de este fichero debe lanzarse en el iMac.

> **Modelo: 7B (decisión del usuario 24/10/2026).** Los comandos de
> `docs/PREPARACION_PILOTO.md` §5 hablan de `qlora_14b.yaml`; aquí se usa
> `qlora_7b.yaml`. Si algún texto suelto menciona 14B, ignóralo: el piloto es 7B.

---

## 0. Qué está ya listo (no volver a hacer)

- **Dataset v1g preparado y en SEMÁFORO VERDE** en el iMac:
  `/Users/angelgonzalez/fase0/dataset_fase1_v1g_preparado/`
  (`train.jsonl` 10.909 filas · `val.jsonl` 704 · `test.jsonl` 702 · 12.315 en
  total · 0 duplicados exactos · formato ChatML `{"messages":[{role,content}]}`).
- **Tokenizador real** descargado en
  `/Users/angelgonzalez/fase0/tokenizador_qwen25_7b/` (`tokenizer.json`, etc.).
- **Config** `finetune/entrenamiento/qlora_7b.yaml` apuntando al dataset
  preparado, con las longitudes reales de la cabecera.

No hace falta regenerar nada de esto para lanzar el piloto.

---

## a) Copiar el dataset del iMac a nodo1 (sin credenciales)

El dataset preparado vive en el iMac. Hay que llevarlo a nodo1. **No se copian
contraseñas ni claves**; solo los `.jsonl` y el `estadisticas.json`.

En el **iMac**, por `rsync` (recomendado: reanudable, muestra progreso):

```bash
# Sustituye USUARIO por tu usuario en nodo1 y RUTA_NODO1 por donde quieras ponerlo.
rsync -av --progress \
  /Users/angelgonzalez/fase0/dataset_fase1_v1g_preparado/ \
  USUARIO@10.0.0.3:RUTA_NODO1/dataset_fase1_v1g_preparado/
```

> **Ajusta el YAML.** `qlora_7b.yaml` trae `data.train` con la ruta del iMac.
> En nodo1 hay que apuntarlo a la copia. Dos opciones:
> 1. Editar `data.train` en el YAML de nodo1 a `RUTA_NODO1/dataset_fase1_v1g_preparado/train.jsonl`, o
> 2. Pasar la ruta por CLI en el paso de lanzamiento (`--data ...`).
>
> Anota en `ESTADO.md` la ruta final que uses en nodo1.

**Comprobación tras copiar** (en nodo1):

```bash
wc -l RUTA_NODO1/dataset_fase1_v1g_preparado/*.jsonl
# Esperado: train 10909, val 704, test 702 (más la línea final si la hay).
```

Si los recuentos no cuadran, **para** y vuelve a copiar (copia incompleta).

---

## b) Comprobar el entorno y las claves de Soup (en nodo1)

### b.1 Entorno

```bash
cd <repo en nodo1>
./finetune/entrenamiento/comprobar_entorno.sh
```

Qué mirar en la salida:
- `torch`, `transformers`, `peft`, `bitsandbytes`, `soup`: deben estar
  disponibles. Si `soup` sale como `NO disponible`, **no se puede entrenar**: para.
- `torch.version.hip` con valor (no `None`) → backend ROCm correcto.
- `torch.cuda.is_available(): True` y la **memoria GPU** ≥ 64 GiB.

### b.2 Claves de Soup (CRÍTICO — no verificar desde el iMac)

Las claves del YAML **no** se han comprobado contra la versión de Soup instalada
en nodo1. Antes de lanzar:

```bash
soup --help
# y, si la versión lo documenta, el modo de prueba / dry-run que ofrezca.
```

Confirma **cuatro** cosas y anótalas en `ESTADO.md`:

1. **Claves de datos**: que `train` (y `val` si se usa) existen como claves.
   - El `val.jsonl` preparado **existe** (704 filas). Si Soup acepta una clave
     `val:`, cablea el `val.jsonl` preparado en lugar de `val_split`. Si **no**
     existe la clave, deja `val_split: 0.05` (Soup separa validación del train).
     **No inventes la clave `val:`.**
2. **Máscara de pérdida (solo el asistente)**: la pérdida debe calcularse **solo**
   sobre los turnos del asistente y enmascarar `system` y `human`. Busca la clave
   (p. ej. `train_on_prompt: false` o `mask_user_system: true`). Si no existe,
   comprueba en el log del humo que las pérdidas de system/human **no** suman.
3. **Cuantización NF4**: que se acepten `bnb_4bit_quant_type: nf4`,
   `bnb_4bit_use_double_quant: true`, `bnb_4bit_compute_dtype: bfloat16`. Si no,
   deja los valores por defecto y anótalo.
4. **Checkpointing**: que exista el guardado por pasos (`save_steps`) para poder
   retomar.

> Si una clave del YAML **no existe**, Soup debe **fallar en voz alta**. **No la
> elimines a ciegas**: anota el error exacto en `ESTADO.md` y para.

---

## c) Menú K «plain» en la TUI de nodo1

En la TUI de nodo1, abre el **menú K** y selecciona el modo **«plain»**:
QLoRA denso, **sin MoE y sin visión**. Esto corresponde a `qlora_7b.yaml`
(Qwen2.5-7B-Instruct denso). No elijas MoE ni el checkpoint de visión.

---

## d) Paso de humo (~50 pasos) — OBLIGATORIO

**No** arranques la tanda larga sin humo. Lanza ~50 pasos y mide lo real.

```bash
# Forma prevista (ajusta rutas al paso a). El CLI exacto depende de soup --help.
soup train --config finetune/entrenamiento/qlora_7b.yaml \
          --data RUTA_NODO1/dataset_fase1_v1g_preparado/train.jsonl \
          --output finetune/entrenamiento/salida/7b
```

Detén tras ~50 pasos (`Ctrl-C` limpio) y apunta:

- **tps real** (tokens/segundo) y **pico de memoria** (GiB).
- Comparar con lo **estimado** (ver «Cifras de referencia» abajo):
  - Memoria estimada: **48,3 GB** (rango ±40 % → 29–68 GB).
  - Si el pico real se sale con creces del rango, **no subas batch**: revisa.
- Que la **loss baja** en los primeros 50 pasos (no NaN, no plana).
- Que la máscara de pérdida funciona (paso b.2.2): loss solo del asistente.

Si el humo da NaN, OOM, o la loss no se mueve → **para** (paso g).

---

## e) Una época + evaluación

Tras un humo correcto, lanza **1 época** completa (el piloto es 1 época; la config
trae `epochs: 3`, pero para el piloto basta 1 para tener señal). Al terminar:

### e.1 Generar respuestas del modelo entrenado

Pasa los **30 prompts adversarios** de `docs/PREPARACION_PILOTO.md` §4.1 al
modelo fine-tune (7B) y guarda las respuestas en un `.jsonl`.

### e.2 Comparar contra el modelo base y los umbrales

```bash
# Comparar fine-tune vs base con los casos de evaluación:
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  finetune/corpus/evaluar_modelo.py \
  --casos finetune/corpus/evaluacion_casos.jsonl \
  --comparar <respuestas_base.jsonl> <respuestas_finetune.jsonl> \
  --salida evaluacion_piloto_7b
```

Coteja contra los **umbrales** de `docs/LINEA_BASE_MODELOS.md` y contra las
**métricas deterministas** de `PREPARACION_PILOTO.md` §4.2:
- 100 % español; longitud en rango; 0 predicciones peligrosas en casos 21-30;
  coherencia de cartas; rechazo correcto fuera de alcance.
- El fine-tune **no debe regredir** >5 puntos frente a la base en ninguna métrica.

> Con 30 prompts el IC95 es ancho (~±9 pt/familia): el piloto da **señal
> direccional**, no veredicto estadístico. Para decisión final, los 240 casos de
> `evaluar_modelo.py`.

---

## f) Criterios para seguir o parar

**SEGUIR** (preparar tanda completa / más épocas) si:
- Humo sin NaN/OOM y loss decreciente.
- Memoria real dentro del rango esperado y con margen en los 128 GB.
- En la evaluación 1 época: el fine-tune **mejora o iguala** la base en las
  métricas deterministas y **no regrede** >5 pt.
- Los rechazos fuera de alcance (casos 21-25) y la respuesta a crisis (26-30)
  se comportan como espera el §4.1.

**PARAR** (no escalar, revisar antes) si:
- Regresión >5 pt frente a la base en cualquier métrica.
- Predicciones peligrosas en los casos de salud/muerte/dinero (21-30).
- El modelo «inventa» cartas o palos, o responde en inglés.
- Loss con picos/inestable → bajar `lr` de 2e-4 a 1e-4 y repetir el humo.
- Memoria real muy por encima del rango → bajar `batch_size` a 2 con
  `gradient_accumulation_steps: 8` (mismo lote efectivo 16).

---

## g) Si algo falla

1. **No reinicies a ciegas.** Copia el **mensaje de error exacto** a `ESTADO.md`.
2. Clasifica:
   - `soup: unknown key ...` → clave del YAML no existe en esta versión. Anota la
     clave y el error; no la borres sin confirmar qué espera el CLI.
   - `CUDA/ROCm out of memory` → baja `batch_size` a 2 (accum 8) y repite el humo.
   - `loss = nan` → baja `lr` a 1e-4; si persiste, revisa el dataset (filas
     raras) y la máscara de pérdida.
   - `No existe el Python esperado` en `comprobar_entorno.sh` → exporta `PY` a la
     ruta correcta del venv en nodo1.
3. **Retomar** tras un corte: relanza el mismo comando apuntando `--output` al
   directorio con el último `checkpoint-*` (Soup retoma desde ahí).
4. Nada de esto se resuelve desde el iMac: todo se ejecuta en nodo1.

---

## Cifras de referencia (medidas/recalculadas en el iMac, 24/10/2026)

**Longitudes reales** (tokenizador Qwen2.5 sobre secuencia ChatML de entrenamiento):

| split | filas | media | p50 | p95 | p99 | máx | > 4096 |
|-------|------:|------:|----:|----:|----:|----:|-------:|
| train | 10.909 | 1.977 | 1.701 | 3.463 | 4.063 | 5.243 | 97 (0,89 %) |
| val   | 704 | 1.853 | 1.592 | 3.412 | 4.107 | 4.611 | 8 (1,14 %) |
| test  | 702 | 1.880 | 1.605 | 3.383 | 3.928 | 4.961 | 3 (0,43 %) |

Total > 4096 = 108 / 12.315 = **0,88 %**. El **val supera el 1 %** (1,14 %):
se reporta. `max_length` se **mantiene en 4096** por decisión del usuario.

**Memoria QLoRA 7B @ 4096, batch 4** (estimada, coeficientes ±40 %):
pesos 4,3 + optimizador 0,48 + activaciones 43,6 = **48,3 GB**
(rango 29–68 GB). Cabe en 128 GB con margen ~79,7 GB. **Confirmar el pico real
en el humo (paso d).**

**Horas** (1 época ≈ 21,56 M tokens; rendimiento **NO medido**, rangos
comunitarios de `docs/PLAN_ENTRENAMIENTO.md` §5):

| rendimiento | 1 época | 3 épocas |
|-------------|--------:|---------:|
| 750 tps | ~9,2 h | ~27,6 h |
| 400 tps | ~17,2 h | ~51,7 h |
| 350 tps | ~19,7 h | ~59,0 h |
| 180 tps | ~38,3 h | ~114,8 h |

El **humo (paso d)** es lo que fija el tps real y, con él, las horas.

---

## Advertencias (NO verificado desde el iMac)

- **Claves de Soup** (datos, máscara de pérdida, NF4, checkpointing): **sin
  verificar** contra la versión instalada en nodo1. Obligaratorio `soup --help`
  (paso b.2) antes de lanzar.
- **Rendimiento ROCm gfx1151**: los tps (400-750 / 180-350) son **supuestos
  comunitarios**, no medidos. El humo los confirma.
- **Coeficientes de memoria ±40 %**: el margen es amplio, pero el pico real se
  confirma en el humo antes de subir batch.
- **`val_split` vs `val.jsonl`**: el `val.jsonl` preparado existe pero **no** está
  cableado (la clave `val:` no está verificada). Mientras, `val_split: 0.05`.
- **Multiturno real**: no está en v1g (todas las filas son de un turno); queda
  para **v2**. El piloto no lo evalúa.
