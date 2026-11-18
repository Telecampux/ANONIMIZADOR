"""Anonimización local y restauración exacta del original sin contraseña."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
from contextlib import contextmanager
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from ocr_local import OCRError, redact as ocr_redact
from procesamiento import ProcessingCancelled, check_cancelled
from entidades import known_entity_spans

TEXT = {'.txt', '.md', '.csv', '.tsv', '.json', '.xml', '.html', '.htm', '.log',
        '.yaml', '.yml', '.ini', '.cfg', '.sql', '.tex', '.rst', '.srt', '.vtt'}
OFFICE = {'.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp'}
MEDIA = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus', '.aiff',
         '.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.mpeg', '.mpg', '.m4v',
         '.3gp', '.mts', '.ts', '.aif', '.amr', '.m2ts', '.vob', '.mka'}
RECOVERY_SUFFIX = '.restauracion'
MAX_BYTES = 100 * 1024 * 1024
NAME_WORD = r'[A-ZÁÉÍÓÚÑÜ][a-záéíóúñüA-ZÁÉÍÓÚÑÜ]+'
PERSON_NAME = NAME_WORD + r'(?:[ \t]+(?:(?i:de|del|la|las|los|y)[ \t]+){0,2}' + NAME_WORD + r'){1,5}'
PERSON_KINDS = frozenset({'PERSONA', 'NOMBRE_FORMULARIO', 'PROFESIONAL'})
NON_PERSON_WORDS = frozenset({
    'JUEZ', 'JUEZA', 'CONSTITUCIONAL', 'MUNICIPAL',
    'EPS', 'IPS', 'SAS', 'LTDA', 'MINISTERIO', 'SECRETARÍA', 'SECRETARIA',
    'JUZGADO', 'CORTE', 'TRIBUNAL', 'HOSPITAL', 'CLÍNICA', 'CLINICA',
    'UNIVERSIDAD', 'EMPRESA', 'SOCIEDAD', 'ALCALDÍA', 'ALCALDIA',
    'GOBERNACIÓN', 'GOBERNACION', 'SUPERINTENDENCIA', 'ENTIDAD',
    'IDENTIFICACIÓN', 'IDENTIFICACION', 'NACIMIENTO', 'DIAGNÓSTICO', 'DIAGNOSTICO',
    'CONSULTA', 'EXTERNA', 'ENFERMEDAD', 'COTIZANTE', 'CONTRIBUTIVO', 'SUBSIDIADO',
    'FEMENINO', 'MASCULINO', 'URGENCIAS', 'HOSPITALIZACIÓN', 'HOSPITALIZACION',
})
PATTERNS = {
    'DOCUMENTO': re.compile(r'(?i)\b(?:c[. ]?c[.]?|c[eé]dula(?:\s+de\s+ciudadan[ií]a)?|pasaporte|documento)\s*(?:n[úu]mero|n\s*[º°o.*]|:|#)?\s*([\d][\d. -]{4,18}\d)(?!\w)'),
    'PERSONA': re.compile(r'(?i:\b(?:(?:afiliado|paciente)\s*:\s*(?:CC|C\.C\.?|TI|CE|RC)\s*[.:\-]?\s*\d[\d.]*|nombre(?: completo)?|accionante|accionado|demandante|demandado|paciente|señor|señora|autorizador|ordenado\s+p[oe]r|registr[oe]\s+impreso\s+por))\s*[:;.\-]?\s*(' + PERSON_NAME + r')'),
    'IDENTIFICACION': re.compile(r'(?i)(?<!\w)(?:CC|TI|RC|CE|NUIP|identificaci[oó]n)\s*[:.\-]?\s*(\d[\d. -]{4,18}\d)(?!\w)'),
    'NOMBRE_FORMULARIO': re.compile(r'(?m)^[ \t]*(?i:nombres?(?:\s+y\s+apellidos)?|apellidos?|nombre\s+del\s+paciente)[ \t]*[:\-]?[ \t]*\n[ \t]*(' + PERSON_NAME + r')[ \t]*(?:\n|$)'),
    'PROFESIONAL': re.compile(r'(?i:\b(?:prof|doctor|doctora|m[eé]dico|m[eé]dica))\s*[:.][ \t]*(' + PERSON_NAME + r')'),
}


class AnonymizationError(ValueError):
    pass


class Replacer:
    def __init__(self, manual=(), automatic=True, *, reviewing=False, approved=None, progress=None, ocr_cache=None, case_id=None, known_entities=None, learning=False):
        self.manual = sorted({s.strip() for s in manual if s.strip()}, key=len, reverse=True)
        self.automatic = automatic
        self.mapping = {}
        self.fields = {}
        self.applied_findings = set()
        self.count = 0
        self.warnings = []
        self.output_suffix = None
        self.ocr_pages = 0
        self.reviewing = reviewing
        self.approved = approved
        self.progress = progress or (lambda message: None)
        self.location = 'Documento'
        self.findings = {}
        self.evidence = {}
        self.ocr_cache = ocr_cache if ocr_cache is not None else {}
        self.case_id = case_id or ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(12))
        self.encounters = {}
        self.ocr_words = None
        self.ocr_seen = []
        self.regions = {}
        self.zone_fields = []
        self.learning = learning
        self.known_entities = known_entities or {}
        self.discovered_entities = {'PERSONA': set(), 'IDENTIFICACION': set()}

    @contextmanager
    def at(self, location):
        check_cancelled()
        previous = self.location
        self.location = previous + ' / ' + location
        self.progress(self.location)
        try:
            yield
        finally:
            self.location = previous

    def spans(self, text):
        check_cancelled()
        scope = (self.location, hashlib.sha256(text.encode()).hexdigest())
        encounter = self.encounters.get(scope, 0)
        self.encounters[scope] = encounter + 1
        if self.reviewing:
            evidence = self.evidence.setdefault(self.location, {'text': '', 'image': None, 'words': []})
            if not evidence['text']:
                evidence['text'] = text
        candidates = []
        for term in self.manual:
            expression = r'\s+'.join(re.escape(part) for part in term.split())
            candidates.extend((m.start(), m.end(), 'DATO', m.group())
                              for m in re.finditer(expression, text, re.IGNORECASE))
        if self.automatic:
            for kind, pattern in PATTERNS.items():
                for m in pattern.finditer(text):
                    group = 1 if pattern.groups else 0
                    if kind in PERSON_KINDS and NON_PERSON_WORDS.intersection(m.group(group).upper().split()):
                        continue
                    category = 'PERSONA' if kind in PERSON_KINDS else 'IDENTIFICACION'
                    self.discovered_entities[category].add(m.group(group))
                    candidates.append((m.start(group), m.end(group), kind, m.group(group)))
            candidates.extend(known_entity_spans(text, self.known_entities))
        end = -1
        for start, stop, kind, value in sorted(candidates, key=lambda x: (x[0], -(x[1]-x[0]))):
            check_cancelled()
            if start >= end:
                end = stop
                if self.ocr_words is not None:
                    boxes = [box for a, b, box, _ in self.ocr_words if start < b and stop > a]
                    if boxes:
                        region = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                                  max(b[2] for b in boxes), max(b[3] for b in boxes))
                        duplicate = False
                        for previous_value, old in self.ocr_seen:
                            if previous_value != value.casefold():
                                continue
                            intersection = max(0, min(region[2], old[2])-max(region[0], old[0])) * max(0, min(region[3], old[3])-max(region[1], old[1]))
                            area = max((region[2]-region[0])*(region[3]-region[1]), (old[2]-old[0])*(old[3]-old[1]))
                            if area and intersection / area > 0.7:
                                duplicate = True
                                break
                        if duplicate:
                            continue
                        self.ocr_seen.append((value.casefold(), region))
                identity = json.dumps([self.location, scope[1], encounter, start, stop, kind, value], ensure_ascii=False)
                finding_id = hashlib.sha256(identity.encode()).hexdigest()
                if self.reviewing and finding_id not in self.findings:
                    self.findings[finding_id] = {'id': finding_id, 'location': self.location, 'kind': kind,
                        'value': value, 'context': text[max(0, start-85):min(len(text), stop+85)],
                        'start': start, 'stop': stop, 'token': None}
                    self.progress(f'Detectado {kind}: {value} — {self.location}')
                key = (kind, value.casefold())
                if key not in self.mapping:
                    self.mapping[key] = f'ANON_{kind}_{self.case_id}_{len(self.mapping)+1:04d}'
                if self.reviewing:
                    self.findings[finding_id]['token'] = self.mapping[key]
                if self.approved is not None and finding_id not in self.approved:
                    continue
                self.fields.setdefault(self.mapping[key], value)
                self.applied_findings.add(finding_id)
                if self.learning:
                    self.progress(f'Detectado {kind}: {value} — {self.location}')
                if not self.reviewing and not self.learning:
                    self.progress(f'Anonimizando {kind}: {value} — {self.location}')
                yield start, stop, self.mapping[key]

    def replace(self, text):
        result, last = [], 0
        for start, stop, token in self.spans(text):
            result.extend((text[last:start], token))
            self.count += 1
            last = stop
        return ''.join(result) + text[last:]


def _decode(data):
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16'), 'utf-16'
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig'), 'utf-8-sig'
    if b'\x00' in data:
        raise AnonymizationError('El archivo parece binario; no se procesará como texto.')
    try:
        return data.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        raise AnonymizationError('Texto con codificación desconocida. Conviértalo a UTF-8.') from None


def _media(data, suffix):
    return (suffix in MEDIA or data.startswith((b'ID3', b'fLaC', b'OggS', b'\x1aE\xdf\xa3'))
            or (data[:4] == b'RIFF' and data[8:12] in (b'WAVE', b'AVI '))
            or (data[4:8] == b'ftyp' and data[8:12] not in (b'avif', b'avis', b'heic', b'heix', b'mif1')))


def _notice(replacer, message):
    if message not in replacer.warnings:
        replacer.warnings.append(message)


def _covered_pdf(replacer, reason):
    """A shareable substitute, never an unchanged copy of an opaque input."""
    import pymupdf
    _notice(replacer, reason + ' Se generó un PDF sustituto con todo el contenido omitido; restaure para recuperar el original.')
    replacer.output_suffix = '.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 60, 545, 240),
                            'CONTENIDO OCULTO\n\nEl contenido de este archivo se ha omitido porque no se pudo interpretar.\n'
                            'Este PDF es un sustituto y no conserva el formato ni el contenido visible del original.\n'
                            'Use Restaurar original con la copia de recuperacion para recuperarlo.', fontsize=12)
        return doc.tobytes(deflate=True)


def _image(data, suffix, replacer):
    from PIL import Image, ImageSequence
    with Image.open(io.BytesIO(data)) as source:
        frames = []
        for index, frame in enumerate(ImageSequence.Iterator(source)):
            with replacer.at(f'Imagen/página {index+1} (OCR)'):
                stage = 'Analizando' if replacer.reviewing or replacer.learning else 'Anonimizando'
                replacer.progress(f'{stage} página {index+1} de {getattr(source, "n_frames", 1)}')
                result = ocr_redact(frame.copy(), replacer)
                if not (replacer.learning or replacer.reviewing):
                    frames.append(result)
        if replacer.learning or replacer.reviewing:
            return b''
        fmt = source.format
        output = io.BytesIO()
        try:
            options = {'save_all': True, 'append_images': frames[1:]} if len(frames) > 1 and fmt in {'GIF', 'TIFF', 'WEBP'} else {}
            frames[0].save(output, format=fmt, **options)
        except (KeyError, ValueError, OSError):
            return _covered_pdf(replacer, 'La imagen no tiene un codificador de salida disponible.')
    return output.getvalue()


def _archive(data, replacer, depth):
    if depth > 8:
        return _covered_pdf(replacer, 'El archivo contiene más de ocho niveles de contenedores.')
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
        if sum(i.file_size for i in source.infolist()) > MAX_BYTES * 3:
            return _covered_pdf(replacer, 'El contenido descomprimido supera 300 MB.')
        for index, info in enumerate(source.infolist()):
            if info.is_dir():
                continue
            try:
                payload = source.read(info)
            except (RuntimeError, NotImplementedError, zipfile.BadZipFile):
                payload = _covered_pdf(replacer, 'Una entrada del contenedor no pudo leerse.')
            else:
                if _media(payload, Path(info.filename).suffix.lower()):
                    _notice(replacer, 'Se descartaron audios o videos dentro del contenedor.')
                    continue
                with replacer.at(info.filename):
                    payload = transform(payload, Path(info.filename).suffix, replacer, depth + 1)
            suffix = replacer.output_suffix or Path(info.filename).suffix
            # Flat, anonymous names prevent identifiers leaking through internal paths.
            target.writestr(f'archivo_{index+1:04d}{suffix}', payload)
            replacer.output_suffix = None
    _notice(replacer, 'Contenedor ZIP procesado: entradas renombradas y carpetas aplanadas.')
    return output.getvalue()


def _office(data, suffix, replacer):
    """Replace logical paragraphs, including text split across formatting runs."""
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise AnonymizationError('El contenedor Office/OpenDocument no es válido.') from None
    with source:
        if sum(i.file_size for i in source.infolist()) > MAX_BYTES * 3:
            raise AnonymizationError('El contenido descomprimido supera 300 MB.')
        names = source.namelist()
        expected = {'.docx': 'word/document.xml', '.xlsx': 'xl/workbook.xml',
                    '.pptx': 'ppt/presentation.xml'}.get(suffix)
        if (expected and expected not in names) or (suffix.startswith('.od') and 'content.xml' not in names):
            raise AnonymizationError('La extensión no coincide con el documento.')
        if any('/embeddings/' in n or n.endswith('vbaProject.bin') for n in names):
            return _covered_pdf(replacer, 'El documento contiene objetos binarios incrustados o macros.')
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                name = info.filename
                payload = source.read(info)
                with replacer.at(name):
                    if '/media/' in name or name.startswith('Pictures/'):
                        if _media(payload, Path(name).suffix.lower()):
                            return _covered_pdf(replacer, 'El documento contiene audio o video incrustado.')
                        try:
                            payload = _image(payload, Path(name).suffix, replacer)
                        except (OCRError, ProcessingCancelled):
                            raise
                        except Exception:
                            return _covered_pdf(replacer, 'Una imagen incrustada no pudo interpretarse.')
                        if replacer.output_suffix:
                            return _covered_pdf(replacer, 'Una imagen incrustada necesita conversión.')
                    elif name.startswith('docProps/') or name in {'meta.xml', 'Thumbnails/thumbnail.png'}:
                        # Keep valid XML parts, removing metadata values.
                        if name.endswith('.xml'):
                            root = ET.fromstring(payload)
                            for child in list(root):
                                root.remove(child)
                            payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                        else:
                            continue
                    elif name.endswith(('.xml', '.rels')):
                        for _, namespace in ET.iterparse(io.BytesIO(payload), events=('start-ns',)):
                            prefix, uri = namespace
                            if not re.fullmatch(r'ns\d+', prefix):
                                ET.register_namespace(prefix, uri)
                        root = ET.fromstring(payload)
                        if name.endswith('.rels'):
                            for child in list(root):
                                if child.attrib.get('TargetMode') == 'External':
                                    root.remove(child)
                        else:
                            _replace_xml(root, replacer)
                            for node in root.iter():
                                # ElementTree may drop prefixes used only in mc:Ignorable.
                                node.attrib.pop('{http://schemas.openxmlformats.org/markup-compatibility/2006}Ignorable', None)
                            sheet_ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
                            for cell in root.iter(sheet_ns + 'c'):
                                value = cell.find(sheet_ns + 'v')
                                if value is not None and value.text and 'ANON_' in value.text:
                                    cell.set('t', 'str')
                                    formula = cell.find(sheet_ns + 'f')
                                    if formula is not None:
                                        cell.remove(formula)
                        payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
                    target.writestr(info, payload)
        return out.getvalue()


def _replace_xml(root, replacer):
    ns_word = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    ns_draw = 'http://schemas.openxmlformats.org/drawingml/2006/main'
    ns_od = 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'
    containers = {f'{{{ns_word}}}p', f'{{{ns_draw}}}p', f'{{{ns_od}}}p', f'{{{ns_od}}}h',
                  '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si',
                  '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is'}
    handled = set()
    for container in root.iter():
        if container.tag not in containers:
            continue
        slots = []
        for node in container.iter():
            if node.text:
                slots.append((node, 'text', node.text))
            if node is not container and node.tail:
                slots.append((node, 'tail', node.tail))
        full = ''.join(s[2] for s in slots)
        matches = list(replacer.spans(full))
        # Replace from right to left; preserve formatting outside sensitive spans.
        for start, stop, token in reversed(matches):
            offset = 0
            inserted = False
            for node, attr, original in slots:
                left, right = offset, offset + len(original)
                offset = right
                if start < right and stop > left:
                    value = getattr(node, attr) or ''
                    a, b = max(0, start-left), min(len(original), stop-left)
                    setattr(node, attr, value[:a] + (token if not inserted else '') + value[b:])
                    inserted = True
            replacer.count += 1
        handled.update((id(n), a) for n, a, _ in slots)
    for node in root.iter():
        for attr in ('text', 'tail'):
            value = getattr(node, attr)
            if value and (id(node), attr) not in handled:
                setattr(node, attr, replacer.replace(value))
        for key, value in list(node.attrib.items()):
            # Do not alter namespace identifiers or relationship identifiers.
            if key.rsplit('}', 1)[-1] in {'title', 'descr', 'name', 'author'}:
                node.attrib[key] = replacer.replace(value)


def _pdf(data, replacer):
    import pymupdf
    from PIL import Image
    with pymupdf.open(stream=data, filetype='pdf') as doc, pymupdf.open() as clean:
        if doc.needs_pass:
            return _covered_pdf(replacer, 'El PDF está protegido y no se puede leer su contenido.')
        if doc.embfile_count():
            _notice(replacer, 'Los adjuntos del PDF se omiten de la copia para compartir.')
        for page in doc:
            with replacer.at(f'Página {page.number+1}'):
                stage = 'Analizando' if replacer.reviewing or replacer.learning else 'Anonimizando'
                replacer.progress(f'{stage} página {page.number+1} de {len(doc)}')
                if page.get_images() or not page.get_text().strip():
                    # Rasterize mixed and scanned pages: the output cannot retain the
                    # original scan or a hidden text layer underneath the black marks.
                    pix = page.get_pixmap(dpi=300, alpha=False, colorspace=pymupdf.csRGB, annots=False)
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    redacted = ocr_redact(image, replacer)
                    if replacer.learning or replacer.reviewing:
                        continue
                    buffer = io.BytesIO()
                    redacted.save(buffer, format='PNG')
                    target = clean.new_page(width=page.rect.width, height=page.rect.height)
                    target.insert_image(target.rect, stream=buffer.getvalue())
                    continue
                parts, word_spans, offset, last_line = [], [], 0, None
                for x0, y0, x1, y1, word, block, line, _ in page.get_text('words', sort=True):
                    current_line = (block, line)
                    separator = '' if last_line is None else (' ' if current_line == last_line else '\n')
                    parts.extend((separator, word))
                    offset += len(separator)
                    word_spans.append((offset, offset + len(word), (x0, y0, x1, y1), 100))
                    offset += len(word)
                    last_line = current_line
                text = ''.join(parts)
                if replacer.learning:
                    list(replacer.spans(text))
                    continue
                if replacer.reviewing:
                    pix = page.get_pixmap(dpi=100, alpha=False, annots=False)
                    scale = 100 / 72
                    boxes = []
                    for a, b, box, confidence in word_spans:
                        rect = pymupdf.Rect(box) * page.rotation_matrix
                        boxes.append((a, b, tuple(v * scale for v in rect), confidence))
                    replacer.evidence[replacer.location] = {'text': text, 'image': pix.tobytes('png'), 'words': boxes}
                for start, stop, token in replacer.spans(text):
                    for a, b, box, _ in word_spans:
                        if start < b and stop > a:
                            clipped = pymupdf.Rect(box) & page.cropbox
                            if not clipped.is_empty:
                                page.add_redact_annot(clipped, fill=(64/255, 64/255, 64/255))
                    replacer.count += 1
                for region in replacer.regions.get(replacer.location, []):
                    box = region['box'] if isinstance(region, dict) else region
                    # Native PDF evidence is rendered at 100 DPI in rotated
                    # page coordinates; convert back to PDF coordinates.
                    rect = (pymupdf.Rect(box) * (72 / 100)) & page.rect
                    if not rect.is_empty:
                        page.add_redact_annot(rect * page.derotation_matrix, fill=(64/255, 64/255, 64/255))
                    replacer.count += 1
                if replacer.reviewing:
                    continue
                for annot in list(page.annots() or []):
                    if annot.type[0] != 12:
                        page.delete_annot(annot)
                for link in page.get_links():
                    page.delete_link(link)
                page.apply_redactions()
                clean.insert_pdf(doc, from_page=page.number, to_page=page.number, links=False, annots=False, widgets=False)
        return b'' if replacer.learning or replacer.reviewing else clean.tobytes(garbage=4, deflate=True)


def transform(data, suffix, replacer, depth=0):
    """Accept every extension; only audio/video are deliberately discarded."""
    check_cancelled()
    suffix = suffix.lower()
    replacer.output_suffix = None
    if _media(data, suffix):
        raise AnonymizationError('Audio y video están excluidos.')
    try:
        if data.startswith(b'%PDF-'):
            result = _pdf(data, replacer)
            replacer.output_suffix = '.pdf'
            return result
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
            inferred = next((ext for part, ext in [('word/document.xml', '.docx'), ('xl/workbook.xml', '.xlsx'), ('ppt/presentation.xml', '.pptx')] if part in names), None)
            if inferred or (suffix in OFFICE and 'content.xml' in names):
                result = _office(data, inferred or suffix, replacer)
                replacer.output_suffix = replacer.output_suffix or inferred or suffix
                return result
            result = _archive(data, replacer, depth)
            replacer.output_suffix = replacer.output_suffix or '.zip'
            return result
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(data)):
                pass
        except (UnidentifiedImageError, OSError):
            pass
        else:
            return _image(data, suffix, replacer)
        return _text_transform(data, suffix, replacer)
    except (OCRError, ProcessingCancelled):
        raise
    except Exception as exc:
        # A failed reader must not copy uninspected bytes to the shareable output.
        return _covered_pdf(replacer, f'El contenido no pudo interpretarse ({type(exc).__name__}).')


def _text_transform(data, suffix, replacer):
    suffix = suffix.lower()
    if _media(data, suffix):
        raise AnonymizationError('Audio y video están excluidos.')
    text, encoding = _decode(data)
    if any(ord(c) < 32 and c not in '\r\n\t\f' for c in text):
        raise AnonymizationError('Contenido binario no interpretable como texto.')
    if suffix == '.json':
        def walk(value):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    new_key = replacer.replace(key)
                    if new_key in result:
                        raise AnonymizationError('La anonimización produciría claves JSON duplicadas.')
                    result[new_key] = walk(item)
                return result
            if isinstance(value, list):
                return [walk(item) for item in value]
            if isinstance(value, str):
                return replacer.replace(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                changed = replacer.replace(str(value))
                return changed if changed != str(value) else value
            return value
        return json.dumps(walk(json.loads(text)), ensure_ascii=False, indent=2).encode(encoding)
    if suffix == '.xml':
        root = ET.fromstring(text)
        _replace_xml(root, replacer)
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return replacer.replace(text).encode(encoding)


def _recovery(original, filename, fields=None, zones=None):
    check_cancelled()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('original', original)
        archive.writestr('info.json', json.dumps({
            'version': 2 if fields is not None else 1, 'name': filename,
            'sha256': hashlib.sha256(original).hexdigest(),
            **({'fields': fields} if fields is not None else {}),
            **({'zones': zones} if zones else {}),
        }, ensure_ascii=False))
    check_cancelled()
    return buffer.getvalue()


def _write_new(path, data):
    # Exclusive creation prevents accidental overwrite, including original files.
    check_cancelled()
    with open(path, 'xb') as f:
        try:
            for start in range(0, len(data), 1024 * 1024):
                check_cancelled()
                f.write(data[start:start + 1024 * 1024])
            check_cancelled()
        except BaseException:
            f.close()
            Path(path).unlink(missing_ok=True)
            raise


@dataclass
class ReviewPlan:
    path: Path
    original: bytes
    manual: tuple
    automatic: bool
    findings: dict
    evidence: dict
    warnings: list
    ocr_pages: int
    ocr_cache: dict
    suffix: str
    purpose: str = 'anonymize'
    restoration_fields: dict | None = None
    case_id: str | None = None
    known_entities: dict | None = None


def analyze(path, manual=(), automatic=True, progress=None):
    """Read and propose changes, without writing any output or recovery file."""
    path = Path(path)
    if not path.is_file():
        raise AnonymizationError('Seleccione un archivo existente.')
    if path.stat().st_size > MAX_BYTES:
        raise AnonymizationError('El límite por archivo es 100 MB.')
    data = path.read_bytes()
    cache, known_entities = {}, {}
    if automatic and data.startswith(b'%PDF-'):
        learner = Replacer(manual, automatic=True, progress=progress, ocr_cache=cache, learning=True)
        try:
            _pdf(data, learner)
        except (OCRError, ProcessingCancelled):
            raise
        except Exception:
            # Keep the normal reader's damaged/protected-file handling below.
            pass
        known_entities = {kind: tuple(sorted(values)) for kind, values in learner.discovered_entities.items()}
    replacer = Replacer(manual, automatic, reviewing=True, progress=progress,
                        ocr_cache=cache, known_entities=known_entities)
    replacer.progress('Analizando: ' + path.name)
    transform(data, path.suffix, replacer)
    if automatic:
        _propose_signature_blocks(replacer)
    return ReviewPlan(path, data, tuple(manual), automatic, replacer.findings,
                      replacer.evidence, replacer.warnings, replacer.ocr_pages,
                      replacer.ocr_cache, replacer.output_suffix or path.suffix, case_id=replacer.case_id,
                      known_entities=known_entities)


def _propose_signature_blocks(replacer):
    """Propose a visual redaction around printed signature labels on PDF pages."""
    for location, evidence in replacer.evidence.items():
        if not location.startswith('Documento / Página ') or not evidence.get('image'):
            continue
        from PIL import Image
        with Image.open(io.BytesIO(evidence['image'])) as image:
            width, height = image.size
        text = evidence.get('text', '')
        anchors = []
        for start, stop, box, _ in evidence.get('words', []):
            if re.fullmatch(r'firma[:.]?', text[start:stop], re.IGNORECASE):
                x0, y0, x1, y1 = box
                if y0 < height * 0.45:
                    continue
                # A lone "Firma" can be printed inside an ID-card photo or a
                # form. Only propose a block when its ID label is nearby.
                id_labels = {'cc', 'cédula', 'cedula', 'identificación', 'identificacion'}
                if not any(text[a:b].casefold().strip(':.').replace('.', '') in id_labels
                           and y0 <= word_box[1] <= y0 + height * .15
                           and abs(word_box[0] - x0) < width * .25
                           for a, b, word_box, _ in evidence['words']):
                    continue
                if any(abs(x0 - old[0]) < width * .04 and abs(y0 - old[1]) < height * .025 for old in anchors):
                    continue
                anchors.append((x0, y0, x1, y1))
        # OCR can report the same printed label in several passes with shifted
        # coordinates. Offer one block per page; further zones can be drawn by hand.
        anchors = sorted(anchors, key=lambda box: box[1], reverse=True)[:1]
        for number, (x0, y0, x1, y1) in enumerate(anchors, 1):
            nearby = [box for a, b, box, _ in evidence['words']
                      if y0 <= box[1] <= y0 + height * .15
                      and box[0] < x0 + width * .65]
            left = max(0, int(min([x0] + [box[0] for box in nearby]) - width * .02))
            right = min(width - 1, int(max(x1 + width * .52, width * .75)))
            top = max(0, int(y0 - height * .06))
            bottom = min(height - 1, int(max(y0 + height * .15,
                                               max([y1] + [box[3] for box in nearby]) + height * .015)))
            if right - left < 150:
                left = max(0, min(left, width - 151))
                right = min(width - 1, left + 150)
            if bottom - top < 22:
                top = max(0, min(top, height - 23))
                bottom = min(height - 1, top + 22)
            identity = 'firma_' + hashlib.sha256(f'{location}:{x0}:{y0}'.encode()).hexdigest()
            replacer.findings[identity] = {
                'id': identity, 'kind': 'ZONA', 'value': 'Bloque de firma y cédula',
                'location': location, 'box': (left, top, right, bottom),
                'start': -1, 'stop': -1,
                'context': 'Zona propuesta alrededor de la firma; revise que cubra el trazo manuscrito, nombre y cédula.',
                'token': f'ANON_FIRMA_{replacer.case_id}_{number:04d}',
            }
        if anchors:
            continue
        # Some tutela petitions close with "Atentamente", followed by the
        # signer's name and C.C. number, without a printed "Firma" label.
        words = evidence.get('words', [])
        closings = [(a, b, box) for a, b, box, _ in words
                    if re.fullmatch(r'atentamente[,]?', text[a:b], re.IGNORECASE)]
        for _, _, closing in reversed(closings):
            cx0, cy0, cx1, cy1 = closing
            if cy0 < height * .25:
                continue
            ids = [box for a, b, box, _ in words
                   if re.fullmatch(r'(?:c\.?c\.?|c[eé]dula|identificaci[oó]n)', text[a:b], re.IGNORECASE)
                   and cy1 < box[1] < cy1 + height * .15]
            if not ids:
                continue
            id_box = min(ids, key=lambda box: box[1])
            block_words = [box for a, b, box, _ in words
                           if cy1 < box[1] <= id_box[3] + height * .035
                           and box[0] < width * .80]
            if not block_words:
                continue
            left = max(0, int(min(box[0] for box in block_words) - width * .02))
            right = min(width - 1, int(max(box[2] for box in block_words) + width * .02))
            top = max(0, int(cy1 + height * .003))
            bottom = min(height - 1, int(max(box[3] for box in block_words) + height * .012))
            if right <= left or bottom <= top:
                continue
            identity = 'firma_' + hashlib.sha256(f'{location}:{cx0}:{cy0}'.encode()).hexdigest()
            replacer.findings[identity] = {
                'id': identity, 'kind': 'ZONA', 'value': 'Bloque final de firma y cédula',
                'location': location, 'box': (left, top, right, bottom),
                'start': -1, 'stop': -1,
                'context': 'Zona propuesta desde el cierre hasta la identificación; revise que cubra todo el bloque.',
                'token': f'ANON_FIRMA_{replacer.case_id}_0001',
            }
            break


def apply_review(plan, approved, output_dir, progress=None):
    """Apply only occurrence IDs approved from this exact source snapshot."""
    if plan.purpose == 'restore_fields':
        from restauracion_campos import apply_field_review
        return apply_field_review(plan, approved, output_dir, progress)
    approved = set(approved)
    if not approved.issubset(plan.findings):
        raise AnonymizationError('La selección no corresponde al análisis revisado.')
    if plan.path.read_bytes() != plan.original:
        raise AnonymizationError('El original cambió después del análisis. Vuelva a analizarlo antes de autorizar.')
    replacer = Replacer(plan.manual, plan.automatic, approved=approved, progress=progress,
                        ocr_cache=plan.ocr_cache, case_id=plan.case_id, known_entities=plan.known_entities)
    for finding_id in sorted(approved):
        finding = plan.findings[finding_id]
        if finding.get('kind') == 'ZONA':
            evidence = plan.evidence.get(finding['location'], {})
            if evidence.get('image'):
                from PIL import Image
                with Image.open(io.BytesIO(evidence['image'])) as preview:
                    width, height = preview.size
                x0, y0, x1, y1 = finding['box']
                box = (max(0, min(width - 1, x0)), max(0, min(height - 1, y0)),
                       max(0, min(width - 1, x1)), max(0, min(height - 1, y1)))
                if box[2] <= box[0] or box[3] <= box[1]:
                    raise AnonymizationError('La zona seleccionada está fuera de la página. Ajústela en la revisión.')
                finding['box'] = box
            region = {'box': finding['box']}
            if finding.get('token'):
                region['token'] = finding['token']
            replacer.regions.setdefault(finding['location'], []).append(region)
            if finding.get('token'):
                replacer.zone_fields.append({'token': finding['token'], 'location': finding['location'], 'box': finding['box']})
    anonymized = transform(plan.original, plan.path.suffix, replacer)
    expected = {identity for identity in approved if plan.findings[identity]['kind'] != 'ZONA'}
    if expected - replacer.applied_findings:
        raise AnonymizationError('No se pudieron ocultar todos los datos seleccionados. No se generó el archivo; vuelva a analizar el documento.')
    if (replacer.output_suffix or plan.path.suffix) != plan.suffix or set(replacer.warnings) - set(plan.warnings):
        raise AnonymizationError('El resultado requiere cambios distintos a los revisados. Vuelva a analizar el archivo.')
    from verificacion import verificar_pdf_seleccionado
    return _save_result(plan.path, plan.original, anonymized, replacer, output_dir,
                        verifier=lambda saved: verificar_pdf_seleccionado(plan, approved, saved))


def _save_result(path, data, anonymized, replacer, output_dir, verifier=None):
    output_dir = Path(output_dir)
    recovery = _recovery(data, path.name, replacer.fields, replacer.zone_fields)
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f'archivo_anon_{secrets.token_hex(4)}{replacer.output_suffix or path.suffix}'
    output, recovery_path = output_dir / name, output_dir / (name + RECOVERY_SUFFIX)
    _write_new(recovery_path, recovery)
    output_created = False
    try:
        _write_new(output, anonymized)
        output_created = True
        if verifier is not None:
            verifier(output.read_bytes())
    except BaseException:
        if output_created:
            output.unlink(missing_ok=True)
        recovery_path.unlink(missing_ok=True)
        raise
    return {'output': str(output.resolve()), 'recovery': str(recovery_path.resolve()),
            'replacements': replacer.count, 'unique': len(replacer.mapping),
            'warnings': replacer.warnings, 'ocr_pages': replacer.ocr_pages}


def anonymize(path, output_dir, manual=(), automatic=True):
    path, output_dir = Path(path), Path(output_dir)
    if not path.is_file():
        raise AnonymizationError('Seleccione un archivo existente.')
    if path.stat().st_size > MAX_BYTES:
        raise AnonymizationError('El límite por archivo es 100 MB.')
    data = path.read_bytes()
    replacer = Replacer(manual, automatic)
    anonymized = transform(data, path.suffix, replacer)
    return _save_result(path, data, anonymized, replacer, output_dir)


def read_recovery(path):
    path = Path(path)
    recovery_path = path if path.suffix.lower() == RECOVERY_SUFFIX else Path(str(path) + RECOVERY_SUFFIX)
    if not recovery_path.is_file():
        raise AnonymizationError('No se encontró la copia de recuperación .restauracion junto al archivo seleccionado.')
    if recovery_path.stat().st_size > MAX_BYTES * 2:
        raise AnonymizationError('La copia de recuperación supera el tamaño admitido.')
    try:
        with zipfile.ZipFile(recovery_path) as archive:
            if sorted(archive.namelist()) != ['info.json', 'original']:
                raise AnonymizationError('No es una copia de recuperación compatible.')
            if archive.getinfo('original').file_size > MAX_BYTES or archive.getinfo('info.json').file_size > 8 * 1024 * 1024:
                raise AnonymizationError('El contenido supera el tamaño admitido.')
            body = json.loads(archive.read('info.json'))
            original = archive.read('original')
    except (zipfile.BadZipFile, UnicodeError, json.JSONDecodeError):
        raise AnonymizationError('La copia de recuperación no es válida o está dañada.') from None
    if not isinstance(body, dict) or body.get('version') not in {1, 2}:
        raise AnonymizationError('La copia de recuperación no es compatible.')
    name = body.get('name')
    if not isinstance(name, str) or not name or Path(name).name != name or any(c in name for c in '/\\:') or name in {'.', '..'}:
        raise AnonymizationError('Nombre de archivo inválido en la copia de recuperación.')
    if hashlib.sha256(original).hexdigest() != body.get('sha256'):
        raise AnonymizationError('La copia de recuperación está dañada.')
    fields = body.get('fields', {})
    if not isinstance(fields, dict) or any(not isinstance(token, str) or
            not re.fullmatch(r'ANON_[A-Z_]+_\d{4,}', token) or
            not isinstance(value, str) or not value or len(value) > 10000
            for token, value in fields.items()):
        raise AnonymizationError('Los campos de recuperación no son válidos.')
    return body, original


def restore(path, output_dir):
    body, original = read_recovery(path)
    name = body['name']
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    p = Path(name)
    if p.suffix.lower() in {'.crdownload', '.part'} and original.startswith(b'%PDF-'):
        p = Path(p.stem)
        if p.suffix.lower() != '.pdf':
            p = p.with_name(p.name + '.pdf')
    target = output_dir / f'{p.stem}_restaurado_{secrets.token_hex(4)}{p.suffix}'
    _write_new(target, original)
    return str(target.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    anon = sub.add_parser('anonimizar')
    anon.add_argument('archivo', type=Path)
    anon.add_argument('--datos', type=Path, help='TXT UTF-8: un nombre, dirección o dato sensible por línea')
    anon.add_argument('--solo-manual', action='store_true')
    recover = sub.add_parser('restaurar')
    recover.add_argument('archivo', type=Path, help='Archivo anonimizado o su copia .restauracion')
    for command in (anon, recover):
        command.add_argument('--salida', type=Path, default=Path('salida'))
    args = parser.parse_args()
    try:
        if args.action == 'anonimizar':
            manual = args.datos.read_text(encoding='utf-8-sig').splitlines() if args.datos else []
            plan = analyze(args.archivo, manual, not args.solo_manual, print)
            proposals = list(plan.findings.values())
            for index, finding in enumerate(proposals, 1):
                print(f"{index}. [{finding['kind']}] {finding['value']} — {finding['location']}\n   {finding['context']}")
            for warning in plan.warnings:
                print('AVISO:', warning)
            print('Al generar se limpian metadatos y enlaces según el formato.')
            choice = input('Autorice números separados por coma, TODAS, o Enter para cancelar: ').strip()
            if not choice:
                print('Cancelado. No se generaron archivos.')
                return
            if choice.upper() == 'TODAS':
                approved = set(plan.findings)
            else:
                indexes = [int(item.strip()) for item in choice.split(',')]
                if any(i < 1 or i > len(proposals) for i in indexes):
                    raise AnonymizationError('Número de propuesta inválido.')
                approved = {proposals[i-1]['id'] for i in indexes}
            print(json.dumps(apply_review(plan, approved, args.salida, print), ensure_ascii=False, indent=2))
        else:
            print('Restaurado:', restore(args.archivo, args.salida))
    except (ValueError, OSError, OCRError, zipfile.BadZipFile, ET.ParseError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
