#!/bin/bash
# uso: ia_send.sh <y_pestaña> "<texto>" [--nuevo]   (pega y envía; con --nuevo escribe /new antes)
Y=$1; TXT=$2; NUEVO=$3
peekaboo click --app Warp --at 140,$Y --foreground >/dev/null 2>&1; sleep 3.5
T=$(peekaboo see --app Warp --no-elements --path /tmp/ia_send_pre.png 2>&1 | grep 📸 | sed 's/📸 //; s/ → .*//')
echo "pestaña activa: $T"
case "$T" in *Claude.md*|*ia-servidores*) echo "ABORTO: foco incorrecto"; exit 1;; esac
if [ "$NUEVO" = "--nuevo" ]; then
  peekaboo paste "/new" --foreground >/dev/null 2>&1; sleep 1; peekaboo press return --foreground >/dev/null 2>&1; sleep 4
fi
peekaboo paste "$TXT" --foreground >/dev/null 2>&1; sleep 3.5
peekaboo press return --foreground >/dev/null 2>&1; sleep 3
echo enviado
