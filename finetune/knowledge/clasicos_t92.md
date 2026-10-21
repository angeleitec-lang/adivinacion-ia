# T92 — Clásicos PD de astrología y tarot (pasada 2)

Pista T92. Objetivo: procesar clásicos de dominio público por la tubería de libros
hacia un work-dir **nuevo** (`/Users/angelgonzalez/fase0/libros_clasicos_pd2/`),
**sin** fusionar con `libros/evidencias/evidencias.jsonl` ni tocar la matriz v3
real. Aquí queda el informe, el comando de fusión y la lista lista-procesar.

## 1. Apagón de archive.org (bloqueante)

Durante toda la pasada, `archive.org` estuvo **caído en toda la red local**:

- DNS resuelve (`207.241.224.2`) pero **TCP 443 con timeout** desde iMac, nodo1 y
  nodo2 (`nc` FAIL, `curl` devuelve `000`).
- Sonda en background (12 intentos c/2 min ≈ 24 min) **nunca** registró `200`.
- `gutendex.com` también caído (`000`).

Consecuencia: **no** se pudieron descargar desde archive.org los clásicos que viven
allí: Éliphas Lévi, Mathers, Etteilla, Court de Gébelin, las mejores ediciones de
Lilly, y los tres títulos **en español** (ver §6). `gutenberg.org`,
`es/en.wikisource.org` sí estaban operativos.

## 2. Procesado en esta pasada: Tetrabiblos de Ptolomeo (trad. Ashmand, 1900)

Único candidato **nuevo, limpio y disponible** durante el apagón.

- Fuente: Gutenberg 70850 — *Ptolemy's Tetrabiblos or Quadripartite*, traducción
  de J. M. Ashmand, original 1900 (W. Foulsham). Idioma **EN**, dominio público.
- Texto limpio PGDP (sin OCR), 552 667 bytes.
- Es una **edición distinta** de `ptolemystetrabib00ptol` (que ya está en main con
  150 evidencias); no duplica.
- Ficha añadida a `finetune/knowledge/fuentes_clasicas_pd.jsonl` como
  `tetrabiblos_ashmand_1900` (familia astrologia, prioridad alta, verificada).
- Descarga: `descarga_clasicos_pd.py --out-dir .../libros_clasicos_pd2 --solo-ids tetrabiblos_ashmand_1900`.
- Procesado (juez **solo nodo2**, workers 3, timeout 300):
  `clasicos_pd_a_evidencias.py --work-dir .../libros_clasicos_pd2 --solo-ids tetrabiblos_ashmand_1900 --endpoints http://10.0.0.4:8000/v1 --workers 3 --timeout 300`
- Resultado: 39/102 secciones con candidatos, 39 llamadas, 0 errores,
  **60 evidencias** (todas calidad ≥ 3; 52 de calidad 4, 8 de calidad 5).

## 3. Falsos positivos de tarot (excluir al fusionar)

El libro es **astrología pura**; no debe producir arcanos. De las 60 evidencias,
**57 son astrología legítima** (signos zodiacales y planeta_en_signo) y **3 son
falsos positivos de tarot** que hay que excluir:

| entidad_id | faceta | sección origen | hash_seccion |
|---|---|---|---|
| `tarot-mayor-20` | simbolismo | THE INFLUENCE OF POSITION WITH REGARD TO THE SUN | `1f991354e1564a553439f31cf44f169ea9cc72fe74634bff113a726dd2060745` |
| `tarot-mayor-14` | significado_general | THE KIND OF DEATH | `be8611d01dd0f59d04ddf2c6e662b947e73357e7db09f79df9e97113e1503f30` |
| `tarot-mayor-14` | simbolismo | THE KIND OF DEATH | `be8611d01dd0f59d04ddf2c6e662b947e73357e7db09f79df9e97113e1503f30` |

Motivo: son la clase de FP ya conocida (T71/T88) — el Sol/Luna astrológicos y la
«clase de muerte» (casa 8) mapeados por error a arcanos. **Ojo:** la sección
`THE KIND OF DEATH` también contiene entidades astrológicas legítimas
(`cancer|signo`, `virgo|signo`), así que la exclusión se hace **por `entidad_id`
de tarot**, no por `hash_seccion` (excluir por hash perdería lo legítimo).

Ya existe una copia saneada lista para fusionar:
`/Users/angelgonzalez/fase0/libros_clasicos_pd2/evidencias/evidencias_sin_fp.jsonl`
(57 líneas, sin las 3 de tarot).

## 4. Delta de cobertura v3 (medido sobre copia, sin tocar la matriz real)

Medición con `cobertura_v3.construir_v3` sobre `libros_crudo` (main) con y sin el
extra saneado (57 evidencias), calidad mínima 3:

- **Celdas completas: 309 → 309. Delta = 0.** Las 57 evidencias no completan
  ninguna celda nueva (una celda completa exige más facetas/fuentes independientes).
