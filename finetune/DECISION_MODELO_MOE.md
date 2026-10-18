# Decisión pendiente: modelo base para el fine-tune

Fecha: 2026-10-18
Estado: propuesta aceptada como candidata, **pendiente de spike de viabilidad**.

## Propuesta

Sustituir `Qwen/Qwen2.5-14B-Instruct` (denso, 14B) por un MoE:

1. **Primera opción**: `Qwen/Qwen3.5-35B-A3B` — 35,95B totales, ~3B activos.
2. **Fallback de tooling**: `Qwen/Qwen3-30B-A3B-Instruct-2507` — texto puro, 30,5B, tooling maduro.
3. **Fallback conservador**: `Qwen/Qwen2.5-14B-Instruct` — denso, ya descargado en nodo1, sin riesgos de MoE.

Configuración propuesta: **LoRA en bf16, router congelado, sin QLoRA 4 bits** (bitsandbytes y MoE no se llevan bien; la guía de Qwen3.5 lo desaconseja explícitamente).

## Datos verificados (2026-10-18)

Consultas directas a la API de Hugging Face, al `pyproject.toml` y README de Soup, y al conversor de llama.cpp (rama master).

| Comprobación | Resultado |
|---|---|
| `Qwen/Qwen3.5-35B-A3B` existe | Sí, 1.411.161 descargas, `gated=None` |
| Licencia | **Apache-2.0** |
| Parámetros | 35.951.822.704 (BF16) |
| Arquitectura | `Qwen3_5MoeForConditionalGeneration` (text_config: `qwen3_5_moe_text`) |
| Capas / hidden | 40 / 2048 |
| Expertos | **256 totales, 8 activos por token**, `moe_intermediate_size` 512 |
| Contexto | 262.144 |
| Vocabulario | 248.320 |
| Modalidad | **image-text-to-text (multimodal)**, no solo texto |
| Variante `-Base` | Existe y es distinta: para SFT hay que usar la instruct, no `-Base` |
| Soup: tarea MoE | Declarada (`moe` en la lista de tareas) y fila propia en la guía de VRAM |
| Soup: Qwen3.5 | `pyproject.toml` menciona una política explícita `qwen3_5_text` para PEFT |
| Soup: dependencias | `torch>=2.6`, `transformers>=5.16.1,<6`, `peft>=0.20,<1`, `trl>=0.29,<1` |
| llama.cpp: conversión GGUF | `conversion/qwen.py` y `conversion/qwen3vl.py` incluyen `Qwen3_5MoeForConditionalGeneration`, `Qwen3_5MoeForCausalLM` y `QWEN35MOE` |
| Unsloth | Publica `unsloth/Qwen3.5-35B-A3B-GGUF`, pero sigue siendo CUDA-first |

Fuentes: `huggingface.co/api/models/...`, `raw.githubusercontent.com/MakazhanAlpamys/Soup/main/{README.md,pyproject.toml}`, `raw.githubusercontent.com/ggml-org/llama.cpp/master/conversion/*`.

## Correcciones a las estimaciones iniciales

- **VRAM**: 35,95B × 2 bytes = **72 GB solo de pesos**, no 74 GB "de entrenamiento". Con activaciones, gradientes de adaptadores y checkpointing, el run real ronda **85-90 GB** sobre los 122 GB del nodo. Cabe, pero deja poco margen.
- **QLoRA 4 bits**: no usarlo con MoE. bf16 LoRA es la opción segura.
- **Router**: congelarlo. Entrenarlo es inestable y puede colapsar expertos; para un dominio estrecho no aporta.

## Riesgos abiertos

1. **ROCm en gfx1151 (Strix Halo)**. PyTorch funciona, pero Unsloth no es ROCm-native y Soup lo usa como extra `fast`. El camino realista es el backend transformers de Soup (PEFT + bitsandbytes ROCm, soporte no oficial). Sin probar.
2. **Merge de un LoRA sobre un MoE**. PEFT debería fundir los adaptadores en las MLP de los expertos, pero hay que verificar que no falle en silencio (Soup tiene `soup adapters check`).
3. **GGUF del modelo fusionado**. El conversor existe en upstream, pero no está probado el ciclo completo LoRA → merge → GGUF → Ollama con un MoE multimodal.
4. **Envoltorio multimodal**. El modelo es image-text-to-text; para SFT solo de texto hay que congelar la torre de visión y usar el processor. Añade piezas móviles.
5. **Throughput en Strix Halo**. Memoria unificada (~256 GB/s) es buena para inferencia y mediocre para entrenar: se espera un ritmo bajo comparado con una GPU dedicada.
6. **Español**. No hay comparación directa publicada entre Qwen2.5-14B y Qwen3.5-35B-A3B; hay que evaluarlo con el set de validación propio.

