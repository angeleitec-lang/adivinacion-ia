# Núcleo de cálculo determinista — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar en Python puro (sin LLM) el cálculo de numerología, la
mecánica de tirada de tarot y la carta astral real con Swiss Ephemeris, como
base determinista y testeable de toda la app.

**Architecture:** Módulos puros en `backend/app/core/` con entradas/salidas
tipadas y sin efectos secundarios, de modo que el RAG y el fine-tune consuman
siempre datos calculados de verdad (no alucinados). Todo es TDD con pytest.

**Tech Stack:** Python 3.11, pytest, `pyswisseph` (carta astral).

**Spec:** `docs/diseno-app-adivinacion.md` (secciones 2, 2.1, 5, 7, 9).

## Global Constraints

- Idioma del producto: español (textos y literales de cartas/signos en español).
- Python 3.11 (NO 3.13); dependencias en `backend/pyproject.toml`.
- Código, nombres de variables, commits y mensajes técnicos en el idioma que
  corresponda; respuestas de la app en español.
- La carta astral NO la calcula ningún LLM: solo `pyswisseph`.
- Todo cálculo determinista debe ser reproducible: funciones puras con seed
  explícito para el tarot.
- Licencia: `pyswisseph` envuelve Swiss Ephemeris (C, AGPL). Para monetizar,
  registrar la preocupación de licencia; si bloquea, alternativa es Skyfield +
  cálculo de casas propio. Dejar como nota en el README del módulo, no bloquea V1.

## Review Focus

1. Fechas antes de 1970 y zonas horarias con DST deben dar cúspides de casas
   coherentes (no excepción) — cubierto en Plan 1 Task 3.
2. Un nombre vacío o con caracteres no latinos en numerología no debe lanzar
   excepción — Task 1.
3. Tirada de tarot con `n` fuera de rango (0 o >78) debe rechazar con error
   claro, no devolver lista vacía silenciosa — Task 2.
4. Cartas repetidas en una misma tirada: no puede salir la misma carta dos
   veces sin reintroducción en el mazo — Task 2.
5. Aspecto entre dos planetas debe ser simétrico (A opuesto a B ⇒ B opuesto a
   A) — Task 3.
6. `cortar` rechaza `en` fuera de 1–77, conserva las 78 cartas únicas y, con la
   misma semilla y el mismo corte, reproduce cartas y orientación — Task 2.

---

### Task 1: Numerología

**Files:**
- Create: `backend/app/core/numerologia.py`
- Create: `backend/tests/test_numerologia.py`

**Interfaces:**
- Consumes: (nada — primer módulo)
- Produces:
  - `reducir_digitos(n: int) -> int` — suma dígitos hasta un dígito, salvo
    maestros 11, 22, 33.
  - `camino_de_vida(fecha: date) -> int`
  - `numero_destino(nombre: str) -> int` — tabla pitagórica (A=1..I=9, J=1..).
  - `lectura_numerologica(fecha: date, nombre: str) -> dict[str, int]` con
    claves `camino_de_vida`, `destino`, `alma` (vocales) y `personalidad`
    (consonantes).

- [ ] **Step 1: Escribir los tests que fallan**

```python
from datetime import date
from app.core.numerologia import (
    reducir_digitos, camino_de_vida, numero_destino, lectura_numerologica,
)

def test_reducir_digitos_respeta_maestros():
    assert reducir_digitos(11) == 11
    assert reducir_digitos(22) == 22
    assert reducir_digitos(29) == 11  # 2+9=11, maestro

def test_reducir_digitos_normal():
    assert reducir_digitos(12345) == 6  # 1+2+3+4+5=15 -> 1+5=6

def test_camino_de_vida():
    assert camino_de_vida(date(1990, 1, 1)) == 1990 + 1 + 1  # suma dígitos
    # 1+9+9+0+1+1 = 21 -> 3
    assert camino_de_vida(date(1990, 1, 1)) == 3

def test_numero_destino_es_ignora_acentos_y_mayusculas():
    assert numero_destino("Ana") == numero_destino("ana")

def test_numero_destino_vacio_o_no_letras():
    assert numero_destino("") == 0
    assert numero_destino("123") == 0

def test_lectura_numerologica_llaves():
    r = lectura_numerologica(date(1985, 7, 15), "Ana")
    assert set(r) == {"camino_de_vida", "destino", "alma", "personalidad"}
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_numerologia.py -v`
Expected: FAIL (module `app.core.numerologia` no existe).

