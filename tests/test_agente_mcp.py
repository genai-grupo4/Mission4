"""Tests del loop async de agente_mcp.py, contra un modelo y tools falsas (sin MCP real,
sin red). La integración real con servidor_mcp.py por stdio se prueba en test_servidor_mcp.py.
"""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

import agente_mcp


def _ai(texto="", tool_calls=(), entrada=100, salida=20):
    return AIMessage(
        content=texto,
        tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(tool_calls)],
        usage_metadata={"input_tokens": entrada, "output_tokens": salida, "total_tokens": entrada + salida},
    )


class ModeloFalso:
    """Como el de test_agente.py pero async: así se ejercita el mismo contrato que
    langchain-mcp-adapters exige (tools con solo ainvoke)."""

    def __init__(self, *mensajes):
        self.pendientes = list(mensajes)
        self.recibidos = []

    async def ainvoke(self, mensajes):
        self.recibidos.append(list(mensajes))
        return self.pendientes.pop(0)


class ToolFalsa:
    def __init__(self, nombre, fn):
        self.name = nombre
        self._fn = fn

    async def ainvoke(self, args):
        return self._fn(**args)


HERRAMIENTA_FALSA = ToolFalsa("herramienta_falsa", lambda valor: f"resultado de {valor}")
CATALOGO = {"herramienta_falsa": HERRAMIENTA_FALSA}


@pytest.mark.anyio
async def test_sin_tool_calls_contesta_directo():
    modelo = ModeloFalso(_ai("Hola"))
    t = await agente_mcp.responder(modelo, "A01", "¿Hola?", CATALOGO)
    assert t.respuesta == "Hola"
    assert t.llamadas == []
    assert t.herramientas == []


@pytest.mark.anyio
async def test_ejecuta_la_tool_y_vuelve_al_modelo_con_el_resultado():
    modelo = ModeloFalso(
        _ai(tool_calls=[("herramienta_falsa", {"valor": "x"})]),
        _ai("Listo"),
    )
    t = await agente_mcp.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert t.respuesta == "Listo"
    assert t.llamadas[0].nombre == "herramienta_falsa"
    assert t.llamadas[0].argumentos == {"valor": "x"}
    assert t.llamadas[0].resultado == "resultado de x"
    ultimos = modelo.recibidos[-1]
    assert isinstance(ultimos[-1], ToolMessage) and ultimos[-1].content == "resultado de x"


@pytest.mark.anyio
async def test_el_primer_mensaje_es_el_system_prompt_y_despues_la_pregunta():
    modelo = ModeloFalso(_ai("ok"))
    await agente_mcp.responder(modelo, "A01", "¿Cuál es el horario?", CATALOGO)
    m = modelo.recibidos[0]
    assert isinstance(m[0], SystemMessage) and isinstance(m[1], HumanMessage)
    assert m[1].content == "¿Cuál es el horario?"


@pytest.mark.anyio
async def test_registra_el_usage_de_cada_llamada_al_modelo():
    modelo = ModeloFalso(
        _ai(tool_calls=[("herramienta_falsa", {"valor": "x"})], entrada=100, salida=20),
        _ai("Listo", entrada=300, salida=40),
    )
    t = await agente_mcp.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert [(u.tokens_entrada, u.tokens_salida) for u in t.usos] == [(100, 20), (300, 40)]


@pytest.mark.anyio
async def test_una_tool_inexistente_no_rompe_el_loop():
    modelo = ModeloFalso(_ai(tool_calls=[("no_existe", {})]), _ai("Perdón"))
    t = await agente_mcp.responder(modelo, "A02", "¿Y?", CATALOGO)
    assert "no_existe" in t.llamadas[0].resultado
    assert t.respuesta == "Perdón"


