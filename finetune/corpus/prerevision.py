#!/usr/bin/env python3
"""Prerevisión de la muestra: banderas de calidad y puntuación de sospecha.

Recorre ``muestras.jsonl``, resuelve el texto real de cada ficha en las
fuentes y aplica comprobaciones deterministas (texto vacío, ruido, idioma,
mojibake, otra entidad, promesas vedadas, contradicciones con la KB,
lecturas incoherentes y duplicados). No modifica la muestra original.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import afirmaciones_es
import cartas
import fase1_prompts
import muestras
import web_calidad
from generate_synthetic import ES_WORDS, es_score

try:
    from web_extraer import FRASES_RUIDO
except Exception:  # pragma: no cover - dependencia opcional
    FRASES_RUIDO = [
        "suscríbete",
        "suscribete",
        "subscribe",
        "compra",
        "comprar",
        "buy",
        "añadir al carrito",
        "agregar al carrito",
        "add to cart",
        "ver productos",
        "lee también",
        "regístrate",
        "iniciar sesión",
        "cookie",
        "política de privacidad",
        "privacy policy",
        "aceptar cookies",
        "publicidad",
        "newsletter",
        "síguenos",
        "follow us",
        "compártelo",
        "share",
        "whatsapp",
        "telegram",
        "facebook",
        "twitter",
        "instagram",
    ]


UMBRAL_TEXTO = {
    "afirmaciones": 20,
    "web": 80,
    "libros": 80,
    "lecturas": 80,
    "consenso": 40,
}

PESOS = {
    "sin_texto": 10,
    "texto_corto": 4,
    "ruido_navegacion": 4,
    "ruido_comercial": 3,
    "no_espanol": 5,
    "mojibake": 5,
    "otra_carta": 6,
    "promesa_vedada": 8,
    "contradiccion_kb": 7,
    "lectura_invalida": 6,
    "duplicada": 5,
}

_CLAVES_RUIDO_FUERTE = {
    "añadir al carrito",
    "agregar al carrito",
    "add to cart",
    "suscríbete",
    "suscribete",
    "subscribe",
    "iniciar sesión",
    "regístrate",
    "sign up",
    "política de privacidad",
    "privacy policy",
    "aceptar cookies",
    "accept cookies",
    "compra ahora",
    "buy now",
    "ver productos",
    "lee también",
    "leer también",
    "read also",
}

_RX_MOJIBAKE = re.compile(r"Ã[\x80-\xBF]|Â[\x80-\xBF]|â€|\ufffd")
_RX_PORTUGUES = re.compile(r"\b(não|nao|você|voce|também|tambem|através|atraves)\b|ções?\b")
_RX_CLAUSULA = re.compile(r"[.;,:!?\n]+")
_RX_PALO = re.compile(r"\b(bastos|copas|espadas|oros)\b")
_RX_ELEMENTO = re.compile(r"\b(fuego|agua|aire|tierra)\b")
_RX_ATRIBUCION = re.compile(
    r"(elemento|se asocia(?: con)?|asociad[oa]s?|relacionad[oa]s?|pertenece|"
    r"corresponde|regid[oa]s?|vinculad[oa]s?)"
)
_RX_AUTO_REFERENCIA = re.compile(r"\b(la carta|esta carta|el naipe|este naipe)\b")
_RX_CONCEPTO_NUMERO = re.compile(
    r"(camino de vida|numero de destino|numero del destino|destino|expresion|alma|personalidad)"
)

_FUNCIONALES_ES = set(ES_WORDS) | {
    "se",
    "lo",
    "le",
    "les",
    "sus",
    "este",
    "esta",
    "estos",
    "estas",
    "cuando",
    "donde",
    "porque",
    "aunque",
    "mientras",
    "también",
    "tiene",
    "puede",
    "hace",
    "desde",
    "hasta",
    "entre",
    "otro",
    "otra",
    "todo",
    "toda",
    "nada",
    "siempre",
    "nunca",
    "ser",
    "estar",
    "son",
    "fue",
    "ha",
    "han",
}

_NOMBRES_CARTA = {
    carta["id"]: carta["nombre"]
    for carta in list(cartas.CARTAS_TAROT) + list(cartas.NAIPES_ESPANOLES)
}


def _nfc(texto: Any) -> str:
    return unicodedata.normalize("NFC", texto if isinstance(texto, str) else "")


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _recorte(texto: str, largo: int) -> str:
    limpio = re.sub(r"\s+", " ", _nfc(texto)).strip()
    if len(limpio) <= largo:
        return limpio
    return limpio[: largo - 1].rstrip() + "…"


def cargar_elementos(ruta_kb: Optional[str] = None) -> Dict[str, str]:
    ruta = Path(ruta_kb) if ruta_kb else Path(__file__).resolve().parent / "kb" / "tarot.json"
    try:
        with ruta.open(encoding="utf-8") as fh:
            kb = json.load(fh)
    except (OSError, ValueError):
        return {}
    elementos = {}
    for menor in kb.get("menores", []):
        palo = menor.get("palo")
        elemento = menor.get("elemento")
        if palo and elemento:
            elementos[str(palo).lower()] = str(elemento).lower()
    return elementos


def bandera_sin_texto(texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return "sin texto legible"
    return None


def bandera_texto_corto(texto: Any, nivel: str = "") -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    largo = len(re.sub(r"\s+", " ", texto).strip())
    minimo = UMBRAL_TEXTO.get(nivel, 80)
    if largo < minimo:
        return f"texto de {largo} caracteres (mínimo {minimo} para {nivel or 'el nivel'})"
    return None


def bandera_ruido_navegacion(texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    if web_calidad.bandera_ruido_navegacion(texto):
        return "bloque de navegación o pie de página"
    return None


def bandera_ruido_comercial(texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    bajo = _nfc(texto).lower()
    encontradas = [
        frase
        for frase in FRASES_RUIDO
        if re.search(r"(?<!\w)" + re.escape(frase) + r"(?!\w)", bajo)
    ]
    distintas = sorted(set(encontradas))
    fuertes = [frase for frase in distintas if frase in _CLAVES_RUIDO_FUERTE]
    if fuertes:
        return "frase comercial o de suscripción: " + ", ".join(fuertes[:4])
    if len(distintas) >= 3:
        return "varias frases de reclamo: " + ", ".join(distintas[:4])
    return None


def bandera_no_espanol(texto: Any, minimo_palabras: int = 15) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    normalizado = _nfc(texto)
    palabras = re.findall(r"[a-záéíóúüñ]+", normalizado.lower())
    if len(palabras) < minimo_palabras:
        return None
    marcas_portuguesas = len(_RX_PORTUGUES.findall(normalizado.lower()))
    if marcas_portuguesas >= 2:
        return f"posible texto en portugués ({marcas_portuguesas} marcas)"
    funcionales = sum(1 for palabra in palabras if palabra in _FUNCIONALES_ES)
    indice = funcionales / len(palabras)
    if indice < 0.08 and es_score(normalizado) < 0.10:
        return (
            f"posible texto no español (índice de palabras funcionales "
            f"{indice:.2f} en {len(palabras)} palabras)"
        )
    return None


def bandera_mojibake(texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    coincide = _RX_MOJIBAKE.search(texto)
    if coincide:
        return f"secuencia de codificación rota: «{coincide.group(0)}»"
    return None


def _signos_mencionados(texto: str) -> set:
    plano = _sin_acentos(_nfc(texto).lower())
    return {
        signo
        for signo in fase1_prompts.ZODIACO
        if re.search(r"\b" + re.escape(signo) + r"\b", plano)
    }


def _motivo_numero(entidad_id: str, texto: str) -> Optional[str]:
    propio = re.match(r"^(\d{1,2})\|", entidad_id)
    if not propio:
        return None
    numero_propio = int(propio.group(1))
    plano = _sin_acentos(_nfc(texto).lower())
    for hallazgo in _RX_CONCEPTO_NUMERO.finditer(plano):
        ventana = plano[hallazgo.end() : hallazgo.end() + 45]
        cifra = re.search(r"\b(\d{1,2})\b", ventana)
        if not cifra:
            continue
        if int(cifra.group(1)) == numero_propio:
            continue
        contexto = plano[max(0, hallazgo.start() - 10) : cifra.end() + hallazgo.end()]
        if re.search(r"\b" + str(numero_propio) + r"\b", contexto):
            continue
        return (
            f"atribuye el número {cifra.group(1)} a «{hallazgo.group(1)}» "
            f"cuando la entidad es {numero_propio}"
        )
    return None


def bandera_otra_entidad(registro: Dict[str, Any], texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    entidad_id = str(registro.get("entidad_id") or "")
    faceta = str(registro.get("faceta") or "").lower()
    if not entidad_id:
        return None
    if entidad_id.startswith(("tarot-", "naipe-")):
        if "|" in entidad_id or "combinacion" in faceta:
            return None
        try:
            if afirmaciones_es.menciona_otra_carta(texto, entidad_id):
                return "menciona una carta distinta de la entidad"
        except Exception:
            return None
        return None
    if "|" in entidad_id:
        partes = entidad_id.split("|")
        if len(partes) != 2:
            return None
        sufijo = partes[1]
        if sufijo == "signo":
            propio = _sin_acentos(partes[0].lower())
            mencionados = _signos_mencionados(texto)
            ajenos = sorted(mencionados - {propio})
            if ajenos and propio not in mencionados:
                return "menciona otro signo sin nombrar el propio: " + ", ".join(ajenos)
            return None
        if sufijo.startswith("camino_de_vida") or sufijo.startswith("numero"):
            return _motivo_numero(entidad_id, texto)
    return None


def bandera_promesa_vedada(texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    motivos: List[str] = []
    try:
        fase1_prompts._verif_promesas(texto, motivos)
        fase1_prompts._verif_juego(texto, motivos)
    except Exception:
        return None
    if motivos:
        return "; ".join(dict.fromkeys(motivos))
    return None


def bandera_contradiccion_kb(
    registro: Dict[str, Any], texto: Any, elementos: Optional[Dict[str, str]] = None
) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    entidad_id = str(registro.get("entidad_id") or "")
    coincide = re.match(r"^(?:tarot|naipe)-([a-z]+)-\d+$", entidad_id)
    if not coincide:
        return None
    palo = coincide.group(1)
    esperado = (elementos or {}).get(palo)
    if not esperado:
        return None
    propio = _NOMBRES_CARTA.get(entidad_id, "").lower()
    for clausula in _RX_CLAUSULA.split(texto):
        bajo = _nfc(clausula).lower().strip()
        if not bajo:
            continue
        palos = set(_RX_PALO.findall(bajo))
        if palos and palo not in palos:
            continue
        referencia_propia = palo in palos or (bool(propio) and propio in bajo)
        if not referencia_propia:
            if _RX_AUTO_REFERENCIA.search(bajo) and not palos:
                referencia_propia = True
        if not referencia_propia:
            continue
        for atribucion in _RX_ATRIBUCION.finditer(bajo):
            resto = bajo[atribucion.end() :]
            elemento = _RX_ELEMENTO.search(resto[:45])
            if not elemento:
                continue
            if elemento.group(1) != esperado:
                return (
                    f"cláusula «{_recorte(clausula.strip(), 120)}» atribuye "
                    f"{elemento.group(1)} cuando la KB dice {esperado}"
                )
    return None


def _reconstruir_tirada(registro: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if registro.get("nivel") != "lecturas":
        return None
    if str(registro.get("idioma") or "").lower() != "es":
        return None
    sistema = str(registro.get("sistema") or "")
    if sistema not in ("tarot", "baraja_espanola"):
        return None
    crudas = registro.get("cartas")
    if not isinstance(crudas, list) or not crudas:
        return None
    tirada = []
    for carta in crudas:
        if not isinstance(carta, str) or not carta.strip():
            continue
        nombre = _nfc(carta).strip()
        invertida = bool(re.search(r"\s+invertid[oa]$", nombre, flags=re.IGNORECASE))
        if invertida:
            nombre = re.sub(r"\s+invertid[oa]$", "", nombre, flags=re.IGNORECASE).strip()
        tirada.append({"nombre": nombre, "invertida": invertida})
    if not tirada:
        return None
    catalogo = cartas.NAIPES_ESPANOLES if sistema == "baraja_espanola" else cartas.CARTAS_TAROT
    return {
        "cartas": tirada,
        "universo_cartas": [{"nombre": carta["nombre"]} for carta in catalogo],
    }


def bandera_lectura_invalida(registro: Dict[str, Any], texto: Any) -> Optional[str]:
    if not isinstance(texto, str) or not texto.strip():
        return None
    tarea = _reconstruir_tirada(registro)
    if not tarea:
        return None
    try:
        _, motivos = fase1_prompts.verificar_lectura(tarea, texto)
    except Exception:
        return None
    relevantes = [
        motivo
        for motivo in motivos
        if motivo.startswith(
            ("Menciona carta ajena", "No indica la orientación", "Menciona una orientación")
        )
    ]
    if relevantes:
        return "; ".join(relevantes)
    return None


def _palabras_clave(texto: str) -> set:
    plano = _sin_acentos(_nfc(texto).lower())
    plano = re.sub(r"[^a-z0-9\s]", " ", plano)
    return {palabra for palabra in plano.split() if palabra}


def similitud_jaccard(a: str, b: str) -> float:
    conjunto_a = _palabras_clave(a)
    conjunto_b = _palabras_clave(b)
    if not conjunto_a or not conjunto_b:
        return 0.0
    return len(conjunto_a & conjunto_b) / len(conjunto_a | conjunto_b)


def indice_duplicados(
    registros: Sequence[Dict[str, Any]],
    textos: Dict[str, str],
    corpus: Optional[Dict[str, Tuple[str, str, str]]] = None,
) -> Dict[str, Tuple[float, str]]:
    """Compara cada afirmación con las de su entidad y faceta.

    ``corpus`` permite comparar contra todo el corpus (id -> entidad, faceta,
    texto) y no solo contra las fichas muestreadas.
    """
    grupos: Dict[Tuple[str, str], List[Tuple[str, set]]] = defaultdict(list)
    if corpus is None:
        for registro in registros:
            if registro.get("nivel") != "afirmaciones":
                continue
            rid = registro.get("id")
            texto = textos.get(rid)
            if not rid or not texto:
                continue
            clave = (
                str(registro.get("entidad_id") or ""),
                str(registro.get("faceta") or ""),
            )
            grupos[clave].append((rid, _palabras_clave(texto)))
    else:
        for rid, (entidad_id, faceta, texto) in corpus.items():
            if not rid or not texto:
                continue
            grupos[(str(entidad_id or ""), str(faceta or ""))].append(
                (rid, _palabras_clave(texto))
            )

    duplicados: Dict[str, Tuple[float, str]] = {}
    for registro in registros:
        if registro.get("nivel") != "afirmaciones":
            continue
        rid = registro.get("id")
        if not rid:
            continue
        clave = (
            str(registro.get("entidad_id") or ""),
            str(registro.get("faceta") or ""),
        )
        palabras = _palabras_clave(textos.get(rid) or "")
        if not palabras:
            continue
        mejor = 0.0
        otro = ""
        for otro_id, otras_palabras in grupos.get(clave, []):
            if otro_id == rid or not otras_palabras:
                continue
            similitud = len(palabras & otras_palabras) / len(palabras | otras_palabras)
            if similitud > mejor:
                mejor = similitud
                otro = otro_id
        if mejor >= web_calidad.UMBRAL_JACCARD:
            duplicados[rid] = (mejor, otro)
    return duplicados


def analizar_registro(
    registro: Dict[str, Any],
    texto: Any,
    duplicados: Optional[Dict[str, Tuple[float, str]]] = None,
    elementos: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Aplica todas las banderas a una ficha y calcula su puntuación."""
    registro = registro or {}
    nivel = str(registro.get("nivel") or "")
    texto = texto if isinstance(texto, str) else ""
    banderas: List[Dict[str, Any]] = []

    def anadir(codigo: str, motivo: Optional[str]) -> None:
        if motivo:
            banderas.append({"codigo": codigo, "motivo": motivo, "peso": PESOS[codigo]})

    anadir("sin_texto", bandera_sin_texto(texto))
    anadir("texto_corto", bandera_texto_corto(texto, nivel))
    anadir("ruido_navegacion", bandera_ruido_navegacion(texto))
    anadir("ruido_comercial", bandera_ruido_comercial(texto))
    anadir("no_espanol", bandera_no_espanol(texto))
    anadir("mojibake", bandera_mojibake(texto))
    if nivel in ("afirmaciones", "consenso"):
        anadir("otra_carta", bandera_otra_entidad(registro, texto))
        anadir("promesa_vedada", bandera_promesa_vedada(texto))
    anadir("contradiccion_kb", bandera_contradiccion_kb(registro, texto, elementos))
    anadir("lectura_invalida", bandera_lectura_invalida(registro, texto))
    if duplicados:
        duplicado = duplicados.get(registro.get("id"))
        if duplicado:
            similitud, otro_id = duplicado
            anadir(
                "duplicada",
                f"casi idéntica (Jaccard {similitud:.2f}) a la ficha {otro_id}",
            )

    puntuacion = min(10, sum(bandera["peso"] for bandera in banderas))
    return {
        "id": registro.get("id"),
        "nivel": nivel,
        "banderas": banderas,
        "puntuacion": puntuacion,
    }


