import re

import pytest

from rag.chunking import CHUNKERS, cargar_corpus, dividir_oraciones, parsear_documento

DOC = """# Laboratorio

Texto de introducción. Segunda oración de la intro.

## Horario

Las extracciones son de 7:00 a 10:00. Los sábados, de 8:00 a 10:00.

## Ayuno

- Glucemia: 8 horas.
- Lípidos: 12 horas.

Se puede tomar agua.
"""

DOC_SIN_SECCIONES = """# Alta hospitalaria

Las altas se dan de 10:00 a 12:00. Después de la recorrida.

Si necesita ambulancia, lo gestiona servicio social.
"""


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def test_parsear_documento_separa_titulo_y_secciones():
    doc = parsear_documento("lab.md", DOC)
    assert doc.titulo == "Laboratorio"
    assert [s.nombre for s in doc.secciones] == ["", "Horario", "Ayuno"]
    assert "Segunda oración de la intro." in doc.secciones[0].texto
    assert doc.secciones[2].texto.startswith("- Glucemia")


def test_documento_sin_subtitulos_es_una_sola_seccion():
    doc = parsear_documento("alta.md", DOC_SIN_SECCIONES)
    assert len(doc.secciones) == 1
    assert doc.secciones[0].nombre == ""


def test_dividir_oraciones_no_rompe_horas_ni_decimales():
    oraciones = dividir_oraciones("Es de 7:00 a 10:00. Fiebre de 38 °C o más. Dura 2.5 horas.")
    assert oraciones == ["Es de 7:00 a 10:00.", "Fiebre de 38 °C o más.", "Dura 2.5 horas."]


@pytest.mark.parametrize("nombre", sorted(CHUNKERS))
def test_ningun_chunker_pierde_ni_inventa_texto(nombre):
    doc = parsear_documento("lab.md", DOC)
    frags = CHUNKERS[nombre](doc)
    assert frags, "tiene que devolver al menos un fragmento"
    cuerpo = norm(" ".join(s.texto for s in doc.secciones))
    # todo fragmento es texto literal del documento (el evaluador busca substrings)
    for f in frags:
        assert norm(f.texto) in cuerpo
        assert f.doc == "lab.md" and f.titulo == "Laboratorio"
    # y toda oración del documento aparece entera en algún fragmento
    for s in doc.secciones:
        for o in dividir_oraciones(s.texto):
            assert any(norm(o) in norm(f.texto) for f in frags), o


def test_chunker_seccion_da_un_fragmento_por_seccion():
    frags = CHUNKERS["seccion"](parsear_documento("lab.md", DOC))
    assert [f.seccion for f in frags] == ["", "Horario", "Ayuno"]


def test_chunker_oraciones_no_cruza_secciones():
    frags = CHUNKERS["oracion2"](parsear_documento("lab.md", DOC))
    for f in frags:
        assert not ("7:00" in f.texto and "Glucemia" in f.texto)


def test_texto_para_embeber_con_y_sin_metadatos():
    f = CHUNKERS["seccion"](parsear_documento("lab.md", DOC))[1]
    assert f.para_embeber(metadatos=False) == f.texto
    con = f.para_embeber(metadatos=True)
    assert con.startswith("Laboratorio. Horario.") and con.endswith(f.texto)


def test_cargar_corpus_real():
    docs = cargar_corpus("datos/corpus")
    assert len(docs) == 20
    assert all(d.titulo for d in docs)
