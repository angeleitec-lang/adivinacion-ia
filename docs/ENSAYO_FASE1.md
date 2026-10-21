# Ensayo extremo de la fase 1 (T70)

Ensayo punta a punta **simulado, sin red**, sobre una copia de `jobs.db` en directorio temporal. Ningún dato real fue modificado.

- Directorio del ensayo: `/var/folders/wf/n_gzv4090z77rh0jlq19y78r0000gn/T/ensayo_t70_fw9p5edn`
- Tareas seleccionadas: **200** (astro_natal: 19, cruz_celta: 19, etica: 18, lectura_completa: 18, multiturno: 18, numerologia: 18, sinastria: 18, tarot_1: 18, tarot_2: 18, tarot_3: 18, tarot_pregunta: 18)
- Semáforo final de `preparar_entrenamiento`: **AMARILLO**

## Cadena y formatos intercambiados

```
jobs.db (copiar) ──> ejecutor_fase1.simulacion_fase1
        registro plano: {id, bloque, prompt_system, prompt_user, respuesta, ok, ...}
   ── adaptar_a_sharegpt (DESAJUSTE D1/D4) ──>
        ShareGPT: {conversations:[system,human,gpt], bloque, id}
   ── validate_synthetic (--dir por bloque) ──>
        synth_clean.jsonl + synth_clean.meta.jsonl {i, block} + report
   ── build_dataset (mini-corpus .md sintético = 'real') ──>
        train.jsonl / val.jsonl ShareGPT (SYSTEM fijo)
   ── merge_final ──> dataset_ensayo/{train,val,test}.jsonl + report.json
   ── preparar_entrenamiento (chatml) ──> semáforo
```

## Etapa 1 — ejecutor_fase1 (simulado)

- Pendientes en la copia tras la selección: `200`
- Procesadas: `200` · Aceptadas: **200** · Rechazadas: `0` · Errores de red: `0`
- Motivos de rechazo: `{}`

## Etapa 2 — adaptación a ShareGPT

- Entradas: `200` · Salidas: `200`
- Claves de entrada (ejecutor): `['bloque', 'error', 'id', 'intentos', 'max_tokens', 'motivos', 'motivos_rechazo_previos', 'ok', 'payload', 'prompt_system', 'prompt_user', 'respuesta', 'segundos']`
- Claves de salida (ShareGPT + extras): `['bloque', 'conversations', 'id']`
- Filas con texto NFD normalizado a NFC: `0`

## Etapa 3 — validate_synthetic

- Total: `200` · Kept: **68** · Rejected: `132` · Casi-duplicados: `0`
- Motivos: `{"sin_datos_del_prompt": 73, "prompt_sin_tildes": 30, "duplicado_exacto": 29}`

Por bloque:

| bloque | total | ok | dup | bad |
|---|---|---|---|---|
| astro_natal | 19 | 0 | 0 | 19 |
| cruz_celta | 19 | 8 | 0 | 11 |
| etica | 12 | 1 | 11 | 0 |
| lectura_completa | 18 | 0 | 0 | 18 |
| multiturno | 18 | 15 | 2 | 1 |
| numerologia | 18 | 6 | 0 | 12 |
| sinastria | 18 | 0 | 0 | 18 |
| tarot_1 | 24 | 3 | 13 | 8 |
| tarot_2 | 18 | 12 | 0 | 6 |
| tarot_3 | 18 | 12 | 0 | 6 |
| tarot_pregunta | 18 | 11 | 3 | 4 |

## Etapa 4 — build_dataset (corpus 'real' sintético)

- train: `8` · val: `3`

## Etapa 5 — merge_final

- real train 8→8 · real val 3→3
- sintético in: `68` · dup con real: `0` · útil: `68`
- descartes: `{"junk": 0, "duplicado_exacto": 0, "duplicado_prefijo": 0, "idioma": 0}`
- split final: train `58` val `6` test `15`

## Etapa 6 — preparar_entrenamiento

- Semáforo: **AMARILLO**
- Errores: `[]`
- Avisos: `["test tiene solo 15 filas; es orientativo, no representativo", "el dataset tiene 79 filas válidas; es un ensayo, no un dataset de entrenamiento", "cobertura de tarot: 51/78 cartas (65%)", "cobertura de baraja española: 31/40 naipes (78%)"]`
- Estadísticas: `{"filas": {"leidas": {"train": 58, "val": 6, "test": 15}, "invalidas": {"train": 0, "val": 0, "test": 0}, "validas": {"train": 58, "val": 6, "test": 15}, "total_validas": 79}, "turnos": {"un_turno": 79, "multiturno": 0, "humanos_total": 79}, "por_familia": {"multiturno": 15, "tarot_2": 12, "tarot_3": 12, "sin_etiquetar": 11, "tarot_pregunta": 11, "cruz_celta": 8, "numerologia": 6, "tarot_1": 3, "etica": 1}, "system_prompts": [{"veces": 68, "texto": "Eres una tarotista, astróloga y numeróloga profesional con más de veinte años de experiencia. Escribes en español estándar, con un tono cercano y empático. Inte"}, {"veces": 11, "texto": "Eres una experta en adivinación: tarot, astrología, numerología y quiromancia. Respondes con rigor, claridad y empatía, siempre en español."}], "longitud_caracteres": {"system": {"n": 79, "media": 615.9, "mediana": 693, "p95": 693, "max": 693}, "human": {"n": 79, "media": 790.9, "mediana": 520, "p95": 2555, "max": 2834}, "gpt": {"n": 79, "media": 278.4, "mediana": 218, "p95": 826, "max": 832}, "total": {"n": 79, "media": 1687.2, "mediana": 1364, "p95": 4069, "max": 4355}}, "tokens": {"metodo": "estimación caracteres/3.5", "por_ejemplo": {"n": 79, "medi`

