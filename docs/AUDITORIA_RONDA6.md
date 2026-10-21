# Auditoría ronda 6 (T96)

Fecha: 2026-10-21. Ámbito: generación de fase 1 con Mercury y cierre de la
recopilación (`finetune/corpus/`): `ejecutor_fase1`, `llm_client`,
`generate_tasks`, `fase1_prompts`, `validate_synthetic`, `merge_final`,
`cierre_recopilacion`, `consenso_kb` y `aplicar_limpieza_libros` (lectura).
Método: lectura focal + ejecución de casos adversos con la venv, sin red y sin
LLM real (clientes y `requests.post` simulados, BD y JSONL temporales; nunca se
leyó ni usó la clave de API). Los defectos marcados **[confirmado por
ejecución]** tienen test en `finetune/corpus/tests/test_auditoria_ronda6.py`,
afirmado como `expectedFailure`: el test pide el comportamiento correcto y hoy
falla; al arreglar el módulo pasará a éxito y habrá que quitar el marcador.
Ningún módulo auditado fue modificado en esta pista.

Resumen: **3 altos, 9 medios, 11 bajos/de diseño**.

---

## GRADO 1 — Crash, duplicación o fuga de evaluación (ALTO)

### A1. `generate_tasks.insertar_jobs` duplica tareas ya hechas con `--replace-pending` **[confirmado por ejecución]**

- Fichero: `finetune/corpus/generate_tasks.py:887-920` (borrado de `pending` en
  la línea 909 e inserción de todo el bloque en 911-914).
- `--replace-pending` borra solo las filas `status='pending'` del bloque y
  después inserta **todas** las filas generadas, incluidas las que ya estaban
  `done`. Como la generación es determinista con la misma `--seed`, una segunda
  pasada deja las mismas tareas dos veces: una hecha y otra pendiente. No hay
  clave única ni dedupe por `(bloque, prompt, payload)`.
- Consecuencia: se vuelven a pagar y a generar lecturas ya hechas y el dataset
  recibe conversaciones duplicadas (o casi duplicadas si la respuesta varía),
  que el dedupe de `merge_final` no elimina porque compara respuestas, no
  preguntas.
- Reproducción: `test_replace_pending_no_duplica_tareas_ya_hechas` (3 filas
  `done` + reinserción con `replace_pending=True` → 6 filas, 3 `done` y 3
  `pending`; lo correcto es 3).
- Arreglo propuesto: añadir `UNIQUE(bloque, prompt)` (o un hash de
  `prompt+payload`) con `INSERT OR IGNORE`; o, con `replace_pending`, borrar
  `pending` **y** `failed`, y saltar las filas cuyo `(prompt, payload)` ya
  exista en el bloque. Si se quiere regenerar un bloque con prompts nuevos,
  exigir `--forzar-bloque` explícito y avisar de las filas `done` que se
  conservan.

### A2. Una excepción no capturada en un job aborta todo el run **[confirmado por ejecución]**

- Fichero: `finetune/corpus/ejecutor_fase1.py:644` (`f.result()` sin
  `try/except`); el `try` de `uno()` solo cubre
  `(ValueError, KeyError, TypeError)` alrededor de `procesar_una`.
- Un `RuntimeError`, `sqlite3.Error`, `OSError` o `OverflowError` dentro de
  `uno()` (o en `marcar`, `_escribir_jsonl`, etc.) se repropaga por
  `f.result()` y tumba el `ThreadPoolExecutor`. El run termina con excepción:
  no hay resumen final, las filas de los futuros pendientes se liberan a
  `pending` en el `finally`, y el error no queda registrado en la BD.
- Reproducción: `test_una_excepcion_en_un_job_no_aborta_todo_el_run` (con
  `workers=2`, el job 2 lanza `RuntimeError`: `ejecutar` propaga la excepción y
  el job 2 queda `pending`, no `failed`).
- Arreglo propuesto: envolver `f.result()` en `try/except Exception`, marcar el
  job como `failed` con `error=f"excepcion:{tipo}: {exc}"` y seguir con el
  resto; o proteger el cuerpo completo de `uno()` con un `except Exception`
  que registre y cuente el fallo. Mantener `KeyboardInterrupt` fuera de esa
  captura.

### A3. Fuga de preguntas de evaluación al split de entrenamiento **[confirmado por ejecución]**

