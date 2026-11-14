"""Seudónimos por caso y restauración local, sin servicios externos."""
import json
import hashlib
import os
import re
import uuid
import threading
import copy
from datetime import datetime
from pathlib import Path

TOKEN = re.compile(r"\[(?:PERSONA|CEDULA|CORREO|DATO)_[A-F0-9]{12}_\d{3,}\]")


class Caso:
    def __init__(self, ruta=None, nombre=None):
        self.lock = threading.RLock()
        if ruta:
            self.ruta = Path(ruta)
            self.datos = json.loads(self.ruta.read_text(encoding='utf-8'))
            if not isinstance(self.datos, dict):
                raise ValueError('Tabla de equivalencias no válida.')
            if self.datos.get('version') != 1 or not isinstance(self.datos.get('equivalencias'), dict) or not re.fullmatch(r'[A-F0-9]{12}', str(self.datos.get('id', ''))):
                raise ValueError('Tabla de equivalencias no válida.')
            for codigo, valor in self.datos['equivalencias'].items():
                if not TOKEN.fullmatch(codigo) or not isinstance(valor, str) or not valor:
                    raise ValueError('Tabla de equivalencias no válida.')
                if self.datos['id'] not in codigo:
                    raise ValueError('La tabla mezcla códigos de distintos casos.')
            copias = self.datos.get('copias', {})
            if not isinstance(copias, dict) or any(
                not isinstance(ruta, str) or not isinstance(firma, str)
                or not re.fullmatch(r'[a-f0-9]{64}', firma)
                for ruta, firma in copias.items()
            ):
                raise ValueError('Registro de copias no válido.')
            archivos = self.datos.get('archivos', {})
            if not isinstance(archivos, dict) or any(
                codigo not in self.datos['equivalencias'] or not isinstance(fuentes, list)
                or any(not isinstance(fuente, str) or not fuente for fuente in fuentes)
                for codigo, fuentes in archivos.items()
            ):
                raise ValueError('Registro de archivos no válido.')
        else:
            identificador = uuid.uuid4().hex[:12].upper()
            base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Anonimizador' / 'casos'
            self.ruta = base / (identificador + '.json')
            self.datos = {'version': 1, 'id': identificador, 'equivalencias': {},
                          'nombre': (nombre or '').strip() or 'Caso sin nombre',
                          'creado': datetime.now().isoformat(timespec='seconds')}
            self.guardar()

    @property
    def nombre(self):
        nombre = self.datos.get('nombre')
        return nombre.strip() if isinstance(nombre, str) and nombre.strip() else 'Caso sin nombre'

    @property
    def fecha(self):
        try:
            fecha = datetime.fromisoformat(self.datos.get('creado', ''))
        except (ValueError, TypeError):
            fecha = datetime.fromtimestamp(self.ruta.stat().st_mtime)
        return fecha.strftime('%d/%m/%Y %H:%M')

    def guardar(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = self.ruta.with_suffix('.tmp')
        temporal.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2), encoding='utf-8')
        temporal.replace(self.ruta)

    @property
    def estado_anonimizacion(self):
        with self.lock:
            copias = list(self.datos.get('copias', {}).items())
        for nombre, firma in copias:
            try:
                if hashlib.sha256(Path(nombre).read_bytes()).hexdigest() == firma:
                    return 'Anonimizado · copia guardada'
            except OSError:
                continue
        return 'Sin copia anonimizada disponible'

    def registrar(self, seleccionados, archivo=None):
        with self.lock:
            tabla = self.datos['equivalencias']
            archivos = self.datos.setdefault('archivos', {})
            origen = str(Path(archivo).resolve()) if archivo is not None else None
            for categoria, valor in seleccionados:
                codigo = next((k for k, v in tabla.items() if v.casefold() == valor.casefold()), None)
                if codigo is None:
                    tipo = 'PERSONA' if 'Nombres' in categoria else 'CORREO' if 'Correo' in categoria else 'CEDULA' if 'Documentos' in categoria else 'DATO'
                    numero = 1 + sum(k.startswith('[' + tipo + '_') for k in tabla)
                    codigo = f"[{tipo}_{self.datos['id']}_{numero:03d}]"
                    tabla[codigo] = valor
                if origen is not None:
                    fuentes = archivos.setdefault(codigo, [])
                    if origen not in fuentes:
                        fuentes.append(origen)
            self.guardar()

    def registrar_archivos(self, archivos):
        with self.lock:
            self.datos['archivos_caso'] = list(dict.fromkeys(str(Path(p).resolve()) for p in archivos))
            self.guardar()

    def estado_archivo(self, archivo):
        origen = Path(archivo).resolve()
        with self.lock:
            registro = self.datos.get('anonimizados', {}).get(str(origen), {})
            copias = dict(self.datos.get('copias', {}))
        try:
            firma_origen = hashlib.sha256(origen.read_bytes()).hexdigest()
            if firma_origen in copias.values():
                return 'Anonimizado'
            if registro.get('firma') != firma_origen:
                return 'No anonimizado'
            for nombre in registro.get('copias', []):
                try:
                    if hashlib.sha256(Path(nombre).read_bytes()).hexdigest() == copias.get(nombre):
                        return 'Anonimizado'
                except OSError:
                    continue
        except OSError:
            pass
        return 'No anonimizado'

    def recuperar_estados_archivos(self, archivos, carpetas=()):
        """Vincula copias anteriores comparando su texto restaurado con el original."""
        from analisis import extraer
        from docx import Document
        with self.lock:
            copias = dict(self.datos.get('copias', {}))
            fuentes = {str(Path(f).resolve()) for valores in self.datos.get('archivos', {}).values() for f in valores}
            vinculados = set(self.datos.get('anonimizados', {}))
        pendientes = [Path(p) for p in archivos
                      if str(Path(p).resolve()) in fuentes and str(Path(p).resolve()) not in vinculados]
        if not pendientes:
            return
        candidatos = {Path(p) for p in copias}
        for carpeta in carpetas:
            candidatos.update(Path(carpeta).glob('anonimizado_*.docx'))
        restaurados = {}
        for copia in candidatos:
            try:
                firma = hashlib.sha256(copia.read_bytes()).hexdigest()
                registrada = copias.get(str(copia.resolve()))
                if registrada is not None and firma != registrada:
                    continue
                doc = Document(copia)
                texto = '\n'.join(p.text for p in doc.paragraphs)
                limpio, _ = self.restaurar_texto(texto)
                restaurados.setdefault(' '.join(limpio.casefold().split()), []).append(copia)
            except (OSError, ValueError, KeyError):
                continue
            except Exception:
                # Un documento antiguo ilegible no impide abrir el caso.
                continue
        if not restaurados:
            return
        for origen in pendientes:
            # El PDF exportado combina el texto de cada página y su OCR.
            # El OCR puede variar entre ejecuciones: primero compara todas
            # las páginas con texto nativo contra la copia restaurada.
            coincidencias = []
            if origen.suffix.lower() == '.pdf':
                try:
                    import pymupdf
                    normalizar = lambda t: ''.join(c for c in t.casefold() if c.isalnum())
                    with pymupdf.open(origen) as doc:
                        paginas = [normalizar(p.get_text()) for p in doc]
                    if paginas and all(len(p) >= 100 for p in paginas):
                        for texto, rutas in restaurados.items():
                            contenido = normalizar(texto)
                            posicion = 0
                            for pagina in paginas:
                                inicio = contenido.find(pagina, posicion)
                                if inicio < 0:
                                    break
                                posicion = inicio + len(pagina)
                            else:
                                coincidencias.extend(rutas)
                except Exception:
                    pass
            if coincidencias:
                for copia in coincidencias:
                    self.registrar_copia(copia, copia, origen=origen)
                continue
            try:
                texto = ' '.join(extraer(origen).casefold().split())
            except Exception:
                continue
            for copia in restaurados.get(texto, []):
                self.registrar_copia(copia, copia, origen=origen)

    def registrar_copia(self, destino, preparada, origen=None):
        with self.lock:
            copias = self.datos.setdefault('copias', {})
            ruta = str(Path(destino).resolve())
            copias[ruta] = hashlib.sha256(Path(preparada).read_bytes()).hexdigest()
            if origen is not None:
                fuente = str(Path(origen).resolve())
                firma = hashlib.sha256(Path(origen).read_bytes()).hexdigest()
                registros = self.datos.setdefault('anonimizados', {})
                registro = registros.get(fuente, {})
                anteriores = registro.get('copias', []) if registro.get('firma') == firma else []
                registros[fuente] = {'firma': firma, 'copias': list(dict.fromkeys(anteriores + [ruta]))}
            self.guardar()

    def copia_para_actualizar(self, origen):
        with self.lock:
            registro = self.datos.get('anonimizados', {}).get(str(Path(origen).resolve()), {})
            for nombre in reversed(registro.get('copias', [])):
                ruta = Path(nombre)
                if not ruta.exists():
                    continue
                if ruta.resolve() == Path(origen).resolve():
                    raise ValueError('La copia no puede ser el original.')
                if hashlib.sha256(ruta.read_bytes()).hexdigest() != self.datos.get('copias', {}).get(nombre):
                    raise ValueError('La copia cambió fuera de la aplicación. No se reemplazó.')
                return ruta
        return None

    def publicar_copia(self, temporal, salida, origen, reemplazar=False):
        with self.lock:
            if reemplazar and self.copia_para_actualizar(origen) != Path(salida):
                raise ValueError('La copia que se iba a actualizar cambió.')
            anteriores = copy.deepcopy(self.datos)
            try:
                self.registrar_copia(salida, temporal, origen=origen)
                if reemplazar:
                    Path(temporal).replace(salida)
                else:
                    Path(temporal).rename(salida)
            except Exception:
                self.datos = anteriores
                self.guardar()
                raise

    def copias_para_eliminar(self, carpetas):
        originales = {Path(f).resolve() for fuentes in self.datos.get('archivos', {}).values() for f in fuentes}
        encontradas = set()
        for nombre, firma in self.datos.get('copias', {}).items():
            ruta = Path(nombre).resolve()
            if ruta in originales or not re.fullmatch(r'anonimizado_[a-f0-9]{12}\.docx', ruta.name):
                raise ValueError('El registro de copias no es válido.')
            if ruta.exists():
                if hashlib.sha256(ruta.read_bytes()).hexdigest() != firma:
                    raise ValueError('Una copia registrada cambió. Revisa el archivo antes de eliminar el caso.')
                encontradas.add(ruta)
        # Las versiones anteriores no registraban las rutas de salida. Solo se
        # reconocen sus copias neutrales con códigos conocidos de este caso.
        from docx import Document
        for carpeta in carpetas:
            for ruta in Path(carpeta).glob('anonimizado_*.docx'):
                ruta = ruta.resolve()
                if ruta in originales or ruta in encontradas or not re.fullmatch(r'anonimizado_[a-f0-9]{12}\.docx', ruta.name):
                    continue
                try:
                    doc = Document(ruta)
                    texto = '\n'.join(t.text or '' for t in doc.element.iter() if t.tag.endswith('}t'))
                    codigos = set(TOKEN.findall(texto))
                except Exception:
                    continue
                if codigos and codigos <= self.datos['equivalencias'].keys():
                    encontradas.add(ruta)
        return sorted(encontradas)

    def eliminar(self, copias):
        # La tabla se borra al final: si un archivo está abierto o falla el
        # borrado, se conserva la información necesaria para restaurar.
        for ruta in copias:
            Path(ruta).unlink(missing_ok=True)
        self.ruta.unlink()

    def sustituir(self, texto, terminos):
        from motor import coincidencias
        with self.lock:
            tabla = {v.casefold(): k for k, v in self.datos['equivalencias'].items()}
            spans = coincidencias(texto, [], terminos)
            for a, b in reversed(spans):
                codigo = tabla.get(texto[a:b].casefold())
                if codigo is None:
                    raise ValueError('Hay un dato seleccionado sin equivalencia local.')
                texto = texto[:a] + codigo + texto[b:]
            return texto, len(spans)

    def restaurar_texto(self, texto):
        encontrados = set(TOKEN.findall(texto))
        desconocidos = encontrados - self.datos['equivalencias'].keys()
        if desconocidos:
            raise ValueError('El fallo contiene códigos de otro caso o desconocidos. No se guardó.')
        # Detecta marcadores modificados o incompletos, sin sustituir parcialmente.
        resto = TOKEN.sub('', texto)
        if re.search(r"\[(?:PERSONA|CEDULA|CORREO|DATO|ANONIMIZADO)(?:_|\])", resto, re.I):
            raise ValueError('Hay códigos modificados o no restaurables. Revise el fallo.')
        if not encontrados:
            raise ValueError('No se encontraron códigos del caso. No se guardó.')
        return TOKEN.sub(lambda m: self.datos['equivalencias'][m.group()], texto), len(TOKEN.findall(texto))


