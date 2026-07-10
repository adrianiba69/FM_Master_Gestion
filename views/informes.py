from datetime import date, datetime
from tkinter import BooleanVar, StringVar, messagebox, ttk

import customtkinter as ctk

from services.cliente_service import ClienteService
from services.informes_service import InformesService


class InformesFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.clientes_por_nombre = {}
        self.datos_actuales = None
        self.crear_interfaz()
        self.cargar_clientes()
        self.actualizar_informe()

    def crear_interfaz(self):
        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="INFORMES",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        filtros = ctk.CTkFrame(self, fg_color="#F3F3F3", corner_radius=4)
        filtros.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        filtros.grid_columnconfigure(0, weight=1)

        etiquetas = ("Informe", "Desde", "Hasta", "Cliente", "Estado")
        for columna, texto in enumerate(etiquetas):
            ctk.CTkLabel(filtros, text=texto, anchor="w").grid(
                row=0,
                column=columna,
                sticky="ew",
                padx=(12 if columna == 0 else 6, 6),
                pady=(9, 0),
            )

        self.selector_informe = ctk.CTkComboBox(
            filtros,
            values=list(InformesService.INFORMES),
            width=260,
            command=self._on_informe_cambiado,
        )
        self.selector_informe.grid(row=1, column=0, sticky="ew", padx=(12, 6), pady=(3, 12))
        self.selector_informe.set(InformesService.INFORMES[0])

        inicio_mes = date.today().replace(day=1).strftime("%d/%m/%Y")
        self.entrada_desde = ctk.CTkEntry(filtros, width=110)
        self.entrada_desde.insert(0, inicio_mes)
        self.entrada_desde.grid(row=1, column=1, padx=6, pady=(3, 12))
        self.entrada_hasta = ctk.CTkEntry(filtros, width=110)
        self.entrada_hasta.insert(0, date.today().strftime("%d/%m/%Y"))
        self.entrada_hasta.grid(row=1, column=2, padx=6, pady=(3, 12))

        self.selector_cliente = ctk.CTkComboBox(
            filtros,
            values=["Todos los clientes"],
            width=220,
        )
        self.selector_cliente.grid(row=1, column=3, padx=6, pady=(3, 12))
        self.selector_cliente.set("Todos los clientes")
        self.selector_estado = ctk.CTkComboBox(
            filtros,
            values=list(InformesService.ESTADOS),
            width=125,
        )
        self.selector_estado.grid(row=1, column=4, padx=(6, 12), pady=(3, 12))
        self.selector_estado.set("Todos")

        self._bloqueo_filtros_agenda = False
        self.var_agenda_todos = BooleanVar(value=True)
        self.var_agenda_activos = BooleanVar(value=False)
        self.var_agenda_telefono = BooleanVar(value=False)
        self.var_agenda_whatsapp = BooleanVar(value=False)
        self.var_agenda_email = BooleanVar(value=False)
        self.orden_agenda = StringVar(value="Razón Social")

        self.filtros_agenda = ctk.CTkFrame(self, fg_color="#F3F3F3", corner_radius=4)
        self.filtros_agenda.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.filtros_agenda.grid_columnconfigure(0, weight=1)
        self.filtros_agenda.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self.filtros_agenda,
            text="Agenda Telefónica de Clientes",
            font=("Arial", 12, "bold"),
            text_color="#C00000",
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 4))

        fila_filtros = ctk.CTkFrame(self.filtros_agenda, fg_color="transparent", corner_radius=0)
        fila_filtros.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(2, 4))
        for indice in range(5):
            fila_filtros.grid_columnconfigure(indice, weight=1)

        self.check_agenda_todos = ctk.CTkCheckBox(
            fila_filtros,
            text="Todos los clientes",
            variable=self.var_agenda_todos,
            command=self._sincronizar_filtros_agenda,
        )
        self.check_agenda_todos.grid(row=0, column=0, sticky="w", padx=6, pady=2)

        self.check_agenda_activos = ctk.CTkCheckBox(
            fila_filtros,
            text="Solo activos",
            variable=self.var_agenda_activos,
            command=self._sincronizar_filtros_agenda,
        )
        self.check_agenda_activos.grid(row=0, column=1, sticky="w", padx=6, pady=2)

        self.check_agenda_telefono = ctk.CTkCheckBox(
            fila_filtros,
            text="Solo con teléfono",
            variable=self.var_agenda_telefono,
            command=self._sincronizar_filtros_agenda,
        )
        self.check_agenda_telefono.grid(row=0, column=2, sticky="w", padx=6, pady=2)

        self.check_agenda_whatsapp = ctk.CTkCheckBox(
            fila_filtros,
            text="Solo con WhatsApp",
            variable=self.var_agenda_whatsapp,
            command=self._sincronizar_filtros_agenda,
        )
        self.check_agenda_whatsapp.grid(row=0, column=3, sticky="w", padx=6, pady=2)

        self.check_agenda_email = ctk.CTkCheckBox(
            fila_filtros,
            text="Solo con Email",
            variable=self.var_agenda_email,
            command=self._sincronizar_filtros_agenda,
        )
        self.check_agenda_email.grid(row=0, column=4, sticky="w", padx=6, pady=2)

        ctk.CTkLabel(
            self.filtros_agenda,
            text="Ordenar por:",
            font=("Arial", 10, "bold"),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=12, pady=(4, 0))
        self.orden_agenda_combo = ctk.CTkComboBox(
            self.filtros_agenda,
            values=["Razón Social", "Nombre Comercial", "Localidad"],
            width=180,
            variable=self.orden_agenda,
        )
        self.orden_agenda_combo.grid(row=2, column=1, sticky="w", padx=12, pady=(4, 8))
        self.filtros_agenda.grid_remove()

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 8))
        acciones.grid_columnconfigure(5, weight=1)
        self.boton_actualizar = ctk.CTkButton(
            acciones,
            text="Actualizar",
            width=115,
            height=38,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.actualizar_informe,
        )
        self.boton_actualizar.grid(row=0, column=0, padx=(0, 8))
        self.boton_imprimir = ctk.CTkButton(
            acciones,
            text="Imprimir",
            width=115,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.imprimir_informe,
        )
        self.boton_imprimir.grid(row=0, column=1, padx=8)
        self.boton_excel = ctk.CTkButton(
            acciones,
            text="Exportar a Excel",
            width=140,
            height=38,
            fg_color="#333333",
            hover_color="#111111",
            command=self.exportar_excel,
        )
        self.boton_excel.grid(row=0, column=2, padx=8)
        self.boton_pdf = ctk.CTkButton(
            acciones,
            text="Exportar a PDF",
            width=135,
            height=38,
            fg_color="#444444",
            hover_color="#222222",
            command=self.exportar_pdf,
        )
        self.boton_pdf.grid(row=0, column=3, padx=8)
        self.boton_cerrar = ctk.CTkButton(
            acciones,
            text="Cerrar",
            width=105,
            height=38,
            fg_color="#555555",
            hover_color="#333333",
            command=self.cerrar_informe,
        )
        self.boton_cerrar.grid(row=0, column=4, padx=8)

        self.resultado_label = ctk.CTkLabel(
            self,
            text="",
            font=("Arial", 12, "bold"),
            text_color="#555555",
        )
        self.resultado_label.grid(row=4, column=0, sticky="w", padx=20, pady=(0, 5))

        self.tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        self.tabla_frame.grid(row=5, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.tabla_frame.grid_rowconfigure(0, weight=1)
        self.tabla_frame.grid_columnconfigure(0, weight=1)
        self.tabla = None
        self.scroll_y = None
        self.scroll_x = None
        self._on_informe_cambiado(self.selector_informe.get())

    def cargar_clientes(self):
        self.clientes_por_nombre = {
            f"{cliente[1] or '-'} - {cliente[2]}": cliente[0]
            for cliente in ClienteService.listar()
        }
        self.selector_cliente.configure(
            values=["Todos los clientes", *self.clientes_por_nombre]
        )

    def actualizar_informe(self):
        try:
            desde = self.obtener_fecha(self.entrada_desde.get())
            hasta = self.obtener_fecha(self.entrada_hasta.get())
            kwargs_agenda = {}
            if self._es_informe_agenda():
                kwargs_agenda = {
                    "agenda_todos": self.var_agenda_todos.get(),
                    "agenda_activos": self.var_agenda_activos.get(),
                    "agenda_telefono": self.var_agenda_telefono.get(),
                    "agenda_whatsapp": self.var_agenda_whatsapp.get(),
                    "agenda_email": self.var_agenda_email.get(),
                    "agenda_orden": self.orden_agenda.get(),
                }
            self.datos_actuales = InformesService.generar(
                self.selector_informe.get(),
                desde,
                hasta,
                self.clientes_por_nombre.get(self.selector_cliente.get()),
                self.selector_estado.get(),
                **kwargs_agenda,
            )
        except ValueError as error:
            messagebox.showerror("Informes", str(error), parent=self)
            return
        self.mostrar_resultados()

    def mostrar_resultados(self):
        if self.tabla is not None:
            self.tabla.destroy()
            self.scroll_y.destroy()
            self.scroll_x.destroy()
        columnas = tuple(f"c{indice}" for indice in range(len(self.datos_actuales["columnas"])))
        self.tabla = ttk.Treeview(
            self.tabla_frame,
            columns=columnas,
            show="headings",
            height=16,
        )
        for indice, (identificador, titulo) in enumerate(zip(columnas, self.datos_actuales["columnas"])):
            self.tabla.heading(identificador, text=titulo)
            anchos_especiales = {
                "Cliente": 180,
                "Concepto": 180,
                "Observaciones": 190,
                "Razón Social": 220,
                "Nombre Comercial": 170,
                "Teléfono": 140,
                "WhatsApp": 140,
                "Email": 200,
                "Localidad": 150,
            }
            ancho = anchos_especiales.get(titulo, 110)
            self.tabla.column(
                identificador,
                width=ancho,
                anchor="w",
                stretch=titulo in ("Cliente", "Concepto", "Observaciones", "Razón Social", "Nombre Comercial", "Email"),
            )
        for fila in self.datos_actuales["filas"]:
            valores = [
                self.formatear_valor(valor, self.datos_actuales["columnas"][indice])
                for indice, valor in enumerate(fila)
            ]
            self.tabla.insert("", "end", values=valores)
        self.scroll_y = ttk.Scrollbar(
            self.tabla_frame,
            orient="vertical",
            command=self.tabla.yview,
        )
        self.scroll_x = ttk.Scrollbar(
            self.tabla_frame,
            orient="horizontal",
            command=self.tabla.xview,
        )
        self.tabla.configure(
            yscrollcommand=self.scroll_y.set,
            xscrollcommand=self.scroll_x.set,
        )
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")
        self.resultado_label.configure(
            text=f"Resultados: {len(self.datos_actuales['filas'])}"
        )

    def exportar_excel(self):
        if self.datos_actuales is None:
            self.actualizar_informe()
        try:
            ruta = InformesService.exportar_excel(self.datos_actuales)
        except Exception as error:
            messagebox.showerror("Exportación", str(error), parent=self)
            return
        messagebox.showinfo("Exportación Excel", f"Archivo creado correctamente.\n{ruta}", parent=self)

    def exportar_pdf(self):
        if self.datos_actuales is None:
            self.actualizar_informe()
        try:
            ruta = InformesService.exportar_pdf(self.datos_actuales)
        except Exception as error:
            messagebox.showerror("Exportación", str(error), parent=self)
            return
        messagebox.showinfo("Exportación PDF", f"Archivo creado correctamente.\n{ruta}", parent=self)

    def imprimir_informe(self):
        if self.datos_actuales is None:
            self.actualizar_informe()
        try:
            ruta = InformesService.imprimir_pdf(self.datos_actuales)
        except Exception as error:
            messagebox.showerror("Impresión", str(error), parent=self)
            return
        messagebox.showinfo("Impresión", f"Informe preparado para imprimir.\n{ruta}", parent=self)

    def cerrar_informe(self):
        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_inicio"):
            aplicacion.mostrar_inicio()

    @staticmethod
    def obtener_fecha(valor):
        valor = valor.strip()
        if not valor:
            return None
        try:
            return datetime.strptime(valor, "%d/%m/%Y").date().isoformat()
        except ValueError as error:
            raise ValueError("Las fechas deben tener formato DD/MM/AAAA.") from error

    @staticmethod
    def formatear_valor(valor, columna):
        if valor is None:
            return ""
        if columna in InformesService.COLUMNAS_MONEDA:
            return InformesService.formatear_moneda(valor)
        if columna == "Renovable":
            return "Sí" if valor else "No"
        if columna == "Mes" and len(str(valor)) == 7:
            return datetime.strptime(str(valor), "%Y-%m").strftime("%m/%Y")
        if any(texto in columna for texto in ("Fecha", "Vencimiento", "inicio", "fin")):
            try:
                return datetime.strptime(str(valor), "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                pass
        return str(valor)

    def _es_informe_agenda(self):
        return self.selector_informe.get() == "Agenda Telefónica de Clientes"

    def _on_informe_cambiado(self, _valor=None):
        if self._es_informe_agenda():
            self.filtros_agenda.grid()
        else:
            self.filtros_agenda.grid_remove()

    def _sincronizar_filtros_agenda(self):
        if self._bloqueo_filtros_agenda:
            return
        self._bloqueo_filtros_agenda = True
        try:
            if self.var_agenda_todos.get():
                self.var_agenda_activos.set(False)
                self.var_agenda_telefono.set(False)
                self.var_agenda_whatsapp.set(False)
                self.var_agenda_email.set(False)
            elif any(
                (
                    self.var_agenda_activos.get(),
                    self.var_agenda_telefono.get(),
                    self.var_agenda_whatsapp.get(),
                    self.var_agenda_email.get(),
                )
            ):
                self.var_agenda_todos.set(False)
        finally:
            self._bloqueo_filtros_agenda = False
