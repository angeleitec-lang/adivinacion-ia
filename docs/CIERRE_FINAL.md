# CIERRE FINAL DE LA RECOPILACIÓN (T121)

Fecha: 2026-10-23 (madrugada). Rama `track/t121-cierre-final`.

## Resumen ejecutivo

Se fusionaron los libros comprados (Pollack/Greer EN, Arroyo/Sasportas astro,
Nichols, Greene «Saturn») y los clásicos T92 (Tetrabiblos) en las rutas
oficiales de `fase0`, se aplicó el filtro de atribución T88/T90 y se
reconstruyeron `kb_v2` y `cobertura_v3`.

- **Consenso**: 3.688 → **4.021** celdas (+333: ganancias de libros nuevos,
  198 celdas nuevas T94, menos 341 afectadas por exclusión).
- **Cobertura v3**: 304 → **299** celdas completas. El descenso neto de 5 es
  el resultado de **+9 ganancias reales** frente a **−14 pérdidas que son una
  corrección de calidad** (contaminación cruzada de familias), no un fallo.

## Cobertura antes / después por familia

| Familia | Celdas | Baseline (21/10) | Ahora | Δ |
|---|---|---|---|---|
| Tarot | 936 | 172 | **173** | +1 |
| Baraja española | 480 | 36 | **39** | +3 |
| Astrología | 5247 | 85 | **81** | −4 |
| Numerología | 792 | 11 | **6** | −5 |
| **Total** | 7455 | **304** | **299** | **−5** |

Criterio `completa`: ≥5 fuentes independientes, ≥1 clásica, ≥2 modernas,
≥1 en español, calidad ≥3.

## Ganancias (+9, reales, de libros nuevos / T94)

- **Tarot**: `tarot-bastos-02 | correspondencias` (T115).
- **Naipes (T94)**: `naipe-bastos-01 | correspondencias`,
  `naipe-bastos-09 | consejo_practico`, `naipe-copas-01 | correspondencias`.
- **Astrología planeta_en_signo (libros nuevos)**: `jupiter|cancer`
  (espiritual), `jupiter|libra` (trabajo), `jupiter|virgo` (consejo_practico),
  `sol|aries` (simbolismo), `venus|leo` (ejemplo_de_uso).

## Pérdidas (−14, corrección de contaminación cruzada)

Las celdas perdidas tenían como **única fuente «clásica» libros de
tarot/naipes** que el baseline contaba erróneamente como clásicos
astrológicos/numerológicos. El filtro T88/T90 los retiró con motivo
`familia_ajena_naipes` (y 1 caso `signo_no_mencionado` de Gramaglia). Fuentes
retiradas de ejemplo: *Tarot De Los Bohemios*, Robert Wang
*The Qabalistic Tarot* (1983), Chic & Sandra Cicero *New Golden Dawn Ritual
Tarot Keys*.

- **Numerología (5)**: `22|destino` (significado_general, simbolismo),
  `2|destino` (significado_general), `3|destino` (significado_general,
  simbolismo).
- **Astrología (9)**: `signo` correspondencias/simbolismo de acuario,
  capricornio (×2), geminis, piscis (×2), sagitario, tauro; y
  `venus|aries|planeta_en_signo` (simbolismo).

Ejemplo (`acuario|signo|correspondencias`): baseline 18 fuentes / 1 «clásica»
→ ahora 19 fuentes / 0 clásicas. Los libros nuevos aportaron +1 moderna, pero
la única «clásica» era un libro de tarot y se retiró → falta 1 clásica → deja
de estar completa.

**Conclusión**: el baseline 304 estaba **inflado** por contaminación cruzada
(tarot contando como clásico de astro/numerología). El 299 es **más exacto**.
Coherente con la premisa del proyecto: *calidad por encima del plazo*.

## Qué falta (pendientes para el siguiente ciclo)

- **Baraja española — paráfrasis (T131)**: la paráfrasis anti-copia de las 320
  afirmaciones de Salas + Tiradas **no se ha ejecutado** (requiere Mercury /
  `INCEPTION_API_KEY`). No existe
  `fase0/libros_comprados_baraja/afirmaciones/afirmaciones_baraja_parafraseadas.jsonl`.
  Fusionar solo cuando exista y T131 esté COMPLETO.
- **Banzhaf (T130)**: bloqueado (epub parcial), ignorado.
- **Huecos restantes**: astrología (81/5247) y numerología (6/792) siguen con
  cobertura baja; requieren más fuentes clásicas en español.

## Rutas oficiales actualizadas (fase0)

- `libros/evidencias/evidencias.jsonl` = 16.545 (RAW: main 14.223 + EN 893 +
  astro 325 + nichols 430 + greene 617 + T92_sin_fp 57).
- `afirmaciones_libros/afirmaciones_libros.jsonl` = 38.857 (main 30.283 +
  EN 4.180 + astro 723 + nichols 1.103 + greene 2.568).
- `consenso_kb/consenso.jsonl` = 4.021 celdas.
- `kb_v2/`: tarot 78, astrología 424, numerología 69, baraja_española 40.
- `cobertura_v3/cobertura_total_v3.json`: 299 completas.

Copias de seguridad previas en
`/Users/angelgonzalez/fase0/_backup_t121_20261022_2249/`.

## Nota para la coordinadora

Revisar las 14 celdas perdidas: si se desea recuperar alguna, la vía correcta
es **aportar una fuente clásica astrológica/numerológica real** (no un libro de
tarot), no relajar el filtro. El filtro está haciendo su trabajo.
