# SPEC — Parte 1: RAG vectorial (`recuperar.py`)

Estado: borrador, antes de escribir código. Fuente de verdad de la consigna: `mission.md` §"Parte 1". Este documento fija las decisiones de diseño y el plan de experimentos antes de tocar código, según la metodología de `CLAUDE.md`.

## Objetivo

Dado un corpus de 20 documentos Markdown (`datos/corpus/`), construir un recuperador que, para cada pregunta, devuelva los fragmentos de texto más relevantes para responderla. Es la base de la herramienta `buscar_documentos` que va a usar el agente en las partes 2 y 3.

## Contrato (no negociable, de `mission.md`)

```bash
python3 recuperar.py --preguntas datos/preguntas_recuperacion_dev.jsonl --salida resultados.jsonl
```

- Entrada: JSONL con `{"id": "R01", "pregunta": "...", "evidencia": ["...", ...]}` (20 preguntas en `dev`).
- Salida: JSONL con una línea por pregunta, `{"id": "R01", "fragmentos": ["texto", "texto", ...]}`, en orden de relevancia descendente.
- La configuración ganadora (encoder, chunking, top-k, umbral) queda fija en código o en un archivo de config — la cátedra corre este mismo comando sobre preguntas de test ocultas, sin retocar nada.

## Cómo puntúa el evaluador (leído de `evaluar/evaluar.py`, no modificar)

Esto condiciona el diseño, así que se deja explícito:

- Normaliza texto con NFKC + minúsculas + colapso de espacios, tanto en `evidencia` como en los `fragmentos` devueltos.
- **Recall:** proporción de frases de `evidencia` que aparecen como **substring literal** dentro de *algún* fragmento devuelto (no similitud semántica, no fuzzy match).
- **Precision:** proporción de fragmentos devueltos que contienen *alguna* frase de evidencia como substring.
- **context_relevance:** media armónica de recall y precision, promediada sobre las preguntas. Es la métrica a maximizar.
- También registra MRR y caracteres totales devueltos, pero no son el criterio de éxito.

**Implicancia directa para el chunking:** los fragmentos tienen que conservar el texto del corpus tal cual, sin resumir ni reformatear — si un chunk corta una oración a la mitad y la frase de evidencia queda partida entre dos fragmentos, el evaluador la cuenta como no encontrada aunque el contenido esté "cerca". Cortar por oración completa (o por sección) es más seguro que cortar por cantidad fija de caracteres sin cuidado.

## Datos

- `datos/corpus/`: 20 archivos Markdown, ~248 líneas en total (corpus chico). Estructura inconsistente entre documentos: 8 no tienen subtítulos `##`, el resto tiene entre 2 y 6 secciones `##` bajo un único `#` título.
- `datos/preguntas_recuperacion_dev.jsonl`: 20 preguntas dev, cada una con 1+ frases de `evidencia` textuales del corpus.
- El conjunto de test de la cátedra es privado, mismo formato, mismos documentos. **No tunear a mano contra las 20 preguntas dev** más allá de lo razonable — el enunciado advierte que overfittear a dev rinde peor en test.

## Diseño propuesto

### Pipeline

```
corpus/*.md → chunker → [chunks de texto] → encoder → [embeddings] → índice en memoria (numpy, cosine)
pregunta → encoder → embedding → top-k por similitud coseno ≥ umbral → fragmentos ordenados
```

Todo en memoria con NumPy — el corpus es chico (248 líneas), no hace falta una vector DB.

### Chunking — variantes a probar

1. **Por sección Markdown:** cada `##` (o el documento completo si no tiene subtítulos) es un chunk. Respeta límites de oración por construcción.
2. **Por tamaño fijo con solapamiento:** ventana de N caracteres/tokens con overlap M, cortando en el límite de oración más cercano (nunca a mitad de frase) para no romper substrings de evidencia.
3. Registrar tamaño de chunk resultante (chars) por variante, para relacionarlo con precision/recall.

### Encoders a comparar (mínimo 3, todos CPU)

