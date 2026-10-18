#!/usr/bin/env python3
"""Tests de web_informe: generación de informe de cobertura."""
import os
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from web_informe import generar_informe, _cargar_manifest, _cargar_md_files


class WebInformeTests(unittest.TestCase):
    def test_genera_informe_completo(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # Crear manifest.jsonl
            manifest = td / "manifest.jsonl"
            lines = [
                json.dumps({"url": "https://a.com/1", "estado": "ok", "dominio": "a.com", "bytes": 2000}),
                json.dumps({"url": "https://a.com/2", "estado": "ok", "dominio": "a.com", "bytes": 3000}),
                json.dumps({"url": "https://b.com/1", "estado": "bloqueada_robots", "dominio": "b.com", "bytes": 0}),
                json.dumps({"url": "https://b.com/2", "estado": "bloqueada_antibot", "dominio": "b.com", "bytes": 0}),
                json.dumps({"url": "https://c.com/1", "estado": "pausado_429", "dominio": "c.com", "bytes": 0}),
                json.dumps({"url": "https://c.com/2", "estado": "error", "dominio": "c.com", "bytes": 0}),
            ]
            manifest = td / "manifest.jsonl"
            manifest.write_text("\n".join(lines))

            # Crear archivos .md con front-matter
            out_dir = td / "web"
            (out_dir / "a.com").mkdir(parents=True)
            (out_dir / "b.com").mkdir(parents=True)
            (out_dir / "a.com" / "entidad1.md").write_text(
                "---\nurl: https://a.com/1\ndominio: a.com\nentidad_id: sol|aries|planeta_en_signo\n"
                "faceta: planeta_en_signo\nfamilia: astrologia\nidioma: es\nsha256: abc\nlicencia_hint: consultar\n---\n\nContenido 1\n"
            )
            (out_dir / "a.com" / "entidad2.md").write_text(
                "---\nurl: https://a.com/2\ndominio: a.com\nentidad_id: luna|tauro|planeta_en_signo\n"
                "faceta: planeta_en_signo\nfamilia: astrologia\nidioma: es\nsha256: def\nlicencia_hint: consultar\n---\n\nContenido 2\n"
            )
            (out_dir / "b.com" / "entidad1.md").write_text(
                "---\nurl: https://b.com/1\ndominio: b.com\nentidad_id: sol|aries|planeta_en_signo\n"
                "faceta: planeta_en_signo\nfamilia: astrologia\nidioma: es\nsha256: ghi\nlicencia_hint: consultar\n---\n\nContenido 3\n"
            )

            out_path = td / "informe.md"
            res = generar_informe(manifest, out_dir, out_path)

            # Verificar estructura del resultado
            self.assertIn("stats_sitio", res)
            self.assertIn("cobertura_faceta", res)
            self.assertIn("entidades_pocas", res)
            self.assertEqual(res["total_md"], 3)
            self.assertEqual(res["total_entidades"], 2)

            # Verificar stats_sitio
            stats = res["stats_sitio"]
            self.assertEqual(stats["a.com"]["descargadas"], 2)
            self.assertEqual(stats["a.com"]["chars_medios"], 2500)
            self.assertEqual(stats["b.com"]["bloqueadas_robots"], 1)
            self.assertEqual(stats["b.com"]["bloqueadas_antibot"], 1)
            self.assertEqual(stats["c.com"]["pausadas_429"], 1)
            self.assertEqual(stats["c.com"]["error"], 1)

            # Verificar cobertura por faceta
            self.assertIn("planeta_en_signo", res["cobertura_faceta"])
            faceta_stats = res["cobertura_faceta"]["planeta_en_signo"]
            self.assertEqual(faceta_stats["entidades_totales"], 2)
            self.assertEqual(faceta_stats["con_3_o_mas_sitios"], 0)
            self.assertEqual(faceta_stats["cobertura_pct"], 0.0)

            # Verificar entidades con <3 sitios
            entidades_pocas = res["entidades_pocas"]
            self.assertEqual(len(entidades_pocas), 2)  # sol|aries (2 sitios) + luna|tauro (1 sitio)
            self.assertEqual(entidades_pocas[0]["entidad_id"], "luna|tauro|planeta_en_signo")

    def test_cargar_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            manifest = td / "manifest.jsonl"
            manifest.write_text(json.dumps({"url": "x", "estado": "ok"}) + "\n")
            res = _cargar_manifest(manifest)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["estado"], "ok")

    def test_cargar_md_files(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            out_dir = td / "web"
            (out_dir / "a.com").mkdir(parents=True)
            (out_dir / "a.com" / "test.md").write_text(
                "---\nurl: https://a.com/1\ndominio: a.com\nentidad_id: test|test|test\n"
                "faceta: test\nfamilia: test\nidioma: es\nsha256: abc\nlicencia_hint: consultar\n---\n\nContenido\n"
            )
            md_files = _cargar_md_files(td / "web")
            self.assertEqual(len(md_files), 1)
            self.assertEqual(md_files[0]["entidad_id"], "test|test|test")
            self.assertEqual(md_files[0]["dominio"], "a.com")


if __name__ == "__main__":
    unittest.main()
