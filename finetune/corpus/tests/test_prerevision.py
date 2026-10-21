import os
import sys
import unicodedata
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import prerevision


def ficha(entidad_id="tarot-mayor-19", nivel="afirmaciones", **extra):
    registro = {
        "id": extra.pop("id", "ficha-1"),
        "nivel": nivel,
        "entidad_id": entidad_id,
        "faceta": extra.pop("faceta", "significado_general"),
        "origen": extra.pop("origen", "web"),
    }
    registro.update(extra)
    return registro


class BanderasBasicasTests(unittest.TestCase):
    def test_ficha_limpia_sin_banderas(self):
        texto = "La intuición se afina cuando escuchas tu voz interior."
        resultado = prerevision.analizar_registro(ficha(), texto)
        self.assertEqual([], resultado["banderas"])
        self.assertEqual(0, resultado["puntuacion"])

    def test_texto_vacio(self):
        for texto in ("", "   ", None):
            self.assertIsNotNone(prerevision.bandera_sin_texto(texto))
        resultado = prerevision.analizar_registro(ficha(), None)
        codigos = [bandera["codigo"] for bandera in resultado["banderas"]]
        self.assertEqual(["sin_texto"], codigos)
        self.assertEqual(10, resultado["puntuacion"])

    def test_texto_corto_por_nivel(self):
        self.assertIsNotNone(prerevision.bandera_texto_corto("Corto.", "web"))
        self.assertIsNone(
            prerevision.bandera_texto_corto(
                "Una afirmación breve pero completa para el nivel de afirmaciones.",
                "afirmaciones",
            )
        )
        self.assertIsNotNone(prerevision.bandera_texto_corto("Demasiado breve.", "afirmaciones"))

    def test_texto_corto_no_se_aplica_sin_texto(self):
        self.assertIsNone(prerevision.bandera_texto_corto("", "web"))


class RuidoYFormatoTests(unittest.TestCase):
    def test_ruido_navegacion(self):
        texto = (
            "Gracias por leer la guía completa.\n"
            "Inicio\n"
            "Contacto\n"
            "Aviso legal\n"
            "Política de privacidad\n"
            "© 2024 Todos los derechos reservados"
        )
        self.assertIsNotNone(prerevision.bandera_ruido_navegacion(texto))

    def test_prosa_no_es_ruido(self):
        texto = (
            "La carta del Loco representa el inicio de un camino.\n"
            "Su energía invita a confiar en lo desconocido.\n"
            "En una tirada indica un salto hacia adelante."
        )
        self.assertIsNone(prerevision.bandera_ruido_navegacion(texto))

    def test_ruido_comercial(self):
        self.assertIsNotNone(prerevision.bandera_ruido_comercial("Añadir al carrito"))
        self.assertIsNotNone(
            prerevision.bandera_ruido_comercial("Suscríbete y compra el curso completo.")
        )
        self.assertIsNone(
            prerevision.bandera_ruido_comercial(
                "La carta habla de compasión y de una compra que llega en buen momento."
            )
        )

    def test_mojibake(self):
        self.assertIsNotNone(prerevision.bandera_mojibake("CafÃ© y seÃ±al"))
        self.assertIsNone(prerevision.bandera_mojibake("Café y señal"))

    def test_no_espanol(self):
        self.assertIsNotNone(
            prerevision.bandera_no_espanol(
                "The card represents a journey through the unknown and the light, "
                "and it invites every reader to trust the process of change."
            )
        )
        self.assertIsNone(
            prerevision.bandera_no_espanol(
                "La carta representa un viaje hacia lo desconocido y la luz."
            )
        )
        self.assertIsNone(prerevision.bandera_no_espanol("Muy breve."))

    def test_portugues(self):
        texto = (
            "A colocação da Lua na terceira Casa muitas vezes indica a falta de "
            "capacidade de adaptação, e não é fácil mudar essa tendência."
        )
        self.assertIsNotNone(prerevision.bandera_no_espanol(texto))

    def test_espanol_con_pocas_palabras_funcionales(self):
        texto = "Nada se aniquila realmente; solo cambia la forma accidental."
        self.assertIsNone(prerevision.bandera_no_espanol(texto))
        texto = "Lo negativo puede volverse positivo si se hacen los cambios necesarios."
        self.assertIsNone(prerevision.bandera_no_espanol(texto))


