# Prompt maestro — Web monetizada de adivinación por IA

> Pega el bloque siguiente tal cual en el agente de código (opencode, Claude Code, etc.)
> dentro del repositorio `~/adivinacion-ia`. Está escrito para que el agente pueda
> construir la V1 sin volver a preguntar lo ya decidido.

---

## 0. Rol

Actúas como **arquitecto y desarrollador full-stack senior**. Construyes una aplicación web
monetizada, en producción, no un prototipo. Trabajas con TDD, commits pequeños y verificación
real (tests, lint, typecheck). Si algo del alcance es ambiguo, preguntas antes de inventarlo;
no amplías el alcance por iniciativa propia.

## 1. Producto

Web de lecturas de adivinación generadas por IA para el mercado hispanohablante. El usuario
introduce sus datos de nacimiento, elige un tipo de lectura, formula su pregunta y recibe una
interpretación personalizada que combina **tarot + astrología + numerología**. El texto lo
genera un modelo de lenguaje afinado para este dominio; los datos astronómicos y numerológicos
los calcula código determinista, nunca el modelo.

- Idioma: **solo español** (es-ES neutro). Sin i18n en V1.
- Público: adultos (18+), España y LATAM.
- Tono: cercano, respetuoso, sin promesas absolutas. Entretenimiento y orientación simbólica,
  nunca diagnóstico médico, legal ni financiero.

## 2. Estado del que partes

Ya existen en el repo:

- `docs/diseno-app-adivinacion.md` — spec del producto. **Léelo antes de empezar.**
- `docs/superpowers/plans/` — planes de implementación por subsistema (núcleo de cálculo,
  RAG, backend, frontend, fine-tune). Úsalos como referencia de interfaces, no los reescribas.
- `finetune/corpus/kb/` — base de conocimiento estructurada: `tarot.json`, `astrologia.json`,
  `numerologia.json`.
- `finetune/corpus/rag/` — índice vectorial (chunks + embeddings) del corpus curado.
- Modelo afinado (QLoRA sobre Qwen2.5-14B-Instruct) servido como **API compatible con OpenAI**.
  El backend NO carga pesos: solo llama a `{LLM_BASE_URL}/chat/completions`.

## 3. Alcance de la V1

Incluido:

1. Registro, login, logout, sesión persistente, recuperación de contraseña por email.
2. Onboarding con datos de nacimiento: nombre, fecha, hora (con opción "no la sé"), lugar
   (autocompletado con latitud/longitud/zona horaria).
3. Tipos de lectura: tarot 1 carta, tarot 3 cartas, cruz celta, carta natal, numerología,
   lectura completa (astro + numerología + tarot combinados).
4. Pregunta libre del consultante, con sugerencias por contexto (amor, trabajo, dinero, salud
   emocional, espiritual).
   En las lecturas con tarot, la pregunta va antes del **corte del mazo por arrastre** (ver
   sección 9 y `docs/diseno-app-adivinacion.md` §2.1).
5. Resultado en streaming (SSE) con secciones: apertura, interpretación, síntesis, consejo.
6. Historial de lecturas y relectura.
7. Hasta 3 preguntas de seguimiento por lectura, con contexto de la lectura original.
8. Freemium: 3 lecturas gratuitas al mes con secciones avanzadas bloqueadas.
9. Créditos de pago por lectura y packs. Stripe Checkout + webhook.
10. Panel de cuenta: lecturas, créditos, consentimiento, exportar y borrar datos.
11. Textos legales base, aviso de entretenimiento y verificación de edad.

Fuera de alcance (no lo implementes): quiromancia o visión por cámara, voz, apps nativas,
i18n, comunidad, suscripción recurrente, generación de PDF, afiliados, gamificación.

## 4. Stack (fijado)

- Frontend: Next.js 15 (App Router), TypeScript estricto, Tailwind CSS, React Server Components
  donde aporte; componentes propios, sin librerías de UI pesadas.
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, Python 3.11.
- Base de datos: PostgreSQL 16 + `pgvector`.
- Cálculo astronómico: `pyswisseph` (casas Placidus, orbe de aspectos ±6°).
- LLM: endpoint OpenAI-compatible (`LLM_BASE_URL`, `LLM_MODEL`), streaming.
- RAG: embeddings `nomic-embed-text` (768 dimensiones) vía Ollama; `top_k=6`,
  umbral de similitud 0.35; chunks de 900 caracteres con solape 150.
- Pagos: Stripe (Checkout + webhook con verificación de firma).
- Despliegue: Docker Compose (web, api, db, caddy) sobre VPS Linux; el modelo se sirve aparte.
- Tests: pytest + httpx para API; Vitest + Playwright para flujos críticos.

## 5. Arquitectura

