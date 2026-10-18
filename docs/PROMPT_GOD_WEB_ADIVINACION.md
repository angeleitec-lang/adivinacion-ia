# Encargo para el God — Web monetizada de adivinación por IA

> **Uso.** En AgenteOS-Native el encargo es el único contexto que recibe el God, y vive en
> `notas/ENCARGO.md` de la raíz del proyecto (ver `docs/PRUEBA-CONCURRENCIA-10-MODULOS.md` §3.3 y §4
> del repositorio de AgenteOS-Native). Copia el bloque de abajo a `notas/ENCARGO.md`. Este prompt
> aporta el **qué** y las restricciones; el **cómo** (método, topes, herramientas) lo definen las
> reglas de AgenteOS-Native, que el God debe leer y aplicar.
>
> **Siembra previa (la hace el humano, hoy a mano; no hay script reutilizable):**
> 1. Crear en la app una empresa de tipo **Programación** (`orchestratorMaySpawn: true`) y el
>    proyecto, para que nazca con la estructura v2 (`.agenteos/` ignorada por git). Pendiente de
>    comprobar si la app admite adoptar la carpeta existente `~/adivinacion-ia` o hay que crear el
>    proyecto y mover allí `docs/`.
> 2. Un `scripts/check.sh` **real** (lint + typecheck + tests de backend y frontend). La app lo
>    ejecuta como verificación al integrar y revierte si falla, así que debe pasar en `main`.
> 3. Repositorio git con un commit `base` en `main`.
> 4. Si el God usa un modelo de pago, fijar `policy.costCapTokens`.
> 5. Recompilar la app con `./scripts/build-app.sh` (con la app cerrada) si se tocó código.

---

## 0. Primero: lee cómo funciona AgenteOS-Native y aplícalo

Antes de crear ninguna tarea, lee en `/Users/angelgonzalez/01_Proyectos_AI/AgenteOS-Native`:

- `AGENTS.md` — estructura del proyecto v2, comandos, convenciones y reglas de git.
- `docs/god-coordinacion.md` — tu método: ciclo de seis pasos, puerta `review_task` →
  `integrate_task`, `StallDetector`, verificación posterior con reversa.
- `Sources/AgenteOSApp/Resources/Templates/_shared/skills/coordinar-y-revisar/SKILL.md` y las
  skills `plan-de-equipo`, `descomponer-tareas`, `integrar-y-revisar` y `seguimiento-de-tareas`.
- `docs/capacidad-inferencia.md` — slots por servidor y tope de workers.

**Precedencia.** Para el *método* (cómo se reparte, se revisa, se integra, cuántos workers, qué
recursos pedir) mandan esas reglas de AgenteOS-Native; este encargo no las repite ni las
sustituye. Para el *producto* manda `docs/diseno-app-adivinacion.md`; después, los planes de
`docs/superpowers/plans/`; después, `docs/PROMPT_WEB_MONETIZADA.md` (sus hitos M0–M6 y reglas de
trabajo son orientativos: el reparto lo decide el arquitecto). Si dos fuentes se contradicen y no
lo resuelve esta precedencia, no lo resuelvas tú: pregunta al humano.

Lo que debes aplicar de AgenteOS-Native a este proyecto:

- **Orden:** crea primero solo la tarea del arquitecto. Él cierra `docs/ARQUITECTURA.md` con la
  sección «Plan de equipo» (perfiles, unidades, skills —máximo 3 por perfil— y paralelismo útil).
  Espera su `done`, léela y reparte según ella. Tú no escribes código ni arreglos de una palabra:
  se devuelven.
- **Tareas:** cada una con contrato de 4 partes, `files` cerrados (qué puede y qué NO tocar),
  `dependsOn` declarado, extracto del plan («no leas el resto») y comando de verificación exacto.
  Una tarea por agente a la vez. `task_assign` rechaza tareas `blocked`.
- **Aislamiento:** cada worker trabaja en su worktree (`.agenteos/hive/worktrees/<agente>`, rama
  `task/<id>`); `main` no se toca a mano. Todo agente es una terminal de opencode.
- **Capacidad:** antes de lanzar workers, lee el bloque de capacidad de tu prompt. Los modelos
  locales tienen 4 slots por nodo (nodo1, nodo2) y el tope global es 10 workers; leer contextos
  grandes se serializa, así que las tareas llevan contexto pequeño. Si la app rechaza por falta de
  hueco, espera; no insistas ni cambies de modelo.
- **Revisión e integración:** `review_task` (rechaza ficheros fuera de `files`, tests borrados,
  árbol sin commitear) → lectura del diff contra el plan → `integrate_task` (merge `--no-ff` local).
  Máximo 2 devoluciones por tarea con corrección exacta; a la tercera, `escalate`. Tras integrar,
  la app ejecuta `scripts/check.sh` y revierte si falla.
- **Recursos:** si hace falta una skill o un MCP que no esté en el catálogo (p. ej. Stripe,
  pyswisseph, pgvector, Playwright), se solicita con `resource_request`. Nunca se instala nada por
  cuenta propia: la app busca y el humano aprueba e instala.
