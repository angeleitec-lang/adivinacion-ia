"""Matriz de cobertura del alcance (ola activa).

Calcula, para cada celda *entidad × faceta*, cuántas fuentes independientes de
calidad la respaldan. La entrada es un fichero de evidencias ya etiquetadas (el
juez LLM produce las etiquetas en otra pista); aquí solo se cuenta y se informa.

Las convenciones de `entidad_id` reutilizan las de `web_rejillas.py`:
`planeta|signo|planeta_en_signo`, `planeta|casaN|planeta_en_casa` y
`p1|aspecto|p2|aspecto` (pares sin repetición, i < j).
"""
import cartas

# ---------------------------------------------------------------------------
# Catálogos canónicos (estables; coinciden con knowledge/rejillas_astrologia.json)
# ---------------------------------------------------------------------------

SIGNOS = ["aries", "tauro", "geminis", "cancer", "leo", "virgo",
          "libra", "escorpio", "sagitario", "capricornio", "acuario", "piscis"]

PLANETAS = ["sol", "luna", "mercurio", "venus", "marte",
            "jupiter", "saturno", "urano", "neptuno", "pluton"]

CASAS = list(range(1, 13))

ASPECTOS = ["conjuncion", "sextil", "cuadratura", "trigono", "oposicion"]

NUMEROS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 22, 33]

POSICIONES = ["camino_de_vida", "destino", "alma", "personalidad",
              "anio_personal", "mes_personal"]

_NOMBRE_POSICION = {
    "camino_de_vida": "Camino de vida",
    "destino": "Destino",
    "alma": "Alma",
    "personalidad": "Personalidad",
    "anio_personal": "Año personal",
    "mes_personal": "Mes personal",
}

# ---------------------------------------------------------------------------
# Facetas por familia
# ---------------------------------------------------------------------------

# Facetas comunes a todas las familias (sin orientación de naipes).
_FACETAS_BASE = [
    "significado_general",
    "luz_sombra",
    "amor",
    "trabajo",
    "dinero",
    "salud",
    "espiritual",
    "simbolismo",
    "correspondencias",
    "consejo_practico",
    "ejemplo_de_uso",
]

# Tarot y baraja añaden la orientación derecha/invertida.
FACETAS_POR_FAMILIA = {
    "tarot": ["significado_general", "luz_sombra", "derecha_invertida",
              "amor", "trabajo", "dinero", "salud", "espiritual",
              "simbolismo", "correspondencias", "consejo_practico",
              "ejemplo_de_uso"],
    "baraja_espanola": ["significado_general", "luz_sombra", "derecha_invertida",
                        "amor", "trabajo", "dinero", "salud", "espiritual",
                        "simbolismo", "correspondencias", "consejo_practico",
                        "ejemplo_de_uso"],
    "astrologia": list(_FACETAS_BASE),
    "numerologia": list(_FACETAS_BASE),
}


def _capital(slug):
    """Nombre legible desde el slug canónico en minúsculas."""
    return slug.capitalize()


def entidades():
    """Lista de entidades de la ola activa.

    Cada entidad: {"entidad_id", "familia", "subtipo", "nombre"}.
    """
    ent = []
    for carta in cartas.CARTAS_TAROT:
        ent.append({
            "entidad_id": carta["id"],
            "familia": "tarot",
            "subtipo": "carta_tarot",
            "nombre": carta["nombre"],
        })
    for naipe in cartas.NAIPES_ESPANOLES:
        ent.append({
            "entidad_id": naipe["id"],
            "familia": "baraja_espanola",
            "subtipo": "naipe_espanol",
            "nombre": naipe["nombre"],
        })
    for signo in SIGNOS:
        ent.append({
            "entidad_id": f"{signo}|signo",
            "familia": "astrologia",
            "subtipo": "signo",
            "nombre": _capital(signo),
        })
    for planeta in PLANETAS:
        for signo in SIGNOS:
            ent.append({
                "entidad_id": f"{planeta}|{signo}|planeta_en_signo",
                "familia": "astrologia",
                "subtipo": "planeta_en_signo",
                "nombre": f"{_capital(planeta)} en {_capital(signo)}",
            })
    for planeta in PLANETAS:
        for casa in CASAS:
            ent.append({
                "entidad_id": f"{planeta}|casa{casa}|planeta_en_casa",
                "familia": "astrologia",
                "subtipo": "planeta_en_casa",
                "nombre": f"{_capital(planeta)} en casa {casa}",
            })
    for i in range(len(PLANETAS)):
        for j in range(i + 1, len(PLANETAS)):
            p1, p2 = PLANETAS[i], PLANETAS[j]
            for aspecto in ASPECTOS:
                ent.append({
                    "entidad_id": f"{p1}|{aspecto}|{p2}|aspecto",
                    "familia": "astrologia",
                    "subtipo": "aspecto",
                    "nombre": f"{_capital(p1)} {aspecto} {_capital(p2)}",
                })
    for numero in NUMEROS:
        for posicion in POSICIONES:
            ent.append({
                "entidad_id": f"{numero}|{posicion}",
                "familia": "numerologia",
                "subtipo": "numero_posicion",
                "nombre": f"{_NOMBRE_POSICION[posicion]} {numero}",
            })
    return ent
