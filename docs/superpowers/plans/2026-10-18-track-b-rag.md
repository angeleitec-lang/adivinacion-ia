# Track B — RAG (recuperación + interpretación) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recopilar un corpus de tarot/astrología/numerología con Firecrawl,
indexarlo con embeddings (Ollama `nomic-embed-text`) en pgvector, y montar el
pipeline de recuperación + generación de interpretaciones basado en el cálculo
determinista del Plan 1.

**Architecture:** Tres capas: (1) recolección offline a markdown, (2) indexado
chunk + embed + insert en pgvector, (3) retrieval + prompt + generación vía un
endpoint OpenAI-compatible configurable (halogen `:8000` u Ollama). Separado
por ficheros con responsabilidad única.

**Tech Stack:** Python 3.11, `firecrawl-py`, Ollama HTTP API, `pgvector`,
`psycopg` (o `asyncpg`), httpx.

**Spec:** `docs/diseno-app-adivinacion.md` (secciones 5, 7, 8, 9).

## Global Constraints

- Idioma del producto: español (los documentos del corpus y los prompts en
  español).
- El RAG solo interpreta datos ya calculados por el Plan 1; nunca calcula
  fechas/posiciones por sí mismo.
- Endpoint de generación configurable por env var `LLM_BASE_URL` (default
  `http://10.0.0.3:8000/v1`) y `LLM_MODEL`; embeddings por `OLLAMA_URL`
  (default `http://10.0.0.1:11434`) y modelo `nomic-embed-text`.
- Licencia del corpus: auditar cada fuente antes de indexarla; no incluir
  contenido con licencia que prohíba uso comercial.
- Firecrawl respeta `robots.txt` por defecto; no desactivar salvo fuentes
  propias.

## Review Focus

1. Un chunk más corto que el mínimo (p. ej. título suelto) no debe romper el
   embedding — Task 2.
2. `retrieve` con índice vacío debe devolver `[]`, no excepción — Task 3.
3. El prompt debe incluir siempre los datos calculados (signo, casas, números)
   y nunca dejar el hueco vacío si falta una disciplina — Task 3.
4. Fallo del endpoint LLM (timeout/500) debe propagarse como error claro, no
   devolver texto vacío ni inventar — Task 4.
5. Textos con acentos/ñ deben conservarse intactos en chunking y prompt (UTF-8)
   — Task 2.

---

### Task 1: Recolección de corpus con Firecrawl

**Files:**
- Create: `backend/scripts/collect_corpus.py`
- Create: `backend/data_sources.yaml`
- Create: `backend/tests/test_collect_corpus.py`

**Interfaces:**
- Consumes: (nada)
- Produces:
  - `collect_corpus.py --disciplina tarot|astrologia|numerologia
    [--limit N] [--out data/corpus/<disciplina>]` — CLI.
  - `load_sources(path: str) -> list[dict]` con claves `disciplina`, `url`,
    `license`.
  - `save_markdown(texto: str, path: Path) -> None`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from pathlib import Path
from scripts.collect_corpus import load_sources, save_markdown

