# Auditoría ronda 5 (T81)

Fecha: 2026-10-21. Ámbito: tubería de fase 0/1 (`finetune/corpus/`):
`consenso_kb`, `kb_v2`, `recuperacion_descarga`, `descubrir_fuentes`,
`ensayo_extremo`, `ejecutor_fase1`, `merge_final`, `validate_synthetic`,
`fase1_prompts`, `build_kb_baraja`, `aplicar_limpieza_libros`,
`comparar_backends`, `llm_client`, `kb/baraja_espanola.json`.
Método: lectura focal + ejecución de casos adversos con la venv (sin red, sin
LLM real). Los defectos marcados **[confirmado por ejecución]** tienen test en
`finetune/corpus/tests/test_auditoria_ronda5.py` (afirmados como
`expectedFailure`: el test pide el comportamiento correcto y hoy falla; al
arreglar el módulo pasará a éxito y habrá que quitar el marcador). Los demás
están confirmados por lectura de código con reproducción descrita.

Resumen: **5 altos, 10 medios, 20 bajos/de diseño**. Ningún módulo auditado fue
modificado en esta pista.

---

## GRADO 1 — Crash que aborta el run / resultados perdidos (ALTO)

### A1. `consenso_kb.construir_consensos` revienta si la celda mezcla `fuente_id=None` con `str` **[confirmado por ejecución]**

- Fichero: `finetune/corpus/consenso_kb.py` (bloque `mayoritarias` de
  `construir_consensos` y `_lado_discrepancia`).
- `fuentes = {m.get("fuente_id") for m in miembros}` y luego
  `sorted(fuentes)`. Las afirmaciones web sin `fuente_id` (solo `dominio`)
  aportan `None`; `sorted({None, 'waite'})` lanza
  `TypeError: '<' not supported between instances of 'NoneType' and 'str'`
  y tumba todo el consenso.
- Reproducción: `test_mayoritaria_con_fuente_id_none_no_crashea`.
- Arreglo propuesto: `sorted(f for f in fuentes if f is not None)` o
  normalizar `fuente_id` a `""` al cargar (usar `_clave_fuente`, que ya
  existe y tolera None).

### A2. `ejecutor_fase1`: un payload malformado aborta TODO el pool y deja la fila en `running` **[confirmado por ejecución]**

- Fichero: `finetune/corpus/ejecutor_fase1.py` (`tarea_desde_job` líneas
  ~142/152; `uno()` captura solo `ValueError` línea ~418; `f.result()` en
  `as_completed` repropaga).
- `bloque='numerologia'` con `payload={}` → `payload["fecha"]` lanza
  `KeyError`. `uno()` solo captura `ValueError` (bloque_invalido), así que
  el hilo muere, la fila queda `running` hasta `huerfano-minutos`, y
  `f.result()` aborta el run completo del worker.
- Reproducción: `test_payload_sin_fecha_no_aborta_el_pool`.
- Arreglo propuesto: validar payload en `tarea_desde_job` y lanzar
  `ValueError("payload incompleto para bloque X: falta 'fecha'")`, o
  capturar `KeyError` además de `ValueError` en `uno()`.

### A3. `recuperacion_descarga.orden_familias` revienta con familia `None` **[confirmado por ejecución]**

- Fichero: `finetune/corpus/recuperacion_descarga.py:100`.
- `candidatas_por_familia` agrupa con `entrada.get("familia") or
  familia_de(...)`, que puede ser `None`; `orden_familias` hace
  `sorted(f for f in familias ...)` → `TypeError` `None` vs `str`.
- Reproducción: `test_orden_familias_tolera_familia_none`.
- Arreglo propuesto: excluir `None` del resto (`sorted(f for f in familias
  if f is not None and f not in prioritarias)`) o descartar la clave `None`
  en `candidatas_por_familia` con aviso.

### A4. `recuperacion_descarga.cargar_plan` tumba todo el run con una línea corrupta **[confirmado por ejecución]**

- Fichero: `finetune/corpus/recuperacion_descarga.py:69`.
- `json.loads(linea)` sin `try`: una sola línea corrupta en
  `plan_recuperacion.jsonl` (p. ej. escritura interrumpida) aborta toda la
  recuperación. Otros loaders de la tubería (`_leer_jsonl` de
  `aplicar_limpieza_libros`) toleran y cuentan.
- Reproducción: `test_cargar_plan_debe_tolerar_linea_corrupta`.
- Arreglo propuesto: `try/except json.JSONDecodeError: continue` con contador
  de líneas corruptas en el resumen.

### A5. `ensayo_extremo._leer_jsonl` sin tolerancia a línea corrupta (por lectura)

