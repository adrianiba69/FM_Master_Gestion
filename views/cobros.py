from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.cobro import Cobro
from services.cliente_service import ClienteService
from services.cobro_service import CobroService


class CobrosFrame(ctk.CTkFrame):
    FORMAS_PAGO = ["Efectivo", "Transferencia", "Deposito", "Cheque", "Tarjeta", "Otro"]

    def __init__(self, master, cliente_id=None, on_cambio=None):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.cliente_inicial = cliente_id
        self.on_cambio = on_cambio
        self.clientes_por_nombre = {}
        self.campos_formulario = {}
        self.crear_interfaz()
        self.cargar_clientes()

    def crear_interfaz(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="CUENTA CORRIENTE Y COBROS",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        selector = ctk.CTkFrame(self, fg_color="#F3F3F3", corner_radius=4)
        selector.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        selector.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            selector,
            text="Cliente",
            font=("Arial", 13, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, padx=(14, 10), pady=14)

        self.selector_cliente = ctk.CTkComboBox(
            selector,
            values=[""],
            width=400,
            command=lambda _valor: self.actualizar_cuenta(),
        )
        self.selector_cliente.grid(row=0, column=1, sticky="w", pady=14)

        self.boton_registrar = ctk.CTkButton(
            selector,
            text="Nuevo",
            width=145,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_nuevo_cobro,
        )
        self.boton_registrar.grid(row=0, column=2, padx=(12, 14), pady=14)

        totales = ctk.CTkFrame(self, fg_color="#222222", corner_radius=4)
        totales.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        for columna in range(3):
            totales.grid_columnconfigure(columna, weight=1, uniform="totales")

        self.total_facturado_label = self.crear_indicador(
            totales, 0, "TOTAL FACTURADO", "$ 0,00"
        )
        self.total_cobrado_label = self.crear_indicador(
            totales, 1, "TOTAL COBRADO", "$ 0,00"
        )
        self.saldo_label = self.crear_indicador(
            totales, 2, "SALDO PENDIENTE", "$ 0,00", destacado=True
        )

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        acciones.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            acciones,
            text="Movimientos de la cuenta",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")

        self.boton_modificar = ctk.CTkButton(
            acciones,
            text="Modificar",
            width=135,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_cobro_seleccionado,
        )
        self.boton_modificar.grid(row=0, column=1, padx=(10, 0))

        self.boton_eliminar = ctk.CTkButton(
            acciones,
            text="Eliminar",
            width=125,
            height=38,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_cobro_seleccionado,
        )
        self.boton_eliminar.grid(row=0, column=2, padx=(10, 0))

        self.pestanas = ttk.Notebook(self)
        self.pestanas.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 20))

        panel_resumenes = ctk.CTkFrame(self.pestanas, fg_color="white", corner_radius=0)
        panel_cobros = ctk.CTkFrame(self.pestanas, fg_color="white", corner_radius=0)
        self.pestanas.add(panel_resumenes, text="  Resumenes emitidos  ")
        self.pestanas.add(panel_cobros, text="  Cobros realizados  ")
        self.crear_tabla_resumenes(panel_resumenes)
        self.crear_tabla_cobros(panel_cobros)

    @staticmethod
    def crear_indicador(master, columna, titulo, valor, destacado=False):
        bloque = ctk.CTkFrame(master, fg_color="transparent", corner_radius=0)
        bloque.grid(row=0, column=columna, sticky="ew", padx=18, pady=14)
        bloque.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            bloque,
            text=titulo,
            font=("Arial", 10, "bold"),
            text_color="#CCCCCC",
        ).grid(row=0, column=0, sticky="w")
        etiqueta = ctk.CTkLabel(
            bloque,
            text=valor,
            font=("Arial", 21, "bold"),
            text_color="#FF3B3B" if destacado else "white",
        )
        etiqueta.grid(row=1, column=0, sticky="w", pady=(3, 0))
        return etiqueta

    def crear_tabla_resumenes(self, panel):
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        columnas = ("id", "numero", "fecha", "vencimiento", "total", "estado")
        self.tabla_resumenes = ttk.Treeview(panel, columns=columnas, show="headings", height=13)
        encabezados = {
            "id": ("ID", 55),
            "numero": ("Resumen", 110),
            "fecha": ("Fecha", 120),
            "vencimiento": ("Vencimiento", 130),
            "total": ("Total", 145),
            "estado": ("Estado", 120),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla_resumenes.heading(columna, text=texto)
            self.tabla_resumenes.column(columna, width=ancho, anchor="w")
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.tabla_resumenes.yview)
        self.tabla_resumenes.configure(yscrollcommand=scroll.set)
        self.tabla_resumenes.grid(row=0, column=0, sticky="nsew", pady=(8, 0))
        scroll.grid(row=0, column=1, sticky="ns", pady=(8, 0))

    def crear_tabla_cobros(self, panel):
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        columnas = ("id", "fecha", "importe", "forma_pago", "comprobante", "observaciones")
        self.tabla_cobros = ttk.Treeview(panel, columns=columnas, show="headings", height=13)
        encabezados = {
            "id": ("ID", 55),
            "fecha": ("Fecha", 105),
            "importe": ("Importe", 120),
            "forma_pago": ("Forma de pago", 150),
            "comprobante": ("Comprobante", 145),
            "observaciones": ("Observaciones", 250),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla_cobros.heading(columna, text=texto)
            self.tabla_cobros.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna == "observaciones",
            )
        self.tabla_cobros.bind("<Double-1>", lambda _evento: self.modificar_cobro_seleccionado())
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.tabla_cobros.yview)
        self.tabla_cobros.configure(yscrollcommand=scroll.set)
        self.tabla_cobros.grid(row=0, column=0, sticky="nsew", pady=(8, 0))
        scroll.grid(row=0, column=1, sticky="ns", pady=(8, 0))

    def cargar_clientes(self):
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {
            f"{cliente[1] or '-'} - {cliente[2]}": cliente[0]
            for cliente in clientes
        }
        nombres = list(self.clientes_por_nombre)
        self.selector_cliente.configure(values=nombres or [""])

        seleccionado = ""
        if self.cliente_inicial is not None:
            seleccionado = next(
                (nombre for nombre, identificador in self.clientes_por_nombre.items()
                 if identificador == self.cliente_inicial),
                "",
            )
        if not seleccionado and nombres:
            seleccionado = nombres[0]
        self.selector_cliente.set(seleccionado)
        self.actualizar_cuenta()

    def cliente_id_actual(self):
        return self.clientes_por_nombre.get(self.selector_cliente.get())

    def actualizar_cuenta(self):
        cliente_id = self.cliente_id_actual()
        self.limpiar_tabla(self.tabla_resumenes)
        self.limpiar_tabla(self.tabla_cobros)

        if cliente_id is None:
            self.actualizar_totales(0, 0, 0)
            return

        for resumen in CobroService.resumenes_cliente(cliente_id):
            self.tabla_resumenes.insert("", "end", values=(
                resumen[0],
                f"{resumen[1]:06d}",
                self.formatear_fecha(resumen[2]),
                self.formatear_fecha(resumen[3]),
                self.formatear_moneda(resumen[4]),
                resumen[5],
            ))

        for cobro in CobroService.listar(cliente_id):
            self.tabla_cobros.insert("", "end", values=(
                cobro[0],
                self.formatear_fecha(cobro[2]),
                self.formatear_moneda(cobro[3]),
                cobro[4] or "",
                cobro[5] or "",
                cobro[6] or "",
            ))

        totales = CobroService.totales(cliente_id)
        self.actualizar_totales(
            totales["total_facturado"],
            totales["total_cobrado"],
            totales["saldo_pendiente"],
        )

    def actualizar_totales(self, facturado, cobrado, saldo):
        self.total_facturado_label.configure(text=self.formatear_moneda(facturado))
        self.total_cobrado_label.configure(text=self.formatear_moneda(cobrado))
        self.saldo_label.configure(
            text=self.formatear_moneda(saldo),
            text_color="#FF3B3B" if saldo > 0 else "#52C878",
        )

    def abrir_nuevo_cobro(self):
        cliente_id = self.cliente_id_actual()
        if cliente_id is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente.")
            return
        self.abrir_formulario("Registrar Cobro", None)

    def modificar_cobro_seleccionado(self):
        cobro_id = self.obtener_cobro_seleccionado()
        if cobro_id is None:
            messagebox.showwarning("Atencion", "Seleccione un cobro para modificar.")
            return
        fila = CobroService.obtener(cobro_id)
        if fila is None:
            messagebox.showerror("Error", "No se encontro el cobro seleccionado.")
            self.actualizar_cuenta()
            return
        self.abrir_formulario("Modificar Cobro", Cobro(*fila))

    def eliminar_cobro_seleccionado(self):
        cobro_id = self.obtener_cobro_seleccionado()
        if cobro_id is None:
            messagebox.showwarning("Atencion", "Seleccione un cobro para eliminar.")
            return
        valores = self.tabla_cobros.item(self.tabla_cobros.selection()[0], "values")
        if not messagebox.askyesno(
            "Confirmar eliminacion",
            f"Desea eliminar el cobro de {valores[2]}?",
            parent=self,
        ):
            return
        CobroService.eliminar(cobro_id)
        self.actualizar_cuenta()

    def abrir_formulario(self, titulo, cobro=None):
        ventana = ctk.CTkToplevel(self)
        ventana.title(titulo)
        ventana.geometry("620x650")
        ventana.minsize(560, 600)
        ventana.resizable(False, False)
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        contenido = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        contenido.pack(fill="both", expand=True, padx=22, pady=20)
        contenido.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            contenido,
            text=titulo,
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        self.campos_formulario = {}
        campos = (
            ("fecha", "Fecha (DD/MM/AAAA)"),
            ("importe", "Importe *"),
            ("comprobante", "Comprobante"),
        )
        for fila, (clave, etiqueta) in enumerate(campos, start=1):
            ctk.CTkLabel(contenido, text=etiqueta, anchor="w").grid(
                row=fila * 2 - 1, column=0, sticky="ew", pady=(8, 0)
            )
            entrada = ctk.CTkEntry(contenido)
            entrada.grid(row=fila * 2, column=0, sticky="ew")
            self.campos_formulario[clave] = entrada

        ctk.CTkLabel(contenido, text="Forma de pago", anchor="w").grid(
            row=7, column=0, sticky="ew", pady=(8, 0)
        )
        self.forma_pago_combo = ctk.CTkComboBox(contenido, values=self.FORMAS_PAGO)
        self.forma_pago_combo.grid(row=8, column=0, sticky="ew")

        ctk.CTkLabel(contenido, text="Observaciones", anchor="w").grid(
            row=9, column=0, sticky="ew", pady=(8, 0)
        )
        self.observaciones_texto = ctk.CTkTextbox(contenido, height=75)
        self.observaciones_texto.grid(row=10, column=0, sticky="ew")

        if cobro is None:
            self.campos_formulario["fecha"].insert(0, date.today().strftime("%d/%m/%Y"))
            self.campos_formulario["importe"].insert(0, "0")
            self.forma_pago_combo.set(self.FORMAS_PAGO[0])
        else:
            self.campos_formulario["fecha"].insert(0, self.formatear_fecha(cobro.fecha))
            self.campos_formulario["importe"].insert(0, self.formatear_numero(cobro.importe))
            self.campos_formulario["comprobante"].insert(0, cobro.comprobante or "")
            self.forma_pago_combo.set(cobro.forma_pago or self.FORMAS_PAGO[0])
            self.observaciones_texto.insert("1.0", cobro.observaciones or "")

        botones = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        botones.grid(row=11, column=0, sticky="ew", pady=(18, 0))
        botones.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            botones,
            text="Guardar",
            width=130,
            height=40,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.guardar_formulario(ventana, cobro),
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))
        ctk.CTkButton(
            botones,
            text="Cancelar",
            width=110,
            height=40,
            fg_color="#666666",
            hover_color="#444444",
            command=ventana.destroy,
        ).grid(row=0, column=1)
        self.campos_formulario["importe"].focus_set()

    def guardar_formulario(self, ventana, cobro_original=None):
        try:
            fecha = datetime.strptime(
                self.campos_formulario["fecha"].get().strip(), "%d/%m/%Y"
            ).date()
            importe = self.convertir_decimal(self.campos_formulario["importe"].get())
        except ValueError:
            messagebox.showerror(
                "Error",
                "Ingrese una fecha DD/MM/AAAA y un importe numerico valido.",
                parent=ventana,
            )
            return

        if importe <= 0:
            messagebox.showerror("Error", "El importe debe ser mayor que cero.", parent=ventana)
            return

        cobro = Cobro(
            id=cobro_original.id if cobro_original else None,
            cliente_id=self.cliente_id_actual(),
            fecha=fecha.isoformat(),
            importe=importe,
            forma_pago=self.forma_pago_combo.get().strip(),
            comprobante=self.campos_formulario["comprobante"].get().strip(),
            observaciones=self.observaciones_texto.get("1.0", "end").strip(),
        )
        if cobro_original:
            CobroService.actualizar(cobro)
        else:
            CobroService.guardar(cobro)
        ventana.destroy()
        self.actualizar_cuenta()
        if callable(self.on_cambio):
            self.on_cambio()
        self.pestanas.select(1)
        messagebox.showinfo(
            "Cobros",
            "Cobro modificado correctamente."
            if cobro_original
            else "Cobro registrado correctamente.",
            parent=self,
        )

    def obtener_cobro_seleccionado(self):
        seleccion = self.tabla_cobros.selection()
        if not seleccion:
            return None
        valores = self.tabla_cobros.item(seleccion[0], "values")
        return int(valores[0]) if valores else None

    @staticmethod
    def limpiar_tabla(tabla):
        for item in tabla.get_children():
            tabla.delete(item)

    @staticmethod
    def convertir_decimal(valor):
        normalizado = valor.strip().replace("$", "").replace(" ", "")
        if "," in normalizado and "." in normalizado:
            normalizado = normalizado.replace(".", "").replace(",", ".")
        else:
            normalizado = normalizado.replace(",", ".")
        return float(normalizado)

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def formatear_numero(valor):
        return f"{float(valor or 0):.2f}"

    @staticmethod
    def formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
