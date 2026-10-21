#!/usr/bin/env python3
"""Comparativa de backends para extracción de afirmaciones (T65).

Toma evidencias ya procesadas por el nodo local (60 web + 40 libros) y
reejecuta la extracción con el backend rápido (Inception Mercury 3), usando
EXACTAMENTE los mismos prompts y validadores de afirmaciones_es.py /
afirmaciones_libros.py (importados, sin modificar). Compara número de
afirmaciones, solapamiento (equivalencia aproximada por entidad + faceta +
texto normalizado), tasa de descartes por los validadores existentes
(otra_carta, vocabulario, exceso, …), JSON inválido, latencia media y tokens.
Escribe /Users/angelgonzalez/fase0/comparativa_backends.md.

La clave de la API se lee en tiempo de ejecución de la variable de entorno
`INCEPTION_API_KEY`; nunca se escribe en este fichero.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

WORKTREE = "/Users/angelgonzalez/adivinacion-ia/.worktrees/t65-backend-rapido"
CORPUS = os.path.join(WORKTREE, "finetune/corpus")
CORPUS_LIBROS = (
    "/Users/angelgonzalez/adivinacion-ia/.worktrees/"
    "t38-afirmaciones-libros/finetune/corpus"
)

# La versión local de llm_client/afirmaciones_es debe tener prioridad.
sys.path.insert(0, CORPUS_LIBROS)
sys.path.insert(0, CORPUS)

import cartas  # noqa: E402
import afirmaciones_es as es  # noqa: E402
from afirmaciones_libros import IndiceLibros, extraer_afirmaciones_libros  # noqa: E402
from consenso_kb import cargar_correspondencias  # noqa: E402
from llm_client import LLMClient  # noqa: E402

BACKEND_URL = "https://api.inceptionlabs.ai/v1"
BACKEND_MODEL = "mercury-3"
API_KEY_ENV = "INCEPTION_API_KEY"

FASE0 = "/Users/angelgonzalez/fase0"
WEB_EVIDENCIAS = os.path.join(FASE0, "evidencias_web/evidencias.jsonl")
WEB_PROCESADOS = os.path.join(FASE0, "afirmaciones_full/procesados.jsonl")
WEB_AFIRMACIONES = os.path.join(FASE0, "afirmaciones_full/afirmaciones.jsonl")
WEB_DIR = os.path.join(FASE0, "web")
LIBROS_EVIDENCIAS = os.path.join(FASE0, "libros/evidencias/evidencias.jsonl")
LIBROS_PROCESADOS = os.path.join(FASE0, "afirmaciones_libros/procesados.jsonl")
LIBROS_AFIRMACIONES = os.path.join(
    FASE0, "afirmaciones_libros/afirmaciones_libros.jsonl")
LIBROS_SECCIONES = os.path.join(FASE0, "libros/secciones")
INFORME = os.path.join(FASE0, "comparativa_backends.md")

N_WEB = 60
N_LIBROS = 40
CONCURRENCIA = 3
TASA_MAX_POR_MINUTO = 60
MAX_DISCREPANCIAS = 5


def cargar_jsonl(ruta):
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                filas.append(json.loads(linea))
            except ValueError:
                continue
    return filas


def clave(ev):
    return (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))


def seleccionar(evidencias, procesados, limite):
    hechas = {
        clave(p) for p in procesados
        if p.get("estado") == "ok"
        and int(p.get("n_afirmaciones") or 0) > 0
    }
    return [e for e in evidencias if clave(e) in hechas][:limite]


def indice_local(afirmaciones):
    """entidad+faceta+fuente -> lista de afirmaciones normalizadas."""
    idx = {}
    for r in afirmaciones:
        k = (r.get("entidad_id"), r.get("faceta"), r.get("fuente_id"))
        idx.setdefault(k, []).append(cartas.norm(r.get("afirmacion") or ""))
    return idx


def norm_set(textos):
    return {cartas.norm(t) for t in textos if t and cartas.norm(t)}


def procesar_evidencia(ev, tipo, cliente, indice_web, indice_libros, corr,
                       local_refs):
    """Ejecuta la extracción con el backend rápido y devuelve un dict."""
    entidad = ev.get("entidad_id")
    faceta = ev.get("faceta")
    texto = None
    idioma = ev.get("idioma")
    if tipo == "web":
        texto = indice_web.texto_por_hash(
            ev.get("dominio"), ev.get("fuente_id"), ev.get("hash_seccion"))
    else:
        sec = indice_libros.seccion(ev.get("fuente_id"),
                                    ev.get("hash_seccion"))
        texto = (sec or {}).get("texto")
    res = {"tipo": tipo, "entidad_id": entidad, "faceta": faceta,
           "fuente_id": ev.get("fuente_id"), "dominio": ev.get("dominio"),
           "n_local": len(local_refs), "estado": "sin_texto"}
    if texto is None or not str(texto).strip():
        return res
    if tipo == "web":
        ext = es.extraer_afirmaciones(cliente, entidad, faceta, texto)
        crudas = ext.get("afirmaciones") or []
        fast_norm = norm_set(crudas)
    else:
        ext = extraer_afirmaciones_libros(cliente, entidad, faceta, texto,
                                          idioma, corr)
        crudas = [a.get("afirmacion", "") for a in ext.get("afirmaciones") or []]
        fast_norm = norm_set(crudas)
    local_norm = norm_set(local_refs)
    res["estado"] = ext.get("estado")
    res["n_fast"] = len(fast_norm)
    res["fast_norm"] = fast_norm
    res["local_norm"] = local_norm
    res["solape"] = len(fast_norm & local_norm)
    res["descartadas"] = ext.get("descartadas") or []
    return res


def _ratio(solape, base):
    return (solape / base) if base else 0.0


def main():
    if not os.environ.get(API_KEY_ENV):
        print("[comparativa] Falta %r en el entorno." % API_KEY_ENV,
              file=sys.stderr)
        return 1

    web_sel = seleccionar(cargar_jsonl(WEB_EVIDENCIAS),
                          cargar_jsonl(WEB_PROCESADOS), N_WEB)
    libros_sel = seleccionar(cargar_jsonl(LIBROS_EVIDENCIAS),
                             cargar_jsonl(LIBROS_PROCESADOS), N_LIBROS)
    web_local = indice_local(cargar_jsonl(WEB_AFIRMACIONES))
    libros_local = indice_local(cargar_jsonl(LIBROS_AFIRMACIONES))

    indice_web = es.IndiceWeb(WEB_DIR)
    indice_libros = IndiceLibros(LIBROS_SECCIONES)
    corr = cargar_correspondencias()

    metricas = {"peticiones": 0, "latencia_total": 0.0,
                "max_latencia": 0.0, "prompt_tokens": 0,
                "completion_tokens": 0}
    cliente = LLMClient(endpoints=[{
        "url": BACKEND_URL,
        "model": BACKEND_MODEL,
        "api_key_env": API_KEY_ENV,
    }], max_concurrencia=CONCURRENCIA,
       tasa_max_por_minuto=TASA_MAX_POR_MINUTO, metricas=metricas)

    resultados = []
    for tipo, sel, local in (("web", web_sel, web_local),
                             ("libros", libros_sel, libros_local)):
        for ev in sel:
            clave_local = (ev.get("entidad_id"), ev.get("faceta"),
                           ev.get("fuente_id"))
            refs = local.get(clave_local, [])
            resultados.append(procesar_evidencia(
                ev, tipo, cliente, indice_web, indice_libros, corr, refs))

    # Agregados
    def _nueva_stat():
        return {"procesadas": 0, "sin_texto": 0, "errores": 0,
                "n_local": 0, "n_fast": 0, "solape_abs": 0,
                "descartadas": Counter()}
    ag = {"web": _nueva_stat(), "libros": _nueva_stat(),
          "total": _nueva_stat()}
    for r in resultados:
        t = r["tipo"]
        s = ag[t]
        s["procesadas"] += 1
        if r["estado"] == "sin_texto":
            s["sin_texto"] += 1
            continue
        if r["estado"] == "error":
            s["errores"] += 1
        else:
            s["n_local"] += r["n_local"]
            s["n_fast"] += r["n_fast"]
            s["solape_abs"] += r["solape"]
        for _, motivo in r.get("descartadas", []):
            s["descartadas"][motivo] += 1

    total_sel = len(resultados)
    proc = sum(ag[t]["procesadas"] for t in ("web", "libros"))
    sin_t = sum(ag[t]["sin_texto"] for t in ("web", "libros"))
    err = sum(ag[t]["errores"] for t in ("web", "libros"))
    n_loc = sum(ag[t]["n_local"] for t in ("web", "libros"))
    n_fast = sum(ag[t]["n_fast"] for t in ("web", "libros"))
    solape = sum(ag[t]["solape_abs"] for t in ("web", "libros"))
    descartes = Counter()
    for t in ("web", "libros"):
        descartes.update(ag[t]["descartadas"])

    peticiones = metricas["peticiones"]
    lat_media = (metricas["latencia_total"] / peticiones) if peticiones else 0.0
    tokens_total = metricas["prompt_tokens"] + metricas["completion_tokens"]

    solape_si = _ratio(solape, n_loc) if n_loc else 0.0
    solape_fast = _ratio(solape, n_fast) if n_fast else 0.0
    error_rate = _ratio(err, proc) if proc else 0.0

    # Discrepancias representativas
    discrepancias = []
    for r in resultados:
        if r["estado"] == "sin_texto":
            continue
        if r["estado"] == "error":
            discrepancias.append((2.0, r, "error de extracción / JSON inválido"))
        else:
            rsi = _ratio(r["solape"], r["n_local"]) if r["n_local"] else 0.0
            if rsi < 0.6:
                discrepancias.append((1.0 - rsi, r, "solapamiento bajo"))
            elif abs(r["n_fast"] - r["n_local"]) >= 3:
                discrepancias.append(
                    (0.5, r, "diferencia de nº de afirmaciones"))
    discrepancias.sort(key=lambda x: -x[0])

    _escribir_informe(resultados, ag, web_sel, libros_sel,
                       lat_media, tokens_total, peticiones,
                       solape_si, solape_fast, error_rate,
                       n_loc, n_fast, solape, total_sel, proc,
                       sin_t, err, descartes,
                       discrepancias[:MAX_DISCREPANCIAS])
    return 0


def _fila_discrepancia(r, comentario):
    n_loc = r.get("n_local", 0)
    n_fast = r.get("n_fast", 0)
    if r["estado"] == "error":
        detalle = "-"
    else:
        solape = r.get("solape", 0)
        base = max(n_loc, 1)
        detalle = "%d/%d (%.0f%%)" % (solape, n_loc, 100.0 * solape / base)
    return ("| %s | %s | %s | %d | %d | %s | %s |"
            % (r["tipo"], r["entidad_id"], r["faceta"],
               n_loc, n_fast, detalle, comentario))


def _escribir_informe(resultados, ag, web_sel, libros_sel,
                       lat_media, tokens_total, peticiones,
                       solape_si, solape_fast, error_rate,
                       n_loc, n_fast, solape, total_sel, proc,
                       sin_t, err, descartes, discrepancias):
    lineas = []
    lineas.append("# Comparativa de backends para extracción de afirmaciones (T65)")
    lineas.append("")
    lineas.append("Backend rápido: Inception Mercury 3 (`mercury-3`) en `%s`, "
                  "autenticado con `Authorization: Bearer` desde la variable "
                  "de entorno `%s`." % (BACKEND_URL, API_KEY_ENV))
    lineas.append("")
    lineas.append("## Metodología")
    lineas.append("")
    lineas.append("- Evidencias ya procesadas por el nodo local (halogen en "
                  "10.0.0.3/10.0.0.4): %d web y %d libros, seleccionadas de "
                  "`afirmaciones_full/` y `afirmaciones_libros/` "
                  "(`estado=ok` y con afirmaciones)." % (len(web_sel), len(libros_sel)))
    lineas.append("- Se reejecuta la extracción con el backend rápido usando "
                  "EXACTAMENTE el mismo prompt y los mismos validadores de "
                  "`afirmaciones_es.py` / `afirmaciones_libros.py` "
                  "(importados, sin modificar).")
    lineas.append("- Equivalencia aproximada: entidad + faceta + texto "
                  "normalizado (`cartas.norm`).")
    lineas.append("")
    lineas.append("## Resultados globales")
    lineas.append("")
    lineas.append("| Métrica | Valor |")
    lineas.append("|---|---|")
    lineas.append("| Evidencias analizadas | %d |" % total_sel)
    lineas.append("| Con texto procesable | %d |" % proc)
    lineas.append("| Sin texto (sin_texto) | %d |" % sin_t)
    lineas.append("| Errores de extracción / JSON inválido | %d (%.1f%%) |"
                  % (err, 100.0 * error_rate))
    lineas.append("| Afirmaciones del nodo local (total) | %d |" % n_loc)
    lineas.append("| Afirmaciones del backend rápido (total) | %d |" % n_fast)
    lineas.append("| Solapamiento (coincidencias normalizadas) | %d |" % solape)
    lineas.append("| Solapamiento respecto al nodo local | %.1f%% |"
                  % (100.0 * solape_si))
    lineas.append("| Solapamiento respecto al backend rápido | %.1f%% |"
                  % (100.0 * solape_fast))
    lineas.append("| Peticiones de red | %d |" % peticiones)
    lineas.append("| Latencia media por petición | %.2f s |" % lat_media)
    lineas.append("| Tokens totales (prompt + completion) | %d |" % tokens_total)
    lineas.append("")

    lineas.append("### Descartes por validador (backend rápido)")
    lineas.append("")
    if descartes:
        lineas.append("| Motivo | N |")
        lineas.append("|---|---|")
        for motivo, n in sorted(descartes.items(), key=lambda kv: -kv[1]):
            lineas.append("| %s | %d |" % (motivo, n))
    else:
        lineas.append("(ninguno)")
    lineas.append("")

    lineas.append("### Desglose por tipo")
    lineas.append("")
    lineas.append("| Tipo | Procesadas | sin_texto | Errores | n_local | "
                  "n_fast | Solape |")
    lineas.append("|---|---|---|---|---|---|---|")
    for t in ("web", "libros"):
        s = ag[t]
        lineas.append("| %s | %d | %d | %d | %d | %d | %d |"
                      % (t, s["procesadas"], s["sin_texto"], s["errores"],
                         s["n_local"], s["n_fast"], s["solape_abs"]))
    lineas.append("")

    lineas.append("## Ejemplos de discrepancias")
    lineas.append("")
    if discrepancias:
        lineas.append("| Tipo | Entidad | Faceta | n_local | n_fast | "
                      "Solape | Comentario |")
        lineas.append("|---|---|---|---|---|---|---|")
        for _, r, comentario in discrepancias:
            lineas.append(_fila_discrepancia(r, comentario))
    else:
        lineas.append("No se registraron discrepancias significativas.")
    lineas.append("")

    # Conclusión
    conclusiones = []
    conclusiones.append("## Conclusión")
    conclusiones.append("")
    if error_rate > 0.3:
        conclusiones.append("El backend rápido **no es fiable** para la "
                            "extracción: %.0f%% de las evidencias acabaron en "
                            "error o JSON inválido." % (100.0 * error_rate))
    elif solape_si >= 0.7:
        conclusiones.append(
            "El backend rápido **sirve para extracción, con reservas**. "
            "Recupera un %.0f%% de las afirmaciones del nodo local "
            "(equivalencia normalizada) con una tasa de error baja (%.1f%%). "
            "Las reservas: (1) el número de afirmaciones extraídas difiere a "
            "veces del nodo local; (2) el solapamiento no es total, por lo "
            "que hay que conservar la deduplicación/consenso existente; "
            "(3) la latencia por petición (%.2f s) y el consumo de tokens son "
            "los costes a vigilar si se escala." % (
                100.0 * solape_si, 100.0 * error_rate, lat_media))
    elif solape_si >= 0.4:
        conclusiones.append(
            "El backend rápido **sirve de forma parcial**. El solapamiento "
            "con el nodo local es de un %.0f%%: capta una parte relevante "
            "pero no suficiente para sustituir al nodo local sin pérdida de "
            "cobertura. Conviene usarlo como segundo extractor y fusionar, "
            "no como sustituto." % (100.0 * solape_si))
    else:
        conclusiones.append(
            "El backend rápido **no sirve** para esta extracción: el "
            "solapamiento con el nodo local es de un %.0f%% y/o la tasa de "
            "errores es alta (%.1f%%)." % (
                100.0 * solape_si, 100.0 * error_rate))

    lineas.extend(conclusiones)
    lineas.append("")

    with open(INFORME, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))
    print("[comparativa] Informe escrito en %s" % INFORME)


if __name__ == "__main__":
    sys.exit(main())
