import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document
from reversible import Caso, exportar, restaurar_archivo
from vista_previa import CopiasPreparadas
from app import Anonimizador


class Reversible(unittest.TestCase):
    def test_volver_anonimizar_actualiza_la_misma_copia(self):
        original = self.base / 'original.txt'
        destino = self.base / 'publico'
        destino.mkdir()
        anterior = destino / 'anonimizado_123456abcdef.docx'
        original.write_text('Ana Perez y ana@example.com', encoding='utf-8')
        exportar(original, anterior, self.caso, ['Ana Perez'])
        self.caso.registrar_copia(anterior, anterior, origen=original)
        contenido_anterior = anterior.read_bytes()
        app = Anonimizador()
        try:
            app.asignar_caso(self.caso)
            app.cargar_archivos([original])
            app.lista.selection_set(0)
            app.cambiar_archivo()
            self.assertTrue(app.anonimizacion_bloqueada(original))
            app.boton_reanonimizar.invoke()
            self.assertFalse(app.anonimizacion_bloqueada(original))
            self.assertEqual(str(app.boton_analizar.cget('state')), 'normal')
            self.assertTrue(app.archivo_anonimizado(original))
            app.trabajar([original], destino, {original: ([], ['Ana Perez', 'ana@example.com'])})
            app.after_cancel(app._poll)
            with patch('app.messagebox.showinfo'):
                app.recibir()
            self.assertTrue(app.anonimizacion_bloqueada(original))
            self.assertNotEqual(anterior.read_bytes(), contenido_anterior)
            nuevas = [p for p in destino.glob('*.docx') if p != anterior]
            self.assertEqual(len(nuevas), 0)
            texto = '\n'.join(p.text for p in Document(anterior).paragraphs)
            self.assertNotIn('Ana Perez', texto)
            self.assertNotIn('ana@example.com', texto)
            self.assertEqual(original.read_text(encoding='utf-8'), 'Ana Perez y ana@example.com')
            self.assertEqual(Caso(self.caso.ruta).estado_archivo(original), 'Anonimizado')
        finally:
            app.destroy()

    def test_error_al_reemplazar_conserva_copia_y_registro(self):
        original = self.base / 'original.txt'
        salida = self.base / 'copia.txt'
        temporal = self.base / 'temporal.txt'
        original.write_text('Original sintetico', encoding='utf-8')
        salida.write_text('Copia anterior', encoding='utf-8')
        temporal.write_text('Copia nueva', encoding='utf-8')
        self.caso.registrar_copia(salida, salida, origen=original)
        tabla = self.caso.ruta.read_bytes()
        reemplazar = Path.replace
        def simular_archivo_abierto(ruta, destino):
            if ruta == temporal:
                raise PermissionError('Archivo abierto')
            return reemplazar(ruta, destino)
        with patch.object(Path, 'replace', simular_archivo_abierto):
            with self.assertRaises(PermissionError):
                self.caso.publicar_copia(temporal, salida, original, reemplazar=True)
        self.assertEqual(salida.read_text(encoding='utf-8'), 'Copia anterior')
        self.assertEqual(self.caso.ruta.read_bytes(), tabla)
        self.assertEqual(self.caso.estado_archivo(original), 'Anonimizado')

    def test_restaurar_abre_carpeta_anonima_y_guarda_en_demanda(self):
        fuente = self.base / 'publico' / 'fallo.txt'
        fuente.parent.mkdir()
        codigo = next(iter(self.caso.datos['equivalencias']))
        fuente.write_text('Fallo de ' + codigo, encoding='utf-8')
        carpeta_demanda = self.base / 'demanda'
        carpeta_demanda.mkdir()
        salida = carpeta_demanda / 'fallo_restaurado.txt'
        app = Anonimizador()
        try:
            app.asignar_caso(self.caso)
            with patch('app.CARPETA_ORIGEN', carpeta_demanda), \
                    patch('app.filedialog.askopenfilename', return_value=str(fuente)) as abrir, \
                    patch('app.filedialog.asksaveasfilename', return_value=str(salida)) as guardar, \
                    patch('app.messagebox.showinfo'), patch('app.messagebox.showerror') as error:
                app.restaurar_fallo()
            self.assertEqual(abrir.call_args.kwargs['initialdir'], str(fuente.parent))
            self.assertEqual(guardar.call_args.kwargs['initialdir'], str(carpeta_demanda))
            self.assertEqual(guardar.call_args.kwargs['initialfile'], 'fallo_restaurado.txt')
            self.assertEqual(salida.read_text(encoding='utf-8'), 'Fallo de Ana Perez')
            self.assertEqual(fuente.read_text(encoding='utf-8'), 'Fallo de ' + codigo)
            error.assert_not_called()
        finally:
            app.destroy()

    def test_recupera_pdf_antiguo_con_texto_y_ocr_entre_paginas(self):
        import pymupdf
        original = self.base / 'original.pdf'
        salida = self.base / 'anonimizado_123456abcdef.docx'
        with pymupdf.open() as pdf:
            for numero in range(2):
                pagina = pdf.new_page()
                pagina.insert_textbox(pymupdf.Rect(40, 40, 550, 700),
                    f'Pagina {numero + 1}. Ana Perez. ' + 'Contenido sintetico de prueba. ' * 12)
            pdf.save(original)
        self.caso.registrar([('Nombres', 'Ana Perez')], archivo=original)
        doc = Document()
        with pymupdf.open(original) as pdf:
            for pagina in pdf:
                texto, _ = self.caso.sustituir(pagina.get_text(), ['Ana Perez'])
                doc.add_paragraph(texto)
                doc.add_paragraph('Lectura OCR adicional variable entre ejecuciones.')
        doc.save(salida)
        self.caso.registrar_copia(salida, salida)
        with patch('analisis.extraer', side_effect=AssertionError('No repetir OCR')):
            self.caso.recuperar_estados_archivos([original])
        self.assertEqual(self.caso.estado_archivo(original), 'Anonimizado')

    def test_recupera_estado_de_copia_anterior_sin_confundir_anexos(self):
        original = self.base / 'original.txt'
        anexo = self.base / 'anexo.txt'
        salida = self.base / 'anonimizado_123456abcdef.docx'
        original.write_text('Solicitud de Ana Perez sobre salud.', encoding='utf-8')
        anexo.write_text('Anexo diferente de Ana Perez.', encoding='utf-8')
        self.caso.registrar([('Nombres', 'Ana Perez')], archivo=original)
        self.caso.registrar([('Nombres', 'Ana Perez')], archivo=anexo)
        exportar(original, salida, self.caso, ['Ana Perez'])
        self.caso.registrar_copia(salida, salida)
        caso = Caso(self.caso.ruta)
        caso.recuperar_estados_archivos([original, anexo])
        self.assertEqual(caso.estado_archivo(original), 'Anonimizado')
        self.assertEqual(caso.estado_archivo(anexo), 'No anonimizado')
        self.assertEqual(caso.estado_archivo(salida), 'Anonimizado')
        self.assertEqual(Caso(caso.ruta).estado_archivo(original), 'Anonimizado')

    def test_estado_por_archivo_al_reabrir_caso(self):
        original = self.base / 'original.txt'
        pendiente = self.base / 'pendiente.txt'
        salida = self.base / 'anonimizado.txt'
        preparada = self.base / 'preparada.txt'
        original.write_text('Persona de Ejemplo', encoding='utf-8')
        pendiente.write_text('Otro documento', encoding='utf-8')
        preparada.write_text('[PERSONA_EJEMPLO]', encoding='utf-8')
        self.caso.registrar_archivos([original, pendiente])
        self.caso.registrar_copia(salida, preparada, origen=original)
        self.assertEqual(self.caso.estado_archivo(original), 'No anonimizado')
        preparada.rename(salida)
        caso = Caso(self.caso.ruta)
        self.assertEqual(caso.estado_archivo(original), 'Anonimizado')
        self.assertEqual(caso.estado_archivo(pendiente), 'No anonimizado')
        app = Anonimizador()
        try:
            def abrir():
                def recorrer(widget):
                    yield widget
                    for hijo in widget.winfo_children():
                        yield from recorrer(hijo)
                widgets = list(recorrer(app))
                lista = next(w for w in widgets if w.winfo_class() == 'Treeview' and 'nombre' in w['columns'])
                lista.selection_set(lista.get_children()[0])
                next(w for w in widgets if w.winfo_class() == 'TButton' and w.cget('text') == 'Abrir caso').invoke()
            app.after(100, abrir)
            app.abrir_caso()
            self.assertEqual(app.archivos, [original, pendiente])
            self.assertEqual([c.cget('text') for _, c in app.lista.filas],
                             ['[Anonimizado] original.txt', '[No anonimizado] pendiente.txt'])
            app.lista.selection_set(0)
            app.cambiar_archivo()
            self.assertEqual(str(app.boton_analizar.cget('state')), 'disabled')
            self.assertEqual(str(app.boton_vista.cget('state')), 'disabled')
            with patch('app.threading.Thread') as hilo, patch('app.Comparador') as comparar, patch('app.messagebox.showinfo'):
                app.iniciar_archivo()
                app.previsualizar()
                self.assertFalse(app.iniciar(planes={original: ([], ['Persona de Ejemplo'])}))
                hilo.assert_not_called()
                comparar.assert_not_called()
            app.lista.selection_set(1)
            app.cambiar_archivo()
            self.assertEqual(str(app.boton_analizar.cget('state')), 'normal')
        finally:
            app.destroy()
        original.write_text('Contenido nuevo', encoding='utf-8')
        self.assertEqual(caso.estado_archivo(original), 'No anonimizado')
        original.write_text('Persona de Ejemplo', encoding='utf-8')
        salida.unlink()
        self.assertEqual(caso.estado_archivo(original), 'No anonimizado')

    def test_estado_exige_copia_exportada_y_se_conserva_al_reabrir(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with patch.dict(os.environ, {'LOCALAPPDATA': carpeta}):
                caso = Caso(nombre='Caso de prueba')
                self.assertEqual(caso.estado_anonimizacion, 'Sin copia anonimizada disponible')
                caso.registrar([('Nombres', 'Persona de Ejemplo')])
                self.assertEqual(caso.estado_anonimizacion, 'Sin copia anonimizada disponible')
                preparada = Path(carpeta) / 'preparada.txt'
                preparada.write_text('[PERSONA_EJEMPLO]', encoding='utf-8')
                salida = Path(carpeta) / 'salida.txt'
                caso.registrar_copia(salida, preparada)
                self.assertEqual(caso.estado_anonimizacion, 'Sin copia anonimizada disponible')
                preparada.rename(salida)
                reabierto = Caso(caso.ruta)
                self.assertEqual(reabierto.estado_anonimizacion, 'Anonimizado · copia guardada')
                salida.write_text('Contenido cambiado', encoding='utf-8')
                self.assertEqual(reabierto.estado_anonimizacion, 'Sin copia anonimizada disponible')
                salida.unlink()
                self.assertEqual(reabierto.estado_anonimizacion, 'Sin copia anonimizada disponible')

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.base = Path(self.temporal.name)
        self.entorno = patch.dict(os.environ, {'LOCALAPPDATA': str(self.base / 'privado')})
        self.entorno.start()
        self.destino_prueba = patch('app.CARPETA_DESTINO', self.base / 'publico')
        self.destino_prueba.start()
        self.caso = Caso()
        self.caso.registrar([('Nombres', 'Ana Perez'), ('Correos electrónicos', 'ana@example.com')])

    def tearDown(self):
        self.destino_prueba.stop()
        self.entorno.stop()
        self.temporal.cleanup()

    def test_nombre_persistente_y_compatibilidad_con_casos_antiguos(self):
        caso = Caso(nombre='  Tutela de prueba  ')
        caso.registrar([('Nombres', 'Ana Perez')])
        reabierto = Caso(caso.ruta)
        self.assertEqual(reabierto.nombre, 'Tutela de prueba')
        self.assertEqual(reabierto.fecha, caso.fecha)
        codigo = next(iter(caso.datos['equivalencias']))
        self.assertEqual(reabierto.restaurar_texto(codigo)[0], 'Ana Perez')
        del caso.datos['nombre']
        del caso.datos['creado']
        caso.guardar()
        antiguo = Caso(caso.ruta)
        self.assertEqual(antiguo.nombre, 'Caso sin nombre')
        self.assertTrue(antiguo.fecha)
        self.assertEqual(antiguo.restaurar_texto(codigo)[0], 'Ana Perez')

    def test_cancelar_nuevo_caso_conserva_el_actual(self):
        app = Anonimizador()
        try:
            app.asignar_caso(self.caso)
            with patch('app.simpledialog.askstring', return_value=None):
                app.nuevo_caso()
            self.assertIs(app.caso, self.caso)
        finally:
            app.destroy()

    def test_lista_abre_caso_por_nombre_y_fecha(self):
        caso = Caso(nombre='Tutela sintética')
        app = Anonimizador()
        try:
            def seleccionar():
                def recorrer(widget):
                    yield widget
                    for hijo in widget.winfo_children():
                        yield from recorrer(hijo)
                widgets = list(recorrer(app))
                lista = next(w for w in widgets if w.winfo_class() == 'Treeview' and 'nombre' in w['columns'])
                fila = next(f for f in lista.get_children() if lista.item(f, 'values')[0] == caso.nombre)
                self.assertEqual(lista.item(fila, 'values')[1], caso.fecha)
                self.assertEqual(lista.item(fila, 'values')[2], 'Sin copia anonimizada disponible')
                lista.selection_set(fila)
                next(w for w in widgets if w.winfo_class() == 'TButton' and w.cget('text') == 'Abrir caso').invoke()
            app.after(100, seleccionar)
            app.abrir_caso()
            self.assertEqual(app.caso.ruta, caso.ruta)
            self.assertEqual(str(app.boton_cargar.cget('state')), 'normal')
            self.assertEqual(app.nombre_caso.get(), 'Caso: Tutela sintética · Sin copia anonimizada disponible')
        finally:
            app.destroy()

    def test_eliminar_desde_lista_cancelar_error_y_caso_activo(self):
        original = self.base / 'original.txt'
        original.write_text('Contenido sintético', encoding='utf-8')
        app = Anonimizador()
        errores = []
        try:
            app.asignar_caso(self.caso)
            otra = Caso(nombre='Conservar')
            def comprobar():
                ventana = next(w for w in app.winfo_children() if w.winfo_class() == 'Toplevel')
                try:
                    def recorrer(widget):
                        yield widget
                        for hijo in widget.winfo_children():
                            yield from recorrer(hijo)
                    widgets = list(recorrer(ventana))
                    lista = next(w for w in widgets if w.winfo_class() == 'Treeview')
                    fila = next(f for f in lista.get_children() if lista.item(f, 'values')[0] == self.caso.nombre)
                    lista.selection_set(fila)
                    boton = next(w for w in widgets if w.winfo_class() == 'TButton' and w.cget('text') == 'Eliminar caso')
                    with patch('app.messagebox.askyesno', return_value=False):
                        boton.invoke()
                    self.assertTrue(self.caso.ruta.exists())
                    self.assertIs(app.caso, self.caso)
                    with patch('app.messagebox.askyesno', return_value=True), patch('app.Path.unlink', side_effect=PermissionError), patch('app.messagebox.showerror') as aviso:
                        boton.invoke()
                        aviso.assert_called_once()
                    self.assertTrue(lista.exists(fila))
                    self.assertIs(app.caso, self.caso)
                    with patch('app.messagebox.askyesno', return_value=True):
                        boton.invoke()
                    self.assertFalse(self.caso.ruta.exists())
                    self.assertFalse(lista.exists(fila))
                    self.assertIsNone(app.caso)
                    self.assertEqual(str(app.boton_cargar.cget('state')), 'disabled')
                    self.assertEqual(app.archivos, [])
                    self.assertIsNone(app.preparadas.caso)
                    self.assertTrue(otra.ruta.exists())
                    self.assertEqual(original.read_text(encoding='utf-8'), 'Contenido sintético')
                except Exception as exc:
                    errores.append(exc)
                finally:
                    ventana.destroy()
            app.after(100, comprobar)
            app.abrir_caso()
            if errores:
                raise errores[0]
        finally:
            app.destroy()

    def test_carga_requiere_crear_o_abrir_caso(self):
        app = Anonimizador()
        try:
            self.assertEqual(str(app.boton_cargar.cget('state')), 'disabled')
            with patch('app.filedialog.askopenfilenames') as elegir, patch('app.filedialog.askdirectory') as carpeta:
                app.boton_cargar.invoke()
                app.elegir_archivos()
                app.elegir_origen()
                app.cargar_archivos([self.base / 'entrada.txt'])
                app.cargar()
                elegir.assert_not_called()
                carpeta.assert_not_called()
                self.assertEqual(app.archivos, [])
            with patch('app.simpledialog.askstring', return_value=None):
                app.nuevo_caso()
            self.assertEqual(str(app.boton_cargar.cget('state')), 'disabled')
            with patch('app.simpledialog.askstring', return_value='Tutela sintética'):
                app.nuevo_caso()
            self.assertEqual(str(app.boton_cargar.cget('state')), 'normal')
            with patch('app.filedialog.askopenfilenames', return_value=(str(self.base / 'entrada.txt'),)):
                app.boton_cargar.invoke()
            self.assertEqual(app.archivos, [self.base / 'entrada.txt'])
        finally:
            app.destroy()

    def test_ver_archivos_guardados_permite_word_y_cancelar(self):
        app = Anonimizador()
        try:
            app.destino.set(str(self.base))
            copia = self.base / 'anonimizado_001.docx'
            with patch('app.filedialog.askopenfilename', return_value=str(copia)) as elegir, patch('app.os.startfile') as abrir:
                app.abrir_destino()
                self.assertEqual(elegir.call_args.kwargs['initialdir'], str(self.base.resolve()))
                from formatos_documentos import filtros_documentos
                self.assertEqual(elegir.call_args.kwargs['filetypes'], filtros_documentos())
                abrir.assert_called_once_with(str(copia.resolve()))
            with patch('app.filedialog.askopenfilename', return_value=''), patch('app.os.startfile') as abrir:
                app.abrir_destino()
                abrir.assert_not_called()
            with patch('app.filedialog.askopenfilename', return_value=str(copia)), patch('app.os.startfile', side_effect=OSError), patch('app.messagebox.showerror') as aviso:
                app.abrir_destino()
                aviso.assert_called_once()
        finally:
            app.destroy()

    def test_ver_tabla_muestra_equivalencias_del_caso(self):
        Caso(nombre='Otro caso vacío')
        app = Anonimizador()
        errores = []
        try:
            app.asignar_caso(self.caso)
            def comprobar():
                ventana = next(w for w in app.winfo_children() if w.winfo_class() == 'Toplevel')
                try:
                    def recorrer(widget):
                        yield widget
                        for hijo in widget.winfo_children():
                            yield from recorrer(hijo)
                    widgets = list(recorrer(ventana))
                    tabla = next(w for w in widgets if w.winfo_class() == 'Treeview')
                    selector = next(w for w in widgets if w.winfo_class() == 'TCombobox')
                    filas = {tabla.item(f, 'values')[0]: tabla.item(f, 'values')[1] for f in tabla.get_children()}
                    self.assertTrue(all('Sin registro de archivo' in tabla.item(f, 'values')[2] for f in tabla.get_children()))
                    self.assertEqual(filas, self.caso.datos['equivalencias'])
                    self.assertEqual(len(selector['values']), 2)
                    otro_indice = 1 - selector.current()
                    selector.current(otro_indice)
                    selector.event_generate('<<ComboboxSelected>>')
                    ventana.update()
                    self.assertEqual(len(tabla.get_children()), 0)
                    self.assertIs(app.caso, self.caso)
                except Exception as exc:
                    errores.append(exc)
                finally:
                    ventana.destroy()
            app.after(100, comprobar)
            with patch('app.os.startfile') as abrir:
                app.ver_caso()
                abrir.assert_not_called()
            if errores:
                raise errores[0]
        finally:
            app.destroy()

    def test_archivos_por_dato_persisten_sin_duplicar_codigos(self):
        demanda = self.base / 'demanda.txt'
        anexo = self.base / 'anexo.txt'
        self.caso.registrar([('Nombres', 'Ana Perez')], archivo=demanda)
        self.caso.registrar([('Nombres', 'ANA PEREZ')], archivo=anexo)
        self.caso.registrar([('Nombres', 'Ana Perez')], archivo=demanda)
        reabierto = Caso(self.caso.ruta)
        codigo = next(k for k, v in reabierto.datos['equivalencias'].items() if v == 'Ana Perez')
        self.assertEqual(len(reabierto.datos['equivalencias']), 2)
        self.assertEqual(reabierto.datos['archivos'][codigo], [str(demanda.resolve()), str(anexo.resolve())])
        self.assertEqual(reabierto.restaurar_texto(codigo)[0], 'Ana Perez')
        correo = next(k for k, v in reabierto.datos['equivalencias'].items() if '@' in v)
        self.assertNotIn(correo, reabierto.datos['archivos'])

    def test_eliminar_copias_registradas_y_antiguas_solo_del_caso(self):
        publico = self.base / 'publico'
        publico.mkdir()
        codigo = next(iter(self.caso.datos['equivalencias']))
        registrada = publico / 'anonimizado_aaaaaaaaaaaa.docx'
        antigua = publico / 'anonimizado_bbbbbbbbbbbb.docx'
        ajena = publico / 'anonimizado_cccccccccccc.docx'
        original = publico / 'demanda.docx'
        for ruta, texto in ((registrada, codigo), (antigua, codigo), (original, codigo), (ajena, '[PERSONA_FFFFFFFFFFFF_001]')):
            doc = Document()
            doc.add_paragraph(texto)
            doc.save(ruta)
        self.caso.registrar_copia(registrada, registrada)
        reabierto = Caso(self.caso.ruta)
        copias = reabierto.copias_para_eliminar([publico])
        self.assertEqual(set(copias), {registrada.resolve(), antigua.resolve()})
        reabierto.eliminar(copias)
        self.assertFalse(registrada.exists())
        self.assertFalse(antigua.exists())
        self.assertFalse(self.caso.ruta.exists())
        self.assertTrue(ajena.exists())
        self.assertTrue(original.exists())

    def test_copia_modificada_y_error_de_borrado_conservan_tabla(self):
        copia = self.base / 'anonimizado_dddddddddddd.docx'
        copia.write_bytes(b'contenido de prueba')
        self.caso.registrar_copia(copia, copia)
        copia.write_bytes(b'contenido modificado')
        with self.assertRaises(ValueError):
            self.caso.copias_para_eliminar([])
        self.assertTrue(self.caso.ruta.exists())
        with patch('reversible.Path.unlink', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.caso.eliminar([copia])
        self.assertTrue(self.caso.ruta.exists())
        self.assertTrue(copia.exists())

    def test_mismo_codigo_en_anexos_y_reabrir_caso(self):
        entrada = self.base / 'entrada.txt'
        entrada.write_text('Ana Perez: ana@example.com. Se conserva el derecho a la salud.', encoding='utf-8')
        almacen = CopiasPreparadas(self.caso)
        try:
            salida, count = almacen.obtener(entrada, [], ['Ana Perez', 'ana@example.com'])
            texto = '\n'.join(p.text for p in Document(salida).paragraphs)
            self.assertEqual(count, 2)
            self.assertNotIn('Ana Perez', texto)
            self.assertNotIn('ana@example.com', texto)
            self.assertIn('derecho a la salud', texto)
            otra = Caso(self.caso.ruta)
            otra.registrar([('Nombres', 'ANA PEREZ')])
            self.assertEqual(len(otra.datos['equivalencias']), 2)
            restaurado, n = otra.restaurar_texto(texto)
            self.assertEqual(n, 2)
            self.assertEqual(restaurado, entrada.read_text(encoding='utf-8'))
            self.assertEqual(entrada.read_text(encoding='utf-8'), restaurado)
        finally:
            almacen.cerrar()

    def test_fallo_docx_codigos_divididos_tablas_y_encabezado(self):
        codigo = next(iter(self.caso.datos['equivalencias']))
        doc = Document()
        parrafo = doc.add_paragraph('Ordenar a ')
        parrafo.add_run(codigo[:12])
        parrafo.add_run(codigo[12:])
        doc.add_table(rows=1, cols=1).cell(0, 0).text = codigo
        doc.sections[0].header.paragraphs[0].text = codigo
        fuente = self.base / 'fallo.docx'
        salida = self.base / 'restaurado.docx'
        doc.save(fuente)
        original = fuente.read_bytes()
        self.assertEqual(restaurar_archivo(fuente, salida, self.caso), 3)
        texto = '\n'.join(p.text for p in Document(salida).paragraphs)
        self.assertEqual(texto.count('Ana Perez'), 3)
        self.assertNotIn(codigo, texto)
        self.assertEqual(fuente.read_bytes(), original)
        with self.assertRaises(ValueError):
            restaurar_archivo(fuente, salida, self.caso)

    def test_rechaza_otro_caso_y_codigos_modificados(self):
        otra = Caso()
        otra.registrar([('Nombres', 'Luis Gomez')])
        codigo = next(iter(otra.datos['equivalencias']))
        for texto in (codigo, '[PERSONA_001]', 'Sin marcadores', '[ANONIMIZADO]'):
            fuente = self.base / 'fallo.txt'
            fuente.write_text(texto, encoding='utf-8')
            salida = self.base / 'restaurado.txt'
            with self.assertRaises(ValueError):
                restaurar_archivo(fuente, salida, self.caso)
            self.assertFalse(salida.exists())

    def test_pdf_e_imagen_producen_word_con_codigos(self):
        from PIL import Image
        import pymupdf as fitz
        imagen = self.base / 'escaneo.png'
        Image.new('RGB', (400, 100), 'white').save(imagen)
        pdf = self.base / 'entrada.pdf'
        with fitz.open() as doc:
            doc.new_page().insert_text((40, 40), 'Ana Perez')
            doc.save(pdf)
        with patch('analisis.reconocer', return_value=('Ana Perez', [])):
            for fuente in (imagen, pdf):
                salida = self.base / (fuente.stem + '_codigos.docx')
                self.assertGreater(exportar(fuente, salida, self.caso, ['Ana Perez']), 0)
                texto = '\n'.join(p.text for p in Document(salida).paragraphs)
                self.assertNotIn('Ana Perez', texto)
                self.assertIn('[PERSONA_', texto)

    def test_interfaz_prepara_y_guarda_mismos_codigos(self):
        app = Anonimizador()
        try:
            fuente = self.base / 'original.txt'
            fuente.write_text('Ana Perez conserva sus derechos.', encoding='utf-8')
            app.asignar_caso(self.caso)
            app.cargar_archivos([fuente])
            app.configuraciones[fuente]['campos'] = {'Nombres propios de personas (detección en español)': ['Ana Perez']}
            app.lista.selection_set(0)
            app.cambiar_archivo()
            dato = ('Nombres propios de personas (detección en español)', 'Ana Perez')
            app.datos_variables[dato].set(True)
            with patch('app.Comparador'), patch('app.simpledialog.askstring', return_value='Tutela de prueba'):
                app.previsualizar()
            self.assertIsNotNone(app.caso)
            codigo = next(k for k, v in app.caso.datos['equivalencias'].items() if v == 'Ana Perez')
            self.assertEqual(app.caso.datos['archivos'][codigo], [str(fuente.resolve())])
            preparada, _ = app.preparadas.obtener(fuente, [], ['Ana Perez'])
            destino = self.base / 'publico'
            destino.mkdir()
            app.trabajar([fuente], destino, {fuente: ([], ['Ana Perez'])})
            guardada = next(destino.glob('anonimizado_*.docx'))
            self.assertEqual(preparada.read_bytes(), guardada.read_bytes())
            self.assertFalse(list(destino.glob('*.json')))
            reabierto = Caso(app.caso.ruta)
            self.assertIn(str(guardada.resolve()), reabierto.datos['copias'])
            restaurada = self.base / 'fallo.docx'
            restaurar_archivo(guardada, restaurada, Caso(app.caso.ruta))
            self.assertIn('Ana Perez', '\n'.join(p.text for p in Document(restaurada).paragraphs))
        finally:
            app.destroy()


if __name__ == '__main__':
    unittest.main()
