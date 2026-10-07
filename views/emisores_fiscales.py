import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk

from services.arca.ambiente_arca import AmbienteArcaInvalidoError, normalizar_ambiente_arca
from services.emisor_fiscal_service import ConfiguracionArcaError, EmisorFiscalService


class EmisoresFiscalesWindow(ctk.CTkToplevel):
    CONDICIONES_IVA = [
        "Monotributo",
        "Responsable Inscripto",
        "Consumidor Final",
        "Exento",
        "Otro",
    ]
    TIPOS_FACTURA = ["Factura A", "Factura C", "No factura"]
    AMBIENTES_ARCA = ("HOMOLOGACION", "PRODUCCION")
    ETIQUETAS_AMBIENTE = {"HOMOLOGACION": "Homologación", "PRODUCCION": "Producción"}
    CAMPOS_ARCA = ("punto_venta", "ruta_certificado", "ruta_clave_privada", "carpeta_facturas")
    ADVERTENCIA_PRODUCCION = "PRODUCCIÓN — Configuración solamente.\nLa emisión real permanece bloqueada."
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
        self._inicializar_estado_arca()
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
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_rowconfigure(2, weight=0)

        ctk.CTkLabel(
            panel,
            text="Ficha",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 10))

        cuerpo_scroll = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            corner_radius=0,
        )
        cuerpo_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        cuerpo_scroll.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cuerpo_scroll,
            text="Datos del emisor",
            font=("Arial", 14, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 2))

        formulario = ctk.CTkFrame(cuerpo_scroll, fg_color="transparent")
        formulario.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))
        formulario.grid_columnconfigure(0, weight=1)
        formulario.grid_columnconfigure(1, weight=1)
        formulario.grid_columnconfigure(2, weight=1)

        self.entry_razon_social = self._crear_campo(formulario, 0, 0, "Razón social", colspan=3)
        self.entry_domicilio = self._crear_campo(formulario, 1, 0, "Domicilio", colspan=3)
        self.entry_nombre_fantasia = self._crear_campo(formulario, 2, 0, "Nombre fantasía")
        self.entry_cuit = self._crear_campo(formulario, 2, 1, "CUIT")
        self.entry_ingresos_brutos = self._crear_campo(formulario, 2, 2, "Ingresos Brutos")
        self.combo_condicion_iva = self._crear_combo(
            formulario,
            3,
            0,
            "Condición IVA",
            self.CONDICIONES_IVA,
        )
        self.combo_tipo_factura = self._crear_combo(
            formulario,
            3,
            1,
            "Tipo de factura",
            self.TIPOS_FACTURA,
        )
        self.entry_fecha_inicio_actividades = self._crear_campo(formulario, 3, 2, "Fecha inicio actividades")

        self.var_activo = ctk.IntVar(value=1)
        ctk.CTkCheckBox(formulario, text="Activo", variable=self.var_activo).grid(
            row=9, column=2, sticky="w", padx=(10, 0), pady=(0, 0)
        )

        # Se mantiene el control para no alterar la lógica existente de carga/guardado,
        # pero ya no se muestra en la ficha.
        self.text_observaciones = ctk.CTkTextbox(formulario, height=28, fg_color="white", text_color="#1F1F1F")

        self._crear_seccion_arca(cuerpo_scroll)

        acciones = ctk.CTkFrame(panel, fg_color="transparent")
        acciones.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
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

        activo = ctk.CTkFrame(arca_frame, fg_color="#F4F4F4", corner_radius=6)
        activo.grid(row=1, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 6))
        activo.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(activo, text="Ambiente activo para emisión:", font=("Arial", 12, "bold"), text_color="#222222").grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=(8, 2)
        )
        self.label_ambiente_activo = ctk.CTkLabel(activo, text="", font=("Arial", 12, "bold"), text_color="#C00000")
        self.label_ambiente_activo.grid(row=0, column=1, sticky="w", pady=(8, 2))
        botones_activo = ctk.CTkFrame(activo, fg_color="transparent")
        botones_activo.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 4))
        self.botones_ambiente_activo = {}
        for indice, ambiente in enumerate(self.AMBIENTES_ARCA):
            boton = ctk.CTkButton(
                botones_activo,
                text=f"Activar {self.ETIQUETAS_AMBIENTE[ambiente]}",
                width=170,
                fg_color="#333333",
                hover_color="#111111",
                command=lambda destino=ambiente: self.cambiar_ambiente_activo(destino),
            )
            boton.grid(row=0, column=indice, padx=(0, 8))
            self.botones_ambiente_activo[ambiente] = boton
        ctk.CTkLabel(
            activo,
            text="Cambiar de pestaña no cambia el ambiente activo.",
            font=("Arial", 10),
            text_color="#666666",
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        self.tabview_arca = ctk.CTkTabview(
            arca_frame,
            height=500,
            fg_color="#FFFFFF",
            segmented_button_selected_color="#333333",
            segmented_button_selected_hover_color="#111111",
        )
        self.tabview_arca.grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))
        for ambiente in self.AMBIENTES_ARCA:
            pestana = self.tabview_arca.add(self.ETIQUETAS_AMBIENTE[ambiente])
            self._crear_pestana_arca(pestana, ambiente)
        self._actualizar_control_ambiente_activo()

    def _crear_pestana_arca(self, pestana, ambiente):
        cuerpo = ctk.CTkScrollableFrame(pestana, fg_color="transparent", corner_radius=0)
        cuerpo.pack(fill="both", expand=True)
        pestana = cuerpo
        pestana.grid_columnconfigure(1, weight=1)
        if ambiente == "PRODUCCION":
            texto_banner, color_banner = self.ADVERTENCIA_PRODUCCION, "#8A4B00"
        else:
            texto_banner, color_banner = "HOMOLOGACIÓN — Ambiente de pruebas.", "#4A4A4A"
        ctk.CTkLabel(
            pestana,
            text=texto_banner,
            font=("Arial", 12, "bold"),
            text_color="#FFFFFF",
            fg_color=color_banner,
            corner_radius=6,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew", padx=4, pady=(4, 6), ipadx=8, ipady=4)

        self.arca_estado_labels[ambiente] = ctk.CTkLabel(pestana, text="", font=("Arial", 11, "italic"), text_color="#555555")
        self.arca_estado_labels[ambiente].grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 4))

        ctk.CTkLabel(pestana, text="Punto de venta:", font=("Arial", 11, "bold"), text_color="#222222").grid(
            row=2, column=0, sticky="w", padx=14, pady=(4, 4)
        )
        entrada_pv = ctk.CTkEntry(pestana, width=120)
        entrada_pv.grid(row=2, column=1, sticky="w", padx=(0, 14), pady=(4, 4))

        entradas = {"punto_venta": entrada_pv}
        entradas["ruta_certificado"] = self._crear_selector_ruta(
            pestana,
            fila=3,
            etiqueta="Certificado digital:",
            boton_texto="Seleccionar",
            comando=lambda: self._seleccionar_certificado(ambiente),
        )
        entradas["ruta_clave_privada"] = self._crear_selector_ruta(
            pestana,
            fila=4,
            etiqueta="Clave privada:",
            boton_texto="Seleccionar",
            comando=lambda: self._seleccionar_clave_privada(ambiente),
        )
        entradas["carpeta_facturas"] = self._crear_selector_ruta(
            pestana,
            fila=5,
            etiqueta="Carpeta de facturas:",
            boton_texto="Seleccionar carpeta",
            comando=lambda: self._seleccionar_carpeta_facturas(ambiente),
            es_carpeta=True,
        )
        self.arca_entries[ambiente] = entradas
        self.arca_variables[ambiente] = {}
        for campo, entrada in entradas.items():
            variable = ctk.StringVar(master=self, value=entrada.get())
            entrada.configure(textvariable=variable)
            variable.trace_add("write", lambda *_args: self._refrescar_estado_arca(ambiente))
            self.arca_variables[ambiente][campo] = variable
        self.arca_validar_botones[ambiente] = ctk.CTkButton(
            pestana,
            text="Validar configuración",
            fg_color="#333333",
            hover_color="#111111",
            command=lambda: self.validar_configuracion_local(ambiente),
        )
        self.arca_validar_botones[ambiente].grid(
            row=6, column=0, columnspan=3, sticky="e", padx=14, pady=(10, 6)
        )
        resultado_panel = ctk.CTkFrame(pestana, fg_color="transparent", corner_radius=0)
        resultado_panel.grid(row=7, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
        resultado_panel.grid_columnconfigure(0, weight=1)
        etiquetas = {}
        for fila, (bloque, color) in enumerate((
            ("estado", "#333333"), ("alcance", "#555555"),
            ("errores", "#A00000"), ("advertencias", "#8A4B00"),
            ("controles", "#666666"), ("produccion", "#8A4B00"),
        )):
            etiqueta = ctk.CTkLabel(
                resultado_panel, text="", text_color=color, anchor="w", justify="left",
                font=("Arial", 11), wraplength=300,
            )
            etiqueta.grid(row=fila, column=0, sticky="ew", pady=(2, 2))
            etiquetas[bloque] = etiqueta
        resultado_panel.bind(
            "<Configure>",
            lambda evento: [etiqueta.configure(wraplength=max(1, evento.width - 8))
                            for etiqueta in etiquetas.values()],
        )
        self.arca_validacion_labels[ambiente] = etiquetas
        self._refrescar_estado_arca(ambiente)

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

    # -- estado ARCA por ambiente (sin GUI: testeable con widgets falsos) --
    def _inicializar_estado_arca(self):
        self.arca_entries = {}
        self.arca_variables = {}
        self.arca_estado_labels = {}
        self.arca_validar_botones = {}
        self.arca_validacion_labels = {}
        self.arca_validacion_resultados = {ambiente: None for ambiente in self.AMBIENTES_ARCA}
        self.botones_ambiente_activo = {}
        self.label_ambiente_activo = None
        # None = sin configuracion hija persistida; tupla = valores persistidos.
        self.arca_original = {ambiente: None for ambiente in self.AMBIENTES_ARCA}
        self.arca_error_carga = {ambiente: None for ambiente in self.AMBIENTES_ARCA}
        self.ambiente_activo = "HOMOLOGACION"

    def _valores_formulario_arca(self, ambiente):
        entradas = self.arca_entries[ambiente]
        return tuple(str(entradas[campo].get() or "").strip() for campo in self.CAMPOS_ARCA)

    def _poner_valores_arca(self, ambiente, valores):
        for campo, valor in zip(self.CAMPOS_ARCA, valores):
            entrada = self.arca_entries[ambiente][campo]
            entrada.delete(0, "end")
            entrada.insert(0, valor or "")

    def _arca_modificada(self, ambiente):
        actuales = self._valores_formulario_arca(ambiente)
        original = self.arca_original[ambiente]
        if original is None:
            return any(actuales)
        return actuales != original

    def _texto_estado_arca(self, ambiente):
        if self._arca_modificada(ambiente):
            return "Cambios sin guardar"
        if self.arca_error_carga[ambiente]:
            return "Configuración inconsistente: no se pudo leer"
        if self.arca_original[ambiente] is None:
            return "Sin configurar"
        return "Configurado"

    def _refrescar_estado_arca(self, ambiente):
        etiqueta = self.arca_estado_labels.get(ambiente)
        if etiqueta is not None and ambiente in self.arca_entries:
            etiqueta.configure(text=f"Estado: {self._texto_estado_arca(ambiente)}")
        if self._arca_modificada(ambiente):
            self.arca_validacion_resultados[ambiente] = None
        habilitado = (
            self.emisor_id_actual is not None
            and self.arca_original[ambiente] is not None
            and not self.arca_error_carga[ambiente]
            and not self._arca_modificada(ambiente)
        )
        boton = self.arca_validar_botones.get(ambiente)
        if boton is not None:
            boton.configure(state="normal" if habilitado else "disabled")
        self._mostrar_validacion_local(ambiente)

    def _mostrar_validacion_local(self, ambiente):
        etiquetas = self.arca_validacion_labels.get(ambiente, {})
        bloques = {bloque: "" for bloque in etiquetas}
        if self._arca_modificada(ambiente):
            bloques["estado"] = "Hay cambios sin guardar. Guarde antes de validar."
        elif self.arca_error_carga[ambiente]:
            bloques["estado"] = "No se pudo leer la configuración persistida."
        elif self.arca_original[ambiente] is None or self.emisor_id_actual is None:
            bloques["estado"] = "Sin configurar. Configure y guarde antes de validar."
        else:
            bloques.update(self.arca_validacion_resultados[ambiente] or {
                "estado": "Validación local pendiente."
            })
        if ambiente == "PRODUCCION":
            bloques["produccion"] = "La emisión real permanece bloqueada."
        for bloque, etiqueta in etiquetas.items():
            etiqueta.configure(text=bloques[bloque])

    def validar_configuracion_local(self, ambiente):
        self._refrescar_estado_arca(ambiente)
        if (self.emisor_id_actual is None or self.arca_original[ambiente] is None
                or self.arca_error_carga[ambiente] or self._arca_modificada(ambiente)):
            return False
        try:
            resultado = EmisorFiscalService.validar_configuracion_arca_por_ambiente(
                self.emisor_id_actual, ambiente
            )
            bloques = {
                "estado": "Validación local básica OK" if resultado.ok else "Validación local con errores",
                "alcance": "Esta validación no acredita habilitación ni conexión con ARCA.",
                "errores": "\n".join((f"Código: {resultado.codigo}", "Errores:", *resultado.errores))
                    if not resultado.ok else "",
                "advertencias": "\n".join(("Advertencias:", *resultado.advertencias))
                    if resultado.advertencias else "",
                "controles": "\n".join(("Controles no realizados:", *resultado.controles_no_realizados))
                    if resultado.controles_no_realizados else "",
            }
        except ConfiguracionArcaError as error:
            bloques = {"estado": "Validación local con errores",
                       "errores": f"Código: {error.codigo}\n{error}"}
        except Exception:
            bloques = {"estado": "Validación local con errores",
                       "errores": "No se pudo realizar la validación local. Intente nuevamente."}
        self.arca_validacion_resultados[ambiente] = bloques
        self._mostrar_validacion_local(ambiente)
        return bloques["estado"] == "Validación local básica OK"

    def _actualizar_control_ambiente_activo(self):
        if self.label_ambiente_activo is not None:
            texto = self.ETIQUETAS_AMBIENTE.get(self.ambiente_activo, "No definido")
            self.label_ambiente_activo.configure(text=texto)
        for ambiente, boton in self.botones_ambiente_activo.items():
            habilitado = self.emisor_id_actual is not None and ambiente != self.ambiente_activo
            boton.configure(state="normal" if habilitado else "disabled")

    def _cargar_configuraciones_arca(self, emisor_id):
        for ambiente in self.AMBIENTES_ARCA:
            self.arca_validacion_resultados[ambiente] = None
            original, error = None, None
            try:
                configuracion = EmisorFiscalService.obtener_configuracion_arca(emisor_id, ambiente)
                original = tuple(
                    str(getattr(configuracion, campo) or "").strip() for campo in self.CAMPOS_ARCA
                )
            except ConfiguracionArcaError as excepcion:
                if excepcion.codigo != "CONFIGURACION_ARCA_NO_ENCONTRADA":
                    error = excepcion.codigo
            self.arca_original[ambiente] = original
            self.arca_error_carga[ambiente] = error
            self._poner_valores_arca(ambiente, original or ("", "", "", ""))
            self._refrescar_estado_arca(ambiente)

    def _seleccionar_ruta(self, ambiente, campo, ruta):
        if not ruta:
            return
        entrada = self.arca_entries[ambiente][campo]
        entrada.delete(0, "end")
        entrada.insert(0, ruta)
        self._refrescar_estado_arca(ambiente)

    def _seleccionar_certificado(self, ambiente):
        ruta = filedialog.askopenfilename(
            parent=self,
            title=f"Seleccionar certificado digital — {self.ETIQUETAS_AMBIENTE[ambiente]}",
            filetypes=[
                ("Certificados", "*.crt *.cer *.pem *.p12 *.pfx"),
                ("Todos los archivos", "*.*"),
            ],
        )
        self._seleccionar_ruta(ambiente, "ruta_certificado", ruta)

    def _seleccionar_clave_privada(self, ambiente):
        ruta = filedialog.askopenfilename(
            parent=self,
            title=f"Seleccionar clave privada — {self.ETIQUETAS_AMBIENTE[ambiente]}",
            filetypes=[
                ("Claves privadas", "*.key *.pem"),
                ("Todos los archivos", "*.*"),
            ],
        )
        self._seleccionar_ruta(ambiente, "ruta_clave_privada", ruta)

    def _seleccionar_carpeta_facturas(self, ambiente):
        ruta = filedialog.askdirectory(
            parent=self, title=f"Seleccionar carpeta de facturas — {self.ETIQUETAS_AMBIENTE[ambiente]}"
        )
        self._seleccionar_ruta(ambiente, "carpeta_facturas", ruta)

    def cambiar_ambiente_activo(self, destino):
        etiqueta = self.ETIQUETAS_AMBIENTE[destino]
        if self.emisor_id_actual is None:
            messagebox.showwarning("Ambiente activo", "Guarde el emisor antes de cambiar el ambiente activo.", parent=self)
            return False
        if destino == self.ambiente_activo:
            return False
        if self._arca_modificada(destino):
            messagebox.showwarning(
                "Ambiente activo",
                f"La configuración de {etiqueta} tiene cambios sin guardar.\n"
                "Guárdela antes de activarla.",
                parent=self,
            )
            return False
        if destino == "PRODUCCION" and not messagebox.askyesno(
            "Ambiente activo",
            "Producción quedará como ambiente activo.\n\n"
            "Esto NO habilita la emisión real: permanece bloqueada.\n\n¿Continuar?",
            parent=self,
        ):
            return False
        try:
            EmisorFiscalService.cambiar_ambiente_arca_activo(self.emisor_id_actual, destino)
        except ConfiguracionArcaError as error:
            if error.codigo == "CONFIGURACION_ARCA_NO_ENCONTRADA":
                mensaje = f"No existe configuración de {etiqueta} guardada.\nConfigúrela y guárdela antes de activarla."
            else:
                mensaje = f"No se pudo cambiar el ambiente activo ({error.codigo})."
            messagebox.showerror("Ambiente activo", mensaje, parent=self)
            return False
        self.ambiente_activo = destino
        self._actualizar_control_ambiente_activo()
        messagebox.showinfo("Ambiente activo", f"Ambiente activo para emisión: {etiqueta}.", parent=self)
        return True

    def _guardar_configuraciones_arca_modificadas(self, emisor_id):
        """Guarda solo las configuraciones modificadas; devuelve lista de errores (sin rutas)."""
        errores = []
        for ambiente in self.AMBIENTES_ARCA:
            if not self._arca_modificada(ambiente):
                continue
            try:
                resultado = EmisorFiscalService.guardar_configuracion_arca(
                    emisor_id, ambiente, *self._valores_formulario_arca(ambiente)
                )
            except ConfiguracionArcaError as error:
                errores.append(f"{self.ETIQUETAS_AMBIENTE[ambiente]}: {error}")
                continue
            guardada = tuple(
                str(getattr(resultado.configuracion, campo) or "").strip() for campo in self.CAMPOS_ARCA
            )
            self.arca_original[ambiente] = guardada
            self.arca_error_carga[ambiente] = None
            self.arca_validacion_resultados[ambiente] = None
            self._poner_valores_arca(ambiente, guardada)
            self._refrescar_estado_arca(ambiente)
        return errores

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
        self.entry_domicilio.delete(0, "end")
        self.entry_nombre_fantasia.delete(0, "end")
        self.entry_cuit.delete(0, "end")
        self.combo_condicion_iva.set(self.CONDICIONES_IVA[0])
        self.combo_tipo_factura.set(self.TIPOS_FACTURA[0])
        self.entry_ingresos_brutos.delete(0, "end")
        self.entry_fecha_inicio_actividades.delete(0, "end")
        self.text_observaciones.delete("1.0", "end")
        self.var_activo.set(1)
        for ambiente in self.AMBIENTES_ARCA:
            self.arca_original[ambiente] = None
            self.arca_error_carga[ambiente] = None
            self.arca_validacion_resultados[ambiente] = None
            self._poner_valores_arca(ambiente, ("", "", "", ""))
            self._refrescar_estado_arca(ambiente)
        self.ambiente_activo = "HOMOLOGACION"
        self._actualizar_control_ambiente_activo()

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
            emisor_id = int(valores[0])
        except (TypeError, ValueError):
            return
        self._cargar_emisor(emisor_id)

    def _cargar_emisor(self, emisor_id):
        fila = EmisorFiscalService.obtener(emisor_id)
        if not fila:
            return
        self.emisor_id_actual = emisor_id

        self.entry_razon_social.delete(0, "end")
        self.entry_razon_social.insert(0, fila[1] or "")
        self.entry_domicilio.delete(0, "end")
        self.entry_domicilio.insert(0, fila[10] or "")
        self.entry_nombre_fantasia.delete(0, "end")
        self.entry_nombre_fantasia.insert(0, fila[2] or "")
        self.entry_cuit.delete(0, "end")
        self.entry_cuit.insert(0, fila[3] or "")
        self.combo_condicion_iva.set(fila[4] or self.CONDICIONES_IVA[0])
        self.combo_tipo_factura.set(fila[5] or self.TIPOS_FACTURA[0])
        self.entry_ingresos_brutos.delete(0, "end")
        self.entry_ingresos_brutos.insert(0, fila[11] or "")
        self.entry_fecha_inicio_actividades.delete(0, "end")
        self.entry_fecha_inicio_actividades.insert(0, fila[12] or "")
        self.var_activo.set(1 if fila[7] else 0)
        self.text_observaciones.delete("1.0", "end")
        self.text_observaciones.insert("1.0", fila[8] or "")
        # La columna legacy ambiente_arca sigue siendo el selector de ambiente activo (4B.2D.1).
        try:
            self.ambiente_activo = normalizar_ambiente_arca(fila[9])
        except AmbienteArcaInvalidoError:
            self.ambiente_activo = None
        self._cargar_configuraciones_arca(emisor_id)
        self._actualizar_control_ambiente_activo()

    def guardar_emisor(self):
        razon_social = self.entry_razon_social.get().strip()
        domicilio = self.entry_domicilio.get().strip()
        nombre_fantasia = self.entry_nombre_fantasia.get().strip()
        cuit = self.entry_cuit.get().strip()
        condicion_iva = self.combo_condicion_iva.get().strip()
        tipo_factura = self.combo_tipo_factura.get().strip()
        ingresos_brutos = self.entry_ingresos_brutos.get().strip()
        fecha_inicio_actividades = self.entry_fecha_inicio_actividades.get().strip()
        observaciones = self.text_observaciones.get("1.0", "end").strip()
        activo = 1 if self.var_activo.get() else 0

        if not razon_social:
            messagebox.showerror("Emisores Fiscales", "La razón social es obligatoria.", parent=self)
            return
        if not cuit:
            messagebox.showerror("Emisores Fiscales", "El CUIT es obligatorio.", parent=self)
            return

        try:
            if self.emisor_id_actual is None:
                # Alta: columnas ARCA legacy quedan en sus valores iniciales; la configuracion va por la API por ambiente.
                emisor_id = EmisorFiscalService.guardar(
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    "",
                    activo,
                    observaciones,
                    self.ETIQUETAS_AMBIENTE["HOMOLOGACION"],
                    domicilio,
                    ingresos_brutos,
                    fecha_inicio_actividades,
                    "",
                    "",
                    "",
                    0,
                )
                self.emisor_id_actual = emisor_id
                self.ambiente_activo = "HOMOLOGACION"
            else:
                emisor_id = self.emisor_id_actual
                EmisorFiscalService.actualizar_datos_fiscales(
                    emisor_id,
                    razon_social,
                    nombre_fantasia,
                    cuit,
                    condicion_iva,
                    tipo_factura,
                    activo,
                    observaciones,
                    domicilio,
                    ingresos_brutos,
                    fecha_inicio_actividades,
                )
        except ConfiguracionArcaError as error:
            messagebox.showerror("Emisores Fiscales", f"No se pudo guardar el emisor ({error.codigo}).", parent=self)
            return
        except Exception as error:
            messagebox.showerror("Emisores Fiscales", f"No se pudo guardar el emisor.\n{error}", parent=self)
            return

        errores_arca = self._guardar_configuraciones_arca_modificadas(emisor_id)
        self.cargar_emisores()
        if errores_arca:
            # Se conserva el formulario para corregir; los datos fiscales ya quedaron guardados.
            for ambiente in self.AMBIENTES_ARCA:
                self._refrescar_estado_arca(ambiente)
            self._actualizar_control_ambiente_activo()
            messagebox.showerror(
                "Emisores Fiscales",
                "Datos del emisor guardados, pero no se pudo guardar la configuración ARCA:\n\n"
                + "\n".join(f"• {linea}" for linea in errores_arca),
                parent=self,
            )
            return
        self._actualizar_control_ambiente_activo()
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
