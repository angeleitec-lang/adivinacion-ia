# Tubería de datos y generación (mapa técnico)

Documento de orientación rápida para retomar el proyecto tras un reinicio. Describe
la tubería **real** del repositorio, no la prevista. Se apoya en:

- [`docs/ESTADO_Y_PENDIENTES.md`](ESTADO_Y_PENDIENTES.md): estado y cifras del proyecto.
- [`docs/PLAN_ADQUISICION_CALIDAD.md`](PLAN_ADQUISICION_CALIDAD.md): criterios de calidad.
- [`docs/INVENTARIO_FUENTES.md`](INVENTARIO_FUENTES.md): fuentes disponibles.
- [`finetune/GUIA_REENTRENAMIENTO.md`](../finetune/GUIA_REENTRENAMIENTO.md): entrenamiento.

Todo lo que sigue se comprobó con `--help`, con simulaciones (`--simulado`,
`--dry-run`) o leyendo el código. Última revisión: 2026-10-21 (T104), que añade
los módulos integrados entre T71 y T101 (cierre de la recopilación, atribución
de entidades, cobertura v3, inventario legal, fase 1 con Mercury y línea base).
La revisión anterior (T77) cubría T52–T70. Las discrepancias encontradas están al
final.

## Convenciones

```bash
cd /Users/angelgonzalez/adivinacion-ia
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python   # 3.11.15
```

- Datos de fase 0: `/Users/angelgonzalez/fase0/` (fuera del repo, no versionado).
- Datos de fase 1: `finetune/corpus/` (la mayoría en `.gitignore`).
- Tests: `unittest`, nunca `pytest`. Verificación global:
  `./finetune/scripts/check.sh` debe terminar en `CHECK OK`.
- Git solo local. Nada de `git push`.

## 1. Flujo completo

```text
FASE 0 · adquisición y curaduría
  ┌ web: índices/rejillas/Exa → web_pipeline/collect_corpus → fase0/web/<dominio>/*.md
  ├ libros: inventario → libros_pipeline / harvest_epubs / fetch_documents /
  │          docs_to_md / descarga_clasicos_pd → fase0/libros/{crudo,limpio,secciones}
  │          └→ clasicos_pd_a_evidencias.py → fase0/libros_clasicos_pd/
  │          └→ limpiar_evidencias_libros.py (propuesta de filtro, no aplica)
  └ YouTube: yt_discover → yt_fetch → yt_clean → yt_classify/yt_extract/yt_normalize
             → fase0/youtube/
                          │
                          ▼
   juez.py / evidencias_incremental.py (secciones + KB + cálculos, LLM) → evidencias.jsonl
       ├→ cobertura.py / cobertura_v3.py → cobertura_total{,_v3}.json/md
       │      └→ recuperacion_dirigida.py → plan_recuperacion.jsonl
       │             └→ descubrir_fuentes.py → plan de URLs → recuperacion_descarga.py
       │                 → fase0/web_recup{2,3,4,5}/ (sin fusionar)
       ├→ afirmaciones_es.py (web, LLM) → afirmaciones.jsonl
       ├→ afirmaciones_libros.py (libros, LLM) → afirmaciones_libros.jsonl
       ├→ afirmaciones_rapido.py (Mercury 3, T69/T94) → fase0/afirmaciones_rapido/
       │      └→ consenso_kb.py (con --extra-afirmaciones y --excluir-claves)
       │             └→ kb_v2.py → kb_v2/{tarot,astrologia,numerologia,baraja_espanola}.json
       └→ lecturas_extraer.py (libros, LLM) → lecturas.jsonl

   CIERRE DE LA RECOPILACIÓN (T85/T90, docs/CIERRE_RECOPILACION.md):
   cierre_recopilacion.py orquesta 7 pasos sobre copias previas — 1 dedupe del
   consenso, 2 limpieza de libros (aplicar_limpieza_libros.py → libros_limpio/),
   3 filtro de atribución (filtro_atribucion.py, T88; decisión humana antes de
   aplicar), 4 consenso con exclusiones, 5 kb_v2, 6 cobertura_v3, 7 informe —
   con log en fase0/cierre/cierre_log.jsonl. Paralelo: inventario_legal.py
   clasifica el riesgo legal de las fuentes (docs/INVENTARIO_LEGAL.md).
                           │
  muestras.py (3 %) → prerevision.py → revisor_local.py
      → muestras_revisadas.jsonl → muestras.py --accion oro → oro.jsonl
                          │
FASE 1 · dataset
  generate_tasks.py → jobs.db
      → ejecutor_fase1.py (prompt + verificar_lectura, reintentos) ─┐
      → generate_synthetic.py ──────────────────────────────────────┤
  fase1_prompts.py ────────────────────────────────────────────────┼→ JSONL sintético
  fase1_piloto.py (medición de familias) ──────────────────────────┤   → validate_synthetic.py
  multiturno.py ───────────────────────────────────────────────────┘        │
                                                                            ├→ translate_dataset.py / prune_short_en.py
                                                                            └→ merge_final.py → audit_dataset.py
                                                                                 → finetune/corpus/final/{train,val,test}.jsonl
  ensayo_extremo.py: simulación de punta a punta sin red → informe de desajustes (T70)
                          │
FASE 2 · modelo
  final/ → entrenamiento (QLoRA/Soup) → evaluacion_casos.py → respuestas
      → evaluar_modelo.py → informe y comparación entre modelos
```

`comparar_backends.py` es auxiliar: mide cuánto aporta un backend externo
(Mercury 3) frente a los nodos locales sobre las mismas evidencias; no forma
parte de la tubería principal.

Rutas alternativas, no usadas en la tubería principal: `build_dataset.py` y
`build_scrapy_dataset.py` convierten Markdown de Firecrawl en ShareGPT y hacen el
split por documento; `merge_datasets.py` fusiona dos datasets ShareGPT.

## 2. Módulos

Comandos abreviados: `$PY finetune/corpus/<módulo>.py`. «LLM» indica si el módulo
llama a un modelo; las calculadoras y los conversores son deterministas.

### 2.1 Web

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `web_indices.py` | Descubre índices de un sitio | config JSON | JSONL de URLs | `--config … --limite 50` | no | no | prod |
| `web_rejillas.py` | Expande rejillas de URLs por sitio/faceta | `knowledge/` | JSONL | `--solo-sitios … --limite 100` | no | no | prod |
| `discover_urls.py` | Descubre URLs con Exa | temas | JSONL | `--topics tarot --num 20 --dry-run` | no | no | piloto |
| `web_pipeline.py` | Orquesta descubrimiento, descarga cortés y extracción | config de sitios | `web/<dominio>/*.md`, manifest, informe | `--work-dir /Users/angelgonzalez/fase0/web` | no | sí (por URL) | prod |
| `collect_corpus.py` | Scrape/crawl/agent con Firecrawl | URLs o prompt | Markdown crudo | `--mode scrape --urls urls.txt --raw …` | no | parcial | piloto |
| `web_extraer.py` | HTML → Markdown con trafilatura | HTML | `.md` | `--html p.html --url … --out-dir …` | no | no | aux |
| `web_calidad.py` | Auditoría determinista del corpus web | `web/` | informes | `--web-dir … --out-dir …` | no | no | prod |
| `web_informe.py` | Informe de descargas desde manifest | manifest | Markdown | `--manifest … --out-dir …` | no | no | aux |
| `descubrir_fuentes.py` | Genera un plan de URLs candidatas por conjunto conocido (T79/T86) | rejillas y listas internas | JSONL de URLs | `--out plan_t86.jsonl --conjunto t86 --max-por-dominio 40 --excluir-manifest …/web/manifest.jsonl` | no | no (regenera) | prod |
| `recuperacion_descarga.py` | Descarga cortes del plan sin LLM, saltando lo ya bajado (T64/T74/T79/T86) | `plan_*.jsonl`, manifest previo | `fase0/web_recup{2,3,4,5}/` (+ `_r4/_r5/_all`) e informe | `--plan …/plan_t86.jsonl --out-dir …/web_recup5 --manifest-previo …/web/manifest.jsonl --tope-por-dominio 40 --max-total 200 --matriz …/cobertura_total_v3.json` | no | sí (omite ya descargadas) | prod |
| `web_fetch.py` | Cliente HTTP educado | URL | HTML | sin CLI | no | — | aux |

