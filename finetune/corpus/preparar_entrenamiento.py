#!/usr/bin/env python3
"""Prepara el dataset final para la fase 2 de entrenamiento (T61).

Lee los ficheros ShareGPT de ``corpus/final`` (train/val/test), valida el
esquema, descarta las filas inválidas, comprueba que no haya fuga del conjunto
reservado de evaluación y calcula estadísticas antes de convertir el dataset al
formato que consume Soup (``sharegpt`` o ``chatml``).

No entrena, no llama a ningún LLM y no instala paquetes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
if str(CORPUS_DIR) not in sys.path:
    sys.path.insert(0, str(CORPUS_DIR))

import cartas as cartas_mod
import evaluacion_casos as eval_mod

SPLITS = ("train", "val", "test")
ROLES = ("system", "human", "gpt")
ROLE_MAP = {"system": "system", "human": "user", "gpt": "assistant"}
FORMATOS = ("sharegpt", "chatml")
CHAR_POR_TOKEN = 3.5
UMBRAL_INVALIDAS_ROJO = 0.10
UMBRAL_DUPLICADOS_ROJO = 0.20
UMBRAL_ETICA_AVISO = 0.02
UMBRAL_COBERTURA_AVISO = 0.80

_ETICA_RE = re.compile(
    r"hacerme daño|suicid|autolesion|me quiero morir|quitar la vida|"
    r"menor de edad|diagn[oó]stico m[eé]dico|enfermedad grave|"
    r"c[aá]ncer|demanda judicial|inversi[oó]n de dinero|"
    r"abuso|violencia|maltrato",
    re.I,
)
_MENCION_CARTA_RE = re.compile(r"\b(?:carta|arcano|naipe)\b", re.I)
_MENCION_BARAJA_RE = re.compile(
    r"baraja espa[ñn]ola|naipes? espa[ñn]ol|palos? espa[ñn]ol|"
    r"espadas|copas|bastos|oros",
    re.I,
)


def nfc(texto) -> str:
    """Normaliza a NFC conservando el contenido."""
    return unicodedata.normalize("NFC", str(texto or ""))


def normalizar(texto) -> str:
    """Minúsculas, sin tildes ni signos: base de comparaciones."""
    descompuesto = unicodedata.normalize("NFKD", nfc(texto).lower())
    sin_tildes = "".join(
        c for c in descompuesto if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes).split())


def validar_fila(fila) -> list[str]:
    """Devuelve los errores de esquema de una fila ShareGPT."""
    if not isinstance(fila, dict):
        return ["la fila no es un objeto JSON"]
    conversaciones = fila.get("conversations")
    if not isinstance(conversaciones, list) or not conversaciones:
        return ["falta 'conversations' o está vacía"]
    errores: list[str] = []
    roles: list[str] = []
    for indice, turno in enumerate(conversaciones):
        if not isinstance(turno, dict):
            errores.append(f"turno {indice}: no es un objeto")
            continue
        rol = turno.get("from")
        valor = turno.get("value")
        if rol not in ROLES:
            errores.append(f"turno {indice}: rol desconocido {rol!r}")
        if not isinstance(valor, str) or not valor.strip():
            errores.append(f"turno {indice}: 'value' vacío o no textual")
        roles.append(str(rol))
    if errores:
        return errores
    if roles[0] == "system":
        cuerpo = roles[1:]
    else:
        cuerpo = roles
    if "system" in cuerpo:
        errores.append("'system' debe ser el primer turno y aparecer una sola vez")
    if len([r for r in roles if r == "system"]) > 1:
        errores.append("hay más de un turno 'system'")
    if not cuerpo:
        errores.append("no hay turnos de conversación")
        return errores
    if cuerpo[0] != "human":
        errores.append("la conversación debe empezar por 'human'")
    for anterior, actual in zip(cuerpo, cuerpo[1:]):
        if anterior == actual:
            errores.append(f"turnos consecutivos con el mismo rol {actual!r}")
    if cuerpo[-1] != "gpt":
        errores.append("la conversación no termina en una respuesta 'gpt'")
    if any(r not in ("human", "gpt") for r in cuerpo):
        errores.append("solo se admiten 'human' y 'gpt' tras el 'system'")
    return errores


def leer_jsonl(ruta: Path) -> tuple[list[dict], list[dict]]:
    """Lee un JSONL y separa filas válidas de líneas con JSON roto."""
    if not ruta.exists():
        return [], []
    validas: list[dict] = []
    invalidas: list[dict] = []
    with ruta.open(encoding="utf-8") as fh:
        for numero, linea in enumerate(fh, start=1):
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError as exc:
                invalidas.append({
                    "linea": numero,
                    "motivo": f"JSON inválido: {exc.msg}",
                })
                continue
            validas.append({"linea": numero, "fila": fila})
    return validas, invalidas


def convertir_fila(fila: dict, formato: str) -> dict:
    """Convierte una fila ShareGPT al formato pedido, sin campos extra."""
    if formato not in FORMATOS:
        raise ValueError(f"Formato no soportado: {formato}")
    conversaciones = [
        {"from": t["from"], "value": nfc(t["value"])}
        for t in fila["conversations"]
    ]
    if formato == "sharegpt":
        return {"conversations": conversaciones}
    return {
        "messages": [
            {"role": ROLE_MAP[t["from"]], "content": t["value"]}
            for t in conversaciones
        ]
    }


def cargar_casos_evaluacion(ruta: Path | None = None) -> list[dict]:
    """Carga el conjunto de evaluación; si no hay fichero, lo genera en memoria."""
    if ruta is not None:
        if not ruta.exists():
            raise FileNotFoundError(f"No existe el conjunto de evaluación: {ruta}")
        casos, _ = leer_jsonl(ruta)
        return [c["fila"] for c in casos]
    casos, _ = leer_jsonl(CORPUS_DIR / "evaluacion_casos.jsonl")
    if casos:
        return [c["fila"] for c in casos]
    return eval_mod.generar_casos()


def cargar_respuestas_evaluacion(ruta: Path | None) -> list[str]:
    """Carga respuestas de referencia de evaluación si el usuario las aporta."""
    if ruta is None:
        return []
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el fichero de respuestas: {ruta}")
    filas, _ = leer_jsonl(ruta)
    respuestas = []
    for item in filas:
        valor = item["fila"].get("respuesta") if isinstance(item["fila"], dict) else None
        if isinstance(valor, str) and valor.strip():
            respuestas.append(normalizar(valor))
    return respuestas


def _semillas_reservadas(fila) -> set[int]:
    encontradas: set[int] = set()

    def recorrer(valor, clave=""):
        if isinstance(valor, dict):
            for k, v in valor.items():
                recorrer(v, str(k).lower())
        elif isinstance(valor, list):
            for v in valor:
                recorrer(v, clave)
        elif clave in ("semilla", "seed", "semillas", "seeds"):
            if isinstance(valor, (int, float)) and int(valor) in eval_mod.SEMILLAS_RESERVADAS:
                encontradas.add(int(valor))
            elif isinstance(valor, str):
                for parte in re.findall(r"\d+", valor):
                    if int(parte) in eval_mod.SEMILLAS_RESERVADAS:
                        encontradas.add(int(parte))

    recorrer(fila)
    return encontradas


def detectar_fugas(
    filas_por_split: dict[str, list[dict]],
    casos: list[dict],
    respuestas_eval: list[str] | None = None,
) -> list[dict]:
    """Busca ids, prompts o semillas del conjunto reservado en train/val."""
    ids = {str(c.get("id", "")) for c in casos if c.get("id")}
    prompts = {
        normalizar(c.get("user", "")) for c in casos if c.get("user")
    }
    prompts.discard("")
    respuestas = set(respuestas_eval or [])
    fugas: list[dict] = []
    for split in ("train", "val"):
        for item in filas_por_split.get(split, []):
            fila = item["fila"]
            if not isinstance(fila, dict):
                fila = {}
            linea = item["linea"]
            ident = str(fila.get("id", ""))
            if eval_mod.es_caso_de_evaluacion(fila) or (ident and ident in ids):
                fugas.append({
                    "split": split,
                    "linea": linea,
                    "motivo": f"id de evaluación: {ident or '(sin id)'}",
                })
            humanos = [
                t.get("value", "")
                for t in fila.get("conversations", [])
                if isinstance(t, dict) and t.get("from") == "human"
            ]
            for texto in humanos:
                if normalizar(texto) in prompts:
                    fugas.append({
                        "split": split,
                        "linea": linea,
                        "motivo": "prompt idéntico a un caso de evaluación",
                    })
                    break
            for semilla in sorted(_semillas_reservadas(fila)):
                fugas.append({
                    "split": split,
                    "linea": linea,
                    "motivo": f"semilla reservada de evaluación: {semilla}",
                })
            if respuestas:
                for turno in fila.get("conversations", []):
                    if (
                        isinstance(turno, dict)
                        and turno.get("from") == "gpt"
                        and normalizar(turno.get("value", "")) in respuestas
                    ):
                        fugas.append({
                            "split": split,
                            "linea": linea,
                            "motivo": "respuesta idéntica a una respuesta de evaluación",
                        })
                        break
    return fugas


def _familia(fila: dict) -> str:
    for contenedor in (fila, fila.get("metadatos") or {}):
        if not isinstance(contenedor, dict):
            continue
        for clave in ("familia", "bloque", "categoria", "categoría", "tipo"):
            valor = contenedor.get(clave)
            if isinstance(valor, str) and valor.strip():
                return unicodedata.normalize("NFC", valor.strip().lower())
    return "sin_etiquetar"


def _system_y_turnos(fila: dict) -> tuple[str, list[dict]]:
    system = ""
    turnos = []
    for turno in fila.get("conversations", []):
        if not isinstance(turno, dict):
            continue
        if turno.get("from") == "system":
            system = nfc(turno.get("value", ""))
        else:
            turnos.append(turno)
    return system, turnos


def _es_etica(fila: dict, humanos: list[str]) -> bool:
    if _familia(fila) == "etica":
        return True
    return bool(_ETICA_RE.search(" ".join(humanos)))


def _mazo_de(fila: dict, texto: str) -> str | None:
    familia = _familia(fila)
    if familia.startswith("baraja") or familia.startswith("naipe"):
        return "espanol"
    if familia.startswith("tarot"):
        return "tarot"
    if _MENCION_BARAJA_RE.search(texto):
        return "espanol"
    if _MENCION_CARTA_RE.search(texto) or "tarot" in normalizar(texto):
        return "tarot"
    return None


def _cartas_de(fila: dict, humanos: list[str]) -> list[dict]:
    texto = "\n".join(humanos)
    mazo = _mazo_de(fila, texto)
    if mazo:
        return cartas_mod.extraer_cartas(texto, mazo=mazo)
    encontradas = cartas_mod.extraer_cartas(texto, mazo="tarot")
    if encontradas:
        return encontradas
    return cartas_mod.extraer_cartas(texto, mazo="espanol")


def _texto_completo(fila: dict) -> str:
    return "\n".join(
        nfc(t.get("value", ""))
        for t in fila.get("conversations", [])
        if isinstance(t, dict)
    )


def _contar_tokens(textos: list[str], tokenizador: str | None) -> tuple[list[int], str]:
    if tokenizador:
        try:
            from tokenizers import Tokenizer

            tok = Tokenizer.from_file(tokenizador)
            return [len(tok.encode(t).ids) for t in textos], f"tokenizers:{tokenizador}"
        except Exception:
            try:
                from transformers import AutoTokenizer

                tok = AutoTokenizer.from_pretrained(tokenizador, local_files_only=True)
                return [len(tok.encode(t)) for t in textos], f"transformers:{tokenizador}"
            except Exception as exc:
                print(
                    f"AVISO: no se pudo usar el tokenizador {tokenizador!r} "
                    f"({exc}); se estima caracteres/{CHAR_POR_TOKEN}.",
                    file=sys.stderr,
                )
    return [int(round(len(t) / CHAR_POR_TOKEN)) for t in textos], (
        f"estimación caracteres/{CHAR_POR_TOKEN}"
    )


def _resumen_numerico(valores: list[int]) -> dict:
    if not valores:
        return {"n": 0, "media": 0.0, "mediana": 0.0, "p95": 0, "max": 0}
    ordenados = sorted(valores)
    p95 = ordenados[min(len(ordenados) - 1, math.ceil(len(ordenados) * 0.95) - 1)]
    return {
        "n": len(valores),
        "media": round(statistics.fmean(valores), 1),
        "mediana": round(statistics.median(valores), 1),
        "p95": p95,
        "max": max(valores),
    }


def calcular_estadisticas(
    filas_por_split: dict[str, list[dict]],
    leidas: dict[str, int],
    invalidas: dict[str, int],
    tokenizador: str | None = None,
    epochs: float = 3,
    max_longitud: int = 2048,
) -> dict:
    """Calcula estadísticas del dataset a partir de las filas ya validadas."""
    familias: Counter = Counter()
    turnos_por_fila = []
    humanos_total = 0
    sistemas: Counter = Counter()
    caracteres = {"system": [], "human": [], "gpt": [], "total": []}
    textos_para_tokens = []
    hashes: Counter = Counter()
    prompts: Counter = Counter()
    eticas = 0
    cartas_tarot: Counter = Counter()
    cartas_espanol: Counter = Counter()
    orientaciones = {"derecha": 0, "invertida": 0, "desconocida": 0}

    filas_validas = []
    for split in SPLITS:
        filas_validas.extend(filas_por_split.get(split, []))

    for item in filas_validas:
        fila = item["fila"]
        system, turnos = _system_y_turnos(fila)
        humanos = [nfc(t.get("value", "")) for t in turnos if t.get("from") == "human"]
        respuestas = [nfc(t.get("value", "")) for t in turnos if t.get("from") == "gpt"]
        familias[_familia(fila)] += 1
        if len(humanos) > 1:
            turnos_por_fila.append("multiturno")
        else:
            turnos_por_fila.append("un_turno")
        humanos_total += len(humanos)
        sistemas[system] += 1
        caracteres["system"].append(len(system))
        caracteres["human"].append(sum(len(x) for x in humanos))
        caracteres["gpt"].append(sum(len(x) for x in respuestas))
        completo = _texto_completo(fila)
        caracteres["total"].append(len(completo))
        textos_para_tokens.append(completo)
        hashes[hashlib.sha256(normalizar(completo).encode("utf-8")).hexdigest()] += 1
        if humanos:
            prompts[hashlib.sha256(normalizar(humanos[0]).encode("utf-8")).hexdigest()] += 1
        if _es_etica(fila, humanos):
            eticas += 1
        for encontrada in _cartas_de(fila, humanos):
            carta = encontrada["carta"]
            orientacion = encontrada.get("orientacion")
            if orientacion == "invertida":
                orientaciones["invertida"] += 1
            elif orientacion == "derecha":
                orientaciones["derecha"] += 1
            else:
                orientaciones["desconocida"] += 1
            if carta.get("id", "").startswith("tarot-"):
                cartas_tarot[carta["nombre"]] += 1
            elif carta.get("id", "").startswith("naipe-"):
                cartas_espanol[carta["nombre"]] += 1

    tokens, metodo_tokens = _contar_tokens(textos_para_tokens, tokenizador)
    tokens_recortados = [min(t, max_longitud) for t in tokens]
    n = len(filas_validas)
    duplicados = sum(c - 1 for c in hashes.values() if c > 1)
    prompts_repetidos = sum(c - 1 for c in prompts.values() if c > 1)

    def resumen_mazo(contador: Counter, catalogo: list[dict]) -> dict:
        nombres = [c["nombre"] for c in catalogo]
        usadas = [n for n in nombres if contador[n] > 0]
        mas = contador.most_common(10)
        menos = sorted(
            ((n, contador[n]) for n in nombres),
            key=lambda x: (x[1], x[0]),
        )[:10]
        return {
            "total_menciones": sum(contador.values()),
            "cartas_distintas": len(usadas),
            "catalogo": len(nombres),
            "cobertura": round(len(usadas) / len(nombres), 4) if nombres else 0.0,
            "mas_frecuentes": mas,
            "menos_frecuentes": menos,
            "sin_usar": [n for n in nombres if contador[n] == 0],
        }

    def horas(throughput: float, factor: float = 1.15) -> float:
        if not tokens_recortados:
            return 0.0
        tokens_totales = sum(tokens_recortados) * epochs
        return round(tokens_totales / throughput * factor / 3600, 2)

    return {
        "filas": {
            "leidas": leidas,
            "invalidas": invalidas,
            "validas": {split: len(filas_por_split.get(split, [])) for split in SPLITS},
            "total_validas": n,
        },
        "turnos": {
            "un_turno": turnos_por_fila.count("un_turno"),
            "multiturno": turnos_por_fila.count("multiturno"),
            "humanos_total": humanos_total,
        },
        "por_familia": dict(sorted(familias.items(), key=lambda x: (-x[1], x[0]))),
        "system_prompts": [
            {"veces": c, "texto": t[:160]} for t, c in sistemas.most_common(10)
        ],
        "longitud_caracteres": {
            clave: _resumen_numerico(valores) for clave, valores in caracteres.items()
        },
        "tokens": {
            "metodo": metodo_tokens,
            "por_ejemplo": _resumen_numerico(tokens_recortados),
            "max_longitud": max_longitud,
        },
        "duplicados": {
            "exactos": duplicados,
            "grupos": sum(1 for c in hashes.values() if c > 1),
            "prompts_repetidos": prompts_repetidos,
            "proporcion_exactos": round(duplicados / n, 4) if n else 0.0,
        },
        "etica": {
            "n": eticas,
            "proporcion": round(eticas / n, 4) if n else 0.0,
        },
        "cartas": {
            "tarot": resumen_mazo(cartas_tarot, cartas_mod.CARTAS_TAROT),
            "espanol": resumen_mazo(cartas_espanol, cartas_mod.NAIPES_ESPANOLES),
            "orientaciones": orientaciones,
        },
        "horas_estimadas": {
            "7b": horas(750.0),
            "14b": horas(350.0),
            "supuestos": (
                "QLoRA 4-bit, longitud máxima 2048, 3 épocas, lote efectivo 16, "
                "15 % de sobrecarga y 750/350 tokens/s para 7B/14B en Strix Halo "
                "128 GB. Valores orientativos, no medidos en este equipo."
            ),
        },
    }


def _problemas_y_semaforo(
    estadisticas: dict,
    fugas: list[dict],
    splits_presentes: dict[str, bool],
) -> tuple[str, list[str], list[str]]:
    errores: list[str] = []
    avisos: list[str] = []
    filas = estadisticas["filas"]
    if fugas:
        errores.append(f"fugas del conjunto de evaluación: {len(fugas)}")
    if filas["validas"]["train"] == 0:
        errores.append("train no tiene ninguna fila válida")
    if filas["validas"]["val"] == 0:
        errores.append("val no tiene ninguna fila válida")
    total_leidas = sum(filas["leidas"].values())
    total_invalidas = sum(filas["invalidas"].values())
    if total_leidas and total_invalidas / total_leidas > UMBRAL_INVALIDAS_ROJO:
        errores.append(
            f"demasiadas filas inválidas: {total_invalidas}/{total_leidas} "
            f"(> {UMBRAL_INVALIDAS_ROJO:.0%})"
        )
    elif total_invalidas:
        avisos.append(f"se descartaron filas inválidas: {total_invalidas}")
    if (
        filas["total_validas"] >= 20
        and estadisticas["duplicados"]["proporcion_exactos"]
        > UMBRAL_DUPLICADOS_ROJO
    ):
        errores.append(
            "más del 20 % de filas duplicadas exactas; revisar merge_final.py"
        )
    elif estadisticas["duplicados"]["exactos"]:
        avisos.append(
            f"hay duplicados exactos: {estadisticas['duplicados']['exactos']}"
        )
    if not splits_presentes.get("test"):
        avisos.append("no hay test.jsonl: la evaluación final usará el conjunto reservado")
    elif filas["validas"]["test"] < 20:
        avisos.append(
            f"test tiene solo {filas['validas']['test']} filas; "
            "es orientativo, no representativo"
        )
    if filas["total_validas"] < 100:
        avisos.append(
            f"el dataset tiene {filas['total_validas']} filas válidas; "
            "es un ensayo, no un dataset de entrenamiento"
        )
    if estadisticas["etica"]["proporcion"] < UMBRAL_ETICA_AVISO:
        avisos.append(
            f"casos éticos: {estadisticas['etica']['proporcion']:.1%} "
            f"(< {UMBRAL_ETICA_AVISO:.0%} recomendado)"
        )
    tarot = estadisticas["cartas"]["tarot"]
    espanol = estadisticas["cartas"]["espanol"]
    if tarot["total_menciones"] and tarot["cobertura"] < UMBRAL_COBERTURA_AVISO:
        avisos.append(
            f"cobertura de tarot: {tarot['cartas_distintas']}/78 cartas "
            f"({tarot['cobertura']:.0%})"
        )
    if espanol["total_menciones"] and espanol["cobertura"] < UMBRAL_COBERTURA_AVISO:
        avisos.append(
            f"cobertura de baraja española: {espanol['cartas_distintas']}/40 naipes "
            f"({espanol['cobertura']:.0%})"
        )
    if not espanol["total_menciones"]:
        avisos.append("no se detectaron naipes de baraja española en los prompts")
    if filas["total_validas"] and (
        estadisticas["por_familia"].get("sin_etiquetar", 0) / filas["total_validas"]
        > 0.5
    ):
        avisos.append(
            "más de la mitad de las filas no llevan 'familia'/'bloque' en los metadatos"
        )
    if errores:
        return "rojo", errores, avisos
    if avisos:
        return "amarillo", errores, avisos
    return "verde", errores, avisos


def _tabla_familias(por_familia: dict, total: int) -> list[str]:
    lineas = ["| Familia | Filas | Proporción |", "|---|---:|---:|"]
    for familia, n in por_familia.items():
        proporcion = f"{n / total:.1%}" if total else "0.0 %"
        lineas.append(f"| {familia} | {n} | {proporcion} |")
    return lineas


def _lista_cartas(items: list[tuple[str, int]]) -> str:
    return ", ".join(f"{nombre} ({n})" for nombre, n in items) or "—"


def construir_informe(
    dataset: Path,
    salida: Path,
    formato: str,
    semaforo: str,
    errores: list[str],
    avisos: list[str],
    estadisticas: dict,
    fugas: list[dict],
    invalidas: dict[str, list[dict]],
    rutas_salida: list[Path],
) -> str:
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filas = estadisticas["filas"]
    lineas = [
        "# Informe de preparación para entrenamiento",
        "",
        f"Generado: {fecha}",
        f"Dataset: `{dataset}`",
        f"Formato de salida: `{formato}`",
        "",
        f"## Semáforo: {semaforo.upper()}",
        "",
    ]
    if semaforo == "verde":
        lineas.append("**Listo** para pasar a entrenamiento, sin avisos bloqueantes.")
    elif semaforo == "amarillo":
        lineas.append("**Advertencia**: se puede entrenar, pero conviene revisar los avisos.")
    else:
        lineas.append(
            "**No listo**: no se generó ningún fichero de entrenamiento nuevo. "
            "Si había ficheros de una ejecución anterior, no se han modificado."
        )
    lineas += ["", "### Problemas bloqueantes", ""]
    lineas += [f"- {x}" for x in errores] or ["- Ninguno."]
    lineas += ["", "### Avisos", ""]
    lineas += [f"- {x}" for x in avisos] or ["- Ninguno."]

    lineas += [
        "",
        "## Recuento por split",
        "",
        "| Split | Leídas | Válidas | Inválidas |",
        "|---|---:|---:|---:|",
    ]
    for split in SPLITS:
        lineas.append(
            f"| {split} | {filas['leidas'].get(split, 0)} | "
            f"{filas['validas'].get(split, 0)} | {filas['invalidas'].get(split, 0)} |"
        )
    lineas.append(f"| **Total** | **{sum(filas['leidas'].values())}** | "
                  f"**{filas['total_validas']}** | "
                  f"**{sum(filas['invalidas'].values())}** |")

    if any(invalidas.values()):
        lineas += ["", "### Filas descartadas (primeras 15)", ""]
        mostradas = 0
        for split in SPLITS:
            for item in invalidas.get(split, []):
                if mostradas >= 15:
                    break
                motivos = item.get("motivos") or [item.get("motivo", "")]
                lineas.append(
                    f"- `{split}` línea {item.get('linea')}: "
                    + "; ".join(str(m) for m in motivos)
                )
                mostradas += 1
        if mostradas == 0:
            lineas.append("- Ninguna.")

    lineas += [
        "",
        "## Fugas del conjunto de evaluación",
        "",
        f"Coincidencias de fuga entre evaluación y train/val: "
        f"{len(fugas)}.",
    ]
    if fugas:
        lineas += [
            "",
            "| Split | Línea | Motivo |",
            "|---|---:|---|",
        ]
        for fuga in fugas[:30]:
            lineas.append(f"| {fuga['split']} | {fuga['linea']} | {fuga['motivo']} |")
    else:
        lineas.append(
            "No se encontraron ids, prompts ni semillas reservadas en train/val. "
            "El conjunto de evaluación no incluye respuestas de referencia, así que "
            "la comparación de respuestas solo se aplica si se aporta "
            "`--eval-respuestas`."
        )

    lineas += [
        "",
        "## Composición",
        "",
        f"- Filas válidas: {filas['total_validas']}",
        f"- Un turno: {estadisticas['turnos']['un_turno']}",
        f"- Multiturno: {estadisticas['turnos']['multiturno']}",
        f"- Turnos de usuario: {estadisticas['turnos']['humanos_total']}",
        f"- Casos éticos: {estadisticas['etica']['n']} "
        f"({estadisticas['etica']['proporcion']:.1%})",
        f"- Duplicados exactos: {estadisticas['duplicados']['exactos']} "
        f"({estadisticas['duplicados']['proporcion_exactos']:.1%}); "
        f"prompts iniciales repetidos: {estadisticas['duplicados']['prompts_repetidos']}",
        "",
        "### Por familia o bloque",
        "",
    ]
    lineas += _tabla_familias(
        estadisticas["por_familia"], estadisticas["filas"]["total_validas"]
    )

    longitudes = estadisticas["longitud_caracteres"]
    tokens = estadisticas["tokens"]
    lineas += [
        "",
        "## Longitud",
        "",
        "| Campo | Media | Mediana | P95 | Máximo |",
        "|---|---:|---:|---:|---:|",
    ]
    for clave in ("system", "human", "gpt", "total"):
        r = longitudes[clave]
        lineas.append(
            f"| {clave} | {r['media']:.1f} | {r['mediana']:.1f} | "
            f"{r['p95']} | {r['max']} |"
        )
    lineas += [
        "",
        f"Tokens por ejemplo ({tokens['metodo']}): media "
        f"{tokens['por_ejemplo']['media']:.1f}, mediana "
        f"{tokens['por_ejemplo']['mediana']:.1f}, P95 "
        f"{tokens['por_ejemplo']['p95']}, máximo {tokens['por_ejemplo']['max']} "
        f"(recortado a {tokens['max_longitud']}).",
    ]

    tarot = estadisticas["cartas"]["tarot"]
    espanol = estadisticas["cartas"]["espanol"]
    orientaciones = estadisticas["cartas"]["orientaciones"]
    lineas += [
        "",
        "## Cartas",
        "",
        f"- Orientación: derecha {orientaciones['derecha']}, "
        f"invertida {orientaciones['invertida']}, "
        f"sin especificar {orientaciones['desconocida']}",
        f"- Tarot: {tarot['cartas_distintas']}/78 cartas distintas, "
        f"{tarot['total_menciones']} menciones, cobertura {tarot['cobertura']:.1%}",
        f"  - Más frecuentes: {_lista_cartas(tarot['mas_frecuentes'])}",
        f"  - Menos frecuentes: {_lista_cartas(tarot['menos_frecuentes'])}",
        f"- Baraja española: {espanol['cartas_distintas']}/40 naipes distintos, "
        f"{espanol['total_menciones']} menciones, cobertura {espanol['cobertura']:.1%}",
        f"  - Más frecuentes: {_lista_cartas(espanol['mas_frecuentes'])}",
        f"  - Menos frecuentes: {_lista_cartas(espanol['menos_frecuentes'])}",
    ]

    horas = estadisticas["horas_estimadas"]
    lineas += [
        "",
        "## Estimación de entrenamiento",
        "",
        f"- 7B: ~{horas['7b']} h",
        f"- 14B: ~{horas['14b']} h",
        "",
        f"Supuestos: {horas['supuestos']}",
        "",
        "## Ficheros generados",
        "",
    ]
    lineas += [f"- `{ruta}`" for ruta in rutas_salida] or [
        "- Ninguno (semáforo rojo)."
    ]
    lineas += [
        "",
        "## Siguiente paso",
        "",
        "Revisar este informe, corregir los avisos que apliquen y, solo después,",
        "usar los ficheros convertidos con la configuración de "
        "`finetune/entrenamiento/`. La estimación de horas no sustituye una "
        "medición real en nodo1.",
        "",
    ]
    return "\n".join(lineas)


def _resolver_formato(valor: str) -> str:
    if valor == "messages":
        return "chatml"
    return valor


def preparar(
    dataset: Path,
    salida: Path,
    formato: str = "chatml",
    eval_casos: Path | None = None,
    eval_respuestas: Path | None = None,
    tokenizador: str | None = None,
    epochs: float = 3,
    max_longitud: int = 2048,
) -> dict:
    """Ejecuta la preparación y devuelve el informe y los datos calculados."""
    formato = _resolver_formato(formato)
    filas_por_split: dict[str, list[dict]] = {}
    invalidas: dict[str, list[dict]] = {}
    leidas: dict[str, int] = {}
    splits_presentes: dict[str, bool] = {}

    for split in SPLITS:
        ruta = dataset / f"{split}.jsonl"
        splits_presentes[split] = ruta.exists()
        validas, rotas = leer_jsonl(ruta)
        buenas = []
        descartes = list(rotas)
        for item in validas:
            errores = validar_fila(item["fila"])
            if errores:
                descartes.append({
                    "linea": item["linea"],
                    "motivos": errores,
                })
            else:
                buenas.append(item)
        filas_por_split[split] = buenas
        invalidas[split] = descartes
        leidas[split] = len(validas) + len(rotas)

    casos = cargar_casos_evaluacion(eval_casos)
    respuestas = cargar_respuestas_evaluacion(eval_respuestas)
    fugas = detectar_fugas(filas_por_split, casos, respuestas)
    estadisticas = calcular_estadisticas(
        filas_por_split, leidas,
        {split: len(invalidas[split]) for split in SPLITS},
        tokenizador=tokenizador,
        epochs=epochs,
        max_longitud=max_longitud,
    )
    semaforo, errores, avisos = _problemas_y_semaforo(
        estadisticas, fugas, splits_presentes
    )

    salida.mkdir(parents=True, exist_ok=True)
    rutas_salida: list[Path] = []
    if semaforo != "rojo":
        for split in SPLITS:
            ruta = salida / f"{split}.jsonl"
            with ruta.open("w", encoding="utf-8") as fh:
                for item in filas_por_split[split]:
                    convertida = convertir_fila(item["fila"], formato)
                    fh.write(json.dumps(convertida, ensure_ascii=False) + "\n")
            rutas_salida.append(ruta)
    ruta_estadisticas = salida / "estadisticas.json"
    ruta_estadisticas.write_text(
        json.dumps(estadisticas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rutas_salida.append(ruta_estadisticas)
    ruta_informe = salida / "informe_entrenamiento.md"
    ruta_informe.write_text(
        construir_informe(
            dataset, salida, formato, semaforo, errores, avisos,
            estadisticas, fugas, invalidas, rutas_salida,
        ),
        encoding="utf-8",
    )
    return {
        "semaforo": semaforo,
        "errores": errores,
        "avisos": avisos,
        "estadisticas": estadisticas,
        "fugas": fugas,
        "invalidas": invalidas,
        "rutas_salida": rutas_salida,
        "informe": ruta_informe,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Valida, convierte y audita el dataset final antes de entrenar."
    )
    parser.add_argument("--dataset", required=True,
                        help="Carpeta con train.jsonl, val.jsonl y test.jsonl (ShareGPT)")
    parser.add_argument("--salida", default=None,
                        help="Carpeta de salida (por defecto <dataset>/preparado)")
    parser.add_argument("--formato", default="chatml",
                        choices=("sharegpt", "chatml", "messages"),
                        help="Formato de entrenamiento: sharegpt o chatml")
    parser.add_argument("--eval-casos", default=None,
                        help="JSONL de casos de evaluación (por defecto, generarlos)")
    parser.add_argument("--eval-respuestas", default=None,
                        help="JSONL opcional con respuestas de referencia de evaluación")
    parser.add_argument("--tokenizador", default=None,
                        help="Ruta local a tokenizer.json o a un modelo con tokenizador")
    parser.add_argument("--epochs", type=float, default=3.0,
                        help="Épocas para la estimación de horas (por defecto 3)")
    parser.add_argument("--max-longitud", type=int, default=2048,
                        help="Longitud máxima de secuencia para la estimación")
    parser.add_argument("--estricto", action="store_true",
                        help="Devuelve error también con semáforo amarillo")
    args = parser.parse_args(argv)

    dataset = Path(args.dataset).expanduser().resolve()
    salida = Path(args.salida).expanduser().resolve() if args.salida else dataset / "preparado"
    resultado = preparar(
        dataset,
        salida,
        formato=args.formato,
        eval_casos=Path(args.eval_casos).expanduser() if args.eval_casos else None,
        eval_respuestas=(
            Path(args.eval_respuestas).expanduser() if args.eval_respuestas else None
        ),
        tokenizador=args.tokenizador,
        epochs=args.epochs,
        max_longitud=args.max_longitud,
    )
    semaforo = resultado["semaforo"]
    print(f"Semáforo: {semaforo.upper()}")
    for error in resultado["errores"]:
        print(f"  BLOQUEANTE: {error}")
    for aviso in resultado["avisos"]:
        print(f"  aviso: {aviso}")
    print(f"Informe: {resultado['informe']}")
    if semaforo == "rojo":
        return 2
    if semaforo == "amarillo" and args.estricto:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
