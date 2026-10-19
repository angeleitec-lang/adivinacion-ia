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
import json
import os
import sys
import time
import urllib.error

import libros_extraer
import libros_fetch
import libros_informe
import libros_limpiar
import libros_segmentar
from libros_fuentes import (ARCHIVE_FILES, DECISIONES_OK, EPUB_FILE, ESTADOS_OK,
                            _leer_jsonl, _normalizar_archive, _normalizar_epub,
                            normalizar_titulo)

ETAPAS = ("descarga", "limpieza", "segmentacion", "informe", "juez")
DEFAULT_WORK_DIR = "/Users/angelgonzalez/fase0/libros"
DEFAULT_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")
# Umbral del orquestador: más laxo que el de libros_fetch (OCR incompleto),
# solo evita guardar páginas de error o ficheros vacíos.
MIN_CRUDO_BYTES = 1024


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
        if i < len(pendientes) - 1 and pausa > 0:
            time.sleep(pausa)
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
    estado = "ok" if descargados else "ya_existe"
    _anotar(os.path.join(work_dir, "fetch.jsonl"),
            {"etapa": "descarga", "estado": estado, "nuevos": descargados,
             "reutilizados": len(pendientes) - descargados, "bytes": bytes_total})
    return 0


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
             hasta="juez", solo_ids=None, max=0, pausa=2.5, workers=1,
             simulado=False, dry_run=False, cliente=None):
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
           "cliente": cliente, "knowledge_dir": knowledge_dir}
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
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--simulado", action="store_true",
                        help="cliente LLM simulado para el juez")
    parser.add_argument("--dry-run", action="store_true",
                        help="lista qué haría sin tocar disco ni red")
    args = parser.parse_args(argv)
    return ejecutar(work_dir=args.work_dir, knowledge_dir=args.knowledge_dir,
                    hasta=args.hasta, solo_ids=args.solo_ids or None,
                    max=args.max, pausa=args.pausa, workers=args.workers,
                    simulado=args.simulado, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
