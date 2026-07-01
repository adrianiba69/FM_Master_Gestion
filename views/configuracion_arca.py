from tkinter import filedialog, messagebox

import customtkinter as ctk

from services.emisor_service import EmisorService
from services.arca_ws_service import ArcaWsService


class ConfiguracionArcaFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="#FFFFFF", corner_radius=6)
        self.grid_columnconfigure(0, weight=1)
        self.emisores_arca = {"": None}
        self.emisor_seleccionado_arca = None
        self.crear_interfaz()

    def crear_interfaz(self):
        ctk.CTkLabel(
            self,
            text="CONFIGURACIÓN ARCA",
            font=("Arial", 18, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 10))

        for fila in EmisorService.listar(False):
            etiqueta = f"{fila[0]} - {fila[1]}"
            self.emisores_arca[etiqueta] = fila

        ctk.CTkLabel(self, text="Emisor ARCA:").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 4))
        self.selector_emisor_arca = ctk.CTkComboBox(
            self,
            values=list(self.emisores_arca.keys()),
            width=320,
            command=self.seleccionar_emisor_arca,
        )
        self.selector_emisor_arca.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 10))
        self.selector_emisor_arca.set("")

        ctk.CTkLabel(self, text="Modo ARCA:").grid(row=1, column=1, sticky="w", padx=18, pady=(0, 4))
        self.option_modo_arca = ctk.CTkComboBox(
            self,
            values=["Manual", "Homologación", "Producción"],
            width=240,
        )
        self.option_modo_arca.grid(row=2, column=1, sticky="w", padx=18, pady=(0, 10))
        self.option_modo_arca.set("Manual")

        self.entry_certificado = ctk.CTkEntry(self, placeholder_text="Ruta de certificado (.crt/.pem)")
        self.entry_certificado.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10), columnspan=2)

        self.entry_clave_privada = ctk.CTkEntry(self, placeholder_text="Ruta de clave privada (.key/.pem)")
        self.entry_clave_privada.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10), columnspan=2)

        self.label_estado_arca = ctk.CTkLabel(
            self,
            text="Estado ARCA: Desconocido",
            font=("Arial", 11),
            text_color="#555555",
            anchor="w",
        )
        self.label_estado_arca.grid(row=5, column=0, sticky="w", padx=18, pady=(0, 10), columnspan=2)

        botones_arca = ctk.CTkFrame(self, fg_color="transparent")
        botones_arca.grid(row=6, column=0, sticky="w", padx=18, pady=(0, 14), columnspan=2)

        ctk.CTkButton(
            botones_arca,
            text="Seleccionar certificado",
            width=180,
            height=36,
            command=self.seleccionar_certificado,
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            botones_arca,
            text="Seleccionar clave",
            width=160,
            height=36,
            command=self.seleccionar_clave_privada,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            botones_arca,
            text="Validar ARCA",
            width=140,
            height=36,
            fg_color="#007A00",
            hover_color="#005500",
            command=self.validar_configuracion_arca,
        ).grid(row=0, column=2, padx=(0, 8))

        ctk.CTkButton(
            botones_arca,
            text="Guardar ARCA",
            width=140,
            height=36,
            fg_color="#C00000",
            hover_color="#990000",
            command=self.guardar_configuracion_arca,
        ).grid(row=0, column=3)

    def seleccionar_emisor_arca(self, label):
        self.emisor_seleccionado_arca = self.emisores_arca.get(label)
        if not self.emisor_seleccionado_arca:
            return
        self.entry_certificado.delete(0, "end")
        self.entry_certificado.insert(0, self.emisor_seleccionado_arca[15] or "")
        self.entry_clave_privada.delete(0, "end")
        self.entry_clave_privada.insert(0, self.emisor_seleccionado_arca[16] or "")
        self.option_modo_arca.set(self.emisor_seleccionado_arca[17] or "Manual")
        self.label_estado_arca.configure(text=f"Estado ARCA: {self.emisor_seleccionado_arca[18] or 'Desconocido'}")

    def seleccionar_certificado(self):
        ruta = filedialog.askopenfilename(filetypes=[("Certificado", "*.crt *.pem")], parent=self)
        if ruta:
            self.entry_certificado.delete(0, "end")
            self.entry_certificado.insert(0, ruta)

    def seleccionar_clave_privada(self):
        ruta = filedialog.askopenfilename(filetypes=[("Clave privada", "*.key *.pem")], parent=self)
        if ruta:
            self.entry_clave_privada.delete(0, "end")
            self.entry_clave_privada.insert(0, ruta)

    def validar_configuracion_arca(self):
        emisor = self.emisor_seleccionado_arca
        if not emisor:
            messagebox.showwarning("ARCA", "Seleccione un emisor ARCA primero.", parent=self)
            return
        emisor = list(emisor)
        emisor[15] = self.entry_certificado.get().strip()
        emisor[16] = self.entry_clave_privada.get().strip()
        emisor[17] = self.option_modo_arca.get().strip()
        valido, mensajes = ArcaWsService.probar_conexion(emisor)
        if valido:
            self.label_estado_arca.configure(text="Estado ARCA: Configuración lista")
            messagebox.showinfo("ARCA", "Configuración ARCA válida.", parent=self)
        else:
            self.label_estado_arca.configure(text="Estado ARCA: Configuración inválida")
            messagebox.showerror("ARCA", "\n".join(mensajes), parent=self)

    def guardar_configuracion_arca(self):
        emisor = self.emisor_seleccionado_arca
        if not emisor:
            messagebox.showwarning("ARCA", "Seleccione un emisor ARCA primero.", parent=self)
            return
        EmisorService.actualizar(
            emisor[0],
            emisor[1],
            emisor[2],
            emisor[3],
            emisor[4],
            emisor[5],
            emisor[6],
            emisor[7],
            emisor[8],
            emisor[9],
            emisor[10],
            emisor[11],
            emisor[12],
            emisor[13],
            self.entry_certificado.get().strip(),
            self.entry_clave_privada.get().strip(),
            self.option_modo_arca.get().strip(),
            emisor[18] or "Desconocido",
        )
        messagebox.showinfo("ARCA", "Configuración ARCA guardada.", parent=self)
