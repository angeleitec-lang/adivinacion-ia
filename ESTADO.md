# ESTADO — T147 arreglos menores

Rama: `track/t147-arreglos-menores`. Fecha: 2026-10-24.

## Cambios

1. **Cierre paso 6 (cobertura v3)** — `cierre_recopilacion.py`: `--libros-limpio`
   ahora apunta al FICHERO `libros_limpio/evidencias_limpias.jsonl` (antes al
   directorio) y se propaga `--extra` (nuevo flag CLI `--extra`, ctx
   `extra_evidencias`) para las evidencias de txt_naipes_tarot,
   txt_ocultismo_numerologia, baraja y catálogo astro. Helper
   `_ruta_evidencias_limpias(ctx)`. `cobertura_v3.py` no se tocó.
   Commit: `dbe8dd1`
2. **nodo1 + nodo2 autorizados** — `regenerar_fuera_alcance.py`:
   `HOSTS_LOCALES_PERMITIDOS = ("10.0.0.3", "10.0.0.4")` y rechazo por
   hostname en `crear_cliente` (antes vetaba 10.0.0.3).
   `txt_ocultismo_numerologia.py`: `NODO1_ENDPOINT`,
   `ENDPOINTS_POR_DEFECTO = nodo1,nodo2`, nueva `validar_endpoints(csv)`
   llamada en `procesar_juez`/`procesar_afirmaciones`. Docstrings actualizados.
   Commit: `e25ebd4`
3. **Inventario de textos obsoletos** — `docs/ARREGLOS_T147.md`: grep
   verificado; en código no queda ninguna restricción activa. Docs históricos
   con «nodo1 reservado / solo nodo2» listados SIN tocar. Constantes
   vestigiales `NODO1_RESERVADO` (7 ficheros, cero usos rejectores) listadas
   para limpieza futura.
   Commit: `2f80a5a`

## Verificación

- Tests nuevos: `TestPaso6CoberturaFicheroYExtra` (6), `TestClienteNodos` (3),
  `TestEndpoints` (6) — todos en verde; ficheros de test completos OK
  (`test_cierre_recopilacion` 38, `test_regenerar_fuera_alcance` 28,
  `test_txt_ocultismo_numerologia` 18).
- `./finetune/scripts/check.sh` → **CHECK OK** (24/10/2026).

TRACK COMPLETO
