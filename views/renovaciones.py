from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from pdf.resumen_pdf import ResumenPDF
from runtime_paths import PDF_DIR
from services.resumen_service import ResumenService
from services.servicio_service import ServicioService


class RenovacionesFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.seleccionados = set()
        self.renovaciones_ids = set()
        self.crear_interfaz()
        self.cargar_servicios()

    def crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="RENOVACIONES",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 8))

        self.resumen_label = ctk.CTkLabel(
            self,
            text="",
            font=("Arial", 13, "bold"),
            text_color="#333333",
        )
        self.resumen_label.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        acciones.grid_columnconfigure(5, weight=1)

        ctk.CTkButton(
            acciones,
            text="Seleccionar todos",
            width=135,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.seleccionar_todos,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            acciones,
            text="Deseleccionar todos",
            width=145,
            height=38,
            fg_color="#666666",
            hover_color="#444444",
            command=self.deseleccionar_todos,
        ).grid(row=0, column=1, padx=8)
        self.boton_renovar = ctk.CTkButton(
            acciones,
            text="Renovar seleccionados",
            width=165,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.renovar_seleccionados,
        )
        self.boton_renovar.grid(row=0, column=2, padx=8)
        self.boton_generar = ctk.CTkButton(
            acciones,
            text="Generar resúmenes de los renovados",
            width=245,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.generar_resumenes_renovados,
        )
        self.boton_generar.grid(row=0, column=3, padx=8)

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = (
            "seleccion", "cliente", "concepto", "inicio", "fin",
            "importe", "estado",
        )
        self.tabla = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            selectmode="none",
            height=18,
        )
        encabezados = {
            "seleccion": ("Sel.", 55),
            "cliente": ("Cliente", 230),
            "concepto": ("Concepto", 220),
            "inicio": ("Fecha inicio", 105),
            "fin": ("Fecha fin", 105),
            "importe": ("Importe", 115),
            "estado": ("Estado", 100),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                anchor="center" if columna != "cliente" and columna != "concepto" else "w",
                stretch=columna in ("cliente", "concepto"),
            )
        self.tabla.tag_configure("vencido", foreground="#C00000")
        self.tabla.tag_configure("proximo", foreground="#9A6A00")
        self.tabla.tag_configure("renovado", foreground="#138A43")
        self.tabla.bind("<ButtonRelease-1>", self.alternar_seleccion_fila)
        scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def cargar_servicios(self):
        self.seleccionados.clear()
        for item in self.tabla.get_children():
            self.tabla.delete(item)

        servicios = ServicioService.listar_para_renovacion()
        for servicio in servicios:
            estado = servicio["estado"]
            if estado == "Vencido":
                tag = "vencido"
            elif estado == "Renovado":
                tag = "renovado"
            else:
                tag = "proximo"
            self.tabla.insert(
                "",
                "end",
                iid=str(servicio["id"]),
                values=(
                    "☐", servicio["cliente"], servicio["concepto"],
                    self.formatear_fecha(servicio["fecha_inicio"]),
                    self.formatear_fecha(servicio["fecha_fin"]),
                    self.formatear_moneda(servicio["importe"]), estado,
                ),
                tags=(tag,),
            )
        self.actualizar_resumen()

    def alternar_seleccion_fila(self, evento):
        item = self.tabla.identify_row(evento.y)
        if not item:
            return
        servicio_id = int(item)
        if servicio_id in self.seleccionados:
            self.seleccionados.remove(servicio_id)
        else:
            self.seleccionados.add(servicio_id)
        self.actualizar_marca(item)
        self.actualizar_resumen()

    def seleccionar_todos(self):
        self.seleccionados = {int(item) for item in self.tabla.get_children()}
        for item in self.tabla.get_children():
            self.actualizar_marca(item)
        self.actualizar_resumen()

    def deseleccionar_todos(self):
        self.seleccionados.clear()
        for item in self.tabla.get_children():
            self.actualizar_marca(item)
        self.actualizar_resumen()

    def actualizar_marca(self, item):
        valores = list(self.tabla.item(item, "values"))
        valores[0] = "☑" if int(item) in self.seleccionados else "☐"
        self.tabla.item(item, values=valores)

    def actualizar_resumen(self):
        total = len(self.tabla.get_children())
        self.resumen_label.configure(
            text=f"Servicios disponibles: {total}  |  Seleccionados: {len(self.seleccionados)}"
        )

    def renovar_seleccionados(self):
        if not self.seleccionados:
            messagebox.showwarning("Renovaciones", "Seleccione al menos un servicio.")
            return
        resultado = ServicioService.renovar_periodos(sorted(self.seleccionados))
        self.renovaciones_ids.update(
            renovacion["renovacion_id"] for renovacion in resultado["renovados"]
        )
        self.cargar_servicios()
        messagebox.showinfo(
            "Renovaciones",
            f"Renovados: {len(resultado['renovados'])}\n"
            f"Omitidos: {resultado['omitidos']}\n"
            f"Errores: {len(resultado['errores'])}",
            parent=self,
        )

    def generar_resumenes_renovados(self):
        if not self.renovaciones_ids:
            messagebox.showwarning(
                "Resúmenes",
                "No hay renovaciones pendientes de generar en esta sesión.",
                parent=self,
            )
            return

        resultado = ResumenService.generar_desde_renovaciones(
            sorted(self.renovaciones_ids)
        )
        generados = 0
        errores = list(resultado["errores"])
        carpeta = PDF_DIR / "resumenes" / date.today().strftime("%Y-%m")
        for resumen in resultado["generados"]:
            try:
                ruta = carpeta / f"resumen_{resumen.numero:06d}.pdf"
                ResumenPDF.generar(resumen.id, ruta)
                generados += 1
            except Exception as error:
                ResumenService.eliminar_generacion(resumen.id)
                errores.append(str(error))

        messagebox.showinfo(
            "Resultado de resúmenes",
            f"Generados: {generados}\n"
            f"Omitidos: {resultado['omitidos']}\n"
            f"Errores: {len(errores)}",
            parent=self,
        )

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
