"""Cobertura v3 reproducible: una orden que regenera la matriz con las evidencias
vigentes y dice qué falta (sin LLM ni red).

Reúne en un único comando las fuentes de evidencia que hoy están en vigor:

- web: ``/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl``
- libros: limpias (``libros_limpio/evidencias_limpias.jsonl``, T71) o crudas
  (``libros/evidencias/evidencias.jsonl``), a elección con ``--libros``
- exclusión opcional de las claves de consenso contaminadas
  (``libros_limpio/claves_excluir_consenso.jsonl``): se descarta toda evidencia
  cuyo ``(hash_seccion, entidad_id, faceta)`` coincida con una clave.

Con las evidencias reunidas calcula la matriz (criterios de celda completa:
>=5 fuentes independientes, >=1 clásica, >=2 modernas, >=1 en español,
calidad >=3), escribe ``cobertura_total_v3.json/.md`` en un directororio nuevo
(sin tocar los ``cobertura_total*.json`` existentes) y produce:

1. Comparación con la v2: celdas que pasan a completas, las que dejan de serlo
   y por qué (qué criterio cae por debajo del mínimo).
2. Informe de huecos: por familia, las 30 entidades con más celdas incompletas
   con su carencia agregada, los dominios que más aportan y la estimación de
   fuentes nuevas para llegar al 10 % de celdas completas por familia con el
   ritmo de aportación real observado (método de mínimos de T43).

Uso típico (todo por defecto):

    finetune/.venv/bin/python finetune/corpus/cobertura_v3.py

Determinista: mismas entradas y opciones -> mismas salidas.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cobertura
from recuperacion_dirigida import MINIMOS, fuentes_necesarias

FASE0 = "/Users/angelgonzalez/fase0"

RUTAS = {
    "web": os.path.join(FASE0, "evidencias_web", "evidencias.jsonl"),
    "libros_limpio": os.path.join(FASE0, "libros_limpio", "evidencias_limpias.jsonl"),
    "libros_crudo": os.path.join(FASE0, "libros", "evidencias", "evidencias.jsonl"),
    "claves_excluir": os.path.join(FASE0, "libros_limpio", "claves_excluir_consenso.jsonl"),
    "v2": os.path.join(FASE0, "cobertura_total_v2.json"),
    "out_dir": os.path.join(FASE0, "cobertura_v3"),
}

META_COMPLETAS = 0.10
TOP_ENTIDADES = 30
TOP_DOMINIOS = 10


# ---------------------------------------------------------------------------
# Reunión de evidencias vigentes
# ---------------------------------------------------------------------------

def cargar_claves_exclusion(ruta):
    """Conjunto de (hash_seccion, entidad_id, faceta) a excluir.

    Fichero inexistente -> conjunto vacío. Líneas inválidas se ignoran.
    """
    claves = set()
    if not ruta:
        return claves
    try:
        archivo = open(ruta, encoding="utf-8")
    except FileNotFoundError:
        return claves
    with archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue
            try:
                dato = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if not isinstance(dato, dict):
                continue
            hash_seccion = dato.get("hash_seccion")
            entidad_id = dato.get("entidad_id")
            faceta = dato.get("faceta")
            if hash_seccion and entidad_id and faceta:
                claves.add((hash_seccion, entidad_id, faceta))
    return claves


def excluir_por_claves(evidencias, claves):
    """Devuelve (conservadas, excluidas) según claves (hash_seccion, entidad_id, faceta).

    Las evidencias sin ``hash_seccion`` no pueden coincidir y se conservan.
    """
    if not claves:
        return list(evidencias), 0
    conservadas = []
    excluidas = 0
    for ev in evidencias:
        clave = (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))
        if None not in clave and clave in claves:
            excluidas += 1
        else:
            conservadas.append(ev)
    return conservadas, excluidas


def reunir_evidencias(web_ruta, libros_ruta, claves=None, extra_rutas=None):
    """Lee y reúne las evidencias vigentes.

    Devuelve (evidencias, info) con ``info``: recuentos por origen, claves
    cargadas/excluidas y líneas JSON inválidas.
    """
    info = {"origenes": {}, "claves_cargadas": 0, "excluidas": 0, "invalidas": 0}
    evidencias = []
    for etiqueta, ruta in (("web", web_ruta), ("libros", libros_ruta)):
        if not ruta:
            continue
        antes, malas = leer_evidencias([ruta])
        info["origenes"][etiqueta] = {"ruta": ruta, "leidas": len(antes), "invalidas": malas}
        info["invalidas"] += malas
        evidencias.extend(antes)
    if claves:
        info["claves_cargadas"] = len(claves)
        evidencias, excluidas = excluir_por_claves(evidencias, claves)
        info["excluidas"] = excluidas
    for ruta in extra_rutas or []:
        antes, malas = leer_evidencias([ruta])
        info["origenes"].setdefault("extra", {"rutas": []})
        info["origenes"]["extra"].setdefault("rutas", []).append(ruta)
        info["origenes"]["extra"]["leidas"] = \
            info["origenes"]["extra"].get("leidas", 0) + len(antes)
        info["invalidas"] += malas
        evidencias.extend(antes)
    return evidencias, info


leer_evidencias = cobertura.leer_evidencias


# ---------------------------------------------------------------------------
# Comparación con la v2
# ---------------------------------------------------------------------------

def _indice_celdas(celdas):
    return {(c["entidad_id"], c["faceta"]): c for c in celdas}


def _motivo_caida(celda_v2, celda_v3, minimos=None):
    """Criterios que la v2 cumplía y la v3 ya no."""
    m = minimos or MINIMOS
    pares = (
        ("fuentes", "n_fuentes", m["fuentes"]),
        ("clasica", "n_clasicas", m["clasicas"]),
        ("moderna", "n_modernas", m["modernas"]),
        ("es", "n_es", m["es"]),
    )
    perdio = []
    for nombre, campo, minimo in pares:
        v2 = int(celda_v2.get(campo) or 0)
        v3 = int(celda_v3.get(campo) or 0)
        if v2 >= minimo and v3 < minimo:
            perdio.append(f"{nombre}: {v2} -> {v3} (min {minimo})")
    return perdio


def comparar_v2_v3(celdas_v3, ruta_v2, minimos=None):
    """Compara la matriz v3 con la v2 guardada en disco.

    Devuelve dict con conteos y listas (ordenadas por entidad_id, faceta):
    ``pasan_a_completas`` y ``dejan_de_serlo`` (con el criterio perdido).
    Si la v2 no existe, ``disponible`` es False.
    """
    if not ruta_v2 or not os.path.exists(ruta_v2):
        return {"disponible": False, "ruta": ruta_v2}
    with open(ruta_v2, encoding="utf-8") as f:
        v2 = json.load(f)
    idx_v2 = _indice_celdas(v2.get("celdas", []))
    idx_v3 = _indice_celdas(celdas_v3)
    pasan = []
    dejan = []
    for clave, c3 in idx_v3.items():
        c2 = idx_v2.get(clave)
        if c2 is None:
            continue
        if not c2.get("completa") and c3.get("completa"):
            pasan.append({
                "entidad_id": clave[0], "faceta": clave[1],
                "n_fuentes": c3.get("n_fuentes"),
                "n_clasicas": c3.get("n_clasicas"),
                "n_modernas": c3.get("n_modernas"),
                "n_es": c3.get("n_es"),
            })
        elif c2.get("completa") and not c3.get("completa"):
            dejan.append({
                "entidad_id": clave[0], "faceta": clave[1],
                "v2": {k: c2.get(k) for k in ("n_fuentes", "n_clasicas",
                                             "n_modernas", "n_es")},
                "v3": {k: c3.get(k) for k in ("n_fuentes", "n_clasicas",
                                             "n_modernas", "n_es")},
                "motivo": _motivo_caida(c2, c3, minimos),
            })
    pasan.sort(key=lambda c: (c["entidad_id"], c["faceta"]))
    dejan.sort(key=lambda c: (c["entidad_id"], c["faceta"]))
    return {
        "disponible": True,
        "ruta": ruta_v2,
        "v2_completas": v2.get("resumen", {}).get("completas"),
        "v3_completas": sum(1 for c in celdas_v3 if c.get("completa")),
        "pasan_a_completas": pasan,
        "dejan_de_serlo": dejan,
    }


# ---------------------------------------------------------------------------
# Informe de huecos
# ---------------------------------------------------------------------------

def top_entidades_incompletas(celdas, catalogo=None, top_n=TOP_ENTIDADES):
    """Por familia, las entidades con más celdas incompletas y su carencia agregada.

    Carencia agregada: suma de los déficits (min - valor, cortado en 0) de cada
    celda incompleta de la entidad. Devuelve {familia: [entrada...]}.
    """
    if catalogo is None:
        catalogo = cobertura.entidades()
    nombre_de = {e["entidad_id"]: e["nombre"] for e in catalogo}
    familia_de = {e["entidad_id"]: e["familia"] for e in catalogo}
    por_entidad = {}
    for celda in celdas:
        if celda.get("completa"):
            continue
        ent = celda["entidad_id"]
        d = por_entidad.setdefault(ent, {
            "entidad_id": ent,
            "nombre": nombre_de.get(ent, ent),
            "familia": familia_de.get(ent, "desconocida"),
            "celdas_incompletas": 0,
            "falta_independientes": 0,
            "falta_clasicas": 0,
            "falta_modernas": 0,
            "falta_es": 0,
        })
        d["celdas_incompletas"] += 1
        d["falta_independientes"] += max(0, MINIMOS["fuentes"] - int(celda.get("n_fuentes") or 0))
        d["falta_clasicas"] += max(0, MINIMOS["clasicas"] - int(celda.get("n_clasicas") or 0))
        d["falta_modernas"] += max(0, MINIMOS["modernas"] - int(celda.get("n_modernas") or 0))
        d["falta_es"] += max(0, MINIMOS["es"] - int(celda.get("n_es") or 0))
    por_familia = {}
    for d in por_entidad.values():
        por_familia.setdefault(d["familia"], []).append(d)
    resultado = {}
    for familia, entradas in por_familia.items():
        entradas.sort(key=lambda d: (-d["celdas_incompletas"], d["entidad_id"]))
        resultado[familia] = entradas[:top_n]
    return resultado


def dominios_top_por_familia(evidencias, catalogo=None, top_n=TOP_DOMINIOS,
                            calidad_min=3):
    """Dominios (o ids de libro) que más aportan por familia.

    Cuenta evidencias de calidad >= minimo y entidades distintas cubiertas.
    Devuelve {familia: [{dominio, n_evidencias, n_entidades}...]}.
    """
    if catalogo is None:
        catalogo = cobertura.entidades()
    familia_de = {e["entidad_id"]: e["familia"] for e in catalogo}
    acum = {}
    for ev in evidencias:
        try:
            calidad = int(ev.get("calidad", 0))
        except (TypeError, ValueError):
            calidad = 0
        if calidad < calidad_min:
            continue
        familia = familia_de.get(ev.get("entidad_id"))
        if familia is None:
            continue
        dominio = cobertura._clave_dominio(ev) or "(sin dominio)"
        d = acum.setdefault((familia, dominio),
                           {"dominio": dominio, "n_evidencias": 0,
                            "entidades": set()})
        d["n_evidencias"] += 1
        d["entidades"].add(ev.get("entidad_id"))
    resultado = {}
    for (familia, _), d in acum.items():
        resultado.setdefault(familia, []).append({
            "dominio": d["dominio"],
            "n_evidencias": d["n_evidencias"],
            "n_entidades": len(d["entidades"]),
        })
    for entradas in resultado.values():
        entradas.sort(key=lambda d: (-d["n_entidades"], -d["n_evidencias"],
                                    d["dominio"]))
        entradas[:] = entradas[:top_n]
    return resultado


def estimacion_meta_por_familia(celdas, catalogo=None, meta=META_COMPLETAS):
    """Fuentes nuevas para llegar a `meta` de celdas completas, por familia.

    - ``fuentes_ideales``: método T43 (arreglar primero las celdas más baratas,
      con ``fuentes_necesarias`` de recuperacion_dirigida).
    - ``ritmo_observado``: celdas completas por fuente distinta aportada a la
      familia en la pasada actual (evidencias de calidad >= minimo).
    - ``fuentes_ritmo``: fuentes necesarias al ritmo observado (None si el
      ritmo es 0 o no hay fuentes).
    """
    if catalogo is None:
        catalogo = cobertura.entidades()
    familia_de = {e["entidad_id"]: e["familia"] for e in catalogo}
    grupos = {}
    for celda in celdas:
        familia = familia_de.get(celda["entidad_id"], "desconocida")
        grupos.setdefault(familia, []).append(celda)
    resultado = {}
    for familia, celdas_f in grupos.items():
        total = len(celdas_f)
        completas = sum(1 for c in celdas_f if c.get("completa"))
        requeridas = max(0, math.ceil(total * meta) - completas)
        necesidades = sorted(fuentes_necesarias(c) for c in celdas_f
                             if not c.get("completa"))
        fuentes_ideales = sum(necesidades[:requeridas])
        resultado[familia] = {
            "celdas": total,
            "completas": completas,
            "meta_completas": math.ceil(total * meta),
            "celdas_faltantes": requeridas,
            "fuentes_ideales": fuentes_ideales,
            "fuentes_total_arreglar": sum(necesidades),
        }
    return resultado


def ritmo_observado_por_familia(evidencias, catalogo=None, calidad_min=3):
    """Celdas completas por fuente distinta aportada, por familia."""
    if catalogo is None:
        catalogo = cobertura.entidades()
    familia_de = {e["entidad_id"]: e["familia"] for e in catalogo}
    fuentes = {}
    for ev in evidencias:
        try:
            calidad = int(ev.get("calidad", 0))
        except (TypeError, ValueError):
            calidad = 0
        if calidad < calidad_min:
            continue
        familia = familia_de.get(ev.get("entidad_id"))
        if familia is None:
            continue
        fuente = ev.get("fuente_id")
        if fuente:
            fuentes.setdefault(familia, set()).add(fuente)
    return {f: len(s) for f, s in fuentes.items()}


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------

def construir_v3(web_ruta, libros_ruta, claves=None, extra_rutas=None,
                calidad_min=3, ruta_v2=None, catalogo=None):
    """Pipeline completo: reúne, calcula la matriz y los informes.

    Devuelve el dict que se vuelca a JSON.
    """
    if catalogo is None:
        catalogo = cobertura.entidades()
    evidencias, info = reunir_evidencias(web_ruta, libros_ruta, claves=claves,
                                       extra_rutas=extra_rutas)
    resultado = cobertura.calcular_cobertura(evidencias, catalogo=catalogo,
                                            calidad_min=calidad_min)
    resumen = cobertura.resumen_por_familia(resultado, catalogo)
    comparacion = comparar_v2_v3(resultado["celdas"], ruta_v2)
    fuentes_familia = ritmo_observado_por_familia(evidencias, catalogo,
                                                 calidad_min=calidad_min)
    estimacion = estimacion_meta_por_familia(resultado["celdas"], catalogo)
    for familia, datos in estimacion.items():
        n_fuentes = fuentes_familia.get(familia, 0)
        if n_fuentes and datos["completas"]:
            ritmo = datos["completas"] / n_fuentes
            datos["fuentes_distintas_aportadas"] = n_fuentes
            datos["ritmo_completas_por_fuente"] = round(ritmo, 4)
            if datos["celdas_faltantes"]:
                datos["fuentes_ritmo"] = math.ceil(
                    datos["celdas_faltantes"] / ritmo)
            else:
                datos["fuentes_ritmo"] = 0
        else:
            datos["fuentes_distintas_aportadas"] = n_fuentes
            datos["ritmo_completas_por_fuente"] = None
            datos["fuentes_ritmo"] = None
    return {
        "resumen": {
            "total_celdas": len(resultado["celdas"]),
            "completas": resultado["completas"],
            "ignoradas": resultado["ignoradas"],
            "calidad_min": calidad_min,
            "por_familia": resumen,
            "evidencias": info,
        },
        "comparacion_v2": comparacion,
        "huecos": {
            "top_entidades": top_entidades_incompletas(resultado["celdas"],
                                                     catalogo),
            "dominios_top": dominios_top_por_familia(evidencias, catalogo,
                                                    calidad_min=calidad_min),
            "estimacion_10pct": estimacion,
        },
        "celdas": resultado["celdas"],
    }


def _pct(valor):
    return f"{valor:.1f}".replace(".", ",") + " %"


def escribir_json(datos, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.write("\n")


def escribir_md(datos, ruta, max_lista=40):
    resumen = datos["resumen"]
    total = resumen["total_celdas"]
    completas = resumen["completas"]
    pct = round(100.0 * completas / total, 1) if total else 0.0
    lineas = [
        "# Matriz de cobertura v3 (evidencias vigentes)",
        "",
        f"- Total de celdas: {total}",
        f"- Celdas completas: {completas} ({_pct(pct)})",
        f"- Calidad mínima: {resumen['calidad_min']}",
        f"- Evidencias ignoradas (entidad/faceta fuera de catálogo): {resumen['ignoradas']}",
        "",
        "## Orígenes reunidos",
        "",
        "| Origen | Ruta | Leídas |",
        "|---|---|---|",
    ]
    for etiqueta, origen in resumen["evidencias"]["origenes"].items():
        rutas = origen.get("rutas") or [origen.get("ruta", "")]
        lineas.append(f"| {etiqueta} | {'; '.join(rutas)} | "
                     f"{origen.get('leidas', 0)} |")
    lineas.append("")
    lineas.append(f"- Claves de consenso excluidas: "
                 f"{resumen['evidencias']['claves_cargadas']} cargadas, "
                 f"{resumen['evidencias']['excluidas']} evidencias excluidas")
    lineas += [
        "",
        "## Resumen por familia",
        "",
        "| Familia | Celdas | Completas | % completas |",
        "|---|---|---|---|",
    ]
    for nombre, d in resumen["por_familia"].items():
        lineas.append(f"| {nombre} | {d['celdas']} | {d['completas']} "
                     f"| {_pct(d['porcentaje'])} |")
    comp = datos.get("comparacion_v2", {})
    lineas += ["", "## Comparación con la v2", ""]
    if not comp.get("disponible"):
        lineas.append("Matriz v2 no disponible; sin comparación.")
    else:
        lineas += [
            f"- Completas v2: {comp.get('v2_completas')} -> v3: "
            f"{comp.get('v3_completas')}",
            f"- Pasan a completas: {len(comp['pasan_a_completas'])}",
            f"- Dejan de serlo: {len(comp['dejan_de_serlo'])}",
            "",
            "### Pasan a completas",
            "",
        ]
        for c in comp["pasan_a_completas"][:max_lista]:
            lineas.append(f"- `{c['entidad_id']}` · {c['faceta']} "
                         f"(f={c['n_fuentes']}, cl={c['n_clasicas']}, "
                         f"mo={c['n_modernas']}, es={c['n_es']})")
        if len(comp["pasan_a_completas"]) > max_lista:
            lineas.append(f"- ... y {len(comp['pasan_a_completas']) - max_lista} más.")
        lineas += ["", "### Dejan de ser completas (y por qué)", ""]
        for c in comp["dejan_de_serlo"][:max_lista]:
            lineas.append(f"- `{c['entidad_id']}` · {c['faceta']}: "
                         + "; ".join(c["motivo"]))
        if len(comp["dejan_de_serlo"]) > max_lista:
            lineas.append(f"- ... y {len(comp['dejan_de_serlo']) - max_lista} más.")
    lineas += ["", "## Informe de huecos por familia", ""]
    nombre_fam = dict(zip(cobertura._NOMBRE_FAMILIA.keys(),
                         cobertura._NOMBRE_FAMILIA.values()))
    huecos = datos["huecos"]
    for familia, entradas in huecos["top_entidades"].items():
        etiqueta = nombre_fam.get(familia, familia)
        lineas += [
            f"### {etiqueta}: entidades con más celdas incompletas",
            "",
            "| Entidad | Incompletas | Falt. indep. | Falt. clásicas | "
            "Falt. modernas | Falt. ES |",
            "|---|---|---|---|---|---|",
        ]
        for d in entradas:
            lineas.append(
                f"| {d['nombre']} (`{d['entidad_id']}`) | "
                f"{d['celdas_incompletas']} | {d['falta_independientes']} | "
                f"{d['falta_clasicas']} | {d['falta_modernas']} | "
                f"{d['falta_es']} |")
        lineas += ["", f"Dominios que más aportan ({etiqueta}):", ""]
        for d in huecos["dominios_top"].get(familia, []):
            lineas.append(f"- {d['dominio']}: {d['n_evidencias']} evidencias, "
                         f"{d['n_entidades']} entidades")
        est = huecos["estimacion_10pct"].get(familia, {})
        ritmo = est.get("ritmo_completas_por_fuente")
        lineas += [
            "",
            f"Estimación para el 10 % de celdas completas ({etiqueta}):",
            "",
            f"- Meta: {est.get('meta_completas')} completas "
            f"(hay {est.get('completas')}; faltan {est.get('celdas_faltantes')})",
            f"- Fuentes nuevas (método T43, arreglando lo más barato primero): "
            f"{est.get('fuentes_ideales')}",
            f"- Fuentes distintas aportadas en la pasada actual: "
            f"{est.get('fuentes_distintas_aportadas')}",
            f"- Ritmo observado: {ritmo if ritmo is not None else 'sin datos'} "
            f"celdas completas por fuente",
            f"- Fuentes al ritmo observado: "
            f"{est.get('fuentes_ritmo') if est.get('fuentes_ritmo') is not None else 'sin datos'}",
            f"- Fuentes para arreglar todas las incompletas: "
            f"{est.get('fuentes_total_arreglar')}",
            "",
        ]
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cobertura v3: matriz reproducible con evidencias vigentes.")
    parser.add_argument("--web", default=RUTAS["web"],
                       help="JSONL de evidencias web")
    parser.add_argument("--libros", choices=["limpio", "crudo"], default="limpio",
                       help="evidencias de libros: limpias (T71) o crudas")
    parser.add_argument("--libros-limpio", default=RUTAS["libros_limpio"])
    parser.add_argument("--libros-crudo", default=RUTAS["libros_crudo"])
    parser.add_argument("--excluir-claves", default=RUTAS["claves_excluir"],
                       help="JSONL de claves de consenso a excluir")
    parser.add_argument("--sin-excluir-claves", action="store_true",
                       help="no aplicar la exclusión de claves")
    parser.add_argument("--extra", nargs="*", default=None,
                       help="JSONL adicionales de evidencias")
    parser.add_argument("--v2", default=RUTAS["v2"],
                       help="matriz v2 para la comparación")
    parser.add_argument("--out-dir", default=RUTAS["out_dir"])
    parser.add_argument("--calidad-min", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true",
                       help="imprime el resumen sin escribir ficheros")
    args = parser.parse_args(argv)

    libros_ruta = (args.libros_limpio if args.libros == "limpio"
                  else args.libros_crudo)
    claves = None if args.sin_excluir_claves else cargar_claves_exclusion(
        args.excluir_claves)
    datos = construir_v3(args.web, libros_ruta, claves=claves,
                        extra_rutas=args.extra, calidad_min=args.calidad_min,
                        ruta_v2=args.v2)
    resumen = datos["resumen"]
    if args.dry_run:
        print(f"Cobertura v3 (simulación): {resumen['completas']} de "
              f"{resumen['total_celdas']} celdas completas; "
              f"ignoradas: {resumen['ignoradas']}")
        for nombre, d in resumen["por_familia"].items():
            print(f"  {nombre}: {d['completas']}/{d['celdas']} "
                  f"({_pct(d['porcentaje'])})")
        comp = datos["comparacion_v2"]
        if comp.get("disponible"):
            print(f"  vs v2: +{len(comp['pasan_a_completas'])} pasan, "
                  f"-{len(comp['dejan_de_serlo'])} dejan de serlo")
        return 0
    os.makedirs(args.out_dir, exist_ok=True)
    json_out = os.path.join(args.out_dir, "cobertura_total_v3.json")
    md_out = os.path.join(args.out_dir, "cobertura_total_v3.md")
    escribir_json(datos, json_out)
    escribir_md(datos, md_out)
    print(f"Cobertura v3 escrita en {json_out} y {md_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
