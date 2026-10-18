"""Tests de audit_dataset: criterios de puntuación de pares ShareGPT (offline, fixtures inline)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import audit_dataset as aud


def fila(prompt, respuesta, **extra):
    d = {
        "conversations": [
            {"from": "system", "value": "Eres una experta en adivinación."},
            {"from": "human", "value": prompt},
            {"from": "gpt", "value": respuesta},
        ]
    }
    d.update(extra)
    return d


RESPUESTA_TAROT = (
    "En esta tirada, El Loco te habla de un comienzo inesperado en tu vida laboral. "
    "Tu carta sugiere que te atrevas a dar un salto aunque el camino no esté trazado; "
    "el tarot indica que la incertidumbre es parte del proceso y que confíes en tu "
    "intuición cuando sientas que algo te llama con fuerza. Los arcanos que acompañan "
    "a esta carta refuerzan la idea de soltar el control y abrirte a lo nuevo, porque "
    "tu momento presente pide movimiento y valentía, no una prudencia excesiva que te "
    "deje paralizado frente a una oportunidad que el destino acaba de poner delante. "
    "Mira también cómo la energía del arcano se combina con tu pregunta sobre el trabajo "
    "y recuerda que cada consulta es un mapa, no una sentencia: tú decides el rumbo."
)

RESPUESTA_ENCICLOPEDICA = (
    "La carta del Ermitaño representa la introspección y la búsqueda interior dentro de "
    "la tradición del tarot de Marsella. Su figura, un anciano con una lámpara en la cima "
    "de una montaña, simboliza la sabiduría que se alcanza con la soledad y la reflexión "
    "pausada. En los mazos tradicionales este arcano se asocia con el número nueve y con "
    "la letra he del alfabeto hebreo, según la interpretación cabalística clásica, y su "
    "presencia en una tirada se lee como una invitación a mirar hacia dentro."
)


class CriteriosPuntuacion(unittest.TestCase):
    def test_par_bueno_de_tarot_aceptado(self):
        score, motivos, tipo = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?", RESPUESTA_TAROT))
        self.assertEqual(motivos, [])
        self.assertEqual(tipo, "lectura")
        self.assertGreaterEqual(score, 0.6)

    def test_prompt_generico_penaliza(self):
        score, motivos, _ = aud.puntuar(
            fila("Sección 3: Historia de la imprenta",
                 "La imprenta de tipos móviles se difundió por Europa durante el siglo XV y "
                 "transformó la producción de libros, la alfabetización y el comercio de las "
                 "ideas en todo el continente de forma irreversible durante varias décadas."))
        self.assertIn("prompt_generico", motivos)
        self.assertLess(score, 0.6)

    def test_tema_de_una_palabra_sin_dominio(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué significa Televisión?",
                 "La televisión es un sistema de transmisión de imágenes y sonido que se "
                 "popularizó durante el siglo XX y cambió la forma de informarse de la gente."))
        self.assertIn("prompt_generico", motivos)

    def test_residuo_wiki_penaliza(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 RESPUESTA_TAROT + " &action=edit&section=5 cite_note-1 [1](https://es.wikipedia.org/x)"))
        self.assertIn("residuos", motivos)

    def test_residuo_javascript_penaliza(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 RESPUESTA_TAROT + " Please enable javascript to continue. Suscríbete a nuestro boletín."))
        self.assertIn("residuos", motivos)

    def test_sin_dominio_penaliza(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me cuentas de la cocina italiana?",
                 "La cocina italiana se basa en pasta, tomate y aceite de oliva, y es muy popular en todo el mundo."))
        self.assertIn("dominio", motivos)

    def test_terminos_debiles_solos_no_cuentan(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dices del sol y la luna?",
                 "El sol y la luna marcan el ritmo del día y de la noche, y la gente mira el cielo "
                 "para orientarse desde siempre; la casa y la mano también son cosas cotidianas."))
        self.assertIn("dominio", motivos)

    def test_espanol_con_muchos_no_no_penaliza_idioma(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 "No te digo que no porque no sea no; no es que no puedas, sino que no conviene "
                 "decir que sí cuando el corazón dice que no, y nadie puede imponerte un no cuando "
                 "tu intuición te grita que no es el momento, así que no temas decir que no."))
        self.assertNotIn("idioma", motivos)

    def test_mezcla_ingles_penaliza_idioma(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 "The Loco card tells you about a new beginning in your work life. This card "
                 "suggests that you dare to take a leap even when the path is not traced, and "
                 "they say that uncertainty is part of the process and you should trust your gut."))
        self.assertIn("idioma", motivos)

    def test_longitud_corta_penaliza(self):
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco?",
                 "El Loco te habla de un comienzo inesperado en tu camino laboral y personal."))
        self.assertIn("longitud", motivos)

    def test_repeticion_interna_penaliza(self):
        trozo = "el tarot indica que la incertidumbre es parte del proceso"
        _, motivos, _ = aud.puntuar(
            fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 (trozo + " ") * 4 + "y tú decides el rumbo de tu consulta con calma y criterio propio."))
        self.assertIn("repeticion", motivos)

    def test_tipo_enciclopedico(self):
        _, _, tipo = aud.puntuar(
            fila("¿Qué representa el Ermitaño en el tarot?", RESPUESTA_ENCICLOPEDICA))
        self.assertEqual(tipo, "enciclopedico")

    def test_sintetica_con_bloque_es_lectura(self):
        _, _, tipo = aud.puntuar(
            fila("Tirada de una carta: El Loco invertida en el trabajo.",
                 RESPUESTA_TAROT, bloque="tarot_1"))
        self.assertEqual(tipo, "lectura")


class Duplicados(unittest.TestCase):
    def test_duplicado_exacto(self):
        f1 = fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?", RESPUESTA_TAROT)
        f2 = fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?", RESPUESTA_TAROT)
        res = aud.auditar_pares([f1, f2])
        self.assertNotIn("duplicado", res[0]["motivos"])
        self.assertIn("duplicado", res[1]["motivos"])
        self.assertFalse(res[1]["aceptado"])

    def test_duplicado_casi_exacto(self):
        f1 = fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?", RESPUESTA_TAROT)
        f2 = fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?",
                 RESPUESTA_TAROT.replace("valentía", "coraje"))
        res = aud.auditar_pares([f1, f2])
        self.assertIn("duplicado", res[1]["motivos"])
        self.assertFalse(res[1]["aceptado"])

    def test_pares_distintos_no_se_marcan_como_duplicados(self):
        f1 = fila("¿Qué me dice El Loco en mi tirada sobre el trabajo?", RESPUESTA_TAROT)
        f2 = fila("¿Qué representa el Ermitaño en el tarot?", RESPUESTA_ENCICLOPEDICA)
        res = aud.auditar_pares([f1, f2])
        self.assertNotIn("duplicado", res[0]["motivos"])
        self.assertNotIn("duplicado", res[1]["motivos"])


if __name__ == "__main__":
    unittest.main()
