# Guía de reentrenamiento (fase 2)

Esta guía cubre **solo la fase 2**: convertir el dataset final en ficheros de
entrenamiento, lanzar un QLoRA y evaluarlo. La adquisición y la generación del
dataset están en [`docs/PIPELINE.md`](../docs/PIPELINE.md); no se repiten aquí.

> Estado verificado el 2026-10-20. El entorno de este repo tiene Python 3.11.15
> en `finetune/.venv`, pero **no** tiene `torch`, `transformers`, `peft`,
> `bitsandbytes` ni `soup`. El entrenamiento se hace en nodo1/nodo2, no en el
> Mac. Los comandos de Soup marcados como *sin verificar* no se han ejecutado.

## 0. Antes de empezar

### 0.1 Requisitos

- Python del proyecto: `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python`.
- `uv` para instalar dependencias; **no usar `pip`**.
- Dataset final en `finetune/corpus/final/{train,val,test}.jsonl` (ShareGPT).
- Casos de evaluación generados por `evaluacion_casos.py` (240 casos, sin
  respuestas de referencia).
- nodo1 con ROCm/PyTorch y espacio para el modelo base y los checkpoints.
  nodo2 es opcional para la segunda vuelta.

Comprobación de solo lectura del entorno:

```bash
cd /Users/angelgonzalez/adivinacion-ia
./finetune/entrenamiento/comprobar_entorno.sh
```

El script no instala nada. En el Mac avisa de que faltan torch, transformers,
peft, bitsandbytes y soup; eso es esperado.

### 0.2 Orden de la fase 2

```text
final/{train,val,test}.jsonl
  → preparar_entrenamiento.py        (validar, convertir, detectar fugas)
  → informe_entrenamiento.md        (semáforo; si rojo, no entrenar)
  → QLoRA 7B                        (iteración rápida)
  → evaluacion_casos.py → respuestas → evaluar_modelo.py
  → QLoRA 14B                       (modelo principal)
  → comparar 7B / 14B / base
```

No se entrena hasta que el informe salga en verde o, como mínimo, en amarillo
con los avisos revisados y aceptados por escrito. Un rojo bloquea el paso.

## 1. Preparar los ficheros de entrenamiento

```bash
cd /Users/angelgonzalez/adivinacion-ia
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python

$PY finetune/corpus/preparar_entrenamiento.py \
  --dataset finetune/corpus/final \
  --salida finetune/corpus/final/preparado \
  --formato chatml
```

Formatos disponibles:

| `--formato` | Estructura de salida | Uso |
|---|---|---|
| `chatml` (por defecto) | `{"messages":[{"role":"system"\|"user"\|"assistant","content":"…"}]}` | Soup con `format: chatml` |
| `sharegpt` | `{"conversations":[{"from":"system"\|"human"\|"gpt","value":"…"}]}` | Soup con `format: sharegpt` |
| `messages` | alias de `chatml` | compatibilidad |

El script:

1. Valida cada fila: `conversations` no vacío, roles conocidos, valores de
   texto no vacíos, como máximo un `system` al principio, cuerpo que empieza por
   `human`, turnos alternos y última respuesta `gpt`.
2. Convierte a `messages` o conserva `conversations`, normalizando Unicode NFC y
   eliminando campos superiores ajenos al formato.
3. Detecta fugas del conjunto de evaluación: ids `eval-*`, prompts idénticos,
   semillas reservadas (560056, 560057, 560058) y respuestas idénticas si se
   pasan con `--eval-respuestas`.
4. Calcula estadísticas por split, familia, longitudes, cartas, duplicados y
   horas estimadas.
5. Escribe `train/val/test` convertidos **solo si el semáforo no es rojo**,
   además de `estadisticas.json` e `informe_entrenamiento.md`.

Opciones útiles:

```bash
# Casos de evaluación explícitos (si no, se generan en memoria)
--eval-casos /tmp/eval_casos.jsonl

# Respuestas de un modelo ya evaluado, para detectar respuestas idénticas
--eval-respuestas /tmp/respuestas.jsonl

# Tokenizador local para contar tokens reales en vez de caracteres/3,5
--tokenizador /ruta/al/tokenizer.json

# Fallar también con semáforo amarillo (útil en CI o antes de una tanda)
--estricto
```

Códigos de salida: `0` verde o amarillo, `1` amarillo con `--estricto`, `2`
rojo. El rojo se activa con fugas de evaluación, train o val vacíos, más del
10 % de filas inválidas o más del 20 % de duplicados exactos cuando hay al menos
20 filas.

### 1.1 Qué revisar en el informe

- **Fugas**: deben ser cero. Cualquier coincidencia con `eval-*` impide entrenar.
- **Filas descartadas**: si hay inválidas, revisar los motivos y corregir el
  dataset; no ignorarlas sin más.
- **Duplicados**: miden respuestas idénticas normalizadas, no preguntas
  parecidas. Los duplicados exactos favorecen la memorización.
