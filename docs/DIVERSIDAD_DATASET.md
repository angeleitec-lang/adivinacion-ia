# Diversidad del dataset (T106)

Análisis de diversidad y balance del dataset de lecturas aceptadas.
Herramienta: `finetune/corpus/diversidad_dataset.py` (solo lectura, stdlib, determinista).
Informe completo con todos los datos: `/Users/angelgonzalez/fase0/diversidad_dataset/informe_diversidad.{json,md}` (generado con `--top 20`).

## Fuente

- Copia congelada: `/Users/angelgonzalez/fase0/diversidad_dataset/aceptadas_snapshot.jsonl`
  (sha256 `9c3b25404cb277c194acdee3408bbc7d5a790d9124ee937dc8fe7826bbe69381`).
- **6596 lecturas** (la snapshot congeló la generación en curso; el enunciado citaba ~6500).
- Tareas pendientes/jobs: `finetune/corpus/jobs.db` (solo lectura, 12902 jobs, 15 bloques).
- Tokens estimados: 1,35 tokens/palabra (sin tokenizer del modelo base todavía).

## Medidas globales

| Métrica | Valor |
|---|---|
| Nº lecturas | 6596 |
| Longitud respuesta (chars) | media 4296, p5 1718, p95 9848, min 988, max 12804 |
| Longitud respuesta (tokens est.) | media 972, p5 397, p95 2199 |
| Proporción multiturno | **0,00 %** |
| TTR global (types/tokens) | 0,0049 (23.073 tipos / 4,75 M tokens) |
| 4-gramas únicos / totales | 54,0 % (2,55 M / 4,73 M) |
| 6-gramas únicos / totales | 81,3 % (3,83 M / 4,72 M) |
| Top-20 aperturas (8 palabras) | 1062 lecturas (16,1 %) |
| Top-20 cierres (8 palabras) | 899 lecturas (13,6 %) |
| Casi-duplicados (Jaccard ≥ 0,75, shingles 5 + MinHash/LSH) | **0 pares**, dentro y entre bloques |

## Por bloque

| Bloque | n | chars media (p5–p95) | TTR | 4-g únicos | 6-g únicos | muletillas 4-g | muletillas 6-g |
|---|---|---|---|---|---|---|---|
| astro_natal | 1434 | 8343 (5326–11438) | 0,0073 | 52,7 % | 80,0 % | 1140 | 278 |
| tarot_3 | 1399 | 3910 (2926–5046) | 0,0144 | 64,2 % | 85,2 % | 370 | 110 |
| tarot_1 | 939 | 2376 (1562–3369) | 0,0269 | 72,3 % | 89,7 % | 204 | 49 |
| tarot_pregunta | 800 | 2062 (1353–3032) | 0,0326 | 74,9 % | 91,2 % | 136 | 31 |
| lectura_completa | 726 | 2745 (2330–3245) | 0,0239 | 65,7 % | 85,1 % | 333 | 106 |
| cruz_celta | 500 | 3899 (3065–5658) | 0,0292 | 75,6 % | 91,0 % | 411 | 72 |
| tarot_2 | 399 | 3188 (2287–4377) | 0,0371 | 76,8 % | 92,1 % | 289 | 76 |
| numerologia | 399 | 4538 (3177–6231) | 0,0212 | 62,6 % | 82,9 % | 791 | 232 |

Muletillas = 4/6-gramas de respuesta presentes en >5 % de las lecturas del bloque.
Ejemplos máximos: `tirada de tres cartas` (100 % de lectura_completa), `tu camino de vida` (99 %),
`tendencias y posibilidades no` (60 % de astro_natal), `al derecho esta carta` (50 % de tarot_3),
`esto es una tendencia no una` (34 % de tarot_1), `con un profesional de la salud` (25 % de tarot_3).

Aperturas más repetidas: «entiendo tu pregunta y te agradezco la confianza» (134, 2,0 % global),
«claro con gusto te acompano en esta lectura» (106), «querido consultante gracias por compartir tu…» (87+61).
Cierres: «con carino y respeto tu tarotista y astrologa» (124), «carino y respeto tu tarotista astrologa y numerologa» (100),
«…explorar sobre esta lectura estoy aqui para acompanarte» (98+66+49+39 en variantes).

## Balance

**Tarot (78 cartas):** presentes las 78 en prompts/respuestas. 13.912 ocurrencias; 5041 invertidas (**36,2 %**).
Más frecuentes: Reina de Oros 213, El Hierofante 207, Dos de Bastos 204, Caballero de Copas 200, La Estrella 196.
Menos: Ocho de Bastos 142, Sota de Bastos 152, El Carro 158, Siete de Oros 159, El Mundo 161. Rango ±20 % en torno a la media (178).

**Baraja española (40 naipes): 0 apariciones.** Ninguna lectura aceptada de espanola_1/3/5/7.

**Contextos** (bloques con contexto, 4763 lecturas): equilibrado — general 815, amor 800, salud 791, espiritual 789, trabajo 786, dinero 782.

**Preguntas:** solo **45 frases distintas** para 6596 lecturas; el **72,2 %** son las preguntas fijas de la plantilla de `generate_tasks.py` (24).
Tipos interrogativos: qué 4420 (67 %), si/no 992, cómo 784, cuál 217, por qué 181, otra 2.
**No aparece ningún** «cuándo», «dónde» ni «quién».

**Signos** (astro_natal/lectura_completa, 1434 cartas): sol entre 162 (Acuario) y 198 (Aries); ascendente entre 149 (Piscis) y 213 (Sagitario). Los 12 presentes.