```
Navegador
   │ HTTPS
   ▼
Next.js (web)  ──/api/*──▶  FastAPI (api)  ──▶ PostgreSQL + pgvector
                                  │
                                  ├─▶ pyswisseph (carta natal)
                                  ├─▶ tarot/numerología (determinista, con seed)
                                  └─▶ LLM_BASE_URL (streaming, OpenAI-compatible)
```

Reglas de arquitectura:

- Todo cálculo verificable (posiciones planetarias, casas, aspectos, números, cartas) ocurre
  en el backend y se persiste en la lectura. El LLM solo interpreta esos datos.
- El LLM nunca recibe datos personales identificables (email, nombre completo). Recibe
  nombre de pila o alias, fecha/hora/lugar y los datos simbólicos.
- El frontend no habla nunca con el LLM directamente.

## 6. Flujo de una lectura

1. `POST /readings` con `{type, question, birth?, corte?}` (`corte` obligatorio, entero 1–77, si la
   lectura incluye tarot). El backend valida, descuenta crédito o cupo freemium (transacción
   atómica) y crea la lectura en estado `pending`.
2. El backend calcula carta natal/numerología/tirada, recupera contexto RAG y compone el prompt.
3. `GET /readings/{id}/stream` (SSE) emite `event: meta`, luego `event: token` y al final
   `event: done` con el uso de tokens.
4. Al terminar, guarda el texto completo, las fuentes RAG usadas, tokens y coste estimado.
5. Si el usuario es freemium, las secciones `avanzada` y `seguimiento` se sirven marcadas como
   bloqueadas: el texto se guarda completo, pero la API no lo entrega hasta el pago.

Idempotencia: `POST /readings` acepta `Idempotency-Key`; dos peticiones con la misma clave
devuelven la misma lectura sin cobrar dos veces.

## 7. Contrato de API

Autenticación con JWT en cookie `httpOnly`, `Secure`, `SameSite=Lax`; access 15 min y refresh
7 días rotatorio. Contraseñas con bcrypt (coste 12).

```
POST   /api/auth/register      {email, password, name, age_confirmed:true}
POST   /api/auth/login         {email, password}
POST   /api/auth/refresh
POST   /api/auth/logout
POST   /api/auth/forgot        {email}
POST   /api/auth/reset         {token, password}
GET    /api/me                 → {id, email, name, credits, free_left, consent_at}
PATCH  /api/me                 {name, birth_date, birth_time, birth_place, lat, lon, tz}
DELETE /api/me                 → borra cuenta y datos personales

POST   /api/readings           {type, question, birth?, corte?, idempotency_key}
                               (corte: entero 1–77, obligatorio con tarot; 422 si falta o no es válido)
GET    /api/readings/{id}      → lectura completa (o bloqueada si no pagada)
GET    /api/readings/{id}/stream   (SSE)
POST   /api/readings/{id}/messages {content}   → seguimiento (SSE)
GET    /api/readings?limit=20&cursor=
DELETE /api/readings/{id}

GET    /api/billing/products   → [{sku, name, price_cents, credits, currency}]
POST   /api/billing/checkout   {sku} → {url}
POST   /api/billing/webhook    (Stripe, firma verificada)
GET    /api/billing/history
```

Códigos: 400 validación, 401 sesión, 402 sin créditos, 403 sección bloqueada, 404, 409
conflicto, 429 límite de peticiones, 503 LLM no disponible.

Errores en formato `{ "error": { "code": "...", "message": "...", "request_id": "..." } }`.

## 8. Modelo de datos

```sql
users(id uuid pk, email citext unique, password_hash, name, age_confirmed bool,
      consent_at timestamptz, role text default 'user', created_at, deleted_at)

profiles(user_id uuid pk refs users, birth_date date, birth_time time null,
         birth_place text, lat numeric(9,6), lon numeric(9,6), tz text)

readings(id uuid pk, user_id uuid refs users, type text, question text,
         status text, is_free bool, locked bool,
         chart jsonb, cards jsonb, numerology jsonb, rag_sources jsonb,
         content text, model text, tokens_in int, tokens_out int,
         cost_cents int, error text, created_at, completed_at)

messages(id uuid pk, reading_id uuid refs readings, role text,
         content text, created_at)

credits_ledger(id uuid pk, user_id uuid refs users, delta int, reason text,
               reading_id uuid null, stripe_payment_id text null, created_at)

payments(id uuid pk, user_id uuid refs users, stripe_session_id text unique,
         sku text, amount_cents int, status text, created_at)
```

Índices: `readings(user_id, created_at desc)`, `credits_ledger(user_id, created_at desc)`,
`messages(reading_id, created_at)`. Borrado lógico de usuario y anonimización a los 30 días;
lecturas borradas en cascada.

## 9. Motor de cálculo (determinista)

