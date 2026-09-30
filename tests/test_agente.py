"""Tests del loop del agente y del CLI, contra un modelo falso (sin red, sin costo)."""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

import agente


class ModeloFalso:
    """Devuelve mensajes scripteados y recuerda lo que le mandaron."""

    def __init__(self, *mensajes):
        self.pendientes = list(mensajes)
        self.recibidos = []

    def invoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.pendientes.pop(0)


def _ai(texto="", tool_calls=(), entrada=100, salida=20):
    return AIMessage(
        content=texto,
        tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(tool_calls)],
        usage_metadata={"input_tokens": entrada, "output_tokens": salida, "total_tokens": entrada + salida},
    )


@tool
def herramienta_falsa(valor: str) -> str:
    """Devuelve un resultado de prueba."""
    return f"resultado de {valor}"


CATALOGO = {"herramienta_falsa": herramienta_falsa}


def test_sin_tool_calls_contesta_directo():
    modelo = ModeloFalso(_ai("Hola"))
    t = agente.responder(modelo, "A01", "¿Hola?", CATALOGO)
    assert t.respuesta == "Hola"
    assert t.llamadas == []
    assert t.herramientas == []


def test_ejecuta_la_tool_y_vuelve_al_modelo_con_el_resultado():
    modelo = ModeloFalso(
        _ai(tool_calls=[("herramienta_falsa", {"valor": "x"})]),
        _ai("Listo"),
    )
    t = agente.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert t.respuesta == "Listo"
    assert t.llamadas[0].nombre == "herramienta_falsa"
    assert t.llamadas[0].argumentos == {"valor": "x"}
    assert t.llamadas[0].resultado == "resultado de x"
    ultimos = modelo.recibidos[-1]
    assert isinstance(ultimos[-1], ToolMessage) and ultimos[-1].content == "resultado de x"


def test_el_primer_mensaje_es_el_system_prompt_y_despues_la_pregunta():
    modelo = ModeloFalso(_ai("ok"))
    agente.responder(modelo, "A01", "¿Cuál es el horario?", CATALOGO)
    m = modelo.recibidos[0]
    assert isinstance(m[0], SystemMessage) and isinstance(m[1], HumanMessage)
    assert m[1].content == "¿Cuál es el horario?"


def test_registra_el_usage_de_cada_llamada_al_modelo():
    modelo = ModeloFalso(
        _ai(tool_calls=[("herramienta_falsa", {"valor": "x"})], entrada=100, salida=20),
        _ai("Listo", entrada=300, salida=40),
    )
    t = agente.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert [(u.tokens_entrada, u.tokens_salida) for u in t.usos] == [(100, 20), (300, 40)]


def test_varias_llamadas_a_la_misma_tool_dan_un_solo_nombre_pero_dos_contextos():
    modelo = ModeloFalso(
        _ai(tool_calls=[("herramienta_falsa", {"valor": "x"})]),
        _ai(tool_calls=[("herramienta_falsa", {"valor": "y"})]),
        _ai("Listo"),
    )
    t = agente.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert t.herramientas == ["herramienta_falsa"]
    assert len(t.contextos) == 2


def test_una_tool_inexistente_no_rompe_el_loop():
    modelo = ModeloFalso(_ai(tool_calls=[("no_existe", {})]), _ai("Perdón"))
    t = agente.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert "no_existe" in t.llamadas[0].resultado
    assert t.respuesta == "Perdón"


def test_corta_en_max_vueltas_y_lo_deja_anotado():
    modelo = ModeloFalso(*[_ai(tool_calls=[("herramienta_falsa", {"valor": "x"})]) for _ in range(10)])
    t = agente.responder(modelo, "A02", "¿Y?", CATALOGO, max_vueltas=3)
    assert len(t.llamadas) == 3
    assert "vueltas" in (t.error or "")


def test_un_modelo_que_explota_deja_la_traza_con_error():
    class Explota:
        def invoke(self, mensajes):
            raise RuntimeError("503 de OpenRouter")

    t = agente.responder(Explota(), "A03", "¿Y?", CATALOGO)
    assert "503 de OpenRouter" in t.error
    assert t.respuesta == ""


def test_el_jsonl_de_salida_tiene_exactamente_los_campos_del_contrato(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(
        json.dumps({"id": "A01", "pregunta": "¿Hola?", "herramientas_esperadas": ["x"],
                    "respuesta_referencia": "no mirar"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    salida = tmp_path / "r.jsonl"
    agente.correr(preguntas, salida, lambda: ModeloFalso(_ai("Hola")), tmp_path / "log.md", CATALOGO)
    linea = json.loads(salida.read_text(encoding="utf-8").strip())
    assert set(linea) == {"id", "respuesta", "contextos", "herramientas"}
    assert linea["id"] == "A01" and linea["respuesta"] == "Hola"


def test_la_salida_tiene_una_linea_por_pregunta_y_en_orden(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(
        "\n".join(json.dumps({"id": f"A0{i}", "pregunta": f"p{i}"}) for i in (1, 2, 3)),
        encoding="utf-8",
    )
    salida = tmp_path / "r.jsonl"
    agente.correr(preguntas, salida, lambda: ModeloFalso(_ai("a"), _ai("b"), _ai("c")),
                  tmp_path / "log.md", CATALOGO)
    ids = [json.loads(l)["id"] for l in salida.read_text(encoding="utf-8").splitlines()]
    assert ids == ["A01", "A02", "A03"]


def test_la_corrida_escribe_el_log_md(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(json.dumps({"id": "A01", "pregunta": "¿Hola?"}), encoding="utf-8")
    log = tmp_path / "log.md"
    agente.correr(preguntas, tmp_path / "r.jsonl", lambda: ModeloFalso(_ai("Hola")), log, CATALOGO)
    assert "A01" in log.read_text(encoding="utf-8")


def test_construir_modelo_exige_la_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        agente.construir_modelo()


def test_construir_modelo_apunta_a_openrouter_con_las_seis_tools(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    modelo = agente.construir_modelo()
    assert modelo.bound.model_name == "deepseek/deepseek-v4-flash-0731"
    assert str(modelo.bound.openai_api_base) == "https://openrouter.ai/api/v1"
    assert modelo.bound.temperature == 0
    assert len(modelo.kwargs["tools"]) == 6
