# T132 — TXT de naipes y tarot del usuario (OCR de archive.org)

Pista T132. Tres TXT ya extraídos por OCR (djvu) que el usuario tiene en
`/Users/angelgonzalez/adivinacion-ia/_txt/`, procesados por un módulo propio
(`finetune/corpus/txt_naipes_tarot.py`) que reutiliza la tubería de libros
(`juez.py`, `afirmaciones_libros.py`, `libros_comprados_en.py`) **sin
modificarla**. Work-dir: `/Users/angelgonzalez/fase0/txt_naipes_tarot/`.

Procedencia: **apuntes TXT del usuario (OCR de archive.org), uso interno,
derechos por revisar** (regla del proyecto: la legalidad se revisa más tarde;
cada fuente conserva su hint).

## 1. Fuentes

| id | título | año | estado |
|---|---|---|---|
| `altaya_naipes` | *Los naipes y sus secretos* (Altaya) | ~1985 | **incluida** |
| `compendium_tarot_mexicanus` | *Compendium Tarot Mexicanus* | 2025 | **incluida** |
| `ricart_1838` | *Relación de la baraja* (Miguel Ricart, 1838) | 1838 | **EXCLUIDA** |

### Ricart 1838 — exclusión por OCR no recuperable

Medida de calidad (`medir_calidad`, ratio = tokens ≥3 letras puras / total):
12 463 tokens, ventanas de 40 líneas con **densidad máxima 0.58** y **cero
ventanas > 0.6**. El texto es un romance/alegoría en verso del s. XIX (relato
picaresco con la Baraja como hilo), **no un manual cartomántico**: las menciones
limpias a naipes son casi nulas por el ruido OCR (`as de oro`: 1, `rey de`: 1,
`copas/espadas/bastos/sota/caballo`: 0). No hay material aprovechable para la
KB. Queda registrado en `knowledge/fuentes_txt_naipes.jsonl` con
`incluido: false` y `motivo_exclusion`.

## 2. Limpieza y calidad

`limpiar()` = unir hifenación de fin de línea (`pal-\nabra` → `palabra` cuando la
siguiente inicia en minúscula) + quitar líneas de basura por fuente:

- **Altaya**: running header «LOS NAIPES Y SUS SECRETOS» (variantes OCR con
  barras/`1`/`0`), fragmentos sueltos (`NAIPES`, `Y SUS SECRETOS`,
  `LOS NAIPES`) y números de página sueltos.
- **Compendium**: cabecera `N|COMPENDIUM TAROT MEXICANUS` + set exacto de
  títulos de capítulo y nombres de autoría en mayúsculas.

Ratio real de palabras antes → después:

- Altaya: 0.674 → **0.682** (4 621 líneas limpias)
- Compendium: 0.677 → **0.675** (8 596 líneas limpias)

La ganancia es modesta porque el OCR ya venía razonable; la limpieza sobre todo
elimina cabeceras repetidas y reconstruye palabras partidas, que es lo que
importa para las citas.

## 3. Segmentación y mapeo a la KB

Regla dura del proyecto: **baraja española y naipes franceses no se mezclan**.
El Altaya trata barajas latinas **y** francesas/poker en los mismos capítulos,
por eso solo los arcanos se mapean de forma determinista a `tarot-mayor-*`;
los capítulos mixtos se dejan sin entidad para que el juez LLM decida por
cuerpo (y nunca se mapean a `naipe-*` de forma automática).

### Altaya (33 secciones)

- 7 capítulos de figuras/numerales + introducción + introducción de arcanos:
  `entidad_id = None`, `motivo_sin_entidad = capitulo_mixto_no_carta` (o
  `capitulo_general_no_carta` para la intro general), `sistema = mixto`.
- 22 capítulos de arcanos (orden Rider-Waite con El Loco al final):
  `entidad_id = cartas.normalizar_carta(nombre, 'tarot')` →
  `tarot-mayor-01..22`, `metodo = cabecera`, `confianza = alta`.
- La mención «LA JUSTICIA» de la introducción de arcanos (discusión de la
  numeración) **no** se segmenta como capítulo: el cursor de arcanos arranca
  tras la introducción, así que queda dentro de `intro_arcanos`.
- Capítulos largos troceados por párrafos a ≤ 5 500 chars (límite del prompt
  del juez/extractor), mismo `entidad_id`, título «(parte N)».

### Compendium (76 secciones)

