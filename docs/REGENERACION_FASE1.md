# REGENERACIÓN FASE 1 (T124)

Rama: `track/t124-regenerar-lecturas`. Generador: mercury-3, `--estilo auto`
(temperatura 0.5). Salida: `fase0/fase1_mercury_c/`.

## Resumen

| Métrica | Valor |
|---|---|
| Procesadas | 3.782 |
| Aceptadas | 3.742 (98,9 %) |
| Rechazadas | 40 (1,1 %) |
| Errores de red | 0 |
| Reverificación | 3.742 leídas · 3.742 válidas · 0 inválidas · 0 fugas de evaluación |
| API (latencia acumulada) | 13.263 s ≈ 3,68 h |
| Tokens de salida estimados | ~4,8 M (1282 tokens/lectura, piloto T83) |

Composición: 3.382 candidatas a regenerar (peor 30 % por bloque, 14 familias)
+ 400 transitos NUEVOS semilla 2026. Por bloque aceptadas: tarot_1 281,
tarot_2 120, tarot_3 419, cruz_celta 150, tarot_pregunta 239, astro_natal
431, numerologia 120, lectura_completa 867, multiturno 238, etica 90,
espanola_1 120, espanola_3 270, espanola_5 3, **transitos 394**.

## Selección de candidatas

- `seleccionar_regenerar.py --umbral 2 --fraccion 0.30` sobre el snapshot de
  aceptadas (14.093 = mercury 11.851 + mercury_b 2.242). Nota: `cargar_lecturas`
  solo lee filas ShareGPT, por lo que la selección cubre las 11.851 de
  fase1_mercury; las familias mercury_b (sinastria, revolucion_solar,
  biorritmos, fuera_alcance) quedan fuera (ya generadas con `--estilo auto`).
- Defectos priorizados (pesos T108): apertura_formula 2, frase_plantilla 2,
  esquema_incumplido 2, genero_asumido 1.
- Propuesta: 3.382 lecturas.

## Muestra de 40 y verificación

- 40 jobs (8 familias: tarot_1, tarot_3, cruz_celta, tarot_pregunta,
  astro_natal, lectura_completa, multiturno + 5 transitos nuevos) en
  `/tmp/jobs_t124_muestra.db` → `fase1_mercury_c/muestra/`. **40/40 aceptadas
  (100 %)** ≥ 90 %.
- Calidad antes/después (35 pares localizados por prompt; los 5 transitos
  nuevos no tienen original):
  | defecto | antes | después |
  |---|---|---|
  | lecturas con ≥1 defecto | 97 % | 46 % |
  | defectos totales | 139 | 44 |
  | apertura_formula | 68,6 % | 0 % |
  | frase_plantilla | 20 % | 0 % |
  | muletilla | 42,9 % | 2,9 % |
  | genero_asumido | 40 % | 11,4 % |
  | lista_en_prosa | 34,3 % | 0 % |
  | placeholder_prompt | 28,6 % | 28,6 % (lectura_completa) |
  Regeneración mejora los defectos de estilo/plantilla; el `placeholder_prompt`
  de lectura_completa persiste (defecto conocido).
- Revisión manual de 6 lecturas (tarot_3 id 6, lectura_completa id 26,
  astro_natal id 21, cruz_celta id 11, multiturno id 31, transitos id 38):
  todas de calidad buena/muy buena, español estándar, aperturas variadas y no
  formulaicas, cierres sin muletillas, transitos sin promesas y coherentes.

## AJUSTE: análisis de los transitos descartados en v1c

- Reproducido el filtro exacto de T112 sobre `01_reverificadas/validas.jsonl`
  (12.883): 12.438 mantenidas, 445 descartes. **transitos descartados = 138**
  (todos `fuga_evaluacion_ngramas`).
- Los n-gramas compartidos con los casos eval-transitos-* son **frases fijas
  del esqueleto del prompt de transitos** (p. ej. «en tránsito hace cuadratura
  a su neptuno natal casa 9 orbe 0», «0 3 saturno en tránsito hace sextil a su
  júpiter natal casa»), no fuga de contenido real de evaluación: el prompt de
  transitos las enumera en «Posiciones:» y los casos de evaluación usan el
  mismo generador/redacción → **falsos positivos estructurales**.
- El filtro de boiler (df ≥ BOILERPLATE_DF) no las elimina porque cada
  combinación concreta de aspecto figura en <20 filas, aunque todas comparten el
  mismo patrón de frase.
- **Propuesta (decisión posterior, fuera de T124):** no relajar el filtro
  global. Vía limpia: añadir los n-gramas de esqueleto del prompt de transitos
  a `boiler_extra` en `fugas_eval` (parámetro ya soportado), o aplicar el
  umbral por familia. Los 138 descartados no se recuperan aquí.
- En su lugar, se generaron **400 transitos nuevos** (semilla 2026, distinta de
  la 42 de T113; 0 duplicados con las 387 aceptadas de mercury_b, verificado
  por prompt normalizado). Aceptados: **394**.

## Reverificación

- `reverificar_fase1.py --eval-casos evaluacion_combinada.jsonl` → **3.742
  válidas · 0 inválidas · 0 fugas de evaluación**. Salida:
  `fase1_mercury_c/aceptadas.reverificadas.jsonl`.

## Notas

- No se fusionó al dataset (lo hace T126). No se modificó `fase1_mercury/`,
  `fase1_mercury_b/` ni `jobs.db` (se trabajó sobre copias en `/tmp`).
- Automoción: `seleccionar_regenerar.py`; construcción de conjuntos y muestra en
  `/tmp`; ejecución con `ejecutor_fase1.py --backend mercury --estilo auto`.
