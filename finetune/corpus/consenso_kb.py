#!/usr/bin/env python3
"""Consenso por celda (entidad, faceta) a partir de afirmaciones (T38 / A6).

Lee afirmaciones tiles de web y de libros, agrupa por (entidad_id, faceta)
con un LLM de nodos (equivalencia y contradiccin, con cach en disco) y
produce por celda:

- ``mayoritarias``: grupos con 2+ fuentes independientes.
- ``discrepancias``: pares de grupos que se contradicen, marcados por tradicin.
- ``unica_fuente``: afirmaciones sin corroboracin.
- ``alertas_factuales``: afirmaciones que contradicen correspondencias de la KB
  (elemento, regente, seres elementales, tautologas). Se marcan con
  ``contradice_kb`` y no entran en el agrupamiento.

Las comprobaciones deterministas de la KB se comparten con
``afirmaciones_libros.py`` (que las aplica al generar).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cartas
import afirmaciones_es as es
from llm_client import LLMClient

MAX_POR_CELDA = 40

PALO_ELEMENTO = {
    "oros": "tierra",
    "copas": "agua",
    "espadas": "aire",
    "bastos": "fuego",
}

SERES_ELEMENTALES = {
    "gnomo": "tierra",
    "gnomos": "tierra",
    "salamandra": "fuego",
    "salamandras": "fuego",
    "ondina": "agua",
    "ondinas": "agua",
    "undina": "agua",
    "undinas": "agua",
    "silfo": "aire",
    "silfos": "aire",
    "silfide": "aire",
    "silfides": "aire",
}

PLANETAS = {
    "sol", "luna", "mercurio", "venus", "marte",
    "jupiter", "saturno", "urano", "neptuno", "pluton",
}

_RE_ELEMENTO = re.compile(
    r"(?:elemento (?:es )?|signo de |carta de )(fuego|agua|aire|tierra)\b"
)

_RE_REGENTE = re.compile(
    r"(?:regid[ao] por|gobernad[ao] por|regente (?:es|era))\s+(?:el |la )?"
    r"(sol|luna|mercurio|venus|marte|jupiter|saturno|urano|neptuno|pluton)\b"
)

_RE_RELACION = re.compile(
    r"\b(?:relaciona|relacionan|asocia|asocian|vincula|vinculan|armoniza|"
    r"armonizan|compatibiliza|compatibilizan|combina|combinan|conecta|conectan|"
    r"emparenta|emparentan|corresponde|corresponden)\b"
)


def cargar_correspondencias(kb_dir=None):
    """Correspondencias deterministas desde kb/*.json (astrologa y palos)."""
    kb_dir = kb_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb")
    with open(os.path.join(kb_dir, "astrologia.json"), "r", encoding="utf-8") as f:
        astro = json.load(f)
    signo_elemento = {}
    signo_regentes = {}
    for s in astro.get("signos", []):
        nombre = cartas.norm(s.get("nombre") or "")
        if not nombre:
            continue
        signo_elemento[nombre] = s.get("elemento")
        regs = set()
        for campo in ("regente", "regente_tradicional"):
            r = cartas.norm(s.get(campo) or "")
            if r:
                regs.add(r)
        signo_regentes[nombre] = regs
    return {
        "signo_elemento": signo_elemento,
        "signo_regentes": signo_regentes,
        "palo_elemento": dict(PALO_ELEMENTO),
    }


def signo_de_entidad(entidad_id):
    """Signo asociado a la entidad: 'aries|signo' o 'jupiter|aries|planeta_en_signo'."""
    partes = entidad_id.split("|")
    if len(partes) == 2 and partes[1] == "signo":
        return partes[0]
    if len(partes) == 3 and partes[2] == "planeta_en_signo":
        return partes[1]
    return None


def _mazo_de_entidad(entidad_id):
    if entidad_id.startswith("naipe-"):
        return "espanol"
    if entidad_id.startswith("tarot-"):
        return "tarot"
    return None


def elemento_de_entidad(entidad_id, corr):
    """Elemento cannico de la entidad, o None si no aplica."""
    signo = signo_de_entidad(entidad_id)
    if signo and corr["signo_elemento"].get(signo):
        return corr["signo_elemento"][signo]
    m = re.match(r"^(?:tarot|naipe)-(oros|copas|espadas|bastos)-\d+$", entidad_id)
    if m:
        return corr["palo_elemento"][m.group(1)]
    return None


def _seres_en_texto(texto):
    tokens = set(re.findall(r"[a-z]+", cartas.norm(texto)))
    return {t for t in tokens if t in SERES_ELEMENTALES}


VENTANA_TAUTOLOGIA = 40


def _tautologia(texto_norm, entidad_id):
    """'Aries se relaciona con los signos Aries, Leo y Sagitario' -> True.

    Exige que la entidad sea tambien el sujeto (antes del verbo): con sujeto
    distinto («El 2 de Bastos corresponde al decanato de Aries») la
    mencion tras el verbo es informativa, no tautologica. Las menciones
    lejanas de contexto («...dentro del simbolismo de Cancer») quedan fuera
    de la ventana corta tras el verbo.
    """
    signo = signo_de_entidad(entidad_id)
    mazo = _mazo_de_entidad(entidad_id)
    if signo is None and mazo is None:
        return False
    for m in _RE_RELACION.finditer(texto_norm):
        antes_verbo = texto_norm[max(0, m.start() - 4):m.start()]
        if antes_verbo.endswith("no "):
            continue
        sujeto = texto_norm[:m.start()]
        cola = texto_norm[m.end():m.end() + VENTANA_TAUTOLOGIA]
        if signo:
            if not re.search(r"\b%s\b" % re.escape(signo), sujeto):
                continue
            for sm in re.finditer(r"\b%s\b" % re.escape(signo), cola):
                antes = cola[max(0, sm.start() - 8):sm.start()]
                if re.search(r"\bno\s+(?:al?\s+|a\s+|el\s+|la\s+)?$", antes):
                    continue
                return True
        if mazo:
            sujeto_self = any(
                h.get("carta", {}).get("id") == entidad_id
                for h in cartas.extraer_cartas(sujeto, mazo=mazo, contextual=False)
            )
            if not sujeto_self:
                continue
            for hit in cartas.extraer_cartas(cola, mazo=mazo, contextual=False):
                if hit.get("carta", {}).get("id") == entidad_id:
                    return True
    return False


def contradiccion_kb(afirmacion, entidad_id, corr):
    """Comprueba contradicciones factuales contra la KB.

    Devuelve (bool, motivo) con motivo en
    {ser_elemental, elemento, regente, tautologia} o (False, None).
    """
    if not afirmacion:
        return (False, None)
    texto_norm = cartas.norm(afirmacion)
    elemento = elemento_de_entidad(entidad_id, corr)

    if elemento:
        for ser in sorted(_seres_en_texto(afirmacion)):
            if SERES_ELEMENTALES[ser] != elemento:
                return (True, "ser_elemental")
        for m in _RE_ELEMENTO.finditer(texto_norm):
            if m.group(1) != elemento:
                return (True, "elemento")

    signo = signo_de_entidad(entidad_id)
    if signo and signo in corr["signo_regentes"]:
        permitidos = corr["signo_regentes"][signo]
        for m in _RE_REGENTE.finditer(texto_norm):
            if m.group(1) in PLANETAS and m.group(1) not in permitidos:
                return (True, "regente")

    if _tautologia(texto_norm, entidad_id):
        return (True, "tautologia")

    return (False, None)


def tradicion_de_fuente(fuente_id, periodo=None):
    """Etiqueta de tradicin para marcar discrepancias."""
    fid = (fuente_id or "").lower()
    if "waite" in fid or "rws" in fid:
        return "RWS"
    if "marsella" in fid or "marseille" in fid:
        return "Marsella"
    if periodo in ("clasica", "moderna"):
        return periodo
    return "sin_periodo"


EXTRACTOR_BASE = "base"


def _clave_fuente(reg):
    """Identidad de la fuente de una afirmacin: fuente_id o dominio como respaldo."""
    return reg.get("fuente_id") or reg.get("dominio") or ""


def _extractor_de(reg):
    """Extractor que produjo la afirmacin (campo ``origen``); la tubera base
    no lo trae y se etiqueta como ``base``."""
    return reg.get("origen") or EXTRACTOR_BASE


def deduplicar_por_fuente(regs):
    """Deduplica afirmaciones por (fuente, texto normalizado) antes de agrupar.

    La independencia se cuenta por FUENTE, nunca por extractor: dos
    afirmaciones equivalentes de la misma fuente extradas por modelos
    distintos son UNA sola y no forman «mayora». El registro fusionado
    conserva en ``extractores`` qu extractores la produjeron.

    Devuelve (registros nicos, nmero de duplicados fusionados).
    """
    por_clave = {}
    orden = []
    fusionadas = 0
    for r in regs:
        texto = r.get("afirmacion")
        if not texto:
            continue
        clave = (_clave_fuente(r), cartas.norm(texto))
        if clave not in por_clave:
            nuevo = dict(r)
            nuevo["extractores"] = [_extractor_de(r)]
            por_clave[clave] = nuevo
            orden.append(clave)
            continue
        fusionadas += 1
        existente = por_clave[clave]
        existente["extractores"] = sorted(
            set(existente["extractores"]) | {_extractor_de(r)})
        for k, v in r.items():
            if k != "extractores" and k not in existente and v is not None:
                existente[k] = v
    return [por_clave[c] for c in orden], fusionadas


def _extractores_de(miembros):
    """Extractores que produjeron los miembros de un grupo de equivalencia."""
    out = set()
    for m in miembros:
        ex = m.get("extractores")
        if ex:
            out.update(ex)
        else:
            out.add(_extractor_de(m))
    return sorted(out)


class CacheEquivalencia:
    """Cach en disco (JSONL) de las respuestas de agrupamiento."""

    def __init__(self, ruta=None):
        self.ruta = ruta
        self._lock = threading.Lock()
        self._datos = {}
        if ruta and os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        reg = json.loads(linea)
                        self._datos[reg["clave"]] = reg["respuesta"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    @staticmethod
    def clave(entidad_id, faceta, afirmaciones):
        payload = json.dumps(
            [entidad_id, faceta, list(afirmaciones)],
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, clave):
        with self._lock:
            return self._datos.get(clave)

    def put(self, clave, respuesta):
        with self._lock:
            if clave in self._datos:
                return
            self._datos[clave] = respuesta
            if self.ruta:
                with open(self.ruta, "a", encoding="utf-8") as f:
                    f.write(json.dumps(
                        {"clave": clave, "respuesta": respuesta},
                        ensure_ascii=False,
                    ) + "\n")
                    f.flush()


SISTEMA_CONSENSO = (
    "Eres un asistente que agrupa afirmaciones equivalentes sobre un mismo tema "
    "y detecta contradicciones entre ellas. Responde SOLO con un objeto JSON valido."
)


def construir_prompt_consenso(entidad_id, faceta, afirmaciones):
    lineas = ["Tema: %s (%s)" % (entidad_id, faceta), "Afirmaciones:"]
    for i, texto in enumerate(afirmaciones):
        lineas.append("[%d] %s" % (i, texto))
    ultimo = len(afirmaciones) - 1
    lineas.extend([
        "",
        "Agrupa las afirmaciones que dicen esencialmente lo mismo. "
        "Devuelve JSON con el formato:",
        '{"grupos": [[0, 2], [1]], "contradicciones": [[0, 1]]}',
        "- Cada indice entre 0 y %d debe aparecer exactamente una vez en \"grupos\"." % ultimo,
        "- \"contradicciones\" son pares [i, j] de indices de grupos distintos "
        "que se contradicen entre si.",
        "- Si no hay contradicciones, usa una lista vacia.",
    ])
    return "\n".join(lineas)


def validar_particion(n):
    def _validar(data):
        if not isinstance(data, dict):
            raise ValueError("la respuesta no es un objeto JSON")
        grupos = data.get("grupos")
        if not isinstance(grupos, list) or not grupos:
            raise ValueError("falta \"grupos\" o esta vacio")
        vistos = []
        for g in grupos:
            if not isinstance(g, list) or not g:
                raise ValueError("cada grupo debe ser una lista no vacia")
            for idx in g:
                if not isinstance(idx, int) or idx < 0 or idx >= n:
                    raise ValueError("indice fuera de rango: %r" % (idx,))
                vistos.append(idx)
        if sorted(vistos) != list(range(n)):
            raise ValueError(
                "los indices deben formar una particion exacta de 0..%d" % (n - 1))
        contradicciones = data.get("contradicciones", [])
        if not isinstance(contradicciones, list):
            raise ValueError("\"contradicciones\" debe ser una lista")
        grupo_de = {}
        for gi, g in enumerate(grupos):
            for idx in g:
                grupo_de[idx] = gi
        limpias = []
        for par in contradicciones:
            if (not isinstance(par, list) or len(par) != 2 or
                    not all(isinstance(x, int) and 0 <= x < n for x in par)):
                raise ValueError("par de contradiccion invalido: %r" % (par,))
            if grupo_de[par[0]] == grupo_de[par[1]]:
                # Dos afirmaciones del mismo grupo de equivalencia no pueden
                # contradecirse: el par es ruido del LLM, se descarta y se
                # conserva la particion valida en lugar de forzar un fallo.
                continue
            limpias.append(par)
        data["contradicciones"] = limpias
        return data
    return _validar


def agrupar_celda(cliente, entidad_id, faceta, afirmaciones, cache=None):
    """Agrupamiento por equivalencia con una llamada LLM (con cach).

    ``afirmaciones``: lista de dicts con campo ``afirmacion``.
    Devuelve {"grupos": [[idx...], ...], "contradicciones": [[i, j], ...]}.
    """
    textos = [a["afirmacion"] for a in afirmaciones][:MAX_POR_CELDA]
    if len(textos) <= 1:
        return {
            "grupos": [[i] for i in range(len(textos))],
            "contradicciones": [],
        }
    clave = CacheEquivalencia.clave(entidad_id, faceta, textos) if cache else None
    if clave:
        guardada = cache.get(clave)
        if guardada is not None:
            return guardada
    prompt = construir_prompt_consenso(entidad_id, faceta, textos)
    try:
        respuesta = cliente.chat_json(
            SISTEMA_CONSENSO, prompt, validar_particion(len(textos)),
            max_tokens=1024, temperature=0.1,
        )
    except ValueError:
        # Respuesta LLM invalida tras los reintentos: no tumbar el run.
        # Caida segura: cada afirmacion en su propio grupo, sin contradicciones.
        # Se marca ``fallback`` para poder reintentar la celda mas adelante.
        return {
            "grupos": [[i] for i in range(len(textos))],
            "contradicciones": [],
            "fallback": True,
        }
    if cache and clave:
        cache.put(clave, respuesta)
    return respuesta


def _representante(miembros):
    return max(miembros, key=lambda m: len(m.get("afirmacion", "")))


def _lado_discrepancia(miembros):
    rep = _representante(miembros)
    return {
        "afirmacion": rep.get("afirmacion"),
        "fuentes": sorted({m.get("fuente_id") for m in miembros}),
        "tradiciones": sorted({
            tradicion_de_fuente(m.get("fuente_id"), m.get("periodo"))
            for m in miembros
        }),
        "extractores": _extractores_de(miembros),
    }


def construir_consensos(cliente, celdas, cache=None):
    """Procesa todas las celdas y devuelve la lista de registros de consenso."""
    resultados = []
    for (eid, faceta), regs in celdas.items():
        alertas = [r for r in regs if r.get("contradice_kb")]
        utiles = [r for r in regs if not r.get("contradice_kb")]
        agrup = agrupar_celda(cliente, eid, faceta, utiles, cache)
        grupos = agrup["grupos"]
        contradicciones = agrup.get("contradicciones", [])

        grupo_de = {}
        for gi, g in enumerate(grupos):
            for idx in g:
                grupo_de[idx] = gi

        pares = []
        for par in contradicciones:
            gi, gj = grupo_de.get(par[0]), grupo_de.get(par[1])
            if gi is None or gj is None or gi == gj:
                continue
            if gi > gj:
                gi, gj = gj, gi
            pares.append((gi, gj))
        en_discrepancia = {gi for par in pares for gi in par}

        mayoritarias = []
        unica_fuente = []
        for gi, g in enumerate(grupos):
            miembros = [utiles[i] for i in g if i < len(utiles)]
            if not miembros:
                continue
            fuentes = {m.get("fuente_id") for m in miembros}
            rep = _representante(miembros)
            if len(fuentes) >= 2:
                mayoritarias.append({
                    "afirmacion": rep.get("afirmacion"),
                    "n_fuentes": len(fuentes),
                    "fuentes": sorted(fuentes),
                    "tradiciones": sorted({
                        tradicion_de_fuente(m.get("fuente_id"), m.get("periodo"))
                        for m in miembros
                    }),
                    "extractores": _extractores_de(miembros),
                })
            elif gi not in en_discrepancia:
                unica_fuente.append({
                    "afirmacion": rep.get("afirmacion"),
                    "fuente_id": rep.get("fuente_id"),
                    "tradicion": tradicion_de_fuente(
                        rep.get("fuente_id"), rep.get("periodo")),
                    "extractores": _extractores_de(miembros),
                })

        discrepancias = [
            {
                "a": _lado_discrepancia([utiles[i] for i in grupos[gi]]),
                "b": _lado_discrepancia([utiles[i] for i in grupos[gj]]),
            }
            for gi, gj in pares
        ]

        resultados.append({
            "entidad_id": eid,
            "faceta": faceta,
            "n_afirmaciones": len(regs),
            "mayoritarias": mayoritarias,
            "discrepancias": discrepancias,
            "unica_fuente": unica_fuente,
            "fallback": bool(agrup.get("fallback")),
            "alertas_factuales": [
                {
                    "afirmacion": a.get("afirmacion"),
                    "fuente_id": a.get("fuente_id"),
                    "motivo": a.get("motivo_contradice"),
                }
                for a in alertas
            ],
        })
    return resultados


def normalizar_afirmaciones(regs, corr):
    """Recalcula ``contradice_kb`` y descarta afirmaciones no utiles.

    Se recalcula siempre (aunque el registro ya traiga el campo) para que la
    alerta final use la logica actual y no banderas de versiones anteriores.
    El filtro de utilidad (T34) se aplica a todas las entradas: las de libros
    ya lo pasaron al generarse; las de web llegan crudas.
    Devuelve (registros_utiles, n_no_utiles).
    """
    out = []
    no_utiles = 0
    for r in regs:
        eid = r.get("entidad_id")
        faceta = r.get("faceta")
        texto = r.get("afirmacion")
        if not eid or not faceta or not texto:
            continue
        util, _ = es.evaluar_utilidad(texto, eid, faceta)
        if not util:
            no_utiles += 1
            continue
        r = dict(r)
        contradice, motivo = contradiccion_kb(texto, eid, corr)
        r["contradice_kb"] = contradice
        if contradice:
            r["motivo_contradice"] = motivo
        else:
            r.pop("motivo_contradice", None)
        out.append(r)
    return out, no_utiles


def agrupar_en_celdas(regs):
    celdas = {}
    for r in regs:
        celdas.setdefault((r["entidad_id"], r["faceta"]), []).append(r)
    return celdas


def _cargar_celdas_procesadas(ruta):
    procesadas = set()
    if ruta and os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    reg = json.loads(linea)
                    procesadas.add((reg["entidad_id"], reg["faceta"]))
                except (json.JSONDecodeError, KeyError):
                    continue
    return procesadas


def _cargar_consenso_existente(ruta):
    """Registros de consenso ya escritos, indexados por (entidad_id, faceta)."""
    existentes = {}
    if ruta and os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    reg = json.loads(linea)
                    existentes[(reg["entidad_id"], reg["faceta"])] = reg
                except (json.JSONDecodeError, KeyError):
                    continue
    return existentes


def _reescribir_consenso_sin(ruta, excluir):
    """Deja copia previa de consenso.jsonl y lo reescribe sin las celdas
    excluidas (las que se van a reprocesar con extras).

    Devuelve la ruta de la copia previa, o None si no haba fichero.
    """
    if not os.path.exists(ruta):
        return None
    ruta_backup = "%s.pre-extra-%s" % (ruta, time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(ruta, ruta_backup)
    tmp = ruta + ".tmp"
    with open(ruta, "r", encoding="utf-8") as fin, \
            open(tmp, "w", encoding="utf-8") as fout:
        for linea in fin:
            s = linea.strip()
            if not s:
                continue
            try:
                reg = json.loads(s)
                clave = (reg["entidad_id"], reg["faceta"])
            except (json.JSONDecodeError, KeyError):
                fout.write(s + "\n")
                continue
            if clave in excluir:
                continue
            fout.write(json.dumps(reg, ensure_ascii=False) + "\n")
    os.replace(tmp, ruta)
    return ruta_backup


def _simulado_consenso(sistema, usuario):
    n = len(re.findall(r"^\[\d+\] ", usuario, flags=re.MULTILINE))
    return json.dumps({
        "grupos": [[i] for i in range(n)],
        "contradicciones": [],
    })


def escribir_informe(ruta, stats):
    lineas = [
        "# Informe de consenso KB (T38 / A6)",
        "",
        "- Celdas procesadas: %d" % stats["celdas"],
        "- Afirmaciones de entrada: %d" % stats["afirmaciones"],
        "- Celdas con afirmaciones mayoritarias: %d" % stats["celdas_mayoritarias"],
        "- Afirmaciones mayoritarias: %d" % stats["mayoritarias"],
        "- Discrepancias: %d" % stats["discrepancias"],
        "- Afirmaciones de una sola fuente: %d" % stats["unica_fuente"],
        "- Alertas factuales: %d" % stats["alertas"],
    ]
    if stats.get("fallback_celdas"):
        lineas.append("- Celdas en caida segura (LLM invalido, sin agrupar): %d"
                      % stats["fallback_celdas"])
    if stats.get("no_utiles"):
        lineas.append("- Descartadas por filtro de utilidad (T34): %d"
                      % stats["no_utiles"])
    if stats.get("extra_entrada"):
        lineas.append("- Afirmaciones extra de otros extractores: %d"
                      % stats["extra_entrada"])
        lineas.append("- Fusionadas por misma fuente y texto: %d"
                      % stats.get("duplicadas_por_fuente", 0))
    if stats.get("rehacer_afectadas"):
        lineas.append("- Celdas rehechas por ganar afirmaciones con extra: %d"
                      % stats["rehacer_afectadas"])
    if stats.get("motivos_alertas"):
        lineas.append("")
        lineas.append("## Alertas por motivo")
        for motivo, n in sorted(stats["motivos_alertas"].items()):
            lineas.append("- %s: %d" % (motivo, n))
    if stats.get("omitidas_existentes"):
        lineas.append("")
        lineas.append("- Celdas ya existentes (omitidas al reanudar): %d"
                      % stats["omitidas_existentes"])
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main(argv=None, cliente=None):
    parser = argparse.ArgumentParser(
        description="Consenso por celda (entidad, faceta) con LLM (T38/A6)")
    parser.add_argument(
        "--web-afirmaciones",
        default="/Users/angelgonzalez/fase0/afirmaciones_full/afirmaciones_utiles.jsonl",
        help="JSONL de afirmaciones tiles de web (opcional si an no existe)")
    parser.add_argument(
        "--libros-afirmaciones",
        default="/Users/angelgonzalez/fase0/afirmaciones_libros/afirmaciones_libros.jsonl",
        help="JSONL de afirmaciones de libros (salida de afirmaciones_libros.py)")
    parser.add_argument(
        "--out-dir",
        default="/Users/angelgonzalez/fase0/consenso_kb",
        help="Directorio de salida")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--simulado", action="store_true",
                      help="Modo simulado (sin LLM): un grupo por afirmacin")
    parser.add_argument(
        "--extra-afirmaciones", nargs="+", default=[],
        help="JSONL adicionales de afirmaciones (pasada rpida, otros "
             "extractores). La independencia se cuenta por fuente, nunca "
             "por extractor: duplicados de la misma fuente se fusionan.")
    parser.add_argument(
        "--rehacer-celdas-con-extra", action="store_true",
        help="Reprocesa solo las celdas ya procesadas que ganan afirmaciones "
             "con los extras; deja copia previa de consenso.jsonl")
    args = parser.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    ruta_salida = os.path.join(args.out_dir, "consenso.jsonl")
    ruta_cache = os.path.join(args.out_dir, "cache_equivalencia.jsonl")
    ruta_informe = os.path.join(args.out_dir, "consenso_informe.md")

    if cliente is None:
        cliente = LLMClient(simulado=_simulado_consenso if args.simulado else None)

    corr = cargar_correspondencias()
    cache = CacheEquivalencia(ruta_cache)

    regs = []
    for ruta in (args.web_afirmaciones, args.libros_afirmaciones):
        if not ruta or not os.path.exists(ruta):
            print("Sin entrada en %s (se omite)" % ruta)
            continue
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    regs.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue

    extra_regs = []
    for ruta in args.extra_afirmaciones:
        if not ruta or not os.path.exists(ruta):
            print("Sin entrada extra en %s (se omite)" % ruta)
            continue
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    extra_regs.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue

    # La base va primero: al fusionar duplicados el registro base conserva sus
    # campos y el extra aporta los extractores que faltaran.
    regs, fusionadas = deduplicar_por_fuente(regs + extra_regs)

    regs, no_utiles = normalizar_afirmaciones(regs, corr)
    celdas = agrupar_en_celdas(regs)
    procesadas = _cargar_celdas_procesadas(ruta_salida)

    rehacer = set()
    if args.rehacer_celdas_con_extra:
        if not extra_regs:
            print("Aviso: --rehacer-celdas-con-extra sin --extra-afirmaciones "
                  "no reprocesa nada")
        else:
            existentes = _cargar_consenso_existente(ruta_salida)
            for clave, regs_celda in celdas.items():
                prev = existentes.get(clave)
                if prev is not None and len(regs_celda) > int(
                        prev.get("n_afirmaciones") or 0):
                    rehacer.add(clave)
            if rehacer:
                ruta_backup = _reescribir_consenso_sin(ruta_salida, rehacer)
                print("Celdas a rehacer por extra: %d (copia previa en %s)"
                      % (len(rehacer), ruta_backup))

    pendientes = {k: v for k, v in celdas.items()
                 if k not in procesadas or k in rehacer}
    omitidas = len(celdas) - len(pendientes)

    print("Celdas totales: %d | pendientes: %d | ya procesadas: %d"
          % (len(celdas), len(pendientes), omitidas))

    stats = {
        "celdas": 0,
        "afirmaciones": len(regs),
        "celdas_mayoritarias": 0,
        "mayoritarias": 0,
        "discrepancias": 0,
        "unica_fuente": 0,
        "alertas": 0,
        "fallback_celdas": 0,
        "motivos_alertas": {},
        "no_utiles": no_utiles,
        "omitidas_existentes": omitidas,
        "extra_entrada": len(extra_regs),
        "duplicadas_por_fuente": fusionadas,
        "rehacer_afectadas": len(rehacer),
    }
    lock = threading.Lock()

    def _tratar(item):
        eid, faceta = item
        return construir_consensos(cliente, {item: celdas[item]}, cache)[0]

    with open(ruta_salida, "a", encoding="utf-8") as fout:
        def _registrar(res):
            with lock:
                fout.write(json.dumps(res, ensure_ascii=False) + "\n")
                fout.flush()
                stats["celdas"] += 1
                stats["mayoritarias"] += len(res["mayoritarias"])
                stats["discrepancias"] += len(res["discrepancias"])
                stats["unica_fuente"] += len(res["unica_fuente"])
                stats["alertas"] += len(res["alertas_factuales"])
                if res.get("fallback"):
                    stats["fallback_celdas"] += 1
                if res["mayoritarias"]:
                    stats["celdas_mayoritarias"] += 1
                for a in res["alertas_factuales"]:
                    motivo = a.get("motivo") or "sin_motivo"
                    stats["motivos_alertas"][motivo] = \
                        stats["motivos_alertas"].get(motivo, 0) + 1

        items = sorted(pendientes.keys())
        if args.workers > 1 and len(items) > 1:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for res in pool.map(_tratar, items):
                    _registrar(res)
        else:
            for item in items:
                _registrar(_tratar(item))

    escribir_informe(ruta_informe, stats)
    print("Consenso escrito en %s" % ruta_salida)
    print("Informe en %s" % ruta_informe)
    return stats


if __name__ == "__main__":
    main()
