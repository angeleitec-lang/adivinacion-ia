#!/usr/bin/env python3
"""Ensayo extremo de la fase 1 (T70): punta a punta, simulado, sin red.

Ejecuta la cadena completa —ejecutor_fase1 (lector simulado) → validate_synthetic →
build_dataset → merge_final → preparar_entrenamiento— sobre una COPIA de jobs.db en
un directorio temporal, con N tareas representativas (round-robin por bloque, todos
los bloques incluidos multiturno y etica), y produce un informe con:

- cada etapa (entrada → salida con recuentos),
- los formatos reales intercambiados entre etapas,
- los DESAJUSTES detectados (con reproducción mínima y parche propuesto),
- las filas perdidas y por qué,
- el semáforo final de preparar_entrenamiento.

Nunca escribe fuera del directorio temporal salvo el informe pedido. No toca la BD
real (solo la copia en modo lectura) ni corpus/final.

Uso:
    python ensayo_extremo.py --n 200 --informe ../../docs/ENSAYO_FASE1.md
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_dataset  # noqa: E402
import ejecutor_fase1 as ef  # noqa: E402
import merge_final  # noqa: E402
import preparar_entrenamiento as pe  # noqa: E402
import validate_synthetic  # noqa: E402
from llm_client import LLMClient  # noqa: E402

def _db_por_defecto():
    """jobs.db esta en .gitignore: en un worktree vive solo en el repo principal."""
    candidatos = [
        Path(__file__).resolve().parent / "jobs.db",
        Path("/Users/angelgonzalez/adivinacion-ia/finetune/corpus/jobs.db"),
    ]
    for c in candidatos:
        if c.exists():
            return c
    return candidatos[0]


DB_REAL = _db_por_defecto()
MIN_CHARS_DEFAULT_ENSAYO = 60


def seleccionar_tareas(db_path, n_total=200):
    """Deja en la copia de la BD solo n_total pendientes, round-robin por bloque.

    Las pendientes no seleccionadas pasan a status='descartada' en la COPIA, de modo
    que el ejecutor (que toma pending ORDER BY id LIMIT n) procese exactamente la
    muestra representativa de todos los bloques.

    Devuelve {bloque: n_seleccionada}.
    """
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    por_bloque = defaultdict(list)
    for r in con.execute(
        "SELECT id, bloque FROM jobs WHERE status='pending' ORDER BY bloque, id"
    ):
        por_bloque[r["bloque"]].append(r["id"])

    bloques = sorted(por_bloque)
    seleccion = []
    i = 0
    while len(seleccion) < n_total and any(por_bloque[b] for b in bloques):
        b = bloques[i % len(bloques)]
        if por_bloque[b]:
            seleccion.append(por_bloque[b].pop(0))
        i += 1

    if seleccion:
        marks = ",".join("?" * len(seleccion))
        con.execute(
            f"UPDATE jobs SET status='descartada' "
            f"WHERE status='pending' AND id NOT IN ({marks})",
            tuple(seleccion),
        )
    else:
        con.execute("UPDATE jobs SET status='descartada' WHERE status='pending'")
    con.commit()
    con.close()
    return seleccion


def _seleccion_por_bloque(db_path, seleccion):
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cuenta = Counter()
    for r_id in seleccion:
        row = con.execute("SELECT bloque FROM jobs WHERE id=?", (r_id,)).fetchone()
        if row:
            cuenta[row["bloque"]] += 1
    con.close()
    return dict(sorted(cuenta.items()))


def adaptar_a_sharegpt(fila):
    """Adaptador DESAJUSTE D1: registro del ejecutor → fila ShareGPT.

    En T75 la lógica canónica se movió a ``ejecutor_fase1.a_sharegpt``: el
    ejecutor ya puede emitir ShareGPT con ``--formato sharegpt`` (con
    ``bloque``, ``id``, ``calculos`` y texto NFC). Esta función queda como
    delegación delgada por compatibilidad con llamadores y tests del ensayo T70.
    """
    return ef.a_sharegpt(fila)


def _texto_gpt(fila):
    """Texto de la última respuesta gpt (ShareGPT o registro plano del ejecutor)."""
    if fila.get("respuesta") is not None:
        return fila.get("respuesta") or ""
    for c in reversed(fila.get("conversations") or []):
        if c.get("from") == "gpt":
            return c.get("value") or ""
    return ""


def escribir_validacion(adaptadas, dir_validacion):
    """Escribe un fichero por bloque (validate_synthetic deriva el bloque del nombre).

    Necesario para que los skips específicos de ``etica`` (eco_prompt, ia_meta) se
    apliquen solo a esas filas. Devuelve {bloque: n_filas}.
    """
    dir_validacion = Path(dir_validacion)
    dir_validacion.mkdir(parents=True, exist_ok=True)
    por_bloque = defaultdict(list)
    for fila in adaptadas:
        por_bloque[str(fila.get("bloque", "sin_bloque"))].append(fila)
    cuenta = {}
    for bloque, filas in sorted(por_bloque.items()):
        with (dir_validacion / f"{bloque}.jsonl").open("w", encoding="utf-8") as fh:
            for fila in filas:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        cuenta[bloque] = len(filas)
    return cuenta


def generar_corpus_real(dir_raw, n_docs=6):
    """Mini-corpus markdown sintético que alimenta build_dataset como datos 'reales'.

    Textos expositivos con términos fuertes del dominio (tarot, astrología,
    numerología) para pasar los filtros de relevancia sin tocar corpus/raw real.
    """
    dir_raw = Path(dir_raw)
    dir_raw.mkdir(parents=True, exist_ok=True)
    docs = [
        (
            "tarot_arcanos_mayores.md",
            """# Los arcanos mayores del tarot

