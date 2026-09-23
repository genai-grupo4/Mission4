# Misión 4 — RAG, MCP y Transformers en el Hospital Arroyo Claro

Repo del grupo para la misión del Hospital Provincial Arroyo Claro (ficticio): un asistente que contesta preguntas de pacientes combinando un RAG vectorial, un agente con herramientas y un servidor MCP, más dos ejercicios sobre la arquitectura transformer.

**La consigna completa y autoritativa está en [`mission.md`](./mission.md). Este README es un resumen para orientarse rápido — ante cualquier duda, `mission.md` manda.**

**Entrega: viernes 9 de octubre de 2026**, pusheando a este repo.

## Qué hay que construir

| Parte | Entregable | Puntos |
|---|---|---|
| 1 — RAG vectorial | `recuperar.py` | 25 |
| 2 — Agente con dos fuentes (docs + API) | `agente.py` | 30 |
| 3 — Las mismas herramientas como servidor MCP | `servidor_mcp.py` + `agente_mcp.py` | 15 |
| 4 — Capa de atención en NumPy | `atencion.py` | 15 |
| 5 — Bloque de transformer a mano (sin IA) | hojas escaneadas en `a_mano/` | 15 |

## Estructura del repo

```
datos/corpus/                     20 documentos del hospital (Markdown) — base de conocimiento de la parte 1
datos/preguntas_recuperacion_dev.jsonl   preguntas dev para la parte 1
datos/preguntas_agente_dev.jsonl         preguntas dev para las partes 2 y 3
api/servidor.py                   API del hospital (estado del día: camas, guardias, turnos, farmacia, espera)
evaluar/evaluar.py                evaluador de la cátedra (no modificar)
atencion/test_atencion.py         tests de la parte 4 (no modificar)
a_mano/ejercicio.md               consigna de la parte 5
experimentos/                     evidencia de cada configuración probada (a crear)
INFORME.md                        informe final (a crear)
```

Archivos que hay que escribir nosotros (no existen todavía): `recuperar.py`, `agente.py`, `servidor_mcp.py`, `agente_mcp.py`, `atencion.py`, `INFORME.md`.

## Antes de empezar

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 api/servidor.py &          # levanta la API del hospital en http://localhost:8765, en otra terminal
export OPENROUTER_API_KEY=...      # necesario para el agente (partes 2 y 3) y el juez del evaluador
```

## Modelos (vía OpenRouter, obligatorios)

| Uso | Modelo |
|---|---|
| Agente (partes 2 y 3) | `deepseek/deepseek-v4-flash-0731` |
| Juez del evaluador | `google/gemini-3.7-flash` |

Cada corrida del evaluador con juez cuesta plata real de la cuenta del grupo — correrlo solo cuando haya un cambio que valga medir.

## LangChain obligatorio (partes 2 y 3)

- `agente.py`: el modelo se conecta con `ChatOpenAI` de `langchain-openai` apuntando a OpenRouter (`base_url="https://openrouter.ai/api/v1"`), y cada herramienta es una tool de LangChain.
- `agente_mcp.py`: también en LangChain, cargando las herramientas del servidor MCP con `langchain-mcp-adapters`.

## Comandos por parte

```bash
# Parte 1
python3 recuperar.py --preguntas datos/preguntas_recuperacion_dev.jsonl --salida resultados.jsonl
python3 evaluar/evaluar.py recuperacion --preguntas datos/preguntas_recuperacion_dev.jsonl --resultados resultados.jsonl

# Parte 2
python3 agente.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas.jsonl
python3 evaluar/evaluar.py agente --preguntas datos/preguntas_agente_dev.jsonl --respuestas respuestas.jsonl

# Parte 3
python3 agente_mcp.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas_mcp.jsonl
npx @modelcontextprotocol/inspector python3 servidor_mcp.py   # probar las 6 herramientas a mano, capturas en experimentos/inspector/

# Parte 4
python3 atencion/test_atencion.py atencion.py
```

## Reglas importantes

- **No modificar** `evaluar/evaluar.py`, `api/`, `datos/` ni `atencion/test_atencion.py` — la cátedra corre sus propias copias.
- Las 6 herramientas del agente (`buscar_documentos`, `consultar_camas`, `consultar_guardia`, `consultar_turnos`, `consultar_farmacia`, `consultar_espera`) tienen que llamarse exactamente así, en las partes 2 y 3.
- Parte 1: toda configuración probada necesita su `.eval.json` en `experimentos/` para contar en la tabla del informe.
- Partes 2 y 3: sin el log `.md` de la corrida, esa parte vale cero.
- Parte 5 se resuelve a mano, en papel, **sin IA**. Antes de hacer las cuentas (partes 4 y 5), mirar [Attention in transformers, step-by-step](https://www.youtube.com/watch?v=eMlx5fFNoYc) (3Blue1Brown, Deep Learning Chapter 6).
- Trabajar con IA (Claude Code, Codex, Copilot, etc.) para las partes 1 a 4, con la metodología de la clase 2: `CLAUDE.md`, `SPEC.md`, TDD e historia de commits limpia. Ver [`CLAUDE.md`](./CLAUDE.md).

## Informe final

`INFORME.md` tiene que incluir: la tabla de experimentos y la elección de la parte 1, los resultados de la parte 2 con análisis de las preguntas donde falló el agente, la comparación entre el agente de la parte 2 y el agente MCP de la parte 3, y el costo total de la misión en OpenRouter contrastado con el dashboard.
