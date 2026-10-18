# Backend API (FastAPI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer una API REST que orqueste el cálculo determinista (Plan 1) y
la interpretación RAG (Plan 2) en un único endpoint de lectura, con usuarios,
límite freemium y pago por lectura (Stripe).

**Architecture:** FastAPI con routers por dominio; capa de persistencia con
SQLAlchemy sobre Postgres; el orquestador de lectura compone cálculo + RAG sin
lógica de negocio en los routers.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.x + Alembic, psycopg,
Pydantic v2, PyJWT, Stripe SDK.

**Spec:** `docs/diseno-app-adivinacion.md` (secciones 2, 2.1, 7).

## Global Constraints

- Idioma del producto: español (mensajes de error y literales de la API).
- Respuestas JSON camelCase en la API externa.
- Los endpoints no calculan nada: delegan en `app.core` (Plan 1) y `app.rag`
  (Plan 2).
- Freemium: N lecturas gratis por usuario (N por defecto 3, configurable);
  superado el límite, la lectura devuelve contenido parcial o exige pago.
- Pagos con Stripe; nunca guardar la clave en el repo (env var `STRIPE_API_KEY`).

## Review Focus

1. Petición sin fecha de nacimiento o con fecha inválida debe devolver 422 con
   mensaje en español, no 500 — Task 2.
2. Usuario no autenticado no puede crear lectura — Task 3.
3. Usuario con 0 lecturas restantes y sin pago no recibe la interpretación
   completa — Task 3.
4. Webhook de Stripe con firma inválida debe rechazarse (no procesar el pago)
   — Task 4.
5. Lectura creada para un usuario no debe ser visible por otro (aislamiento)
   — Task 3.
6. `corte` ausente o fuera de 1–77 devuelve 422 en español, y la respuesta nunca
   incluye la semilla ni el orden del mazo — Task 2.

---

### Task 1: Modelos de datos y migraciones

**Files:**
- Create: `backend/app/db/base.py`, `backend/app/db/models.py`
- Create: `backend/alembic/` (inicial + primera migración)
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: (nada)
- Produces:
  - `User`: `id`, `email` (único), `hashed_password`, `created_at`.
  - `Reading`: `id`, `user_id` (FK), `tipo` (`tarot`/`astro`/`numerologia`/
    `completa`), `pregunta`, `resultado` (JSONB), `created_at`.
  - `Payment`: `id`, `user_id` (FK), `stripe_session_id` (único), `amount`,
    `status`, `created_at`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_user_email_unico(session):
    session.add(User(email="a@b.c", hashed_password="x"))
    session.commit()
    with pytest.raises(IntegrityError):
        session.add(User(email="a@b.c", hashed_password="y"))
        session.commit()
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_models.py -v`
Expected: FAIL (tablas no existen).

- [ ] **Step 3: Implementar los modelos en `backend/app/db/models.py`**

Enfoque: declarar los tres modelos con SQLAlchemy 2.0 (`Mapped`/`mapped_column`),
`Reading.resultado` como JSONB, y `unique=True` en `User.email` y
`Payment.stripe_session_id`. Migración inicial con Alembic.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/base.py backend/app/db/models.py backend/alembic backend/tests/test_models.py
git commit -m "feat: modelos User/Reading/Payment y migración inicial"
```

---

### Task 2: Endpoint de lectura (orquestador)

**Files:**
- Create: `backend/app/api/readings.py`
- Create: `backend/app/services/orquestador.py`
- Create: `backend/app/schemas.py`
- Create: `backend/tests/test_readings.py`

**Interfaces:**
- Consumes: `calcular_carta` (Plan 1), `lectura_numerologica` (Plan 1),
  `tirada_tres_cartas` (Plan 1), `retrieve` + `interpretar` (Plan 2).
- Produces:
  - `Orquestador.orquestar(payload: ReadingRequest) -> dict` — con claves
    `astro`, `numerologia`, `tarot`, `interpretacion`.
  - `POST /api/readings` → `ReadingResponse` (camelCase).

- [ ] **Step 1: Escribir los tests que fallan**

```python
from app.services.orquestador import Orquestador

def test_orquestar_incluye_tres_disciplinas(monkeypatch):
    def fake_interpretar(calculo, pregunta, contexto):
        return "interpretación"
    monkeypatch.setattr("app.rag.generate.interpretar", fake_interpretar)
    payload = ReadingRequest(
        fecha_nacimiento="1990-01-10", hora="12:00", lat=40.4, lon=-3.7,
        tz=1.0, pregunta="¿amor?", corte=10,
    )
    r = Orquestador().orquestar(payload)
    assert set(r) == {"astro", "numerologia", "tarot", "interpretacion"}

def test_fecha_invalida_422(client):
    resp = client.post("/api/readings", json={"fecha_nacimiento": "no-fecha"})
    assert resp.status_code == 422

def test_corte_obligatorio_y_en_rango_422(client, user_token):
    base = {"fecha_nacimiento": "1990-01-10", "lat": 40.4, "lon": -3.7,
            "tz": 1.0, "pregunta": "¿amor?"}
    for extra in ({}, {"corte": 0}, {"corte": 78}):
        r = client.post("/api/readings", json={**base, **extra}, headers=user_token)
        assert r.status_code == 422

def test_tirada_reproducible_con_semilla_y_corte(monkeypatch):
    monkeypatch.setattr("app.rag.generate.interpretar", lambda c, p, ctx: "x")
    payload = ReadingRequest(
        fecha_nacimiento="1990-01-10", lat=40.4, lon=-3.7, tz=1.0,
        pregunta="¿amor?", corte=25,
    )
    a = Orquestador().orquestar(payload, semilla=99)
    b = Orquestador().orquestar(payload, semilla=99)
    assert a["tarot"] == b["tarot"]
```

