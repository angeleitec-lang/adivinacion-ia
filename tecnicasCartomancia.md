# Mapa de Técnicas de Adivinación y Astrología

> Inventario completo de los sistemas interpretativos de "lectura del futuro",
> organizado por familias, con notas de viabilidad técnica para un producto de
> IA (LLM + cálculo astronómico + visión por cámara).

## Nota previa

Ninguna de estas técnicas "predice el futuro" en sentido científico. Son
sistemas **interpretativos y reflexivos**: a partir de un elemento aleatorio
(cartas), un dato calculado (carta astral) o una característica física (mano),
producen una lectura coherente y personalizada que invita a la reflexión. Esto
es justo lo que un LLM hace bien: combinar los elementos y redactar.

---

## 1. Cartomancia (lectura de cartas)

| Técnica | Descripción | Viabilidad |
|---|---|---|
| **Tarot** | 78 cartas: 22 Arcanos Mayores + 56 Menores (4 palos). Sistemas: Rider-Waite-Smith, Marsella, Thoth. Tiradas: 1 carta, 3 cartas (pasado/presente/futuro), Cruz Celta (10), herradura, etc. | Muy alta (abundante texto) |
| **Lenormand** | 36 cartas, más literal y "predictivo"; significado por carta + combinaciones de pares. | Muy alta |
| **Kipper** | 36 cartas, origen alemán, lectura posicional por casas. | Alta |
| **Sibilla (Sibilla Italiana)** | 52 cartas, estilo italiano, tono directo. | Alta |
| **Baraja española** | 40/48 naipes (oros, copas, espadas, bastos), popular en España y Latinoamérica. | Alta |
| **Naipes comunes** | 52 cartas francesas (póker). | Alta |
| **Cartas gitanas** | Variante tradicional de naipes con simbolismo propio. | Alta |
| **Oráculos modernos** | Mazos temáticos (ángeles, hadas, runas, etc.), cada uno con guía propia. | Alta |

---

## 2. Quiromancia (lectura de la mano)

### Líneas mayores
- **Línea del corazón**: vida afectiva y emocional.
- **Línea de la cabeza**: mente, intelecto, forma de pensar.
- **Línea de la vida**: vitalidad, energía, longevidad (no indica fecha de muerte).
- **Línea del destino**: carrera, rumbo, factores externos.

### Líneas menores
- **Línea del Sol (Apolo)**: éxito, creatividad, reconocimiento.
- **Línea de Mercurio (salud)**: salud y comunicación.
- **Cinturón de Venus**: sensibilidad, emotividad.
- **Líneas de matrimonio**: vínculos afectivos duraderos.

### Montes (relieves de la palma)
- Venus, Júpiter, Saturno, Apolo, Mercurio, Marte, Luna.

### Otros rasgos
- **Forma de la mano** (los 4 elementos): tierra, aire, fuego, agua.
- **Dedos y falanges**: longitudes relativas y proporciones.
- **Dermatoglifos**: patrones de huellas dactilares.
- **Onicomancia**: lectura de las uñas.

> ⚠️ **Viabilidad**: esta es la parte más difícil técnicamente. Detectar líneas
> reales en una imagen es un problema de **visión por computador** (CV), no de
> LLM. Casi no existen datasets etiquetados de manos con líneas de quiromancia;
> habría que generarlos (sintéticos o anotación manual) o simplificar la lectura
> a rasgos medibles (forma de mano, proporción de dedos) + interpretación textual.

---

## 3. Astrología (carta astral)

- **Carta natal**: posiciones exactas de los planetas en el momento y lugar de nacimiento (Sol, Luna, Mercurio, Venus, Marte, Júpiter, Saturno, Urano, Neptuno, Plutón, ascendente, nodos lunares).
- **Signo solar / lunar / ascendente**: las tres piezas base.
- **Las 12 casas**: áreas de la vida (identidad, dinero, comunicación, hogar, etc.).
- **Aspectos**: ángulos entre planetas (conjunción, sextil, cuadratura, trígono, oposición).
- **Tránsitos**: posición de los planetas *ahora* comparada con la carta natal.
- **Revolución solar**: carta del cumpleaños; predicción del año entrante.
- **Progresiones secundarias**: evolución simbólica de la carta natal.
- **Sinastría**: compatibilidad entre dos cartas natales.
- **Astrología horaria**: carta del momento exacto de la pregunta.
- **Astrología védica (Jyotish)**: sistema indio, zodiaco sideral, dasha, nakshatras.
- **Astrología china**: ciclo de 12 animales + 5 elementos, BaZi (4 pilares).

> ✅ **Clave técnica**: el cálculo de posiciones planetarias se hace con una
> librería de **astronomía** (recomendado: **Swiss Ephemeris** / `pyswisseph`), no
> lo "adivina" el LLM. El modelo solo *interpreta* lo que calcula la librería.
> Esto hace que la carta astral sea objetivamente correcta y el producto sólido.

---

## 4. Numerología

- **Número del camino de vida**: propósito general (suma de la fecha de nacimiento).
- **Número del destino / expresión**: talentos (desde el nombre completo).
- **Número del alma**: motivación interior (vocales del nombre).
- **Número de la personalidad**: cómo te ven los demás (consonantes).
- **Año personal / mes personal**: ciclos temporales.
- **Compatibilidad numerológica**: afinidad entre dos personas.

> ✅ Totalmente calculable por código; el LLM solo interpreta.

---

## 5. Otras técnicas adivinatorias

- **I Ching**: 64 hexagramas, consulta con monedas o varetas, texto oracular.
- **Runas**: Futhark (24 runas), tirada y lectura simbólica.
- **Cafeomancia**: lectura de los posos del café.
- **Tasseografía**: lectura de las hojas de té.
- **Cristalomancia**: bola de cristal / espejos (escrying).
- **Péndulo / radiestesia**: respuestas binarias por movimiento.
- **Biorritmos**: ciclos físico (23d), emocional (28d) e intelectual (33d) calculables desde la fecha de nacimiento.

---

## Resumen de arquitectura por familia

| Familia | Fuente de verdad | Rol del LLM | Dificultad |
|---|---|---|---|
| Cartomancia | Aleatorio (tirada real) | Interpretar la combinación | Baja |
| Astrología | Cálculo astronómico (Swiss Ephemeris) | Interpretar posiciones/aspectos | Baja (cálculo ya resuelto) |
| Numerología | Cálculo aritmético | Interpretar números | Baja |
| Quiromancia | **Imagen de la mano (CV)** | Interpretar rasgos detectados | **Alta** |
| I Ching / Runas | Aleatorio | Interpretar | Baja |

### Tres piezas técnicas del producto
1. **Datos de texto** (tarot, astrología, numerología, I Ching) → corpus para RAG y/o fine-tune del LLM.
2. **Cálculo astronómico / numérico** → librería determinista, no IA.
3. **Visión por cámara** (lectura de la palma) → pipeline de CV, el más arriesgado; diferido a fase 2.
