# Generación de la fase 1 (T95)

Guía operativa para generar las **12.536 lecturas pendientes** de `jobs.db` con
el ejecutor de fase 1, usando **Mercury 3** (nube) o los nodos locales. Ningún
comando de este documento se ha ejecutado durante T95: son las órdenes previstas
para la producción real.

## Estado de partida

Pendientes exactos por familia (consulta de solo lectura sobre `jobs.db`):

| familia | pendientes | `max_completion_tokens` |
|---|---:|---:|
| lectura_completa | 3.000 | 6144 |
| astro_natal | 1.500 | 3072 |
| tarot_3 | 1.400 | 2560 |
| tarot_1 | 936 | 1536 |
| espanola_3 | 900 | 2560 |
| multiturno | 800 | 2048 |
| tarot_pregunta | 800 | 1536 |
| sinastria | 600 | 4096 |
| cruz_celta | 500 | 6144 |
| espanola_1 | 400 | 1536 |
| espanola_5 | 400 | 4096 |
| tarot_2 | 400 | 2048 |
| numerologia | 400 | 2048 |
| etica | 300 | 1536 |
| espanola_7 | 200 | 5120 |
| **total** | **12.536** | |

Estimación con los datos del piloto T83 (4,1 s/lectura en Mercury, 169,9 s en
local; 840 tokens de entrada y 1.282 de salida por lectura):

- **Mercury, 3 workers:** ~4,8 h y ~6,7 USD con precios de lanzamiento
  (0,10 USD/1M entrada + 0,35 USD/1M salida).
- **Local, 4 workers:** ~148 h. Con 8 workers, ~74 h.
- Techo de salida si todas las respuestas agotan su presupuesto: 44,1M tokens.

La estimación exacta se obtiene con `--solo-estimar` (sección 2).

## 1. Antes de la primera llamada real

### 1.1 Opt-out del entrenamiento del proveedor

Los términos de Inception (resumen en `docs/PILOTO_MERCURY.md`, §8) permiten usar
las salidas para entrenar otro modelo, pero licencian los **prompts** para
entrenar los suyos salvo opt-out. Antes de generar:

1. Entrar en la API Platform de Inception → **User Settings**.
2. Dejar **OFF** la opción «Improve the model for everyone».
3. Guardar captura y fecha de la comprobación junto al registro de la pista.
4. Si no se puede confirmar que está OFF, **no usar Mercury**; generar solo en
   local.

### 1.2 Clave de Mercury solo en el entorno

La clave se lee exclusivamente de `INCEPTION_API_KEY`. No se lee de
`auth.json`, no se escribe en el repositorio y el ejecutor nunca la imprime. Para
evitar que quede en el historial de la shell:

```bash
read -rs INCEPTION_API_KEY
export INCEPTION_API_KEY
```

Comprobar que existe sin revelar su valor:

```bash
[ -n "$INCEPTION_API_KEY" ] && echo "INCEPTION_API_KEY definida" || echo "FALTA INCEPTION_API_KEY"
```

Al terminar la sesión:

```bash
unset INCEPTION_API_KEY
```

Si falta la variable, el ejecutor sale con código 2 y un mensaje que nombra
`INCEPTION_API_KEY`, sin crear copia de la BD ni llamar a la red.

### 1.3 Copia de trabajo y tildes de los prompts

Nunca ejecutar sobre `finetune/corpus/jobs.db`. El ejecutor ya crea una copia
`jobs.db.copia-AAAAMMDD-HHMMSS` antes de escribir, pero la copia de trabajo se
hace aparte para poder inspeccionarla y repetir sin tocar el original:

```bash
cd /Users/angelgonzalez/adivinacion-ia
cp finetune/corpus/jobs.db /tmp/fase1_mercury.db
```

Antes de la producción, revisar el desajuste D6 de
`docs/ENSAYO_FASE1_T75.md`: los pendientes generados con prompts viejos sin
tildes serán rechazados por `validate_synthetic` con `prompt_sin_tildes`. Si el
ensayo o una muestra lo confirma, regenerar los pendientes **sobre la copia** y
con el generador actualizado:

```bash
./finetune/.venv/bin/python finetune/corpus/generate_tasks.py \
  --db /tmp/fase1_mercury.db --replace-pending --seed 42
```

No reanudar los generadores suspendidos con prompts viejos (PIDs 66101 y 66396)
ni lanzar `--replace-pending` sobre la BD real.

El nodo1 (`10.0.0.3`) está reservado: el backend local usa únicamente
`http://10.0.0.4:8000/v1`. El valor por defecto del ejecutor ya es ese.

## 2. Estimación sin escribir nada

`--solo-estimar` abre la BD en modo solo lectura, no crea copia y muestra
pendientes por familia, presupuesto de salida, horas por backend y coste
estimado de Mercury:

```bash
./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_mercury.db --solo-estimar
```

También admite `--workers` para simular otro reparto. No ejecuta ninguna tarea.

## 3. Reparto sugerido por familia

**Opción recomendada: todo con Mercury.** Es la más rápida (~4,8 h con 3
workers) y el coste estimado es bajo (~6,7 USD). El backend local queda como plan
B o para ahorrar el gasto.

