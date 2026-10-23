"""T137 — Propuesta de catalogo astrológico ampliado (casa-N, elemento, modalidad).

Propuesta SIN APLICAR: inventaria el catalogo actual de astrologia
(``cobertura.entidades()``), las afirmaciones de T119 (Arroyo + Sasportas,
723) y calcula en una COPIA la cobertura hipotetica de anadir 19 entidades
nuevas (12 casas, 4 elementos, 3 modalidades). No escribe en el catalogo
compartido, ni en ``kb/*.json``, ni en la matriz v3 real: todo el trabajo va a
``/Users/angelgonzalez/fase0/catalogo_astro_propuesta/``.

Remapeo determinista (sin LLM) de las afirmaciones existentes de T119:

- R1 ``casa``: una afirmacion ``p|casaN|planeta_en_casa`` es evidencia
  (indirecta, via el planeta) de ``casaN|casa``. Casa fuera de 1..12 se rechaza.
- R2 ``elemento``: una afirmacion de ``signo`` o ``planeta_en_signo`` lleva
  asociado el elemento del signo (mapeo canonico, coincide con
  ``kb/astrologia.json``) → ``{el}|elemento``.
- R3 ``modalidad``: igual que R2 con la modalidad del signo → ``{mod}|modalidad``.
- Los ``aspecto`` no se remapean (no llevan informacion de casa).

El remapeo es estructural (desde el ``entidad_id``), no por palabras clave del
texto: es reproducible y sin falsos positivos lexicos ("agua" literal, "comun"
como adverbio). La calidad de la evidencia remapeada es INDIRECTA y queda
documentada en ``docs/PROPUESTA_CATALOGO_ASTRO.md``.
"""
import argparse
import json
import os
import re
import sys
import unicodedata

import cobertura

AFIRMACIONES_T119 = (
    "/Users/angelgonzalez/fase0/libros_comprados_astro/afirmaciones/"
    "afirmaciones_astro.jsonl"
)
V3_OFICIAL = "/Users/angelgonzalez/fase0/cobertura_v3/cobertura_total_v3.json"
WORK_DIR = "/Users/angelgonzalez/fase0/catalogo_astro_propuesta"

RUTAS_PROTEGIDAS = (
    "/Users/angelgonzalez/fase0/cobertura_v3",
    "/Users/angelgonzalez/fase0/libros",
    "/Users/angelgonzalez/fase0/evidencias_web",
    "/Users/angelgonzalez/fase0/libros_comprados_astro",
)

SIGNO_ELEMENTO = {
    "aries": "fuego", "leo": "fuego", "sagitario": "fuego",
    "tauro": "tierra", "virgo": "tierra", "capricornio": "tierra",
    "geminis": "aire", "libra": "aire", "acuario": "aire",
    "cancer": "agua", "escorpio": "agua", "piscis": "agua",
}

SIGNO_MODALIDAD = {
    "aries": "cardinal", "cancer": "cardinal",
    "libra": "cardinal", "capricornio": "cardinal",
    "tauro": "fijo", "leo": "fijo", "escorpio": "fijo", "acuario": "fijo",
    "geminis": "variable", "virgo": "variable",
    "sagitario": "variable", "piscis": "variable",
}

ELEMENTOS = ("fuego", "tierra", "aire", "agua")
MODALIDADES = ("cardinal", "fijo", "variable")
CASAS = tuple(range(1, 13))

_RE_CASA_TOKEN = re.compile(r"^casa(\d+)$")

_NOMBRE_CASA = {
    1: "Casa 1", 2: "Casa 2", 3: "Casa 3", 4: "Casa 4",
    5: "Casa 5", 6: "Casa 6", 7: "Casa 7", 8: "Casa 8",
    9: "Casa 9", 10: "Casa 10", 11: "Casa 11", 12: "Casa 12",
}


def _norm(texto):
    """Minusculas sin tildes para comparaciones deterministas."""
    return (unicodedata.normalize("NFD", str(texto))
            .replace("\u0300", "").replace("\u0301", "")
            .replace("\u0302", "").replace("\u0303", "")
            .replace("\u0308", "").lower())


def entidades_propuestas():
    """Las 19 entidades nuevas propuestas, en formato de catalogo de cobertura."""
    ent = []
    for casa in CASAS:
        ent.append({
            "entidad_id": "casa%d|casa" % casa,
            "familia": "astrologia",
            "subtipo": "casa",
            "nombre": _NOMBRE_CASA[casa],
        })
    for elemento in ELEMENTOS:
        ent.append({
            "entidad_id": "%s|elemento" % elemento,
            "familia": "astrologia",
            "subtipo": "elemento",
            "nombre": "Elemento %s" % elemento,
        })
    for modalidad in MODALIDADES:
        ent.append({
            "entidad_id": "%s|modalidad" % modalidad,
            "familia": "astrologia",
            "subtipo": "modalidad",
            "nombre": "Modalidad %s" % modalidad,
        })
    return ent


