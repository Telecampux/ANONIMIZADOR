import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from lector_fallo import LectorFallo
from motor import FORMATOS
from formatos_documentos import filtros_documentos


class LecturaFallo(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        self.lector = LectorFallo(self.root, lambda: str(self.base))

    def tearDown(self):
        self.root.destroy()
        self.temporal.cleanup()

    def test_lee_formatos_sin_modificar_originales(self):
        for extension in ('.txt', '.md', '.docx'):
            with self.subTest(extension=extension):
                ruta = self.base / ('fallo' + extension)
                if extension == '.docx':
                    doc = Document()
                    doc.add_paragraph('Fallo de Ana Pérez')
                    doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Decisión concedida'
                    doc.save(ruta)
                else:
                    ruta.write_text('Fallo de Ana Pérez\nDecisión concedida', encoding='utf-8')
                antes = ruta.read_bytes()
                self.assertTrue(self.lector.cargar(ruta))
                texto = self.lector.texto.get('1.0', 'end-1c')
                self.assertIn('Ana Pérez', texto)
                self.assertIn('Decisión concedida', texto)
                self.assertEqual(ruta.read_bytes(), antes)
                self.assertEqual(str(self.lector.texto.cget('state')), 'disabled')

    def test_selector_recuerda_carpeta_y_cancelar_conserva_lectura(self):
        ruta = self.base / 'fallo.txt'
        ruta.write_text('Decisión', encoding='utf-8')
        with patch('lector_fallo.filedialog.askopenfilename', return_value=str(ruta)):
            self.lector.elegir()
        with patch('lector_fallo.filedialog.askopenfilename', return_value='') as selector:
            self.lector.elegir()
        self.assertEqual(selector.call_args.kwargs['initialdir'], str(self.base))
        self.assertEqual(self.lector.texto.get('1.0', 'end-1c'), 'Decisión')

    def test_error_conserva_lectura(self):
        ruta = self.base / 'fallo.txt'
        ruta.write_text('Decisión', encoding='utf-8')
        self.lector.cargar(ruta)
        with patch('lector_fallo.messagebox.showerror') as aviso:
            self.assertFalse(self.lector.cargar(self.base / 'ausente.docx'))
        aviso.assert_called_once()
        self.assertEqual(self.lector.texto.get('1.0', 'end-1c'), 'Decisión')

    def test_lee_excel_powerpoint_pdf_e_imagen(self):
        from openpyxl import Workbook
        from pptx import Presentation
        from pptx.util import Inches
        from PIL import Image
        import pymupdf

        libro = Workbook()
        libro.active['A1'] = 'Decisión concedida'
        libro.save(self.base / 'fallo.xlsx')
        libro.close()
        presentacion = Presentation()
        diapositiva = presentacion.slides.add_slide(presentacion.slide_layouts[6])
        diapositiva.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = 'Decisión concedida'
        presentacion.save(self.base / 'fallo.pptx')
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((50, 50), 'Decision concedida')
            pdf.save(self.base / 'fallo.pdf')
        Image.new('RGB', (200, 100), 'white').save(self.base / 'fallo.png')
        for extension in ('.xlsx', '.pptx', '.pdf', '.png'):
            with self.subTest(extension=extension):
                ruta = self.base / ('fallo' + extension)
                antes = ruta.read_bytes()
                with patch('analisis.reconocer', return_value=('Decisión concedida', [])):
                    self.assertTrue(self.lector.cargar(ruta))
                self.assertIn('concedida', self.lector.texto.get('1.0', 'end-1c'))
                self.assertEqual(ruta.read_bytes(), antes)

    def test_filtro_incluye_todos_los_formatos_y_rechaza_incompatibles(self):
        self.assertEqual(set(filtros_documentos()[0][1]), {'*' + ext for ext in FORMATOS})
        with patch('lector_fallo.messagebox.showerror') as aviso, patch('lector_fallo.extraer') as leer:
            self.assertFalse(self.lector.cargar(self.base / 'archivo.zip'))
        aviso.assert_called_once()
        leer.assert_not_called()
