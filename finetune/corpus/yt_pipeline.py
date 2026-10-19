#!/usr/bin/env python3
"""Orquestador del pipeline YouTube A4 (T21.3).

Encadena las etapas: descubrir → fetch → clean → clasificar → extraer →
normalizar. Cada etapa es reanudable: salta los vídeos ya presentes en su
propia salida. Si la descarga salta por límite de YouTube (rate_limit), el
pipeline para y el llamador debe salir con código 3.

Esquema de work-dir:
    catalogo.jsonl            entrada de vídeos (descubrir o --catalogo)
    fetch.jsonl               estado de descarga de subtítulos
    raw_vtt/<canal>/<id>...   VTT crudos (los escribe yt_fetch)
    limpio/<id>.txt           transcript limpio por vídeo
    clasificacion.jsonl       tipo de vídeo
    lecturas_validadas.jsonl  lecturas que pasan validar_lectura
    lecturas_descartadas.jsonl lecturas rechazadas (con motivos)
    conocimiento.jsonl        afirmaciones de cursos
    dataset.jsonl             pares ShareGPT (yt_normalize)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import llm_client
import yt_classify
import yt_discover
import yt_extract
import yt_fetch
import yt_normalize

ETAPAS = ["descubrir", "fetch", "clean", "clasificar", "extraer", "normalizar"]

EXIT_OK = 0
EXIT_ERROR_YT_LIMIT = 3


# ---------------------------------------------------------------------------
# Utilidades JSONL
# ---------------------------------------------------------------------------

def _leer_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    filas = []
    with open(path, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                filas.append(json.loads(linea))
            except json.JSONDecodeError:
                continue
    return filas


def _append_jsonl(path: Path, registro: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Etapa clean: transcript limpio por vídeo
# ---------------------------------------------------------------------------

def _etapa_clean(fetch_path: Path, vtt_dir: Path, limpio_dir: Path) -> Dict[str, int]:
    """Convierte los VTT descargados en limpio/<id>.txt (reanudable)."""
    limpio_dir.mkdir(parents=True, exist_ok=True)
    stats = {"limpiados": 0, "saltados": 0, "sin_vtt": 0}
    for reg in _leer_jsonl(fetch_path):
        if reg.get("estado") != "ok":
            continue
        vid = reg.get("id")
        if not vid:
            continue
        destino = limpio_dir / f"{vid}.txt"
        if destino.exists():
            stats["saltados"] += 1
            continue
        ruta_vtt = yt_classify.localizar_vtt(vid, vtt_dir)
        if ruta_vtt is None:
            stats["sin_vtt"] += 1
            continue
        try:
            texto = yt_classify.texto_limpio_vtt(ruta_vtt)
        except Exception:
            stats["sin_vtt"] += 1
            continue
        if texto.strip():
            destino.write_text(texto, encoding="utf-8")
            stats["limpiados"] += 1
        else:
            stats["sin_vtt"] += 1
    return stats


# ---------------------------------------------------------------------------
# Etapa extraer: lecturas validadas y conocimiento
# ---------------------------------------------------------------------------

def _etapa_extraer(
    catalogo_path: Path,
    clasif_path: Path,
    limpio_dir: Path,
    lecturas_path: Path,
    conocimiento_path: Path,
    descartadas_path: Path,
    client: llm_client.LLMClient,
    limite: Optional[int] = None,
) -> Dict[str, int]:
    """Extrae lecturas (tipos lectura_*/mixto) y conocimiento (cursos).

    Reanudable: salta vídeos ya presentes en lecturas_validadas,
    conocimiento o lecturas_descartadas.
    """
    canal_por_id = {}
    for fila in _leer_jsonl(catalogo_path):
        if fila.get("id"):
            canal_por_id[fila["id"]] = (fila.get("canal", ""), fila.get("titulo", ""))

    hechos = set()
    for reg in _leer_jsonl(lecturas_path):
        if reg.get("video_id"):
            hechos.add(reg["video_id"])
    for reg in _leer_jsonl(conocimiento_path):
        if reg.get("video_id"):
            hechos.add(reg["video_id"])
    for reg in _leer_jsonl(descartadas_path):
        if reg.get("video_id"):
            hechos.add(reg["video_id"])

    stats = {"lecturas_ok": 0, "lecturas_descartadas": 0, "conocimiento": 0,
             "saltados": 0, "sin_texto": 0}
    procesadas = 0

    for reg in _leer_jsonl(clasif_path):
        vid = reg.get("video_id")
        if not vid:
            continue
        if vid in hechos:
            stats["saltados"] += 1
            continue
        tipo = reg.get("tipo", "")
        es_curso = tipo == "curso_conocimiento"
        es_lectura = tipo.startswith("lectura") or tipo == "mixto"
        if not (es_curso or es_lectura):
            continue
        if limite is not None and procesadas >= limite:
            break
        ruta_txt = limpio_dir / f"{vid}.txt"
        if not ruta_txt.exists():
            stats["sin_texto"] += 1
            continue
        texto = ruta_txt.read_text(encoding="utf-8")
        procesadas += 1
        canal, titulo = canal_por_id.get(vid, ("", reg.get("titulo", "")))
        if es_curso:
            conocimiento = yt_extract.extraer_conocimiento(texto, client)
            if conocimiento.get("afirmaciones"):
                _append_jsonl(conocimiento_path, {
                    "video_id": vid,
                    "canal": canal,
                    "titulo": titulo,
                    "conocimiento": conocimiento,
                })
                stats["conocimiento"] += 1
        else:
            lectura = yt_extract.extraer_lectura(texto, client)
            valida, motivos = yt_extract.validar_lectura(lectura, texto)
            if valida:
                fila = dict(lectura)
                fila["video_id"] = vid
                fila["canal"] = canal
                fila["titulo"] = titulo
                _append_jsonl(lecturas_path, fila)
                stats["lecturas_ok"] += 1
            else:
                _append_jsonl(descartadas_path, {
                    "video_id": vid,
                    "tipo": tipo,
                    "motivos": motivos,
                })
                stats["lecturas_descartadas"] += 1
    return stats


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def procesar_pipeline(
    work_dir: str,
    catalogo: Optional[str] = None,
    limite: Optional[int] = None,
    pausa: float = 1.5,
    hasta: str = "normalizar",
    clase_ydl: Optional[Callable] = None,
    client: Optional[llm_client.LLMClient] = None,
) -> Dict[str, Any]:
    """Ejecuta el pipeline hasta la etapa `hasta` (inclusive).

    Si `catalogo` no se indica, la etapa descubrir lo genera en el work-dir.
    Devuelve un dict con las estadísticas por etapa; si la descarga se corta
    por límite de YouTube, incluye `rate_limit: True` y para ahí.
    """
    if hasta not in ETAPAS:
        raise ValueError(f"etapa 'hasta' inválida: {hasta}. Valores: {ETAPAS}")

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    catalogo_path = Path(catalogo) if catalogo else work / "catalogo.jsonl"
    fetch_path = work / "fetch.jsonl"
    vtt_dir = work / "raw_vtt"
    limpio_dir = work / "limpio"
    clasif_path = work / "clasificacion.jsonl"
    lecturas_path = work / "lecturas_validadas.jsonl"
    descartadas_path = work / "lecturas_descartadas.jsonl"
    conocimiento_path = work / "conocimiento.jsonl"
    resultado: Dict[str, Any] = {}

    # 1. descubrir
    if hasta == "descubrir":
        if catalogo:
            resultado["descubrir"] = {"saltado": 1}
        else:
            resultado["descubrir"] = yt_discover.descubrir(
                out_dir=str(work), pausa=pausa, clase_ydl=clase_ydl)
        return resultado

    if client is None:
        client = llm_client.LLMClient()

    # 2. fetch
    if not catalogo_path.exists():
        raise FileNotFoundError(f"catálogo no encontrado: {catalogo_path}")
    antes = _leer_jsonl(fetch_path)
    stats = yt_fetch.procesar_catalogo(
        catalogo_path, work, clase_ydl=clase_ydl, pausa=pausa, limite=limite)
    resultado["fetch"] = stats
    nuevas = _leer_jsonl(fetch_path)[len(antes):]
    if nuevas and nuevas[-1].get("error") == "rate_limit":
        resultado["rate_limit"] = True
        return resultado
    if hasta == "fetch":
        return resultado

    # 3. clean
    resultado["clean"] = _etapa_clean(fetch_path, vtt_dir, limpio_dir)
    if hasta == "clean":
        return resultado

    # 4. clasificar
    resultado["clasificar"] = yt_classify.procesar_clasificacion(
        catalogo_path, fetch_path, work, client, limite=limite, vtt_dir=vtt_dir)
    if hasta == "clasificar":
        return resultado

    # 5. extraer
    resultado["extraer"] = _etapa_extraer(
        catalogo_path, clasif_path, limpio_dir, lecturas_path,
        conocimiento_path, descartadas_path, client, limite=limite)
    if hasta == "extraer":
        return resultado

    # 6. normalizar (si no quedó ninguna lectura válida, no hay fichero que leer)
    if not lecturas_path.exists():
        resultado["normalizar"] = {"ok": 0, "descartados": 0, "saltados": 0}
    else:
        resultado["normalizar"] = yt_normalize.procesar_normalizacion(
            lecturas_path, work, client, limite=limite)
    return resultado


# ---------------------------------------------------------------------------
# Simulado para la CLI (smoke test sin GPU)
# ---------------------------------------------------------------------------

def _simulado_por_defecto(sistema: str, usuario: str) -> str:
    if "Clasifica según el esquema" in usuario:
        if "CURSO" in usuario:
            return json.dumps({
                "tipo": "curso_conocimiento", "familia": "tarot-conocimiento",
                "tirada": "otras", "n_cartas": 1, "calidad": 3, "motivo": "curso",
            }, ensure_ascii=False)
        return json.dumps({
            "tipo": "lectura_individual", "familia": "tarot-lectura",
            "tirada": "3_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok",
        }, ensure_ascii=False)
    if "Extrae la lectura según el esquema" in usuario:
        return json.dumps({
            "tipo": "lectura", "tirada": "3_cartas", "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [
                {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica decision importante en el amor"},
                {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
                {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y exito"},
            ],
            "sintesis": "La lectura muestra evolucion de bloqueo a claridad",
            "consejo": "Confia en tu intuicion",
        }, ensure_ascii=False)
    if "Extrae afirmaciones de conocimiento" in usuario:
        return json.dumps({
            "tipo": "conocimiento", "familia": "tarot-conocimiento",
            "afirmaciones": [
                {"entidad": "La Loca", "faceta": "significado",
                 "texto": "La Loca representa nuevos comienzos"},
            ],
        }, ensure_ascii=False)
    return (
        "En esta tirada de tres cartas sobre el amor, Los Enamorados en posición presente "
        "te hablan de una elección importante que tienes delante. La Emperatriz invertida "
        "en el pasado sugiere que has sentido un bloqueo creativo o emocional. El Sol en el "
        "futuro te trae claridad y optimismo. En síntesis, la lectura muestra una evolución "
        "desde el bloqueo hacia la luz. Consejo: confía en tu intuición y toma la decisión "
        "que tu corazón te indica."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None, clase_ydl: Optional[Callable] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline YouTube A4: descubrir → fetch → clean → clasificar → extraer → normalizar")
    parser.add_argument("--work-dir", required=True,
                       help="Directorio de trabajo del pipeline")
    parser.add_argument("--catalogo",
                       help="Catálogo externo (si se omite, se descubre en el work-dir)")
    parser.add_argument("--limite", type=int, help="Máximo de vídeos por etapa")
    parser.add_argument("--pausa", type=float, default=1.5,
                       help="Pausa entre peticiones (segundos)")
    parser.add_argument("--simulado", action="store_true",
                       help="Usar cliente simulado (smoke test sin GPU)")
    parser.add_argument("--hasta", choices=ETAPAS, default="normalizar",
                       help="Etapa hasta la que ejecutar (inclusive)")
    args = parser.parse_args(argv)

    client = None
    if args.simulado:
        client = llm_client.LLMClient(simulado=_simulado_por_defecto)

    resultado = procesar_pipeline(
        args.work_dir,
        catalogo=args.catalogo,
        limite=args.limite,
        pausa=args.pausa,
        hasta=args.hasta,
        clase_ydl=clase_ydl,
        client=client,
    )
    print(json.dumps(resultado, ensure_ascii=False))
    if resultado.get("rate_limit"):
        return EXIT_ERROR_YT_LIMIT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
