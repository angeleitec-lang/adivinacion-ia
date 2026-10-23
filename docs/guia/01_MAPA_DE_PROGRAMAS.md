# Mapa de los programas del proyecto

Esta guía explica, en lenguaje de oficio, qué hace cada programa de la tubería.
No das por sabido nada: si aparece una palabra rara, está en el glosario
(`02_GLOSARIO.md`).

**Cómo leer una ficha.** Cada programa tiene: qué problema resuelve, qué recibe,
qué produce (con rutas reales y un ejemplo de una línea), en qué fase está y si
se usa todavía.

**Rutas de datos.** Los datos pesados NO están en el repo. Viven en
`/Users/angelgonzalez/fase0/` (fase 0) y en `finetune/corpus/` (fase 1, en
`.gitignore`). El código sí está versionado.

---

## Esquema del flujo completo (con las cifras de hoy)

```text
FASE 0 · CONSEGUIR Y FILTRAR EL CONOCIMIENTO          FASE 1 · FABRICAR EJEMPLOS        FASE 2 · ENTRENAR
═══════════════════════════════════════════════════     ═════════════════════════════     ═══════════════════

 (A) CONSEGUIR TEXTOS
   web (páginas en español) ──► fase0/web/*.md
   libros (PDF/EPUB)        ──► fase0/libros/{crudo,limpio,secciones}
   YouTube (subtítulos)     ──► fase0/yt/
   clásicos dominio público ──► fase0/libros_clasicos_pd/
            │
 (B) LIMPIAR Y TROCEAR (quitar ruido, partir por capítulos/entidades)
            │
 (C) SACAR IDEAS CON UNA IA
   juez: «¿de qué carta/signo/número habla este trozo?»
     └─► evidencias:  23.682 (web) + 16.545 (libros)
   afirmaciones: una idea suelta por línea
     └─► 100.401 (web) + 38.857 (libros)
            │
 (D) CONSENSO Y BASE DE CONOCIMIENTO (KB)
   agrupar ideas que dicen lo mismo, marcar contradicciones
     └─► consenso: 4.021 celdas (entidad × faceta)
   KB v2: tarot 78 · astrología 424 · numerología 69 · baraja 40
   cobertura: 299 de 7.455 celdas «completas» (≥5 fuentes)
            │                                        │
            └──── la KB alimenta los prompts ────────►┤
                                                     │
                                          (E) GENERAR LECTURAS DE EJEMPLO
                                            12.536 tareas → Mercury 3 escribe
                                            lecturas y un verificador las aprueba
                                              └─► dataset v1d: 13.290 filas
                                                  (train 11.986 / val 648 / test 656)
                                                          │
                                          (F) CONTROLES DE CALIDAD    │
                                            QA sin fugas, diversidad, │
                                            muletillas, semáforo verde│
                                                                    ▼
                                                     (G) ENTRENAR Y EVALUAR
                                                       modelo ajustado + 240 casos fijos
```

Las cifras son de `docs/ARMAR_DATASET_V1D.md` y `docs/CIERRE_FINAL.md`
(2026-10-23).

---

## (A) Conseguir textos

### `collect_corpus.py`
Lanza Firecrawl (un servicio que copia páginas web como texto) para extraer el
corpus. Lee `corpus/urls.txt` (una URL por línea) y guarda cada página en
`corpus/raw/<dominio>/<slug>.md`. Es el modo «una página por URL».
**Fase 0 · web. En uso** para listas concretas.

### `discover_urls.py`
Descubre URLs sobre adivinación usando Exa (un buscador). No genera informes:
solo saca las URLs de los resultados y las quita repetidas. Su salida alimenta
`collect_corpus.py`. **Fase 0 · web. En uso** puntual.

### `expand_wikipedia.py`
Descubre artículos de Wikipedia en español por categoría (por ejemplo,
«Tarot») y escribe una lista de URLs lista para `collect_corpus.py`. Respeta
el límite de peticiones con pausas. **Fase 0 · web. En uso** puntual.

### `fetch_documents.py`
Descarga libros clásicos (PDF/EPUB) de archive.org para el corpus. Lista curada
a mano: dominio público (Papus, Waite, Cheiro…) y algunos de licencia dudosa
marcados «consultar». **Fase 0 · libros. En uso** inicial.

### `harvest_epubs.py`
Busca y descarga EPUB libres de archive.org por tema (en inglés y español).
Guarda en `corpus/docs_epub/<tema>/` y registra licencia en un manifiesto.
**Fase 0 · libros. En uso** inicial.

### `docs_to_md.py`
Extrae texto de los PDF/EPUB de `corpus/docs` y lo deja como markdown en
`corpus/raw/docs/<familia>/<slug>.md`, listo para `build_dataset.py`. Elige
EPUB antes que PDF. **Fase 0 · libros. En uso** inicial.

