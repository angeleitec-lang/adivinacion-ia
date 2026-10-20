#!/usr/bin/env python3
"""Auditoría determinista de calidad de las páginas web descargadas (T31).

Lee los Markdown de ``/Users/angelgonzalez/fase0/web/<dominio>/*.md``
(front-matter YAML + cuerpo) y marca banderas de calidad sin usar LLM:

- ``corta``: menos de 1.000 caracteres de texto.
- ``mojibake``: secuencias típicas de codificación rota.
- ``no_espanol``: proporción baja de palabras funcionales españolas.
- ``ruido_navegacion``: bloques de menú o pie que sobreviven a la
  extracción y contienen una etiqueta de navegación inequívoca.
- ``duplicada``: misma página o párrafos casi idénticos a otra.
- ``titulo_pobre``: título vacío, corto, truncado o con Markdown.
- ``repeticion_interna``: un párrafo repetido tres o más veces.

Produce ``calidad.jsonl`` (una línea por página) y ``calidad.md`` (informe
por dominio con porcentajes y peores páginas).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

UMBRAL_CORTO = 1000
UMBRAL_NO_ESPANOL_PALABRAS = 40
UMBRAL_JACCARD = 0.90
MIN_PARRAFO = 40

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_ENCABEZADO_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_MOJIBAKE_RE = re.compile(
    r"Ã[\x80-\xBF]|Â[\x80-\xBF]|â€|â€™|â€œ|â€\x9d|\ufffd"
)

_PALABRAS_ES = frozenset("""
a al algo algunas algunos ante antes aunque cada como con contra cual cuando
de del desde donde dos durante e el ella ellas ellos en entre era eran es esa
esas ese eso esos esta estaba estado estas este esto estos fue fueron ha hace
hacen hasta hay la las le les lo los más me mientras mi mis mucho muchos muy
nada ni no nos nosotros o os otra otras otro otros para pero poco por porque
que qué quien quienes se sea según ser si sí sin sino sobre son su sus también
tanto te tiene tienen todo todos tu tus tú un una uno unos y ya yo
""".split())

_PALABRAS_EN = frozenset("""
a about all also an and any are as at be been before being between both but by
can could did do does doing down each few for from further had has have having
he her here hers him his how i if in into is it its itself just me more most my
no not now of off on once only or other our out over own same she should so
some such than that the their them then there these they this those through to
too under until up very was we were what when where which while who whom why
will with would you your yours
""".split())

# Etiquetas que solo aparecen en menús/pies: anclan la bandera sin duda.
_NAVS_INEQUIVOCAS = (
    "aviso legal", "aviso de cookies", "política de privacidad",
    "politica de privacidad", "política de cookies", "politica de cookies",
    "todos los derechos reservados", "todos los derechos", "copyright",
    "iniciar sesión", "iniciar sesion", "registrarse", "publicidad",
    "newsletter", "síguenos", "siguenos", "suscríbete", "suscribete",
    "mapa del sitio", "quiénes somos", "quienes somos", "sobre nosotros",
    "términos y condiciones", "terminos y condiciones",
)

# Etiquetas que también son vocabulario normal del corpus (nombres de cartas,
# prosa interpretativa): solo anclan si la línea es la etiqueta en sí.
_NAVS_AMBIGUAS = (
    "inicio", "menú", "menu", "contacto", "cookies", "compartir", "home",
    "blog", "buscar", "aceptar", "rechazar", "términos", "terminos",
)

_COMILLAS_BORDE = "\"'“”«»()[]{}"

_VERBO_RE = re.compile(
    r"\b\w{3,}(?:ar|er|ir|ando|iendo|ado|ada|idos|idas|aba|aban|"
    r"ía|ían|ó|aron|ieron|é|aste|iste)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Lectura de páginas
# ---------------------------------------------------------------------------

def _quitar_comillas(valor: str) -> str:
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        valor = valor[1:-1].replace('\\"', '"')
    return valor


def _parsear_front_matter(texto: str) -> Dict[str, Any]:
    """Carga un YAML plano de ``clave: valor`` (sin dependencia de PyYAML)."""
    datos: Dict[str, Any] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or ": " not in linea:
            if linea.endswith(":") and not linea.startswith("#"):
                clave = linea[:-1].strip()
                if clave:
                    datos[clave] = None
            continue
        clave, valor = linea.split(": ", 1)
        clave = clave.strip()
        valor = _quitar_comillas(valor.strip())
        if valor.lower() in ("null", "~", ""):
            datos[clave] = None
        elif valor.lower() == "true":
            datos[clave] = True
        elif valor.lower() == "false":
            datos[clave] = False
        else:
            datos[clave] = valor
    return datos


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def leer_pagina(ruta: Path) -> Dict[str, Any]:
    """Lee una página Markdown y separa front-matter y cuerpo."""
    ruta = Path(ruta)
    contenido = ruta.read_text(encoding="utf-8", errors="replace")
    if contenido.startswith("\ufeff"):
        contenido = contenido[1:]
    coincidencia = _FRONT_MATTER_RE.match(contenido)
    if coincidencia:
        front_matter = _parsear_front_matter(coincidencia.group(1))
        cuerpo = contenido[coincidencia.end():]
    else:
        front_matter = {}
        cuerpo = contenido

    cuerpo = cuerpo.strip()
    titulo = front_matter.get("titulo")
    if not isinstance(titulo, str):
        titulo = ""
    if not titulo.strip():
        encabezado = _ENCABEZADO_RE.search(cuerpo)
        titulo = encabezado.group(1).strip() if encabezado else ""

    sha = front_matter.get("sha256")
    if not isinstance(sha, str) or not sha.strip():
        sha = _sha256_texto(cuerpo)

    dominio = front_matter.get("dominio")
    if not isinstance(dominio, str) or not dominio.strip():
        dominio = ruta.parent.name

    return {
        "ruta": str(ruta),
        "dominio": dominio.strip(),
        "titulo": titulo.strip(),
        "front_matter": front_matter,
        "cuerpo": cuerpo,
        "caracteres": len(cuerpo),
        "sha256": sha.strip(),
    }


def leer_paginas(web_dir: Path) -> List[Dict[str, Any]]:
    """Lee los ``<dominio>/*.md`` de ``web_dir`` ordenados por ruta.

    Solo baja un nivel: los Markdown sueltos en la raíz (informes generados
    como ``informe.md`` o ``calidad.md``) no son páginas descargadas.
    """
    web_dir = Path(web_dir)
    paginas = [leer_pagina(ruta) for ruta in sorted(web_dir.glob("*/*.md"))]
    return paginas


