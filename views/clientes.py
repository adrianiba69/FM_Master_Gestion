from datetime import datetime
import os
import re
import webbrowser
from types import MethodType
from tkinter import TclError, messagebox, ttk

import customtkinter as ctk

from models.cliente import Cliente
from services.cliente_service import ClienteService
from services.contacto_service import ContactoService
from services.emisor_fiscal_service import EmisorFiscalService
from runtime_paths import EXPORTS_DIR
from views.cobros import CobrosFrame
from views.cliente_ficha import FichaClienteFrame
from views.crm import CRMWindow
from views.servicios import ServiciosWindow


class ClientesFrame(ctk.CTkFrame):

    IVA_OPCIONES = [
        "Monotributo",
        "Responsable Inscripto",
        "Consumidor Final",
        "Exento",
        "Otro",
    ]
    TIPO_FACTURA_OPCIONES = ["Factura A", "Factura C", "No factura"]
    EMISOR_FACTURACION_DEFAULT = ["No aplica"]
    MODALIDAD_COMPROBANTE_OPCIONES = [
        "Solo Resumen",
        "Resumen + Factura",
        "Solo Factura",
    ]
    EMISOR_HABITUAL_OPCIONES = [
        "FM Master 98.3",
        "Publicidad & Servicios",
        "Publicidad & Servicios S.H.",
    ]

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
        ("tipo_factura", "Tipo de Factura"),
        ("monotributo_facturacion", "Emisor Fiscal"),
        ("modalidad_comprobante", "Modalidad de Comprobante"),
        ("emisor_habitual", "Emisor Habitual"),
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
            text="CLIENTES",
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
            width=430,
        )
        self.entrada_buscar.grid(row=0, column=0, sticky="w")
        self.entrada_buscar.bind("<Return>", lambda _event: self.buscar_clientes())

        boton_buscar = ctk.CTkButton(
            barra,
            text="Buscar",
            width=105,
            height=36,
            command=self.buscar_clientes,
        )
        boton_buscar.grid(row=0, column=1, padx=(10, 0))

        boton_limpiar = ctk.CTkButton(
            barra,
            text="Limpiar",
            width=105,
            height=36,
            fg_color="#555555",
            hover_color="#333333",
            command=self.limpiar_busqueda,
        )
        boton_limpiar.grid(row=0, column=2, padx=(10, 0))

        boton_nuevo = ctk.CTkButton(
            barra,
            text="Nuevo",
            width=110,
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.abrir_ventana_nuevo_cliente,
        )
        boton_nuevo.grid(row=1, column=0, sticky="w", pady=(10, 0))

        boton_modificar = ctk.CTkButton(
            barra,
            text="Modificar",
            width=110,
            height=36,
            fg_color="#444444",
            hover_color="#222222",
            command=self.modificar_cliente_seleccionado,
        )
        boton_modificar.grid(row=1, column=1, padx=(10, 0), pady=(10, 0))

        boton_eliminar = ctk.CTkButton(
            barra,
            text="Eliminar",
            width=110,
            height=36,
            fg_color="#7A0000",
            hover_color="#550000",
            command=self.eliminar_cliente_seleccionado,
        )
        boton_eliminar.grid(row=1, column=2, padx=(10, 0), pady=(10, 0))

        boton_servicios = ctk.CTkButton(
            barra,
            text="Servicios",
            width=110,
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

        boton_contactos = ctk.CTkButton(
            barra,
            text="Listado contactos",
            width=150,
            height=36,
            fg_color="#333333",
            hover_color="#111111",
            command=self.generar_listado_contactos,
        )
        boton_contactos.grid(row=2, column=2, padx=(10, 0), pady=(10, 0), sticky="w")

        tabla_frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        tabla_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        tabla_frame.grid_rowconfigure(0, weight=1)
        tabla_frame.grid_rowconfigure(1, weight=0)
        tabla_frame.grid_columnconfigure(0, weight=1)

        columnas = ("id", "codigo", "razon_social", "telefono", "localidad", "estado", "semaforo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings", height=18)

        encabezados = {
            "id": ("ID", 52),
            "codigo": ("Codigo", 110),
            "razon_social": ("Razon Social", 360),
            "telefono": ("Telefono", 165),
            "localidad": ("Localidad", 190),
            "estado": ("Estado", 100),
            "semaforo": ("Semáforo comercial", 170),
        }

        for columna, (texto, ancho) in encabezados.items():
            self.tabla.heading(columna, text=texto)
            self.tabla.column(
                columna,
                width=ancho,
                anchor="w",
                stretch=columna in ("razon_social", "localidad"),
            )

        self.tabla.bind("<Double-1>", lambda _event: self.abrir_ficha_cliente())
        self.tabla.tag_configure("verde", foreground="#16823A")
        self.tabla.tag_configure("amarillo", foreground="#B88600")
        self.tabla.tag_configure("rojo", foreground="#C00000")

        scroll_y = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(tabla_frame, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

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

    def abrir_ficha_cliente(self):
        id_cliente = self.obtener_id_seleccionado()
        if id_cliente is None:
            messagebox.showwarning("Atencion", "Seleccione un cliente para abrir la ficha.")
            return

        ventana = ctk.CTkToplevel(self)
        ventana.title("Ficha Única del Cliente")
        ventana.geometry("1320x820")
        ventana.minsize(1080, 700)
        ventana.transient(self.winfo_toplevel())

        callbacks = {}
        ficha = FichaClienteFrame(ventana, cliente_data=id_cliente, callbacks=callbacks)

        def refrescar_ficha_si_disponible():
            try:
                if not ficha.winfo_exists():
                    return
                toplevel_ficha = ficha.winfo_toplevel()
                if toplevel_ficha is None or not toplevel_ficha.winfo_exists():
                    return
            except TclError:
                return
            ficha.cargar_cliente(id_cliente)

        callbacks["nuevo_resumen"] = lambda _cliente_data: self._abrir_resumenes_desde_ficha(
            id_cliente,
            parent_toplevel=ficha.winfo_toplevel(),
            on_cambio=refrescar_ficha_si_disponible,
        )
        callbacks["editar_cliente"] = lambda _cliente_data: self._editar_cliente_desde_ficha(
            id_cliente,
            on_guardado=lambda: ficha.cargar_cliente(id_cliente),
        )
        callbacks["registrar_cobro"] = lambda _cliente_data: self._abrir_cobros_desde_ficha(
            id_cliente,
            parent_toplevel=ficha.winfo_toplevel(),
            on_cambio=lambda: ficha.cargar_cliente(id_cliente),
        )
        callbacks["nueva_tarea"] = lambda _cliente_data: self._abrir_nueva_tarea_desde_ficha(
            id_cliente,
            parent_toplevel=ficha.winfo_toplevel(),
            on_guardado=lambda: ficha.cargar_cliente(id_cliente),
        )
        callbacks["whatsapp"] = lambda _cliente_data: self._abrir_whatsapp_desde_ficha(id_cliente)
        ficha.pack(fill="both", expand=True)

    def _editar_cliente_desde_ficha(self, id_cliente, on_guardado=None):
        datos = ClienteService.obtener(id_cliente)
        if datos is None:
            messagebox.showerror("Error", "No se encontro el cliente seleccionado.")
            self.cargar_clientes()
            return

        cliente = self.crear_cliente_desde_fila(datos)
        self.abrir_formulario(
            titulo="Modificar Cliente",
            cliente=cliente,
            on_guardado=on_guardado,
        )

    def _abrir_resumenes_desde_ficha(self, id_cliente, parent_toplevel=None, on_cambio=None):
        self._abrir_resumenes_para_cliente(
            id_cliente=id_cliente,
            parent_toplevel=parent_toplevel,
            on_cambio=on_cambio,
            origen_creacion="clientes._abrir_resumenes_desde_ficha",
        )

    def _abrir_resumenes_para_cliente(self, id_cliente, parent_toplevel=None, on_cambio=None, origen_creacion="clientes._abrir_resumenes_para_cliente"):
        try:
            id_cliente_int = int(id_cliente)
        except (TypeError, ValueError):
            messagebox.showerror("Error", "No se pudo identificar el cliente seleccionado.")
            return

        fila_cliente = ClienteService.obtener(id_cliente_int)
        if fila_cliente is None:
            messagebox.showerror("Error", "No se encontró el cliente seleccionado.")
            return

        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_resumenes"):
            aplicacion.mostrar_resumenes(
                cliente_id=id_cliente_int,
                on_cambio=on_cambio,
                origen_creacion=origen_creacion,
            )
            aplicacion.lift()
            aplicacion.focus_force()

        if parent_toplevel is not None:
            try:
                if parent_toplevel.winfo_exists():
                    parent_toplevel.lower()
            except TclError:
                pass

    def _abrir_nueva_tarea_desde_ficha(self, id_cliente, parent_toplevel=None, on_guardado=None):
        aplicacion = self.winfo_toplevel()
        if hasattr(aplicacion, "mostrar_agenda"):
            aplicacion.mostrar_agenda(cliente_id=id_cliente, nueva_tarea=True)
            aplicacion.lift()
            aplicacion.focus_force()

            panel = getattr(aplicacion, "panel", None)
            agenda_frame = None
            if panel is not None and hasattr(panel, "winfo_children"):
                for child in panel.winfo_children():
                    if hasattr(child, "guardar_formulario") and hasattr(child, "abrir_nueva_tarea"):
                        agenda_frame = child
                        break

            if agenda_frame is not None and callable(on_guardado):
                self._instalar_hook_refresco_ficha_en_agenda(agenda_frame, on_guardado)

        if parent_toplevel is not None and hasattr(parent_toplevel, "lift"):
            parent_toplevel.lower()

    @staticmethod
    def _instalar_hook_refresco_ficha_en_agenda(agenda_frame, on_guardado):
        agenda_frame._ficha_on_guardado = on_guardado
        if getattr(agenda_frame, "_ficha_refresh_hook_instalado", False):
            return

        guardar_original = agenda_frame.guardar_formulario

        def guardar_formulario_con_refresco(self, ventana, tarea_original=None):
            guardar_original(ventana, tarea_original)
            if callable(getattr(self, "_ficha_on_guardado", None)) and not ventana.winfo_exists():
                self._ficha_on_guardado()

        agenda_frame.guardar_formulario = MethodType(guardar_formulario_con_refresco, agenda_frame)
        agenda_frame._ficha_refresh_hook_instalado = True

    def _abrir_whatsapp_desde_ficha(self, id_cliente):
        datos = ClienteService.obtener(id_cliente)
        if datos is None:
            messagebox.showerror("Error", "No se encontro el cliente seleccionado.")
            self.cargar_clientes()
            return

        numero_limpio = self._limpiar_numero_whatsapp(datos[8] or "")
        if not numero_limpio:
            messagebox.showwarning("WhatsApp", "El cliente no tiene WhatsApp cargado.")
            return

        url_desktop = f"whatsapp://send?phone={numero_limpio}"
        url_web = f"https://wa.me/{numero_limpio}"

        try:
            if hasattr(os, "startfile"):
                os.startfile(url_desktop)
                return

            abierto_desktop = webbrowser.open(url_desktop, new=0, autoraise=True)
            if abierto_desktop:
                return
        except (webbrowser.Error, OSError):
            pass

        webbrowser.open(url_web, new=0, autoraise=True)

    @staticmethod
    def _limpiar_numero_whatsapp(numero):
        return re.sub(r"\D", "", (numero or "").strip())

    def _abrir_cobros_desde_ficha(self, id_cliente, parent_toplevel=None, on_cambio=None):
        ventana = ctk.CTkToplevel(self)
        ventana.title("Cuenta Corriente y Cobros")
        ventana.geometry("1280x820")
        ventana.minsize(1080, 700)
        if parent_toplevel is not None:
            ventana.transient(parent_toplevel)
        else:
            ventana.transient(self.winfo_toplevel())
        ventana.lift()
        ventana.focus_force()
        ventana.grab_set()

        cobros = CobrosFrame(ventana, cliente_id=id_cliente, on_cambio=on_cambio)
        cobros.pack(fill="both", expand=True)

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

        self._abrir_resumenes_para_cliente(
            id_cliente=id_cliente,
            parent_toplevel=None,
            on_cambio=None,
            origen_creacion="clientes.abrir_resumen_cliente",
        )

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

    def generar_listado_contactos(self):
        try:
            contactos = ClienteService.listar_contactos()
        except Exception as error:
            messagebox.showerror(
                "Listado de contactos",
                f"No se pudo generar el listado.\n\nDetalle: {error}",
                parent=self,
            )
            return

        if not contactos:
            messagebox.showinfo(
                "Listado de contactos",
                "No hay clientes para incluir en el listado.",
                parent=self,
            )
            return

        destino_dir = EXPORTS_DIR / "estadisticas"
        destino_dir.mkdir(parents=True, exist_ok=True)
        marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M")
        destino = destino_dir / f"listado_contactos_{marca_tiempo}.txt"

        lineas = [
            "FM MASTER GESTION - LISTADO DE CONTACTOS",
            f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            "",
            "CODIGO | RAZON SOCIAL | TELEFONO | WHATSAPP",
            "-" * 100,
        ]

        for _, codigo, razon_social, telefono, whatsapp in contactos:
            lineas.append(
                " | ".join([
                    (codigo or "-").strip(),
                    (razon_social or "-").strip(),
                    (telefono or "-").strip(),
                    (whatsapp or "-").strip(),
                ])
            )

        try:
            destino.write_text("\n".join(lineas), encoding="utf-8")
        except OSError as error:
            messagebox.showerror(
                "Listado de contactos",
                f"No se pudo guardar el archivo.\n\nDetalle: {error}",
                parent=self,
            )
            return

        abrir_ahora = messagebox.askyesno(
            "Listado de contactos",
            f"Listado generado en:\n{destino}\n\n¿Desea abrirlo ahora para imprimir?",
            parent=self,
        )
        if abrir_ahora:
            try:
                os.startfile(str(destino))
            except OSError:
                messagebox.showwarning(
                    "Listado de contactos",
                    "No se pudo abrir automaticamente el archivo.",
                    parent=self,
                )

    def abrir_formulario(self, titulo, cliente=None, on_guardado=None):
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
        emisores_fiscales = self.obtener_opciones_emisor_fiscal()
        campos_opciones = {
            "iva": self.IVA_OPCIONES,
            "tipo_factura": self.TIPO_FACTURA_OPCIONES,
            "monotributo_facturacion": emisores_fiscales,
            "modalidad_comprobante": self.MODALIDAD_COMPROBANTE_OPCIONES,
            "emisor_habitual": self.EMISOR_HABITUAL_OPCIONES,
        }
        for fila, (clave, etiqueta) in enumerate(self.CAMPOS_FORMULARIO, start=1):
            label = ctk.CTkLabel(contenedor, text=etiqueta, anchor="w")
            label.grid(row=fila * 2 - 1, column=0, sticky="ew", pady=(8, 0))

            if clave in campos_opciones:
                entrada = ctk.CTkOptionMenu(
                    contenedor,
                    values=campos_opciones[clave],
                    fg_color="white",
                    button_color="#C00000",
                    button_hover_color="#990000",
                    text_color="#1F1F1F",
                )
            else:
                entrada = ctk.CTkEntry(contenedor)

            entrada.grid(row=fila * 2, column=0, sticky="ew")
            self.campos_formulario[clave] = entrada

        if cliente is None:
            self.set_campo("iva", "Otro")
            self.set_campo("tipo_factura", "No factura")
            self.set_campo("monotributo_facturacion", "No aplica")
            self.set_campo("modalidad_comprobante", "Solo Resumen")
            self.set_campo("emisor_habitual", "FM Master 98.3")
            self.set_campo("vencimiento", "1")
            self.set_campo("estado", "Activo")
        else:
            self.cargar_datos_en_formulario(cliente)

        boton_guardar = ctk.CTkButton(
            contenedor,
            text="Guardar",
            height=40,
            fg_color="#C00000",
            hover_color="#990000",
            command=lambda: self.guardar_formulario(ventana, cliente, on_guardado),
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
            "iva": cliente.iva or "Otro",
            "tipo_factura": cliente.tipo_factura or "No factura",
            "monotributo_facturacion": EmisorFiscalService.resolver_etiqueta(cliente.monotributo_facturacion),
            "modalidad_comprobante": cliente.modalidad_comprobante or "Solo Resumen",
            "emisor_habitual": cliente.emisor_habitual or "FM Master 98.3",
            "vencimiento": str(cliente.vencimiento or 1),
            "estado": cliente.estado or "Activo",
            "observaciones": cliente.observaciones,
        }

        for clave, valor in valores.items():
            self.set_campo(clave, valor or "")

    def guardar_formulario(self, ventana, cliente_original=None, on_guardado=None):
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
            tipo_factura=self.obtener_campo("tipo_factura") or "No factura",
            monotributo_facturacion=EmisorFiscalService.codificar_seleccion(
                self.obtener_campo("monotributo_facturacion") or "No aplica"
            ),
            modalidad_comprobante=self.obtener_campo("modalidad_comprobante") or "Solo Resumen",
            emisor_habitual=self.obtener_campo("emisor_habitual") or "FM Master 98.3",
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
        if callable(on_guardado):
            on_guardado()
        messagebox.showinfo(
            "Clientes",
            "Cliente modificado correctamente."
            if cliente_original
            else "Cliente creado correctamente.",
            parent=self,
        )

    def crear_cliente_desde_fila(self, fila):
        def valor(indice, por_defecto=""):
            if indice < len(fila):
                return fila[indice]
            return por_defecto

        return Cliente(
            id=valor(0),
            codigo=valor(1) or "",
            razon_social=valor(2) or "",
            nombre_comercial=valor(3) or "",
            responsable=valor(4) or "",
            direccion=valor(5) or "",
            localidad=valor(6) or "",
            telefono=valor(7) or "",
            whatsapp=valor(8) or "",
            email=valor(9) or "",
            cuit=valor(10) or "",
            iva=valor(11) or "Otro",
            tipo_factura=valor(12) or "No factura",
            monotributo_facturacion=valor(13) or "No aplica",
            modalidad_comprobante=valor(21) or "Solo Resumen",
            emisor_habitual=valor(22) or "FM Master 98.3",
            vencimiento=valor(16, 1) or 1,
            estado=valor(17, "Activo") or "Activo",
            observaciones=valor(18) or "",
            fecha_alta=valor(19) or "",
            fecha_modificacion=valor(20) or "",
        )

    def set_campo(self, clave, valor):
        campo = self.campos_formulario.get(clave)
        if campo is None:
            return

        if isinstance(campo, ctk.CTkEntry):
            campo.delete(0, "end")
            campo.insert(0, valor)
            return

        if isinstance(campo, ctk.CTkOptionMenu):
            valores = list(campo.cget("values") or [])
            if valor and valor not in valores:
                valores.append(valor)
                campo.configure(values=valores)
            campo.set(valor)

    def obtener_opciones_emisor_fiscal(self):
        opciones = ["No aplica"]
        try:
            emisores = EmisorFiscalService.listar_activos()
        except Exception:
            emisores = []

        for emisor in emisores:
            nombre = EmisorFiscalService.etiqueta_visible(emisor)
            if nombre and nombre not in opciones:
                opciones.append(nombre)

        if not opciones:
            return ["No aplica"]
        return opciones

    def obtener_campo(self, clave):
        return self.campos_formulario[clave].get().strip()
