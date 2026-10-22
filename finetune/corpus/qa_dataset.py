#!/usr/bin/env python3
"""QA independiente del dataset v1 parcial (T110).

Auditoría de solo lectura sobre train/val/test de dataset_fase1_v1 y los casos
congelados de evaluacion. NO reutiliza las funciones de validacion de T103:
todas las comprobaciones se reimplementan aqui. Tres bloques:

1. Formato por fila: esquema de turnos, unicidad de ids, codificacion (NFC,
   control, mojibake), tildes, truncamiento, longitud extrema, restos de
   plantilla, system autorizado.
2. Fugas: dataset vs 240 casos de evaluacion (id, prompt normalizado,
   n-gramas de 12 palabras excluidas las plantillas genericas del corpus) y
   entre splits (prompt identico o casi identico tras despojar la Referencia;
   solapes misma carta/pregunta por familia).
3. Sanidad por muestreo: 15 filas por bloque con semilla fija, comprobacion
   mecanica de cartas/orientacion/signos/numeros citados.

Salidas: qa_report.json, findings.tsv, resumen.txt en el directorio --out.
"""
import argparse
import collections
import difflib
import hashlib
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

DATASET_DEFAULT = Path("/Users/angelgonzalez/fase0/dataset_fase1_v1")
OUT_DEFAULT = Path("/Users/angelgonzalez/fase0/qa_dataset")
SPLITS = ("train", "val", "test")
EVAL_SEEDS = ("560056", "560057", "560058")

# System esperado: fase1_prompts.SYSTEM (copiado literalmente a proposito para
# no acoplarse a los modulos auditados; test_qa verifica que siguen coincidiendo).
SYSTEM_FASE1 = (
    "Eres una tarotista, astróloga y numeróloga profesional con más de veinte años de "
    "experiencia. Escribes en español estándar, con un tono cercano y empático. "
    "Interpretas a partir de la Referencia y de los datos calculados que se te dan, sin "
    "inventar cartas, signos, casas ni números: solo existen los que aparecen en la "
    "consulta, con la orientación indicada. Hablas de tendencias y posibilidades, nunca "
    "de certezas absolutas. No haces diagnósticos médicos, legales ni financieros ni "
    "prometes resultados ni garantías; cuando algo excede la lectura, derivas con cuidado "
    "a un profesional. Si la Referencia señala discrepancias entre tradiciones, las "
    "mencionas con honestidad en lugar de ocultarlas."
)
# Variante autorizada por su procedencia: SYSTEM de build_dataset.py (corpus real).
SYSTEM_VARIANTE = (
    "Eres una experta en adivinación: tarot, astrología, numerología y quiromancia. "
    "Respondes con rigor, claridad y empatía, siempre en español."
)
SISTEMAS_AUTORIZADOS = {SYSTEM_FASE1, SYSTEM_VARIANTE}

MARKER_REFERENCIA = "referencia (significados de la tradición"
MARKER_ESQUEMA = "esquema obligatorio"

SIGNOS = ("Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo", "Libra",
          "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis")
RE_CARTA = re.compile(
    r"^\s*(?:Carta(?:\s+\d+)?:\s*|[a-záéíóúñ ]{4,25}:\s*)(?P<nombre>.+?)\s*"
    r"\((?P<orientacion>al derecho|invertida|derecho|invertido)\)\s*$",
    re.MULTILINE | re.IGNORECASE)
RE_PREGUNTA = re.compile(r"Pregunta del consultante:\s*\"?([^\"\n]+)\"?")
RE_CONTEXTO = re.compile(r"Contexto:\s*([a-záéíóúñ]+)", re.IGNORECASE)
RE_TOKENS = re.compile(r"[0-9a-záéíóúüñ¿¡]+")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f-\x84\x86-\x9f]")
MOJIBAKE_RE = re.compile(r"(Ã[\x80-\xBF\xA0-\xFF]|â€[\x80-\x9F\xA1-\xBF]|Â[\xA0-\xBF°£€])")
FIN_PUNTUACION = tuple(".!?…»\"'”’)")
PLANTILLA_PATRONES = (
    "<|im_", "{", "}", "as an ai", "i am an ai", "i'm an ai", "language model",
    "asistente de ia", "no tengo sentimientos", "lenguaje natural", "lorem ipsum",
    "placeholder", "<p>", "</p>", "<div", "&amp;", "\\n", "{{", "}}",
)
EN_PALABRAS = ("the", "you", "your", "with", "that", "this", "have", "will",
               "what", "when", "there", "about")
