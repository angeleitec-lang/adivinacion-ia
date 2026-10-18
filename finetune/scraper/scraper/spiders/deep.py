import json
import re
from urllib.parse import urlparse

import scrapy
import trafilatura
from scrapy.linkextractors import LinkExtractor


SKIP_EXT = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".gz", ".tar",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".epub", ".mobi", ".azw", ".azw3",
)

# Segmentos de ruta exactos que se saltan (comparar segmento a segmento,
# no por subcadena: «carta-astral» no debe confundirse con «cart»).
RUTA_SALTAR = frozenset({
    "login", "signin", "register", "cart", "carrito", "checkout", "account",
    "mi-cuenta", "wp-admin", "wp-login", "feed", "rss", "tag", "category",
    "author", "search", "buscar", "privacidad", "privacy", "cookies",
    "aviso-legal", "terminos", "terms", "contacto", "contact", "policies",
    "policy", "legal", "refund", "shipping", "devoluciones", "envios",
    "envio", "faq", "sobre-nosotros", "quienes-somos", "newsletter",
    "suscripcion", "suscripciones",
})

# Palabras completas (\b) que descartan un título: «cart» no coincide con
# «carta» ni «legal» con «ilegal», pero sí con los títulos comerciales.
TITULO_SALTAR_RE = re.compile(
    r"\b(?:t[ée]rminos|terms|privacy|privacidad|cookies?|legal|"
    r"aviso legal|env[íi]o|shipping|devoluci[óo]n|refund|contacto|contact|"
    r"login|carrito|cart|checkout|suscripci[óo]n|newsletter|pol[íi]tica)\b",
    re.IGNORECASE,
)


def read_seeds(path):
    urls = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def domain_of(url):
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def titulo_descartable(titulo):
    """True si el título contiene una palabra comercial a descartar."""
    return bool(TITULO_SALTAR_RE.search(titulo or ""))


def ruta_crawleable(url):
    """True si la ruta no contiene segmentos comerciales exactos."""
    low = url.lower()
    if any(low.endswith(ext) for ext in SKIP_EXT):
        return False
    path = urlparse(low).path
    segmentos = [s for s in path.strip("/").split("/") if s]
    return not any(seg in RUTA_SALTAR for seg in segmentos)


def is_crawlable(url):
    return ruta_crawleable(url)


def read_urls(path):
    urls = set()
    if not path:
        return urls
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("url"):
                    urls.add(obj["url"])
    except FileNotFoundError:
        pass
    return urls


class DeepSpider(scrapy.Spider):
    name = "deep"

    def __init__(self, seeds="corpus/urls_research.txt", pages_per_domain=40,
                 max_depth=2, prior="corpus/raw_scrapy/pages.jsonl", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seed_urls = read_seeds(seeds)
        self.pages_per_domain = int(pages_per_domain)
        self.max_depth = int(max_depth)
        self.prior = read_urls(prior)
        self.per_domain = {}
        self.seen = set()
        self.allowed_domains = sorted({domain_of(u) for u in self.seed_urls})
        self.link_extractor = LinkExtractor(
            allow_domains=self.allowed_domains,
            deny_extensions=["pdf", "doc", "docx", "zip", "epub"],
            unique=True,
            canonicalize=True,
            strip=True,
        )

    async def start(self):
        for url in self.seed_urls:
            yield scrapy.Request(
                url,
                callback=self.parse,
                errback=self.on_error,
                meta={"depth": 0},
                dont_filter=True,
            )

    def on_error(self, failure):
        self.logger.warning("Fallo %s: %s", failure.request.url, failure.value)

    def parse(self, response):
        url = response.url
        domain = domain_of(url)
        depth = response.meta.get("depth", 0)

        if url in self.seen:
            return
        if response.status >= 400:
            return

        content_type = response.headers.get("Content-Type", b"").decode("latin-1", "ignore")
        if "html" not in content_type.lower():
            return

        lang_raw = response.xpath("//html/@lang").get()
        lang = lang_raw.strip().lower().split("-")[0] if lang_raw else None
        if lang and lang not in {"es", "en"}:
            return

        is_new = url not in self.prior
        if is_new and self.per_domain.get(domain, 0) >= self.pages_per_domain:
            return

        self.seen.add(url)
        if is_new:
            self.per_domain[domain] = self.per_domain.get(domain, 0) + 1

        try:
            html = response.text
        except Exception:
            html = response.body.decode("utf-8", "ignore")

        title = response.css("title::text").get(default="").strip()
        if titulo_descartable(title):
            return

        if is_new:
            text = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=False,
                include_images=False,
                include_tables=True,
                favor_precision=True,
                deduplicate=True,
            )
            if text:
                yield {
                    "url": url,
                    "domain": domain,
                    "title": title,
                    "depth": depth,
                    "lang": lang,
                    "text": text,
                }

        if depth >= self.max_depth:
            return
        if self.per_domain.get(domain, 0) >= self.pages_per_domain:
            return

        for link in self.link_extractor.extract_links(response):
            target = link.url
            if target in self.seen or not is_crawlable(target):
                continue
            yield scrapy.Request(
                target,
                callback=self.parse,
                errback=self.on_error,
                meta={"depth": depth + 1},
            )
