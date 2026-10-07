# SPEC — Parte 3: las mismas herramientas como servidor MCP (`servidor_mcp.py`, `agente_mcp.py`)

Estado: borrador, antes de escribir código. Fuente de verdad de la consigna: `mission.md` §"Parte 3". Reglas operativas: `CLAUDE.md`.

## Objetivo

Mover las 6 herramientas de la parte 2 a un servidor MCP real (SDK oficial `mcp`, transporte stdio) y armar un cliente (`agente_mcp.py`) que las descubra con `tools/list` y las llame con `tools/call`, con el mismo modelo y el mismo diseño de agente que la parte 2. El punto de la parte es que `agente_mcp.py` **no tenga ninguna lógica propia** para hablar con la API del hospital o con el recuperador: todo pasa por el servidor.

## Contrato (no negociable, de `mission.md`)

```bash
python3 agente_mcp.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas_mcp.jsonl
```

Mismo formato de salida que `agente.py` (parte 2): `{"id": "A01", "respuesta": "...", "contextos": [...], "herramientas": [...]}`. Se evalúa con el mismo comando de `evaluar.py agente`, apuntando a `respuestas_mcp.jsonl`.

Para probar el servidor con cualquier cliente MCP (no solo el nuestro):

```bash
npx @modelcontextprotocol/inspector python3 servidor_mcp.py
```

Capturas de las 6 herramientas probadas desde el Inspector en `experimentos/inspector/`.

## Restricción de diseño (la que define la parte)

> "`agente_mcp.py` no puede tener lógica propia para llamar a la API o al recuperador: todo tiene que pasar por `servidor_mcp.py` vía `tools/list` / `tools/call`."

Consecuencia directa: `agente_mcp.py` no importa `herramientas.api_hospital` ni `herramientas.documentos` ni `recuperar`. Las únicas tools que ve son las que le devuelve el servidor MCP en tiempo de ejecución.

`servidor_mcp.py`, en cambio, sí reutiliza los módulos de lógica pura que ya existen (`herramientas/api_hospital.py`, `herramientas/documentos.py`), **para no duplicar la llamada HTTP ni la llamada al recuperador** — eso ya está hecho y testeado en la parte 2. Lo único nuevo en `servidor_mcp.py` es la capa de 6 funciones decoradas con `@mcp.tool()` en vez de `@tool` de LangChain, igual que `herramientas/tools.py` es la misma lógica decorada para LangChain.

## Diseño

### `servidor_mcp.py`

SDK oficial `mcp`, usando `mcp.server.fastmcp.FastMCP` (parte del paquete `mcp`, no una librería aparte) por transporte stdio:

```python
from mcp.server.fastmcp import FastMCP
from herramientas import api_hospital, documentos

mcp = FastMCP("hospital-arroyo-claro")

@mcp.tool()
def buscar_documentos(consulta: str) -> str: ...   # llama a documentos.buscar
@mcp.tool()
def consultar_camas(sector: str) -> str: ...        # llama a api_hospital.camas
# ... las otras 4, mismos nombres y parámetros que la parte 2

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

- Nombres, parámetros y docstrings son equivalentes a los de `herramientas/tools.py` (misma división de fuentes, mismas listas de valores válidos) — es la misma información de ruteo, pasada a un framework distinto. No se comparte el string entre los dos archivos: son dos capas de descripción separadas sobre la misma lógica, y mantenerlas como dos funciones cortas es más simple que una abstracción para des-duplicar seis docstrings.
- La lógica (llamada HTTP, llamada al recuperador) vive una sola vez, en `herramientas/api_hospital.py` y `herramientas/documentos.py`. `servidor_mcp.py` es una capa fina, igual que `herramientas/tools.py`.

### `agente_mcp.py`

También con LangChain, como pide el enunciado. Las tools del servidor se cargan con `langchain-mcp-adapters` (`MultiServerMCPClient`), no con el SDK `mcp` a mano:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

cliente = MultiServerMCPClient({
    "hospital": {"command": sys.executable, "args": [str(SERVIDOR_MCP)], "transport": "stdio"}
})
tools = await cliente.get_tools()      # tools/list, resuelto por la librería
modelo = ChatOpenAI(...).bind_tools(tools)
...
resultado = await herramienta.ainvoke(args)   # tools/call, resuelto por la librería
```

Reutiliza de `agente.py` (import directo, sin duplicar): `MODELO`, `BASE_URL`, `MAX_VUELTAS`, `SISTEMA`, `leer_preguntas`. Reutiliza de `herramientas/registro.py`: `Traza`, `LlamadaTool`, `escribir_log`, y la nueva función pública `extraer_uso(mensaje)` (ver desvío abajo).

### Desvío respecto a "importar `responder`/`correr` de `agente.py`" (nota de `specs/parte2-agente.md`)

