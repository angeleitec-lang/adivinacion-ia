"""Matriz de cobertura del alcance (ola activa).

Calcula, para cada celda *entidad × faceta*, cuántas fuentes independientes de
calidad la respaldan. La entrada es un fichero de evidencias ya etiquetadas (el
juez LLM produce las etiquetas en otra pista); aquí solo se cuenta y se informa.

Las convenciones de `entidad_id` reutilizan las de `web_rejillas.py`:
`planeta|signo|planeta_en_signo`, `planeta|casaN|planeta_en_casa` y
`p1|aspecto|p2|aspecto` (pares sin repetición, i < j).
"""
import argparse
import json
import os
import sys

import cartas

_NOMBRE_FAMILIA = {
    "tarot": "Tarot",
    "baraja_espanola": "Baraja española",
    "astrologia": "Astrología",
    "numerologia": "Numerología",
}

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


# ---------------------------------------------------------------------------
# Lectura de evidencias y resumen
# ---------------------------------------------------------------------------

def leer_evidencias(rutas):
    """Lee ficheros JSONL de evidencias. Devuelve (evidencias, ignoradas).

    Las líneas vacías se omiten; las que no son JSON válido (o no son objetos)
    se cuentan como ignoradas. Los ficheros inexistentes se saltan sin error.
    """
    evidencias = []
    ignoradas = 0
    for ruta in rutas:
        try:
            archivo = open(ruta, encoding="utf-8")
        except FileNotFoundError:
            continue
        with archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    ev = json.loads(linea)
                except json.JSONDecodeError:
                    ignoradas += 1
                    continue
                if not isinstance(ev, dict):
                    ignoradas += 1
                    continue
                evidencias.append(ev)
    return evidencias, ignoradas


def resumen_por_familia(resultado, catalogo=None):
    """Celdas, completas y porcentaje por familia (con nombre legible)."""
    if catalogo is None:
        catalogo = entidades()
    familia_de = {e["entidad_id"]: e["familia"] for e in catalogo}
    acumulado = {}
    for celda in resultado["celdas"]:
        familia = familia_de.get(celda["entidad_id"])
        datos = acumulado.setdefault(familia, {"celdas": 0, "completas": 0})
        datos["celdas"] += 1
        if celda["completa"]:
            datos["completas"] += 1
    for datos in acumulado.values():
        if datos["celdas"]:
            datos["porcentaje"] = round(100.0 * datos["completas"] / datos["celdas"], 1)
        else:
            datos["porcentaje"] = 0.0
    return {_NOMBRE_FAMILIA.get(f, f): d for f, d in acumulado.items()}


def _porcentaje_es(valor):
    return f"{valor:.1f}".replace(".", ",") + " %"


# ---------------------------------------------------------------------------
# Salida en disco
# ---------------------------------------------------------------------------

def ordenar_por_carencia(celdas, minimo_fuentes=5, minimo_clasicas=1,
                        minimo_modernas=2, minimo_es=1):
    """Ordena las celdas de mayor a menor carencia (desempate por id y faceta)."""
    def clave(celda):
        carencia = (
            max(0, minimo_fuentes - celda["n_fuentes"])
            + max(0, minimo_clasicas - celda["n_clasicas"])
            + max(0, minimo_modernas - celda["n_modernas"])
            + max(0, minimo_es - celda["n_es"])
        )
        return (-carencia, celda["entidad_id"], celda["faceta"])
    return sorted(celdas, key=clave)


