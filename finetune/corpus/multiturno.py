#!/usr/bin/env python3
"""Generador de conversaciones multi-turno en dos fases (T45).

Fase 1 (guion): el LLM actua como guionista del consultante y escribe los turnos
de usuario (pregunta inicial, aclaracion, seguimiento, reaccion emocional, tirada
adicional, limite) a partir de un perfil y una tarea de lectura.

Fase 2 (respuestas): el LLM actua como la lectora y responde turno a turno
usando la Referencia de la KB y el historial, sin cambiar las cartas ni repetir lo
ya dicho.

El cliente LLM es inyectable (``LLMClient`` con ``simulado`` en los tests) y la
generacion es reanudable por semilla: si la tarea ya trae un guion valido, no se
regenera (se reanuda tal cual).

ESQUEMA JSONL (una linea por conversacion), compatible con build_dataset.py
(ShareGPT ``from``/``value``) y merge_final.py (``turnos_de``/``human_of``/
``answer_of``/``sha``; las claves extra se conservan intactas)::

    {
      "conversations": [
        {"from": "system", "value": <SYSTEM de la lectora>},
        {"from": "human",  "value": <turno del consultante 1>},
        {"from": "gpt",    "value": <respuesta de la lectora 1>},
        {"from": "human",  "value": <turno del consultante 2>},
        {"from": "gpt",    "value": <respuesta de la lectora 2>}
        // ... alternan human/gpt; N pares
      ],
      "turnos": <int: numero de pares consultante/lectora>,
      "metadatos": {
        "bloque": "multiturno",
        "sistema": <SYSTEM>,
        "cartas": [{"nombre": str, "invertida": bool}, ...],  // fijas: no cambian
        "contexto": str,
        "referencia": str,            // bloque de significados de la KB
        "datos_calculados": str,      // opcional (astro/numerologia)
        "semilla": int,               // reproducibilidad y reanudacion
        "perfil": str,                // perfil del consultante
        "tipos": [str, ...],          // tipo de cada turno del guion
        "verificada": bool,           // resultado del verificador (CLI)
        "motivo": str                 // motivo del verificador (CLI)
      }
    }
"""
from __future__ import annotations

import argparse
import json
import random
import re

from llm_client import LLMClient
from generate_tasks import (
    CONTEXTOS,
    PREGUNTAS,
    SYSTEM,
    Builder,
    carta_txt,
    load_kb,
    referencia_tarot,
)
import validate_synthetic as vs
from translate_dataset import detect_language
import fase1_prompts as fp

# Marcas que afirman que una carta esta al derecho (para detectar el giro
# contrario en una carta que se sorteo invertida).
DERECHO_MARCAS = ("al derecho", "al recto")

# Tipos de turno que debe cubrir un guion natural de una conversacion.
TIPOS_GUION = (
    "pregunta_inicial",
    "aclaracion",
    "seguimiento",
    "reaccion_emocional",
    "tirada_adicional",
    "limite",
)


def prompt_lectura(tarea: dict) -> str:
    """Cuerpo de la lectura (cartas + contexto) en formato reconocible por el
    validador (``extraer_cartas``)."""
    cartas = tarea["cartas"]
    if len(cartas) == 1:
        cuerpo = f"Tirada de una carta de tarot.\n\nCarta: {carta_txt(cartas[0])}."
    else:
        lineas = "\n".join(
            f"- posicion {i + 1}: {carta_txt(c)}" for i, c in enumerate(cartas)
        )
        cuerpo = f"Tirada de {len(cartas)} cartas de tarot.\n\n{lineas}"
    return cuerpo + f"\nContexto: {tarea['contexto']}."


def _lectura_desde_meta(meta: dict) -> str:
    cartas = meta.get("cartas")
    if not isinstance(cartas, list):
        cartas = []
    return prompt_lectura({"cartas": cartas, "contexto": meta.get("contexto", "")})


