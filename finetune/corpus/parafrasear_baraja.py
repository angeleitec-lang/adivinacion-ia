#!/usr/bin/env python3
"""T131: Parafrasear las afirmaciones de baraja española (Salas + Tiradas).

Lee el JSONL de afirmaciones de los libros comprados de baraja española
(`/Users/angelgonzalez/fase0/libros_comprados_baraja/afirmaciones/afirmaciones_baraja.jsonl`),
donde `afirmacion` es la cita recortada («…Es la carta más favorable de la.»), y
reescribe cada fila como una afirmación breve, completa y propia en español
estándar (1-2 oraciones, sin cita literal), conservando la orientación y el
resto del esquema más `procedencia` y `fid` (hash estable para reanudar).

Verificación determinista por fila:
  (a) 1-2 oraciones y termina en punto.
  (b) ninguna secuencia de más de 8 palabras consecutivas igual a la cita
       (`cita_original`); límite duro del proyecto: 25.
  (c) sin marcadores de otra lengua ni «asistente de IA».
  (d) conserva la orientación (derecho / revés).
Las filas que fallen se reintentan (hasta --max-intentos intentos, por defecto
1 inicial + 2 reintentos) y al final van a <salida>.rechazadas.jsonl con el
último motivo. Las filas aceptadas se anotan en <salida>.procesados.jsonl para
reanudar con --resume (solo se omiten las ya aceptadas; los rechazos pueden
reintentarse).

Backend: Mercury (mercury-3) con la clave SOLO por variable de entorno
INCEPTION_API_KEY (nunca por argumentos ni ficheros; nunca se imprime). Si
falta la variable o la API devuelve errores fatales (401/429/timeout) seguidos,
el script se detiene y avisa.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import requests

from cartas import NAIPES_ESPANOLES, norm
from llm_client import LLMClient, RateLimitError
from translate_dataset import EN_WORDS, detect_language

PROCEDENCIA = "comprado por el usuario, uso interno, libro con copyright"

MERCURY_URL = "https://api.inceptionlabs.ai/v1"
MERCURY_MODEL = "mercury-3"
MERCURY_API_KEY_ENV = "INCEPTION_API_KEY"
MERCURY_TIMEOUT = 180.0
MERCURY_TASA_POR_MIN = 60
MERCURY_MAX_COMPLETION_TOKENS = 2048

ENDPOINT_LOCAL_POR_DEFECTO = "http://10.0.0.4:8000/v1"
MODEL_LOCAL_POR_DEFECTO = "halogen-qwen3.8-flash-next"

MAX_WORKERS = 2
MAX_CONSECUTIVAS_COPIA = 8   # puerta anti-copia de esta pista
LIMITE_DURO_PROYECTO = 25

NOMBRE_CARTA = {e["id"]: e["nombre"] for e in NAIPES_ESPANOLES}

BASE_PROMPT = (
    "Eres un redactor experto en baraja española (oros, copas, espadas y "
    "bastos). Reescribes afirmaciones breves de significado de cartas."
)

REGLAS_PROMPT = [
    "Reglas obligatorias:",
    "- Devuelve SOLO la paráfrasis, sin comillas, notas, prefijos ni "
    "explicaciones.",
    "- Escríbela como una afirmación breve, completa y propia en español "
    "neutro estándar, de 1 o 2 oraciones, terminando en punto.",
    "- No copies literalmente la cita y no nombres el libro ni al autor.",
    "- No inventes significados: reformula únicamente lo que dice la cita, "
    "incluida la orientación (al derecho / al revés).",
    "- Conserva la orientación de la carta tal como aparece en la cita.",
    "- Baraja española: nada de naipes franceses ni de tarot.",
    "- Español estándar: nada de gallego, portugués ni inglés.",
]

# Marcadores de gallego/portugués (se excluyen cadenas que existen en español).
GLPT_MARKERS = {
    "não", "nao", "são", "sao", "você", "voce", "então", "entao", "muito",
    "obrigado", "obrigada", "tambem", "non", "unha", "unhas", "tamén", "moi",
    "súa", "súas", "edes", "uma", "um", "é", "mesmo", "mesma", "primeiro",
    "primeira", "próprio", "proprio", "gosto",
}

_STOP_EXCEPTO = {"as"}

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_PREFIX_PARAF_RE = re.compile(
    r"^(?:Par[áa]frasis|Par[áa]frasear|Afirmaci[óo]n|"
    r"Aqu[ií]\s+est[áa]\s+la\s+afirmaci[óo]n)\s*[:：]\s*", re.I)
_ORAC_RE = re.compile(r"[.!?]+(?:\s+|$)")
_ORIENT_REVES_RE = re.compile(
    r"\b(?:al\s+rev[eé]s|rev[eé]s|invertid[ao]s?)\b", re.I)
_ORIENT_DERECHO_RE = re.compile(
    r"\b(?:al\s+derecho|derech[ao]s?)\b", re.I)
_ASISTENTE_IA_RE = re.compile(
    r"\basistente\s+de\s+ia\b|asistente|inteligencia\s+artificial", re.I)
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Umbral nominal de cita para considerar que tiene contenido propio de la carta.
CITA_MIN_CARACTERES = 40

# Vocabulario de "reversa vacía": términos que, solos, solo describen que la
# carta está invertida sin aportar significado propio (detectado en las 80
# paráfrasis inventadas de T134). Se comparan normalizados (sin tildes).
_FÓRMULA_GENÉRICA = set("""
inversion inversiones alteracion alteraciones significado significados habitual habituales
energia energias bloqueada bloqueadas bloqueado bloqueados bloqueo bloqueos
equilibrio material materiales valor valores perdida perdidas ausencia carencia
intercambios recursos movimiento figura cualidades cualidad positiva positivas
actitud actitudes armonia vinculos vinculo afectivo afectivos afectos afectividad
emocional emocionales asuntos ambito plano tirada claves propias orientacion orientaciones
carta cartas sentido contraria contrario desequilibrada desequilibrado inmadura
inmaduro canalizada canalizado caprichosa caprichoso sinceridad sentimientos sentimiento
naturalidad claridad dificultad dificultades interrupcion interrupciones
desarrollarse manifiesta fluye fluyen presentarse presenta logra logran
asociada asociado asociadas relacionados relacionadas representados representadas
indicada indicado indicadas representada representado representa representan señalar senalar
señala senala indica indican apunta apuntan asocia asocian invierte invierten
voltea voltean altera alteran bloquea bloquean obstaculiza obstaculizan
""".split())

# Conectores y verbos vacíos para quedarse con el contenido real.
_CONECTORES_VACIOS = set("""
la el los las de del en que o y con una un su sus por para a al esta este esto estos estas
esas aquel aquellos se le les lo tambien asi como sobre no ya mas muy sin cuando donde cual
cuales quien quienes entre ante tras hacia hasta desde durante mediante segun porque pues si
pero aunque sino ni es son era eran fue fueron ser estar esta estan estaba estaban hay habia
tiene tienen tenia tenian del ha he han hemos habia estoy estamos se asocia asociada asociado
señala senala indica representa apunta advierte expresa evoca anuncia viene significa quiere
habla muestra revela describe define nombra menciona aparece torna vuelve presenta refiere
remite alude trata resalta destaca sugiere propone ofrece entrega da hace realiza simboliza
encarna ejemplifica manifiesta expone narra cuenta explica aclara precisa detalla concreta
enumera lista recoge resume sintetiza agrupa clasifica ordena orienta guia aconseja recomienda
invita alienta motiva anima impulsa promueve fomenta estimula potencia intensifica fortalece
debilita limita restringe obstaculiza bloquea frena paraliza estanca retrasa demora aplaza
pospone suspende cancela elimina anula neutraliza contrarresta compensa equilibra corrige
ajusta adapta transforma modifica altera cambia invierte revierte gira rota voltea tambalea
sacude conmueve perturba afecta impacta incide influye interviene actua opera funciona
desarrolla evoluciona progresa mejora empeora decae cae sube baja asciende desciende aumenta
disminuye reduce incrementa multiplica divide suma resta agrega quita sustrae anade añade
incluye excluye admite rechaza acepta niega afirma sostiene mantiene conserva protege defiende
ataca combate pelea enfrenta desafia reta supera vence triunfa gana pierde logra consigue
alcanza obtiene adquiere hereda recibe da dedica ofrece regala dona presta cobra paga invierte
gasta ahorra acumula atesora despilfarra dilapida malgasta derrocha arriesga apuesta juega
especula negocia vende compra importa exporta transporta mueve traslada desplaza viaja llega
parte sale avanza retrocede acelera apresura adelanta anticipa preve pronostica predice augura
vaticina presagia devela revela expone enseña aprende estudia trabaja aplica ejercita practica
entrena prepara planifica proyecta diseña construye edifica crea inventa innova imagina sueña
idealiza fantasea ilusiona espera desea anhela quiere ansia ambiciona codicia envidia cela teme
duda vacila titubea hesita sospecha desconfia confia cree sabe ignora olvida recuerda evoca
rememora añora extraña siente emociona conmueve toca remueve agita instiga provoca causa origina
genera desata dispara lanza impulsa empuja atrae convoca invita repele ahuyenta aleja acerca
junta une separa divide relaciona vincula conecta liga asocia combina mezcla fusiona integra
incorpora agrega añade sustituye reemplaza cambia permuta canjea intercambia trueca comparte
parte reparte distribuye asigna adjudica atribuye corresponde pertenece afecta incumbe importa
interesa preocupa inquieta perturba agita alarma asusta espanta asombra sorprende maravilla
deslumbra fascina encanta seduce cautiva atrae embelesa hipnotiza hechiza conjura invoca evoca
llama nombra menciona cita refiere alude remite apunta senala indica muestra habla menciona
cuenta narra relata describe retrata pinta dibuja esboza perfila delinea traza graba imprime
marca deja estampa sella firma rubrica autentica verifica confirma valida avala ratifica
corrobora sustenta respalda apoya ayuda asiste socorre auxilia beneficia favorece perjudica
lastima hiere ofende agravia humilla denigra menosprecia desprecia subestima infravalora
sobrevalora exagera minimiza resta quita limita condiciona supedita subordina depende requiere
exige demanda pide solicita ruega implora suplica ordena manda dirije gobierna administra
gestiona maneja opera controla domina somete subyuga oprime reprime contiene frena modera
atenua mitiga suaviza atempera calma serena tranquiliza sosiega relaja distiende alivia
consuela reconforta abriga protege ampara resguarda custodia vigila cuida atiende observa mira
examina analiza estudia investiga indaga explora sondea averigua descubre halla encuentra
localiza ubica situa coloca pone instala monta arma ensambla construye fabrica produce elabora
manufactura transforma convierte procesa trata refina purifica depura limpia asea higieniza
sanea desinfecta esteriliza seca humedece moja empapa remoja enjuaga lava frota talla pulimenta
abrillanta lustra bruñe esmaltan barniza pinta colorea tiñe matiza entona afina ajusta calibra
nivela iguala empareja completa complementa añade suplementa acrecienta aumenta refuerza concentra
condensa espesa aglutina agrupa congrega reunne junta acumula almacena guarda conserva retiene
mantiene sostiene aguanta soporta resiste permite tolera admite traga acepta consiente aprueba
autoriza concede otorga da cede entrega confiere asigna delega encomienda encarga comisiona
deposita confia encomienda lega hereda transmite comunica informa notifica avisa anuncia publica
difunde propaga divulga extiende disemina esparce reparte distribuye comparte da dona regala
ofrece brinda facilita permite posibilita hace coadyuva contribuye colabora coopera ayuda asiste
apoya respalda secunda acompaña sigue persigue busca indaga rastrea persigue acecha vigila
espía observa atiende cuida protege defiende resguarda salvaguarda preserva conserva mantiene
sostiene apuntala apuntala apuntala apuntala apuntala apuntala apuntala apuntala
""".split())


class BackendFatal(Exception):
    """Error fatal de backend (auth, límite de tasa o timeout) → detener."""


# ---------------------------------------------------------------------------
# Anti-copia (misma técnica que T129, umbral de esta pista)
# ---------------------------------------------------------------------------

def _palabras(texto: str) -> List[str]:
    return norm(texto or "").split()


def construir_indice_copia(cita: str,
                           max_consecutivas: int = MAX_CONSECUTIVAS_COPIA
                           ) -> set:
    palabras = _palabras(cita)
    n = max_consecutivas + 1
    indice = set()
    for i in range(0, max(0, len(palabras) - n + 1)):
        indice.add(hash(tuple(palabras[i:i + n])))
    return indice


def es_copia_literal(texto: str, indice: Optional[set] = None,
                      cita: Optional[str] = None,
                      max_consecutivas: int = MAX_CONSECUTIVAS_COPIA) -> bool:
    if indice is None:
        if cita is None:
            raise ValueError("falta cita o indice")
        indice = construir_indice_copia(cita, max_consecutivas)
    palabras = _palabras(texto)
    n = max_consecutivas + 1
    for i in range(0, max(0, len(palabras) - n + 1)):
        if hash(tuple(palabras[i:i + n])) in indice:
            return True
    return False


def indice_copia_de(fila: Dict[str, Any]) -> set:
    return construir_indice_copia(fila.get("cita_original") or "")


# ---------------------------------------------------------------------------
# Prompt y limpieza de salida
# ---------------------------------------------------------------------------

def construir_sistema() -> str:
    return "\n".join([BASE_PROMPT, "", *REGLAS_PROMPT])


def _usuario(fila: Dict[str, Any], motivo: Optional[str]) -> str:
    entidad = fila.get("entidad_id") or ""
    carta = NOMBRE_CARTA.get(entidad, entidad)
    orient = fila.get("orientacion")
    orient_txt = "al derecho" if orient == "derecho" else "al revés"
    cita = fila.get("cita_original") or ""
    actual = fila.get("afirmacion") or ""
    s = (
        f"Carta: {carta} ({entidad})\n"
        f"Orientación: {orient_txt}\n"
        f"Afirmación actual (cita recortada):\n{actual}\n\n"
        f"Cita original del libro:\n\"{cita}\"\n\n"
        "Reescribe la cita como una afirmación breve, completa y propia, en "
        "español estándar, sin citar literalmente y sin añadir significados "
        "nuevos."
    )
    if motivo:
        s += (
            f"\n\nEl intento anterior fue rechazado: {motivo}. "
            "Corrige ese problema en esta versión."
        )
    return s


def limpiar_salida(bruto: str) -> str:
    texto = (bruto or "").strip()
    texto = _THINK_RE.sub("", texto).strip()
    texto = _PREFIX_PARAF_RE.sub("", texto, count=1).strip()
    if len(texto) >= 2 and texto[0] == '"' and texto[-1] == '"':
        texto = texto[1:-1].strip()
    return re.sub(r"\s+", " ", texto).strip()


# ---------------------------------------------------------------------------
# Verificador determinista
# ---------------------------------------------------------------------------

def es_formula_generica(fila: Dict[str, Any], texto: str) -> bool:
    """True si la paráfrasis solo describe la reversa sin contenido propio.

    Se eliminan el nombre de la carta, los marcadores de orientación y los
    conectores/verbos vacíos; si lo que queda está enteramente dentro del
    vocabulario de reversa genérica, la paráfrasis es vacía.
    """
    t = norm(texto or "")
    entidad = fila.get("entidad_id") or ""
    nombre = NOMBRE_CARTA.get(entidad, "")
    if nombre:
        t = t.replace(norm(nombre), " ")
    for frase in ("al reves", "al derecho", "posicion invertida",
                  "invertido", "invertida"):
        t = t.replace(frase, " ")
    t = norm(t)
    tokens = [w for w in t.split() if w not in _CONECTORES_VACIOS]
    return all(w in _FÓRMULA_GENÉRICA for w in tokens)


def verificar_parafrasis(fila: Dict[str, Any], bruto: str,
                         indice: set) -> Tuple[Optional[str], Optional[str]]:
    """Devuelve (texto_limpio, None) o (None, motivo_de_fallo)."""
    texto = limpiar_salida(bruto)
    if not texto:
        return None, "respuesta vacía"

    # (e) la cita debe tener contenido propio (≥40 caracteres)
    cita = fila.get("cita_original") or ""
    if len(cita) < CITA_MIN_CARACTERES:
        return None, (f"cita sin contenido propio (<{CITA_MIN_CARACTERES} "
                       f"caracteres)")

    # (f) la paráfrasis no debe ser solo una fórmula genérica de reversa
    if es_formula_generica(fila, texto):
        return None, "solo fórmula genérica sin contenido propio de la carta"

    # (a) oraciones y punto final
    if not texto.endswith("."):
        return None, "no termina en punto"
    n_oraciones = len(_ORAC_RE.findall(texto))
    if n_oraciones < 1 or n_oraciones > 2:
        return None, f"número de oraciones fuera de rango (1-2): {n_oraciones}"

    # (b) anti-copia frente a la cita original
    if es_copia_literal(texto, indice=indice):
        return None, "copia literal de la cita (>8 palabras consecutivas)"

    # (c) otra lengua / asistente de IA
    lang = detect_language(texto)
    if lang == "en":
        return None, "la paráfrasis sigue en inglés"
    tokens = [t.lower() for t in _TOKEN_RE.findall(texto)]
    tokens_set = set(tokens)
    en_hits = sorted({t for t in tokens_set if t in EN_WORDS} - _STOP_EXCEPTO)
    if en_hits:
        return None, f"palabras en inglés: {en_hits[:5]}"
    glpt = sorted(tokens_set & GLPT_MARKERS)
    if glpt:
        return None, f"marcadores de gallego/portugués: {glpt[:5]}"
    if _ASISTENTE_IA_RE.search(texto):
        return None, "contiene marcador de asistente de IA"

    # (d) orientación
    orient = fila.get("orientacion")
    if orient == "reves" and not _ORIENT_REVES_RE.search(texto):
        return None, "no se conservó la orientación al revés"
    if orient == "derecho" and not _ORIENT_DERECHO_RE.search(texto):
        return None, "no se conservó la orientación al derecho"

    return texto, None


# ---------------------------------------------------------------------------
# Error fatal de backend
# ---------------------------------------------------------------------------

def es_error_fatal(e: Exception) -> bool:
    if isinstance(e, RateLimitError):
        return True
    if isinstance(e, (requests.exceptions.Timeout,
                      requests.exceptions.ConnectionError)):
        return True
    if isinstance(e, requests.exceptions.HTTPError):
        return e.response is not None and e.response.status_code in (401, 403, 429)
    if isinstance(e, RuntimeError) and "INCEPTION_API_KEY" in str(e):
        return True
    return False


# ---------------------------------------------------------------------------
# Procesado de una fila
# ---------------------------------------------------------------------------

def parafrasear_una(cliente: LLMClient, sistema: str, fila: Dict[str, Any],
                    indice: set, max_intentos: int, temperatura: float
                    ) -> Tuple[Optional[str], Optional[str], int]:
    """Devuelve (parafrasis|None, motivo|None, intentos_usados)."""
    motivo = None
    for n in range(1, max(1, max_intentos) + 1):
        usuario = _usuario(fila, motivo)
        try:
            bruto = cliente.chat(sistema, usuario, temperature=temperatura)
        except Exception as e:
            if es_error_fatal(e):
                raise BackendFatal(str(e)[:200])
            motivo = f"error de backend: {type(e).__name__}: {str(e)[:120]}"
            continue
        limpia, motivo = verificar_parafrasis(fila, bruto, indice)
        if motivo is None:
            return limpia, None, n
    return None, motivo, max(1, max_intentos)


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


def fids_procesados(ruta: str) -> set:
    if not os.path.exists(ruta):
        return set()
    done = set()
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            fid = linea.strip()
            if fid:
                done.add(fid)
    return done


def parse_endpoint(spec: str) -> Any:
    if "=" in spec:
        url, model = spec.split("=", 1)
        return (url, model)
    return spec


def crear_cliente(args: argparse.Namespace, simulado: Optional[Any] = None) -> LLMClient:
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
    return LLMClient(
        endpoints=endpoints, model=args.model or MODEL_LOCAL_POR_DEFECTO,
        timeout=args.timeout, simulado=simulado,
        max_concurrencia=args.workers,
    )


# ---------------------------------------------------------------------------
# Lote (pool de workers)
# ---------------------------------------------------------------------------

def procesar_lote(filas: List[Dict[str, Any]], cliente: LLMClient,
                  sistema: str, args, done: set) -> Tuple[Dict[int, Dict], bool]:
    """Devuelve (resultados_por_indice, fatal). Los omitidos no aparecen."""
    def uno(item):
        n, fila, fid = item
        indice = indice_copia_de(fila)
        txt, motivo, intentos = parafrasear_una(
            cliente, sistema, fila, indice, args.max_intentos, args.temperatura)
        if txt is not None:
            nueva = {**fila, "fid": fid, "afirmacion": txt,
                     "procedencia": PROCEDENCIA}
            return {"fid": fid, "estado": "aceptada", "fila": nueva,
                    "intentos": intentos}
        return {"fid": fid, "estado": "rechazada",
                "rechazo": {**fila, "fid": fid, "motivo": motivo,
                            "intentos": intentos}}

    pendientes = []
    for n, fila in enumerate(filas):
        fid = fila.get("fid") or fid_de(fila)
        if fid not in done:
            pendientes.append((n, fila, fid))
    resultados: Dict[int, Dict] = {}
    if not pendientes:
        return resultados, False
    inicio = time.time()
    hechos = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futuros = {pool.submit(uno, item): item for item in pendientes}
        try:
            for fut in concurrent.futures.as_completed(futuros):
                res = fut.result()
                n = futuros[fut][0]
                resultados[n] = res
                hechos += 1
                if hechos % 20 == 0:
                    rate = hechos / max(1e-9, time.time() - inicio)
                    print(f"  ... {hechos}/{len(pendientes)} ({rate:.1f}/s)")
        except BackendFatal:
            pool.shutdown(wait=False, cancel_futures=True)
            return resultados, True
    return resultados, False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Parafrasea afirmaciones de baraja española (T131).")
    ap.add_argument("--entrada", required=True, help="JSONL de afirmaciones")
    ap.add_argument("--salida", help="JSONL de salida (obligatorio salvo --dry-run)")
    ap.add_argument("--procesados", help="diario de progreso "
                      "(por defecto <salida>.procesados.jsonl)")
    ap.add_argument("--rechazadas", help="JSONL de rechazos "
                      "(por defecto <salida>.rechazadas.jsonl)")
    ap.add_argument("--backend", choices=["mercury", "local"], default="mercury")
    ap.add_argument("--endpoint", action="append", default=[],
                    help='endpoint local "url" o "url=modelo" (repetible)')
    ap.add_argument("--model", default=None)
    ap.add_argument("--workers", type=int, default=2,
                    help=f"workers de red (máx. {MAX_WORKERS})")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-intentos", type=int, default=3,
                    help="intentos totales por fila (1 inicial + reintentos)")
    ap.add_argument("--temperatura", type=float, default=0.2)
    ap.add_argument("--limite", type=int, default=0,
                    help="procesar solo las N primeras filas")
    ap.add_argument("--resume", action="store_true",
                    help="omitir filas ya aceptadas (por fid en procesados)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo recuentos; sin red ni escritura")
    args = ap.parse_args(argv)

    if not args.dry_run and not args.salida:
        ap.error("--salida es obligatorio salvo con --dry-run")

    args.workers = max(1, min(args.workers, MAX_WORKERS))

    filas = leer_jsonl(args.entrada)
    if args.limite:
        filas = filas[:args.limite]
    print(f"filas: {len(filas)} | backend: {args.backend} | workers: {args.workers}")

    if args.dry_run:
        return 0

    ruta_proc = args.procesados or (args.salida + ".procesados.jsonl")
    ruta_rech = args.rechazadas or (args.salida + ".rechazadas.jsonl")
    done = fids_procesados(ruta_proc) if args.resume else set()
    if done:
        print(f"resume: {len(done)} filas ya aceptadas se omiten")

    cliente = crear_cliente(args)
    sistema = construir_sistema()
    resultados, fatal = procesar_lote(filas, cliente, sistema, args, done)

    stats = {"aceptada": 0, "rechazada": 0, "omitida": 0}
    motivos: collections.Counter = collections.Counter()
    modo = "a" if done else "w"
    with open(args.salida, modo, encoding="utf-8") as con_sal, \
            open(ruta_proc, modo, encoding="utf-8") as con_proc, \
            open(ruta_rech, modo, encoding="utf-8") as con_rech:
        for n in range(len(filas)):
            res = resultados.get(n)
            if res is None:
                stats["omitida"] += 1
                continue
            stats[res["estado"]] += 1
            if res.get("fila"):
                con_sal.write(json.dumps(res["fila"], ensure_ascii=False) + "\n")
                con_proc.write(res["fid"] + "\n")
            elif res.get("rechazo"):
                motivos[res["rechazo"]["motivo"]] += 1
                con_rech.write(json.dumps(res["rechazo"], ensure_ascii=False) + "\n")

    print(f"completo: aceptadas={stats['aceptada']} "
          f"rechazos={stats['rechazada']} omitidas={stats['omitida']}")
    for m, c in motivos.most_common():
        print(f"  rechazo [{m}]: {c}")
    print(f"salida: {args.salida} | rechazadas: {ruta_rech} | "
          f"procesados: {ruta_proc}")
    if fatal:
        print("ERROR: fallo de backend fatal; procesamiento detenido.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
