#!/usr/bin/env python3
"""T103: de las lecturas de Mercury al dataset de entrenamiento, en un solo comando.

Encadena con salvaguardas y reanudación:

  (a) snapshot  copia instantánea de aceptadas.jsonl (la generación sigue escribiendo
      en fase1_mercury: aquí solo se lee una vez y se trabaja sobre la copia).
  (b) reverificar  reverificar_fase1 con el verificador vigente (separa inválidas
      con motivo).
  (c) filtro  fuga de evaluación por id y por contenido normalizado contra los
      casos de las semillas reservadas (560056-560058) + duplicados exactos y
      casi duplicados dentro de cada familia.
  (d) sharegpt  adaptación a ShareGPT reutilizando ejecutor_fase1.a_sharegpt,
      conservando bloque, id y generador.
  (e) validar  validate_synthetic con los parámetros de producción.
  (f) fusion  build_dataset (corpus real de fase 0, solo lectura) + merge_final
      hacia el directorio de salida (train/val/test; el test del dataset NO es el
      conjunto de evaluación T56).
  (g) preparar  preparar_entrenamiento con su informe y semáforo (rojo = parada).

Cada etapa deja su registro en <salida>/_etapas/registro.jsonl con la huella
(sha256 de entradas + parámetros). Si una etapa ya está «completada» con la misma
huella se omite (reanudación); si falla, queda «fallida» y el proceso para.

Uso (producción, sin red):

  python3 finetune/corpus/armar_dataset_v1.py

Repetir cuando acabe la generación: el mismo comando; la huella de la entrada
habrá cambiado y la cadena vuelve a correr completa sobre la nueva copia.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import build_dataset as bd
import evaluacion_casos
import merge_final
import preparar_entrenamiento as pe
import reverificar_fase1
import validate_synthetic as vs
from ejecutor_fase1 import a_sharegpt

from generate_tasks import TARGETS

CORPUS_DIR = Path(__file__).resolve().parent
ENTRADA_POR_DEFECTO = "/Users/angelgonzalez/fase0/fase1_mercury/aceptadas.jsonl"
SALIDA_POR_DEFECTO = "/Users/angelgonzalez/fase0/dataset_fase1_v1"
RAW_REAL_POR_DEFECTO = str(CORPUS_DIR / "raw")
MANIFEST_POR_DEFECTO = str(CORPUS_DIR / "manifest.json")

MAX_EJEMPLOS_MOTIVO = 10


def nfc(texto) -> str:
    return unicodedata.normalize("NFC", str(texto or ""))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_archivo(ruta) -> str:
    return sha256_bytes(Path(ruta).read_bytes())


def _huella(*rutas, **params) -> str:
    """Huella sha256 de ficheros (o directorios por tamaño+mtime) y parámetros."""
    h = hashlib.sha256()
    for r in rutas:
        p = Path(r)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    st = f.stat()
                    h.update(f"{f.relative_to(p)}|{st.st_size}|{st.st_mtime_ns}"
                            .encode("utf-8"))
        elif p.exists():
            h.update(f"ARCHIVO:{p.name}:".encode("utf-8"))
            h.update(Path(p).read_bytes())
        else:
            h.update(b"AUSENTE")
    for k in sorted(params):
        h.update(f"{k}={params[k]}".encode("utf-8"))
    return h.hexdigest()


def turnos_gpt(fila: dict) -> int:
    return sum(1 for c in fila.get("conversations", [])
              if isinstance(c, dict) and c.get("from") == "gpt")


def respuesta_completa(fila: dict) -> str:
    return "\n".join(c.get("value", "") for c in fila.get("conversations", [])
                    if isinstance(c, dict) and c.get("from") == "gpt")


def humano_completo(fila: dict) -> str:
    return "\n".join(c.get("value", "") for c in fila.get("conversations", [])
                    if isinstance(c, dict) and c.get("from") == "human")


def prompt_de(fila: dict) -> str:
    if "prompt_user" in fila:
        return nfc(fila.get("prompt_user", ""))
    return humano_completo(fila)


def adaptar_sharegpt(fila: dict) -> dict:
    """Identidad NFC si ya es ShareGPT; si no, delega en el ejecutor.

    OJO: a_sharegpt espera registros planos; con filas que ya traen
    «conversations» produciría turnos vacíos, por eso se detecta antes.
    """
    if isinstance(fila.get("conversations"), list):
        nuevo: dict = {"conversations": [
            {"from": nfc(c.get("from", "")), "value": nfc(c.get("value", ""))}
            for c in fila["conversations"] if isinstance(c, dict)
        ]}
        for campo in ("id", "bloque", "generador"):
            if campo in fila:
                nuevo[campo] = nfc(fila[campo])
        if "calculos" in fila:
            nuevo["calculos"] = fila["calculos"]
        return nuevo
    return a_sharegpt(fila)


class Registro:
    """Registro JSONL de etapas: última entrada por etapa manda."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.ultima: dict[str, dict] = {}
        if self.ruta.exists():
            for fila in merge_final.load_jsonl(self.ruta):
                if isinstance(fila, dict) and fila.get("etapa"):
                    self.ultima[fila["etapa"]] = fila

    def esta_completada(self, etapa: str, huella: str) -> bool:
        e = self.ultima.get(etapa)
        return bool(e and e.get("estado") == "completada"
                   and e.get("huella") == huella)

    def registrar(self, etapa: str, estado: str, huella: str,
                  stats: dict | None = None) -> None:
        entrada = {
            "etapa": etapa,
            "estado": estado,
            "huella": huella,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stats": stats or {},
        }
        self.ultima[etapa] = entrada
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entrada, ensure_ascii=False) + "\n")


