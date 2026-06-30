from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.contacto import Contacto
from services.cliente_service import ClienteService
from services.contacto_service import ContactoService
from views.servicios import ServiciosWindow


class ContactoFormWindow(ctk.CTkToplevel):
    def __init__(self, master, cliente_id=None, contacto_id=None, al_guardar=None):
        super().__init__(master)
        self.contacto_id = contacto_id
        self.al_guardar = al_guardar
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {fila[2]: fila[0] for fila in clientes}
        self.nombres_por_id = {fila[0]: fila[2] for fila in clientes}
        self.title("Registrar contacto" if contacto_id is None else "Modificar contacto")
        self.geometry("620x690")
        self.minsize(560, 620)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self._crear_interfaz(cliente_id)
        if contacto_id is not None:
            self._cargar_contacto()

    def _crear_interfaz(self, cliente_id):
        contenido = ctk.CTkScrollableFrame(self, fg_color="white")
        contenido.pack(fill="both", expand=True, padx=20, pady=20)
        contenido.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            contenido, text=self.title().upper(), font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.campos = {}
        fila = 1
        fila = self._combo(contenido, fila, "cliente", "Cliente *", list(self.clientes_por_nombre))
        fila = self._entrada(contenido, fila, "fecha", "Fecha * (DD/MM/AAAA)")
        fila = self._entrada(contenido, fila, "hora", "Hora * (HH:MM)")
        fila = self._combo(contenido, fila, "tipo", "Tipo *", list(ContactoService.TIPOS))
        fila = self._combo(contenido, fila, "resultado", "Resultado *", list(ContactoService.RESULTADOS))
        fila = self._entrada(contenido, fila, "proximo_contacto", "Próximo contacto (DD/MM/AAAA)")
        fila = self._entrada(contenido, fila, "vendedor", "Vendedor")
        ctk.CTkLabel(contenido, text="Observaciones", anchor="w").grid(
            row=fila, column=0, sticky="ew", pady=(8, 0)
        )
        self.observaciones = ctk.CTkTextbox(contenido, height=100)
        self.observaciones.grid(row=fila + 1, column=0, sticky="ew")
        botones = ctk.CTkFrame(contenido, fg_color="white")
        botones.grid(row=fila + 2, column=0, sticky="ew", pady=(18, 4))
        botones.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            botones, text="Guardar contacto", height=42, fg_color="#C00000",
            hover_color="#990000", command=self.guardar,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            botones, text="Cancelar", width=110, height=42, fg_color="#555555",
            hover_color="#333333", command=self.destroy,
        ).grid(row=0, column=1, padx=(6, 0))
        self._establecer("fecha", date.today().strftime("%d/%m/%Y"))
        self._establecer("hora", datetime.now().strftime("%H:%M"))
        self.campos["tipo"].set(ContactoService.TIPOS[0])
        self.campos["resultado"].set(ContactoService.RESULTADOS[0])
        if cliente_id in self.nombres_por_id:
            self.campos["cliente"].set(self.nombres_por_id[cliente_id])
            self.campos["cliente"].configure(state="disabled")

    def _entrada(self, master, fila, clave, texto):
        ctk.CTkLabel(master, text=texto, anchor="w").grid(row=fila, column=0, sticky="ew", pady=(8, 0))
        campo = ctk.CTkEntry(master)
        campo.grid(row=fila + 1, column=0, sticky="ew")
        self.campos[clave] = campo
        return fila + 2

    def _combo(self, master, fila, clave, texto, valores):
        ctk.CTkLabel(master, text=texto, anchor="w").grid(row=fila, column=0, sticky="ew", pady=(8, 0))
        campo = ctk.CTkComboBox(master, values=valores or [""])
        campo.grid(row=fila + 1, column=0, sticky="ew")
        campo.set(valores[0] if valores else "")
        self.campos[clave] = campo
        return fila + 2

    def _establecer(self, clave, valor):
        campo = self.campos[clave]
        estado = campo.cget("state")
        if estado == "disabled":
            campo.configure(state="normal")
        if isinstance(campo, ctk.CTkComboBox):
            campo.set(valor)
        else:
            campo.delete(0, "end")
            campo.insert(0, valor)
        if estado == "disabled":
            campo.configure(state="disabled")

    def _cargar_contacto(self):
        fila = ContactoService.obtener(self.contacto_id)
        if not fila:
            messagebox.showerror("CRM", "No se encontró el contacto.", parent=self)
            self.destroy()
            return
        valores = {
            "cliente": self.nombres_por_id.get(fila[1], ""),
            "fecha": self.formatear_fecha(fila[2]), "hora": fila[3] or "",
            "tipo": fila[4] or ContactoService.TIPOS[0],
            "resultado": fila[5] or ContactoService.RESULTADOS[0],
            "proximo_contacto": self.formatear_fecha(fila[7]), "vendedor": fila[8] or "",
        }
        for clave, valor in valores.items():
            self._establecer(clave, valor)
        self.observaciones.insert("1.0", fila[6] or "")

    def guardar(self):
        cliente_id = self.clientes_por_nombre.get(self.campos["cliente"].get())
        try:
            contacto = Contacto(
                id=self.contacto_id, cliente_id=cliente_id,
                fecha=self.convertir_fecha(self.campos["fecha"].get(), obligatoria=True),
                hora=self.campos["hora"].get().strip(), tipo=self.campos["tipo"].get(),
                resultado=self.campos["resultado"].get(),
                observaciones=self.observaciones.get("1.0", "end").strip(),
                proximo_contacto=self.convertir_fecha(self.campos["proximo_contacto"].get()),
                vendedor=self.campos["vendedor"].get().strip(),
            )
            ContactoService.guardar(contacto) if self.contacto_id is None else ContactoService.actualizar(contacto)
        except ValueError as error:
            messagebox.showerror("CRM", str(error), parent=self)
            return
        vendido = contacto.resultado == "Vendido" and messagebox.askyesno(
            "Venta registrada", "¿Desea crear un servicio?", parent=self
        )
        if self.al_guardar:
            self.al_guardar()
        nombre, master = self.nombres_por_id.get(cliente_id, "Cliente"), self.master
        self.destroy()
        if vendido:
            ServiciosWindow(master, cliente_id, nombre)

    @staticmethod
    def convertir_fecha(valor, obligatoria=False):
        valor = valor.strip()
        if not valor and not obligatoria:
            return ""
        try:
            return datetime.strptime(valor, "%d/%m/%Y").date().isoformat()
        except ValueError as error:
            raise ValueError("Ingrese las fechas con formato DD/MM/AAAA.") from error

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""


