# CONTINUAR — traspaso para la próxima sesión (escrito el 24/10/2026)

> Este fichero se carga solo al abrir Claude Code en este proyecto (import desde `CLAUDE.md`).
> Al empezar: **no preguntes al usuario qué toca; ejecuta la sección 1** y retoma desde ahí.

## 1. Primeros pasos al abrir sesión (en este orden)

1. `cd /Users/angelgonzalez/adivinacion-ia && git status --short && git log --oneline -8 && git worktree list`.
2. `./finetune/scripts/coordinacion/estado.sh` (pistas abiertas, commits sin integrar, nodos nodo1/nodo2/Mini).
3. Mira si hay pistas con commits sin integrar (sobre todo **T148**, ver §3). Si `estado.sh` marca una con `completo=1`: revisarla con casos propios, integrar (§7) y pasar `check.sh`.
4. Lee las respuestas pendientes del usuario (§6) y dile **en 5 líneas** dónde estamos y qué propones (no un resumen largo).
5. Retoma la hoja de ruta (§5): lo siguiente es **lanzar el piloto 7B** (runbook `docs/LANZAR_PILOTO_7B.md`, lo escribe T148) y, en paralelo, el **modo profesora** (§8).

Rol: **coordinadora** (no programa; **sin subagentes `Agent`**; git **solo local**, nunca push). Español estándar, sin voseo. Al usuario: estado y lo que necesita decidir; solo se explica en profundidad en modo profesora.

## 2. Qué es el proyecto (una línea)

Modelo de lenguaje en español para lecturas de tarot (78), baraja española (40), carta astral y numerología (+ biorritmos). Hoy es sobre todo la **tubería de datos** (`finetune/`): conocimiento con procedencia → dataset ShareGPT → fine-tune QLoRA. Producto final: app web (aún sin código).

## 3. Estado al cerrar el 24/10/2026 (mañana)

**Dataset vigente: v1g** — `/Users/angelgonzalez/fase0/dataset_fase1_v1g/` (train 10.909 / val 704 / test 702 = 12.315; semáforo `resumen.json` VERDE; semáforo de `comprobar_piloto.py` ROJO solo por «sin multiturno real», no bloquea entrenar). Informe: `docs/INFORME_PILOTO_V1G.md`. Generado con `finetune/corpus/armar_dataset_v1g.py` (T146) encadenado sobre v1f (T144) ← v1e (T141) ← v1d.

**Integrado en `main` esta semana (23-24/10):** T121 cierre final, T131/T134 paráfrasis baraja, T133 y T132 TXT de ocultismo/numerología y naipes, T135 auditoría v1d, T137 propuesta de catálogo astro, T138 guía/mapa de programas (`docs/guia/`), T139 preparación del piloto (`comprobar_piloto.py`), T140 cierre 2 (fusión de fuentes nuevas), T141 dataset v1e, T136 fuera_alcance v2 (400 respuestas), T142 ética + baraja 1 naipe v2 (560), T143 y T147 (nodo1 permitido + arreglo del paso 6 de `cierre_recopilacion.py`), T144 v1f, T145 catálogo astro opción A aplicado (496 entidades, 7.664 celdas), T146 v1g.

**Pista abierta: T148** (`.worktrees/t148-preparar-piloto`, rama `track/t148-preparar-piloto`, pestaña 2 de Warp): deja listo el piloto 7B **sin entrenar** — instala el tokenizador de Qwen2.5 (solo ficheros de tokenizador), recalcula tokens exactos, prepara datos de entrenamiento de v1g hacia `/Users/angelgonzalez/fase0/dataset_fase1_v1g_preparado/`, actualiza `finetune/entrenamiento/qlora_7b.yaml` y escribe `docs/LANZAR_PILOTO_7B.md`. Revisar con casos adversos antes de integrar (¿rutas correctas? ¿cifras de tokens coherentes con 74/4/1 excedentes estimados? ¿el yaml no inventa claves de Soup?).

**Cobertura de conocimiento (cobertura_v3 real, ya regenerada con catálogo ampliado):** 7.664 celdas, 314 completas (tarot 172/936, baraja 39/480, astrología 93/5.456, numerología 10/792). Para completar hacen falta libros nuevos (§5, compras).

