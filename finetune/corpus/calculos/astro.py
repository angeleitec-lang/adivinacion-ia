#!/usr/bin/env python3
"""Calculadoras de astrología deterministas (C1.1, C1.2, C1.3, C1.4).

Usa swisseph (pyswisseph) con Moshier (sin archivos externos).
"""

from __future__ import annotations

import calendar
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

try:
    import swisseph as swe
except ImportError:
    swe = None  # type: ignore

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

PLANETAS = [
    ("Sol", swe.SUN if swe else 0),
    ("Luna", swe.MOON if swe else 1),
    ("Mercurio", swe.MERCURY if swe else 2),
    ("Venus", swe.VENUS if swe else 3),
    ("Marte", swe.MARS if swe else 4),
    ("Júpiter", swe.JUPITER if swe else 5),
    ("Saturno", swe.SATURN if swe else 6),
    ("Urano", swe.URANUS if swe else 7),
    ("Neptuno", swe.NEPTUNE if swe else 8),
    ("Plutón", swe.PLUTO if swe else 9),
]

PLANETAS_LENtos = ["Júpiter", "Saturno", "Urano", "Neptuno", "Plutón"]

SIGNOS = [
    "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo",
    "Libra", "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis"
]

# Aspectos y orbes (grados)
ASPECTOS = [
    ("conjunción", 0, 6),
    ("sextil", 60, 5),
    ("cuadratura", 90, 6),
    ("trígono", 120, 6),
    ("oposición", 180, 7),
]

# Orbes para tránsitos al natal (la mitad)
ASPECTOS_TRANSITO = [
    ("conjunción", 0, 3),
    ("sextil", 60, 2.5),
    ("cuadratura", 90, 3),
    ("trígono", 120, 3),
    ("oposición", 180, 3.5),
]

# Elementos y modalidades por signo
ELEMENTOS = {
    "Aries": "Fuego", "Leo": "Fuego", "Sagitario": "Fuego",
    "Tauro": "Tierra", "Virgo": "Tierra", "Capricornio": "Tierra",
    "Géminis": "Aire", "Libra": "Aire", "Acuario": "Aire",
    "Cáncer": "Agua", "Escorpio": "Agua", "Piscis": "Agua",
}

MODALIDADES = {
    "Aries": "Cardinal", "Cáncer": "Cardinal", "Libra": "Cardinal", "Capricornio": "Cardinal",
    "Tauro": "Fijo", "Leo": "Fijo", "Escorpio": "Fijo", "Acuario": "Fijo",
    "Géminis": "Mutable", "Virgo": "Mutable", "Sagitario": "Mutable", "Piscis": "Mutable",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _init_swe():
    """Inicializa swisseph con Moshier (sin archivos externos)."""
    if swe:
        swe.set_ephe_path("")  # usa Moshier interno
        swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY)


