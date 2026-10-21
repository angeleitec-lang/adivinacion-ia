# Estado del proyecto y pendientes (traspaso)

> Escrito el 2026-10-18 y **cerrado el 2026-10-19 a las 00:05** por orden del usuario («seguimos mañana»). Refleja el estado exacto a esa hora. Lee este documento **antes de tocar nada**: explica qué hay, por qué, qué está a medias y cómo seguir.

## 1. Objetivo y decisiones del usuario (no se discuten de nuevo)

- **Objetivo:** un modelo de lenguaje en español, de calidad alta o muy alta, para hacer lecturas de tarot, baraja española, carta astral y numerología. «Me consta que no existe algo así.» Producto previsto: app web (ver `docs/diseno-app-adivinacion.md`).
- **Calidad por encima del plazo:** se invierten los días que haga falta en reunir información buena **antes** de generar el dataset final y entrenar.
- **Legalidad de los textos:** se revisa más adelante; no bloquea ahora. Cada documento conserva su procedencia para poder filtrar después (`finetune/corpus/license_filter.py`).
- **Alcance actual:** tarot (78 cartas), baraja española (40 naipes), astrología occidental (signos, planetas en signo y casa, aspectos, nodos, tránsitos, revolución solar, sinastría), numerología (+ biorritmos). **Aplazado:** quiromancia, Lenormand, I Ching, runas, Kipper, Sibilla, naipes comunes, gitanas, Jyotish, BaZi/china, horaria, progresiones, café/té/cristal/péndulo y demás.
- **Coordinación multi-IA** (protocolo en `~/.config/opencode/docs/coordinacion/PROTOCOLO.md`): Claude (modelo de pago) **solo coordina: no programa y NO usa subagentes `Agent`** (rechazado por el usuario). Las IAs locales (opencode sobre halogen en nodo1/nodo2, y una de opencode go) programan en worktrees separados. Todo git es **solo local, nunca remotos**.
- **Presupuesto:** el usuario tiene poco dinero; no comprar nada sin avisar y justificarlo.

## 2. Cómo está organizado el trabajo

- **Repo git local:** `/Users/angelgonzalez/adivinacion-ia` (rama `main`, sin remoto). Contiene solo código y documentos; los datos pesados están en `.gitignore`.
- **Worktrees por pista:** `/Users/angelgonzalez/adivinacion-ia/.worktrees/<pista>/` en la rama `track/<pista>`. Cada una tiene `SIGUIENTE.md` (instrucciones; las escribe la coordinadora) y `ESTADO.md` (progreso; lo escribe la IA). Ambos están en `.gitignore`.
- **Verificación:** `finetune/scripts/check.sh` (compila y ejecuta todos los tests, sin red ni datos pesados). Debe acabar en `CHECK OK`.
- **Python:** siempre `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python` (hay `uv` pero no `pip`). Tests con `unittest` (no hay pytest).
- **Integración de una pista:** revisar el diff, ejecutar mis propios casos adversos (no fiarse solo de sus tests), `git merge --no-ff track/<pista>` desde la raíz y pasar `check.sh`.
- **Ajustes sobre una pista:** las IAs leen su `SIGUIENTE.md` al arrancar y **no lo vuelven a mirar**: un ajuste añadido al final no se aplica hasta que el usuario pega en su terminal «Relee SIGUIENTE.md: hay una sección AJUSTE…».
- **Sondeo:** `/private/tmp/claude-501/-Users-angelgonzalez-adivinacion-ia/8f147f51-d817-422c-8b90-8a7f48b9a511/scratchpad/poll.sh` (espera 5 min y resume commits y `ESTADO.md` de cada worktree). Es temporal: si no existe, se hace con `git -C .worktrees/<pista> log --oneline main..HEAD`.

## 3. Documentos clave (léelos en este orden)

1. `docs/PLAN_ADQUISICION_CALIDAD.md`: plan de la fase 0 (adquisición de conocimiento de calidad), matriz de cobertura, niveles de fuentes, tubería de calidad.
2. `docs/INVENTARIO_FUENTES.md` + `finetune/knowledge/*.jsonl|json`: libros verificados, EPUB locales evaluados, sitios web, rejillas de URLs (astrología, numerología, baraja), foros.
3. `docs/DISENO_A4_YOUTUBE.md`: diseño de las lecturas trabajadas desde subtítulos de YouTube.
4. `finetune/PLAN_COBERTURA.md`, `finetune/DECISION_MODELO_MOE.md`: plan de dataset (18.100 pares) y decisión pendiente del modelo base (Qwen2.5-14B denso vs Qwen3.5-35B-A3B MoE).
5. `tecnicasCartomancia.md`: mapa completo de técnicas (el alcance real del producto a largo plazo).

## 4. Evolución (resumen cronológico, 2026-10-18)

1. Revisión de la documentación existente: el dataset final (`finetune/corpus/final/`) tenía 4.249 pares de entrenamiento con **22 % de prompts vacíos** («¿Qué significa Sección 24?»), residuos de Wikipedia, respuestas fuera de tema y solo 118 pares de tirada. Veredicto: **no entrenar así**.
2. Auditoría de los 17 scripts propios: 20 defectos verificados con datos reales (tabla en la sección 5).
3. Se montó repo git local, contrato de tests (`check.sh`) y **8 pistas** con IAs locales en worktrees; se añadieron A4 (YouTube), A2 (libros) y A3 (rastreo).
4. Se decidió **calidad antes que velocidad**, se acotó el alcance y se escribió el plan de adquisición.
5. Investigación de fuentes: libros en archive.org (≈ 80 verificados con texto, ≈ 40 MB), evaluación de los 155 EPUB locales (solo 19 útiles), rejillas de sitios por entidad para astrología, numerología y baraja española, foros, YouTube (95 % de los vídeos tienen subtítulos en español), Hugging Face (nada comparable existe).
6. Revisión e integración de pistas completadas (T2, T5, T6, T8 ya en `main`).

## 5. Defectos de la auditoría y su estado

