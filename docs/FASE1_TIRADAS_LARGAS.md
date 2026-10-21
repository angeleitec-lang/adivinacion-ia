# Fase 1 — Tiradas largas y baraja española (pista T72)

Fecha: 2026-10-21. Ficheros afectados: `finetune/corpus/fase1_prompts.py`,
`finetune/corpus/build_kb_baraja.py` (nuevo), `finetune/corpus/kb/baraja_espanola.json`
(nuevo, provisional), `finetune/corpus/tests/test_fase1_prompts.py`.
Prueba real: `/Users/angelgonzalez/fase0/piloto_fase1_v2/prueba.jsonl` (12 lecturas).

## 1. Diagnóstico del piloto v1

En `/Users/angelgonzalez/fase0/piloto_fase1/piloto.jsonl`, `cruz_celta` (0/3) y
`lectura_completa` (0/3) fallaron por **truncamiento**, no por calidad:

- El piloto usaba `max_tokens=2048` y `generate_tasks.py` pedía 1600 (cruz_celta) y
  1800 (lectura_completa). Con la medida empírica de ~2,05 chars/token en español,
  eso corta la respuesta en 3,3–4,2 k chars; las lecturas rechazadas medían
  4173–4428 chars y terminaban en mitad de frase.
- Con el presupuesto recortado, `cruz_celta` solo alcanzaba a cubrir 5–6 posiciones
  de 10 (`Falta la carta de la tirada: X` en los motivos) y `lectura_completa`
  gastaba el presupuesto en la lista de aspectos de la carta natal y no llegaba a
  nombrar las tres cartas del tarot.
- Motivo recurrente «Menciona carta ajena»: en `lectura_completa` la carta natal
  menciona `La Luna en Capricornio` o `el Sol en Leo` (astros), y el verificador los
  contaba como arcanos de tarot.

## 2. Cambios en el prompt (`fase1_prompts.py`)

- **Esquema obligatorio por posiciones** (`_esquema_texto`) para las familias de
  `FAMILIAS_ESQUEMA = (cruz_celta, espanola_5, espanola_7)`: cabeceras literales
  `## N. posición — Carta (orientación)` en orden fijo, una sección por carta,
  150–300 chars por sección, prohibido nombrar cartas no dibujadas (solo existen las
  N indicadas), y cierre único `## Síntesis` de máximo 400 chars. Con secciones
  acotadas, la lectura completa de la Cruz Celta cabe en ~3 k chars: el problema
  deja de ser de presupuesto y pasa a ser de estructura.
- **`lectura_completa`** recibe esquema duro de cuatro secciones:
  `## Carta natal` (≤600 chars, sin lista de aspectos), `## Tirada de tres cartas`
  (las tres posiciones con su carta), `## Numerología` (los números calculados) y
  `## Síntesis` (≤400 chars).
- Familias de 1–3 cartas (tarot y español): se mantiene el prompt libre
  (compatibilidad hacia atrás: los tests históricos de `tarot_3` sin esquema siguen
  aprobando).

## 3. Familia baraja española

- Nuevas familias `espanola_1`, `espanola_3`, `espanola_5`, `espanola_7`
  (`tarea['mazo'] = 'espanol'`). Posiciones: `espanola_3` pasado/presente/futuro;
  `espanola_5` situación/obstáculo/pasado/futuro/resultado; `espanola_7`
  base/pasado/presente/futuro/entorno/consejo/resultado (una de las tiradas
  tradicionales más extendidas de 7 cartas).
- El cuerpo del prompt declara explícitamente: *Baraja española de 40 naipes: no es
  tarot ni baraja francesa; no la mezcles*, y la referencia sale de
  `kb/baraja_espanola.json` (`_ref_baraja`).
- **KB provisional**: `build_kb_baraja.py` genera los 40 naipes con significado
  propio, invertida, `palabras_clave` y contextos amor/trabajo, con clave `aviso`
  de provisionalidad. `afirmaciones_full` tiene 8.604 afirmaciones de naipe
  pendientes de destilar a la KB definitiva (2/480 celdas de la rejilla cubiertas);
  esta KB permite generar dataset ya, marcando el origen.
- Sorteo desde `cartas.NAIPES_ESPANOLES` (40, sin reemplazo). Baraja y tarot se
  mantienen separados: `universo_baraja()` añade al universo los nombres del tarot
  que **no** son naipe (mayores, Reinas, Ochos/Nueves/Dieces) para que el verificador
  detecte mezclas y la «41.ª carta»; `Caballero de X` y los sinónimos Sota/paje/jota
  se consideran variantes legítimas del naipe dibujado, no ajenas.

## 4. Verificador

- `_verif_esquema`: exige cabeceras numeradas 1..N en orden creciente, que cada
  sección nombre a su carta (la cabecera cuenta) y que la síntesis exista y no
  exceda `LIMITE_SINTESIS_CHARS`; segmentos por encima de `LIMITE_POSICION_CHARS`
  se rechazan. Solo se aplica a las familias con esquema (y a `lectura_completa`,
  que verifica sus cuatro secciones en orden), de modo que no rompe lecturas
  cortas existentes.
- `_verif_cartas` ampliado: carta repetida en la tirada, presencia por sinónimos
  (paje/jota/Caballero) y filtro astrológico nuevo (`_mascara_astros`): cuando la
  tarea incluye carta natal, `el sol / la luna en <signo>` se blanquea antes de
  buscar menciones ajenas — son astros, no arcanos. En tareas sin carta natal se
  sigue marcando (test de control incluido).

