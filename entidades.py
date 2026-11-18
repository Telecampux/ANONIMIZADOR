"""Coincidencias de personas ya identificadas dentro del mismo documento."""
import re
import unicodedata


def normalized_word(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.upper()) if c.isalpha())


def edit_distance(left, right):
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (a != b)))
        previous = current
    return previous[-1]


def known_entity_spans(text, entities):
    """Only match names/IDs learned from this document, never general numbers."""
    tokens = list(re.finditer(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,}(?:[:'][A-Za-zÁÉÍÓÚÑÜáéíóúñü]+)?", text))
    normalized = [normalized_word(token.group()) for token in tokens]
    pairs = set()
    for name in entities.get('PERSONA', ()):
        parts = [normalized_word(part) for part in name.split()]
        parts = [part for part in parts if part not in {'DE', 'DEL', 'LA', 'LAS', 'LOS', 'Y'}]
        for left, right in zip(parts, parts[1:]):
            pairs.add((left, right))
        # Names in authorizations may put the surnames before the given names.
        if len(parts) >= 4:
            pairs.add((parts[-1], parts[0]))
    for i in range(len(tokens)-1):
        a, b = tokens[i:i+2]
        if not re.fullmatch(r'[\s.:,-]+', text[a.end():b.start()]):
            continue
        for left, right in pairs:
            x, y = normalized[i:i+2]
            # Require an exact neighbouring name; OCR tolerance is limited to
            # the other word, so isolated capitalized phrases do not qualify.
            if not ((x == left and len(left) >= 3) or (y == right and len(right) >= 3)):
                continue
            if edit_distance(x, left) <= (2 if len(left) >= 5 else 0) and edit_distance(y, right) <= (2 if len(right) >= 5 else 0):
                yield a.start(), b.end(), 'PERSONA', text[a.start():b.end()]
                break
    substitutions = {'0': '0Oo', '1': '1Il', '2': '2Zz', '5': '5Ss', '8': '8B'}
    for identifier in entities.get('IDENTIFICACION', ()):
        digits = re.sub(r'\D', '', identifier)
        if len(digits) < 6:
            continue
        expression = r'(?<![\w])' + r'[ .\-]*'.join('[' + substitutions.get(digit, digit) + '?]' for digit in digits) + r'(?![\w])'
        for match in re.finditer(expression, text):
            if match.group().count('?') <= 1:
                yield match.start(), match.end(), 'IDENTIFICACION', match.group()
