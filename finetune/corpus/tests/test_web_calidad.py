#!/usr/bin/env python3
"""Tests de web_calidad: auditoría determinista de páginas web descargadas."""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from web_calidad import (
    bandera_corta,
    detectar_duplicadas,
    bandera_mojibake,
    bandera_no_espanol,
    bandera_repeticion_interna,
    bandera_ruido_navegacion,
    bandera_titulo_pobre,
    leer_pagina,
    leer_paginas,
    analizar_paginas,
    parrafos_repetidos,
)


FM = """---
url: "https://ejemplo.com/pagina"
dominio: {dominio}
titulo: {titulo}
entidad_id: null
faceta: null
familia: astrologia
idioma: es
fecha: null
sha256: {sha}
licencia_hint: consultar
---

{cuerpo}
"""


def _escribir_pagina(base: Path, dominio: str, nombre: str, titulo: str,
                     cuerpo: str, sha: str = None) -> Path:
    carpeta = base / dominio
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    if sha is None:
        sha = hashlib.sha256(f"{dominio}/{nombre}".encode("utf-8")).hexdigest()
    ruta.write_text(FM.format(dominio=dominio, titulo=titulo, sha=sha, cuerpo=cuerpo), encoding="utf-8")
    return ruta


class LecturaPaginasTests(unittest.TestCase):
    def test_lee_front_matter_y_cuerpo(self):
        with tempfile.TemporaryDirectory() as td:
            ruta = _escribir_pagina(
                Path(td), "ejemplo.com", "uno.md", "Carta astral",
                "Contenido de la página con suficientes palabras.",
                sha="abc123",
            )
            pagina = leer_pagina(ruta)
            self.assertEqual(pagina["titulo"], "Carta astral")
            self.assertEqual(pagina["dominio"], "ejemplo.com")
            self.assertEqual(pagina["sha256"], "abc123")
            self.assertNotIn("---", pagina["cuerpo"])
            self.assertIn("Contenido de la página", pagina["cuerpo"])
            self.assertEqual(pagina["ruta"], str(ruta))

    def test_titulo_entre_comillas_y_dos_puntos(self):
        with tempfile.TemporaryDirectory() as td:
            ruta = _escribir_pagina(
                Path(td), "ejemplo.com", "dos.md",
                '"Tarot: guía básica"', "Texto cualquiera.",
            )
            pagina = leer_pagina(ruta)
            self.assertEqual(pagina["titulo"], "Tarot: guía básica")

    def test_sin_front_matter_usa_primer_encabezado(self):
        with tempfile.TemporaryDirectory() as td:
            carpeta = Path(td) / "sinfm.com"
            carpeta.mkdir()
            ruta = carpeta / "uno.md"
            ruta.write_text("# Numerología básica\n\nTexto del cuerpo.", encoding="utf-8")
            pagina = leer_pagina(ruta)
            self.assertEqual(pagina["titulo"], "Numerología básica")
            self.assertEqual(pagina["dominio"], "sinfm.com")
            self.assertIn("Texto del cuerpo", pagina["cuerpo"])

    def test_lee_todas_las_paginas_por_dominio(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _escribir_pagina(base, "a.com", "uno.md", "Uno", "Cuerpo uno.")
            _escribir_pagina(base, "b.com", "dos.md", "Dos", "Cuerpo dos.")
            (base / "notas.txt").write_text("no es markdown", encoding="utf-8")
            paginas = leer_paginas(base)
            self.assertEqual(len(paginas), 2)
            self.assertEqual({p["dominio"] for p in paginas}, {"a.com", "b.com"})


class BanderaCortaTests(unittest.TestCase):
    def test_texto_menor_de_mil_caracteres(self):
        self.assertTrue(bandera_corta("x" * 999))

    def test_texto_de_mil_o_mas_caracteres(self):
        self.assertFalse(bandera_corta("x" * 1000))

    def test_ignora_espacios_del_borde(self):
        self.assertFalse(bandera_corta("  " + "x" * 1000 + "  "))


class BanderaMojibakeTests(unittest.TestCase):
    def test_detecta_secuencias_rotas(self):
        for muestra in ("Ã©", "Ã±", "â€™", "â€œ", "Â¿", "�"):
            with self.subTest(muestra=muestra):
                self.assertTrue(bandera_mojibake(f"Texto con {muestra} roto."))

    def test_texto_espanol_correcto_no_tiene_bandera(self):
        self.assertFalse(bandera_mojibake("Canción, niño, ¿qué tal? «Comillas»."))


class BanderaTituloPobreTests(unittest.TestCase):
    def test_titulo_vacio(self):
        self.assertTrue(bandera_titulo_pobre(""))
        self.assertTrue(bandera_titulo_pobre("   "))

    def test_titulo_demasiado_corto(self):
        self.assertTrue(bandera_titulo_pobre("abc"))

    def test_titulo_acaba_en_dos_puntos(self):
        self.assertTrue(bandera_titulo_pobre("Significado de la carta:"))

    def test_titulo_con_markdown(self):
        self.assertTrue(bandera_titulo_pobre("**El Loco**"))

    def test_titulo_correcto(self):
        self.assertFalse(bandera_titulo_pobre("El Loco en el tarot"))


class AnalizarPaginasTests(unittest.TestCase):
    def test_marca_banderas_de_cada_pagina(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _escribir_pagina(base, "a.com", "corta.md", "abc", "Texto breve.")
            _escribir_pagina(
                base, "a.com", "larga.md", "Título correcto",
                "Contenido limpio. " * 100,
            )
            paginas = analizar_paginas(leer_paginas(base))
            por_nombre = {Path(p["ruta"]).name: p for p in paginas}
            self.assertEqual(
                por_nombre["corta.md"]["banderas"], ["corta", "titulo_pobre"]
            )
            self.assertEqual(por_nombre["larga.md"]["banderas"], [])
            self.assertGreater(por_nombre["larga.md"]["caracteres"], 1000)


if __name__ == "__main__":
    unittest.main()

class BanderaNoEspanolTests(unittest.TestCase):
    def test_texto_largo_en_espanol(self):
        texto = (
            "El tarot es un sistema de símbolos que se utiliza para interpretar "
            "la vida y las decisiones de quien consulta. "
        ) * 8
        self.assertFalse(bandera_no_espanol(texto))

    def test_texto_largo_en_ingles(self):
        texto = (
            "The tarot is a system of symbols that people use to interpret life "
            "and to find meaning in the world around them. "
        ) * 8
        self.assertTrue(bandera_no_espanol(texto))

    def test_texto_corto_no_se_evalua(self):
        self.assertFalse(bandera_no_espanol("Short English text with the and of."))


class BanderaRuidoNavegacionTests(unittest.TestCase):
    def test_menu_consecutivo(self):
        texto = "Inicio\nQuiénes somos\nContacto\nAviso legal\nPolítica de cookies"
        self.assertTrue(bandera_ruido_navegacion(texto))

    def test_prosa_no_es_ruido(self):
        texto = (
            "La carta del Loco representa el inicio de un camino.\n"
            "Su energía invita a confiar en lo desconocido.\n"
            "En una tirada indica un salto hacia adelante."
        )
        self.assertFalse(bandera_ruido_navegacion(texto))

    def test_dos_lineas_no_bastan(self):
        self.assertFalse(bandera_ruido_navegacion("Inicio\nContacto"))

    def test_pie_con_copyright(self):
        texto = (
            "Texto introductorio de la página.\n"
            "© 2024 Todos los derechos reservados\n"
            "Aviso legal\n"
            "Política de privacidad"
        )
        self.assertTrue(bandera_ruido_navegacion(texto))


class BanderaRepeticionInternaTests(unittest.TestCase):
    def test_parrafo_repetido_tres_veces(self):
        parrafo = "Este párrafo se repite varias veces dentro de la misma página."
        texto = "\n\n".join([parrafo, "Otro párrafo distinto.", parrafo, parrafo])
        self.assertTrue(bandera_repeticion_interna(texto))
        repetidos = parrafos_repetidos(texto)
        self.assertEqual(len(repetidos), 1)
        self.assertEqual(repetidos[0][1], 3)

    def test_parrafo_repetido_dos_veces(self):
        parrafo = "Este párrafo aparece solo dos veces en esta página de prueba."
        texto = "\n\n".join([parrafo, parrafo])
        self.assertFalse(bandera_repeticion_interna(texto))

    def test_ignora_variaciones_de_espacios_y_mayusculas(self):
        parrafo = "La misma frase repetida con variaciones de formato."
        texto = "\n".join([
            parrafo,
            "  LA MISMA FRASE   repetida con variaciones de formato.  ",
            parrafo,
        ])
        self.assertTrue(bandera_repeticion_interna(texto))


class AnalizarPaginasT312Tests(unittest.TestCase):
    def test_incluye_banderas_de_lenguaje_ruido_y_repeticion(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            ingles = (
                "The tarot is a system of symbols that people use to interpret "
                "life and to find meaning in the world around them. "
            ) * 8
            _escribir_pagina(base, "a.com", "ingles.md", "Tarot guide", ingles)
            parrafo = "Este párrafo se repite varias veces dentro de la misma página."
            _escribir_pagina(
                base, "a.com", "repite.md", "Página repetida",
                "\n".join([parrafo, parrafo, parrafo]),
            )
            paginas = analizar_paginas(leer_paginas(base))
            por_nombre = {Path(p["ruta"]).name: p for p in paginas}
            self.assertIn("no_espanol", por_nombre["ingles.md"]["banderas"])
            self.assertIn(
                "repeticion_interna", por_nombre["repite.md"]["banderas"]
            )
            self.assertGreaterEqual(
                len(por_nombre["repite.md"]["detalles"]["repeticion_interna"]), 1
            )

class DetectarDuplicadasTests(unittest.TestCase):
    def test_mismo_sha256_marca_ambas_paginas(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _escribir_pagina(base, "a.com", "uno.md", "Página uno",
                             "Cuerpo distinto de la primera página.", sha="mismo")
            _escribir_pagina(base, "a.com", "dos.md", "Página dos",
                             "Cuerpo distinto de la segunda página.", sha="mismo")
            paginas = leer_paginas(base)
            infos = detectar_duplicadas(paginas)
            self.assertEqual(set(infos), {0, 1})
            por_ruta = {paginas[i]["ruta"]: infos[i] for i in infos}
            info_uno = por_ruta[str(base / "a.com" / "uno.md")]
            info_dos = por_ruta[str(base / "a.com" / "dos.md")]
            self.assertEqual(info_uno["motivo"], "sha256")
            self.assertIn(str(base / "a.com" / "dos.md"), info_uno["rutas"])
            self.assertIn(str(base / "a.com" / "uno.md"), info_dos["rutas"])

    def test_parrafos_casi_identicos(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            comunes = [
                f"Párrafo compartido número {i} con longitud suficiente para contar."
                for i in range(10)
            ]
            _escribir_pagina(base, "a.com", "uno.md", "Página uno",
                             "\n".join(comunes))
            _escribir_pagina(base, "a.com", "dos.md", "Página dos",
                             "\n".join(comunes + [
                                 "Párrafo exclusivo de la segunda página, también largo."
                             ]))
            paginas = leer_paginas(base)
            infos = detectar_duplicadas(paginas)
            self.assertEqual(set(infos), {0, 1})
            por_ruta = {paginas[i]["ruta"]: infos[i] for i in infos}
            info_uno = por_ruta[str(base / "a.com" / "uno.md")]
            info_dos = por_ruta[str(base / "a.com" / "dos.md")]
            self.assertEqual(info_uno["motivo"], "parrafos")
            self.assertAlmostEqual(info_uno["jaccard"], 10 / 11, places=3)
            self.assertIn(str(base / "a.com" / "dos.md"), info_uno["rutas"])
            self.assertIn(str(base / "a.com" / "uno.md"), info_dos["rutas"])

    def test_paginas_distintas_no_se_marcan(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _escribir_pagina(base, "a.com", "uno.md", "Página uno",
                             "Contenido completamente distinto sobre el tarot y sus arcanos.")
            _escribir_pagina(base, "a.com", "dos.md", "Página dos",
                             "Otra materia sin relación alguna con la numerología práctica.")
            infos = detectar_duplicadas(leer_paginas(base))
            self.assertEqual(infos, {})

    def test_analizar_incluye_bandera_duplicada(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _escribir_pagina(base, "a.com", "uno.md", "Página uno",
                             "Cuerpo suficientemente largo para no marcarse como corto. " * 30,
                             sha="repetido")
            _escribir_pagina(base, "a.com", "dos.md", "Página dos",
                             "Otro cuerpo suficientemente largo para no marcarse como corto. " * 30,
                             sha="repetido")
            paginas = analizar_paginas(leer_paginas(base))
            por_nombre = {Path(p["ruta"]).name: p for p in paginas}
            for nombre in ("uno.md", "dos.md"):
                self.assertIn("duplicada", por_nombre[nombre]["banderas"])
                detalle = por_nombre[nombre]["detalles"]["duplicada_de"]
                self.assertEqual(detalle["motivo"], "sha256")
                self.assertEqual(len(detalle["rutas"]), 1)
