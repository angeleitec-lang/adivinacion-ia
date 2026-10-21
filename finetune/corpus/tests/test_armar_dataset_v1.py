"""Tests de armar_dataset_v1 (T103): orquestación reanudable de la cadena.

Cubren: fuga de evaluación (por id y por contenido) detectada y excluida,
duplicados exactos y casi duplicados dentro de familia, reanudación por huellas,
parada ante etapa rota y no tocar la entrada.
"""
import json
import os
import shutil
import sys
from pathlib import Path
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import armar_dataset_v1 as ad
import evaluacion_casos
import merge_final
import reverificar_fase1


def respuesta_unica(i: int) -> str:
    base = (f"La carta numero {i} representa el ciclo {i + 1} y su sombra "
            f"{i + 2}; en la posicion {i + 3} aparece el consejo {i + 4} para "
            f"el consultante que pregunta hoy. El numero {i + 5} refuerza el "
            f"mensaje {i + 6} y la lectura {i + 7} cierra el tiraje {i + 8}. "
            f"Ademas, el simbolo {i + 9} conecta con la pregunta {i + 10} del "
            f"consultante, mientras que el palo {i + 11} indica el camino "
            f"{i + 12} y la sombra {i + 13} revela lo oculto detras del "
            f"numero {i + 14}. La sintesis {i + 15} del tiraje sugiere "
            f"prudencia, y el reflejo {i + 16} del ciclo {i + 17} confirma "
            f"la lectura {i + 18} con claridad meridiana en esta tirada.")
    return base


def fila_mercury(i, bloque="tarot_1", humano=None, respuesta=None, turnos=1,
                id_extra=None):
    conv = [
        {"from": "system", "value": "Eres un lector experto en tarot."},
        {"from": "human",
         "value": humano or f"Consulta numero {i}: que me dicen las cartas?"},
        {"from": "gpt", "value": respuesta or respuesta_unica(i)},
    ]
    if turnos == 2:
        conv.append({"from": "human", "value": f"Y ademas, consulta {i}?"})
        conv.append({"from": "gpt", "value": respuesta_unica(i + 500)})
    fila = {"conversations": conv,
           "id": id_extra or f"{bloque}-{i:04d}",
           "bloque": bloque,
           "generador": "mercury-3"}
    return fila


def fila_real(i):
    return {
        "conversations": [
            {"from": "system", "value": "Asistente util."},
            {"from": "human", "value": f"Pregunta real numero {i} sobre "
                                      f"historia y cultura clasica."},
            {"from": "gpt", "value": respuesta_unica(i + 900) +
             " Texto adicional del corpus real para superar el minimo de "
             "longitud exigido por la fusion de datos."},
        ],
        "bloque": "real-corpus",
    }


def passthrough_reverificar(entrada, salida, rechazadas=None, eval_casos=None,
                           kb=None):
    """Simula el verificador vigente: todo valido (las filas fake no pasarian
    el verificador real de lecturas)."""
    filas = merge_final.load_jsonl(entrada)
    merge_final.write_jsonl(salida, filas)
    if rechazadas:
        merge_final.write_jsonl(rechazadas, [])
    return {"entrada": str(entrada), "salida": str(salida),
            "rechazadas": str(rechazadas), "total": len(filas),
            "validas": len(filas), "invalidas": 0, "evaluacion": 0,
            "motivos": {}}


def stub_build_dataset(argv):
    out = os.path.join(argv[argv.index("--out") + 1])
    os.makedirs(out, exist_ok=True)
    merge_final.write_jsonl(Path(out, "train.jsonl"),
                           [fila_real(i) for i in range(10)])
    merge_final.write_jsonl(Path(out, "val.jsonl"),
                           [fila_real(100 + i) for i in range(5)])
    return 0