def ids_propuestos():
    """Conjunto de entidad_id nuevos (para detecciones y colisiones)."""
    return {e["entidad_id"] for e in entidades_propuestas()}


def parsear_entidad_id(entidad_id):
    """Clasifica un entidad_id de astrologia en (tipo, partes).

    Tipos: ``signo``, ``planeta_en_signo``, ``planeta_en_casa`` (con numero
    entero en partes[1]), ``aspecto`` o ``desconocido``. Nunca lanza.
    """
    if not entidad_id or not isinstance(entidad_id, str):
        return "desconocido", []
    partes = entidad_id.split("|")
    if len(partes) == 2 and partes[1] == "signo":
        return "signo", partes
    if len(partes) == 3 and partes[2] == "planeta_en_signo":
        return "planeta_en_signo", partes
    if len(partes) == 3 and partes[2] == "planeta_en_casa":
        m = _RE_CASA_TOKEN.match(partes[1])
        if m:
            return "planeta_en_casa", [partes[0], int(m.group(1))]
        return "desconocido", partes
    if len(partes) == 4 and partes[3] == "aspecto":
        return "aspecto", partes
    return "desconocido", partes


def remapear_afirmacion(afirmacion):
    """Remapeo determinista de una afirmacion T119 a ids nuevos propuestos.

    Devuelve una lista (posiblemente vacia) de dicts
    ``{"entidad_id": ..., "regla": ...}``. No remapea: ids desconocidos,
    casas fuera de 1..12, signos que no estan en el mapeo canonico
    (ambiguos o inexistentes) y aspectos.
    """
    if not isinstance(afirmacion, dict):
        return []
    tipo, partes = parsear_entidad_id(afirmacion.get("entidad_id"))
    planetas_validos = set(cobertura.PLANETAS)
    if tipo == "planeta_en_casa":
        planeta, casa = partes[0], partes[1]
        if planeta in planetas_validos and casa in CASAS:
            return [{"entidad_id": "casa%d|casa" % casa,
                     "regla": "casa_desde_planeta_en_casa"}]
        return []
    if tipo == "signo":
        signo = partes[0]
    elif tipo == "planeta_en_signo":
        if partes[0] not in planetas_validos:
            return []
        signo = partes[1]
    else:
        return []
    if signo not in SIGNO_ELEMENTO or signo not in SIGNO_MODALIDAD:
        return []
    return [
        {"entidad_id": "%s|elemento" % SIGNO_ELEMENTO[signo],
         "regla": "elemento_desde_signo"},
        {"entidad_id": "%s|modalidad" % SIGNO_MODALIDAD[signo],
         "regla": "modalidad_desde_signo"},
    ]


def evidencias_remapeadas(afirmaciones):
    """Convierte el remapeo en evidencias para ``cobertura.calcular_cobertura``.

    Las afirmaciones de T119 son modernas y en ingles (original del libro);
    la afirmacion derivada esta en espanol pero la fuente es anglosajona,
    asi que ``idioma`` se fija en ``en`` como en la evidencia original.
    """
    evidencias = []
    for claim in afirmaciones:
        if not isinstance(claim, dict):
            continue
        faceta = claim.get("faceta")
        if not faceta:
            continue
        for nuevo in remapear_afirmacion(claim):
            evidencias.append({
                "entidad_id": nuevo["entidad_id"],
                "faceta": faceta,
                "fuente_id": claim.get("fuente_id"),
                "dominio": claim.get("dominio"),
                "periodo": claim.get("periodo", "moderna"),
                "idioma": "en",
                "tipo": "libro",
                "calidad": claim.get("calidad", 0),
                "regla": nuevo["regla"],
            })
    return evidencias


def _subtipo_astro(entidad_id):
    tipo, _ = parsear_entidad_id(entidad_id)
    return tipo


def inventario_actual(ruta_v3=V3_OFICIAL):
    """Inventario del catalogo astro actual y su cobertura v3 oficial."""
    catalogo = cobertura.entidades()
    por_subtipo = {}
    for e in catalogo:
        if e["familia"] != "astrologia":
            continue
        st = _subtipo_astro(e["entidad_id"])
        por_subtipo[st] = por_subtipo.get(st, 0) + 1
    facetas = cobertura.FACETAS_POR_FAMILIA["astrologia"]
    resultado = {"entidades_por_subtipo": por_subtipo,
                 "facetas": list(facetas),
                 "total_entidades_astro": sum(por_subtipo.values()),
                 "total_celdas_astro": sum(por_subtipo.values()) * len(facetas)}
    try:
        with open(ruta_v3, encoding="utf-8") as fh:
            v3 = json.load(fh)
    except (OSError, json.JSONDecodeError):
        resultado["cobertura_v3"] = None
        return resultado
    cob = {}
    for celda in v3.get("celdas", []):
        st = _subtipo_astro(celda["entidad_id"])
        if st not in por_subtipo:
            continue
        d = cob.setdefault(st, {"celdas": 0, "completas": 0})
        d["celdas"] += 1
        if celda.get("completa"):
            d["completas"] += 1
    resultado["cobertura_v3"] = cob
    return resultado