## 4. Datos e infraestructura (rutas y gotchas)

- Datos pesados fuera del repo en `/Users/angelgonzalez/fase0/` (`dataset_fase1_v1g/`, `fuera_alcance_v2/`, `etica_espanola1_v2/`, `cobertura_v3/`, `consenso_kb/`, `kb_v2/`, copias `_backup_*`, `cobertura_v3_pre_t145_*`). Python SIEMPRE `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python` (hay `uv`, no `pip`); tests con `unittest`; `./finetune/scripts/check.sh` debe acabar en `CHECK OK`.
- **Nodos:** nodo1 `http://10.0.0.3:8000/v1` y nodo2 `http://10.0.0.4:8000/v1` (halogen `halogen-qwen3.8-flash-next`, 4 slots cada uno). **Desde el 23/10 el usuario permite nodo1 para datos: repartir siempre entre los dos nodos** (máx. 3 workers en total entre todas las pistas; ~1 respuesta/min por worker). Los scripts validan el host por `urlparse().hostname` (solo 10.0.0.3 y 10.0.0.4).
- **Mini (10.0.0.1)** — Mac mini M2 Pro, 32 GB. Desde 24/10 09:13 sirve **Ornith 1.5 35B-A3B uncensored (MLX 4 bits, solo texto)** en el puerto 8000 con `mlx_vlm.server` (launchd `com.homelab.mlx-vlm`). La ruta antigua `~/models/Qwen3-VL-30B-A3B-Instruct-4bit` es un **enlace simbólico** a Ornith (los clientes piden el modelo por esa ruta y `mlx_vlm` carga lo que lleve la petición; con otra ruta cargaría un segundo modelo y agotaría la RAM). El Qwen3-VL real está en `~/models/Qwen3-VL-30B-A3B-Instruct-4bit.off`. Revertir: ver `~/models/LEEME_CAMBIO_ORNITH.txt` en el Mini. **La visión NO funciona** (error `patch_embed`): el análisis con IA de peekaboo (config `~/.peekaboo/config.json` apunta a este servidor) ya no puede leer imágenes; mis capturas las leo yo directamente. Letta (`:8283`) y Postgres siguen bien. Medido: ~53 tokens/s, memoria libre 33 %. Contexto del servidor limitado (`--max-kv-size 16384`, `--max-tokens 1024` por defecto). Entrada de opencode añadida: proveedor **`Mini-Ornith`** (`~/.config/opencode/opencode.json`, copia `opencode.json.bak-mini-ornith`; contexto 16.384, salida 4.096, solo texto). La descarga en el Mini se atasca con xet: usar `HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1`.
- **Warp/peekaboo:** pestaña 1 = coordinadora; 2-6 = IAs opencode (halogen); `ia-servidores` (última) = TUI del usuario, no tocar. Y de la barra lateral: 102, 172, 240, 309, 377, 446, 514 (recalcular con captura: cambian). Enviar con `finetune/scripts/coordinacion/ia_send.sh <y> "<prompt>" [--nuevo]` (aborta si el título es Claude.md/ia-servidores; reintentar una vez si el clic falla; volver a la pestaña 1 con clic en 140,102; no insistir con pantalla bloqueada; si el usuario está usando el ordenador, esperar). Prompt tipo: `cd <worktree> && git branch --show-current (debe imprimir track/<pista>). Lee SIGUIENTE.md completo y ejecuta el TRACK: commits en esa rama, hashes reales en ESTADO.md (cabecera Tnnn, TRACK COMPLETO al final).`
- **Vigilante:** `nohup finetune/scripts/coordinacion/vigia.sh <salida.out> <pista...> &` y después `./finetune/scripts/coordinacion/espera.sh` con `run_in_background` (espera hasta que la salida no esté vacía; copiar `espera.sh` junto a la salida o ajustar ruta). **No** usar `pkill -f` con un patrón que aparezca en la línea de comando del propio comando. macOS: `sed -i ''` obligatorio. Sleeps largos en primer plano están bloqueados: usar `run_in_background`.
- Copias de datos: `finetune/scripts/coordinacion/copias.sh` (cada 3 h, `salud_datos.py --copia`); relanzar si hace falta.

