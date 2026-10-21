# Revisión humana de la muestra del 3 % (v2, sobre datos vigentes)

La muestra anterior (`/Users/angelgonzalez/fase0/muestras/`) se generó **antes** de la
limpieza de libros (T71), del filtro de atribución (T88), del consenso, de la KB v2 y de
las evidencias nuevas. Esta versión (T93) se rehace sobre los datos actuales, en un
directorio nuevo: **`/Users/angelgonzalez/fase0/muestras_v2/`**. No se usó ningún LLM:
todo el filtrado previo es determinista.

## Cómo empezar

1. Abre `/Users/angelgonzalez/fase0/muestras_v2/revisor.html` en el navegador (doble
   clic o `open`). Es un único fichero autocontenido, sin conexión ni dependencias.
2. Las decisiones se guardan solas en el navegador (localStorage, clave
   `revisor-muestras-v2`): puedes cerrar y reanudar donde lo dejaste.
3. Al terminar cada sesión —o si cambias de equipo— pulsa **Exportar decisiones**:
   descarga `muestras_revisadas.jsonl` (una fila por ficha revisada con
   `id`, `veredicto`, `nota` y `nivel`). Guarda ese fichero en
   `/Users/angelgonzalez/fase0/muestras_v2/`. Para continuar en otro sitio, abre el
   revisor y pulsa **Importar decisiones** seleccionando ese fichero.

## Atajos

| Tecla | Acción |
|---|---|
| `1` / `2` / `3` | Veredicto: correcto / dudoso / incorrecto |
| `←` o `K`, `→` o `J` | Ficha anterior / siguiente |
| `N` | Escribir nota en la ficha actual |
| `U` | Deshacer la última decisión |
| `S` | Saltar (sin veredicto) |

Arriba hay filtros: por **nivel**, por **origen**, por banderas y «solo sin revisar».
Las fichas salen ordenadas por sospecha (las marcadas primero).

## Qué contiene la muestra (semilla 42, fracción 0,03, estratificada)

| Nivel | Muestra | Corpus | Origen de los datos |
|---|---|---|---|
| web | 754 | 25 193 | evidencias web (evidencias_web/) |
| libros | 447 | 14 221 | evidencias de libros ya limpiados (T71/T88) |
| afirmaciones | 5 645 | 187 787 | nodo local · web: 3 012 · nodo local · libros: 914 · rápido (mercury-3) · web: 927 · rápido (mercury-3) · libros: 792 |
| lecturas | 16 | 231 | lecturas de ejemplo |
| consenso | 120 | 3 688 | celdas de consenso_kb/ + confianza de kb_v2/ |
| **Total** | **6 982** | **231 120** | |

Cada ficha lleva una etiqueta de **origen** (web (evidencia), libro (evidencia), nodo
local · web/libros, rápido (mercury-3) · web/libros, libro · lectura, consenso · kb_v2)
para poder juzgar distinto según de dónde viene el dato. Las afirmaciones rápidas
(generadas con mercury-3) están incluidas y se identifican en el revisor.

Las **celdas de consenso** muestran la ficha completa de la entidad: afirmaciones
mayoritarias (con fuentes y tradiciones), discrepancias (A — B), aportaciones de una
sola fuente y alertas fácticas, además de la confianza asignada en la KB v2 (alta /
media / baja) y la forma de la celda. En la muestra hay: 58 astrología, 30 tarot,
17 numerología, 15 baraja española; 29 de confianza alta, 76 media, 15 baja; 47 celdas
solo con aportación única, 25 mayoritaria+única, 23 con todo, etc. Aquí conviene mirar
sobre todo si la mezcla es coherente y si la confianza parece adecuada.

## Prerevisión determinista

659 de 6 982 fichas llevan alguna marca (**9,4 %**). Por nivel:

| Nivel | Marcadas | Porcentaje | Banderas dominantes |
|---|---|---|---|
| web | 284 | 37,7 % | sin_texto 219, mojibake 39, ruido_comercial 26 |
| libros | 235 | 52,6 % | no_espanol 230, texto_corto 5 |
| afirmaciones | 125 | 2,2 % | otra_carta 68, duplicada 52, promesa_vedada 5 |
| lecturas | 10 | 62,5 % | no_espanol 10 |
| consenso | 5 | 4,2 % | otra_carta 5 |

Qué significa cada bandera:

- **sin_texto**: la evidencia web no encuentra su sección origen (hash no resuelve).
  Revisa si la ficha es recuperable o hay que retirarla.
- **mojibake / ruido_navegacion / ruido_comercial**: texto con caracteres corruptos o
  restos de la página (menús, publicidad).
- **no_espanol**: el texto está en otro idioma. Ojo: los libros clásicos en inglés
  (Waite, Minetta…) siguen vigentes tras T71 —la limpieza fue de **atribución**, no de
  idioma—, así que esta marca en libros es real y la decisión (traducir citas o
  retirarlas) te corresponde a ti.
- **texto_corto**: fragmento sospechosamente breve (umbral 80 caracteres; 20 en
  afirmaciones y 40 en celdas de consenso, que son listas de frases cortas).
- **otra_carta**: el texto describe una carta/entidad distinta de la del registro.
- **promesa_vedada**: promesas de resultado literal (curar, garantizar amor en fecha…),
  prohibidas en las lecturas.
- **duplicada**: repetida en el corpus (grupo entidad+faceta).
- **contradiccion_kb**: atribución de elemento/palo que choca con la KB
  (solo afirmaciones y consenso).

## Cuánto tiempo

A 3–5 s por ficha, la muestra completa son unas **6–10 horas**. Alternativa razonable:
revisar solo las 659 marcadas (están primero con el filtro «solo marcadas»), unos
**40 minutos**, y dar un muestreo rápido del resto. El trabajo se guarda en el
navegador, así que puedes por partes sin coste.

## Ficheros del directorio

- `revisor.html` — la herramienta de revisión (esto es lo que se abre).
- `muestras.md` / `muestras.jsonl` — la muestra en formato legible y máquina.
- `prerevision.md` / `prerevision.jsonl` — informe y fichas de banderas.
- `muestras_revisadas.jsonl` — lo que produces al exportar (no existe hasta la
  primera exportación).

Regenerar todo (sin LLM, desde la raíz del repo):

```sh
P=finetune/.venv/bin/python
$P finetune/corpus/muestras.py --accion muestrear --base /Users/angelgonzalez/fase0 \
   --out-dir /Users/angelgonzalez/fase0/muestras_v2 --fraccion 0.03 --semilla 42
$P finetune/corpus/prerevision.py --muestras /Users/angelgonzalez/fase0/muestras_v2/muestras.jsonl \
   --base /Users/angelgonzalez/fase0 --out-dir /Users/angelgonzalez/fase0/muestras_v2
$P finetune/corpus/revisor_local.py --muestras /Users/angelgonzalez/fase0/muestras_v2/muestras.jsonl \
   --prerevision /Users/angelgonzalez/fase0/muestras_v2/prerevision.jsonl \
   --base /Users/angelgonzalez/fase0 --out /Users/angelgonzalez/fase0/muestras_v2/revisor.html
```
