# Cobertura v3 (T82)

Comando único reproducible, sin LLM ni red, que reúne las evidencias vigentes,
regenera la matriz de cobertura y produce el informe de huecos.

## Orden

```bash
cd /Users/angelgonzalez/adivinacion-ia/.worktrees/t82-cobertura-v3
finetune/.venv/bin/python finetune/corpus/cobertura_v3.py
```

Salidas (directorio nuevo, no toca los `cobertura_total*.json` previos):

- `/Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.json`
- `/Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.md`

Opciones principales: `--libros limpio|crudo` (por defecto limpio, T71),
`--sin-excluir-claves`, `--web`, `--libros-limpio`, `--libros-crudo`,
`--excluir-claves`, `--extra <jsonl...>`, `--v2 <ruta>`, `--out-dir`,
`--calidad-min` (3), `--dry-run`.

Criterios de celda completa (sin cambios respecto a `cobertura.py`):
>=5 fuentes independientes, >=1 clásica, >=2 modernas, >=1 en español,
calidad >=3.

## Números de la pasada real (ejecutada 2026-10-21)

Insumos: web 19.481 evidencias + libros limpias 14.223; claves de consenso
cargadas 1.098; evidencias excluidas **0** (ver abajo); inválidas 0.

| Familia | Celdas | Completas v3 | % | Completas v2 |
|---|---|---|---|---|
| Tarot | 936 | 172 | 18,4 % | 173 |
| Baraja española | 480 | 36 | 7,5 % | 2 |
| Astrología | 5.247 | 85 | 1,6 % | 79 |
| Numerología | 792 | 11 | 1,4 % | 5 |
| **Total** | **7.455** | **304** | **4,1 %** | **259** |

Ignoradas (fuera de catálogo): 375.

### Comparación v2 -> v3

- Pasan a completas: **51** (mayoría numerología y astrología, por el
  crecimiento de la web y las limpias de libros).
- Dejan de serlo: **6**, todas en Tarot `derecha_invertida`
  (mayores 10, 11, 13, 15, 18 y una más), por perder la única fuente
  clásica: la limpieza T71 eliminó esas secciones de los libros.
- Nota: la v2 se generó con libros **crudos** y una web más pequeña; la v3
  usa libros **limpios** (T71) y la web vigente.

### La exclusión por claves de consenso

Las 1.098 claves de `libros_limpio/claves_excluir_consenso.jsonl`
coinciden con **1.099 evidencias de los libros crudos** pero con **0 de las
limpias**: la limpieza T71 ya eliminó esas secciones contaminadas. Por eso
la exclusión es un no-op con `--libros limpio` (correcto) y solo tiene
efecto con `--libros crudo`:

| Variante | Completas | vs v2 |
|---|---|---|
| limpio + exclusión (defecto v3) | 304 | +51 / -6 |
| crudo + exclusión | 308 | +51 / -2 |
| crudo sin exclusión | 310 | +51 / -0 |

Es decir: las claves protegen 2 celdas que solo serían completas apoyándose
en secciones marcadas como contaminadas por consenso.

## Informe de huecos (top 3, detalle completo en el .md/.json)

Entidades con más celdas incompletas:

- Tarot: Dos/Cuatro/Cinco de Bastos (12 incompletas cada una).
- Baraja española: Tres/Cinco/Seis de Bastos (12).
- Astrología: Escorpio, Júpiter en Acuario, Júpiter en Capricornio (11).
- Numerología: Año personal 11, Camino de vida 11, Destino 11 (11).

Dominios que más aportan (entidades distintas cubiertas):

- Tarot: tarotveraluna.com (78), cartastarotsagrado.com (78),
  tarot-secret.com (78).
- Baraja: astrologuias.com (40), jardindeltarot.com (40),
  tiradadetarot.com (40).
- Astrología: escuelamaia.com (163), gramaglia-e. (libro, 126),
  astrology_202211 (122).
- Numerología: yourastrallife.com (63), astralsagehub.com (41),
  numerologia-portal-del-destino (libro, 38).

### Estimación para el 10 % de celdas completas por familia (método T43)

`fuentes_ideales` = arreglar primero las celdas más baratas
(`fuentes_necesarias` de `recuperacion_dirigida`); `ritmo` = celdas
completas por fuente distinta aportada en la pasada actual;
`fuentes_ritmo` = fuentes necesarias a ese ritmo.

| Familia | Meta (10 %) | Hay | Faltan | Fuentes ideales | Fuentes distintas | Ritmo | Fuentes al ritmo |
|---|---|---|---|---|---|---|---|
| Tarot | 94 | 172 | 0 | 0 | 1.129 | 0,152 | 0 |
| Baraja española | 48 | 36 | 12 | 12 | 359 | 0,100 | 120 |
| Astrología | 525 | 85 | 440 | 655 | 576 | 0,148 | 2.982 |
| Numerología | 80 | 11 | 69 | 69 | 489 | 0,023 | 3.068 |

Lectura: Tarot ya supera el 10 %. Baraja necesita solo 12 fuentes ideales
(celdas casi completas) pero al ritmo observado de esta pasada, 120.
Astrología es el sumidero: 655 fuentes ideales, ~3.000 al ritmo real.
Numerología tiene el peor ritmo (0,023): sus fuentes actuales apenas
convierten; conviene recuperación dirigida (T43) en vez de más web.

## Reproducibilidad

Mismas entradas y opciones -> mismas salidas (orden determinista, sin LLM ni
red). Tests hermetéticos en `finetune/corpus/tests/test_cobertura_v3.py`
(22 casos: celda completa, falta clásica, falta español, exclusión de
claves, comparación v2->v3, reunión de orígenes, informe de huecos, CLI).
