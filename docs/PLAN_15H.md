# Plan de trabajo de 15 horas (2026-10-20)

Objetivo: mantener ocupadas ≥ 90 % del tiempo las IAs halogen locales (pestañas 2-5, nodos 1 y 2) con trabajo que acerque la fase 0 a la matriz completa y prepare la fase 1. Las de pago (pestañas 6 y 7) solo en casos puntuales; la última pestaña no se toca.

## Principio de ocupación
Las IAs terminan las pistas de código en 5-30 min; para llenar horas, cada carril combina (1) pista de código y (2) una ejecución real larga sobre los nodos (juez, afirmaciones, rastreo, consenso) que la propia IA vigila. La coordinadora mantiene ≥ 1 pista preparada por carril (worktree + SIGUIENTE.md) y lanza trabajos de máquina propios en segundo plano. Un vigilante único avisa cuando una pista acaba.

## Carriles (orden de ejecución; horas aproximadas desde el inicio)
| Carril | Pestaña | h 0-3 | h 3-7 | h 7-11 | h 11-15 |
|---|---|---|---|---|---|
| A | 4 | T38 afirmaciones de libros + consenso A6 (ejecución completa de libros: horas) | T41 consenso sobre todo + alerta de contradicciones con la KB | T45 muestras 3 % y conjunto de oro (herramienta) | revisión de huecos de la matriz y reintentos |
| B | 2 | T35 unificar calculos/generate_tasks + tránsitos | T39 generador de prompts de fase 1 con «Referencia» de la KB | T40 multi-turno en dos fases | T44 piloto de generación (nodo1/nodo2) y validación |
| C | 3 | T36 sitios baraja española y numerología (descubrir y rastrear) | T42 sitios astrología (casas, aspectos, planetas) y recuperación dirigida desde las celdas bajo mínimo | T43 rastreo dirigido ejecutado + juez de lo nuevo | segunda iteración de cobertura |
| D | 5 | T37 extractor de lecturas trabajadas de libros (ejecución completa) | T46 lecturas desde transcripciones de YouTube (si se resuelve el 429) o foros | T47 juez de lecturas y puntuación ≥ 4/5 | informe F0.5 |

Trabajos de máquina de la coordinadora (en segundo plano, sin IA): extracción de afirmaciones web completa (14.010 evidencias, ya lanzada), juez de las páginas nuevas de T36/T42, `cobertura.py` tras cada bloque, vigilantes.

## Hitos y criterios
1. h 3: afirmaciones web completas y filtradas; sitios de baraja y numerología rastreados; cobertura recalculada.
2. h 7: consenso (A6) de celdas con ≥ 2 fuentes; contradicciones con la KB marcadas; lecturas de libros extraídas.
3. h 11: generador de fase 1 con referencias; multi-turno; muestras del 3 % para el usuario.
4. h 15: piloto de generación pequeño y validado (NO la generación completa sin aprobación del usuario del 3 %); matriz con < 10 % de celdas bajo el mínimo en tarot; informe.

## Riesgos y condiciones
- Las IAs comparten los nodos con los trabajos de máquina: máx. 4 workers por trabajo; si hay 429/timeouts, bajar a 2.
- Antes de la fase 1: copia de `jobs.db`, matar los generadores viejos (66101, 66396) y decidir `--min-density 2.0`.
- Decisiones del usuario pendientes: respuesta de Hugging Face (`Pepere45/spanish-esotericism-corpus`); compra de libros solo si la matriz sigue floja en baraja española tras T36; revisión humana del 3 %.
- YouTube sigue con HTTP 429: probar cookies del navegador o aplazar.
- Verificar siempre las pistas con casos adversos propios antes de integrar.

## Cola adicional
- T39 (pedida por el usuario el 2026-10-20): disponibilidad LEGAL de los libros que faltan (dominio público, bibliotecas, precios) para decidir compras. Asignar a la primera pestaña local que quede libre. Sin búsqueda de copias pirata.

## Previsión de 10+ horas (actualizada 2026-10-20 10:00)

**Cuello de botella:** los nodos 1 y 2 (las IAs de las pestañas 2-5, el juez, las afirmaciones y la extracción de lecturas comparten el mismo modelo). Más pistas en paralelo no aumentan el rendimiento; lo que importa es que cada pestaña nunca espere por falta de trabajo y que los trabajos largos corran sin parar.

**En marcha ahora (ETA orientativa):**
- T37 extractor de lecturas: pasada LLM de 878 evidencias, ~70 hechas en 20 min → ~3-4 h.
- T38 afirmaciones de libros + consenso A6: código y luego pasada larga sobre 17.449 evidencias de libros → varias horas.
- T36 sitios de baraja española y numerología: descubrir y rastrear (≈ 1-2 h más).
- T39 disponibilidad legal de libros (≈ 30-60 min más).
- Coordinadora: extracción de afirmaciones web en tandas de 500 (`afirmaciones_full/tandas.log`).

**Cola preparada (worktree + SIGUIENTE.md listos), en orden de asignación a la primera pestaña local libre:**
1. T40 calculos: revolución solar para nacidos el 29-feb y robustez (bug real, rápido).
2. T41 afirmaciones_es incremental, por tandas y priorizada (necesaria antes de relanzar la pasada completa).
3. T43 recuperación dirigida de huecos (plan de búsquedas desde la matriz).
4. T42 sitios de astrología (planetas en casas/signos, aspectos).
5. T44 prompts de fase 1 con Referencia de la KB y verificador.
6. T45 conversaciones multi-turno en dos fases.
Siguientes (por escribir cuando se liberen pestañas): T46 lecturas desde YouTube (si cede el 429), T47 juez de lecturas, T48 muestras del 3 % y conjunto de oro, T49 piloto de generación fase 1 (nodos), T50 segunda iteración de cobertura.

**Hitos (a 10 h):** celdas de tarot ≥ 60 % completas; baraja española y numerología con fuentes nuevas rastreadas y juzgadas; afirmaciones extraídas y filtradas de web y libros; consenso (A6) de las celdas con ≥ 2 fuentes; lecturas trabajadas extraídas de libros; generador de prompts de fase 1 con verificador y multi-turno listos. La generación completa de fase 1 y el entrenamiento esperan a la revisión del 3 % por el usuario.

**Regla de continuidad:** un vigilante único avisa de cada TRACK COMPLETO; al recibirlo reviso con casos adversos, integro, asigno la siguiente pista de la cola (o escribo una nueva) y vuelvo a la pestaña 1. Trabajos de máquina propios: lanzar siempre reanudables y por tandas.
