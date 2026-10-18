import hashlib
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from itemadapter import ItemAdapter

_LOG = logging.getLogger(__name__)


def slugify(text, max_len=80):
    text = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE).strip("-")
    return (text[:max_len] or "index").lower()


class MarkdownPipeline:
    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self.out_dir / "pages.jsonl"
        self.seen_hashes = set()
        self.seen_urls = set()
        self.count = 0
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls(crawler.settings.get("RAW_OUT_DIR", "corpus/raw_scrapy"))
        obj.crawler = crawler
        return obj

    @property
    def logger(self):
        spider = getattr(self.crawler, "spider", None) if self.crawler else None
        return spider.logger if spider else _LOG

    def open_spider(self, spider=None):
        self._cargar_previos()
        self.logger.info("Guardando markdown en %s", self.out_dir)

    def _cargar_previos(self):
        """Carga sha256 y URLs ya guardadas para no re-duplicar entre ejecuciones."""
        if not self.manifest.exists():
            return
        with self.manifest.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("sha256"):
                    self.seen_hashes.add(rec["sha256"])
                if rec.get("url"):
                    self.seen_urls.add(rec["url"])

    def process_item(self, item):
        adapter = ItemAdapter(item)
        text = (adapter.get("text") or "").strip()
        if len(text) < 400:
            return item

        url = adapter.get("url") or ""
        domain = adapter.get("domain") or urlparse(url).netloc
        title = adapter.get("title") or ""
        lang = adapter.get("lang")

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in self.seen_hashes or (url and url in self.seen_urls):
            return item
        self.seen_hashes.add(digest)
        if url:
            self.seen_urls.add(url)

        license_hint = "cc-by-sa" if domain.endswith("wikipedia.org") else "consultar"

        folder = self.out_dir / slugify(domain)
        folder.mkdir(parents=True, exist_ok=True)

        name = slugify(title) if title else slugify(urlparse(url).path or "index")
        path = folder / (name + ".md")
        if path.exists():
            path = folder / (name + "-" + digest[:8] + ".md")

        front = (
            "---\n"
            "url: " + url + "\n"
            "title: " + json.dumps(title, ensure_ascii=False) + "\n"
            "domain: " + domain + "\n"
            "depth: " + str(adapter.get("depth", 0)) + "\n"
            "sha256: " + digest + "\n"
        )
        if lang:
            front += "lang: " + str(lang) + "\n"
        front += "license_hint: " + license_hint + "\n---\n\n"
        path.write_text(front + text + "\n", encoding="utf-8")

        record = {
            "url": url,
            "domain": domain,
            "title": title,
            "depth": adapter.get("depth", 0),
            "chars": len(text),
            "sha256": digest,
            "license_hint": license_hint,
            "file": str(path.relative_to(self.out_dir)),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if lang:
            record["lang"] = lang
        with self.manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.count += 1
        spider_logger = self.logger
        spider_logger.info("[%d] %s -> %s (%d chars)", self.count, url, path.name, len(text))
        return item

    def close_spider(self, spider=None):
        self.logger.info("Total paginas guardadas: %d", self.count)
