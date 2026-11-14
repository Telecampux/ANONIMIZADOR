import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageOps, ImageTk


def elegir_zonas(parent, ruta):
    with Image.open(ruta) as original:
        if getattr(original, 'n_frames', 1) != 1:
            raise ValueError('Las imágenes animadas o de varias páginas deben separarse primero.')
        imagen = ImageOps.exif_transpose(original).convert('RGB')
    ventana = tk.Toplevel(parent)
    ventana.title('Ocultar zonas — ' + ruta.name)
    ventana.transient(parent)
    zonas, objetos = [], []
    resultado = None
    ancho = min(1000, parent.winfo_screenwidth() - 100)
    alto = min(650, parent.winfo_screenheight() - 220)
    escala = min(ancho / imagen.width, alto / imagen.height, 1)
    tamano = (max(1, int(imagen.width * escala)), max(1, int(imagen.height * escala)))
    foto = ImageTk.PhotoImage(imagen.resize(tamano))
    ttk.Label(ventana, text='Arrastra sobre cada dato que quieras ocultar. Las zonas negras se eliminan de la copia.').pack(padx=12, pady=10)
    canvas = tk.Canvas(ventana, width=tamano[0], height=tamano[1], highlightthickness=0)
    canvas.pack(padx=12)
    canvas.create_image(0, 0, image=foto, anchor='nw')
    inicio = None
    actual = None

    def punto(event):
        return max(0, min(event.x, tamano[0])), max(0, min(event.y, tamano[1]))

    def pulsar(event):
        nonlocal inicio, actual
        inicio = punto(event)
        actual = canvas.create_rectangle(*inicio, *inicio, fill='black', outline='#ef4444')

    def mover(event):
        if inicio is not None:
            canvas.coords(actual, *inicio, *punto(event))

    def soltar(event):
        nonlocal inicio
        if inicio is None:
            return
        x, y = punto(event)
        x0, x1 = sorted((inicio[0], x))
        y0, y1 = sorted((inicio[1], y))
        if x1 - x0 >= 2 and y1 - y0 >= 2:
            zonas.append(tuple(int(v / escala) for v in (x0, y0, x1, y1)))
            objetos.append(actual)
        else:
            canvas.delete(actual)
        inicio = None

    def deshacer():
        if zonas:
            zonas.pop()
            canvas.delete(objetos.pop())

    def aceptar():
        nonlocal resultado
        if not zonas:
            messagebox.showinfo('Selecciona zonas', 'Marca al menos una zona para ocultar.', parent=ventana)
            return
        resultado = list(zonas)
        ventana.destroy()

    canvas.bind('<ButtonPress-1>', pulsar)
    canvas.bind('<B1-Motion>', mover)
    canvas.bind('<ButtonRelease-1>', soltar)
    botones = ttk.Frame(ventana)
    botones.pack(fill='x', padx=12, pady=10)
    ttk.Button(botones, text='Deshacer zona', command=deshacer).pack(side='left')
    ttk.Button(botones, text='Cancelar', command=ventana.destroy).pack(side='right')
    ttk.Button(botones, text='Usar estas zonas', command=aceptar).pack(side='right', padx=8)
    ventana.grab_set()
    parent.wait_window(ventana)
    return resultado
