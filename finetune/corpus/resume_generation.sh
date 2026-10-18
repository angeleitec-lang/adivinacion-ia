#!/bin/bash
# Reactiva la generación sintética por fases:
#  - nodo1 cuando termina la traducción principal (44914)
#  - nodo2 cuando termina la cadena de rebuild (44915)
set -uo pipefail

LOG="/tmp/gen_resume.log"
echo "== esperando traduccion principal 44914 $(date -u) ==" >> "$LOG"
while kill -0 44914 2>/dev/null; do sleep 30; done
if kill -CONT 66101 2>/dev/null; then
  echo "-- nodo1 generando al 100% $(date -u) --" >> "$LOG"
fi

echo "== esperando cadena rebuild 44915 $(date -u) ==" >> "$LOG"
while kill -0 44915 2>/dev/null; do sleep 60; done
if kill -CONT 66396 2>/dev/null; then
  echo "-- nodo2 generando al 100% $(date -u) --" >> "$LOG"
fi
echo "== generacion reactivada $(date -u) ==" >> "$LOG"
