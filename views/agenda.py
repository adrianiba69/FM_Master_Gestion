from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.tarea import Tarea
from services.cliente_service import ClienteService
from services.tarea_service import TareaService


class AgendaFrame(ctk.CTkFrame):

    def __init__(self, master, cliente_id=None, abrir_nueva=False):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.cliente_inicial = cliente_id
        self.clientes_por_nombre = {}
        self.campos_formulario = {}
        self.crear_interfaz()
        self.cargar_clientes()
        self.cargar_tareas()
        if abrir_nueva:
            self.after(150, self.abrir_nueva_tarea)

    def crear_interfaz(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="AGENDA COMERCIAL",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        filtros = ctk.CTkFrame(self, fg_color="#F3F3F3", corner_radius=4)
        filtros.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        filtros.grid_columnconfigure(2, weight=1)

        self.filtro_segmentado = ctk.CTkSegmentedButton(
            filtros,
            values=["Todas", "Hoy", "Mañana", "Esta semana", "Vencidas"],
            command=lambda _valor: self.cargar_tareas(),
            selected_color="#C00000",
            selected_hover_color="#990000",
        )
        self.filtro_segmentado.grid(row=0, column=0, padx=12, pady=12)
        self.filtro_segmentado.set("Todas")

        self.selector_cliente = ctk.CTkComboBox(
            filtros,
            values=["Todos los clientes"],
            width=245,
            command=lambda _valor: self.cargar_tareas(),
        )
        self.selector_cliente.grid(row=0, column=1, padx=(0, 10), pady=12)

        self.entrada_buscar = ctk.CTkEntry(
            filtros,
            placeholder_text="Buscar tareas...",
            width=220,
        )
        self.entrada_buscar.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=12)
        self.entrada_buscar.bind("<Return>", lambda _evento: self.cargar_tareas())
        ctk.CTkButton(
            filtros,
            text="Buscar",
            width=85,
            height=36,
            command=self.cargar_tareas,
        ).grid(row=0, column=3, padx=(0, 12), pady=12)

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        acciones.grid_columnconfigure(4, weight=1)
        self.boton_nueva = ctk.CTkButton(
            acciones,
            text="Nuevo",
            width=120,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_nueva_tarea,
        )
        self.boton_nueva.grid(row=0, column=0, padx=(0, 8))
        self.boton_modificar = ctk.CTkButton(
            acciones,
            text="Modificar",
            width=110,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_tarea_seleccionada,
        )
        self.boton_modificar.grid(row=0, column=1, padx=8)
        self.boton_eliminar = ctk.CTkButton(
            acciones,
            text="Eliminar",
            width=105,
            height=38,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_tarea_seleccionada,
        )
        self.boton_eliminar.grid(row=0, column=2, padx=8)
        self.boton_completar = ctk.CTkButton(
            acciones,
            text="Marcar completada",
            width=155,
            height=38,
            fg_color="#167A45",
            hover_color="#105C34",
            command=self.completar_tarea_seleccionada,
        )
        self.boton_completar.grid(row=0, column=3, padx=8)

        self.conteo_label = ctk.CTkLabel(
            self,
            text="",
            font=("Arial", 12, "bold"),
            text_color="#555555",
        )
        self.conteo_label.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 5))

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = (
            "id", "fecha", "hora", "cliente", "tipo", "titulo",
            "estado", "prioridad",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=17)
        encabezados = {
            "id": ("ID", 45),
            "fecha": ("Fecha", 90),
            "hora": ("Hora", 60),
            "cliente": ("Cliente", 190),
            "tipo": ("Tipo", 140),
            "titulo": ("Título", 230),
            "estado": ("Estado", 100),
            "prioridad": ("Prioridad", 80),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna in ("cliente", "titulo"),
            )
        self.tabla.tag_configure("vencida", foreground="#C00000")
        self.tabla.tag_configure("hoy", foreground="#9A6A00")
        self.tabla.tag_configure("completada", foreground="#138A43")
        self.tabla.bind("<Double-1>", lambda _evento: self.modificar_tarea_seleccionada())
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def cargar_clientes(self):
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {
            f"{cliente[1] or '-'} - {cliente[2]}": cliente[0]
            for cliente in clientes
        }
        nombres = ["Todos los clientes", *self.clientes_por_nombre]
        self.selector_cliente.configure(values=nombres)
        seleccionado = next(
            (nombre for nombre, cliente_id in self.clientes_por_nombre.items()
             if cliente_id == self.cliente_inicial),
            "Todos los clientes",
        )
        self.selector_cliente.set(seleccionado)

    def cargar_tareas(self):
        filtro = self.filtro_segmentado.get() or "Todas"
        cliente_id = self.clientes_por_nombre.get(self.selector_cliente.get())
        texto = self.entrada_buscar.get().strip()
        tareas = TareaService.listar(filtro, cliente_id, texto)
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        ahora = datetime.now()
        for tarea in tareas:
            fecha_hora = datetime.strptime(f"{tarea[2]} {tarea[3]}", "%Y-%m-%d %H:%M")
            if tarea[7] == "Completada":
                tag = "completada"
            elif fecha_hora < ahora and tarea[7] not in ("Completada", "Cancelada"):
                tag = "vencida"
            elif tarea[2] == date.today().isoformat():
                tag = "hoy"
            else:
                tag = ""
            self.tabla.insert(
                "",
                "end",
                values=(
                    tarea[0], self.formatear_fecha(tarea[2]), tarea[3], tarea[10],
                    tarea[4], tarea[5], tarea[7], tarea[8],
                ),
                tags=(tag,) if tag else (),
            )
        self.conteo_label.configure(text=f"Tareas: {len(tareas)}")

    def abrir_nueva_tarea(self):
        self.abrir_formulario("Nueva tarea", None)

    def modificar_tarea_seleccionada(self):
        tarea_id = self.obtener_id_seleccionado()
        if tarea_id is None:
            messagebox.showwarning("Agenda", "Seleccione una tarea para modificar.")
            return
        fila = TareaService.obtener(tarea_id)
        if fila is None:
            messagebox.showerror("Agenda", "No se encontró la tarea seleccionada.")
            self.cargar_tareas()
            return
        self.abrir_formulario("Modificar tarea", Tarea(*fila))

    def eliminar_tarea_seleccionada(self):
        tarea_id = self.obtener_id_seleccionado()
        if tarea_id is None:
            messagebox.showwarning("Agenda", "Seleccione una tarea para eliminar.")
            return
        if not messagebox.askyesno(
            "Eliminar tarea",
            "¿Desea eliminar la tarea seleccionada?",
            parent=self,
        ):
            return
        TareaService.eliminar(tarea_id)
        self.cargar_tareas()

    def completar_tarea_seleccionada(self):
        tarea_id = self.obtener_id_seleccionado()
        if tarea_id is None:
            messagebox.showwarning("Agenda", "Seleccione una tarea para completar.")
            return
        TareaService.marcar_completada(tarea_id)
        self.cargar_tareas()
        messagebox.showinfo(
            "Agenda",
            "Tarea marcada como completada.",
            parent=self,
        )

    def abrir_formulario(self, titulo, tarea=None):
        ventana = ctk.CTkToplevel(self)
        ventana.title(titulo)
        ventana.geometry("650x720")
        ventana.minsize(580, 650)
        ventana.resizable(False, False)
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        contenido = ctk.CTkScrollableFrame(ventana, fg_color="white")
        contenido.pack(fill="both", expand=True, padx=20, pady=20)
        contenido.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            contenido,
            text=titulo.upper(),
            font=("Arial", 21, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        nombres_clientes = ["Sin cliente", *self.clientes_por_nombre]
        ctk.CTkLabel(contenido, text="Cliente", anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )
        self.form_cliente = ctk.CTkComboBox(contenido, values=nombres_clientes)
        self.form_cliente.grid(row=2, column=0, sticky="ew")

        campos = (("fecha", "Fecha (DD/MM/AAAA)"), ("hora", "Hora (HH:MM)"), ("titulo", "Título *"))
        self.campos_formulario = {}
        fila_actual = 3
        for clave, etiqueta in campos:
            ctk.CTkLabel(contenido, text=etiqueta, anchor="w").grid(
                row=fila_actual, column=0, sticky="ew", pady=(7, 0)
            )
            entrada = ctk.CTkEntry(contenido)
            entrada.grid(row=fila_actual + 1, column=0, sticky="ew")
            self.campos_formulario[clave] = entrada
            fila_actual += 2

        ctk.CTkLabel(contenido, text="Tipo", anchor="w").grid(
            row=9, column=0, sticky="ew", pady=(7, 0)
        )
        self.form_tipo = ctk.CTkComboBox(contenido, values=list(TareaService.TIPOS))
        self.form_tipo.grid(row=10, column=0, sticky="ew")
        ctk.CTkLabel(contenido, text="Estado", anchor="w").grid(
            row=11, column=0, sticky="ew", pady=(7, 0)
        )
        self.form_estado = ctk.CTkComboBox(contenido, values=list(TareaService.ESTADOS))
        self.form_estado.grid(row=12, column=0, sticky="ew")
        ctk.CTkLabel(contenido, text="Prioridad", anchor="w").grid(
            row=13, column=0, sticky="ew", pady=(7, 0)
        )
        self.form_prioridad = ctk.CTkComboBox(contenido, values=list(TareaService.PRIORIDADES))
        self.form_prioridad.grid(row=14, column=0, sticky="ew")
        ctk.CTkLabel(contenido, text="Descripción", anchor="w").grid(
            row=15, column=0, sticky="ew", pady=(7, 0)
        )
        self.form_descripcion = ctk.CTkTextbox(contenido, height=85)
        self.form_descripcion.grid(row=16, column=0, sticky="ew")

        if tarea is None:
            nombre_cliente = next(
                (nombre for nombre, cliente_id in self.clientes_por_nombre.items()
                 if cliente_id == self.cliente_inicial),
                "Sin cliente",
            )
            self.form_cliente.set(nombre_cliente)
            self.campos_formulario["fecha"].insert(0, date.today().strftime("%d/%m/%Y"))
            self.campos_formulario["hora"].insert(0, datetime.now().strftime("%H:%M"))
            self.form_tipo.set(TareaService.TIPOS[0])
            self.form_estado.set("Pendiente")
            self.form_prioridad.set("Media")
        else:
            nombre_cliente = next(
                (nombre for nombre, cliente_id in self.clientes_por_nombre.items()
                 if cliente_id == tarea.cliente_id),
                "Sin cliente",
            )
            self.form_cliente.set(nombre_cliente)
            self.campos_formulario["fecha"].insert(0, self.formatear_fecha(tarea.fecha))
            self.campos_formulario["hora"].insert(0, tarea.hora)
            self.campos_formulario["titulo"].insert(0, tarea.titulo)
            self.form_tipo.set(tarea.tipo)
            self.form_estado.set(tarea.estado)
            self.form_prioridad.set(tarea.prioridad)
            self.form_descripcion.insert("1.0", tarea.descripcion or "")

        ctk.CTkButton(
            contenido,
            text="Guardar",
            height=40,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.guardar_formulario(ventana, tarea),
        ).grid(row=17, column=0, sticky="ew", pady=(18, 8))
        self.campos_formulario["titulo"].focus_set()

    def guardar_formulario(self, ventana, tarea_original=None):
        try:
            fecha = datetime.strptime(
                self.campos_formulario["fecha"].get().strip(), "%d/%m/%Y"
            ).date()
            hora = datetime.strptime(
                self.campos_formulario["hora"].get().strip(), "%H:%M"
            ).strftime("%H:%M")
        except ValueError:
            messagebox.showerror("Agenda", "La fecha o la hora no son válidas.", parent=ventana)
            return
        tarea = Tarea(
            id=tarea_original.id if tarea_original else None,
            cliente_id=self.clientes_por_nombre.get(self.form_cliente.get()),
            fecha=fecha.isoformat(),
            hora=hora,
            tipo=self.form_tipo.get(),
            titulo=self.campos_formulario["titulo"].get().strip(),
            descripcion=self.form_descripcion.get("1.0", "end").strip(),
            estado=self.form_estado.get(),
            prioridad=self.form_prioridad.get(),
            fecha_creacion=tarea_original.fecha_creacion if tarea_original else "",
        )
        try:
            if tarea_original:
                TareaService.actualizar(tarea)
            else:
                TareaService.guardar(tarea)
        except ValueError as error:
            messagebox.showerror("Agenda", str(error), parent=ventana)
            return
        ventana.destroy()
        self.cargar_tareas()
        messagebox.showinfo(
            "Agenda",
            "Tarea modificada correctamente."
            if tarea_original
            else "Tarea creada correctamente.",
            parent=self,
        )

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None
        valores = self.tabla.item(seleccion[0], "values")
        return int(valores[0]) if valores else None

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""
