"""Tests del informe de cobertura del dataset de entrenamiento (track T15)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cobertura_dataset


def _fila(*mensajes):
    return json.dumps({"conversations": list(mensajes)}, ensure_ascii=False)


def _escribir(directorio, nombre, lineas):
    ruta = os.path.join(directorio, nombre)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas) + "\n")
    return ruta


class LectorShareGPT(unittest.TestCase):
    def test_lee_un_par_valido(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "a.jsonl", [
                _fila({"from": "system", "value": "Eres una tarotista."},
                      {"from": "human", "value": "¿Qué significa el Loco?"},
                      {"from": "gpt", "value": "El Loco habla de nuevos comienzos."}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            pregunta, respuesta = pares[0]
            self.assertIn("Loco", pregunta)
            self.assertIn("comienzos", respuesta)
            self.assertEqual(stats["pares"], 1)
            self.assertEqual(stats["lineas_invalidas"], 0)
            self.assertEqual(stats["sin_gpt"], 0)

    def test_lineas_vacias_y_json_invalido_se_cuentan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "b.jsonl", [
                "",
                "{no es json",
                '{"sin_conversations": 1}',
                _fila({"from": "human", "value": "hola"},
                      {"from": "gpt", "value": "adios"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            self.assertEqual(stats["lineas_invalidas"], 3)
            self.assertEqual(stats["sin_gpt"], 0)

    def test_filas_sin_gpt_se_cuentan_aparte(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "c.jsonl", [
                _fila({"from": "system", "value": "s"},
                      {"from": "human", "value": "h"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(pares, [])
            self.assertEqual(stats["sin_gpt"], 1)
            self.assertEqual(stats["lineas_invalidas"], 0)

    def test_sin_human_da_pregunta_vacia(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "d.jsonl", [
                _fila({"from": "gpt", "value": "solo respuesta"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(len(pares), 1)
            self.assertEqual(pares[0][0], "")
            self.assertEqual(stats["pares"], 1)

    def test_varios_ficheros_se_acumulan_en_orden(self):
        with tempfile.TemporaryDirectory() as tmp:
            r1 = _escribir(tmp, "1.jsonl", [
                _fila({"from": "human", "value": "uno"},
                      {"from": "gpt", "value": "respuesta uno"}),
            ])
            r2 = _escribir(tmp, "2.jsonl", [
                _fila({"from": "human", "value": "dos"},
                      {"from": "gpt", "value": "respuesta dos"}),
            ])
            pares, stats = cobertura_dataset.leer_pares([r1, r2])
            self.assertEqual(stats["pares"], 2)
            self.assertEqual(pares[0][1], "respuesta uno")
            self.assertEqual(pares[1][1], "respuesta dos")

    def test_varios_mensajes_gpt_se_concatenan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, "e.jsonl", [
                _fila({"from": "human", "value": "h"},
                      {"from": "gpt", "value": "parte1"},
                      {"from": "gpt", "value": "parte2"}),
            ])
            pares, _ = cobertura_dataset.leer_pares([ruta])
            self.assertEqual(pares[0][1], "parte1 parte2")


class ContadorCartas(unittest.TestCase):
    def _contar(self, pares):
        contadores = {}
        cobertura_dataset.contar_cartas(pares, contadores)
        return contadores

    def test_loco_invertido_en_respuesta(self):
        cont = self._contar([("otras cosas", "El Loco invertido anuncia un cambio.")])
        c = cont["tarot:tarot-mayor-01"]
        self.assertEqual(c["etiqueta"], "El Loco")
        self.assertEqual(c["familia"], "tarot")
        self.assertEqual(c["pares_respuesta"], 1)
        self.assertEqual(c["pares_pregunta"], 0)
        self.assertEqual(c["solo_en_respuesta"], 1)
        self.assertEqual(c["invertidas"], 1)

    def test_menores_de_tarot(self):
        cont = self._contar([("", "veo el tres de copas, el as de oros y la sota de espadas")])
        self.assertEqual(cont["tarot:tarot-copas-03"]["pares_respuesta"], 1)
        self.assertEqual(cont["tarot:tarot-oros-01"]["pares_respuesta"], 1)
        self.assertEqual(cont["tarot:tarot-espadas-11"]["pares_respuesta"], 1)
        self.assertEqual(cont["tarot:tarot-copas-03"]["invertidas"], 0)

    def test_repetida_en_el_mismo_par_cuenta_una_vez(self):
        cont = self._contar([("", "el dos de bastos y de nuevo el dos de bastos")])
        self.assertEqual(cont["tarot:tarot-bastos-02"]["pares_respuesta"], 1)

    def test_negativo_loco_del_pueblo_no_es_carta(self):
        cont = self._contar([("", "el loco del pueblo cruzó corriendo la plaza")])
        self.assertNotIn("tarot:tarot-mayor-01", cont)

    def test_baraja_espanola_en_su_familia(self):
        cont = self._contar([("¿el tres de bastos?", "salió el tres de bastos")])
        espanola = cont["espanol:naipe-bastos-03"]
        self.assertEqual(espanola["familia"], "espanola")
        self.assertEqual(espanola["pares_respuesta"], 1)
        self.assertEqual(espanola["pares_pregunta"], 1)
        self.assertEqual(espanola["solo_en_respuesta"], 0)

    def test_solo_en_pregunta(self):
        cont = self._contar([("¿Qué significa la reina de copas?", "hablo de otra cosa")])
        c = cont["tarot:tarot-copas-13"]
        self.assertEqual(c["pares_respuesta"], 0)
        self.assertEqual(c["pares_pregunta"], 1)
        self.assertEqual(c["solo_en_respuesta"], 0)


class ContadorAstrologia(unittest.TestCase):
    def _contar(self, pares):
        contadores = {}
        cobertura_dataset.contar_astrologia(pares, contadores)
        return contadores

    def test_signos_directos(self):
        cont = self._contar([("", "Aries y Piscis se llevan bien; Tauro tampoco")])
        self.assertEqual(cont["signo:aries"]["pares_respuesta"], 1)
        self.assertEqual(cont["signo:piscis"]["pares_respuesta"], 1)
        self.assertEqual(cont["signo:tauro"]["pares_respuesta"], 1)
        self.assertEqual(cont["signo:aries"]["familia"], "signo")

    def test_leo_nombre_propio_no_cuenta(self):
        cont = self._contar([("", "Leo Messi marcó dos goles")])
        self.assertNotIn("signo:leo", cont)

    def test_leo_con_contexto_astrologico(self):
        cont = self._contar([
            ("", "Tu signo es Leo"),
            ("", "Sol en Leo te favorece"),
            ("", "tienes el ascendente en Leo"),
        ])
        self.assertEqual(cont["signo:leo"]["pares_respuesta"], 3)
        self.assertEqual(cont["signo:leo"]["con_contexto_astrologico"], 3)

    def test_cancer_se_acepta_sin_contexto(self):
        # La exigencia del track es solo para Leo; cáncer (enfermedad) se
        # acepta como límite conocido y se documenta en el informe.
        cont = self._contar([("", "los síntomas del cáncer se estudian pronto")])
        self.assertEqual(cont["signo:cancer"]["pares_respuesta"], 1)

    def test_cancer_signo_con_contexto(self):
        cont = self._contar([("", "tu signo solar es Cáncer")])
        self.assertEqual(cont["signo:cancer"]["pares_respuesta"], 1)

    def test_escorpio_con_o_sin_n(self):
        cont = self._contar([
            ("", "Escorpio intensidad"),
            ("", "Escorpión cambia"),
        ])
        self.assertEqual(cont["signo:escorpio"]["pares_respuesta"], 2)
        self.assertEqual(cont["signo:escorpio"]["etiqueta"], "Escorpio")

    def test_planetas_con_tildes(self):
        cont = self._contar([("", "Mercurio retrógrado, Júpiter y Venus brillan")])
        self.assertEqual(cont["planeta:mercurio"]["pares_respuesta"], 1)
        self.assertEqual(cont["planeta:jupiter"]["pares_respuesta"], 1)
        self.assertEqual(cont["planeta:venus"]["pares_respuesta"], 1)
        self.assertEqual(cont["planeta:mercurio"]["familia"], "planeta")

    def test_casas_varias_formas(self):
        cont = self._contar([
            ("", "la casa 7 rige la pareja"),
            ("", "casa VII de tu mapa"),
            ("", "la séptima casa marca los vínculos"),
        ])
        self.assertEqual(cont["casa:07"]["pares_respuesta"], 3)
        self.assertEqual(cont["casa:07"]["etiqueta"], "Casa 7")

    def test_casa_once_formas_en_el_mismo_par(self):
        cont = self._contar([("", "la casa XI, la undécima casa y casa 11")])
        self.assertEqual(cont["casa:11"]["pares_respuesta"], 1)

    def test_casa_como_vivienda_no_cuenta(self):
        cont = self._contar([("", "fui a la casa de la playa y vi la casa nueva")])
        self.assertFalse(any(k.startswith("casa:") for k in cont))


class ContadorNumerologia(unittest.TestCase):
    def _contar(self, pares):
        contadores = {}
        cobertura_dataset.contar_numerologia(pares, contadores)
        return contadores

    def test_camino_de_vida(self):
        cont = self._contar([("", "tu camino de vida es 7")])
        self.assertEqual(cont["numero:07"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:07"]["etiqueta"], "Número 7")
        self.assertEqual(cont["numero:07"]["familia"], "numerologia")

    def test_numero_maestro(self):
        cont = self._contar([
            ("", "el número 11 se repite"),
            ("", "tu número es 22"),
            ("", "el 33 es maestro"),
        ])
        self.assertEqual(cont["numero:11"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:22"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:33"]["pares_respuesta"], 1)

    def test_ano_personal_y_reducido(self):
        cont = self._contar([
            ("", "el año personal 3 trae cambios"),
            ("", "tu número reducido es 9"),
            ("", "la expresión 5 te define"),
        ])
        self.assertEqual(cont["numero:03"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:09"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:05"]["pares_respuesta"], 1)

    def test_numero_a_secas_no_cuenta(self):
        cont = self._contar([("", "me dio 3 cartas y salieron 2 espadas")])
        self.assertFalse(any(k.startswith("numero:") for k in cont))

    def test_diez_no_es_numero_numerologico(self):
        # Solo 1-9 y maestros 11, 22, 33; «camino de vida 10» no se cuenta.
        cont = self._contar([("", "tu camino de vida 10 no existe")])
        self.assertFalse(any(k.startswith("numero:") for k in cont))

    def test_una_vez_por_par_ambito(self):
        cont = self._contar([("", "camino de vida 7 y año personal 3")])
        self.assertEqual(cont["numero:07"]["pares_respuesta"], 1)
        self.assertEqual(cont["numero:03"]["pares_respuesta"], 1)


class Informe(unittest.TestCase):
    def _contadores(self):
        pares = [
            ("¿me lees el tarot?", "sale la carta El Loco; invertida sale la carta Muerte"),
            ("casa 7", "tu casa VII y el ascendente en Leo"),
            ("", "camino de vida 7"),
        ]
        cont = {}
        cobertura_dataset.contar_cartas(pares, cont)
        cobertura_dataset.contar_astrologia(pares, cont)
        cobertura_dataset.contar_numerologia(pares, cont)
        return cont, len(pares)

    def test_resumen_json(self):
        cont, n = self._contadores()
        resumen = cobertura_dataset.construir_resumen(cont, n,
                                                     stats={"pares": n,
                                                            "lineas_invalidas": 0,
                                                            "sin_gpt": 0})
        self.assertEqual(resumen["totales"]["pares_analizados"], n)
        self.assertIn("tarot:tarot-mayor-01", resumen["entidades"])
        e = resumen["entidades"]["signo:leo"]
        self.assertEqual(e["pares_respuesta"], 1)
        self.assertEqual(e["con_contexto_astrologico"], 1)
        self.assertEqual(resumen["minimo"], 20)

    def test_informe_markdown(self):
        cont, n = self._contadores()
        md = cobertura_dataset.construir_informe_md(
            cont, n, 20, stats={"pares": n, "lineas_invalidas": 0,
                                "sin_gpt": 0})
        self.assertIn("# Informe de cobertura del dataset", md)
        self.assertIn("## Pares analizados", md)
        self.assertIn("## Entidades con menos de 20 pares", md)
        self.assertIn("## Las 10 entidades más representadas", md)
        self.assertIn("El Loco", md)
        # Porcentaje de sobre-representación presente
        self.assertIn("%", md)

    def test_sobre_representadas_orden_y_porcentaje(self):
        cont = {}
        pares = [("", "sale la carta El Loco") for _ in range(4)] + [
            ("", "sale la carta Muerte")]
        cobertura_dataset.contar_cartas(pares, cont)
        md = cobertura_dataset.construir_informe_md(cont, 5, 20,
                                                    stats={"pares": 5})
        self.assertIn("80.0%", md)  # Loco: 4 de 5
        seccion = md.split("## Las 10 entidades más representadas", 1)[1]
        self.assertLess(seccion.find("El Loco"), seccion.find("La Muerte"))


class Cli(unittest.TestCase):
    def test_dry_run_no_escribe(self):
        import contextlib
        import io
        ruta = os.path.join("/tmp", "t15_test_dry.jsonl")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"conversations": [
                {"from": "human", "value": "¿tarot?"},
                {"from": "gpt", "value": "sale la carta El Loco"}]},
                ensure_ascii=False) + "\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cobertura_dataset.main([
                "--in", ruta, "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("El Loco", buf.getvalue())
        for p in ("/tmp/cobertura_dataset.json", "/tmp/cobertura_dataset.md"):
            if os.path.exists(p):
                os.remove(p)
        os.remove(ruta)

    def test_escribe_ficheros(self):
        ruta_in = "/tmp/t15_test_in.jsonl"
        with open(ruta_in, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"conversations": [
                {"from": "human", "value": "numerología"},
                {"from": "gpt", "value": "tu camino de vida es 7"}]},
                ensure_ascii=False) + "\n")
        rc = cobertura_dataset.main([
            "--in", ruta_in,
            "--out-json", "/tmp/t15_out.json",
            "--out-md", "/tmp/t15_out.md"])
        self.assertEqual(rc, 0)
        with open("/tmp/t15_out.json", encoding="utf-8") as fh:
            resumen = json.load(fh)
        self.assertEqual(
            resumen["entidades"]["numero:07"]["pares_respuesta"], 1)
        with open("/tmp/t15_out.md", encoding="utf-8") as fh:
            self.assertIn("# Informe de cobertura", fh.read())
        for p in (ruta_in, "/tmp/t15_out.json", "/tmp/t15_out.md"):
            os.remove(p)


if __name__ == "__main__":
    unittest.main()