### `libros_fetch.py`
Descarga reanudable y educada de los textos OCR de archive.org. Escribe en
`<salida>/crudo/<id>.txt` y registra cada acción. Ante demasiados cortes (HTTP
429) para limpio. **Fase 0 · libros. En uso** dentro del pipeline de libros.

### `libros_pipeline.py` (T24)
Orquestador reanudable de la fase 0 de libros. Encadena las piezas sueltas en
etapas idempotentes sobre un directorio de trabajo: crudo → limpio → secciones
→ informe. Si algo ya está hecho, lo salta.
**Fase 0 · libros. En uso** como encadenado principal de libros.

### `libros_fuentes.py`
Inventario unificado de libros fuente. Lee los ficheros de `knowledge/`, los
pasa a un esquema común, quita lo no aprobado y quita repetidos por título.
**Fase 0 · libros. En uso** como catálogo de entrada.

### `descarga_clasicos_pd.py` (T55)
Descarga reanudable de las fuentes clásicas de dominio público. Comprueba que
cada URL esté en la lista blanca de repositorios patrimoniales y baja el texto
a `fase0/libros/crudo/<id>.txt`. Guarda la huella SHA-256 de cada fichero.
**Fase 0 · libros. En uso** (clásicos).

### `descubrir_fuentes.py` (T74)
Descubridor de fuentes nuevas. Recorre el `sitemap.xml` de un dominio
respetando `robots.txt` y la tasa de cortesía, y escribe URLs candidatas en un
plan compatible con `recuperacion_descarga.py`. **Fase 0 · web. En uso** para
rellenar huecos.

### `recuperacion_dirigida.py`
Recuperación de celdas que no alcanzan el mínimo de cobertura. Lee la matriz de
cobertura y produce un plan (`plan_recuperacion.jsonl`) con fuentes nuevas y
consultas de búsqueda por faceta. **Fase 0 · web. En uso** dirigido.

### `recuperacion_descarga.py` (T64)
Segunda iteración de la recuperación: toma las URLs candidatas del plan, las
filtra contra lo ya descargado, prioriza baraja española y numerología, y las
baja con la tubería existente. **Fase 0 · web. En uso** dirigido.

### `web_fetch.py`
Cliente HTTP educado para rastreo dirigido. Reglas: máximo 1 petición cada X por
dominio, respeta `robots.txt`, reintenta con espera ante cortes, detecta
antibot sin insistir. Manifiesto reanudable. **Fase 0 · web. Pieza base** que
usan otros.

### `web_indices.py`
Descubrimiento de páginas desde índices. Para sitios con una página por
carta/número pero sin patrón de URL fijo: se parte de una página índice y se
siguen los enlaces que cumplen una regla configurable. **Fase 0 · web. En uso**.

### `web_rejillas.py`
Expansión de las rejillas de astrología en tareas de descarga. Cada tarea
apunta a una entidad concreta (planeta en signo, planeta en casa o aspecto) con
su `entidad_id` en español canónico, para poder cruzar fuentes entre sitios.
**Fase 0 · web. En uso** para astrología.

### `web_pipeline.py` (T25)
Orquestador del pipeline web en español. Descubre páginas desde los índices de
`knowledge/sitios_indice_es.json`, las descarga con cortesía, extrae el
contenido a Markdown, registra cada URL y genera el informe de cobertura.
**Fase 0 · web. En uso** como encadenado principal.

### `scraper/` (Scrapy, spider `deep.py`)
Crawler alternativo con el framework Scrapy. El spider `deep` recorre sitios
saltándose rutas de tienda, login y archivos. Su salida se integra con
`build_scrapy_dataset.py`. **Fase 0 · web. En uso** secundario.

### `yt_discover.py`
Descubrimiento de vídeos de YouTube y selección de canales (track A4.2).
**Fase 0 · YouTube. En uso** (limitado por cortes de YouTube).

### `yt_fetch.py`
Descarga subtítulos de YouTube. Solo subtítulos: manual en español si existe; si
no, automático original. Nunca el español automático traducido.
**Fase 0 · YouTube. En uso** (limitado por 429).

### `yt_pipeline.py` (T21.3)
Orquestador del pipeline de YouTube. Encadena: descubrir → descargar subtítulos
→ limpiar → clasificar → extraer → normalizar. Cada etapa es reanudable; si
YouTube corta por límite, el pipeline para y avisa.
**Fase 0 · YouTube. En uso** (encadenado principal de vídeo).

---

## (B) Limpiarlos y trocearlos

### `libros_extraer.py`
Extracción de texto plano desde EPUB locales. Recorre las páginas en el orden
del índice del libro, ignora scripts y estilos, y convierte los títulos en
líneas con `#`. **Fase 0 · libros. Pieza base** del pipeline de libros.

### `libros_limpiar.py`
Limpieza de textos OCR y EPUB. Quita páginas con OCR poco fiable, cabeceras y
números de página, reune palabras partidas y ruido, y recorta portada e índice.
No traduce ni reescribe. **Fase 0 · libros. Pieza base**.

