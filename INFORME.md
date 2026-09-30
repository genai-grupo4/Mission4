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