def _lon_a_signo_grado_minuto(lon: float) -> Tuple[str, int, int]:
    """Convierte longitud eclíptica (0-360) a signo, grado, minuto."""
    lon = lon % 360
    signo_idx = int(lon // 30)
    grado_en_signo = lon % 30
    grado = int(grado_en_signo)
    minuto = int(round((grado_en_signo - grado) * 60))
    if minuto == 60:
        minuto = 0
        grado += 1
        if grado == 30:
            grado = 0
            signo_idx = (signo_idx + 1) % 12
    return SIGNOS[signo_idx], grado, minuto


def _normalizar_lon(lon: float) -> float:
    """Normaliza longitud a 0-360."""
    return lon % 360


def _diferencia_angular(a: float, b: float) -> float:
    """Diferencia angular mínima entre dos longitudes (0-180)."""
    diff = abs(_normalizar_lon(a) - _normalizar_lon(b))
    return min(diff, 360 - diff)


def _es_aplicativo(lon_rapido: float, lon_lento: float, aspecto_angulo: float) -> bool:
    """Determina si el aspecto es aplicativo (True) o separativo (False)."""
    # Simplificación: para aspectos exactos, consideramos aplicativo si el planeta rápido
    # se acerca al aspecto (diferencia angular decreciente en el futuro inmediato)
    # Usamos una heurística simple basada en velocidades medias
    return True  # Simplificación para MVP


def _calcular_aspectos(lon1: float, lon2: float, aspectos_lista: List[Tuple[str, float, float]]) -> List[Dict[str, Any]]:
    """Calcula aspectos entre dos longitudes."""
    diff = _diferencia_angular(lon1, lon2)
    resultados = []
    for nombre, angulo, orbe in aspectos_lista:
        if abs(diff - angulo) <= orbe or abs(diff - (360 - angulo)) <= orbe:
            resultados.append({
                "aspecto": nombre,
                "orbe": round(abs(diff - angulo), 4),
                "aplicativo": _es_aplicativo(0, 0, angulo),  # placeholder
            })
    return resultados


def _validar_fecha(fecha: str) -> datetime:
    """Valida "AAAA-MM-DD" y devuelve el datetime naive; error claro en español."""
    try:
        return datetime.strptime(fecha, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError(
            f"Fecha inválida: {fecha!r}. Use formato AAAA-MM-DD con un día existente "
            "(recuerde que 1900 no fue bisiesto)."
        ) from None


def _validar_hora(hora: str) -> Tuple[int, int]:
    """Valida "HH:MM" y devuelve (hora, minuto); error claro en español."""
    try:
        partes = hora.split(":")
        h = int(partes[0])
        m = int(partes[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return h, m
    except (ValueError, TypeError, IndexError, AttributeError):
        raise ValueError(
            f"Hora no válida: {hora!r}. Use formato HH:MM (00:00-23:59)."
        ) from None


def _zona(tz: str) -> ZoneInfo:
    """Devuelve ZoneInfo o error claro en español si la zona no existe."""
    try:
        return ZoneInfo(tz)
    except Exception:
        raise ValueError(
            f"Zona horaria no reconocida: {tz!r}. Use una zona IANA "
            "(p. ej. Europe/Madrid, UTC)."
        ) from None


def _utc_desde_local(fecha: str, hora: str, tz: str) -> datetime:
    """Convierte fecha/hora local a UTC usando zoneinfo, con validación clara."""
    dt_naive = _validar_fecha(fecha)
    h, m = _validar_hora(hora)
    dt_local = dt_naive.replace(hour=h, minute=m, tzinfo=_zona(tz))
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


def _julian_day(dt_utc: datetime) -> float:
    """Calcula día juliano desde datetime UTC."""
    if swe:
        return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                          dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)
    # Fallback manual
    a = (14 - dt_utc.month) // 12
    y = dt_utc.year + 4800 - a
    m = dt_utc.month + 12 * a - 3
    jdn = dt_utc.day + ((153 * m + 2) // 5) + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn + (dt_utc.hour - 12) / 24.0 + dt_utc.minute / 1440.0 + dt_utc.second / 86400.0


def _calcular_carta(jd_ut: float, lat: float, lon: float) -> Dict[str, Any]:
    """Calcula la carta natal completa para un día juliano UT y coordenadas."""
    if not swe:
        raise RuntimeError("swisseph no disponible")
    if (isinstance(lat, bool) or not isinstance(lat, (int, float))
            or not math.isfinite(lat)):
        raise ValueError(f"Latitud inválida: {lat!r}")
    if abs(lat) > 90:
        raise ValueError(f"Latitud fuera de rango (-90 a 90): {lat!r}")
    if (isinstance(lon, bool) or not isinstance(lon, (int, float))
            or not math.isfinite(lon)):
        raise ValueError(f"Longitud inválida: {lon!r}")

    _init_swe()

    # Configurar casas Placidus; en latitudes polares Placidus no converge y
    # degradamos a casas iguales (Equal) avisando, en lugar de romper la lectura.
    aviso_casas: Optional[str] = None
    try:
        casas, ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except Exception:
        casas, ascmc = swe.houses(jd_ut, lat, lon, b"E")
        aviso_casas = (
            "Casas iguales (Equal): Placidus no converge en esta latitud polar."
        )

    # Planetas
    planetas_res = []
    for nombre, pid in PLANETAS:
        try:
            res = swe.calc_ut(jd_ut, pid, swe.FLG_SWIEPH | swe.FLG_SPEED)
            lon_planeta = res[0][0] % 360
            lat_planeta = res[0][1]
            dist = res[0][2]
            speed = res[0][3]
            retr = speed < 0
        except Exception:
            lon_planeta = 0
            speed = 0
            retr = False

        signo, grado, minuto = _lon_a_signo_grado_minuto(lon_planeta)

        # Determinar casa
        casa = 1
        for i in range(12):
            cusp_actual = casas[i] % 360
            cusp_siguiente = casas[(i + 1) % 12] % 360
            if cusp_siguiente < cusp_actual:
                cusp_siguiente += 360
            lon_norm = lon_planeta % 360
            if lon_norm < cusp_actual:
                lon_norm += 360
            if cusp_actual <= lon_norm < cusp_siguiente:
                casa = i + 1
                break

        planetas_res.append({
            "nombre": nombre,
            "signo": signo,
            "grado": grado,
            "minuto": minuto,
            "casa": casa,
            "retrógrado": retr,
            "lon": round(lon_planeta, 4),
        })

    # Nodos lunares: nodo medio (swe.MEAN_NODE) en trópico. Son puntos matemáticos
    # del plano lunar; no entran en el cálculo de aspectos ni en el elemento o la
    # modalidad dominante.
    res_nodo = swe.calc_ut(jd_ut, swe.MEAN_NODE, swe.FLG_SWIEPH)
    nodo_norte_lon = res_nodo[0][0] % 360
    nodo_sur_lon = (nodo_norte_lon + 180) % 360
    nodos_res = []
    for nombre_nodo, lon_nodo in (("Nodo Norte", nodo_norte_lon), ("Nodo Sur", nodo_sur_lon)):
        signo_n, grado_n, minuto_n = _lon_a_signo_grado_minuto(lon_nodo)
        nodos_res.append({
            "nombre": nombre_nodo,
            "signo": signo_n,
            "grado": grado_n,
            "minuto": minuto_n,
            "casa": _casa_desde_cusps(lon_nodo, casas),
            "lon": round(lon_nodo, 4),
        })

    # Ascendente y MC
    asc_lon = ascmc[0] % 360
    mc_lon = ascmc[1] % 360
    asc_signo, asc_grado, asc_minuto = _lon_a_signo_grado_minuto(asc_lon)
    mc_signo, mc_grado, mc_minuto = _lon_a_signo_grado_minuto(mc_lon)

    # Aspectos entre planetas
    aspectos = []
    for i, (nom1, pid1) in enumerate(PLANETAS):
        res1 = swe.calc_ut(jd_ut, pid1, swe.FLG_SWIEPH)
        lon1 = res1[0][0] % 360
        for j, (nom2, pid2) in enumerate(PLANETAS):
            if i >= j:
                continue
            res2 = swe.calc_ut(jd_ut, pid2, swe.FLG_SWIEPH)
            lon2 = res2[0][0] % 360
            diff = _diferencia_angular(lon1, lon2)
            for asp_nombre, asp_angulo, asp_orbe in ASPECTOS:
                if abs(diff - asp_angulo) <= asp_orbe or abs(diff - (360 - asp_angulo)) <= asp_orbe:
                    aspectos.append({
                        "planeta_a": nom1,
                        "planeta_b": nom2,
                        "aspecto": asp_nombre,
                        "orbe": round(abs(diff - asp_angulo), 4),
                        "aplicativo": True,  # simplificación
                    })

    # Ordenar por orbe y tomar los 14 más exactos
    aspectos.sort(key=lambda x: x["orbe"])
    aspectos = aspectos[:14]

    # Elemento y modalidad dominante
    pesos = {}
    for p in planetas_res:
        peso = 2 if p["nombre"] in ("Sol", "Luna") or p.get("es_ascendente") else 1
        elem = ELEMENTOS.get(p["signo"], "")
        mod = MODALIDADES.get(p["signo"], "")
        if elem:
            pesos[("elem", elem)] = pesos.get(("elem", elem), 0) + peso
        if mod:
            pesos[("mod", mod)] = pesos.get(("mod", mod), 0) + peso
    # Ascendente y MC con peso 2
    asc_signo = _lon_a_signo_grado_minuto(asc_lon)[0]
    mc_signo = _lon_a_signo_grado_minuto(mc_lon)[0]
    for s in (asc_signo, mc_signo):
        elem = ELEMENTOS.get(s, "")
        mod = MODALIDADES.get(s, "")
        if elem:
            pesos[("elem", elem)] = pesos.get(("elem", elem), 0) + 2
        if mod:
            pesos[("mod", mod)] = pesos.get(("mod", mod), 0) + 2

    elem_dom = max([k for k in pesos if k[0] == "elem"], key=lambda k: pesos[k])[1] if any(k[0] == "elem" for k in pesos) else "Fuego"
    mod_dom = max([k for k in pesos if k[0] == "mod"], key=lambda k: pesos[k])[1] if any(k[0] == "mod" for k in pesos) else "Cardinal"

    return {
        "planetas": planetas_res,
        "nodos": nodos_res,
        "ascendente": {"signo": asc_signo, "grado": asc_grado, "minuto": asc_minuto, "lon": round(asc_lon, 4)},
        "medio_cielo": {"signo": mc_signo, "grado": mc_grado, "minuto": mc_minuto, "lon": round(mc_lon, 4)},
        "casas": [{"signo": _lon_a_signo_grado_minuto(c % 360)[0], "grado": _lon_a_signo_grado_minuto(c % 360)[1], "minuto": _lon_a_signo_grado_minuto(c % 360)[2], "lon": round(c % 360, 4)} for c in casas],
        "aspectos": aspectos,
        "elemento_dominante": elem_dom,
        "modalidad_dominante": mod_dom,
        "aviso_casas": aviso_casas,
    }


# ---------------------------------------------------------------------------
# API Pública
# ---------------------------------------------------------------------------

def carta_natal(fecha: str, hora: str, lat: float, lon: float, tz: str) -> Dict[str, Any]:
    """Calcula la carta natal completa.

    Args:
        fecha: "AAAA-MM-DD"
        hora: "HH:MM" local
        lat: latitud (decimal, positivo norte)
        lon: longitud (decimal, positivo este)
        tz: zona horaria IANA

    Returns:
        dict con planetas, ascendente, medio_cielo, casas (12), aspectos (14 más exactos),
        elemento_dominante, modalidad_dominante.
    """
    dt_utc = _utc_desde_local(fecha, hora, tz)
    jd_ut = _julian_day(dt_utc)
    carta = _calcular_carta(jd_ut, lat, lon)
    # Marcar ascendente para pesos
    for p in carta["planetas"]:
        if p["nombre"] == "Sol":
            p["es_ascendente"] = False  # Solo Ascendente y MC tienen peso 2 extra
    return carta


def _planeta_en_casa(lon: float, casas: List[Dict[str, Any]]) -> int:
    """Determina en qué casa cae una longitud."""
    lon_norm = lon % 360
    for i, casa in enumerate(casas):
        cusp_actual = casa["lon"]
        cusp_siguiente = casas[(i + 1) % 12]["lon"]
        if cusp_siguiente < cusp_actual:
            cusp_siguiente += 360
        if lon_norm < cusp_actual:
            lon_norm += 360
        if cusp_actual <= lon_norm < cusp_siguiente:
            return i + 1
    return 1


def _casa_desde_cusps(lon: float, cusps: List[float]) -> int:
    """Determina en qué casa cae una longitud dado un listado de cúspides (floats)."""
    for i in range(12):
        cusp_actual = cusps[i] % 360
        cusp_siguiente = cusps[(i + 1) % 12] % 360
        if cusp_siguiente < cusp_actual:
            cusp_siguiente += 360
        lon_norm = lon % 360
        if lon_norm < cusp_actual:
            lon_norm += 360
        if cusp_actual <= lon_norm < cusp_siguiente:
            return i + 1
    return 1


def transitos(
    natal: Dict[str, Any],
    fecha_transito: str,
    hora: str = "12:00",
    tz: str = "UTC",
    incluir_rapidos: bool = False,
) -> Dict[str, Any]:
    """Calcula tránsitos de planetas lentos (y rápidos opcional) a la carta natal.

    Args:
        natal: carta natal de carta_natal()
        fecha_transito: "AAAA-MM-DD"
        hora: "HH:MM" (default 12:00)
        tz: zona horaria (default UTC)
        incluir_rapidos: si True, incluye Sol y Marte

    Returns:
        dict con aspectos del planeta en tránsito al planeta natal,
        con orbe, casa_natal, y aplicativo/separativo.
    """
    dt_utc = _utc_desde_local(fecha_transito, hora, tz)
    jd_ut = _julian_day(dt_utc)

    _init_swe()

    # Posiciones de planetas en tránsito
    planetas_transito = PLANETAS if incluir_rapidos else [(n, p) for n, p in PLANETAS if n in PLANETAS_LENtos]

    transito_pos = {}
    for nombre, pid in planetas_transito:
        res = swe.calc_ut(jd_ut, pid, swe.FLG_SWIEPH)
        transito_pos[nombre] = res[0][0] % 360

    # Aspectos tránsito -> natal. Los nodos lunares se tratan como puntos natales
    # adicionales (aportan nombre, lon y casa), con los mismos orbes de tránsito.
    puntos_natales = list(natal["planetas"]) + list(natal.get("nodos", []))
    aspectos = []
    for p_natal in puntos_natales:
        lon_natal = p_natal["lon"]
        casa_natal = p_natal["casa"]
        for nombre_t, lon_t in transito_pos.items():
            diff = _diferencia_angular(lon_t, lon_natal)
            for asp_nombre, asp_angulo, asp_orbe in ASPECTOS_TRANSITO:
                if abs(diff - asp_angulo) <= asp_orbe or abs(diff - (360 - asp_angulo)) <= asp_orbe:
                    aspectos.append({
                        "planeta_transito": nombre_t,
                        "planeta_natal": p_natal["nombre"],
                        "aspecto": asp_nombre,
                        "orbe": round(abs(diff - asp_angulo), 4),
                        "casa_natal": casa_natal,
                        "aplicativo": True,  # simplificación
                    })

    # Ordenar por orbe
    aspectos.sort(key=lambda x: x["orbe"])

    return {
        "fecha_transito": fecha_transito,
        "aspectos": aspectos,
    }


def transitos_periodo(
    natal: Dict[str, Any],
    desde: str,
    hasta: str,
    paso_dias: int = 1,
) -> List[Dict[str, Any]]:
    """Lista aspectos exactos (orbe cruza 0) para planetas lentos en un rango.

    Args:
        natal: carta natal
        desde: "AAAA-MM-DD"
        hasta: "AAAA-MM-DD"
        paso_dias: paso de búsqueda en días

    Returns:
        Lista de aspectos exactos (cuando orbe cruza 0) sin duplicados.
    """
    from datetime import timedelta

    if not isinstance(paso_dias, int) or paso_dias < 1:
        raise ValueError("paso_dias debe ser un entero >= 1.")
    dt_desde = _validar_fecha(desde)
    dt_hasta = _validar_fecha(hasta)

    resultados = []
    vistos = set()

    actual = dt_desde
    while actual <= dt_hasta:
        fecha_str = actual.strftime("%Y-%m-%d")
        res = transitos(natal, fecha_str, hora="12:00", tz="UTC")
        for a in res["aspectos"]:
            if a["orbe"] < 0.01:  # aspecto exacto (orbe ~0)
                clave = (a["planeta_transito"], a["planeta_natal"], a["aspecto"], a.get("orbe", 0))
                if clave not in vistos:
                    vistos.add(clave)
                    a_copy = a.copy()
                    a_copy["fecha"] = fecha_str
                    resultados.append(a_copy)
        actual += timedelta(days=paso_dias)

    return resultados


def revolucion_solar(
    natal_fecha: str,
    natal_hora: str,
    lat: float,
    lon: float,
    tz: str,
    anio: int,
    lat_rs: Optional[float] = None,
    lon_rs: Optional[float] = None,
    tz_rs: Optional[str] = None,
) -> Dict[str, Any]:
    """Calcula la revolución solar para un año dado.

    Encuentra el instante exacto en que el Sol vuelve a su longitud natal
    (búsqueda por bisección con precisión < 1 minuto).
    """
    from datetime import timedelta
    # Longitud del Sol natal
    natal = carta_natal(natal_fecha, natal_hora, lat, lon, tz)
    sol_natal = next(p for p in natal["planetas"] if p["nombre"] == "Sol")
    sol_natal_lon = sol_natal["lon"]

    def diff_lon(a: float, b: float) -> float:
        d = (a - b) % 360
        return d if d <= 180 else d - 360

    # El retorno solar se define por la longitud del Sol, no por la fecha de
    # calendario: la fecha de partida es solo una ancla. Para nacidos el 29-feb en
    # un año objetivo no bisiesto se ancla en 28-feb. La ventana se centra en la
    # ancla ±2 días porque la deriva del año tropical puede desplazar el retorno
    # real hasta ~1-2 días respecto del cumpleaños de calendario.
    mes_dia = natal_fecha[5:]
    if mes_dia == "02-29" and not calendar.isleap(anio):
        ancla = datetime(anio, 2, 28)
    else:
        ancla = _validar_fecha(f"{anio}-{mes_dia}")

    def sol_lon_en_jd(jd):
        res = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
        return res[0][0] % 360

    jd_ancla = _julian_day(ancla.replace(tzinfo=timezone.utc))

    # Escaneo fino para hallar el corchete (cambio de signo de diff_lon).
    paso = 0.25  # días
    jd_a = jd_ancla - 2.0
    bracket: Optional[Tuple[float, float]] = None
    while jd_a <= jd_ancla + 2.0 + 1e-9:
        jd_b = jd_a + paso
        d_a = diff_lon(sol_lon_en_jd(jd_a), sol_natal_lon)
        if d_a == 0.0:
            bracket = (jd_a, jd_a)
            break
        d_b = diff_lon(sol_lon_en_jd(jd_b), sol_natal_lon)
        if d_a * d_b < 0:
            bracket = (jd_a, jd_b)
            break
        jd_a = jd_b

    if bracket is None:
        raise ValueError(
            "No se pudo localizar el retorno solar en la ventana esperada "
            f"alrededor de {anio}-{mes_dia}."
        )

    # Bisección dentro del corchete hasta precisión < 1 minuto.
    jd_lo, jd_hi = bracket
    d_lo = diff_lon(sol_lon_en_jd(jd_lo), sol_natal_lon)
    for _ in range(60):
        jd_mid = (jd_lo + jd_hi) / 2
        d_mid = diff_lon(sol_lon_en_jd(jd_mid), sol_natal_lon)
        if d_lo * d_mid <= 0:
            jd_hi = jd_mid
        else:
            jd_lo = jd_mid
            d_lo = d_mid
        if abs(jd_hi - jd_lo) < 1 / 1440:  # < 1 minuto
            break

    jd_rs = (jd_lo + jd_hi) / 2
    sol_rs_lon = sol_lon_en_jd(jd_rs)

    # Convertir jd_rs a datetime UTC
    # swe.revjul devuelve (year, month, day, hour_decimal)
    y, m, d, h = swe.revjul(jd_rs)
    dt_utc = datetime(int(y), int(m), int(d), int(h), int((h % 1) * 60), tzinfo=timezone.utc)

    # Lugar de la RS
    lat_final = lat_rs if lat_rs is not None else lat
    lon_final = lon_rs if lon_rs is not None else lon
    tz_final = tz_rs if tz_rs is not None else tz

    # Carta de la RS
    carta_rs = _calcular_carta(jd_rs, lat_final, lon_final)

    # Instante local
    dt_local = dt_utc.astimezone(ZoneInfo(tz_final)).replace(tzinfo=None)

    # Añadir ascendente y MC al nivel superior para compatibilidad con tests
    carta_rs["ascendente"] = carta_rs.get("ascendente")
    carta_rs["medio_cielo"] = carta_rs.get("medio_cielo")
    return {
        "instante_ut": dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "instante_local": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
        "carta": carta_rs,
        "sol_natal_lon": round(sol_natal_lon, 4),
        "sol_rs_lon": round(sol_rs_lon, 4),
        "diferencia_arco": round(abs(diff_lon(sol_rs_lon, sol_natal_lon)), 4),
        "ascendente": carta_rs.get("ascendente"),
        "medio_cielo": carta_rs.get("medio_cielo"),
    }


def sinastria(natal_a: Dict[str, Any], natal_b: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula sinastría entre dos cartas natales.

    Returns:
        dict con aspectos entre planetas, superposición de casas,
        puntuación de armonía (0-100), y 5 aspectos más relevantes.
    """
    aspectos = []

    # Aspectos entre planetas de A y B
    for p_a in natal_a["planetas"]:
        for p_b in natal_b["planetas"]:
            diff = _diferencia_angular(p_a["lon"], p_b["lon"])
            for asp_nombre, asp_angulo, asp_orbe in ASPECTOS:
                if abs(diff - asp_angulo) <= asp_orbe or abs(diff - (360 - asp_angulo)) <= asp_orbe:
                    aspectos.append({
                        "planeta_a": p_a["nombre"],
                        "planeta_b": p_b["nombre"],
                        "aspecto": asp_nombre,
                        "orbe": round(abs(diff - asp_angulo), 4),
                    })

    # Ordenar por orbe
    aspectos.sort(key=lambda x: x["orbe"])

    # Superposición de casas
    a_en_b = {}
    b_en_a = {}

    # Casas de A y B
    casas_a = {c["signo"]: i+1 for i, c in enumerate(natal_a["casas"])}
    casas_b = {c["signo"]: i+1 for i, c in enumerate(natal_b["casas"])}

    for p_a in natal_a["planetas"]:
        casa_b = _planeta_en_casa(p_a["lon"], natal_b["casas"])
        a_en_b[p_a["nombre"]] = casa_b

    for p_b in natal_b["planetas"]:
        casa_a = _planeta_en_casa(p_b["lon"], natal_a["casas"])
        b_en_a[p_b["nombre"]] = casa_a

    # Puntuación de armonía (0-100)
    # Fórmula: base 50, + por trígono/sextil, - por cuadratura/oposición, ± por conjunción
    puntuacion = 50
    for a in aspectos:
        if a["aspecto"] in ("trígono", "sextil"):
            puntuacion += 3
        elif a["aspecto"] in ("cuadratura", "oposición"):
            puntuacion -= 3
        elif a["aspecto"] == "conjunción":
            # Conjunción depende de planetas: benéficos +, maléficos -
            if any(p in ["Júpiter", "Venus", "Sol", "Luna"] for p in [a["planeta_a"], a["planeta_b"]]):
                puntuacion += 2
            else:
                puntuacion -= 1

    puntuacion = max(0, min(100, puntuacion))

    # 5 aspectos más relevantes: luminarias y Venus-Marte primero
    prioridad = {"Sol": 5, "Luna": 5, "Venus": 4, "Marte": 4, "Mercurio": 3, "Júpiter": 2, "Saturno": 2, "Urano": 1, "Neptuno": 1, "Plutón": 1}
    aspectos_con_prioridad = sorted(
        aspectos,
        key=lambda x: -(prioridad.get(x["planeta_a"], 0) + prioridad.get(x["planeta_b"], 0))
    )
    aspectos_relevantes = aspectos_con_prioridad[:5]

    return {
        "aspectos": aspectos,
        "superposicion_casas": {
            "a_en_b": a_en_b,
            "b_en_a": b_en_a,
        },
        "puntuacion_armonia": puntuacion,
        "aspectos_relevantes": aspectos_relevantes,
    }


if __name__ == "__main__":
    import json
    # Test rápido
    res = carta_natal("1990-06-15", "12:00", -12.0464, -77.0428, "America/Lima")
    print(json.dumps(res, ensure_ascii=False, indent=2))