- [ ] **Step 3: Implementar las funciones en `backend/app/core/numerologia.py`**

Enfoque: `reducir_digitos` suma los dígitos iterando; si el total intermedio es
11/22/33 lo devuelve. `numero_destino` mapea letras con `ord`, ignorando
acentos vía `unicodedata.normalize('NFD')` y descartando no-letras.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_numerologia.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/numerologia.py backend/tests/test_numerologia.py
git commit -m "feat: cálculo de numerología (camino de vida, destino, alma)"
```

---

### Task 2: Mecánica de tarot

**Files:**
- Create: `backend/app/core/tarot.py`
- Create: `backend/tests/test_tarot.py`

**Interfaces:**
- Consumes: (nada)
- Produces:
  - `@dataclass(frozen=True) Carta`: `nombre: str`, `palo: str | None`
    (None si arcano mayor), `numero: int`, `arcano_mayor: bool`,
    `invertida: bool`.
  - `MAZO: tuple[Carta, ...]` — 78 cartas (22 mayores + 56 menores).
  - `class Mazo` con `barajar(semilla: int | None = None) -> Mazo`,
    `cortar(en: int) -> Mazo`, `sacar(n: int) -> list[Carta]`.
    `cortar(en)` (requisito V1, spec §2.1): rota el mazo de modo que el orden
    resultante sea `cartas[en:] + cartas[:en]`; `en` debe estar entre 1 y 77
    (`ValueError` con mensaje claro fuera de rango). Es el corte que hace el
    usuario; la baraja previa la hace siempre el servidor con su propia semilla.
    La orientación de cada carta (`invertida`) la decide `barajar` con el mismo
    `random.Random(semilla)`, de modo que semilla + corte reproducen la tirada
    completa, incluida la orientación.
  - `tirada_tres_cartas(mazo: Mazo) -> dict[str, Carta]` claves
    `pasado`, `presente`, `futuro`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
import pytest
from app.core.tarot import MAZO, Mazo, tirada_tres_cartas

def test_mazo_tiene_78_cartas():
    assert len(MAZO) == 78

def test_22_arcanos_mayores():
    assert sum(1 for c in MAZO if c.arcano_mayor) == 22

def test_cartas_unicas():
    nombres = [c.nombre for c in MAZO]
    assert len(set(nombres)) == 78

def test_barajar_determinista_con_semilla():
    a = Mazo(MAZO).barajar(42)
    b = Mazo(MAZO).barajar(42)
    assert [c.nombre for c in a] == [c.nombre for c in b]

def test_sacar_no_repite():
    m = Mazo(MAZO).barajar(1)
    cartas = m.sacar(5)
    assert len({c.nombre for c in cartas}) == 5

def test_sacar_rango_invalido():
    with pytest.raises(ValueError):
        Mazo(MAZO).sacar(0)
    with pytest.raises(ValueError):
        Mazo(MAZO).sacar(79)

def test_tirada_tres_cartas_claves():
    r = tirada_tres_cartas(Mazo(MAZO).barajar(7))
    assert set(r) == {"pasado", "presente", "futuro"}

def test_cortar_rota_el_mazo():
    base = [c.nombre for c in Mazo(MAZO).barajar(3)]
    cortado = [c.nombre for c in Mazo(MAZO).barajar(3).cortar(10)]
    assert cortado == base[10:] + base[:10]

def test_cortar_conserva_78_cartas_unicas():
    cortado = Mazo(MAZO).barajar(3).cortar(40)
    assert len({c.nombre for c in cortado}) == 78

def test_cortar_rango_invalido():
    m = Mazo(MAZO).barajar(3)
    for en in (0, 78, -1):
        with pytest.raises(ValueError):
            m.cortar(en)

def test_barajar_y_cortar_reproducen_la_tirada_con_orientacion():
    def tirada(semilla, corte):
        return [(c.nombre, c.invertida)
                for c in Mazo(MAZO).barajar(semilla).cortar(corte).sacar(3)]
    assert tirada(42, 17) == tirada(42, 17)
    assert tirada(42, 17) != tirada(42, 18)
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_tarot.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `backend/app/core/tarot.py`**

Enfoque: `MAZO` se genera con los 22 arcanos mayores (El Loco..El Mundo) y los
56 menores (4 palos × 14: As..10, Sota, Caballo, Reina, Rey). `barajar` usa
`random.Random(semilla)` sobre una copia, y fija la orientación de cada carta con
ese mismo generador. `sacar` valida `1 <= n <= 78` y extrae del final. `cortar`
valida `1 <= en <= 77` y rota la lista: `cartas[en:] + cartas[:en]`.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_tarot.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/tarot.py backend/tests/test_tarot.py
git commit -m "feat: mazo de tarot y mecánica de tirada determinista"
```