### `libros_segmentar.py`
Segmentación de libros limpios en capítulos y secciones con sentido. Detecta
encabezados y, en tarot/baraja/astrología/numerología, también entidades (las
78 cartas, signos, planetas, números). **Fase 0 · libros. Pieza base**.

### `libros_informe.py`
Informe de calidad de los libros limpios y segmentados. Recalcula métricas de
limpieza y escribe una tabla por libro, marcando los que requieren revisión
humana. **Fase 0 · libros. En uso** como control.

### `web_extraer.py`
Extracción de páginas HTML a Markdown con procedencia. Usa trafilatura para
quedarse con el contenido principal, descarta páginas cortas y quita frases de
navegación/comerciales. Guarda cabecera YAML con el origen.
**Fase 0 · web. Pieza base**.

### `web_calidad.py` (T31)
Auditoría determinista (sin IA) de la calidad de las páginas web descargadas.
Marca banderas: página corta, mojibake (texto con acentos rotos), título pobre,
duplicada. **Fase 0 · web. En uso** como control.

### `web_informe.py`
Informe de cobertura por sitio y entidad. Lee el manifiesto y los .md y
produce un `informe.md`: descargadas, bloqueadas, cortas, y entidades con
menos de 3 sitios. **Fase 0 · web. En uso** como control.

### `yt_clean.py`
Limpieza y métricas de subtítulos VTT de YouTube (quita marcas de tiempo y
etiquetas). **Fase 0 · YouTube. Pieza base** del pipeline A4.

### `yt_normalize.py`
Normalización de subtítulos a pares de pregunta/respuesta con fidelidad
comprobada (que la respuesta no se desvíe del vídeo).
**Fase 0 · YouTube. Pieza base** del pipeline A4.

### `cartas.py` (A4.1 / T53)
Catálogo de cartas (tarot y baraja española) y normalización de nombres. Los
subtítulos y textos traen los nombres rotos («la papisa», «paje de
pentáculos»); este módulo los identifica contra un catálogo cerrado de 78 + 40
naipes para que no se pierda ninguna mención.
**Fase 0 · transversal. Pieza base** (nombres bien puestos).

### `license_filter.py`
Clasifica la licencia de los textos brutos y decide si son usables. Clases:
público, cc-by, cc-by-sa, cc-nc, cc-nd, desconocida. Lee los manifiestos de
`raw/` y `docs/`. **Fase 0 · transversal. En uso** (la legalidad se revisa
aquí, aunque la decisión final sea posterior).

### `prune_short_en.py`
Purga pares y documentos en inglés cortos para no acumular basura. En datasets
quita filas cortas no españolas; en crudos borra documentos no españoles de
menos de X caracteres. **Fase 0/1 · transversal. En uso** de mantenimiento.

### `salud_datos.py` (T59)
Vigilancia barata, reparación opcional y copias de seguridad de fase 0.
Recorre los JSONL clave y comprueba integridad (líneas rotas, truncadas,
duplicados). Solo si se pide, retira la última línea truncada o crea una copia
comprimida. **Fase 0 · transversal. En uso** como guardián.

---

## (C) Sacar evidencias y afirmaciones con una IA

Una **evidencia** es un trozo de texto etiquetado: «esto habla de la carta X,
de esta faceta». Una **afirmación** es una idea suelta y concreta extraída de
esa evidencia. Aquí es donde una IA (un modelo de lenguaje) lee y clasifica.

### `juez.py` (pista A5)
Juez LLM de evidencias. Toma secciones de libros y páginas web y produce
evidencias en el esquema de `cobertura.py`: qué entidad, qué faceta, calidad,
periodo. Es el que «etiqueta» cada trozo. **Fase 0 · transversal. Pieza base**.

### `evidencias_incremental.py`
Ejecución incremental del tramo calidad → juez → append de evidencias. Procesa
solo las páginas web pendientes (las que aún no están en `juicios.jsonl` ni en
`evidencias.jsonl`). Reutiliza las piezas existentes.
**Fase 0 · web. En uso** para no repetir trabajo.

### `afirmaciones_es.py` (T29)
Extractor de afirmaciones atómicas en español. Convierte cada evidencia en
afirmaciones de una sola idea, fieles al texto, sin inventar. Base de la KB.
**Fase 0 · transversal. Pieza base** de las afirmaciones.

### `afirmaciones_libros.py` (T38)
Extracción de afirmaciones desde libros. Igual que `afirmaciones_es.py` pero
añade `cita_original`: la afirmación se redacta en español y la cita se copia
tal cual del original. Ejemplo real (recortado):
`{"entidad_id": "tarot-mayor-14", "faceta": "significado_general", "afirmacion": "…se asocia con el engaño…", "cita_original": "deceit, immorality"}`
**Fase 0 · libros. En uso**.

### `afirmaciones_rapido.py` (T69)
Pasada masiva de extracción de afirmaciones con el backend rápido (Mercury 3,
en la nube). Calcula las evidencias pendientes y escribe en directorios NUEVOS
para no pisar los del nodo local. **Fase 0 · transversal. En uso** (gran
volumen).

