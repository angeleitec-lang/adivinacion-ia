# Auditoría ronda 7 (T123)

Fecha: 2026-10-22. Rama `track/t123-auditoria-ronda7`.

Alcance: verificar las familias nuevas de fase 1 (`transitos`, `revolucion_solar`,
`biorritmos`, `fuera_alcance`, `sinastria`), revisar lecturas reales de
`fase1_mercury_b`, probar fugas de evaluación/splits y auditar el verificador de
traducción T116. Solo lectura sobre los datos; no se ha llamado a ningún LLM ni a
Mercury y no se ha modificado el código auditado.

Artefactos:

- `finetune/corpus/auditoria_ronda7.py`: casos adversos y buenos, revisión de
  lecturas reales, pruebas de fugas y de traducción. Ejecutable con
  `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python finetune/corpus/auditoria_ronda7.py --json /tmp/ronda7.json`.
- `finetune/corpus/tests/test_auditoria_ronda7.py`: 15 pruebas; las 12 que
  fallan hoy están marcadas `expectedFailure` con el comportamiento correcto.
- Datos reales: `/Users/angelgonzalez/fase0/fase1_mercury_b/aceptadas.reverificadas.jsonl`
  (2242 filas).

## Resumen ejecutivo

| Componente | Casos | Aciertos | Defectos graves | Medios | Leves |
|---|---:|---:|---:|---:|---:|
| `_verif_transitos` | 18 adversos + 12 buenos | 6/18 y 12/12 | 1 | 1 | 1 |
| `_verif_revolucion` | 18 + 12 | 8/18 y 12/12 | 1 | 1 | 1 |
| `_verif_biorritmos` | 18 + 12 | 9/18 y 12/12 | 1 | 1 | 1 |
| `_verif_negativa_alcance` | 18 + 12 | 8/18 y 10/12 | 2 | 1 | 1 |
| Sinastría (sin verificador) | 18 + 12 | 4/18 y 12/12 | 1 | 1 | 0 |
| Lecturas reales (60) | 60 | 14/60 con hallazgos | 2 | 1 | 2 |
| Fugas evaluación/splits | 6 variantes + 3 splits | 5/6 variantes | 1 | 1 | 1 |
| Traducción T116 | 20 | 18/20 | 1 | 1 | 1 |

Totales de fase 1: 35/90 casos adversos detectados (38,9 %; 55 falsos
negativos) y 58/60 lecturas buenas aceptadas (2 falsos positivos). El
verificador actual no está diseñado para las familias nuevas: solo cubre una
construcción literal de tránsitos, el Sol/Ascendente de la RS y los porcentajes
de biorritmos.

## Fase 1: casos adversos y buenos

Metodología: 18 lecturas adversas y 12 buenas por familia, con tareas y
cálculos coherentes. Se considera fallo del verificador el adverso aceptado
(falso negativo) y la buena rechazada (falso positivo).

| Familia | Adversos detectados | FN | Buenos aceptados | FP |
|---|---:|---:|---:|---:|
| `transitos` | 6/18 | 12 | 12/12 | 0 |
| `revolucion_solar` | 8/18 | 10 | 12/12 | 0 |
| `biorritmos` | 9/18 | 9 | 12/12 | 0 |
| `fuera_alcance` | 8/18 | 10 | 10/12 | 2 |
| `sinastria` | 4/18 | 14 | 12/12 | 0 |

Adversos no detectados (lista literal del informe):

- `transitos`: T-A2, T-A3, T-A4, T-A5, T-A6, T-A9, T-A10, T-A11, T-A12,
  T-A13, T-A17, T-A18.
- `revolucion_solar`: R-A4, R-A6, R-A7, R-A8, R-A9, R-A10, R-A11, R-A13,
  R-A16, R-A17.
- `biorritmos`: B-A3, B-A4, B-A5, B-A6, B-A7, B-A8, B-A13, B-A14, B-A17.
- `fuera_alcance`: F-A2, F-A6, F-A8, F-A9, F-A10, F-A11, F-A12, F-A15,
  F-A17, F-A18.
- `sinastria`: S-A1, S-A2, S-A3, S-A4, S-A5, S-A6, S-A7, S-A8, S-A9,
  S-A10, S-A11, S-A15, S-A17, S-A18.

