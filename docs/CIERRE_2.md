# CIERRE 2 — Fusión de fuentes nuevas del 23/10 (T140)

Fecha: 2026-10-23. Pista: T140 (rama `track/t140-cierre-2`).
Objetivo: fusionar las fuentes nuevas de las pistas T132/T133/T134 en evidencias,
consenso, kb_v2 y cobertura v3. **No** se regenera el dataset. **No** se reanudan
los generadores sintéticos suspendidos (PID 66101 nodo1, 66396 nodo2). Sin Mercury,
sin nodo1. Git solo local.

## Fuentes fusionadas

| Pista | Fichero de afirmaciones | Fuentes | Filas | Duplicados retirados |
|---|---|---|---|---|
| T132 | `txt_naipes_tarot/afirmaciones/afirmaciones_txt_naipes.jsonl` | `altaya_naipes`, `compendium_tarot_mexicanus` | 746 | 48 (por entidad+norm(texto)) |
| T133 | `txt_ocultismo_numerologia/afirmaciones/afirmaciones_txt_ocultismo.jsonl` | `numerologia_facil_galves` (moderna), `diccionario_ciencias_ocultas` (clásica, Papus) | 695 | 0 |
| T134 | `libros_comprados_baraja/afirmaciones/afirmaciones_baraja_validas.jsonl` | `libro_salas_baraja`, `libro_tiradas_baraja_espanola` | 320 | 24 (por entidad+norm(texto)) |

Las 6 afirmaciones marcadas como sospechosas EN/PT en T132 se **mantienen**: son
nombres propios dentro de frases españolas correctas (*The Book of the Law*, letra
hebrea *He*, *Hermetic Order of the Golden Dawn*), no prosa en inglés/portugués.

## Recuentos oficiales (antes → después)

| Fichero | Antes | Después | Delta |
|---|---|---|---|
| `libros/evidencias/evidencias.jsonl` | 16 545 | 17 278 | +733 (250 T132 + 163 T133 + 320 T134) |
| `afirmaciones_libros/afirmaciones_libros.jsonl` | 38 857 | 40 546 | +1 689 (698 + 695 + 296 dedup) |
| `consenso_kb/consenso.jsonl` | 4 021 | 4 078 | +57 netos (138 procesadas: 80 rehacer + 58 nuevas) |
| `kb_v2` — tarot | 78 | 78 | 0 |
| `kb_v2` — astrología | 424 | 424 | 0 |
| `kb_v2` — numerología | 69 | 71 | +2 |
| `kb_v2` — baraja española | 40 | 40 | 0 |

Copia de seguridad previa: `fase0/_backup_t140_20261023_1727` (consenso_kb,
kb_v2, libros/evidencias, afirmaciones_libros, cobertura_v3). Copia pre-extra del
consenso: `consenso_kb/consenso.jsonl.pre-extra-20261023_173056`.

## Cobertura v3 — antes / después por familia

Criterio de celda *completa*: ≥5 fuentes independientes, ≥1 clásica, ≥2 modernas,
≥1 en español, calidad ≥3.

| Familia | Baseline CIERRE_FINAL (v3) | Estado actual sin fuentes nuevas (dry-run 23/10) | Con fuentes nuevas (`--extra`) |
|---|---|---|---|
| Tarot | 173 | 172 | 172 |
| Baraja española | 39 | 39 | 39 |
| Astrología | 81 | 87 | **93** |
| Numerología | 6 | 9 | **10** |
| **Total** | **299** | **307** | **314** |

### Ganancias atribuibles a esta fusión (estado actual → con `--extra`)

- **Astrología: +6** celdas completas. Los libros de naipes (T132) y ocultismo
  (T133) aportan contenido astrológico (signos, planeta en signo/casa, aspectos)
  que redondea celdas que ya tenían clásica y les faltaban modernas.
- **Numerología: +1** celda completa (posición `mes_personal`/`destino` reforzada
  por `numerologia_facil_galves` + `diccionario_ciencias_ocultas`).
- Total: **+7** celdas completas.

### Pérdidas

- **Ninguna atribuible a esta fusión.** La diferencia Tarot 173→172 y el ascenso
  general 299→307 son *deriva* previa entre el CIERRE_FINAL y el estado actual de
  `libros_limpio`/claves de exclusión (otros tracks), no de T140. T140 no toca
  `libros_limpio`.

### Qué falta (por qué Tarot y Baraja no ganan)

T132 (`altaya_naipes`, `compendium_tarot_mexicanus`) y T134
(`libro_salas_baraja`, `libro_tiradas_baraja_espanola`) son fuentes **modernas**.
Las celdas de tarot/baraja que refuerzan ya carecen de una fuente **clásica**, así
que no alcanzan el criterio *≥1 clásica*. Para completar más celdas de tarot y
baraja hacen falta fuentes clásicas (p. ej. Papus/Cicero para tarot; un tratado
clásico de baraja española), no más fuentes modernas.

## fuera_alcance v2

`fase0/fuera_alcance_v2` (fuera_alcance_v2.jsonl + jobs_fuera_v2.db) **ya está
preparado por T136** (creado 23/10 12:51). T140 **no** lo regenera ni lo toca, en
coherencia con «no regenerar dataset». Se referencia como trabajo previo de T136.

## Nota sobre el paso 6 del script de cierre

`cierre_recopilacion.py --paso 6` pasa `--libros-limpio` como **directorio**
(`fase0/libros_limpio`) cuando `cobertura_v3.py` espera el **fichero**
`evidencias_limpias.jsonl` → `IsADirectoryError`. Bug preexistente en la rama.
Además, el paso 6 no incorpora las evidencias nuevas. La cobertura v3 de este
cierre se generó invocando `cobertura_v3.py` directamente con la ruta correcta del
fichero y `--extra` con los tres JSONL de evidencias nuevas (ver comando en
`ESTADO.md`). Queda pendiente (fuera de T140) arreglar el paso 6 del cierre.
