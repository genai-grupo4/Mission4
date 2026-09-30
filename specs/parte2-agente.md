# SPEC — Parte 2: agente con tool calling (`agente.py`)

Estado: borrador, antes de escribir código. Fuente de verdad de la consigna: `mission.md` §"Parte 2". Reglas operativas: `CLAUDE.md`. Este documento fija el diseño antes de tocar código.

## Objetivo

Un agente sobre `deepseek/deepseek-v4-flash-0731` que conteste preguntas de pacientes combinando dos fuentes: los documentos del hospital (vía el recuperador de la parte 1) y el estado del día (vía la API de `api/servidor.py`). El modelo decide qué herramienta llamar leyendo las descripciones de las tools.

## Contrato (no negociable, de `mission.md`)

```bash
python3 agente.py --preguntas datos/preguntas_agente_dev.jsonl --salida respuestas.jsonl
```

- Entrada: JSONL con `{"id": "A01", "pregunta": "...", "herramientas_esperadas": [...], "respuesta_referencia": "..."}`. El agente **solo puede leer `id` y `pregunta`**: `herramientas_esperadas` y `respuesta_referencia` son del evaluador, usarlas sería hacer trampa.
- Salida: una línea por pregunta, `{"id": "A01", "respuesta": "...", "contextos": ["...", ...], "herramientas": ["buscar_documentos", ...]}`.
- `contextos`: **todo** lo que el agente recibió de sus herramientas, como texto (fragmentos del corpus y JSON de la API).
- `herramientas`: los nombres de las herramientas que efectivamente se llamaron.

### Nombres exactos de las herramientas

El evaluador compara por nombre, así que estos strings son parte del contrato:

| Herramienta | Fuente | Parámetro |
|---|---|---|
| `buscar_documentos` | recuperador de la parte 1 | `consulta: str` |
| `consultar_camas` | `GET /camas` | `sector: str` |
| `consultar_guardia` | `GET /guardia` | `especialidad: str` |
| `consultar_turnos` | `GET /turnos` | `especialidad: str` |
| `consultar_farmacia` | `GET /farmacia` | `medicamento: str` |
| `consultar_espera` | `GET /espera` | (ninguno) |

## Cómo puntúa el evaluador (leído de `evaluar/evaluar.py`, no modificar)

- **ruteo** (sin LLM, gratis): `|esperadas ∩ usadas| / |esperadas|` por pregunta. Es un **recall de herramientas**: llamar herramientas de más no lo baja, pero sí ensucia los contextos y por lo tanto baja `context_relevance`. Meta del enunciado: ruteo cercano a 1.
- **Juez LLM** (`google/gemini-3.7-flash`, temperatura 0, JSON schema estricto), tres notas de 1 a 5:
  - `context_relevance`: los contextos traen lo necesario **sin ruido de más**. Consecuencia directa de diseño: no volcar los 8 fragmentos del recuperador si con 3 alcanza, y no llamar herramientas por las dudas.
  - `faithfulness`: se juzga **solo contra los contextos**, no contra la referencia. Consecuencia: la respuesta no puede agregar nada que no esté en lo que devolvieron las herramientas — ni siquiera datos correctos de conocimiento general. Si una herramienta falla, decirlo, no rellenar.
  - `answer_relevance`: contesta lo que se preguntó, completa. Las preguntas mixtas (A10, A11, A12) tienen **dos partes**: contestar una sola baja esta nota.
- Criterio de éxito del enunciado: ruteo ≈ 1 y las tres notas > 4 en `dev`.

## Las 12 preguntas dev, por tipo

- **Solo documentos** (A01–A04): `buscar_documentos`.
- **Solo API** (A05–A09): una herramienta de API cada una (camas, guardia, turnos, farmacia, espera).
- **Mixtas** (A10–A12): API + documentos. Son las que definen la nota: exigen que el modelo encadene dos llamadas y que la respuesta cubra las dos mitades.

Estas 12 son de desarrollo; la cátedra evalúa con preguntas ocultas del mismo tipo. **No hardcodear nada específico de estas preguntas** (ni sinónimos a medida, ni mapeos de "nene" → pediatría).

## Dependencia con la parte 1 y su interfaz

