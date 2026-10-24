# Hoja de ruta y traspaso (histórica, 21/10; el traspaso vigente es docs/CONTINUAR.md)

Leer primero esto, después `docs/ESTADO_Y_PENDIENTES.md` (sección 8h, de T104) y `docs/PIPELINE.md`.
Rol de Claude aquí: **coordinadora** (no programa; sin subagentes `Agent`; git SOLO local; las IAs opencode de las pestañas de Warp programan en `.worktrees/<pista>`; Claude revisa con casos adversos propios, integra con `git merge --no-ff` + `./finetune/scripts/check.sh` = CHECK OK y reasigna).

## 1. Objetivo

Modelo de lenguaje en español, de calidad, para lecturas de **tarot (78), baraja española (40), astrología occidental y numerología (+ biorritmos)**, con producto final app web monetizada. Se entrena con un dataset (fase 1) generado a partir de una base de conocimiento verificada (fase 0). Decisión fija del usuario: **calidad por encima del plazo**, poco presupuesto, legalidad de los textos aplazada pero con procedencia conservada.

## 2. Qué se ha hecho (y para qué)

**Recopilación (fase 0) — para tener conocimiento fiable con procedencia**
- Pipeline web/libros → evidencias (juez LLM) → afirmaciones → consenso entre fuentes → KB v2.
- Fuentes nuevas: sitios de baraja española, numerología y astrología (T36, T42, T64, T74, T79, T86), clásicos de dominio público (T55, T57; Waite reprocesado T53), 4 rondas de descubrimiento sin repetir dominios.
- Limpieza para que el conocimiento no esté contaminado: libros con Sol/Luna astrológicos tomados como cartas, títulos de otra carta (T53, T71: 4.007 evidencias retiradas); filtro de atribución de entidad en astrología/numerología (T88/T90: propone retirar 2.188, **aún sin aplicar a producción**).
- Consenso completo (3.688 celdas entidad×faceta), deduplicado (1.274 filas duplicadas por dos procesos), con exclusión de 3.935 afirmaciones de evidencias retiradas; **KB v2** construida (tarot 78, astrología 401, numerología 65, baraja 40 entidades; cobertura con núcleo mayoritario: tarot 88,7 %, astro 31,6 %, numero 32,3 %, baraja 33,5 %). Cobertura v3: 304/7.455 celdas completas (4,1 %; criterio estricto: ≥5 fuentes independientes, ≥1 clásica, ≥2 modernas, ≥1 en español).
- Pasada rápida de afirmaciones con Mercury 3 (T69: 14.188 evidencias; T94 parada en 2.214/10.512): complemento, no sustituto (T68: cobertura baja; T76: Mercury NO sirve para el consenso, ARI 0,41).
- Inventario de procedencia/licencias (T84) listo para la revisión legal futura.

**Dataset (fase 1) — para entrenar el estilo, la estructura y la ética**
- Prompts y verificador determinista (T44, T45, T49, T72), tiradas largas con esquema obligatorio, familia **baraja española** nueva (KB provisional de 40 naipes, T72, T80, T89), `generate_tasks.py` con 12.902 tareas (12.536 pendientes), ejecutor reanudable (T62, T75, T89, T95) con backend local o Mercury.
- Piloto Mercury 3 (T83): 93 % de aprobación, 4,1 s/lectura (local: ~170 s). Se decidió generar con Mercury (usuario apagó «Improve the model for everyone» en Inception el 2026-10-21; términos: las salidas se pueden usar para entrenar; coste ~7 USD).
- **Generación real (T100) en curso** → `fase0/fase1_mercury/{aceptadas,rechazadas}.jsonl` (campo `generador: mercury-3`).
- Auditorías adversas rondas 4, 5 y 6 (T63, T81, T96) y sus arreglos (T67, T91, T101, T101b, T101c, T101d): el verificador ya rechaza cartas inventadas, orientaciones mal asignadas, promesas, diagnósticos, consejos médicos y fuga de evaluación; `reverificar_fase1.py` relee lo generado con el verificador vigente (hoy 5.921/5.931 válidas).
- Evaluación: 240 casos fijos (T56, semillas reservadas 560056-560058, nunca en entrenamiento); **línea base sin entrenar** de Flash Next (T99): 74,6 % bruto, ≈86 % ajustado; peor: tránsitos 1/20, astro natal 50 %, numerología 45 %.
- Preparación del entrenamiento (T61): `preparar_entrenamiento.py`, plantillas QLoRA 7B/14B, guía.
- Revisión humana del 3 %: `fase0/muestras_v2/revisor.html` (6.982 fichas sobre datos vigentes, `docs/REVISION_3PC.md`); **pendiente del usuario**.

