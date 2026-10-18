#!/usr/bin/env python3
"""Clasifica la licencia de los textos brutos del corpus y decide si son usables.

Clases: publico, cc-by, cc-by-sa, cc-nc, cc-nd, desconocida.
Origenes (relativos a la raiz del corpus):
- `raw/<dominio>/<slug>.md`: licencia en `manifest.json` (lista de {url, dominio, licencia, estado}).
- `raw/docs/<familia>/<slug>.md`: licencia en `docs/manifest.json` (dict id -> {familia, licencia, ...}).
- `raw_scrapy/<dominio>/<titulo>.md`: sin licencia salvo `wikipedia.org` (CC BY-SA), via front-matter.
- `docs_epub/<tema>/*.epub`: licencia en `docs_epub/manifest.json` (dict id -> {tema, licencia, fichero}).

API: `license_of(path)`, `is_allowed(path, allowed=...)`, `configure(root)`.
Carga perezosa y cacheada de manifests; tolera manifests ausentes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

CLASES = ("publico", "cc-by", "cc-by-sa", "cc-nc", "cc-nd", "desconocida")
DEFAULT_ALLOWED = ("publico", "cc-by", "cc-by-sa")

# Sufijo que añade collect_corpus.save_page al colisionar dos slugs: _xxxx antes de la extension.
SUFIXO_COLISION = re.compile(r"_[0-9a-f]{4}(?=\.[A-Za-z0-9]+$)")

_root: Path | None = None
_cache: dict[str, str] = {}
_maps: dict[str, dict[str, str] | None] = {"raw": None, "docs": None, "epub": None}


def configure(root: str) -> None:
    """Apunta el filtro a otra raiz de corpus (los tests usan directorios temporales)."""
    global _root
    _root = Path(root).resolve()
    _cache.clear()
    for k in _maps:
        _maps[k] = None


def _raiz() -> Path:
    return _root if _root is not None else Path(__file__).resolve().parent


def domain_of(url: str) -> str:
    """Duplicado de collect_corpus.domain_of: netloc saneado para nombre de carpeta."""
    netloc = urlparse(url).netloc
    return re.sub(r"[^A-Za-z0-9.\-]", "_", netloc) or "desconocido"


def slug_of(url: str) -> str:
    """Duplicado de collect_corpus.slug_of: ultima ruta de la URL como slug."""
    path = unquote(urlparse(url).path).strip("/")
    if not path:
        return "index"
    parts = []
    for seg in path.split("/"):
        seg = re.sub(r"[^A-Za-z0-9]+", "_", seg).strip("_")
        if seg:
            parts.append(seg)
    return "_".join(parts)[-80:] or "index"


def slugify(text: str) -> str:
    """Duplicado de docs_to_md.slugify: id de libro a nombre de fichero."""
    text = text.strip().lower()
    text = re.sub(r"[^0-9a-záéíóúñü]+", "_", text)
    return text.strip("_")[:80] or "documento"


def classify_license_text(text: str) -> str:
    """Convierte el texto libre de licencia en una de las clases del contrato.

    Si el texto menciona varias licencias se aplica la mas restrictiva.
    Las marcas de duda («verificar», «varía por obra») invalidan el dominio publico.
    """
    t = (text or "").lower()
    if "verificar" in t or "varía por obra" in t:
        return "desconocida"
    if re.search(r"\bnc\b", t):
        return "cc-nc"
    if re.search(r"\bnd\b", t):
        return "cc-nd"
    if re.search(r"\bsa\b", t):
        return "cc-by-sa"
    if re.search(r"cc\s*by", t):
        return "cc-by"
    if "dominio público" in t or "public domain" in t:
        return "publico"
    return "desconocida"


def _leer_json(ruta: Path):
    try:
        with ruta.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _raw_map() -> dict[str, str]:
    if _maps["raw"] is None:
        m: dict[str, str] = {}
        manifest = _leer_json(_raiz() / "manifest.json")
        if isinstance(manifest, list):
            for it in manifest:
                if not isinstance(it, dict):
                    continue
                url = it.get("url", "")
                dominio = it.get("dominio") or domain_of(url)
                slug = slug_of(url)
                m[f"raw/{dominio}/{slug}.md"] = classify_license_text(it.get("licencia", ""))
        _maps["raw"] = m
    return _maps["raw"]


def _docs_map() -> dict[str, str]:
    if _maps["docs"] is None:
        m: dict[str, str] = {}
        manifest = _leer_json(_raiz() / "docs" / "manifest.json")
        if isinstance(manifest, dict):
            for _id, it in manifest.items():
                if not isinstance(it, dict):
                    continue
                familia = it.get("familia", "")
                slug = slugify(str(it.get("id", _id)))
                m[f"raw/docs/{familia}/{slug}.md"] = classify_license_text(it.get("licencia", ""))
        _maps["docs"] = m
    return _maps["docs"]


def _epub_map() -> dict[str, str]:
    if _maps["epub"] is None:
        m: dict[str, str] = {}
        manifest = _leer_json(_raiz() / "docs_epub" / "manifest.json")
        if isinstance(manifest, dict):
            for _id, it in manifest.items():
                if not isinstance(it, dict):
                    continue
                tema = it.get("tema", "")
                fichero = it.get("fichero", "")
                m[f"docs_epub/{tema}/{fichero}"] = classify_license_text(it.get("licencia", ""))
        _maps["epub"] = m
    return _maps["epub"]


def _buscar_con_colision(key: str, mapa: dict[str, str]) -> str | None:
    """Busca la ruta exacta y, si falla, sin el sufijo de colision `_xxxx`."""
    clase = mapa.get(key)
    if clase:
        return clase
    desnuuda = SUFIXO_COLISION.sub("", key)
    if desnuuda != key:
        return mapa.get(desnuuda)
    return None


def _clase_scrapy(key: str) -> str:
    """raw_scrapy no tiene manifest: el front-matter dice el dominio; Wikipedia es CC BY-SA."""
    ruta = _raiz() / key
    try:
        with ruta.open(encoding="utf-8", errors="replace") as f:
            lineas = [f.readline() for _ in range(30)]
    except OSError:
        return "desconocida"
    if not lineas or not lineas[0].startswith("---"):
        return "desconocida"
    dominio = ""
    for linea in lineas[1:]:
        if linea.strip() == "---":
            break
        mt = re.match(r"domain:\s*(.+?)\s*$", linea)
        if mt:
            dominio = mt.group(1)
    if dominio.endswith("wikipedia.org"):
        return "cc-by-sa"
    return "desconocida"


def _normalizar_clave(path: str) -> str:
    p = str(path).replace("\\", "/")
    raiz = str(_raiz()).rstrip("/") + "/"
    if p.startswith(raiz):
        return p[len(raiz):]
    # En macOS /var es symlink de /private/var: resolver antes de comparar prefijos.
    try:
        res = str(Path(p).resolve())
    except OSError:
        res = p
    if res.startswith(raiz):
        return res[len(raiz):]
    return p


def license_of(path: str) -> str:
    """Clase de licencia de una ruta del corpus (absoluta o relativa a la raiz)."""
    key = _normalizar_clave(path)
    if key in _cache:
        return _cache[key]
    clase = _resolver(key)
    _cache[key] = clase
    return clase


def _resolver(key: str) -> str:
    if key.startswith("raw/docs/"):
        return _buscar_con_colision(key, _docs_map()) or "desconocida"
    if key.startswith("raw/"):
        return _buscar_con_colision(key, _raw_map()) or "desconocida"
    if key.startswith("raw_scrapy/"):
        return _clase_scrapy(key)
    if key.startswith("docs_epub/"):
        return _buscar_con_colision(key, _epub_map()) or "desconocida"
    # Sin prefijo conocido: probar los origenes en orden.
    for prefijo, mapa in (("raw/", _raw_map()), ("raw/docs/", _docs_map()),
                         ("docs_epub/", _epub_map())):
        clase = _buscar_con_colision(prefijo + key, mapa)
        if clase:
            return clase
    scrapy = _clase_scrapy("raw_scrapy/" + key)
    if scrapy != "desconocida":
        return scrapy
    return "desconocida"


def is_allowed(path: str, allowed=DEFAULT_ALLOWED) -> bool:
    """True si la clase de licencia esta dentro de las permitidas."""
    return license_of(path) in set(allowed)


def _tamano_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def _recorrido(raw_dir: Path, sufijos: tuple[str, ...]):
    for p in sorted(raw_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in sufijos:
            yield p


def tabla_licencias(root: str) -> tuple[list[dict], list[tuple[str, float]]]:
    """Estadisticas por origen y clase + los ficheros no permitidos mas grandes."""
    raiz = Path(root).resolve()
    origenes = [
        ("raw", raiz / "raw", (".md",), raiz / "raw" / "docs"),
        ("raw/docs", raiz / "raw" / "docs", (".md",), None),
        ("raw_scrapy", raiz / "raw_scrapy", (".md",), None),
        ("docs_epub", raiz / "docs_epub", (".epub",), None),
    ]
    filas: list[dict] = []
    no_permitidos: list[tuple[str, float]] = []
    for nombre, carpeta, sufijos, excluir in origenes:
        conteo: dict[str, list] = {}
        if not carpeta.is_dir():
            continue
        for f in _recorrido(carpeta, sufijos):
            if excluir is not None and excluir in f.parents:
                continue
            clase = license_of(str(f))
            reg = conteo.setdefault(clase, [0, 0.0])
            reg[0] += 1
            reg[1] += _tamano_mb(f)
            if clase not in DEFAULT_ALLOWED:
                no_permitidos.append((str(f.relative_to(raiz)), _tamano_mb(f)))
        for clase in CLASES:
            if clase in conteo:
                n, mb = conteo[clase]
                filas.append({"origen": nombre, "clase": clase, "ficheros": n,
                            "mb": round(mb, 1), "permitida": clase in DEFAULT_ALLOWED})
    no_permitidos.sort(key=lambda x: -x[1])
    return filas, no_permitidos[:15]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Inventario de licencias del corpus (solo lectura).")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent),
                    help="raiz del corpus (por defecto corpus/)")
    args = ap.parse_args(argv)

    configure(args.root)
    filas, top_no_permitidos = tabla_licencias(args.root)
    print(f"origen       clase         ficheros      MB  permitida")
    for r in filas:
        print(f"{r['origen']:<12} {r['clase']:<12} {r['ficheros']:>8} {r['mb']:>8.1f}  "
              f"{'si' if r['permitida'] else 'NO'}")
    tot = sum(r["ficheros"] for r in filas)
    tot_ok = sum(r["ficheros"] for r in filas if r["permitida"])
    mb_tot = sum(r["mb"] for r in filas)
    mb_ok = sum(r["mb"] for r in filas if r["permitida"])
    print(f"{'TOTAL':<12} {'':<12} {tot:>8} {mb_tot:>8.1f}  {tot_ok} permitidos "
          f"({mb_ok:.1f} MB)")
    print("\n15 ficheros mayores NO permitidos:")
    for ruta, mb in top_no_permitidos:
        print(f"  {mb:>8.1f} MB  {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
