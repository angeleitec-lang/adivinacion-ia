# ESTADO — T146 dataset v1g (opencode, worktree t146-dataset-v1g)

Rama: `track/t146-dataset-v1g` (verificada con `git branch --show-current`).

## Resultado

Dataset v1g construido en `/Users/angelgonzalez/fase0/dataset_fase1_v1g/`
a partir de v1f (solo lectura). 12330 → 12315 filas (−15 por voseo).

- Splits: train 10909 / val 704 / test 702.
- Retiradas voseo (15): lectura_completa 4, transitos 3+1 val, tarot_3 2,
  astro_natal 1, cruz_celta 1, revolucion_solar 1, sin_bloque 1, tarot_2 1.
  Detalle en `_cambios/voseo_retiradas.jsonl`.
- Sin bloque: 486 (445/25/16). No inferibles de forma segura (explicadores
  multi-tema, muchos fuera de alcance) → documentados, no reetiquetados.
- Tokens >4096: train 74 / val 4 / test 1 (idéntico a v1f; ninguna fila
  retirada excedía). Decisión: NO recortar; política de truncamiento sigue
  pendiente como en v1f.
- Semáforo resumen.json (lógica v1e): VERDE. Piloto: ROJO por las mismas
  causas preexistentes de v1f (multiturno sin test, 2 system prompts,
  excedentes, sin bloque) — ninguna empeora.
- sha256 reales: train `d60d8144958c9cdb3f986d1775330a4d40e609b3247d0d6452af8e3b1af730ae`,
  val `06913cfa3f6739b31915aba8bb0e4d413f6ebef03099f3d06b8ebbd877845cd7`,
  test `0803b1c75b120fce4635862fcf2010309d2a73534a7acec1081b3545fbebd67f`.

## Diferencia con la estimación de la coordinadora

Se estimaban 12 filas de voseo; la verificación fila a fila da **15**
(extras: train#5556, train#7415, train#5427 — voseo inequívoco sin
marcador de vosotros). De las 31 que casan `RE_VOSEO`: 15 retiradas,
16 conservadas (vosotros peninsular legítimo + falsos positivos `elegí`
pretérito y `Tomás de Aquino`).

## Commits (git log main..HEAD)

- `c4745db688ad14ec676b678f868955a2787a74cb` — armar_dataset_v1g.py + tests (17 tests OK)
- `41cc15d4f39a8c01ea930a76f7723d4d3b46103d` — docs/ARMAR_DATASET_V1G.md (piloto, comparación v1f→v1g)

## Verificación

- `tests/test_armar_dataset_v1g.py`: 17 tests OK (incluye determinismo
  dos ejecuciones mismo sha256, no fuga train→val/test, falsos positivos
  más/estás/además/a través, elegí/Tomás, ambiguo con/sin marcador).
- `comprobar_piloto.py --dataset .../dataset_fase1_v1g`: ejecutado, tabla
  pegada en docs/ARMAR_DATASET_V1G.md.
- `./finetune/scripts/check.sh`: **CHECK OK**.
- v1f intacto (solo lectura); `armar_dataset_v1e.py`/`v1f.py` sin modificar.

TRACK COMPLETO