def construir_tarea(
    builder: Builder,
    semilla: int,
    n_cartas: int = 1,
    contexto: str | None = None,
    pregunta: str | None = None,
    perfil: str | None = None,
) -> dict:
    """Construye una ``tarea`` de lectura a partir de un ``Builder`` (usa su RNG)."""
    rng = builder.rng
    ctx = contexto or rng.choice(CONTEXTOS)
    cartas = builder.tirada(n_cartas)
    preg = pregunta or rng.choice(PREGUNTAS[ctx])
    return {
        "sistema": SYSTEM,
        "cartas": cartas,
        "contexto": ctx,
        "referencia": referencia_tarot(cartas, builder.cartas, ctx),
        "pregunta_inicial": preg,
        "datos_calculados": "",
        "semilla": semilla,
        "perfil": perfil or "persona adulta con una preocupacion actual",
    }


def _validar_guion(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("el guion no es un objeto JSON")
    turnos = data.get("turnos")
    if not isinstance(turnos, list) or len(turnos) < 2:
        raise ValueError("falta la lista 'turnos' con al menos 2 mensajes")
    for t in turnos:
        if not isinstance(t, dict):
            raise ValueError("cada turno debe ser un objeto")
        if not str(t.get("texto", "")).strip():
            raise ValueError("hay un turno sin texto")
        if not str(t.get("tipo", "")).strip():
            raise ValueError("hay un turno sin tipo")


def generar_guion(
    tarea: dict,
    cliente,
    n_turnos: int = 4,
    max_tokens: int = 900,
    temperature: float = 0.6,
) -> list:
    """Fase 1: el LLM escribe los turnos del consultante.

    Reanudable por semilla: si ``tarea`` ya trae un ``guion`` valido (lista de al
    menos 2 dicts con ``texto``), se devuelve tal cual sin llamar al cliente.
    """
    existente = tarea.get("guion")
    if (
        isinstance(existente, list)
        and len(existente) >= 2
        and all(isinstance(t, dict) and str(t.get("texto", "")).strip() for t in existente)
    ):
        return [dict(t) for t in existente]

    sistema = (
        "Eres el guionista de una persona real (el consultante) que acude a una "
        "lectura de tarot. Redactas SOLO sus mensajes, en espanol neutro y natural, "
        "como hablaria una persona: breve, con sus dudas y sus emociones. Nunca "
        "respondes tu como la lectora; solo escribes lo que el consultante dice, "
        "turno a turno. Escribe siempre con tildes."
    )
    cartas_txt = ", ".join(carta_txt(c) for c in tarea["cartas"])
    usuario = (
        f"Perfil del consultante: {tarea.get('perfil', 'persona adulta con una preocupacion actual')}.\n"
        f"Contexto de la consulta: {tarea['contexto']}.\n"
        f"Cartas que la lectora tiene delante: {cartas_txt}.\n"
        f"Pregunta inicial: {tarea['pregunta_inicial']}\n"
        f"Semilla: {tarea['semilla']}.\n\n"
        f"Escribe {n_turnos} mensajes del consultante, en orden, como JSON:\n"
        '{"turnos": [{"tipo": "...", "texto": "..."}, ...]}\n'
        "Cubre, en el orden natural de una conversacion, tipos como: "
        "pregunta_inicial, aclaracion, seguimiento, reaccion_emocional, "
        "tirada_adicional o limite. No inventes cartas distintas de las indicadas."
    )
    data = cliente.chat_json(
        sistema, usuario, _validar_guion, max_tokens=max_tokens, temperature=temperature
    )
    return [dict(t) for t in data["turnos"]]


def generar_respuestas(
    guion: list,
    tarea: dict,
    cliente,
    max_tokens: int = 900,
    temperature: float = 0.4,
) -> list:
    """Fase 2: la lectora responde turno a turno con la Referencia y el historial."""
    sistema = tarea["sistema"]
    lectura = prompt_lectura(tarea)
    respuestas: list = []
    historial: list = []
    for turno in guion:
        partes = [lectura]
        if tarea.get("referencia"):
            partes.append(tarea["referencia"])
        if tarea.get("datos_calculados"):
            partes.append(tarea["datos_calculados"])
        if historial:
            partes.append("Conversacion hasta ahora:\n" + "\n".join(historial))
        partes.append("Mensaje del consultante: " + str(turno["texto"]))
        partes.append(
            "Responde a este mensaje como la lectora: mantén el hilo de la lectura, "
            "no la repitas, usa solo las cartas dadas, en espanol neutro, sin "
            "diagnosticos ni promesas."
        )
        usuario = "\n\n".join(partes)
        r = cliente.chat(sistema, usuario, max_tokens=max_tokens, temperature=temperature)
        respuestas.append(r)
        historial.append("Consultante: " + str(turno["texto"]))
        historial.append("Lectora: " + r)
    return respuestas


def construir_fila(guion: list, respuestas: list, tarea: dict) -> dict:
    """Ensambla la fila JSONL (ShareGPT + turnos + metadatos)."""
    if len(guion) != len(respuestas):
        raise ValueError(
            "Guion y respuestas desalineados: %d turnos frente a %d respuestas"
            % (len(guion), len(respuestas))
        )
    conv = [{"from": "system", "value": tarea["sistema"]}]
    for turno, r in zip(guion, respuestas):
        conv.append({"from": "human", "value": str(turno["texto"])})
        conv.append({"from": "gpt", "value": r})
    return {
        "conversations": conv,
        "turnos": len(guion),
        "metadatos": {
            "bloque": "multiturno",
            "sistema": tarea["sistema"],
            "cartas": [dict(c) for c in tarea["cartas"]],
            "contexto": tarea["contexto"],
            "referencia": tarea.get("referencia", ""),
            "datos_calculados": tarea.get("datos_calculados", ""),
            "semilla": tarea["semilla"],
            "perfil": tarea.get("perfil", ""),
            "tipos": [str(t.get("tipo", "")) for t in guion],
        },
    }


def _orientacion_turno(respuesta: str, carta: dict) -> bool:
    """True si la respuesta no le cambia la orientacion a ``carta`` donde la menciona.

    - Carta al derecho: no debe afirmarse inversion cerca de su nombre.
    - Carta invertida: no debe afirmarse que esta al derecho cerca de su nombre.
    Si el turno no menciona la carta, no hay restriccion.
    """
    token = vs._sin_articulo(vs.norm(carta["nombre"]))
    if not token:
        return True
    na = vs.norm(respuesta)
    menciones = list(re.finditer(r"\b" + re.escape(token) + r"\b", na))
    if not menciones:
        return True
    for m in menciones:
        ventana = na[max(0, m.start() - 40): m.end() + 40]
        if carta.get("invertida"):
            if any(d in ventana for d in DERECHO_MARCAS):
                return False
        else:
            if any(f in ventana for f in vs.INVERT_AFIRMA):
                return False
    return True


_UNIVERSO_TAROT: list | None = None


def _universo_tarot() -> list:
    """Nombres de todas las cartas del tarot (mayores + menores), cacheado."""
    global _UNIVERSO_TAROT
    if _UNIVERSO_TAROT is None:
        kb = load_kb("tarot.json")
        _UNIVERSO_TAROT = [c["nombre"] for c in kb["mayores"] + kb["menores"]]
    return _UNIVERSO_TAROT


def _tarea_para_verif(meta: dict) -> dict:
    """Reconstruye la ``tarea`` que espera ``fase1_prompts.verificar_lectura`` a
    partir de los ``metadatos`` de la fila (cartas, orientaciones, calculos)."""
    return {
        "familia": "tarot_multiturno",
        "contexto": meta.get("contexto", ""),
        "pregunta": "",
        "cartas": [dict(c) for c in meta.get("cartas", [])],
        "universo_cartas": meta.get("universo_cartas") or _universo_tarot(),
        "calculos": meta.get("calculos") or {},
    }


_INV_ORIENT_RE = re.compile(
    r"(?:est[áa]|sale|queda|aparece|resulta|va|viene)\s+(?:muy\s+|algo\s+)?invertid"
    r"|invertid[ao]\s+(?:la\s+)?carta"
    r"|carta[^.\n]{0,25}invertid"
    r"|\bal\s+rev[eé]s\b",
    re.IGNORECASE,
)


def _afirmacion_inversion(texto: str) -> bool:
    """True si el texto AFIRMA que una carta esta invertida (copia/verbo de estado
    o proximidad a «carta»), no el uso comun de «invertido» (p. ej. «tiempo
    invertido»). Compuerta para el chequeo de orientacion de ``fase1_prompts``,
    demasiado laxo para texto conversacional."""
    return bool(_INV_ORIENT_RE.search(texto or ""))


def _clasificar_vedado(motivos: list) -> str:
    """Categoriza los motivos de ``verificar_lectura`` en un codigo corto."""
    for mt in motivos:
        low = mt.lower()
        if "carta ajena" in low:
            return "carta_ajena"
        if "juego" in low or "apuesta" in low:
            return "juego"
        if any(k in low for k in ("medicaci", "depres", "curar", "sanar", "morir")):
            return "diagnostico"
        if "orientaci" in low:
            return "orientacion"
        if "contradic" in low:
            return "contradiccion"
        if "promesa" in low or "garant" in low:
            return "promesa"
    return "vedado"


def verificar_conversacion(fila: dict, args, bloque: str | None = None):
    """Verificador de coherencia multi-turno. Devuelve ``(ok, motivo)``.

    Comprueba: numero de turnos, longitud, boilerplate, idioma, repeticion y
    ``ia_meta`` por turno; en el turno 1, anclaje a los datos y orientacion; en
    cruzado, que las cartas no cambian de orientacion, que cada turno recuerda lo
    dicho antes (hilo) y que ningun turno copia a otro; y por cada turno de la
    lectora, los vedados de contenido de ``fase1_prompts.verificar_lectura``
    (promesas, juego/apuestas, diagnosticos, carta ajena, orientacion contraria y
    contradicciones con lo calculado). En los turnos de seguimiento no se exige
    repetir todas las cartas, pero si se rechazan los demas vedados.
    """
    pares = vs.turnos_de(fila)
    if len(pares) < 2:
        return False, "sin_turnos"
    meta = fila.get("metadatos", {})
    bloque = bloque or meta.get("bloque", "multiturno")
    cartas = meta.get("cartas")
    if not isinstance(cartas, list):
        cartas = []
    lectura = _lectura_desde_meta(meta)

    for humano, gpt in pares:
        if not humano or not gpt:
            return False, "turno_vacio"
        if len(gpt) < args.min_chars:
            return False, "corto"
        if len(gpt) > args.max_chars:
            return False, "largo"
        if any(m in gpt.lower() for m in vs.JUNK):
            return False, "boilerplate"
        lang = detect_language(gpt)
        if lang not in ("es", "mixed"):
            return False, f"idioma_{lang}"
        if vs.repetition_ratio(gpt) > args.max_repetition:
            return False, "repeticion"
        if vs._copia_turno1(humano, gpt):
            return False, "copia_pregunta"
        if bloque != "etica" and vs.ia_meta(gpt):
            return False, "ia_meta"

    if cartas:
        if not vs.grounding(lectura, pares[0][1]):
            return False, "sin_datos"
        if not vs.orientacion_ok(lectura, pares[0][1]):
            return False, "orientacion"

    m = vs.QUESTION_RE.search(pares[0][0])
    if m:
        q = vs.normalize(m.group(1))
        if len(q) > 25 and vs.normalize(pares[0][1][:120]).startswith(q[:40]):
            return False, "eco_pregunta"

    for carta in cartas:
        for _humano, gpt in pares:
            if not _orientacion_turno(gpt, carta):
                return False, "carta_cambiada"

    for i in range(1, len(pares)):
        previo = " ".join(g for _h, g in pares[:i])
        if vs._sin_hilo(previo, pares[i][1]):
            return False, "sin_hilo"
        for j in range(i):
            if vs._copia_turno1(pares[j][1], pares[i][1]):
                return False, "copia"

    # Vedados de contenido (T44 fase1_prompts) por cada turno de la lectora.
    if cartas:
        tarea_verif = _tarea_para_verif(meta)
        # En turnos de seguimiento no se exige repetir todas las cartas ni volver
        # a indicar la inversion; si se rechazan carta ajena, orientacion contraria
        # (la pilla tambien _orientacion_turno), promesas, juego y contradicciones.
        _seguimiento_omitir = (
            "Falta la carta de la tirada",
            "No indica la orientaci",
        )
        for i, (_humano, gpt) in enumerate(pares):
            ok_v, motivos = fp.verificar_lectura(tarea_verif, gpt)
            if ok_v:
                continue
            limpios = []
            for mt in motivos:
                if i >= 1 and mt.startswith(_seguimiento_omitir):
                    continue
                if mt.startswith("Menciona una orientaci") and not _afirmacion_inversion(gpt):
                    continue
                limpios.append(mt)
            if limpios:
                return False, _clasificar_vedado(limpios)

    return True, "ok"


def generar_conversacion(tarea: dict, cliente, args, n_turnos: int = 4):
    """Pipeline completo: guion -> respuestas -> fila -> verificacion."""
    guion = generar_guion(tarea, cliente, n_turnos=n_turnos)
    respuestas = generar_respuestas(guion, tarea, cliente)
    fila = construir_fila(guion, respuestas, tarea)
    ok, motivo = verificar_conversacion(fila, args)
    fila["metadatos"]["verificada"] = ok
    fila["metadatos"]["motivo"] = motivo
    return fila, ok, motivo


# --- Cliente simulado determinista (para CLI --simulado y tests) ---

def _sim_guion(usuario: str) -> str:
    turnos = [
        {
            "tipo": "pregunta_inicial",
            "texto": "Que me dicen las cartas sobre lo que estoy viviendo ahora mismo?",
        },
        {
            "tipo": "aclaracion",
            "texto": "No lo tengo claro: te refieres a hoy o a las proximas semanas?",
        },
        {
            "tipo": "seguimiento",
            "texto": "Y eso que me comentas, como lo aplico a la decision que tengo entre manos?",
        },
        {
            "tipo": "reaccion_emocional",
            "texto": "Me deja mas tranquila lo que dices, aunque me cuesta creerlo del todo.",
        },
    ]
    return json.dumps({"turnos": turnos}, ensure_ascii=False)


def _sim_lector(usuario: str) -> str:
    cartas = vs.extraer_cartas(usuario)
    if cartas:
        nombre, orient = cartas[0]
    else:
        nombre, orient = "la carta", "derecho"
    if orient == "invertida":
        base = f"La carta {nombre} aparece invertida, y ese bloqueo o sombra pide mirar hacia dentro"
    else:
        base = f"La carta {nombre} sale al derecho y acompana tu momento con claridad"
    idx = usuario.count("Lectora:")
    plantillas = [
        base + ". Es un tiempo de calma y de escucha atenta. Avanza con paciencia y sin forzar lo que aun no esta listo.",
        base + ". Lo que ya hemos visto se confirma hoy. Da un paso pequeno y claro sobre el mismo asunto, sin dar vueltas.",
        base + ". Entiendo tu inquietud y la acompano. Observa esta semana como se manifiesta esa energia y anota lo que cambie.",
        base + ". Puedo sacar una carta mas si lo necesitas. Refuerza lo dicho y te pide actuar con honestidad y criterio.",
        base + ". Esto orienta, no sentencia ni promete. Cuidate, no decidas desde el miedo y busca ayuda profesional si hace falta.",
    ]
    return plantillas[idx % len(plantillas)]


def simulacion(sistema: str, usuario: str) -> str:
    """Cliente simulado: guionista si el system lo indica, lectora en otro caso."""
    if "guionista" in sistema:
        return _sim_guion(usuario)
    return _sim_lector(usuario)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Genera conversaciones multi-turno en dos fases (T45).")
    ap.add_argument("--n", type=int, default=5, help="numero de conversaciones")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="/tmp/t45/ejemplos.jsonl")
    ap.add_argument("--n-turnos", type=int, default=4)
    ap.add_argument("--n-cartas", type=int, default=1)
    ap.add_argument("--simulado", action="store_true", help="usa el cliente simulado (sin red)")
    ap.add_argument("--min-chars", type=int, default=150)
    ap.add_argument("--max-chars", type=int, default=4000)
    ap.add_argument("--max-repetition", type=float, default=0.12)
    args = ap.parse_args(argv)

    if args.simulado:
        cliente = LLMClient(simulado=simulacion)
    else:
        cliente = LLMClient(timeout=120.0)

    builder = Builder(
        random.Random(args.seed),
        load_kb("tarot.json"),
        load_kb("astrologia.json"),
        load_kb("numerologia.json"),
    )

    from pathlib import Path

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ok_count = 0
    with out.open("w", encoding="utf-8") as fh:
        for i in range(args.n):
            tarea = construir_tarea(builder, semilla=args.seed + i, n_cartas=args.n_cartas)
            fila, ok, motivo = generar_conversacion(tarea, cliente, args, n_turnos=args.n_turnos)
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            ok_count += 1 if ok else 0
            print(f"conv {i + 1}: turnos={fila['turnos']} ok={ok} ({motivo})")
    print(f"escritas {args.n} en {out} · verificadas {ok_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