def cobertura_hipotetica(afirmaciones, calidad_min=3):
    """Cobertura hipotetica de las 19 entidades nuevas con el remapeo T119.

    No toca la matriz real: se calcula en memoria sobre un catalogo
    extendido y solo se informan las celdas nuevas.
    """
    catalogo = cobertura.entidades() + entidades_propuestas()
    evidencias = evidencias_remapeadas(afirmaciones)
    res = cobertura.calcular_cobertura(evidencias, catalogo=catalogo,
                                      calidad_min=calidad_min)
    nuevos = ids_propuestos()
    celdas_nuevas = [c for c in res["celdas"] if c["entidad_id"] in nuevos]
    por_subtipo = {}
    for celda in celdas_nuevas:
        st = celda["entidad_id"].split("|")[1]
        d = por_subtipo.setdefault(st, {"celdas": 0, "con_fuente": 0,
                                       "con_dos_fuentes": 0, "completas": 0})
        d["celdas"] += 1
        if celda["n_fuentes"] >= 1:
            d["con_fuente"] += 1
        if celda["n_fuentes"] >= 2:
            d["con_dos_fuentes"] += 1
        if celda["completa"]:
            d["completas"] += 1
    resumen = {
        "celdas_nuevas": len(celdas_nuevas),
        "con_fuente": sum(d["con_fuente"] for d in por_subtipo.values()),
        "con_dos_fuentes": sum(d["con_dos_fuentes"]
                               for d in por_subtipo.values()),
        "completas": sum(d["completas"] for d in por_subtipo.values()),
        "por_subtipo": por_subtipo,
        "evidencias_remapeadas": len(evidencias),
        "calidad_min": calidad_min,
    }
    return {"resumen": resumen, "celdas_nuevas": celdas_nuevas}


def estadisticas_remapeo(afirmaciones):
    """Cuentas del remapeo por regla y por patron de origen."""
    por_regla = {}
    por_origen = {}
    sin_remapeo = 0
    for claim in afirmaciones:
        nuevos = remapear_afirmacion(claim) if isinstance(claim, dict) else []
        tipo, _ = parsear_entidad_id(
            claim.get("entidad_id") if isinstance(claim, dict) else None)
        if not nuevos:
            sin_remapeo += 1
            por_origen[tipo] = por_origen.get(tipo, 0) + 1
            continue
        for n in nuevos:
            por_regla[n["regla"]] = por_regla.get(n["regla"], 0) + 1
        por_origen.setdefault(tipo, 0)
    return {"por_regla": por_regla,
            "sin_remapeo_por_origen": por_origen,
            "sin_remapeo": sin_remapeo,
            "total_afirmaciones": len(afirmaciones)}


def _guardar_json(objeto, ruta):
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(objeto, fh, ensure_ascii=False, indent=2)


def _guardar_jsonl(filas, ruta):
    with open(ruta, "w", encoding="utf-8") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")


