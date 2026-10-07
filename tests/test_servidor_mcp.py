"""Tests de servidor_mcp.py.

Dos niveles: las 6 funciones subyacentes (el decorador @mcp.tool() no cambia la función,
así que se llaman como funciones Python comunes) delegan en herramientas.api_hospital /
herramientas.documentos, igual que ya prueba test_tools.py para las tools de LangChain —
no se repiten todos esos casos, solo lo mínimo para confirmar que apuntan a los mismos
módulos. Y un test de integración real por stdio (tools/list + tools/call), para probar el
transporte MCP de verdad, no solo la lógica de negocio.
"""
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import servidor_mcp
from herramientas import api_hospital

RAIZ = Path(__file__).resolve().parents[1]

ESPERADAS = {
    "buscar_documentos": ["consulta"],
    "consultar_camas": ["sector"],
    "consultar_guardia": ["especialidad"],
    "consultar_turnos": ["especialidad"],
    "consultar_farmacia": ["medicamento"],
    "consultar_espera": [],
}


@pytest.fixture(autouse=True)
def _apuntar_a_la_api(api_url, monkeypatch):
    monkeypatch.setattr(api_hospital, "BASE_URL", api_url)


def test_estan_las_seis_con_los_nombres_exactos_del_contrato():
    nombres = {t.name for t in servidor_mcp.mcp._tool_manager.list_tools()}
    assert nombres == set(ESPERADAS)


def test_consultar_camas_devuelve_el_json_de_la_api():
    d = json.loads(servidor_mcp.consultar_camas("pediatria"))
    assert d["datos"]["libres"] == d["datos"]["total"] - d["datos"]["ocupadas"]


def test_consultar_espera_no_necesita_argumentos():
    assert "minutos_por_nivel" in servidor_mcp.consultar_espera()


def test_buscar_documentos_devuelve_los_fragmentos_como_texto(monkeypatch):
    monkeypatch.setattr(servidor_mcp.documentos, "buscar", lambda consulta, top_k=None: ["frag A", "frag B"])
    texto = servidor_mcp.buscar_documentos("horario de visita")
    assert "frag A" in texto and "frag B" in texto


def test_buscar_documentos_avisa_cuando_no_hay_resultados(monkeypatch):
    monkeypatch.setattr(servidor_mcp.documentos, "buscar", lambda consulta, top_k=None: [])
    assert "no se encontr" in servidor_mcp.buscar_documentos("xyz").lower()


@pytest.fixture
def servidor_params(api_url):
    """Arranca servidor_mcp.py como subproceso real, apuntando a la API de test."""
    return StdioServerParameters(
        command=sys.executable,
        args=[str(RAIZ / "servidor_mcp.py")],
        env={"API_HOSPITAL_URL": api_url},
    )


@pytest.mark.anyio
async def test_tools_list_devuelve_las_seis_por_stdio(servidor_params):
    async with stdio_client(servidor_params) as (read, write):
        async with ClientSession(read, write) as sesion:
            await sesion.initialize()
            resultado = await sesion.list_tools()
    assert {t.name for t in resultado.tools} == set(ESPERADAS)


@pytest.mark.anyio
async def test_tools_call_consultar_camas_por_stdio(servidor_params):
    async with stdio_client(servidor_params) as (read, write):
        async with ClientSession(read, write) as sesion:
            await sesion.initialize()
            resultado = await sesion.call_tool("consultar_camas", {"sector": "pediatria"})
    assert not resultado.isError
    d = json.loads(resultado.content[0].text)
    assert d["datos"]["libres"] == d["datos"]["total"] - d["datos"]["ocupadas"]


@pytest.mark.anyio
async def test_tools_call_consultar_espera_sin_argumentos_por_stdio(servidor_params):
    async with stdio_client(servidor_params) as (read, write):
        async with ClientSession(read, write) as sesion:
            await sesion.initialize()
            resultado = await sesion.call_tool("consultar_espera", {})
    assert not resultado.isError
    assert "minutos_por_nivel" in resultado.content[0].text
