> **NOTA (2026-10-18, noche) — LEER ANTES:** este plan se redactó antes de la auditoría y **está superado en varios puntos**: (1) los 56 arcanos menores de la KB eran texto genérico y se están reescribiendo; (2) el dataset `final/` no es entrenable (el auditor deja 1.991 de 4.653 pares); (3) el generador tenía 3 bugs graves (zona horaria, tildes, año personal) ya corregidos en rama; (4) el alcance se acotó a tarot, baraja española, astrología occidental y numerología; (5) la generación sintética NO debe empezar hasta cerrar la fase 0 de adquisición. Estado vigente y pasos: `docs/ESTADO_Y_PENDIENTES.md` y `docs/PLAN_ADQUISICION_CALIDAD.md`.

# Fine-tuning del modelo de adivinación (adivinacion-ia)

Espacio de trabajo del track A (fine-tune). Aquí se prepara el corpus, se
reentrena el modelo base y se exporta para servirlo en la app.

## Pipeline (visión general)

1. Extraer el corpus de manuales/técnicas/tutoriales con Firecrawl (ver `corpus/`).
2. Limpiar y formatear el corpus a formato ShareGPT (JSONL).
3. Reentrenar el modelo base con Soup (QLoRA).
4. Evaluar, fusionar (merge) y exportar a GGUF.
5. Servir con Ollama/halogen en el homelab.

## Ficheros

| Fichero | Contenido |
|---|---|
| `MODELO.md` | Selección del modelo base y justificación |
| `GUIA_REENTRENAMIENTO.md` | Pasos concretos (comandos) con Soup + Firecrawl |
| `corpus/INSTRUCCIONES_FIRECRAWL.md` | Documento que lee Firecrawl para extraer el corpus |
| `corpus/urls.txt` | Lista plana de URLs fuente (una por línea) |

## Orden recomendado

1. Leer `MODELO.md` para confirmar la base.
2. Leer `corpus/INSTRUCCIONES_FIRECRAWL.md` y lanzar la extracción.
3. Seguir `GUIA_REENTRENAMIENTO.md` paso a paso.

> Relación con el resto del proyecto: ver los planes en
> `~/adivinacion-ia/docs/superpowers/plans/` (Plan 3 = track A fine-tune).
