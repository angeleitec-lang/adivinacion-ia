# REGENERAR_FUERA_ALCANCE (T136)

Regeneración del bloque `fuera_alcance` corrupto del dataset v1d.

## Contexto de la corrupción

El bloque `fuera_alcance` del dataset `fase1_v1d` se generó con **Mercury**
(`generador: mercury-3`) y salió **corrupto**: el generador sustituyó la pregunta
real del consultante por un índice numérico seguido de un «arranque» suelto, con
este patrón:

```
Pregunta del consultante: "<n> <arranque>:"
```

En lugar de la pregunta real. La pregunta sí está recuperable en los jobs
originales (`payload["tecnica"][1]`), pero las filas del dataset no.

### Cifras de la corrupción

| Concepto | Valor |
|---|---|
| Jobs `fuera_alcance` originales (Mercury) | 400 |
| Filas corruptas en `fase1_v1d` | 398 |
| — train | 357 |
| — val | 20 |
| — test | 21 |
| Generador de las corruptas | `mercury-3` |

Todas las 398 presentan el patrón de corrupción. Fuente de las 400 originales:
`/Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl`
(`fuera_alcance` = 400; `mercury` y `mercury_c` aportan 0). Jobs corruptos en
`/tmp/jobs_t113_final.db` (400, status `done`) y `/tmp/jobs_t113.db` (400
`pending`). El `corpus/jobs.db` maestro **no** contiene `fuera_alcance`.

### 5 ejemplos corruptos (ids de v1d)

| id | arranque truncado |
|---|---|
| 36905 | `Vengo a preguntarte:` |
| 37084 | `Alguien me recomendó preguntarte:` |
| 37000 | `Me han dicho que sabes de esto:` |
| 37087 | `Una consulta rápida:` |
| 36894 | `Dime si puedes,` |

## Nota de alcance (categorías)

El `SIGUIENTE` menciona categorías de seguridad (salud, legal, financiero,
muerte/fecha de muerte, embarazo, violencia, menores). Esas categorías
corresponden a la familia **`etica`**, que **NO está corrupta** y no se toca en
esta pista.

El bloque corrupto `fuera_alcance` es de **TÉCNICAS** fuera de alcance
(`FUERA_ALCANCE_ENTRENAMIENTO` en `generate_tasks.py`: quiromancia, runas, I
Ching, Lenormand, Jyotish, BaZi, péndulo, bola de cristal, posos de café, hojas
de té, dados, aura, mediumnidad, feng shui, horóscopo chino, calendario maya,
magia blanca, cristales, chakras, vidas pasadas, telepatía animal, ángeles). Su
verificador (`_verif_negativa_alcance`) busca **marcadores de técnica**, no de
seguridad. Por eso se regenera **ese** bloque, respetando la indicación «mira
las categorías existentes».

## Qué hace el script

`finetune/corpus/regenerar_fuera_alcance.py` **solo importa**
`generate_tasks`, `fase1_prompts`, `ejecutor_fase1` y `llm_client`; **no** los
modifica. Genera un conjunto **nuevo** en
`/Users/angelgonzalez/fase0/fuera_alcance_v2/` (no toca v1d) con prompts
válidos (pregunta real, sin el patrón corrupto) y respuestas que declinan con
empatía en español estándar, remiten a un profesional sin predicción concreta y
ofrecen una alternativa dentro de tarot/baraja/astrología/numerología. Respeta
el esquema ShareGPT exacto de las filas `fuera_alcance` de v1d
(`system`/`human`/`gpt`).

Subcomandos (excluyentes):

| Flag | Acción |
|---|---|
| `--dry-run` | Construye y valida N jobs, estima llamadas/tokens. Sin red. |
| `--prepare` | Crea la DB de jobs (`jobs_fuera_v2.db`) en `pending`. Sin LLM. |
| `--run` | Genera por lotes reanudables contra nodo2 (1 worker). |
| `--report` | Cuentas pending/running/done/failed + rechazos por motivo. |

Garantías del script:
- Valida cada job antes de correr; **aborta (rc=2)** si algún prompt está
  mutilado (detecta el patrón de corrupción), le falta técnica/encabezado o el
  bloque es inesperado.
- **Prohíbe nodo1**: lanza `ValueError` si el endpoint contiene `10.0.0.3`.
- LLM **solo nodo2** (`http://10.0.0.4:8000/v1`), `max_concurrencia=1`,
  `tasa_max_por_minuto=60` (≤1 petición/s).
- Reanudable: usa el ciclo `pending → running → done/failed` del ejecutor.
- Salida ShareGPT: `aceptadas.jsonl` → `fuera_alcance_v2.jsonl`; rechazos en
  `rechazadas.jsonl`.

## Cifras del dry-run (n=400)

```
jobs construidos: 400 (todos validados)
llamadas estimadas (con 30% reintentos): 520
tokens de prompt estimados (~4 char/token): 33210
presupuesto de salida (suma max_tokens): 614400
endpoint previsto: http://10.0.0.4:8000/v1 (modelo halogen-qwen3.8-flash-next, 1 worker)
```

## Resultados de la generación (COMPLETA)

Generación ejecutada contra nodo2 (1 worker, ≤1 req/s) tras abrirse el gate de
t134 (T134 integrada en `main`, merge `35c5364`).

| Concepto | Valor |
|---|---|
| Jobs construidos y validados | 400 |
| Aceptados (`fuera_alcance_v2.jsonl`) | **400** |
| Fallidos al final | 0 |
| Rechazos durante el primer paso (luego reintentados y aceptados) | 2 |

El primer paso dejó 398 aceptados + 2 rechazados por contenido; el relanzamiento
reanudable (`--run`) reintentó esos 2 con el prompt de reintento y los aceptó →
**400/400**.

