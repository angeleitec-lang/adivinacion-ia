# adivinacion-ia

## Qué es

Modelo de lenguaje en español, de calidad alta, para hacer lecturas de **tarot (78 cartas), baraja española (40 naipes), carta astral (astrología occidental) y numerología (+ biorritmos)**. Producto final previsto: app web monetizada (diseño en `docs/diseno-app-adivinacion.md`; planes de backend FastAPI y frontend Next.js en `docs/superpowers/plans/`, aún sin código en el repo).

Hoy el repo contiene sobre todo la **tubería de datos y fine-tune** (`finetune/`): adquisición de conocimiento de calidad (fase 0), generación y validación del dataset (fase 1) y entrenamiento del modelo (fase 2). Alcance aplazado: quiromancia, Lenormand, I Ching, runas, Jyotish, BaZi, etc. (mapa completo en `tecnicasCartomancia.md`).

## Leer primero

`docs/ESTADO_Y_PENDIENTES.md`: traspaso completo (decisiones, estado de cada pista, procesos suspendidos, pendientes y plan de continuación). Después, `docs/PLAN_ADQUISICION_CALIDAD.md` y `docs/INVENTARIO_FUENTES.md`.

## Decisiones fijas del usuario (no reabrir)

- **Calidad por encima del plazo**: reunir información buena antes de generar el dataset final y entrenar.
- **Legalidad de los textos**: se revisa más adelante; cada documento conserva su procedencia (`finetune/corpus/license_filter.py`).
- **Presupuesto muy limitado**: no comprar nada sin avisar y justificarlo.
- **Rol de Claude aquí: coordinadora, no programa**, y **NO usar subagentes `Agent`** (el usuario los rechazó). Las IAs locales (opencode en nodo1/nodo2) programan en worktrees; ver protocolo en `~/.config/opencode/docs/coordinacion/PROTOCOLO.md`.
- **Git solo local**, sin remotos ni push.

## Estructura

- `docs/`: diseño, planes, estado y pendientes.
- `finetune/corpus/`: scripts de la tubería (recolección, limpieza, KB, generador sintético, validador, auditoría, fusión) y sus tests en `corpus/tests/`. `calculos/` tiene las calculadoras deterministas (carta natal, numerología, biorritmos); `kb/*.json` la base de conocimiento de significados.
- `finetune/knowledge/`: inventarios de fuentes y rejillas de URLs (libros, web, YouTube).
- `finetune/scraper/`: spider Scrapy; `finetune/scripts/check.sh`: verificación global.
- `finetune/*.md`: modelo base (`MODELO.md`, `DECISION_MODELO_MOE.md`), plan de cobertura y guía de reentrenamiento.
- `.worktrees/<pista>/`: un worktree por pista (rama `track/<pista>`), con `SIGUIENTE.md` (instrucciones) y `ESTADO.md` (progreso). Ambos y `.worktrees/` están en `.gitignore`.
- Datos pesados (`corpus/raw`, `final`, `synthetic`, `jobs.db`, `*.jsonl`, `knowledge/youtube`, `.venv`) están en `.gitignore`, no en el repo.

## Cómo trabajar

- Python: siempre `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python` (hay `uv`, no `pip`). Tests con `unittest` (no pytest).
- Verificación: `./finetune/scripts/check.sh` debe acabar en `CHECK OK`.
- Integrar una pista: revisar el diff, ejecutar casos adversos propios (no fiarse solo de los tests de la IA), `git merge --no-ff track/<pista>` desde la raíz y pasar `check.sh`.
- Un ajuste a una IA no se aplica solo por escribirlo en su `SIGUIENTE.md`: el usuario debe pegarle «Relee SIGUIENTE.md: hay una sección AJUSTE…».
- Las horas que anotan las IAs en sus `ESTADO.md` pueden ser inventadas; no usarlas como registro.

## Precauciones

- **No reanudar** (`kill -CONT`) los generadores sintéticos suspendidos (PID 66101 nodo1, 66396 nodo2): usan prompts viejos sin tildes. Hacer copia de `finetune/corpus/jobs.db` antes de regenerar con `generate_tasks.py --replace-pending`.
- Rate limits y cortesía: ≤ 1 petición/s por dominio, respetar `robots.txt`; no saltar bloqueos (astro.com, nymero.org, Reddit).
- Baraja española y naipes franceses son sistemas distintos: mantenerlos separados en la KB.
- Una IA puede dar `TRACK COMPLETO` antes de tiempo: verificar siempre.

## Infraestructura

Nodo1 (10.0.0.3, API OpenAI-compatible en `:8000/v1`) y nodo2 (10.0.0.4) para generación y entrenamiento; Mini (10.0.0.1) para Postgres/Ollama (embeddings); Firecrawl en `localhost:3002` (Docker). Detalle en el `CLAUDE.md` global.

## Memoria

Letta `scope=project`, `project: "adivinacion-ia"` (resúmenes y correcciones del 2026-10-18/19). Memoria local en `~/.claude/projects/-Users-angelgonzalez-adivinacion-ia/memory/`.
