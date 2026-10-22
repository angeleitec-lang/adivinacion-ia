# Libros comprados por el usuario — T114

Pista T114. Fuente **comprada por el usuario** procesada por la tubería de libros
hacia un work-dir **nuevo** (`/Users/angelgonzalez/fase0/libros_comprados_nichols/`),
**sin** fusionar con `libros/evidencias/evidencias.jsonl` ni tocar la matriz v3
real. Aquí queda la ficha, el delta de cobertura y el comando de fusión.

Regla de procedencia: cada libro comprado conserva `origen = comprado_por_usuario`
y `licencia_hint = libro con copyright, uso interno`. El PDF **nunca** se copia al
repo; solo se procesa desde su ruta original y quedan las evidencias derivadas.

## 1. Ficha del libro

| Campo | Valor |
|---|---|
| `id` | `nichols_jung_tarot_1988` |
| Título | *Jung y el Tarot* |
| Autora | Sallie Nichols |
| Año | 1988 |
| Idioma | es (traducción al español) |
| Familia | Tarot — **solo arcanos mayores** (22) |
| Enfoque | junguiano (arquetipos, sombra, individuación) |
| Origen | comprado por el usuario |
| Licencia | libro con copyright, uso interno (revisión legal posterior en `license_filter.py`) |
| PDF fuente | `/Users/angelgonzalez/fase0/libros_comprados/Nichols - Jung y el Tarot (1988).pdf` (525 pp.) |
| Work-dir | `/Users/angelgonzalez/fase0/libros_comprados_nichols/` |
| Módulo | `finetune/corpus/libro_comprado_nichols.py` |

Ficha de procedencia escrita en
`/Users/angelgonzalez/fase0/libros_comprados_nichols/knowledge/fuentes_libros_comprados.jsonl`.

## 2. Procesado (juez, solo nodo2)

- Limpieza OCR: tabla segura (ä→á, ö→ó, ü→ú, £→é) + unir guion silábico + quitar
  números de página y cabeceras repetidas + reparar `¿` inicial. Ver `ESTADO.md`
  (10 párrafos antes/después y lista de 40 tokens dudosos que **no** se corrigieron
  a ciegas).
- Segmentación por arcano mayor, mapeada por **nombre de carta** (no por número de
  capítulo: el libro altera el orden — cap. 11 = Justicia = `tarot-mayor-12`, etc.).
- Juez: `--endpoints http://10.0.0.4:8000/v1 --workers 2`, reanudable.
- Resultado: 90 secciones juzgadas, **430 evidencias**, 22 entidades, 0 errores.
  Facetas: simbolismo 143, significado_general 112, espiritual 89, luz_sombra 37,
  correspondencias 25, consejo_practico 14, ejemplo_de_uso 7, amor 3.
  Calidad: 318×5, 112×4. Periodo `moderna`, idioma `es`.

## 3. Delta de cobertura v3 (medido sobre copia, sin tocar la matriz real)

Medición con `cobertura_v3.construir_v3` sobre las evidencias vigentes (web +
libros), con y sin las 430 evidencias de Nichols, calidad mínima 3.

- **Sobre la matriz real (web + libros): celdas tarot completas 172 → 172.
  Delta = 0.** Las celdas que Nichols refuerza ya estaban completas vía web; una
  celda completa exige ≥5 fuentes independientes + clásica + 2 modernas + 1 en
  español, y Nichols no aporta la que faltaba en ninguna.
- **Aislado a libros (sin web): 127 → 128 (+1).** Pasa a completa
  `tarot-mayor-06` (El Papa) en la faceta `luz_sombra`.
- **Densidad: 119 celdas tarot ganan +1 fuente** (robustez sobre celdas ya
  cubiertas), los **22 arcanos mayores**, repartidas en 8 facetas:
  `significado_general` 22, `espiritual` 22, `simbolismo` 22, `correspondencias`
  18, `luz_sombra` 16, `consejo_practico` 11, `ejemplo_de_uso` 7, `amor` 1.
- **0 celdas nuevas** (todas existían en el catálogo).

Valor real de esta fuente: **densidad y diversidad** sobre los 22 arcanos ya
cubiertos, con una voz **moderna, en español y explícitamente junguiana** (sombra,
individuación, analogía con mitología y artes visuales) que no estaba
representada con este peso. No completa celdas nuevas sobre la matriz real, pero
sube la robustez de casi todas las facetas de los 22 arcanos.

## 4. Comando de FUSIÓN (cuando se decida integrar) — con copia previa

**NUNCA** fusionar sin copia previa. La fusión añade las 430 evidencias de Nichols
al pipeline de libros y regenera la matriz v3 en un directorio **nuevo** (no
sobrescribe `cobertura_total_v3.json` real).

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
MAIN=/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl
WEB=/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl
NICH=/Users/angelgonzalez/fase0/libros_comprados_nichols/evidencias/evidencias.jsonl
FUS=/Users/angelgonzalez/fase0/libros_comprados_nichols/fusion

# 1) copia previa de las evidencias main (intocable)
mkdir -p "$FUS"
cp -a "$MAIN" "$MAIN.copia_previa_t114"

# 2) regenerar matriz v3 sobre web + libros + nichols, en DIRECTORIO NUEVO
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t114-libro-nichols/finetune/corpus
$PY cobertura_v3.py --web "$WEB" --libros-crudo "$MAIN" \
    --extra "$NICH" --out-dir "$FUS/cobertura_v3_tras_t114"
```

Verificar en `$FUS/cobertura_v3_tras_t114/cobertura_total_v3.md` que el recuento
de completas no baja (debe quedar en 172 tarot) y que las 119 celdas tarot
mantienen su +1 fuente. Solo tras revisar, promover manualmente a la ruta oficial.

Nota: no hay falsos positivos de tarot que excluir — el libro es **tarot puro**
(arcanos mayores), a diferencia del Tetrabiblos de T92. El control de falsos
positivos se hizo en la segmentación (solo encabezados numerados de arcano; nada de
Sol/Luna astrológicos ni «la fuerza» como palabra común).

## 5. Puerta anti-copia (afirmaciones)

Las afirmaciones se extraen con `afirmaciones_libros.py` (ruta T38) más una
**puerta anti-copia propia** en `libro_comprado_nichols.es_copia_literal`: una
afirmación que repita **>25 palabras consecutivas** idénticas al libro se marca
`copia_literal` y se **rechaza** (exigida por ser libro con copyright: se
paraphrasea, no se citan párrafos literales largos). Test en
`tests/test_libro_comprado_nichols.py` (TestPuertaAntiCopia). Las afirmaciones
aceptadas quedan en
`/Users/angelgonzalez/fase0/libros_comprados_nichols/afirmaciones/afirmaciones_nichols.jsonl`.
