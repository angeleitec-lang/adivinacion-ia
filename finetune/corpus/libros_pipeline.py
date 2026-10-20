"""Orquestador reanudable de la fase 0 de libros (T24).

Encadena las piezas sueltas en etapas idempotentes sobre un `--work-dir`
(fuera del repo) con esta estructura:

- `crudo/<id>.txt`          texto descargado o extraído tal cual
- `limpio/<id>.txt`         texto tras la limpieza
- `secciones/<id>.jsonl`    secciones segmentadas
- `fetch.jsonl`             bitácora de pasadas (inventario, descargas)
- `errores.jsonl`           incidencias por libro (nunca cortan la pasada)
- `evidencias/`             salidas del juez
- `informe.md`              informe de calidad

Etapas: `descarga` (archive.org con `libros_fetch._obtener` y extracción de
EPUB locales) → `limpieza` → `segmentacion` → `informe` → `juez`.
Cada pasada solo procesa lo pendiente, así que se puede interrumpir y
reanudar sin repetir trabajo ni tocar la red de más.
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.error

import cobertura
import juez
import libros_extraer
import libros_fetch
import libros_informe
import libros_limpiar
import libros_segmentar
import llm_client
from libros_fuentes import (ARCHIVE_FILES, DECISIONES_OK, EPUB_FILE, ESTADOS_OK,
                            _leer_jsonl, _normalizar_archive, _normalizar_epub,
                            normalizar_titulo)

ETAPAS = ("descarga", "limpieza", "segmentacion", "informe", "juez")
DEFAULT_WORK_DIR = "/Users/angelgonzalez/fase0/libros"
DEFAULT_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")
# Umbral del orquestador: más laxo que el de libros_fetch (OCR incompleto),
# solo evita guardar páginas de error o ficheros vacíos.
MIN_CRUDO_BYTES = 1024
# Con estos 429 seguidos se corta la pasada (código 3) para no hostigar.
CUARENTA_Y_NUEVE_SEGUIDOS = 2
# Juez: las secciones se procesan por lotes para que cada lote quede escrito
# en `juicios.jsonl` antes de empezar el siguiente. Con lotes grandes una
# llamada lenta (o un endpoint que no responde) retrasaba horas la primera
# línea escrita, con el proceso aparentemente colgado al 0 % de CPU.
SECCIONES_POR_LOTE_JUEZ = 50
# Timeout por petición al LLM (segundos). Acota la espera de una sección
# atascada; con `REINTENTOS_JUEZ = 1` el peor caso por sección es 2 timeouts.
TIMEOUT_JUEZ = 60.0
REINTENTOS_JUEZ = 1


def cargar_inventario(dir_knowledge):
    """Inventario para el orquestador: libros aprobados de archive y EPUB local.

    Acepta tanto las filas OCR con `estado` aprobado en los ficheros de
    archive como las filas con `decision` aprobada en cualquiera (los
    inventarios de libros admiten EPUB en su propio fichero o suelto).
    """
    candidatos = []
    for nombre in ARCHIVE_FILES + (EPUB_FILE,):
        for fila in _leer_jsonl(os.path.join(dir_knowledge, nombre)):
            if fila.get("estado") in ESTADOS_OK and fila.get("texto_ocr"):
                candidatos.append(_normalizar_archive(fila))
            elif fila.get("decision") in DECISIONES_OK:
                candidatos.append(_normalizar_epub(fila, dir_knowledge))
    mejores = {}
    orden = []
    for registro, tamano in candidatos:
        clave = normalizar_titulo(registro["titulo"])
        if clave not in mejores or tamano > mejores[clave][1]:
            if clave not in mejores:
                orden.append(clave)
            mejores[clave] = (registro, tamano)
    return [mejores[clave][0] for clave in orden]


def filtrar_libros(libros, solo_ids=None, max=0):
    """Recorta el inventario por ids (separados por comas) y por número máximo."""
    if solo_ids:
        wanted = {s.strip() for s in solo_ids.split(",") if s.strip()}
        libros = [r for r in libros if r["id"] in wanted]
    if max and max > 0:
        libros = libros[:max]
    return libros


def _ruta_crudo(work_dir, libro):
    return os.path.join(work_dir, "crudo", libro["id"] + ".txt")


def crudo_usable(ruta):
    """Un crudo existente sirve si ocupa lo mínimo y no es una página HTML."""
    if not os.path.exists(ruta):
        return False
    with open(ruta, "rb") as fh:
        datos = fh.read()
    if len(datos) < MIN_CRUDO_BYTES:
        return False
    return not datos.lstrip()[:200].lower().startswith((b"<!doctype html", b"<html"))


def pendientes_de_descarga(libros, work_dir):
    """Libros de archive.org cuyo crudo falta o no es aprovechable."""
    return [r for r in libros
            if r["origen"] == "archive" and r["url"]
            and not crudo_usable(_ruta_crudo(work_dir, r))]


def _anotar(ruta_jsonl, registro):
    with open(ruta_jsonl, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _es_pagina_error(datos):
    return datos.lstrip()[:200].lower().startswith((b"<!doctype html", b"<html"))


def _guardar_crudo(crud_dir, libro, datos):
    with open(os.path.join(crud_dir, libro["id"] + ".txt"), "wb") as fh:
        fh.write(datos)


def _extraer_epub(libro, crud_dir, errores_ruta):
    """Extrae el texto de un EPUB local al crudo. Devuelve los bytes escritos."""
    try:
        texto, metricas = libros_extraer.epub_a_texto(libro["ruta_local"])
    except Exception as exc:
        _anotar(errores_ruta, {"id": libro["id"], "etapa": "descarga",
                               "motivo": "epub_%s" % type(exc).__name__})
        print("%s: error leyendo EPUB (%s)" % (libro["id"], type(exc).__name__),
              file=sys.stderr)
        return 0
    if metricas.get("drm") or len(texto.strip()) < MIN_CRUDO_BYTES:
        _anotar(errores_ruta, {"id": libro["id"], "etapa": "descarga",
                               "motivo": "epub_con_drm" if metricas.get("drm")
                               else "contenido_invalido"})
        print("%s: EPUB no aprovechable" % libro["id"], file=sys.stderr)
        return 0
    datos = texto.encode("utf-8")
    _guardar_crudo(crud_dir, libro, datos)
    print("%s: extraído del EPUB (%d bytes)" % (libro["id"], len(datos)))
    return len(datos)


def _etapa_descarga(libros, work_dir, ctx):
    """Baja los crudos de archive.org que falten y extrae los EPUB locales.

    Deja una línea de resumen en `fetch.jsonl` por pasada; los detalles de
    cada incidencia van a `errores.jsonl` y no cortan la ejecución.
    """
    crud_dir = os.path.join(work_dir, "crudo")
    os.makedirs(crud_dir, exist_ok=True)
    errores_ruta = os.path.join(work_dir, "errores.jsonl")
    pausa = ctx["pausa"]
    pendientes = pendientes_de_descarga(libros, work_dir)
    descargados = 0
    bytes_total = 0
    cuarenta_y_nueve = 0
    parada_limitada = False
    for i, libro in enumerate(pendientes):
        datos = b""
        try:
            datos = libros_fetch._obtener(libro["url"])
        except urllib.error.HTTPError as exc:
            motivo = "http_%d" % exc.code
        except (urllib.error.URLError, OSError):
            motivo = "error_de_red"
        except Exception:
            motivo = "error_inesperado"
        else:
            motivo = ""
        if motivo == "http_429":
            cuarenta_y_nueve += 1
        else:
            cuarenta_y_nueve = 0
        if not motivo and len(datos) >= MIN_CRUDO_BYTES \
                and not _es_pagina_error(datos):
            _guardar_crudo(crud_dir, libro, datos)
            descargados += 1
            bytes_total += len(datos)
            print("%s: descargado (%d bytes)" % (libro["id"], len(datos)))
        else:
            _anotar(errores_ruta, {"id": libro["id"], "etapa": "descarga",
                                   "motivo": motivo or "contenido_invalido"})
            print("%s: error (%s)" % (libro["id"], motivo or "contenido_invalido"),
                  file=sys.stderr)
        if cuarenta_y_nueve >= CUARENTA_Y_NUEVE_SEGUIDOS:
            parada_limitada = True
            print("descarga: %d errores 429 seguidos, se para la pasada"
                  % cuarenta_y_nueve, file=sys.stderr)
            break
        if i < len(pendientes) - 1 and pausa > 0:
            time.sleep(pausa)
    if not parada_limitada:
        for libro in libros:
            if libro["origen"] != "epub_local":
                continue
            if crudo_usable(_ruta_crudo(work_dir, libro)):
                continue
            if not libro.get("ruta_local"):
                _anotar(errores_ruta, {"id": libro["id"], "etapa": "descarga",
                                       "motivo": "sin_ruta_local"})
                print("%s: sin ruta local de EPUB" % libro["id"], file=sys.stderr)
                continue
            bytes_extraidos = _extraer_epub(libro, crud_dir, errores_ruta)
            descargados += 1 if bytes_extraidos else 0
            bytes_total += bytes_extraidos
    estado = "limitada" if parada_limitada else ("ok" if descargados else "ya_existe")
    _anotar(os.path.join(work_dir, "fetch.jsonl"),
            {"etapa": "descarga", "estado": estado, "nuevos": descargados,
             "reutilizados": len(pendientes) - descargados, "bytes": bytes_total})
    return 3 if parada_limitada else 0


def _etapa_limpieza(libros, work_dir, ctx):
    """Pasa `libros_limpiar.limpiar` a cada crudo que aún no tenga limpio."""
    limpio_dir = os.path.join(work_dir, "limpio")
    os.makedirs(limpio_dir, exist_ok=True)
    errores_ruta = os.path.join(work_dir, "errores.jsonl")
    hechos = 0
    for libro in libros:
        ruta_crudo = _ruta_crudo(work_dir, libro)
        if not crudo_usable(ruta_crudo):
            continue
        ruta_limpio = os.path.join(limpio_dir, libro["id"] + ".txt")
        if os.path.exists(ruta_limpio):
            hechos += 1
            continue
        with open(ruta_crudo, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
        limpio, informe = libros_limpiar.limpiar(texto, libro["idioma"])
        if len(limpio.strip()) < MIN_CRUDO_BYTES:
            _anotar(errores_ruta, {"id": libro["id"], "etapa": "limpieza",
                                   "motivo": "texto_insuficiente"})
            print("%s: limpieza no deja texto aprovechable" % libro["id"],
                  file=sys.stderr)
            continue
        with open(ruta_limpio, "w", encoding="utf-8") as fh:
            fh.write(limpio)
        if informe["calidad_baja"]:
            _anotar(errores_ruta, {"id": libro["id"], "etapa": "limpieza",
                                   "motivo": "calidad_baja",
                                   "ratio_comunes": informe["ratio_comunes"]})
            print("%s: calidad baja (ratio %.2f)"
                  % (libro["id"], informe["ratio_comunes"]), file=sys.stderr)
        hechos += 1
    print("limpieza: %d libros listos" % hechos)
    return 0


def _etapa_segmentacion(libros, work_dir, ctx):
    """Cada limpio se segmenta con su familia en `secciones/<id>.jsonl`."""
    secciones_dir = os.path.join(work_dir, "secciones")
    limpio_dir = os.path.join(work_dir, "limpio")
    os.makedirs(secciones_dir, exist_ok=True)
    errores_ruta = os.path.join(work_dir, "errores.jsonl")
    hechos = 0
    for libro in libros:
        ruta_limpio = os.path.join(limpio_dir, libro["id"] + ".txt")
        if not os.path.exists(ruta_limpio):
            continue
        ruta_secciones = os.path.join(secciones_dir, libro["id"] + ".jsonl")
        if os.path.exists(ruta_secciones):
            hechos += 1
            continue
        with open(ruta_limpio, encoding="utf-8") as fh:
            texto = fh.read()
        secciones = libros_segmentar.segmentar(texto, libro["familia"],
                                               libro["id"])
        if not secciones:
            _anotar(errores_ruta, {"id": libro["id"], "etapa": "segmentacion",
                                   "motivo": "sin_secciones"})
            print("%s: sin secciones" % libro["id"], file=sys.stderr)
            continue
        with open(ruta_secciones, "w", encoding="utf-8") as fh:
            for seccion in secciones:
                fh.write(json.dumps(seccion, ensure_ascii=False) + "\n")
        hechos += 1
        print("%s: %d secciones" % (libro["id"], len(secciones)))
    print("segmentación: %d libros listos" % hechos)
    return 0


def _etapa_informe(libros, work_dir, ctx):
    """Delega en `libros_informe` para escribir `informe.md`."""
    ruta = os.path.join(work_dir, "informe.md")
    contenido = libros_informe.generar_informe(work_dir, ruta,
                                                knowledge_dir=ctx["knowledge_dir"])
    print("informe: %s (%d líneas)" % (ruta, contenido.count("\n")))
    return 0


class _ClienteAcotado:
    """Cliente del juez con reintentos acotados y timeout explícito.

    `juez.juzgar_seccion` llama a `chat` sin fijar `max_reintentos`, de modo
    que el valor por defecto (3) multiplicaba por cuatro el tiempo de espera
    de una sección atascada. Aquí se baja a `reintentos` sin tocar `juez.py`.
    """

    def __init__(self, cliente, reintentos=REINTENTOS_JUEZ):
        self._cliente = cliente
        self._reintentos = reintentos

    def chat(self, sistema, usuario, **kwargs):
        kwargs.setdefault("max_reintentos", self._reintentos)
        return self._cliente.chat(sistema, usuario, **kwargs)


def _cliente_juez(ctx):
    """Cliente para el juez: el explícito, uno simulado o el real."""
    if ctx.get("cliente") is not None:
        return ctx["cliente"]
    if ctx.get("simulado"):
        base = llm_client.LLMClient(simulado=juez._simular)
    else:
        base = llm_client.LLMClient(
            timeout=ctx.get("timeout") or TIMEOUT_JUEZ)
    return _ClienteAcotado(base)


def secciones_de_libros(libros, work_dir):
    """Secciones de `secciones/` que pertenecen a los libros de esta pasada.

    Sin este filtro `--solo-ids` y `--max` solo recortaban inventario,
    descarga, limpieza y segmentación: el juez seguía recorriendo las 74
    secciones del directorio (miles de secciones) aunque se pidiera una
    muestra de dos libros.
    """
    ids = {libro["id"] for libro in libros}
    return [s for s in juez.leer_secciones(os.path.join(work_dir, "secciones"))
            if s.get("id_libro") in ids]


def _etapa_juez(libros, work_dir, ctx):
    """Jueza las secciones segmentadas y anota la cobertura resultante."""
    secciones_dir = os.path.join(work_dir, "secciones")
    hay_secciones = (os.path.isdir(secciones_dir)
                     and any(fn.endswith(".jsonl") for fn in os.listdir(secciones_dir)))
    if not hay_secciones:
        print("juez: no hay secciones que juzgar", file=sys.stderr)
        return 0
    out_dir = os.path.join(work_dir, "evidencias")
    rutas_meta = []
    for patron in juez._RUTAS_META_POR_DEFECTO:
        rutas_meta.extend(sorted(glob.glob(
            os.path.join(ctx["knowledge_dir"], patron))))
    meta = juez.cargar_meta_libros(rutas_meta)
    secciones = secciones_de_libros(libros, work_dir)
    if not secciones:
        print("juez: no hay secciones de los libros seleccionados",
              file=sys.stderr)
        return 0
    errores_ruta = os.path.join(work_dir, "errores.jsonl")
    cliente = _cliente_juez(ctx)
    lote = ctx.get("lote_juez") or SECCIONES_POR_LOTE_JUEZ
    total = len(secciones)
    print("juez: %d secciones de %d libros, lotes de %d, %d workers"
          % (total, len(libros), lote, ctx["workers"]), flush=True)
    stats = {"juzgadas": 0, "llamadas": 0, "evidencias": 0,
             "reaprovechadas": 0, "sin_candidatos": 0, "error": 0,
             "lotes_fallidos": 0}
    inicio = time.monotonic()
    for desde in range(0, total, lote):
        trozo = secciones[desde:desde + lote]
        try:
            parcial = juez.procesar_secciones(trozo, cliente, out_dir,
                                              meta=meta,
                                              workers=ctx["workers"])
        except Exception as exc:
            stats["lotes_fallidos"] += 1
            _anotar(errores_ruta, {"id": "*", "etapa": "juez",
                                   "motivo": "juez_%s" % type(exc).__name__})
            print("juez: lote %d-%d falló (%s: %s), se continúa"
                  % (desde + 1, desde + len(trozo), type(exc).__name__, exc),
                  file=sys.stderr, flush=True)
            continue
        for clave in ("juzgadas", "llamadas", "evidencias", "reaprovechadas",
                      "sin_candidatos", "error"):
            stats[clave] += parcial[clave]
        # `juzgar_seccion` no propaga los fallos del endpoint: los convierte
        # en juicios `tipo=error`. Para que el operador los vea en el log de
        # incidencias del orquestador (y no solo en `juicios.jsonl`), se
        # anota aquí el número de secciones que el juez no pudo resolver.
        if parcial["error"]:
            _anotar(errores_ruta,
                    {"id": "*", "etapa": "juez",
                     "motivo": "juez_error_secciones",
                     "secciones_error": parcial["error"],
                     "desde": desde + 1, "hasta": desde + len(trozo)})
        print("juez: %d/%d secciones (%.0fs) — %d juzgadas, %d reaprovechadas,"
              " %d sin candidatos, %d errores, %d evidencias"
              % (min(desde + lote, total), total, time.monotonic() - inicio,
                 stats["juzgadas"], stats["reaprovechadas"],
                 stats["sin_candidatos"], stats["error"], stats["evidencias"]),
              flush=True)
    if stats["lotes_fallidos"]:
        print("juez: %d lotes fallidos (ver errores.jsonl)"
              % stats["lotes_fallidos"], file=sys.stderr)
    stats.pop("lotes_fallidos")
    juez.escribir_informe(out_dir, stats)
    evidencias, _ = cobertura.leer_evidencias(
        [os.path.join(out_dir, "evidencias.jsonl")])
    resumen = cobertura.calcular_cobertura(evidencias)
    print("juez: %d juzgadas, %d reaprovechadas, %d sin candidatos, "
          "%d evidencias" % (stats["juzgadas"], stats["reaprovechadas"],
                             stats["sin_candidatos"], stats["evidencias"]))
    print("cobertura: %d/%d celdas completas (%d evidencias ignoradas)"
          % (resumen["completas"], len(resumen["celdas"]), resumen["ignoradas"]))
    return 0


def _etapa_pendiente(nombre):
    def etapa(libros, work_dir, ctx):
        print("Etapa %s: aún sin implementar" % nombre, file=sys.stderr)
        return 0
    return etapa


ETAPAS_IMPLEMENTADAS = {
    "descarga": _etapa_descarga,
    "limpieza": _etapa_limpieza,
    "segmentacion": _etapa_segmentacion,
    "informe": _etapa_informe,
    "juez": _etapa_juez,
}


def plan_de_pruebas(libros, work_dir):
    """Una línea por libro: qué haría la pasada con ese libro."""
    lineas = []
    for libro in libros:
        if crudo_usable(_ruta_crudo(work_dir, libro)):
            accion = "crudo ya en disco"
        elif libro["origen"] == "epub_local":
            accion = "extraer EPUB"
        else:
            accion = "descargar"
        lineas.append("  - %s (%s, %s): %s"
                      % (libro["id"], libro["origen"], libro["idioma"], accion))
    return lineas


def ejecutar(work_dir=DEFAULT_WORK_DIR, knowledge_dir=DEFAULT_KNOWLEDGE_DIR,
             hasta="juez", solo_ids=None, max=0, pausa=2.5, workers=4,
             simulado=False, dry_run=False, cliente=None,
             timeout=TIMEOUT_JUEZ, lote_juez=None):
    """Corre las etapas hasta `hasta`. Devuelve el código de salida."""
    if hasta not in ETAPAS:
        print("Etapa desconocida: %s (válidas: %s)" % (hasta, ", ".join(ETAPAS)),
              file=sys.stderr)
        return 2
    libros = filtrar_libros(cargar_inventario(knowledge_dir), solo_ids, max)
    print("Inventario: %d libros" % len(libros))
    pendientes = pendientes_de_descarga(libros, work_dir)
    print("pendientes de descarga: %d" % len(pendientes))
    if dry_run:
        for linea in plan_de_pruebas(libros, work_dir):
            print(linea)
        print("Hasta: %s (sin tocar disco ni red)" % hasta)
        return 0
    if not libros:
        print("No hay libros que procesar.")
        return 0
    ctx = {"pausa": pausa, "workers": workers, "simulado": simulado,
           "cliente": cliente, "knowledge_dir": knowledge_dir,
           "timeout": timeout, "lote_juez": lote_juez}
    for etapa_nombre in ETAPAS[:ETAPAS.index(hasta) + 1]:
        funcion = ETAPAS_IMPLEMENTADAS.get(etapa_nombre, _etapa_pendiente(etapa_nombre))
        code = funcion(libros, work_dir, ctx)
        if code != 0:
            return code
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Orquestador de la fase 0 de libros (descarga, limpieza, "
                    "segmentación, informe y juez).")
    parser.add_argument("--work-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--knowledge-dir", default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--hasta", default="juez", choices=ETAPAS)
    parser.add_argument("--solo-ids", default="",
                        help="ids separados por comas")
    parser.add_argument("--max", type=int, default=0,
                        help="máximo de libros (0 = sin límite)")
    parser.add_argument("--pausa", type=float, default=2.5,
                        help="segundos entre descargas")
    parser.add_argument("--workers", type=int, default=4,
                        help="hilos de llamada al LLM en el juez (por "
                             "defecto: 4, como juez.py)")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_JUEZ,
                        help="timeout por petición al LLM en segundos "
                             "(por defecto: %.0f)" % TIMEOUT_JUEZ)
    parser.add_argument("--lote-juez", type=int, default=None,
                        help="secciones por lote del juez (por defecto: %d)"
                             % SECCIONES_POR_LOTE_JUEZ)
    parser.add_argument("--simulado", action="store_true",
                        help="cliente LLM simulado para el juez")
    parser.add_argument("--dry-run", action="store_true",
                        help="lista qué haría sin tocar disco ni red")
    args = parser.parse_args(argv)
    return ejecutar(work_dir=args.work_dir, knowledge_dir=args.knowledge_dir,
                    hasta=args.hasta, solo_ids=args.solo_ids or None,
                    max=args.max, pausa=args.pausa, workers=args.workers,
                    simulado=args.simulado, dry_run=args.dry_run,
                    timeout=args.timeout, lote_juez=args.lote_juez)


if __name__ == "__main__":
    sys.exit(main())
