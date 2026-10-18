# Selección del modelo base para el fine-tune

Criterios de selección (producto de pago, audiencia en español):

1. **Licencia comercial limpia**: Apache-2.0 (o MIT). Nada de CC-BY-NC ni gates.
2. **Buen español** en el modelo base (reduce el esfuerzo de SFT).
3. **Chat-tuned** (Instruct), para solo tener que enseñar dominio/estilo, no
   conversación desde cero.
4. **Tamaño acorde al hardware**: nodo1/nodo2 = AMD Strix Halo con 128 GB de
   memoria unificada (ROCm). Con QLoRA 4-bit se entrena cómodamente hasta 24-32B.
5. **Soportado por Soup**: Llama, Qwen 2.5/3, Mistral, Gemma, DeepSeek, Phi.

## Datos verificados (Hugging Face API)

| Modelo | Gate | Licencia | Descargas | Nota |
|---|---|---|---|---|
| **Qwen/Qwen2.5-14B-Instruct** | no | Apache-2.0 | 962 k | chat-tuned → PRIMARIA |
| Qwen/Qwen2.5-7B-Instruct | no | Apache-2.0 | 6,87 M | chat-tuned → iteración rápida |
| Qwen/Qwen2.5-32B-Instruct | no | Apache-2.0 | 1,45 M | gama alta |
| Qwen/Qwen3-8B | no | Apache-2.0 | 9,34 M | BASE (no Instruct) |
| Qwen/Qwen3-14B | no | Apache-2.0 | 8,06 M | BASE |
| Qwen/Qwen3-VL-8B-Instruct | no | Apache-2.0 | 6,47 M | visión → Fase 2 |
| mistralai/Mistral-Small-3.1-24B-Instruct-2503 | no | Apache-2.0 | 289 k | 24B de calidad |
| meta-llama/Llama-3.1-8B-Instruct | manual | llama3.1 | 5,56 M | gate + licencia con restricciones |

## Recomendación

**Base primaria: `Qwen/Qwen2.5-14B-Instruct`**

- Apache-2.0 sin gate → lo más limpio para un producto de pago.
- Chat-tuned → el SFT solo añade conocimiento/estilo esotérico.
- Mejor calidad y mejor español que el 7B; el Strix Halo (128 GB) lo
  entrena cómodamente con QLoRA 4-bit.
- Coste: ~2x más lento por paso que el 7B. Estrategia: iterar el pipeline
  con el 7B y hacer la versión final con el 14B.

**Iteración rápida**: `Qwen/Qwen2.5-7B-Instruct` (mismo family, mismo
pipeline, ~2x más rápido; útil para depurar dataset y `soup.yaml`).

**Escalado de calidad (opcional)**: `Qwen/Qwen2.5-32B-Instruct`;
alternativa no-Qwen: `mistralai/Mistral-Small-3.1-24B-Instruct-2503`.

**Fase 2 (visión/quiromancia)**: `Qwen/Qwen3-VL-8B-Instruct` (Apache-2.0,
image-text-to-text).

> Nota: Qwen3 denso solo publica modelos **base** (no hay repos
> "Qwen3-8B-Instruct"); para SFT simple de dominio conviene partir de una
> base ya instruct de Qwen2.5.
