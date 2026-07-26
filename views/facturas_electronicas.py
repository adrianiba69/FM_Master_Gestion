from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

from config import COLOR_PRINCIPAL
from database import conectar
from services.factura_arca_service import FacturaArcaService


class FacturasElectronicasFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._cache_clientes = {}
        self.crear_interfaz()
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

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
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
        self.tabla.delete(*self.tabla.get_children())
        filas = FacturaArcaService.listar()

        if not filas:
            self.mensaje_vacio.grid(row=0, column=0)
            return

        self.mensaje_vacio.grid_remove()
        for fila in filas:
            self.tabla.insert(
                "",
                "end",
                values=(
                    self._formatear_fecha(fila[4]),
                    self._resolver_nombre_cliente(fila[1]),
                    self._formatear_tipo(fila[6]),
                    self._formatear_punto_venta(fila[5]),
                    self._formatear_numero(fila[9]),
                    self._formatear_moneda(fila[7]),
                    str(fila[10] or "").strip(),
                    str(fila[8] or "").strip(),
                ),
            )

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