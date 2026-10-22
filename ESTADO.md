# ESTADO — pista T117 (dataset v1c multi-fuente)

**TRACK COMPLETO** — rama `track/t117-dataset-v1c`, worktree `.worktrees/t117-dataset-v1c`.

Commits locales (git log main..HEAD, sin push):

- `<$HASH1>` — armar_dataset_v1.py: soporte multi-fuente (`--fuente` repetible, snapshot fusionado, huella multi-fuente); humano/resto completo soporta formato plano (prompt_user/respuesta) y ShareGPT; merge_final.py: split_agrupado agrupa por situación Y prompt idéntico (union-find), puerta real case-insensitive; qa_dataset.py: contar_preguntas_basura + test nuevo T117
- `<$HASH2>` — informe docs/ARMAR_DATASET_V1C.md + ESTADO.md

Verificación: suite completa **2493 tests OK** (skipped 1); `./finetune/scripts/check.sh` → **CHECK OK**.

## Qué se hizo

1. **Multi-fuente**: `armar_dataset_v1.py` acepta `--fuente` repetible. El snapshot fusiona todas las fuentes (fase1_mercury 11851 + fase1_mercury_b 2242). La huella de reanudación incluye todas las fuentes.
2. **Residuo (a)**: `merge_final.split_agrupado` agrupa por situación (T112) Y por prompt humano normalizado idéntico (union-find). Garantiza 0 solapes entre splits incluso para prompts idénticos con clave de situación distinta.
3. **Residuo (b)**: puerta real ahora case-insensitive para PLANTILLA_PATRONES → la fila train «asistente de IA» queda descartada (`grep -ic "asistente de ia" train.jsonl` = 0).
4. **Residuo (c)**: `qa_dataset.contar_preguntas_basura` cuenta (no elimina) preguntas basura en fuera_alcance: 120/400 en la fuente (patrón «124 A ver,» etc.).
5. **Bug encontrado durante el run**: `humano_completo`/`respuesta_completa` solo leían `conversations` (ShareGPT). Las filas de mercury_b son planas (`prompt_user`/`respuesta`). Sin el fix, el filtro marcaba ~2020 filas de mercury_b como «duplicado_exacto» falso (toda la fuente colapsaba a la misma clave sha256). Corregido: fallback a `prompt_user`/`respuesta`.

## Resultado v1c

- Salida: `/Users/angelgonzalez/fase0/dataset_fase1_v1c/`
- Filas: train 11563 / val 609 / test 624 (total 12796; v1b era 8131/425/430).
- Bloques: 20 (v1b 15); añadidos sinastria 577, transitos 208, revolucion_solar 398, biorritmos 382, fuera_alcance 398.
- Puerta QA final: **verde** — 0 fugas eval, 0 solapes exactos, 0 casi idénticos, 0 buckets solapados. 2 hallazgos de formato preexistentes (restos_plantilla astro_natal), 1/15 fallo de sanidad en lectura_completa.
- `preparar_entrenamiento`: **semáforo verde** (errores [], avisos [], fugas 0).

## Comando de construcción (v1c)

```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/armar_dataset_v1.py \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl \
  --salida /Users/angelgonzalez/fase0/dataset_fase1_v1c \
  --train-ratio 0.9 --val-ratio 0.05 \
  --real-raw /Users/angelgonzalez/adivinacion-ia/finetune/corpus/raw \
  --manifest /Users/angelgonzalez/adivinacion-ia/finetune/corpus/manifest.json
```

Informe: `docs/ARMAR_DATASET_V1C.md`. Salidas: train/val/test.jsonl, informe.md, `_etapas/qa/{qa_report.json,findings.tsv,resumen.txt}`, `_etapas/fugas_boiler.json`.