**Infraestructura**
- halogen-flash-server actualizado a **0.18.13** en ambos nodos (2026-10-21; rollback en `~/halogen-sandbox/bak-0174`; procedimiento en Letta).
- Backend rápido **Mercury 3** (Inception, tokens gratuitos, ~100 M de cuota, unos 28+ M gastados): clave solo por variable de entorno `INCEPTION_API_KEY`, nunca en repo/logs.
- **Nodo1 reservado** por el usuario (llama.cpp Qwen3.8-27B-abliterated Q5_K_L para otro proyecto urgente; halogen parado; script `~/iniciar-servidor.sh` del nodo1 con flags por defecto). Nodo2 con Flash Next 0.18.13 para el proyecto (≤2-3 workers).
- Copias: bucle de backup cada 3 h (`scratchpad/copias.sh` → `fase0_backups/`), `salud_datos.py`.

## 3. Estado al cerrar la noche (actualizar)

Ver el apartado «Estado final de la noche» al final de este fichero (lo rellena Claude al acabar las tareas).

## 4. Qué queda por hacer — checklist ordenada para mañana

1. **Integrar** las pistas que queden abiertas (T100, T103, T104, T92 y lo que haya) con `git merge --no-ff` + `check.sh`. Vigilante: `scratchpad/vigia21.sh`; estado: `scratchpad/estado.sh`; latido: `scratchpad/latido.sh` (si no existen, `git worktree list` y los ESTADO.md de `.worktrees/`).
2. **Terminar la generación de fase 1** (T100) y pasar `reverificar_fase1.py` sobre `fase1_mercury/aceptadas.jsonl`; relanzar rechazadas/pendientes si hace falta; revisar 6 lecturas a mano por familia.
3. **Armar el dataset v1** con `armar_dataset_v1.py` (T103): reverificar → fuga de evaluación → duplicados → ShareGPT → validate_synthetic → build_dataset → merge_final → `preparar_entrenamiento` (semáforo). Salida en `fase0/dataset_fase1_v1/`. No tocar `corpus/final` sin revisar.
4. **Relanzar la pasada rápida T94** (Mercury, `--workers 1`, reanudable) cuando T100 haya terminado; luego añadir al consenso (`--extra-afirmaciones` + `--rehacer-celdas-con-extra`) **solo las celdas que ganen fuentes independientes** (comando y filtro en el ESTADO.md de la rama t94).
5. **Aplicar el cierre pendiente** con `finetune/corpus/cierre_recopilacion.py` (solo con TODOS los procesos escritores parados; empieza con `--dry-run`): paso 3 filtro de atribución (T88/T90), paso 4 consenso con las dos listas de exclusión, KB v2, cobertura v3, informe de cierre. Revisar antes la muestra de retiradas (`fase0/filtro_atribucion/muestra_revision.jsonl`).
6. **T97 (recopilación continua, pestaña 7): EMPEZAR DE CERO.** Apenas había empezado (sin commits ni descargas); el usuario ordenó (2026-10-21) dejarla toda para mañana y que arranque limpia. Cuando el usuario avise de que halogen vuelve a arrancar en el nodo1 (la pestaña 7 usa ese modelo): enviar a esa pestaña (verificando el título con `scratchpad/ia_send.sh`) `/new` + el prompt corto de siempre con la ruta `.worktrees/t97-recopilacion-nocturna` y su `SIGUIENTE.md` (ya escrito; actualizar antes la lista de dominios ya usados con `fuentes_nuevas_t97`/`t79`/`t86` y revisar los directorios `fase0/web_recup6+` por si hubiera restos). No enviar `continue`. Juzgar las evidencias web nuevas que produzca y extraer sus afirmaciones.
7. **Levantar halogen Flash Next en el nodo1** cuando el usuario libere el nodo (mismo método que la actualización 0.18.13: `ssh bosgame`, lanzar `flash_serve` con los flags de `~/halogen-tui.sh` y el wrapper de la API en `:8000`).
8. **Usuario: revisión del 3 %** con `revisor.html` (muestras_v2). Sus veredictos deciden qué fuentes/familias reforzar.
9. **Entrenar**: 7B QLoRA de iteración rápida (`finetune/entrenamiento/qlora_7b.yaml`, `comprobar_entorno.sh`, `GUIA_REENTRENAMIENTO.md`) cuando haya nodo libre (hoy el nodo1 está reservado) → evaluar con `evaluar_modelo.py` y comparar con la línea base de T99 (umbrales propuestos en `docs/LINEA_BASE_MODELOS.md`) → 14B final.
10. **Seguir recopilando** donde la KB es floja (baraja española, astrología avanzada: planeta en casa, aspectos): nuevas rondas de fuentes, fuentes clásicas cuando vuelva `archive.org`; posible compra de algún libro de baraja española (Salas) si el usuario lo aprueba.
11. **Auditoría ronda 7** tras los cambios del día siguiente (DeepSeek solo de 10:00 a 24:00).

