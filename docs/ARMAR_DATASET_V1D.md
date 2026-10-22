# ARMAR_DATASET_V1D — Dataset de fase 1 v1d

Track **T126**. Construye `fase0/dataset_fase1_v1d/` a partir de **tres
fuentes**: `fase1_mercury` (aceptadas.jsonl, 11851 filas, T100),
`fase1_mercury_b` (aceptadas.reverificadas.jsonl, 2242 filas, T113) y
`fase1_mercury_c` (aceptadas.reverificadas.jsonl, 3742 filas, T124). Novedad:
las lecturas **regeneradas reemplazan** a las originales que sustituyen
(misma tarea `id`) en el snapshot, con mapa derivado de las BD de tareas;
el resto de la cadena es idéntica a v1c (reverificar → filtrar fugas →
sharegpt → validate_synthetic → build_dataset → merge_final →
preparar_entrenamiento → QA gate).

## 0. Reemplazos (T124 → originales)

Mapa `fase0/t126_reemplazos.jsonl` generado con `--mapear-regeneradas`:
une cada fila de mercury_c con el job de su pasada (`/tmp/jobs_t124_final.db`)
y, por (bloque, prompt) exacto, con los ids del maestro `corpus/jobs.db`.

- filas nueva fuente: 3742 · reemplazos: 3348 · originales eliminados: 3442
  (139 prompts del maestro tenían varios ids: 3487 referencias → 3442 claves
  únicas) · solo nuevas (transitos 2026): 394 · sin job: 0.
- Las 34 candidatas + 6 transitos rechazadas en T124 no están en la fuente de
  aceptadas, así que sus originales **se conservan** (no hay reemplazo que
  aplicar) — comportamiento pedido en SIGUIENTE.
- Verificación: 0 originales ausentes, 0 colisiones (bloque,id) entre
  originales y nuevas; el snapshot baja de 17835 concatenadas a 14393.

## 1. Filas por bloque y split

Total: **13290** filas (train 11986 / val 648 / test 656).

| bloque | train | val | test | total |
|---|---:|---:|---:|---:|
| lectura_completa | 1765 | 99 | 100 | 1964 |
| astro_natal | 1332 | 69 | 73 | 1474 |
| tarot_3 | 1240 | 68 | 70 | 1378 |
| tarot_1 | 820 | 45 | 47 | 912 |
| espanola_3 | 799 | 45 | 45 | 889 |
| tarot_pregunta | 673 | 37 | 38 | 748 |
| multiturno | 654 | 37 | 37 | 728 |
| sinastria | 518 | 29 | 30 | 577 |
| transitos | 407 | 23 | 24 | 454 |
| sin_bloque (real) | 447 | 25 | 16 | 488 |
| cruz_celta | 442 | 25 | 26 | 493 |
| espanola_1 | 343 | 20 | 20 | 383 |
| espanola_5 | 358 | 19 | 21 | 398 |
| fuera_alcance | 357 | 20 | 21 | 398 |
| revolucion_solar | 357 | 20 | 21 | 398 |
| tarot_2 | 353 | 20 | 22 | 395 |
| biorritmos | 342 | 20 | 20 | 382 |
| numerologia | 321 | 14 | 0 | 335 |
| etica | 281 | 3 | 14 | 298 |
| espanola_7 | 177 | 10 | 11 | 198 |

Generador: mercury-3 12802 · real-corpus 488.

### Proporción vs objetivo (generate_tasks.TARGETS)

| familia | objetivo | final v1d | % | final v1c |
|---|---:|---:|---:|---:|
| tarot_1 | 936 | 912 | 97% | 907 |
| tarot_2 | 400 | 395 | 99% | 395 |
| tarot_3 | 1400 | 1378 | 98% | 1378 |
| cruz_celta | 500 | 493 | 99% | 493 |
| tarot_pregunta | 800 | 748 | 94% | 776 |
| astro_natal | 1500 | 1474 | 98% | 1467 |
| sinastria | 600 | 577 | 96% | 577 |
| numerologia | 400 | 335 | 84% | 332 |
| lectura_completa | 3000 | 1964 | 65% | 1648 |
| multiturno | 800 | 728 | 91% | 766 |
| etica | 300 | 298 | 99% | 300 |
| espanola_1 | 400 | 383 | 96% | 400 |
| espanola_3 | 900 | 889 | 99% | 887 |
| espanola_5 | 400 | 398 | 100% | 398 |
| espanola_7 | 200 | 198 | 99% | 198 |
| **transitos** | 400 | **454** | **114%** | 208 (52%) |
| revolucion_solar | 400 | 398 | 100% | 398 |
| biorritmos | 400 | 382 | 96% | 382 |
| fuera_alcance | 400 | 398 | 100% | 398 |