### 2.2 Libros y clásicos

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `libros_pipeline.py` | Orquesta descarga, limpieza, segmentación, informe y juez | inventario | `fase0/libros/` | `--work-dir /Users/angelgonzalez/fase0/libros --hasta juez` | en etapa juez | sí | prod |
| `libros_fetch.py` | Descarga de archive.org | inventario | `crudo/<id>.txt`, `fetch.jsonl` | `--knowledge-dir … --out-dir …` | no | sí | prod |
| `libros_extraer.py` | Extrae EPUB locales | EPUB | texto | sin `--help` | no | no | aux |
| `libros_limpiar.py` | Limpieza de OCR | crudo | limpio | sin `--help` | no | no | prod |
| `libros_segmentar.py` | Segmenta por capítulos/secciones | limpio | secciones JSONL | sin `--help` | no | no | prod |
| `libros_informe.py` | Informe del work-dir | `--in-dir` | Markdown | `--in-dir … --out …` | no | no | aux |
| `libros_fuentes.py` | Inventario unificado de fuentes | knowledge | listado | sin `--help` | no | no | aux |
| `harvest_epubs.py` | Busca EPUB en archive.org | temas | EPUB + manifest | `--topics tarot --max-per-topic 5` | no | no | piloto |
| `fetch_documents.py` | Descarga PDF/EPUB de archive.org | inventario | ficheros + manifest | `--only … --max-size-mb 80` | no | parcial | piloto |
| `docs_to_md.py` | PDF/EPUB → Markdown | documentos | `.md` | `--docs … --out …` | no | sí (`--force` rehace) | aux |
| `descarga_clasicos_pd.py` | Descarga clásicos de dominio público (T55) | inventario | `crudo/<id>.txt`, manifiesto | `--out-dir /Users/angelgonzalez/fase0/libros` | no | sí | piloto |
| `clasicos_pd_a_evidencias.py` | Limpieza, segmentación y juez de los clásicos descargados (T57) | `libros_clasicos_pd/` | `fase0/libros_clasicos_pd/{secciones,juicios,evidencias}` | `--work-dir …/libros_clasicos_pd --hasta juez` | en etapa juez | sí (por etapa) | prod |
| `limpiar_evidencias_libros.py` | Propone un filtro de evidencias de «mayores» sin tocar producción (T53) | evidencias + secciones | `evidencias_filtradas.jsonl`, `informe_filtro.md` | `--evidencias … --secciones-dir … --out-dir …` | no | no | aux |

### 2.3 Evidencias, afirmaciones, lecturas y cobertura

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `juez.py` | Decide entidad/faceta/calidad de cada sección y escribe evidencias | secciones JSONL/MD | `juicios.jsonl`, `evidencias.jsonl`, informe | `--secciones … --out-dir … --workers 4` | sí | sí (hash) | prod |
| `cobertura.py` | Matriz entidad × faceta | evidencias JSONL | `cobertura.json/md` | `--evidencias … --out-json … --out-md …` | no | no (recalcula) | prod |
| `cobertura_dataset.py` | Cobertura de un dataset | JSONL | matriz | `--in … --minimo 5` | no | no | aux |
| `recuperacion_dirigida.py` | Convierte huecos en plan de recuperación | `cobertura_total.json` | `plan_recuperacion.jsonl`, informe | `--matriz … --out-plan …` | no | no | prod |
| `evidencias_incremental.py` | Lleva páginas web nuevas hasta evidencias con juez, en append (T47) | `web/`, `evidencias.jsonl` previas | append a `evidencias.jsonl` + `.bak` | `--web-dir …/web --evidencias …/evidencias.jsonl --dominios … --limite 500` | sí | sí (hash de sección) | prod |
| `afirmaciones_es.py` | Extrae afirmaciones atómicas de evidencias web (T29) | evidencias + `web/` | `afirmaciones.jsonl`, procesados | `--limite 200 --workers 2` | sí | sí (`procesados.jsonl`) | prod |
| `afirmaciones_libros.py` | Extrae afirmaciones con cita verbatim de evidencias de libros (T38) | evidencias + secciones | `afirmaciones_libros.jsonl`, procesados | `--evidencias … --secciones-dir … --out-dir … --limite 200` | sí | sí (procesados) | prod |
| `consenso_kb.py` | Vota por celda (entidad × faceta) agrupando afirmaciones por fuente; dedup por fuente, clave COMPLETA `hash_seccion+entidad_id+faceta` (T38/T73/T78/T87) | afirmaciones web y libros (+ `--extra-afirmaciones`, `--excluir-claves` repetible) | `consenso_kb/consenso.jsonl` + informes | `--web-afirmaciones … --libros-afirmaciones … --out-dir …/consenso_kb --workers 6 --excluir-claves …/claves_excluir_consenso.jsonl --rehacer-celdas-con-exclusion` | no | sí (cache de equivalencia) | prod |
| `kb_v2.py` | Construye la KB v2 desde el consenso y la compara con `kb/*.json` (T66) | `consenso.jsonl`, KB v1 | `kb_v2/*.json`, `diff_vs_kb_v1.md` | `--consenso …/consenso.jsonl --out-dir …/kb_v2 --kb-v1 finetune/corpus/kb` | no | no (determinista) | prod |
| `kb_v2.py` | Construye la KB v2 desde el consenso y la compara con `kb/*.json` (T66); hoy incluye `tarot.json` (3.688 celdas, 1.719 nuevas vs v1, 203 contradicen) | `consenso.jsonl`, KB v1 | `kb_v2/{tarot,astrologia,numerologia,baraja_espanola}.json`, `diff_vs_kb_v1.md` | `--consenso …/consenso.jsonl --out-dir …/kb_v2 --kb-v1 finetune/corpus/kb` | no | no (determinista) | prod |
| `aplicar_limpieza_libros.py` | Aplica en copia la limpieza de libros y mide el efecto (T71); no toca la evidencia original | evidencias + secciones + afirmaciones | `fase0/libros_limpio/{evidencias_limpias,evidencias_retiradas,claves_excluir_consenso,muestra_revision}.jsonl`, `informe_limpieza.json` | `--evidencias … --secciones-dir … --afirmaciones-dir … --out-dir …/libros_limpio` | no | no | prod |
| `filtro_atribucion.py` | Retira evidencias de astrología/numerología mal atribuidas a otra entidad; determinista, sin LLM; la decisión de aplicar a producción es humana (T88, `docs/ATRIBUCION_ENTIDADES.md`) | evidencias web/libros + secciones + procesados | `fase0/filtro_atribucion/{evidencias_retiradas,claves_excluir_consenso,muestra_revision}.jsonl`, `informe_filtro.json` | `--base /Users/angelgonzalez/fase0 --salida …/filtro_atribucion` | no | no (determinista) | prod (sin aplicar aún) |
| `cobertura_v3.py` | Matriz de cobertura reproducible con las evidencias vigentes y las exclusiones aplicadas (T82, `docs/COBERTURA_V3.md`) | evidencias web + libros (limpios o crudos) + claves a excluir | `fase0/cobertura_v3/cobertura_total_v3.{json,md}` | `--web … --libros limpio --libros-limpio … --excluir-claves … --out-dir …/cobertura_v3` | no | no (recalcula) | prod |
| `inventario_legal.py` | Inventario de procedencia y licencias por metadatos, sin red; riesgo `libre`/`consultar`/`riesgo_alto` (T84, `docs/INVENTARIO_LEGAL.md`) | `fase0/` + `finetune/knowledge/` | `fase0/inventario_legal/` + Markdown | `--fase0 /Users/angelgonzalez/fase0 --out-dir … --md` | no | no (solo lectura) | prod |
| `cierre_recopilacion.py` | Orquesta el cierre de la fase 0 en 7 pasos: dedupe del consenso, limpieza de libros, filtro de atribución, consenso con exclusiones, KB v2, cobertura v3 e informe, con copias previas (T85/T90, `docs/CIERRE_RECOPILACION.md`) | todo `fase0/` | `fase0/cierre/cierre_log.jsonl` + salidas de cada paso | `--base-dir /Users/angelgonzalez/fase0 --dry-run` y luego `--todo` (o `--paso {1..7}`, `--solo-verificar` solo con paso 2/3) | en pasos con juez/afirmaciones | sí (log y copias `pre-cierre-ts`, `pre-filtro-atrib-ts`, `pre-exclusion-ts`) | prod |
| `afirmaciones_rapido.py` | Pasada de afirmaciones con backend rápido Mercury 3; integrada en `main` (T69/T94); parada de seguridad el 2026-10-21 a 2.214/10.512 evidencias | evidencias web/libros + procesados | `fase0/afirmaciones_rapido/{web,libros}/`, `informe.md` | `INCEPTION_API_KEY=… $PY finetune/corpus/afirmaciones_rapido.py --workers 1 --limite …` | sí (API) | sí (procesados) | prod (pasada incompleta) |
| `lecturas_extraer.py` | Detecta y clasifica lecturas trabajadas (T37/F0.5) | secciones + juicios | `lecturas.jsonl` | `--limite 50 --workers 2` | sí | parcial | piloto |
| `build_kb.py` | Construye/valida la KB de significados | `kb/*.json` | KB validada | `--validate --out …` | no | no | prod |
| `cartas.py` | Catálogo y normalización de 78 tarot + 40 españolas | texto | JSON | `texto --mazo español` | no | — | prod |
| `calculos/*.py` | Carta natal, numerología, biorritmos | datos de consulta | cálculos | importación / CLI propia | no | — | prod |
| `diagnostico_tarot_libros.py` | Diagnóstico de solo lectura | corpus | informe | sin `--help` | no | — | aux |