- Fichero: `finetune/corpus/merge_final.py:170-173` (`_clave_respuestas`) y
  `:175-290` (`fusionar`): el dedupe real y el de sintéticos usan solo el hash
  de las **respuestas**; `prefijos` (`:244`) compara 200 caracteres de
  respuesta, no la pregunta; `split_block` reparte los sintéticos por grupos
  del primer `human` sin mirar los `human` reservados para val/test.
- Un prompt real reservado para val/test puede reaparecer en train vía una
  fila sintética con otra respuesta: el par no es duplicado exacto y el prefijo
  de respuesta tampoco coincide. La evaluación deja de ser ciega para esas
  preguntas.
- Reproducción: `test_el_prompt_de_evaluacion_no_aparece_en_train` (20
  preguntas reales en val + 20 sintéticas con las mismas preguntas y respuestas
  distintas → 16 preguntas en train y las 20 en val/test; intersección 16, se
  espera 0).
- Arreglo propuesto: calcular el conjunto de `sha(human_of(r))` de
  `real_val` (val+test) y excluir de train cualquier fila sintética cuyo
  `human` esté en ese conjunto (o moverla a eval); además, dedupe por
  `(human, respuesta)` entre fuentes y construir `prefijos` también con los
  `human` de train.

---

## GRADO 2 — Resultados erróneos / pérdida silenciosa (MEDIO)

### B1. La parada por umbral de errores no cuenta los rechazos del verificador y exige la ventana llena **[confirmado por ejecución]**

- Fichero: `finetune/corpus/ejecutor_fase1.py` (`anotar_resultado` y la llamada
  `anotar_resultado(bool(registro.get("error")))` en `uno()`; `ventana` con
  `maxlen=max(ventana_errores,1)`; evaluación solo si
  `len(ventana) >= ventana_max`).
- Solo se anota `error_red` (fallo de transporte). Una pasada en la que el
  verificador rechaza el 100 % de las lecturas no mueve la ventana: no hay
  parada y se sigue gastando presupuesto. Además, con menos de
  `ventana_errores` tareas la ventana nunca se llena y el umbral no se evalúa.
- Reproducción: `test_los_rechazos_del_verificador_cuentan_para_la_parada`
  (`ventana_errores=2`, `umbral_error=0.2`, 4 rechazos → `rechazadas=4` y
  `parada=None`; se espera parada no nula).
- Arreglo propuesto: anotar también `ok=False` (rechazo del verificador) como
  fallo, y evaluar el umbral con el mínimo entre `ventana_errores` y las
  procesadas (o con un mínimo configurable `--min-muestra-parada`, p. ej. 20),
  no exigiendo la ventana completa.

### B2. El verificador acepta cartas inventadas fuera del universo **[confirmado por ejecución]**

- Fichero: `finetune/corpus/fase1_prompts.py:658-700` (`_verif_cartas`):
  recorre `universo` y detecta cartas **conocidas** que no están en la tirada,
  pero no busca nombres de carta que no existan en `universo`.
- Un texto que menciona «El Arquitecto» (arcano inexistente) junto a la carta
  real pasa la verificación. Lo mismo vale para una «41.ª carta» de la baraja
  española: si el nombre no está en la KB, no se detecta.
- Reproducción: `test_rechaza_carta_inventada_fuera_del_universo`
  (`ok=True` con «El Sol trae claridad. El Arquitecto abre tu camino»).
- Arreglo propuesto: además del universo conocido, extraer candidatos a carta
  (patrones `carta/arcano de X`, nombres propios con artículo `El/La/Los/Las`
  y mayúscula inicial, o una lista cerrada de sufijos) y rechazar los que no
  pertenezcan al universo del sistema (tarot o baraja). Compartir esa lista con
  `validate_synthetic` (ver B9).

### B3. La orientación se comprueba de forma global, no por carta **[confirmado por ejecución]**

- Fichero: `finetune/corpus/fase1_prompts.py:694-704`: `hay_inv` es
  `any(c.invertida)` y `inv` busca «invertid»/«al reves» en cualquier parte del
  texto. Basta una marca de inversión en cualquier sitio para dar por buena una
  carta invertida, y una carta al derecho se rechaza si la inversión se afirma
  lejos de su nombre.
- Reproducción: `test_la_orientacion_se_comprueba_por_carta` (tirada [El Sol
  invertida, La Luna al derecho]; el texto dice «La Luna aparece invertida» y
  no marca El Sol → `ok=True`; se espera rechazo).