5 ensayos académicos (Frieda Harris/Thoth, Tiradas Sagradas, Tetramorfos y
Merkabá, Tarot 2020-2024, Cartomancia en México). Sin mapeo determinista por
capítulo (`motivo_sin_entidad = ensayo_sin_carta_determinista`,
`sistema = tarot`); el juez extrae candidatos por cuerpo (El Loco y otros
arcanos aparecen citados con simbolismo útil, p. ej. Crowley sobre el Aire).
El TOC (líneas < 400) se ignora; se descartan bloques de bibliografía,
referencias, agradecimientos y notas biográficas.

## 4. Etapas LLM (nodo2, ≤ 2 workers)

Todo el LLM va **solo a nodo2** (`http://10.0.0.4:8000/v1`); el módulo rechaza
cualquier endpoint que contenga `10.0.0.3` (nodo1 reservado). Lotes reanudables
por hash.

1. **Juez de relevancia** (`--juez`): 60 secciones con candidatos →
   Altaya 25 juzgadas / 51 evidencias / 0 errores; Compendium 35 juzgadas /
   199 evidencias / 0 errores (1 sección falló 2 veces por JSON inválido del
   modelo — «Campo tipo ausente» — y salió a la tercera).
2. **Extracción de afirmaciones** (`--afirmaciones`): 250 evidencias →
   afirmaciones en español con `cita_original` (≤ 25 palabras) vía
   `afirmaciones_libros.main`.
3. **Auditoría anti-copia** (`--auditar`): `libros_comprados_en.es_copia`
   comparando `afirmacion` y `cita_original` contra el texto limpio de cada
   fuente; lo que comparte ≥ 26 palabras consecutivas se mueve a
   `afirmaciones/rechazadas_copia.jsonl` con `motivo_rechazo`.
4. **Fusión** (`--fusionar`): lo no rechazado se copia a
   `afirmaciones/afirmaciones_txt_naipes.jsonl` con la `procedencia` añadida.

## 5. Cifras finales (cierre 2026-10-23)

- Secciones juzgadas: **60** (25 Altaya + 35 Compendium), 0 errores tras
  reintentos (una sección del Capítulo IV falló 2 veces por JSON inválido del
  modelo y salió a la tercera con `--workers 1`).
- Evidencias del juez: **250**.
- Afirmaciones extraídas: **746** (0 errores; 2 marcadas `contradice_kb`).
  - Por familia: tarot 639, baraja española 57, astrología 50.
  - Descartes del extractor: otra_carta 372, cita_no_textual 118,
    exceso_cita 97, deictica 18, exceso 3, vocabulario 1.
- Rechazadas por copia > 25 palabras: **0** (la puerta anti-copia no encontró
  n-gramas de 26 palabras compartidos).
- Fusionadas en `afirmaciones/afirmaciones_txt_naipes.jsonl`: **746** con
  `procedencia` añadida.
- Muestras verificadas a mano: **20/20 correctas** (paráfrasis de 1-2 frases
  completas terminadas en punto, `cita_original` verbatim ≤ 25 palabras, sin
  recortes; detalle en `ESTADO.md`).

## 6. Comandos

```bash
VENV=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
MOD=finetune/corpus/txt_naipes_tarot.py   # desde la raíz del worktree

$VENV $MOD --preparar --limpiar --segmentar --cobertura
$VENV $MOD --juez --endpoints http://10.0.0.4:8000/v1 --workers 2
$VENV $MOD --afirmaciones --endpoints http://10.0.0.4:8000/v1 --workers 2
$VENV $MOD --auditar
$VENV $MOD --fusionar
```

Reanudable: el juez repite solo las secciones con juicio `tipo=error`; las
afirmaciones se reanudan por `procesados.jsonl` (clave
`hash_seccion,entidad_id,faceta`).

## 7. Delta de cobertura estimado

- Altaya aporta **22 arcanos** con entidad directa (facetas de
  significado/simbolismo/historia por capítulo, hasta 12 facetas por carta →
  techo teórico 264 afirmaciones) más candidatos de baraja latina en los
  capítulos mixtos que el juez puede rescatar.
- Compendium aporta simbolismo de arcanos (especialmente El Loco vía Crowley y
  correspondencias hebreo-arcanos de Tiradas Sagradas) y contexto histórico de
  la cartomancia en México; sin baraja española.
- No se toca la matriz v3 real desde esta pista; la fusión global la decide la
  coordinadora.
