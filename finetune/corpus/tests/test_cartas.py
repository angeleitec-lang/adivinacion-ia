"""Tests del catálogo de cartas y del normalizador de nombres (track A4.1)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cartas


def _por_nombre(lista, nombre):
    for entrada in lista:
        if entrada["nombre"] == nombre:
            return entrada
    return None


class Catalogo(unittest.TestCase):
    def test_tarot_tiene_78_cartas(self):
        self.assertEqual(len(cartas.CARTAS_TAROT), 78)

    def test_tarot_ids_y_nombres_unicos(self):
        ids = [c["id"] for c in cartas.CARTAS_TAROT]
        nombres = [c["nombre"] for c in cartas.CARTAS_TAROT]
        self.assertEqual(len(set(ids)), 78)
        self.assertEqual(len(set(nombres)), 78)

    def test_tarot_22_mayores_y_56_menores(self):
        mayores = [c for c in cartas.CARTAS_TAROT if c["arcano"] == "mayor"]
        menores = [c for c in cartas.CARTAS_TAROT if c["arcano"] == "menor"]
        self.assertEqual(len(mayores), 22)
        self.assertEqual(len(menores), 56)
        for c in cartas.CARTAS_TAROT:
            self.assertIn(c["arcano"], ("mayor", "menor"))
            if c["arcano"] == "mayor":
                self.assertIsNone(c["palo"])
            else:
                self.assertIn(c["palo"], ("Bastos", "Copas", "Espadas", "Oros"))

    def test_naipe_tiene_40_cartas_unicas(self):
        self.assertEqual(len(cartas.NAIPES_ESPANOLES), 40)
        ids = [c["id"] for c in cartas.NAIPES_ESPANOLES]
        nombres = [c["nombre"] for c in cartas.NAIPES_ESPANOLES]
        self.assertEqual(len(set(ids)), 40)
        self.assertEqual(len(set(nombres)), 40)

    def test_esquema_de_entrada(self):
        for lista in (cartas.CARTAS_TAROT, cartas.NAIPES_ESPANOLES):
            for entrada in lista:
                self.assertEqual(
                    sorted(entrada.keys()),
                    ["arcano", "id", "nombre", "numero", "palo", "sinonimos"],
                )
                self.assertIsInstance(entrada["numero"], int)
                self.assertIsInstance(entrada["sinonimos"], list)

    def test_sonido_de_mayores_canonicos(self):
        esperados = ["El Loco", "La Sacerdotisa", "Los Enamorados",
                     "La Rueda de la Fortuna", "El Juicio"]
        for nombre in esperados:
            self.assertIsNotNone(_por_nombre(cartas.CARTAS_TAROT, nombre), nombre)


class Norm(unittest.TestCase):
    def test_norm_minusculas_sin_tildes_sin_signos(self):
        self.assertEqual(cartas.norm("¡La Reina de Copas, invertida!"),
                         "la reina de copas invertida")

    def test_norm_espacios_simplos(self):
        self.assertEqual(cartas.norm("  el   loco  "), "el loco")

    def test_norm_vacia(self):
        self.assertEqual(cartas.norm(""), "")
        self.assertEqual(cartas.norm(None), "")


class NormalizarCarta(unittest.TestCase):
    def test_papisa_es_sacerdotisa(self):
        entrada = cartas.normalizar_carta("la papisa")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "La Sacerdotisa")

    def test_ahorcado_es_colgado(self):
        entrada = cartas.normalizar_carta("El Ahorcado")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "El Colgado")

    def test_tres_de_espadas_con_articulo(self):
        entrada = cartas.normalizar_carta("el tres de espadas")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "Tres de Espadas")
        self.assertEqual(entrada["palo"], "Espadas")
        self.assertEqual(entrada["numero"], 3)

    def test_sota_de_oros(self):
        entrada = cartas.normalizar_carta("sota de oros")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "Sota de Oros")

    def test_paje_de_pentaculos_es_sota(self):
        entrada = cartas.normalizar_carta("paje de pentáculos")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "Sota de Oros")

    def test_bastos_solo_no_es_carta(self):
        self.assertIsNone(cartas.normalizar_carta("bastos"))
        self.assertIsNone(cartas.normalizar_carta("las copas"))

    def test_subtitulo_auto_reina_de_copas_invertido(self):
        entrada = cartas.normalizar_carta("la reina de copas invertido")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "Reina de Copas")

    def test_carta_inventada_devuelve_none(self):
        self.assertIsNone(cartas.normalizar_carta("la carta mágica verde"))

    def test_mazo_espanol_caballo_y_siete(self):
        caballo = cartas.normalizar_carta("el caballo de copas", mazo="español")
        self.assertIsNotNone(caballo)
        self.assertEqual(caballo["nombre"], "Caballo de Copas")
        siete = cartas.normalizar_carta("el siete de oros", mazo="español")
        self.assertIsNotNone(siete)
        self.assertEqual(siete["nombre"], "Siete de Oros")
        # La reina no existe en la baraja española de 40 cartas
        self.assertIsNone(cartas.normalizar_carta("la reina de copas",
                                                  mazo="español"))

    def test_magia_de_los_bastos(self):
        entrada = cartas.normalizar_carta("el mago de los bastos")
        self.assertIsNotNone(entrada)
        self.assertEqual(entrada["nombre"], "El Mago")


class ExtraerCartas(unittest.TestCase):
    def test_texto_sin_cartas(self):
        self.assertEqual(cartas.extraer_cartas("hoy toca hablar del destino"), [])

    def test_bastos_solo_no_extrae(self):
        self.assertEqual(cartas.extraer_cartas("vemos los bastos del naipe"), [])

    def test_enamorados_invertidos(self):
        menciones = cartas.extraer_cartas("salen los enamorados invertidos hoy")
        self.assertEqual(len(menciones), 1)
        self.assertEqual(menciones[0]["carta"]["nombre"], "Los Enamorados")
        self.assertEqual(menciones[0]["orientacion"], "invertida")

    def test_orientacion_derecha_explicita(self):
        menciones = cartas.extraer_cartas("la fuerza derecha apoya el cambio")
        self.assertEqual(len(menciones), 1)
        self.assertEqual(menciones[0]["orientacion"], "derecha")

    def test_orientacion_ausente_es_none(self):
        menciones = cartas.extraer_cartas("hablamos de la muerte y el sol")
        orientaciones = {m["carta"]["nombre"]: m["orientacion"]
                         for m in menciones}
        self.assertEqual(orientaciones["La Muerte"], None)
        self.assertEqual(orientaciones["El Sol"], None)

    def test_orden_de_aparicion_y_posicion(self):
        texto = "primero el loco, luego tres de espadas y al final la luna"
        menciones = cartas.extraer_cartas(texto)
        self.assertEqual([m["carta"]["nombre"] for m in menciones],
                         ["El Loco", "Tres de Espadas", "La Luna"])
        posiciones = [m["posicion_texto"] for m in menciones]
        self.assertEqual(posiciones, sorted(posiciones))
        self.assertEqual(posiciones[0], cartas.norm(texto).index("el loco"))

    def test_ventana_orientacion_no_contamina_siguiente_carta(self):
        menciones = cartas.extraer_cartas("el loco y la luna invertida")
        self.assertEqual(len(menciones), 2)
        self.assertEqual(menciones[0]["carta"]["nombre"], "El Loco")
        self.assertIsNone(menciones[0]["orientacion"])
        self.assertEqual(menciones[1]["carta"]["nombre"], "La Luna")
        self.assertEqual(menciones[1]["orientacion"], "invertida")

    def test_subtitulo_auto_sin_tildes(self):
        texto = "hoy la sacerdotisa esta invertida y el mago aparece derecho"
        menciones = cartas.extraer_cartas(texto)
        self.assertEqual(len(menciones), 2)
        self.assertEqual(menciones[0]["carta"]["nombre"], "La Sacerdotisa")
        self.assertEqual(menciones[0]["orientacion"], "invertida")
        self.assertEqual(menciones[1]["orientacion"], "derecha")

    def test_mazo_espanol_en_texto(self):
        menciones = cartas.extraer_cartas(
            "primero el caballo de copas y después el siete de oros",
            mazo="español")
        self.assertEqual([m["carta"]["nombre"] for m in menciones],
                         ["Caballo de Copas", "Siete de Oros"])

    def test_no_coincide_dentro_de_palabra(self):
        self.assertEqual(cartas.extraer_cartas("casas y solares bonitos"), [])


if __name__ == "__main__":
    unittest.main()
