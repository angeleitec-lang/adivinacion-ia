# T115 — Libros comprados en inglés (Pollack y Greer)

Pista T115. Dos libros **comprados por el usuario, uso interno, copyright** (no
dominio público; los PDFs viven en `/Users/angelgonzalez/fase0/libros_comprados/`
y **nunca** se copian al repo). Se procesan por la tubería de libros hacia un
work-dir **nuevo** (`/Users/angelgonzalez/fase0/libros_comprados_en/`), **sin**
fusionar con `libros/evidencias/evidencias.jsonl` ni tocar la matriz v3 real.
Las evidencias quedan en **inglés** (`idioma: "en"`); la traducción de las partes
valiosas llega en T116.

## 1. Procedencia

| id | título | autor | año | procedencia |
|---|---|---|---|---|
| `pollack-78-degrees` | Seventy-Eight Degrees of Wisdom | Rachel Pollack | 1980 | comprado por el usuario, uso interno, copyright |
| `greer-tarot-your-self` | Tarot for Your Self | Mary K. Greer | 1984 | comprado por el usuario, uso interno, copyright |

Ficha con el campo `procedencia` en `knowledge/fuentes_libros_comprados_en.jsonl`
del work-dir. El script `libros_comprados_en.py` extrae el crudo con
`pdftotext -layout` (idempotente) y limpia cabeceras/pies repetidos propios de
cada libro antes de segmentar.

## 2. Estructura de la segmentación

**Pollack — 41 secciones:**
- 22 arcanos mayores, uno por capítulo (título exacto en inglés: `The Fool`,
  `The Magician`, … `Judgement`, `The World`); los largos troceados en partes
  (`The High Priestess (parte 1/2)`). Numeración Rider: Loco=01 … Mundo=22.
- 13 secciones de palos (`Wands/Cups/Swords/Pentacles (Arcana Menor)`, en
  partes). **En el original los menores no tienen encabezado por carta**: se
  segmenta por capítulo de palo y la detección de cartas la hace el juez sobre el
  cuerpo del texto.
- Front matter, índice, introducción y la parte de `READINGS` **no** se segmentan.
- Trampa tratada: menciones sueltas de «the Tower»/«the Star» dentro de otros
  capítulos no crean secciones falsas (búsqueda secuencial por título de capítulo).

**Greer — 133 secciones:**
- `Prefacio e introduccion` + 12 capítulos (`Capitulo N: <título>`).
- 34 secciones de técnica/tirada (`Tecnica: …`) separadas dentro de los
  capítulos (Celtic Cross, permutaciones, mandalas, ejercicios, rituales,
  péndulo…), para que el juez no las trate como significado de carta.
- Apendice por carta: 78 cartas con nombres canónicos (fallbacks OCR:
  `MOON`→The Moon, `HIGH PRIESTESS`→The High Priestess,
  `THE WHEEL OF FORTUNE`→Wheel of Fortune, dobles `STRENGTH/LUST`→09,
  `JUSTICE/ADJUSTMENT`→12, `TEMPERANCE/ART`→15, `JUDGMENT/AEON`→21,
  `THE WORLD/UNIVERSE`→22). La tabla de correspondencias final se excluye.

## 3. Resultado del juez (nodo2, 1 worker)

| libro | secciones | llamadas | errores | evidencias |
|---|---|---|---|---|
| pollack-78-degrees | 41/41 | 41 | 0 | 364 (todas calidad >= 3) |
| greer-tarot-your-self | 118/133 (15 sin candidatos) | 118 | 0 | 529 (todas calidad >= 3) |
| **total** | 174 con candidatos | 159 | 0 | **893** |

Reparto Pollack: 22 mayores con evidencia + 27 menores; facetas principales
simbolismo (118), significado_general (91), espiritual (49), correspondencias
(34), derecha_invertida (26), luz_sombra (25).

## 4. Delta de cobertura v3 (medido sobre copia, matriz real intacta)

Medición con `cobertura_v3` sobre la matriz v3 de main **más** las 893 evidencias
de esta pista, salida en `/Users/angelgonzalez/fase0/cobertura_v3_t115/`
(no sobrescribe `cobertura_v3/` real):

- **Celdas tarot completas: 172 → 173 (+1).** Ganada:
  `tarot-bastos-02|correspondencias`. **0 perdidas.**
