"""Tests del log .md de la corrida.

Es evidencia obligatoria del enunciado ("sin logs, esta parte vale cero"): tiene que tener
cada pregunta, cada llamada a herramienta con argumentos y resultado, la respuesta final y
el usage de cada llamada al modelo.
"""
from herramientas import registro
from herramientas.registro import LlamadaTool, Traza, UsoModelo


def _traza():
    return Traza(
        id="A10",
        pregunta="¿Hay lugar en pediatría y me puedo quedar?",
        llamadas=[
            LlamadaTool("consultar_camas", {"sector": "pediatria"}, '{"libres": 7}'),
            LlamadaTool("buscar_documentos", {"consulta": "acompañante pediatría"}, "Un adulto puede quedarse."),
        ],
        usos=[UsoModelo(900, 40, 0.0001), UsoModelo(1200, 60, 0.0002)],
        respuesta="Hay 7 camas libres y podés quedarte.",
    )


def test_el_log_tiene_pregunta_llamadas_resultado_respuesta_y_usage(tmp_path):
    destino = tmp_path / "corrida.md"
    registro.escribir_log(destino, [_traza()], modelo="deepseek/deepseek-v4-flash-0731", segundos=12.5)
    texto = destino.read_text(encoding="utf-8")
    assert "A10" in texto
    assert "¿Hay lugar en pediatría y me puedo quedar?" in texto
    assert "consultar_camas" in texto and '"sector": "pediatria"' in texto
    assert '{"libres": 7}' in texto
    assert "Un adulto puede quedarse." in texto
    assert "Hay 7 camas libres y podés quedarte." in texto
    assert "2100" in texto, "tokens de entrada totales de la pregunta"
    assert "deepseek/deepseek-v4-flash-0731" in texto


def test_el_log_totaliza_tokens_y_costo_de_la_corrida(tmp_path):
    destino = tmp_path / "corrida.md"
    registro.escribir_log(destino, [_traza(), _traza()], modelo="m", segundos=1.0)
    texto = destino.read_text(encoding="utf-8")
    assert "0.0006" in texto, "costo total de las dos preguntas"
    assert "4200" in texto, "tokens de entrada totales de la corrida"


def test_crea_el_directorio_si_no_existe(tmp_path):
    destino = tmp_path / "experimentos" / "logs" / "corrida.md"
    registro.escribir_log(destino, [_traza()], modelo="m", segundos=1.0)
    assert destino.exists()


def test_el_costo_estimado_se_marca_como_estimado(tmp_path):
    t = _traza()
    t.usos = [UsoModelo(1_000_000, 1_000_000, None)]
    destino = tmp_path / "corrida.md"
    registro.escribir_log(destino, [t], modelo="m", segundos=1.0)
    texto = destino.read_text(encoding="utf-8")
    assert "0.68" in texto, "1M de entrada a 0,04 + 1M de salida a 0,64"
    assert "estimado" in texto.lower()


def test_una_traza_con_error_queda_registrada(tmp_path):
    t = _traza()
    t.error = "timeout de OpenRouter"
    destino = tmp_path / "corrida.md"
    registro.escribir_log(destino, [t], modelo="m", segundos=1.0)
    assert "timeout de OpenRouter" in destino.read_text(encoding="utf-8")
