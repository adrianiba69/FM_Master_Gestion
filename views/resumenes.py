import os
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from pdf.resumen_pdf import ResumenPDF
from runtime_paths import PDF_DIR
from services.cliente_service import ClienteService
from services.resumen_service import ResumenService
from services.whatsapp_service import WhatsAppService


class ResumenesFrame(ctk.CTkFrame):

    def __init__(self, master, cliente_id=None, on_cambio=None):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.clientes_por_nombre = {}
        self.cliente_inicial = cliente_id
        self.on_cambio = on_cambio
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
            height=38,
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

        self.boton_pendientes = ctk.CTkButton(
            barra,
            text="Generar resúmenes pendientes",
            width=205,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_resumenes_pendientes,
        )
        self.boton_pendientes.grid(row=0, column=1, padx=(10, 0))

        boton_abrir = ctk.CTkButton(
            barra,
            text="Abrir PDF",
            width=115,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.abrir_pdf_seleccionado,
        )
        boton_abrir.grid(row=0, column=2, padx=(10, 0))

        self.boton_whatsapp = ctk.CTkButton(
            barra,
            text="Enviar por WhatsApp",
            width=165,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.enviar_whatsapp_seleccionado,
        )
        self.boton_whatsapp.grid(row=0, column=3, padx=(10, 0))

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
        if callable(self.on_cambio):
            self.on_cambio()
        self.mostrar_modal_resumen_generado(ruta)

    def abrir_resumenes_pendientes(self):
        pendientes = ResumenService.listar_pendientes()
        if not pendientes:
            messagebox.showinfo(
                "Resúmenes pendientes",
                "No hay resúmenes pendientes para generar.",
                parent=self,
            )
            return

        ventana = ctk.CTkToplevel(self)
        self.ventana_pendientes = ventana
        ventana.title("Generar resúmenes pendientes")
        ventana.geometry("950x560")
        ventana.minsize(820, 500)
        ventana.configure(fg_color="white")
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()
        ventana.grid_rowconfigure(2, weight=1)
        ventana.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            ventana,
            text="RESÚMENES PENDIENTES",
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        seleccion = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        seleccion.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        ctk.CTkButton(
            seleccion,
            text="Seleccionar todos",
            width=135,
            height=36,
            fg_color="#444444",
            hover_color="#222222",
            command=lambda: self.tabla_pendientes.selection_set(
                self.tabla_pendientes.get_children()
            ),
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            seleccion,
            text="Deseleccionar todos",
            width=145,
            height=36,
            fg_color="#666666",
            hover_color="#444444",
            command=lambda: self.tabla_pendientes.selection_remove(
                self.tabla_pendientes.get_children()
            ),
        ).grid(row=0, column=1)

        tabla_frame = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20)
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)
        columnas = ("cliente", "servicios", "inicio", "fin", "total")
        self.tabla_pendientes = ttk.Treeview(
            tabla_frame,
            columns=columnas,
            show="headings",
            selectmode="extended",
            height=14,
        )
        encabezados = {
            "cliente": ("Cliente", 220),
            "servicios": ("Servicios incluidos", 330),
            "inicio": ("Fecha inicio", 105),
            "fin": ("Fecha fin", 105),
            "total": ("Total", 115),
        }
        for columna, (texto, ancho) in encabezados.items():
            self.tabla_pendientes.heading(columna, text=texto)
            self.tabla_pendientes.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna in ("cliente", "servicios"),
            )
        for pendiente in pendientes:
            conceptos = ", ".join(
                servicio["concepto"] for servicio in pendiente["servicios"]
            )
            self.tabla_pendientes.insert(
                "",
                "end",
                iid=str(pendiente["cliente_id"]),
                values=(
                    pendiente["cliente"],
                    conceptos,
                    self.formatear_fecha(pendiente["fecha_inicio"]),
                    self.formatear_fecha(pendiente["fecha_fin"]),
                    self.formatear_moneda(pendiente["total"]),
                ),
            )
        scroll = ttk.Scrollbar(
            tabla_frame,
            orient="vertical",
            command=self.tabla_pendientes.yview,
        )
        self.tabla_pendientes.configure(yscrollcommand=scroll.set)
        self.tabla_pendientes.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabla_pendientes.selection_set(self.tabla_pendientes.get_children())

        botones = ctk.CTkFrame(ventana, fg_color="white", corner_radius=0)
        botones.grid(row=3, column=0, sticky="e", padx=20, pady=18)
        self.boton_confirmar_pendientes = ctk.CTkButton(
            botones,
            text="Generar seleccionados",
            width=170,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.generar_pendientes_seleccionados,
        )
        self.boton_confirmar_pendientes.grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            botones,
            text="Cancelar",
            width=105,
            height=38,
            fg_color="#666666",
            hover_color="#444444",
            command=ventana.destroy,
        ).grid(row=0, column=1)

    def generar_pendientes_seleccionados(self):
        seleccion = self.tabla_pendientes.selection()
        if not seleccion:
            messagebox.showwarning(
                "Resúmenes pendientes",
                "Seleccione al menos un cliente.",
                parent=self.ventana_pendientes,
            )
            return

        generados = 0
        omitidos = 0
        errores = []
        carpeta = PDF_DIR / "resumenes" / date.today().strftime("%Y-%m")
        for item in seleccion:
            cliente_id = int(item)
            try:
                resumen = ResumenService.generar_pendiente_cliente(cliente_id)
                if resumen is None:
                    omitidos += 1
                    continue
                ruta = carpeta / f"resumen_{resumen.numero:06d}.pdf"
                ResumenPDF.generar(resumen.id, ruta)
                generados += 1
            except Exception as error:
                if "resumen" in locals() and resumen is not None:
                    ResumenService.eliminar_generacion(resumen.id)
                errores.append(str(error))
            finally:
                resumen = None

        self.ventana_pendientes.destroy()
        self.cargar_resumenes()
        messagebox.showinfo(
            "Resultado de generación",
            f"Generados: {generados}\n"
            f"Omitidos: {omitidos}\n"
            f"Errores: {len(errores)}",
            parent=self,
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

    def enviar_whatsapp_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Atencion", "Seleccione un resumen para enviar.")
            return

        valores = self.tabla.item(seleccion[0], "values")
        resumen_id = int(valores[0])
        try:
            datos = WhatsAppService.abrir_whatsapp_resumen(resumen_id)
        except (ValueError, OSError) as error:
            messagebox.showerror("WhatsApp", str(error), parent=self)
            return

        messagebox.showinfo(
            "WhatsApp Web",
            "WhatsApp se abrió con el mensaje preparado. "
            "Adjuntá manualmente el PDF que se abrió en la carpeta.",
            parent=self,
        )

    def mostrar_modal_resumen_generado(self, ruta_pdf):
        modal = ctk.CTkToplevel(self)
        modal.title("Resumen generado")
        modal.geometry("440x220")
        modal.resizable(False, False)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()
        modal.configure(fg_color="white")

        contenedor = ctk.CTkFrame(modal, fg_color="white", corner_radius=0)
        contenedor.pack(fill="both", expand=True, padx=20, pady=20)
        contenedor.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            contenedor,
            text="Resumen generado correctamente",
            font=("Arial", 18, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 18))

        ctk.CTkButton(
            contenedor,
            text="Ver PDF",
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.abrir_pdf_generado(ruta_pdf),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            contenedor,
            text="Enviar por WhatsApp",
            height=36,
            fg_color="#333333",
            hover_color="#111111",
            command=self.mostrar_aviso_whatsapp_pendiente,
        ).grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkButton(
            contenedor,
            text="Cerrar",
            height=36,
            fg_color="#666666",
            hover_color="#444444",
            command=modal.destroy,
        ).grid(row=3, column=0, sticky="ew")

    def abrir_pdf_generado(self, ruta_pdf):
        try:
            os.startfile(str(Path(ruta_pdf).resolve()))
        except (OSError, ValueError) as error:
            messagebox.showerror("Error", f"No se pudo abrir el PDF: {error}", parent=self)

    def mostrar_aviso_whatsapp_pendiente(self):
        messagebox.showinfo(
            "WhatsApp",
            "La integración de envío por WhatsApp se agregará en el próximo paso.",
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
