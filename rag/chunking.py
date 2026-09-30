"""Parseo del corpus Markdown y variantes de chunking.

Todas las variantes devuelven texto literal del corpus: el evaluador busca la
evidencia como substring, así que nunca se resume ni se reformatea, y nunca se
corta una oración a la mitad.
"""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Seccion:
    nombre: str  # "" para el texto que va antes del primer "##"
    texto: str


@dataclass
class Documento:
    archivo: str
    titulo: str
    secciones: list


@dataclass
class Fragmento:
    texto: str
    doc: str
    titulo: str
    seccion: str

    def para_embeber(self, metadatos=False):
        """Texto que ve el encoder. Con metadatos, antepone título y sección."""
        if not metadatos:
            return self.texto
        cabecera = ". ".join(p for p in [self.titulo, self.seccion] if p)
        return f"{cabecera}. {self.texto}"


def parsear_documento(archivo, md):
    titulo, secciones = "", []
    nombre, lineas = "", []

    def cerrar():
        texto = "\n".join(lineas).strip()
        if texto:
            secciones.append(Seccion(nombre, texto))

    for linea in md.splitlines():
        if linea.startswith("## "):
            cerrar()
            nombre, lineas = linea[3:].strip(), []
        elif linea.startswith("# ") and not titulo:
            titulo = linea[2:].strip()
        else:
            lineas.append(linea)
    cerrar()
    return Documento(archivo, titulo, secciones)


def cargar_corpus(carpeta):
    return [parsear_documento(p.name, p.read_text(encoding="utf-8"))
            for p in sorted(Path(carpeta).glob("*.md"))]


# Fin de oración: punto/signo seguido de espacio y de algo que abre oración.
# No corta "7:00", "2.5" ni "38 °C". Los saltos de línea (ítems de lista) también cortan.
_FIN = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\-])|\n+")


def dividir_oraciones(texto):
    return [o.strip() for o in _FIN.split(texto) if o.strip()]


def _frag(doc, seccion, texto):
    return Fragmento(texto, doc.archivo, doc.titulo, seccion)


def por_seccion(doc):
    return [_frag(doc, s.nombre, s.texto) for s in doc.secciones]


def por_parrafo(doc):
    return [_frag(doc, s.nombre, p.strip())
            for s in doc.secciones for p in re.split(r"\n\s*\n", s.texto) if p.strip()]


def por_oraciones(n, solapamiento):
    """Ventanas de n oraciones dentro de cada sección (no cruza secciones)."""
    paso = n - solapamiento

    def chunker(doc):
        frags = []
        for s in doc.secciones:
            ors = dividir_oraciones(s.texto)
            for i in range(0, max(len(ors) - solapamiento, 1), paso):
                frags.append(_frag(doc, s.nombre, " ".join(ors[i:i + n])))
        return frags
    return chunker


def por_ventana(caracteres, solapamiento):
    """Tamaño fijo en caracteres, ignorando la estructura del Markdown.

    Junta oraciones hasta llegar a `caracteres` y arranca la siguiente ventana
    repitiendo las últimas oraciones hasta cubrir `solapamiento` caracteres.
    """
    def chunker(doc):
        ors = [o for s in doc.secciones for o in dividir_oraciones(s.texto)]
        frags, i = [], 0
        while i < len(ors):
            j, largo = i, 0
            while j < len(ors) and (largo < caracteres or j == i):
                largo += len(ors[j]) + 1
                j += 1
            frags.append(_frag(doc, "", " ".join(ors[i:j])))
            if j >= len(ors):
                break
            k, extra = j, 0
            while k - 1 > i and extra < solapamiento:
                k -= 1
                extra += len(ors[k]) + 1
            i = k
        return frags
    return chunker


CHUNKERS = {
    "seccion": por_seccion,
    "parrafo": por_parrafo,
    "oracion1": por_oraciones(1, 0),
    "oracion2": por_oraciones(2, 1),
    "oracion3": por_oraciones(3, 1),
    "ventana300": por_ventana(300, 80),
    "ventana600": por_ventana(600, 150),
}


def fragmentar(docs, chunking):
    return [f for d in docs for f in CHUNKERS[chunking](d)]
