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

import libros_fetch
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


def _etapa_descarga(libros, work_dir, pausa):
    """Descarga los crudos que faltan y deja una línea de resumen en fetch.jsonl."""
    crud_dir = os.path.join(work_dir, "crudo")
    os.makedirs(crud_dir, exist_ok=True)
    pendientes = pendientes_de_descarga(libros, work_dir)
    errores_ruta = os.path.join(work_dir, "errores.jsonl")
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
        else:
            motivo = ""
        if not motivo and len(datos) >= MIN_CRUDO_BYTES and not \
                datos.lstrip()[:200].lower().startswith((b"<!doctype html", b"<html")):
            ruta = _ruta_crudo(work_dir, libro)
            with open(ruta, "wb") as fh:
                fh.write(datos)
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
    estado = "ok" if descargados else "ya_existe"
    _anotar(os.path.join(work_dir, "fetch.jsonl"),
            {"etapa": "descarga", "estado": estado, "nuevos": descargados,
             "reutilizados": len(pendientes) - descargados, "bytes": bytes_total})
    return 0


def _etapa_pendiente(nombre):
    def etapa(libros, work_dir, ctx):
        print("Etapa %s: aún sin implementar" % nombre, file=sys.stderr)
        return 0
    return etapa


def plan_de_pruebas(libros, work_dir):
    """Una línea por libro: qué haría la pasada con ese libro."""
    lineas = []
    for libro in libros:
        if libro["origen"] == "epub_local":
            accion = "extraer EPUB"
        elif crudo_usable(_ruta_crudo(work_dir, libro)):
            accion = "crudo ya en disco"
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
           "cliente": cliente}
    for etapa in ETAPAS[:ETAPAS.index(hasta) + 1]:
        if etapa == "descarga":
            code = _etapa_descarga(libros, work_dir, ctx["pausa"])
        else:
            code = _etapa_pendiente(etapa)(libros, work_dir, ctx)
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
