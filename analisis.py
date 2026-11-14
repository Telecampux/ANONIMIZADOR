from functools import lru_cache
from pathlib import Path
import re

from motor import PATRONES, nombres_personas, IMAGENES, leer_texto


@lru_cache(maxsize=1)
def modelo_ocr():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def reconocer(imagen):
    import numpy as np
    # RapidOCR espera canales BGR.
    resultado, _ = modelo_ocr()(np.array(imagen.convert('RGB'))[:, :, ::-1].copy())
    lineas = []
    texto = ''
    for puntos, contenido, confianza in resultado or []:
        inicio = len(texto)
        texto += contenido + '\n'
        xs, ys = zip(*puntos)
        lineas.append((inicio, inicio + len(contenido), (min(xs), min(ys), max(xs), max(ys))))
    return texto, lineas


def extraer(ruta):
    ext = ruta.suffix.lower()
    from office_antiguo import FORMATOS_ANTIGUOS, convertir_antiguo
    if ext in FORMATOS_ANTIGUOS:
        with convertir_antiguo(ruta) as convertido:
            return extraer(convertido)
    if ext in IMAGENES:
        from PIL import Image, ImageOps
        with Image.open(ruta) as imagen:
            if getattr(imagen, 'n_frames', 1) != 1:
                raise ValueError('Imagen animada o con varias páginas: sepárala primero.')
            return reconocer(ImageOps.exif_transpose(imagen))[0]
    if ext == '.pdf':
        import pymupdf as fitz
        from PIL import Image
        textos = []
        with fitz.open(ruta) as doc:
            if doc.needs_pass:
                raise ValueError('PDF protegido con contraseña.')
            for pagina in doc:
                texto = pagina.get_text()
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False, annots=False)
                imagen = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                # Analiza también imágenes incrustadas en PDF con texto.
                ocr = reconocer(imagen)[0]
                textos.append(texto + '\n' + ocr)
        return '\n'.join(textos)
    if ext == '.docx':
        from docx import Document
        from docx.oxml.ns import qn
        doc = Document(ruta)
        partes = [doc.element.body]
        for seccion in doc.sections:
            for nombre in ('header', 'footer', 'first_page_header', 'first_page_footer', 'even_page_header', 'even_page_footer'):
                partes.append(getattr(seccion, nombre)._element)
        return '\n'.join(''.join(t.text or '' for t in p.iter(qn('w:t'))) for parte in partes for p in parte.iter(qn('w:p')))
    if ext == '.xlsx':
        from openpyxl import load_workbook
        doc = load_workbook(ruta, data_only=False, read_only=True)
        try:
            return '\n'.join(str(valor) for hoja in doc for fila in hoja.values for valor in fila if valor is not None)
        finally:
            doc.close()
    if ext == '.pptx':
        from pptx import Presentation
        def textos(shapes):
            for shape in shapes:
                if shape.has_text_frame:
                    yield shape.text
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            yield cell.text
                if hasattr(shape, 'shapes'):
                    yield from textos(shape.shapes)
        return '\n'.join(t for slide in Presentation(ruta).slides for t in textos(slide.shapes))
    return leer_texto(ruta)


def analizar(ruta):
    texto = extraer(ruta)
    return detectar_campos(texto)


def detectar_campos(texto):
    campos = {}
    for categoria, patron in PATRONES.items():
        if patron is None:
            spans = nombres_personas(texto)
        else:
            spans = [(m.start('valor'), m.end('valor')) if 'valor' in m.groupdict() else (m.start(), m.end()) for m in re.finditer(patron, texto, re.I)]
        valores = [texto[a:b].strip() for a, b in spans if texto[a:b].strip()]
        # Agrupa repeticiones y variantes de mayúsculas, conservando el dato visible.
        unicos = {}
        for valor in valores:
            unicos.setdefault(valor.casefold(), valor)
        campos[categoria] = sorted(unicos.values(), key=str.casefold)
    return campos
