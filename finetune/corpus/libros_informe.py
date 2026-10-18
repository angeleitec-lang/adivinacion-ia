"""Informe de calidad de los libros limpios y segmentados (F0.2).

Lee `limpio/<id>.txt`, `crudo/<id>.txt` y `secciones/<id>.jsonl` de un
directorio de salida, recalcula las métricas de limpieza sobre el crudo y
escribe una tabla por libro más un resumen global en Markdown, marcando los
libros que requieren revisión humana.
"""
import argparse
import os
import re
import sys
import unicodedata

from libros_fuentes import cargar_inventario
from libros_limpiar import PALABRAS_COMUNES, limpiar

IDIOMA_MINIMO = 0.15
CABECERA = ("| Libro | Idioma | Chars | Págs. descartadas | Ratio comunes | "
            "Secciones | Calidad baja | Revisión |")
SEPARADOR = "|---|---|---:|---:|---:|---:|---|---|"


def _normalizar(palabra):
    base = unicodedata.normalize("NFKD", palabra.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def _idioma_detectado(texto):
    """Heurística simple por palabras funcionales; devuelve (idioma, ratios)."""
    palabras = [_normalizar(p)
                for p in re.findall(r"[^\W\d_]+", texto[:30000], re.UNICODE)]
    if not palabras:
        return "desconocido", {}
    ratios = {}
    for idioma, comunes in PALABRAS_COMUNES.items():
        ratios[idioma] = sum(1 for p in palabras if p in comunes) / len(palabras)
    mejor = max(ratios, key=ratios.get)
    if ratios[mejor] < IDIOMA_MINIMO:
        return "desconocido", ratios
    return mejor, ratios


def _leer(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def _contar_lineas(ruta):
    if not os.path.exists(ruta):
        return 0
    with open(ruta, encoding="utf-8") as fh:
        return sum(1 for linea in fh if linea.strip())


def _metadatos(knowledge_dir):
    if not knowledge_dir or not os.path.isdir(knowledge_dir):
        return {}
    return {libro["id"]: libro for libro in cargar_inventario(knowledge_dir)}


def _celda(texto):
    return str(texto).replace("|", "\\|")


def _ids_limpios(in_dir):
    limpio_dir = os.path.join(in_dir, "limpio")
    if not os.path.isdir(limpio_dir):
        return []
    return sorted(nombre[:-4] for nombre in os.listdir(limpio_dir)
                  if nombre.endswith(".txt"))


def _fila_libro(libro_id, in_dir, metadatos):
    limpio_path = os.path.join(in_dir, "limpio", libro_id + ".txt")
    crudo_path = os.path.join(in_dir, "crudo", libro_id + ".txt")
    secciones_path = os.path.join(in_dir, "secciones", libro_id + ".jsonl")
    texto = _leer(limpio_path)
    datos = metadatos.get(libro_id, {})
    titulo = datos.get("titulo") or libro_id
    idioma = datos.get("idioma") or "?"

    informe = {}
    if os.path.exists(crudo_path):
        _, informe = limpiar(_leer(crudo_path), idioma)

    detectado, _ = _idioma_detectado(texto)
    calidad = informe.get("calidad_baja")
    descartadas = informe.get("paginas_descartadas", 0)
    total_paginas = informe.get("paginas_total", 0)
    ratio = informe.get("ratio_comunes")
    n_secciones = _contar_lineas(secciones_path)

    motivos = []
    if calidad:
        motivos.append("calidad baja")
    if (idioma != "?" and detectado != "desconocido"
            and idioma[:2].lower() != detectado[:2]):
        motivos.append("idioma no coincide (detectado %s)" % detectado)
    if total_paginas and descartadas / total_paginas > 0.5:
        motivos.append("muchas páginas descartadas (%d/%d)"
                       % (descartadas, total_paginas))
    if not datos:
        motivos.append("sin metadatos en el inventario")
    if n_secciones == 0:
        motivos.append("sin secciones")

    return {
        "id": libro_id,
        "titulo": titulo,
        "idioma": idioma,
        "chars": len(texto),
        "descartadas": descartadas,
        "ratio": ratio,
        "secciones": n_secciones,
        "calidad_baja": calidad,
        "motivos": motivos,
    }


def _tabla(filas):
    lineas = [CABECERA, SEPARADOR]
    for fila in filas:
        ratio = "—" if fila["ratio"] is None else "%.2f" % fila["ratio"]
        calidad = ("sí" if fila["calidad_baja"] else "no"
                   if fila["calidad_baja"] is not None else "—")
        revision = "sí" if fila["motivos"] else "no"
        lineas.append("| %s | %s | %d | %d | %s | %d | %s | %s |" % (
            _celda(fila["titulo"]), _celda(fila["idioma"]), fila["chars"],
            fila["descartadas"], ratio, fila["secciones"], calidad, revision))
    return "\n".join(lineas)


def _resumen(filas):
    total_chars = sum(f["chars"] for f in filas)
    total_descartadas = sum(f["descartadas"] for f in filas)
    ratios = [f["ratio"] for f in filas if f["ratio"] is not None]
    media = sum(ratios) / len(ratios) if ratios else 0.0
    bajas = sum(1 for f in filas if f["calidad_baja"])
    revision = sum(1 for f in filas if f["motivos"])
    idiomas = {}
    for fila in filas:
        idiomas[fila["idioma"]] = idiomas.get(fila["idioma"], 0) + 1
    reparto = ", ".join("%s: %d" % (clave, valor)
                        for clave, valor in sorted(idiomas.items()))
    return "\n".join([
        "## Resumen global",
        "",
        "- Libros analizados: %d" % len(filas),
        "- Caracteres limpios: %d" % total_chars,
        "- Páginas descartadas: %d" % total_descartadas,
        "- Ratio medio de palabras comunes: %.2f" % media,
        "- Libros con calidad baja: %d" % bajas,
        "- Libros a revisar: %d" % revision,
        "- Idiomas declarados: %s" % (reparto or "—"),
    ])


def generar_informe(in_dir, out_path, knowledge_dir=None):
    """Genera el informe Markdown y devuelve su contenido."""
    if knowledge_dir is None:
        knowledge_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "knowledge")
    metadatos = _metadatos(knowledge_dir)
    filas = [_fila_libro(libro_id, in_dir, metadatos)
             for libro_id in _ids_limpios(in_dir)]

    lineas = ["# Informe de calidad de libros", "",
              _tabla(filas), "", _resumen(filas), "",
              "## Libros que requieren revisión humana", ""]
    revisables = [fila for fila in filas if fila["motivos"]]
    if revisables:
        for fila in revisables:
            lineas.append("- **%s** (%s): %s" % (
                fila["titulo"], fila["id"], "; ".join(fila["motivos"])))
    else:
        lineas.append("Ninguno.")
    contenido = "\n".join(lineas) + "\n"

    carpeta = os.path.dirname(os.path.abspath(out_path))
    if carpeta and not os.path.isdir(carpeta):
        os.makedirs(carpeta)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(contenido)
    return contenido


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Informe de calidad de los libros limpios.")
    parser.add_argument("--in-dir", required=True,
                        help="directorio con crudo/, limpio/ y secciones/")
    parser.add_argument("--out", required=True, help="fichero Markdown de salida")
    parser.add_argument("--knowledge-dir", default=None,
                        help="directorio knowledge/ con los inventarios")
    args = parser.parse_args(argv)

    if not os.path.isdir(os.path.join(args.in_dir, "limpio")):
        print("ERROR: no existe %s" % os.path.join(args.in_dir, "limpio"),
              file=sys.stderr)
        return 2
    generar_informe(args.in_dir, args.out, args.knowledge_dir)
    print("Informe escrito en %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
