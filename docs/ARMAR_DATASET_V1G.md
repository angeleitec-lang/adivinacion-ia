# Dataset v1g — limpieza de voseo, informe sin bloque y recuento de tokens

Generado por `finetune/corpus/armar_dataset_v1g.py` (T146) a partir de
`/Users/angelgonzalez/fase0/dataset_fase1_v1f/` (solo lectura). Salida:
`/Users/angelgonzalez/fase0/dataset_fase1_v1g/` con el mismo formato
(`train/val/test.jsonl`, `resumen.json`, `_cambios/`).

## Cambios respecto a v1f

Solo se **retiran** filas; no se reescribe ni se añade ninguna. 12330 →
12315 (−15).

### 1. Voseo (15 retiradas)

Detector determinista sobre las formas de `RE_VOSEO`
(`regenerar_fuera_alcance.py`), con reglas para no matar falsos positivos:

- Formas ambiguas con `vosotros` peninsular (`sentís, vivís, seguís, venís,
  pedís, dormís, abrís, escribís, compartís, recibís, preferís`) **no**
  disparan si la fila contiene marcador de vosotros (`os`, `vosotros`,
  `estáis`, `tenéis`, `ambos/ambas`, `dais`).
- `elegí`/`escribí` (pretérito 1.ª persona) nunca disparan solos.
- `Tomás` se ignora cuando es nombre propio (`\bTomás de\b`).
- El resto de formas (`vos`, `necesitás`, `podés`, `querés`, `tenés`,
  imperativos `mirá/hablá/poné`, etc.) es voseo inequívoco y dispara aunque
  haya marcador de vosotros (filas mixtas mal generadas).

De las 31 filas que casan con `RE_VOSEO` en v1f: **15 retiradas** (voseo
real o mixto) y **16 conservadas** (vosotros peninsular legítimo o falsos
positivos: `porque la elegí`, `Tomás de Aquino`). Retiradas por bloque:
`lectura_completa` 4, `transitos` 3+1 val, `tarot_3` 2, y 1 cada una de
`astro_natal`, `cruz_celta`, `revolucion_solar`, `sin_bloque`, `tarot_2`.
Listado completo con id/bloque/forma/fragmento en
`_cambios/voseo_retiradas.jsonl`.

**Discrepancia con la estimación de la coordinadora**: se estimaban 12 filas
a retirar; la verificación fila a fila (2026-10-24) da 15. Las 3
adicionales (`train#5556`, `train#7415`, `train#5427`) son voseo
inequívoco (`buscás/podés/necesitás`, `ponés`, `te sentís` sin marcador
de vosotros). Ninguna de las 12 iniciales se reclasificó: las 15 incluyen
las 12 + 3.

### 2. Filas sin bloque (486) — no inferibles, se documentan

Quedan 445 train / 25 val / 16 test = 486 (en v1f eran 487; se retiró
`train#9441` por voseo). Todas comparten el system prompt genérico de
corpus real y son explicadores multi-tema (`Háblame de runas`, `Explica:
línea del corazón`, `Las Nubes (I Ching)`…), muchos de ellos **fuera del
alcance** del modelo (quiromancia, runas, I Ching). No existe regla
determinista segura para asignarles un bloque existente sin inventar, así
que se dejan sin bloque y se reportan con recuentos y ejemplos en
`_cambios/sin_bloque_informe.json`.

### 3. Tokens > 4096 — recuento, sin recorte

Recuento por split con la estimación del piloto (chars/3.5, config
`qlora_14b.yaml`, max_length=4096): train 74, val 4, test 1 — idéntico a
v1f: **ninguna fila retirada por voseo excedía el límite**, la limpieza no
agrava ni mejora los excedentes. No se recorta ninguna fila: recortar
dentro de una respuesta degrada la señal de entrenamiento y ninguna de las
instrucciones pedía truncar; la política de truncamiento sigue pendiente
como en v1f. Detalle por split en `_cambios/tokens_exceden_informe.json`.

## Piloto (comprobar_piloto.py, T139) sobre v1g

```
Piloto base=Qwen/Qwen2.5-14B-Instruct max_len=4096 lote=2x8 epocas=3.0
  train: n=10909 invalidas=0 tokens(media/p95/max)=1926.4/3336/5148 exceden=74 (0.68%)
  val: n=704 invalidas=0 tokens(media/p95/max)=1805.8/3273/4446 exceden=4 (0.57%)
  test: n=702 invalidas=0 tokens(media/p95/max)=1835.9/3383/4870 exceden=1 (0.14%)
  pasos: 682/época (lote 16) total=2046
  SEMAFORO: ROJO
    [DEGRADA] 74 filas de train superan max_length=4096
    [DEGRADA] 4 filas de val superan max_length=4096
    [BLOQUEANTE] familias sin ejemplos en test: multiturno
    [DEGRADA] 2 system prompts distintos en train
    [DEGRADA] 445 filas de train sin 'bloque' (sin familia)
```

### Comparación v1f → v1g (piloto)

| Métrica | v1f | v1g | Δ |
|---|---|---|---|
| train n | 10923 | 10909 | −14 |
| val n | 705 | 704 | −1 |
| test n | 702 | 702 | 0 |
| exceden >4096 (train/val/test) | 74/4/1 | 74/4/1 | 0 |
| media tokens train | 1927.0 | 1926.4 | −0.6 |
| filas sin bloque train | 446 | 445 | −1 |
| pasos total (3 épocas) | 2049 | 2046 | −3 |

Ninguna condición del piloto empeora. El ROJO es idéntico al de v1f y por
las mismas causas preexistentes (no regresión de v1g):

- `multiturno` sin test: condición conocida desde T141 (reetiquetado a
  `consulta_con_contexto`); el piloto sigue esperando la familia.
- 2 system prompts distintos en train: preexistente (base tarot vs
  canónico de los bloques swap).
- Excedentes de tokens y filas sin bloque: documentados arriba.

## Semáforo de resumen.json (lógica de v1e)

Con la lógica de `preparar_entrenamiento._problemas_y_semaforo` (la que
dio VERDE a v1e/v1f): **verde** (0 errores, 0 avisos). El ROJO del piloto
es una capa distinta (evaluación por familia), no inconsistencia.

## Idempotencia y determinismo

Dos ejecuciones de `construir()` producen sha256 idénticos de
train/val/test y de los informes (verificado en
`tests/test_armar_dataset_v1g.py`, 17 tests). sha256 de la construcción
real: train `d60d8144…`, val `06913cfa…`, test `0803b1c7…`.

## Tests adversos cubiertos

- Falsos positivos de tuteo: `más`, `además`, `estás`, `detrás`,
  `interés`, `a través`, `después`, `quizás` no disparan.
- `elegí` pretérito y `Tomás de Aquino` no disparan.
- Ambiguo sin marcador de vosotros → voseo; con marcador → conservado.
- Determinismo: dos ejecuciones, mismo sha256.
- No fuga train→val/test tras retirar filas (detector de `auditoria_v1d`).

## Ficheros generados

`train.jsonl`, `val.jsonl`, `test.jsonl`, `resumen.json` y
`_cambios/` (voseo_retiradas.jsonl, sin_bloque_informe.json,
tokens_exceden_informe.json).
