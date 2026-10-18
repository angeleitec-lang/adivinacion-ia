# Índice de planes de implementación

Proyecto: app web monetizada de adivinación por IA. Spec:
`docs/diseno-app-adivinacion.md`.

Orden de implementación (por dependencias):

| # | Plan | Archivo | Depende de |
|---|---|---|---|
| 1 | Núcleo de cálculo determinista | `2026-10-18-nucleo-calculo.md` | — |
| 2 | Track B — RAG | `2026-10-18-track-b-rag.md` | Plan 1 (interfaces de cálculo) |
| 3 | Track A — Fine-tune | `2026-10-18-track-a-finetune.md` | Plan 2 (corpus) |
| 4 | Backend API (FastAPI) | `2026-10-18-backend-api.md` | Plan 1, 2 (y 3 cuando exista el modelo) |
| 5 | Frontend (Next.js) | `2026-10-18-frontend.md` | Plan 4 |

**Dependencias externas previas (setup, fuera de los planes):**
- Repo monorepo en `~/adivinacion-ia/` con `backend/`, `frontend/`, `data/`.
- Python 3.11 (Soup exige 3.10–3.12, NO 3.13).
- Postgres + extensión `pgvector` en el mini (10.0.0.1).
- Ollama en el mini con `nomic-embed-text` (embeddings) y, para dev, un modelo
  de generación (`qwen3:8b`); producción apunta a halogen `:8000` (nodo1).
- Entorno ROCm PyTorch en nodo1 para el fine-tune (Plan 3, Task 1).