- Fichero: `finetune/corpus/ensayo_extremo.py`.
- Si un worker murió a mitad de escritura de `aceptadas.jsonl`, la última
  línea queda truncada y el ensayo en reanudación lanza `JSONDecodeError`
  antes de empezar. Mismo patrón que A4.
- Arreglo propuesto: saltar líneas inválidas con aviso (patrón `_leer_jsonl`
  de `aplicar_limpieza_libros.py`).

---

## GRADO 2 — Resultados erróneos / pérdida silenciosa / cortesía violada (MEDIO)

### B1. Consenso: dos webs de dominios distintos sin `fuente_id` nunca forman mayoría **[confirmado por ejecución]**

- `construir_consensos` cuenta independencia SOLO por `fuente_id`
  (`fuentes = {m.get("fuente_id")...}`), mientras `deduplicar_por_fuente`
  usa `_clave_fuente = fuente_id or dominio`. Dos fuentes web independientes
  sin id dan `fuentes={None}` → `len<2` → nunca mayoritarias
  (subconteo de independencia).
- Reproducción: `test_dominios_distintos_sin_fuente_id_deben_sumar_mayoria`.
- Arreglo propuesto: contar con `_clave_fuente(m)` en lugar de
  `m.get("fuente_id")`.

### B2. `kb_v2._confianza`: dos entradas de la MISMA fuente suben a «media» **[confirmado por ejecución]**

- `len(unica) >= 2 → "media"` sin comprobar que las `unica_fuente` sean de
  fuentes DISTINTAS (criterio documentado: respaldo cruzado). Dos
  afirmaciones de `waite` sin acuerdo externo valen como si fueran dos
  fuentes.
- Reproducción: `test_unica_fuente_repetida_no_debe_dar_media`.
- Arreglo propuesto: `len({u.get("fuente_id") for u in unica}) >= 2`.

### B3. `kb_v2` es first-wins y `consenso_kb` es last-wins en celdas duplicadas **[confirmado por ejecución]**

- `construir_kb_v2` (`vistas`): `if clave in vistas: continue` → gana la
  PRIMERA ocurrencia de `(entidad_id, faceta)`.
  `consenso_kb._cargar_consenso_existente` asigna el dict → gana la ÚLTIMA.
  Si una corrección se añade (append) al final de `consenso.jsonl`, la KB v2
  conserva la versión ANTIGUA.
- Reproducción: `test_celda_duplicada_gana_la_ultima_no_la_primera`.
- Arreglo propuesto: sobreescribir en `vistas` (last-wins) o detectar
  duplicados y avisar.

### B4. `kb_v2.construir_kb_v2` devuelve stats no serializables **[confirmado por ejecución]**

- `stats["v1_con_nucleo"]` es un `set`; cualquier `json.dumps(stats)` por
  parte del llamador lanza `TypeError`.
- Reproducción: `test_stats_deben_ser_serializables`.
- Arreglo propuesto: `sorted(list(...))` al devolver, o serializar dentro.

### B5. `consenso_kb.agrupar_celda` trunca a `MAX_POR_CELDA` en silencio **[confirmado por ejecución]**

- `textos = [a["afirmacion"] for a in afirmaciones][:MAX_POR_CELDA]`: las
  afirmaciones 41+ nunca se agrupan ni cuentan, pero `n_afirmaciones`
  reporta todas. Pérdida silenciosa de evidencia en celdas grandes.
- Confirmación: `test_truncamiento_max_por_celda_es_silencioso` (el test
  afirma el truncamiento tal como ocurre).
- Arreglo propuesto: registrar en el resultado cuántas quedaron fuera
  (`n_no_agrupadas`) o procesar en lotes.

### B6. Celdas `fallback` (LLM inválido) nunca se reintentan al reanudar **[confirmado por ejecución]**

- El docstring de `agrupar_celda` dice «se marca `fallback` para poder
  reintentar la celda más adelante», pero `_cargar_celdas_procesadas`
  excluye por igual las celdas con `fallback=True`: al reanudar no se
  reintentan nunca.
- Reproducción: `test_fallback_no_debe_contarse_como_procesada_definitiva`.
- Arreglo propuesto: no marcar como procesadas las `fallback`, o añadir
  `--reintentar-fallback` que las excluya del set de procesadas.

### B7. Bloqueo de dominios evadible por subdominio (recuperación) **[confirmado por ejecución]**

- `recuperacion_descarga.DOMINIOS_BLOQUEADOS` se compara exacto tras
  `_norm_dominio` (solo quita `www.` y puerto): `old.reddit.com` y
  `es.astro.com` pasan el filtro y se descargarían, violando la cortesía
  declarada en el proyecto.
