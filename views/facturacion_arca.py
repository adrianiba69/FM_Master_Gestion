import os
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from services.cliente_service import ClienteService
from services.emisor_fiscal_service import EmisorFiscalService
from services.emisor_service import EmisorService
from services.factura_arca_service import FacturaArcaService
from services.resumen_service import ResumenService
from services.arca.homologacion_service import HomologacionService
from models.factura_arca import FacturaArca


class FacturacionArcaFrame(ctk.CTkFrame):

    ESTADOS = ["Pendiente", "Facturada manualmente", "Anulada"]

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.clientes = {}
        self.emisores = {}
        self.crear_interfaz()
        self.cargar_filtros()
        self.cargar_facturas()

    def crear_interfaz(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text="FACTURACIÓN ARCA",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        filtros = ctk.CTkFrame(self, fg_color="#F4F4F4", corner_radius=6)
        filtros.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 14))
        filtros.grid_columnconfigure(0, weight=1)
        filtros.grid_columnconfigure(1, weight=1)
        filtros.grid_columnconfigure(2, weight=1)
        filtros.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(filtros, text="Cliente").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(filtros, text="Emisor").grid(row=0, column=1, sticky="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(filtros, text="Estado").grid(row=0, column=2, sticky="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(filtros, text="Resumen").grid(row=0, column=3, sticky="w", padx=14, pady=(12, 4))

        self.selector_cliente = ctk.CTkComboBox(filtros, values=[""], width=240)
        self.selector_cliente.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")
        self.selector_cliente.set("")
        self.selector_cliente.bind("<<ComboboxSelected>>", lambda _e: self.actualizar_facturas())

        self.selector_emisor = ctk.CTkComboBox(filtros, values=[""], width=240)
        self.selector_emisor.grid(row=1, column=1, padx=14, pady=(0, 12), sticky="ew")
        self.selector_emisor.set("")
        self.selector_emisor.bind("<<ComboboxSelected>>", lambda _e: self.actualizar_facturas())

        self.selector_estado = ctk.CTkComboBox(filtros, values=["", *self.ESTADOS], width=240)
        self.selector_estado.grid(row=1, column=2, padx=14, pady=(0, 12), sticky="ew")
        self.selector_estado.set("")
        self.selector_estado.bind("<<ComboboxSelected>>", lambda _e: self.actualizar_facturas())

        self.selector_resumen = ctk.CTkComboBox(filtros, values=[""], width=240)
        self.selector_resumen.grid(row=1, column=3, padx=14, pady=(0, 12), sticky="ew")
        self.selector_resumen.set("")
        self.selector_resumen.bind("<<ComboboxSelected>>", lambda _e: self.actualizar_facturas())

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        acciones.grid_columnconfigure(5, weight=1)

        ctk.CTkButton(
            acciones,
            text="Crear factura pendiente",
            width=190,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.crear_factura_pendiente,
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            acciones,
            text="Editar seleccionada",
            width=170,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.editar_factura,
        ).grid(row=0, column=1, padx=8)

        ctk.CTkButton(
            acciones,
            text="Marcar facturada",
            width=150,
            height=38,
            fg_color="#007A00",
            hover_color="#005500",
            command=lambda: self.cambiar_estado_seleccion("Facturada manualmente"),
        ).grid(row=0, column=2, padx=8)

        ctk.CTkButton(
            acciones,
            text="Marcar anulada",
            width=130,
            height=38,
            fg_color="#7A0000",
            hover_color="#550000",
            command=lambda: self.cambiar_estado_seleccion("Anulada"),
        ).grid(row=0, column=3, padx=8)

        ctk.CTkButton(
            acciones,
            text="Consultar último comprobante",
            width=220,
            height=38,
            fg_color="#2E5A88",
            hover_color="#23476C",
            command=self.consultar_ultimo_comprobante,
        ).grid(row=0, column=4, padx=8)

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = (
            "id",
            "cliente",
            "emisor",
            "resumen",
            "fecha",
            "punto_venta",
            "tipo_comprobante",
            "importe_total",
            "estado",
            "numero_factura",
            "cae",
            "vencimiento_cae",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=16)
        encabezados = {
            "id": ("ID", 40),
            "cliente": ("Cliente", 220),
            "emisor": ("Emisor", 180),
            "resumen": ("Resumen", 90),
            "fecha": ("Fecha", 95),
            "punto_venta": ("Punto venta", 90),
            "tipo_comprobante": ("Tipo", 120),
            "importe_total": ("Importe", 110),
            "estado": ("Estado", 140),
            "numero_factura": ("Factura", 100),
            "cae": ("CAE", 110),
            "vencimiento_cae": ("Vence CAE", 105),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(columna, width=ancho, anchor="w")

        self.tabla.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview).grid(row=0, column=1, sticky="ns")

    def cargar_filtros(self):
        self.clientes = {"": None}
        for fila in ClienteService.listar():
            self.clientes[f"{fila[1] or '-'} - {fila[2]}"] = fila[0]
        self.selector_cliente.configure(values=list(self.clientes.keys()))

        self.emisores = {"": None}
        for fila in EmisorFiscalService.listar():
            etiqueta = self._etiqueta_emisor_para_filtro(fila)
            self.emisores[etiqueta] = fila[0]
        self.selector_emisor.configure(values=list(self.emisores.keys()))

        self.resumenes = {"": None}
        resumenes = [""]
        for fila in ResumenService.listar():
            etiqueta = f"{fila[0]} - {fila[1]:06d}"
            self.resumenes[etiqueta] = fila[0]
            resumenes.append(etiqueta)
        self.selector_resumen.configure(values=resumenes)

    @staticmethod
    def _etiqueta_emisor_para_filtro(emisor):
        # Estructura EmisorFiscalService.listar: id, razon_social, nombre_fantasia, cuit, ...
        nombre_comercial = str(emisor[2] if len(emisor) > 2 else "" or "").strip()
        razon_social = str(emisor[1] if len(emisor) > 1 else "" or "").strip()
        cuit = str(emisor[3] if len(emisor) > 3 else "" or "").strip()

        nombre_visible = nombre_comercial or razon_social or f"Emisor {emisor[0]}"
        cuit_visible = cuit or "CUIT sin informar"
        return f"{nombre_visible} - {cuit_visible}"

    def cargar_facturas(self):
        self.tabla.delete(*self.tabla.get_children())
        estado = self.selector_estado.get().strip() or None
        cliente_id = self.clientes.get(self.selector_cliente.get())
        emisor_id = self.emisores.get(self.selector_emisor.get())
        resumen_id = None
        resumen_texto = self.selector_resumen.get().strip()
        if resumen_texto:
            resumen_id = self.resumenes.get(resumen_texto)

        for fila in FacturaArcaService.listar(estado=estado):
            if cliente_id and fila[1] != cliente_id:
                continue
            if emisor_id and fila[2] != emisor_id:
                continue
            if resumen_id and fila[3] != resumen_id:
                continue
            cliente = ClienteService.obtener(fila[1])
            emisor = EmisorFiscalService.obtener(fila[2])
            resumen = ResumenService.obtener(fila[3])
            self.tabla.insert("", "end", values=(
                fila[0],
                cliente[2] if cliente else "",
                self._etiqueta_emisor_para_filtro(emisor) if emisor else f"Emisor fiscal #{fila[2]}",
                f"{resumen.numero:06d}" if resumen else "",
                self.formatear_fecha(fila[4]),
                fila[5],
                fila[6],
                self.formatear_moneda(fila[7]),
                fila[8],
                fila[9] or "",
                fila[10] or "",
                self.formatear_fecha(fila[11]) if fila[11] else "",
            ))

    def actualizar_facturas(self):
        self.cargar_facturas()

    def consultar_ultimo_comprobante(self):
        emisor_id = self.emisores.get(self.selector_emisor.get())
        if not emisor_id:
            messagebox.showwarning(
                "Facturación ARCA",
                "Seleccione un emisor para consultar el último comprobante.",
                parent=self,
            )
            return

        emisor = EmisorFiscalService.obtener(emisor_id)
        if not emisor:
            messagebox.showerror(
                "Facturación ARCA",
                "No se encontró el emisor seleccionado.",
                parent=self,
            )
            return

        nombre_emisor = EmisorFiscalService.etiqueta_visible(emisor)
        cuit = str(emisor[3] if len(emisor) > 3 else "" or "").strip()
        punto_venta = str(emisor[6] if len(emisor) > 6 else "" or "").strip()
        tipo_factura = str(emisor[5] if len(emisor) > 5 else "" or "").strip()
        ruta_certificado = str(emisor[11] if len(emisor) > 11 else "" or "").strip()
        ruta_clave = str(emisor[12] if len(emisor) > 12 else "" or "").strip()
        carpeta_facturas = str(emisor[13] if len(emisor) > 13 else "" or "").strip()

        tipo_comprobante = self._tipo_comprobante_desde_tipo_factura(tipo_factura)
        if tipo_comprobante is None:
            messagebox.showerror(
                "Facturación ARCA",
                "No se pudo determinar el tipo de comprobante para el emisor seleccionado.",
                parent=self,
            )
            return

        resultado = HomologacionService.consultar_ultimo_comprobante(
            ruta_certificado=ruta_certificado,
            ruta_clave=ruta_clave,
            cuit=cuit,
            punto_venta=punto_venta,
            tipo_comprobante=tipo_comprobante,
            carpeta_trabajo=carpeta_facturas,
        )

        if not resultado.get("ok"):
            errores = list(resultado.get("errores") or [])
            detalle = "\n- ".join(errores) if errores else "Error desconocido al consultar ARCA."
            messagebox.showerror(
                "Facturación ARCA",
                "No se pudo consultar el último comprobante autorizado.\n\n- " + detalle,
                parent=self,
            )
            return

        ultimo_numero = int(resultado.get("ultimo_numero") or 0)
        messagebox.showinfo(
            "Facturación ARCA",
            (
                "Último comprobante autorizado:\n"
                f"{tipo_factura or 'Comprobante'}\n"
                f"Emisor: {nombre_emisor}\n"
                f"Punto de venta {int(punto_venta or 0):05d}\n"
                f"Número {ultimo_numero:08d}"
            ),
            parent=self,
        )

    @staticmethod
    def _tipo_comprobante_desde_tipo_factura(tipo_factura):
        texto = str(tipo_factura or "").strip().upper()
        if texto == "FACTURA C":
            return 11
        if texto == "FACTURA A":
            return 1
        return None

    def crear_factura_pendiente(self):
        resumen_texto = self.selector_resumen.get().strip()
        if not resumen_texto:
            messagebox.showwarning("Atencion", "Seleccione un resumen para crear la factura.", parent=self)
            return
        resumen_id = self.resumenes.get(resumen_texto)
        if not resumen_id:
            messagebox.showerror("Error", "Resumen invalido seleccionado.", parent=self)
            return

        resumen = ResumenService.obtener(resumen_id)
        if not resumen:
            messagebox.showerror("Error", "No se encontro el resumen seleccionado.", parent=self)
            return

        cliente = ClienteService.obtener(resumen.cliente_id)
        if not cliente:
            messagebox.showerror("Error", "No se encontro el cliente asociado.", parent=self)
            return

        emisor_id = cliente[12]
        emisor_recomendado_id = cliente[13]
        iva_cliente = cliente[11] or ""

        if emisor_recomendado_id:
            emisor_id = emisor_recomendado_id

        if emisor_id is None:
            messagebox.showwarning("Atencion", "El cliente no tiene un emisor asignado.", parent=self)
            return

        emisor = EmisorService.obtener(emisor_id)
        if "responsable" in iva_cliente.lower() and EmisorService.es_emisor_monotributo(emisor):
            respuesta = messagebox.askyesno(
                "Atencion",
                "El cliente es Responsable Inscripto, pero el emisor seleccionado parece ser Monotributo. Desea continuar?",
                parent=self
            )
            if not respuesta:
                return

        factura = FacturaArca(
            cliente_id=cliente[0],
            emisor_id=emisor_id,
            resumen_id=resumen.id,
            fecha=date.today().isoformat(),
            punto_venta=emisor[6] if emisor else "",
            tipo_comprobante=emisor[7] if emisor else "",
            importe_total=resumen.total,
            estado="Pendiente",
            fecha_creacion=datetime.now().isoformat(timespec="seconds"),
        )
        FacturaArcaService.guardar(factura)
        self.cargar_facturas()
        messagebox.showinfo("Factura ARCA", "Factura pendiente creada correctamente.", parent=self)

    def editar_factura(self):
        seleccion = self.obtener_factura_seleccionada()
        if seleccion is None:
            messagebox.showwarning("Atencion", "Seleccione una factura para editar.", parent=self)
            return
        factura = FacturaArcaService.obtener(seleccion)
        if not factura:
            messagebox.showerror("Error", "No se encontro la factura seleccionada.", parent=self)
            return

        FacturaArcaEditor(self, factura, self.cargar_facturas)

    def cambiar_estado_seleccion(self, estado):
        seleccion = self.obtener_factura_seleccionada()
        if seleccion is None:
            messagebox.showwarning("Atencion", "Seleccione una factura.", parent=self)
            return
        factura = FacturaArcaService.obtener(seleccion)
        if not factura:
            messagebox.showerror("Error", "No se encontro la factura seleccionada.", parent=self)
            return
        factura_obj = FacturaArca(
            id=factura[0],
            cliente_id=factura[1],
            emisor_id=factura[2],
            resumen_id=factura[3],
            fecha=factura[4],
            punto_venta=factura[5] or "",
            tipo_comprobante=factura[6] or "",
            importe_total=factura[7] or 0,
            estado=estado,
            numero_factura=factura[9] or "",
            cae=factura[10] or "",
            vencimiento_cae=factura[11] or "",
            observaciones=factura[12] or "",
        )
        FacturaArcaService.actualizar(factura_obj)
        self.cargar_facturas()

    def obtener_factura_seleccionada(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None
        valores = self.tabla.item(seleccion[0], "values")
        return int(valores[0]) if valores else None

    def obtener_resumen_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None
        valores = self.tabla.item(seleccion[0], "values")
        return int(valores[3]) if valores and valores[3] else None

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def formatear_moneda(valor):
        try:
            numero = f"{float(valor or 0):,.2f}"
            return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return "$ 0,00"


class FacturaArcaEditor(ctk.CTkToplevel):

    def __init__(self, master, factura, on_guardar=None):
        super().__init__(master)
        self.factura = factura
        self.on_guardar = on_guardar
        self.title("Editar Factura ARCA")
        self.geometry("620x620")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.crear_interfaz()
        self.cargar()

    def crear_interfaz(self):
        contenedor = ctk.CTkScrollableFrame(self, fg_color="white")
        contenedor.pack(fill="both", expand=True, padx=16, pady=16)

        self.cliente_label = ctk.CTkLabel(contenedor, text="Cliente:")
        self.cliente_label.pack(anchor="w", pady=(0, 6))

        self.emisor_label = ctk.CTkLabel(contenedor, text="Emisor:")
        self.emisor_label.pack(anchor="w", pady=(0, 6))

        ctk.CTkLabel(contenedor, text="Fecha").pack(anchor="w", pady=(8, 0))
        self.fecha = ctk.CTkEntry(contenedor)
        self.fecha.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Punto de venta").pack(anchor="w", pady=(8, 0))
        self.punto_venta = ctk.CTkEntry(contenedor)
        self.punto_venta.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Tipo de comprobante").pack(anchor="w", pady=(8, 0))
        self.tipo_comprobante = ctk.CTkEntry(contenedor)
        self.tipo_comprobante.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Importe total").pack(anchor="w", pady=(8, 0))
        self.importe_total = ctk.CTkEntry(contenedor)
        self.importe_total.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Estado").pack(anchor="w", pady=(8, 0))
        self.estado = ctk.CTkComboBox(contenedor, values=self.ESTADOS)
        self.estado.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Número de factura").pack(anchor="w", pady=(8, 0))
        self.numero_factura = ctk.CTkEntry(contenedor)
        self.numero_factura.pack(fill="x")

        ctk.CTkLabel(contenedor, text="CAE").pack(anchor="w", pady=(8, 0))
        self.cae = ctk.CTkEntry(contenedor)
        self.cae.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Vencimiento CAE").pack(anchor="w", pady=(8, 0))
        self.vencimiento_cae = ctk.CTkEntry(contenedor)
        self.vencimiento_cae.pack(fill="x")

        ctk.CTkLabel(contenedor, text="Observaciones").pack(anchor="w", pady=(8, 0))
        self.observaciones = ctk.CTkTextbox(contenedor, height=120)
        self.observaciones.pack(fill="x")

        botones = ctk.CTkFrame(contenedor, fg_color="white")
        botones.pack(fill="x", pady=16)
        ctk.CTkButton(botones, text="Guardar", fg_color="#C00000", command=self.guardar).pack(side="right")

    def cargar(self):
        cliente = ClienteService.obtener(self.factura[1])
        emisor = EmisorService.obtener(self.factura[2])
        self.cliente_label.configure(text=f"Cliente: {cliente[2] if cliente else ''}")
        self.emisor_label.configure(text=f"Emisor: {emisor[1] if emisor else ''}")
        self.fecha.insert(0, self.factura[4] or date.today().isoformat())
        self.punto_venta.insert(0, self.factura[5] or "")
        self.tipo_comprobante.insert(0, self.factura[6] or "")
        self.importe_total.insert(0, str(self.factura[7] or 0))
        self.estado.set(self.factura[8] or "Pendiente")
        self.numero_factura.insert(0, self.factura[9] or "")
        self.cae.insert(0, self.factura[10] or "")
        self.vencimiento_cae.insert(0, self.factura[11] or "")
        self.observaciones.insert("0.0", self.factura[12] or "")

    def guardar(self):
        try:
            importe_total = float(self.importe_total.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Importe total invalido.", parent=self)
            return

        factura_obj = FacturaArca(
            id=self.factura[0],
            cliente_id=self.factura[1],
            emisor_id=self.factura[2],
            resumen_id=self.factura[3],
            fecha=self.fecha.get().strip() or date.today().isoformat(),
            punto_venta=self.punto_venta.get().strip(),
            tipo_comprobante=self.tipo_comprobante.get().strip(),
            importe_total=importe_total,
            estado=self.estado.get().strip() or "Pendiente",
            numero_factura=self.numero_factura.get().strip(),
            cae=self.cae.get().strip(),
            vencimiento_cae=self.vencimiento_cae.get().strip(),
            observaciones=self.observaciones.get("0.0", "end").strip(),
        )
        FacturaArcaService.actualizar(factura_obj)
        if self.on_guardar:
            self.on_guardar()
        self.destroy()
