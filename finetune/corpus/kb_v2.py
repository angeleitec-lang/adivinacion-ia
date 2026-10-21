#!/usr/bin/env python3
"""Constructor de la KB v2 a partir del consenso de afirmaciones (T66).

Lee ``consenso.jsonl`` (salida de ``consenso_kb.py``, formato por celda
entidad x faceta con ``mayoritarias``, ``discrepancias``, ``unica_fuente``,
``fallback`` y ``alertas_factuales``) y construye una KB v2 por familia en
el directorio de salida: ``tarot.json``, ``astrologia.json``,
``numerologia.json`` y ``baraja_espanola.json``.

Separacion estricta de sistemas: las entidades ``tarot-*`` van solo a tarot,
las ``naipe-*`` solo a baraja espanola; nunca se mezclan.

Criterio de confianza por celda (documentado, determinista):

- ``alta``: al menos una afirmacion mayoritaria (2+ fuentes independientes),
  sin discrepancias y sin caida segura (``fallback``).
- ``media``: hay nucleo pero tambien discrepancias entre tradiciones, o no
  hay nucleo pero si dos o mas afirmaciones de fuentes unicas distintas.
- ``baja``: caida segura (``fallback``) o menos de dos afirmaciones de una
  sola fuente sin nucleo.

Garantias: determinista (misma entrada = misma salida byte a byte),
reanudable sobre un consenso parcial (solo lee lo que hay), ignora lineas
corruptas o vacias informando del recuento, nunca modifica la entrada y
escribe de forma atomica (temporal + ``os.replace``). Cada afirmacion
conserva su procedencia (fuente_id / fuentes / tradicion) para la revision
de legalidad posterior.

El diff contra la KB v1 (``kb/*.json``) usa ``contradiccion_kb`` de
``consenso_kb.py`` para senalar las afirmaciones del consenso que
contradicen las correspondencias canonicas.
"""

from __future__ import annotations

import argparse
import json
import os
import re

import cartas
from consenso_kb import cargar_correspondencias, contradiccion_kb

FAMILIAS = ("tarot", "astrologia", "numerologia", "baraja_espanola")

FACETAS_ASTRO = {"signo", "planeta_en_signo", "planeta_en_casa", "aspecto"}
FACETAS_NUM = {"alma", "destino", "camino_de_vida", "personalidad",
               "anio_personal", "mes_personal"}

_RE_TAROT_MAYOR = re.compile(r"^tarot-mayor-(\d+)$")
_RE_TAROT_MENOR = re.compile(r"^tarot-(oros|copas|espadas|bastos)-(\d+)$")
_RE_NAIPE = re.compile(r"^naipe-(oros|copas|espadas|bastos)-(\d+)$")
_RE_CASA = re.compile(r"^casa(\d+)$")


def familia_de_entidad(entidad_id):
    """Familia KB v2 de una entidad_id, o None si no se reconoce."""
    eid = (entidad_id or "").strip()
    if not eid:
        return None
    if eid.startswith("tarot-"):
        return "tarot"
    if eid.startswith("naipe-"):
        return "baraja_espanola"
    if "|" in eid:
        sufijo = eid.rsplit("|", 1)[1]
        if sufijo in FACETAS_ASTRO:
            return "astrologia"
        if sufijo in FACETAS_NUM:
            return "numerologia"
    return None


def _norm(texto):
    return cartas.norm(texto or "")


def clave_v1(entidad_id):
    """Clave canonica de la entidad para compararla con la KB v1.

    Devuelve una tupla o None si el formato no se reconoce.
    """
    eid = (entidad_id or "").strip()
    m = _RE_TAROT_MAYOR.match(eid)
    if m:
        return ("tarot", "mayor", int(m.group(1)))
    m = _RE_TAROT_MENOR.match(eid)
    if m:
        return ("tarot", "menor", m.group(1), int(m.group(2)))
    if "|" not in eid:
        return None
    partes = eid.split("|")
    sufijo = partes[-1]
    if sufijo == "signo":
        return ("astrologia", "signo", _norm(partes[0]))
    if sufijo == "planeta_en_signo" and len(partes) == 3:
        return ("astrologia", "pes", _norm(partes[0]), _norm(partes[1]))
    if sufijo == "planeta_en_casa" and len(partes) == 3:
        mc = _RE_CASA.match(partes[1])
        if mc:
            return ("astrologia", "pec", _norm(partes[0]), int(mc.group(1)))
        return None
    if sufijo == "aspecto" and len(partes) == 4:
        return ("astrologia", "aspecto", _norm(partes[1]))
    if sufijo in FACETAS_NUM:
        try:
            return ("numerologia", int(partes[0]))
        except ValueError:
            return None
    return None


