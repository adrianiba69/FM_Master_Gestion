from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.servicio import Servicio
from services.servicio_service import ServicioService


class ServiciosWindow(ctk.CTkToplevel):

    def __init__(self, master, cliente_id, cliente_nombre):
        super().__init__(master)

        self.cliente_id = cliente_id
        self.cliente_nombre = cliente_nombre
        self.campos_formulario = {}
        self.activo_var = ctk.IntVar(value=1)
        self.renovable_var = ctk.IntVar(value=1)

        self.title(f"Servicios - {cliente_nombre}")
        self.geometry("1180x700")
        self.minsize(1000, 650)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.crear_interfaz()
        self.cargar_servicios()
        self.limpiar_formulario()

    def crear_interfaz(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        encabezado.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            encabezado,
            text=f"SERVICIOS DE {self.cliente_nombre.upper()}",
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w")

        self.total_label = ctk.CTkLabel(
            encabezado,
            text="Total activo: $ 0,00",
            font=("Arial", 16, "bold"),
            text_color="#111111",
        )
        self.total_label.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            self,
            text="Seleccione una fila para editarla o complete los datos para crear un servicio.",
            font=("Arial", 12),
            text_color="#555555",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        contenido = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        contenido.grid(row=2, column=0, sticky="nsew", padx=20)
        contenido.grid_rowconfigure(0, weight=1)
        contenido.grid_columnconfigure(0, weight=0, minsize=300)
        contenido.grid_columnconfigure(1, weight=1)

        formulario = ctk.CTkFrame(contenido, fg_color="#F3F3F3", corner_radius=4)
        formulario.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        formulario.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            formulario,
            text="Datos del servicio",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        campos = (
            ("concepto", "Concepto *"),
            ("descripcion", "Descripcion"),
            ("cantidad", "Cantidad"),
            ("importe", "Importe"),
            ("descuento", "Descuento"),
            ("fecha_inicio", "Fecha de inicio * (DD/MM/AAAA)"),
            ("fecha_fin", "Fecha de fin"),
        )
        for fila, (clave, etiqueta) in enumerate(campos, start=1):
            ctk.CTkLabel(formulario, text=etiqueta, anchor="w").grid(
                row=fila * 2 - 1,
                column=0,
                sticky="ew",
                padx=16,
                pady=(8, 0),
            )
            entrada = ctk.CTkEntry(formulario)
            entrada.grid(row=fila * 2, column=0, sticky="ew", padx=16)
            self.campos_formulario[clave] = entrada

        self.campos_formulario["fecha_inicio"].bind(
            "<KeyRelease>", lambda _evento: self.actualizar_fecha_fin_formulario()
        )
        self.campos_formulario["fecha_inicio"].bind(
            "<FocusOut>", lambda _evento: self.actualizar_fecha_fin_formulario()
        )
        self.campos_formulario["fecha_fin"].configure(state="disabled")

        self.check_activo = ctk.CTkCheckBox(
            formulario,
            text="Servicio activo",
            variable=self.activo_var,
            onvalue=1,
            offvalue=0,
            fg_color="#C00000",
            hover_color="#990000",
        )
        self.check_activo.grid(row=15, column=0, sticky="w", padx=16, pady=(18, 6))

        self.check_renovable = ctk.CTkCheckBox(
            formulario,
            text="Renovable",
            variable=self.renovable_var,
            onvalue=1,
            offvalue=0,
            fg_color="#C00000",
            hover_color="#990000",
        )
        self.check_renovable.grid(row=16, column=0, sticky="w", padx=16, pady=(4, 14))

        tabla_frame = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=0, column=1, sticky="nsew")
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = (
            "id", "concepto", "cantidad", "total", "inicio", "fin",
            "renovable", "estado_periodo", "activo",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=15)
        encabezados = {
            "id": ("ID", 48),
            "concepto": ("Concepto", 210),
            "cantidad": ("Cantidad", 75),
            "total": ("Total", 105),
            "inicio": ("Inicio", 95),
            "fin": ("Fin", 95),
            "renovable": ("Renovable", 80),
            "estado_periodo": ("Periodo", 90),
            "activo": ("Activo", 60),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                anchor="w" if columna == "concepto" else "center",
                stretch=columna == "concepto",
            )

        self.tabla.bind("<<TreeviewSelect>>", self.cargar_seleccion_en_formulario)
        self.tabla.bind("<Double-1>", self.cargar_seleccion_en_formulario)
        self.tabla.tag_configure("vencido", foreground="#C00000")

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(tabla_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=3, column=0, sticky="ew", padx=20, pady=18)
        acciones.grid_columnconfigure(5, weight=1)

        self.boton_guardar = ctk.CTkButton(
            acciones,
            text="Guardar",
            width=125,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.guardar_servicio,
        )
        self.boton_guardar.grid(row=0, column=0, padx=(0, 8))

        self.boton_modificar = ctk.CTkButton(
            acciones,
            text="Modificar",
            width=125,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_servicio,
        )
        self.boton_modificar.grid(row=0, column=1, padx=8)

        self.boton_eliminar = ctk.CTkButton(
            acciones,
            text="Eliminar",
            width=125,
            height=38,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_servicio_seleccionado,
        )
        self.boton_eliminar.grid(row=0, column=2, padx=8)

        self.boton_renovar = ctk.CTkButton(
            acciones,
            text="Renovar periodo",
            width=140,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.renovar_periodo,
        )
        self.boton_renovar.grid(row=0, column=3, padx=8)

        self.boton_limpiar = ctk.CTkButton(
            acciones,
            text="Limpiar",
            width=145,
            height=38,
            fg_color="#555555",
            hover_color="#333333",
            command=self.limpiar_formulario,
        )
        self.boton_limpiar.grid(row=0, column=4, padx=8)

        self.boton_cerrar = ctk.CTkButton(
            acciones,
            text="Cerrar",
            width=110,
            height=38,
            fg_color="#666666",
            hover_color="#444444",
            command=self.destroy,
        )
        self.boton_cerrar.grid(row=0, column=6, sticky="e")

    def cargar_servicios(self, seleccionar_id=None):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        item_seleccionado = None
        for servicio in ServicioService.listar(self.cliente_id):
            estado_periodo = servicio[12] or "Activo"
            item = self.tabla.insert(
                "",
                "end",
                values=(
                    servicio[0],
                    servicio[2],
                    self.formatear_numero(servicio[4]),
                    self.formatear_moneda(servicio[8]),
                    self.formatear_fecha(servicio[9]),
                    self.formatear_fecha(servicio[10]),
                    "Si" if servicio[11] else "No",
                    estado_periodo,
                    "Si" if servicio[7] else "No",
                ),
                tags=("vencido",)
                if estado_periodo in ("Vencido", "Finalizado")
                else (),
            )
            if servicio[0] == seleccionar_id:
                item_seleccionado = item

        if item_seleccionado:
            self.tabla.selection_set(item_seleccionado)
            self.tabla.focus(item_seleccionado)
            self.tabla.see(item_seleccionado)

        total_cliente = ServicioService.total_cliente(self.cliente_id)
        self.total_label.configure(
            text=f"Total activo: {self.formatear_moneda(total_cliente)}"
        )

    def guardar_servicio(self):
        servicio = self.obtener_servicio_formulario()
        if servicio is None:
            return

        nuevo_id = ServicioService.guardar(servicio)
        self.cargar_servicios(seleccionar_id=nuevo_id)
        self.limpiar_formulario(limpiar_seleccion=False)
        messagebox.showinfo(
            "Servicios",
            "Servicio creado correctamente.",
            parent=self,
        )

    def modificar_servicio(self):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            messagebox.showwarning("Atencion", "Seleccione un servicio para modificar.")
            return

        servicio = self.obtener_servicio_formulario(id_servicio=id_servicio)
        if servicio is None:
            return

        ServicioService.actualizar(servicio)
        self.cargar_servicios(seleccionar_id=id_servicio)
        messagebox.showinfo(
            "Servicios",
            "Servicio modificado correctamente.",
            parent=self,
        )

    def renovar_periodo(self):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            messagebox.showwarning("Atencion", "Seleccione un servicio para renovar.")
            return

        try:
            inicio, fin = ServicioService.renovar_periodo(id_servicio)
        except ValueError as error:
            messagebox.showerror("Renovacion", str(error), parent=self)
            return

        self.cargar_servicios(seleccionar_id=id_servicio)
        messagebox.showinfo(
            "Periodo renovado",
            f"Nuevo periodo: {self.formatear_fecha(inicio)} al {self.formatear_fecha(fin)}.",
            parent=self,
        )

    def eliminar_servicio_seleccionado(self):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            messagebox.showwarning("Atencion", "Seleccione un servicio para eliminar.")
            return

        valores = self.tabla.item(self.tabla.selection()[0], "values")
        if not messagebox.askyesno(
            "Confirmar eliminacion",
            f"Desea eliminar el servicio '{valores[1]}'?",
            parent=self,
        ):
            return

        ServicioService.eliminar(id_servicio)
        self.cargar_servicios()
        self.limpiar_formulario()

    def cargar_seleccion_en_formulario(self, _evento=None):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            return
        fila = ServicioService.obtener(id_servicio)
        if fila is None:
            self.cargar_servicios()
            return

        valores = {
            "concepto": fila[2] or "",
            "descripcion": fila[3] or "",
            "cantidad": self.formatear_numero(fila[4]),
            "importe": self.formatear_numero(fila[5]),
            "descuento": self.formatear_numero(fila[6]),
            "fecha_inicio": self.formatear_fecha(fila[8]),
            "fecha_fin": self.formatear_fecha(fila[9]),
        }
        for clave, valor in valores.items():
            self.establecer_campo(clave, valor)
        self.activo_var.set(1 if fila[7] else 0)
        self.renovable_var.set(1 if fila[10] else 0)
        self.boton_renovar.configure(state="normal" if fila[10] else "disabled")

    def limpiar_formulario(self, limpiar_seleccion=True):
        for clave in self.campos_formulario:
            self.establecer_campo(clave, "")
        self.establecer_campo("cantidad", "1")
        self.establecer_campo("importe", "0")
        self.establecer_campo("descuento", "0")
        self.establecer_campo("fecha_inicio", date.today().strftime("%d/%m/%Y"))
        self.actualizar_fecha_fin_formulario()
        self.activo_var.set(1)
        self.renovable_var.set(1)
        self.boton_renovar.configure(state="disabled")
        if limpiar_seleccion:
            self.tabla.selection_remove(self.tabla.selection())
        self.campos_formulario["concepto"].focus_set()

    def obtener_servicio_formulario(self, id_servicio=None):
        concepto = self.campos_formulario["concepto"].get().strip()
        if not concepto:
            messagebox.showerror("Error", "El concepto es obligatorio.", parent=self)
            return None

        try:
            cantidad = self.convertir_decimal(self.campos_formulario["cantidad"].get() or "1")
            importe = self.convertir_decimal(self.campos_formulario["importe"].get() or "0")
            descuento = self.convertir_decimal(self.campos_formulario["descuento"].get() or "0")
            fecha_inicio = datetime.strptime(
                self.campos_formulario["fecha_inicio"].get().strip(),
                "%d/%m/%Y",
            ).date()
        except ValueError:
            messagebox.showerror(
                "Error",
                "Ingrese valores numericos validos y una fecha DD/MM/AAAA.",
                parent=self,
            )
            return None

        if cantidad <= 0 or importe < 0 or descuento < 0:
            messagebox.showerror(
                "Error",
                "Cantidad debe ser mayor que cero; importe y descuento no pueden ser negativos.",
                parent=self,
            )
            return None

        return Servicio(
            id=id_servicio,
            cliente_id=self.cliente_id,
            concepto=concepto,
            descripcion=self.campos_formulario["descripcion"].get().strip(),
            cantidad=cantidad,
            importe=importe,
            descuento=descuento,
            activo=self.activo_var.get(),
            fecha_inicio=fecha_inicio.isoformat(),
            fecha_fin=ServicioService.sumar_un_mes(fecha_inicio).isoformat(),
            renovable=self.renovable_var.get(),
            estado_periodo="Activo",
        )

    def actualizar_fecha_fin_formulario(self):
        try:
            inicio = datetime.strptime(
                self.campos_formulario["fecha_inicio"].get().strip(),
                "%d/%m/%Y",
            ).date()
        except ValueError:
            self.establecer_campo("fecha_fin", "")
            return
        fin = ServicioService.sumar_un_mes(inicio)
        self.establecer_campo("fecha_fin", fin.strftime("%d/%m/%Y"))

    def establecer_campo(self, clave, valor):
        entrada = self.campos_formulario[clave]
        estado_anterior = entrada.cget("state")
        if estado_anterior == "disabled":
            entrada.configure(state="normal")
        entrada.delete(0, "end")
        entrada.insert(0, valor)
        if estado_anterior == "disabled":
            entrada.configure(state="disabled")

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None
        valores = self.tabla.item(seleccion[0], "values")
        return int(valores[0]) if valores else None

    @staticmethod
    def convertir_decimal(valor):
        normalizado = valor.strip().replace("$", "").replace(" ", "")
        if "," in normalizado and "." in normalizado:
            normalizado = normalizado.replace(".", "").replace(",", ".")
        else:
            normalizado = normalizado.replace(",", ".")
        return float(normalizado)

    @staticmethod
    def formatear_numero(valor):
        return f"{float(valor or 0):.2f}"

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
