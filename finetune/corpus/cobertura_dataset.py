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
import re

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


# ---------------------------------------------------------------------------
# Astrología: signos, planetas y casas (T15.3)
# ---------------------------------------------------------------------------

# (id, etiqueta, formas normalizadas, ambiguo)
_SIGNOS = [
    ("aries", "Aries", ["aries"], False),
    ("tauro", "Tauro", ["tauro"], False),
    ("geminis", "Géminis", ["geminis"], False),
    ("cancer", "Cáncer", ["cancer"], False),
    ("leo", "Leo", ["leo"], True),
    ("virgo", "Virgo", ["virgo"], False),
    ("libra", "Libra", ["libra"], False),
    ("escorpio", "Escorpio", ["escorpio", "escorpion"], False),
    ("sagitario", "Sagitario", ["sagitario"], False),
    ("capricornio", "Capricornio", ["capricornio"], False),
    ("acuario", "Acuario", ["acuario"], False),
    ("piscis", "Piscis", ["piscis"], False),
]

# Leo es también nombre propio; solo cuenta como signo si hay contexto
# astrológico explícito en las 8 palabras de alrededor (signo, ascendente,
# «sol en», otro planeta…). La cifra de esos casos se guarda aparte en
# «con_contexto». Cáncer como enfermedad no se filtra: apenas aparece en
# respuestas de este dominio y el requisito del informe era Leo.
_CONTEXTO_ASTRO_RE = re.compile(
    r"\bsigno\b|\bascendente\b|\bsol en\b|\bluna en\b|\bzodiaco\b|"
    r"\bhoroscopo\b|\bnatal\b|\bmercurio en\b|\bvenus en\b|\bmarte en\b|"
    r"\bjupiter en\b|\bsaturno en\b|\burano en\b|\bneptuno en\b|\bpluton en\b")

_PLANETAS = ["sol", "luna", "mercurio", "venus", "marte", "jupiter",
             "saturno", "urano", "neptuno", "pluton"]

_ORDINALES_CASA = {
    "primera": 1, "segunda": 2, "tercera": 3, "cuarta": 4, "quinta": 5,
    "sexta": 6, "septima": 7, "octava": 8, "novena": 9, "decima": 10,
    "undecima": 11, "duodecima": 12,
}
_PALABRAS_CASA = {
    "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
}
_ROMANOS_CASA = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
    "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12,
}


def _regex_formas(formas):
    """Alternación de formas fijas, de más larga a más corta, con bordes."""
    ordenadas = sorted(set(formas), key=len, reverse=True)
    return re.compile(r"(?<![0-9a-z])(?:"
                      + "|".join(re.escape(f) for f in ordenadas)
                      + r")(?![0-9a-z])")


_FORMAS_SIGNO = {}
for _sid, _etiqueta, _formas, _ambiguo in _SIGNOS:
    for _f in _formas:
        _FORMAS_SIGNO[_f] = (_sid, _etiqueta, _ambiguo)
_RE_SIGNOS = _regex_formas(_FORMAS_SIGNO)
_RE_PLANETAS = _regex_formas(_PLANETAS)
_ORD_ALT = "|".join(_ORDINALES_CASA)
_PAL_ALT = "|".join(_PALABRAS_CASA)
_ROM_ALT = "|".join(sorted(_ROMANOS_CASA, key=len, reverse=True))
_CASAS_RES = [
    (re.compile(r"\bcasa\s+(1[0-2]|[1-9])(?![0-9])"),
     lambda m: int(m.group(1))),
    (re.compile(r"\bcasa\s+(" + _ROM_ALT + r")(?![a-z])"),
     lambda m: _ROMANOS_CASA[m.group(1)]),
    (re.compile(r"\bcasa\s+(" + _PAL_ALT + r")(?![a-z])"),
     lambda m: _PALABRAS_CASA[m.group(1)]),
    (re.compile(r"\bcasa\s+(" + _ORD_ALT + r")(?![a-z])"),
     lambda m: _ORDINALES_CASA[m.group(1)]),
    (re.compile(r"(?<![a-z])(" + _ORD_ALT + r")\s+casa\b"),
     lambda m: _ORDINALES_CASA[m.group(1)]),
]