## Multimodalidad y alcance del LoRA (verificado en los pesos)

Rutas reales de los tensores según `model.safetensors.index.json` (1.811 tensores):

- Texto: `model.language_model.*`
- Visión: `model.visual.*` (`blocks`, `merger`, `norm`)
- Por capa de texto (40 capas, arquitectura híbrida):
  - Capas 0, 1, 2 (y el mismo patrón cada 4): `linear_attn.{in_proj_qkv, in_proj_z, in_proj_a, in_proj_b, out_proj, conv1d, A_log, dt_bias, norm}`
  - Capas 3, 7, ...: `self_attn.{q, k, v, o}_proj` + `q_norm`, `k_norm`
  - Todas: `mlp.gate` (router), `mlp.experts.gate_up_proj` y `mlp.experts.down_proj` (fusionados), `mlp.shared_expert.{gate, up, down}_proj`, `mlp.shared_expert_gate`

Consecuencias:

1. **No usar una lista simple** `["q_proj", "v_proj"]`: solo tocaría las capas con `self_attn` (~10 de 40) y dejaría fuera la atención lineal, que es la mayoría.
2. Usar `target_modules` como **regex acotada a `model.language_model`**:
   `.*language_model.*\.(self_attn\.(q|k|v|o)_proj|linear_attn\.(in_proj_qkv|in_proj_z|out_proj)|mlp\.shared_expert\.(gate|up|down)_proj)$`
3. **Excluir explícitamente**: `mlp.gate` (router), `mlp.shared_expert_gate`, `mlp.experts.*` y todo `model.visual.*`.
4. **Verificación obligatoria** tras el primer paso del spike: leer las claves de `adapter_model.safetensors` y comprobar que **todas** contienen `language_model` y que **ninguna** contiene `visual`, `mlp.gate` ni `experts`.
5. Usar la variante **instruct** (`Qwen/Qwen3.5-35B-A3B`), nunca `-Base`.
6. Entrenamiento solo de texto: torre visual congelada, sin imágenes en el dataset, pero manteniendo el chat template del processor.

Duda abierta: LoRA sobre los tensores fusionados de expertos (`gate_up_proj`, 3D) puede no estar soportado por PEFT. Si se quisiera tocar expertos, habría que desempaquetar o pasar por Unsloth. Para estilo y tono debería bastar con atención + `shared_expert`.

## Spike de viabilidad (protocolo)

Ejecutar cuando nodo1 quede libre (primero termina la traducción EN→ES).

1. **Entrenar**: `soup init` + config con `Qwen/Qwen3.5-35B-A3B`, `task: sft`, LoRA bf16, router congelado y `target_modules` regex acotada al texto, 20 pasos sobre ~50 ejemplos del dataset. Criterio: la loss baja, no hay OOM ni error de arquitectura y **las claves del adaptador están todas bajo `model.language_model`** (ninguna en `model.visual`, `mlp.gate` ni `experts`).
2. **Adapter**: `soup adapters check` sobre el adaptador generado. Criterio: sin avisos de fallo silencioso.
3. **Merge + export**: `soup merge` y `soup export --format gguf --quant q4_k_m`. Criterio: el GGUF carga en Ollama y responde con coherencia.
4. **Calidad**: 20 prompts del dominio contra el modelo fusionado y contra el base. Criterio: mejora clara de tono/formato, sin degradar el español.

Duración estimada: 1-2 h. Coste: 0 € en el homelab.

## Regla de decisión

| Resultado del spike | Decisión |
|---|---|
| Los 3 pasos técnicos pasan | Entrenar `Qwen3.5-35B-A3B` (bf16 LoRA) |
| Falla ROCm pero el resto pinta bien | Alquilar A100 80 GB o H100 (~0,44-1,33 $/h); 10-20 h ≈ **5-30 $** |
| Falla merge o GGUF | Caer a `Qwen3-30B-A3B-Instruct-2507` (texto puro, tooling maduro) |
| Falla también el fallback MoE | Quedarse con `Qwen2.5-14B-Instruct` (denso) para V1 |

## Por qué el MoE tiene sentido si pasa el spike

- Solo ~3B activos por token: inferencia mucho más barata y rápida que un denso de 30-35B, que es justo el coste dominante del producto a escala.
- Apache-2.0 y sin gate: monetización limpia.
- Al ser multimodal, podría cubrir también la Fase 2 (quiromancia) sin cambiar de base.

## Por qué no es urgente

- El cuello de botella actual es el **dataset**, no el modelo base.
- El producto V1 puede lanzarse con el 14B denso; el MoE es una mejora de economía de inferencia, no un requisito.
- El pipeline (traducción, generación sintética, validación, merge) es independiente del modelo elegido.
