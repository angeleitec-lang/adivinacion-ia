# Ensayo extremo de la fase 1 (T70)

Ensayo punta a punta **simulado, sin red**, sobre una copia de `jobs.db` en directorio temporal. Ningún dato real fue modificado.

- Directorio del ensayo: `/tmp/ensayo_t75`
- Tareas seleccionadas: **200** (astro_natal: 19, cruz_celta: 19, etica: 18, lectura_completa: 18, multiturno: 18, numerologia: 18, sinastria: 18, tarot_1: 18, tarot_2: 18, tarot_3: 18, tarot_pregunta: 18)
- Semáforo final de `preparar_entrenamiento`: **AMARILLO**

## Cadena y formatos intercambiados

```
jobs.db (copiar) ──> ejecutor_fase1.simulacion_fase1 (--formato sharegpt, T75)
        ShareGPT: {conversations:[system,human,gpt], bloque, id, calculos} (NFC)
   ── adaptar_a_sharegpt: delegacion a a_sharegpt (identidad en T75) ──>
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
- Claves de entrada (ejecutor): `['bloque', 'conversations', 'id']`
- Claves de salida (ShareGPT + extras): `['bloque', 'conversations', 'id']`
- Filas con texto NFD normalizado a NFC: `0`

## Etapa 3 — validate_synthetic

- Total: `200` · Kept: **125** · Rejected: `75` · Casi-duplicados: `0`
- Motivos: `{"prompt_sin_tildes": 30, "sin_datos_del_prompt": 16, "duplicado_exacto": 29}`

Por bloque:

| bloque | total | ok | dup | bad |
|---|---|---|---|---|
| astro_natal | 19 | 18 | 0 | 1 |
| cruz_celta | 19 | 8 | 0 | 11 |
| etica | 12 | 1 | 11 | 0 |
| lectura_completa | 18 | 14 | 0 | 4 |
| multiturno | 18 | 15 | 2 | 1 |
| numerologia | 18 | 13 | 0 | 5 |
| sinastria | 18 | 18 | 0 | 0 |
| tarot_1 | 24 | 3 | 13 | 8 |
| tarot_2 | 18 | 12 | 0 | 6 |
| tarot_3 | 18 | 12 | 0 | 6 |
| tarot_pregunta | 18 | 11 | 3 | 4 |

## Etapa 4 — build_dataset (corpus 'real' sintético)

- train: `8` · val: `3`

## Etapa 5 — merge_final

- real train 8→8 · real val 3→3
- sintético in: `125` · dup con real: `0` · útil: `125`
- descartes: `{"junk": 0, "duplicado_exacto": 0, "duplicado_prefijo": 1, "idioma": 0}`
- split final: train `103` val `9` test `23`

## Etapa 6 — preparar_entrenamiento

- Semáforo: **AMARILLO**
- Errores: `[]`
- Avisos: `["cobertura de tarot: 51/78 cartas (65%)"]`
- Estadísticas: `{"filas": {"leidas": {"train": 103, "val": 9, "test": 23}, "invalidas": {"train": 0, "val": 0, "test": 0}, "validas": {"train": 103, "val": 9, "test": 23}, "total_validas": 135}, "turnos": {"un_turno": 135, "multiturno": 0, "humanos_total": 135}, "por_familia": {"astro_natal": 18, "sinastria": 18, "multiturno": 15, "lectura_completa": 14, "numerologia": 12, "tarot_2": 12, "tarot_3": 12, "sin_etiquetar": 11, "tarot_pregunta": 11, "cruz_celta": 8, "tarot_1": 3, "etica": 1}, "system_prompts": [{"veces": 124, "texto": "Eres una tarotista, astróloga y numeróloga profesional con más de veinte años de experiencia. Escribes en español estándar, con un tono cercano y empático. Inte"}, {"veces": 11, "texto": "Eres una experta en adivinación: tarot, astrología, numerología y quiromancia. Respondes con rigor, claridad y empatía, siempre en español."}], "longitud_caracteres": {"system": {"n": 135, "media": 647.9, "mediana": 693, "p95": 693, "max": 693}, "human": {"n": 135, "media": 1682.7, "mediana": 1476, "p95": 4120, "max": 4298}, "gpt": {"n": 135, "media": 304.7, "mediana": 219, "p95": 818, "max": 832}, "total": {"n": 135, "media": 2637.3, "mediana": 2545, "p95": 5526, "max": 5704}}, "tokens`

## DESAJUSTES entre etapas

### D1 — La salida del ejecutor no era ShareGPT (CORREGIDO EN T75)

T70: ejecutor_fase1 escribia registros planos con prompt_system/prompt_user/respuesta y validate_synthetic no los entendia. T75: el ejecutor acepta --formato sharegpt y emite conversations [system,human,gpt] con 'bloque', 'id' y 'calculos' en NFC. Este ensayo usa ese formato; adaptar_a_sharegpt queda como delegacion delgada hacia ejecutor_fase1.a_sharegpt.

- **Reproducción mínima:** T70: validate_synthetic.human_of(registro_plano) -> ''. T75: a_sharegpt(registro)['conversations'] tiene roles system/human/gpt y el validador lo consume directamente.
- **Parche propuesto:** Aplicado en ejecutor_fase1.a_sharegpt + --formato sharegpt (commit 8d43541).

### D2 — min-chars=400 de validate_synthetic vs lector simulado breve

El lector simulado genera lecturas de una frase por carta; 163 de 200 respuestas aceptadas miden menos de 400 caracteres y caerían como 'corto' con el umbral por defecto.

- **Reproducción mínima:** validate(fila, Namespace(min_chars=400, ...)) -> (False, 'corto') para respuestas del simulador.
- **Parche propuesto:** En el ensayo se pasa --min-chars 60. Para producción: subir la verbosidad del lector o bajar el umbral explícitamente en la orden de validación (no cambiar el default ajeno).

### D6 — Prompts pendientes en jobs.db sin tildes

validate_synthetic rechazo 30 filas por 'prompt_sin_tildes': los jobs pendientes de la BD se generaron con prompts viejos sin acentuar (PIPELINE: no reanudar generadores viejos). El ejecutor no lo detecta porque su verificador no revisa tildes.

- **Reproducción mínima:** validate_synthetic.validate(fila, args, bloque) -> (False, 'prompt_sin_tildes') para esas filas.
- **Parche propuesto:** Regenerar las tareas pendientes con generate_tasks actualizado (--replace-pending) antes de la producción real; el ensayo solo lo documenta.

### D7 — Grounding del validador vs calculos del ejecutor (CORREGIDO EN T75)

T70: validate_synthetic extraia signos y numeros del TEXTO del prompt, un conjunto distinto del que comprueba fase1_prompts.verificar_lectura (usa 'calculos'); los bloques astrales caian casi al 100%. T75: grounding() usa signos_de_calculos/numeros_de_calculos cuando la fila trae 'calculos' (commits c46d98f y 31eb144; el Ascendente se lee tambien de la clave 'ascendente' de la carta) y el lector simulado menciona los ejes Sol/Luna/Ascendente. Residual: 16 filas 'sin_datos_del_prompt'.

- **Reproducción mínima:** T70: grounding(prompt_astro, lectura_breve) -> False. T75: grounding(prompt, ans, calculos=CALCULOS_ASTRO) -> True si ans menciona 2/3 de los signos de los calculos.
- **Parche propuesto:** Aplicado en validate_synthetic.grounding con calculos de la fila (fuente canonica identica a verificar_lectura) + ejes astrales en el lector simulado; tests TestGroundingConCalculos.

### D3 — Filtro de términos de dominio de merge_final vs filas de etica (CORREGIDO EN T75)

T70: merge_final descartaba como junk las filas con domain_hits < 2; las de etica hablan de límites y contención, no de arcanos ni signos, y podian perderse pese a pasar validate_synthetic. T75: is_junk_pair exime las filas con 'bloque'=='etica'. Residual en este ensayo: 0 filas junk.

- **Reproducción mínima:** merge_final.is_junk_pair({'bloque': 'etica', 'conversations': [pobres en terminos de dominio]}) -> False (antes True).
- **Parche propuesto:** Aplicado en merge_final.is_junk_pair: min_terms=0 para bloque=='etica' (commit fa43684); test TestExencionEtica.

### D4 — Normalización unicode (NFC/NFD) entre etapas

0 filas del ejecutor traen texto en NFD (descompuesto). preparar_entrenamiento normaliza NFC internamente, pero validate y merge comparan con su propia normalización: las comparaciones de duplicados y grounding pueden fallar según la forma normal.

- **Reproducción mínima:** unicodedata.normalize('NFC', texto) != texto en las filas NFD.
- **Parche propuesto:** Aplicado en T75: ejecutor_fase1.a_sharegpt normaliza a NFC system/human/gpt; residual NFD en este ensayo: 0 filas.

### D5 — Ids de jobs vs prefijo reservado de evaluación

Los ids de jobs.db son numéricos; 0 empiezan por 'eval-'. No hay riesgo de fuga con la muestra actual (comprobado).

- **Reproducción mínima:** evaluacion_casos.es_caso_de_evaluacion(fila) -> False para todos los ids numéricos.
- **Parche propuesto:** Ninguno necesario; se documenta la comprobación.

## Filas perdidas (resumen por etapa)

- ejecutor (rechazadas): **0**
- validate_synthetic (rejected): **75**
- merge_final (descartes totales): **1**
- preparar_entrenamiento (inválidas): **0**

## Fallos del ensayo

- Ninguno: la cadena completa corrió de punta a punta.