class CRMWindow(ctk.CTkToplevel):
    def __init__(self, master, cliente_id=None):
        super().__init__(master)
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {fila[2]: fila[0] for fila in clientes}
        self.nombres_por_id = {fila[0]: fila[2] for fila in clientes}
        self.cliente_inicial = cliente_id
        self.title("CRM Comercial")
        self.geometry("1280x760")
        self.minsize(1050, 680)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self._crear_interfaz()
        self.cargar_contactos()

    def _crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="CRM COMERCIAL", font=("Arial", 26, "bold"), text_color="#C00000").grid(
            row=0, column=0, sticky="w", padx=20, pady=(18, 8)
        )
        resumen = ctk.CTkFrame(self, fg_color="#1B1B1B", corner_radius=5)
        resumen.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.etiquetas_resumen = {}
        titulos = (
            ("ultimo", "ÚLTIMO CONTACTO"), ("proximo", "PRÓXIMO CONTACTO"),
            ("cantidad", "CONTACTOS"), ("ventas", "VENTAS"),
            ("facturacion", "FACTURACIÓN HISTÓRICA"), ("saldo", "SALDO PENDIENTE"),
        )
        for columna, (clave, titulo) in enumerate(titulos):
            resumen.grid_columnconfigure(columna, weight=1, uniform="crm")
            tarjeta = ctk.CTkFrame(resumen, fg_color="#292929", corner_radius=4)
            tarjeta.grid(row=0, column=columna, sticky="nsew", padx=4, pady=8)
            ctk.CTkLabel(tarjeta, text=titulo, font=("Arial", 9, "bold"), text_color="#CCCCCC").pack(anchor="w", padx=10, pady=(8, 0))
            etiqueta = ctk.CTkLabel(tarjeta, text="-", font=("Arial", 14, "bold"), text_color="white")
            etiqueta.pack(anchor="w", padx=10, pady=(2, 8))
            self.etiquetas_resumen[clave] = etiqueta
        filtros = ctk.CTkFrame(self, fg_color="white")
        filtros.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        filtros.grid_columnconfigure(0, weight=1)
        self.filtro_cliente = ctk.CTkComboBox(filtros, values=["Todos"] + list(self.clientes_por_nombre), width=260)
        self.filtro_cliente.grid(row=0, column=0, sticky="w")
        self.filtro_cliente.set(self.nombres_por_id.get(self.cliente_inicial, "Todos"))
        self.filtro_fecha = ctk.CTkEntry(filtros, placeholder_text="Fecha DD/MM/AAAA", width=155)
        self.filtro_fecha.grid(row=0, column=1, padx=6)
        self.filtro_tipo = ctk.CTkComboBox(filtros, values=["Todos"] + list(ContactoService.TIPOS), width=140)
        self.filtro_tipo.grid(row=0, column=2, padx=6)
        self.filtro_tipo.set("Todos")
        self.filtro_resultado = ctk.CTkComboBox(filtros, values=["Todos"] + list(ContactoService.RESULTADOS), width=145)
        self.filtro_resultado.grid(row=0, column=3, padx=6)
        self.filtro_resultado.set("Todos")
        ctk.CTkButton(filtros, text="Buscar", width=90, command=self.cargar_contactos).grid(row=0, column=4, padx=6)
        ctk.CTkButton(filtros, text="Limpiar", width=90, fg_color="#555555", hover_color="#333333", command=self.limpiar_filtros).grid(row=0, column=5, padx=6)
        marco = ctk.CTkFrame(self, fg_color="white")
        marco.grid(row=3, column=0, sticky="nsew", padx=20)
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        columnas = ("id", "fecha", "hora", "cliente", "tipo", "resultado", "proximo", "vendedor", "observaciones")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings")
        anchos = {"id": 45, "fecha": 90, "hora": 60, "cliente": 190, "tipo": 95, "resultado": 100, "proximo": 100, "vendedor": 110, "observaciones": 300}
        for clave in columnas:
            self.tabla.heading(clave, text=clave.title())
            self.tabla.column(clave, width=anchos[clave], anchor="w", stretch=clave in ("cliente", "observaciones"))
        self.tabla.bind("<Double-1>", lambda _e: self.modificar_contacto())
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=4, column=0, sticky="ew", padx=20, pady=16)
        acciones.grid_columnconfigure(4, weight=1)
        ctk.CTkButton(acciones, text="Nuevo contacto", width=135, fg_color="#C00000", hover_color="#990000", command=self.nuevo_contacto).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(acciones, text="Modificar", width=110, fg_color="#444444", hover_color="#222222", command=self.modificar_contacto).grid(row=0, column=1, padx=6)
        ctk.CTkButton(acciones, text="Eliminar", width=110, fg_color="#7A0000", hover_color="#550000", command=self.eliminar_contacto).grid(row=0, column=2, padx=6)
        ctk.CTkButton(acciones, text="Cerrar", width=100, fg_color="#666666", hover_color="#444444", command=self.destroy).grid(row=0, column=5)

    def cargar_contactos(self):
        try:
            fecha = ContactoFormWindow.convertir_fecha(self.filtro_fecha.get())
        except ValueError as error:
            messagebox.showerror("CRM", str(error), parent=self)
            return
        nombre = self.filtro_cliente.get().strip()
        cliente_id = self.clientes_por_nombre.get(nombre)
        filas = ContactoService.listar(
            cliente_id=cliente_id, cliente="" if nombre == "Todos" else nombre,
            fecha=fecha, tipo=self.filtro_tipo.get(), resultado=self.filtro_resultado.get(),
        )
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        for fila in filas:
            self.tabla.insert("", "end", values=(
                fila[0], self.formatear_fecha(fila[2]), fila[3], fila[10], fila[4],
                fila[5], self.formatear_fecha(fila[7]), fila[8], fila[6],
            ))
        self.actualizar_resumen(cliente_id)

    def actualizar_resumen(self, cliente_id):
        if cliente_id is None:
            for etiqueta in self.etiquetas_resumen.values():
                etiqueta.configure(text="-")
            return
        datos = ContactoService.resumen_cliente(cliente_id)
        ultimo = datos["ultimo"]
        valores = {
            "ultimo": f"{self.formatear_fecha(ultimo[0])} {ultimo[1]} · {ultimo[2]}" if ultimo else "Sin contactos",
            "proximo": self.formatear_fecha(datos["proximo"]) or "Sin fecha",
            "cantidad": str(datos["cantidad"]), "ventas": str(datos["ventas"]),
            "facturacion": self.formatear_moneda(datos["facturacion"]),
            "saldo": self.formatear_moneda(datos["saldo"]),
        }
        for clave, valor in valores.items():
            self.etiquetas_resumen[clave].configure(text=valor)

    def limpiar_filtros(self):
        self.filtro_cliente.set("Todos")
        self.filtro_fecha.delete(0, "end")
        self.filtro_tipo.set("Todos")
        self.filtro_resultado.set("Todos")
        self.cargar_contactos()

    def nuevo_contacto(self):
        ContactoFormWindow(self, cliente_id=self.clientes_por_nombre.get(self.filtro_cliente.get()), al_guardar=self.cargar_contactos)

    def modificar_contacto(self):
        contacto_id = self.obtener_id_seleccionado()
        if contacto_id is None:
            messagebox.showwarning("CRM", "Seleccione un contacto.", parent=self)
            return
        ContactoFormWindow(self, contacto_id=contacto_id, al_guardar=self.cargar_contactos)

    def eliminar_contacto(self):
        contacto_id = self.obtener_id_seleccionado()
        if contacto_id is None:
            messagebox.showwarning("CRM", "Seleccione un contacto.", parent=self)
            return
        if messagebox.askyesno("CRM", "¿Desea eliminar el contacto?", parent=self):
            ContactoService.eliminar(contacto_id)
            self.cargar_contactos()

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        valores = self.tabla.item(seleccion[0], "values") if seleccion else ()
        return int(valores[0]) if valores else None

    @staticmethod
    def formatear_fecha(valor):
        return ContactoFormWindow.formatear_fecha(valor)

    @staticmethod
    def formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