### 2.4 Generación y dataset

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `generate_tasks.py` | Crea la matriz de trabajos | semilla, escala | `corpus/jobs.db` | `--scale 1.0` | no | sí (`--replace-pending`) | prod |
| `generate_synthetic.py` | Reclama jobs y genera lecturas (prompts antiguos) | `jobs.db` | `synthetic/*.jsonl` | `--endpoint http://10.0.0.3:8000/v1 --workers 4` | sí | sí (estado en DB) | legado: no reanudar |
| `ejecutor_fase1.py` | Runner de fase 1 sobre `jobs.db`: prompt actual, `verificar_lectura`, reintento con causa, reclamo atómico y copia previa de la BD; backends `local` (nodo) y `mercury` (Inception, T95, `docs/GENERACION_FASE1.md`); parada de seguridad si >20 % de errores en la ventana (rc=3); salida `--formato sharegpt` | `jobs.db`, `fase1_prompts`, KB | `aceptadas.jsonl`, `rechazadas.jsonl`; estados `done`/`failed` | `INCEPTION_API_KEY=… $PY finetune/corpus/ejecutor_fase1.py --backend mercury --db /tmp/fase1_mercury_full.db --workers 3 --formato sharegpt --out-dir …/fase1_mercury` (piso de tokens por familia en `fase1_prompts.RECOMENDACION_MAX_TOKENS`: `cruz_celta`/`lectura_completa` 6144, `espanola_7` 5120; mercury timeout 180 s, temp 0,5; `--solo-estimar`, `--ventana-errores`, `--umbral-error`) | sí | sí (estado en DB + huérfanos) | prod |
| `piloto_mercury.py` | Piloto de 3 lecturas por familia con Mercury 3 para medir aceptación y latencia (T83, `docs/PILOTO_MERCURY.md`: 42/45 ok) | semillas reservadas | `fase0/piloto_mercury/{piloto.jsonl,informe.md}` | `INCEPTION_API_KEY=… $PY finetune/corpus/piloto_mercury.py --n-por-familia 3 --semilla 83` | sí (API) | sí (semilla) | prod |
| `reverificar_fase1.py` | Re-verifica `aceptadas.jsonl` con el verificador corregido de la ronda 6 (T101/T101b/T101c/T101d) | `aceptadas.jsonl` de una pasada | `fase0/fase1_reverif/aceptadas_reverificadas.jsonl` + `.rechazadas` | `$PY finetune/corpus/reverificar_fase1.py --aceptadas …/aceptadas.jsonl --salida …/aceptadas_reverificadas.jsonl --eval-casos …/casos-semilla560056.jsonl` | no | no | prod |
| `fase1_piloto.py` | Piloto por familias con el LLM real para medir aceptación y latencia (T49) | semillas reservadas | `fase0/piloto_fase1/{piloto.jsonl,informe_piloto.md,errores}` | `--n-por-familia 3 --workers 3 --model … --endpoints …` | sí | sí (semilla) | prod |
| `fase1_prompts.py` | Construye prompts con KB y cálculos | KB, recetas | JSONL de ejemplos | `--n 10 --out /tmp/ejemplos.jsonl` | no | no | prod |
| `multiturno.py` | Conversaciones de 2 fases (T45) | semilla | JSONL multiturno | `--n 5 --out /tmp/t45/ejemplos.jsonl` | sí | sí (por semilla) | piloto |
| `validate_synthetic.py` | Puertas de idioma, longitud, repetición, eco, coherencia y duplicados | `synthetic/` | `synthetic_clean.jsonl` + informe | `--dir corpus/synthetic` | no | no | prod |
| `translate_dataset.py` | Traduce EN→ES con el nodo | JSONL | JSONL traducido + `.progress` | `--train … --val … --resume` | sí | sí (`--resume`) | piloto |
| `prune_short_en.py` | Elimina pares ingleses demasiado cortos | raw/datasets | JSONL podado | `--raw … --datasets …` | no | no | aux |
| `merge_final.py` | Fusiona real + sintético, deduplica y divide | `train_final`, `synthetic_clean` | `final/{train,val,test}.jsonl`, `report.json` | `--real-train … --synth …` | no | no (rehace) | prod |
| `ensayo_extremo.py` | Ensayo de punta a punta con N tareas simuladas (sin red) y informe de desajustes entre etapas (T70) | `jobs.db` (solo lectura) | informe + salidas temporales del ensayo | `--db …/jobs.db --n 200 --base-dir /tmp/t70 --informe …/ensayo.md` | no | no | aux |
| `audit_dataset.py` | Auditoría final y filtro de licencia | datasets | informe | `--in … --out-dir …` | no | no | prod |
| `build_dataset.py` | Markdown Firecrawl → ShareGPT | `corpus/raw` | train/val | `--raw … --out …` | no | no | aux |
| `build_scrapy_dataset.py` | Scrapy JSONL → ShareGPT | `raw_scrapy` | train/val | `--raw … --out …` | no | no | aux |
| `merge_datasets.py` | Fusiona datasets ShareGPT | dos JSONL | JSONL | `--base … --new … --out …` | no | no | aux |
| `rag_index.py` | Índice RAG con embeddings de Ollama | documentos | índice | `--dirs … --out …` | embeddings | sí (`--resume`) | experimental |

