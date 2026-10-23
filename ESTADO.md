# ESTADO — T136 Regenerar fuera_alcance (v2)

Rama: `track/t136-regenerar-fuera-alcance`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t136-regenerar-fuera-alcance`.

## Estado: PREPARADO — GENERACIÓN BLOQUEADA por gate t134

Script + tests + dry-run listos y commiteados. **No se lanza `--run`** hasta que
`t134-parafrasis-baraja-local` tenga su propio `TRACK COMPLETO`.

Motivo del bloqueo: el `ESTADO.md` de
`.worktrees/t134-parafrasis-baraja-local/` contiene el reporte de **T121**
(header `# ESTADO — T121`), no de T134 (`grep T134` = 0 hits propios). La
condición del `SIGUIENTE` («lanzar cuando t134 tenga TRACK COMPLETO») **no se
cumple**. Regla «desconfiar de TRACK COMPLETO» aplicada.

## Commits (hashes reales, `git log main..HEAD`)

- `8f51e71` T136: regenerar_fuera_alcance.py (gen nuevo v2, dry-run, reanudable, nodo2) + tests adversos

(este commit añade `docs/REGENERAR_FUERA_ALCANCE.md` y el presente `ESTADO.md`)

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
   son la familia `etica`, **NO corrupta** → no se toca. Se regenera el bloque
   de técnicas, respetando «mira las categorías existentes».
4. **Script** `finetune/corpus/regenerar_fuera_alcance.py`: solo importa
   `generate_tasks`/`fase1_prompts`/`ejecutor_fase1`/`llm_client` (no los
   modifica). Genera set nuevo en `/Users/angelgonzalez/fase0/fuera_alcance_v2/`
   (no toca v1d), esquema ShareGPT exacto de v1d. Subcomandos
   `--dry-run`/`--prepare`/`--run`/`--report`. Valida cada job y **aborta** si
   hay prompt mutilado. **Prohíbe nodo1** (`ValueError` si `10.0.0.3`). LLM solo
   nodo2, 1 worker, ≤1 req/s. Reanudable (`pending→running→done/failed`).
5. **Tests** `tests/test_regenerar_fuera_alcance.py`: 19 tests unittest, todos
   OK. Casos adversos: prompt vacío/mutilado, sin técnica, sin encabezado, bloque
   inesperado, respuesta con diagnóstico/predicción de muerte (rechazada), sin
   rechazo, sin alternativa, buena aceptada, otra lengua (rechazada), truncada.
6. **check.sh = CHECK OK** (2733 tests, skipped=1).

## Cifras del dry-run (n=400)

```
jobs construidos: 400 (todos validados)
llamadas estimadas (con 30% reintentos): 520
tokens de prompt estimados (~4 char/token): 33210
presupuesto de salida (suma max_tokens): 614400
endpoint: http://10.0.0.4:8000/v1 (halogen-qwen3.8-flash-next, 1 worker)
```

Rechazos por motivo: **ninguno** (no se ha ejecutado LLM).

## Para continuar (cuando abra el gate de t134)

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t136-regenerar-fuera-alcance
$PY finetune/corpus/regenerar_fuera_alcance.py --prepare --n 400
$PY finetune/corpus/regenerar_fuera_alcance.py --run --n 400 --workers 1
$PY finetune/corpus/regenerar_fuera_alcance.py --report
```

Después: verificar **30 muestras a mano** y anotarlas aquí; integrar
`fuera_alcance_v2.jsonl` sustituyendo las 398 corruptas (armadores agrupan por
`bloque`). Ver `docs/REGENERAR_FUERA_ALCANCE.md`.

## Estado de procesos

Sin procesos LLM de T136 en ejecución. No se reanudan los generadores
suspendidos (PID 66101 nodo1, 66396 nodo2). Sin push (git solo local).
