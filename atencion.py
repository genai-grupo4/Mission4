"""Parte 4: una capa de atencion de transformer, solo con NumPy.

Contrato en atencion/test_atencion.py; diseño en specs/parte4-atencion.md.
"""
import numpy as np


def softmax(M):
    """Softmax sobre el ultimo eje. Resta el maximo de cada fila para no desbordar exp."""
    M = np.asarray(M, dtype=float)
    e = np.exp(M - M.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def atencion(Q, K, V, mascara=False):
    """Atencion escalada: A = softmax(Q K^T / sqrt(d_k)), salida = A V.

    Con mascara=True cada posicion i solo ve las posiciones j <= i (mascara causal).
    """
    Q, K, V = (np.asarray(M, dtype=float) for M in (Q, K, V))
    puntajes = Q @ K.T / np.sqrt(K.shape[-1])
    if mascara:
        futuro = np.triu(np.ones(puntajes.shape, dtype=bool), k=1)
        puntajes = np.where(futuro, -np.inf, puntajes)
    A = softmax(puntajes)
    return A @ V, A


def autoatencion(X, Wq, Wk, Wv, mascara=False):
    """Proyecta X a Q, K y V y aplica atencion sobre la misma secuencia."""
    X = np.asarray(X, dtype=float)
    return atencion(X @ Wq, X @ Wk, X @ Wv, mascara=mascara)
