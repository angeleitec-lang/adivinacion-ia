# Plan de adquisición de conocimiento de calidad (Fase 0, antes de entrenar)

Fecha: 2026-10-18 · Decisión del usuario: **la calidad del modelo manda sobre el plazo**; se invierten los días que haga falta en recuperar buena información antes de generar el dataset final. La licencia de los textos se revisa más adelante (no bloquea esta fase, pero cada documento conserva su procedencia para poder filtrar después).

## 1. Qué significa «modelo muy bueno» aquí

El modelo debe, en este orden:

1. **Saber** el simbolismo correcto y coherente de cartas, signos, planetas, casas, aspectos y números (varias tradiciones, sin contradecirse).
2. **Leer**: combinar posición, orientación, pregunta y contexto en una interpretación personalizada, empática, honesta (tendencias, no certezas) y bien escrita en español.
3. **Calcular bien** lo calculable (posiciones astrales, números) — esto lo hace el código, el modelo solo lo interpreta.
4. **Mantener límites**: no diagnósticos, no promesas, derivar cuando corresponde.

Hallazgo de la auditoría: lo que hay hoy son sobre todo textos *enciclopédicos* (Wikipedia, blogs). Eso enseña a recitar, no a leer. Hace falta (a) **conocimiento contrastado** por entidad y (b) **lecturas trabajadas** de calidad (la pieza más escasa y valiosa).

## 2. Alcance (decisión del usuario: solo lo más razonable) y matriz de cobertura

`tecnicasCartomancia.md` recoge unas 35 técnicas; **no se aplican todas**. Se trabaja solo el núcleo de mayor demanda en español y se aplaza el resto. La adquisición se dirige por una **matriz de cobertura**: la lista exacta de *entidades* y *facetas* que el modelo debe dominar y, para cada una, cuántas fuentes independientes de calidad la respaldan. Mientras una celda esté por debajo de su mínimo, se sigue buscando.

**Dentro del alcance (única ola activa):** ≈ 1.500 celdas.

| Familia | Entidades | Fuente de verdad en el producto |
|---|---|---|
| Tarot | 78 cartas (RWS como base; variantes de Marsella anotadas en los 22 mayores y en las figuras); tiradas de 1, 2, 3 cartas, herradura, relación, sí/no, Cruz Celta y año; combinaciones | azar (tirada real) |
| Baraja española | 40 naipes (oros, copas, espadas, bastos) + tiradas habituales | azar |
| Astrología occidental | 12 signos; 10 planetas × 12 signos (120); 10 planetas × 12 casas (120); Ascendente × 12; nodos; 5 aspectos × 45 pares (225); tránsitos; revolución solar; sinastría | cálculo astronómico |
| Numerología | 12 números (1–9, 11, 22, 33) × 6 posiciones (camino de vida, destino, alma, personalidad, año y mes personal); compatibilidad; biorritmos | cálculo aritmético |

**Facetas por entidad:** significado general, luz y sombra, derecha/invertida, amor, trabajo, dinero, salud, espiritual, simbolismo, correspondencias (elemento, astro, cábala), consejo práctico y ejemplo de uso.
**Mínimo de fuentes independientes por celda: 5** (≥ 1 clásica, ≥ 2 modernas, ≥ 1 en español).

**Aplazado (no se rastrea ni se calcula hasta que el núcleo esté aprobado):** quiromancia (fase 2 del producto, requiere visión por computador), Lenormand, I Ching, runas, Kipper, Sibilla, naipes comunes, cartas gitanas, Jyotish, astrología china/BaZi, horaria, progresiones, cafeomancia, tasseografía, cristalomancia, péndulo, onicomancia, dermatoglifos y oráculos modernos. Si algo se promueve, entra con el mismo criterio de cobertura.

El estado vive en `finetune/corpus/knowledge/cobertura.json`; `cobertura.md` lista las celdas bajo el mínimo.

