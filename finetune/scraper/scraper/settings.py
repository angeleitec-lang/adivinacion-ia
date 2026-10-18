BOT_NAME = "scraper"

SPIDER_MODULES = ["scraper.spiders"]
NEWSPIDER_MODULE = "scraper.spiders"

ADDONS = {}

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 0.5
RANDOMIZE_DOWNLOAD_DELAY = True

COOKIES_ENABLED = False
TELNETCONSOLE_ENABLED = False

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es,en;q=0.8",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

ITEM_PIPELINES = {
    "scraper.pipelines.MarkdownPipeline": 300,
}

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 15
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

DOWNLOAD_TIMEOUT = 60
RETRY_TIMES = 2
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504]

HTTPCACHE_ENABLED = False

RAW_OUT_DIR = "corpus/raw_scrapy"

FEED_EXPORT_ENCODING = "utf-8"
FEED_MODE = "create"

LOG_LEVEL = "INFO"
