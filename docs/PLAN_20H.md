# Plan de trabajo de las IAs: 20 horas más (desde 2026-10-20 ~21:15)

## Restricción que manda
Las IAs y los trabajos de máquina comparten nodo1 y nodo2. Medido hoy: pasada de afirmaciones de libros (T38) ~445 evidencias/h (5.200 de 17.410 hechas; faltan ~27 h) y pasada web ~500/h (4.526 de 14.010; faltan ~19 h). Por eso las pistas nuevas son sobre todo código que NO consume LLM (herramientas, tests, auditorías) y las ejecuciones con LLM se limitan a pruebas pequeñas o a trabajos ya en marcha. Reparto: solo a las pestañas que queden libres; no interrumpir a las que trabajan.

## En ejecución (máquina)
- Afirmaciones web por tandas de 500 (`afirmaciones_full/`), ~19 h.
- Afirmaciones de libros (T38, PID propio), ~27 h; el consenso con la KB se calcula al final.
- En marcha como pistas: T38 (cierre), T45 (verificador multi-turno), T47 (evidencias de sitios nuevos), T49 (piloto fase 1), T53 (cartas en inglés y reproceso de Waite), T54 (revisor local).

## Cola de pistas (orden de asignación)
Con SIGUIENTE.md ya escrito: **T55** fuentes clásicas de dominio público (astrología, numerología, baraja española) y su descarga; **T56** conjunto de evaluación y evaluador del modelo.
Por escribir cuando haga falta (dependen de lo que salga de las anteriores):
- **T57** constructor de la KB v2 a partir del consenso de afirmaciones (web + libros) con discrepancias entre tradiciones marcadas y diff contra `kb/*.json` (tras T38).
- **T58** ejecutor de la generación de fase 1 sobre `jobs.db` con `fase1_prompts` + `verificar_lectura`, reintento y reanudación; copia previa de `jobs.db` (tras T49; no reanudar los generadores viejos PID 66101/66396).
- **T59** ensayo de punta a punta con 200 ejemplos: generar, validar, `build_dataset`, `merge_final`, informe de auditoría del dataset (tras T58 y T45).
- **T60** extracción de afirmaciones de las fuentes nuevas (T36/T42/T55) con `--orden calidad` y juicio de cobertura v2 (tras T47 y T55).
- **T61** segunda iteración de recuperación dirigida con la matriz v2 y la lista de huecos restantes; decisión de recorte de objetivos de cobertura.
- **T62** guía de entrenamiento: comprobar `GUIA_REENTRENAMIENTO.md` con un entrenamiento de humo sobre un dataset diminuto (solo cuando los nodos estén libres; decisión del usuario).
- **T63** ronda 3 de auditoría adversa (multiturno, evaluador, prerevisión, revisor, nuevos módulos).
DeepSeek (pestaña 6) solo 10:00–24:00; Qwen (pestaña 7) solo si las demás están ocupadas. Pestañas 8 y 9: del usuario.

## Hitos
- 5 h: T54 y T56 integradas; T53 con menores de Waite recuperadas; T47 con matriz v2; piloto de fase 1 medido.
- 10 h: T55 con ≥ 10 clásicos descargados; KB v2 construible (T57); runner de fase 1 listo.
- 20 h: afirmaciones web y de libros terminadas y con consenso; ensayo de 200 ejemplos de punta a punta; evaluador con línea base. La generación completa y el entrenamiento esperan a la revisión humana (el usuario) y a decidir el hito de cobertura.

## Decisiones pendientes del usuario
Revisión del 3 % (usar `revisor.html` de T54 y `prerevision.md`); tratamiento de libros no españoles (55,7 % de la muestra de libros); redefinir el hito de cobertura; compra de libros; respuesta de Hugging Face.

## Decisión del usuario (2026-10-20 22:45): terminar primero la recopilación de datos
Prioridad en los nodos: acabar las pasadas de afirmaciones (web y libros), las evidencias de los sitios y clásicos nuevos (T47, T53, T57) y el consenso/KB v2; la generación completa de fase 1 espera. Medido: nodo1 admite concurrencia (4 peticiones a la vez no son más lentas que 1); nodo2 va más justo. La pasada web se relanzó con `--workers 8 --orden calidad --min-calidad 4 --timeout 180` (log `afirmaciones_full/run_v2.log`, reanudable). Las pistas nuevas que pidan LLM solo se asignan si son de recopilación; el resto, código sin LLM o esperar. El piloto de fase 1 (T49) midió ~64 s por lectura: 10.000 lecturas serían ~59 h con 3 workers.