# ---------------------------------------------------------------------------
# Banderas
# ---------------------------------------------------------------------------

def bandera_corta(texto: str, minimo: int = UMBRAL_CORTO) -> bool:
    return len(texto.strip()) < minimo


def bandera_mojibake(texto: str) -> bool:
    return bool(_MOJIBAKE_RE.search(texto))


def bandera_no_espanol(texto: str) -> bool:
    """Heurística: texto largo con pocas palabras funcionales españolas.

    Solo se pronuncia si hay al menos 40 palabras y presencia apreciable de
    palabras funcionales inglesas; así no marca textos sin función conocida.
    """
    palabras = re.findall(r"[a-záéíóúüñ]+", texto.lower())
    if len(palabras) < UMBRAL_NO_ESPANOL_PALABRAS:
        return False
    total = len(palabras)
    es = sum(1 for palabra in palabras if palabra in _PALABRAS_ES) / total
    en = sum(1 for palabra in palabras if palabra in _PALABRAS_EN) / total
    return es < 0.08 and en >= 0.05


def _quitar_bordes(texto: str) -> str:
    """Quita viñetas iniciales y comillas o paréntesis de los bordes."""
    texto = re.sub(r"^(?:[-*+>]\s*)+", "", texto).strip()
    while texto and texto[0] in _COMILLAS_BORDE:
        texto = texto[1:].strip()
    while texto and texto[-1] in _COMILLAS_BORDE:
        texto = texto[:-1].strip()
    return texto


def _match_palabra_completa(texto: str, clave: str) -> bool:
    return bool(
        re.search(r"(?:^|\W)" + re.escape(clave) + r"(?:$|\W)", texto, re.IGNORECASE)
    )


