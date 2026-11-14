"""Selección explícita de documentos antes de analizarlos."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from motor import FORMATOS


class SelectorArchivos(tk.Toplevel):
    def __init__(self, parent, carpeta, on_seleccionar):
        super().__init__(parent)
        self.title('Seleccionar archivos para anonimizar')
        self.geometry('780x520')
        self.minsize(580, 380)
        self.transient(parent)
        self.on_seleccionar = on_seleccionar
        self.archivos = sorted(
            (p for p in Path(carpeta).iterdir() if p.is_file() and p.suffix.lower() in FORMATOS),
            key=lambda p: p.name.casefold(),
        )
        panel = ttk.Frame(self, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Elige uno, varios o todos los archivos',
                  font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(panel, text=str(carpeta), wraplength=540).pack(anchor='w', pady=6)
        ttk.Label(panel, text='Ctrl + clic: elegir varios. Mayús + clic: elegir un intervalo.').pack(anchor='w')
        acciones = ttk.Frame(panel)
        acciones.pack(fill='x', pady=8)
        ttk.Button(acciones, text='Seleccionar todos', command=self.seleccionar_todos).pack(side='left')
        ttk.Button(acciones, text='Quitar selección', command=self.quitar_seleccion).pack(side='left', padx=8)
        area = ttk.Frame(panel)
        area.pack(fill='both', expand=True)
        self.lista = tk.Listbox(area, selectmode='extended', exportselection=False,
                               font=('Segoe UI', 11))
        scroll = ttk.Scrollbar(area, command=self.lista.yview)
        self.lista.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.lista.pack(fill='both', expand=True)
        for archivo in self.archivos:
            self.lista.insert('end', archivo.name)
        self.lista.bind('<<ListboxSelect>>', self.actualizar)
        self.conteo = tk.StringVar()
        ttk.Label(panel, textvariable=self.conteo).pack(anchor='w', pady=8)
        pie = ttk.Frame(panel)
        pie.pack(fill='x')
        ttk.Button(pie, text='Cancelar', command=self.destroy).pack(side='right')
        self.boton_cargar = ttk.Button(pie, text='Cargar seleccionados', command=self.aceptar)
        self.boton_cargar.pack(side='right', padx=8)
        self.actualizar()
        self.grab_set()

    def actualizar(self, event=None):
        cantidad = len(self.lista.curselection())
        self.conteo.set(f'{cantidad} de {len(self.archivos)} archivos seleccionados.' if self.archivos
                        else 'No hay archivos compatibles en esta carpeta.')
        self.boton_cargar.configure(state='normal' if cantidad else 'disabled')

    def seleccionar_todos(self):
        self.lista.selection_set(0, 'end')
        self.actualizar()

    def quitar_seleccion(self):
        self.lista.selection_clear(0, 'end')
        self.actualizar()

    def aceptar(self):
        elegidos = [self.archivos[i] for i in self.lista.curselection()]
        if elegidos:
            self.destroy()
            self.on_seleccionar(elegidos)
