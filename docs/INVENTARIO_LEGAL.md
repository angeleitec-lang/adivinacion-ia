# Inventario de procedencia y licencias

Generado por `finetune/corpus/inventario_legal.py` a partir de los
manifiestos, `finetune/knowledge/`, las evidencias y las afirmaciones de
fase 0. No se ha consultado la red: la clasificación se basa solo en los
metadatos disponibles y es una ayuda para la revisión legal, no un
dictamen.

## Cómo leer el riesgo

- `libre`: dominio público o licencia CC compatible declarada en los datos.
- `consultar`: web comercial, foro o blog sin licencia explícita; también
  fuentes sin metadatos suficientes.
- `riesgo_alto`: obra moderna con copyright, contenido de pago o vídeo de
  plataforma; requiere permiso, licencia o sustitución antes de un modelo
  comercial.

## Resumen

- Fuentes inventariadas: 204
- libre: 38
- consultar: 112
- riesgo_alto: 54

### Por riesgo y familia

| Riesgo | Familia | Fuentes | Evidencias | Afirmaciones |
|---|---|---|---|---|
| consultar | astrologia | 33 | 5663 | 41061 |
| consultar | baraja_espanola | 16 | 3625 | 8931 |
| consultar | desconocida | 4 | 606 | 512 |
| consultar | numerologia | 31 | 3439 | 12819 |
| consultar | tarot | 28 | 11982 | 44690 |
| libre | astrologia | 16 | 3249 | 1848 |
| libre | baraja_espanola | 12 | 695 | 858 |
| libre | desconocida | 1 | 170 | 540 |
| libre | numerologia | 5 | 208 | 433 |
| libre | tarot | 4 | 1181 | 1094 |
| riesgo_alto | astrologia | 7 | 2569 | 4525 |
| riesgo_alto | baraja_espanola | 13 | 244 | 2236 |
| riesgo_alto | desconocida | 4 | 903 | 2635 |
| riesgo_alto | numerologia | 8 | 301 | 1159 |
| riesgo_alto | tarot | 22 | 2876 | 7343 |

## Las 20 fuentes de riesgo no libre con más peso

Ordenadas por evidencias + afirmaciones que dependen de ellas.

| Fuente | Tipo | Familia | Evidencias | Afirmaciones | Riesgo |
|---|---|---|---|---|---|
| `escuelamaia.com` | web | astrologia | 1281 | 15313 | consultar |
| `cartastarotsagrado.com` | web | tarot | 1122 | 8627 | consultar |
| `tarot-secret.com` | web | tarot | 999 | 8283 | consultar |
| `astrolink.com` | web | astrologia | 662 | 7473 | consultar |
| `tarotveraluna.com` | web | tarot | 1267 | 6567 | consultar |
| `grancosmos.com` | web | astrologia | 597 | 7126 | consultar |
| `astrologuias.com` | web | baraja_espanola | 517 | 6029 | consultar |
| `tuastral.com` | web | tarot | 653 | 5012 | consultar |
| `mercurioretrogrado.com` | web | astrologia | 464 | 5063 | consultar |
| `zodiatarot.com` | web | tarot | 659 | 3588 | consultar |
| `astroideal.com` | web | tarot | 1415 | 2652 | consultar |
| `loveplay.io` | web | numerologia | 325 | 3567 | consultar |
| `astrologiaparadummiesraeorion6` | libro | astrologia | 709 | 2740 | consultar |
| `astrology_202211` | libro | astrologia | 803 | 2253 | riesgo_alto |
| `anonimo.-los-arcanos-mayores-del-tarot-ocr-1987` | libro | tarot | 660 | 2262 | riesgo_alto |
| `PaulFosterCase-TarotFundamentals-1936` | libro | tarot | 556 | 2024 | riesgo_alto |
| `la-via-del-tarot-alejandro-jodorowsky` | libro | tarot | 1180 | 1184 | consultar |
| `elvitarot.com` | web | tarot | 523 | 1841 | consultar |
| `mysticanswer.com` | web | tarot | 566 | 1791 | consultar |
| `eight-leaves.de` | web | numerologia | 172 | 2047 | consultar |

## Fuentes a consultar, contactar o sustituir para un modelo comercial

### Riesgo alto