| # | Defecto | Pista | Estado |
|---|---|---|---|
| 1 | Hora local pasada como UT en la carta natal (Ascendente erróneo) | T1 | **Corregido** (T1.1, verificado con Lima: Virgo 20°) — en rama, sin integrar |
| 2 | Scraper descarta páginas con «cart» (cartas, carta astral) | T6 | **Integrado** |
| 3 | `detect_language` clasifica el «no» español como inglés | T2 | **Integrado** |
| 4 | Fallo de traducción deja inglés escrito como traducido | T2 | **Integrado** (`.failed.jsonl` + `--retry-failed`) |
| 5 | Residuos de Wikipedia (`&action=edit`, `cite_note`) | T3 | Corregido en rama (156 → 0 y 305 → 0) |
| 6 | Filtro de dominio con palabras cotidianas (sol, luna, mano…) | T3 | Corregido en rama (fuertes/débiles) |
| 7 | Validador sintético: no comprueba todas las cartas ni la orientación; casi-duplicados falsos | T4 | Corregido en rama (T4.1–T4.4); faltan T4.5/T4.6 |
| 8 | Generador sin KB/Referencia: el LLM inventa significados | T1 + T7 | KB de menores casi lista; **T1.7 (inyectar la Referencia) pendiente** |
| 9 | Año personal de numerología mal calculado (usaba el año como día) | T1 | **Corregido** (T1.8, verificado con 7 casos) — en rama |
| 10 | Licencias sin aplicar | T5 | **Integrado** el módulo `license_filter`; falta usarlo en el build (T3.5) |
| 11 | Los 155 EPUB no estaban en el pipeline | A2 | En curso |
| 12 | `generate_synthetic` reseteaba trabajos de otros workers | T2 | **Integrado** |
| 13 | `rebuild_when_done.sh` seguía tras un fallo | T2 | **Integrado** |
| 14 | `merge_final`: test solo sintético, `is_junk_pair` ineficaz | T5 | **Integrado** (probado sin fuga train/test) |
| 15 | Ética: 300 trabajos sobre 8 preguntas | T1 | Corregido en rama (≥ 40 casos) |
| 16 | `multiturno` no es multi-turno real | T1 | Redacción corregida; **multi-turno real sigue pendiente** (requiere generación en dos fases) |
| 17 | Índice RAG con basura (página anti-bot) y embeddings lentos | T8 | **Integrado** |
| 18 | Prompts del generador sin tildes | T1 | **Corregido** (T1.2, verificado en 1.052 prompts) |
| 19 | Aspectos recortados por orden de planeta | T1 | **Corregido e integrado** (T1.6: los 14 de menor orbe, verificado) |
| 20 | Tabla de trabajos no idempotente | T1 | **Corregido e integrado** (T1.5: `--replace-pending` solo toca `pending`; los `done`/`running` se conservan, verificado con BD temporal) |

## 6. Procesos y recursos vivos (¡cuidado!)

- **Generadores sintéticos** (PID 66101 nodo1 y 66396 nodo2): **suspendidos** (estado `T`). Habían hecho 360 trabajos (356 tarot_1, 4 ética) con los **prompts viejos sin tildes**. **No los reanudes (`kill -CONT`) con los trabajos actuales**: generarían con el código anterior. Procedimiento correcto: integrar T1, regenerar los trabajos pendientes con `--replace-pending` y lanzar generadores nuevos; los dos procesos viejos se matan (`kill -TERM`, y luego `kill -CONT` solo para que procesen la señal).
- **Traducción en curso** (PID 30819): **suspendida**. Va por la fila 1.578 de 7.526 de `finetune/corpus/train_scrapy.jsonl` (salida en `train_scrapy_es.jsonl`, con `.progress`). Se puede reanudar con `kill -CONT 30819`; usa el código antiguo del script pero la lógica de progreso es compatible. Si se relanza con el script nuevo (ya en `main`), usar `--resume`.
- `jobs.db`: 360 hechos, 10.270 pendientes, 6 `running` huérfanos (se resetean al relanzar). **Hay que hacer una copia de seguridad antes de regenerar.** Las 360 filas hechas tienen prompts sin tildes y las puerta `prompt_sin_tildes` de T4 las rechaza.
- **Docker/Firecrawl:** los 5 contenedores están arriba en `localhost:3002`. Solo hace falta para páginas con mucho JavaScript; astro.com bloquea incluso a Firecrawl (Cloudflare).
- **Memoria local de Claude:** `~/.claude/projects/-Users-angelgonzalez-adivinacion-ia/memory/` (feedback: no subagentes).

## 7. Datos acumulados (rutas y cifras)

| Qué | Dónde | Cifra |
|---|---|---|
| Libros con texto verificado (archive.org, en/es/tema) | `finetune/knowledge/fuentes_libros*.jsonl` | ≈ 60 obras (≈ 28 MB) |
| EPUB locales evaluados | `finetune/knowledge/epubs_locales.jsonl` | 15 usar + 4 con limpieza |
| Sitios con rejilla astrología | `finetune/knowledge/rejillas_astrologia.json` | planeta/signo 120 (5 sitios), planeta/casa 120 (6 reales), aspectos 225 (4) |
| Sitios con rejilla numerología | `finetune/knowledge/rejillas_numerologia.json` | camino 6, destino 5, compatibilidad 5, año 4, alma 3, personalidad 3, mes 2 |
| Baraja española y foros | `finetune/knowledge/rejillas_baraja_foros.json` | 3 sitios con ≥ 36/40; forotarot.net prometedor |
| Catálogo de prueba YouTube | scratchpad (`yt/catalogo_prueba.json`) | 429 vídeos, 225 canales, 95 % con subtítulos |
| Dataset actual (antiguo) | `finetune/corpus/final/` | 4.249 train; tras el auditor sobreviven ≈ 1.991 (42,8 %) |

## 8. Estado final de cada pista (2026-10-19 00:50)

**Todas las pistas están integradas en `main`** (último merge `03f5c82`; `check.sh` OK, 560+ tests). No queda ninguna rama sin fusionar. Los worktrees de `.worktrees/` se pueden conservar o borrar (`git worktree remove`).