## 5. Hoja de ruta

**A. Ahora (primer piloto)** — decisiones del usuario del 24/10 («las recomendadas»): piloto **Qwen2.5-7B-Instruct QLoRA** con **v1g tal cual**; markdown se deja; multiturno real **a la v2**; `max_length` 4.096; instalar tokenizador; revisión manual del 3 % **mientras entrena**; **no arrancar hasta que el usuario lo diga (tarde del 24/10 o mañana)**.
1. Cerrar e integrar T148.
2. Con el usuario: pasar datos al nodo1, comprobar entorno (`soup --help`: claves del YAML y máscara de pérdida solo del asistente), menú K «plain», **humo de ~50 pasos**, luego 1 época. Lo ejecuta el usuario en la TUI de nodo1; yo guío paso a paso con `docs/LANZAR_PILOTO_7B.md` (modo profesora).
3. Evaluar con `finetune/corpus/evaluar_modelo.py` frente a `docs/LINEA_BASE_MODELOS.md` y los 30 prompts adversarios de `docs/PREPARACION_PILOTO.md` §4; umbrales en `docs/PLAN_ENTRENAMIENTO.md` §4 (seguridad: fuera_alcance 1,00, ética 1,00, baraja 1,00).

**B. Versión 2 del dataset (tras ver resultados)**
- **Multiturno real** (2-4 turnos, generado en los dos nodos desde lecturas ya validadas; hoy las 387 filas «consulta con contexto» son un solo turno).
- **Libros a comprar (recomendados al usuario, por prioridad):** astrología — Sakoian y Acker *The Astrologer's Handbook*; Robert Hand *Planets in Transit* y *Horoscope Symbols*; Ebertin *La combinación de las influencias planetarias*; Arroyo *Chart Interpretation Handbook*; Greene/Sasportas *The Development of the Personality* o *The Gods of Change*. Numerología — Javane y Bunker *Numerology and the Divine Triangle*; Juno Jordan *Numerology: The Romance in Your Name*; Goodwin *Numerology: The Complete Guide*; un libro de biorritmos (Gittelson). Baraja española — Salas *El arte de echar las cartas 2*, Rossi *Curso de cartomancia*, Mercadal. Tarot — Greer *21 Ways…* y *Tarot Constellations*, Eden Gray, Jodorowsky y Costa *La vía del Tarot*. Formato: PDF/ePub con texto seleccionable y sin DRM, mejor en español. Tras comprar: pistas como T114/T115/T119 (`finetune/corpus/libro_comprado_*.py`, `libros_comprados_*.py`).
- Decisión de **estilo markdown** tras ver el piloto (≈6 de cada 10 respuestas de train lo llevan); unificar los 2 system prompts; política para las 74 filas >4.096 tokens; asignar bloque a las 445 filas sin bloque (explicadores multi-tema, muchos fuera de alcance); reforzar bloques débiles (lectura_completa 65 % del objetivo; tránsitos con plantillas parecidas).
- Limpieza de celdas contaminadas de la KB (Leo arrastra consejos de Géminis; el número 3 mezcla otros números).
- Piloto **14B** (~97 h) solo cuando el 7B valide receta y datos.

**C. Más adelante:** revisión legal de los textos (aplazada por el usuario); RAG con la KB v2 en inferencia; backend FastAPI y frontend Next.js (`docs/superpowers/plans/`, sin código aún); alcance aplazado (quiromancia, Lenormand, I Ching, runas…).

## 6. Pendientes del usuario

- Revisión manual del **3 %** (`/Users/angelgonzalez/fase0/muestras_v2/revisor.html`, `docs/REVISION_3PC.md`): la haría mientras entrena el piloto.
- Decidir cuándo arrancar el piloto (tarde del 24/10 o 25/10).
- Compra de libros (lista en §5-B); completar la copia del libro de Banzhaf y el PDF completo de Sasportas (el actual está a medias).
- Probar el modelo kj en nodo1 (Qwen3.8 ROCmFP4) y decidir el modelo del Mini a futuro; si se necesita visión para peekaboo, hay que servir un modelo con visión (el Qwen3-VL-8B 8 bits está en el Mini).
- Cuestión abierta menor: instalar o no más herramientas (ya autorizado el tokenizador).

