from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from services.cliente_service import ClienteService
from services.dashboard_service import DashboardService
from views.servicios import ServiciosWindow


class InicioFrame(ctk.CTkFrame):
    ROJO = "#C00000"
    NEGRO = "#1B1B1B"

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.indicadores = {}
        self.importes_reales = {}
        self.importes_visibles = {}
        self.botones_visibilidad = {}
        self.crear_interfaz()
        self.actualizar_dashboard()

    def crear_interfaz(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        encabezado.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            encabezado,
            text="DASHBOARD",
            font=("Arial", 26, "bold"),
            text_color=self.ROJO,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            encabezado,
            text=datetime.now().strftime("%d/%m/%Y"),
            font=("Arial", 13, "bold"),
            text_color="#555555",
        ).grid(row=0, column=1, sticky="e")

        metricas = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        metricas.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        for columna in range(4):
            metricas.grid_columnconfigure(columna, weight=1, uniform="metricas")

        configuracion = (
            ("clientes_activos", "CLIENTES ACTIVOS", False),
            ("total_clientes", "TOTAL CLIENTES", False),
            ("resumenes_mes", "RESUMENES DEL MES", False),
            ("facturado_mes", "FACTURADO ESTE MES", True),
            ("cobrado_mes", "COBRADO ESTE MES", True),
            ("saldo_pendiente", "SALDO PENDIENTE", True),
            ("resumenes_vencidos", "RESUMENES VENCIDOS", False),
            ("proximos_vencimientos", "PROX. VENCIMIENTOS", False),
            ("resumenes_pendientes", "CLIENTES POR RESUMIR", False),
        )
        for indice, (clave, titulo, es_moneda) in enumerate(configuracion):
            fila = indice // 4
            columna = indice % 4
            self.indicadores[clave] = self.crear_tarjeta(
                metricas,
                fila,
                columna,
                clave,
                titulo,
                es_moneda,
                alerta=clave in (
                    "saldo_pendiente",
                    "resumenes_vencidos",
                    "servicios_vencidos",
                ),
            )

        self.indicadores_renovacion = self.crear_tarjeta_renovaciones(
            metricas,
            len(configuracion) // 4,
            len(configuracion) % 4,
        )
        self.indicadores_agenda = self.crear_tarjeta_agenda(
            metricas,
            len(configuracion) // 4,
            len(configuracion) % 4 + 1,
        )

        accesos = ctk.CTkFrame(self, fg_color=self.NEGRO, corner_radius=4)
        accesos.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        for columna in range(6):
            accesos.grid_columnconfigure(columna, weight=1, uniform="accesos")

        acciones = (
            ("Clientes", self.ir_clientes),
            ("Servicios", self.abrir_selector_servicios),
            ("Resumenes", self.ir_resumenes),
            ("Cobros", self.ir_cobros),
            ("Cuenta Corriente", self.ir_cuenta_corriente),
            ("Backup", self.crear_backup),
        )
        for columna, (texto, comando) in enumerate(acciones):
            boton = ctk.CTkButton(
                accesos,
                text=texto,
                height=38,
                fg_color="#333333",
                hover_color=self.ROJO,
                corner_radius=4,
                command=comando,
            )
            boton.grid(row=0, column=columna, sticky="ew", padx=5, pady=9)

        titulo_vencimientos = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        titulo_vencimientos.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))
        titulo_vencimientos.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            titulo_vencimientos,
            text="PROXIMOS VENCIMIENTOS",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            titulo_vencimientos,
            text="30 dias",
            font=("Arial", 11),
            text_color="#666666",
        ).grid(row=0, column=1, sticky="e")

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 16))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = ("numero", "vencimiento", "cliente", "total", "saldo", "estado")
        self.tabla_vencimientos = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            height=7,
        )
        self.tabla_vencimientos.bind(
            "<Double-1>",
            lambda _evento: self.ir_resumenes(),
        )
        encabezados = {
            "numero": ("Resumen", 90),
            "vencimiento": ("Vencimiento", 105),
            "cliente": ("Cliente", 260),
            "total": ("Total", 110),
            "saldo": ("Saldo", 110),
            "estado": ("Estado", 90),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla_vencimientos.heading(columna, text=texto)
            self.tabla_vencimientos.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna == "cliente",
            )
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla_vencimientos.yview)
        self.tabla_vencimientos.configure(yscrollcommand=scroll.set)
        self.tabla_vencimientos.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def crear_tarjeta(self, master, fila, columna, clave, titulo, es_moneda, alerta=False):
        tarjeta = ctk.CTkFrame(
            master,
            height=82,
            fg_color=self.ROJO if alerta else self.NEGRO,
            corner_radius=6,
        )
        tarjeta.grid(row=fila, column=columna, sticky="nsew", padx=6, pady=5)
        tarjeta.grid_propagate(False)
        tarjeta.grid_columnconfigure(0, weight=1)
        tarjeta.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            tarjeta,
            text=titulo,
            font=("Arial", 10, "bold"),
            text_color="#E0E0E0",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        if es_moneda:
            self.importes_visibles[clave] = True
            boton_ojo = ctk.CTkButton(
                tarjeta,
                text="👁",
                width=30,
                height=26,
                font=("Segoe UI Emoji", 15),
                fg_color="transparent",
                hover_color="#4A4A4A" if not alerta else "#990000",
                corner_radius=4,
                command=lambda clave_importe=clave: self.alternar_importe(clave_importe),
            )
            boton_ojo.grid(row=0, column=1, padx=(0, 7), pady=(7, 0), sticky="e")
            self.botones_visibilidad[clave] = boton_ojo

        valor = ctk.CTkLabel(
            tarjeta,
            text="$ 0,00" if es_moneda else "0",
            font=("Arial", 22, "bold"),
            text_color="white",
            anchor="w",
        )
        valor.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(2, 8))
        return valor

    def crear_tarjeta_renovaciones(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(
            master,
            height=82,
            fg_color=self.NEGRO,
            corner_radius=6,
        )
        tarjeta.grid(row=fila, column=columna, sticky="nsew", padx=6, pady=5)
        tarjeta.grid_propagate(False)
        for indice in range(4):
            tarjeta.grid_columnconfigure(indice, weight=1, uniform="renovacion")
        ctk.CTkLabel(
            tarjeta,
            text="SERVICIOS A RENOVAR",
            font=("Arial", 10, "bold"),
            text_color="#E0E0E0",
            anchor="w",
        ).grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(10, 0))
        etiquetas = {}
        configuracion = (
            ("hoy", "Hoy", "#F4C542"),
            ("semana", "Semana", "#F4C542"),
            ("vencidos", "Vencidos", "#FF4D4D"),
            ("renovados", "Renov.", "#52C878"),
        )
        for columna_indice, (clave, texto, color) in enumerate(configuracion):
            etiqueta = ctk.CTkLabel(
                tarjeta,
                text=f"{texto}: 0",
                font=("Arial", 9, "bold"),
                text_color=color,
            )
            etiqueta.grid(row=1, column=columna_indice, pady=(7, 8))
            etiquetas[clave] = etiqueta
        return etiquetas

    def crear_tarjeta_agenda(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(
            master,
            height=82,
            fg_color=self.NEGRO,
            corner_radius=6,
        )
        tarjeta.grid(
            row=fila,
            column=columna,
            columnspan=2,
            sticky="nsew",
            padx=6,
            pady=5,
        )
        tarjeta.grid_propagate(False)
        for indice in range(4):
            tarjeta.grid_columnconfigure(indice, weight=1)
        ctk.CTkLabel(
            tarjeta,
            text="AGENDA DEL DÍA",
            font=("Arial", 10, "bold"),
            text_color="#E0E0E0",
        ).grid(row=0, column=0, sticky="w", padx=(12, 4), pady=(8, 0))
        ctk.CTkButton(
            tarjeta,
            text="Ir a Agenda",
            width=82,
            height=24,
            font=("Arial", 9, "bold"),
            fg_color="#C00000",
            hover_color="#990000",
            command=self.ir_agenda,
        ).grid(row=0, column=3, sticky="e", padx=(4, 8), pady=(6, 0))
        etiquetas = {}
        datos = (
            ("pendientes", "Pendientes: 0", "#F4C542"),
            ("vencidas", "Vencidas: 0", "#FF4D4D"),
            ("completadas", "Completadas: 0", "#52C878"),
        )
        for indice, (clave, texto, color) in enumerate(datos):
            etiqueta = ctk.CTkLabel(
                tarjeta,
                text=texto,
                font=("Arial", 9, "bold"),
                text_color=color,
            )
            etiqueta.grid(row=1, column=indice, padx=4, pady=(3, 0))
            etiquetas[clave] = etiqueta
        etiquetas["proxima"] = ctk.CTkLabel(
            tarjeta,
            text="Próxima: Sin tareas",
            font=("Arial", 8),
            text_color="white",
            anchor="w",
        )
        etiquetas["proxima"].grid(
            row=2,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=10,
            pady=(0, 5),
        )
        return etiquetas

    def actualizar_dashboard(self):
        datos = DashboardService.obtener_indicadores()
        claves_moneda = {"facturado_mes", "cobrado_mes", "saldo_pendiente"}
        for clave, etiqueta in self.indicadores.items():
            valor = datos[clave]
            if clave in claves_moneda:
                importe_formateado = self.formatear_moneda(valor)
                self.importes_reales[clave] = importe_formateado
                etiqueta.configure(
                    text=importe_formateado if self.importes_visibles[clave] else "********"
                )
            else:
                etiqueta.configure(text=str(valor))

        self.indicadores_renovacion["hoy"].configure(
            text=f"Hoy: {datos['renovaciones_hoy']}"
        )
        self.indicadores_renovacion["semana"].configure(
            text=f"Semana: {datos['renovaciones_semana']}"
        )
        self.indicadores_renovacion["vencidos"].configure(
            text=f"Vencidos: {datos['renovaciones_vencidas']}"
        )
        self.indicadores_renovacion["renovados"].configure(
            text=f"Renov.: {datos['renovados_hoy']}"
        )
        agenda = datos["agenda"]
        self.indicadores_agenda["pendientes"].configure(
            text=f"Pendientes: {agenda['pendientes_hoy']}"
        )
        self.indicadores_agenda["vencidas"].configure(
            text=f"Vencidas: {agenda['vencidas']}"
        )
        self.indicadores_agenda["completadas"].configure(
            text=f"Completadas: {agenda['completadas_hoy']}"
        )
        self.indicadores_agenda["proxima"].configure(
            text=f"Próxima: {agenda['proxima']}"
        )

        for item in self.tabla_vencimientos.get_children():
            self.tabla_vencimientos.delete(item)
        for resumen in DashboardService.listar_proximos_vencimientos():
            self.tabla_vencimientos.insert("", "end", values=(
                f"{resumen[1]:06d}",
                self.formatear_fecha(resumen[2]),
                resumen[3],
                self.formatear_moneda(resumen[4]),
                self.formatear_moneda(resumen[5]),
                resumen[6],
            ))

    def alternar_importe(self, clave):
        visible = not self.importes_visibles[clave]
        self.importes_visibles[clave] = visible
        self.indicadores[clave].configure(
            text=self.importes_reales[clave] if visible else "********"
        )
        self.botones_visibilidad[clave].configure(text="👁" if visible else "🙈")

    def ir_clientes(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_clientes()

    def ir_resumenes(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_resumenes()

    def ir_cobros(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_cobros()

    def ir_cuenta_corriente(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_cobros()

    def ir_agenda(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_agenda()

    def abrir_selector_servicios(self):
        clientes = ClienteService.listar()
        if not clientes:
            messagebox.showwarning("Atencion", "No hay clientes cargados.")
            return

        ventana = ctk.CTkToplevel(self)
        ventana.title("Seleccionar Cliente")
        ventana.geometry("500x220")
        ventana.resizable(False, False)
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        nombres = {f"{cliente[1] or '-'} - {cliente[2]}": cliente for cliente in clientes}
        ctk.CTkLabel(
            ventana,
            text="SERVICIOS DEL CLIENTE",
            font=("Arial", 20, "bold"),
            text_color=self.ROJO,
        ).pack(anchor="w", padx=22, pady=(22, 12))
        selector = ctk.CTkComboBox(ventana, values=list(nombres), width=455)
        selector.pack(fill="x", padx=22)
        selector.set(next(iter(nombres)))

        def abrir():
            cliente = nombres.get(selector.get())
            if cliente:
                ventana.destroy()
                ServiciosWindow(self, cliente[0], cliente[2])

        ctk.CTkButton(
            ventana,
            text="Abrir Servicios",
            fg_color=self.ROJO,
            hover_color="#990000",
            command=abrir,
        ).pack(anchor="e", padx=22, pady=18)

    def crear_backup(self):
        try:
            ruta = DashboardService.crear_backup()
        except OSError as error:
            messagebox.showerror("Backup", str(error), parent=self)
            return
        messagebox.showinfo("Backup", f"Backup creado correctamente.\n{ruta}", parent=self)

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
