#!/bin/bash
# Espera a que terminen los procesos indicados (PIDs como argumentos) y regenera:
# build_scrapy_dataset -> traduccion de pares Scrapy -> merge final.
# Aborta inmediatamente si algun paso falla (no sigue con datos viejos).
set -uo pipefail

ROOT="${ROOT:-/Users/angelgonzalez/adivinacion-ia/finetune}"
LOG="${LOG:-/tmp/final_rebuild.log}"
ENDPOINT1="${ENDPOINT1:-http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next}"
ENDPOINT2="${ENDPOINT2:-http://10.0.0.1:8000/v1=/Users/angelgonzalez/models/Qwen3-VL-30B-A3B-Instruct-4bit}"

paso() {
  # Ejecuta un paso redirigiendo al log y aborta el script si devuelve rc != 0.
  nombre="$1"
  shift
  "$@" >> "$LOG" 2>&1
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "!! FALLO en ${nombre} (rc=${rc}) $(date -u)" >> "$LOG"
    exit 1
  fi
}

cd "$ROOT" || { echo "!! FALLO al entrar en $ROOT" >> "$LOG"; exit 1; }
echo "== inicio espera $(date -u) (PIDs: $*) ==" >> "$LOG"

for pid in "$@"; do
  while kill -0 "$pid" 2>/dev/null; do sleep 60; done
  echo "-- PID $pid terminado $(date -u) --" >> "$LOG"
done

echo "== construyendo pares Scrapy $(date -u) ==" >> "$LOG"
paso build_scrapy_dataset .venv/bin/python corpus/build_scrapy_dataset.py

echo "== traduciendo pares Scrapy $(date -u) ==" >> "$LOG"
paso traduccion .venv/bin/python corpus/translate_dataset.py \
  --train corpus/train_scrapy.jsonl \
  --val corpus/val_scrapy.jsonl \
  --out-train corpus/train_scrapy_es.jsonl \
  --out-val corpus/val_scrapy_es.jsonl \
  --resume --workers 8 --timeout 600 \
  --min-en-chars 1200 --drop-short-en \
  --endpoint "$ENDPOINT1" \
  --endpoint "$ENDPOINT2"

echo "== fusionando datasets $(date -u) ==" >> "$LOG"
paso merge .venv/bin/python corpus/merge_datasets.py \
  --new corpus/train_scrapy_es.jsonl \
  --val-new corpus/val_scrapy_es.jsonl

echo "== DONE $(date -u) ==" >> "$LOG"
