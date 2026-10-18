# Track A — Fine-tune con Soup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entrenar `Qwen3-8B-Instruct` con `soup-cli[train]` para que adopte el
tono y la forma de razonar de un vidente experto en español, partiendo del
corpus recopilado en el Track B, y exportarlo a GGUF para servir por Ollama.

**Architecture:** Dataset en formato ShareGPT/ChatML (JSONL) generado por un
script determinista a partir del corpus + plantillas; config de Soup en YAML;
entrenamiento QLoRA en nodo1; evaluación, merge y export a GGUF.

**Tech Stack:** Python 3.11, `soup-cli[train]`, PyTorch ROCm, modelo base
`Qwen/Qwen3-8B-Instruct`.

**Spec:** `docs/diseno-app-adivinacion.md` (secciones 5, 6, 9).

## Global Constraints

- Modelo base: `Qwen/Qwen3-8B-Instruct` (Apache-2.0). Alternativa de calidad:
  `Qwen/Qwen3-14B-Instruct` si el tiempo de iteración lo permite.
- Hardware: Strix Halo (ROCm), 128 GB unificados. QLoRA (4-bit) por defecto;
  con 128 GB se puede subir a LoRA bf16 sin quantizar.
- Python 3.11 (Soup NO soporta 3.13). Ejecutar en nodo1 (10.0.0.3) vía
  `ssh bosgame`.
- Dataset íntegramente en español, formato ShareGPT (`conversations` con
  `from`/`value` = system/user/assistant).
- No incluir en el dataset contenido con licencia no comercial.
- El fine-tune NO calcula nada: recibe los datos calculados (carta, números,
  tirada) ya resueltos en el prompt, y aprende a interpretarlos.

## Review Focus

1. Dataset con una sola muestra o mal formado debe fallar en `soup data
   inspect`, no en mitad del entrenamiento — Task 1.
2. Reparto train/val sin fugas: la misma conversación no puede estar en ambos
   splits — Task 1.
3. Prompt del usuario ausente o vacío en una muestra debe rechazarse al
   construir el dataset — Task 1.
4. LoRA con `r`/`alpha` mal proporcionados (alpha < r) debe detectarse en la
   validación de config antes de lanzar GPU — Task 2.
5. Tras el merge, el modelo debe responder en español a una tirada de prueba
   con los datos calculados presentes en el prompt — Task 3.

---

### Task 1: Preparación del dataset de fine-tune

**Files:**
- Create: `backend/scripts/build_dataset.py`
- Create: `backend/finetune/plantillas.py`
- Create: `backend/tests/test_build_dataset.py`

**Interfaces:**
- Consumes: corpus de `data/corpus/<disciplina>/*.md` (Track B, Task 1).
- Produces:
  - `construir_muestra(disciplina: str, contexto: str, calculo: dict) -> dict`
    — devuelve una conversación ShareGPT `{"conversations": [...]}` con
    system/user/assistant, o `None` si falta el prompt del usuario.
  - `build_dataset(corpus_dir: Path, salida: Path, semilla: int = 0) ->
    tuple[int, int]` — escribe `train.jsonl` y `val.jsonl` sin solapamiento;
    devuelve (n_train, n_val).

- [ ] **Step 1: Escribir los tests que fallan**

```python
from pathlib import Path
from scripts.build_dataset import construir_muestra, build_dataset

def test_construir_muestra_rechaza_prompt_vacio():
    assert construir_muestra("tarot", "contexto", {"pregunta": ""}) is None

def test_construir_muestra_formato_sharegpt():
    m = construir_muestra("tarot", "significado", {"pregunta": "¿amor?"})
    assert set(m) == {"conversations"}
    roles = [t["from"] for t in m["conversations"]]
    assert roles == ["system", "user", "assistant"]

def test_build_dataset_split_sin_solape(tmp_path):
    (tmp_path / "tarot").mkdir(parents=True)
    for i in range(6):
        (tmp_path / "tarot" / f"{i}.md").write_text(f"contexto {i}", encoding="utf-8")
    n_train, n_val = build_dataset(tmp_path, tmp_path / "out", semilla=0)
    train = [l for l in (tmp_path / "out" / "train.jsonl").read_text().splitlines()]
    val = [l for l in (tmp_path / "out" / "val.jsonl").read_text().splitlines()]
    assert n_train + n_val == 6 and len(train) == n_train and len(val) == n_val
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_build_dataset.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `build_dataset.py` y `plantillas.py`**

Enfoque: `plantillas.py` define las plantillas system (rol del vidente) y
user (contexto + datos calculados + pregunta) por disciplina. `construir_muestra`
rellena la plantilla y rechaza prompts vacíos. `build_dataset` lee el corpus,
divide con `random.Random(semilla)` (80/20) garantizando que una misma fuente
no quede en ambos splits.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_build_dataset.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/build_dataset.py backend/finetune/plantillas.py backend/tests/test_build_dataset.py
git commit -m "feat: construcción de dataset ShareGPT para fine-tune"
```

