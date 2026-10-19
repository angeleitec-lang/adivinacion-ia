"""Tests de merge_final: extraccion del tema del prompt y descarte de pares basura."""
import os
import json
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from merge_final import extraer_tema, is_junk_pair, fusionar, lang_counts
from validate_synthetic import sha


def fila(human: str, gpt: str) -> dict:
    return {"conversations": [
        {"from": "human", "value": human},
        {"from": "gpt", "value": gpt},
    ]}


def fila_multi(pares: list) -> dict:
    msgs = []
    for h, g in pares:
        msgs.append({"from": "human", "value": h})
        msgs.append({"from": "gpt", "value": g})
    return {"conversations": msgs, "turnos": len(pares)}


RESPUESTA_VALIDA = ("El tarot es una baraja de 78 cartas; el arcano mayor "
                   "representa arquetipos del camino del alma.")


class TestExtraerTema(unittest.TestCase):
    def test_plantilla_dos_puntos(self):
        self.assertEqual(extraer_tema("Explica en detalle: Sección 3."), "Sección 3")

    def test_plantilla_que_significa(self):
        self.assertEqual(extraer_tema("¿Qué significa Referencias?"), "Referencias")

    def test_plantilla_expliname_de_forma(self):
        self.assertEqual(
            extraer_tema("Explícame El Loco de forma clara y completa."), "El Loco")

    def test_plantilla_habla_de(self):
        self.assertEqual(extraer_tema("Háblame del Tarot de Marsella."), "Tarot de Marsella")

    def test_plantilla_desarrollame(self):
        self.assertEqual(
            extraer_tema("Como experta en adivinación, desarróllame la carta El Colgado."),
            "la carta El Colgado")

    def test_sin_plantilla_frase_completa(self):
        self.assertEqual(extraer_tema("el tarot de marsella"), "el tarot de marsella")

    def test_tema_con_separador_mayor(self):
        self.assertEqual(
            extraer_tema("Explica en detalle: Arcanos > El Loco."), "Arcanos > El Loco")


class TestIsJunkPair(unittest.TestCase):
    def test_seccion_es_junk(self):
        self.assertTrue(is_junk_pair(fila("Explica en detalle: Sección 3.", RESPUESTA_VALIDA)))

    def test_referencias_es_junk(self):
        self.assertTrue(is_junk_pair(fila("¿Qué significa Referencias?", RESPUESTA_VALIDA)))

    def test_segmento_malo_en_jerarquia_es_junk(self):
        self.assertTrue(is_junk_pair(
            fila("Explica en detalle: El Loco > Referencias.", RESPUESTA_VALIDA)))

    def test_tema_valido_no_es_junk(self):
        self.assertFalse(is_junk_pair(
            fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA)))

    def test_tema_corto_es_junk(self):
        self.assertTrue(is_junk_pair(fila("¿Qué significa X?", RESPUESTA_VALIDA)))

    def test_tema_vacio_es_junk(self):
        self.assertTrue(is_junk_pair(fila("", RESPUESTA_VALIDA)))

    def test_sin_terminos_de_dominio_es_junk(self):
        self.assertTrue(is_junk_pair(
            fila("Explícame El Loco de forma clara y completa.", "Texto sin anclaje alguno.")))

    def test_seccion_numerada_en_texto_humano_sigue_descartando(self):
        self.assertTrue(is_junk_pair(
            fila("Háblame de la Sección 12 del manual.", RESPUESTA_VALIDA)))


def respuestas(rows):
    return [r["conversations"][1]["value"] for r in rows]


