# Fuentes nuevas T74 — baraja española, numerología y arreglo de rutas tarot

Descubrimiento dirigido (2ª tanda de recuperación, sin LLM) tras el agotamiento del pool ES de baraja y numerología observado en T64 (`/Users/angelgonzalez/fase0/web_recup2/informe.md`). Descubiertas vía búsqueda (DDG lite) + sondeo de `robots.txt`/sitemaps reales con `descubrir_fuentes.py`. Todas las fuentes son **páginas web públicas y legales**; no se ha saltado ningún bloqueo. `astro.com`, `nymero.org` y Reddit quedan excluidos por política.

Descubrimiento: `finetune/corpus/descubrir_fuentes.py` → plan `/Users/angelgonzalez/fase0/plan_t74.jsonl` (330 URLs).
Tanda real: `recuperacion_descarga.py` → `/Users/angelgonzalez/fase0/web_recup3/` (NUEVO, sin fusionar con `web/`).

## Validadas (aportan a baraja española y numerología, español primero)

| Dominio | Familia | Idioma | Tipo | Páginas útiles (descub. → ok tanda) | Calidad | Nota |
|---|---|---|---|---|---|---|
| thenumerologypower.com | numerología | ES | moderna (cubre tradición pitagórica/caldea) | 28 → 28 ok | 4 | Cubre camino de vida 11/22/33, «qué es la numerología caldea», pitagórica vs caldea. `robots` 200 |
| nohemia.com | numerología | ES | moderna (glosario estructurado) | 19 → 1 ok / 18 cortas | 2 | Glosario ES: camino-de-vida, año-personal, número-del-alma, personalidad, expresión, ciclo-de-nueve-años. **Entradas muy breves** (<1000 chars) → casi todas «cortas» |
| astralsagehub.com | numerología | ES | moderna | 31 → 31 ok | 3 | `/es-es/…numerolog`: carta-año, compatibilidad, desafío-N, expresión. `robots` 200 |
| numerologic.app | numerología | ES | moderna | 31 → 30 ok / 1 corta | 3 | `/es/`: life-path, soul-urge, expression, personality, mission, karmic. Slugs en inglés, contenido en español |
| annacasas.es | baraja española | ES | moderna | 42 → 40 ok | 3 | Fichas por naipe (`significado-…baraja-espanola`, `el-N-de-palo-en-una-lectura`, sota/caballo/rey/reyina). El patrón excluye el ruido «propiedades-mágicas». **Re-validada**: en T36 se descartó por «sin serie por naipe»; el patrón nuevo sí la encuentra |
| tarotamigo.com | baraja española | ES | moderna | 49 → 9 ok (≈40 ya en `web/`) | 3 | `/tarot/significado-cartas/baraja-espanola/` fichas por naipe (as/tres/siete… de copas/bastos/espadas/oros) |
| tarotgratuito.net | baraja española | ES | moderna | 49 → 1 ok (≈48 ya en `web/`) | 3 | `/tarot-baraja-espanola` + `/el-X-de-{oro,copas,espada,bastos}-tarot`. Ya muy cubierta por pistas previas |
| tiradadetarot.com | baraja española | ES | moderna | 5 → 5 ok | 4 | Página maestra de los 40 naipes + tiradas (`/cartas-espanolas`, `/tirada/cartas-espanolas`). Alto valor por página |

**Total nuevo en tanda:** baraja española **+55** páginas válidas, numerología **+90** válidas (+19 cortas). El pool ES no estaba del todo agotado: los dominios nuevos (annacasas, astralsagehub, numerologic, thenumerologypower) aportan lo que los índices clásicos de T25 no cubrían.

## Arreglo de rutas tarot (404 de T64 → 200)

Las rutas candidatas del plan viejo de T64 para `biddytarot.com` y `labyrinthos.co` devolvían 404 (33/33). Leyendo sus sitemaps reales se localizaron las fichas correctas. **Ambas fuentes son TAROT en inglés** (no baraja española); arreglan el 404 y aportan a la familia tarot.

| Dominio | Ruta vieja (404) | Ruta real (200) | Páginas (descub. → ok tanda) |
|---|---|---|---|
| biddytarot.com | `/tarot-card-meanings/minor-arcana/…` | `/blog/<x>-tarot-card-meanings/` (en `post-sitemap.xml`) | 16 → 12 ok / 4 cortas |
| labyrinthos.co | `/blogs/tarot-card-meanings-list/<slug-simple>` | `/blogs/tarot-card-meanings-list/<x>-meaning-tarot-card-meanings` y `/blogs/learn-tarot-with-labyrinthos-academy/the-<x>-tarot-card-meaning-<deck>` (en `sitemap_articles_1.xml`) | 60 → 20 ok |

Spot-check del arreglo (todas 200, contenido sustancial):
- `biddytarot.com/blog/the-tower-tarot-card-meanings/` → 200 (382 KB)
- `biddytarot.com/blog/fool-card-meaning/` → 200 (380 KB)
- `labyrinthos.co/blogs/tarot-card-meanings-list/ace-of-swords-meaning-tarot-card-meanings` → 200 (228 KB)
- `labyrinthos.co/blogs/learn-tarot-with-labyrinthos-academy/the-four-of-wands-tarot-card-meaning-luminous-spirit-tarot-deck` → 200 (211 KB)

En la tanda de 200, la familia tarot se alcanzó (32 ok) porque ~90 candidatas de baraja ya estaban en `web/` de pistas previas y liberaron cupo.

## Descartadas (con motivo)

| Dominio | Motivo |
|---|---|
| fijate.com | Solo 3 páginas de numerología; orientado a calculadora, escaso contenido interpretativo |
| centroserintegral.org | Solo 2 páginas, escaso |
| karmastro.com | Solo 5 páginas en español; el resto en francés |
| astrolium.com | Solo 3 páginas en español, escaso |
| es.scribd.com | Documentos subidos por usuarios; licencia dudosa |
| es.wikipedia.org | Enciclopédico, no interpretativo de cartomancia/numerología |
| astrofuturoonline.blogspot.com | Blogspot mixto, no aporta frente a las fuentes ya validadas |

## Licencia

Todas las fuentes: `licencia_hint = consultar` (convención del proyecto). Cada texto conserva su procedencia en el front-matter del markdown descargado; la revisión legal es una fase posterior (`finetune/corpus/license_filter.py`). Ninguna fuente es copia pirata: son páginas públicas de sitios editoriales con `robots.txt` que autoriza el rastreo de las rutas objetivo.

## Resultado de la tanda (autoritativo, `web_recup3/resumen.json`)

- Intentos: 200 → **177 ok**, 23 cortas. Omitidas ya en `web/`: 88.
- Por familia: baraja_espanola 55 ok · numerologia 90 ok (+19 cortas) · tarot 32 ok (+4 cortas).
- Por dominio (ok): annacasas.es 40 · astralsagehub.com 31 · numerologic.app 30 · thenumerologypower.com 28 · labyrinthos.co 20 · biddytarot.com 12 · tarotamigo.com 9 · tiradadetarot.com 5 · tarotgratuito.net 1 · nohemia.com 1.
