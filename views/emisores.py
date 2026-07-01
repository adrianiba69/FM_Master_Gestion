import customtkinter as ctk
from tkinter import ttk, messagebox

from services.emisor_service import EmisorService


class EmisoresWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Emisores de Facturación")
        self.geometry("920x520")
        self.transient(master)
        self.grab_set()
        self.crear_interfaz()
        self.cargar()

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
        columnas = ("id","nombre","cuit","condicion_iva","direccion","localidad","telefono","email","activo")
        self.tabla = ttk.Treeview(tabla_frame, columns=columnas, show="headings")
        for col in columnas:
            self.tabla.heading(col, text=col.capitalize())
        self.tabla.pack(fill="both", expand=True, side="left")
        ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tabla.yview).pack(side="right", fill="y")
        self.tabla.bind("<<TreeviewSelect>>", lambda e: self.editar())

    def cargar(self):
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        for fila in EmisorService.listar(False):
            self.tabla.insert("", "end", values=fila)

    def cargar_busqueda(self):
        texto = self.buscar.get().strip()
        for i in self.tabla.get_children():
            self.tabla.delete(i)
        for fila in EmisorService.listar(False):
            if texto.lower() in (str(fila[1]) + str(fila[2])).lower():
                self.tabla.insert("", "end", values=fila)

    def nuevo(self):
        from .emisor_editor import EmisorEditor
        EmisorEditor(self, on_guardar=self.cargar)

    def editar(self):
        sel = self.tabla.selection()
        if not sel:
            return
        fila = self.tabla.item(sel[0], "values")
        from .emisor_editor import EmisorEditor
        EmisorEditor(self, emisor_id=int(fila[0]), on_guardar=self.cargar)