| Encoder | Tipo | Pooling |
|---|---|---|
| `dccuchile/bert-base-spanish-wwm-cased` (o `google-bert/bert-base-multilingual-cased`) | **Baseline obligatoria** — BERT sin ajustar para similitud | promedio de tokens de la última capa |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | sentence-embedding | pooling propio del modelo |
| `intfloat/multilingual-e5-small` (o `-base`) | sentence-embedding, requiere prefijos `query: ` / `passage: ` | pooling propio del modelo |

Cuarto opcional si da tiempo: `BAAI/bge-m3`.

### Top-k y umbral

Barrer top-k ∈ {3, 5, 8} y umbral de coseno ∈ {sin umbral, 0.3, 0.5} por encoder/chunking ganador, para entender el trade-off recall/precision que describe la consigna (pocos fragmentos pierden evidencia, muchos bajan precisión).

### Opcional (si el tiempo alcanza)

- Anteponer título del documento + título de sección al texto del chunk antes de embeder (metadata).
- Reranking con cross-encoder sobre los top-N candidatos antes de cortar a top-k.

## Plan de experimentos y evidencia

- Cada combinación probada (encoder × chunking × top-k × umbral) se corre con el contrato real y se evalúa:
  ```bash
  python3 recuperar.py --preguntas datos/preguntas_recuperacion_dev.jsonl --salida experimentos/<slug>.jsonl
  python3 evaluar/evaluar.py recuperacion --preguntas datos/preguntas_recuperacion_dev.jsonl --resultados experimentos/<slug>.jsonl
  ```
  Esto genera `experimentos/<slug>.jsonl.eval.json` automáticamente (requisito de la consigna: sin este archivo, la fila no cuenta).
- Convención de nombres: `<slug>` = `<encoder-corto>_<chunking>_k<top-k>_u<umbral>`, ej. `e5small_seccion_k5_u030`.
- Mantener una tabla en `INFORME.md` (parte 1) con una fila por experimento y su `context_relevance`, recall y precision, referenciando el `.eval.json` correspondiente.
- Meta explícita: superar con claridad el baseline BERT (la línea de base léxica ingenua del enunciado saca 0.35 — no es el baseline a superar, es solo referencia de piso).

## Estructura de código propuesta

```
recuperar.py              # CLI: --preguntas --salida, carga config, corre pipeline
config_recuperador.py     # (o config.yaml) config ganadora fija: encoder, chunking, top-k, umbral
rag/
  chunking.py             # las variantes de chunking, testeadas por separado
  embeddings.py           # wrapper de carga de encoder + encode(textos) -> np.ndarray
  indice.py               # similitud coseno + top-k + umbral
experimentos/
  <slug>.jsonl
  <slug>.jsonl.eval.json
```

## Plan TDD (antes de correr el pipeline completo)

1. Test de `chunking.py`: dado un doc Markdown de ejemplo, verificar que ninguna oración queda partida entre dos chunks y que la concatenación de chunks reconstruye el texto original (sin pérdida de contenido).
2. Test de `embeddings.py`: dado un batch chico de textos, el encoder devuelve un array de shape `(n, d)` con normas ~unitarias (si se normaliza para coseno).
3. Test de `indice.py`: dado un set sintético de embeddings y un umbral, el top-k respeta orden descendente de similitud y descarta por debajo del umbral.
4. Test de integración chico: 2-3 preguntas de `preguntas_recuperacion_dev.jsonl` corridas end-to-end, verificando que `resultados.jsonl` tiene el formato exacto que espera `evaluar.py` (parseable, campos correctos).
5. Recién después de estos tests en verde, correr la matriz completa de experimentos.

## Criterio de éxito (de `mission.md`)

- La configuración entregada le gana con claridad a la baseline de BERT sin ajustar.
- El informe explica, con los números de la tabla de experimentos, por qué ganó el encoder elegido.

## Decisiones abiertas (a resolver durante la implementación, actualizar este archivo cuando se cierren)

- [ ] ¿Chunking final: por sección Markdown o por tamaño fijo? — depende de los resultados del barrido.
- [ ] ¿Se usa metadata (título de doc/sección antepuesto)? — probar con y sin, comparar `context_relevance`.
- [ ] ¿Vale la pena el reranking con cross-encoder dado el tamaño chico del corpus? — evaluar costo/beneficio en tiempo vs. mejora.
- [ ] Formato del archivo de config ganadora: ¿constantes en `recuperar.py` o un `config.yaml`/`config.json` separado?