### 2.5 Revisión, evaluación y salud

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `muestras.py` | Muestrea el 3 % por nivel (incluido `consenso`) o construye el oro (T48/T93) | `fase0/` | `muestras_v2/{muestras.jsonl,md}`, `oro.jsonl` | `--accion muestrear --nivel todos --out-dir /Users/angelgonzalez/fase0/muestras_v2` | no | no | prod |
| `prerevision.py` | Banderas deterministas sobre las muestras (T93: 659 de 6.982 fichas marcadas, 9,4 %) | muestras | `muestras_v2/prerevision.jsonl/md` | `--muestras …/muestras.jsonl --out-dir …/muestras_v2` | no | no | prod |
| `revisor_local.py` | Revisor HTML autocontenido con localStorage (T54); `docs/REVISION_3PC.md` | muestras + prerevisión | `muestras_v2/revisor.html` | `--out …/revisor.html --max-texto 6000` | no | no | prod |
| `linea_base.py` | Pasa los casos de evaluación T56 (240, semilla reservada 560056) por los modelos de referencia y los puntúa con `evaluar_modelo.py` (T99, `docs/LINEA_BASE_MODELOS.md`) | casos T56 + modelo | `fase0/linea_base/<modelo>/` (respuestas, informe) | `$PY finetune/corpus/linea_base.py --modelo flash-next --paralelo 2` (nodo2; `mercury-3` requiere `INCEPTION_API_KEY`) | sí | sí (semilla) | prod |
| `comparar_consenso.py` | Muestra celdas del consenso con sus fuentes para revisión puntual (T76) | `consenso.jsonl` + caché | informe por celda | `--n-celdas 20 --semilla 76 --consenso …/consenso.jsonl --desde-json …` | parcial (cache) | sí | aux |
| `evaluacion_casos.py` | 240 casos fijos, 20 por familia (T56) | semillas reservadas | `eval_casos.jsonl` | `--salida /tmp/eval_casos.jsonl` | no | no | prod |
| `evaluar_modelo.py` | Comprueba respuestas y compara modelos (T56) | casos + respuestas | informe JSON/MD | `--casos … --respuestas … --salida …` | opcional (`--juez-llm`) | caché del juez | prod |
| `salud_datos.py` | Integridad, vigilancia, reparación opt-in y copias (T59) | `fase0/` | informe + copia `.tar.gz` con SHA-256 | `--copia --backups …/fase0_backups` | no | — | prod |
| `comparar_backends.py` | Compara la extracción de afirmaciones del nodo local con Mercury 3 sobre las mismas evidencias (T65/T68) | evidencias ya procesadas + `INCEPTION_API_KEY` en el entorno | `fase0/comparativa_backends_v2.md` | `INCEPTION_API_KEY=… $PY finetune/corpus/comparar_backends.py` (sin argparse) | sí (API) | no | piloto |

### 2.6 YouTube

| Módulo | Qué hace | Entrada | Salida | Comando típico | LLM | Reanudable | Estado |
|---|---|---|---|---|---|---|---|
| `yt_pipeline.py` | Orquesta descubrir → fetch → clean → clasificar → extraer → normalizar | catálogo | `fase0/youtube/` | `--work-dir …/fase0/youtube --hasta normalizar` | en fases 4–6 | sí | piloto |
| `yt_discover.py` | Busca vídeos | consultas | `catalogo.jsonl` | `--n-por-consulta 5 --solo-espanol` | no | no | piloto |
| `yt_fetch.py` | Descarga subtítulos VTT | catálogo | `raw_vtt/`, `fetch.jsonl` | `--catalogo … --out-dir …` | no | sí | piloto |
| `yt_clean.py` | Limpia VTT | VTT | texto | posicional `video.vtt` | no | no | piloto |
| `yt_classify.py` | Clasifica si hay lectura trabajada | catálogo + fetch | JSONL | `--simulado` para probar | sí | parcial | piloto |
| `yt_extract.py` | Extrae la lectura | texto | JSONL | `--texto … --out …` | sí | no | piloto |
| `yt_normalize.py` | Normaliza a cartas/facetas | lecturas | JSONL | `--lecturas … --out-dir …` | sí | no | piloto |
| `yt_qa.py` | Control de calidad del lote | todas las fases | informe | `--catalogo … --fetch …` | no | no | aux |

## 3. Formatos JSONL reales

Todos los ejemplos son líneas reales recortadas. Los `…` indican texto omitido,
no campos inventados.

### 3.1 Evidencia

`/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl` (≈23.118 líneas
tras las tandas T79/T86/T94) y
`fase0/libros/evidencias/evidencias.jsonl` (18.230 crudas; 14.223 tras la
limpieza de `libros_limpio/`, T71).

```json
{"entidad_id":"tarot-copas-02","faceta":"significado_general","fuente_id":"https://angelestarotyvidencia.com/articulos/combinaciones-del-tarot/2-de-copas-y-la-estrella-en-el-tarot/","dominio":"angelestarotyvidencia.com","idioma":"es","periodo":"moderna","calidad":4,"tipo":"web","hash_seccion":"20801f25…"}
```

En libros, `tipo` es `"libro"`, `fuente_id` es el id del libro y `dominio` repite
ese id; por ejemplo `1899minettawhatthecardstell`, `idioma:"en"`,
`periodo:"clasica"`, `calidad:2`.

Campos: `entidad_id` (carta, planeta, número…), `faceta`, `fuente_id` (URL o id de
libro), `dominio`, `idioma`, `periodo` (`clasica`/`moderna`), `calidad` (1–5),
`tipo` (`web`/`libro`/`youtube`), `hash_seccion` (deduplicación y reanudación).

### 3.2 Afirmación

`/Users/angelgonzalez/fase0/afirmaciones_full/afirmaciones.jsonl`:

```json
{"entidad_id":"tarot-copas-02","faceta":"significado_general","fuente_id":"https://angelestarotyvidencia.com/articulos/combinaciones-del-tarot/2-de-copas-y-la-estrella-en-el-tarot/","dominio":"angelestarotyvidencia.com","periodo":"moderna","calidad":4,"afirmacion":"Esta combinación habla de sanación compartida y de vínculos que llegan en el momento exacto."}
```

Las afirmaciones de libros añaden la cita y la contradicción con la KB:

```json
{"entidad_id":"tarot-mayor-14","faceta":"significado_general","fuente_id":"1899minettawhatthecardstell","dominio":"1899minettawhatthecardstell","periodo":"clasica","calidad":2,"afirmacion":"…","cita_original":"deceit, immorality","contradice_kb":false}
```

`afirmacion` es una proposición atómica y atribuible; `cita_original` conserva el
texto fuente cuando el original no está en español; `contradice_kb` marca
discrepancias que no deben ocultarse.

### 3.3 Lectura

`/Users/angelgonzalez/fase0/lecturas/lecturas.jsonl` (231 líneas; detector y
clasificador con LLM):

