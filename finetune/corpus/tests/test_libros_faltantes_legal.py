# Tests del esquema de libros_faltantes_legal.jsonl (T39: solo fuentes legales).
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import unittest
from urllib.parse import urlparse

KNOWLEDGE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
)
JSONL_PATH = os.path.join(KNOWLEDGE_DIR, "libros_faltantes_legal.jsonl")
MD_PATH = os.path.join(KNOWLEDGE_DIR, "libros_faltantes_legal.md")

CAMPOS_OBLIGATORIOS = {
    "id", "titulo", "autor", "anio", "estado_legal",
    "urls_legales", "precio_papel", "precio_ebook", "nota",
}

ESTADOS_PERMITIDOS = {
    "dominio_publico",
    "copyright_vigente_compra",
    "copyright_vigente_prestamo_biblioteca",
    "no_localizado",
}

# Dominios de piratería: prohibidos incluso como referencia de investigación.
LISTA_NEGRA_PIRATERIA = (
    "libgen",
    "library.lol",
    "z-lib",
    "zlibrary",
    "b-ok",
    "1lib",
    "epubdrive",
    "pdfdrive",
    "annasarchive",
    "annas-archive",
    "annas archive",
    "descargargratis",
    "descargalibros",
    "getmybook",
    "cambrook",
)


def cargar_filas(ruta=JSONL_PATH):
    filas = []
    with open(ruta, "r", encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                filas.append(json.loads(linea))
    return filas


def validar_fila(fila):
    """Devuelve la lista de errores de esquema de una fila ([] si es válida)."""
    errores = []
    faltan = CAMPOS_OBLIGATORIOS - set(fila)
    if faltan:
        errores.append("campos obligatorios faltantes: %s" % sorted(faltan))
    if not isinstance(fila.get("id"), str) or not fila.get("id"):
        errores.append("id debe ser un string no vacío")
    if not isinstance(fila.get("titulo"), str) or not fila.get("titulo"):
        errores.append("titulo debe ser un string no vacío")
    if not isinstance(fila.get("autor"), str) or not fila.get("autor"):
        errores.append("autor debe ser un string no vacío")
    anio = fila.get("anio")
    if not (anio is None or (isinstance(anio, int) and not isinstance(anio, bool))):
        errores.append("anio debe ser entero o null")
    if fila.get("estado_legal") not in ESTADOS_PERMITIDOS:
        errores.append("estado_legal no permitido: %r" % (fila.get("estado_legal"),))
    urls = fila.get("urls_legales")
    if not isinstance(urls, list):
        errores.append("urls_legales debe ser una lista")
    else:
        for u in urls:
            if not isinstance(u, str) or not u.startswith("https://"):
                errores.append("url no https: %r" % (u,))
                continue
            host = (urlparse(u).hostname or "").lower()
            for malo in LISTA_NEGRA_PIRATERIA:
                if malo in host:
                    errores.append("dominio en lista negra de piratería: %s" % u)
    for campo in ("precio_papel", "precio_ebook"):
        v = fila.get(campo)
        if v is not None and (
            not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0
        ):
            errores.append("%s debe ser null o un número >= 0" % campo)
    if not isinstance(fila.get("nota"), str) or not fila.get("nota").strip():
        errores.append("nota debe ser un string no vacío")
    return errores


class TestLibrosFaltantesLegal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(JSONL_PATH):
            raise unittest.SkipTest("falta %s" % JSONL_PATH)
        cls.filas = cargar_filas()

    def test_archivo_no_vacio(self):
        self.assertGreaterEqual(len(self.filas), 14)

    def test_esquema_todas_las_filas(self):
        for fila in self.filas:
            with self.subTest(id=fila.get("id")):
                self.assertEqual(validar_fila(fila), [])

    def test_ids_unicos(self):
        ids = [f["id"] for f in self.filas]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ids_de_los_libros_clave(self):
        ids = {f["id"] for f in self.filas}
        esperados = {
            "simbolismo-tarot-ouspensky",
            "arte-echar-cartas-baraja-espanola",
            "arte-echar-cartas-2-salas",
            "curso-cartomancia-rossi",
            "tarot-cartas-espanolas-beltrame",
            "romance-in-your-name-jordan",
            "your-days-are-numbered-campbell",
            "tarot-for-your-self-greer",
            "gran-libro-tarot-banzhaf",
        }
        faltan = esperados - ids
        self.assertEqual(faltan, set())

    def test_md_existe_con_recomendacion(self):
        self.assertTrue(os.path.exists(MD_PATH))
        with open(MD_PATH, "r", encoding="utf-8") as fh:
            contenido = fh.read()
        self.assertIn("Recomendación", contenido)
        self.assertIn("cobertura", contenido.lower())
        self.assertIn("|", contenido)


class TestValidadorContraejemplos(unittest.TestCase):
    def _fila_valida(self):
        return {
            "id": "ejemplo-ok",
            "titulo": "Libro Ejemplo",
            "autor": "Autora Ejemplo",
            "anio": 1990,
            "estado_legal": "copyright_vigente_compra",
            "urls_legales": [
                "https://openlibrary.org/search?q=libro",
                "https://archive.org/details/ejemplo1990",
            ],
            "precio_papel": None,
            "precio_ebook": None,
            "nota": "Nota válida.",
        }

    def test_fila_valida_pasa(self):
        self.assertEqual(validar_fila(self._fila_valida()), [])

    def test_faltan_campos(self):
        fila = self._fila_valida()
        del fila["estado_legal"]
        self.assertTrue(validar_fila(fila))

    def test_url_http_no_permitida(self):
        fila = self._fila_valida()
        fila["urls_legales"] = ["http://archive.org/details/x"]
        self.assertTrue(any("https" in e for e in validar_fila(fila)))

    def test_lista_negra_pirateria(self):
        for dominio in (
            "https://libgen.is/book/x",
            "https://z-library.se/book/x",
            "https://b-ok.cc/book/x",
            "https://www.annas-archive.org/search?q=x",
            "https://epubdrive.cat/book/x",
        ):
            with self.subTest(url=dominio):
                fila = self._fila_valida()
                fila["urls_legales"] = [dominio]
                errores = validar_fila(fila)
                self.assertTrue(
                    any("lista negra" in e for e in errores),
                    "no se detectó piratería en %s: %s" % (dominio, errores),
                )

    def test_estado_legal_inventado_falla(self):
        fila = self._fila_valida()
        fila["estado_legal"] = "gratis_internet"
        self.assertTrue(validar_fila(fila))

    def test_precio_negativo_falla(self):
        fila = self._fila_valida()
        fila["precio_ebook"] = -5
        self.assertTrue(validar_fila(fila))


if __name__ == "__main__":
    unittest.main()
