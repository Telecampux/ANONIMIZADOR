"""Casillas con chulito, independientes del indicador X del tema de Windows."""
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk


def configurar_casillas(root):
    style = ttk.Style(root)
    lado = max(18, round(float(root.tk.call('tk', 'scaling')) * 15))
    imagenes = []
    for seleccionado, deshabilitado in ((False, False), (True, False), (False, True), (True, True)):
        escala = 4
        imagen = Image.new('RGBA', (lado * escala, lado * escala))
        dibujo = ImageDraw.Draw(imagen)
        borde = '#94a3b8' if deshabilitado else '#64748b'
        fondo = '#e2e8f0' if deshabilitado else '#ffffff'
        if seleccionado:
            fondo = '#94a3b8' if deshabilitado else '#087f6d'
            borde = fondo
        def puntos(valores):
            return tuple(round(v * lado * escala) for v in valores)
        dibujo.rounded_rectangle(puntos((.08, .08, .88, .88)), radius=round(lado * escala * .13), fill=fondo, outline=borde, width=escala)
        if seleccionado:
            dibujo.line([puntos((.24, .48)), puntos((.42, .65)), puntos((.73, .31))], fill='white', width=round(lado * escala * .12), joint='curve')
        imagenes.append(ImageTk.PhotoImage(imagen.resize((lado, lado), Image.Resampling.LANCZOS), master=root))
    root._imagenes_casillas = imagenes
    style.element_create('Chulito.indicator', 'image', imagenes[0],
                         ('disabled', 'selected', imagenes[3]), ('disabled', imagenes[2]),
                         ('selected', imagenes[1]), sticky='w')
    style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
        ('Chulito.indicator', {'side': 'left', 'sticky': ''}),
        ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
            ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
    style.configure('TCheckbutton', padding=(0, 2, 6, 2))
