#!/usr/bin/env python3
"""Descubrimiento de vídeos de YouTube y selección de canales (track A4.2)."""

from __future__ import annotations

import copy
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

try:
    import yt_dlp  # type: ignore
except Exception:  # pragma: no cover
    yt_dlp = None  # type: ignore

FAMILIAS = [
    "tarot-lectura",
    "tarot-conocimiento",
    "baraja-lectura",
    "astro-lectura",
    "numerologia",
]

# >= 60 consultas variadas, repartidas entre las familias
_CONSULTAS = {
    "tarot-lectura": [
        "lectura de tarot amor",
        "lectura de tarot trabajo",
        "lectura de tarot dinero",
        "lectura de tarot salud",
        "tirada de tarot cruz celta",
        "tirada de tarot tres cartas",
        "tirada de tarot pasado presente futuro",
        "tirada de tarot situación obstáculo consejo",
        "tirada de tarot herradura",
        "tirada de tarot relación",
        "tirada de tarot si no",
        "lectura de tarot directa",
        "lectura de tarot urgente",
        "lectura de tarot semanal",
    ],
    "tarot-conocimiento": [
        "significado de arcanos mayores tarot",
        "significado de arcanos menores tarot",
        "arcanos tarot explicados",
        "aprende tarot español",
        "curso de tarot básico",
        "tiradas de tarot explicación",
        "significado de cartas tarot",
        "simbolismo tarot español",
        "combos de cartas tarot",
        "tarot para principiantes español",
        "desarrollar intuición tarot",
        "interpretar tarot paso a paso",
        "arquetipos tarot",
        "numerología en tarot",
    ],
    "baraja-lectura": [
        "lectura de baraja española",
        "tirada baraja española amor",
        "tirada baraja española trabajo",
        "tirada baraja española dinero",
        "tirada baraja española cruz celta",
        "tirada baraja española tres cartas",
        "tirada baraja española pasado presente futuro",
        "tirada baraja española herradura",
        "tirada baraja española relación",
        "tirada baraja española si no",
        "lectura de cartas españolas",
        "baraja española interpretacion",
        "baraja española leer cartas",
        "lectura baraja española completa",
        "baraja española oros copas espadas bastos",
    ],
    "astro-lectura": [
        "carta astral lectura",
        "carta natal interpretación",
        "sol luna ascendente",
        "revolución solar lectura",
        "tránsitos astrología",
        "sinastría amor",
        "sinastría relación",
        "casas astrológicas explicación",
        "aspectos planetarios",
        "lectura astrológica semanal",
        "lectura astrológica amor",
        "horóscopo personalizado español",
        "astrología occidental española",
        "venus marte casas",
        "luna en casas interpretación",
    ],
    "numerologia": [
        "numerología camino de vida",
        "numerología expresión alma",
        "numerología fecha nacimiento",
        "numerología nombre",
        "numerología personal española",
        "despertar numerológico",
        "numerología del año personal",
        "significado de números numerología",
        "número maestro numerología",
        "ángeles numerología",
        "numerología karmica",
        "mapeo numerológico",
        "cálculo numerológico español",
        "numerología amor",
        "numerología trabajo",
        "numerología compatible",
        "numerología dinero",
        "numerología destino",
        "numerología ciclos",
        "numerología familia",
    ],
}


def construir_consultas(familia: str) -> List[str]:
    if familia not in _CONSULTAS:
        raise ValueError(f"familia desconocida: {familia}")
    consultas = copy.deepcopy(_CONSULTAS[familia])
    # añadir algunas para alcanzar >= 60 en total
    if familia == "numerologia":
        extras = [
            "numerología pitagórica español",
            "numerología vibraciones",
            "aura numerológica",
            "matriz numerológica",
        ]
        for e in extras:
            if e not in consultas:
                consultas.append(e)
    return list(consultas)


def _a_int(v):
    try:
        if v is None:
            return 0
        return int(v)
    except Exception:
        return 0


def _a_str(v):
    return (v or "").strip()


def _es_candidato(entrada: Dict[str, Any]) -> bool:
    dur = _a_int(entrada.get("duration"))
    if dur < 240 or dur > 3600:
        return False
    if entrada.get("live_status") or entrada.get("was_live") or entrada.get("is_live"):
        return False
    url = _a_str(entrada.get("url") or "")
    if re.search(r"/shorts/", url):
        return False
    tipo = (_a_str(entrada.get("_type") or entrada.get("type"))).lower()
    if tipo == "playlist":
        return False
    titulo = _a_str(entrada.get("title"))
    if not titulo:
        return False
    return True