```json
{"id":"78931deae97b717c81a20e9b97d5fcd1555416f938e3b35ab75e1554fbbfca91","fuente":"libro","libro_id":"1918minettacardreading","titulo_libro":"Card-Reading: A Practical Guide","autor":"Minetta","periodo":"clasica","seccion":24,"posicion":23,"sistema":"baraja_espanola","cartas":["Queen of Clubs","Ten of Hearts","Knave of Clubs"],"elementos":["significador","corte en tres montones","tendido de 32 cartas en cuatro filas"],"pregunta":"Consultante de ojos y cabello castaños…","calidad":4,"idioma":"en","motivo":"Presenta una consulta explícita…","texto":"ness Of the world-soul…"}
```

Campos: `fuente` (`libro`/`youtube`), `sistema` (`tarot`/`baraja_espanola`/…),
`cartas` y `elementos` tal como aparecen en el texto, `pregunta`, `calidad`,
`idioma`, `motivo` y `texto` completo de la lectura.

### 3.4 Muestra del 3 %

`/Users/angelgonzalez/fase0/muestras/muestras.jsonl` (2.712 líneas):

```json
{"id":"197473836d…","nivel":"web","origen":"web","estrato":["combinaciones","3"],"entidad_id":"1|camino_de_vida","sistema":null,"faceta":"amor","calidad":3}
```

`nivel` puede ser `web`, `libros`, `afirmaciones` o `lecturas`; `estrato` es la
combinación usada para muestrear proporcionalmente; `id` enlaza con la ficha
original que abre el revisor.

### 3.5 Prerevisión

`/Users/angelgonzalez/fase0/muestras_v2/prerevision.jsonl` (muestra T93 de 6.982
fichas, 659 marcadas; la antigua `muestras/prerevision.jsonl` tenía 2.712):

```json
{"banderas":[{"codigo":"contradiccion_kb","motivo":"cláusula «El naipe-copas-06 se relaciona con el elemento Tierra» atribuye tierra cuando la KB dice agua","peso":7}],"id":"6f9e…","nivel":"afirmaciones","puntuacion":7}
```

`puntuacion` ordena la revisión (`--top`); cada bandera tiene `codigo`, `motivo`
legible y `peso`. No sustituye la revisión humana.

### 3.6 Caso de evaluación

Generado por `evaluacion_casos.py` en `/tmp/eval_casos.jsonl` (240 líneas, 20 por
familia):

```json
{"id":"eval-tarot_1-01","familia":"tarot_1","origen":"evaluacion","system":"Eres una tarotista…","user":"Tirada de una carta de tarot.\n\nCarta: Siete de Bastos (invertida)…","tarea":{"familia":"tarot_1","contexto":"salud","pregunta":"¿Qué energía rodea mi bienestar físico y emocional?","cartas":[{"nombre":"Siete de Bastos","invertida":true}],"universo_cartas":["El Loco","El Mago","…"]},"calculos":{},"cartas":["Siete de Bastos"],"orientaciones":{"Siete de Bastos":"invertida"},"datos_esperados":{"cartas":["Siete de Bastos"],"invertidas":["Siete de Bastos"],"universo":["El Loco","…"]},"comprobaciones":["no_vacia","idioma","longitud","repeticion","promesas","cartas","orientacion","carta_ajena","datos"],"longitud_minima":60}
```

`tarea` es la especificación estructurada; `datos_esperados` y `comprobaciones`
alimentan el evaluador determinista; `longitud_minima` es en palabras.

### 3.7 Conversación multi-turno

`/tmp/t45/ejemplos.jsonl` (5 líneas; generado por `multiturno.py`):

```json
{"conversations":[{"from":"system","value":"Eres una tarotista…"},{"from":"human","value":"Hola, gracias por atenderme. Quería preguntarte qué energía hay en mi vida sentimental ahora mismo…"},{"from":"gpt","value":"Hola. Gracias por confiar en mí…"},{"from":"human","value":"No estoy en una relación formal…"},{"from":"gpt","value":"Te entiendo perfectamente…"}],"turnos":4,"metadatos":{"bloque":"multiturno","sistema":"Eres una tarotista…","cartas":[{"nombre":"Cinco de Copas","invertida":false}],"contexto":"amor","referencia":"…","datos_calculados":"","semilla":2026,"perfil":"persona adulta con una preocupacion actual","tipos":["…"],"verificada":true,"motivo":"…"}}
```

`turnos` cuenta los pares humano/asistente; `metadatos.semilla` permite reanudar
sin regenerar; `verificada` y `motivo` registran la puerta de calidad.

### 3.8 Fila de dataset

`/Users/angelgonzalez/adivinacion-ia/finetune/corpus/final/train.jsonl`:

```json
{"conversations":[{"from":"system","value":"Eres una experta en adivinación: tarot, astrología, numerología y quiromancia. Respondes con rigor, claridad y empatía, siempre en español."},{"from":"human","value":"¿Qué significa Preguntas frecuentes > ¿Qué significan los símbolos de las runas??"},{"from":"gpt","value":"Cada símbolo rúnico del Futhark Antiguo representa un sonido, un objeto y un concepto más amplio—por ejemplo, Fehu (ᚠ) significa tanto «ganado» como «riqueza»…"}]}
```

Formato ShareGPT: lista `conversations` con `from` (`system`/`human`/`gpt`) y
`value`. `merge_final.py` añade el split y `report.json` con recuentos; el formato
no incluye metadatos por fila (se pierden al fusionar).

## 4. Rutas y volumen

### `/Users/angelgonzalez/fase0/` (~497 MB, medido 2026-10-21 por T104)

Cifras medidas con los procesos de fondo aún escribiendo; `fase1_mercury/`
crece mientras corre la pasada de T100.

