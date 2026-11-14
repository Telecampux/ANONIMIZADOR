import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock

from selector_archivos import SelectorArchivos


class SeleccionArchivos(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.carpeta = tempfile.TemporaryDirectory()
        self.base = Path(self.carpeta.name)
        for nombre in ('uno.txt', 'dos.pdf', 'tres.docx', 'ignorar.zip'):
            (self.base / nombre).touch()
        (self.base / 'subcarpeta.txt').mkdir()
        self.cargar = Mock()
        self.vista = SelectorArchivos(self.root, self.base, self.cargar)
        self.root.update()

    def tearDown(self):
        self.root.destroy()
        self.carpeta.cleanup()

    def test_elegir_uno_o_varios_carga_solo_los_elegidos(self):
        self.assertEqual(len(self.vista.archivos), 3)
        self.assertEqual(str(self.vista.boton_cargar.cget('state')), 'disabled')
        self.vista.lista.selection_set(0)
        self.vista.actualizar()
        self.assertEqual(len(self.vista.lista.curselection()), 1)
        self.vista.lista.selection_set(2)
        self.vista.actualizar()
        elegidos = [self.vista.archivos[i] for i in (0, 2)]
        self.vista.boton_cargar.invoke()
        self.cargar.assert_called_once_with(elegidos)

    def test_seleccionar_todos_y_quitar_seleccion(self):
        self.vista.seleccionar_todos()
        self.assertEqual(self.vista.lista.curselection(), (0, 1, 2))
        self.vista.quitar_seleccion()
        self.assertEqual(self.vista.lista.curselection(), ())
        self.assertEqual(str(self.vista.boton_cargar.cget('state')), 'disabled')
        self.vista.seleccionar_todos()
        elegidos = list(self.vista.archivos)
        self.vista.aceptar()
        self.cargar.assert_called_once_with(elegidos)

    def test_cancelar_no_carga_documentos(self):
        self.vista.seleccionar_todos()
        self.vista.destroy()
        self.cargar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
