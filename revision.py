"""Revisión local de propuestas antes de autorizar la escritura de resultados."""
import io
import secrets
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageTk
from estilo import configurar_estilos

DATOS_PERSONALES_AUTOMATICOS = frozenset({
    'PERSONA', 'NOMBRE_FORMULARIO', 'PROFESIONAL', 'DOCUMENTO', 'IDENTIFICACION', 'DATO',
})


def draw_redaction(draw, box):
    """Preview the same dark gray redaction used in the exported file."""
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return
    draw.rectangle(box, fill='#404040')


class ReviewWindow(tk.Toplevel):
    def __init__(self, parent, plans, on_approve):
        super().__init__(parent)
        configurar_estilos(self)
        self.restoring = all(getattr(plan, 'purpose', '') == 'restore_fields' for plan in plans)
        self.title('Revisar campos para restaurar en el fallo' if self.restoring else 'Revisar y autorizar anonimización · 2026.11.17.7')
        width, height = min(1200, self.winfo_screenwidth()-80), min(820, self.winfo_screenheight()-90)
        self.geometry(f'{width}x{height}+25+25')
        self.minsize(min(900, width), min(650, height))
        self.plans, self.on_approve = plans, on_approve
        self.rows, self.chosen = {}, set()
        self.row_locations = {}
        self.photo = None
        self.current = None
        self.image_geometry = None
        self.drag_start = None
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Revisa los datos que se cargarán al fallo' if self.restoring else 'Revisa qué se va a anonimizar', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
        instruction = ('Todavía no se ha guardado ningún resultado. Marca cada dato que autorizas restaurar.' if self.restoring else
                       'Solo se proponen nombres propios de personas e identificaciones. Quedan marcados automáticamente; puede desmarcarlos antes de generar.')
        ttk.Label(frame, text=instruction, wraplength=1050).pack(anchor='w', pady=5)
        tools = ttk.Frame(frame)
        tools.pack(fill='x', pady=5)
        ttk.Button(tools, text='Marcar todos', command=lambda: self.mark_all(True)).pack(side='left')
        ttk.Button(tools, text='Desmarcar todos', command=lambda: self.mark_all(False)).pack(side='left', padx=6)
        self.counter = tk.StringVar()
        ttk.Label(tools, textvariable=self.counter).pack(side='left', padx=10)
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill='both', expand=True)
        self.table = ttk.Treeview(table_frame, columns=('allow', 'kind', 'value', 'where'), show='headings', height=6)
        self.table.tag_configure('autorizado', background='#e4f2e8', foreground='#164526')
        for key, text, width in [('allow', 'Autorizar', 70), ('kind', 'Tipo', 110), ('value', 'Dato que se ocultará', 300), ('where', 'Archivo / ubicación', 450)]:
            if key == 'value' and self.restoring:
                text = 'Código que se restaurará'
            self.table.heading(key, text=text)
            self.table.column(key, width=width, stretch=key != 'allow')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=self.table.xview)
        self.table.configure(xscrollcommand=horizontal.set)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.grid(row=0, column=0, sticky='nsew')
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.table.bind('<Button-1>', self.click)
        self.table.bind('<space>', self.toggle_current)
        self.table.bind('<<TreeviewSelect>>', self.show_selected)
        for index, plan in enumerate(plans):
            for finding in plan.findings.values():
                self.add_row(index, finding['id'], finding['kind'], finding['value'], finding['location'])
            if not plan.findings:
                action = 'PDF sustituto: omitir TODO el contenido' if any('PDF sustituto' in w for w in plan.warnings) else 'Generar copia sin datos detectados; revisar texto reconocido'
                self.add_row(index, None, 'SIN HALLAZGOS', action, 'Archivo completo')
            found_locations = {finding['location'] for finding in plan.findings.values()}
            for location, evidence in plan.evidence.items():
                if evidence.get('image') and location not in found_locations:
                    self.add_row(index, None, 'REVISAR PÁGINA', 'Sin propuestas automáticas; revise el texto reconocido', location)
        if not self.restoring:
            for row, (index, identity) in self.rows.items():
                finding = plans[index].findings.get(identity, {})
                if finding.get('kind') in DATOS_PERSONALES_AUTOMATICOS or finding.get('kind') == 'ZONA':
                    self.toggle(row, redraw=False)
        self.update_counter()
        notebook = ttk.Notebook(frame)
        notebook.pack(fill='both', expand=True, pady=8)
        text_frame, image_frame = ttk.Frame(notebook), ttk.Frame(notebook)
        notebook.add(text_frame, text='Contexto y texto reconocido')
        self.approve_button = ttk.Button(notebook, text='Generar anonimizado',
                                         command=self.approve, style='Principal.TButton')
        self.approve_button.place(relx=1, x=-4, y=1, anchor='ne')
        self.context = tk.Text(text_frame, height=6, wrap='word', font=('Segoe UI', 10))
        text_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=self.context.yview)
        self.context.configure(yscrollcommand=text_scroll.set)
        text_scroll.pack(side='right', fill='y')
        self.context.pack(side='left', fill='both', expand=True)
        self.context.tag_configure('match', background='#ffe180', foreground='#111111')
        zoom_bar = ttk.Frame(image_frame)
        zoom_bar.pack(fill='x')
        ttk.Label(zoom_bar, text='Arrastre sobre toda la firma: la zona dibujada queda autorizada').pack(side='left')
        self.zoom = tk.DoubleVar(value=1)
        ttk.Scale(zoom_bar, from_=1, to=6, variable=self.zoom,
                  command=lambda value: self.draw_image()).pack(side='left', fill='x', expand=True)
        image_view = ttk.Frame(image_frame)
        image_view.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(image_view, background='#dbe2e8', height=190)
        vscroll = ttk.Scrollbar(image_view, orient='vertical', command=self.canvas.yview)
        hscroll = ttk.Scrollbar(image_view, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        vscroll.pack(side='right', fill='y')
        hscroll.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.draw_image())
        self.canvas.bind('<ButtonPress-1>', self.start_region)
        self.canvas.bind('<B1-Motion>', self.drag_region)
        self.canvas.bind('<ButtonRelease-1>', self.finish_region)
        ttk.Label(frame, text='Seleccione cada aparición que autoriza restaurar. Las demás conservarán su código.' if self.restoring else 'Revise los datos y marque los que autoriza anonimizar.', wraplength=1050).pack(anchor='w')
        bottom = ttk.Frame(frame)
        bottom.pack(fill='x', pady=(10, 0))
        ttk.Button(bottom, text='Cancelar sin generar archivos', command=self.cancel).pack(side='left')
        if self.rows:
            first = next(iter(self.rows))
            self.table.selection_set(first)
            self.show_selected()
        self.transient(parent)
        self.grab_set()

    def add_row(self, plan_index, finding_id, kind, value, location):
        row = self.table.insert('', 'end', values=('☐', kind, value, self.plans[plan_index].path.name + ' / ' + location))
        self.rows[row] = (plan_index, finding_id)
        self.row_locations[row] = location

    def update_counter(self):
        self.counter.set(f'{len(self.chosen)} de {len(self.rows)} propuestas autorizadas')

    def toggle(self, row, redraw=True):
        if row in self.chosen:
            self.chosen.remove(row)
        else:
            self.chosen.add(row)
        self.table.set(row, 'allow', '☑' if row in self.chosen else '☐')
        self.table.item(row, tags=('autorizado',) if row in self.chosen else ())
        self.update_counter()
        if redraw:
            self.draw_image()

    def click(self, event):
        row = self.table.identify_row(event.y)
        if row and self.table.identify_column(event.x) == '#1':
            self.toggle(row)

    def toggle_current(self, event=None):
        for row in self.table.selection():
            self.toggle(row)
        return 'break'

    def mark_all(self, selected):
        for row in self.rows:
            if (row in self.chosen) != selected:
                self.toggle(row, redraw=False)
        self.draw_image()

    def show_selected(self, event=None):
        selection = self.table.selection()
        if not selection:
            return
        index, finding_id = self.rows[selection[0]]
        plan = self.plans[index]
        finding = plan.findings.get(finding_id)
        evidence = plan.evidence.get(finding['location']) if finding else None
        if not finding:
            evidence = plan.evidence.get(self.row_locations[selection[0]])
            if evidence is None:
                evidence = next((item for item in plan.evidence.values() if item.get('image')), None)
        self.current = (evidence, finding)
        self.context.configure(state='normal')
        self.context.delete('1.0', 'end')
        if finding:
            proposal = f"Restaurar dato original: {finding['token']}" if self.restoring else f"Ocultar en imagen/PDF o sustituir por {finding['token']} en texto."
            self.context.insert('end', f"Archivo: {plan.path.name}\nUbicación: {finding['location']}\nDato: {finding['value']}\nPropuesta: {proposal}\n\nCONTEXTO:\n{finding['context']}\n\n")
        else:
            self.context.insert('end', 'No se encontraron coincidencias. Revise el texto reconocido y añada los datos que desea ocultar.\n\n')
        texts = [evidence] if finding and evidence else list(plan.evidence.values())
        for item in texts:
            self.context.insert('end', 'TEXTO LEÍDO:\n' + item['text'] + '\n\n')
        if finding:
            start = '1.0'
            while True:
                position = self.context.search(finding['value'], start, stopindex='end', nocase=True)
                if not position:
                    break
                end = f'{position}+{len(finding["value"])}c'
                self.context.tag_add('match', position, end)
                start = end
        self.context.configure(state='disabled')
        self.draw_image()

    def get_preview_image(self):
        """Preview the selected redactions rather than the unmodified scan."""
        evidence, finding = self.current
        image = Image.open(io.BytesIO(evidence['image'])).convert('RGB')
        if self.restoring:
            return image
        selection = self.table.selection()
        if not selection:
            return image
        index, _ = self.rows[selection[0]]
        plan = self.plans[index]
        location = next(key for key, item in plan.evidence.items() if item is evidence)
        drawing = ImageDraw.Draw(image)
        for row in self.chosen:
            plan_index, identity = self.rows[row]
            selected = plan.findings.get(identity)
            if plan_index != index or not selected or selected['location'] != location:
                continue
            if selected.get('box'):
                draw_redaction(drawing, selected['box'])
            else:
                for a, b, (x0, y0, x1, y1), _ in evidence['words']:
                    if selected['start'] < b and selected['stop'] > a:
                        draw_redaction(drawing, (max(0, x0-2), max(0, y0-2), min(image.width-1, x1+2), min(image.height-1, y1+2)))
        return image

    def draw_image(self):
        self.canvas.delete('all')
        self.image_geometry = None
        if not self.current or not self.current[0] or not self.current[0].get('image'):
            self.canvas.create_text(20, 20, anchor='nw', text='La ubicación y el contexto de este dato se muestran en la pestaña de texto.')
            return
        evidence, finding = self.current
        image = self.get_preview_image()
        original_size = image.size
        if finding:
            draw = ImageDraw.Draw(image)
            if finding.get('box'):
                draw.rounded_rectangle(finding['box'], radius=4, outline='#147d74', width=max(2, image.width // 500))
            for a, b, box, _ in evidence['words']:
                if finding['start'] < b and finding['stop'] > a:
                    draw.rounded_rectangle(box, radius=3, outline='#147d74', width=max(2, image.width // 500))
        zoom = self.zoom.get()
        image.thumbnail((max(100, int((self.canvas.winfo_width()-20)*zoom)), max(100, int((self.canvas.winfo_height()-20)*zoom))))
        self.image_geometry = (original_size, image.size)
        self.canvas.configure(scrollregion=(0, 0, image.width+20, image.height+20))
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.create_image(10, 10, image=self.photo, anchor='nw')

    def start_region(self, event):
        if self.image_geometry and not self.restoring:
            self.drag_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def drag_region(self, event):
        if self.drag_start:
            self.canvas.delete('selection')
            self.canvas.create_rectangle(*self.drag_start, self.canvas.canvasx(event.x), self.canvas.canvasy(event.y),
                                         outline='red', width=2, tags='selection')

    def finish_region(self, event):
        if not self.drag_start or not self.image_geometry:
            return
        x, y = self.drag_start
        self.drag_start = None
        (width, height), (shown_width, shown_height) = self.image_geometry
        x0, x1 = sorted((max(0, min(shown_width, x-10)), max(0, min(shown_width, self.canvas.canvasx(event.x)-10))))
        y0, y1 = sorted((max(0, min(shown_height, y-10)), max(0, min(shown_height, self.canvas.canvasy(event.y)-10))))
        if x1-x0 < 4 or y1-y0 < 4:
            self.canvas.delete('selection')
            return
        selected = self.table.selection()
        if not selected:
            return
        index, finding_id = self.rows[selected[0]]
        plan = self.plans[index]
        evidence = self.current[0]
        location = next(key for key, item in plan.evidence.items() if item is evidence)
        box = (int(x0*width/shown_width), int(y0*height/shown_height),
               min(width-1, int(x1*width/shown_width)+1), min(height-1, int(y1*height/shown_height)+1))
        if box[2]-box[0] < 8 or box[3]-box[1] < 8:
            self.canvas.delete('selection')
            messagebox.showinfo('Zona demasiado pequeña', 'Marque toda la zona que desea ocultar.', parent=self)
            return
        if finding_id and plan.findings.get(finding_id, {}).get('kind') == 'ZONA':
            plan.findings[finding_id]['box'] = box
            if selected[0] not in self.chosen:
                self.toggle(selected[0], redraw=False)
            self.canvas.delete('selection')
            self.show_selected()
            return
        identity = 'zona_' + secrets.token_hex(12)
        token = f'ANON_FIRMA_{plan.case_id}_{sum(f.get("kind") == "ZONA" for f in plan.findings.values()) + 1:04d}'
        plan.findings[identity] = {'id': identity, 'kind': 'ZONA', 'value': 'Sección de firma',
            'location': location, 'box': box, 'start': -1, 'stop': -1,
            'context': 'Se ocultará completamente el rectángulo dibujado al autorizar esta propuesta.',
            'token': token}
        for row, (row_index, row_id) in list(self.rows.items()):
            if row_index == index and row_id is None and self.row_locations[row] == location:
                self.chosen.discard(row)
                self.table.delete(row)
                del self.rows[row]
        self.add_row(index, identity, 'ZONA', 'Sección de firma', location)
        row = next(row for row, value in self.rows.items() if value == (index, identity))
        self.toggle(row, redraw=False)
        self.table.selection_set(row)
        self.table.see(row)
        self.update_counter()
        self.show_selected()

    def approve(self):
        if not self.chosen:
            messagebox.showinfo('Sin autorización', 'Marque las propuestas que desea autorizar.', parent=self)
            return
        approved = {}
        for row in self.chosen:
            index, finding_id = self.rows[row]
            approved.setdefault(index, set())
            if finding_id:
                approved[index].add(finding_id)
        self.grab_release()
        self.destroy()
        self.on_approve([(self.plans[index], ids) for index, ids in sorted(approved.items())])

    def cancel(self):
        self.master.status.set('Revisión cancelada. No se generaron archivos.')
        self.grab_release()
        self.destroy()
