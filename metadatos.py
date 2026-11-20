"""Inventory source metadata shown before creating a shareable copy."""

import io
import zipfile
import xml.etree.ElementTree as ET


def _short(value):
    if isinstance(value, bytes):
        return f'{len(value)} bytes binarios'
    text = ' '.join(str(value).split())
    return text[:240] + ('…' if len(text) > 240 else '')


def inspect_metadata(data, suffix):
    found = []
    def add(location, key, value):
        if value not in (None, '', b''):
            found.append((location, key, _short(value)))

    if data.startswith(b'%PDF-'):
        import pymupdf
        with pymupdf.open(stream=data, filetype='pdf') as doc:
            for key, value in (doc.metadata or {}).items():
                add('PDF', key, value)
            xmp = doc.get_xml_metadata()
            if xmp:
                try:
                    root = ET.fromstring(xmp)
                    for node in root.iter():
                        if node.text and node.text.strip():
                            add('PDF / XMP', node.tag.rsplit('}', 1)[-1], node.text)
                except ET.ParseError:
                    add('PDF', 'XMP', xmp)
    elif zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            add('Contenedor', 'comentario', archive.comment)
            for info in archive.infolist():
                name = info.filename
                if name.startswith('docProps/') or name == 'meta.xml':
                    try:
                        root = ET.fromstring(archive.read(info))
                    except ET.ParseError:
                        add(name, 'XML de propiedades', 'presente')
                    else:
                        for node in root.iter():
                            if node.text and node.text.strip():
                                add(name, node.tag.rsplit('}', 1)[-1], node.text)
                add(name, 'fecha interna', '%04d-%02d-%02d %02d:%02d:%02d' % info.date_time
                    if info.date_time != (1980, 1, 1, 0, 0, 0) else '')
                add(name, 'comentario interno', info.comment)
    else:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(data)) as image:
                from PIL.ExifTags import TAGS
                for key, value in image.getexif().items():
                    add('Imagen / EXIF', TAGS.get(key, str(key)), value)
                for key, value in image.info.items():
                    if key != 'exif':
                        add('Imagen', key, value)
        except (UnidentifiedImageError, OSError):
            pass
    return found