class BaseTuberia(unittest.TestCase):
    """Fixture comun: entrada fake + salida temporal + etapas externas stubbeadas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir_entrada = os.path.join(self.tmp.name, "mercury")
        os.makedirs(self.dir_entrada)
        self.entrada = Path(self.dir_entrada) / "aceptadas.jsonl"
        self.salida = Path(self.tmp.name) / "dataset_fase1_v1"

        self.casos_eval = evaluacion_casos.generar_casos(560056)
        self.humano_eval = self.casos_eval[0]["user"]

        self._patches = [
            unittest.mock.patch.object(reverificar_fase1, "reverificar",
                                     side_effect=passthrough_reverificar),
            unittest.mock.patch.object(ad.bd, "main",
                                     side_effect=stub_build_dataset),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def escribir_entrada(self, filas):
        merge_final.write_jsonl(self.entrada, filas)

    def tuber(self):
        return ad.Tuberia(entrada=self.entrada, salida_dir=self.salida,
                         real_raw=str(Path(self.tmp.name) / "raw_real"),
                         manifest=str(Path(self.tmp.name) / "manifest.json"),
                         min_chars=20, max_chars=12000)

    def filas_base(self):
        filas = []
        # 10 validas por familia en 3 familias (para que val no quede vacia)
        for i in range(10):
            filas.append(fila_mercury(i, bloque="tarot_1"))
            filas.append(fila_mercury(100 + i, bloque="tarot_3"))
            filas.append(fila_mercury(200 + i, bloque="cruz_celta"))
        return filas


class TestAdaptarSharegpt(unittest.TestCase):
    def test_identidad_conserva_campos_y_nfc(self):
        fila = {"conversations": [
            {"from": "human", "value": "áéí"},
            {"from": "gpt", "value": "léctura"},
        ], "id": "x-1", "bloque": "tarot_1", "generador": "mercury-3",
            "calculos": {"a": 1}}
        nuevo = ad.adaptar_sharegpt(fila)
        self.assertEqual(nuevo["id"], "x-1")
        self.assertEqual(nuevo["bloque"], "tarot_1")
        self.assertEqual(nuevo["generador"], "mercury-3")
        self.assertEqual(nuevo["calculos"], {"a": 1})
        self.assertEqual(nuevo["conversations"][0]["value"],
                         "áéí")
        self.assertNotIn("prompt_user", nuevo)

    def test_plano_delega_en_ejecutor(self):
        fila = {"prompt_system": "s", "prompt_user": "u", "respuesta": "r",
               "id": "p-1", "bloque": "numerologia"}
        nuevo = ad.adaptar_sharegpt(fila)
        self.assertIn("conversations", nuevo)
        roles = [c["from"] for c in nuevo["conversations"]]
        self.assertIn("human", roles)
        self.assertIn("gpt", roles)
        self.assertEqual(nuevo["bloque"], "numerologia")


class TestFugaEvaluacion(BaseTuberia):
    def test_fuga_contenido_excluida(self):
        filas = self.filas_base()
        filas.append(fila_mercury(900, bloque="tarot_2",
                                 humano=self.humano_eval))
        self.escribir_entrada(filas)
        rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        descartes = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "descartes.jsonl"))
        motivos = {d["motivo"] for d in descartes}
        self.assertIn("fuga_evaluacion_contenido_qa", motivos)
        descartada = [d for d in descartes
                      if d["motivo"] == "fuga_evaluacion_contenido_qa"]
        self.assertEqual(len(descartada), 1)
        self.assertEqual(descartada[0]["id"], "tarot_2-0900")
        # y no aparece en ningun split final
        for split in ("train", "val", "test"):
            ruta = self.salida / f"{split}.jsonl"
            for fila in merge_final.load_jsonl(ruta):
                self.assertNotEqual(ad.humano_completo(fila), self.humano_eval)

    def test_fuga_id_excluida(self):
        filas = self.filas_base()
        filas.append(fila_mercury(901, bloque="tarot_2",
                                 id_extra="eval-tarot_2-99"))
        self.escribir_entrada(filas)
        rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        descartes = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "descartes.jsonl"))
        ids = {d["id"] for d in descartes
               if d["motivo"] == "fuga_evaluacion_id"}
        self.assertIn("eval-tarot_2-99", ids)
        for split in ("train", "val", "test"):
            for fila in merge_final.load_jsonl(
                    Path(self.salida, f"{split}.jsonl")):
                self.assertFalse(str(fila.get("id", "")).startswith("eval-"))


class TestDuplicados(BaseTuberia):
    def test_exacto_y_casi_misma_familia_excluidos(self):
        filas = self.filas_base()
        base = filas[0]  # tarot_1-0000
        filas.append(fila_mercury(910, bloque="tarot_1",
                                 humano=ad.humano_completo(base),
                                 respuesta=ad.respuesta_completa(base)))
        casi = ad.respuesta_completa(base).replace("sombra", "luz", 1)
        filas.append(fila_mercury(911, bloque="tarot_1",
                                 humano=ad.humano_completo(base),
                                 respuesta=casi))
        self.escribir_entrada(filas)
        rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        descartes = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "descartes.jsonl"))
        motivos = {d["id"]: d["motivo"] for d in descartes}
        self.assertEqual(motivos.get("tarot_1-0910"), "duplicado_exacto")
        self.assertEqual(motivos.get("tarot_1-0911"), "casi_duplicado")

    def test_misma_contenido_otra_familia_conservada_en_filtro(self):
        filas = self.filas_base()
        base = filas[0]
        filas.append(fila_mercury(912, bloque="astro_natal",
                                 humano=ad.humano_completo(base),
                                 respuesta=ad.respuesta_completa(base)))
        self.escribir_entrada(filas)
        rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        filtradas = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "filtradas.jsonl"))
        ids = {f.get("id") for f in filtradas}
        self.assertIn("astro_natal-0912", ids)
        descartes = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "descartes.jsonl"))
        self.assertNotIn("astro_natal-0912",
                        {d["id"] for d in descartes})


class TestReanudacion(BaseTuberia):
    def test_segunda_pasada_omite_todo(self):
        self.escribir_entrada(self.filas_base())
        self.assertEqual(self.tuber().ejecutar(), 0)
        reg = self.salida / "_etapas" / "registro.jsonl"
        n1 = len(merge_final.load_jsonl(reg))
        train1 = open(self.salida / "train.jsonl",
                     "rb").read()
        with unittest.mock.patch.object(
                ad.Tuberia, "etapa_snapshot",
                side_effect=AssertionError("debio omitirse")) as m_snap:
            rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        m_snap.assert_not_called()
        self.assertEqual(len(merge_final.load_jsonl(reg)), n1)
        train2 = open(self.salida / "train.jsonl",
                     "rb").read()
        self.assertEqual(train1, train2)

    def test_cambio_de_entrada_vuelve_a_correr(self):
        self.escribir_entrada(self.filas_base())
        self.assertEqual(self.tuber().ejecutar(), 0)
        filas = self.filas_base() + [fila_mercury(777, bloque="numerologia")]
        self.escribir_entrada(filas)
        self.assertEqual(self.tuber().ejecutar(), 0)
        filtradas = merge_final.load_jsonl(
            Path(self.salida, "02_filtradas", "filtradas.jsonl"))
        self.assertIn("numerologia-0777", {f.get("id") for f in filtradas})


class TestParadaEtapaRota(BaseTuberia):
    def test_falla_reverificar_para_y_luego_reanuda(self):
        self.escribir_entrada(self.filas_base())
        with unittest.mock.patch.object(
                reverificar_fase1, "reverificar",
                side_effect=RuntimeError("verificador roto")):
            rc = self.tuber().ejecutar()
        self.assertEqual(rc, 1)
        reg = merge_final.load_jsonl(
            Path(self.salida, "_etapas", "registro.jsonl"))
        ultima_rev = [e for e in reg if e["etapa"] == "reverificar"][-1]
        self.assertEqual(ultima_rev["estado"], "fallida")
        self.assertFalse(os.path.exists(
            self.salida / "02_filtradas" / "filtradas.jsonl"))
        # arreglada la etapa, la segunda pasada reanuda desde reverificar
        rc = self.tuber().ejecutar()
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(
            self.salida / "02_filtradas" / "filtradas.jsonl"))
        self.assertTrue(os.path.exists(
            self.salida / "preparado" / "informe_entrenamiento.md"))

    def test_fallo_validar_deja_fallida(self):
        self.escribir_entrada(self.filas_base())
        with unittest.mock.patch.object(
                ad.vs, "main", return_value=2):
            rc = self.tuber().ejecutar()
        self.assertEqual(rc, 1)
        reg = merge_final.load_jsonl(
            Path(self.salida, "_etapas", "registro.jsonl"))
        self.assertEqual([e for e in reg if e["etapa"] == "validar"][-1]
                         ["estado"], "fallida")


class TestNoTocaEntrada(BaseTuberia):
    def test_entrada_invariable(self):
        self.escribir_entrada(self.filas_base())
        sha_antes = ad.sha256_archivo(self.entrada)
        antes = sorted(os.listdir(self.dir_entrada))
        self.assertEqual(self.tuber().ejecutar(), 0)
        self.assertEqual(ad.sha256_archivo(self.entrada), sha_antes)
        self.assertEqual(sorted(os.listdir(self.dir_entrada)), antes)


class TestEtapaEval(BaseTuberia):
    def test_eval_congela_tres_semillas_y_sharegpt(self):
        self.escribir_entrada(self.filas_base())
        self.assertEqual(self.tuber().ejecutar(), 0)
        for semilla in evaluacion_casos.SEMILLAS_RESERVADAS:
            ruta = (self.salida / "_etapas" / "eval" / f"evaluacion_{semilla}.jsonl")
            self.assertTrue(os.path.exists(ruta))
        sh = merge_final.load_jsonl(
            Path(self.salida, "_etapas", "eval",
                        "evaluacion_sharegpt.jsonl"))
        self.assertEqual(len(sh), 3 * len(self.casos_eval))
        humanos = merge_final.cargar_humanos_evaluacion(
            [self.salida / "_etapas" / "eval" / "evaluacion_sharegpt.jsonl"])
        self.assertNotIn("", humanos)
        self.assertIn(merge_final._norm(self.humano_eval), humanos)


if __name__ == "__main__":
    unittest.main()
