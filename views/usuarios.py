import customtkinter as ctk
from tkinter import messagebox, ttk, simpledialog

from services.usuario_service import UsuarioService


class UsuariosFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self._crear_interfaz()
        self._cargar()

    def _crear_interfaz(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="USUARIOS", font=("Arial", 20, "bold"), text_color="#C00000").grid(row=0, column=0, sticky="w", padx=20, pady=(12, 8))

        marco = ctk.CTkFrame(self, fg_color="white")
        marco.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 12))
        columnas = ("id", "nombre", "usuario", "rol", "activo", "fecha_creacion")
        self.tabla = ttk.Treeview(marco, columns=columnas, show="headings")
        for col in columnas:
            self.tabla.heading(col, text=col.capitalize())
            self.tabla.column(col, width=120, anchor="w")
        self.tabla.column("id", width=40)
        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)

        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 12))
        ctk.CTkButton(acciones, text="Nuevo", fg_color="#16823A", command=self.nuevo).grid(row=0, column=0, padx=6)
        ctk.CTkButton(acciones, text="Editar", fg_color="#444444", command=self.editar).grid(row=0, column=1, padx=6)
        ctk.CTkButton(acciones, text="Desactivar", fg_color="#7A0000", command=self.desactivar).grid(row=0, column=2, padx=6)
        ctk.CTkButton(acciones, text="Cambiar clave", fg_color="#C00000", command=self.cambiar_clave).grid(row=0, column=3, padx=6)

    def _cargar(self):
        for it in self.tabla.get_children():
            self.tabla.delete(it)
        for fila in UsuarioService.listar():
            self.tabla.insert("", "end", values=(fila[0], fila[1], fila[2], fila[3], "Sí" if fila[4] else "No", fila[5]))

    def nuevo(self):
        nombre = simpledialog.askstring("Nuevo usuario", "Nombre:", parent=self)
        if not nombre:
            return
        usuario = simpledialog.askstring("Nuevo usuario", "Usuario (login):", parent=self)
        if not usuario:
            return
        clave = simpledialog.askstring("Nuevo usuario", "Clave:", parent=self)
        if clave is None:
            return
        rol = simpledialog.askstring("Nuevo usuario", "Rol (Administrador/Operador/Consulta):", parent=self)
        if rol not in UsuarioService.ROLES:
            messagebox.showerror("Usuarios", "Rol inválido.", parent=self); return
        UsuarioService.crear_usuario(nombre, usuario, clave, rol=rol)
        self._cargar()

    def editar(self):
        sel = self.tabla.selection()
        if not sel:
            messagebox.showwarning("Usuarios", "Seleccione un usuario.", parent=self); return
        datos = self.tabla.item(sel[0], "values")
        usuario_id = int(datos[0])
        nombre = simpledialog.askstring("Editar usuario", "Nombre:", initialvalue=datos[1], parent=self)
        if nombre is None:
            return
        rol = simpledialog.askstring("Editar usuario", "Rol:", initialvalue=datos[3], parent=self)
        if rol not in UsuarioService.ROLES:
            messagebox.showerror("Usuarios", "Rol inválido.", parent=self); return
        UsuarioService.modificar_usuario(usuario_id, nombre=nombre, rol=rol)
        self._cargar()

    def desactivar(self):
        sel = self.tabla.selection()
        if not sel:
            messagebox.showwarning("Usuarios", "Seleccione un usuario.", parent=self); return
        datos = self.tabla.item(sel[0], "values")
        usuario_id = int(datos[0])
        confirmar = messagebox.askyesno("Usuarios", "Desactivar este usuario?", parent=self)
        if not confirmar:
            return
        UsuarioService.modificar_usuario(usuario_id, activo=0)
        self._cargar()

    def cambiar_clave(self):
        sel = self.tabla.selection()
        if not sel:
            messagebox.showwarning("Usuarios", "Seleccione un usuario.", parent=self); return
        datos = self.tabla.item(sel[0], "values")
        usuario_id = int(datos[0])
        nueva = simpledialog.askstring("Cambiar clave", "Nueva clave:", parent=self)
        if nueva is None:
            return
        UsuarioService.cambiar_clave(usuario_id, nueva)
        messagebox.showinfo("Usuarios", "Clave actualizada.", parent=self)
