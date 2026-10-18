# Diseño A4 — Lecturas trabajadas y conocimiento desde YouTube (subtítulos)

Fecha: 2026-10-18 · Parte del `PLAN_ADQUISICION_CALIDAD.md` (nivel D). Estado: **diseño; sin implementar**. Alcance: tarot, baraja española, astrología occidental y numerología.

## 1. Para qué sirve y para qué no

El gran hueco del corpus son las **lecturas trabajadas**: alguien con cartas concretas, una posición, una pregunta y una interpretación fluida. En YouTube hay miles, en español natural, con tono de consulta real. Dos usos distintos:

| Uso | Qué vídeos | Qué se extrae | Destino |
|---|---|---|---|
| **Lectura** | Lecturas individuales o de ejemplo con cartas/posiciones/carta natal reales | Estructura de la lectura: cartas, posiciones, pregunta, interpretación por carta, síntesis, consejo | Ejemplos de **estilo y estructura** para el SFT |
| **Conocimiento** | Cursos y explicaciones («significado de El Loco», «Marte en casa 7») | Afirmaciones por entidad y faceta, con cita al vídeo | Matriz de cobertura y consenso de la KB (nivel D, nunca verdad única) |

**No** son fuente de verdad de significados: los significados se deciden por consenso entre fuentes. Son modelo de *cómo se lee*.

## 2. Medición real (2026-10-18, prueba pequeña)

| Medida | Resultado |
|---|---|
| Descubrimiento | 20 búsquedas × 25 resultados → **429 vídeos únicos en 60 s**, sin bloqueo |
| Canales distintos | 225; **41** con ≥ 3 vídeos relevantes (candidatos a rastrear completos) |
| Duración | 318 de 429 entre 5 y 40 min; mediana 16 min; 73 de más de 40 min |
| Vistas | mediana 9.474; 106 con más de 50.000 |
| Subtítulos en español (muestra de 40) | **95 %**: 34 automáticos originales (`es-orig`), 4 manuales, 1 traducido, 1 sin subtítulos |
| Ritmo de extracción completa | ≈ 2,5 s por vídeo (con pausa de 1 s) |
| Tipo de título (heurística) | tarot-lectura: 91 posibles lecturas de 125 · baraja: 31 de 47 · astrología: 88 de 122 · numerología: 61 de 70 |
| Calidad del subtítulo automático | Legible y con nombres de carta casi siempre correctos («los enamorados invertidos», «la reina de copas invertida»); sin puntuación ni mayúsculas, con muletillas y `[Música]` |

Conclusión: el material es abundante y accesible. El trabajo está en **seleccionar, limpiar y estructurar**, no en conseguirlo.

## 3. Tubería (etapas con entrada y salida)

Datos en `finetune/knowledge/youtube/` (ignorado en git salvo los catálogos ligeros).

### S1 · Descubrimiento
`yt_discover.py`: búsquedas (`ytsearchN:`) por familia con ≥ 60 consultas variadas (lectura de amor/trabajo/dinero/salud, Cruz Celta, 3 cartas, herradura, sí/no, baraja española, carta natal en vivo, tránsitos, revolución solar, sinastría, camino de vida…) y **expansión por canal**: de cada canal con ≥ 3 aciertos se listan todos sus vídeos (`channel/videos`).
Salida `catalogo.jsonl`: `id, canal, canal_id, titulo, duracion, vistas, fecha, familia, consulta`. Reanudable y deduplicado por `id`. Pausa 1,5 s entre peticiones; sin cookies.

### S2 · Selección de canales y vídeos
Reglas deterministas (sin LLM): duración 4–60 min; idioma español (por título/canal y después por subtítulo); excluir `shorts`, directos y listas musicales; puntuar canales por nº de vídeos relevantes, vistas y regularidad. **Tope por canal**: ningún canal supera el 3 % del corpus final (evita un único estilo y una única «voz»). El usuario puede revisar `canales.md` (top 100) y vetar o destacar canales.

