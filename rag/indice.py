"""Búsqueda por similitud coseno en memoria (el corpus es chico, no hace falta una vector DB)."""
import numpy as np


def normalizar(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.linalg.norm(x, axis=-1, keepdims=True).clip(min=1e-12)


def buscar(q, emb, k, umbral=None, margen=None):
    """Top-k por coseno. `q` y `emb` ya normalizados.

    - umbral: descarta fragmentos con coseno < umbral.
    - margen: descarta fragmentos con coseno < (coseno del mejor - margen).
    El mejor fragmento se devuelve siempre: una lista vacía vale 0 en el evaluador.
    """
    sims = emb @ q
    orden = np.argsort(-sims, kind="stable")[:k]
    mejor = sims[orden[0]]
    elegidos = [orden[0]] + [i for i in orden[1:]
                            if (umbral is None or sims[i] >= umbral)
                            and (margen is None or sims[i] >= mejor - margen)]
    elegidos = np.array(elegidos)
    return elegidos, sims[elegidos]
