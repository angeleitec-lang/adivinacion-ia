# Plan de trabajo de las IAs: 20 horas más (desde 2026-10-20 ~21:15)

Revisado el 2026-10-21 (T104) con el estado real de `main` y de los procesos
vivos (la revisión anterior era la de T77). Lo que sigue marcado como **hecho**
ya está integrado y con `check.sh` = CHECK OK; lo **en curso** vive en worktrees
sin merge; la **cola** es lo que queda por asignar.

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
- **T78** exclusiones de celdas en el consenso (`--excluir-claves`). **T79** y
  **T86** rondas 3 y 4 de fuentes (`descubrir_fuentes.py`, `web_recup4/5/`).
  **T80** tareas de baraja en `generate_tasks`.
- **T81/T91** auditoría ronda 5 y arreglos. **T96/T101/T101b/T101c/T101d** ronda 6 y
  arreglos (`reverificar_fase1.py`).
- **T82** `cobertura_v3.py`: 304 celdas completas de 7.455 (`docs/COBERTURA_V3.md`).
- **T83** piloto Mercury: 42/45 ok, ~40× más rápido que el nodo local.
- **T84** `inventario_legal.py`: 204 fuentes, 54 de riesgo alto.
- **T85/T90** `cierre_recopilacion.py`: consenso cerrado en 3.688 celdas,
  `kb_v2/tarot.json` construido, limpieza de libros aplicada en `libros_limpio/`.
- **T87** clave completa del consenso (hash+entidad+faceta). **T88**
  `filtro_atribucion.py`: 2.188 retiradas propuestas, 0 falsos positivos; sin
  aplicar a producción (decisión humana).
- **T89** baraja en el ejecutor. **T93** `muestras_v2`: 6.982 fichas, 659
  prerevisadas. **T95** documento de generación y `--formato sharegpt`.
- **T99** `linea_base.py`: Flash Next 179/240 (≈86,3 % ajustado).

## En ejecución (máquina, 2026-10-21)

- **T100 pasada completa de fase 1** (en curso): PID 78477, 11.936 tareas con
  Mercury, 3 workers, ShareGPT; instantánea al revisar este plan: 5.490
  aceptadas / 71 rechazadas en `fase0/fase1_mercury/`, ~53 lecturas/min,
  ETA ~3,7 h desde las 17:47. Parada de seguridad rc=3 si hay >20 % de errores.
- **T94 pasada rápida**: parada de seguridad 2026-10-21 17:35 al 2.214/10.512
  evidencias (choque con T100 en el mismo backend). Relanzar con `--workers 1`
  al terminar T100.
- Los generadores viejos PID 66101/66396 siguen suspendidos y **no se reanudan**
  (prompts sin tildes). Nodo1 reservado: comprobar antes de lanzar nada.

## En curso como pistas (sin merge)

- **t92** clásicos de astrología/tarot de dominio público a
  `libros_clasicos_pd2/` (descarga, sin fusionar).
- **t97** recopilación nocturna: descubrir + descargar + evidencias hacia los
  huecos de cobertura v3 (nodo2, ≤2 workers).
- **t100** pasada de generación de fase 1 (en ejecución, ver arriba).
- **t103** `armar_dataset_v1.py` (no existe aún): cadena copia → reverificar →
  fuga a evaluación → ShareGPT → validar → `merge_final` → `preparar`, salida en
  `fase0/dataset_fase1_v1/`.
- **t104** documentación al día (esta pista).

## Cola de pistas

1. Dejar terminar **T100**, reverificar la totalidad con
   `reverificar_fase1.py` (detector de t101d ya integrado, merge `97c2e55`) y
   validar solo las aceptadas (`validate_synthetic --min-chars 400`); después
   **t103** arma el dataset v1.
2. Relanzar **T94** con `--workers 1` cuando T100 suelte el backend; sus
   afirmaciones extras se fusionan en el consenso con `--extra-afirmaciones` y
   `--rehacer-celdas-con-extra` solo en las celdas que ganan fuentes.
3. Decisión humana del paso 3 del cierre: aplicar `filtro_atribucion.py` a
   producción (`--paso 3` + paso 4 con `--excluir-claves`).
4. Revisión humana del 3 % sobre `muestras_v2/` (6.982 fichas; ~40 min si solo
   se validan las 659 prerevisadas, 6–10 h la muestra completa).
5. **t92** y **t97**: terminar y fusionar clásicos y `web_recup4/5/` cuando
   haya hueco de nodo; recalcular cobertura con `cobertura_v3.py`.
6. Decidir piso de `sinastria` (4096→6144), validar con muestra y relanzar sus
   600 tareas excluidas.
7. Esqueleto del backend (FastAPI) y del frontend, cuando el usuario lo decida.
8. Entrenamiento de humo sobre el dataset v1, solo con los nodos libres y
   decisión expresa del usuario.

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
- **Recuento T104:** las 20 h están consumidas. La fase 0 ha cerrado (consenso
  3.688 celdas, `kb_v2` completo, cobertura v3 con 304 celdas), la primera pasada
  real de fase 1 está en curso (T100) y quedan la revisión humana del 3 %, el
  filtro de atribución en producción y el ensamblado del dataset v1 (t103).

## Decisiones pendientes del usuario

1. Revisión del 3 % (ahora 6.982 fichas en `muestras_v2/`, T93): usar
   `revisor.html` y la prerevisión (659 marcadas), o reducir el alcance.
2. Tratamiento de libros no españoles (55,7 % de la muestra).
3. Redefinir el hito de cobertura (completa solo en tarot; mínimos menores en el
   resto).
4. Compra de libros, prioridad baraja española (Salas), con presupuesto limitado.
5. Respuesta de Hugging Face (`Pepere45/spanish-esotericism-corpus`).
6. Esqueleto del backend y del frontend de la app.
7. Generación de fase 1: decidida con Mercury (T100 en curso). Falta relanzar
   las 600 `sinastria` excluidas (decidir piso 4096→6144) y la pasada rápida T94.

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

**Cumplida (T104):** la recopilación cerró en T85/T90 (consenso 3.688 celdas y
`kb_v2` completo) y la generación arrancó con Mercury (T100) el 2026-10-21.
