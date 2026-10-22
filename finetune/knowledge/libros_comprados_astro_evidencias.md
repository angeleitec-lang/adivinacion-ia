# Libros comprados de astrología (Arroyo, Sasportas) — T119

Pista T119. Dos libros **comprados por el usuario** procesados por la tubería de
libros hacia un work-dir **nuevo**
(`/Users/angelgonzalez/fase0/libros_comprados_astro/`), **sin** fusionar con
`libros/evidencias/evidencias.jsonl` ni tocar la matriz v3 real. Aquí queda la
ficha, la cobertura, el **hueco** de contenido sin celda destino y el comando de
fusión.

Regla de procedencia: cada libro comprado conserva `origen = comprado_por_usuario`
y `licencia_hint = libro con copyright, uso interno`. Los PDF **nunca** se copian
al repo; solo se procesan desde su ruta original y quedan las evidencias derivadas.

## 1. Ficha de los libros

| Campo | Arroyo | Sasportas |
|---|---|---|
| `id` | `arroyo_astrologia_psicologia_1982` | `sasportas_twelve_houses_1985` |
| Título | *Astrology, Psychology and the Four Elements* | *The Twelve Houses* |
| Autor | Stephen Arroyo | Howard Sasportas |
| Año | 1982 | 1985 |
| Idioma | en (original inglés) | en (original inglés) |
| Familia | Astrología | Astrología |
| Origen | comprado por el usuario | comprado por el usuario |
| Licencia | libro con copyright, uso interno (revisión legal posterior en `license_filter.py`) | libro con copyright, uso interno |
| Texto limpio | `fase0/libros_comprados_astro/limpio/arroyo.txt` (T118) | `fase0/libros_comprados_astro/limpio/sasportas.txt` (T118) |
| Estado escaneo | COMPLETO (~418 200 caracteres) | INCOMPLETO (falta final cap. 15 y todo lo posterior a pág. impresa 131, apéndices, glosario, bibliografía, índice) |

Ficha de procedencia escrita en
`/Users/angelgonzalez/fase0/libros_comprados_astro/knowledge/fuentes_libros_comprados.jsonl`
(2 líneas, una por libro). Módulo: `finetune/corpus/libros_comprados_astro.py`.

## 2. Alcance decidido (vinculante)

**Solo celdas existentes** en el catálogo (`cobertura.entidades()`, 667): `signo`,
`planeta_en_signo`, `planeta_en_casa` y `aspecto`. **No** se crean entidades
`casa-N`, `elemento` ni `modalidad`, y **no** se toca el catálogo compartido. En
Sasportas, `planeta_en_casa` solo cuando el capítulo de casa nombra **explícitamente**
un planeta en esa casa. El resto del contenido (ver §5 HUECO) queda sin celda destino.

Detección EN→ES propia en el módulo (la detección del pipeline es solo español):
mapeo de signos/planetas/casas/aspectos inglés→español y patrones
`planeta in signo`, `planeta in la N-ésima casa` (acepta dígito: `in the 2nd`),
`the sign of X`, `X is a fire/earth/air/water sign`, `p1 aspect p2`. Cada párrafo
se segmenta en secciones con `entidad_id` explícito (una por entidad detectada,
máx. 5) y el juez las juzga por nodo2.

## 3. Procesado (juez + afirmaciones, solo nodo2)

- Juez: `--endpoints http://10.0.0.4:8000/v1 --workers 2`, reanudable.
  93 secciones juzgadas (90 + 3 reaprovechadas de la validación inicial),
  **325 evidencias**, 0 errores, 0 sin candidatos.
- Afirmaciones: 325 evidencias procesadas, **723 afirmaciones**, 0 rechazos por
  copia literal, 0 errores.
- Evidencias por libro: Arroyo 187 / Sasportas 138.
- Evidencias por tipo: `planeta_en_signo` 160, `signo` 106, `planeta_en_casa` 32,
  `aspecto` 27.