**Opción mixta (ahorro con coste en horas):** enviar a Mercury solo las familias
pesadas o de salida larga y dejar las cortas al nodo2. Las dos pasadas pueden
correr en paralelo sobre copias distintas de la BD.

| backend | familias | pendientes | tiempo estimado |
|---|---|---:|---:|
| Mercury | lectura_completa, astro_natal, espanola_3, sinastria, cruz_celta, espanola_5, espanola_7 | 7.100 | ~2,7 h con 3 workers |
| Local | tarot_1, tarot_3, multiturno, tarot_pregunta, tarot_2, numerologia, espanola_1, etica | 5.436 | ~64 h con 4 workers |

Si se elige la opción mixta, la pared de tiempo la marca el local (~64 h). Para
producción normal, usar Mercury para todo.

**Opción local pura:** ~148 h con 4 workers. Solo si no se puede usar la nube.

## 4. Comandos de generación

### 4.1 Mercury para las 12.536 (recomendado)

Primero un canario de 20 tareas para comprobar clave, cuota, formato y calidad.
El canario y la pasada completa comparten `--out-dir`, de modo que las aceptadas
se acumulan sin repetir las ya hechas:

```bash
./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_mercury.db \
  --backend mercury \
  --workers 3 \
  --formato sharegpt \
  --limite 20 \
  --out-dir /tmp/fase1_mercury_salida

./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_mercury.db \
  --backend mercury \
  --workers 3 \
  --formato sharegpt \
  --out-dir /tmp/fase1_mercury_salida
```

No hace falta `--model`: el valor por defecto es `mercury-3`. Tampoco se pasa la
clave por argumento. `--max-reintentos 2`, `--temperature 0.5` y
`--timeout 180` son los valores por defecto del backend.

### 4.2 Opción mixta (Mercury + local en paralelo)

Crear dos copias y dejar en cada una solo las familias asignadas. El `DELETE`
afecta únicamente a pendientes de la copia; no toca las filas ya hechas:

```bash
cp finetune/corpus/jobs.db /tmp/fase1_mercury.db
cp finetune/corpus/jobs.db /tmp/fase1_local.db

sqlite3 /tmp/fase1_mercury.db "
DELETE FROM jobs
WHERE status='pending' AND bloque NOT IN (
  'lectura_completa','astro_natal','espanola_3','sinastria',
  'cruz_celta','espanola_5','espanola_7'
);"

sqlite3 /tmp/fase1_local.db "
DELETE FROM jobs
WHERE status='pending' AND bloque NOT IN (
  'tarot_1','tarot_3','multiturno','tarot_pregunta','tarot_2',
  'numerologia','espanola_1','etica'
);"
```

Lanzar cada pasada en una terminal distinta:

```bash
./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_mercury.db \
  --backend mercury \
  --workers 3 \
  --formato sharegpt \
  --out-dir /tmp/fase1_mercury_salida

./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_local.db \
  --backend local \
  --endpoints http://10.0.0.4:8000/v1 \
  --workers 4 \
  --formato sharegpt \
  --out-dir /tmp/fase1_local_salida
```

Al final, unir solo las aceptadas para la validación posterior:

```bash
rm -rf /tmp/fase1_validar && mkdir -p /tmp/fase1_validar
cat /tmp/fase1_mercury_salida/aceptadas.jsonl \
    /tmp/fase1_local_salida/aceptadas.jsonl \
    > /tmp/fase1_validar/aceptadas.jsonl
```

### 4.3 Local para las 12.536 (plan B)

```bash
cp finetune/corpus/jobs.db /tmp/fase1_local.db

./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_local.db \
  --backend local \
  --endpoints http://10.0.0.4:8000/v1 \
  --workers 4 \
  --formato sharegpt \
  --out-dir /tmp/fase1_local_salida
```

No usar `10.0.0.3` mientras siga reservado.

### 4.4 Simulación sin red ni clave

Para comprobar la maquinaria antes de gastar cuota:

```bash
./finetune/.venv/bin/python finetune/corpus/ejecutor_fase1.py \
  --db /tmp/fase1_mercury.db \
  --backend mercury --simulado \
  --workers 3 --limite 10 \
  --out-dir /tmp/fase1_sim
```

Con `--simulado` no se exige `INCEPTION_API_KEY`. Para el backend local, cambiar
`--backend local`.

## 5. Vigilar el progreso

En otra terminal, contar estados de la copia:

```bash
sqlite3 /tmp/fase1_mercury.db \
  "SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY status;"
```

Progreso de las salidas (cada línea es una tarea terminada):

```bash
wc -l /tmp/fase1_mercury_salida/aceptadas.jsonl \
      /tmp/fase1_mercury_salida/rechazadas.jsonl

tail -f /tmp/fase1_mercury_salida/aceptadas.jsonl
```

`done` = aceptada, `failed` = rechazada tras reintentos, `pending` = todavía no
hecha o devuelta a la cola por un error de red. La pasada termina sola si en una
ventana de 50 tareas hay **más del 20 % de errores de red**; en ese caso sale con
código 3, imprime `PARADA DE SEGURIDAD` y deja el resto en `pending`. Revisar los
errores antes de relanzar:

