#!/usr/bin/env python3
"""Descubridor de fuentes nuevas (T74).

Dado un dominio y un patrón, recorre su ``sitemap.xml`` (o índice de sitemaps)
respetando ``robots.txt`` y la tasa de cortesía, y escribe las URLs candidatas
en un plan compatible con :mod:`recuperacion_descarga` (JSONL con entradas
``{entidad_id, familia, nombre, urls_candidatas:[{url}]}``).

Los dominios descubiertos aquí no están en ``knowledge/sitios_indice_es.json``,
de modo que ``recuperacion_descarga`` los trata como páginas directas y las
descarga tal cual. No se usa ningún LLM: el descubrimiento es puramente
estructural (sitemaps + regex + robots).

Nunca se salta un bloqueo: los dominios con bloqueo conocido (astro.com,
nymero.org, Reddit) se descartan antes de cualquier petición.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "adivinacion-ia-corpus/1.0 (investigacion local)"

DOMINIOS_BLOQUEADOS = frozenset({"astro.com", "nymero.org", "reddit.com"})

# Fuentes candidatas descubiertas y verificadas en T74 (baraja española y
# numerología en español, más el arreglo de las rutas 404 de tarot en inglés).
# Cada fuente: dominio, sitemap raíz, patrón de URL útil y familia.
FUENTES_DEF = [
    # --- Baraja española (prioritaria) ---
    {
        "dominio": "tarotamigo.com",
        "sitemap": "https://www.tarotamigo.com/sitemap.xml",
        "patron": r"tarotamigo\.com/tarot/significado-cartas/baraja-espanola/",
        "familia": "baraja_espanola",
    },
    {
        "dominio": "tarotgratuito.net",
        "sitemap": "https://www.tarotgratuito.net/sitemap.xml",
        "patron": r"tarotgratuito\.net/(tarot-baraja-espanola|el-[^/]*de-(oro|copas|espada|basto)[s]?-tarot)",
        "familia": "baraja_espanola",
    },
    {
        "dominio": "annacasas.es",
        "sitemap": "https://annacasas.es/sitemap_index.xml",
        "patron": r"annacasas\.es/(significado-[^/]*baraja-espanola|el-[^/]*de-(oro|copas|espadas|bastos)-en-una-lectura|(sota|caballo|rey|reyina)-de-(oro|copas|espadas|bastos))",
        "familia": "baraja_espanola",
    },
    {
        "dominio": "tiradadetarot.com",
        "sitemap": "https://tiradadetarot.com/sitemap.xml",
        "patron": r"tiradadetarot\.com/(cartas-espanolas|tirada/cartas-espanolas)",
        "familia": "baraja_espanola",
    },
    # --- Numerología (prioritaria) ---
    {
        "dominio": "thenumerologypower.com",
        "sitemap": "https://thenumerologypower.com/sitemap_index.xml",
        "patron": r"thenumerologypower\.com/.*numerolog",
        "familia": "numerologia",
    },
    {
        "dominio": "nohemia.com",
        "sitemap": "https://nohemia.com/sitemap-index.xml",
        "patron": r"nohemia\.com/es/glosario/numerologia/",
        "familia": "numerologia",
    },
    {
        "dominio": "astralsagehub.com",
        "sitemap": "https://astralsagehub.com/sitemap.xml",
        "patron": r"astralsagehub\.com/es-es/.*numerolog",
        "familia": "numerologia",
    },
    {
        "dominio": "numerologic.app",
        "sitemap": "https://numerologic.app/sitemap.xml",
        "patron": r"numerologic\.app/es/",
        "familia": "numerologia",
    },
    # --- Tarot: arreglo de rutas 404 de T64 (inglés) ---
    {
        "dominio": "biddytarot.com",
        "sitemap": "https://biddytarot.com/sitemap.xml",
        "patron": r"biddytarot\.com/blog/.*tarot-card-meaning",
        "familia": "tarot",
    },
    {
        "dominio": "labyrinthos.co",
        "sitemap": "https://labyrinthos.co/sitemap.xml",
        "patron": r"labyrinthos\.co/blogs/(tarot-card-meanings-list|learn-tarot-with-labyrinthos-academy)/.*meaning",
        "familia": "tarot",
    },
]

_LOCS_RE = re.compile(r"(?is)<loc>\s*(.*?)\s*</loc>")


def norm_dominio(netloc: str) -> str:
    """Normaliza un netloc: minúsculas, sin ``www.`` y sin puerto."""
    host = (netloc or "").split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def dominios_bloqueados() -> frozenset:
    return DOMINIOS_BLOQUEADOS


def extraer_locs(xml_text: str) -> list:
    """Devuelve el contenido de todas las etiquetas ``<loc>`` de un sitemap."""
    return [u.strip() for u in _LOCS_RE.findall(xml_text or "") if u.strip()]


def es_sitemap_index(xml_text: str) -> bool:
    """True si el XML es un índice de sitemaps (``<sitemapindex>``)."""
    return "sitemapindex" in (xml_text or "")[:2000]


def fabrica_robots(cliente, dominio: str, sleep=time.sleep):
    """Devuelve ``callable(url) -> bool`` según el robots.txt del dominio.

    Se apoya en el cliente HTTP para leer ``robots.txt``. Si no se puede leer
    (404/robo), se permite todo, que es el comportamiento estándar de un
    robot respetuoso cuando no hay directrices.
    """
    rp = RobotFileParser()
    rp.set_url(f"https://{dominio}/robots.txt")
    try:
        resp = cliente.get(f"https://{dominio}/robots.txt")
        sleep(0)
        if resp and resp.get("estado") == "ok" and resp.get("html"):
            rp.parse(resp["html"].splitlines())
            return lambda url: rp.can_fetch(USER_AGENT, url)
    except Exception:
        pass
    return lambda url: True


def descubrir_desde_sitemap(
    cliente,
    sitemap_url: str,
    patron: str,
    limite: int = 200,
    robots=None,
    sleep=time.sleep,
    _profundidad: int = 0,
) -> list:
    """Recorre un sitemap (o índice recursivo) y devuelve URLs que casan con el patrón.

    - Respeta ``robots`` (callable) y el ``limite`` de URLs.
    - Si el documento es un ``<sitemapindex>``, desciende a los sub-sitemaps.
    - Devuelve una lista ordenada de URLs únicas.
    """
    if limite <= 0 or _profundidad > 3:
        return []
    regex = re.compile(patron) if isinstance(patron, str) else patron
    dominio_raiz = norm_dominio(urlsplit(sitemap_url).netloc)
    vistos = set()
    salida = []

    def _procesar_doc(url_doc: str) -> None:
        nonlocal salida
        if len(salida) >= limite:
            return
        resp = cliente.get(url_doc)
        sleep(1.2)
        if not resp or resp.get("estado") != "ok":
            return
        xml = resp.get("html") or ""
        locs = extraer_locs(xml)
        if es_sitemap_index(xml):
            for sub in locs:
                if len(salida) >= limite:
                    break
                _procesar_doc(sub)
            return
        for loc in locs:
            if len(salida) >= limite:
                break
            if loc in vistos:
                continue
            vistos.add(loc)
            if norm_dominio(urlsplit(loc).netloc) != dominio_raiz:
                continue
            if not regex.search(loc):
                continue
            if robots is not None and not robots(loc):
                continue
            salida.append(loc)

    _procesar_doc(sitemap_url)
    return salida


def construir_plan(fuentes, cliente, max_por_dominio=60, sleep=time.sleep,
                  robots_fn=fabrica_robots):
    """Descubre candidatas por fuente y devuelve ``{familia: [urls]}``."""
    por_familia = {}
    bloqueados = dominios_bloqueados()
    for f in fuentes:
        dominio = norm_dominio(f["dominio"])
        if dominio in bloqueados:
            continue
        robots = robots_fn(cliente, dominio, sleep=sleep)
        urls = descubrir_desde_sitemap(
            cliente, f["sitemap"], f["patron"],
            limite=max_por_dominio, robots=robots, sleep=sleep,
        )
        for u in urls:
            bucket = por_familia.setdefault(f["familia"], [])
            if u not in bucket:
                bucket.append(u)
    return por_familia


def escribir_plan(por_familia, ruta) -> int:
    """Escribe el plan JSONL compatible con recuperacion_descarga. Devuelve nº de URLs."""
    total = 0
    lineas = []
    for familia in sorted(por_familia):
        urls = por_familia[familia]
        if not urls:
            continue
        entrada = {
            "entidad_id": f"t74_{familia}",
            "familia": familia,
            "nombre": f"Fuentes nuevas T74 ({familia})",
            "urls_candidatas": [{"url": u} for u in urls],
        }
        lineas.append(json.dumps(entrada, ensure_ascii=False))
        total += len(urls)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + ("\n" if lineas else ""))
    return total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Descubre fuentes nuevas y escribe un plan T74.")
    ap.add_argument("--out", default="/Users/angelgonzalez/fase0/plan_t74.jsonl",
                    help="Ruta del plan JSONL de salida.")
    ap.add_argument("--max-por-dominio", type=int, default=60,
                    help="Máximo de URLs candidatas por dominio.")
    args = ap.parse_args(argv)

    from web_fetch import Cliente
    cliente = Cliente(USER_AGENT, min_interval=1.2)
    por_familia = construir_plan(FUENTES_DEF, cliente, max_por_dominio=args.max_por_dominio)
    total = escribir_plan(por_familia, args.out)
    for familia in sorted(por_familia):
        print(f"{familia}: {len(por_familia[familia])} candidatas")
    print(f"Plan escrito en {args.out} ({total} URLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
