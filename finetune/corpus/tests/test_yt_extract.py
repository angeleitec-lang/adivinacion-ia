#!/usr/bin/env python3
"""Tests para yt_extract.py (A4.5)."""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_extract
import llm_client
import cartas
import unittest


def _simulado_lectura_buena(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [
    {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica una decision importante en el amor"},
    {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
    {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y exito"}
  ],
  "sintesis": "La lectura muestra evolucion de bloqueo a claridad",
  "consejo": "Confia en tu intuicion"
}
```'''


def _simulado_carta_inventada(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "El Dragon", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [
    {"carta": "El Dragon", "texto": "El Dragon indica poder"},
    {"carta": "La Emperatriz", "texto": "La Emperatriz invertida"},
    {"carta": "El Sol", "texto": "El Sol brilla"}
  ],
  "sintesis": "Test",
  "consejo": "Ok"
}
```'''


def _simulado_nueve_cartas_tres(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
    {"nombre": "La Luna", "orientacion": "derecha", "posicion": "extra1"},
    {"nombre": "El Mago", "orientacion": "derecha", "posicion": "extra2"},
    {"nombre": "La Muerte", "orientacion": "derecha", "posicion": "extra3"},
    {"nombre": "El Diablo", "orientacion": "derecha", "posicion": "extra4"},
    {"nombre": "La Torre", "orientacion": "derecha", "posicion": "extra5"},
    {"nombre": "El Loco", "orientacion": "derecha", "posicion": "extra6"}
  ],
  "interpretaciones": [],
  "sintesis": "",
  "consejo": ""
}
```'''


def _simulado_posicion_invalida(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "posicion_inventada"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [],
  "sintesis": "",
  "consejo": ""
}
```'''


def _simulado_interpretacion_no_anclada(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [
    {"carta": "Los Enamorados", "texto": "Esta carta significa algo que NO aparece en el texto original del video"},
    {"carta": "La Emperatriz", "texto": "Interpretacion inventada"},
    {"carta": "El Sol", "texto": "Otra interpretacion falsa"}
  ],
  "sintesis": "Test",
  "consejo": "Ok"
}
```'''


def _simulado_carta_natal_sin_planetas(sistema, usuario):
    return '''```json
{
  "tipo": "lectura",
  "tirada": "carta_natal",
  "pregunta_o_tema": "carta natal",
  "cartas": [],
  "interpretaciones": [],
  "sintesis": "",
  "consejo": ""
}
```'''


def _simulado_no_lectura(sistema, usuario):
    return '''```json
{"tipo": "no_lectura"}
```'''


class ExtraerLectura(unittest.TestCase):
    def test_extraccion_exitosa(self):
        client = llm_client.LLMClient(simulado=lambda s, u: '''```json
{
  "tipo": "lectura",
  "tirada": "3_cartas",
  "pregunta_o_tema": "amor",
  "cartas": [
    {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
    {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
    {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"}
  ],
  "interpretaciones": [
    {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica decision"},
    {"carta": "La Emperatriz", "texto": "La Emperatriz invertida pasado"},
    {"carta": "El Sol", "texto": "El Sol futuro claridad"}
  ],
  "sintesis": "Evolucion bloqueo a claridad",
  "consejo": "Confia en intuicion"
}
```''')
        texto = "texto original con Los Enamorados La Emperatriz El Sol decision amor claridad"
        res = yt_extract.extraer_lectura(texto, client)
        self.assertEqual(res.get("tipo"), "lectura")
        self.assertEqual(res.get("tirada"), "3_cartas")
        self.assertEqual(len(res.get("cartas", [])), 3)


class ValidarLectura(unittest.TestCase):
    def setUp(self):
        self.texto_base = (
            "hola bienvenidos hoy en esta tirada la carta los enamorados sale en presente "
            "la carta la emperatriz invertida en pasado y la carta el sol sale en futuro "
            "los enamorados significa decision importante en el amor "
            "la emperatriz invertida representa bloqueo creativo "
            "el sol representa claridad y exito "
            "sintesis la lectura muestra evolucion de bloqueo a claridad "
            "consejo confia en tu intuicion"
        )

    def test_lectura_buena_pasa(self):
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [
                {"carta": "Los Enamorados", "texto": "Los Enamorados en presente indica decision importante en el amor"},
                {"carta": "La Emperatriz", "texto": "La Emperatriz invertida en pasado sugiere bloqueo creativo"},
                {"carta": "El Sol", "texto": "El Sol en futuro augura claridad y exito"},
            ],
            "sintesis": "La lectura muestra evolucion de bloqueo a claridad",
            "consejo": "Confia en tu intuicion",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertTrue(valida, f"Fallos: {motivos}")

    def test_carta_inventada_falla(self):
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "El Dragon", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("no existe en catálogo" in m for m in motivos))

    def test_nueve_cartas_para_tres_falla(self):
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
                {"nombre": "La Luna", "orientacion": "derecha", "posicion": "extra1"},
                {"nombre": "El Mago", "orientacion": "derecha", "posicion": "extra2"},
                {"nombre": "La Muerte", "orientacion": "derecha", "posicion": "extra3"},
                {"nombre": "El Diablo", "orientacion": "derecha", "posicion": "extra4"},
                {"nombre": "La Torre", "orientacion": "derecha", "posicion": "extra5"},
                {"nombre": "El Loco", "orientacion": "derecha", "posicion": "extra6"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("Nº cartas" in m for m in motivos))

    def test_posicion_inexistente_falla(self):
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "posicion_inventada"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("Posición inválida" in m for m in motivos))

    def test_interpretacion_no_anclada_falla(self):
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [
                {"carta": "Los Enamorados", "texto": "Esta carta significa algo que NO aparece en el texto original del video"},
                {"carta": "La Emperatriz", "texto": "Interpretacion inventada"},
                {"carta": "El Sol", "texto": "Otra interpretacion falsa"},
            ],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("no anclada" in m for m in motivos))

    def test_carta_natal_sin_validacion_especifica(self):
        # Por ahora solo validamos estructura básica
        lectura = {
            "tipo": "lectura",
            "tirada": "carta_natal",
            "pregunta_o_tema": "carta natal",
            "cartas": [],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        # No debe fallar por validaciones 1-4 (no hay cartas)
        # La validación 5 (carta_natal) es passthrough por ahora
        self.assertTrue(valida or len(motivos) == 0)

    # --- Tests A4.5b: validaciones de carta en original y orientación ---
    def test_carta_no_mencionada_en_original_falla(self):
        """Carta extraída que no está en el texto original debe fallar."""
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "El Loco", "orientacion": "derecha", "posicion": "presente"},  # no en texto_base
                {"nombre": "La Emperatriz", "orientacion": "invertida", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("carta_no_mencionada" in m and "El Loco" in m for m in motivos))

    def test_orientacion_contradice_original_invertida_vs_derecha_falla(self):
        """Original dice invertida, extracción dice derecha -> falla."""
        # En texto_base: "la carta la emperatriz invertida"
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "derecha", "posicion": "presente"},
                {"nombre": "La Emperatriz", "orientacion": "derecha", "posicion": "pasado"},  # contradice
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, self.texto_base)
        self.assertFalse(valida)
        self.assertTrue(any("orientacion_contradice" in m and "La Emperatriz" in m for m in motivos))

    def test_orientacion_contradice_original_derecha_vs_invertida_falla(self):
        """Original dice derecha (al derecho), extracción dice invertida -> falla."""
        texto = (
            "hola en esta tirada la carta los enamorados sale al derecho en presente "
            "la carta la emperatriz en pasado y la carta el sol en futuro "
        )
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "invertida", "posicion": "presente"},  # contradice
                {"nombre": "La Emperatriz", "orientacion": "derecha", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, texto)
        self.assertFalse(valida)
        self.assertTrue(any("orientacion_contradice" in m and "Los Enamorados" in m for m in motivos))

    def test_sinonimo_carta_en_original_pasa(self):
        """Sinónimo en original (la papisa) coincide con canónico (La Sacerdotisa) -> pasa."""
        texto = (
            "hola en esta tirada la carta la papisa sale en presente "
            "la carta el emperador en pasado y la carta el sol en futuro "
        )
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "La Sacerdotisa", "orientacion": "derecha", "posicion": "presente"},  # sinónimo
                {"nombre": "El Emperador", "orientacion": "derecha", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, texto)
        self.assertTrue(valida, f"Fallos: {motivos}")

    def test_orientacion_no_mencionada_pasa(self):
        """Original no menciona orientación, extracción puede poner cualquiera -> pasa."""
        texto = (
            "hola en esta tirada la carta los enamorados sale en presente "
            "la carta la emperatriz en pasado y la carta el sol en futuro "
        )
        lectura = {
            "tipo": "lectura",
            "tirada": "3_cartas",
            "pregunta_o_tema": "amor",
            "cartas": [
                {"nombre": "Los Enamorados", "orientacion": "invertida", "posicion": "presente"},  # original no dice
                {"nombre": "La Emperatriz", "orientacion": "derecha", "posicion": "pasado"},
                {"nombre": "El Sol", "orientacion": "derecha", "posicion": "futuro"},
            ],
            "interpretaciones": [],
            "sintesis": "", "consejo": "",
        }
        valida, motivos = yt_extract.validar_lectura(lectura, texto)
        self.assertTrue(valida, f"Fallos: {motivos}")


if __name__ == "__main__":
    unittest.main()
