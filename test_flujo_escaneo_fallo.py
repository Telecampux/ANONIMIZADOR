"""Recorrido local: escaneo revisado, fallo nuevo y restauración de campos."""
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from anonimizador import analyze, apply_review, read_recovery
from restauracion_campos import restore_judgment


class ScannedJudgmentFlowTests(unittest.TestCase):
    def test_scanned_pdf_codes_survive_in_new_judgment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'escaneo.pdf'
            picture = io.BytesIO()
            image = Image.new('RGB', (1200, 500), 'white')
            drawing = ImageDraw.Draw(image)
            font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 40)
            drawing.text((60, 80), 'INFORME PUBLICO', fill='black', font=font)
            drawing.text((60, 170), 'Nombre: Maria Perez', fill='black', font=font)
            drawing.text((60, 300), 'Este contenido debe permanecer visible.', fill='black', font=font)
            image.save(picture, format='PNG')
            with pymupdf.open() as doc:
                page = doc.new_page(width=900, height=450)
                page.insert_image(page.rect, stream=picture.getvalue())
                doc.save(source)

            plan = analyze(source, ['Maria Perez'])
            selected = {key for key, finding in plan.findings.items()
                        if finding['kind'] == 'DATO' and finding['value'] == 'Maria Perez'}
            self.assertTrue(selected)
            result = apply_review(plan, selected, root / 'anonimizado')
            fields = read_recovery(result['recovery'])[0]['fields']
            self.assertEqual(len(fields), 1)
            code = next(iter(fields))
            self.assertEqual(fields[code], 'Maria Perez')
            with pymupdf.open(result['output']) as doc:
                self.assertIn(code, doc[0].get_text())
                self.assertNotIn('Maria Perez', doc[0].get_text())

            # Simula el texto nuevo que produciría el sustanciador con el código completo.
            judgment = root / 'fallo.docx'
            with zipfile.ZipFile(judgment, 'w') as archive:
                archive.writestr('word/document.xml',
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    f'<w:body><w:p><w:r><w:t>AMPARAR a {code}. Decisión nueva.</w:t></w:r></w:p></w:body></w:document>')
            restored = restore_judgment(judgment, result['recovery'], root / 'restaurado')
            with zipfile.ZipFile(restored['output']) as archive:
                text = archive.read('word/document.xml').decode('utf-8')
            self.assertIn('AMPARAR a Maria Perez. Decisión nueva.', text)
            self.assertNotIn(code, text)
            self.assertEqual(restored['fields'], 1)
            with zipfile.ZipFile(judgment) as archive:
                self.assertIn(code, archive.read('word/document.xml').decode('utf-8'))
