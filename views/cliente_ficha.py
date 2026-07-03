from copy import deepcopy
from tkinter import ttk

import customtkinter as ctk

from config import COLOR_BLANCO, COLOR_NEGRO, COLOR_PRINCIPAL
from services.cliente_service import ClienteService
from services.cobro_service import CobroService
from services.contacto_service import ContactoService
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService
from services.tarea_service import TareaService


class FichaClienteFrame(ctk.CTkFrame):
    MOCK_DATA = {
        "datos_generales": {
            "codigo": "",
            "razon_social": "",
            "nombre_comercial": "",
            "responsable": "",
            "cuit": "",
            "iva": "",
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
        self.callbacks = callbacks or {}
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
                    "iva": fila[11],
                    "estado": fila[16] if len(fila) > 16 else "",
                })
                datos["observaciones"] = fila[17] or "" if len(fila) > 17 else ""

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
            columnas=("numero", "fecha", "importe", "estado"),
            encabezados={
                "numero": ("Resumen", 110),
                "fecha": ("Fecha", 100),
                "importe": ("Importe", 110),
                "estado": ("Estado", 110),
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

        contenido.grid_rowconfigure(fila_servicios, weight=0)

        return tarjeta

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
        tarjeta = self._crear_tarjeta_base(parent, titulo)
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
            tabla.column(columna, width=ancho, anchor="w", stretch=columna == columnas[0])

        scroll = ttk.Scrollbar(contenedor_tabla, orient="vertical", command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        setattr(self, atributo_tabla, tabla)
        return tarjeta

    def _crear_tarjeta_base(self, parent, titulo):
        tarjeta = ctk.CTkFrame(parent, fg_color=COLOR_BLANCO, corner_radius=10, border_width=1, border_color="#DADADA")
        ctk.CTkLabel(
            tarjeta,
            text=titulo,
            font=("Arial", 15, "bold"),
            text_color=COLOR_NEGRO,
        ).pack(anchor="w", padx=18, pady=(16, 12))
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

        self._cargar_tabla(self.tabla_servicios, servicios_activos)
        self._cargar_tabla(self.tabla_resumenes, self.cliente_data.get("ultimos_resumenes", []))
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