- Evidencias por faceta: `significado_general` 140, `ejemplo_de_uso` 65, `amor` 36,
  `simbolismo` 19, `trabajo` 17, `luz_sombra` 16, `espiritual` 9,
  `consejo_practico` 8, `salud` 6, `correspondencias` 6, `dinero` 3.
- Calidad: 321×4, 3×5, 1×3. Periodo `moderna`, idioma `en`.
- Celdas únicas tocadas: `planeta_en_signo` 44, `signo` 6, `aspecto` 14,
  `planeta_en_casa` 15.
  - Casas cubiertas: 1, 2, 4, 5, 7, 9, 10, 11, 12 (no 3, 6, 8).
  - Planetas en casa: sol, luna, mercurio, marte, saturno, urano, neptuno, plutón
    (no venus, júpiter).
  - Signos (entidad `signo`): acuario, aries, cáncer, libra, sagitario, virgo (6/12).
  - Aspectos únicos: 14 (p. ej. `sol|trigono|marte`, `luna|cuadratura|venus`,
    `jupiter|trigono|pluton`, `neptuno|trigono|urano`).
- Afirmaciones por tipo: `planeta_en_signo` 340, `signo` 244, `aspecto` 76,
  `planeta_en_casa` 63. Por libro: Arroyo 432 / Sasportas 291.

## 4. Delta de cobertura v3 (medido sobre copia, sin tocar la matriz real)

Medición con `cobertura_v3.py` sobre las evidencias vigentes (web + libros), con y
sin las 325 evidencias astro, en directorios **nuevos**
(`fase0/libros_comprados_astro/fusion/base/` y `.../con_astro/`).

| Tipo | Celdas | Completas base → con astro | Celdas que **ganan +1 fuente** |
|---|---|---|---|
| `planeta_en_signo` | 1320 | 30 → 33 (**+3 completas nuevas**) | 104 |
| `planeta_en_casa` | 1320 | 0 → 0 (+0) | 31 |
| `aspecto` | 2475 | 0 → 0 (+0) | 23 |
| `signo` | 132 | 57 → 57 (+0) | 30 |

**Conclusión:** las evidencias astro **aportan fuentes** (+104 `planeta_en_signo`,
+31 `planeta_en_casa`, +23 `aspecto`, +30 `signo`) y **+3 celdas completas nuevas**
en `planeta_en_signo`. No completan celdas de casa ni de aspecto por sí solas: una
celda `completa` exige ≥5 fuentes independientes + clásica + 2 modernas + 1 en
español, y estos libros (modernos, en inglés) no aportan la que faltaba. Valor real:
**densidad y diversidad** sobre celdas ya cubiertas, con voz moderna anglosajona
(psicología humanista / astropsicología) no representada con este peso.

## 5. HUECO — contenido sin celda destino (importante)

Gran parte del valor de estos libros **no tiene dónde ir** en el catálogo actual,
porque no existen las entidades correspondientes:

- **Sasportas — las doce casas (caps. 3-14).** Cada capítulo trata **una casa de
  forma holística** (la casa como campo de experiencia), **sin** subsecciones
  «Sol en la casa X» por planeta. El significado general de cada casa (1ª–12ª)
  **no** mapea a ninguna celda: no hay entidad `casa-N`. Solo se capturó
  `planeta_en_casa` donde el texto nombra un planeta concreto en esa casa.
- **Arroyo — los cuatro elementos** (fuego/tierra/aire/agua) y los **desequilibrios
  por elemento**: no hay entidad `elemento`.
- **Agrupaciones de casas** (cuadrantes, hemisferios, angular/sucedente/cadente,
  tríplicidades de casas) en ambos libros: no hay entidad `modalidad` ni `casa-N`.
- **Arroyo — «Sun, Moon & Ascendant», «Jupiter & Saturn»**: tratamiento por
  planeta suelto; no hay entidad `planeta` aislada.

**Propuesta (pista aparte, si el usuario quiere fusionar este contenido):** añadir
al catálogo las entidades `casa-N` (12), `elemento` (4) y `modalidad` (3), con
sus facetas, y re-segmentar estos libros hacia esas celdas. Es un cambio
transversal en el catálogo compartido que **excede el alcance de T119** y debe
coordinarse aparte. Mientras no exista, el núcleo de *The Twelve Houses* queda
largamente sin aprovechar.