- Arreglo propuesto: para cada carta invertida, exigir una marca de inversión
  en una ventana alrededor de su nombre; para cada carta al derecho, rechazar
  una afirmación de inversión en esa misma ventana (reutilizar
  `_mencion_carta`/`_presente_carta_any` para localizar las menciones).

### B4. Un número contradicho en frase natural no se detecta **[confirmado por ejecución]**

- Fichero: `finetune/corpus/fase1_prompts.py:707-724` (`_verif_numeros`): los
  patrones de `_VERIF_NUM` exigen que la etiqueta vaya seguida inmediatamente
  de dígitos (`camino de vida 7`), no de «es el 8» ni «corresponde al 8».
- Reproducción: `test_numero_contradicho_en_frase_natural` (camino de vida
  calculado 7 y texto «Tu camino de vida es el 8» → `ok=True`).
- Arreglo propuesto: permitir hasta ~6 palabras de enlace entre la etiqueta y
  el número (`(?:es|será|corresponde al|marca el|da)\s+(?:el\s+)?(\d{1,2})`),
  manteniendo la exclusión del año de cuatro cifras.

### B5. Promesas vedadas con perífrasis no se detectan **[confirmado por ejecución]**

- Fichero: `finetune/corpus/fase1_prompts.py` (`_PROMESAS_VEDADAS` y
  `_verif_promesas:738-744`): los patrones cubren «puedes dejar la medicación»
  pero no «puedes dejar **de tomar** la medicación», «dejarás el tratamiento»,
  «abandonarás la medicación» ni «te vas a curar» (sí «vas a curar»).
- Reproducción: `test_promesa_vedada_con_perifrasis` («Puedes dejar de tomar la
  medicación sin problema» → `ok=True`).
- Arreglo propuesto: añadir perífrasis (`dejar de (tomar|llevar)`,
  `abandonar(?:ás| la)`, `suspender(?:ás| la)`, `no necesitarás (médico|
  tratamiento)`, `te vas a curar`, `quedarás curado`) y cubrir también el
  consejo en segunda persona del plural.

### B6. Una negativa expresa sobre la lotería se rechaza como promesa vedada **[confirmado por ejecución]**

- Fichero: `finetune/corpus/fase1_prompts.py:567-570` (`_negado` mira solo 6
  caracteres antes del inicio del match y `\bno\s+$`).
- «No puedo darte números de la lotería» genera dos motivos (promesa de juego y
  números de la lotería). El modelo está siendo correcto y el verificador lo
  penaliza; con reintentos, además, se le pide reescribir una respuesta sana.
- Reproducción: `test_una_negativa_expresa_no_es_promesa_vedada`
  (`ok=False` con dos motivos; se espera `ok=True`).
- Arreglo propuesto: ampliar la ventana de negación al inicio de la cláusula
  (p. ej. 30-40 caracteres o desde el último `.`/`;`/`,`), y añadir formas
  «no puedo darte», «no voy a darte», «no te doy», «no puedo predecir»,
  «no hay números ganadores».

### B7. El dedupe del cierre conserva la última fila aunque sea peor **[confirmado por ejecución]**

- Fichero: `finetune/corpus/cierre_recopilacion.py:135-155`: agrupa por
  `(entidad_id, faceta)` y hace `ultima[clave] = fila`; no compara
  `fallback`, longitud ni completitud. Si la última duplicada es un relleno
  `fallback=True`, se queda esa y se descarta la lectura buena.
- Reproducción: `test_dedupe_no_se_queda_la_ultima_si_es_peor` (fila buena y
  después fallback → sobrevive el fallback).
- Arreglo propuesto: ordenar los candidatos por preferencia antes de elegir:
  `fallback=False` primero, luego texto no vacío y de mayor longitud/calidad,
  y solo desempatar por la última aparición. Registrar cuántas filas se
  descartan por celda y por qué criterio.

### B8. Una clave de exclusión con hash vacío se acepta y no excluye nada **[confirmado por ejecución]**

- Fichero: `finetune/corpus/consenso_kb.py:609-627`
  (`cargar_claves_exclusion`): añade `hash_seccion` tal cual, sin validar
  formato ni exigir que no esté vacío.
- Una clave `{"entidad_id": "e", "faceta": "f", "hash_seccion": ""}` crea la
  celda `('e','f')` con `{''}` y la exclusión no coincide con ninguna sección:
  el texto excluido sigue en el consenso y el paso se considera correcto.
