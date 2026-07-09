from datetime import datetime
from types import MethodType
from tkinter import messagebox, ttk

import customtkinter as ctk

from services.cliente_service import ClienteService
from services.dashboard_service import DashboardService
from services.prioridad_service import PrioridadService
from services.tarea_service import TareaService
from views.crm import ContactoFormWindow
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
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        contenedor = ctk.CTkScrollableFrame(self, fg_color="white")
        contenedor.grid(row=0, column=0, sticky="nsew")
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(0, weight=1)

        contenido = ctk.CTkFrame(contenedor, fg_color="white", corner_radius=0)
        contenido.grid(row=0, column=0, sticky="nsew")
        contenido.grid_columnconfigure(0, weight=1)

        encabezado = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 10))
        encabezado.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            encabezado,
            text="PANEL DE CONTROL",
            font=("Arial", 26, "bold"),
            text_color=self.ROJO,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            encabezado,
            text=datetime.now().strftime("%d/%m/%Y"),
            font=("Arial", 13, "bold"),
            text_color="#555555",
        ).grid(row=0, column=1, sticky="e")

        metricas = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
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
            ("clientes_con_deuda", "CLIENTES CON DEUDA", False),
            ("total_cobrado_hoy", "COBRADO HOY", True),
            ("tareas_hoy", "TAREAS HOY", False),
        )
        click_handlers = {
            "clientes_con_deuda": self.ir_cuenta_corriente,
            "total_cobrado_hoy": self.ir_cobros,
            "tareas_hoy": self.ir_agenda,
        }
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
                alerta=clave in ("saldo_pendiente", "resumenes_vencidos"),
                on_click=click_handlers.get(clave),
            )

        self.indicadores_renovacion = self.crear_tarjeta_renovaciones(
            metricas,
            len(configuracion) // 4,
            0,
        )
        self.indicadores_agenda = self.crear_tarjeta_agenda(
            metricas,
            len(configuracion) // 4,
            2,
        )
        self.indicadores_seguimientos = self.crear_tarjeta_seguimientos(
            metricas,
            len(configuracion) // 4 + 1,
            0,
        )
        self.indicadores_oportunidades = self.crear_tarjeta_oportunidades(
            metricas,
            len(configuracion) // 4 + 1,
            2,
        )
        self.indicadores_alertas = self.crear_tarjeta_alertas(
            metricas,
            len(configuracion) // 4 + 2,
            0,
        )
        self.alertas_prioritarias = self.crear_bloque_alertas_prioritarias(
            metricas,
            len(configuracion) // 4 + 3,
            0,
        )
        self.bloque_prioridad = self.crear_bloque_prioridad(
            metricas,
            len(configuracion) // 4 + 4,
            0,
        )

        accesos = ctk.CTkFrame(contenido, fg_color=self.NEGRO, corner_radius=4)
        accesos.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        for columna in range(6):
            accesos.grid_columnconfigure(columna, weight=1, uniform="accesos")

        acciones = (
            ("Clientes", self.ir_clientes),
            ("Servicios", self.abrir_selector_servicios),
            ("Resúmenes", self.ir_resumenes),
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

        ctk.CTkButton(
            accesos,
            text="CIERRE DEL MES",
            height=48,
            font=("Arial", 16, "bold"),
            fg_color=self.ROJO,
            hover_color="#990000",
            corner_radius=4,
            command=self.ir_cierre_mensual,
        ).grid(row=1, column=0, columnspan=6, sticky="ew", padx=5, pady=(0, 9))

        titulo_agenda = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        titulo_agenda.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 4))
        titulo_agenda.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            titulo_agenda,
            text="AGENDA DEL DÍA",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")

        tabla_agenda_frame = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        tabla_agenda_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 12))
        tabla_agenda_frame.grid_rowconfigure(0, weight=1)
        tabla_agenda_frame.grid_columnconfigure(0, weight=1)
        self.tabla_agenda = ttk.Treeview(
            tabla_agenda_frame,
            columns=("hora", "tipo", "titulo", "estado"),
            show="headings",
            height=5,
        )
        for columna, (texto, ancho) in {
            "hora": ("Hora", 90),
            "tipo": ("Tipo", 140),
            "titulo": ("Título", 320),
            "estado": ("Estado", 110),
        }.items():
            self.tabla_agenda.heading(columna, text=texto)
            self.tabla_agenda.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna == "titulo",
            )
        scroll_agenda = ttk.Scrollbar(tabla_agenda_frame, orient="vertical", command=self.tabla_agenda.yview)
        self.tabla_agenda.configure(yscrollcommand=scroll_agenda.set)
        self.tabla_agenda.grid(row=0, column=0, sticky="nsew")
        scroll_agenda.grid(row=0, column=1, sticky="ns")

        titulo_vencimientos = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        titulo_vencimientos.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 4))
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

        tabla_frame = ctk.CTkFrame(contenido, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=6, column=0, sticky="nsew", padx=20, pady=(0, 16))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        self.tabla_vencimientos = ttk.Treeview(
            tabla_frame,
            columns=("numero", "vencimiento", "cliente", "total", "saldo", "estado"),
            show="headings",
            height=7,
        )
        self.tabla_vencimientos.bind("<Double-1>", lambda _evento: self.ir_resumenes())
        for columna, (texto, ancho) in {
            "numero": ("Resumen", 90),
            "vencimiento": ("Vencimiento", 105),
            "cliente": ("Cliente", 260),
            "total": ("Total", 110),
            "saldo": ("Saldo", 110),
            "estado": ("Estado", 90),
        }.items():
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

    def crear_tarjeta(self, master, fila, columna, clave, titulo, es_moneda, alerta=False, on_click=None):
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
        titulo_label = ctk.CTkLabel(
            tarjeta,
            text=titulo,
            font=("Arial", 10, "bold"),
            text_color="#E0E0E0",
            anchor="w",
        )
        titulo_label.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))

        if es_moneda:
            ocultar_inicio = clave in {"facturado_mes", "cobrado_mes", "saldo_pendiente"}
            self.importes_visibles[clave] = not ocultar_inicio
            boton_ojo = ctk.CTkButton(
                tarjeta,
                text="🙈" if ocultar_inicio else "👁",
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

        if callable(on_click):
            for widget in (tarjeta, titulo_label, valor):
                widget.bind("<Button-1>", lambda _evento, accion=on_click: accion())
                try:
                    widget.configure(cursor="hand2")
                except Exception:
                    pass

        return valor

    def crear_tarjeta_renovaciones(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(
            master,
            height=82,
            fg_color=self.NEGRO,
            corner_radius=6,
        )
        tarjeta.grid(row=fila, column=columna, columnspan=2, sticky="nsew", padx=6, pady=5)
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

    def crear_tarjeta_seguimientos(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(master, height=76, fg_color=self.NEGRO, corner_radius=6)
        tarjeta.grid(row=fila, column=columna, columnspan=2, sticky="nsew", padx=6, pady=5)
        tarjeta.grid_propagate(False)
        for indice in range(4):
            tarjeta.grid_columnconfigure(indice, weight=1)
        ctk.CTkLabel(
            tarjeta, text="SEGUIMIENTOS", font=("Arial", 10, "bold"), text_color="#E0E0E0",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(9, 0))
        etiquetas = {}
        datos = (
            ("hoy", "Contactos para hoy: 0", "#F4C542"),
            ("atrasados", "Atrasados: 0", "#FF4D4D"),
            ("semana", "Esta semana: 0", "#52C878"),
        )
        for indice, (clave, texto, color) in enumerate(datos, start=1):
            etiqueta = ctk.CTkLabel(
                tarjeta, text=texto, font=("Arial", 10, "bold"), text_color=color,
            )
            etiqueta.grid(row=1, column=indice, padx=6, pady=(4, 8))
            etiquetas[clave] = etiqueta
        return etiquetas

    def crear_tarjeta_oportunidades(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(master, height=76, fg_color=self.NEGRO, corner_radius=6)
        tarjeta.grid(row=fila, column=columna, columnspan=2, sticky="nsew", padx=6, pady=5)
        tarjeta.grid_propagate(False)
        for indice in range(4):
            tarjeta.grid_columnconfigure(indice, weight=1)
        ctk.CTkLabel(
            tarjeta, text="OPORTUNIDADES", font=("Arial", 10, "bold"), text_color="#E0E0E0",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(9, 0))
        etiquetas = {}
        for indice, (clave, texto, color) in enumerate((
            ("nuevas", "Nuevas: 0", "#F4C542"),
            ("negociacion", "Negociación: 0", "#5DADE2"),
            ("ganadas_mes", "Ganadas mes: 0", "#52C878"),
            ("importe_estimado", "$ 0,00", "#FFFFFF"),
        )):
            etiqueta = ctk.CTkLabel(
                tarjeta, text=texto, font=("Arial", 9, "bold"), text_color=color,
            )
            etiqueta.grid(row=1, column=indice, padx=3, pady=(4, 8))
            etiquetas[clave] = etiqueta
        return etiquetas

    def crear_tarjeta_alertas(self, master, fila, columna):
        self.tarjeta_alertas = ctk.CTkFrame(
            master, height=70, fg_color=self.NEGRO, corner_radius=6,
        )
        self.tarjeta_alertas.grid(
            row=fila, column=columna, columnspan=4, sticky="nsew", padx=6, pady=5,
        )
        self.tarjeta_alertas.grid_propagate(False)
        for indice in range(4):
            self.tarjeta_alertas.grid_columnconfigure(indice, weight=1)
        ctk.CTkLabel(
            self.tarjeta_alertas, text="ALERTAS", font=("Arial", 11, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
        etiquetas = {}
        for indice, (clave, texto, color) in enumerate((
            ("urgentes", "Urgentes: 0", "#FF4D4D"),
            ("pendientes", "Pendientes: 0", "#F4C542"),
            ("vencidas", "Vencidas: 0", "#FF8C42"),
        ), start=1):
            etiqueta = ctk.CTkLabel(
                self.tarjeta_alertas, text=texto, font=("Arial", 10, "bold"),
                text_color=color,
            )
            etiqueta.grid(row=1, column=indice, padx=6, pady=(2, 7))
            etiquetas[clave] = etiqueta
        return etiquetas

    def crear_bloque_alertas_prioritarias(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(master, fg_color=self.NEGRO, corner_radius=6)
        tarjeta.grid(row=fila, column=columna, columnspan=4, sticky="nsew", padx=6, pady=5)
        tarjeta.grid_columnconfigure(0, weight=1)
        tarjeta.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(
            tarjeta,
            text="ALERTAS PRIORITARIAS",
            font=("Arial", 11, "bold"),
            text_color="white",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 4))

        etiquetas = {}
        acciones = {
            "resumenes_vencidos": self.ir_resumenes,
            "servicios_vencidos": self.abrir_selector_servicios,
            "tareas_vencidas": self.ir_agenda,
            "seguimientos_atrasados": self.ir_crm,
            "clientes_con_deuda": self.ir_cuenta_corriente,
        }
        filas = (
            ("resumenes_vencidos", "Resúmenes vencidos"),
            ("servicios_vencidos", "Servicios vencidos"),
            ("tareas_vencidas", "Tareas vencidas"),
            ("seguimientos_atrasados", "Seguimientos atrasados"),
            ("clientes_con_deuda", "Clientes con deuda"),
        )
        for indice, (clave, texto) in enumerate(filas, start=1):
            etiqueta_texto = ctk.CTkLabel(
                tarjeta,
                text=texto,
                font=("Arial", 10),
                text_color="#E0E0E0",
                anchor="w",
            )
            etiqueta_texto.grid(row=indice, column=0, sticky="w", padx=12, pady=2)

            valor = ctk.CTkLabel(
                tarjeta,
                text="0",
                font=("Arial", 10, "bold"),
                text_color="#E0E0E0",
                anchor="e",
            )
            valor.grid(row=indice, column=1, sticky="e", padx=12, pady=2)

            accion = acciones.get(clave)
            if callable(accion):
                for widget in (etiqueta_texto, valor):
                    widget.bind("<Button-1>", lambda _evento, callback=accion: callback())
                    try:
                        widget.configure(cursor="hand2")
                    except Exception:
                        pass

            etiquetas[clave] = valor

        return etiquetas

    def crear_bloque_prioridad(self, master, fila, columna):
        tarjeta = ctk.CTkFrame(master, fg_color=self.NEGRO, corner_radius=6)
        tarjeta.grid(row=fila, column=columna, columnspan=4, sticky="nsew", padx=6, pady=(5, 8))
        tarjeta.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            tarjeta,
            text="🧠 ¿Qué hago ahora?",
            font=("Arial", 11, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))

        titulo = ctk.CTkLabel(
            tarjeta,
            text="",
            font=("Arial", 10, "bold"),
            text_color="#F4C542",
            anchor="w",
            justify="left",
        )
        titulo.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        mensaje = ctk.CTkLabel(
            tarjeta,
            text="",
            font=("Arial", 10),
            text_color="#E0E0E0",
            anchor="w",
            justify="left",
            wraplength=980,
        )
        mensaje.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))

        prioridad = ctk.CTkLabel(
            tarjeta,
            text="",
            font=("Arial", 10, "bold"),
            text_color="#E0E0E0",
            anchor="w",
            justify="left",
        )
        prioridad.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))

        motivos = ctk.CTkLabel(
            tarjeta,
            text="",
            font=("Arial", 9),
            text_color="#E0E0E0",
            anchor="w",
            justify="left",
            wraplength=980,
        )
        motivos.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 10))

        contenedor_acciones = ctk.CTkFrame(tarjeta, fg_color="transparent", corner_radius=0)
        contenedor_acciones.grid(row=5, column=0, sticky="w", padx=12, pady=(0, 10))
        for columna in range(4):
            contenedor_acciones.grid_columnconfigure(columna, weight=0)

        boton_abrir_ficha = ctk.CTkButton(
            contenedor_acciones,
            text="Abrir ficha",
            width=110,
            height=28,
            font=("Arial", 10, "bold"),
            fg_color=self.ROJO,
            hover_color="#990000",
            corner_radius=4,
            command=lambda: None,
        )
        boton_abrir_ficha.grid(row=0, column=0, padx=(0, 8))

        boton_registrar_cobro = ctk.CTkButton(
            contenedor_acciones,
            text="Registrar cobro",
            width=130,
            height=28,
            font=("Arial", 10, "bold"),
            fg_color=self.ROJO,
            hover_color="#990000",
            corner_radius=4,
            command=lambda: None,
        )
        boton_registrar_cobro.grid(row=0, column=1, padx=(0, 8))

        boton_nuevo_resumen = ctk.CTkButton(
            contenedor_acciones,
            text="Nuevo resumen",
            width=130,
            height=28,
            font=("Arial", 10, "bold"),
            fg_color=self.ROJO,
            hover_color="#990000",
            corner_radius=4,
            command=lambda: None,
        )
        boton_nuevo_resumen.grid(row=0, column=2, padx=(0, 8))

        boton_nueva_tarea = ctk.CTkButton(
            contenedor_acciones,
            text="Nueva tarea",
            width=120,
            height=28,
            font=("Arial", 10, "bold"),
            fg_color=self.ROJO,
            hover_color="#990000",
            corner_radius=4,
            command=lambda: None,
        )
        boton_nueva_tarea.grid(row=0, column=3)

        contenedor_acciones.grid_remove()

        return {
            "titulo": titulo,
            "mensaje": mensaje,
            "prioridad": prioridad,
            "motivos": motivos,
            "contenedor_acciones": contenedor_acciones,
            "boton_abrir_ficha": boton_abrir_ficha,
            "boton_registrar_cobro": boton_registrar_cobro,
            "boton_nuevo_resumen": boton_nuevo_resumen,
            "boton_nueva_tarea": boton_nueva_tarea,
        }

    def actualizar_dashboard(self):
        try:
            datos = DashboardService.obtener_indicadores()
        except Exception:
            datos = {
                "clientes_activos": 0,
                "total_clientes": 0,
                "resumenes_mes": 0,
                "facturado_mes": 0,
                "cobrado_mes": 0,
                "saldo_pendiente": 0,
                "resumenes_vencidos": 0,
                "servicios_vencidos": 0,
                "proximos_vencimientos": 0,
                "resumenes_pendientes": 0,
                "clientes_con_deuda": 0,
                "total_cobrado_hoy": 0,
                "tareas_hoy": 0,
                "renovaciones_hoy": 0,
                "renovaciones_semana": 0,
                "renovaciones_vencidas": 0,
                "renovados_hoy": 0,
                "agenda": {
                    "pendientes_hoy": 0,
                    "vencidas": 0,
                    "completadas_hoy": 0,
                    "proxima": "Sin tareas",
                },
                "seguimientos": {"hoy": 0, "atrasados": 0, "semana": 0},
                "oportunidades": {"nuevas": 0, "negociacion": 0, "ganadas_mes": 0, "importe_estimado": 0},
                "alertas": {"urgentes": 0, "pendientes": 0, "vencidas": 0},
            }

        claves_moneda = {"facturado_mes", "cobrado_mes", "saldo_pendiente", "total_cobrado_hoy"}
        for clave, etiqueta in self.indicadores.items():
            valor = datos.get(clave, 0)
            if clave in claves_moneda:
                importe_formateado = self.formatear_moneda(valor)
                self.importes_reales[clave] = importe_formateado
                etiqueta.configure(
                    text=importe_formateado if self.importes_visibles.get(clave, True) else "********"
                )
            else:
                etiqueta.configure(text=str(valor))

        self.indicadores_renovacion["hoy"].configure(text=f"Hoy: {datos.get('renovaciones_hoy', 0)}")
        self.indicadores_renovacion["semana"].configure(text=f"Semana: {datos.get('renovaciones_semana', 0)}")
        self.indicadores_renovacion["vencidos"].configure(text=f"Vencidos: {datos.get('renovaciones_vencidas', 0)}")
        self.indicadores_renovacion["renovados"].configure(text=f"Renov.: {datos.get('renovados_hoy', 0)}")

        agenda = datos.get("agenda", {})
        self.indicadores_agenda["pendientes"].configure(text=f"Pendientes: {agenda.get('pendientes_hoy', 0)}")
        self.indicadores_agenda["vencidas"].configure(text=f"Vencidas: {agenda.get('vencidas', 0)}")
        self.indicadores_agenda["completadas"].configure(text=f"Completadas: {agenda.get('completadas_hoy', 0)}")
        self.indicadores_agenda["proxima"].configure(text=f"Próxima: {agenda.get('proxima', 'Sin tareas')}")

        seguimientos = datos.get("seguimientos", {})
        self.indicadores_seguimientos["hoy"].configure(text=f"Contactos para hoy: {seguimientos.get('hoy', 0)}")
        self.indicadores_seguimientos["atrasados"].configure(text=f"Atrasados: {seguimientos.get('atrasados', 0)}")
        self.indicadores_seguimientos["semana"].configure(text=f"Esta semana: {seguimientos.get('semana', 0)}")

        oportunidades = datos.get("oportunidades", {})
        self.indicadores_oportunidades["nuevas"].configure(text=f"Nuevas: {oportunidades.get('nuevas', 0)}")
        self.indicadores_oportunidades["negociacion"].configure(text=f"Negociación: {oportunidades.get('negociacion', 0)}")
        self.indicadores_oportunidades["ganadas_mes"].configure(text=f"Ganadas mes: {oportunidades.get('ganadas_mes', 0)}")
        self.indicadores_oportunidades["importe_estimado"].configure(text=self.formatear_moneda(oportunidades.get('importe_estimado', 0)))

        alertas = datos.get("alertas", {})
        self.indicadores_alertas["urgentes"].configure(text=f"Urgentes: {alertas.get('urgentes', 0)}")
        self.indicadores_alertas["pendientes"].configure(text=f"Pendientes: {alertas.get('pendientes', 0)}")
        self.indicadores_alertas["vencidas"].configure(text=f"Vencidas: {alertas.get('vencidas', 0)}")
        self.tarjeta_alertas.configure(fg_color=self.ROJO if alertas.get("urgentes", 0) else self.NEGRO)

        alertas_prioritarias_valores = {
            "resumenes_vencidos": int(datos.get("resumenes_vencidos", 0) or 0),
            "servicios_vencidos": int(datos.get("servicios_vencidos", 0) or 0),
            "tareas_vencidas": int(agenda.get("vencidas", 0) or 0),
            "seguimientos_atrasados": int(seguimientos.get("atrasados", 0) or 0),
            "clientes_con_deuda": int(datos.get("clientes_con_deuda", 0) or 0),
        }
        for clave, valor in alertas_prioritarias_valores.items():
            self.alertas_prioritarias[clave].configure(
                text=str(valor),
                text_color=self.ROJO if valor > 0 else "#E0E0E0",
            )

        self.actualizar_recomendacion()

        for item in self.tabla_agenda.get_children():
            self.tabla_agenda.delete(item)
        try:
            tareas = TareaService.listar("Hoy")
        except Exception:
            tareas = []
        for tarea in tareas:
            self.tabla_agenda.insert("", "end", values=(tarea[3], tarea[4], tarea[5], tarea[7]))

        for item in self.tabla_vencimientos.get_children():
            self.tabla_vencimientos.delete(item)
        try:
            vencimientos = DashboardService.listar_proximos_vencimientos()
        except Exception:
            vencimientos = []
        for resumen in vencimientos:
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

    def abrir_ficha_cliente_desde_dashboard(self, cliente_id):
        try:
            id_cliente = int(cliente_id)
        except (TypeError, ValueError):
            return

        aplicacion = self.winfo_toplevel()
        if not hasattr(aplicacion, "mostrar_clientes"):
            return

        aplicacion.mostrar_clientes()

        panel = getattr(aplicacion, "panel", None)
        if panel is None or not hasattr(panel, "winfo_children"):
            return

        clientes_frame = None
        for child in panel.winfo_children():
            if hasattr(child, "abrir_ficha_cliente") and hasattr(child, "tabla"):
                clientes_frame = child
                break

        if clientes_frame is None:
            return

        item_objetivo = None
        for item in clientes_frame.tabla.get_children():
            valores = clientes_frame.tabla.item(item, "values")
            if not valores:
                continue
            try:
                fila_id = int(valores[0])
            except (TypeError, ValueError):
                continue
            if fila_id == id_cliente:
                item_objetivo = item
                break

        if item_objetivo is None:
            return

        clientes_frame.tabla.selection_set(item_objetivo)
        clientes_frame.tabla.focus(item_objetivo)
        clientes_frame.abrir_ficha_cliente()

    def actualizar_recomendacion(self):
        try:
            recomendacion = PrioridadService.obtener_recomendacion()
        except Exception:
            recomendacion = {
                "titulo": "Sistema al día",
                "mensaje": "No se detectaron prioridades operativas.",
                "prioridad": "Baja",
                "motivos": [],
            }

        titulo = recomendacion.get("titulo") or ""
        mensaje = recomendacion.get("mensaje") or ""
        prioridad = recomendacion.get("prioridad") or "-"
        cliente_id = recomendacion.get("cliente_id")
        cliente_nombre = str(recomendacion.get("cliente_nombre") or "").strip()
        puntaje = recomendacion.get("puntaje")
        motivos = recomendacion.get("motivos") or []

        if cliente_nombre:
            self.bloque_prioridad["titulo"].configure(text="Te recomiendo comenzar por:")
            self.bloque_prioridad["mensaje"].configure(text=cliente_nombre.upper())
            texto_prioridad = f"Prioridad: {str(prioridad).upper()}"
            if puntaje not in (None, ""):
                texto_prioridad += f"   Puntaje: {puntaje}"
            self.bloque_prioridad["prioridad"].configure(text=texto_prioridad)
            if motivos:
                texto_motivos = "Motivos:\n" + "\n".join(f"• {motivo}" for motivo in motivos)
            else:
                texto_motivos = ""
            self.bloque_prioridad["motivos"].configure(text=texto_motivos)
        else:
            self.bloque_prioridad["titulo"].configure(text=titulo)
            self.bloque_prioridad["mensaje"].configure(text=mensaje)
            self.bloque_prioridad["prioridad"].configure(text=f"Prioridad: {prioridad}")
            if motivos:
                texto_motivos = "\n".join(f"• {motivo}" for motivo in motivos)
            else:
                texto_motivos = ""
            self.bloque_prioridad["motivos"].configure(text=texto_motivos)

        contenedor_acciones = self.bloque_prioridad.get("contenedor_acciones")
        boton_ficha = self.bloque_prioridad.get("boton_abrir_ficha")
        boton_registrar_cobro = self.bloque_prioridad.get("boton_registrar_cobro")
        boton_nuevo_resumen = self.bloque_prioridad.get("boton_nuevo_resumen")
        boton_nueva_tarea = self.bloque_prioridad.get("boton_nueva_tarea")

        if contenedor_acciones is not None:
            if cliente_id not in (None, ""):
                if boton_ficha is not None:
                    boton_ficha.configure(command=lambda cid=cliente_id: self.abrir_ficha_cliente_desde_dashboard(cid))
                if boton_registrar_cobro is not None:
                    boton_registrar_cobro.configure(
                        command=lambda cid=cliente_id: self.abrir_cobros_cliente_desde_dashboard(cid)
                    )
                if boton_nuevo_resumen is not None:
                    boton_nuevo_resumen.configure(
                        command=lambda cid=cliente_id: self.abrir_resumenes_cliente_desde_dashboard(cid)
                    )
                if boton_nueva_tarea is not None:
                    boton_nueva_tarea.configure(
                        command=lambda cid=cliente_id: self.abrir_nueva_tarea_cliente_desde_dashboard(cid)
                    )
                contenedor_acciones.grid()
            else:
                contenedor_acciones.grid_remove()

    def abrir_resumenes_cliente_desde_dashboard(self, cliente_id):
        try:
            id_cliente = int(cliente_id)
        except (TypeError, ValueError):
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_resumenes"):
            aplicacion.mostrar_resumenes(cliente_id=id_cliente, on_cambio=self.actualizar_recomendacion)

    def abrir_cobros_cliente_desde_dashboard(self, cliente_id):
        try:
            id_cliente = int(cliente_id)
        except (TypeError, ValueError):
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_cobros"):
            aplicacion.mostrar_cobros(cliente_id=id_cliente)
            panel = getattr(aplicacion, "panel", None)
            if panel is not None and hasattr(panel, "winfo_children"):
                for child in panel.winfo_children():
                    if hasattr(child, "on_cambio") and hasattr(child, "guardar_formulario"):
                        child.on_cambio = self.actualizar_recomendacion
                        break

    def abrir_nueva_tarea_cliente_desde_dashboard(self, cliente_id):
        try:
            id_cliente = int(cliente_id)
        except (TypeError, ValueError):
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_agenda"):
            aplicacion.mostrar_agenda(cliente_id=id_cliente, nueva_tarea=True)
            panel = getattr(aplicacion, "panel", None)
            if panel is not None and hasattr(panel, "winfo_children"):
                for child in panel.winfo_children():
                    if hasattr(child, "guardar_formulario") and hasattr(child, "abrir_nueva_tarea"):
                        self._instalar_hook_recomendacion_en_agenda(child)
                        break

    def _instalar_hook_recomendacion_en_agenda(self, agenda_frame):
        if getattr(agenda_frame, "_dashboard_recomendacion_hook_instalado", False):
            return

        guardar_original = agenda_frame.guardar_formulario

        def guardar_formulario_con_recomendacion(self, ventana, tarea_original=None):
            guardar_original(ventana, tarea_original)
            if not ventana.winfo_exists():
                self._dashboard_actualizar_recomendacion()

        agenda_frame._dashboard_actualizar_recomendacion = self.actualizar_recomendacion
        agenda_frame.guardar_formulario = MethodType(guardar_formulario_con_recomendacion, agenda_frame)
        agenda_frame._dashboard_recomendacion_hook_instalado = True

    def ir_resumenes(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_resumenes()

    def ir_cobros(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_cobros()

    def ir_cuenta_corriente(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_cobros()

    def ir_cierre_mensual(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_cierre_mensual()

    def ir_agenda(self):
        aplicacion = self.winfo_toplevel()
        aplicacion.mostrar_agenda()

    def ir_crm(self):
        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_crm"):
            aplicacion.mostrar_crm()
            return
        self.registrar_contacto()

    def registrar_contacto(self):
        ContactoFormWindow(self, al_guardar=self.actualizar_dashboard)

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