def analizar(
    registros: Sequence[Dict[str, Any]],
    textos: Dict[str, str],
    elementos: Optional[Dict[str, str]] = None,
    corpus: Optional[Dict[str, Tuple[str, str, str]]] = None,
) -> List[Dict[str, Any]]:
    duplicados = indice_duplicados(registros, textos, corpus)
    resultados = [
        analizar_registro(registro, textos.get(registro.get("id")), duplicados, elementos)
        for registro in registros
    ]
    resultados.sort(key=lambda resultado: (-resultado["puntuacion"], str(resultado["id"])))
    return resultados


def _inferir_base(ruta_muestras: str) -> str:
    ruta = Path(ruta_muestras).resolve()
    if ruta.parent.name == "muestras":
        return str(ruta.parent.parent)
    return muestras.BASE_POR_DEFECTO


def _porcentaje(marcadas: int, total: int) -> str:
    if not total:
        return "0,0 %"
    return f"{100.0 * marcadas / total:.1f} %".replace(".", ",")


def escribir_jsonl(resultados: Iterable[Dict[str, Any]], ruta: Path) -> None:
    with ruta.open("w", encoding="utf-8") as fh:
        for resultado in resultados:
            fh.write(json.dumps(resultado, ensure_ascii=False, sort_keys=True) + "\n")