### Transitos

`_verif_transitos` (`finetune/corpus/fase1_prompts.py:1536-1552`) solo busca
`X hace Y a su Z natal` contra `calculos.transitos.aspectos`. No comprueba:

- posiciones de planetas en tránsito (el cálculo solo trae aspectos);
- fechas distintas de `fecha_transito`;
- casas, grados, retrogradación;
- recuentos («hay tres tránsitos») ni construcciones sin «hace»;
- que el texto no niegue los tránsitos calculados.

Ejemplo T-A10: «Marte cuadratura tu Sol natal» (sin «hace») pasa. T-A11:
«El Sol en tránsito en Leo» pasa porque `_verif_sol` compara con el Sol natal y
el cálculo no contiene posiciones de tránsito. T-A4/T-A12/T-A13: fechas
inventadas pasan porque el verificador no lee `fecha_transito`.

Arreglo propuesto:

1. En `calculos/astro.py` (`datos_proyeccion`, tránsitos) añadir
   `posiciones` con `planeta`, `signo`, `grado`, `retrogrado` y `casa`.
2. En `fase1_prompts.py`, sustituir `_RE_TRIPLE_TRANSITO` por
   `(?P<pt>[a-z]+)\s+(?:en\s+transito\s+)?(?:hace|forma)\s+(?P<asp>[a-z]+)\s+(?:a\s+)?(?:su|tu)\s+(?P<pn>[a-z]+)\s+natal`
   y añadir un segundo patrón para `X (en tránsito) en Signo`, comparando con
   `posiciones`. Rechazar cualquier fecha que no sea `transitos.fecha_transito`
   y cualquier casa que no esté en los aspectos o en la carta natal.
3. Si no se quieren añadir posiciones, rechazar toda afirmación de posición de
   tránsito no calculada en vez de aceptarla.

### Revolución solar

`_verif_revolucion` (`fase1_prompts.py:1555-1576`) solo compara Sol y
Ascendente cuando el texto lleva la marca `rs`/`de la revolucion`. No comprueba
Luna, Mercurio, Venus, Marte, Júpiter, Saturno, Urano, Neptuno, Plutón, Medio
Cielo, casas, fechas ni el año. R-A6 y R-A16 (Luna RS en signo incorrecto),
R-A7 (planetas inventados), R-A8 (fecha), R-A9 (MC), R-A10 (casa), R-A11 (Sol
natal) y R-A17 (Descendente) pasan.

Arreglo propuesto:

- Construir `planetas_rs = {nombre: signo}` desde
  `rs["carta"]["planetas"]` y comparar todas las menciones con marca explícita
  de RS. Mantener una comparación separada contra `carta_natal` cuando el texto
  diga `natal`.
- Añadir `rs["mc"]["signo"]`, `rs["descendente"]["signo"]` y las cuspides de
  casas si el cálculo las trae; si no las trae, rechazar su afirmación.
- Comparar `rs["instante_ut"]` con cualquier fecha del texto y rechazar años
  distintos.

### Biorritmos

`_verif_biorritmos` (`fase1_prompts.py:1579-1616`) solo compara el porcentaje
más cercano con tolerancia ±5. No comprueba fase (`ascendente`, `descendente`,
`crítico`), «día crítico», días hasta el pico, duración del ciclo, fecha ni
rango ±100. B-A3, B-A4, B-A5, B-A6, B-A7, B-A8, B-A13, B-A17 pasan.

Arreglo propuesto:

- Leer `ciclos[clave]["fase"]` y comparar con la fase afirmada, exigiendo que
  la fase esté pegada al nombre del ciclo o al porcentaje («físico al 40% y
  descendente»), y no con frases futuras («recupere dirección ascendente»).
- Rechazar «día/ciclo crítico» si ningún ciclo tiene `fase == "critico"`.
- Añadir `dias_al_pico` y `duracion` a `calculos/biorritmos.biorritmos()` o
  calcularlos en el verificador a partir de `periodo` y `valor`; comparar
  cualquier «faltan N días para el pico» y las duraciones 23/28/33.
- Comparar la fecha del texto con `calculos.biorritmos.fecha`.

### Fuera de alcance

