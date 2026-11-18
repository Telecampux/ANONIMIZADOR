"""Resaltado permanente de las opciones en todas las ventanas de la aplicación."""
from tkinter import ttk


def configurar_estilos(widget):
    root = widget._root()
    if getattr(root, '_opciones_resaltadas', False):
        return
    style = ttk.Style(widget)
    # Clam renders explicit colors consistently, including on Windows.
    style.theme_use('clam')
    azul = '#174ea6'
    claro = '#e2edff'
    texto = '#143969'
    style.configure('TButton', font=('Segoe UI', 10, 'bold'), padding=(10, 6),
                    background=claro, foreground=texto, bordercolor=azul,
                    lightcolor=claro, darkcolor=azul, borderwidth=1)
    style.map('TButton', background=[('disabled', '#e4e7ec'), ('pressed', '#bfd5ff'), ('active', '#d2e2ff')],
              foreground=[('disabled', '#64748b')], bordercolor=[('focus', '#082b67')])
    style.configure('Principal.TButton', background=azul, foreground='white')
    style.map('Principal.TButton', background=[('disabled', '#e4e7ec'), ('pressed', '#0c3276'), ('active', '#2161bd')],
              foreground=[('disabled', '#64748b'), ('!disabled', 'white')])
    style.configure('Proceso.TButton', background='#166534', foreground='white',
                    bordercolor='#14532d', lightcolor='#166534', darkcolor='#14532d')
    style.map('Proceso.TButton', background=[('disabled', '#47825c'), ('pressed', '#14532d'), ('active', '#15803d')],
              foreground=[('disabled', 'white'), ('!disabled', 'white')],
              bordercolor=[('focus', '#052e16')])
    style.configure('Proceso.Horizontal.TProgressbar', background='#16a34a',
                    lightcolor='#22c55e', darkcolor='#15803d',
                    troughcolor='#dcfce7', bordercolor='#15803d')
    for kind in ('TRadiobutton', 'TCheckbutton'):
        style.configure(kind, font=('Segoe UI', 10, 'bold'), padding=(8, 5),
                        background=claro, foreground=texto)
        style.map(kind, background=[('disabled', '#e4e7ec'), ('selected', azul), ('active', '#d2e2ff')],
                  foreground=[('disabled', '#64748b'), ('selected', 'white')],
                  indicatorbackground=[('selected', '#ffffff'), ('!selected', '#ffffff')],
                  indicatorforeground=[('selected', azul)])
    style.configure('TNotebook.Tab', font=('Segoe UI', 10, 'bold'), padding=(10, 7),
                    background=claro, foreground=texto)
    style.map('TNotebook.Tab', background=[('selected', azul), ('active', '#d2e2ff')],
              foreground=[('selected', 'white')])
    style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'),
                    background=claro, foreground=texto, padding=(5, 5))
    style.map('Treeview', background=[('selected', azul)], foreground=[('selected', 'white')])
    style.configure('TLabelframe.Label', font=('Segoe UI', 10, 'bold'), foreground=azul)
    root._opciones_resaltadas = True