## 7. Cómo integrar una pista (receta exacta)

1. `git log --oneline main..track/<p>` y `git diff --stat main...track/<p>`: comprobar que los hashes existen y que solo toca sus ficheros.
2. Casos adversos propios (no fiarse de los tests de la IA): datos (voseo, duplicados, fugas, claves, chino/cirílico), validación de hosts, cifras que cuadran con los ficheros reales.
3. `cd /Users/angelgonzalez/adivinacion-ia && git -c user.name="Angel Gonzalez" -c user.email="angel.eitec@gmail.com" merge --no-ff track/<p> -m "merge: pista <p>

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"`.
4. **`ESTADO.md`**: está trackeado en main como plantilla neutra y los merges lo pisan o chocan. Tras el merge: `git show HEAD~1:ESTADO.md > ESTADO.md && git add ESTADO.md && git commit` (o `git checkout --ours ESTADO.md` si hay conflicto). Si no, el vigilante da falsos «COMPLETO».
5. `./finetune/scripts/check.sh` → `CHECK OK`. Reasignar la IA liberada.

## 8. Modo profesora (pedido del usuario el 23/10: aún sin empezar)

El usuario no tiene experiencia entrenando modelos ni limpiando datos y dice que de la semana «no ha aprendido nada». Es excepción a «no explicar tareas». Empezar **tras dejar T148 integrada y proponerlo en una frase**, con lenguaje llano, un concepto cada vez, ejemplos con datos reales del proyecto y comprobación de que lo ha entendido. Temario propuesto (`docs/guia/00_INDICE.md`, `01_MAPA_DE_PROGRAMAS.md`, `02_GLOSARIO.md` ya existen):
1. Qué es entrenar (pesos, ejemplos, época, pérdida); qué es LoRA/QLoRA; por qué 7B antes que 14B.
2. El dataset: qué es una fila ShareGPT, qué son train/val/test y por qué no pueden mezclarse (fugas), con v1g abierto delante.
3. Limpieza: duplicados, voseo, datos inventados, corruptos; cómo los detectamos y retiramos (casos reales de esta semana).
4. De los libros al dataset: evidencias → afirmaciones → consenso → KB → generación → verificación (mapa de programas).
5. Cómo se lanza el piloto en nodo1 (menú K), qué mirar durante el entrenamiento (pérdida, NaN, memoria).
6. Cómo se evalúa (prompts adversarios, umbrales) y cómo se decide la versión 2.

## 9. Reglas fijas del usuario (no reabrir)

Calidad por encima del plazo; poco presupuesto (no comprar sin avisar y justificar; solo fuentes legales; revisión legal aplazada); git solo local (nunca push/remotos); sin subagentes `Agent`; nunca leer ni imprimir `INCEPTION_API_KEY` ni credenciales de `HOMELAB.md`; no usar el LM Studio personal del iMac; no tocar la pestaña `ia-servidores`; DeepSeek solo 10:00-24:00 (hoy cerrado); no reanudar los generadores suspendidos PID 66101/66396; baraja española y naipes franceses son sistemas distintos; hoy no se usa Mercury (cerrado, sin clave). Una IA puede dar `TRACK COMPLETO` antes de tiempo con hashes inventados: verificar siempre.

## 10. Lecciones de esta semana (evitar repetirlas)

- Repartir la generación entre **los dos nodos desde el principio** (me costó horas dejar T142 en un solo worker de nodo2).
- Un solo prompt por respuesta colapsa bloques repetitivos (ética quedó en 5 filas): regenerar con prompts variados.
- Las IAs usaron voseo («querés», «podés», «vos») en bloques generados: filtrar siempre con lista cerrada de formas voseantes y excepciones («más», «estás», «además», «vosotros» legítimo).
- Un detector que mira solo los bloques nuevos deja pasar los viejos: comprobar todo el dataset.
- `mlx_vlm.server` carga el modelo que pida cada petición: no cambiar el modelo del Mini sin que las rutas que usan Letta/peekaboo apunten al mismo.
- Pantalla bloqueada o usuario trabajando ⇒ peekaboo no funciona; no insistir; un sondeo cada 5-10 min.
