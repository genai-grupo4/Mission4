"""Corre la matriz de experimentos de la parte 1 y evalúa cada configuración con evaluar/evaluar.py.

    python3 experimentos/correr_experimentos.py [etapa ...]

Cada configuración deja experimentos/<slug>.jsonl y experimentos/<slug>.jsonl.eval.json
(el .eval.json lo escribe el evaluador de la cátedra, sin tocar). Las ya evaluadas se saltean.
Al final regenera experimentos/tabla.md con una fila por configuración.
"""
import itertools
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from recuperar import Recuperador, correr  # noqa: E402
from rag.embeddings import cargar_encoder  # noqa: E402

EXP = RAIZ / "experimentos"
PREGUNTAS = RAIZ / "datos" / "preguntas_recuperacion_dev.jsonl"
CHUNKINGS = ["seccion", "parrafo", "oracion1", "oracion2", "oracion3", "ventana300", "ventana600"]


def cfg(encoder, chunking, k, umbral=None, margen=None, metadatos=False, reranker=None):
    return dict(encoder=encoder, chunking=chunking, k=k, umbral=umbral, margen=margen,
                metadatos=metadatos, reranker=reranker)


def slug(c):
    s = f"{c['encoder']}_{c['chunking']}{'_meta' if c['metadatos'] else ''}_k{c['k']}"
    if c["umbral"] is not None:
        s += f"_u{int(round(c['umbral'] * 100)):03d}"
    if c["margen"] is not None:
        s += f"_m{int(round(c['margen'] * 100)):03d}"
    if c["reranker"]:
        s += "_rerank"
    return s


# Etapa A: todos los encoders contra todos los chunkings, sin umbral, k chico y k grande.
ETAPA_A = [cfg(e, ch, k) for e, ch, k in itertools.product(
    ["beto", "mbert", "minilm", "e5small", "e5base", "bgem3"], CHUNKINGS, [1, 3])]

# Etapa B: metadatos (título + sección antepuestos al embeber) con los encoders de oraciones,
# y k=2 / margen relativo para ver si vale la pena devolver un segundo fragmento.
SENTENCE = ["minilm", "e5small", "e5base", "bgem3"]
CH_B = ["seccion", "parrafo", "oracion2", "oracion3", "ventana300", "ventana600"]
ETAPA_B = ([cfg(e, ch, 1, metadatos=True) for e, ch in itertools.product(SENTENCE, CH_B)]
           + [cfg(e, ch, 2, metadatos=m) for e, ch, m in itertools.product(["e5base", "bgem3"], ["seccion", "ventana600"], [False, True])]
           + [cfg(e, ch, 3, margen=mg, metadatos=True) for e, ch, mg in itertools.product(["e5base", "bgem3"], ["seccion", "ventana600"], [0.02, 0.05])]
           + [cfg("beto", ch, 1, metadatos=True) for ch in ["seccion", "ventana300"]])

# Etapa C: umbral absoluto de coseno (lo que pide la consigna) y reranking con cross-encoder.
RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
ETAPA_C = ([cfg(e, "seccion", 3, umbral=u, metadatos=True) for e, u in itertools.product(["e5base", "bgem3"], [0.5, 0.6, 0.7])]
           + [cfg(e, ch, 1, metadatos=True, reranker=RERANKER) for e, ch in itertools.product(["e5base", "bgem3"], ["seccion", "ventana600"])])

ETAPAS = {"A": ETAPA_A, "B": ETAPA_B, "C": ETAPA_C}


def correr_etapa(configs):
    encoders, recuperadores = {}, {}
    for c in configs:
        s = slug(c)
        salida = EXP / f"{s}.jsonl"
        if Path(f"{salida}.eval.json").exists():
            continue
        if c["encoder"] not in encoders:
            encoders.clear(); recuperadores.clear()  # liberar memoria: un encoder por vez
            encoders[c["encoder"]] = cargar_encoder(c["encoder"])
        clave = (c["chunking"], c["metadatos"], c["reranker"])
        if clave not in recuperadores:
            recuperadores[clave] = Recuperador(c, encoder=encoders[c["encoder"]])
        rec = recuperadores[clave]
        rec.cfg = c  # k/umbral/margen no cambian los embeddings
        correr(PREGUNTAS, salida, rec)
        subprocess.run([sys.executable, str(RAIZ / "evaluar" / "evaluar.py"), "recuperacion",
                        "--preguntas", str(PREGUNTAS), "--resultados", str(salida)],
                       check=True, capture_output=True)
        r = json.loads(Path(f"{salida}.eval.json").read_text(encoding="utf-8"))["resumen"]
        print(f"{s:45s} CR {r['context_relevance']:.4f}  R {r['recall']:.3f}  P {r['precision']:.3f}", flush=True)


def escribir_tabla():
    filas = []
    for ev in sorted(EXP.glob("*.jsonl.eval.json")):
        s = ev.name[: -len(".jsonl.eval.json")]
        r = json.loads(ev.read_text(encoding="utf-8"))["resumen"]
        filas.append((s, r))
    filas.sort(key=lambda x: -x[1]["context_relevance"])
    lineas = ["| # | Configuración (slug) | context_relevance | recall | precision | MRR | k medio | caracteres |",
              "|---|---|---|---|---|---|---|---|"]
    for i, (s, r) in enumerate(filas, 1):
        lineas.append(f"| {i} | [`{s}`]({s}.jsonl.eval.json) | {r['context_relevance']:.4f} | {r['recall']:.3f} | "
                      f"{r['precision']:.3f} | {r['mrr']:.3f} | {r['k']:.2f} | {r['caracteres']:.0f} |")
    (EXP / "tabla.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for etapa in sys.argv[1:] or list(ETAPAS):
        print(f"== etapa {etapa}")
        correr_etapa(ETAPAS[etapa])
    escribir_tabla()
