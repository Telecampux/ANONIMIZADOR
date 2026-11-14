import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

from app import Anonimizador
from motor import procesar
from vista_previa import Comparador, CopiasPreparadas, leer_comparacion, renderizar


def esperar(app, ventana):
    limite = time.monotonic() + 30
    while ventana.datos is None and time.monotonic() < limite:
        app.update()
        if ventana.estado.get().startswith('No se pudo'):
            raise AssertionError(ventana.estado.get())
        time.sleep(.01)
    if ventana.datos is None:
        raise AssertionError('La vista no terminó de cargar.')
    app.update()


class VistaPrevia(unittest.TestCase):
    @patch('app.messagebox.showinfo')
    def test_guardar_desde_boton_superior(self, aviso):
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            fuente = base / 'original.txt'
            fuente.write_text('ana@example.com; juan@example.com', encoding='utf-8')
            destino = base / 'destino'
            destino.mkdir()
            app = Anonimizador()
            try:
                app.destino.set(str(destino))
                vista = Comparador(app, fuente, [], ['ana@example.com'], app.preparadas, on_guardar=app.guardar_previsualizado)
                esperar(app, vista)
                vista.boton_guardar.invoke()
                limite = time.monotonic() + 10
                while app.vista_guardado is not None and time.monotonic() < limite:
                    app.update()
                    time.sleep(.01)
                self.assertIsNone(app.vista_guardado)
                copias = list(destino.iterdir())
                self.assertEqual(len(copias), 1)
                self.assertEqual(copias[0].read_text(encoding='utf-8'), '[ANONIMIZADO]; juan@example.com')
                self.assertEqual(vista.boton_guardar.cget('text'), '✓ Copia guardada')
                aviso.assert_called_once_with(
                    'Guardado completado',
                    'La copia anonimizada se guardó correctamente.\n\nUbicación:\n' + str(copias[0]),
                    parent=vista,
                )
                vista.destroy()
            finally:
                app.destroy()

    def test_texto_original_resultado_y_copia_identica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            fuente = base / 'entrada.txt'
            fuente.write_text('Nombre: Ana García. Correo: ana@example.com', encoding='utf-8')
            destino = base / 'copias'
            destino.mkdir()
            app = Anonimizador()
            try:
                categorias = ['Correos electrónicos']
                guardar = Mock()
                self.assertFalse(app.boton.winfo_manager())
                vista = Comparador(app, fuente, categorias, [], app.preparadas, on_guardar=guardar)
                self.assertFalse(vista.boton_guardar.winfo_manager())
                self.assertIsNotNone(vista._parpadeo)
                color = str(vista.aviso_estado.cget('background'))
                vista.after_cancel(vista._parpadeo)
                vista.parpadear_aviso()
                self.assertNotEqual(str(vista.aviso_estado.cget('background')), color)
                esperar(app, vista)
                self.assertIsNone(vista._parpadeo)
                self.assertEqual(str(vista.aviso_estado.cget('background')), '#eef2f7')
                self.assertEqual(vista.boton_guardar.winfo_manager(), 'pack')
                self.assertLess(vista.boton_guardar.winfo_rooty(), vista.textos[1].winfo_rooty())
                vista.boton_guardar.invoke()
                guardar.assert_called_once_with(vista, fuente, categorias, [])
                self.assertIn('ana@example.com', vista.textos[0].get('1.0', 'end'))
                self.assertNotIn('ana@example.com', vista.textos[1].get('1.0', 'end'))
                self.assertIn('[ANONIMIZADO]', vista.textos[1].get('1.0', 'end'))
                self.assertTrue(vista.textos[1].tag_ranges('anonimizado'))
                self.assertFalse(vista.textos[0].tag_ranges('anonimizado'))
                self.assertTrue(vista.textos[0].tag_ranges('seleccionado'))
                vista.resaltar.set(False)
                vista.actualizar_resaltado()
                self.assertFalse(vista.textos[1].tag_ranges('anonimizado'))
                vista.resaltar.set(True)
                vista.actualizar_resaltado()
                self.assertTrue(vista.textos[1].tag_ranges('anonimizado'))
                preparada, _ = app.preparadas.obtener(fuente, categorias, [])
                bytes_revisados = preparada.read_bytes()
                app.trabajar([fuente], destino, {fuente: (categorias, [])})
                copia = next(destino.iterdir())
                self.assertEqual(copia.read_bytes(), bytes_revisados)
                self.assertIn('ana@example.com', fuente.read_text(encoding='utf-8'))
                vista.destroy()
            finally:
                app.destroy()

    def test_cache_cambia_con_opciones_y_archivo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            fuente = Path(carpeta) / 'a.txt'
            fuente.write_text('Ana y Juan', encoding='utf-8')
            almacen = CopiasPreparadas()
            with patch('vista_previa.procesar', wraps=procesar) as generar:
                primera, _ = almacen.obtener(fuente, [], ['Ana'])
                repetida, _ = almacen.obtener(fuente, [], ['Ana'])
                self.assertEqual(primera, repetida)
                self.assertEqual(generar.call_count, 1)
                segunda, _ = almacen.obtener(fuente, [], ['Juan'])
                self.assertNotEqual(primera, segunda)
                fuente.write_text('Ana y Juan cambiaron el original', encoding='utf-8')
                tercera, _ = almacen.obtener(fuente, [], ['Ana'])
                self.assertNotEqual(primera, tercera)
                self.assertEqual(generar.call_count, 3)
            almacen.cerrar()

    def test_pdf_paginas_y_original_sin_campos(self):
        import pymupdf as fitz
        with tempfile.TemporaryDirectory() as carpeta:
            fuente = Path(carpeta) / 'a.pdf'
            with fitz.open() as doc:
                for i in range(2):
                    doc.new_page().insert_text((50, 60), f'Pagina {i + 1}: Ana')
                doc.save(fuente)
            app = Anonimizador()
            try:
                vista = Comparador(app, fuente, [], [], app.preparadas, on_guardar=Mock())
                esperar(app, vista)
                self.assertFalse(vista.boton_guardar.winfo_manager())
                self.assertEqual(vista.datos[0]['paginas'], 2)
                self.assertEqual(vista.datos[1]['tipo'], 'mensaje')
                vista.ir(1)
                self.assertEqual(vista.pagina, 1)
                self.assertIn('2 de 2', vista.contador.get())
                self.assertTrue(vista.imagenes)
                self.assertFalse(vista.estado.get().startswith('No se pudo'))
                self.assertEqual(renderizar(leer_comparacion(fuente), 0, 400).width, 400)
                self.assertLessEqual(vista.siguiente.winfo_rooty() - vista.winfo_rooty() + vista.siguiente.winfo_height(), vista.winfo_height())
                vista.destroy()
                vista = Comparador(app, fuente, [], ['Ana'], app.preparadas)
                esperar(app, vista)
                self.assertEqual(vista.datos[1]['tipo'], 'pdf')
                self.assertEqual(vista.datos[1]['paginas'], 2)
                self.assertTrue(vista.canvases[1].find_withtag('anonimizado'))
                self.assertFalse(vista.canvases[0].find_withtag('anonimizado'))
                self.assertTrue(vista.canvases[0].find_withtag('seleccionado'))
                vista.ir(1)
                self.assertTrue(vista.canvases[1].find_withtag('anonimizado'))
                vista.resaltar.set(False)
                vista.actualizar_resaltado()
                self.assertFalse(vista.canvases[1].find_withtag('anonimizado'))
                from PIL import ImageChops
                original = renderizar(vista.datos[0], 0, 500)
                anonimizado = renderizar(vista.datos[1], 0, 500)
                self.assertIsNotNone(ImageChops.difference(original, anonimizado).getbbox())
                self.assertFalse(vista.estado.get().startswith('No se pudo'))
                vista.destroy()
            finally:
                app.destroy()


if __name__ == '__main__':
    unittest.main()