### `traducir_afirmaciones.py` (T116)
Traduce al español las afirmaciones en inglés de los libros. Conserva el resto
de campos y añade una huella para poder reanudar. **Fase 0 · libros. En uso**.

### `lecturas_extraer.py` (T37)
Extractor de «lecturas trabajadas» de libros segmentados. Una lectura trabajada
es una consulta resuelta: cartas (o carta natal) con pregunta explícita y una
interpretación desarrollada. Es la pieza más escasa del corpus.
**Fase 0 · libros. En uso** (poca baraja española).

### `clasicos_pd_a_evidencias.py` (T57)
Orquestador de los clásicos de dominio público hacia evidencias. Reutiliza
limpieza, segmentación y juez sobre un directorio NUEVO, para que los diez
clásicos PD cubran las celdas que exigen fuente clásica.
**Fase 0 · libros. En uso**.

### `libros_comprados_prep.py` (T118)
Preparación de los libros de astrología comprados (Arroyo y Sasportas). Los
PDF están apaisados (dos páginas del libro por hoja). Este script recorta cada
media hoja y las endereza. **Fase 0 · libros comprados. En uso** (preproceso).

### `libros_comprados_en.py` (T115)
Libros comprados en inglés (Pollack, Greer) hacia evidencias. Reutiliza las
etapas del pipeline sobre un work-dir NUEVO, nunca sobre el real. Los PDF no se
copian al repo. **Fase 0 · libros comprados. En uso**.

### `libros_comprados_astro.py` (T119)
Procesado de los libros comprados de astrología (Arroyo, Sasportas) a
evidencias. Aportó las 723 afirmaciones de T119. **Fase 0 · libros comprados.
En uso**.

### `libro_comprado_nichols.py` (T114)
Procesado del libro «Jung y el Tarot» (Nichols) hacia evidencias. Solo
arcanos mayores, enfoque junguiano. Se trabaja sobre el texto extraído, el PDF
nunca se copia al repo. **Fase 0 · libros comprados. En uso**.

### `libro_comprado_greene.py` (T130)
Procesado del libro «Saturn» (Liz Greene). El escaneo no tenía capa de texto
útil: se extrae por OCR con tesseract a 300 dpi. **Fase 0 · libros comprados.
En uso** (OCR).

### `libros_comprados_baraja.py` (T129)
Procesado determinista de dos libros comprados de baraja española (Salas y
Tiradas). **Fase 0 · libros comprados. En uso**.

### `parafrasear_baraja.py` (T131)
Parafrasea las afirmaciones de baraja española. Reescribe cada cita recortada
como una afirmación breve, completa y propia en español (anti-copia).
**Fase 0 · libros comprados. Pendiente de ejecutar** (necesita Mercury).

### `txt_ocultismo_numerologia.py` (T133)
Apuntes TXT del usuario (OCR de archive.org): «Diccionario de ciencias
ocultas» y «Numerología fácil». Segmentación determinista, filtro estricto y
etapas de juez y afirmaciones reanudables. **Fase 0 · transversal. En uso**.

### `llm_client.py` (A4.4)
Cliente LLM para los nodos de inferencia. Reparte peticiones entre endpoints,
reintenta con espera, y extrae JSON de forma robusta. Soporta backend en la
nube con clave. **Transversal. Pieza base** que consumen casi todos los que
usan IA.

### `yt_classify.py` (A4.4)
Clasificación de vídeos de YouTube con IA: decide de qué trata cada vídeo
descargado (tarot, astrología, numerología…) para enrutarlo.
**Fase 0 · YouTube. En uso**.

### `yt_extract.py` (A4.5)
Extracción de lecturas y conocimiento de los subtítulos con IA, más una
validación determinista de lo extraído. **Fase 0 · YouTube. En uso**.

---

## (D) Consenso, base de conocimiento (KB) y cobertura

El **consenso** agrupa las afirmaciones que dicen lo mismo sobre una misma
celda (una entidad × una faceta) y marca las que se contradicen. La **KB** es
el resultado ordenado. La **cobertura** mide cuántas fuentes respaldan cada
celda.

### `consenso_kb.py` (T38 / A6)
Consenso por celda a partir de afirmaciones. Agrupa por (entidad, faceta) con
una IA (equivalencia y contradicción, con caché) y produce por celda:
mayoritarias, discrepancias, única fuente y alertas. Ejemplo real (recortado):
`{"entidad_id": "11|alma", "faceta": "correspondencias", "unica_fuente": [{"afirmacion": "El once se asocia con el alma…"}]}`
**Fase 0 · transversal. Pieza base** (4.021 celdas).

### `comparar_consenso.py` (T76)
Comparativa del consenso local frente a Mercury 3. Reconstruye las afirmaciones
y mide el acuerdo entre ambos. **Fase 0 · transversal. En uso** como control.