- Reproducción: `test_bloqueo_debe_cubrir_subdominios`.
- Arreglo propuesto: coincidir por sufijo de dominio registrable
  (`dominio == b or dominio.endswith("." + b)`).

### B8. `descubrir_fuentes` comparte la misma evasión por subdominio (por lectura)

- `descubrir_fuentes.py:29` define el mismo `frozenset` exacto y
  `norm_dominio` solo quita `www.`/puerto. Mismo arreglo que B7.

### B9. `fase1_prompts._verif_numeros`: la etiqueta «Año personal 2026: 5» se rechaza como contradicción **[confirmado por ejecución]**

- Patrón `año\s*personal\s*(\d+)` aplicado a la respuesta: si el modelo
  repite la etiqueta del prompt (`Año personal 2026: 5`), el regex captura
  **2026** ≠ esperado **5** → rechazo falso «Contradice el año personal
  calculado (5): el texto dice 2026». Descarta lecturas correctas.
- Reproducción: `test_etiqueta_con_ano_no_contradice_anio_personal`.
- Arreglo propuesto: patrón que capture el valor tras los dos puntos
  (`año\s*personal(?:\s*\d{4})?\s*[:\-–]?\s*(\d+)`) o extraer el último
  número de la frase.

### B10. `build_kb_baraja.construir()` calcula `sinonimos` y NUNCA los guarda **[confirmado por ejecución]**

- Líneas ~410-414 construyen la lista (`paje/jota de <palo>`, `caballero`,
  `N de palo`, `uno de palo`) pero el `dict` del naipe (líneas ~415-428)
  carece de la clave `"sinonimos"`. El `kb/baraja_espanola.json` commitado
  no tiene el campo en ningún naipe (verificado por ejecución). Los
  consumidores que lean sinonimias desde la KB no reciben nada; hoy solo se
  salvan porque `fase1_prompts` los lee de `cartas.NAIPES_ESPANOLES`.
- Reproducción: `test_naipes_deben_incluir_sinonimos`.
- Arreglo propuesto: añadir `"sinonimos": sinonimos` al dict y regenerar el
  JSON.

---

## GRADO 3 — Robustez / diseño / datos menores (BAJO)

- **C1.** `kb_v2._escribir_informe_diff`: `open+write` no atómico, aunque
  los JSON de KB sí usan `_escribir_atomico` (tmp + `os.replace`). (por lectura)
- **C2.** `kb_v2.clave_v1`: las claves PES/PEC (`('astrologia','pes',...)`)
  nunca existen en la v1 (que guarda planeta/casa sueltos) → toda celda
  PES/PEC se cuenta «nueva». Probablemente por diseño; documentar. (por lectura)
- **C3.** `consenso_kb.signo_de_entidad`/`elemento_de_entidad` comparan
  `partes[0]` crudo contra claves normalizadas: entidad `Aries|signo`
  (mayúscula) no encuentra elemento/regente y los checks se saltan. (por lectura)
- **C4.** `recuperacion_descarga.cargar_hashes_previos` lee solo 2048 bytes
  de cabecera: un `sha256:` de front-matter más allá no se ve → duplicados. (por lectura)
- **C5.** `recuperacion_descarga._append_registro` no atómico (tolerable:
  append-only). (por lectura)
- **C6.** `dominio_usado` cuenta intentos, no éxitos: 40 errores consecutivos
  bloquean el dominio para el resto del run. (por lectura)
- **C7.** `descubrir_fuentes.escribir_plan` no atómico (`open 'w'`): crash a
  mitad trunca el plan. (por lectura)
- **C8.** `descubrir_fuentes.es_sitemap_index` mira solo los primeros 2000
  caracteres. (por lectura)
- **C9.** `descubrir_fuentes`: los sub-sitemaps del índice no se filtran por
  `robots.txt` (solo las URLs finales). (por lectura)
- **C10.** `descubrir_fuentes`: `f['dominio']`/`f['sitemap']`/`f['patron']`
  `KeyError` con fuente malformada en la config. (por lectura)
- **C11.** `merge_final.write_jsonl` y `report.json` no atómicos: crash a mitad
  trunca `corpus/final/*.jsonl`. (por lectura)
- **C12.** `merge_final`: el filtro de prefijos se construye solo desde train;
  duplicados de prefijo DENTRO de val o dentro de test sobreviven ambos. (por lectura)
- **C13.** `merge_final.split_block`: un grupo grande que excede el cupo pasa
  el split del ratio (aproximado, por diseño). (por lectura)