def _hay_contexto_astro(texto_norm, ini, fin):
    """Busca contexto astrológico explícito a menos de 8 palabras."""
    palabras = texto_norm.split()
    p_ini = len(texto_norm[:ini].split())
    p_fin = len(texto_norm[:fin].split())
    ventana = palabras[max(0, p_ini - 8): p_fin + 8]
    return bool(_CONTEXTO_ASTRO_RE.search(" " + " ".join(ventana) + " "))


def _menciones_astro(texto):
    """Devuelve {clave: {"nombre", "con_contexto"}} para signos, planetas y casas."""
    tn = cartas.norm(texto)
    hallazgos = {}
    if tn:
        for m in _RE_SIGNOS.finditer(tn):
            sid, etiqueta, ambiguo = _FORMAS_SIGNO[m.group(0)]
            con_contexto = False
            if ambiguo:
                if not _hay_contexto_astro(tn, m.start(), m.end()):
                    continue
                con_contexto = True
            anterior = hallazgos.get("signo:" + sid)
            if anterior is None or con_contexto:
                hallazgos["signo:" + sid] = {"nombre": etiqueta,
                                             "con_contexto": con_contexto}
        for m in _RE_PLANETAS.finditer(tn):
            p = m.group(0)
            hallazgos.setdefault("planeta:" + p,
                                 {"nombre": p.capitalize(),
                                  "con_contexto": False})
        for regex, resolver in _CASAS_RES:
            for m in regex.finditer(tn):
                n = resolver(m)
                hallazgos.setdefault("casa:%02d" % n,
                                     {"nombre": "Casa %d" % n,
                                      "con_contexto": False})
    return hallazgos


def contar_astrologia(pares, contadores):
    """Cuenta signos (con la precaución de Leo), planetas y casas.

    Las claves son «signo:<id>», «planeta:<id>» y «casa:<nn>». En los signos
    aceptados solo por contexto astrológico explícito se incrementa además el
    campo «con_contexto» del par de la respuesta.
    """
    for pregunta, respuesta in pares:
        en_resp = _menciones_astro(respuesta)
        en_preg = _menciones_astro(pregunta)
        for clave in sorted(set(en_resp) | set(en_preg)):
            dato = en_resp[clave] if clave in en_resp else en_preg[clave]
            familia = clave.split(":", 1)[0]
            c = _contador(contadores, clave, dato["nombre"], familia)
            if clave in en_resp:
                c["pares_respuesta"] += 1
                if clave not in en_preg:
                    c["solo_en_respuesta"] += 1
                if en_resp[clave]["con_contexto"]:
                    c["con_contexto_astrologico"] = \
                        c.get("con_contexto_astrologico", 0) + 1
            if clave in en_preg:
                c["pares_pregunta"] += 1


# ---------------------------------------------------------------------------
# Numerología: números 1-9 y maestros 11, 22, 33 solo en contexto (T15.4)
# ---------------------------------------------------------------------------

# Contextos que confirman que el número habla de numerología y no de cualquier
# cifra suelta («me dio 3 cartas»). El texto se normaliza con cartas.norm (sin
# tildes). «maestro» inmediatamente después también vale («el 33 es maestro»).
_CONTEXTO_NUMERO_ANTES_RE = re.compile(
    r"\bcamino de vida\b|\bnumero\b|\bano personal\b|"
    r"\bexpresion\b|\bmotivacion\b|\bdestino\b|"
    r"\bnumero maestro\b|\bpersona[lr]\b")
_CONTEXTO_NUMERO_DESPUES_RE = re.compile(r"^\s+(es\s+)?maestros?\b")

_NUMEROS_VALIDOS = set(range(1, 10)) | {11, 22, 33}


