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

Lo que entregó la cátedra (no modificar):

```
datos/corpus/                     20 documentos del hospital (Markdown) — base de conocimiento de la parte 1
datos/preguntas_recuperacion_dev.jsonl   preguntas dev para la parte 1
datos/preguntas_agente_dev.jsonl         preguntas dev para las partes 2 y 3
api/servidor.py                   API del hospital (estado del día: camas, guardias, turnos, farmacia, espera)
evaluar/evaluar.py                evaluador de la cátedra
atencion/test_atencion.py         tests de la parte 4
a_mano/ejercicio.md               consigna de la parte 5
```

Lo nuestro:

```
recuperar.py                      parte 1: CLI del recuperador; expone buscar() para el agente
config_recuperador.json           parte 1: la configuración ganadora, fija
rag/                              parte 1: chunking, embeddings e índice coseno
agente.py                         parte 2: CLI + loop de tool calling con LangChain
herramientas/
  api_hospital.py                 cliente de la API del hospital (solo stdlib)
  documentos.py                   adaptador a recuperar.buscar()
  tools.py                        las 6 tools de LangChain
  registro.py                     el log .md de cada corrida del agente
servidor_mcp.py                   parte 3: las 6 herramientas como servidor MCP (SDK `mcp`, stdio)
agente_mcp.py                     parte 3: el agente con las tools del servidor vía langchain-mcp-adapters
atencion.py                       parte 4: softmax, atención, autoatención, multicabeza y layer_norm en NumPy
tests/                            pytest de las partes 1 a 3 (87 tests + 5 marcados `lento`)
specs/                            un SPEC por parte, escrito antes del código
experimentos/                     toda la evidencia: .eval.json por configuración, logs de corrida y capturas del Inspector
resultados.jsonl(.eval.json)      la corrida entregada de la parte 1
respuestas.jsonl(.eval.json)      la corrida entregada de la parte 2
respuestas_mcp.jsonl(.eval.json)  la corrida entregada de la parte 3
a_mano/ejercicio5.pdf             parte 5: hojas escaneadas, a mano y sin IA
INFORME.md                        el informe
```

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

Todos se corren con el `.venv` activado. Los de las partes 2 y 3 necesitan además la API del hospital levantada y `OPENROUTER_API_KEY` en el entorno.

```bash
pytest -q          # los 87 tests de las partes 1 a 3; no usa red ni gasta créditos
                   # (los que bajan modelos de Hugging Face están marcados `lento` y se corren con -m lento)

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

## Estado del código

| Parte | Estado | Resultado |
|---|---|---|
| 1 | **terminada** — `recuperar.py` + `rag/`, 136 experimentos en `experimentos/` | context_relevance **1.000** |
| 2 | **terminada** — `agente.py` + `herramientas/` | ruteo **1.000**, juez **5,00 / 5,00 / 5,00** |
| 3 | **terminada** — `servidor_mcp.py` + `agente_mcp.py`, capturas en `experimentos/inspector/` | ruteo **1.000**, juez **5,00 / 5,00 / 5,00** |
| 4 | **terminada** — `atencion.py` | **14/14** tests de la cátedra en verde |
| 5 | **terminada** — hojas escaneadas en `a_mano/ejercicio5.pdf`, a mano y sin IA | |

Los SPEC están en `specs/` (uno por parte) y el análisis de cada parte en `INFORME.md`, que incluye el costo total de la misión (USD 0,0642 por logs, USD 0,0644 según el dashboard de OpenRouter) en su última sección.

### Interfaz entre la parte 1 y la parte 2

Para poder trabajar en paralelo, `recuperar.py` tiene que exponer — además de su CLI — esta función a nivel de módulo:

```python
def buscar(consulta: str, top_k: int | None = None) -> list[str]:
    """Fragmentos más relevantes del corpus, en orden de relevancia descendente.
    top_k=None usa la configuración ganadora fija de la parte 1."""
```

Devuelve texto crudo del corpus (sin reformatear) y carga el encoder de forma perezosa, en la primera llamada. `herramientas/documentos.py` la usa cuando existe y cae a un stub si no, avisando por `stderr`. Quedó implementada tal cual, así que la parte 2 la tomó sin cambios.

El agente **no pisa** el `top_k` de la parte 1 (`TOP_K = None`): se probó con `top_k=2` y el juez bajó `context_relevance` de 5,00 a 4,50, porque el segundo fragmento casi siempre es texto ajeno. Está medido en `INFORME.md` §Parte 2.

## Reglas importantes

- **No modificar** `evaluar/evaluar.py`, `api/`, `datos/` ni `atencion/test_atencion.py` — la cátedra corre sus propias copias.
- Las 6 herramientas del agente (`buscar_documentos`, `consultar_camas`, `consultar_guardia`, `consultar_turnos`, `consultar_farmacia`, `consultar_espera`) tienen que llamarse exactamente así, en las partes 2 y 3.
- Parte 1: toda configuración probada necesita su `.eval.json` en `experimentos/` para contar en la tabla del informe.
- Partes 2 y 3: sin el log `.md` de la corrida, esa parte vale cero.
- Parte 5 se resuelve a mano, en papel, **sin IA**. Antes de hacer las cuentas (partes 4 y 5), mirar [Attention in transformers, step-by-step](https://www.youtube.com/watch?v=eMlx5fFNoYc) (3Blue1Brown, Deep Learning Chapter 6).
- Trabajar con IA (Claude Code, Codex, Copilot, etc.) para las partes 1 a 4, con la metodología de la clase 2: `CLAUDE.md`, `SPEC.md`, TDD e historia de commits limpia. Ver [`CLAUDE.md`](./CLAUDE.md).

## Informe final

`INFORME.md` tiene que incluir: la tabla de experimentos y la elección de la parte 1, los resultados de la parte 2 con análisis de las preguntas donde falló el agente, la comparación entre el agente de la parte 2 y el agente MCP de la parte 3, y el costo total de la misión en OpenRouter contrastado con el dashboard.