**Calculadoras necesarias dentro del alcance:** natal occidental (ya existe, hay que corregir la zona horaria en la pista T1), tránsitos, revolución solar, sinastría, numerología completa y biorritmos, con tests contra valores de referencia. Las de Jyotish, BaZi, I Ching y runas quedan aplazadas.

## 3. Fuentes por niveles (prioridad de calidad)

**Nivel A — libros clásicos de texto completo y limpio** (la mejor materia prima para conocimiento y para ejemplos de lectura):
Waite *Pictorial Key*, Papus, Case (*Tarot Fundamentals*, BOTA), Wirth, Mathers; Alan Leo (*Astrology for All*, *The Key to Your Own Nativity*, *How to Judge a Nativity*), Sepharial; Cheiro, Heron-Allen, Saint-Germain (quiromancia); Ariel Taylor *Numerology Made Plain*, Cheiro *Book of Numbers*; versiones españolas si existen. **Fuente técnica:** texto OCR plano de archive.org (`*_djvu.txt`) o Project Gutenberg / Wikisource, no EPUB de imagen. Hallazgo: de los 155 EPUB descargados en `docs_epub`, solo ~25 son realmente útiles; hay mucho ruido (Teen Magazine, manuales de nórdico antiguo, *Sex: A Manual*) porque se buscó por materia.

**Nivel B — obras modernas de referencia** (copyright; uso aplazado a la revisión legal, pero se recopilan y se etiquetan): Pollack *78 Degrees of Wisdom*, Greer, Banzhaf, Jodorowsky *La vía del tarot*, Nichols *Jung y el tarot*, Hand, Greene, Arroyo, Hamaker-Zondag. **Prioridad al español** cuando exista.

**Nivel C — referencia web por entidad** (páginas por carta/signo/número, URLs construidas a partir de la lista de entidades, no rastreo ciego). Candidatos a validar en la fase de descubrimiento: Biddy Tarot, Labyrinthos, tarot.com, Aeclectic Tarot (significados), Cafe Astrology, astro.com, sitios en español de tarot/astrología/numerología con una página por carta. Cada candidato se evalúa con una muestra antes de rastrearlo entero.

**Nivel D — lecturas trabajadas** (la pieza escasa):
- Foros con lecturas resueltas (Aeclectic Tarot Forum, r/tarotreadings, r/tarot): carta(s) + pregunta + interpretación.
- **Subtítulos de YouTube de tarotistas en español** (volumen alto, voz natural, lecturas reales); requiere instalar `yt-dlp` (no está instalado).
- Ejemplos resueltos dentro de los libros del nivel A/B (Leo, Case, Pollack).
- Se tratan como **modelos de estilo y estructura**, no como verdad de contenido.

**Nivel E — datasets abiertos ya existentes** (solo como contraste y para detectar huecos; no se entrena con ellos sin filtrar): Tarotoo (78 cartas estructuradas, multilingüe) para validar la KB; `Dendory/tarot` (5.770 lecturas generadas por ChatGPT: calidad media, útil de comparación); CELESTIAL (astrología védica en inglés/hindi).

**Lo que NO se hace:** rastreo de dominios enteros por palabras clave (origen del ruido actual), ni usar Wikipedia como respuesta de entrenamiento (queda para contexto/RAG, recortada a las ~208 páginas relevantes).

## 4. Tubería de calidad (cada documento pasa por todas las puertas)

1. **Descarga** con procedencia: `url`, fecha, `hash`, nivel (A–E), tipo de licencia estimada (solo anotada).
2. **Extracción de contenido principal**: trafilatura (web), `pdftotext`/OCR con `ocrmypdf`+`tesseract` (libros escaneados), limpieza de guiones de fin de línea, cabeceras/pies, numeración de páginas y OCR roto (ratio de palabras desconocidas).
3. **Idioma** (es/en; el resto se descarta) y **segmentación** en unidades con sentido (una carta, un signo, un ejemplo de lectura), no en trozos de N caracteres.
4. **Juez LLM local** (27B de nodo1/nodo2) por unidad: ¿conocimiento sobre qué entidad y faceta?, ¿lectura trabajada?, ¿publicidad/relleno/ficción?, ¿calidad 1-5? Se descartan puntuaciones bajas; el resultado etiqueta la matriz de cobertura.
5. **Extracción de afirmaciones**: para cada entidad/faceta, un resumen estructurado por fuente (`claim` + cita + fuente).
6. **Consenso**: se construye la KB final por mayoría entre fuentes, marcando discrepancias entre tradiciones (p. ej. Marsella vs RWS) para decidir cuál se enseña.
7. **Muestreo humano**: el usuario revisa un 3 % aleatorio por nivel (informes `cobertura.md` y `muestras.md`).
8. **Traducción EN→ES** solo de lo que pasa las puertas 1-6 (nada de traducir basura), con validación del resultado (ya corregido en la pista T2).

