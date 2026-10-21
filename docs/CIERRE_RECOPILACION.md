# Cierre de la recopilación (T85 / T90)

Orquestador determinista que encadena los pasos finales de la fase 0 sobre los
ficheros de `/Users/angelgonzalez/fase0`, con copias previas, log JSONL,
reanudabilidad y parada en el primer fallo. Sin LLM propio: los pasos delegan en
las herramientas ya existentes (T71, T88, T78, T66, T82).

Script: `finetune/corpus/cierre_recopilacion.py`
Tests: `finetune/corpus/tests/test_cierre_recopilacion.py`

> **T90**: se inserta el **filtro de atribución (T88)** como **paso 3** y se
> renumerán los pasos posteriores. El paso de consenso ahora admite **varias
> listas de claves** (T71 + T88) unidas por clave.

## Secuencia de pasos

| Paso | Nombre | Qué hace | Herramienta |
|---|---|---|---|
| 1 | `dedupe_consenso` | Deduplica `consenso.jsonl` conservando la ÚLTIMA versión por celda `(entidad_id, faceta)`, en orden de primera aparición. Si no hay duplicados: `sin_cambio` (sin copia). | interno |
| 2 | `limpieza_libros` | Genera la limpieza T71 en `libros_limpio/` y sustituye `libros/evidencias/evidencias.jsonl` (backup previo). Si el md5 ya coincide: `ya_aplicada`. Comprueba que ninguna evidencia retirada sigue vigente (clave completa). | `aplicar_limpieza_libros.py` |
| 3 | `filtro_atribucion` | **(T90)** Aplica el filtro de atribución T88 a `evidencias_web/evidencias.jsonl` y `libros/evidencias/evidencias.jsonl` (ya limpias): retira evidencias de astrología/numerología mal atribuidas. Copia previa por origen (`pre-filtro-atrib`), reescritura atómica y verificación por **clave COMPLETA** `(hash_seccion, entidad_id, faceta)`. Idempotente (`ya_aplicada`). Escribe retiradas y conservadas **por origen** y las claves T88 en `filtro_atribucion/`. | `filtro_atribucion.py` (T88) |
| 4 | `consenso_exclusion` | Relanza el consenso con `--excluir-claves` (**T71 + T88**, repetible) y `--rehacer-celdas-con-exclusion` (T78). Las claves se unen por `(entidad_id, faceta)`, de modo que una celda afectada por ambas listas se rehace **una sola vez**. Verifica después que ninguna afirmación de sección excluida aparece en `mayoritarias`/`discrepancias`/`unica_fuente`. | `consenso_kb.py` |
| 5 | `kb_v2` | Reconstruye la KB v2 por familias. Verifica que ningún fichero de familia contiene entidades de otra familia. | `kb_v2.py` |
| 6 | `cobertura_v3` | Regenera la cobertura v3 con las claves de exclusión (T71 + T88). Si `cobertura_v3.py` no está integrado, se omite con aviso. | `cobertura_v3.py` (T82) |
| 7 | `informe_cierre` | Lee el log JSONL y escribe `cierre/informe_cierre.json` y `.md` con la tabla de pasos, estados y recuentos. | interno |

## Orden correcto tras aplicar el filtro (T90)

El filtro (paso 3) debe ir **después** de la limpieza de libros (paso 2) y
**antes** del consenso (paso 4), porque el consenso consume las claves de
exclusión que genera el filtro. `--todo` respeta este orden: `1 → 2 → 3 → 4 → 5 → 6 → 7`.

## Uso

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
CD=/Users/angelgonzalez/adivinacion-ia/.worktrees/t90-aplicar-atribucion/finetune/corpus

# 1) Comprobar entradas, procesos vivos y espacio (no escribe nada)
$PY $CD/cierre_recopilacion.py --dry-run

# 2) Ejecutar todo el encadenado
$PY $CD/cierre_recopilacion.py --todo