### `build_kb.py`
Construye la KB estructurada inicial para la generación sintética. Genera
`tarot.json` (78 cartas), `astrologia.json` (signos, planetas, casas,
aspectos) y `numerologia.json` (números y maestros).
**Fase 0 · KB. Semilla inicial** (antes del consenso).

### `build_kb_baraja.py`
Genera `kb/baraja_espanola.json` (40 naipes) con la tradición clásica.
PROVISIONAL: los significados resumen manuales clásicos y NO proceden aún del
consenso de fuentes. **Fase 0 · KB. Provisional**.

### `kb_v2.py` (T66)
Constructor de la KB v2 a partir del consenso. Lee `consenso.jsonl` y
construye una KB por familia: tarot 78, astrología 424, numerología 69,
baraja 40. **Fase 0 · KB. En uso** (la KB buena).

### `cobertura.py` (T14)
Matriz de cobertura del alcance. Para cada celda entidad × faceta, cuenta
cuántas fuentes independientes de calidad la respaldan. Aquí solo cuenta e
informa. **Fase 0 · transversal. Pieza base** de la cobertura.

### `cobertura_v3.py` (T82)
Cobertura v3 reproducible: una orden que regenera la matriz con las evidencias
vigentes y dice qué falta, sin IA ni red. Hoy: 299 de 7.455 celdas completas.
**Fase 0 · transversal. En uso** (la cobertura actual).

### `cierre_recopilacion.py` (T85/T90)
Cierre de la recopilación: orquestador del encadenado final. Cuando terminan
las pasadas en vivo, ejecuta en orden y sin olvidos: deduplicado del consenso,
reconstrucción de KB y cobertura, con copias previas.
**Fase 0 · transversal. En uso** al cerrar.

### `filtro_atribucion.py` (T88)
Auditoría y filtro determinista de atribución en astrología y numerología.
Retira evidencias asignadas a una entidad cuyo título o URL nombran OTRA
entidad (contaminación cruzada). Retiró 2.188 evidencias.
**Fase 0 · transversal. En uso** (calidad).

### `aplicar_limpieza_libros.py` (T71)
Aplica (en copia) la limpieza de evidencias de libros y mide su efecto. Filtro
determinista con tres motivos de retirada (p. ej. evidencias de La Luna
etiquetadas como astrología). **Fase 0 · libros. En uso** (en copia).

### `limpiar_evidencias_libros.py`
Post-filtro determinista (PROPUESTA, no aplica a producción). Propone quitar
evidencias de arcanos mayores cuyo título ya identifica OTRA carta. Solo
clasifica, no borra. **Fase 0 · libros. Propuesta, no aplicada**.

### `diagnostico_tarot_libros.py`
Diagnóstico (solo lectura) de la evidencia clásica de tarot en libros.
Reproduce con pruebas el defecto de mapeo de nombres ingleses en `cartas.py`.
**Fase 0 · libros. Diagnóstico puntual**.

### `catalogo_astro_propuesta.py` (T137)
Propuesta de catálogo astrológico ampliado (casas, elementos, modalidades).
Propuesta SIN APLICAR: calcula en una COPIA la cobertura hipotética de añadir
19 entidades nuevas. No escribe en el catálogo real.
**Fase 0 · astrología. Propuesta, no aplicada**.

### `inventario_legal.py` (T84)
Inventario de procedencia y licencias de todas las fuentes de fase 0. Recorre
manifiestos y metadatos y produce una fila por fuente con su procedencia y una
clasificación de riesgo. No consulta la red.
**Fase 0 · transversal. En uso** (legalidad).

---

## (E) Fabricar ejemplos de entrenamiento (dataset)

El **dataset** es la lista de ejemplos pregunta→respuesta con los que se
entrena el modelo. Aquí se generan con una IA buena (Mercury 3) usando la KB
como referencia, y se guardan en formato ShareGPT.

### `generate_tasks.py`
Genera la matriz de trabajos sintéticos en `corpus/jobs.db`. Combina cartas,
signos, números y datos calculados para crear miles de tareas de lectura.
**Fase 1 · transversal. Pieza base** (crea las 12.536 tareas).

### `fase1_prompts.py`
Prompts de fase 1 con «Referencia» de la KB de consenso y datos calculados.
Cada prompt incluye solo hechos contrastados y marca las discrepancias entre
tradiciones. **Fase 1 · transversal. Pieza base** (las instrucciones que lee
la IA generadora).

### `ejecutor_fase1.py` (T62 / T100)
Ejecutor de la generación de fase 1 sobre `jobs.db`. Toma tareas pendientes,
genera la lectura, la verifica y reintenta si falla. Las aceptadas se guardan.
Es el que corrió la pasada completa T100. **Fase 1 · transversal. En uso**
(generación principal).

### `generate_synthetic.py`
Worker de generación sintética (viejo): reclama jobs de `jobs.db` y llama a la
IA. **Fase 1 · transversal. SUSPENDIDO** (usa prompts viejos sin tildes; no
reanudar).

