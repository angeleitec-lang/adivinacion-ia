import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import comprobar_piloto as cp


def chatml(*turnos):
    return {"messages": [{"role": r, "content": c} for r, c in turnos]}


def sharegpt(bloque, *turnos):
    return {
        "conversations": [{"from": r, "value": c} for r, c in turnos],
        "bloque": bloque,
    }


class TestEstimarTokens(unittest.TestCase):
    def test_redondeo(self):
        self.assertEqual(cp.estimar_tokens("a" * 7), 2)
        self.assertEqual(cp.estimar_tokens(""), 0)

    def test_chatml_suma_contenidos(self):
        # 35+1+35+1+35 = 107 chars -> round(107/3.5) = 31
        fila = chatml(("system", "x" * 35), ("user", "y" * 35),
                     ("assistant", "z" * 35))
        self.assertEqual(cp.tokens_de_fila_chatml(fila), 31)


class TestValidarChatml(unittest.TestCase):
    def test_valida(self):
        fila = chatml(("system", "Eres tarotista."), ("user", "Hola"),
                     ("assistant", "Hola."))
        self.assertEqual(cp.validar_chatml(fila), [])

    def test_sin_mensajes(self):
        self.assertTrue(cp.validar_chatml({}))

    def test_rol_invalido(self):
        fila = chatml(("user", "Hola"), ("bot", "Hola."))
        self.assertTrue(any("rol inválido" in e for e in cp.validar_chatml(fila)))

    def test_dos_system(self):
        fila = chatml(("system", "Uno"), ("system", "Dos"), ("user", "H"),
                     ("assistant", "R"))
        self.assertTrue(any("más de un turno 'system'" in e
                           for e in cp.validar_chatml(fila)))

    def test_system_fuera_de_sitio(self):
        fila = chatml(("user", "H"), ("system", "Tarde"), ("assistant", "R"))
        self.assertTrue(any("primera posición" in e
                           for e in cp.validar_chatml(fila)))

    def test_no_empieza_user(self):
        fila = chatml(("assistant", "R"))
        errs = cp.validar_chatml(fila)
        self.assertTrue(any("empezar en 'user'" in e for e in errs))

    def test_no_termina_assistant(self):
        fila = chatml(("user", "H"))
        self.assertTrue(any("terminar en 'assistant'" in e
                           for e in cp.validar_chatml(fila)))

    def test_rol_consecutivo(self):
        fila = chatml(("user", "H1"), ("user", "H2"), ("assistant", "R"))
        self.assertTrue(any("consecutivos del mismo rol" in e
                           for e in cp.validar_chatml(fila)))

    def test_contenido_vacio(self):
        fila = chatml(("system", ""), ("user", "H"), ("assistant", "R"))
        self.assertTrue(any("contenido vacío" in e
                           for e in cp.validar_chatml(fila)))


class TestCalcularPasos(unittest.TestCase):
    def test_techo_y_totales(self):
        r = cp.calcular_pasos(100, 2, 8, 3)
        self.assertEqual(r["lote_efectivo"], 16)
        self.assertEqual(r["pasos_por_epoca"], 7)  # ceil(100/16)
        self.assertEqual(r["pasos_totales"], 21)

    def test_lote_cero_error(self):
        with self.assertRaises(ValueError):
            cp.calcular_pasos(10, 0, 4, 1)


class TestNormalizarConfig(unittest.TestCase):
    def test_aplana_anidada(self):
        cruda = {
            "base": "Qwen/Qwen2.5-14B-Instruct",
            "data": {"max_length": 4096, "format": "chatml"},
            "training": {"epochs": 3, "batch_size": 2,
                        "gradient_accumulation_steps": 8, "lr": 0.0001},
        }
        n = cp.normalizar_config(cruda)
        self.assertEqual(n["base_model"], "Qwen/Qwen2.5-14B-Instruct")
        self.assertEqual(n["max_length"], 4096)
        self.assertEqual(n["batch_size"], 2)
        self.assertEqual(n["grad_accum"], 8)
        self.assertEqual(n["epochs"], 3.0)

    def test_defectos_sin_claves(self):
        n = cp.normalizar_config({})
        self.assertEqual(n["max_length"], 4096)
        self.assertEqual(n["grad_accum"], 8)


