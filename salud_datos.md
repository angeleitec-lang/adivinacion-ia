# Salud de los datos de fase 0

Fecha: 2026-10-20 22:08:56

Base: `/Users/angelgonzalez/fase0`

Semáforo global: **AVISAR**

## Resumen por fichero

| Fichero | Semáforo | Líneas | Tamaño | Modificado | Crece |
|---|---|---:|---:|---|---|
| `afirmaciones_full/afirmaciones.jsonl` | AVISAR | 52716 | 14.8 MB | 2026-10-20 22:08:53 | sí |
| `afirmaciones_full/procesados.jsonl` | OK | 4713 | 861.9 KB | 2026-10-20 22:08:53 | sí |
| `afirmaciones_libros/afirmaciones_libros.jsonl` | AVISAR | 19425 | 8.1 MB | 2026-10-20 22:08:45 | sí |
| `afirmaciones_libros/procesados.jsonl` | AVISAR | 5577 | 996.5 KB | 2026-10-20 22:08:45 | sí |
| `evidencias_web/evidencias.jsonl` | AVISAR | 14010 | 4.2 MB | 2026-10-20 02:22:44 | sí |
| `evidencias_web/juicios.jsonl` | OK | 1558 | 1.2 MB | 2026-10-20 02:22:44 | sí |
| `lecturas/candidatas.jsonl` | OK | 878 | 225.2 KB | 2026-10-20 13:16:31 | no |
| `lecturas/lecturas.jsonl` | OK | 231 | 1.7 MB | 2026-10-20 13:07:03 | no |
| `lecturas/procesados.jsonl` | OK | 878 | 123.9 KB | 2026-10-20 13:07:03 | no |
| `libros/evidencias/evidencias.jsonl` | AVISAR | 17449 | 5.3 MB | 2026-10-20 04:08:28 | no |
| `libros/evidencias/juicios.jsonl` | OK | 4589 | 2.3 MB | 2026-10-20 04:08:28 | no |
| `libros/manifiesto_clasicos_pd.jsonl` | AVISAR | 11 | 6.0 KB | 2026-10-20 21:34:08 | no |
| `muestras/muestras.jsonl` | OK | 2712 | 655.9 KB | 2026-10-20 18:57:19 | no |
| `muestras/prerevision.jsonl` | OK | 2712 | 401.2 KB | 2026-10-20 21:05:11 | no |
| `piloto_fase1/piloto.jsonl` | OK | 22 | 124.6 KB | 2026-10-20 22:04:42 | no |
| `piloto_fase1/piloto_errores.jsonl` | OK | 2 | 6.4 KB | 2026-10-20 21:49:39 | no |
| `plan_recuperacion.jsonl` | OK | 660 | 2.7 MB | 2026-10-20 18:14:57 | no |
| `web/calidad.jsonl` | OK | 756 | 301.5 KB | 2026-10-19 22:00:35 | no |
| `web/manifest.jsonl` | OK | 3970 | 1.1 MB | 2026-10-20 19:30:49 | no |

## Problemas

### AVISAR · `afirmaciones_full/afirmaciones.jsonl`