### `fase1_piloto.py` (T49)
Piloto de fase 1: medir si los prompts producen lecturas aceptables. Pide unas
pocas lecturas a una IA real y las pasa por el verificador. No toca `jobs.db`.
**Fase 1 · transversal. Piloto puntual**.

### `piloto_mercury.py` (T83)
Piloto de fase 1 con Mercury 3: medir si sus lecturas pasan el verificador con
la calidad exigida, frente a la línea base local. 42/45 tareas ok.
**Fase 1 · transversal. Piloto puntual**.

### `multiturno.py` (T45)
Generador de conversaciones multi-turno en dos fases. Primero una IA escribe los
turnos del consultante (pregunta, aclaración, reacción); luego se genera la
respuesta. **Fase 1 · transversal. En uso** (familia multiturno).

### `build_dataset.py`
Convierte el corpus markdown extraído con Firecrawl a JSONL ShareGPT. Trocea
cada página por sus encabezados: el encabezado es el tema de la pregunta y el
cuerpo es la respuesta. **Fase 1 · transversal. Pieza base** (formato).

### `build_scrapy_dataset.py`
Construye pares ShareGPT desde `corpus/raw_scrapy` sin duplicar lo ya
integrado. Reutiliza la lógica de `build_dataset.py` y descarta respuestas cuya
huella ya exista. **Fase 1 · transversal. En uso** (Scrapy).

### `translate_dataset.py`
Traduce al español las respuestas en inglés del dataset. Detecta el idioma y
solo traduce las que están en inglés. **Fase 1 · transversal. En uso** (idioma).

### `merge_datasets.py`
Fusiona el dataset ya traducido con los pares nuevos de Scrapy, sin duplicar.
**Fase 1 · transversal. En uso** (fusión parcial).

### `merge_final.py`
Fusiona pares reales y sintéticos, quita duplicados y genera el reparto
estratificado (train/val/test). Salida: `corpus/final/{train,val,test}.jsonl`.
**Fase 1 · transversal. Pieza base** (fusión final).

### `armar_dataset_v1.py` (T103 / T126)
De las lecturas de Mercury al dataset de entrenamiento, en un solo comando.
Encadena con salvaguardas: snapshot → reverificar → filtrar fugas → validar →
fusionar → preparar → QA. Produce `dataset_fase1_v1d` (13.290 filas).
**Fase 1 · transversal. En uso** (el comando que arma el dataset).

### `preparar_entrenamiento.py` (T61)
Prepara el dataset final para la fase 2. Valida el esquema, descarta filas
inválidas, comprueba que no haya fuga del conjunto de evaluación y calcula
estadísticas. **Fase 1 · transversal. Pieza base** (antes de entrenar).

### `rag_index.py`
Índice RAG sobre el corpus: trocea, calcula embeddings (vectores que capturan
el significado con nomic-embed-text) y permite búsqueda por similitud.
**Transversal. Auxiliar** (búsqueda semántica).

### `calculos/` (astro.py, numerologia.py, biorritmos.py)
Calculadoras deterministas: carta natal, revolución solar, tránsitos,
numerología y biorritmos. Dan los datos exactos que luego se meten en los
prompts, para que la IA no los invente. **Transversal. Pieza base** (números
reales, no inventados).

---

## (F) Controles de calidad (QA / auditoría)

### `validate_synthetic.py`
Valida y quita duplicados de los pares sintéticos. Puertas: idioma español,
longitud, texto de relleno, repetición, eco de la pregunta y coherencia con
los datos del prompt. **Fase 1 · transversal. Pieza base** (primera puerta).

### `audit_dataset.py`
Auditoría de calidad del dataset ShareGPT: puntúa cada par y escribe ficheros
nuevos. Nunca modifica la entrada. **Fase 1 · transversal. En uso** (auditoría).

### `qa_dataset.py` (T110)
QA independiente del dataset: auditoría de solo lectura que NO reutiliza las
funciones de validación de T103 (las reimplementa). Busca fugas con el
conjunto de evaluación y solapes entre splits. **Fase 1 · transversal. En uso**
(semáforo).

### `diversidad_dataset.py` (T106)
Diversidad y balance del dataset (solo lectura). Mide vocabulario variado
(TTR), frases únicas y muletillas repetidas. **Fase 1 · transversal. En uso**
(que el modelo no suene clónico).

### `calidad_lecturas.py` (T105)
Auditoría de calidad de las lecturas ya aceptadas. Detecta defectos que el
verificador de fase 1 no mide: fórmulas repetidas, muletillas, género asumido,
contradicciones astrológicas. **Fase 1 · transversal. En uso** (control fino).

### `prerevision.py` (T52)
Prerevisión de la muestra: banderas de calidad y puntuación de sospecha.
Recorre la muestra y aplica comprobaciones (texto vacío, ruido, idioma, otra
entidad, promesas vedadas). **Fase 0/1 · transversal. En uso** (pre-humano).

