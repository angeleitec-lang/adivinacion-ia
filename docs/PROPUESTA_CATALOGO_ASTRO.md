# Propuesta de catálogo astrológico ampliado (casa-N, elemento, modalidad)

> Pista T137, rama `track/t137-catalogo-astro-casas`, escrita el 2026-10-23.
> **Estado: PROPUESTA — no aplicada.** No se ha tocado `kb/*.json`, ni `cobertura_v3`, ni ningún módulo existente. Todo el trabajo determinista (sin LLM) se ejecutó sobre una COPIA en `/Users/angelgonzalez/fase0/catalogo_astro_propuesta/`.

## 1. Inventario del catálogo astro actual

Fuente: `finetune/corpus/cobertura.py` (`entidades()`) y `finetune/corpus/kb/astrologia.json`.

| Tipo de entidad | Entidades | Celdas (entidad × 11 facetas) |
|---|---|---|
| `signo` | 12 | 132 |
| `planeta_en_signo` | 120 (10 planetas × 12 signos) | 1 320 |
| `planeta_en_casa` | 120 (10 planetas × 12 casas) | 1 320 |
| `aspecto` | 225 (C(10,2) × 5 aspectos) | 2 475 |
| **Total astrología** | **477** | **5 247** |

Facetas (comunes a toda astrología, `_FACETAS_BASE`, 11): `significado_general`, `luz_sombra`, `amor`, `trabajo`, `dinero`, `salud`, `espiritual`, `simbolismo`, `correspondencias`, `consejo_practico`, `ejemplo_de_uso`.

Cobertura v3 actual (`/Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.json`, 7 455 celdas totales, 299 completas; una celda es **completa** con ≥5 fuentes independientes + 1 clásica + 2 modernas + 1 en español):

| Tipo | Completas |
|---|---|
| signo | 49 / 132 |
| planeta_en_signo | 32 / 1 320 |
| planeta_en_casa | 0 / 1 320 |
| aspecto | 0 / 2 475 |

**No existen** en el catálogo: entidades `casa-N` sueltas, `elemento` (fuego/tierra/aire/agua) ni `modalidad` (cardinal/fijo/variable). La KB guarda el elemento como atributo de cada signo, pero no hay entidad propia que pueda recibir evidencias.

## 2. Lo que los libros T119 contienen y hoy no cabe

T119 (`/Users/angelgonzalez/fase0/libros_comprados_astro/afirmaciones/afirmaciones_astro.jsonl`): **723 afirmaciones** (Arroyo 432, Sasportas 291), todas periodo *moderna*, con cita original en inglés. Distribución por entidad de origen:

| entidad_id de origen | Afirmaciones |
|---|---|
| planeta_en_signo | 340 |
| signo | 244 |
| aspecto | 76 |
| planeta_en_casa | 63 |

Contenido de los libros que **rebosa** el catálogo actual (hueco documentado en `finetune/knowledge/libros_comprados_astro_evidencias.md` §5):

1. **Doce casas como tema propio** (Sasportas, *The Twelve Houses*): la casa como entidad con su psicología, no solo como contenedor de planeta. Ej.: «La casa cuatro representa la acción directa en el nivel emocional y del alma.» Hoy solo cabe si un planeta la ocupa (`planeta_en_casa`); la casa 3, 6 y 8 no tienen ni eso (casas con evidencias vía planeta: 1, 2, 4, 5, 7, 9, 10, 11, 12).
2. **Cuatro elementos y sus desequilibrios** (Arroyo, *Astrology, Psychology and the Four Elements*): discusión del fuego/tierra/aire/agua como entidades con dinámicas propias. Hoy no hay entidad `elemento`.
3. **Modalidades / agrupaciones** (Arroyo, Sasportas): cardinal-fijo-variable, cuadrantes y hemisferios. Hoy no hay entidad `modalidad`.
4. **Planetas sueltos** (Arroyo): descripciones del planeta aislado (p. ej. Saturno como principio) sin signo ni casa. Fuera del alcance de esta propuesta (sería entidad `planeta` simple).

**Por qué el remapeo es estructural y no por texto:** buscar las palabras «fuego/tierra/aire/agua» en las afirmaciones da falsos positivos literales («…funcionaban mejor *cerca del agua*», Sol en Piscis) y solo 24 coincidencias limpias de 723. Lo mismo con modalidad (7 crudos, todos ambiguos). La relación signo→elemento y signo→modalidad es canónica y determinista, así que se deriva del `entidad_id`, no del texto.

## 3. Entidades nuevas propuestas (19, sin aplicar)

Formato de id idéntico al catálogo actual (`nombre|tipo`), familia `astrologia`, mismas 11 facetas:

| Familia de entidad | ids | Nº |
|---|---|---|
| Casa | `casa1..casa12` (tipo `casa`) | 12 |
| Elemento | `fuego\|elemento`, `tierra\|elemento`, `aire\|elemento`, `agua\|elemento` | 4 |
| Modalidad | `cardinal\|modalidad`, `fijo\|modalidad`, `variable\|modalidad` | 3 |

Celdas nuevas: 19 × 11 = **209** (astro pasaría de 5 247 a 5 456; total v3 de 7 455 a 7 664).

Reglas de remapeo determinista (implementadas en `finetune/corpus/catalogo_astro_propuesta.py`):

