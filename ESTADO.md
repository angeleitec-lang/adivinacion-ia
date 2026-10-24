# ESTADO — T145: Aplicar el catálogo astrológico ampliado (opción A)

Rama: `track/t145-catalogo-astro-aplicar` · Worktree: `.worktrees/t145-catalogo-astro-aplicar`

## Tarea 1 — Copia de seguridad (hecha, 2026-10-24 08:12)

Destino: `/Users/angelgonzalez/fase0/_backup_t145_20261024_0812` (123 MB, `cp -R`, origen solo lectura).

| Origen (fase0) | Contenido copiado | Conteos |
|---|---|---|
| `kb_v2/` | 5 ficheros (tarot, baraja_espanola, astrologia, numerologia, diff_vs_kb_v1) | 5 ficheros |
| `consenso_kb/` | `consenso.jsonl` + informe + caché | 4.078 líneas |
| `cobertura_v3/` | `cobertura_total_v3.json/.md` | 7.455 celdas, 314 completas, 501 ignoradas |

## Tarea 2 — cobertura.py: +19 entidades astro (hecha)

- `entidades()` ahora incluye las 19 de `catalogo_astro_propuesta.entidades_propuestas()` (import perezoso dentro de la función para evitar ciclo: `catalogo_astro_propuesta` importa `cobertura` a nivel de módulo).
- Astro: 477 → 496 entidades; 5.247 → 5.456 celdas. Total catálogo: 7.664 celdas.
- Tests actualizados (cifras, ningún caso borrado): `test_recuento_por_familia` (496), `test_recuento_por_subtipo` (+casa 12, elemento 4, modalidad 3), `test_main_...` total_celdas 7664, `test_max_huecos_limita_listado` (7659), y en `test_catalogo_astro_propuesta.py` el caso de no-colisión pasa a `test_ids_propuestos_ya_integrados_en_catalogo` (los 19 ids son ahora subconjunto del catálogo).
- Suite corpus completa: 2.944 tests OK (skipped=1).

## Tarea 3 — kb/astrologia.json (hecha)

- Nueva sección top-level `entidades_ampliadas` con las 19 entradas mínimas deterministas: casa (número, ciclo angular/sucedente/cadente, signo natural), elemento y modalidad (sus signos canónicos). `significado: null` con marca `pendiente` explícita; sin significados inventados.
- Secciones antiguas (`signos`, `planetas`, `casas`, `aspectos`) intactas byte a byte: hash canónico `ecc474d8947e71e0a73c2db74ae3f326907fd8d4e1ca6eb71220028366fbe35f`.
- Tests nuevos en `tests/test_aplicar_catalogo_astro.py` (clase `TestKbAstroAmpliado`, 7 casos: hash de antiguas, 19 ids, casas deterministas, coherencia con `SIGNO_ELEMENTO`/`SIGNO_MODALIDAD`, ids presentes en catálogo, nombres no vacíos).

## Tarea 4 — aplicar_catalogo_astro.py (hecha)

- Módulo nuevo `finetune/corpus/aplicar_catalogo_astro.py`: genera 1.231 evidencias remapeadas (R1 casa 63 + R2 elemento 584 + R3 modalidad 584) en `fase0/catalogo_astro_aplicado/evidencias_catalogo_astro.jsonl` (determinista, sobrescribe → idempotente) y reconstruye la matriz v3 (fuentes T140 + fichero nuevo) en `catalogo_astro_aplicado/cobertura_v3_nueva/`.
- Rutas protegidas (nunca se escriben): `cobertura_v3`, `libros_limpio`, `evidencias_web`, `libros_comprados_astro`.
- Verificación real (24/10): antes 7.455 celdas / 314 completas / 501 ignoradas → después 7.664 / 314 / 501 (delta +209 celdas, +0 completas, esperado). Astrología: 5.456 celdas / 93 completas (sin cambio). Doble ejecución: sha256 idénticos (`shasum -c` OK) en evidencias y matriz.
- El `cobertura_v3` oficial NO se tocó.

## Tarea 5 — tests adversos + check.sh (hecha)

- Tests adversos en `tests/test_aplicar_catalogo_astro.py` (clases `TestGenerarEvidencias`, `TestProteccionRutasReales`): casa 13/0/-1, id inexistente, signo ambiguo, doble aplicación idempotente, evidencia sin faceta, escritura en rutas protegidas rechazada.
- `./finetune/scripts/check.sh` → **CHECK OK** (2.958 tests corpus + 23 scraper, skipped=1), ejecutado 2026-10-24 desde la raíz del worktree.

## Tarea 6 — docs/APLICAR_CATALOGO_ASTRO.md (hecha)

- Doc con qué cambió, cifras antes/después, ruta del backup y comando EXACTO para aplicar sobre el fase0 real (con copia previa `cobertura_v3_pre_t145_*`), para que lo ejecute la coordinadora tras el merge. No se ha ejecutado sobre el real.

## Cierre

Commits reales en la rama (`git log --oneline main..HEAD`, 2026-10-24):

```
f43ea86 T145: doc de aplicacion del catalogo astro ampliado (cifras y comando exacto)
a0b607e T145: aplicar_catalogo_astro.py — evidencias R1-R3 (1231) + reconstruccion v3 en catalogo_astro_aplicado/ (7664 celdas, 314 completas, idempotencia byte a byte verificada)
dc92774 T145: kb/astrologia.json +19 entradas en entidades_ampliadas (casas con ciclo y casa natural, elementos/modalidades con signos canonicos); secciones antiguas intactas (hash)
496c261 T145: catálogo astro ampliado en cobertura.entidades() (+19: 12 casas, 4 elementos, 3 modalidades; 496 ent, 5456 celdas astro; total 7664)
```

Cifras clave: +19 entidades astro (496 totales), 5.456 celdas astro, 7.664 celdas totales, 1.231 evidencias remapeadas, 314 completas sin cambio (+0), backup en `_backup_t145_20261024_0812`. Sin LLM, sin nodos, sin push.

TRACK COMPLETO
