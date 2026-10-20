#!/usr/bin/env python3
"""Muestras aleatorias del 3 % por nivel para revisión humana (T48, F0.6).

Prepara la revisión humana previa a la fase 1 (punto 7 de
`docs/PLAN_ADQUISICION_CALIDAD.md`) y el conjunto de oro reutilizable.

Niveles y entradas (JSONL, bajo `--base`, por defecto `/Users/angelgonzalez/fase0`):
  - `web`:          `evidencias_web/evidencias.jsonl`
  - `libros`:       `libros/evidencias/*.jsonl`
  - `afirmaciones`: `afirmaciones_full/afirmaciones.jsonl` (si falta,
                    `afirmaciones/afirmaciones.jsonl`) y, si existe,
                    `afirmaciones_libros/afirmaciones_libros.jsonl`
  - `lecturas`:     `lecturas/lecturas.jsonl`

El muestreo es aleatorio reproducible (semilla fija) y estratificado por
familia (o sistema en lecturas) y calidad; los afirmaciones de libros
estratifican además por origen, porque libro y web son canales distintos.
Cada estrato con registros aporta mínimo 1 ficha y nunca se repite un id.

Salida de `--accion muestrear` (en `--out-dir`):
  - `muestras.md`:    fichas legibles, ordenadas por nivel y estrato, con
                      casillas de veredicto para el revisor humano.
  - `muestras.jsonl`: los mismos ids con metadatos, para volcar después
                      `muestras_revisadas.jsonl` (`id`, `veredicto`, `nota`).

Salida de `--accion oro` (a partir de `muestras_revisadas.jsonl`):
  - `oro.jsonl` / `rechazados.jsonl` con los registros «correcto» e
    «incorrecto», e `oro_informe.md` con la tasa de acierto por nivel y
    estrato frente al umbral (90 % por defecto) que decide si el nivel pasa.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import sys

import juez

BASE_POR_DEFECTO = "/Users/angelgonzalez/fase0"
NIVELES = ("web", "libros", "afirmaciones", "lecturas")
FRACCION_POR_DEFECTO = 0.03
SEMILLA_POR_DEFECTO = 42
UMBRAL_ORO = 0.90
LARGO_TEXTO = 600
VEREDICTOS = ("correcto", "dudoso", "incorrecto")


# ---------------------------------------------------------------------------
# Identificadores y estratos
# ---------------------------------------------------------------------------


def id_registro(registro):
    """Id determinista: el campo `id` si lo trae, si no sha256 canónico."""
    if registro.get("id"):
        return str(registro["id"])
    base = json.dumps(registro, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def familia_de(entidad_id):
    """Familia de una entidad: combinaciones, prefijo sin número, o ella."""
    eid = entidad_id or ""
    if "|" in eid:
        return "combinaciones"
    if "-" in eid and eid.rsplit("-", 1)[1].isdigit():
        return eid.rsplit("-", 1)[0]
    return eid or "sin-entidad"


def estrato_de(nivel, registro, origen=None):
    """Clave de estrato (tuple hashable) del registro según su nivel."""
    calidad = registro.get("calidad")
    calidad = "s/d" if calidad is None else str(calidad)
    if nivel == "lecturas":
        return (registro.get("sistema") or "sin-sistema", calidad)
    if nivel == "afirmaciones":
        return (origen or "web", familia_de(registro.get("entidad_id")),
                calidad)
    return (familia_de(registro.get("entidad_id")), calidad)


def _clave_estrato(estrato):
    return " · ".join(str(x) for x in estrato)


# ---------------------------------------------------------------------------
# Muestreo estratificado reproducible
# ---------------------------------------------------------------------------


def muestrear(registros, fraccion=FRACCION_POR_DEFECTO, estratos=None,
              semilla=SEMILLA_POR_DEFECTO):
    """Muestra aleatoria reproducible, estratificada, con mínimo 1 por estrato.

    `estratos` es una función `registro -> tuple` (por defecto, un solo
    estrato vacío). Deduplica por `id_registro` (nunca repite), agrupa por
    estrato y extrae `max(1, round(fraccion * n))` de cada estrato con
    registros, con un RNG sembrado por semilla y clave de estrato, sobre los
    ids ordenados: misma semilla y mismos registros dan siempre la misma
    selección, sea cual sea el orden de entrada.

    Devuelve `(seleccion, tamanos)`: `seleccion` es la lista de registros
    ordenada por (estrato, id) y `tamanos` un dict estrato -> tamaño real de
    la muestra en ese estrato.
    """
    clave = estratos or (lambda r: ())
    vistos = set()
    unicos = []
    for registro in registros:
        rid = id_registro(registro)
        if rid in vistos:
            continue
        vistos.add(rid)
        unicos.append((clave(registro), rid, registro))
    grupos = {}
    for estrato, rid, registro in unicos:
        grupos.setdefault(estrato, []).append((rid, registro))
    seleccion = []
    tamanos = {}
    for estrato in sorted(grupos, key=_clave_estrato):
        miembros = sorted(grupos[estrato], key=lambda x: x[0])
        n = len(miembros)
        k = min(n, max(1, int(round(fraccion * n))))
        rng = random.Random("%d|%s" % (semilla, _clave_estrato(estrato)))
        elegidos = rng.sample(range(n), k)
        for i in sorted(elegidos):
            seleccion.append(miembros[i][1])
        tamanos[estrato] = k
    return seleccion, tamanos


# ---------------------------------------------------------------------------
# Carga de niveles
# ---------------------------------------------------------------------------


def _leer_jsonl(ruta):
    registros = []
    with open(ruta, encoding="utf-8-sig") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                registro = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(registro, dict):
                registros.append(registro)
    return registros


def rutas_entradas(base, nivel):
    """Ficheros de entrada del nivel: lista de (ruta, origen)."""
    if nivel == "web":
        return [(os.path.join(base, "evidencias_web", "evidencias.jsonl"),
                 "web")]
    if nivel == "libros":
        patron = os.path.join(base, "libros", "evidencias", "*.jsonl")
        return sorted([(r, "libros") for r in glob.glob(patron)
                       if not os.path.basename(r).startswith("juicios")])
    if nivel == "afirmaciones":
        rutas = []
        full = os.path.join(base, "afirmaciones_full", "afirmaciones.jsonl")
        viejo = os.path.join(base, "afirmaciones", "afirmaciones.jsonl")
        if os.path.exists(full):
            rutas.append((full, "web"))
        elif os.path.exists(viejo):
            rutas.append((viejo, "web"))
        libros = os.path.join(base, "afirmaciones_libros",
                              "afirmaciones_libros.jsonl")
        if os.path.exists(libros):
            rutas.append((libros, "libros"))
        return rutas
    if nivel == "lecturas":
        return [(os.path.join(base, "lecturas", "lecturas.jsonl"), "lecturas")]
    raise ValueError("nivel desconocido: %r" % nivel)


def cargar_registros(base, nivel):
    """Registros del nivel, cada uno con `nivel`, `origen`, `id` y `estrato`."""
    salida = []
    for ruta, origen in rutas_entradas(base, nivel):
        for registro in _leer_jsonl(ruta):
            fila = dict(registro)
            fila["nivel"] = nivel
            fila["origen"] = origen
            fila["id"] = id_registro(registro)
            fila["estrato"] = estrato_de(nivel, registro, origen)
            salida.append(fila)
    return salida


# ---------------------------------------------------------------------------
# Resolución del texto de cada ficha
# ---------------------------------------------------------------------------


class Resolvedor:
    """Localiza el texto citable de cada registro (o None si no se encuentra).

    - Evidencias web: reutiliza `afirmaciones_es.IndiceWeb` sobre
      `<base>/web/<dominio>/*.md` (hash compatible con `juez`).
    - Evidencias de libros: hash de las secciones de
      `<base>/libros/secciones/<libro_id>.jsonl`.
    - Afirmaciones y lecturas: traen el texto inline.
    """

    def __init__(self, base):
        self.base = base
        self._indice_web = None
        self._secciones = {}

    def _web(self):
        if self._indice_web is None:
            import afirmaciones_es
            self._indice_web = afirmaciones_es.IndiceWeb(
                os.path.join(self.base, "web"))
        return self._indice_web

    def _por_hash_libro(self, libro_id):
        if libro_id not in self._secciones:
            mapa = {}
            ruta = os.path.join(self.base, "libros", "secciones",
                                "%s.jsonl" % libro_id)
            if os.path.exists(ruta):
                for sec in _leer_jsonl(ruta):
                    mapa[juez.hash_seccion(sec)] = sec
            self._secciones[libro_id] = mapa
        return self._secciones[libro_id]

    def seccion_web(self, registro):
        """Texto de la sección citada (o None) y no añade procedencia."""
        import afirmaciones_es
        return afirmaciones_es.texto_seccion(registro, self._web())

    def seccion_libro(self, registro):
        sec = self._por_hash_libro(registro.get("fuente_id", "")).get(
            registro.get("hash_seccion"))
        return sec

    def texto(self, nivel, registro):
        if nivel == "web":
            return self.seccion_web(registro)
        if nivel == "libros":
            sec = self.seccion_libro(registro)
            return (sec or {}).get("texto")
        if nivel == "afirmaciones":
            return registro.get("afirmacion")
        if nivel == "lecturas":
            return registro.get("texto")
        return None


def recortar(texto, largo=LARGO_TEXTO):
    """Texto plano recortado a ~`largo` caracteres, sin «(sin texto)» vacío."""
    if not texto or not str(texto).strip():
        return None
    limpio = " ".join(str(texto).split())
    if len(limpio) <= largo:
        return limpio
    return limpio[:largo].rstrip() + " […]"


def procedencia_de(nivel, registro, resolvedor):
    """Línea de procedencia legible: URL o libro/sección."""
    if nivel == "web":
        url = str(registro.get("fuente_id") or "fuente desconocida")
        dominio = registro.get("dominio")
        return url if not dominio or dominio in url else "%s (%s)" % (
            url, dominio)
    if nivel == "libros":
        libro = registro.get("fuente_id") or "libro desconocido"
        sec = resolvedor.seccion_libro(registro)
        if sec:
            titulo = " ".join(str(sec.get("titulo") or "").split())[:80]
            return "libro %s · sección %s — %s" % (libro,
                                                   sec.get("seccion"), titulo)
        return "libro %s · sección %s" % (
            libro, (registro.get("hash_seccion") or "?")[:12])
    if nivel == "afirmaciones":
        if registro.get("origen") == "libros" or not str(
                registro.get("fuente_id", "")).startswith("http"):
            return "libro %s" % (registro.get("fuente_id")
                                 or "desconocido")
        return registro.get("fuente_id") or "fuente desconocida"
    if nivel == "lecturas":
        libro = registro.get("titulo_libro") or registro.get("libro_id") or "?"
        autor = registro.get("autor")
        partes = ["%s (%s)" % (libro, autor) if autor else libro,
                  registro.get("fuente") or "?"]
        if registro.get("seccion") is not None:
            partes.append("sección %s" % registro["seccion"])
        return " · ".join(partes)
    return "?"


# ---------------------------------------------------------------------------
# Fichas y salida
# ---------------------------------------------------------------------------


def ficha_markdown(nivel, registro, resolvedor):
    """Ficha de revisión humana en Markdown para un registro muestreado."""
    texto = resolvedor.texto(nivel, registro)
    recorte = recortar(texto)
    estrato = _clave_estrato(registro.get("estrato", ()))
    lineas = ["### %s · %s" % (nivel, estrato), ""]
    lineas.append("- id: `%s`" % (registro.get("id") or id_registro(registro)))
    lineas.append("- procedencia: %s" % procedencia_de(nivel, registro,
                                                       resolvedor))
    entidad = registro.get("entidad_id") or registro.get("sistema") or "?"
    faceta = registro.get("faceta") or ""
    detalle = entidad if not faceta else "%s · %s" % (entidad, faceta)
    extras = []
    if registro.get("calidad") is not None:
        extras.append("calidad %s" % registro["calidad"])
    cartas = registro.get("cartas")
    if nivel == "lecturas" and isinstance(cartas, (list, tuple)) and cartas:
        extras.append("cartas: %s" % ", ".join(str(c) for c in cartas[:6]))
    if extras:
        detalle += " (%s)" % "; ".join(extras)
    lineas.append("- entidad/faceta: %s" % detalle)
    if nivel == "lecturas" and registro.get("pregunta"):
        lineas.append("- pregunta: %s" % recortar(registro["pregunta"], 200))
    if nivel == "afirmaciones" and registro.get("cita_original"):
        cita = recortar(registro["cita_original"], 200)
        lineas.append("- cita original: «%s»" % cita)
    lineas.append("- texto: %s" % ("«%s»" % recorte if recorte
                                   else "(sin texto)"))
    lineas.append("")
    lineas.append("  [ ] correcto   [ ] dudoso   [ ] incorrecto"
                  "   Nota: ___")
    lineas.append("")
    return "\n".join(lineas)


def escribir_muestras(base, niveles, fraccion, semilla, out_dir):
    """Genera `muestras.md` y `muestras.jsonl`; devuelve un resumen."""
    os.makedirs(out_dir, exist_ok=True)
    resolvedor = Resolvedor(base)
    ruta_md = os.path.join(out_dir, "muestras.md")
    ruta_jsonl = os.path.join(out_dir, "muestras.jsonl")
    resumen = {"niveles": {}, "total_registros": 0, "total_muestra": 0}
    with open(ruta_md, "w", encoding="utf-8") as md, \
            open(ruta_jsonl, "w", encoding="utf-8") as jl:
        cabecera = ["# Muestras para revisión humana (T48)", "",
                    "- Base: `%s`" % base,
                    "- Fracción: %g · Semilla: %d" % (fraccion, semilla),
                    "- Niveles: %s" % ", ".join(niveles), "", "## Recuentos",
                    ""]
        cuerpos = []
        registros_por_nivel = {}
        for nivel in niveles:
            registros = cargar_registros(base, nivel)
            vistos = set()
            unicos = []
            for fila in registros:
                if fila["id"] in vistos:
                    continue
                vistos.add(fila["id"])
                unicos.append(fila)
            registros_por_nivel[nivel] = unicos
        for nivel in niveles:
            registros = registros_por_nivel[nivel]
            seleccion, tamanos = muestrear(
                registros, fraccion=fraccion,
                estratos=lambda r: r["estrato"], semilla=semilla)
            resumen["niveles"][nivel] = {
                "total": len(registros), "muestra": len(seleccion),
                "estratos": {_clave_estrato(e): k
                             for e, k in sorted(tamanos.items(),
                                                key=lambda x:
                                                _clave_estrato(x[0]))},
            }
            resumen["total_registros"] += len(registros)
            resumen["total_muestra"] += len(seleccion)
            seleccion.sort(key=lambda r: (_clave_estrato(r["estrato"]),
                                          r["id"]))
            cuerpos.append("\n## Nivel %s (%d de %d registros)\n"
                           % (nivel, len(seleccion), len(registros)))
            for registro in seleccion:
                cuerpos.append(ficha_markdown(nivel, registro, resolvedor))
                fila = {
                    "id": registro["id"],
                    "nivel": nivel,
                    "origen": registro.get("origen"),
                    "estrato": list(registro["estrato"]),
                    "entidad_id": registro.get("entidad_id"),
                    "sistema": registro.get("sistema"),
                    "faceta": registro.get("faceta"),
                    "calidad": registro.get("calidad"),
                }
                jl.write(json.dumps(fila, ensure_ascii=False) + "\n")
        for nivel in niveles:
            info = resumen["niveles"][nivel]
            cabecera.append("- %s: %d de %d (%d estratos)"
                            % (nivel, info["muestra"], info["total"],
                               len(info["estratos"])))
        cabecera.append("- TOTAL: %d de %d" % (resumen["total_muestra"],
                                               resumen["total_registros"]))
        cabecera.append("")
        md.write("\n".join(cabecera) + "\n" + "\n".join(cuerpos))
    resumen["ruta_md"] = ruta_md
    resumen["ruta_jsonl"] = ruta_jsonl
    return resumen


# ---------------------------------------------------------------------------
# Conjunto de oro
# ---------------------------------------------------------------------------


def generar_oro(muestras_jsonl, revisadas_jsonl, out_dir, umbral=UMBRAL_ORO):
    """Separa el veredicto humano en `oro.jsonl` / `rechazados.jsonl` + informe.

    `revisadas_jsonl` tiene una fila por ficha revisada: `id`, `veredicto`
    (correcto/dudoso/incorrecto) y `nota` opcional. Los ids desconocidos se
    reportan con un error claro. La tasa de acierto por nivel y estrato es
    `correcto / (correcto + dudoso + incorrecto)`; el dudoso penaliza, porque
    todavía no es conocimiento fiable.
    """
    muestras = {r["id"]: r for r in _leer_jsonl(muestras_jsonl)}
    if not muestras:
        raise ValueError("no hay ids en %s; genera antes la muestra con "
                         "--accion muestrear" % muestras_jsonl)
    revisadas = _leer_jsonl(revisadas_jsonl)
    desconocidos = [r.get("id") for r in revisadas
                    if r.get("id") not in muestras]
    if desconocidos:
        ejemplo = ", ".join(str(d)[:12] for d in desconocidos[:3])
        raise ValueError("%d ids de %s no están en %s (ejemplos: %s)"
                         % (len(desconocidos), revisadas_jsonl,
                            muestras_jsonl, ejemplo))
    mal = [r for r in revisadas if r.get("veredicto") not in VEREDICTOS]
    if mal:
        raise ValueError("%d filas de %s tienen veredicto inválido "
                         "(usar: %s); primer id: %s"
                         % (len(mal), revisadas_jsonl, ", ".join(VEREDICTOS),
                            mal[0].get("id")))
    os.makedirs(out_dir, exist_ok=True)
    oro_ruta = os.path.join(out_dir, "oro.jsonl")
    rech_ruta = os.path.join(out_dir, "rechazados.jsonl")
    informe_ruta = os.path.join(out_dir, "oro_informe.md")
    cuentas = {}
    con_nota = {}
    for r in revisadas:
        meta = muestras[r["id"]]
        clave = (meta["nivel"], _clave_estrato(tuple(meta.get("estrato") or ())))
        acc = cuentas.setdefault(clave, {"correcto": 0, "dudoso": 0,
                                         "incorrecto": 0})
        acc[r["veredicto"]] += 1
        con_nota[r["id"]] = r.get("nota")
    for destino, veredicto in ((oro_ruta, "correcto"),
                               (rech_ruta, "incorrecto")):
        with open(destino, "w", encoding="utf-8") as fh:
            for r in revisadas:
                if r["veredicto"] != veredicto:
                    continue
                fila = dict(muestras[r["id"]])
                fila["nota"] = r.get("nota")
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    lineas = ["# Conjunto de oro: tasa de acierto por nivel y estrato", "",
              "- Revisadas: %d de %d fichas" % (len(revisadas), len(muestras)),
              "- Umbral: %g (tasa = correcto / todas las revisadas; el "
              "dudoso penaliza)" % umbral, "",
              "| nivel | estrato | correcto | dudoso | incorrecto | tasa "
              "| ≥ umbral |",
              "|---|---|---|---|---|---|---|"]
    por_nivel = {}
    for (nivel, estrato), c in sorted(cuentas.items()):
        total = sum(c.values())
        tasa = c["correcto"] / total if total else 0.0
        cumple = "sí" if tasa >= umbral else "NO"
        lineas.append("| %s | %s | %d | %d | %d | %.1f %% | %s |"
                      % (nivel, estrato, c["correcto"], c["dudoso"],
                         c["incorrecto"], 100 * tasa, cumple))
        pn = por_nivel.setdefault(nivel, {"correcto": 0, "dudoso": 0,
                                          "incorrecto": 0})
        for k, v in c.items():
            pn[k] += v
    lineas.append("")
    lineas.append("## Resumen por nivel")
    lineas.append("")
    for nivel in NIVELES:
        if nivel not in por_nivel:
            continue
        c = por_nivel[nivel]
        total = sum(c.values())
        tasa = c["correcto"] / total if total else 0.0
        estado = "supera" if tasa >= umbral else "NO ALCANZA"
        lineas.append("- %s: %d revisadas · tasa %.1f %% · %s el umbral"
                      % (nivel, total, 100 * tasa, estado))
    with open(informe_ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    return {"oro": oro_ruta, "rechazados": rech_ruta,
            "informe": informe_ruta,
            "por_nivel": {n: {"total": sum(c.values()),
                              "tasa": (c["correcto"] / sum(c.values())
                                       if sum(c.values()) else 0.0)}
                          for n, c in por_nivel.items()}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Muestras del 3 % para revisión humana y conjunto de oro "
                    "(T48).")
    parser.add_argument("--accion", choices=("muestrear", "oro"),
                        default="muestrear")
    parser.add_argument("--nivel", choices=NIVELES + ("todos",),
                        default="todos")
    parser.add_argument("--fraccion", type=float,
                        default=FRACCION_POR_DEFECTO)
    parser.add_argument("--semilla", type=int, default=SEMILLA_POR_DEFECTO)
    parser.add_argument("--base", default=BASE_POR_DEFECTO,
                        help="directorio raíz de los datos de la fase 0")
    parser.add_argument("--out-dir", dest="out_dir", default=None,
                        help="directorio de salida (por defecto "
                             "<base>/muestras)")
    parser.add_argument("--revisadas", default=None,
                        help="para --accion oro: JSONL con id, veredicto y "
                             "nota (por defecto <out-dir>/"
                             "muestras_revisadas.jsonl)")
    parser.add_argument("--umbral", type=float, default=UMBRAL_ORO)
    args = parser.parse_args(argv)

    out_dir = args.out_dir or os.path.join(args.base, "muestras")
    if args.accion == "muestrear":
        if not 0 < args.fraccion <= 1:
            parser.error("--fraccion debe estar en (0, 1]")
        niveles = NIVELES if args.nivel == "todos" else (args.nivel,)
        resumen = escribir_muestras(args.base, niveles, args.fraccion,
                                    args.semilla, out_dir)
        for nivel, info in resumen["niveles"].items():
            print("%s: %d de %d (%d estratos)" % (nivel, info["muestra"],
                                                  info["total"],
                                                  len(info["estratos"])))
        print("TOTAL: %d de %d" % (resumen["total_muestra"],
                                   resumen["total_registros"]))
        print("escrito: %s" % resumen["ruta_md"])
        print("escrito: %s" % resumen["ruta_jsonl"])
        return 0
    muestras_ruta = os.path.join(out_dir, "muestras.jsonl")
    revisadas_ruta = args.revisadas or os.path.join(
        out_dir, "muestras_revisadas.jsonl")
    informe = generar_oro(muestras_ruta, revisadas_ruta, out_dir,
                          umbral=args.umbral)
    for nivel, dato in informe["por_nivel"].items():
        print("%s: %d revisadas · tasa %.1f %% · umbral %g"
              % (nivel, dato["total"], 100 * dato["tasa"], args.umbral))
    print("escrito: %s" % informe["oro"])
    print("escrito: %s" % informe["rechazados"])
    print("escrito: %s" % informe["informe"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