def escribir_json(resultado, ruta, resumen=None, catalogo=None):
    """Vuelca la matriz completa y el resumen a cobertura.json (UTF-8)."""
    if resumen is None:
        resumen = resumen_por_familia(resultado, catalogo)
    datos = {
        "resumen": {
            "total_celdas": len(resultado["celdas"]),
            "completas": resultado["completas"],
            "ignoradas": resultado["ignoradas"],
            "por_familia": resumen,
        },
        "celdas": resultado["celdas"],
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.write("\n")


def escribir_md(resultado, ruta, max_huecos=200, resumen=None, catalogo=None):
    """Informe en markdown: resumen por familia y celdas bajo el mínimo."""
    if resumen is None:
        resumen = resumen_por_familia(resultado, catalogo)
    total = len(resultado["celdas"])
    completas = resultado["completas"]
    pct = round(100.0 * completas / total, 1) if total else 0.0
    lineas = [
        "# Matriz de cobertura",
        "",
        f"- Total de celdas: {total}",
        f"- Celdas completas: {completas} ({_porcentaje_es(pct)})",
        f"- Evidencias ignoradas: {resultado['ignoradas']}",
        "",
        "## Resumen por familia",
        "",
        "| Familia | Celdas | Completas | % completas |",
        "|---|---|---|---|",
    ]
    for nombre, datos in resumen.items():
        lineas.append(
            f"| {nombre} | {datos['celdas']} | {datos['completas']} "
            f"| {_porcentaje_es(datos['porcentaje'])} |"
        )
    huecos = [c for c in resultado["celdas"] if not c["completa"]]
    huecos = ordenar_por_carencia(huecos)
    lineas += [
        "",
        "## Celdas bajo el mínimo (ordenadas por mayor carencia)",
        "",
    ]
    for celda in huecos[:max_huecos]:
        lineas.append(
            f"- `{celda['entidad_id']}` · {celda['faceta']}: "
            + "; ".join(celda["faltan"])
        )
    restantes = len(huecos) - max_huecos
    if restantes > 0:
        lineas.append("")
        lineas.append(f"Y {restantes} celdas más bajo el mínimo.")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def huecos_para_rastreo(resultado):
    """Lista de huecos para las pistas de rastreo, ordenada por mayor carencia.

    Cada elemento: {"entidad_id", "faceta", "faltan"}.
    """
    huecos = [c for c in resultado["celdas"] if not c["completa"]]
    return [
        {"entidad_id": c["entidad_id"], "faceta": c["faceta"], "faltan": c["faltan"]}
        for c in ordenar_por_carencia(huecos)
    ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Calcula la matriz de cobertura a partir de evidencias etiquetadas.")
    parser.add_argument("--evidencias", nargs="+", required=True,
                       help="uno o varios ficheros JSONL de evidencias")
    parser.add_argument("--out-json", default="cobertura.json",
                       help="ruta de salida del JSON (por defecto: cobertura.json)")
    parser.add_argument("--out-md", default="cobertura.md",
                       help="ruta de salida del informe (por defecto: cobertura.md)")
    parser.add_argument("--calidad-min", type=int, default=3,
                       help="calidad mínima para contar una evidencia (por defecto: 3)")
    parser.add_argument("--max-huecos", type=int, default=200,
                       help="máximo de celdas listadas en el informe (por defecto: 200)")
    parser.add_argument("--dry-run", action="store_true",
                       help="imprime el resumen y no escribe ficheros")
    args = parser.parse_args(argv)

    evidencias, malas = leer_evidencias(args.evidencias)
    catalogo = entidades()
    resultado = calcular_cobertura(evidencias, catalogo=catalogo,
                                  calidad_min=args.calidad_min)
    resultado["ignoradas"] += malas
    resumen = resumen_por_familia(resultado, catalogo)
    if args.dry_run:
        total = len(resultado["celdas"])
        print(f"Cobertura (simulación): {resultado['completas']} de {total} "
              f"celdas completas; evidencias ignoradas: {resultado['ignoradas']}")
        for nombre, datos in resumen.items():
            print(f"  {nombre}: {datos['completas']}/{datos['celdas']} completas "
                  f"({_porcentaje_es(datos['porcentaje'])})")
        return 0
    escribir_json(resultado, args.out_json, resumen)
    escribir_md(resultado, args.out_md, max_huecos=args.max_huecos, resumen=resumen)
    print(f"Cobertura escrita en {args.out_json} y {args.out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