**transitos** supera el mínimo de 300 exigido en SIGUIENTE: los 400 nuevos de
la semilla 2026 entran en la cadena y la retención final es 454 (394 nuevas
aceptadas reverificadas + restos de mercury_b que pasan filtros).

## 2. Comparación v1c → v1d

| | v1c | v1d | Δ |
|---|---:|---:|---:|
| train | 11563 | 11986 | +423 |
| val | 609 | 648 | +39 |
| test | 624 | 656 | +32 |
| **total** | 12796 | 13290 | +494 |
| transitos | 208 | 454 | +246 |
| lectura_completa | 1648 | 1964 | +316 |

Movimientos por bloque (v1d−v1c): suben transitos +246, lectura_completa +316,
astro_natal +7, tarot_1 +5, numerologia +3, espanola_3 +2; bajan multiturno
−38, tarot_pregunta −28, espanola_1 −17, etica −2. Las bajadas son descartes
de las regeneradas en reverificar/filtro/validar (no pérdida de originales:
el reemplazo quitó el viejo solo cuando la nueva superó toda la puerta).
Etapas: snapshot 14393 → reverificar válidas 13536 → filtro 12984 (fugas_qa
552: 545 de evaluación + 7 de contenido; boiler 2176) → validar kept 12812
(rejected 172: sin_datos_del_prompt 101, orientacion 37, largo 25, corto 5,
eco 1, ia_meta 1, prompt_sin_tildes 2; near_dup 0) → fusión con real 488.

Basura en fuera_alcance (solo contada, `qa.contar_preguntas_basura` sobre el
dataset final): **120 de 398** (v1c: 120/400 en fuente).

## 3. Puerta QA

QA v1d: **0 fugas con conjunto de evaluación** · **0 solapes entre splits**
(prefijo 0, completo 0) · **0 casi idénticos** · **0 buckets solapados**.
Hallazgos de formato: 4 = 2 `restos_plantilla` (preexistentes, vistos en v1c)
+ 2 `id_repetido` **benignos**: los ids numéricos 342 y 361 aparecen una vez
como fila de tarot_1 (maestro) y otra como fila de mercury_c en otro bloque;
la clave (bloque, id) es distinta y el split no se altera. Sanidad: 0 filas
con fallo. **semáforo QA: verde**.

`preparar_entrenamiento`: **semáforo verde** (errores [], avisos [], fugas 0).

## 4. Diversidad (diversidad_dataset.py sobre train, v1c → v1d)

- TTR global: 0.0045 → **0.0048** · únicas 4g: 0.526 → **0.544** ·
  únicas 6g: 0.806 → **0.824** (los 6-gramas repetidos bajan porque las
  regeneradas sustituyen plantillas fijadas).
- Muletillas globales (≥0.5% de ocurrencia): 4g 138 → **100** · 6g 16 → **4**.
- Por bloque (6g único, v1c → v1d): tarot_1 .903→.928 · tarot_2 .924→.943 ·
  tarot_3 .859→.886 · tarot_pregunta .917→.941 · astro_natal .809→.830 ·
  espanola_1 .928→.953 · espanola_3 .859→.887 · etica .795→.843 ·
  multiturno .912→.936 · numerologia .843→.876 · lectura_completa .800→.806.
  Todos mejoran salvo **transitos .934→.905**, que diluye con las 394 filas
  nuevas de semilla 2026 (plantilla compartida, aún alta en absoluto).

## 5. Calidad (calidad_lecturas.py sobre train, % filas, v1c → v1d)

