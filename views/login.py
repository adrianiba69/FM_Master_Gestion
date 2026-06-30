import customtkinter as ctk
from tkinter import messagebox

from services.usuario_service import UsuarioService


class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.transient(master)
        self.grab_set()
        self.title("Login")
        self.geometry("360x200")
        self.resizable(False, False)
        self.usuario = None
        self._crear_interfaz()

    def _crear_interfaz(self):
        ctk.CTkLabel(self, text="INICIAR SESIÓN", font=("Arial", 16, "bold"), text_color="#C00000").pack(pady=(12, 6))
        frame = ctk.CTkFrame(self, fg_color="white")
        frame.pack(fill="both", expand=True, padx=16, pady=6)

        ctk.CTkLabel(frame, text="Usuario:").grid(row=0, column=0, sticky="w", pady=(8, 4))
        self.entry_usuario = ctk.CTkEntry(frame, width=260)
        self.entry_usuario.grid(row=1, column=0, pady=(0, 8))
        ctk.CTkLabel(frame, text="Clave:").grid(row=2, column=0, sticky="w", pady=(4, 4))
        self.entry_clave = ctk.CTkEntry(frame, width=260, show="*")
        self.entry_clave.grid(row=3, column=0, pady=(0, 12))

        botones = ctk.CTkFrame(self, fg_color="white")
        botones.pack(pady=(0, 12))
        ctk.CTkButton(botones, text="Entrar", width=100, fg_color="#C00000", command=self._entrar).grid(row=0, column=0, padx=6)
        ctk.CTkButton(botones, text="Cancelar", width=100, fg_color="#555555", command=self._cancelar).grid(row=0, column=1, padx=6)

        self.bind("<Return>", lambda _e: self._entrar())
        self.bind("<KP_Enter>", lambda _e: self._entrar())
        self.entry_usuario.bind("<Return>", lambda _e: self._entrar())
        self.entry_clave.bind("<Return>", lambda _e: self._entrar())
        self.protocol("WM_DELETE_WINDOW", self._cancelar)
        self.entry_usuario.focus()
        self.focus_force()

    def _entrar(self):
        usuario = self.entry_usuario.get().strip()
        clave = self.entry_clave.get().strip()
        if not usuario or not clave:
            messagebox.showwarning("Login", "Ingrese usuario y clave.", parent=self)
            return
        datos = UsuarioService.autenticar(usuario, clave)
        if not datos:
            messagebox.showerror("Login", "Usuario o clave incorrectos.", parent=self)
            return
        self.usuario = datos
        self.destroy()

    def _cancelar(self):
        self.usuario = None
        self.destroy()
