# Piloto Mercury 3 — fase 1 (T83)

Fecha: 2026-10-21. Rama `track/t83-piloto-mercury`.

## 1. Objetivo

Medir si Mercury 3 (Inception, rápido y con tokens gratuitos en la prueba) puede
generar las lecturas de entrenamiento de fase 1 con la calidad exigida, frente a
la línea base local del piloto T49 (82 % de aprobación con los nodos
10.0.0.3/10.0.0.4). Solo se mide; no se genera dataset real. No se toca `jobs.db`
ni `corpus/final`.

## 2. Metodología

- **Tareas**: 3 por familia (las 15 de `fase1_prompts.FAMILIAS`, incluidas
  `espanola_1/3/5/7`, `cruz_celta` y `lectura_completa`), semilla fija 83.
  Se reutilizan los prompts propios del proyecto (no llevan texto de libros; solo
  referencias de la KB, autorizadas).
- **Backend**: `mercury-3` en `https://api.inceptionlabs.ai/v1`,
  `reasoning_effort=instant`, `temperature=0.5` (mínimo soportado por Mercury 3;
  el rango del modelo es 0.5–1.0), `max_completion_tokens` según la tabla
  `RECOMENDACION_MAX_TOKENS` (1536–6144), concurrencia 3, reintento por causa
  (máx. 1) como en el ejecutor de fase 1.
- **Verificación**: `fase1_prompts.verificar_lectura` (determinista) + detección
  de truncamiento (`respuesta_truncada`).

## 3. Resultados (Mercury vs local)

| familia | n | ok | ok 1er intento | local (T49) |
|---|---|---|---|---|
| astro_natal | 3 | 3 | 2 | 3/3 (100 %) |
| cruz_celta | 3 | 3 | 3 | 0/3 (0 %) |
| espanola_1 | 3 | 3 | 3 | — |
| espanola_3 | 3 | 2 | 2 | — |
| espanola_5 | 3 | 3 | 3 | — |
| espanola_7 | 3 | 3 | 3 | — |
| etica | 3 | 2 | 2 | 3/3 (100 %) |
| lectura_completa | 3 | 3 | 3 | 0/3 (0 %) |
| multiturno | 3 | 3 | 3 | 3/3 (100 %) |
| numerologia | 3 | 2 | 2 | 3/3 (100 %) |
| sinastria | 3 | 3 | 1 | 3/3 (100 %) |
| tarot_1 | 3 | 3 | 3 | 3/3 (100 %) |
| tarot_2 | 3 | 3 | 2 | 3/3 (100 %) |
| tarot_3 | 3 | 3 | 3 | 3/3 (100 %) |
| tarot_pregunta | 3 | 3 | 3 | 3/3 (100 %) |
| **GLOBAL** | **45** | **42** | **38** | **82 %** |

- Aprobación **con reintento**: **93 %** (42/45). Sin reintento: 84 %.
- Línea base local: 82 % (con `max_tokens=2048` y nodos saturados; truncaba las
  tiradas largas). Con el presupuesto recomendado (T72) el local también mejora en
  `cruz_celta`/`lectura_completa`, pero aquí Mercury **ya los aprueba al 100 %**.

## 4. Longitud, truncamiento, latencia y tokens

- Longitud: media **4022 chars**, mín 972, máx 15485. Las más largas son
  `sinastria` (~12.7k avg) y `astro_natal` (~8.6k avg): verbosas, pero válidas.
- Truncadas: **1 (2 %)** (un `numerologia` cortado).
- Latencia media: **4.1 s/lectura** (incluye reintentos). El local: 169.9 s.
- Tokens (acumulados, 45 lecturas): prompt 37820, completion 57695
  (~840 prompt + ~1282 completion por lectura).

## 5. Revisión manual (6 lecturas completas)

Se revisaron a mano 2 de tarot, 2 de baraja española, 1 astro y 1 numerología
(pasaron el verificador):

| id | familia | Calidad | Ética | Español |
|---|---|---|---|---|
| tarot_1-01 | tarot_1 | Alta. Lectura coherente y empática de la Justicia invertida en salud. | Deriva a especialista al cierre; «guía, no diagnóstico». Sin promesas ni certezas. | Correcto, con tildes, tono cálido. |
| tarot_3-01 | tarot_3 | Muy alta. Relaciona las tres cartas en una historia con hilo. | «No es una sentencia», «no es un sí rotundo ni un no definitivo»; deriva a asesor financiero. | Correcto, con tildes. |
| espanola_1-01 | espanola_1 | Alta. Sota de Bastos bien interpretada en trabajo. | «Tendencia, no certeza absoluta»; «la puerta está entreabierta, decides tú». | Correcto, con tildes. |
| espanola_5-01 | espanola_5 | Alta. Cumple el esquema por posiciones con cabeceras correctas. | Tendencia, sin garantías. | Correcto. |
| astro_natal-01 | astro_natal | Alta pero muy extensa; interpreta casas/aspectos con foco en vocación. | «Mapa, no destino»; libre albedrío; sin diagnósticos. | Correcto, con tildes. |
| numerologia-01 | numerologia | Alta. Combina año personal y números de base. | «Brújula, no destino»; deriva a salud mental cuando corresponde. | Correcto, con tildes. |

