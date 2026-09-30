"""Encoders a comparar. Todos devuelven embeddings normalizados (norma 1) para usar coseno como producto punto."""
import numpy as np

from rag.indice import normalizar

ENCODERS = {
    # Línea de base obligatoria: BERT sin ajustar para similitud, promedio de tokens de la última capa.
    "beto": {"modelo": "dccuchile/bert-base-spanish-wwm-cased", "tipo": "bert_mean"},
    "mbert": {"modelo": "google-bert/bert-base-multilingual-cased", "tipo": "bert_mean"},
    # Modelos entrenados para embeddings de oraciones.
    "minilm": {"modelo": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "tipo": "sentence"},
    "e5small": {"modelo": "intfloat/multilingual-e5-small", "tipo": "sentence",
                "prefijo_consulta": "query: ", "prefijo_pasaje": "passage: "},
    "e5base": {"modelo": "intfloat/multilingual-e5-base", "tipo": "sentence",
               "prefijo_consulta": "query: ", "prefijo_pasaje": "passage: "},
    "bgem3": {"modelo": "BAAI/bge-m3", "tipo": "sentence"},
}


class EncoderBertMean:
    def __init__(self, modelo):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(modelo)
        self.model = AutoModel.from_pretrained(modelo).eval()

    def _encode(self, textos, lote=16):
        salida = []
        with self.torch.no_grad():
            for i in range(0, len(textos), lote):
                b = self.tok(textos[i:i + lote], padding=True, truncation=True, max_length=512, return_tensors="pt")
                h = self.model(**b).last_hidden_state              # (lote, tokens, 768)
                m = b["attention_mask"].unsqueeze(-1).float()      # no promediar el padding
                salida.append(((h * m).sum(1) / m.sum(1)).numpy())
        return normalizar(np.concatenate(salida))

    def consultas(self, textos):
        return self._encode(textos)

    def pasajes(self, textos):
        return self._encode(textos)


class EncoderSentence:
    def __init__(self, modelo, prefijo_consulta="", prefijo_pasaje=""):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(modelo, device="cpu")
        self.pq, self.pp = prefijo_consulta, prefijo_pasaje

    def _encode(self, textos):
        return normalizar(self.model.encode(textos, batch_size=16, normalize_embeddings=True))

    def consultas(self, textos):
        return self._encode([self.pq + t for t in textos])

    def pasajes(self, textos):
        return self._encode([self.pp + t for t in textos])


def cargar_encoder(nombre):
    cfg = ENCODERS[nombre]
    if cfg["tipo"] == "bert_mean":
        return EncoderBertMean(cfg["modelo"])
    return EncoderSentence(cfg["modelo"], cfg.get("prefijo_consulta", ""), cfg.get("prefijo_pasaje", ""))