- línea 24463: duplicado exacto de la línea 24457
- línea 24464: duplicado exacto de la línea 24455
- línea 24465: duplicado exacto de la línea 24459
- línea 29105: duplicado exacto de la línea 29095
- línea 35424: duplicado exacto de la línea 35416
- línea 35425: duplicado exacto de la línea 35420
- línea 45530: duplicado exacto de la línea 45529
- línea 45531: duplicado exacto de la línea 45529
- línea 45532: duplicado exacto de la línea 45529
- línea 48707: duplicado exacto de la línea 48704
- línea 48708: duplicado exacto de la línea 48703
- línea 24463: duplicado por clave (entidad_id='pluton|acuario|planeta_en_signo', faceta='luz_sombra', fuente_id='https://escuelamaia.com/pluton-en-leo/', afirmacion='La sombra de Plutón en Acuario sacrifica al individuo en nombre del ideal colectivo.') de la línea 24457
- línea 24464: duplicado por clave (entidad_id='pluton|acuario|planeta_en_signo', faceta='luz_sombra', fuente_id='https://escuelamaia.com/pluton-en-leo/', afirmacion='La sombra de Plutón en Acuario se activa cuando el sistema no cambia a la velocidad que exige.') de la línea 24455
- línea 24465: duplicado por clave (entidad_id='pluton|acuario|planeta_en_signo', faceta='luz_sombra', fuente_id='https://escuelamaia.com/pluton-en-leo/', afirmacion='En la sombra, Plutón en Acuario prioriza el ideal colectivo sobre la persona concreta.') de la línea 24459
- línea 29105: duplicado por clave (entidad_id='urano|escorpio|planeta_en_signo', faceta='luz_sombra', fuente_id='https://escuelamaia.com/urano-en-tauro/', afirmacion='Urano en Escorpio rompe los vínculos de control y dependencia.') de la línea 29095
- línea 35424: duplicado por clave (entidad_id='saturno|escorpio|planeta_en_signo', faceta='consejo_practico', fuente_id='https://grancosmos.com/guia/saturno-en-escorpio', afirmacion='Se sostiene lo que no se controla.') de la línea 35416
- línea 35425: duplicado por clave (entidad_id='saturno|escorpio|planeta_en_signo', faceta='consejo_practico', fuente_id='https://grancosmos.com/guia/saturno-en-escorpio', afirmacion='Se descubre que se puede sostener lo que no se controla.') de la línea 35420
- línea 45530: duplicado por clave (entidad_id='jupiter|sagitario|planeta_en_signo', faceta='significado_general', fuente_id='https://www.astrolink.com/es/interpretacion/jupiter-en-sagitario', afirmacion='Tienen una mayor curiosidad intelectual y sed de conocimiento.') de la línea 45529
- línea 45531: duplicado por clave (entidad_id='jupiter|sagitario|planeta_en_signo', faceta='significado_general', fuente_id='https://www.astrolink.com/es/interpretacion/jupiter-en-sagitario', afirmacion='Tienen una mayor curiosidad intelectual y sed de conocimiento.') de la línea 45529
- línea 45532: duplicado por clave (entidad_id='jupiter|sagitario|planeta_en_signo', faceta='significado_general', fuente_id='https://www.astrolink.com/es/interpretacion/jupiter-en-sagitario', afirmacion='Tienen una mayor curiosidad intelectual y sed de conocimiento.') de la línea 45529
- línea 48707: duplicado por clave (entidad_id='pluton|escorpio|planeta_en_signo', faceta='consejo_practico', fuente_id='https://www.astrolink.com/es/interpretacion/pluton-en-escorpio', afirmacion='Se aconseja no usar la energía sexual para beneficio propio.') de la línea 48704
- línea 48708: duplicado por clave (entidad_id='pluton|escorpio|planeta_en_signo', faceta='consejo_practico', fuente_id='https://www.astrolink.com/es/interpretacion/pluton-en-escorpio', afirmacion='Se aconseja no sucumbir a la tentación de usar el magnetismo personal para beneficio propio.') de la línea 48703

### AVISAR · `afirmaciones_libros/afirmaciones_libros.jsonl`

- línea 9653: duplicado exacto de la línea 9576
- línea 9641: duplicado por clave (entidad_id='tarot-mayor-04', faceta='simbolismo', fuente_id='TarotOfTheMagiciansByOswaldWirth', afirmacion='En la numerología teosófica del tarot, el número 4 se reduce a 1 mediante la suma de los números que lo preceden.') de la línea 9555
- línea 9653: duplicado por clave (entidad_id='tarot-mayor-11', faceta='simbolismo', fuente_id='TarotOfTheMagiciansByOswaldWirth', afirmacion='En el tarot cabalístico, los arcanos 8, 11 y 14 se consideran intermediarios o relacionados con el alma.') de la línea 9576
- línea 15437: duplicado por clave (entidad_id='luna|conjuncion|sol|aspecto', faceta='significado_general', fuente_id='astrologia-predictiva-tito-macia', afirmacion='Este tránsito representa un momento para dejar atrás una parte importante de la vida anterior y comenzar de nuevo.') de la línea 15374

### AVISAR · `afirmaciones_libros/procesados.jsonl`

