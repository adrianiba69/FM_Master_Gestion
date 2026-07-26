import customtkinter as ctk
from tkinter import messagebox, ttk

from config import COLOR_NEGRO, COLOR_PRINCIPAL
from database import crear_base
from services.backup_service import BackupService
from services.notificacion_service import NotificacionService
from services.usuario_service import UsuarioService
from views.agenda import AgendaFrame
from views.usuarios import UsuariosFrame
from views.ayuda import AyudaFrame
from views.clientes import ClientesFrame
from views.cobros import CobrosFrame
from views.cierre_mensual import CierreMensualFrame
from views.configuracion import ConfiguracionFrame
from views.estadisticas import EstadisticasFrame
from views.facturas_electronicas import FacturasElectronicasFrame
from views.facturacion_arca import FacturacionArcaFrame
from views.inicio import InicioFrame
from views.informes import InformesFrame
from views.notificaciones import NotificacionesFrame
from views.oportunidades import OportunidadesFrame
from views.renovaciones import RenovacionesFrame
from views.resumenes import ResumenesFrame


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class FMMasterApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("FM Master Gestion")
        self.geometry("1280x760")
        self.minsize(1050, 680)
        self.configure(fg_color="white")

        self.configurar_estilos()

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.crear_topbar()
        self.crear_contenedor_principal()
        self.crear_menu_lateral()
        self.crear_panel_principal()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.mostrar_inicio()

    def configurar_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure(
            "Treeview",
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#222222",
            rowheight=30,
            font=("Arial", 10),
            borderwidth=0,
        )
        estilo.configure(
            "Treeview.Heading",
            background="#1B1B1B",
            foreground="#FFFFFF",
            font=("Arial", 10, "bold"),
            relief="flat",
            padding=(7, 8),
        )
        estilo.map(
            "Treeview",
            background=[("selected", "#C00000")],
            foreground=[("selected", "#FFFFFF")],
        )
        estilo.map(
            "Treeview.Heading",
            background=[("active", "#C00000")],
        )
        estilo.configure("TNotebook", background="#FFFFFF", borderwidth=0)
        estilo.configure(
            "TNotebook.Tab",
            font=("Arial", 10, "bold"),
            padding=(14, 8),
        )
        estilo.map(
            "TNotebook.Tab",
            background=[("selected", "#C00000")],
            foreground=[("selected", "#FFFFFF")],
        )

    def crear_topbar(self):
        self.topbar = ctk.CTkFrame(
            self,
            height=60,
            fg_color=COLOR_PRINCIPAL,
            corner_radius=0
        )

        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)

        titulo = ctk.CTkLabel(
            self.topbar,
            text="FM MASTER GESTION",
            text_color="white",
            font=("Arial", 24, "bold")
        )

        titulo.grid(row=0, column=0, sticky="nsew", pady=12)

    def crear_contenedor_principal(self):
        self.main = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        self.main.grid(row=1, column=0, sticky="nsew")
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=0, minsize=230)
        self.main.grid_columnconfigure(1, weight=1)

    def crear_menu_lateral(self):
        self.menu = ctk.CTkScrollableFrame(
            self.main,
            width=230,
            fg_color=COLOR_NEGRO,
            corner_radius=0,
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#444444",
        )
        self.menu.grid(row=0, column=0, sticky="nsew")
        self.menu.grid_columnconfigure(0, weight=1)

        self.botones_menu = {}
        botones = [
            ("Inicio", self.mostrar_inicio),
            ("Clientes", self.mostrar_clientes),
            ("Agenda", self.mostrar_agenda),
            ("Resúmenes", self.mostrar_resumenes),
            ("Facturas Electrónicas", self.mostrar_facturas_electronicas),
            ("Cobros", self.mostrar_cobros),
            ("Renovaciones", self.mostrar_renovaciones),
            ("Informes", self.mostrar_informes),
            ("Usuarios", self.mostrar_usuarios),
            ("Facturación ARCA", self.mostrar_facturacion_arca),
            ("Oportunidades", self.mostrar_oportunidades),
            ("Estadísticas", self.mostrar_estadisticas),
            ("Notificaciones", self.mostrar_notificaciones),
            ("Ayuda", self.mostrar_ayuda),
            ("Configuración", self.mostrar_configuracion),
            ("Cierre del Mes", self.mostrar_cierre_mensual),
        ]

        for fila, (texto, comando) in enumerate(botones):
            boton = ctk.CTkButton(
                self.menu,
                text=texto,
                height=40,
                fg_color="#222222",
                hover_color=COLOR_PRINCIPAL,
                anchor="w",
                command=comando,
            )
            boton.grid(row=fila, column=0, sticky="ew", padx=10, pady=(8 if fila == 0 else 4, 0))
            self.botones_menu[texto] = boton

    def aplicar_permisos(self):
        # Ajusta los botones del menú según el rol del usuario actual
        user = getattr(self, "current_user", None)
        if not user:
            return
        rol = user.get("rol")
        # por defecto habilitados
        for boton in self.botones_menu.values():
            boton.configure(state="normal")
        if rol == "Administrador":
            return
        if rol == "Operador":
            permitidos = {"Clientes", "Resúmenes", "Cobros", "Renovaciones", "Agenda", "Inicio"}
            for nombre, boton in self.botones_menu.items():
                if nombre not in permitidos and nombre != "Ayuda":
                    boton.configure(state="disabled")
            return
        if rol == "Consulta":
            permitidos = {"Inicio", "Informes", "Estadísticas", "Ayuda"}
            for nombre, boton in self.botones_menu.items():
                if nombre not in permitidos:
                    boton.configure(state="disabled")
            return

    def crear_panel_principal(self):
        self.panel = ctk.CTkFrame(self.main, fg_color="white", corner_radius=0)
        self.panel.grid(row=0, column=1, sticky="nsew")
        self.panel.grid_rowconfigure(0, weight=1)
        self.panel.grid_columnconfigure(0, weight=1)

    def limpiar_panel(self):
        for widget in self.panel.winfo_children():
            try:
                widget.destroy()
            except Exception:
                pass

    def mostrar_inicio(self):
        self.limpiar_panel()
        try:
            inicio = InicioFrame(self.panel)
            inicio.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Inicio.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Inicio.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_clientes(self):
        self.limpiar_panel()
        try:
            clientes = ClientesFrame(self.panel)
            clientes.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Clientes.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Clientes.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_resumenes(self, cliente_id=None, on_cambio=None, contexto_facturacion=None):
        self.limpiar_panel()
        try:
            resumenes = ResumenesFrame(
                self.panel,
                cliente_id=cliente_id,
                on_cambio=on_cambio,
                contexto_facturacion=contexto_facturacion,
            )
            resumenes.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Resúmenes.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Resúmenes.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_cobros(self, cliente_id=None):
        self.limpiar_panel()
        try:
            cobros = CobrosFrame(self.panel, cliente_id=cliente_id)
            cobros.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Cobros.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Cobros.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_configuracion(self):
        self.limpiar_panel()
        try:
            configuracion = ConfiguracionFrame(self.panel)
            configuracion.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Configuración.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Configuración.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_usuarios(self):
        self.limpiar_panel()
        try:
            usuarios = UsuariosFrame(self.panel)
            usuarios.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Usuarios.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Usuarios.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_renovaciones(self):
        self.limpiar_panel()
        try:
            renovaciones = RenovacionesFrame(self.panel)
            renovaciones.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Renovaciones.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Renovaciones.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_agenda(self, cliente_id=None, nueva_tarea=False):
        self.limpiar_panel()
        try:
            agenda = AgendaFrame(
                self.panel,
                cliente_id=cliente_id,
                abrir_nueva=nueva_tarea,
            )
            agenda.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Agenda.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Agenda.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_informes(self):
        self.limpiar_panel()
        try:
            informes = InformesFrame(self.panel)
            informes.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Informes.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Informes.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_oportunidades(self):
        self.limpiar_panel()
        try:
            oportunidades = OportunidadesFrame(self.panel)
            oportunidades.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Oportunidades.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Oportunidades.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_estadisticas(self):
        self.limpiar_panel()
        try:
            estadisticas = EstadisticasFrame(self.panel)
            estadisticas.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Estadísticas.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Estadísticas.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_notificaciones(self):
        self.limpiar_panel()
        try:
            notificaciones = NotificacionesFrame(self.panel)
            notificaciones.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Notificaciones.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Notificaciones.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_ayuda(self):
        self.limpiar_panel()
        try:
            ayuda = AyudaFrame(self.panel)
            ayuda.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Ayuda.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Ayuda.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_facturacion_arca(self):
        self.limpiar_panel()
        try:
            facturacion = FacturacionArcaFrame(self.panel)
            facturacion.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Facturación ARCA.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Facturación ARCA.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_facturas_electronicas(self):
        self.limpiar_panel()
        try:
            facturas = FacturasElectronicasFrame(self.panel)
            facturas.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Facturas Electrónicas.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Facturas Electrónicas.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

    def mostrar_cierre_mensual(self):
        self.limpiar_panel()
        try:
            cierre = CierreMensualFrame(self.panel)
            cierre.grid(row=0, column=0, sticky="nsew")
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo cargar Cierre del Mes.\n{error}", parent=self)
            error_label = ctk.CTkLabel(
                self.panel,
                text="Error al cargar Cierre del Mes.",
                text_color="#C00000",
                font=("Arial", 14, "bold"),
            )
            error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)


