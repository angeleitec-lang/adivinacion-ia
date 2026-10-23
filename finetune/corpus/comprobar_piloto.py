#!/usr/bin/env python3
"""Comprobación determinista (sin GPU, sin LLM, sin red) de lo que falta para un
piloto LoRA/SFT sobre el dataset v1d preparado en chatml.

Revisa, de forma reproductible y sin descargar nada:

* formato ShareGPT de ``train``/``val`` (roles, orden, system único al inicio),
* plantilla chat del fichero preparado en chatml (roles ``system``/``user``/
  ``assistant``, alternancia, termina en ``assistant``),
* longitud en tokens estimada (``chars / 3.5``: el tokenizador de Qwen2.5 no está
  instalado en local y no se descarga),
* filas que exceden la ventana de contexto (``max_length`` de la config),
* número de pasos por época y totales para el conjunto de entrenamiento,
* cobertura por familia (``bloque``) y huecos que bloquean o degradan el piloto.

No entrena, no llama a ningún LLM, no toca los nodos y no instala paquetes.

Uso::

    python comprobar_piloto.py [--dataset DIR] [--config NOMBRE.yaml] [--json SALIDA]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
if str(CORPUS_DIR) not in sys.path:
    sys.path.insert(0, str(CORPUS_DIR))

ENTRENAMIENTO_DIR = CORPUS_DIR.parent / "entrenamiento"
if str(ENTRENAMIENTO_DIR) not in sys.path:
    sys.path.insert(0, str(ENTRENAMIENTO_DIR))

import preparar_entrenamiento as prep  # noqa: E402

try:  # ajuste_config vive en finetune/entrenamiento
    import ajuste_config as ac  # noqa: E402
except Exception:  # pragma: no cover - dependencia opcional
    ac = None

DATASET_POR_DEFECTO = Path("/Users/angelgonzalez/fase0/dataset_fase1_v1d")
CONFIG_POR_DEFECTO = "qlora_14b.yaml"
SPLITS = ("train", "val", "test")
CHATML_ROLES = ("system", "user", "assistant")
CHAR_POR_TOKEN = 3.5

# Familias mínimas que deben aparecer en test para poder evaluarlas.
FAMILIAS_EVALUABLES = (
    "tarot_1", "tarot_2", "tarot_3", "tarot_pregunta", "cruz_celta",
    "espanola_1", "espanola_3", "espanola_5", "espanola_7",
    "astro_natal", "sinastria", "revolucion_solar",
    "numerologia", "biorritmos", "etica", "fuera_alcance",
    "lectura_completa", "multiturno", "transitos",
)
# Umbrales de val por familia por debajo de los cuales la métrica es poco fiable.
VAL_MINIMO_FAMILIA = 10


def estimar_tokens(texto: str, char_por_token: float = CHAR_POR_TOKEN) -> int:
    """Tokens estimados de un texto plano (sin tokenizador local)."""
    return int(round(len(str(texto or "")) / char_por_token))


def tokens_de_fila_chatml(fila: dict, char_por_token: float = CHAR_POR_TOKEN) -> int:
    """Tokens estimados de una fila chatml (``messages`` con ``content``)."""
    texto = "\n".join(
        str(m.get("content", ""))
        for m in fila.get("messages", [])
        if isinstance(m, dict)
    )
    return estimar_tokens(texto, char_por_token)


def validar_chatml(fila: dict) -> list[str]:
    """Errores de plantilla chat de una fila chatml.

    Reglas: roles válidos, como mucho un ``system`` y en primera posición, el
    cuerpo empieza en ``user``, alterna ``user``/``assistant`` y termina en
    ``assistant``. Ningún turno vacío.
    """
    if not isinstance(fila, dict):
        return ["la fila no es un objeto JSON"]
    mensajes = fila.get("messages")
    if not isinstance(mensajes, list) or not mensajes:
        return ["falta 'messages' o está vacío"]
    errores: list[str] = []
    roles: list = []
    for i, m in enumerate(mensajes):
        if not isinstance(m, dict):
            errores.append(f"turno {i}: no es un objeto")
            continue
        rol = m.get("role")
        roles.append(rol)
        if rol not in CHATML_ROLES:
            errores.append(f"turno {i}: rol inválido {rol!r}")
        if not str(m.get("content", "")).strip():
            errores.append(f"turno {i}: contenido vacío")
    sistemas = [i for i, r in enumerate(roles) if r == "system"]
    if len(sistemas) > 1:
        errores.append(f"más de un turno 'system' ({len(sistemas)})")
    elif sistemas and sistemas[0] != 0:
        errores.append("'system' debe ir en la primera posición")
    cuerpo = roles[1:] if (sistemas and sistemas[0] == 0) else roles
    if not cuerpo:
        errores.append("no hay turnos de conversación tras el system")
    else:
        if cuerpo[0] != "user":
            errores.append("la conversación debe empezar en 'user'")
        if cuerpo[-1] != "assistant":
            errores.append("la conversación debe terminar en 'assistant'")
        for a, b in zip(cuerpo, cuerpo[1:]):
            if a == b:
                errores.append("turnos consecutivos del mismo rol")
    return errores


def _iterar_jsonl(ruta: Path):
    with ruta.open("r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                yield json.loads(linea)


def analizar_split_sharegpt(ruta: Path, max_length: int) -> dict:
    """Valida formato ShareGPT y agrupa tokens y familias (``bloque``)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {"existe": False, "ruta": str(ruta)}
    n = 0
    invalidas = 0
    muestras_invalidas: list[dict] = []
    tokens: list[int] = []
    bloques: Counter = Counter()
    exceden = 0
    for fila in _iterar_jsonl(ruta):
        n += 1
        errs = prep.validar_fila(fila)
        if errs:
            invalidas += 1
            if len(muestras_invalidas) < 5:
                muestras_invalidas.append({
                    "id": fila.get("id"),
                    "errores": errs,
                })
        tok = _tokens_sharegpt_local(fila)
        tokens.append(tok)
        if tok > max_length:
            exceden += 1
        bloques[fila.get("bloque", "?")] += 1
    resumen = _resumen(tokens)
    return {
        "existe": True,
        "ruta": str(ruta),
        "n": n,
        "invalidas": invalidas,
        "muestras_invalidas": muestras_invalidas,
        "tokens": resumen,
        "exceden_contexto": exceden,
        "pct_exceden": round(100.0 * exceden / n, 2) if n else 0.0,
        "bloques": dict(bloques),
    }