`_verif_negativa_alcance` (`fase1_prompts.py:1619-1626`) exige una frase de
rechazo y una alternativa en cualquier parte del texto, pero no comprueba que
no se responda la técnica prohibida ni que coincida con `tarea["tecnica"]`.
F-A2, F-A8, F-A9, F-A10, F-A11, F-A12, F-A15, F-A17 y F-A18 rechazan de palabra
y después responden quiromancia, I Ching, runas o vidas pasadas. F-A6 rechaza
otra técnica distinta de la pedida.

Además, los casos de evaluación usan `familia="etica"` y
`tema="fuera_alcance"` (`evaluacion_casos.py:469-487`), por lo que
`_verif_negativa_alcance` no se ejecuta en evaluación.

Arreglo propuesto:

1. Aplicar la comprobación también cuando
   `tarea.get("tema") == "fuera_alcance"` o `tarea.get("familia") == "etica"`
   con `tecnica` de la lista prohibida.
2. Tras el rechazo, prohibir marcadores de la técnica pedida (por ejemplo,
   `linea de la vida`, `monte de venus`, `hexagrama`, `runa`, `tirada
   lenormand`, `nakshatra`, `dasha`, `bazi`, `pendulo`, `bola de cristal`,
   `posos`, `aura`, `mediumnidad`) y de cualquier otra técnica de
   `TECNICAS_FUERA` si se está respondiendo, no solo nombrando.
3. Exigir que `tarea["tecnica"]` aparezca en el rechazo y que la alternativa
   pertenezca al producto (`tarot`, `baraja`, `astrologia`, `carta natal`,
   `numerologia`, `transitos`, `revolucion solar`, `biorritmos`).
4. Ampliar `_RECHAZO_ALCANCE` con `queda fuera de lo que trabajo` y
   `_ALTERNATIVA_TECNICAS` con `numerol[oó]g` para eliminar los dos falsos
   positivos F-B4 y F-B8.

### Sinastría

No existe `_verif_sinastria`; `verificar_lectura`
(`fase1_prompts.py:1629-1660`) no llama a nada que revise esta familia. Los
cálculos solo traen aspectos intra-carta (`carta_a.aspectos`,
`carta_b.aspectos`), no aspectos cruzados. Cualquier «Venus de A trígono Marte
de B» es, por tanto, no verificable o inventado. S-A1, S-A2, S-A8, S-A10,
S-A17 y S-A18 pasan; también pasan posiciones incorrectas (S-A5, S-A6, S-A11),
casas superpuestas (S-A7), fechas (S-A9) y la negación de aspectos calculados
(S-A4). S-A15 (promesa médica) sí lo coge `_verif_promesas`.

Arreglo propuesto:

- Añadir `_verif_sinastria(calc, texto, motivos)` y llamarla desde
  `verificar_lectura` para `familia == "sinastria"`.
- Calcular aspectos cruzados con `lon` de `carta_a.planetas` y
  `carta_b.planetas` (0/60/90/120/180 con orbes de 6-7°) y comparar las
  menciones `p1 de A asp p2 de B`; rechazar las que no estén.
- Comparar `planeta en signo` con la carta A o B indicada; si no se indica
  carta y no coincide con ninguna, rechazar.
- Comparar casas con las de cada carta y rechazar casas superpuestas
  inventadas.

## Fase 2: 60 lecturas reales

Muestra: 10 lecturas por familia de `fase1_mercury_b` (transitos, RS,
biorritmos, sinastría, astro_natal, fuera_alcance). Se revisaron los datos del
prompt/cálculo contra la respuesta, no solo la forma.

| Familia | Con hallazgos | Detalle |
|---|---:|---|
| `transitos` | 1/10 | 35582: «Tu Sol en Aries, Venus y Luna en Tauro»; la natal tiene Venus en Aries y el cálculo no trae posiciones de tránsito. |
| `revolucion_solar` | 0/10 | Las 10 usan correctamente posiciones natales; no se ha confirmado ningún error RS en la muestra. |
| `biorritmos` | 0/10 | Sin contradicciones tras corregir la atribución de porcentajes del auditor (ver nota). |
| `sinastria` | 3/10 | 28620: 8 aspectos cruzados no calculados; 28621: 2; 28626: «Júpiter en Aries» no está en ninguna carta. |
| `astro_natal` | 0/10 | 37181 y 37175 son correctos. |
| `fuera_alcance` | 10/10 | Prompts con `Pregunta del consultante: "<n> <arranque>:"`; la pregunta real desaparece. |

