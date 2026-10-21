# -*- coding: utf-8 -*-
"""Tests de qa_dataset.py con datos sintéticos (sin red ni dataset real)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qa_dataset as qa


def fila(sistema=qa.SYSTEM_FASE1, humano="h", gpt="g", **kw):
    f = {"conversations": [
        {"from": "system", "value": sistema},
        {"from": "human", "value": humano},
        {"from": "gpt", "value": gpt},
    ]}
    f.update(kw)
    return f


RESP_OK = ("El Loco habla de los nuevos comienzos y la inocencia original, "
           "una energía que abre el camino con frescura y confianza plena.")


class Utilidades(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(qa.normalizar("¡Hola, Mundo 42!"), "hola mundo 42")

    def test_sin_plantilla(self):
        t = ("Tarot: 1 carta.\nCarta 1: El Loco (al derecho)\n\n"
             "Referencia (significados de la tradición): blabla\n"
             "Responde a la pregunta.")
        self.assertNotIn("Referencia", qa.sin_plantilla(t))
        self.assertIn("El Loco", qa.sin_plantilla(t))

    def test_gramaturcas(self):
        toks = " ".join(f"palabra{i}" for i in range(20))
        gs = qa.gramaturcas(qa.normalizar(toks))
        self.assertEqual(len(gs), 20 - qa.N_GRAM + 1)
        self.assertEqual(gs, qa.gramaturcas(qa.normalizar(toks)))


class Formato(unittest.TestCase):
    def test_fila_sana(self):
        filas = [("train", 1, fila(humano="¿Qué significa El Loco en el tarot?",
                                   gpt=RESP_OK, id=1, bloque="tarot_1"))]
        self.assertEqual(qa.chequear_formato(filas), [])

    def test_roles_y_vacios(self):
        f = {"conversations": [
            {"from": "system", "value": qa.SYSTEM_FASE1},
            {"from": "gpt", "value": RESP_OK},
            {"from": "human", "value": ""},
        ]}
        h = qa.chequear_formato([("train", 1, f)])
        chequeos = {x["chequeo"] for x in h}
        self.assertIn("esquema", chequeos)
        self.assertIn("valores_vacios", chequeos)

    def test_id_repetido(self):
        a = fila(humano="primera pregunta distinta del consultante", gpt=RESP_OK, id=7)
        b = fila(humano="segunda pregunta distinta del consultante", gpt=RESP_OK, id=7)
        h = qa.chequear_formato([("train", 1, a), ("val", 2, b)])
        self.assertEqual([x["chequeo"] for x in h], ["id_repetido"])

    def test_no_nfc_y_mojibake(self):
        nfd = "El Loco significa nuevo co" + "mo" + "i" + "́"  # i + acento combinante
        h = qa.chequear_formato([("train", 1, fila(humano=nfd * 3, gpt=RESP_OK))])
        self.assertTrue(any(x["chequeo"] == "no_nfc" for x in h))
        h2 = qa.chequear_formato([("train", 1, fila(
            humano="Carta: El Loco Ãºnica referencia valedera", gpt=RESP_OK))])
        self.assertTrue(any(x["chequeo"] == "mojibake" for x in h2))

    def test_truncada_y_longitud(self):
        h = qa.chequear_formato([
            ("train", 1, fila(humano="pregunta del consultante aqui",
                              gpt="esta respuesta termina sin ningun signo de puntuacion "
                                  "final y por eso parece cortada o incompleta para el "
                                  "lector que la recibe hoy")),
            ("train", 2, fila(humano="pregunta del consultante aqui", gpt="corta")),
            ("train", 3, fila(humano="breve", gpt=RESP_OK)),
        ])
        chequeos = [x["chequeo"] for x in h]
        self.assertIn("respuesta_truncada", chequeos)
        self.assertIn("longitud_extrema", chequeos)

    def test_system_no_autorizado(self):
        h = qa.chequear_formato([("train", 1, fila(
            sistema="Eres un oráculo egipcio.", humano="pregunta valida del consultante",
            gpt=RESP_OK))])
        self.assertTrue(any(x["chequeo"] == "system_no_autorizado" for x in h))

    def test_variante_autorizada(self):
        h = qa.chequear_formato([("train", 1, fila(
            sistema=qa.SYSTEM_VARIANTE, humano="pregunta valida del consultante",
            gpt=RESP_OK))])
        self.assertEqual(h, [])


class FugasEval(unittest.TestCase):
    def setUp(self):
        self.caso = {
            "id": "eval-tarot_1-01", "familia": "tarot_1",
            "user": ("Tarot: 1 carta.\nCarta 1: El Emperador (al derecho)\n"
                     "Contexto: trabajo\nPregunta del consultante: \"¿Cómo va mi "
                     "jefe?\n\nReferencia (significados de la tradición): texto largo"),
        }
        self.casos = {self.caso["id"]: self.caso}

    def test_prompt_identico(self):
        propio = ("Tarot: 1 carta.\nCarta 1: El Emperador (al derecho)\nContexto: "
                  "trabajo\nPregunta del consultante: \"¿Cómo va mi jefe?\"")
        h = qa.fugas_eval([("train", 5, fila(humano=propio + "\nReferencia (significados de la tradición): otra",
                                             gpt=RESP_OK))], self.casos)
        self.assertTrue(any(x["chequeo"] == "fuga_eval_prompt_identico"
                            for x in h["hallazgos"]))

    def test_fragmento(self):
        humano = ("Tarot: 1 carta.\nCarta 1: El Emperador (al derecho)\nContexto: "
                  "trabajo\nPregunta del consultante: \"¿Cómo va mi jefe hoy martes?\"")
        h = qa.fugas_eval([("train", 1, fila(humano=humano, gpt=RESP_OK))], self.casos)
        self.assertTrue(any(x["chequeo"] == "fuga_eval_fragmento" for x in h["hallazgos"]))

    def test_boilerplate_excluido(self):
        comunes = " ".join(f"palabra{i}" for i in range(14))
        filas = []
        for i in range(qa.BOILERPLATE_DF):
            humano = f"{comunes} fila unica {i} con tokens extra para que difieran"
            filas.append(("train", i + 1, fila(humano=humano, id=i, gpt=RESP_OK)))
        caso = {"id": "eval-x-01",
                "user": f"{comunes} cierre distinto del caso de evaluacion aqui"}
        h = qa.fugas_eval(filas, {caso["id"]: caso})
        self.assertEqual(h["hallazgos"], [])

    def test_fuga_por_id(self):
        h = qa.fugas_eval([("train", 1, fila(
            humano="pregunta valida del consultante aqui", gpt=RESP_OK,
            id="eval-tarot_1-01"))], self.casos)
        self.assertTrue(any(x["chequeo"] == "fuga_eval_id" for x in h["hallazgos"]))


class FugasSplits(unittest.TestCase):
    def _f(self, humano, bloque="tarot_1", ln=1):
        return ("train", ln, fila(humano=humano, gpt=RESP_OK, id=ln, bloque=bloque))

    def test_identico_entre_splits(self):
        base = ("Tarot: 1 carta.\nCarta 1: La Luna (al derecho)\nContexto: amor\n"
                "Pregunta del consultante: \"¿Volvera?\"")
        filas = [("train", 1, fila(humano=base, gpt=RESP_OK, id=1, bloque="tarot_1")),
                 ("val", 2, fila(humano=base, gpt=RESP_OK, id=2, bloque="tarot_1"))]
        r = qa.fugas_splits(filas)
        self.assertEqual(r["resumen"]["prompts_exactos_entre_splits"], 1)
        self.assertEqual(r["resumen"]["prompts_completos_exactos_entre_splits"], 1)
        self.assertEqual(len(r["hallazgos"]), 1)

    def test_casi_identico(self):
        a = ("Tarot: 1 carta.\nCarta 1: La Luna (al derecho)\nContexto: amor\n"
             "Pregunta del consultante: \"¿Volvera mi amor pronto?\"")
        b = ("Tarot: 1 carta.\nCarta 1: La Luna (al derecho)\nContexto: amor sincero\n"
             "Pregunta del consultante: \"¿Volvera mi amor pronto?\"")
        filas = [("train", 1, fila(humano=a, gpt=RESP_OK, id=1, bloque="tarot_1")),
                 ("test", 2, fila(humano=b, gpt=RESP_OK, id=2, bloque="tarot_1"))]
        r = qa.fugas_splits(filas)
        self.assertEqual(r["resumen"]["buckets_misma_carta_pregunta"], 1)
        self.assertEqual(len(r["casi_identico_pares"]), 1)

    def test_sin_fuga_interna(self):
        filas = [("train", 1, fila(humano="pregunta A distinta del consultante aqui",
                                   gpt=RESP_OK, id=1, bloque="tarot_1")),
                 ("val", 2, fila(humano="pregunta B totalmente distinta y larga aqui",
                                 gpt=RESP_OK, id=2, bloque="tarot_1"))]
        r = qa.fugas_splits(filas)
        self.assertEqual(r["hallazgos"], [])
        self.assertEqual(r["resumen"]["buckets_misma_carta_pregunta"], 0)


class Sanidad(unittest.TestCase):
    def test_tarot_ok(self):
        f = fila(humano="Carta 1: El Loco (al derecho)",
                 gpt=RESP_OK, bloque="tarot_1")
        self.assertEqual(qa._sanidad_fila(f), [])

    def test_cartas_no_citadas(self):
        f = fila(humano="Carta 1: El Colgado (al derecho)\nCarta 2: La Torre (al derecho)",
                 gpt="Esta lectura habla de cambios, finales y transformacion profunda.",
                 bloque="tarot_3")
        self.assertTrue(any(x.startswith("cartas_no_citadas")
                            for x in qa._sanidad_fila(f)))

    def test_orientacion_ignorada(self):
        f = fila(humano="Carta 1: El Diablo (invertida)",
                 gpt="El diablo representa las ataduras y los apegos materiales del consultante.",
                 bloque="tarot_1")
        self.assertEqual(qa._sanidad_fila(f), ["orientacion_ignorada:el diablo"])

    def test_numerologia(self):
        f = fila(humano="Datos numerológicos:\n- Camino de vida: 7",
                 gpt="Tu número lo dice todo sobre tu perfil personal hoy.",
                 bloque="numerologia")
        self.assertTrue(any(x.startswith("numeros_no_citados")
                            for x in qa._sanidad_fila(f)))

    def test_astro(self):
        f = fila(humano="Posiciones:\n- Sol: Aries 11°46' (casa 5)\n- Luna: Géminis 2° (casa 7)",
                 gpt="Tu carta muestra aspectos armónicos entre los planetas implicados.",
                 bloque="astro_natal")
        self.assertTrue(any(x.startswith("signos_no_citados")
                            for x in qa._sanidad_fila(f)))

    def test_sin_bloque_resto_web(self):
        f = fila(humano="¿Qué significa el sol?",
                 gpt="El sol es una estrella. Visita nuestra página para más.",
                 bloque=None)
        self.assertTrue(any(x.startswith("resto_web") for x in qa._sanidad_fila(f)))

    def test_muestreo_determinista(self):
        filas = [("train", i, fila(humano="pregunta del consultante", gpt=RESP_OK,
                                   id=i, bloque="tarot_1")) for i in range(5)]
        a = qa.sanidad_muestreo(filas, semilla=42, muestras=3)
        b = qa.sanidad_muestreo(filas, semilla=42, muestras=3)
        self.assertEqual(a, b)
        self.assertEqual(a["tabla"][0]["muestra"], 3)


class RunQa(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            ds = Path(tmp) / "ds"
            ds.mkdir()
            eval_dir = ds / "_etapas" / "eval"
            eval_dir.mkdir(parents=True)
            humano = ("Tarot: 1 carta.\nCarta 1: El Loco (al derecho)\n"
                      "Pregunta del consultante: \"¿Qué me espera?\"")
            filas = {"train": [fila(humano=humano, gpt=RESP_OK, id=1, bloque="tarot_1")],
                     "val": [fila(humano="¿Quien soy? pregunta larga del consultante",
                                  gpt="Eres una persona compleja, con luces y sombras, "
                                      "capaz de transformar los desafios en aprendizajes.",
                                  id=2, bloque="tarot_pregunta")],
                     "test": []}
            for split, fs in filas.items():
                with open(ds / f"{split}.jsonl", "w", encoding="utf-8") as fh:
                    for f in fs:
                        fh.write(json.dumps(f, ensure_ascii=False) + "\n")
            caso = {"id": "eval-tarot_1-01", "familia": "tarot_1", "user": humano}
            for sem in qa.EVAL_SEEDS:
                with open(eval_dir / f"evaluacion_{sem}.jsonl", "w",
                          encoding="utf-8") as fh:
                    fh.write(json.dumps(caso, ensure_ascii=False) + "\n")
            out = Path(tmp) / "out"
            rep = qa.run_qa(ds, out_dir=out, semilla=7, muestras=2)
            self.assertEqual(rep["conteos"]["total"], 2)
            self.assertTrue(any(h["chequeo"] == "fuga_eval_prompt_identico"
                                for h in rep["fugas_eval"]["hallazgos"]))
            self.assertTrue((out / "qa_report.json").exists())
            self.assertTrue((out / "findings.tsv").exists())
            self.assertTrue((out / "resumen.txt").exists())
            self.assertEqual(rep["resumen"]["hallazgos_formato"], 0)


if __name__ == "__main__":
    unittest.main()
