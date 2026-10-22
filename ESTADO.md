# ESTADO — T127 Arreglos de la auditoría ronda 7

Rama: `track/t127-arreglos-ronda7`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t127-arreglos-ronda7`.

## Estado: TRACK COMPLETO

Los 10 puntos de la lista priorizada de `docs/AUDITORIA_RONDA7.md` están
resueltos salvo el 10 (LEVE), que se deja fuera conscientemente. Los 12
`expectedFailure` de `finetune/corpus/tests/test_auditoria_ronda7.py` pasan
como tests normales (0 expected failures) y no se ha aflojado ningún
verificador: los datos no calculados se siguen rechazando.

## Puntos y commits (hashes reales)

- Punto 2 — `18b12fb` — `_verif_sinastria`: aspectos cruzados por longitud,
  posiciones A/B, casas y fechas.
- Punto 3 — `8c1468b` — `_verif_negativa_alcance`: aplica también en
  `familia="etica"` con `tema="fuera_alcance"` y detecta que el texto
  responde la técnica prohibida aunque la nombre solo para rechazarla.
- Punto 4 — `28c4f4e` — `_verif_revolucion`: todos los planetas RS,
  Medio Cielo, Ascendente y fechas/años.
- Punto 5 — `fae66d5` — `_verif_biorritmos`: fases por ciclo, día crítico,
  días hasta el pico, duraciones (23/28/33) y fechas.
- Punto 6 — `5dc58a0` — `_verif_transitos`: posiciones natales y de tránsito,
  casas, retrogradación y fechas; rechaza lo no calculado.
- Punto 7 — `b5584ab` — `merge_final._norm` sin tildes ni puntuación y
  detección de fugas de evaluación reordenadas por oraciones en
  `qa_dataset.fugas_eval`.
- Punto 8 — `eb75b5e` — falsos positivos de fuera de alcance:
  «queda fuera de lo que trabajo» y «numerológica» con tilde.
- Punto 9 — `4bc7f14` — T116: orientación comprobada carta a carta y
  tokenizador con diacríticos portugueses.
- Punto 1 — `541c62c` — `generate_tasks.fuera_alcance`: `islice` en lugar de
  `zip(..., range(n))` (el arranque era el índice) y `pregunta` en el
  payload. Sin regenerar datos; test de regresión en
  `test_generate_tasks.TestFueraAlcance`.

## Punto 10 (no hecho)

LEVE: unificar el tipo de `payload`/`calculos` y documentar el contrato.
Se deja fuera para no tocar la forma de la carta (dict en payload, lista en
`calculos.astro`) sin un consumidor que lo exija; queda anotado como
pendiente menor.

## Verificación

- `test_auditoria_ronda7` + `test_t107_familias_faltantes` +
  `test_fase1_prompts`: 87 tests OK, 0 expected failures.
- `test_generate_tasks`: 49 tests OK.
- `test_traducir_afirmaciones`: 29 tests OK.
- `./finetune/scripts/check.sh` → **CHECK OK** (2578 tests, 1 skipped;
  tests del scraper OK).

No se han regenerado datasets ni se ha tocado `main`. Sin push.
