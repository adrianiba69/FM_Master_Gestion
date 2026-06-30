from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from services.notificacion_service import NotificacionService


class NotificacionesFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self._crear_interfaz()
        self.actualizar_notificaciones()

    def _crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text="CENTRO DE NOTIFICACIONES", font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))

        resumen = ctk.CTkFrame(self, fg_color="#1B1B1B", corner_radius=5)
        resumen.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.contadores = {}
        for columna, (clave, titulo, color) in enumerate((
            ("urgentes", "URGENTES", "#FF4D4D"),
            ("pendientes", "PENDIENTES", "#F4C542"),
            ("vencidas", "VENCIDAS", "#FF8C42"),
        )):
            resumen.grid_columnconfigure(columna, weight=1, uniform="alertas")
            tarjeta = ctk.CTkFrame(resumen, fg_color="#292929", corner_radius=4)
            tarjeta.grid(row=0, column=columna, sticky="nsew", padx=5, pady=8)
            ctk.CTkLabel(tarjeta, text=titulo, font=("Arial", 10, "bold"), text_color="#CCCCCC").pack(anchor="w", padx=12, pady=(8, 0))
            valor = ctk.CTkLabel(tarjeta, text="0", font=("Arial", 22, "bold"), text_color=color)
            valor.pack(anchor="w", padx=12, pady=(2, 8))
            self.contadores[clave] = valor

        filtros = ctk.CTkFrame(self, fg_color="white")
        filtros.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        filtros.grid_columnconfigure(3, weight=1)
        self.tipo = self._combo(filtros, 0, "Tipo", ["Todos"] + list(NotificacionService.TIPOS), 220)
        self.prioridad = self._combo(filtros, 1, "Prioridad", ["Todas"] + list(NotificacionService.PRIORIDADES), 130)
        self.estado = self._combo(filtros, 2, "Estado", ["Todos"] + list(NotificacionService.ESTADOS), 130)
        ctk.CTkButton(
            filtros, text="Actualizar", width=100, fg_color="#C00000",
            hover_color="#990000", command=self.actualizar_notificaciones,
        ).grid(row=1, column=3, sticky="e", padx=5)
        ctk.CTkButton(
            filtros, text="Limpiar filtros", width=110, fg_color="#555555",
            hover_color="#333333", command=self.limpiar_filtros,
        ).grid(row=1, column=4, padx=(5, 0))

        marco = ctk.CTkFrame(self, fg_color="white")
        marco.grid(row=3, column=0, sticky="nsew", padx=20)
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        columnas = ("id", "prioridad", "tipo", "titulo", "mensaje", "vencimiento", "estado")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings")
        encabezados = {
            "id": ("ID", 50), "prioridad": ("Prioridad", 85),
            "tipo": ("Tipo", 165), "titulo": ("Título", 250),
            "mensaje": ("Detalle", 360), "vencimiento": ("Vencimiento", 100),
            "estado": ("Estado", 90),
        }
        for clave, (titulo, ancho) in encabezados.items():
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=ancho, anchor="w", stretch=clave in ("titulo", "mensaje"))
        self.tabla.tag_configure("urgente", foreground="#C00000")
        self.tabla.tag_configure("alta", foreground="#D05A00")
        self.tabla.tag_configure("resuelta", foreground="#777777")
        self.tabla.tag_configure("descartada", foreground="#999999")
        self.tabla.bind("<Double-1>", lambda _e: self.marcar_leida())
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=4, column=0, sticky="ew", padx=20, pady=16)
        ctk.CTkButton(
            acciones, text="Marcar como leída", width=145, fg_color="#444444",
            hover_color="#222222", command=self.marcar_leida,
        ).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(
            acciones, text="Marcar como resuelta", width=160, fg_color="#16823A",
            hover_color="#0E5C28", command=self.marcar_resuelta,
        ).grid(row=0, column=1, padx=6)
        ctk.CTkButton(
            acciones, text="Descartar", width=110, fg_color="#7A0000",
            hover_color="#550000", command=self.descartar,
        ).grid(row=0, column=2, padx=6)

    @staticmethod
    def _combo(master, columna, titulo, valores, ancho):
        ctk.CTkLabel(master, text=titulo, font=("Arial", 10, "bold")).grid(
            row=0, column=columna, sticky="w", padx=4
        )
        combo = ctk.CTkComboBox(master, values=valores, width=ancho)
        combo.grid(row=1, column=columna, sticky="w", padx=4)
        combo.set(valores[0])
        return combo

    def actualizar_notificaciones(self):
        try:
            NotificacionService.generar_automaticas()
            filas = NotificacionService.listar(
                tipo=self.tipo.get(), prioridad=self.prioridad.get(), estado=self.estado.get()
            )
        except Exception as error:
            messagebox.showerror("Notificaciones", f"No se pudieron actualizar las alertas.\n{error}", parent=self)
            return
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        for fila in filas:
            tags = []
            if fila[4] in ("Urgente", "Alta"):
                tags.append(fila[4].lower())
            if fila[5] in ("Resuelta", "Descartada"):
                tags.append(fila[5].lower())
            self.tabla.insert("", "end", values=(
                fila[0], fila[4], fila[1], fila[2], fila[3],
                self.formatear_fecha(fila[7]), fila[5],
            ), tags=tuple(tags))
        datos = NotificacionService.resumen_dashboard()
        for clave, valor in datos.items():
            self.contadores[clave].configure(text=str(valor))

    def limpiar_filtros(self):
        self.tipo.set("Todos")
        self.prioridad.set("Todas")
        self.estado.set("Todos")
        self.actualizar_notificaciones()

    def marcar_leida(self):
        self._aplicar_estado(NotificacionService.marcar_leida, "marcar como leída")

    def marcar_resuelta(self):
        self._aplicar_estado(NotificacionService.marcar_resuelta, "marcar como resuelta")

    def descartar(self):
        self._aplicar_estado(NotificacionService.descartar, "descartar")

    def _aplicar_estado(self, accion, descripcion):
        notificacion_id = self.obtener_id_seleccionado()
        if notificacion_id is None:
            messagebox.showwarning("Notificaciones", "Seleccione una notificación.", parent=self)
            return
        if not accion(notificacion_id):
            messagebox.showwarning(
                "Notificaciones", f"La notificación no se puede {descripcion} en su estado actual.", parent=self
            )
        self.actualizar_notificaciones()

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        valores = self.tabla.item(seleccion[0], "values") if seleccion else ()
        return int(valores[0]) if valores else None

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""
