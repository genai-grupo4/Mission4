"""Parte 1: recuperador vectorial sobre datos/corpus/.

    python3 recuperar.py --preguntas datos/preguntas_recuperacion_dev.jsonl --salida resultados.jsonl

La configuración entregada está fija en config_recuperador.json. Los flags opcionales
(--encoder, --chunking, --k, ...) solo se usan para correr los experimentos.

Para las partes 2 y 3: `from recuperar import recuperar` y `recuperar("pregunta")`.
"""
import argparse
import json
from pathlib import Path

from rag.chunking import cargar_corpus, fragmentar
from rag.embeddings import cargar_encoder
from rag.indice import buscar

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config_recuperador.json"
CORPUS = RAIZ / "datos" / "corpus"


def leer_config(path=CONFIG, **cambios):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg.update({k: v for k, v in cambios.items() if v is not None})
    return cfg


class Recuperador:
    def __init__(self, cfg, encoder=None):
        self.cfg = cfg
        self.encoder = encoder or cargar_encoder(cfg["encoder"])
        self.fragmentos = fragmentar(cargar_corpus(CORPUS), cfg["chunking"])
        self.emb = self.encoder.pasajes([f.para_embeber(cfg.get("metadatos", False)) for f in self.fragmentos])
        self.reranker = None
        if cfg.get("reranker"):
            from sentence_transformers import CrossEncoder
            self.reranker = CrossEncoder(cfg["reranker"], device="cpu")

    def buscar_lote(self, consultas, k=None):
        cfg = self.cfg
        k = k or cfg["k"]
        qs = self.encoder.consultas(consultas)
        salida = []
        for consulta, q in zip(consultas, qs):
            if self.reranker:
                # el cross-encoder reordena los mejores candidatos del coseno y se queda con k
                cand, _ = buscar(q, self.emb, k=cfg.get("candidatos", 10))
                puntajes = self.reranker.predict([(consulta, self.fragmentos[i].texto) for i in cand])
                idx = [cand[i] for i in sorted(range(len(cand)), key=lambda i: -puntajes[i])[:k]]
            else:
                idx, _ = buscar(q, self.emb, k=k, umbral=cfg.get("umbral"), margen=cfg.get("margen"))
            salida.append([self.fragmentos[i].texto for i in idx])
        return salida


_recuperador = None


def recuperar(consulta, k=None):
    """Fragmentos más relevantes para una consulta, con la configuración entregada."""
    global _recuperador
    if _recuperador is None:
        _recuperador = Recuperador(leer_config())
    return _recuperador.buscar_lote([consulta], k=k)[0]


def correr(preguntas, salida, recuperador):
    filas = [json.loads(l) for l in Path(preguntas).read_text(encoding="utf-8").splitlines() if l.strip()]
    resultados = recuperador.buscar_lote([p["pregunta"] for p in filas])
    with open(salida, "w", encoding="utf-8") as f:
        for p, frags in zip(filas, resultados):
            f.write(json.dumps({"id": p["id"], "fragmentos": frags}, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preguntas", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--encoder")
    ap.add_argument("--chunking")
    ap.add_argument("--k", type=int)
    ap.add_argument("--umbral", type=float)
    ap.add_argument("--margen", type=float)
    ap.add_argument("--metadatos", action=argparse.BooleanOptionalAction, default=None)
    args = ap.parse_args(argv)
    cfg = leer_config(args.config, encoder=args.encoder, chunking=args.chunking, k=args.k,
                      umbral=args.umbral, margen=args.margen, metadatos=args.metadatos)
    correr(args.preguntas, args.salida, Recuperador(cfg))


if __name__ == "__main__":
    main()