class EntidadYPromesasTests(unittest.TestCase):
    def test_menciona_otra_carta(self):
        registro = ficha(entidad_id="tarot-bastos-04")
        self.assertIsNotNone(
            prerevision.bandera_otra_entidad(registro, "La Reina de Copas trae calma.")
        )
        self.assertIsNone(
            prerevision.bandera_otra_entidad(registro, "El Cuatro de Bastos celebra un logro.")
        )

    def test_combinacion_no_se_revisa_por_carta(self):
        registro = ficha(entidad_id="tarot-bastos-04|tarot-copas-02", faceta="combinacion")
        self.assertIsNone(
            prerevision.bandera_otra_entidad(registro, "La Reina de Copas trae calma.")
        )

    def test_otro_signo(self):
        registro = ficha(entidad_id="aries|signo", nivel="afirmaciones")
        self.assertIsNotNone(
            prerevision.bandera_otra_entidad(registro, "Los nacidos en Leo brillan con fuerza.")
        )
        self.assertIsNone(
            prerevision.bandera_otra_entidad(
                registro, "Aries comparte el fuego con Leo, pero con otro ritmo."
            )
        )

    def test_numero_equivocado(self):
        registro = ficha(entidad_id="8|camino_de_vida", nivel="afirmaciones")
        self.assertIsNotNone(
            prerevision.bandera_otra_entidad(registro, "Tu camino de vida es el 7.")
        )
        self.assertIsNone(
            prerevision.bandera_otra_entidad(registro, "Tu camino de vida es el 8.")
        )

    def test_promesa_vedada(self):
        self.assertIsNotNone(prerevision.bandera_promesa_vedada("Vas a curar tu enfermedad."))
        self.assertIsNotNone(
            prerevision.bandera_promesa_vedada("Te garantizo que encontrarás el amor.")
        )
        self.assertIsNone(
            prerevision.bandera_promesa_vedada(
                "La carta invita a cuidar la salud y a pedir ayuda profesional."
            )
        )


class ContradiccionKBTests(unittest.TestCase):
    def setUp(self):
        self.elementos = prerevision.cargar_elementos()

    def test_elemento_contrario_al_palo(self):
        registro = ficha(entidad_id="tarot-bastos-04")
        motivo = prerevision.bandera_contradiccion_kb(
            registro,
            "El Cuatro de Bastos se asocia con el elemento Agua.",
            self.elementos,
        )
        self.assertIsNotNone(motivo)
        self.assertIn("agua", motivo)

    def test_otro_palo_no_es_contradiccion(self):
        registro = ficha(entidad_id="tarot-bastos-04")
        self.assertIsNone(
            prerevision.bandera_contradiccion_kb(
                registro,
                "El palo de Copas se asocia al elemento Agua.",
                self.elementos,
            )
        )

    def test_mencion_metaforica_no_es_contradiccion(self):
        registro = ficha(entidad_id="tarot-bastos-04")
        self.assertIsNone(
            prerevision.bandera_contradiccion_kb(
                registro,
                "El apego material proviene de la tierra.",
                self.elementos,
            )
        )

    def test_arcano_mayor_no_tiene_palo(self):
        registro = ficha(entidad_id="tarot-mayor-19")
        self.assertIsNone(
            prerevision.bandera_contradiccion_kb(
                registro,
                "La Luna se asocia con el elemento Agua.",
                self.elementos,
            )
        )


