#!/bin/bash
# copia de seguridad de los datos de fase 0 cada 3 h (salud_datos.py --copia)
cd /Users/angelgonzalez/adivinacion-ia/finetune/corpus
while true; do
  sleep 10800
  /Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python salud_datos.py --copia >> /Users/angelgonzalez/fase0/copias.log 2>&1
done
