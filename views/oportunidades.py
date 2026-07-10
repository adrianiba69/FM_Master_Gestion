from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.cliente import Cliente
from models.oportunidad import Oportunidad
from services.cliente_service import ClienteService
from services.oportunidad_service import OportunidadService
from views.servicios import ServiciosWindow


class ClienteRapidoWindow(ctk.CTkToplevel):
    def __init__(self, master, oportunidad, al_crear):
        super().__init__(master)
        self.oportunidad = oportunidad
        self.al_crear = al_crear
        self.title("Crear cliente desde oportunidad")
        self.geometry("540x480")
        self.resizable(False, False)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        contenido = ctk.CTkFrame(self, fg_color="white")
        contenido.pack(fill="both", expand=True, padx=24, pady=22)
        contenido.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            contenido, text="NUEVO CLIENTE", font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.campos = {}
        datos = (
            ("razon_social", "Razón social *", oportunidad.nombre_potencial),
            ("telefono", "Teléfono", oportunidad.telefono),
            ("whatsapp", "WhatsApp", oportunidad.whatsapp),
            ("email", "Email", oportunidad.email),
        )
        for indice, (clave, etiqueta, valor) in enumerate(datos, start=1):
            ctk.CTkLabel(contenido, text=etiqueta, anchor="w").grid(
                row=indice * 2 - 1, column=0, sticky="ew", pady=(8, 0)
            )
            entrada = ctk.CTkEntry(contenido)
            entrada.grid(row=indice * 2, column=0, sticky="ew")
            entrada.insert(0, valor or "")
            self.campos[clave] = entrada
        ctk.CTkButton(
            contenido, text="Crear cliente y continuar", height=42,
            fg_color="#C00000", hover_color="#990000", command=self.guardar,
        ).grid(row=10, column=0, sticky="ew", pady=(22, 0))

    def guardar(self):
        nombre = self.campos["razon_social"].get().strip()
        if not nombre:
            messagebox.showerror("Oportunidades", "La razón social es obligatoria.", parent=self)
            return
        ahora = datetime.now().strftime("%d/%m/%Y")
        cliente = Cliente(
            razon_social=nombre, telefono=self.campos["telefono"].get().strip(),
            whatsapp=self.campos["whatsapp"].get().strip(),
            email=self.campos["email"].get().strip(), estado="Activo",
            vencimiento=1, fecha_alta=ahora, fecha_modificacion=ahora,
        )
        cliente_id = ClienteService.guardar(cliente)
        self.destroy()
        self.al_crear(cliente_id, nombre)