class TestAnalizarSplits(unittest.TestCase):
    def _escribir(self, dirpath, nombre, filas):
        p = Path(dirpath) / nombre
        with p.open("w", encoding="utf-8") as fh:
            for f in filas:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        return p

    def test_sharegpt_agrupa_bloques(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._escribir(d, "train.jsonl", [
                sharegpt("tarot_1", ("system", "S"), ("human", "H"),
                        ("gpt", "R")),
                sharegpt("numerologia", ("system", "S"), ("human", "H"),
                        ("gpt", "R")),
            ])
            r = cp.analizar_split_sharegpt(p, 4096)
            self.assertEqual(r["n"], 2)
            self.assertEqual(r["invalidas"], 0)
            self.assertEqual(r["bloques"]["tarot_1"], 1)
            self.assertEqual(r["bloques"]["numerologia"], 1)

    def test_chatml_detecta_invalida(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._escribir(d, "train.jsonl", [
                chatml(("system", "S"), ("user", "H"), ("assistant", "R")),
                chatml(("user", "H"), ("user", "H2")),
            ])
            r = cp.analizar_split_chatml(p, 4096)
            self.assertEqual(r["n"], 2)
            self.assertEqual(r["invalidas"], 1)

    def test_exceden_contexto(self):
        with tempfile.TemporaryDirectory() as d:
            larga = "x" * 8192  # ~2340 tokens
            p = self._escribir(d, "train.jsonl", [
                chatml(("user", larga), ("assistant", "R")),
            ])
            r = cp.analizar_split_chatml(p, 100)
            self.assertEqual(r["exceden_contexto"], 1)

    def test_no_existe(self):
        r = cp.analizar_split_chatml(Path("/no/existe.jsonl"), 4096)
        self.assertFalse(r["existe"])


class TestDetectarHuecos(unittest.TestCase):
    def _train(self, **bloques):
        return {"existe": True, "ruta": "", "bloques": bloques,
                "exceden_contexto": 0, "invalidas": 0}

    def test_numerologia_sin_test_bloqueante(self):
        train = self._train(numerologia=321, tarot_1=820)
        val = {"existe": True, "bloques": {"numerologia": 14, "tarot_1": 45}}
        test = {"existe": True, "bloques": {"tarot_1": 47}}
        chatml_tr = {"existe": True, "invalidas": 0}
        huecos = cp.detectar_huecos(train, val, test, chatml_tr,
                                    {"max_length": 4096})
        titulos = " ".join(h["titulo"] for h in huecos)
        self.assertIn("numerologia", titulos)
        self.assertTrue(any(h["severidad"] == "BLOQUEANTE" for h in huecos))

    def test_chatml_invalido_bloqueante(self):
        train = self._train(tarot_1=10)
        val = {"existe": True, "bloques": {"tarot_1": 20}}
        test = {"existe": True, "bloques": {f: 5 for f in cp.FAMILIAS_EVALUABLES}}
        chatml_tr = {"existe": True, "invalidas": 3}
        huecos = cp.detectar_huecos(train, val, test, chatml_tr,
                                    {"max_length": 4096})
        self.assertTrue(any("plantilla inválida" in h["titulo"] and
                           h["severidad"] == "BLOQUEANTE" for h in huecos))


class TestResumenPiloto(unittest.TestCase):
    def test_extremo_con_todo_ok(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            preparado = dp / "preparado"
            preparado.mkdir()
            filas_sg = [
                sharegpt("tarot_1", ("system", "S"), ("human", "H"),
                        ("gpt", "R")),
            ] * 3
            for split in ("train", "val", "test"):
                with (dp / f"{split}.jsonl").open("w", encoding="utf-8") as fh:
                    for f in filas_sg:
                        fh.write(json.dumps(f, ensure_ascii=False) + "\n")
            with (preparado / "train.jsonl").open("w", encoding="utf-8") as fh:
                for _ in range(3):
                    fh.write(json.dumps(
                        chatml(("system", "S"), ("user", "H"),
                              ("assistant", "R"))) + "\n")
            cfg = {"max_length": 4096, "batch_size": 2, "grad_accum": 8,
                   "epochs": 3, "base_model": "X"}
            informe = cp.resumen_piloto(dp, cfg)
            self.assertEqual(informe["pasos"]["pasos_por_epoca"], 1)
            self.assertEqual(informe["splits"]["train"]["n"], 3)
            # numerologia y otras familias sin test => ROJO
            self.assertEqual(informe["semforo"], "ROJO")


if __name__ == "__main__":
    unittest.main()
