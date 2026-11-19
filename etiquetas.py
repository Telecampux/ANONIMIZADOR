"""Etiquetas opacas que caben estrictamente en el campo original."""

from anonimizador import AnonymizationError


class LabelFitError(AnonymizationError):
    pass


def _font(size):
    from PIL import ImageFont
    for name in ('DejaVuSans.ttf', 'arial.ttf', 'C:/Windows/Fonts/arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def image_label(image, box, token):
    from PIL import ImageDraw

    x0, y0, x1, y1 = map(int, box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(image.width, x1), min(image.height, y1)
    width, height = x1 - x0, y1 - y0
    draw = ImageDraw.Draw(image)
    font = None
    for size in range(min(48, height - 2), 7, -1):
        candidate = _font(size)
        bounds = draw.textbbox((0, 0), token, font=candidate)
        if bounds[2] - bounds[0] <= width - 4 and bounds[3] - bounds[1] <= height - 2:
            font = candidate
            break
    if font is None:
        if width < 4 or height < 8:
            raise LabelFitError('El campo no tiene espacio visible para el código.')
        font = _font(max(8, min(48, height - 2)))
        while token and draw.textbbox((0, 0), token, font=font)[2] > width - 2:
            token = token[:-1]
        if not token:
            token = 'A'
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill='#fff2a8')
    bounds = draw.textbbox((0, 0), token, font=font)
    draw.text((x0 + (width - (bounds[2]-bounds[0])) / 2 - bounds[0],
               y0 + (height - (bounds[3]-bounds[1])) / 2 - bounds[1]),
              token, fill='#202020', font=font)


def pdf_label(page, box, token):
    import pymupdf

    rect = pymupdf.Rect(box)
    if rect.width <= 2 or rect.height <= 3:
        raise LabelFitError('El campo no tiene espacio visible para el código.')
    size = min(24, max(3, rect.height - 2))
    visible = token
    while visible and pymupdf.get_text_length(visible, fontname='helv', fontsize=size) > rect.width - 2:
        visible = visible[:-1]
    if not visible:
        visible = 'A'
    page.draw_rect(rect, color=None, fill=(1, 0.95, 0.66), overlay=True)
    width = pymupdf.get_text_length(visible, fontname='helv', fontsize=size)
    x = rect.x0 + (rect.width - width) / 2
    baseline = rect.y0 + (rect.height + size) / 2 - 1
    page.insert_text((x, baseline), visible, fontname='helv', fontsize=size,
                     color=(0.12, 0.12, 0.12), overlay=True)
    if visible != token:
        page.insert_text((x, baseline), token, fontname='helv', fontsize=size,
                         render_mode=3, overlay=True)
