#!/usr/bin/env python3
"""Pasada masiva de extracción de afirmaciones con el backend rápido (T69).

Calcula las evidencias pendientes de `fase0/web` y `fase0/libros` cuya clave
(hash_seccion, entidad_id, faceta) no está en `afirmaciones_full/procesados.jsonl`
ni en `afirmaciones_libros/procesados.jsonl`, las envía al backend rápido de
Inception (Mercury 3) y escribe los resultados en directorios NUEVOS:

- /Users/angelgonzalez/fase0/afirmaciones_rapido/web/
- /Users/angelgonzalez/fase0/afirmaciones_rapido/libros/

Reutiliza EXACTAMENTE los prompts y validadores de `afirmaciones_es.py` y
`afirmaciones_libros.py` (importados, sin modificarlos) y añade a cada
afirmación y a cada registro de procesados el campo `origen: "mercury-3"`.

Comportamiento: reanudable por clave, concurrencia ≤ 3, control de tasa y
backoff ante 429 (los gestiona `LLMClient`), y parada si >20 % de errores en
una ventana de 50 evidencias consecutivas. La clave de la API se lee de la
variable de entorno `INCEPTION_API_KEY` y nunca se escribe en repo/logs.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from urllib.parse import urlparse

import afirmaciones_es as es
import afirmaciones_libros as al
from consenso_kb import cargar_correspondencias
from llm_client import LLMClient

BACKEND_URL = "https://api.inceptionlabs.ai/v1"
BACKEND_MODEL = "mercury-3"
API_KEY_ENV = "INCEPTION_API_KEY"

REASONING_EFFORT = "instant"
MAX_COMPLETION_TOKENS = 8192
MAX_TOKENS_DEFAULT = 4096

CONCURRENCIA = 3
TASA_MAX_POR_MINUTO = 60

VENTANA_ERRORES = 50
UMBRAL_ERRORES = 0.20

ORIGEN = "mercury-3"
TOKENS_ESTIMADOS_POR_EVIDENCIA = 1600

FASE0 = "/Users/angelgonzalez/fase0"
DEFAULT_WEB_EVIDENCIAS = os.path.join(FASE0, "evidencias_web/evidencias.jsonl")
DEFAULT_LIBROS_EVIDENCIAS = os.path.join(FASE0, "libros/evidencias/evidencias.jsonl")
DEFAULT_WEB_PROCESADOS = os.path.join(FASE0, "afirmaciones_full/procesados.jsonl")
DEFAULT_LIBROS_PROCESADOS = os.path.join(FASE0, "afirmaciones_libros/procesados.jsonl")
DEFAULT_WEB_DIR = os.path.join(FASE0, "web")
DEFAULT_LIBROS_SECCIONES = os.path.join(FASE0, "libros/secciones")
DEFAULT_COBERTURA = os.path.join(FASE0, "cobertura_total_v2.json")
DEFAULT_OUT_ROOT = os.path.join(FASE0, "afirmaciones_rapido")

DEFAULT_WEB_MIN_CALIDAD = 4
DEFAULT_LIBROS_MIN_CALIDAD = 3


def clave(ev):
    return (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))


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


def _calidad_num(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def filtrar_min_calidad(evidencias, min_calidad):
    if not min_calidad or min_calidad <= 0:
        return list(evidencias)
    return [e for e in evidencias
            if _calidad_num(e.get("calidad")) >= min_calidad]


def cargar_procesados_claves(*rutas):
    claves = set()
    for ruta in rutas:
        if not os.path.exists(ruta):
            continue
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                claves.add((d.get("hash_seccion"), d.get("entidad_id"),
                            d.get("faceta")))
    return claves


def seleccionar_pendientes(evidencias_web, evidencias_libros, procesados,
                           web_min_calidad, libros_min_calidad):
    pendientes = []
    for ev in filtrar_min_calidad(evidencias_web, web_min_calidad):
        if clave(ev) not in procesados:
            pendientes.append(("web", ev))
    for ev in filtrar_min_calidad(evidencias_libros, libros_min_calidad):
        if clave(ev) not in procesados:
            pendientes.append(("libros", ev))
    return pendientes


def estimar(pendientes):
    n = len(pendientes)
    return {
        "pendientes": n,
        "tokens_estimados": n * TOKENS_ESTIMADOS_POR_EVIDENCIA,
        "tokens_por_evidencia": TOKENS_ESTIMADOS_POR_EVIDENCIA,
    }


def _simulado_rapido(sistema, usuario):
    return '{"afirmaciones": []}'


def procesar_item(tipo, ev, indice_web, indice_libros, cliente, corr):
    error = {"estado": "error", "afirmaciones": [], "descartadas": []}
    sin_texto = {"estado": "sin_texto", "afirmaciones": [], "descartadas": []}
    try:
        if tipo == "web":
            texto = indice_web.texto_por_hash(
                ev.get("dominio"), ev.get("fuente_id"), ev.get("hash_seccion"))
            if texto is None:
                return tipo, ev, sin_texto
            res = es.extraer_afirmaciones(
                cliente, ev.get("entidad_id"), ev.get("faceta"), texto)
            return tipo, ev, res
        sec = indice_libros.seccion(ev.get("fuente_id"),
                                    ev.get("hash_seccion"))
        if sec is None or not (sec.get("texto") or "").strip():
            return tipo, ev, sin_texto
        res = al.extraer_afirmaciones_libros(
            cliente, ev.get("entidad_id"), ev.get("faceta"), sec.get("texto", ""),
            ev.get("idioma"), corr)
        return tipo, ev, res
    except Exception:
        return tipo, ev, error


def registro_procesado(ev, res):
    return {
        "hash_seccion": ev.get("hash_seccion"),
        "entidad_id": ev.get("entidad_id"),
        "faceta": ev.get("faceta"),
        "estado": res["estado"],
        "n_afirmaciones": len(res["afirmaciones"]),
        "origen": ORIGEN,
    }


def _log_progreso(stream, hechas, total, stats, inicio, abortado):
    transcurrido = time.time() - inicio
    ritmo = hechas / (transcurrido / 60.0) if transcurrido > 0 else 0.0
    restantes = max(total - hechas, 0)
    eta = restantes / ritmo if ritmo > 0 else 0.0
    descartas = sum(stats["descartadas"].values())
    detalle = ", ".join("%s:%d" % (m, n)
                        for m, n in sorted(stats["descartadas"].items()))
    estado = "PARADO (>20%% errores)" if abortado else ""
    linea = ("[afirmaciones_rapido] %d/%d evidencias | aceptadas=%d "
             "descartadas=%d (%s) | %.1f ev/min | ETA %.1f min %s"
             % (hechas, total, stats["afirmaciones"], descartas,
                detalle or "-", ritmo, eta, estado))
    print(linea, file=stream, flush=True)


def _error_en_ventana(window):
    if len(window) < VENTANA_ERRORES:
        return False
    errores = sum(1 for e in window if e == "error")
    return errores / len(window) > UMBRAL_ERRORES


class Ejecutor:
    def __init__(self, pendientes, out_web, out_libros, workers, cliente,
                 indice_web, indice_libros, corr):
        self.pendientes = pendientes
        self.total = len(pendientes)
        self.workers = workers
        self.cliente = cliente
        self.indice_web = indice_web
        self.indice_libros = indice_libros
        self.corr = corr
        self.stats = {
            "procesadas": 0,
            "sin_texto": 0,
            "errores": 0,
            "afirmaciones": 0,
            "contradicciones": 0,
            "descartadas": collections.Counter(),
            "por_familia": collections.Counter(),
        }
        self.lock = threading.Lock()
        self.window = collections.deque(maxlen=VENTANA_ERRORES)
        self.abortado = False
        self.inicio = time.time()
        self.exitosos = []
        self._abrir(out_web, out_libros)

    def _abrir(self, out_web, out_libros):
        self._fweb_proc = open(os.path.join(out_web, "procesados.jsonl"), "a",
                               encoding="utf-8")
        self._fweb_af = open(os.path.join(out_web, "afirmaciones.jsonl"), "a",
                             encoding="utf-8")
        self._flib_proc = open(os.path.join(out_libros, "procesados.jsonl"),
                               "a", encoding="utf-8")
        self._flib_af = open(os.path.join(out_libros,
                                          "afirmaciones_libros.jsonl"),
                             "a", encoding="utf-8")

    def cerrar(self):
        self._fweb_proc.close()
        self._fweb_af.close()
        self._flib_proc.close()
        self._flib_af.close()

    def _registrar(self, tipo, ev, res):
        with self.lock:
            if tipo == "web":
                fp, fa = self._fweb_proc, self._fweb_af
                for a in res["afirmaciones"]:
                    reg = es.registro_afirmacion(ev, a)
                    reg["origen"] = ORIGEN
                    fa.write(json.dumps(reg, ensure_ascii=False) + "\n")
                    self.stats["por_familia"][
                        es.familia_de_entidad(ev.get("entidad_id"))] += 1
                for _, motivo in res["descartadas"]:
                    self.stats["descartadas"][motivo] += 1
            else:
                fp, fa = self._flib_proc, self._flib_af
                for item in res["afirmaciones"]:
                    reg = al.registro_afirmacion_libros(ev, item)
                    reg["origen"] = ORIGEN
                    fa.write(json.dumps(reg, ensure_ascii=False) + "\n")
                    self.stats["por_familia"][
                        es.familia_de_entidad(ev.get("entidad_id"))] += 1
                    if item.get("contradice_kb"):
                        self.stats["contradicciones"] += 1
                for _, motivo in res["descartadas"]:
                    self.stats["descartadas"][motivo] += 1
            fp.write(json.dumps(registro_procesado(ev, res),
                                ensure_ascii=False) + "\n")
            fp.flush()
            fa.flush()
            self.stats["procesadas"] += 1
            self.window.append(res["estado"])
            if res["estado"] == "sin_texto":
                self.stats["sin_texto"] += 1
            elif res["estado"] == "error":
                self.stats["errores"] += 1
            else:
                self.stats["afirmaciones"] += len(res["afirmaciones"])
                if res["afirmaciones"]:
                    self.exitosos.append((tipo, ev))
            if self.stats["procesadas"] % 25 == 0 \
                    or self.stats["procesadas"] == self.total:
                _log_progreso(sys.stderr, self.stats["procesadas"], self.total,
                              self.stats, self.inicio, self.abortado)

    def ejecutar(self):
        if self.workers > 1:
            self._ejecutar_threads()
        else:
            self._ejecutar_secuencial()
        return self.stats, self.abortado

    def _ejecutar_secuencial(self):
        for tipo, ev in self.pendientes:
            if self.abortado:
                break
            t, e, res = procesar_item(tipo, ev, self.indice_web,
                                      self.indice_libros, self.cliente,
                                      self.corr)
            self._registrar(t, e, res)
            if _error_en_ventana(self.window):
                self.abortado = True

    def _ejecutar_threads(self):
        ex = ThreadPoolExecutor(max_workers=self.workers)
        futuros = set()
        idx = 0
        try:
            while True:
                while not self.abortado and idx < self.total \
                        and len(futuros) < self.workers:
                    tipo, ev = self.pendientes[idx]
                    idx += 1
                    futuros.add(ex.submit(procesar_item, tipo, ev,
                                          self.indice_web, self.indice_libros,
                                          self.cliente, self.corr))
                if not futuros:
                    break
                done, futuros = wait(futuros, return_when=FIRST_COMPLETED)
                for fut in done:
                    t, e, res = fut.result()
                    self._registrar(t, e, res)
                    if _error_en_ventana(self.window):
                        self.abortado = True
        except BaseException:
            ex.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            ex.shutdown(wait=True)


def _clave_dominio(ev):
    dominio = ev.get("dominio") or ""
    if not dominio:
        candidata = ev.get("url") or ev.get("fuente_id") or ""
        if "://" in candidata:
            dominio = urlparse(candidata).netloc
    dominio = dominio.strip().lower()
    if dominio.startswith("www."):
        dominio = dominio[4:]
    if ":" in dominio:
        dominio = dominio.split(":", 1)[0]
    return dominio


def _fuentes_independientes(evidencias):
    vistas_fuente = set()
    dominios_web = set()
    unicas = []
    for ev in evidencias:
        fuente = ev.get("fuente_id")
        if not fuente or fuente in vistas_fuente:
            continue
        vistas_fuente.add(fuente)
        if ev.get("tipo") == "web":
            dominio = _clave_dominio(ev)
            if dominio and dominio in dominios_web:
                continue
            if dominio:
                dominios_web.add(dominio)
        unicas.append(ev)
    return unicas


def _fuente_clave(ev):
    if ev.get("tipo") == "web":
        return ("web", _clave_dominio(ev))
    return ("libro", ev.get("fuente_id"))


def construir_fuentes_base(evidencias_web, evidencias_libros,
                          web_min_calidad, libros_min_calidad, excluir=None):
    excluir = excluir or set()
    por_celda = {}
    for ev in filtrar_min_calidad(evidencias_web, web_min_calidad):
        if clave(ev) in excluir:
            continue
        por_celda.setdefault((ev.get("entidad_id"), ev.get("faceta")),
                             []).append(ev)
    for ev in filtrar_min_calidad(evidencias_libros, libros_min_calidad):
        if clave(ev) in excluir:
            continue
        por_celda.setdefault((ev.get("entidad_id"), ev.get("faceta")),
                             []).append(ev)
    base = {}
    for k, evs in por_celda.items():
        base[k] = {_fuente_clave(ev) for ev in _fuentes_independientes(evs)}
    return base


def celdas_que_pasan_a_cinco(exitosos, cobertura_ruta, fuentes_base,
                             celda_por_clave):
    with open(cobertura_ruta, encoding="utf-8") as fh:
        cov = json.load(fh)
    nuevas_por_celda = {}
    for tipo, ev in exitosos:
        k = (ev.get("entidad_id"), ev.get("faceta"))
        if k not in celda_por_clave:
            continue
        base = fuentes_base.get(k, set())
        fc = _fuente_clave(ev)
        if fc not in base:
            nuevas_por_celda.setdefault(k, set()).add(fc)
    pasan = []
    for celda in cov["celdas"]:
        k = (celda["entidad_id"], celda["faceta"])
        n = celda["n_fuentes"]
        if n >= 5:
            continue
        nuevas = len(nuevas_por_celda.get(k, ()))
        if n + nuevas >= 5:
            pasan.append({
                "entidad_id": celda["entidad_id"],
                "faceta": celda["faceta"],
                "n_antes": n,
                "n_nuevas": nuevas,
                "n_despues": n + nuevas,
            })
    return pasan


def _fuente_afirmacion(reg):
    """Clave de fuente de una afirmación (fuente_id o dominio), igual que el
    consenso (`_clave_fuente`): la independencia se cuenta por fuente."""
    return reg.get("fuente_id") or reg.get("dominio") or ""


def fuentes_por_celda(afirmaciones):
    """(entidad_id, faceta) -> set(fuente) a partir de afirmaciones."""
    por_celda = {}
    for r in afirmaciones:
        k = (r.get("entidad_id"), r.get("faceta"))
        f = _fuente_afirmacion(r)
        if f:
            por_celda.setdefault(k, set()).add(f)
    return por_celda


def celdas_con_fuentes_nuevas(base_afirmaciones, extra_afirmaciones):
    """Celdas que ganan ≥1 fuente independiente nueva con los extras.

    Compara las fuentes ya presentes en la base (consenso/afirmaciones ya
    contadas) con las que aportan los extras; solo devuelve celdas donde los
    extras introducen al menos una fuente nueva. Es el filtro propuesto en T94
    para no rehacer las miles de celdas que solo duplican fuentes ya contadas.
    """
    base = fuentes_por_celda(base_afirmaciones)
    extra_por_celda = {}
    for r in extra_afirmaciones:
        k = (r.get("entidad_id"), r.get("faceta"))
        f = _fuente_afirmacion(r)
        if f:
            extra_por_celda.setdefault(k, set()).add(f)
    resultado = {}
    for k, fextra in sorted(extra_por_celda.items()):
        fbase = base.get(k, set())
        nuevas = fextra - fbase
        if nuevas:
            resultado[k] = {
                "fuentes_base": len(fbase),
                "fuentes_nuevas": len(nuevas),
                "fuentes_nuevas_lista": sorted(nuevas),
            }
    return resultado


def escribir_extra_filtrado(ruta, extra_afirmaciones, celdas_ganadoras):
    """Escribe solo las afirmaciones extra de celdas que ganan fuentes nuevas."""
    filtradas = [r for r in extra_afirmaciones
                 if (r.get("entidad_id"), r.get("faceta")) in celdas_ganadoras]
    with open(ruta, "w", encoding="utf-8") as fh:
        for r in filtradas:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(filtradas)


def escribir_informe(ruta, stats, estimacion, pasan, abortado,
                     celdas_nuevas=None):
    celdas_nuevas = celdas_nuevas or {}
    lineas = [
        "# Informe de afirmaciones del backend rápido (T69)",
        "",
        "Backend: Inception Mercury 3 (`mercury-3`) en `%s`, autenticado "
        "con `Authorization: Bearer` desde la variable de entorno `%s`."
        % (BACKEND_URL, API_KEY_ENV),
        "",
    ]
    if abortado:
        lineas.append("**La pasada se detuvo** porque superó el 20%% de "
                      "errores en una ventana de %d evidencias."
                      % VENTANA_ERRORES)
        lineas.append("")
    lineas += [
        "## Estimación previa",
        "",
        "- Evidencias pendientes: %d" % estimacion["pendientes"],
        "- Tokens estimados (a %d por evidencia): %d"
        % (estimacion["tokens_por_evidencia"],
           estimacion["tokens_estimados"]),
        "",
        "## Resultados",
        "",
        "- Evidencias procesadas: %d" % stats["procesadas"],
        "- Sin texto localizable (`sin_texto`): %d" % stats["sin_texto"],
        "- Errores del modelo: %d" % stats["errores"],
        "- Afirmaciones aceptadas: %d" % stats["afirmaciones"],
        "- Afirmaciones marcadas `contradice_kb`: %d"
        % stats["contradicciones"],
        "- Tokens consumidos (prompt + completion): %d"
        % stats["tokens_consumidos"],
        "",
        "## Descartadas por motivo",
        "",
    ]
    if stats["descartadas"]:
        for motivo, n in sorted(stats["descartadas"].items(),
                               key=lambda kv: -kv[1]):
            lineas.append("- %s: %d" % (motivo, n))
    else:
        lineas.append("- (ninguna)")
    lineas += ["", "## Afirmaciones por familia", "",
               "| Familia | Afirmaciones |", "|---|---|"]
    if stats["por_familia"]:
        for familia, n in sorted(stats["por_familia"].items(),
                                key=lambda kv: -kv[1]):
            lineas.append("| %s | %d |" % (familia, n))
    else:
        lineas.append("| (ninguna) | 0 |")
    lineas += ["", "## Celdas entidad×faceta que pasan a ≥5 fuentes "
                   "independientes", "",
               "| Entidad | Faceta | Fuentes antes | Fuentes nuevas | "
               "Fuentes después |", "|---|---|---|---|---|"]
    for p in pasan:
        lineas.append("| %s | %s | %d | %d | %d |"
                      % (p["entidad_id"], p["faceta"], p["n_antes"],
                         p["n_nuevas"], p["n_despues"]))
    lineas.append("")
    lineas.append("Total de celdas que pasan a ≥5 fuentes: %d" % len(pasan))
    lineas.append("")
    if celdas_nuevas:
        lineas += ["", "## Celdas que ganan ≥1 fuente independiente nueva "
                       "(filtro propuesto en T94 para el consenso)", "",
                   "| Entidad | Faceta | Familia | Fuentes base | Fuentes "
                   "nuevas |", "|---|---|---|---|---|"]
        for k, info in sorted(celdas_nuevas.items()):
            familia = es.familia_de_entidad(k[0])
            lineas.append("| %s | %s | %s | %d | %d |"
                          % (k[0], k[1], familia, info["fuentes_base"],
                             info["fuentes_nuevas"]))
        lineas.append("")
        lineas.append("Total de celdas que ganan fuentes nuevas: %d"
                      % len(celdas_nuevas))
        lineas.append("")
        por_familia = collections.Counter()
        for k, info in celdas_nuevas.items():
            por_familia[es.familia_de_entidad(k[0])] += 1
        lineas += ["Desglose por familia:", ""]
        for familia, n in sorted(por_familia.items(),
                                 key=lambda kv: -kv[1]):
            lineas.append("- %s: %d celdas" % (familia, n))
        lineas.append("")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


def _cliente_rapido(workers, simulado):
    if simulado:
        return LLMClient(simulado=_simulado_rapido)
    if not os.environ.get(API_KEY_ENV):
        print("[afirmaciones_rapido] Falta %r en el entorno."
              % API_KEY_ENV, file=sys.stderr)
        return None
    metricas = {"peticiones": 0, "latencia_total": 0.0,
                "max_latencia": 0.0, "prompt_tokens": 0,
                "completion_tokens": 0}
    return LLMClient(endpoints=[{
        "url": BACKEND_URL,
        "model": BACKEND_MODEL,
        "api_key_env": API_KEY_ENV,
    }], max_concurrencia=workers,
        tasa_max_por_minuto=TASA_MAX_POR_MINUTO, metricas=metricas,
        reasoning_effort=REASONING_EFFORT,
        max_completion_tokens=MAX_COMPLETION_TOKENS,
        max_tokens_default=MAX_TOKENS_DEFAULT)


def main(argv=None, cliente=None):
    parser = argparse.ArgumentParser(
        description="Pasada masiva de extracción de afirmaciones con el "
                    "backend rápido (T69).")
    parser.add_argument("--web-evidencias", default=DEFAULT_WEB_EVIDENCIAS)
    parser.add_argument("--libros-evidencias", default=DEFAULT_LIBROS_EVIDENCIAS)
    parser.add_argument("--web-procesados", default=DEFAULT_WEB_PROCESADOS)
    parser.add_argument("--libros-procesados", default=DEFAULT_LIBROS_PROCESADOS)
    parser.add_argument("--web-dir", default=DEFAULT_WEB_DIR)
    parser.add_argument("--libros-secciones-dir",
                        default=DEFAULT_LIBROS_SECCIONES)
    parser.add_argument("--cobertura", default=DEFAULT_COBERTURA)
    parser.add_argument("--base-web-afirmaciones",
                        default="/Users/angelgonzalez/fase0/afirmaciones_full/"
                                "afirmaciones.jsonl")
    parser.add_argument("--base-libros-afirmaciones",
                        default="/Users/angelgonzalez/fase0/afirmaciones_"
                                "libros/afirmaciones_libros.jsonl")
    parser.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    parser.add_argument("--web-min-calidad", type=int,
                        default=DEFAULT_WEB_MIN_CALIDAD)
    parser.add_argument("--libros-min-calidad", type=int,
                        default=DEFAULT_LIBROS_MIN_CALIDAD)
    parser.add_argument("--workers", type=int, default=CONCURRENCIA)
    parser.add_argument("--limite", type=int, default=0,
                        help="Máximo de evidencias a procesar (0 = todas).")
    parser.add_argument("--simulado", action="store_true",
                        help="Usa un cliente simulado (sin API).")
    parser.add_argument("--solo-estimar", action="store_true",
                        help="Estimación previa y salida.")
    args = parser.parse_args(argv)

    evidencias_web = cargar_jsonl(args.web_evidencias)
    evidencias_libros = cargar_jsonl(args.libros_evidencias)
    procesados = cargar_procesados_claves(
        args.web_procesados, args.libros_procesados,
        os.path.join(args.out_root, "web", "procesados.jsonl"),
        os.path.join(args.out_root, "libros", "procesados.jsonl"))

    pendientes = seleccionar_pendientes(
        evidencias_web, evidencias_libros, procesados,
        args.web_min_calidad, args.libros_min_calidad)
    if args.limite:
        pendientes = pendientes[:args.limite]
    estimacion = estimar(pendientes)

    print("Evidencias pendientes: %d (web+libros)" % estimacion["pendientes"],
          flush=True)
    print("Estimación: ~%d tokens (a %d por evidencia)"
          % (estimacion["tokens_estimados"],
             estimacion["tokens_por_evidencia"]), flush=True)
    if args.solo_estimar:
        print("Solo estimación.", flush=True)
        return estimacion
    if not pendientes:
        stats = {
            "procesadas": 0,
            "sin_texto": 0,
            "errores": 0,
            "afirmaciones": 0,
            "contradicciones": 0,
            "descartadas": collections.Counter(),
            "por_familia": collections.Counter(),
            "tokens_consumidos": 0,
        }
        print("Sin evidencias pendientes.", flush=True)
        return stats

    out_web = os.path.join(args.out_root, "web")
    out_libros = os.path.join(args.out_root, "libros")
    os.makedirs(out_web, exist_ok=True)
    os.makedirs(out_libros, exist_ok=True)

    if cliente is None:
        cliente = _cliente_rapido(args.workers, args.simulado)
        if cliente is None:
            return None

    indice_web = es.IndiceWeb(args.web_dir)
    indice_libros = al.IndiceLibros(args.libros_secciones_dir)
    corr = cargar_correspondencias()

    ejecutor = Ejecutor(pendientes, out_web, out_libros, args.workers,
                        cliente, indice_web, indice_libros, corr)
    try:
        stats, abortado = ejecutor.ejecutar()
    finally:
        ejecutor.cerrar()

    stats["tokens_consumidos"] = 0
    if isinstance(cliente.metricas, dict):
        stats["tokens_consumidos"] = (
            cliente.metricas.get("prompt_tokens", 0)
            + cliente.metricas.get("completion_tokens", 0))

    fuentes_base = construir_fuentes_base(
        evidencias_web, evidencias_libros,
        args.web_min_calidad, args.libros_min_calidad,
        excluir={clave(ev) for _, ev in pendientes})
    with open(args.cobertura, encoding="utf-8") as fh:
        cov = json.load(fh)
    celda_por_clave = {(c["entidad_id"], c["faceta"]): c
                       for c in cov["celdas"]}
    pasan = celdas_que_pasan_a_cinco(
        ejecutor.exitosos, args.cobertura, fuentes_base, celda_por_clave)

    base_afirmaciones = []
    for ruta in (args.base_web_afirmaciones,
                 args.base_libros_afirmaciones):
        if ruta and os.path.exists(ruta):
            base_afirmaciones.extend(cargar_jsonl(ruta))
    extra_afirmaciones = []
    for rel in ("web/afirmaciones.jsonl",
                "libros/afirmaciones_libros.jsonl"):
        ruta = os.path.join(args.out_root, rel)
        if os.path.exists(ruta):
            extra_afirmaciones.extend(cargar_jsonl(ruta))
    celdas_nuevas = celdas_con_fuentes_nuevas(
        base_afirmaciones, extra_afirmaciones)

    if celdas_nuevas:
        ruta_filtro = os.path.join(args.out_root,
                                    "afirmaciones_celdas_nuevas.jsonl")
        n_filtradas = escribir_extra_filtrado(
            ruta_filtro, extra_afirmaciones, set(celdas_nuevas))
        print("[afirmaciones_rapido] Filtro de consenso: %d celdas que "
              "ganan fuentes nuevas (%d afirmaciones extra filtradas) -> %s"
              % (len(celdas_nuevas), n_filtradas, ruta_filtro), flush=True)

    ruta_informe = os.path.join(args.out_root, "informe.md")
    escribir_informe(ruta_informe, stats, estimacion, pasan, abortado,
                     celdas_nuevas=celdas_nuevas)
    print("[afirmaciones_rapido] Informe escrito en %s" % ruta_informe,
          flush=True)
    return stats


if __name__ == "__main__":
    main()
