import customtkinter as ctk
from tkinter import messagebox

from services.emisor_service import EmisorService


class EmisorEditor(ctk.CTkToplevel):
    def __init__(self, master, emisor_id=None, on_guardar=None):
        super().__init__(master)
        self.emisor_id = emisor_id
        self.on_guardar = on_guardar
        self.title("Editor Emisor")
        self.geometry("560x420")
        self.transient(master)
        self.grab_set()
        self.crear_interfaz()
        if emisor_id:
            self.cargar()

    def crear_interfaz(self):
        f = ctk.CTkFrame(self, fg_color="white")
        f.pack(fill="both", expand=True, padx=12, pady=12)
        self.alias = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Alias visible").pack(anchor="w")
        self.alias.pack(fill="x")
        self.titular = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Titular").pack(anchor="w", pady=(8,0))
        self.titular.pack(fill="x")
        self.nombre = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Nombre").pack(anchor="w", pady=(8,0))
        self.nombre.pack(fill="x")
        self.cuit = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="CUIT").pack(anchor="w", pady=(8,0))
        self.cuit.pack(fill="x")
        self.condicion = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Condicion IVA").pack(anchor="w", pady=(8,0))
        self.condicion.pack(fill="x")
        self.punto_venta = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Punto de venta").pack(anchor="w", pady=(8,0))
        self.punto_venta.pack(fill="x")
        self.tipo_comprobante = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Tipo de comprobante por defecto").pack(anchor="w", pady=(8,0))
        self.tipo_comprobante.pack(fill="x")
        self.orden_prioridad = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Orden de prioridad").pack(anchor="w", pady=(8,0))
        self.orden_prioridad.pack(fill="x")
        self.direccion = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Direccion").pack(anchor="w", pady=(8,0))
        self.direccion.pack(fill="x")
        self.localidad = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Localidad").pack(anchor="w", pady=(8,0))
        self.localidad.pack(fill="x")
        self.telefono = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Telefono").pack(anchor="w", pady=(8,0))
        self.telefono.pack(fill="x")
        self.email = ctk.CTkEntry(f)
        ctk.CTkLabel(f, text="Email").pack(anchor="w", pady=(8,0))
        self.email.pack(fill="x")
        self.observaciones = ctk.CTkTextbox(f, height=80)
        ctk.CTkLabel(f, text="Observaciones").pack(anchor="w", pady=(8,0))
        self.observaciones.pack(fill="x")

        self.activo_var = ctk.IntVar(value=1)
        ctk.CTkCheckBox(f, text="Activo", variable=self.activo_var).pack(anchor="w", pady=(8,0))
        ctk.CTkButton(f, text="Guardar", fg_color="#C00000", command=self.guardar).pack(anchor="e", pady=(12,0))

    def cargar(self):
        fila = EmisorService.obtener(self.emisor_id)
        if not fila:
            messagebox.showerror("Error", "No se encontro el emisor.", parent=self)
            self.destroy()
            return
        self.alias.insert(0, fila[1] or "")
        self.titular.insert(0, fila[2] or "")
        self.nombre.insert(0, fila[3] or "")
        self.cuit.insert(0, fila[4] or "")
        self.condicion.insert(0, fila[5] or "")
        self.punto_venta.insert(0, fila[6] or "")
        self.tipo_comprobante.insert(0, fila[7] or "")
        self.orden_prioridad.insert(0, str(fila[8] or 0))
        self.direccion.insert(0, fila[9] or "")
        self.localidad.insert(0, fila[10] or "")
        self.telefono.insert(0, fila[11] or "")
        self.email.insert(0, fila[12] or "")
        self.observaciones.insert("0.0", fila[14] or "")
        self.activo_var.set(1 if fila[13] else 0)

    def guardar(self):
        alias = self.alias.get().strip()
        if not alias:
            messagebox.showerror("Error", "Alias visible es obligatorio.", parent=self)
            return
        try:
            orden_prioridad = int(self.orden_prioridad.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Error", "Orden de prioridad debe ser numérico.", parent=self)
            return
        try:
            if self.emisor_id:
                EmisorService.actualizar(
                    self.emisor_id,
                    alias,
                    self.titular.get().strip(),
                    self.nombre.get().strip(),
                    self.cuit.get().strip(),
                    self.condicion.get().strip(),
                    self.punto_venta.get().strip(),
                    self.tipo_comprobante.get().strip(),
                    orden_prioridad,
                    self.direccion.get().strip(),
                    self.localidad.get().strip(),
                    self.telefono.get().strip(),
                    self.email.get().strip(),
                    1 if self.activo_var.get() else 0,
                    self.observaciones.get("0.0", "end").strip(),
                )
            else:
                EmisorService.guardar(
                    alias,
                    self.titular.get().strip(),
                    self.nombre.get().strip(),
                    self.cuit.get().strip(),
                    self.condicion.get().strip(),
                    self.punto_venta.get().strip(),
                    self.tipo_comprobante.get().strip(),
                    orden_prioridad,
                    self.direccion.get().strip(),
                    self.localidad.get().strip(),
                    self.telefono.get().strip(),
                    self.email.get().strip(),
                    1 if self.activo_var.get() else 0,
                    self.observaciones.get("0.0", "end").strip(),
                )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
            return
        if self.on_guardar:
            self.on_guardar()
        self.destroy()
