"""Tests de calidad_lecturas: auditoría offline con lecturas sintéticas."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import calidad_lecturas as cal


def lectura(bloque, human, gpt, ident="1", calculos=None):
    return {
        "id": ident,
        "bloque": bloque,
        "system": "Eres una tarotista profesional.",
        "human": human,
        "gpt": gpt,
        "calculos": calculos,
    }


def codigos(lectura_, kb=None):
    return {h["codigo"] for h in cal.analizar_lectura(lectura_, kb)}


HUMAN_TAROT = "Carta: El Loco (al derecho)\n\nPregunta del consultante: \"¿Cómo va mi trabajo?\""
HUMAN_ASTRO = (
    "Datos de nacimiento: 1966-11-09, 16:00, Barcelona.\n"
    "Posiciones:\n"
    "- Sol: Escorpio 16°46' (casa 7)\n"
    "- Luna: Libra 6°11' (casa 6)\n"
    "- Ascendente: Aries 9°40'\n"
)


def cuerpo_lectura_completa():
    return (
        "## Carta natal\n"
        "Tu Sol en Escorpio busca intensidad y la Luna en Libra cuida los vínculos. "
        "El Ascendente en Aries te impulsa a empezar sin esperar permiso.\n\n"
        "## Tirada de tres cartas\n"
        + ("El Loco abre un camino de aprendizaje y confianza en lo desconocido. " * 8)
        + "\n\n## Numerología\n"
        "El número siete invita a la reflexión y al estudio pausado de tus metas.\n\n"
        "## Síntesis\n"
        "Las tres técnicas señalan un momento de cambio que pide decisión y escucha.\n"
    )


def cuerpo_cruz_celta(largo=160):
    lineas = []
    for numero in range(1, 11):
        relleno = f"La posición {numero} habla de un proceso propio y distinto. "
        while len(relleno) < largo:
            relleno += f"Observa el matiz {len(relleno)} con calma. "
        lineas.append(f"## {numero}. posición {numero} — El Loco (al derecho)\n{relleno[:largo]}")
    lineas.append("## Síntesis\nLa tirada reúne los hilos en una decisión posible.")
    return "\n\n".join(lineas)


class CargaTests(unittest.TestCase):
    def test_carga_sharegpt_y_roles_alternativos(self):
        filas = [
            {"id": 7, "bloque": "tarot_1", "conversations": [
                {"from": "system", "value": "s"},
                {"from": "human", "value": "h"},
                {"from": "gpt", "value": "g"},
            ]},
            {"id": 8, "familia": "numerologia", "conversations": [
                {"role": "user", "content": "h2"},
                {"role": "assistant", "content": "g2"},
            ]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "datos.jsonl"
            ruta.write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
            lecturas = cal.cargar_lecturas(ruta)
        self.assertEqual([l["id"] for l in lecturas], ["7", "8"])
        self.assertEqual(lecturas[1]["bloque"], "numerologia")
        self.assertEqual(lecturas[1]["human"], "h2")
        self.assertEqual(lecturas[1]["gpt"], "g2")

    def test_json_invalido_falla_con_numero_de_linea(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "datos.jsonl"
            ruta.write_text("{no es json}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "línea 1"):
                cal.cargar_lecturas(ruta)

    def test_normalizar_quita_acentos_markdown_y_puntuacion(self):
        self.assertEqual(cal.normalizar("## **Qué** hermosa, carta."),
                         "que hermosa, carta")

    def test_carga_kb_real(self):
        kb = cal.cargar_kb()
        self.assertEqual(kb["signos"]["aries"]["elemento"].lower(), "fuego")
        self.assertIn("regente", kb["signos"]["aries"])


class FormaTests(unittest.TestCase):
    def test_apertura_y_cierre_formulaicos(self):
        gpt = (
            "Claro, con gusto te acompaño en esta lectura. El Loco habla de empezar "
            "con confianza y de mirar el trabajo con otra perspectiva.\n\n"
            "Estoy aquí para acompañarte."
        )
        encontrados = codigos(lectura("tarot_1", HUMAN_TAROT, gpt))
        self.assertIn("apertura_formula", encontrados)
        self.assertIn("cierre_formula", encontrados)

    def test_muletilla(self):
        gpt = "El Loco te invita a confiar. En el fondo, ya sabes qué camino elegir."
        self.assertIn("muletilla", codigos(lectura("tarot_1", HUMAN_TAROT, gpt)))

    def test_lista_donde_se_pide_prosa(self):
        gpt = (
            "El Loco abre una etapa laboral distinta y te pide escuchar tu deseo.\n"
            "- Revisa tus prioridades.\n- Habla con tu equipo.\n- Reserva tiempo."
        )
        self.assertIn("lista_en_prosa", codigos(lectura("tarot_1", HUMAN_TAROT, gpt)))

    def test_truncamiento(self):
        gpt = "El Loco abre una etapa distinta, pero el texto termina sin"
        self.assertIn("truncamiento", codigos(lectura("tarot_1", HUMAN_TAROT, gpt)))

    def test_texto_limpio_no_dispara_defectos_de_forma(self):
        gpt = (
            "El Loco aparece en tu tirada para hablarte de un comienzo laboral que "
            "todavía no tiene forma del todo. La carta sugiere que escuches tu impulso "
            "y que pongas un límite claro a lo que no te corresponde. No hay una "
            "respuesta cerrada: hay un movimiento posible que conviene probar con "
            "prudencia y con ayuda de quien conoce tu oficio."
        )
        encontrados = codigos(lectura("tarot_1", HUMAN_TAROT, gpt))
        self.assertFalse(encontrados & {
            "apertura_formula", "cierre_formula", "muletilla", "lista_en_prosa",
            "truncamiento", "repeticion_interna",
        })


class EsquemaTests(unittest.TestCase):
    def test_lectura_completa_correcta(self):
        gpt = cuerpo_lectura_completa()
        encontrados = codigos(lectura("lectura_completa", HUMAN_TAROT, gpt))
        self.assertNotIn("esquema_incumplido", encontrados)

    def test_lectura_completa_sin_secciones(self):
        gpt = "Una lectura corrida sin ninguna cabecera y sin las cuatro partes."
        self.assertIn("esquema_incumplido",
                      codigos(lectura("lectura_completa", HUMAN_TAROT, gpt)))

    def test_lectura_completa_sintesis_larga_cuenta_una_lectura(self):
        gpt = cuerpo_lectura_completa().replace(
            "Las tres técnicas señalan un momento de cambio que pide decisión y escucha.",
            "Las tres técnicas señalan un momento de cambio que pide decisión y escucha. " * 8)
        lecturas = [lectura("lectura_completa", HUMAN_TAROT, gpt, "10")]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        datos = informe["hallazgos"]["esquema_incumplido"]
        self.assertEqual(datos["total"], 1)
        self.assertGreaterEqual(datos["casos"], 1)

    def test_cruz_celta_correcta(self):
        encontrados = codigos(lectura("cruz_celta", HUMAN_TAROT, cuerpo_cruz_celta()))
        self.assertNotIn("esquema_incumplido", encontrados)

    def test_cruz_celta_seccion_demasiado_larga(self):
        gpt = cuerpo_cruz_celta(largo=310)
        self.assertIn("esquema_incumplido",
                      codigos(lectura("cruz_celta", HUMAN_TAROT, gpt)))

    def test_cruz_celta_sin_diez_secciones(self):
        gpt = "## 1. situación — El Loco (al derecho)\n" + "Texto suficiente. " * 12
        self.assertIn("esquema_incumplido",
                      codigos(lectura("cruz_celta", HUMAN_TAROT, gpt)))


class RepeticionTests(unittest.TestCase):
    def test_frase_plantilla_entre_tres_lecturas(self):
        frase = ("Recuerda que esto es una tendencia y que tu libertad pesa más "
                 "que cualquier pronóstico.")
        lecturas = [
            lectura("tarot_1", HUMAN_TAROT,
                    f"Apertura distinta número {n}. El Loco pide avanzar. {frase}", str(n))
            for n in range(3)
        ]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        self.assertEqual(informe["hallazgos"]["frase_plantilla"]["total"], 3)
        self.assertEqual(informe["plantillas_total"], 1)

    def test_apertura_repetida_entre_tres_lecturas(self):
        lecturas = [
            lectura("tarot_1", HUMAN_TAROT,
                    "Hola, gracias por compartir tu consulta. " + "Texto distinto " * n,
                    str(n))
            for n in range(1, 4)
        ]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        self.assertEqual(informe["hallazgos"]["apertura_repetida"]["total"], 3)

    def test_repeticion_interna(self):
        frase = ("Esta frase larga se repite de forma literal en el mismo texto "
                 "para probar el detector interno.")
        gpt = f"El Loco abre el camino. {frase} {frase}"
        self.assertIn("repeticion_interna",
                      codigos(lectura("tarot_pregunta", HUMAN_TAROT, gpt)))


class GeneroTests(unittest.TestCase):
    def test_genero_inconsistente(self):
        gpt = "Querido/a consultante, eres un constructor nato de tu propio camino."
        self.assertIn("genero_inconsistente",
                      codigos(lectura("numerologia", HUMAN_TAROT, gpt)))

    def test_genero_asumido_femenino(self):
        gpt = "Te sientes agotada y atrapada entre dos opciones que no te gustan."
        self.assertIn("genero_asumido", codigos(lectura("tarot_1", HUMAN_TAROT, gpt)))

    def test_no_asume_genero_con_dato_explicito(self):
        human = "Soy mujer y pregunto por mi trabajo.\n" + HUMAN_TAROT
        gpt = "Te sientes agotada y atrapada entre dos opciones que no te gustan."
        self.assertNotIn("genero_asumido", codigos(lectura("tarot_1", human, gpt)))


class PromptTests(unittest.TestCase):
    def test_ficha_tecnica_colada(self):
        gpt = "Datos de nacimiento: 22 de enero de 1950, 15:00, Panamá.\n" + \
              "Tu Sol en Escorpio y tu Luna en Libra buscan equilibrio."
        self.assertIn("ficha_tecnica", codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))

    def test_placeholder_de_pais_vacio(self):
        human = HUMAN_ASTRO.replace("Barcelona.", "Barcelona ().")
        gpt = "Tu Sol en Escorpio y tu Luna en Libra buscan equilibrio."
        self.assertIn("placeholder_prompt",
                      codigos(lectura("astro_natal", human, gpt)))

    def test_pregunta_de_futuro_sin_transitos(self):
        human = HUMAN_ASTRO + 'Pregunta del consultante: "¿Qué dice mi carta sobre mi próximo año?"'
        gpt = "Tu Sol en Escorpio y tu Luna en Libra buscan equilibrio este año."
        self.assertIn("pregunta_sin_datos",
                      codigos(lectura("astro_natal", human, gpt)))

    def test_pregunta_de_futuro_con_transitos_no_se_marca(self):
        human = ("Datos de nacimiento: 1966-11-09.\n"
                 "- Sol: Escorpio 16°46' (casa 7)\n"
                 "- Luna: Libra 6°11' (casa 6)\n"
                 "- Ascendente: Aries 9°40'\n"
                 "Tránsitos de Saturno para 2026.\n"
                 'Pregunta del consultante: "¿Qué dice mi próximo año?"')
        gpt = "Tu Sol en Escorpio y tu Luna en Libra reciben el tránsito de Saturno."
        self.assertNotIn("pregunta_sin_datos",
                         codigos(lectura("astro_natal", human, gpt)))


class AstroTests(unittest.TestCase):
    def test_signo_contradicho(self):
        gpt = ("Tu Sol en Leo necesita reconocimiento, mientras la Luna en Libra "
               "busca acuerdos y el Ascendente en Aries te impulsa a actuar.")
        self.assertIn("astro_signo_contradicho",
                      codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))

    def test_lista_coordinada_no_se_confunde_con_contradiccion(self):
        gpt = ("Tu Sol en Escorpio y la Luna en Libra forman un equilibrio, "
               "mientras Mercurio y Venus en Sagitario avivan tu curiosity.")
        self.assertNotIn("astro_signo_contradicho",
                         codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))

    def test_ascendente_contradicho(self):
        gpt = ("Tu Sol en Escorpio y tu Luna en Libra. Júpiter en Acuario en el "
               "ascendente te da una mirada amplia.")
        self.assertIn("astro_ascendente_contradicho",
                      codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))

    def test_casa_contradicha(self):
        gpt = ("Tu Sol en Escorpio está en la casa 3, aunque la Luna en Libra "
               "modera esa intensidad y el Ascendente en Aries empuja.")
        self.assertIn("astro_casa_contradicha",
                      codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))

    def test_elemento_contradicho_contra_kb(self):
        kb = {"signos": {"aries": {"elemento": "fuego"}}}
        gpt = "Aries es un signo de agua, aunque tu Sol en Escorpio matice esa idea."
        self.assertIn("elemento_contradicho",
                      codigos(lectura("astro_natal", HUMAN_ASTRO, gpt), kb))

    def test_referencia_ausente_en_astro(self):
        gpt = "Esta lectura habla del destino en general sin nombrar los puntos clave."
        self.assertIn("referencia_ausente",
                      codigos(lectura("astro_natal", HUMAN_ASTRO, gpt)))


class InformeTests(unittest.TestCase):
    def test_longitud_atipica_por_familia(self):
        lecturas = [
            lectura("tarot_1", HUMAN_TAROT, "Texto normal. " * 100, "1"),
            lectura("tarot_1", HUMAN_TAROT, "Texto normal. " * 100, "2"),
            lectura("tarot_1", HUMAN_TAROT, "Muy corto.", "3"),
        ]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        ejemplo = informe["hallazgos"]["longitud_atipica"]["ejemplos"][0]
        self.assertEqual(ejemplo["id"], "3")

    def test_no_excluye_ninguna_lectura(self):
        lecturas = [
            lectura("tarot_1", HUMAN_TAROT, "Texto limpio y suficiente. " * 30, "1"),
            lectura("tarot_2", HUMAN_TAROT, "Otro texto distinto. " * 30, "2"),
        ]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        self.assertEqual(set(informe["detalle"]), {"1", "2"})
        self.assertEqual(informe["lecturas"], 2)
        self.assertEqual(sum(informe["por_bloque"].values()), 2)

    def test_muestra_reproducible_y_estratificada(self):
        lecturas = []
        for bloque in ("tarot_1", "tarot_2"):
            for n in range(20):
                lecturas.append(lectura(bloque, HUMAN_TAROT, f"Texto {bloque} {n}.", f"{bloque}-{n}"))
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.jsonl"
            b = Path(tmp) / "b.jsonl"
            self.assertEqual(cal.exportar_muestra(lecturas, a, 12, 99), 24)
            self.assertEqual(cal.exportar_muestra(lecturas, b, 12, 99), 24)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            filas = [json.loads(l) for l in a.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(filas), 24)
        self.assertEqual(sum(f["bloque"] == "tarot_1" for f in filas), 12)
        self.assertEqual(sum(f["bloque"] == "tarot_2" for f in filas), 12)

    def test_markdown_se_genera(self):
        lecturas = [lectura("tarot_1", HUMAN_TAROT, "Claro, te acompaño. El Loco avanza.", "1")]
        informe = cal.analizar_lecturas(lecturas, kb={"signos": {}})
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "informe.md"
            cal.escribir_markdown(informe, ruta)
            texto = ruta.read_text(encoding="utf-8")
        self.assertIn("# Informe de calidad", texto)
        self.assertIn("apertura_formula", texto)


if __name__ == "__main__":
    unittest.main()