def exportar(origen, destino, caso, terminos):
    from analisis import extraer
    from docx import Document
    texto = extraer(origen)
    # Nunca confundir marcadores que ya estaban en un documento de entrada.
    if TOKEN.search(texto):
        raise ValueError('El original ya contiene códigos de caso. Use el documento original.')
    limpio, cantidad = caso.sustituir(texto, terminos)
    doc = Document()
    for linea in limpio.splitlines():
        doc.add_paragraph(linea)
    doc.core_properties.author = ''
    doc.core_properties.last_modified_by = ''
    doc.save(destino)
    return cantidad


def restaurar_archivo(origen, destino, caso):
    from docx import Document
    from docx.oxml.ns import qn
    from motor import leer_texto
    origen, destino = Path(origen), Path(destino)
    if origen.resolve() == destino.resolve() or destino.exists():
        raise ValueError('Elija un archivo nuevo; se conserva el original.')
    if origen.suffix.lower() == '.docx':
        doc = Document(origen)
        raices = [doc.element.body]
        for seccion in doc.sections:
            for nombre in ('header', 'footer', 'first_page_header', 'first_page_footer', 'even_page_header', 'even_page_footer'):
                raices.append(getattr(seccion, nombre)._element)
        parrafos = []
        vistos = set()
        for raiz in raices:
            for parrafo in raiz.iter(qn('w:p')):
                if parrafo not in vistos:
                    vistos.add(parrafo)
                    parrafos.append(parrafo)
        textos = [''.join(t.text or '' for t in p.iter(qn('w:t'))) for p in parrafos]
        _, cantidad = caso.restaurar_texto('\n'.join(textos))
        for parrafo, texto in zip(parrafos, textos):
            if not TOKEN.search(texto):
                continue
            restaurado, _ = caso.restaurar_texto(texto)
            nodos = list(parrafo.iter(qn('w:t')))
            nodos[0].text = restaurado
            nodos[0].set(qn('xml:space'), 'preserve')
            for nodo in nodos[1:]:
                nodo.text = ''
        # Un DOCX reconstruido evita dejar códigos en comentarios, revisiones u objetos.
        nuevo = Document()
        for parrafo in parrafos:
            texto = ''.join(t.text or '' for t in parrafo.iter(qn('w:t')))
            nuevo.add_paragraph(texto)
        nuevo.core_properties.author = ''
        nuevo.core_properties.last_modified_by = ''
        nuevo.save(destino)
    elif origen.suffix.lower() in {'.txt', '.md'}:
        texto, cantidad = caso.restaurar_texto(leer_texto(origen))
        with destino.open('x', encoding='utf-8') as archivo:
            archivo.write(texto)
    else:
        raise ValueError('Descargue el fallo en DOCX, TXT o MD para restaurarlo.')
    return cantidad
