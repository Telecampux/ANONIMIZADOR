"""Filtros comunes para abrir documentos que el motor puede leer."""
from motor import FORMATOS, IMAGENES


def filtros_documentos():
    return [
        ('Todos los compatibles', tuple('*' + ext for ext in sorted(FORMATOS))),
        ('PDF', '*.pdf'), ('Word', ('*.doc', '*.docx')), ('Excel', ('*.xls', '*.xlsx')),
        ('PowerPoint', ('*.ppt', '*.pptx')),
        ('Imágenes', tuple('*' + ext for ext in sorted(IMAGENES))),
        ('Texto y datos', tuple('*' + ext for ext in sorted(
            FORMATOS - IMAGENES - {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}))),
        ('Todos los archivos', '*.*'),
    ]