La única pieza de la parte 2 que depende de la parte 1 es el cuerpo de `buscar_documentos`. Para poder avanzar en paralelo se fija ahora la interfaz, y se trabaja contra un stub hasta que `recuperar.py` exista.

**Interfaz acordada** — `recuperar.py` expone, además de su CLI, una función a nivel de módulo:

```python
def buscar(consulta: str, top_k: int | None = None) -> list[str]:
    """Devuelve los fragmentos más relevantes del corpus, en orden de relevancia descendente.
    top_k=None usa la configuración ganadora fija de la parte 1."""
```

- Devuelve **texto crudo del corpus** (el evaluador de la parte 1 compara substrings literales, así que los fragmentos ya vienen sin reformatear).
- Carga perezosa: el modelo de embeddings se carga la primera vez que se llama, no al importar, para que los tests de la parte 2 no paguen el costo del encoder.
- `herramientas/documentos.py` encapsula esta dependencia: intenta `import recuperar`; si no existe, usa un stub que devuelve fragmentos sintéticos y avisa por `stderr`. Así la parte 2 corre end-to-end hoy y el día que aparezca `recuperar.py` no hay que tocar nada más.

## Diseño

### Estructura de código

```
agente.py                      # CLI de la parte 2: arma el modelo, corre el loop, escribe salida y log
herramientas/
  __init__.py
  api_hospital.py              # cliente HTTP de api/servidor.py (solo stdlib: urllib)
  documentos.py                # adaptador al recuperador de la parte 1 (+ stub mientras no exista)
  tools.py                     # las 6 tools de LangChain (@tool) sobre los módulos de arriba
  registro.py                  # log .md de la corrida (evidencia obligatoria)
tests/
  test_api_hospital.py
  test_documentos.py
  test_tools.py
  test_registro.py
  test_agente.py
```

Las funciones "puras" viven en `api_hospital.py` / `documentos.py` y las tools de LangChain son una capa fina encima. Esto es a propósito: en la parte 3, `servidor_mcp.py` va a exponer **las mismas funciones** como herramientas MCP sin duplicar lógica.

### El loop del agente

LangChain, con el loop escrito a mano (no `AgentExecutor`) para poder registrar exactamente lo que pide la consigna: argumentos, resultados y usage de cada llamada.

```
mensajes = [SystemMessage(...), HumanMessage(pregunta)]
repetir hasta N vueltas:
    respuesta = modelo_con_tools.invoke(mensajes)      # registrar usage
    si no hay tool_calls: terminar, esa es la respuesta final
    para cada tool_call: ejecutar la tool, guardar (nombre, args, resultado) y appendear ToolMessage
```

- Modelo: `ChatOpenAI(model="deepseek/deepseek-v4-flash-0731", base_url="https://openrouter.ai/api/v1", api_key=$OPENROUTER_API_KEY, temperature=0)`.
- `temperature=0` para que las corridas sean lo más reproducibles posible entre evaluaciones.
- Se pide el costo real a OpenRouter con `extra_body={"usage": {"include": True}}`; si no viene, se estima con los precios del enunciado (USD 0,04 / 0,64 por millón).
- Tope de vueltas (`MAX_VUELTAS = 6`) para que un modelo que se queda en loop no queme créditos.
- Si una tool falla (API caída, sector inexistente), el error vuelve como resultado de la tool y el modelo se corrige solo — la API está diseñada para eso: devuelve la lista de opciones válidas.

### El system prompt

Tiene que empujar tres cosas que el juez mide:

1. Responder **solo** con lo que devolvieron las herramientas; si falta el dato, decir que no se pudo obtener (protege `faithfulness`).
2. Contestar **todas** las partes de la pregunta, encadenando herramientas cuando haga falta (protege `answer_relevance` en A10–A12).
3. No llamar herramientas innecesarias (protege `context_relevance`).

Además: fecha de hoy, respuestas breves y en español rioplatense neutro, sin inventar teléfonos ni horarios.

### Descripciones de las tools

Es el punto donde se juega el ruteo: el modelo elige leyendo las descripciones. Cada una tiene que decir **qué devuelve y cuándo usarla**, con las opciones válidas cuando el conjunto es cerrado (sectores, especialidades), y marcar explícitamente que el estado del día (camas, guardias, turnos, stock, espera) **no está en los documentos** y que las normas y procedimientos **no están en la API**.