**Caminos de vida** (numerologia + lectura_completa, 1125): los 12 valores presentes (1-9, 11, 22, 33).
Frecuencias: 3 137, 5 128, 8 125, 9 123, 6 122, 1 112, 7 104, 11 91, 4 82, 2 42, 22 42, 33 17.

**Ética/fuera de alcance:** bloque `etica` = **0 lecturas aceptadas** (304 jobs pendientes); ninguna clave temática ética detectada en el resto.

**Multiturno:** 0 lecturas (bloque multiturno: 800 jobs pendientes).

## Huecos (bloques en jobs.db sin ninguna aceptada)

`espanola_1` (400), `espanola_3` (900), `espanola_5` (400), `espanola_7` (200), `multiturno` (800), `sinastria` (600), `etica` (304) — **3904 jobs pendientes (30 % de la cola)**.

## Diez hallazgos

1. **La baraja española está ausente por completo**: 0/40 naipes, 2200 tareas sin generar/aceptar. El dataset actual no enseñaría español.
2. **Cero casi-duplicados**: con umbral Jaccard 0,75 (y ni un solo par ≥0,75 en 6596 lecturas, dentro y entre bloques), no hay redundancia literal; la variación léxica del generador es alta.
3. **Todo es monoturno** (0 % multiturno): el modelo no aprendería a gestionar seguimiento de conversación; bloque `multiturno` pendiente (800).
4. **Ni un solo caso ético/fuera de alcance aceptado** (304 pendientes): el modelo no tendría ejemplos de contención (salud grave, duelo, violencia, adicciones).
5. **Las preguntas están topadas por la plantilla**: 45 frases distintas para 6596 lecturas, 72 % preguntas fijas, sin «cuándo/dónde/quién». La variedad de respuestas no se corresponde con variedad de consultas.
6. **astro_natal es el bloque menos diverso**: TTR 0,0073, 4-gramas únicos 52,7 %, 1140 muletillas 4-g («tendencias y posibilidades no» en el 60 % de las lecturas) y el disclaimer «esto es una lectura de tendencias…» encadenado en ~25-28 %.
7. **Aperturas y cierres canónicos**: top-20 aperturas = 16 % de las lecturas y top-20 cierres = 14 %; fórmulas tipo «gracias por compartir», «estoy aqui para acompanarte» y firmas «con cariño y respeto tu tarotista…» se repiten como plantilla.
8. **lectura_completa es 100 % formulaica en sus anclas** («tirada de tres cartas», «tu camino de vida», «numerologia tu camino de» en ≥99 %): mezcla los tres sistemas pero recita siempre la misma estructura.
9. **Tarot bien cubierto y balanceado**: 78/78 cartas, rango ±20 %, 36 % invertidas; es la parte sana del dataset. Contextos, signos y caminos de vida también balanceados (33 escaso: 17).
10. **Desequilibrio de longitudes**: astro_natal (media 8343 chars, p95 11438) cuadriplica a tarot_pregunta (2062); en tokens medios 972 globales con p95 2199 — los bloques largos dominarán el coste de entrenamiento.

## Recomendaciones

- **Subgenerar antes del dataset final** (prioridad): 1) baraja española `espanola_*` (2200 jobs) — requisito funcional del producto; 2) `etica` (304); 3) `multiturno` (800); 4) `sinastria` (600). Son el 30 % de la cola y sin ellos el modelo no cubre tres de los cuatro sistemas prometidos.
- **Deduplicación: no hace falta umbral estricto ahora.** A 0,75/0,80/0,90/0,95 se perderían **0 lecturas**. Recomiendo dejar el umbral guardián en **0,90** (perdidas actuales 0) en el verificador para futuras tandas, y no introducir 0,75 (empezaría a cortar pares legítimos de corta distancia cuando crezca el corpus).
- **Ampliar la plantilla de preguntas de `generate_tasks.py`** (proposición, no cambio): pasar de 24 preguntas fijas a ≥80 variantes y añadir marcas «cuándo/dónde/quién» y preguntas sin interrogación directa; hoy el 72 % de las consultas es literalmente de plantilla y el modelo aprenderá a responder plantillas, no personas.
- **Plantillas que generan aperturas/cierres repetidos**: la frase de apertura del sistema/prompt de astro_natal y numerologia («querido consultante gracias por compartir…») y el cierre «…estoy aqui para acompanarte» / firma «con cariño y respeto tu tarotista…» provienen de ejemplos few-shot del prompt; variar o quitar los ejemplos de apertura/cierre y, si persiste, filtrar en el verificador lecturas cuya apertura iguale al top-3 acumulado (>2 %).
- **Reducir el lastre de astro_natal/lectura_completa**: el disclaimer «esto es una lectura de tendencias y posibilidades no…» repetido en cadena añade muletillas sin valor; conviene un solo formato de disclaimer (o moverlo al system) y reauditar TTR tras la regeneración.
- **Vigilar 33 (17 lecturas) y los naipes españoles en la siguiente snapshot**: repetir este análisis (`diversidad_dataset.py --jsonl <nueva> --jobs-db <db>`) tras cada tanda de generación; el informe md/json es comparable serie a serie.

## Uso de la herramienta

```bash
finetune/.venv/bin/python finetune/corpus/diversidad_dataset.py \
  --jsonl /Users/angelgonzalez/fase0/diversidad_dataset/aceptadas_snapshot.jsonl \
  --jobs-db finetune/corpus/jobs.db \
  --out informe_diversidad.json --md informe_diversidad.md --top 20
```

`--jobs-db ''` desactiva el cruce con la cola (huecos por payload). Tests: `corpus/tests/test_diversidad_dataset.py` (28).
