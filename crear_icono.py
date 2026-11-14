"""Genera el icono geométrico de la aplicación en varios tamaños."""
from pathlib import Path
from PIL import Image, ImageDraw

carpeta = Path(__file__).resolve().parent
imagen = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
d = ImageDraw.Draw(imagen)
d.rounded_rectangle((40, 40, 984, 984), radius=220, fill='#102c50')
d.polygon([(512, 130), (825, 255), (800, 595), (700, 750), (512, 890),
           (324, 750), (224, 595), (199, 255)], fill='#30c8ba')
d.rounded_rectangle((340, 278, 684, 705), radius=35, fill='white')
d.rounded_rectangle((389, 350, 635, 377), radius=12, fill='#a6b9cd')
d.rounded_rectangle((389, 430, 635, 485), radius=12, fill='#102c50')
d.rounded_rectangle((389, 524, 635, 579), radius=12, fill='#102c50')
d.rounded_rectangle((389, 624, 546, 645), radius=10, fill='#a6b9cd')
imagen.save(carpeta / 'anonimizador.png')
imagen.save(carpeta / 'anonimizador.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