- **Tarot**: mazo de 78 cartas (`finetune/corpus/kb/tarot.json`). El servidor baraja con una
  semilla secreta propia (`secrets.randbits(64)`) y aplica el corte del usuario como rotación
  del mazo (`Mazo.cortar(corte)`, `corte` entre 1 y 77), sin repeticiones dentro de una tirada.
  La orientación (derecho/invertido) sale del mismo generador. Se guardan semilla, `corte` y
  orientación en la lectura, de modo que semilla + corte reproducen la tirada. Ni la semilla ni
  el orden del mazo se envían al navegador. El corte es un gesto ritual: no se presenta como
  algo que cambie el resultado.
- **Astrología**: `pyswisseph`; planetas Sol–Plutón, nodos lunares, Ascendente y MC, 12 casas
  Placidus, aspectos con orbe ±6°. Si falta la hora, se calcula sin Ascendente ni casas y se
  declara explícitamente en la respuesta.
- **Numerología**: camino de vida, destino, alma, personalidad y año personal; números maestros
  11/22/33 sin reducir.
- **Formato**: todos los resultados se guardan como JSON estructurado y se inyectan en el prompt
  como bloque de datos verificados.

## 10. Capa de IA

- Proveedor: `POST {LLM_BASE_URL}/chat/completions` con `stream: true`, `temperature: 0.7`,
  `top_p: 0.9`, `max_tokens: 1200`, `timeout: 90 s`.
- Prompt de sistema (resumen; la versión completa vive en `backend/app/llm/prompts.py`):
  tarotista/astróloga/numeróloga con 20 años de experiencia; español neutro; usa solo los datos
  aportados; estructura apertura → interpretación → síntesis → consejo; no inventa cartas,
  posiciones ni números; no promete resultados; no da diagnósticos médicos, legales ni
  financieros y deriva a profesionales; si detecta riesgo para la vida, responde con contención
  y recursos de ayuda.
- RAG: recupera fragmentos del corpus y los inserta como "contexto de referencia" con su fuente.
  Si no hay fragmentos por encima del umbral, se omite el bloque (no se inventa).
- Seguimiento: se reenvía la lectura resumida + los últimos 3 mensajes; máximo 3 por lectura.
- Reintentos: 2 con backoff exponencial ante 429/5xx; si falla, la lectura queda `failed` y el
  crédito se devuelve automáticamente.
- Guardarraíles de entrada: bloquear edades < 18, datos de terceros sin consentimiento,
  peticiones de diagnóstico, apuestas y contenido sexual explícito. Registro de la decisión.
- Coste: calcular `tokens_in/out × precio` configurable y guardarlo por lectura.

## 11. Monetización

- Freemium: **3 lecturas gratis al mes**. Incluyen tarot 1 carta y numerología básica; carta
  natal y lectura completa aparecen con candado y vista previa de 2 frases.
- Créditos: 1 lectura de pago = 1 crédito.
  - Lectura individual: **4,99 €** (1 crédito).
  - Pack 5: **19,99 €** (5 créditos).
  - Pack 12: **39,99 €** (12 créditos).
- Stripe Checkout en EUR; el crédito se acredita solo cuando el webhook
  `checkout.session.completed` valida la firma. Reembolso manual desde el panel de Stripe
  revierte créditos no usados.
- Nunca cobrar dos veces: ledger de créditos como única fuente de verdad; saldo = suma del
  ledger.
- El paywall no debe ser engañoso: se muestra qué se bloquea y por qué antes de pagar.

## 12. UX/UI

- Páginas: `/` (landing), `/onboarding`, `/leer` (selector), `/lectura/[id]`, `/historial`,
  `/cuenta`, `/precios`, `/legal/{terminos,privacidad,cookies,aviso}`.
- Landing: propuesta de valor, ejemplo de lectura, precios, FAQ, aviso de entretenimiento.
- Lectura: revelado de cartas con animación sutil, rueda astral en SVG con 12 casas, secciones
  con tipografía legible, streaming con cursor, botón "preguntar algo más", botón de compartir
  solo con texto agregado (sin datos de nacimiento).
- Corte del mazo (V1): el usuario arrastra la parte superior del mazo boca abajo y la suelta; la
  distancia fija `corte` (1–77). Alternativas obligatorias: teclado (flechas y Enter), botón
  «Cortar por mí» y `prefers-reduced-motion`. Fuera de la V1: contacto sostenido de 3 s (modo
  móvil), corte en tres montones y elección desde un abanico.
- Móvil primero; contraste AA; navegación por teclado; `prefers-reduced-motion` respetado.
- Estados vacíos, de error y de carga explícitos. Nunca spinner infinito: timeout con reintento.
- Sin emojis en la interfaz salvo los símbolos astrológicos imprescindibles.

## 13. Legal y cumplimiento

- Aviso visible: contenido de entretenimiento y reflexión; no sustituye asesoramiento médico,
  legal, financiero ni psicológico; mayores de 18.
