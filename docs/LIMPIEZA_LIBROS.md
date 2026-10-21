# LIMPIEZA_LIBROS — T71

Fecha: 2026-10-21. Rama: `track/t71-limpieza-libros`.
Script: `finetune/corpus/aplicar_limpieza_libros.py`. Determinista, sin LLM ni red.

## Objetivo

Las evidencias de tarot mayor generadas desde libros de **otras familias** (astrología,
numerología, quiromancia, I Ching) están contaminadas: el Sol/Luna astrológicos se
colaron como las cartas El Sol (tarot-mayor-20) y La Luna (tarot-mayor-19), y
secciones que nombran una carta distinta de la entidad asignada alimentan el
consenso con datos cruzados. Esta pista **no toca** el original en vivo
(`/Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl`): produce una
copia limpia y los retiros justificados para revisión humana.

## Reglas (prioridad de arriba a abajo)

1. **`sol_luna_astrologica`** — entidad `tarot-mayor-19` o `tarot-mayor-20`
   (La Luna / El Sol) cuyo libro tiene `familia=astrologia` en el inventario de
   `finetune/knowledge/*.jsonl`. Contaminación planeta→carta.
2. **`titulo_otra_carta`** — regla T53 reutilizada de
   `limpiar_evidencias_libros.py`: el título de la sección nombra una carta mayor
   (o una carta de palo) **distinta** de la entidad de la evidencia.
3. **`mayor_sistema_ajeno`** — cualquier mayor (19/20 ya capturadas por la 1) de
   libros con `familia` en {numerologia, quiromancia, iching}.

Los libros sin metadato de familia (`SIN_META`) **no** se retiran por las reglas
1 y 3 (criterio conservador); solo pueden caer por la regla 2.

## Resultados (pasada real sobre 18 230 evidencias)

| Concepto | Valor |
|---|---|
| Total | 18 230 |
| Conservadas | 14 223 |
| Retiradas | 4 007 |
| — `sol_luna_astrologica` | 1 544 |
| — `titulo_otra_carta` | 2 353 |
| — `mayor_sistema_ajeno` | 110 |
| Claves de consenso a excluir | 1 098 |
| Afirmaciones afectadas | 4 127 |

Cobertura (celdas completas / 7 455, solo libros): **antes 211 → después 202**.
Con evidencias web: antes 305 → después 299. (El 305 difiere del 259 de
`cobertura_total_v2.json` porque las evidencias web han crecido desde que se
congeló la v2; la v2 no se sobrescribe.)

El md5 del original (`24c8b8fc6a214fe6343e7a17e1daf943`) quedó intacto antes y
después de la pasada.

Salidas en `/Users/angelgonzalez/fase0/libros_limpio/`:

- `evidencias_limpias.jsonl` — las 14 223 conservadas
- `evidencias_retiradas.jsonl` — las 4 007 retiradas con `motivo`, `titulo`, `familia_libro`
- `muestra_revision.jsonl` — 40 retiradas al azar (semilla 42, determinista)
- `claves_excluir_consenso.jsonl` — 1 098 claves (hash_seccion+entidad_id+faceta) con `n_afirmaciones > 0` en `procesados.jsonl`
- `informe_limpieza.json` — recuentos, afirmaciones y cobertura antes/después

## Ejemplos correctos (10)

Sol/Luna astrológico retirado de El Sol (20) / La Luna (19):

1. `ASPECTS. TO THE SUN` — mayor-20, libro astrología (dli.ernet.128062): capítulo sobre el astro, no la carta.
2. `THE SUN IN CAPRICORN AND MOON IN TAURUS` — mayor-20 (astrologyforall00leogoog): tránsitos planetarios.
3. `THE SUN IN ARIES AND MOON IN SAGITTARIUS` — mayor-20 (astrologyforall00leogoog).
4. `FUTURr PROSPECTS—MOON IN HOUSES` — mayor-19 (dli.ernet.128062): la Luna en casas astrológicas.
5. `Aries` — mayor-19 (messageofstarses00heiniala): capítulo del signo, no de la carta.

Título que nombra otra carta:

6. `The Sun` asignada a mayor-04 (La Emperatriz, PaulFosterCase): nombra El Sol (20).
7. `Nine of Wands` asignada a mayor-02 (El Mago, the-star-1): nombra un nueve de bastos.
8. `La Muerte` asignada a mayor-13 (El Colgado, nichols-sallie): nombra la Muerte, no el Colgado.
9. `El Sol` asignada a mayor-19 (La Luna, nichols-sallie): nombra la carta 20.
10. `The Emperor` asignada a mayor-09 (La Fuerza, manualofcartoman00gran): nombra al Emperador.

