# Guía de reentrenamiento (Soup + Firecrawl)

Reentrena un modelo open-weights para que haga lecturas de tarot, carta
astral, numerología y (Fase 2) quiromancia, en español.

> Requisitos: Python 3.10–3.12 (NO 3.13). Clave de Firecrawl (cloud) o
> self-host. nodo1/nodo2 con entorno ROCm PyTorch propio (ver 0.2).

## 0. Requisitos previos

### 0.1 Entorno Python y dependencias

```bash
# En la máquina que entrene (nodo1), crea un venv con Python 3.11
python3.11 -m venv ~/adivinacion-ia/finetune/.venv
source ~/adivinacion-ia/finetune/.venv/bin/activate

pip install "soup-cli[train]" firecrawl-py
```

### 0.2 PyTorch ROCm (solo nodo1/nodo2, iGPU RDNA 3.5)

Soup por debajo usa transformers/unsloth; halogen NO sirve (no es PyTorch).
Instala torch con soporte ROCm según la doc oficial de PyTorch:

```bash
pip install torch --index-url https://download.pytorch.org/whl/rocm6.2
```

Comprueba la versión ROCm exacta del driver con `rocminfo`.

### 0.3 Clave de Firecrawl

```bash
export FIRECRAWL_API_KEY="fc-..."
```

Alternativa sin nube: self-host Firecrawl con Docker
(https://github.com/firecrawl/firecrawl → SELF_HOST.md, AGPL-3.0).

## 1. Extraer el corpus con Firecrawl

El documento que lee Firecrawl (objetivo, prompt y lista de fuentes) está en
`corpus/INSTRUCCIONES_FIRECRAWL.md`. Hay dos modos:

### 1.1 Modo agent (recolección autónoma)

```python
import os
from firecrawl import Firecrawl

app = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])

# prompt = sección "PROMPT" de corpus/INSTRUCCIONES_FIRECRAWL.md
resp = app.agent(prompt=open("corpus/INSTRUCCIONES_FIRECRAWL.md").read())
open("corpus/raw/agent_output.json", "w").write(str(resp))
```

### 1.2 Modo crawl por lista de URLs (determinista)

```python
import os
from firecrawl import Firecrawl

app = Firecrawl(api_key=os.environ["FIRECRAWL_API_KEY"])

urls = [l.strip() for l in open("corpus/urls.txt")
        if l.strip() and not l.startswith("#")]
for url in urls:
    try:
        res = app.crawl(url, limit=50, formats=["markdown"])
        for page in res.get("data", []):
            guardar_pagina(page["markdown"], page["metadata"]["url"])
    except Exception as e:
        print("fallo", url, e)
```

Guardado de cada página: `corpus/raw/<dominio>/<slug>.md` + registro en
`corpus/manifest.json` con URL y licencia estimada.

> Nota: Firecrawl respeta robots.txt; si un sitio bloquea el rastreo, se marca
> en el manifest como "bloqueado" y se descarta o se pide permiso.

## 2. Limpiar y formatear a ShareGPT

El dataset de SFT debe ser JSONL con formato ShareGPT:

```json
{"conversations": [
  {"from": "human", "value": "...pregunta/contexto..."},
  {"from": "gpt", "value": "...lectura/interpretación..."}
]}
```

Escribe un script `corpus/build_dataset.py` que:
1. Lea `corpus/raw/**/*.md`.
2. Extraiga bloques de texto → parejas (instrucción, respuesta) por plantilla.
3. Divida en train/val (90/10) SIN solape entre documentos.
4. Escriba `corpus/train.jsonl` y `corpus/val.jsonl`.

Plantilla de instrucción (ejemplo):

```
Eres una lectora de tarot experta y empática. Explica el significado del
arcano {carta} en una tirada de {tipo_tirada}. Responde en español.
```

> El Plan 3 del proyecto (`docs/superpowers/plans/2026-10-18-track-a-finetune.md`)
> detalla `build_dataset.py` y `plantillas.py` con TDD.

## 3. Configurar Soup

Inicializa el template de chat (genera un `soup.yaml` real):

```bash
soup init --template chat
```

Edita `soup.yaml` ajustando los campos clave:

```yaml
base: Qwen/Qwen2.5-14B-Instruct
task: sft
data:
  train: corpus/train.jsonl
  validation: corpus/val.jsonl
epochs: 3
learning_rate: 2e-5
lora:
  r: 16
  alpha: 32
quantization: 4bit          # QLoRA
backend: transformers       # o unsloth para +velocidad (2-5x)
```

(Para depurar el pipeline más rápido puedes usar temporalmente
`Qwen/Qwen2.5-7B-Instruct`; la versión final va con el 14B. Los
nombres exactos de las claves los fija el YAML generado por `soup init`.)

## 4. Entrenar (QLoRA)

```bash
soup train --config soup.yaml
```

- El adaptador LoRA se guarda en el directorio de salida configurado.
- En Strix Halo 128 GB: 7B sobra; 14B/24B/32B QLoRA caben.
- Cuello de botella = cómputo de la iGPU, no memoria.

Vigila la pérdida (loss): no pases de 3-5 epochs o sobreajusta.

## 5. Evaluar

```bash
soup eval --config soup.yaml
# o charla de prueba:
soup chat --config soup.yaml
```

Pruebas manuales clave: pídele una tirada de 3 cartas, un camino de vida
numérico, la interpretación de un Sol en casa 7, etc. Compara tono y fidelidad
con la base sin fine-tune.

## 6. Fusionar y exportar

```bash
# Fusiona el adaptador LoRA con la base (modelo completo)
soup merge --config soup.yaml

# Exporta a GGUF cuantizado para Ollama/llama.cpp/halogen
soup export --format gguf --quant q4_k_m
```

## 7. Servir en el homelab

- **Ollama (mini, 10.0.0.1)**: `ollama create adivina:1 --file Modelfile`
  apuntando al GGUF, o copia el GGUF a la carpeta de modelos de Ollama.
- **halogen (nodo1/nodo2)**: si se prefiere el motor flash_serve, cargar el
  GGUF vía la TUI (consulta `~/homelab.md`).

> Recordatorio de licencia: Qwen2.5 es Apache-2.0; el corpus propio debe ser
> de dominio público/CC o con licencia revisada antes de usarse en un
> producto de pago. Consulta `corpus/manifest.json`.