Además, en Step 3 el implementador añade un test que comprueba que
`Reading.resultado` guarda `semilla` y `corte` y que el JSON de respuesta de
`POST /api/readings` no contiene la clave `semilla`.

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_readings.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar el orquestador y el router**

Enfoque: `orquestar(payload, semilla=None)` calcula carta astral + numerología +
una tirada de tres cartas, los serializa a `dict`, llama a `retrieve` para el
contexto y a `interpretar` para el texto final. La tirada se hace así (spec §2.1):
`semilla` se genera en el servidor con `secrets.randbits(64)` si no se inyecta
(el parámetro existe para los tests), y el mazo sale de
`Mazo(MAZO).barajar(semilla).cortar(payload.corte)`. Se guardan `semilla`,
`corte` y la orientación de cada carta dentro de `Reading.resultado`; la
respuesta de la API no devuelve ni la semilla ni el orden del mazo.
`ReadingRequest.corte` es un entero obligatorio con `Field(ge=1, le=77)` para las
lecturas con tarot. El router valida con Pydantic (mensajes de error en español
vía configurador de errores) y devuelve camelCase.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_readings.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/readings.py backend/app/services/orquestador.py backend/app/schemas.py backend/tests/test_readings.py
git commit -m "feat: endpoint de lectura que orquesta cálculo y RAG"
```

---

### Task 3: Autenticación y límite freemium

**Files:**
- Create: `backend/app/api/auth.py`
- Create: `backend/app/services/limites.py`
- Create: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: modelo `User`, `Reading` (Task 1); router de lecturas (Task 2).
- Produces:
  - `crear_token(user: User) -> str` (JWT).
  - `lecturas_restantes(user_id: int) -> int`.
  - `GET /api/auth/me`, `POST /api/auth/register`, `POST /api/auth/login`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_registro_y_login(client):
    client.post("/api/auth/register", json={"email": "a@b.c", "password": "secreto123"})
    r = client.post("/api/auth/login", json={"email": "a@b.c", "password": "secreto123"})
    assert r.status_code == 200 and "token" in r.json()

def test_sin_token_lectura_denegada(client):
    r = client.post("/api/readings", json={})
    assert r.status_code == 401

def test_lecturas_restantes(session, user):
    for _ in range(3):
        session.add(Reading(user_id=user.id, tipo="tarot", pregunta="x", resultado={}))
    session.commit()
    assert lecturas_restantes(user.id) == 0
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_auth.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar auth y límites**

Enfoque: hashing con `bcrypt`, JWT con expiración, dependencia FastAPI
`get_current_user`. `lecturas_restantes = LIMITE_FREEMIUM - count(Reading)`.
En el endpoint de lectura, si `lecturas_restantes <= 0` y no hay pago,
devolver la parte calculada pero omitir `interpretacion`.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_auth.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/app/services/limites.py backend/tests/test_auth.py
git commit -m "feat: autenticación JWT y límite freemium"
```

---

### Task 4: Pagos con Stripe

**Files:**
- Create: `backend/app/api/payments.py`
- Create: `backend/app/services/stripe_service.py`
- Create: `backend/tests/test_payments.py`

**Interfaces:**
- Consumes: modelo `Payment` (Task 1).
- Produces:
  - `crear_checkout(user_id: int) -> str` (URL de sesión Stripe).
  - `POST /api/payments/checkout`, `POST /api/payments/webhook`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_webhook_firma_invalida_rechazado(client):
    r = client.post(
        "/api/payments/webhook",
        data=b"{}",
        headers={"Stripe-Signature": "inválida"},
    )
    assert r.status_code == 400

def test_checkout_devuelve_url(monkeypatch, client, user_token):
    monkeypatch.setattr("app.services.stripe_service.crear_checkout", lambda uid: "https://checkout.stripe.com/x")
    r = client.post("/api/payments/checkout", headers=user_token)
    assert r.status_code == 200 and "url" in r.json()
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_payments.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar pagos**

Enfoque: `crear_checkout` crea una sesión de Stripe y devuelve su URL.
El webhook verifica la firma con `stripe.Webhook.construct_event` (clave del
endpoint desde env var) y marca el `Payment` como `pagado` al recibir
`checkout.session.completed`; ante firma inválida devuelve 400.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_payments.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/payments.py backend/app/services/stripe_service.py backend/tests/test_payments.py
git commit -m "feat: checkout y webhook de pagos Stripe"
```
