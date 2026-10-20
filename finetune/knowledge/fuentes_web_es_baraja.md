# Fuentes web en español — baraja española (T36)

Catálogo en `fuentes_web_es_baraja.jsonl` (12 fuentes) e índice de rastreo en `sitios_indice_es_baraja.json`. Verificadas el 2026-10-20 abriendo sitemaps reales y comprobando que la regex de cada sitio descubre páginas por naipe (pipeline `web_pipeline.py --dry-run`). Unión de los 12 sitios: **40/40 naipes** de la baraja española.

## Sitios (por prioridad)

| Sitio | Tipo | Páginas por naipe | Calidad | Nota |
|---|---|---|---|---|
| tiradadetarot.com | sitio | 40/40 | 4 | `/cartas-espanolas/<rango>-de-<palo>/`; 3 variantes por carta en sitemap (dedup por URL) |
| futooro.net | sitio | 40/40 | 4 | `/tarot/baraja-espanola/<rango>-de-<palo>/` exacto |
| www.tarotamigo.com | sitio | 40/40 | 4 | Páginas en hijo `sitemap-posttype-page.xml` |
| jardindeltarot.com | sitio | 40/40 | 4 | `/cartas-espanolas/` en `sitemap-0.xml` (no usar variante `/cartas/` de tarot) |
| oraculoseuropeos.blogspot.com | blog | 40/40 | 2 | Serie 2011/07; contenido original humano pero BREVE (~400-750 chars; solo 1/40 pasa umbral 1000). Prioridad baja |
| tarotdeabsalon.com | sitio | 39/40 | 4 | ~6000 caracteres por naipe; `as-copas` sin prefijo `de` |
| soyespiritual.top | sitio | 39/40 | 3 | `/significado-<rango>-de-<palo>-tarot-baraja-espanola/` |
| www.tarotsolaguilar.com | sitio | 38/40 | 3 | Post-sitemap1..5; faltan 2 naipes; en ejecucion real 15/38 paginas superan umbral 1000 chars |
| elreydecopas.com | sitio | 36/40 | 4 | Páginas largas (~13000 caracteres); mezcla rango en palabra y número |
| tarotdeana.es | sitio | 28/40 | 3 | Rangos 2-7 numéricos en la raíz; no usar variantes `-tarot/` |
| www.consultacartas.com | sitio | 38/40 | 3 | **NO rastreado**: robots.txt crawl-delay 10 s que el pipeline no soporta |
| tarotgratis.club | sitio | 40/40 | 3 | **NO rastreado**: robots.txt crawl-delay 20 s que el pipeline no soporta |

## Descartes

- `tarotrossana.com`: arcanos menores de tarot (56), no baraja española.
- `cartiluna.com`, `adivinos.com`: solo índice, sin páginas por naipe en sitemap.
- `barajadecartas.net`: 20 URLs informativas, sin serie por naipe.
- `tiradadecartasespañolasgratis.com`: solo 24/40 y dominio IDN con codificación corrupta.
- `vitaloracle.com` (1 página), `m-p-a.org` (0), `taroluz.com` (403 anti-bot), `annacasas.es`, `cursos.lluviabruja.com`, `astrofuturoonline.blogspot.com`: sin serie por naipe.
- Buscadores bloqueados durante el sondeo (DDG captcha, Brave/Brave-block, Mojeek/Yandex vacíos); el descubrimiento se hizo con sitemaps, inventario del repo y proxy de lectura.

## Licencia

Todas las fuentes: `licencia_hint = consultar` (por defecto del proyecto). Cada texto conserva su procedencia; la revisión legal es una fase posterior (`license_filter.py`).
