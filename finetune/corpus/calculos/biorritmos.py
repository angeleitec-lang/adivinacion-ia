"""Biorritmos (C1.6).

Ciclos:
- Físico: 23 días
- Emocional: 28 días
- Intelectual: 33 días

Fórmula: valor = sin(2π * t / P)
t = días enteros transcurridos desde nacimiento (positivo o negativo)
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Dict, List, Optional


CICLOS = {
    "fisico": 23,
    "emocional": 28,
    "intelectual": 33,
}


def _parse_fecha(fecha: str) -> date:
    """Valida "AAAA-MM-DD" con error claro en español (rechaza días inexistentes)."""
    try:
        return date.fromisoformat(fecha)
    except (ValueError, TypeError):
        raise ValueError(
            f"Fecha inválida: {fecha!r}. Use formato AAAA-MM-DD con un día existente "
            "(recuerde que 1900 no fue bisiesto)."
        ) from None


def _dias_transcurridos(fecha_nacimiento: str, fecha: str) -> int:
    """Calcula días enteros entre dos fechas (fecha - nacimiento)."""
    fn = _parse_fecha(fecha_nacimiento)
    f = _parse_fecha(fecha)
    return (f - fn).days


def _valor_ciclo(t: int, periodo: int) -> float:
    """Valor del biorritmo: sin(2π * t / P)."""
    return math.sin(2 * math.pi * t / periodo)


def _fase(valor: float, t: int, periodo: int) -> str:
    """Determina la fase: ascendente, descendente, crítico."""
    # Crítico si |valor| < 0.05 o si cruza cero ese día (cambio de signo)
    if abs(valor) < 0.05:
        return "crítico"
    # Verificar si cruza cero al día siguiente
    valor_sig = _valor_ciclo(t + 1, periodo)
    if valor * valor_sig < 0:  # cambio de signo
        return "crítico"
    return "ascendente" if valor_sig > valor else "descendente"


def _porcentaje(valor: float) -> int:
    """Convierte valor [-1, 1] a porcentaje [-100, 100] redondeado."""
    return round(valor * 100)


def biorritmos(
    fecha_nacimiento: str,
    fecha: str,
    dias: int = 0
) -> Dict[str, Any]:
    """Calcula biorritmos para una fecha (y ventana opcional).

    Args:
        fecha_nacimiento: "AAAA-MM-DD"
        fecha: "AAAA-MM-DD" (fecha objetivo)
        dias: si > 0, devuelve ventana de N días desde la fecha objetivo

    Returns:
        dict con ciclos (valor, porcentaje, fase) para la fecha,
        y opcionalmente "ventana" con lista de días.
    """
    fn = _parse_fecha(fecha_nacimiento)
    f = _parse_fecha(fecha)

    if f < fn:
        raise ValueError("La fecha no puede ser anterior al nacimiento")

    t_base = (f - fn).days

    def calc_dia(t: int) -> Dict[str, Any]:
        return {
            "fisico": {
                "valor": round(_valor_ciclo(t, 23), 4),
                "porcentaje": _porcentaje(_valor_ciclo(t, 23)),
                "fase": _fase(_valor_ciclo(t, 23), t, 23),
            },
            "emocional": {
                "valor": round(_valor_ciclo(t, 28), 4),
                "porcentaje": _porcentaje(_valor_ciclo(t, 28)),
                "fase": _fase(_valor_ciclo(t, 28), t, 28),
            },
            "intelectual": {
                "valor": round(_valor_ciclo(t, 33), 4),
                "porcentaje": _porcentaje(_valor_ciclo(t, 33)),
                "fase": _fase(_valor_ciclo(t, 33), t, 33),
            },
        }

    resultado = {
        "fecha": fecha,
        "dias_desde_nacimiento": t_base,
        "ciclos": calc_dia(t_base),
    }

    if dias > 0:
        ventana = []
        for i in range(dias):
            f_dia = f + timedelta(days=i)
            t = (f_dia - fn).days
            dia_data = calc_dia(t)
            dia_data["fecha"] = f_dia.isoformat()
            dia_data["dias_desde_nacimiento"] = t
            ventana.append(dia_data)
        resultado["ventana"] = ventana

    return resultado


if __name__ == "__main__":
    import json
    # Tests de referencia
    print(json.dumps({
        "t0": biorritmos("1990-01-01", "1990-01-01"),
        "t23_4": biorritmos("1990-01-01", "1990-01-24"),  # t=23 -> fisico P/4? 23/4=5.75 no
        "t7_28": biorritmos("1990-01-01", "1990-01-08"),  # t=7 para emocional (28/4=7)
        "t14_28": biorritmos("1990-01-01", "1990-01-15"), # t=14 para emocional (28/2=14)
    }, ensure_ascii=False, indent=2))
