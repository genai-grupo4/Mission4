"""Parte 2: agente con tool calling sobre las dos fuentes del hospital.

    python3 agente.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas.jsonl

Requiere OPENROUTER_API_KEY y la API del hospital levantada (python3 api/servidor.py).
El loop de tool calling está escrito a mano en vez de usar AgentExecutor porque el enunciado
pide registrar, por pregunta, cada llamada con sus argumentos y resultados y el usage de cada
llamada al modelo; con un executor cerrado eso no se ve.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from herramientas import registro, tools
from herramientas.registro import LlamadaTool, Traza, UsoModelo

MODELO = "deepseek/deepseek-v4-flash-0731"
BASE_URL = "https://openrouter.ai/api/v1"
MAX_VUELTAS = 6

SISTEMA = """Sos el asistente del Hospital Provincial Arroyo Claro. Contestás consultas de pacientes y familiares.

Tenés dos fuentes y ninguna reemplaza a la otra:
- Los documentos del hospital (buscar_documentos): normas, reglamentos y procedimientos, que casi no cambian.
- La API del hospital (consultar_camas, consultar_guardia, consultar_turnos, consultar_farmacia, consultar_espera): el estado de hoy, que cambia todo el tiempo.

Reglas:
1. No contestes de memoria: todo dato concreto tiene que salir de una herramienta.
2. Si la pregunta tiene más de una parte, usá todas las herramientas que hagan falta antes de contestar (por ejemplo, si hay camas libres Y si el acompañante se puede quedar).
3. No llames herramientas que no aporten a lo que se preguntó.
4. Si una herramienta devuelve un error con la lista de opciones válidas, reintentá con el nombre correcto de esa lista.
5. Si después de usar las herramientas falta un dato, decí que no lo pudiste obtener. No lo completes con conocimiento general ni lo inventes.
6. Contestá en español rioplatense, breve y concreto: el dato que se pidió y las condiciones que lo acompañan, sin saludos ni relleno.
"""


def construir_modelo(temperatura=0):
    """El ChatOpenAI del enunciado, apuntando a OpenRouter, con las 6 tools bindeadas."""
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        sys.exit("falta la variable OPENROUTER_API_KEY")
    llm = ChatOpenAI(
        model=MODELO,
        base_url=BASE_URL,
        api_key=clave,
        temperature=temperatura,
        # OpenRouter devuelve el costo real de cada llamada si se lo pide explícitamente.
        extra_body={"usage": {"include": True}},
    )
    return llm.bind_tools(tools.TODAS)


def _uso(mensaje: AIMessage):
    um = mensaje.usage_metadata or {}
    costo = (mensaje.response_metadata.get("token_usage") or {}).get("cost")
    return UsoModelo(um.get("input_tokens", 0), um.get("output_tokens", 0), costo)


def responder(modelo, pid, pregunta, catalogo=None, max_vueltas=MAX_VUELTAS):
    """Corre el loop de tool calling para una pregunta y devuelve su traza completa."""
    catalogo = tools.POR_NOMBRE if catalogo is None else catalogo
    traza = Traza(id=pid, pregunta=pregunta)
    mensajes = [SystemMessage(SISTEMA), HumanMessage(pregunta)]

    for _ in range(max_vueltas):
        try:
            respuesta = modelo.invoke(mensajes)
        except Exception as e:
            traza.error = f"la llamada al modelo falló: {e}"
            return traza
        traza.usos.append(_uso(respuesta))
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
                    resultado = str(herramienta.invoke(llamada["args"]))
                except Exception as e:
                    resultado = f"error al ejecutar '{llamada['name']}': {e}"
            traza.llamadas.append(LlamadaTool(llamada["name"], llamada["args"], resultado))
            mensajes.append(ToolMessage(content=resultado, tool_call_id=llamada["id"]))

    traza.error = f"se alcanzó el máximo de {max_vueltas} vueltas sin respuesta final"
    return traza


def leer_preguntas(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def correr(preguntas_path, salida_path, fabrica_modelo, log_path, catalogo=None):
    preguntas = leer_preguntas(preguntas_path)
    modelo = fabrica_modelo()
    arranque = time.time()
    trazas = []

    for p in preguntas:
        # Del JSONL solo se leen id y pregunta: herramientas_esperadas y respuesta_referencia
        # son del evaluador.
        traza = responder(modelo, p["id"], p["pregunta"], catalogo)
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
    ap = argparse.ArgumentParser(description="Agente del Hospital Arroyo Claro (parte 2)")
    ap.add_argument("--preguntas", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--log", default=None, help="por defecto experimentos/logs/agente_<timestamp>.md")
    args = ap.parse_args()
    log = args.log or f"experimentos/logs/agente_{datetime.now():%Y%m%d_%H%M%S}.md"
    correr(args.preguntas, args.salida, construir_modelo, log)


if __name__ == "__main__":
    main()
