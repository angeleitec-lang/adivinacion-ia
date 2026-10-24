# ARREGLOS_T147 — Arreglos menores (nodo1/nodo2 y cierre de recopilación)

Fecha: 2026-10-24. Rama: `track/t147-arreglos-menores`.

## 1. Cierre de recopilación: paso 6 (cobertura v3)

**Defecto**: `cierre_recopilacion.py` paso 6 pasaba `--libros-limpio` apuntando
al DIRECTORIO `libros_limpio`, pero `cobertura_v3.py` espera el FICHERO
`evidencias_limpias.jsonl` dentro de él. Además no propagaba `--extra`
(evidencias de `txt_naipes_tarot`, `txt_ocultismo_numerologia`, baraja y
catálogo astro), que el comando de referencia de `docs/APLICAR_CATALOGO_ASTRO.md`
sí incluye.

**Arreglo** (commit T147-1):
- Helper `_ruta_evidencias_limpias(ctx)`: usa `ctx["evidencias_limpias"]` si se
  indica, si no `libros_limpio/evidencias_limpias.jsonl`.
- `paso6_cobertura_v3` pasa esa ruta a `--libros-limpio` y, si hay
  `extra_evidencias`, añade `--extra <ruta> ...`.
- `construir_ctx` puebla `extra_evidencias` desde el nuevo flag CLI
  `--extra` (`nargs="*"`); `_validar_entradas_paso` y `_descripcion_paso`
  del paso 6 validan/describen el fichero y los extras.
- `cobertura_v3.py` no se tocó. Nota: su `--excluir-claves` es de valor único
  (el último gana); queda fuera de este ámbito.

## 2. nodo1 y nodo2 autorizados para generación

**Defecto**: `regenerar_fuera_alcance.py` rechazaba `10.0.0.3` («esta pista no
usa nodo1») y `txt_ocultismo_numerologia.py` estaba fijado a «solo nodo2»,
cuando el usuario autorizó nodo1 el 23/10.

**Arreglo** (commit T147-2):
- `regenerar_fuera_alcance.py`: constante `HOSTS_LOCALES_PERMITIDOS =
  ("10.0.0.3", "10.0.0.4")`; `crear_cliente` rechaza por hostname
  (`urlparse`) cualquier host ajeno en lugar de vetar solo nodo1. Docstring y
  ayudas de CLI actualizados (nunca Mercury).
- `txt_ocultismo_numerologia.py`: `NODO1_ENDPOINT` y
  `ENDPOINTS_POR_DEFECTO = nodo1,nodo2` (espejo de T143); CLI `--endpoints` y
  `medir_dry` usan el nuevo default. Nueva `validar_endpoints(csv)` que rechaza
  hosts fuera de `baraja.HOSTS_LOCALES_PERMITIDOS`, llamada en
  `procesar_juez`/`procesar_afirmaciones` cuando no se pasa cliente.

## 3. Textos obsoletos «nodo1 reservado / solo nodo2» (solo inventario)

Verificado con `grep -rnE "reservad.*nodo1|nodo1.*reservad|solo nodo2" finetune docs`.
En **código** ya no queda ninguna restricción activa:
- `finetune/corpus/linea_base.py:20` — ya actualizado («nodo1 ya no está
  reservado, autorizado 23/10»). OK.
- `regenerar_fuera_alcance.py` y `txt_ocultismo_numerologia.py` — arreglados
  arriba.
- `regenerar_etica_espanola1.py:981` — ya permitía ambos hosts.

**Docs históricos NO tocados** (registro de lo que era cierto en su momento;
editarlos borraría el registro):
- `finetune/knowledge/libros_comprados.md:32`
- `finetune/knowledge/libros_comprados_baraja.md:155`
- `finetune/knowledge/txt_naipes_tarot.md:87`
- `finetune/knowledge/traduccion_afirmaciones.md:24`
- `finetune/knowledge/clasicos_t92.md:34`
- `finetune/knowledge/libros_comprados_astro_evidencias.md:48`
- `finetune/knowledge/libros_comprados_greene.md:89`
- `docs/GENERACION_FASE1.md:106`
- `docs/REGENERAR_FUERA_ALCANCE.md:88`
- `docs/HOJA_DE_RUTA.md:32,49,78`
- `docs/PLAN_DIA_2026-10-22.md:3`

**Constantes vestigiales** (definidas, cero usos rejectores; fuera del ámbito de
esta pista, se listan para limpieza futura):
- `txt_naipes_tarot.py:53`, `libros_comprados_baraja.py:73`,
  `libro_comprado_nichols.py:56`, `libro_comprado_greene.py:68`,
  `clasicos_pd_a_evidencias.py:41`, `libros_comprados_en.py:56`,
  `libros_comprados_astro.py:49` — todas `NODO1_RESERVADO = "10.0.0.3"`.
