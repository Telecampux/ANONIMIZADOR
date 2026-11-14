"""Integración local con documentos sintéticos Office 97–2003."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from analisis import extraer
from office_antiguo import convertir_antiguo
from reversible import Caso, exportar
from vista_previa import CopiasPreparadas


class OfficeAntiguo(unittest.TestCase):
    def test_lectura_y_exportacion_real_de_los_tres_formatos(self):
        import pythoncom
        from win32com.client import DispatchEx
        pythoncom.CoInitialize()
        try:
            with tempfile.TemporaryDirectory() as carpeta:
                base = Path(carpeta)
                for extension, programa in (('.doc', 'Word.Application'),
                                            ('.xls', 'Excel.Application'),
                                            ('.ppt', 'PowerPoint.Application')):
                    with self.subTest(extension=extension):
                        ruta = base / ('entrada' + extension)
                        app = DispatchEx(programa)
                        documento = None
                        try:
                            app.AutomationSecurity = 3
                            if extension == '.doc':
                                app.Visible = False
                                documento = app.Documents.Add()
                                documento.Content.Text = 'Ana Perez obtiene la tutela'
                                documento.SaveAs2(str(ruta), FileFormat=0)
                            elif extension == '.xls':
                                app.Visible = False
                                app.DisplayAlerts = False
                                documento = app.Workbooks.Add()
                                documento.Worksheets(1).Cells(1, 1).Value = 'Ana Perez obtiene la tutela'
                                documento.SaveAs(str(ruta), FileFormat=56)
                            else:
                                documento = app.Presentations.Add(WithWindow=False)
                                diapositiva = documento.Slides.Add(1, 12)
                                diapositiva.Shapes.AddTextbox(1, 20, 20, 400, 100).TextFrame.TextRange.Text = 'Ana Perez obtiene la tutela'
                                documento.SaveAs(str(ruta), FileFormat=1)
                        finally:
                            if documento is not None:
                                documento.Close()
                            app.Quit()
                        antes = ruta.read_bytes()
                        self.assertIn('Ana Perez', extraer(ruta))
                        with patch.dict('os.environ', {'LOCALAPPDATA': str(base)}):
                            caso = Caso(nombre='Caso sintético')
                        caso.registrar([('Nombres', 'Ana Perez')], archivo=ruta)
                        salida = base / ('anonimo' + extension + '.docx')
                        exportar(ruta, salida, caso, ['Ana Perez'])
                        texto = extraer(salida)
                        self.assertNotIn('Ana Perez', texto)
                        self.assertIn('obtiene la tutela', texto)
                        self.assertEqual(caso.restaurar_texto(texto)[0].strip(), 'Ana Perez obtiene la tutela')
                        copias = CopiasPreparadas()
                        try:
                            copia, _ = copias.obtener(ruta, [], ['Ana Perez'])
                            self.assertIn(copia.suffix, {'.docx', '.xlsx', '.pptx'})
                            self.assertNotIn('Ana Perez', extraer(copia))
                        finally:
                            copias.cerrar()
                        self.assertEqual(ruta.read_bytes(), antes)
                        with convertir_antiguo(ruta) as temporal:
                            self.assertTrue(temporal.exists())
                        self.assertFalse(temporal.exists())
        finally:
            pythoncom.CoUninitialize()

    def test_error_cierra_su_instancia_sin_modificar_original(self):
        aplicacion = Mock()
        aplicacion.Documents.Open.side_effect = RuntimeError('Error sintético')
        with patch('win32com.client.DispatchEx', return_value=aplicacion):
            with self.assertRaisesRegex(ValueError, 'original se conserva'):
                with convertir_antiguo(Path('ausente.doc')):
                    self.fail('No debe continuar')
        aplicacion.Quit.assert_called_once()