### `muestras.py` (T48 / T93)
Muestras aleatorias del 3 % por nivel para revisión humana. Prepara la revisión
previa a la fase 1 y el conjunto de oro reutilizable.
**Fase 0/1 · transversal. En uso** (muestreo).

### `revisor_local.py` (T54)
Revisor local de muestras: una página HTML autocontenida (sin red) con todas
las fichas, banderas y atajos de teclado. Guarda los veredictos en el
navegador. **Fase 0/1 · transversal. En uso** (revisión humana).

### `reverificar_fase1.py` (T101)
Re-verifica un `aceptadas.jsonl` con el verificador corregido. Separa válidas
de inválidas sin tocar la entrada. **Fase 1 · transversal. En uso** (puerta).

### `seleccionar_regenerar.py` (T108)
Selecciona lecturas aceptadas que conviene regenerar con el prompt mejorado.
Escribe un JSONL priorizado. No llama a nodos ni excluye lecturas.
**Fase 1 · transversal. En uso** (regeneración dirigida).

### `ensayo_extremo.py` (T70)
Ensayo extremo de la fase 1: punta a punta, simulado, sin red. Ejecuta toda la
cadena sobre una COPIA de `jobs.db` con tareas representativas, para ver si
algo se rompe antes de gastar horas reales.
**Fase 1 · transversal. En uso** (prueba integral).

### `comparar_backends.py` (T65 / T68)
Comparativa de backends para extraer afirmaciones. Pone a prueba el backend
rápido (Mercury) frente al nodo local sobre las mismas evidencias.
**Fase 0/1 · transversal. En uso** (elegir motor).

### `auditoria_ronda7.py` (T123)
Auditoría adversa de la ronda 7. No corrige el código: fabrica casos trampa,
los pasa por los verificadores reales y resume aciertos y defectos.
**Fase 1 · transversal. En uso** (ataque de calidad).

### `cobertura_dataset.py` (T15)
Informe de cobertura del dataset. Cuenta por entidad cuántos pares la mencionan
en la respuesta y cuántos solo en la pregunta, y señala huecos.
**Fase 1 · transversal. En uso** (cobertura del dataset).

### `yt_qa.py` (A4.7)
Informe de calidad y cobertura del material de YouTube: cuántos vídeos
aprovechados, qué familias cubren y qué falta.
**Fase 0 · YouTube. En uso** (control de vídeo).

---

## (G) Entrenar y evaluar

### `evaluacion_casos.py` (T56)
Conjunto fijo de evaluación del modelo. Genera 20 casos por familia (240 en
total) con datos calculados reales y las comprobaciones que debe aplicar el
evaluador. **Fase 2 · transversal. Pieza base** (el examen).

### `evaluar_modelo.py` (T56)
Evaluador automático del modelo. Compara las respuestas del modelo con los 240
casos fijos sin consumir IA (salvo un juez opcional).
**Fase 2 · transversal. Pieza base** (la nota).

### `linea_base.py` (T99)
Línea base de modelos sin entrenar sobre los 240 casos. Genera la respuesta de
varios modelos con temperatura fija, para tener con qué comparar el modelo ya
entrenado. **Fase 2 · transversal. En uso** (punto de partida).

### Entrenamiento (fuera de estos scripts)
El entrenamiento en sí lo hace una herramienta externa (Soup) sobre el dataset
preparado. La guía está en `finetune/GUIA_REENTRENAMIENTO.md` y la decisión de
modelo en `MODELO.md` / `DECISION_MODELO_MOE.md`. **Fase 2 · externa**.

---

## Tabla: pista T## → qué hizo → programa

