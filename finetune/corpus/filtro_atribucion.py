"""Auditoria y filtro determinista de atribucion de entidad en astrologia y numerologia.

T88. Contaminacion tipo T53/T71 pero en las celdas de ASTROLOGIA y
NUMEROLOGIA: evidencias asignadas a una entidad cuyo titulo de seccion o URL
nombran OTRA entidad (otro signo, otro planeta) o directamente una pagina de
naipes (tarot / baraja espanola) que nada tiene que ver con la celda.

El filtro es 100% determinista (sin LLM ni red) y CONSERVADOR: prioriza la
precision sobre el recall. Solo retira cuando el titulo/URL identifican de
forma inequivoca una entidad distinta de la asignada. Un titulo generico que
no nombra ningun signo ni planeta NUNCA retira.

Motivos de retirada:

  1. ``familia_ajena_naipes``: el titulo o el PATH de la URL contienen un
     termino de naipes (tarot, arcano, naipe, baraja, un palo en espanol o
     ingles, o un patron tipo ``6 de espadas`` / ``Two of Cups``). Una
     pagina de naipes no puede sustentar una celda de astrologia o
     numerologia. Se mira el path y no el dominio: sitios cuyo dominio suena
     a naipes (p. ej. ``tarot.ac``) albergan paginas de numerologia validas
     y no deben retirarse por el nombre del dominio.
  2. ``signo_no_mencionado``: la celda es un signo (``X|signo``) o un
     planeta-en-signo (``P|S|planeta_en_signo``) y el titulo/URL nombran
     signos, pero el signo de la celda no aparece entre ellos.
  3. ``planeta_no_mencionado``: la celda es planeta-en-signo, planeta-en-casa
     o aspecto, y el titulo/URL nombran planetas, pero el planeta de la
     celda (en un aspecto, ninguno de los dos) no aparece.

Regla de oro: ``Venus en Leo`` para ``leo|signo`` se CONSERVA (Leo esta
mencionado); para ``acuario|signo`` se RETIRA (se nombra Leo, no Acuario).

Nunca toca el original: escribe copias en ``filtro_atribucion/`` (retiradas
con motivo, claves de afirmaciones a excluir del consenso, muestra de
revision con semilla fija e informe). Mide celdas completas antes/despues
usando ``cobertura.py`` sin sobrescribir ``cobertura_total_v2.json``.

La decision de aplicar a produccion la toma un humano revisando el informe;
el comando exacto se documenta en docs/ATRIBUCION_ENTIDADES.md.
"""
import argparse
import glob
import json
import os
import random
import re
import sys
import unicodedata
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cobertura
import juez

BASE = "/Users/angelgonzalez/fase0"
RUTA_EVIDENCIAS_WEB = os.path.join(BASE, "evidencias_web", "evidencias.jsonl")
RUTA_EVIDENCIAS_LIBROS = os.path.join(BASE, "libros", "evidencias", "evidencias.jsonl")
DIR_SECCIONES_LIBROS = os.path.join(BASE, "libros", "secciones")
DIR_PROCESADOS_WEB = os.path.join(BASE, "afirmaciones_full")
DIR_PROCESADOS_LIBROS = os.path.join(BASE, "afirmaciones_libros")
DIR_SALIDA = os.path.join(BASE, "filtro_atribucion")

SEMILLA_MUESTRA = 42
TAM_MUESTRA = 40

FAMILIAS_OBJETIVO = {"astrologia", "numerologia"}

SIGNOS = ["aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra",
          "escorpio", "sagitario", "capricornio", "acuario", "piscis"]
PLANETAS = ["sol", "luna", "mercurio", "venus", "marte", "jupiter",
            "saturno", "urano", "neptuno", "pluton"]

# Terminos de naipes (espanol e ingles) que delatan una pagina ajena a la
# celda de astrologia/numerologia.
PALOS_ES = ["espadas", "copas", "oros", "bastos"]
PALOS_EN = ["swords", "cups", "pentacles", "coins", "wands", "staves"]
PALABRAS_NAIPES = ["tarot", "arcano", "arcanos", "arcana", "arcanum",
                   "naipe", "naipes", "baraja"]

_RANGO_OF = re.compile(
    r"(?:ace|two|three|four|five|six|seven|eight|nine|ten|page|knight|"
    r"queen|king|sota|caballo|rey|reina|as)\s+of\s+(?:"
    + "|".join(PALOS_ES + PALOS_EN) + r")")
_NUM_PALO = re.compile(
    r"\d{1,2}\s*(?:-|\s+de\s+)(?:" + "|".join(PALOS_ES) + r")")


def norm(texto):
    """Minusculas y sin marcas diacriticas para comparar de forma robusta."""
    if not texto:
        return ""
    descomp = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descomp if unicodedata.category(c) != "Mn")


def _wb(palabra):
    return r"(?<![a-z])" + re.escape(palabra) + r"(?![a-z])"


