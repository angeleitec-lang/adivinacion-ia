#!/usr/bin/env python3
"""Revisor local de muestras: una página HTML autocontenida (T54).

Genera un único fichero HTML (CSS y JS inline, sin red ni CDN) con todas las
fichas de ``muestras.jsonl``, el texto resuelto en las fuentes y las banderas
de ``prerevision.jsonl``. La interfaz permite revisar una ficha a la vez con
atajos de teclado, guarda los veredictos en ``localStorage`` y exporta
``muestras_revisadas.jsonl`` en el esquema que lee ``muestras.py --accion oro``
(``id``, ``veredicto``, ``nota``, ``nivel``).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

BASE_POR_DEFECTO = "/Users/angelgonzalez/fase0"
MAX_TEXTO_POR_DEFECTO = 6000
VEREDICTOS = ("correcto", "dudoso", "incorrecto")
VERSION_DATOS = 1
NOMBRE_EXPORT = "muestras_revisadas.jsonl"


# ---------------------------------------------------------------------------
# Carga y construcción de fichas
# ---------------------------------------------------------------------------


def leer_jsonl(ruta):
    """Filas (dict) de un JSONL; ignora líneas vacías o inválidas."""
    filas = []
    with open(ruta, encoding="utf-8-sig") as fh:
        for linea in fh:
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


def inferir_base(ruta_muestras):
    """Base del corpus a partir de la ruta de ``muestras.jsonl``."""
    ruta = os.path.abspath(ruta_muestras)
    if os.path.basename(os.path.dirname(ruta)) == "muestras":
        return os.path.dirname(os.path.dirname(ruta))
    return BASE_POR_DEFECTO


def resolver_desde_base(base):
    """Devuelve ``fila -> (texto, procedencia)`` usando las fuentes del corpus.

    Importa ``muestras`` de forma perezosa: los tests pueden inyectar su
    propio resolvedor sin tocar disco.
    """
    import muestras

    crudos = {}
    for nivel in muestras.NIVELES:
        try:
            crudos[nivel] = {
                registro["id"]: registro
                for registro in muestras.cargar_registros(base, nivel)
            }
        except Exception:
            crudos[nivel] = {}
    resolvedor = muestras.Resolvedor(base)

    def resolver(fila):
        nivel = str(fila.get("nivel") or "")
        rid = str(fila.get("id") or "")
        crudo = crudos.get(nivel, {}).get(rid)
        if crudo is None:
            return "", "procedencia desconocida"
        try:
            texto = resolvedor.texto(nivel, crudo) or ""
        except Exception:
            texto = ""
        try:
            procedencia = muestras.procedencia_de(nivel, crudo, resolvedor) or ""
        except Exception:
            procedencia = "procedencia desconocida"
        return str(texto), str(procedencia)

    return resolver


def _entero(valor, defecto=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def _banderas(pre):
    salida = []
    for bandera in pre.get("banderas") or []:
        if not isinstance(bandera, dict):
            continue
        codigo = bandera.get("codigo")
        if not codigo:
            continue
        salida.append({
            "codigo": str(codigo),
            "motivo": str(bandera.get("motivo") or ""),
            "peso": _entero(bandera.get("peso")),
        })
    return salida


def construir_fichas(filas_muestras, filas_pre, resolver=None,
                     max_texto=MAX_TEXTO_POR_DEFECTO):
    """Fichas normalizadas para incrustar en el HTML.

    ``resolver`` es una función ``fila -> (texto, procedencia)``. Sin ella el
    texto queda vacío y la procedencia se marca como desconocida. Ignora filas
    sin ``id`` y deduplica por ``id`` conservando la primera aparición.
    """
    pre_por_id = {}
    for pre in filas_pre or []:
        if not isinstance(pre, dict):
            continue
        rid = pre.get("id")
        if rid is not None and str(rid) not in pre_por_id:
            pre_por_id[str(rid)] = pre

    fichas = []
    vistos = set()
    for fila in filas_muestras or []:
        if not isinstance(fila, dict):
            continue
        rid = fila.get("id")
        if rid is None or str(rid).strip() == "":
            continue
        rid = str(rid)
        if rid in vistos:
            continue
        vistos.add(rid)

        if resolver is not None:
            try:
                texto, procedencia = resolver(fila)
            except Exception:
                texto, procedencia = "", "procedencia desconocida"
        else:
            texto, procedencia = "", "procedencia desconocida"
        texto = texto if isinstance(texto, str) else ""
        procedencia = (procedencia if isinstance(procedencia, str)
                       else "")

        estrato = fila.get("estrato")
        if isinstance(estrato, (list, tuple)):
            estrato = " · ".join(str(parte) for parte in estrato)
        else:
            estrato = str(estrato or "")

        pre = pre_por_id.get(rid) or {}
        banderas = _banderas(pre)
        puntuacion = max(0, min(10, _entero(pre.get("puntuacion"))))

        fichas.append({
            "id": rid,
            "nivel": str(fila.get("nivel") or ""),
            "origen": str(fila.get("origen") or ""),
            "estrato": estrato,
            "entidad": str(fila.get("entidad_id") or ""),
            "faceta": str(fila.get("faceta") or ""),
            "sistema": str(fila.get("sistema") or ""),
            "calidad": fila.get("calidad"),
            "procedencia": procedencia,
            "texto": texto[:max_texto],
            "truncado": len(texto) > max_texto,
            "largo_original": len(texto),
            "banderas": banderas,
            "puntuacion": puntuacion,
        })
    return fichas


# ---------------------------------------------------------------------------
# Serialización segura y exportación
# ---------------------------------------------------------------------------


def json_para_html(objeto):
    """JSON seguro dentro de un ``<script>`` (escapa HTML y U+2028/2029)."""
    crudo = json.dumps(objeto, ensure_ascii=False, separators=(",", ":"))
    return (
        crudo.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def construir_lineas_export(fichas, veredictos, notas=None):
    """Filas revisadas con el esquema que lee ``muestras.py --accion oro``."""
    notas = notas or {}
    lineas = []
    for ficha in fichas or []:
        rid = str(ficha.get("id") or "")
        if not rid:
            continue
        veredicto = veredictos.get(rid)
        if veredicto not in VEREDICTOS:
            continue
        nota = notas.get(rid) or ""
        lineas.append({
            "id": rid,
            "veredicto": veredicto,
            "nota": str(nota),
            "nivel": str(ficha.get("nivel") or ""),
        })
    return lineas


def texto_export(lineas):
    """Texto JSONL del export, con salto final y sin ASCII escapado."""
    return "".join(
        json.dumps(linea, ensure_ascii=False) + "\n" for linea in lineas
    )


# ---------------------------------------------------------------------------
# Plantilla HTML
# ---------------------------------------------------------------------------


_PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisor de muestras — adivinación</title>
<style>
:root {
  --fondo: #f5f2ea;
  --panel: #fffdf8;
  --texto: #201c16;
  --suave: #6a6155;
  --borde: #dcd4c5;
  --acento: #74429b;
  --ok: #1d7a44;
  --duda: #a26800;
  --mal: #a52a2a;
  --barra: #e6dfd1;
  --sombra: 0 1px 3px rgba(30, 24, 16, 0.10);
}
@media (prefers-color-scheme: dark) {
  :root {
    --fondo: #141312;
    --panel: #1e1c19;
    --texto: #ece7dc;
    --suave: #a79d8e;
    --borde: #3b352e;
    --acento: #cba6ef;
    --ok: #6fd39a;
    --duda: #e8b45a;
    --mal: #ef8b8b;
    --barra: #2d2924;
    --sombra: 0 1px 3px rgba(0, 0, 0, 0.45);
  }
}
* { box-sizing: border-box; }
html { font-size: 19px; }
body {
  margin: 0;
  background: var(--fondo);
  color: var(--texto);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  line-height: 1.5;
}
header, nav, main, footer { max-width: 1000px; margin: 0 auto; }
header { padding: 1rem 1rem 0.5rem; }
h1 { font-size: 1.35rem; margin: 0 0 0.35rem; letter-spacing: 0.01em; }
.sub { margin: 0.15rem 0; color: var(--suave); font-size: 0.86rem; }
.barra {
  height: 9px;
  background: var(--barra);
  border-radius: 99px;
  overflow: hidden;
  margin: 0.6rem 0 0.25rem;
}
#barra-relleno {
  height: 100%;
  width: 0;
  background: var(--acento);
  transition: width 120ms ease-out;
}
.filtros {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem 1rem;
  align-items: center;
  padding: 0.6rem 1rem;
  font-size: 0.82rem;
  color: var(--suave);
}
.filtros label { display: inline-flex; gap: 0.35rem; align-items: center; }
select, textarea, button, input[type="checkbox"] {
  font: inherit;
  color: inherit;
}
select {
  background: var(--panel);
  border: 1px solid var(--borde);
  border-radius: 7px;
  padding: 0.15rem 0.4rem;
  font-size: 0.82rem;
}
#btn-lote {
  background: var(--panel);
  border: 1px solid var(--borde);
  border-radius: 7px;
  padding: 0.3rem 0.6rem;
  font-size: 0.78rem;
  cursor: pointer;
}
#btn-lote:disabled { opacity: 0.45; cursor: not-allowed; }
main { padding: 0.4rem 1rem 0.5rem; }
.ficha {
  background: var(--panel);
  border: 1px solid var(--borde);
  border-radius: 14px;
  box-shadow: var(--sombra);
  padding: 1.05rem 1.15rem 1.2rem;
}
.meta { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.55rem; }
.pill {
  display: inline-block;
  border: 1px solid var(--borde);
  border-radius: 99px;
  padding: 0.08rem 0.55rem;
  font-size: 0.72rem;
  color: var(--suave);
  white-space: nowrap;
}
.pill.punt-0 { border-color: var(--ok); color: var(--ok); }
.pill.punt-baja { border-color: var(--ok); color: var(--ok); }
.pill.punt-media { border-color: var(--duda); color: var(--duda); }
.pill.punt-alta { border-color: var(--mal); color: var(--mal); }
.pill.revisada { border-color: var(--acento); color: var(--acento); }
.linea { margin: 0.3rem 0; font-size: 0.88rem; }
.linea b { color: var(--suave); font-weight: 600; }
.banderas { margin: 0.6rem 0; padding: 0; list-style: none; }
.banderas li {
  border-left: 3px solid var(--duda);
  background: color-mix(in srgb, var(--duda) 8%, transparent);
  padding: 0.3rem 0.6rem;
  margin: 0.28rem 0;
  border-radius: 0 7px 7px 0;
  font-size: 0.86rem;
}
.banderas .codigo { font-weight: 700; }
.texto {
  margin: 0.85rem 0 0.35rem;
  padding: 0.8rem 0.9rem;
  border: 1px solid var(--borde);
  border-radius: 10px;
  background: color-mix(in srgb, var(--fondo) 55%, var(--panel));
  font-size: 1.08rem;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.texto.vacio { color: var(--suave); font-style: italic; }
.aviso-texto { font-size: 0.76rem; color: var(--suave); margin: 0.15rem 0 0; }
.ver-mas {
  margin-top: 0.45rem;
  background: transparent;
  border: 1px solid var(--borde);
  border-radius: 7px;
  padding: 0.28rem 0.65rem;
  font-size: 0.8rem;
  cursor: pointer;
  color: var(--acento);
}
.nota { display: block; margin-top: 0.9rem; font-size: 0.82rem; color: var(--suave); }
.nota textarea {
  display: block;
  width: 100%;
  min-height: 3.2rem;
  margin-top: 0.3rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--borde);
  border-radius: 9px;
  background: var(--panel);
  resize: vertical;
  font-size: 0.92rem;
}
.vacio-ficha { text-align: center; color: var(--suave); padding: 2rem 1rem; }
footer.acciones {
  position: sticky;
  bottom: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.65rem 1rem 0.9rem;
  background: color-mix(in srgb, var(--fondo) 88%, transparent);
  backdrop-filter: blur(6px);
}
footer.acciones button {
  border: 1px solid var(--borde);
  background: var(--panel);
  border-radius: 9px;
  padding: 0.45rem 0.8rem;
  font-size: 0.88rem;
  cursor: pointer;
  min-height: 2.3rem;
}
footer.acciones button:hover { border-color: var(--acento); }
footer.acciones button[data-veredicto="correcto"].activo {
  border-color: var(--ok); color: var(--ok); font-weight: 700;
}
footer.acciones button[data-veredicto="dudoso"].activo {
  border-color: var(--duda); color: var(--duda); font-weight: 700;
}
footer.acciones button[data-veredicto="incorrecto"].activo {
  border-color: var(--mal); color: var(--mal); font-weight: 700;
}
footer.acciones .sep { flex: 1 1 0.5rem; }
.acciones-io {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  padding: 0 1rem 0.8rem;
  max-width: 1000px;
  margin: 0 auto;
  font-size: 0.8rem;
  color: var(--suave);
}
.acciones-io button {
  border: 1px solid var(--borde);
  background: var(--panel);
  border-radius: 7px;
  padding: 0.35rem 0.7rem;
  font-size: 0.8rem;
  cursor: pointer;
}
#aviso {
  position: fixed;
  left: 50%;
  bottom: 5.2rem;
  transform: translateX(-50%) translateY(0.5rem);
  background: var(--texto);
  color: var(--fondo);
  padding: 0.45rem 0.9rem;
  border-radius: 9px;
  font-size: 0.82rem;
  opacity: 0;
  pointer-events: none;
  transition: opacity 140ms ease, transform 140ms ease;
  z-index: 20;
  max-width: 90vw;
  text-align: center;
}
#aviso.visible { opacity: 1; transform: translateX(-50%) translateY(0); }
[hidden] { display: none !important; }
@media (max-width: 620px) {
  html { font-size: 17px; }
  footer.acciones button { flex: 1 1 28%; }
}
</style>
</head>
<body>
<header>
  <h1>Revisor de muestras</h1>
  <p class="sub" id="contadores"></p>
  <p class="sub" id="resumen"></p>
  <div class="barra" role="progressbar" aria-label="Progreso de revisión">
    <div id="barra-relleno"></div>
  </div>
</header>

<nav class="filtros" aria-label="Filtros">
  <label>Nivel
    <select id="filtro-nivel"><option value="todos">todos</option></select>
  </label>
  <label><input type="checkbox" id="solo-marcadas"> Solo con banderas</label>
  <label><input type="checkbox" id="solo-sin-revisar"> Solo sin revisar</label>
  <label>Orden
    <select id="orden">
      <option value="sospecha">sospecha (mayor primero)</option>
      <option value="estrato">estrato</option>
      <option value="original">original</option>
    </select>
  </label>
  <label><input type="checkbox" id="modo-lote"> Modo lote</label>
  <button id="btn-lote" disabled>Marcar visibles limpias como correctas</button>
</nav>

<main>
  <article class="ficha" id="ficha" hidden></article>
  <p class="vacio-ficha" id="vacio">No hay fichas que mostrar (0 fichas).</p>
</main>

<footer class="acciones">
  <button data-veredicto="correcto" title="Atajo: 1">1 · Correcto</button>
  <button data-veredicto="dudoso" title="Atajo: 2">2 · Dudoso</button>
  <button data-veredicto="incorrecto" title="Atajo: 3">3 · Incorrecto</button>
  <span class="sep"></span>
  <button id="btn-anterior" title="Atajo: ← o K">← Anterior</button>
  <button id="btn-siguiente" title="Atajo: → o J">Siguiente →</button>
  <button id="btn-saltar" title="Atajo: S">Saltar</button>
  <button id="btn-deshacer" title="Atajo: U">↶ Deshacer</button>
</footer>

<div class="acciones-io">
  <button id="btn-exportar">Exportar muestras_revisadas.jsonl</button>
  <button id="btn-importar">Importar…</button>
  <input type="file" id="fichero-importar" accept=".jsonl,.json,application/json,text/plain" hidden>
  <span id="estado-guardado"></span>
</div>

<div id="aviso" role="status" aria-live="polite"></div>

<script id="datos-revisor" type="application/json">__DATOS__</script>

<script>
"use strict";

/* INICIO_EXPORT */
function construirLineasExport(fichas, veredictos, notas) {
  var validos = { correcto: true, dudoso: true, incorrecto: true };
  var lineas = [];
  for (var i = 0; i < fichas.length; i++) {
    var f = fichas[i];
    var veredicto = veredictos[f.id];
    if (!validos[veredicto]) {
      continue;
    }
    lineas.push({
      id: f.id,
      veredicto: veredicto,
      nota: String((notas && notas[f.id]) || ""),
      nivel: String(f.nivel || "")
    });
  }
  return lineas;
}
/* FIN_EXPORT */

var DATOS = JSON.parse(document.getElementById("datos-revisor").textContent);
var FICHAS = DATOS.fichas || [];
var CLAVE = "revisor-t54-v1";
var TEXTO_VISIBLE = 700;
var EXPANDIDOS = {};
var HISTORIAL = [];
var HAY_ALMACEN = true;
var idActual = null;

var ESTADO = {
  veredictos: {},
  notas: {},
  filtroNivel: "todos",
  soloMarcadas: false,
  soloSinRevisar: false,
  orden: "sospecha"
};

function porId(id) {
  for (var i = 0; i < FICHAS.length; i++) {
    if (FICHAS[i].id === id) {
      return FICHAS[i];
    }
  }
  return null;
}

function cargar() {
  try {
    var crudo = localStorage.getItem(CLAVE);
    if (!crudo) {
      return;
    }
    var guardado = JSON.parse(crudo);
    if (guardado && typeof guardado === "object") {
      ESTADO.veredictos = guardado.veredictos || {};
      ESTADO.notas = guardado.notas || {};
    }
  } catch (e) {
    HAY_ALMACEN = false;
  }
}

function guardar() {
  if (!HAY_ALMACEN) {
    return;
  }
  try {
    localStorage.setItem(CLAVE, JSON.stringify({
      veredictos: ESTADO.veredictos,
      notas: ESTADO.notas
    }));
  } catch (e) {
    HAY_ALMACEN = false;
    aviso("No se pudo guardar en el navegador; usa Exportar antes de cerrar.");
  }
}

function instantanea() {
  HISTORIAL.push(JSON.stringify({
    veredictos: ESTADO.veredictos,
    notas: ESTADO.notas
  }));
  if (HISTORIAL.length > 100) {
    HISTORIAL.shift();
  }
}

function revisada(f) {
  return Boolean(ESTADO.veredictos[f.id]);
}

function ordenadas(lista) {
  var copia = lista.slice();
  if (ESTADO.orden === "estrato") {
    copia.sort(function (a, b) {
      return String(a.estrato || "").localeCompare(String(b.estrato || ""), "es") ||
        (a.id < b.id ? -1 : (a.id > b.id ? 1 : 0));
    });
  } else if (ESTADO.orden === "sospecha") {
    copia.sort(function (a, b) {
      return (b.puntuacion - a.puntuacion) ||
        (a.id < b.id ? -1 : (a.id > b.id ? 1 : 0));
    });
  }
  return copia;
}

function visibles() {
  var lista = FICHAS.filter(function (f) {
    if (ESTADO.filtroNivel !== "todos" && f.nivel !== ESTADO.filtroNivel) {
      return false;
    }
    if (ESTADO.soloMarcadas && !(f.banderas.length > 0 || f.puntuacion > 0)) {
      return false;
    }
    if (ESTADO.soloSinRevisar && revisada(f)) {
      return false;
    }
    return true;
  });
  return ordenadas(lista);
}

function fichaActual() {
  return idActual ? porId(idActual) : null;
}

function esc(v) {
  return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g,
    function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[c];
    });
}

function clasePuntuacion(p) {
  if (p <= 0) {
    return "punt-0";
  }
  if (p <= 3) {
    return "punt-baja";
  }
  if (p <= 6) {
    return "punt-media";
  }
  return "punt-alta";
}

function textoContadores() {
  var porNivel = {};
  FICHAS.forEach(function (f) {
    if (!porNivel[f.nivel]) {
      porNivel[f.nivel] = { total: 0, revisadas: 0 };
    }
    porNivel[f.nivel].total += 1;
    if (revisada(f)) {
      porNivel[f.nivel].revisadas += 1;
    }
  });
  var partes = Object.keys(porNivel).sort().map(function (nivel) {
    var d = porNivel[nivel];
    return nivel + " " + d.revisadas + "/" + d.total;
  });
  return partes.join("   ·   ");
}

function actualizarCabecera(lista) {
  var total = FICHAS.length;
  var hechas = FICHAS.filter(revisada).length;
  document.getElementById("contadores").textContent = textoContadores() ||
    "Sin fichas";
  document.getElementById("resumen").textContent =
    hechas + " de " + total + " revisadas · mostrando " + lista.length;
  var relleno = document.getElementById("barra-relleno");
  relleno.style.width = (total ? (100 * hechas / total) : 0) + "%";
  relleno.parentNode.setAttribute("aria-valuenow", String(hechas));
  relleno.parentNode.setAttribute("aria-valuemax", String(total));
}

function render() {
  var lista = visibles();
  if (!lista.length) {
    idActual = null;
    document.getElementById("ficha").hidden = true;
    document.getElementById("vacio").hidden = false;
    document.getElementById("vacio").textContent = FICHAS.length
      ? "No hay fichas que cumplan los filtros."
      : "No hay fichas que mostrar (0 fichas).";
    actualizarCabecera(lista);
    return;
  }
  var posicion = -1;
  for (var i = 0; i < lista.length; i++) {
    if (lista[i].id === idActual) {
      posicion = i;
      break;
    }
  }
  if (posicion < 0) {
    posicion = 0;
    idActual = lista[0].id;
  }
  var f = lista[posicion];
  document.getElementById("vacio").hidden = true;
  var contenedor = document.getElementById("ficha");
  contenedor.hidden = false;
  contenedor.innerHTML = plantillaFicha(f, posicion, lista.length);
  conectarFicha(f);
  actualizarCabecera(lista);
  var botones = document.querySelectorAll("footer.acciones button[data-veredicto]");
  for (var j = 0; j < botones.length; j++) {
    botones[j].classList.toggle(
      "activo",
      ESTADO.veredictos[f.id] === botones[j].getAttribute("data-veredicto")
    );
  }
}

function plantillaFicha(f, posicion, total) {
  var partes = [];
  var veredicto = ESTADO.veredictos[f.id];
  partes.push('<div class="meta">');
  partes.push('<span class="pill">' + esc(f.nivel || "sin nivel") + "</span>");
  if (f.estrato) {
    partes.push('<span class="pill">' + esc(f.estrato) + "</span>");
  }
  partes.push('<span class="pill ' + clasePuntuacion(f.puntuacion) + '">' +
    "sospecha " + f.puntuacion + "/10</span>");
  partes.push('<span class="pill">' + (posicion + 1) + " / " + total +
    "</span>");
  if (veredicto) {
    partes.push('<span class="pill revisada">' + esc(veredicto) + "</span>");
  }
  partes.push("</div>");

  partes.push('<p class="linea"><b>Procedencia:</b> ' +
    (f.procedencia ? esc(f.procedencia) : "desconocida") + "</p>");
  var entidad = f.entidad || f.sistema || "?";
  var detalle = entidad;
  if (f.faceta) {
    detalle += " · " + f.faceta;
  }
  if (f.origen) {
    detalle += " (origen " + f.origen + ")";
  }
  if (f.calidad !== null && f.calidad !== undefined) {
    detalle += " (calidad " + f.calidad + ")";
  }
  partes.push('<p class="linea"><b>Entidad/faceta:</b> ' + esc(detalle) +
    "</p>");

  if (f.banderas && f.banderas.length) {
    partes.push('<ul class="banderas">');
    for (var i = 0; i < f.banderas.length; i++) {
      var b = f.banderas[i];
      partes.push("<li><span class=\\"codigo\\">" + esc(b.codigo) +
        "</span> (" + esc(b.peso) + "): " + esc(b.motivo) + "</li>");
    }
    partes.push("</ul>");
  }

  var expandido = Boolean(EXPANDIDOS[f.id]);
  var texto = f.texto || "";
  var recortado = false;
  if (!expandido && texto.length > TEXTO_VISIBLE) {
    texto = texto.slice(0, TEXTO_VISIBLE) + "…";
    recortado = true;
  }
  partes.push('<div class="texto' + (f.texto ? "" : " vacio") + '">' +
    (f.texto ? esc(texto) : "(sin texto)") + "</div>");
  if (f.texto.length > TEXTO_VISIBLE) {
    partes.push('<button class="ver-mas" id="btn-ver-mas">' +
      (expandido ? "Ver menos" : "Ver más") + "</button>");
  }
  if (f.truncado) {
    partes.push('<p class="aviso-texto">Texto guardado recortado: el ' +
      "original tiene " + f.largo_original + " caracteres.</p>");
  } else if (recortado) {
    partes.push('<p class="aviso-texto">Mostrando los primeros ' +
      TEXTO_VISIBLE + " caracteres.</p>");
  }

  partes.push('<label class="nota">Nota (N)' +
    '<textarea id="nota-ficha" placeholder="Observaciones para el conjunto ' +
    'de oro…">' + esc(ESTADO.notas[f.id] || "") + "</textarea></label>");
  return partes.join("");
}

function conectarFicha(f) {
  var nota = document.getElementById("nota-ficha");
  nota.addEventListener("input", function () {
    ESTADO.notas[f.id] = nota.value;
    guardar();
  });
  var verMas = document.getElementById("btn-ver-mas");
  if (verMas) {
    verMas.addEventListener("click", function () {
      if (EXPANDIDOS[f.id]) {
        delete EXPANDIDOS[f.id];
      } else {
        EXPANDIDOS[f.id] = true;
      }
      render();
    });
  }
}

function aviso(texto) {
  var el = document.getElementById("aviso");
  el.textContent = texto;
  el.classList.add("visible");
  clearTimeout(aviso._t);
  aviso._t = setTimeout(function () {
    el.classList.remove("visible");
  }, 2600);
}

function mover(delta) {
  var lista = visibles();
  if (!lista.length) {
    return;
  }
  var posicion = -1;
  for (var i = 0; i < lista.length; i++) {
    if (lista[i].id === idActual) {
      posicion = i;
      break;
    }
  }
  var destino = posicion < 0 ? 0 : posicion + delta;
  if (destino < 0) {
    destino = 0;
  }
  if (destino >= lista.length) {
    destino = lista.length - 1;
    if (delta > 0) {
      aviso("Fin de la lista filtrada");
    }
  }
  idActual = lista[destino].id;
  render();
}

function marcar(veredicto) {
  var f = fichaActual();
  if (!f) {
    return;
  }
  var antes = visibles();
  var posicion = -1;
  for (var i = 0; i < antes.length; i++) {
    if (antes[i].id === f.id) {
      posicion = i;
      break;
    }
  }
  instantanea();
  ESTADO.veredictos[f.id] = veredicto;
  guardar();
  var despues = visibles();
  var siguiente = null;
  for (var k = posicion + 1; k < antes.length; k++) {
    for (var m = 0; m < despues.length; m++) {
      if (despues[m].id === antes[k].id) {
        siguiente = antes[k].id;
        break;
      }
    }
    if (siguiente) {
      break;
    }
  }
  if (!siguiente && despues.length) {
    siguiente = despues[Math.min(posicion, despues.length - 1)].id;
  }
  idActual = siguiente;
  render();
}

function deshacer() {
  if (!HISTORIAL.length) {
    aviso("Nada que deshacer");
    return;
  }
  var anterior = JSON.parse(HISTORIAL.pop());
  ESTADO.veredictos = anterior.veredictos || {};
  ESTADO.notas = anterior.notas || {};
  guardar();
  render();
  aviso("Cambio deshecho");
}

function descargar(nombre, contenido) {
  var blob = new Blob([contenido], { type: "application/json;charset=utf-8" });
  var url = URL.createObjectURL(blob);
  var enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  document.body.removeChild(enlace);
  setTimeout(function () {
    URL.revokeObjectURL(url);
  }, 2000);
}

function exportar() {
  var lineas = construirLineasExport(FICHAS, ESTADO.veredictos, ESTADO.notas);
  if (!lineas.length) {
    aviso("Todavía no hay fichas revisadas que exportar");
    return;
  }
  descargar("muestras_revisadas.jsonl", lineas.map(function (linea) {
    return JSON.stringify(linea);
  }).join("\\n") + "\\n");
  aviso("Exportadas " + lineas.length + " fichas revisadas");
}

function importarTexto(texto) {
  var validos = { correcto: true, dudoso: true, incorrecto: true };
  var conocidas = {};
  FICHAS.forEach(function (f) {
    conocidas[f.id] = true;
  });
  var lineas = texto.split(/\\r?\\n/);
  var aplicadas = 0;
  var ignoradas = 0;
  var provisionales = {};
  var notas = {};
  for (var i = 0; i < lineas.length; i++) {
    if (!lineas[i].trim()) {
      continue;
    }
    var fila = null;
    try {
      fila = JSON.parse(lineas[i]);
    } catch (e) {
      ignoradas += 1;
      continue;
    }
    if (!fila || !conocidas[fila.id] || !validos[fila.veredicto]) {
      ignoradas += 1;
      continue;
    }
    provisionales[fila.id] = fila.veredicto;
    if (typeof fila.nota === "string" && fila.nota) {
      notas[fila.id] = fila.nota;
    }
    aplicadas += 1;
  }
  if (aplicadas) {
    instantanea();
    for (var rid in provisionales) {
      ESTADO.veredictos[rid] = provisionales[rid];
    }
    for (var nid in notas) {
      ESTADO.notas[nid] = notas[nid];
    }
    guardar();
  }
  render();
  aviso("Importadas " + aplicadas + " fichas" +
    (ignoradas ? " (" + ignoradas + " líneas ignoradas)" : ""));
}

function lote() {
  var marca = document.getElementById("modo-lote");
  if (!marca.checked) {
    return;
  }
  var candidatas = visibles().filter(function (f) {
    return f.puntuacion === 0 && f.banderas.length === 0 && !revisada(f);
  });
  if (!candidatas.length) {
    aviso("No hay fichas visibles sin banderas pendientes");
    return;
  }
  var ok = window.confirm(
    "¿Marcar " + candidatas.length + " fichas visibles sin banderas como " +
    "correctas? Se registrará la nota «lote». Puedes deshacer con U."
  );
  if (!ok) {
    return;
  }
  instantanea();
  for (var i = 0; i < candidatas.length; i++) {
    var f = candidatas[i];
    ESTADO.veredictos[f.id] = "correcto";
    var previa = ESTADO.notas[f.id];
    ESTADO.notas[f.id] = previa ? previa + " · lote" : "lote";
  }
  guardar();
  render();
  aviso("Marcadas " + candidatas.length + " fichas como correctas (lote)");
}

function iniciar() {
  cargar();
  var niveles = [];
  FICHAS.forEach(function (f) {
    if (niveles.indexOf(f.nivel) < 0) {
      niveles.push(f.nivel);
    }
  });
  niveles.sort();
  var selector = document.getElementById("filtro-nivel");
  niveles.forEach(function (nivel) {
    var opcion = document.createElement("option");
    opcion.value = nivel;
    opcion.textContent = nivel;
    selector.appendChild(opcion);
  });

  selector.addEventListener("change", function () {
    ESTADO.filtroNivel = selector.value;
    render();
  });
  var marcadas = document.getElementById("solo-marcadas");
  marcadas.addEventListener("change", function () {
    ESTADO.soloMarcadas = marcadas.checked;
    render();
  });
  var sinRevisar = document.getElementById("solo-sin-revisar");
  sinRevisar.addEventListener("change", function () {
    ESTADO.soloSinRevisar = sinRevisar.checked;
    render();
  });
  var orden = document.getElementById("orden");
  orden.addEventListener("change", function () {
    ESTADO.orden = orden.value;
    render();
  });

  document.querySelectorAll("footer.acciones button[data-veredicto]")
    .forEach(function (boton) {
      boton.addEventListener("click", function () {
        marcar(boton.getAttribute("data-veredicto"));
      });
    });
  document.getElementById("btn-siguiente")
    .addEventListener("click", function () { mover(1); });
  document.getElementById("btn-anterior")
    .addEventListener("click", function () { mover(-1); });
  document.getElementById("btn-saltar")
    .addEventListener("click", function () {
      mover(1);
      aviso("Ficha saltada");
    });
  document.getElementById("btn-deshacer")
    .addEventListener("click", deshacer);
  document.getElementById("btn-exportar")
    .addEventListener("click", exportar);
  document.getElementById("btn-importar")
    .addEventListener("click", function () {
      document.getElementById("fichero-importar").click();
    });
  document.getElementById("fichero-importar")
    .addEventListener("change", function (ev) {
      var fichero = ev.target.files && ev.target.files[0];
      if (!fichero) {
        return;
      }
      var lector = new FileReader();
      lector.onload = function () {
        importarTexto(String(lector.result || ""));
        ev.target.value = "";
      };
      lector.readAsText(fichero, "utf-8");
    });
  var modoLote = document.getElementById("modo-lote");
  var botonLote = document.getElementById("btn-lote");
  modoLote.addEventListener("change", function () {
    botonLote.disabled = !modoLote.checked;
  });
  botonLote.addEventListener("click", lote);

  document.addEventListener("keydown", function (ev) {
    var destino = ev.target;
    var escribiendo = destino && (
      destino.tagName === "TEXTAREA" ||
      destino.tagName === "INPUT" ||
      destino.tagName === "SELECT"
    );
    if (escribiendo) {
      if (ev.key === "Escape") {
        destino.blur();
      }
      return;
    }
    if (ev.metaKey || ev.ctrlKey || ev.altKey) {
      return;
    }
    var tecla = ev.key;
    if (tecla === "1") {
      marcar("correcto");
    } else if (tecla === "2") {
      marcar("dudoso");
    } else if (tecla === "3") {
      marcar("incorrecto");
    } else if (tecla === "ArrowRight" || tecla === "j" || tecla === "J") {
      mover(1);
    } else if (tecla === "ArrowLeft" || tecla === "k" || tecla === "K") {
      mover(-1);
    } else if (tecla === "n" || tecla === "N") {
      var nota = document.getElementById("nota-ficha");
      if (nota) {
        nota.focus();
        nota.setSelectionRange(nota.value.length, nota.value.length);
      }
    } else if (tecla === "u" || tecla === "U") {
      deshacer();
    } else if (tecla === "s" || tecla === "S") {
      mover(1);
    } else {
      return;
    }
    ev.preventDefault();
  });

  document.getElementById("estado-guardado").textContent = HAY_ALMACEN
    ? "Guardado automático en localStorage."
    : "Sin localStorage: exporta antes de cerrar.";

  var lista = visibles();
  idActual = lista.length ? lista[0].id : null;
  render();
}

iniciar();
</script>
</body>
</html>
"""


