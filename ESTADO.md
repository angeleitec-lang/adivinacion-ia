# ESTADO — T124 Regenerar lecturas más flojas con Mercury

Rama: `track/t124-regenerar-lecturas`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t124-regenerar-lecturas`.

## Estado: TRACK COMPLETO

Muestra de 40 → 40/40 aceptadas (100 %). Calidad antes/después (35 pares
localizados): lecturas con ≥1 defecto 97 % → 46 %; defectos totales 139 → 44.
apertura_formula 68,6 % → 0 %; frase_plantilla 20 % → 0 %; muletilla 42,9 %
→ 2,9 %; genero_asumido 40 % → 11,4 %. Criterio de lanzamiento cumplido
(aprobación verificador 100 % ≥ 90 % y mejora) → pasada completa lanzada.

Pasada completa finalizada: 3.782 procesadas → 3.742 aceptadas (98,9 %), 40
rechazadas (1,1 %), 0 errores de red. Reverificación: 3.742 válidas · 0
inválidas · 0 fugas de evaluación. Salida `fase0/fase1_mercury_c/`
(aceptadas.reverificadas.jsonl). Informe `docs/REGENERACION_FASE1.md`.
`./finetune/scripts/check.sh` → **CHECK OK**.

## AJUSTE paso 1 — Análisis transitos descartados (COMPLETADO)

Reproducido el filtro exacto de T112 (`filtrar_fugas_eval` sobre
`01_reverificadas/validas.jsonl`, 12883 filas): 12438 mantenidas, 445
descartes, boiler 2037. transitos descartados = **138** (no 139), todos
`fuga_evaluacion_ngramas` (5–13 n-gramas compartidos con casos eval-transitos-*).

Hallazgo clave: los n-gramas compartidos son **frases fijas del esqueleto del
prompt de transitos** (no fugas de contenido real). Ejemplos legibles:
«en tránsito hace cuadratura a su neptuno natal casa 9 orbe 0», «0 3 saturno
en tránsito hace sextil a su júpiter natal casa». El prompt de transitos las
enumera en «Posiciones:», y los casos de evaluación usan el mismo generador y
la misma redacción → falsos positivos estructurales. El filtro de boiler
(df ≥ BOILERPLATE_DF) no las elimina porque cada combinación concreta de
aspecto figura en <20 filas, aunque todas comparten el mismo patrón de frase.

Conclusión / propuesta para el informe (decisión posterior, fuera de T124):
los descartes de transitos son **falsos positivos por plantilla del prompt**,
no por solape con respuestas de evaluación. No relajar el filtro global; la
vía limpia sería añadir los n-gramas de esqueleto del prompt de transitos a
`boiler_extra` en `fugas_eval` (ya soportado), o aplicar el umbral por familia.
Los 138 no se recuperan en T124.

Método de verificación: `/tmp/t124_analisis_transitos.py` y
`/tmp/t124_gramas_compartidos.py`.

## Construcción del conjunto de tareas (pasos 1 y AJUSTE 2)

- Selección: `seleccionar_regenerar.py --in <snapshot> --umbral 2 --fraccion 0.30`
  sobre `/tmp/aceptadas_snapshot_v1c.jsonl` (mercury 11851 + mercury_b 2242).
  Nota: `cargar_lecturas` solo lee filas ShareGPT, así que la selección cubre
  las 11851 de fase1_mercury (mercury_b planas quedan fuera). Propuesta: 3382
  lecturas (14 familias).
- `jobs.db` maestra copiada → `/tmp/jobs_t124.db`; las 3382 candidatas ya
  estaban `pending` (la maestra nunca se ejecutó para ellas).
- transitos NUEVOS: `generate_tasks.py --db /tmp/jobs_t124.db --seed 2026
  --only transitos` → 400 (0 duplicados con las 387 aceptadas de mercury_b,
  verificado por prompt normalizado).
- BD final de pasada: `/tmp/jobs_t124_final.db` = 3382 candidatas + 400
  transitos = **3782** jobs, todos pending.
- Muestra de 40 (8 familias, incl. 5 transitos nuevos):
  `/tmp/jobs_t124_muestra.db` → salida `fase0/fase1_mercury_c/muestra/`
  (40/40 aceptadas).

## Pasada completa (COMPLETADA)

- BD `/tmp/jobs_t124_final.db` (3782), backend mercury, `--estilo auto`,
  `--workers 3`, salida `fase0/fase1_mercury_c/`.
- Resultado: 3782 procesadas → 3742 aceptadas, 40 rechazadas, 0 errores de
  red. Reverificación 3742 válidas / 0 inválidas / 0 fugas.

## Commits (git log main..HEAD)

- `e04f629` T124: ESTADO TRACK COMPLETO con hashes
- `9e40dad` T124: informe de regeneración fase 1 + ESTADO

## Pendiente

Ninguno. TRACK COMPLETO.
