from tkinter import messagebox, ttk

import customtkinter as ctk

from models.servicio import Servicio
from services.servicio_service import ServicioService


class ServiciosWindow(ctk.CTkToplevel):

    CAMPOS_FORMULARIO = [
        ("concepto", "Concepto *"),
        ("descripcion", "Descripcion"),
        ("cantidad", "Cantidad"),
        ("importe", "Importe"),
        ("descuento", "Descuento"),
        ("activo", "Activo"),
    ]

    def __init__(self, master, cliente_id, cliente_nombre):
        super().__init__(master)

        self.cliente_id = cliente_id
        self.cliente_nombre = cliente_nombre
        self.campos_formulario = {}

        self.title(f"Servicios - {cliente_nombre}")
        self.geometry("850x560")
        self.minsize(760, 500)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.crear_interfaz()
        self.cargar_servicios()

    def crear_interfaz(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text=f"Servicios de {self.cliente_nombre}",
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        barra = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        barra.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        barra.grid_columnconfigure(3, weight=1)

        boton_agregar = ctk.CTkButton(
            barra,
            text="+ Agregar",
            width=120,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_formulario_agregar,
        )
        boton_agregar.grid(row=0, column=0, padx=(0, 10))

        boton_modificar = ctk.CTkButton(
            barra,
            text="Modificar",
            width=120,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_servicio_seleccionado,
        )
        boton_modificar.grid(row=0, column=1, padx=(0, 10))

        boton_eliminar = ctk.CTkButton(
            barra,
            text="Eliminar",
            width=120,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_servicio_seleccionado,
        )
        boton_eliminar.grid(row=0, column=2, padx=(0, 10))

        self.total_label = ctk.CTkLabel(
            barra,
            text="Total activo: $0.00",
            font=("Arial", 15, "bold"),
            text_color="black",
        )
        self.total_label.grid(row=0, column=3, sticky="e")

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = ("id", "concepto", "cantidad", "importe", "descuento", "total")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=14)

        encabezados = {
            "id": ("ID", 60),
            "concepto": ("Concepto", 280),
            "cantidad": ("Cantidad", 100),
            "importe": ("Importe", 120),
            "descuento": ("Descuento", 120),
            "total": ("Total", 120),
        }

        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(columna, width=ancho, anchor="w")

        self.tabla.bind("<Double-1>", lambda _event: self.modificar_servicio_seleccionado())

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll_y.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

    def cargar_servicios(self):
        self.limpiar_tabla()

        for servicio in ServicioService.listar(self.cliente_id):
            id_servicio = servicio[0]
            concepto = servicio[2]
            cantidad = servicio[4] or 0
            importe = servicio[5] or 0
            descuento = servicio[6] or 0
            total = servicio[8] or 0
            self.tabla.insert(
                "",
                "end",
                values=(
                    id_servicio,
                    concepto,
                    self.formatear_numero(cantidad),
                    self.formatear_moneda(importe),
                    self.formatear_moneda(descuento),
                    self.formatear_moneda(total),
                ),
            )

        total_cliente = ServicioService.total_cliente(self.cliente_id)
        self.total_label.configure(text=f"Total activo: {self.formatear_moneda(total_cliente)}")

    def limpiar_tabla(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None

        valores = self.tabla.item(seleccion[0], "values")
        if not valores:
            return None

        return int(valores[0])

    def abrir_formulario_agregar(self):
        self.abrir_formulario("Agregar Servicio", None)

    def modificar_servicio_seleccionado(self):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            messagebox.showwarning("Atencion", "Seleccione un servicio para modificar.")
            return

        datos = ServicioService.obtener(id_servicio)
        if datos is None:
            messagebox.showerror("Error", "No se encontro el servicio seleccionado.")
            self.cargar_servicios()
            return

        servicio = self.crear_servicio_desde_fila(datos)
        self.abrir_formulario("Modificar Servicio", servicio)

    def eliminar_servicio_seleccionado(self):
        id_servicio = self.obtener_id_seleccionado()
        if id_servicio is None:
            messagebox.showwarning("Atencion", "Seleccione un servicio para eliminar.")
            return

        valores = self.tabla.item(self.tabla.selection()[0], "values")
        concepto = valores[1] if len(valores) > 1 else "seleccionado"
        confirma = messagebox.askyesno(
            "Confirmar eliminacion",
            f"Desea eliminar el servicio '{concepto}'?"
        )

        if not confirma:
            return

        ServicioService.eliminar(id_servicio)
        self.cargar_servicios()

    def abrir_formulario(self, titulo, servicio=None):
        ventana = ctk.CTkToplevel(self)
        ventana.title(titulo)
        ventana.geometry("500x480")
        ventana.resizable(False, False)
        ventana.configure(fg_color="white")
        ventana.transient(self)
        ventana.grab_set()

        contenedor = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        contenedor.pack(fill="both", expand=True, padx=20, pady=20)
        contenedor.grid_columnconfigure(0, weight=1)

        titulo_label = ctk.CTkLabel(
            contenedor,
            text=titulo,
            font=("Arial", 20, "bold"),
            text_color="#C00000",
        )
        titulo_label.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.campos_formulario = {}
        for fila, (clave, etiqueta) in enumerate(self.CAMPOS_FORMULARIO, start=1):
            label = ctk.CTkLabel(contenedor, text=etiqueta, anchor="w")
            label.grid(row=fila * 2 - 1, column=0, sticky="ew", pady=(8, 0))

            entrada = ctk.CTkEntry(contenedor)
            entrada.grid(row=fila * 2, column=0, sticky="ew")
            self.campos_formulario[clave] = entrada

        if servicio is None:
            self.campos_formulario["cantidad"].insert(0, "1")
            self.campos_formulario["importe"].insert(0, "0")
            self.campos_formulario["descuento"].insert(0, "0")
            self.campos_formulario["activo"].insert(0, "1")
        else:
            self.cargar_servicio_en_formulario(servicio)

        boton_guardar = ctk.CTkButton(
            contenedor,
            text="Guardar",
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.guardar_formulario(ventana, servicio),
        )
        boton_guardar.grid(row=len(self.CAMPOS_FORMULARIO) * 2 + 1, column=0, sticky="ew", pady=20)

        self.campos_formulario["concepto"].focus_set()

    def cargar_servicio_en_formulario(self, servicio):
        valores = {
            "concepto": servicio.concepto,
            "descripcion": servicio.descripcion,
            "cantidad": self.formatear_numero(servicio.cantidad),
            "importe": self.formatear_numero(servicio.importe),
            "descuento": self.formatear_numero(servicio.descuento),
            "activo": str(servicio.activo),
        }

        for clave, valor in valores.items():
            self.campos_formulario[clave].insert(0, valor)

    def guardar_formulario(self, ventana, servicio_original=None):
        concepto = self.obtener_campo("concepto")
        if not concepto:
            messagebox.showerror("Error", "El concepto es obligatorio.")
            return

        try:
            cantidad = self.convertir_decimal(self.obtener_campo("cantidad") or "1")
            importe = self.convertir_decimal(self.obtener_campo("importe") or "0")
            descuento = self.convertir_decimal(self.obtener_campo("descuento") or "0")
            activo = int(self.obtener_campo("activo") or "1")
        except ValueError:
            messagebox.showerror("Error", "Cantidad, importe, descuento y activo deben ser numericos.")
            return

        servicio = Servicio(
            id=servicio_original.id if servicio_original else None,
            cliente_id=self.cliente_id,
            concepto=concepto,
            descripcion=self.obtener_campo("descripcion"),
            cantidad=cantidad,
            importe=importe,
            descuento=descuento,
            activo=1 if activo else 0,
        )

        if servicio_original:
            ServicioService.actualizar(servicio)
        else:
            ServicioService.guardar(servicio)

        ventana.destroy()
        self.cargar_servicios()

    def crear_servicio_desde_fila(self, fila):
        return Servicio(
            id=fila[0],
            cliente_id=fila[1],
            concepto=fila[2] or "",
            descripcion=fila[3] or "",
            cantidad=fila[4] or 0,
            importe=fila[5] or 0,
            descuento=fila[6] or 0,
            activo=fila[7] if fila[7] is not None else 1,
        )

    def obtener_campo(self, clave):
        return self.campos_formulario[clave].get().strip()

    def convertir_decimal(self, valor):
        return float(valor.replace(",", "."))

    def formatear_numero(self, valor):
        return f"{float(valor):.2f}"

    def formatear_moneda(self, valor):
        return f"${float(valor):.2f}"
