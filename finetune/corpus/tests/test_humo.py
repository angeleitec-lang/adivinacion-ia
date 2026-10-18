"""Test de humo del contrato: los módulos clave se importan y exponen la API que otros usan."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class HumoContrato(unittest.TestCase):
    def test_apis_compartidas(self):
        import build_dataset
        import translate_dataset
        import validate_synthetic

        for nombre in ("build_pairs", "BAD_TOPIC_RE", "domain_hits", "write_jsonl",
                       "iter_markdown", "INSTRUCTION_TEMPLATES", "SYSTEM"):
            self.assertTrue(hasattr(build_dataset, nombre), nombre)
        self.assertTrue(hasattr(translate_dataset, "detect_language"))
        for nombre in ("answer_of", "human_of", "sha"):
            self.assertTrue(hasattr(validate_synthetic, nombre), nombre)


if __name__ == "__main__":
    unittest.main()