Nota de transparencia: la primera pasada del auditor marcó 36380 y 36384 como
errores de biorritmos. Eran falsos positivos del propio auditor: 36380 habla de
«recupere dirección ascendente» en futuro y 36384 dice «63% físico» y «90%
emocional». Corregida la atribución por adyacencia, la muestra queda 0/10.

### Defecto grave de datos: fuera_alcance

En las 10 lecturas reales el prompt contiene, por ejemplo:

```
Pregunta del consultante: "0 Tengo curiosidad:"
```

y el payload es `{"tecnica": ["vidas pasadas", "¿Quién fui...?"]}`. La causa
está en `generate_tasks.py:977-986`:

```python
for (tecnica, pregunta_base), arranque in zip(self._pares_fuera(), range(n)):
    pregunta = f"{arranque} {pregunta_base}"
    ...
    payload = {"tecnica": tecnica}
```

`_pares_fuera()` ya devuelve `((tecnica, pregunta_base), arranque)`; el
`zip(..., range(n))` añade un segundo nivel y desplaza las variables:
`tecnica` acaba siendo la tupla `(tecnica, pregunta)`, `pregunta_base` el
arranque y `arranque` el índice `0, 1, ...`. Resultado: `"0 Verás,"`,
`"1 Verás,"`, etc., y un payload con la técnica y la pregunta mezcladas.

Arreglo exacto:

```python
from itertools import islice

for (tecnica, pregunta_base), arranque in islice(self._pares_fuera(), n):
    pregunta = f"{arranque} {pregunta_base}"
    ...
    payload = {"tecnica": tecnica, "pregunta": pregunta}
```

Esto invalida las 400 filas de `fuera_alcance` actuales para entrenamiento:
no contienen la pregunta que el modelo debía rechazar. Hay que regenerarlas
(con copia previa de `jobs.db`) o filtrarlas del dataset.

## Fase 3: fugas de evaluación y solapes de split

Se generaron los 240 casos de `evaluacion_casos.generar_casos(560056)` y se
probaron variantes del prompt de un caso en una fila de train, usando
`qa_dataset.fugas_eval` y `qa_dataset.fugas_splits`.

| Variante | Hallazgos QA | Chequeos |
|---|---:|---|
| idéntico | 2 | `fuga_eval_fragmento`, `fuga_eval_prompt_identico` |
| sin tildes | 1 | `fuga_eval_fragmento` |
| mayúsculas | 2 | fragmento + prompt idéntico |
| espacios | 1 | fragmento |
| puntuación | 2 | fragmento + prompt idéntico |
| reordenado (parcial) | 1 | fragmento |

La puerta QA aguanta tildes, mayúsculas, espacios y puntuación porque
`normalizar` y los n-gramas de 12 colapsan esas diferencias
(`qa_dataset.py:92-95,290-358`). La reordenación parcial se coge solo si queda
un 12-grama literal; una reordenación total de las oraciones da **0 hallazgos**
(comprobado con `" ".join(reversed(oraciones))`). Es una dependencia de la
secuencia literal, no de la equivalencia semántica.

Solapes de split: `split_prompt_identico=1` (la variante de puntuación
normaliza al mismo prompt) y `split_casi_identico=0`. La variante reordenada no
se detecta como prompt idéntico.

Exclusión en `merge_final.cargar_humanos_evaluacion`:

| Variante | ¿Excluida? |
|---|---|
| idéntico | sí |
| sin tildes | **no** |
| mayúsculas | sí |
| espacios | sí |
| puntuación | **no** |
| reordenado | **no** |

Causa: `merge_final._norm` (`merge_final.py:255-257`) solo hace NFC, colapsa
espacios y pasa a minúsculas; no quita tildes ni puntuación, y la exclusión es
por igualdad exacta, no por n-gramas. Arreglo: reutilizar
`qa_dataset.normalizar` (o una función equivalente que elimine diacríticos y
puntuación) y comparar también por n-gramas/clave de situación, no solo por
cadena exacta.

