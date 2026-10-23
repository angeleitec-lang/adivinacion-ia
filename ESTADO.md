# ESTADO — T141 dataset v1e

Rama: `track/t141-dataset-v1e` (verificada con `git branch --show-current`).

## Commits (hashes reales, `git log main..HEAD`)

- `c1eb6c2` T141: armar_dataset_v1e con 7 pasos deterministas (semilla 141) + tests adversos
- `d2386cb` T141: paso2 al final (boiler depende de val/test definitivo) + fuga por prompt exacto cross-split + paso6 con reparacion iterativa
- (pendiente en este commit final: docs/ARMAR_DATASET_V1E.md + ESTADO)

## Qué se hizo

1. **Script** `finetune/corpus/armar_dataset_v1e.py`: 7 pasos deterministas
   (semilla 141, sin LLM, sin nodos) sobre v1d (13290 filas) → v1e (11480).
   Orden efectivo 1→3→4→5→6→2 (el detector de fugas depende de la composición
   definitiva de val/test). Registro por paso en `_cambios/*.jsonl` y
   `resumen.json`.
2. **Paso 1**: retiradas las 398 filas corruptas de `fuera_alcance`
   (detector de la auditoría, 398/398). Paso 1b OMITIDO:
   `fuera_alcance_v2.jsonl` no existe (T136 incompleto); reanudable con
   `--fuera-alcance-v2 <ruta>` (reparto 90/5/5).
3. **Paso 2**: 77 filas train retiradas por fuga cross-split (similitud de
   prompt, similitud de respuesta —incluido el par train#3780↔test#0— y
   prompt exacto cross-split oculto por boilerplate).
4. **Paso 3**: dedupe train mismo prompt → 1075 retiradas (se conserva la fila
   sin banderas de expurgo; si todas limpias, id menor).
5. **Paso 4**: 260 retiradas por alucinación de cálculo en todos los splits
   (signo_no_calculado 41, numero_numerologia_incorrecto 25,
   aspecto_no_calculado 194). Conservadas y listadas casa_no_calculada (65) y
   fase_biorritmo_incorrecta (5) en `_cambios/paso4_conservadas.jsonl`.
6. **Paso 5**: 472 filas `multiturno` (monoturno falso) reetiquetadas a
   `consulta_con_contexto`, id conservado, bloque original en `bloque_origen`.
7. **Paso 6**: numerología 20 movidas a test y 15 a val con bucle de reparación
   anti-fuga → 269/28/20.
8. **Paso 7**: markdown NO se cambia; 5823 filas con markdown (informativo).
9. **Auditoría v1e** (`auditoria_v1d.py --semilla 141`): 0 fugas
   train↔val/test (prompt y respuesta), 0 preguntas corruptas, 0 alucinaciones
   removidas. Within-split no bloqueante: 24 pares prompt, 67 pares
   pregunta-respuesta (0 cruzan train↔val/test).
10. **QA + semáforo**: `qa_dataset.py` fuga_eval=0, fuga_splits=0 (avisos
    menores: restos_plantilla 2, id_repetido 2). `preparar_entrenamiento.py`:
    **VERDE**.
11. **Tests**: `finetune/corpus/tests/test_armar_dataset_v1e.py` — 19 OK.
    Adversos: par con fuga train↔val, 3 respuestas al mismo prompt (limpia con
    bandera gana la limpia), fila con bandera de expurgo, split sin numerología,
    fuera_alcance_v2 presente (reparto 90/5/5), determinismo doble pasada.
12. **check.sh**: `CHECK OK`.

## Decisiones abiertas (ver docs/ARMAR_DATASET_V1E.md §Decisiones abiertas)

- Markdown 5823 filas sin limpiar (decisión de estilo de salida).
- Multiturno real pendiente de generar.
- Calidad del dedupe: etica 281→5 y espanola_1 343→46 en train (bloques
  plantillados); revisar criterio antes de entrenar.
- Paso 1b pendiente de T136 (fuera_alcance_v2).

TRACK COMPLETO
