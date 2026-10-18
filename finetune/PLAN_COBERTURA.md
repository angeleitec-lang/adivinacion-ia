> **NOTA (2026-10-18, noche) — LEER ANTES:** este plan se redactó antes de la auditoría y **está superado en varios puntos**: (1) los 56 arcanos menores de la KB eran texto genérico y se están reescribiendo; (2) el dataset `final/` no es entrenable (el auditor deja 1.991 de 4.653 pares); (3) el generador tenía 3 bugs graves (zona horaria, tildes, año personal) ya corregidos en rama; (4) el alcance se acotó a tarot, baraja española, astrología occidental y numerología; (5) la generación sintética NO debe empezar hasta cerrar la fase 0 de adquisición. Estado vigente y pasos: `docs/ESTADO_Y_PENDIENTES.md` y `docs/PLAN_ADQUISICION_CALIDAD.md`.

# Plan de cobertura: de corpus scrapeado a modelo que lee de verdad

**Objetivo:** llegar a **15.000–25.000 pares SFT de alta calidad en español**, con cobertura combinatoria real, y entrenar `Qwen/Qwen2.5-14B-Instruct` con QLoRA.

**Principio rector:** el SFT enseña *cómo leer* (estructura, tono, razonamiento simbólico, combinación de técnicas); el RAG aporta *qué decir* (significados, correspondencias, reglas); los datos astronómicos y numerológicos **se calculan por código**, nunca los inventa el modelo.

---

## 1. Decisiones de infraestructura

| Pieza | Decisión | Motivo |
|---|---|---|
| Memoria de proyecto | **Letta se queda como está** (solo notas de proyecto) | Letta es memoria de agente, no un almacén de recuperación masiva. Meter 30k chunks ahí degrada su función y no aporta. |
| RAG de generación | **Índice vectorial propio** (`numpy` + embeddings de Ollama `nomic-embed-text`, 768d) | Sin dependencias de servidor; 30k chunks se resuelven por producto escalar en ~10 ms. |
| RAG de producto (web) | Postgres + pgvector, **tarea aparte** | El cluster PG 15 del mini tiene un rol desconocido y pgvector solo está compilado para 17/18. No bloquea la generación. |
| Generación | **nodo1 + nodo2 en paralelo** (27B `halogen-qwen3.8-flash-next`) | 128 GB cada uno; GPU libre en nodo1, nodo2 termina la traducción. |
| Cola de trabajo | SQLite (`corpus/jobs.db`) con reclamación atómica | Reanudable, idempotente, sin infra extra. |
| Embeddings | Ollama del mini (`http://10.0.0.1:11434`) | Ya operativo con `nomic-embed-text:latest`. |

---

## 2. Matriz de cobertura (objetivo ~18.100 pares)

| Bloque | Combinaciones / criterio | Pares |
|---|---|---:|
| Corpus real (libros + web, traducido) | lo que salga del pipeline actual | ~7.500 |
| Tarot · 1 carta × contexto × orientación | 78 cartas × 6 contextos (amor, trabajo, dinero, salud, espiritual, general) × 2 orientaciones, muestreado | 900 |
| Tarot · 2 cartas (relación / sí-no) | parejas con contexto | 400 |
| Tarot · 3 cartas (pasado/presente/futuro) | muestreo estratificado por palo y arcano | 1.400 |
| Tarot · Cruz Celta (10 posiciones) | tiradas completas | 500 |
| Tarot · arcano + pregunta libre | 1 carta, pregunta del consultante | 800 |
| Astrología natal | Sol/Luna/Asc en signo, planeta en casa, casas, aspectos | 1.500 |
| Sinastría | parejas de signos y aspectos entre cartas | 600 |
| Numerología | camino de vida, destino, alma, personalidad, año personal, compatibilidad | 400 |
| Lecturas completas multi-técnica | fecha + cartas + pregunta → síntesis tarot+astro+numerología | 3.000 |
| Multi-turno | aclaraciones y seguimiento sobre una lectura previa | 800 |
| Ética y límites | derivación médica/legal/financiera, edad, tono | 300 |
| **Total sintético** | | **10.600** |
| **Total esperado** | | **~18.100** |

Cada ítem se genera con: datos calculados (cartas concretas, posiciones, números) + contexto recuperado del RAG + plantilla de pregunta distinta.

---

## 3. Fases y entregables

### Fase 0 — Cerrar los datos actuales
- Esperar a la traducción (`PID 8075`) y al vigilante (`PID 9548`), que encadena build de Scrapy → traducción de EN largos → merge.
- Entregable: `corpus/train_final.jsonl` / `corpus/val_final.jsonl` con ~7.500 pares reales en español.

