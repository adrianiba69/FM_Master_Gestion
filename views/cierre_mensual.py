from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from services.cierre_mensual_service import CierreMensualService


class CierreMensualFrame(ctk.CTkFrame):
    ROJO = "#C00000"
    NEGRO = "#1B1B1B"

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.servicio = CierreMensualService()
        self.paso = 1
        self.pendientes = []
        self.seleccionados = set()
        self.resultado_generacion = None
        self._crear_base()
        self.mostrar_paso_1()

    def _crear_base(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)
        cabecera = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        cabecera.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 10))
        cabecera.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cabecera, text="CIERRE DEL MES", font=("Arial", 26, "bold"),
            text_color=self.ROJO,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            cabecera, text=self.servicio.periodo, font=("Arial", 15, "bold"),
            text_color="#555555",
        ).grid(row=0, column=1, sticky="e")

        self.barra_pasos = ctk.CTkFrame(self, width=190, fg_color=self.NEGRO, corner_radius=0)
        self.barra_pasos.grid(row=1, column=0, sticky="nsw")
        self.barra_pasos.grid_propagate(False)
        self.etiquetas_pasos = []
        nombres = ("Análisis", "Selección", "Resúmenes PDF", "Resultado", "Renovación", "Backup", "Informes")
        for indice, nombre in enumerate(nombres, 1):
            etiqueta = ctk.CTkLabel(
                self.barra_pasos, text=f"PASO {indice}\n{nombre}", anchor="w",
                justify="left", height=54, corner_radius=4, padx=14,
                font=("Arial", 12, "bold"), text_color="#BBBBBB",
            )
            etiqueta.pack(fill="x", padx=10, pady=(10 if indice == 1 else 3, 0))
            self.etiquetas_pasos.append(etiqueta)

        self.contenido = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        self.contenido.grid(row=1, column=1, sticky="nsew", padx=22, pady=(0, 18))
        self.contenido.grid_rowconfigure(1, weight=1)
        self.contenido.grid_columnconfigure(0, weight=1)

    def _preparar_paso(self, numero, titulo, detalle):
        self.paso = numero
        for widget in self.contenido.winfo_children():
            widget.destroy()
        for indice, etiqueta in enumerate(self.etiquetas_pasos, 1):
            if indice < numero:
                etiqueta.configure(fg_color="#333333", text_color="#FFFFFF")
            elif indice == numero:
                etiqueta.configure(fg_color=self.ROJO, text_color="#FFFFFF")
            else:
                etiqueta.configure(fg_color="transparent", text_color="#BBBBBB")
        encabezado = ctk.CTkFrame(self.contenido, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew", pady=(4, 12))
        ctk.CTkLabel(
            encabezado, text=f"PASO {numero} · {titulo}", font=("Arial", 20, "bold"),
            text_color="#222222",
        ).pack(anchor="w")
        ctk.CTkLabel(
            encabezado, text=detalle, font=("Arial", 12), text_color="#666666",
        ).pack(anchor="w", pady=(3, 0))

    def _boton_continuar(self, comando, texto="Continuar"):
        boton = ctk.CTkButton(
            self.contenido, text=texto, width=180, height=42,
            fg_color=self.ROJO, hover_color="#990000", command=comando,
        )
        boton.grid(row=2, column=0, sticky="e", pady=(14, 0))
        return boton

    def mostrar_paso_1(self):
        self._preparar_paso(1, "ANÁLISIS DE SERVICIOS", "Estado de todos los servicios al día de hoy y próximos 7 días.")
        analisis = self.servicio.analizar_servicios()
        marco = ctk.CTkFrame(self.contenido, fg_color="#F5F5F5", corner_radius=6)
        marco.grid(row=1, column=0, sticky="nsew")
        marco.grid_rowconfigure(1, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        resumen = (
            f"Vencidos: {len(analisis['vencidos'])}     "
            f"Vencen hoy: {len(analisis['hoy'])}     "
            f"Vencen en 7 días: {len(analisis['proximos'])}"
        )
        ctk.CTkLabel(marco, text=resumen, font=("Arial", 14, "bold"), text_color=self.ROJO).grid(
            row=0, column=0, sticky="w", padx=14, pady=12
        )
        tabla = ttk.Treeview(marco, columns=("estado", "cliente", "concepto", "fin", "renovable"), show="headings")
        for columna, texto, ancho in (
            ("estado", "Estado", 105), ("cliente", "Cliente", 230),
            ("concepto", "Servicio", 250), ("fin", "Vencimiento", 110),
            ("renovable", "Renovable", 90),
        ):
            tabla.heading(columna, text=texto)
            tabla.column(columna, width=ancho, anchor="w", stretch=columna in ("cliente", "concepto"))
        for clave, estado in (("vencidos", "Vencido"), ("hoy", "Vence hoy"), ("proximos", "Próximo")):
            for item in analisis[clave]:
                tabla.insert("", "end", values=(estado, item["cliente"], item["concepto"], self.fecha(item["fecha_fin"]), "Sí" if item["renovable"] else "No"))
        tabla.grid(row=1, column=0, sticky="nsew", padx=(14, 0), pady=(0, 14))
        scroll = ttk.Scrollbar(marco, command=tabla.yview)
        tabla.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 14), pady=(0, 14))
        self._boton_continuar(self.mostrar_paso_2)

    def mostrar_paso_2(self):
        self._preparar_paso(2, "CLIENTES CON RESUMEN PENDIENTE", "Seleccione todos los clientes o elija cada uno individualmente.")
        self.pendientes = self.servicio.clientes_pendientes()
        self.seleccionados = {item["cliente_id"] for item in self.pendientes}
        marco = ctk.CTkFrame(self.contenido, fg_color="#F5F5F5", corner_radius=6)
        marco.grid(row=1, column=0, sticky="nsew")
        marco.grid_rowconfigure(1, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        barra = ctk.CTkFrame(marco, fg_color="transparent")
        barra.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
        ctk.CTkButton(barra, text="☑ Todos", width=105, fg_color="#333333", command=self.seleccionar_todos).pack(side="left", padx=(0, 8))
        ctk.CTkButton(barra, text="☐ Ninguno", width=105, fg_color="#666666", command=self.deseleccionar_todos).pack(side="left")
        self.etiqueta_seleccion = ctk.CTkLabel(barra, text="", font=("Arial", 12, "bold"))
        self.etiqueta_seleccion.pack(side="right")
        self.tabla_pendientes = ttk.Treeview(marco, columns=("marca", "cliente", "servicios", "periodo", "total"), show="headings")
        for columna, texto, ancho in (
            ("marca", "", 45), ("cliente", "Cliente", 220), ("servicios", "Servicios", 300),
            ("periodo", "Período", 190), ("total", "Total", 110),
        ):
            self.tabla_pendientes.heading(columna, text=texto)
            self.tabla_pendientes.column(columna, width=ancho, anchor="w", stretch=columna in ("cliente", "servicios"))
        for item in self.pendientes:
            conceptos = ", ".join(servicio["concepto"] for servicio in item["servicios"])
            periodo = f"{self.fecha(item['fecha_inicio'])} — {self.fecha(item['fecha_fin'])}"
            self.tabla_pendientes.insert("", "end", iid=str(item["cliente_id"]), values=("☑", item["cliente"], conceptos, periodo, self.moneda(item["total"])))
        self.tabla_pendientes.bind("<Double-1>", self.alternar_cliente)
        self.tabla_pendientes.bind("<space>", self.alternar_cliente)
        self.tabla_pendientes.grid(row=1, column=0, sticky="nsew", padx=(12, 0), pady=(0, 12))
        scroll = ttk.Scrollbar(marco, command=self.tabla_pendientes.yview)
        self.tabla_pendientes.configure(yscrollcommand=scroll.set)
        scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))
        self.actualizar_seleccion()
        self._boton_continuar(self.mostrar_paso_3)

    def seleccionar_todos(self):
        self.seleccionados = {item["cliente_id"] for item in self.pendientes}
        self.actualizar_seleccion()

    def deseleccionar_todos(self):
        self.seleccionados.clear()
        self.actualizar_seleccion()

    def alternar_cliente(self, _evento=None):
        seleccion = self.tabla_pendientes.selection()
        if not seleccion:
            return
        cliente_id = int(seleccion[0])
        if cliente_id in self.seleccionados:
            self.seleccionados.remove(cliente_id)
        else:
            self.seleccionados.add(cliente_id)
        self.actualizar_seleccion()

    def actualizar_seleccion(self):
        for item in self.tabla_pendientes.get_children():
            valores = list(self.tabla_pendientes.item(item, "values"))
            valores[0] = "☑" if int(item) in self.seleccionados else "☐"
            self.tabla_pendientes.item(item, values=valores)
        self.etiqueta_seleccion.configure(text=f"{len(self.seleccionados)} de {len(self.pendientes)} seleccionados")

    def mostrar_paso_3(self):
        self._preparar_paso(3, "GENERAR RESÚMENES PDF", "Los períodos ya incluidos en otro resumen se omiten automáticamente.")
        marco = self._panel_centrado(
            "Generación automática",
            f"Se procesarán {len(self.seleccionados)} clientes y sus servicios pendientes.",
        )
        self.boton_generar = ctk.CTkButton(
            marco, text="Generar todos los resúmenes PDF", width=260, height=46,
            fg_color=self.ROJO, hover_color="#990000", command=self.generar_resumenes,
        )
        self.boton_generar.pack(pady=(20, 0))

    def generar_resumenes(self):
        self.boton_generar.configure(state="disabled", text="Generando...")
        self.update_idletasks()
        self.resultado_generacion = self.servicio.generar_resumenes(sorted(self.seleccionados))
        self.mostrar_paso_4()

    def mostrar_paso_4(self):
        self._preparar_paso(4, "RESULTADO DE GENERACIÓN", "Resumen de la emisión realizada durante este cierre.")
        resultado = self.resultado_generacion or {"generados": 0, "omitidos": 0, "importe_total": 0, "errores": []}
        marco = ctk.CTkFrame(self.contenido, fg_color="#F5F5F5", corner_radius=6)
        marco.grid(row=1, column=0, sticky="nsew")
        for indice, (titulo, valor) in enumerate((
            ("Cantidad generada", resultado["generados"]),
            ("Importe total", self.moneda(resultado["importe_total"])),
            ("Omitidos (sin duplicar)", resultado["omitidos"]),
            ("Errores encontrados", len(resultado["errores"])),
        )):
            tarjeta = ctk.CTkFrame(marco, fg_color=self.ROJO if titulo == "Errores encontrados" and valor else self.NEGRO, corner_radius=6)
            tarjeta.grid(row=0, column=indice, sticky="nsew", padx=8, pady=16)
            marco.grid_columnconfigure(indice, weight=1)
            ctk.CTkLabel(tarjeta, text=titulo.upper(), text_color="white", font=("Arial", 10, "bold")).pack(padx=10, pady=(12, 4))
            ctk.CTkLabel(tarjeta, text=str(valor), text_color="white", font=("Arial", 20, "bold")).pack(padx=10, pady=(0, 12))
        if resultado["errores"]:
            texto = "\n".join(f"• {error}" for error in resultado["errores"])
            ctk.CTkTextbox(marco, height=180).grid(row=1, column=0, columnspan=4, sticky="nsew", padx=8, pady=(0, 16))
            caja = marco.grid_slaves(row=1, column=0)[0]
            caja.insert("1.0", texto)
            caja.configure(state="disabled")
        self._boton_continuar(self.mostrar_paso_5)

    def mostrar_paso_5(self):
        self._preparar_paso(5, "RENOVACIÓN AUTOMÁTICA", "Los servicios renovables vencidos o que vencen hoy pueden avanzar al período siguiente.")
        marco = self._panel_centrado("¿Desea renovar automáticamente los servicios renovables?", "Cada renovación actualizará el período y quedará registrada en el historial.")
        botones = ctk.CTkFrame(marco, fg_color="transparent")
        botones.pack(pady=(24, 0))
        ctk.CTkButton(botones, text="Sí, renovar", width=150, height=42, fg_color=self.ROJO, command=lambda: self.procesar_renovacion(True)).pack(side="left", padx=6)
        ctk.CTkButton(botones, text="No renovar", width=150, height=42, fg_color="#555555", command=lambda: self.procesar_renovacion(False)).pack(side="left", padx=6)

    def procesar_renovacion(self, renovar):
        try:
            resultado = self.servicio.renovar_servicios(renovar)
        except Exception as error:
            self.servicio.errores.append(f"Renovación: {error}")
            messagebox.showerror("Cierre mensual", f"No se pudieron procesar las renovaciones:\n{error}", parent=self)
        else:
            if renovar:
                messagebox.showinfo("Renovaciones", f"Renovados: {len(resultado['renovados'])}\nOmitidos: {resultado['omitidos']}\nErrores: {len(resultado['errores'])}", parent=self)
        self.mostrar_paso_6()

    def mostrar_paso_6(self):
        self._preparar_paso(6, "BACKUP DEL SISTEMA", "El asistente está creando y verificando una copia de la base de datos.")
        marco = self._panel_centrado("Creando backup...", "La copia también se guardará dentro de la carpeta del cierre.")
        self.update_idletasks()
        try:
            ruta = self.servicio.crear_backup()
        except Exception as error:
            self.servicio.errores.append(f"Backup: {error}")
            titulo, detalle = "No se pudo crear el backup", str(error)
        else:
            titulo, detalle = "Backup creado correctamente", ruta
        for widget in marco.winfo_children():
            widget.destroy()
        ctk.CTkLabel(marco, text=titulo, font=("Arial", 20, "bold"), text_color=self.ROJO).pack(pady=(10, 8))
        ctk.CTkLabel(marco, text=detalle, wraplength=650, text_color="#555555").pack()
        self._boton_continuar(self.mostrar_paso_7, "Exportar informes")

    def mostrar_paso_7(self):
        self._preparar_paso(7, "INFORMES DEL MES", "Generando el informe mensual en PDF y Excel.")
        marco = self._panel_centrado("Exportando...", f"Destino: cierres/{self.servicio.periodo}/")
        self.update_idletasks()
        try:
            rutas = self.servicio.exportar_informes()
        except Exception as error:
            self.servicio.errores.append(f"Informes: {error}")
            for widget in marco.winfo_children():
                widget.destroy()
            ctk.CTkLabel(marco, text="No se pudieron exportar los informes", font=("Arial", 20, "bold"), text_color=self.ROJO).pack(pady=(10, 8))
            ctk.CTkLabel(marco, text=str(error), wraplength=650).pack()
            self._boton_continuar(self.mostrar_paso_7, "Reintentar")
            return
        for widget in marco.winfo_children():
            widget.destroy()
        ctk.CTkLabel(marco, text="CIERRE MENSUAL FINALIZADO CORRECTAMENTE", font=("Arial", 20, "bold"), text_color=self.ROJO).pack(pady=(8, 14))
        ctk.CTkLabel(marco, text=f"PDF: {rutas['pdf']}\n\nExcel: {rutas['excel']}", justify="left", wraplength=700, text_color="#444444").pack()
        ctk.CTkButton(marco, text="Volver al Dashboard", width=190, height=42, fg_color=self.NEGRO, command=self.volver_inicio).pack(pady=(24, 0))
        messagebox.showinfo("Cierre del Mes", "Cierre mensual finalizado correctamente", parent=self)

    def _panel_centrado(self, titulo, detalle):
        marco = ctk.CTkFrame(self.contenido, fg_color="#F5F5F5", corner_radius=6)
        marco.grid(row=1, column=0, sticky="nsew")
        interior = ctk.CTkFrame(marco, fg_color="transparent")
        interior.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(interior, text=titulo, font=("Arial", 20, "bold"), text_color="#222222", wraplength=700).pack()
        ctk.CTkLabel(interior, text=detalle, font=("Arial", 12), text_color="#666666", wraplength=700).pack(pady=(8, 0))
        return interior

    def volver_inicio(self):
        self.winfo_toplevel().mostrar_inicio()

    @staticmethod
    def fecha(valor):
        try:
            return datetime.strptime(str(valor), "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def moneda(valor):
        return CierreMensualService.moneda(valor)
