#!/usr/bin/env python3
"""Comparativa de backends v2 para extracción de afirmaciones (T68).

Segunda comparativa sobre las mismas 100 evidencias (60 web + 40 libros) ya
procesadas por el nodo local. Respecto a T65:

* Se reduce el razonamiento del backend rápido (`reasoning_effort="instant"`)
  y se sube el presupuesto de tokens (`max_completion_tokens`) SOLO en esta
  comparativa, sin tocar los extractores (`afirmaciones_es.py` /
  `afirmaciones_libros.py`).
* Se reintenta ante respuesta vacía (`content=None`), que era la causa
  dominante del 51 % de errores de T65.
* Se sustituye el solapamiento exacto por una similitud aproximada de tokens
  (Jaccard sobre raíces truncadas, umbral documentado) y se mide cobertura de
  ambos lados, más la tasa de afirmaciones que superan los validadores.

Escribe /Users/angelgonzalez/fase0/comparativa_backends_v2.md.

La clave de la API se lee en tiempo de ejecución de la variable de entorno
`INCEPTION_API_KEY`; nunca se escribe en este fichero.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from statistics import mean, median

WORKTREE = "/Users/angelgonzalez/adivinacion-ia/.worktrees/t68-backend-rapido-2"
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

# Parámetros del backend SOLO para esta comparativa (no modifican los
# extractores; se aplican vía los valores por defecto del cliente).
REASONING_EFFORT = "instant"
MAX_COMPLETION_TOKENS = 8192
MAX_TOKENS_DEFAULT = 4096

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
INFORME = os.path.join(FASE0, "comparativa_backends_v2.md")

N_WEB = 60
N_LIBROS = 40
CONCURRENCIA = 3
TASA_MAX_POR_MINUTO = 60

# Umbral de similitud (Jaccard) para considerar dos afirmaciones equivalentes.
UMBRAL_JACCARD = 0.5


# ---------------------------------------------------------------------------
# Similitud aproximada de tokens (sin LLM)
# ---------------------------------------------------------------------------

_PARARUELAS = set(
    "a al ante bajo cabe con contra de del desde durante e el en entre hacia "
    "hasta la las le les lo los mas mas mediante mi mis muy ni no nos o os "
    "para pero por porque que quien se segun si sin so sobre su sus sus te "
    "tambien tan tanto tras tu tus un una uno unas unos y ya yo me nos"
    .split())


def _raiz_corta(p):
    """Raíz truncada: quita flexión mínima y corta a 6 caracteres."""
    if len(p) > 5 and (p.endswith("as") or p.endswith("os")):
        p = p[:-2]
    elif len(p) > 4 and p.endswith("es"):
        p = p[:-2]
    elif len(p) > 4 and p.endswith("s"):
        p = p[:-1]
    return p[:6]


def _tokens_raiz(texto):
    """Conjunto de raíces truncadas de un texto (normalizado a minúsculas)."""
    norm = cartas.norm(texto)
    raices = set()
    for t in norm.split():
        if len(t) >= 3 and t not in _PARARUELAS:
            raices.add(_raiz_corta(t))
    return raices


def _jaccard(conj_a, conj_b):
    """Coeficiente de Jaccard entre dos conjuntos de raíces."""
    if not conj_a or not conj_b:
        return 0.0
    union = len(conj_a | conj_b)
    if not union:
        return 0.0
    return len(conj_a & conj_b) / union


def _conjuntos(textos):
    """Lista de conjuntos de raíces para cada texto."""
    if not textos:
        return []
    return [_tokens_raiz(t) for t in textos if t]


def _cobertura_conjuntos(conj_a, conj_b, umbral=UMBRAL_JACCARD):
    """Fracción de textos de A con al menos un equivalente en B (umbral)."""
    if not conj_a:
        return 0.0
    aciertos = 0
    for x in conj_a:
        if max((_jaccard(x, y) for y in conj_b), default=0.0) >= umbral:
            aciertos += 1
    return aciertos / len(conj_a)


def _cobertura(textos_a, textos_b, umbral=UMBRAL_JACCARD):
    """Igual que `_cobertura_conjuntos` pero sobre listas de texto."""
    return _cobertura_conjuntos(_conjuntos(textos_a),
                                _conjuntos(textos_b), umbral)


# ---------------------------------------------------------------------------
# Carga y selección
# ---------------------------------------------------------------------------

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
    """entidad+faceta+fuente -> lista de afirmaciones originales."""
    idx = {}
    for r in afirmaciones:
        k = (r.get("entidad_id"), r.get("faceta"), r.get("fuente_id"))
        idx.setdefault(k, []).append(r.get("afirmacion") or "")
    return idx


def norm_set(textos):
    return {cartas.norm(t) for t in textos if t and cartas.norm(t)}


# ---------------------------------------------------------------------------
# Procesado de una evidencia
# ---------------------------------------------------------------------------

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

    local_textos = [t for t in local_refs if t and str(t).strip()]
    res = {"tipo": tipo, "entidad_id": entidad, "faceta": faceta,
           "fuente_id": ev.get("fuente_id"), "dominio": ev.get("dominio"),
           "n_local": len(local_textos), "estado": "sin_texto",
           "local_textos": local_textos}
    if texto is None or not str(texto).strip():
        return res

    if tipo == "web":
        ext = es.extraer_afirmaciones(cliente, entidad, faceta, texto)
        crudas = ext.get("afirmaciones") or []
        fast_textos = [a for a in crudas if a and str(a).strip()]
    else:
        ext = extraer_afirmaciones_libros(cliente, entidad, faceta, texto,
                                          idioma, corr)
        fast_textos = [a.get("afirmacion", "")
                       for a in ext.get("afirmaciones") or []
                       if a.get("afirmacion")]

    descartadas = ext.get("descartadas") or []
    res["estado"] = ext.get("estado")
    res["n_fast"] = len(fast_textos)
    res["fast_textos"] = fast_textos
    res["n_descartadas"] = len(descartadas)
    res["descartadas"] = descartadas
    res["solape_exacto"] = len(norm_set(fast_textos) & norm_set(local_textos))
    res["cobertura_local"] = _cobertura(local_textos, fast_textos)
    res["cobertura_fast"] = _cobertura(fast_textos, local_textos)
    return res


def _snapshot(metricas):
    return (metricas.get("peticiones", 0),
            metricas.get("latencia_total", 0.0),
            metricas.get("prompt_tokens", 0),
            metricas.get("completion_tokens", 0))


def _delta(metricas, antes):
    p, l, pt, ct = antes
    return {"peticiones": metricas.get("peticiones", 0) - p,
            "latencia": metricas.get("latencia_total", 0.0) - l,
            "tokens": ((metricas.get("prompt_tokens", 0) - pt)
                       + (metricas.get("completion_tokens", 0) - ct))}


# ---------------------------------------------------------------------------
# Lógica principal
# ---------------------------------------------------------------------------

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
       tasa_max_por_minuto=TASA_MAX_POR_MINUTO, metricas=metricas,
       reasoning_effort=REASONING_EFFORT,
       max_completion_tokens=MAX_COMPLETION_TOKENS,
       max_tokens_default=MAX_TOKENS_DEFAULT)

    resultados = []
    for tipo, sel, local in (("web", web_sel, web_local),
                             ("libros", libros_sel, libros_local)):
        for ev in sel:
            clave_local = (ev.get("entidad_id"), ev.get("faceta"),
                           ev.get("fuente_id"))
            refs = local.get(clave_local, [])
            antes = _snapshot(metricas)
            res = procesar_evidencia(
                ev, tipo, cliente, indice_web, indice_libros, corr, refs)
            res.update(_delta(metricas, antes))
            resultados.append(res)

    # Agregados
    def _nueva_stat():
        return {"procesadas": 0, "sin_texto": 0, "errores": 0,
                "n_local": 0, "n_fast": 0, "n_descartadas": 0,
                "solape_exacto": 0, "cobertura_local": 0.0,
                "cobertura_fast": 0.0, "celdas_cob_local": 0,
                "celdas_cob_fast": 0, "peticiones": 0,
                "latencia": 0.0, "tokens": 0, "descartadas": Counter()}

    ag = {"web": _nueva_stat(), "libros": _nueva_stat(),
          "total": _nueva_stat()}
    for r in resultados:
        t = r["tipo"]
        s = ag[t]
        s["procesadas"] += 1
        s["peticiones"] += r["peticiones"]
        s["latencia"] += r["latencia"]
        s["tokens"] += r["tokens"]
        if r["estado"] == "sin_texto":
            s["sin_texto"] += 1
            continue
        if r["estado"] == "error":
            s["errores"] += 1
        else:
            s["n_local"] += r["n_local"]
            s["n_fast"] += r["n_fast"]
            s["n_descartadas"] += r["n_descartadas"]
            s["solape_exacto"] += r["solape_exacto"]
            if r["n_local"]:
                s["cobertura_local"] += r["cobertura_local"]
                s["celdas_cob_local"] += 1
            if r["n_fast"]:
                s["cobertura_fast"] += r["cobertura_fast"]
                s["celdas_cob_fast"] += 1
        for _, motivo in r.get("descartadas", []):
            s["descartadas"][motivo] += 1

    total_sel = len(resultados)
    proc = sum(ag[t]["procesadas"] for t in ("web", "libros"))
    sin_t = sum(ag[t]["sin_texto"] for t in ("web", "libros"))
    err = sum(ag[t]["errores"] for t in ("web", "libros"))
    n_loc = sum(ag[t]["n_local"] for t in ("web", "libros"))
    n_fast = sum(ag[t]["n_fast"] for t in ("web", "libros"))
    n_desc = sum(ag[t]["n_descartadas"] for t in ("web", "libros"))
    validadas = n_fast
    tasa_validacion = (validadas / (validadas + n_desc)
                       if (validadas + n_desc) else 0.0)
    solape = sum(ag[t]["solape_exacto"] for t in ("web", "libros"))
    cob_local = sum(ag[t]["cobertura_local"] for t in ("web", "libros"))
    cob_fast = sum(ag[t]["cobertura_fast"] for t in ("web", "libros"))
    celdas_cob_local = sum(ag[t]["celdas_cob_local"]
                           for t in ("web", "libros"))
    celdas_cob_fast = sum(ag[t]["celdas_cob_fast"]
                          for t in ("web", "libros"))
    cob_local_media = (cob_local / celdas_cob_local
                       if celdas_cob_local else 0.0)
    cob_fast_media = (cob_fast / celdas_cob_fast
                      if celdas_cob_fast else 0.0)

    peticiones = sum(ag[t]["peticiones"] for t in ("web", "libros"))
    latencia_total = sum(ag[t]["latencia"] for t in ("web", "libros"))
    tokens_total = sum(ag[t]["tokens"] for t in ("web", "libros"))

    def _media(valor, base):
        return (valor / base) if base else 0.0

    lat_por_pet = _media(latencia_total, peticiones)
    tokens_por_ev = _media(tokens_total, proc)
    lat_por_ev = _media(latencia_total, proc)
    error_rate = _media(err, proc)
    solape_si = _media(solape, n_loc)

    descartes = Counter()
    for t in ("web", "libros"):
        descartes.update(ag[t]["descartadas"])

    # Ejemplos
    buenos = _ejemplos_buenos(resultados, 5)
    malos = _ejemplos_malos(resultados, 5)

    _escribir_informe(resultados, ag, web_sel, libros_sel,
                       lat_por_pet, lat_por_ev, tokens_por_ev,
                       tokens_total, peticiones, total_sel, proc,
                       sin_t, err, error_rate, n_loc, n_fast,
                       solape, solape_si, validadas, n_desc,
                       tasa_validacion, cob_local_media, cob_fast_media,
                       descartes, buenos, malos)
    return 0


def _ejemplos_buenos(resultados, limite):
    """Las celdas donde el backend cubre mejor al nodo local y viceversa."""
    candidatos = [r for r in resultados
                  if r["estado"] == "ok"
                  and r["n_local"] > 0 and r["n_fast"] > 0]
    candidatos.sort(key=lambda r: -min(r["cobertura_local"],
                                       r["cobertura_fast"]))
    return candidatos[:limite]


def _ejemplos_malos(resultados, limite):
    """Errores primero, luego las celdas con peor cobertura."""
    errores = [r for r in resultados if r["estado"] == "error"]
    bajos = [r for r in resultados
             if r["estado"] == "ok" and r["n_local"] > 0]
    bajos.sort(key=lambda r: r["cobertura_local"])
    return (errores + bajos)[:limite]


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

def _truncar(texto, n=110):
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= n else texto[:n - 1] + "…"


def _fila_ejemplo(r, nota, etiqueta_texto="afirmación local"):
    n_loc = r.get("n_local", 0)
    n_fast = r.get("n_fast", 0)
    if r["estado"] == "error":
        cob = "-"
        texto = "-"
    else:
        cob = "L %.0f%% / F %.0f%%" % (
            100.0 * r["cobertura_local"], 100.0 * r["cobertura_fast"])
        texto = _truncar((r.get("local_textos") or [""])[0])
    return ("| %s | %s | %s | %d | %d | %s | %s | %s |"
            % (r["tipo"], r["entidad_id"], r["faceta"],
               n_loc, n_fast, cob, texto, nota))


def _escribir_informe(resultados, ag, web_sel, libros_sel,
                       lat_por_pet, lat_por_ev, tokens_por_ev,
                       tokens_total, peticiones, total_sel, proc,
                       sin_t, err, error_rate, n_loc, n_fast,
                       solape, solape_si, validadas, n_desc,
                       tasa_validacion, cob_local_media, cob_fast_media,
                       descartes, buenos, malos):
    lineas = []
    lineas.append("# Comparativa de backends v2 (T68)")
    lineas.append("")
    lineas.append("Backend rápido: Inception Mercury 3 (`mercury-3`) en "
                  "`%s`, autenticado con `Authorization: Bearer` desde la "
                  "variable de entorno `%s`." % (BACKEND_URL, API_KEY_ENV))
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
    lineas.append("- Para reducir el 51%% de errores de T65 (respuesta vacía "
                  "por agotar `max_tokens=1024` en razonamiento), en esta "
                  "comparativa se usa únicamente `reasoning_effort=%s` y "
                  "`max_completion_tokens=%d` (y `max_tokens_default=%d`) a "
                  "nivel de cliente; los extractores no se tocan. Además se "
                  "reintenta ante `content=None`."
                  % (REASONING_EFFORT, MAX_COMPLETION_TOKENS,
                     MAX_TOKENS_DEFAULT))
    lineas.append("- Similitud aproximada sin LLM: Jaccard sobre raíces "
                  "truncadas (minúsculas, sin tildes, sin signos, sin "
                  "palabras vacías y raíz truncada a 6 caracteres) con "
                  "umbral `%.2f`. Se mide cobertura en ambos sentidos: "
                  "fracción de afirmaciones del nodo local con un equivalente "
                  "del backend y viceversa." % UMBRAL_JACCARD)
    lineas.append("- Nota: la API fuerza `temperature>=0.5` (el extractor "
                  "pide 0.2, el proveedor la sube a 1).")
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
    lineas.append("| Solapamiento exacto (normalizado) | %d (%.1f%% de n_local) |"
                  % (solape, 100.0 * solape_si))
    lineas.append("| Cobertura media del nodo local por el backend | %.1f%% |"
                  % (100.0 * cob_local_media))
    lineas.append("| Cobertura media del backend por el nodo local | %.1f%% |"
                  % (100.0 * cob_fast_media))
    lineas.append("| Tasa de superación de validadores | %d/%d (%.1f%%) |"
                  % (validadas, validadas + n_desc, 100.0 * tasa_validacion))
    lineas.append("| Peticiones de red | %d |" % peticiones)
    lineas.append("| Latencia media por petición | %.2f s |" % lat_por_pet)
    lineas.append("| Latencia media por evidencia | %.2f s |" % lat_por_ev)
    lineas.append("| Tokens totales (prompt + completion) | %d |"
                  % tokens_total)
    lineas.append("| Tokens por evidencia (media) | %d |" % tokens_por_ev)
    lineas.append("")

    lineas.append("### Desglose por tipo")
    lineas.append("")
    lineas.append("| Tipo | Procesadas | sin_texto | Errores | n_local | "
                  "n_fast | Solape exacto | Cobertura local | Cobertura fast |")
    lineas.append("|---|---|---|---|---|---|---|---|---|")
    for t in ("web", "libros"):
        s = ag[t]
        cob_loc = (100.0 * s["cobertura_local"] / s["celdas_cob_local"]
                   if s["celdas_cob_local"] else 0.0)
        cob_fast = (100.0 * s["cobertura_fast"] / s["celdas_cob_fast"]
                    if s["celdas_cob_fast"] else 0.0)
        lineas.append("| %s | %d | %d | %d | %d | %d | %d | %.1f%% | %.1f%% |"
                      % (t, s["procesadas"], s["sin_texto"], s["errores"],
                         s["n_local"], s["n_fast"], s["solape_exacto"],
                         cob_loc, cob_fast))
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

    lineas.append("## Ejemplos buenos (el backend capta bien la afirmación)")
    lineas.append("")
    lineas.append("| Tipo | Entidad | Faceta | n_local | n_fast | Cobertura "
                  "L/F | Afirmación local (inicio) | Nota |")
    lineas.append("|---|---|---|---|---|---|---|---|")
    for r in buenos:
        lineas.append(_fila_ejemplo(r, "buena cobertura"))
    lineas.append("")

    lineas.append("## Ejemplos malos (errores o cobertura baja)")
    lineas.append("")
    lineas.append("| Tipo | Entidad | Faceta | n_local | n_fast | Cobertura "
                  "L/F | Afirmación local (inicio) | Nota |")
    lineas.append("|---|---|---|---|---|---|---|---|")
    for r in malos:
        nota = "error de extracción" if r["estado"] == "error" else \
            "cobertura baja"
        lineas.append(_fila_ejemplo(r, nota))
    lineas.append("")

    # Conclusión
    lineas.append("## Conclusión")
    lineas.append("")
    lineas.append("**¿Sirve para extracción masiva?** %s"
                  % _conclusion_viable(error_rate, cob_local_media,
                                       cob_fast_media))
    lineas.append("")
    lineas.append("- **Parámetros usados:** `reasoning_effort=%s`, "
                  "`max_completion_tokens=%d`. Con `max_tokens=1024` (T65) "
                  "el error era del 51%%; ahora es del %.1f%%."
                  % (REASONING_EFFORT, MAX_COMPLETION_TOKENS,
                     100.0 * error_rate))
    lineas.append("- **Cobertura / precisión relativa al nodo local:** "
                  "%.1f%% de las afirmaciones locales tienen un equivalente en "
                  "el backend (contra %.1f%% en sentido contrario)."
                  % (100.0 * cob_local_media, 100.0 * cob_fast_media))
    lineas.append("- **Coste:** %.2f s y %d tokens por evidencia (media); con "
                  "concurrencia %d." % (lat_por_ev, tokens_por_ev,
                                        CONCURRENCIA))
    lineas.append("")
    lineas.append(_estimacion_horas(tokens_por_ev, lat_por_ev, n_loc))
    lineas.append("")

    with open(INFORME, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))
    print("[comparativa] Informe escrito en %s" % INFORME)


def _conclusion_viable(error_rate, cob_local_media, cob_fast_media):
    if error_rate > 0.3:
        return ("**No**, de momento: la tasa de errores (%.1f%%) sigue siendo "
                "alta." % (100.0 * error_rate))
    if cob_local_media >= 0.7 and cob_fast_media >= 0.7:
        return ("**Sí**, con reservas: alta cobertura en ambos sentidos "
                "(%.0f%% / %.0f%%) y error bajo." % (
                    100.0 * cob_local_media, 100.0 * cob_fast_media))
    if cob_local_media >= 0.5:
        return ("**Parcialmente**: ~ cobertura del nodo local (%.0f%%), pero "
                "no suficiente para sustituirlo sin pérdida; útil como "
                "segundo extractor o para fusión." % (
                    100.0 * cob_local_media))
    return ("**No** para sustituir al nodo local: cobertura baja "
            "(%.0f%% local, %.0f%% fast)." % (
                100.0 * cob_local_media, 100.0 * cob_fast_media))


def _estimacion_horas(tokens_por_ev, lat_por_ev, n_loc):
    pendientes = 6000
    lat_total_seg = pendientes * lat_por_ev / CONCURRENCIA
    horas = lat_total_seg / 3600.0
    tokens_total = pendientes * tokens_por_ev
    return ("**Estimación de esfuerzo para las ~%d evidencias pendientes:** "
            "a %d tokens y %.2f s por evidencia, con concurrencia %d, el "
            "tiempo de pared sería ≈ %.1f h (dominado por la latencia), y el "
            "consumo ≈ %d M tokens. Es una cota inferior: no incluye "
            "reintentos ni el coste de la fusión/deduplicación con el nodo "
            "local." % (pendientes, tokens_por_ev, lat_por_ev,
                        CONCURRENCIA, horas, tokens_total // 1000000))


if __name__ == "__main__":
    sys.exit(main())
