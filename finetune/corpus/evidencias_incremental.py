"""Ejecución incremental del tramo calidad → juez → append de evidencias.

Procesa solo las páginas web pendientes (cuyo `hash_seccion` no está ya en
`juicios.jsonl` ni en `evidencias.jsonl`), para los dominios indicados o
para todos los detectados como pendientes. Reutiliza las piezas existentes:

- `web_calidad`: auditoría determinista de cada página (banderas).
- `juez`: secciones, candidatos, juicio LLM y evidencias (reanudable,
  con flush incremental por sección).

Antes del primer append de la jornada se crea una copia de seguridad
`evidencias.jsonl.bak-AAAAMMDD` (una sola vez; no se sobreescribe).

Las páginas con banderas descalificadoras se descartan sin llamar al LLM.
El filtro de calidad mínima (3) vive en `cobertura.py`, como siempre.
"""

import argparse
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import juez
import llm_client
import web_calidad

BANDERAS_DESCALIFICADORAS = frozenset(
    {"corta", "mojibake", "ruido_navegacion", "duplicada"})

_WEB_DIR = "/Users/angelgonzalez/fase0/web"
_EVIDENCIAS = "/Users/angelgonzalez/fase0/evidencias_web/evidencias.jsonl"


def _ruta_juicios(ruta_evidencias):
    return os.path.join(os.path.dirname(ruta_evidencias), "juicios.jsonl")


def hashes_conocidos(ruta_evidencias, ruta_juicios=None):
    """Hashes ya procesados: `hash` de juicios + `hash_seccion` de evidencias."""
    if ruta_juicios is None:
        ruta_juicios = _ruta_juicios(ruta_evidencias)
    conocidos = set()
    for registro in juez._leer_jsonl(ruta_juicios):
        if registro.get("hash"):
            conocidos.add(registro["hash"])
    for evidencia in juez._leer_jsonl(ruta_evidencias):
        if evidencia.get("hash_seccion"):
            conocidos.add(evidencia["hash_seccion"])
    return conocidos


def dominios_pendientes(web_dir, ruta_evidencias, filtro=None):
    """Dominios de `web_dir` con al menos una página sin juzgar."""
    conocidos = hashes_conocidos(ruta_evidencias)
    pendientes = set()
    if not os.path.isdir(web_dir):
        return []
    for dominio in sorted(os.listdir(web_dir)):
        carpeta = os.path.join(web_dir, dominio)
        if not os.path.isdir(carpeta):
            continue
        if filtro is not None and dominio not in filtro:
            continue
        for nombre in sorted(os.listdir(carpeta)):
            if not nombre.endswith((".md", ".markdown")):
                continue
            secciones = juez._secciones_de_fichero(os.path.join(carpeta,
                                                                nombre))
            if any(juez.hash_seccion(s) not in conocidos for s in secciones):
                pendientes.add(dominio)
                break
    return sorted(pendientes)


def ensure_backup(ruta_evidencias):
    """Copia `evidencias.jsonl.bak-AAAAMMDD` una sola vez por jornada."""
    if not os.path.exists(ruta_evidencias):
        return None
    ruta_bak = "%s.bak-%s" % (ruta_evidencias,
                              date.today().strftime("%Y%m%d"))
    if os.path.exists(ruta_bak):
        return ruta_bak
    shutil.copy2(ruta_evidencias, ruta_bak)
    return ruta_bak


def ejecutar_incremento(web_dir, ruta_evidencias, cliente, dominios=None,
                        workers=1, limite=None, dry_run=False):
    """Audita calidad, juzga lo pendiente y hace append de evidencias.

    Devuelve estadísticas: paginas, pendientes, descartadas, secciones y
    (si hubo trabajo) las del juez: juzgadas, llamadas, evidencias,
    reaprovechadas, sin_candidatos, error.
    """
    conocidos = hashes_conocidos(ruta_evidencias)
    analizadas = web_calidad.analizar_paginas(web_calidad.leer_paginas(web_dir))
    secciones = []
    pendientes = 0
    descartadas = 0
    for pagina in analizadas:
        if dominios is not None and pagina.get("dominio") not in dominios:
            continue
        seccion = juez._secciones_de_fichero(pagina["ruta"])[0]
        if juez.hash_seccion(seccion) in conocidos:
            continue
        pendientes += 1
        if BANDERAS_DESCALIFICADORAS & set(pagina.get("banderas", [])):
            descartadas += 1
            continue
        secciones.append(seccion)
    stats = {"paginas": len(analizadas), "pendientes": pendientes,
             "descartadas": descartadas, "secciones": len(secciones)}
    if dry_run or not secciones:
        return stats
    ensure_backup(ruta_evidencias)
    stats.update(juez.procesar_secciones(secciones, cliente,
                                         os.path.dirname(ruta_evidencias),
                                         workers=workers, limite=limite))
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Procesa solo las páginas web pendientes de calidad y "
                    "juez, y añade evidencias de forma reanudable.")
    parser.add_argument("--web-dir", default=_WEB_DIR)
    parser.add_argument("--evidencias", default=_EVIDENCIAS)
    parser.add_argument("--dominios", default=None,
                        help="lista CSV de dominios (por defecto: todos "
                             "los pendientes)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limite", type=int, default=None)
    parser.add_argument("--simulado", action="store_true",
                        help="cliente determinista sin red (pruebas)")
    parser.add_argument("--dry-run", action="store_true",
                        help="solo informa, no escribe ni llama")
    args = parser.parse_args(argv)

    filtro = None
    if args.dominios:
        filtro = {d.strip() for d in args.dominios.split(",") if d.strip()}
    if args.simulado:
        cliente = llm_client.LLMClient(simulado=juez._simular)
    else:
        cliente = llm_client.LLMClient()
    stats = ejecutar_incremento(args.web_dir, args.evidencias, cliente,
                                dominios=filtro, workers=args.workers,
                                limite=args.limite, dry_run=args.dry_run)
    print("Páginas: %d | pendientes: %d | descartadas: %d | secciones: %d"
          % (stats["paginas"], stats["pendientes"], stats["descartadas"],
             stats["secciones"]))
    if "juzgadas" in stats:
        print("Juzgadas: %d | reaprovechadas: %d | sin candidatos: %d | "
              "llamadas: %d | evidencias nuevas: %d | errores: %d"
              % (stats["juzgadas"], stats["reaprovechadas"],
                 stats["sin_candidatos"], stats["llamadas"],
                 stats["evidencias"], stats["error"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
