# Greene — «Saturn: A New Look at an Old Devil» (T130)

## Ficha

- Autor: Liz Greene. Título: *Saturn: A New Look at an Old Devil*.
- Edición: primera edición 1976 (Red Wheel/Weiser); reimpresión Llewellyn
  ISBN 978-1-57863-507-8. `id_libro = greene_saturn_1976`, idioma `en`.
- Procedencia: PDF comprado por el usuario en
  `/Users/angelgonzalez/fase0/libros_comprados/`; uso interno, libro con
  copyright. **Nunca** copiar el PDF ni texto del libro al repositorio.
- Módulo: `finetune/corpus/libro_comprado_greene.py` (tests en
  `tests/test_libro_comprado_greene.py`, 33 unittest). Work-dir de datos:
  `/Users/angelgonzalez/fase0/libros_comprados_greene/`.
- Reutiliza sin tocar: `libros_comprados_prep` (OCR/limpieza T118) y
  `libros_comprados_astro` (mapeo a celdas, juez, anti-copia T119).

## Alcance

Solo celdas ya existentes en `cobertura.entidades()`:
`saturno|<signo>|planeta_en_signo`, `saturno|casa<N>|planeta_en_casa` y
`p1|<aspecto>|p2|aspecto` con saturno. No se crean entidades nuevas.

## Extracción

- El escaneo (202 pp., una página por hoja) **no tiene capa de texto útil**:
  solo 11/202 páginas traen texto real (preliminares y colofón); el resto son
  marcas de imprenta (`45173`, `TXT49`, `*_TXT.indd`, fechas/horas). Informe:
  `limpio/capa_texto_informe.json`.
- OCR con tesseract 300 dpi, **psm=3** (muestreo psm 3/4/6 sobre páginas de
  muestra; 3 y 4 empatan y 6 es peor). 202/202 páginas, 0 en blanco, 294 s en
  CPU local (iMac, `nice`). Caché reanudable por página: `ocr/pNNN.txt`.

## Calidad del texto limpio (`--limpiar`)

`limpio/greene_saturn.txt`: 492 255 chars (7601 líneas).
Informe `limpio/greene_saturn_1976_informe.json`: vocabulario 87.54 % antes →
88.56 % después; palabras pegadas (glued) 3111; 16 rúbricas detectadas y
retiradas; 858 líneas de imprenta eliminadas (filtro `RE_IMPRENTA` + regla de
≥2 tokens reales); guiones silábicos: 65 unidos, 58 conservados, 22 forzados.

## Segmentación y dry-run (`--segmentar`, `--dry-run`)

Segmentación **por cabecera** (el OCR no preserva párrafos; los bloques se
trocean por oraciones a ~2500 chars):

- Capítulos 1–4: cabeceras «Saturn in <signo> and the <ord> house» (a veces
  partida en dos líneas OCR) → 12 secciones signo+casa conjuntas.
- Capítulo 5: cabeceras «Saturn in aspect (to the <planeta>)». El OCR suele
  perder la línea «to the X»: el planeta se **infiere por frecuencia** en el
  trozo (`inferir_planeta`) y queda pegado al contexto.
- Capítulo 6 (sinastria) y 7 (conclusión) no dejan cabecera superviviente: se
  abren por **marcadores** de primera frase y en ellos **se filtran los
  aspectos** (el lenguaje es sinastrico/natal mixto y generaría celdas
  falsas); solo pasan menciones explícitas de signo/casa.

Cifras: **208 secciones** (todas con candidatos del juez), 226 trozos, 120
trozos sin celda (hueco), **46 celdas distintas** de las 69 de Saturno en el
catálogo. Por tipo: 86 planeta_en_signo, 88 planeta_en_casa, 34 aspecto.
Hueco por capítulo: inicio 14, watery 5, earthy 5, airy 3, fiery 2, aspectos
intro 3 + por planeta 33, sinastria 44, conclusion 6.

Estimación LLM: juez ≈ **208 llamadas** (1 por sección); afirmaciones ≈
**83–166** (0.4–0.8 × secciones, depende de las facetas que apruebe el juez).

## Celdas Saturno SIN refuerzo (23 de 69)

Todas son de aspecto (los 12 signos y 12 casas sí quedan cubiertos):
`sol|sextil`, `luna|cuadratura/sextil/trigono/oposicion`,
`mercurio|conjuncion/sextil/trigono`, `marte|conjuncion/sextil/trigono`,
`jupiter|conjuncion`, y con Urano/Neptuno/Plutón: `conjuncion`,
`cuadratura` (Neptuno, Plutón), `sextil`, `trigono`, `oposicion`
(Neptuno, Urano) — Greene no nombra esos aspectos en los capítulos
correspondientes.

## HUECOS documentados (sin celda destino en el catálogo)

1. **El libro NO tiene capítulo de tránsitos ni retornos de Saturno** (el
   planteamiento del track los asumía; el índice real es: Foreword,
   Introduction, caps. 1–4 signos/casas por elemento, cap. 5 aspectos,
   cap. 6 sinastria, cap. 7 conclusión). Si se quisieran tránsitos habría que
   ir a otra fuente.
2. **Sinastria** (cap. 6, ~46 pp.): sin celdas de comparación entre cartas
   en el catálogo; se extrajo solo como hueco con menciones de signo/casa.
3. Prólogo/introducción/conclusión: arquetipo holístico, sin celda.
   Precedente T119 §5: no crear entidades; pista aparte si se decide.

## Comandos EXACTOS de las etapas LLM (aplazadas por presupuesto)

Nodo1 (10.0.0.3) está **reservado**; LLM solo nodo2. En el momento de este
track T125 ocupa nodo2 con 3 workers, así que **no se lanzó ninguna llamada**.
El `main()` del módulo bloquea hoy estas banderas (devuelve 3) por el
presupuesto de T130: cuando el usuario autorice, basta con retirar el guardón
en `main()` (dos líneas) y lanzar en tramos:

```sh
cd /Users/angelgonzalez/adivinacion-ia/finetune/corpus
# Juez (≈208 llamadas): por tramos de 50 con --max-llamadas
python libro_comprado_greene.py --juez \
  --endpoints http://10.0.0.4:8000/v1 --workers 2 --max-llamadas 50
# (repetir hasta juzgar las 208; reaprovecha hashes ya juzgados)
# Afirmaciones (faceta a faceta de las evidencias aprobadas):
python libro_comprado_greene.py --afirmaciones \
  --endpoints http://10.0.0.4:8000/v1 --workers 2
```

Smoke test sin red antes de lanzar: `--juez --simulado` (tras quitar el
guardón). Puerta anti-copia: afirmaciones con ≥25 palabras consecutivas igual
al libro se descartan (`copia_rechazada` en stats).

## Fusión

Cuando existan `afirmaciones/afirmaciones_greene.jsonl`, fundir con la KB
igual que T119 (`fusión` en `libros_comprados_astro_evidencias.md`):
revisar contradicciones con Arroyo/Sasportas antes de escribir
`kb/*.json` (comparar afirmaciones ES de Greene-en-inglés con las celdas;
no volcar texto del libro).