def nombradas(texto, palabras):
    """Subconjunto de ``palabras`` que aparecen como palabra suelta en texto."""
    t = norm(texto)
    return {p for p in palabras if re.search(_wb(p), t)}


def _es_ajena_naipes(blob):
    if any(re.search(_wb(t), blob)
           for t in PALABRAS_NAIPES + PALOS_ES + PALOS_EN):
        return True
    if _RANGO_OF.search(blob):
        return True
    if _NUM_PALO.search(blob):
        return True
    return False


def familia_entidad(entidad_id):
    for e in cobertura.entidades():
        if e["entidad_id"] == entidad_id:
            return e.get("familia")
    return None


def motivo(ev, idx):
    """Devuelve el motivo de retirada o ``None`` si se conserva."""
    eid = ev.get("entidad_id", "")
    if familia_entidad(eid) not in FAMILIAS_OBJETIVO:
        return None
    meta = idx.get(ev.get("hash_seccion"))
    if not meta:
        return None
    titulo = meta.get("titulo", "") or ""
    url = meta.get("url", "") or ""
    path = urlparse(url).path or ""
    blob_naipes = norm(titulo) + " " + norm(path)

    if _es_ajena_naipes(blob_naipes):
        return "familia_ajena_naipes"

    parts = eid.split("|")
    subtipo = parts[-1] if parts else ""
    signs = nombradas(titulo, SIGNOS) | nombradas(url, SIGNOS)
    planets = nombradas(titulo, PLANETAS) | nombradas(url, PLANETAS)

    if subtipo == "signo":
        if signs and parts[0] not in signs:
            return "signo_no_mencionado"
    elif subtipo == "planeta_en_signo":
        if signs and parts[1] not in signs:
            return "signo_no_mencionado"
        elif planets and parts[0] not in planets:
            return "planeta_no_mencionado"
    elif subtipo == "planeta_en_casa":
        if planets and parts[0] not in planets:
            return "planeta_no_mencionado"
    elif subtipo == "aspecto":
        if planets and parts[0] not in planets and parts[2] not in planets:
            return "planeta_no_mencionado"
    return None


def construir_indice(base=BASE, secciones_dir=None):
    """Mapa hash_seccion -> {titulo, url, familia} para toda la fase0.

    Las paginas web se indexan por glob de ``*.md`` bajo ``base``; las
    secciones de libro por ``secciones_dir`` (por defecto el directorio de
    secciones de libro de la fase0).
    """
    if secciones_dir is None:
        secciones_dir = DIR_SECCIONES_LIBROS
    idx = {}
    for ruta in glob.glob(os.path.join(base, "**", "*.md"), recursive=True):
        try:
            secciones = juez._secciones_de_fichero(ruta)
        except Exception:
            continue
        for s in secciones:
            h = juez.hash_seccion(s)
            if h not in idx:
                idx[h] = {"titulo": s.get("titulo", ""),
                         "url": s.get("url", ""),
                         "familia": s.get("familia")}
    if os.path.isdir(secciones_dir):
        for s in juez.leer_secciones(secciones_dir):
            h = juez.hash_seccion(s)
            if h not in idx:
                idx[h] = {"titulo": s.get("titulo", ""),
                         "url": s.get("url", ""),
                         "familia": s.get("familia")}
    return idx


def _leer_jsonl(ruta):
    out = []
    if not os.path.exists(ruta):
        return out
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                out.append(json.loads(linea))
    return out


def _escribir_jsonl(ruta, filas):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")


def aplicar_filtro(web_evs, libros_evs, idx):
    """Separa conservadas y retiradas y devuelve recuentos."""
    conservadas = {"web": [], "libros": []}
    retiradas = {"web": [], "libros": []}
    recuento = {}
    for etiqueta, evs in (("web", web_evs), ("libros", libros_evs)):
        for ev in evs:
            m = motivo(ev, idx)
            if m is None:
                conservadas[etiqueta].append(ev)
            else:
                fam = familia_entidad(ev.get("entidad_id", ""))
                retiradas[etiqueta].append(dict(ev, motivo=m, familia=fam))
                recuento[(etiqueta, fam, m)] = recuento.get((etiqueta, fam, m), 0) + 1
    return conservadas, retiradas, recuento


def claves_excluir_consenso(retiradas, procesados):
    """Claves (hash,entidad,faceta) con afirmaciones que hay que excluir."""
    n_por_clave = {}
    for p in procesados:
        clave = (p.get("hash_seccion"), p.get("entidad_id"), p.get("faceta"))
        n_por_clave[clave] = n_por_clave.get(clave, 0) + int(p.get("n_afirmaciones", 0) or 0)
    claves = []
    vistos = set()
    for ev in retiradas:
        clave = (ev.get("hash_seccion"), ev.get("entidad_id"), ev.get("faceta"))
        if clave in vistos:
            continue
        vistos.add(clave)
        n = n_por_clave.get(clave, 0)
        if n > 0:
            claves.append({"hash_seccion": clave[0],
                          "entidad_id": clave[1],
                          "faceta": clave[2],
                          "n_afirmaciones": n,
                          "motivo": ev.get("motivo")})
    claves.sort(key=lambda c: (c["entidad_id"], c["faceta"], c["hash_seccion"]))
    return claves


