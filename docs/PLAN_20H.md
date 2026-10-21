# Plan de trabajo de las IAs: 20 horas más (desde 2026-10-20 ~21:15)

Revisado el 2026-10-21 (T77) con el estado real de `main` y de los procesos
vivos. Lo que sigue marcado como **hecho** ya está integrado y con `check.sh` =
CHECK OK; lo **en curso** vive en worktrees sin merge; la **cola** es lo que
queda por asignar.

## Restricción que manda

Las IAs y los trabajos de máquina comparten nodo1 y nodo2. En el corte original:
pasada de afirmaciones de libros (T38) ~445 evidencias/h y pasada web ~500/h.
Por eso las pistas nuevas son sobre todo código que NO consume LLM (herramientas,
tests, auditorías) y las ejecuciones con LLM se limitan a pruebas pequeñas o a
trabajos ya en marcha. Reparto: solo a las pestañas que queden libres; no
interrumpir a las que trabajan. Nodo1 admite concurrencia; nodo2 va más justo.

## Hecho (integrado en `main`)

- **T52** prerevisión, **T53** cartas en inglés y Waite, **T54** revisor local.
- **T55** fuentes clásicas de dominio público: 19 de astrología, 5 de
  numerología y baraja, con manifiesto y hashes.
- **T56** 240 casos de evaluación (20 × 12 familias) y evaluador con línea base.
- **T57** clásicos PD convertidos a evidencias (limpieza, segmentación y juez).
- **T58** auditoría ronda 3, **T59** salud de datos, **T60** mapa del pipeline.
- **T61** `preparar_entrenamiento` y comprobación de cobertura de la muestra.
- **T62** `ejecutor_fase1`: runner sobre `jobs.db` con `fase1_prompts`,
  `verificar_lectura`, reintento con causa, reclamo atómico y copia previa de la
  BD. Dry-run: 10.270 pendientes y 121,2 h con 4 workers a 169,9 s/lectura.
- **T63** auditoría ronda 4, **T67** arreglos de esa ronda (41 tests).
- **T64** recuperación 2 (150 URLs en `web_recup2/`, sin fusionar).
- **T65** y **T68** backend rápido Mercury: comparativa con 0 errores, 1,08 s por
  petición y solo 1,5 % de solape exacto con el nodo local; uso complementario.
- **T66** `kb_v2`: astrología, numerología y baraja construidas; tarot pendiente
  de consenso.
- **T70** ensayo extremo de punta a punta (200 tareas simuladas): 200/200
  aceptadas, pero `validate_synthetic` conservó 68 y `merge_final` dejó 58/6/15.
  Deja siete desajustes D1–D7 documentados.
- **T73** consenso rápido: dedup por fuente (nunca por extractor) y campo
  `extractores`; `--extra-afirmaciones` y `--rehacer-celdas-con-extra`.
- Cerradas además T38, T41, T45, T46, T47, T48, T49, T50 y T51.

## En ejecución (máquina, 2026-10-21)

- Consenso de la KB: dos procesos `consenso_kb.py` (PID 3552 y 96681) escriben a
  la vez en `fase0/consenso_kb/`. **Riesgo de carrera**: dejar uno y conservar
  `consenso.jsonl.bak-0858`.
- Pasada rápida de afirmaciones (T69, PID 81434): ~6.225 de 14.188 evidencias,
  59,3 evidencias/min, ETA ~134 min; log `afirmaciones_rapido/pasada.log`.
- Recuperación 3 (T74, PID 14273): 200 páginas a `web_recup3/`, sin LLM.
- Piloto de tiradas largas (T72, PID 6474): 12 lecturas en
  `fase0/piloto_fase1_v2/prueba.jsonl`.
- Los generadores viejos PID 66101/66396 siguen suspendidos y **no se reanudan**
  (prompts sin tildes).

## En curso como pistas (sin merge)