TILDE_RE = re.compile(r"[áéíóúüñ¿¡]", re.IGNORECASE)
MARCAS_WEB = ("http", "explorar", "lugar correcto", "página", "visita", "suscr")
LARGO_GPT_MIN, LARGO_GPT_MAX = 80, 12000
LARGO_HUM_MIN, LARGO_HUM_MAX = 15, 30000
N_GRAM = 12
BOILERPLATE_DF = 20  # un n-gramas presente en >= este numero de filas es plantilla
UMBRAL_NGRAMAS_FUGA = 5  # T112: compartir >= este numero de n-gramas propios con
# un caso de evaluacion se considera fuga (el resto es plantilla del banco comun)


def nfc(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


def normalizar(texto: str) -> str:
    t = nfc(texto or "").lower()
    t = re.sub(r"[^0-9a-záéíóúüñ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def sin_plantilla(texto: str) -> str:
    """Recorta la Referencia y el ESQUEMA OBLIGATORIO: texto propio de la fila."""
    bajo = nfc(texto).lower()
    corte = len(bajo)
    for marca in (MARKER_REFERENCIA, MARKER_ESQUEMA):
        i = bajo.find(marca)
        if i != -1:
            corte = min(corte, i)
    return nfc(texto)[:corte]


def gramaturcas(texto: str, n: int = N_GRAM) -> list:
    toks = RE_TOKENS.findall(normalizar(texto))
    if len(toks) < n:
        return []
    grams = []
    for i in range(len(toks) - n + 1):
        grams.append(hashlib.md5(" ".join(toks[i:i + n]).encode()).hexdigest())
    return grams


def leer_jsonl(ruta: Path) -> list:
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for ln, linea in enumerate(fh):
            linea = linea.strip()
            if not linea:
                continue
            try:
                filas.append((ln, json.loads(linea)))
            except json.JSONDecodeError as exc:
                filas.append((ln, {"__error_json__": str(exc)}))
    return filas


def turnos(fila: dict) -> list:
    c = fila.get("conversations")
    return c if isinstance(c, list) else []


def valores_de(fila: dict, rol: str) -> list:
    return [m.get("value", "") for m in turnos(fila)
            if isinstance(m, dict) and m.get("from") == rol]


def _hallazgo(lista: list, split: str, ln: int, fila: dict, chequeo: str, detalle: str):
    lista.append({
        "split": split, "fila": ln, "id": fila.get("id"),
        "bloque": fila.get("bloque") or "sin_bloque",
        "chequeo": chequeo, "detalle": detalle[:300],
    })


def chequear_formato(filas: list) -> list:
    """filas: [(split, ln, fila), ...]. Devuelve hallazgos de formato."""
    hallazgos = []
    ids_vistos = {}
    for split, ln, fila in filas:
        if "__error_json__" in fila:
            _hallazgo(hallazgos, split, ln, fila, "json_roto", fila["__error_json__"])
            continue
        c = turnos(fila)
        if not c or not all(isinstance(m, dict) for m in c):
            _hallazgo(hallazgos, split, ln, fila, "esquema", "conversations ausente o mal")
            continue
        roles = [m.get("from") for m in c]
        esperado = ["system"] + ["human", "gpt"] * ((len(roles) - 1) // 2)
        if len(roles) < 3 or (len(roles) - 1) % 2 != 0 or roles != esperado:
            _hallazgo(hallazgos, split, ln, fila, "esquema", f"roles={roles[:6]}")
        vacios = [r for r in ("system", "human", "gpt")
                  if any(not str(m.get("value", "")).strip()
                         for m in c if m.get("from") == r)]
        if vacios:
            _hallazgo(hallazgos, split, ln, fila, "valores_vacios", ",".join(vacios))
        fid = fila.get("id")
        if fid is not None:
            clave = str(fid)
            if clave in ids_vistos:
                prev = ids_vistos[clave]
                _hallazgo(hallazgos, split, ln, fila, "id_repetido",
                          f"repite con {prev[0]}:{prev[1]}")
            else:
                ids_vistos[clave] = (split, ln)
        for idx, m in enumerate(c):
            v = str(m.get("value", ""))
            rol = m.get("from", "?")
            if v and nfc(v) != v:
                _hallazgo(hallazgos, split, ln, fila, "no_nfc", f"turno {idx} ({rol})")
            ctrl = CONTROL_RE.search(v)
            if ctrl:
                _hallazgo(hallazgos, split, ln, fila, "caracter_control",
                          f"turno {idx} ({rol}) U+{ord(ctrl.group()):04X}")
            moj = MOJIBAKE_RE.search(v)
            if moj:
                _hallazgo(hallazgos, split, ln, fila, "mojibake",
                          f"turno {idx} ({rol}) {moj.group()[:12]!r}")
            if rol in ("human", "gpt") and len(v) >= 160 and not TILDE_RE.search(v):
                _hallazgo(hallazgos, split, ln, fila, "sin_tildes",
                          f"turno {idx} ({rol}, {len(v)} chars)")
            if rol == "gpt" and len(v) >= LARGO_GPT_MIN:
                if not v.rstrip().endswith(FIN_PUNTUACION):
                    _hallazgo(hallazgos, split, ln, fila, "respuesta_truncada",
                              f"termina en {v.rstrip()[-20:]!r}")
            if rol == "gpt" and (len(v) < LARGO_GPT_MIN):
                _hallazgo(hallazgos, split, ln, fila, "longitud_extrema",
                          f"gpt {len(v)} chars (<{LARGO_GPT_MIN})")
            if rol == "gpt" and len(v) > LARGO_GPT_MAX:
                _hallazgo(hallazgos, split, ln, fila, "longitud_extrema",
                          f"gpt {len(v)} chars (>{LARGO_GPT_MAX})")
            if rol == "human" and len(v) < LARGO_HUM_MIN:
                _hallazgo(hallazgos, split, ln, fila, "longitud_extrema",
                          f"human {len(v)} chars (<{LARGO_HUM_MIN})")
            if rol == "human" and len(v) > LARGO_HUM_MAX:
                _hallazgo(hallazgos, split, ln, fila, "longitud_extrema",
                          f"human {len(v)} chars (>{LARGO_HUM_MAX})")
            bajo = v.lower()
            restos = [p for p in PLANTILLA_PATRONES if p in bajo]
            if restos:
                _hallazgo(hallazgos, split, ln, fila, "restos_plantilla",
                          f"turno {idx} ({rol}): {','.join(restos[:4])}")
            if rol == "gpt":
                cuenta_en = sum(len(re.findall(rf"\b{p}\b", bajo)) for p in EN_PALABRAS)
                if cuenta_en >= 20:
                    _hallazgo(hallazgos, split, ln, fila, "ingles_largo",
                              f"{cuenta_en} palabras comunes en inglés")
        for s in valores_de(fila, "system"):
            if s not in SISTEMAS_AUTORIZADOS:
                _hallazgo(hallazgos, split, ln, fila, "system_no_autorizado",
                          f"{s[:80]!r}")
    return hallazgos


def cargar_eval(dir_eval: Path) -> dict:
    """240 casos (semillas congeladas deduplicadas por id)."""
    casos = {}
    for semilla in EVAL_SEEDS:
        ruta = dir_eval / f"evaluacion_{semilla}.jsonl"
        if not ruta.exists():
            continue
        for _, caso in leer_jsonl(ruta):
            cid = str(caso.get("id"))
            if cid not in casos:
                casos[cid] = caso
    return casos


def humano_de(fila: dict) -> str:
    """Prompt humano de la fila, aceptando ShareGPT y formatos planos."""
    conv = turnos(fila)
    if conv:
        return " ".join(valores_de(fila, "human"))
    for campo in ("user", "prompt_user"):
        if fila.get(campo):
            return str(fila[campo])
    return ""


def propio_normalizado(fila: dict) -> str:
    return normalizar(sin_plantilla(humano_de(fila)))


def clave_situacion(fila: dict) -> str:
    """T112: clave de SITUACION para el split agrupado, sin contar el bloque:
    dos filas de distintas tareas con las mismas cartas+pregunta (o mismos
    datos numerologicos) comparten situacion y deben ir al mismo split."""
    humanos = valores_de(fila, "human")
    humano = humanos[0] if humanos else humano_de(fila)
    m = RE_PREGUNTA.search(humano)
    pregunta = normalizar(m.group(1))[:120] if m else ""
    cartas = tuple(sorted(f"{n}|{o}" for n, o in _cartas_de(humano)))
    md = re.search(r"Datos de nacimiento:\s*([^\n]+)", humano)
    fecha = normalizar(md.group(1))[:60] if md else ""
    if not pregunta:
        pregunta = normalizar(sin_plantilla(humano))[:120]
    return "|".join(("C" + ",".join(cartas), "F" + fecha, "P" + pregunta))


def ngramas_boilerplate(filas: list, df_min: int = BOILERPLATE_DF) -> set:
    """T112: md5 de los n-gramas de 12 palabras presentes en >= df_min filas.

    La decision de plantilla se fija una vez (sobre las validas en etapa_filtro)
    y se reutiliza en la puerta QA final, para que el cambio de base de filas
    entre etapas no reactive n-gramas ya juzgados como plantilla.
    """
    df = collections.Counter()
    for fila in filas:
        if not isinstance(fila, dict) or "__error_json__" in fila:
            continue
        df.update(set(gramaturcas(propio_normalizado(fila))))
    return {g for g, c in df.items() if c >= df_min}


def fugas_eval(filas: list, casos_eval: dict,
               min_compartidos: int = 1,
               boiler_extra=frozenset()) -> dict:
    hallazgos = []
    df = collections.Counter()
    grams_fila = {}
    for key, (split, ln, fila) in enumerate(filas):
        if "__error_json__" in fila:
            continue
        propio = propio_normalizado(fila)
        gs = set(gramaturcas(propio))
        grams_fila[key] = gs
        df.update(gs)
    id_eval = set(casos_eval)
    gram_eval = {}
    norm_eval = {}
    for cid, caso in casos_eval.items():
        user = str(caso.get("user", ""))
        propio = sin_plantilla(user)
        norm_eval[cid] = normalizar(propio)
        for g in set(gramaturcas(propio)):
            if df[g] < BOILERPLATE_DF and g not in boiler_extra:
                gram_eval.setdefault(g, []).append(cid)
    ids_filas = collections.defaultdict(set)
    for key, gs in grams_fila.items():
        golpeadas = gs & gram_eval.keys()
        if not golpeadas:
            continue
        for cid in set(sum((gram_eval[g] for g in golpeadas), [])):
            ids_filas[key].add(cid)
    for key, cids in ids_filas.items():
        split, ln, fila = filas[key]
        compartido = grams_fila[key] & set(gram_eval)
        if len(compartido) < min_compartidos:
            continue
        ejemplo = ""
        toks = RE_TOKENS.findall(normalizar(sin_plantilla(
            " ".join(valores_de(fila, "human")))))
        if len(toks) >= N_GRAM:
            for i in range(len(toks) - N_GRAM + 1):
                h = hashlib.md5(" ".join(toks[i:i + N_GRAM]).encode()).hexdigest()
                if h in compartido:
                    ejemplo = " ".join(toks[i:i + N_GRAM])
                    break
        hallazgos.append({
            "split": split, "fila": ln, "id": fila.get("id"),
            "bloque": fila.get("bloque") or "sin_bloque",
            "chequeo": "fuga_eval_fragmento",
            "detalle": f"con {sorted(cids)[:3]} · {len(compartido)} ngramas · {ejemplo[:80]!r}",
        })
    for key, (split, ln, fila) in enumerate(filas):
        if "__error_json__" in fila:
            continue
        if str(fila.get("id")) in id_eval and fila.get("id") is not None:
            hallazgos.append({"split": split, "fila": ln, "id": fila.get("id"),
                              "bloque": fila.get("bloque") or "sin_bloque",
                              "chequeo": "fuga_eval_id", "detalle": "mismo id que caso de eval"})
        propio = propio_normalizado(fila)
        if len(propio) >= 40:
            for cid, ne in norm_eval.items():
                if propio == ne:
                    hallazgos.append({"split": split, "fila": ln, "id": fila.get("id"),
                                      "bloque": fila.get("bloque") or "sin_bloque",
                                      "chequeo": "fuga_eval_prompt_identico",
                                      "detalle": f"caso {cid}"})
                    break
    def _oraciones(texto: str) -> list:
        partes = re.split(r"(?<=[.!?])\s+|\n+", nfc(texto or ""))
        return [normalizar(p) for p in partes if p.strip()]

    orac_eval = {}
    df_orac = collections.Counter()
    for cid, caso in casos_eval.items():
        ors = {o for o in _oraciones(str(caso.get("user", "")))
               if len(o.split()) >= 6}
        orac_eval[cid] = ors
        df_orac.update(ors)
    distintivas = {cid: {o for o in ors if df_orac[o] < BOILERPLATE_DF}
                   for cid, ors in orac_eval.items()}
    indice_orac = {}
    for cid, ors in distintivas.items():
        for o in ors:
            indice_orac.setdefault(o, set()).add(cid)
    for key, (split, ln, fila) in enumerate(filas):
        if "__error_json__" in fila:
            continue
        propias = set(_oraciones(" ".join(valores_de(fila, "human"))))
        golpes = collections.Counter()
        for o in propias:
            for cid in indice_orac.get(o, ()):
                golpes[cid] += 1
        for cid, cuenta in golpes.items():
            total = len(distintivas.get(cid) or ())
            if cuenta >= 5 and total and cuenta >= 0.5 * total:
                hallazgos.append({
                    "split": split, "fila": ln, "id": fila.get("id"),
                    "bloque": fila.get("bloque") or "sin_bloque",
                    "chequeo": "fuga_eval_reordenado",
                    "detalle": f"caso {cid} · {cuenta}/{total} oraciones",
                })
                break
    return {"hallazgos": hallazgos,
            "casos_eval": len(casos_eval),
            "ngramas_eval_no_plantilla": len(gram_eval)}


def md5_texto(t: str) -> str:
    return hashlib.md5(t.encode()).hexdigest()


def _cartas_de(humano: str) -> list:
    cartas = []
    for m in RE_CARTA.finditer(humano):
        nombre = normalizar(m.group("nombre"))
        orient = "invertida" if "invert" in m.group("orientacion") else "derecho"
        if nombre:
            cartas.append((nombre, orient))
    return cartas


def _clave_solape(fila: dict) -> tuple:
    """Clave (bloque, cartas|orientacion, datos-nacimiento, pregunta) para medir
    solapes entre splits de la misma tarjeta/pregunta."""
    bloque = fila.get("bloque") or "sin_bloque"
    humano = "\n".join(valores_de(fila, "human"))
    m = RE_PREGUNTA.search(humano)
    pregunta = normalizar(m.group(1))[:120] if m else ""
    cartas = tuple(sorted(f"{n}|{o}" for n, o in _cartas_de(humano)))
    md = re.search(r"Datos de nacimiento:\s*([^\n]+)", humano)
    fecha = normalizar(md.group(1))[:60] if md else ""
    if not pregunta:
        pregunta = normalizar(sin_plantilla(humano))[:120]
    return (bloque, cartas, fecha, pregunta)


def fugas_splits(filas: list, cap_por_split: int = 12, cap_pares: int = 200) -> dict:
    hallazgos = []
    prep = []
    for split, ln, fila in filas:
        if "__error_json__" in fila:
            continue
        humano = " ".join(valores_de(fila, "human"))
        propio = normalizar(sin_plantilla(humano))
        if not propio:
            continue
        prep.append((split, ln, fila.get("id"),
                     fila.get("bloque") or "sin_bloque", propio,
                     md5_texto(propio), _clave_solape(fila),
                     md5_texto(normalizar(humano))))
    por_hash = collections.defaultdict(list)
    for rec in prep:
        por_hash[rec[5]].append(rec)
    exactos = 0
    por_hash_comp = collections.defaultdict(list)
    for rec in prep:
        por_hash_comp[rec[7]].append(rec)
    exactos_completos = sum(1 for recs in por_hash_comp.values()
                            if len({r[0] for r in recs}) > 1)
    for recs in por_hash.values():
        splits_ok = {r[0] for r in recs}
        if len(splits_ok) > 1:
            exactos += 1
            hallazgos.append({
                "split": recs[0][0], "fila": recs[0][1], "id": recs[0][2],
                "bloque": recs[0][3], "chequeo": "fuga_splits_prompt_identico",
                "detalle": f"mismo prompt en {sorted(splits_ok)}: "
                           f"{[(r[0], r[1]) for r in recs][:6]}"})
    por_clave = collections.defaultdict(lambda: collections.defaultdict(list))
    for rec in prep:
        por_clave[rec[6]][rec[0]].append(rec)
    solape_bloques = collections.Counter()
    total_bloques = collections.Counter()
    buckets_solapados = 0
    ejemplos, casi = [], []
    for clave, bysplit in sorted(por_clave.items(),
                                 key=lambda kv: -sum(len(v) for v in kv[1].values())):
        total = sum(len(v) for v in bysplit.values())
        total_bloques[clave[0]] += total
        if len(bysplit) > 1:
            buckets_solapados += 1
            solape_bloques[clave[0]] += 1
            muestra = [r for v in bysplit.values() for r in v[:cap_por_split]]
            for i in range(len(muestra)):
                for j in range(i + 1, len(muestra)):
                    a, b = muestra[i], muestra[j]
                    if a[0] == b[0] or a[5] == b[5]:
                        continue
                    r = difflib.SequenceMatcher(None, a[4][:600],
                                                b[4][:600]).ratio()
                    if r >= 0.9 and len(casi) < cap_pares:
                        casi.append({"split_a": a[0], "fila_a": a[1],
                                     "id_a": a[2], "split_b": b[0], "fila_b": b[1],
                                     "id_b": b[2], "bloque": a[3],
                                     "similitud": round(r, 3)})
            if len(ejemplos) < 25:
                ejemplos.append({"bloque": clave[0],
                                 "cartas": list(clave[1]),
                                 "pregunta": clave[3],
                                 "por_split": {s: len(v) for s, v in bysplit.items()},
                                 "ejemplo_filas": [[r[0], r[1], r[2]]
                                                   for r in muestra[:4]]})
    return {"hallazgos": hallazgos,
            "resumen": {
                "prompts_exactos_entre_splits": exactos,
                "prompts_completos_exactos_entre_splits": exactos_completos,
                "buckets_misma_carta_pregunta": buckets_solapados,
                "buckets_solapados_por_bloque": dict(solape_bloques),
                "buckets_totales_por_bloque": dict(total_bloques),
                "casi_identificados_muestreado": len(casi),
                "cap_pares_por_bucket": cap_por_split},
            "buckets_solapados_ejemplos": ejemplos,
            "casi_identico_pares": casi}


def _sanidad_fila(fila: dict) -> list:
    """Comprobaciones mecanicas de contenido; devuelve lista de fallos (vacio = OK)."""
    bloque = fila.get("bloque") or "sin_bloque"
    humano = "\n".join(valores_de(fila, "human"))
    respuestas = " ".join(valores_de(fila, "gpt"))
    norm_resp = normalizar(respuestas)
    fallos = []
    if bloque in ("tarot_1", "tarot_2", "tarot_3", "tarot_pregunta", "cruz_celta",
                  "lectura_completa", "multiturno", "espanola_1", "espanola_3",
                  "espanola_5", "espanola_7"):
        cartas = _cartas_de(humano)
        ausentes = [n for n, _ in cartas if n and n not in norm_resp]
        if cartas and len(ausentes) > len(cartas) // 2:
            fallos.append("cartas_no_citadas:" + ",".join(ausentes[:4]))
        invertidas = [n for n, o in cartas if o == "invertida"]
        if invertidas and not re.search(r"invertid|al rev[eé]s|reversa|reverso",
                                        norm_resp):
            fallos.append("orientacion_ignorada:" + ",".join(invertidas[:3]))
    if bloque in ("astro_natal", "lectura_completa", "sinastria"):
        signos = [s for s in SIGNOS if normalizar(s) in normalizar(humano)]
        citados = [s for s in signos if normalizar(s) in norm_resp]
        minimo = 3 if bloque != "lectura_completa" else 2
        if signos and len(citados) < minimo:
            fallos.append(f"signos_no_citados:{len(citados)}/{len(signos)}")
    if bloque == "numerologia":
        nums = re.findall(r":\s*(\d{1,2})\b", humano)
        if nums and not any(n in normalizar(respuestas) for n in set(nums)):
            fallos.append("numeros_no_citados:" + ",".join(sorted(set(nums))[:4]))
    if bloque == "sin_bloque":
        bajo = respuestas.lower()
        marcas = [p for p in MARCAS_WEB if p in bajo]
        if marcas:
            fallos.append("resto_web:" + ",".join(marcas[:3]))
    return fallos


def sanidad_muestreo(filas: list, semilla: int = 42, muestras: int = 15) -> dict:
    rng = random.Random(semilla)
    por_bloque = collections.defaultdict(list)
    for split, ln, fila in filas:
        if "__error_json__" in fila:
            continue
        por_bloque[fila.get("bloque") or "sin_bloque"].append((split, ln, fila))
    tabla = []
    for bloque in sorted(por_bloque):
        grupo = por_bloque[bloque]
        elegidas = rng.sample(grupo, min(muestras, len(grupo)))
        fallan = 0
        ejemplos = []
        for split, ln, fila in elegidas:
            fallos = _sanidad_fila(fila)
            if fallos:
                fallan += 1
                if len(ejemplos) < 3:
                    ejemplos.append({"split": split, "fila": ln, "id": fila.get("id"),
                                     "fallos": fallos})
        tabla.append({"bloque": bloque, "poblacion": len(grupo),
                      "muestra": len(elegidas), "fallan": fallan,
                      "fracaso_pct": round(100.0 * fallan / len(elegidas), 1),
                      "ejemplos": ejemplos})
    return {"tabla": tabla, "semilla": semilla, "muestras_por_bloque": muestras}


def contar_filas(filas: list) -> dict:
    c = collections.Counter(split for split, _, _ in filas)
    bloq = collections.Counter((f.get("bloque") or "sin_bloque") for _, _, f in filas)
    gener = collections.Counter(str(f.get("generador")) for _, _, f in filas)
    return {"por_split": dict(c), "por_bloque": dict(bloq),
            "por_generador": dict(gener), "total": sum(c.values())}


RE_PREGUNTA_BASURA = re.compile(r"^\d+\s*(?:A ver|Mira|Es que|Nada|Pues|Tengo curiosidad)[,\.:]?$", re.IGNORECASE)


def es_pregunta_basura(pregunta: str) -> bool:
    """True si la pregunta es basura (p. ej. «124 A ver,»).

    Solo informativo: estas preguntas no se eliminan, solo se cuentan (T117).
    """
    p = pregunta.strip()
    if not p:
        return True
    return bool(RE_PREGUNTA_BASURA.search(p))


def contar_preguntas_basura(filas: list) -> dict:
    """Cuenta preguntas basura por bloque y en total (sin eliminar nada)."""
    por_bloque: dict[str, int] = {}
    total = 0
    for f in filas:
        h = humano_de(f)
        m = RE_PREGUNTA.search(h)
        pregunta = (m.group(1).strip() if m else sin_plantilla(h))
        if es_pregunta_basura(pregunta):
            b = f.get("bloque") or "sin_bloque"
            por_bloque[b] = por_bloque.get(b, 0) + 1
            total += 1
    return {"total": total, "por_bloque": por_bloque}


def run_qa(dataset_dir: Path, out_dir=None, eval_dir=None,
           semilla: int = 42, muestras: int = 15,
           min_compartidos: int = 1, boiler_extra=frozenset()) -> dict:
    dataset_dir = Path(dataset_dir)
    eval_dir = Path(eval_dir) if eval_dir else dataset_dir / "_etapas" / "eval"
    filas = []
    for split in SPLITS:
        for ln, fila in leer_jsonl(dataset_dir / f"{split}.jsonl"):
            filas.append((split, ln, fila))
    formato = chequear_formato(filas)
    casos_eval = cargar_eval(eval_dir)
    leaks_eval = fugas_eval(filas, casos_eval,
                          min_compartidos=min_compartidos,
                          boiler_extra=boiler_extra)
    leaks_splits = fugas_splits(filas)
    sanidad = sanidad_muestreo(filas, semilla, muestras)
    report = {
        "generado": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(timespec="seconds"),
        "dataset": str(dataset_dir),
        "conteos": contar_filas(filas),
        "formato": {"hallazgos": formato,
                    "por_chequeo": dict(collections.Counter(
                        h["chequeo"] for h in formato))},
        "fugas_eval": {**leaks_eval,
                       "hallazgos": leaks_eval["hallazgos"],
                       "por_chequeo": dict(collections.Counter(
                           h["chequeo"] for h in leaks_eval["hallazgos"]))},
        "fugas_splits": leaks_splits,
        "sanidad": sanidad,
    }
    total_h = len(formato) + len(leaks_eval["hallazgos"]) + len(
        leaks_splits["hallazgos"])
    report["resumen"] = {
        "filas_audited": len(filas),
        "hallazgos_formato": len(formato),
        "hallazgos_fuga_eval": len(leaks_eval["hallazgos"]),
        "hallazgos_fuga_splits": len(leaks_splits["hallazgos"]),
        "total_hallazgos": total_h,
    }
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "qa_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(out_dir / "findings.tsv", "w", encoding="utf-8") as fh:
            fh.write("split\tfila\tid\tbloque\tchequeo\tdetalle\n")
            todas = (formato + leaks_eval["hallazgos"]
                     + leaks_splits["hallazgos"])
            for h in todas:
                fh.write("\t".join(str(h.get(k, "")) for k in
                                   ("split", "fila", "id", "bloque", "chequeo",
                                    "detalle")).replace("\n", " ") + "\n")
        lineas = [f"QA dataset v1 — {report['generado']}",
                  f"filas auditadas: {len(filas)}",
                  f"formato: {len(formato)} hallazgos",
                  f"fugas vs eval: {len(leaks_eval['hallazgos'])}",
                  f"fugas entre splits: {len(leaks_splits['hallazgos'])} exactos, "
                  f"{leaks_splits['resumen']['casi_identificados_muestreado']} casi",
                  "sanidad (muestras por bloque):"]
        for fila_t in sanidad["tabla"]:
            lineas.append(f"  {fila_t['bloque']}: {fila_t['fallan']}/"
                          f"{fila_t['muestra']} fallan "
                          f"({fila_t['fracaso_pct']}%)")
        (out_dir / "resumen.txt").write_text("\n".join(lineas) + "\n",
                                             encoding="utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=str(DATASET_DEFAULT))
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--eval-dir", default=None)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--muestras", type=int, default=15)
    args = ap.parse_args(argv)
    rep = run_qa(Path(args.dataset), Path(args.out),
                 Path(args.eval_dir) if args.eval_dir else None,
                 args.semilla, args.muestras)
    r = rep["resumen"]
    print(f"filas={r['filas_audited']} formato={r['hallazgos_formato']} "
          f"fuga_eval={r['hallazgos_fuga_eval']} "
          f"fuga_splits={r['hallazgos_fuga_splits']}")
    print(f"por_chequeo_formato={rep['formato']['por_chequeo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