class TestFusionar(unittest.TestCase):
    def setUp(self):
        self.cfg = {"seed": 42, "train_ratio": 0.8, "val_ratio": 0.1, "include_en": False}

    def test_claves_descartes(self):
        res = fusionar([], [], [], [], self.cfg)
        self.assertEqual(
            set(res["report"]["descartes"]),
            {"junk", "duplicado_exacto", "duplicado_prefijo", "idioma"})

    def test_report_conserva_claves_antiguas(self):
        res = fusionar([], [], [], [], self.cfg)
        for k in ("real_train_in", "real_val_in", "real_train_kept", "real_val_kept",
                 "synth_in", "synth_dups_vs_real", "synth_kept", "split", "blocks", "langs"):
            self.assertIn(k, res["report"])

    def test_val_real_se_divide_mitad(self):
        val = [fila(f"Explícame tema{i} de forma clara y completa.",
                   RESPUESTA_VALIDA + f" Nota {i}.") for i in range(20)]
        res = fusionar([], val, [], [], self.cfg)
        self.assertEqual(len(res["val"]) + len(res["test"]), 20)
        self.assertGreater(len(res["val"]), 0)
        self.assertGreater(len(res["test"]), 0)

    def test_particion_determinista(self):
        val = [fila(f"Explícame tema{i} de forma clara y completa.",
                   RESPUESTA_VALIDA + f" Nota {i}.") for i in range(20)]
        r1 = fusionar([], val, [], [], self.cfg)
        r2 = fusionar([], val, [], [], self.cfg)
        self.assertEqual(respuestas(r1["val"]), respuestas(r2["val"]))
        self.assertEqual(respuestas(r1["test"]), respuestas(r2["test"]))

    def test_mismo_prompt_mismo_lado(self):
        a = fila("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA)
        b = fila("Explícame El Colgado de forma clara y completa.",
                RESPUESTA_VALIDA + " Además, invita a la introspección profunda.")
        res = fusionar([], [a, b], [], [], self.cfg)
        en_val = all(r in res["val"] for r in (a, b))
        en_test = all(r in res["test"] for r in (a, b))
        self.assertTrue(en_val or en_test)

    def test_dedupe_exacto_val_contra_train(self):
        t = fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA)
        v = fila("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA)
        res = fusionar([t], [v], [], [], self.cfg)
        self.assertEqual(len(res["val"]) + len(res["test"]), 0)
        self.assertEqual(res["report"]["descartes"]["duplicado_exacto"], 1)

    def test_dedupe_prefijo_val_contra_train(self):
        base = "x" * 300
        t = fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA + " " + base)
        v = fila("Explícame El Colgado de forma clara y completa.",
                RESPUESTA_VALIDA + " " + base + " y un final distinto tras el prefijo.")
        res = fusionar([t], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["duplicado_prefijo"], 1)
        self.assertEqual(len(res["val"]) + len(res["test"]), 0)

    def test_dedupe_prefijo_test_contra_train(self):
        base = "y" * 300
        t = fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA + " " + base)
        for i in range(100):
            h = f"Explícame tema{i} de forma clara y completa."
            if int(sha(h), 16) % 2 != 1:
                continue
            v = fila(h, RESPUESTA_VALIDA + " " + base +
                     " con un final que difiere tras los primeros doscientos caracteres.")
            res = fusionar([t], [v], [], [], self.cfg)
            self.assertEqual(len(res["test"]), 0)
            self.assertEqual(res["report"]["descartes"]["duplicado_prefijo"], 1)
            return
        self.fail("no se encontró un prompt que caiga en test")

    def test_descarte_idioma_real(self):
        v = fila("Explícame el tarot y los arcanos de forma clara.",
                "The Fool represents new beginnings and spontaneous potential in the deck.")
        res = fusionar([], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["idioma"], 1)
        self.assertEqual(len(res["val"]) + len(res["test"]), 0)

    def test_include_en_conserva_ingles(self):
        cfg = dict(self.cfg, include_en=True)
        v = fila("Explícame el tarot y los arcanos de forma clara.",
                "The Fool represents new beginnings and spontaneous potential in the deck.")
        res = fusionar([], [v], [], [], cfg)
        self.assertEqual(res["report"]["descartes"]["idioma"], 0)
        self.assertEqual(len(res["val"]) + len(res["test"]), 1)

    def test_descarte_junk_real(self):
        t = fila("Explica en detalle: Sección 3.", RESPUESTA_VALIDA)
        res = fusionar([t], [], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["junk"], 1)
        self.assertEqual(len(res["train"]), 0)

    def test_blocks_por_split(self):
        real_t = fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA)
        synth = [fila(f"Explícame variante{i} de forma clara y completa.",
                     RESPUESTA_VALIDA + f" Detalle {i}.") for i in range(20)]
        meta = [{"block": "tarot"}] * 10 + [{"block": "astrologia"}] * 10
        res = fusionar([real_t], [], synth, meta, self.cfg)
        bps = res["report"]["blocks_por_split"]
        self.assertEqual(bps["train"]["real"], 1)
        for bloque in ("tarot", "astrologia"):
            total = sum(bps[s].get(bloque, 0) for s in ("train", "val", "test"))
            self.assertEqual(total, 10)

    def test_synth_dup_vs_real(self):
        real_t = fila("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA)
        synth = [fila("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA)]
        meta = [{"block": "tarot"}]
        res = fusionar([real_t], [], synth, meta, self.cfg)
        self.assertEqual(res["report"]["synth_dups_vs_real"], 1)
        self.assertEqual(res["report"]["descartes"]["duplicado_exacto"], 1)
        self.assertEqual(len(res["train"]), 1)


class TestMultiTurnoFusion(unittest.TestCase):
    def setUp(self):
        self.cfg = {"seed": 42, "train_ratio": 0.8, "val_ratio": 0.1, "include_en": False}

    def test_junk_en_turno_dos_descarta(self):
        f = fila_multi([
            ("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA),
            ("Explica en detalle: Sección 3.", RESPUESTA_VALIDA),
        ])
        self.assertTrue(is_junk_pair(f))

    def test_multi_turno_bueno_no_es_junk(self):
        f = fila_multi([
            ("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA),
            ("¿Y qué me dice el tarot sobre el Ermitaño?", RESPUESTA_VALIDA),
        ])
        self.assertFalse(is_junk_pair(f))

    def test_idioma_detecta_turno_dos_ingles(self):
        v = fila_multi([
            ("Explícame el tarot de forma clara.", RESPUESTA_VALIDA),
            ("¿Y el Ermitaño?",
             "The Hermit is a card of the tarot that, like palmistry reads the hand, "
             "represents introspection and inner search in the Marseille tradition."),
        ])
        res = fusionar([], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["idioma"], 1)
        self.assertEqual(len(res["val"]) + len(res["test"]), 0)

    def test_lang_counts_considera_todas_las_respuestas(self):
        f = fila_multi([
            ("Explícame el tarot.", RESPUESTA_VALIDA),
            ("Seguimiento", RESPUESTA_VALIDA + " y una segunda lectura del arcano."),
        ])
        c = lang_counts([f])
        self.assertEqual(c.get("es"), 2)

    def test_misma_gpt1_distinta_gpt2_no_duplicada(self):
        t = fila_multi([
            ("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA),
            ("Seguimiento uno", RESPUESTA_VALIDA + " El Loco invita a empezar de cero."),
        ])
        v = fila_multi([
            ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA),
            ("Seguimiento dos", RESPUESTA_VALIDA + " El Colgado pide pausa y perspectiva."),
        ])
        res = fusionar([t], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["duplicado_exacto"], 0)
        self.assertEqual(len(res["val"]) + len(res["test"]), 1)

    def test_multi_turno_identica_si_es_duplicada(self):
        par = [("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA),
               ("Seguimiento", RESPUESTA_VALIDA + " cierre idéntico del arcano.")]
        t = fila_multi(par)
        v = fila_multi(list(par))
        res = fusionar([t], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["duplicado_exacto"], 1)

    def test_dedupe_prefijo_multi_turno(self):
        base = "z" * 300
        t = fila_multi([
            ("Explícame El Loco de forma clara y completa.", RESPUESTA_VALIDA + " " + base),
            ("Seguimiento", RESPUESTA_VALIDA),
        ])
        v = fila_multi([
            ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA + " " + base),
            ("Seguimiento", RESPUESTA_VALIDA + " final distinto tras el prefijo comun."),
        ])
        res = fusionar([t], [v], [], [], self.cfg)
        self.assertEqual(res["report"]["descartes"]["duplicado_prefijo"], 1)
        self.assertEqual(len(res["val"]) + len(res["test"]), 0)


class TestRepartoSinFuga(unittest.TestCase):
    def setUp(self):
        self.cfg = {"seed": 42, "train_ratio": 0.8, "val_ratio": 0.1, "include_en": False}

    def test_val_real_mismo_primer_human_mismo_lado(self):
        a = fila_multi([
            ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA),
            ("Seguimiento A", RESPUESTA_VALIDA + " Variante A del seguimiento con mas texto."),
        ])
        b = fila_multi([
            ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA),
            ("Seguimiento B", RESPUESTA_VALIDA + " Variante B del seguimiento con otro texto."),
        ])
        res = fusionar([], [a, b], [], [], self.cfg)
        en_val = a in res["val"] and b in res["val"]
        en_test = a in res["test"] and b in res["test"]
        self.assertTrue(en_val or en_test)

    def test_synth_mismo_primer_human_mismo_split(self):
        par1 = ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA)
        s1 = fila_multi([par1, ("Seguimiento A", RESPUESTA_VALIDA + " texto A distinto.")])
        s2 = fila_multi([par1, ("Seguimiento B", RESPUESTA_VALIDA + " texto B distinto.")])
        synth = [s1, s2]
        meta = [{"block": "tarot"}, {"block": "tarot"}]
        res = fusionar([], [], synth, meta, self.cfg)
        en_train = all(r in res["train"] for r in synth)
        en_val = all(r in res["val"] for r in synth)
        en_test = all(r in res["test"] for r in synth)
        self.assertTrue(en_train or en_val or en_test)

    def test_synth_distinto_human_puede_repartirse(self):
        synth = [fila(f"Explícame tema{i} de forma clara y completa.",
                     RESPUESTA_VALIDA + f" Detalle {i}.") for i in range(20)]
        meta = [{"block": "tarot"}] * 20
        res = fusionar([], [], synth, meta, self.cfg)
        self.assertGreater(len(res["train"]), 0)
        self.assertGreater(len(res["val"]) + len(res["test"]), 0)


class TestE2EDirectorioTemporal(unittest.TestCase):
    def test_seis_filas_end_to_end(self):
        from merge_final import main
        filas = [
            fila("Explícame El Loco de forma clara y completa.",
                 RESPUESTA_VALIDA + " Uno."),
            fila("Explícame La Luna de forma clara y completa.",
                 RESPUESTA_VALIDA + " Dos."),
            fila("Explícame El Sol de forma clara y completa.",
                 RESPUESTA_VALIDA + " Tres."),
            fila_multi([
                ("Explícame El Colgado de forma clara y completa.", RESPUESTA_VALIDA),
                ("¿Y su invertida?", RESPUESTA_VALIDA + " Invertida."),
            ]),
            fila_multi([
                ("Explícame El Carro de forma clara y completa.", RESPUESTA_VALIDA),
                ("Explica en detalle: Sección 3.", RESPUESTA_VALIDA),
            ]),
            fila("Explícame El Loco de forma clara y completa.",
                 RESPUESTA_VALIDA + " Uno."),
        ]
        with tempfile.TemporaryDirectory() as td:
            rt = os.path.join(td, "real_train.jsonl")
            with open(rt, "w", encoding="utf-8") as f:
                for r in filas:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out = os.path.join(td, "final")
            main(["--real-train", rt, "--real-val", os.path.join(td, "none.jsonl"),
                 "--synth", os.path.join(td, "none.jsonl"),
                 "--synth-meta", os.path.join(td, "none.meta.jsonl"),
                 "--out-dir", out])
            train = [json.loads(l) for l in
                     open(os.path.join(out, "train.jsonl"), encoding="utf-8") if l.strip()]
            rep = json.load(open(os.path.join(out, "report.json"), encoding="utf-8"))
            self.assertEqual(len(train), 4)
            self.assertEqual(rep["descartes"]["junk"], 1)
            self.assertEqual(rep["descartes"]["duplicado_exacto"], 1)
            self.assertEqual(rep["real_train_kept"], 4)


if __name__ == "__main__":
    unittest.main()