| Pista | Qué hace | Estado |
|---|---|---|
| T1 generador | `generate_tasks.py`: UT/zoneinfo, tildes, ética ≥ 40, multiturno, idempotencia, 14 aspectos de menor orbe, año personal/camino de vida corregidos, «Referencia» de la KB en los prompts, sin doble punto | **Integrada** (dry-run: 11 bloques, 10.636 trabajos) |
| T2, T5, T6, T8 | traducción/workers, fusión y licencias, recolección, auditoría y RAG | **Integradas** (el índice RAG real NO se ha reconstruido) |
| T3 limpieza del dataset | `build_dataset.py`, `build_scrapy_dataset.py` | **Integrada** con ajustes: elimina frases comerciales completas, ofertas con precio y «Lee también». Opcional pendiente: exigir densidad de términos fuertes (temas fuera de alcance como «Mundo musulmán») |
| T4 validador | `validate_synthetic.py` | **Integrada** (rechaza `<think>`/`</think>`/`<thinking>` sobre texto bruto) |
| T7 KB | `build_kb.py` + `kb/*.json` | **Integrada** (Sota de Espadas corregida, lenguaje neutro) |
| A2 libros | inventario, descarga, extracción EPUB, limpieza OCR, segmentación, informe | **Integrada** (rama `a2b-segmentar`). Probada con 3 EPUB reales: *Tarot Fundamentals* 718 págs/259 descartadas, 22 arcanos como título; *78 Degrees* 105 secciones; *Jung y el Tarot* 21 arcanos. Defecto menor: la primera sección lleva el título «Sección 1 — <portada>» |
| A3 rastreo dirigido | cliente educado, expansión de rejillas, extracción, índices, informe | **Integrada** (ramas `a3-rastreo` y `a3b-rastreo`). **La prueba real de 25 URLs NO se ha hecho** (la de punta a punta fue simulada) y los patrones de `sitios_indice.json` no están comprobados contra internet |
| A4 YouTube | cartas, descubrimiento, subtítulos, clasificación, extracción validada | **Integrada**. Prueba de punta a punta con ≤ 5 vídeos: IA-9 hizo 1 vídeo; pendiente revisarla con calma y repetir con 5; borrar `yt_discover.py.bak`; corregir `ESTADO.md` de A4 |
| C1 calculadoras | carta natal, tránsitos, revolución solar, sinastría, numerología, biorritmos | **Integrada** (verificada: Ascendente Lima Virgo 20°, Mercurio retrógrado 2024, revolución solar 0,0002°). Pendiente: renombrar la reexportación `biorritmos` que oculta al módulo (ajuste ya escrito, no urgente) |

**Aviso:** las horas que anotan IA-9 e IA-10 en sus `ESTADO.md` son inventadas (p. ej. `01:15`, `02:45` cuando eran las 00:36). No usarlas como registro.

## 8b. Actualización 2026-10-19 (tarde)

**Integradas hoy en `main`:** T12 (filtro opcional `--min-density`, umbral recomendado 2,0, NO activado), T11 (el segmentador de libros ya no marca prosa como material preliminar), T10 (nodos lunares medios en trópico + tránsitos a nodos; la reexportación de biorritmos es ahora `calcular_biorritmos`), T9 (`generate_tasks.py` delega en `calculos/`; 10.636 trabajos sin cambios), T13 (descubrimiento con enlaces relativos y varios índices; `aeclectic.net` da 78 URLs y `tarotrossana.com` 78 cartas en español). Prueba real de A3 (22 URLs, 5 sitios): 21 extraídas.

**Integradas después:** T14 `cobertura.py` (matriz de cobertura de fuentes), T15 `cobertura_dataset.py` (cobertura del dataset; límites conocidos: «Cáncer» enfermedad cuenta como signo y las cartas con el mismo nombre en tarot y baraja española se cuentan en ambos mazos), T16 multi-turno real en dos fases (filas de 5 mensajes con `turnos: 2`; el validador aplica reglas por turno). Pendiente tras T16: matar los generadores suspendidos (PID 66101 nodo1, 66396 nodo2), hacer copia de `jobs.db` y regenerar con `--replace-pending`. `audit_dataset.extraer` audita el ÚLTIMO par y `merge_final` el PRIMERO: decidir si unificar. Ya no queda ninguna pista abierta.

**Decisiones del usuario:** acceso a `Pepere45/spanish-esotericism-corpus` solicitado (sin respuesta); no tiene PDFs/EPUB propios, compra de libros digitales autorizada avisando antes; filtro de licencias estricto NO se aplica por ahora.

**Residuos menores:** `web_indices.py` aún deja pasar `href="/ruta/#top"` que apunta a la propia página índice (lo filtra el regex) y tiene la errata «separte» en un docstring; no se ha repetido la prueba real de A4 (≤ 5 vídeos) ni la de A2 (1–2 libros). Algunas IAs han commiteado en `main` en vez de en su rama: verificar siempre `git branch --show-current` en el prompt.

## 8c. Primera cobertura real (2026-10-19, solo web en español)

Datos en `/Users/angelgonzalez/fase0/` (fuera del repo): `web/` (170 páginas de 14 sitios, `informe.md`), `evidencias_web/` (146 secciones juzgadas, 1.283 evidencias, calidad media 3,93; 27 lecturas trabajadas), `cobertura_web.json|md`. Celdas con ≥ 1 fuente: baraja española 372/480, tarot 325/936, astrología+numerología 63/6.039; con ≥ 3 fuentes: 36, 24 y 0; **completas (5 fuentes, 1 clásica, 2 modernas, 1 en español): 0**, porque la web aporta solo fuentes modernas y como mucho 14 dominios independientes. Falta: libros (clásicas), YouTube, y sobre todo astrología (planeta×signo, planeta×casa, aspectos) y numerología en español.

## 9. Pendientes (el punto 1, unificar `generate_tasks.py` con `calculos/`, ya está hecho) (en este orden)

