import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from itemadapter import ItemAdapter


def slugify(text, max_len=80):
    text = re.sub(r"[^\w\-]+", "-", text, flags=re.UNICODE).strip("-")
    return (text[:max_len] or "index").lower()


class MarkdownPipeline:
    def __init__(self, out_dir):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = self.out_dir / "pages.jsonl"
        self.seen_hashes = set()
        self.count = 0
        self.crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls(crawler.settings.get("RAW_OUT_DIR", "corpus/raw_scrapy"))
        obj.crawler = crawler
        return obj

    @property
    def logger(self):
        return self.crawler.spider.logger

    def open_spider(self):
        self.logger.info("Guardando markdown en %s", self.out_dir)

    def process_item(self, item):
        adapter = ItemAdapter(item)
        text = (adapter.get("text") or "").strip()
        if len(text) < 400:
            return item

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in self.seen_hashes:
            return item
        self.seen_hashes.add(digest)

        url = adapter.get("url") or ""
        domain = adapter.get("domain") or urlparse(url).netloc
        title = adapter.get("title") or ""

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
            "---\n\n"
        )
        path.write_text(front + text + "\n", encoding="utf-8")

        record = {
            "url": url,
            "domain": domain,
            "title": title,
            "depth": adapter.get("depth", 0),
            "chars": len(text),
            "sha256": digest,
            "file": str(path.relative_to(self.out_dir)),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self.manifest.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.count += 1
        spider_logger = self.logger
        spider_logger.info("[%d] %s -> %s (%d chars)", self.count, url, path.name, len(text))
        return item

    def close_spider(self):
        self.logger.info("Total paginas guardadas: %d", self.count)