---

### Task 3: Carta astral (Swiss Ephemeris)

**Files:**
- Create: `backend/app/core/astro.py`
- Create: `backend/tests/test_astro.py`

**Interfaces:**
- Consumes: (nada)
- Produces:
  - `@dataclass(frozen=True) PosicionPlaneta`: `planeta: str`, `signo: str`,
    `grado: float`, `casa: int`.
  - `@dataclass(frozen=True) CartaAstral`: `ascendente: str`,
    `medio_cielo: str`, `casas: list[float]` (12 cúspides),
    `planetas: list[PosicionPlaneta]`, `aspectos: list[tuple[str, str, str]]`.
  - `calcular_carta(fecha: datetime, lat: float, lon: float,
    tz: float) -> CartaAstral`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
from datetime import datetime
from app.core.astro import calcular_carta

def test_sol_en_capricornio_enero():
    carta = calcular_carta(datetime(1990, 1, 10, 12, 0), 40.4, -3.7, 1.0)
    sol = next(p for p in carta.planetas if p.planeta == "Sol")
    assert sol.signo == "Capricornio"

def test_sol_en_cancer_julio():
    carta = calcular_carta(datetime(1990, 7, 10, 12, 0), 40.4, -3.7, 1.0)
    sol = next(p for p in carta.planetas if p.planeta == "Sol")
    assert sol.signo == "Cancer"

def test_doce_casas():
    carta = calcular_carta(datetime(1990, 1, 10, 12, 0), 40.4, -3.7, 1.0)
    assert len(carta.casas) == 12

def test_ascendente_presente():
    carta = calcular_carta(datetime(1990, 1, 10, 12, 0), 40.4, -3.7, 1.0)
    assert carta.ascendente in SIGNOS

def test_aspectos_simetricos():
    carta = calcular_carta(datetime(1990, 1, 10, 12, 0), 40.4, -3.7, 1.0)
    for a, b, tipo in carta.aspectos:
        assert (b, a, tipo) in carta.aspectos
```

(Definir `SIGNOS` en el test como la lista de los 12 signos.)

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest backend/tests/test_astro.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementar `calcular_carta` en `backend/app/core/astro.py`**

Enfoque: usar `swe.calc_ut` con `FLG_SWIEPH` para cada planeta y
`swe.houses_ex` con casas Placidus (modo `b'P'`). Asignar signo por los 30°
de cada signo empezando en Aries. Calcular ascendente = cúspide 1 y MC =
cúspide 10. Aspectos por diferencia angular (orbe ±6°): 0° conjunción, 60°
sextil, 90° cuadratura, 120° trígono, 180° oposición. Registrar en el README
del módulo que se necesita `swe.set_ephe_path()` a los ficheros `.se1` o usar
Moshier embebido para los tests.

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest backend/tests/test_astro.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/astro.py backend/tests/test_astro.py
git commit -m "feat: cálculo de carta astral con Swiss Ephemeris"
```
