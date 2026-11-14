"""Formulario para crear un caso local."""
import tkinter as tk
from tkinter import ttk, simpledialog


class DialogoNuevoCaso(simpledialog.Dialog):
    def body(self, master):
        self.resizable(False, False)
        self.configure(bg='#eef2f7')
        master.configure(bg='#eef2f7', padx=32, pady=28)
        estilo = ttk.Style(self)
        estilo.configure('NombreCaso.TEntry', padding=(14, 12),
                         fieldbackground='#ffffff', foreground='#123247',
                         bordercolor='#b8c7d5', lightcolor='#ffffff',
                         darkcolor='#ffffff')
        estilo.map('NombreCaso.TEntry', bordercolor=[('focus', '#087f6d')])
        marco = ttk.Frame(master)
        marco.pack(fill='both', expand=True)
        ttk.Label(marco, text='Crea un nuevo caso',
                  font=('Segoe UI', 20, 'bold'), foreground='#123247').pack(anchor='w')
        ttk.Label(marco, text='Dale un nombre para encontrarlo y continuar después.',
                  wraplength=600).pack(anchor='w', pady=(8, 28))
        ttk.Label(marco, text='Nombre del caso',
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 7))
        self.nombre = tk.StringVar(self)
        self.entrada = ttk.Entry(marco, textvariable=self.nombre, width=56,
                                 font=('Segoe UI', 14), style='NombreCaso.TEntry')
        self.entrada.pack(fill='x')
        ttk.Label(marco, text='Por ejemplo: Tutela de salud · Noviembre 2026',
                  foreground='#526477', wraplength=600).pack(anchor='w', pady=(10, 0))
        self.error = tk.StringVar(self)
        ttk.Label(marco, textvariable=self.error, foreground='#b42318',
                  wraplength=600).pack(anchor='w', pady=(8, 0))
        ttk.Separator(marco).pack(fill='x', pady=(18, 18))
        ttk.Label(marco, text='El caso y su tabla privada se guardan en este computador.',
                  foreground='#526477', wraplength=600).pack(anchor='w')
        return self.entrada

    def buttonbox(self):
        botones = ttk.Frame(self, padding=(32, 0, 32, 28))
        botones.pack(fill='x')
        ttk.Button(botones, text='Crear caso', style='Accion.TButton',
                   command=self.ok).pack(side='right')
        ttk.Button(botones, text='Cancelar', command=self.cancel).pack(side='right', padx=(0, 12))
        self.bind('<Return>', self.ok)
        self.bind('<Escape>', self.cancel)

    def validate(self):
        if not self.nombre.get().strip():
            self.error.set('Escribe un nombre para reconocer el caso.')
            self.entrada.focus_set()
            return False
        return True

    def apply(self):
        self.result = self.nombre.get().strip()


def pedir_nombre_caso(parent):
    return DialogoNuevoCaso(parent, title='Nuevo caso').result
