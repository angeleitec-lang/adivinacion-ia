"""Tests de T112: correcciones sobre el dataset v1 (fugas, split agrupado, puerta).

Cubren: deteccion de fuga por la normalizacion de qa_dataset (incluida
coincidencia parcial por n-gramas), split agrupado determinista que mantiene
cada situacion en un unico split, puerta de calidad del corpus real con
exclusion si no alcanza el minimo, y aborto de la etapa qa (semaforo rojo)
cuando queda una fuga o un solape exacto entre splits.
"""
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import armar_dataset_v1 as ad
import merge_final as mf
import qa_dataset as qa


def _conv(humano, respuesta, system="Eres un lector experto."):
    return [{"from": "system", "value": system},
            {"from": "human", "value": humano},
            {"from": "gpt", "value": respuesta}]


def fila(humano, respuesta, bloque="tarot_1", id_=None):
    return {"conversations": _conv(humano, respuesta),
            "id": id_ or f"{bloque}-x", "bloque": bloque,
            "generador": "mercury-3"}


def situacion(i, pregunta="¿como evolucionara mi trabajo?"):
    return (f"Cartas: \u2014\ndata (no)\n"
            f"Carta 1: La Sombra {i} (al derecho)\n"
            f"Pregunta del consultante: \"{pregunta}\"")


RESP_OK = ("La carta mostrada habla de un ciclo que se cierra con prudencia; "
           "convien\u00e9 observar los silencios del consultante antes de "
           "actuar, porque la prisa nubla el juicio y la duda se disipa "
           "cuando el mapa interior est\u00e1 claro.")


def real_resp(i: int) -> str:
    return (f"El matiz {i} aclara la tirada: la carta {i} mostrada habla de "
            f"un ciclo que se cierra con prudencia y serenidad numerada {i}; "
            f"conviene observar los silencios del consultante antes de "
            f"actuar, porque la prisa nubla el juicio y la duda se disipa "
            f"cuando el mapa interior est\u00e1 claro.")


def real_humano(i: int) -> str:
    return (f"Carta 1: El Sol {i} (al derecho) en la tirada {i} de tarot; "
            f"pregunta {i} del consultante sobre las cartas y su lectura.")


class TestClaveSituacion(unittest.TestCase):
    def test_misma_situacion_distinto_texto_plantilla(self):
        h1 = "Contexto: x\n" + situacion(1) + "\nReferencia (significados de la tradicion): tarot"
        h2 = situacion(1) + "\nESQUEMA OBLIGATORIO: respuesta breve"
        f1 = fila(h1, RESP_OK, bloque="tarot_1", id_="a")
        f2 = fila(h1, RESP_OK, bloque="lectura_completa", id_="b")
        self.assertEqual(qa.clave_situacion(f1), qa.clave_situacion(f2))

    def test_distinta_carta_distinta_clave(self):
        f1 = fila(situacion(1), RESP_OK)
        f2 = fila(situacion(2), RESP_OK)
        self.assertNotEqual(qa.clave_situacion(f1), qa.clave_situacion(f2))


class TestSplitAgrupado(unittest.TestCase):
    def _items(self):
        items = []
        for sit in range(20):
            for bloque in ("tarot_1", "tarot_pregunta"):
                items.append((fila(situacion(sit), RESP_OK,
                                   bloque=bloque,
                                   id_=f"{bloque}-{sit}"), bloque))
        return items

    def test_grupo_completo_en_un_mismo_split(self):
        items = self._items()
        train, val, test = mf.split_agrupado(items, 42, 0.9, 0.05)
        by_id = {}
        for destino, pares in (("train", train), ("val", val), ("test", test)):
            for f, _bl in pares:
                by_id[f["id"]] = (destino, qa.clave_situacion(f))
        grupos = {}
        for ident, (destino, clave) in by_id.items():
            grupos.setdefault(clave, set()).add(destino)
        for clave, destinos in grupos.items():
            self.assertEqual(len(destinos), 1,
                             f"situacion {clave} repartida en {destinos}")
        self.assertEqual(len(by_id), len(items))

    def test_determinismo_y_proporcion(self):
        items = self._items()
        a = mf.split_agrupado(items, 42, 0.9, 0.05)
        b = mf.split_agrupado(items, 42, 0.9, 0.05)
        ids = lambda r: [sorted(f["id"] for f, _ in s) for s in r]
        self.assertEqual(ids(a), ids(b))
        train, val, test = a
        self.assertGreater(len(train), len(val))
        self.assertGreater(len(train), len(test))
        c = mf.split_agrupado(items, 7, 0.9, 0.05)
        self.assertNotEqual(ids(a), ids(c))


