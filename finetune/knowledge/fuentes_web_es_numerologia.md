# Fuentes web en español — numerología (T36)

Catálogo en `fuentes_web_es_numerologia.jsonl` (12 fuentes) e índice de rastreo en `sitios_indice_es_numerologia.json`. Verificadas el 2026-10-20 abriendo sitemaps reales y comprobando que la regex de cada sitio descubre páginas por número (pipeline `web_pipeline.py --dry-run`). Unión de los 12 sitios: **12/12 números** de la matriz (1-9, 11, 22, 33).

## Sitios (por prioridad)

| Sitio | Tipo | Números | Calidad | Nota |
|---|---|---|---|---|
| www.yourastrallife.com | sitio | 12/12 | 4 | 216 págs numeradas en `/es/numerologia/guia/<tipo>-<N>`: camino de vida, alma, personalidad, expresión, año/mes personal, madurez, ciclos… Multi-posición de la matriz |
| www.cartaceleste.com | sitio | 12/12 | 4 | `/numerologia/camino-de-vida/<N>/` |
| mybornday.com | sitio | 12/12 | 4 | `/es/numerologia/camino-<N>/` |
| datemyst.com | sitio | 12/12 | 4 | `/es/conocimiento/numerologia/numerologia-<N>-significado…` |
| freenumerology.net | sitio | 12/12 | 4 | `/es/guides/life-path-<N>` (12) + `personal-year-<N>` (9) |
| www.aurimundi.com | sitio | 12/12 | 4 | `camino-de-vida-<N>` (1-9) + `numero-maestro-<N>` (11/22/33) |
| www.velotit.com | blog | 12/12 | 3 | `/es/blog/numero-<N>-significado…` y `numero-maestro-…` |
| numerologia-cotidiana.com | blog | 11/12 | 3 | Series `significado-<N>-numeropersonal` (11) y `-numeropersonalidad` (11) |
| www.numerovya.com | sitio | 11/12 | 3 | `/es/camino-de-vida-<N>-numerologia` (falta 33) |
| www.mon-oracle.org | sitio | 9/12 | 3 | Solo camino de vida; maestros en página conjunta |
| www.skywhisper.app | sitio | 9/12 | 3 | `/es/numerology/life-path/<N>` (sin maestros) |
| numerologos.com | blog | 9/12 | 3 | `numero-de-vida-<N>` (1-9); maestros en `/numeros-maestros/` |

## Descartes

- `aurakosmos.com`: robots.txt DISALLOW `/es/numerologia/`.
- `worldnumerology.com`, `numerologist.com`, `lifepathcalculator.org`: sin contenido en español o solo calculadoras.
- `zaruvia.com`, `astrologynumerology.org`: solo *angel numbers* (111/222), no la matriz 1-9/11/22/33.
- `asterlogia.com`, `oracul.fyi`, `soykairos.com`, `tutarot.club`, `centroserintegral.org`, `astroak.com`: artículos sueltos sin serie por número.
- `numastra.com`: solo life-path 1-5 (débil).
- Granjas de contenido IA con sufijos aleatorios y duplicados (`esotericos.es`, `tucartanumerologica.com`, `auroratikun.com`, `pregunting.es`, `numerologia-guia.com`, `astrologia-guia-es.com`): excluidas por calidad.
- `mis-numeros.es`: robots Disallow `/`. `numerolo.com`: checkpoint anti-bot.

## Licencia

Todas las fuentes: `licencia_hint = consultar` (por defecto del proyecto). Cada texto conserva su procedencia; la revisión legal es una fase posterior (`license_filter.py`).
