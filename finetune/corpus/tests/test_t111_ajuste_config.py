"""Tests del ajuste de configuración de entrenamiento (T111).

Cubren ``finetune/entrenamiento/ajuste_config.py``: parseo de los YAML del
repo, resumen de longitudes, impacto de truncamiento, horas y memoria QLoRA.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "entrenamiento"))

import ajuste_config as ac  # noqa: E402

RUTA_ENTRENAMIENTO = Path(__file__).resolve().parents[2] / "entrenamiento"


class TestParseYamlSimple(unittest.TestCase):
    def test_mapa_listas_y_escalares(self):
        texto = (
            "# comentario de cabecera\n"
            "base: Qwen/Qwen2.5-7B-Instruct\n"
            "task: sft\n"
            "data:\n"
            "  max_length: 4096\n"
            "  ratio: 0.05\n"
            "  flag: true\n"
            "  nombres:\n"
            "    - q_proj\n"
            "    - k_proj\n"
            "training:\n"
            "  lr: 0.0002\n"
            "  offline: false\n"
        )
        cfg = ac.parse_yaml_simple(texto)
        self.assertEqual(cfg["base"], "Qwen/Qwen2.5-7B-Instruct")
        self.assertEqual(cfg["task"], "sft")
        self.assertEqual(cfg["data"]["max_length"], 4096)
        self.assertIsInstance(cfg["data"]["max_length"], int)
        self.assertEqual(cfg["data"]["ratio"], 0.05)
        self.assertIs(cfg["data"]["flag"], True)
        self.assertEqual(cfg["data"]["nombres"], ["q_proj", "k_proj"])
        self.assertEqual(cfg["training"]["lr"], 0.0002)
        self.assertIs(cfg["training"]["offline"], False)

    def test_vacio(self):
        self.assertEqual(ac.parse_yaml_simple(""), {})
        self.assertEqual(ac.parse_yaml_simple("# solo comentario\n"), {})

    def test_sintaxis_no_soportada(self):
        with self.assertRaises(ValueError):
            ac.parse_yaml_simple("clave: valor\nrota sin dos puntos\n")


class TestYamlReales(unittest.TestCase):
    def test_qlora_7b(self):
        cfg = ac.cargar_config(RUTA_ENTRENAMIENTO / "qlora_7b.yaml")
        self.assertEqual(cfg["base"], "Qwen/Qwen2.5-7B-Instruct")
        self.assertEqual(cfg["data"]["max_length"], 4096)
        self.assertEqual(cfg["training"]["batch_size"], 4)
        self.assertEqual(cfg["training"]["gradient_accumulation_steps"], 4)
        self.assertEqual(cfg["training"]["lora"]["r"], 16)
        self.assertEqual(cfg["training"]["lora"]["alpha"], 32)
        self.assertEqual(cfg["training"]["quantization"], "4bit")
        self.assertEqual(len(cfg["training"]["lora"]["target_modules"]), 7)

    def test_qlora_14b(self):
        cfg = ac.cargar_config(RUTA_ENTRENAMIENTO / "qlora_14b.yaml")
        self.assertEqual(cfg["base"], "Qwen/Qwen2.5-14B-Instruct")
        self.assertEqual(cfg["data"]["max_length"], 4096)
        self.assertEqual(cfg["training"]["batch_size"], 2)
        self.assertEqual(cfg["training"]["gradient_accumulation_steps"], 8)
        self.assertEqual(cfg["training"]["lora"]["r"], 32)
        self.assertEqual(cfg["training"]["lora"]["alpha"], 64)

    def test_lote_efectivo_igual_en_ambos(self):
        for nombre in ("qlora_7b.yaml", "qlora_14b.yaml"):
            cfg = ac.cargar_config(RUTA_ENTRENAMIENTO / nombre)
            t = cfg["training"]
            self.assertEqual(
                t["batch_size"] * t["gradient_accumulation_steps"], 16, nombre)


class TestResumenLongitudes(unittest.TestCase):
    def test_valores_conocidos(self):
        r = ac.resumen_longitudes(list(range(1, 101)))
        self.assertEqual(r["n"], 100)
        self.assertEqual(r["media"], 50.5)
        self.assertEqual(r["p50"], 50)
        self.assertEqual(r["p95"], 95)
        self.assertEqual(r["p99"], 99)
        self.assertEqual(r["max"], 100)

    def test_vacio(self):
        r = ac.resumen_longitudes([])
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["max"], 0)

    def test_un_valor(self):
        r = ac.resumen_longitudes([42])
        self.assertEqual(r, {"n": 1, "media": 42.0, "p50": 42,
                             "p95": 42, "p99": 42, "max": 42})


class TestImpactoTruncamiento(unittest.TestCase):
    def test_sintactico(self):
        r = ac.impacto_truncamiento([1000, 2000, 5000], 4096)
        self.assertEqual(r["limite"], 4096)
        self.assertEqual(r["filas_over"], 1)
        self.assertEqual(r["pct_filas"], 33.33)
        self.assertEqual(r["pct_tokens_perdidos"], 11.3)

    def test_sin_over(self):
        r = ac.impacto_truncamiento([100, 200], 4096)
        self.assertEqual(r["filas_over"], 0)
        self.assertEqual(r["pct_tokens_perdidos"], 0.0)

    def test_vacio_no_divide_por_cero(self):
        r = ac.impacto_truncamiento([], 4096)
        self.assertEqual(r["pct_filas"], 0.0)
        self.assertEqual(r["pct_tokens_perdidos"], 0.0)


class TestEstimarHoras(unittest.TestCase):
    def test_sin_sobrecarga(self):
        self.assertEqual(ac.estimar_horas(3_600_000, 1, 1000, sobrecarga=1.0), 1.0)

    def test_caso_real_7b(self):
        # 8.384.298 tokens/época (recortado a 4096), 3 épocas, 550 tps.
        h = ac.estimar_horas(8_384_298, 3, 550)
        self.assertAlmostEqual(h, 14.6, delta=0.1)

    def test_rendimiento_no_positivo(self):
        with self.assertRaises(ValueError):
            ac.estimar_horas(1000, 1, 0)


class TestEstimarMemoriaQlora(unittest.TestCase):
    def test_7b_cabe(self):
        m = ac.estimar_memoria_qlora(7.0, 20.0, 4096, 4)
        self.assertEqual(m["pesos_gb"], 3.9)
        self.assertEqual(m["optimizador_gb"], 0.24)
        self.assertEqual(m["activaciones_gb"], 40.1)
        self.assertEqual(m["total_gb"], 44.3)
        self.assertTrue(m["cabe_en_128gb"])
        self.assertEqual(m["margen_gb"], 83.7)

    def test_14b_cabe(self):
        m = ac.estimar_memoria_qlora(14.0, 35.0, 4096, 2)
        self.assertEqual(m["pesos_gb"], 7.8)
        self.assertEqual(m["optimizador_gb"], 0.42)
        self.assertEqual(m["total_gb"], 48.4)
        self.assertTrue(m["cabe_en_128gb"])
        self.assertGreaterEqual(m["margen_gb"], 60.0)

    def test_no_cabe(self):
        m = ac.estimar_memoria_qlora(200.0, 100.0, 8192, 8)
        self.assertFalse(m["cabe_en_128gb"])
        self.assertLess(m["margen_gb"], 0.0)


class TestTokensDeFila(unittest.TestCase):
    def test_estimacion_por_caracteres(self):
        fila = {"conversations": [
            {"from": "human", "value": "x" * 35},
            {"from": "gpt", "value": "y" * 35},
        ]}
        # 35 + 1 (salto) + 35 = 71 chars / 3,5 ≈ 20,29 → 20
        self.assertEqual(ac.tokens_de_fila(fila), 20)

    def test_sin_conversations(self):
        self.assertEqual(ac.tokens_de_fila({}), 0)


class TestAnalizarDataset(unittest.TestCase):
    def test_global_y_por_familia(self):
        filas = [
            {"conversations": [{"from": "human", "value": "a" * 70},
                              {"from": "gpt", "value": "b" * 70}],
             "metadatos": {"familia": "Tarot_1"}},
            {"conversations": [{"from": "human", "value": "c" * 35}],
             "metadata": {"categoria": "astro_natal"}},
            {"conversations": [{"from": "human", "value": "d" * 35}]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "train.jsonl"
            ruta.write_text(
                "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
                encoding="utf-8")
            informe = ac.analizar_dataset(ruta)
        self.assertEqual(informe["global"]["n"], 3)
        self.assertIn("tarot_1", informe["por_familia"])
        self.assertIn("astro_natal", informe["por_familia"])
        self.assertIn("sin_etiqueta", informe["por_familia"])
        self.assertEqual(informe["por_familia"]["tarot_1"]["max"], 40)
        self.assertIn("4096", informe["truncamiento"])
        self.assertEqual(informe["truncamiento"]["4096"]["filas_over"], 0)


if __name__ == "__main__":
    unittest.main()
