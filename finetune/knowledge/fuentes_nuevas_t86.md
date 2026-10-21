# Fuentes nuevas T86 — ronda 4: astrología (ES primero, EN después)

Pista: continuación de T79 (ronda 3). Objetivo: reforzar la familia **astrología**
(la más floja del corpus: 79/5247 celdas completas en la matriz v2) con
dominios **nuevos** que publiquen **ficha por combinación** (planeta en signo,
planeta en casa, aspectos, nodos lunares, Quirón, ascendente), en español primero
y en inglés después, más el inventario de **clásicos en dominio público** que
otra pista procesará.

- Fecha de verificación: 2026-10-21.
- Rama: `track/t86-fuentes-ronda3` → `track/t86-fuentes-ronda4`.
- Salida de descargas: `/Users/angelgonzalez/fase0/web_recup5/` (sin fusionar).
- Herramientas: `finetune/corpus/descubrir_fuentes.py` (conjunto `t86`) +
  `finetune/corpus/recuperacion_descarga.py`.
- Calidad estimada por muestra trafilatura (chars de texto extraído), umbral ≥3
  (≈ ≥3.000 chars sustanciosos, sin plantilla hueca).
- Reglas cumplidas: ≤1 req/s por dominio, `robots.txt` respetado,
  astro.com / nymero.org / Reddit excluidos, sin LLM local.

> **No se repite ningún dominio de T74/T79.** Los dominios astrología ya usados
> (astralsagehub.com, campus-astrologia.es, astro-cours.com) quedan fuera de
> esta ronda; hay test que lo verifica (`test_no_repite_dominios_t74_t79_astrologia`).

## 1. Dominios validados (modernos, web)

### Español

| Dominio | Sitemap | Sección útil | Fichas est. | Muestras (chars) | Calidad | Idioma | Tipo | Términos cubiertos |
|---|---|---|---:|---|:-:|---|---|
| mundoastro.com | `/sitemap.xml` (88 locs) | `/planetas/` | 28 | 15.028 / 13.911 | 4 | ES (tildes correctas) | moderna | nodos lunares, Quirón, planetas |
| astralisis.com | `/sitemap.xml` (110 locs) | `/articulos/` | 65 | 5.838 / 4.901 | 3-4 | ES | moderna | planeta en signo (Urano/Saturno/Júpiter/Marte/Venus/Mercurio en cada signo) |
| aspectados.com | `/sitemap.xml` (344 locs) | `/guias/`, `/blog/` | 62 | 4.733 / 6.379 | 3-4 | ES | moderna | aspectos (aplicativos/separativos, orbes), Quirón por casas |
| astrocronos.com | `/sitemap.xml` (227 locs) | `/blog/la-casa-*` | 5 | 6.110 / 3.134 | 3 | ES | moderna | casas astrológicas 1-12 (guía por casa) |
| zodiacohoy.com | `/sitemap.xml` (93 locs) | `/blog/` | 36 | 6.834 / 6.773 | 3 | ES (voseo AR) | moderna | ascendente en signo, Marte en cada signo, planetas generacionales en casas |
| aprendeastrologia.com | `/sitemap.xml` (921 locs) | `/blog/` | 262 | 4.631 / 4.392 | 3 | ES | moderna | Sol/Luna/planetas en signo, planetas en carta natal, tránsitos |
| yourastrallife.com | `www./sitemap.xml` (16.646 locs, multilang) | `/es/` | 2.734 (todas las lenguas) | 10.306 / 10.105 | 3-4 ⚠ | ES correcto | moderna | Quirón, compatibilidad por planeta/signo. **⚠ probable contenido generado por IA** (marcar en fusión) |
| miastrologa.com | `/sitemap.xml` (1.975 locs) | `/es/aspects/` | 211 | 2.767 / 2.596 | 3 | ES (slugs EN) | moderna | ficha por aspecto (Asc/MC/Quirón sextil, etc.) |

### Inglés

| Dominio | Sitemap | Sección útil | Fichas est. | Muestras (chars) | Calidad | Idioma | Tipo | Términos cubiertos |
|---|---|---|---:|---|:-:|---|---|
| cafeastrology.com | `/sitemap.xml` (índice, 27 subs) | `/natal/`, `/synastry/`, `/aspects/`, `/sign-combinations/` | ~275 | (ver tanda) | 3-4 | EN | moderna | planeta natal en signo, aspectos de síntesis (Venus-Marte etc.), combinaciones de signos |
| astrology.com | `www./sitemap.xml` (índice, 8.867 locs) | `/houses/`, `/planets/`, `/zodiac-signs/` | ~35 | (ver tanda) | 3 | EN | moderna | 12 casas, 10 planetas, 12 signos (fichas canónicas) |

Notas:
- `cafeastrology.com` publicaba los `<loc>` del índice envueltos en
  `<![CDATA[...]]>` (All in One SEO v5.0.3); se arregló `extraer_locs()` para
  desenvolverlos (commit `5dc9b79`), si no el recorrido del índice se cortaba.