- **548 celdas tarot ganan +1 fuente** (densidad/robustez sobre celdas ya
  cubiertas), de las cuales **374 son de arcanos menores** y **78 ganan
  evidencia en la faceta `derecha_invertida`** — el punto flaco que esta pista
  venía a reforzar (invertidos).
- Facetas que más ganan: significado_general (78), derecha_invertida (78),
  simbolismo (77), luz_sombra (55), espiritual (51), consejo_practico (48).

Valor real: **densidad masiva en menores e invertidos**, más una celda completa
nueva. Todo en inglés; T116 aportará la versión ES.

## 5. Puerta anti-copia

Tras las afirmaciones se ejecuta `auditar_copias()`: normaliza (NFKD, minúsculas,
no alfanumérico → espacio) y rechaza cualquier afirmación o `cita_original` que
comparta **más de 25 palabras consecutivas** con el texto del libro. Rechazos a
`afirmaciones/rechazadas_copia.jsonl` con `motivo_rechazo`. Las citas ya están
topadas a 25 palabras por `afirmaciones_libros.MAX_CITA_PALABRAS`; esta puerta es
la segunda capa sobre el texto libre de la afirmación.

## 6. Afirmaciones (T38 sobre estas evidencias) — COMPLETAS

Corrida terminada (nodo2, 1 worker). Salida en
`/Users/angelgonzalez/fase0/libros_comprados_en/afirmaciones/afirmaciones_libros.jsonl`.

| métrica | valor |
|---|---|
| evidencias procesadas | 893/893 |
| afirmaciones generadas | 4191 |
| **aceptadas tras anti-copia** | **4180** |
| rechazadas anti-copia | 11 (todas `copia>25` en `cita_original`) |
| contradicciones KB detectadas | 4 |
| errores transitorios | 35 (3,9 %, sin motivo persistido) |

Los 35 errores son fallos transitorios del LLM (timeout/JSON inválido). Son
**reintentables**: borrar del `procesados.jsonl` las 35 líneas con
`"estado": "error"` y relanzar `--hasta afirmaciones` (la resumabilidad solo
procesa las que faltan). No bloquean el cierre de la pista.

Las 11 rechazos anti-copia están en `rechazadas_copia.jsonl` con
`motivo_rechazo` (ej.: `tarot-mayor-11|espiritual`, cita textual >25 palabras).

## 7. Comando de FUSIÓN (cuando se decida integrar) — con copia previa

**NUNCA** fusionar sin copia previa. La fusión añade las evidencias al pipeline
de libros y regenera la matriz v3 en un directorio **nuevo** (no sobrescribe la
real).

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
MAIN=/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl
EN=/Users/angelgonzalez/fase0/libros_comprados_en/evidencias/evidencias.jsonl
FUS=/Users/angelgonzalez/fase0/libros_comprados_en/fusion

# 1) copia previa de las evidencias main (intocable)
mkdir -p "$FUS"
cp -a "$MAIN" "$MAIN.copia_previa_t115"

# 2) evidencias fusionadas = main + 893 de comprados EN
cat "$MAIN" "$EN" > "$FUS/evidencias_fusionadas.jsonl"

# 3) regenerar matriz v3 sobre la fusión, en DIRECTORIO NUEVO (no toca la real)
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t115-libros-ingles/finetune/corpus
$PY cobertura_v3.py --libros-crudo "$FUS/evidencias_fusionadas.jsonl" \
    --out-dir "$FUS/cobertura_v3_tras_t115"
```

Verificar en `$FUS/cobertura_v3_tras_t115/cobertura_total_v3.md` que el recuento
de completas no baja (esperado: tarot 172 → 173) y que las 548 celdas mantienen
su +1. Solo tras revisar, promover manualmente a la ruta oficial. **Esta pista no
ejecuta la fusión.**

## 8. Cómo reproducir

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t115-libros-ingles/finetune/corpus
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
$PY libros_comprados_en.py --dry-run                 # medir sin LLM
$PY libros_comprados_en.py --hasta segmentacion      # crudo+limpio+secciones
$PY libros_comprados_en.py --hasta juez              # nodo2, 1 worker (T114 vivo)
$PY libros_comprados_en.py --hasta afirmaciones      # T38 + auditar_copias
$PY libros_comprados_en.py --medir                   # delta vs cobertura_v3
```

Reanudable por `hash_seccion`; los endpoints nodo1 (10.0.0.3) están rechazados.
Tests: `python -m unittest tests.test_t115_comprados_en` (26 tests).