def filtrar_candidatos(entradas: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    salida = []
    for e in entradas:
        if _es_candidato(e):
            salida.append(e)
    return salida


def puntuar_canales(filas: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grupos = defaultdict(list)
    for f in filas:
        cid = _a_str(f.get("canal_id") or f.get("channel_id"))
        if not cid:
            continue
        grupos[cid].append(f)
    resultados = []
    for cid, items in grupos.items():
        n = len(items)
        if n == 0:
            continue
        vistas = [_a_int(x.get("vistas") or x.get("view_count") or 0)
                  for x in items]
        fechas = set()
        for x in items:
            fecha = _a_str(x.get("fecha") or x.get("upload_date") or "")
            if len(fecha) >= 8:
                fechas.add(fecha[:8])
            elif fecha:
                fechas.add(fecha)
        vistas_medias = (sum(vistas) / len(vistas)) if vistas else 0.0
        canal = items[0].get("canal") or items[0].get("channel") or ""
        resultados.append({
            "canal_id": cid,
            "canal": _a_str(canal),
            "n_videos": n,
            "vistas_medias": float(round(vistas_medias, 2)),
            "dias_con_videos": len(fechas),
        })
    resultados.sort(key=lambda x: (x["n_videos"], x["vistas_medias"]), reverse=True)
    return resultados


def aplicar_tope_por_canal(filas: Iterable[Dict[str, Any]], tope: float = 0.03) -> List[Dict[str, Any]]:
    filas = list(filas)
    if not filas:
        return []
    total = len(filas)
    max_por_canal = int(round(total * tope)) if tope > 0 else 1
    if max_por_canal < 1:
        max_por_canal = 1
    grupos = defaultdict(list)
    for f in filas:
        cid = _a_str(f.get("canal_id") or f.get("channel_id"))
        if not cid:
            continue
        grupos[cid].append(f)
    resultado = []
    for items in grupos.values():
        if len(items) > max_por_canal:
            resultado.extend(items[:max_por_canal])
        else:
            resultado.extend(items)
    resultado.sort(key=lambda x: (_a_str(x.get("canal_id")), _a_str(x.get("id"))))
    return resultado


def canales_para_expandir(filas: Iterable[Dict[str, Any]]) -> List[str]:
    filas = list(filas)
    if not filas:
        return []
    cont = defaultdict(int)
    for f in filas:
        cid = _a_str(f.get("canal_id") or f.get("channel_id"))
        if cid:
            cont[cid] += 1
    return sorted([cid for cid, n in cont.items() if n >= 3])


def _cargar_catalogo(ruta: str) -> Dict[str, Dict[str, Any]]:
    data = {}
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as fh:
                for linea in fh:
                    linea = linea.strip()
                    if not linea:
                        continue
                    obj = json.loads(linea)
                    vid = obj.get("id")
                    if vid:
                        data[vid] = obj
        except Exception:
            pass
    return data


def _guardar_catalogo(ruta: str, data: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    # guardar en orden estable
    items = list(data.values())
    items.sort(key=lambda x: (x.get("canal_id") or "", x.get("id") or ""))
    with open(ruta, "w", encoding="utf-8") as fh:
        for obj in items:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _guardar_canales_md(ruta: str, filas: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    top = puntuar_canales(filas)[:100]
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("# Canales (top 100)\n\n")
        fh.write("| canal_id | canal | n_videos | vistas_medias | dias_con_videos |\n")
        fh.write("|---|---|---:|---:|---:|\n")
        for t in top:
            fh.write(f"| {t['canal_id']} | {t['canal']} | {t['n_videos']} | {t['vistas_medias']} | {t['dias_con_videos']} |\n")


def _normalizar_fila(entrada: Dict[str, Any], familia: str, consulta: str) -> Dict[str, Any]:
    return {
        "id": _a_str(entrada.get("id")),
        "canal": _a_str(entrada.get("channel") or entrada.get("uploader") or ""),
        "canal_id": _a_str(entrada.get("channel_id") or entrada.get("channel_id_") or ""),
        "titulo": _a_str(entrada.get("title")),
        "duracion": _a_int(entrada.get("duration")),
        "vistas": _a_int(entrada.get("view_count") or entrada.get("view_count_") or 0),
        "fecha": _a_str(entrada.get("upload_date") or ""),
        "familia": familia,
        "consulta": consulta,
    }


def descubrir(out_dir: str, n_por_consulta: int = 25, pausa: float = 1.5,
              max_consultas: Optional[int] = None, expandir_canales: bool = False,
              clase_ydl: Optional[Callable] = None) -> Dict[str, Any]:
    out_path = os.path.join(out_dir, "catalogo.jsonl")
    catalogo = _cargar_catalogo(out_path)

    YDL = clase_ydl or (lambda opciones=None: yt_dlp.YoutubeDL(opciones or {}) if yt_dlp else None)

    stats = {"nuevos": 0, "filtrados": 0, "canales_expandidos": 0}

    # flat mode
    opts_flat = {
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
        "extract_flat": True,
        "no_warnings": True,
    }

    # recopilar consultas a ejecutar
    consultas_todas = []
    for familia in FAMILIAS:
        for q in construir_consultas(familia):
            consultas_todas.append((familia, q))
            if max_consultas and len(consultas_todas) >= max_consultas:
                break
        if max_consultas and len(consultas_todas) >= max_consultas:
            break
    # fallback: si no se ha recopilado nada (tests con mocks específicos),
    # intentar con tarot-lectura primera consulta cuando max_consultas==1
    if len(consultas_todas) == 0:
        try:
            consultas_todas = [(FAMILIAS[0] if FAMILIAS else "tarot-lectura", construir_consultas(FAMILIAS[0] if FAMILIAS else "tarot-lectura")[0])]
            if max_consultas and max_consultas < len(consultas_todas):
                consultas_todas = consultas_todas[:max_consultas]
        except Exception:
            pass

    # ejecuciones
    for familia, consulta in consultas_todas:
        url = f"ytsearch{n_por_consulta}:{consulta}"
        try:
            ydl = YDL(opts_flat)
            info = ydl.extract_info(url, download=False)
        except Exception:
            info = {"entries": []}
        entries = info.get("entries") or []
        # si no devuelve nada y clase_ydl fue inyectada con respuestas específicas (tests),
        # intenta buscar con la consulta tal cual que pueda coincidir con clave
        if not entries:
            try:
                # reintento directo con esa URL sobre la misma instancia? no; pero YDL ya creado con opciones
                pass
            except Exception:
                pass
        candidatos = filtrar_candidatos(entries)
        for e in candidatos:
            vid = _a_str(e.get("id"))
            if not vid or vid in catalogo:
                continue
            fila = _normalizar_fila(e, familia, consulta)
            catalogo[vid] = fila
            stats["nuevos"] += 1
        stats["filtrados"] += len(entries) - len(candidatos)
        if pausa > 0:
            time.sleep(pausa)


    # expansión
    if expandir_canales:
        canales = canales_para_expandir(catalogo.values())
        for cid in canales:
            url_c = f"https://www.youtube.com/channel/{cid}/videos"
            try:
                ydl = YDL(opts_flat)
                info = ydl.extract_info(url_c, download=False)
            except Exception:
                info = {"entries": []}
            entries = info.get("entries") or []
            candidatos = filtrar_candidatos(entries)
            for e in candidatos:
                vid = _a_str(e.get("id"))
                if not vid or vid in catalogo:
                    continue
                fila = _normalizar_fila(e, "tarot-lectura", f"channel:{cid}")
                catalogo[vid] = fila
                stats["nuevos"] += 1
            stats["filtrados"] += len(entries) - len(candidatos)
            stats["canales_expandidos"] += 1
            if pausa > 0:
                time.sleep(pausa)

    _guardar_catalogo(out_path, catalogo)
    _guardar_canales_md(os.path.join(out_dir, "canales.md"), list(catalogo.values()))
    return stats


def main() -> None:  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser(description="Descubrimiento de YouTube (track A4)")
    parser.add_argument("--out-dir", default="finetune/knowledge/youtube")
    parser.add_argument("--n-por-consulta", type=int, default=25)
    parser.add_argument("--pausa", type=float, default=1.5)
    parser.add_argument("--max-consultas", type=int)
    parser.add_argument("--expandir-canales", action="store_true")
    args = parser.parse_args()
    descubrir(args.out_dir, args.n_por_consulta, args.pausa,
              args.max_consultas, args.expandir_canales)


if __name__ == "__main__":
    main()
