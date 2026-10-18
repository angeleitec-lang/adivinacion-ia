#!/bin/bash
# Espera a que terminen los procesos indicados (PIDs como argumentos) y regenera:
# build_scrapy_dataset -> traduccion de pares Scrapy -> merge final.
set -uo pipefail

ROOT="/Users/angelgonzalez/adivinacion-ia/finetune"
LOG="/tmp/final_rebuild.log"

cd "$ROOT"
echo "== inicio espera $(date -u) (PIDs: $*) ==" >> "$LOG"

for pid in "$@"; do
  while kill -0 "$pid" 2>/dev/null; do sleep 60; done
  echo "-- PID $pid terminado $(date -u) --" >> "$LOG"
done

echo "== construyendo pares Scrapy $(date -u) ==" >> "$LOG"
.venv/bin/python corpus/build_scrapy_dataset.py >> "$LOG" 2>&1

echo "== traduciendo pares Scrapy $(date -u) ==" >> "$LOG"
.venv/bin/python corpus/translate_dataset.py \
  --train corpus/train_scrapy.jsonl \
  --val corpus/val_scrapy.jsonl \
  --out-train corpus/train_scrapy_es.jsonl \
  --out-val corpus/val_scrapy_es.jsonl \
  --resume --workers 8 --timeout 600 \
  --min-en-chars 1200 --drop-short-en \
  --endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next" \
  --endpoint "http://10.0.0.1:8000/v1=/Users/angelgonzalez/models/Qwen3-VL-30B-A3B-Instruct-4bit" \
  >> "$LOG" 2>&1

echo "== fusionando datasets $(date -u) ==" >> "$LOG"
.venv/bin/python corpus/merge_datasets.py \
  --new corpus/train_scrapy_es.jsonl \
  --val-new corpus/val_scrapy_es.jsonl \
  >> "$LOG" 2>&1

echo "== DONE $(date -u) ==" >> "$LOG"
