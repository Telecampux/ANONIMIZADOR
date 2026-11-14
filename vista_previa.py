"""Comparación del original con el mismo archivo que se guardará."""
import queue
import threading
import tempfile
import uuid
import re
import difflib
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from motor import IMAGENES, PATRONES, procesar, coincidencias
from office_antiguo import FORMATOS_ANTIGUOS


def plan_configuracion(config):
    if 'seleccionados' in config:
        # Ninguna regla global: solo los valores que el usuario marcó uno a uno.
        return [], sorted({valor for categoria, valor in config['seleccionados']})
    categorias = list(config.get('categorias', []))
    terminos = [t.strip() for t in config.get('terminos', '').splitlines() if t.strip()]
    for categoria in categorias:
        terminos.extend(config.get('campos', {}).get(categoria, []))
    return ([c for c in categorias if PATRONES[c] is not None], sorted(set(terminos)))


class CopiasPreparadas:
    def __init__(self, caso=None):
        self.caso = caso
        self.temporal = tempfile.TemporaryDirectory(prefix='anonimizador-vista-')
        self.copias = {}
        self.marcas = {}
        self.lock = threading.Lock()
        self.cerrado = False

    def cerrar(self):
        def limpiar():
            with self.lock:
                self.cerrado = True
                self.copias.clear()
                self.marcas.clear()
                self.temporal.cleanup()
        if self.lock.locked():
            threading.Thread(target=limpiar, daemon=True).start()
        else:
            limpiar()

    def obtener(self, ruta, categorias, terminos):
        ruta = Path(ruta)
        estado = ruta.stat()
        firma = (str(ruta.resolve()), estado.st_size, estado.st_mtime_ns,
                 tuple(sorted(categorias)), tuple(sorted(set(terminos))))
        with self.lock:
            if self.cerrado:
                raise ValueError('La aplicación se cerró.')
            if firma in self.copias:
                return self.copias[firma]
            extension = '.docx' if self.caso else '.png' if ruta.suffix.lower() in IMAGENES else FORMATOS_ANTIGUOS.get(ruta.suffix.lower(), ruta.suffix.lower())
            salida = Path(self.temporal.name) / (uuid.uuid4().hex + extension)
            try:
                marcas = []
                if self.caso:
                    from reversible import exportar
                    count = exportar(ruta, salida, self.caso, terminos)
                else:
                    count = procesar(ruta, salida, categorias, terminos, marcas=marcas)
                final = ruta.stat()
                if (final.st_size, final.st_mtime_ns) != (estado.st_size, estado.st_mtime_ns):
                    raise ValueError('El archivo original cambió durante la preparación. Vuelve a cargarlo.')
            except Exception:
                salida.unlink(missing_ok=True)
                raise
            self.copias[firma] = (salida, count)
            self.marcas[str(salida)] = marcas
            return salida, count

    def marcas_de(self, ruta):
        with self.lock:
            return list(self.marcas.get(str(ruta), []))


def leer_comparacion(ruta):
    """Datos de lectura sin widgets; no ejecuta Office ni abre enlaces."""
    if ruta.suffix.lower() == '.pdf':
        import pymupdf as fitz
        with fitz.open(ruta) as doc:
            if doc.needs_pass:
                raise ValueError('PDF protegido con contraseña.')
            return {'tipo': 'pdf', 'ruta': ruta, 'paginas': len(doc)}
    if ruta.suffix.lower() in IMAGENES:
        return {'tipo': 'imagen', 'ruta': ruta, 'paginas': 1}
    from analisis import extraer
    return {'tipo': 'texto', 'texto': extraer(ruta), 'paginas': 1}


def renderizar(datos, pagina, ancho):
    from PIL import Image, ImageOps
    if datos['tipo'] == 'pdf':
        import pymupdf as fitz
        with fitz.open(datos['ruta']) as doc:
            page = doc[min(pagina, len(doc) - 1)]
            escala = ancho / max(1, page.rect.width)
            pix = page.get_pixmap(matrix=fitz.Matrix(escala, escala), alpha=False)
            return Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    with Image.open(datos['ruta']) as original:
        imagen = ImageOps.exif_transpose(original).convert('RGB')
    alto = max(1, round(imagen.height * ancho / imagen.width))
    return imagen.resize((ancho, alto), Image.Resampling.LANCZOS)


