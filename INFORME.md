# Informe — RAG, MCP y Transformers en el Hospital Arroyo Claro

## Parte 1: RAG vectorial

### Configuración entregada

Fijada en `config_recuperador.json` (la lee `recuperar.py` sin flags):

| Encoder | Chunking | Metadatos | top-k | Umbral |
|---|---|---|---|---|
| `BAAI/bge-m3` | una sección `##` por fragmento (el documento entero si no tiene subtítulos) | título del documento + título de sección antepuestos **al embeber** (el fragmento devuelto es el texto literal) | 1 | sin umbral |

Resultado con el contrato real (`resultados.jsonl.eval.json`):

| context_relevance | recall | precision | MRR | caracteres por pregunta |
|---|---|---|---|---|
| **1.000** | 1.000 | 1.000 | 1.000 | 296 |

Contra la línea de base obligatoria (BERT sin ajustar, promedio de tokens de la última capa), con el mismo chunking:
`beto_seccion_k1` = 0.300, `mbert_seccion_k1` = 0.250, y el mejor BERT de toda la matriz (`beto_ventana300_k1`) = 0.600.

### Cómo se experimentó

`experimentos/correr_experimentos.py` recorre la matriz en tres etapas. Cada configuración escribe `experimentos/<slug>.jsonl` y su `.eval.json` lo genera `evaluar/evaluar.py` sin modificar. En total son 136 configuraciones, con su `.eval.json` cada una. Los logs de las corridas están en `experimentos/logs/`.

- **Etapa A:** 6 encoders × 7 chunkings × k ∈ {1, 3}, sin metadatos ni umbral.
- **Etapa B:** metadatos con los 4 encoders de oraciones × 6 chunkings; k = 2; y k = 3 con margen relativo al mejor coseno (0,02 y 0,05).
- **Etapa C:** umbral absoluto de coseno (0,5 / 0,6 / 0,7) con k = 3, y reranking con cross-encoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` sobre los 10 mejores por coseno).

Slug: `<encoder>_<chunking>[_meta]_k<k>[_u<umbral×100>][_m<margen×100>][_rerank]`.

Chunkings: `seccion` (una sección `##`), `parrafo` (bloques separados por línea en blanco), `oracionN` (ventanas de N oraciones con solapamiento de 1, sin cruzar secciones), `ventanaN` (≈N caracteres cortando siempre entre oraciones, con solapamiento, ignorando la estructura). Ningún chunker corta una oración a la mitad (hay un test para eso), porque el evaluador busca la evidencia como substring literal.

### Por qué ganó lo que ganó

**1. top-k = 1.** En `dev` cada pregunta tiene una sola frase de evidencia, así que cada fragmento extra puede sumar como mucho recall y siempre baja la precisión. Con el top-1 correcto, k = 2 tiene un techo de CR = 0,667. Promedio de los 4 encoders de oraciones, sin metadatos:

| Chunking | CR k=1 | CR k=3 | CR k=1 con metadatos | caracteres (k=1) |
|---|---|---|---|---|
| seccion | 0.812 | 0.450 | **0.938** | 287 |
| parrafo | 0.812 | 0.450 | 0.912 | 215 |
| oracion1 | 0.588 | 0.381 | — | 105 |
| oracion2 | 0.800 | 0.539 | 0.850 | 190 |
| oracion3 | 0.812 | 0.474 | 0.925 | 238 |
| ventana300 | 0.825 | 0.536 | 0.863 | 337 |
| ventana600 | 0.875 | 0.506 | 0.875 | 532 |

El margen relativo y el umbral absoluto son formas de devolver "1 o más según la confianza". El mejor caso (`bgem3_seccion_meta_k3_u070`) empata con k = 1 porque en la práctica siempre deja uno solo, y el resto queda por debajo. Por eso se entrega el k = 1 fijo, que es más simple.

**2. Chunking por sección + metadatos.** Las oraciones sueltas (`oracion1`) pierden contexto: "Se requiere ayuno de sólidos de 8 horas" no dice de qué estudio habla. Las ventanas grandes (`ventana600`) aciertan más sin metadatos porque arrastran el contexto, pero devuelven casi el doble de texto. La clave estuvo en los fallos de `bgem3_seccion_k1` (R01 y R02). La información que distingue la respuesta está en el **título de la sección** ("Unidad de terapia intensiva de adultos", "Endoscopía digestiva alta"), que el fragmento no contiene. Al anteponer título y sección solo al texto que se embebe, esos dos casos se resuelven y la sección pasa a ser el mejor chunking (0,812 → 0,938 de promedio). Es una mejora estructural, que no depende de las preguntas de `dev`: el corpus entero usa los subtítulos para decir de qué trata cada sección.

**3. El encoder.** Con k = 1, context_relevance promedio sobre todos los chunkings:

| Encoder | Tipo | sin metadatos (7 chunkings) | con metadatos (6 chunkings) | mejor |
|---|---|---|---|---|
| `mbert` (`bert-base-multilingual-cased`) | BERT sin ajustar, mean pooling | 0.207 | — | 0.25 |
| `beto` (`bert-base-spanish-wwm-cased`) | BERT sin ajustar, mean pooling | 0.393 | 0.475 (2) | 0.60 |
| `minilm` (paraphrase-multilingual-MiniLM-L12-v2) | oraciones | 0.743 | 0.850 | 0.90 |
| `e5small` | oraciones | 0.757 | 0.867 | 0.90 |
| `e5base` | oraciones | 0.807 | 0.942 | 1.00 |
| `bgem3` | oraciones | **0.850** | 0.917 | 1.00 |

