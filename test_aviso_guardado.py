import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

from vista_previa import Comparador, CopiasPreparadas


class AvisoGuardado(unittest.TestCase):
    def test_confirmacion_legible_en_ventana_estrecha(self):
        root = tk.Tk()
        almacen = CopiasPreparadas()
        try:
            with tempfile.TemporaryDirectory() as carpeta:
                original = Path(carpeta) / 'original.txt'
                original.write_text('Correo: ana@example.com', encoding='utf-8')
                vista = Comparador(root, original, [], ['ana@example.com'], almacen,
                                   on_guardar=lambda *args: None)
                limite = time.monotonic() + 10
                while vista.datos is None and time.monotonic() < limite:
                    root.update()
                    time.sleep(.01)
                self.assertIsNotNone(vista.datos)
                vista.state('normal')
                vista.geometry('760x500')
                ruta = Path(carpeta) / ('carpeta_larga_' * 8) / 'anonimizado.txt'
                vista.mostrar_guardado(ruta)
                root.update()
                self.assertIn('COPIA GUARDADA CORRECTAMENTE', vista.estado.get())
                self.assertIn(str(ruta), vista.estado.get())
                self.assertFalse(vista.boton_guardar.winfo_manager())
                self.assertTrue(vista.confirmacion_guardado.winfo_ismapped())
                self.assertEqual(str(vista.confirmacion_guardado.cget('background')), '#ffffff')
                self.assertEqual(str(vista.confirmacion_guardado.cget('foreground')), '#000000')
                self.assertEqual(str(vista.aviso_estado.cget('background')), '#ffffff')
                self.assertEqual(str(vista.aviso_estado.cget('foreground')), '#000000')
                self.assertGreater(vista.aviso_estado.winfo_height(), 50)
                self.assertLessEqual(int(vista.aviso_estado.cget('wraplength')),
                                     vista.aviso_estado.winfo_width())
                vista.destroy()
        finally:
            root.destroy()
            almacen.temporal.cleanup()


if __name__ == '__main__':
    unittest.main()
