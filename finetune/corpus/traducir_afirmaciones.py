#!/usr/bin/env python3
"""T116: Traducir al español las afirmaciones en inglés de los libros.

Lee un JSONL de afirmaciones (esquema de fase0: entidad_id, faceta, fuente_id,
dominio, afirmacion, cita_original...) y escribe un JSONL con la `afirmacion`
traducida, conservando el resto de campos e id de entidad. Añade `fid` (hash
estable de la fila) a toda fila de salida para poder reanudar (--resume), y
`idioma_origen` y `traductor` en las filas traducidas.

Cada traducción pasa un verificador determinista (nombres de carta del glosario,
cifras y orientaciones, sin restos de inglés, longitud 0.6-1.6x, español
estándar sin gallego ni portugués). Si falla se reintenta con el motivo; tras
--max-intentos la fila va a <salida>.rechazadas.jsonl con el ultimo motivo.

Los textos ya en español pasan sin tocarlos. Los backends:
  - local:   endpoint OpenAI-compatible (por defecto nodo2 10.0.0.4; nodo1 esta
             reservado para entrenamiento, no usarlo aqui).
  - mercury: API de Inception Labs; la clave SOLO por variable de entorno
             INCEPTION_API_KEY (nunca por argumentos ni ficheros; nunca se
             imprime su valor).

Uso:
  python corpus/traducir_afirmaciones.py --entrada afms_en.jsonl \
      --salida afms_es.jsonl --backend local [--limite 20] [--dry-run] [--resume]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from cartas import CARTAS_TAROT, norm
from llm_client import LLMClient
from translate_dataset import EN_WORDS, detect_language

GLOSARIO_POR_DEFECTO = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "glosario_tarot_en_es.json"
)

# Endpoints por defecto: NODO2. El nodo1 esta reservado para entrenamiento.
ENDPOINT_LOCAL_POR_DEFECTO = "http://10.0.0.4:8000/v1"
MODEL_LOCAL_POR_DEFECTO = "halogen-qwen3.8-flash-next"
MERCURY_URL = "https://api.inceptionlabs.ai/v1"
MERCURY_MODEL = "mercury-3"
MERCURY_API_KEY_ENV = "INCEPTION_API_KEY"
MERCURY_TIMEOUT = 180.0
MERCURY_TASA_POR_MIN = 60
MERCURY_MAX_COMPLETION_TOKENS = 2048

BASE_PROMPT = (
    "Eres un traductor profesional de textos de tarot, astrologia y "
    "numerologia. Traduce del ingles al espanol neutro estandar."
)

REGLAS_PROMPT = [
    "Reglas obligatorias:",
    "- Devuelve SOLO la traducción, sin comillas, notas ni explicaciones.",
    "- Español neutro estándar: nada de gallego ni portugués.",
    "- Usa el glosario de forma literal y consistente en toda la colección.",
    "- Conserva todas las cifras y la orientación de las cartas "
    "(invertida / derecha).",
    "- No dejes ninguna palabra en inglés sin traducir.",
]

# Alias ambiguos de mayores que solo exigen traducción si van en mayúsculas
# (en minúsculas pueden ser palabras comunes: "the star shone", "her strength").
_AMBIGUOS_SIN_REQUERIR = {
    "hanged man", "the hanged man", "wheel of fortune", "the wheel of fortune",
}

# Palabras en inglés que jamás aparecen en una traducción española correcta y
# que EN_WORDS de translate_dataset no cubre (nombres de rango, palo, etc.).
RESIDUAL_TERMS = {
    "reversed", "inverted", "upside", "down", "upright", "spread", "layout",
    "querent", "querents", "significator", "signifying", "reading", "readings",
    "deck", "decks", "card", "cards", "court", "suit", "suits", "arcana",
    "pip", "wands", "pentacles", "cups", "swords", "coins", "disks", "discs",
    "knave", "page", "pages", "knight", "knights", "queen", "queens",
    "king", "kings", "draw", "draws",
}
# "as" esta en EN_WORDS pero es español legitimo ("As de Copas").
_STOP_EXCEPTO = {"as"}

# Marcadores de gallego/portugues (minusculas con acentos, con limites de
# palabra). Se excluyen cadenas que existen en español: no, a, o, la, de, su,
# da, e (conjuncion "padres e hijos"), mas, nos, esta, era, tambien...
GLPT_MARKERS = {
    "não", "nao", "são", "sao", "você", "voce", "então", "entao", "muito",
    "obrigado", "obrigada", "tambem", "non", "unha", "unhas", "tamén", "moi",
    "súa", "súas", "edes", "uma", "um", "os", "do", "é", "mesmo", "mesma",
    "primeiro", "primeira", "próprio", "proprio", "obrigado", "gosto",
}

_NUM_ES: Dict[str, Tuple[str, ...]] = {
    "one": ("uno", "un", "una", "1"),
    "two": ("dos", "2"), "three": ("tres", "3"), "four": ("cuatro", "4"),
    "five": ("cinco", "5"), "six": ("seis", "6"), "seven": ("siete", "7"),
    "eight": ("ocho", "8"), "nine": ("nueve", "9"), "ten": ("diez", "10"),
    "eleven": ("once", "11"), "twelve": ("doce", "12"),
    "thirteen": ("trece", "13"), "fourteen": ("catorce", "14"),
    "fifteen": ("quince", "15"), "sixteen": ("dieciséis", "dieciseis", "16"),
    "seventeen": ("diecisiete", "17"), "eighteen": ("dieciocho", "18"),
    "nineteen": ("diecinueve", "19"), "twenty": ("veinte", "20"),
    "thirty": ("treinta", "30"), "forty": ("cuarenta", "40"),
    "fifty": ("cincuenta", "50"),
    "hundred": ("cien", "ciento", "cientos", "100"),
    "thousand": ("mil", "miles", "1000"),
}

_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+")
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_PREFIX_TRAD_RE = re.compile(
    r"^(?:Aqu[ií]\s+est[áa]\s+la\s+traducci[óo]n|Traducci[óo]n"
    r"|Traducción)\s*[:：]\s*", re.IGNORECASE,
)
_INVERT_RE = re.compile(r"\b(?:reversed|inverted|upside[-\s]down)\b", re.I)
_UPRIGHT_RE = re.compile(r"\bupright\b", re.I)
_BASIC_EN_RE = re.compile(r"\b(?:the|and|of|is|are|to|with|that|for)\b", re.I)


def cargar_glosario(ruta: Optional[str] = None) -> Dict[str, Any]:
    with open(ruta or GLOSARIO_POR_DEFECTO, encoding="utf-8") as f:
        g = json.load(f)
    for clave in ("mayores", "palos", "rangos", "terminos", "astrologia",
                  "numerologia"):
        if clave not in g:
            raise ValueError(f"glosario sin sección {clave!r}: {ruta}")
    return g


class IndiceCartas:
    """Índice alias inglés -> nombre español y formas españolas aceptadas."""

    def __init__(self, glosario: Dict[str, Any]):
        self.alias_es: Dict[str, str] = {}
        for alias, es in glosario["mayores"].items():
            self.alias_es[alias.lower()] = es
        for r_en, r_es in glosario["rangos"].items():
            for p_en, p_es in glosario["palos"].items():
                self.alias_es[f"{r_en} of {p_en}"] = f"{r_es} de {p_es}"
        # Variantes con digito: "2 of Cups" -> "Dos de Copas" (los numerales
        # de los nombres de carta no cuentan como cifras a conservar).
        _RANGO_NUM = {"1": "ace", "2": "two", "3": "three", "4": "four",
                      "5": "five", "6": "six", "7": "seven", "8": "eight",
                      "9": "nine", "10": "ten"}
        for dig, r_en in _RANGO_NUM.items():
            if r_en not in glosario["rangos"]:
                continue
            for p_en, p_es in glosario["palos"].items():
                self.alias_es.setdefault(
                    f"{dig} of {p_en}",
                    f"{glosario['rangos'][r_en]} de {p_es}",
                )
        patrones = sorted(self.alias_es, key=len, reverse=True)
        self._re = re.compile(
            r"\b(" + "|".join(re.escape(p) for p in patrones) + r")\b", re.I
        )
        # Formas españolas aceptadas por nombre canonico, desde cartas.py.
        self.es_aceptadas: Dict[str, set] = {}
        for e in CARTAS_TAROT:
            forms = {norm(e["nombre"])}
            for s in e.get("sinonimos") or []:
                if re.search(r"\bof\b", s.lower()):
                    continue  # sinonimo en ingles, no sirve como forma ES
                forms.add(norm(s))
            self.es_aceptadas[e["nombre"]] = forms

    def contiene_alias(self, texto: str) -> bool:
        return bool(self._re.search(texto or ""))

    def requeridos(self, original: str) -> List[str]:
        """Nombres canonicos espanoles que DEBEN aparecer en la traduccion."""
        out: List[str] = []
        for m in self._re.finditer(original or ""):
            alias = m.group(1).lower()
            es = self.alias_es[alias]
            es_menor = " of " in alias
            if (not es_menor and alias not in _AMBIGUOS_SIN_REQUERIR
                    and not original[m.start(1)].isupper()):
                continue  # palabra comun en minusculas, no es el nombre de la carta
            if es not in out:
                out.append(es)
        return out

    def alias_residuales(self, texto: str) -> Optional[str]:
        m = self._re.search(texto or "")
        return m.group(1) if m else None


def construir_sistema(glosario: Dict[str, Any]) -> str:
    def par(secc: Dict[str, str]) -> str:
        return "; ".join(f"{k} → {v}" for k, v in sorted(secc.items()))

    ast = glosario["astrologia"]
    regla = glosario.get("regla_menores",
                         "'Rango of Palo' -> 'Rango ES de Palo ES'")
    bloques = [
        BASE_PROMPT,
        "",
        "GLOSARIO OBLIGATORIO (inglés → español):",
        f"- Arcanos mayores: {par(glosario['mayores'])}.",
        f"- Palos: {par(glosario['palos'])}.",
        f"- Rangos: {par(glosario['rangos'])}.",
        f"- Arcanos menores: «{regla}».",
        f"- Términos: {par(glosario['terminos'])}.",
        f"- Signos astrológicos: {par(ast['signos'])}.",
        f"- Planetas: {par(ast['planetas'])}.",
        f"- Aspectos: {par(ast['aspectos'])}.",
        f"- Términos de astrología: {par(ast['terminos'])}.",
        f"- Numerología: {par(glosario['numerologia'])}.",
        "",
        *REGLAS_PROMPT,
    ]
    return "\n".join(bloques)


def limpiar_salida(bruto: str) -> str:
    texto = (bruto or "").strip()
    texto = _THINK_RE.sub("", texto).strip()
    texto = _PREFIX_TRAD_RE.sub("", texto, count=1).strip()
    if len(texto) >= 2 and texto[0] == '"' and texto[-1] == '"':
        texto = texto[1:-1].strip()
    return texto


def verificar_traduccion(original: str, traducida_bruta: str,
                         indice: IndiceCartas
                         ) -> Tuple[Optional[str], Optional[str]]:
    """Devuelve (texto_limpio, None) o (None, motivo_de_fallo)."""
    texto = limpiar_salida(traducida_bruta)
    if not texto:
        return None, "respuesta vacía"

    # (d) longitud
    ratio = len(texto) / max(1, len(original.strip()))
    if ratio < 0.6 or ratio > 1.6:
        return None, f"ratio de longitud fuera de rango (0.6-1.6): {ratio:.2f}"

    # (c) restos de inglés
    lang = detect_language(texto)
    if lang == "en":
        return None, "la traducción sigue en inglés"
    tokens = [t.lower() for t in _TOKEN_RE.findall(texto)]
    tokens_set = set(tokens)
    en_hits = sorted({t for t in tokens_set if t in EN_WORDS} - _STOP_EXCEPTO)
    if en_hits:
        return None, f"palabras en inglés: {en_hits[:5]}"
    resid = sorted(tokens_set & RESIDUAL_TERMS)
    if resid:
        return None, f"términos en inglés sin traducir: {resid[:5]}"
    alias = indice.alias_residuales(texto)
    if alias:
        return None, f"nombre de carta en inglés residual: «{alias}»"

    # (a) nombres de carta en español según glosario
    n_texto = norm(texto)
    for es in indice.requeridos(original):
        forms = indice.es_aceptadas.get(es)
        if not forms:
            return None, f"error de glosario: «{es}» no está en cartas.py"
        if not any(f in n_texto for f in forms):
            return None, f"falta el nombre en español «{es}»"

    # (b) cifras y orientaciones (sin contar los numeros de los nombres de carta)
    sin_alias = indice._re.sub(" ", original or "")
    digitos_o = re.findall(r"\d+", sin_alias)
    digitos_t = set(re.findall(r"\d+", texto))
    for d in digitos_o:
        if d not in digitos_t:
            return None, f"falta la cifra {d}"
    for w in _TOKEN_RE.findall(sin_alias):
        w = w.lower()
        formas = _NUM_ES.get(w)
        if formas and not (tokens_set & set(formas)):
            return None, f"falta el número «{w}» en español"
    if _INVERT_RE.search(original or "") and "invert" not in texto.lower():
        return None, "no se conservó la inversión (invertida)"
    if _UPRIGHT_RE.search(original or "") and "derech" not in texto.lower():
        return None, "no se conservó la posición al derecho (derecha)"

    # (e) gallego/portugués
    glpt = sorted(tokens_set & GLPT_MARKERS)
    if glpt:
        return None, f"marcadores de gallego/portugués: {glpt[:5]}"

    return texto, None


def debe_traducirse(texto: str, indice: IndiceCartas) -> Tuple[bool, str]:
    lang = detect_language(texto or "")
    if lang == "en":
        return True, "en"
    if lang == "mixed":
        # "mixed" sin marcas claras de ingles (p. ej. texto corto con
        # pocas palabras) no se traduce: no hay restos evidentes.
        if indice.contiene_alias(texto) or _BASIC_EN_RE.search(texto or ""):
            return True, "mixed"
        return False, "unknown"
    if lang == "unknown":
        if indice.contiene_alias(texto) or _BASIC_EN_RE.search(texto or ""):
            return True, "en"
        return False, "unknown"
    return False, lang


def fid_de(fila: Dict[str, Any]) -> str:
    blob = json.dumps(fila, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def leer_jsonl(ruta: str) -> List[Dict[str, Any]]:
    filas: List[Dict[str, Any]] = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                filas.append(json.loads(linea))
            except json.JSONDecodeError as e:
                raise SystemExit(f"JSON inválido en {ruta}:{n}: {e}")
    return filas


def parse_endpoint(spec: str) -> Any:
    if "=" in spec:
        url, model = spec.split("=", 1)
        return (url, model)
    return spec


def crear_cliente(args: argparse.Namespace,
                  simulado: Optional[Any] = None) -> LLMClient:
    if args.backend == "mercury":
        if simulado is None and not os.environ.get(MERCURY_API_KEY_ENV):
            raise SystemExit(
                "Falta la variable de entorno INCEPTION_API_KEY: la clave de "
                "Inception Labs solo se lee de esa variable (nunca por "
                "argumentos ni ficheros)."
            )
        spec: Dict[str, Any] = {
            "url": MERCURY_URL,
            "model": args.model or MERCURY_MODEL,
            "api_key_env": MERCURY_API_KEY_ENV,
        }
        return LLMClient(
            endpoints=[spec], model=args.model or MERCURY_MODEL,
            timeout=MERCURY_TIMEOUT, simulado=simulado,
            max_concurrencia=args.workers,
            tasa_max_por_minuto=MERCURY_TASA_POR_MIN,
            reasoning_effort="instant",
            max_completion_tokens=MERCURY_MAX_COMPLETION_TOKENS,
        )
    endpoints = [parse_endpoint(e) for e in args.endpoint] or [
        ENDPOINT_LOCAL_POR_DEFECTO
    ]
    model = args.model or MODEL_LOCAL_POR_DEFECTO
    return LLMClient(
        endpoints=endpoints, model=model, timeout=args.timeout,
        simulado=simulado, max_concurrencia=args.workers,
    )


def traducir_una(cliente: LLMClient, sistema: str, original: str,
                 indice: IndiceCartas, max_intentos: int, temperatura: float,
                 ) -> Tuple[Optional[str], Optional[str], int]:
    """Devuelve (traduccion|None, motivo|None, intentos_usados)."""
    motivo = None
    for n in range(1, max(1, max_intentos) + 1):
        usuario = (
            f"Texto original en inglés:\n{original}\n\n"
            "Devuelve SOLO la traducción al español."
        )
        if motivo:
            usuario += (
                f"\n\nEl intento anterior fue rechazado: {motivo}. "
                "Corrige ese problema en esta versión."
            )
        try:
            bruto = cliente.chat(sistema, usuario, temperature=temperatura)
        except Exception as e:  # red, backend caido, respuesta vacia...
            motivo = f"error de backend: {type(e).__name__}: {str(e)[:120]}"
            continue
        limpia, motivo = verificar_traduccion(original, bruto, indice)
        if motivo is None:
            return limpia, None, n
    return None, motivo, max(1, max_intentos)


def fids_completados(ruta_salida: str) -> set:
    if not os.path.exists(ruta_salida):
        return set()
    done = set()
    with open(ruta_salida, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if fila.get("fid"):
                done.add(fila["fid"])
    return done


def procesar_lote(filas: List[Dict[str, Any]], cliente: LLMClient,
                  sistema: str, indice: IndiceCartas, args, tag: str,
                  done: set, log=print):
    """Procesa en orden con pool de workers. Genera dicts de resultado."""
    def uno(item):
        n, fila = item
        fid = fila.get("fid") or fid_de(fila)
        texto = fila.get("afirmacion") or ""
        toca, lang = debe_traducirse(texto, indice)
        if not toca:
            return {"fid": fid, "estado": "passthrough",
                    "fila": {**fila, "fid": fid}}
        trad, motivo, intentos = traducir_una(
            cliente, sistema, texto, indice, args.max_intentos, args.temperatura
        )
        if trad is not None:
            nueva = {**fila, "fid": fid, "afirmacion": trad,
                     "idioma_origen": lang, "traductor": tag}
            return {"fid": fid, "estado": "traducida", "fila": nueva,
                    "intentos": intentos}
        return {"fid": fid, "estado": "rechazada",
                "rechazo": {**fila, "fid": fid, "motivo": motivo,
                            "intentos": intentos}}

    con_skips = []
    for n, fila in enumerate(filas):
        fid = fila.get("fid") or fid_de(fila)
        if fid in done:
            con_skips.append((n, None))
        else:
            con_skips.append((n, fila))
    pendientes = [(n, f) for n, f in con_skips if f is not None]
    resultados = {}
    inicio = time.time()
    hechos = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for (n, _), res in zip(pendientes, pool.map(uno, pendientes)):
            resultados[n] = res
            hechos += 1
            if log and hechos % 20 == 0:
                rate = hechos / max(1e-9, time.time() - inicio)
                log(f"  ... {hechos}/{len(pendientes)} ({rate:.1f}/s)")
    for n in range(len(filas)):
        if n in resultados:
            yield resultados[n]
        else:
            yield {"fid": filas[n].get("fid") or fid_de(filas[n]),
                   "estado": "omitida"}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Traduce afirmaciones de tarot/astrologia/numerologia "
                    "del ingles al espanol (T116).")
    ap.add_argument("--entrada", required=True, help="JSONL de afirmaciones")
    ap.add_argument("--salida", help="JSONL de salida (obligatorio salvo --dry-run)")
    ap.add_argument("--rechazadas", help="JSONL de rechazos "
                      "(por defecto <salida>.rechazadas.jsonl)")
    ap.add_argument("--backend", choices=["local", "mercury"], default="local")
    ap.add_argument("--endpoint", action="append", default=[],
                    help='endpoint local "url" o "url=modelo" (repetible). '
                         f"Por defecto {ENDPOINT_LOCAL_POR_DEFECTO} (nodo2).")
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--glosario", default=None)
    ap.add_argument("--max-intentos", type=int, default=3)
    ap.add_argument("--temperatura", type=float, default=0.2)
    ap.add_argument("--limite", type=int, default=0,
                    help="procesar solo las N primeras filas")
    ap.add_argument("--resume", action="store_true",
                    help="omitir filas ya presentes en la salida (por fid)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo clasificar y recuentos; sin red ni escritura")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.salida:
        ap.error("--salida es obligatorio salvo con --dry-run")

    glosario = cargar_glosario(args.glosario)
    indice = IndiceCartas(glosario)
    sistema = construir_sistema(glosario)

    filas = leer_jsonl(args.entrada)
    if args.limite:
        filas = filas[:args.limite]

    cuenta = {"en": 0, "mixed": 0, "es": 0, "unknown": 0}
    for fila in filas:
        toca, lang = debe_traducirse(fila.get("afirmacion") or "", indice)
        cuenta[lang if lang in cuenta else "unknown"] += 1
    print(f"filas: {len(filas)} | en/mixed a traducir: "
          f"{cuenta['en'] + cuenta['mixed']} | es: {cuenta['es']} | "
          f"unknown: {cuenta['unknown']}")

    if args.dry_run:
        return 0

    done = fids_completados(args.salida) if args.resume else set()
    if done:
        print(f"resume: {len(done)} filas ya completadas se omiten")

    cliente = crear_cliente(args)
    tag = f"{args.backend}:{cliente.model}"
    ruta_rech = args.rechazadas or f"{args.salida}.rechazadas.jsonl"

    modo = "a" if done else "w"
    stats = {"traducida": 0, "passthrough": 0, "rechazada": 0, "omitida": 0}
    con_sal = open(args.salida, modo, encoding="utf-8")
    con_rech = open(ruta_rech, "w", encoding="utf-8")
    try:
        for res in procesar_lote(filas, cliente, sistema, indice, args, tag,
                                 done):
            stats[res["estado"]] += 1
            if res.get("fila"):
                con_sal.write(json.dumps(res["fila"], ensure_ascii=False)
                              + "\n")
            elif res.get("rechazo"):
                con_rech.write(json.dumps(res["rechazo"], ensure_ascii=False)
                               + "\n")
    finally:
        con_sal.close()
        con_rech.close()

    print(f"completo: traducidas={stats['traducida']} "
          f"passthrough={stats['passthrough']} rechazos={stats['rechazada']} "
          f"omitidas={stats['omitida']}")
    print(f"salida: {args.salida} | rechazadas: {ruta_rech}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