- **BERT sin ajustar pierde por mucho**, incluso contra el recuperador léxico ingenuo del enunciado (0,35). El promedio de los vectores de tokens de un BERT preentrenado solo con MLM no está entrenado para que "pregunta" y "pasaje que la responde" queden cerca. Todos los vectores terminan en un cono estrecho, con cosenos altos para cualquier par, y lo que domina es el solapamiento superficial de tokens. BETO, que es monolingüe en español, le gana a mBERT, pero ninguno pasa de 0,60.
- **Entre los encoders de oraciones**, `e5base` y `bgem3` son los mejores y los dos llegan a 1,0 con la configuración entregada. Elegimos **bge-m3** por robustez:
  1. Es el mejor sin metadatos (0,850 contra 0,807) y el que menos varía entre chunkings: 0,90 en cuatro chunkings distintos.
  2. Separa mejor lo relevante de lo que no lo es. Con margen relativo 0,02 saca 0,967 contra 0,867 de e5base, y con umbral 0,70 sigue en 1,0 mientras que e5base cae a 0,50. En e5 los cosenos quedan comprimidos (todo parece parecido), así que cualquier corte por similitud es frágil.
  3. La diferencia a favor de e5base con metadatos (0,942 contra 0,917) equivale a medio acierto sobre 20 preguntas. Pesa menos que la estabilidad de los otros dos puntos.

  Costo de la elección: bge-m3 es ~2,2 GB y más lento de cargar que e5base (~1,1 GB). Si hiciera falta, `e5base` con la misma config da el mismo 1,0 en `dev`.
- **El reranking con cross-encoder no ayudó** (0,80–0,90): el cross-encoder multilingüe chico (mMARCO) rankea peor que bge-m3 solo en este dominio.

### Riesgos para el conjunto de test

- **20 preguntas es poco:** cada pregunta vale 0,05 de CR, y varias configuraciones están a una pregunta de distancia. Elegimos priorizando lo que es estable en toda la matriz (sección + metadatos + un encoder de oraciones grande), no el máximo aislado. El caso de `e5base_ventana600_k1`, que saca 0,95 sin metadatos mientras que sus vecinos sacan 0,80–0,85, se descartó como ruido.
- **k = 1 asume una evidencia por pregunta.** Si el test trae preguntas con dos evidencias en secciones distintas, se pierde recall. Aceptamos ese riesgo porque la consigna dice que el test tiene "la misma forma" que `dev`, y en `dev` las 20 tienen una sola evidencia.
- **Para el agente (partes 2 y 3)**, `recuperar.buscar(consulta, top_k=...)` (la interfaz acordada en `specs/parte2-agente.md`) permite pedir más fragmentos, porque al agente le sirve más contexto que al evaluador de la parte 1.

### Tabla completa de experimentos

Una fila por configuración, ordenadas por context_relevance. Cada fila enlaza a su `.eval.json`.