| Ruta | Contenido | Tamaño |
|---|---|---|
| `web/` | Markdown por dominio (3.568 `.md`) | 36 MB |
| `evidencias_web/` | `evidencias.jsonl` (≈23.118), juicios, informes y copias `.bak` | 19 MB |
| `libros/` | `crudo/`, `limpio/`, `secciones/`, `evidencias/` (18.230), `fetch.jsonl`, `errores.jsonl`, `informe.md` | 126 MB |
| `libros_limpio/` | Resultado de `aplicar_limpieza_libros.py` (T71): 14.223 evidencias limpias + retiradas y claves | 6,8 MB |
| `libros_clasicos_pd/` | Clásicos de dominio público (T57): secciones, juicios y evidencias | 7,6 MB |
| `afirmaciones/` | Salida por tandas de T29 | 2 MB |
| `afirmaciones_full/` | `afirmaciones.jsonl` (100.401 líneas de varias tanda) | 30 MB |
| `afirmaciones_libros/` | `afirmaciones_libros.jsonl` (30.283) | 17 MB |
| `afirmaciones_rapido/` | Pasada con Mercury (T69/T94): `web/` y `libros/`, parada de seguridad a 2.214/10.512 | 32 MB |
| `consenso_kb/` | `consenso.jsonl` cerrado en 3.688 celdas con exclusiones aplicadas, caché de equivalencia | 42 MB |
| `kb_v2/` | `tarot.json`, `astrologia.json`, `numerologia.json`, `baraja_espanola.json`, `diff_vs_kb_v1.md` | 16 MB |
| `filtro_atribucion/` | Salida del dry-run de `filtro_atribucion.py` (T88): retiradas, claves, muestra, informe | 7,1 MB |
| `inventario_legal/` | Inventario de fuentes y riesgo legal (T84) | 0,1 MB |
| `cobertura_v3/` | `cobertura_total_v3.{json,md}` (7.455 celdas, 304 completas) | 2,2 MB |
| `cierre/` | `cierre_log.jsonl` del orquestador (T85/T90) | 4 KB |
| `lecturas/` | `lecturas.jsonl` (231) | 2,4 MB |
| `muestras/` | Muestra antigua (T48): 2.712 fichas | 8,6 MB |
| `muestras_v2/` | Muestra actual T93: `muestras.jsonl` (6.982), `prerevision.jsonl` (659 marcadas), `revisor.html` | 15 MB |
| `youtube/` | catálogo, fetch, VTT, clasificación | 4,7 MB |
| `piloto_fase1/` | `piloto.jsonl` (33 lecturas) e informe | 0,2 MB |
| `piloto_mercury/` | Piloto Mercury T83 (45 tareas, 42 ok) | 0,3 MB |
| `linea_base/` | `casos-semilla560056.jsonl` y resultados `flash_next_nodo2/` (T99) | 1,9 MB |
| `web_recup2/`, `web_recup3/` | Descargas de la recuperación 2 y 3 (T64/T74), sin fusionar | 0,5 / 2,6 MB |
| `web_recup4/`, `web_recup5/` (+ `_r4/_r5/_all`) | Descargas de las tandas T79/T86, sin fusionar en el corpus | 8,8 / 3,5 MB |
| `fase1_mercury/` | Pasada completa T100 EN CURSO: `aceptadas.jsonl` (5.490 al medir) y `rechazadas.jsonl` (71) | 41 MB |
| `fase1_reverif/` | Aceptadas reverificadas con el verificador de T101 (5.340 ok, 1 rechazada) | 36 MB |
| `cobertura_total.json/md` | Matriz v2 histórica | 2,3 MB |
| `plan_recuperacion.jsonl` | 660 entidades bajo mínimo | 2,8 MB |

### `finetune/corpus/` (datos, casi todo ignorado por git)

- `jobs.db` (~33 MB): regenerado por T95/T100 con `generate_tasks.py --replace-pending`
  (D6 verificado: 0 pendientes sin tildes); 12.536 pendientes; la pasada Mercury en
  curso de T100 lanza 11.936 tareas tras excluir 600 de `sinastria`.
- `synthetic/`: `tarot_1.n1.jsonl` (1,1 MB), `tarot_1.n2.jsonl`, `etica.test.jsonl`.
- `synthetic_clean.jsonl` + `.meta.jsonl`; `train*.jsonl`, `val*.jsonl`.
- `final/{train,val,test}.jsonl` + `report.json` (train ~6,9 MB).
- `raw_scrapy/pages.jsonl`, `research_sources.jsonl`, `kb/*.json`.

**Reproducible:** descarga y extracción web/libros (mismas URLs y mismos scripts),
cálculos, KB, matriz de cobertura, evaluación determinista. **No reproducible
bit a bit:** generación sintética y multiturno (LLM, endpoints y prompts pueden
cambiar), traducción, y el estado exacto de `jobs.db` (guardar copia).

Copias: `salud_datos.py --base /Users/angelgonzalez/fase0 --copia --backups
/Users/angelgonzalez/fase0_backups` crea un `.tar.gz` con SHA-256 y rota copias.
Probado con un `fase0` mínimo en `/tmp`: `rc=0`, copia creada e informe sin
incidencias.

## 5. Recetas

### Reanudar una pasada larga

```bash
# Web: salta las URLs ya descargadas; un sitio concreto con --solo
$PY finetune/corpus/web_pipeline.py --work-dir /Users/angelgonzalez/fase0/web \
  --limite-por-sitio 50

# Libros: idempotente por etapa; --dry-run muestra el plan sin tocar disco
$PY finetune/corpus/libros_pipeline.py --work-dir /Users/angelgonzalez/fase0/libros \
  --hasta juez --dry-run

# YouTube: cada etapa reanuda desde sus manifests
$PY finetune/corpus/yt_pipeline.py --work-dir /Users/angelgonzalez/fase0/youtube \
  --hasta normalizar

# Traducción: reanuda desde el .progress
$PY finetune/corpus/translate_dataset.py --train corpus/train.jsonl \
  --val corpus/val.jsonl --out-train corpus/train_es.jsonl \
  --out-val corpus/val_es.jsonl --resume

# Juez y afirmaciones: reanudan por hash/procesados; no hay que borrar salidas
$PY finetune/corpus/juez.py --secciones /Users/angelgonzalez/fase0/libros/secciones \
  --out-dir /Users/angelgonzalez/fase0/libros/evidencias
```

### Lanzar una tanda de afirmaciones

```bash
mkdir -p /Users/angelgonzalez/fase0/afirmaciones
nohup $PY finetune/corpus/afirmaciones_es.py \
  --evidencias /Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl \
  --web-dir /Users/angelgonzalez/fase0/web \
  --out-dir /Users/angelgonzalez/fase0/afirmaciones \
  --limite 500 --workers 2 >> /Users/angelgonzalez/fase0/afirmaciones/run.log 2>&1 &
```

Antes de la tanda real, `--simulado --limite 2` debe devolver `rc=0` sin llamar al
modelo. La reanudación usa `procesados.jsonl`; no borrar ese fichero.

### Fusionar evidencias nuevas con copia previa

```bash
cd /Users/angelgonzalez/fase0/evidencias_web
cp -p evidencias.jsonl "evidencias.jsonl.bak-$(date +%Y%m%d-%H%M)"
$PY /Users/angelgonzalez/adivinacion-ia/finetune/corpus/juez.py \
  --secciones <nuevas_secciones> \
  --out-dir /Users/angelgonzalez/fase0/evidencias_web --workers 4
```

`juez.py` abre `juicios.jsonl` y `evidencias.jsonl` en modo append y salta los
hashes ya juzgados. Si se rejuzga una sección modificada, su hash cambia y se
añade; por eso conviene deduplicar después o revisar el informe.

### Regenerar la matriz de cobertura y el plan

```bash
$PY finetune/corpus/cobertura.py \
  --evidencias /Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl \
               /Users/angelgonzalez/fase0/libros/evidencias/evidencias.jsonl \
  --out-json /Users/angelgonzalez/fase0/cobertura_total.json \
  --out-md /Users/angelgonzalez/fase0/cobertura_total.md --calidad-min 3

$PY finetune/corpus/recuperacion_dirigida.py \
  --matriz /Users/angelgonzalez/fase0/cobertura_total.json \
  --out-plan /Users/angelgonzalez/fase0/plan_recuperacion.jsonl \
  --out-informe /Users/angelgonzalez/fase0/informe_recuperacion.md
```

`--dry-run` no escribe. Una celda «completa» exige el mínimo de fuentes del plan
de calidad; que haya evidencias sueltas no implica celda completa (por eso una
matriz con 31.459 evidencias puede seguir mostrando 0/7.455 completas).

### Regenerar trabajos sintéticos (con precaución)

```bash
cp -p /Users/angelgonzalez/adivinacion-ia/finetune/corpus/jobs.db \
      /Users/angelgonzalez/adivinacion-ia/finetune/corpus/jobs.db.bak-$(date +%Y%m%d-%H%M)
$PY finetune/corpus/generate_tasks.py --dry-run          # ver recuento
$PY finetune/corpus/generate_tasks.py --replace-pending  # borra pendientes viejos
$PY finetune/corpus/generate_synthetic.py \
  --endpoint http://10.0.0.3:8000/v1 --workers 4 --out corpus/synthetic
```

