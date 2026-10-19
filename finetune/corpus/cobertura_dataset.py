#!/usr/bin/env python3
"""Informe de cobertura del dataset de entrenamiento (track T15).

Cuenta, por entidad (cartas de tarot y baraja española, signos, planetas,
casas y números de numerología), cuántos pares del dataset la mencionan en
la respuesta y cuántos solo en la pregunta, y señala los huecos por debajo
de un mínimo. Formato de entrada: ShareGPT ({"conversations": [{"from":
"system"|"human"|"gpt", "value": …}]}).

API:
    leer_pares(rutas)                       -> ([(pregunta, respuesta)], stats)
    contar_cartas(pares, contadores)        -> rellena contadores por carta
Diseñado para no depender de la matriz de cobertura de fuentes (T14).
"""

from __future__ import annotations

import json

import cartas


def leer_pares(rutas):
    """Lee ficheros JSONL en formato ShareGPT y devuelve (pares, stats).

    Cada par es (texto_de_human, texto_de_gpt); si hay varios mensajes del
    mismo rol se concatenan con espacios. Las líneas vacías, el JSON
    inválido y los objetos sin lista «conversations» se cuentan en
    stats["lineas_invalidas"]; las filas sin ningún mensaje «gpt» se
    cuentan en stats["sin_gpt"] y no producen par. stats["pares"] es el
    número de pares leídos.
    """
    pares = []
    stats = {"pares": 0, "lineas_invalidas": 0, "sin_gpt": 0}
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    stats["lineas_invalidas"] += 1
                    continue
                try:
                    fila = json.loads(linea)
                except json.JSONDecodeError:
                    stats["lineas_invalidas"] += 1
                    continue
                if (not isinstance(fila, dict)
                        or not isinstance(fila.get("conversations"), list)):
                    stats["lineas_invalidas"] += 1
                    continue
                humano, gpt = [], []
                for mensaje in fila["conversations"]:
                    if not isinstance(mensaje, dict):
                        continue
                    origen = mensaje.get("from")
                    valor = str(mensaje.get("value", ""))
                    if origen == "gpt":
                        gpt.append(valor)
                    elif origen == "human":
                        humano.append(valor)
                if not gpt:
                    stats["sin_gpt"] += 1
                    continue
                pares.append((" ".join(humano), " ".join(gpt)))
    stats["pares"] = len(pares)
    return pares, stats


_FAMILIAS_CARTAS = (("tarot", "tarot"), ("espanol", "espanola"))


def _contador(contadores, clave, etiqueta, familia):
    """Devuelve (creándolo si falta) el contador de una entidad."""
    if clave not in contadores:
        contadores[clave] = {
            "etiqueta": etiqueta,
            "familia": familia,
            "pares_respuesta": 0,
            "pares_pregunta": 0,
            "solo_en_respuesta": 0,
        }
    return contadores[clave]


def _menciones_cartas(texto, mazo):
    """Menciones de cartas del mazo agrupadas por clave; «invertida» es True
    si alguna mención del texto viene invertida. Se apoya en
    cartas.extraer_cartas (no reimplementa el reconocimiento)."""
    por_clave = {}
    for m in cartas.extraer_cartas(texto, mazo=mazo):
        clave = "{}:{}".format(mazo, m["carta"]["id"])
        dato = por_clave.setdefault(
            clave, {"nombre": m["carta"]["nombre"], "invertida": False})
        if m["orientacion"] == "invertida":
            dato["invertida"] = True
    return por_clave


def contar_cartas(pares, contadores):
    """Cuenta los pares que mencionan cada carta de tarot y de baraja
    española. Una carta cuenta una sola vez por par; en «invertidas» se
    suman los pares cuya respuesta la trae invertida. Clave: «<mazo>:<id>»."""
    for pregunta, respuesta in pares:
        for mazo, familia in _FAMILIAS_CARTAS:
            en_resp = _menciones_cartas(respuesta, mazo)
            en_preg = _menciones_cartas(pregunta, mazo)
            for clave in sorted(set(en_resp) | set(en_preg)):
                dato = en_resp[clave] if clave in en_resp else en_preg[clave]
                c = _contador(contadores, clave, dato["nombre"], familia)
                c.setdefault("invertidas", 0)
                if clave in en_resp:
                    c["pares_respuesta"] += 1
                    if clave not in en_preg:
                        c["solo_en_respuesta"] += 1
                    if en_resp[clave]["invertida"]:
                        c["invertidas"] += 1
                if clave in en_preg:
                    c["pares_pregunta"] += 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Informe de cobertura del dataset (WIP track T15).")
    parser.add_argument("--in", dest="ins", nargs="+", required=True,
                        help="ficheros JSONL ShareGPT")
    args = parser.parse_args()
    _pares, _stats = leer_pares(args.ins)
    print(json.dumps(_stats, ensure_ascii=False))