## Ejemplos dudosos (10) — a revisar antes de aplicar

Retiradas `sol_luna_astrologica` con título genérico o sin mención solar/lunar;
la retirada se apoya en el metadato del libro, no en el título:

1. `PHILOSOPHy` — mayor-20 (dli.ernet.128062).
2. `INTRODUCTION` — mayor-20 (in.ernet.dli.2015.128064).
3. `CHAPTER XXII` — mayor-20 (dli.ernet.128062).
4. `EL EGO ACTIVO` — mayor-20 (astrology_202211).
5. `104 HElSfRY CORNELIUS AGRIPPA'S` — mayor-20 (agrippa_three_books_1898, OCR).
6. `THAT PRESCIENCE IS USEFUL` — mayor-20 (ptolemy, Tetrabiblos).
7. `THE SECOND HOUSE 153` — mayor-20 (howtojudgenativi00leoa).

Otros riesgos:

8. `TheKabalaOfNumbers` aporta 36 retiradas `mayor_sistema_ajeno`
   (p. ej. `CHAPTER XI THE SIGNIFICANCE OF NUMBERS` → mayor-20). Riesgo: en el
   tarot cabalístico la Luna es el sendero Gimel y el Sol el Tiphereth; si el
   libro trata correspondencias cabalísticas explícitas, parte podría ser
   contenido legítimo para la carta.
9. `DEL SOL` / `LECTURA DEL ÉXITO FINANCIERO` desde
   `la-revolucion-de-la-quiromancia-yasuto-nishitani` (mayor-20): en quiromancia
   el "llano del Sol" es una región de la mano; la retirada es correcta para la
   carta, pero conviene confirmar que no hay lectura simbólica tarotística.
10. `The Emperor` desde `manualofcartoman00gran` (`familia=baraja`): en
    cartomancia "El Emperador" es una carta del mazo cartomántico, no un mayor
    del tarot; la regla 2 la retira por ambigüedad del sistema.

## Riesgos residuales (no cubiertos por esta pasada)

- **Falsos positivos `sol_luna`**: libros de astrología que citan la carta del
  Sol/Luna metafóricamente o en tablas de correspondencias legítimas.
- **Contaminación inversa** (entidades de astrología alimentadas desde libros de
  tarot: 169 evidencias; numerología desde tarot: 41) **no** se filtra aquí;
  queda para una pasada futura con reglas simétricas.
- **baraja ↔ tarot** (512 evidencias cruzadas) no se toca: fuera de alcance.
- **`SIN_META`**: los libros sin familia en el inventario escapan a las reglas
  1 y 3; solo la regla 2 (título) los alcanza.

## Reproducirla

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t71-limpieza-libros
finetune/.venv/bin/python finetune/corpus/aplicar_limpieza_libros.py \
  --evidencias /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl \
  --secciones-dir /Users/angelgonzalez/fase0/libros/secciones \
  --afirmaciones-dir /Users/angelgonzalez/fase0/libros/afirmaciones \
  --evidencias-web /Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl \
  --out-dir /Users/angelgonzalez/fase0/libros_limpio
```

Determinista: misma entrada → mismas salidas (muestra con semilla 42).

## Aplicación a producción (NO ejecutar sin revisión humana)

Solo después de revisar `muestra_revision.jsonl` y el informe:

```bash
# 1. Copia de seguridad con fecha
cp /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl \
   /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl.bak-20261021

# 2. Sustituir por la copia limpia
cp /Users/angelgonzalez/fase0/libros_limpio/evidencias_limpias.jsonl \
   /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl

# 3. Pasar las claves a excluir del consenso al consumidor que corresponda
#    (claves_excluir_consenso.jsonl: 1 098 claves, 4 127 afirmaciones)
```

**No ejecutar estos comandos desde esta pista.** La decisión de aplicar la
limpieza a las pasadas en vivo la toma el usuario tras la revisión.

## Tests

`finetune/corpus/tests/test_aplicar_limpieza_libros.py` — 15 tests
(`unittest`): SolLunaAstrologica, TituloOtraCarta, MayorSistemaAjeno,
Determinismo, ClavesExclusionConsenso, OriginalIntacto. Hermeticos: usan
`tempdir` y `--familias-json`.
