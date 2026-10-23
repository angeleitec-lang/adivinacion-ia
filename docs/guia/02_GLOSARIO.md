# Glosario del proyecto

Cada término lleva una definición corta y un ejemplo sacado de este proyecto.
Los números citados son de octubre de 2026.

**1. Dataset (conjunto de datos).** Lista de ejemplos con los que se entrena el
modelo. Ejemplo: `dataset_fase1_v1d` tiene 13.290 filas de pregunta→respuesta.

**2. Fine-tuning (ajuste fino).** Partir de un modelo ya entrenado en mucho
texto general y afinarlo con nuestro dataset concreto. Es lo que haremos en fase
2 con el dataset v1d.

**3. LoRA.** Técnica de ajuste fino que solo entrena una parte pequeña del
modelo (una «capa adicional»), en vez de todo. Abarata y acelera el
entrenamiento. En este proyecto se contempla como opción de entrenamiento.

**4. Época (epoch).** Una pasada completa del dataset durante el entrenamiento.
Si el dataset tiene 12.000 filas y se entrenan 3 épocas, el modelo ve las
12.000 tres veces.

**5. Split train/val/test.** Reparto del dataset en tres montones: *train* para
aprender, *val* para ajustar sin engañarse, *test* para la nota final intacta.
En v1d: train 11.986 / val 648 / test 656.

**6. Token.** Pieza de texto que procesa el modelo (una palabra o fragmento).
Los costes y límites se miden en tokens: la pasada T100 gastó millones de
tokens en Mercury.

**7. Evidencia.** Trozo de texto etiquetado: «esto habla de la carta X, de la
faceta Y». Ejemplo real: `{"entidad_id": "tarot-copas-02", "faceta":
"significado_general", "dominio": "angelestarotyvidencia.com", "calidad": 4}`.

**8. Afirmación.** Una idea suelta y concreta extraída de una evidencia, una
sola por línea. Ejemplo: «Esta combinación habla de sanación compartida».

**9. Consenso.** Agrupar las afirmaciones que dicen lo mismo sobre una misma
celda y marcar las que se contradicen. Resultado: 4.021 celdas de consenso.

**10. KB (base de conocimiento).** El conocimiento ordenado y contrastado que
alimenta los prompts. La buena es `kb_v2`: tarot 78, astrología 424,
numerología 69, baraja 40 entradas.

**11. Celda.** Un cruce entre una entidad y una faceta, p. ej.
`tarot-copas-02 | significado_general`. La matriz completa tiene 7.455 celdas.

**12. Entidad.** Lo que se interpreta: una carta, un signo, un planeta, un
número. Cada una tiene un `entidad_id` fijo como `tarot-mayor-14`.

**13. Faceta.** El ángulo que se estudia de una entidad: significado general,
simbolismo, correspondencias, consejo práctico…

**14. Cobertura.** Cuántas fuentes independientes respaldan cada celda.
«Completa» exige ≥5 fuentes, ≥1 clásica, ≥2 modernas, ≥1 en español y calidad
≥3. Hoy: 299 de 7.455.

**15. Juez.** La IA que etiqueta evidencias: lee un trozo y dice de qué entidad
y faceta habla, con una calidad. Programa: `juez.py`.

**16. Anti-copia (paráfrasis).** Reescribir una cita textual como una
afirmación propia para no copiar literalmente. Ejemplo: T131 parafrasea las 320
afirmaciones de los libros de baraja.

**17. QA (aseguramiento de calidad).** Revisiones automáticas que buscan fugas,
solapes y defectos antes de entrenar. El QA de v1d dio semáforo verde.

**18. Semáforo QA.** Verde/ámbar/rojo del control de calidad. Verde = sin
fugas, sin solapes entre splits, sin casi-idénticos. Como en v1d.

**19. Alucinación.** Cuando la IA se inventa datos que no están en la fuente.
Contra eso va la «Referencia» de la KB en los prompts: «solo existen las
cartas que aparecen en la consulta».

**20. Prompt.** La instrucción que se le da a la IA. En fase 1 cada prompt
lleva la Referencia de la KB y los datos calculados. Programa:
`fase1_prompts.py`.

**21. ShareGPT.** Formato de conversación para el dataset: una lista de turnos
con roles `system`, `human` y `gpt`. Así están los `train.jsonl` del proyecto.

**22. JSONL.** Formato de fichero: una línea por objeto JSON. Casi todos los
datos del proyecto (evidencias, afirmaciones, dataset) son `.jsonl`.

**23. Fuente.** El origen de una evidencia: una web, un libro o un vídeo, con
su `fuente_id`. Ejemplo: `1899minettawhatthecardstell` (libro de 1899).

**24. Dominio público.** Textos sin derechos de autor, usables libremente. Los
clásicos de T55 se descargan solo de repositorios patrimoniales de la lista
blanca.

**25. Licencia Creative Commons (CC).** Familias de permisos: cc-by (atribuir),
cc-by-sa (compartir igual), cc-nc (no comercial), cc-nd (sin derivados). Los
clasifica `license_filter.py`.

**26. OCR.** Reconocimiento óptico de caracteres: leer texto de una imagen o
escaneo. El libro de Greene (T130) se sacó por OCR con tesseract.

**27. Mojibake.** Texto con los acentos rotos por una mala codificación
(«EspaÃ±a»). `web_calidad.py` marca las páginas con mojibake.