- línea 2083: duplicado por clave (hash_seccion='2e6bd7dc71f59cff5b3557546bbb4c208c528d2dc54b8b0db1696b94caf31166', entidad_id='tarot-mayor-05', faceta='simbolismo') de la línea 2071
- línea 2084: duplicado por clave (hash_seccion='2e6bd7dc71f59cff5b3557546bbb4c208c528d2dc54b8b0db1696b94caf31166', entidad_id='tarot-mayor-05', faceta='correspondencias') de la línea 2068
- línea 2786: duplicado por clave (hash_seccion='d877a418bd6524424ab3973a5deaaeba4b5f7a7b9bfcfb8a6423459fbdf8458e', entidad_id='tarot-mayor-13', faceta='significado_general') de la línea 2780

### AVISAR · `evidencias_web/evidencias.jsonl`

- línea 5892: duplicado exacto de la línea 5862
- línea 5893: duplicado exacto de la línea 5863
- línea 5894: duplicado exacto de la línea 5864
- línea 5892: duplicado por clave (hash_seccion='3c9b14f274ecceb6f3a78686c8709b31b15d95df11bfc431487f7fcacb5cd7fc', entidad_id='tarot-mayor-15', faceta='significado_general') de la línea 5862
- línea 5893: duplicado por clave (hash_seccion='3c9b14f274ecceb6f3a78686c8709b31b15d95df11bfc431487f7fcacb5cd7fc', entidad_id='tarot-mayor-15', faceta='derecha_invertida') de la línea 5863
- línea 5894: duplicado por clave (hash_seccion='3c9b14f274ecceb6f3a78686c8709b31b15d95df11bfc431487f7fcacb5cd7fc', entidad_id='tarot-mayor-15', faceta='consejo_practico') de la línea 5864

### AVISAR · `libros/evidencias/evidencias.jsonl`

- línea 2085: duplicado exacto de la línea 2073
- línea 2086: duplicado exacto de la línea 2074
- línea 2786: duplicado exacto de la línea 2784
- línea 2085: duplicado por clave (hash_seccion='2e6bd7dc71f59cff5b3557546bbb4c208c528d2dc54b8b0db1696b94caf31166', entidad_id='tarot-mayor-05', faceta='correspondencias') de la línea 2073
- línea 2086: duplicado por clave (hash_seccion='2e6bd7dc71f59cff5b3557546bbb4c208c528d2dc54b8b0db1696b94caf31166', entidad_id='tarot-mayor-05', faceta='simbolismo') de la línea 2074
- línea 2786: duplicado por clave (hash_seccion='d877a418bd6524424ab3973a5deaaeba4b5f7a7b9bfcfb8a6423459fbdf8458e', entidad_id='tarot-mayor-13', faceta='significado_general') de la línea 2784

### AVISAR · `libros/manifiesto_clasicos_pd.jsonl`

- línea 11: duplicado por clave (id='sepharial_horoscope_1920') de la línea 2


## Distribuciones

### `afirmaciones_full/afirmaciones.jsonl`

- periodo: moderna=52716
- calidad: 4=24533, 5=23803, 3=4380
- dominio: escuelamaia.com=15313, www.astrolink.com=7473, grancosmos.com=7126, astrologuias.com=6029, loveplay.io=3567, eight-leaves.de=2047, horoscopelogic.com=1579, es.astro-seek.com=954, www.forotarot.net=943, tarot.ac=863 (y 14 valores más)

### `afirmaciones_full/procesados.jsonl`

- estado: ok=4666, error=47

### `afirmaciones_libros/afirmaciones_libros.jsonl`

- periodo: moderna=14772, clasica=4653
- calidad: 4=14115, 5=4586, 3=659, 2=64, 1=1
- dominio: astrologiaparadummiesraeorion6=2740, anonimo.-los-arcanos-mayores-del-tarot-ocr-1987=2262, PaulFosterCase-TarotFundamentals-1936=2024, TarotOfTheMagiciansByOswaldWirth=1681, RobertWang-TheQabalisticTarot-1983=1379, IOTTOM=1165, artofsynthesis00leoa=911, Tarot-el-arte-de-adivinar-enrique-eskenazi=905, astrology_202211=809, ChicCiceroSandraTabathaCicero-NewGoldenDawnRitualTarotKeysToThe=783 (y 14 valores más)

