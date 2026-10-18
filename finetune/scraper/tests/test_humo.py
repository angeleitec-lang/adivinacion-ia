import unittest


class Humo(unittest.TestCase):
    def test_importa_spider(self):
        from scraper.spiders import deep  # noqa: F401
        self.assertTrue(hasattr(deep, "DeepSpider"))


if __name__ == "__main__":
    unittest.main()