## El Loco y el comienzo del camino
El arcano del Loco representa en el tarot el inicio espontáneo del viaje
interior. En la lectura de cartas simboliza la confianza previa a la experiencia:
el consultante pisa terreno nuevo con el corazón abierto. Los arcanos mayores
describen un recorrido completo del alma, desde la inocencia hasta el mundo.

## La Emperatriz y la creatividad fértil
La Emperatriz gobierna la fertilidad, el arte y el cuidado en el tarot. Cuando
aparece en una tirada señala un momento de gestación creativa: proyectos que
nacen del deseo y se sostienen con paciencia. Su número, el tres, habla de
triángulos estables y de expresión compartida.

## El Mago y la voluntad dirigida
El Mago canaliza los cuatro palos sobre la mesa: voluntad, emoción, acción y
tierra. En cartomancia este arcano mayor indica que los recursos ya están
dispuestos y solo falta la decisión de usarlos. Su clave es la intención clara.
""",
        ),
        (
            "astrologia_carta_natal.md",
            """# La carta natal en astrología occidental

## Signo solar, Luna y ascendente
La carta natal es una fotografía del cielo en el instante del nacimiento. El
signo solar describe la identidad consciente, la Luna el mundo emocional y el
ascendente la máscara con la que salimos al mundo. Interpretar la carta exige
conocer hora y lugar exactos, porque el ascendente cambia en minutos.

## Casas y aspectos
Las doce casas de la astrología reparten la experiencia en ámbitos: pareja,
trabajo, hogar, vocación. Los aspectos —conjunción, cuadratura, trino— miden el
ángulo entre planetas y describen talento o tensión. Un trino de Júpiter al
Sol, por ejemplo, se lee como expansión y optimismo templado.

## Tránsitos y ciclos
Los tránsitos son los movimientos actuales de los planetas sobre la carta
natal. Saturno, lento y exigente, marca madurez y responsabilidad en sus
ciclos de casi treinta años. Leer tránsitos es situar el presente dentro de
un ritmo, no predecir hechos concretos.
""",
        ),
        (
            "numerologia_camino_de_vida.md",
            """# Numerología pitagórica aplicada

## El camino de vida
El camino de vida se obtiene sumando las cifras de la fecha de nacimiento hasta
reducirlas a un dígito, salvo los números maestros once, veintidós y
treinta y tres. Describe la lección central de la existencia: el uno inicia,
el dos coopera, el tres comunica. Es el número más consultado de la
numerología práctica.

## La expresión del nombre
La numerología también estudia el nombre propio: cada letra vibra con un valor
del uno al nueve y la suma da el número de expresión, que habla del talento
visible. Comparar expresión y camino de vida revela si la vocación coincide
con la misión personal.

## Ciclos personales
El año personal se calcula sumando día y mes de nacimiento al año corriente.
Cada ciclo de nueve años repite una escalera de aprendizajes: sembrar,
pulir, construir, ordenar, recoger, soltar, sembrar de nuevo, compartir y
cerrar. Conocer el ciclo ayuda a elegir el momento de cada decisión.
""",
        ),
        (
            "tarot_tiradas.md",
            """# Tiradas clásicas de tarot

