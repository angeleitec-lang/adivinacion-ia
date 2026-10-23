# ESTADO — T137 Propuesta de catálogo astrológico ampliado (casa-N, elemento, modalidad)

Rama: `track/t137-catalogo-astro-casas`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t137-catalogo-astro-casas`.

## Estado: TRACK COMPLETO

Propuesta completa en `docs/PROPUESTA_CATALOGO_ASTRO.md`. Sin LLM. No se tocó `kb/*.json`, `cobertura_v3` ni ningún módulo existente. Copia de trabajo en `/Users/angelgonzalez/fase0/catalogo_astro_propuesta/`.

## Commits (hashes reales, `git log main..HEAD`)

- `4fda4af` T137: modulo de propuesta de catalogo astro ampliado (casa-N, elemento, modalidad) con remapeo determinista y tests
- `343a57e` T137: propuesta de catalogo astro ampliado (inventario, 19 entidades, impacto cobertura, coste, decision del usuario)

## Qué se hizo

1. **Inventario real**: catálogo astro 477 entidades / 5 247 celdas (signo 12, planeta_en_signo 120, planeta_en_casa 120, aspecto 225; 11 facetas). Cobertura v3 astro: 81 completas (signo 49/132, planeta_en_signo 32/1320, planeta_en_casa 0/1320, aspecto 0/2475). T119: 723 afirmaciones (Arroyo 432 / Sasportas 291): planeta_en_signo 340, signo 244, aspecto 76, planeta_en_casa 63 (casas 1,2,4,5,7,9,10,11,12; faltan 3,6,8).
2. **Propuesta (sin aplicar)**: 19 entidades nuevas — `casa1..casa12` (tipo casa), `fuego|elemento`..`agua|elemento`, `cardinal|modalidad`..`variable|modalidad`; mismas 11 facetas. Remapeo determinista estructural (no por texto, por falsos positivos): R1 casa desde planeta_en_casa (63), R2 elemento desde signo (584), R3 modalidad desde signo (584); aspecto 76 sin remapeo; 584+63+76=723 ✓.
3. **Script** `finetune/corpus/catalogo_astro_propuesta.py`: remapea y calcula cobertura hipotética en COPIA (`--work-dir /Users/angelgonzalez/fase0/catalogo_astro_propuesta`); protege rutas reales de fase0 (ValueError). Resultados: 209 celdas nuevas; con ≥1 fuente 88 (casa 23/132, elemento 35/44, modalidad 30/33); con ≥2 fuentes 28; completas 0 (falta clásica + español).
4. **Calculadora** (solo lectura, ejecutada): `calculos/astro.py::carta_natal` ya da casa 1-12 por planeta, cusps, `elemento_dominante`, `modalidad_dominante` → coste en calculos/ = CERO.
5. **Tests**: `finetune/corpus/tests/test_catalogo_astro_propuesta.py` — 34 OK. Adversos: casa 13/0/-1, ids inexistentes (quiron), signos ambiguos, claims basura, work-dir protegido, coherencia SIGNO_ELEMENTO vs KB, no colisión de ids.
6. **check.sh**: `CHECK OK` (corpus 2 748 tests OK + scraper OK).

## Pendiente de decisión del usuario (ver §7 de la doc)

- A: aceptar 19 entidades (recomendado). B: solo 12 casas. C: rechazar.
- La integración (tocar `cobertura.py` + `kb/astrologia.json` + absorción de evidencias) NO se hizo aquí por prohibición expresa de la pista; va en pista nueva si se acepta.

TRACK COMPLETO