def _escribir_atomico(destino, obj):
    """Escribe JSON de forma atomica: temporal + rename.

    Si la serializacion falla, no queda ni el destino ni el temporal.
    """
    tmp = destino + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    except BaseException:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def _confianza(celda):
    nucleo = celda.get("nucleo") or []
    discrepancias = celda.get("discrepancias") or []
    unica = celda.get("unica_fuente") or []
    if celda.get("fallback"):
        return "baja"
    if nucleo and not discrepancias:
        return "alta"
    if nucleo:
        return "media"
    if len(unica) >= 2:
        return "media"
    return "baja"


def _celda_v2(reg):
    return {
        "nucleo": [dict(a) for a in reg.get("mayoritarias") or []],
        "discrepancias": [
            {"a": dict(d.get("a") or {}), "b": dict(d.get("b") or {})}
            for d in reg.get("discrepancias") or []
        ],
        "unica_fuente": [dict(u) for u in reg.get("unica_fuente") or []],
        "fallback": bool(reg.get("fallback")),
    }


def _entidades_v1(kb_v1_dir):
    """Claves v1 existentes por familia, con descripcion legible."""
    claves = set()
    descripciones = {}

    def alta(clave, familia, desc):
        claves.add(clave)
        descripciones.setdefault(familia, {})[clave] = desc

    astro_r = os.path.join(kb_v1_dir, "astrologia.json")
    if os.path.exists(astro_r):
        with open(astro_r, "r", encoding="utf-8") as f:
            astro = json.load(f)
        for s in astro.get("signos", []):
            nombre = _norm(s.get("nombre"))
            if nombre:
                alta(("astrologia", "signo", nombre), "astrologia",
                     "%s (signo)" % s.get("nombre"))
        for p in astro.get("planetas", []):
            nombre = _norm(p.get("nombre"))
            if nombre:
                alta(("astrologia", "planeta", nombre), "astrologia",
                     "%s (planeta)" % p.get("nombre"))
        for c in astro.get("casas", []):
            if c.get("numero") is not None:
                alta(("astrologia", "casa", int(c["numero"])), "astrologia",
                     "casa %s" % c.get("numero"))
        for a in astro.get("aspectos", []):
            nombre = _norm(a.get("nombre"))
            if nombre:
                alta(("astrologia", "aspecto", nombre), "astrologia",
                     "%s (aspecto)" % a.get("nombre"))

    num_r = os.path.join(kb_v1_dir, "numerologia.json")
    if os.path.exists(num_r):
        with open(num_r, "r", encoding="utf-8") as f:
            num = json.load(f)
        entradas = num.values() if isinstance(num, dict) else num
        for v in entradas:
            if isinstance(v, dict) and v.get("numero") is not None:
                alta(("numerologia", int(v["numero"])), "numerologia",
                     "%s (%s)" % (v.get("numero"), v.get("nombre", "")))

    tarot_r = os.path.join(kb_v1_dir, "tarot.json")
    if os.path.exists(tarot_r):
        with open(tarot_r, "r", encoding="utf-8") as f:
            tarot = json.load(f)
        for m in tarot.get("mayores", []):
            if m.get("numero") is not None:
                alta(("tarot", "mayor", int(m["numero"])), "tarot",
                     "%s (mayor)" % m.get("nombre"))
        for m in tarot.get("menores", []):
            palo = _norm(m.get("palo"))
            if palo and m.get("numero") is not None:
                alta(("tarot", "menor", palo, int(m["numero"])), "tarot",
                     "%s (%s)" % (m.get("nombre"), m.get("palo")))
    return claves, descripciones


def _afirmaciones_de_celda(reg):
    """Todas las afirmaciones con fuente que llegan a la celda del consenso."""
    out = []
    for a in reg.get("mayoritarias") or []:
        out.append((a.get("afirmacion"), ", ".join(a.get("fuentes") or [])))
    for u in reg.get("unica_fuente") or []:
        out.append((u.get("afirmacion"), u.get("fuente_id")))
    return out