## La cruz celta
La cruz celta es la tirada larga por excelencia: diez cartas que ordenan el
presente, el desafío, la corona, la raíz, el pasado cercano y el futuro, más
un eje final de síntesis. Exige memoria de la posición: la misma carta cambia
de significado según la casa que ocupa en el tapete.

## Tirada de tres cartas
Pasado, presente y consejo: la tirada breve más usada en cartomancia. Su
virtud es la claridad; su riesgo, la tentación de leer cada carta aislada.
El hilo entre las tres cartas importa más que cada carta por separado.

## Carta única del día
Una sola carta, leída como tema del día. Es un ejercicio de atención: obliga
a condensar el simbolismo del arcano en una intención concreta y útil para
la jornada, sin prometer lo que el tarot no puede prometer.
""",
        ),
        (
            "astrologia_sinastria.md",
            """# Sinastria: compatibilidad entre cartas

## Comparación de dos cielos
La sinastria superpone las cartas natales de dos personas y estudia los
aspectos cruzados: la Luna de uno sobre el Venus del otro, por ejemplo, se
lee como ternura fácil. No es un veredicto de pareja, sino un mapa de
facilidades y fricciones entre dos modos de querer.

## Nodos y vínculos
Los astrólogos asignan a los nodos lunares un peso especial en los vínculos:
el nodo norte de uno tocado por planetas del otro sugiere crecimiento
conjunto. Son lecturas simbólicas que ayudan a nombrar lo que se siente, no
a decidir por nadie.

## Ritmos distintos
Saturno y Neptuno avanzan a velocidades distintas y tocan a generaciones
enteras. En sinastria, la diferencia de edad se nota en tránsitos lentos:
lo que para uno es crisis, para el otro es fondo de paisaje. Tenerlo
presente evita leer como personal lo que es generacional.
""",
        ),
        (
            "numerologia_biorritmos.md",
            """# Biorritmos: los ciclos del cuerpo y la mente

## Los tres ciclos clásicos
Los biorritmos proponen tres senoides nacidas del día de nacimiento: física
de veintitrés días, emocional de veintiocho e intelectual de treinta y
tres. Cada curva alterna días altos de rendimiento y días bajos de
descanso, con días críticos en los cruces por cero.

## Lectura prudente
Los biorritmos no son predicción: son una herramienta de autoobservación.
Quien los registra comprueba si su energía sigue las curvas y ajusta el
esfuerzo. La numerología de los ciclos ofrece un vocabulario para respetar
los bajones sin dramatismos.

