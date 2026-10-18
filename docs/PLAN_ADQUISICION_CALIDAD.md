# Plan de adquisición de conocimiento de calidad (Fase 0, antes de entrenar)

Fecha: 2026-10-18 · Decisión del usuario: **la calidad del modelo manda sobre el plazo**; se invierten los días que haga falta en recuperar buena información antes de generar el dataset final. La licencia de los textos se revisa más adelante (no bloquea esta fase, pero cada documento conserva su procedencia para poder filtrar después).

## 1. Qué significa «modelo muy bueno» aquí

El modelo debe, en este orden:

1. **Saber** el simbolismo correcto y coherente de cartas, signos, planetas, casas, aspectos y números (varias tradiciones, sin contradecirse).
2. **Leer**: combinar posición, orientación, pregunta y contexto en una interpretación personalizada, empática, honesta (tendencias, no certezas) y bien escrita en español.
3. **Calcular bien** lo calculable (posiciones astrales, números) — esto lo hace el código, el modelo solo lo interpreta.
4. **Mantener límites**: no diagnósticos, no promesas, derivar cuando corresponde.

Hallazgo de la auditoría: lo que hay hoy son sobre todo textos *enciclopédicos* (Wikipedia, blogs). Eso enseña a recitar, no a leer. Hace falta (a) **conocimiento contrastado** por entidad y (b) **lecturas trabajadas** de calidad (la pieza más escasa y valiosa).

## 2. Principio: adquisición dirigida por una matriz de cobertura

En lugar de «rastrear y ver qué sale», se define la lista exacta de **entidades** y **facetas** que el modelo debe dominar, y se mide para cada una cuántas fuentes independientes de calidad la cubren. Hasta que no se alcanza el mínimo, se sigue buscando.

| Dominio (V1) | Entidades | Facetas por entidad | Mínimo de fuentes independientes |
|---|---|---|---|
| Tarot | 78 cartas | significado general, derecha/invertida, amor, trabajo, dinero, salud, espiritual, simbolismo de la imagen, correspondencias (elemento, astro, cábala), consejo | **6** |
| Tarot | tiradas (1, 2, 3, herradura, relación, sí/no, Cruz Celta 10, año 12 meses) | significado de cada posición, orden de lectura, ejemplo resuelto | **4** |
| Tarot | combinaciones | pares y tríos habituales, lectura de palos y arcanos dominantes | **3** |
| Astrología | 12 signos; 10 planetas × 12 signos (120); 10 planetas × 12 casas (120); Ascendente × 12; aspectos (5) × pares de planetas; nodos; tránsitos básicos; sinastría | descripción, luz y sombra, consejo | **4** (≥ 1 clásica + ≥ 2 modernas) |
| Numerología | 1–9, 11, 22, 33 × posiciones (camino de vida, destino, alma, personalidad, año personal, compatibilidad) | descripción, luz y sombra, amor, trabajo, método de cálculo | **5** |
| **Fase 2** Quiromancia | líneas mayores/menores, montes, formas de mano, dedos | descripción, variantes, advertencias | 4 |
| **Fase 3** Otros | runas (24), I Ching (64), Lenormand (36), baraja española (40), astrología china | igual | 3 |

El estado de la matriz vive en `finetune/corpus/knowledge/cobertura.json` (lo actualiza el etiquetador de fuentes; `cobertura.md` es el informe legible con las celdas por debajo del mínimo).

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
| **F0.1** | Inventario curado de fuentes: lista de libros (nivel A/B) con identificador de archive.org/Gutenberg y comprobación de texto limpio; lista de sitios (nivel C) con muestra evaluada; plan de foros y canales (nivel D) | `knowledge/fuentes.jsonl` con nivel, URL, idioma, tamaño, nota de calidad | ≥ 60 libros verificados, ≥ 15 sitios evaluados |
| **F0.2** | Descarga y extracción limpia de nivel A/B + C | `knowledge/raw/<nivel>/…` + manifiesto con hash | tasa de OCR roto < 3 % por libro |
| **F0.3** | Segmentación, juez LLM, etiquetado de entidades | `cobertura.json/md` | informe con las celdas bajo el mínimo |
| **F0.4** | Recuperación dirigida a los huecos (búsquedas específicas por entidad faltante) | huecos < 10 % de las celdas | repetir hasta cumplir |
| **F0.5** | Lecturas trabajadas (nivel D): foros + subtítulos + ejemplos de libros | `knowledge/lecturas/` | ≥ 1.500 lecturas puntuadas ≥ 4/5 |
| **F0.6** | KB de consenso + revisión humana del 3 % | `kb/` v2 + `muestras.md` | aprobación del usuario |

Duración estimada: **3–6 días** de trabajo de máquina (descargas y OCR en segundo plano; juez LLM en los dos nodos; el cuello de botella es el juez y la traducción).

## 7. Cómo se reparte (protocolo multi-IA)

La coordinadora (Claude) investiga, define esquemas y revisa; las IAs locales ejecutan tareas acotadas con ficheros disjuntos. Las pistas T1–T8 ya preparadas siguen vigentes; **se lanzan primero T6 (scraper) y T2 (traducción)** porque son herramientas de esta fase. El resto se pospone hasta cerrar F0. Nuevas pistas previstas: A1 inventario de fuentes, A2 descargador/extractor de libros (OCR), A3 rastreador por entidad (nivel C), A4 foros y subtítulos (nivel D), A5 segmentador + juez LLM + matriz de cobertura, A6 consenso de KB.
