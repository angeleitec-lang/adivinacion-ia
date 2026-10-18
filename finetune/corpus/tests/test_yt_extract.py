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
            "hola bienvenidos hoy vemos los enamorados en presente "
            "la emperatriz invertida en pasado y el sol en futuro "
            "los enamorados indica decision importante en el amor "
            "la emperatriz invertida sugiere bloqueo creativo "
            "el sol augura claridad y exito "
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


if __name__ == "__main__":
    unittest.main()
