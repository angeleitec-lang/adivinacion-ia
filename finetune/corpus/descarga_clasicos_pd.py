"""Descarga reanudable de las fuentes clasicas de dominio publico (T55).

Lee `finetune/knowledge/fuentes_clasicas_pd.jsonl`, comprueba que cada URL este
en la lista blanca de repositorios patrimoniales y baja el texto a
`/Users/angelgonzalez/fase0/libros/crudo/<id>.txt` (mismo esquema que
`libros_pipeline.py`). No sobrescribe ficheros existentes, guarda SHA-256 y
procedencia en `manifiesto_clasicos_pd.jsonl` y deja un resumen por pasada en
`fetch.jsonl`. Solo hace descarga y limpieza basica de HTML: no llama a ningun
LLM ni ejecuta el juez.
"""
import argparse
import datetime
import hashlib
import html.parser
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from libros_fetch import BASE_ESPERA, MAX_INTENTOS, ParadaLimitada, _obtener

DOMINIOS_PERMITIDOS = (
    "gutenberg.org",
    "archive.org",
    "wikisource.org",
    "bne.es",
    "cervantesvirtual.com",
)
MIN_BYTES = 1024
LIMITE_429_CONSECUTIVOS = 2
DEFAULT_WORK_DIR = "/Users/angelgonzalez/fase0/libros"
# En este Mac el almacen del sistema no incluye el CA del proxy local; el
# bundle de Homebrew si valida gutenberg.org. Solo se usa como reintento.
CA_LOCAL = "/opt/homebrew/etc/openssl@3/cert.pem"
DEFAULT_INVENTARIO = os.path.join(os.path.dirname(__file__), "..", "knowledge",
                                  "fuentes_clasicas_pd.jsonl")
MANIFIESTO = "manifiesto_clasicos_pd.jsonl"
ORDEN_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}


def dominio_de(url):
    """Host en minusculas, o cadena vacia si la URL no es absoluta."""
    try:
        partes = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    return (partes.hostname or "").lower()


def url_permitida(url):
    """Solo http(s) y solo dominios patrimoniales de la lista blanca."""
    if not isinstance(url, str):
        return False
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https"):
        return False
    host = (partes.hostname or "").lower()
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in DOMINIOS_PERMITIDOS)


def cargar_candidatas(ruta):
    """Lee el JSONL de fuentes y devuelve las filas con los campos minimos."""
    filas = []
    with open(ruta, encoding="utf-8") as fh:
        for numero, linea in enumerate(fh, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError as exc:
                raise ValueError("JSON invalido en %s:%d (%s)"
                                 % (ruta, numero, exc))
            if not fila.get("id") or not fila.get("url_texto"):
                raise ValueError("fila sin id o url_texto en %s:%d"
                                 % (ruta, numero))
            filas.append(fila)
    return filas


def seleccionar(candidatas, solo_ids=None, maximo=0, todas_prioridades=False):
    """Filtra verificadas y ordena por prioridad conservando el orden del fichero."""
    wanted = {s.strip() for s in (solo_ids or "").split(",") if s.strip()}
    elegidas = []
    for fila in candidatas:
        if not fila.get("verificada"):
            continue
        if wanted and fila["id"] not in wanted:
            continue
        if not todas_prioridades and fila.get("prioridad") != "alta":
            continue
        elegidas.append(fila)
    elegidas.sort(key=lambda f: ORDEN_PRIORIDAD.get(f.get("prioridad"), 9))
    if maximo and maximo > 0:
        elegidas = elegidas[:maximo]
    return elegidas


def _obtener_datos(url):
    """Reutiliza libros_fetch y, si falla el CA local, reintenta con Homebrew."""
    try:
        return _obtener(url)
    except urllib.error.URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError) \
                or not os.path.exists(CA_LOCAL):
            raise
        contexto = ssl.create_default_context(cafile=CA_LOCAL)
        with urllib.request.urlopen(url, timeout=120, context=contexto) as resp:
            return resp.read()


def _es_pagina_error(datos):
    return datos.lstrip()[:200].lower().startswith((b"<!doctype html", b"<html"))