def _linea_nav_like(linea: str) -> bool:
    """Línea corta sin pinta de prosa: candidata a etiqueta de navegación."""
    texto_bruto = linea.strip()
    if not texto_bruto or texto_bruto.startswith(("#", "|")):
        return False
    texto = _quitar_bordes(texto_bruto)
    if not texto:
        return False
    if len(texto) > 45 or len(texto.split()) > 7:
        return False
    if re.search(r"[.!?;:…]$", texto):
        return False
    if _VERBO_RE.search(texto):
        return False
    return True


def _es_ancla_navegacion(linea: str) -> bool:
    """Línea nav_like que contiene una etiqueta de navegación que ancla la bandera.

    Las etiquetas ambiguas («inicio», «contacto», «buscar»…) solo anclan si
    la línea es la etiqueta en sí, sin viñeta y sin palabras alrededor: en
    este corpus esas palabras aparecen en listas de cartas («- Inicio» es una
    carta del Osho Zen) y en prosa interpretativa.
    """
    if not _linea_nav_like(linea):
        return False
    texto_bruto = linea.strip()
    con_vineta = bool(re.match(r"^[-*+>]\s*", texto_bruto))
    texto = _quitar_bordes(texto_bruto)
    for clave in _NAVS_INEQUIVOCAS:
        if _match_palabra_completa(texto, clave):
            return True
    if con_vineta:
        return False
    for clave in _NAVS_AMBIGUAS:
        if len(texto) <= len(clave) + 2 and _match_palabra_completa(texto, clave):
            return True
    return False


def bandera_ruido_navegacion(texto: str) -> bool:
    """Tres o más líneas cortas de navegación consecutivas con ancla inequívoca.

    Medición 2026-10-20 sobre el corpus actual (1.626 páginas): no queda
    ruido de navegación real tras la extracción con trafilatura; la bandera
    anterior marcaba 599 páginas, todas falsos positivos (listas de cartas,
    tablas, citas). Se mantiene como red de seguridad para descargas
    futuras: sin una línea ancla inequívoca no marca nada.
    """
    racha = 0
    anclas = 0
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        if _linea_nav_like(linea):
            racha += 1
            if _es_ancla_navegacion(linea):
                anclas += 1
            if racha >= 3 and anclas >= 1:
                return True
        else:
            racha = 0
            anclas = 0
    return False


def _normalizar_parrafo(parrafo: str) -> str:
    parrafo = parrafo.strip().lower()
    parrafo = re.sub(r"[^\w\s]", " ", parrafo)
    return re.sub(r"\s+", " ", parrafo).strip()


def extraer_parrafos(texto: str) -> List[str]:
    """Extrae párrafos normalizados (sin encabezados ni líneas cortas)."""
    parrafos: List[str] = []
    for bloque in re.split(r"\n+", texto):
        bloque = bloque.strip()
        if not bloque or bloque.startswith("#"):
            continue
        bloque = re.sub(r"^(?:[-*+>]\s*)+", "", bloque)
        normalizado = _normalizar_parrafo(bloque)
        if len(normalizado) >= MIN_PARRAFO:
            parrafos.append(normalizado)
    return parrafos


def parrafos_repetidos(texto: str, minimo: int = 3) -> List[Tuple[str, int]]:
    """Devuelve los párrafos normalizados que aparecen ``minimo`` veces o más."""
    cuenta = Counter(extraer_parrafos(texto))
    repetidos = [(p, n) for p, n in cuenta.items() if n >= minimo]
    return sorted(repetidos, key=lambda par: (-par[1], par[0]))


def bandera_repeticion_interna(texto: str) -> bool:
    return bool(parrafos_repetidos(texto))


def bandera_titulo_pobre(titulo: str) -> bool:
    titulo = (titulo or "").strip()
    if len(titulo) < 4:
        return True
    if titulo.endswith(":"):
        return True
    if "**" in titulo:
        return True
    return False


# ---------------------------------------------------------------------------
# Duplicados
# ---------------------------------------------------------------------------

def _hashes_parrafos(texto: str) -> set:
    return {_sha256_texto(parrafo) for parrafo in extraer_parrafos(texto)}