def iniciar_sesion(app):
    app.current_user = {"usuario": "admin", "rol": "Administrador"}
    app.aplicar_permisos()
    app.deiconify()
    app.state("zoomed")
    app.lift()
    app.focus_force()
    app.update_idletasks()
    return True


def iniciar_servicios_post_login(app):
    backup_automatico = None
    error_backup = None
    try:
        backup_automatico = BackupService.crear_backup_automatico()
    except Exception as error:
        error_backup = str(error)

    error_notificaciones = None
    try:
        NotificacionService.generar_automaticas()
    except Exception as error:
        error_notificaciones = str(error)

    if backup_automatico:
        app.after(
            250,
            lambda ruta=backup_automatico: messagebox.showinfo(
                "Backup automatico",
                f"La copia de seguridad diaria se creo correctamente.\n{ruta}",
                parent=app,
            ),
        )
    elif error_backup:
        app.after(
            250,
            lambda detalle=error_backup: messagebox.showwarning(
                "Backup automatico",
                f"No se pudo crear la copia de seguridad diaria.\n{detalle}",
                parent=app,
            ),
        )
    if error_notificaciones:
        app.after(
            350,
            lambda detalle=error_notificaciones: messagebox.showwarning(
                "Notificaciones",
                f"No se pudieron generar las notificaciones automáticas.\n{detalle}",
                parent=app,
            ),
        )


if __name__ == "__main__":
    crear_base()
    UsuarioService.init_admin_if_missing()

    app = FMMasterApp()
    app.current_user = {"usuario": "admin", "rol": "Administrador"}
    app.aplicar_permisos()
    iniciar_servicios_post_login(app)
    app.deiconify()
    app.state("zoomed")
    app.lift()
    app.focus_force()
    app.update_idletasks()
    app.mainloop()