"""Aplica el catalogo astro ampliado (T145) sin tocar los datos reales de fase0.

Genera en ``/Users/angelgonzalez/fase0/catalogo_astro_aplicado/``:

- ``evidencias_catalogo_astro.jsonl``: evidencias remapeadas R1-R3 (casa desde
  planeta_en_casa, elemento y modalidad desde signo) en el formato que lee
  ``cobertura_v3.py --extra``. Determinista e idempotente (sobrescribe).
- ``cobertura_v3_nueva/``: reconstruccion de la matriz v3 con las fuentes de
  T140 (ver docs/CIERRE_2.md) mas el fichero nuevo, en un directorio NUEVO.
  El ``cobertura_v3`` oficial nunca se sobrescribe desde aqui.

Reglas: sin LLM, sin nodos, todo determinista.
"""

import argparse
import json
import os
import sys

import catalogo_astro_propuesta as cap
import cobertura_v3

FASE0 = "/Users/angelgonzalez/fase0"
DESTINO = os.path.join(FASE0, "catalogo_astro_aplicado")
EVIDENCIAS_OUT = os.path.join(DESTINO, "evidencias_catalogo_astro.jsonl")
V3_NUEVA_DIR = os.path.join(DESTINO, "cobertura_v3_nueva")
V3_OFICIAL = os.path.join(FASE0, "cobertura_v3", "cobertura_total_v3.json")

# Fuentes exactas de la reconstruccion T140 (docs/CIERRE_2.md).
FUENTES_T140 = {
    "web": cobertura_v3.RUTAS["web"],
    "libros_limpio": cobertura_v3.RUTAS["libros_limpio"],
    "claves_excluir": cobertura_v3.RUTAS["claves_excluir"],
    "v2": cobertura_v3.RUTAS["v2"],
    "extra": [
        os.path.join(FASE0, "txt_naipes_tarot", "evidencias",
                    "evidencias.jsonl"),
        os.path.join(FASE0, "txt_ocultismo_numerologia", "evidencias",
                    "evidencias.jsonl"),
        os.path.join(FASE0, "libros_comprados_baraja", "evidencias",
                    "evidencias_baraja.jsonl"),
    ],
}

# Directorios reales que jamas se escriben desde este modulo.
RUTAS_PROTEGIDAS = [
    os.path.join(FASE0, "cobertura_v3"),
    os.path.join(FASE0, "libros_limpio"),
    os.path.join(FASE0, "evidencias_web"),
    os.path.join(FASE0, "libros_comprados_astro"),
]


def _ruta_protegida(ruta):
    """Devuelve la ruta protegida que contiene a `ruta`, o None."""
    ruta_abs = os.path.abspath(ruta)
    for protegida in RUTAS_PROTEGIDAS:
        p_abs = os.path.abspath(protegida)
        if ruta_abs == p_abs or ruta_abs.startswith(p_abs + os.sep):
            return protegida
    return None


def leer_afirmaciones_t119(ruta=cap.AFIRMACIONES_T119):
    """Lee las afirmaciones T119 (JSONL). Lista vacia si no existe."""
    afirmaciones = []
    try:
        archivo = open(ruta, encoding="utf-8")
    except FileNotFoundError:
        return afirmaciones
    with archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue
            try:
                obj = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                afirmaciones.append(obj)
    return afirmaciones


def generar_evidencias(afirmaciones, destino):
    """Escribe las evidencias remapeadas R1-R3 en `destino` (JSONL).

    Orden determinista (entidad, faceta, fuente, regla) para que la doble
    aplicacion produzca bytes identicos. Rechaza destinos dentro de rutas
    protegidas. Devuelve el numero de evidencias escritas.
    """
    protegida = _ruta_protegida(destino)
    if protegida:
        raise ValueError(
            "destino dentro de ruta protegida: %s" % protegida)
    evidencias = cap.evidencias_remapeadas(afirmaciones)
    evidencias.sort(key=lambda e: (e.get("entidad_id", ""),
                                  e.get("faceta", ""),
                                  e.get("fuente_id", ""),
                                  e.get("regla", "")))
    carpeta = os.path.dirname(os.path.abspath(destino))
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        for ev in evidencias:
            f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")
    return len(evidencias)


