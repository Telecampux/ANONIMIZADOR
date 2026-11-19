"""OCR Tesseract local, sin enviar imágenes ni texto a servicios externos."""
import csv
import io
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from procesamiento import check_cancelled


class OCRError(RuntimeError):
    pass


def executable():
    candidates = [os.environ.get('TESSERACT_CMD'), shutil.which('tesseract'),
                  str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe'),
                  str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Tesseract-OCR/tesseract.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise OCRError('Falta Tesseract OCR. Ejecute instalar_ocr.ps1 para instalarlo.')


def _recognize_pass(image, psm=3, threshold_method=None):
    check_cancelled()
    buffer = io.BytesIO()
    image.convert('RGB').save(buffer, format='PNG')
    tessdata = Path(__file__).resolve().parent / 'tessdata'
    command = [executable(), 'stdin', 'stdout']
    if (tessdata / 'spa.traineddata').is_file() and (tessdata / 'eng.traineddata').is_file():
        command += ['--tessdata-dir', str(tessdata)]
    command += ['-l', 'spa+eng', '--psm', str(psm), '-c', 'tessedit_create_tsv=1']
    if threshold_method is not None:
        command += ['--dpi', '300', '-c', f'thresholding_method={threshold_method}']
    try:
        environment = os.environ.copy()
        environment.setdefault('OMP_THREAD_LIMIT', '1')
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=environment, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
            deadline = time.monotonic() + 180
            payload = buffer.getvalue()
            try:
                while True:
                    check_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, 180)
                    try:
                        stdout, stderr = process.communicate(input=payload, timeout=min(0.2, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        payload = None
                check_cancelled()
            except BaseException:
                process.kill()
                process.communicate()
                raise
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OCRError('No se pudo completar el OCR. No se generó una copia anonimizada.') from exc
    if result.returncode:
        raise OCRError('Tesseract no pudo leer la imagen. Compruebe los idiomas español e inglés con instalar_ocr.ps1.')
    words, pieces, offset, previous = [], [], 0, None
    for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8-sig')), delimiter='\t', quoting=csv.QUOTE_NONE):
        text = (row.get('text') or '').strip()
        if row.get('level') != '5' or not text:
            continue
        line = tuple(row[key] for key in ('page_num', 'block_num', 'par_num', 'line_num'))
        separator = '' if previous is None else (' ' if line == previous else '\n')
        pieces.extend((separator, text))
        offset += len(separator)
        x, y, w, h = (int(row[key]) for key in ('left', 'top', 'width', 'height'))
        words.append((offset, offset + len(text), (x, y, x+w, y+h), float(row['conf'])))
        offset += len(text)
        previous = line
    return ''.join(pieces), words


def recognize(image):
    """Read normal text and sparse forms, preserving coordinates on the original.

    Additional passes keep their own reading order and image coordinates.
    The caller merges proposals that cover the same physical words.
    """
    from PIL import ImageOps, ImageFilter
    check_cancelled()
    image = image.convert('RGB')
    denoised = ImageOps.grayscale(image).filter(ImageFilter.GaussianBlur(1))
    text, words = _recognize_pass(denoised, threshold_method=2)
    enhanced = ImageOps.autocontrast(ImageOps.grayscale(image), cutoff=1)
    enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=130, threshold=3))
    # A legible page is already located by the full-page pass. The expensive
    # sparse and cropped passes are reserved for pages with little usable text.
    substantial = sum(len(text[a:b]) >= 4 and confidence >= 35
                      for a, b, _, confidence in words)
    if len(words) >= 80 and substantial >= max(20, len(words) // 3):
        return text, words
    passes = [(enhanced, 11, 0, 0)]
    # Camera scans can turn paper texture into hundreds of spurious letters.
    # Denoising before binarization recovers dark print on shaded ID cards.
    if len(words) < 80 or substantial < max(10, len(words) // 3):
        smoothed = ImageOps.grayscale(image).filter(ImageFilter.GaussianBlur(1.2))
        for threshold in (85, 110):
            binary = smoothed.point(lambda value, limit=threshold: 255 if value > limit else 0)
            passes.append((binary, 11, 0, 0))
    # Columns isolate the small label/value pairs of clinical forms from the
    # neighbouring columns that otherwise interrupt the patient's name/address.
    for column in range(3):
        left = max(0, image.width * column // 3 - image.width // 40)
        right = min(image.width, image.width * (column + 1) // 3 + image.width // 40)
        passes.append((enhanced.crop((left, 0, right, image.height)), 3, left, 0))
    for column in range(4):
        left = image.width * column // 4
        right = min(image.width, left + image.width * 2 // 5)
        passes.append((enhanced.crop((left, 0, right, image.height * 2 // 5)), 6, left, 0))
    # Two independent OCR workers match the two physical cores of the older
    # machines used for this application. Preserve pass order for offsets.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: _recognize_pass(item[0], item[1]), passes))
    for (crop, psm, dx, dy), (extra_text, extra_words) in zip(passes, results):
        check_cancelled()
        # A strip may cut a word (e.g. example.com -> example.cor).
        # Never propose those fragments as independent sensitive values.
        kept = []
        characters = list(extra_text)
        for a, b, box, confidence in extra_words:
            x0, y0, x1, y1 = box
            clipped = ((dx > 0 and x0 <= 4) or
                       (dx + crop.width < image.width and x1 >= crop.width - 4) or
                       (dy + crop.height < image.height and y1 >= crop.height - 4))
            if clipped:
                characters[a:b] = ' ' * (b-a)
            else:
                kept.append((a, b, box, confidence))
        extra_text = ''.join(characters)
        offset = len(text) + 1
        text += '\n' + extra_text
        for a, b, (x0, y0, x1, y1), confidence in kept:
            words.append((offset + a, offset + b,
                          (x0 + dx, y0 + dy, x1 + dx, y1 + dy), confidence))
    return text, words


def redact(image, replacer):
    from PIL import ImageDraw, ImageOps
    from etiquetas import image_label
    check_cancelled()
    image = ImageOps.exif_transpose(image).convert('RGB')
    cache_key = (image.size, hashlib.sha256(image.tobytes()).hexdigest())
    if cache_key not in replacer.ocr_cache:
        replacer.progress('Reconociendo texto (OCR): ' + replacer.location)
        replacer.ocr_cache[cache_key] = recognize(image)
    text, words = replacer.ocr_cache[cache_key]
    if replacer.reviewing:
        preview = io.BytesIO()
        image.save(preview, format='PNG')
        replacer.evidence[replacer.location] = {'image': preview.getvalue(), 'words': words, 'text': text}
    drawing = ImageDraw.Draw(image)
    replacer.ocr_words, replacer.ocr_seen = words, []
    try:
        matches = list(replacer.spans(text))
    finally:
        replacer.ocr_words = None
    for start, stop, token in matches:
        check_cancelled()
        selected_words = [word for word in words if start < word[1] and stop > word[0]]
        if not selected_words:
            raise OCRError('No se pudo ubicar un dato seleccionado en el escaneo. No se generó una copia anonimizada.')
        box = (min(word[2][0] for word in selected_words), min(word[2][1] for word in selected_words),
               max(word[2][2] for word in selected_words), max(word[2][3] for word in selected_words))
        image_label(image, box, token)
        replacer.visual_codes.append((replacer.location, box, token))
        replacer.count += 1
    for region in replacer.regions.get(replacer.location, []):
        box = region['box'] if isinstance(region, dict) else region
        x0, y0, x1, y1 = box
        clipped = (max(0, min(image.width - 1, x0)), max(0, min(image.height - 1, y0)),
                   max(0, min(image.width - 1, x1)), max(0, min(image.height - 1, y1)))
        if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
            token = region.get('token') if isinstance(region, dict) else None
            if token:
                image_label(image, clipped, token)
                replacer.visual_codes.append((replacer.location, clipped, token))
            else:
                drawing.rectangle(clipped, fill='#fff2a8')
        replacer.count += 1
    replacer.ocr_pages += 1
    if not words:
        message = 'OCR ejecutado sin texto reconocido en una imagen/página. Revise su legibilidad y contenido visual.'
    elif any(confidence < 60 for _, _, _, confidence in words):
        message = 'OCR con palabras de baja confianza: revise los datos y las áreas que no se hayan reconocido bien.'
    else:
        message = 'OCR local aplicado. Revise el resultado: manuscritos, rostros y firmas no se anonimizan automáticamente.'
    if message not in replacer.warnings:
        replacer.warnings.append(message)
    return image