### S3 · Descarga de subtítulos
`yt_fetch.py`: `skip_download`, `writesubtitles` + `writeautomaticsub`, idiomas `es` (manual) y **`es-orig`** (automático original; **no** usar el `es` automático traducido). Guarda `.vtt` en `raw_vtt/<canal_id>/<id>.vtt` y la tasa de éxito en `fetch.jsonl`. Reintentos con espera exponencial; si YouTube limita, para y reanuda al día siguiente (no se rodean los límites).

### S4 · Limpieza determinista
`yt_clean.py`: de VTT a texto continuo conservando **marcas de tiempo por frase** (para segmentar después). Quita líneas repetidas de los subtítulos «rodantes», `[Música]`, `[Aplausos]`, onomatopeyas, URLs, saludos fijos repetidos. Calcula métricas: palabras, palabras por minuto, proporción de nombres de carta conocidos por 1.000 palabras (detecta vídeos con cartas) y de términos astrológicos/numerológicos.

### S5 · Clasificación (LLM local, barata)
`yt_classify.py`: una llamada por vídeo con título, descripción corta y ~2.500 caracteres repartidos (inicio, mitad, final). Salida JSON validada:
`tipo` ∈ {`lectura_individual`, `lectura_ejemplo`, `lectura_general_elige_carta`, `curso_conocimiento`, `mixto`, `otro`}, `familia`, `tirada` (1 carta, 3 cartas, Cruz Celta, herradura, carta natal, etc.), `n_cartas` estimado, `calidad` 1–5 (claridad, profundidad, sin relleno comercial), `motivo`. Se descartan `otro` y calidad < 3. Los `lectura_general_elige_carta` («elige una carta, todos los signos») se conservan solo si calidad ≥ 4 y se marcan: son interpretaciones genéricas, menos útiles para personalizar.

### S6 · Extracción estructurada (LLM local) + validación determinista
`yt_extract.py` sobre el texto limpio (ventanas con solape de ~6.000 caracteres). Para `lectura_*` extrae:

```json
{"tirada":"cruz_celta","pregunta_o_tema":"…","cartas":[{"nombre":"Los Enamorados","orientacion":"invertida","posicion":"lo que bloquea"}],
 "interpretaciones":[{"carta":"Los Enamorados","texto":"…"}],"sintesis":"…","consejo":"…"}
```
Para `curso_conocimiento` extrae afirmaciones `{entidad, faceta, texto, minuto}`.
**Validaciones deterministas (sin LLM)** — una lectura no pasa si falla alguna:
1. Cada `nombre` de carta se normaliza contra el catálogo de las 78 (tildes, artículos, sinónimos: «la papisa»=«La Sacerdotisa», «la fuerza/la fortaleza»…) y debe existir.
2. Nº de cartas coherente con la tirada.
3. Posiciones válidas para esa tirada.
4. La interpretación de cada carta aparece en el texto original (coincidencia aproximada de palabras clave de la carta y de su posición) → evita que el LLM invente.
5. Para carta natal: planetas, signos y casas deben aparecer en el original.

### S7 · Normalización para SFT (LLM local, con fidelidad forzada)
`yt_normalize.py` convierte cada lectura validada en un par de entrenamiento: **prompt estructurado** (tirada, cartas con orientación y posición, pregunta, contexto) + **respuesta** reescrita en español neutro de calidad: segunda persona, sin nombres propios, sin saludos ni publicidad del canal, con la estructura apertura → interpretación por posición → síntesis → consejo. Reglas de fidelidad en el prompt y comprobadas después: **no añadir afirmaciones que no estén en el vídeo**, mantener todas las cartas y posiciones, longitud entre 0,3× y 1,2× del original útil. Además se guarda la versión *restaurada* (con puntuación) del texto original para uso opcional de estilo natural.

