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


# ---------------------------------------------------------------------------
# Cálculo de celdas a partir de evidencias etiquetadas
# ---------------------------------------------------------------------------

def _plural(n, singular, plural):
    return f"falta {n} {singular}" if n == 1 else f"faltan {n} {plural}"


def _carencias(n_fuentes, n_clasicas, n_modernas, n_es,
              minimo_fuentes, minimo_clasicas, minimo_modernas, minimo_es):
    faltan = []
    if n_fuentes < minimo_fuentes:
        faltan.append(_plural(minimo_fuentes - n_fuentes,
                             "fuente independiente", "fuentes independientes"))
    if n_clasicas < minimo_clasicas:
        faltan.append(_plural(minimo_clasicas - n_clasicas,
                             "fuente clásica", "fuentes clásicas"))
    if n_modernas < minimo_modernas:
        faltan.append(_plural(minimo_modernas - n_modernas,
                             "fuente moderna", "fuentes modernas"))
    if n_es < minimo_es:
        faltan.append(_plural(minimo_es - n_es,
                             "fuente en español", "fuentes en español"))
    return faltan


def _fuentes_independientes(evidencias):
    """Deduplica por fuente_id y, entre las web, por dominio.

    La primera evidencia de cada fuente fija sus atributos (periodo, idioma).
    """
    vistas_fuente = set()
    dominios_web = set()
    unicas = []
    for ev in evidencias:
        fuente = ev.get("fuente_id")
        if not fuente or fuente in vistas_fuente:
            continue
        vistas_fuente.add(fuente)
        if ev.get("tipo") == "web":
            dominio = ev.get("dominio")
            if dominio and dominio in dominios_web:
                continue
            if dominio:
                dominios_web.add(dominio)
        unicas.append(ev)
    return unicas


def calcular_cobertura(evidencias, catalogo=None, calidad_min=3,
                       minimo_fuentes=5, minimo_clasicas=1, minimo_modernas=2,
                       minimo_es=1):
    """Calcula la matriz completa de cobertura.

    `evidencias`: iterable de dicts con entidad_id, faceta, fuente_id, dominio,
    idioma, periodo, calidad y tipo. Las evidencias de entidad o faceta
    desconocidas se ignoran y se cuentan en `ignoradas`.

    Devuelve {"celdas": [...], "completas": n, "ignoradas": n}, con una celda
    por cada combinación entidad × faceta del catálogo.
    """
    if catalogo is None:
        catalogo = entidades()
    validas = {}
    for e in catalogo:
        for faceta in FACETAS_POR_FAMILIA[e["familia"]]:
            validas.setdefault((e["entidad_id"], faceta), []).append(None)

    por_celda = {}
    ignoradas = 0
    for ev in evidencias:
        clave = (ev.get("entidad_id"), ev.get("faceta"))
        if clave not in validas:
            ignoradas += 1
            continue
        try:
            calidad = int(ev.get("calidad", 0))
        except (TypeError, ValueError):
            calidad = 0
        if calidad < calidad_min:
            continue
        por_celda.setdefault(clave, []).append(ev)

    celdas = []
    completas = 0
    for (entidad_id, faceta) in validas:
        fuentes = _fuentes_independientes(por_celda.get((entidad_id, faceta), []))
        n_fuentes = len(fuentes)
        n_clasicas = sum(1 for f in fuentes if f.get("periodo") == "clasica")
        n_modernas = sum(1 for f in fuentes if f.get("periodo") == "moderna")
        n_es = sum(1 for f in fuentes if f.get("idioma") == "es")
        faltan = _carencias(n_fuentes, n_clasicas, n_modernas, n_es,
                           minimo_fuentes, minimo_clasicas, minimo_modernas,
                           minimo_es)
        completa = not faltan
        if completa:
            completas += 1
        celdas.append({
            "entidad_id": entidad_id,
            "faceta": faceta,
            "n_fuentes": n_fuentes,
            "n_clasicas": n_clasicas,
            "n_modernas": n_modernas,
            "n_es": n_es,
            "completa": completa,
            "faltan": faltan,
        })
    return {"celdas": celdas, "completas": completas, "ignoradas": ignoradas}