- **R1 — casa desde `planeta_en_casa`:** `sol|casa2|planeta_en_casa` → evidencia para `casa2` (conserva faceta, fuente, calidad). 63 afirmaciones → 63 evidencias.
- **R2 — elemento desde signo:** toda afirmación de `signo` o `planeta_en_signo` se propaga al elemento del signo (tabla `SIGNO_ELEMENTO`, verificada contra `kb/astrologia.json`). 584 afirmaciones → 584 evidencias.
- **R3 — modalidad desde signo:** igual con `SIGNO_MODALIDAD` canónica por orden zodiacal (cardinal: Aries/Cáncer/Libra/Capricornio; fijo: Tauro/Leo/Escorpio/Acuario; variable: Géminis/Virgo/Sagitario/Piscis; la KB no guarda modalidad). 584 → 584.
- Aspectos (76) y cualquier id desconocido, casa fuera de 1-12 o planeta no canónico: **sin remapeo**. 584 + 63 + 76 = 723 ✓ (cubrimiento exacto, sin duplicados ni pérdidas).

Nota de honestidad: R2/R3 **no afirman que el texto hable del elemento**; derivan una evidencia *indirecta* (el libro describe un signo, y el signo pertenece a un elemento). La faceta y la calidad se conservan tal cual; la auditoría posterior decidirá si vale.

## 4. Impacto estimado en cobertura_v3 (calculado con el script, no a ojo)

Con las 19 entidades añadidas y las evidencias remapeadas (calidad ≥ 3):

| Métrica | Valor |
|---|---|
| Celdas nuevas creadas | 209 |
| Celdas con ≥1 fuente | 88 (casa 23/132, elemento 35/44, modalidad 30/33) |
| Celdas con ≥2 fuentes | 28 (casa 3, elemento 13, modalidad 12) |
| Celdas **completas** | **0** |

Las 0 completas son esperables: los libros T119 son modernos y en inglés (cita original); la regla de completitud pide además 1 clásica + 1 en español y 5 fuentes. **La propuesta no llena celdas por sí sola: abre 209 celdas nuevas captando 88 con evidencia inmediata**, que después se reforzarán con las fuentes web/clásicas de las pistas de adquisición.

## 5. Coste

- **Dataset (prompts de lectura):** +209 celdas × facetas pendientes. Si cada celda completa requiere ~5 evidencias y hoy hay 88 con al menos 1, el trabajo extra de generación Fase 1 es del orden de **+1 000 lecturas** como máximo, no de 2 475 (las 161 celdas restantes sin evidencia habría que alimentarlas desde fuentes nuevas; se pueden dejar fuera del v1). Coste marginal real decidible celda a celda.
- **`calculos/`: CERO.** Verificado ejecutando `calculos/astro.py::carta_natal('1985-06-15','10:30',40.4168,-3.7038,'Europe/Madrid')` (solo lectura): la calculadora ya devuelve por planeta `{nombre, signo, grado, minuto, casa(1-12), retrógrado, lon}`, los 12 cusps, ascendente, medio cielo, aspectos, `elemento_dominante` y `modalidad_dominante`. Los datos para casa/elemento/modalidad ya se computan; no hay que tocar nada.
- **Riesgo:** bajo. Ningún módulo existente cambia; el catálogo ampliado vive solo en la propuesta hasta que el usuario decida.

## 6. Script determinista y verificación

- Módulo: `finetune/corpus/catalogo_astro_propuesta.py` (sin LLM, sin red). Protege las rutas reales de fase0 (`RUTAS_PROTEGIDAS`): lanza `ValueError` si el work-dir cae dentro de `cobertura_v3`, `libros`, `evidencias_web` o `libros_comprados_astro`.
- Ejecución realizada (copa en `/Users/angelgonzalez/fase0/catalogo_astro_propuesta/`):

```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  /Users/angelgonzalez/adivinacion-ia/.worktrees/t137-catalogo-astro-casas/finetune/corpus/catalogo_astro_propuesta.py \
  --work-dir /Users/angelgonzalez/fase0/catalogo_astro_propuesta
```

  Genera: `afirmaciones_origen.jsonl`, `remapeo.jsonl`, `cobertura_hipotetica.json`, `inventario_y_remapeo.json`, `informe.md`.
- Tests: `finetune/corpus/tests/test_catalogo_astro_propuesta.py` — 34 tests OK, adversos incluidos: casa 13/0/-1, ids inexistentes (`quiron|signo`, `quiron|piscis|planeta_en_signo`, `quiron|casa5|planeta_en_casa`), signos ambiguos (`cancer leo|signo`, `ascendente|signo`, vacío), claims basura, work-dir protegido, coherencia `SIGNO_ELEMENTO` vs KB, no colisión de ids propuestos con el catálogo actual.

## 7. Decisión que debe tomar el usuario

**Opción A — Aceptar la propuesta (recomendada):** añadir 19 entidades (12 casas + 4 elementos + 3 modalidades) al catálogo de astrología de `cobertura.py` y a la KB, y absorber las 88 celdas con evidencia inmediata de T119. Impacto: +209 celdas, 0 completas hoy, coste de calculos/ nulo, ~+1 000 lecturas de Fase 1 como techo.

**Opción B — Solo casas (12 entidades):** el hueco más claro (Sasportas es un libro por casas); elementos/modalidades se dejan para otra ronda. 132 celdas nuevas, 23 con fuente.

**Opción C — Rechazar:** mantener 477 entidades; las 723 afirmaciones de T119 siguen usándose solo donde ya caben.

Si se acepta (A o B), el comando de aplicación **no existe todavía**: lo escribirá la siguiente pista de integración (modificar `cobertura.py` + `kb/astrologia.json` + absorción de evidencias), porque esta pista tenía prohibido tocarlos. Esta propuesta entrega la decisión informada y el mecanismo probado (remapeo determinista + cobertura hipotética) sobre el que construir esa integración.
