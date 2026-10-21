#!/usr/bin/env python3
"""Comparativa del consenso local vs Mercury 3 (T76).

Toma celdas ya resueltas por el nodo local (``consenso_kb.py``), reconstruye
sus afirmaciones de entrada con las mismas funciones de ``consenso_kb``
(``normalizar_afirmaciones`` / ``agrupar_en_celdas`` sobre las afirmaciones
de web y de libros), recupera el agrupamiento local exacto desde la caché de
equivalencias (lo que garantiza que la entrada reconstruida coincide bit a bit
con la que vio el nodo local) y ejecuta ``agrupar_celda`` con un cliente
apuntado a Inception Mercury 3.

Compara por celda:

* nº de mayoritarias / discrepancias / únicas derivadas de cada partición,
* acuerdo de partición (índice de Rand ajustado, ARI),
* pares que el nodo local fusionó y Mercury no (y al revés), con ejemplos,
* errores de formato/validación (caída segura ``fallback``) y latencia.

Escribe /Users/angelgonzalez/fase0/comparativa_consenso.md con la conclusión:
¿acuerdo suficiente (ARI medio >= 0,85) para delegar el consenso restante en
Mercury, y con qué parámetros? Estima horas ahorradas sobre las celdas
pendientes.

La clave de la API se lee en tiempo de ejecución de la variable de entorno
``INCEPTION_API_KEY`` o, en su defecto, de ``~/.local/share/opencode/auth.json``
(entrada ``inception``). Nunca se escribe en este fichero ni en los logs.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from statistics import mean, median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import consenso_kb as ck  # noqa: E402
from llm_client import LLMClient  # noqa: E402

BACKEND_URL = "https://api.inceptionlabs.ai/v1"
BACKEND_MODEL = "mercury-3"
API_KEY_ENV = "INCEPTION_API_KEY"
AUTH_FILE = os.path.expanduser("~/.local/share/opencode/auth.json")
AUTH_ENTRY = "inception"

REASONING_EFFORT = "instant"
MAX_COMPLETION_TOKENS = 8192
TASA_MAX_POR_MINUTO = 60
TIMEOUT_S = 120.0

FASE0 = "/Users/angelgonzalez/fase0"
CONSENSO_LOCAL = os.path.join(FASE0, "consenso_kb/consenso.jsonl")
CACHE_EQUIV = os.path.join(FASE0, "consenso_kb/cache_equivalencia.jsonl")
WEB_AFIRMACIONES = os.path.join(FASE0, "afirmaciones_full/afirmaciones.jsonl")
LIBROS_AFIRMACIONES = os.path.join(
    FASE0, "afirmaciones_libros/afirmaciones_libros.jsonl")
INFORME = os.path.join(FASE0, "comparativa_consenso.md")

N_CELDAS = 40
SEMILLA = 76
MIN_FUENTES = 2
MIN_AFIRMACIONES = 8
UMBRAL_ACUERDO = 0.85

# Velocidad documentada del nodo local para la estimación de horas (T76:
# ~1-3 celdas/min con los nodos ocupados). Se usa el extremo conservador.
CELDAS_POR_MINUTO_LOCAL = 1.0

EJEMPLOS_MAX = 10


def cargar_clave_inception():
    """Devuelve la clave de Inception sin exponerla: env primero, auth.json después."""
    clave = os.environ.get(API_KEY_ENV)
    if clave:
        return clave
    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            auth = json.load(f)
        entrada = auth.get(AUTH_ENTRY) or {}
        clave = entrada.get("key")
    except (OSError, json.JSONDecodeError):
        clave = None
    if not clave:
        raise RuntimeError(
            "No hay clave para %s: define %s o la entrada %r en %s"
            % (BACKEND_MODEL, API_KEY_ENV, AUTH_ENTRY, AUTH_FILE))
    os.environ[API_KEY_ENV] = clave
    return clave


def crear_cliente_mercury(metricas=None):
    """LLMClient apuntando a Mercury 3 con los parámetros de T68."""
    cargar_clave_inception()
    return LLMClient(
        endpoints=[{
            "url": BACKEND_URL,
            "model": BACKEND_MODEL,
            "api_key_env": API_KEY_ENV,
        }],
        reasoning_effort=REASONING_EFFORT,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        max_concurrencia=1,
        tasa_max_por_minuto=TASA_MAX_POR_MINUTO,
        timeout=TIMEOUT_S,
        metricas=metricas,
    )


def _leer_jsonl(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            s = linea.strip()
            if not s:
                continue
            try:
                yield json.loads(s)
            except json.JSONDecodeError:
                continue


def cargar_consenso_local(ruta=CONSENSO_LOCAL):
    """Registros de consenso del nodo local, por (entidad_id, faceta)."""
    out = {}
    for reg in _leer_jsonl(ruta):
        try:
            out[(reg["entidad_id"], reg["faceta"])] = reg
        except KeyError:
            continue
    return out


def cargar_cache_equivalencias(ruta=CACHE_EQUIV):
    """Respuestas de agrupamiento locales indexadas por clave de entrada."""
    out = {}
    for reg in _leer_jsonl(ruta):
        try:
            out[reg["clave"]] = reg["respuesta"]
        except KeyError:
            continue
    return out


def reconstruir_celdas(web=WEB_AFIRMACIONES, libros=LIBROS_AFIRMACIONES):
    """Reconstruye las celdas de entrada tal y como las vio el nodo local."""
    corr = ck.cargar_correspondencias()
    regs = []
    for ruta in (web, libros):
        if ruta and os.path.exists(ruta):
            regs.extend(_leer_jsonl(ruta))
    utiles, _ = ck.normalizar_afirmaciones(regs, corr)
    return ck.agrupar_en_celdas(utiles)


def familia_de(entidad_id):
    if entidad_id.startswith("naipe-"):
        return "naipe"
    if entidad_id.startswith("tarot-"):
        return "tarot"
    partes = entidad_id.split("|")
    if len(partes) == 2:
        return partes[1]
    if len(partes) == 3:
        return partes[2]
    return "otra"


def clave_local(esperada_cache, clave, regs_celda):
    """Clave de caché que el nodo local usó para esta celda (entrada exacta)."""
    textos = [r["afirmacion"] for r in regs_celda][:ck.MAX_POR_CELDA]
    k = ck.CacheEquivalencia.clave(clave[0], clave[1], textos)
    if k in esperada_cache:
        return k, textos
    return None, textos


def seleccionar_celdas(consenso, celdas, cache, n=N_CELDAS, semilla=SEMILLA):
    """Selecciona ``n`` celdas procesadas: >=2 fuentes, afirmaciones suficientes,
    agrupamiento local recuperable de la caché y mezcla de familias.

    Devuelve una lista de dicts con clave, regs, textos y respuesta local.
    """
    candidatos = {}
    for clave, reg in consenso.items():
        if int(reg.get("n_afirmaciones") or 0) < MIN_AFIRMACIONES:
            continue
        regs_celda = celdas.get(clave)
        if not regs_celda:
            continue
        fuentes = {r.get("fuente_id") for r in regs_celda}
        if len(fuentes) < MIN_FUENTES:
            continue
        k, textos = clave_local(cache, clave, regs_celda)
        if k is None or len(textos) < 2:
            continue
        local = cache[k]
        if not isinstance(local, dict) or "grupos" not in local:
            continue
        candidatos[clave] = {
            "clave": clave,
            "familia": familia_de(clave[0]),
            "regs": regs_celda,
            "textos": textos,
            "local": local,
        }
    por_familia = {}
    for clave, c in candidatos.items():
        por_familia.setdefault(c["familia"], []).append(clave)
    rng = random.Random(semilla)
    for claves in por_familia.values():
        rng.shuffle(claves)
    seleccion = []
    familias = sorted(por_familia)
    rng.shuffle(familias)
    i = 0
    while len(seleccion) < n and familias:
        familias = [f for f in familias if por_familia[f]]
        if not familias:
            break
        f = familias[i % len(familias)]
        if por_familia[f]:
            seleccion.append(candidatos[por_familia[f].pop()])
        i += 1
    return seleccion


def ari(part_a, part_b):
    """Índice de Rand ajustado entre dos particiones del mismo conjunto 0..n-1."""
    n = 0
    vistos = set()
    for g in part_a:
        for i in g:
            vistos.add(i)
            n += 1
    if n < 2:
        return None
    combos_ab = Counter()
    tam_a = Counter()
    tam_b = Counter()
    pos_b = {}
    for gj, g in enumerate(part_b):
        for j in g:
            pos_b[j] = gj
    for gi, g in enumerate(part_a):
        for i in g:
            tam_a[gi] += 1
            if i in pos_b:
                combos_ab[(gi, pos_b[i])] += 1
    for gj, g in enumerate(part_b):
        tam_b[gj] += len(g)

    def c2(x):
        return x * (x - 1) // 2

    sum_ij = sum(c2(v) for v in combos_ab.values())
    sum_a = sum(c2(v) for v in tam_a.values())
    sum_b = sum(c2(v) for v in tam_b.values())
    total = c2(n)
    if total == 0:
        return None
    esperado = sum_a * sum_b / total
    maximo = 0.5 * (sum_a + sum_b)
    denom = maximo - esperado
    if denom == 0:
        return 1.0 if sum_ij == esperado else 0.0
    return (sum_ij - esperado) / denom


def pares_cocluster(particion):
    """Pares (i, j) con i < j que caen en el mismo grupo."""
    pares = set()
    for g in particion:
        for a in range(len(g)):
            for b in range(a + 1, len(g)):
                i, j = sorted((g[a], g[b]))
                pares.add((i, j))
    return pares


def contar_derivados(particion, contradicciones, regs):
    """Mayoritarias / únicas / discrepancias derivadas de una partición,
    replicando la lógica de ``construir_consensos`` (independencia por fuente)."""
    grupo_de = {}
    for gi, g in enumerate(particion):
        for i in g:
            grupo_de[i] = gi
    pares = set()
    for par in contradicciones or []:
        gi, gj = grupo_de.get(par[0]), grupo_de.get(par[1])
        if gi is None or gj is None or gi == gj:
            continue
        pares.add((min(gi, gj), max(gi, gj)))
    en_disc = {g for p in pares for g in p}
    mayoritarias = unicas = 0
    for gi, g in enumerate(particion):
        miembros = [regs[i] for i in g if i < len(regs)]
        if not miembros:
            continue
        fuentes = {m.get("fuente_id") for m in miembros}
        if len(fuentes) >= 2:
            mayoritarias += 1
        elif gi not in en_disc:
            unicas += 1
    return {
        "mayoritarias": mayoritarias,
        "unicas": unicas,
        "discrepancias": len(pares),
    }


def comparar_celda(sel, cliente, cache=None):
    """Compara una celda: ejecuta Mercury y mide acuerdo vs el local."""
    eid, faceta = sel["clave"]
    textos = sel["textos"]
    regs = sel["regs"]
    local = sel["local"]
    inicio = time.time()
    error = None
    try:
        mercury = ck.agrupar_celda(cliente, eid, faceta,
                                  [{"afirmacion": t} for t in textos])
    except Exception as exc:  # red u otros fallos: no tumbar la comparativa
        error = "%s: %s" % (type(exc).__name__, exc)
        mercury = None
    latencia = time.time() - inicio

    resultado = {
        "entidad_id": eid,
        "faceta": faceta,
        "familia": sel["familia"],
        "n_textos": len(textos),
        "latencia_s": round(latencia, 2),
        "error": error,
        "fallback_mercury": bool(mercury and mercury.get("fallback")),
    }
    if mercury is None or mercury.get("fallback"):
        resultado["ari"] = None
        return resultado

    resultado["ari"] = ari(local["grupos"], mercury["grupos"])
    resultado["local_derivados"] = contar_derivados(
        local["grupos"], local.get("contradicciones", []), regs)
    resultado["mercury_derivados"] = contar_derivados(
        mercury["grupos"], mercury.get("contradicciones", []), regs)

    co_local = pares_cocluster(local["grupos"])
    co_mercury = pares_cocluster(mercury["grupos"])
    resultado["pares_fusion_local_no_mercury"] = len(co_local - co_mercury)
    resultado["pares_fusion_mercury_no_local"] = len(co_mercury - co_local)
    resultado["ejemplos"] = []
    for (i, j) in sorted(co_local - co_mercury)[:EJEMPLOS_MAX]:
        resultado["ejemplos"].append({
            "tipo": "fusion_local_no_mercury",
            "i": i, "j": j,
            "texto_i": textos[i], "texto_j": textos[j],
        })
    for (i, j) in sorted(co_mercury - co_local)[:EJEMPLOS_MAX]:
        resultado["ejemplos"].append({
            "tipo": "fusion_mercury_no_local",
            "i": i, "j": j,
            "texto_i": textos[i], "texto_j": textos[j],
        })
    return resultado


def ejecutar_comparacion(seleccion, cliente):
    resultados = []
    for sel in seleccion:
        resultados.append(comparar_celda(sel, cliente))
    return resultados


def resumir(resultados, pendientes_locales=None):
    aris = [r["ari"] for r in resultados if r.get("ari") is not None]
    con_error = [r for r in resultados if r.get("error")]
    fallbacks = [r for r in resultados if r.get("fallback_mercury")]
    latencias = [r["latencia_s"] for r in resultados
                if not r.get("error") and r.get("ari") is not None]
    resumen = {
        "total": len(resultados),
        "comparables": len(aris),
        "errores": len(con_error),
        "fallbacks": len(fallbacks),
        "ari_medio": mean(aris) if aris else None,
        "ari_mediana": median(aris) if aris else None,
        "celdas_ari_85": sum(1 for a in aris if a >= UMBRAL_ACUERDO),
        "pct_celdas_85": (100.0 * sum(1 for a in aris if a >= UMBRAL_ACUERDO)
                          / len(aris)) if aris else None,
        "latencia_media_s": mean(latencias) if latencias else None,
        "latencia_mediana_s": median(latencias) if latencias else None,
        "mayoritarias_local": sum(
            r.get("local_derivados", {}).get("mayoritarias", 0)
            for r in resultados),
        "mayoritarias_mercury": sum(
            r.get("mercury_derivados", {}).get("mayoritarias", 0)
            for r in resultados),
        "unicas_local": sum(
            r.get("local_derivados", {}).get("unicas", 0) for r in resultados),
        "unicas_mercury": sum(
            r.get("mercury_derivados", {}).get("unicas", 0) for r in resultados),
        "discrepancias_local": sum(
            r.get("local_derivados", {}).get("discrepancias", 0)
            for r in resultados),
        "discrepancias_mercury": sum(
            r.get("mercury_derivados", {}).get("discrepancias", 0)
            for r in resultados),
        "pendientes": pendientes_locales,
    }
    if resumen["ari_medio"] is not None:
        resumen["delegable"] = resumen["ari_medio"] >= UMBRAL_ACUERDO
        if pendientes_locales and latencias:
            horas_local = pendientes_locales * CELDAS_POR_MINUTO_LOCAL / 60.0
            seg_por_celda = resumen["latencia_media_s"]
            horas_mercury = pendientes_locales * seg_por_celda / 3600.0
            resumen["horas_locales_restantes"] = horas_local
            resumen["horas_mercury"] = horas_mercury
            resumen["horas_ahorradas"] = horas_local - horas_mercury
    return resumen


def escribir_informe(ruta, resumen, resultados):
    lineas = ["# T76 — ¿Puede Mercury 3 hacer el consenso?", ""]
    lineas.append("Comparación sobre celdas ya resueltas por el nodo local "
                 "(misma entrada reconstruida y verificada contra la caché de "
                 "equivalencias).")
    lineas.append("")
    lineas.append("## Resultados de la muestra")
    lineas.append("")
    lineas.append("- Celdas comparadas: %d (de %d seleccionadas)"
                  % (resumen["comparables"], resumen["total"]))
    lineas.append("- Errores de red/cliente: %d" % resumen["errores"])
    lineas.append("- Celdas en caída segura (JSON inválido): %d"
                  % resumen["fallbacks"])
    if resumen.get("ari_medio") is not None:
        lineas.append("- ARI medio (acuerdo de partición): **%.3f**"
                      % resumen["ari_medio"])
        lineas.append("- ARI mediano: %.3f" % resumen["ari_mediana"])
        lineas.append("- Celdas con ARI >= %.2f: %d (%.1f %%)"
                      % (UMBRAL_ACUERDO, resumen["celdas_ari_85"],
                         resumen["pct_celdas_85"]))
    lineas.append("- Latencia media por celda (Mercury): %s s | mediana: %s s"
                  % (("%.1f" % resumen["latencia_media_s"])
                     if resumen.get("latencia_media_s") else "n/d",
                     ("%.1f" % resumen["latencia_mediana_s"])
                     if resumen.get("latencia_mediana_s") else "n/d"))
    lineas.append("")
    lineas.append("### Recuentos derivados (toda la muestra)")
    lineas.append("")
    lineas.append("| Métrica | Nodo local | Mercury 3 |")
    lineas.append("|---|---|---|")
    lineas.append("| Grupos mayoritarios (2+ fuentes) | %d | %d |"
                  % (resumen["mayoritarias_local"],
                     resumen["mayoritarias_mercury"]))
    lineas.append("| Afirmaciones de una sola fuente | %d | %d |"
                  % (resumen["unicas_local"], resumen["unicas_mercury"]))
    lineas.append("| Discrepancias | %d | %d |"
                  % (resumen["discrepancias_local"],
                     resumen["discrepancias_mercury"]))
    lineas.append("")
    lineas.append("## Ejemplos revisables de diferencias de fusión")
    lineas.append("")
    por_celda = []
    for r in resultados:
        exs = r.get("ejemplos", [])
        if exs:
            celda = "%s / %s" % (r["entidad_id"], r["faceta"])
            por_celda.append((celda, exs))
    ejemplos = []
    i = 0
    while any(len(exs) > i for _, exs in por_celda):
        for celda, exs in por_celda:
            if i < len(exs):
                e = dict(exs[i])
                e["celda"] = celda
                ejemplos.append(e)
        i += 1
    if not ejemplos:
        lineas.append("(sin diferencias de fusión en la muestra)")
    for e in ejemplos[:EJEMPLOS_MAX]:
        etiqueta = ("El nodo local fusionó y Mercury no"
                   if e["tipo"] == "fusion_local_no_mercury"
                   else "Mercury fusionó y el nodo local no")
        lineas.append("- **%s** (%s)" % (e["celda"], etiqueta))
        lineas.append("  - [%d] %s" % (e["i"], e["texto_i"]))
        lineas.append("  - [%d] %s" % (e["j"], e["texto_j"]))
    lineas.append("")
    lineas.append("## Conclusión")
    lineas.append("")
    if resumen.get("ari_medio") is None:
        lineas.append("Sin datos comparables: no se puede concluir.")
    elif resumen.get("delegable"):
        lineas.append(
            "**Sí**: el acuerdo de partición (%.3f) supera el umbral del %.0f %% "
            "exigido. Mercury 3 con `reasoning_effort=\"instant\"` y "
            "`max_completion_tokens=%d` agrupa las afirmaciones de forma "
            "equivalente al nodo local, con una latencia de ~%.1f s por celda "
            "frente a ~%.0f min/celda del nodo local."
            % (resumen["ari_medio"], UMBRAL_ACUERDO * 100,
               MAX_COMPLETION_TOKENS,
               resumen.get("latencia_media_s") or 0.0,
               1.0 / CELDAS_POR_MINUTO_LOCAL))
        if resumen.get("horas_ahorradas") is not None:
            lineas.append("")
            lineas.append(
                "- Celdas pendientes estimadas: %d" % resumen["pendientes"])
            lineas.append("- Horas restantes en el nodo local: ~%.1f h"
                          % resumen["horas_locales_restantes"])
            lineas.append("- Horas estimadas en Mercury: ~%.1f h"
                          % resumen["horas_mercury"])
            lineas.append("- **Horas ahorradas: ~%.1f h**"
                         % resumen["horas_ahorradas"])
        lineas.append("")
        lineas.append(
            "Parámetros recomendados para delegar: endpoint %s, modelo `%s`, "
            "`reasoning_effort=\"instant\"`, `max_completion_tokens=%d`, "
            "temperatura y validación de partición sin cambios (las de "
            "`consenso_kb.py`), concurrencia 1 y tasa <= %d peticiones/min."
            % (BACKEND_URL, BACKEND_MODEL, MAX_COMPLETION_TOKENS,
               TASA_MAX_POR_MINUTO))
    else:
        lineas.append(
            "**No**: el acuerdo de partición (%.3f) queda por debajo del umbral "
            "del %.0f %%. Mercury 3 no es fiable para delegar el consenso "
            "con estos parámetros; revisar los ejemplos de divergencia arriba."
            % (resumen["ari_medio"], UMBRAL_ACUERDO * 100))
        if resumen.get("pendientes"):
            lineas.append("")
            lineas.append(
                "- Celdas pendientes estimadas: %d. Al no recomendarse la "
                "delegación, el ahorro de horas es nulo: debe terminarlas el "
                "nodo local (~%.1f h restantes)."
                % (resumen["pendientes"],
                   resumen["pendientes"] * CELDAS_POR_MINUTO_LOCAL / 60.0))
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main(argv=None, cliente=None):
    parser = argparse.ArgumentParser(
        description="Comparativa consenso local vs Mercury 3 (T76)")
    parser.add_argument("--n-celdas", type=int, default=N_CELDAS)
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--consenso", default=CONSENSO_LOCAL)
    parser.add_argument("--cache", default=CACHE_EQUIV)
    parser.add_argument("--web", default=WEB_AFIRMACIONES)
    parser.add_argument("--libros", default=LIBROS_AFIRMACIONES)
    parser.add_argument("--informe", default=INFORME)
    parser.add_argument("--simulado", action="store_true",
                       help="Cliente simulado (sin red) para pruebas humo")
    parser.add_argument("--desde-json", default=None,
                       help="Regenera el informe desde un vuelco de resultados "
                           "previo sin volver a llamar a la API")
    args = parser.parse_args(argv)

    if args.desde_json:
        with open(args.desde_json, "r", encoding="utf-8") as f:
            vuelco = json.load(f)
        escribir_informe(args.informe, vuelco["resumen"],
                        vuelco["resultados"])
        print("Informe regenerado desde %s" % args.desde_json)
        return vuelco["resumen"]

    consenso = cargar_consenso_local(args.consenso)
    cache = cargar_cache_equivalencias(args.cache)
    celdas = reconstruir_celdas(args.web, args.libros)
    seleccion = seleccionar_celdas(consenso, celdas, cache,
                                  n=args.n_celdas, semilla=args.semilla)
    print("Celdas procesadas localmente: %d | seleccionadas: %d"
          % (len(consenso), len(seleccion)))
    if not seleccion:
        print("Sin celdas elegibles; nada que comparar.")
        return {"total": 0}

    if cliente is None:
        if args.simulado:
            cliente = LLMClient(simulado=ck._simulado_consenso)
        else:
            cliente = crear_cliente_mercury()

    resultados = ejecutar_comparacion(seleccion, cliente)
    pendientes = max(len(celdas) - len(consenso), 0)
    resumen = resumir(resultados, pendientes_locales=pendientes)
    vuelco = args.informe + ".resultados.json"
    with open(vuelco, "w", encoding="utf-8") as f:
        json.dump({"resumen": resumen, "resultados": resultados}, f,
                  ensure_ascii=False, indent=1)
    escribir_informe(args.informe, resumen, resultados)
    print("ARI medio: %s | comparables: %d | errores: %d | fallbacks: %d"
          % (("%.3f" % resumen["ari_medio"])
             if resumen.get("ari_medio") is not None else "n/d",
             resumen["comparables"], resumen["errores"], resumen["fallbacks"]))
    print("Informe en %s" % args.informe)
    return resumen


if __name__ == "__main__":
    main()