| Fuente | Tipo | Familia | Evidencias | Afirmaciones | Riesgo |
|---|---|---|---|---|---|
| `astrology_202211` | libro | astrologia | 803 | 2253 | riesgo_alto |
| `anonimo.-los-arcanos-mayores-del-tarot-ocr-1987` | libro | tarot | 660 | 2262 | riesgo_alto |
| `PaulFosterCase-TarotFundamentals-1936` | libro | tarot | 556 | 2024 | riesgo_alto |
| `gramaglia-e.-astrologia-hermetica-ocr-2006` | libro | astrologia | 966 | 980 | riesgo_alto |
| `RobertWang-TheQabalisticTarot-1983` | libro | desconocida | 529 | 1379 | riesgo_alto |
| `los-planetas-huber` | libro | astrologia | 500 | 1123 | riesgo_alto |
| `numerologia-portal-del-destino-helyn-hitchcock` | libro | numerologia | 301 | 1159 | riesgo_alto |
| `IOTTOM` | libro | tarot | 250 | 1165 | riesgo_alto |
| `ChicCiceroSandraTabathaCicero-NewGoldenDawnRitualTarotKeysToThe` | libro | desconocida | 267 | 783 | riesgo_alto |
| `euroresidentes.com` | web | tarot | 113 | 818 | riesgo_alto |
| `instantesconrosmeris.com` | web | baraja_espanola | 75 | 832 | riesgo_alto |
| `angelestarotyvidencia.com` | web | tarot | 85 | 642 | riesgo_alto |
| `eragon8.blogspot.com` | web | baraja_espanola | 94 | 587 | riesgo_alto |
| `nichols-sallie.-jung-y-el-tarot-ocr-1988` | libro | tarot | 468 | 123 | riesgo_alto |
| `meditations-on-the-tarot` | libro | tarot | 558 | 0 | riesgo_alto |
| `brisademartarot.blogspot.com` | web | baraja_espanola | 45 | 497 | riesgo_alto |
| `TheKeyToTheUniverse7thEdition` | libro | desconocida | 93 | 437 | riesgo_alto |
| `tarotsevilla.com` | web | baraja_espanola | 30 | 320 | riesgo_alto |
| `eclectica.com.ar` | web | tarot | 34 | 305 | riesgo_alto |
| `maria-blaquier-astrologia-tradicional.-tecnicas-predictivas-de-los-senores-del-tiempo` | libro | astrologia | 160 | 119 | riesgo_alto |
| `compendium-tarot-mexicanus-no-0` | libro | tarot | 152 | 4 | riesgo_alto |
| `in.ernet.dli.2015.128064` | libro | astrologia | 109 | 5 | riesgo_alto |
| `le-grice-k.-el-cosmos-arquetipal-ocr-2018` | libro | astrologia | 31 | 45 | riesgo_alto |
| `la-revolucion-de-la-quiromancia-yasuto-nishitani` | libro | desconocida | 14 | 36 | riesgo_alto |
| `2iVWTU2Khrc` | video | numerologia | 0 | 0 | riesgo_alto |
| `3GX9sG0eMmI` | video | tarot | 0 | 0 | riesgo_alto |
| `4ZHfqaFic2A` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `5O0CjaqTm80` | video | numerologia | 0 | 0 | riesgo_alto |
| `65fl5z6aJJk` | video | numerologia | 0 | 0 | riesgo_alto |
| `ClNAqqUYShc` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `EYCe4jXvZys` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `FTT5t8faWMQ` | video | tarot | 0 | 0 | riesgo_alto |
| `H8G_YxIUi4c` | video | tarot | 0 | 0 | riesgo_alto |
| `JKK3CWUhKKM` | video | tarot | 0 | 0 | riesgo_alto |
| `KCZCUQx766A` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `MGKQI2o1hBE` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `VXRAiVdxmhA` | video | numerologia | 0 | 0 | riesgo_alto |
| `X37uNPmPdeQ` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `ZIzlu7uT8mA` | video | tarot | 0 | 0 | riesgo_alto |
| `aNBsVLSBS0w` | video | tarot | 0 | 0 | riesgo_alto |
| `cu0crzTTmCk` | video | numerologia | 0 | 0 | riesgo_alto |
| `dxVSxlWknSU` | video | tarot | 0 | 0 | riesgo_alto |
| `eWpKtvC00u0` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `fxGBbzdUNwc` | video | numerologia | 0 | 0 | riesgo_alto |
| `gZkk2FlUwLM` | video | tarot | 0 | 0 | riesgo_alto |
| `h-nv043LTDA` | video | tarot | 0 | 0 | riesgo_alto |
| `lIybc6WEG_U` | video | tarot | 0 | 0 | riesgo_alto |
| `mG5ekS3I7FI` | video | tarot | 0 | 0 | riesgo_alto |
| `mvTZ-a07aOU` | video | baraja_espanola | 0 | 0 | riesgo_alto |
| `nptr7WVOAbk` | video | numerologia | 0 | 0 | riesgo_alto |
| `up41cwNvIXA` | video | tarot | 0 | 0 | riesgo_alto |
| `vBYtj80Ji5s` | video | astrologia | 0 | 0 | riesgo_alto |
| `xLt2GCLA024` | video | tarot | 0 | 0 | riesgo_alto |
| `tarotdestrella.blogspot.com` | web | baraja_espanola | 0 | 0 | riesgo_alto |

