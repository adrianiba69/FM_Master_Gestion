from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from services.backup_service import BackupService
from services.emisor_service import EmisorService
from services.arca_ws_service import ArcaWsService


class ConfiguracionFrame(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master, fg_color="white", corner_radius=0)
        self.crear_interfaz()
        self.actualizar_estado()

    def crear_interfaz(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="CONFIGURACIÓN",
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

        self.boton_catalogo = ctk.CTkButton(
            acciones,
            text="Catálogo de Servicios",
            width=200,
            height=40,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_catalogo,
        )
        self.boton_catalogo.grid(row=0, column=3, padx=(10, 0))

        self.boton_emisores = ctk.CTkButton(
            acciones,
            text="Emisores Fiscales",
            width=200,
            height=40,
            fg_color="#333333",
            hover_color="#111111",
            command=self.abrir_emisores,
        )
        self.boton_emisores.grid(row=0, column=4, padx=(10, 0))

        self.crear_seccion_arca(seccion)

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

    def abrir_catalogo(self):
        try:
            from views.catalogo_servicios import CatalogoServiciosWindow
        except Exception as error:
            messagebox.showerror("Catálogo", f"No se pudo abrir el catálogo.\n{error}", parent=self)
            return
        CatalogoServiciosWindow(self)

    def abrir_emisores(self):
        try:
            from views.emisores_fiscales import EmisoresFiscalesWindow
        except Exception as error:
            messagebox.showerror("Emisores Fiscales", f"No se pudo abrir emisores fiscales.\n{error}", parent=self)
            return
        EmisoresFiscalesWindow(self)

    def crear_seccion_arca(self, contenedor):
        arca_frame = ctk.CTkFrame(contenedor, fg_color="#FFFFFF", corner_radius=6)
        arca_frame.grid(row=4, column=0, sticky="ew", padx=18, pady=(18, 16))
        arca_frame.grid_columnconfigure(0, weight=1)
        arca_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            arca_frame,
            text="CONFIGURACIÓN ARCA",
            font=("Arial", 18, "bold"),
            text_color="#222222",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(14, 10))

        self.emisores_arca = {"": None}
        for fila in EmisorService.listar(False):
            etiqueta = f"{fila[0]} - {fila[1]}"
            self.emisores_arca[etiqueta] = fila

        ctk.CTkLabel(arca_frame, text="Emisor ARCA:").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 4))
        self.selector_emisor_arca = ctk.CTkComboBox(
            arca_frame,
            values=list(self.emisores_arca.keys()),
            width=320,
            command=self.seleccionar_emisor_arca,
        )
        self.selector_emisor_arca.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 10))
        self.selector_emisor_arca.set("")

        ctk.CTkLabel(arca_frame, text="Modo ARCA:").grid(row=1, column=1, sticky="w", padx=18, pady=(0, 4))
        self.option_modo_arca = ctk.CTkComboBox(
            arca_frame,
            values=["Manual", "Homologación", "Producción"],
            width=240,
        )
        self.option_modo_arca.grid(row=2, column=1, sticky="w", padx=18, pady=(0, 10))
        self.option_modo_arca.set("Manual")

        self.entry_certificado = ctk.CTkEntry(arca_frame, placeholder_text="Ruta de certificado (.crt/.pem)")
        self.entry_certificado.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 10), columnspan=2)

        self.entry_clave_privada = ctk.CTkEntry(arca_frame, placeholder_text="Ruta de clave privada (.key/.pem)")
        self.entry_clave_privada.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10), columnspan=2)

        self.label_estado_arca = ctk.CTkLabel(
            arca_frame,
            text="Estado ARCA: Desconocido",
            font=("Arial", 11),
            text_color="#555555",
            anchor="w",
        )
        self.label_estado_arca.grid(row=5, column=0, sticky="w", padx=18, pady=(0, 10), columnspan=2)

        botones_arca = ctk.CTkFrame(arca_frame, fg_color="transparent")
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
