import customtkinter as ctk
from config import *
from database import crear_base

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class FMMasterApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("FM Master Gestión v0.1")
        self.geometry("1200x700")
        self.minsize(1000, 650)

        # =======================
        # Barra superior
        # =======================

        self.topbar = ctk.CTkFrame(
            self,
            height=60,
            fg_color=COLOR_PRINCIPAL,
            corner_radius=0
        )
        self.topbar.pack(fill="x")

        self.titulo = ctk.CTkLabel(
            self.topbar,
            text="FM MASTER GESTIÓN",
            text_color="white",
            font=("Arial", 24, "bold")
        )

        self.titulo.pack(pady=15)

        # =======================
        # Contenedor principal
        # =======================

        self.main = ctk.CTkFrame(self, fg_color="white")
        self.main.pack(fill="both", expand=True)

        # =======================
        # Menú izquierdo
        # =======================

        self.menu = ctk.CTkFrame(
            self.main,
            width=220,
            fg_color=COLOR_NEGRO,
            corner_radius=0
        )

        self.menu.pack(side="left", fill="y")
        self.menu.pack_propagate(False)

        botones = [
            "🏠 Inicio",
            "👥 Clientes",
            "📄 Resúmenes",
            "💰 Cobros",
            "📊 Informes",
            "⚙ Configuración"
        ]

        for texto in botones:

            boton = ctk.CTkButton(
                self.menu,
                text=texto,
                height=45,
                fg_color="#222222",
                hover_color=COLOR_PRINCIPAL,
                anchor="w"
            )

            boton.pack(fill="x", padx=10, pady=6)

        # =======================
        # Panel principal
        # =======================

        self.panel = ctk.CTkFrame(
            self.main,
            fg_color="white"
        )

        self.panel.pack(side="left", fill="both", expand=True)

        bienvenida = ctk.CTkLabel(
            self.panel,
            text="Bienvenido a FM Master Gestión",
            font=("Arial", 28, "bold"),
            text_color="black"
        )

        bienvenida.pack(pady=40)

        subtitulo = ctk.CTkLabel(
            self.panel,
            text="Sistema de administración de clientes y resúmenes",
            font=("Arial", 18)
        )

        subtitulo.pack()


crear_base()

app = FMMasterApp()
app.mainloop()
