# Tests de clasicos_pd_a_evidencias: orquestador de clásicos PD (T57).
# Sin red ni LLM: cliente simulado que responde el primer candidato.
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import io
import json
import contextlib
import re
import tempfile
import unittest
from unittest import mock

import clasicos_pd_a_evidencias as mod


class ClienteFalso:
    """Cuenta llamadas y responde con el primer candidato y una faceta exenta."""

    def __init__(self):
        self.llamadas = 0

    def chat(self, sistema, usuario, **kwargs):
        self.llamadas += 1
        m = re.search(r"^- (\S+) \(", usuario, re.M)
        entidades = []
        if m:
            entidades = [{"entidad_id": m.group(1),
                         "facetas": ["significado_general"]}]
        return json.dumps({"tipo": "conocimiento", "calidad": 4,
                          "idioma": "es", "entidades": entidades})


_VALORES = ["as", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
            "nueve", "diez"]
_PALOS = ["oros", "copas", "espadas", "bastos"]


def _texto_variado(n):
    """n secciones de naipes españoles, todas con candidatos y texto unico."""
    partes = []
    for i in range(n):
        palo = _PALOS[i % 4]
        valor = _VALORES[(i // 4) % 10]
        partes.append(
            "EL %s DE %s\n\n"
            "El %s de %s significa prosperidad en el amor y en el trabajo "
            "del consultante numero %d.\n"
            "Su simbolismo habla de abundancia, dinero y salud para quien "
            "lo consulta.\n"
            "En esta tirada el %s de %s trae consejo practico y noticias "
            "de hacienda.\n"
            % (valor.upper(), palo.upper(), valor, palo, i, valor, palo))
    return "\n".join(partes)


class TestOrden(unittest.TestCase):
    def test_libro_negro_primero(self):
        libros = mod.libros_en_orden()
        self.assertEqual(libros[0]["id"], "libro_negro_1886")

    def test_baraja_antes_que_numerologia_y_astrologia(self):
        familias = [l["familia"] for l in mod.libros_en_orden()]
        ultima_baraja = max(i for i, f in enumerate(familias) if f == "baraja")
        primera_num = min(i for i, f in enumerate(familias)
                         if f == "numerologia")
        primera_astro = min(i for i, f in enumerate(familias)
                           if f == "astrologia")
        self.assertLess(ultima_baraja, primera_num)
        self.assertLess(primera_num, primera_astro)

    def test_ids_desconocidos_error_claro(self):
        with self.assertRaises(mod.LibroAusenteError) as ctx:
            mod.libros_en_orden({"no_existe_pd"})
        self.assertIn("no_existe_pd", str(ctx.exception))

    def test_solo_ids_conserva_prioridad(self):
        libros = mod.libros_en_orden({"agrippa_three_books_1898",
                                     "libro_negro_1886"})
        self.assertEqual([l["id"] for l in libros],
                         ["libro_negro_1886", "agrippa_three_books_1898"])


class TestWorkDir(unittest.TestCase):
    def test_work_dir_real_rechazado(self):
        with self.assertRaises(ValueError):
            mod.validar_work_dir(mod.WORK_DIR_REAL)
        with self.assertRaises(ValueError):
            mod.validar_work_dir(mod.WORK_DIR_REAL + "/evidencias")

    def test_work_dir_aparte_aceptado(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(mod.validar_work_dir(tmp), os.path.realpath(tmp))

    def test_ejecutar_en_directorio_real_no_escribe_nada(self):
        cliente = ClienteFalso()
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = mod.ejecutar(work_dir=mod.WORK_DIR_REAL, cliente=cliente)
        self.assertEqual(code, 2)
        self.assertEqual(cliente.llamadas, 0)
        self.assertIn("directorio real", err.getvalue())


class TestDryRun(unittest.TestCase):
    def test_dry_run_sin_llamadas_ni_escritura(self):
        with tempfile.TemporaryDirectory() as tmp:
            crudo = os.path.join(tmp, "crudo_origen")
            os.makedirs(crudo)
            with open(os.path.join(crudo, "libro_negro_1886.txt"), "w",
                     encoding="utf-8") as fh:
                fh.write(_texto_variado(6))
            work = os.path.join(tmp, "work")
            cliente = ClienteFalso()
            with mock.patch.object(mod, "CRUDO_ORIGEN", crudo):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = mod.ejecutar(work_dir=work, dry_run=True,
                                       cliente=cliente)
            self.assertEqual(code, 0)
            self.assertEqual(cliente.llamadas, 0)
            self.assertNotEqual(os.path.exists(work), True)
            salida = out.getvalue()
            self.assertIn("libro_negro_1886", salida)
            self.assertIn("secciones", salida)

    def test_dry_run_advierte_si_supera_umbral(self):
        medida = {"secciones": 700, "con_candidatos": mod.UMBRAL_LLAMADAS + 50,
                 "llamadas_estimadas": mod.UMBRAL_LLAMADAS + 50,
                 "calidad_baja": False}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(mod, "medir_libro", return_value=medida):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    mod.ejecutar(work_dir=os.path.join(tmp, "work"),
                                 dry_run=True, cliente=ClienteFalso())
            self.assertIn("supera", out.getvalue())
            self.assertIn("--max-llamadas", out.getvalue())


class TestProceso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.crudo = os.path.join(self.tmp.name, "crudo_origen")
        os.makedirs(self.crudo)
        with open(os.path.join(self.crudo, "libro_negro_1886.txt"), "w",
                 encoding="utf-8") as fh:
            fh.write(_texto_variado(6))
        self.work = os.path.join(self.tmp.name, "work")
        self.patcher = mock.patch.object(mod, "CRUDO_ORIGEN", self.crudo)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_libro_ausente_error_claro(self):
        with self.assertRaises(mod.LibroAusenteError) as ctx:
            mod.preparar_work_dir(self.work, [{"id": "fantasma_pd"}])
        self.assertIn("fantasma_pd", str(ctx.exception))

    def test_procesa_y_escribe_resumen(self):
        cliente = ClienteFalso()
        with contextlib.redirect_stdout(io.StringIO()):
            code = mod.ejecutar(work_dir=self.work, cliente=cliente,
                               solo_ids={"libro_negro_1886"})
        self.assertEqual(code, 0)
        self.assertGreater(cliente.llamadas, 0)
        ruta_resumen = os.path.join(self.work, "resumenes",
                                   "libro_negro_1886.json")
        self.assertTrue(os.path.exists(ruta_resumen))
        with open(ruta_resumen, encoding="utf-8") as fh:
            resumen = json.load(fh)
        for clave in ("secciones", "juzgadas", "llamadas", "evidencias",
                     "aceptadas_calidad_ge_3", "evidencias_por_familia",
                     "evidencias_por_entidad"):
            self.assertIn(clave, resumen)
        self.assertGreater(resumen["evidencias"], 0)
        self.assertGreaterEqual(resumen["aceptadas_calidad_ge_3"], 1)
        self.assertTrue(os.path.exists(
            os.path.join(self.work, "evidencias", "evidencias.jsonl")))

    def test_reanudacion_sin_repetir_llamadas(self):
        with contextlib.redirect_stdout(io.StringIO()):
            mod.ejecutar(work_dir=self.work, cliente=ClienteFalso(),
                         solo_ids={"libro_negro_1886"})
        cliente2 = ClienteFalso()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            mod.ejecutar(work_dir=self.work, cliente=cliente2,
                         solo_ids={"libro_negro_1886"})
        self.assertEqual(cliente2.llamadas, 0)
        self.assertIn("reaprovechadas", out.getvalue())
        ruta = os.path.join(self.work, "evidencias", "evidencias.jsonl")
        with open(ruta, encoding="utf-8") as fh:
            lineas = [json.loads(l) for l in fh if l.strip()]
        hashes = [e["hash_seccion"] for e in lineas]
        self.assertEqual(len(hashes), len(set(hashes)))

    def test_max_llamadas_recorta_y_continua(self):
        with open(os.path.join(self.crudo, "libro_negro_1886.txt"), "w",
                 encoding="utf-8") as fh:
            fh.write(_texto_variado(6))
        cliente1 = ClienteFalso()
        with contextlib.redirect_stdout(io.StringIO()):
            mod.ejecutar(work_dir=self.work, cliente=cliente1,
                         solo_ids={"libro_negro_1886"}, max_llamadas=1)
        self.assertLessEqual(cliente1.llamadas, 1)
        cliente2 = ClienteFalso()
        with contextlib.redirect_stdout(io.StringIO()):
            mod.ejecutar(work_dir=self.work, cliente=cliente2,
                         solo_ids={"libro_negro_1886"})
        self.assertGreater(cliente2.llamadas, 1)

    def test_periodo_clasica_en_evidencias(self):
        with contextlib.redirect_stdout(io.StringIO()):
            mod.ejecutar(work_dir=self.work, cliente=ClienteFalso(),
                         solo_ids={"libro_negro_1886"})
        ruta = os.path.join(self.work, "evidencias", "evidencias.jsonl")
        with open(ruta, encoding="utf-8") as fh:
            evidencias = [json.loads(l) for l in fh if l.strip()]
        self.assertTrue(evidencias)
        for ev in evidencias:
            self.assertEqual(ev["periodo"], "clasica")
            self.assertEqual(ev["tipo"], "libro")


if __name__ == "__main__":
    unittest.main()