## Combinar con el año personal
Sumar el ciclo personal de la numerología pitagórica a los biorritmos da una
visión en dos escalas: el año que toca y el día que se tiene. La
concordancia entre ambas se lee como momento favorable para emprender,
nunca como garantía.
""",
        ),
    ][:n_docs]
    for nombre, texto in docs:
        (dir_raw / nombre).write_text(texto, encoding="utf-8")
    return [nombre for nombre, _ in docs]


def _leer_jsonl(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    filas = []
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def _contar_nfd(filas):
    """Filas cuyo texto viene en NFD (descompuesto) y necesita NFC.

    Cubre el registro plano del ejecutor (T70) y las filas ShareGPT con
    ``conversations`` que el ejecutor ya normaliza a NFC en T75.
    """
    n = 0
    for fila in filas:
        textos = [fila.get(clave) or "" for clave in
                  ("prompt_system", "prompt_user", "respuesta")]
        textos += [c.get("value") or "" for c in fila.get("conversations") or []]
        if any(unicodedata.normalize("NFC", t) != t for t in textos):
            n += 1
    return n


def ejecutar_ensayo(base_dir, db_src=None, n_tareas=200, lector=None,
                   min_chars=MIN_CHARS_DEFAULT_ENSAYO, semilla=42):
    """Corre la cadena completa en base_dir y devuelve el resumen del ensayo."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    db_src = Path(db_src) if db_src else DB_REAL
    fallos = []

    # --- Etapa 0: copia de la BD y selección representativa -------------------
    copia_db = base_dir / "jobs_ensayo.db"
    shutil.copy2(db_src, copia_db)
    seleccion = seleccionar_tareas(copia_db, n_tareas)
    seleccion_bloques = _seleccion_por_bloque(copia_db, seleccion)

    # --- Etapa 1: ejecutor en modo simulado -----------------------------------
    cliente = LLMClient(simulado=lector or ef.simulacion_fase1)
    kb = ef.cargar_kb()
    resumen_ejec = ef.ejecutar(
        copia_db, cliente, kb,
        workers=2, limite=n_tareas, out_dir=base_dir / "ejecutor",
        formato="sharegpt",
    )
    aceptadas = _leer_jsonl(base_dir / "ejecutor" / "aceptadas.jsonl")
    rechazadas = _leer_jsonl(base_dir / "ejecutor" / "rechazadas.jsonl")
    motivos_rechazo = Counter()
    for r in rechazadas:
        for m in r.get("motivos") or ["sin_motivo"]:
            motivos_rechazo[m] += 1
    if not aceptadas:
        fallos.append(
            "etapa ejecutor: 0 registros aceptados "
            f"(rechazadas={len(rechazadas)}, motivos={dict(motivos_rechazo)})"
        )

    # --- Etapa 2: adaptación a ShareGPT (T75: identidad, ya viene en ShareGPT) --
    adaptadas = list(aceptadas)
    n_nfd = _contar_nfd(adaptadas)
    cuenta_validacion = escribir_validacion(adaptadas, base_dir / "validacion")

    # --- Etapa 3: validate_synthetic ------------------------------------------
    synth_clean = base_dir / "synth_clean.jsonl"
    synth_meta = base_dir / "synth_clean.meta.jsonl"
    val_report = base_dir / "synth_report.json"
    rc_val = validate_synthetic.main([
        "--dir", str(base_dir / "validacion"),
        "--out", str(synth_clean),
        "--meta-out", str(synth_meta),
        "--report", str(val_report),
        "--min-chars", str(min_chars),
    ])
    if rc_val != 0:
        fallos.append("etapa validate_synthetic: sin ficheros de entrada o error")
    val_informe = json.loads(val_report.read_text(encoding="utf-8")) \
        if val_report.exists() else {}
    if val_informe.get("kept", 0) == 0:
        fallos.append(
            "etapa validate_synthetic: 0 filas limpias "
            f"(motivos={val_informe.get('reasons')})"
        )

    # --- Etapa 4: build_dataset con mini-corpus 'real' -------------------------
    dir_real = base_dir / "real"
    generar_corpus_real(base_dir / "real_raw")
    rc_bd = build_dataset.main([
        "--raw", str(base_dir / "real_raw"),
        "--out", str(dir_real),
        "--seed", str(semilla),
        "--min-domain-terms", "2",
        "--manifest", str(base_dir / "manifest_inexistente.json"),
    ])
    real_train = _leer_jsonl(dir_real / "train.jsonl")
    real_val = _leer_jsonl(dir_real / "val.jsonl")
    if rc_bd != 0 or not (real_train or real_val):
        fallos.append("etapa build_dataset: no produjo pares reales de entrada")

    # --- Etapa 5: merge_final --------------------------------------------------
    dir_fusion = base_dir / "dataset_ensayo"
    rc_mf = merge_final.main([
        "--real-train", str(dir_real / "train.jsonl"),
        "--real-val", str(dir_real / "val.jsonl"),
        "--synth", str(synth_clean),
        "--synth-meta", str(synth_meta),
        "--out-dir", str(dir_fusion),
        "--seed", str(semilla),
    ])
    fusion_report = json.loads((dir_fusion / "report.json").read_text(encoding="utf-8")) \
        if (dir_fusion / "report.json").exists() else {}
    fusion_counts = {
        "train": len(_leer_jsonl(dir_fusion / "train.jsonl")),
        "val": len(_leer_jsonl(dir_fusion / "val.jsonl")),
        "test": len(_leer_jsonl(dir_fusion / "test.jsonl")),
    }
    if rc_mf != 0:
        fallos.append("etapa merge_final: error al fusionar")

    # --- Etapa 6: preparar_entrenamiento ---------------------------------------
    preparado = pe.preparar(dir_fusion, base_dir / "preparado", formato="chatml")
    if preparado["semaforo"] == "rojo":
        fallos.append(
            f"etapa preparar_entrenamiento: semáforo ROJO ({preparado['errores']})"
        )

    # --- DESAJUSTES ------------------------------------------------------------
    desajustes = construir_desajustes(
        aceptadas=aceptadas, rechazadas=rechazadas, adaptadas=adaptadas,
        n_nfd=n_nfd, val_informe=val_informe, fusion_report=fusion_report,
        min_chars=min_chars,
    )

    return {
        "base_dir": str(base_dir),
        "seleccion": {"total": len(seleccion), "por_bloque": seleccion_bloques},
        "ejecutor": {
            "resumen": {k: v for k, v in resumen_ejec.items() if k != "copia"},
            "aceptadas": len(aceptadas),
            "rechazadas": len(rechazadas),
            "motivos_rechazo": dict(motivos_rechazo),
        },
        "adaptacion": {
            "entradas": len(aceptadas),
            "salidas": len(adaptadas),
            "claves_entrada": sorted(aceptadas[0].keys()) if aceptadas else [],
            "claves_salida": sorted(adaptadas[0].keys()) if adaptadas else [],
            "filas_nfd": n_nfd,
        },
        "validacion": val_informe,
        "real": {"train": len(real_train), "val": len(real_val)},
        "fusion": {"report": fusion_report, **fusion_counts},
        "preparacion": {
            "semaforo": preparado["semaforo"],
            "errores": preparado["errores"],
            "avisos": preparado["avisos"],
            "estadisticas": preparado["estadisticas"],
            "invalidas": {s: len(v) for s, v in preparado["invalidas"].items()},
        },
        "desajustes": desajustes,
        "fallos": fallos,
    }


