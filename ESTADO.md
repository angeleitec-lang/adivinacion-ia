# ESTADO — T136 Regenerar fuera_alcance (v2)

Rama: `track/t136-regenerar-fuera-alcance`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t136-regenerar-fuera-alcance`.

TRACK COMPLETO

## Estado: TRACK COMPLETO

Generación ejecutada y verificada. Gate de t134 abierto (T134 integrada en
`main`, merge `35c5364`, T134 TRACK COMPLETO en `da3371d`). Informe completo en
`docs/REGENERAR_FUERA_ALCANCE.md`.

## Commits (hashes reales, `git log main..HEAD`)

- `8f51e71` T136: regenerar_fuera_alcance.py (gen nuevo v2, dry-run, reanudable, nodo2) + tests adversos
- `157d740` T136: docs/REGENERAR_FUERA_ALCANCE.md + ESTADO (preparado, gate t134)
- (este commit) T136: cierre — resultados de la generación (400/400) y ESTADO COMPLETO

## Qué se hizo

1. **Medición de la corrupción**: 400 jobs `fuera_alcance` originales
   (Mercury `mercury-3`); 398 filas corruptas en `fase1_v1d`
   (train 357 / val 20 / test 21). Patrón:
   `Pregunta del consultante: "<n> <arranque>:"` (pregunta real perdida, pero
   recuperable en `payload["tecnica"][1]` de los jobs de
   `/tmp/jobs_t113_final.db`). 5 ejemplos v1d: 36905, 37084, 37000, 37087,
   36894. El `corpus/jobs.db` maestro no tiene `fuera_alcance`.
2. **Copia de seguridad** de `corpus/jobs.db` en
   `/Users/angelgonzalez/fase0/copias/jobs_20261023_075506.db`
   (57.888.768 bytes) antes de tocar nada.
3. **Alcance**: el bloque corrupto es de **TÉCNICAS** fuera de alcance
   (`FUERA_ALCANCE_ENTRENAMIENTO`), no de seguridad. Las categorías de seguridad
   del `SIGUIENTE` (salud/legal/financiero/muerte/embarazo/violencia/menores)
   son la familia `etica`, **NO corrupta** → no se toca.
4. **Script** `finetune/corpus/regenerar_fuera_alcance.py`: solo importa
   `generate_tasks`/`fase1_prompts`/`ejecutor_fase1`/`llm_client` (no los
   modifica). Set nuevo en `/Users/angelgonzalez/fase0/fuera_alcance_v2/` (no
   toca v1d), esquema ShareGPT exacto de v1d. **Prohíbe nodo1** (`ValueError` si
   `10.0.0.3`). LLM solo nodo2, 1 worker, ≤1 req/s. Reanudable.
5. **Tests** `tests/test_regenerar_fuera_alcance.py`: 19 tests unittest, OK.
6. **Generación** (nodo2, 1 worker): primer paso 398 aceptados + 2 rechazados
   por contenido («vidas pasadas»/«vida anterior»); relanzamiento reanudable
   reintentó los 2 → **400 aceptados, 0 fallidos**.

## Resultados finales

```
aceptadas (fuera_alcance_v2.jsonl): 400
fallidas: 0
rechazos 1er paso (reintentados y aceptados): 2
  - Responde contenido de una técnica fuera de alcance (vidas pasadas): «vidas pasadas»
  - Responde contenido de una técnica fuera de alcance (vidas pasadas): «vida anterior»
barrido 400 filas: corruptas=0 sin_rechazo=0 sin_alternativa=0 truncadas=0
check.sh: CHECK OK
```

Verificación manual de 30 muestras: **30/30 correctas** (declinan la técnica
pedida, nombran tarot/baraja/astrología/numerología, no inventan, alternativa
concreta, español estándar con tildes, sin predicción literal). 6 banderas
`PREDICCION_VEDADA` de una regex de control resultaron falsos positivos («no doy
diagnósticos…» en negación). Detalle en `docs/REGENERAR_FUERA_ALCANCE.md`.

## Integración (pendiente, la hace la coordinadora)

`fuera_alcance_v2.jsonl` (400 filas, ShareGPT v1d) sustituye las 398 corruptas
al armar el dataset final (armadores/`merge_final` agrupan por `bloque`). No
reintroducir Mercury ni reanudar PIDs 66101/66396.

## Estado de procesos

Generación terminada (procesos PID 12385 y 67257 finalizados). Sin procesos LLM
de T136 vivos. No se reanudan los generadores suspendidos (PID 66101 nodo1,
66396 nodo2). Sin push (git solo local).
