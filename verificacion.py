"""Comprueba las tachaduras seleccionadas en el PDF realmente guardado."""
import io
import math
import re

from procesamiento import check_cancelled


def verificar_pdf_seleccionado(plan, approved, data):
    if not plan.original.startswith(b'%PDF-'):
        return
    from anonimizador import AnonymizationError
    import pymupdf
    from PIL import Image
    selected = {}
    for identity in approved:
        finding = plan.findings[identity]
        match = re.fullmatch(r'Documento / Página (\d+)', finding['location'])
        if match:
            selected.setdefault(int(match.group(1))-1, []).append(finding)
    with pymupdf.open(stream=plan.original, filetype='pdf') as original, pymupdf.open(stream=data, filetype='pdf') as output:
        for number, findings in selected.items():
            check_cancelled()
            if number >= len(output):
                raise AnonymizationError('El PDF guardado no contiene todas las páginas seleccionadas.')
            page = original[number]
            rasterized = bool(page.get_images()) or not page.get_text().strip()
            if rasterized:
                images = output[number].get_images()
                if len(images) != 1 or output[number].get_text().strip():
                    raise AnonymizationError('La página anonimizada conserva contenido que no corresponde a la revisión.')
                image = Image.open(io.BytesIO(output.extract_image(images[0][0])['image'])).convert('RGB')
            else:
                pix = output[number].get_pixmap(dpi=100, alpha=False, colorspace=pymupdf.csRGB)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            for finding in findings:
                evidence = plan.evidence.get(finding['location'], {})
                boxes = [finding['box']] if finding.get('box') else [
                    box for a, b, box, _ in evidence.get('words', [])
                    if finding['start'] < b and finding['stop'] > a]
                if not boxes:
                    raise AnonymizationError(f'No se pudo verificar un dato seleccionado en la página {number+1}.')
                for x0, y0, x1, y1 in boxes:
                    # Ignore antialiasing along native PDF rectangle edges.
                    inset = 1 if rasterized else 2
                    left, top = max(0, math.ceil(x0)+inset), max(0, math.ceil(y0)+inset)
                    right, bottom = min(image.width, math.floor(x1)-inset), min(image.height, math.floor(y1)-inset)
                    if right <= left or bottom <= top:
                        left, top = int((x0+x1)/2), int((y0+y1)/2)
                        right, bottom = left+1, top+1
                    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
                        raise AnonymizationError(f'Una tachadura quedó fuera de la página {number+1}.')
                    extrema = image.crop((left, top, right, bottom)).getextrema()
                    if any(low != 64 or high != 64 for low, high in extrema):
                        raise AnonymizationError(f'El PDF guardado no ocultó un dato seleccionado de la página {number+1}. No se conservará esta salida.')