## 6. Caveats

- **Signo parcial (6/12).** La entidad `signo` solo se cubrió para los signos cuyas
  formas española e inglesa coinciden (aries, cáncer, leo, virgo, libra) más lo
  capturado por `the sign of X` / `X is a <element> sign`. Signos como tauro,
  geminis, escorpio, capricornio, acuario, piscis no aparecen como entidad `signo`
  (el detector EN→ES los trata dentro de `planeta_en_signo`, no como signo suelto).
  Riesgo de falso positivo bajo: en un libro de astrología «Cancer» = signo, no
  enfermedad.
- **Idioma de las afirmaciones.** El extractor compartido
  (`afirmaciones_libros.py`) redacta la **afirmación siempre en español estándar**
  con tildes aunque el original esté en inglés, y guarda la **cita verbatim en
  inglés**. El parámetro `idioma` solo activa el filtro de vocabulario (es). Esto
  **igual el precedente T115** (Pollack+Greer, inglés → afirmaciones en español).
  La **evidencia** sí lleva `idioma = en` (del meta). **Reconciliar** con la línea
  del SIGUIENTE «Afirmaciones en inglés (campo idioma en): T125 las traduce»: el
  pipeline real **traduce inline a español**, no deja la afirmación en inglés. Se
  documenta aquí para que la coordinadora lo aclare con T125.
- **OCR Sasportas.** El escaneo tiene ruido OCR en ordinales de casa (`Ist`=1st,
  `Sth`=5th, `death three` ilegible). El detector acepta ordinales en dígito
  (`in the 2nd`) y en palabra; no se fía de ordinales OCR corruptos.

## 7. Puerta anti-copia (afirmaciones)

Las afirmaciones se extraen con `afirmaciones_libros.py` (ruta T38) más una
**puerta anti-copia propia** en `libros_comprados_astro.es_copia_literal`: una
afirmación que repita **>25 palabras consecutivas** idénticas al libro se marca
`copia_literal` y se **rechaza** (libro con copyright: se paraphrasea, no se citan
párrafos literales largos). Verificado operativo: copia literal de 30 palabras →
rechazada; paráfrasis normal → aceptada. En el run: 0 rechazos (el extractor
produce paráfrasis y las citas verbatim quedan ≤25 palabras). Test en
`tests/test_libros_comprados_astro.py` (TestAntiCopia). Afirmaciones aceptadas en
`/Users/angelgonzalez/fase0/libros_comprados_astro/afirmaciones/afirmaciones_astro.jsonl`.

## 8. Comando de FUSIÓN (cuando se decida integrar) — con copia previa

**NUNCA** fusionar sin copia previa. La fusión añade las 325 evidencias astro al
pipeline de libros y regenera la matriz v3 en un directorio **nuevo** (no
sobrescribe `cobertura_total_v3.json` real).

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
MAIN=/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl
WEB=/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl
ASTRO=/Users/angelgonzalez/fase0/libros_comprados_astro/evidencias/evidencias.jsonl
FUS=/Users/angelgonzalez/fase0/libros_comprados_astro/fusion

# 1) copia previa de las evidencias main (intocable)
mkdir -p "$FUS"
cp -a "$MAIN" "$MAIN.copia_previa_t119"

# 2) regenerar matriz v3 sobre web + libros + astro, en DIRECTORIO NUEVO
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t119-evidencias-libros-astro/finetune/corpus
$PY cobertura_v3.py --web "$WEB" --libros-crudo "$MAIN" \
    --extra "$ASTRO" --out-dir "$FUS/cobertura_v3_tras_t119"
```

Verificar en `$FUS/cobertura_v3_tras_t119/cobertura_total_v3.md` que el recuento
de completas no baja (debe quedar +3 en `planeta_en_signo` y sin retroceso en el
resto) y que las celdas que ganan fuente mantienen su +1. Solo tras revisar,
promover manualmente a la ruta oficial.