class _ExtractorTexto(html.parser.HTMLParser):
    """Quita etiquetas y conserva el texto visible; ignora script y style."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._ignorar += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._ignorar:
            self._ignorar -= 1

    def handle_data(self, data):
        if not self._ignorar:
            self.partes.append(data)

    def texto(self):
        crudo = "".join(self.partes)
        lineas = [" ".join(linea.split()) for linea in crudo.splitlines()]
        return "\n".join(linea for linea in lineas if linea)


def html_a_texto(datos):
    """Convierte una pagina HTML en texto plano UTF-8 (limpieza basica)."""
    parser = _ExtractorTexto()
    parser.feed(datos.decode("utf-8", errors="replace"))
    parser.close()
    return parser.texto().encode("utf-8")


def _texto_aprovechable(datos):
    if not datos or len(datos) < MIN_BYTES or _es_pagina_error(datos):
        return False
    texto = datos.decode("utf-8", errors="replace")
    return sum(1 for c in texto if c.isalpha()) > 200


def sha256_de(ruta):
    digest = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _registro(fila, estado, ruta, bytes_, http, intentos):
    return {
        "id": fila["id"],
        "estado": estado,
        "bytes": bytes_,
        "sha256": sha256_de(ruta) if bytes_ else "",
        "http": http,
        "intentos": intentos,
        "fichero": ruta,
        "url_texto": fila["url_texto"],
        "familia": fila.get("familia", ""),
        "licencia_hint": fila.get("licencia_hint", ""),
        "celdas_que_cubre": fila.get("celdas_que_cubre", []),
        "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
    }


def descargar_candidata(fila, crud_dir):
    """Descarga una ficha sin pisar lo existente. Devuelve el registro del manifest."""
    if not url_permitida(fila["url_texto"]):
        raise ValueError("URL fuera de la lista blanca: %s" % fila["url_texto"])
    os.makedirs(crud_dir, exist_ok=True)
    ruta = os.path.join(crud_dir, fila["id"] + ".txt")
    if os.path.exists(ruta):
        with open(ruta, "rb") as fh:
            datos = fh.read()
        if _texto_aprovechable(datos):
            return _registro(fila, "ya_existe", ruta, len(datos), 200, 0)
        return _registro(fila, "ya_existe_invalido", ruta, 0, 0, 0)

    consec_429 = 0
    motivo = "desconocido"
    for intento in range(1, MAX_INTENTOS + 1):
        codigo = 0
        try:
            datos = _obtener_datos(fila["url_texto"])
            codigo = 200
        except urllib.error.HTTPError as exc:
            codigo = exc.code
            consec_429 = consec_429 + 1 if exc.code == 429 else 0
            motivo = "http_%d" % exc.code
            if consec_429 >= LIMITE_429_CONSECUTIVOS:
                raise ParadaLimitada(fila["id"])
        except (urllib.error.URLError, OSError, ValueError):
            consec_429 = 0
            motivo = "error_de_red"
        else:
            if fila.get("formato") == "html" or _es_pagina_error(datos):
                datos = html_a_texto(datos)
            if _texto_aprovechable(datos):
                temporal = ruta + ".tmp"
                with open(temporal, "wb") as fh:
                    fh.write(datos)
                os.replace(temporal, ruta)
                return _registro(fila, "ok", ruta, len(datos), codigo, intento)
            consec_429 = 0
            motivo = "contenido_invalido"
        if intento < MAX_INTENTOS:
            time.sleep(BASE_ESPERA * (2 ** (intento - 1)))
    estado = "invalido" if motivo == "contenido_invalido" else "fallido"
    return _registro(fila, estado, ruta, 0, 0, MAX_INTENTOS)


def _anotar(ruta_jsonl, registro):
    with open(ruta_jsonl, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")


def descargar_todas(candidatas, work_dir, pausa=1.5):
    """Descarga la lista y registra cada accion. 0 si va bien, 3 si hay 429."""
    crud_dir = os.path.join(work_dir, "crudo")
    os.makedirs(crud_dir, exist_ok=True)
    manifiesto = os.path.join(work_dir, MANIFIESTO)
    errores = os.path.join(work_dir, "errores.jsonl")
    nuevos = reutilizados = 0
    bytes_total = 0
    limitada = False
    for i, fila in enumerate(candidatas):
        try:
            res = descargar_candidata(fila, crud_dir)
        except ValueError as exc:
            _anotar(errores, {"id": fila.get("id", "?"), "etapa": "descarga_pd",
                              "motivo": "url_no_permitida", "detalle": str(exc)})
            print("%s: URL rechazada" % fila.get("id", "?"), file=sys.stderr)
            continue
        except ParadaLimitada:
            print("Parada por 429 repetido en %s" % fila["id"], file=sys.stderr)
            limitada = True
            break
        _anotar(manifiesto, res)
        if res["estado"] == "ok":
            nuevos += 1
            bytes_total += res["bytes"]
        elif res["estado"] == "ya_existe":
            reutilizados += 1
        else:
            _anotar(errores, {"id": fila["id"], "etapa": "descarga_pd",
                              "motivo": res["estado"]})
        print("%s: %s (%d bytes)" % (fila["id"], res["estado"], res["bytes"]))
        if i < len(candidatas) - 1 and pausa > 0:
            time.sleep(pausa)
    estado = "limitada" if limitada else ("ok" if nuevos else "ya_existe")
    _anotar(os.path.join(work_dir, "fetch.jsonl"),
            {"etapa": "descarga_clasicos_pd", "estado": estado, "nuevos": nuevos,
             "reutilizados": reutilizados, "bytes": bytes_total})
    return 3 if limitada else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventario", default=DEFAULT_INVENTARIO)
    parser.add_argument("--out-dir", default=DEFAULT_WORK_DIR)
    parser.add_argument("--pausa", type=float, default=1.5)
    parser.add_argument("--max", type=int, default=0,
                        help="maximo de fichas (0 = todas las de prioridad alta)")
    parser.add_argument("--solo-ids", default="",
                        help="lista separada por comas para procesar solo esos ids")
    parser.add_argument("--todas-prioridades", action="store_true",
                        help="incluye tambien prioridad media y baja")
    args = parser.parse_args(argv)

    candidatas = cargar_candidatas(args.inventario)
    elegidas = seleccionar(candidatas, solo_ids=args.solo_ids, maximo=args.max,
                           todas_prioridades=args.todas_prioridades)
    print("A descargar: %d fuentes" % len(elegidas))
    return descargar_todas(elegidas, args.out_dir, pausa=args.pausa)


if __name__ == "__main__":
    sys.exit(main())
