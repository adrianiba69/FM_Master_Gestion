import os
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from config import COLOR_BLANCO, COLOR_NEGRO, COLOR_PRINCIPAL
from pdf.nombre_archivos import nombre_factura_pdf
from pdf.resumen_pdf import ResumenPDF
from services.cliente_service import ClienteService
from services.cobro_service import CobroService
from services.contacto_service import ContactoService
from services.arca.homologacion_service import HomologacionService
from services.arca.pdf_fiscal_service import PDFFiscalService
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
            "modalidad_comprobante": "Solo Resumen",
            "emisor_habitual": "FM Master 98.3",
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
        self.factura_emitida_temporal = {}
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
                    "modalidad_comprobante": fila[21] if len(fila) > 21 and fila[21] else "Solo Resumen",
                    "emisor_habitual": fila[22] if len(fila) > 22 and fila[22] else "FM Master 98.3",
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
        self._crear_tarjeta_comprobantes(panel).grid(row=4, column=0, sticky="nsew", pady=(0, 12))
        self._crear_tarjeta_observaciones(panel).grid(row=5, column=0, sticky="nsew")

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

    def _crear_tarjeta_comprobantes(self, parent):
        tarjeta = self._crear_tarjeta_base(parent, "COMPROBANTES")
        cuerpo = ctk.CTkFrame(tarjeta, fg_color="#F7F7F7", corner_radius=8)
        cuerpo.pack(fill="x", padx=18, pady=(0, 18))

        ctk.CTkLabel(
            cuerpo,
            text="Modalidad",
            font=("Arial", 12, "bold"),
            text_color=COLOR_PRINCIPAL,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        self.label_modalidad_comprobante = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 12),
            text_color="#1F1F1F",
            justify="left",
            wraplength=320,
        )
        self.label_modalidad_comprobante.pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            cuerpo,
            text="Emisor habitual",
            font=("Arial", 12, "bold"),
            text_color=COLOR_PRINCIPAL,
        ).pack(anchor="w", padx=12, pady=(4, 2))
        self.label_emisor_habitual = ctk.CTkLabel(
            cuerpo,
            text="-",
            font=("Arial", 12),
            text_color="#1F1F1F",
            justify="left",
            wraplength=320,
        )
        self.label_emisor_habitual.pack(anchor="w", padx=12, pady=(0, 10))

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

        self.label_modalidad_comprobante.configure(
            text=datos_generales.get("modalidad_comprobante") or "Solo Resumen"
        )
        self.label_emisor_habitual.configure(
            text=datos_generales.get("emisor_habitual") or "FM Master 98.3"
        )

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
        try:
            resumen_id = int(valores[5]) if len(valores) > 5 and str(valores[5]).strip() else None
        except (TypeError, ValueError):
            resumen_id = None
        pdf_path = valores[4] if len(valores) > 4 else ""
        if not pdf_path and resumen_id is None:
            messagebox.showinfo(
                "Resumen sin PDF",
                "El resumen no tiene PDF asociado.",
                parent=self.winfo_toplevel(),
            )
            return

        try:
            if resumen_id is not None:
                ruta_pdf = ResumenPDF.obtener_ruta_pdf_resumen(resumen_id, regenerar_si_falta=True)
            else:
                ruta_pdf = str(pdf_path)
            os.startfile(ruta_pdf)
        except OSError as error:
            messagebox.showerror(
                "Error",
                f"No se pudo abrir el PDF: {error}",
                parent=self.winfo_toplevel(),
            )
        except ValueError as error:
            messagebox.showerror(
                "Error",
                str(error),
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

        # Obtener explícitamente los datos del emisor para pasar al validador
        # Recargar el emisor JUSTO AHORA para asegurar que tenemos la versión actualizada
        validacion_arca = {"completa": False, "faltantes": [], "errores": []}
        configuracion_arca_ok = False
        
        if emisor_id:
            # Recargar el emisor actualizado desde la BD (no usar versión anterior)
            emisor = EmisorFiscalService.obtener(emisor_id)
            
        if emisor_id and emisor:
            ruta_certificado = str(emisor[10] if len(emisor) > 10 else "" or "").strip()
            ruta_clave_privada = str(emisor[11] if len(emisor) > 11 else "" or "").strip()
            carpeta_facturas = str(emisor[12] if len(emisor) > 12 else "" or "").strip()
            ambiente_arca = str(emisor[9] if len(emisor) > 9 else "" or "").strip()
            
            # Reutilizar exactamente la misma validación que Emisores Fiscales
            validacion_arca = EmisorFiscalService.validar_configuracion_arca(
                emisor_id,
                ruta_certificado=ruta_certificado,
                ruta_clave_privada=ruta_clave_privada,
                carpeta_facturas=carpeta_facturas,
                ambiente_arca=ambiente_arca,
            )
            configuracion_arca_ok = bool(validacion_arca.get("completa"))
        
        # Agregar un solo ítem de validación ARCA que refleja el resultado completo
        checklist.append({
            "ok": configuracion_arca_ok,
            "correcto": "Configuración ARCA del emisor",
            "error": "Falta / Incorrecto: configuración ARCA del emisor",
        })

        if not configuracion_arca_ok:
            faltantes_emisor = True

        cliente_validado = razon_social_ok and cuit_cliente_ok and iva_cliente_ok and tipo_factura_ok and emisor_asignado_ok
        emisor_validado = emisor_asignado_ok and cuit_emisor_ok and punto_venta_ok
        resumen_disponible = resumen_ok and importe_ok and estado_facturacion_ok

        preparada = all(item["ok"] for item in checklist)
        return {
            "preparada": preparada,
            "checklist": checklist,
            "faltantes_cliente": faltantes_cliente,
            "faltantes_emisor": faltantes_emisor,
            "detalle": {
                "resumen_id": resumen.id if resumen is not None else None,
                "emisor_id": emisor_id,
                "cliente": razon_social or "-",
                "cuit_cliente": cuit_cliente or "-",
                "resumen_numero": str(resumen.numero) if resumen is not None else "-",
                "resumen_fecha": str(resumen.fecha or "-") if resumen is not None else "-",
                "importe_total": self._formatear_moneda(total_resumen) or "-",
                "emisor": EmisorFiscalService.etiqueta_visible(emisor) if emisor is not None else "-",
                "cuit_emisor": cuit_emisor or "-",
                "tipo_factura": tipo_factura_cliente or "-",
                "punto_venta": punto_venta_emisor or "-",
                "ambiente_arca": str(emisor[9] if emisor and len(emisor) > 9 else "" or "-").strip() or "-",
            },
            "estado_confirmacion": {
                "cliente_validado": cliente_validado,
                "emisor_validado": emisor_validado,
                "configuracion_arca_validada": configuracion_arca_ok,
                "resumen_disponible": resumen_disponible,
            },
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

        if diagnostico.get("preparada"):
            ctk.CTkButton(
                acciones,
                text="Continuar",
                width=120,
                fg_color=COLOR_PRINCIPAL,
                hover_color="#990000",
                command=lambda: self._abrir_confirmacion_factura_preparada(modal, diagnostico),
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

    def _abrir_confirmacion_factura_preparada(self, modal_diagnostico, diagnostico):
        modal_diagnostico.destroy()
        self._mostrar_confirmacion_factura_preparada(diagnostico)

    def _mostrar_confirmacion_factura_preparada(self, diagnostico):
        detalle = diagnostico.get("detalle", {})
        estado = diagnostico.get("estado_confirmacion", {})

        modal = ctk.CTkToplevel(self)
        modal.title("Factura lista para emitir")
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
            text="Factura lista para emitir",
            font=("Arial", 20, "bold"),
            text_color=COLOR_NEGRO,
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        cuerpo = ctk.CTkScrollableFrame(contenedor, fg_color="#F6F6F6")
        cuerpo.grid(row=1, column=0, sticky="nsew", pady=(8, 12))
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_columnconfigure(1, weight=1)

        datos = [
            ("Cliente", detalle.get("cliente", "-")),
            ("CUIT del cliente", detalle.get("cuit_cliente", "-")),
            ("Resumen seleccionado", detalle.get("resumen_numero", "-")),
            ("Fecha del resumen", detalle.get("resumen_fecha", "-")),
            ("Importe total", detalle.get("importe_total", "-")),
            ("Emisor fiscal", detalle.get("emisor", "-")),
            ("CUIT del emisor", detalle.get("cuit_emisor", "-")),
            ("Tipo de factura", detalle.get("tipo_factura", "-")),
            ("Punto de venta", detalle.get("punto_venta", "-")),
            ("Ambiente ARCA", detalle.get("ambiente_arca", "-")),
        ]

        for indice, (etiqueta, valor) in enumerate(datos):
            fila = indice // 2
            columna = indice % 2
            bloque = ctk.CTkFrame(cuerpo, fg_color=COLOR_BLANCO, corner_radius=8, border_width=1, border_color="#DADADA")
            bloque.grid(row=fila, column=columna, sticky="ew", padx=8, pady=6)
            ctk.CTkLabel(
                bloque,
                text=etiqueta,
                font=("Arial", 11, "bold"),
                text_color=COLOR_PRINCIPAL,
            ).pack(anchor="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(
                bloque,
                text=valor,
                font=("Arial", 12),
                text_color="#1F1F1F",
                justify="left",
                wraplength=300,
            ).pack(anchor="w", padx=12, pady=(0, 10))

        inicio_checklist = (len(datos) + 1) // 2
        estado_items = [
            (estado.get("cliente_validado", False), "Cliente validado"),
            (estado.get("emisor_validado", False), "Emisor validado"),
            (estado.get("configuracion_arca_validada", False), "Configuración ARCA validada"),
            (estado.get("resumen_disponible", False), "Resumen disponible"),
        ]

        estado_frame = ctk.CTkFrame(cuerpo, fg_color=COLOR_BLANCO, corner_radius=8, border_width=1, border_color="#DADADA")
        estado_frame.grid(row=inicio_checklist, column=0, columnspan=2, sticky="ew", padx=8, pady=(10, 6))
        ctk.CTkLabel(
            estado_frame,
            text="Estado",
            font=("Arial", 12, "bold"),
            text_color=COLOR_PRINCIPAL,
        ).pack(anchor="w", padx=12, pady=(10, 6))

        for ok, texto in estado_items:
            prefijo = "✓" if ok else "✗"
            color = "#0E6E3A" if ok else "#A11A1A"
            ctk.CTkLabel(
                estado_frame,
                text=f"{prefijo} {texto}",
                font=("Arial", 12),
                text_color=color,
                justify="left",
            ).pack(anchor="w", padx=12, pady=2)

        acciones = ctk.CTkFrame(contenedor, fg_color="transparent")
        acciones.grid(row=2, column=0, sticky="e")

        ctk.CTkButton(
            acciones,
            text="Volver",
            width=110,
            fg_color="#333333",
            hover_color="#222222",
            command=lambda: self._volver_a_diagnostico_desde_confirmacion(modal, diagnostico),
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            acciones,
            text="Cerrar",
            width=110,
            fg_color="#666666",
            hover_color="#444444",
            command=modal.destroy,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            acciones,
            text="Emitir factura",
            width=130,
            fg_color=COLOR_PRINCIPAL,
            hover_color="#990000",
            command=lambda: self._emitir_factura_desde_confirmacion(modal, diagnostico),
        ).grid(row=0, column=2)

    def _volver_a_diagnostico_desde_confirmacion(self, modal_confirmacion, diagnostico):
        modal_confirmacion.destroy()
        self._mostrar_diagnostico_facturacion(diagnostico)

    def _informar_emision_no_habilitada(self):
        messagebox.showinfo(
            "Emitir factura",
            "La conexión real con ARCA todavía no está habilitada.\n\nNo se realizó ninguna emisión.",
            parent=self.winfo_toplevel(),
        )

    def _emitir_factura_desde_confirmacion(self, modal_confirmacion, diagnostico):
        detalle = diagnostico.get("detalle", {})
        resumen_id = detalle.get("resumen_id")
        emisor_id = detalle.get("emisor_id")

        if resumen_id is None or emisor_id is None:
            messagebox.showerror(
                "Emitir factura",
                "Falta información del resumen o del emisor para continuar.",
                parent=modal_confirmacion,
            )
            return

        resumen = ResumenService.obtener(resumen_id)
        if resumen is None:
            messagebox.showerror(
                "Emitir factura",
                "No se encontró el resumen seleccionado.",
                parent=modal_confirmacion,
            )
            return

        cliente_fila = ClienteService.obtener(resumen.cliente_id)
        emisor = EmisorFiscalService.obtener(emisor_id)
        if cliente_fila is None or emisor is None:
            messagebox.showerror(
                "Emitir factura",
                "No se pudieron recuperar los datos del cliente o del emisor.",
                parent=modal_confirmacion,
            )
            return

        tipo_factura = str(cliente_fila[12] if len(cliente_fila) > 12 else "" or "").strip()
        if tipo_factura != "Factura C":
            messagebox.showerror(
                "Emitir factura",
                "Esta integración solo emite Factura C en Homologación.",
                parent=modal_confirmacion,
            )
            return

        # IMPORTANTE: Usar fecha fiscal actual del sistema
        from datetime import datetime
        fecha_comprobante = datetime.now().strftime("%Y%m%d")

        cuit_emisor = str(emisor[3] if len(emisor) > 3 else "" or "").strip()
        punto_venta = emisor[6] if len(emisor) > 6 else ""
        ruta_certificado = str(emisor[10] if len(emisor) > 10 else "" or "").strip()
        ruta_clave = str(emisor[11] if len(emisor) > 11 else "" or "").strip()
        carpeta_facturas = str(emisor[12] if len(emisor) > 12 else "" or "").strip()

        cuit_emisor_normalizado = self._normalizar_cuit_emisor(cuit_emisor)
        punto_venta_normalizado = self._normalizar_punto_venta(punto_venta)
        
        try:
            # Validar que la normalización fue exitosa
            if cuit_emisor_normalizado is None:
                messagebox.showerror(
                    "Emitir factura",
                    f"CUIT del emisor inválido o mal formado: {repr(cuit_emisor)}",
                    parent=modal_confirmacion,
                )
                return
            
            if punto_venta_normalizado is None:
                messagebox.showerror(
                    "Emitir factura",
                    f"Punto de venta inválido o mal formado: {repr(punto_venta)}",
                    parent=modal_confirmacion,
                )
                return

            cuit_o_doc = str(cliente_fila[10] if len(cliente_fila) > 10 else "" or "").strip()
            condicion_iva_receptor = str(cliente_fila[11] if len(cliente_fila) > 11 else "" or "").strip()
            
            # Normalizar condición IVA a minúsculas para comparación
            condicion_iva_normalizada = str(condicion_iva_receptor or "").strip().lower()
            
            # Normalizar número a solo dígitos
            documento_normalizado = ''.join(c for c in cuit_o_doc if c.isdigit())
            
            if documento_normalizado and len(documento_normalizado) == 11:
                # Consumidor Final: extraer DNI central del CUIL y usar DocTipo 96
                if condicion_iva_normalizada == "consumidor final":
                    # Extraer dígitos centrales: posiciones 2 a 9 (11 dígitos totales)
                    # Ejemplo: 27502653436 → 50265343
                    tipo_documento = 96
                    documento_receptor = int(documento_normalizado[2:-1])
                else:
                    # Otros: usar como CUIT (DocTipo 80)
                    tipo_documento = 80
                    documento_receptor = int(documento_normalizado)
            else:
                tipo_documento = 99
                documento_receptor = 0

            print("DEBUG RECEPTOR - condicion_iva_receptor repr:", repr(condicion_iva_normalizada))
            print("DEBUG RECEPTOR - DocTipo:", tipo_documento)
            print("DEBUG RECEPTOR - DocNro:", documento_receptor)

            emision = HomologacionService.emitir_factura_c_prueba(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta=punto_venta_normalizado,
                condicion_iva_receptor_id=5,
                concepto=1,
                tipo_documento=tipo_documento,
                documento_receptor=documento_receptor,
                importe_total=resumen.total,
                importe_neto=resumen.total,
                importe_iva=0.0,
                importe_exento=0.0,
                fecha_comprobante=fecha_comprobante,
                carpeta_trabajo=carpeta_facturas,
            )

            if not emision.get("ok"):
                messagebox.showerror(
                    "Emitir factura",
                    self._mensaje_errores_emision(emision),
                    parent=modal_confirmacion,
                )
                return

            numero_emitido = int(emision.get("numero_comprobante") or 0)
            
            consulta = HomologacionService.consultar_comprobante_emitido(
                ruta_certificado=ruta_certificado,
                ruta_clave=ruta_clave,
                cuit_emisor=cuit_emisor_normalizado,
                punto_venta=punto_venta_normalizado,
                tipo_comprobante=11,
                numero_comprobante=numero_emitido,
                carpeta_trabajo=carpeta_facturas,
                token=emision.get("token"),
                sign=emision.get("sign"),
            )

            if not consulta.get("ok"):
                messagebox.showerror(
                    "Emitir factura",
                    self._mensaje_errores_emision(consulta),
                    parent=modal_confirmacion,
                )
                return

            numero_comprobante = int(consulta.get("numero_comprobante") or numero_emitido)
            punto_venta_num = int(consulta.get("punto_venta") or punto_venta or 0)

            self.factura_emitida_temporal = {
                "cae": str(consulta.get("cae") or emision.get("cae") or ""),
                "vencimiento_cae": str(consulta.get("vencimiento_cae") or emision.get("vencimiento_cae") or ""),
                "numero_comprobante": numero_comprobante,
                "punto_venta": punto_venta_num,
                "fecha_comprobante": str(consulta.get("fecha_comprobante") or fecha_comprobante or ""),
            }

            codigo_factura = self._formatear_codigo_factura(punto_venta_num, numero_comprobante)
            ruta_sugerida_pdf = str(Path(carpeta_facturas) / nombre_factura_pdf(cliente_fila[0], tipo_factura, codigo_factura))

            datos_emisor = {
                "razon_social": str(emisor[1] if len(emisor) > 1 else "" or ""),
                "nombre_fantasia": str(emisor[2] if len(emisor) > 2 else "" or ""),
                "cuit": cuit_emisor,
                "condicion_iva": str(emisor[4] if len(emisor) > 4 else "" or ""),
                "domicilio": str(emisor[10] if len(emisor) > 10 else "" or ""),
                "ingresos_brutos": str(emisor[11] if len(emisor) > 11 else "" or ""),
                "fecha_inicio_actividades": str(emisor[12] if len(emisor) > 12 else "" or ""),
                "punto_venta": punto_venta_num,
            }

            datos_receptor = {
                "razon_social": str(cliente_fila[2] if len(cliente_fila) > 2 else "" or ""),
                "cuit": cuit_o_doc,
                "documento": cuit_o_doc,
                "condicion_iva": str(cliente_fila[11] if len(cliente_fila) > 11 else "" or ""),
                "domicilio": self._combinar_domicilio_cliente(cliente_fila),
            }

            datos_comprobante = {
                "tipo": "Factura C",
                "numero": numero_comprobante,
                "fecha": self.factura_emitida_temporal.get("fecha_comprobante", ""),
                "concepto": "1 - Productos",
                "periodo_servicio_desde": "",
                "periodo_servicio_hasta": "",
                "vencimiento_pago": self._a_fecha_arca_yyyymmdd(resumen.fecha_vencimiento),
                "importe_total": float(consulta.get("importe_total") or resumen.total or 0.0),
                "moneda": str(consulta.get("moneda") or "PES"),
                "cae": self.factura_emitida_temporal.get("cae", ""),
                "vencimiento_cae": self.factura_emitida_temporal.get("vencimiento_cae", ""),
                "ambiente": str(emisor[9] if len(emisor) > 9 else "Homologación"),
                "punto_venta": punto_venta_num,
            }

            pdf = PDFFiscalService.generar_factura_c(
                ruta_destino=ruta_sugerida_pdf,
                datos_emisor=datos_emisor,
                datos_receptor=datos_receptor,
                datos_comprobante=datos_comprobante,
            )
            if not pdf.get("ok"):
                errores_pdf = "\n".join(pdf.get("errores") or ["No se pudo generar el PDF fiscal."])
                messagebox.showerror(
                    "Emitir factura",
                    f"Factura autorizada, pero falló la generación del PDF fiscal.\n\n{errores_pdf}",
                    parent=modal_confirmacion,
                )
                return

            ruta_pdf = str(pdf.get("ruta_pdf") or "").strip()
            if ruta_pdf:
                try:
                    os.startfile(ruta_pdf)
                except OSError as error:
                    messagebox.showwarning(
                        "Emitir factura",
                        f"La factura fue emitida y el PDF generado, pero no se pudo abrir automáticamente.\n\n{error}",
                        parent=modal_confirmacion,
                    )

            modal_confirmacion.destroy()
            messagebox.showinfo(
                "Emitir factura",
                (
                    "Factura emitida correctamente.\n\n"
                    "Factura C\n"
                    f"{codigo_factura}\n\n"
                    "CAE:\n"
                    f"{self.factura_emitida_temporal.get('cae', '-') }"
                ),
                parent=self.winfo_toplevel(),
            )
        except Exception as error:
            messagebox.showerror(
                "Emitir factura",
                f"Error inesperado durante la emisión de factura:\n\n{str(error)}",
                parent=modal_confirmacion,
            )

    def _a_fecha_arca_yyyymmdd(self, valor):
        texto = str(valor or "").strip()
        if len(texto) == 8 and texto.isdigit():
            return texto
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            return texto.replace("-", "")
        return texto

    def _normalizar_cuit_emisor(self, cuit):
        """Normaliza CUIT: quita guiones y caracteres no numéricos, valida 11 dígitos."""
        # Convertir a string y quitar espacios
        cuit_texto = str(cuit or "").strip()
        # Quitar todos los caracteres no numéricos
        cuit_limpio = "".join(c for c in cuit_texto if c.isdigit())
        # Validar exactamente 11 dígitos
        if len(cuit_limpio) != 11:
            return None  # Inválido
        return cuit_limpio

    def _normalizar_punto_venta(self, punto_venta):
        """Normaliza punto de venta: convierte a int y valida > 0."""
        try:
            pv_int = int(punto_venta or 0)
            if pv_int > 0:
                return pv_int
        except (TypeError, ValueError):
            pass
        return None  # Inválido

    def _formatear_codigo_factura(self, punto_venta, numero):
        try:
            pv = int(punto_venta)
        except (TypeError, ValueError):
            pv = 0
        try:
            nro = int(numero)
        except (TypeError, ValueError):
            nro = 0
        return f"{pv:05d}-{nro:08d}"

    def _combinar_domicilio_cliente(self, cliente_fila):
        direccion = str(cliente_fila[5] if len(cliente_fila) > 5 else "" or "").strip()
        localidad = str(cliente_fila[6] if len(cliente_fila) > 6 else "" or "").strip()
        if direccion and localidad:
            return f"{direccion} - {localidad}"
        return direccion or localidad

    def _mensaje_errores_emision(self, resultado):
        errores = list(resultado.get("errores") or [])
        
        # Agregar errores de ARCA con formato "CODIGO - MENSAJE"
        errores_arca = resultado.get("errores_arca") or []
        for item in errores_arca:
            if isinstance(item, dict):
                codigo = str(item.get("codigo") or "").strip()
                mensaje = str(item.get("mensaje") or "").strip()
                if codigo or mensaje:
                    errores.append(f"{codigo} - {mensaje}".strip() if codigo else mensaje)
            elif str(item or "").strip():
                errores.append(str(item))

        # Agregar observaciones con formato "CODIGO - MENSAJE"
        observaciones = resultado.get("observaciones") or []
        for item in observaciones:
            if isinstance(item, dict):
                codigo = str(item.get("codigo") or "").strip()
                mensaje = str(item.get("mensaje") or "").strip()
                obs_formato = f"{codigo} - {mensaje}".strip() if codigo else mensaje
                if obs_formato:
                    errores.append(f"(Observación) {obs_formato}")
            elif str(item or "").strip():
                errores.append(f"(Observación) {str(item)}")

        if not errores:
            return "No se pudo completar la operación con ARCA."

        return "No se pudo completar la emisión.\n\n" + "\n".join(errores)

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