- **Familias**: las filas reales pueden no traer `familia`/`bloque`. Sin
  etiqueta, la estadística por familia sale vacía o incompleta; es un aviso, no
  un error de formato.
- **Baraja española**: si casi no aparecen naipes, el modelo no aprenderá ese
  mazo aunque el tarot esté bien cubierto.
- **Longitudes**: la media y el p95 orientan `max_length`; no sustituyen a un
  tokenizador real.
- **Horas**: son una estimación con supuestos fijos (QLoRA 4 bits, 4096 tokens,
  3 épocas, 400-750 tok/s en 7B y 180-350 tok/s en 14B —punto medio 550/250—,
  15 % de sobrecarga). **No se han medido** en nodo1/nodo2. Con el train v1
  (8,38 M de tokens por época) dan ~10-20 h para el 7B y ~23-45 h para el 14B.

### 1.2 Defectos conocidos del dataset actual

Comprobados en una muestra de `finetune/corpus/final`:

- Hay filas de tema ajeno al producto (por ejemplo, una pregunta sobre
  «Televisión») con respuestas de edición de Wikipedia.
- `val` contiene respuestas en italiano.
- `test` tiene muy pocas filas (3 en la instantánea revisada).
- Conviven dos system prompts distintos y muchas filas no traen familia.
- La cobertura de baraja española es muy baja en la muestra.

El informe no corrige el contenido: lo señala. La limpieza semántica sigue
siendo una tarea aparte de la fase 1.

## 2. Configuraciones QLoRA

Ficheros:

- `finetune/entrenamiento/qlora_7b.yaml` — iteración rápida, Qwen2.5-7B-Instruct.
- `finetune/entrenamiento/qlora_14b.yaml` — modelo principal, Qwen2.5-14B-Instruct.

Ambas usan `task: sft`, `format: chatml`, 4 bits NF4 con doble cuantización,
LoRA y `max_length: 4096` (ajustado en T111 a las longitudes reales del
dataset v1: p50 1.510, p95 3.233, p99 3.869, máx 4.166 tokens estimados;
4096 cubre ≥99,8 % sin truncar —solo 10 filas de 5.205 por encima, <0,01 %
de tokens— y 6144/8192 no aportan nada). Los valores de `lr`, tamaño de
batch, acumulación y `r`/`alpha` son puntos de partida razonables, **no
resultados medidos**.

Recalculo de estas cifras con el venv del proyecto (sin red):

```bash
$PY finetune/entrenamiento/ajuste_config.py --dataset /Users/angelgonzalez/fase0/dataset_fase1_v1
```

**Pérdida solo sobre la respuesta del asistente (T111)**: la pérdida debe
calcularse únicamente en los tokens de los turnos `assistant`/`gpt`; los
turnos `system` y `human` van enmascarados. Es el comportamiento estándar
del SFT en ChatML (mask sobre el prompt), pero en Soup **no está verificado**:
antes de la tanda hay que comprobar con `soup --help` el nombre de la clave
(`train_on_prompt: false` o equivalente) y confirmar en el log que system/user
no contribuyen a la pérdida. Si la herramienta entrena también sobre el
prompt, el modelo gastaría capacidad en memorizar las instrucciones y las
consultas en lugar de las lecturas.

> **Sin verificar**: el CLI de Soup no está instalado y las claves exactas del
> YAML se contrastaron solo con la documentación del proyecto. Antes de una
> tanda larga, ejecutar `soup --help`, validar la configuración con el modo de
> prueba de Soup y confirmar que acepta `data.format: chatml`. No se documentan
> subcomandos de Soup que no se hayan comprobado.

## 3. Entrenar el 7B

En nodo1, desde la raíz del repo:

```bash
# 1. Comprobar entorno y dependencias
./finetune/entrenamiento/comprobar_entorno.sh

# 2. Confirmar que el informe no está en rojo
grep -m1 "Semáforo" finetune/corpus/final/preparado/informe_entrenamiento.md

# 3. Consultar el CLI instalado y usar su modo de prueba
# No se documenta un subcomando concreto porque no está verificado.
soup --help
```

Si la prueba corta es correcta, lanzar el entrenamiento con la configuración
7B. Guardar el log completo y el checkpoint en
`finetune/entrenamiento/salida/7b`. No se debe lanzar el 14B hasta tener una
evaluación del 7B y haber revisado sus fallos.

## 4. Evaluar

La evaluación es determinista sin juez LLM. Genera 240 casos (20 por familia)
y exige los 240 ids salvo que se use `--permitir-faltantes`.

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python

$PY finetune/corpus/evaluacion_casos.py --salida /tmp/eval_casos.jsonl

# respuestas.jsonl: una línea por caso, {"id":"eval-…","respuesta":"…"}
$PY finetune/corpus/evaluar_modelo.py \
  --casos /tmp/eval_casos.jsonl \
  --respuestas /tmp/respuestas_7b.jsonl \
  --salida /tmp/evaluacion_7b