def _escribir_informe(ruta, inventario, remapeo, hipotetica):
    lineas = ["# Informe de cobertura hipotetica — catalogo astro ampliado (T137)", ""]
    lineas.append("## Catalogo actual (astrologia)")
    lineas.append("")
    lineas.append("| Subtipo | Entidades | Celdas (x%d facetas) | Completas v3 |"
                 % len(inventario["facetas"]))
    lineas.append("|---|---|---|---|")
    cob = inventario.get("cobertura_v3") or {}
    for st, n in sorted(inventario["entidades_por_subtipo"].items()):
        c = cob.get(st, {})
        lineas.append("| %s | %d | %d | %s |" % (
            st, n, n * len(inventario["facetas"]),
            c.get("completas", "n/d")))
    lineas.append("| TOTAL | %d | %d | %s |" % (
        inventario["total_entidades_astro"], inventario["total_celdas_astro"],
        sum(c.get("completas", 0) for c in cob.values()) if cob else "n/d"))
    lineas.append("")
    lineas.append("## Remapeo de las 723 afirmaciones T119")
    lineas.append("")
    lineas.append("- Total afirmaciones: %d" % remapeo["total_afirmaciones"])
    for regla, n in sorted(remapeo["por_regla"].items()):
        lineas.append("- Regla `%s`: %d remapeos" % (regla, n))
    lineas.append("- Sin remapeo: %d (por patron de origen: %s)" % (
        remapeo["sin_remapeo"],
        ", ".join("%s=%d" % kv for kv in sorted(
            remapeo["sin_remapeo_por_origen"].items()))))
    lineas.append("")
    lineas.append("## Cobertura hipotetica de las 19 entidades nuevas")
    lineas.append("")
    r = hipotetica["resumen"]
    lineas.append("- Celdas nuevas: %d (19 entidades x %d facetas)" % (
        r["celdas_nuevas"], len(cobertura.FACETAS_POR_FAMILIA["astrologia"])))
    lineas.append("- Con al menos 1 fuente (remapeo T119): %d" % r["con_fuente"])
    lineas.append("- Con 2 fuentes: %d" % r["con_dos_fuentes"])
    lineas.append("- Completas: %d (los libros son modernos y en ingles; una "
                  "celda completa exige ademas 1 clasica y 1 en espanol)"
                  % r["completas"])
    lineas.append("")
    lineas.append("| Subtipo nuevo | Celdas | Con fuente | Con 2 fuentes | Completas |")
    lineas.append("|---|---|---|---|---|")
    for st, d in sorted(r["por_subtipo"].items()):
        lineas.append("| %s | %d | %d | %d | %d |" % (
            st, d["celdas"], d["con_fuente"], d["con_dos_fuentes"],
            d["completas"]))
    lineas.append("")
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas))


def ejecutar(work_dir=WORK_DIR, ruta_afirmaciones=AFIRMACIONES_T119,
            ruta_v3=V3_OFICIAL, calidad_min=3):
    """Ejecuta inventario + remapeo + cobertura hipotetica y escribe la COPIA.

    Todos los artefactos van a ``work_dir`` (nuevo). Se niega a escribir en
    rutas protegidas de la tuberia real.
    """
    destino = os.path.abspath(work_dir)
    for protegida in RUTAS_PROTEGIDAS:
        if destino == os.path.abspath(protegida) or destino.startswith(
                os.path.abspath(protegida) + os.sep):
            raise ValueError(
                "work_dir %r cae dentro de una ruta protegida (%s)"
                % (work_dir, protegida))
    os.makedirs(destino, exist_ok=True)

    afirmaciones = []
    with open(ruta_afirmaciones, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                afirmaciones.append(json.loads(linea))

    _guardar_jsonl(afirmaciones,
                  os.path.join(destino, "afirmaciones_origen.jsonl"))

    inventario = inventario_actual(ruta_v3)
    remapeo = estadisticas_remapeo(afirmaciones)
    hipotetica = cobertura_hipotetica(afirmaciones, calidad_min=calidad_min)

    registro = []
    for claim in afirmaciones:
        nuevos = remapear_afirmacion(claim)
        registro.append({
            "entidad_id_origen": claim.get("entidad_id"),
            "faceta": claim.get("faceta"),
            "fuente_id": claim.get("fuente_id"),
            "nuevos": [n["entidad_id"] for n in nuevos],
            "reglas": [n["regla"] for n in nuevos],
        })
    _guardar_jsonl(registro, os.path.join(destino, "remapeo.jsonl"))
    _guardar_json(hipotetica, os.path.join(destino, "cobertura_hipotetica.json"))
    _guardar_json({"inventario_actual": inventario, "remapeo": remapeo},
                 os.path.join(destino, "inventario_y_remapeo.json"))
    _escribir_informe(os.path.join(destino, "informe.md"),
                      inventario, remapeo, hipotetica)
    return {"inventario": inventario, "remapeo": remapeo,
            "hipotetica": hipotetica["resumen"], "work_dir": destino}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Propuesta de catalogo astro ampliado (T137, sin LLM)")
    parser.add_argument("--work-dir", default=WORK_DIR)
    parser.add_argument("--afirmaciones", default=AFIRMACIONES_T119)
    parser.add_argument("--v3", default=V3_OFICIAL)
    parser.add_argument("--calidad-min", type=int, default=3)
    args = parser.parse_args(argv)
    resultado = ejecutar(work_dir=args.work_dir,
                        ruta_afirmaciones=args.afirmaciones,
                        ruta_v3=args.v3, calidad_min=args.calidad_min)
    r = resultado["hipotetica"]
    print("Celdas nuevas: %d | con fuente: %d | con 2 fuentes: %d | "
          "completas: %d" % (r["celdas_nuevas"], r["con_fuente"],
                             r["con_dos_fuentes"], r["completas"]))
    print("Remapeos por regla: %s" % json.dumps(resultado["remapeo"]["por_regla"]))
    print("Artefactos en: %s" % resultado["work_dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
