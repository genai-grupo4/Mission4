"""Tests del cliente HTTP de la API del hospital, contra la API real levantada en un puerto libre."""
import json

import pytest

from herramientas import api_hospital


@pytest.fixture(autouse=True)
def _apuntar_a_la_api(api_url, monkeypatch):
    monkeypatch.setattr(api_hospital, "BASE_URL", api_url)


def test_camas_devuelve_total_ocupadas_y_libres():
    d = json.loads(api_hospital.camas("pediatria"))["datos"]
    assert d["libres"] == d["total"] - d["ocupadas"]


def test_nombres_con_tildes_mayusculas_y_espacios_funcionan():
    con_tilde = json.loads(api_hospital.camas("Terapia Intensiva"))
    sin_tilde = json.loads(api_hospital.camas("terapia_intensiva"))
    assert con_tilde["datos"] == sin_tilde["datos"]


def test_guardia_turnos_farmacia_y_espera_responden():
    assert "datos" in json.loads(api_hospital.guardia("cardiologia"))
    assert "datos" in json.loads(api_hospital.turnos("traumatologia"))
    assert "datos" in json.loads(api_hospital.farmacia("enalapril 10 mg"))
    assert "minutos_por_nivel" in json.loads(api_hospital.espera())


def test_sector_inexistente_devuelve_error_con_opciones_validas():
    """El agente se corrige solo leyendo las opciones, así que el error tiene que llegarle entero."""
    d = json.loads(api_hospital.camas("kinesiologia"))
    assert "error" in d
    assert "pediatria" in d["opciones"]


def test_parametro_vacio_devuelve_error_con_opciones_validas():
    d = json.loads(api_hospital.guardia(""))
    assert "error" in d
    assert d["opciones"]


def test_api_caida_devuelve_texto_de_error_y_no_una_excepcion(monkeypatch):
    """Si la API no está levantada el agente tiene que enterarse, no morirse."""
    monkeypatch.setattr(api_hospital, "BASE_URL", "http://localhost:1")
    d = json.loads(api_hospital.espera())
    assert "error" in d


def test_la_respuesta_es_texto_json_legible():
    texto = api_hospital.camas("neonatologia")
    assert isinstance(texto, str)
    assert "neonatolog" in texto.lower()