0. **Orientarse (5 min):** leer este documento; `git log --oneline | head`; `./finetune/scripts/check.sh`.
1. **Unificar `generate_tasks.py` con `calculos/`:** T1 conserva sus propias `calcular_carta`, `camino_de_vida`, `anio_personal`; C1 tiene versiones independientes. Las dos están verificadas, pero hay que elegir una (la de `calculos/`) y que el generador la importe, con test de equivalencia. Pista pequeña para una IA.
2. **Pruebas reales con internet (las lanzo yo, con cortesía):** A3 con 25 URLs reales (5 sitios × 5) para validar `sitios_indice.json`; A4 con ≤ 5 vídeos; A2 con 1–2 libros de archive.org (pausa ≥ 2,5 s).
3. **Ejecución real de la fase 0:** A2 sobre el inventario completo → `knowledge/libros/`; A3 sobre las rejillas → `knowledge/web/`; A4 sobre el catálogo → `knowledge/youtube/`. Ritmo cortés. Revisar los informes de calidad antes de pasar a la matriz.
4. **Decisiones del usuario que desbloquean cosas** (preguntar en cuanto empiece):
   - ¿Solicitó acceso a `Pepere45/spanish-esotericism-corpus` en Hugging Face (cuenta `Serono22`)? Es el único corpus en español.
   - ¿Tiene PDFs/EPUB propios de libros de **baraja española** o de astrología/tarot en español? Es el hueco más serio (los de préstamo digital no son descargables).
   - ¿Se compra algún libro? Lista corta: *El arte de echar las cartas* (Emilio Salas, baraja española); Beltrame *Tarot con cartas españolas*; Banzhaf *El gran libro del tarot*; Greer *Tarot for Your Self* (el menos urgente). Presupuesto muy limitado: no comprar sin avisar.
   - ¿Aplicar el filtro de licencias estricto (`--license-filter strict`)? En el build sobre `raw/` baja de 1.077 a 381 pares. Decisión legal que el usuario aplazó.
5. **Diseños que faltan por escribir** (coordinadora): A5 (segmentador + juez LLM + matriz de cobertura), A6 (consenso de KB), pista de **multi-turno real** (generación en dos fases), astrología adicional (nodos lunares), y rastreo de `forotarot.net`.
6. **Fase 1 (regeneración):** solo después de 1 y de la matriz de cobertura; ver sección 10.

## 10. Cómo continuar cuando se acaben los pendientes (plan completo)

**Fase 0 — adquisición de calidad (en curso; duración estimada 4–7 días de máquina)**
1. **F0.2 Descarga y extracción real:** A2 sobre el inventario (`knowledge/fuentes_libros*.jsonl` + `epubs_locales.jsonl`) → `knowledge/libros/{crudo,limpio,secciones}`; A3 sobre `rejillas_*.json` e índices → `knowledge/web/`; A4 (catálogo ≥ 4.000 vídeos de ≥ 150 canales, subtítulos, extracción) → `knowledge/youtube/`. Ritmo cortés (≤ 1 petición/s por dominio, `robots.txt`).
2. **F0.3 Juez y matriz de cobertura (A5):** segmentar, juzgar con el LLM local de los nodos, etiquetar entidad/faceta, generar `cobertura.json/md` con las celdas bajo el mínimo (5 fuentes en la ola activa).
3. **F0.4 Recuperación dirigida** de los huecos que marque la matriz; repetir hasta < 10 % de celdas bajo el mínimo.
4. **F0.5 Lecturas trabajadas:** ≥ 1.500 lecturas puntuadas ≥ 4/5 (YouTube + libros con ejemplos resueltos como Minetta y Platt).
5. **F0.6 KB de consenso v2** (por mayoría entre fuentes, con discrepancias de tradición marcadas) y **revisión humana del 3 %** por el usuario antes de pasar a la fase 1.

**Fase 1 — dataset**
6. Copia de seguridad de `finetune/corpus/jobs.db`; integrar T1 y C1; regenerar los trabajos pendientes con `generate_tasks.py --replace-pending` (los 360 viejos se descartan); incluir la «Referencia» de la KB y los datos calculados por C1.
7. Matar los generadores suspendidos (66101, 66396: `kill -TERM` y luego `kill -CONT`) y lanzar generadores nuevos en nodo1/nodo2 (ver `finetune/PLAN_COBERTURA.md`, fase 3, adaptando endpoints). Parar la traducción 30819 o reanudarla con `kill -CONT 30819` si se quiere terminarla (progreso 1.578/7.526).
8. Validar con `validate_synthetic.py` (T4), auditar con `audit_dataset.py` (T8), mezclar con las lecturas reales y fusionar con `merge_final.py` (T5): split 80/10/10 con test real, sin fuga.
9. **Conjunto de oro** de ~150 lecturas revisadas por el usuario como test ciego, congelado antes de entrenar.

**Fase 2 — modelo**
10. **Decidir el modelo base** con el spike descrito en `finetune/DECISION_MODELO_MOE.md` (Qwen3.5-35B-A3B MoE preferido; fallbacks Qwen3-30B-A3B-Instruct-2507 y Qwen2.5-14B denso). Soup en `/Users/angelgonzalez/01_Proyectos_AI/Soup`.
11. Entrenamiento QLoRA/LoRA; evaluación ciega contra el modelo base con juez LLM y revisión humana de 30 lecturas; `soup merge` y exportación GGUF; servir en halogen/Ollama.

## 11. Riesgos y notas que no hay que olvidar

- **Los generadores suspendidos no deben reanudarse con los trabajos viejos.** Los 360 trabajos hechos tienen prompts sin tildes.
- **Una IA puede dar `TRACK COMPLETO` antes de tiempo** y los tests de las IAs no detectaron: el año personal de numerología mal calculado, la carta que el vídeo nunca mencionaba, los títulos útiles descartados. Verificar siempre con casos adversos propios.
- **Rate limits:** astrolink devuelve 429 a ritmo rápido; Reddit y muchos foros ingleses dan 403; astro.com y nymero.org bloquean incluso a Firecrawl. No saltar bloqueos.
- **`my-zodiac-ai.com`, `horoscopelogic.com` y similares** parecen texto generado por plantilla/IA: no contarlos como fuente independiente sin el juicio del juez de calidad.
- **Baraja española vs naipes franceses:** los manuales de cartomancia con naipes (Grand Orient, Platt, Minetta) sirven, pero los significados no coinciden carta a carta; mantener ambos sistemas separados en la KB.
- Mini (10.0.0.1): Ollama solo escucha en 127.0.0.1 (túnel SSH para embeddings); Postgres sin pgvector útil.

