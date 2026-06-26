import customtkinter as ctk

class ClientesFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white")

        titulo = ctk.CTkLabel(
            self,
            text="👥 Clientes",
            font=("Arial", 28, "bold"),
            text_color="black"
        )
        titulo.pack(pady=20)

        self.buscar = ctk.CTkEntry(
            self,
            width=400,
            placeholder_text="Buscar cliente..."
        )
        self.buscar.pack(pady=10)

        self.lista = ctk.CTkTextbox(
            self,
            width=900,
            height=350
        )
        self.lista.pack(padx=20, pady=20)

        self.lista.insert("end", "Todavía no hay clientes cargados.")

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(pady=10)

        ctk.CTkButton(botones, text="Nuevo", width=120).pack(side="left", padx=5)
        ctk.CTkButton(botones, text="Guardar", width=120).pack(side="left", padx=5)
        ctk.CTkButton(botones, text="Modificar", width=120).pack(side="left", padx=5)
        ctk.CTkButton(botones, text="Eliminar", width=120).pack(side="left", padx=5)