from datetime import datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from models.cliente import Cliente
from services.cliente_service import ClienteService
from services.contacto_service import ContactoService
from views.crm import CRMWindow
from views.servicios import ServiciosWindow


class ClientesFrame(ctk.CTkFrame):

    CAMPOS_FORMULARIO = [
        ("codigo", "Codigo"),
        ("razon_social", "Razon Social *"),
        ("nombre_comercial", "Nombre Comercial"),
        ("responsable", "Responsable"),
        ("direccion", "Direccion"),
        ("localidad", "Localidad"),
        ("telefono", "Telefono"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("cuit", "CUIT"),
        ("iva", "IVA"),
        ("vencimiento", "Vencimiento"),
        ("estado", "Estado"),
        ("observaciones", "Observaciones"),
    ]

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)

        self.campos_formulario = {}
        self.crear_interfaz()
        self.cargar_clientes()

    def crear_interfaz(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self,
            text="ADMINISTRACION DE CLIENTES",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        )
        titulo.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        barra = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        barra.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        barra.grid_columnconfigure(0, weight=1)

        self.entrada_buscar = ctk.CTkEntry(
            barra,
            placeholder_text="Buscar cliente por razon social...",
            width=340,
        )
        self.entrada_buscar.grid(row=0, column=0, sticky="w")
        self.entrada_buscar.bind("<Return>", lambda _event: self.buscar_clientes())

        boton_buscar = ctk.CTkButton(
            barra,
            text="Buscar",
            width=95,
            height=36,
            command=self.buscar_clientes,
        )
        boton_buscar.grid(row=0, column=1, padx=(10, 0))

        boton_limpiar = ctk.CTkButton(
            barra,
            text="Limpiar",
            width=95,
            height=36,
            fg_color="#555555",
            hover_color="#333333",
            command=self.limpiar_busqueda,
        )
        boton_limpiar.grid(row=0, column=2, padx=(10, 0))

        boton_nuevo = ctk.CTkButton(
            barra,
            text="Nuevo",
            width=95,
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_ventana_nuevo_cliente,
        )
        boton_nuevo.grid(row=1, column=0, sticky="w", pady=(10, 0))

        boton_modificar = ctk.CTkButton(
            barra,
            text="Modificar",
            width=95,
            height=36,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_cliente_seleccionado,
        )
        boton_modificar.grid(row=1, column=1, padx=(10, 0), pady=(10, 0))

        boton_eliminar = ctk.CTkButton(
            barra,
            text="Eliminar",
            width=95,
            height=36,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_cliente_seleccionado,
        )
        boton_eliminar.grid(row=1, column=2, padx=(10, 0), pady=(10, 0))

        boton_servicios = ctk.CTkButton(
            barra,
            text="Servicios",
            width=95,
            height=36,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_servicios_cliente,
        )
        boton_servicios.grid(row=1, column=3, padx=(10, 0), pady=(10, 0))

        boton_resumen = ctk.CTkButton(
            barra,
            text="Generar resumen",
            width=125,
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_resumen_cliente,
        )
        boton_resumen.grid(row=1, column=4, padx=(10, 0), pady=(10, 0))

        boton_cuenta = ctk.CTkButton(
            barra,
            text="Cuenta Corriente",
            width=140,
            height=36,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_cuenta_corriente,
        )
        boton_cuenta.grid(row=1, column=5, padx=(10, 0), pady=(10, 0))

        boton_tarea = ctk.CTkButton(
            barra,
            text="Nueva tarea",
            width=115,
            height=36,
            fg_color="#444444",
            hover_color="#222222",
            command=self.abrir_nueva_tarea,
        )
        boton_tarea.grid(row=2, column=0, sticky="w", pady=(10, 0))

        boton_crm = ctk.CTkButton(
            barra, text="CRM", width=95, height=36,
            fg_color="#C00000", hover_color="#990000",
            command=self.abrir_crm_cliente,
        )
        boton_crm.grid(row=2, column=1, padx=(10, 0), pady=(10, 0))

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = ("id", "codigo", "razon_social", "telefono", "localidad", "estado", "semaforo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=18)

        encabezados = {
            "id": ("ID", 60),
            "codigo": ("Codigo", 100),
            "razon_social": ("Razon Social", 320),
            "telefono": ("Telefono", 150),
            "localidad": ("Localidad", 180),
            "estado": ("Estado", 110),
            "semaforo": ("Semáforo comercial", 145),
        }

        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(columna, width=ancho, anchor="w")

        self.tabla.bind("<Double-1>", lambda _event: self.modificar_cliente_seleccionado())
        self.tabla.tag_configure("verde", foreground="#16823A")
        self.tabla.tag_configure("amarillo", foreground="#B88600")
        self.tabla.tag_configure("rojo", foreground="#C00000")

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll_y.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")

    def cargar_clientes(self):
        self.limpiar_tabla()

        for cliente in ClienteService.listar():
            semaforo = ContactoService.semaforo_cliente(cliente[0])
            self.tabla.insert("", "end", values=(*cliente, semaforo), tags=(semaforo.lower(),))

    def buscar_clientes(self):
        texto = self.entrada_buscar.get().strip()
        clientes = ClienteService.buscar(texto) if texto else ClienteService.listar()

        self.limpiar_tabla()
        for cliente in clientes:
            semaforo = ContactoService.semaforo_cliente(cliente[0])
            self.tabla.insert("", "end", values=(*cliente, semaforo), tags=(semaforo.lower(),))

    def limpiar_busqueda(self):
        self.entrada_buscar.delete(0, "end")
        self.cargar_clientes()

    def limpiar_tabla(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)

    def obtener_id_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return None

        valores = self.tabla.item(seleccion[0], "values")
        if not valores:
            return None

        return int(valores[0])

    def abrir_ventana_nuevo_cliente(self):
        self.abrir_formulario(titulo="Nuevo Cliente", cliente=None)

    def modificar_cliente_seleccionado(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para modificar.")
            return

        datos = ClienteService.obtener(id_cliente)
        if datos is None:
            messagebox.showerror("Error", "No se encontro el cliente seleccionado.")
            self.cargar_clientes()
            return

        cliente = self.crear_cliente_desde_fila(datos)
        self.abrir_formulario(titulo="Modificar Cliente", cliente=cliente)

    def eliminar_cliente_seleccionado(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para eliminar.")
            return

        valores = self.tabla.item(self.tabla.selection()[0], "values")
        nombre = valores[2] if len(valores) > 2 else "seleccionado"
        confirma = messagebox.askyesno(
            "Confirmar eliminacion",
            f"Desea eliminar el cliente '{nombre}'?"
        )

        if not confirma:
            return

        ClienteService.eliminar(id_cliente)
        self.cargar_clientes()

    def abrir_servicios_cliente(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para administrar servicios.")
            return

        valores = self.tabla.item(self.tabla.selection()[0], "values")
        nombre = valores[2] if len(valores) > 2 else "Cliente"
        ServiciosWindow(self, id_cliente, nombre)

    def abrir_resumen_cliente(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para generar el resumen.")
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_resumenes"):
            aplicacion.mostrar_resumenes(cliente_id=id_cliente)

    def abrir_cuenta_corriente(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para ver su cuenta corriente.")
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_cobros"):
            aplicacion.mostrar_cobros(cliente_id=id_cliente)

    def abrir_nueva_tarea(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para crear la tarea.")
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_agenda"):
            aplicacion.mostrar_agenda(cliente_id=id_cliente, nueva_tarea=True)

    def abrir_crm_cliente(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para abrir el CRM.")
            return
        CRMWindow(self, cliente_id=id_cliente)

    def abrir_formulario(self, titulo, cliente=None):
        ventana = ctk.CTkToplevel(self)
        ventana.title(titulo)
        ventana.geometry("650x720")
        ventana.minsize(580, 650)
        ventana.resizable(False, True)
        ventana.transient(self.winfo_toplevel())
        ventana.grab_set()

        contenedor = ctk.CTkScrollableFrame(ventana, fg_color="white")
        contenedor.pack(fill="both", expand=True, padx=20, pady=20)
        contenedor.grid_columnconfigure(0, weight=1)

        etiqueta_titulo = ctk.CTkLabel(
            contenedor,
            text=titulo,
            font=("Arial", 22, "bold"),
            text_color="#C00000",
        )
        etiqueta_titulo.grid(row=0, column=0, sticky="w", pady=(0, 10))

        if cliente is not None:
            semaforo = ContactoService.semaforo_cliente(cliente.id)
            colores = {"Verde": "#16823A", "Amarillo": "#B88600", "Rojo": "#C00000"}
            ctk.CTkLabel(
                contenedor, text=f"SEMÁFORO COMERCIAL: {semaforo.upper()}",
                font=("Arial", 12, "bold"), text_color=colores[semaforo],
            ).grid(row=0, column=0, sticky="e", pady=(0, 10))

        self.campos_formulario = {}
        for fila, (clave, etiqueta) in enumerate(self.CAMPOS_FORMULARIO, start=1):
            label = ctk.CTkLabel(contenedor, text=etiqueta, anchor="w")
            label.grid(row=fila * 2 - 1, column=0, sticky="ew", pady=(8, 0))

            entrada = ctk.CTkEntry(contenedor)
            entrada.grid(row=fila * 2, column=0, sticky="ew")
            self.campos_formulario[clave] = entrada

        if cliente is None:
            self.campos_formulario["vencimiento"].insert(0, "1")
            self.campos_formulario["estado"].insert(0, "Activo")
        else:
            self.cargar_datos_en_formulario(cliente)

        boton_guardar = ctk.CTkButton(
            contenedor,
            text="Guardar",
            height=40,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.guardar_formulario(ventana, cliente),
        )
        boton_guardar.grid(row=len(self.CAMPOS_FORMULARIO) * 2 + 1, column=0, sticky="ew", pady=20)

        self.campos_formulario["razon_social"].focus_set()

    def cargar_datos_en_formulario(self, cliente):
        valores = {
            "codigo": cliente.codigo,
            "razon_social": cliente.razon_social,
            "nombre_comercial": cliente.nombre_comercial,
            "responsable": cliente.responsable,
            "direccion": cliente.direccion,
            "localidad": cliente.localidad,
            "telefono": cliente.telefono,
            "whatsapp": cliente.whatsapp,
            "email": cliente.email,
            "cuit": cliente.cuit,
            "iva": cliente.iva,
            "vencimiento": str(cliente.vencimiento or 1),
            "estado": cliente.estado or "Activo",
            "observaciones": cliente.observaciones,
        }

        for clave, valor in valores.items():
            self.campos_formulario[clave].insert(0, valor or "")

    def guardar_formulario(self, ventana, cliente_original=None):
        razon_social = self.obtener_campo("razon_social")
        if not razon_social:
            messagebox.showerror("Error", "La razon social es obligatoria.")
            return

        try:
            vencimiento = int(self.obtener_campo("vencimiento") or 1)
        except ValueError:
            messagebox.showerror("Error", "El vencimiento debe ser numerico.")
            return

        ahora = datetime.now().strftime("%d/%m/%Y")
        cliente = Cliente(
            id=cliente_original.id if cliente_original else None,
            codigo=self.obtener_campo("codigo"),
            razon_social=razon_social,
            nombre_comercial=self.obtener_campo("nombre_comercial"),
            responsable=self.obtener_campo("responsable"),
            direccion=self.obtener_campo("direccion"),
            localidad=self.obtener_campo("localidad"),
            telefono=self.obtener_campo("telefono"),
            whatsapp=self.obtener_campo("whatsapp"),
            email=self.obtener_campo("email"),
            cuit=self.obtener_campo("cuit"),
            iva=self.obtener_campo("iva"),
            vencimiento=vencimiento,
            estado=self.obtener_campo("estado") or "Activo",
            observaciones=self.obtener_campo("observaciones"),
            fecha_alta=cliente_original.fecha_alta if cliente_original else ahora,
            fecha_modificacion=ahora,
        )

        if cliente_original:
            ClienteService.actualizar(cliente)
        else:
            ClienteService.guardar(cliente)

        ventana.destroy()
        self.cargar_clientes()
        messagebox.showinfo(
            "Clientes",
            "Cliente modificado correctamente."
            if cliente_original
            else "Cliente creado correctamente.",
            parent=self,
        )

    def crear_cliente_desde_fila(self, fila):
        return Cliente(
            id=fila[0],
            codigo=fila[1] or "",
            razon_social=fila[2] or "",
            nombre_comercial=fila[3] or "",
            responsable=fila[4] or "",
            direccion=fila[5] or "",
            localidad=fila[6] or "",
            telefono=fila[7] or "",
            whatsapp=fila[8] or "",
            email=fila[9] or "",
            cuit=fila[10] or "",
            iva=fila[11] or "",
            vencimiento=fila[12] or 1,
            estado=fila[13] or "Activo",
            observaciones=fila[14] or "",
            fecha_alta=fila[15] or "",
            fecha_modificacion=fila[16] or "",
        )

    def obtener_campo(self, clave):
        return self.campos_formulario[clave].get().strip()
