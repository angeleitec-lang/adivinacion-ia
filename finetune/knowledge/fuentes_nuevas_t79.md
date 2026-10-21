# Fuentes nuevas T79 — ronda 3: agotado de validados T74 + dominios nuevos (astrología ES, baraja, numerología)

Continuación de T74 (2026-10-21). Descubrimiento estructural puro (sitemaps + regex + `robots.txt`, sin LLM) con `descubrir_fuentes.py --conjunto t79`, que ahora acepta `--excluir-manifest` para no re-proponer URLs ya descargadas en `web/`, `web_recup2/` y `web_recup3/` (manifest acumulado: 4 320 URLs). Tanda real con `recuperacion_descarga.py` hacia `/Users/angelgonzalez/fase0/web_recup4/` (NUEVO, sin fusionar). `astro.com`, `nymero.org` y Reddit excluidos por política; ningún bloqueo saltado.

## Plan y tandas

- Plan completo: `/Users/angelgonzalez/fase0/plan_t79_completo.jsonl` (921 candidatas, tope 150/dom, excluidas las ya descargadas).
- Tanda A (dominios validados T74): `plan_t79A.jsonl` → 250 intentos, **250 ok**.
- Tanda B (dominios nuevos): `plan_t79B.jsonl` → 150 intentos, **147 ok / 3 cortas** (48 omitidas por hash/descargadas previas).
- **Total tanda: 400 intentos → 397 ok, 3 cortas.**

## Validadas (evidencia: `web_recup4/manifest.jsonl`)

| Dominio | Familia | Idioma | Páginas tanda (ok) | Med chars | Calidad | Nota |
|---|---|---|---|---|---|---|
| astralsagehub.com | astrología | ES | 150 → 150 | 37 015 | 4 | Secciones `/es-es/` nuevas: sol-ascendente (145 combinaciones sol+ascendente), casas-astrologicas (12), aspectos (11), planetas (10), signos (12). Contenido largo y estructurado. Antes solo se usó su sección de numerología |
| campus-astrologia.es | astrología | ES | 40 → 40 | 7 847 | 2-3 | **Ficha por combinación** (lo que pedía la pista): aspectos (`luna-oposicion-neptuno`), sinastrias, puntos-en-casa, nodos, Quirón — buenas (≥3). PERO las fichas `planeta-en-signo-en-casa-N` son plantilla auto-generada repetitiva (densidad «puede» 12/1k) — calidad 2. Quedan 3 136 candidatas más sin bajar |
| numerologist.com | numerología | EN | 40 → 40 | 12 255 | 4 | Números maestros 11/22/33, caldea, life-path (109 págs), soul, birthday, personality. Editorial limpio, bien estructurado. Quedan ~1 650 candidatas |
| elreydecopas.com | baraja española | ES | 40 → 40 | 7 292 | 3 | Curso online de baraja española (114 págs), cápsulas (23) y fichas por naipe (`/baraja-espanola/as-de-copas`). Voz de cartomante experimentado |
| annacasas.es | baraja española | ES | 29 → 29 | 8 715 | 3 | Resto útil del sitemap tras T74: fichas `X-de-palo-baraja-espanola`, `el-N-de-palo-en-una-lectura`, figuras `en-el-tarot`, tiradas baraja. Patrón T79 excluye ruido («sonar con monedas de oro», «colgantes de oro», «caballo de Troya») |
| biddytarot.com | tarot | EN | 71 → 71 | 5 209 | 3 | `card-sitemap.xml`: 78 fichas canónicas `/tarot-card-meanings/<arcano>/<carta>/` (en T74 solo se usó el blog). Fichas breves pero limpias por carta |
| astro-cours.com | astrología | ES | 30 → 27 | 16 557 | 2-3 | `/es/planetas` (11), `/es/casas` (13), `/es/signos` (13). 3 páginas de casas vacías (casa-4/5/6 → «cortas»). Aceptable como relleno, no como fuente principal |

Aporte por familia en la tanda: astrología **+217** · baraja española **+69** · numerología **+40** · tarot **+71**.

## Sin bajar por tope de tanda (quedan candidatas útiles para una ronda futura)

| Dominio | Candidatas restantes | Motivo |
|---|---|---|
| labyrinthos.co | ~150 | Tope `--max-total 250` de la Tanda A agotado por astrología/tarot previo. Fichas EN de calidad ya probada en T74 |
| tiradadetarot.com | 22 | Idem. Tiradas y lectura de vida en español |
| campus-astrologia.es | ~3 136 | Tope 40/dom (nuevo). Priorizar aspectos/sinastrias/nodos; evitar las fichas «en-casa» plantilla |
| numerologist.com | ~1 650 | Tope 40/dom (nuevo) |
| elreydecopas.com | ~110 | Tope 40/dom (nuevo) |

## Descartados (con motivo)

| Dominio | Motivo |
|---|---|
| bdh.bne.es | Bloqueo anti-bot detectado en el sondeo. No se salta bloqueos (política del proyecto) |
| es.wikisource.org | Búsqueda «cartomancia»: solo 12 menciones literarias (Galdós, Palacio Valdés). Sin manuales didácticos en dominio público |
| astrosofia.com | `sitemap.xml` con 1 sola `<loc>`; sin cuerpo rastreable |
| tiradadecartas.com.ar | 6 987 URLs templadas repetitivas (≈51 por categoría idénticas); baja calidad |
| es.scribd.com / slideshare | Subidas de usuarios, licencia dudosa |
| numerologic.app | Sin contenido nuevo: las 64 URLs del sitemap ya están cubiertas por T74 |
| thenumerologypower.com | Posts de numerología agotados en T74 (28); `page-sitemap` solo 3 páginas institucionales |

## Clásicos en dominio público

No se han encontrado fuentes PD nuevas más allá de lo ya inventariado en T55 (`finetune/knowledge/fuentes_clasicas_pd.jsonl`: 24 de archive.org, 3 de Gutenberg, 1 de Wikisource). BDH (BNE) no es accesible sin saltar bloqueos; Wikisource en español no tiene manuales de cartomancia. Queda como pendiente futuro: localizar manuales antiguos de baraja española en repositorios PD verificables (HathiTrust, Internet Archive con search por título).

## Licencia

Convención del proyecto: `licencia_hint = consultar`. Cada texto conserva su procedencia en el front-matter del markdown descargado; revisión legal posterior (`finetune/corpus/license_filter.py`). Todos los dominios rastreados tienen `robots.txt` que autoriza las rutas objetivo (verificado en el sondeo previo).

## Herramientas (esta pista)

- `finetune/corpus/descubrir_fuentes.py`: nuevo conjunto `FUENTES_T79` (10 fuentes), `--conjunto {t74,t79}`, `--excluir-manifest` (repetible), `norm_url`, `cargar_exclusiones_de_manifest`, `prefijo` en `escribir_plan`. Retro-compatible con T74.
- Planes: `plan_t79A.jsonl` (436 candidatas T74-dom) / `plan_t79B.jsonl` (485 candidatas nuevos).
- Manifest acumulado usado: `/Users/angelgonzalez/fase0/manifest_acumulado_t79.jsonl` (4 320 URLs) y `manifest_acumulado_t79b.jsonl` (para la Tanda B).
