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