class Tuberia:
    """Cadena completa reanudable hacia dataset_fase1_v1."""

    def __init__(self, entrada, salida_dir, semilla: int = 42,
                 real_raw=None, manifest=None, min_chars: int = 400,
                 max_chars: int = 12000, max_repetition: float = 0.12,
                 train_ratio: float = 0.8, val_ratio: float = 0.1,
                 formato: str = "chatml"):
        self.entrada = Path(entrada)
        self.salida = Path(salida_dir)
        self.semilla = semilla
        self.real_raw = Path(real_raw) if real_raw else Path(RAW_REAL_POR_DEFECTO)
        self.manifest = Path(manifest) if manifest else Path(MANIFEST_POR_DEFECTO)
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.max_repetition = max_repetition
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.formato = formato
        self.etapas_dir = self.salida / "_etapas"
        self.eval_dir = self.etapas_dir / "eval"
        self.registro = Registro(self.etapas_dir / "registro.jsonl")

    # -- utilidades ----------------------------------------------------------
    def _p(self, *partes) -> Path:
        return self.salida.joinpath(*partes)

    def _guardar_stats(self, etapa: str, stats: dict) -> None:
        self.etapas_dir.mkdir(parents=True, exist_ok=True)
        (self.etapas_dir / f"{etapa}.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    def _leer_stats(self, etapa: str) -> dict:
        ruta = self.etapas_dir / f"{etapa}.json"
        if ruta.exists():
            return json.loads(ruta.read_text(encoding="utf-8"))
        return {}

    def ficheros_eval(self) -> list[Path]:
        return [self.eval_dir / f"evaluacion_{s}.jsonl"
                for s in evaluacion_casos.SEMILLAS_RESERVADAS]

    @property
    def eval_combinada(self) -> Path:
        """Casos congelados en formato original (claves system/user).

        Es el que espera preparar_entrenamiento.detectar_fugas, que lee `user`.
        """
        return self.eval_dir / "evaluacion_combinada.jsonl"

    @property
    def eval_sharegpt(self) -> Path:
        """Mismos casos en formato ShareGPT, para los consumidores que leen
        `conversations` (merge_final.cargar_humanos_evaluacion, reverificar).

        OJO: cargar_humanos_evaluacion usa human_of(), que solo mira
        «conversations»; con el formato user devolvería {""} y la exclusión
        por contenido no funcionaria.
        """
        return self.eval_dir / "evaluacion_sharegpt.jsonl"

    # -- etapas ------------------------------------------------------------
    def etapa_snapshot(self) -> dict:
        if not self.entrada.exists():
            raise FileNotFoundError(self.entrada)
        sha = sha256_archivo(self.entrada)
        destino = self._p("00_snapshot", "aceptadas.jsonl")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.entrada, destino)
        (destino.with_name("aceptadas.sha256")).write_text(sha + "\n",
                                                         encoding="utf-8")
        filas = sum(1 for _ in destino.open(encoding="utf-8"))
        return {"origen": str(self.entrada), "sha256": sha, "filas": filas}

    def etapa_eval(self) -> dict:
        """Genera (una vez, congelados) los casos de las 3 semillas reservadas
        y un fichero combinado con ids re-etiquetados por semilla."""
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        generados = []
        for semilla, ruta in zip(evaluacion_casos.SEMILLAS_RESERVADAS,
                                self.ficheros_eval()):
            if not ruta.exists():
                casos = evaluacion_casos.generar_casos(semilla)
                evaluacion_casos.escribir_casos(ruta, casos)
                generados.append(str(ruta.name))
        combinadas, sharegpt = [], []
        for semilla, ruta in zip(evaluacion_casos.SEMILLAS_RESERVADAS,
                                self.ficheros_eval()):
            for fila in merge_final.load_jsonl(ruta):
                fila = dict(fila)
                fila["id"] = f"{fila.get('id', 'eval')}-s{semilla}"
                fila["semilla_eval"] = semilla
                combinadas.append(fila)
                conv = []
                if nfc(fila.get("system")):
                    conv.append({"from": "system", "value": nfc(fila["system"])})
                conv.append({"from": "human", "value": nfc(fila.get("user"))})
                sharegpt.append({
                    "conversations": conv,
                    "id": fila["id"],
                    "origen": "evaluacion",
                    "familia": fila.get("familia"),
                })
        merge_final.write_jsonl(self.eval_combinada, combinadas)
        merge_final.write_jsonl(self.eval_sharegpt, sharegpt)
        return {"semillas": list(evaluacion_casos.SEMILLAS_RESERVADAS),
               "generados_ahora": generados, "total_combinado": len(combinadas)}

    def etapa_reverificar(self) -> dict:
        snapshot = self._p("00_snapshot", "aceptadas.jsonl")
        res = reverificar_fase1.reverificar(
            snapshot,
            self._p("01_reverificadas", "validas.jsonl"),
            rechazadas=self._p("01_reverificadas", "invalidas.jsonl"),
            eval_casos=self.eval_sharegpt,
        )
        return res

    def etapa_filtro(self) -> dict:
        validas = merge_final.load_jsonl(self._p("01_reverificadas",
                                               "validas.jsonl"))
        humanos_eval = merge_final.cargar_humanos_evaluacion([self.eval_sharegpt])
        humanos_eval.discard("")
        exactos: dict[str, set] = defaultdict(set)
        casi: dict[str, vs.IndiceCasiDuplicados] = defaultdict(
            vs.IndiceCasiDuplicados)
        mantenidas, descartes = [], []
        conteo = Counter()
        ejemplos: dict[str, list] = defaultdict(list)
        for fila in validas:
            if not isinstance(fila, dict):
                continue
            bloque = nfc(fila.get("bloque")) or "sin_bloque"
            humano = humano_completo(fila)
            respuesta = respuesta_completa(fila)
            clave = sha256_bytes((nfc(humano) + "\x00" + nfc(respuesta))
                                .encode("utf-8"))
            if evaluacion_casos.es_caso_de_evaluacion(fila):
                motivo = "fuga_evaluacion_id"
            elif merge_final._norm(humano) in humanos_eval:
                motivo = "fuga_evaluacion_contenido"
            elif clave in exactos[bloque]:
                motivo = "duplicado_exacto"
            elif casi[bloque].buscar(respuesta):
                motivo = "casi_duplicado"
            else:
                motivo = None
            if motivo:
                descartes.append({"id": fila.get("id"), "bloque": bloque,
                                 "motivo": motivo})
                if len(ejemplos[motivo]) < MAX_EJEMPLOS_MOTIVO:
                    ejemplos[motivo].append({
                        "id": fila.get("id"), "bloque": bloque,
                        "fragmento": nfc(humano)[:160],
                    })
            else:
                exactos[bloque].add(clave)
                casi[bloque].add(str(fila.get("id")), respuesta)
                mantenidas.append(fila)
        merge_final.write_jsonl(self._p("02_filtradas", "filtradas.jsonl"),
                               mantenidas)
        merge_final.write_jsonl(self._p("02_filtradas", "descartes.jsonl"),
                               descartes)
        (self._p("02_filtradas", "ejemplos_descarte.json")).write_text(
            json.dumps(ejemplos, ensure_ascii=False, indent=2),
            encoding="utf-8")
        conteo.update(m["motivo"] for m in descartes)
        return {"entrada": len(validas), "mantenidas": len(mantenidas),
               "descartes": dict(conteo)}

    def etapa_sharegpt(self) -> dict:
        filas = merge_final.load_jsonl(self._p("02_filtradas",
                                             "filtradas.jsonl"))
        adaptadas = [adaptar_sharegpt(f) for f in filas if isinstance(f, dict)]
        merge_final.write_jsonl(self._p("03_sharegpt", "sharegpt.jsonl"),
                               adaptadas)
        ya_era = sum(1 for f in filas
                    if isinstance(f, dict) and "conversations" in f)
        return {"total": len(adaptadas), "ya_sharegpt": ya_era,
               "convertidas_planas": len(adaptadas) - ya_era}

    def etapa_validar(self) -> dict:
        filas = merge_final.load_jsonl(self._p("03_sharegpt", "sharegpt.jsonl"))
        bloques_dir = self._p("04_validacion", "bloques")
        if bloques_dir.exists():
            shutil.rmtree(bloques_dir)
        bloques_dir.mkdir(parents=True, exist_ok=True)
        por_bloque: dict[str, list] = defaultdict(list)
        for fila in filas:
            bloque = nfc(fila.get("bloque")) or "sin_bloque"
            por_bloque[bloque].append(fila)
        for bloque, grupo in por_bloque.items():
            merge_final.write_jsonl(bloques_dir / f"{bloque}.jsonl", grupo)
        rc = vs.main([
            "--dir", str(bloques_dir),
            "--out", str(self._p("04_validacion", "synth_clean.jsonl")),
            "--meta-out", str(self._p("04_validacion",
                                     "synth_clean.meta.jsonl")),
            "--report", str(self._p("04_validacion", "synthetic_report.json")),
            "--min-chars", str(self.min_chars),
            "--max-chars", str(self.max_chars),
            "--max-repetition", str(self.max_repetition),
        ])
        if rc != 0:
            raise RuntimeError(f"validate_synthetic devolvio {rc}")
        informe = json.loads(self._p("04_validacion",
                                    "synthetic_report.json")
                            .read_text(encoding="utf-8"))
        return {"total": informe.get("total"), "kept": informe.get("kept"),
               "rejected": informe.get("rejected"),
               "near_duplicates": informe.get("near_duplicates"),
               "reasons": informe.get("reasons")}

    def etapa_fusion(self) -> dict:
        real_dir = self._p("real")
        real_dir.mkdir(parents=True, exist_ok=True)
        rc = bd.main([
            "--raw", str(self.real_raw),
            "--out", str(real_dir),
            "--seed", str(self.semilla),
            "--manifest", str(self.manifest),
            "--eval-casos", str(self.eval_sharegpt),
        ])
        if rc != 0:
            raise RuntimeError(f"build_dataset devolvio {rc}")
        rc = merge_final.main([
            "--real-train", str(real_dir / "train.jsonl"),
            "--real-val", str(real_dir / "val.jsonl"),
            "--synth", str(self._p("04_validacion", "synth_clean.jsonl")),
            "--synth-meta", str(self._p("04_validacion",
                                       "synth_clean.meta.jsonl")),
            "--out-dir", str(self.salida),
            "--seed", str(self.semilla),
            "--train-ratio", str(self.train_ratio),
            "--val-ratio", str(self.val_ratio),
            "--eval-casos", str(self.eval_sharegpt),
        ])
        if rc != 0:
            raise RuntimeError(f"merge_final devolvio {rc}")
        informe = json.loads((self.salida / "report.json")
                            .read_text(encoding="utf-8"))
        return informe

    def etapa_preparar(self) -> dict:
        resultado = pe.preparar(
            self.salida,
            self._p("preparado"),
            formato=self.formato,
            eval_casos=self.eval_combinada,
        )
        semaforo = resultado.get("semaforo")
        stats = {
            "semaforo": semaforo,
            "errores": resultado.get("errores", []),
            "avisos": resultado.get("avisos", []),
            "fugas": len(resultado.get("fugas", [])),
        }
        if semaforo == "rojo":
            raise RuntimeError(
                "semforo ROJO en preparar_entrenamiento: "
                + "; ".join(stats["errores"]))
        return stats

    # -- ejecución ---------------------------------------------------------
    def _definicion_etapas(self):
        snap = self._p("00_snapshot", "aceptadas.jsonl")
        return [
            ("snapshot", lambda: _huella(self.entrada), self.etapa_snapshot),
            # Huella solo por semillas: los ficheros que esta etapa crea no deben
            # alterar su propia huella (si no, nunca se reanudaria).
            ("eval", lambda: _huella(
                semillas=list(evaluacion_casos.SEMILLAS_RESERVADAS)),
             self.etapa_eval),
            ("reverificar",
             lambda: _huella(snap, self.eval_combinada),
             self.etapa_reverificar),
            ("filtro",
             lambda: _huella(self._p("01_reverificadas", "validas.jsonl"),
                            self.eval_combinada),
             self.etapa_filtro),
            ("sharegpt",
             lambda: _huella(self._p("02_filtradas", "filtradas.jsonl")),
             self.etapa_sharegpt),
            ("validar",
             lambda: _huella(self._p("03_sharegpt", "sharegpt.jsonl"),
                            min_chars=self.min_chars, max_chars=self.max_chars,
                            max_repetition=self.max_repetition),
             self.etapa_validar),
            ("fusion",
             lambda: _huella(self._p("04_validacion", "synth_clean.jsonl"),
                            self._p("04_validacion",
                                   "synth_clean.meta.jsonl"),
                            self.real_raw, self.manifest,
                            semilla=self.semilla,
                            train_ratio=self.train_ratio,
                            val_ratio=self.val_ratio),
             self.etapa_fusion),
            ("preparar",
             lambda: _huella(self.salida / "train.jsonl",
                            self.salida / "val.jsonl",
                            self.salida / "test.jsonl",
                            formato=self.formato),
             self.etapa_preparar),
        ]

    def ejecutar(self) -> int:
        self.salida.mkdir(parents=True, exist_ok=True)
        self.etapas_dir.mkdir(parents=True, exist_ok=True)
        for nombre, huella_fn, fn in self._definicion_etapas():
            huella = huella_fn()
            if self.registro.esta_completada(nombre, huella):
                print(f"[tuberia] {nombre}: omitida (completada, misma huella)")
                continue
            print(f"[tuberia] {nombre}: ejecutando...")
            try:
                stats = fn()
            except Exception as exc:  # noqa: BLE001 - parada controlada
                self.registro.registrar(nombre, "fallida", huella,
                                       {"error": f"{type(exc).__name__}: {exc}"})
                print(f"[tuberia] {nombre}: FALLIDA -> {exc}", file=sys.stderr)
                return 1
            self.registro.registrar(nombre, "completada", huella, stats)
            self._guardar_stats(nombre, stats)
            print(f"[tuberia] {nombre}: completada")
        self.generar_informe()
        return 0

    # -- informe -----------------------------------------------------------
    def _conteos_finales(self):
        por_split = {}
        for split in ("train", "val", "test"):
            ruta = self.salida / f"{split}.jsonl"
            filas = merge_final.load_jsonl(ruta) if ruta.exists() else []
            chars = sum(len(humano_completo(f)) + len(respuesta_completa(f))
                       for f in filas if isinstance(f, dict))
            por_split[split] = {
                "filas": len(filas),
                "chars": chars,
                "tokens_est": chars // 4,
                "bloques": dict(Counter(
                    (nfc(f.get("bloque")) or "sin_bloque")
                    for f in filas if isinstance(f, dict))),
                "generadores": dict(Counter(
                    (nfc(f.get("generador")) or "real-corpus")
                    for f in filas if isinstance(f, dict))),
                "multiturno": sum(1 for f in filas if isinstance(f, dict)
                                 and turnos_gpt(f) > 1),
            }
        return por_split

    def _distribucion_cartas(self) -> dict:
        """Menciones de cartas en los prompts del dataset final (train+val+test)."""
        menciones: Counter = Counter()
        orientaciones: Counter = Counter()
        for split in ("train", "val", "test"):
            ruta = self.salida / f"{split}.jsonl"
            if not ruta.exists():
                continue
            for fila in merge_final.load_jsonl(ruta):
                if not isinstance(fila, dict):
                    continue
                for nombre, orient in vs.extraer_cartas(prompt_de(fila)):
                    menciones[nombre] += 1
                    orientaciones[orient] += 1
        try:
            kb_tarot = json.loads((CORPUS_DIR / "kb" / "tarot.json")
                                  .read_text(encoding="utf-8"))
            universo_tarot = evaluacion_casos._universo_tarot(kb_tarot)
        except Exception:  # noqa: BLE001
            universo_tarot = []
        universo_es = evaluacion_casos._nombre_naipes()
        tarot_menc = {c: menciones.get(c, 0) for c in universo_tarot}
        es_menc = {c: menciones.get(c, 0) for c in universo_es}
        return {
            "tarot": {
                "universo": len(universo_tarot),
                "distintas": sum(1 for v in tarot_menc.values() if v),
                "menciones": sum(tarot_menc.values()),
                "min": min(tarot_menc.values(), default=0),
                "max": max(tarot_menc.values(), default=0),
            },
            "espanola": {
                "universo": len(universo_es),
                "distintas": sum(1 for v in es_menc.values() if v),
                "menciones": sum(es_menc.values()),
                "min": min(es_menc.values(), default=0),
                "max": max(es_menc.values(), default=0),
            },
            "orientaciones": dict(orientaciones),
            "sin_clasificar": sum(
                v for c, v in menciones.items()
                if c not in tarot_menc and c not in es_menc),
        }

    def generar_informe(self) -> Path:
        st = {e: self._leer_stats(e) for e in
              ("snapshot", "eval", "reverificar", "filtro", "sharegpt",
               "validar", "fusion", "preparar")}
        splits = self._conteos_finales()
        cartas = self._distribucion_cartas()
        fusion = st.get("fusion", {})
        filtro = st.get("filtro", {})
        validar = st.get("validar", {})
        preparar = st.get("preparar", {})
        ejemplos_path = self._p("02_filtradas", "ejemplos_descarte.json")
        ejemplos = (json.loads(ejemplos_path.read_text(encoding="utf-8"))
                   if ejemplos_path.exists() else {})

        lineas = []
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lineas.append("# dataset_fase1_v1 — informe de armado (T103)")
        lineas.append(f"\nGenerado: {ahora}\n")
        lineas.append(f"- Entrada: `{st.get('snapshot', {}).get('origen', '—')}`"
                     f" (sha256 {st.get('snapshot', {}).get('sha256', '—')[:16]}…,"
                     f" {st.get('snapshot', {}).get('filas', '—')} filas)")
        lineas.append(f"- Semilla: {self.semilla} · semáforo: "
                     f"**{preparar.get('semaforo', '—')}**\n")

        lineas.append("## Filas por split, familia (bloque) y generador\n")
        for split, d in splits.items():
            lineas.append(f"### {split}: {d['filas']} filas · "
                         f"{d['chars']} chars · ~{d['tokens_est']} tokens · "
                         f"multiturno {d['multiturno']}\n")
            lineas.append("| bloque | filas |")
            lineas.append("|---|---|")
            for b, n in sorted(d["bloques"].items(),
                               key=lambda kv: (-kv[1], kv[0])):
                lineas.append(f"| {b} | {n} |")
            lineas.append("\n| generador | filas |")
            lineas.append("|---|---|")
            for g, n in sorted(d["generadores"].items(),
                               key=lambda kv: (-kv[1], kv[0])):
                lineas.append(f"| {g} | {n} |")
            lineas.append("")

        lineas.append("## Distribución de cartas (prompts del dataset final)\n")
        for sistema, d in (("tarot (78)", cartas["tarot"]),
                          ("baraja española (40)", cartas["espanola"])):
            cobertura = (f"{d['distintas']}/{d['universo']}"
                        if d["universo"] else "—")
            lineas.append(f"- {sistema}: {cobertura} distintas · "
                         f"{d['menciones']} menciones · "
                         f"min {d['min']} / max {d['max']} por carta")
        lineas.append(f"- Orientaciones: {cartas['orientaciones']}")
        if cartas["sin_clasificar"]:
            lineas.append(f"- Menciones sin clasificar: {cartas['sin_clasificar']}")
        lineas.append("")

        lineas.append("## Casos éticos y fuera de alcance (dataset final)\n")
        eticas = sum(d["bloques"].get("etica", 0) for d in splits.values())
        alcance = sum(d["bloques"].get("fuera_alcance", 0)
                     for d in splits.values())
        lineas.append(f"- etica: {eticas} · fuera_alcance: {alcance}\n")

        lineas.append("## Duplicados y descartes por etapa\n")
        lineas.append(f"- filtro (familia): {filtro.get('descartes', {})}")
        lineas.append(f"- validate_synthetic: near_duplicates="
                     f"{validar.get('near_duplicates', 0)} · rejected="
                     f"{validar.get('rejected', 0)} · reasons="
                     f"{validar.get('reasons', {})}")
        d = fusion.get("descartes", {})
        lineas.append(f"- merge_final: junk={d.get('junk', 0)} · "
                     f"duplicado_exacto={d.get('duplicado_exacto', 0)} · "
                     f"duplicado_prefijo={d.get('duplicado_prefijo', 0)} · "
                     f"idioma={d.get('idioma', 0)} · "
                     f"evaluacion={d.get('evaluacion', 0)}")
        rev = st.get("reverificar", {})
        lineas.append(f"- reverificar: invalidas={rev.get('invalidas', 0)} · "
                     f"motivos={rev.get('motivos', {})}")
        lineas.append("")
        if ejemplos:
            lineas.append("### Ejemplos de descarte (hasta 10 por motivo)\n")
            for motivo, lista in sorted(ejemplos.items()):
                lineas.append(f"**{motivo}**")
                for e in lista:
                    lineas.append(f"- `{e.get('id')}` ({e.get('bloque')}): "
                                 f"{e.get('fragmento')}")
                lineas.append("")

        lineas.append("## Proporción final por familia vs objetivo "
                     "(generate_tasks.TARGETS)\n")
        total_final = {b: sum(s["bloques"].get(b, 0) for s in splits.values())
                      for b in TARGETS}
        lineas.append("| familia | objetivo | final | proporción |")
        lineas.append("|---|---|---|---|")
        for familia, objetivo in TARGETS.items():
            final = total_final.get(familia, 0)
            prop = f"{final / objetivo:.0%}" if objetivo else "—"
            lineas.append(f"| {familia} | {objetivo} | {final} | {prop} |")
        bloques_extra = sorted(
            {b for s in splits.values() for b in s["bloques"]}
            - set(TARGETS))
        for b in bloques_extra:
            final = sum(s["bloques"].get(b, 0) for s in splits.values())
            lineas.append(f"| {b} (fuera de TARGETS) | — | {final} | — |")
        lineas.append("")

        if preparar.get("avisos"):
            lineas.append("## Avisos de preparar_entrenamiento\n")
            for a in preparar["avisos"]:
                lineas.append(f"- {a}")
            lineas.append("")

        informe = self.salida / "informe.md"
        informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        return informe


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Arma dataset_fase1_v1 desde las lecturas de Mercury (T103).")
    ap.add_argument("--entrada", default=ENTRADA_POR_DEFECTO,
                    help="aceptadas.jsonl de la generación Mercury")
    ap.add_argument("--salida", default=SALIDA_POR_DEFECTO,
                    help="directorio de salida (dataset_fase1_v1)")
    ap.add_argument("--real-raw", default=RAW_REAL_POR_DEFECTO,
                    help="corpus real de fase 0 (solo lectura)")
    ap.add_argument("--manifest", default=MANIFEST_POR_DEFECTO)
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--min-chars", type=int, default=400)
    ap.add_argument("--max-chars", type=int, default=12000)
    ap.add_argument("--max-repetition", type=float, default=0.12)
    ap.add_argument("--train-ratio", type=float, default=0.8)
    ap.add_argument("--val-ratio", type=float, default=0.1)
    args = ap.parse_args(argv)
    tub = Tuberia(
        entrada=args.entrada, salida_dir=args.salida, semilla=args.semilla,
        real_raw=args.real_raw, manifest=args.manifest,
        min_chars=args.min_chars, max_chars=args.max_chars,
        max_repetition=args.max_repetition,
        train_ratio=args.train_ratio, val_ratio=args.val_ratio,
    )
    return tub.ejecutar()


if __name__ == "__main__":
    sys.exit(main())