def medir_cobertura(evs):
    catalogo = cobertura.entidades()
    res = cobertura.calcular_cobertura(evs, catalogo=catalogo)
    return {"celdas": res.get("celdas"), "completas": res.get("completas"),
            "por_familia": cobertura.resumen_por_familia(res, catalogo)}


def muestra_revision(retiradas, n=TAM_MUESTRA, semilla=SEMILLA_MUESTRA):
    plano = []
    for etiqueta in ("web", "libros"):
        for ev in retiradas[etiqueta]:
            plano.append(dict(ev, origen=etiqueta))
    plano.sort(key=lambda e: (e.get("hash_seccion", ""),
                             e.get("entidad_id", ""),
                             e.get("faceta", "")))
    rng = random.Random(semilla)
    if len(plano) <= n:
        return plano
    return rng.sample(plano, n)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--evidencias-web", default=None)
    ap.add_argument("--evidencias-libros", default=None)
    ap.add_argument("--secciones-dir", default=None)
    ap.add_argument("--procesados-web", default=None)
    ap.add_argument("--procesados-libros", default=None)
    args = ap.parse_args(argv)

    base = args.base
    salida = args.salida or os.path.join(base, "filtro_atribucion")
    r_web = args.evidencias_web or os.path.join(
        base, "evidencias_web", "evidencias.jsonl")
    r_lib = args.evidencias_libros or os.path.join(
        base, "libros", "evidencias", "evidencias.jsonl")
    sec_dir = args.secciones_dir or os.path.join(base, "libros", "secciones")
    proc_web_r = args.procesados_web or os.path.join(
        base, "afirmaciones_full", "procesados.jsonl")
    proc_lib_r = args.procesados_libros or os.path.join(
        base, "afirmaciones_libros", "procesados.jsonl")

    idx = construir_indice(base, secciones_dir=sec_dir)
    web = _leer_jsonl(r_web)
    libros = _leer_jsonl(r_lib)

    conservadas, retiradas, recuento = aplicar_filtro(web, libros, idx)

    proc_web = _leer_jsonl(proc_web_r)
    proc_lib = _leer_jsonl(proc_lib_r)
    todas_retiradas = retiradas["web"] + retiradas["libros"]
    claves = claves_excluir_consenso(todas_retiradas, proc_web + proc_lib)
    afirm_afectadas = sum(c["n_afirmaciones"] for c in claves)

    antes = medir_cobertura(web + libros)
    despues = medir_cobertura(conservadas["web"] + conservadas["libros"])

    os.makedirs(salida, exist_ok=True)
    _escribir_jsonl(os.path.join(salida, "evidencias_retiradas.jsonl"),
                    todas_retiradas)
    _escribir_jsonl(os.path.join(salida, "evidencias_retiradas_web.jsonl"),
                    retiradas["web"])
    _escribir_jsonl(os.path.join(salida, "evidencias_retiradas_libros.jsonl"),
                    retiradas["libros"])
    _escribir_jsonl(os.path.join(salida, "evidencias_conservadas_web.jsonl"),
                    conservadas["web"])
    _escribir_jsonl(os.path.join(salida, "evidencias_conservadas_libros.jsonl"),
                    conservadas["libros"])
    _escribir_jsonl(os.path.join(salida, "claves_excluir_consenso.jsonl"),
                    claves)
    _escribir_jsonl(os.path.join(salida, "muestra_revision.jsonl"),
                    muestra_revision(retiradas))

    informe = {
        "total_web": len(web),
        "total_libros": len(libros),
        "retiradas_web": len(retiradas["web"]),
        "retiradas_libros": len(retiradas["libros"]),
        "retiradas_total": len(todas_retiradas),
        "conservadas_web": len(conservadas["web"]),
        "conservadas_libros": len(conservadas["libros"]),
        "recuento_por_motivo": {},
        "recuento_detalle": {},
        "claves_excluir": len(claves),
        "afirmaciones_afectadas": afirm_afectadas,
        "cobertura_antes": antes,
        "cobertura_despues": despues,
    }
    for (etiqueta, fam, m), c in sorted(recuento.items()):
        informe["recuento_detalle"]["%s|%s|%s" % (etiqueta, fam, m)] = c
        informe["recuento_por_motivo"][m] = \
            informe["recuento_por_motivo"].get(m, 0) + c
    with open(os.path.join(salida, "informe_filtro.json"), "w",
             encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2)

    print("retiradas_total=%d (web=%d libros=%d)" % (
        len(todas_retiradas), len(retiradas["web"]), len(retiradas["libros"])))
    print("claves_excluir=%d afirmaciones_afectadas=%d" % (
        len(claves), afirm_afectadas))
    print("cobertura completas antes=%s despues=%s" % (
        antes.get("completas"), despues.get("completas")))
    return informe


if __name__ == "__main__":
    main()