def _anotar_duplicado(infos: Dict[int, Dict[str, Any]], i: int, ruta: str,
                      motivo: str, jaccard: float) -> None:
    info = infos.setdefault(i, {"rutas": [], "motivo": motivo, "jaccard": jaccard})
    if ruta not in info["rutas"]:
        info["rutas"].append(ruta)
    if motivo == "sha256" or info["motivo"] != "sha256":
        info["motivo"] = motivo
    info["jaccard"] = max(info["jaccard"], jaccard)


def detectar_duplicadas(paginas: Sequence[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Marca páginas con el mismo sha256 o Jaccard de párrafos >= 0,90.

    Solo compara pares que comparten al menos un párrafo (índice invertido de
    hashes), de modo que el coste no es cuadrático en el corpus completo.
    """
    infos: Dict[int, Dict[str, Any]] = {}

    por_sha: Dict[str, List[int]] = defaultdict(list)
    for i, pagina in enumerate(paginas):
        por_sha[pagina["sha256"]].append(i)
    for indices in por_sha.values():
        if len(indices) < 2:
            continue
        for i in indices:
            for j in indices:
                if i != j:
                    _anotar_duplicado(
                        infos, i, paginas[j]["ruta"], "sha256", 1.0
                    )

    hashes = [_hashes_parrafos(pagina["cuerpo"]) for pagina in paginas]
    indice: Dict[str, List[int]] = defaultdict(list)
    for i, conjunto in enumerate(hashes):
        for hash_parrafo in conjunto:
            indice[hash_parrafo].append(i)

    pares = set()
    for indices in indice.values():
        if len(indices) < 2:
            continue
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                pares.add((indices[a], indices[b]))

    for i, j in sorted(pares):
        conjunto_i, conjunto_j = hashes[i], hashes[j]
        if not conjunto_i or not conjunto_j:
            continue
        union = conjunto_i | conjunto_j
        jaccard = len(conjunto_i & conjunto_j) / len(union)
        if jaccard < UMBRAL_JACCARD:
            continue
        _anotar_duplicado(infos, i, paginas[j]["ruta"], "parrafos", jaccard)
        _anotar_duplicado(infos, j, paginas[i]["ruta"], "parrafos", jaccard)

    return infos


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------

def analizar_paginas(paginas: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Añade a cada página sus banderas y detalles, en orden determinista."""
    ordenadas = sorted(paginas, key=lambda p: p["ruta"])
    duplicadas = detectar_duplicadas(ordenadas)
    resultados: List[Dict[str, Any]] = []
    for indice, pagina in enumerate(ordenadas):
        cuerpo = pagina["cuerpo"]
        banderas: List[str] = []
        if bandera_corta(cuerpo):
            banderas.append("corta")
        if bandera_mojibake(cuerpo):
            banderas.append("mojibake")
        if bandera_no_espanol(cuerpo):
            banderas.append("no_espanol")
        if bandera_ruido_navegacion(cuerpo):
            banderas.append("ruido_navegacion")
        if indice in duplicadas:
            banderas.append("duplicada")
        if bandera_titulo_pobre(pagina["titulo"]):
            banderas.append("titulo_pobre")
        repetidos = parrafos_repetidos(cuerpo)
        if repetidos:
            banderas.append("repeticion_interna")

        resultado = dict(pagina)
        resultado["banderas"] = banderas
        resultado["detalles"] = {}
        if indice in duplicadas:
            info = duplicadas[indice]
            resultado["detalles"]["duplicada_de"] = {
                "motivo": info["motivo"],
                "rutas": sorted(info["rutas"]),
                "jaccard": round(info["jaccard"], 3),
            }
        if repetidos:
            resultado["detalles"]["repeticion_interna"] = [
                {"parrafo": parrafo[:160], "veces": veces}
                for parrafo, veces in repetidos
            ]
        resultados.append(resultado)
    return resultados


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------

BANDERAS = (
    "corta",
    "mojibake",
    "no_espanol",
    "ruido_navegacion",
    "duplicada",
    "titulo_pobre",
    "repeticion_interna",
)


def _tabla_banderas(paginas: Sequence[Dict[str, Any]]) -> List[str]:
    total = len(paginas)
    conteo = Counter(
        bandera for pagina in paginas for bandera in pagina["banderas"]
    )
    lineas = ["| Bandera | Páginas | % |", "|---|---|---|"]
    for bandera in BANDERAS:
        n = conteo.get(bandera, 0)
        porcentaje = (100.0 * n / total) if total else 0.0
        lineas.append(f"| {bandera} | {n} | {porcentaje:.1f} % |")
    return lineas


def _peores_paginas(paginas: Sequence[Dict[str, Any]], limite: int = 3) -> List[str]:
    con_banderas = [p for p in paginas if p["banderas"]]
    peores = sorted(
        con_banderas,
        key=lambda p: (-len(p["banderas"]), p["caracteres"], p["ruta"]),
    )[:limite]
    if not peores:
        return ["Sin páginas con banderas."]
    lineas = []
    for posicion, pagina in enumerate(peores, 1):
        banderas = ", ".join(pagina["banderas"])
        lineas.append(
            f"{posicion}. `{pagina['ruta']}` — {len(pagina['banderas'])} "
            f"banderas ({banderas}), {pagina['caracteres']} caracteres"
        )
    return lineas


def generar_informe(
    paginas: Sequence[Dict[str, Any]], out_dir: Path
) -> Dict[str, Any]:
    """Escribe ``calidad.md`` y ``calidad.jsonl``; devuelve el resumen."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    por_dominio: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for pagina in paginas:
        por_dominio[pagina["dominio"]].append(pagina)

    lineas_md: List[str] = [
        "# Auditoría de calidad de páginas web",
        "",
        "Generado por `finetune/corpus/web_calidad.py` (heurísticas "
        "deterministas, sin LLM).",
        "",
        f"- Páginas analizadas: {len(paginas)}",
        f"- Dominios: {len(por_dominio)}",
        "",
        "## Resumen global",
        "",
        *_tabla_banderas(paginas),
        "",
        "## Por dominio",
        "",
    ]

    resumen_dominios: Dict[str, Any] = {}
    for dominio in sorted(por_dominio):
        paginas_dominio = sorted(por_dominio[dominio], key=lambda p: p["ruta"])
        conteo = Counter(
            bandera for pagina in paginas_dominio for bandera in pagina["banderas"]
        )
        resumen_dominios[dominio] = {
            "paginas": len(paginas_dominio),
            "banderas": dict(conteo),
        }
        lineas_md.extend([
            f"### {dominio}",
            "",
            f"- Páginas: {len(paginas_dominio)}",
            "",
            *_tabla_banderas(paginas_dominio),
            "",
            "**Peores páginas**",
            "",
            *_peores_paginas(paginas_dominio),
            "",
        ])

    (out_dir / "calidad.md").write_text(
        "\n".join(lineas_md).rstrip() + "\n", encoding="utf-8"
    )

    with open(out_dir / "calidad.jsonl", "w", encoding="utf-8") as fichero:
        for pagina in paginas:
            registro = {
                "ruta": pagina["ruta"],
                "dominio": pagina["dominio"],
                "titulo": pagina["titulo"],
                "sha256": pagina["sha256"],
                "caracteres": pagina["caracteres"],
                "banderas": pagina["banderas"],
                "detalles": pagina["detalles"],
            }
            fichero.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return {
        "paginas": len(paginas),
        "dominios": len(por_dominio),
        "por_dominio": resumen_dominios,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audita la calidad de las páginas web Markdown descargadas."
    )
    parser.add_argument(
        "--web-dir",
        default="/Users/angelgonzalez/fase0/web",
        help="Directorio raíz con un subdirectorio por dominio.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directorio de salida (por defecto, el mismo que --web-dir).",
    )
    args = parser.parse_args(argv)

    web_dir = Path(args.web_dir)
    out_dir = Path(args.out_dir) if args.out_dir else web_dir
    paginas = analizar_paginas(leer_paginas(web_dir))
    resumen = generar_informe(paginas, out_dir)

    print(f"Páginas analizadas: {resumen['paginas']}")
    for dominio in sorted(resumen["por_dominio"]):
        datos = resumen["por_dominio"][dominio]
        detalle = ", ".join(
            f"{bandera}={n}" for bandera, n in sorted(datos["banderas"].items())
        )
        print(f"  {dominio}: {datos['paginas']} páginas" + (f" ({detalle})" if detalle else ""))
    print(f"Informe: {out_dir / 'calidad.md'}")
    print(f"JSONL: {out_dir / 'calidad.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
