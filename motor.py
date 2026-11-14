import re
from office_antiguo import FORMATOS_ANTIGUOS
import unicodedata
from functools import lru_cache
from pathlib import Path

IMAGENES = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}
FORMATOS = {'.pdf', '.docx', '.xlsx', '.pptx', '.txt', '.csv', '.tsv', '.md', '.json', '.xml', '.html', '.htm', '.log', '.yaml', '.yml', '.ini', '.sql'} | IMAGENES
FORMATOS |= FORMATOS_ANTIGUOS.keys()
PATRONES = {
    'Nombres propios de personas (detección en español)': None,
    'Correos electrónicos': r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',
    'Documentos con etiqueta CC, TI, CE o NIT': r'(?<!\w)(?:C\.?[ \t]*C\.?|T\.?[ \t]*I\.?|C\.?[ \t]*E\.?|N\.?[ \t]*I\.?[ \t]*T\.?|c[eé]dula(?:[ \t]+de[ \t]+ciudadan[ií]a)?|identificaci[oó]n|pasaporte)[ \t]*(?:n[uú]mero|nro\.?|no\.?|n[.°º])?[ \t]*[:#º°.-]?[ \t]*(?P<valor>\d{1,3}(?:\.\d{3}){1,4}(?:-\d)?|[A-Z]{0,3}\d{4,12}(?:-\d)?)(?!\w)',
}

@lru_cache(maxsize=1)
def modelo_nombres():
    import spacy
    try:
        return spacy.load('es_core_news_sm', disable=['parser', 'lemmatizer', 'attribute_ruler'])
    except OSError as exc:
        raise ValueError('Falta el modelo de nombres en español. Ejecuta Instalar.bat.') from exc


def nombre_personal_valido(valor):
    normal = ''.join(c for c in unicodedata.normalize('NFD', valor.casefold()) if unicodedata.category(c) != 'Mn')
    palabras = re.findall(r'[^\W\d_]+', normal)
    excluidas = {
        'accion', 'tutela', 'juez', 'juzgado', 'tribunal', 'corte', 'constitucional',
        'municipal', 'sentencia', 'radicado', 'republica', 'derecho', 'derechos',
        'identificacion', 'cedula', 'notificaciones', 'demandante', 'demandado',
        'accionante', 'accionado', 'solicitud', 'ministerio', 'secretaria', 'departamento',
        'universidad', 'universitario', 'universitaria', 'master', 'magister', 'instituto',
        'institucion', 'entidad', 'empresa', 'sociedad', 'fundacion', 'hospital',
        'clinica', 'servicio', 'servicios', 'salud', 'educacion', 'nacional', 'correo',
        'electronico', 'celular', 'telefono', 'referencia', 'asunto', 'constancia',
        'registrar', 'retener', 'certificado', 'certificacion', 'anexo', 'anexos',
        'abogado', 'abogada', 'doctor', 'doctora', 'senor', 'senora', 'director',
        'directora', 'rector', 'rectora', 'magistrado', 'magistrada', 'presidente',
        'defensoria', 'procuraduria', 'fiscalia', 'superintendencia', 'consejo',
        'congreso', 'alcaldia', 'gobernacion', 'bogota', 'colombia', 'articulo',
        'expediente', 'resolucion', 'peticion', 'administrativo', 'administrativa',
    }
    if not valor or '@' in valor or any(c.isdigit() for c in valor) or set(palabras) & excluidas:
        return False
    # Prioriza nombres completos: descarta verbos, títulos y palabras aisladas.
    conectores = {'de', 'del', 'la', 'las', 'los', 'y', 'da', 'do', 'dos', 'van', 'von'}
    tokens = re.findall(r'[^\W\d_]+', valor)
    significativos = [t for t in tokens if t.casefold() not in conectores and len(t) >= 2]
    return len(significativos) >= 2 and all(t[0].isupper() for t in significativos)


