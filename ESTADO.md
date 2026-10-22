# ESTADO — T119 Evidencias y afirmaciones de libros de astrología comprados (Arroyo, Sasportas)

Rama: `track/t119-evidencias-libros-astro`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t119-evidencias-libros-astro`.

## Estado: TRACK COMPLETO

Dos libros comprados por el usuario procesados hacia el work-dir **nuevo**
`/Users/angelgonzalez/fase0/libros_comprados_astro/`, **sin** fusionar con
`libros/evidencias/evidencias.jsonl` ni tocar la matriz v3 real.

- **Arroyo** *Astrology, Psychology and the Four Elements* (1982), escaneo COMPLETO.
- **Sasportas** *The Twelve Houses* (1985), escaneo INCOMPLETO (falta final cap. 15
  y posterior a pág. 131, apéndices, glosario, bibliografía, índice).

Ficha de procedencia (`origen=comprado_por_usuario`,
`licencia_hint=libro con copyright, uso interno`) en
`fase0/libros_comprados_astro/knowledge/fuentes_libros_comprados.jsonl`.

## Alcance decidido (vinculante, usuario)

**Solo celdas existentes** en el catálogo: `signo`, `planeta_en_signo`,
`planeta_en_casa`, `aspecto`. **No** se crean `casa-N` / `elemento` / `modalidad`
ni se toca el catálogo compartido. En Sasportas, `planeta_en_casa` solo cuando el
capítulo de casa nombra explícitamente un planeta en esa casa. El hueco de
contenido sin celda destino se documenta en el `.md` (§5) con propuesta de pista
aparte.

## Resultados (números reales)

- **Juez** (nodo2, 2 workers, reanudable): 93 secciones juzgadas (90 + 3
  reaprovechadas), **325 evidencias**, 0 errores, 0 sin candidatos.
  - Por libro: Arroyo 187 / Sasportas 138.
  - Por tipo: `planeta_en_signo` 160, `signo` 106, `planeta_en_casa` 32, `aspecto` 27.
  - Celdas únicas: `planeta_en_signo` 44, `signo` 6, `aspecto` 14, `planeta_en_casa` 15.
  - Calidad: 321×4, 3×5, 1×3. Periodo `moderna`, idioma `en`.
- **Afirmaciones**: 325 evidencias procesadas → **723 afirmaciones**, 0 rechazos
  por copia literal, 0 errores.
  - Por tipo: `planeta_en_signo` 340, `signo` 244, `aspecto` 76, `planeta_en_casa` 63.
  - Por libro: Arroyo 432 / Sasportas 291.
  - Afirmaciones en **español** + cita verbatim en **inglés** (igual precedente T115;
    la evidencia lleva `idioma=en`). Ver caveat §6 del `.md` para reconciliar con T125.
- **Puerta anti-copia** (>25 palabras consecutivas) verificada operativa: copia
  literal de 30 palabras → rechazada; paráfrasis → aceptada.

## Delta de fusión (medido sobre copia, matriz real intacta)

`cobertura_v3.py` con/sin las 325 evidencias astro, en `fusion/base/` y
`fusion/con_astro/`:

| Tipo | Completas base → con astro | Celdas que ganan +1 fuente |
|---|---|---|
| `planeta_en_signo` | 30 → 33 (**+3 completas nuevas**) | 104 |
| `planeta_en_casa` | 0 → 0 | 31 |
| `aspecto` | 0 → 0 | 23 |
| `signo` | 57 → 57 | 30 |

Aportan densidad/diversidad y +3 completas en `planeta_en_signo`. No completan
casa/aspecto por sí solas (exigen ≥5 fuentes + clásica + 2 modernas + 1 es).

## Ficheros entregados (solo los míos)

- `finetune/corpus/libros_comprados_astro.py` (722 líneas) — detector EN→ES,
  segmentación por párrafos con `entidad_id` explícito, reusa juez +
  `afirmaciones_libros` + puerta anti-copia de nichols. LLM solo nodo2 (≤2 workers),
  work-dir nuevo, reanudable.
- `finetune/corpus/tests/test_libros_comprados_astro.py` — 25 tests, **25/25 OK**.
- `finetune/knowledge/libros_comprados_astro_evidencias.md` — ficha, cobertura,
  HUECO (casas/elementos/modalidades sin celda), caveats y comando de fusión con
  copia previa.

## Verificación

- Tests pista: `cd finetune/corpus && $PY -m unittest tests.test_libros_comprados_astro` → OK (25).
- Global: `./finetune/scripts/check.sh` → **CHECK OK** (2585 tests, sk=1), antes y
  después del merge de main.

## Commits (git log main..HEAD)

- `1a5427a` T119: evidencias y afirmaciones de libros astro comprados (Arroyo, Sasportas)
- `a012cd0` Merge main en track/t119 (trae auditoria_ronda7; ficheros disjuntos con T119)

HEAD = `a012cd0`. `git diff --stat main..HEAD` = solo los 3 ficheros de T119
(1110 inserciones). El merge de main se hizo para que el diff quede limpio (la
rama se basó en `3cfb196` y main había avanzado con `auditoria_ronda7`, ficheros
disjuntos; el merge no toca main).

## Limpieza

- El módulo se había escrito por error en el repo raíz
  (`/Users/angelgonzalez/adivinacion-ia/finetune/corpus/libros_comprados_astro.py`,
  untracked). **Eliminado** del raíz tras copiarlo al worktree. El raíz solo
  conserva `finetune/corpus/salud_datos.md` (ajeno, NO tocado).

## NUNCA

- NUNCA push (git solo local).
- NUNCA tocar `fase0/libros` (real) ni `fase0/libros_comprados_astro/work/` (temp T118).
- NUNCA nodo1 (10.0.0.3, reservado). LLM solo nodo2 (10.0.0.4).

## Pendiente

Ninguno para T119. TRACK COMPLETO. (La propuesta de añadir `casa-N`/`elemento`/
`modalidad` para aprovechar el núcleo de Sasportas queda como pista aparte, fuera
del alcance de esta.)
