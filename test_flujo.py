import tempfile
import os
from reversible import Caso
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from analisis import analizar, reconocer
from motor import procesar
from app import Anonimizador
from vista_previa import plan_configuracion


class Flujo(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.entorno = patch.dict(os.environ, {'LOCALAPPDATA': self.temporal.name})
        self.entorno.start()
        self.addCleanup(self.temporal.cleanup)
        self.addCleanup(self.entorno.stop)

    def test_campos_detectados_se_muestran_directamente_sin_dialogos(self):
        app = Anonimizador()
        try:
            app.asignar_caso(Caso(nombre='Tutela sintética'))
            archivo = Path(self.temporal.name) / 'demanda.txt'
            app.cargar_archivos([archivo])
            app.lista.selection_set(0)
            app.cambiar_archivo()
            campos = {'Nombres propios de personas (detección en español)': ['Persona de Ejemplo'],
                      'Correos electrónicos': ['ejemplo@example.com'],
                      'Documentos con etiqueta CC, TI, CE o NIT': ['12345678']}
            app.analizando = True
            app.boton.configure(state='disabled')
            app.eventos.put(('analizado', app.generacion, archivo, campos, None))
            app.eventos.put(('analisis_fin', app.generacion))
            app.after_cancel(app._poll)
            with patch('app.messagebox.askyesno') as preguntar:
                app.recibir()
                app.update()
                preguntar.assert_not_called()
            self.assertEqual({w.cget('text') for w in app.casillas_datos}, {'Persona de Ejemplo', 'ejemplo@example.com', '12345678'})
            self.assertFalse(any(v.get() for v in app.datos_variables.values()))
            self.assertFalse(any(w.winfo_class() == 'Toplevel' for w in app.winfo_children()))
            app.datos_variables[('Correos electrónicos', 'ejemplo@example.com')].set(True)
            app.guardar_activo()
            with patch('app.Comparador') as comparar:
                app.boton_vista.invoke()
                comparar.assert_called_once()
                self.assertEqual(comparar.call_args.args[2:4], ([], ['ejemplo@example.com']))
        finally:
            app.destroy()

    def test_ocr_campos_y_ocultacion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            base = Path(carpeta)
            imagen = Image.new('RGB', (1200, 250), 'white')
            dibujo = ImageDraw.Draw(imagen)
            fuente = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 42)
            dibujo.text((30, 60), 'Correo: ana@example.com', fill='black', font=fuente)
            imagen.save(base / 'entrada.png')
            campos = analizar(base / 'entrada.png')
            self.assertIn('ana@example.com', campos['Correos electrónicos'])
            count = procesar(base / 'entrada.png', base / 'salida.png', ['Correos electrónicos'], [])
            self.assertGreater(count, 0)
            with Image.open(base / 'salida.png') as salida:
                self.assertNotIn('ana@example.com', reconocer(salida)[0])
                self.assertEqual(salida.getpixel((200, 90)), (0, 0, 0))
            import pymupdf as fitz
            with fitz.open() as doc:
                page = doc.new_page(width=600, height=125)
                page.insert_image(page.rect, filename=str(base / 'entrada.png'))
                doc.save(base / 'escaneado.pdf')
            self.assertIn('ana@example.com', analizar(base / 'escaneado.pdf')['Correos electrónicos'])
            self.assertGreater(procesar(base / 'escaneado.pdf', base / 'oculto.pdf', ['Correos electrónicos'], []), 0)
            self.assertFalse(analizar(base / 'oculto.pdf')['Correos electrónicos'])

    def test_cargar_solo_lista_y_analizar_archivo_elegido(self):
        app = Anonimizador()
        app.asignar_caso(Caso(nombre='Tutela sintética'))
        try:
            archivos = [Path('uno.txt'), Path('dos.txt')]
            with patch('app.threading.Thread') as hilo, patch('app.Comparador') as comparar, patch('app.procesar') as procesar:
                app.cargar_archivos(archivos)
                self.assertEqual(app.lista.size(), 2)
                self.assertEqual(app.lista.curselection(), ())
                self.assertIsNone(app.activo)
                self.assertFalse(app.analizando)
                hilo.assert_not_called()
                app.lista.filas[1][1].invoke()
                app.update()
                self.assertEqual(app.activo, archivos[1])
                hilo.assert_not_called()
                self.assertEqual(str(app.boton_analizar.cget('state')), 'normal')
                self.assertIsNotNone(app._parpadeo)
                app.lista.filas[1][1].invoke()
                app.update()
                self.assertIsNone(app.activo)
                self.assertEqual(str(app.boton_analizar.cget('state')), 'disabled')
                self.assertIsNone(app._parpadeo)
                hilo.assert_not_called()
                app.lista.filas[1][1].invoke()
                app.update()
                app.boton_analizar.invoke()
                self.assertEqual(hilo.call_args.kwargs['args'], ([archivos[1]], app.generacion))
                self.assertEqual(app.boton_analizar.cget('text'), 'Iniciar anonimización')
                self.assertEqual(app.boton_analizar.cget('style'), 'AnalizandoIntenso.TButton')
                app.after_cancel(app._parpadeo)
                app.parpadear_analisis()
                self.assertEqual(app.boton_analizar.cget('style'), 'AnalizandoClaro.TButton')
                app.eventos.put(('analizado', app.generacion, archivos[1], {}, None))
                app.eventos.put(('analisis_fin', app.generacion))
                app.after_cancel(app._poll)
                app.recibir()
                app.update_idletasks()
                self.assertIsNotNone(app._parpadeo)
                self.assertEqual(app.boton_analizar.cget('text'), 'Iniciar anonimización')
                self.assertEqual(app.boton_analizar.cget('style'), 'AnalizandoIntenso.TButton')
                comparar.assert_not_called()
                procesar.assert_not_called()
        finally:
            app.destroy()

    def test_opciones_independientes_y_pantalla(self):
        app = Anonimizador()
        app.asignar_caso(Caso(nombre='Tutela sintética'))
        try:
            a, b = Path('uno.txt'), Path('dos.txt')
            with patch('app.filedialog.askopenfilenames', return_value=(str(a), str(b))), patch('app.threading.Thread'):
                app.elegir_archivos()
            app.analizando = False
            app.boton.configure(state='normal')
            for ruta in (a, b):
                app.configuraciones[ruta]['campos'] = {'Correos electrónicos': ['ana@example.com']}
            app.lista.selection_set(0)
            app.cambiar_archivo()
            dato = ('Correos electrónicos', 'ana@example.com')
            self.assertFalse(app.datos_variables[dato].get())
            self.assertEqual(str(app.boton_vista.cget('state')), 'disabled')
            app.datos_variables[dato].set(True)
            with patch('app.Comparador') as comparar:
                app.guardar_activo()
                comparar.assert_not_called()
                self.assertEqual(str(app.boton_vista.cget('state')), 'normal')
                self.assertEqual(app.boton_analizar.winfo_manager(), '')
                self.assertIsNone(app._parpadeo)
                app.boton.configure(state='normal')
                app.boton_vista.invoke()
                comparar.assert_called_once()
                self.assertEqual(comparar.call_args.args[2:4], ([], ['ana@example.com']))
            app.lista.selection_clear(0, 'end')
            app.lista.selection_set(1)
            app.cambiar_archivo()
            self.assertFalse(app.datos_variables[dato].get())
            self.assertEqual(app.boton_analizar.winfo_manager(), 'grid')
            app.lista.selection_clear(0, 'end')
            app.lista.selection_set(0)
            app.cambiar_archivo()
            self.assertTrue(app.datos_variables[dato].get())
            self.assertEqual(app.boton_analizar.winfo_manager(), '')
            self.assertEqual(plan_configuracion(app.configuraciones[a]), ([], ['ana@example.com']))
            self.assertEqual(plan_configuracion(app.configuraciones[b]), ([], []))
            # Todos los campos con ejemplos deben caber en el área de trabajo.
            app.configuraciones[a]['campos'] = {k: [f'Dato {i}' for i in range(50)] for k in app.etiquetas}
            app.mostrar_campos()
            app.update()
            self.assertLessEqual(app.progreso.winfo_rooty() - app.winfo_rooty() + app.progreso.winfo_height(), app.winfo_height())
        finally:
            app.destroy()


if __name__ == '__main__':
    unittest.main()
