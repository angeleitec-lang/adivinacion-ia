# adivinacion-ia

Modelo de lenguaje en español, de calidad alta, para hacer lecturas de **tarot (78 cartas)**, **baraja española (40 naipes)**, **carta astral** (astrología occidental) y **numerología** (con biorritmos).

El producto final previsto es una aplicación web de lecturas (diseño en [`docs/diseno-app-adivinacion.md`](docs/diseno-app-adivinacion.md)). Hoy el repositorio contiene sobre todo la **tubería de datos y de fine-tune**; la aplicación web (backend FastAPI, frontend Next.js) está planificada en [`docs/superpowers/plans/`](docs/superpowers/plans/) pero aún no tiene código.

> **Estado:** en desarrollo, sin modelo publicado. Primer piloto previsto: Qwen2.5-7B-Instruct con QLoRA sobre el dataset v1g (12.315 ejemplos).

## Cómo funciona la tubería

```
fuentes (libros, web, vídeo)  →  evidencias con procedencia  →  afirmaciones
        →  consenso entre fuentes  →  base de conocimiento (KB)
        →  generación sintética de lecturas  →  verificación y auditoría
        →  dataset ShareGPT (train / val / test)  →  fine-tune QLoRA  →  evaluación
```

Principios de diseño:

- **Calidad antes que plazo**: se reúne y verifica el conocimiento antes de generar el dataset final.
- **Procedencia por documento**: cada fragmento conserva su fuente y licencia (`finetune/corpus/license_filter.py`).
- **Cálculos deterministas**: carta natal, numerología y biorritmos se calculan con código (`finetune/corpus/calculos/`), no los inventa el modelo.
- **Sistemas separados**: la baraja española y los naipes franceses se mantienen distintos en la KB.
- **Ética**: el modelo debe rechazar lo que cae fuera de alcance (salud, legal, predicciones de muerte, etc.) y no presentar la adivinación como certeza.

## Estructura

| Ruta | Contenido |
|---|---|
| `docs/` | Diseño, planes, informes de cada versión del dataset, estado y pendientes |
| `docs/guia/` | Guía para principiantes: mapa de programas, glosario |
| `finetune/corpus/` | Scripts de la tubería (recolección, limpieza, KB, generador, validador, auditoría, fusión) y sus tests |
| `finetune/corpus/calculos/` | Calculadoras de carta natal, numerología y biorritmos |
| `finetune/corpus/kb/` | Base de conocimiento de significados (JSON) |
| `finetune/knowledge/` | Inventarios de fuentes y rejillas de URLs |
| `finetune/scraper/` | Spider Scrapy |
| `finetune/entrenamiento/` | Configuración de entrenamiento (QLoRA) |
| `finetune/scripts/` | Verificación global (`check.sh`) y scripts de coordinación |

Los datos pesados (corpus en bruto, datasets, base de trabajos, entornos virtuales) **no están en el repositorio**; viven fuera de él y están en `.gitignore`.

## Empezar

Requisitos: Python 3 y [`uv`](https://docs.astral.sh/uv/).

```bash
cd finetune
uv venv .venv
# instala las dependencias que necesite el script concreto con uv pip install
./scripts/check.sh      # verificación global; debe terminar en "CHECK OK"
```

Los tests usan `unittest` (no pytest):

```bash
.venv/bin/python -m unittest discover -s corpus/tests
```

## Documentación recomendada

1. [`docs/CONTINUAR.md`](docs/CONTINUAR.md): traspaso vigente y siguientes pasos.
2. [`docs/ESTADO_Y_PENDIENTES.md`](docs/ESTADO_Y_PENDIENTES.md): decisiones, estado de cada pista y pendientes.
3. [`docs/PIPELINE.md`](docs/PIPELINE.md): descripción de la tubería.
4. [`docs/PLAN_ADQUISICION_CALIDAD.md`](docs/PLAN_ADQUISICION_CALIDAD.md) e [`docs/INVENTARIO_FUENTES.md`](docs/INVENTARIO_FUENTES.md): cómo se reúne el conocimiento.
5. [`docs/LANZAR_PILOTO_7B.md`](docs/LANZAR_PILOTO_7B.md): runbook del primer entrenamiento.
6. [`tecnicasCartomancia.md`](tecnicasCartomancia.md): mapa de técnicas y alcance aplazado (quiromancia, Lenormand, I Ching, runas, Jyotish, BaZi…).

## Aviso

Las lecturas son entretenimiento y reflexión personal, no sustituyen asesoramiento médico, legal ni financiero. La revisión legal de los textos de origen está pendiente; no se redistribuyen libros completos.

## Licencia

Sin licencia definida todavía: todos los derechos reservados hasta que se decida una.
