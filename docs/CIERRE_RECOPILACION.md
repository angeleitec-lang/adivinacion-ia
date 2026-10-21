# Cierre de la recopilación (T85)

Orquestador determinista que encadena los pasos finales de la fase 0 sobre los
ficheros de `/Users/angelgonzalez/fase0`, con copias previas, log JSONL,
reanudabilidad y parada en el primer fallo. Sin LLM propio: los pasos 2-4
delegan en las herramientas ya existentes (T71, T78, T66).

Script: `finetune/corpus/cierre_recopilacion.py`
Tests: `finetune/corpus/tests/test_cierre_recopilacion.py` (15 tests)

## Secuencia de pasos

| Paso | Nombre | Qué hace | Herramienta |
|---|---|---|---|
| 1 | `dedupe_consenso` | Deduplica `consenso.jsonl` conservando la ÚLTIMA versión por celda `(entidad_id, faceta)`, en orden de primera aparición. Si no hay duplicados: `sin_cambio` (sin copia). | interno |
| 2 | `limpieza_libros` | Genera la limpieza T71 en `libros_limpio/` y sustituye `libros/evidencias/evidencias.jsonl` (backup previo). Si el md5 ya coincide: `ya_aplicada`. Comprueba que ninguna evidencia retirada sigue vigente. | `aplicar_limpieza_libros.py` |
| 3 | `consenso_exclusion` | Relanza el consenso con `--excluir-claves --rehacer-celdas-con-exclusion` (T78). Verifica después que ninguna afirmación de sección excluida aparece en `mayoritarias`/`discrepancias`/`unica_fuente`. | `consenso_kb.py` |
| 4 | `kb_v2` | Reconstruye la KB v2 por familias. Verifica que ningún fichero de familia contiene entidades de otra familia (p. ej. `baraja_espanola.json` sin cartas de tarot). | `kb_v2.py` |
| 5 | `cobertura_v3` | OMITIDO mientras `cobertura_v3.py` no esté integrado en main (vive en `track/t82-cobertura-v3`, commit `350550b`). Si el fichero existe en `finetune/corpus/`, se ejecuta con `--libros limpio --excluir-claves`. | `cobertura_v3.py` (T82) |
| 6 | `informe_cierre` | Lee el log JSONL y escribe `cierre/informe_cierre.json` y `.md` con la tabla de pasos, estados y recuentos. | interno |

## Uso

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
CD=/Users/angelgonzalez/adivinacion-ia/.worktrees/t85-cierre-recopilacion/finetune/corpus

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
`--libros-limpio`, `--kb-out`, `--cobertura-out`, `--work-dir`,
`--familias-json`, `--simulado`, `--workers N`.

## Copias previas y deshacer

Cada paso que modifica un fichero deja antes una copia
`<fichero>.pre-cierre-<YYYYMMDD-HHMMSS>`:

- paso 1: `consenso.jsonl.pre-cierre-<ts>`
- paso 2: `evidencias.jsonl.pre-cierre-<ts>`
- paso 3: `consenso.jsonl.pre-exclusion-<ts>` (la pone `consenso_kb.py`)
- paso 4: los JSON de `kb_v2` se regeneran; la copia de seguridad de referencia
  es la de paso 1 (el consenso del que derivan).

Deshacer un paso = restaurar su copia previa:

```bash
cp consenso.jsonl.pre-cierre-<ts> consenso.jsonl   # deshace paso 1 (y posterior)
cp evidencias.jsonl.pre-cierre-<ts> evidencias.jsonl  # deshace paso 2
```

## Idempotencia y reanudabilidad

- Paso 1 sin duplicados → `sin_cambio`, no toca nada.
- Paso 2 con md5(limpio) == md5(vigente) → `ya_aplicada`.
- Paso 3: `consenso_kb.py` solo rehace celdas afectadas por la exclusión.
- El log `cierre/cierre_log.jsonl` registra por paso: ts, estado, recuentos y
  comandos ejecutados. Un fallo en cualquier paso aborta (`rc=1`) y se puede
  reanudar con `--paso N` tras corregir la causa.
- Escritura atómica (tmp + fsync + `os.replace`) en todas las salidas propias.

## Re-verificación sin reaplicar (T87)

Si un paso se aplicó correctamente pero su verificación falló, puede
re-verificarse sin reaplicar:

```bash
$PY $CD/cierre_recopilacion.py --paso 2 --solo-verificar
```

Es solo lectura (no ejecuta `aplicar_limpieza_libros.py` ni copia nada) y no
loquean los procesos vivos: útil mientras el paso 3 corre en producción.

## Correcciones T87 (falsos positivos de clave incompleta)

- **Paso 2**: la comprobación comparaba solo `hash_seccion`, pero una misma
  seccion puede estar retirada para una `(entidad_id, faceta)` y conservada
  legitimamente para otra (produccion 2026-10-21: 318 "vigentes" falsos).
  La clave correcta es `(hash_seccion, entidad_id, faceta)`.
- **Paso 3**: el chequeo de retiradas fuera del consenso marcaba como filtracion
  un texto identico que procedia de la web (la exclusion solo atane a secciones
  de libros). Ahora los textos presentes en las afirmaciones web se consideran
  legitimos y no se flaggean.
- Dedupe (clave = celda completa) y kb_v2 (familia por entidad) revisados:
  ya usaban claves completas.

## Aborto por procesos vivos

Antes de ejecutar (no en `--dry-run`) se comprueba con `pgrep -fl` que no hay
procesos escribiendo las salidas (`consenso_kb.py`, `afirmaciones_*.py`,
`evidencias_incremental.py`). Si los hay, aborta con `rc=1` y aviso.

## Salida del --dry-run real (2026-10-21)

Todas las entradas de los pasos 1-5 existen en fase0. Aborta correctamente por
proceso vivo:

```
AVISO: procesos vivos que escriben los ficheros del cierre:
  PID 96681: .../python consenso_kb.py --web-afirmaciones .../afirmaciones_full/afirmaciones.jsonl ...
Abortar el cierre hasta que terminen.
rc=1
```

## Comando de producción (NO ejecutar sin revisión)

Ejecutar SOLO cuando hayan terminado los procesos en vivo de la fase 0
(verificar con `pgrep -fl consenso_kb.py`):

```bash
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  /Users/angelgonzalez/adivinacion-ia/.worktrees/t85-cierre-recopilacion/finetune/corpus/cierre_recopilacion.py --todo
```

Revisar antes `--dry-run`, y después el `cierre/informe_cierre.md`. El paso 5
quedará omitido hasta que T82 se integre en main; entonces volver a lanzar
solo `--paso 5`.