def test_load_sources_lee_disciplinas(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(
        "tarot:\n  - url: https://example.com/tarot\n    license: libre\n"
    )
    s = load_sources(str(p))
    assert s[0]["disciplina"] == "tarot"

def test_save_markdown_conserva_utf8(tmp_path):
    dest = tmp_path / "x.md"
    save_markdown("árbol de la vida — ñ", dest)
    assert dest.read_text(encoding="utf-8") == "árbol de la vida — ñ\n"
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_collect_corpus.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `backend/scripts/collect_corpus.py`**

Enfoque: `load_sources` parsea el YAML (estructura `disciplina: list[{url,
license}]`). `save_markdown` escribe UTF-8 con salto final. El CLI usa
`Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])` y `app.crawl(url,
limit)` (o `app.scrape` para páginas sueltas); guarda cada página en
`data/corpus/<disciplina>/<slug>.md` y un `manifest.json` con URL y licencia.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_collect_corpus.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/collect_corpus.py backend/data_sources.yaml backend/tests/test_collect_corpus.py
git commit -m "feat: recolección de corpus con Firecrawl a markdown"
```

---

### Task 2: Chunking + embeddings + indexado en pgvector

**Files:**
- Create: `backend/app/rag/index.py`
- Create: `backend/tests/test_rag_index.py`

**Interfaces:**
- Consumes: (nada)
- Produces:
  - `chunk_text(texto: str, max_chars: int = 800,
    solape: int = 80) -> list[str]` — chunks que respetan UTF-8 y no cortan
    palabras.
  - `embed(textos: list[str]) -> list[list[float]]` — POST a Ollama
    `/api/embeddings` con `nomic-embed-text`.
  - `insert_chunks(conn, disciplina: str, chunks: list[str],
    vectors: list[list[float]]) -> int` — inserta en tabla `chunks` con columna
    `embedding vector(768)`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from app.rag.index import chunk_text

def test_chunk_text_no_rompe_utf8():
    out = chunk_text("ñandú ñandú " * 100, max_chars=50)
    assert all("ñ" in c or c == "" for c in out)

def test_chunk_text_corto_no_se_divide():
    assert chunk_text("hola", max_chars=800) == ["hola"]

def test_chunk_text_maximo_respetado():
    for c in chunk_text("a" * 2000, max_chars=500):
        assert len(c) <= 500
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_rag_index.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `backend/app/rag/index.py`**

Enfoque: `chunk_text` parte por tamaño respetando espacios/UTF-8, con `solape`
de caracteres entre chunks. `embed` y `insert_chunks` usan httpx y el driver
pgvector respectivamente (mockeables en tests por inyección de dependencias).

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_rag_index.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/index.py backend/tests/test_rag_index.py
git commit -m "feat: chunking UTF-8, embeddings Ollama e indexado pgvector"
```

---

### Task 3: Retrieval + plantilla de prompt

**Files:**
- Create: `backend/app/rag/retrieve.py`
- Create: `backend/app/rag/prompts.py`
- Create: `backend/tests/test_retrieve.py`
- Create: `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `embed()` de Task 2; cálculo del Plan 1 (objetos `CartaAstral`,
  `dict` de numerología, tirada de tarot).
- Produces:
  - `retrieve(conn, consulta: str, top_k: int = 5) -> list[dict]` — con claves
    `texto`, `disciplina`, `score`. Índice vacío ⇒ `[]`.
  - `build_interpretation_prompt(calculo: dict, pregunta: str,
    contexto: list[dict]) -> str`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from app.rag.retrieve import retrieve

def test_retrieve_indice_vacio_devuelve_lista(conn):
    assert retrieve(conn, "amor", top_k=3) == []
```

```python
from app.rag.prompts import build_interpretation_prompt

def test_prompt_incluye_datos_calculados():
    calc = {"astro": {"sol": "Capricornio"}, "numerologia": {"camino_de_vida": 3}}
    p = build_interpretation_prompt(calc, "¿qué me depara?", [])
    assert "Capricornio" in p and "3" in p and "¿qué me depara?" in p

def test_prompt_sin_disciplina_no_deja_hueco_vacio():
    p = build_interpretation_prompt({"astro": {"sol": "Cancer"}}, "pregunta", [])
    assert "None" not in p
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_retrieve.py backend/tests/test_prompts.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `retrieve.py` y `prompts.py`**

Enfoque: `retrieve` calcula el embedding de la consulta y hace un `ORDER BY
embedding <=> %s LIMIT %s`. `build_interpretation_prompt` monta una plantilla
en español con: rol del vidente, datos calculados presentes, contexto
recuperado, y la pregunta del usuario; omite disciplinas ausentes en vez de
escribir `None`.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_retrieve.py backend/tests/test_prompts.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/retrieve.py backend/app/rag/prompts.py backend/tests/test_retrieve.py backend/tests/test_prompts.py
git commit -m "feat: recuperación por similitud y plantilla de interpretación"
```

---

### Task 4: Generación end-to-end (orquestador de lectura)

**Files:**
- Create: `backend/app/rag/generate.py`
- Create: `backend/tests/test_generate.py`

**Interfaces:**
- Consumes: `build_interpretation_prompt()` de Task 3.
- Produces:
  - `generar(prompt: str) -> str` — POST a `{LLM_BASE_URL}/chat/completions`
    con `{LLM_MODEL}`; devuelve el contenido de la respuesta. Error HTTP ⇒
    excepción con mensaje claro.
  - `interpretar(calculo: dict, pregunta: str, contexto: list[dict]) -> str`
    que encadena prompt + generar.

- [ ] **Step 1: Escribir los tests que fallan**

```python
import pytest
from app.rag.generate import generar

def test_generar_error_http_propaga(respx_mock):
    respx_mock.post("http://10.0.0.3:8000/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    with pytest.raises(RuntimeError):
        generar("hola")

def test_generar_devuelve_texto(respx_mock):
    respx_mock.post("http://10.0.0.3:8000/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "respuesta"}}]
        })
    )
    assert generar("hola") == "respuesta"
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_generate.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `backend/app/rag/generate.py`**

Enfoque: leer `LLM_BASE_URL`/`LLM_MODEL` de entorno (defaults en Global
Constraints). Construir el body de `chat/completions` (rol system con las
instrucciones del vidente, user con el prompt). `interpretar` compone
`build_interpretation_prompt` + `generar`.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_generate.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/generate.py backend/tests/test_generate.py
git commit -m "feat: generación de interpretaciones vía endpoint OpenAI-compatible"
```