def generar_html(fichas, generado=None):
    """HTML autocontenido con las fichas incrustadas como JSON seguro."""
    datos = {
        "version": VERSION_DATOS,
        "generado": generado or datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M"),
        "total": len(fichas),
        "fichas": fichas,
    }
    return _PLANTILLA.replace("__DATOS__", json_para_html(datos))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Genera un revisor HTML autocontenido para la revisión "
                    "humana de muestras (T54).")
    parser.add_argument(
        "--muestras", required=True,
        help="JSONL de fichas (muestras.jsonl)")
    parser.add_argument(
        "--prerevision", default=None,
        help="JSONL de banderas y puntuaciones (prerevision.jsonl)")
    parser.add_argument(
        "--out", required=True, help="ruta del HTML de salida")
    parser.add_argument(
        "--base", default=None,
        help="base del corpus para resolver textos (por defecto se infiere "
             "de --muestras)")
    parser.add_argument(
        "--max-texto", dest="max_texto", type=int,
        default=MAX_TEXTO_POR_DEFECTO,
        help="caracteres máximos de texto por ficha (por defecto %d)"
             % MAX_TEXTO_POR_DEFECTO)
    args = parser.parse_args(argv)

    if args.max_texto < 1:
        parser.error("--max-texto debe ser positivo")
    filas = leer_jsonl(args.muestras)
    pre = leer_jsonl(args.prerevision) if args.prerevision else []
    base = args.base or inferir_base(args.muestras)
    fichas = construir_fichas(
        filas, pre, resolver=resolver_desde_base(base),
        max_texto=args.max_texto,
    )
    html = generar_html(fichas)
    directorio = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(directorio, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    tamano = os.path.getsize(args.out)
    marcadas = sum(1 for f in fichas if f["banderas"])
    print("%d fichas (%d con banderas) · %.1f MB · %s"
          % (len(fichas), marcadas, tamano / (1024 * 1024), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