class TestPuertaCalidad(unittest.TestCase):
    def test_motivos_truncada_y_web(self):
        trunc = ("La lectura de las cartas sugiere atencion porque el ciclo "
                 "pendiente se repite y el consultante debe revisar sus "
                 "silencios antes de decidir el rumbo que toma hoy en la "
                 "tirada de tarot consultada")
        f_trunc = fila(real_humano(1), trunc, bloque="real-corpus")
        self.assertIn("respuesta_truncada", mf.fallos_puerta_calidad(f_trunc))
        web = fila(real_humano(2), RESP_OK + " Visita http://ejemplo.com "
                   "la pagina del consultorio.", bloque="real-corpus")
        fallos = mf.fallos_puerta_calidad(web)
        self.assertTrue(any(x.startswith("resto_web") for x in fallos))
        self.assertEqual(mf.fallos_puerta_calidad(
            fila(real_humano(3), real_resp(3), bloque="real-corpus")), [])

    def test_fusionar_descarta_y_excluye_real(self):
        mala = fila(real_humano(1), "La carta del tarot no dice nada",
                    bloque="real-corpus")
        buena = fila(real_humano(2), real_resp(2), bloque="real-corpus")
        cfg = {"seed": 42, "train_ratio": 0.9, "val_ratio": 0.05,
               "puerta_real": True, "min_real_filas": 100}
        res = mf.fusionar([mala], [buena], [], [], cfg)
        rep = res["report"]
        self.assertEqual(rep["descartes"]["puerta_calidad"], 1)
        self.assertEqual(rep["descartes"]["real_excluido_por_minimo"], 1)
        for split in ("train", "val", "test"):
            for f in res[split]:
                self.assertNotEqual(f.get("bloque"), "real-corpus")

    def test_fusionar_conserva_real_suficiente(self):
        buenas = [fila(real_humano(i), real_resp(i), bloque="real-corpus")
                  for i in range(1, 5)]
        cfg = {"seed": 42, "train_ratio": 0.9, "val_ratio": 0.05,
               "puerta_real": True, "min_real_filas": 3}
        res = mf.fusionar(buenas[:2], buenas[2:], [], [], cfg)
        self.assertEqual(res["report"]["descartes"]["real_excluido_por_minimo"],
                         0)
        total = sum(len(res[s]) for s in ("train", "val", "test"))
        self.assertEqual(total, 4)


class TestFiltrarFugasEval(unittest.TestCase):
    HUM_EVAL = (
        "Datos del consultante:\nFecha de nacimiento: 3 de mayo de 1990\n"
        "Carta 1: La Torre (invertida)\nCarta 2: El Diablo (al derecho)\n"
        "Pregunta del consultante: \"\u00bfqu\u00e9 bloqueos arrastro en mi "
        "relaci\u00f3n de pareja desde hace a\u00f1os y c\u00f3mo suelto?\"\n"
        "Contexto: trabajo estable, pareja estable, sin novedades.\n"
        "Referencia (significados de la tradici\u00f3n): torre=ruptura")

    def casos(self):
        return {"eval-tarot_2-00": {"id": "eval-tarot_2-00",
                                    "user": self.HUM_EVAL}}

    def test_igualdad_por_normalizacion_distinta(self):
        # mismo prompt con tildes/markdown distintos: la normalizacion qa lo
        # detecta como fuga de contenido aunque el texto crudo difiera
        humano = (self.HUM_EVAL.replace(": ", " \u2014 ")
                  .replace("\"", "\u00ab\u00bb")).upper()
        fila_igual = fila(humano, RESP_OK, bloque="tarot_2", id_="t1")
        fila_ok = fila(situacion(9), RESP_OK, bloque="tarot_2", id_="t2")
        mantenidas, descartes, _boiler = ad.filtrar_fugas_eval(
            [fila_igual, fila_ok], self.casos())
        self.assertEqual([d["id"] for d in descartes], ["t1"])
        self.assertEqual(descartes[0]["motivo"],
                         "fuga_evaluacion_contenido_qa")
        self.assertEqual([f["id"] for f in mantenidas], ["t2"])

    def test_umbral_cinco_ngramas(self):
        # comparte solo 4 ventanas de 12 palabras con el eval -> se mantiene
        arrastre = self.HUM_EVAL.split("\n")
        core = ("trabajo estable, pareja estable, sin novedades y sin "
                "urgencias que alteren la rutina diaria del hogar compartido")
        base = (f"Carta 1: La Estrella (al derecho)\nPregunta del "
                f"consultante: \"\u00bfqu\u00e9 bloqueos arrastro?\"\n{core}\n"
                f"Contexto: {arrastre[5]}")
        casi = fila(base, RESP_OK, bloque="tarot_2", id_="c1")
        compartidos = None
        mantenidas, descartes, _boiler = ad.filtrar_fugas_eval(
            [casi], self.casos())
        ids_desc = [d["id"] for d in descartes]
        if "c1" in ids_desc:
            d = [x for x in descartes if x["id"] == "c1"][0]
            self.assertIn(d["motivo"],
                          ("fuga_evaluacion_ngramas",
                           "fuga_evaluacion_contenido_qa"))
        else:
            self.assertIn("c1", [f["id"] for f in mantenidas])

    def test_fuga_ngramas_reales(self):
        # copia textual de 5+ ventanas del user eval (sin ser el prompt entero)
        trozo = self.HUM_EVAL.replace(
            "Referencia (significados de la tradici\u00f3n): torre=ruptura",
            "Contexto extra propio del consultante sobre su vida diaria.")
        replicado = (self.HUM_EVAL.split("\n")[4] + "\n" +
                     self.HUM_EVAL.split("\n")[1] + "\n" +
                     self.HUM_EVAL.split("\n")[0] + "\n" + trozo)
        f = fila(replicado, RESP_OK, bloque="tarot_2", id_="n1")
        mantenidas, descartes, _boiler = ad.filtrar_fugas_eval(
            [f], self.casos())
        self.assertEqual([d["id"] for d in descartes], ["n1"])
        self.assertEqual(descartes[0]["motivo"], "fuga_evaluacion_ngramas")