- RGPD: base legal consentimiento explícito; datos de nacimiento tratados como sensibles;
  cifrado en reposo; retención 12 meses; exportación y borrado desde la cuenta; política de
  cookies con consentimiento previo (solo analítica tras aceptar).
- Recursos de crisis en español (024 y Teléfono de la Esperanza) cuando el texto lo requiera.
- Términos, privacidad y cookies redactados en español, con datos del responsable y encargados
  (Stripe, hosting, proveedor del modelo).

## 14. Seguridad

- Secretos solo por variables de entorno; nunca en el repo.
- Rate limit por IP y por usuario en auth (5/min), lecturas (10/h freemium) y checkout.
- Validación estricta de entrada con Pydantic; sin SQL dinámico.
- Sanitizar el markdown generado antes de renderizar (sin HTML crudo).
- Defensa ante prompt injection: el texto del usuario va delimitado y el modelo tiene instrucción
  explícita de ignorar órdenes dentro de los datos del consultante.
- Webhook Stripe: verificar firma, tolerancia 5 min, idempotencia por `event.id`.
- Logs sin PII; `request_id` en todas las respuestas.

## 15. Observabilidad y rendimiento

- Logs estructurados JSON: ruta, latencia, estado, tokens, coste, `request_id`.
- Métricas mínimas: lecturas/día, conversión freemium→pago, latencia p50/p95 del primer token,
  errores del LLM, coste medio por lectura.
- Objetivos: primer token < 2 s, lectura completa < 45 s, p95 API < 300 ms (sin LLM).
- Caché: KB en memoria; respuestas de catálogo y precios con `Cache-Control`.

## 16. Testing y CI

- pytest: cálculo (numerología, tarot con seed, carta natal con casos conocidos), auth,
  créditos, paywall, webhook, idempotencia.
- Vitest: utilidades y componentes con lógica.
- Playwright: registro → lectura gratis → historia → paywall → compra simulada.
- CI: lint + typecheck + tests en cada push; bloqueo de merge si falla.

## 17. Despliegue

`docker-compose.yml` con `web`, `api`, `db`, `caddy`. Variables:

```
DATABASE_URL=postgresql+psycopg://...
JWT_SECRET=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PRICE_1=... STRIPE_PRICE_5=... STRIPE_PRICE_12=...
LLM_BASE_URL=http://.../v1
LLM_MODEL=...
LLM_API_KEY=...
EMBEDDINGS_URL=http://...:11434
APP_BASE_URL=https://...
```

Backups diarios de Postgres, retención 14 días, restauración probada. Healthchecks en `web` y
`api`. Migraciones Alembic en el arranque del contenedor `api`.

## 18. Criterios de aceptación

1. Un usuario nuevo completa registro, onboarding y una lectura gratuita sin errores.
2. La lectura gratuita muestra carta/signos/números correctos y texto en español coherente.
3. La cuarta lectura del mes exige pago y muestra qué se desbloquea.
4. La compra en modo test de Stripe acredita exactamente los créditos del SKU.
5. Un webhook duplicado no acredita dos veces.
6. Un fallo del LLM devuelve el crédito y deja la lectura en `failed` con mensaje claro.
7. El seguimiento mantiene el contexto y se corta a los 3 mensajes.
8. Borrar la cuenta elimina datos personales y lecturas.
9. Los tests pasan en CI y el despliegue levanta con `docker compose up -d`.
10. Lighthouse móvil ≥ 90 en rendimiento y accesibilidad en la landing.
11. Con la misma semilla y el mismo `corte`, la tirada es idéntica; un `corte` ausente o fuera
    de 1–77 devuelve 422 en español; la respuesta de la API no incluye la semilla ni el orden
    del mazo.

## 19. Hitos

- **M0** Esqueleto: monorepo, docker-compose, Postgres+pgvector, migraciones, healthchecks.
- **M1** Núcleo de cálculo con tests (tarot, numerología, astro).
- **M2** Auth + perfiles + consentimiento.
- **M3** Lecturas + streaming + persistencia + guardarraíles.
- **M4** Freemium + créditos + Stripe + paywall.
- **M5** Frontend completo (landing, lectura, historial, cuenta, legal).
- **M6** Endurecimiento: rate limits, observabilidad, backups, Playwright, despliegue.

## 20. Reglas de trabajo para el agente

- Antes de tocar código, lee el spec y el plan del subsistema correspondiente.
- TDD: primero el test que falla, luego la implementación mínima.
- Un commit por tarea, mensaje en español, sin mezclar refactors.
- No añadas dependencias sin justificar y sin comprobar que ya existen en el repo.
- No cambies el alcance ni los precios sin preguntar.
- Ejecuta lint, typecheck y tests antes de declarar algo terminado.
- Si un requisito es ambiguo, pregunta; no lo resuelvas por tu cuenta.