# 3) Un paso concreto (reanudable tras un fallo)
$PY $CD/cierre_recopilacion.py --paso 3
```

Opciones de rutas: `--base-dir` cambia la raíz (por defecto `/Users/angelgonzalez/fase0`);
overrides finos: `--consenso`, `--consenso-dir`, `--evidencias-libros`,
`--secciones-dir`, `--afirmaciones-libros-dir`, `--afirmaciones-libros-file`,
`--afirmaciones-web-file`, `--evidencias-web`, `--claves-excluir`,
`--claves-atribucion`, `--procesados-web`, `--procesados-libros`,
`--libros-limpio`, `--filtro-atribucion-out`, `--kb-out`, `--cobertura-out`,
`--work-dir`, `--familias-json`, `--simulado`, `--workers N`.

## Copias previas y deshacer

Cada paso que modifica un fichero deja antes una copia con marca de tiempo:

- paso 1: `consenso.jsonl.pre-cierre-<ts>`
- paso 2: `evidencias.jsonl.pre-cierre-<ts>`
- paso 3: `evidencias.jsonl.pre-filtro-atrib-<ts>` (web y libros, por origen)
- paso 4: `consenso.jsonl.pre-exclusion-<ts>` (la pone `consenso_kb.py`)
- paso 5: los JSON de `kb_v2` se regeneran; la copia de referencia es la de paso 1.

Deshacer un paso = restaurar su copia previa.

## Idempotencia y reanudabilidad

- Paso 1 sin duplicados → `sin_cambio`, no toca nada.
- Paso 2 con md5(limpio) == md5(vigente) → `ya_aplicada`.
- Paso 3: si tras el filtro ningún origen cambia y no hay retiradas → `ya_aplicada`
  (las conservadas coinciden con las vigentes). Reejecutar es seguro.
- Paso 4: `consenso_kb.py` solo rehace celdas afectadas por la exclusión; una
  celda en ambas listas se rehace una sola vez (claves unidas por `(entidad, faceta)`).
- El log `cierre/cierre_log.jsonl` registra por paso: ts, estado, recuentos y
  comandos. Un fallo aborta (`rc=1`) y se reanuda con `--paso N`.
- Escritura atómica (tmp + fsync + `os.replace`) en todas las salidas propias.

## Re-verificación sin reaplicar (T87 / T90)

Un paso ya aplicado puede re-verificarse sin reaplicar (solo lectura, no loquean
los procesos vivos). Aplica a los pasos **2 y 3**:

```bash
$PY $CD/cierre_recopilacion.py --paso 2 --solo-verificar   # limpieza T71
$PY $CD/cierre_recopilacion.py --paso 3 --solo-verificar   # filtro T88
```

`--solo-verificar` con cualquier otro paso (`--paso 4`, etc.) es error de uso.

## Claves de exclusión: varias listas (T90)

`consenso_kb.py --excluir-claves` es ahora **repetible** (`action="append"`) y
`cargar_claves_exclusion` acepta una ruta o una lista de rutas. El cierre pasa
dos listas al consenso:

- `libros_limpio/claves_excluir_consenso.jsonl` (T71)
- `filtro_atribucion/claves_excluir_consenso.jsonl` (T88)

Se unen en un único `dict (entidad_id, faceta) -> set(hash_seccion)`, así que
una celda que aparece en ambas se rehace una sola vez.

## Correcciones T87 (falsos positivos de clave incompleta)

- **Paso 2**: la comprobación comparaba solo `hash_seccion`, pero una misma
  seccion puede estar retirada para una `(entidad_id, faceta)` y conservada
  legitimamente para otra. La clave correcta es `(hash_seccion, entidad_id, faceta)`.
- **Paso 4**: el chequeo de retiradas fuera del consenso no marca como filtración
  un texto idéntico que procedía de la web.
- El paso 3 (filtro) usa la misma clave COMPLETA para su verificación.

## Aborto por procesos vivos

Antes de ejecutar (no en `--dry-run`) se comprueba con `pgrep -fl` que no hay
procesos escribiendo las salidas (`consenso_kb.py`, `afirmaciones_*.py`,
`evidencias_incremental.py`). Si los hay, aborta con `rc=1` y aviso.

## Salida del --dry-run real (2026-10-21, rama T90)

Todas las entradas de los pasos 1-6 existen en fase0 (incluido el paso 3 del
filtro). Aborta correctamente por proceso vivo:

```
== DRY RUN: no se escribe nada ==
  [OK ] paso 3: /Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl
  [OK ] paso 3: /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl
  [OK ] paso 3: /Users/angelgonzalez/fase0/libros/secciones
  ...
AVISO: procesos vivos que escriben los ficheros del cierre:
  PID 54326: .../python -u afirmaciones_rapido.py --workers 3
Abortar el cierre hasta que terminen.
rc=1
```

## Comando de producción (NO ejecutar sin revisión)

Ejecutar SOLO cuando hayan terminado los procesos en vivo de la fase 0
(verificar con `pgrep -fl 'consenso_kb.py|afirmaciones_'`):

```bash
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  /Users/angelgonzalez/adivinacion-ia/.worktrees/t90-aplicar-atribucion/finetune/corpus/cierre_recopilacion.py --todo
```

Revisar antes `--dry-run`, y después el `cierre/informe_cierre.md`. Para aplicar
solo el filtro de atribución sin tocar el resto: `--paso 3`.