def reconstruir_v3(dest_dir, extra_evidencias):
    """Reconstruye la matriz v3 (fuentes T140 + extra) en `dest_dir`.

    No toca el cobertura_v3 oficial. Devuelve el dict de la matriz nueva.
    """
    protegida = _ruta_protegida(dest_dir)
    if protegida:
        raise ValueError(
            "destino dentro de ruta protegida: %s" % protegida)
    claves = cobertura_v3.cargar_claves_exclusion(
        FUENTES_T140["claves_excluir"])
    extras = list(FUENTES_T140["extra"]) + [extra_evidencias]
    datos = cobertura_v3.construir_v3(
        FUENTES_T140["web"], FUENTES_T140["libros_limpio"],
        claves=claves, extra_rutas=extras, calidad_min=3,
        ruta_v2=FUENTES_T140["v2"])
    os.makedirs(dest_dir, exist_ok=True)
    cobertura_v3.escribir_json(
        datos, os.path.join(dest_dir, "cobertura_total_v3.json"))
    cobertura_v3.escribir_md(
        datos, os.path.join(dest_dir, "cobertura_total_v3.md"))
    return datos


def comparar(ruta_oficial=V3_OFICIAL, ruta_nueva=None):
    """Compara los resumenes antes (oficial) y despues (nueva)."""
    if ruta_nueva is None:
        ruta_nueva = os.path.join(V3_NUEVA_DIR, "cobertura_total_v3.json")
    with open(ruta_oficial, encoding="utf-8") as f:
        antes = json.load(f)["resumen"]
    with open(ruta_nueva, encoding="utf-8") as f:
        despues = json.load(f)["resumen"]
    return {
        "antes": {"total_celdas": antes["total_celdas"],
                 "completas": antes["completas"],
                 "ignoradas": antes["ignoradas"]},
        "despues": {"total_celdas": despues["total_celdas"],
                   "completas": despues["completas"],
                   "ignoradas": despues["ignoradas"]},
        "delta_celdas": despues["total_celdas"] - antes["total_celdas"],
        "delta_completas": despues["completas"] - antes["completas"],
    }


def ejecutar(destino=DESTINO):
    """Aplicacion completa en el directorio nuevo. Idempotente."""
    protegida = _ruta_protegida(destino)
    if protegida:
        raise ValueError("destino dentro de ruta protegida: %s" % protegida)
    evid_out = os.path.join(destino, "evidencias_catalogo_astro.jsonl")
    v3_dir = os.path.join(destino, "cobertura_v3_nueva")
    n_ev = generar_evidencias(leer_afirmaciones_t119(), evid_out)
    reconstruir_v3(v3_dir, evid_out)
    comp = comparar(ruta_nueva=os.path.join(v3_dir,
                                          "cobertura_total_v3.json"))
    return {"evidencias": n_ev, "comparacion": comp,
            "destino": destino}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aplica el catalogo astro ampliado (T145) en un "
                    "directorio nuevo de fase0 (nunca sobre el real).")
    parser.add_argument("--dest", default=DESTINO,
                       help="directorio de salida (fuera de rutas reales)")
    parser.add_argument("--solo-evidencias", action="store_true",
                       help="solo genera el JSONL remapeado, sin v3")
    args = parser.parse_args(argv)
    if args.solo_evidencias:
        protegida = _ruta_protegida(args.dest)
        if protegida:
            print("ERROR: destino protegido: %s" % protegida,
                  file=sys.stderr)
            return 1
        n = generar_evidencias(
            leer_afirmaciones_t119(),
            os.path.join(args.dest, "evidencias_catalogo_astro.jsonl"))
        print("Evidencias remapeadas: %d" % n)
        return 0
    res = ejecutar(args.dest)
    c = res["comparacion"]
    print("Evidencias remapeadas: %d" % res["evidencias"])
    print("Antes: %d celdas, %d completas" % (
        c["antes"]["total_celdas"], c["antes"]["completas"]))
    print("Despues: %d celdas, %d completas (delta celdas %+d, "
          "completas %+d)" % (
              c["despues"]["total_celdas"], c["despues"]["completas"],
              c["delta_celdas"], c["delta_completas"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
