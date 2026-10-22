# T129 — Libros de baraja española COMPRADOS (Salas y Tiradas), preparación determinista

## Procedencia y uso (importante)

- Los dos PDF son **ejemplares comprados por el usuario** (carpeta
  `/Users/angelgonzalez/fase0/libros_comprados/`). **Tienen copyright.**
- Uso exclusivo: consulta interna para construir el dataset de entrenamiento.
  Procedencia registrada en cada fuente: `comprado por el usuario, uso interno,
  libro con copyright` (metadatos: `origen=comprado_por_usuario`,
  `licencia_hint=libro con copyright, uso interno`).
- Los textos extraídos y todo el material derivado viven en
  `/Users/angelgonzalez/fase0/libros_comprados_baraja/` y **NUNCA** se copian al
  repo, a `corpus/final` ni a ningún sitio público. En el repo solo quedan este
  informe, el script y sus tests.
- Los PDF **no** se copian al repo: el script los lee desde
  `/Users/angelgonzalez/fase0/libros_comprados/`.

## Fuentes

| id | título | autor | idioma | PDF | páginas |
|---|---|---|---|---|---|
| `libro_salas_baraja` | *El arte de echar las cartas* | Salas | es | `Salas - El arte de echar las cartas.pdf` | 25 |
| `libro_tiradas_baraja_espanola` | *Tiradas de cartas españolas* | Anónimo | es | `TiradasDeCartasEspanolas.pdf` | 20 |

- Año desconocido en ambos ejemplares (`anio=None`).
- Capa de texto nativa (Word → PDF), sin OCR. Extracción con
  `/opt/homebrew/bin/pdftotext -layout` y caché en `crudo/<corto>.txt`
  (`salas.txt`, `tiradas.txt`). No se reprocesa si el fichero supera 1 KiB.
- `libro_tiradas_baraja_espanola` describe **48 naipes** (12 por palo, incluidos
  Ocho y Nueve), aunque el título hable de tiradas: el grueso del texto son
  significados por carta y orientación, no posiciones de tirada.

## Estructura detectada

### Salas

- 48 encabezados en mayúsculas sostenidas: `AS DE OROS` … `REY DE ESPADAS`,
  en orden oros → copas → espadas → bastos, 12 rangos por palo.
- 96 marcadores `AL DERECHO:` / `AL REVÉS:` (con variante OCR `ÁL DERECHO:`).
- Cada sección = carta + orientación. Las listas iniciales de palabras clave
  («Felicidad. Prosperidad. Triunfo…») forman parte del significado.
- Las menciones en prosa minúscula («al revés, pronostica infamia.») **no** se
  confunden con marcadores: el parser exige línea que empiece por el marcador y
  encabezado de carta a línea completa en mayúsculas.

### Tiradas de cartas españolas

- Páginas 1–2: método de palos (OROS/COPAS/BASTOS/ESPADAS con temas, signos y
  estaciones). Son **método**, no significado de carta; se guardan aparte en
  `secciones/metodo_libro_tiradas_baraja_espanola.jsonl` (22 líneas).
- Oros y Bastos: 12 encabezados explícitos por palo, de As a Rey.
- Espadas: encabezado **inline** («As de Espadas. Al derecho, …»).
- Copas: sin encabezados. Los bloques «Al derecho… / Al revés…» se asignaron
  por orden documental usando la **numeración impresa de las ilustraciones**
  (verificado visualmente: 1 = As de Copas, 2–12 = Dos a Rey). El bloque
  huérfano de la página 6, situado antes de «Rey de Oros», es el **As de Copas**;
  los 11 bloques siguientes continúan Dos … Rey.
- Notas de método («* Para saber si está del revés…», «* Estará del revés
  cuando el palo…») y ruido de página («Elige un tema y haz tu consulta»,
  `</di.<>`) se descartan del significado.
- Las tiradas/posiciones **no** se convierten en significado de carta: el método
  queda separado. Baraja española y naipes franceses no se mezclan en ningún
  momento.

## Mapeo a la KB: 48 naipes → 40 entidades

`finetune/corpus/kb/baraja_espanola.json` y `cartas.NAIPES_ESPANOLES` tienen
**40 naipes**: As–Siete + Sota (numero 8), Caballo (9) y Rey (10), con ids
`naipe-<palo>-<NN>` (`01`–`07`, `08` Sota, `09` Caballo, `10` Rey) y palo en
minúsculas (`oros`, `copas`, `espadas`, `bastos`).

- El mapeo se hace por **(rango, palo)**, nunca por número asumido.
- Los libros traen también **Ocho** y **Nueve** (12 por palo). Esos 16 naipes
  (2 rangos × 8 orientaciones × 2 libros) **no existen en la KB**: se guardan en
  `secciones/sin_entidad_<id>.jsonl` con
  `motivo_sin_entidad=rango_ocho_ausente_en_kb` o
  `rango_nueve_ausente_en_kb`, y no generan evidencias.
- Resultado: 48 cartas por libro, 80 secciones con entidad (40 cartas × 2
  orientaciones) y 16 sin entidad.

## Salidas (fase0, fuera del repo)

