# Atribución de entidad en astrología y numerología (T88)

## El problema

En las celdas de **astrología** y **numerología** del corpus hay evidencias
mal atribuidas: la sección de origen habla de una entidad (un signo, un
planeta, una carta de naipes) **distinta** de la entidad a la que se asignó
la evidencia. Es la misma clase de contaminación que T53/T71 trató para el
tarot, pero en astro/numero. Ejemplos reales detectados:

- `acuario|signo` ← sección *"Venus en Leo…"* (`escuelamaia.com/venus-en-leo`).
- `cáncer|signo` ← páginas de **baraja española** (`astrologuias.com/baraja-espanola/4-de-oros`).
- `saturno|capricornio|planeta_en_signo` ← *"Saturno en Acuario…"* (`grancosmos.com/guia/saturno-en-acuario`).
- `luna|cáncer|planeta_en_signo` ← páginas de **Sol en Cáncer ascendente** (`astralsagehub.com/.../sol-cancer-ascendente`).
- `tauro|signo` ← *"Tres de Oros en la baraja española"* (`annacasas.es/tres-de-oros-baraja-espanola`).

## Qué hace el filtro

`finetune/corpus/filtro_atribucion.py` es **100 % determinista** (sin LLM
ni red) y **conservador**: prioriza la **precisión** sobre el *recall*. Solo
retira cuando el título de la sección o el *path* de la URL identifican de
forma inequívoca una entidad distinta de la asignada. Un título genérico que
no nombra ningún signo ni planeta **nunca** retira.

Solo actúa sobre evidencias cuya entidad pertenece a `astrologia` o
`numerologia`. Tarot y baraja no se tocan aquí (ya los trata T71).

### Reglas (en orden)

1. **`familia_ajena_naipes`** — el **título** o el **path** de la URL
   contienen un término de naipes: `tarot`, `arcano`, `naipe`, `baraja`, un
   palo en español (`espadas/copas/oros/bastos`) o inglés
   (`swords/cups/pentacles/coins/wands/staves`), o un patrón tipo
   `6 de espadas` / `Two of Cups`. Una página de naipes no puede sustentar
   una celda de astrología o numerología.
   - **Se mira el path, no el dominio.** Sitios cuyo dominio suena a naipes
     (p. ej. `tarot.ac`) albergan páginas de numerología válidas
     (`/es/numerology/numbers/13`) y **no** deben retirarse por el nombre
     del dominio. Este ajuste eliminó 45 falsos positivos.
2. **`signo_no_mencionado`** — la celda es `X|signo` o `P|S|planeta_en_signo`
   y el título/URL **nombran signos**, pero el signo de la celda no aparece.
3. **`planeta_no_mencionado`** — la celda es `planeta_en_signo`,
   `planeta_en_casa` o `aspecto`, y el título/URL **nombran planetas**, pero
   el planeta de la celda (en un aspecto, ninguno de los dos) no aparece.

Regla de oro: `Venus en Leo` para `leo|signo` se **CONSERVA** (Leo está
mencionado); para `acuario|signo` se **RETIRA** (se nombra Leo, no Acuario).

## Resultados sobre el corpus

| Métrica | Valor |
|---|---|
| Evidencias web totales | 23 118 |
| Evidencias libros totales | 14 223 |
| **Retiradas totales** | **2 188** (web 1 365 · libros 823) |
| · `familia_ajena_naipes` | 488 |
| · `signo_no_mencionado` | 1 080 |
| · `planeta_no_mencionado` | 620 |
| Claves a excluir del consenso | 1 372 |
| Afirmaciones afectadas | 11 895 |

### Efecto sobre la matriz de cobertura (celdas completas)

| Familia | Antes | Después | Δ |
|---|---|---|---|
| Astrología | 86 | 75 | −11 |
| Numerología | 11 | 6 | −5 |
| Tarot | 172 | 172 | 0 |
| Baraja española | 39 | 39 | 0 |
| **Total** | **308** | **292** | **−16** |

Se pierden 16 celdas "completas" en astro/numero: eran celdas que solo
estaban completas gracias a evidencia contaminada. Tarot y baraja quedan
intactos porque el filtro no los toca.

## Revisión manual (estimación de falsos positivos)

Se revisaron a mano 20 retiradas (muestra con semilla 42) y 20 conservadas
dudosas (astro/numero cuyo título nombra algún signo o planeta):

- **20 retiradas → 0 falsos positivos.** Todas son contaminación real:
  páginas de otro signo/planeta, páginas de naipes, o secciones de
  "Sol en X ascendente" asignadas a una celda de otro planeta.
