"""Tests del adaptador al recuperador de la parte 1.

La parte 1 todavía no existe: el adaptador tiene que usarla cuando aparezca y caer a un
stub mientras tanto, sin que la parte 2 se entere.
"""
import sys
import types

import pytest

from herramientas import documentos


@pytest.fixture(autouse=True)
def _limpiar_estado():
    documentos._recuperador.cache_clear()
    documentos._ya_avisamos = False
    yield
    documentos._recuperador.cache_clear()
    documentos._ya_avisamos = False


def _modulo_recuperar_falso(fragmentos, registro=None):
    mod = types.ModuleType("recuperar")

    def buscar(consulta, top_k=None):
        if registro is not None:
            registro.append((consulta, top_k))
        return fragmentos

    mod.buscar = buscar
    return mod


def test_usa_recuperar_buscar_cuando_el_modulo_existe(monkeypatch):
    registro = []
    monkeypatch.setitem(sys.modules, "recuperar", _modulo_recuperar_falso(["frag A", "frag B"], registro))
    assert documentos.buscar("horario de visita") == ["frag A", "frag B"]
    assert registro == [("horario de visita", documentos.TOP_K)]


def test_cae_al_stub_cuando_recuperar_no_existe(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "recuperar", None)
    fragmentos = documentos.buscar("horario de visita")
    assert fragmentos and all(isinstance(f, str) for f in fragmentos)
    assert "STUB" in capsys.readouterr().err


def test_el_stub_avisa_una_sola_vez(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "recuperar", None)
    documentos.buscar("una")
    documentos.buscar("otra")
    assert capsys.readouterr().err.count("STUB") == 1


def test_el_stub_deja_claro_en_el_texto_que_no_es_el_corpus_real(monkeypatch):
    monkeypatch.setitem(sys.modules, "recuperar", None)
    assert all("STUB" in f for f in documentos.buscar("colonoscopia"))


def test_un_recuperador_roto_no_tumba_al_agente(monkeypatch):
    mod = types.ModuleType("recuperar")

    def buscar(consulta, top_k=None):
        raise RuntimeError("no se pudo cargar el encoder")

    mod.buscar = buscar
    monkeypatch.setitem(sys.modules, "recuperar", mod)
    fragmentos = documentos.buscar("colonoscopia")
    assert len(fragmentos) == 1
    assert "error" in fragmentos[0].lower()
