"""Parte 3: el mismo agente de la parte 2, pero con las 6 herramientas servidas por
servidor_mcp.py (tools/list / tools/call vía langchain-mcp-adapters) en vez de locales.

    python3 agente_mcp.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas_mcp.jsonl

Este archivo no llama a la API del hospital ni al recuperador por su cuenta: no importa
herramientas.api_hospital ni herramientas.documentos. Las únicas tools que ve son las que
devuelve servidor_mcp.py en tiempo de ejecución.

El loop es async (a diferencia de agente.py) porque las tools que arma langchain-mcp-adapters
solo exponen coroutine (toda llamada MCP habla con el servidor por stdio): ver "Desvío" en
specs/parte3-mcp.md. El diseño del loop en sí —prompt, tope de vueltas, traza— es el mismo.
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from agente import BASE_URL, MAX_VUELTAS, MODELO, SISTEMA, leer_preguntas
from herramientas import registro
from herramientas.registro import LlamadaTool, Traza, extraer_uso

SERVIDOR_MCP = Path(__file__).with_name("servidor_mcp.py")


def conexion_mcp():
    return {
        "hospital": {
            "command": sys.executable,
            "args": [str(SERVIDOR_MCP)],
            "transport": "stdio",
        }
    }


async def cargar_tools():
    """tools/list contra servidor_mcp.py, convertidas a tools de LangChain."""
    cliente = MultiServerMCPClient(conexion_mcp())
    return await cliente.get_tools()


def construir_modelo(tools, temperatura=0):
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        sys.exit("falta la variable OPENROUTER_API_KEY")
    llm = ChatOpenAI(
        model=MODELO,
        base_url=BASE_URL,
        api_key=clave,
        temperature=temperatura,
        extra_body={"usage": {"include": True}},
    )
    return llm.bind_tools(tools)


async def responder(modelo, pid, pregunta, catalogo, max_vueltas=MAX_VUELTAS):
    """Igual que agente.responder, pero async: tools/call vía ainvoke."""
    traza = Traza(id=pid, pregunta=pregunta)
    mensajes = [SystemMessage(SISTEMA), HumanMessage(pregunta)]

    for _ in range(max_vueltas):
        try:
            respuesta = await modelo.ainvoke(mensajes)
        except Exception as e:
            traza.error = f"la llamada al modelo falló: {e}"
            return traza
        traza.usos.append(extraer_uso(respuesta))
        mensajes.append(respuesta)

        if not respuesta.tool_calls:
            traza.respuesta = respuesta.text
            return traza

        for llamada in respuesta.tool_calls:
            herramienta = catalogo.get(llamada["name"])
            if herramienta is None:
                resultado = f"error: la herramienta '{llamada['name']}' no existe"
            else:
                try:
                    resultado = str(await herramienta.ainvoke(llamada["args"]))
                except Exception as e:
                    resultado = f"error al ejecutar '{llamada['name']}': {e}"
            traza.llamadas.append(LlamadaTool(llamada["name"], llamada["args"], resultado))
            mensajes.append(ToolMessage(content=resultado, tool_call_id=llamada["id"]))

    traza.error = f"se alcanzó el máximo de {max_vueltas} vueltas sin respuesta final"
    return traza


async def correr(preguntas_path, salida_path, log_path, fabrica_tools=cargar_tools,
                  fabrica_modelo=construir_modelo):
    """fabrica_tools/fabrica_modelo son inyectables para poder testear el loop sin MCP real."""
    preguntas = leer_preguntas(preguntas_path)
    tools = await fabrica_tools()
    catalogo = {t.name: t for t in tools}
    modelo = fabrica_modelo(tools)
    arranque = time.time()
    trazas = []

    for p in preguntas:
        # Del JSONL solo se leen id y pregunta: herramientas_esperadas y respuesta_referencia
        # son del evaluador.
        traza = await responder(modelo, p["id"], p["pregunta"], catalogo)
        trazas.append(traza)
        print(f"{traza.id}  herramientas: {', '.join(traza.herramientas) or '(ninguna)'}"
              + (f"  ERROR: {traza.error}" if traza.error else ""))

    salida_path = Path(salida_path)
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    salida_path.write_text(
        "\n".join(json.dumps(t.linea_jsonl(), ensure_ascii=False) for t in trazas) + "\n",
        encoding="utf-8",
    )
    registro.escribir_log(log_path, trazas, MODELO, time.time() - arranque)
    print(f"\n{len(trazas)} respuestas en {salida_path}\nlog en {log_path}")
    return trazas


def main():
    ap = argparse.ArgumentParser(description="Agente MCP del Hospital Arroyo Claro (parte 3)")
    ap.add_argument("--preguntas", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--log", default=None, help="por defecto experimentos/logs/agente_mcp_<timestamp>.md")
    args = ap.parse_args()
    log = args.log or f"experimentos/logs/agente_mcp_{datetime.now():%Y%m%d_%H%M%S}.md"
    asyncio.run(correr(args.preguntas, args.salida, log))


if __name__ == "__main__":
    main()