@pytest.mark.anyio
async def test_corta_en_max_vueltas_y_lo_deja_anotado():
    modelo = ModeloFalso(*[_ai(tool_calls=[("herramienta_falsa", {"valor": "x"})]) for _ in range(10)])
    t = await agente_mcp.responder(modelo, "A02", "¿Y?", CATALOGO, max_vueltas=3)
    assert len(t.llamadas) == 3
    assert "vueltas" in (t.error or "")


@pytest.mark.anyio
async def test_un_modelo_que_explota_deja_la_traza_con_error():
    class Explota:
        async def ainvoke(self, mensajes):
            raise RuntimeError("503 de OpenRouter")

    t = await agente_mcp.responder(Explota(), "A03", "¿Y?", CATALOGO)
    assert "503 de OpenRouter" in t.error
    assert t.respuesta == ""


@pytest.mark.anyio
async def test_el_jsonl_de_salida_tiene_exactamente_los_campos_del_contrato(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(
        json.dumps({"id": "A01", "pregunta": "¿Hola?", "herramientas_esperadas": ["x"],
                    "respuesta_referencia": "no mirar"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    salida = tmp_path / "r.jsonl"

    async def fabrica_tools():
        return [HERRAMIENTA_FALSA]

    await agente_mcp.correr(preguntas, salida, tmp_path / "log.md",
                             fabrica_tools=fabrica_tools,
                             fabrica_modelo=lambda tools: ModeloFalso(_ai("Hola")))
    linea = json.loads(salida.read_text(encoding="utf-8").strip())
    assert set(linea) == {"id", "respuesta", "contextos", "herramientas"}
    assert linea["id"] == "A01" and linea["respuesta"] == "Hola"


@pytest.mark.anyio
async def test_la_salida_tiene_una_linea_por_pregunta_y_en_orden(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(
        "\n".join(json.dumps({"id": f"A0{i}", "pregunta": f"p{i}"}) for i in (1, 2, 3)),
        encoding="utf-8",
    )
    salida = tmp_path / "r.jsonl"

    async def fabrica_tools():
        return [HERRAMIENTA_FALSA]

    await agente_mcp.correr(preguntas, salida, tmp_path / "log.md",
                             fabrica_tools=fabrica_tools,
                             fabrica_modelo=lambda tools: ModeloFalso(_ai("a"), _ai("b"), _ai("c")))
    ids = [json.loads(l)["id"] for l in salida.read_text(encoding="utf-8").splitlines()]
    assert ids == ["A01", "A02", "A03"]


@pytest.mark.anyio
async def test_la_corrida_escribe_el_log_md(tmp_path):
    preguntas = tmp_path / "p.jsonl"
    preguntas.write_text(json.dumps({"id": "A01", "pregunta": "¿Hola?"}), encoding="utf-8")
    log = tmp_path / "log.md"

    async def fabrica_tools():
        return [HERRAMIENTA_FALSA]

    await agente_mcp.correr(preguntas, tmp_path / "r.jsonl", log,
                             fabrica_tools=fabrica_tools,
                             fabrica_modelo=lambda tools: ModeloFalso(_ai("Hola")))
    assert "A01" in log.read_text(encoding="utf-8")


def test_construir_modelo_exige_la_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        agente_mcp.construir_modelo([])


@tool
def _tool_real(valor: str) -> str:
    """Una tool de LangChain real, para probar el bind_tools de construir_modelo."""
    return valor


def test_construir_modelo_apunta_a_openrouter_y_bindea_las_tools_recibidas(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    modelo = agente_mcp.construir_modelo([_tool_real, _tool_real])
    assert modelo.bound.model_name == "deepseek/deepseek-v4-flash-0731"
    assert str(modelo.bound.openai_api_base) == "https://openrouter.ai/api/v1"
    assert modelo.bound.temperature == 0
    assert len(modelo.kwargs["tools"]) == 2


def test_conexion_mcp_arranca_servidor_mcp_con_el_mismo_interprete():
    c = agente_mcp.conexion_mcp()
    assert c["hospital"]["transport"] == "stdio"
    assert c["hospital"]["args"][-1].endswith("servidor_mcp.py")
