"""Interfaz local en español; los documentos nunca se suben a internet."""
import os
from pathlib import Path
import queue
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from anonimizador import analyze, apply_review, read_recovery, restore
from restauracion_campos import restore_judgment
from revision import ReviewWindow
from estilo import configurar_estilos
from estilo_casillas import configurar_casillas
from procesamiento import ProcessingCancelled, cancellation_scope, check_cancelled


ORIGINALS_FOLDER = Path(r'C:\TUTELAS\ORIGINALES')
RESTORATION_FOLDER = Path(r'C:\TUTELAS\ANONIMIZADOS')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        configurar_estilos(self)
        configurar_casillas(self)
        self.title('Anonimizador · Revisión y autorización · 2026.11.17.7')
        icon = Path(__file__).resolve().parent / 'assets' / 'anonimizador.ico'
        if icon.is_file():
            self.iconbitmap(str(icon))
        self.geometry('860x760')
        self.minsize(720, 660)
        self.state('zoomed')
        self.files = []
        self.events = queue.Queue()
        self.busy = False
        self.cancel_event = threading.Event()
        self.progress_page = None
        self.active_filename = ''
        self.restored_file = ''
        self.selected_restored = tk.StringVar()
        self.output = tk.StringVar(value=str(Path(__file__).resolve().parent.parent / 'ANONIMIZADOS'))
        self.auto = tk.BooleanVar(value=True)
        self.mode = tk.StringVar(value='anonimizar')
        self.recovery = tk.StringVar()
        self.judgment = tk.StringVar()
        self.judgment_name = tk.StringVar(value='Seleccione el archivo que desea restaurar')
        self.recovery_name = tk.StringVar(value='Ninguna tabla cargada')
        self.anonymized_source = tk.StringVar(value='Insumo anonimizado asociado: sin cargar')
        self.status = tk.StringVar(value='Seleccione archivos, analice las propuestas y autorice cuáles aplicar.')
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Anonimizador reversible', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='OCR local en español e inglés · Originales intactos · Restauración de archivos anonimizados').pack(anchor='w', pady=(3, 15))
        modes = ttk.Frame(frame)
        modes.pack(fill='x')
        for value, label in [('anonimizar', 'Anonimizar archivos'), ('fallo', 'Restaurar archivos anonimizados')]:
            ttk.Radiobutton(modes, text=label, variable=self.mode, value=value).pack(side='left', padx=(0, 24))
        ttk.Button(modes, text='Instalar nueva versión', command=self.install_new_version).pack(side='right')
        document_area = ttk.Frame(frame)
        document_area.pack(fill='x')
        self.input_frame = ttk.Frame(document_area)
        self.input_frame.pack(fill='x')
        bar = ttk.Frame(self.input_frame)
        bar.pack(fill='x', pady=(15, 5))
        ttk.Button(bar, text='Seleccionar archivos…', command=self.choose).pack(side='left')
        ttk.Button(bar, text='Limpiar selección', command=self.clear).pack(side='left', padx=8)
        self.listing = tk.Listbox(self.input_frame, height=5)
        self.listing.pack(fill='x')
        self.judgment_frame = ttk.LabelFrame(document_area, text='1. Archivo anonimizado', padding=10)
        ttk.Label(self.judgment_frame, text='Archivo anonimizado por esta aplicación cuyos datos originales desea restaurar.', wraplength=700).pack(anchor='w')
        judgment_buttons = ttk.Frame(self.judgment_frame)
        judgment_buttons.pack(fill='x')
        ttk.Button(judgment_buttons, text='Cargar archivo…', command=self.choose_judgment).pack(side='left')
        ttk.Label(self.judgment_frame, textvariable=self.judgment_name, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(5, 0))
        self.judgment_path = ttk.Entry(self.judgment_frame, textvariable=self.judgment, state='readonly')
        recovery_bar = self.recovery_bar = ttk.LabelFrame(document_area, text='Recuperación identificada automáticamente', padding=10)
        recovery_bar.pack(fill='x', pady=5)
        ttk.Label(recovery_bar, text='La aplicación identifica los datos originales al cargar el archivo anonimizado.', wraplength=700).pack(anchor='w')
        recovery_buttons = ttk.Frame(recovery_bar)
        recovery_buttons.pack(fill='x', pady=4)
        ttk.Label(recovery_bar, textvariable=self.recovery_name, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        self.recovery_path = ttk.Entry(recovery_bar, textvariable=self.recovery, state='readonly')
        self.recovery_path.pack(fill='x', pady=3)
        ttk.Label(recovery_bar, textvariable=self.anonymized_source, wraplength=700).pack(anchor='w')
        self.recovery_info = tk.StringVar(value='Cargue la tabla .restauracion del caso para ver sus campos.')
        ttk.Label(recovery_bar, textvariable=self.recovery_info, wraplength=700).pack(anchor='w')
        fields_frame = ttk.Frame(recovery_bar)
        fields_frame.pack(fill='x', pady=(5, 0))
        self.recovery_fields = ttk.Treeview(fields_frame, columns=('code', 'value'), show='headings', height=4)
        self.recovery_fields.heading('code', text='Campo anonimizado')
        self.recovery_fields.heading('value', text='Dato original que se restaurará')
        self.recovery_fields.column('code', width=320)
        self.recovery_fields.column('value', width=360)
        fields_scroll = ttk.Scrollbar(fields_frame, orient='vertical', command=self.recovery_fields.yview)
        self.recovery_fields.configure(yscrollcommand=fields_scroll.set)
        fields_scroll.pack(side='right', fill='y')
        self.recovery_fields.pack(fill='x', expand=True)
        self.manual_frame = ttk.Frame(frame)
        self.manual_frame.pack(fill='x')
        ttk.Label(self.manual_frame, text='Nombres de personas o identificaciones adicionales: uno por línea.').pack(anchor='w', pady=(14, 4))
        self.manual = tk.Text(self.manual_frame, height=5, wrap='word', font=('Segoe UI', 10))
        self.manual.pack(fill='x')
        ttk.Checkbutton(self.manual_frame, text='Detectar solo nombres propios de personas e identificaciones',
                        variable=self.auto, command=self.actualizar_aviso_deteccion).pack(anchor='w', pady=6)
        self.aviso_deteccion = tk.StringVar()
        ttk.Label(self.manual_frame, textvariable=self.aviso_deteccion, foreground='#9a3412',
                  wraplength=790).pack(anchor='w')
        self.manual.bind('<KeyRelease>', self.actualizar_aviso_deteccion)
        self.actualizar_aviso_deteccion()
        grid = self.output_grid = ttk.Frame(frame)
        grid.pack(fill='x', pady=8)
        grid.columnconfigure(1, weight=1)
        ttk.Label(grid, text='Carpeta de salida').grid(row=0, column=0, sticky='w', padx=(0, 12), pady=4)
        ttk.Entry(grid, textvariable=self.output).grid(row=0, column=1, sticky='ew', pady=4)
        ttk.Button(grid, text='Elegir…', command=self.choose_output).grid(row=0, column=2, padx=(8, 0))
        self.mode_hint = tk.StringVar()
        ttk.Label(frame, textvariable=self.mode_hint, wraplength=790, foreground='#794500').pack(anchor='w', pady=8)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=5)
        self.run_button = ttk.Button(actions, text='Anonimizar', command=self.run, style='Proceso.TButton')
        self.run_button.pack(side='left')
        self.cancel_button = ttk.Button(actions, text='Cancelar anonimización', command=self.cancel_processing, state='disabled')
        self.cancel_button.pack(side='left', padx=8)
        self.folder_button = ttk.Button(actions, text='Abrir carpeta anonimizados', command=self.open_output)
        self.folder_button.pack(side='left', padx=8)
        self.activity = ttk.Progressbar(actions, mode='indeterminate', length=150,
                                        style='Proceso.Horizontal.TProgressbar')
        self.activity.pack(side='right', padx=8)
        ttk.Label(frame, textvariable=self.status, wraplength=790).pack(anchor='w', pady=6)
        results = self.results_frame = ttk.LabelFrame(frame, text='2. Archivo restaurado', padding=10)
        self.result_name = tk.StringVar(value='')
        ttk.Label(results, textvariable=self.result_name, wraplength=700).pack(anchor='w', pady=(0, 5))
        result_actions = ttk.Frame(results)
        result_actions.pack(fill='x')
        self.open_result_button = ttk.Button(result_actions, text='Abrir', command=self.open_restored, state='disabled')
        self.open_result_button.pack(side='left', padx=8)
        self.download_result_button = ttk.Button(result_actions, text='Descargar como…', command=self.download_restored, state='disabled')
        self.download_result_button.pack(side='left')
        self.selected_restored.trace_add('write', self.update_result_controls)
        self.log = tk.Text(frame, height=6, state='disabled', wrap='word')
        self.log.tag_configure('pagina', font=('Segoe UI', 11, 'bold'))
        self.log.pack(fill='both', expand=True)
        self.mode.trace_add('write', self.update_mode)
        self.update_mode()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(150, self.poll)

    def actualizar_aviso_deteccion(self, event=None):
        if self.auto.get():
            self.aviso_deteccion.set('')
        elif self.manual.get('1.0', 'end').strip():
            self.aviso_deteccion.set('Al desactivar esta opción, no se anonimizan nombres ni identificaciones automáticamente. Solo se anonimizan los datos que haya incluido manualmente en el campo de arriba.')
        else:
            self.aviso_deteccion.set('Al desactivar esta opción, no se anonimizan nombres ni identificaciones automáticamente. Solo se anonimizan los datos que incluya manualmente en el campo de arriba. Si lo deja en blanco, no se anonimiza nada.')

    def update_result_controls(self, *_):
        selected = self.selected_restored.get()
        self.result_name.set(Path(selected).name if selected else '')
        if selected and Path(selected).is_file() and self.mode.get() == 'fallo':
            self.results_frame.pack(fill='x', pady=5)
        else:
            self.results_frame.pack_forget()
        state = 'normal' if selected and Path(selected).is_file() else 'disabled'
        self.open_result_button.config(state=state)
        self.download_result_button.config(state=state)

    def restored_selection(self):
        path = Path(self.selected_restored.get()) if self.selected_restored.get() else None
        if path is None or not path.is_file():
            messagebox.showinfo('Archivo restaurado', 'Seleccione primero un archivo restaurado.')
            return None
        return path

    def open_restored(self):
        path = self.restored_selection()
        if path is not None:
            try:
                os.startfile(str(path.resolve()))
            except OSError as exc:
                messagebox.showerror('Abrir archivo', str(exc))

    def download_restored(self):
        path = self.restored_selection()
        if path is None:
            return
        if self.busy:
            return
        from conversion import FORMATS
        formats = sorted(FORMATS, key=lambda item: item[1] != '*' + path.suffix.lower())
        if not any(pattern == '*' + path.suffix.lower() for _, pattern in formats):
            formats.insert(0, ('Formato original', '*' + path.suffix))
        destination = filedialog.asksaveasfilename(title='Descargar como',
            initialfile=path.name, defaultextension=path.suffix,
            filetypes=formats)
        if destination:
            target = Path(destination)
            if target.suffix.lower() != path.suffix.lower():
                self.busy = True
                self.activity.start(12)
                self.download_result_button.config(state='disabled')
                self.status.set('Convirtiendo descarga…')
                threading.Thread(target=self.convert_download, args=(path, target), daemon=True).start()
                return
            try:
                if target.resolve() != path.resolve():
                    shutil.copy2(path, destination)
                self.status.set(f'Archivo descargado: {destination}')
            except OSError as exc:
                messagebox.showerror('Descargar archivo', str(exc))

    def convert_download(self, source, destination):
        from conversion import convert_file
        try:
            convert_file(source, destination, lambda text: self.events.put(('download_progress', text)))
            self.events.put(('download_done', f'Archivo descargado: {destination}'))
        except Exception as exc:
            self.events.put(('download_error', str(exc)))

    def close(self):
        if self.busy:
            self.cancel_processing()
        else:
            self.destroy()

    def install_new_version(self):
        if self.busy:
            messagebox.showinfo('Actualización', 'Espere a que termine el proceso actual.')
            return
        launcher = Path(__file__).resolve().parent / 'Actualizar.bat'
        if not launcher.is_file():
            messagebox.showerror('Actualización', f'No se encuentra {launcher.name} en la carpeta del programa.')
            return
        try:
            os.startfile(str(launcher))
        except OSError as error:
            messagebox.showerror('Actualización', str(error))
            return
        self.destroy()

    def cancel_processing(self):
        if self.busy:
            self.cancel_event.set()
            self.cancel_button.config(state='disabled')
            self.status.set('Cancelando…')

    def clear_progress(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')
        self.progress_page = None
        self.seen_progress_findings = set()

    def show_page_progress(self, message):
        activity = re.fullmatch(r'(?:Analizando|Anonimizando|Restaurando) página (\d+) de (\d+)', message)
        if activity:
            self.page_activity = (self.active_filename, activity.group(1), message)
            self.status.set(message)
            return
        finding = re.match(r'^(?:Detectado|Anonimizando) ([A-Z_]+): (.*?) — (.+)$', message, re.DOTALL)
        if not finding:
            page = re.search(r'página (\d+)', message, re.IGNORECASE)
            if page:
                activity = getattr(self, 'page_activity', None)
                self.status.set(activity[2] if activity and activity[:2] == (self.active_filename, page.group(1))
                                else 'Analizando página ' + page.group(1))
            return
        kind, value, location = finding.groups()
        page = re.search(r'página (\d+)', location, re.IGNORECASE)
        title = 'Página ' + page.group(1) if page else 'Documento'
        key = (self.active_filename, title)
        if not hasattr(self, 'seen_progress_findings'):
            self.seen_progress_findings = set()
        item_key = (key, kind, ' '.join(value.split()).casefold())
        if item_key in self.seen_progress_findings:
            return
        self.seen_progress_findings.add(item_key)
        self.log.config(state='normal')
        if key != self.progress_page:
            self.log.insert('end', ('\n' if self.progress_page else '') + title + '\n', 'pagina')
            self.progress_page = key
        label = 'Identificación' if kind in {'DOCUMENTO', 'IDENTIFICACION'} else 'Nombre' if kind in {'PERSONA', 'NOMBRE_FORMULARIO', 'PROFESIONAL'} else 'Nombre o identificación'
        self.log.insert('end', f"{label}: {' '.join(value.split())}\n")
        self.log.see('end')
        self.log.config(state='disabled')
        activity = getattr(self, 'page_activity', None)
        self.status.set(activity[2] if page and activity and activity[:2] == (self.active_filename, page.group(1)) else title)

    def update_mode(self, *_):
        mode = self.mode.get()
        self.input_frame.pack_forget()
        self.judgment_frame.pack_forget()
        self.recovery_bar.pack_forget()
        self.manual_frame.pack_forget()
        if mode == 'fallo':
            self.output_grid.pack_forget()
            self.folder_button.pack_forget()
            self.log.pack_forget()
            self.update_result_controls()
            self.judgment_frame.pack(fill='x', pady=(12, 5))
            self.run_button.config(text='Restaurar archivo', state='normal' if self.judgment.get() and self.recovery.get() else 'disabled')
            self.mode_hint.set('Cargue el archivo y pulse «Restaurar archivo». Se guarda en C:\\TUTELAS\\ANONIMIZADOS.')
        else:
            self.results_frame.pack_forget()
            self.folder_button.pack(side='left', padx=8)
            self.log.pack(fill='both', expand=True)
            self.input_frame.pack(fill='x')
            self.manual_frame.pack(fill='x')
            self.output_grid.pack(fill='x', pady=8, after=self.manual_frame)
            self.run_button.config(text='Anonimizar', state='normal')
            self.mode_hint.set('La copia .restauracion contiene los datos originales sin cifrar. Comparta solo el archivo anonimizado.')

    def choose(self):
        if self.busy:
            return
        if self.mode.get() == 'fallo':
            self.choose_judgment()
            return
        files = filedialog.askopenfilenames(title='Seleccione los archivos originales para anonimizar', initialdir=str(ORIGINALS_FOLDER))
        for file in files:
            if file not in self.files:
                self.files.append(file)
                self.listing.insert('end', file)

    def choose_judgment(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='Cargar archivo anonimizado',
            initialdir=self.judgment_initial_folder(),
            filetypes=[('Todos los archivos del caso', '*'),
                       ('Archivo Word, PDF o texto', ('*.docx', '*.pdf', '*.txt', '*.md', '*.log', '*.rst'))])
        if path:
            self.selected_restored.set('')
            self.judgment.set(path)
            self.judgment_name.set(Path(path).name)
            self.reset_recovery()
            if '_restaurado_' in Path(path).stem.lower():
                self.selected_restored.set(path)
                self.status.set('Este archivo ya está restaurado. Puede abrirlo o descargarlo.')
            else:
                self.detect_recovery(path)

    def detect_recovery(self, path):
        document = Path(path)
        self.reset_recovery()
        candidates = [Path(str(document) + '.restauracion')]
        for folder in (RESTORATION_FOLDER, Path(__file__).resolve().parent / 'salida'):
            candidate = folder / (document.name + '.restauracion')
            if candidate not in candidates:
                candidates.append(candidate)
        for candidate in candidates:
            if candidate.is_file():
                self.load_recovery(candidate)
                return
        self.status.set('No se encontró la recuperación automática de este archivo. Conserve el archivo .restauracion generado al anonimizar junto al documento.')

    def judgment_initial_folder(self):
        cases = Path(__file__).resolve().parent.parent / 'ANONIMIZADOS'
        candidates = [cases]
        if self.judgment.get():
            candidates.append(Path(self.judgment.get()).parent)
        candidates.extend((Path(self.output.get()), Path.cwd()))
        return str(next(path for path in candidates if path.is_dir()))

    def open_judgment(self):
        path = Path(self.judgment.get()) if self.judgment.get() else None
        if path is None or not path.is_file():
            messagebox.showinfo('Ver documento', 'Primero cargue el fallo desde ANONIMIZADOS.')
            return
        try:
            os.startfile(str(path.resolve()))
        except OSError as exc:
            messagebox.showerror('Ver documento', f'No se pudo abrir el archivo: {exc}')

    def reset_recovery(self):
        self.recovery.set('')
        if self.mode.get() == 'fallo':
            self.run_button.config(state='disabled')
        self.recovery_name.set('Ninguna tabla cargada')
        self.recovery_info.set('La recuperación se identifica automáticamente al cargar un archivo.')
        self.anonymized_source.set('Insumo anonimizado asociado: sin cargar')
        self.recovery_fields.delete(*self.recovery_fields.get_children())

    def clear(self):
        if not self.busy:
            self.files.clear()
            self.listing.delete(0, 'end')

    def choose_recovery(self):
        if self.busy:
            return
        if not self.judgment.get():
            self.mode.set('fallo')
            self.choose_judgment()
            if not self.judgment.get():
                return
            if self.recovery.get():
                return
        path = filedialog.askopenfilename(title='Cargue la tabla .restauracion o el insumo anonimizado que la acompaña',
            initialdir=str(Path(self.judgment.get()).parent),
            filetypes=[('Todos los archivos del caso', '*'),
                       ('Tabla de correspondencias', '*.restauracion'),
                       ('Tabla e insumos anonimizados', ('*.restauracion', '*.pdf', '*.docx', '*.txt', '*.md', '*.log', '*.rst'))])
        if path:
            self.load_recovery(path)

    def load_recovery(self, path):
        self.reset_recovery()
        path = Path(path)
        recovery_path = path if path.suffix.lower() == '.restauracion' else Path(str(path) + '.restauracion')
        try:
            body, _ = read_recovery(recovery_path)
        except Exception as exc:
            messagebox.showerror('Recuperación no válida', str(exc))
            return
        self.recovery.set(str(recovery_path))
        if self.mode.get() == 'fallo':
            self.run_button.config(state='normal', text='Restaurar archivo')
        self.recovery_name.set(recovery_path.name)
        associated = Path(str(recovery_path)[:-len('.restauracion')])
        self.anonymized_source.set(f'Insumo anonimizado asociado: {associated}' + ('' if associated.is_file() else ' (no está en esta carpeta)'))
        self.recovery_fields.delete(*self.recovery_fields.get_children())
        for code, value in sorted(body['fields'].items()):
            self.recovery_fields.insert('', 'end', values=(code, value))
        self.recovery_info.set(f"Insumo de origen: {body['name']} · {len(body['fields'])} campos guardados.")
        self.status.set('Archivo listo para restaurar.')

    def show_fields(self):
        if not self.recovery.get():
            messagebox.showinfo('Campos', 'Elija primero una copia .restauracion.')
            return
        try:
            body, _ = read_recovery(self.recovery.get())
            fields = body.get('fields', {})
            if not fields:
                raise ValueError('Esta copia no contiene campos guardados. Vuelva a anonimizar el original con esta versión para crearlos.')
        except Exception as exc:
            messagebox.showerror('Campos', str(exc))
            return
        window = tk.Toplevel(self)
        window.title('Campos para redactar y restaurar el fallo')
        window.geometry('820x440')
        ttk.Label(window, text='Consulta de campos del caso. Los códigos que ya aparezcan en el fallo se restaurarán automáticamente; no necesita copiarlos ni seleccionarlos aquí.', wraplength=780).pack(padx=15, pady=10)
        table = ttk.Treeview(window, columns=('code', 'value'), show='headings', selectmode='browse')
        table.heading('code', text='Código para el fallo')
        table.heading('value', text='Dato original')
        table.column('code', width=280)
        table.column('value', width=450)
        scroll = ttk.Scrollbar(window, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        table.pack(fill='both', expand=True, padx=15)
        for code, value in sorted(fields.items()):
            table.insert('', 'end', values=(code, value))
        def copy_code():
            if table.selection():
                code = table.item(table.selection()[0], 'values')[0]
                self.clipboard_clear()
                self.clipboard_append(code)
        ttk.Button(window, text='Copiar código seleccionado', command=copy_code).pack(pady=10)

    def choose_output(self):
        value = filedialog.askdirectory()
        if value:
            self.output.set(value)

    def open_output(self):
        path = RESTORATION_FOLDER if self.mode.get() == 'fallo' else Path(self.output.get())
        if path.is_dir():
            os.startfile(path)
        else:
            messagebox.showinfo('Salida', 'La carpeta se creará al procesar archivos.')

    def run(self):
        if self.busy:
            return
        mode = self.mode.get()
        files = [self.judgment.get()] if mode == 'fallo' and self.judgment.get() else ([] if mode == 'fallo' else list(self.files))
        if not files:
            messagebox.showerror('Falta el fallo' if mode == 'fallo' else 'Falta selección',
                                 'Primero pulse «Cargar archivo…» y seleccione el fallo del sustanciador.' if mode == 'fallo' else 'Seleccione al menos un archivo.')
            return
        if mode == 'fallo' and not self.recovery.get():
            self.detect_recovery(self.judgment.get())
            if self.recovery.get():
                return self.run()
            messagebox.showerror('No se encontró la recuperación', 'No se encontró el archivo .restauracion asociado. Debe conservarse junto al archivo anonimizado o en C:\\TUTELAS\\ANONIMIZADOS.')
            return
        if mode != 'fallo' and not self.output.get().strip():
            messagebox.showerror('Carpeta', 'Seleccione una carpeta de salida.')
            return
        output = str(RESTORATION_FOLDER) if mode == 'fallo' else self.output.get()
        manual, automatic = self.manual.get('1.0', 'end').splitlines(), self.auto.get()
        self.busy = True
        self.restored_file = ''
        self.cancel_event.clear()
        self.clear_progress()
        self.cancel_button.config(state='normal', text='Cancelar anonimización' if mode == 'anonimizar' else 'Cancelar restauración')
        self.run_button.config(state='disabled', text='Procesando…')
        self.activity.start(12)
        self.status.set('Analizando… No se guardará nada hasta que autorice las propuestas.' if mode == 'anonimizar' else 'Restaurando archivo original…' if mode == 'fallo' else 'Restaurando…')
        threading.Thread(target=self.work, args=(mode, files, output, manual, automatic, self.recovery.get()), daemon=True).start()

    def report_progress(self, message):
        check_cancelled()
        self.events.put(('progress', message))

    def work(self, mode, files, output, manual, automatic, recovery=''):
        try:
            with cancellation_scope(getattr(self, 'cancel_event', None)):
                App._work(self, mode, files, output, manual, automatic, recovery)
        except ProcessingCancelled:
            self.events.put(('done', 'Proceso cancelado.'))
        except Exception as exc:
            self.events.put(('error', str(exc)))
            self.events.put(('done', 'No se pudo completar el proceso.'))

    def _work(self, mode, files, output, manual, automatic, recovery=''):
        success, plans = 0, []
        for index, file in enumerate(files, 1):
            check_cancelled()
            self.events.put(('file', Path(file).name))
            self.report_progress(f'Archivo {index}/{len(files)}: {Path(file).name}')
            try:
                if mode == 'anonimizar':
                    plan = analyze(file, manual, automatic, self.report_progress)
                    plans.append(plan)
                    message = f'{Path(file).name}: {len(plan.findings)} propuestas; {plan.ocr_pages} imágenes/páginas con OCR. Pendiente de su autorización.'
                elif mode == 'fallo':
                    restored = restore(recovery, output)
                    self.events.put(('restored', restored))
                    message = f'{Path(file).name}: archivo original restaurado automáticamente.\nArchivo generado: {restored}'
                else:
                    raise ValueError('Seleccione «Anonimizar archivos» o «Restaurar archivos anonimizados».')
                success += 1
            except ProcessingCancelled:
                raise
            except Exception as exc:
                message = f'{Path(file).name}: ERROR — {exc}'
                self.events.put(('error', message))
            if mode != 'anonimizar' or 'ERROR —' in message:
                self.events.put(('log', message))
        check_cancelled()
        if plans:
            self.events.put(('review', (plans, output)))
        else:
            self.events.put(('done', 'Proceso terminado' if success == len(files) else 'Revise los errores.'))

    def save_approved(self, selections, output):
        self.busy = True
        self.restored_file = ''
        self.cancel_event.clear()
        self.clear_progress()
        self.cancel_button.config(state='normal', text='Cancelar anonimización')
        self.run_button.config(state='disabled', text='Procesando…')
        self.activity.start(12)
        self.status.set('Aplicando únicamente las propuestas autorizadas…')
        threading.Thread(target=self.save_work, args=(selections, output), daemon=True).start()

    def save_work(self, selections, output):
        try:
            with cancellation_scope(self.cancel_event):
                App._save_work(self, selections, output)
        except ProcessingCancelled:
            self.events.put(('done', 'Anonimización cancelada.'))

    def _save_work(self, selections, output):
        success = 0
        for plan, ids in selections:
            check_cancelled()
            self.events.put(('file', plan.path.name))
            try:
                result = apply_review(plan, ids, output, self.report_progress)
                zones = sum(plan.findings[identity]['kind'] == 'ZONA' for identity in ids)
                self.events.put(('log', f'Guardado: {result["output"]}\nZonas de firma aplicadas: {zones}'))
                message = None
                success += 1
            except ProcessingCancelled:
                raise
            except Exception as exc:
                message = f'{plan.path.name}: ERROR — {exc}'
            if message:
                self.events.put(('log', message))
        self.events.put(('done', 'Proceso terminado' if success == len(selections) else 'Revise los errores.'))

    def poll(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == 'file':
                    self.active_filename = message
                    self.progress_page = None
                elif kind in {'download_done', 'download_error', 'download_progress'}:
                    if kind == 'download_progress':
                        self.status.set(message)
                    else:
                        self.busy = False
                        self.activity.stop()
                        self.update_result_controls()
                        self.status.set(message if kind == 'download_done' else 'No se pudo convertir la descarga.')
                        if kind == 'download_error':
                            messagebox.showerror('Error al convertir la descarga', message)
                elif kind == 'log':
                    self.log.config(state='normal')
                    self.log.insert('end', message + '\n\n')
                    self.log.see('end')
                    self.log.config(state='disabled')
                elif kind == 'progress':
                    if not self.cancel_event.is_set():
                        self.show_page_progress(message)
                elif kind == 'error':
                    self.busy = False
                    self.activity.stop()
                    self.cancel_button.config(state='disabled')
                    self.run_button.config(state='normal', text='Restaurar archivo' if self.mode.get() == 'fallo' else 'Anonimizar')
                    self.status.set('No se pudo completar el proceso.')
                    messagebox.showerror('Error al procesar el archivo', message)
                elif kind == 'restored':
                    self.restored_file = message
                    self.selected_restored.set(message)
                elif kind == 'review':
                    self.busy = False
                    self.activity.stop()
                    self.run_button.config(state='normal', text='Anonimizar')
                    self.cancel_button.config(state='disabled')
                    if self.cancel_event.is_set():
                        self.status.set('Anonimización cancelada.')
                        continue
                    plans, output = message
                    self.status.set('Revise las propuestas y autorice las que desea aplicar. No se han generado archivos.')
                    ReviewWindow(self, plans, lambda selections: self.save_approved(selections, output))
                else:
                    self.busy = False
                    self.activity.stop()
                    label = 'Restaurar archivo' if self.mode.get() == 'fallo' else 'Anonimizar'
                    self.run_button.config(state='normal', text='Proceso terminado' if message == 'Proceso terminado' else label)
                    self.cancel_button.config(state='disabled')
                    self.status.set(message)
                    if self.restored_file:
                        restored = self.restored_file
                        self.restored_file = ''
                        self.status.set('Proceso terminado. Puede abrir o descargar el archivo restaurado.')
                        self.update_idletasks()
                        try:
                            os.startfile(str(Path(restored).resolve()))
                        except OSError as exc:
                            messagebox.showinfo('Archivo restaurado', f'Archivo guardado en: {restored}\nNo se pudo abrir automáticamente: {exc}')
        except queue.Empty:
            pass
        self.after(150, self.poll)


if __name__ == '__main__':
    App().mainloop()