## DESAJUSTES entre etapas

### D1 — La salida del ejecutor no es ShareGPT

ejecutor_fase1 escribe registros planos con prompt_system/prompt_user/respuesta; validate_synthetic y preparar_entrenamiento esperan conversations con roles system/human/gpt.

- **Reproducción mínima:** validate_synthetic.human_of(registro_ejecutor) devuelve cadena vacia porque no existe 'conversations'.
- **Parche propuesto:** Adaptador implementar en el ensayo: adaptar_a_sharegpt() (convierte a conversations y conserva 'bloque' e 'id').

### D2 — min-chars=400 de validate_synthetic vs lector simulado breve

El lector simulado genera lecturas de una frase por carta; 163 de 200 respuestas aceptadas miden menos de 400 caracteres y caerían como 'corto' con el umbral por defecto.

- **Reproducción mínima:** validate(fila, Namespace(min_chars=400, ...)) -> (False, 'corto') para respuestas del simulador.
- **Parche propuesto:** En el ensayo se pasa --min-chars 60. Para producción: subir la verbosidad del lector o bajar el umbral explícitamente en la orden de validación (no cambiar el default ajeno).

### D6 — Prompts pendientes en jobs.db sin tildes

validate_synthetic rechazo 30 filas por 'prompt_sin_tildes': los jobs pendientes de la BD se generaron con prompts viejos sin acentuar (PIPELINE: no reanudar generadores viejos). El ejecutor no lo detecta porque su verificador no revisa tildes.

- **Reproducción mínima:** validate_synthetic.validate(fila, args, bloque) -> (False, 'prompt_sin_tildes') para esas filas.
- **Parche propuesto:** Regenerar las tareas pendientes con generate_tasks actualizado (--replace-pending) antes de la producción real; el ensayo solo lo documenta.

### D7 — El grounding de validate_synthetic es mas estricto que el verificador del ejecutor

validate_synthetic rechazo 73 filas por 'sin_datos_del_prompt': exige que la respuesta mencione signos y numeros extraidos del TEXTO del prompt, un conjunto distinto del que comprueba fase1_prompts.verificar_lectura (que usa 'calculos'). El lector simulado pasa el verificador del ejecutor pero no el grounding del validador; en los bloques ['astro_natal', 'lectura_completa', 'sinastria'] cayo el 100% de las filas.

- **Reproducción mínima:** validate_synthetic.grounding(prompt_astro_natal, simulacion_fase1(system, user)) -> False.
- **Parche propuesto:** Alinear el grounding del validador con los calculos de la tarea (la misma fuente que verificar_lectura) o enriquecer el lector simulado para que recite los datos del prompt. No se modifica el modulo ajeno desde el ensayo.

### D3 — Filtro de términos de dominio de merge_final vs filas de etica

merge_final descarta como junk las filas con domain_hits < 2. Las filas del bloque etica hablan de límites y contención, no de arcanos ni signos, y pueden perderse pese a pasar validate_synthetic.

- **Reproducción mínima:** merge_final.is_junk_pair(adaptar_a_sharegpt(fila_etica)) -> True en las filas marcadas abajo.
- **Parche propuesto:** Propuesta: eximir en merge_final las filas cuyo 'bloque'=='etica' del filtro de dominio (el adaptador ya conserva 'bloque'). No se modifica el módulo ajeno desde el ensayo.
- **Bloques afectados:** `{"etica": 12}`

### D4 — Normalización unicode (NFC/NFD) entre etapas

0 filas del ejecutor traen texto en NFD (descompuesto). preparar_entrenamiento normaliza NFC internamente, pero validate y merge comparan con su propia normalización: las comparaciones de duplicados y grounding pueden fallar según la forma normal.

- **Reproducción mínima:** unicodedata.normalize('NFC', texto) != texto en las filas NFD.
- **Parche propuesto:** El adaptador adaptar_a_sharegpt aplica NFC en system/human/gpt, de modo que lo que entra a validación ya está normalizado.

### D5 — Ids de jobs vs prefijo reservado de evaluación

Los ids de jobs.db son numéricos; 0 empiezan por 'eval-'. No hay riesgo de fuga con la muestra actual (comprobado).

- **Reproducción mínima:** evaluacion_casos.es_caso_de_evaluacion(fila) -> False para todos los ids numéricos.
- **Parche propuesto:** Ninguno necesario; se documenta la comprobación.

## Filas perdidas (resumen por etapa)

- ejecutor (rechazadas): **0**
- validate_synthetic (rejected): **132**
- merge_final (descartes totales): **0**
- preparar_entrenamiento (inválidas): **0**

## Fallos del ensayo

- Ninguno: la cadena completa corrió de punta a punta.