- **Memoria y cierre:** decisiones y devoluciones en `reviews/`; lo duradero en `memory.md`;
  informe breve al humano; limpia worktrees y ramas integradas.
- **Git:** solo local. Commits convencionales (`feat(...)`, `fix(...)`, `test(...)`, `docs(...)`),
  uno por tarea, con el texto en español.
- **Tests:** TDD; en el código del proyecto, lo que corresponda a cada lenguaje (pytest, Vitest,
  Playwright). Cada tarea se verifica con `scripts/check.sh`.

## 1. Encargo

Construir en este proyecto la **V1** de una web monetizada de lecturas de adivinación por IA
(tarot + astrología + numerología), solo en español. Fuentes de verdad, que se referencian y no se
copian: `docs/diseno-app-adivinacion.md` (spec), `docs/superpowers/plans/` (planes por subsistema:
núcleo de cálculo, backend, frontend, fine-tune y RAG) y `docs/PROMPT_WEB_MONETIZADA.md`
(especificación completa del producto). Léelas antes de crear tareas.

## 2. Decisiones ya tomadas (no se reabren; el arquitecto parte de ellas)

- Stack: Next.js 15 + TypeScript estricto + Tailwind; FastAPI + Pydantic v2 + SQLAlchemy 2.0 +
  Alembic (Python 3.11); PostgreSQL 16 + pgvector; `pyswisseph`; Stripe Checkout + webhook;
  Docker Compose (`web`, `api`, `db`, `caddy`).
- El LLM se consume por `LLM_BASE_URL` (OpenAI-compatible, streaming); el backend no carga pesos.
- Cálculo astronómico, de tarot y numerología: código determinista; el LLM solo interpreta.
- Alcance, precios y criterios de aceptación: los de `docs/PROMPT_WEB_MONETIZADA.md` (secciones 3,
  11 y 18). No cambian sin preguntar al humano.
- Fuera de alcance: quiromancia, voz, apps nativas, i18n, suscripciones, PDF, afiliados.

### Requisito V1: pregunta y corte del mazo (decidido por el humano el 2026-10-18)

Fuente: `docs/diseno-app-adivinacion.md` §2.1; repartido en `2026-10-18-nucleo-calculo.md` (Task 2),
`2026-10-18-backend-api.md` (Task 2) y `2026-10-18-frontend.md` (Task 3A). El arquitecto lo recoge
en `docs/ARQUITECTURA.md` y el «Plan de equipo» lo asigna sin que dos agentes se pisen ficheros.

- Flujo: pregunta obligatoria → corte del mazo por arrastre → reparto y volteo → interpretación.
- El cliente envía solo `corte` (entero 1–77). El servidor baraja con su semilla secreta
  (`secrets.randbits(64)`) y aplica `Mazo.cortar(corte)`. La semilla y el orden del mazo no llegan
  nunca al navegador; se guardan en `Reading.resultado` con `corte` y la orientación de cada carta.
  Esto sustituye a `seed = hash(reading_id)` de versiones anteriores del prompt de producto.
- Accesibilidad obligatoria: ratón, táctil y teclado, botón «Cortar por mí» y
  `prefers-reduced-motion`.
- Fuera de la V1: contacto sostenido de 3 s (modo móvil, posterior), corte en tres montones y
  elección desde un abanico. El corte es un gesto ritual: la interfaz no lo presenta como algo que
  cambie el resultado.
- Criterio de aceptación 11: misma semilla y mismo `corte` ⇒ tirada idéntica; `corte` ausente o
  fuera de 1–77 ⇒ 422 en español; la respuesta de la API no incluye semilla ni orden del mazo.

## 3. Qué decide el equipo (no este encargo)

El despiece en módulos y tareas, los roles, el número de workers, su paralelismo, el orden de las
migraciones de Alembic y la propiedad de los ficheros compartidos (`main.py`, registro de modelos,
`layout.tsx`): los fija el arquitecto en `docs/ARQUITECTURA.md` y tú los ajustas a los topes.

## 4. Restricciones de producto que aplican a todo el equipo

- El LLM nunca recibe email ni nombre completo; el frontend nunca habla con el LLM.
- Webhook de Stripe con firma verificada e idempotencia por `event.id`; saldo = suma del ledger.
- Un fallo del LLM deja la lectura en `failed` y devuelve el crédito.
- Sin secretos en el repositorio; logs sin PII.
- Comentarios, documentación y texto de la interfaz en español estándar; sin emojis en la UI.
- Si un requisito es ambiguo, se pregunta al humano.

## 5. Cierre

Declara terminada la V1 solo cuando los 10 criterios de la sección 18 de
`docs/PROMPT_WEB_MONETIZADA.md`, más el 11 del corte, estén comprobados con evidencia (comando y
salida). Los que exigen validación manual (Stripe en modo test, Lighthouse móvil,
`docker compose up -d`) se los pasas al humano. **Nada se sube a ningún remoto.**

Empieza por leer lo de la sección 0. Después comprueba que existen `scripts/check.sh` y el commit
`base`; si falta algo, avisa al humano y espera. Luego sigue el flujo: tarea del arquitecto primero.