## 5. Decisiones del usuario aún abiertas

- Revisión del 3 % (sin hacer).
- Tratamiento de libros no españoles (55,7 % de la muestra de libros).
- Redefinir el hito de cobertura (el 10 % de celdas completas exigiría unas 24.700 fuentes; hoy 4,1 %): ¿suficiente la KB v2 con RAG en inferencia?
- Compra de libros (baraja española), respuesta de Hugging Face (`Pepere45/spanish-esotericism-corpus`), esqueleto del backend de la app (pregunta sin respuesta).
- Probar Qwen 27B (halogen-server) frente a Flash Next con el evaluador (propuesto, no hecho).
- ds4/DeepSeek V4.1 Flash en un nodo: solo curiosidad, no instalar.

## 6. Reglas fijas (no reabrir)

- Git local siempre; nunca push ni remotos. Responder en español estándar.
- No comprar sin avisar y justificar; solo fuentes legales; no saltar bloqueos (astro.com, nymero.org, Reddit); ≤1 petición/s por dominio, robots.txt.
- No repetir credenciales (HOMELAB.md ni la clave de Inception); peekaboo solo con pantalla desbloqueada y sin insistir; volver siempre a la pestaña 1; **pestañas 8 y 9 del usuario** (ia-servidores, etc.): no tocar salvo lo asignado (la pestaña 8 actual es la IA de Mercury; ver `reference_pestanas_warp_ias.md` en la memoria).
- DeepSeek (pestaña 5) solo 10:00–24:00. **Nodo1 (10.0.0.3) reservado** hasta que el usuario lo libere; todo el LLM local solo contra el nodo2 (`http://10.0.0.4:8000/v1`).
- Antes de integrar una pista: revisar con casos propios (no fiarse de los tests de la IA); `TRACK COMPLETO` puede ser falso. Ajustes a una IA: escribir en `SIGUIENTE.md` y enviarle el aviso.
- Generadores viejos (PID 66101/66396) NO reanudar. Copia de `jobs.db` antes de `--replace-pending` (hay `jobs.db.antes-t80`).
- No usar LM Studio personal del iMac; usuario no quiere explicaciones de las tareas (solo estado y el prompt).
- Las posiciones Y de la barra lateral de Warp cambian al cambiar los títulos de las pestañas: **verificar el título** antes de enviar (`scratchpad/ia_send.sh` lo imprime).

## Estado final de la noche y mañana del 2026-10-22 (actualizado 10:15)

- **Integrado desde la noche:** T112 (dataset v1b), T113 (generación complementaria: 2.242 lecturas válidas de sinastría, tránsitos, revolución solar, biorritmos, fuera_alcance + 65 astro_natal regeneradas; arreglo del signo en biorritmos verificado con casos propios), T116 (traductor EN→ES con glosario y verificador), T117 (dataset **v1c**: 12.796 filas, train 11.563 / val 609 / test 624, 20 bloques, QA verde; 0 solapes, 0 fugas).
- **Hallazgos abiertos:** transitos retiene 208/400 en v1c (el filtro de fugas por n-gramas descarta 139; T124 lo analiza y genera ≥300 nuevas); `fuera_alcance` tiene 120/400 preguntas basura (solo contadas; decisión del usuario); T107 no se aplicó a la jobs.db real (superado por la salida de T113).
- **Libros comprados** (uso interno, copyright, en `fase0/libros_comprados/`; el PDF de Sasportas está incompleto: 63 hojas ≈ 126 de ≈300 páginas): Nichols (T114), Pollack y Greer (T115), Arroyo y Sasportas (T118 prepara texto; T119 evidencias). Traducción de afirmaciones EN→ES: T125.
- **Modelo nuevo en nodo1** (kingjones777 ROCmFP4 imatrix, instalado y verificado, **sin probar**): `~/iniciar-qwen38-kj.sh` (entrada K del menú de `~/iniciar-servidor.sh`; plantilla parcheada `~/qwen38-kj-system-ok.jinja`; puerto 8003) y entrada opencode `Qwen38-KJ-nodo1`. Nodo1 sigue reservado por el usuario.
- **Plan del día:** `docs/PLAN_DIA_2026-10-22.md` (cola por IA hasta las 20:00). Pistas preparadas: T118, T119, T121, T123, T124, T125, T126.
- **Incidencias de operación:** pantalla bloqueada ≈10:01 (peekaboo imposible; no insistir; hay un sondeo cada 10 min); una IA editó `armar_dataset_v1.py` en `main` en vez de su worktree (copia del parche en el scratchpad; revertido); pestaña 7 sin IA hasta nueva orden (aparece una sesión `opencode -c` ajena: no tocar).