def construir_desajustes(aceptadas, rechazadas, adaptadas, n_nfd, val_informe,
                        fusion_report, min_chars):
    """Lista de desajustes entre etapas con reproducción mínima y parche propuesto."""
    des = []

    if aceptadas:
        ejemplo = aceptadas[0]
        des.append({
            "id": "D1",
            "titulo": "La salida del ejecutor no era ShareGPT (CORREGIDO EN T75)",
            "descripcion": (
                "T70: ejecutor_fase1 escribia registros planos con prompt_system/"
                "prompt_user/respuesta y validate_synthetic no los entendia. "
                "T75: el ejecutor acepta --formato sharegpt y emite "
                "conversations [system,human,gpt] con 'bloque', 'id' y 'calculos' "
                "en NFC. Este ensayo usa ese formato; adaptar_a_sharegpt queda "
                "como delegacion delgada hacia ejecutor_fase1.a_sharegpt."
            ),
            "reproduccion": (
                "T70: validate_synthetic.human_of(registro_plano) -> ''. "
                "T75: a_sharegpt(registro)['conversations'] tiene roles "
                "system/human/gpt y el validador lo consume directamente."
            ),
            "parche": (
                "Aplicado en ejecutor_fase1.a_sharegpt + --formato sharegpt "
                "(commit 8d43541)."
            ),
            "ejemplo_claves": sorted(ejemplo.keys()),
        })

    cortas_400 = sum(1 for f in aceptadas if len(_texto_gpt(f)) < 400)
    des.append({
        "id": "D2",
        "titulo": "min-chars=400 de validate_synthetic vs lector simulado breve",
        "descripcion": (
            f"El lector simulado genera lecturas de una frase por carta; "
            f"{cortas_400} de {len(aceptadas)} respuestas aceptadas miden menos "
            "de 400 caracteres y caerían como 'corto' con el umbral por defecto."
        ),
        "reproduccion": (
            "validate(fila, Namespace(min_chars=400, ...)) -> (False, 'corto') "
            "para respuestas del simulador."
        ),
        "parche": (
            f"En el ensayo se pasa --min-chars {min_chars}. Para producción: "
            "subir la verbosidad del lector o bajar el umbral explícitamente en "
            "la orden de validación (no cambiar el default ajeno)."
        ),
    })

    sin_tildes = (val_informe.get("reasons") or {}).get("prompt_sin_tildes", 0)
    if sin_tildes:
        des.append({
            "id": "D6",
            "titulo": "Prompts pendientes en jobs.db sin tildes",
            "descripcion": (
                f"validate_synthetic rechazo {sin_tildes} filas por "
                "'prompt_sin_tildes': los jobs pendientes de la BD se generaron "
                "con prompts viejos sin acentuar (PIPELINE: no reanudar "
                "generadores viejos). El ejecutor no lo detecta porque su "
                "verificador no revisa tildes."
            ),
            "reproduccion": (
                "validate_synthetic.validate(fila, args, bloque) -> "
                "(False, 'prompt_sin_tildes') para esas filas."
            ),
            "parche": (
                "Regenerar las tareas pendientes con generate_tasks actualizado "
                "(--replace-pending) antes de la producción real; el ensayo solo "
                "lo documenta."
            ),
        })

    sin_datos = (val_informe.get("reasons") or {}).get("sin_datos_del_prompt", 0)
    per_block = val_informe.get("per_block") or {}
    caida_total = sorted(
        b for b, s in per_block.items()
        if s.get("total", 0) > 0 and s.get("bad", 0) == s.get("total", 0)
    )
    des.append({
        "id": "D7",
        "titulo": "Grounding del validador vs calculos del ejecutor "
                  "(CORREGIDO EN T75)",
        "descripcion": (
            "T70: validate_synthetic extraia signos y numeros del TEXTO del "
            "prompt, un conjunto distinto del que comprueba "
            "fase1_prompts.verificar_lectura (usa 'calculos'); los bloques "
            "astrales caian casi al 100%. T75: grounding() usa "
            "signos_de_calculos/numeros_de_calculos cuando la fila trae "
            "'calculos' (commits c46d98f y 31eb144; el Ascendente se lee "
            "tambien de la clave 'ascendente' de la carta) y el lector "
            "simulado menciona los ejes Sol/Luna/Ascendente. Residual: "
            f"{sin_datos} filas 'sin_datos_del_prompt'"
            + (f"; caida total residual en {caida_total}" if caida_total else "")
            + "."
        ),
        "reproduccion": (
            "T70: grounding(prompt_astro, lectura_breve) -> False. T75: "
            "grounding(prompt, ans, calculos=CALCULOS_ASTRO) -> True si ans "
            "menciona 2/3 de los signos de los calculos."
        ),
        "parche": (
            "Aplicado en validate_synthetic.grounding con calculos de la fila "
            "(fuente canonica identica a verificar_lectura) + ejes astrales en "
            "el lector simulado; tests TestGroundingConCalculos."
        ),
    })

    junk_por_bloque = Counter()
    for fila in adaptadas:
        if merge_final.is_junk_pair(fila):
            junk_por_bloque[str(fila.get("bloque"))] += 1
    des.append({
        "id": "D3",
        "titulo": "Filtro de términos de dominio de merge_final vs filas de "
                  "etica (CORREGIDO EN T75)",
        "descripcion": (
            "T70: merge_final descartaba como junk las filas con domain_hits < 2; "
            "las de etica hablan de límites y contención, no de arcanos ni "
            "signos, y podian perderse pese a pasar validate_synthetic. T75: "
            "is_junk_pair exime las filas con 'bloque'=='etica'. Residual en "
            f"este ensayo: {dict(junk_por_bloque) if junk_por_bloque else '0 filas junk'}."
        ),
        "reproduccion": (
            "merge_final.is_junk_pair({'bloque': 'etica', 'conversations': "
            "[pobres en terminos de dominio]}) -> False (antes True)."
        ),
        "parche": (
            "Aplicado en merge_final.is_junk_pair: min_terms=0 para "
            "bloque=='etica' (commit fa43684); test TestExencionEtica."
        ),
        "bloques_afectados": dict(junk_por_bloque),
    })

    des.append({
        "id": "D4",
        "titulo": "Normalización unicode (NFC/NFD) entre etapas",
        "descripcion": (
            f"{n_nfd} filas del ejecutor traen texto en NFD (descompuesto). "
            "preparar_entrenamiento normaliza NFC internamente, pero validate y "
            "merge comparan con su propia normalización: las comparaciones de "
            "duplicados y grounding pueden fallar según la forma normal."
        ),
        "reproduccion": (
            "unicodedata.normalize('NFC', texto) != texto en las filas NFD."
        ),
        "parche": (
            "Aplicado en T75: ejecutor_fase1.a_sharegpt normaliza a NFC "
            f"system/human/gpt; residual NFD en este ensayo: {n_nfd} filas."
        ),
    })

    ids_eval = [f for f in adaptadas
               if str(f.get("id", "")).startswith("eval-")]
    des.append({
        "id": "D5",
        "titulo": "Ids de jobs vs prefijo reservado de evaluación",
        "descripcion": (
            f"Los ids de jobs.db son numéricos; {len(ids_eval)} empiezan por "
            "'eval-'. No hay riesgo de fuga con la muestra actual (comprobado)."
        ),
        "reproduccion": (
            "evaluacion_casos.es_caso_de_evaluacion(fila) -> False para todos "
            "los ids numéricos."
        ),
        "parche": "Ninguno necesario; se documenta la comprobación.",
    })

    return des


