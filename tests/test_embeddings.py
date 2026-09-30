import numpy as np
import pytest

from rag.embeddings import ENCODERS, cargar_encoder

TEXTOS = ["Las visitas son de 16:00 a 20:00.", "Se requiere ayuno de 8 horas.", "El estacionamiento es gratuito."]


def test_encoders_declarados():
    # baseline obligatoria + al menos dos de sentence embeddings
    assert ENCODERS["beto"]["tipo"] == "bert_mean"
    assert sum(e["tipo"] == "sentence" for e in ENCODERS.values()) >= 2


@pytest.mark.lento
@pytest.mark.parametrize("nombre", ["beto", "minilm", "e5small"])
def test_encoder_devuelve_vectores_unitarios(nombre):
    enc = cargar_encoder(nombre)
    pas = enc.pasajes(TEXTOS)
    q = enc.consultas(["¿A qué hora son las visitas?"])
    assert pas.shape[0] == 3 and q.shape == (1, pas.shape[1])
    assert np.allclose(np.linalg.norm(pas, axis=1), 1.0, atol=1e-4)
    if ENCODERS[nombre]["tipo"] == "sentence":
        # sanity: la pregunta sobre visitas se parece más al texto de visitas que al de estacionamiento
        # (a BERT sin ajustar no se le exige: justamente es la línea de base)
        sims = pas @ q[0]
        assert sims[0] > sims[2]


def test_prefijos_e5():
    assert ENCODERS["e5small"]["prefijo_consulta"] == "query: "
    assert ENCODERS["e5small"]["prefijo_pasaje"] == "passage: "
