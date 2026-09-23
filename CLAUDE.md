# CLAUDE.md

Contexto e instrucciones para trabajar en este repo con Claude Code (o cualquier IA de programación). La consigna completa está en `mission.md` — este archivo son reglas operativas para no romper el contrato del evaluador.

## Qué es este repo

Un asistente para un hospital ficticio (Hospital Provincial Arroyo Claro), construido en tres capas — RAG vectorial, agente con tool calling, servidor MCP — más dos ejercicios de transformer. Cada capa se mide con `evaluar/evaluar.py`, el evaluador de la cátedra, que **no se puede modificar**.

## Archivos de solo lectura — nunca editar

- `evaluar/evaluar.py`
- `api/` (toda la carpeta)
- `datos/` (toda la carpeta)
- `atencion/test_atencion.py`

La cátedra corre sus propias copias de estos archivos contra el código que entreguemos. Si algo de acá parece necesitar un cambio, el problema está en el código nuestro, no en estos archivos.

## Archivos a crear (no existen todavía)

`recuperar.py`, `agente.py`, `servidor_mcp.py`, `agente_mcp.py`, `atencion.py`, `INFORME.md`, y la carpeta `experimentos/` con la evidencia de cada configuración probada en la parte 1.

## Contratos exactos (no negociables)

Estos comandos y formatos los va a correr la cátedra tal cual — no cambiar nombres de flags ni de campos de salida.

```bash
python3 recuperar.py --preguntas datos/preguntas_recuperacion_dev.jsonl --salida resultados.jsonl
# resultados.jsonl: {"id": "R01", "fragmentos": ["texto", ...]}  -- una línea por pregunta, en orden de relevancia

python3 agente.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas.jsonl
# respuestas.jsonl: {"id": "A01", "respuesta": "...", "contextos": ["...", ...], "herramientas": ["buscar_documentos", ...]}

python3 agente_mcp.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas_mcp.jsonl
# mismo formato que agente.py

python3 atencion/test_atencion.py atencion.py
# tiene que dejar los 14 tests en verde, sin tocar test_atencion.py
```

## Nombres de herramientas (partes 2 y 3) — exactos, el evaluador los busca por nombre

| Herramienta | Hace |
|---|---|
| `buscar_documentos(consulta)` | llama al recuperador de la parte 1 |
| `consultar_camas(sector)` | `GET /camas` |
| `consultar_guardia(especialidad)` | `GET /guardia` |
| `consultar_turnos(especialidad)` | `GET /turnos` |
| `consultar_farmacia(medicamento)` | `GET /farmacia` |
| `consultar_espera()` | `GET /espera` |

En la parte 3, `agente_mcp.py` no puede tener lógica propia para llamar a la API o al recuperador: todo tiene que pasar por `servidor_mcp.py` vía `tools/list` / `tools/call` (SDK oficial `mcp`, transporte stdio).

## Modelos (OpenRouter, obligatorios, no cambiar sin anotarlo en el informe)

- Agente (partes 2 y 3): `deepseek/deepseek-v4-flash-0731`
- Juez del evaluador: `google/gemini-3.7-flash` (lo invoca `evaluar.py`, no lo llamamos nosotros directamente)

`OPENROUTER_API_KEY` tiene que estar en el entorno. Cada corrida del evaluador con juez cuesta plata real — no correrlo en loop ni por las dudas, solo cuando haya un cambio que valga medir.

## Qué evidencia es obligatoria

- **Parte 1:** cada configuración probada (encoder × chunking × top-k × umbral) necesita su propio `.eval.json` en `experimentos/`. Una fila de la tabla del informe sin su archivo no cuenta.
- **Partes 2 y 3:** un log `.md` por corrida del benchmark, con cada pregunta, las llamadas a herramientas (argumentos y resultados), la respuesta final, y el usage (tokens/costo) de cada llamada al modelo. Sin este log la parte vale cero — no es opcional.
- **Parte 3:** capturas de pantalla del MCP Inspector probando las 6 herramientas, en `experimentos/inspector/`.

## Metodología de trabajo (partes 1 a 4)

Seguir la forma de trabajo de la clase 2: `CLAUDE.md` (este archivo), un `SPEC.md` por feature/parte antes de escribir código, TDD, e historia de commits limpia y chica (un commit por paso lógico, no un commit gigante al final).

## Parte 5 — excepción total

`a_mano/ejercicio.md` se resuelve **a mano, en papel, sin ninguna IA**. No generar el desarrollo ni las respuestas con Claude Code — el criterio de la cátedra pesa la justificación escrita a mano de cada operación. El único rol de la IA acá es, como mucho, ayudar a verificar el resultado final con `atencion.py` de la parte 4, nunca a resolver el ejercicio.

## Antes de correr nada

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 api/servidor.py &   # API del hospital en http://localhost:8765, necesaria para partes 2 y 3
```
