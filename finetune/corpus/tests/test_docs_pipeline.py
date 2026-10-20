# Tests de docs/PIPELINE.md: los módulos y las opciones citados existen.
import os
import re
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DOC = os.path.join(RAIZ, "docs", "PIPELINE.md")
CORPUS = os.path.join(RAIZ, "finetune", "corpus")

# Nombres citados en la sección de discrepancias porque NO existen en el árbol.
INEXISTENTES = {"afirmaciones_libros.py", "consenso_kb.py", "evidencias_incremental.py"}

SECCIONES = (
    "## 1. Flujo completo",
    "## 2. Módulos",
    "## 3. Formatos JSONL reales",
    "## 4. Rutas y volumen",
    "## 5. Recetas",
    "## 6. Precauciones y trampas",
    "## 7. Verificación y discrepancias",
)


def _leer():
    with open(DOC, encoding="utf-8") as fh:
        return fh.read()


def _comandos(texto):
    """Une continuaciones de línea y devuelve los comandos con un .py citado."""
    lineas = texto.splitlines()
    unidas = []
    buffer = ""
    for linea in lineas:
        limpia = linea.strip()
        if buffer:
            buffer += " " + limpia
        else:
            buffer = limpia
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        unidas.append(buffer)
        buffer = ""
    if buffer:
        unidas.append(buffer)
    return [l for l in unidas if "finetune/corpus/" in l and ".py" in l]


class DocsPipeline(unittest.TestCase):
    def setUp(self):
        self.texto = _leer()

    def test_secciones_obligatorias(self):
        for seccion in SECCIONES:
            self.assertIn(seccion, self.texto)

    def test_modulos_citados_existen(self):
        nombres = set(re.findall(r"`([a-z_0-9]+\.py)`", self.texto)) - INEXISTENTES
        self.assertTrue(nombres)
        for nombre in sorted(nombres):
            ruta = os.path.join(CORPUS, nombre)
            self.assertTrue(os.path.isfile(ruta), "falta el módulo %s" % nombre)

    def test_opciones_citadas_existen_en_su_modulo(self):
        for comando in _comandos(self.texto):
            modulos = re.findall(r"finetune/corpus/([a-z_0-9]+\.py)", comando)
            if not modulos:
                continue
            fuente = ""
            for modulo in modulos:
                with open(os.path.join(CORPUS, modulo), encoding="utf-8") as fh:
                    fuente += fh.read()
            for opcion in re.findall(r"(--[a-z][a-z0-9-]+)", comando):
                self.assertIn(
                    opcion,
                    fuente,
                    "la opción %s no aparece en %s" % (opcion, ", ".join(modulos)),
                )


if __name__ == "__main__":
    unittest.main()