def _menciones_numerologia(texto):
    """Devuelve {clave: nombre} de números numerológicos en contexto."""
    tn = cartas.norm(texto)
    hallazgos = {}
    if not tn:
        return hallazgos
    for m in re.finditer(r"(?<![0-9a-z])(1[0-9]|2[0-9]|3[0-9]|[1-9])(?![0-9a-z])",
                         tn):
        n = int(m.group(1))
        if n not in _NUMEROS_VALIDOS:
            continue
        anterior = tn[max(0, m.start() - 40):m.start()]
        posterior = tn[m.end():m.end() + 20]
        if not (_CONTEXTO_NUMERO_ANTES_RE.search(anterior)
                or _CONTEXTO_NUMERO_DESPUES_RE.search(posterior)):
            continue
        hallazgos.setdefault("numero:%02d" % n, "Número %d" % n)
    return hallazgos


def contar_numerologia(pares, contadores):
    """Cuenta los números numerológicos (1-9, 11, 22, 33) mencionados en contexto.

    Las claves son «numero:<nn>». Un número suelto sin contexto numerológico
    no se cuenta, y solo se aceptan 1-9 y los maestros 11, 22 y 33.
    """
    for pregunta, respuesta in pares:
        en_resp = _menciones_numerologia(respuesta)
        en_preg = _menciones_numerologia(pregunta)
        for clave in sorted(set(en_resp) | set(en_preg)):
            c = _contador(contadores, clave, en_resp.get(clave)
                          or en_preg[clave], "numerologia")
            if clave in en_resp:
                c["pares_respuesta"] += 1
                if clave not in en_preg:
                    c["solo_en_respuesta"] += 1
            if clave in en_preg:
                c["pares_pregunta"] += 1


# ---------------------------------------------------------------------------
# Informe y CLI (T15.5)
# ---------------------------------------------------------------------------

_FAMILIAS_LABEL = {
    "tarot": "Tarot",
    "espanola": "Baraja española",
    "signo": "Signos del zodiaco",
    "planeta": "Planetas",
    "casa": "Casas astrológicas",
    "numerologia": "Numerología",
}


def construir_resumen(contadores, num_pares, minimo=20, stats=None):
    """Monta el diccionario serializable del informe JSON."""
    deficit = sorted(
        [{"clave": k, "etiqueta": c["etiqueta"], "familia": c["familia"],
          "pares_respuesta": c["pares_respuesta"],
          "pares_pregunta": c["pares_pregunta"],
          "solo_en_respuesta": c["solo_en_respuesta"]}
         for k, c in contadores.items()
         if c["pares_respuesta"] < minimo],
        key=lambda e: (e["pares_respuesta"], e["etiqueta"]))
    top = sorted(contadores.items(),
                 key=lambda kv: (-kv[1]["pares_respuesta"], kv[1]["etiqueta"]))
    sobre = [
        {"clave": k, "etiqueta": c["etiqueta"], "familia": c["familia"],
         "pares_respuesta": c["pares_respuesta"],
         "porcentaje_respuesta": round(
             100.0 * c["pares_respuesta"] / num_pares, 1) if num_pares else 0.0}
        for k, c in top[:10]]
    extra = {}
    for k, c in contadores.items():
        if c.get("invertidas"):
            extra[k] = {"invertidas": c["invertidas"]}
        if c.get("con_contexto_astrologico"):
            extra.setdefault(k, {})["con_contexto_astrologico"] = \
                c["con_contexto_astrologico"]
    entidades = {}
    for k, c in contadores.items():
        e = {"etiqueta": c["etiqueta"], "familia": c["familia"],
             "pares_respuesta": c["pares_respuesta"],
             "pares_pregunta": c["pares_pregunta"],
             "solo_en_respuesta": c["solo_en_respuesta"]}
        e.update(extra.get(k, {}))
        entidades[k] = e
    return {
        "totales": {
            "pares_analizados": num_pares,
            "pares_con_lineas_invalidas": (stats or {}).get(
                "lineas_invalidas", 0),
            "pares_sin_gpt": (stats or {}).get("sin_gpt", 0),
        },
        "minimo": minimo,
        "entidades": entidades,
        "deficitarias": deficit,
        "sobre_representadas": sobre,
    }


