import os
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from pdf.resumen_pdf import ResumenPDF
from services.cliente_service import ClienteService
from services.resumen_service import ResumenService


class ResumenesFrame(ctk.CTkFrame):

    def __init__(self, master, cliente_id=None):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.clientes_por_nombre = {}
        self.cliente_inicial = cliente_id
        self.crear_interfaz()
        self.cargar_clientes()
        self.cargar_resumenes()

    def crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text="RESUMENES",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        emision = ctk.CTkFrame(self, fg_color="#F4F4F4", corner_radius=4)
        emision.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        emision.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(emision, text="Cliente", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=(14, 8), pady=(10, 0)
        )
        ctk.CTkLabel(emision, text="Fecha", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=8, pady=(10, 0)
        )
        ctk.CTkLabel(emision, text="Vencimiento", anchor="w").grid(
            row=0, column=2, sticky="ew", padx=8, pady=(10, 0)
        )

        self.selector_cliente = ctk.CTkComboBox(
            emision,
            values=[""],
            width=340,
            command=lambda _valor: self.actualizar_vencimiento(),
        )
        self.selector_cliente.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(4, 14))

        hoy = date.today().strftime("%d/%m/%Y")
        self.entrada_fecha = ctk.CTkEntry(emision, width=130)
        self.entrada_fecha.insert(0, hoy)
        self.entrada_fecha.grid(row=1, column=1, padx=8, pady=(4, 14))

        self.entrada_vencimiento = ctk.CTkEntry(emision, width=130)
        self.entrada_vencimiento.insert(0, hoy)
        self.entrada_vencimiento.grid(row=1, column=2, padx=8, pady=(4, 14))

        boton_generar = ctk.CTkButton(
            emision,
            text="Generar PDF",
            width=135,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.generar_resumen,
        )
        boton_generar.grid(row=1, column=3, padx=(10, 14), pady=(4, 14))

        barra = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        barra.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        barra.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            barra,
            text="Historial de resumenes",
            font=("Arial", 16, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w")

        boton_abrir = ctk.CTkButton(
            barra,
            text="Abrir PDF",
            width=115,
            fg_color="#444444",
            hover_color="#222222",
            command=self.abrir_pdf_seleccionado,
        )
        boton_abrir.grid(row=0, column=1, padx=(10, 0))

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = (
            "id", "numero", "fecha", "vencimiento", "cliente",
            "total", "saldo", "estado", "pdf_path",
        )
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=16)
        encabezados = {
            "id": ("ID", 50),
            "numero": ("Resumen", 90),
            "fecha": ("Fecha", 95),
            "vencimiento": ("Vencimiento", 105),
            "cliente": ("Cliente", 260),
            "total": ("Total", 110),
            "saldo": ("Saldo", 110),
            "estado": ("Estado", 100),
            "pdf_path": ("PDF", 0),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                minwidth=0 if columna == "pdf_path" else 40,
                stretch=columna in ("cliente",),
                anchor="w",
            )

        self.tabla.bind("<Double-1>", lambda _evento: self.abrir_pdf_seleccionado())
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def cargar_clientes(self):
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {
            f"{cliente[1] or '-'} - {cliente[2]}": cliente[0]
            for cliente in clientes
        }
        nombres = list(self.clientes_por_nombre)
        self.selector_cliente.configure(values=nombres or [""])

        seleccionado = ""
        if self.cliente_inicial is not None:
            seleccionado = next(
                (nombre for nombre, identificador in self.clientes_por_nombre.items()
                 if identificador == self.cliente_inicial),
                "",
            )
        if not seleccionado and nombres:
            seleccionado = nombres[0]
        self.selector_cliente.set(seleccionado)
        self.actualizar_vencimiento()

    def actualizar_vencimiento(self):
        cliente_id = self.clientes_por_nombre.get(self.selector_cliente.get())
        if cliente_id is None:
            return
        cliente = ClienteService.obtener(cliente_id)
        if cliente is None:
            return
        try:
            emision = datetime.strptime(self.entrada_fecha.get(), "%d/%m/%Y").date()
        except ValueError:
            emision = date.today()
        vencimiento = ResumenService.calcular_vencimiento(cliente, emision)
        self.entrada_vencimiento.delete(0, "end")
        self.entrada_vencimiento.insert(0, vencimiento.strftime("%d/%m/%Y"))

    def cargar_resumenes(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        for fila in ResumenService.listar():
            self.tabla.insert("", "end", values=(
                fila[0],
                f"{fila[1]:06d}",
                self.formatear_fecha(fila[2]),
                self.formatear_fecha(fila[3]),
                fila[4],
                self.formatear_moneda(fila[5]),
                self.formatear_moneda(fila[6]),
                fila[7],
                fila[8] or "",
            ))

    def generar_resumen(self):
        cliente_id = self.clientes_por_nombre.get(self.selector_cliente.get())
        if cliente_id is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente.")
            return

        try:
            fecha = datetime.strptime(self.entrada_fecha.get().strip(), "%d/%m/%Y").date()
            vencimiento = datetime.strptime(
                self.entrada_vencimiento.get().strip(), "%d/%m/%Y"
            ).date()
        except ValueError:
            messagebox.showerror("Error", "Las fechas deben tener formato DD/MM/AAAA.")
            return

        try:
            resumen = ResumenService.generar_desde_servicios(
                cliente_id,
                fecha=fecha,
                fecha_vencimiento=vencimiento,
            )
            ruta = ResumenPDF.generar(resumen.id)
        except (ValueError, OSError) as error:
            messagebox.showerror("No se pudo generar", str(error))
            return
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo generar el resumen: {error}")
            return

        self.cargar_resumenes()
        messagebox.showinfo(
            "Resumen generado",
            f"Resumen Nro. {resumen.numero:06d} generado correctamente.\n{ruta}",
        )

    def abrir_pdf_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atencion", "Seleccione un resumen para abrir.")
            return

        valores = self.tabla.item(seleccion[0], "values")
        resumen_id = int(valores[0])
        ruta = valores[8] if len(valores) > 8 else ""

        try:
            if not ruta or not Path(ruta).exists():
                ruta = ResumenPDF.generar(resumen_id)
                self.cargar_resumenes()
            os.startfile(str(Path(ruta).resolve()))
        except (OSError, ValueError) as error:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {error}")

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