def nombres_personas(texto):
    modelo = modelo_nombres()
    spans = []
    # Solapamiento para mantener nombres que cruzan los límites de fragmentos.
    for offset in range(0, len(texto), 38000):
        fragmento = texto[offset:offset + 40000]
        for entidad in modelo(fragmento).ents:
            if entidad.label_ == 'PER':
                valor = entidad.text
                titulo = re.match(r'(?i)(?:(?:señor(?:a)?|doctor(?:a)?|abogad[oa]|dr\.?|dra\.?)\s+)+', valor)
                inicio = titulo.end() if titulo else 0
                # Impide juntar el nombre con el título del campo de la siguiente línea.
                linea = valor[inicio:].split('\n', 1)[0].split('\r', 1)[0]
                sin_inicio = linea.lstrip(' ,.;:\t\u200b\ufeff')
                inicio += len(linea) - len(sin_inicio)
                valor = sin_inicio.rstrip(' ,.;:\t\u200b\ufeff')
                if nombre_personal_valido(valor):
                    comienzo = offset + entidad.start_char + inicio
                    spans.append((comienzo, comienzo + len(valor)))
    # También tapa repeticiones del nombre detectado con otras mayúsculas/minúsculas.
    nombres = {texto[start:end].strip() for start, end in spans}
    for nombre in nombres:
        if nombre:
            spans.extend((m.start(), m.end()) for m in re.finditer(r'(?<!\w)' + re.escape(nombre) + r'(?!\w)', texto, re.I))
    return spans

def coincidencias(texto, categorias, terminos):
    spans = []
    for categoria in categorias:
        if PATRONES[categoria] is None:
            spans.extend(nombres_personas(texto))
        else:
            spans.extend((m.start(), m.end()) for m in re.finditer(PATRONES[categoria], texto, re.I))
    for termino in terminos:
        if termino.strip():
            termino = termino.strip()
            patron = (r'(?<!\w)' if termino[0].isalnum() else '') + re.escape(termino) + (r'(?!\w)' if termino[-1].isalnum() else '')
            spans.extend((m.start(), m.end()) for m in re.finditer(patron, texto, re.I))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged

def reemplazar(texto, categorias, terminos):
    spans = coincidencias(texto, categorias, terminos)
    for start, end in reversed(spans):
        texto = texto[:start] + '[ANONIMIZADO]' + texto[end:]
    return texto, len(spans)


def leer_texto(origen):
    datos = origen.read_bytes()
    if datos.startswith((b'\xff\xfe', b'\xfe\xff')):
        texto = datos.decode('utf-16')
    else:
        try:
            texto = datos.decode('utf-8-sig')
        except UnicodeDecodeError:
            texto = datos.decode('cp1252')
    if '\x00' in texto:
        raise ValueError('El archivo no parece texto; no se modificó.')
    return texto

