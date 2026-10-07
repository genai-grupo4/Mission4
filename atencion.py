"""Parte 4: una capa de atencion de transformer, solo con NumPy.

Contrato en atencion/test_atencion.py; diseño en specs/parte4-atencion.md.
"""
import numpy as np


def softmax(M):
    """Softmax sobre el ultimo eje. Resta el maximo de cada fila para no desbordar exp."""
    M = np.asarray(M, dtype=float)
    e = np.exp(M - M.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)
