# ESTADO — T126 dataset v1d (track/t126-dataset-v1d)

## TRACK COMPLETO

Commits en la rama (`git log --oneline main..HEAD`, hashes reales):

- `21f2bbb357542ccd2e4f0c0d95f0cf3dfbcc6472` — T126: reemplazo de originales
  por regeneradas en el snapshot (--reemplazos, --mapear-regeneradas)
  (armar_dataset_v1.py + tests/test_armar_t126.py, 12 tests nuevos).
- `a9b902013fc435bd166a68576878e20aa79bffaa` — T126: informe
  ARMAR_DATASET_V1D (v1d 13290 filas, QA verde, transitos 454).

Base de la rama: a2ce9b9 (main, incluye T124 y T123; tras fast-forward desde
a42687b). Ningún push; todo local.

## Qué se hizo

1. **Reemplazo por tarea/id**: `--reemplazos` aplica un mapa JSONL
   {nuevo(bloque,id) → originales(bloque,id)} en la etapa snapshot; el
   original se elimina y solo queda la regenerada (orden de fuentes
   conservado, colisiones (bloque,id) imposibles). Mapa derivado con
   `--mapear-regeneradas` (fuente nueva → jobs.db de la pasada T124 →
   jobs.db maestro por (bloque, prompt) exacto). Mapa real generado:
   `fase0/t126_reemplazos.jsonl` — 3348 reemplazos, 3442 originales
   eliminados (139 ids extra por prompts maestros duplicados), 394 solo
   nuevas (transitos 2026), 0 sin job. Las 40 rechazadas de T124 no están
   en la fuente de aceptadas → sus originales se conservan, como pedía
   SIGUIENTE.
2. **v1d construido** con puerta QA completa en
   `/Users/angelgonzalez/fase0/dataset_fase1_v1d/` (log:
   /tmp/t126_pipeline.log). **13290 filas** (train 11986 / val 648 / test
   656) vs 12796 en v1c (+494). transitos **454 ≥ 300** ✓. Preparar y QA:
   **semáforo verde** (0 fugas, 0 solapes, 0 casi idénticos, 0 buckets
   solapados; 4 hallazgos de formato: 2 restos_plantilla preexistentes +
   2 id_repetido benignos — ids 342/361 repetidos entre bloques distintos,
   clave (bloque,id) única). Basura fuera_alcance contada: 120/398.
3. **Comparación v1c→v1d** (diversidad_dataset.py y calidad_lecturas.py
   sobre train; artefactos en /tmp/t126_cmp/): mejora en los tres defectos
   pedidos — frase_plantilla 42.1→21.9 %, apertura_formula 30.6→13.2 %,
   cierre_formula 16.8→10.0 %; TTR 0.0045→0.0048, únicas 6g 0.806→0.824,
   muletillas 6g 16→4. Empeoran levemente esquema_incumplido y
   placeholder_prompt (<2,5 pt). Tablas por bloque en el informe.
4. **Tokens/horas (T111)**: train 22.741.075 tokens; p99 3993 → max_seq_len
   4096 sigue válido (trunca 81 filas, 0,121 % tokens). 7B 3 épocas
   ≈25–48 h; 14B 3 épocas ≈54–105 h.
5. **Informe** `docs/ARMAR_DATASET_V1D.md` con comandos exactos (mapeo y
   cadena).
6. **Verificación**: suites armar 43 OK; `./finetune/scripts/check.sh` →
   **CHECK OK**.

## Notas para la coordinadora

- Ficheros tocados: `finetune/corpus/armar_dataset_v1.py`,
  `finetune/corpus/tests/test_armar_t126.py` (nuevo),
  `docs/ARMAR_DATASET_V1D.md` (nuevo). No se tocaron qa_dataset.py,
  merge_final.py ni las fuentes/datasets anteriores (solo lectura).
- Dependencia externa: el mapa usa `/tmp/jobs_t124_final.db` (BD de tareas
  de la pasada T124). Si se pierde, rehacerla antes de re-mapear (nota en
  el informe §7).
- mercury_c son filas planas re-renderizadas con plantilla nueva: el prompt
  NUNCA coincide literalmente con el de mercury (maestro); el emparejamiento
  va por job→maestro, no por texto — por eso existe `--mapear-regeneradas`.