`--replace-pending` descarta los trabajos pendientes con los prompts antiguos.
Nunca lanzarlo sin copia de `jobs.db`.

### Evaluar un modelo

```bash
$PY finetune/corpus/evaluacion_casos.py --salida /tmp/eval_casos.jsonl
# respuestas.jsonl: una línea por caso, {"id":"eval-…","respuesta":"…"}
$PY finetune/corpus/evaluar_modelo.py --casos /tmp/eval_casos.jsonl \
  --respuestas respuestas.jsonl --salida /tmp/evaluacion_informe
# comparación opcional entre dos informes:
$PY finetune/corpus/evaluar_modelo.py --comparar A.json B.json
```

Sin `--permitir-faltantes` exige los 240 ids. `--juez-llm` añade una nota 1–5 y
usa caché reanudable; sin él, la evaluación es determinista.

### Preparar la revisión del 3 %

```bash
$PY finetune/corpus/muestras.py --accion muestrear --nivel todos \
  --base /Users/angelgonzalez/fase0 \
  --out-dir /Users/angelgonzalez/fase0/muestras

$PY finetune/corpus/prerevision.py \
  --muestras /Users/angelgonzalez/fase0/muestras/muestras.jsonl \
  --out-dir /Users/angelgonzalez/fase0/muestras \
  --base /Users/angelgonzalez/fase0

$PY finetune/corpus/revisor_local.py \
  --muestras /Users/angelgonzalez/fase0/muestras/muestras.jsonl \
  --prerevision /Users/angelgonzalez/fase0/muestras/prerevision.jsonl \
  --out /Users/angelgonzalez/fase0/muestras/revisor.html \
  --base /Users/angelgonzalez/fase0
# abrir revisor.html, revisar y exportar muestras_revisadas.jsonl
$PY finetune/corpus/muestras.py --accion oro --nivel todos \
  --base /Users/angelgonzalez/fase0 \
  --revisadas /Users/angelgonzalez/fase0/muestras/muestras_revisadas.jsonl \
  --umbral 0.90
```

Probado con salida en `/tmp`: 3.160 muestras, 491 con banderas y `revisor.html`
de 6,1 MB. `--accion oro` produce `oro.jsonl`, `rechazados.jsonl` e
`oro_informe.md`; la tasa de acierto penaliza los «dudoso». La muestra T93 se
regeneró en `muestras_v2/` con las mismas tres herramientas (6.982 fichas).

### Cerrar la fase 0 (T85/T90)

```bash
$PY finetune/corpus/cierre_recopilacion.py --base-dir /Users/angelgonzalez/fase0 --dry-run
$PY finetune/corpus/cierre_recopilacion.py --base-dir /Users/angelgonzalez/fase0 --todo
```

`--dry-run` muestra los 7 pasos sin tocar nada; `--todo` los ejecuta en orden
(dedupe del consenso, limpieza de libros, filtro de atribución, consenso con
exclusiones, KB v2, cobertura v3, informe) dejando copias `pre-cierre-ts`,
`pre-filtro-atrib-ts` y `pre-exclusion-ts`. `--paso {1..7}` fuerza uno solo y
`--solo-verificar` (solo con paso 2 o 3) re-verifica sin reaplicar. El paso 3
(filtro de atribución, T88) es decisión humana: ver `docs/ATRIBUCION_ENTIDADES.md`
antes de aplicarlo a producción.

### Generar la fase 1 con Mercury (T95/T100)

```bash
INCEPTION_API_KEY=… $PY finetune/corpus/ejecutor_fase1.py --backend mercury \
  --db /tmp/fase1_mercury_full.db --workers 3 --formato sharegpt \
  --out-dir /Users/angelgonzalez/fase0/fase1_mercury
```

La clave solo va en el entorno, nunca en el repo. Parada de seguridad automática
si los errores superan el 20 % en la ventana (rc=3). Tras la pasada:
`reverificar_fase1.py` con el verificador corregido y `validate_synthetic.py
--min-chars 400` solo sobre `aceptadas.jsonl`; después `merge_final.py` y
`preparar_entrenamiento.py`. No lanzar dos pasadas sobre el mismo backend a la
vez (ver discrepancia 13).

### Línea base de modelos (T99)

```bash
$PY finetune/corpus/linea_base.py --modelo flash-next --paralelo 2
```

Pasa los 240 casos de evaluación (semilla reservada 560056) por el modelo y
puntúa con `evaluar_modelo.py`; salida en `fase0/linea_base/<modelo>/`. Para
Mercury: `--modelo mercury-3` con `INCEPTION_API_KEY` en el entorno y
`--paralelo 1`. Resultado de referencia: 179/240 (74,6 %) bruto, ≈86,3 %
descontando falsos positivos del verificador.

## 6. Precauciones y trampas

- **Baraja española ≠ naipes franceses.** Son sistemas distintos; no mezclar
  entidades, significados ni mazos en la KB (`cartas.py --mazo`).
- **No reanudar** los generadores antiguos PID 66101 (nodo1) y 66396 (nodo2):
  usan prompts viejos sin tildes. Matar o dejar suspendidos; regenerar con
  `generate_tasks.py --replace-pending`.
- **Copia de `jobs.db`** antes de cualquier regeneración o de ejecutar
  `--replace-pending`. Tras la regeneración de T95/T100 hay 12.536 pendientes y
  estado no reproducible; la pasada de Mercury en curso usa una copia en
  `/tmp/fase1_mercury_full.db`.
- **Nodos compartidos.** Nodo1 `10.0.0.3:8000` y nodo2 `10.0.0.4:8000` se saturan
  con varias IAs. Comprobar disponibilidad y no lanzar más workers de los
  acordados; `llm_client.py` hace round-robin.
- **Semillas de evaluación reservadas:** 560056, 560057 y 560058. No usarlas para
  muestrear ni generar datos de entrenamiento.
- **El 55 % de las muestras de libros no está en español.** Para revisar hay que
  leer el original o usar `cita_original`; no aplicar filtros de idioma a ciegas.
- **Rate limits y robots.txt:** ≤ 1 petición/s por dominio, respetar `robots.txt`,
  no saltar bloqueos (astro.com, nymero.org, Reddit). `libros_fetch.py` se detiene
  con código 3 si archive.org devuelve 429 repetidos (parada limpia, reanudable).
- **Lista blanca de dominios:** la configuración web y `license_filter.py` limitan
  qué se descarga y qué licencia se acepta. No añadir dominios sin revisar.
- **`--license-filter` por defecto es `off`** en `build_dataset.py`: la revisión
  legal es posterior y cada documento debe conservar su procedencia.
- **Rutas absolutas:** los valores por defecto apuntan a
  `/Users/angelgonzalez/fase0` y al venv de esa ruta. En otro equipo hay que
  pasarlas explícitamente.
- **Salidas en append:** `juez.py`, `afirmaciones_es.py` y `multiturno.py`
  reanudan sin borrar; si se quiere empezar de cero, usar un `--out-dir` nuevo,
  no truncar a mano.
- **Cuota Mercury 3:** 100 M de tokens gratis. T69 gastó ~28 M y la pasada
  parcial de T94 ~3,94 M; la pasada completa de T100 prevista consume ~10,5 M de
  entrada y hasta ~16 M de salida. Antes de otra pasada grande, revisar el saldo.
- **Términos de Inception:** las salidas permiten entrenar. El opt-out de
  entrenamiento («Improve the model for everyone») está **desactivado** — decisión
  confirmada por el usuario el 2026-10-21; no cambiarlo sin consultarlo.
