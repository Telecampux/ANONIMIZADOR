import os
import json
import queue
import threading
import uuid
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from motor import FORMATOS, IMAGENES, PATRONES, procesar
from vista_previa import Comparador, CopiasPreparadas, plan_configuracion
from estilo import configurar_casillas
from selector_archivos import SelectorArchivos
from lista_archivos import ListaArchivos
from reversible import Caso, restaurar_archivo
from lector_fallo import LectorFallo
from formatos_documentos import filtros_documentos
from office_antiguo import FORMATOS_ANTIGUOS
from dialogo_caso import pedir_nombre_caso

CARPETA_ORIGEN = Path('C:/TUTELAS/DEMANDA')
CARPETA_DESTINO = Path('C:/TUTELAS/demanda anonima')


class Anonimizador(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Anonimizador — seleccionar y anonimizar')
        icono = Path(__file__).resolve().parent / 'anonimizador.ico'
        if icono.exists():
            self.iconbitmap(str(icono))
        # Arranca maximizada respetando el área de trabajo y la barra de tareas.
        ancho = min(1000, max(360, self.winfo_screenwidth() - 80))
        alto = min(860, max(400, self.winfo_screenheight() - 100))
        self.geometry(f'{ancho}x{alto}')
        self.minsize(760, 560)
        self.state('zoomed')
        self.configure(bg='#eef2f7')
        style = ttk.Style(self)
        style.theme_use('clam')
        configurar_casillas(self)
        style.configure('TFrame', background='#eef2f7')
        style.configure('TLabel', background='#eef2f7', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=7)
        style.configure('Accion.TButton', font=('Segoe UI', 12, 'bold'), padding=(18, 10), background='#087f6d', foreground='white')
        style.map('Accion.TButton', background=[('disabled', '#d8e2e8'), ('active', '#065f52')], foreground=[('disabled', '#64748b')])
        style.configure('Reanonimizar.TButton', font=('Segoe UI', 12, 'bold'),
                        padding=(20, 12), background='#facc15', foreground='#422006',
                        bordercolor='#a16207')
        style.map('Reanonimizar.TButton',
                  background=[('disabled', '#e2e8f0'), ('pressed', '#eab308'), ('active', '#fde047')],
                  foreground=[('disabled', '#64748b')])
        for nombre, fondo in (('AnalizandoClaro.TButton', '#fff3c4'), ('AnalizandoIntenso.TButton', '#facc15')):
            style.configure(nombre, background=fondo, foreground='#713f12', font=('Segoe UI', 10, 'bold'))
            style.map(nombre, background=[('disabled', fondo)], foreground=[('disabled', '#713f12')])
        self.origen = tk.StringVar(value=str(CARPETA_ORIGEN))
        self.destino = tk.StringVar(value=str(CARPETA_DESTINO))
        self.eventos = queue.Queue()
        self.archivos = []
        self.configuraciones = {}
        self.activo = None
        self.cambiando = False
        self.generacion = 0
        self.analizando = False
        self._parpadeo = None
        self._fase_aviso = False
        self.caso = None
        self.preparadas = CopiasPreparadas()
        self.vista_guardado = None
        self.ultima_copia = None
        root = ttk.Frame(self, padding=16)
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        cabecera = ttk.Frame(root)
        cabecera.grid(row=0, column=0, sticky='ew')
        self.nombre_caso = tk.StringVar(value='Crea o abre un caso para comenzar')
        ttk.Label(cabecera, textvariable=self.nombre_caso, font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        herramientas = ttk.Frame(cabecera)
        herramientas.pack(fill='x')
        ttk.Button(herramientas, text='Nuevo caso', command=self.nuevo_caso).pack(side='left')
        ttk.Button(herramientas, text='Abrir caso local', command=self.abrir_caso).pack(side='left', padx=4)
        ttk.Button(herramientas, text='Ver tabla local', command=self.ver_caso).pack(side='left', padx=4)
        ttk.Button(herramientas, text='Restaurar fallo', command=self.restaurar_fallo).pack(side='left', padx=4)
        ttk.Button(herramientas, text='Leer fallo restaurado', command=self.leer_fallo_restaurado).pack(side='left', padx=4)
        destino = ttk.Frame(root)
        destino.grid(row=1, column=0, sticky='ew', pady=(8, 12))
        destino.columnconfigure(1, weight=1)
        ttk.Label(destino, text='Guardar en:').grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(destino, textvariable=self.destino, state='readonly').grid(row=0, column=1, sticky='ew')
        ttk.Button(destino, text='Cambiar destino', command=self.elegir_destino).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(destino, text='Ver archivos guardados', command=self.abrir_destino).grid(row=0, column=3, padx=(8, 0))
        self.pestanas = ttk.Notebook(root)
        self.pestanas.grid(row=2, column=0, sticky='nsew')
        paneles = ttk.Frame(self.pestanas)
        self.pestanas.add(paneles, text='Anonimizar documentos')
        self.lector_fallo = LectorFallo(self.pestanas, lambda: self.destino.get())
        self.pestanas.add(self.lector_fallo, text='Leer fallo restaurado')
        paneles.columnconfigure(0, weight=1, uniform='panel')
        paneles.columnconfigure(1, weight=1, uniform='panel')
        paneles.rowconfigure(0, weight=1)
        izquierda = ttk.Frame(paneles, padding=(0, 0, 12, 0))
        izquierda.grid(row=0, column=0, sticky='nsew')
        izquierda.columnconfigure(0, weight=1)
        izquierda.rowconfigure(4, weight=1)
        ttk.Label(izquierda, text='1. Archivos', font=('Segoe UI', 13, 'bold')).grid(row=0, column=0, sticky='w')
        self.etiqueta_caso_izquierda = ttk.Label(
            izquierda, textvariable=self.nombre_caso, font=('Segoe UI', 11, 'bold'),
            foreground='#087f6d', wraplength=280)
        self.etiqueta_caso_izquierda.grid(row=2, column=0, sticky='ew', pady=(6, 0))
        acciones = ttk.Frame(izquierda)
        acciones.grid(row=1, column=0, sticky='ew', pady=6)
        self.boton_cargar = ttk.Button(acciones, text='Demanda y anexos de la tutela…', command=self.elegir_archivos, state='disabled')
        self.boton_cargar.pack(side='left')
        self.subcarpetas = tk.BooleanVar(value=False)
        self.archivo_elegido = tk.BooleanVar(value=False)
        self.conteo = tk.StringVar(value='Primero crea un nuevo caso o abre uno guardado.')
        contador = ttk.Label(izquierda, textvariable=self.conteo, wraplength=280)
        contador.grid(row=3, column=0, sticky='ew', pady=5)
        area = ttk.Frame(izquierda)
        area.grid(row=4, column=0, sticky='nsew')
        self.lista = ListaArchivos(area)
        self.lista.bind('<<ListboxSelect>>', self.cambiar_archivo)
        scroll = ttk.Scrollbar(area, orient='vertical', command=self.lista.yview)
        self.lista.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.lista.pack(side='left', fill='both', expand=True)
        formatos = ttk.Label(izquierda, wraplength=280, text='Marca la casilla delante del archivo y pulsa Iniciar cuando quieras. Después elige los datos que deseas ocultar.')
        formatos.grid(row=5, column=0, sticky='ew', pady=(6, 0))
        derecha = ttk.Frame(paneles, padding=(12, 0, 0, 0))
        derecha.grid(row=0, column=1, sticky='nsew')
        derecha.columnconfigure(0, weight=1)
        derecha.rowconfigure(2, weight=1)
        self.titulo_campos = tk.StringVar(value='2. Selecciona un archivo para ver sus campos')
        cabecera_campos = ttk.Frame(derecha)
        cabecera_campos.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        cabecera_campos.columnconfigure(0, weight=1)
        titulo_campos = ttk.Label(cabecera_campos, textvariable=self.titulo_campos, font=('Segoe UI', 12, 'bold'), wraplength=120)
        titulo_campos.grid(row=0, column=0, sticky='w')
        self.boton_analizar = ttk.Button(cabecera_campos, text='Iniciar anonimización', command=self.iniciar_archivo, state='disabled')
        self.boton_analizar.grid(row=0, column=1, sticky='e', padx=(8, 0))
        self.boton_vista = ttk.Button(cabecera_campos, text='3. Anonimizar campos seleccionados', command=self.anonimizar_campos, style='Accion.TButton', state='disabled')
        self.boton_vista.grid(row=1, column=0, columnspan=2, sticky='e', pady=(8, 0))
        self.boton_reanonimizar = ttk.Button(cabecera_campos, text='Volver a anonimizar', style='Reanonimizar.TButton', command=self.volver_anonimizar)
        self.boton_reanonimizar.grid(row=2, column=0, columnspan=2, sticky='e', pady=(8, 0))
        self.boton_reanonimizar.grid_remove()
        cabecera_campos.bind('<Configure>', lambda e: titulo_campos.configure(wraplength=max(80, e.width - self.boton_analizar.winfo_reqwidth() - 8)))
        self.datos_variables = {}
        self.casillas_datos = []
        self.etiquetas = {
            'Nombres propios de personas (detección en español)': 'Nombres de personas',
            'Correos electrónicos': 'Correos electrónicos',
            'Documentos con etiqueta CC, TI, CE o NIT': 'Identificaciones'}
        self.resumen_campos = tk.StringVar(value='Los campos detectados aparecerán aquí al cargar los archivos.')
        nota = ttk.Label(derecha, textvariable=self.resumen_campos, wraplength=280)
        self.aviso_analisis = nota
        nota.grid(row=1, column=0, sticky='ew', pady=(5, 10))
        area_datos = ttk.Frame(derecha)
        area_datos.grid(row=2, column=0, sticky='nsew')
        lista_datos = ttk.Frame(area_datos)
        lista_datos.pack(fill='both', expand=True)
        self.lienzo_datos = tk.Canvas(lista_datos, bg='#eef2f7', highlightthickness=0)
        scroll_datos = ttk.Scrollbar(lista_datos, orient='vertical', command=self.lienzo_datos.yview)
        self.lienzo_datos.configure(yscrollcommand=scroll_datos.set)
        scroll_datos.pack(side='right', fill='y')
        self.lienzo_datos.pack(side='left', fill='both', expand=True)
        self.panel_datos = ttk.Frame(self.lienzo_datos)
        self.ventana_datos = self.lienzo_datos.create_window(0, 0, window=self.panel_datos, anchor='nw')
        self.panel_datos.bind('<Configure>', lambda e: self.lienzo_datos.configure(scrollregion=self.lienzo_datos.bbox('all')))
        self.lienzo_datos.bind('<Configure>', self.ajustar_datos)
        aviso = ttk.Label(derecha, wraplength=280, foreground='#7b4b14', text='Marca solo los datos que quieras ocultar. Deja desmarcadas las detecciones incorrectas. La copia para el skill es Word con códigos. En escaneos se usa OCR: revisa todo el texto antes de guardar.')
        aviso.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        # Ajusta las l?neas al ancho real de cada panel.
        def ajustar_textos(event):
            ancho = max(120, event.width - 24)
            for label in (nota, aviso):
                label.configure(wraplength=ancho)
        derecha.bind('<Configure>', ajustar_textos)
        izquierda.bind('<Configure>', lambda e: [label.configure(wraplength=max(120, e.width - 12)) for label in (contador, formatos, self.etiqueta_caso_izquierda)])
        pie = ttk.Frame(root)
        pie.grid(row=3, column=0, sticky='ew', pady=(12, 0))
        pie.columnconfigure(0, weight=1)
        self.boton = ttk.Button(pie, text='Crear copias anonimizadas', command=self.iniciar)
        self.progreso = ttk.Progressbar(pie)
        self.progreso.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.estado = tk.StringVar(value='Procesamiento local. Los originales se conservan.')
        estado_label = ttk.Label(pie, textvariable=self.estado, wraplength=600)
        estado_label.grid(row=1, column=0, columnspan=3, sticky='ew', pady=5)
        pie.bind('<Configure>', lambda e: estado_label.configure(wraplength=max(120, e.width)))
        self.cargar_destino()
        self.mostrar_campos()
        self._poll = self.after(150, self.recibir)

    def leer_fallo_restaurado(self):
        self.pestanas.select(self.lector_fallo)
        self.lector_fallo.elegir()

    def asignar_caso(self, caso):
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        # Una comparación abierta pertenece al caso con que fue preparada.
        for ventana in self.winfo_children():
            if ventana.__class__.__name__ == 'Comparador':
                ventana.destroy()
        self.preparadas.cerrar()
        self.caso = caso
        self.boton_cargar.configure(state='normal')
        self.conteo.set('Caso listo. Ya puedes cargar la demanda y sus anexos.')
        self.preparadas = CopiasPreparadas(caso)
        self.actualizar_estado_caso()
        self.estado.set('Caso guardado localmente. La tabla privada se conserva en este computador.')
        self.actualizar_accion()

    def actualizar_estado_caso(self):
        if self.caso:
            self.nombre_caso.set(f'Caso: {self.caso.nombre} · {self.caso.estado_anonimizacion}')

    def nuevo_caso(self, recargar=True):
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        nombre = pedir_nombre_caso(self)
        if nombre is None:
            return
        if not nombre.strip():
            messagebox.showinfo('Nombre del caso', 'Escribe un nombre para reconocer el caso.', parent=self)
            return
        self.asignar_caso(Caso(nombre=nombre))
        if recargar and self.archivos:
            self.cargar_archivos(list(self.archivos))

    def abrir_caso(self):
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        carpeta = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Anonimizador' / 'casos'
        ventana = tk.Toplevel(self)
        ventana.title('Abrir caso local')
        ventana.geometry('900x380')
        ventana.transient(self)
        marco = ttk.Frame(ventana, padding=16)
        marco.pack(fill='both', expand=True)
        ttk.Label(marco, text='Elige el caso que quieres continuar:').pack(anchor='w', pady=(0, 8))
        lista = ttk.Treeview(marco, columns=('nombre', 'fecha', 'estado'), show='headings', selectmode='browse')
        lista.heading('nombre', text='Nombre del caso')
        lista.heading('fecha', text='Fecha de creación')
        lista.heading('estado', text='Estado')
        lista.column('nombre', width=360)
        lista.column('fecha', width=160)
        lista.column('estado', width=280)
        lista.pack(fill='both', expand=True)
        casos = {}
        omitidos = 0
        for ruta in sorted(carpeta.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                caso = Caso(ruta)
                fila = lista.insert('', 'end', values=(caso.nombre, caso.fecha, caso.estado_anonimizacion))
                casos[fila] = caso
            except (OSError, ValueError, KeyError, TypeError):
                omitidos += 1
        aviso_vacio = ttk.Label(marco, text='No hay casos guardados disponibles.')
        if not casos:
            aviso_vacio.pack(anchor='w', pady=8)
        if omitidos:
            ttk.Label(marco, text=f'No se pudieron leer {omitidos} tablas locales.').pack(anchor='w')

        def elegir(event=None):
            seleccion = lista.selection()
            if not seleccion:
                return
            self.asignar_caso(casos[seleccion[0]])
            archivos = self.caso.datos.get('archivos_caso', [])
            if not archivos:
                archivos = list(dict.fromkeys(f for fuentes in self.caso.datos.get('archivos', {}).values() for f in fuentes))
            if archivos:
                self.cargar_archivos(archivos)
            elif self.archivos:
                self.cargar_archivos(list(self.archivos))
            ventana.destroy()

        def eliminar():
            seleccion = lista.selection()
            if not seleccion:
                messagebox.showinfo('Eliminar caso', 'Selecciona el caso que quieres eliminar.', parent=ventana)
                return
            fila = seleccion[0]
            caso = casos[fila]
            try:
                copias = caso.copias_para_eliminar([self.destino.get(), CARPETA_DESTINO])
            except (OSError, ValueError) as exc:
                messagebox.showerror('No se eliminó el caso', str(exc), parent=ventana)
                return
            if not messagebox.askyesno(
                'Eliminar caso',
                f'¿Eliminar «{caso.nombre}» ({caso.fecha})?\n\n'
                f'Se borrarán su tabla privada y {len(copias)} copias anonimizadas asociadas. '
                'Los documentos originales se conservan. Sin la tabla no podrás restaurar los códigos del caso.',
                parent=ventana, default='no',
            ):
                return
            try:
                caso.eliminar(copias)
            except OSError:
                messagebox.showerror('No se eliminó el caso', 'No se completó el borrado. La tabla se conserva; cierra los documentos abiertos y vuelve a intentarlo.', parent=ventana)
                return
            if self.caso is not None and self.caso.ruta.resolve() == caso.ruta.resolve():
                for comparador in self.winfo_children():
                    if isinstance(comparador, Comparador):
                        comparador.destroy()
                self.preparadas.cerrar()
                self.caso = None
                self.boton_cargar.configure(state='disabled')
                self.archivos = []
                self.configuraciones = {}
                self.activo = None
                self.lista.delete(0, 'end')
                self.archivo_elegido.set(False)
                self.generacion += 1
                self.mostrar_campos()
                self.conteo.set('Primero crea un nuevo caso o abre uno guardado.')
                self.preparadas = CopiasPreparadas()
                self.nombre_caso.set('Sin caso seleccionado')
                self.vista_guardado = None
                self.ultima_copia = None
            lista.delete(fila)
            del casos[fila]
            self.estado.set('Caso y copias anonimizadas eliminados. Los originales se conservan.')
            if not casos:
                aviso_vacio.pack(anchor='w', pady=8)

        botones = ttk.Frame(marco)
        botones.pack(fill='x', pady=(12, 0))
        ttk.Button(botones, text='Eliminar caso', command=eliminar).pack(side='left')
        ttk.Button(botones, text='Abrir caso', command=elegir).pack(side='right')
        ttk.Button(botones, text='Cancelar', command=ventana.destroy).pack(side='right', padx=8)
        lista.bind('<Double-1>', elegir)
        lista.bind('<Return>', elegir)
        lista.focus_set()
        ventana.grab_set()
        self.wait_window(ventana)

    def ver_caso(self):
        carpeta = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Anonimizador' / 'casos'
        casos = []
        for ruta in carpeta.glob('*.json'):
            try:
                casos.append(Caso(ruta))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        casos.sort(key=lambda caso: (bool(caso.datos['equivalencias']), caso.ruta.stat().st_mtime), reverse=True)
        if not casos:
            messagebox.showinfo('Tabla local', 'No hay tablas locales guardadas. Crea o abre un caso para comenzar.', parent=self)
            return
        indice = next((i for i, caso in enumerate(casos) if self.caso and caso.ruta.resolve() == self.caso.ruta.resolve()), 0)
        ventana = tk.Toplevel(self)
        ventana.title('Tablas locales de los casos')
        ventana.geometry('860x460')
        ventana.minsize(540, 300)
        ventana.transient(self)
        marco = ttk.Frame(ventana, padding=16)
        marco.pack(fill='both', expand=True)
        ttk.Label(marco, text='Elige el caso cuya tabla quieres consultar:', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        selector = ttk.Combobox(marco, state='readonly', values=[
            f'{caso.nombre} — {caso.fecha} — {len(caso.datos["equivalencias"])} equivalencias'
            for caso in casos
        ])
        selector.pack(fill='x', pady=(6, 0))
        selector.current(indice)
        aviso = ttk.Label(marco, text='Tabla privada: contiene los datos originales. Consérvala en este computador.', wraplength=780)
        aviso.pack(anchor='w', pady=(6, 12))
        marco.bind('<Configure>', lambda e: aviso.configure(wraplength=max(100, e.width - 32)))
        area = ttk.Frame(marco)
        area.pack(fill='both', expand=True)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        tabla = ttk.Treeview(area, columns=('codigo', 'original', 'archivos'), show='headings', selectmode='browse')
        tabla.heading('codigo', text='Código anonimizado')
        tabla.heading('original', text='Dato original')
        tabla.heading('archivos', text='Archivos donde aparece')
        tabla.column('codigo', width=300, minwidth=280)
        tabla.column('original', width=220, minwidth=180)
        tabla.column('archivos', width=340, minwidth=220)
        tabla.grid(row=0, column=0, sticky='nsew')
        vertical = ttk.Scrollbar(area, orient='vertical', command=tabla.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(area, orient='horizontal', command=tabla.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        tabla.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        resumen = tk.StringVar()
        ttk.Label(marco, textvariable=resumen, wraplength=780).pack(anchor='w', pady=(10, 0))

        def mostrar(event=None):
            for fila in tabla.get_children():
                tabla.delete(fila)
            caso = casos[selector.current()]
            equivalencias = caso.datos['equivalencias']
            for codigo, original in equivalencias.items():
                fuentes = caso.datos.get('archivos', {}).get(codigo, [])
                tabla.insert('', 'end', values=(codigo, original, '; '.join(fuentes) or 'Sin registro de archivo (caso anterior)'))
            resumen.set(f'{len(equivalencias)} equivalencias guardadas.' if equivalencias else
                        'Este caso no tiene equivalencias. Elige otro caso de la lista para consultar su tabla.')

        selector.bind('<<ComboboxSelected>>', mostrar)
        mostrar()
        ttk.Button(marco, text='Cerrar', command=ventana.destroy).pack(anchor='e', pady=(10, 0))
        ventana.grab_set()
        self.wait_window(ventana)

    def restaurar_fallo(self):
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        if not self.caso:
            self.abrir_caso()
            if not self.caso:
                return
        origen = filedialog.askopenfilename(parent=self, title='Fallo con códigos para restaurar', initialdir=str(CARPETA_DESTINO), filetypes=[('Fallo editable', '*.docx *.txt *.md')])
        if not origen:
            return
        fuente = Path(origen)
        destino = filedialog.asksaveasfilename(parent=self, title='Guardar fallo con datos originales', initialdir=str(CARPETA_ORIGEN), initialfile='fallo_restaurado' + fuente.suffix.lower(), defaultextension=fuente.suffix.lower(), filetypes=[('Fallo', '*' + fuente.suffix.lower())])
        if not destino:
            return
        try:
            if Path(destino).suffix.lower() != fuente.suffix.lower():
                raise ValueError('Conserva la extensión del fallo de entrada.')
            cantidad = restaurar_archivo(fuente, Path(destino), self.caso)
            self.lector_fallo.cargar(Path(destino))
            self.pestanas.select(self.lector_fallo)
            messagebox.showinfo('Fallo restaurado', f'{cantidad} códigos restaurados. Revisa el contenido antes de utilizarlo.\n\n{destino}', parent=self)
        except (OSError, ValueError, KeyError):
            messagebox.showerror('No se restauró el fallo', 'Comprueba el caso y el documento. No debe contener códigos desconocidos o modificados y el destino debe ser un archivo nuevo.', parent=self)

    def destroy(self):
        self.detener_parpadeo()
        if getattr(self, '_poll', None):
            self.after_cancel(self._poll)
            self._poll = None
        if hasattr(self, 'preparadas'):
            self.preparadas.cerrar()
        super().destroy()
        self._imagenes_casillas.clear()
        self.datos_variables.clear()
        for nombre in tuple(vars(self)):
            if isinstance(getattr(self, nombre), tk.Variable):
                setattr(self, nombre, None)

    def detener_parpadeo(self):
        if self._parpadeo is not None:
            self.after_cancel(self._parpadeo)
            self._parpadeo = None
        self._fase_aviso = False
        if hasattr(self, 'boton_analizar'):
            self.boton_analizar.configure(style='TButton', text='Iniciar anonimización')
        if hasattr(self, 'aviso_analisis'):
            self.aviso_analisis.configure(background='#eef2f7', foreground='#111827', font=('Segoe UI', 10), padding=0)

    def parpadear_analisis(self):
        self._parpadeo = None
        config = self.configuraciones.get(self.activo, {})
        en_curso = self.analizando and 'campos' not in config and not config.get('error')
        if str(self.boton_analizar.cget('state')) == 'disabled' and not en_curso:
            self.detener_parpadeo()
            return
        self._fase_aviso = not self._fase_aviso
        self.boton_analizar.configure(
            style='AnalizandoIntenso.TButton' if self._fase_aviso else 'AnalizandoClaro.TButton',
            text='Iniciar anonimización')
        if en_curso:
            self.aviso_analisis.configure(
                background='#facc15' if self._fase_aviso else '#fff3c4',
                foreground='#713f12', font=('Segoe UI', 12, 'bold'), padding=(10, 8))
        self._parpadeo = self.after(650, self.parpadear_analisis)

    def guardar_activo(self, event=None):
        if self.cambiando or self.activo not in self.configuraciones:
            return
        config = self.configuraciones[self.activo]
        config['seleccionados'] = [dato for dato, variable in self.datos_variables.items() if variable.get()]
        self.actualizar_accion()

    def actualizar_accion(self):
        elegidos = sum(variable.get() for variable in self.datos_variables.values())
        config = self.configuraciones.get(self.activo, {})
        seleccion_terminada = bool(elegidos) and 'campos' in config
        if seleccion_terminada and not self.analizando:
            self.boton_analizar.grid_remove()
        else:
            self.boton_analizar.grid()
        bloqueado = self.anonimizacion_bloqueada(self.activo)
        if bloqueado:
            self.boton_reanonimizar.grid()
            self.boton_reanonimizar.configure(state='normal' if not self.analizando and str(self.boton.cget('state')) != 'disabled' else 'disabled')
        else:
            self.boton_reanonimizar.grid_remove()
        libre = not bloqueado and not self.analizando and str(self.boton.cget('state')) != 'disabled'
        listo = not seleccion_terminada and bool(self.activo) and self.archivo_elegido.get() and libre
        self.boton_analizar.configure(state='normal' if listo else 'disabled')
        config = self.configuraciones.get(self.activo, {})
        en_curso = self.analizando and 'campos' not in config and not config.get('error')
        if listo or en_curso:
            if self._parpadeo is None:
                self.parpadear_analisis()
        else:
            self.detener_parpadeo()
        disponible = not bloqueado and bool(elegidos) and not self.analizando and str(self.boton.cget('state')) != 'disabled'
        self.boton_vista.configure(state='normal' if disponible else 'disabled')

    def archivo_anonimizado(self, archivo):
        return bool(self.caso and archivo and self.caso.estado_archivo(archivo) == 'Anonimizado')

    def anonimizacion_bloqueada(self, archivo):
        return self.archivo_anonimizado(archivo) and not self.configuraciones.get(archivo, {}).get('reanonimizar', False)

    def volver_anonimizar(self):
        if self.analizando or str(self.boton.cget('state')) == 'disabled' or not self.archivo_anonimizado(self.activo):
            return
        self.configuraciones[self.activo] = {'seleccionados': [], 'reanonimizar': True}
        self.mostrar_campos()
        self.estado.set('Revisión habilitada. Analiza el original y elige los datos. Al guardar se actualizará la misma copia anonimizada.')

    def anonimizar_campos(self):
        self.guardar_activo()
        if not self.activo or not self.configuraciones.get(self.activo, {}).get('seleccionados'):
            return
        self.previsualizar()

    def ajustar_datos(self, event):
        self.lienzo_datos.itemconfigure(self.ventana_datos, width=event.width)
        ttk.Style(self).configure('Dato.TCheckbutton', wraplength=max(100, event.width - 36))

    def rueda_datos(self, event):
        self.lienzo_datos.yview_scroll(-int(event.delta / 120), 'units')
        return 'break'

    def previsualizar(self):
        if self.anonimizacion_bloqueada(self.activo):
            self.estado.set('Este archivo ya está anonimizado. Su copia guardada está disponible en Ver archivos guardados.')
            return
        if not self.activo:
            messagebox.showinfo('Selecciona un archivo', 'Carga los archivos y pulsa el que quieras comparar.')
            return
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            messagebox.showinfo('Espera un momento', 'Espera a que termine el análisis o la creación de copias.')
            return
        self.guardar_activo()
        config = self.configuraciones[self.activo]
        if config.get('error'):
            messagebox.showerror('Archivo no disponible', config['error'])
            return
        if self.caso is None:
            self.nuevo_caso(recargar=False)
            if self.caso is None:
                return
        for archivo, opciones in self.configuraciones.items():
            self.caso.registrar(opciones.get('seleccionados', []), archivo=archivo)
        categorias, terminos = plan_configuracion(config)
        Comparador(self, self.activo, categorias, terminos, self.preparadas, on_guardar=self.guardar_previsualizado)

    def guardar_previsualizado(self, vista, ruta, categorias, terminos):
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        if not self.destino.get():
            self.elegir_destino(parent=vista)
            if not self.destino.get():
                return
        self.vista_guardado = vista
        if self.iniciar(planes={ruta: (categorias, terminos)}):
            vista.boton_guardar.configure(state='disabled', text='Guardando copia…')
        else:
            self.vista_guardado = None

    def cambiar_archivo(self, event=None):
        self.guardar_activo()
        indices = self.lista.curselection()
        if not indices:
            self.activo = None
            self.archivo_elegido.set(False)
            self.mostrar_campos()
            return
        self.activo = self.archivos[indices[0]]
        self.archivo_elegido.set(True)
        self.mostrar_campos()
        if self.anonimizacion_bloqueada(self.activo):
            self.estado.set('Este archivo ya está anonimizado. Su copia guardada está disponible en Ver archivos guardados.')

    def iniciar_archivo(self):
        if self.anonimizacion_bloqueada(self.activo):
            return
        if not self.activo or not self.archivo_elegido.get() or self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        config = self.configuraciones[self.activo]
        if 'campos' not in config:
            self.analizando = True
            self.boton.configure(state='disabled')
            self.lista.configure(state='disabled')
            self.estado.set('Detectando campos del archivo elegido. Después marca los datos que quieras ocultar.')
            threading.Thread(target=self.analizar_archivos, args=([self.activo], self.generacion), daemon=True).start()
        self.mostrar_campos()

    def mostrar_campos(self):
        self.cambiando = True
        config = self.configuraciones.get(self.activo, {})
        campos = config.get('campos', {})
        self.titulo_campos.set('2. Campos de ' + self.activo.name if self.activo else '2. Selecciona un archivo para ver sus campos')
        self.boton_vista.grid()
        for widget in self.panel_datos.winfo_children():
            widget.destroy()
        self.datos_variables.clear()
        self.casillas_datos.clear()
        seleccionados = {tuple(dato) for dato in config.get('seleccionados', [])}
        total = sum(len(valores) for valores in campos.values())
        for nombre in PATRONES:
            valores = campos.get(nombre, [])
            ttk.Label(self.panel_datos, text=f'{self.etiquetas.get(nombre, nombre)} ({len(valores)})', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(10, 4))
            if not valores:
                ttk.Label(self.panel_datos, text='Sin datos detectados.').pack(anchor='w', padx=8)
            for valor in valores:
                dato = (nombre, valor)
                variable = tk.BooleanVar(value=dato in seleccionados)
                self.datos_variables[dato] = variable
                casilla = ttk.Checkbutton(self.panel_datos, text=valor, variable=variable, style='Dato.TCheckbutton', command=self.guardar_activo, state='disabled' if self.analizando or self.anonimizacion_bloqueada(self.activo) else 'normal')
                casilla.pack(fill='x', anchor='w', padx=4, pady=2)
                casilla.bind('<MouseWheel>', self.rueda_datos)
                self.casillas_datos.append(casilla)
        resumen = [f'{total} datos encontrados. Marca uno por uno los que quieras ocultar.']
        if self.anonimizacion_bloqueada(self.activo):
            resumen = ['Este archivo ya está anonimizado. Puedes consultar su copia en Ver archivos guardados.']
        elif config.get('error'):
            resumen = ['No se pudo analizar este archivo: ' + config['error']]
        elif not self.activo:
            resumen = ['Primero crea o abre un caso y carga la demanda.' if not self.caso else 'Elige un archivo para continuar con estos campos.']
        elif 'campos' not in config:
            resumen = ['Detectando campos del archivo elegido…' if self.analizando else 'Marca la casilla de selección y pulsa Iniciar anonimización.']
        elif not total:
            resumen = ['No se detectaron nombres, identificaciones ni correos.']
        # Mantiene el panel compacto; cada campo muestra su número de valores.
        self.resumen_campos.set('\n'.join(resumen))
        self.detener_parpadeo()
        if self.analizando and 'campos' not in config and not config.get('error'):
            self.parpadear_analisis()
        self.cambiando = False
        self.actualizar_accion()

    def analizar_archivos(self, archivos, generacion):
        from analisis import analizar
        for archivo in archivos:
            try:
                if archivo.suffix.lower() not in FORMATOS:
                    raise ValueError('Formato no compatible.')
                campos = analizar(archivo)
                self.eventos.put(('analizado', generacion, archivo, campos, None))
            except Exception as exc:
                self.eventos.put(('analizado', generacion, archivo, {}, str(exc)))
        self.eventos.put(('analisis_fin', generacion))

    def elegir_origen(self):
        if self.caso is None:
            return
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        ruta = filedialog.askdirectory(parent=self, title='Selecciona la carpeta de documentos', initialdir=str(CARPETA_ORIGEN))
        if ruta:
            try:
                SelectorArchivos(self, ruta, self.cargar_archivos)
            except OSError:
                messagebox.showerror('Carpeta no disponible', 'No se pudo leer la carpeta seleccionada.', parent=self)

    def elegir_archivos(self):
        if self.caso is None:
            return
        if self.analizando or str(self.boton.cget('state')) == 'disabled':
            return
        rutas = filedialog.askopenfilenames(
            title='Demanda y anexos de la tutela',
            parent=self,
            initialdir=str(CARPETA_ORIGEN),
            filetypes=filtros_documentos())
        if rutas:
            self.cargar_archivos(rutas)

    def cargar_archivos(self, rutas):
        if self.caso is None:
            return
        if not rutas:
            return
        self.guardar_activo()
        self.archivos = [Path(ruta) for ruta in rutas]
        self.caso.recuperar_estados_archivos(self.archivos, [self.destino.get(), CARPETA_DESTINO])
        self.caso.registrar_archivos(self.archivos)
        self.configuraciones = {p: {'seleccionados': []} for p in self.archivos}
        self.generacion += 1
        self.analizando = False
        self.boton.configure(state='normal')
        self.origen.set(str(self.archivos[0].parent))
        self.lista.delete(0, 'end')
        for path in self.archivos:
            marca = '' if path.suffix.lower() in FORMATOS else ' [formato no compatible]'
            self.lista.insert('end', f'[{self.caso.estado_archivo(path)}] {path.name}{marca}')
        self.activo = None
        self.archivo_elegido.set(False)
        self.mostrar_campos()
        self.conteo.set(f'{len(self.archivos)} archivos cargados. Elige uno de la lista.')
        self.estado.set('Elige un archivo, marca sus datos y pulsa Anonimizar campos seleccionados.')

    def elegir_destino(self, parent=None):
        ruta = filedialog.askdirectory(parent=parent or self, title='Carpeta donde guardar las copias', initialdir=self.destino.get() or str(Path.home()))
        if ruta:
            self.destino.set(ruta)
            try:
                config = self.ruta_configuracion()
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(json.dumps({'destino': ruta}, ensure_ascii=False), encoding='utf-8')
            except OSError:
                pass

    def ruta_configuracion(self):
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Anonimizador' / 'preferencias.json'

    def cargar_destino(self):
        try:
            ruta = json.loads(self.ruta_configuracion().read_text(encoding='utf-8')).get('destino', '')
            if ruta and Path(ruta).is_dir():
                self.destino.set(ruta)
        except (OSError, ValueError, TypeError):
            pass

    def cargar(self):
        if self.caso is None:
            return
        self.lista.delete(0, 'end')
        self.archivos = []
        if not self.origen.get():
            self.conteo.set('Sin archivos. Elige archivos o una carpeta para comenzar.')
            return
        try:
            base = Path(self.origen.get())
            encontrados = list(base.rglob('*') if self.subcarpetas.get() else base.iterdir())
            archivos = [p for p in encontrados if p.is_file()]
            self.archivos = sorted(archivos, key=lambda p: str(p).lower())
            self.caso.recuperar_estados_archivos(self.archivos, [self.destino.get(), CARPETA_DESTINO])
            self.caso.registrar_archivos(self.archivos)
            compatibles = sum(p.suffix.lower() in FORMATOS for p in self.archivos)
            for path in self.archivos:
                marca = '' if path.suffix.lower() in FORMATOS else ' [formato no compatible]'
                self.lista.insert('end', f'[{self.caso.estado_archivo(path)}] {path.relative_to(base)}{marca}')
            self.conteo.set(f'{len(archivos)} archivos encontrados · {compatibles} compatibles.' if archivos else 'No hay archivos en esta carpeta. Prueba Incluir subcarpetas o Elegir archivos.')
        except OSError as exc:
            messagebox.showerror('Carpeta no disponible', str(exc))

    def abrir_destino(self):
        if not self.destino.get():
            messagebox.showinfo('Carpeta de destino', 'Primero elige dónde guardar las copias.', parent=self)
            return
        carpeta = Path(self.destino.get()).resolve()
        if not carpeta.is_dir():
            messagebox.showerror('Carpeta no disponible', 'La carpeta de destino ya no está disponible.', parent=self)
            return
        ruta = filedialog.askopenfilename(
            parent=self, title='Ver documento guardado',
            initialdir=str(carpeta),
            filetypes=filtros_documentos(),
        )
        if not ruta:
            return
        try:
            os.startfile(str(Path(ruta).resolve()))
        except OSError:
            messagebox.showerror(
                'No se pudo abrir la copia',
                'Comprueba que el archivo existe y que tienes una aplicación compatible con su formato instalada.',
                parent=self,
            )

    def iniciar(self, planes=None):
        if self.analizando:
            return
        self.guardar_activo()
        if planes is None:
            planes = {}
            for archivo, config in self.configuraciones.items():
                if config.get('error'):
                    continue
                if not config.get('seleccionados'):
                    continue
                planes[archivo] = plan_configuracion(config)
        planes = {archivo: plan for archivo, plan in planes.items() if not self.anonimizacion_bloqueada(archivo)}
        seleccion = list(planes)
        if not seleccion and any(self.anonimizacion_bloqueada(p) for p in self.archivos):
            messagebox.showinfo('Archivos ya anonimizados', 'Los archivos anonimizados no se vuelven a procesar. Selecciona un archivo pendiente y marca sus datos.', parent=self)
            return
        if not seleccion or not self.destino.get():
            messagebox.showinfo('Faltan datos', 'Elige la carpeta de destino y marca los datos concretos que quieres anonimizar. Los archivos sin datos marcados no se procesan.')
            return
        destino = Path(self.destino.get()).resolve()
        if (self.origen.get() and destino == Path(self.origen.get()).resolve()) or any(destino == p.parent.resolve() for p in seleccion):
            messagebox.showerror('Elige otra carpeta', 'La carpeta de destino debe ser diferente de la de origen.')
            return
        self.boton.configure(state='disabled')
        self.boton_vista.configure(state='disabled')
        self.lista.configure(state='disabled')
        for casilla in self.casillas_datos:
            casilla.configure(state='disabled')
        self.progreso.configure(maximum=len(seleccion), value=0)
        self.ultima_copia = None
        self.estado.set('Procesando… La detección de nombres puede tardar al cargar el modelo local.')
        threading.Thread(target=self.trabajar, args=(seleccion, destino, planes), daemon=True).start()
        return True

    def trabajar(self, seleccion, destino, planes):
        ok = 0
        for i, origen in enumerate(seleccion, 1):
            extension = '.docx' if self.preparadas.caso else '.png' if origen.suffix.lower() in IMAGENES else FORMATOS_ANTIGUOS.get(origen.suffix.lower(), origen.suffix.lower())
            temporal = destino / ('.anon-' + uuid.uuid4().hex + extension)
            try:
                if self.anonimizacion_bloqueada(origen):
                    self.eventos.put(('avance', i, 'Omitido: el archivo ya está anonimizado.'))
                    continue
                # Nombre neutral: el nombre original también puede contener datos personales.
                salida = destino / ('anonimizado_' + uuid.uuid4().hex[:12] + extension)
                existente = self.caso.copia_para_actualizar(origen) if self.caso else None
                if existente:
                    salida = existente
                    temporal = salida.parent / ('.anon-' + uuid.uuid4().hex + extension)
                categorias, terminos = planes[origen]
                preparada, count = self.preparadas.obtener(origen, categorias, terminos)
                if self.caso:
                    self.caso.guardar()
                    instrucciones = destino / 'LEER_ANTES_DE_CARGAR_AL_SKILL.txt'
                    instrucciones.write_text('Carga únicamente los documentos anonimizados. Conserva exactamente todos los códigos entre corchetes al redactar el fallo; no los traduzcas, abrevies ni inventes. Devuelve el proyecto en DOCX para restaurarlo localmente. Nunca cargues la tabla privada de equivalencias. Revisa los documentos antes de compartirlos.', encoding='utf-8')
                # Guarda exactamente los bytes revisados si las opciones y el original siguen iguales.
                shutil.copyfile(preparada, temporal)
                if self.caso:
                    self.caso.publicar_copia(temporal, salida, origen, reemplazar=bool(existente))
                else:
                    temporal.rename(salida)
                ok += 1
                aviso = ' REVISAR: sin coincidencias; puede contener datos no detectados.' if count == 0 else ''
                self.eventos.put(('avance', i, f'Guardado: {salida} · {count} coincidencias.{aviso}', salida, origen))
            except Exception as exc:
                temporal.unlink(missing_ok=True)
                self.eventos.put(('avance', i, f'Archivo {i}: ERROR ({type(exc).__name__}). No se creó una copia. Comprueba formato, permisos o contraseña.'))
        self.eventos.put(('fin', ok, len(seleccion)))

    def recibir(self):
        try:
            while True:
                evento = self.eventos.get_nowait()
                if evento[0] == 'analizado':
                    _, generacion, archivo, campos, error = evento
                    if generacion != self.generacion:
                        continue
                    self.configuraciones[archivo]['campos'] = campos
                    if error:
                        self.configuraciones[archivo]['error'] = error
                    if self.activo == archivo:
                        self.mostrar_campos()
                elif evento[0] == 'analisis_fin':
                    if evento[1] != self.generacion:
                        continue
                    self.analizando = False
                    self.lista.configure(state='normal')
                    self.boton.configure(state='normal')
                    self.conteo.set(f'{len(self.archivos)} archivos. Pulsa cada uno y marca sus campos.')
                    self.estado.set('Análisis terminado. Marca en pantalla los datos que deseas anonimizar.')
                    if self.activo:
                        self.mostrar_campos()
                elif evento[0] == 'avance':
                    if len(evento) > 3:
                        self.ultima_copia = evento[3]
                    if len(evento) > 4:
                        self.configuraciones.get(evento[4], {}).pop('reanonimizar', None)
                    self.progreso.configure(value=evento[1])
                    if 'ERROR' in evento[2] or 'REVISAR:' in evento[2]:
                        self.estado.set(evento[2])
                else:
                    self.actualizar_estado_caso()
                    if self.caso:
                        for archivo, (_, casilla) in zip(self.archivos, self.lista.filas):
                            marca = '' if archivo.suffix.lower() in FORMATOS else ' [formato no compatible]'
                            casilla.configure(text=f'[{self.caso.estado_archivo(archivo)}] {archivo.name}{marca}')
                    self.boton.configure(state='normal')
                    self.lista.configure(state='normal')
                    if self.activo:
                        self.mostrar_campos()
                    self.estado.set(f'Terminado: {evento[1]} de {evento[2]} copias creadas. Revisa los resultados antes de compartir.')
                    if self.vista_guardado and self.vista_guardado.winfo_exists():
                        if evento[1] == evento[2]:
                            self.vista_guardado.mostrar_guardado(self.ultima_copia)
                            if self.ultima_copia:
                                copia = str(self.ultima_copia)
                                self.vista_guardado.boton_abrir.configure(command=lambda ruta=copia: os.startfile(ruta))
                                self.vista_guardado.boton_abrir.pack(side='right', padx=8)
                        else:
                            self.vista_guardado.boton_guardar.configure(text='Reintentar guardar copia', state='normal')
                            self.vista_guardado.estado.set('No se pudo guardar la copia. Comprueba los permisos de la carpeta de destino.')
                    padre_aviso = self.vista_guardado if self.vista_guardado and self.vista_guardado.winfo_exists() else self
                    self.vista_guardado = None
                    if evento[1] > 0 and evento[1] == evento[2]:
                        if self.ultima_copia:
                            mensaje = 'La copia anonimizada se guardó correctamente.\n\nUbicación:\n' + str(self.ultima_copia)
                        else:
                            mensaje = f'Se guardaron correctamente {evento[1]} copias anonimizadas.'
                        # La comparación puede cubrir la ventana principal: el aviso
                        # debe pertenecer a la ventana que el usuario está viendo.
                        messagebox.showinfo('Guardado completado', mensaje, parent=padre_aviso)
        except queue.Empty:
            pass
        self._poll = self.after(150, self.recibir)


if __name__ == '__main__':
    Anonimizador().mainloop()
