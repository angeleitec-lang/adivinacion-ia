"""Extracción de texto plano desde EPUB locales (F0.2).

Recorre los `.xhtml/.html/.htm` en el orden del `spine` del OPF (si no hay OPF,
orden alfabético), ignora `script`/`style`/`nav`, conserva párrafos y convierte
los encabezados `h1`-`h4` en líneas precedidas por `#`. Salta ficheros de más de
6 MB y devuelve métricas del proceso.
"""
import os
import posixpath
import sys
import zipfile

from lxml import etree

MAX_FICHERO = 6 * 1024 * 1024
EXTENSIONES_HTML = (".xhtml", ".html", ".htm")
BLOQUES = {"p", "div", "li", "blockquote", "section", "article", "td",
           "dd", "dt", "figcaption"}


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _plano(el):
    """Texto de un elemento conservando saltos de <br>."""
    partes = []
    if el.text:
        partes.append(el.text)
    for hijo in el:
        if _local(hijo.tag) == "br":
            partes.append("\n")
        else:
            partes.append(_plano(hijo))
        if hijo.tail:
            partes.append(hijo.tail)
    return "".join(partes)


def _es_bloque(tag):
    return tag in BLOQUES or tag in ("h1", "h2", "h3", "h4", "h5", "h6")


def _bloques_cuerpo(cuerpo):
    """Bloques de texto de <body> en orden de documento.

    Incluye el texto suelto y el de nodos en línea (`b`, `span`, `font`…) que
    no van dentro de un `<p>`/`<div>`; así los avisos de OCR de los EPUB no se
    pierden y quedan en su propia línea.
    """
    bloques = []
    buffer = []

    def volcar():
        texto = " ".join("".join(buffer).split())
        if texto:
            bloques.append(texto)
        buffer.clear()

    def recorrer(nodo):
        if nodo.text:
            buffer.append(nodo.text)
        for hijo in nodo:
            loc = _local(hijo.tag)
            if loc in ("script", "style", "nav"):
                pass
            elif loc in ("h1", "h2", "h3", "h4"):
                volcar()
                texto = " ".join(_plano(hijo).split())
                if texto:
                    bloques.append("#" * int(loc[1]) + " " + texto)
            elif _es_bloque(loc):
                volcar()
                if any(_es_bloque(_local(x.tag)) for x in hijo):
                    recorrer(hijo)
                    volcar()
                else:
                    texto = " ".join(_plano(hijo).split())
                    if texto:
                        bloques.append(texto)
            else:
                texto = _plano(hijo)
                if texto:
                    buffer.append(texto)
            if hijo.tail:
                buffer.append(hijo.tail)

    recorrer(cuerpo)
    volcar()
    return bloques


def _orden_spine(zf):
    """Nombres dentro del zip en el orden del spine; None si no hay OPF."""
    try:
        cont = etree.fromstring(zf.read("META-INF/container.xml"))
    except (KeyError, etree.XMLSyntaxError):
        return None
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = cont.find(".//c:rootfile", ns)
    if rootfile is None:
        return None
    opf = rootfile.get("full-path")
    try:
        paquete = etree.fromstring(zf.read(opf))
    except (KeyError, etree.XMLSyntaxError):
        return None
    pns = {"o": "http://www/idpf.org/opf/"}
    hrefs = {}
    for item in paquete.findall(".//o:manifest/o:item", pns):
        hrefs[item.get("id")] = item.get("href")
    orden = []
    for ref in paquete.findall(".//o:spine/o:itemref", pns):
        href = hrefs.get(ref.get("idref"))
        if not href:
            continue
        nombre = posixpath.normpath(posixpath.join(posixpath.dirname(opf), href))
        if nombre.lower().endswith(EXTENSIONES_HTML) and nombre in zf.namelist():
            orden.append(nombre)
    return orden or None


def epub_a_texto(ruta):
    """Devuelve (texto, metricas) para un EPUB. Sin red, sin escribir nada."""
    metricas = {"n_html": 0, "n_imagenes": 0, "chars": 0, "drm": False}
    partes = []
    with zipfile.ZipFile(ruta) as zf:
        nombres = zf.namelist()
        if "META-INF/encryption.xml" in nombres or any(
                n.endswith(".drm") for n in nombres):
            metricas["drm"] = True
        orden = _orden_spine(zf)
        if orden is None:
            orden = sorted(n for n in nombres
                          if n.lower().endswith(EXTENSIONES_HTML))
        for nombre in orden:
            try:
                info = zf.getinfo(nombre)
            except KeyError:
                continue
            if info.file_size > MAX_FICHERO:
                continue
            parser = etree.XMLParser(recover=True, resolve_entities=False,
                                   huge_tree=False)
            try:
                arbol = etree.fromstring(zf.read(nombre), parser=parser)
            except etree.XMLSyntaxError:
                continue
            if arbol is None:
                continue
            for el in list(arbol.iter()):
                if _local(el.tag) in ("script", "style", "nav"):
                    padre = el.getparent()
                    if padre is not None:
                        if el.tail:
                            padre.text = (padre.text or "") + el.tail
                        padre.remove(el)
            metricas["n_imagenes"] += sum(1 for el in arbol.iter()
                                         if _local(el.tag) == "img")
            cuerpo = arbol.find(".//{http://www.w3.org/1999/xhtml}body")
            if cuerpo is None:
                cuerpo = arbol.find(".//body")
            if cuerpo is None:
                cuerpo = arbol
            bloques = _bloques_cuerpo(cuerpo)
            if not bloques:
                t = _plano(cuerpo).strip()
                if t:
                    bloques.append(t)
            if bloques:
                metricas["n_html"] += 1
                partes.append("\n\n".join(bloques))
    texto = "\n\n".join(partes)
    metricas["chars"] = len(texto)
    return texto, metricas


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        t, m = epub_a_texto(arg)
        print(arg, m)
