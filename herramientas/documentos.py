"""Adaptador al recuperador de la parte 1.

Interfaz acordada con la parte 1 (ver `specs/parte2-agente.md`): `recuperar.py` expone, además
de su CLI, `buscar(consulta: str, top_k: int | None = None) -> list[str]`, que devuelve texto
crudo del corpus en orden de relevancia descendente.

Mientras `recuperar.py` no exista, se usa un stub que devuelve fragmentos marcados: la parte 2
corre end-to-end igual, y el día que aparezca el recuperador real no hay que tocar nada.
"""
import sys
from functools import lru_cache

TOP_K = 5

_ya_avisamos = False


@lru_cache(maxsize=1)
def _recuperador():
    try:
        import recuperar
    except Exception:
        return None
    return getattr(recuperar, "buscar", None)


def _avisar_stub():
    global _ya_avisamos
    if not _ya_avisamos:
        _ya_avisamos = True
        print(
            "AVISO: recuperar.buscar() no está disponible todavía; buscar_documentos usa el STUB "
            "de la parte 2. Los fragmentos NO son del corpus real.",
            file=sys.stderr,
        )


def _stub(consulta):
    return [
        f"[STUB parte 1] Fragmento {i} que respondería a: {consulta!r}. "
        "Reemplazar enchufando recuperar.buscar()."
        for i in range(1, 4)
    ]


def buscar(consulta, top_k=None):
    """Fragmentos del corpus del hospital más relevantes para `consulta`, más relevante primero."""
    recuperar_buscar = _recuperador()
    if recuperar_buscar is None:
        _avisar_stub()
        return _stub(consulta)
    try:
        return list(recuperar_buscar(consulta, top_k=TOP_K if top_k is None else top_k))
    except Exception as e:
        return [f"(error del recuperador de documentos: {e})"]
