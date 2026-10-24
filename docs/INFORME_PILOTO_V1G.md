# Informe de preparación para el primer entrenamiento (dataset v1g)

Fecha: 24/10/2026. Autora: coordinadora (Claude). Datos: `/Users/angelgonzalez/fase0/dataset_fase1_v1g/`.
Base técnica: `docs/PREPARACION_PILOTO.md` (T139), `docs/ARMAR_DATASET_V1G.md` (T146).

## Veredicto

**Se puede lanzar un primer entrenamiento de prueba (piloto) con v1g.** No es el entrenamiento
definitivo: sirve para comprobar que la tubería funciona y para ver qué sabe hacer el modelo.

Recomendación: **empezar por el modelo pequeño (Qwen2.5-7B, QLoRA) para iterar**, y reservar el
14B para cuando los datos estén decididos. El 7B tarda unas 44 h en las estimaciones del proyecto
frente a unas 97 h del 14B; un fallo de datos descubierto tarde en el 14B cuesta cuatro días.

El semáforo automático del comprobador sale **ROJO**, pero por un único motivo bloqueante
(no hay multiturno real), que no impide entrenar: impide *medir* esa capacidad.

## Qué hay (v1g)

| Conjunto | Filas | Tokens medios (estim.) |
|---|---|---|
| train | 10.909 | 1.926 (p95 3.336, máx. 5.148) |
| val | 704 | 1.806 |
| test | 702 | 1.836 |
| **Total** | **12.315** | |

Pasos de entrenamiento (lote efectivo 16, 3 épocas): unos 2.046.

Comprobado por mí con casos propios, no solo con los tests de las IAs:
- 0 prompts de val o test que aparezcan también en train; 0 coincidencias entre val y test.
- 0 respuestas con chino o cirílico, 0 claves, 0 respuestas vacías o muy cortas en los bloques nuevos.
- Voseo: se retiraron 15 filas y los bloques regenerados hoy tienen 0.
- Los tests y `check.sh` pasan (CHECK OK tras cada integración).

## Composición del train (por bloque)

Lectura completa 16 %, tarot 3 cartas 11 %, astro natal 11 %, baraja española 3 naipes 7 %,
tarot 1 carta 7 %, sinastría 4 %, tarot con pregunta 4 %, cruz celta 4 %, tránsitos 3 %,
biorritmos 3 %, revolución solar 3 %, fuera de alcance 3 %, numerología 2,5 %, ética 2,1 %,
baraja española 1 naipe 2 % y otros. Hay 445 filas (4 %) sin bloque asignado.

Lo que más pesa es tarot y astrología. Numerología, ética, baraja española y fuera de alcance
son minoritarias pero ya tienen val y test medibles.

## Lo que mejoró hoy

| Problema | Antes | Ahora |
|---|---|---|
| Fugas train → val/test | 274 pares | 0 |
| Filas corruptas de «fuera de alcance» | 398 | retiradas; 400 nuevas (320 train) |
| Datos de cálculo inventados | 260 filas | retiradas |
| Numerología en test | 0 | 20 |
| Ética | 5 filas de train, 3 en val | 224 / 28 / 28 |
| Baraja española 1 naipe | 46 train | 223 / 28 / 27 |
| Voseo | 12-15 filas | retiradas (0 en bloques nuevos) |

## Riesgos y huecos (de mayor a menor)

1. **Multiturno real: no existe.** Las 387 filas «consulta con contexto» llevan contexto en el
   prompt, pero son un solo turno. El modelo no aprenderá a conversar en varios turnos.
   *No bloquea el piloto.* Decisión: entrenar sin él y añadirlo en una versión posterior.
2. **Markdown: unas 6 de cada 10 respuestas** de train llevan negritas, títulos o listas
   (medido con una regla amplia; el recuento anterior por otra regla era 5.823 sobre v1e).
   El modelo aprenderá ese estilo. Es **decisión tuya**: dejarlo o quitarlo en una versión
   posterior. Un solo estilo coherente es mejor que una mezcla.
3. **Respuestas largas:** 74 filas de train (0,68 %) pasan de 4.096 tokens. Con `max_length=4096`
   se truncan. Poco volumen, pero afecta a lectura completa. Opciones: subir a 6.144 (más
   memoria y tiempo) o dejarlo así en el piloto.
4. **Dos «system prompts» distintos** (tarotista y una variante de quiromancia). Conviene
   unificarlos antes del entrenamiento definitivo. En el piloto el efecto es pequeño.
5. **Lectura completa** al 65 % del objetivo previsto y **tránsitos** con plantillas
   parecidas: riesgo de respuestas repetitivas en esos dos bloques.
6. **Tokenizador de Qwen no instalado:** todas las cifras de tokens son estimaciones
   (caracteres / 3,5). No bloquea; el entrenador lo calculará con precisión. Decisión tuya
   instalarlo para cifras exactas.
7. **Calidad de la fuente:** hay celdas de conocimiento con contaminación cruzada (Leo
   arrastra consejos de Géminis; el 3 mezcla otros números). Afecta a pocas celdas.

## Qué NO está resuelto y sé que no lo está

- No he leído el dataset entero; hago comprobaciones automáticas y muestreos (30 muestras por
  bloque nuevo, revisadas por la IA y por mí en parte). Falta tu **revisión manual del 3 %**
  (`muestras_v2/revisor.html`), que es la mejor protección contra un fallo que nadie ha visto.
- La **legalidad de los textos** de los libros sigue sin revisar (decisión tuya aplazada).
  Para un piloto interno no es un obstáculo; sí lo será antes de publicar un modelo.
- El dataset enseña **estilo y estructura**, no garantiza exactitud astrológica ni de tarot:
  el modelo puede equivocarse con cartas o posiciones poco frecuentes.

## Plan propuesto

1. **Piloto 7B (nodo1, menú K «plain»)** con v1g tal cual, 1-2 épocas primero para ver curvas.
2. **Evaluar** con los 30 prompts adversarios de `docs/PREPARACION_PILOTO.md` §4 y las métricas
   deterministas (idioma, longitud, predicciones peligrosas, cartas coherentes). Comparar con
   el modelo base sin entrenar.
3. **Decidir con datos:** markdown, multiturno, `max_length`, qué bloques reforzar.
4. **Versión 2 del dataset** (libros nuevos recomendados, catálogo de astrología ampliado,
   multiturno) y piloto 14B.

## Decisiones que necesito de ti

| # | Decisión | Mi recomendación |
|---|---|---|
| 1 | ¿Lanzar piloto 7B con v1g? | Sí |
| 2 | Estilo markdown | Dejarlo en el piloto y decidir tras ver resultados |
| 3 | Multiturno real | Posponer a v2 |
| 4 | `max_length` 4.096 o 6.144 | 4.096 en el piloto |
| 5 | Instalar el tokenizador | Sí (ligero, da cifras exactas) |
| 6 | Revisión manual del 3 % | Hacerla mientras entrena el piloto |
