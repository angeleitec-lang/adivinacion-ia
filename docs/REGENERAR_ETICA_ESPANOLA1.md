# REGENERACIÓN ÉTICA Y ESPAÑOLA_1 (T142)

Rama: `track/t142-etica-v2`. Generador: `halogen-qwen3.8-flash-next` en nodo2
(`http://10.0.0.4:8000/v1`), 1 worker, `--estilo auto`. Salida:
`/Users/angelgonzalez/fase0/etica_espanola1_v2/etica_espanola1_v2.jsonl`.

## Por qué

El dedupe v1e colapsó dos bloques por prompts casi idénticos:

| Bloque | Filas v1d | Sobrevivientes v1e | Prompts únicos |
|---|---|---|---|
| `etica` | 281 | 5 | 7 |
| `espanola_1` | 343 | 46 | 76 |

La causa está en la plantilla: en `etica` solo variaban 7 preguntas fijas
(`CASOS_ETICA`), y en `espanola_1` la línea «Baraja española de 40 naipes…»
aparecía antes de la pregunta, de modo que `auditoria_v1d.prompt_propio()`
cortaba ahí y no contaba ni el contexto ni la pregunta. Techo de unicidad: 80
combinaciones carta×orientación.

## Qué hace el regenerador

`finetune/corpus/regenerar_etica_espanola1.py` construye 280 + 280 trabajos
con variabilidad real y los genera en nodo2 de forma reanudable (BD SQLite
propia, `jobs_etica_esp1_v2.db`). No toca el dataset v1e.

### Ética (280 trabajos)

Banco de 12 categorías × 24 preguntas únicas = 288; se muestrean 280 sin
repetir pregunta. Categorías: crisis emocional (única con `riesgo=True`),
salud, menores, legal, dependencia de la consulta, presión para predecir
muerte, presión para predecir embarazo, presión para predecir infidelidad,
manipulación de terceros, dinero, duelo y adicciones. El prompt guardado es
el estándar (`Consulta delicada. Pregunta del consultante: "…"`) más las
instrucciones acotadas que inyecta el parche (ver abajo).

### Española 1 (280 trabajos)

Combinaciones de 40 naipes (KB `kb/baraja_espanola.json`) × 2 orientaciones ×
6 contextos (salud, amor, trabajo, dinero, espiritual, general) × 14
preguntas por contexto = 6.720 tuplas; se toman 280 con la tupla
(carta, orientación, contexto, pregunta) única. La plantilla nueva coloca la
línea comodín **después** de la pregunta:

```
Tirada de una carta de la baraja española (40 naipes).

Carta: {naipe} ({orientación})
Contexto: {contexto}.
Pregunta del consultante: "{pregunta}"

Baraja española de 40 naipes: no es tarot ni baraja francesa; no la mezcles.

{referencia de la KB}
```

Así `prompt_propio()` (que corta en el comodín) sí incluye carta, orientación,
contexto y pregunta, y la unicidad deja de estar topada. La primera línea dice
«baraja española (40 naipes)» sin el «de», por lo que no dispara el marcador
de corte antes de tiempo.

### Parche acotado (`_instalar_parches_t142`)

Envuelve `fase1_prompts.construir_prompt` y `verificar_lectura` solo para las
familias `etica` y `espanola_1` (la BD de este track no contiene otras). El
resto de familias pasa intacto y todo se restaura al terminar.

- **Tuteo obligatorio**: se añade `INSTRUCCION_TUTEO` al prompt de usuario y
  se rechaza el voseo con una lista cerrada de formas (`querés`, `podés`,
  `contame`, `vos`…), no con patrones genéricos que darían falsos positivos.
- **Línea 024**: en `crisis_emocional` (`riesgo=True`) se exige que la
  respuesta mencione el 024; en el resto está prohibida, para que el modelo no
  la suelte en reflejo.
- **Español y forma**: se rechaza inglés detectable, autodenominaciones de IA
  («asistente de IA», «modelo de lenguaje»…) y respuestas sin punto final.
- **Anti-copia**: tras el export, similitud de Jaccard sobre 12-gramas plegados
  ≥ 0,83 entre respuestas; se descarta la posterior.
- **Fuga de evaluación**: filtro `armar_dataset_v1.filtrar_fugas_eval` contra
  los 240 casos de las semillas reservadas (T56) en el dry-run y en el export.

## Uso

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
S=/Users/angelgonzalez/adivinacion-ia/finetune/corpus/regenerar_etica_espanola1.py

$PY $S --dry-run    # jobs, unicidad, fugas y estimación (sin llamadas)
$PY $S --prepare    # crea la BD reanudable (copia de seguridad si existía)
$PY $S --run        # genera en nodo2, 1 worker, reanudable
$PY $S --report     # dedup + anti-copia + fuga-eval + unicidad → JSONL final
```

El `--run` puede interrumpirse y relanzarse: retoma los `pending` de la BD. El
rechazo de cada fila queda en `rechazadas.jsonl` con su motivo; lo aceptado, en
`aceptadas.jsonl` (formato ShareGPT).

## Resultados

Pendiente: se completará tras el `--report` (válidas por bloque, unicidad,
rechazos por motivo y muestra revisada a mano en `ESTADO.md`).
