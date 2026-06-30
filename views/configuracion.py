from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from services.backup_service import BackupService


class ConfiguracionFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.crear_interfaz()
        self.actualizar_estado()

    def crear_interfaz(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="CONFIGURACION",
            font=("Arial", 26, "bold"),
            text_color="#C00000",
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))

        seccion = ctk.CTkFrame(self, fg_color="#F3F3F3", corner_radius=6)
        seccion.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        seccion.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            seccion,
            text="COPIAS DE SEGURIDAD",
            font=("Arial", 18, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 4))

        self.estado_label = ctk.CTkLabel(
            seccion,
            text="",
            font=("Arial", 13),
            text_color="#555555",
            anchor="w",
            justify="left",
        )
        self.estado_label.grid(row=1, column=0, sticky="ew", padx=18, pady=(4, 2))

        self.ruta_label = ctk.CTkLabel(
            seccion,
            text=str(BackupService.BACKUP_DIR),
            font=("Arial", 11),
            text_color="#666666",
            anchor="w",
        )
        self.ruta_label.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))

        acciones = ctk.CTkFrame(seccion, fg_color="transparent", corner_radius=0)
        acciones.grid(row=3, column=0, sticky="w", padx=18, pady=(0, 18))

        self.boton_crear = ctk.CTkButton(
            acciones,
            text="Crear backup ahora",
            width=170,
            height=40,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.crear_backup_manual,
        )
        self.boton_crear.grid(row=0, column=0, padx=(0, 10))

        self.boton_abrir = ctk.CTkButton(
            acciones,
            text="Abrir carpeta de backups",
            width=205,
            height=40,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_carpeta,
        )
        self.boton_abrir.grid(row=0, column=1)

        self.boton_usuarios = ctk.CTkButton(
            acciones,
            text="Usuarios",
            width=140,
            height=40,
            fg_color="#444444",
            hover_color="#222222",
            command=self.abrir_usuarios,
        )
        self.boton_usuarios.grid(row=0, column=2, padx=(10, 0))

    def actualizar_estado(self):
        ultimo = BackupService.ultimo_backup()
        if ultimo is None:
            self.estado_label.configure(text="Todavia no hay backups registrados.")
            return

        fecha = datetime.fromtimestamp(ultimo.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        self.estado_label.configure(
            text=f"Ultimo backup: {ultimo.name}  |  {fecha}"
        )

    def crear_backup_manual(self):
        try:
            ruta = BackupService.crear_backup()
        except Exception as error:
            messagebox.showerror("Backup", f"No se pudo crear el backup.\n{error}", parent=self)
            return

        self.actualizar_estado()
        messagebox.showinfo(
            "Backup creado",
            f"La copia de seguridad se creo correctamente.\n{ruta}",
            parent=self,
        )

    def abrir_carpeta(self):
        try:
            BackupService.abrir_carpeta()
        except OSError as error:
            messagebox.showerror("Backups", str(error), parent=self)

    def abrir_usuarios(self):
        try:
            from views.usuarios import UsuariosFrame
        except Exception as error:
            messagebox.showerror("Usuarios", f"No se pudo abrir la gestión de usuarios.\n{error}", parent=self)
            return
        ventana = ctk.CTkToplevel(self)
        ventana.title("Usuarios")
        ventana.geometry("800x520")
        frame = UsuariosFrame(ventana)
        frame.pack(fill="both", expand=True)
