import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

from services.emisor_fiscal_service import EmisorFiscalService


class EmisoresFiscalesWindow(ctk.CTkToplevel):
    CONDICIONES_IVA = [
        "Monotributo",
        "Responsable Inscripto",
        "Consumidor Final",
        "Exento",
        "Otro",
    ]
    TIPOS_FACTURA = ["Factura A", "Factura C", "No factura"]
    AMBIENTES_ARCA = ["Homologación", "Producción"]
    FILTROS_ESTADO = ["Todos", "Activos", "Inactivos"]

    def __init__(self, master):
        super().__init__(master)
        self.title("Emisores Fiscales")
        self.geometry("1520x820")
        self.minsize(1340, 720)
        self.transient(master)
        self.grab_set()
        self.emisor_id_actual = None
        self.filtro_estado = "Todos"
        self.configuracion_arca_completa = 0
        self._crear_interfaz()
        self.cargar_emisores()

    def _crear_interfaz(self):
        self.configure(fg_color="white")
        contenedor = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        contenedor.pack(fill="both", expand=True, padx=16, pady=16)
        contenedor.grid_columnconfigure(0, weight=7)
        contenedor.grid_columnconfigure(1, weight=3)
        contenedor.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(contenedor, fg_color="transparent", corner_radius=0)
        encabezado.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        encabezado.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            encabezado,
            text="Emisores Fiscales",
            font=("Arial", 24, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            encabezado,
            text="+ Nuevo Emisor",
            width=150,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.nuevo_emisor,
        ).grid(row=0, column=1, sticky="e")

        barra_busqueda = ctk.CTkFrame(encabezado, fg_color="transparent", corner_radius=0)
        barra_busqueda.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        barra_busqueda.grid_columnconfigure(1, weight=0)
        barra_busqueda.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(
            barra_busqueda,
            text="Buscar",
            font=("Arial", 12, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.entry_buscar = ctk.CTkEntry(barra_busqueda, width=280, placeholder_text="Nombre fantasía o CUIT")
        self.entry_buscar.grid(row=0, column=1, sticky="w")
        self.entry_buscar.bind("<KeyRelease>", lambda _evento: self.cargar_emisores())

        ctk.CTkLabel(
            barra_busqueda,
            text="Mostrar",
            font=("Arial", 12, "bold"),
            text_color="#222222",
        ).grid(row=0, column=2, sticky="w", padx=(18, 8))
        self.segmento_estado = ctk.CTkSegmentedButton(
            barra_busqueda,
            values=self.FILTROS_ESTADO,
            fg_color="#D8D8D8",
            selected_color="#333333",
            selected_hover_color="#111111",
            unselected_color="#F0F0F0",
            unselected_hover_color="#E2E2E2",
            text_color="#FFFFFF",
            command=self.cambiar_filtro_estado,
        )
        self.segmento_estado.grid(row=0, column=3, sticky="w")
        self.segmento_estado.set(self.filtro_estado)

        lista_frame = ctk.CTkFrame(contenedor, fg_color="#F4F4F4", corner_radius=8)
        lista_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        lista_frame.grid_propagate(False)
        lista_frame.grid_rowconfigure(1, weight=1)
        lista_frame.grid_rowconfigure(2, weight=0)
        lista_frame.grid_columnconfigure(0, weight=1)

        barra_listado = ctk.CTkFrame(lista_frame, fg_color="transparent")
        barra_listado.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))
        barra_listado.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            barra_listado,
            text="Listado",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            barra_listado,
            text="Activar/Desactivar",
            width=160,
            fg_color="#333333",
            hover_color="#111111",
            command=self.cambiar_estado_seleccionado,
        ).grid(row=0, column=2, padx=(8, 0))

        columnas = (
            "id",
            "nombre_fantasia",
            "cuit",
            "condicion_iva",
            "tipo_factura",
            "activo",
        )
        self.tabla = ttk.Treeview(lista_frame, columns=columnas, show="headings", height=18)
        encabezados = {
            "id": ("", 1),
            "nombre_fantasia": ("Nombre fantasía", 310),
            "cuit": ("CUIT", 150),
            "condicion_iva": ("IVA", 170),
            "tipo_factura": ("Factura", 120),
            "activo": ("Estado", 90),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(columna, width=ancho, minwidth=ancho, anchor="w")
        self.tabla.column("id", width=0, minwidth=0, stretch=False)
        self.tabla.bind("<<TreeviewSelect>>", lambda _evento: self.seleccionar_emisor())
        self.tabla.bind("<Double-1>", lambda _evento: self.seleccionar_emisor())

        scroll_y = ttk.Scrollbar(lista_frame, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(lista_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tabla.grid(row=1, column=0, sticky="nsew", padx=(12, 0))
        scroll_y.grid(row=1, column=1, sticky="ns", pady=(0, 0))
        scroll_x.grid(row=2, column=0, sticky="ew", padx=(12, 0), pady=(0, 10))

        panel = ctk.CTkFrame(contenedor, fg_color="#F4F4F4", corner_radius=8)
        panel.grid(row=1, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=0)
        panel.grid_rowconfigure(3, weight=0)

        ctk.CTkLabel(
            panel,
            text="Ficha",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 10))

        formulario = ctk.CTkFrame(panel, fg_color="transparent")
        formulario.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        formulario.grid_columnconfigure(0, weight=1)
        formulario.grid_columnconfigure(1, weight=1)
        formulario.grid_columnconfigure(2, weight=1)

        self.entry_razon_social = self._crear_campo(formulario, 0, 0, "Razón social", colspan=3)
        self.entry_nombre_fantasia = self._crear_campo(formulario, 1, 0, "Nombre fantasía")
        self.entry_cuit = self._crear_campo(formulario, 1, 1, "CUIT")
        self.entry_punto_venta = self._crear_campo(formulario, 1, 2, "Punto de venta")
        self.combo_condicion_iva = self._crear_combo(
            formulario,
            2,
            0,
            "Condición IVA",
            self.CONDICIONES_IVA,
        )
        self.combo_tipo_factura = self._crear_combo(
            formulario,
            2,
            1,
            "Tipo de factura",
            self.TIPOS_FACTURA,
        )

        self.var_activo = ctk.IntVar(value=1)
        ctk.CTkCheckBox(formulario, text="Activo", variable=self.var_activo).grid(
            row=5, column=2, sticky="w", padx=(10, 0), pady=(26, 0)
        )

        ctk.CTkLabel(formulario, text="Observaciones", anchor="w").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=(12, 4)
        )
        self.text_observaciones = ctk.CTkTextbox(formulario, height=28, fg_color="white", text_color="#1F1F1F")
        self.text_observaciones.grid(row=7, column=0, columnspan=3, sticky="ew")

        self._crear_seccion_arca(panel)

        acciones = ctk.CTkFrame(panel, fg_color="transparent")
        acciones.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 16))
        acciones.grid_columnconfigure(0, weight=1)
        acciones.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            acciones,
            text="Guardar",
            width=110,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.guardar_emisor,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            acciones,
            text="Cancelar",
            width=110,
            fg_color="#666666",
            hover_color="#444444",
            command=self.destroy,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _crear_seccion_arca(self, parent):
        arca_frame = ctk.CTkFrame(parent, fg_color="#FFFFFF", corner_radius=6, border_width=1, border_color="#DADADA")
        arca_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        arca_frame.grid_columnconfigure(1, weight=1)
        arca_frame.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(
            arca_frame,
            text="Configuración ARCA",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 8))

        ctk.CTkLabel(arca_frame, text="Ambiente:", font=("Arial", 12, "bold"), text_color="#222222").grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 4)
        )
        self.combo_ambiente_arca = ctk.CTkOptionMenu(
            arca_frame,
            values=self.AMBIENTES_ARCA,
            fg_color="white",
            button_color="#C00000",
            button_hover_color="#990000",
            text_color="#1F1F1F",
        )
        self.combo_ambiente_arca.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(0, 4))
        self.combo_ambiente_arca.set(self.AMBIENTES_ARCA[0])

        self.entry_ruta_certificado = self._crear_selector_ruta(
            arca_frame,
            fila=2,
            etiqueta="Certificado digital:",
            boton_texto="Seleccionar",
            comando=self._seleccionar_certificado,
        )
        self.entry_ruta_clave_privada = self._crear_selector_ruta(
            arca_frame,
            fila=3,
            etiqueta="Clave privada:",
            boton_texto="Seleccionar",
            comando=self._seleccionar_clave_privada,
        )
        self.entry_carpeta_facturas = self._crear_selector_ruta(
            arca_frame,
            fila=4,
            etiqueta="Carpeta de facturas:",
            boton_texto="Seleccionar carpeta",
            comando=self._seleccionar_carpeta_facturas,
            es_carpeta=True,
        )

        ctk.CTkButton(
            arca_frame,
            text="Validar configuración",
            width=180,
            fg_color="#333333",
            hover_color="#111111",
            command=self.validar_configuracion_arca_actual,
        ).grid(row=5, column=0, columnspan=3, sticky="e", padx=14, pady=(8, 12))

    def _crear_selector_ruta(self, master, fila, etiqueta, boton_texto, comando, es_carpeta=False):
        ctk.CTkLabel(master, text=etiqueta, font=("Arial", 11, "bold"), text_color="#222222").grid(
            row=fila,
            column=0,
            sticky="w",
            padx=14,
            pady=(4, 4),
        )
        contenedor = ctk.CTkFrame(master, fg_color="transparent")
        contenedor.grid(row=fila, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(4, 4))
        contenedor.grid_columnconfigure(0, weight=1)

        entrada = ctk.CTkEntry(contenedor)
        entrada.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            contenedor,
            text=boton_texto,
            width=126 if not es_carpeta else 146,
            fg_color="#666666",
            hover_color="#444444",
            command=comando,
        ).grid(row=0, column=1, sticky="e")
        return entrada

    def _seleccionar_certificado(self):
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar certificado digital",
            filetypes=[
                ("Certificados", "*.crt *.cer *.pem *.p12 *.pfx"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if ruta:
            self.entry_ruta_certificado.delete(0, "end")
            self.entry_ruta_certificado.insert(0, ruta)

    def _seleccionar_clave_privada(self):
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar clave privada",
            filetypes=[
                ("Claves privadas", "*.key *.pem"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if ruta:
            self.entry_ruta_clave_privada.delete(0, "end")
            self.entry_ruta_clave_privada.insert(0, ruta)

    def _seleccionar_carpeta_facturas(self):
        ruta = filedialog.askdirectory(parent=self, title="Seleccionar carpeta de facturas")
        if ruta:
            self.entry_carpeta_facturas.delete(0, "end")
            self.entry_carpeta_facturas.insert(0, ruta)

    def _crear_campo(self, master, fila, columna, etiqueta, colspan=1):
        columna_final = columna + colspan - 1
        ctk.CTkLabel(master, text=etiqueta, anchor="w").grid(
            row=fila * 2,
            column=columna,
            columnspan=colspan,
            sticky="ew",
            padx=(0, 10) if columna == 0 else (10, 0),
            pady=(8, 4),
        )
        entrada = ctk.CTkEntry(master)
        entrada.grid(
            row=fila * 2 + 1,
            column=columna,
            columnspan=colspan,
            sticky="ew",
            padx=(0, 10) if columna == 0 else (10, 0),
        )
        if colspan == 2:
            master.grid_columnconfigure(columna_final, weight=1)
        return entrada

    def _crear_combo(self, master, fila, columna, etiqueta, valores):
        ctk.CTkLabel(master, text=etiqueta, anchor="w").grid(
            row=fila * 2,
            column=columna,
            sticky="ew",
            padx=(0, 10) if columna == 0 else (10, 0),
            pady=(8, 4),
        )
        combo = ctk.CTkOptionMenu(
            master,
            values=valores,
            fg_color="white",
            button_color="#C00000",
            button_hover_color="#990000",
            text_color="#1F1F1F",
        )
        combo.grid(
            row=fila * 2 + 1,
            column=columna,
            sticky="ew",
            padx=(0, 10) if columna == 0 else (10, 0),
        )
        combo.set(valores[0])
        return combo

    def cambiar_filtro_estado(self, valor):
        self.filtro_estado = valor or "Todos"
        self.cargar_emisores()

    def cargar_emisores(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        texto_busqueda = self.entry_buscar.get().strip().lower() if hasattr(self, "entry_buscar") else ""
        for fila in EmisorFiscalService.listar():
            activo = bool(fila[7])
            if self.filtro_estado == "Activos" and not activo:
                continue
            if self.filtro_estado == "Inactivos" and activo:
                continue

            nombre_fantasia = (fila[2] or "").strip()
            cuit = (fila[3] or "").strip()
            texto_compuesto = f"{nombre_fantasia} {cuit}".lower()
            if texto_busqueda and texto_busqueda not in texto_compuesto:
                continue

            self.tabla.insert(
                "",
                "end",
                values=(
                    fila[0],
                    nombre_fantasia,
                    cuit,
                    fila[4] or "",
                    fila[5] or "",
                    "Activo" if activo else "Inactivo",
                ),
            )

    def limpiar_formulario(self):
        self.emisor_id_actual = None
        self.entry_razon_social.delete(0, "end")
        self.entry_nombre_fantasia.delete(0, "end")
        self.entry_cuit.delete(0, "end")
        self.combo_condicion_iva.set(self.CONDICIONES_IVA[0])
        self.combo_tipo_factura.set(self.TIPOS_FACTURA[0])
        self.combo_ambiente_arca.set(self.AMBIENTES_ARCA[0])
        self.entry_punto_venta.delete(0, "end")
        self.entry_ruta_certificado.delete(0, "end")
        self.entry_ruta_clave_privada.delete(0, "end")
        self.entry_carpeta_facturas.delete(0, "end")
        self.text_observaciones.delete("1.0", "end")
        self.var_activo.set(1)
        self.configuracion_arca_completa = 0

    def nuevo_emisor(self):
        self.limpiar_formulario()
        self.tabla.selection_remove(self.tabla.selection())

    def seleccionar_emisor(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return

        valores = self.tabla.item(seleccion[0], "values")
        if not valores:
            return

        try:
            self.emisor_id_actual = int(valores[0])
        except (TypeError, ValueError):
            return

        fila = EmisorFiscalService.obtener(self.emisor_id_actual)
        if not fila:
            return

        self.entry_razon_social.delete(0, "end")
        self.entry_razon_social.insert(0, fila[1] or "")
        self.entry_nombre_fantasia.delete(0, "end")
        self.entry_nombre_fantasia.insert(0, fila[2] or "")
        self.entry_cuit.delete(0, "end")
        self.entry_cuit.insert(0, fila[3] or "")
        self.combo_condicion_iva.set(fila[4] or self.CONDICIONES_IVA[0])
        self.combo_tipo_factura.set(fila[5] or self.TIPOS_FACTURA[0])
        self.entry_punto_venta.delete(0, "end")
        self.entry_punto_venta.insert(0, fila[6] or "")
        self.var_activo.set(1 if fila[7] else 0)
        self.text_observaciones.delete("1.0", "end")
        self.text_observaciones.insert("1.0", fila[8] or "")
        self.combo_ambiente_arca.set(fila[9] or self.AMBIENTES_ARCA[0])
        self.entry_ruta_certificado.delete(0, "end")
        self.entry_ruta_certificado.insert(0, fila[10] or "")
        self.entry_ruta_clave_privada.delete(0, "end")
        self.entry_ruta_clave_privada.insert(0, fila[11] or "")
        self.entry_carpeta_facturas.delete(0, "end")
        self.entry_carpeta_facturas.insert(0, fila[12] or "")
        self.configuracion_arca_completa = 1 if len(fila) > 13 and fila[13] else 0

    def validar_configuracion_arca_actual(self):
        if self.emisor_id_actual is None:
            messagebox.showwarning(
                "Emisores Fiscales",
                "Seleccione o guarde un emisor para validar la configuración ARCA.",
                parent=self,
            )
            return

        resultado = EmisorFiscalService.validar_configuracion_arca(self.emisor_id_actual)
        self.configuracion_arca_completa = 1 if resultado["completa"] else 0

        if resultado["completa"]:
            messagebox.showinfo(
                "Configuración ARCA",
                "Configuración completa",
                parent=self,
            )
            return

        lineas = ["Configuración incompleta"]
        if resultado["faltantes"]:
            lineas.append("")
            lineas.extend(f"• {item}" for item in resultado["faltantes"])
        if resultado["errores"]:
            lineas.append("")
            lineas.extend(f"• {item}" for item in resultado["errores"])

        messagebox.showwarning(
            "Configuración ARCA",
            "\n".join(lineas),
            parent=self,
        )

    def guardar_emisor(self):
        razon_social = self.entry_razon_social.get().strip()
        nombre_fantasia = self.entry_nombre_fantasia.get().strip()
        cuit = self.entry_cuit.get().strip()
        condicion_iva = self.combo_condicion_iva.get().strip()
        tipo_factura = self.combo_tipo_factura.get().strip()
        punto_venta = self.entry_punto_venta.get().strip()
        observaciones = self.text_observaciones.get("1.0", "end").strip()
        activo = 1 if self.var_activo.get() else 0
        ambiente_arca = self.combo_ambiente_arca.get().strip() or self.AMBIENTES_ARCA[0]
        ruta_certificado = self.entry_ruta_certificado.get().strip()
        ruta_clave_privada = self.entry_ruta_clave_privada.get().strip()
        carpeta_facturas = self.entry_carpeta_facturas.get().strip()

        if not razon_social:
            messagebox.showerror("Emisores Fiscales", "La razón social es obligatoria.", parent=self)
            return
        if not cuit:
            messagebox.showerror("Emisores Fiscales", "El CUIT es obligatorio.", parent=self)
            return

        try:
            if self.emisor_id_actual is None:
                EmisorFiscalService.guardar(
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    punto_venta,
                    activo,
                    observaciones,
                    ambiente_arca,
                    ruta_certificado,
                    ruta_clave_privada,
                    carpeta_facturas,
                    self.configuracion_arca_completa,
                )
            else:
                EmisorFiscalService.actualizar(
                    self.emisor_id_actual,
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    punto_venta,
                    activo,
                    observaciones,
                    ambiente_arca,
                    ruta_certificado,
                    ruta_clave_privada,
                    carpeta_facturas,
                    self.configuracion_arca_completa,
                )
        except Exception as error:
            messagebox.showerror("Emisores Fiscales", f"No se pudo guardar el emisor.\n{error}", parent=self)
            return

        self.cargar_emisores()
        self.nuevo_emisor()
        messagebox.showinfo("Emisores Fiscales", "Emisor fiscal guardado correctamente.", parent=self)

    def cambiar_estado_seleccionado(self):
        if self.emisor_id_actual is None:
            messagebox.showwarning("Emisores Fiscales", "Seleccione un emisor para cambiar su estado.", parent=self)
            return

        nuevo_estado = 0 if self.var_activo.get() else 1
        try:
            EmisorFiscalService.cambiar_estado(self.emisor_id_actual, nuevo_estado)
        except Exception as error:
            messagebox.showerror("Emisores Fiscales", f"No se pudo cambiar el estado.\n{error}", parent=self)
            return

        self.cargar_emisores()
        self.seleccionar_emisor()