class LecturasYDuplicadosTests(unittest.TestCase):
    def test_carta_ajena_en_lectura_espanola(self):
        registro = ficha(
            entidad_id="",
            nivel="lecturas",
            idioma="es",
            sistema="tarot",
            cartas=["El Loco"],
        )
        motivo = prerevision.bandera_lectura_invalida(
            registro, "También aparece la Reina de Copas en la tirada."
        )
        self.assertIsNotNone(motivo)
        self.assertIn("Reina de Copas", motivo)

    def test_lectura_en_ingles_no_se_reconstruye(self):
        registro = ficha(
            entidad_id="",
            nivel="lecturas",
            idioma="en",
            sistema="tarot",
            cartas=["The Fool"],
        )
        self.assertIsNone(
            prerevision.bandera_lectura_invalida(registro, "The Queen of Cups appears.")
        )

    def test_jaccard_y_duplicados(self):
        registros = [
            ficha(id="a", entidad_id="1|camino_de_vida"),
            ficha(id="b", entidad_id="1|camino_de_vida"),
            ficha(id="c", entidad_id="1|camino_de_vida"),
        ]
        textos = {
            "a": "El Uno se asocia con el Sol y el elemento Fuego.",
            "b": "El Uno se asocia con el Sol y el elemento Fuego.",
            "c": "La energía del Uno abre un camino propio y luminoso.",
        }
        duplicados = prerevision.indice_duplicados(registros, textos)
        self.assertEqual(1.0, duplicados["a"][0])
        self.assertEqual("b", duplicados["a"][1])
        self.assertNotIn("c", duplicados)

    def test_textos_vacios_no_son_duplicados(self):
        registros = [ficha(id="a"), ficha(id="b")]
        self.assertEqual({}, prerevision.indice_duplicados(registros, {"a": "", "b": ""}))


class UnicodeYEntradasVaciasTests(unittest.TestCase):
    def test_nfd_equivalente_a_nfc(self):
        nfc = "Canción de amor y claridad"
        nfd = unicodedata.normalize("NFD", nfc)
        self.assertIsNone(prerevision.bandera_mojibake(nfd))
        self.assertEqual(1.0, prerevision.similitud_jaccard(nfc, nfd))

    def test_entrada_vacia(self):
        self.assertEqual([], prerevision.analizar([], {}))

    def test_campos_ausentes_no_revientan(self):
        resultado = prerevision.analizar_registro({}, "")
        self.assertEqual("sin_texto", resultado["banderas"][0]["codigo"])
        texto = "La carta habla de un camino que se abre con fuerza y claridad para ti. " * 3
        codigos = [
            bandera["codigo"]
            for bandera in prerevision.analizar_registro({}, texto)["banderas"]
        ]
        self.assertNotIn("sin_texto", codigos)


class ConsensoPrerevisionTests(unittest.TestCase):
    def _celda(self):
        return ficha(
            entidad_id="tarot-copas-02",
            nivel="consenso",
            faceta="significado_general",
            origen="consenso",
        )

    def test_umbral_texto_consenso(self):
        self.assertEqual(40, prerevision.UMBRAL_TEXTO["consenso"])

    def test_texto_corto_consenso(self):
        self.assertIsNotNone(prerevision.bandera_texto_corto("Casi vacía.", "consenso"))
        self.assertIsNone(
            prerevision.bandera_texto_corto(
                "Afirmaciones mayoritarias:\n· La copa ofrece calma cuando uno la sostiene en calma.",
                "consenso",
            )
        )

    def test_otra_carta_en_celda_consenso(self):
        texto = (
            "Afirmaciones mayoritarias:\n"
            "· La Reina de Copas aparece como figura de contraste en esta lectura.\n"
            "Discrepancias:\n"
            "1) A: La dua ofrece ternura [fuente-a] — B: La dua guarda secretos [fuente-b]"
        )
        resultado = prerevision.analizar_registro(self._celda(), texto)
        codigos = [bandera["codigo"] for bandera in resultado["banderas"]]
        self.assertIn("otra_carta", codigos)

    def test_promesa_vedada_en_celda_consenso(self):
        texto = (
            "Aportaciones de una sola fuente:\n"
            "· Te garantizo que encontrarás el amor verdadero en tres meses. (fuente: x)"
        )
        resultado = prerevision.analizar_registro(self._celda(), texto)
        codigos = [bandera["codigo"] for bandera in resultado["banderas"]]
        self.assertIn("promesa_vedada", codigos)

    def test_celda_consenso_limpi_sin_banderas(self):
        texto = (
            "Afirmaciones mayoritarias:\n"
            "· La dua invita a acoger la emoción sin drama (3 fuentes; fuentes: a, b, c)\n"
            "Discrepancias:\n"
            "1) A: La dua guarda secretos [fuente-a] — B: La dua canta verdades [fuente-b]\n"
            "Aportaciones de una sola fuente:\n"
            "· La dua regala descanso al corazón cansado. (fuente: d; tradición: Marsella)"
        )
        resultado = prerevision.analizar_registro(self._celda(), texto)
        self.assertEqual([], resultado["banderas"])


if __name__ == "__main__":
    unittest.main()
