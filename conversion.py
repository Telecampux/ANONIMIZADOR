"""Conversión local exclusiva para descargar copias en Word."""
from pathlib import Path
import os
import tempfile

FORMATS = [
    ('PDF (.pdf)', '*.pdf'), ('Word (.docx)', '*.docx'),
    ('Word 97–2003 (.doc)', '*.doc'), ('Texto (.txt)', '*.txt'),
    ('Texto enriquecido (.rtf)', '*.rtf'), ('OpenDocument (.odt)', '*.odt'),
    ('Página web (.html)', '*.html'),
]
WORD_FORMATS = {'.pdf': 17, '.docx': 16, '.doc': 0, '.txt': 7,
                '.rtf': 6, '.odt': 23, '.html': 10, '.htm': 10}


def convert_file(source, destination, progress=None):
    """Generar una copia en el formato solicitado sin cambiar el original."""
    import shutil
    import subprocess
    source, destination = Path(source).resolve(), Path(destination).resolve()
    suffix = destination.suffix.lower()
    if suffix not in WORD_FORMATS:
        raise ValueError('Formato no admitido. Elija PDF, DOCX, DOC, TXT, RTF, ODT o HTML.')
    if source.suffix.lower() == suffix:
        if source != destination:
            shutil.copy2(source, destination)
        return
    if source == destination:
        raise ValueError('Guarde la conversión con otro nombre.')
    with tempfile.TemporaryDirectory(prefix='descarga_', dir=destination.parent) as directory:
        workspace = Path(directory)
        converted = workspace / destination.name
        working_source = source
        if source.suffix.lower() == '.pdf':
            working_source = workspace / 'intermedio.docx'
            pdf_to_word(source, working_source, progress)
            if suffix == '.docx':
                os.replace(working_source, destination)
                return
        if progress:
            progress(f'Convirtiendo copia a {suffix[1:].upper()}…')
        try:
            result = subprocess.run([
                'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(Path(__file__).with_name('convertir_word.ps1')),
                '-Source', str(working_source), '-Destination', str(converted),
                '-Format', str(WORD_FORMATS[suffix]),
            ], capture_output=True, timeout=240,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise ValueError('La conversión tardó demasiado. Intente de nuevo con el documento cerrado.') from exc
        if result.returncode or not converted.is_file() or not converted.stat().st_size:
            detail = result.stderr.decode(errors='replace').strip()
            raise ValueError('No se pudo convertir con Microsoft Word. ' + detail)
        if suffix in {'.html', '.htm'}:
            for resource in workspace.iterdir():
                if resource.is_dir():
                    shutil.copytree(resource, destination.parent / resource.name, dirs_exist_ok=True)
        os.replace(converted, destination)


def pdf_to_word(source, destination, progress=None):
    import io
    import pymupdf
    from docx import Document
    from docx.shared import Inches, Pt
    from PIL import Image
    from ocr_local import _recognize_pass

    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(0.7)
    document.styles['Normal'].font.name = 'Arial'
    document.styles['Normal'].font.size = Pt(11)
    destination = Path(destination)
    temporary = None
    try:
        with pymupdf.open(source) as pdf:
            if pdf.needs_pass:
                raise ValueError('El PDF tiene contraseña. Use una copia sin contraseña.')
            if not len(pdf):
                raise ValueError('El PDF no contiene páginas.')
            for index, page in enumerate(pdf):
                if progress:
                    progress(f'Convirtiendo a Word: página {index + 1} de {len(pdf)}…')
                text = page.get_text(sort=True).strip()
                if not text or page.get_images():
                    pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    text, _ = _recognize_pass(image)
                    text = text.strip()
                if index:
                    document.add_page_break()
                if text:
                    for paragraph in text.split('\n\n'):
                        document.add_paragraph(paragraph)
                else:
                    pix = page.get_pixmap(dpi=150, alpha=False)
                    scale = min(7.1 / (page.rect.width / 72), 9.3 / (page.rect.height / 72))
                    document.add_picture(io.BytesIO(pix.tobytes('png')),
                                         width=Inches(page.rect.width / 72 * scale))
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.docx', delete=False) as file:
            temporary = Path(file.name)
        document.save(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