- **Un solo inquilino por backend:** no relanzar la pasada rápida de T94 mientras
  T100 ocupe Mercury; relanzarla con `--workers 1` al terminar. `sinastria` quedó
  fuera de la pasada de T100 (65 % truncadas en la muestra; propuesta futura:
  subir su piso en `RECOMENDACION_MAX_TOKENS` de 4096 a 6144 y validar con una
  muestra antes de relanzar).

## 7. Verificación y discrepancias

Comprobado el 2026-10-20 y ampliado el 2026-10-21:

- `--help` devuelve 0 en todos los módulos con argparse, salvo
  `libros_extraer.py` (rc=1; interpreta `--help` como ruta). Sin argparse y sin
  ayuda: `diagnostico_tarot_libros.py`, `libros_fuentes.py`, `libros_limpiar.py`,
  `libros_segmentar.py`, `llm_client.py`, `web_fetch.py`.
- `libros_pipeline.py --dry-run --work-dir /tmp/t60_libros` → rc=0 y plan hasta
  `juez`.
- `generate_tasks.py --dry-run` → rc=0, 10.636 trabajos.
- `cobertura.py --dry-run` y `recuperacion_dirigida.py --dry-run` → rc=0.
- `afirmaciones_es.py --simulado --limite 2` y `lecturas_extraer.py --simulado
  --limite 2` → rc=0.
- `muestras.py`, `prerevision.py` y `revisor_local.py` con salida en `/tmp` →
  rc=0.
- `evaluacion_casos.py --salida /tmp/t60_eval.jsonl` → rc=0, 240 líneas.
- `salud_datos.py --copia` con un `fase0` mínimo → rc=0, copia y SHA-256.
- `--help` → rc=0 en `ejecutor_fase1.py`, `fase1_piloto.py`, `ensayo_extremo.py`,
  `evidencias_incremental.py`, `clasicos_pd_a_evidencias.py`,
  `limpiar_evidencias_libros.py`, `recuperacion_descarga.py`, `kb_v2.py`,
  `consenso_kb.py` y `afirmaciones_libros.py`.
- `--help` → rc=0 verificado el 2026-10-21 (T104) en los 19 módulos posteriores a
  T77: `cierre_recopilacion`, `aplicar_limpieza_libros`, `filtro_atribucion`,
  `cobertura_v3`, `inventario_legal`, `kb_v2`, `linea_base`,
  `afirmaciones_rapido`, `descubrir_fuentes`, `recuperacion_descarga`,
  `ejecutor_fase1`, `reverificar_fase1`, `piloto_mercury`, `comparar_consenso`,
  `evaluar_modelo`, `ensayo_extremo`, `muestras`, `prerevision` y
  `revisor_local`.
- `ejecutor_fase1.py --db …/jobs.db --dry-run` → rc=0: 10.270 pendientes y
  121,2 h estimadas con 4 workers a 169,9 s/lectura. Con `--simulado` completó
  10.226/10.226 aceptadas (el resto eran trabajos no reclamables).
- `ensayo_extremo.py --n 200` (simulado) → 200/200 aceptadas, pero
  `validate_synthetic` conservó 68 y `merge_final` dejó 58/6/15; el valor está
  en el informe de desajustes, no en el «éxito» de la generación.

Discrepancias encontradas:

1. **Actualizado en T104:** `afirmaciones_rapido.py` ya **sí** está integrado en
   `main` (merges `7d70cdd` de T69 y `0a2d242` de T94); la advertencia anterior de
   la revisión T77 («solo en el worktree») quedó obsoleta. Los demás módulos de
   las tablas 2.2–2.5 siguen en `main` (merges de T38/T47).
2. **`web_pipeline.py` exige `--work-dir`.** Sin él termina con rc=2; los ejemplos
   que lo omiten están incompletos.
3. **`build_dataset.py --dry-run` falla con rc=1** si no existe `corpus/raw`
   (valor por defecto). Hay que pasar `--raw` a un directorio real; el
   `--dry-run` no evita la comprobación de existencia.
4. **`GUIA_REENTRENAMIENTO.md` está desactualizada:** describe `build_dataset.py`
   como un script «a escribir», usa `pip` (aquí se usa `uv`) y no menciona la
   tubería actual (juez, afirmaciones, cobertura, `fase1_prompts`, `merge_final`).
   Los comandos `soup` no se verificaron en esta pista.
5. **Recuento de `jobs.db`:** desactualizado tras T95/T100. La foto vieja hablaba
   de 10.636 trabajos; `generate_tasks.py --replace-pending` regeneró la matriz
   (D6: 0 pendientes sin tildes) y ahora hay 12.536 pendientes, de los que la
   pasada de Mercury en curso procesa 11.936 (excluidas 600 de `sinastria`).
6. **`merge_final.py` no tiene `--dry-run`.** No se ejecutó para no sobrescribir
   `corpus/final/`; su CLI sí se comprobó con `--help`.
7. **Los ejemplos multi-turno y de evaluación no están versionados:** viven en
   `/tmp/t45/ejemplos.jsonl` y `/tmp/eval_casos.jsonl`. Si se limpia `/tmp`, hay
   que regenerarlos (`multiturno.py --n 5`, `evaluacion_casos.py`) antes de
   citarlos.
8. **`comparar_backends.py` no tiene argparse.** Exige `INCEPTION_API_KEY` en el
   entorno; sin ella sale con rc=1 y el mensaje «[comparativa] Falta
   'INCEPTION_API_KEY' en el entorno.». No se pudo verificar `--help`: con una
   clave ficticia el proceso se quedó bloqueado más de 120 s (import o trabajo
   real). La clave no se documenta ni se escribe en el repo.
9. **El consenso está CERRADO** (T85/T90): 3.688 celdas en `consenso.jsonl` y
   `kb_v2/tarot.json` ya existe. Lo único que crece en vivo es
   `fase0/fase1_mercury/` mientras corre T100; las cifras de ese directorio son
   una instantánea de 2026-10-21, no un total.
10. **`fase1_piloto.py` no cubre baraja española:** sus familias son tarot
    (`tarot_1/2/3`, `tarot_pregunta`), astro (`astro_natal`, `sinastria`),
    numerología, multiturno y ética. La familia de baraja llega con T72.
11. **Los ejemplos de `fase1_piloto` con `max_tokens 2048`** hacen que
    `cruz_celta` y `lectura_completa` fallen por truncado; el ejecutor sube el
    piso a 6144 para esas familias.
12. **Recuento de celdas completas distinto según el informe:**
    `INVENTARIO_LEGAL.md` habla de 310 celdas completas (310→297 al excluir
    riesgo alto) y `COBERTURA_V3.md` da 304. Son matrices generadas en momentos
    distintos (el inventario usó la cobertura previa a la pasada definitiva de
    cobertura_v3). Citando cada cifra con su fuente no hay contradicción.
13. **`afirmaciones_rapido` (T94) en parada de seguridad:** el 2026-10-21 a las
    17:35 se detuvo al 2.214/10.512 evidencias por >20 % de errores, justo al
    coincidir en el tiempo con el arranque de T100 sobre el mismo backend. Es
    reanudable con `--workers 1` cuando T100 termine; los procesados quedan en
    `fase0/afirmaciones_rapido/`.
14. **`sinastria` no lanzada en la pasada T100:** en la muestra de 300, el 65 %
    de las sinastrías salieron truncadas con el piso de 4096 tokens, así que sus
    600 tareas se excluyeron de la pasada completa. Quedan pendientes hasta
    validar la subida del piso a 6144.
