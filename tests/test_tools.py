"""Tests de las 6 tools de LangChain.

Los nombres son parte del contrato: `evaluar.py` mide el ruteo comparando estos strings
contra `herramientas_esperadas`. Un rename silencioso pone el ruteo en 0.
"""
import json

import pytest
from langchain_core.tools import BaseTool

from herramientas import api_hospital, tools

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
    assert {t.name for t in tools.TODAS} == set(ESPERADAS)


def test_son_tools_de_langchain():
    assert all(isinstance(t, BaseTool) for t in tools.TODAS)


@pytest.mark.parametrize("nombre,params", ESPERADAS.items())
def test_cada_tool_declara_sus_parametros_y_una_descripcion_util(nombre, params):
    t = next(t for t in tools.TODAS if t.name == nombre)
    assert set(t.args) == set(params)
    assert len(t.description) > 80, "el modelo rutea leyendo la descripción: tiene que ser explícita"


def test_consultar_camas_devuelve_el_json_de_la_api():
    d = json.loads(tools.consultar_camas.invoke({"sector": "pediatria"}))
    assert d["datos"]["libres"] == d["datos"]["total"] - d["datos"]["ocupadas"]


def test_consultar_espera_no_necesita_argumentos():
    assert "minutos_por_nivel" in tools.consultar_espera.invoke({})


def test_buscar_documentos_devuelve_los_fragmentos_como_texto(monkeypatch):
    monkeypatch.setattr(tools.documentos, "buscar", lambda consulta, top_k=None: ["frag A", "frag B"])
    texto = tools.buscar_documentos.invoke({"consulta": "horario de visita"})
    assert "frag A" in texto and "frag B" in texto


def test_buscar_documentos_avisa_cuando_no_hay_resultados(monkeypatch):
    monkeypatch.setattr(tools.documentos, "buscar", lambda consulta, top_k=None: [])
    assert "no se encontr" in tools.buscar_documentos.invoke({"consulta": "xyz"}).lower()


def test_toda_tool_devuelve_string():
    """El loop guarda el resultado crudo en `contextos`, que el evaluador espera como texto."""
    assert isinstance(tools.consultar_farmacia.invoke({"medicamento": "insulina NPH"}), str)
    assert isinstance(tools.consultar_guardia.invoke({"especialidad": "cardiologia"}), str)
    assert isinstance(tools.consultar_turnos.invoke({"especialidad": "traumatologia"}), str)