# Comparación entre dos informes
$PY finetune/corpus/evaluar_modelo.py --comparar \
  /tmp/evaluacion_7b/informe.json /tmp/evaluacion_14b/informe.json
```

El informe da tasa de aprobados global y por familia, puntuación media, resultado
por comprobación y los peores casos. El juez LLM (`--juez-llm`) es opcional y
solo añade una nota 1–5; no sustituye a las comprobaciones deterministas.

## 5. Umbrales de aceptación propuestos

Estos umbrales se fijan **antes** de medir para no ajustarlos a posteriori. No
están validados todavía con un modelo entrenado.

| Ámbito | Umbral propuesto | Motivo |
|---|---:|---|
| Cálculos deterministas (fechas, números, cartas, posiciones) | 100 % de comprobaciones | Un cálculo mal hecho invalida la lectura |
| Ética y fuera de alcance | 100 % | No debe inventar ni diagnosticar |
| Tarot (78 cartas) | ≥ 85 % de casos aprobados | Es el núcleo del producto |
| Baraja española (40 naipes) | ≥ 80 % | Hoy tiene poca cobertura; el listón inicial es menor |
| Astrología, numerología y biorritmos | ≥ 85 % cada familia | Tienen cálculos verificables |
| Global | ≥ 85 % | Media ponderada por familia |
| Ninguna familia | < 70 % | Evita un modelo fuerte en tarot y flojo en el resto |
| Idioma | 100 % en español | Requisito del producto |
| Longitud | ≥ 90 % de casos dentro del mínimo | Una respuesta correcta pero truncada no sirve |
| Regresión frente al base | Caída ≤ 5 puntos | El fine-tune no debe empeorar lo que ya funcionaba |

Con 20 casos por familia, un intervalo aproximado del 95 % ronda ±9 puntos
porcentuales; diferencias menores no deben interpretarse como mejoras reales.
Para decidir entre 7B y 14B, repetir la evaluación y mirar también los peores
casos, no solo la media.

## 6. Riesgos

- **Calidad del dataset**: hay ruido temático y respuestas de fuentes poco
  fiables. El filtro de formato no detecta errores de contenido.
- **Fuga de evaluación**: si los casos reservados acaban en train, la métrica
  deja de ser honesta. `preparar_entrenamiento.py` lo comprueba, pero también
  hay que mantener las semillas reservadas fuera de la generación.
- **Test diminuto**: con 3 filas no se puede concluir nada; usar val y la
  evaluación por familias, y ampliar test antes de decisiones importantes.
- **System prompts mezclados**: el modelo puede aprender dos estilos. Unificar
  el prompt o etiquetar el estilo antes de entrenar.
- **QLoRA 4 bits**: ahorra memoria, pero puede perder calidad frente a bf16. No
  se ha comparado en este proyecto.
- **MoE**: `DECISION_MODELO_MOE.md` propone Qwen3.5-35B-A3B como candidato, pero
  QLoRA en MoE requiere cuidado (no cuantizar el router). No usar esas recetas
  con el YAML denso de 7B/14B.
- **Hardware**: ROCm, memoria y velocidad no están medidos. Las horas del
  informe son estimaciones.
- **Exportación**: el paso a GGUF y la cuantización posterior no están probados
  en este repo.
- **Legalidad**: la licencia del modelo base y de las fuentes del corpus debe
  revisarse antes de publicar el producto.

## 7. Checklist antes de dar una tanda por buena

- [ ] `preparar_entrenamiento.py` termina sin rojo.
- [ ] Cero fugas de evaluación.
- [ ] Menos del 10 % de filas inválidas y revisadas las causas.
- [ ] Informe guardado junto al dataset preparado.
- [ ] `comprobar_entorno.sh` ejecutado en la máquina que entrena.
- [ ] Configuración de Soup validada con una prueba corta.
- [ ] Evaluación de los 240 casos, sin faltantes.
- [ ] Umbrales de la sección 5 revisados y comparados con el modelo base.
- [ ] Fallos residuales anotados antes de pasar al 14B.

## 8. Referencias

- Pipeline completo y formatos: [`docs/PIPELINE.md`](../docs/PIPELINE.md).
- Elección de modelo: [`MODELO.md`](MODELO.md) y
  [`DECISION_MODELO_MOE.md`](DECISION_MODELO_MOE.md).
- Cobertura prevista: [`PLAN_COBERTURA.md`](PLAN_COBERTURA.md).
- Script de preparación: [`corpus/preparar_entrenamiento.py`](corpus/preparar_entrenamiento.py).
- Configs: [`entrenamiento/qlora_7b.yaml`](entrenamiento/qlora_7b.yaml) y
  [`entrenamiento/qlora_14b.yaml`](entrenamiento/qlora_14b.yaml).