| # | Configuración (slug) | context_relevance | recall | precision | MRR | k medio | caracteres |
|---|---|---|---|---|---|---|---|
| 1 | [`bgem3_seccion_meta_k1`](experimentos/bgem3_seccion_meta_k1.jsonl.eval.json) | 1.0000 | 1.000 | 1.000 | 1.000 | 1.00 | 296 |
| 2 | [`bgem3_seccion_meta_k3_u070`](experimentos/bgem3_seccion_meta_k3_u070.jsonl.eval.json) | 1.0000 | 1.000 | 1.000 | 1.000 | 1.00 | 296 |
| 3 | [`e5base_seccion_meta_k1`](experimentos/e5base_seccion_meta_k1.jsonl.eval.json) | 1.0000 | 1.000 | 1.000 | 1.000 | 1.00 | 296 |
| 4 | [`bgem3_seccion_meta_k3_m002`](experimentos/bgem3_seccion_meta_k3_m002.jsonl.eval.json) | 0.9667 | 1.000 | 0.950 | 1.000 | 1.10 | 328 |
| 5 | [`bgem3_oracion3_meta_k1`](experimentos/bgem3_oracion3_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 242 |
| 6 | [`bgem3_parrafo_meta_k1`](experimentos/bgem3_parrafo_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 217 |
| 7 | [`e5base_oracion3_meta_k1`](experimentos/e5base_oracion3_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 236 |
| 8 | [`e5base_parrafo_meta_k1`](experimentos/e5base_parrafo_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 217 |
| 9 | [`e5base_ventana300_meta_k1`](experimentos/e5base_ventana300_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 338 |
| 10 | [`e5base_ventana600_k1`](experimentos/e5base_ventana600_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 547 |
| 11 | [`e5base_ventana600_meta_k1`](experimentos/e5base_ventana600_meta_k1.jsonl.eval.json) | 0.9500 | 0.950 | 0.950 | 0.950 | 1.00 | 553 |
| 12 | [`bgem3_seccion_meta_k3_m005`](experimentos/bgem3_seccion_meta_k3_m005.jsonl.eval.json) | 0.9417 | 1.000 | 0.917 | 1.000 | 1.20 | 342 |
| 13 | [`bgem3_oracion2_k1`](experimentos/bgem3_oracion2_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 192 |
| 14 | [`bgem3_oracion3_k1`](experimentos/bgem3_oracion3_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 236 |
| 15 | [`bgem3_parrafo_k1`](experimentos/bgem3_parrafo_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 215 |
| 16 | [`bgem3_seccion_k1`](experimentos/bgem3_seccion_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 289 |
| 17 | [`bgem3_seccion_meta_k1_rerank`](experimentos/bgem3_seccion_meta_k1_rerank.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 287 |
| 18 | [`bgem3_ventana600_meta_k1`](experimentos/bgem3_ventana600_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 549 |
| 19 | [`e5base_seccion_meta_k1_rerank`](experimentos/e5base_seccion_meta_k1_rerank.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 287 |
| 20 | [`e5small_oracion3_meta_k1`](experimentos/e5small_oracion3_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 244 |
| 21 | [`e5small_seccion_meta_k1`](experimentos/e5small_seccion_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 301 |
| 22 | [`e5small_ventana600_meta_k1`](experimentos/e5small_ventana600_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 559 |
| 23 | [`minilm_oracion2_meta_k1`](experimentos/minilm_oracion2_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 195 |
| 24 | [`minilm_oracion3_meta_k1`](experimentos/minilm_oracion3_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 244 |
| 25 | [`minilm_parrafo_meta_k1`](experimentos/minilm_parrafo_meta_k1.jsonl.eval.json) | 0.9000 | 0.900 | 0.900 | 0.900 | 1.00 | 227 |
| 26 | [`bgem3_ventana600_meta_k3_m005`](experimentos/bgem3_ventana600_meta_k3_m005.jsonl.eval.json) | 0.8983 | 1.000 | 0.858 | 0.942 | 1.50 | 829 |
| 27 | [`bgem3_seccion_meta_k3_u060`](experimentos/bgem3_seccion_meta_k3_u060.jsonl.eval.json) | 0.8833 | 1.000 | 0.842 | 1.000 | 1.45 | 384 |
| 28 | [`bgem3_ventana600_meta_k3_m002`](experimentos/bgem3_ventana600_meta_k3_m002.jsonl.eval.json) | 0.8817 | 0.950 | 0.850 | 0.925 | 1.30 | 716 |
| 29 | [`e5base_seccion_meta_k3_m002`](experimentos/e5base_seccion_meta_k3_m002.jsonl.eval.json) | 0.8667 | 1.000 | 0.817 | 1.000 | 1.50 | 406 |
| 30 | [`e5base_ventana600_meta_k3_m002`](experimentos/e5base_ventana600_meta_k3_m002.jsonl.eval.json) | 0.8567 | 0.950 | 0.817 | 0.950 | 1.60 | 845 |
| 31 | [`bgem3_oracion2_meta_k1`](experimentos/bgem3_oracion2_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 179 |
| 32 | [`bgem3_ventana300_k1`](experimentos/bgem3_ventana300_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 338 |
| 33 | [`bgem3_ventana300_meta_k1`](experimentos/bgem3_ventana300_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 340 |
| 34 | [`bgem3_ventana600_k1`](experimentos/bgem3_ventana600_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 544 |
| 35 | [`bgem3_ventana600_meta_k1_rerank`](experimentos/bgem3_ventana600_meta_k1_rerank.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 518 |
| 36 | [`e5base_oracion2_meta_k1`](experimentos/e5base_oracion2_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 186 |
| 37 | [`e5base_oracion3_k1`](experimentos/e5base_oracion3_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 234 |
| 38 | [`e5base_seccion_k1`](experimentos/e5base_seccion_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 287 |
| 39 | [`e5base_ventana300_k1`](experimentos/e5base_ventana300_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 337 |
| 40 | [`e5small_parrafo_meta_k1`](experimentos/e5small_parrafo_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 222 |
| 41 | [`e5small_ventana300_meta_k1`](experimentos/e5small_ventana300_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 341 |
| 42 | [`e5small_ventana600_k1`](experimentos/e5small_ventana600_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 541 |
| 43 | [`minilm_seccion_meta_k1`](experimentos/minilm_seccion_meta_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 290 |
| 44 | [`minilm_ventana300_k1`](experimentos/minilm_ventana300_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 337 |
| 45 | [`minilm_ventana600_k1`](experimentos/minilm_ventana600_k1.jsonl.eval.json) | 0.8500 | 0.850 | 0.850 | 0.850 | 1.00 | 497 |
| 46 | [`e5base_parrafo_k1`](experimentos/e5base_parrafo_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 208 |
| 47 | [`e5base_ventana600_meta_k1_rerank`](experimentos/e5base_ventana600_meta_k1_rerank.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 515 |
| 48 | [`e5small_oracion2_k1`](experimentos/e5small_oracion2_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 192 |
| 49 | [`e5small_oracion2_meta_k1`](experimentos/e5small_oracion2_meta_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 183 |
| 50 | [`e5small_parrafo_k1`](experimentos/e5small_parrafo_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 214 |
| 51 | [`e5small_seccion_k1`](experimentos/e5small_seccion_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 288 |
| 52 | [`minilm_ventana300_meta_k1`](experimentos/minilm_ventana300_meta_k1.jsonl.eval.json) | 0.8000 | 0.800 | 0.800 | 0.800 | 1.00 | 337 |
| 53 | [`e5base_oracion2_k1`](experimentos/e5base_oracion2_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 187 |
| 54 | [`e5small_oracion3_k1`](experimentos/e5small_oracion3_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 240 |
| 55 | [`e5small_ventana300_k1`](experimentos/e5small_ventana300_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 337 |
| 56 | [`minilm_oracion2_k1`](experimentos/minilm_oracion2_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 187 |
| 57 | [`minilm_oracion3_k1`](experimentos/minilm_oracion3_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 239 |
| 58 | [`minilm_parrafo_k1`](experimentos/minilm_parrafo_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 222 |
| 59 | [`minilm_ventana600_meta_k1`](experimentos/minilm_ventana600_meta_k1.jsonl.eval.json) | 0.7500 | 0.750 | 0.750 | 0.750 | 1.00 | 487 |
| 60 | [`minilm_seccion_k1`](experimentos/minilm_seccion_k1.jsonl.eval.json) | 0.7000 | 0.700 | 0.700 | 0.700 | 1.00 | 284 |
| 61 | [`e5base_seccion_meta_k3_m005`](experimentos/e5base_seccion_meta_k3_m005.jsonl.eval.json) | 0.6917 | 1.000 | 0.583 | 1.000 | 2.20 | 586 |
| 62 | [`e5base_ventana600_meta_k2`](experimentos/e5base_ventana600_meta_k2.jsonl.eval.json) | 0.6833 | 0.950 | 0.550 | 0.950 | 2.00 | 1022 |
| 63 | [`bgem3_seccion_meta_k2`](experimentos/bgem3_seccion_meta_k2.jsonl.eval.json) | 0.6667 | 1.000 | 0.500 | 1.000 | 2.00 | 498 |
| 64 | [`bgem3_ventana600_meta_k2`](experimentos/bgem3_ventana600_meta_k2.jsonl.eval.json) | 0.6667 | 0.950 | 0.525 | 0.925 | 2.00 | 1056 |
| 65 | [`e5base_seccion_meta_k2`](experimentos/e5base_seccion_meta_k2.jsonl.eval.json) | 0.6667 | 1.000 | 0.500 | 1.000 | 2.00 | 526 |
| 66 | [`e5base_ventana600_k2`](experimentos/e5base_ventana600_k2.jsonl.eval.json) | 0.6667 | 0.950 | 0.525 | 0.950 | 2.00 | 1026 |
| 67 | [`bgem3_oracion1_k1`](experimentos/bgem3_oracion1_k1.jsonl.eval.json) | 0.6500 | 0.650 | 0.650 | 0.650 | 1.00 | 96 |
| 68 | [`e5base_ventana600_meta_k3_m005`](experimentos/e5base_ventana600_meta_k3_m005.jsonl.eval.json) | 0.6450 | 0.950 | 0.533 | 0.950 | 2.50 | 1288 |
| 69 | [`bgem3_ventana600_k2`](experimentos/bgem3_ventana600_k2.jsonl.eval.json) | 0.6333 | 0.900 | 0.500 | 0.875 | 2.00 | 1058 |
| 70 | [`bgem3_seccion_meta_k3_u050`](experimentos/bgem3_seccion_meta_k3_u050.jsonl.eval.json) | 0.6083 | 1.000 | 0.458 | 1.000 | 2.45 | 569 |
| 71 | [`beto_ventana300_k1`](experimentos/beto_ventana300_k1.jsonl.eval.json) | 0.6000 | 0.600 | 0.600 | 0.600 | 1.00 | 341 |
| 72 | [`bgem3_seccion_k2`](experimentos/bgem3_seccion_k2.jsonl.eval.json) | 0.6000 | 0.900 | 0.450 | 0.900 | 2.00 | 506 |
| 73 | [`e5base_oracion1_k1`](experimentos/e5base_oracion1_k1.jsonl.eval.json) | 0.6000 | 0.600 | 0.600 | 0.600 | 1.00 | 113 |
| 74 | [`e5base_seccion_k2`](experimentos/e5base_seccion_k2.jsonl.eval.json) | 0.6000 | 0.900 | 0.450 | 0.875 | 2.00 | 505 |
| 75 | [`bgem3_ventana300_k3`](experimentos/bgem3_ventana300_k3.jsonl.eval.json) | 0.5750 | 1.000 | 0.417 | 0.908 | 3.00 | 1002 |
| 76 | [`e5base_ventana300_k3`](experimentos/e5base_ventana300_k3.jsonl.eval.json) | 0.5750 | 1.000 | 0.417 | 0.908 | 3.00 | 998 |
| 77 | [`bgem3_oracion2_k3`](experimentos/bgem3_oracion2_k3.jsonl.eval.json) | 0.5550 | 0.900 | 0.417 | 0.900 | 3.00 | 525 |
| 78 | [`e5small_oracion2_k3`](experimentos/e5small_oracion2_k3.jsonl.eval.json) | 0.5550 | 0.900 | 0.417 | 0.842 | 3.00 | 536 |
| 79 | [`e5small_oracion1_k1`](experimentos/e5small_oracion1_k1.jsonl.eval.json) | 0.5500 | 0.550 | 0.550 | 0.550 | 1.00 | 112 |
| 80 | [`minilm_oracion1_k1`](experimentos/minilm_oracion1_k1.jsonl.eval.json) | 0.5500 | 0.550 | 0.550 | 0.550 | 1.00 | 100 |
| 81 | [`bgem3_ventana600_k3`](experimentos/bgem3_ventana600_k3.jsonl.eval.json) | 0.5450 | 1.000 | 0.383 | 0.908 | 3.00 | 1603 |
| 82 | [`e5base_oracion2_k3`](experimentos/e5base_oracion2_k3.jsonl.eval.json) | 0.5300 | 0.850 | 0.400 | 0.800 | 3.00 | 501 |
| 83 | [`e5base_ventana600_k3`](experimentos/e5base_ventana600_k3.jsonl.eval.json) | 0.5200 | 0.950 | 0.367 | 0.950 | 3.00 | 1513 |
| 84 | [`minilm_oracion2_k3`](experimentos/minilm_oracion2_k3.jsonl.eval.json) | 0.5150 | 0.850 | 0.383 | 0.792 | 3.00 | 537 |
| 85 | [`e5small_ventana600_k3`](experimentos/e5small_ventana600_k3.jsonl.eval.json) | 0.5050 | 0.950 | 0.350 | 0.892 | 3.00 | 1554 |
| 86 | [`beto_ventana300_meta_k1`](experimentos/beto_ventana300_meta_k1.jsonl.eval.json) | 0.5000 | 0.500 | 0.500 | 0.500 | 1.00 | 336 |
| 87 | [`e5base_seccion_meta_k3_u050`](experimentos/e5base_seccion_meta_k3_u050.jsonl.eval.json) | 0.5000 | 1.000 | 0.333 | 1.000 | 3.00 | 764 |
| 88 | [`e5base_seccion_meta_k3_u060`](experimentos/e5base_seccion_meta_k3_u060.jsonl.eval.json) | 0.5000 | 1.000 | 0.333 | 1.000 | 3.00 | 764 |
| 89 | [`e5base_seccion_meta_k3_u070`](experimentos/e5base_seccion_meta_k3_u070.jsonl.eval.json) | 0.5000 | 1.000 | 0.333 | 1.000 | 3.00 | 764 |
| 90 | [`e5small_ventana300_k3`](experimentos/e5small_ventana300_k3.jsonl.eval.json) | 0.5000 | 0.850 | 0.367 | 0.800 | 3.00 | 993 |
| 91 | [`minilm_ventana300_k3`](experimentos/minilm_ventana300_k3.jsonl.eval.json) | 0.4950 | 0.900 | 0.350 | 0.875 | 3.00 | 996 |
| 92 | [`bgem3_oracion3_k3`](experimentos/bgem3_oracion3_k3.jsonl.eval.json) | 0.4800 | 0.900 | 0.333 | 0.900 | 3.00 | 664 |
| 93 | [`e5base_oracion3_k3`](experimentos/e5base_oracion3_k3.jsonl.eval.json) | 0.4800 | 0.900 | 0.333 | 0.875 | 3.00 | 635 |
| 94 | [`e5small_oracion3_k3`](experimentos/e5small_oracion3_k3.jsonl.eval.json) | 0.4800 | 0.900 | 0.333 | 0.817 | 3.00 | 666 |
| 95 | [`minilm_oracion3_k3`](experimentos/minilm_oracion3_k3.jsonl.eval.json) | 0.4550 | 0.850 | 0.317 | 0.800 | 3.00 | 676 |
| 96 | [`minilm_ventana600_k3`](experimentos/minilm_ventana600_k3.jsonl.eval.json) | 0.4550 | 0.850 | 0.317 | 0.850 | 3.00 | 1598 |
| 97 | [`beto_oracion2_k1`](experimentos/beto_oracion2_k1.jsonl.eval.json) | 0.4500 | 0.450 | 0.450 | 0.450 | 1.00 | 220 |
| 98 | [`beto_seccion_meta_k1`](experimentos/beto_seccion_meta_k1.jsonl.eval.json) | 0.4500 | 0.450 | 0.450 | 0.450 | 1.00 | 248 |
| 99 | [`bgem3_parrafo_k3`](experimentos/bgem3_parrafo_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.900 | 3.00 | 629 |
| 100 | [`bgem3_seccion_k3`](experimentos/bgem3_seccion_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.900 | 3.00 | 728 |
| 101 | [`e5base_parrafo_k3`](experimentos/e5base_parrafo_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.850 | 3.00 | 590 |
| 102 | [`e5base_seccion_k3`](experimentos/e5base_seccion_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.875 | 3.00 | 723 |
| 103 | [`e5small_parrafo_k3`](experimentos/e5small_parrafo_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.842 | 3.00 | 607 |
| 104 | [`e5small_seccion_k3`](experimentos/e5small_seccion_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.842 | 3.00 | 688 |
| 105 | [`minilm_parrafo_k3`](experimentos/minilm_parrafo_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.817 | 3.00 | 642 |
| 106 | [`minilm_seccion_k3`](experimentos/minilm_seccion_k3.jsonl.eval.json) | 0.4500 | 0.900 | 0.300 | 0.792 | 3.00 | 770 |
| 107 | [`beto_oracion3_k1`](experimentos/beto_oracion3_k1.jsonl.eval.json) | 0.4000 | 0.400 | 0.400 | 0.400 | 1.00 | 247 |
| 108 | [`beto_ventana600_k1`](experimentos/beto_ventana600_k1.jsonl.eval.json) | 0.4000 | 0.400 | 0.400 | 0.400 | 1.00 | 416 |
| 109 | [`bgem3_oracion1_k3`](experimentos/bgem3_oracion1_k3.jsonl.eval.json) | 0.4000 | 0.800 | 0.267 | 0.717 | 3.00 | 260 |
| 110 | [`e5base_oracion1_k3`](experimentos/e5base_oracion1_k3.jsonl.eval.json) | 0.4000 | 0.800 | 0.267 | 0.692 | 3.00 | 299 |
| 111 | [`e5small_oracion1_k3`](experimentos/e5small_oracion1_k3.jsonl.eval.json) | 0.4000 | 0.800 | 0.267 | 0.675 | 3.00 | 294 |
| 112 | [`beto_parrafo_k1`](experimentos/beto_parrafo_k1.jsonl.eval.json) | 0.3500 | 0.350 | 0.350 | 0.350 | 1.00 | 216 |
| 113 | [`minilm_oracion1_k3`](experimentos/minilm_oracion1_k3.jsonl.eval.json) | 0.3250 | 0.650 | 0.217 | 0.600 | 3.00 | 304 |
| 114 | [`beto_ventana300_k3`](experimentos/beto_ventana300_k3.jsonl.eval.json) | 0.3150 | 0.600 | 0.217 | 0.600 | 3.00 | 1024 |
| 115 | [`beto_parrafo_k3`](experimentos/beto_parrafo_k3.jsonl.eval.json) | 0.3000 | 0.600 | 0.200 | 0.433 | 3.00 | 697 |
| 116 | [`beto_seccion_k1`](experimentos/beto_seccion_k1.jsonl.eval.json) | 0.3000 | 0.300 | 0.300 | 0.300 | 1.00 | 264 |
| 117 | [`beto_oracion2_k3`](experimentos/beto_oracion2_k3.jsonl.eval.json) | 0.2950 | 0.500 | 0.217 | 0.475 | 3.00 | 645 |
| 118 | [`beto_oracion3_k3`](experimentos/beto_oracion3_k3.jsonl.eval.json) | 0.2750 | 0.550 | 0.183 | 0.467 | 3.00 | 748 |
| 119 | [`beto_ventana600_k3`](experimentos/beto_ventana600_k3.jsonl.eval.json) | 0.2750 | 0.550 | 0.183 | 0.475 | 3.00 | 1343 |
| 120 | [`mbert_ventana600_k3`](experimentos/mbert_ventana600_k3.jsonl.eval.json) | 0.2650 | 0.500 | 0.183 | 0.367 | 3.00 | 1720 |
| 121 | [`beto_oracion1_k1`](experimentos/beto_oracion1_k1.jsonl.eval.json) | 0.2500 | 0.250 | 0.250 | 0.250 | 1.00 | 125 |
| 122 | [`beto_seccion_k3`](experimentos/beto_seccion_k3.jsonl.eval.json) | 0.2500 | 0.500 | 0.167 | 0.383 | 3.00 | 824 |
| 123 | [`mbert_oracion2_k1`](experimentos/mbert_oracion2_k1.jsonl.eval.json) | 0.2500 | 0.250 | 0.250 | 0.250 | 1.00 | 153 |
| 124 | [`mbert_parrafo_k1`](experimentos/mbert_parrafo_k1.jsonl.eval.json) | 0.2500 | 0.250 | 0.250 | 0.250 | 1.00 | 201 |
| 125 | [`mbert_seccion_k1`](experimentos/mbert_seccion_k1.jsonl.eval.json) | 0.2500 | 0.250 | 0.250 | 0.250 | 1.00 | 235 |
| 126 | [`mbert_ventana600_k1`](experimentos/mbert_ventana600_k1.jsonl.eval.json) | 0.2500 | 0.250 | 0.250 | 0.250 | 1.00 | 567 |
| 127 | [`mbert_ventana300_k3`](experimentos/mbert_ventana300_k3.jsonl.eval.json) | 0.2300 | 0.400 | 0.167 | 0.250 | 3.00 | 989 |
| 128 | [`mbert_oracion2_k3`](experimentos/mbert_oracion2_k3.jsonl.eval.json) | 0.2050 | 0.350 | 0.150 | 0.283 | 3.00 | 487 |
| 129 | [`mbert_oracion3_k1`](experimentos/mbert_oracion3_k1.jsonl.eval.json) | 0.2000 | 0.200 | 0.200 | 0.200 | 1.00 | 222 |
| 130 | [`beto_oracion1_k3`](experimentos/beto_oracion1_k3.jsonl.eval.json) | 0.1750 | 0.350 | 0.117 | 0.300 | 3.00 | 377 |
| 131 | [`mbert_oracion3_k3`](experimentos/mbert_oracion3_k3.jsonl.eval.json) | 0.1750 | 0.350 | 0.117 | 0.267 | 3.00 | 654 |
| 132 | [`mbert_parrafo_k3`](experimentos/mbert_parrafo_k3.jsonl.eval.json) | 0.1750 | 0.350 | 0.117 | 0.300 | 3.00 | 629 |
| 133 | [`mbert_seccion_k3`](experimentos/mbert_seccion_k3.jsonl.eval.json) | 0.1750 | 0.350 | 0.117 | 0.292 | 3.00 | 733 |
| 134 | [`mbert_ventana300_k1`](experimentos/mbert_ventana300_k1.jsonl.eval.json) | 0.1500 | 0.150 | 0.150 | 0.150 | 1.00 | 335 |
| 135 | [`mbert_oracion1_k3`](experimentos/mbert_oracion1_k3.jsonl.eval.json) | 0.1250 | 0.250 | 0.083 | 0.175 | 3.00 | 366 |
| 136 | [`mbert_oracion1_k1`](experimentos/mbert_oracion1_k1.jsonl.eval.json) | 0.1000 | 0.100 | 0.100 | 0.100 | 1.00 | 114 |

## Parte 2: agente con dos fuentes

### Configuración entregada

| Modelo | Framework | Temperatura | Herramientas | `top_k` de `buscar_documentos` | Tope de vueltas |
|---|---|---|---|---|---|
| `deepseek/deepseek-v4-flash-0731` vía OpenRouter | LangChain (`ChatOpenAI` + `@tool`), loop de tool calling propio | 0 | 6 | el de la parte 1 (k = 1) | 6 |

Resultado sobre las 12 preguntas de `dev` (`respuestas.jsonl.eval.json`):

| ruteo | context_relevance | faithfulness | answer_relevance | costo del agente | costo del juez |
|---|---|---|---|---|---|
| **1.000** | **5.00** | **5.00** | **5.00** | USD 0,00313 | USD 0,01782 |

Las tres notas del juez son 5 en las 12 preguntas, y el ruteo es perfecto: cada pregunta llamó exactamente las herramientas esperadas, sin ninguna de más. El criterio de éxito de la consigna (ruteo cercano a 1 y las tres métricas por encima de 4) queda cumplido con margen.

### Diseño: las tres decisiones que movieron la aguja

**1. El loop está escrito a mano, no con `AgentExecutor`.** La consigna pide, como evidencia obligatoria, las llamadas a herramientas con sus argumentos y resultados y el usage de cada llamada al modelo. Con un executor cerrado eso no se ve. El loop de `agente.py` es de quince líneas: invoca el modelo, ejecuta las `tool_calls` que pida, devuelve los resultados como `ToolMessage` y corta cuando el modelo contesta sin pedir más herramientas. De paso, los `contextos` que pide el evaluador salen exactos: son los resultados de las herramientas, en orden de llamada.

**2. Las descripciones de las tools son el mecanismo de ruteo.** El modelo elige leyéndolas, así que cada una dice qué devuelve, cuándo usarla y, sobre todo, **dónde no está el dato**: `buscar_documentos` aclara que el estado del día no está en los documentos, y las tools de API aclaran que las normas y requisitos no están en la API. Ese cruce explícito es lo que hace que las preguntas mixtas (A10, A11, A12) encadenen las dos fuentes solas. Las que tienen un conjunto cerrado de valores (sectores, especialidades) los listan en la descripción, y ante un nombre inexistente la API devuelve las opciones válidas, así que el modelo se corrige sin intervención.

**3. El system prompt protege las tres métricas del juez.** Una regla por métrica: contestar solo con lo que devolvieron las herramientas y decir "no lo pude obtener" antes que completar de memoria (`faithfulness`); usar todas las herramientas que la pregunta necesite antes de contestar (`answer_relevance` en las mixtas); no llamar herramientas que no aporten (`context_relevance`).

### El experimento del `top_k`: más contexto empeoró la nota

La parte 1 entrega k = 1 porque su métrica castiga cada fragmento de más. La intuición al armar el agente era la contraria: que un asistente conversacional necesita más contexto que el evaluador de recuperación, sobre todo en las preguntas mixtas. Lo medimos con las dos corridas completas:

| Corrida | `top_k` | ruteo | context_relevance | faithfulness | answer_relevance | caracteres de contexto | tokens (entrada/salida) | costo agente |
|---|---|---|---|---|---|---|---|---|
| [k=1](experimentos/respuestas_k1.jsonl.eval.json) (entregada) | config de la parte 1 | 1.000 | **5.00** | 5.00 | 5.00 | 3.292 | 41.332 / 2.120 | USD 0,00313 |
| [k=2](experimentos/respuestas_k2.jsonl.eval.json) | 2 | 1.000 | 4.50 | 5.00 | 5.00 | 4.754 (+44 %) | 41.728 / 2.349 | USD 0,00342 |

**La intuición estaba mal.** Pedir dos fragmentos bajó `context_relevance` medio punto y no mejoró nada: `faithfulness` y `answer_relevance` quedaron en 5 en las dos corridas. La penalización es quirúrgica — cae exactamente en las 6 preguntas donde el segundo fragmento es texto ajeno (A01, A02, A03, A04, A10, A12) y no toca las 5 que solo usan la API. El juez lo dice con todas las letras:

> A01: "El primer contexto contiene la información exacta y requerida para responder, **aunque se recuperó un segundo contexto innecesario**."
> A02: "...**aunque se recuperó un segundo fragmento no pertinente sobre vejiga llena**."

El caso que motivó la prueba fue A10 ("¿hay lugar en pediatría y me puedo quedar con él?"). Con k = 1, el fragmento recuperado es la norma **general** de acompañantes ("uno por paciente durante la noche") y no la **específica** de pediatría, que está en otra sección (`visitas.md`: "Madre, padre o tutor pueden permanecer las 24 horas"). Con k = 2 tampoco apareció: el modelo consulta *"acompañante en internación de pediatría"*, y con esa consulta la regla de las 24 horas cae recién en la posición 4 del ranking. O sea que ni siquiera k = 2 arreglaba el caso que lo justificaba, mientras ensuciaba las otras cinco preguntas de documentos.

La conclusión es que los dos criterios empujan para el mismo lado: lo que la parte 1 mide como precisión de fragmentos, el juez del agente lo mide como ruido en los contextos. **Se entrega el `top_k` de la parte 1**, y `herramientas/documentos.py` lo deja explícito con `TOP_K = None`.

Vale anotar el límite de esta conclusión: A10 sigue respondiéndose con la norma general en vez de la de pediatría, y el juez igual le puso 5 en las tres métricas. Con un juez más estricto, o con una pregunta de test donde la diferencia entre la regla general y la específica cambie la respuesta, ese caso se pierde. Arreglarlo de verdad no es cuestión de `top_k` sino del ranking: el fragmento correcto está en el corpus pero el recuperador lo pone cuarto.

### Riesgos para el conjunto de test

- **12 preguntas es muy poco** y las tres notas están en el techo, así que no hay señal para seguir optimizando contra `dev`. Cualquier ajuste más fino sería tunear a ciegas.
- **El ruteo perfecto depende de las descripciones de las tools**, no de las preguntas: no hay ningún mapeo hardcodeado del estilo "nene → pediatría". Una pregunta de test con una especialidad que no esté en la lista de la descripción va a fallar la primera llamada, pero la API devuelve las opciones válidas y el modelo reintenta (el tope de 6 vueltas da lugar a eso).
- **El caso A10** descrito arriba es el punto flojo conocido: preguntas donde existe una regla general y una específica para el sector, y el recuperador devuelve la general.

### Evidencia

- `respuestas.jsonl` y `respuestas.jsonl.eval.json`: la corrida entregada.
- `experimentos/logs/agente_k1.md` y `experimentos/logs/agente_k2.md`: el log de cada corrida, con cada pregunta, cada llamada a herramienta con argumentos y resultado, la respuesta final y el usage (tokens y costo real informado por OpenRouter) de cada llamada al modelo.
- `experimentos/respuestas_k1.jsonl`, `experimentos/respuestas_k2.jsonl` y sus `.eval.json`: las dos corridas comparadas arriba.
- `specs/parte2-agente.md`: el diseño previo, con las decisiones y su justificación.

## Parte 3: las mismas herramientas como servidor MCP

### Configuración entregada

`servidor_mcp.py` expone las 6 herramientas por el SDK oficial `mcp` (`FastMCP`, transporte stdio), como una capa fina sobre los mismos módulos que ya usaba la parte 2 (`herramientas/api_hospital.py` y `herramientas/documentos.py`): no hay ninguna lógica de HTTP ni de recuperación duplicada entre las dos partes.

`agente_mcp.py` no importa esos módulos: carga las 6 tools en tiempo de ejecución con `langchain-mcp-adapters` (`MultiServerMCPClient.get_tools()`, que resuelve `tools/list`) y las llama con `ainvoke` (`tools/call`). El diseño del loop (prompt, tope de 6 vueltas, traza) es el mismo que `agente.py`, pero async: las tools que arma `langchain-mcp-adapters` solo exponen coroutine, porque toda llamada MCP habla con el servidor por stdio. El detalle de esta decisión está en `specs/parte3-mcp.md`, sección "Desvío".

### Comparación con la parte 2

| | `agente.py` (parte 2) | `agente_mcp.py` (parte 3) |
|---|---|---|
| ruteo | 1.000 | 1.000 |
| context_relevance | 5.00 | 5.00 |
| faithfulness | 5.00 | 5.00 |
| answer_relevance | 5.00 | 5.00 |
| tokens entrada/salida | 41332 / 2120 | 42264 / 2213 |
| costo del agente (12 preguntas) | USD 0.003127 | USD 0.003394 |
| costo del juez (evaluación) | — | USD 0.01891 |
| duración de la corrida | 865.8 s | 329.4 s |

Las cuatro métricas quedaron **idénticas** a la parte 2: mismo modelo, mismas 6 herramientas, mismo prompt — el transporte MCP no le cambia nada al modelo, solo cómo el proceso que lo llama consigue el resultado de la tool. Los tokens y el costo también quedan prácticamente iguales (diferencia de ~2-3%, dentro del ruido normal entre corridas con el mismo prompt: el modelo no repite la respuesta palabra por palabra de una corrida a otra). La duración sí varía bastante, pero en la dirección contraria a la esperada: la corrida MCP tardó menos (329 s) que la de la parte 2 (866 s). Esto no es una ventaja estructural del MCP — `MultiServerMCPClient` en modo básico abre una sesión stdio nueva por cada llamada a herramienta, y cada `buscar_documentos` recarga el encoder `bge-m3` desde cero (~20-40 s por carga, visible en el log). La diferencia de duración entre las dos corridas es ruido de red hacia OpenRouter de ese momento, no una comparación confiable de performance de transporte.

**Riesgo de diseño a anotar:** para un volumen mayor de preguntas, el modo "una sesión por llamada" de `MultiServerMCPClient` sería notoriamente más lento que una sesión MCP persistente, porque cada `buscar_documentos` paga de nuevo la carga del encoder. Para las 12 preguntas de `dev` el costo es aceptable y evita manejar a mano el ciclo de vida de la sesión (ver "Decisiones abiertas" en `specs/parte3-mcp.md`).

### Evidencia

- `respuestas_mcp.jsonl` y `respuestas_mcp.jsonl.eval.json`: la corrida entregada.
- `experimentos/logs/agente_mcp_20261007_152733.md`: el log de la corrida, con cada pregunta, cada llamada a herramienta (vía MCP) con argumentos y resultado, la respuesta final y el usage de cada llamada al modelo.
- `experimentos/inspector/`: 6 capturas del MCP Inspector (`npx @modelcontextprotocol/inspector python3 servidor_mcp.py`), una por herramienta, probadas sin ningún LLM de por medio.
- `specs/parte3-mcp.md`: el diseño previo, con la restricción de diseño, el desvío respecto al plan original y el plan de TDD.
