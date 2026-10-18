#!/usr/bin/env python3
"""Tests para yt_qa.py (A4.7)."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_qa
import unittest


def _par_ejemplo(video_id, canal="Canal Test", tirada="3_cartas"):
    return {
        "conversations": [
            {"from": "system", "value": "sys"},
            {"from": "human", "value": f"Tirada: {tirada}\nCartas: Los Enamorados (derecha) en presente"},
            {"from": "gpt", "value": "Los Enamorados en presente te hablan de una elección. El Sol en futuro trae claridad. Síntesis: evolución positiva. Consejo: confía."}
        ],
        "meta": {"video_id": video_id, "canal": canal, "tipo": "lectura", "tirada": tirada}
    }


class GenerarInformeQA(unittest.TestCase):
    def test_genera_informe_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Archivos de entrada ficticios
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text("\n".join(json.dumps({"id": f"v{i}"}) for i in range(5)))

            fetch = tmp / "fetch.jsonl"
            fetch.write_text("\n".join(json.dumps({"id": f"v{i}", "estado": "ok"}) for i in range(3))
                           + "\n" + json.dumps({"id": "v3", "estado": "sin_subtitulo"})
                           + "\n" + json.dumps({"id": "v4", "estado": "error"}))

            clasificacion = tmp / "clasificacion.jsonl"
            clasificacion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura_individual"}) for i in range(3)))

            extraccion = tmp / "extraccion.jsonl"
            extraccion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura"}) for i in range(2)))

            normalizacion = tmp / "dataset.jsonl"
            pares = [_par_ejemplo(f"v{i}") for i in range(2)]
            normalizacion.write_text("\n".join(json.dumps(p) for p in pares))

            out_dir = tmp / "qa_out"
            qa = yt_qa.generar_informe_qa(catalogo, fetch, clasificacion, extraccion, normalizacion, out_dir)

            # Verificar archivos de salida
            self.assertTrue((out_dir / "qa.json").exists())
            self.assertTrue((out_dir / "qa.md").exists())

            # Verificar estructura JSON
            self.assertIn("embudo", qa)
            self.assertIn("por_canal", qa)
            self.assertIn("cobertura_cartas", qa)
            self.assertIn("alertas", qa)
            self.assertIn("muestras_revision", qa)

            # Verificar embudo
            embudo = qa["embudo"]
            self.assertEqual(embudo["catalogo_total"], 5)
            self.assertEqual(embudo["con_subtitulos_ok"], 3)
            self.assertEqual(embudo["normalizados_ok"], 2)

    def test_alerta_canal_sobre_3_porciento(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text("\n".join(json.dumps({"id": f"v{i}"}) for i in range(100)))

            fetch = tmp / "fetch.jsonl"
            fetch.write_text("\n".join(json.dumps({"id": f"v{i}", "estado": "ok"}) for i in range(100)))

            clasificacion = tmp / "clasificacion.jsonl"
            clasificacion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura_individual"}) for i in range(100)))

            extraccion = tmp / "extraccion.jsonl"
            extraccion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura"}) for i in range(100)))

            normalizacion = tmp / "dataset.jsonl"
            # 95 de canal A, 5 de canal B -> A supera 3%
            pares = [_par_ejemplo(f"v{i}", canal="Canal A") for i in range(95)]
            pares += [_par_ejemplo(f"v{i}", canal="Canal B") for i in range(95, 100)]
            normalizacion.write_text("\n".join(json.dumps(p) for p in pares))

            out_dir = tmp / "qa_out"
            qa = yt_qa.generar_informe_qa(catalogo, fetch, clasificacion, extraccion, normalizacion, out_dir)

            alertas = qa["alertas"]
            self.assertTrue(any("3%" in a for a in alertas))

    def test_alerta_cartas_bajas(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text(json.dumps({"id": "v1"}))

            fetch = tmp / "fetch.jsonl"
            fetch.write_text(json.dumps({"id": "v1", "estado": "ok"}))

            clasificacion = tmp / "clasificacion.jsonl"
            clasificacion.write_text(json.dumps({"video_id": "v1", "tipo": "lectura_individual"}))

            extraccion = tmp / "extraccion.jsonl"
            extraccion.write_text(json.dumps({"video_id": "v1", "tipo": "lectura"}))

            normalizacion = tmp / "dataset.jsonl"
            # Solo una lectura con "El Loco" -> 77 cartas con 0 lecturas
            par = _par_ejemplo("v1", tirada="1_carta")
            # Modificar para que solo mencione El Loco
            par["conversations"][1] = {"from": "human", "value": "Tirada: 1_carta\nCartas: El Loco (derecha) en carta"}
            par["conversations"][2] = {"from": "gpt", "value": "El Loco en posición carta indica un nuevo comienzo. Síntesis: nuevo inicio. Consejo: atrévete."}
            normalizacion.write_text(json.dumps(par))

            out_dir = tmp / "qa_out"
            qa = yt_qa.generar_informe_qa(catalogo, fetch, clasificacion, extraccion, normalizacion, out_dir)

            # Debe alertar sobre cartas con <10 lecturas (77 de 78)
            alertas = qa["alertas"]
            self.assertTrue(any("<10" in a for a in alertas))

    def test_muestras_aleatorias_max_30(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            catalogo = tmp / "catalogo.jsonl"
            catalogo.write_text("\n".join(json.dumps({"id": f"v{i}"}) for i in range(50)))

            fetch = tmp / "fetch.jsonl"
            fetch.write_text("\n".join(json.dumps({"id": f"v{i}", "estado": "ok"}) for i in range(50)))

            clasificacion = tmp / "clasificacion.jsonl"
            clasificacion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura_individual"}) for i in range(50)))

            extraccion = tmp / "extraccion.jsonl"
            extraccion.write_text("\n".join(json.dumps({"video_id": f"v{i}", "tipo": "lectura"}) for i in range(50)))

            normalizacion = tmp / "dataset.jsonl"
            pares = [_par_ejemplo(f"v{i}") for i in range(50)]
            normalizacion.write_text("\n".join(json.dumps(p) for p in pares))

            out_dir = tmp / "qa_out"
            qa = yt_qa.generar_informe_qa(catalogo, fetch, clasificacion, extraccion, normalizacion, out_dir)

            muestras = qa["muestras_revision"]
            self.assertLessEqual(len(muestras), 30)
            self.assertEqual(len(muestras), 30)  # Exactamente 30


if __name__ == "__main__":
    unittest.main()
