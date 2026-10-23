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

## Rechazos por motivo

**Ninguno todavía**: no se ha ejecutado la generación LLM (ver «Estado de la
generación» en `ESTADO.md`). Al correr `--run`, `--report` agrupará los rechazos
por el primer motivo del verificador (p. ej. «No rechaza…», «No ofrece
alternativa…», «Responde contenido de una técnica fuera de alcance (X)»,
«Promesa o diagnóstico vedado»).

## Estado de la generación

**BLOQUEADA por el gate de t134.** La pista exige lanzar la generación solo
cuando `t134-parafrasis-baraja-local` tenga su propio `TRACK COMPLETO`. El
`ESTADO.md` de esa worktree muestra el reporte de **T121**, no de T134 (0 hits
propios de T134). Por tanto **no se lanza `--run`** hasta que t134 confirme.

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

`fuera_alcance_v2.jsonl` (esquema ShareGPT de v1d) **sustituye** las 398 filas
corruptas al armar el dataset final: los armadores/`merge_final` agrupan por
campo `bloque`, así que basta con excluir el `fuera_alcance` de v1d e incluir el
v2. Antes de integrar:

1. Verificar **30 muestras a mano** (rechazo empático, sin predicción concreta,
   alternativa dentro de las cuatro técnicas, español estándar con tildes, sin
   contenido de la técnica pedida) y anotarlas en `ESTADO.md`.
2. Confirmar `--report` con aceptadas ≈ objetivo y rechazos revisados.
3. No reintroducir Mercury ni reanudar los generadores suspendidos
   (PID 66101 nodo1, 66396 nodo2).