```bash
sqlite3 /tmp/fase1_mercury.db \
  "SELECT substr(error,1,80), COUNT(*) FROM jobs
   WHERE status='pending' AND error IS NOT NULL GROUP BY 1;"
```

Motivos de rechazo (requiere `jq`):

```bash
jq -r '.motivos[]?' /tmp/fase1_mercury_salida/rechazadas.jsonl \
  | sort | uniq -c | sort -rn
```

Los rechazos quedan en `rechazadas.jsonl` con sus motivos y **nunca** pasan a
`aceptadas.jsonl`. Se pueden reintentar más adelante creando una copia en la que
esos `failed` vuelvan a `pending`.

## 6. Reanudar sin duplicar

Relanzar exactamente el mismo comando. El ejecutor:

- reclama cada fila de forma atómica y solo procesa `pending`;
- no repite las filas `done`;
- recupera las filas `running` huérfanas de un proceso caído (por defecto, más de
  30 minutos; ajustable con `--huerfano-minutos`);
- añade a `aceptadas.jsonl`/`rechazadas.jsonl` sin reescribir lo anterior;
- crea otra copia de la BD en cada arranque (las copias se acumulan en `/tmp`).

Para acotar una pasada, `--limite N` procesa como máximo N tareas. `Ctrl-C` una
sola vez: las tareas en vuelo vuelven a `pending` y la BD queda consistente.

## 7. Cadena posterior a la generación

### 7.1 Validación

Copiar **solo** las aceptadas a un directorio exclusivo: `validate_synthetic`
escanea todos los `*.jsonl` del directorio y no debe leer `rechazadas.jsonl`.

```bash
rm -rf /tmp/fase1_validar && mkdir -p /tmp/fase1_validar
cp /tmp/fase1_mercury_salida/aceptadas.jsonl /tmp/fase1_validar/aceptadas.jsonl

./finetune/.venv/bin/python finetune/corpus/validate_synthetic.py \
  --dir /tmp/fase1_validar \
  --out /tmp/fase1_validar/synthetic_clean.jsonl \
  --meta-out /tmp/fase1_validar/synthetic_clean.meta.jsonl \
  --report /tmp/fase1_validar/synthetic_report.json \
  --min-chars 400
```

Usar `--min-chars 400` (valor de producción). El ensayo T75 usó 60 porque el
lector simulado era breve; las lecturas reales de Mercury miden ~4.022
caracteres. Revisar `synthetic_report.json` antes de seguir.

### 7.2 Corpus real de partida

Si ya existen `finetune/corpus/train_final.jsonl` y `val_final.jsonl` (es el caso
del repositorio principal), **no hace falta** `build_dataset.py`: se pasan
directamente a `merge_final`. Solo si hay que regenerarlos desde el markdown
crudo:

```bash
./finetune/.venv/bin/python finetune/corpus/build_dataset.py \
  --raw finetune/corpus/raw \
  --out /tmp/fase1_real \
  --ratio 0.9 --seed 42
```

Comprobar antes con `--dry-run`. El filtro de licencias sigue en `off` por
defecto; cada documento conserva su procedencia.

### 7.3 Fusión con el corpus real

```bash
./finetune/.venv/bin/python finetune/corpus/merge_final.py \
  --real-train finetune/corpus/train_final.jsonl \
  --real-val finetune/corpus/val_final.jsonl \
  --synth /tmp/fase1_validar/synthetic_clean.jsonl \
  --synth-meta /tmp/fase1_validar/synthetic_clean.meta.jsonl \
  --out-dir /tmp/fase1_final \
  --seed 42
```

Genera `train.jsonl`, `val.jsonl`, `test.jsonl` y `report.json`. El test se
reserva del corpus real, sin fuga del sintético.

### 7.4 Preparación del entrenamiento

```bash
./finetune/.venv/bin/python finetune/corpus/preparar_entrenamiento.py \
  --dataset /tmp/fase1_final \
  --salida /tmp/fase1_chatml \
  --formato chatml \
  --epochs 3 \
  --max-longitud 2048
```

Sale con código 2 si el semáforo es rojo. Un semáforo amarillo no bloquea, pero
sus avisos (por ejemplo, cobertura incompleta de cartas) deben revisarse antes
de entrenar. Añadir `--estricto` si se quiere tratar el amarillo como error.

## 8. Checklist antes de lanzar

- [ ] Opt-out «Improve the model for everyone» confirmado OFF (o backend local).
- [ ] `INCEPTION_API_KEY` definida en el entorno, nunca en un fichero del repo.
- [ ] Copia de trabajo creada; la BD real no se toca.
- [ ] `--solo-estimar` revisado y pendientes esperados (12.536).
- [ ] D6 comprobado: prompts pendientes con tildes.
- [ ] Canario de 20 tareas aceptado (clave, cuota, formato ShareGPT).
- [ ] Nodo1 reservado; local solo contra `http://10.0.0.4:8000/v1`.
- [ ] Plan de vigilancia y de reanudación a mano.
