import customtkinter as ctk
from tkinter import messagebox

from services.catalogo_service import CatalogoService


class CatalogoEditor(ctk.CTkToplevel):
    def __init__(self, master, catalogo_id=None, on_guardar=None):
        super().__init__(master)
        self.catalogo_id = catalogo_id
        self.on_guardar = on_guardar
        self.title("Editor de servicio")
        self.geometry("520x320")
        self.transient(master)
        self.grab_set()
        self.crear_interfaz()
        if catalogo_id:
            self.cargar()

    def crear_interfaz(self):
        frame = ctk.CTkFrame(self, fg_color="white")
        frame.pack(fill="both", expand=True, padx=16, pady=12)

        ctk.CTkLabel(frame, text="Nombre").pack(anchor="w")
        self.nombre = ctk.CTkEntry(frame)
        self.nombre.pack(fill="x")

        ctk.CTkLabel(frame, text="Descripcion").pack(anchor="w", pady=(8,0))
        self.descripcion = ctk.CTkEntry(frame)
        self.descripcion.pack(fill="x")

        ctk.CTkLabel(frame, text="Precio").pack(anchor="w", pady=(8,0))
        self.precio = ctk.CTkEntry(frame)
        self.precio.pack(fill="x")

        self.activo_var = ctk.IntVar(value=1)
        ctk.CTkCheckBox(frame, text="Activo", variable=self.activo_var).pack(anchor="w", pady=(8,0))

        botones = ctk.CTkFrame(frame, fg_color="transparent")
        botones.pack(fill="x", pady=(12,0))
        ctk.CTkButton(botones, text="Guardar", fg_color="#C00000", command=self.guardar).pack(side="right")

    def cargar(self):
        fila = CatalogoService.obtener(self.catalogo_id)
        if not fila:
            messagebox.showerror("Error", "No se encontro el servicio.", parent=self)
            self.destroy()
            return
        self.nombre.insert(0, fila[1])
        self.descripcion.insert(0, fila[2] or "")
        self.precio.insert(0, str(fila[3] or 0))
        self.activo_var.set(1 if fila[4] else 0)

    def guardar(self):
        nombre = self.nombre.get().strip()
        descripcion = self.descripcion.get().strip()
        try:
            precio = float(self.precio.get() or 0)
        except ValueError:
            messagebox.showerror("Error", "Precio invalido.", parent=self)
            return
        activo = 1 if self.activo_var.get() else 0
        if not nombre:
            messagebox.showerror("Error", "Nombre es obligatorio.", parent=self)
            return
        if self.catalogo_id:
            CatalogoService.actualizar(self.catalogo_id, nombre, descripcion, precio, activo)
        else:
            CatalogoService.guardar(nombre, descripcion, precio, activo)
        if self.on_guardar:
            self.on_guardar()
        self.destroy()
