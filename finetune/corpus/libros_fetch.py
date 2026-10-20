"""Descarga reanudable y educada de los textos OCR de archive.org (F0.2).

Escribe en `<out-dir>/crudo/<id>.txt` y registra cada acción en `<out-dir>/fetch.jsonl`
con los campos `id, estado, bytes, intentos`. No vuelve a descargar lo que ya
existe y es válido. Ante HTTP 429 repetido hace una parada limpia con código 3.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from libros_fuentes import cargar_inventario

MIN_BYTES = 30 * 1024
MAX_INTENTOS = 4
LIMITE_429_CONSECUTIVOS = 2
BASE_ESPERA = 2.0
MAX_REDIRECCIONES = 5
DOMINIOS_PERMITIDOS = ("gutenberg.org", "archive.org", "wikisource.org",
                       "bne.es", "cervantesvirtual.com")


class ParadaLimitada(Exception):
    """El servidor devuelve 429 de forma repetida: hay que parar en seco."""


class DescargaInsegura(Exception):
    """URL fuera de la lista blanca, con credenciales o redirección no segura."""


def validar_url(url):
    """Comprueba esquema, credenciales y dominio contra la lista blanca."""
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https"):
        raise DescargaInsegura("esquema no permitido: %r" % partes.scheme)
    if not partes.netloc:
        raise DescargaInsegura("URL sin host: %r" % url)
    if "@" in partes.netloc or partes.username or partes.password:
        raise DescargaInsegura("URL con credenciales: %r" % url)
    host = (partes.hostname or "").rstrip(".").lower()
    if not host:
        raise DescargaInsegura("URL sin host válido: %r" % url)
    permitido = any(host == dominio or host.endswith("." + dominio)
                    for dominio in DOMINIOS_PERMITIDOS)
    if not permitido:
        raise DescargaInsegura("dominio no permitido: %r" % host)
    return url


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Deja que _obtener siga los saltos a mano para validar cada destino."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _obtener(url, timeout=120):
    actual = validar_url(url)
    vistos = set()
    opener = urllib.request.build_opener(_SinRedirecciones())
    for _ in range(MAX_REDIRECCIONES + 1):
        validar_url(actual)
        if actual in vistos:
            raise DescargaInsegura("bucle de redirecciones en %r" % actual)
        vistos.add(actual)
        try:
            with opener.open(actual, timeout=timeout) as resp:
                validar_url(resp.geturl())
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            destino = exc.headers.get("Location") if exc.headers else None
            if not destino:
                raise DescargaInsegura("redirección sin Location en %r"
                                       % actual)
            actual = urllib.parse.urljoin(actual, destino)
    raise DescargaInsegura("demasiadas redirecciones desde %r" % url)


def es_texto_valido(datos):
    """Más de 30 KB, no es una página HTML de error y tiene texto de verdad."""
    if not datos or len(datos) < MIN_BYTES:
        return False
    texto = datos.decode("utf-8", errors="replace")
    arranque = texto.lstrip()[:200].lower()
    if arranque.startswith(("<!doctype html", "<html")):
        return False
    return sum(1 for c in texto if c.isalpha()) > 500


def descargar_libro(libro, crud_dir):
    """Descarga un libro con reintentos y espera exponencial. Devuelve el registro."""
    ruta = os.path.join(crud_dir, libro["id"] + ".txt")
    if os.path.exists(ruta):
        with open(ruta, "rb") as fh:
            if es_texto_valido(fh.read()):
                return {"id": libro["id"], "estado": "ya_existe",
                        "bytes": os.path.getsize(ruta), "intentos": 0}
    os.makedirs(crud_dir, exist_ok=True)
    consec_429 = 0
    motivo = "desconocido"
    for intento in range(1, MAX_INTENTOS + 1):
        try:
            datos = _obtener(libro["url"])
        except DescargaInsegura:
            motivo = "url_no_permitida"
            return {"id": libro["id"], "estado": "bloqueado", "bytes": 0,
                    "intentos": intento}
        except urllib.error.HTTPError as exc:
            consec_429 = consec_429 + 1 if exc.code == 429 else 0
            motivo = "http_%d" % exc.code
            if consec_429 >= LIMITE_429_CONSECUTIVOS:
                raise ParadaLimitada(libro["id"])
        except (urllib.error.URLError, OSError):
            consec_429 = 0
            motivo = "error_de_red"
        else:
            if es_texto_valido(datos):
                with open(ruta, "wb") as fh:
                    fh.write(datos)
                return {"id": libro["id"], "estado": "ok",
                        "bytes": len(datos), "intentos": intento}
            consec_429 = 0
            motivo = "contenido_invalido"
        if intento < MAX_INTENTOS:
            time.sleep(BASE_ESPERA * (2 ** (intento - 1)))
    estado = "invalido" if motivo == "contenido_invalido" else "fallido"
    return {"id": libro["id"], "estado": estado, "bytes": 0,
            "intentos": MAX_INTENTOS}


def fetch_todos(libros, out_dir, pausa=2.5):
    """Descarga la lista de libros de archive.org. 0 si todo fue bien, 3 si 429."""
    crud_dir = os.path.join(out_dir, "crudo")
    os.makedirs(crud_dir, exist_ok=True)
    registro_ruta = os.path.join(out_dir, "fetch.jsonl")
    try:
        for i, libro in enumerate(libros):
            try:
                res = descargar_libro(libro, crud_dir)
            except ParadaLimitada:
                print("Parada por 429 repetido en %s" % libro["id"],
                      file=sys.stderr)
                return 3
            with open(registro_ruta, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(res, ensure_ascii=False) + "\n")
            print("%s: %s (%d bytes, %d intentos)"
                  % (libro["id"], res["estado"], res["bytes"], res["intentos"]))
            if i < len(libros) - 1:
                time.sleep(pausa)
    except KeyboardInterrupt:
        print("Interrumpido; vuelve a lanzar para continuar.", file=sys.stderr)
        return 130
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge-dir",
                      default=os.path.join(os.path.dirname(__file__), "..",
                                         "knowledge"))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pausa", type=float, default=2.5)
    parser.add_argument("--max", type=int, default=0,
                      help="máximo de libros a descargar (0 = sin límite)")
    parser.add_argument("--solo-ids", default="",
                      help="lista separada por comas para procesar solo esos ids")
    args = parser.parse_args(argv)

    inventario = cargar_inventario(args.knowledge_dir)
    libros = [r for r in inventario if r["origen"] == "archive" and r["url"]]
    if args.solo_ids:
        wanted = {s.strip() for s in args.solo_ids.split(",") if s.strip()}
        libros = [r for r in libros if r["id"] in wanted]
    if args.max > 0:
        libros = libros[:args.max]
    print("A descargar: %d libros" % len(libros))
    return fetch_todos(libros, args.out_dir, pausa=args.pausa)


if __name__ == "__main__":
    sys.exit(main())
