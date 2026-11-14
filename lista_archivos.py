"""Lista desplazable con una casilla delante de cada archivo."""
import tkinter as tk
from tkinter import ttk


class ListaArchivos(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.filas = []
        self.indice = None
        self.estado = 'normal'
        self.lienzo = tk.Canvas(self, background='white', highlightthickness=0)
        self.panel = ttk.Frame(self.lienzo)
        self.ventana = self.lienzo.create_window(0, 0, window=self.panel, anchor='nw')
        self.panel.bind('<Configure>', lambda e: self.lienzo.configure(scrollregion=self.lienzo.bbox('all')))
        self.lienzo.bind('<Configure>', lambda e: self.lienzo.itemconfigure(self.ventana, width=e.width))
        self.lienzo.pack(fill='both', expand=True)

    def yview(self, *args):
        return self.lienzo.yview(*args)

    def configure(self, **kwargs):
        if 'yscrollcommand' in kwargs:
            self.lienzo.configure(yscrollcommand=kwargs.pop('yscrollcommand'))
        if 'state' in kwargs:
            self.estado = kwargs.pop('state')
            for _, casilla in self.filas:
                casilla.configure(state=self.estado)
        if kwargs:
            super().configure(**kwargs)

    def insert(self, posicion, texto):
        indice = len(self.filas)
        variable = tk.BooleanVar(value=False)
        casilla = ttk.Checkbutton(self.panel, text=texto, variable=variable,
                                 command=lambda: self.elegir(indice), state=self.estado)
        casilla.pack(fill='x', anchor='w', padx=6, pady=3)
        self.filas.append((variable, casilla))

    def elegir(self, indice):
        marcado = self.filas[indice][0].get()
        self.selection_clear(0, 'end')
        if marcado:
            self.selection_set(indice)
        self.event_generate('<<ListboxSelect>>')

    def delete(self, primero, ultimo=None):
        for _, casilla in self.filas:
            casilla.destroy()
        self.filas.clear()
        self.indice = None

    def size(self):
        return len(self.filas)

    def curselection(self):
        return () if self.indice is None else (self.indice,)

    def selection_set(self, indice):
        self.selection_clear(0, 'end')
        self.indice = indice
        self.filas[indice][0].set(True)

    def selection_clear(self, primero, ultimo=None):
        for variable, _ in self.filas:
            variable.set(False)
        self.indice = None
