# T118 — Libros de astrología COMPRADOS (Arroyo y Sasportas), preparación para T119

## Procedencia y uso (importante)

- Ambos PDF son **ejemplares comprados por el usuario** (2026-10, carpeta
  `/Users/angelgonzalez/fase0/libros_comprados/`). **Con copyright.**
- Uso exclusivo: consulta interna para construir el dataset de entrenamiento.
- Los textos extraídos viven en `/Users/angelgonzalez/fase0/libros_comprados_astro/`
  y **NUNCA** se copian al repo ni a `corpus/final` ni a ningún sitio público.
  En el repo solo quedan este informe y el script de preparación.
- Si T119 genera evidencias a partir de estos libros, deben marcarse con la
  procedencia `libro_comprado` (uso interno) como hacen `clasicos_t92.md` con los PD.

## Salidas (fase0, fuera del repo)

- `limpio/arroyo.txt` + `limpio/arroyo.paginas.jsonl`
- `limpio/sasportas.txt` + `limpio/sasportas.paginas.jsonl`
- `informe_calidad.md` (métricas, tabla hoja-a-hoja de Sasportas, cobertura de
  casas y partes, problemas conocidos)
- `work/ocr/` (caché OCR reanudable, media página por fichero) y
  `work/config_sasportas.json` (psm elegido: 3)
- Regenerar todo: `python finetune/corpus/libros_comprados_prep.py ambos`
  (nice -n 10, ≤3 procesos; solo CPU del iMac; no toca nodo1/nodo2).

## Arroyo — *Astrology, Psychology and the Four Elements* (1982)

- 99 hojas apaisadas (2 libros por hoja, texto real del PDF), recorrido
  **completo**: portada → sumario → prólogo → 4 capítulos de Parts I-III y
  apéndices; etiquetas impresas `xl` … `184`, 196 medias páginas, ~418 200 caracteres.
- Método: recorte por mitad con `pdftotext -x -y -W -H` (la capa de texto es de
  buena calidad; no hizo falta OCR), limpieza de cabeceras recurrentes (171
  líneas), números sueltos y uniones de guion (748+255).
- Vocabulario inglés 83,67 % → 84,81 % tras limpieza (las palabras no-EN son
  nombres propios, griego y latinismos).
- Defectos conocidos (detallados en el informe): tipografía decorativa de las
  portadillas con espacios internos («Astro logy & P syc ho [ogy»); en la hoja
  25 L la capa de texto trae «5» suelto donde la página impresa es la 35
  (artefacto del PDF, se conserva la etiqueta tal cual).

## Sasportas — *The Twelve Houses* (1985), Howard Sasportas, prefacio de Liz Greene

- **ESCÁNEO INCOMPLETO**: 63 hojas (126 medias páginas) de un libro de ~220
  páginas impresas. La capa de texto original era inservible (palabras pegadas,
  56,07 % vocabulario); se rehízo el OCR: 300 dpi, partida la hoja por la mitad,
  `tesseract -l eng --psm 3` → 86,20 % vocabulario, pegadas 4466 → 1782.
- **Qué SÍ está** (ver tabla de cobertura en el informe):
  - Sumario, Acknowledgements, Prefacio (Greene), Introducción.
  - Part 1 *The Landscape of Life*: cap. 1 Basic Premises y cap. 2 Space, Time
    and Boundaries (completo).
  - Part 2 *Mapping the Journey*: **capítulos 3 a 14, las doce casas completas**
    (1ª … 12ª, págs. impresas 37–107). Detección automática: las 12 casas
    presentes con rúbrica propia.
  - Inicio del cap. 15 *Grouping the Houses* (desde pág. 108): cuadrantes,
    hemisferios, EAST/WEST y tríplicidades de fuego/aire/agua/tierra.
- **Qué FALTA** (no está en el archivo, no usar para evidencias):
  - El **final del cap. 15** y todo lo posterior al corte en la pág. impresa 131.
  - Apéndices (el texto cita un «Appendix 2» sobre división de casas), glosario,
    bibliografía e índice: no aparecen como rúbrica en ninguna hoja escaneada.
  - Solo hay 2 medias páginas realmente en blanco (1 L, 2 L) y una figura
    (15 L); el resto tiene texto. No es un problema de OCR: las hojas faltantes
    no están escaneadas (el PDF termina en la hoja 63).
- Defectos menores: fracciones como «2½» salen «2%»; en las 2 últimas hojas se
  pierden caracteres del borde izquierdo (defecto del escaneo físico); las
  figuras quedan sin texto alternativo.

## Instrucciones para T119

- Usar `sasportas.txt` con `sasportas.paginas.jsonl` (offsets exactos por media
  página con hoja/lado/etiqueta impresa) para anclar evidencias a páginas.
- **No** citar este libro como fuente de: división de casas (Apéndice), tabla de
  aspectos, ni nada posterior a la pág. 131. Las casas 1–12 y los caps. 1–2 y el
  arranque del 15 son material sano.
- Las marcas `#`/`##` de ambos textos son heurísticas: revisar antes de segmentar.