### Consultar

| Fuente | Tipo | Familia | Evidencias | Afirmaciones | Riesgo |
|---|---|---|---|---|---|
| `escuelamaia.com` | web | astrologia | 1281 | 15313 | consultar |
| `cartastarotsagrado.com` | web | tarot | 1122 | 8627 | consultar |
| `tarot-secret.com` | web | tarot | 999 | 8283 | consultar |
| `astrolink.com` | web | astrologia | 662 | 7473 | consultar |
| `tarotveraluna.com` | web | tarot | 1267 | 6567 | consultar |
| `grancosmos.com` | web | astrologia | 597 | 7126 | consultar |
| `astrologuias.com` | web | baraja_espanola | 517 | 6029 | consultar |
| `tuastral.com` | web | tarot | 653 | 5012 | consultar |
| `mercurioretrogrado.com` | web | astrologia | 464 | 5063 | consultar |
| `zodiatarot.com` | web | tarot | 659 | 3588 | consultar |
| `astroideal.com` | web | tarot | 1415 | 2652 | consultar |
| `loveplay.io` | web | numerologia | 325 | 3567 | consultar |
| `astrologiaparadummiesraeorion6` | libro | astrologia | 709 | 2740 | consultar |
| `la-via-del-tarot-alejandro-jodorowsky` | libro | tarot | 1180 | 1184 | consultar |
| `elvitarot.com` | web | tarot | 523 | 1841 | consultar |
| `mysticanswer.com` | web | tarot | 566 | 1791 | consultar |
| `eight-leaves.de` | web | numerologia | 172 | 2047 | consultar |
| `TarotOfTheMagiciansByOswaldWirth` | libro | tarot | 503 | 1681 | consultar |
| `mundivia.es` | web | numerologia | 152 | 1714 | consultar |
| `horoscopelogic.com` | web | numerologia | 133 | 1579 | consultar |
| `yourastrallife.com` | web | numerologia | 1244 | 0 | consultar |
| `Tarot-el-arte-de-adivinar-enrique-eskenazi` | libro | tarot | 269 | 905 | consultar |
| `forotarot.net` | web | baraja_espanola | 213 | 943 | consultar |
| `es.astro-seek.com` | web | numerologia | 81 | 954 | consultar |
| `tarotgratuito.net` | web | tarot | 414 | 582 | consultar |
| `tiradadecartas.com.ar` | web | baraja_espanola | 110 | 870 | consultar |
| `tarot.ac` | web | numerologia | 76 | 863 | consultar |
| `astrologia-kabbalistica-rav-berg` | libro | astrologia | 153 | 758 | consultar |
| `tarotsevilla.top` | web | baraja_espanola | 65 | 759 | consultar |
| `la-numerologia-a-la-luz-del-arbol-de-la-vida-y-las-letras-hebraicas-martine-coqu` | libro | numerologia | 191 | 583 | consultar |
| `astrologia-cientifica-simplificada-max-heindel` | libro | astrologia | 254 | 483 | consultar |
| `astrologia-predictiva-tito-macia` | libro | astrologia | 167 | 525 | consultar |
| `wtf-es-el-tarot-un-enfoque-sensato-al-antiguo-arte-de-la-lectura-del-tarot-bakar` | libro | tarot | 266 | 407 | consultar |
| `curso_basico_de_astrologia_-_vol._1` | libro | astrologia | 232 | 435 | consultar |
| `tarotamigo.com` | web | baraja_espanola | 655 | 0 | consultar |
| `tarotfiable.es` | web | tarot | 206 | 449 | consultar |
| `szare_op_78` | libro | desconocida | 498 | 130 | consultar |
| `moonoscope.com` | web | numerologia | 47 | 554 | consultar |
| `the-star-1` | libro | tarot | 549 | 34 | consultar |
| `curso-basico-de-astrologia-vol-3-analise-do-horoscopo-copia` | libro | astrologia | 274 | 280 | consultar |
| `tarotjunguiano.com` | web | tarot | 272 | 254 | consultar |
| `curso-basico-de-astrologia-vol-3-joan-mc-evers-e-marion-d.-march` | libro | astrologia | 277 | 242 | consultar |
| `grupovenus.com` | web | astrologia | 40 | 387 | consultar |
| `es.astrologyk.com` | web | numerologia | 30 | 359 | consultar |
| `tarotsi.gratis` | web | baraja_espanola | 50 | 330 | consultar |
| `jardindeltarot.com` | web | baraja_espanola | 366 | 0 | consultar |
| `tiradadetarot.com` | web | baraja_espanola | 343 | 0 | consultar |
| `tarotbrisatalis.com` | web | tarot | 105 | 232 | consultar |
| `TheSecretScienceOfNumerology` | libro | desconocida | 65 | 268 | consultar |
| `tarotdetiziana.com` | web | tarot | 89 | 218 | consultar |
| `tarotdeabsalon.com` | web | baraja_espanola | 298 | 0 | consultar |
| `annacasas.es` | web | baraja_espanola | 293 | 0 | consultar |
| `elreydecopas.com` | web | baraja_espanola | 276 | 0 | consultar |
| `cartas-tarot-de-las-brujas-modernas` | libro | tarot | 104 | 166 | consultar |
| `TheKabalaOfNumbers` | libro | numerologia | 73 | 187 | consultar |
| `astralsagehub.com` | web | astrologia | 256 | 0 | consultar |
| `tarotnova.app` | web | tarot | 146 | 106 | consultar |
| `tarotdeana.es` | web | baraja_espanola | 230 | 0 | consultar |
| `NumerologyTheCompleteGuideVol1` | libro | numerologia | 36 | 172 | consultar |
| `ElLenguajeDelEspiritu` | libro | astrologia | 36 | 170 | consultar |
| `freenumerology.net` | web | numerologia | 204 | 0 | consultar |
| `tarotsolaguilar.com` | web | baraja_espanola | 200 | 0 | consultar |
| `losarcanos.com` | web | numerologia | 14 | 163 | consultar |
| `curso-basico-de-astrologia-volume-2-tecnicas-de-calculos-pdfdrive` | libro | astrologia | 112 | 52 | consultar |
| `tarotysalud.com` | web | tarot | 121 | 37 | consultar |
| `aeclectic.net` | web | tarot | 155 | 0 | consultar |
| `tarot.com` | web | tarot | 152 | 0 | consultar |
| `ptolemystetrabib00ptol` | libro | astrologia | 130 | 0 | consultar |
| `tiradas-de-cartas-espanolas` | libro | desconocida | 33 | 94 | consultar |
| `thenumerologypower.com` | web | numerologia | 125 | 0 | consultar |
| `mi.astrocentro.com` | web | tarot | 55 | 68 | consultar |
| `labyrinthos.co` | web | tarot | 112 | 0 | consultar |
| `chaldean-numerology-for-beginners-pdfdrive-1` | libro | numerologia | 91 | 12 | consultar |
| `aurimundi.com` | web | numerologia | 88 | 0 | consultar |
| `NumerologyTheCompleteGuideVol2` | libro | numerologia | 10 | 65 | consultar |
| `skywhisper.app` | web | numerologia | 74 | 0 | consultar |
| `velotit.com` | web | numerologia | 50 | 0 | consultar |
| `numerovya.com` | web | numerologia | 45 | 0 | consultar |
| `biddytarot.com` | web | tarot | 44 | 0 | consultar |
| `cheirosbookofnumbers` | libro | numerologia | 42 | 0 | consultar |
| `mon-oracle.org` | web | numerologia | 34 | 0 | consultar |
| `fundamentos-de-la-astrologia-clasica-tito-macia` | libro | astrologia | 19 | 14 | consultar |
| `hajo-banzhaf-el-tarot-una-guia-de-ayuda-para-la-toma-de-decisiones` | libro | tarot | 27 | 6 | consultar |
| `datemyst.com` | web | numerologia | 31 | 0 | consultar |
| `yi-jing-el-libro-de-los-cambios-jordi-alva-traduccion-prologo-y-notas-del-texto` | libro | desconocida | 10 | 20 | consultar |
| `mybornday.com` | web | numerologia | 26 | 0 | consultar |
| `numerologia-cotidiana.com` | web | numerologia | 25 | 0 | consultar |
| `numerologos.com` | web | numerologia | 13 | 0 | consultar |
| `eltarot.es` | web | tarot | 9 | 0 | consultar |
| `oraculoseuropeos.blogspot.com` | web | baraja_espanola | 9 | 0 | consultar |
| `numerologic.app` | web | numerologia | 4 | 0 | consultar |
| `nohemia.com` | web | numerologia | 3 | 0 | consultar |
| `aprendeastrologia.com` | web | astrologia | 0 | 0 | consultar |
| `astralisis.com` | web | astrologia | 0 | 0 | consultar |
| `astro-cours.com` | web | astrologia | 0 | 0 | consultar |
| `astrochart.co` | web | astrologia | 0 | 0 | consultar |
| `astrocosmo.cl` | web | astrologia | 0 | 0 | consultar |
| `astrologica.es` | web | astrologia | 0 | 0 | consultar |
| `astroworld.es` | web | astrologia | 0 | 0 | consultar |
| `caminosdeconocimiento.com` | web | astrologia | 0 | 0 | consultar |
| `campus-astrologia.es` | web | astrologia | 0 | 0 | consultar |
| `cartaceleste.com` | web | numerologia | 0 | 0 | consultar |
| `enastrologico.com` | web | astrologia | 0 | 0 | consultar |
| `fernandoangelcoronado.es` | web | astrologia | 0 | 0 | consultar |
| `futooro.net` | web | baraja_espanola | 0 | 0 | consultar |
| `leandroliptak.com` | web | astrologia | 0 | 0 | consultar |
| `numerologist.com` | web | numerologia | 0 | 0 | consultar |
| `ritmolunar.com` | web | astrologia | 0 | 0 | consultar |
| `ruthmontenegro.com` | web | astrologia | 0 | 0 | consultar |
| `simbologia.net` | web | astrologia | 0 | 0 | consultar |
| `soyespiritual.top` | web | baraja_espanola | 0 | 0 | consultar |
| `tailoredmoon.com` | web | astrologia | 0 | 0 | consultar |

