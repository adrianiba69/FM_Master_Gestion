import customtkinter as ctk

from config import COLOR_NEGRO, COLOR_PRINCIPAL
from database import crear_base
from views.clientes import ClientesFrame


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class FMMasterApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("FM Master Gestion v0.1")
        self.geometry("1200x700")
        self.minsize(1000, 650)
        self.configure(fg_color="white")

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.crear_topbar()
        self.crear_contenedor_principal()
        self.crear_menu_lateral()
        self.crear_panel_principal()
        self.mostrar_inicio()

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
        self.main.grid_columnconfigure(0, weight=0, minsize=220)
        self.main.grid_columnconfigure(1, weight=1)

    def crear_menu_lateral(self):
        self.menu = ctk.CTkFrame(
            self.main,
            width=220,
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
            ("Resumenes", None),
            ("Cobros", None),
            ("Informes", None),
            ("Configuracion", None),
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

        inicio = ctk.CTkFrame(self.panel, fg_color="white", corner_radius=0)
        inicio.grid(row=0, column=0, sticky="nsew")
        inicio.grid_columnconfigure(0, weight=1)

        bienvenida = ctk.CTkLabel(
            inicio,
            text="Bienvenido a FM Master Gestion",
            font=("Arial", 28, "bold"),
            text_color="black"
        )
        bienvenida.grid(row=0, column=0, pady=(40, 10))

        subtitulo = ctk.CTkLabel(
            inicio,
            text="Sistema de administracion de clientes y resumenes",
            font=("Arial", 18),
            text_color="black"
        )
        subtitulo.grid(row=1, column=0)

    def mostrar_clientes(self):
        self.limpiar_panel()

        clientes = ClientesFrame(self.panel)
        clientes.grid(row=0, column=0, sticky="nsew")


if __name__ == "__main__":
    crear_base()
    app = FMMasterApp()
    app.mainloop()