def escribir_informe(resumen, ruta):
    """Vuelca el resumen del ensayo a un informe markdown."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    sel = resumen["seleccion"]
    eje = resumen["ejecutor"]
    val = resumen["validacion"]
    fus = resumen["fusion"]
    rep = fus.get("report") or {}
    prep = resumen["preparacion"]
    est = prep.get("estadisticas") or {}

    lineas = [
        "# Ensayo extremo de la fase 1 (T70)",
        "",
        "Ensayo punta a punta **simulado, sin red**, sobre una copia de `jobs.db` "
        "en directorio temporal. Ningún dato real fue modificado.",
        "",
        f"- Directorio del ensayo: `{resumen['base_dir']}`",
        f"- Tareas seleccionadas: **{sel['total']}** "
        f"({', '.join(f'{b}: {n}' for b, n in sel['por_bloque'].items())})",
        f"- Semáforo final de `preparar_entrenamiento`: **{prep['semaforo'].upper()}**",
        "",
        "## Cadena y formatos intercambiados",
        "",
        "```",
        "jobs.db (copiar) ──> ejecutor_fase1.simulacion_fase1 (--formato sharegpt, T75)",
        "        ShareGPT: {conversations:[system,human,gpt], bloque, id, calculos} (NFC)",
        "   ── adaptar_a_sharegpt: delegacion a a_sharegpt (identidad en T75) ──>",
        "   ── validate_synthetic (--dir por bloque) ──>",
        "        synth_clean.jsonl + synth_clean.meta.jsonl {i, block} + report",
        "   ── build_dataset (mini-corpus .md sintético = 'real') ──>",
        "        train.jsonl / val.jsonl ShareGPT (SYSTEM fijo)",
        "   ── merge_final ──> dataset_ensayo/{train,val,test}.jsonl + report.json",
        "   ── preparar_entrenamiento (chatml) ──> semáforo",
        "```",
        "",
        "## Etapa 1 — ejecutor_fase1 (simulado)",
        "",
        f"- Pendientes en la copia tras la selección: "
        f"`{eje['resumen'].get('pendientes')}`",
        f"- Procesadas: `{eje['resumen'].get('procesadas')}` · "
        f"Aceptadas: **{eje['aceptadas']}** · Rechazadas: `{eje['rechazadas']}` · "
        f"Errores de red: `{eje['resumen'].get('errores_red')}`",
        f"- Motivos de rechazo: `{json.dumps(eje['motivos_rechazo'], ensure_ascii=False)}`",
        "",
        "## Etapa 2 — adaptación a ShareGPT",
        "",
        f"- Entradas: `{resumen['adaptacion']['entradas']}` · "
        f"Salidas: `{resumen['adaptacion']['salidas']}`",
        f"- Claves de entrada (ejecutor): `{resumen['adaptacion']['claves_entrada']}`",
        f"- Claves de salida (ShareGPT + extras): "
        f"`{resumen['adaptacion']['claves_salida']}`",
        f"- Filas con texto NFD normalizado a NFC: "
        f"`{resumen['adaptacion']['filas_nfd']}`",
        "",
        "## Etapa 3 — validate_synthetic",
        "",
        f"- Total: `{val.get('total')}` · Kept: **{val.get('kept')}** · "
        f"Rejected: `{val.get('rejected')}` · Casi-duplicados: "
        f"`{val.get('near_duplicates')}`",
        f"- Motivos: `{json.dumps(val.get('reasons', {}), ensure_ascii=False)}`",
        "",
        "Por bloque:",
        "",
        "| bloque | total | ok | dup | bad |",
        "|---|---|---|---|---|",
    ]
    for bloque, s in sorted((val.get("per_block") or {}).items()):
        lineas.append(
            f"| {bloque} | {s.get('total')} | {s.get('ok')} | "
            f"{s.get('dup')} | {s.get('bad')} |"
        )
    lineas += [
        "",
        "## Etapa 4 — build_dataset (corpus 'real' sintético)",
        "",
        f"- train: `{resumen['real']['train']}` · val: `{resumen['real']['val']}`",
        "",
        "## Etapa 5 — merge_final",
        "",
        f"- real train {rep.get('real_train_in')}→{rep.get('real_train_kept')} · "
        f"real val {rep.get('real_val_in')}→{rep.get('real_val_kept')}",
        f"- sintético in: `{rep.get('synth_in')}` · dup con real: "
        f"`{rep.get('synth_dups_vs_real')}` · útil: `{rep.get('synth_kept')}`",
        f"- descartes: `{json.dumps(rep.get('descartes', {}), ensure_ascii=False)}`",
        f"- split final: train `{fus.get('train')}` val "
        f"`{fus.get('val')}` test `{fus.get('test')}`",
        "",
        "## Etapa 6 — preparar_entrenamiento",
        "",
        f"- Semáforo: **{prep['semaforo'].upper()}**",
        f"- Errores: `{json.dumps(prep['errores'], ensure_ascii=False)}`",
        f"- Avisos: `{json.dumps(prep['avisos'], ensure_ascii=False)}`",
        f"- Estadísticas: `{json.dumps(est, ensure_ascii=False)[:1200]}`",
        "",
        "## DESAJUSTES entre etapas",
        "",
    ]
    for d in resumen["desajustes"]:
        lineas += [
            f"### {d['id']} — {d['titulo']}",
            "",
            d["descripcion"],
            "",
            f"- **Reproducción mínima:** {d['reproduccion']}",
            f"- **Parche propuesto:** {d['parche']}",
        ]
        if "bloques_afectados" in d and d["bloques_afectados"]:
            lineas.append(
                f"- **Bloques afectados:** "
                f"`{json.dumps(d['bloques_afectados'], ensure_ascii=False)}`"
            )
        lineas.append("")

    lineas += ["## Filas perdidas (resumen por etapa)", ""]
    perdidas = [
        ("ejecutor (rechazadas)", eje["rechazadas"]),
        ("validate_synthetic (rejected)", val.get("rejected", 0)),
        ("merge_final (descartes totales)",
         sum((rep.get("descartes") or {}).values())),
        ("preparar_entrenamiento (inválidas)",
         sum((prep.get("invalidas") or {}).values())),
    ]
    for etapa, n in perdidas:
        lineas.append(f"- {etapa}: **{n}**")
    lineas += [
        "",
        "## Fallos del ensayo",
        "",
    ]
    if resumen["fallos"]:
        for f in resumen["fallos"]:
            lineas.append(f"- ⚠️ {f}")
    else:
        lineas.append("- Ninguno: la cadena completa corrió de punta a punta.")
    lineas.append("")
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Ensayo extremo de la fase 1 (simulado, sin red, sin datos reales)."
    )
    ap.add_argument("--db", default=str(DB_REAL), help="jobs.db de origen (solo lectura)")
    ap.add_argument("--n", type=int, default=200, help="tareas representativas")
    ap.add_argument("--base-dir", default=None,
                    help="directorio temporal (por defecto mkdtemp)")
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT_ENSAYO,
                    help="umbral min-chars para validate_synthetic")
    ap.add_argument("--informe", default=None,
                    help="ruta del informe markdown (opcional)")
    args = ap.parse_args(argv)

    base = args.base_dir or tempfile.mkdtemp(prefix="ensayo_t70_")
    resumen = ejecutar_ensayo(
        base, db_src=args.db, n_tareas=args.n, min_chars=args.min_chars,
    )
    if args.informe:
        escribir_informe(resumen, args.informe)
        print(f"[ensayo] informe escrito en {args.informe}")
    print(f"[ensayo] base: {resumen['base_dir']}")
    print(f"[ensayo] seleccion {resumen['seleccion']['total']} "
          f"({resumen['seleccion']['por_bloque']})")
    print(f"[ensayo] ejecutor: aceptadas {resumen['ejecutor']['aceptadas']} "
          f"rechazadas {resumen['ejecutor']['rechazadas']}")
    print(f"[ensayo] validacion: kept {resumen['validacion'].get('kept')} "
          f"rejected {resumen['validacion'].get('rejected')}")
    print(f"[ensayo] fusion: train {resumen['fusion'].get('train')} "
          f"val {resumen['fusion'].get('val')} "
          f"test {resumen['fusion'].get('test')}")
    print(f"[ensayo] semaforo: {resumen['preparacion']['semaforo']}")
    if resumen["fallos"]:
        for f in resumen["fallos"]:
            print(f"[ensayo] FALLO: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