class Comparador(tk.Toplevel):
    def __init__(self, parent, ruta, categorias, terminos, almacen, on_guardar=None):
        super().__init__(parent)
        self.title('Original y anonimizado — ' + ruta.name)
        self.state('zoomed')
        self.minsize(760, 500)
        self.ruta = ruta
        self.categorias_elegidas = list(categorias)
        self.terminos_elegidos = list(terminos)
        self.on_guardar = on_guardar
        self.cola = queue.Queue()
        self.datos = None
        self.pagina = 0
        self.zoom = 1.0
        self.imagenes = []
        self.render_pendiente = None
        self._parpadeo = None
        self._fase_aviso = False
        root = ttk.Frame(self, padding=12)
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        cabecera = ttk.Frame(root)
        cabecera.grid(row=0, column=0, sticky='ew')
        ttk.Label(cabecera, text=ruta.name, font=('Segoe UI', 13, 'bold')).pack(side='left')
        ttk.Button(cabecera, text='Volver a los campos', command=self.destroy).pack(side='right')
        self.boton_guardar = tk.Button(cabecera, text='✓ Crear copia anonimizada',
                                      command=self.guardar, background='#087f6d', foreground='white',
                                      activebackground='#065f52', activeforeground='white',
                                      font=('Segoe UI', 12, 'bold'), padx=18, pady=9, relief='flat', cursor='hand2')
        self.boton_abrir = ttk.Button(cabecera, text='Abrir copia guardada')
        self.confirmacion_guardado = tk.Label(
            cabecera, text='✓ COPIA GUARDADA', background='#ffffff', foreground='#000000',
            font=('Segoe UI', 14, 'bold'), padx=16, pady=10,
            relief='solid', borderwidth=1,
        )
        self.estado = tk.StringVar(value='Anonimizando los campos seleccionados… Espera el resultado antes de guardar.')
        self.aviso_estado = ttk.Label(root, textvariable=self.estado, wraplength=1100)
        self.aviso_estado.grid(row=1, column=0, sticky='ew', pady=6)
        self.aviso_estado.bind('<Configure>', lambda evento: self.aviso_estado.configure(wraplength=max(1, evento.width - 24)))
        columnas = ttk.Frame(root)
        columnas.grid(row=2, column=0, sticky='nsew')
        columnas.columnconfigure(0, weight=1, uniform='vista')
        columnas.columnconfigure(1, weight=1, uniform='vista')
        columnas.rowconfigure(0, weight=1)
        self.paneles, self.canvases, self.textos = [], [], []
        for columna, titulo in enumerate(('ORIGINAL — datos visibles y resaltados', 'ANONIMIZADO — resultado que se guardará')):
            panel = ttk.LabelFrame(columnas, text=titulo, padding=5)
            panel.grid(row=0, column=columna, sticky='nsew', padx=(0, 6) if columna == 0 else (6, 0))
            panel.rowconfigure(0, weight=1)
            panel.columnconfigure(0, weight=1)
            canvas = tk.Canvas(panel, bg='#dce2e9', highlightthickness=0)
            canvas.grid(row=0, column=0, sticky='nsew')
            vertical = ttk.Scrollbar(panel, orient='vertical', command=self.desplazar_y)
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal = ttk.Scrollbar(panel, orient='horizontal', command=canvas.xview)
            horizontal.grid(row=1, column=0, sticky='ew')
            canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            texto = tk.Text(panel, wrap='word', font=('Segoe UI', 11), state='disabled')
            texto.configure(yscrollcommand=vertical.set)
            canvas.bind('<MouseWheel>', self.rueda)
            texto.bind('<MouseWheel>', self.rueda)
            self.paneles.append(panel)
            self.canvases.append(canvas)
            self.textos.append(texto)
        controles = ttk.Frame(root)
        controles.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        self.anterior = ttk.Button(controles, text='← Página anterior', command=lambda: self.ir(-1), state='disabled')
        self.anterior.pack(side='left')
        self.contador = tk.StringVar(value='')
        ttk.Label(controles, textvariable=self.contador).pack(side='left', padx=12)
        self.siguiente = ttk.Button(controles, text='Página siguiente →', command=lambda: self.ir(1), state='disabled')
        self.siguiente.pack(side='left')
        self.resaltar = tk.BooleanVar(value=True)
        ttk.Checkbutton(controles, text='Resaltar campos', variable=self.resaltar, command=self.actualizar_resaltado).pack(side='left', padx=12)
        ttk.Button(controles, text='−', command=lambda: self.ampliar(1 / 1.25)).pack(side='right')
        ttk.Button(controles, text='+', command=lambda: self.ampliar(1.25)).pack(side='right')
        ttk.Button(controles, text='Ajustar al ancho', command=self.ajustar).pack(side='right', padx=8)
        self.bind('<Configure>', self.programar_render)
        self.parpadear_aviso()
        self._poll = self.after(100, self.recibir)
        threading.Thread(target=self.preparar, args=(categorias, terminos, almacen), daemon=True).start()

    def destroy(self):
        for nombre in ('_poll', 'render_pendiente', '_parpadeo'):
            evento = getattr(self, nombre, None)
            if evento:
                self.after_cancel(evento)
                setattr(self, nombre, None)
        super().destroy()
        # Libera objetos Tk en el hilo de la interfaz, nunca al terminar un trabajador.
        self.imagenes.clear()
        self.estado = None
        self.contador = None
        self.resaltar = None

    def parpadear_aviso(self):
        self._parpadeo = None
        self._fase_aviso = not self._fase_aviso
        self.aviso_estado.configure(background='#facc15' if self._fase_aviso else '#fff3c4',
                                    foreground='#713f12', font=('Segoe UI', 12, 'bold'), padding=(10, 8))
        self._parpadeo = self.after(650, self.parpadear_aviso)

    def detener_aviso(self):
        if self._parpadeo is not None:
            self.after_cancel(self._parpadeo)
            self._parpadeo = None
        self.aviso_estado.configure(background='#eef2f7', foreground='#111827', font=('Segoe UI', 10), padding=0)

    def preparar(self, categorias, terminos, almacen):
        try:
            if not categorias and not terminos:
                self.cola.put(('listo', leer_comparacion(self.ruta),
                               {'tipo': 'mensaje', 'paginas': 1, 'texto': 'Vuelve a los campos y marca qué datos quieres ocultar. Después abre otra vez esta comparación.'}, None))
                return
            salida, count = almacen.obtener(self.ruta, categorias, terminos)
            anonimizado = leer_comparacion(salida)
            anonimizado['marcas'] = almacen.marcas_de(salida)
            if almacen.caso:
                from analisis import extraer
                original = {'tipo': 'texto', 'texto': extraer(self.ruta), 'paginas': 1}
            else:
                original = leer_comparacion(self.ruta)
            self.cola.put(('listo', original, anonimizado, count))
        except Exception as exc:
            self.cola.put(('error', str(exc)))

    def guardar(self):
        if self.on_guardar:
            self.on_guardar(self, self.ruta, list(self.categorias_elegidas), list(self.terminos_elegidos))

    def mostrar_guardado(self, ruta):
        self.detener_aviso()
        self.boton_guardar.configure(text='✓ Copia guardada', state='disabled',
                                     background='#ffffff', foreground='#000000', disabledforeground='#000000')
        self.boton_guardar.pack_forget()
        self.confirmacion_guardado.pack(side='right', padx=8)
        self.estado.set('✓ COPIA GUARDADA CORRECTAMENTE\nUbicación: ' + str(ruta))
        self.aviso_estado.configure(background='#ffffff', foreground='#000000',
                                    font=('Segoe UI', 14, 'bold'), padding=(12, 10))

    def recibir(self):
        if not self.winfo_exists():
            return
        try:
            evento = self.cola.get_nowait()
        except queue.Empty:
            self._poll = self.after(100, self.recibir)
            return
        self._poll = None
        self.detener_aviso()
        if evento[0] == 'error':
            self.estado.set('No se pudo generar la vista: ' + evento[1])
            return
        self.datos = (evento[1], evento[2])
        count = evento[3]
        if count is not None and count > 0 and self.on_guardar:
            self.boton_guardar.pack(side='right', padx=16)
        self.estado.set('Vista del original. Todavía no elegiste datos para ocultar.' if count is None else
                        f'{count} coincidencias ocultadas. Revisa todas las páginas antes de guardar.' if count else
                        'Sin coincidencias ocultadas. Revisa los campos: este resultado puede conservar datos personales.')
        if self.datos[0]['tipo'] == 'texto':
            self.estado.set(self.estado.get() + ' Vista de texto: muestra el contenido del archivo, sin reproducir su diseño de Office.')
            for i, datos in enumerate(self.datos):
                self.canvases[i].grid_remove()
                self.textos[i].grid(row=0, column=0, sticky='nsew')
                self.textos[i].configure(state='normal')
                self.textos[i].insert('1.0', datos['texto'])
                self.textos[i].configure(state='disabled')
            self.contador.set('Contenido completo')
            self.actualizar_resaltado()
        else:
            self.dibujar()

    def actualizar_resaltado(self):
        if not self.datos:
            return
        if self.datos[0]['tipo'] != 'texto':
            self.dibujar()
            return
        texto = self.textos[1]
        original_widget = self.textos[0]
        original_widget.tag_configure('seleccionado', background='#fef08a', foreground='#713f12')
        original_widget.tag_remove('seleccionado', '1.0', 'end')
        texto.tag_configure('anonimizado', background='#fde047', foreground='#713f12', font=('Segoe UI', 11, 'bold'))
        texto.tag_remove('anonimizado', '1.0', 'end')
        if not self.resaltar.get() or self.datos[1]['tipo'] == 'mensaje':
            return
        original, salida = self.datos[0]['texto'], self.datos[1]['texto']
        for inicio, fin in coincidencias(original, self.categorias_elegidas, self.terminos_elegidos):
            original_widget.tag_add('seleccionado', f'1.0+{inicio}c', f'1.0+{fin}c')
        cambios = [(b0, b1) for tipo, a0, a1, b0, b1 in difflib.SequenceMatcher(None, original, salida, autojunk=False).get_opcodes() if tipo in ('insert', 'replace')]
        for match in re.finditer(r'\[(?:ANONIMIZADO|(?:PERSONA|CEDULA|CORREO|DATO)_[A-F0-9]{12}_\d+)\]', salida):
            if any(inicio < match.end() and fin > match.start() for inicio, fin in cambios):
                texto.tag_add('anonimizado', f'1.0+{match.start()}c', f'1.0+{match.end()}c')

    def desplazar_y(self, *args):
        widgets = self.textos if self.datos and self.datos[0]['tipo'] == 'texto' else self.canvases
        for widget in widgets:
            widget.yview(*args)

    def rueda(self, event):
        self.desplazar_y('scroll', -int(event.delta / 120), 'units')
        return 'break'

    def programar_render(self, event):
        if event.widget != self or not self.datos or self.datos[0]['tipo'] == 'texto':
            return
        if self.render_pendiente:
            self.after_cancel(self.render_pendiente)
        self.render_pendiente = self.after(200, self.dibujar)

    def dibujar(self):
        self.render_pendiente = None
        if not self.datos or self.datos[0]['tipo'] == 'texto':
            return
        from PIL import ImageTk
        try:
            self.imagenes = []
            ancho = max(100, min(4000, int((self.canvases[0].winfo_width() - 16) * self.zoom)))
            for canvas, datos in zip(self.canvases, self.datos):
                if datos['tipo'] == 'mensaje':
                    canvas.delete('all')
                    canvas.create_text(24, 32, text=datos['texto'], anchor='nw', width=max(100, canvas.winfo_width() - 48), font=('Segoe UI', 12))
                    continue
                imagen = renderizar(datos, self.pagina, ancho)
                foto = ImageTk.PhotoImage(imagen, master=self)
                self.imagenes.append(foto)
                canvas.delete('all')
                canvas.create_image(8, 8, image=foto, anchor='nw')
                if self.resaltar.get() and self.datos[1]['tipo'] != 'mensaje':
                    for marca in self.datos[1].get('marcas', []):
                        if marca['pagina'] == self.pagina:
                            x0, y0, x1, y1 = marca['rect']
                            canvas.create_rectangle(8 + x0 * imagen.width - 2, 8 + y0 * imagen.height - 2,
                                                    8 + x1 * imagen.width + 2, 8 + y1 * imagen.height + 2,
                                                    outline='#f59e0b', width=3, tags='anonimizado' if datos is self.datos[1] else 'seleccionado')
                canvas.configure(scrollregion=canvas.bbox('all'))
            paginas = max(d['paginas'] for d in self.datos)
            self.contador.set(f'Página {self.pagina + 1} de {paginas} · {round(self.zoom * 100)} %')
            self.anterior.configure(state='normal' if self.pagina else 'disabled')
            self.siguiente.configure(state='normal' if self.pagina + 1 < paginas else 'disabled')
        except Exception as exc:
            self.estado.set('No se pudo mostrar la página: ' + str(exc))

    def ir(self, cambio):
        if self.datos:
            paginas = max(d['paginas'] for d in self.datos)
            self.pagina = max(0, min(paginas - 1, self.pagina + cambio))
            self.dibujar()
            self.desplazar_y('moveto', 0)

    def ampliar(self, factor):
        self.zoom = min(4, max(.5, self.zoom * factor))
        self.dibujar()

    def ajustar(self):
        self.zoom = 1
        self.dibujar()
