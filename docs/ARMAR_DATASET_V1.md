# ARMAR_DATASET_V1 (T103) — de las lecturas de Mercury al dataset de entrenamiento en un solo comando

## Qué hace

`finetune/corpus/armar_dataset_v1.py` encadena, con salvaguardas y **reanudación**,
todo el camino desde las lecturas reales generadas por Mercury
(`/Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl`) hasta el dataset de
entrenamiento en `/Users/angelgonzalez/fase0/dataset_fase1_v1/`:

| # | Etapa | Qué hace | Ficheros |
|---|-------|----------|----------|
| a | `snapshot` | Copia instantánea de `aceptadas.jsonl` (la generación sigue escribiendo en origen; aquí solo se lee una vez). Guarda `.sha256`. | `00_snapshot/` |
| b | `reverificar` | `reverificar_fase1` con el verificador vigente (T101/T101b/T101c): separa inválidas con motivo. | `01_reverificadas/` |
| c | `filtro` | Fuga de evaluación por **id** (`eval-…`/`origen=evaluacion`) y por **contenido normalizado** contra los casos de las semillas reservadas 560056-560058; duplicados exactos y casi duplicados (MinHash Jaccard ≥ 0,9) **dentro de cada familia**. Hasta 10 ejemplos por motivo. | `02_filtradas/` |
| d | `sharegpt` | Adaptación a ShareGPT reutilizando `ejecutor_fase1.a_sharegpt` (identidad NFC si la fila ya trae `conversations`), conservando `bloque`, `id`, `generador` y `calculos`. | `03_sharegpt/` |
| e | `validar` | `validate_synthetic` con parámetros de producción (min 400 / max 12000 chars, repetición ≤ 0,12). | `04_validacion/` |
| f | `fusion` | `build_dataset` sobre el corpus real de fase 0 (solo lectura) + `merge_final` → `train/val/test`. El test del dataset **no** es el conjunto de evaluación T56. | `real/`, `train.jsonl`, `val.jsonl`, `test.jsonl`, `report.json` |
| g | `preparar` | `preparar_entrenamiento` con informe y semáforo; **rojo = parada** (excepción registrada). | `preparado/` |

## Reanudación y parada

Cada etapa deja su entrada en `_etapas/registro.jsonl` con una **huella**
(sha256 de ficheros de entrada + parámetros). Al relanzar:

- etapa `completada` con la misma huella → **se omite**;
- etapa `fallida` o huella distinta (entrada nueva) → **se vuelve a correr** ella y
  todo lo posterior;
- cualquier excepción → se registra `fallida` y el proceso **para** (rc 1).

Los casos de evaluación de las 3 semillas reservadas se generan **una vez y se
congelan** en `_etapas/eval/` (huella solo por semillas). Se producen en dos
formatos: `evaluacion_sharegpt.jsonl` (para reverificar/filtro/build_dataset/
merge_final, que leen `conversations`) y `evaluacion_combinada.jsonl` (formato
original con `user`, para `preparar_entrenamiento.detectar_fugas`).

## Uso

Producción (repite el mismo comando cuando acabe la generación; la huella de la
entrada habrá cambiado y la cadena vuelve a correr completa sobre la copia nueva):

```bash
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  finetune/corpus/armar_dataset_v1.py \
  --real-raw /Users/angelgonzalez/adivinacion-ia/finetune/corpus/raw \
  --manifest /Users/angelgonzalez/adivinacion-ia/finetune/corpus/manifest.json
```

Opciones: `--entrada`, `--salida`, `--real-raw`, `--manifest`, `--semilla` (42),
`--min-chars` (400), `--max-chars` (12000), `--max-repetition` (0,12),
`--train-ratio` (0,8), `--val-ratio` (0,1).

Garantías: sin red ni claves; la entrada (`fase1_mercury/`) **nunca se modifica**
(se trabaja sobre la copia instantánea); no toca `corpus/final` ni `jobs.db`.

## Informe

`dataset_fase1_v1/informe.md` (regenerado al final de cada pasada) incluye: filas
por split/familia/generador, longitud en chars y tokens estimados (chars/4),
multiturno, distribución de cartas (cobertura de las 78 de tarot y los 40 naipes
españoles, orientaciones), éticos y fuera de alcance, descartes por etapa con
recuentos y hasta 10 ejemplos por motivo, y proporción final por familia frente a
los objetivos de `generate_tasks.TARGETS`.

## Tests

`finetune/corpus/tests/test_armar_dataset_v1.py` (unittest, 12 casos): fuga por
contenido y por id detectadas y excluidas del dataset final, duplicados exactos y
casi duplicados por familia (otra familia se conserva), reanudación (segunda pasada
omite todo y no reescribe salidas), cambio de entrada vuelve a correr, parada ante
etapa rota (`fallida` registrada, etapas posteriores no se ejecutan) y
reanudación tras arreglar, entrada invariable, y `adaptar_sharegpt`
(identidad/plano).
