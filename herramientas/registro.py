"""Log .md de una corrida del benchmark: evidencia obligatoria de las partes 2 y 3.

El enunciado pide, por pregunta, las llamadas a herramientas con sus argumentos y resultados,
la respuesta final y el usage de cada llamada al modelo. Sin este archivo la parte vale cero.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Precios de OpenRouter para deepseek/deepseek-v4-flash-0731 (mission.md), por token.
PRECIO_ENTRADA = 0.04 / 1_000_000
PRECIO_SALIDA = 0.64 / 1_000_000


@dataclass
class LlamadaTool:
    nombre: str
    argumentos: dict
    resultado: str


@dataclass
class UsoModelo:
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float | None = None
    """Costo informado por OpenRouter; None significa que hay que estimarlo con los precios."""

    @property
    def costo(self):
        if self.costo_usd is not None:
            return self.costo_usd
        return self.tokens_entrada * PRECIO_ENTRADA + self.tokens_salida * PRECIO_SALIDA

    @property
    def estimado(self):
        return self.costo_usd is None


def extraer_uso(mensaje):
    """El usage (tokens y costo real, si OpenRouter lo informó) de una respuesta del modelo."""
    um = mensaje.usage_metadata or {}
    costo = (mensaje.response_metadata.get("token_usage") or {}).get("cost")
    return UsoModelo(um.get("input_tokens", 0), um.get("output_tokens", 0), costo)


@dataclass
class Traza:
    id: str
    pregunta: str
    llamadas: list[LlamadaTool] = field(default_factory=list)
    usos: list[UsoModelo] = field(default_factory=list)
    respuesta: str = ""
    error: str | None = None

    @property
    def contextos(self):
        return [ll.resultado for ll in self.llamadas]

    @property
    def herramientas(self):
        """Nombres usados, sin repetir y en orden de primera llamada."""
        return list(dict.fromkeys(ll.nombre for ll in self.llamadas))

    def linea_jsonl(self):
        return {
            "id": self.id,
            "respuesta": self.respuesta,
            "contextos": self.contextos,
            "herramientas": self.herramientas,
        }


def _totales(usos):
    return (
        sum(u.tokens_entrada for u in usos),
        sum(u.tokens_salida for u in usos),
        sum(u.costo for u in usos),
        any(u.estimado for u in usos),
    )


def _marca(estimado):
    return " (estimado)" if estimado else ""


def escribir_log(destino, trazas, modelo, segundos):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    entrada, salida, costo, estimado = _totales([u for t in trazas for u in t.usos])

    L = [
        f"# Corrida del agente — {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        f"- Modelo: `{modelo}`",
        f"- Preguntas: {len(trazas)}",
        f"- Duración: {segundos:.1f} s",
        f"- Tokens: {entrada} de entrada, {salida} de salida",
        f"- Costo total: USD {costo:.6f}{_marca(estimado)}",
        "",
    ]

    for t in trazas:
        t_entrada, t_salida, t_costo, t_estimado = _totales(t.usos)
        L += [f"## {t.id}", "", f"**Pregunta:** {t.pregunta}", ""]
        if t.error:
            L += [f"**ERROR:** {t.error}", ""]
        if not t.llamadas:
            L += ["_Sin llamadas a herramientas._", ""]
        for i, ll in enumerate(t.llamadas, 1):
            L += [
                f"### Llamada {i}: `{ll.nombre}`",
                "",
                "Argumentos:",
                "",
                "```json",
                json.dumps(ll.argumentos, ensure_ascii=False, indent=1),
                "```",
                "",
                "Resultado:",
                "",
                "```",
                ll.resultado,
                "```",
                "",
            ]
        L += [
            "**Respuesta final:**",
            "",
            t.respuesta or "_(vacía)_",
            "",
            "**Usage:**",
            "",
            "| # | tokens entrada | tokens salida | costo USD |",
            "|---|---|---|---|",
        ]
        L += [
            f"| {i} | {u.tokens_entrada} | {u.tokens_salida} | {u.costo:.6f}{_marca(u.estimado)} |"
            for i, u in enumerate(t.usos, 1)
        ]
        L += [
            f"| **total** | **{t_entrada}** | **{t_salida}** | **{t_costo:.6f}**{_marca(t_estimado)} |",
            "",
            "---",
            "",
        ]

    destino.write_text("\n".join(L), encoding="utf-8")
    return destino