def escribir_md(
    resultados: Sequence[Dict[str, Any]],
    registros: Sequence[Dict[str, Any]],
    textos: Dict[str, str],
    procedencias: Dict[str, str],
    ruta: Path,
    top: int = 40,
) -> None:
    por_id = {registro.get("id"): registro for registro in registros}
    total = len(registros)
    marcadas = sum(1 for resultado in resultados if resultado["banderas"])

    niveles = list(muestras.NIVELES)
    for registro in registros:
        nivel = str(registro.get("nivel") or "")
        if nivel and nivel not in niveles:
            niveles.append(nivel)

    lineas: List[str] = [
        "# Prerevisión de la muestra",
        "",
        "Generado por `finetune/corpus/prerevision.py`. La muestra original no se ha modificado.",
        "",
        f"- Fichas revisadas: **{total}**",
        f"- Fichas con al menos una bandera: **{marcadas}** ({_porcentaje(marcadas, total)})",
        f"- Fichas sin banderas: **{total - marcadas}**",
        "",
        "## Recuento por nivel",
        "",
        "| Nivel | Fichas | Marcadas | Tasa | Puntuación media | Puntuación máxima |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for nivel in niveles:
        del_nivel = [r for r in resultados if r["nivel"] == nivel]
        if not del_nivel:
            continue
        marcadas_nivel = sum(1 for r in del_nivel if r["banderas"])
        media = sum(r["puntuacion"] for r in del_nivel) / len(del_nivel)
        maxima = max(r["puntuacion"] for r in del_nivel)
        lineas.append(
            f"| {nivel} | {len(del_nivel)} | {marcadas_nivel} | "
            f"{_porcentaje(marcadas_nivel, len(del_nivel))} | {media:.2f} | {maxima} |"
        )

    lineas.extend(
        [
            "",
            "## Banderas por nivel",
            "",
            "| Bandera | " + " | ".join(niveles) + " | Total |",
            "|---|" + "---:|" * len(niveles) + "---:|",
        ]
    )
    conteo = Counter(
        (bandera["codigo"], resultado["nivel"])
        for resultado in resultados
        for bandera in resultado["banderas"]
    )
    for codigo in PESOS:
        celdas = [str(conteo.get((codigo, nivel), 0)) for nivel in niveles]
        lineas.append(f"| `{codigo}` | " + " | ".join(celdas) + f" | {sum(int(c) for c in celdas)} |")

    lineas.extend(
        [
            "",
            "## Tasa estimada por nivel y estrato",
            "",
            "El estrato procede de `muestras.jsonl`; los estratos con pocas fichas",
            "tienen intervalos muy amplios y solo orientan.",
            "",
            "| Nivel | Estrato | Fichas | Marcadas | Tasa |",
            "|---|---|---:|---:|---:|",
        ]
    )

    acumulado: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    for resultado in resultados:
        registro = por_id.get(resultado["id"], {})
        estrato = registro.get("estrato")
        if isinstance(estrato, (list, tuple)):
            etiqueta = "/".join(str(parte) for parte in estrato)
        else:
            etiqueta = str(estrato or "sin-estrato")
        clave = (resultado["nivel"], etiqueta)
        acumulado[clave][0] += 1
        if resultado["banderas"]:
            acumulado[clave][1] += 1
    for (nivel, estrato), (fichas, marcadas_estrato) in sorted(acumulado.items()):
        lineas.append(
            f"| {nivel} | {estrato} | {fichas} | {marcadas_estrato} | "
            f"{_porcentaje(marcadas_estrato, fichas)} |"
        )

    lineas.extend(
        [
            "",
            f"## {top} fichas más sospechosas",
            "",
            "Ordenadas por puntuación y, a igualdad, por identificador.",
            "",
        ]
    )

    for posicion, resultado in enumerate(resultados[:top], start=1):
        registro = por_id.get(resultado["id"], {})
        procedencia = procedencias.get(resultado["id"]) or "procedencia desconocida"
        texto = muestras.recortar(textos.get(resultado["id"]) or "", 240) or "(sin texto)"
        motivos = "; ".join(
            f"{bandera['codigo']}: {bandera['motivo']}" for bandera in resultado["banderas"]
        )
        lineas.extend(
            [
                f"{posicion}. **{resultado['id']}** · {resultado['nivel']} · "
                f"puntuación {resultado['puntuacion']}/10",
                f"   - Procedencia: {procedencia}",
                f"   - Entidad: `{registro.get('entidad_id', '')}` · "
                f"faceta `{registro.get('faceta', '')}` · origen `{registro.get('origen', '')}`",
                f"   - Motivos: {motivos or 'ninguno'}",
                f"   - Texto: «{texto}»",
                "",
            ]
        )

    lineas.extend(
        [
            "## Criterios y límites",
            "",
            "- Umbral de texto corto: 80 caracteres en web, libros y lecturas;",
            "  20 en afirmaciones y 40 en celdas de consenso. Las afirmaciones son",
            "  unidades atómicas de una frase (máximo 40 palabras) y las celdas de",
            "  consenso son listas de esas afirmaciones: aplicar 80 caracteres marcaría",
            "  más de la mitad de la muestra sin que eso indique un problema real;",
            "  el umbral bajo en consenso solo detecta celdas vacías o apenas esbozadas.",
            "- El idioma se estima con la proporción de palabras funcionales españolas",
            "  (conjunto ampliado sobre `es_score`), exigiendo al menos 15 palabras para",
            "  evitar falsos positivos en afirmaciones breves. Además se detectan marcas",
            "  portuguesas («ção», «não», «você»…) que el español no usa.",
            "- La contradicción con la KB solo se marca cuando el elemento se atribuye",
            "  explícitamente a la entidad o a su palo; las menciones a otros palos y",
            "  los usos metafóricos («proviene de la tierra») quedan fuera.",
            "- Las banderas de otra carta y de promesas vedadas solo se aplican a",
            "  afirmaciones y a celdas de consenso (listas de afirmaciones atómicas).",
            "  En prosa de web o libros es legítimo mencionar muchas",
            "  cartas y explicar que una promesa es falsa («no garantiza la lotería»);",
            "  marcarlas allí produciría mucho ruido.",
            "- En lecturas solo se reconstruyen tiradas en español de tarot o baraja",
            "  española con cartas declaradas. Los fragmentos sin la tirada completa",
            "  no se marcan por cartas ausentes, para no generar ruido.",
            "- Los duplicados se calculan contra todo el corpus de afirmaciones,",
            "  agrupando por entidad y faceta, con Jaccard de palabras y umbral 0,90.",
            "- La puntuación suma pesos y se limita a 10; es una prioridad de revisión,",
            "  no una probabilidad.",
            "",
        ]
    )

    ruta.write_text("\n".join(lineas), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    analizador = argparse.ArgumentParser(description="Prerevisión determinista de la muestra")
    analizador.add_argument(
        "--muestras",
        default=str(Path(muestras.BASE_POR_DEFECTO) / "muestras" / "muestras.jsonl"),
        help="Ruta del muestras.jsonl de entrada",
    )
    analizador.add_argument(
        "--out-dir",
        default=None,
        help="Directorio de salida (por defecto, el de la muestra)",
    )
    analizador.add_argument(
        "--base",
        default=None,
        help="Base del corpus (por defecto se infiere de --muestras)",
    )
    analizador.add_argument("--top", type=int, default=40, help="Fichas en el informe Markdown")
    argumentos = analizador.parse_args(argv)

    ruta_muestras = Path(argumentos.muestras)
    registros = muestras._leer_jsonl(str(ruta_muestras))
    base = argumentos.base or _inferir_base(str(ruta_muestras))
    salida = Path(argumentos.out_dir) if argumentos.out_dir else ruta_muestras.parent
    salida.mkdir(parents=True, exist_ok=True)

    resolvedor = muestras.Resolvedor(base)
    crudos: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for nivel in muestras.NIVELES:
        try:
            for registro in muestras.cargar_registros(base, nivel):
                crudos[(nivel, registro.get("id"))] = registro
        except (OSError, ValueError):
            continue

    corpus: Dict[str, Tuple[str, str, str]] = {}
    for (nivel, rid), crudo in crudos.items():
        if nivel != "afirmaciones" or not rid:
            continue
        try:
            texto_crudo = resolvedor.texto(nivel, crudo) or ""
        except Exception:
            texto_crudo = ""
        if texto_crudo:
            corpus[rid] = (
                str(crudo.get("entidad_id") or ""),
                str(crudo.get("faceta") or ""),
                texto_crudo,
            )

    textos: Dict[str, str] = {}
    procedencias: Dict[str, str] = {}
    for registro in registros:
        rid = registro.get("id")
        nivel = registro.get("nivel")
        crudo = crudos.get((nivel, rid))
        if crudo is None:
            textos[rid] = ""
            procedencias[rid] = "registro no encontrado en las fuentes"
            continue
        try:
            textos[rid] = resolvedor.texto(nivel, crudo) or ""
        except Exception:
            textos[rid] = ""
        try:
            procedencias[rid] = muestras.procedencia_de(nivel, crudo, resolvedor) or ""
        except Exception:
            procedencias[rid] = ""

    resultados = analizar(registros, textos, cargar_elementos(), corpus)
    escribir_jsonl(resultados, salida / "prerevision.jsonl")
    escribir_md(resultados, registros, textos, procedencias, salida / "prerevision.md", argumentos.top)

    marcadas = sum(1 for resultado in resultados if resultado["banderas"])
    print(
        f"{len(resultados)} fichas revisadas, {marcadas} con banderas. "
        f"Salida en {salida / 'prerevision.jsonl'} y {salida / 'prerevision.md'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
