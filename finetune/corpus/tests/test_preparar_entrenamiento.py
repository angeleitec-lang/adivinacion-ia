import json
import os
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import preparar_entrenamiento as prep


def conversacion(*turnos):
    return {
        "conversations": [
            {"from": rol, "value": valor} for rol, valor in turnos
        ]
    }


def fila_valida(texto="¿Qué significa El Loco?", respuesta="El Loco abre un ciclo."):
    return conversacion(
        ("system", "Eres una tarotista."),
        ("human", texto),
        ("gpt", respuesta),
    )


class TestValidacion(unittest.TestCase):
    def test_fila_valida(self):
        self.assertEqual(prep.validar_fila(fila_valida()), [])

    def test_multiturno_valido(self):
        fila = conversacion(
            ("system", "Eres una tarotista."),
            ("human", "Hola"),
            ("gpt", "Hola, ¿qué necesitas?"),
            ("human", "Una tirada"),
            ("gpt", "Claro."),
        )
        self.assertEqual(prep.validar_fila(fila), [])

    def test_fila_sin_respuesta(self):
        fila = conversacion(
            ("system", "Eres una tarotista."),
            ("human", "¿Qué significa El Loco?"),
        )
        errores = prep.validar_fila(fila)
        self.assertTrue(any("termina en una respuesta" in e for e in errores))

    def test_system_duplicado(self):
        fila = conversacion(
            ("system", "Uno."),
            ("system", "Dos."),
            ("human", "Hola"),
            ("gpt", "Hola."),
        )
        errores = prep.validar_fila(fila)
        self.assertTrue(any("más de un turno 'system'" in e for e in errores))

    def test_rol_desconocido(self):
        fila = conversacion(
            ("system", "Eres una tarotista."),
            ("user", "Hola"),
            ("assistant", "Hola."),
        )
        errores = prep.validar_fila(fila)
        self.assertTrue(any("rol desconocido" in e for e in errores))

    def test_value_vacio(self):
        fila = conversacion(
            ("system", "Eres una tarotista."),
            ("human", "   "),
            ("gpt", "Hola."),
        )
        self.assertTrue(any("vacío" in e for e in prep.validar_fila(fila)))


class TestFormatos(unittest.TestCase):
    def test_sharegpt(self):
        salida = prep.convertir_fila(fila_valida(), "sharegpt")
        self.assertIn("conversations", salida)
        self.assertNotIn("messages", salida)
        self.assertEqual(salida["conversations"][1]["from"], "human")

    def test_chatml(self):
        salida = prep.convertir_fila(fila_valida(), "chatml")
        self.assertIn("messages", salida)
        self.assertEqual(
            [m["role"] for m in salida["messages"]], ["system", "user", "assistant"]
        )
        self.assertEqual(salida["messages"][1]["content"], "¿Qué significa El Loco?")

    def test_unicode_nfd(self):
        texto = unicodedata.normalize("NFD", "¿Qué significa José?")
        salida = prep.convertir_fila(fila_valida(texto=texto), "chatml")
        contenido = salida["messages"][1]["content"]
        self.assertTrue(unicodedata.is_normalized("NFC", contenido))
        self.assertEqual(contenido, "¿Qué significa José?")


