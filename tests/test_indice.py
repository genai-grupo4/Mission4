import numpy as np

from rag.indice import buscar, normalizar

EMB = normalizar(np.array([
    [1.0, 0.0, 0.0],
    [0.8, 0.6, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
]))
Q = normalizar(np.array([1.0, 0.1, 0.0]))


def test_normalizar_deja_norma_uno():
    assert np.allclose(np.linalg.norm(EMB, axis=1), 1.0)


def test_buscar_ordena_por_similitud_descendente():
    idx, sims = buscar(Q, EMB, k=4)
    assert list(idx) == [0, 1, 2, 3]
    assert all(sims[i] >= sims[i + 1] for i in range(len(sims) - 1))


def test_buscar_respeta_top_k():
    idx, _ = buscar(Q, EMB, k=2)
    assert list(idx) == [0, 1]


def test_umbral_descarta_pero_siempre_deja_el_mejor():
    idx, sims = buscar(Q, EMB, k=4, umbral=0.5)
    assert list(idx) == [0, 1] and all(s >= 0.5 for s in sims)
    idx, _ = buscar(Q, EMB, k=4, umbral=0.999)
    assert list(idx) == [0]


def test_margen_relativo_al_mejor():
    # sims ~ [0.995, 0.856, 0.0995, 0]; margen 0.2 deja solo los que están a <=0.2 del primero
    idx, _ = buscar(Q, EMB, k=4, margen=0.2)
    assert list(idx) == [0, 1]
    idx, _ = buscar(Q, EMB, k=4, margen=0.1)
    assert list(idx) == [0]