- **T69** pasada rápida con Mercury (`afirmaciones_rapido.py`, solo en su
  worktree).
- **T71** limpieza de libros en copia `libros_limpio/`, con
  `docs/LIMPIEZA_LIBROS.md` y `claves_excluir_consenso.jsonl`; no toca evidencias
  reales.
- **T72** prompts de tiradas largas (cruz celta y lectura completa) y familia de
  baraja española; `docs/FASE1_TIRADAS_LARGAS.md`.
- **T74** fuentes nuevas de baraja y numerología y rutas de biddytarot y
  labyrinthos; `descubrir_fuentes.py`, `fuentes_nuevas_t74.md` y tanda real de
  200 páginas.
- **T75** alinear la fase 1 con D1/D2/D3/D7 del ensayo: `--formato sharegpt` en
  el ejecutor, exención de `etica` en `merge_final`, grounding del validador y
  repetición del ensayo.
- **T76** consenso Mercury frente a nodos en 40 celdas, con acuerdo ≥ 85 %.

## Cola de pistas

1. **T77** (esta pista): documentación al día; no consume LLM.
2. Fusionar o descartar `web_recup3/` cuando termine T74 y recalcular cobertura.
3. Dejar un único proceso de consenso y construir `kb_v2/tarot.json`.
4. Repetir el ensayo extremo tras T75 y comprobar que los desajustes bajan.
5. Entrenamiento de humo sobre un dataset diminuto, solo con los nodos libres y
   decisión expresa del usuario.
6. Esqueleto del backend (FastAPI) y del frontend, cuando el usuario lo decida.

DeepSeek (pestaña 6) solo 10:00–24:00; Qwen (pestaña 7) solo si las demás están
ocupadas. Pestañas 8 y 9: del usuario.

## Hitos (revisados)

- **5 h: cumplido.** T54 y T56 integradas; T53 con menores de Waite; T47 con
  matriz v2; piloto de fase 1 medido (~64 s/lectura).
- **10 h: cumplido en lo principal.** T55 con 19 clásicos de astrología y 5 de
  numerología; KB v2 construible (T66); runner de fase 1 listo (T62). Tarot de
  `kb_v2` sigue pendiente del consenso.
- **20 h: parcial.** El ensayo de 200 ejemplos está hecho y el evaluador tiene
  línea base, pero las pasadas de afirmaciones y el consenso no han cerrado y la
  generación completa sigue esperando la revisión humana y la decisión del hito
  de cobertura.

## Decisiones pendientes del usuario

1. Revisión del 3 % (2.712 fichas): usar `revisor.html` de T54 y
   `prerevision.md`, o reducir el alcance.
2. Tratamiento de libros no españoles (55,7 % de la muestra).
3. Redefinir el hito de cobertura (completa solo en tarot; mínimos menores en el
   resto).
4. Compra de libros, prioridad baraja española (Salas), con presupuesto limitado.
5. Respuesta de Hugging Face (`Pepere45/spanish-esotericism-corpus`).
6. Esqueleto del backend y del frontend de la app.
7. Generación completa de fase 1: con qué modelo y en qué nodo.

## Decisión del usuario (2026-10-20 22:45): terminar primero la recopilación de datos

Prioridad en los nodos: acabar las pasadas de afirmaciones (web y libros), las
evidencias de los sitios y clásicos nuevos (T47, T53, T57) y el consenso/KB v2; la
generación completa de fase 1 espera. Medido: nodo1 admite concurrencia (4
peticiones a la vez no son más lentas que 1); nodo2 va más justo. La pasada web se
relanzó con `--workers 8 --orden calidad --min-calidad 4 --timeout 180` (log
`afirmaciones_full/run_v2.log`, reanudable). Las pistas nuevas que pidan LLM solo
se asignan si son de recopilación; el resto, código sin LLM o esperar. El piloto
de fase 1 (T49) midió ~64 s por lectura: 10.000 lecturas serían ~59 h con 3
workers.
