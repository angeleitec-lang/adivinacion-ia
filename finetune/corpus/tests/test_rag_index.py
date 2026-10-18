import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import rag_index


PARRAFO_TAROT = (
    "El As de Copas en una tirada de tarot simboliza el inicio emocional de un ciclo nuevo. "
    "Cuando aparece en la posición del pasado reciente, sugiere que una relación o una vivencia "
    "afectiva todavía influye en las decisiones presentes. En combinación con la Emperatriz, "
    "refuerza la idea de creatividad y fertilidad afectiva, mientras que junto al Cinco de Espadas "
    "advierte sobre malentendidos que conviene aclarar antes de actuar por impulso."
)


class TestChunkUtil(unittest.TestCase):
    def test_rechaza_boilerplate_whitelist(self):
        texto = ("Detecting... Please whitelist dirzon.es to continue reading the article about "
                 "tarot and divination, our system is checking your browser for security reasons.")
        self.assertFalse(rag_index.chunk_util(texto))

    def test_rechaza_enable_javascript(self):
        texto = ("Please enable javascript to view this page. We use cookies to improve your "
                 "experience on our site about la carta astral y los planetas en el zodíaco.")
        self.assertFalse(rag_index.chunk_util(texto))

    def test_rechaza_corto(self):
        self.assertFalse(rag_index.chunk_util("El tarot es una herramienta de introspección."))

    def test_rechaza_lleno_de_simbolos(self):
        texto = "|#*~^&=|% " * 30 + "http://ejemplo.com/pagina"
        self.assertFalse(rag_index.chunk_util(texto))

    def test_acepta_parrafo_real(self):
        self.assertTrue(rag_index.chunk_util(PARRAFO_TAROT))


class TestSplitChunks(unittest.TestCase):
    def test_tamanos_respetados(self):
        texto = "\n\n".join([PARRAFO_TAROT] * 8)
        chunks = rag_index.split_chunks(texto, chunk_size=500, overlap=100)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 500)

    def test_overlap_presente(self):
        texto = PARRAFO_TAROT * 6
        chunks = rag_index.split_chunks(texto, chunk_size=300, overlap=100)
        self.assertGreater(len(chunks), 2)
        # con overlap, el final de un chunk debe reaparecer al inicio del siguiente
        for a, b in zip(chunks, chunks[1:]):
            if len(a) == 300 and len(b) == 300:
                self.assertTrue(any(a[-50:][i:i + 20] in b for i in range(0, 31, 10)))


class TestEmbedParalelo(unittest.TestCase):
    def test_orden_con_servidor_falso(self):
        def falso_embed(texto):
            time.sleep(0.01)
            return [float(len(texto)), 1.0]

        textos = [f"texto-{i}" * (i + 1) for i in range(10)]
        res = rag_index.embed_paralelo(textos, falso_embed, workers=3)
        self.assertEqual(len(res), 10)
        for i, (vec, t) in enumerate(zip(res, textos)):
            self.assertEqual(vec[0], float(len(t)))

    def test_paralelismo_real(self):
        def lento(texto):
            time.sleep(0.15)
            return [1.0]

        inicio = time.time()
        res = rag_index.embed_paralelo(["a", "b", "c", "d"], lento, workers=4)
        duracion = time.time() - inicio
        self.assertEqual(len(res), 4)
        self.assertLess(duracion, 0.5)  # secuencial tardaría 0,6 s


class TestReanudacion(unittest.TestCase):
    def test_resume_solo_embelle_pendientes(self):
        llamadas = []
        lock = threading.Lock()

        def falso_embed(texto):
            with lock:
                llamadas.append(texto)
            return [float(len(texto))]

        items = [{"id": f"c{i}", "text": f"contenido {i}"} for i in range(10)]
        with tempfile.TemporaryDirectory() as tmp:
            parcial = os.path.join(tmp, "embeddings.partial.jsonl")
            # simular 5 ya embebidos
            import json as _json
            with open(parcial, "w", encoding="utf-8") as fh:
                for i in range(5):
                    fh.write(_json.dumps({"id": f"c{i}", "vec": [0.0]}) + "\n")

            hecho = rag_index.embed_con_reudo(items, falso_embed, workers=2,
                                            partial_path=parcial, resume=True)
            self.assertEqual(len(hecho), 10)
            self.assertEqual(len(llamadas), 5)
            self.assertEqual(sorted(llamadas), [f"contenido {i}" for i in range(5, 10)])

    def test_sin_resume_embelle_todo(self):
        def falso_embed(texto):
            return [1.0]

        items = [{"id": f"c{i}", "text": f"x{i}"} for i in range(4)]
        with tempfile.TemporaryDirectory() as tmp:
            parcial = os.path.join(tmp, "embeddings.partial.jsonl")
            hecho = rag_index.embed_con_reudo(items, falso_embed, workers=2,
                                             partial_path=parcial, resume=False)
            self.assertEqual(len(hecho), 4)


if __name__ == "__main__":
    unittest.main()