## 5. Prueba real (12 lecturas)

Script temporal con `LLMClient` sobre los dos nodos (modelo halogen, temperatura
0,4, 2workers), `max_tokens` = `RECOMENDACION_MAX_TOKENS` de cada familia.
Salida: `piloto_fase1_v2/prueba.jsonl`.

| Familia | Aprobadas | chars (min–máx) | max_tokens | s (media) |
|---|---|---|---|---|
| cruz_celta | 3/3 | 2810–3134 | 6144 | 347 |
| lectura_completa | 3/3 | 1472–1816 | 6144 | 338 |
| espanola_5 | 3/3 | 1628–1829 | 4096 | 445 |
| espanola_3 | 3/3 | 4121–5850 | 2560 | 265 |

Iteraciones durante la prueba:

1. Dos tareas (1 cruz_celta y 1 lectura_completa) dieron *read timeout* a 240 s en
   nodo1 (saturado con 6144 tokens en paralelo); reintentadas en nodo2 con timeout
   600 s: **aprobadas** (170 s y 202 s). No es problema de prompt: el generador debe
   usar timeout ≥600 s para las familias pesadas.
2. Una `lectura_completa` se rechazó por `Menciona carta ajena: La Luna` — falso
   positivo de la carta natal; se corrigió el verificador (§4) y la lectura guardada
   re-verificada offline: aprueba sin regenerar.

Resultado final: **12/12 aprobadas** con `verificar_lectura` (incluye esquema,
baraja de 40 y luminares).

## 6. max_tokens recomendado por familia

Base empírica: ~2,0–2,3 chars/token en español. Las cabeceras del esquema mantienen
las tiradas largas en ~3 k chars, pero el presupuesto debe cubrir el peor caso sin
cortar la síntesis final.

| Familia | max_tokens |
|---|---|
| tarot_1, tarot_pregunta, espanola_1, etica | 1536 |
| tarot_2, multiturno, numerologia | 2048 |
| tarot_3, espanola_3 | 2560 |
| astro_natal | 3072 |
| espanola_5, sinastria | 4096 |
| espanola_7 | 5120 |
| cruz_celta, lectura_completa | 6144 |

`ejecutor_fase1.py` ya aplica PISO_MAX_TOKENS=4096 y PISOS_PESADOS=6144 para
cruz_celta/lectura_completa; la tabla queda expuesta en
`fase1_prompts.RECOMENDACION_MAX_TOKENS` como fuente única. Nota: `espanola_3` sin
esquema llegó a 5850 chars con 2560 tokens (ratio ~2,29); si se quisieran lecturas
de 3 cartas más largas, subir a 3072.

## 7. Cambio exacto necesario en `generate_tasks.py` (NO aplicado)

1. **Subir presupuesto de las dos familias truncadas** en los builders:
   - `Builder.cruz_celta` (línea ~598): `self.job("cruz_celta", prompt, {...}, 1600)`
     → `6144`.
   - `Builder.lectura_completa` (línea ~709): `self.job("lectura_completa", {...}, 1800)`
     → `6144`.
2. **Adoptar el esquema en los prompts del builder** (mismo texto que ya genera
   `fase1_prompts.construir_prompt`): insertar entre cuerpo y referencia la salida
   de `_esquema_texto(tarea)` para cruz_celta, y el bloque `_ESQUEMA_COMPLETA` para
   lectura_completa. Alternativa recomendada: que `generate_tasks.py` delegue el
   prompt en `fase1_prompts.construir_prompt` para no duplicar el texto.
3. **Nuevas familias baraja** en `TARGETS` (línea ~757) y `build_all.metodos`
   (línea ~769), p. ej.:
   ```python
   "espanola_1": 400, "espanola_3": 900, "espanola_5": 400, "espanola_7": 200,
   ```
   con builders `espanola_*` que:
   - sorteen de `cartas.NAIPES_ESPANOLES` (`rng.sample(..., n)`, sin reemplazo);
   - usen `referencia_baraja(cartas, KB_BARAJA, ctx)` sobre
     `kb/baraja_espanola.json` (nueva constante `KB_BARAJA = load_kb("baraja_espanola.json")`);
   - incluyan en el payload `{"cartas": [...], "contexto": ctx, "mazo": "espanol"}`
     y declaren en el cuerpo «Baraja española de 40 naipes: no es tarot ni baraja
     francesa» (texto literal ya en `fase1_prompts._cuerpo`);
   - fijen `max_tokens` según la tabla §6 (específicamente 2560/4096/5120).
4. El verificador del executor (`fase1_prompts.verificar_lectura`) ya distingue el
   mazo por `tarea['mazo']`/`universo_cartas`: basta que el payload lleve el universo
   de 40 naipes + extras de `universo_baraja()`.

## 8. Tests

`finetune/corpus/tests/test_fase1_prompts.py`: 52 tests sin LLM — 27 históricos de
compatibilidad, más esquema (orden, sección sin su carta, excede límite, falta
síntesis, lectura_completa en orden), baraja (universo de 40 con extras, ajena
`Reina de Copas`, 41.ª `Ocho de Oros` no confundida con el sinónimo naipe `8 de
Oros`, sinónimo `Caballero de Copas` legítimo, carta repetida) y filtro astrológico
(con/sin carta natal). `./finetune/scripts/check.sh` → CHECK OK.