**28. robots.txt.** Fichero que un sitio web usa para decir qué no se debe
rastrear. Los programas de descarga lo respetan siempre.

**29. Rate limit (tasa de cortesía).** Límite de peticiones por dominio para no
saturar los servidores: aquí, máximo 1 por segundo.

**30. Firecrawl.** Servicio que copia páginas web y las devuelve como texto
limpio. `collect_corpus.py` lo lanza para el corpus web.

**31. Scrapy.** Framework de rastreo web. El proyecto tiene un spider propio
(`scraper/scraper/spiders/deep.py`) como vía alternativa.

**32. Spider (araña).** Programa que recorre enlaces de una web automáticamente.
El `deep` salta rutas de tienda y login.

**33. Sitemap.** Mapa de URLs de un sitio web. `descubrir_fuentes.py` lo
recorre para encontrar páginas candidatas.

**34. Chunk (trozo).** Fragmento de texto indexado para buscarlo después.
`rag_index.py` trocea el corpus en chunks.

**35. Embedding.** Vector de números que representa el significado de un texto,
para poder comparar «parecido» con matemáticas. Aquí usa nomic-embed-text.

**36. RAG.** Generación aumentada por recuperación: buscar en el corpus trozos
relevantes y dárselos a la IA como contexto. `rag_index.py` monta ese índice.

**37. Similitud coseno.** Medida de cuánto se parecen dos embeddings (vectores).
Cuanto más cerca de 1, más parecidos. Es la búsqueda de `rag_index.py`.

**38. Deduplicado (dedupe).** Quitar elementos repetidos. El cierre de T121
deduplicó `consenso.jsonl` porque dos procesos escribieron el mismo fichero.

**39. Huella (hash SHA-256).** Firma única de un contenido: si cambia una
coma, la huella cambia. Sirve para detectar duplicados y verificar ficheros
(`descarga_clasicos_pd.py` guarda la SHA-256 de cada libro).

**40. jobs.db.** Base de datos SQLite con la cola de tareas de fase 1.
`generate_tasks.py` la llena (12.536 tareas) y `ejecutor_fase1.py` la consume.

**41. Worker.** Proceso que reclama tareas de la cola y las ejecuta. El viejo
`generate_synthetic.py` era un worker (suspendido).

**42. Reanudable.** Que un programa puede pararse y retomarse donde estaba, sin
repetir lo ya hecho. Casi todos los de fase 0 lo son (manifiestos, cachés).

**43. Snapshot (copia instantánea).** Copia de un fichero en un momento dado
para trabajar sobre ella mientras el original sigue creciendo.
`armar_dataset_v1.py` empieza con un snapshot de `aceptadas.jsonl`.

**44. Verificador determinista.** Comprobación por reglas fijas (sin IA): mismo
resultado siempre. `fase1_prompts.verificar_lectura` rechaza promesas vedadas,
cartas inventadas o formato roto.

**45. Lectura trabajada.** Consulta resuelta en un libro: cartas o carta natal
con pregunta explícita e interpretación desarrollada. Es la pieza más escasa
(T37 sacó 231).

**46. Carta natal.** Mapa del cielo en el momento y lugar de nacimiento. Lo
calcula `calculos/astro.py` y se usa en la familia astro_natal.

**47. Revolución solar.** Carta del cielo en el cumpleaños de cada año. La
calcula `calculos/astro.py`; familia revolucion_solar (398 filas en v1d).

**48. Tránsitos.** Posiciones planetarias actuales comparadas con la carta
natal. Familia transitos: 454 filas en v1d.

**49. Sinastria.** Comparación de dos cartas natales (parejas). Familia
sinastria: 577 filas en v1d.

**50. Biorritmos.** Ciclos teóricos físico/emocional/intelectual desde el
nacimiento. Los calcula `calculos/biorritmos.py`; familia biorritmos (382).

**51. Arcano mayor.** Las 22 cartas «grandes» del tarot (El Loco, La Luna…).
En la KB: `tarot-mayor-14` = Templanza.

**52. Arcano menor.** Las 56 cartas restantes, en cuatro palos (copas, oros,
espadas, bastos).

**53. Palo.** Cada una de las cuatro familias de naipes: copas, oros, espadas,
bastos. En baraja española, 10 cartas por palo.

**54. Invertida.** Carta que sale del revés; cambia matices de su
significado. Los subtítulos de YouTube dicen «la reina de copas invertido» y
`cartas.py` lo normaliza.

**55. Línea base (baseline).** Nota de un modelo sin entrenar, para comparar.
T99: Flash Next sin ajustar sacó 179/240 (74,6 %).

**56. TTR (vocabulario variado).** Ratio de palabras únicas sobre el total:
mide riqueza léxica. El train de v1d tiene TTR 0,0048.

**57. n-grama (4-grama, 6-grama).** Secuencia de n palabras seguidas. Se usa
para medir frases repetidas: en v1d las muletillas de 6-gramas bajaron a 4.

**58. Muletilla.** Frase que se repite demasiado entre lecturas y delata
plantilla. `diversidad_dataset.py` las caza (≥0,5 % de ocurrencia).

**59. Fuga (data leakage).** Que datos reservados (test o casos de evaluación)
se cuelen en el entrenamiento y falseen la nota. El QA de v1d: 0 fugas.

**60. Backend rápido.** Motor de IA en la nube barato y veloz (Mercury 3) para
pasadas masivas. Se comparó con el nodo local en T65/T68.
