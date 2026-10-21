# Auditoría ronda 4 (T63)

Fecha: 2026-10-21. Ámbito: tubería de fase 0/1 (`finetune/corpus/`).
Método: lectura focal + ejecución de casos adversos con la venv (sin red, sin
LLM). Cada defecto marcado **[confirmado por ejecución]** tiene test en
`finetune/corpus/tests/test_auditoria_ronda4.py` (los defectos se afirman como
`expectedFailure`: el test pide el comportamiento correcto y hoy falla; al
arreglar el módulo pasará a éxito y habrá que quitar el marcador). Los demás
están confirmados por lectura de código con reproducción descrita.

Resumen: **4 altos, 6 medios, 8 bajos/de diseño**. Ningún módulo auditado fue
modificado en esta pista.

---

## GRADO 1 — Pérdida de datos / resultados erróneos (ALTO)

### A1. `purgar_errores_juez` reescribe `juicios.jsonl` sin copia de seguridad **[confirmado por ejecución]**

- Fichero: `finetune/corpus/clasicos_pd_a_evidencias.py`, `purgar_errores_juez`.
- Reescribe con `open(ruta, "w")` y vuelca línea a línea. Si el proceso muere a
  mitad (o el disco se llena), se pierden TODOS los juicios del work-dir; no
  queda `.bak` porque la función no lo crea.
- Reproducción: `test_deberia_dejar_copia_previa` (expectedFailure).
- Arreglo propuesto: escribir a `juicios.jsonl.tmp` + `os.replace`, o copia
  `.bak-YYYYMMDD` previa (el patrón ya existe en `evidencias_incremental.ensure_backup`).

### A2. Filtro de cartas mayores inoperante con corpus español **[confirmado por ejecución]**

- Ficheros: `limpiar_evidencias_libros.propuesta_filtro`,
  `diagnostico_tarot_libros.clasificar_titulo`, `cartas._MAYORES_EN`.
- `_nombra_propio` y `clasificar_titulo` solo buscan tokens EN (`death`,
  `justice`…). Con títulos en español devuelven siempre `neutro`, así que
  ninguna evidencia con título de OTRA carta en español es propuesta para
  retirada: el limpiador calla exactamente en el corpus mayoritario.
- Reproducción (ejecutada):

  ```python
  seccion = {"id_libro": "l1", "seccion": 1, "titulo": "La Muerte", "texto": "x"*60}
  ev = {"entidad_id": "tarot-mayor-18", "hash_seccion": juez.hash_seccion(seccion)}
  limpiar_evidencias_libros.propuesta_filtro([ev], [seccion])["n_quitadas"]
  # → 0 con "La Muerte"; → 1 con "Death".
  ```

- Tests: `test_titulo_espanol_debe_quitar` (expectedFailure),
  `test_titulo_ingles_si_quita` (contraste, pasa).
- Arreglo: nutrir los tokens con los nombres ES de `cartas._MAYORES`
  (norm ya unifica NFC/NFD y acentos).

### A3. Reanudación del juez no completa facetas parcial-escritas (por lectura)

- Fichero: `juez.procesar_secciones`.
- `hashes_ev` se construye con los `hash_seccion` presentes en
  `evidencias.jsonl`; si una pasada anterior murió en medio del bloque de una
  sección (el `flush` es por bloque, no por línea), el hash ya figura en el
  fichero con N-1 facetas y la reanudación **omite la sección completa**: las
  facetas que faltan no se regeneran nunca, sin aviso en `stats`.
- Reproducción: cortar a mano `evidencias.jsonl` tras la primera línea de un
  hash con 2+ facetas y relanzar; `stats["evidencias"]` no incluye la que falta.
- Arreglo: comparar facetas esperadas del juicio reaprovechado contra las
  escritas por hash, o volcar/cotejar por línea.

### A4. Caché del juez de evaluación ignora caso y rúbrica (por lectura)