class OportunidadFormWindow(ctk.CTkToplevel):
    def __init__(self, master, oportunidad_id=None, al_guardar=None):
        super().__init__(master)
        self.oportunidad_id = oportunidad_id
        self.al_guardar = al_guardar
        clientes = ClienteService.listar()
        self.clientes_por_nombre = {fila[2]: fila[0] for fila in clientes}
        self.nombres_por_id = {fila[0]: fila[2] for fila in clientes}
        self.estado_original = None
        self.title("Nueva oportunidad" if oportunidad_id is None else "Modificar oportunidad")
        self.geometry("700x760")
        self.minsize(620, 680)
        self.configure(fg_color="white")
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self._crear_interfaz()
        if oportunidad_id is not None:
            self._cargar()

    def _crear_interfaz(self):
        contenido = ctk.CTkScrollableFrame(self, fg_color="white")
        contenido.pack(fill="both", expand=True, padx=20, pady=20)
        contenido.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            contenido, text=self.title().upper(), font=("Arial", 22, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        self.campos = {}
        fila = 1
        fila = self._combo(contenido, fila, "cliente", "Cliente vinculado", ["Sin cliente"] + list(self.clientes_por_nombre))
        fila = self._entrada(contenido, fila, "nombre_potencial", "Nombre potencial *")
        fila = self._entrada(contenido, fila, "telefono", "Teléfono")
        fila = self._entrada(contenido, fila, "whatsapp", "WhatsApp")
        fila = self._entrada(contenido, fila, "email", "Email")
        fila = self._entrada(contenido, fila, "fecha", "Fecha * (DD/MM/AAAA)")
        fila = self._combo(contenido, fila, "origen", "Origen", list(OportunidadService.ORIGENES))
        fila = self._entrada(contenido, fila, "servicio_interes", "Servicio de interés")
        fila = self._entrada(contenido, fila, "importe_estimado", "Importe estimado")
        fila = self._entrada(contenido, fila, "probabilidad", "Probabilidad %")
        fila = self._combo(contenido, fila, "estado", "Estado", list(OportunidadService.ESTADOS))
        fila = self._entrada(contenido, fila, "proximo_contacto", "Próximo contacto (DD/MM/AAAA)")
        ctk.CTkLabel(contenido, text="Observaciones", anchor="w").grid(row=fila, column=0, sticky="ew", pady=(8, 0))
        self.observaciones = ctk.CTkTextbox(contenido, height=100)
        self.observaciones.grid(row=fila + 1, column=0, sticky="ew")
        botones = ctk.CTkFrame(contenido, fg_color="white")
        botones.grid(row=fila + 2, column=0, sticky="ew", pady=(18, 4))
        botones.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            botones, text="Guardar oportunidad", height=42, fg_color="#C00000",
            hover_color="#990000", command=self.guardar,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            botones, text="Cancelar", width=110, height=42, fg_color="#555555",
            hover_color="#333333", command=self.destroy,
        ).grid(row=0, column=1, padx=(6, 0))
        self._establecer("cliente", "Sin cliente")
        self._establecer("fecha", date.today().strftime("%d/%m/%Y"))
        self._establecer("origen", OportunidadService.ORIGENES[0])
        self._establecer("importe_estimado", "0")
        self._establecer("probabilidad", "0")
        self._establecer("estado", "Nueva")
        self.campos["cliente"].configure(command=self._cliente_seleccionado)

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
        self.campos[clave] = campo
        return fila + 2

    def _establecer(self, clave, valor):
        campo = self.campos[clave]
        if isinstance(campo, ctk.CTkComboBox):
            campo.set(str(valor or ""))
        else:
            campo.delete(0, "end")
            campo.insert(0, str(valor or ""))

    def _cliente_seleccionado(self, nombre):
        cliente_id = self.clientes_por_nombre.get(nombre)
        if not cliente_id:
            return
        fila = ClienteService.obtener(cliente_id)
        if not fila:
            return
        for clave, valor in {
            "nombre_potencial": fila[2], "telefono": fila[7],
            "whatsapp": fila[8], "email": fila[9],
        }.items():
            self._establecer(clave, valor)

    def _cargar(self):
        fila = OportunidadService.obtener(self.oportunidad_id)
        if not fila:
            messagebox.showerror("Oportunidades", "No se encontró la oportunidad.", parent=self)
            self.destroy()
            return
        self.estado_original = fila[11]
        valores = {
            "cliente": self.nombres_por_id.get(fila[1], "Sin cliente"),
            "nombre_potencial": fila[2], "telefono": fila[3], "whatsapp": fila[4],
            "email": fila[5], "fecha": self.formatear_fecha(fila[6]),
            "origen": fila[7], "servicio_interes": fila[8],
            "importe_estimado": self.formatear_numero(fila[9]),
            "probabilidad": self.formatear_numero(fila[10]), "estado": fila[11],
            "proximo_contacto": self.formatear_fecha(fila[12]),
        }
        for clave, valor in valores.items():
            self._establecer(clave, valor)
        self.observaciones.insert("1.0", fila[13] or "")

    def guardar(self):
        try:
            oportunidad = Oportunidad(
                id=self.oportunidad_id,
                cliente_id=self.clientes_por_nombre.get(self.campos["cliente"].get()),
                nombre_potencial=self.campos["nombre_potencial"].get().strip(),
                telefono=self.campos["telefono"].get().strip(),
                whatsapp=self.campos["whatsapp"].get().strip(),
                email=self.campos["email"].get().strip(),
                fecha=self.convertir_fecha(self.campos["fecha"].get(), obligatoria=True),
                origen=self.campos["origen"].get(),
                servicio_interes=self.campos["servicio_interes"].get().strip(),
                importe_estimado=self.convertir_numero(self.campos["importe_estimado"].get()),
                probabilidad=self.convertir_numero(self.campos["probabilidad"].get()),
                estado=self.campos["estado"].get(),
                proximo_contacto=self.convertir_fecha(self.campos["proximo_contacto"].get()),
                observaciones=self.observaciones.get("1.0", "end").strip(),
            )
            if self.oportunidad_id is None:
                oportunidad.id = OportunidadService.guardar(oportunidad)
            else:
                OportunidadService.actualizar(oportunidad)
        except ValueError as error:
            messagebox.showerror("Oportunidades", str(error), parent=self)
            return
        cambio_a_ganada = oportunidad.estado == "Ganada" and self.estado_original != "Ganada"
        if self.al_guardar:
            self.al_guardar()
        if not cambio_a_ganada:
            self.destroy()
            return
        if oportunidad.cliente_id:
            crear = messagebox.askyesno(
                "Oportunidad ganada", "¿Desea crear un servicio para el cliente?", parent=self
            )
            master = self.master
            nombre = self.nombres_por_id.get(oportunidad.cliente_id, oportunidad.nombre_potencial)
            self.destroy()
            if crear:
                ServiciosWindow(master, oportunidad.cliente_id, nombre)
            return
        crear = messagebox.askyesno(
            "Oportunidad ganada",
            "La oportunidad no tiene cliente vinculado. ¿Desea crear el cliente y luego el servicio?",
            parent=self,
        )
        if crear:
            ClienteRapidoWindow(self, oportunidad, lambda cid, nombre: self._cliente_creado(oportunidad, cid, nombre))
        else:
            self.destroy()

    def _cliente_creado(self, oportunidad, cliente_id, nombre):
        oportunidad.cliente_id = cliente_id
        OportunidadService.actualizar(oportunidad)
        master = self.master
        if self.al_guardar:
            self.al_guardar()
        self.destroy()
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
    def convertir_numero(valor):
        texto = valor.strip().replace("$", "").replace(" ", "") or "0"
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        try:
            return float(texto)
        except ValueError as error:
            raise ValueError("Importe y probabilidad deben ser numéricos.") from error

    @staticmethod
    def formatear_fecha(valor):
        try:
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return valor or ""

    @staticmethod
    def formatear_numero(valor):
        return f"{float(valor or 0):.2f}"


class OportunidadesFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self._crear_interfaz()
        self.cargar_oportunidades()

    def _crear_interfaz(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self, text="CRM", font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))
        metricas = ctk.CTkFrame(self, fg_color="#1B1B1B", corner_radius=5)
        metricas.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.total_label = self._metrica(metricas, 0, "IMPORTE ESTIMADO TOTAL")
        self.probabilidad_label = self._metrica(metricas, 1, "PROBABILIDAD PROMEDIO")
        self.cantidad_label = self._metrica(metricas, 2, "OPORTUNIDADES")
        filtros = ctk.CTkFrame(self, fg_color="white")
        filtros.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        filtros.grid_columnconfigure(0, weight=1)
        self.buscar = ctk.CTkEntry(filtros, placeholder_text="Buscar cliente, contacto o servicio...", width=320)
        self.buscar.grid(row=0, column=0, sticky="w")
        self.buscar.bind("<Return>", lambda _e: self.cargar_oportunidades())
        self.estado = ctk.CTkComboBox(filtros, values=["Todos"] + list(OportunidadService.ESTADOS), width=180)
        self.estado.grid(row=0, column=1, padx=6)
        self.estado.set("Todos")
        self.proximo = ctk.CTkComboBox(filtros, values=list(OportunidadService.FILTROS_CONTACTO), width=140)
        self.proximo.grid(row=0, column=2, padx=6)
        self.proximo.set("Todos")
        ctk.CTkButton(filtros, text="Buscar", width=90, command=self.cargar_oportunidades).grid(row=0, column=3, padx=6)
        ctk.CTkButton(filtros, text="Limpiar", width=90, fg_color="#555555", hover_color="#333333", command=self.limpiar_filtros).grid(row=0, column=4, padx=6)
        marco = ctk.CTkFrame(self, fg_color="white")
        marco.grid(row=3, column=0, sticky="nsew", padx=20)
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        columnas = ("id", "fecha", "nombre", "servicio", "importe", "probabilidad", "estado", "proximo", "origen")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings")
        anchos = {"id": 45, "fecha": 90, "nombre": 210, "servicio": 210, "importe": 110, "probabilidad": 90, "estado": 135, "proximo": 100, "origen": 110}
        for clave in columnas:
            self.tabla.heading(clave, text=clave.title())
            self.tabla.column(clave, width=anchos[clave], anchor="w", stretch=clave in ("nombre", "servicio"))
        self.tabla.bind("<Double-1>", lambda _e: self.modificar())
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=4, column=0, sticky="ew", padx=20, pady=16)
        ctk.CTkButton(acciones, text="Nueva oportunidad", width=150, fg_color="#C00000", hover_color="#990000", command=self.nueva).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(acciones, text="Modificar", width=110, fg_color="#444444", hover_color="#222222", command=self.modificar).grid(row=0, column=1, padx=6)
        ctk.CTkButton(acciones, text="Eliminar", width=110, fg_color="#7A0000", hover_color="#550000", command=self.eliminar).grid(row=0, column=2, padx=6)

    def _metrica(self, master, columna, titulo):
        master.grid_columnconfigure(columna, weight=1, uniform="metricas")
        tarjeta = ctk.CTkFrame(master, fg_color="#292929", corner_radius=4)
        tarjeta.grid(row=0, column=columna, sticky="nsew", padx=5, pady=8)
        ctk.CTkLabel(tarjeta, text=titulo, font=("Arial", 10, "bold"), text_color="#CCCCCC").pack(anchor="w", padx=12, pady=(8, 0))
        valor = ctk.CTkLabel(tarjeta, text="0", font=("Arial", 20, "bold"), text_color="white")
        valor.pack(anchor="w", padx=12, pady=(2, 8))
        return valor

    def cargar_oportunidades(self):
        texto, estado, proximo = self.buscar.get(), self.estado.get(), self.proximo.get()
        filas = OportunidadService.listar(texto, estado, proximo)
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        for fila in filas:
            nombre = fila[15] or fila[2] or "-"
            self.tabla.insert("", "end", values=(
                fila[0], OportunidadFormWindow.formatear_fecha(fila[6]), nombre,
                fila[8], self.formatear_moneda(fila[9]), f"{float(fila[10] or 0):.0f}%",
                fila[11], OportunidadFormWindow.formatear_fecha(fila[12]), fila[7],
            ))
        datos = OportunidadService.metricas(texto, estado, proximo)
        self.total_label.configure(text=self.formatear_moneda(datos["importe_total"]))
        self.probabilidad_label.configure(text=f"{datos['probabilidad_promedio']:.1f}%")
        self.cantidad_label.configure(text=str(datos["cantidad"]))

    def limpiar_filtros(self):
        self.buscar.delete(0, "end")
        self.estado.set("Todos")
        self.proximo.set("Todos")
        self.cargar_oportunidades()

    def nueva(self):
        OportunidadFormWindow(self, al_guardar=self.cargar_oportunidades)

    def modificar(self):
        oportunidad_id = self.obtener_id_seleccionado()
        if oportunidad_id is None:
            messagebox.showwarning("Oportunidades", "Seleccione una oportunidad.", parent=self)
            return
        OportunidadFormWindow(self, oportunidad_id, self.cargar_oportunidades)

    def eliminar(self):
        oportunidad_id = self.obtener_id_seleccionado()
        if oportunidad_id is None:
            messagebox.showwarning("Oportunidades", "Seleccione una oportunidad.", parent=self)
            return
        if messagebox.askyesno("Oportunidades", "¿Desea eliminar la oportunidad?", parent=self):
            OportunidadService.eliminar(oportunidad_id)
            self.cargar_oportunidades()

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        valores = self.tabla.item(seleccion[0], "values") if seleccion else ()
        return int(valores[0]) if valores else None

    @staticmethod
    def formatear_moneda(valor):
        numero = f"{float(valor or 0):,.2f}"
        return "$ " + numero.replace(",", "X").replace(".", ",").replace("X", ".")