### Fase 1 — Base de conocimiento estructurada
Ficheros: `corpus/kb/tarot.json`, `corpus/kb/astrologia.json`, `corpus/kb/numerologia.json`.
Contenido mínimo:
- 78 cartas: significado general, amor, trabajo, dinero, invertida, palabras clave.
- 12 signos, 10 planetas, 12 casas, 5 aspectos, ejes.
- Números 1–9 + 11/22/33 y sus áreas.
Script: `corpus/build_kb.py` (extrae de `corpus/raw` y de los libros ya convertidos; lo que falte se completa a mano).
Validación: revisión manual de una muestra de 30 entradas por bloque.

### Fase 2 — Índice RAG
Script: `corpus/rag_index.py`.
- Chunks de 800–1.200 caracteres con solape de 150.
- Embeddings vía `POST http://10.0.0.1:11434/api/embeddings` (`nomic-embed-text`).
- Salida: `corpus/rag/chunks.jsonl` + `corpus/rag/embeddings.npy`.
- Búsqueda: top-k por coseno normalizado (numpy).

### Fase 3 — Generador sintético
Scripts: `corpus/generate_tasks.py` (crea la matriz de trabajos en `corpus/jobs.db`) y `corpus/generate_synthetic.py` (workers).
- Cada job guarda: bloque, parámetros, prompt, datos calculados, estado, intentos, respuesta.
- Dos lanzadores en paralelo:

```bash
# nodo1
.venv/bin/python corpus/generate_synthetic.py --shard 0/2 \
  --endpoint http://10.0.0.3:8000/v1 --model halogen-qwen3.8-flash-next --workers 5

# nodo2
.venv/bin/python corpus/generate_synthetic.py --shard 1/2 \
  --endpoint http://10.0.0.4:8000/v1 --model halogen-qwen3.8-flash-next --workers 5
```

- Salida: `corpus/synthetic/<bloque>.jsonl` (formato ShareGPT).
- Reanudable: los jobs `done` no se repiten.

### Fase 4 — Validación y deduplicación
Script: `corpus/validate_synthetic.py`.
Puertas:
1. Idioma español (heurística de stopwords).
2. Longitud 200–1.500 tokens.
3. Los datos del prompt aparecen y no se contradicen (cartas, grados, casas, números).
4. Sin boilerplate ni markdown roto.
5. Dedupe exacto (sha256) + near-dup (MinHash, Jaccard > 0,9).
6. Muestra del 10% con juez LLM (relevancia, coherencia, no invención); aceptar >85%.

### Fase 5 — Merge y split final
Script: `corpus/merge_final.py`.
- Real + sintético, dedupe cruzado, split **estratificado por bloque**: 80% train / 10% val / 10% test.
- `val_final.jsonl` y `test_final.jsonl` **no se tocan** durante el entrenamiento ni la generación.

### Fase 6 — Entrenamiento y evaluación
- `soup.yaml`: base `Qwen/Qwen2.5-14B-Instruct`, `task: sft`, LoRA `r=32, alpha=64`, `quantization: 4bit`, 3 épocas, lr `1e-4`, cosine, warmup 3%.
- Entrenar en nodo1 (ROCm + venv propio, separado de halogen).
- Evaluación:
  - loss de validación;
  - 100 prompts ciegos comparados contra el modelo base con juez LLM;
  - revisión humana de 30 lecturas completas.
- Export: `soup merge` + `soup export --format gguf --quant q4_k_m`; servir en Ollama/halogen.

---

## 4. Calendario estimado (máquina)

| Fase | Tiempo |
|---|---|
| 0 · cierre de datos | 1–3 h |
| 1 · KB estructurada | 4–6 h |
| 2 · índice RAG | 1–2 h |
| 3 · generación (10.600 ítems) | 10–18 h |
| 4 · validación | 2–4 h |
| 5 · merge/split | 1 h |
| 6 · entrenamiento 14B | 15–25 h |
| **Total** | **~2–3 días** |

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El generador repite fórmulas | 6+ plantillas por bloque, temperatura 0,8, muestreo estratificado, dedupe near-dup |
| Alucinación astronómica | Las posiciones las calcula `pyswisseph`; el prompt las fija y el validador las comprueba |
| Estilo uniforme del 27B | Mezclar corpus humano (libros/web) con sintético; juez LLM y revisión humana |
| Licencias | Solo dominio público / CC BY / CC BY-SA en el producto; el resto marcado `consultar` y fuera del dataset final |
| Deriva de idioma | Validador de español obligatorio; los pares mixtos se descartan |
| Coste de rehacer | Job queue persistente + splits congelados |

---

## 6. Primeras acciones concretas

1. `corpus/build_kb.py` → KB de tarot/astro/numerología.
2. `corpus/rag_index.py` → índice sobre `corpus/raw` + `corpus/raw_scrapy`.
3. `corpus/generate_tasks.py` → matriz de 10.600 jobs.
4. Lanzar generación en nodo1 y nodo2.
5. Validar, fusionar y entrenar.
