import os
from datetime import datetime
from pathlib import Path
from tkinter import Menu, StringVar, TclError, messagebox, ttk

import customtkinter as ctk

from config import COLOR_PRINCIPAL
from database import conectar
from pdf.nombre_archivos import nombre_factura_pdf
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from services.factura_arca_service import FacturaArcaService
from views.cliente_ficha import FichaClienteFrame


class FacturasElectronicasFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._cache_clientes = {}
        self._facturas_en_memoria = []
        self._facturas_por_id = {}
        self._busqueda_var = StringVar()
        self._estado_var = StringVar(value="Todos")
        self._columnas_ordenables = {
            "fecha",
            "cliente",
            "tipo",
            "punto_venta",
            "numero",
            "total",
            "estado",
        }
        self._orden_columna = None
        self._orden_descendente = False
        self.crear_interfaz()
        self._busqueda_var.trace_add("write", self._on_busqueda_cambiada)
        self._estado_var.trace_add("write", self._on_busqueda_cambiada)
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

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = (
            "fecha",
            "cliente",
            "tipo",
            "punto_venta",
            "numero",
            "total",
            "cae",
            "estado",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=16)
        self.tabla.bind("<Double-1>", self._abrir_pdf_desde_doble_clic)
        self.tabla.bind("<Button-3>", self._mostrar_menu_contextual)
        self.menu_contextual = Menu(self, tearoff=0)
        self.menu_contextual.add_command(label="Abrir PDF", command=self._abrir_pdf_desde_menu)
        self.menu_contextual.add_command(label="Abrir cliente", command=self._abrir_cliente_desde_menu)
        encabezados = {
            "fecha": ("Fecha", 110),
            "cliente": ("Cliente", 290),
            "tipo": ("Tipo", 70),
            "punto_venta": ("Punto de venta", 110),
            "numero": ("Número", 110),
            "total": ("Total", 120),
            "cae": ("CAE", 130),
            "estado": ("Estado", 160),
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
                anchor="e" if columna in ("punto_venta", "numero", "total") else "w",
                stretch=columna == "cliente",
            )

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll_y.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

        self.mensaje_vacio = ctk.CTkLabel(
            tabla_frame,
            text="No hay facturas electrónicas registradas.",
            font=("Arial", 13),
            text_color="#6A6A6A",
        )

    def cargar_facturas(self):
        filas = FacturaArcaService.listar()
        self._facturas_en_memoria = [self._normalizar_fila(fila) for fila in filas]
        self._facturas_por_id = {
            factura["factura_id"]: factura for factura in self._facturas_en_memoria
        }
        self._aplicar_filtro()

    def _normalizar_fila(self, fila):
        cliente = self._resolver_nombre_cliente(fila[1])
        tipo = self._formatear_tipo(fila[6])
        punto_venta = self._formatear_punto_venta(fila[5])
        numero = self._formatear_numero(fila[9])
        cae = str(fila[10] or "").strip()
        estado = str(fila[8] or "").strip()
        clase_estado = self._clasificar_estado(cae, estado)
        factura_id = int(fila[0])
        cliente_id = fila[1]
        emisor_id = fila[2]
        tipo_factura = str(fila[6] or "").strip()
        punto_venta_raw = str(fila[5] or "").strip()
        numero_factura_raw = str(fila[9] or "").strip()
        return {
            "factura_id": factura_id,
            "cliente_id": cliente_id,
            "emisor_id": emisor_id,
            "tipo_factura": tipo_factura,
            "punto_venta_raw": punto_venta_raw,
            "numero_factura_raw": numero_factura_raw,
            "valores_tabla": (
                self._formatear_fecha(fila[4]),
                cliente,
                tipo,
                punto_venta,
                numero,
                self._formatear_moneda(fila[7]),
                cae,
                estado,
            ),
            "texto_busqueda": " ".join(
                [
                    cliente,
                    punto_venta,
                    numero,
                    cae,
                    tipo,
                    estado,
                ]
            ).lower(),
            "clase_estado": clase_estado,
            "orden": {
                "fecha": self._clave_fecha(fila[4]),
                "cliente": cliente.lower(),
                "tipo": tipo.lower(),
                "punto_venta": self._clave_entero(fila[5]),
                "numero": self._clave_numero_factura(fila[9]),
                "total": self._clave_float(fila[7]),
                "estado": estado.lower(),
            },
        }

    def _on_busqueda_cambiada(self, *_):
        self._aplicar_filtro()

    def _aplicar_filtro(self):
        termino = self._busqueda_var.get().strip().lower()
        estado_filtro = self._estado_var.get().strip()
        facturas_filtradas = []

        for factura in self._facturas_en_memoria:
            coincide_busqueda = not termino or termino in factura["texto_busqueda"]
            coincide_estado = (
                estado_filtro == "Todos" or factura["clase_estado"] == estado_filtro
            )
            if coincide_busqueda and coincide_estado:
                facturas_filtradas.append(factura)

        facturas_filtradas = self._ordenar_facturas(facturas_filtradas)

        self._renderizar_facturas(facturas_filtradas)

    def _on_ordenar_columna(self, columna):
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
            self.tabla.insert(
                "",
                "end",
                iid=str(factura["factura_id"]),
                values=factura["valores_tabla"],
            )

    def _abrir_pdf_desde_doble_clic(self, _event=None):
        seleccion = self.tabla.selection()
        if not seleccion:
            return

        try:
            factura_id = int(seleccion[0])
        except (TypeError, ValueError):
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar la factura seleccionada.",
                parent=self,
            )
            return

        factura = self._facturas_por_id.get(factura_id)
        if not factura:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se encontró la información de la factura seleccionada.",
                parent=self,
            )
            return

        emisor_fiscal = self._resolver_emisor_fiscal_desde_factura(factura.get("emisor_id"))
        if not emisor_fiscal:
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se pudo identificar el emisor fiscal para esta factura.",
                parent=self,
            )
            return

        carpeta_facturas = str(emisor_fiscal[13] if len(emisor_fiscal) > 13 else "" or "").strip()
        if not carpeta_facturas:
            messagebox.showwarning(
                "Facturas electrónicas",
                "El emisor fiscal no tiene configurada la carpeta de facturas.",
                parent=self,
            )
            return

        cliente_id = factura.get("cliente_id")
        tipo_factura = str(factura.get("tipo_factura") or "").strip() or str(
            emisor_fiscal[5] if len(emisor_fiscal) > 5 else "" or ""
        ).strip()
        codigo_factura = self._reconstruir_codigo_factura(
            factura.get("numero_factura_raw"),
            factura.get("punto_venta_raw"),
        )

        if not cliente_id or not tipo_factura or not codigo_factura:
            messagebox.showwarning(
                "Facturas electrónicas",
                "Faltan datos para ubicar el PDF asociado a esta factura.",
                parent=self,
            )
            return

        nombre_pdf = nombre_factura_pdf(cliente_id, tipo_factura, codigo_factura)
        ruta_pdf = Path(carpeta_facturas) / nombre_pdf
        if not ruta_pdf.is_file():
            messagebox.showwarning(
                "Facturas electrónicas",
                "No se encontró el PDF asociado a esta factura.",
                parent=self,
            )
            return

        try:
            os.startfile(str(ruta_pdf))
        except OSError as error:
            messagebox.showwarning(
                "Facturas electrónicas",
                f"No se pudo abrir el PDF asociado a esta factura.\n\n{error}",
                parent=self,
            )

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

        callbacks = {}
        ficha = FichaClienteFrame(ventana, cliente_data=cliente_id, callbacks=callbacks)
        ficha.pack(fill="both", expand=True)

        try:
            if ventana.state() == "iconic":
                ventana.deiconify()
        except TclError:
            pass
        ventana.lift()
        ventana.focus_force()

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