## 12. Comandos útiles

```
# verificación global
cd /Users/angelgonzalez/adivinacion-ia && ./finetune/scripts/check.sh
# integrar una pista (desde la raíz, tras revisarla)
git -c user.name="Angel Gonzalez" -c user.email="angel.eitec@gmail.com" merge --no-ff track/<pista> -m "merge: pista <X>

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
# estado de todas las pistas
for w in .worktrees/*/; do echo "$(basename $w): $(git -C $w log --oneline main..HEAD | wc -l) commits, $(git -C $w status --short | grep -v -E 'SIGUIENTE|ESTADO' | wc -l) sin commit"; done
# licencias (tabla)       .venv/bin/python finetune/corpus/license_filter.py
# build_dataset (ensayo)  .venv/bin/python finetune/corpus/build_dataset.py --raw finetune/corpus/raw --dry-run [--license-filter strict]
# auditoría               .venv/bin/python finetune/corpus/audit_dataset.py --in finetune/corpus/final/train.jsonl --out-dir /tmp/audit
# generador (ensayo)      .venv/bin/python finetune/corpus/generate_tasks.py --dry-run
# Firecrawl               docker ps   (api en http://localhost:3002)
```

## 13. Registro de lo escrito en Letta (2026-10-18/19)

Scope `project: adivinacion-ia`: entrada de **correcciones** (9 puntos que sustituyen a entradas anteriores), entrada de **resumen de la sesión**, y las entradas que escribieron las propias IAs (T5, T8…). Scope `global`: **lecciones de coordinación multi-IA** (ajustes por prompt, verificar con casos propios, sin subagentes Agent, rate limits). Memoria local de Claude: `feedback_no_subagentes.md`, `project_estado_adivinacion_ia.md`.

## 8d. Cobertura web ampliada (2026-10-19, tras T26 y 647 páginas nuevas)

Web en español: 756 páginas de 27 dominios; 5.285 evidencias. Celdas con ≥ 1 fuente (todas en español, ninguna clásica todavía):
- Tarot: 332 de 936 (≥ 3 fuentes: 31; ≥ 5: 2).
- Numerología: 387 de 792 (≥ 3: 63; ≥ 5: 3).
- Astrología + baraja española (`naipe-*`): 1.566 de 6.207 (≥ 3: 213; ≥ 5: 4). La baraja española estaba en 372 de 480 antes de esta ampliación.
- Celdas completas: 0 (falta siempre la fuente clásica; vendrá de libros).
Auditoría de calidad (T31, `/Users/angelgonzalez/fase0/web/calidad.md`): 4 páginas con mojibake (tarotsevilla.com), 171 con título pobre, 2 duplicadas; ambos defectos reales pasan a T30b.
Pendientes: libros (T24), YouTube (limitado por 429, bucle de reanudación), tarot por carta (T27), lecturas trabajadas (T28), extractor de afirmaciones (T29).

## 8e. Cobertura total web + libros (2026-10-20)

Evidencias: 14.010 de web (~1.626 páginas) y 17.449 de libros. Celdas completas: 259 de 7.455 (3,5 %): Tarot 173/936 (18,5 %), Astrología 79/5.247 (1,5 %), Numerología 5/792 (0,6 %), Baraja española 2/480 (0,4 %). Informe: `/Users/angelgonzalez/fase0/cobertura_total.md`.
Afirmaciones (T29, 300 evidencias): 3.166 aceptadas; descartes `otra_carta` ~10 %; sin revisar a fondo.
Defecto abierto: la etapa `juez` de `libros_pipeline.py` se cuelga (0 % CPU, sin volcar juicios); `juez.py` directo funciona. YouTube sigue limitado por HTTP 429.

## 8f. Integrado el 2026-10-20 (T36–T51) y pendientes inmediatos

Integradas en `main` (todas con `check.sh` = CHECK OK): T36 (índices de sitios ES de baraja y numerología, 12+12), T37 (extractor de lecturas de libros: 231 lecturas, 225 con calidad ≥ 4/5; casi nada de baraja española), T39 (disponibilidad legal de los 15 libros que faltan; sin precios verificables por vía automática), T40 (robustez de cálculos: 29-feb, 1900 no bisiesto, polos con casas iguales, validación de fechas/horas/zonas), T41 (afirmaciones: escritura incremental, reanudable, `--orden calidad`, `--min-calidad`, `--familias`, `--timeout`), T42 (15 sitios de astrología por combinación; 1.275 páginas descargadas en `fase0/web/`), T43 (plan de recuperación dirigida), T44 (prompts de fase 1 + `verificar_lectura`), T48 (muestras del 3 % y conjunto de oro: 2.712 fichas en `fase0/muestras/muestras.md`), T50 y T51 (auditorías adversas de los módulos: más de 40 fallos reales arreglados con tests; discutibles anotados en sus `ESTADO.md`).
En curso: T38 (afirmaciones de libros y consenso con la KB), T45 (multi-turno; su verificador dejaba pasar promesas y cartas ajenas: se le pidió reutilizar `verificar_lectura`), T46 (por qué casi no hay evidencia clásica de las cartas menores de tarot aunque Waite está en el corpus), T47 (llevar las páginas nuevas de T36/T42 hasta evidencias y a una matriz de cobertura v2), T49 (piloto de generación de fase 1 con el LLM real).
Hallazgos que condicionan el plan: (1) la cobertura completa es muy baja (3,5 % de celdas); bajar del 10 % bajo mínimo exigiría ~24.700 fuentes nuevas, por lo que el hito debe redefinirse (cobertura completa solo en tarot; mínimos menores en el resto). (2) La pasada de afirmaciones web va a ~500 evidencias/hora con los nodos compartidos: no cabe entera; se acota con `--orden calidad --min-calidad 4`. (3) El 3 % a revisar por el usuario son 2.712 fichas: conviene decidir si se reduce al 1 % o a las de mayor calidad. (4) YouTube sigue bloqueado por 429.
Decisiones del usuario pendientes: respuesta de Hugging Face (`Pepere45/spanish-esotericism-corpus`); compra de libros (prioridad baraja española: Salas; ver `finetune/knowledge/libros_faltantes_legal.md`); revisión del 3 %; redefinir el hito de cobertura.
Operativa: pestañas 2–7 de Warp para las IAs (6 DeepSeek solo 10:00–24:00; 7 Qwen de pago), 8 y 9 del usuario (no tocar). El vigilante busca `TRACK COMPLETO` en cualquier posición de la línea.