def construir_informe_md(contadores, num_pares, minimo=20, stats=None):
    """Redacta el informe en Markdown, en español."""
    lineas = ["# Informe de cobertura del dataset", ""]
    lineas.append("## Pares analizados")
    lineas.append("")
    lineas.append("- Pares con respuesta de asistente: **%d**" % num_pares)
    st = stats or {}
    lineas.append("- Líneas inválidas ignoradas: %d" % st.get(
        "lineas_invalidas", 0))
    lineas.append("- Pares sin mensaje del asistente: %d" % st.get(
        "sin_gpt", 0))
    lineas.append("")
    lineas.append("## Cobertura por familia")
    lineas.append("")
    lineas.append("| Familia | Entidades vistas | Con menos de %d pares |"
                  % minimo)
    lineas.append("|---|---:|---:|")
    por_familia = {}
    for c in contadores.values():
        por_familia.setdefault(c["familia"], []).append(c)
    for fam in [f for f in _FAMILIAS_LABEL if f in por_familia]:
        cs = por_familia[fam]
        faltan = sum(1 for c in cs if c["pares_respuesta"] < minimo)
        lineas.append("| %s | %d | %d |"
                      % (_FAMILIAS_LABEL[fam], len(cs), faltan))
    lineas.append("")
    lineas.append("## Entidades con menos de %d pares" % minimo)
    lineas.append("")
    deficit = sorted((c for c in contadores.values()
                      if c["pares_respuesta"] < minimo),
                     key=lambda c: (c["pares_respuesta"], c["etiqueta"]))
    if not deficit:
        lineas.append("_Ninguna: todas las entidades alcanzadas superan el mínimo._")
    else:
        lineas.append("| Entidad | Familia | Pares en respuesta | "
                      "Pares en pregunta |")
        lineas.append("|---|---|---:|---:|")
        for c in deficit:
            lineas.append("| %s | %s | %d | %d |" % (
                c["etiqueta"], _FAMILIAS_LABEL.get(c["familia"], c["familia"]),
                c["pares_respuesta"], c["pares_pregunta"]))
    lineas.append("")
    lineas.append("## Las 10 entidades más representadas")
    lineas.append("")
    top = sorted(contadores.items(),
                 key=lambda kv: (-kv[1]["pares_respuesta"],
                                 kv[1]["etiqueta"]))[:10]
    lineas.append("| Entidad | Familia | Pares en respuesta | % del dataset |")
    lineas.append("|---|---|---:|---:|")
    for _, c in top:
        pct = 100.0 * c["pares_respuesta"] / num_pares if num_pares else 0.0
        lineas.append("| %s | %s | %d | %.1f%% |" % (
            c["etiqueta"], _FAMILIAS_LABEL.get(c["familia"], c["familia"]),
            c["pares_respuesta"], pct))
    lineas.append("")
    return "\n".join(lineas)


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Informe de cobertura de entidades del dataset.")
    parser.add_argument("--in", dest="ins", nargs="+", required=True,
                        help="ficheros JSONL ShareGPT a analizar")
    parser.add_argument("--minimo", type=int, default=20,
                        help="mínimo de pares en respuesta por entidad "
                             "(defecto: 20)")
    parser.add_argument("--out-json", default="cobertura_dataset.json",
                        help="ruta del informe JSON")
    parser.add_argument("--out-md", default="cobertura_dataset.md",
                        help="ruta del informe Markdown")
    parser.add_argument("--dry-run", action="store_true",
                        help="imprime el informe sin escribir ficheros")
    args = parser.parse_args(argv)

    pares, stats = leer_pares(args.ins)
    contadores = {}
    contar_cartas(pares, contadores)
    contar_astrologia(pares, contadores)
    contar_numerologia(pares, contadores)
    resumen = construir_resumen(contadores, len(pares), args.minimo, stats)
    informe = construir_informe_md(contadores, len(pares), args.minimo, stats)
    if args.dry_run:
        print(informe)
        return 0
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write(informe)
    print("Escritos %s y %s (%d pares, %d entidades)." % (
        args.out_json, args.out_md, len(pares), len(contadores)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
