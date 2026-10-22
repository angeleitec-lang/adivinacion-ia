"""Auditoría ronda 7 (T123): familias nuevas, fugas y traducción.

Cada prueba describe el comportamiento CORRECTO. Las que fallan hoy quedan
marcadas ``expectedFailure`` para que ``check.sh`` siga en CHECK OK; cuando se
arregle el defecto, se convertirán en ``unexpected success`` y habrá que quitar
la marca. Ver ``docs/AUDITORIA_RONDA7.md``.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import evaluacion_casos as ec  # noqa: E402
import fase1_prompts as fp  # noqa: E402
import merge_final as mf  # noqa: E402
import qa_dataset as qa  # noqa: E402
import traducir_afirmaciones as ta  # noqa: E402


NATAL = {
    "planetas": {
        "Sol": {"signo": "Aries", "lon": 10.0},
        "Luna": {"signo": "Tauro", "lon": 40.0},
        "Venus": {"signo": "Aries", "lon": 15.0},
        "Marte": {"signo": "Virgo", "lon": 160.0},
        "Saturno": {"signo": "Piscis", "lon": 350.0},
    },
    "ascendente": {"signo": "Leo"},
}


def _aceptada(tarea, texto):
    ok, motivos = fp.verificar_lectura(tarea, texto)
    return ok, motivos


class TestFalsosNegativos(unittest.TestCase):
    def test_transitos_posicion_y_fecha_inventadas(self):
        tarea = {
            "familia": "transitos",
            "calculos": {
                "carta_natal": NATAL,
                "transitos": {
                    "fecha_transito": "2026-10-15",
                    "aspectos": [{
                        "planeta_transito": "Marte", "aspecto": "cuadratura",
                        "planeta_natal": "Sol",
                    }],
                },
            },
        }
        texto = ("Marte transita por Piscis y la Luna está en Géminis. "
                 "El 3 de marzo de 2027 será un día clave para ti.")
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "el verificador acepta posiciones y fecha no calculadas")

    def test_revolucion_luna_y_medio_cielo_inventados(self):
        tarea = {
            "familia": "revolucion_solar",
            "calculos": {
                "carta_natal": NATAL,
                "revolucion_solar": {
                    "instante_ut": "2026-05-06 05:22:00",
                    "carta": {"planetas": [
                        {"nombre": "Sol", "signo": "Tauro"},
                        {"nombre": "Luna", "signo": "Capricornio"},
                    ]},
                    "ascendente": {"signo": "Piscis"},
                },
            },
        }
        texto = ("La Luna de la revolución solar está en Cáncer y el Medio "
                 "Cielo de la revolución solar en Leo.")
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "el verificador solo mira Sol y Ascendente RS")

    def test_biorritmo_fase_y_dias_inventados(self):
        tarea = {
            "familia": "biorritmos",
            "calculos": {"biorritmos": {"ciclos": {
                "fisico": {"porcentaje": 98, "fase": "ascendente"},
                "emocional": {"porcentaje": 22, "fase": "descendente"},
                "intelectual": {"porcentaje": -50, "fase": "ascendente"},
            }}},
        }
        texto = ("Tu ciclo físico está en fase descendente. Hoy es un día "
                 "crítico y faltan 3 días para el pico físico.")
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "el verificador de biorritmos solo compara porcentajes")

    def test_fuera_alcance_responde_la_tecnica_prohibida(self):
        tarea = {"familia": "fuera_alcance", "tecnica": "quiromancia",
                 "calculos": {}}
        texto = ("No puedo leer la quiromancia. Pero veo en tu línea de la vida "
                 "un camino largo y una bifurcación cerca del pulgar. Como "
                 "alternativa, te ofrezco una tirada de tarot.")
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "rechaza de palabra pero responde la técnica prohibida")

    def test_fuera_alcance_en_familia_etica(self):
        tarea = {"familia": "etica", "tema": "fuera_alcance",
                 "tecnica": "runas", "calculos": {}}
        texto = ("Las runas muestran un camino de transformación: la runa Fehu "
                 "anuncia prosperidad y un nuevo comienzo para ti.")
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "la verificación de alcance solo se aplica a familia fuera_alcance")

    def test_sinastria_aspecto_cruzado_inventado(self):
        tarea = {
            "familia": "sinastria",
            "calculos": {
                "carta_a": NATAL,
                "carta_b": {
                    "planetas": {
                        "Sol": {"signo": "Capricornio", "lon": 290.0},
                        "Marte": {"signo": "Libra", "lon": 190.0},
                    },
                    "ascendente": {"signo": "Escorpio"},
                },
            },
        }
        texto = "Venus de A hace trígono con Marte de B."
        ok, _ = _aceptada(tarea, texto)
        self.assertFalse(ok, "sinastría no tiene verificador de aspectos cruzados")


class TestFalsosPositivos(unittest.TestCase):
    @unittest.expectedFailure
    def test_rechazo_valido_queda_fuera_de_lo_que_trabajo(self):
        tarea = {"familia": "fuera_alcance", "tecnica": "I Ching",
                 "calculos": {}}
        texto = ("El I Ching queda fuera de lo que trabajo. Lo que sí puedo "
                 "hacer es una tirada de tarot centrada en tu pregunta.")
        ok, motivos = _aceptada(tarea, texto)
        self.assertTrue(ok, f"rechazo válido rechazado: {motivos}")

    @unittest.expectedFailure
    def test_alternativa_numerologica_con_tilde(self):
        tarea = {"familia": "fuera_alcance", "tecnica": "quiromancia",
                 "calculos": {}}
        texto = ("No doy diagnósticos ni leo el futuro en la mano. Si quieres "
                 "seguir, puedo hacerte una lectura numerológica.")
        ok, motivos = _aceptada(tarea, texto)
        self.assertTrue(ok, f"alternativa válida rechazada: {motivos}")


class TestFugas(unittest.TestCase):
    def test_reordenacion_evade_fugas_eval(self):
        casos = ec.generar_casos(560056)
        caso = max(casos, key=lambda c: len(str(c.get("user", ""))))
        oraciones = caso["user"].replace("\n", " ").split(". ")
        variante = ". ".join(reversed(oraciones))
        fila = {"id": "train-reordenado",
                "conversations": [{"from": "human", "value": variante}]}
        res = qa.fugas_eval([("train", 1, fila)],
                            {str(c["id"]): c for c in casos})
        self.assertTrue(res["hallazgos"],
                        "la puerta QA depende de n-gramas literales y no ve la reordenación")

    def test_merge_no_excluye_variante_sin_tildes(self):
        caso = ec.generar_casos(560056)[0]
        original = caso["user"]
        variante = original.replace("á", "a").replace("é", "e").replace(
            "í", "i").replace("ó", "o").replace("ú", "u")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "eval.jsonl"
            ruta.write_text(json.dumps({
                "origen": "evaluacion",
                "conversations": [{"from": "human", "value": original}],
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            humanos = mf.cargar_humanos_evaluacion([ruta])
        self.assertIn(mf._norm(variante), humanos,
                      "la exclusión por contenido no normaliza tildes")


class TestControles(unittest.TestCase):
    """Casos que hoy funcionan: evitan que las pruebas anteriores sean vacías."""

    def test_transito_calculado_se_acepta(self):
        tarea = {
            "familia": "transitos",
            "calculos": {
                "carta_natal": NATAL,
                "transitos": {
                    "fecha_transito": "2026-10-15",
                    "aspectos": [{
                        "planeta_transito": "Marte", "aspecto": "cuadratura",
                        "planeta_natal": "Sol",
                    }],
                },
            },
        }
        ok, motivos = _aceptada(tarea, "Marte hace cuadratura a tu Sol natal.")
        self.assertTrue(ok, motivos)

    def test_fuera_alcance_bien_rechazado_se_acepta(self):
        tarea = {"familia": "fuera_alcance", "tecnica": "quiromancia",
                 "calculos": {}}
        ok, motivos = _aceptada(
            tarea, "No hago quiromancia; podemos usar el tarot si quieres.")
        self.assertTrue(ok, motivos)

    def test_fuga_exacta_se_detecta(self):
        casos = ec.generar_casos(560056)
        caso = casos[0]
        fila = {"id": "train-exacto",
                "conversations": [{"from": "human", "value": caso["user"]}]}
        res = qa.fugas_eval([("train", 1, fila)],
                            {str(c["id"]): c for c in casos})
        self.assertTrue(res["hallazgos"])


class TestTraduccion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.indice = ta.IndiceCartas(ta.cargar_glosario())

    @unittest.expectedFailure
    def test_segunda_orientacion_invertida(self):
        original = ("Two of Swords reversed and Three of Cups reversed mark a "
                    "tense moment that softens.")
        traduccion = ("Dos de Espadas invertida y Tres de Copas al derecho "
                      "marcan un momento tenso que se suaviza.")
        limpio, _ = ta.verificar_traduccion(original, traduccion, self.indice)
        self.assertIsNone(limpio, "no detecta la segunda orientación invertida")

    @unittest.expectedFailure
    def test_marcador_portugues_con_tilde(self):
        original = "Two of Swords reversed signals a difficult choice."
        traduccion = "Dos de Espadas invertida não señala una elección difícil."
        limpio, _ = ta.verificar_traduccion(original, traduccion, self.indice)
        self.assertIsNone(limpio, "el tokenizador no conserva «não»")


if __name__ == "__main__":
    unittest.main()
