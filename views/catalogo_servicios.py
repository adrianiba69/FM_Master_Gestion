import customtkinter as ctk
from tkinter import ttk, messagebox

from services.catalogo_service import CatalogoService


class CatalogoServiciosWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Catálogo de Servicios")
        self.geometry("820x520")
        self.transient(master)
        self.grab_set()
        self.crear_interfaz()
        self.cargar_catalogo()

    def crear_interfaz(self):
        frame = ctk.CTkFrame(self, fg_color="white")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        barra = ctk.CTkFrame(frame, fg_color="transparent")
        barra.pack(fill="x")
        self.buscar = ctk.CTkEntry(barra, placeholder_text="Buscar...")
        self.buscar.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(barra, text="Buscar", command=self.cargar_busqueda).pack(side="left", padx=6)
        ctk.CTkButton(barra, text="Nuevo", fg_color="#C00000", command=self.nuevo).pack(side="right")

        tabla_frame = ctk.CTkFrame(frame)
        tabla_frame.pack(fill="both", expand=True, pady=(10,0))
        columnas = ("id", "nombre", "descripcion", "precio", "activo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        for col, txt in (("id","ID"),("nombre","Nombre"),("descripcion","Descripcion"),("precio","Precio"),("activo","Activo")):
            self.tabla.heading(col, text=txt)
        self.tabla.pack(fill="both", expand=True, side="left")
        ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview).pack(side="right", fill="y")
        self.tabla.bind("<<TreeviewSelect>>", lambda e: self.editar())

    def cargar_catalogo(self):
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        for fila in CatalogoService.listar(False):
            self.tabla.insert("", "end", values=fila)

    def cargar_busqueda(self):
        texto = self.buscar.get().strip()
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        for fila in CatalogoService.buscar(texto):
            self.tabla.insert("", "end", values=fila)

    def nuevo(self):
        from .catalogo_editor import CatalogoEditor
        CatalogoEditor(self, on_guardar=self.cargar_catalogo)

    def editar(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        fila = self.tabla.item(seleccion[0], "values")
        from .catalogo_editor import CatalogoEditor
        CatalogoEditor(self, catalogo_id=int(fila[0]), on_guardar=self.cargar_catalogo)
