from datetime import date, datetime
from tkinter import messagebox

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from services.estadisticas_service import EstadisticasService
from services.oportunidad_service import OportunidadService


class EstadisticasFrame(ctk.CTkFrame):
    ROJO = "#C00000"
    NEGRO = "#1B1B1B"

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.datos = None
        self.canvases = []
        clientes = EstadisticasService.listar_clientes()
        self.clientes_por_nombre = {nombre: cliente_id for cliente_id, nombre in clientes}
        self._crear_interfaz()
        self.actualizar()

    def _crear_interfaz(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text="ESTADÍSTICAS COMERCIALES", font=("Arial", 26, "bold"),
            text_color=self.ROJO,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 8))

        filtros = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        filtros.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 8))
        filtros.grid_columnconfigure(4, weight=1)
        self.desde = self._campo_fecha(filtros, 0, "Desde", date.today().replace(month=1, day=1))
        self.hasta = self._campo_fecha(filtros, 1, "Hasta", date.today())
        self.cliente = self._combo(
            filtros, 2, "Cliente", ["Todos"] + list(self.clientes_por_nombre), 210
        )
        self.servicio = self._combo(
            filtros, 3, "Servicio", ["Todos"] + EstadisticasService.listar_servicios(), 180
        )
        self.estado = self._combo(
            filtros, 4, "Estado oportunidad", ["Todos"] + list(OportunidadService.ESTADOS), 180
        )
        botones = ctk.CTkFrame(filtros, fg_color="white")
        botones.grid(row=0, column=5, rowspan=2, sticky="e", padx=(10, 0), pady=(18, 0))
        ctk.CTkButton(
            botones, text="Actualizar", width=95, fg_color=self.ROJO,
            hover_color="#990000", command=self.actualizar,
        ).grid(row=0, column=0, padx=4)
        ctk.CTkButton(
            botones, text="Exportar PDF", width=105, fg_color="#333333",
            hover_color="#111111", command=self.exportar_pdf,
        ).grid(row=0, column=1, padx=4)
        ctk.CTkButton(
            botones, text="Exportar Excel", width=110, fg_color="#16823A",
            hover_color="#0E5C28", command=self.exportar_excel,
        ).grid(row=0, column=2, padx=4)

        metricas = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        metricas.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        self.indicadores = {}
        configuracion = (
            ("facturacion_mensual", "FACTURACIÓN", True),
            ("cobros_mensuales", "COBROS", True),
            ("saldo_pendiente", "SALDO PENDIENTE", True),
            ("clientes_activos", "CLIENTES ACTIVOS", False),
            ("servicios_activos", "SERVICIOS ACTIVOS", False),
            ("oportunidades_abiertas", "OPORTUNIDADES ABIERTAS", False),
            ("oportunidades_ganadas", "OPORTUNIDADES GANADAS", False),
        )
        for indice, (clave, titulo, moneda) in enumerate(configuracion):
            fila, columna = divmod(indice, 4)
            metricas.grid_columnconfigure(columna, weight=1, uniform="estadisticas")
            tarjeta = ctk.CTkFrame(metricas, fg_color=self.NEGRO, corner_radius=5)
            tarjeta.grid(row=fila, column=columna, sticky="nsew", padx=5, pady=4)
            ctk.CTkLabel(
                tarjeta, text=titulo, font=("Arial", 9, "bold"), text_color="#CCCCCC",
            ).pack(anchor="w", padx=12, pady=(8, 0))
            valor = ctk.CTkLabel(
                tarjeta, text="$ 0,00" if moneda else "0",
                font=("Arial", 18, "bold"), text_color="white",
            )
            valor.pack(anchor="w", padx=12, pady=(2, 8))
            self.indicadores[clave] = (valor, moneda)

        self.tabs = ctk.CTkTabview(
            self, fg_color="#F5F5F5", segmented_button_selected_color=self.ROJO,
            segmented_button_selected_hover_color="#990000",
        )
        self.tabs.grid(row=4, column=0, sticky="nsew", padx=20, pady=(0, 16))
        for nombre in ("Mensual", "Oportunidades", "Rankings", "Deuda"):
            tab = self.tabs.add(nombre)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

    def _campo_fecha(self, master, columna, titulo, valor):
        ctk.CTkLabel(master, text=titulo, font=("Arial", 10, "bold")).grid(
            row=0, column=columna, sticky="w", padx=4
        )
        entrada = ctk.CTkEntry(master, width=110)
        entrada.grid(row=1, column=columna, sticky="w", padx=4)
        entrada.insert(0, valor.strftime("%d/%m/%Y"))
        return entrada

    def _combo(self, master, columna, titulo, valores, ancho):
        ctk.CTkLabel(master, text=titulo, font=("Arial", 10, "bold")).grid(
            row=0, column=columna, sticky="w", padx=4
        )
        combo = ctk.CTkComboBox(master, values=valores or ["Todos"], width=ancho)
        combo.grid(row=1, column=columna, sticky="w", padx=4)
        combo.set("Todos")
        return combo

    def actualizar(self):
        try:
            self.datos = EstadisticasService.obtener(
                desde=self._convertir_fecha(self.desde.get()),
                hasta=self._convertir_fecha(self.hasta.get()),
                cliente_id=self.clientes_por_nombre.get(self.cliente.get()),
                servicio=self.servicio.get(), estado=self.estado.get(),
            )
        except (ValueError, OSError) as error:
            messagebox.showerror("Estadísticas", str(error), parent=self)
            return
        for clave, (etiqueta, moneda) in self.indicadores.items():
            valor = self.datos["indicadores"][clave]
            etiqueta.configure(text=self.formatear_moneda(valor) if moneda else str(valor))
        self._dibujar_graficos()

    def _dibujar_graficos(self):
        for canvas in self.canvases:
            canvas.get_tk_widget().destroy()
        self.canvases.clear()
        self._grafico_mensual()
        self._grafico_oportunidades()
        self._grafico_rankings()
        self._grafico_deuda()

    def _grafico_mensual(self):
        figura = Figure(figsize=(10, 4), dpi=100, tight_layout=True)
        for eje, serie, titulo, color in (
            (figura.add_subplot(1, 2, 1), self.datos["facturacion_mensual"], "Facturación por mes", self.ROJO),
            (figura.add_subplot(1, 2, 2), self.datos["cobros_mensuales"], "Cobros por mes", "#1B1B1B"),
        ):
            self._barras(eje, serie, titulo, color)
        self._montar("Mensual", figura)

    def _grafico_oportunidades(self):
        figura = Figure(figsize=(8, 4), dpi=100, tight_layout=True)
        eje = figura.add_subplot(1, 1, 1)
        serie = self.datos["oportunidades_estado"]
        if serie:
            eje.pie(
                [valor for _, valor in serie], labels=[nombre for nombre, _ in serie],
                autopct="%1.0f%%", startangle=90,
                colors=("#C00000", "#1B1B1B", "#F4C542", "#5DADE2", "#52C878", "#888888"),
            )
        else:
            eje.text(.5, .5, "Sin oportunidades para los filtros seleccionados", ha="center", va="center")
        eje.set_title("Estado de oportunidades")
        self._montar("Oportunidades", figura)

    def _grafico_rankings(self):
        figura = Figure(figsize=(10, 4), dpi=100, tight_layout=True)
        self._barras(
            figura.add_subplot(1, 2, 1), self.datos["ranking_clientes"],
            "Clientes por facturación", self.ROJO, horizontal=True,
        )
        self._barras(
            figura.add_subplot(1, 2, 2), self.datos["ranking_servicios"],
            "Servicios más vendidos", "#1B1B1B", horizontal=True,
        )
        self._montar("Rankings", figura)

    def _grafico_deuda(self):
        figura = Figure(figsize=(9, 4), dpi=100, tight_layout=True)
        eje = figura.add_subplot(1, 1, 1)
        serie = self.datos["deuda_mensual"]
        if serie:
            eje.plot([mes for mes, _ in serie], [valor for _, valor in serie], marker="o", color=self.ROJO, linewidth=2)
            eje.fill_between([mes for mes, _ in serie], [valor for _, valor in serie], color="#F3B5B5", alpha=.4)
            eje.tick_params(axis="x", rotation=35)
            eje.grid(axis="y", alpha=.25)
        else:
            eje.text(.5, .5, "Sin datos de deuda", ha="center", va="center")
        eje.set_title("Evolución mensual de saldo pendiente")
        self._montar("Deuda", figura)

    def _montar(self, tab, figura):
        canvas = FigureCanvasTkAgg(figura, master=self.tabs.tab(tab))
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.canvases.append(canvas)

    @staticmethod
    def _barras(eje, serie, titulo, color, horizontal=False):
        if serie:
            etiquetas, valores = zip(*serie)
            if horizontal:
                eje.barh(etiquetas, valores, color=color)
                eje.invert_yaxis()
            else:
                eje.bar(etiquetas, valores, color=color)
                eje.tick_params(axis="x", rotation=35)
            eje.grid(axis="x" if horizontal else "y", alpha=.2)
        else:
            eje.text(.5, .5, "Sin datos", ha="center", va="center")
        eje.set_title(titulo)

    def exportar_pdf(self):
        if not self.datos:
            self.actualizar()
        try:
            ruta = EstadisticasService.exportar_pdf(self.datos)
        except Exception as error:
            messagebox.showerror("Estadísticas", f"No se pudo exportar el PDF.\n{error}", parent=self)
            return
        messagebox.showinfo("Estadísticas", f"PDF creado correctamente.\n{ruta}", parent=self)

    def exportar_excel(self):
        if not self.datos:
            self.actualizar()
        try:
            ruta = EstadisticasService.exportar_excel(self.datos)
        except Exception as error:
            messagebox.showerror("Estadísticas", f"No se pudo exportar el Excel.\n{error}", parent=self)
            return
        messagebox.showinfo("Estadísticas", f"Excel creado correctamente.\n{ruta}", parent=self)

    @staticmethod
    def _convertir_fecha(valor):
        valor = valor.strip()
        if not valor:
            return None
        try:
            return datetime.strptime(valor, "%d/%m/%Y").date().isoformat()
        except ValueError as error:
            raise ValueError("Use el formato DD/MM/AAAA en Desde y Hasta.") from error

    @staticmethod
    def formatear_moneda(valor):
        return EstadisticasService.formatear_moneda(valor)