## Qué cambiaría si se excluyeran las fuentes de riesgo alto

- Celdas de la matriz: 7455
- Celdas completas ahora: 310
- Celdas completas sin fuentes de riesgo alto: 297
- Celdas que perderían la condición de completa: 13

### Comparación por familia

| Familia | Completas ahora | Completas sin riesgo alto |
|---|---|---|
| Tarot | 178/936 | 178/936 |
| Baraja española | 36/480 | 36/480 |
| Astrología | 85/5247 | 76/5247 |
| Numerología | 11/792 | 7/792 |

### Celdas afectadas

- `aries|signo` · dinero: falta 1 fuente moderna
- `cancer|signo` · dinero: falta 1 fuente en español
- `libra|signo` · salud: falta 1 fuente moderna; falta 1 fuente en español
- `libra|signo` · ejemplo_de_uso: falta 1 fuente moderna
- `sol|leo|planeta_en_signo` · simbolismo: falta 1 fuente independiente
- `luna|geminis|planeta_en_signo` · significado_general: faltan 2 fuentes independientes
- `venus|aries|planeta_en_signo` · simbolismo: faltan 4 fuentes independientes; faltan 2 fuentes modernas; falta 1 fuente en español
- `venus|libra|planeta_en_signo` · correspondencias: faltan 2 fuentes independientes; falta 1 fuente moderna; falta 1 fuente en español
- `jupiter|leo|planeta_en_signo` · simbolismo: falta 1 fuente independiente
- `1|alma` · espiritual: falta 1 fuente independiente
- `1|alma` · simbolismo: falta 1 fuente independiente
- `22|destino` · significado_general: faltan 2 fuentes independientes
- `22|destino` · simbolismo: faltan 2 fuentes independientes