def procesar(origen, destino, categorias, terminos, zonas=None, marcas=None):
    """Produce una copia nueva. Los documentos Office se reconstruyen sin objetos incrustados."""
    ext = origen.suffix.lower()
    if ext in FORMATOS_ANTIGUOS:
        from office_antiguo import convertir_antiguo
        if destino.suffix.lower() != FORMATOS_ANTIGUOS[ext]:
            raise ValueError('La copia de un documento antiguo debe usar su formato moderno.')
        with convertir_antiguo(origen) as convertido:
            return procesar(convertido, destino, categorias, terminos, zonas, marcas)
    total = 0
    def limpiar(s):
        nonlocal total
        value, count = reemplazar(str(s), categorias, terminos)
        total += count
        return value
    if ext in IMAGENES:
        from PIL import Image, ImageOps, ImageDraw
        with Image.open(origen) as fuente:
            if getattr(fuente, 'n_frames', 1) != 1:
                raise ValueError('Imagen con varias páginas o animación: separa las páginas antes de procesar.')
            orientada = ImageOps.exif_transpose(fuente).convert('RGB')
            nueva = Image.new('RGB', orientada.size, 'white')
            nueva.paste(orientada)
            dibujo = ImageDraw.Draw(nueva)
            if zonas is None:
                from analisis import reconocer
                texto, lineas = reconocer(nueva)
                spans = coincidencias(texto, categorias, terminos)
                zonas = [rect for a, b, rect in lineas if any(start < b and end > a for start, end in spans)]
            if not zonas:
                raise ValueError('No se detectaron los datos seleccionados en la imagen. No se creó una copia.')
            for zona in zonas:
                dibujo.rectangle(zona, fill='black')
                if marcas is not None:
                    marcas.append({'pagina': 0, 'rect': [zona[0] / nueva.width, zona[1] / nueva.height, zona[2] / nueva.width, zona[3] / nueva.height]})
                total += 1
            # PNG nuevo sin EXIF, GPS, comentarios ni miniatura original.
            nueva.save(destino, format='PNG')
    elif ext == '.pdf':
        import fitz
        with fitz.open(origen) as doc, fitz.open() as nuevo:
            if doc.needs_pass:
                raise ValueError('PDF protegido con contraseña.')
            for numero, pagina in enumerate(doc):
                texto = pagina.get_text()
                for start, end in coincidencias(texto, categorias, terminos):
                    for rect in pagina.search_for(texto[start:end]):
                        pagina.add_redact_annot(rect, fill=(0, 0, 0))
                        if marcas is not None:
                            visible = rect * pagina.rotation_matrix
                            marcas.append({'pagina': numero, 'rect': [visible.x0 / pagina.rect.width, visible.y0 / pagina.rect.height, visible.x1 / pagina.rect.width, visible.y1 / pagina.rect.height]})
                        total += 1
                pagina.apply_redactions()
                # Re-renderizar elimina capas ocultas, adjuntos y texto bajo tachaduras.
                pix = pagina.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False, annots=False)
                from PIL import Image, ImageDraw
                from analisis import reconocer
                imagen = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                texto_ocr, lineas = reconocer(imagen)
                spans = coincidencias(texto_ocr, categorias, terminos)
                dibujo = ImageDraw.Draw(imagen)
                for a, b, rect in lineas:
                    if any(start < b and end > a for start, end in spans):
                        dibujo.rectangle(rect, fill='black')
                        if marcas is not None:
                            marcas.append({'pagina': numero, 'rect': [rect[0] / imagen.width, rect[1] / imagen.height, rect[2] / imagen.width, rect[3] / imagen.height]})
                        total += 1
                import io
                buffer = io.BytesIO()
                imagen.save(buffer, format='PNG')
                salida = nuevo.new_page(width=pagina.rect.width, height=pagina.rect.height)
                salida.insert_image(salida.rect, stream=buffer.getvalue())
            nuevo.set_metadata({})
            nuevo.save(destino, garbage=4, deflate=True)
    elif ext == '.docx':
        from docx import Document
        from docx.oxml.ns import qn
        fuente, nuevo = Document(origen), Document()
        # Incluye tablas, cuadros de texto, encabezados y pies; omite imágenes y objetos.
        raices = [fuente.element.body]
        for section in fuente.sections:
            for attr in ('header', 'footer', 'first_page_header', 'first_page_footer', 'even_page_header', 'even_page_footer'):
                raices.append(getattr(section, attr)._element)
        for raiz in raices:
            for p in raiz.iter(qn('w:p')):
                texto = ''.join(t.text or '' for t in p.iter(qn('w:t')))
                if texto:
                    nuevo.add_paragraph(limpiar(texto))
        nuevo.core_properties.author = ''
        nuevo.core_properties.last_modified_by = ''
        nuevo.save(destino)
    elif ext == '.xlsx':
        from openpyxl import load_workbook, Workbook
        fuente = load_workbook(origen, data_only=False)
        nuevo = Workbook()
        nuevo.remove(nuevo.active)
        for numero, hoja in enumerate(fuente, 1):
            salida = nuevo.create_sheet(f'Hoja {numero}')
            for fila in hoja:
                for celda in fila:
                    if celda.value is not None:
                        value = limpiar(celda.value) if isinstance(celda.value, str) else celda.value
                        target = salida.cell(celda.row, celda.column, value)
                        if isinstance(value, str):
                            target.data_type = 's'  # fórmulas como texto, sin enlaces ejecutables
        nuevo.properties.creator = ''
        nuevo.properties.lastModifiedBy = ''
        nuevo.save(destino)
        fuente.close()
    elif ext == '.pptx':
        from pptx import Presentation
        fuente, nuevo = Presentation(origen), Presentation()
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
        from pptx.util import Inches
        for slide in fuente.slides:
            salida = nuevo.slides.add_slide(nuevo.slide_layouts[6])
            box = salida.shapes.add_textbox(Inches(.4), Inches(.4), Inches(9), Inches(6.5))
            box.text_frame.word_wrap = True
            box.text_frame.text = limpiar('\n'.join(textos(slide.shapes)))
        nuevo.core_properties.author = ''
        nuevo.core_properties.last_modified_by = ''
        nuevo.save(destino)
    elif ext in FORMATOS:
        texto = leer_texto(origen)
        destino.write_text(limpiar(texto), encoding='utf-8')
    else:
        raise ValueError('Formato no compatible; no se copió.')
    return total
