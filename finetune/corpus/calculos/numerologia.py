"""Numerología pitagórica completa (C1.5)."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Dict, List, Tuple, Optional


# ---------------------------------------------------------------------------
# Tabla pitagórica
# ---------------------------------------------------------------------------

PITAGORICA = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8, 'I': 9,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'O': 6, 'P': 7, 'Q': 8, 'R': 9,
    'S': 1, 'T': 2, 'U': 3, 'V': 4, 'W': 5, 'X': 6, 'Y': 7, 'Z': 8,
}

VOCALES = set('AEIOUÁÉÍÓÚ')

# Tabla de compatibilidad caminos de vida (1-9, 11, 22, 33 reducidos a base)
# Simétrica, valores: "alta", "media", "baja"
COMPATIBILIDAD = {
    (1, 1): "media", (1, 2): "alta", (1, 3): "alta", (1, 4): "baja", (1, 5): "alta", (1, 6): "alta", (1, 7): "alta", (1, 8): "baja", (1, 9): "alta",
    (2, 2): "media", (2, 3): "alta", (2, 4): "alta", (2, 5): "baja", (2, 6): "alta", (2, 7): "baja", (2, 8): "alta", (2, 9): "alta",
    (3, 3): "media", (3, 4): "alta", (3, 5): "alta", (3, 6): "alta", (3, 7): "alta", (3, 8): "alta", (3, 9): "alta",
    (4, 4): "media", (4, 5): "baja", (4, 6): "alta", (4, 7): "alta", (4, 8): "alta", (4, 9): "baja",
    (5, 5): "media", (5, 6): "baja", (5, 7): "alta", (5, 8): "alta", (5, 9): "alta",
    (6, 6): "media", (6, 7): "baja", (6, 8): "alta", (6, 9): "alta",
    (7, 7): "media", (7, 8): "alta", (7, 9): "baja",
    (8, 8): "media", (8, 9): "alta",
    (9, 9): "media",
}


def _normalizar_texto(texto: str) -> str:
    """Normaliza: NFD, quita tildes, mayúsculas, solo letras."""
    if not texto:
        return ""
    nfd = unicodedata.normalize('NFD', texto)
    sin_tildes = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return ''.join(c.upper() for c in sin_tildes if c.isalpha())


def reducir(n: int, maestros: bool = True) -> int:
    """Reduce un número a 1-9, conservando 11/22/33 si maestros=True."""
    if n <= 0:
        return 0
    while n > 9:
        if maestros and n in (11, 22, 33):
            return n
        n = sum(int(d) for d in str(n))
    return n


def camino_de_vida(fecha: str) -> int:
    """Calcula el camino de vida por componentes (día, mes, año por separado).

    Método: reducir día, mes y año por separado conservando maestros en componentes,
    luego sumar y reducir.
    """
    dt = datetime.strptime(fecha, "%Y-%m-%d")
    dia = reducir(dt.day)
    mes = reducir(dt.month)
    anio = reducir(dt.year)
    total = dia + mes + anio
    return reducir(total)


def _valor_letra(c: str) -> int:
    return PITAGORICA.get(c, 0)


def _es_vocal(c: str) -> bool:
    return c in VOCALES


def expresion(nombre: str) -> int:
    """Número de expresión: suma de todas las letras."""
    texto = _normalizar_texto(nombre)
    total = sum(_valor_letra(c) for c in texto)
    return reducir(total)


def alma(nombre: str) -> int:
    """Número del alma (vocales)."""
    texto = _normalizar_texto(nombre)
    total = sum(_valor_letra(c) for c in texto if _es_vocal(c))
    return reducir(total)


def personalidad(nombre: str) -> int:
    """Número de personalidad (consonantes). Y siempre como consonante (simplificación)."""
    texto = _normalizar_texto(nombre)
    total = sum(_valor_letra(c) for c in texto if not _es_vocal(c))
    return reducir(total)


def _reduccion_sin_maestros(n: int) -> int:
    """Reduce a 1-9 sin conservar maestros."""
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n


def anio_personal(fecha: str, anio: int) -> int:
    """Año personal: día + mes de nacimiento + dígitos del año (reducidos sin maestros)."""
    dt = datetime.strptime(fecha, "%Y-%m-%d")
    dia = reducir(dt.day, maestros=False)
    mes = reducir(dt.month, maestros=False)
    anio_red = _reduccion_sin_maestros(anio)
    return reducir(dia + mes + anio_red, maestros=False)


def mes_personal(fecha: str, anio: int, mes: int) -> int:
    """Mes personal: año_personal + mes (reducido sin maestros)."""
    ap = anio_personal(fecha, anio)
    mes_red = reducir(mes, maestros=False)
    return reducir(ap + mes_red, maestros=False)


def dia_personal(fecha: str, anio: int, mes: int, dia: int) -> int:
    """Día personal: mes_personal + día (reducido sin maestros)."""
    mp = mes_personal(fecha, anio, mes)
    dia_red = reducir(dia, maestros=False)
    return reducir(mp + dia_red, maestros=False)


def compatibilidad(fecha_a: str, fecha_b: str) -> Dict[str, Any]:
    """Compatibilidad entre dos caminos de vida."""
    cdv_a = camino_de_vida(fecha_a)
    cdv_b = camino_de_vida(fecha_b)

    # Reducir maestros a base para tabla
    base_a = cdv_a if cdv_a not in (11, 22, 33) else reducir(cdv_a, maestros=False)
    base_b = cdv_b if cdv_b not in (11, 22, 33) else reducir(cdv_b, maestros=False)

    key = tuple(sorted((base_a, base_b)))
    nivel = COMPATIBILIDAD.get(key, "media")

    return {
        "camino_a": cdv_a,
        "camino_b": cdv_b,
        "nivel": nivel,
    }


def perfil_completo(nombre: str, fecha: str, anio: int) -> Dict[str, Any]:
    """Perfil numerológico completo."""
    return {
        "camino_de_vida": camino_de_vida(fecha),
        "expresion": expresion(nombre),
        "alma": alma(nombre),
        "personalidad": personalidad(nombre),
        "anio_personal": anio_personal(fecha, anio),
        "mes_personal": mes_personal(fecha, anio, datetime.now().month),
        "dia_personal": dia_personal(fecha, anio, datetime.now().month, datetime.now().day),
    }


if __name__ == "__main__":
    import json
    print(json.dumps({
        "camino_de_vida_1963_11_06": camino_de_vida("1963-11-06"),
        "camino_de_vida_1960_02_29": camino_de_vida("1960-02-29"),
        "camino_de_vida_1992_11_29": camino_de_vida("1992-11-29"),
        "camino_de_vida_1985_07_04": camino_de_vida("1985-07-04"),
        "expresion_Ana": expresion("Ana"),
        "alma_Ana": alma("Ana"),
        "personalidad_Ana": personalidad("Ana"),
        "anio_personal_1963_11_06_2026": anio_personal("1963-11-06", 2026),
    }, ensure_ascii=False, indent=2))
