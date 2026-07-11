import os
from copy import deepcopy
from tkinter import messagebox, ttk

import customtkinter as ctk

from config import COLOR_BLANCO, COLOR_NEGRO, COLOR_PRINCIPAL
from services.cliente_service import ClienteService
from services.cobro_service import CobroService
from services.contacto_service import ContactoService
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService
from services.tarea_service import TareaService
from services.emisor_fiscal_service import EmisorFiscalService


class FichaClienteFrame(ctk.CTkFrame):
    MOCK_DATA = {
        "datos_generales": {
            "codigo": "",
            "razon_social": "",
            "nombre_comercial": "",
            "responsable": "",
            "cuit": "",
            "iva": "",
            "tipo_factura": "No factura",
            "monotributo_facturacion": "No aplica",
            "telefono": "",
            "whatsapp": "",
            "email": "",
            "direccion": "",
            "localidad": "",
            "estado": "",
        },
        "servicios_activos": [],
        "ultimos_resumenes": [],
        "ultimos_cobros": [],
        "historial_crm": [],
        "proximas_tareas": [],
        "cuenta_corriente": {
            "saldo_pendiente": "",
            "total_cobrado": "",
            "ultimo_cobro": "",
        },
        "observaciones": "",
    }

    def __init__(self, master, cliente_data=None, callbacks=None):
        super().__init__(master, fg_color=COLOR_BLANCO, corner_radius=0)
        self.callbacks = callbacks if callbacks is not None else {}
        self.cliente_data = self._normalizar_cliente_data(cliente_data)
        self._crear_estilo_tablas()
        self._crear_interfaz()
        self.cargar_cliente(self.cliente_data)

    def _normalizar_cliente_data(self, cliente_data):
        datos = deepcopy(self.MOCK_DATA)
        cliente_id = None
        if isinstance(cliente_data, int):
            cliente_id = cliente_data
        elif isinstance(cliente_data, dict):
            cliente_id = cliente_data.get("cliente_id") or cliente_data.get("id")
        elif isinstance(cliente_data, (list, tuple)) and cliente_data:
            primer_valor = cliente_data[0]
            if isinstance(primer_valor, int):
                cliente_id = primer_valor

        if cliente_id:
            fila = ClienteService.obtener(cliente_id)
            if fila:
                datos["datos_generales"].update({
                    "codigo": fila[1],
                    "razon_social": fila[2],
                    "nombre_comercial": fila[3],
                    "responsable": fila[4],
                    "direccion": fila[5],
                    "localidad": fila[6],
                    "telefono": fila[7],
                    "whatsapp": fila[8],
                    "email": fila[9],
                    "cuit": fila[10],
                    "iva": fila[11] if len(fila) > 11 and fila[11] else "Otro",
                    "tipo_factura": fila[12] if len(fila) > 12 and fila[12] else "No factura",
                    "monotributo_facturacion": EmisorFiscalService.resolver_etiqueta(
                        fila[13] if len(fila) > 13 else ""
                    ),
                    "estado": fila[17] if len(fila) > 17 else "",
                })
                observaciones = fila[18] if len(fila) > 18 else ""
                datos["observaciones"] = observaciones or ""

            servicios = ServicioService.listar(cliente_id)
            if servicios:
                datos["servicios_activos"] = [
                    {
                        "servicio": str(servicio[2] or "-"),
                        "estado": servicio[12] or "-",
                        "plan": self._formatear_moneda(servicio[5]) or "-",
                        "vencimiento": servicio[10] or "-",
                    }
                    for servicio in servicios
                ]

            totales = CobroService.totales(cliente_id)
            cobros = CobroService.listar(cliente_id)
            ultimo_cobro = "Sin cobros registrados"
            if cobros:
                ultimo = cobros[0]
                fecha_ultimo = ultimo[2] or "-"
                importe_ultimo = self._formatear_moneda(ultimo[3]) or "-"
                ultimo_cobro = f"{fecha_ultimo} - {importe_ultimo}"

                datos["ultimos_cobros"] = [
                    (
                        cobro[2] or "-",
                        self._formatear_moneda(cobro[3]) or "-",
                        cobro[4] or "-",
                        cobro[6] or "-",
                    )
                    for cobro in cobros[:5]
                ]

            datos["cuenta_corriente"] = {
                "saldo_pendiente": self._formatear_moneda(totales.get("saldo_pendiente")) or "$ 0,00",
                "total_cobrado": self._formatear_moneda(totales.get("total_cobrado")) or "$ 0,00",
                "ultimo_cobro": ultimo_cobro,
            }

            resumenes = ResumenService.listar(cliente_id)
            if resumenes:
                datos["ultimos_resumenes"] = [
                    (
                        resumen[1],
                        resumen[2],
                        self._formatear_moneda(resumen[5]) or "-",
                        resumen[7] or "-",
                        resumen[8] or "",
                        resumen[0],
                    )
                    for resumen in resumenes[:5]
                ]

            contactos = ContactoService.listar(cliente_id=cliente_id)
            if contactos:
                datos["historial_crm"] = [
                    (
                        contacto[2] or "-",
                        contacto[3] or "-",
                        contacto[4] or "-",
                        contacto[5] or "-",
                        contacto[6] or "-",
                    )
                    for contacto in contactos[:5]
                ]

            tareas = TareaService.listar(cliente_id=cliente_id)
            if tareas:
                datos["proximas_tareas"] = [
                    (
                        tarea[2] or "-",
                        tarea[3] or "-",
                        tarea[4] or "-",
                        tarea[5] or "-",
                        tarea[7] or "-",
                    )
                    for tarea in tareas[:5]
                ]

        if not cliente_data:
            return datos

        if isinstance(cliente_data, dict):
            for clave, valor in cliente_data.items():
                if isinstance(valor, dict) and isinstance(datos.get(clave), dict):
                    datos[clave].update(valor)
                elif valor is not None:
                    datos[clave] = valor

        return datos

    def _formatear_moneda(self, valor):
        try:
            importe_parse = valor
            if isinstance(importe_parse, str):
                importe_parse = importe_parse.replace("$", "").replace(" ", "").replace(".", "").replace(",", ".")
            importe_num = float(importe_parse)
            return f"$ {importe_num:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        except (TypeError, ValueError):
            return ""

    def _crear_estilo_tablas(self):
        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except Exception:
            pass

        estilo.configure(
            "FichaCliente.Treeview",
            background=COLOR_BLANCO,
            fieldbackground=COLOR_BLANCO,
            foreground="#202020",
            rowheight=30,
            borderwidth=0,
            font=("Arial", 11),
        )
        estilo.configure(
            "FichaCliente.Treeview.Heading",
            background=COLOR_NEGRO,
            foreground=COLOR_BLANCO,
            relief="flat",
            font=("Arial", 11, "bold"),
        )
        estilo.map(
            "FichaCliente.Treeview",
            background=[("selected", COLOR_PRINCIPAL)],
            foreground=[("selected", COLOR_BLANCO)],
        )
        estilo.map(
            "FichaCliente.Treeview.Heading",
            background=[("active", COLOR_PRINCIPAL)],
        )

    def _crear_interfaz(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._crear_encabezado()

        contenedor = ctk.CTkScrollableFrame(
            self,
            fg_color=COLOR_BLANCO,
            scrollbar_button_color=COLOR_PRINCIPAL,
            scrollbar_button_hover_color="#990000",
        )
        contenedor.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        contenedor.grid_columnconfigure(0, weight=3)
        contenedor.grid_columnconfigure(1, weight=2)

        self._crear_tarjeta_resumen_ejecutivo(contenedor).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 12),
        )
        self._crear_barra_acciones_rapidas(contenedor).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )

        self._crear_panel_izquierdo(contenedor)
        self._crear_panel_derecho(contenedor)

    def _crear_encabezado(self):
        encabezado = ctk.CTkFrame(self, fg_color=COLOR_NEGRO, corner_radius=0, height=88)
        encabezado.grid(row=0, column=0, sticky="ew")
        encabezado.grid_columnconfigure(0, weight=1)

        textos = ctk.CTkFrame(encabezado, fg_color="transparent")
        textos.grid(row=0, column=0, sticky="w", padx=24, pady=16)

        self.titulo_label = ctk.CTkLabel(
            textos,
            text="FICHA ÚNICA DEL CLIENTE",
            font=("Arial", 26, "bold"),
            text_color=COLOR_BLANCO,
        )
        self.titulo_label.pack(anchor="w")

        self.subtitulo_label = ctk.CTkLabel(
            textos,
            text="Vista preliminar",
            font=("Arial", 12, "bold"),
            text_color="#D9D9D9",
        )
        self.subtitulo_label.pack(anchor="w", pady=(4, 0))

        botones = ctk.CTkFrame(encabezado, fg_color="transparent")
        botones.grid(row=0, column=1, sticky="e", padx=24, pady=16)

        acciones = [
            ("Nuevo Resumen", "nuevo_resumen", COLOR_PRINCIPAL),
            ("Registrar Cobro", "registrar_cobro", "#333333"),
            ("Nueva Tarea", "nueva_tarea", "#333333"),
            ("Editar Cliente", "editar_cliente", "#333333"),
            ("WhatsApp", "whatsapp", "#0E6E3A"),
            ("Cerrar", "cerrar", "#6B6B6B"),
        ]

        for indice, (texto, accion, color) in enumerate(acciones):
            boton = ctk.CTkButton(
                botones,
                text=texto,
                width=124,
                height=34,
                fg_color=color,
                hover_color=COLOR_PRINCIPAL if accion != "cerrar" else "#444444",
                command=lambda nombre=accion: self._ejecutar_accion(nombre),
            )
            boton.grid(row=indice // 3, column=indice % 3, padx=4, pady=4)

    def _crear_panel_izquierdo(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=2, column=0, sticky="nsew", padx=(0, 10), pady=(0, 0))
        panel.grid_columnconfigure(0, weight=1)

        self._crear_tarjeta_datos_generales(panel).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._crear_tarjeta_tabla(
            panel,
            titulo="SERVICIOS ACTIVOS",
            columnas=("servicio", "estado", "plan", "vencimiento"),
            encabezados={
                "servicio": ("Servicio", 210),
                "estado": ("Estado", 90),
                "plan": ("Plan", 120),
                "vencimiento": ("Vencimiento", 110),
            },
            atributo_tabla="tabla_servicios",
            altura=5,
        ).grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self._crear_tarjeta_tabla(
            panel,
            titulo="ÚLTIMOS RESÚMENES",
            columnas=("numero", "fecha", "importe", "estado", "pdf_path", "resumen_id"),
            encabezados={
                "numero": ("Resumen", 110),
                "fecha": ("Fecha", 100),
                "importe": ("Importe", 110),
                "estado": ("Estado", 110),
                "pdf_path": ("", 0),
                "resumen_id": ("", 0),
            },
            atributo_tabla="tabla_resumenes",
            altura=5,
        ).grid(row=2, column=0, sticky="nsew")

    def _crear_panel_derecho(self, parent):
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=2, column=1, sticky="nsew", padx=(10, 0), pady=(0, 0))
        panel.grid_columnconfigure(0, weight=1)

        self._crear_tarjeta_proximo_vencimiento(panel).grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._crear_tarjeta_tabla(
            panel,
            titulo="ÚLTIMOS COBROS",
            columnas=("fecha", "importe", "medio", "estado"),
            encabezados={
                "fecha": ("Fecha", 95),
                "importe": ("Importe", 100),
                "medio": ("Medio", 110),
                "estado": ("Estado", 95),
            },
            atributo_tabla="tabla_cobros",
            altura=5,
        ).grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self._crear_tarjeta_tabla(
            panel,
            titulo="CRM / HISTORIAL",
            columnas=("fecha", "hora", "tipo", "resultado", "observaciones"),
            encabezados={
                "fecha": ("Fecha", 90),
                "hora": ("Hora", 70),
                "tipo": ("Tipo", 95),
                "resultado": ("Resultado", 100),
                "observaciones": ("Observaciones", 150),
            },
            atributo_tabla="tabla_crm",
            altura=5,
        ).grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        self._crear_tarjeta_tabla(
            panel,
            titulo="PRÓXIMAS TAREAS",
            columnas=("fecha", "hora", "tipo", "titulo", "estado"),
            encabezados={
                "fecha": ("Fecha", 85),
                "hora": ("Hora", 65),
                "tipo": ("Tipo", 95),
                "titulo": ("Título", 150),
                "estado": ("Estado", 90),
            },
            atributo_tabla="tabla_tareas",
            altura=5,
        ).grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        self._crear_tarjeta_observaciones(panel).grid(row=4, column=0, sticky="nsew")

    def _crear_tarjeta_datos_generales(self, parent):
        tarjeta = self._crear_tarjeta_base(parent, "DATOS GENERALES")
        contenido = ctk.CTkFrame(tarjeta, fg_color="transparent")
        contenido.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        for columna in range(2):
            contenido.grid_columnconfigure(columna, weight=1)

        campos = [
            ("codigo", "Código"),
            ("razon_social", "Razón Social"),
            ("nombre_comercial", "Nombre Comercial"),
            ("responsable", "Responsable"),
            ("cuit", "CUIT"),
            ("iva", "IVA"),
            ("tipo_factura", "Tipo de Factura"),
            ("monotributo_facturacion", "Emisor fiscal"),
            ("telefono", "Teléfono"),
            ("whatsapp", "WhatsApp"),
            ("email", "Email"),
            ("direccion", "Dirección"),
            ("localidad", "Localidad"),
            ("estado", "Estado"),
        ]

        self.labels_datos = {}
        for indice, (clave, titulo) in enumerate(campos):
            fila = indice // 2
            columna = indice % 2
            bloque = ctk.CTkFrame(contenido, fg_color="#F6F6F6", corner_radius=6)
            bloque.grid(row=fila, column=columna, sticky="ew", padx=6, pady=6)
            ctk.CTkLabel(
                bloque,
                text=titulo,
                font=("Arial", 11, "bold"),
                text_color=COLOR_PRINCIPAL,
            ).pack(anchor="w", padx=12, pady=(10, 2))
            valor = ctk.CTkLabel(
                bloque,
                text="-",
                font=("Arial", 12),
                text_color="#1F1F1F",
                justify="left",
                wraplength=240,
            )
            valor.pack(anchor="w", padx=12, pady=(0, 10))
            self.labels_datos[clave] = valor

        fila_servicios = (len(campos) + 1) // 2
        bloque_servicio = ctk.CTkFrame(contenido, fg_color="#F6F6F6", corner_radius=8)
        bloque_servicio.grid(row=fila_servicios, column=0, columnspan=2, sticky="ew", padx=6, pady=(8, 6))

        ctk.CTkLabel(
            bloque_servicio,
            text="Servicios activos",
            font=("Arial", 12, "bold"),
            text_color=COLOR_PRINCIPAL,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.label_servicio_activo = ctk.CTkLabel(
            bloque_servicio,
            text="Sin servicios activos registrados",
            font=("Arial", 12),
            text_color="#1F1F1F",
            justify="left",
            wraplength=520,
        )
        self.label_servicio_activo.pack(anchor="w", padx=12, pady=(0, 4))

        self.label_importe_servicio = ctk.CTkLabel(
            bloque_servicio,
            text="",
            font=("Arial", 12, "bold"),
            text_color="#1F1F1F",
        )
        self.label_importe_servicio.pack(anchor="w", padx=12, pady=(0, 10))

        fila_estado = fila_servicios + 1
        bloque_estado = ctk.CTkFrame(contenido, fg_color="#F6F6F6", corner_radius=8)
        bloque_estado.grid(row=fila_estado, column=0, columnspan=2, sticky="ew", padx=6, pady=(8, 6))

        ctk.CTkLabel(
            bloque_estado,
            text="Estado del Cliente",
            font=("Arial", 12, "bold"),
            text_color=COLOR_PRINCIPAL,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.label_estado_cliente = ctk.CTkLabel(
            bloque_estado,
            text="-",
            font=("Arial", 12, "bold"),
            text_color="#1F1F1F",
            justify="left",
            wraplength=520,
        )
        self.label_estado_cliente.pack(anchor="w", padx=12, pady=(0, 4))

        self.label_faltantes_estado = ctk.CTkLabel(
            bloque_estado,
            text="",
            font=("Arial", 12),
            text_color="#1F1F1F",
            justify="left",
            wraplength=520,
        )
        self.label_faltantes_estado.pack(anchor="w", padx=12, pady=(0, 10))

        contenido.grid_rowconfigure(fila_servicios, weight=0)

        return tarjeta

    def _resolver_emisor_fiscal(self, valor):
        return EmisorFiscalService.resolver_etiqueta(valor)

    def _evaluar_estado_cliente(self, datos_generales, servicios_activos):
        faltantes = []

        def _vacio(valor):
            return str(valor or "").strip() in {"", "-"}

        if _vacio(datos_generales.get("razon_social")):
            faltantes.append("Falta Razón Social")

        if _vacio(datos_generales.get("cuit")):
            faltantes.append("Falta CUIT")

        if _vacio(datos_generales.get("iva")):
            faltantes.append("Falta Condición IVA")

        emisor_fiscal = str(datos_generales.get("monotributo_facturacion") or "").strip()
        if emisor_fiscal in {"", "-", "No aplica"}:
            faltantes.append("Falta Emisor Fiscal")

        tipo_factura = str(datos_generales.get("tipo_factura") or "").strip()
        if tipo_factura in {"", "-", "No factura"}:
            faltantes.append("Falta Tipo de Factura")

        tiene_servicio_activo = any(
            str(servicio.get("estado") or "").strip().lower() == "activo"
            for servicio in servicios_activos
            if isinstance(servicio, dict)
        )
        if not tiene_servicio_activo:
            faltantes.append("Falta al menos un Servicio activo")

        return len(faltantes) == 0, faltantes

    def _crear_tarjeta_proximo_vencimiento(self, parent):
        tarjeta = self._crear_tarjeta_base(parent, "CUENTA CORRIENTE")
        cuerpo = ctk.CTkFrame(tarjeta, fg_color=COLOR_PRINCIPAL, corner_radius=8)
        cuerpo.pack(fill="x", padx=18, pady=(0, 18))

        self.label_vencimiento_fecha = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 20, "bold"),
            text_color=COLOR_BLANCO,
            justify="left",
            wraplength=320,
        )
        self.label_vencimiento_fecha.pack(anchor="w", padx=16, pady=(16, 4))

        self.label_vencimiento_concepto = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 16, "bold"),
            text_color=COLOR_BLANCO,
            justify="left",
            wraplength=320,
        )
        self.label_vencimiento_concepto.pack(anchor="w", padx=16, pady=(6, 0))

        self.label_vencimiento_importe = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 13, "bold"),
            text_color="#FFE7E7",
            justify="left",
            wraplength=320,
        )
        self.label_vencimiento_importe.pack(anchor="w", padx=16, pady=(10, 0))

        self.label_vencimiento_estado = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 12),
            text_color="#FFF2F2",
            justify="left",
            wraplength=320,
        )
        self.label_vencimiento_estado.pack(anchor="w", padx=16, pady=(4, 16))

        return tarjeta

    def _crear_tarjeta_observaciones(self, parent):
        tarjeta = self._crear_tarjeta_base(parent, "OBSERVACIONES")
        self.observaciones_box = ctk.CTkTextbox(
            tarjeta,
            height=210,
            fg_color="#F7F7F7",
            border_width=1,
            border_color="#D6D6D6",
            text_color="#202020",
            wrap="word",
        )
        self.observaciones_box.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.observaciones_box.configure(state="disabled")
        return tarjeta

    def _crear_tarjeta_tabla(self, parent, titulo, columnas, encabezados, atributo_tabla, altura):
        mostrar_boton_emitir = atributo_tabla == "tabla_resumenes"
        tarjeta = self._crear_tarjeta_base(
            parent,
            titulo,
            boton_texto="Emitir factura" if mostrar_boton_emitir else None,
            boton_comando=self._emitir_factura_resumen_seleccionado if mostrar_boton_emitir else None,
        )
        contenedor_tabla = ctk.CTkFrame(tarjeta, fg_color="transparent")
        contenedor_tabla.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        contenedor_tabla.grid_rowconfigure(0, weight=1)
        contenedor_tabla.grid_columnconfigure(0, weight=1)

        tabla = ttk.Treeview(
            contenedor_tabla,
            columns=columnas,
            show="headings",
            height=altura,
            style="FichaCliente.Treeview",
        )
        for columna in columnas:
            texto, ancho = encabezados[columna]
            tabla.heading(columna, text=texto)
            tabla.column(
                columna,
                width=ancho,
                minwidth=0 if columna in ("pdf_path", "resumen_id") else 20,
                anchor="w",
                stretch=columna == columnas[0],
            )

        if atributo_tabla == "tabla_resumenes":
            tabla.bind("<Double-1>", lambda _evento: self._abrir_pdf_resumen_seleccionado())

        scroll = ttk.Scrollbar(contenedor_tabla, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        setattr(self, atributo_tabla, tabla)
        return tarjeta

    def _crear_tarjeta_base(self, parent, titulo, boton_texto=None, boton_comando=None):
        tarjeta = ctk.CTkFrame(parent, fg_color=COLOR_BLANCO, corner_radius=10, border_width=1, border_color="#DADADA")
        encabezado = ctk.CTkFrame(tarjeta, fg_color="transparent")
        encabezado.pack(fill="x", padx=18, pady=(16, 12))
        encabezado.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            encabezado,
            text=titulo,
            font=("Arial", 15, "bold"),
            text_color=COLOR_NEGRO,
        ).grid(row=0, column=0, sticky="w")

        if boton_texto and callable(boton_comando):
            ctk.CTkButton(
                encabezado,
                text=boton_texto,
                width=140,
                height=30,
                fg_color="#333333",
                hover_color="#222222",
                command=boton_comando,
            ).grid(row=0, column=1, sticky="e")

        return tarjeta

    def _crear_tarjeta_resumen_ejecutivo(self, parent):
        tarjeta = self._crear_tarjeta_base(parent, "RESUMEN EJECUTIVO")
        contenido = ctk.CTkFrame(tarjeta, fg_color="transparent")
        contenido.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        for columna in range(3):
            contenido.grid_columnconfigure(columna, weight=1)

        self._resumen_labels = {}
        campos = [
            ("nombre", "Cliente"),
            ("estado", "Estado"),
            ("servicios", "Servicios activos"),
            ("saldo", "Saldo pendiente"),
            ("cobrado", "Total cobrado"),
            ("ultimo", "Último cobro"),
        ]

        for indice, (clave, titulo) in enumerate(campos):
            fila = indice // 3
            columna = indice % 3
            bloque = ctk.CTkFrame(contenido, fg_color="#F6F6F6", corner_radius=6)
            bloque.grid(row=fila, column=columna, sticky="ew", padx=6, pady=6)
            ctk.CTkLabel(
                bloque,
                text=titulo,
                font=("Arial", 11, "bold"),
                text_color=COLOR_PRINCIPAL,
            ).pack(anchor="w", padx=12, pady=(10, 2))
            valor = ctk.CTkLabel(
                bloque,
                text="-",
                font=("Arial", 12),
                text_color="#1F1F1F",
                justify="left",
                wraplength=340,
            )
            valor.pack(anchor="w", padx=12, pady=(0, 10))
            self._resumen_labels[clave] = valor

        return tarjeta

    def _crear_barra_acciones_rapidas(self, parent):
        barra = ctk.CTkFrame(parent, fg_color="transparent")
        barra.grid_columnconfigure(0, weight=0)

        ctk.CTkButton(
            barra,
            text="Editar Cliente",
            width=150,
            height=34,
            fg_color="#333333",
            hover_color="#222222",
            command=lambda: self._ejecutar_accion("editar_cliente"),
        ).grid(row=0, column=0, sticky="w")

        return barra

    def cargar_cliente(self, cliente_data):
        self.cliente_data = self._normalizar_cliente_data(cliente_data)

        datos_generales = self.cliente_data.get("datos_generales", {})
        razon_social = datos_generales.get("razon_social") or "Cliente sin nombre"
        codigo = datos_generales.get("codigo") or "S/C"
        self.titulo_label.configure(text=f"FICHA ÚNICA DEL CLIENTE · {razon_social}")
        self.subtitulo_label.configure(text=f"Código {codigo} · Estado {datos_generales.get('estado', 'Sin definir')}")

        for clave, label in self.labels_datos.items():
            label.configure(text=datos_generales.get(clave) or "-")

        servicios_activos = self.cliente_data.get("servicios_activos", [])
        cuenta_corriente = self.cliente_data.get("cuenta_corriente", {})

        self._resumen_labels["nombre"].configure(text=razon_social)
        self._resumen_labels["estado"].configure(text=datos_generales.get("estado") or "-")
        self._resumen_labels["servicios"].configure(text=str(len(servicios_activos)))
        self._resumen_labels["saldo"].configure(
            text=cuenta_corriente.get("saldo_pendiente") or "$ 0,00"
        )
        self._resumen_labels["cobrado"].configure(
            text=cuenta_corriente.get("total_cobrado") or "$ 0,00"
        )
        self._resumen_labels["ultimo"].configure(
            text=cuenta_corriente.get("ultimo_cobro") or "Sin cobros registrados"
        )

        if servicios_activos:
            primer_servicio = servicios_activos[0]
            self.label_servicio_activo.configure(text=primer_servicio.get("servicio") or "-")
            plan = primer_servicio.get("plan") or ""
            if plan and plan != "-":
                self.label_importe_servicio.configure(text=f"Importe: {plan}")
            else:
                self.label_importe_servicio.configure(text="")
        else:
            self.label_servicio_activo.configure(text="Sin servicios activos.")
            self.label_importe_servicio.configure(text="")

        cliente_listo, faltantes = self._evaluar_estado_cliente(datos_generales, servicios_activos)
        if cliente_listo:
            self.label_estado_cliente.configure(
                text="🟢 Cliente listo para facturación.",
                text_color="#0E6E3A",
            )
            self.label_faltantes_estado.configure(text="")
        else:
            self.label_estado_cliente.configure(
                text="🟡 Faltan datos administrativos.",
                text_color="#8A6D00",
            )
            self.label_faltantes_estado.configure(text="\n".join(f"• {item}" for item in faltantes))

        self._cargar_tabla(self.tabla_servicios, servicios_activos)
        self._cargar_tabla(
            self.tabla_resumenes,
            self.cliente_data.get("ultimos_resumenes", []),
            fila_vacia=("Sin registros", "-", "-", "-", "", ""),
        )
        self._cargar_tabla(self.tabla_cobros, self.cliente_data.get("ultimos_cobros", []))
        self._cargar_tabla(self.tabla_crm, self.cliente_data.get("historial_crm", []))
        self._cargar_tabla(
            self.tabla_tareas,
            self.cliente_data.get("proximas_tareas", []),
            fila_vacia=("Sin tareas programadas", "", "", "", ""),
        )

        self.label_vencimiento_fecha.configure(
            text=f"Saldo pendiente: {cuenta_corriente.get('saldo_pendiente') or '$ 0,00'}"
        )
        self.label_vencimiento_concepto.configure(
            text=f"Total cobrado: {cuenta_corriente.get('total_cobrado') or '$ 0,00'}"
        )
        self.label_vencimiento_importe.configure(
            text=f"Último cobro: {cuenta_corriente.get('ultimo_cobro') or 'Sin cobros registrados'}"
        )
        self.label_vencimiento_estado.configure(text="")

        self.observaciones_box.configure(state="normal")
        self.observaciones_box.delete("1.0", "end")
        self.observaciones_box.insert("1.0", self.cliente_data.get("observaciones") or "Sin observaciones registradas.")
        self.observaciones_box.configure(state="disabled")

    def _cargar_tabla(self, tabla, filas, fila_vacia=("Sin registros", "-", "-", "-")):
        for item in tabla.get_children():
            tabla.delete(item)

        if filas:
            for fila in filas:
                if isinstance(fila, dict):
                    tabla.insert(
                        "",
                        "end",
                        values=(
                            fila.get("servicio", "-"),
                            fila.get("estado", "-"),
                            fila.get("plan", "-"),
                            fila.get("vencimiento", "-"),
                        ),
                    )
                else:
                    tabla.insert("", "end", values=fila)
            return

        tabla.insert("", "end", values=fila_vacia)

    def _abrir_pdf_resumen_seleccionado(self):
        seleccion = self.tabla_resumenes.selection()
        if not seleccion:
            return

        valores = self.tabla_resumenes.item(seleccion[0], "values")
        pdf_path = valores[4] if len(valores) > 4 else ""
        if not pdf_path:
            messagebox.showinfo(
                "Resumen sin PDF",
                "El resumen no tiene PDF asociado.",
                parent=self.winfo_toplevel(),
            )
            return

        try:
            os.startfile(pdf_path)
        except OSError as error:
            messagebox.showerror(
                "Error",
                f"No se pudo abrir el PDF: {error}",
                parent=self.winfo_toplevel(),
            )

    def _emitir_factura_resumen_seleccionado(self):
        seleccion = self.tabla_resumenes.selection()
        if not seleccion:
            messagebox.showwarning(
                "Emitir factura",
                "Seleccione un resumen para continuar.",
                parent=self.winfo_toplevel(),
            )
            return

        valores = self.tabla_resumenes.item(seleccion[0], "values")
        try:
            resumen_id = int(valores[5]) if len(valores) > 5 and str(valores[5]).strip() else None
        except (TypeError, ValueError):
            resumen_id = None

        diagnostico = self._construir_diagnostico_facturacion(resumen_id)
        self._mostrar_diagnostico_facturacion(diagnostico)

    def _construir_diagnostico_facturacion(self, resumen_id):
        checklist = []
        faltantes_cliente = False
        faltantes_emisor = False

        resumen = ResumenService.obtener(resumen_id) if resumen_id is not None else None
        resumen_ok = resumen is not None
        checklist.append({
            "ok": resumen_ok,
            "correcto": "Resumen seleccionado",
            "error": "Falta / Incorrecto: resumen seleccionado",
        })

        cliente_fila = ClienteService.obtener(resumen.cliente_id) if resumen_ok else None
        razon_social = str(cliente_fila[2] if cliente_fila and len(cliente_fila) > 2 else "" or "").strip()
        cuit_cliente = str(cliente_fila[10] if cliente_fila and len(cliente_fila) > 10 else "" or "").strip()
        iva_cliente = str(cliente_fila[11] if cliente_fila and len(cliente_fila) > 11 else "" or "").strip()
        tipo_factura_cliente = str(cliente_fila[12] if cliente_fila and len(cliente_fila) > 12 else "" or "").strip()
        referencia_emisor = str(cliente_fila[13] if cliente_fila and len(cliente_fila) > 13 else "" or "").strip()

        razon_social_ok = bool(razon_social)
        checklist.append({
            "ok": razon_social_ok,
            "correcto": "Razón social",
            "error": "Falta / Incorrecto: razón social",
        })
        if not razon_social_ok:
            faltantes_cliente = True

        cuit_cliente_ok = bool(cuit_cliente)
        checklist.append({
            "ok": cuit_cliente_ok,
            "correcto": "CUIT del cliente",
            "error": "Falta / Incorrecto: CUIT del cliente",
        })
        if not cuit_cliente_ok:
            faltantes_cliente = True

        iva_cliente_ok = bool(iva_cliente)
        checklist.append({
            "ok": iva_cliente_ok,
            "correcto": "Condición IVA",
            "error": "Falta / Incorrecto: condición IVA",
        })
        if not iva_cliente_ok:
            faltantes_cliente = True

        tipo_factura_ok = tipo_factura_cliente in {"Factura A", "Factura C"}
        checklist.append({
            "ok": tipo_factura_ok,
            "correcto": "Tipo de factura",
            "error": "Falta / Incorrecto: tipo de factura (debe ser Factura A o Factura C)",
        })
        if not tipo_factura_ok:
            faltantes_cliente = True

        emisor_id = self._resolver_emisor_id_desde_referencia(referencia_emisor)
        emisor_asignado_ok = bool(emisor_id)
        checklist.append({
            "ok": emisor_asignado_ok,
            "correcto": "Emisor fiscal",
            "error": "Falta / Incorrecto: emisor fiscal",
        })
        if not emisor_asignado_ok:
            faltantes_cliente = True

        emisor = EmisorFiscalService.obtener(emisor_id) if emisor_id else None
        cuit_emisor = str(emisor[3] if emisor and len(emisor) > 3 else "" or "").strip()
        punto_venta_emisor = str(emisor[6] if emisor and len(emisor) > 6 else "" or "").strip()

        cuit_emisor_ok = bool(cuit_emisor)
        checklist.append({
            "ok": cuit_emisor_ok,
            "correcto": "CUIT del emisor",
            "error": "Falta / Incorrecto: CUIT del emisor",
        })
        if not cuit_emisor_ok:
            faltantes_emisor = True

        punto_venta_ok = bool(punto_venta_emisor)
        checklist.append({
            "ok": punto_venta_ok,
            "correcto": "Punto de venta",
            "error": "Falta / Incorrecto: punto de venta",
        })
        if not punto_venta_ok:
            faltantes_emisor = True

        total_resumen = 0
        if resumen is not None:
            try:
                total_resumen = float(resumen.total or 0)
            except (TypeError, ValueError):
                total_resumen = 0
        importe_ok = total_resumen > 0
        checklist.append({
            "ok": importe_ok,
            "correcto": "Importe del resumen",
            "error": "Falta / Incorrecto: importe del resumen",
        })

        estado_facturacion = str(resumen.estado_facturacion if resumen else "" or "").strip().lower()
        estado_facturacion_ok = bool(resumen) and estado_facturacion != "facturado"
        checklist.append({
            "ok": estado_facturacion_ok,
            "correcto": "Estado de facturación del resumen",
            "error": "Falta / Incorrecto: el resumen ya figura como facturado",
        })

        validacion_arca = {"completa": False, "faltantes": [], "errores": []}
        if emisor_id:
            validacion_arca = EmisorFiscalService.validar_configuracion_arca(emisor_id)

        faltantes_arca = set(validacion_arca.get("faltantes") or [])
        errores_arca = set(validacion_arca.get("errores") or [])

        certificado_ok = (
            "Falta ruta del certificado digital" not in faltantes_arca
            and "No existe el archivo del certificado digital." not in errores_arca
            and emisor_id is not None
        )
        checklist.append({
            "ok": certificado_ok,
            "correcto": "Certificado ARCA",
            "error": "Falta / Incorrecto: certificado ARCA",
        })

        clave_ok = (
            "Falta ruta de la clave privada" not in faltantes_arca
            and "No existe el archivo de la clave privada." not in errores_arca
            and emisor_id is not None
        )
        checklist.append({
            "ok": clave_ok,
            "correcto": "Clave privada",
            "error": "Falta / Incorrecto: clave privada",
        })

        carpeta_ok = (
            "Falta carpeta de facturas" not in faltantes_arca
            and "No existe la carpeta de facturas." not in errores_arca
            and emisor_id is not None
        )
        checklist.append({
            "ok": carpeta_ok,
            "correcto": "Carpeta de facturas",
            "error": "Falta / Incorrecto: carpeta de facturas",
        })

        configuracion_arca_ok = bool(validacion_arca.get("completa")) and emisor_id is not None
        checklist.append({
            "ok": configuracion_arca_ok,
            "correcto": "Configuración ARCA del emisor",
            "error": "Falta / Incorrecto: configuración ARCA del emisor",
        })

        if not (certificado_ok and clave_ok and carpeta_ok and configuracion_arca_ok):
            faltantes_emisor = True

        preparada = all(item["ok"] for item in checklist)
        return {
            "preparada": preparada,
            "checklist": checklist,
            "faltantes_cliente": faltantes_cliente,
            "faltantes_emisor": faltantes_emisor,
        }

    def _mostrar_diagnostico_facturacion(self, diagnostico):
        modal = ctk.CTkToplevel(self)
        modal.title("Diagnóstico de facturación")
        modal.geometry("760x620")
        modal.minsize(700, 560)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        contenedor = ctk.CTkFrame(modal, fg_color=COLOR_BLANCO)
        contenedor.pack(fill="both", expand=True, padx=16, pady=16)
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            contenedor,
            text="Diagnóstico de facturación",
            font=("Arial", 20, "bold"),
            text_color=COLOR_NEGRO,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        if diagnostico.get("preparada"):
            estado_texto = (
                "Factura preparada para emitir\n"
                "La conexión real con ARCA todavía no está habilitada."
            )
            estado_color = "#0E6E3A"
        else:
            estado_texto = "Factura no preparada para emitir"
            estado_color = "#A11A1A"

        ctk.CTkLabel(
            contenedor,
            text=estado_texto,
            font=("Arial", 13, "bold"),
            justify="left",
            text_color=estado_color,
        ).grid(row=0, column=0, sticky="e", pady=(0, 6))

        lista = ctk.CTkScrollableFrame(contenedor, fg_color="#F6F6F6")
        lista.grid(row=1, column=0, sticky="nsew", pady=(8, 12))
        lista.grid_columnconfigure(0, weight=1)

        for indice, item in enumerate(diagnostico.get("checklist", [])):
            texto = f"✓ {item['correcto']}" if item.get("ok") else f"✗ {item['error']}"
            color = "#0E6E3A" if item.get("ok") else "#A11A1A"
            ctk.CTkLabel(
                lista,
                text=texto,
                font=("Arial", 12),
                text_color=color,
                justify="left",
                anchor="w",
            ).grid(row=indice, column=0, sticky="ew", padx=10, pady=(6 if indice == 0 else 4, 2))

        acciones = ctk.CTkFrame(contenedor, fg_color="transparent")
        acciones.grid(row=2, column=0, sticky="e")

        columna = 0
        if diagnostico.get("faltantes_cliente"):
            ctk.CTkButton(
                acciones,
                text="Editar cliente",
                width=140,
                fg_color="#333333",
                hover_color="#222222",
                command=lambda: self._abrir_edicion_cliente_desde_diagnostico(modal),
            ).grid(row=0, column=columna, padx=(0, 8))
            columna += 1

        if diagnostico.get("faltantes_emisor"):
            ctk.CTkButton(
                acciones,
                text="Configurar emisor",
                width=160,
                fg_color="#333333",
                hover_color="#222222",
                command=self._abrir_configuracion_emisores_desde_diagnostico,
            ).grid(row=0, column=columna, padx=(0, 8))
            columna += 1

        ctk.CTkButton(
            acciones,
            text="Cerrar",
            width=110,
            fg_color="#666666",
            hover_color="#444444",
            command=modal.destroy,
        ).grid(row=0, column=columna)

    def _abrir_edicion_cliente_desde_diagnostico(self, modal):
        modal.destroy()
        callback = self.callbacks.get("editar_cliente")
        if callable(callback):
            callback(self.cliente_data)
            return

        messagebox.showinfo(
            "Acción no disponible",
            "No hay un flujo de edición de cliente configurado desde esta vista.",
            parent=self.winfo_toplevel(),
        )

    def _abrir_configuracion_emisores_desde_diagnostico(self):
        try:
            from views.emisores_fiscales import EmisoresFiscalesWindow
        except Exception as error:
            messagebox.showerror(
                "Emisores Fiscales",
                f"No se pudo abrir la configuración de emisores.\n{error}",
                parent=self.winfo_toplevel(),
            )
            return

        EmisoresFiscalesWindow(self.winfo_toplevel())

    def _resolver_emisor_id_desde_referencia(self, referencia_emisor):
        texto = str(referencia_emisor or "").strip()
        if not texto or texto == "No aplica":
            return None

        if texto.startswith("EMISOR:"):
            try:
                return int(texto.split(":", 1)[1])
            except (TypeError, ValueError):
                return None

        if texto in ("Monotributo 1", "Monotributo 2"):
            indice = 0 if texto.endswith("1") else 1
            emisores = EmisorFiscalService.listar_activos_ordenados_por_id()
            if len(emisores) > indice:
                return emisores[indice][0]
            return None

        for emisor in EmisorFiscalService.listar():
            if texto == EmisorFiscalService.etiqueta_visible(emisor):
                return emisor[0]
        return None

    def _ejecutar_accion(self, nombre_accion):
        callback = self.callbacks.get(nombre_accion)
        if callable(callback):
            callback(self.cliente_data)
            return

        if nombre_accion == "cerrar":
            contenedor = self.winfo_toplevel()
            if contenedor is self:
                self.destroy()
            elif hasattr(contenedor, "destroy"):
                contenedor.destroy()
            return

        messagebox.showinfo(
            "Acción no disponible",
            "Esta acción todavía no está disponible.",
            parent=self.winfo_toplevel(),
        )