**Conclusión cualitativa**: las 6 lecturas cumplen calidad, ética (sin promesas,
sin diagnósticos, sin cartas inventadas, siempre dentro de las cartas/signos/
números dados) y español estándar con tildes correctas. El tono es cercano y
empático, coherente con el system prompt.

## 6. Motivos de rechazo (3 casos)

- `numerologia-03`: truncada + contradice el año personal calculado (7) al decir
  «2026» en el texto.
- `etica-02`: promesa vedada («garantía por escrito» / «garantía que»).
- `espanola_3-01`: menciona una orientación invertida sin cartas invertidas.
Todos son corregibles con un reintento adicional o ajuste de prompt; ninguno es de
calidad estructural.

## 7. Estimación para 10.270 lecturas

- **Tiempo**: a 4.1 s/lectura → 3 workers: **3.9 h**; 6 workers: ~2.0 h.
  Frente a ~78.7 h (6 workers) del local: **~40× más rápido**.
- **Coste** (precios de lanzamiento Mercury 3: $0.10/1M input, $0.35/1M output):
  - Input: 10.270 × ~840 = ~8.6M tokens → ~$0.86
  - Output: 10.270 × ~1282 = ~13.2M tokens → ~$4.61
  - Total ≈ **$5.5** (sin contar reintentos; el orden de magnitud no cambia).

## 8. Términos de uso del proveedor (Inception)

Fuente: Terms of Use, Inception AI Inc. (vigentes desde 2025-09-01),
`https://www.inceptionlabs.ai/docs/terms-of-use`.

- **Outputs**: «Subject to your compliance with the terms of this agreement, you
  may use, modify, reproduce, distribute and display Outputs for any purpose not
  otherwise restricted herein.» → **permitido usar las salidas para entrenar otro
  modelo**, sin restricción específica de fine-tuning.
- **User Submissions (prompts)**: se concede a Inception una licencia para usar
  los prompts para «provide and maintain our Services … and train our models»,
  con **opt-out** (`Improve the model for everyone` = OFF en User Settings de la
  API Platform). Los prompts van nuestro (referencias de la KB propias), pero hay
  que tener en cuenta esta licencia si no se quiere que se entrenen con ellos.
- **Restricción relevante**: queda vedado «directly or indirectly competes …
  with Inception or the Services». Entrenar un modelo de lecturas de adivinación
  no compite con los dLLMs generales de Inception, por lo que no se ve afectado.
  La cláusula es general y no menciona fine-tuning específicamente.

**Conclusión de términos**: los términos **no prohíben** usar las salidas para
entrenar otro modelo y lo habilitan explícitamente («for any purpose not otherwise
restricted»). El único matiz es la licencia de los prompts hacia Inception (con
opt-out disponible) y la cláusula general de no competencia, que no aplica a este
uso.

## 9. Conclusión y recomendación

Mercury 3 aprueba el verificador en **93 %** (frente a 82 % local) con una
**latencia ~40× menor** (~4.1 s frente a ~169.9 s) y un **coste insignificante**
(~$5.5 para las 10.270 lecturas en la franja de lanzamiento). La revisión manual
de 6 lecturas confirma calidad, ética y español correctos.

**Recomendación: USAR.** Mercury 3 es viable para generar el corpus de
entrenamiento de fase 1 en horas (no ~120 h), con aprobación superior a la local y
coste mínimo. Consideraciones:

1. Usar `max_completion_tokens` recomendado por familia (y subirlo para
   `sinastria`/`astro_natal` si se quieren lecturas menos extensas o se ajusta el
   prompt para recortar verbosidad).
2. Mantener la verificación automática en el pipeline (filtra el 7 % restante) y
   valorar 2 reintentos para los pocos rechazos corregibles.
3. Respetar el opt-out de «Improve the model for everyone» si no se desea que
   Inception entrene con los prompts.
4. Descontar el coste real (precios fuera de lanzamiento) si se escala fuera de
   la franja promocional.
