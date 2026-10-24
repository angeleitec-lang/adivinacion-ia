# Aplicar el catálogo astro ampliado (T145)

Fecha: 2026-10-24. Rama: `track/t145-catalogo-astro-aplicar`.
Base: propuesta en `docs/PROPUESTA_CATALOGO_ASTRO.md` y módulo
`finetune/corpus/catalogo_astro_propuesta.py` (ya en main).

## Qué cambia

1. **Catálogo** (`finetune/corpus/cobertura.py`): `entidades()` incorpora las
   19 entidades nuevas de la propuesta (12 casas, 4 elementos, 3 modalidades),
   reutilizando `catalogo_astro_propuesta.entidades_propuestas()` con import
   perezoso. Astrología: 477 → **496** entidades; celdas astro: 5.247 →
   **5.456**. Total catálogo: 7.455 → **7.664** celdas. Ninguna entidad
   antigua cambia.
2. **KB** (`finetune/corpus/kb/astrologia.json`): nueva sección top-level
   `entidades_ampliadas` con las 19 entradas mínimas deterministas (casa:
   número, ciclo angular/sucedente/cadente y signo natural; elemento/modalidad:
   sus signos canónicos). `significado: null` con marca `pendiente` explícita:
   sin significado propio hasta adquisición. Las secciones antiguas
   (`signos`, `planetas`, `casas`, `aspectos`) quedan intactas byte a byte
   (hash canónico `ecc474d8…fbe35f`).
3. **Evidencias remapeadas** (nuevo módulo
   `finetune/corpus/aplicar_catalogo_astro.py`): desde las afirmaciones de
   T119 se generan **1.231** evidencias R1-R3 en el formato que lee
   `cobertura_v3.py --extra`:
   - R1 casa desde `planeta_en_casa`: 63
   - R2 elemento desde signo: 584
   - R3 modalidad desde signo: 584
   Determinista e idempotente (sobrescribe, orden estable por
   entidad/faceta/fuente/regla).

## Cifras antes / después (verificado 2026-10-24)

| Métrica | Antes (v3 oficial) | Después (v3 nueva) | Delta |
|---|---|---|---|
| Celdas totales | 7.455 | 7.664 | +209 |
| Completas | 314 | 314 | 0 |
| Ignoradas | 501 | 501 | 0 |
| Celdas astrología | 5.247 | 5.456 | +209 |
| Completas astrología | 93 | 93 | 0 |

Las 209 celdas nuevas quedan **sin completar** (0 completas nuevas), como
anunciaba la propuesta: traen evidencia remapeada pero no alcanzan los umbrales
de fuentes. Ninguna celda antigua cambia de estado.

## Respaldo previo

Copia completa de `kb_v2`, `consenso_kb` y `cobertura_v3` en:
`/Users/angelgonzalez/fase0/_backup_t145_20261024_0812` (123 MB).
Conteos: kb_v2 5 ficheros; `consenso_kb/consenso.jsonl` 4.078 líneas;
`cobertura_v3` 7.455 celdas / 314 completas / 501 ignoradas.

## Estado actual en disco

Todo lo generado por T145 está **fuera** de las rutas reales:

- `/Users/angelgonzalez/fase0/catalogo_astro_aplicado/evidencias_catalogo_astro.jsonl` (1.231 líneas)
- `/Users/angelgonzalez/fase0/catalogo_astro_aplicado/cobertura_v3_nueva/` (matriz reconstruida con las fuentes de T140 + el fichero nuevo)

El `cobertura_v3` oficial **no se ha tocado**. El módulo
`aplicar_catalogo_astro.py` rechaza escribir dentro de `cobertura_v3`,
`libros_limpio`, `evidencias_web` y `libros_comprados_astro`.

## Comando EXACTO para aplicar sobre el fase0 real (lo ejecuta la coordinadora)

Solo tras fusionar `track/t145-catalogo-astro-aplicar` en `main`. Pasos:

```bash
# 1. Copia previa de seguridad del v3 real (además del backup de la tarea 1)
cp -R /Users/angelgonzalez/fase0/cobertura_v3 \
      /Users/angelgonzalez/fase0/cobertura_v3_pre_t145_$(date +%Y%m%d_%H%M)

# 2. Regenerar el v3 oficial con el catálogo ampliado (fuentes T140 + evidencias remapeadas)
cd /Users/angelgonzalez/adivinacion-ia
finetune/.venv/bin/python finetune/corpus/cobertura_v3.py \
  --libros limpio \
  --libros-limpio /Users/angelgonzalez/fase0/libros_limpio/evidencias_limpias.jsonl \
  --extra /Users/angelgonzalez/fase0/txt_naipes_tarot/evidencias/evidencias.jsonl \
          /Users/angelgonzalez/fase0/txt_ocultismo_numerologia/evidencias/evidencias.jsonl \
          /Users/angelgonzalez/fase0/libros_comprados_baraja/evidencias/evidencias_baraja.jsonl \
          /Users/angelgonzalez/fase0/catalogo_astro_aplicado/evidencias_catalogo_astro.jsonl
```

(Sin `--out-dir`: usa el default `/Users/angelgonzalez/fase0/cobertura_v3`.)

Comprobar tras ejecutar: `total_celdas` = 7.664, `completas` = 314,
`ignoradas` = 501; astrología 5.456 celdas / 93 completas. Si algo no cuadra
con lo verificado en `catalogo_astro_aplicado/cobertura_v3_nueva/`, restaurar
desde la copia `cobertura_v3_pre_t145_*`.

## Verificación de la pista

- `./finetune/scripts/check.sh` → `CHECK OK` (2.958 tests corpus + 23 scraper,
  skipped=1).
- Idempotencia: doble ejecución de `aplicar_catalogo_astro.py` produce
  idénticos sha256 en el JSONL de evidencias y en `cobertura_total_v3.json`.
- Tests adversos en `finetune/corpus/tests/test_aplicar_catalogo_astro.py`:
  casa 13/0/-1, id inexistente, signo ambiguo, doble aplicación, evidencia
  sin faceta, intento de escritura en rutas protegidas.