### S8 · Control de calidad
`yt_qa.py`: juez LLM independiente (otro modelo/otra pasada) puntúa fidelidad, coherencia, empatía, ausencia de promesas absolutas y de diagnósticos; filtros de seguridad (salud, muerte, embarazo, dinero y legal «garantizados» → se descartan o se reescriben con límites). Informe `qa.md` con 30 muestras aleatorias para tu revisión (3 %). Métricas: rendimiento por etapa, reparto por canal/familia/tirada, cobertura de cartas (cuántas lecturas tocan cada una de las 78) para detectar huecos.

## 4. Volumen y tiempo estimados

| Etapa | Volumen | Tiempo |
|---|---|---|
| S1 catálogo | 4.000–8.000 vídeos | 1–2 h |
| S3 subtítulos | ≈ 3.000–6.000 con subtítulo útil | 3–5 h (en segundo plano) |
| S5 clasificación | 1 llamada corta por vídeo | 2–3 h con los dos nodos |
| S6–S7 | 1.500–2.500 vídeos seleccionados; ≈ 1.000 tokens de salida por vídeo | 6–12 h |
| Rendimiento esperado | **1.000–2.000 lecturas validadas**, ≥ 1.500 puntuadas ≥ 4/5 es el objetivo | — |

El cuello de botella es el LLM local; por eso S5 filtra antes de las etapas caras y S7 genera solo la lectura normalizada, no la transcripción entera. Con Ornith (≈ 119 tokens/s con 4 slots por nodo) el tiempo baja casi a la mitad.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Un canal domina el estilo | tope del 3 % por canal; ≥ 40 canales distintos |
| Errores del subtítulo automático en nombres de carta | normalización contra el catálogo + validación 1–5 |
| El LLM «mejora» la lectura y la inventa | fidelidad exigida y comprobada (V4); juez independiente |
| Lecturas con afirmaciones peligrosas | filtro de seguridad en S8 y en el juez |
| Vídeos de venta («llama al 806…») | reglas de ruido + `calidad` ≥ 3 |
| Bloqueo o límites de YouTube | ritmo bajo, sin cookies, parada y reanudación; sin rodear límites |
| Duplicados (re-subidas) | hash de texto + MinHash entre vídeos |
| Privacidad de consultantes | anonimizar nombres y datos personales en S7 |
| Licencia y términos de YouTube | aplazado por decisión del usuario; se conserva `video_id`, canal y fecha de cada ejemplo para filtrar o retirar después |

## 6. Reparto en tareas para una IA local (pista A4; no lanzada)

Ficheros propios: `corpus/yt_discover.py`, `yt_fetch.py`, `yt_clean.py`, `yt_classify.py`, `yt_extract.py`, `yt_normalize.py`, `yt_qa.py`, `corpus/prompts/yt_*.md`, tests `corpus/tests/test_yt_*.py` (todo offline, con VTT y respuestas de LLM simuladas). Tareas en orden: **A4.1** descubrimiento y catálogo · **A4.2** descarga y limpieza VTT · **A4.3** catálogo de cartas y normalizador de nombres (compartido con A5/A6; módulo `cartas.py`) · **A4.4** clasificador (prompt + validación de JSON) · **A4.5** extractor y validaciones deterministas · **A4.6** normalizador SFT y fidelidad · **A4.7** QA e informe. Estimado: ≈ 4 h de IA local (×2,4 por compartir nodo ≈ 10 h reales). Dependencias: ninguna con T1–T8 salvo `translate_dataset.detect_language` (ya corregido en T2).

## 7. Criterios de aceptación

- Catálogo ≥ 4.000 vídeos de ≥ 150 canales; ≥ 40 canales con ≥ 3 vídeos seleccionados.
- ≥ 1.500 lecturas validadas con puntuación ≥ 4/5; ninguna carta de las 78 con menos de 10 lecturas (si falta, búsqueda dirigida).
- 0 lecturas con cartas inexistentes o incoherentes con la tirada (validación determinista al 100 %).
- Revisión humana del 3 % aprobada por el usuario.