## 5. Del conocimiento al dataset (resumen; se detalla después)

KB de consenso (+ RAG sobre las unidades buenas) → generación sintética de lecturas **con referencias reales en el prompt** (pista T1.7) y datos calculados por código → panel de jueces (dos modelos) + verificadores deterministas (cartas, orientación, signos, números) → conjunto de oro de ~150 lecturas revisadas por el usuario como test ciego → mezcla con las lecturas trabajadas (nivel D, traducidas y normalizadas) para el estilo.

## 6. Fases, entregables y criterios de aceptación

| Fase | Contenido | Entregable | Criterio |
|---|---|---|---|
| **F0.0** | Herramientas: corregir el scraper (bug «cart», pista T6), traducción (T2), instalar `yt-dlp`; arrancar si hace falta Firecrawl solo para páginas con JavaScript | scraper y traductor corregidos con tests | `check.sh` verde |
| **F0.1** | Inventario curado de fuentes **por familia**: libros (nivel A/B) con identificador y comprobación de texto limpio; sitios (nivel C) con muestra evaluada; foros y canales (nivel D) | `finetune/knowledge/fuentes_libros.jsonl y fuentes_sitios.jsonl` con nivel, familia, URL, idioma, tamaño, nota de calidad | ≥ 70 libros verificados y ≥ 25 sitios evaluados; cada celda del alcance con candidatas suficientes |
| **F0.2** | Descarga y extracción limpia de nivel A/B + C | `knowledge/raw/<nivel>/…` + manifiesto con hash | tasa de OCR roto < 3 % por libro |
| **F0.3** | Segmentación, juez LLM, etiquetado de entidades | `cobertura.json/md` | informe con las celdas bajo el mínimo |
| **F0.4** | Recuperación dirigida a los huecos (búsquedas específicas por entidad faltante) | huecos < 10 % de las celdas | repetir hasta cumplir |
| **F0.5** | Lecturas trabajadas (nivel D): foros + subtítulos + ejemplos de libros | `knowledge/lecturas/` | ≥ 1.500 lecturas puntuadas ≥ 4/5 |
| **F0.6** | KB de consenso + revisión humana del 3 % | `kb/` v2 + `muestras.md` | aprobación del usuario |

Duración estimada: **4–7 días** de trabajo de máquina. Descargas y OCR corren en segundo plano; el cuello de botella es el juez LLM y la traducción. Lo aplazado no empieza hasta que el núcleo cumpla sus mínimos y el usuario apruebe las muestras.

## 7. Cómo se reparte (protocolo multi-IA)

La coordinadora (Claude) investiga, define esquemas y revisa; las IAs locales ejecutan tareas acotadas con ficheros disjuntos. Las pistas T1–T8 ya preparadas siguen vigentes; **se lanzan primero T6 (scraper) y T2 (traducción)** porque son herramientas de esta fase. El resto se pospone hasta cerrar F0. Nuevas pistas previstas: A1 inventario de fuentes por familia, A2 descargador/extractor de libros (OCR), A3 rastreador por entidad (nivel C), A4 foros y subtítulos (nivel D), A5 segmentador + juez LLM + matriz de cobertura, A6 consenso de KB, y C1 calculadoras deterministas del alcance (tránsitos, revolución solar, sinastría, numerología completa y biorritmos).