- Fichero: `evaluar_modelo.aplicar_juez`.
- La clave es `sha256(id + "\n" + respuesta)`: no entra el `system`/`user` del
  caso ni `RUBRICA`. Si se regeneran los casos (misma familia/numeración de id,
  contenido otro — ver B3) o se edita la rúbrica, la caché antigua
  (`evaluacion_juez_cache.jsonl`) devuelve veredículos de otra época sin señal.
- Arreglo: incluir `hash(caso)` y `hash(RUBRICA)` en la clave.

---

## GRADO 2 — Validadores/contaminación (MEDIO)

### B1. Mínima de 3 etiquetas numerales se satisface con 2 (doble cuenta) **[confirmado por ejecución]**

- `evaluar_modelo._check_numerologia`: `etiquetas` lista «ano personal» **y**
  «año personal»; `_norm` quita acentos y ambas colapsan al mismo texto, así
  que un `texto` con solo «camino de vida» + «año personal» suma 3 y pasa.
- Test: `test_doble_cuenta_ano_personal` (expectedFailure).
- Arreglo: eliminar el duplicado acentuado (o usar un set de `_norm(e)`).

### B2. `parsear_respuesta` acepta calidad como cadena y trunca float **[confirmado por ejecución]**

- `juez.parsear_respuesta`: `"4"` → 4; `3.7` → 3 (truncado, sin error). Solo
  rechaza bools y fuera de 1–5.
- Tests: `test_calidad_cadena_debe_rechazarse`,
  `test_calidad_flotante_debe_rechazarse` (expectedFailure);
  `test_calidad_actualmente_trunca_y_acepta` documenta el estado actual.
- Arreglo: exigir `isinstance(calidad, int)` sin `bool`.

### B3. Ids de casos de evaluación no identifican la semilla (por lectura)

- `evaluacion_casos.py`: `id = "ev-{familia}-{NN}"` sin semilla; al regenerar
  el conjunto con otra semilla, respuestas viejas casan por id con casos
  nuevos (`evaluar()` las acepta; la caché del juez B1/A4 hereda el problema).
  Además `escribir_casos` abre con `"w"` sin copia: regenerar destruye el
  conjunto congelado anterior.
- Arreglo: meter un sufijo corto del hash del set (o la semilla) en el id, y
  copia previa.

### B4. Reanudación del piloto silencia tareas nuevas (por lectura)

- `fase1_piloto.py`: el id es `{familia}-{contador:02d}`. `--ids-existente`
  deduplica POR ID, y los ids no dependen de la semilla: reanudar con otro
  `--n-por-familia`/`--semilla` omite las tareas nuevas como si ya estuvieran
  hechas (solo aparece «omitidos» en el resumen). Dos procesos simultáneos
  generan ids iguales y duplican líneas. `piloto_errores.jsonl` acumula el
  mismo id repetido en cada reanudación (se reintentan, pero el fichero crece
  sin dedupe).

### B5. Juicio de tipo `error` queda guardado como hecho (por lectura)

- `juez.procesar_secciones` escribe los juicios `{"tipo": "error"}` en
  `juicios.jsonl`; la reanudación los cuenta como `reaprovechadas` y no los
  reintenta. `clasicos_pd` lo mitigó con `purgar_errores_juez` (ver A1);
  `evidencias_incremental` NO purga → sus timeouts quedan fosilizados.
- Arreglo: tratar `tipo=error` como pendiente en `procesar_secciones` (o purgar
  en el flujo incremental).

### B6. `salud_datos`: patrón de exclusión demasiado amplio y truncado no atómico **[confirmado por ejecución]**

- `_es_excluido` descarta cualquier nombre que contenga `.bak`: un fichero
  legítimo `naipes.bakery-ventas.jsonl` desaparece del descubrimiento y de las
  copias de seguridad. Test: `test_no_deberia_excluir_nombres_con_bak`
  (expectedFailure).
