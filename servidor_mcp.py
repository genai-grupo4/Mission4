"""Parte 3: las 6 herramientas del hospital como servidor MCP (SDK oficial `mcp`, stdio).

    python3 servidor_mcp.py
    npx @modelcontextprotocol/inspector python3 servidor_mcp.py   # para probarlo a mano

No reimplementa la llamada HTTP ni la llamada al recuperador: esa lógica vive una sola vez
en herramientas/api_hospital.py y herramientas/documentos.py (las mismas que usa la parte 2).
Esto es solo la capa de 6 tools MCP encima, igual que herramientas/tools.py es la misma lógica
decorada para LangChain.
"""
from mcp.server.fastmcp import FastMCP

from herramientas import api_hospital, documentos

mcp = FastMCP("hospital-arroyo-claro")


@mcp.tool()
def buscar_documentos(consulta: str) -> str:
    """Busca en los documentos del Hospital Provincial Arroyo Claro (normas, reglamentos y
    procedimientos que casi no cambian) y devuelve los fragmentos más relevantes.

    Usala para todo lo que sea una regla o un instructivo del hospital: horarios de visita,
    acompañantes, preparación para estudios, requisitos y documentación para turnos o para
    retirar medicación, donación de sangre, derechos del paciente, triage, reclamos.

    NO sirve para el estado del día (camas libres, quién está de guardia, turnos disponibles,
    stock de farmacia, minutos de espera): eso no está en los documentos, está en la API.

    Args:
        consulta: qué buscar, en lenguaje natural y con las palabras del tema
            (por ejemplo "horario de visita en neonatología" o "preparación para colonoscopía").
    """
    fragmentos = documentos.buscar(consulta)
    if not fragmentos:
        return f"No se encontraron fragmentos para: {consulta}"
    return "\n\n---\n\n".join(fragmentos)


@mcp.tool()
def consultar_camas(sector: str) -> str:
    """Devuelve la disponibilidad de camas de hoy en un sector de internación: total, ocupadas
    y libres. Es el estado del día y cambia todo el tiempo, no está en los documentos.

    Args:
        sector: el sector de internación. Válidos: clínica médica, cirugía general,
            terapia intensiva, pediatría, neonatología, maternidad.
    """
    return api_hospital.camas(sector)


@mcp.tool()
def consultar_guardia(especialidad: str) -> str:
    """Devuelve qué profesionales están de guardia HOY en una especialidad y en qué horario.

    Usala para "quién está de guardia", "hay un médico de X ahora". Para pedir un turno
    programado usá consultar_turnos, que es otra cosa.

    Args:
        especialidad: la especialidad de la guardia. Válidas: clínica médica, cardiología,
            pediatría, traumatología, obstetricia, salud mental.
    """
    return api_hospital.guardia(especialidad)


@mcp.tool()
def consultar_turnos(especialidad: str) -> str:
    """Devuelve los próximos turnos programados disponibles (fecha y hora) en una especialidad.

    Usala para "cuándo puedo conseguir turno con X". No dice qué hay que llevar a la consulta:
    eso es una norma del hospital y está en los documentos (buscar_documentos).

    Args:
        especialidad: la especialidad del turno. Válidas: cardiología, dermatología,
            traumatología, psicología, gastroenterología, obstetricia, kinesiología.
    """
    return api_hospital.turnos(especialidad)


@mcp.tool()
def consultar_farmacia(medicamento: str) -> str:
    """Devuelve el stock de hoy de un medicamento en la farmacia del hospital y, si no hay,
    la fecha prevista de reposición.

    No dice qué hay que presentar para retirarlo: ese requisito es una norma y está en los
    documentos (buscar_documentos).

    Args:
        medicamento: el nombre con su presentación, como figura en la receta
            (por ejemplo "enalapril 10 mg", "insulina NPH", "salbutamol aerosol").
    """
    return api_hospital.farmacia(medicamento)


@mcp.tool()
def consultar_espera() -> str:
    """Devuelve los minutos de espera actuales en la guardia, por nivel de triage
    (rojo, naranja, amarillo, verde, azul). No lleva argumentos.

    Devuelve cuánto se está esperando hoy, que es un dato del momento. Qué significa cada
    color y cuál es el tiempo máximo que fija el protocolo es una norma: está en los
    documentos (buscar_documentos).
    """
    return api_hospital.espera()


if __name__ == "__main__":
    mcp.run(transport="stdio")
