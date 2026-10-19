# Fuentes web en español — síntesis T20

Catálogo complementario en `fuentes_web_es.jsonl` (41 fuentes verificadas abriendo al menos una URL real de cada una, 2026-10-19). No duplica los 143 dominios de `fuentes_sitios.jsonl` ni los sitios de las rejillas existentes.

## (a) Las 15 mejores fuentes por valor para el proyecto

1. **forotarot.net** (foro, calidad 5) — 57.181 temas y 616.871 mensajes; subforos propios de Interpretaciones (Baraja Española), Combinaciones, Tiradas, Consultas, Astrología y Numerología. Cubre las cinco familias; lecturas reales de consultantes.
2. **brisademartarot.blogspot.com** (calidad 4) — guía de baraja española de 63.000 caracteres en una página: modo de echar las cartas y significado de cada palo y número.
3. **institutolta.com** (PDF curso, calidad 4) — curso "Baraja Española" de Soledad Chico Labra: historia, simbología y significado carta a carta con invertidas; clase 4 sobre tiradas.
4. **eragon8.blogspot.com** (calidad 4) — serie "Cartomancia y esoterismo": palos, figuras, historia del mazo y combinaciones al derecho/al revés.
5. **tarotdestrella.blogspot.com** (calidad 4) — combinaciones resueltas de baraja española (ejemplos de 3-4 naipes) y fichas por naipe.
6. **euroresidentes.com/entretenimiento/curso-tarot** (calidad 4) — ~80 lecciones y páginas de respuestas donde la tarotista "Chloé" interpreta tiradas concretas dejadas por consultantes.
7. **quareia.squarespace.com** (PDF libro, calidad 4) — "El Tarot del Siglo XXI" en español, 482.000 caracteres: simbolismo, interpretación y tiradas con enfoque histórico-crítico.
8. **grupovenus.com** (calidad 4) — curso de astrología (tomos 15-16, 250.000 caracteres) y curso de aspectos: relación planeta-casa-signo extensa.
9. **es.wikisource.org** (biblioteca, dominio público, calidad 4) — "Curso Zodiacal" de Samael Aun Weor y de Krumm Heller (65 páginas), Feijóo sobre astrología judiciaria (s. XVIII).
10. **YouTube José Millán — Astrología Humanística** (307.000 subs, calidad 4) — tránsitos y nodos lunares en español.
11. **YouTube Círculo Antares** (16.400 subs, calidad 4) — escuela profesional: sinastría y astrología rigurosa.
12. **YouTube María Blaquier** (32.300 subs, calidad 4) — astrología horaria y sinastría.
13. **losarcanos.com** (calidad 3) — camino de vida, números del alma y de la expresión (11.566 caracteres).
14. **eclectica.com.ar** (calidad 3) — lecturas de tiradas narrativas en español rioplatense; categoría Cartomancia con 19 posts.
15. **montekurama.com.ar** (calidad 3) — ejemplos resueltos de tiradas pasado/presente/futuro bien redactados.

## (b) Cobertura de la matriz por familia

| Familia | Fuentes | Cobertura principal |
|---|---|---|
| baraja_espanola | 12 | Los 40 naipes (brisademartarot, institutolta, eragon8, astrologuias), combinaciones (tarotdestrella, eragon8 entrega 3), tiradas (institutolta clase 4, instantesconrosmeris), foro con lecturas reales (forotarot), curso en vídeo (Lari Téllez). Hueco mayor del proyecto: **cubierto**. |
| lecturas | 11 | Q&A real (euroresidentes, forotarot), lecturas narrativas (eclectica, montekurama), combinaciones resueltas (tarotdestrella), libro con método (quareia), lecturas en directo (Nelys Tarot, Eduardo Tarot Profesional). Hueco mayor del proyecto: **cubierto**. |
| astrologia | 13 | Curso extenso (grupovenus), casas y planetas (carta-natal.es), PD clásico (wikisource), tránsitos/nodos/sinastría/revolución solar vía 8 canales YouTube verificados. |
| numerologia | 6 | Camino de vida y números del alma/expresión (losarcanos), series en vídeo (Josep Gimbernat 52+ entregas, Ricard Barrufet, Alejandro Lavín, La Numerología). Es la familia más floja: la rejilla existente (moonoscope, yourastrallife, astro-seek) sigue siendo el grueso. |
| tarot | 17 | Escuelas (Marsella: Plano Consciente), combinaciones de arcanos (angelestarotyvidencia), cursos en vídeo (Popy, El Tarot de Andy), lecturas (Nelys, Eduardo), Q&A (euroresidentes), libro (quareia). |

## (c) Descartes y motivos

- **Bloqueados (403/anti-bot), anotados como intentados**: Biblioteca Digital Hispánica (bdh.bne.es y SRU), Cervantes Virtual, HathiTrust.
- **Sin contenido útil**: Project Gutenberg (casi nada en español), es.wikibooks.org (vacío de esoterismo), pdfcoffee.com (shell JS sin texto), astrologia.es (vacío), astroworld.es (corta conexión), cosmoesencia.com (comercial sin denidad), numerologiaviva.com y elnumerologo.com (monocélula/comercial), tarotistas.es (directorio comercial de videncia), winegogh.net (reconvertido a turismo), esoterismos.com (HTTP 500), dominios NXDOMAIN varios (numerologia.es, jovymel.com, asociaciontarot.com, fenat.org…).
- **Regla de no rastreo**: Scribd, Studocu, CourseHero, SlideShare y Amazon (pago/login).
- **Ya catalogados**: todo dominio presente en `fuentes_sitios.jsonl` (143) y en las rejillas (40), p. ej. tarotrossana.com, elreydecopas.com, astro-seek, moonoscope.
- **Casinos/juegos** (888casino, asdepoker) y prensa superficial (Univision, Cosmopolitan): sin valor de conocimiento.

## Notas de método

- Búsqueda: solo Brave Search fue utilizable (vía la herramienta de fetch; curl directo devuelve 429 persistente). Descubrimiento de canales por el buscador interno de YouTube.
- Verificación: cada fuente se abrió con extracción de texto visible y recuento de menciones clave; PDFs con `pdftotext`.
- Los canales YouTube se catalogan por ID/handle para garantizar unicidad de "dominio" en el JSONL.
