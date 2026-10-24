#!/bin/bash
# Resumen rápido: pistas abiertas (worktrees), commits sin integrar, TRACK COMPLETO, nodos y procesos.
cd /Users/angelgonzalez/adivinacion-ia
echo "== $(date +%H:%M)"
for d in .worktrees/*/; do
  w=$(basename $d)
  echo "$w commits=$(git log main..track/$w --oneline --no-merges 2>/dev/null | wc -l | tr -d ' ') completo=$(grep -c '^TRACK COMPLETO' $d/ESTADO.md 2>/dev/null) sucio=$(cd $d && git status --short | wc -l | tr -d ' ')"
done
for n in 3 4; do curl -s -m 5 http://10.0.0.$n:8000/v1/models >/dev/null && echo -n "nodo$((n-2)) ok " || echo -n "nodo$((n-2)) CAIDO "; done; echo
curl -s -m 5 http://10.0.0.1:8000/v1/models >/dev/null && echo "mini:8000 ok" || echo "mini:8000 CAIDO"