| Pista | Qué hizo | Programa principal |
|---|---|---|
| T10 | Nodos lunares medios en trópico | `calculos/astro.py` |
| T11 | Segmentador ya no marca prosa como preliminar | `libros_segmentar.py` |
| T12 | Filtro opcional `--min-density` | `license_filter.py` / segmentador |
| T14 | Matriz de cobertura de fuentes | `cobertura.py` |
| T15 | Cobertura del dataset | `cobertura_dataset.py` |
| T21.3 | Pipeline YouTube | `yt_pipeline.py` |
| T24 | Pipeline de libros reanudable | `libros_pipeline.py` |
| T25 | Pipeline web en español | `web_pipeline.py` |
| T26 | Cobertura web ampliada (647 páginas) | `web_pipeline.py` / índices |
| T29 | Extractor de afirmaciones en español | `afirmaciones_es.py` |
| T31 | Auditoría de calidad web | `web_calidad.py` |
| T36 | Índices de sitios ES (baraja, numerología) | `web_indices.py` / `knowledge/` |
| T37 | Extractor de lecturas de libros | `lecturas_extraer.py` |
| T38 | Afirmaciones de libros y consenso | `afirmaciones_libros.py` / `consenso_kb.py` |
| T45 | Conversaciones multi-turno | `multiturno.py` |
| T48 | Muestra de revisión del 3 % | `muestras.py` |
| T49 | Piloto de fase 1 | `fase1_piloto.py` |
| T52 | Prerevisión de la muestra | `prerevision.py` |
| T53 | Cartas en inglés y reproceso de Waite | `cartas.py` |
| T54 | Revisor local HTML | `revisor_local.py` |
| T55 | Clásicos de dominio público con hashes | `descarga_clasicos_pd.py` |
| T56 | 240 casos de evaluación y evaluador | `evaluacion_casos.py` / `evaluar_modelo.py` |
| T57 | Clásicos PD convertidos a evidencias | `clasicos_pd_a_evidencias.py` |
| T59 | Salud de datos y copias SHA-256 | `salud_datos.py` |
| T60 | Mapa del pipeline | `docs/PIPELINE.md` |
| T61 | Preparar entrenamiento | `preparar_entrenamiento.py` |
| T62 | Ejecutor de fase 1 | `ejecutor_fase1.py` |
| T64 | Recuperación 2 (descarga de plan) | `recuperacion_descarga.py` |
| T65 / T68 | Backend rápido Mercury (comparativa) | `comparar_backends.py` |
| T66 | KB v2 desde consenso | `kb_v2.py` |
| T69 | Pasada rápida de afirmaciones | `afirmaciones_rapido.py` |
| T70 | Ensayo extremo punta a punta | `ensayo_extremo.py` |
| T71 | Limpieza de libros en copia | `aplicar_limpieza_libros.py` |
| T72 | Prompts de tiradas largas y baraja | `fase1_prompts.py` |
| T73 | Consenso rápido con dedup por fuente | `consenso_kb.py` |
| T74 | Fuentes nuevas (sitemap) | `descubrir_fuentes.py` |
| T76 | Consenso Mercury frente a nodos | `comparar_consenso.py` |
| T78 | Exclusiones del consenso | `consenso_kb.py` |
| T82 | Cobertura v3 reproducible | `cobertura_v3.py` |
| T83 | Piloto Mercury | `piloto_mercury.py` |
| T84 | Inventario legal | `inventario_legal.py` |
| T85 / T90 | Cierre de la recopilación | `cierre_recopilacion.py` |
| T88 | Filtro de atribución | `filtro_atribucion.py` |
| T89 | Baraja en el ejecutor | `ejecutor_fase1.py` |
| T93 | Muestra de revisión v2 | `muestras.py` |
| T94 | Pasada rápida parcial (parada) | `afirmaciones_rapido.py` |
| T95 | Documento de generación ShareGPT | `generate_tasks.py` / docs |
| T99 | Línea base sin entrenar | `linea_base.py` |
| T100 | Pasada completa de fase 1 (Mercury) | `ejecutor_fase1.py` |
| T101 | Reverificación con verificador corregido | `reverificar_fase1.py` |
| T103 | Armar dataset v1 en un comando | `armar_dataset_v1.py` |
| T105 | Auditoría de lecturas aceptadas | `calidad_lecturas.py` |
| T106 | Diversidad y balance del dataset | `diversidad_dataset.py` |
| T108 | Selección para regenerar | `seleccionar_regenerar.py` |
| T110 | QA independiente del dataset | `qa_dataset.py` |
| T113 | Reverificación mercury_b | `reverificar_fase1.py` |
| T114 | Libro comprado Nichols | `libro_comprado_nichols.py` |
| T115 | Libros comprados en inglés | `libros_comprados_en.py` |
| T116 | Traducir afirmaciones al español | `traducir_afirmaciones.py` |
| T118 | Preparar libros de astrología comprados | `libros_comprados_prep.py` |
| T119 | Libros comprados de astrología | `libros_comprados_astro.py` |
| T121 | Cierre final de la recopilación | `docs/CIERRE_FINAL.md` / `cierre_recopilacion.py` |
| T123 | Auditoría adversa ronda 7 | `auditoria_ronda7.py` |
| T124 | Regeneración mercury_c | `ejecutor_fase1.py` / `seleccionar_regenerar.py` |
| T126 | Dataset v1d (reemplazos) | `armar_dataset_v1.py` |
| T129 | Libros comprados de baraja española | `libros_comprados_baraja.py` |
| T130 | Libro comprado Greene (OCR) | `libro_comprado_greene.py` |
| T131 | Parafrasear baraja española | `parafrasear_baraja.py` |
| T133 | Apuntes TXT ocultismo y numerología | `txt_ocultismo_numerologia.py` |
| T137 | Propuesta de catálogo astrológico | `catalogo_astro_propuesta.py` |
| T138 | Esta guía didáctica | `docs/guia/` |

**Nota:** algunas pistas (T41, T46, T47, T50, T51, T58, T63, T67, T75, T79,
T80, T81, T86, T87, T91, T96, T101b/c/d) son arreglos, fuentes nuevas o
auditorías internas de las pistas de arriba; su detalle está en
`docs/ESTADO_Y_PENDIENTES.md`.