- Reproducción: `test_claves_de_exclusion_con_hash_vacio_no_crean_celda`
  (devuelve `{('e','f'): {'', 'abc'}}`; se espera `{'abc'}` o un error).
- Arreglo propuesto: validar `hash_seccion` como SHA-256 hexadecimal de 64
  caracteres (o el formato exacto de `diag.hash_seccion`), ignorar/avisar las
  líneas inválidas y contar los descartes; fallar el paso si una celda queda
  con un conjunto vacío tras la validación.

### B9. `validate_synthetic` acepta una carta inventada **[confirmado por ejecución]**

- Fichero: `finetune/corpus/validate_synthetic.py:358-398` (`grounding`):
  comprueba que las cartas del prompt aparezcan en la respuesta, pero no
  prohíbe cartas adicionales ni valida el universo del sistema.
- Reproducción: `test_el_validador_rechaza_una_carta_inventada` (texto de 617
  caracteres con «El Sol» y «El Arquitecto» → `(True, 'ok')`).
- Arreglo propuesto: reutilizar el mismo control de cartas ajenas/inexistentes
  que el verificador (B2) y pasarlo también en `validate` cuando no hay
  `calculos`; si no se conoce el universo, extraer candidatos y rechazar los
  que no estén en la KB del bloque.

---

## GRADO 3 — Robustez / diseño / datos menores (BAJO)

- **C1.** `merge_final.load_jsonl:91-112` descarta en silencio las líneas con
  JSON inválido (sin contador ni aviso). Una línea truncada de
  `aceptadas.jsonl` desaparece del dataset. Test documental:
  `test_load_jsonl_descarta_la_linea_corrupta_sin_aviso`. Arreglo: contar y
  avisar (o fallar con `--strict`).
- **C2.** `ejecutor_fase1._escribir_jsonl:493-497` hace `append` + `flush`, no
  escritura atómica: un crash a mitad deja una línea truncada que C1 luego
  tira. Arreglo: escribir a `.tmp`, `fsync` y `os.replace` por lote, o al menos
  `fsync` tras el `flush` y una marca de lote completo.
- **C3.** `consenso_kb.cargar_claves_exclusion:620-626` salta en silencio las
  líneas sin `entidad_id`/`faceta`/`hash_seccion` (y también las que no son
  JSON). Arreglo: contar y avisar, y devolver el recuento junto al dict.
- **C4.** `ejecutor_fase1.recuperar_huerfanas:275-286` recupera solo por
  antigüedad (`--huerfano-minutos`, 30 por defecto): un `running` de un worker
  muerto hace menos de 30 minutos se ignora en la reanudación inmediata.
  Test documental: `test_un_running_reciente_no_se_recupera_al_reanudar`
  (`huerfanas_recuperadas=0`, el `running` sigue `running`). Arreglo: reclamar
  por `worker` vivo/heartbeat o documentar `--huerfano-minutos 0` para la
  reanudación manual.
- **C5.** `ejecutor_fase1.ejecutar:514` llama a `copiar_bd` en **cada**
  ejecución, incluso sin pendientes; las copias `jobs.db.copia-*` se acumulan
  sin límite. Arreglo: copiar solo si hay pendientes o si se va a escribir, y
  rotar/limitar las copias.
- **C6.** `llm_client._chat_real:210` asigna `endpoint = self._siguiente_endpoint()`
  y no usa la variable; el `_idx` se lee en la línea 209 y se incrementa sin
  lock. No hay fuga de credenciales (ver sanos), pero el round-robin puede
  repetir nodo con concurrencia. Arreglo: eliminar la variable muerta y
  proteger `_idx` con un lock (o devolver `(idx, endpoint)` de una sola
  operación atómica).
- **C7.** `llm_client.chat_json:351-402` captura `Exception` (incluido el
  `RuntimeError` de clave de API ausente) y lo convierte en `ValueError` tras
  los intentos: se pierde el tipo y el mensaje original queda enterrado.
  Arreglo: dejar pasar `RuntimeError`/errores de configuración sin reintentar.
- **C8.** `fase1_prompts._verif_esquema:758-771`: para `lectura_completa` solo
  comprueba presencia y orden de las cuatro etiquetas; no aplica
  `LIMITE_POSICION_CHARS` (1200) ni `LIMITE_SINTESIS_CHARS` (800) que el
  esquema pide. Un texto con secciones enormes pasa. Arreglo: medir cada
  segmento entre etiquetas y aplicar los límites (o los del esquema vigente).