def _tokens_sharegpt_local(fila: dict) -> int:
    texto = "\n".join(
        str(t.get("value", ""))
        for t in fila.get("conversations", [])
        if isinstance(t, dict)
    )
    return estimar_tokens(texto)


def analizar_split_chatml(ruta: Path, max_length: int) -> dict:
    """Valida la plantilla chat del fichero preparado y agrupa tokens."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {"existe": False, "ruta": str(ruta)}
    n = 0
    invalidas = 0
    muestras_invalidas: list[dict] = []
    tokens: list[int] = []
    exceden = 0
    for fila in _iterar_jsonl(ruta):
        n += 1
        errs = validar_chatml(fila)
        if errs:
            invalidas += 1
            if len(muestras_invalidas) < 5:
                muestras_invalidas.append({"errores": errs})
        tok = tokens_de_fila_chatml(fila)
        tokens.append(tok)
        if tok > max_length:
            exceden += 1
    return {
        "existe": True,
        "ruta": str(ruta),
        "n": n,
        "invalidas": invalidas,
        "muestras_invalidas": muestras_invalidas,
        "tokens": _resumen(tokens),
        "exceden_contexto": exceden,
        "pct_exceden": round(100.0 * exceden / n, 2) if n else 0.0,
    }


def _resumen(valores: list[int]) -> dict:
    if not valores:
        return {"n": 0, "media": 0.0, "p50": 0, "p95": 0, "p99": 0, "max": 0}
    ordenados = sorted(valores)
    return {
        "n": len(ordenados),
        "media": round(statistics.fmean(ordenados), 1),
        "p50": _percentil(ordenados, 0.50),
        "p95": _percentil(ordenados, 0.95),
        "p99": _percentil(ordenados, 0.99),
        "max": ordenados[-1],
    }


def _percentil(ordenados: list[int], q: float) -> int:
    if not ordenados:
        return 0
    idx = min(len(ordenados) - 1, max(0, int(round(q * (len(ordenados) - 1)))))
    return ordenados[idx]


def calcular_pasos(n_ejemplos: int, batch_size: int, grad_accum: int,
                  epochs: float) -> dict:
    """Pasos por época y totales para un lote efectivo dado."""
    lote_efectivo = batch_size * grad_accum
    if lote_efectivo <= 0:
        raise ValueError("batch_size y grad_accum deben ser positivos")
    pasos_epoca = -(-n_ejemplos // lote_efectivo)  # techo
    total = int(round(pasos_epoca * epochs))
    return {
        "n_ejemplos": n_ejemplos,
        "batch_size": batch_size,
        "grad_accum": grad_accum,
        "lote_efectivo": lote_efectivo,
        "pasos_por_epoca": pasos_epoca,
        "epochs": epochs,
        "pasos_totales": total,
    }


def detectar_huecos(train: dict, val: dict, test: dict,
                   chatml_train: dict, config: dict) -> list[dict]:
    """Lista priorizada de huecos que bloquean o degradan el piloto."""
    huecos: list[dict] = []

    def add(severidad, titulo, accion):
        huecos.append({"severidad": severidad, "titulo": titulo, "accion": accion})

    # Formato chatml inválido: bloquea el arranque.
    if chatml_train.get("existe") and chatml_train.get("invalidas", 0) > 0:
        add("BLOQUEANTE",
            f"{chatml_train['invalidas']} filas chatml con plantilla inválida",
            "Revisar alternancia de roles y system único antes de lanzar.")

    # Filas que exceden contexto: degradan (truncamiento silencioso).
    for nombre, sp in (("train", train), ("val", val)):
        if sp.get("existe") and sp.get("exceden_contexto", 0) > 0:
            add("DEGRADA",
                f"{sp['exceden_contexto']} filas de {nombre} superan "
                f"max_length={config.get('max_length')}",
                "Confirmar política de truncamiento o subir max_length; "
                "revisar lectura_completa (filas largas).")

    # Familias sin test: no se pueden medir.
    bloques_test = test.get("bloques", {}) if test.get("existe") else {}
    sin_test = [f for f in FAMILIAS_EVALUABLES if bloques_test.get(f, 0) == 0]
    if sin_test:
        add("BLOQUEANTE",
            "familias sin ejemplos en test: " + ", ".join(sin_test),
            "Generar ejemplos de test para poder evaluar esas familias.")

    # Val por familia insuficiente: métrica poco fiable.
    bloques_val = val.get("bloques", {}) if val.get("existe") else {}
    val_bajo = sorted(
        f for f in FAMILIAS_EVALUABLES
        if 0 < bloques_val.get(f, 0) < VAL_MINIMO_FAMILIA
    )
    if val_bajo:
        add("DEGRADA",
            "val con <10 ejemplos en: " + ", ".join(val_bajo),
            "Ampliar val o agrupar familias para la métrica de selección.")

    # Dos system prompts mezclados.
    sistemas = _sistemas_distintos(train) if train.get("existe") else []
    if len(sistemas) > 1:
        add("DEGRADA",
            f"{len(sistemas)} system prompts distintos en train",
            "Unificar el system prompt o decidir cuál domina en el piloto.")

    # Filas sin familia etiquetada.
    sin_bloque = train.get("bloques", {}).get("?", 0) if train.get("existe") else 0
    if sin_bloque:
        add("DEGRADA",
            f"{sin_bloque} filas de train sin 'bloque' (sin familia)",
            "Etiquetar o excluir de la métrica por familia.")

    if not huecos:
        add("OK", "sin huecos detectados por este script",
            "Pendiente de revisión semántica humana.")
    return huecos


def _sistemas_distintos(train: dict) -> list[str]:
    """Devuelve los textos system distintos (prefijo) en el split ShareGPT."""
    ruta = Path(train.get("ruta", ""))
    if not ruta.is_file():
        return []
    vistos: dict[str, int] = {}
    for fila in _iterar_jsonl(ruta):
        for t in fila.get("conversations", []):
            if isinstance(t, dict) and t.get("from") == "system":
                clave = str(t.get("value", ""))[:48]
                vistos[clave] = vistos.get(clave, 0) + 1
                break
    return list(vistos.keys())


def normalizar_config(cruda: dict) -> dict:
    """Aplane las claves anidadas de la config YAML de Soup a claves planas."""
    data = obtener(cruda, "data", {}) or {}
    training = obtener(cruda, "training", {}) or {}
    return {
        "base_model": obtener(cruda, "base", "Qwen/Qwen2.5-14B-Instruct"),
        "max_length": int(data.get("max_length", 4096)),
        "batch_size": int(training.get("batch_size", 2)),
        "grad_accum": int(training.get("gradient_accumulation_steps", 8)),
        "epochs": float(training.get("epochs", 3)),
        "lr": training.get("lr"),
        "format": data.get("format", "chatml"),
    }


def obtener(d: dict, clave: str, por_defecto=None):  # noqa: N802
    return d.get(clave, por_defecto) if isinstance(d, dict) else por_defecto


def cargar_config_piloto(nombre: str) -> dict:
    """Carga y normaliza la config YAML del piloto (con fallback mínimo)."""
    ruta = ENTRENAMIENTO_DIR / nombre
    if ac is not None and ruta.exists():
        return normalizar_config(ac.cargar_config(ruta))
    # Fallback mínimo coherente con qlora_14b.yaml.
    return {
        "max_length": 4096,
        "batch_size": 2,
        "grad_accum": 8,
        "epochs": 3,
        "base_model": "Qwen/Qwen2.5-14B-Instruct",
    }


def resumen_piloto(dataset_dir: Path, config: dict) -> dict:
    """Composición completa del estado del piloto (determinista)."""
    dataset_dir = Path(dataset_dir)
    preparado = dataset_dir / "preparado"
    max_len = int(config.get("max_length", 4096))
    train = analizar_split_sharegpt(dataset_dir / "train.jsonl", max_len)
    val = analizar_split_sharegpt(dataset_dir / "val.jsonl", max_len)
    test = analizar_split_sharegpt(dataset_dir / "test.jsonl", max_len)
    chatml_train = analizar_split_chatml(preparado / "train.jsonl", max_len)
    n_entreno = train.get("n", 0) if train.get("existe") else 0
    pasos = calcular_pasos(
        n_entreno,
        int(config.get("batch_size", 2)),
        int(config.get("grad_accum", 8)),
        float(config.get("epochs", 3)),
    )
    huecos = detectar_huecos(train, val, test, chatml_train, config)
    bloqueantes = [h for h in huecos if h["severidad"] == "BLOQUEANTE"]
    return {
        "config": {
            "base_model": config.get("base_model"),
            "max_length": max_len,
            "batch_size": config.get("batch_size"),
            "grad_accum": config.get("grad_accum"),
            "epochs": config.get("epochs"),
        },
        "splits": {"train": train, "val": val, "test": test},
        "chatml_train": chatml_train,
        "pasos": pasos,
        "huecos": huecos,
        "semforo": "ROJO" if bloqueantes else "AMBAR",
    }


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--dataset", default=str(DATASET_POR_DEFECTO),
                   help="directorio del dataset v1d")
    p.add_argument("--config", default=CONFIG_POR_DEFECTO,
                   help="nombre de la config YAML en finetune/entrenamiento")
    p.add_argument("--json", default=None, help="ruta de salida JSON del informe")
    return p


def main(argv=None) -> int:
    args = construir_parser().parse_args(argv)
    config = cargar_config_piloto(args.config)
    informe = resumen_piloto(Path(args.dataset), config)
    if args.json:
        Path(args.json).write_text(
            json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    _imprimir(informe)
    return 0


def _imprimir(informe: dict) -> None:
    cfg = informe["config"]
    print(f"Piloto base={cfg['base_model']} max_len={cfg['max_length']} "
          f"lote={cfg['batch_size']}x{cfg['grad_accum']} epocas={cfg['epochs']}")
    for nombre in SPLITS:
        sp = informe["splits"][nombre]
        if not sp.get("existe"):
            print(f"  {nombre}: NO EXISTE")
            continue
        tok = sp["tokens"]
        print(f"  {nombre}: n={sp['n']} invalidas={sp['invalidas']} "
              f"tokens(media/p95/max)={tok['media']}/{tok['p95']}/{tok['max']} "
              f"exceden={sp['exceden_contexto']} ({sp['pct_exceden']}%)")
    ct = informe["chatml_train"]
    if ct.get("existe"):
        print(f"  chatml train: n={ct['n']} invalidas={ct['invalidas']} "
              f"exceden={ct['exceden_contexto']}")
    ps = informe["pasos"]
    print(f"  pasos: {ps['pasos_por_epoca']}/época "
          f"(lote {ps['lote_efectivo']}) total={ps['pasos_totales']}")
    print(f"  SEMAFORO: {informe['semforo']}")
    for h in informe["huecos"]:
        print(f"    [{h['severidad']}] {h['titulo']} -> {h['accion']}")


if __name__ == "__main__":
    raise SystemExit(main())
