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
