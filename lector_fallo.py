"""Lectura local de fallos guardados, sin modificar los documentos."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from analisis import extraer
from motor import FORMATOS
from formatos_documentos import filtros_documentos


class LectorFallo(ttk.Frame):
    def __init__(self, parent, carpeta_inicial):
        super().__init__(parent, padding=12)
        self.carpeta_inicial = carpeta_inicial
        self.carpeta = None
        acciones = ttk.Frame(self)
        acciones.pack(fill='x')
        ttk.Button(acciones, text='Abrir fallo desde carpeta…',
                   command=self.elegir).pack(side='left')
        self.ruta = tk.StringVar(value='Abre un documento: PDF, Word (DOC/DOCX), Excel (XLS/XLSX), PowerPoint (PPT/PPTX), imagen o texto.')
        etiqueta = ttk.Label(self, textvariable=self.ruta, wraplength=600)
        etiqueta.pack(fill='x', pady=8)
        self.bind('<Configure>', lambda e: etiqueta.configure(wraplength=max(120, e.width - 24)))
        area = ttk.Frame(self)
        area.pack(fill='both', expand=True)
        self.texto = tk.Text(area, wrap='word', font=('Segoe UI', 12),
                             state='disabled', padx=12, pady=12)
        scroll = ttk.Scrollbar(area, command=self.texto.yview)
        self.texto.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.texto.pack(fill='both', expand=True)
        ttk.Label(self, text='Solo lectura del texto. En imágenes y PDF se usa OCR; revisa posibles errores.').pack(anchor='w', pady=(8, 0))

    def elegir(self):
        ruta = filedialog.askopenfilename(
            parent=self, title='Leer fallo restaurado desde carpeta',
            initialdir=str(self.carpeta or self.carpeta_inicial()),
            filetypes=filtros_documentos())
        if ruta:
            self.cargar(Path(ruta))

    def cargar(self, ruta):
        ruta = Path(ruta)
        try:
            if ruta.suffix.lower() not in FORMATOS:
                raise ValueError('Formato no compatible')
            contenido = extraer(ruta)
        except Exception:
            messagebox.showerror('No se pudo leer el fallo',
                                 'Comprueba que el archivo está disponible, no está protegido y tiene un formato compatible. Para DOC, XLS o PPT se necesita Microsoft Office instalado.',
                                 parent=self)
            return False
        self.texto.configure(state='normal')
        self.texto.delete('1.0', 'end')
        self.texto.insert('1.0', contenido)
        self.texto.configure(state='disabled')
        self.texto.yview_moveto(0)
        self.ruta.set(str(ruta.resolve()))
        self.carpeta = ruta.parent
        return True
