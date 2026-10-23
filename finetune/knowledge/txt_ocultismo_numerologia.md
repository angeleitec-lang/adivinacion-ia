# TXT ocultismo y numerología (T133)

## Procedencia

- **Diccionario de las ciencias ocultas** (Papus / Gérard Encausse, «El Tarot de los Bohemios», ed. 1889 aprox.): apuntes TXT del usuario (OCR de archive.org), uso interno, derechos por revisar. Fichero: `_txt/diccionario_ciencias_ocultas_djvu.txt` (73.020 líneas). Época: **clásica** (`periodo="clasica"`).
- **Numerología Fácil** (portada © Heloísa Galves; la serie atribuye el texto a Regina Maria Azevedo), portugués: apuntes TXT del usuario (OCR de archive.org), uso interno, derechos por revisar. Fichero: `_txt/numerologia_facil_djvu.txt` (5.070 líneas). Época: **moderna** (`periodo="moderna"`).

Ningún texto fuente se copia al repo. Datos pesados en `/Users/angelgonzalez/fase0/txt_ocultismo_numerologia/`.

## Pipeline

`finetune/corpus/txt_ocultismo_numerologia.py` (reutiliza sin modificar `juez`, `afirmaciones_libros`, `libros_comprados_baraja`, `consenso_kb`, `cartas`).

### Diccionario (español, clásica)

- Entradas = `CABECERA — definición` (regex mayúsculas + raya U+2014). Excluye front matter (≤ l.610), cabeceras de página (2-4 letras) y cuadro sinóptico de -mancias (minúsculas).
- Limpieza OCR: unión de guiones de sílaba (`-`/`¬` final), números de página sueltos.
- Filtro de calidad: `corta` (<40 car.) e `ilegible` (<72 % letras). Tope `exceso_longitud` >4.000 car. (rechaza p. ej. TEOSOFÍA, que traga un ensayo).
- Filtro de familias por términos estrictos (norm sin tildes, word-boundary): tarot, numerología, astrología, naipes, adivinación. Prioridad: tarot > numerología > astrología > naipes > adivinación.
- Solo las entradas con candidatos deterministas de la KB van al juez LLM; el resto a `sin_entidad` (sin LLM).

### Numerología (portugués, bypass del juez)

- Colapso de espacios dobles del OCR; secciones por número (1-9) y maestros (11, 22; el 33 no tiene sección propia en el libro).
- Dos bloques por número: `general` (Palavras-chave + párrafo) → faceta `significado_general`; `sombra` (positivas/negativas/missão o virtudes/desafíos) → faceta `luz_sombra`.
- Evidencias deterministas: cada bloque × 6 posiciones canónicas (`alma, anio_personal, camino_de_vida, destino, mes_personal, personalidad`) = 132 evidencias (calidad 4, tipo libro, idioma pt).

## Cifras (ejecución 2026-10-23, nodo2 halogen, ≤2 workers)

| Concepto | Valor |
|---|---|
| Entradas diccionario | 1.191 |
| Rechazo calidad `corta` | 150 |
| Rechazo `exceso_longitud` | 96 |
| Pasan filtro de familia | 287 (astro 187, adivinación 59, naipes 19, numerología 18, tarot 4) |
| Con candidatos KB → juez | 54 |
| `sin_entidad` (sin LLM) | 199 |
| Juez: conocimiento / otro | 52 / 2 |
| Evidencias diccionario | 31 |
| Bloques numerología | 22 (números 1-9, 11, 22) |
| Evidencias numerología | 132 |
| Afirmaciones diccionario | 103 |
| Afirmaciones numerología | 592 |
| **Total afirmaciones** | **695** |
| Llamadas LLM (juez 54 + extracción 163) | 217 |
| Descartadas anti-copia (>25 palabras) | 0 |
| Errores | 0 |

Salida: `fase0/txt_ocultismo_numerologia/afirmaciones/afirmaciones_txt_ocultismo.jsonl` (695 líneas). Rechazos: `rechazos/calidad.jsonl` (246), `rechazos/sin_entidad.jsonl` (199).

## Delta de cobertura

- **Numerología**: las 72 entidades (`12 números × 6 posiciones`) reciben por primera vez una fuente moderna en portugués con `significado_general` y `luz_sombra` (familia con menos cobertura hasta ahora: 6 de 792 celdas del plan).
- **Astrología (clásica)**: signos, planetas en signo y correspondencias/floras simbólicas desde Papus (facetas `simbolismo`, `correspondencias`), época clásica — complementa la fuente moderna.
- **Tarot**: 4 entradas clásicas con candidatos de arcanos mayores.

## Comandos

```bash
V=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
M=finetune/corpus/txt_ocultismo_numerologia.py
W=/Users/angelgonzalez/fase0/txt_ocultismo_numerologia
$V $M --work-dir $W --segmentar      # segmentación + filtros (sin LLM)
$V $M --work-dir $W --determinista   # 132 evidencias numerología (sin LLM)
$V $M --work-dir $W --dry-run       # estimación de llamadas
$V $M --work-dir $W --juez --workers 2          # 54 secciones dicc (nodo2)
$V $M --work-dir $W --afirmaciones --workers 2  # reanudable, numerología primero
```

Endpoints por defecto: `http://10.0.0.4:8000/v1` (nodo2). El módulo rechaza nodo1. Reanudación por `(hash_seccion, entidad_id, faceta)` vía fichero de salida + `afirmaciones/procesadas.jsonl`.