## 8g. Actualización 2026-10-21 (T77): estado real, procesos y decisiones abiertas

Esta sección sustituye, para el estado vivo, a la lista de procesos de §6 y a las
cifras de §7/§8e. Las secciones anteriores se conservan como histórico.

### Pistas integradas en `main` (con `check.sh` = CHECK OK)

Desde el corte de §8f se han integrado: T52 (prerevisión), T53 (cartas en inglés
y reproceso de Waite), T54 (revisor local), T55 (19 clásicos de astrología, 5 de
numerología y baraja de dominio público, con hashes), T56 (240 casos de
evaluación y evaluador con línea base), T57 (clásicos PD convertidos a
evidencias), T58 (auditoría ronda 3), T59 (salud de datos y copias SHA-256), T60
(mapa del pipeline), T61 (`preparar_entrenamiento`), T62 (`ejecutor_fase1`),
T63 (auditoría ronda 4), T64 (recuperación 2), T65 y T68 (backend rápido
Mercury), T66 (`kb_v2`), T67 (arreglos de la ronda 4), T70 (ensayo extremo de
punta a punta) y T73 (consenso rápido con dedup por fuente). También quedaron
cerradas T38 (afirmaciones de libros), T41, T45, T46, T47, T48, T49, T50 y T51
que §8f daba como en curso.

En curso, **sin merge todavía**: T69 (pasada rápida de afirmaciones con Mercury),
T71 (limpieza de libros en copia `libros_limpio/`), T72 (prompts de tiradas
largas y familia de baraja española), T74 (fuentes nuevas de baraja y
numerología), T75 (alinear fase 1 con los desajustes D1/D2/D3/D7 del ensayo) y
T76 (consenso Mercury frente a nodos, 40 celdas, acuerdo ≥ 85 %). T69 conserva
su script en el worktree: no está en `main`.

### Procesos vivos y logs (medido el 2026-10-21)

- **Consenso de la KB**: dos procesos `consenso_kb.py` escriben a la vez en
  `/Users/angelgonzalez/fase0/consenso_kb/` (PID 3552 con `--workers 2` y PID
  96681 con `--workers 6`). Logs: `run_consenso.log` y `run_consenso2.log`.
  Riesgo real de carrera sobre `consenso.jsonl`; conviene dejar uno solo y
  conservar la copia `.bak-0858`.
- **Pasada rápida de afirmaciones (T69)**: PID 81434, `afirmaciones_rapido.py
  --workers 3`, log `afirmaciones_rapido/pasada.log`. Aproximadamente 6.225 de
  14.188 evidencias, 35.527 afirmaciones aceptadas y 17.057 descartadas, a 59,3
  evidencias/min (ETA ~134 min en el momento de la medida).
- **Recuperación 2/3 (T74)**: PID 14273, `recuperacion_descarga.py` con
  `plan_t74.jsonl` y `web_recup3/`, sin LLM, tope 40 por dominio y 200 en total.
- **Piloto de tiradas largas (T72)**: PID 6474, `/tmp/opencode/t72_piloto_v2.py`,
  salida `fase0/piloto_fase1_v2/prueba.jsonl` (12 lecturas).
- **Generadores antiguos**: PID 66101 (nodo1) y 66396 (nodo2) siguen
  suspendidos. **No reanudar**: usan prompts viejos sin tildes. Tampoco se debe
  relanzar `generate_synthetic.py` sobre `jobs.db` sin copia previa.
- Logs de referencia: `afirmaciones_full/run_k5.log`,
  `afirmaciones_libros/run_nuevas.log` (y `run_full.log`, `run_k5.log`),
  `evidencias_web/run_incremental1.log`, `libros_clasicos_pd/run_resto.log`,
  `libros_reproceso_waite/run.log`, `consenso_kb/run_consenso*.log` y
  `afirmaciones_rapido/pasada.log`.

### Cifras reales (foto de 2026-10-21, con procesos aún escribiendo)

| Dato | Valor |
|---|---|
| Evidencias web (`evidencias_web/evidencias.jsonl`) | 18.142 |
| Evidencias de libros (`libros/evidencias/evidencias.jsonl`) | 18.230 |
| Afirmaciones web (`afirmaciones_full/afirmaciones.jsonl`) | 100.401 |
| Afirmaciones de libros (`afirmaciones_libros/afirmaciones_libros.jsonl`) | 30.283 |
| Afirmaciones rápidas (Mercury, `afirmaciones_rapido/`) | 30.796 web + 4.384 libros |
| Celdas de consenso (`consenso_kb/consenso.jsonl`) | 1.958 y creciendo |
| Lecturas trabajadas | 231 |
| Muestras del 3 % | 2.712 |
| `jobs.db` | 10.636: 360 `done`, 10.270 `pending`, 6 `running` |
| Corpus web | 3.568 `.md` |
| `fase0` completo | ~308 MB |

`kb_v2/` tiene ya `astrologia.json` (930 celdas, 282 con núcleo; 164 alta, 644
media, 122 baja), `numerologia.json` (471/152; 100/351/20) y
`baraja_espanola.json` (239/76; 25/199/15). `tarot.json` no existe todavía
porque el consenso de tarot no había llegado. El diff contra la KB v1 detecta 103
contradicciones y 777 celdas nuevas; la cobertura «con núcleo» es 30,3 % en
astrología, 32,3 % en numerología y 31,8 % en baraja, y 0 % en tarot.

La matriz `cobertura_total_v2.md` sigue en 259 de 7.455 celdas completas (3,5 %):
Tarot 173/936 (18,5 %), Astrología 79/5.247 (1,5 %), Numerología 5/792 (0,6 %) y
Baraja 2/480 (0,4 %), con 372 evidencias ignoradas. La recuperación 2 no se
fusionó: 150 URLs en `web_recup2/`, de las que fallaron por completo biddytarot y
labyrinthos y tarot.com dejó 8 errores. El pool de baraja y numerología está
agotado; hacen falta fuentes nuevas (T74).

