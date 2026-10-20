# Fuentes web en español: astrología por combinación (T42)

Sondeo del 2026-10-20. Objetivo: localizar sitios en español con **páginas originales
y largas por combinación astrológica** (planeta en signo, planeta en casa, aspectos y
ascendente) para cubrir la matriz de astrología, que partía de 79 de 5.247 celdas
completas.

## Método

- Descubrimiento por búsqueda web (DuckDuckGo a través de `r.jina.ai`, con pausas de
  cortesía) y por sondeo directo de sitemaps.
- Para cada candidato se descargó `robots.txt`, se localizaron los sitemaps y se contaron
  las URLs que casan con los patrones de entidad. Después se extrajo una muestra con
  `corpus.web_extraer.extraer` para comprobar longitud y calidad del texto.
- Se descartaron plantillas o agregadores generados por IA, páginas cortas, sitios en
  inglés, dominios con bloqueo explícito a bots de entrenamiento y sitios ya cubiertos por
  `sitios_indice_es.json`, `sitios_indice_es_tarot.json` o `rejillas_astrologia.json`.

## Cobertura

Unión de los 15 sitios: **120 planeta-signo, 120 planeta-casa, 27 aspectos, 12 ascendentes
y 12 nodos lunares**. Los dos huecos grandes de la matriz (planeta×signo y planeta×casa)
quedan cubiertos al completo; los aspectos solo parcialmente.

| Dominio | Tipo | Calidad | Páginas | Cobertura | Muestra |
|---|---|---|---|---|---|
| enastrologico.com | blog | 4 | 192 | 72 signo, 120 casa | 2.929 |
| astrochart.co | sitio | 4 | 240 | 120 signo, 120 casa | 11.210 |
| fernandoangelcoronado.es | blog | 4 | 116 | 12 signo, 80 casa, 12 asc, 12 nodos | 8.750 |
| aprendeastrologia.com | blog | 3 | 37 | 25 signo, 5 aspectos | 5.546 |
| astroworld.es | blog | 3 | 24 | 12 signo, 12 asc | 18.078 |
| astralisis.com | sitio | 4 | 64 | 64 signo | 8.853 |
| ruthmontenegro.com | blog | 4 | 12 | 12 signo (Sol) | 11.819 |
| astrologica.es | blog | 3 | 4 | 4 signo | 4.106 |
| soyespiritual.top | blog | 4 | 48 | 37 casa, 11 asc | 21.663 |
| leandroliptak.com | blog | 4 | 82 | 70 signo, 12 asc | 3.961 |
| tailoredmoon.com | sitio | 3 | 120 | 120 signo | 1.438 |
| simbologia.net | blog | 3 | 12 | 12 casa | 7.201 |
| ritmolunar.com | blog | 4 | 271 | 120 signo, 120 casa, 19 aspectos, 12 asc | 1.700 |
| www.astrocosmo.cl | blog | 4 | 117 | 82 signo, 3 casa, 8 aspectos, 5 asc | 8.051 |
| caminosdeconocimiento.com | blog | 3 | 18 | 15 signo, 3 aspectos | 9.050 |

La cobertura más completa es **ritmolunar.com** (signo, casa, aspectos y ascendente en un
solo sitio). Le siguen **astrochart.co** y **enastrologico.com** para la matriz
planeta-signo/planeta-casa, y **fernandoangelcoronado.es** para casa, ascendente y nodos.

## Descartes

- **al-mutem.com** y **astralevolution.com**: `robots.txt`/`Content-Signal` bloquean
  explícitamente el entrenamiento con IA. No se saltó esa intención.
- **miastrologa.com**, **auratella.com**, **astralsagehub.com**, **theastroscope.com**:
  plantillas o agregadores generados por IA, con miles de páginas multilingües y texto
  genérico.
- **astrocentro.com**: los sitemaps listan artículos, pero las URLs devuelven 404.
- **astroak.com**, **wemystic.com**, **astralwise.com**, **astrotheme.com**: solo inglés
  (o `/es/` inexistente).
- **mundoastro.com**: solo 4 URLs válidas y una da 404. **zodiacohoy.com**: 1 URL.
  **astrologia.club** y **tucartastral.com**: sin páginas por combinación.
- **astrocronicas.com**: misma marca que fernandoangelcoronado.es; se evita duplicar.
- **astrolium.com**, **astroopal.com**, **anahana.com**, **encolombia.com**,
  **laguiaesoterica.com**, **micartadisenohumano.com**, **horoscopia.org**,
  **astroinsightz.com**, **esotericouniverso.es**, **comoaprenderastrologia.com**,
  **laberintoastrologico.com**: 0 coincidencias con los patrones de entidad.

## Nota sobre `entidad_id`

La matriz de cobertura no tiene entidad para **Ascendente×signo** ni para **nodos
lunares**. Solo existen:

- `{signo}|signo`
- `{planeta}|{signo}|planeta_en_signo`
- `{planeta}|casa{n}|planeta_en_casa` (sin guion: `casa4`)
- `{planeta}|{aspecto}|{planeta}|aspecto` (orden i<j de la lista de planetas)

Por eso las páginas de ascendente y de nodos se recogen como corpus, pero no se mapean a
entidades. No se inventaron identificadores.

## Ficheros

- `sitios_indice_es_astro_casas.json`: 15 sitios con índice, regex validada y recuento de
  URLs capturadas.
- `fuentes_web_es_astro_casas.jsonl`: una línea por dominio con autoría, año, calidad
  estimada, evidencia y muestras.
- `corpus/tests/test_sitios_indice_es_astro_casas.py`: estructura, regex y fuentes.

El rastreo se ejecuta con `corpus/web_pipeline.py --limite-por-sitio 2000`, porque el
valor por defecto (50) recorta la matriz.