- **C14.** `validate_synthetic`: sin `calculos`, el `NUM_RE` heredado captura
  «20» de «Año personal 2026: 5» → rechazo falso `sin_datos_del_prompt`
  (documentado en D7: se evita pasando calculos; sin ellos persiste). (por lectura)
- **C15.** `validate_synthetic.orientacion_ok`: ventana ±30 chars alrededor
  del nombre de carta; una mención de inversión lejos del nombre pasa. (por lectura)
- **C16.** `fase1_prompts._fmt_numerologia` hardcodea la etiqueta «Año
  personal 2026» (bomba de relojería en 2027; agrava B9). (por lectura)
- **C17.** `fase1_prompts._verif_esquema`: `_CAB_NUM` (`^[ \t>*#-]*(\d+)[.)]`)
  también casa líneas numeradas del cuerpo → falsos «Sección N duplicada» /
  desorden. (por lectura)
- **C18.** `build_kb_baraja.NAIPES` define «Siete de Bastos» dos veces
  (líneas 337 y 351) con contenido idéntico: inofensivo en dict literal,
  pero si hubieran diferido, sobrescritura silenciosa. (por lectura)
- **C19.** Typos en datos de `build_kb_baraja`: «Sociadad afectuosa» (Dos de
  Copas, trabajo) y «volvverse» (Nueve de Copas, amor). (por lectura)
- **C20.** `llm_client._chat_real`: `self._idx` se lee y se incrementa sin
  lock; con concurrencia dos hilos pueden coincidir en endpoint y descuadrar
  el round-robin (sin crash). (por lectura)
- **C21.** `aplicar_limpieza_libros`: `BASE` hardcodeada a
  `/Users/angelgonzalez/fase0` y `DIR_SALIDA` dentro de fase0 real → el
  default escribe en el corpus real (diseño T71; conviene `--dry-run` por
  defecto o salida fuera de fase0). (por lectura)
- **C22.** `comparar_backends`: rutas hardcodeadas a los worktrees
  `t68-backend-rapido-2` / `t38-afirmaciones-libros` → `ImportError` si ya
  no existen. (por lectura)
- **C23.** `comparar_backends._fila_ejemplo` accedería `r['cobertura_local']`
  con `KeyError` en filas `sin_texto`; hoy latente porque los ejemplos solo
  salen de filas ok/error. (por lectura)
- **C24.** `comparar_backends._estimacion_horas` hardcodea `pendientes=6000`. (por lectura)

---

## Verificados como sanos

- `llm_client`: la API key **no se filtra** — `_headers_de_endpoint` nombra
  solo la variable de entorno en el error, nunca el valor; los reintentos de
  `chat_json` interpolan excepciones que no contienen la clave. Test:
  `test_error_de_env_nombra_variable_sin_valor`.
- `comparar_backends`: `INCEPTION_API_KEY` nunca se escribe en el informe
  (solo se nombra la variable); `main()` exige la env antes de arrancar. (por lectura)
- `kb/baraja_espanola.json` commitado: 40 naipes, 10 por palo, rangos
  As..Rey, nombres únicos, sin colisiones sinonimo↔nombre de otro naipe,
  estado «provisional» en todos. Test: `test_baraja_cuarenta_naipes_sana`.
- `ejecutor_fase1`: `reclamar()` es atómico (`UPDATE ... WHERE status='pending'`
  con rowcount) — sin doble reclamo entre workers; las escrituras a
  aceptadas/rechazadas van dentro de `with lock`; `copiar_bd` hace copia
  timestampada antes de escribir; `proteger_final` bloquea la ruta `final`. (por lectura)
- `ejecutor_fase1`: fallo de red → `error_red` y la fila vuelve a `pending`
  (correcto); `KeyboardInterrupt` libera las filas en vuelo. (por lectura)
- `consenso_kb.deduplicar_por_fuente`: la fusión conserva `extractores` y
  no pisa campos existentes con `None`. (por lectura)
- `validate_synthetic`: MinHash/LSH determinista (semilla 20261018, 16×4,
  umbral 0.9); `etica` exenta de `ia_meta`/`eco_prompt`; `SIN_TILDES_MARCAS`
  descarta prompts del generador viejo. (por lectura)
- `merge_final`: reparto val/test 50/50 determinista por `sha(human)`;
  `is_junk_pair` exime `etica` de `min_terms`; truncado synth/meta al mínimo
  si difieren. (por lectura)
- `llm_client._LimitadorTasa`: ventana de 60 s thread-safe;
  `RateLimitError.backoff` respeta `Retry-After`; `ContenidoVacioError`
  reintentable. (por lectura)