class TestFugas(unittest.TestCase):
    def setUp(self):
        self.casos = [{
            "id": "eval-tarot_1-01",
            "origen": "evaluacion",
            "user": "Carta: El Loco (invertida). ¿Qué significa?",
        }]

    def test_id_de_evaluacion(self):
        filas = {"train": [{"linea": 1, "fila": {
            **fila_valida(), "id": "eval-tarot_1-01"
        }}], "val": []}
        fugas = prep.detectar_fugas(filas, self.casos)
        self.assertTrue(fugas)
        self.assertIn("id de evaluación", fugas[0]["motivo"])

    def test_prompt_de_evaluacion(self):
        filas = {"train": [{"linea": 1, "fila": fila_valida(
            texto="Carta: El Loco (invertida). ¿Qué significa?"
        )}], "val": []}
        fugas = prep.detectar_fugas(filas, self.casos)
        self.assertTrue(any("prompt idéntico" in f["motivo"] for f in fugas))

    def test_semilla_reservada(self):
        fila = {**fila_valida(), "metadatos": {"semilla": 560057}}
        filas = {"train": [{"linea": 1, "fila": fila}], "val": []}
        fugas = prep.detectar_fugas(filas, self.casos)
        self.assertTrue(any("semilla reservada" in f["motivo"] for f in fugas))

    def test_fuga_bloquea_la_salida(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "train.jsonl").write_text(
                json.dumps({**fila_valida(), "id": "eval-tarot_1-01"},
                           ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (raiz / "val.jsonl").write_text(
                json.dumps(fila_valida(texto="Otra pregunta"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            casos = raiz / "casos.jsonl"
            casos.write_text(json.dumps(self.casos[0], ensure_ascii=False) + "\n",
                             encoding="utf-8")
            salida = raiz / "salida"
            resultado = prep.preparar(raiz, salida, eval_casos=casos)
            self.assertEqual(resultado["semaforo"], "rojo")
            self.assertFalse((salida / "train.jsonl").exists())
            self.assertTrue((salida / "informe_entrenamiento.md").exists())


class TestEstadisticas(unittest.TestCase):
    def test_dataset_vacio(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "train.jsonl").write_text("", encoding="utf-8")
            (raiz / "val.jsonl").write_text("", encoding="utf-8")
            casos = raiz / "casos.jsonl"
            casos.write_text("", encoding="utf-8")
            resultado = prep.preparar(raiz, raiz / "salida", eval_casos=casos)
            self.assertEqual(resultado["semaforo"], "rojo")
            self.assertTrue(any("train" in e for e in resultado["errores"]))

    def test_estadisticas_sinteticas(self):
        tarot = {
            **fila_valida(
                texto="Tarot. Carta: El Loco (invertida)\nCarta: La Luna (al derecho)",
                respuesta="Dos cartas.",
            ),
            "familia": "tarot_1",
        }
        baraja = {
            **fila_valida(
                texto="Baraja española: As de Bastos (invertida), Tres de Copas",
                respuesta="Dos naipes.",
            ),
            "familia": "baraja_3",
        }
        etica = {
            **conversacion(
                ("system", "Eres una tarotista."),
                ("human", "Pienso en hacerme daño, ¿qué carta sale?"),
                ("gpt", "No puedo seguir; busca ayuda urgente."),
            ),
            "familia": "etica",
        }
        filas = {
            "train": [
                {"linea": 1, "fila": tarot},
                {"linea": 2, "fila": baraja},
                {"linea": 3, "fila": etica},
            ],
            "val": [{"linea": 1, "fila": fila_valida(texto="Otra")}],
            "test": [],
        }
        stats = prep.calcular_estadisticas(
            filas,
            {"train": 3, "val": 1, "test": 0},
            {"train": 0, "val": 0, "test": 0},
        )
        self.assertEqual(stats["filas"]["total_validas"], 4)
        self.assertEqual(stats["turnos"]["un_turno"], 4)
        self.assertEqual(stats["por_familia"]["tarot_1"], 1)
        self.assertEqual(stats["por_familia"]["baraja_3"], 1)
        self.assertEqual(stats["etica"]["n"], 1)
        self.assertEqual(stats["cartas"]["tarot"]["total_menciones"], 2)
        self.assertEqual(stats["cartas"]["espanol"]["total_menciones"], 2)
        self.assertEqual(stats["cartas"]["orientaciones"]["invertida"], 2)
        self.assertEqual(stats["cartas"]["orientaciones"]["derecha"], 1)
        self.assertGreater(stats["tokens"]["por_ejemplo"]["media"], 0)

    def test_multiturno_y_duplicados(self):
        fila = conversacion(
            ("system", "Eres una tarotista."),
            ("human", "Hola"),
            ("gpt", "Hola."),
            ("human", "Una tirada"),
            ("gpt", "Claro."),
        )
        filas = {
            "train": [{"linea": 1, "fila": fila}, {"linea": 2, "fila": fila}],
            "val": [], "test": [],
        }
        stats = prep.calcular_estadisticas(
            filas, {"train": 2, "val": 0, "test": 0},
            {"train": 0, "val": 0, "test": 0},
        )
        self.assertEqual(stats["turnos"]["multiturno"], 2)
        self.assertEqual(stats["duplicados"]["exactos"], 1)
        self.assertEqual(stats["duplicados"]["prompts_repetidos"], 1)


class TestSalidaCompleta(unittest.TestCase):
    def test_escribe_ambos_formatos(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            datos = raiz / "final"
            datos.mkdir()
            for split in ("train", "val", "test"):
                (datos / f"{split}.jsonl").write_text(
                    json.dumps(fila_valida(), ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            casos = raiz / "casos.jsonl"
            casos.write_text("", encoding="utf-8")
            for formato, clave in (("chatml", "messages"), ("sharegpt", "conversations")):
                salida = raiz / formato
                resultado = prep.preparar(
                    datos, salida, formato=formato, eval_casos=casos
                )
                self.assertNotEqual(resultado["semaforo"], "rojo")
                self.assertTrue((salida / "train.jsonl").exists())
                self.assertTrue((salida / "informe_entrenamiento.md").exists())
                with (salida / "train.jsonl").open(encoding="utf-8") as fh:
                    primera = json.loads(fh.readline())
                self.assertIn(clave, primera)
                self.assertNotIn("metadatos", primera)


if __name__ == "__main__":
    unittest.main()
