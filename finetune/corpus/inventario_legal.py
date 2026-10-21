"""Inventario de procedencia y licencias de todas las fuentes de fase 0.

Recorre manifiestos, metadatos de `knowledge/`, evidencias y afirmaciones para
producir una fila por fuente (dominio web, libro o vídeo) con su procedencia,
los indicios de dominio público que constan en los datos y una clasificación de
riesgo determinista. No consulta la red ni modifica los datos de origen.

La clasificación es una ayuda para la revisión legal futura, no un dictamen:
`libre` reúne dominio público y licencias CC compatibles; `consultar` señala
fuentes sin licencia explícita; `riesgo_alto` marca obras modernas con
copyright, contenido de pago o texto íntegro de una obra reciente.
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import tempfile
import unicodedata
from urllib.parse import urlparse

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(RAIZ, "finetune", "corpus")
FASE0_POR_DEFECTO = "/Users/angelgonzalez/fase0"
KNOWLEDGE_POR_DEFECTO = os.path.join(RAIZ, "finetune", "knowledge")

DOMINIOS_PD = ("archive.org", "gutenberg.org", "wikisource.org")
TIPOS_WEB = ("foro", "blog", "sitio", "guia", "portal", "revista")

_LICENCIAS_LIBRES = (
    "dominio publico", "public domain", "publico", "cc0", "cc by",
    "cc by sa", "creative commons",
)
_LICENCIAS_ALTAS = (
    "copyright", "reservad", "todos los derechos", "propietari", "pago",
    "suscripcion", "premium", "compra", "youtube",
)


def _slug(texto):
    """Minúsculas sin tildes ni signos, para comparar etiquetas de licencia."""
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def normalizar_dominio(dominio):
    """Dominio en minúsculas, sin `www.`, puerto ni barra final."""
    dominio = (dominio or "").strip().lower()
    if "://" in dominio:
        dominio = urlparse(dominio).netloc
    dominio = dominio.split("/", 1)[0]
    if dominio.startswith("www."):
        dominio = dominio[4:]
    if ":" in dominio:
        dominio = dominio.split(":", 1)[0]
    return dominio


def leer_jsonl(ruta):
    """Lee un JSONL y devuelve las filas válidas (los errores se omiten)."""
    filas = []
    try:
        archivo = open(ruta, encoding="utf-8")
    except FileNotFoundError:
        return filas
    with archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(fila, dict):
                filas.append(fila)
    return filas


def _fusionar(base, nueva):
    """Completa `base` con los valores no vacíos de `nueva`."""
    for clave, valor in nueva.items():
        if valor not in (None, "", [], {}):
            base[clave] = valor
    return base


def _anio(valor):
    try:
        return int(str(valor).strip()[:4])
    except (TypeError, ValueError):
        return None


def _anio_en_id(valor):
    """Año de publicación pegado al final de un id (p. ej. `...-1983`)."""
    coincidencia = re.search(r"(?:^|[-_])((?:1[7-9]\d{2}|20\d{2}))$", str(valor or ""))
    return int(coincidencia.group(1)) if coincidencia else None


def anio_fallecimiento(autor):
    """Año de fallecimiento a partir de fechas tipo `Encausse, Gérard, 1865-1916`."""
    if not autor:
        return None
    coincidencias = re.findall(r"\b(1[0-9]{3}|20[0-9]{2})\b", str(autor))
    if len(coincidencias) >= 2:
        return int(coincidencias[-1])
    return None


def _es_dominio_pd(url):
    url = (url or "").lower()
    return any(dominio in url for dominio in DOMINIOS_PD)


def indicios_dominio_publico(tipo, autor, anio, origen, licencia_hint,
                             anio_actual=None):
    """Lista legible de indicios de dominio público presentes en los metadatos."""
    if anio_actual is None:
        anio_actual = datetime.date.today().year
    indicios = []
    fallecimiento = anio_fallecimiento(autor)
    if fallecimiento and anio_actual - fallecimiento > 70:
        indicios.append(
            f"autor fallecido en {fallecimiento} (hace más de 70 años)")
    if anio and anio < 1931:
        indicios.append(f"publicado en {anio} (anterior a 1931)")
    hint = _slug(licencia_hint)
    if _es_dominio_pd(origen) and any(marca in hint for marca in
                                      ("dominio publico", "public domain",
                                       "publico", "cc0", "cc by")):
        indicios.append("repositorio de dominio público con licencia declarada")
    return indicios


def clasificar_riesgo(tipo, licencia_hint, indicios, anio=None,
                      estado_legal="", origen=""):
    """Clasifica una fuente en `libre`, `consultar` o `riesgo_alto`.

    Reglas deterministas, en este orden:
    1. Un indicio de dominio público o una licencia CC compatible -> libre.
    2. Copyright, licencia reservada, pago o una obra moderna sin indicios de
       dominio público -> riesgo_alto. Si una obra moderna no declara año, se
       deja en `consultar` para revisión manual.
    3. Todo lo demás (web comercial o blog sin licencia explícita, fuente sin
       metadatos) -> consultar.
    """
    hint = _slug(licencia_hint)
    estado = _slug(estado_legal)

    if indicios:
        return "libre"
    if "dominio publico" in estado or "public domain" in estado:
        return "libre"
    if any(marca in hint for marca in _LICENCIAS_LIBRES):
        if " nc " not in f" {hint} " and " nd " not in f" {hint} ":
            return "libre"
    if any(marca in hint for marca in _LICENCIAS_ALTAS):
        return "riesgo_alto"
    if "copyright" in estado or "vigente" in estado:
        return "riesgo_alto"
    if tipo == "libro" and anio and anio >= 1931:
        return "riesgo_alto"
    if tipo == "video":
        return "riesgo_alto"
    return "consultar"


def normalizar_familia(valor):
    """Reduce una etiqueta de familia a las cuatro familias del alcance."""
    for token in re.split(r"[^a-z0-9]+", _slug(valor)):
        if token.startswith("tarot"):
            return "tarot"
        if (token.startswith("baraja") or token in ("espanol", "espanola")
                or token.startswith("naipe")):
            return "baraja_espanola"
        if token.startswith("astro") or token.startswith("signo"):
            return "astrologia"
        if token.startswith("numerolog"):
            return "numerologia"
    return "desconocida"


def _periodo(valor, por_defecto="moderna"):
    valor = _slug(valor)
    if valor.startswith("clasic"):
        return "clasica"
    if valor.startswith("modern"):
        return "moderna"
    return por_defecto


def _contar_por_clave(filas, clave):
    cuenta = {}
    for fila in filas:
        valor = fila.get(clave)
        if valor:
            cuenta[valor] = cuenta.get(valor, 0) + 1
    return cuenta


def _contar_evidencias(evidencias):
    """Cuenta evidencias por fuente: dominio web normalizado o id de libro."""
    cuenta = {}
    for ev in evidencias:
        if ev.get("tipo") == "web":
            clave = normalizar_dominio(ev.get("dominio")
                                       or ev.get("fuente_id") or "")
        else:
            clave = ev.get("fuente_id")
        if clave:
            cuenta[clave] = cuenta.get(clave, 0) + 1
    return cuenta


def _es_afirmacion_web(afirmacion):
    """Las afirmaciones web llevan la URL como `fuente_id`; las de libro, su id."""
    return "://" in str(afirmacion.get("fuente_id") or "")


def _contar_afirmaciones_web(afirmaciones):
    cuenta = {}
    for af in afirmaciones:
        if not _es_afirmacion_web(af):
            continue
        clave = normalizar_dominio(af.get("dominio") or af.get("fuente_id"))
        if clave:
            cuenta[clave] = cuenta.get(clave, 0) + 1
    return cuenta


def _contar_afirmaciones_libro(afirmaciones):
    cuenta = {}
    for af in afirmaciones:
        if _es_afirmacion_web(af):
            continue
        fuente = af.get("fuente_id")
        if fuente:
            cuenta[fuente] = cuenta.get(fuente, 0) + 1
    return cuenta


def _metadatos_web(knowledge):
    """Índice de dominios web a partir de los ficheros de knowledge."""
    indice = {}
    for nombre in sorted(os.listdir(knowledge)):
        if not nombre.startswith("fuentes_") or not nombre.endswith(".jsonl"):
            continue
        for fila in leer_jsonl(os.path.join(knowledge, nombre)):
            dominio = normalizar_dominio(fila.get("dominio")
                                         or fila.get("url_ejemplo") or "")
            if not dominio:
                continue
            actual = indice.setdefault(dominio, {})
            _fusionar(actual, fila)
    return indice


def _clave_id(valor):
    """Id normalizado para emparejar variantes con y sin guiones."""
    return re.sub(r"[^a-z0-9]+", "", str(valor or "").lower())


def _metadatos_libros(knowledge):
    """Índice de libros: une todos los ficheros de knowledge, por id y alias."""
    indice = {}
    nombres = [
        "fuentes_libros.jsonl",
        "fuentes_libros_es.jsonl",
        "fuentes_libros_tema.jsonl",
        "fuentes_clasicas_pd.jsonl",
        "epubs_locales.jsonl",
        "libros_faltantes_legal.jsonl",
    ]
    presentes = [os.path.join(knowledge, n) for n in nombres
                 if os.path.exists(os.path.join(knowledge, n))]
    for nombre in sorted(os.listdir(knowledge)):
        if (nombre.endswith(".jsonl") and "libro" in nombre
                and "legal" in nombre
                and os.path.join(knowledge, nombre) not in presentes):
            presentes.append(os.path.join(knowledge, nombre))
    for ruta in presentes:
        for fila in leer_jsonl(ruta):
            libro_id = fila.get("id")
            if libro_id:
                _fusionar(indice.setdefault(libro_id, {}), fila)
                alias = _clave_id(libro_id)
                if alias != libro_id:
                    _fusionar(indice.setdefault(alias, {}), fila)
    return indice


def _manifiestos_web(fase0):
    rutas = [
        os.path.join(fase0, "web", "manifest.jsonl"),
        os.path.join(fase0, "web_recup2", "manifest.jsonl"),
        os.path.join(fase0, "web_recup3", "manifest.jsonl"),
        os.path.join(fase0, "web_recup4", "manifest.jsonl"),
        os.path.join(fase0, "web_recup_all", "manifest.jsonl"),
    ]
    paginas = {}
    for ruta in rutas:
        for fila in leer_jsonl(ruta):
            url = fila.get("url")
            if not url:
                continue
            dominio = normalizar_dominio(fila.get("dominio")
                                         or fila.get("sitio") or url)
            if not dominio:
                continue
            datos = paginas.setdefault(dominio, {"urls": {}, "familias": set(),
                                                 "ejemplo": None})
            usada = (fila.get("estado") == "ok"
                     and int(fila.get("chars") or 0) > 0)
            anterior = datos["urls"].get(url)
            datos["urls"][url] = usada or bool(anterior)
            if usada and not datos["ejemplo"]:
                datos["ejemplo"] = url
            familia = fila.get("familia")
            if familia:
                datos["familias"].add(familia)
    return paginas


def _secciones_usadas(fase0, libro_id):
    for sub in ("libros", "libros_clasicos_pd"):
        ruta = os.path.join(fase0, sub, "secciones", f"{libro_id}.jsonl")
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                return sum(1 for _ in f)
    return 0


def _videos_con_subtitulos(fase0):
    carpeta = os.path.join(fase0, "youtube", "raw_vtt")
    ids = set()
    if not os.path.isdir(carpeta):
        return ids
    for raiz, _, nombres in os.walk(carpeta):
        for nombre in nombres:
            if nombre.endswith(".vtt"):
                ids.add(nombre.split(".", 1)[0])
    return ids


def cargar_evidencias(fase0):
    """Evidencias canónicas de web y libros (sin las variantes `rapido`)."""
    rutas = [
        os.path.join(fase0, "evidencias_web", "evidencias.jsonl"),
        os.path.join(fase0, "libros", "evidencias", "evidencias.jsonl"),
    ]
    filas = []
    for ruta in rutas:
        filas.extend(leer_jsonl(ruta))
    return filas


def cargar_afirmaciones(fase0):
    rutas = [
        os.path.join(fase0, "afirmaciones_full", "afirmaciones.jsonl"),
        os.path.join(fase0, "afirmaciones_libros", "afirmaciones_libros.jsonl"),
    ]
    filas = []
    for ruta in rutas:
        filas.extend(leer_jsonl(ruta))
    return filas


def _fuentes_web(fase0, knowledge, evidencias, afirmaciones):
    paginas = _manifiestos_web(fase0)
    metadatos = _metadatos_web(knowledge)
    ev_web = _contar_evidencias([e for e in evidencias if e.get("tipo") == "web"])
    af_web = _contar_afirmaciones_web(afirmaciones)
    dominios = set(paginas) | set(ev_web) | set(af_web)
    dominios.discard("")

    filas = []
    for dominio in sorted(dominios):
        meta = metadatos.get(dominio, {})
        pagina = paginas.get(dominio, {})
        familias = meta.get("familias") or sorted(pagina.get("familias") or [])
        if isinstance(familias, str):
            familias = [familias]
        origen = (meta.get("url_ejemplo") or pagina.get("ejemplo")
                  or f"https://{dominio}")
        licencia = (meta.get("licencia_hint") or meta.get("licencia")
                    or "desconocida")
        periodo = _periodo(meta.get("periodo"))
        anio = _anio(meta.get("anio"))
        indicios = indicios_dominio_publico(
            "web", meta.get("autor"), anio, origen, licencia)
        if dominio in ("wikipedia.org", "es.wikipedia.org"):
            indicios.append("Wikipedia con licencia CC BY-SA")
        riesgo = clasificar_riesgo("web", licencia, indicios, anio,
                                   meta.get("estado_legal", ""), origen)
        filas.append({
            "id": dominio,
            "tipo": "web",
            "origen": origen,
            "idioma": meta.get("idioma") or "es",
            "periodo": periodo,
            "familia": normalizar_familia("/".join(familias)) if familias else "desconocida",
            "autor": meta.get("autor") or "",
            "anio": anio or "",
            "licencia_hint": licencia,
            "indicios_dominio_publico": indicios,
            "n_paginas": sum(1 for usada in pagina.get("urls", {}).values() if usada),
            "n_evidencias": ev_web.get(dominio, 0),
            "n_afirmaciones": af_web.get(dominio, 0),
            "riesgo": riesgo,
        })
    return filas


def _manifest_clasicos(fase0):
    ruta = os.path.join(fase0, "libros", "manifiesto_clasicos_pd.jsonl")
    indice = {}
    for fila in leer_jsonl(ruta):
        if fila.get("id"):
            _fusionar(indice.setdefault(fila["id"], {}), fila)
    return indice


def _fuentes_libro(fase0, knowledge, evidencias, afirmaciones):
    metadatos = _metadatos_libros(knowledge)
    manifiesto = _manifest_clasicos(fase0)
    ev_libro = _contar_evidencias([e for e in evidencias if e.get("tipo") != "web"])
    af_libro = _contar_afirmaciones_libro(afirmaciones)
    hashes = {}
    for ev in evidencias:
        if ev.get("tipo") != "web" and ev.get("fuente_id") and ev.get("hash_seccion"):
            hashes.setdefault(ev["fuente_id"], set()).add(ev["hash_seccion"])

    ids = set(manifiesto) | set(ev_libro) | set(af_libro)
    ids.discard("")

    filas = []
    for libro_id in sorted(ids):
        meta = dict(manifiesto.get(libro_id, {}))
        for clave in (libro_id, _clave_id(libro_id)):
            _fusionar(meta, metadatos.get(clave, {}))
        evidencia_meta = next(
            (e for e in evidencias
             if e.get("tipo") != "web" and e.get("fuente_id") == libro_id), {})
        origen = meta.get("url_texto") or meta.get("fuente") or ""
        licencia = meta.get("licencia_hint") or meta.get("licencia") or "desconocida"
        anio = _anio(meta.get("anio")) or _anio_en_id(libro_id)
        periodo = _periodo(meta.get("periodo") or evidencia_meta.get("periodo"),
                           "clasica" if (anio and anio < 1931) else "moderna")
        indicios = indicios_dominio_publico(
            "libro", meta.get("autor"), anio, origen, licencia)
        riesgo = clasificar_riesgo(
            "libro", licencia, indicios, anio, meta.get("estado_legal", ""), origen)
        paginas = _secciones_usadas(fase0, libro_id)
        if not paginas:
            paginas = len(hashes.get(libro_id, ()))
        filas.append({
            "id": libro_id,
            "tipo": "libro",
            "origen": origen,
            "idioma": meta.get("idioma") or evidencia_meta.get("idioma") or "",
            "periodo": periodo,
            "familia": normalizar_familia(
                meta.get("familia") or evidencia_meta.get("dominio")),
            "autor": meta.get("autor") or "",
            "anio": anio or "",
            "licencia_hint": licencia,
            "indicios_dominio_publico": indicios,
            "n_paginas": paginas,
            "n_evidencias": ev_libro.get(libro_id, 0),
            "n_afirmaciones": af_libro.get(libro_id, 0),
            "riesgo": riesgo,
        })
    return filas


def _fuentes_video(fase0):
    catalogo = leer_jsonl(os.path.join(fase0, "youtube", "catalogo.jsonl"))
    por_id = {v.get("id"): v for v in catalogo if v.get("id")}
    con_vtt = _videos_con_subtitulos(fase0)
    filas = []
    for video_id in sorted(con_vtt):
        video = por_id.get(video_id, {})
        origen = f"https://www.youtube.com/watch?v={video_id}"
        filas.append({
            "id": video_id,
            "tipo": "video",
            "origen": origen,
            "idioma": "es",
            "periodo": "moderna",
            "familia": normalizar_familia(video.get("familia")),
            "autor": video.get("canal") or "",
            "anio": (str(video.get("fecha"))[:4] if video.get("fecha") else ""),
            "licencia_hint": "reservada_youtube",
            "indicios_dominio_publico": [],
            "n_paginas": 1 if video_id in con_vtt else 0,
            "n_evidencias": 0,
            "n_afirmaciones": 0,
            "riesgo": clasificar_riesgo(
                "video", "reservada_youtube", [], None, "", origen),
        })
    return filas


def construir_inventario(fase0=FASE0_POR_DEFECTO,
                         knowledge=KNOWLEDGE_POR_DEFECTO):
    """Construye la lista de fuentes con sus dependencias y riesgo."""
    evidencias = cargar_evidencias(fase0)
    afirmaciones = cargar_afirmaciones(fase0)
    fuentes = (_fuentes_web(fase0, knowledge, evidencias, afirmaciones)
               + _fuentes_libro(fase0, knowledge, evidencias, afirmaciones)
               + _fuentes_video(fase0))
    fuentes.sort(key=lambda f: (f["tipo"], f["id"]))
    return {"fuentes": fuentes, "evidencias": evidencias, "afirmaciones": afirmaciones}


def resumen_por_riesgo_y_familia(fuentes):
    """Cuenta fuentes, evidencias y afirmaciones por riesgo y familia."""
    resumen = {}
    for fuente in fuentes:
        familia = fuente["familia"]
        clave = (fuente["riesgo"], familia)
        datos = resumen.setdefault(clave, {
            "riesgo": fuente["riesgo"], "familia": familia,
            "fuentes": 0, "evidencias": 0, "afirmaciones": 0})
        datos["fuentes"] += 1
        datos["evidencias"] += fuente["n_evidencias"]
        datos["afirmaciones"] += fuente["n_afirmaciones"]
    return [resumen[clave] for clave in sorted(resumen)]


def fuentes_de_riesgo_no_libre(fuentes, limite=20):
    """Las fuentes con riesgo distinto de `libre` que más peso acumulan."""
    candidatas = [f for f in fuentes if f["riesgo"] != "libre"]
    candidatas.sort(key=lambda f: (-(f["n_evidencias"] + f["n_afirmaciones"]),
                                   f["tipo"], f["id"]))
    return candidatas[:limite]


def _riesgo_por_fuente(fuentes):
    """Índice para filtrar evidencias: dominio web o id de libro."""
    return {(f["tipo"], f["id"]): f["riesgo"] for f in fuentes}


def filtrar_evidencias(evidencias, fuentes, riesgos_excluidos=("riesgo_alto",)):
    """Devuelve las evidencias que no dependen de fuentes excluidas."""
    riesgos = _riesgo_por_fuente(fuentes)
    conservadas = []
    for ev in evidencias:
        if ev.get("tipo") == "web":
            clave = ("web", normalizar_dominio(ev.get("dominio")
                                               or ev.get("fuente_id") or ""))
        else:
            clave = ("libro", ev.get("fuente_id"))
        if riesgos.get(clave) in riesgos_excluidos:
            continue
        conservadas.append(ev)
    return conservadas


def impacto_exclusion(evidencias, fuentes):
    """Celdas de cobertura que se perderían al excluir fuentes de riesgo alto."""
    if CORPUS not in sys.path:
        sys.path.insert(0, CORPUS)
    import cobertura

    with tempfile.TemporaryDirectory(prefix="inventario_legal_") as temporal:
        ruta_completa = os.path.join(temporal, "evidencias.jsonl")
        ruta_filtrada = os.path.join(temporal, "evidencias_sin_riesgo.jsonl")
        with open(ruta_completa, "w", encoding="utf-8") as f:
            for ev in evidencias:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        filtradas = filtrar_evidencias(evidencias, fuentes)
        with open(ruta_filtrada, "w", encoding="utf-8") as f:
            for ev in filtradas:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

        catalogo = cobertura.entidades()
        completas, _ = cobertura.leer_evidencias([ruta_completa])
        sin_riesgo, _ = cobertura.leer_evidencias([ruta_filtrada])
        antes = cobertura.calcular_cobertura(completas, catalogo=catalogo)
        despues = cobertura.calcular_cobertura(sin_riesgo, catalogo=catalogo)

    perdidas = []
    for celda_antes, celda_despues in zip(antes["celdas"], despues["celdas"]):
        if celda_antes["completa"] and not celda_despues["completa"]:
            perdidas.append({
                "entidad_id": celda_despues["entidad_id"],
                "faceta": celda_despues["faceta"],
                "faltan": celda_despues["faltan"],
            })
    return {
        "celdas_totales": len(antes["celdas"]),
        "completas_antes": antes["completas"],
        "completas_despues": despues["completas"],
        "perdidas": len(perdidas),
        "detalle": perdidas,
        "resumen_antes": cobertura.resumen_por_familia(antes, catalogo),
        "resumen_despues": cobertura.resumen_por_familia(despues, catalogo),
    }


CABECERAS_CSV = [
    "id", "tipo", "origen", "idioma", "periodo", "familia", "autor", "anio",
    "licencia_hint", "indicios_dominio_publico", "n_paginas", "n_evidencias",
    "n_afirmaciones", "riesgo",
]


def escribir_csv(fuentes, ruta):
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=CABECERAS_CSV)
        escritor.writeheader()
        for fuente in fuentes:
            fila = dict(fuente)
            fila["indicios_dominio_publico"] = " | ".join(
                fuente["indicios_dominio_publico"])
            escritor.writerow({clave: fila.get(clave, "") for clave in CABECERAS_CSV})


def escribir_json(fuentes, ruta, impacto=None):
    datos = {"fuentes": fuentes}
    if impacto is not None:
        datos["impacto_exclusion_riesgo_alto"] = impacto
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _tabla_resumen(resumen):
    lineas = [
        "| Riesgo | Familia | Fuentes | Evidencias | Afirmaciones |",
        "|---|---|---|---|---|",
    ]
    for datos in resumen:
        lineas.append(
            f"| {datos['riesgo']} | {datos['familia']} | {datos['fuentes']} "
            f"| {datos['evidencias']} | {datos['afirmaciones']} |")
    return lineas


def _tabla_fuentes(fuentes):
    lineas = [
        "| Fuente | Tipo | Familia | Evidencias | Afirmaciones | Riesgo |",
        "|---|---|---|---|---|---|",
    ]
    for fuente in fuentes:
        lineas.append(
            f"| `{fuente['id']}` | {fuente['tipo']} | {fuente['familia']} "
            f"| {fuente['n_evidencias']} | {fuente['n_afirmaciones']} "
            f"| {fuente['riesgo']} |")
    return lineas


def escribir_md(fuentes, impacto, ruta):
    """Informe legible y reproducible a partir del inventario calculado."""
    total = len(fuentes)
    por_riesgo = {}
    for fuente in fuentes:
        por_riesgo[fuente["riesgo"]] = por_riesgo.get(fuente["riesgo"], 0) + 1
    resumen = resumen_por_riesgo_y_familia(fuentes)
    consultar = [f for f in fuentes if f["riesgo"] == "consultar"]
    consultar.sort(key=lambda f: (-(f["n_evidencias"] + f["n_afirmaciones"]),
                                  f["tipo"], f["id"]))
    alto = [f for f in fuentes if f["riesgo"] == "riesgo_alto"]
    alto.sort(key=lambda f: (-(f["n_evidencias"] + f["n_afirmaciones"]),
                             f["tipo"], f["id"]))

    lineas = [
        "# Inventario de procedencia y licencias",
        "",
        "Generado por `finetune/corpus/inventario_legal.py` a partir de los",
        "manifiestos, `finetune/knowledge/`, las evidencias y las afirmaciones de",
        "fase 0. No se ha consultado la red: la clasificación se basa solo en los",
        "metadatos disponibles y es una ayuda para la revisión legal, no un",
        "dictamen.",
        "",
        "## Cómo leer el riesgo",
        "",
        "- `libre`: dominio público o licencia CC compatible declarada en los datos.",
        "- `consultar`: web comercial, foro o blog sin licencia explícita; también",
        "  fuentes sin metadatos suficientes.",
        "- `riesgo_alto`: obra moderna con copyright, contenido de pago o vídeo de",
        "  plataforma; requiere permiso, licencia o sustitución antes de un modelo",
        "  comercial.",
        "",
        "## Resumen",
        "",
        f"- Fuentes inventariadas: {total}",
    ]
    for riesgo in ("libre", "consultar", "riesgo_alto"):
        lineas.append(f"- {riesgo}: {por_riesgo.get(riesgo, 0)}")
    lineas += ["", "### Por riesgo y familia", ""] + _tabla_resumen(resumen)

    lineas += [
        "",
        "## Las 20 fuentes de riesgo no libre con más peso",
        "",
        "Ordenadas por evidencias + afirmaciones que dependen de ellas.",
        "",
    ]
    lineas += _tabla_fuentes(fuentes_de_riesgo_no_libre(fuentes, 20))

    lineas += [
        "",
        "## Fuentes a consultar, contactar o sustituir para un modelo comercial",
        "",
        "### Riesgo alto",
        "",
    ]
    lineas += _tabla_fuentes(alto) if alto else ["No hay fuentes de riesgo alto."]
    lineas += ["", "### Consultar", ""]
    lineas += _tabla_fuentes(consultar) if consultar else [
        "No hay fuentes pendientes de consulta."]

    lineas += [
        "",
        "## Qué cambiaría si se excluyeran las fuentes de riesgo alto",
        "",
        f"- Celdas de la matriz: {impacto['celdas_totales']}",
        f"- Celdas completas ahora: {impacto['completas_antes']}",
        f"- Celdas completas sin fuentes de riesgo alto: "
        f"{impacto['completas_despues']}",
        f"- Celdas que perderían la condición de completa: {impacto['perdidas']}",
        "",
        "### Comparación por familia",
        "",
        "| Familia | Completas ahora | Completas sin riesgo alto |",
        "|---|---|---|",
    ]
    for familia, antes in impacto["resumen_antes"].items():
        despues = impacto["resumen_despues"].get(familia, {})
        lineas.append(
            f"| {familia} | {antes['completas']}/{antes['celdas']} "
            f"| {despues.get('completas', 0)}/{despues.get('celdas', antes['celdas'])} |")
    if impacto["detalle"]:
        lineas += ["", "### Celdas afectadas", ""]
        for celda in impacto["detalle"]:
            lineas.append(
                f"- `{celda['entidad_id']}` · {celda['faceta']}: "
                + "; ".join(celda["faltan"]))

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inventario de procedencia y licencias de las fuentes de fase 0.")
    parser.add_argument("--fase0", default=FASE0_POR_DEFECTO,
                        help="raíz de los datos de fase 0 (solo lectura)")
    parser.add_argument("--knowledge", default=KNOWLEDGE_POR_DEFECTO,
                        help="directorio de metadatos de fuentes")
    parser.add_argument("--out-dir", default=os.path.join(FASE0_POR_DEFECTO,
                                                         "inventario_legal"),
                        help="directorio de salida del CSV y el JSON")
    parser.add_argument("--md", default=os.path.join(RAIZ, "docs",
                                                     "INVENTARIO_LEGAL.md"),
                        help="ruta del informe markdown")
    parser.add_argument("--dry-run", action="store_true",
                        help="calcula y resume sin escribir ficheros")
    args = parser.parse_args(argv)

    inventario = construir_inventario(args.fase0, args.knowledge)
    fuentes = inventario["fuentes"]
    impacto = impacto_exclusion(inventario["evidencias"], fuentes)
    if args.dry_run:
        print(f"Fuentes: {len(fuentes)}; celdas completas: "
              f"{impacto['completas_antes']}; perdidas sin riesgo alto: "
              f"{impacto['perdidas']}")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    escribir_csv(fuentes, os.path.join(args.out_dir, "inventario_legal.csv"))
    escribir_json(fuentes, os.path.join(args.out_dir, "inventario_legal.json"),
                  impacto)
    os.makedirs(os.path.dirname(os.path.abspath(args.md)), exist_ok=True)
    escribir_md(fuentes, impacto, args.md)
    print(f"Inventario escrito en {args.out_dir} y {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