- **24 celdas de astrología ganan +1 fuente** (densidad/robustez sobre celdas ya
  cubiertas): los signos `aries`, `cancer`, `virgo`, `libra` en las facetas
  `significado_general`, `trabajo`, `salud`, `simbolismo`, `correspondencias`,
  `ejemplo_de_uso`.
- **0 celdas ganan evidencia en español** (el libro va en inglés).

Valor real de esta pasada: **densidad** sobre celdas astrológicas ya existentes, no
celdas nuevas completas. Aun así es evidencia clásica primaria que refuerza la KB.

## 5. Comando de FUSIÓN (cuando se decida integrar) — con copia previa

**NUNCA** fusionar sin copia previa. La fusión añade las 57 evidencias legítimas
al pipeline de libros y regenera la matriz v3 en un directorio **nuevo** (no
sobrescribe `cobertura_total_v3.json` real).

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
MAIN=/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl
PD2=/Users/angelgonzalez/fase0/libros_clasicos_pd2/evidencias/evidencias_sin_fp.jsonl
FUS=/Users/angelgonzalez/fase0/libros_clasicos_pd2/fusion

# 1) copia previa de las evidencias main (intocable)
mkdir -p "$FUS"
cp -a "$MAIN" "$MAIN.copia_previa_t92"

# 2) evidencias fusionadas = main + 57 legit (sin los 3 FP de tarot)
cat "$MAIN" "$PD2" > "$FUS/evidencias_fusionadas.jsonl"

# 3) regenerar matriz v3 sobre la fusión, en DIRECTORIO NUEVO (no toca la real)
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t92-clasicos-astro/finetune/corpus
$PY cobertura_v3.py --libros-crudo "$FUS/evidencias_fusionadas.jsonl" \
    --out-dir "$FUS/cobertura_v3_tras_t92"
```

Verificar en `$FUS/cobertura_v3_tras_t92/cobertura_total_v3.md` que el recuento
de completas no baja y que las 24 celdas astro mantienen su +1. Solo tras revisar,
promover manualmente a la ruta oficial.

## 6. Lista LISTA-PROCESAR (cuando archive.org vuelva)

Candidatos priorizados, **aún no procesados** por el apagón. Priorizar los 3 en
español al final (aportan `n_es`, que esta pasada no pudo dar).

**Astrología (EN):**
- Éliphas Lévi — *Transcendental Magic / Dogme et Rituel de la Haute Magie*.
- S. L. MacGregor Mathers — *Kabbalah Unveiled*, *Book of the Sacred Magic of Abramelin*.
- Etteilla — *Manière de se procurer la connaissance* (tarot Etteilla).
- Court de Gébelin — *Le Monde Primitif* (vol. tarot/astrología).
- William Lilly — mejores ediciones (`ca-william-lilly`, `bim_early-english-books`
  1647/1659, `isbn_9781162979427`). La de main (`b30338724`) es OCR pésimo.
- Alan Leo extra — `esotericastrolog00leoa`, `the-key-to-your-own-nativity`,
  `modern-astrology`, `1001-notable-nativities`, `progressedhorosc00leoa`,
  `saturnreaperbein00leoa`.
- Sepharial — *The Science of Foreknowledge* (`sepharial_foreknowledge_1918`),
  *Primary Directions* (`sepharial_primary_directions`), *Directional Astrology*
  (`sepharial_directional_1921`).

**EN ESPAÑOL (prioridad alta por `n_es`):**
- `gran_libro_oraculos_1841` — archive `b28748803`.
- `almanaque_profetico_1844` — archive `A11401406`.
- `rueda_adivinar_1890` — `la-rueda-de-adivinar`.

Para cada uno: añadir ficha a `fuentes_clasicas_pd.jsonl`, extender la tupla
`CLASICOS` en `clasicos_pd_a_evidencias.py`, descargar con
`descarga_clasicos_pd.py --out-dir .../libros_clasicos_pd2`, procesar con
`--endpoints http://10.0.0.4:8000/v1 --workers 3 --timeout 300`, revisar FP por
sección y repetir el §5.

## 7. Qué YA está en main (no repetir)

Candidatos T86/T55 que **ya** tienen evidencias en `libros/evidencias/evidencias.jsonl`:
Alan Leo ×3 (`artofsynthesis00leoa` 128, `astrologyforall00leogoog` 139,
`howtojudgenativi00leoa` 142), Papus ES+EN (`TarotDeLosBohemios` 163,
`tarotofbohemians00papu` 139), Sepharial numerología (`TheKabalaOfNumbers` 37),
Ptolomeo Tetrabiblos otra edición (`ptolemystetrabib00ptol` 150), Lilly OCR malo
(`b30338724` 23), Raphael/Alan Leo (`manualofastrolog00raph` 24), Waite
(`A.EWaiteThePictorialKeyToTheTarot` 224), entre otros.
