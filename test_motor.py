import tempfile
import unittest
from pathlib import Path
import fitz
from docx import Document
from openpyxl import Workbook, load_workbook
from pptx import Presentation
from motor import procesar, reemplazar


class Pruebas(unittest.TestCase):
    def test_nombres_personas(self):
        categoria = 'Nombres propios de personas (detección en español)'
        texto = 'La señora María García presentó la solicitud. Juan Pérez recibió el documento.'
        salida, count = reemplazar(texto, [categoria], [])
        self.assertNotIn('María García', salida)
        self.assertNotIn('Juan Pérez', salida)
        self.assertGreaterEqual(count, 2)
        self.assertIn('solicitud', salida)
        # Desmarcar la categoría conserva los nombres.
        self.assertEqual(reemplazar(texto, [], [])[0], texto)

    def test_imagen_zonas_y_metadatos(self):
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        with tempfile.TemporaryDirectory() as carpeta:
            root = Path(carpeta)
            imagen = Image.new('RGB', (100, 100), 'white')
            info = PngInfo()
            info.add_text('autor', 'Secreto')
            imagen.save(root / 'a.png', pnginfo=info)
            with self.assertRaises(ValueError):
                procesar(root / 'a.png', root / 'fallo.png', [], [])
            self.assertFalse((root / 'fallo.png').exists())
            self.assertEqual(procesar(root / 'a.png', root / 'b.png', [], [], [(10, 10, 30, 30)]), 1)
            with Image.open(root / 'b.png') as salida:
                self.assertEqual(salida.getpixel((20, 20)), (0, 0, 0))
                self.assertEqual(salida.getpixel((80, 80)), (255, 255, 255))
                self.assertNotIn('autor', salida.info)

    def test_solapamientos(self):
        texto, count = reemplazar('Ana Perez: ana@example.com', ['Correos electrónicos'], ['Ana', 'Ana Perez'])
        self.assertEqual(texto, '[ANONIMIZADO]: [ANONIMIZADO]')
        self.assertEqual(count, 2)

    def test_documentos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            root = Path(carpeta)
            doc = Document()
            doc.add_paragraph('Secreto Privado')
            doc.sections[0].header.paragraphs[0].text = 'Secreto Privado'
            doc.save(root / 'a.docx')
            self.assertGreater(procesar(root / 'a.docx', root / 'b.docx', [], ['Secreto Privado']), 0)
            salida = Document(root / 'b.docx')
            self.assertNotIn('Secreto', '\n'.join(p.text for p in salida.paragraphs))
            wb = Workbook()
            wb.active['A1'] = '=HYPERLINK("http://example.com/Secreto","Secreto")'
            wb.save(root / 'a.xlsx')
            procesar(root / 'a.xlsx', root / 'b.xlsx', [], ['Secreto'])
            resultado = load_workbook(root / 'b.xlsx')
            self.assertEqual(resultado.active['A1'].data_type, 's')
            self.assertNotIn('Secreto', resultado.active['A1'].value)
            resultado.close()
            ppt = Presentation()
            slide = ppt.slides.add_slide(ppt.slide_layouts[1])
            slide.shapes.title.text = 'Secreto'
            ppt.save(root / 'a.pptx')
            self.assertEqual(procesar(root / 'a.pptx', root / 'b.pptx', [], ['Secreto']), 1)
            self.assertNotIn('Secreto', str([s.text for s in Presentation(root / 'b.pptx').slides[0].shapes]))

    def test_pdf_redaccion_real(self):
        with tempfile.TemporaryDirectory() as carpeta:
            root = Path(carpeta)
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((50, 60), 'Secreto visible')
            rect = page.search_for('Secreto')[0]
            doc.set_metadata({'author': 'Secreto'})
            doc.embfile_add('oculto.txt', b'Secreto')
            doc.save(root / 'a.pdf')
            doc.close()
            self.assertEqual(procesar(root / 'a.pdf', root / 'b.pdf', [], ['Secreto']), 1)
            with fitz.open(root / 'b.pdf') as result:
                self.assertEqual(result.embfile_count(), 0)
                self.assertFalse(result.metadata.get('author'))
                self.assertEqual(result[0].get_text(), '')
                pix = result[0].get_pixmap(clip=fitz.Rect(rect.x0+1, rect.y0+1, rect.x1-1, rect.y1-1))
                self.assertLess(sum(pix.samples) / len(pix.samples), 10)
            self.assertTrue((root / 'a.pdf').exists())


if __name__ == '__main__':
    unittest.main()