- `astralisis.com` ya estaba crawleado en la ronda fundacional `web/` (64 fichas
  en el manifest); el dedup por manifest lo excluyó correctamente del plan — no
  se volvió a descargar.
- Ruido excluido por patrón: `/birthday/` de cafeastrology (7.365 páginas),
  `/tarot/` de astrology.com (6.176), `/pt/` de yourastrallife.

## 2. Descartados con motivo (nuevos en esta ronda)

| Dominio | Motivo del descarte |
|---|---|
| tucartastral.com | 173 fichas `/astrologia/planetas/*` pero texto **sin tildes** (~2.9k chars) — defecto de acentuación inservible para modelo ES |
| vitastral.com | muestras ~1.6k chars, cortas y plantilladas (calidad 2-3) |
| my-zodiac-ai.com | contenido generado por IA declarado explícitamente; ni muestreado |
| micartadisenohumano.com | no es astrología occidental (diseño humano); fuera de alcance |
| geneticmatrix.com | sistema nuevo-era propio (matriz genética), no astrología por combinación |
| tuastral.com | sin fichas por combinación en sitemap |
| astronet.es | NXDOMAIN (muerto) |
| thechariat.com, constellation.guru, astroenigma.com, cursosdeastrologia.com, astroacademia.com, signosyplanetas.com, zodiaco.es | NXDOMAIN (muertos) |
| cartasastrales.com | sin ruta |
| laboratorioastral.com | HTTP 530 (caído) |
| horoscopo.com | 912 locs pero solo 10 fichas (forecasts, no conocimiento) |
| horoscopo.es | 794 locs, 0 fichas por combinación |
| astrologiaonline.com | 1 loc |
| astroasist.com | 2.833 locs, 0 fichas con patrón útil |
| astralwise.com | 2.343 locs, 0 fichas |
| carta-natal.es | 336 locs, solo 6 fichas (`aspectos.php`, `quiron.php`) — insuficiente |
| bdh.bne.es | bloqueo anti-bot (no se salta, regla fija) |
| es.wikisource.org (astrología) | solo Feijoo (crítica), Samael Aun Weor (no PD) y periféricos: sin manual didáctico PD nuevo |

## 3. Clásicos en dominio público (CANDIDATOS — NO descargados en esta pista)

Por indicación de SIGUIENTE.md, las obras completas **no** se descargan aquí: se
listan identificadores para que otra pista (procesado de libros PD) los trate.
Licencia PD por autor: **William Lilly** (m. 1681) → PD; **Ptolomeo** / traducción
de Thomas Ashmand → PD; **Alan Leo** (m. 1917) → PD; **Sepharial** (m. 1929) → PD
(verificar ediciones posteriores a 1929, que pueden no serlo).

### William Lilly — *Christian Astrology* (1647)

| Identificador (archive.org) | Año | Nota |
|---|---|---|
| `william-lilly-christian-astrology` | — | edición moderna escaneada |
| `ca-william-lilly` | — | colección CA |
| `b30338724` | 1647 | primera edición |
| `bim_early-english-books-1641-1700_christian-astrology-_lilly-william_1647` | 1647 | Early English Books |
| `bim_early-english-books-1641-1700_christian-astrology-_lilly-william_1659` | 1659 | 2.ª edición |
| `isbn_9781162979427` | — | reimpresión (verificar escaneo) |

### Claudio Ptolomeo — *Tetrabiblos*

| Identificador | Fuente | Año | Nota |
|---|---|---|---|
| `ashmand-ptolemys-tetrabiblos-or-quadripartite-en-1917` | archive.org | 1917 | trad. Ashmand, la clásica en EN |
| `ptolemystetrabi01procgoog` | archive.org | 1822 | edición temprana |
| `b29320276` | archive.org | 1828 | edición temprana |
| `ptolemy-tetrabiblos-four-books-of-the-influence-of-the-stars` | archive.org | — | edición moderna |
| `70850` | Proyecto Gutenberg | — | *Tetrabiblos* (trad. Ashmand), texto limpio |

### Alan Leo (1860-1917) — 22 obras en archive.org (selección)

| Identificador | Año | Nota |
|---|---|---|
| `howtojudgenativi00leoa` | 1928 | póstuma pero autor PD |
| `artofsynthesis00leoa` | 1926 | síntesis de carta natal |
| `esotericastrolog00leoa` | — | astrología esotérica |
| `astrologyforall00leogoog` | 1899 | divulgativa |
| `bub_gb_8CwSAAAAYAAJ` | 1899 | misma obra, otro escaneo |
| `the-key-to-your-own-nativity-1927-alan-leo` | 1927 | clave de la natividad |
| `modern-astrology-alan-leo` | — | astrología moderna |
| `horoscopoparatod0000leoa` | 1987 | **en ESPAÑOL** — verificar licencia de la edición/ traducción |
| `alan-leo-1001-notable-nativities-1917` | 1917 | 1001 cartas de famosos |
| `progressedhorosc00leoa` | — | horóscopos progresados |
| `bub_gb_OY7ZLx4jQmcC` | 1906 | escaneo Google |
| `saturnreaperbein00leoa` | 1916 | Saturno |
| `QPZD_astrology-for-all-alan-leo` | — | otro escaneo de *Astrology for All* |