class TestEtapaQaAborta(unittest.TestCase):
    def _preparar(self, tmp, humano):
        salida = Path(tmp)
        respuesta = RESP_OK
        (salida / "train.jsonl").write_text(
            json.dumps(fila(humano, respuesta, bloque="tarot_1", id_="d1"),
                       ensure_ascii=False) + "\n", encoding="utf-8")
        (salida / "val.jsonl").write_text(
            json.dumps(fila(humano, respuesta, bloque="tarot_1", id_="d2"),
                       ensure_ascii=False) + "\n", encoding="utf-8")
        (salida / "test.jsonl").write_text("", encoding="utf-8")
        ev = salida / "_etapas" / "eval"
        ev.mkdir(parents=True)
        caso = {"id": "eval-tarot_1-00", "familia": "tarot_1",
                "user": "Pregunta del consultante: \"¿cual es mi destino?\"",
                "system": "x", "tarea": "leer", "comprobaciones": []}
        for seed in qa.EVAL_SEEDS:
            (ev / f"evaluacion_{seed}.jsonl").write_text(
                json.dumps(caso, ensure_ascii=False) + "\n", encoding="utf-8")
        tub = ad.Tuberia(entrada=str(salida / "noexiste.jsonl"),
                         salida_dir=str(salida))
        return tub

    def test_aborta_por_solape_entre_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            tub = self._preparar(tmp, situacion(3))
            with self.assertRaises(RuntimeError) as ctx:
                tub.etapa_qa()
            self.assertIn("ROJO", str(ctx.exception))

    def test_aborta_por_fuga_con_eval(self):
        with tempfile.TemporaryDirectory() as tmp:
            humano = ("Carta 1: La Estrella (al derecho)\nPregunta del "
                      "consultante: \"\u00bfcual es mi destino?\""
                      "\nContexto: consulta larga con detalle sobre el "
                      "trabajo y la familia del consultante interesado.")
            tub = self._preparar(tmp, humano)
            # mismo prompt en train y val + coincide con el caso eval
            with self.assertRaises(RuntimeError):
                tub.etapa_qa()

    def test_verde_cuando_no_hay_fugas(self):
        with tempfile.TemporaryDirectory() as tmp:
            salida = Path(tmp)
            h1 = situacion(1) + " extra uno unico para este split"
            h2 = situacion(2) + " extra dos unico para la validacion"
            (salida / "train.jsonl").write_text(
                json.dumps(fila(h1, RESP_OK, id_="g1"), ensure_ascii=False)
                + "\n", encoding="utf-8")
            (salida / "val.jsonl").write_text(
                json.dumps(fila(h2, RESP_OK, id_="g2"), ensure_ascii=False)
                + "\n", encoding="utf-8")
            (salida / "test.jsonl").write_text("", encoding="utf-8")
            ev = salida / "_etapas" / "eval"
            ev.mkdir(parents=True)
            caso = {"id": "eval-tarot_1-00", "familia": "tarot_1",
                    "user": "Pregunta del consultante: \"¿nada que ver?\"",
                    "system": "x", "tarea": "leer", "comprobaciones": []}
            for seed in qa.EVAL_SEEDS:
                (ev / f"evaluacion_{seed}.jsonl").write_text(
                    json.dumps(caso, ensure_ascii=False) + "\n",
                    encoding="utf-8")
            tub = ad.Tuberia(entrada=str(salida / "noexiste.jsonl"),
                             salida_dir=str(salida))
            stats = tub.etapa_qa()
            self.assertEqual(stats["semaforo_qa"], "verde")


if __name__ == "__main__":
    unittest.main()
