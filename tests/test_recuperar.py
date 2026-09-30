import json

import pytest

import recuperar


@pytest.mark.lento
def test_contrato_de_salida(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    lineas = open("datos/preguntas_recuperacion_dev.jsonl", encoding="utf-8").read().splitlines()[:3]
    preguntas.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    salida = tmp_path / "r.jsonl"

    recuperar.main(["--preguntas", str(preguntas), "--salida", str(salida), "--encoder", "minilm", "--k", "2"])

    filas = [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines()]
    assert [f["id"] for f in filas] == ["R01", "R02", "R03"]
    for f in filas:
        assert set(f) == {"id", "fragmentos"}
        assert 1 <= len(f["fragmentos"]) <= 2
        assert all(isinstance(t, str) and t for t in f["fragmentos"])


def test_interfaz_acordada_con_la_parte_2():
    # specs/parte2-agente.md: herramientas/documentos.py busca recuperar.buscar(consulta, top_k=None)
    import inspect
    params = inspect.signature(recuperar.buscar).parameters
    assert list(params) == ["consulta", "top_k"] and params["top_k"].default is None


@pytest.mark.lento
def test_buscar_devuelve_texto_crudo_del_corpus():
    frags = recuperar.buscar("¿Cuántas sesiones de kinesio cubre una orden?", top_k=2)
    assert len(frags) == 2 and all(isinstance(f, str) for f in frags)
    assert "un máximo de 10 sesiones" in frags[0]


def test_config_entregada_es_valida():
    cfg = recuperar.leer_config()
    from rag.chunking import CHUNKERS
    from rag.embeddings import ENCODERS
    assert cfg["encoder"] in ENCODERS and cfg["chunking"] in CHUNKERS and cfg["k"] >= 1