La idea original era que `agente_mcp.py` importara `responder`/`correr` de `agente.py` sin cambios, pasándole el catálogo de tools MCP. Al implementar aparece un problema real: `langchain-mcp-adapters` genera cada tool con **solo coroutine** (`call_tool` es `async`), porque toda llamada MCP es asíncrona por naturaleza (habla con el servidor por stdio). Probado a mano: `tool.invoke(...)` sobre una `StructuredTool` sin `func` sincrónico levanta `NotImplementedError: StructuredTool does not support sync invocation` — no es un problema de "estamos dentro de un loop corriendo", es que el modo síncrono no existe para estas tools.

`agente.responder`/`agente.correr` son sincrónicos (`modelo.invoke(...)`, `herramienta.invoke(...)`), a propósito, porque las tools de la parte 2 son funciones Python comunes. No se pueden reusar tal cual contra tools que solo exponen `ainvoke`.

**Decisión:** `agente_mcp.py` define su propio `responder`/`correr` **async**, con el mismo diseño exacto (mismo prompt, mismo tope de vueltas, mismo registro de traza) pero `await modelo.ainvoke(...)` y `await herramienta.ainvoke(...)`. No es duplicar lógica de negocio (eso sigue viviendo una sola vez en `herramientas/`): es la misma forma de loop, en su variante async, porque el protocolo MCP lo exige. Se documenta acá en vez de forzar la reutilización textual del código síncrono de la parte 2.

Para que las dos variantes no diverjan en cómo se lee el `usage` de la respuesta del modelo, `_uso` pasa de ser una función privada de `agente.py` a `herramientas/registro.py::extraer_uso`, pública, y la usan las dos.

### Vida de la conexión MCP

`MultiServerMCPClient.get_tools()` (modo básico de la librería) abre una sesión stdio nueva por cada llamada a herramienta. Para las 12 preguntas de `dev` (unas pocas llamadas a tool cada una) el costo de arrancar el subproceso por llamada es aceptable y es el modo documentado más simple de la librería — no hay necesidad de manejar a mano el ciclo de vida de una sesión persistente para este volumen.

### Log y evidencia

Mismo formato que la parte 2: un `.md` por corrida en `experimentos/logs/agente_mcp_<timestamp>.md`, generado con `herramientas/registro.escribir_log` (mismo módulo, nada nuevo que escribir).

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector python3 servidor_mcp.py
```

Con la API del hospital levantada (`python3 api/servidor.py`). Probar las 6 herramientas desde la UI del Inspector (no usa ningún LLM) y capturar pantalla de cada una en `experimentos/inspector/`.

## Plan TDD

1. `test_servidor_mcp.py`:
   - Las funciones subyacentes (`servidor_mcp.buscar_documentos`, etc., llamadas como funciones Python comunes — el decorador `@mcp.tool()` no cambia la función) delegan en `herramientas.api_hospital` / `herramientas.documentos`, igual que ya se prueba para las tools de LangChain en `test_tools.py`. Evita duplicar esos casos; solo lo mínimo para confirmar que `servidor_mcp.py` llama a los mismos módulos.
   - Un test de integración real por stdio: levantar el servidor como subproceso (`mcp.client.stdio.stdio_client` + `ClientSession`, apuntando a `python3 servidor_mcp.py` con `API_HOSPITAL_URL` seteada a la API de test), hacer `list_tools()` y confirmar los 6 nombres exactos, y `call_tool()` sobre 1 o 2 para confirmar que el resultado viaja por el protocolo real.
2. `test_agente_mcp.py` — el loop async corre contra un modelo falso (`ainvoke` scripteado) y un catálogo de tools falsas (`ainvoke` scripteado): mismas verificaciones que `test_agente.py` (ejecuta tools, corta sin `tool_calls`, respeta `MAX_VUELTAS`, la línea JSONL tiene los 4 campos), sin red ni subproceso real.
3. Recién con todo en verde: la corrida real (`agente_mcp.py` contra OpenRouter + servidor MCP real) y después `evaluar.py agente` sobre `respuestas_mcp.jsonl` (cuesta plata, una vez).

## Comparación con la parte 2 (para el informe)

El criterio de éxito de la consigna pide comparar las 4 métricas (ruteo + 3 del juez) y el costo entre `agente.py` y `agente_mcp.py`. La expectativa de diseño es que el ruteo y las notas del juez no deberían cambiar mucho (mismo modelo, mismas 6 herramientas, mismo prompt): lo que puede cambiar es el costo/latencia por el overhead de levantar un subproceso MCP por llamada a tool. Si los números difieren con claridad, el log de la corrida MCP es la fuente para explicar por qué (overhead de transporte no afecta tokens del modelo, así que un cambio en tokens/costo señalaría una diferencia real de comportamiento del agente, no solo de infraestructura).

## Decisiones abiertas

- [ ] ¿Vale la pena una sesión MCP persistente (en vez de una por llamada) para la corrida real, por velocidad? Mientras los tiempos sean razonables para 12 preguntas, no — el modo básico de la librería alcanza y es menos código.
