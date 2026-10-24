#!/bin/bash
# Vigilante de pistas. Uso: vigia.sh <salida.out> <pista1> [<pista2> ...]
# Sale escribiendo "COMPLETO <pista>" cuando: el ESTADO.md del worktree lleva el número de pista (tNNN) en
# las 3 primeras líneas, tiene una línea que empieza por "TRACK COMPLETO" y hay commits en main..track/<pista>.
# Lanzar con nohup en segundo plano. NO usar `pkill -f vigia` desde un comando que contenga esa palabra en su línea.
OUT=$1; shift
cd /Users/angelgonzalez/adivinacion-ia
while true; do
  for w in "$@"; do
    n=${w%%-*}
    if head -3 .worktrees/$w/ESTADO.md 2>/dev/null | grep -qi "$n" && grep -qE "^(\*\*)?TRACK COMPLETO" .worktrees/$w/ESTADO.md && [ -n "$(git log main..track/$w --oneline)" ]; then echo "COMPLETO $w" > "$OUT"; exit 0; fi
  done
  sleep 60
done