### Infraestructura

- nodo1 `10.0.0.3:8000/v1` y nodo2 `10.0.0.4:8000/v1`, ambos con **halogen
  0.18.13** desde el 2026-10-21. Nodo1 admite concurrencia; nodo2 va más justo.
- Mini `10.0.0.1`: Postgres y Ollama en `127.0.0.1:11434` (embeddings).
- Firecrawl en `localhost:3002` (Docker).
- **Mercury 3** (Inception, `https://api.inceptionlabs.ai/v1`, modelo
  `mercury-3`) con tokens gratuitos: uso **complementario**, no sustituye a los
  nodos. La clave vive solo en el entorno (o en la auth de opencode); nunca en el
  repo, en informes ni en logs. En la comparativa T68: 0 errores, 1,08 s por
  petición, 1.607 tokens por evidencia y solo 1,5 % de solape exacto con el nodo
  local; sirve para pasadas rápidas y para contraste, no como generador único.

### Decisiones abiertas del usuario

1. **Revisión del 3 %**: son 2.712 fichas; decidir si se reduce al 1 %, a las de
   mayor calidad o se hace por muestreo estratificado.
2. **Libros no españoles**: el 55,7 % de la muestra de libros no es español;
   decidir si se traducen, se filtran o se conservan como evidencia de tradición.
3. **Hito de cobertura**: asumir que la cobertura completa solo es viable en tarot
   y fijar mínimos menores para astrología, numerología y baraja (bajar del 10 %
   exigiría ~24.700 fuentes nuevas).
4. **Compra de libros**: prioridad baraja española (Salas); sin precios
   verificables de forma automática y con presupuesto muy limitado.
5. **Respuesta de Hugging Face** sobre `Pepere45/spanish-esotericism-corpus`.
6. **Esqueleto del backend de la app** (FastAPI) y del frontend: todavía no hay
   código en el repo.
7. **Generación completa de fase 1**: con qué modelo y en qué nodo; el piloto T49
   midió ~64 s por lectura (169,9 s con reintentos), es decir, ~59 h para 10.000
   lecturas con 3 workers. Hasta decidirlo, `jobs.db` no se toca.

### Riesgos

- Dos procesos de consenso concurrentes sobre el mismo `consenso.jsonl`.
- Nodos saturados: las pasadas reales de evidencias (T47) devolvieron 0 juicios
  por falta de capacidad; no lanzar trabajo LLM nuevo sin comprobar carga.
- Ficheros en crecimiento sin cifra cerrada; las tablas de §4 y de esta sección
  son una foto, no un total.
- `jobs.db` conserva prompts viejos y 10.270 pendientes: cualquier reanudación
  debe pasar por `ejecutor_fase1.py` y por una copia previa de la BD.
- Tarot sigue sin KB v2 y la baraja/numerología no tienen fuentes suficientes;
  el riesgo de cerrar la fase 0 con la cobertura actual es alto.
- Presupuesto: Mercury es gratuito por ahora, pero no hay que asumir que lo sea
  siempre; medir consumo antes de tandas grandes.

## 8h. Actualización 2026-10-21 (T104): cierre de la fase 0 y arranque de la fase 1

Desde T77 han entrado en `main` 23 merges (T78–T101d): exclusiones del consenso
(T78), fuentes ronda 3 (T79), tareas de baraja (T80), auditoría ronda 5 y sus
arreglos (T81/T91), cobertura v3 (T82), piloto Mercury (T83), inventario legal
(T84), cierre de la recopilación (T85/T90), fuentes ronda 4 (T86), clave completa
del consenso (T87), filtro de atribución (T88), baraja en el ejecutor (T89),
pasada rápida parcial (T94), documento de generación y formato ShareGPT (T95),
auditoría ronda 6 y sus arreglos (T96/T101/T101b/T101c/T101d), línea base de modelos
(T99) y muestra de revisión v2 (T93). Detalle de cada módulo en `docs/PIPELINE.md`
(revisado hoy) y en los documentos `docs/CIERRE_RECOPILACION.md`,
`docs/COBERTURA_V3.md`, `docs/ATRIBUCION_ENTIDADES.md`,
`docs/INVENTARIO_LEGAL.md`, `docs/PILOTO_MERCURY.md`, `docs/GENERACION_FASE1.md`,
`docs/LINEA_BASE_MODELOS.md`, `docs/REVISION_3PC.md` y `docs/AUDITORIA_RONDA5.md`
/`RONDA6.md`.

### Cierre de la fase 0 (recopilación)

- Orquestador `cierre_recopilacion.py` (T85/T90): 7 pasos con copias previas
  (`pre-cierre-ts`, `pre-filtro-atrib-ts`, `pre-exclusion-ts`) y log en
  `fase0/cierre/cierre_log.jsonl`.
- Consenso **cerrado**: 3.688 celdas. `kb_v2` ya tiene las cuatro familias
  (existe `kb_v2/tarot.json`): 1.719 celdas nuevas frente a v1, 203 afirmaciones
  que contradicen a v1, sin respaldo en v1: 1 de tarot, 22 de astrología, 0 de
  numerología y baraja. Cobertura del núcleo: tarot 88,7 %, astrología 31,6 %,
  baraja 33,5 %, numerología 32,3 %.
- Cobertura v3 (pasada real 2026-10-21): 7.455 celdas, **304 completas (4,1 %)**:
  tarot 172/936 (18,4 %), baraja 36/480 (7,5 %), astrología 85/5247 (1,6 %),
  numerología 11/792 (1,4 %). La v2 marcaba 259. Base: 19.481 evidencias web
  limpias + 14.223 de libros.
- Filtro de atribución (T88): 2.188 evidencias retiradas (1.365 web, 823 libros),
  1.372 claves propuestas para el consenso; revisión manual 20+20 con 0 falsos
  positivos. **No aplicado todavía a producción**: el paso 3 del cierre espera
  decisión humana. Antes/después del filtro, celdas completas: astrología 86→75,
  numerología 11→6, total 308→292.