def construir_kb_v2(ruta_consenso, dir_salida, kb_v1_dir=None,
                    informe_diff=None):
    """Construye la KB v2 por familia y (opcional) el diff contra la v1.

    Devuelve un dict de estadisticas: lineas, corruptas, celdas,
    desconocidas, por_familia, celdas_nuevas, contradicciones_v1 y
    v1_sin_respaldo.
    """
    kb_v1_dir = kb_v1_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "kb")
    os.makedirs(dir_salida, exist_ok=True)

    claves_v1, descripciones_v1 = _entidades_v1(kb_v1_dir)
    corr = cargar_correspondencias(kb_v1_dir)

    familias_datos = {f: {} for f in FAMILIAS}
    stats = {
        "lineas": 0,
        "corruptas": 0,
        "celdas": 0,
        "desconocidas": 0,
        "por_familia": {f: {"celdas": 0, "con_nucleo": 0,
                            "confianza": {"alta": 0, "media": 0, "baja": 0}}
                        for f in FAMILIAS},
        "celdas_nuevas": [],
        "contradicciones_v1": [],
        "v1_con_nucleo": set(),
    }
    vistas = set()

    with open(ruta_consenso, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            stats["lineas"] += 1
            try:
                reg = json.loads(linea)
            except json.JSONDecodeError:
                stats["corruptas"] += 1
                continue
            eid = reg.get("entidad_id")
            faceta = reg.get("faceta")
            if not eid or not faceta:
                stats["corruptas"] += 1
                continue
            familia = familia_de_entidad(eid)
            if familia is None:
                stats["desconocidas"] += 1
                continue
            clave = (eid, faceta)
            if clave in vistas:
                continue
            vistas.add(clave)

            celda = _celda_v2(reg)
            celda["confianza"] = _confianza(celda)
            familias_datos[familia].setdefault(eid, {})[faceta] = celda
            stats["celdas"] += 1
            pf = stats["por_familia"][familia]
            pf["celdas"] += 1
            pf["confianza"][celda["confianza"]] += 1
            if celda["nucleo"]:
                pf["con_nucleo"] += 1

            cv1 = clave_v1(eid)
            if cv1 is not None and celda["nucleo"]:
                stats["v1_con_nucleo"].add(cv1)
            if cv1 is None or cv1 not in claves_v1:
                stats["celdas_nuevas"].append({
                    "familia": familia,
                    "entidad_id": eid,
                    "faceta": faceta,
                })

            for texto, fuente in _afirmaciones_de_celda(reg):
                contradice, motivo = contradiccion_kb(texto, eid, corr)
                if contradice:
                    stats["contradicciones_v1"].append({
                        "familia": familia,
                        "entidad_id": eid,
                        "faceta": faceta,
                        "afirmacion": texto,
                        "fuente": fuente,
                        "motivo": motivo,
                    })
            for a in reg.get("alertas_factuales") or []:
                stats["contradicciones_v1"].append({
                    "familia": familia,
                    "entidad_id": eid,
                    "faceta": faceta,
                    "afirmacion": a.get("afirmacion"),
                    "fuente": a.get("fuente_id"),
                    "motivo": a.get("motivo"),
                })

    # Deduplicar contradicciones por (entidad, faceta, afirmacion)
    unicas = {}
    for c in stats["contradicciones_v1"]:
        k = (c["entidad_id"], c["faceta"], c["afirmacion"])
        if k not in unicas:
            unicas[k] = c
    stats["contradicciones_v1"] = [unicas[k] for k in sorted(unicas)]

    # (c) entidades v1 sin ninguna celda con nucleo en el consenso
    stats["v1_sin_respaldo"] = {}
    for familia in FAMILIAS:
        sin = []
        for clave, desc in descripciones_v1.get(familia, {}).items():
            if clave not in stats["v1_con_nucleo"]:
                sin.append(desc)
        stats["v1_sin_respaldo"][familia] = sorted(sin)

    for familia in FAMILIAS:
        entidades = familias_datos[familia]
        if not entidades:
            continue
        doc = {
            "version": 2,
            "familia": familia,
            "fuente": os.path.abspath(ruta_consenso),
            "criterio_confianza": {
                "alta": "nucleo (2+ fuentes) sin discrepancias y sin fallback",
                "media": "nucleo con discrepancias, o 2+ unicas fuentes sin nucleo",
                "baja": "fallback o menos de dos unicas fuentes sin nucleo",
            },
            "entidades": entidades,
        }
        _escribir_atomico(os.path.join(dir_salida, familia + ".json"), doc)

    if informe_diff:
        _escribir_informe_diff(informe_diff, stats)
    return stats


def _escribir_informe_diff(ruta, stats):
    lineas = [
        "# Diff de la KB v2 (consenso) contra la KB v1",
        "",
        "- Lineas leidas del consenso: %d" % stats["lineas"],
        "- Lineas corruptas o vacias ignoradas: %d" % stats["corruptas"],
        "- Celdas incorporadas: %d" % stats["celdas"],
        "- Entidades desconocidas (fuera de las cuatro familias): %d"
        % stats["desconocidas"],
        "",
        "## (a) Celdas nuevas respecto a la KB v1",
        "",
    ]
    if stats["celdas_nuevas"]:
        for c in sorted(stats["celdas_nuevas"],
                       key=lambda x: (x["familia"], x["entidad_id"],
                                     x["faceta"])):
            lineas.append("- [%s] %s / %s" % (c["familia"], c["entidad_id"],
                                             c["faceta"]))
    else:
        lineas.append("- Ninguna.")
    lineas.extend([
        "",
        "## (b) Afirmaciones del consenso que contradicen la KB v1",
        "",
        "Detectadas con ``contradiccion_kb`` de ``consenso_kb.py`` "
        "(motivos: elemento, regente, ser_elemental, tautologia) mas las "
        "alertas factuales ya presentes en el consenso.",
        "",
    ])
    if stats["contradicciones_v1"]:
        for c in stats["contradicciones_v1"]:
            lineas.append("- [%s] %s / %s (%s): %r (fuente: %s)" % (
                c["familia"], c["entidad_id"], c["faceta"],
                c.get("motivo"), c.get("afirmacion"), c.get("fuente")))
    else:
        lineas.append("- Ninguna.")
    lineas.extend([
        "",
        "## (c) Significados de la KB v1 sin respaldo en el consenso",
        "",
        "Entidades con contenido en la KB v1 para las que el consenso no "
        "aporta ninguna celda con nucleo mayoritario.",
        "",
    ])
    for familia in FAMILIAS:
        sin = stats["v1_sin_respaldo"].get(familia, [])
        lineas.append("### %s (%d)" % (familia, len(sin)))
        if sin:
            for desc in sin:
                lineas.append("- %s" % desc)
        else:
            lineas.append("- Todo respaldado o sin entradas v1.")
        lineas.append("")
    lineas.extend([
        "## (d) Cobertura por familia (celdas con nucleo / total)",
        "",
        "| Familia | Celdas | Con nucleo | Cobertura |",
        "|---|---|---|---|",
    ])
    for familia in FAMILIAS:
        pf = stats["por_familia"][familia]
        total = pf["celdas"]
        nucleo = pf["con_nucleo"]
        pct = (100.0 * nucleo / total) if total else 0.0
        lineas.append("| %s | %d | %d | %.1f%% |" % (
            familia, total, nucleo, pct))
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="KB v2 por familia a partir del consenso (T66, sin LLM)")
    parser.add_argument(
        "--consenso",
        default="/Users/angelgonzalez/fase0/consenso_kb/consenso.jsonl",
        help="JSONL de consenso (append-only, puede estar parcial)")
    parser.add_argument(
        "--out-dir",
        default="/Users/angelgonzalez/fase0/kb_v2",
        help="Directorio de salida de la KB v2")
    parser.add_argument("--kb-v1", default=None,
                       help="Directorio de la KB v1 (por defecto corpus/kb)")
    parser.add_argument("--informe", default=None,
                       help="Ruta del diff vs KB v1 (por defecto out-dir/"
                            "diff_vs_kb_v1.md)")
    args = parser.parse_args(argv)

    informe = args.informe or os.path.join(args.out_dir, "diff_vs_kb_v1.md")
    stats = construir_kb_v2(args.consenso, args.out_dir,
                           kb_v1_dir=args.kb_v1, informe_diff=informe)
    print("Lineas: %d | corruptas: %d | celdas: %d | desconocidas: %d"
          % (stats["lineas"], stats["corruptas"], stats["celdas"],
             stats["desconocidas"]))
    for familia in FAMILIAS:
        pf = stats["por_familia"][familia]
        print("  %s: %d celdas, %d con nucleo, confianza %s"
              % (familia, pf["celdas"], pf["con_nucleo"],
                 pf["confianza"]))
    print("Contradicciones v1: %d | celdas nuevas: %d"
          % (len(stats["contradicciones_v1"]), len(stats["celdas_nuevas"])))
    print("KB en %s | informe en %s" % (args.out_dir, informe))
    return stats


if __name__ == "__main__":
    main()
