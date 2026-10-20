#!/bin/bash
# Comprobación de entorno para la fase 2. Solo lee: no instala ni modifica nada.
# Uso: ./finetune/entrenamiento/comprobar_entorno.sh
set -u

PY="${PY:-/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python}"

echo "== Fecha"
date -u +"%Y-%m-%dT%H:%M:%SZ"

echo "== Python del proyecto"
if [ -x "$PY" ]; then
  "$PY" --version
  "$PY" - <<'PY'
import platform
import sys
print("ejecutable:", sys.executable)
print("plataforma:", platform.platform())
for modulo in ("torch", "transformers", "peft", "bitsandbytes", "soup"):
    try:
        m = __import__(modulo)
        print(f"{modulo}: {getattr(m, '__version__', 'instalado sin __version__')}")
    except Exception as exc:
        print(f"{modulo}: NO disponible ({type(exc).__name__}: {exc})")
try:
    import torch
    print("torch.version.hip:", getattr(torch.version, "hip", None))
    print("torch.version.cuda:", getattr(torch.version, "cuda", None))
    print("torch.cuda.is_available():", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU 0:", torch.cuda.get_device_name(0))
        props = torch.cuda.get_device_properties(0)
        print("memoria GPU 0 (GiB):", round(props.total_memory / 1024 ** 3, 1))
except Exception as exc:
    print("torch no permite consultar la GPU:", type(exc).__name__, exc)
PY
else
  echo "NO existe el Python esperado: $PY"
fi

echo "== Soup"
if command -v soup >/dev/null 2>&1; then
  soup --version 2>&1 || true
  echo "ruta: $(command -v soup)"
else
  echo "soup: NO instalado en PATH"
fi

echo "== uv"
if command -v uv >/dev/null 2>&1; then
  uv --version
else
  echo "uv: NO instalado en PATH"
fi

echo "== ROCm"
if command -v rocminfo >/dev/null 2>&1; then
  rocminfo 2>/dev/null | grep -m1 -E "ROCm version|Version:" || true
else
  echo "rocminfo: NO disponible"
fi
if command -v rocm-smi >/dev/null 2>&1; then
  rocm-smi --showproductname 2>/dev/null || true
else
  echo "rocm-smi: NO disponible"
fi

echo "== NVIDIA"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo "nvidia-smi: NO disponible"
fi

echo "== Espacio libre en disco"
df -h /Users/angelgonzalez/adivinacion-ia 2>/dev/null || df -h .

echo "== Modelos locales en caché (solo nombres)"
for raiz in "$HOME/.cache/huggingface/hub" "$HOME/.cache/lm-studio/models"; do
  if [ -d "$raiz" ]; then
    echo "$raiz:"
    find "$raiz" -maxdepth 1 -mindepth 1 -type d -print 2>/dev/null | head -20
  else
    echo "$raiz: no existe"
  fi
done
