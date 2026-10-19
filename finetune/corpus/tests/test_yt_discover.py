"""Tests del descubrimiento de vídeos y selección de canales (A4.2)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yt_discover


def _crudo(**kwargs):
    """Entrada cruda tipo yt_dlp (extract_flat) con valores por defecto."""
    entrada = {
        "id": "vid000000001",
        "title": "Lectura de tarot completa",
        "duration": 600,
        "channel": "Canal Uno",
        "channel_id": "UC111",
        "view_count": 5000,
        "url": "https://www.youtube.com/watch?v=vid000000001",
    }
    entrada.update(kwargs)
    return entrada


def _fila(**kwargs):
    """Fila de catálogo (claves en español) para puntuar/tope."""
    fila = {
        "id": "vid000000001",
        "canal": "Canal Uno",
        "canal_id": "UC111",
        "titulo": "Lectura de tarot completa",
        "duracion": 600,
        "vistas": 5000,
        "fecha": "20260101",
        "familia": "tarot-lectura",
        "consulta": "lectura de tarot",
    }
    fila.update(kwargs)
    return fila


class YDLFalso:
    """Doble de yt_dlp.YoutubeDL: responde según la URL pedida."""

    def __init__(self, opciones=None, respuestas=None):
        self.opciones = opciones or {}
        self.respuestas = respuestas or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        for prefijo, entradas in self.respuestas.items():
            if url.startswith(prefijo) or url == prefijo:
                if entradas is None:
                    return {"entries": None}
                return {"entries": list(entradas)}
        return {"entries": []}


def _doble(respuestas):
    """Fábrica para inyectar como clase_ydl."""
    return lambda opciones=None: YDLFalso(opciones, respuestas)


class ConstruirConsultas(unittest.TestCase):
    def test_al_menos_60_consultas_en_total(self):
        total = []
        for familia in yt_discover.FAMILIAS:
            consultas = yt_discover.construir_consultas(familia)
            self.assertGreater(len(consultas), 0, familia)
            for consulta in consultas:
                self.assertIsInstance(consulta, str)
                self.assertTrue(consulta.strip())
            total.extend(consultas)
        self.assertGreaterEqual(len(total), 60)

    def test_consultas_sin_duplicar(self):
        total = []
        for familia in yt_discover.FAMILIAS:
            total.extend(yt_discover.construir_consultas(familia))
        self.assertEqual(len(total), len(set(total)))

    def test_familia_desconocida(self):
        with self.assertRaises(ValueError):
            yt_discover.construir_consultas("familia-inexistente")

    def test_devuelve_copia(self):
        a = yt_discover.construir_consultas("tarot-lectura")
        a.append("x")
        self.assertNotIn("x", yt_discover.construir_consultas("tarot-lectura"))


class FiltrarCandidatos(unittest.TestCase):
    def test_duracion_en_rango_ok(self):
        entradas = [_crudo(duration=240), _crudo(duration=3600)]
        salida = yt_discover.filtrar_candidatos(entradas)
        self.assertEqual(len(salida), 2)

    def test_duracion_fuera_de_rango(self):
        entradas = [_crudo(duration=120), _crudo(duration=4000),
                    _crudo(duration=None)]
        self.assertEqual(yt_discover.filtrar_candidatos(entradas), [])

    def test_descarta_directos(self):
        entradas = [
            _crudo(id="a", live_status="is_live"),
            _crudo(id="b", was_live=True),
            _crudo(id="c", is_live=True),
        ]
        self.assertEqual(yt_discover.filtrar_candidatos(entradas), [])

    def test_descarta_shorts_y_listas(self):
        entradas = [
            _crudo(id="a", duration=60),
            _crudo(id="b",
                   url="https://www.youtube.com/shorts/abc12345678"),
            _crudo(id="c", _type="playlist", duration=600),
            _crudo(id="d", type="playlist", duration=600),
        ]
        self.assertEqual(yt_discover.filtrar_candidatos(entradas), [])

    def test_descarta_titulo_vacio(self):
        entradas = [_crudo(title="  "), _crudo(title=None)]
        self.assertEqual(yt_discover.filtrar_candidatos(entradas), [])

    def test_conserva_orden(self):
        entradas = [_crudo(id="a"), _crudo(id="b"), _crudo(id="c")]
        salida = yt_discover.filtrar_candidatos(entradas)
        self.assertEqual([e["id"] for e in salida], ["a", "b", "c"])


class PuntuarCanales(unittest.TestCase):
    def test_agrupa_y_ordena(self):
        filas = [
            _fila(id="1", canal_id="UC_A", canal="A", vistas=1000),
            _fila(id="2", canal_id="UC_A", canal="A", vistas=3000),
            _fila(id="3", canal_id="UC_B", canal="B", vistas=9000),
        ]
        salida = yt_discover.puntuar_canales(filas)
        self.assertEqual(salida[0]["canal_id"], "UC_A")
        self.assertEqual(salida[0]["n_videos"], 2)
        self.assertEqual(salida[0]["vistas_medias"], 2000.0)
        self.assertEqual(salida[1]["canal_id"], "UC_B")
        self.assertEqual(salida[1]["n_videos"], 1)

    def test_regularidad_por_dias_distintos(self):
        filas = [
            _fila(id="1", canal_id="UC_A", fecha="20260101"),
            _fila(id="2", canal_id="UC_A", fecha="20260101"),
            _fila(id="3", canal_id="UC_A", fecha="20260315"),
        ]
        salida = yt_discover.puntuar_canales(filas)
        self.assertEqual(salida[0]["dias_con_videos"], 2)

    def test_vacio(self):
        self.assertEqual(yt_discover.puntuar_canales([]), [])


class TopePorCanal(unittest.TestCase):
    def test_limita_al_tope(self):
        filas = [_fila(id=f"a{i}", canal_id="UC_A") for i in range(100)]
        filas += [_fila(id=f"b{i}", canal_id="UC_B") for i in range(5)]
        salida = yt_discover.aplicar_tope_por_canal(filas, tope=0.03)
        ids_a = [f["id"] for f in salida if f["canal_id"] == "UC_A"]
        ids_b = [f["id"] for f in salida if f["canal_id"] == "UC_B"]
        self.assertEqual(len(ids_a), 3)
        self.assertEqual(len(ids_b), 3)
        self.assertEqual(ids_a, ["a0", "a1", "a2"])

    def test_tope_miniuno_y_vacio(self):
        filas = [_fila(id=f"a{i}", canal_id="UC_A") for i in range(10)]
        salida = yt_discover.aplicar_tope_por_canal(filas, tope=0.0)
        self.assertEqual(len(salida), 1)
        self.assertEqual(yt_discover.aplicar_tope_por_canal([], 0.03), [])


class CanalesParaExpandir(unittest.TestCase):
    def test_umbral_tres(self):
        filas = [_fila(id=f"a{i}", canal_id="UC_A") for i in range(3)]
        filas += [_fila(id=f"b{i}", canal_id="UC_B") for i in range(2)]
        self.assertEqual(yt_discover.canales_para_expandir(filas),
                         ["UC_A"])


class Descubrimiento(unittest.TestCase):
    def _respuestas(self):
        return {
            "ytsearch2:lectura de tarot amor": [
                _crudo(id="ok1", title="Lectura de tarot de amor",
                       channel_id="UC_A", channel="Canal A"),
                _crudo(id="corto", duration=60),
                _crudo(id="otro", title="Otra lectura",
                       channel_id="UC_B", channel="Canal B"),
            ],
            "https://www.youtube.com/channel/UC_A/videos": [
                _crudo(id="exp1", title="Video del canal A",
                       channel_id="UC_A", channel="Canal A"),
                _crudo(id="ok1", title="Ya estaba"),
            ],
        }

    def test_descubrimiento_basico_y_salida(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=2, pausa=0.0,
                max_consultas=1, expandir_canales=False,
                clase_ydl=_doble(self._respuestas()))
            self.assertEqual(stats["nuevos"], 2)
            ruta = os.path.join(tmp, "catalogo.jsonl")
            self.assertTrue(os.path.exists(ruta))
            with open(ruta, encoding="utf-8") as fh:
                filas = [json.loads(linea) for linea in fh if linea.strip()]
            self.assertEqual([f["id"] for f in filas], ["ok1", "otro"])
            self.assertEqual(filas[0]["familia"], "tarot-lectura")
            self.assertEqual(filas[0]["consulta"], "lectura de tarot amor")
            self.assertEqual(filas[0]["titulo"],
                             "Lectura de tarot de amor")
            self.assertEqual(filas[0]["duracion"], 600)
            self.assertEqual(filas[0]["vistas"], 5000)
            self.assertTrue(os.path.exists(
                os.path.join(tmp, "canales.md")))

    def test_reanudable_no_repite_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            yt_discover.descubrir(out_dir=tmp, n_por_consulta=2,
                                  pausa=0.0, max_consultas=1,
                                  expandir_canales=False,
                                  clase_ydl=_doble(self._respuestas()))
            stats2 = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=2, pausa=0.0,
                max_consultas=1, expandir_canales=False,
                clase_ydl=_doble(self._respuestas()))
            self.assertEqual(stats2["nuevos"], 0)
            with open(os.path.join(tmp, "catalogo.jsonl"),
                      encoding="utf-8") as fh:
                self.assertEqual(len(fh.readlines()), 2)

    def test_expansion_de_canales(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=2, pausa=0.0,
                max_consultas=1, expandir_canales=True,
                clase_ydl=_doble(self._respuestas()))
            # UC_A tiene 1 acierto en la búsqueda: no se expande (umbral 3)
            self.assertEqual(stats["canales_expandidos"], 0)
            with open(os.path.join(tmp, "catalogo.jsonl"),
                      encoding="utf-8") as fh:
                ids = [json.loads(l)["id"] for l in fh if l.strip()]
            self.assertNotIn("exp1", ids)

    def test_expansion_con_tres_aciertos(self):
        respuestas = self._respuestas()
        respuestas["ytsearch3:lectura de tarot amor"] = [
            _crudo(id=f"ok{i}", title=f"Lectura {i}",
                   channel_id="UC_A", channel="Canal A")
            for i in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            stats = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=3, pausa=0.0,
                max_consultas=1, expandir_canales=True,
                clase_ydl=_doble(respuestas))
            self.assertEqual(stats["canales_expandidos"], 1)
            with open(os.path.join(tmp, "catalogo.jsonl"),
                      encoding="utf-8") as fh:
                ids = [json.loads(l)["id"] for l in fh if l.strip()]
            self.assertIn("exp1", ids)
            self.assertEqual(len(ids), len(set(ids)))


class FiltroIdioma(unittest.TestCase):
    def test_titulos_reales_ingles_fallan(self):
        for titulo in [
            "Work and Money",
            "What's Coming for Your FINANCES: Money Reading",
            "HOW TO READ A 3-CARD READING - TAROT RIDER COURSE",
            "Tarot Readings for Work and Projects",
        ]:
            self.assertFalse(yt_discover.es_probablemente_espanol(titulo, ""),
                           f"debería descartar: {titulo}")

    def test_titulos_reales_espanol_pasan(self):
        for titulo in [
            "🌺SU PENSAMIENTO MÁS RECIENTE SOBRE TI Y LO VUESTRO🌺",
            "CURSO DE TAROT. LAS 3 TIRADAS BÁSICAS DE TAROT PARA EMPEZAR",
            "🧭PIENSA EN UNA PERSONA Y TE DIRÉ QUE SIGNIFICAS PARA EL/ELLA",
        ]:
            self.assertTrue(yt_discover.es_probablemente_espanol(titulo, ""),
                           f"debería aceptar: {titulo}")

    def test_titulo_neuro_canal_espagnol_pasa(self):
        self.assertTrue(yt_discover.es_probablemente_espanol(
            "Tarot 2026", "Tarot con María"))

    def test_titulo_neutro_canal_ingles_falla(self):
        self.assertFalse(yt_discover.es_probablemente_espanol(
            "Tarot 2026", "English Tarot Channel"))

    def test_mixed_gana_senal_espanola(self):
        self.assertTrue(yt_discover.es_probablemente_espanol(
            "Lectura de tarot para ti", ""))

    def test_vacio_falla(self):
        self.assertFalse(yt_discover.es_probablemente_espanol("", ""))


class DescubrimientoSoloEspanol(unittest.TestCase):
    def _respuestas(self):
        return {
            "ytsearch2:lectura de tarot amor": [
                _crudo(id="es1", title="TIRADA DE TAROT PARA HOY",
                       channel_id="UC_ES", channel="Tarot con María"),
                _crudo(id="en1", title="What's Coming for Your FINANCES: Money Reading",
                       channel_id="UC_EN", channel="English Tarot"),
            ],
        }

    def test_descarta_ingles_por_defecto(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=2, pausa=0.0,
                max_consultas=1, clase_ydl=_doble(self._respuestas()))
            with open(os.path.join(tmp, "catalogo.jsonl"), encoding="utf-8") as fh:
                ids = [json.loads(l)["id"] for l in fh if l.strip()]
            self.assertIn("es1", ids)
            self.assertNotIn("en1", ids)
            self.assertEqual(stats["descartados_idioma"], 1)

    def test_desactivado_conserva_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = yt_discover.descubrir(
                out_dir=tmp, n_por_consulta=2, pausa=0.0,
                max_consultas=1, solo_espanol=False,
                clase_ydl=_doble(self._respuestas()))
            with open(os.path.join(tmp, "catalogo.jsonl"), encoding="utf-8") as fh:
                ids = [json.loads(l)["id"] for l in fh if l.strip()]
            self.assertIn("es1", ids)
            self.assertIn("en1", ids)
            self.assertEqual(stats.get("descartados_idioma", 0), 0)


if __name__ == "__main__":
    unittest.main()