- **20 conservadas dudosas → 0 falsos positivos** (ninguna conservada está
  claramente mal). Se observan **vacíos de *recall*** (contaminación que el
  filtro NO caza, por diseño conservador):
  - Secciones cuyo título nombra solo un **planeta** pero están asignadas a
    una celda de **signo** (p. ej. libro *"PLUTÓN SOBRE EL SOL"* en
    `libra|signo`): al no nombrar ningún signo, la regla 2 no dispara.
  - **Desfase de tipo de aspecto**: una sección *"Marte en trígono con
    Urano"* asignada a `marte|sextil|urano|aspecto` se conserva porque la
    regla 3 solo comprueba que los **extremos** estén nombrados, no el
    **tipo** de aspecto.

Estos vacíos se dejan a propósito: cerrarlos exigiría parsear tipos de
aspecto y subciclos en varios idiomas, con riesgo de introducir falsos
positivos. La prioridad es no retirar evidencia buena.

## Salidas

El filtro **nunca toca el original**. Escribe en `/Users/angelgonzalez/fase0/filtro_atribucion/`:

- `evidencias_retiradas.jsonl` — cada evidencia retirada con `motivo` y `familia`.
- `claves_excluir_consenso.jsonl` — claves `{hash_seccion, entidad_id, faceta, n_afirmaciones, motivo}` (solo claves con `n_afirmaciones > 0`), mismo formato que `libros_limpio/claves_excluir_consenso.jsonl`.
- `muestra_revision.jsonl` — 40 retiradas con semilla fija 42.
- `informe_filtro.json` — recuentos por motivo/familia, afirmaciones afectadas y cobertura antes/después.

## Comando para APLICAR (no ejecutar sin revisión humana)

La decisión de aplicar a producción la toma un humano revisando el informe.
El comando exacto para regenerar las salidas del filtro es:

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t88-atribucion-astro
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
    finetune/corpus/filtro_atribucion.py
```

Para aplicar la exclusión al consenso, añadir las claves de
`filtro_atribucion/claves_excluir_consenso.jsonl` a las ya existentes de
`libros_limpio/claves_excluir_consenso.jsonl` en la fase de fusión
**después** de la revisión. Este track **no** ejecuta esa fusión.

## Aplicación encadenada (T90)

La pista T90 (`track/t90-aplicar-atribucion`) encadena este filtro en el cierre
de la recopilación (`cierre_recopilacion.py`):

- **Paso 3 `filtro_atribucion`**: aplica el filtro a `evidencias_web` y
  `libros/evidencias` (ya limpias) con copia previa por origen
  (`pre-filtro-atrib`), reescritura atómica y verificación por **clave COMPLETA**
  `(hash_seccion, entidad_id, faceta)`. Idempotente (`ya_aplicada`) y con
  `--solo-verificar`. Escribe retiradas y conservadas **por origen**.
- **Paso 4 `consenso_exclusion`**: pasa **dos listas** de claves al consenso
  (T71 + T88). `consenso_kb.py --excluir-claves` es ahora repetible y
  `cargar_claves_exclusion` acepta una lista; las claves se unen por
  `(entidad_id, faceta)`, de modo que una celda afectada por ambas se rehace
  **una sola vez**.
- **Pasos 5-6**: `kb_v2` y `cobertura_v3` se regeneran después, en el orden
  correcto (`1 → 2 → 3 → 4 → 5 → 6 → 7`).

Comando de producción (revisar antes `--dry-run`; NO ejecutar con procesos en vivo):

```bash
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  /Users/angelgonzalez/adivinacion-ia/.worktrees/t90-aplicar-atribucion/finetune/corpus/cierre_recopilacion.py --todo
```

Solo el filtro: `--paso 3`. Detalle en `docs/CIERRE_RECOPILACION.md`.

## Tests

`finetune/corpus/tests/test_filtro_atribucion.py` (23 tests, `unittest`):

- `Venus en Leo` → `leo|signo` y `venus|leo|planeta_en_signo` **conservados**; `acuario|signo` **retirado**.
- Página de baraja en celda astro → `familia_ajena_naipes`.
- Título genérico sin signo/planeta → **no retira**.
- `numero_posicion` no afectado por la regla de signo; sí por la de naipes.
- Dominio `tarot.ac` con path de numerología → **conservado** (regla del path).
- Tarot y baraja fuera del objetivo → no se filtran.
