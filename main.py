import customtkinter as ctk
from tkinter import messagebox, ttk

from config import COLOR_NEGRO, COLOR_PRINCIPAL
from database import crear_base
from services.backup_service import BackupService
from views.agenda import AgendaFrame
from views.clientes import ClientesFrame
from views.cobros import CobrosFrame
from views.configuracion import ConfiguracionFrame
from views.inicio import InicioFrame
from views.informes import InformesFrame
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
        self.topbar.grid_propagate(False)
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
        self.menu = ctk.CTkFrame(
            self.main,
            width=230,
            fg_color=COLOR_NEGRO,
            corner_radius=0
        )
        self.menu.grid(row=0, column=0, sticky="nsw")
        self.menu.grid_propagate(False)
        self.menu.grid_columnconfigure(0, weight=1)

        self.botones_menu = {}
        botones = [
            ("Inicio", self.mostrar_inicio),
            ("Clientes", self.mostrar_clientes),
            ("Agenda", self.mostrar_agenda),
            ("Resumenes", self.mostrar_resumenes),
            ("Cobros", self.mostrar_cobros),
            ("Renovaciones", self.mostrar_renovaciones),
            ("Informes", self.mostrar_informes),
            ("Configuracion", self.mostrar_configuracion),
        ]

        for fila, (texto, comando) in enumerate(botones):
            boton = ctk.CTkButton(
                self.menu,
                text=texto,
                height=45,
                fg_color="#222222",
                hover_color=COLOR_PRINCIPAL,
                anchor="w",
                command=comando,
            )
            boton.grid(row=fila, column=0, sticky="ew", padx=10, pady=(10 if fila == 0 else 6, 0))
            self.botones_menu[texto] = boton

    def crear_panel_principal(self):
        self.panel = ctk.CTkFrame(self.main, fg_color="white", corner_radius=0)
        self.panel.grid(row=0, column=1, sticky="nsew")
        self.panel.grid_rowconfigure(0, weight=1)
        self.panel.grid_columnconfigure(0, weight=1)

    def limpiar_panel(self):
        for widget in self.panel.winfo_children():
            widget.destroy()

    def mostrar_inicio(self):
        self.limpiar_panel()

        inicio = InicioFrame(self.panel)
        inicio.grid(row=0, column=0, sticky="nsew")

    def mostrar_clientes(self):
        self.limpiar_panel()

        clientes = ClientesFrame(self.panel)
        clientes.grid(row=0, column=0, sticky="nsew")

    def mostrar_resumenes(self, cliente_id=None):
        self.limpiar_panel()

        resumenes = ResumenesFrame(self.panel, cliente_id=cliente_id)
        resumenes.grid(row=0, column=0, sticky="nsew")

    def mostrar_cobros(self, cliente_id=None):
        self.limpiar_panel()

        cobros = CobrosFrame(self.panel, cliente_id=cliente_id)
        cobros.grid(row=0, column=0, sticky="nsew")

    def mostrar_configuracion(self):
        self.limpiar_panel()

        configuracion = ConfiguracionFrame(self.panel)
        configuracion.grid(row=0, column=0, sticky="nsew")

    def mostrar_renovaciones(self):
        self.limpiar_panel()

        renovaciones = RenovacionesFrame(self.panel)
        renovaciones.grid(row=0, column=0, sticky="nsew")

    def mostrar_agenda(self, cliente_id=None, nueva_tarea=False):
        self.limpiar_panel()

        agenda = AgendaFrame(
            self.panel,
            cliente_id=cliente_id,
            abrir_nueva=nueva_tarea,
        )
        agenda.grid(row=0, column=0, sticky="nsew")

    def mostrar_informes(self):
        self.limpiar_panel()

        informes = InformesFrame(self.panel)
        informes.grid(row=0, column=0, sticky="nsew")


if __name__ == "__main__":
    crear_base()
    backup_automatico = None
    error_backup = None
    try:
        backup_automatico = BackupService.crear_backup_automatico()
    except Exception as error:
        error_backup = str(error)

    app = FMMasterApp()
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
    app.mainloop()