### Sepharial (1864-1929) — 26 obras en archive.org (selección)

| Identificador | Año | Nota |
|---|---|---|
| `the-science-of-foreknowledge` | — | obra magna |
| `DirectionalAstrology` | 1921 | direcciones direccionales |
| `astrologyhowtoma46963gut` | — | *Astrology: How to Amuse and Interest* (via Gutenberg) |
| `manualofoccultis01seph` | 1914 | manual de ocultismo |
| `a-manual-of-occultism-1864-1929-1914-sepharial` | 1914 | misma obra, otro escaneo |
| `kabalaofnumbersh0000seph` | — | **numerología** (útil para familia numerología) |
| `TheKabalaOfNumbers` | — | misma obra |
| `in.ernet.dli.2015.128334` | — | *Primary Directions Made Easy* (India Office) |

**⚠ No PD (marcar con cautela, NO usar sin verificar):**
`transitsplanetar0000seph` (1998), `sepharialsbookof00foul` (1989, Foul — no
Sepharial), `isbn_0572002432` (1965). Son ediciones posteriores a la muerte del
autor con posible copyright del editor/traductor.

### Gutenberg (búsqueda gutendex)

Solo un hallazgo astrología PD: id **70850** (*Tetrabiblos*, trad. Ashmand).
Gutendex presentó timeouts intermitentes durante la consulta; repetir más adelante.

## 4. Descarga de la tanda (web_recup5/)

- Plan: `/Users/angelgonzalez/fase0/plan_t86.jsonl` — 320 candidatas
  (9 dominios: 7×40 + astrology.com 35 + astrocronos 5; astralisis excluido por
  estar ya en `web/`).
- Tanda: `recuperacion_descarga.py --out-dir /Users/angelgonzalez/fase0/web_recup5
  --manifest-previo /Users/angelgonzalez/fase0/manifest_acumulado_t86.jsonl
  (4.720 URLs previas) --web-previa /Users/angelgonzalez/fase0/web
  --tope-por-dominio 40 --max-total 400 --min-chars 1000
  --matriz /Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.json`.
- Log: `/Users/angelgonzalez/fase0/t86_batch.log`.
- Resultado tanda 1: 320 intentos → 300 ok, 19 cortas, 1 error
  (`astrology.com/planets/chiron`, fallo de red). Desglose ok / chars medios:
  mundoastro 40/14.301 (calidad 4), cafeastrology 40/8.269 (calidad 4),
  aspectados 39/7.324, zodiacohoy 40/6.552, astrocronos 5/3.733,
  aprendeastrologia 39/3.219, miastrologa 27/2.810, yourastrallife 36/2.553,
  astrology.com 34/2.325. Las 19 cortas fueron páginas no-ficha
  (`/es/calendar`, `/es/chat`, `/es/vedica`, `/es/biblioteca`, etc.),
  ya excluidas estrechando los patrones de yourastrallife y miastrologa.
- Tanda 2 (dirigida, cupo restante 80): plan
  `/Users/angelgonzalez/fase0/plan_t86b.jsonl` con las 2 fuentes estrechadas
  (miastrologa `/es/aspects/` 40 + yourastrallife `/es/blog/` 40, excluidas
  las ya bajadas), mismo `--out-dir web_recup5`,
  `--manifest-previo manifest_acumulado_t86b.jsonl` (5.040 URLs),
  `--max-total 80`. Log: `/Users/angelgonzalez/fase0/t86_batch2.log`.
- Resultado tanda 2: 80 intentos → 65 ok, 15 cortas. Las 15 cortas son
  hubs de índice `/es/aspects/planet/<planeta>` (páginas de lista, no fichas
  de combinación); las fichas reales (`/es/aspects/<a>-<tipo>-<b>`) entraron
  bien. Aporte: miastrologa +25 fichas de aspecto, yourastrallife +40 posts.
- **Total T86: 400 intentos → 365 ok, 34 cortas, 1 error.**
  Desglose final ok / mediana de chars en `web_recup5/`: mundoastro 40/14.301,
  yourastrallife 76/9.655 (⚠ probable generado por IA), cafeastrology 40/8.269,
  aspectados 39/7.324, zodiacohoy 40/6.552, astrocronos 5/3.733,
  miastrologa 52/2.576, aprendeastrologia 39/3.219, astrology.com 34/2.325.

## 5. Herramientas y verificación

- `descubrir_fuentes.py --conjunto t86`: 10 fuentes registradas en
  `FUENTES_T86`, todas familia `astrologia`, ninguna en dominios bloqueados,
  ninguna repite astrología de T74/T79 (tests `TestFuentesT86`).
- Arreglo CDATA en `extraer_locs()` con tests nuevos (42 tests OK en
  `test_descubrir_fuentes.py`).
- `check.sh` desde la raíz del worktree: ver ESTADO.md.
