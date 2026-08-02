import os
from datetime import datetime
from pathlib import Path
from tkinter import Menu, StringVar, TclError, messagebox, ttk

import customtkinter as ctk

from config import COLOR_PRINCIPAL
from database import conectar
from pdf.nombre_archivos import nombre_cliente_archivo, nombre_factura_pdf
from services.arca.pdf_fiscal_service import PDFFiscalService
from views.clientes import ClientesFrame
from services.cobro_service import CobroService
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from services.factura_arca_service import FacturaArcaService
from services.resumen_service import ResumenService
from services.whatsapp_service import WhatsAppService
from views.cliente_ficha import FichaClienteFrame


class FacturasElectronicasFrame(ctk.CTkFrame):

    COLOR_ESTADO_COBRO_SIN = "#B43A3A"
    COLOR_ESTADO_COBRO_PARCIAL = "#B36A00"
    COLOR_ESTADO_COBRO_COBRADA = "#1E7E46"
    COLOR_PRIORIDAD_ALTA = "#B43A3A"
    COLOR_PRIORIDAD_MEDIA = "#B36A00"
    COLOR_PRIORIDAD_BAJA = "#8A6D00"
    COLOR_PRIORIDAD_SIN_ACCION = "#2F6F3E"
    COLOR_DETALLE_TEXTO_DEFAULT = "#505050"

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._cache_clientes = {}
        self._facturas_en_memoria = []
        self._facturas_por_id = {}
        self._cache_emisores = {}
        self._clientes_bridge = None
        self._busqueda_var = StringVar()
        self._estado_var = StringVar(value="Todos")
        self._estado_cobro_var = StringVar(value="Todos")
        self._vista_pendientes_activa = False
        self._usar_orden_pendientes_default = False
        self._columnas_ordenables = {
            "fecha",
            "cliente",
            "tipo",
            "punto_venta",
            "numero",
            "total",
            "estado",
            "estado_cobro",
            "dias_atraso",
            "prioridad",
        }
        self._orden_columna = None
        self._orden_descendente = False
        self.crear_interfaz()
        self._busqueda_var.trace_add("write", self._on_busqueda_cambiada)
        self._estado_var.trace_add("write", self._on_busqueda_cambiada)
        self._estado_cobro_var.trace_add("write", self._on_busqueda_cambiada)
        self.cargar_facturas()

    def crear_interfaz(self):
        titulo = ctk.CTkLabel(
            self,
            text="FACTURAS ELECTRÓNICAS",
            font=("Arial", 26, "bold"),
            text_color=COLOR_PRINCIPAL,
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        descripcion = ctk.CTkLabel(
            self,
            text="Consulta de facturas ARCA registradas en la base de datos.",
            font=("Arial", 12),
            text_color="#4A4A4A",
        )
        descripcion.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        buscador_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        buscador_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 8))
        buscador_frame.grid_columnconfigure(1, weight=1)

        etiqueta_buscar = ctk.CTkLabel(
            buscador_frame,
            text="Buscar:",
            font=("Arial", 13, "bold"),
            text_color="#303030",
        )
        etiqueta_buscar.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.entrada_busqueda = ctk.CTkEntry(
            buscador_frame,
            textvariable=self._busqueda_var,
            placeholder_text="Cliente, punto de venta, número, CAE, tipo o estado",
        )
        self.entrada_busqueda.grid(row=0, column=1, sticky="ew", padx=(0, 12))

        etiqueta_estado = ctk.CTkLabel(
            buscador_frame,
            text="Estado:",
            font=("Arial", 13, "bold"),
            text_color="#303030",
        )
        etiqueta_estado.grid(row=0, column=2, sticky="w", padx=(0, 8))

        self.combo_estado = ctk.CTkComboBox(
            buscador_frame,
            values=["Todos", "Emitidas", "Pendientes"],
            variable=self._estado_var,
            state="readonly",
            width=140,
        )
        self.combo_estado.grid(row=0, column=3, sticky="e")

        etiqueta_estado_cobro = ctk.CTkLabel(
            buscador_frame,
            text="Estado de cobro:",
            font=("Arial", 13, "bold"),
            text_color="#303030",
        )
        etiqueta_estado_cobro.grid(row=0, column=4, sticky="w", padx=(14, 8))

        self.combo_estado_cobro = ctk.CTkComboBox(
            buscador_frame,
            values=["Todos", "Sin cobrar", "Parcialmente cobradas", "Cobradas"],
            variable=self._estado_cobro_var,
            state="readonly",
            width=210,
        )
        self.combo_estado_cobro.grid(row=0, column=5, sticky="e")

        self.boton_pendientes_cobro = ctk.CTkButton(
            buscador_frame,
            text="Ver pendientes de cobro",
            width=210,
            command=self._alternar_vista_pendientes,
        )
        self.boton_pendientes_cobro.grid(row=0, column=6, sticky="e", padx=(12, 0))

        resumen_frame = ctk.CTkFrame(self, fg_color="#F4F4F4", corner_radius=8)
        resumen_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        for columna in range(4):
            resumen_frame.grid_columnconfigure(columna, weight=1, uniform="resumen")

        self._resumen_visible_labels = {
            "facturas": self._crear_indicador_resumen_visible(
                resumen_frame, 0, "Facturas visibles", "0"
            ),
            "facturado": self._crear_indicador_resumen_visible(
                resumen_frame, 1, "Total facturado", self._formatear_moneda(0)
            ),
            "cobrado": self._crear_indicador_resumen_visible(
                resumen_frame, 2, "Total cobrado", self._formatear_moneda(0)
            ),
            "saldo": self._crear_indicador_resumen_visible(
                resumen_frame, 3, "Saldo pendiente", self._formatear_moneda(0)
            ),
        }

        contenido_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        contenido_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 20))
        contenido_frame.grid_rowconfigure(0, weight=1)
        contenido_frame.grid_columnconfigure(0, weight=1)

        tabla_frame = ctk.CTkFrame(contenido_frame, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        panel_detalle = ctk.CTkFrame(contenido_frame, fg_color="#F7F7F7", corner_radius=8)
        panel_detalle.grid(row=0, column=1, sticky="nsew")
        panel_detalle.grid_columnconfigure(0, weight=1)
        panel_detalle.grid_rowconfigure(1, weight=1)

        columnas = (
            "fecha",
            "cliente",
            "tipo",
            "punto_venta",
            "numero",
            "total",
            "cae",
            "estado",
            "estado_cobro",
            "dias_atraso",
            "prioridad",
        )
        self.tabla = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            height=16,
            style="FacturasElectronicas.Treeview",
        )
        self.tabla.bind("<Double-1>", self._abrir_pdf_desde_doble_clic)
        self.tabla.bind("<Button-3>", self._mostrar_menu_contextual)
        self.tabla.bind("<<TreeviewSelect>>", self._on_seleccion_factura)
        self.menu_contextual = Menu(self, tearoff=0)
        self.menu_contextual.add_command(label="Abrir PDF", command=self._abrir_pdf_desde_menu)
        self.menu_contextual.add_command(
            label="Enviar por WhatsApp",
            command=self._enviar_whatsapp_desde_menu,
        )
        self.menu_contextual.add_command(label="Abrir cliente", command=self._abrir_cliente_desde_menu)
        self.menu_contextual.add_command(label="Abrir resumen", command=self._abrir_resumen_desde_menu)
        encabezados = {
            "fecha": ("Fecha", 110),
            "cliente": ("Cliente", 290),
            "tipo": ("Tipo", 70),
            "punto_venta": ("Punto de venta", 110),
            "numero": ("Número", 110),
            "total": ("Total", 120),
            "cae": ("CAE", 130),
            "estado": ("Estado", 160),
            "estado_cobro": ("Estado de cobro", 170),
            "dias_atraso": ("Días de atraso", 120),
            "prioridad": ("Prioridad", 120),
        }
        for columna, (texto, ancho) in encabezados.items():
            if columna in self._columnas_ordenables:
                self.tabla.heading(
                    columna,
                    text=texto,
                    command=lambda c=columna: self._on_ordenar_columna(c),
                )
            else:
                self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                anchor="e" if columna in ("punto_venta", "numero", "total", "dias_atraso") else "w",
                stretch=columna == "cliente",
            )

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll_y.set)
        self._configurar_estilo_tabla_estado_cobro()
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        self.mensaje_vacio = ctk.CTkLabel(
            tabla_frame,
            text="No hay facturas electrónicas registradas.",
            font=("Arial", 13),
            text_color="#6A6A6A",
        )

        ctk.CTkLabel(
            panel_detalle,
            text="Detalle de factura",
            font=("Arial", 15, "bold"),
            text_color="#202020",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        detalle_frame = ctk.CTkScrollableFrame(
            panel_detalle,
            fg_color="transparent",
            corner_radius=0,
        )
        detalle_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 6))
        detalle_frame.grid_columnconfigure(0, weight=1)

        self._detalle_labels = {}
        campos_detalle = [
            ("cliente", "Cliente"),
            ("tipo", "Tipo de comprobante"),
            ("punto_venta", "Punto de venta"),
            ("numero", "Número"),
            ("fecha", "Fecha"),
            ("importe", "Importe"),
            ("cobrado", "Cobrado"),
            ("saldo", "Saldo"),
            ("estado_cobro", "Estado de cobro"),
            ("cae", "CAE"),
            ("vencimiento", "Vencimiento"),
            ("dias_atraso", "Días de atraso"),
            ("prioridad", "Prioridad de cobranza"),
            ("emisor", "Emisor"),
            ("resumen", "Resumen relacionado"),
            ("estado", "Estado"),
        ]
        for indice, (clave, titulo) in enumerate(campos_detalle, start=1):
            ctk.CTkLabel(
                detalle_frame,
                text=titulo,
                font=("Arial", 12, "bold"),
                text_color="#303030",
            ).grid(row=indice * 2 - 1, column=0, sticky="w", padx=6, pady=(0, 0))

            valor_label = ctk.CTkLabel(
                detalle_frame,
                text="-",
                font=("Arial", 12),
                text_color=self.COLOR_DETALLE_TEXTO_DEFAULT,
                wraplength=300,
                justify="left",
            )
            valor_label.grid(row=indice * 2, column=0, sticky="w", padx=6, pady=(0, 4))
            self._detalle_labels[clave] = valor_label

        acciones_panel = ctk.CTkFrame(panel_detalle, fg_color="transparent", corner_radius=0)
        acciones_panel.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        self.boton_abrir_pdf_panel = ctk.CTkButton(
            acciones_panel,
            text="Abrir PDF",
            command=self._abrir_pdf_desde_menu,
            state="disabled",
            width=180,
        )
        self.boton_abrir_pdf_panel.pack(fill="x", pady=(0, 6))

        self.boton_whatsapp_panel = ctk.CTkButton(
            acciones_panel,
            text="Enviar por WhatsApp",
            command=self._enviar_whatsapp_desde_menu,
            state="disabled",
            width=180,
        )
        self.boton_whatsapp_panel.pack(fill="x", pady=6)

        self.boton_abrir_cliente_panel = ctk.CTkButton(
            acciones_panel,
            text="Abrir cliente",
            command=self._abrir_cliente_desde_menu,
            state="disabled",
            width=180,
        )
        self.boton_abrir_cliente_panel.pack(fill="x", pady=(6, 6))

        self.boton_abrir_resumen_panel = ctk.CTkButton(
            acciones_panel,
            text="Abrir resumen",
            command=self._abrir_resumen_desde_menu,
            state="disabled",
            width=180,
        )
        self.boton_abrir_resumen_panel.pack(fill="x", pady=(6, 0))

    def cargar_facturas(self):
        filas = FacturaArcaService.listar()
        factura_ids = []
        for fila in filas:
            try:
                factura_ids.append(int(fila[0]))
            except (TypeError, ValueError, IndexError):
                continue

        totales_cobrados = CobroService.totales_por_factura_ids(factura_ids)
        self._facturas_en_memoria = [
            self._normalizar_fila(
                fila,
                totales_cobrados.get(int(fila[0]), 0.0),
            )
            for fila in filas
        ]
        self._facturas_por_id = {
            factura["factura_id"]: factura for factura in self._facturas_en_memoria
        }
        self._aplicar_filtro()

    def _normalizar_fila(self, fila, cobrado_total):
        cliente = self._resolver_nombre_cliente(fila[1])
        tipo = self._formatear_tipo(fila[6])
        punto_venta = self._formatear_punto_venta(fila[5])
        numero = self._formatear_numero(fila[9])
        cae = str(fila[10] or "").strip()
        estado = str(fila[8] or "").strip()
        clase_estado = self._clasificar_estado(cae, estado)
        importe_total = self._clave_float(fila[7])
        cobrado = self._clave_float(cobrado_total)
        saldo = max(importe_total - cobrado, 0.0)
        estado_cobro = self._calcular_estado_cobro(cobrado, importe_total)
        vencimiento_texto = str(fila[11] or "").strip()
        dias_atraso = self._calcular_dias_atraso(vencimiento_texto, estado_cobro)
        prioridad = self._calcular_prioridad_cobranza(estado_cobro, dias_atraso, saldo)
        factura_id = int(fila[0])
        cliente_id = fila[1]
        emisor_id = fila[2]
        resumen_id = fila[3]
        tipo_factura = str(fila[6] or "").strip()
        punto_venta_raw = str(fila[5] or "").strip()
        numero_factura_raw = str(fila[9] or "").strip()
        return {
            "factura_id": factura_id,
            "cliente_id": cliente_id,
            "emisor_id": emisor_id,
            "resumen_id": resumen_id,
            "importe_total": importe_total,
            "cobrado_total": cobrado,
            "saldo_cobro": saldo,
            "estado_cobro": estado_cobro,
            "vencimiento": vencimiento_texto,
            "dias_atraso": dias_atraso,
            "prioridad": prioridad,
            "tipo_factura": tipo_factura,
            "punto_venta_raw": punto_venta_raw,
            "numero_factura_raw": numero_factura_raw,
            "valores_tabla": (
                self._formatear_fecha(fila[4]),
                cliente,
                tipo,
                punto_venta,
                numero,
                self._formatear_moneda(importe_total),
                cae,
                estado,
                estado_cobro,
                self._formatear_dias_atraso_columna(dias_atraso, estado_cobro),
                prioridad,
            ),
            "texto_busqueda": " ".join(
                [
                    cliente,
                    punto_venta,
                    numero,
                    cae,
                    tipo,
                    estado,
                    estado_cobro,
                    prioridad,
                ]
            ).lower(),
            "clase_estado": clase_estado,
            "orden": {
                "fecha": self._clave_fecha(fila[4]),
                "cliente": cliente.lower(),
                "tipo": tipo.lower(),
                "punto_venta": self._clave_entero(fila[5]),
                "numero": self._clave_numero_factura(fila[9]),
                "total": importe_total,
                "estado": estado.lower(),
                "estado_cobro": self._clave_estado_cobro(estado_cobro),
                "dias_atraso": dias_atraso,
                "prioridad": self._clave_prioridad_cobranza(prioridad),
            },
        }

    @staticmethod
    def _calcular_prioridad_cobranza(estado_cobro, dias_atraso, saldo_pendiente):
        estado = str(estado_cobro or "").strip()
        dias = int(dias_atraso or 0)
        saldo = float(saldo_pendiente or 0)

        if estado == "Cobrada" or saldo <= 0:
            return "SIN ACCIÓN"
        if estado == "Parcialmente cobrada" and dias > 0:
            return "ALTA"
        if estado == "Sin cobrar" and dias > 30:
            return "ALTA"
        if estado == "Sin cobrar" and 8 <= dias <= 30:
            return "MEDIA"
        return "BAJA"

    @staticmethod
    def _clave_prioridad_cobranza(prioridad):
        orden = {
            "ALTA": 0,
            "MEDIA": 1,
            "BAJA": 2,
            "SIN ACCIÓN": 3,
        }
        return orden.get(str(prioridad or "").strip(), 99)

    def _calcular_dias_atraso(self, vencimiento_texto, estado_cobro):
        if str(estado_cobro or "").strip() == "Cobrada":
            return 0

        fecha_vencimiento = self._parsear_fecha(vencimiento_texto)
        if not fecha_vencimiento:
            return 0

        hoy = datetime.now().date()
        diferencia = (hoy - fecha_vencimiento.date()).days
        if diferencia <= 0:
            return 0
        return diferencia

    @staticmethod
    def _parsear_fecha(valor):
        texto = str(valor or "").strip()
        if not texto:
            return None

        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:10], formato)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _formatear_dias_atraso_columna(dias_atraso, estado_cobro):
        if str(estado_cobro or "").strip() == "Cobrada":
            return "-"
        return str(int(dias_atraso or 0))

    @staticmethod
    def _calcular_estado_cobro(cobrado, importe_total):
        cobrado_valor = float(cobrado or 0)
        importe_valor = float(importe_total or 0)

        if cobrado_valor <= 0:
            return "Sin cobrar"
        if cobrado_valor < importe_valor:
            return "Parcialmente cobrada"
        return "Cobrada"

    @staticmethod
    def _clave_estado_cobro(estado_cobro):
        orden = {
            "Sin cobrar": 0,
            "Parcialmente cobrada": 1,
            "Cobrada": 2,
        }
        return orden.get(str(estado_cobro or "").strip(), 99)

    def _on_busqueda_cambiada(self, *_):
        self._aplicar_filtro()

    def _alternar_vista_pendientes(self):
        self._vista_pendientes_activa = not self._vista_pendientes_activa
        if self._vista_pendientes_activa:
            self._usar_orden_pendientes_default = True
            self._orden_columna = None
            self._orden_descendente = False
            # Evita conflicto entre el atajo de pendientes y el combo de estado de cobro.
            self._estado_cobro_var.set("Todos")
        else:
            self._usar_orden_pendientes_default = False

        self._actualizar_texto_boton_pendientes()
        self._aplicar_filtro()

    def _actualizar_texto_boton_pendientes(self):
        if self._vista_pendientes_activa:
            self.boton_pendientes_cobro.configure(text="Mostrar todas")
        else:
            self.boton_pendientes_cobro.configure(text="Ver pendientes de cobro")

    @staticmethod
    def _crear_indicador_resumen_visible(master, columna, titulo, valor):
        bloque = ctk.CTkFrame(master, fg_color="transparent", corner_radius=0)
        bloque.grid(row=0, column=columna, sticky="ew", padx=10, pady=8)

        ctk.CTkLabel(
            bloque,
            text=titulo,
            font=("Arial", 11, "bold"),
            text_color="#4A4A4A",
        ).pack(anchor="w")

        valor_label = ctk.CTkLabel(
            bloque,
            text=valor,
            font=("Arial", 17, "bold"),
            text_color="#1F1F1F",
        )
        valor_label.pack(anchor="w", pady=(2, 0))
        return valor_label

    def _actualizar_resumen_visible(self, facturas_visibles):
        cantidad = len(facturas_visibles)
        total_facturado = sum(float(factura.get("importe_total") or 0) for factura in facturas_visibles)
        total_cobrado = sum(float(factura.get("cobrado_total") or 0) for factura in facturas_visibles)
        total_saldo = sum(float(factura.get("saldo_cobro") or 0) for factura in facturas_visibles)

        self._resumen_visible_labels["facturas"].configure(text=str(cantidad))
        self._resumen_visible_labels["facturado"].configure(text=self._formatear_moneda(total_facturado))
        self._resumen_visible_labels["cobrado"].configure(text=self._formatear_moneda(total_cobrado))
        self._resumen_visible_labels["saldo"].configure(text=self._formatear_moneda(total_saldo))

    def _aplicar_filtro(self):
        termino = self._busqueda_var.get().strip().lower()
        estado_filtro = self._estado_var.get().strip()
        estado_cobro_filtro = self._estado_cobro_var.get().strip()
        facturas_filtradas = []

        mapa_estado_cobro = {
            "Sin cobrar": "Sin cobrar",
            "Parcialmente cobradas": "Parcialmente cobrada",
            "Cobradas": "Cobrada",
        }
        estado_cobro_normalizado = mapa_estado_cobro.get(estado_cobro_filtro, "")

        for factura in self._facturas_en_memoria:
            coincide_busqueda = not termino or termino in factura["texto_busqueda"]
            coincide_estado = (
                estado_filtro == "Todos" or factura["clase_estado"] == estado_filtro
            )
            coincide_pendientes_rapido = (
                not self._vista_pendientes_activa
                or factura.get("estado_cobro") in {"Sin cobrar", "Parcialmente cobrada"}
            )
            coincide_estado_cobro = (
                estado_cobro_filtro == "Todos"
                or factura.get("estado_cobro") == estado_cobro_normalizado
            )
            if (
                coincide_busqueda
                and coincide_estado
                and coincide_pendientes_rapido
                and coincide_estado_cobro
            ):
                facturas_filtradas.append(factura)

        if self._vista_pendientes_activa and self._usar_orden_pendientes_default:
            facturas_filtradas = self._ordenar_pendientes_por_defecto(facturas_filtradas)
        else:
            facturas_filtradas = self._ordenar_facturas(facturas_filtradas)

        self._renderizar_facturas(facturas_filtradas)

    def _on_ordenar_columna(self, columna):
        self._usar_orden_pendientes_default = False
        if self._orden_columna == columna:
            self._orden_descendente = not self._orden_descendente
        else:
            self._orden_columna = columna
            self._orden_descendente = False
        self._aplicar_filtro()

    def _ordenar_facturas(self, facturas):
        if not self._orden_columna:
            return facturas

        return sorted(
            facturas,
            key=lambda factura: factura["orden"][self._orden_columna],
            reverse=self._orden_descendente,
        )

    @staticmethod
    def _ordenar_pendientes_por_defecto(facturas):
        return sorted(
            facturas,
            key=lambda factura: (
                factura["orden"]["fecha"],
                factura["orden"]["cliente"],
                factura["orden"]["numero"],
            ),
        )

    @staticmethod
    def _clasificar_estado(cae, estado):
        cae_texto = str(cae or "").strip()
        estado_texto = str(estado or "").strip().lower()

        if cae_texto:
            return "Emitidas"

        if any(palabra in estado_texto for palabra in ("facturada", "emitida", "autorizada")):
            return "Emitidas"

        if "pendiente" in estado_texto:
            return "Pendientes"

        return "Pendientes"

    def _renderizar_facturas(self, facturas):
        self.tabla.delete(*self.tabla.get_children())
        self._actualizar_resumen_visible(facturas)

        if not self._facturas_en_memoria:
            self.mensaje_vacio.grid(row=0, column=0)
            self.mensaje_vacio.configure(text="No hay facturas electrónicas registradas.")
            return

        if not facturas:
            self.mensaje_vacio.grid(row=0, column=0)
            self.mensaje_vacio.configure(text="No se encontraron facturas para la búsqueda.")
            return

        self.mensaje_vacio.grid_remove()
        for factura in facturas:
            tag_estado_cobro = self._tag_estado_cobro_fila(factura.get("estado_cobro"))
            tag_prioridad = self._tag_prioridad_fila(factura.get("prioridad"))
            self.tabla.insert(
                "",
                "end",
                iid=str(factura["factura_id"]),
                values=factura["valores_tabla"],
                tags=(tag_estado_cobro, tag_prioridad),
            )

        seleccion_actual = self.tabla.selection()
        if seleccion_actual:
            self._actualizar_panel_detalle()
        else:
            self._limpiar_panel_detalle()

    def _on_seleccion_factura(self, _event=None):
        self._actualizar_panel_detalle()

    def _actualizar_panel_detalle(self):
        factura = self._obtener_factura_seleccionada()
        if not factura:
            self._limpiar_panel_detalle()
            return

        emisor = self._resolver_nombre_emisor_para_panel(factura.get("emisor_id"))
        resumen_id = factura.get("resumen_id")
        resumen_texto = f"ID {resumen_id}" if resumen_id else "-"

        detalle = {
            "cliente": self._valor_o_guion(factura["valores_tabla"][1]),
            "tipo": self._valor_o_guion(factura.get("tipo_factura")),
            "punto_venta": self._valor_o_guion(factura["valores_tabla"][3]),
            "numero": self._valor_o_guion(factura.get("numero_factura_raw") or factura["valores_tabla"][4]),
            "fecha": self._valor_o_guion(factura["valores_tabla"][0]),
            "importe": self._valor_o_guion(self._formatear_moneda(factura.get("importe_total"))),
            "cobrado": self._valor_o_guion(self._formatear_moneda(factura.get("cobrado_total"))),
            "saldo": self._valor_o_guion(self._formatear_moneda(factura.get("saldo_cobro"))),
            "estado_cobro": self._valor_o_guion(factura.get("estado_cobro")),
            "estado": self._valor_o_guion(factura["valores_tabla"][7]),
            "cae": self._valor_o_guion(factura["valores_tabla"][6]),
            "vencimiento": self._valor_o_guion(self._formatear_fecha(factura.get("vencimiento"))),
            "dias_atraso": f"{int(factura.get('dias_atraso') or 0)} días",
            "prioridad": self._valor_o_guion(factura.get("prioridad")),
            "emisor": self._valor_o_guion(emisor),
            "resumen": resumen_texto,
        }

        for clave, label in self._detalle_labels.items():
            label.configure(text_color=self.COLOR_DETALLE_TEXTO_DEFAULT)
            label.configure(text=detalle.get(clave, "-"))

        self._detalle_labels["estado_cobro"].configure(
            text_color=self._color_texto_estado_cobro(detalle.get("estado_cobro"))
        )
        self._detalle_labels["prioridad"].configure(
            text_color=self._color_texto_prioridad(detalle.get("prioridad"))
        )

        self._actualizar_estado_botones_panel(True)

    def _limpiar_panel_detalle(self):
        for label in self._detalle_labels.values():
            label.configure(text="-", text_color=self.COLOR_DETALLE_TEXTO_DEFAULT)
        self._actualizar_estado_botones_panel(False)

    def _configurar_estilo_tabla_estado_cobro(self):
        estilo = ttk.Style(self)
        estilo.map(
            "FacturasElectronicas.Treeview",
            background=[("selected", "#1F6AA5")],
            foreground=[("selected", "#FFFFFF")],
        )

        # Si no hay soporte estable por celda en Treeview, coloreamos la fila completa por tag.
        self.tabla.tag_configure(
            "estado_cobro_sin",
            background="#FDEDED",
            foreground="#5A2222",
        )
        self.tabla.tag_configure(
            "estado_cobro_parcial",
            background="#FFF3DF",
            foreground="#6A4A1A",
        )
        self.tabla.tag_configure(
            "estado_cobro_cobrada",
            background="#EAF7EE",
            foreground="#1E4D32",
        )
        self.tabla.tag_configure("prioridad_alta", foreground=self.COLOR_PRIORIDAD_ALTA)
        self.tabla.tag_configure("prioridad_media", foreground=self.COLOR_PRIORIDAD_MEDIA)
        self.tabla.tag_configure("prioridad_baja", foreground=self.COLOR_PRIORIDAD_BAJA)
        self.tabla.tag_configure(
            "prioridad_sin_accion",
            foreground=self.COLOR_PRIORIDAD_SIN_ACCION,
        )

    @staticmethod
    def _tag_estado_cobro_fila(estado_cobro):
        texto = str(estado_cobro or "").strip()
        if texto == "Cobrada":
            return "estado_cobro_cobrada"
        if texto == "Parcialmente cobrada":
            return "estado_cobro_parcial"
        return "estado_cobro_sin"

    def _color_texto_estado_cobro(self, estado_cobro):
        texto = str(estado_cobro or "").strip()
        if texto == "Cobrada":
            return self.COLOR_ESTADO_COBRO_COBRADA
        if texto == "Parcialmente cobrada":
            return self.COLOR_ESTADO_COBRO_PARCIAL
        if texto == "Sin cobrar":
            return self.COLOR_ESTADO_COBRO_SIN
        return self.COLOR_DETALLE_TEXTO_DEFAULT

    @staticmethod
    def _tag_prioridad_fila(prioridad):
        texto = str(prioridad or "").strip()
        if texto == "ALTA":
            return "prioridad_alta"
        if texto == "MEDIA":
            return "prioridad_media"
        if texto == "BAJA":
            return "prioridad_baja"
        return "prioridad_sin_accion"

    def _color_texto_prioridad(self, prioridad):
        texto = str(prioridad or "").strip()
        if texto == "ALTA":
            return self.COLOR_PRIORIDAD_ALTA
        if texto == "MEDIA":
            return self.COLOR_PRIORIDAD_MEDIA
        if texto == "BAJA":
            return self.COLOR_PRIORIDAD_BAJA
        if texto == "SIN ACCIÓN":
            return self.COLOR_PRIORIDAD_SIN_ACCION
        return self.COLOR_DETALLE_TEXTO_DEFAULT

    def _actualizar_estado_botones_panel(self, habilitado):
        estado = "normal" if habilitado else "disabled"
        self.boton_abrir_pdf_panel.configure(state=estado)
        self.boton_whatsapp_panel.configure(state=estado)
        self.boton_abrir_cliente_panel.configure(state=estado)
        self.boton_abrir_resumen_panel.configure(state=estado)

    def _resolver_nombre_emisor_para_panel(self, emisor_id):
        if not emisor_id:
            return ""
        if emisor_id in self._cache_emisores:
            return self._cache_emisores[emisor_id]

        emisor_fiscal = self._resolver_emisor_fiscal_desde_factura(emisor_id)
        if emisor_fiscal:
            nombre = EmisorFiscalService.etiqueta_visible(emisor_fiscal)
        else:
            emisor_interno = EmisorService.obtener(emisor_id)
            if emisor_interno:
                nombre = str(emisor_interno[1] or emisor_interno[3] or "").strip()
            else:
                nombre = ""

        self._cache_emisores[emisor_id] = nombre
        return nombre

    @staticmethod
    def _valor_o_guion(valor):
        texto = str(valor or "").strip()
        return texto if texto else "-"

    def _abrir_pdf_desde_doble_clic(self, _event=None):
        datos = self._resolver_pdf_factura_seleccionada()
        if not datos:
            return

        try:
            os.startfile(str(datos["ruta_pdf"]))
        except OSError as error:
            messagebox.showwarning(
                "Facturas electrónicas",
                f"No se pudo abrir el PDF asociado a esta factura.\n\n{error}",
                parent=self,
            )

    def _resolver_pdf_factura_seleccionada(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning(
                "Facturas electrónicas",
                "Seleccione una factura para continuar.",
                parent=self,
            )
            return None

        try:
            factura_id = int(seleccion[0])
        except (TypeError, ValueError):
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar la factura seleccionada.",
                parent=self,
            )
            return None

        factura = self._facturas_por_id.get(factura_id)
        if not factura:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se encontró la información de la factura seleccionada.",
                parent=self,
            )
            return None

        valores_fila = self.tabla.item(seleccion[0], "values")
        if not valores_fila or len(valores_fila) < 8:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo leer la fila seleccionada para ubicar el PDF.",
                parent=self,
            )
            return None

        emisor_fiscal = self._resolver_emisor_fiscal_desde_factura(factura.get("emisor_id"))
        if not emisor_fiscal:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar el emisor fiscal para esta factura.",
                parent=self,
            )
            return None

        carpeta_facturas = str(emisor_fiscal[13] if len(emisor_fiscal) > 13 else "" or "").strip()
        if not carpeta_facturas:
            messagebox.showwarning(
                "Facturas electrónicas",
                "El emisor fiscal no tiene configurada la carpeta de facturas.",
                parent=self,
            )
            return None

        cliente_id = factura.get("cliente_id")
        tipo_factura = self._tipo_factura_desde_fila(str(valores_fila[2] or "").strip())
        punto_venta = str(valores_fila[3] or "").strip()
        numero_factura = str(valores_fila[4] or "").strip()
        codigo_factura = self._reconstruir_codigo_factura(numero_factura, punto_venta)

        if not cliente_id or not tipo_factura or not codigo_factura:
            messagebox.showwarning(
                "Facturas electrónicas",
                "Faltan datos para ubicar el PDF asociado a esta factura.",
                parent=self,
            )
            return None

        nombre_pdf = nombre_factura_pdf(cliente_id, tipo_factura, codigo_factura)
        ruta_pdf_estandar = Path(carpeta_facturas) / nombre_pdf
        ruta_pdf = ruta_pdf_estandar
        if not ruta_pdf.is_file():
            coincidencias = self._buscar_pdf_historico_compatible(
                carpeta_facturas=carpeta_facturas,
                cliente_id=cliente_id,
                tipo_factura=tipo_factura,
                codigo_factura=codigo_factura,
            )
            if len(coincidencias) == 1:
                ruta_pdf = coincidencias[0]
            elif len(coincidencias) > 1:
                messagebox.showwarning(
                    "Facturas electrónicas",
                    "Se encontraron varios PDFs posibles para esta factura."
                    "\nRevise la carpeta del emisor para abrir el archivo correcto.",
                    parent=self,
                )
                return None

        ruta_pdf_inicial = ruta_pdf
        regenerado = False
        if tipo_factura == "Factura A":
            ruta_pdf, regenerado = self._asegurar_pdf_fiscal_actualizado_factura_a(
                factura=factura,
                valores_fila=valores_fila,
                emisor_fiscal=emisor_fiscal,
                carpeta_facturas=carpeta_facturas,
                ruta_pdf_estandar=ruta_pdf_estandar,
                ruta_pdf_resuelta=ruta_pdf,
                cliente_id=cliente_id,
                tipo_factura=tipo_factura,
                codigo_factura=codigo_factura,
            )

        if not ruta_pdf.is_file():
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se encontró el PDF asociado a esta factura.",
                parent=self,
            )
            return None

        coincide_con_estandar = False
        try:
            coincide_con_estandar = ruta_pdf.resolve() == ruta_pdf_estandar.resolve()
        except OSError:
            coincide_con_estandar = False

        print(
            "DIAGNOSTICO PDF FACTURAS ELECTRONICAS | "
            f"factura_id={factura_id} | tipo={tipo_factura} | "
            f"ruta_elegida_inicial={ruta_pdf_inicial} | "
            f"archivo={ruta_pdf.name} | "
            f"fecha_archivo={self._fecha_modificacion_archivo(ruta_pdf)} | "
            f"regenerado={regenerado} | "
            f"coincide_con_ruta_estandar={coincide_con_estandar} | "
            f"ruta_final_abierta={ruta_pdf}"
        )

        return {
            "factura": factura,
            "valores_fila": valores_fila,
            "ruta_pdf": ruta_pdf,
        }

    def _asegurar_pdf_fiscal_actualizado_factura_a(
        self,
        factura,
        valores_fila,
        emisor_fiscal,
        carpeta_facturas,
        ruta_pdf_estandar,
        ruta_pdf_resuelta,
        cliente_id,
        tipo_factura,
        codigo_factura,
    ):
        ruta_estandar = Path(ruta_pdf_estandar)
        ruta_resuelta = Path(ruta_pdf_resuelta)

        requiere_regenerar = False
        if not ruta_estandar.is_file():
            requiere_regenerar = True
        else:
            tiene_desglose = self._pdf_contiene_desglose_factura_a(ruta_estandar)
            if not tiene_desglose:
                requiere_regenerar = True

            if ruta_resuelta.is_file() and ruta_resuelta.resolve() != ruta_estandar.resolve():
                try:
                    if ruta_resuelta.stat().st_mtime > ruta_estandar.stat().st_mtime:
                        requiere_regenerar = True
                except OSError:
                    pass

        if not requiere_regenerar:
            return ruta_estandar if ruta_estandar.is_file() else ruta_resuelta, False

        datos_pdf = self._construir_datos_pdf_fiscal_desde_factura(
            factura=factura,
            valores_fila=valores_fila,
            emisor_fiscal=emisor_fiscal,
            carpeta_facturas=carpeta_facturas,
            cliente_id=cliente_id,
            tipo_factura=tipo_factura,
            codigo_factura=codigo_factura,
        )
        if not datos_pdf:
            return ruta_resuelta, False

        resultado = PDFFiscalService.generar_factura_c(
            ruta_destino=str(ruta_estandar),
            datos_emisor=datos_pdf["datos_emisor"],
            datos_receptor=datos_pdf["datos_receptor"],
            datos_comprobante=datos_pdf["datos_comprobante"],
        )
        if not resultado.get("ok"):
            return ruta_resuelta, False

        return Path(str(resultado.get("ruta_pdf") or ruta_estandar)), True

    def _construir_datos_pdf_fiscal_desde_factura(
        self,
        factura,
        valores_fila,
        emisor_fiscal,
        carpeta_facturas,
        cliente_id,
        tipo_factura,
        codigo_factura,
    ):
        resumen_id = factura.get("resumen_id")
        if not resumen_id:
            return None

        resumen = ResumenService.obtener(resumen_id)
        cliente = ResumenService.obtener_cliente(resumen_id)
        if not resumen or not cliente:
            return None

        items = []
        for concepto in list(getattr(resumen, "conceptos", []) or []):
            descripcion = str(getattr(concepto, "descripcion", "") or "").strip()
            nombre_concepto = str(getattr(concepto, "concepto", "") or "").strip()
            texto_item = f"{nombre_concepto} - {descripcion}" if descripcion else nombre_concepto
            items.append(
                {
                    "cantidad": float(getattr(concepto, "cantidad", 0) or 0),
                    "descripcion": texto_item or "Servicio",
                    "precio_unitario": float(getattr(concepto, "importe", 0) or 0),
                    "importe": float(getattr(concepto, "total", 0) or 0),
                }
            )

        neto = round(sum(float(item.get("importe", 0) or 0) for item in items), 2)
        total = round(float(factura.get("importe_total") or 0), 2)
        if total <= 0:
            total = round(float(getattr(resumen, "total", 0) or 0), 2)

        if tipo_factura == "Factura A":
            alicuota = 21.0
            iva = round(total - neto, 2)
            if iva < 0:
                iva = round(neto * (alicuota / 100.0), 2)
                total = round(neto + iva, 2)
        else:
            alicuota = 0.0
            iva = 0.0

        fecha_valor = str(factura.get("valores_tabla_fecha") or "")
        if not fecha_valor and valores_fila and len(valores_fila) > 0:
            fecha_fila = str(valores_fila[0] or "").strip()
            try:
                fecha_valor = datetime.strptime(fecha_fila, "%d/%m/%Y").strftime("%Y%m%d")
            except (TypeError, ValueError):
                fecha_valor = datetime.now().strftime("%Y%m%d")

        vto_cae = str(factura.get("vencimiento") or "").strip()
        if len(vto_cae) == 10 and "-" in vto_cae:
            vto_cae = vto_cae.replace("-", "")

        numero_comprobante = 0
        try:
            numero_comprobante = int(str(codigo_factura).split("-", 1)[1])
        except (TypeError, ValueError, IndexError):
            try:
                numero_comprobante = int(str(factura.get("numero_factura_raw") or "0").split("-", 1)[-1])
            except (TypeError, ValueError):
                numero_comprobante = 0

        punto_venta = str(factura.get("punto_venta_raw") or "").strip()
        if not punto_venta and "-" in codigo_factura:
            punto_venta = str(codigo_factura).split("-", 1)[0]

        datos_emisor = {
            "razon_social": str(emisor_fiscal[1] if len(emisor_fiscal) > 1 else "" or ""),
            "nombre_fantasia": str(emisor_fiscal[2] if len(emisor_fiscal) > 2 else "" or ""),
            "cuit": self._normalizar_cuit(emisor_fiscal[3] if len(emisor_fiscal) > 3 else "") or "",
            "condicion_iva": str(emisor_fiscal[4] if len(emisor_fiscal) > 4 else "" or ""),
            "domicilio": str(emisor_fiscal[10] if len(emisor_fiscal) > 10 else "" or ""),
            "punto_venta": punto_venta,
            "carpeta_facturas": carpeta_facturas,
        }

        datos_receptor = {
            "razon_social": str(cliente[2] if len(cliente) > 2 else "" or ""),
            "cuit": str(cliente[9] if len(cliente) > 9 else "" or ""),
            "documento": str(cliente[9] if len(cliente) > 9 else "" or ""),
            "condicion_iva": str(cliente[10] if len(cliente) > 10 else "" or ""),
            "domicilio": self._combinar_domicilio_cliente(cliente),
        }

        datos_comprobante = {
            "tipo": tipo_factura,
            "numero": numero_comprobante,
            "fecha": fecha_valor,
            "concepto": "1 - Productos",
            "periodo_servicio_desde": "",
            "periodo_servicio_hasta": "",
            "vencimiento_pago": "",
            "importe_neto": neto,
            "importe_iva": iva,
            "alicuota_iva": alicuota,
            "importe_total": total,
            "items": items,
            "moneda": "PES",
            "cae": str(valores_fila[6] if valores_fila and len(valores_fila) > 6 else "" or ""),
            "vencimiento_cae": vto_cae,
            "ambiente": str(emisor_fiscal[9] if len(emisor_fiscal) > 9 else "Homologación"),
            "punto_venta": punto_venta,
        }
        return {
            "datos_emisor": datos_emisor,
            "datos_receptor": datos_receptor,
            "datos_comprobante": datos_comprobante,
        }

    @staticmethod
    def _pdf_contiene_desglose_factura_a(ruta_pdf):
        try:
            contenido = Path(ruta_pdf).read_bytes().decode("latin-1", errors="ignore").lower()
        except OSError:
            return False

        return (
            "importe neto gravado" in contenido
            and "iva" in contenido
            and "importe total" in contenido
        )

    @staticmethod
    def _fecha_modificacion_archivo(ruta_pdf):
        try:
            marca = Path(ruta_pdf).stat().st_mtime
            return datetime.fromtimestamp(marca).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            return "-"

    @staticmethod
    def _combinar_domicilio_cliente(cliente_fila):
        direccion = str(cliente_fila[5] if len(cliente_fila) > 5 else "" or "").strip()
        localidad = str(cliente_fila[6] if len(cliente_fila) > 6 else "" or "").strip()
        if direccion and localidad:
            return f"{direccion} - {localidad}"
        return direccion or localidad

    def _mostrar_menu_contextual(self, event):
        fila = self.tabla.identify_row(event.y)
        if not fila:
            return

        self.tabla.selection_set(fila)
        self.tabla.focus(fila)
        try:
            self.menu_contextual.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu_contextual.grab_release()

    def _abrir_pdf_desde_menu(self):
        self._abrir_pdf_desde_doble_clic()

    def _enviar_whatsapp_desde_menu(self):
        datos = self._resolver_pdf_factura_seleccionada()
        if not datos:
            return

        factura = datos["factura"]
        cliente_id = factura.get("cliente_id")
        contacto = self._obtener_contacto_cliente_para_whatsapp(cliente_id)
        if not contacto:
            messagebox.showwarning(
                "WhatsApp",
                "No se encontró el cliente asociado a esta factura.",
                parent=self,
            )
            return

        numero_destino = contacto["numero_destino"]
        if not numero_destino:
            messagebox.showwarning(
                "WhatsApp",
                "El cliente no tiene WhatsApp ni teléfono cargado.",
                parent=self,
            )
            return

        valores_fila = datos["valores_fila"]
        mensaje = self._crear_mensaje_whatsapp_factura(
            nombre_cliente=contacto["nombre"],
            tipo_factura=str(valores_fila[2] or "").strip(),
            numero_factura=str(valores_fila[4] or "").strip(),
            importe=str(valores_fila[5] or "").strip(),
        )

        try:
            resultado = WhatsAppService.abrir_whatsapp_factura(
                numero=numero_destino,
                mensaje=mensaje,
                pdf_path=str(datos["ruta_pdf"]),
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("WhatsApp", str(error), parent=self)
            return

        origen = "WhatsApp" if contacto["fuente"] == "whatsapp" else "Teléfono"
        canal_resultado = str(resultado.get("canal") or "")
        if canal_resultado == "desktop+web":
            canal = "WhatsApp Desktop + fallback Web"
        elif canal_resultado == "web":
            canal = "WhatsApp Web"
        else:
            canal = "WhatsApp Desktop"

        url_usada = str(resultado.get("url") or "")
        messagebox.showinfo(
            "WhatsApp",
            f"Se abrió {canal} con el mensaje preparado.\n"
            f"Número utilizado: {origen}.\n"
            f"URL usada: {url_usada}\n"
            "Se abrió también el Explorador con el PDF seleccionado para adjuntarlo manualmente.",
            parent=self,
        )

        advertencia_explorador = str(resultado.get("explorador_advertencia") or "").strip()
        if advertencia_explorador:
            messagebox.showwarning("WhatsApp", advertencia_explorador, parent=self)

    def _obtener_contacto_cliente_para_whatsapp(self, cliente_id):
        if not cliente_id:
            return None

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(razon_social, ''), ''),
                COALESCE(NULLIF(nombre_comercial, ''), ''),
                COALESCE(whatsapp, ''),
                COALESCE(telefono, '')
            FROM clientes
            WHERE id=?
            """,
            (cliente_id,),
        )
        fila = cur.fetchone()
        conn.close()

        if not fila:
            return None

        nombre = str(fila[0] or "").strip() or str(fila[1] or "").strip() or "Cliente"
        whatsapp = str(fila[2] or "").strip()
        telefono = str(fila[3] or "").strip()
        if whatsapp:
            return {"nombre": nombre, "numero_destino": whatsapp, "fuente": "whatsapp"}
        if telefono:
            return {"nombre": nombre, "numero_destino": telefono, "fuente": "telefono"}
        return {"nombre": nombre, "numero_destino": "", "fuente": ""}

    @staticmethod
    def _crear_mensaje_whatsapp_factura(nombre_cliente, tipo_factura, numero_factura, importe):
        nombre = str(nombre_cliente or "Cliente").strip()
        tipo = str(tipo_factura or "Factura").strip()
        numero = str(numero_factura or "").strip()
        importe_texto = str(importe or "-").strip()
        return (
            f"Hola {nombre}.\n\n"
            f"Te enviamos la Factura {tipo} {numero} correspondiente.\n\n"
            f"Importe: {importe_texto}\n\n"
            "Muchas gracias.\n\n"
            "FM Master 98.3"
        )

    def _abrir_cliente_desde_menu(self):
        factura = self._obtener_factura_seleccionada()
        if not factura:
            return

        cliente_id = factura.get("cliente_id")
        if not cliente_id:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar el cliente asociado a esta factura.",
                parent=self,
            )
            return

        self._abrir_ficha_cliente(cliente_id)

    def _abrir_resumen_desde_menu(self):
        factura = self._obtener_factura_seleccionada()
        if not factura:
            return

        resumen_id = factura.get("resumen_id")
        if not resumen_id:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar el resumen asociado a esta factura.",
                parent=self,
            )
            return

        cliente_id = factura.get("cliente_id")
        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_resumenes"):
            aplicacion.mostrar_resumenes(
                cliente_id=cliente_id,
                origen_creacion="facturas_electronicas.abrir_resumen_cliente",
            )
            self._seleccionar_resumen_en_vista(aplicacion, resumen_id)
            aplicacion.lift()
            aplicacion.focus_force()

    def _seleccionar_resumen_en_vista(self, aplicacion, resumen_id):
        panel = getattr(aplicacion, "panel", None)
        if panel is None:
            return

        for child in panel.winfo_children():
            tabla = getattr(child, "tabla", None)
            if tabla is None:
                continue

            for item in tabla.get_children():
                valores = tabla.item(item, "values")
                if not valores:
                    continue
                try:
                    item_resumen_id = int(valores[0])
                except (TypeError, ValueError):
                    continue
                if item_resumen_id == int(resumen_id):
                    tabla.selection_set(item)
                    tabla.focus(item)
                    tabla.see(item)
                    return

    def _obtener_factura_seleccionada(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None

        try:
            factura_id = int(seleccion[0])
        except (TypeError, ValueError):
            return None

        return self._facturas_por_id.get(factura_id)

    def _abrir_ficha_cliente(self, cliente_id):
        try:
            cliente_id = int(cliente_id)
        except (TypeError, ValueError):
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar el cliente asociado a esta factura.",
                parent=self,
            )
            return

        ventana = ctk.CTkToplevel(self)
        ventana.title("Ficha Única del Cliente")
        ventana.geometry("1320x820")
        ventana.minsize(1080, 700)
        ventana.transient(self.winfo_toplevel())

        bridge = self._obtener_clientes_bridge()

        callbacks = {}
        ficha = FichaClienteFrame(ventana, cliente_data=cliente_id, callbacks=callbacks)

        def refrescar_ficha_si_disponible():
            try:
                if not ficha.winfo_exists():
                    return
                toplevel_ficha = ficha.winfo_toplevel()
                if toplevel_ficha is None or not toplevel_ficha.winfo_exists():
                    return
            except TclError:
                return
            ficha.cargar_cliente(cliente_id)

        callbacks["nuevo_resumen"] = lambda _cliente_data: bridge._abrir_resumenes_desde_ficha(
            cliente_id,
            parent_toplevel=ficha.winfo_toplevel(),
            on_cambio=refrescar_ficha_si_disponible,
        )
        callbacks["editar_cliente"] = lambda _cliente_data: bridge._editar_cliente_desde_ficha(
            cliente_id,
            on_guardado=lambda: ficha.cargar_cliente(cliente_id),
        )
        callbacks["registrar_cobro"] = lambda _cliente_data: bridge._abrir_cobros_desde_ficha(
            cliente_id,
            parent_toplevel=ficha.winfo_toplevel(),
            on_cambio=lambda: ficha.cargar_cliente(cliente_id),
        )
        callbacks["nueva_tarea"] = lambda _cliente_data: bridge._abrir_nueva_tarea_desde_ficha(
            cliente_id,
            parent_toplevel=ficha.winfo_toplevel(),
            on_guardado=lambda: ficha.cargar_cliente(cliente_id),
        )
        callbacks["whatsapp"] = lambda _cliente_data: bridge._abrir_whatsapp_desde_ficha(cliente_id)

        ficha.pack(fill="both", expand=True)

        try:
            if ventana.state() == "iconic":
                ventana.deiconify()
        except TclError:
            pass
        ventana.lift()
        ventana.focus_force()

    def _obtener_clientes_bridge(self):
        try:
            if self._clientes_bridge is not None and self._clientes_bridge.winfo_exists():
                return self._clientes_bridge
        except TclError:
            self._clientes_bridge = None

        # Reutiliza la implementación de callbacks de Clientes sin duplicar lógica.
        self._clientes_bridge = ClientesFrame(self.winfo_toplevel())
        return self._clientes_bridge

    def _resolver_emisor_fiscal_desde_factura(self, emisor_id):
        if not emisor_id:
            return None

        emisor_fiscal = EmisorFiscalService.obtener(emisor_id)
        if emisor_fiscal:
            return emisor_fiscal

        emisor_interno = EmisorService.obtener(emisor_id)
        if not emisor_interno:
            return None

        cuit_interno = self._normalizar_cuit(emisor_interno[4] if len(emisor_interno) > 4 else "")
        if not cuit_interno:
            return None

        for emisor in EmisorFiscalService.listar():
            cuit_fiscal = self._normalizar_cuit(emisor[3] if len(emisor) > 3 else "")
            if cuit_fiscal and cuit_fiscal == cuit_interno:
                return emisor

        return None

    @staticmethod
    def _normalizar_cuit(valor):
        digitos = "".join(char for char in str(valor or "") if char.isdigit())
        return digitos if len(digitos) == 11 else None

    @staticmethod
    def _reconstruir_codigo_factura(numero_factura, punto_venta):
        numero_texto = str(numero_factura or "").strip()
        pv_texto = str(punto_venta or "").strip()

        if numero_texto and "-" in numero_texto:
            pv_parte, nro_parte = numero_texto.split("-", 1)
            try:
                return f"{int(pv_parte):05d}-{int(nro_parte):08d}"
            except (TypeError, ValueError):
                return numero_texto

        try:
            pv = int(pv_texto)
            nro = int(numero_texto)
            return f"{pv:05d}-{nro:08d}"
        except (TypeError, ValueError):
            return numero_texto

    @staticmethod
    def _tipo_factura_desde_fila(tipo):
        texto = str(tipo or "").strip().upper()
        if texto == "A":
            return "Factura A"
        if texto == "C":
            return "Factura C"
        return str(tipo or "").strip()

    @staticmethod
    def _buscar_pdf_historico_compatible(carpeta_facturas, cliente_id, tipo_factura, codigo_factura):
        carpeta = Path(str(carpeta_facturas or "").strip())
        if not carpeta.is_dir():
            return []

        codigo = str(codigo_factura or "").strip()
        if "-" not in codigo:
            return []

        punto_venta, numero = codigo.split("-", 1)
        punto_venta = punto_venta.strip()
        numero = numero.strip()
        if not punto_venta or not numero:
            return []

        codigo_guion = f"{punto_venta}-{numero}".lower()
        codigo_guion_bajo = f"{punto_venta}_{numero}".lower()
        tipo_normalizado = FacturasElectronicasFrame._normalizar_texto_archivo(tipo_factura)
        cliente_normalizado = FacturasElectronicasFrame._normalizar_texto_archivo(
            nombre_cliente_archivo(cliente_id)
        )

        candidatos = []
        for archivo in carpeta.glob("*.pdf"):
            nombre = archivo.name.lower()
            if codigo_guion not in nombre and codigo_guion_bajo not in nombre:
                continue
            if tipo_normalizado and tipo_normalizado not in nombre:
                continue
            candidatos.append(archivo)

        if len(candidatos) <= 1:
            return candidatos

        if cliente_normalizado:
            refinados = [
                archivo
                for archivo in candidatos
                if cliente_normalizado in FacturasElectronicasFrame._normalizar_texto_archivo(archivo.stem)
            ]
            if refinados:
                return refinados

        return candidatos

    @staticmethod
    def _normalizar_texto_archivo(texto):
        valor = str(texto or "").strip().lower()
        limpio = []
        for caracter in valor:
            if caracter.isalnum():
                limpio.append(caracter)
            elif caracter in {" ", "-", "_"}:
                limpio.append("_")
        normalizado = "".join(limpio)
        while "__" in normalizado:
            normalizado = normalizado.replace("__", "_")
        return normalizado.strip("_")

    def _resolver_nombre_cliente(self, cliente_id):
        if not cliente_id:
            return "Sin cliente"
        if cliente_id in self._cache_clientes:
            return self._cache_clientes[cliente_id]

        conn = conectar()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(razon_social, ''), ''),
                COALESCE(NULLIF(nombre_comercial, ''), '')
            FROM clientes
            WHERE id=?
            """,
            (cliente_id,),
        )
        fila = cur.fetchone()
        conn.close()

        if not fila:
            nombre = "Sin cliente"
        else:
            razon_social = str(fila[0] or "").strip()
            nombre_comercial = str(fila[1] or "").strip()
            nombre = razon_social or nombre_comercial or "Sin cliente"

        self._cache_clientes[cliente_id] = nombre
        return nombre

    @staticmethod
    def _formatear_fecha(valor):
        texto = str(valor or "").strip()
        try:
            return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return texto

    @staticmethod
    def _formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _formatear_punto_venta(valor):
        try:
            return f"{int(valor or 0):05d}"
        except (TypeError, ValueError):
            return str(valor or "")

    @staticmethod
    def _formatear_numero(valor):
        texto = str(valor or "").strip()
        if texto and "-" in texto:
            partes = texto.split("-", 1)
            ultimo = partes[-1].strip()
            try:
                return f"{int(ultimo):08d}"
            except (TypeError, ValueError):
                return ultimo
        try:
            return f"{int(texto or 0):08d}"
        except (TypeError, ValueError):
            return texto

    @staticmethod
    def _formatear_tipo(valor):
        texto = str(valor or "").strip().upper()
        if texto.endswith(" A"):
            return "A"
        if texto.endswith(" C"):
            return "C"
        if "FACTURA A" in texto:
            return "A"
        if "FACTURA C" in texto:
            return "C"
        return texto

    @staticmethod
    def _clave_fecha(valor):
        texto = str(valor or "").strip()
        try:
            return datetime.strptime(texto[:10], "%Y-%m-%d")
        except (TypeError, ValueError):
            return datetime.min

    @staticmethod
    def _clave_entero(valor):
        try:
            return int(str(valor or "").strip())
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _clave_float(valor):
        try:
            return float(valor or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _clave_numero_factura(valor):
        texto = str(valor or "").strip()
        if texto and "-" in texto:
            texto = texto.split("-", 1)[-1].strip()
        try:
            return int(texto or 0)
        except (TypeError, ValueError):
            return 0