### `afirmaciones_libros/procesados.jsonl`

- estado: ok=5542, error=35

### `evidencias_web/evidencias.jsonl`

- periodo: moderna=14010
- calidad: 5=7968, 4=5558, 3=484
- tipo: web=14010
- idioma: es=14010
- dominio: astroideal.com=1415, escuelamaia.com=1281, tarotveraluna.com=1267, cartastarotsagrado.com=1122, tarot-secret.com=999, www.astrolink.com=662, zodiatarot.com=659, tuastral.com=653, grancosmos.com=597, mysticanswer.com=566 (y 34 valores más)

### `lecturas/lecturas.jsonl`

- periodo: None=97, clasica=75, moderna=59
- calidad: 4=125, 5=100, 3=6
- idioma: en=91, es=91, otro=49
- sistema: astrologia=167, tarot=30, numerologia=26, baraja_espanola=6, otro=2

### `lecturas/procesados.jsonl`

- calidad: 1=594, 4=125, 5=100, 2=53, 3=6
- estado: rechazada=647, aceptada=231
- sistema: astrologia=360, tarot=351, numerologia=89, otro=65, baraja_espanola=13

### `libros/evidencias/evidencias.jsonl`

- periodo: moderna=12074, clasica=5375
- calidad: 4=12080, 5=3352, 3=1722, 2=284, 1=11
- tipo: libro=17449
- idioma: en=8890, es=7759, otro=800
- dominio: la-via-del-tarot-alejandro-jodorowsky=1180, gramaglia-e.-astrologia-hermetica-ocr-2006=966, astrology_202211=803, astrologiaparadummiesraeorion6=709, anonimo.-los-arcanos-mayores-del-tarot-ocr-1987=660, messageofstarses00heiniala=614, dlscrib.com-pdf-oswald-wirth-the-tarot-of-the-magicians-dl_5b8b09b0d8e84b6124ebf1e5ea4e6837=595, meditations-on-the-tarot=558, PaulFosterCase-TarotFundamentals-1936=556, the-star-1=549 (y 63 valores más)

### `libros/manifiesto_clasicos_pd.jsonl`

- familia: astrologia=7, baraja=2, numerologia=2
- estado: ok=10, fallido=1

### `muestras/muestras.jsonl`

- calidad: 4=1322, 5=1155, 3=212, 2=20, 1=3
- nivel: afirmaciones=1730, libros=542, web=424, lecturas=16
- sistema: None=2696, astrologia=6, baraja_espanola=3, numerologia=3, tarot=3, otro=1

### `muestras/prerevision.jsonl`

- nivel: afirmaciones=1730, libros=542, web=424, lecturas=16

### `piloto_fase1/piloto.jsonl`

- familia: astro_natal=3, cruz_celta=3, numerologia=3, tarot_1=3, tarot_3=3, tarot_pregunta=3, sinastria=2, tarot_2=2

### `piloto_fase1/piloto_errores.jsonl`

- familia: sinastria=1, tarot_2=1

### `plan_recuperacion.jsonl`

- familia: astrologia=473, tarot=75, numerologia=72, baraja_espanola=40

### `web/calidad.jsonl`

- dominio: escuelamaia.com=120, www.astrolink.com=120, www.mercurioretrogrado.com=120, grancosmos.com=72, astrologuias.com=48, loveplay.io=45, www.euroresidentes.com=33, eight-leaves.de=25, horoscopelogic.com=24, www.forotarot.net=20 (y 16 valores más)

### `web/manifest.jsonl`

- familia: astrologia=1794, tarot=1099, numerologia=567, baraja=380, baraja_espanola=130
- estado: ok=3680, cortas=287, error=3
- dominio: ritmolunar.com=271, astrochart.co=240, www.yourastrallife.com=216, enastrologico.com=192, astrolink.com=120, escuelamaia.com=120, mercurioretrogrado.com=120, tailoredmoon.com=120, www.astrocosmo.cl=117, fernandoangelcoronado.es=116 (y 70 valores más)