- Inventario legal (T84): 204 fuentes (38 libres, 112 a consultar, 54 de riesgo
  alto). Simulación de excluir el riesgo alto: 310→297 celdas completas
  (pierden astrología y numerología; tarot y baraja no pierden ninguna).
- Pasada rápida de afirmaciones (T94, Mercury): **parada de seguridad el
  2026-10-21 17:35** al 2.214/10.512 evidencias por >20 % de errores al coincidir
  con el arranque de T100 en el mismo backend. Aceptó 17.681 afirmaciones y gastó
  3.935.034 tokens. Reanudable con `--workers 1` al terminar T100; sus extras no
  entran en el consenso hasta fusionarlos con `--extra-afirmaciones` y
  `--rehacer-celdas-con-extra`.
- Muestra de revisión del 3 % (T93): nueva en `fase0/muestras_v2/revisor.html`
  con 6.982 fichas (web 754, libros 447, afirmaciones 5.645, lecturas 16,
  consenso 120), 659 (9,4 %) prerevisadas. **La revisión humana no ha
  empezado**: 6–10 h en total; ~40 min si solo se validan las marcadas.

### Fase 1: primera pasada real de generación

- Piloto Mercury (T83): 42/45 tareas ok (93 % con reintento); latencia media
  4,1 s frente a 169,9 s del nodo local (~40×); coste estimado de la pasada
  completa ~6,7 USD a precios de lanzamiento.
- Pasada completa **en curso (T100)**: 11.936 tareas (12.536 pendientes tras
  regenerar `jobs.db` en T95 con `--replace-pending`, D6 verificado: 0 sin
  tildes; menos 600 de `sinastria` excluidas porque el 65 % salió truncada en la
  muestra de 300). PID 78477, backend Mercury, 3 workers, formato ShareGPT,
  arranque 17:47. Instantánea al redactar este documento: 5.490 aceptadas / 71
  rechazadas en `fase0/fase1_mercury/`, ~53 lecturas/min, ETA ~3,7 h. La clave
  `INCEPTION_API_KEY` solo viaja por entorno; parada de seguridad rc=3 si el
  ratio de errores supera el 20 % en la ventana. Opt-out de entrenamiento de
  Inception desactivado (confirmado por el usuario).
- Reverificación (T101): `reverificar_fase1.py` aplica el verificador corregido
  de la ronda 6 a las aceptadas; `fase0/fase1_reverif/` provisional: 5.340 ok / 1
  rechazada (misma instantánea, crece con la pasada).
- Línea base sin entrenar (T99): Flash Next en nodo2 179/240 (74,6 %; ≈86,3 %
  ajustados los 28 rechazos que eran artefactos del verificador). Umbrales
  propuestos para el entrenado por familia en `docs/LINEA_BASE_MODELOS.md`.
  Peores familias: tránsitos (1/20), numerología (9/20), carta natal (10/20).

### Calidad: auditorías ronda 5 y 6

- Ronda 5 (T81→T91): consenso agrupado mal por `source_id`, payloads malformados
  que abortaban el ejecutor, líneas corruptas en recuperación, `kb_v2` pasa a
  last-wins, `merge_final` atómico, prompts con la etiqueta de año personal,
  sinónimos de baraja.
- Ronda 6 (T96→T101): `--replace-pending` duplicaba hechos, fuga de casos de
  evaluación a entrenamiento, cartas inventadas y orientación por carta en las
  tiradas largas, números en frase natural, promesas vedadas por perífrasis,
  dedupe que conservaba el peor. **t101d integrado al redactar este documento**
  (merge `97c2e55`, commit `59f9985`): el detector de cartas inventadas ahora se
  ejecuta también en `cruz_celta`, `lectura_completa` y `astro_natal` cuando no
  se reconstruye la tirada; rechaza el 100 % de los 7.424 casos inventados de
  prueba sin tocar ninguna lectura original.

### Procesos vivos (cuidado)

- Ejecutor T100 PID 78477 (Mercury; no usa nodo1). No lanzar otra pasada al mismo
  backend hasta que termine.
- T94 parado, relanzable. Generadores viejos 66101/66396 suspendidos y **no se
  reanudan**. Nodo1 reservado (comprobar antes de lanzar nada).

### Pistas en worktree sin merge

- **t92** clásicos de astrología/tarot PD a `libros_clasicos_pd2/` (sin fusionar).
- **t97** recopilación nocturna (descubrir+descargar+evidencias hacia huecos v3).
- **t100** pasada de generación fase 1 (en curso).
- **t103** `armar_dataset_v1.py` (no existe aún): copia → reverificar → fuga a
  evaluación → ShareGPT → `validate_synthetic` → `merge_final` →
  `preparar_entrenamiento`, salida en `fase0/dataset_fase1_v1/`.
- **t104** esta pista: documentación.

### Decisiones abiertas (actualiza §8g)

1. Revisión humana del 3 % sobre las 6.982 fichas nuevas de `muestras_v2/`.
2. Aplicar o no el filtro de atribución a producción (paso 3 del cierre).
3. Hito de cobertura: para el 10 % faltan ~12 fuentes de baraja, ~440 de
   astrología y ~69 de numerología (recuperación dirigida); tarot ya supera el
   listón. Asumir completo solo en tarot.
4. Subir el piso de `sinastria` de 4096 a 6144 tokens y relanzar sus 600 tareas.
5. Libros no españoles (55 % de la muestra) y compra de libros de baraja (Salas).
6. Backend (FastAPI) y frontend de la app: sigue sin código.

### Riesgos (actualiza §8g)

- Dos pasadas simultáneas al mismo backend Mercury provocan la parada de
  seguridad (ya pasó con T94/T100): un solo inquilino.
- `fase1_mercury/` y `fase1_reverif/` crecen mientras T100 corre: las cifras de
  este documento son una instantánea.
- La reverificación de la pasada T100 debe rehacerse con `reverificar_fase1.py`
  tras el detector corregido de t101d antes de armar el dataset v1; `id 11881`
  queda como único rechazo discutible.
- Cuota Mercury 100 M de tokens gratis: T69 gastó ~28 M, T94 ~3,9 M y T100
  consumirá ~26 M entre entrada y salida; si se agota, la pasada completa cuesta
  ~6,7 USD.