```
/Users/angelgonzalez/fase0/libros_comprados_baraja/
├── crudo/                 salas.txt, tiradas.txt
├── limpio/
├── secciones/
│   ├── libro_salas_baraja.jsonl                 96 secciones
│   ├── libro_tiradas_baraja_espanola.jsonl      96 secciones
│   ├── sin_entidad_<id>.jsonl                   16 secciones c/u
│   └── metodo_libro_tiradas_baraja_espanola.jsonl
├── evidencias/
│   └── evidencias_baraja.jsonl                  320 evidencias
├── afirmaciones/
│   └── afirmaciones_baraja.jsonl                320 afirmaciones
├── knowledge/
│   └── fuentes_libros_comprados_baraja.jsonl    2 fuentes con procedencia
└── resumenes/
    ├── segmentacion.json
    ├── determinista.json
    └── cobertura.json
```

Cada sección lleva: `id_libro`, `fuente_id`, `seccion`, `titulo`, `texto`,
`chars`, `posicion`, `entidad_id`, `motivo_sin_entidad`, `rango`, `palo`,
`orientacion` (`derecho`/`reves`), `idioma`, `metodo`, `confianza` y `pagina`.

## Resultados

- Segmentación: **96 secciones por libro** (48 derechos + 48 reveses), 80 con
  entidad y 16 sin entidad (Ocho/Nueve), **0 incidencias**.
  - Salas: 48 cartas, 0 líneas de método.
  - Tiradas: 48 cartas, 22 líneas de método separadas.
- Determinista (sin LLM): **160 evidencias y 160 afirmaciones por libro**
  (320 + 320 en total), **0 afirmaciones rechazadas**.
- Facetas asignadas por orientación:
  - derecho → `significado_general`, `derecha_invertida`
  - revés → `derecha_invertida`, `luz_sombra`
- Anti-copia: se rechaza cualquier afirmación con **más de 25 palabras
  consecutivas** idénticas al libro. La afirmación se construye con plantilla y
  un núcleo de ≤14 palabras; la cita textual se limita a 20 palabras.
- Cobertura de orientaciones: **40/40 cartas con derecho y 40/40 con revés**
  en cada libro y en el combinado; 0 faltantes.
- Delta sobre `cobertura_v3` (base: 39 419 evidencias de
  `/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl` +
  `/Users/angelgonzalez/fase0/libros_limpio/evidencias_limpias.jsonl`):
  - Baraja española antes: 480 celdas, **39 completas**.
  - Después: 480 celdas, **39 completas**.
  - Motivo: `calcular_cobertura` exige 5 fuentes independientes + 1 clásica;
    estos libros aportan **una** fuente moderna en español por celda, así que
    suman cobertura de fuentes pero no completan celdas nuevas. Es el resultado
    esperado con una sola fuente nueva.

## Regenerar (sin LLM)

```bash
cd /Users/angelgonzalez/adivinacion-ia
finetune/.venv/bin/python finetune/corpus/libros_comprados_baraja.py \
  --preparar --segmentar --dry-run
finetune/.venv/bin/python finetune/corpus/libros_comprados_baraja.py \
  --determinista
finetune/.venv/bin/python finetune/corpus/libros_comprados_baraja.py \
  --cobertura
```

Tests:

```bash
cd finetune/corpus
../.venv/bin/python -m unittest tests.test_libros_comprados_baraja
```

## Fase LLM (documentada, NO ejecutada en T129)

No se lanzó ninguna llamada real: nodo1 (10.0.0.3) está reservado y nodo2
(10.0.0.4) estaba ocupado por T125 con 3 workers. El cliente del módulo rechaza
explícitamente cualquier endpoint de nodo1.

Comandos previstos, solo cuando nodo2 quede libre y el usuario lo autorice:

```bash
cd /Users/angelgonzalez/adivinacion-ia
# Juez: secciones -> juicios.jsonl + evidencias.jsonl (reanudable)
finetune/.venv/bin/python finetune/corpus/libros_comprados_baraja.py \
  --juez --endpoints http://10.0.0.4:8000/v1 --workers 2

# Afirmaciones: evidencias -> afirmaciones_llm.jsonl (reanudable)
finetune/.venv/bin/python finetune/corpus/libros_comprados_baraja.py \
  --afirmaciones --endpoints http://10.0.0.4:8000/v1 --workers 2
```

- `--limite N` permite una prueba corta.
- `--workers 2` por defecto (`MAX_WORKERS=2`); no subir sin comprobar la carga
  de nodo2.
- La etapa LLM escribe en `evidencias/evidencias.jsonl` y
  `afirmaciones/afirmaciones_llm.jsonl`; no pisa las salidas deterministas
  (`evidencias_baraja.jsonl`, `afirmaciones_baraja.jsonl`).

## Limitaciones conocidas

- Ocho y Nueve no tienen entidad en la KB actual: quedan documentados en las
  secciones `sin_entidad_*` para una futura ampliación de la KB, pero no cuentan
  como evidencia.
- En Tiradas, la asignación de Copas es ordinal y se apoya en la numeración
  impresa de las ilustraciones (confianza alta), no en encabezados de texto.
- La afirmación determinista es una paráfrasis plantilla de las claves del
  libro; sirve para cobertura y como material de trabajo, no sustituye a la
  redacción final del dataset.