---

### Task 2: Config de Soup y lanzamiento del entrenamiento

**Files:**
- Create: `backend/finetune/soup.yaml`
- Create: `backend/scripts/run_finetune.sh`
- Create: `backend/tests/test_soup_config.py`

**Interfaces:**
- Consumes: dataset `train.jsonl`/`val.jsonl` de Task 1.
- Produces:
  - `validar_config(yaml_path: Path) -> bool` — comprueba `base`,
    `task == sft`, `data.train`, `lora.r <= lora.alpha`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from pathlib import Path
from scripts.validate_soup import validar_config

def test_validar_config_ok(tmp_path):
    p = tmp_path / "soup.yaml"
    p.write_text(
        "base: Qwen/Qwen3-8B-Instruct\n"
        "task: sft\n"
        "data:\n  train: train.jsonl\n"
        "lora:\n  r: 16\n  alpha: 32\n"
    )
    assert validar_config(p) is True

def test_validar_config_alpha_menor_que_r(tmp_path):
    p = tmp_path / "soup.yaml"
    p.write_text("base: Qwen/Qwen3-8B-Instruct\ntask: sft\nlora:\n  r: 32\n  alpha: 8\n")
    assert validar_config(p) is False
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_soup_config.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `validar_config` en `backend/scripts/validate_soup.py`**

Enfoque: parsear el YAML con `yaml.safe_load` y comprobar los campos mínimos.
`soup.yaml` usa `base: Qwen/Qwen3-8B-Instruct`, `task: sft`, `lora.r=16,
alpha=32, dropout=0.05`, `quantization: 4bit`, `epochs: 3`, `lr: 2e-5`,
`data.train: ../data/datasets/train.jsonl`. `run_finetune.sh` instala
`soup-cli[train]` en un venv ROCm y lanza `soup train --config soup.yaml`.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_soup_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/finetune/soup.yaml backend/scripts/run_finetune.sh backend/scripts/validate_soup.py backend/tests/test_soup_config.py
git commit -m "feat: config Soup y script de lanzamiento del fine-tune"
```

---

### Task 3: Evaluación, merge y export a GGUF

**Files:**
- Create: `backend/scripts/eval_finetune.sh`
- Create: `backend/finetune/eval_casos.jsonl`
- Create: `backend/tests/test_eval_casos.py`

**Interfaces:**
- Consumes: adaptador entrenado de Task 2.
- Produces:
  - `eval_casos.jsonl` — casos de prueba con `{"pregunta", "calculo",
    "esperado_espanol": true}`.
  - `cargar_casos(path: Path) -> list[dict]`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from pathlib import Path
from scripts.eval_casos import cargar_casos

def test_cargar_casos(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text('{"pregunta": "¿amor?", "calculo": {"sol": "Leo"}}\n')
    casos = cargar_casos(p)
    assert casos[0]["calculo"]["sol"] == "Leo"
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_eval_casos.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `cargar_casos` y `eval_finetune.sh`**

Enfoque: `cargar_casos` lee JSONL. `eval_finetune.sh` ejecuta `soup eval` con
los casos, luego `soup merge` (LoRA→base) y `soup export --format gguf
--quant q4_k_m`, y copia el GGUF al mini con rsync para servirlo con Ollama.
Verificar manualmente que una tirada de prueba responde en español con los
datos calculados presentes.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_eval_casos.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/eval_finetune.sh backend/finetune/eval_casos.jsonl backend/scripts/eval_casos.py backend/tests/test_eval_casos.py
git commit -m "feat: evaluación, merge y export GGUF del fine-tune"
```
