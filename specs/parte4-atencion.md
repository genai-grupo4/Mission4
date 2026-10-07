# SPEC — Parte 4: una capa de atención en NumPy (`atencion.py`)

Estado: implementado, 14/14 tests en verde con `python3 atencion/test_atencion.py atencion.py`. Fuente de verdad de la consigna: `mission.md` §"Parte 4". Reglas operativas: `CLAUDE.md`.

## Objetivo

Implementar en `atencion.py`, solo con NumPy, las piezas de una capa de atención de transformer: `softmax`, `atencion`, `autoatencion` (con máscara causal opcional), `multicabeza` y `layer_norm`. Sirve además para verificar las cuentas a mano de la parte 5.

## Contrato (no negociable)

```bash
python3 atencion/test_atencion.py atencion.py
```

Los 14 tests en verde, con `atencion/test_atencion.py` tal cual lo entregó la cátedra (solo lectura). Los valores de referencia son los del ejemplo de la clase ("the cat sat", d = 4).

## Interfaz

| Función | Entrada | Salida |
|---|---|---|
| `softmax(M)` | matriz (o vector) | softmax sobre el último eje; cada fila suma 1 |
| `atencion(Q, K, V, mascara=False)` | `Q: (n, d_k)`, `K: (m, d_k)`, `V: (m, d_v)` | `(salida, A)` con `A = softmax(Q Kᵀ / √d_k)` `(n, m)` y `salida = A V` `(n, d_v)` |
| `autoatencion(X, Wq, Wk, Wv, mascara=False)` | `X: (n, d)` y las tres proyecciones | `(salida, A)` de `atencion(X Wq, X Wk, X Wv, mascara)` |
| `multicabeza(X, cabezas, Wo, mascara=False)` | `cabezas`: lista de `(Wq, Wk, Wv)` | `concat(salida_h por columnas) · Wo` (solo la salida) |
| `layer_norm(x, eps=1e-5)` | matriz | cada fila con media 0 y varianza 1: `(x − μ) / √(σ² + eps)`, sin γ/β |

## Decisiones

- **Softmax estable:** se resta el máximo de cada fila antes de `exp`. No cambia el resultado (el softmax es invariante a corrimientos) y evita `inf` con valores como `[1000, 1000]`.
- **Máscara causal:** si `mascara=True`, las posiciones `j > i` de los scores se ponen en `-inf` antes del softmax, así su peso es exactamente 0 y cada fila sigue sumando 1. La diagonal siempre queda visible, así que ninguna fila queda toda en `-inf`.
- **Escala por √d_k:** `d_k` es la última dimensión de `K` (no la de `X`), que es lo que mide el test `test_escala_por_raiz_de_dk`.
- **layer_norm sin parámetros aprendidos:** el test pide media 0 / varianza 1 exactas; γ y β quedarían en 1 y 0, así que no se agregan.
- **Sin otras dependencias:** solo `numpy`, como pide el docstring del test.

## Plan TDD

1. Archivo vacío → los tests fallan (rojo).
2. `softmax` → pasan los 3 tests de `TestSoftmax`.
3. `atencion` + `autoatencion` con máscara → pasan los 6 de `TestAtencion`.
4. `multicabeza` → pasan los 2 de `TestMulticabeza`.
5. `layer_norm` → pasan los 3 de `TestLayerNorm`. Total: 14 en verde.