### Contextos

Cada resultado de herramienta se guarda tal cual (texto) y se vuelca a `contextos` en orden de llamada. No se resume ni se recorta: el evaluador pide "todo lo que el agente recibió de sus herramientas". El control de ruido se hace **antes** (top-k del recuperador, no llamar tools de más), no filtrando el log.

### Log de la corrida (evidencia obligatoria)

Un `.md` por corrida en `experimentos/logs/agente_<timestamp>.md`. Sin este archivo la parte vale cero. Por pregunta: el id y el texto, cada llamada a herramienta con sus argumentos y su resultado, la respuesta final, y el usage de cada llamada al modelo (tokens de entrada/salida y costo). Al final, totales de la corrida (tokens, costo, duración).

## Plan TDD

Todo lo que se pueda testear sin red se testea sin red.

1. `test_api_hospital.py` — levanta `api/servidor.py` en un puerto libre (fixture de sesión) y verifica: las 5 rutas devuelven lo esperado, los nombres con y sin tildes/mayúsculas/espacios funcionan, y un sector inexistente devuelve un error **con la lista de opciones** (el agente depende de eso para corregirse).
2. `test_documentos.py` — el adaptador usa `recuperar.buscar` cuando el módulo existe (inyectado en el test) y cae al stub cuando no, sin romper.
3. `test_tools.py` — las 6 tools existen con los **nombres exactos** del contrato, tienen descripción no vacía, y su schema declara los parámetros esperados.
4. `test_registro.py` — el log `.md` generado contiene pregunta, llamadas con argumentos y resultados, respuesta y usage.
5. `test_agente.py` — el loop corre contra un **modelo falso** que emite `tool_calls` scripteadas: verifica que ejecuta las tools, que corta cuando no hay más llamadas, que respeta `MAX_VUELTAS`, y que la línea JSONL de salida tiene exactamente los cuatro campos del contrato.
6. Recién con todo en verde, la corrida real contra OpenRouter (cuesta plata: una sola vez por cambio que valga la pena medir).

## Estado de la implementación

Hecho y en verde (43 tests, sin red): el cliente de la API, el adaptador al recuperador con su stub, las 6 tools, el loop de tool calling, la salida JSONL y el log `.md`.

Desvíos respecto del diseño de arriba, cerrados durante la implementación:

- El loop vive en `agente.py` y no en un módulo aparte: `agente_mcp.py` (parte 3) va a importar `responder`/`correr` de acá, que no tienen nada específico de las tools locales — reciben el catálogo de herramientas por parámetro.
- Las listas de valores válidos (sectores, especialidades) quedaron escritas en los docstrings de las tools, no armadas por `.format()` a posteriori.

Smoke test real contra OpenRouter (1 pregunta, A05): el agente llamó a `consultar_camas`, contestó lo mismo que la respuesta de referencia y OpenRouter devolvió el costo real de cada llamada (USD 0,000181 la pregunta, ~USD 0,002 proyectado para las 12). Es decir: los costos del log son reales, no estimados.

## Qué queda pendiente de la parte 1

- [ ] Enchufar `recuperar.buscar` real en `herramientas/documentos.py` (hoy: stub).
- [ ] Ajustar el `top_k` que usa `buscar_documentos` según lo que rinda en la evaluación del agente: el óptimo para el juez puede no ser el mismo que el óptimo de la parte 1 (allá penaliza precision de fragmentos, acá penaliza ruido en los contextos).
- [ ] Corrida real del benchmark + `respuestas.jsonl.eval.json` + análisis de fallos en `INFORME.md`.

## Decisiones abiertas

- [ ] ¿Conviene que `buscar_documentos` acepte un `top_k` que el modelo pueda elegir? Riesgo: el modelo pide 10 y ensucia los contextos. Default: no exponerlo, fijarlo del lado nuestro.
- [ ] ¿Reintento automático si el modelo no llama ninguna herramienta en preguntas que claramente la necesitan? Preferencia inicial: no — sería tunear contra `dev`.