- `reparar_ficheros` copia antes de truncar (bién, `test_repara_tras_copia`),
  pero el `open(ruta, "wb")` posterior no es atómico: un fallo entre la copia y
  el volcado deja el fichero a medias (recuperable solo vía `.bak`). Usar
  `os.replace`.

---

## GRADO 3 — Baja / comportamiento a documentar

- **C1 Sobrescritura sin copia (patrón sistémico):**
  `evaluar_modelo.escribir_informe` (informe .json/.md), `prerevision.escribir_jsonl/escribir_md`,
  `revisor_local.main` (HTML), `evaluacion_casos.escribir_casos`,
  `fase1_piloto.generar_informe`. Relanzar con el mismo `--salida` destruye el
  informe anterior; los defaults relativos dependen del CWD.
- **C2 `prerevision._motivo_numero`:** la ventana de contexto mezcla índices
  (`cifra.end()` relativo a la ventana + `hallazgo.end()` absoluto), con lo que
  el guard «el número propio aparece cerca» tiene ancho variable según la
  posición del concepto. No produce falsos positivos en las muestras ejecutadas;
  riesgo de falsos negativos lejanos. Solo detecta cifras ASCII `\d{1,2}`: «el
  siete» mal atribuido no se marca.
- **C3 Excepciones silenciosas en prerevisión:** `bandera_otra_entidad`,
  `bandera_promesa_vedada` y compañía capturan y devuelven `None`: si cambia el
  formato de `entidad_id`, la bandera deja de aplicarse sin ruido.
- **C4 `juez._extraer_json`:** el contador de llaves no ignora `{`/`}` dentro de
  cadenas JSON; una respuesta con llaves en textos largos puede recortar el
  objeto y provocar reintentos evitables.
- **C5 Dos secciones con el mismo hash en una sola pasada** (p. ej.
  duplicado en `secciones`): ambas se juzgan y duplican evidencias; la
  deduplicación solo mira el estado guardado al inicio.
- **C6 `hash_seccion` con `|`:** sospechado y **descartado por ejecución** —
  `numero` es int y el texto va al final; no hay colisión fabricable con
  `"a|b"` como id.
- **C7 Rendimiento:** `prerevision.indice_duplicados` es O(n²) por grupo
  (entidad, faceta) con Jaccard; `salud_datos.crear_copia` lee cada fichero
  completo en memoria. Con corpus enorme serán lentos/pesados (documentar).
- **C8 `cartas.extraer_cartas(contextual=False)`:** acepta toda palabra suelta
  del vocabulario («mundo», «muerte», «sol», «fuerza»…) — solo apto para títulos
  normalizados, nunca para prosa. Con `contextual=True` (default) el filtrado
  funciona: prosa genérica → 0 cartas; «La Muerte invertida» → `tarot-mayor-14`
  invertida. Tests `test_prosa_sin_contexto_no_extrae`,
  `test_orientacion_hace_aceptable`.
- **C9 Ordenación de prerevisión:** `analizar` ordena por `str(id)`; un `id`
  `None` se ordena como "None" (queda primero).

## Verificados como sanos (con test o ejecución)

- `cartas.norm` unifica NFC/NFD (test).
- `juez.parsear_respuesta` rechaza bools y calidad fuera de rango (test).
- `salud_datos.reparar_ficheros` copia antes de truncar y respeta
  `omitido_creciendo` (test de reparado; `lsof` verificado por lectura).
- `evidencias_incremental.ensure_backup` crea la copia diaria ANTES del primer
  append y es idempotente el mismo día (lectura; patrón correcto que A1 debería
  copiar).
- `evaluacion_casos`: día `randint(1, 28)` (sin fechas imposibles); semilla
  restringida a `SEMILLAS_RESERVADAS`; ids duplicados detectados en
  `cargar_casos/cargar_respuestas` (`evaluar_modelo`).
- `revisor_local`: lee con `utf-8-sig` y escapa `<`, `>`, `&`, U+2028, U+2029
  antes de insertar JSON en el `<script>` (inyección neutralizada).
