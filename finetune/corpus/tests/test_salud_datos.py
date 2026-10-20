# Tests de salud_datos: analisis, reparacion, copias y rotacion (sin red).
import hashlib
import json
import os
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import salud_datos as salud


def escribir(ruta, contenido):
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(contenido)


def linea(**datos):
    return json.dumps(datos, ensure_ascii=False)


EVIDENCIA = {
    "entidad_id": "tarot-copas-02",
    "faceta": "significado_general",
    "fuente_id": "https://ejemplo.org/a",
    "dominio": "ejemplo.org",
    "idioma": "es",
    "periodo": "moderna",
    "calidad": 4,
    "tipo": "web",
    "hash_seccion": "abc",
}


class Analisis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def ruta(self, nombre="evidencias.jsonl"):
        return os.path.join(self.tmp.name, "evidencias_web", nombre)

    def test_jsonl_sano(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n" +
                 linea(**dict(EVIDENCIA, entidad_id="tarot-copas-03")) + "\n")
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["lineas"], 2)
        self.assertEqual(res["nivel"], "OK")
        self.assertEqual(res["problemas"], [])
        self.assertFalse(res["ultima_truncada"])

    def test_ultima_linea_truncada(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n" + '{"entidad_id": "tarot-co')
        res = salud.analizar_fichero(ruta)
        self.assertTrue(res["ultima_truncada"])
        self.assertEqual(res["nivel"], "grave")
        self.assertEqual(res["invalidas"][0][0], 2)
        self.assertIn("truncada", res["invalidas"][0][1].lower())

    def test_linea_no_objeto(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n" + '["no", "es", "objeto"]\n')
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["nivel"], "grave")
        self.assertEqual(res["invalidas"][0][0], 2)
        self.assertIn("objeto", res["invalidas"][0][1].lower())

    def test_campos_obligatorios_ausentes(self):
        ruta = self.ruta()
        fila = dict(EVIDENCIA)
        del fila["calidad"]
        escribir(ruta, linea(**fila) + "\n")
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["campos_ausentes"], [(1, "calidad")])
        self.assertEqual(res["nivel"], "grave")

    def test_duplicados_exactos_y_por_clave(self):
        ruta = self.ruta()
        fila = linea(**EVIDENCIA)
        otra = linea(**dict(EVIDENCIA, calidad=1, fuente_id="https://ejemplo.org/b"))
        escribir(ruta, fila + "\n" + fila + "\n" + otra + "\n")
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["duplicados_exactos"], [(2, 1)])
        self.assertEqual(len(res["duplicados_clave"]), 2)
        self.assertEqual(res["duplicados_clave"][0][1], 2)
        self.assertEqual(res["duplicados_clave"][1][1], 3)
        self.assertEqual(res["nivel"], "avisar")

    def test_fichero_vacio(self):
        ruta = self.ruta()
        escribir(ruta, "")
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["lineas"], 0)
        self.assertEqual(res["nivel"], "avisar")
        self.assertTrue(any("vac" in p["texto"].lower() for p in res["problemas"]))

    def test_distribuciones(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n" +
                 linea(**dict(EVIDENCIA, entidad_id="otra", calidad=5)) + "\n")
        res = salud.analizar_fichero(ruta)
        self.assertEqual(res["distribuciones"]["calidad"], {"4": 1, "5": 1})
        self.assertEqual(res["distribuciones"]["periodo"], {"moderna": 2})

    def test_detecta_crecimiento_con_hilo(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n")
        parar = threading.Event()

        def escribir_mas():
            with open(ruta, "a", encoding="utf-8") as fh:
                while not parar.is_set():
                    fh.write(linea(**dict(EVIDENCIA, calidad=3)) + "\n")
                    fh.flush()
                    time.sleep(0.05)

        hilo = threading.Thread(target=escribir_mas, daemon=True)
        hilo.start()
        self.addCleanup(parar.set)
        crece = salud.detectar_crecimiento([ruta], intervalo=0.4,
                                           comprobar_lsof=False)
        self.assertTrue(crece[ruta])

    def test_informe_menciona_la_linea(self):
        ruta = self.ruta()
        escribir(ruta, linea(**EVIDENCIA) + "\n" + '{"roto":\n')
        res = salud.analizar_fichero(ruta)
        salida = os.path.join(self.tmp.name, "salud_datos.md")
        salud.generar_informe([res], salida, base=self.tmp.name, vigilar=False)
        with open(salida, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertIn("GRAVE", texto.upper())
        self.assertIn("línea 2", texto)


class Reparacion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = os.path.join(self.tmp.name, "evidencias_web",
                                 "evidencias.jsonl")
        self.buena = linea(**EVIDENCIA)
        escribir(self.ruta, self.buena + "\n" + '{"entidad_id": "roto')

    def test_sin_si_no_hace_nada(self):
        acciones = salud.reparar_ficheros([self.ruta], si=False, intervalo=0)
        self.assertEqual(acciones[0]["estado"], "omitido_sin_si")
        with open(self.ruta, encoding="utf-8") as fh:
            self.assertTrue(fh.read().endswith("roto"))

    def test_repara_con_copia_y_fichero_truncada(self):
        acciones = salud.reparar_ficheros([self.ruta], si=True, intervalo=0)
        self.assertEqual(acciones[0]["estado"], "reparado")
        with open(self.ruta, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), self.buena + "\n")
        copias = [n for n in os.listdir(os.path.dirname(self.ruta))
                  if ".bak-" in n]
        self.assertEqual(len(copias), 1)
        with open(os.path.join(os.path.dirname(self.ruta), copias[0]),
                  encoding="utf-8") as fh:
            self.assertIn("roto", fh.read())
        truncadas = [n for n in os.listdir(os.path.dirname(self.ruta))
                     if ".truncada-" in n]
        self.assertEqual(len(truncadas), 1)
        with open(os.path.join(os.path.dirname(self.ruta), truncadas[0]),
                  encoding="utf-8") as fh:
            self.assertIn('{"entidad_id": "roto', fh.read())

    def test_no_repara_fichero_que_crece(self):
        with mock.patch.object(salud, "detectar_crecimiento",
                               return_value={self.ruta: True}):
            acciones = salud.reparar_ficheros([self.ruta], si=True, intervalo=0)
        self.assertEqual(acciones[0]["estado"], "omitido_creciendo")
        with open(self.ruta, encoding="utf-8") as fh:
            texto = fh.read()
        self.assertTrue(texto.endswith("roto"))
        nombres = os.listdir(os.path.dirname(self.ruta))
        self.assertFalse(any(".bak-" in n for n in nombres))

    def test_no_repara_si_la_ultima_linea_es_valida(self):
        escribir(self.ruta, self.buena + "\n")
        acciones = salud.reparar_ficheros([self.ruta], si=True, intervalo=0)
        self.assertEqual(acciones, [])


class Copias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = os.path.join(self.tmp.name, "fase0")
        self.backups = os.path.join(self.tmp.name, "backups")
        escribir(os.path.join(self.base, "evidencias_web", "evidencias.jsonl"),
                 linea(**EVIDENCIA) + "\n")

    def test_copia_y_restauracion(self):
        res = salud.crear_copia(self.base, self.backups, min_libre_gb=0,
                                ahora="20261020-2215")
        self.assertTrue(os.path.exists(res["tar"]))
        self.assertIn("evidencias_web/evidencias.jsonl", res["ficheros"])
        esperado = hashlib.sha256(
            (linea(**EVIDENCIA) + "\n").encode("utf-8")).hexdigest()
        self.assertEqual(
            res["ficheros"]["evidencias_web/evidencias.jsonl"]["sha256"],
            esperado)
        with open(res["manifiesto"], encoding="utf-8") as fh:
            manifiesto = json.load(fh)
        self.assertEqual(
            manifiesto["ficheros"]["evidencias_web/evidencias.jsonl"]["sha256"],
            esperado)
        destino = os.path.join(self.tmp.name, "restaurado", "evidencias.jsonl")
        salud.restaurar_miembro(res["tar"], "evidencias_web/evidencias.jsonl",
                                destino)
        with open(destino, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), linea(**EVIDENCIA) + "\n")

    def test_copia_de_fichero_que_crece_solo_hasta_linea_completa(self):
        ruta = os.path.join(self.base, "evidencias_web", "evidencias.jsonl")
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write('{"entidad_id": "a medias')
        with mock.patch.object(salud, "detectar_crecimiento",
                               return_value={ruta: True}):
            res = salud.crear_copia(self.base, self.backups, min_libre_gb=0,
                                    ahora="20261020-2216")
        destino = os.path.join(self.tmp.name, "r.jsonl")
        salud.restaurar_miembro(res["tar"], "evidencias_web/evidencias.jsonl",
                                destino)
        with open(destino, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), linea(**EVIDENCIA) + "\n")

    def test_rotacion_conserva_cinco(self):
        os.makedirs(self.backups)
        for i in range(1, 8):
            os.makedirs(os.path.join(self.backups, "2026010%d-1200" % i))
        borradas = salud.rotar_copias(self.backups, max_copias=5)
        quedan = sorted(os.listdir(self.backups))
        self.assertEqual(len(quedan), 5)
        self.assertEqual(quedan[0], "20260103-1200")
        self.assertEqual(len(borradas), 2)

    def test_aborta_si_queda_poco_espacio(self):
        uso = os.statvfs(self.tmp.name)
        libre = uso.f_bavail * uso.f_frsize
        with mock.patch.object(salud.shutil, "disk_usage",
                               return_value=mock.Mock(free=libre)):
            with self.assertRaises(RuntimeError):
                salud.crear_copia(self.base, self.backups, min_libre_gb=10 ** 9,
                                  ahora="20261020-2217")

    def test_no_copia_crudo_ni_secciones(self):
        escribir(os.path.join(self.base, "libros", "crudo", "x.txt"), "crudo")
        escribir(os.path.join(self.base, "libros", "secciones", "x.jsonl"),
                 '{"id": "x"}\n')
        res = salud.crear_copia(self.base, self.backups, min_libre_gb=0,
                                ahora="20261020-2218")
        self.assertNotIn("libros/crudo/x.txt", res["ficheros"])
        self.assertNotIn("libros/secciones/x.jsonl", res["ficheros"])


if __name__ == "__main__":
    unittest.main()
