"""Módulo de calculadoras deterministas (C1)."""

from .astro import (
    carta_natal,
    transitos,
    transitos_periodo,
    revolucion_solar,
    sinastria,
)

from .numerologia import (
    reducir,
    camino_de_vida,
    expresion,
    alma,
    personalidad,
    anio_personal,
    mes_personal,
    dia_personal,
    compatibilidad,
    perfil_completo,
)

from .biorritmos import biorritmos as calcular_biorritmos

__all__ = [
    "carta_natal",
    "transitos",
    "transitos_periodo",
    "revolucion_solar",
    "sinastria",
    "reducir",
    "camino_de_vida",
    "expresion",
    "alma",
    "personalidad",
    "anio_personal",
    "mes_personal",
    "dia_personal",
    "compatibilidad",
    "perfil_completo",
    "calcular_biorritmos",
]