Los tres defectos pedidos (por bloque, v1c→v1d):

- `frase_plantilla`: global 42.1 → **21.9**. astro_natal 80.1→51.2 ·
  espanola_1 54.6→23.9 · espanola_3 74.9→41.6 · etica 64.3→31.7 ·
  multiturno 58.5→24.9 · numerologia 74.4→42.1 · tarot_1 57.1→26.5 ·
  tarot_2 68.6→36.5 · tarot_3 73.4→40.7 · tarot_pregunta 47.4→19.2.
- `apertura_formula`: global 30.6 → **13.2**. astro_natal 40.4→11.7 ·
  espanola_1 55.7→23.3 · espanola_3 63.7→33.8 · multiturno 51.2→20.6 ·
  numerologia 76.5→48.9 · tarot_1 49.3→20.0 · tarot_2 63.2→31.7 ·
  tarot_3 60.1→29.8 · tarot_pregunta 36.4→10.0.
- `cierre_formula` (cierre formulaico): global 16.8 → **10.0**.

Otros: apertura_repetida 27.3→15.4 · cierre_repetido 26.9→16.2 ·
lista_en_prosa 27.0→18.5 · muletilla 25.3→18.3 · truncamiento desaparece.
Empeoran levemente (margen < 2,5 pt): esquema_incumplido 15.6→17.3 ·
placeholder_prompt 24.3→26.1 · longitud_atipica 2.9→5.2 (colas de
lectura_completa largas) · referencia_ausente 0.4→0.7.

## 6. Tokens y estimación de entrenamiento (config T111)

`ajuste_config.py --dataset` sobre el train de v1d:

- Tokens: train **22.741.075** (v1c 20.922.791) · val 1.228.359 ·
  test 1.259.802.
- Longitudes train: p50 1679 · p95 3344 · p99 **3993** · max 5148 (sinastria,
  preexistente). Con `max_seq_len 4096` se truncarían 81 filas (0,68 % de las
  filas; 0,121 % de tokens) — **4096 sigue siendo válido**; con 6144, 0.
- Horas GPU (nodo1/nodo2, T111: 7B r16/a32 400–750 tps; 14B r32/a64
  180–350 tps): 7B 1 época ≈ **8,4–15,8 h**, 3 épocas ≈ **25–48 h**;
  14B 1 época ≈ 18–35 h, 3 épocas ≈ **54–105 h**. (v1c: 7B 3 ép 23–44 h.)
- Semáforo `preparar_entrenamiento`: **verde** (0 errores, 0 avisos, 0 fugas);
  puerta QA: **verde**. Dataset apto para entrenamiento.

## 7. Comandos de construcción

Mapeo de reemplazos (una vez; requiere la BD de tareas de la pasada T124):

```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/armar_dataset_v1.py \
  --mapear-regeneradas \
  --fuente-nueva /Users/angelgonzalez/fase0/fase1_mercury_c/aceptadas.reverificadas.jsonl \
  --db-tareas /tmp/jobs_t124_final.db \
  --db-maestra /Users/angelgonzalez/adivinacion-ia/finetune/corpus/jobs.db \
  --mapa-salida /Users/angelgonzalez/fase0/t126_reemplazos.jsonl
```

Cadena completa v1d (desde la raíz del repo/worktree):

```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/armar_dataset_v1.py \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl \
  --fuente /Users/angelgonzalez/fase0/fase1_mercury_c/aceptadas.reverificadas.jsonl \
  --reemplazos /Users/angelgonzalez/fase0/t126_reemplazos.jsonl \
  --salida /Users/angelgonzalez/fase0/dataset_fase1_v1d \
  --train-ratio 0.9 --val-ratio 0.05 \
  --real-raw /Users/angelgonzalez/adivinacion-ia/finetune/corpus/raw \
  --manifest /Users/angelgonzalez/adivinacion-ia/finetune/corpus/manifest.json
```

Nota: si `/tmp/jobs_t124_final.db` se pierde, hay que volver a generar la BD
de tareas de la pasada T124 antes de re-mapear; el snapshot cacheado con
`--reemplazos` no cambia hasta que cambie la huella del mapa.
