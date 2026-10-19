"""Tests del informe de cobertura del dataset de entrenamiento (track T15)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura_dataset


def _fila(*mensajes):
    return json.dumps({"conversations": list(mensajes)}, ensure_ascii=False)


def _escribir(directorio, nombre, lineas):
    ruta = os.path.join(directorio, nombre)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    return ruta


class LectorShareGPT(unittest.TestCase):
    def test_lee_un_par_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "a.jsonl", [
                _fila({"from": "system", "value": "Eres una tarotista."},
                      {"from": "human", "value": "¿Qué significa el Loco?"},
                      {"from": "gpt", "value": "El Loco habla de nuevos comienzos."}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            pregunta, respuesta = pares[0]
            self.assertIn("Loco", pregunta)
            self.assertIn("comienzos", respuesta)
            self.assertEqual(stats["pares"], 1)
            self.assertEqual(stats["lineas_invalidas"], 0)
            self.assertEqual(stats["sin_gpt"], 0)

    def test_lineas_vacias_y_json_invalido_se_cuentan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "b.jsonl", [
                "",
                "{no es json",
                '{"sin_conversations": 1}',
                _fila({"from": "human", "value": "hola"},
                      {"from": "gpt", "value": "adios"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            self.assertEqual(stats["lineas_invalidas"], 3)
            self.assertEqual(stats["sin_gpt"], 0)

    def test_filas_sin_gpt_se_cuentan_aparte(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "c.jsonl", [
                _fila({"from": "system", "value": "s"},
                      {"from": "human", "value": "h"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(pares, [])
            self.assertEqual(stats["sin_gpt"], 1)
            self.assertEqual(stats["lineas_invalidas"], 0)

    def test_sin_human_da_pregunta_vacia(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "d.jsonl", [
                _fila({"from": "gpt", "value": "solo respuesta"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            self.assertEqual(pares[0][0], "")
            self.assertEqual(stats["pares"], 1)

    def test_varios_ficheros_se_acumulan_en_orden(self):
        with tempfile.TemporaryDirectory() as tmp:
            r1 = _escribir(tmp, "1.jsonl", [
                _fila({"from": "human", "value": "uno"},
                      {"from": "gpt", "value": "respuesta uno"}),
            ])
            r2 = _escribir(tmp, "2.jsonl", [
                _fila({"from": "human", "value": "dos"},
                      {"from": "gpt", "value": "respuesta dos"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([r1, r2])
            self.assertEqual(stats["pares"], 2)
            self.assertEqual(pares[0][1], "respuesta uno")
            self.assertEqual(pares[1][1], "respuesta dos")

    def test_varios_mensajes_gpt_se_concatenan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "e.jsonl", [
                _fila({"from": "human", "value": "h"},
                      {"from": "gpt", "value": "parte1"},
                      {"from": "gpt", "value": "parte2"}),
            ])
            pares, _ = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(pares[0][1], "parte1 parte2")


if __name__ == "__main__":
    unittest.main()
