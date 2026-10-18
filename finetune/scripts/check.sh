#!/bin/bash
# Verificación del proyecto: compila y ejecuta todos los tests (unittest, sin red ni datos pesados).
# Uso: desde cualquier worktree:  ./finetune/scripts/check.sh   (o ./scripts/check.sh dentro de finetune/)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
$PY -m compileall -q corpus scraper/scraper
echo "== tests corpus"
$PY -m unittest discover -s corpus/tests -t corpus -p 'test_*.py'
echo "== tests scraper"
(cd scraper && $PY -m unittest discover -s tests -t . -p 'test_*.py')
echo "CHECK OK"
