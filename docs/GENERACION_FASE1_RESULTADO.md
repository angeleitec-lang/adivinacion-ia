# Resultado de la generación de fase 1 (T100)

Fecha: 2026-10-21. Backend: Inception Mercury 3 (`mercury-3`) vía
`https://api.inceptionlabs.ai/v1`, autenticado con `INCEPTION_API_KEY`.

## Resumen

- Evidencias pendientes a procesar: 12.536 (jobs.db).
- Familias lanzadas: 14 (se excluyó **sinastria**, 600 pendientes, por no
  superar el umbral en la muestra; ver sección 5 de ESTADO.md).
- Pendientes realmente lanzadas: 11.936 (+ 6 huérfanas recuperadas = 11.942).
- Procesadas: 11.942.
- **Aceptadas: 11.851 (99,2 %).**
- Rechazadas: 91.
- Errores de red (RateLimitError/429): 29, todos reintentados con éxito;
  ninguno superó el umbral del 20 % en ventana de 50 (la pasada no se detuvo).
- Tokens estimados: entrada ~10,53M + salida ~11,38M ≈ **~21,9M** (no se
  registran métricas exactas por registro; salida estimada a ~3,8 chars/token
  desde la longitud media de 3.650 chars).

## Aceptadas / rechazadas por familia

| Familia | Aceptadas | Rechazadas | Total | Aprobación |
|---|---|---|---|---|
| lectura_completa | 2989 | 11 | 3000 | 99,6 % |
| astro_natal | 1434 | 66 | 1500 | 95,6 % |
| tarot_3 | 1399 | 1 | 1400 | 99,9 % |
| tarot_1 | 939 | 3 | 942 | 99,7 % |
| espanola_3 | 897 | 3 | 900 | 99,7 % |
| tarot_pregunta | 800 | 0 | 800 | 100 % |
| multiturno | 796 | 4 | 800 | 99,5 % |
| cruz_celta | 500 | 0 | 500 | 100 % |
| espanola_1 | 400 | 0 | 400 | 100 % |
| espanola_5 | 400 | 0 | 400 | 100 % |
| tarot_2 | 399 | 1 | 400 | 99,8 % |
| numerologia | 399 | 1 | 400 | 99,8 % |
| etica | 300 | 0 | 300 | 100 % |
| espanola_7 | 199 | 1 | 200 | 99,5 % |
| **Total** | **11851** | **91** | **11942** | **99,2 %** |

## Rechazadas por motivo

| Motivo | N |
|---|---|
| respuesta_truncada (lectura cortada antes de cerrar) | 71 |
| Menciona orientación invertida sin cartas invertidas | 11 |
| Menciona carta ajena a la tirada (El Sol) | 4 |
| Menciona carta ajena a la tirada (La Luna) | 3 |
| Promesa vedada «garantía de que» | 2 |
| Falta carta de la tirada (La Emperatriz) | 1 |
| Promesa vedada de juego/apuestas «apuesta» | 1 |

El motivo dominante es `respuesta_truncada` (71/91), concentrado en
`astro_natal` (66) por ser la familia más extensa; requieren máx. 3.072 tokens y
con ~3,8 chars/token se quedan cortas en los casos más largos. Aun así, la tasa
global de rechazo es baja (<1 %).

## Revisión manual de 6 lecturas

Muestra semilla 7, una por familia representativa.

1. **tarot_1 (id 10962)** — Seis de Bastos invertida, amor, comunicación.
   Interpretación correcta y alineada con la referencia (orgullo/reconocimiento
   bloqueados). Español claro y natural, tono empático, sin invenciones fuera de
   base. Incluye advertencia de no-certeza («no desde la certeza»). Longitud
   2.688 chars. Calidad: buena.
2. **tarot_3 (id 12279)** — Pasado/presente/futuro (As de Copas, Emperatriz,
   Nueve de Bastos), amor. Estructura especial, usa solo las tres cartas dadas,
   conecta bien la narración. Español correcto. Longitud 4.175 chars. Calidad:
   buena.
3. **espanola_1 (id 21477)** — Seis de Espadas, salud. Interpretación correcta
   (transición, mejora), no mezcla con tarot, lenguaje prudente en salud
   («no es carta de enfermedad ni alarma»). Longitud 2.083 chars. Calidad: buena.
4. **espanola_3 (id 22342)** — Tres cartas, trabajo. Narración coherente de los
   tres naipes, sin mezclar con tarot, recomendación práctica sensata. Longitud
   3.209 chars. Calidad: buena.
5. **astro_natal (id 14776)** — Carta natal (Sol Leo casa 1, Luna Capricornio
   casa 6, aspectos). Lectura estructurada y técnica, integra Sol/Urano y
   aspectos con prudencia («tendencias y posibilidades, nunca certezas»).
   Longitud 6.589 chars. Calidad: muy buena.
6. **numerologia (id 16809)** — Camino de vida 1, destino 1, año personal 2026.
   Interpretación correcta de los números, con ejemplos por área (amor, trabajo,
   dinero, salud), tono cálido y no-determinista. Longitud 4.592 chars. Calidad:
   buena.

Valoración transversal: las 6 lecturas cumplen con calidad, estilo en español
estándar y ética (sin promesas, sin diagnósticos, sin juego). No se detectaron
problemas de formato ni de mezcla de barajas.

## Archivos de salida

- `/Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl` (11.851, ShareGPT)
- `/Users/angelgonzalez/fase0/fase1_mercury/rechazadas.jsonl` (91)
- BD reanudable: `/tmp/fase1_mercury_full.db` (done 12.811 / failed 91)

## Siguiente paso

Las aceptadas se pasan por la cadena:
`validate_synthetic → build_dataset → merge_final → preparar_entrenamiento`
(ver ESTADO.md, sección 8).
