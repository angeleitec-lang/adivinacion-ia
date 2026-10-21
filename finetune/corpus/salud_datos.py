"""Vigilancia barata, reparación opt-in y copias de seguridad de fase 0.

Recorre los JSONL clave de `/Users/angelgonzalez/fase0/`, comprueba su
integridad (líneas rotas, truncamientos, campos obligatorios, duplicados y
distribuciones), detecta ficheros que siguen creciendo y, solo si se pide,
retira la última línea truncada o crea una copia comprimida con manifiesto de
SHA-256. Por defecto no modifica nada.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

BASE_DEFECTO = "/Users/angelgonzalez/fase0"
BACKUPS_DEFECTO = "/Users/angelgonzalez/fase0_backups"
MIN_LIBRE_GB = 20.0
INTERVALO_VIGILANCIA = 5.0
MAX_COPIAS = 5

DIRS_CLAVE = (
    "afirmaciones_full",
    "afirmaciones_libros",
    "evidencias_web",
    "lecturas",
    "muestras",
    "web",
    "libros/evidencias",
)
SUELTOS_CLAVE = (
    "libros/manifiesto_clasicos_pd.jsonl",
    "plan_recuperacion.jsonl",
    "piloto_fase1/piloto.jsonl",
    "piloto_fase1/piloto_errores.jsonl",
)
CAMPOS_DISTRIBUCION = ("familia", "periodo", "calidad", "tipo", "estado",
                       "nivel", "idioma", "sistema", "dominio")

AFIRMACIONES = {
    "requeridos": ("entidad_id", "faceta", "fuente_id", "dominio", "periodo",
                   "calidad", "afirmacion"),
    "clave": ("entidad_id", "faceta", "fuente_id", "afirmacion"),
}
AFIRMACIONES_LIBROS = {
    "requeridos": ("entidad_id", "faceta", "fuente_id", "dominio", "periodo",
                   "calidad", "afirmacion", "cita_original", "contradice_kb"),
    "clave": ("entidad_id", "faceta", "fuente_id", "afirmacion"),
}
PROCESADOS_AFIRMACIONES = {
    "requeridos": ("hash_seccion", "entidad_id", "faceta", "estado",
                   "n_afirmaciones"),
    "clave": ("hash_seccion", "entidad_id", "faceta"),
}
PROCESADOS_LECTURAS = {
    "requeridos": ("hash_seccion", "estado", "sistema", "calidad"),
    "clave": ("hash_seccion",),
}
EVIDENCIAS = {
    "requeridos": ("entidad_id", "faceta", "fuente_id", "dominio", "idioma",
                   "periodo", "calidad", "tipo", "hash_seccion"),
    "clave": ("hash_seccion", "entidad_id", "faceta"),
}
JUICIOS = {
    "requeridos": ("hash", "fuente_id", "titulo", "candidatos", "juicio"),
    "clave": ("hash",),
}
LECTURAS = {
    "requeridos": ("id", "fuente", "sistema", "calidad", "idioma", "texto"),
    "clave": ("id",),
}
CANDIDATAS = {
    "requeridos": ("hash_seccion", "id_libro", "seccion"),
    "clave": ("hash_seccion",),
}
MUESTRAS = {
    "requeridos": ("id", "nivel", "origen", "calidad"),
    "clave": ("id",),
}
PREREVISION = {
    "requeridos": ("id", "nivel", "puntuacion"),
    "clave": ("id",),
}
MANIFEST_WEB = {
    "requeridos": ("url", "sitio", "dominio", "familia", "estado"),
    "clave": ("url",),
}
CALIDAD_WEB = {
    "requeridos": ("ruta", "dominio", "sha256", "caracteres"),
    "clave": ("ruta",),
}
MANIFIESTO_CLASICOS = {
    "requeridos": ("id", "estado", "url_texto"),
    "clave": ("id",),
}
PILOTO = {
    "requeridos": ("id", "familia", "ok"),
    "clave": ("id",),
}
GENERICO = {"requeridos": (), "clave": ("id",)}


def _es_excluido(nombre):
    # T67 (B6): «.bak» como subcadena ocultaba ficheros legítimos (p. ej.
    # naipes.bakery-ventas.jsonl). Solo excluyen los sufijos reales de copia:
    # «.bak-...» (copia diaria) o nombre terminado en «.bak».
    return (".bak-" in nombre or nombre.endswith(".bak")
            or ".truncada" in nombre
            or nombre.endswith(".tmp") or nombre.startswith("."))


def descubrir_ficheros(base=BASE_DEFECTO):
    """JSONL clave de fase 0: solo los de interés, nunca crudo ni secciones."""
    rutas = []
    for directorio in DIRS_CLAVE:
        ruta_dir = os.path.join(base, directorio)
        if not os.path.isdir(ruta_dir):
            continue
        for nombre in sorted(os.listdir(ruta_dir)):
            if not nombre.endswith(".jsonl") or _es_excluido(nombre):
                continue
            ruta = os.path.join(ruta_dir, nombre)
            if os.path.isfile(ruta):
                rutas.append(ruta)
    for relativo in SUELTOS_CLAVE:
        ruta = os.path.join(base, relativo)
        if os.path.isfile(ruta):
            rutas.append(ruta)
    return sorted(dict.fromkeys(rutas))


def esquema_de(ruta):
    """Campos obligatorios y clave de duplicado según el fichero."""
    nombre = os.path.basename(ruta)
    padre = os.path.basename(os.path.dirname(os.path.abspath(ruta)))
    if nombre == "procesados.jsonl":
        if padre in ("afirmaciones_full", "afirmaciones_libros",
                     "afirmaciones"):
            return PROCESADOS_AFIRMACIONES
        return PROCESADOS_LECTURAS
    if nombre == "afirmaciones_libros.jsonl":
        return AFIRMACIONES_LIBROS
    if nombre == "afirmaciones.jsonl":
        return AFIRMACIONES
    if nombre == "evidencias.jsonl":
        return EVIDENCIAS
    if nombre == "juicios.jsonl":
        return JUICIOS
    if nombre == "lecturas.jsonl":
        return LECTURAS
    if nombre == "candidatas.jsonl":
        return CANDIDATAS
    if nombre == "muestras.jsonl":
        return MUESTRAS
    if nombre == "prerevision.jsonl":
        return PREREVISION
    if nombre == "manifest.jsonl":
        return MANIFEST_WEB
    if nombre == "calidad.jsonl":
        return CALIDAD_WEB
    if nombre == "manifiesto_clasicos_pd.jsonl":
        return MANIFIESTO_CLASICOS
    if nombre.startswith("piloto"):
        return PILOTO
    return GENERICO


def _valor_clave(valor):
    try:
        hash(valor)
        return valor
    except TypeError:
        return json.dumps(valor, sort_keys=True, ensure_ascii=False)


def _formatear_clave(campos, clave):
    return ", ".join("%s=%r" % (campo, valor)
                     for campo, valor in zip(campos, clave))


def _problema(nivel, texto):
    return {"nivel": nivel, "texto": texto}


def analizar_fichero(ruta, crece=False):
    """Analiza un JSONL sin modificarlo y devuelve el diagnóstico completo."""
    esquema = esquema_de(ruta)
    requeridos = esquema["requeridos"]
    campos_clave = esquema["clave"]
    est = os.stat(ruta)
    invalidas = []
    vacias = []
    ausentes = []
    duplicados_exactos = []
    duplicados_clave = []
    vistos_exactos = {}
    vistos_clave = {}
    distribuciones = {}
    lineas = 0
    ultima_sin_salto = False
    termina_en_salto = True

    with open(ruta, "rb") as fh:
        for numero, bruto in enumerate(fh, 1):
            lineas = numero
            termina_en_salto = bruto.endswith(b"\n")
            contenido = bruto.rstrip(b"\r\n")
            if not contenido.strip():
                vacias.append(numero)
                continue
            try:
                texto = contenido.decode("utf-8")
            except UnicodeDecodeError as exc:
                invalidas.append((numero, "no es UTF-8 válido (%s)" % exc))
                continue
            try:
                objeto = json.loads(texto)
            except json.JSONDecodeError as exc:
                invalidas.append((numero, "JSON inválido (%s)" % exc.msg))
                continue
            if not isinstance(objeto, dict):
                invalidas.append((numero, "no es objeto JSON (%s)"
                                  % type(objeto).__name__))
                continue
            for campo in requeridos:
                if campo not in objeto:
                    ausentes.append((numero, campo))
            huella = hashlib.sha256(contenido).hexdigest()
            if huella in vistos_exactos:
                duplicados_exactos.append((numero, vistos_exactos[huella]))
            else:
                vistos_exactos[huella] = numero
            if all(campo in objeto for campo in campos_clave):
                clave = tuple(_valor_clave(objeto[campo])
                              for campo in campos_clave)
                if clave in vistos_clave:
                    duplicados_clave.append(
                        (clave, numero, vistos_clave[clave]))
                else:
                    vistos_clave[clave] = numero
            for campo in CAMPOS_DISTRIBUCION:
                if campo in objeto:
                    valor = str(objeto[campo])
                    por_campo = distribuciones.setdefault(campo, {})
                    por_campo[valor] = por_campo.get(valor, 0) + 1

    numeros_invalidos = {numero for numero, _ in invalidas}
    ultima_truncada = lineas > 0 and lineas in numeros_invalidos
    if ultima_truncada:
        invalidas = [
            (numero, "última línea truncada (%s)" % motivo
             if numero == lineas else motivo)
            for numero, motivo in invalidas
        ]
    if lineas > 0 and not termina_en_salto and not ultima_truncada:
        ultima_sin_salto = True

    problemas = []
    for numero, motivo in invalidas:
        problemas.append(_problema("grave", "línea %d: %s"
                                   % (numero, motivo)))
    for numero, campo in ausentes:
        problemas.append(_problema("grave", "línea %d: falta el campo `%s`"
                                   % (numero, campo)))
    for numero, primero in duplicados_exactos:
        problemas.append(_problema("avisar", "línea %d: duplicado exacto de "
                                   "la línea %d" % (numero, primero)))
    for clave, numero, primero in duplicados_clave:
        problemas.append(_problema(
            "avisar", "línea %d: duplicado por clave (%s) de la línea %d"
            % (numero, _formatear_clave(campos_clave, clave), primero)))
    for numero in vacias:
        problemas.append(_problema("avisar", "línea %d: línea en blanco"
                                   % numero))
    if ultima_sin_salto:
        problemas.append(_problema("avisar", "la última línea (%d) no termina "
                                   "en salto de línea" % lineas))
    if lineas == 0:
        problemas.append(_problema("avisar", "fichero vacío (0 líneas)"))

    nivel = "OK"
    if any(p["nivel"] == "grave" for p in problemas):
        nivel = "grave"
    elif problemas:
        nivel = "avisar"

    return {
        "ruta": ruta,
        "esquema": esquema,
        "lineas": lineas,
        "bytes": est.st_size,
        "mtime": est.st_mtime,
        "crece": bool(crece),
        "invalidas": invalidas,
        "vacias": vacias,
        "campos_ausentes": ausentes,
        "duplicados_exactos": duplicados_exactos,
        "duplicados_clave": duplicados_clave,
        "distribuciones": distribuciones,
        "ultima_truncada": ultima_truncada,
        "ultima_sin_salto": ultima_sin_salto,
        "problemas": problemas,
        "nivel": nivel,
    }


def _procesos_con_fichero_abierto(ruta):
    """PIDs que tienen el fichero abierto, si `lsof` está disponible."""
    try:
        salida = subprocess.run(["lsof", "-t", "--", ruta],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    if salida.returncode != 0:
        return []
    return [linea.strip() for linea in salida.stdout.splitlines()
            if linea.strip()]


def detectar_crecimiento(rutas, intervalo=INTERVALO_VIGILANCIA,
                         comprobar_lsof=True):
    """Compara dos lecturas separadas `intervalo` segundos y mira `lsof`."""
    rutas = list(rutas)
    inicial = {}
    for ruta in rutas:
        try:
            est = os.stat(ruta)
        except OSError:
            inicial[ruta] = None
            continue
        inicial[ruta] = (est.st_size, est.st_mtime_ns)
    if intervalo and intervalo > 0:
        time.sleep(intervalo)
    crece = {}
    for ruta in rutas:
        antes = inicial.get(ruta)
        try:
            est = os.stat(ruta)
        except OSError:
            crece[ruta] = False
            continue
        despues = (est.st_size, est.st_mtime_ns)
        cambio = antes is not None and despues != antes
        abierto = bool(_procesos_con_fichero_abierto(ruta)) if comprobar_lsof \
            else False
        crece[ruta] = bool(cambio or abierto)
    return crece


def _sello(ahora=None, formato="%Y%m%d-%H%M%S"):
    if isinstance(ahora, str):
        return ahora
    momento = ahora or datetime.datetime.now()
    return momento.strftime(formato)


def _copia_segura(ruta, sello):
    destino = "%s.bak-%s" % (ruta, sello)
    shutil.copy2(ruta, destino)
    return destino


def reparar_ficheros(rutas, si=False, intervalo=INTERVALO_VIGILANCIA,
                     comprobar_lsof=True, ahora=None):
    """Retira la última línea truncada, siempre tras copia y nunca si crece."""
    rutas = list(rutas)
    crece = detectar_crecimiento(rutas, intervalo=intervalo,
                                 comprobar_lsof=comprobar_lsof)
    fecha = datetime.datetime.now()
    sello_completo = _sello(ahora or fecha, "%Y%m%d-%H%M%S")
    sello_dia = _sello(ahora or fecha, "%Y%m%d")
    acciones = []
    for ruta in rutas:
        diagnostico = analizar_fichero(ruta, crece=crece.get(ruta, False))
        if not diagnostico["ultima_truncada"]:
            continue
        if crece.get(ruta):
            acciones.append({"ruta": ruta, "estado": "omitido_creciendo",
                             "motivo": "el fichero sigue creciendo o está "
                                       "abierto en escritura"})
            continue
        if not si:
            acciones.append({"ruta": ruta, "estado": "omitido_sin_si",
                             "motivo": "hace falta --si para reparar"})
            continue
        respaldo = _copia_segura(ruta, sello_completo)
        with open(ruta, "rb") as fh:
            partes = fh.readlines()
        ultima = partes[-1] if partes else b""
        prefijo = b"".join(partes[:-1])
        # T67 (B6): el truncado se escribe en un .tmp y se sustituye con
        # os.replace; si el proceso muere a medias, el original intacto sigue
        # en pie (antes se vaciaba el fichero y se reescribía a mano).
        tmp = "%s.tmp" % ruta
        with open(tmp, "wb") as fh:
            fh.write(prefijo)
        os.replace(tmp, ruta)
        ruta_truncada = "%s.truncada-%s" % (ruta, sello_dia)
        with open(ruta_truncada, "ab") as fh:
            if os.path.exists(ruta_truncada) and os.path.getsize(ruta_truncada) > 0:
                fh.write(b"\n")
            fh.write(ultima)
        acciones.append({"ruta": ruta, "estado": "reparado",
                         "linea": diagnostico["lineas"],
                         "bytes_movidos": len(ultima),
                         "copia": respaldo,
                         "truncada": ruta_truncada})
    return acciones


def _leer_hasta_linea_completa(ruta):
    with open(ruta, "rb") as fh:
        datos = fh.read()
    corte = datos.rfind(b"\n")
    return datos[:corte + 1] if corte >= 0 else b""


def rotar_copias(base=BACKUPS_DEFECTO, max_copias=MAX_COPIAS):
    """Conserva solo las `max_copias` carpetas AAAAMMDD-HHMM más recientes."""
    if not os.path.isdir(base):
        return []
    patron = re.compile(r"^\d{8}-\d{4}$")
    carpetas = sorted(n for n in os.listdir(base)
                      if patron.match(n)
                      and os.path.isdir(os.path.join(base, n)))
    sobrantes = carpetas[:-max_copias] if max_copias > 0 else carpetas
    for nombre in sobrantes:
        shutil.rmtree(os.path.join(base, nombre))
    return sobrantes


class _BytesDe:
    def __init__(self, datos):
        self.datos = datos
        self.pos = 0

    def read(self, tamano=-1):
        if tamano < 0:
            trozo = self.datos[self.pos:]
            self.pos = len(self.datos)
            return trozo
        trozo = self.datos[self.pos:self.pos + tamano]
        self.pos += len(trozo)
        return trozo


def crear_copia(base=BASE_DEFECTO, backups=BACKUPS_DEFECTO,
                min_libre_gb=MIN_LIBRE_GB, ahora=None,
                intervalo=1.0, comprobar_lsof=True, max_copias=MAX_COPIAS):
    """Copia comprimida de los JSONL clave, con manifiesto SHA-256."""
    os.makedirs(backups, exist_ok=True)
    libre_gb = shutil.disk_usage(backups).free / (1024.0 ** 3)
    if libre_gb < min_libre_gb:
        raise RuntimeError("espacio libre insuficiente: %.1f GB (mínimo %.1f)"
                           % (libre_gb, min_libre_gb))
    sello = _sello(ahora)
    destino = os.path.join(backups, sello)
    os.makedirs(destino, exist_ok=True)
    rutas = descubrir_ficheros(base)
    crece = detectar_crecimiento(rutas, intervalo=intervalo,
                                 comprobar_lsof=comprobar_lsof)
    tar_ruta = os.path.join(destino, "fase0-datos-%s.tar.gz" % sello)
    ficheros = {}
    with tarfile.open(tar_ruta, "w:gz") as archivo:
        for ruta in rutas:
            if crece.get(ruta):
                datos = _leer_hasta_linea_completa(ruta)
            else:
                with open(ruta, "rb") as fh:
                    datos = fh.read()
            arcname = os.path.relpath(ruta, base).replace(os.sep, "/")
            info = tarfile.TarInfo(arcname)
            info.size = len(datos)
            info.mtime = int(os.stat(ruta).st_mtime)
            archivo.addfile(info, _BytesDe(datos))
            ficheros[arcname] = {
                "sha256": hashlib.sha256(datos).hexdigest(),
                "bytes": len(datos),
            }
    manifest_ruta = os.path.join(destino, "manifiesto_sha256.json")
    with open(manifest_ruta, "w", encoding="utf-8") as fh:
        json.dump({"fecha": sello, "base": base, "ficheros": ficheros},
                  fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    rotadas = rotar_copias(backups, max_copias=max_copias)
    return {"directorio": destino, "tar": tar_ruta,
            "manifiesto": manifest_ruta, "ficheros": ficheros,
            "rotadas": rotadas, "libre_gb": libre_gb}


def restaurar_miembro(tar_ruta, miembro, destino):
    """Extrae un miembro concreto del tar para verificar la restauración."""
    with tarfile.open(tar_ruta, "r:gz") as archivo:
        extraido = archivo.extractfile(miembro)
        datos = extraido.read()
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with open(destino, "wb") as fh:
        fh.write(datos)
    return destino


def _tamano_legible(bytes_):
    for unidad in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024 or unidad == "GB":
            if unidad == "B":
                return "%d B" % bytes_
            return "%.1f %s" % (bytes_, unidad)
        bytes_ /= 1024.0
    return "%d B" % bytes_


def _fecha_legible(marca):
    return datetime.datetime.fromtimestamp(marca).strftime("%Y-%m-%d %H:%M:%S")


def _distribucion_texto(nombre, valores, maximo=None):
    elementos = sorted(valores.items(), key=lambda par: (-par[1], par[0]))
    total = len(elementos)
    if maximo:
        elementos = elementos[:maximo]
    texto = ", ".join("%s=%d" % (valor, cuenta)
                      for valor, cuenta in elementos)
    if maximo and total > maximo:
        texto += " (y %d valores más)" % (total - maximo)
    return "- %s: %s" % (nombre, texto or "(sin datos)")


def generar_informe(resultados, salida, base=BASE_DEFECTO, vigilar=False):
    """Escribe el informe markdown en español con semáforo y líneas exactas."""
    niveles = {r["nivel"] for r in resultados}
    global_ = "grave" if "grave" in niveles else \
        ("avisar" if "avisar" in niveles else "OK")
    lineas = [
        "# Salud de los datos de fase 0",
        "",
        "Fecha: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
        "Base: `%s`" % base,
        "",
        "Semáforo global: **%s**" % global_.upper(),
        "",
        "## Resumen por fichero",
        "",
        "| Fichero | Semáforo | Líneas | Tamaño | Modificado | Crece |",
        "|---|---|---:|---:|---|---|",
    ]
    for resultado in resultados:
        relativo = os.path.relpath(resultado["ruta"], base)
        crece = "sí" if resultado["crece"] else ("no" if vigilar else "-")
        lineas.append("| `%s` | %s | %d | %s | %s | %s |" % (
            relativo, resultado["nivel"].upper(), resultado["lineas"],
            _tamano_legible(resultado["bytes"]),
            _fecha_legible(resultado["mtime"]), crece))
    lineas.extend(["", "## Problemas", ""])
    con_problemas = [r for r in resultados if r["problemas"]]
    if not con_problemas:
        lineas.append("Sin problemas detectados en los ficheros revisados.")
    for resultado in con_problemas:
        relativo = os.path.relpath(resultado["ruta"], base)
        lineas.append("### %s · `%s`" % (resultado["nivel"].upper(), relativo))
        lineas.append("")
        for problema in resultado["problemas"][:50]:
            lineas.append("- %s" % problema["texto"])
        restantes = len(resultado["problemas"]) - 50
        if restantes > 0:
            lineas.append("- ... y %d problemas más" % restantes)
        lineas.append("")
    lineas.extend(["", "## Distribuciones", ""])
    for resultado in resultados:
        if not resultado["distribuciones"]:
            continue
        relativo = os.path.relpath(resultado["ruta"], base)
        lineas.append("### `%s`" % relativo)
        lineas.append("")
        for campo in CAMPOS_DISTRIBUCION:
            valores = resultado["distribuciones"].get(campo)
            if valores:
                maximo = 10 if campo in ("dominio", "familia", "sistema") \
                    else None
                lineas.append(_distribucion_texto(campo, valores, maximo))
        lineas.append("")
    os.makedirs(os.path.dirname(os.path.abspath(salida)) or ".", exist_ok=True)
    with open(salida, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lineas).rstrip() + "\n")
    return salida


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE_DEFECTO)
    parser.add_argument("--salida", default="salud_datos.md")
    parser.add_argument("--vigilar", action="store_true",
                        help="compara dos lecturas separadas --intervalo")
    parser.add_argument("--intervalo", type=float,
                        default=INTERVALO_VIGILANCIA)
    parser.add_argument("--reparar", action="store_true",
                        help="retira la última línea truncada (requiere --si)")
    parser.add_argument("--si", action="store_true",
                        help="confirma la reparación")
    parser.add_argument("--copia", action="store_true",
                        help="crea una copia comprimida con manifiesto")
    parser.add_argument("--backups", default=BACKUPS_DEFECTO)
    parser.add_argument("--min-libre-gb", type=float, default=MIN_LIBRE_GB)
    args = parser.parse_args(argv)

    rutas = descubrir_ficheros(args.base)
    if not rutas:
        print("No se han encontrado JSONL clave en %s" % args.base,
              file=sys.stderr)
        return 2

    if args.copia:
        try:
            copia = crear_copia(args.base, args.backups,
                                min_libre_gb=args.min_libre_gb,
                                intervalo=args.intervalo)
        except RuntimeError as exc:
            print("Copia abortada: %s" % exc, file=sys.stderr)
            return 2
        print("Copia creada: %s (%d ficheros, %.1f GB libres)"
              % (copia["tar"], len(copia["ficheros"]), copia["libre_gb"]))
        if copia["rotadas"]:
            print("Copias rotadas: %s" % ", ".join(copia["rotadas"]))

    if args.reparar:
        acciones = reparar_ficheros(rutas, si=args.si,
                                    intervalo=args.intervalo)
        for accion in acciones:
            print("%s: %s%s" % (
                os.path.relpath(accion["ruta"], args.base), accion["estado"],
                " (%s)" % accion.get("motivo", "") if accion.get("motivo")
                else ""))
        if not args.si and any(a["estado"] == "omitido_sin_si"
                               for a in acciones):
            print("Nada reparado: repite con --reparar --si", file=sys.stderr)
        if not acciones:
            print("No hay últimas líneas truncadas que reparar.")

    crece = {}
    if args.vigilar:
        crece = detectar_crecimiento(rutas, intervalo=args.intervalo)
    resultados = [analizar_fichero(ruta, crece=crece.get(ruta, False))
                  for ruta in rutas]
    generar_informe(resultados, args.salida, base=args.base,
                    vigilar=args.vigilar)
    graves = sum(1 for r in resultados if r["nivel"] == "grave")
    avisos = sum(1 for r in resultados if r["nivel"] == "avisar")
    ok = len(resultados) - graves - avisos
    print("Informe: %s (%d OK, %d avisar, %d grave)"
          % (args.salida, ok, avisos, graves))
    for resultado in resultados:
        if resultado["nivel"] != "OK":
            print("  %s: %s" % (os.path.relpath(resultado["ruta"], args.base),
                                resultado["nivel"].upper()))
    if graves:
        return 2
    if avisos:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