- **C9.** `ejecutor_fase1.ejecutar` calcula `no_procesadas_por_parada` siempre,
  también cuando `parada is None` (solo puede ser >0 con `stop_event`), y el
  nombre sugiere una parada que no existe. Arreglo: calcularlo solo si
  `parada`/`interrumpida`, o renombrar a `no_procesadas`.
- **C10.** La API interna `ejecutar(..., backend=...)` espera los valores
  `GENERADOR_LOCAL`/`GENERADOR_MERCURY`; pasar `backend="mercury"` (como el
  flag del CLI) no falla: se ejecuta como local con etiqueta `local` y sin
  `max_completion_tokens`. Solo afecta a llamadas internas, pero es una
  trampa. Arreglo: validar el valor y lanzar `ValueError`.
- **C11.** `ejecutor_fase1.a_sharegpt:479-480` solo copia `generador` si es
  truthy; los llamadores actuales siempre lo rellenan, pero una fila antigua o
  una llamada directa quedaría sin etiqueta de origen. Arreglo: escribir
  siempre `generador` (con `"local"` por defecto) o exigirlo.

---

## Verificados como sanos

- **Credenciales entre endpoints.** Se sospechaba una carrera entre
  `_idx` y `_siguiente_endpoint()` que enviaría el modelo/clave de un nodo a la
  URL de otro. **No existe**: `_chat_real` construye `spec`, `url` y `headers`
  del mismo `spec = self._specs[idx]`; el valor devuelto por
  `_siguiente_endpoint()` no se usa. Con dos hilos intercalados por barrera,
  cada petición conserva su URL, modelo y `Authorization`. Test:
  `test_la_clave_no_viaja_al_endpoint_equivocado`. (Sí queda el código muerto y
  el `_idx` sin lock: C6.)
- **La clave no se filtra.** `_headers_de_endpoint` nombra solo la variable de
  entorno y la URL en el error, nunca el valor; los reintentos y `chat_json`
  interpolan excepciones que no contienen la cabecera (ronda 5, revalidado por
  lectura).
- **Errores de red.** Vuelven a `pending`, cuentan para la ventana y disparan la
  parada: `test_los_errores_de_red_si_disparan_la_parada` (3 jobs, ventana 2 →
  parada, 2 procesadas, 1 no procesada).
- **Carta repetida en la tirada.** Se rechaza con motivo «Carta repetida en la
  tirada»: `test_carta_repetida_en_la_tirada_se_rechaza`.
- **Separación baraja/tarot.** El universo de la baraja incluye los arcanos como
  control y un texto de baraja que menciona «La Torre» se rechaza:
  `test_baraja_espanola_rechaza_arcano_de_tarot`.
- **Mercury de extremo a extremo.** Con `backend=GENERADOR_MERCURY` la petición
  lleva `max_completion_tokens` igual a `RECOMENDACION_MAX_TOKENS[bloque]`
  (`tarot_1`), la respuesta se acepta y `aceptadas.jsonl` (sharegpt) conserva
  `generador="mercury-3"`: `test_aceptadas_llevan_el_generador_de_mercury`.
- **Etiqueta de origen en general.** `procesar_una` rellena `generador`
  (explícito o por backend), `a_sharegpt` lo copia si existe y el formato plano
  lo conserva; no se pierde en el camino actual.
- **Cierre atómico.** `cierre_recopilacion._escribir_jsonl_atomico` usa
  `tmp` + `fsync` + `os.replace`, hace copia previa y verifica las claves
  después de escribir; el problema de B7 es la elección de fila, no la
  escritura.
- **Claves de equivalencia.** `consenso_kb.CacheEquivalencia.clave` incluye
  `entidad_id`, `faceta` y los textos: el hash no pierde entidad ni faceta.
- **Reclamación y liberación.** `reclamar` es un `UPDATE ... WHERE
  status='pending'` con `rowcount` (sin doble reclamo), las escrituras de
  aceptadas/rechazadas van bajo lock, `copiar_bd` hace copia timestampada y
  `proteger_final` bloquea rutas `final` (ronda 5, sin regresión).
- **429 y backoff.** `RateLimitError` respeta `Retry-After` y el backoff
  exponencial; el limitador de tasa es thread-safe (ronda 5, sin regresión).