### Rechazos por motivo (registro de `rechazadas.jsonl`)

```
1  Responde contenido de una técnica fuera de alcance (vidas pasadas): «vidas pasadas»
1  Responde contenido de una técnica fuera de alcance (vidas pasadas): «vida anterior»
```

Ambos del primer paso: el modelo redactó una lectura real de «vidas pasadas» en
lugar de declinar. El verificador canónico (`_verif_negativa_alcance`) los frenó
correctamente; en el reintento el modelo sí declinó y se aceptaron.

### Verificación manual de 30 muestras

Se revisaron 30 respuestas a mano (técnica pedida + respuesta). **30/30
correctas**: declinan la técnica pedida, nombran las cuatro propias (tarot,
baraja española, astrología occidental, numerología), no inventan, ofrecen
alternativa concreta, español estándar con tildes, sin predicción literal, tono
empático. 6 muestras saltaron una bandera `PREDICCION_VEDADA` con una regex
gruesa de control; al leer el texto completo resultaron **falsos positivos**: la
palabra «diagnóstico» aparecía dentro de negaciones correctas («no doy
diagnósticos médicos, legales ni financieros», «no puedo decirte cuánto
vivirás»). El verificador canónico las aceptó bien porque sus patrones detectan
contenido real, no la palabra suelta en negación.

### Barrido automático de las 400 filas

```
total=400 corruptas=0 sin_rechazo=0 sin_alternativa=0 truncadas=0
```

Ninguna fila conserva el patrón de corrupción original; todas contienen rechazo +
alternativa dentro de las cuatro técnicas y ninguna está truncada.

## Comandos

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t136-regenerar-fuera-alcance

# Estimación (sin red)
$PY finetune/corpus/regenerar_fuera_alcance.py --dry-run --n 400

# Preparar jobs en pending (sin LLM)
$PY finetune/corpus/regenerar_fuera_alcance.py --prepare --n 400

# Generar (solo cuando el gate de t134 se cumpla) — 1 worker, nodo2
$PY finetune/corpus/regenerar_fuera_alcance.py --run --n 400 --workers 1

# Cifras y rechazos por motivo
$PY finetune/corpus/regenerar_fuera_alcance.py --report
```

Salidas en `/Users/angelgonzalez/fase0/fuera_alcance_v2/`:
`jobs_fuera_v2.db`, `aceptadas.jsonl`, `rechazadas.jsonl`,
`fuera_alcance_v2.jsonl`.

## Integración

`fuera_alcance_v2.jsonl` (esquema ShareGPT de v1d, **400 filas**) **sustituye**
las 398 filas corruptas al armar el dataset final: los armadores/`merge_final`
agrupan por campo `bloque`, así que basta con excluir el `fuera_alcance` de v1d
e incluir el v2. Estado de los pasos de integración:

1. **Hecho** — Verificadas 30 muestras a mano (rechazo empático, sin predicción
   concreta, alternativa dentro de las cuatro técnicas, español estándar con
   tildes, sin contenido de la técnica pedida) + barrido automático de las 400
   (0 corruptas, 0 sin rechazo, 0 sin alternativa, 0 truncadas). Anotado arriba.
2. **Hecho** — `--report`: 400 aceptadas, 0 fallidas; 2 rechazos del primer paso
   revisados (contenido de «vidas pasadas») y resueltos en el reintento.
3. **En la integración** — No reintroducir Mercury ni reanudar los generadores
   suspendidos (PID 66101 nodo1, 66396 nodo2).

## AJUSTE voseo (23/10, revisión de la coordinadora)

**Defecto**: 137 de las 400 respuestas de `aceptadas.jsonl` usaban **voseo**
(«querés», «podés», «tenés», «contame», «decime», «mirá», «vos»…). El español
del producto debe ser **estándar con tuteo** (tú). Los *prompts* del consultante
pueden conservar voseo (voz del usuario); las **respuestas no**. (La coordinadora
reportó 134; el detector `RE_VOSEO` de esta pista es algo más amplio —incluye
«elegí», «mirá», «contate», etc.— y encontró 137.)

**Cómo se corrigió** (sin tocar `fase1_prompts.py` ni `generate_tasks.py` en
disco, solo *monkey-patch* en tiempo de ejecución acotado a `fuera_alcance`):

- `INSTRUCCION_TUTEO` se añade al campo `user` del prompt en
  `fp.construir_prompt` (solo para `fuera_alcance`): «Responde siempre en
  español estándar con tuteo (tú); nunca uses voseo…». Como el reintento del
  ejecutor parte del `prompt["user"]` ya parcheado, la instrucción llega también
  al reintento.
- `MOTIVO_VOSEO` se añade en `fp.verificar_lectura`: una respuesta con voseo se
  **rechaza** (motivo «Respuesta con voseo (debe ser tuteo estándar)»).
- El parche se instala y se **restaura** con `try/finally` en cada corrida; los
  ficheros de `fase1_prompts.py`/`generate_tasks.py` no se modifican.

**Resultado del reajuste** (`--reajustar-voseo`, nodo2, 1 worker):

```
voseo_detectados: 137
aceptadas_sin_voseo (conservadas): 263
reseteadas_a_pending (regeneradas con tuteo): 137
filas_final: 400
voseo_final: 0
RESULTADO: 0 respuestas con voseo en el export final
```

Backup previo: `aceptadas.jsonl.pre-voseo-20261023-173419` (400 filas).
Verificación independiente: `fuera_alcance_v2.jsonl` = 400 filas, 0 con voseo.
Tests: 27 OK (8 nuevos de detección de voseo + parches). `check.sh` = CHECK OK.