## Fase 4: traducción T116

20 casos (TR-01 a TR-20): 18 aciertos, 2 falsos negativos, 0 falsos positivos.

| Caso | Esperado | Resultado | Motivo |
|---|---|---|---|
| TR-18 | rechazar | aceptado | «Dos de Espadas invertida y Tres de Copas al derecho»: se conserva la primera inversión, no la segunda. |
| TR-19 | rechazar | aceptado | «não» no se detecta: `_TOKEN_RE` (`traducir_afirmaciones.py:116`) no incluye `ã`, `õ`, `ç`, así que el marcador `não` de `GLPT_MARKERS` (línea 93) nunca coincide. |

Hallazgos relacionados:

- `verificar_traduccion` (`traducir_afirmaciones.py:284-287`) comprueba
  `"invert" in texto.lower()` global, no por carta. Si el original tiene dos
  cartas invertidas y la traducción conserva una, pasa.
- TR-10 (carta añadida que no estaba en el original) se rechaza solo por el
  ratio de longitud 1,64 (`traducir_afirmaciones.py:241-243`), no porque se
  detecte la carta extra. Una traducción más corta con una carta añadida
  pasaría.
- TR-09 se rechaza por el marcador `uma`, no por `com/teu/coração`; los
  marcadores con diacríticos portugueses son inalcanzables por el tokenizador.

Arreglo propuesto:

1. Ampliar `_TOKEN_RE` a `[A-Za-zÁÉÍÓÚÜÑáéíóúüñãõçêôÃÕÇÊÔ0-9]+` y añadir a
   `GLPT_MARKERS` las formas `com`, `teu`, `tua`, `coração`, `coraçao`,
   `não`, `são`, `está`, `você`, `também`.
2. Verificar la orientación por carta: extraer del original los pares
   `(carta, reversed|upright)` y comprobar que cada carta traducida tiene la
   orientación correspondiente; no basta con que aparezca «invert» una vez.
3. Comparar el conjunto de cartas del original con el de la traducción
   (`IndiceCartas.requeridos`) y rechazar cartas añadidas, no solo las que
   faltan.
4. Mantener el ratio como comprobación secundaria, no como única defensa.

## Lista priorizada de arreglos

1. **Grave**: corregir `generate_tasks.py:977` y regenerar las 400 filas de
   `fuera_alcance`; sin esto el entrenamiento aprende a rechazar una pregunta
   corrupta.
2. **Grave**: añadir `_verif_sinastria` (aspectos cruzados con `lon`,
   posiciones A/B y casas); hoy no hay ninguna verificación de la familia.
3. **Grave**: reescribir `_verif_negativa_alcance` para que no responda la
   técnica prohibida, comprobar `tecnica` y cubrir `familia="etica"`.
4. **Grave**: ampliar `_verif_revolucion` a todos los planetas, MC, casas,
   fechas y año.
5. **Grave**: ampliar `_verif_biorritmos` con fases, crítico, días al pico,
   duraciones y fecha.
6. **Grave**: ampliar `_verif_transitos` con posiciones, fechas, casas y
   retrogradación, o rechazar lo no calculado.
7. **Grave**: normalizar tildes/puntuación en `merge_final._norm` y añadir
   detección por n-gramas/clave de situación; la reordenación total evade
   `fugas_eval`.
8. **Medio**: arreglar los dos falsos positivos de `fuera_alcance`
   (`queda fuera de lo que trabajo`, `numerol[oó]g`).
9. **Medio**: orientación por carta y cartas extra en T116; tokenizador con
   diacríticos portugueses.
10. **Leve**: unificar el tipo de `payload`/`calculos` en las filas reales
    (dict vs cadena JSON, lista en fuera_alcance) y documentar el contrato.

## Reproducción

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t123-auditoria-ronda7
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  finetune/corpus/auditoria_ronda7.py --json /tmp/ronda7.json
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  -m unittest finetune.corpus.tests.test_auditoria_ronda7 -v
./finetune/scripts/check.sh
```

`check.sh` debe terminar en `CHECK OK`; las 12 pruebas de defectos están en
`expectedFailure` y las 3 de control pasan.
