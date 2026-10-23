# ESTADO — T121 Cierre final de la recopilación

Rama: `track/t121-cierre-final`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t121-cierre-final`.

## Estado: TRACK COMPLETO

Informe completo en `docs/CIERRE_FINAL.md`.

## Commits (hashes reales, `git log main..HEAD`)

- `65063cc` T121: desbloquear etapas LLM de Greene (dispatch --juez/--afirmaciones, patrón astro)
- `98e0deb` T121: actualizar test de Greene al dispatch LLM (bloquea_llm -> despacha_etapas_llm)
- (pendiente en este commit) T121: docs/CIERRE_FINAL.md + ESTADO de cierre

## Qué se hizo

1. **Copias de seguridad** en `/Users/angelgonzalez/fase0/_backup_t121_20261022_2249/`
   (consenso_kb, kb_v2, libros_evidencias, cobertura_v3, afirmaciones_libros).
2. **AJUSTE 2 aplicado**: la paráfrasis de baraja NO es de T121 (es de T131).
   No se usó `afirmaciones_baraja.jsonl` (cita recortada).
3. **Revisión manual** de las 40 líneas de `filtro_atribucion/muestra_revision.jsonl`:
   39/40 correctas, 1 dudosa → aprobadas las 40 (diseño por sección). Sin exclusiones extra.
4. **Greene (T130)**: desbloqueado el guardón, dispatch `--juez`/`--afirmaciones`
   patrón astro. Juez COMPLETO (208 secciones, 617 evidencias, 0 errores).
   Afirmaciones COMPLETO (617 pares, 2.568 afirmaciones). Test actualizado 33/33 OK.
5. **Staging** `fase0/t121_staging/`: fusión EN+astro+nichols+T92+Greene;
   pasos 2-3 del cierre (limpieza 16.328 conservadas / 217 retiradas;
   filtro atribución 563 claves).
6. **Consenso**: pass final 3 workers → 4.021 celdas (antes 3.688).
7. **Paso 4 exclusión**: claves CORRIENTES de staging (limpieza 0 + filtro 563),
   NO las oficiales obsoletas (1.098/1.372). 341 celdas afectadas, 2.265
   afirmaciones excluidas.
8. **Pasos 5-6**: kb_v2 (tarot 78, astro 424, numero 69, baraja 40) y
   cobertura_v3 (299 completas).
9. **Promoción a rutas oficiales** (fase0): evidencias 16.545 RAW,
   afirmaciones 38.857, consenso 4.021, kb_v2, cobertura_v3.
10. **check.sh = CHECK OK**.

## Cobertura: 304 → 299

+9 ganancias reales (tarot bastos-02; 3 naipes T94; 5 astro planeta_en_signo
de libros nuevos) vs −14 pérdidas que son **corrección de contaminación
cruzada** (libros de tarot/naipes que el baseline contaba como «clásicos» de
astro/numerología, retirados por `familia_ajena_naipes`). Aceptado 299 como
más exacto (calidad > plazo). Detalle en `docs/CIERRE_FINAL.md`.

## PENDIENTE para continuación (no es de T121)

- **Baraja paráfrasis (T131)**: NO ejecutada (requiere Mercury /
  `INCEPTION_API_KEY`). No existe
  `fase0/libros_comprados_baraja/afirmaciones/afirmaciones_baraja_parafraseadas.jsonl`.
  Cuando T131 esté COMPLETO, fusionar ese fichero al consenso con:
  ```bash
  PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
  B=/Users/angelgonzalez/fase0
  cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t121-cierre-final/finetune/corpus
  $PY consenso_kb.py --web-afirmaciones $B/afirmaciones_full/afirmaciones.jsonl \
    --libros-afirmaciones $B/afirmaciones_libros/afirmaciones_libros.jsonl \
    --extra-afirmaciones $B/libros_comprados_baraja/afirmaciones/afirmaciones_baraja_parafraseadas.jsonl \
    --rehacer-celdas-con-extra --out-dir $B/consenso_kb --workers 3
  ```
  y regenerar kb_v2 + cobertura_v3.
- **Banzhaf**: bloqueado (epub parcial), ignorado.

## Estado de procesos

Sin escritores vivos (nodo2 libre). Ningún proceso de T121 en ejecución.
